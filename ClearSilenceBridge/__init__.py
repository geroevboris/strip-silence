# Clear Silence Bridge v0.7 - Ableton Live 12 Python Remote Script.
# All Live API calls run on the Live main thread via update_display().
from __future__ import absolute_import, print_function
import os
import json
import queue
import socket
import threading
import traceback
import secrets
import math
import time
import types
from _Framework.ControlSurface import ControlSurface

HOST = '127.0.0.1'
PORT = 47861
TOKEN_FILE = os.path.expanduser('~/Library/Application Support/ClearSilence/bridge_token')
VERSION = '0.7.1'


def create_instance(c_instance):
    return ClearSilenceBridge(c_instance)


class ClearSilenceBridge(ControlSurface):
    def __init__(self, c_instance):
        super(ClearSilenceBridge, self).__init__(c_instance)
        self._requests = queue.Queue(maxsize=32)
        self._shutdown = threading.Event()
        self._server_socket = None
        self._pending_command = None
        folder = os.path.dirname(TOKEN_FILE)
        os.makedirs(folder, mode=0o700, exist_ok=True)
        if not os.path.isfile(TOKEN_FILE):
            with open(TOKEN_FILE, 'w') as f:
                f.write(secrets.token_hex(24))
            os.chmod(TOKEN_FILE, 0o600)
        with open(TOKEN_FILE, 'r') as f:
            self._token = f.read().strip()
        self._server_thread = threading.Thread(target=self._serve, name='ClearSilenceSocket', daemon=True)
        self._server_thread.start()
        self.log_message('ClearSilenceBridge %s loading (127.0.0.1:%d)' % (VERSION, PORT))

    def disconnect(self):
        if getattr(self, '_pending_command', None) is not None:
            command, result_q, _deadline = self._pending_command
            try:
                command.throw(RuntimeError('Мост отключён во время импорта.'))
            except (Exception, StopIteration) as exc:
                self._reply(result_q, {'ok': False, 'error': str(exc)})
            self._pending_command = None
        self._shutdown.set()
        try:
            if self._server_socket:
                self._server_socket.close()
        except Exception:
            pass
        # Wait for the listener to release its local port when the surface is reloaded.
        try:
            if self._server_thread.is_alive() and self._server_thread is not threading.current_thread():
                self._server_thread.join(timeout=1.5)
        except Exception:
            pass
        super(ClearSilenceBridge, self).disconnect()

    def _serve(self):
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((HOST, PORT))
            server.listen(4)
            server.settimeout(0.5)
            self._server_socket = server
            while not self._shutdown.is_set():
                try:
                    client, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    client.settimeout(30)
                    raw = bytearray()
                    while not raw.endswith(b'\n') and len(raw) < 350000:
                        block = client.recv(65536)
                        if not block:
                            break
                        raw.extend(block)
                    if len(raw) >= 350000:
                        raise ValueError('Request too large')
                    request = json.loads(bytes(raw).decode('utf-8'))
                    if request.get('token') != self._token:
                        raise ValueError('Invalid authorization token')
                    response = queue.Queue(maxsize=1)
                    timeout = 180 if request.get('action') == 'replace' else 25
                    deadline = time.monotonic() + timeout - 5
                    self._requests.put((request, response, deadline), timeout=2)
                    try:
                        result = response.get(timeout=timeout)
                    except queue.Empty:
                        raise TimeoutError('Live did not complete the command in %d seconds' % timeout)
                except Exception as e:
                    result = {'ok': False, 'error': str(e)}
                try:
                    client.sendall((json.dumps(result, ensure_ascii=False) + '\n').encode('utf-8'))
                except Exception:
                    pass
                finally:
                    client.close()
        except Exception as e:
            self.log_message('ClearSilence socket error: ' + repr(e))
        finally:
            try:
                server.close()
            except Exception:
                pass

    def update_display(self):
        super(ClearSilenceBridge, self).update_display()
        # A generator advances at most once per Live event. Returning to Live
        # is required: Warp setters are deferred internally, so sleeping here
        # or advancing the generator in a loop would keep reading stale state.
        if getattr(self, '_pending_command', None) is not None:
            self._advance_command()
            return
        try:
            request, result_q, deadline = self._requests.get_nowait()
        except queue.Empty:
            return
        try:
            if time.monotonic() >= deadline:
                raise RuntimeError('Команда устарела до начала обработки; изменений нет.')
            result = self._execute(request)
            if isinstance(result, types.GeneratorType):
                self._pending_command = (result, result_q, deadline)
                self._advance_command()
                return
        except Exception as exc:
            self.log_message('ClearSilence command error: ' + traceback.format_exc())
            result = {'ok': False, 'error': str(exc)}
        self._reply(result_q, result)

    @staticmethod
    def _reply(result_q, result):
        try:
            result_q.put_nowait(result)
        except queue.Full:
            pass

    def _advance_command(self):
        command, result_q, deadline = self._pending_command
        try:
            if time.monotonic() >= deadline:
                # Throw through the transaction's exception handler so Undo and
                # end_undo_step run. close() would skip that rollback handler.
                command.throw(RuntimeError('Live не завершил импорт вовремя.'))
            else:
                next(command)
            return
        except StopIteration as done:
            result = done.value
        except Exception as exc:
            self.log_message('ClearSilence command error: ' + traceback.format_exc())
            result = {'ok': False, 'error': str(exc)}
        self._pending_command = None
        self._reply(result_q, result)

    def _execute(self, req):
        action = req.get('action')
        song = self.song()
        if action == 'status':
            return {'ok': True, 'version': VERSION, 'tempo': float(song.tempo), 'tracks': len(song.tracks),
                    'can_replace': all(callable(getattr(song, n, None)) for n in ('begin_undo_step','end_undo_step','undo')),
                    'protocol': 13, 'actions': ['status', 'list', 'preview', 'replace']}
        if action == 'list':
            tracks = []
            for ti, track in enumerate(song.tracks):
                clips = []
                for ci, clip in enumerate(track.arrangement_clips):
                    if not clip.is_audio_clip:
                        continue
                    try:
                        path = str(clip.file_path)
                        clips.append({
                            'index': ci, 'name': str(clip.name),
                            'file_path': path, 'start': float(clip.start_time),
                            'end': float(clip.end_time),
                            'file_offset': float(clip.loop_start),
                            'file_end': float(clip.loop_end),
                            'warping': bool(clip.warping),
                            'looping': bool(clip.looping),
                            'gain': float(clip.gain),
                            'muted': bool(getattr(clip,'muted',False)), 'color': int(getattr(clip,'color',0)),
                            'has_groove': bool(getattr(clip, 'has_groove', False)),
                            'has_envelopes': bool(getattr(clip, 'has_envelopes', False)),
                            'pitch_coarse': int(clip.pitch_coarse),
                            'pitch_fine': int(clip.pitch_fine),
                        })
                    except Exception as e:
                        clips.append({'index': ci, 'name': str(clip.name), 'error': str(e)})
                if clips:
                    tracks.append({'index': ti, 'name': str(track.name), 'clips': clips,
                                   'can_take_lanes':callable(getattr(track, 'create_take_lane', None)) and hasattr(track, 'take_lanes')})
            selected = None
            try:
                selected_track = song.view.selected_track
                selected = next((i for i,tr in enumerate(song.tracks) if tr == selected_track), None)
            except Exception:
                pass
            return {'ok': True, 'version': VERSION, 'tempo': float(song.tempo),
                    'selected_track_index':selected, 'tracks': tracks}
        if action == 'replace':
            return self._replace(song, req)
        if action == 'preview':
            if song.is_playing or song.record_mode:
                raise RuntimeError('Stop playback and recording before creating preview')
            ti = int(req['track_index']); ci = int(req['clip_index'])
            if ti < 0 or ti >= len(song.tracks):
                raise ValueError('Track index invalid')
            track = song.tracks[ti]
            if ci < 0 or ci >= len(track.arrangement_clips):
                raise ValueError('Clip index invalid')
            clip = track.arrangement_clips[ci]
            info = req['source']
            if not clip.is_audio_clip or clip.warping or clip.looping:
                raise ValueError('Only unwarped, unlooped audio clips supported')
            if (abs(float(clip.start_time) - float(info['start'])) > 0.001
                    or abs(float(clip.end_time) - float(info['end'])) > 0.001
                    or abs(float(clip.loop_start) - float(info['file_offset'])) > 0.001
                    or abs(float(clip.loop_end) - float(info['file_end'])) > 0.001
                    or str(clip.file_path) != str(info['file_path'])):
                raise ValueError('Source clip changed. Refresh the list and retry.')
            if abs(float(song.tempo) - float(req['tempo'])) > 0.00001:
                raise ValueError('Tempo changed. Refresh analysis.')
            if not callable(getattr(track, 'create_audio_clip', None)):
                raise RuntimeError('Track.create_audio_clip is not available in this Live build')
            if not bool(track.has_audio_input) or bool(track.is_frozen):
                raise ValueError('Source track is not an editable audio track')
            items = req.get('fragments', [])
            if not 1 <= len(items) <= 60:
                raise ValueError('Prototype supports 1–60 fragments per clip')
            preview_dir = os.path.realpath(os.path.expanduser('~/Music/ClearSilence Preview'))
            ordered = sorted(items, key=lambda s: float(s['time']))
            last_end = -1.0
            for item in ordered:
                path = os.path.realpath(str(item['path']))
                if not path.startswith(preview_dir + os.sep) or not os.path.isfile(path):
                    raise ValueError('Generated file must be inside ClearSilence Preview')
                if not path.lower().endswith('.wav'):
                    raise ValueError('WAV fragments only')
                st = float(item['time']); ed = float(item['end'])
                if st < float(clip.start_time) - 0.001 or ed > float(clip.end_time) + 0.001 or st < last_end - 0.0001:
                    raise ValueError('Fragment times out of bounds or overlapping')
                last_end = ed
            if not callable(getattr(song, 'create_audio_track', None)):
                raise RuntimeError('Cannot create preview track')
            new_index = len(song.tracks)
            song.create_audio_track(new_index)
            new_track = song.tracks[new_index]
            new_track.name = 'Clear Silence PREVIEW - ' + str(clip.name)[:40]
            new_track.mute = True
            count = 0
            try:
                for item in ordered:
                    new_clip = new_track.create_audio_clip(str(item['path']), float(item['time']))
                    new_clip.warping = False
                    new_clip.looping = False
                    new_clip.name = 'CS ' + str(clip.name)[:35]
                    try:
                        new_clip.gain = float(clip.gain)
                    except Exception:
                        pass
                    count += 1
            except Exception:
                # No modification of source track: remove only our own freshly created track.
                song.delete_track(new_index)
                raise
            return {'ok': True, 'created': count, 'track_name': str(new_track.name), 'muted': True}
        return {'ok': False, 'error': 'Unknown action'}

    def _replace(self, song, req):
        """A yielded replacement on its EXISTING track; one undo unit per clip.

        Network and audio file work never happen on the Live UI thread. All
        fragment files must already exist. On error, one undo group is rolled
        back and the error is returned to the caller (which stops the batch).
        """
        if song.is_playing or song.record_mode:
            raise RuntimeError('Stop playback/recording before replacing a clip.')
        for method in ('begin_undo_step', 'end_undo_step', 'undo'):
            if not callable(getattr(song, method, None)):
                raise RuntimeError('Safe replacement requires Song.%s in this Live build. No edits performed.' % method)
        ti = int(req['track_index'])
        if not 0 <= ti < len(song.tracks):
            raise ValueError('Track index changed; refresh and analyze again')
        track = song.tracks[ti]
        source = req['source']
        if str(track.name) != str(req['track_name']):
            raise ValueError('Track name/order changed; analyze again')
        if not bool(track.has_audio_input) or bool(track.is_frozen):
            raise ValueError('Source track is not an editable audio track')
        if not callable(getattr(track, 'delete_clip', None)) or not callable(getattr(track, 'create_audio_clip', None)):
            raise RuntimeError('Track has no delete_clip/create_audio_clip; no edits made')
        if abs(float(song.tempo)-float(req['tempo'])) > 0.00001:
            raise ValueError('Tempo changed. Analyze again.')
        # The former arrangement index is NOT stable after earlier splits.
        # Find the source by a fingerprint and require an unambiguous match.
        matches = []
        for clip in list(track.arrangement_clips):
            if not clip.is_audio_clip:
                continue
            try:
                equivalent = (str(clip.file_path) == str(source['file_path'])
                    and str(clip.name) == str(source['name'])
                    and abs(float(clip.start_time)-float(source['start'])) < 0.0001
                    and abs(float(clip.end_time)-float(source['end'])) < 0.0001
                    and abs(float(clip.loop_start)-float(source['file_offset'])) < 0.0001
                    and abs(float(clip.loop_end)-float(source['file_end'])) < 0.0001
                    and abs(float(clip.gain)-float(source['gain'])) < 0.0001
                    and bool(clip.muted) == bool(source['muted'])
                    and not clip.warping and not clip.looping
                    and not bool(getattr(clip,'has_envelopes',False))
                    and not bool(getattr(clip,'has_groove',False))
                    and not int(clip.pitch_coarse) and not float(clip.pitch_fine))
                if equivalent:
                    matches.append(clip)
            except Exception:
                continue
        if len(matches) != 1:
            raise ValueError('Source clip missing/ambiguous/changed; nothing replaced (matches=%d)' % len(matches))
        clip = matches[0]
        items = sorted(req['fragments'], key=lambda x: float(x['time']))
        if len(items) > 150:
            raise ValueError('More than 150 fragments; increase Min Silence')
        root = os.path.realpath(os.path.expanduser('~/Music/ClearSilence Output'))
        last_end = float(source['start'])
        for item in items:
            path = os.path.realpath(str(item['path']))
            if not path.startswith(root+os.sep) or not os.path.isfile(path) or not path.lower().endswith('.wav'):
                raise ValueError('Fragment must be an existing generated WAV inside ClearSilence Output')
            st, ed = float(item['time']), float(item['end'])
            if (st < last_end-0.0001 or ed <= st or
                    ed > float(source['end'])+0.0001):
                raise ValueError('Fragment positions invalid/overlapping/outside original clip')
            last_end = ed
        # The removal plan explicitly includes fully silent clips.
        if not items and not bool(req.get('allow_empty', False)):
            raise ValueError('Refusing to delete all-silent clip without explicit permission')
        backup = req.get('backup')
        if backup:
            path = os.path.realpath(str(backup['path']))
            if not path.startswith(root+os.sep) or not os.path.isfile(path) or not path.lower().endswith('.wav'):
                raise ValueError('Backup must be an existing generated WAV inside ClearSilence Output')
            if (abs(float(backup['time'])-float(source['start'])) > .0001 or
                    abs(float(backup['end'])-float(source['end'])) > .0001):
                raise ValueError('Backup range must match the entire original clip')
            if not self._supports_take_lanes(track):
                raise RuntimeError('Take Lanes unavailable; original clip has not been removed')
            if not str(backup['lane_name']).startswith('Clear Silence · Original · '):
                raise ValueError('Invalid backup lane name')
        rate = int(req['rate'])
        if rate <= 0:
            raise ValueError('Invalid sample rate')
        tolerance = max(.0001, 2.1 * float(song.tempo) / 60 / rate)
        for item in items + ([backup] if backup else []):
            frames = item.get('frames')
            if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
                raise ValueError('Generated audio must declare its sample count')
            if abs(frames / rate * float(song.tempo) / 60 -
                   (float(item['end'])-float(item['time']))) > tolerance:
                raise ValueError('Generated audio sample count does not match its timeline range')
        protected = self._clip_signatures([c for c in track.arrangement_clips if c != clip])
        before_lanes = list(getattr(track, 'take_lanes', []))
        before_main = self._clip_signatures(track.arrangement_clips)
        before_takes = [(lane, self._clip_signatures(lane.arrangement_clips)) for lane in before_lanes]
        lane = None
        lane_before = []
        song.begin_undo_step()
        n = 0
        error = None
        did_change = False
        try:
            if backup:
                lanes = [x for x in track.take_lanes if str(x.name) == str(backup['lane_name'])]
                if len(lanes) > 1:
                    raise RuntimeError('Backup lane is ambiguous')
                if lanes:
                    lane = lanes[0]
                else:
                    track.create_take_lane()
                    created = [x for x in track.take_lanes if x not in before_lanes]
                    if len(created) != 1:
                        raise RuntimeError('Live did not create exactly one take lane')
                    lane = created[0]
                    did_change = True
                    lane.name = str(backup['lane_name'])
                if not callable(getattr(lane, 'create_audio_clip', None)):
                    raise RuntimeError('TakeLane.create_audio_clip unavailable')
                lane_before = list(lane.arrangement_clips)
                if any(float(c.start_time) < float(backup['end'])-tolerance and
                       float(c.end_time) > float(backup['time'])+tolerance for c in lane_before):
                    raise RuntimeError('Backup lane already contains audio in this range')
                preserved = self._clip_signatures(lane_before)
                yield from self._insert_audio(lane, backup, source, tolerance, rate, 'резерв Take Lane')
                did_change = True
                remaining = [c for c in lane.arrangement_clips if c in lane_before]
                if self._clip_signatures(remaining) != preserved:
                    raise RuntimeError('Existing backup clips changed; rolling back')
                # Only delete the main clip AFTER the complete backup is verified.
            if song.is_playing or song.record_mode:
                raise RuntimeError('Воспроизведение запущено во время импорта; замена остановлена.')
            if (abs(float(song.tempo)-float(req['tempo'])) > .00001 or
                    self._clip_signatures(track.arrangement_clips) != before_main):
                raise RuntimeError('Темп или исходные клипы изменились во время импорта.')
            track.delete_clip(clip)
            did_change = True
            # Check deletion before inserting at identical positions.
            if len(track.arrangement_clips) >= int(req['before_count']):
                raise RuntimeError('Original clip was not removed; aborting')
            made = []
            for index, item in enumerate(items):
                made.append((yield from self._insert_audio(
                    track, item, source, tolerance, rate, 'фрагмент %d/%d' % (index+1, len(items)))))
                n += 1
                if song.is_playing or song.record_mode or abs(float(song.tempo)-float(req['tempo'])) > .00001:
                    raise RuntimeError('Воспроизведение или темп изменились во время импорта.')
            if self._clip_signatures([c for c in track.arrangement_clips if c not in made]) != protected:
                raise RuntimeError('Neighbouring clips changed; rolling back')
            if len(track.arrangement_clips) != int(req['before_count'])-1+n:
                raise RuntimeError('Unexpected clip count after replacement')
        except Exception as exc:
            error = exc
        finally:
            try:
                song.end_undo_step()
            except Exception as exc:
                if error is None:
                    error = exc
        if error is not None:
            # Do not undo an unrelated user edit if no change was made.
            if (did_change or self._clip_signatures(track.arrangement_clips) != before_main
                    or list(getattr(track, 'take_lanes', [])) != before_lanes
                    or any(self._clip_signatures(lane.arrangement_clips) != signature for lane, signature in before_takes)):
                try:
                    song.undo()
                except Exception as rollback_error:
                    raise RuntimeError('REPLACEMENT FAILED: %s. ALSO UNDO FAILED: %s. Stop and inspect the project; original WAV is intact.' % (error, rollback_error))
                raise RuntimeError('Замена отменена через Undo. %s' % error)
            raise RuntimeError('Замена остановлена до изменения основного клипа. %s' % error)
        return {'ok': True, 'created': n, 'removed': 1, 'backed_up': bool(backup),
                'track_name': str(track.name), 'clip_name': source['name']}


    @staticmethod
    def _supports_take_lanes(track):
        return callable(getattr(track, 'create_take_lane', None)) and hasattr(track, 'take_lanes')

    @staticmethod
    def _clip_signatures(clips):
        return sorted((str(c.file_path), str(c.name), float(c.start_time), float(c.end_time),
                       float(c.loop_start), float(c.loop_end), float(c.gain), bool(c.muted))
                      for c in clips)

    @staticmethod
    def _same_audio_path(first, second):
        try:
            return os.path.samefile(str(first), str(second))
        except OSError:
            return os.path.realpath(str(first)) == os.path.realpath(str(second))

    def _insert_audio(self, container, item, source, tolerance, rate, stage):
        before = list(container.arrangement_clips)
        returned = container.create_audio_clip(str(item['path']), float(item['time']))
        added = [c for c in container.arrangement_clips if c not in before]
        if len(added) != 1:
            raise RuntimeError('%s: Live создал %d клипов вместо одного.' % (stage, len(added)))
        clip = added[0]
        if returned is not None and returned != clip:
            raise RuntimeError('%s: Live вернул другой клип.' % stage)
        clip.warping = False
        # Even a getter already returning False does not guarantee that Live's
        # deferred geometry change has been applied. Always yield at least once.
        ready = 0
        for _ in range(30):
            yield
            ready = ready + 1 if not clip.warping else 0
            if ready >= 2:
                break
        else:
            raise RuntimeError('%s: Warp остался включён после ожидания Live.' % stage)
        clip.looping = False
        clip.name = str(source['name'])[:120]
        clip.gain = float(source['gain'])
        clip.muted = bool(source['muted'])
        clip.color = int(source['color'])
        # These are NEW, full-file WAVs, so their visible source range is known
        # exactly. Loop markers use seconds only after Warp has actually turned
        # off. Do not touch start_marker/end_marker (their units differ).
        duration = int(item['frames']) / rate
        if abs(float(clip.loop_start)) > 1 / rate:
            clip.loop_start = 0.
        if abs(float(clip.loop_end)-duration) > 1 / rate:
            clip.loop_end = duration
        yield
        problems = []
        if not self._same_audio_path(clip.file_path, item['path']):
            problems.append('file_path: Live=%r; ожидалось=%r' % (str(clip.file_path), str(item['path'])))
        for name, wanted, epsilon in (
                ('start_time', float(item['time']), tolerance),
                ('end_time', float(item['end']), tolerance),
                ('loop_start', 0., 1.1 / rate),
                ('loop_end', duration, 1.1 / rate),
                ('gain', float(source['gain']), .0001)):
            actual = float(getattr(clip, name))
            if not math.isfinite(actual) or abs(actual-wanted) > epsilon:
                problems.append('%s: Live=%.8f; ожидалось=%.8f; допуск=%.8f' % (name, actual, wanted, epsilon))
        for name, wanted in (('warping', False), ('looping', False), ('muted', bool(source['muted']))):
            actual = bool(getattr(clip, name))
            if actual != wanted:
                problems.append('%s: Live=%s; ожидалось=%s' % (name, actual, wanted))
        if problems:
            raise RuntimeError('%s: %s' % (stage, '; '.join(problems)))
        return clip
