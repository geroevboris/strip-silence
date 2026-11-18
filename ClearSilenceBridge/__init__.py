# Clear Silence Bridge v0.3 - Ableton Live 12 Python Remote Script.
# All Live API calls run on the Live main thread via update_display().
from __future__ import absolute_import, print_function
import os
import json
import queue
import socket
import threading
import traceback
import secrets
from _Framework.ControlSurface import ControlSurface

HOST = '127.0.0.1'
PORT = 47861
TOKEN_FILE = os.path.expanduser('~/Library/Application Support/ClearSilence/bridge_token')
VERSION = '0.5.7'


def create_instance(c_instance):
    return ClearSilenceBridge(c_instance)


class ClearSilenceBridge(ControlSurface):
    def __init__(self, c_instance):
        super(ClearSilenceBridge, self).__init__(c_instance)
        self._requests = queue.Queue(maxsize=32)
        self._shutdown = threading.Event()
        self._server_socket = None
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
                    self._requests.put((request, response), timeout=2)
                    try:
                        result = response.get(timeout=25)
                    except queue.Empty:
                        raise TimeoutError('Live did not process command in 25 seconds')
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
        # Never call the Live Object Model from the socket thread.
        for _ in range(2):
            try:
                request, result_q = self._requests.get_nowait()
            except queue.Empty:
                break
            try:
                result = self._execute(request)
            except Exception as e:
                self.log_message('ClearSilence command error: ' + traceback.format_exc())
                result = {'ok': False, 'error': str(e)}
            try:
                result_q.put_nowait(result)
            except queue.Full:
                pass

    def _execute(self, req):
        action = req.get('action')
        song = self.song()
        if action == 'status':
            return {'ok': True, 'version': VERSION, 'tempo': float(song.tempo), 'tracks': len(song.tracks),
                    'can_replace': all(callable(getattr(song, n, None)) for n in ('begin_undo_step','end_undo_step','undo')),
                    'protocol': 8, 'actions': ['status', 'list', 'preview', 'split_mute', 'probe_region', 'native_prepare', 'native_arm', 'native_confirm', 'native_verify', 'native_cleanup']}
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
                    tracks.append({'index': ti, 'name': str(track.name), 'clips': clips})
            selected = None
            try:
                selected_track = song.view.selected_track
                selected = next((i for i,tr in enumerate(song.tracks) if tr == selected_track), None)
            except Exception:
                pass
            return {'ok': True, 'version': VERSION, 'tempo': float(song.tempo),
                    'selected_track_index':selected, 'tracks': tracks}
        if action == 'probe_region':
            return self._probe_region(song, req)
        if action == 'native_prepare':
            return self._native_prepare(song, req)
        if action == 'native_arm':
            return self._native_arm(song, req)
        if action == 'native_confirm':
            return self._native_confirm(song, req)
        if action == 'native_verify':
            return self._native_verify(song, req)
        if action == 'native_cleanup':
            return self._native_cleanup(song, req)
        if action == 'split_mute':
            return self._split_mute(song, req)
        if action == 'replace':
            raise RuntimeError('Старый режим с удалением клипов отключён. Обнови Clear Silence.')
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

    def _native_test_track(self, song):
        state = getattr(self, '_native_test_state', None)
        if not state:
            raise RuntimeError('Сначала подготовь тест.')
        index = state['index']
        if index >= len(song.tracks):
            raise RuntimeError('Тестовая дорожка перемещена или удалена. '
                               'Не изменяю чужие дорожки.')
        track = song.tracks[index]
        if track.name != state['name'] or not bool(track.mute):
            raise RuntimeError('Тестовая дорожка изменена. '
                               'Не изменяю чужие дорожки.')
        return state, track

    def _native_prepare(self, song, req):
        """Create a muted test track for user's real Arrangement Cmd+E."""
        if song.is_playing or song.record_mode:
            raise RuntimeError('Останови Live перед тестом.')
        if getattr(self, '_native_test_state', None):
            raise RuntimeError('Сначала удали предыдущий тест.')
        ti, ci = int(req['track_index']), int(req['clip_index'])
        if not 0 <= ti < len(song.tracks):
            raise RuntimeError('Исходная дорожка не найдена.')
        orig_track = song.tracks[ti]
        if not 0 <= ci < len(orig_track.arrangement_clips):
            raise RuntimeError('Исходный клип не найден.')
        src = orig_track.arrangement_clips[ci]
        if not src.is_audio_clip or src.warping or src.looping:
            raise RuntimeError('Нужен WAV без Warp и Loop.')
        path = str(src.file_path)
        if not os.path.isfile(path):
            raise RuntimeError('Исходный WAV не найден.')
        if not callable(getattr(song, 'create_audio_track', None)) or not callable(getattr(song, 'delete_track', None)):
            raise RuntimeError('Live не поддерживает тест на отдельной дорожке.')
        index = len(song.tracks)
        created = False
        name = 'Clear Silence SPLIT TEST ' + secrets.token_hex(3)
        try:
            song.create_audio_track(index)
            created = True
            track = song.tracks[index]
            track.name = name
            track.mute = True
            intended_start = float(src.start_time)
            clip = track.create_audio_clip(path, intended_start)
            if abs(float(clip.start_time) - intended_start) > 0.005:
                raise RuntimeError('Тестовый клип оказался не на позиции оригинала.')
            clip.warping = False
            clip.looping = False
            if str(clip.file_path) != path or len(track.arrangement_clips) != 1:
                raise RuntimeError('Тестовый клип не совпал с исходным WAV.')
            self._native_test_state = {
                'index': index, 'name': name, 'path': path,
                'start': float(clip.start_time), 'end': float(clip.end_time),
                'source_index': ti, 'source_count': len(orig_track.arrangement_clips),
                'source_start': float(src.start_time), 'source_end': float(src.end_time)}
            try:
                song.view.selected_track = track
                song.view.detail_clip = clip
            except Exception:
                pass
            return {'ok': True, 'track_name': name,
                    'start': float(clip.start_time), 'end': float(clip.end_time),
                    'message': 'В Ableton найди заглушённую дорожку ' + name +
                               '. Кликни ВНУТРИ тестового клипа и нажми Cmd+E. '
                               'Вернись и нажми «Проверить». Исходный клип не менялся.'}
        except Exception:
            if created and len(song.tracks) == index + 1:
                try:
                    song.delete_track(index)
                except Exception:
                    raise RuntimeError('Тестовая дорожка осталась в проекте. '
                                       'НЕ СОХРАНЯЙ проект.')
            self._native_test_state = None
            raise

    def _native_arm(self, song, req):
        """Position playhead inside the temporary test clip, before UI Split."""
        if song.is_playing or song.record_mode:
            raise RuntimeError('Останови воспроизведение и запись.')
        state, track = self._native_test_track(song)
        clips = list(track.arrangement_clips)
        if len(clips) != 1:
            raise RuntimeError('На тестовой дорожке должен быть один клип.')
        clip = clips[0]
        if (not clip.is_audio_clip or clip.warping or
                str(clip.file_path) != state['path'] or
                abs(float(clip.start_time)-state['start']) > .005 or
                abs(float(clip.end_time)-state['end']) > .005):
            raise RuntimeError('Тестовый клип изменился. Не отправляю клавиши.')
        view = getattr(song, 'view', None)
        if view is None:
            raise RuntimeError('Live не предоставляет выбор дорожки.')
        # Critical: do NOT assign view.selected_track or detail_clip here.
        # The user has focused the desired Arrangement waveform before
        # switching to Clear Silence. Assigning these properties destroys
        # the waveform's insert selection, causing Cmd+E to do nothing or
        # operate with a broad arrangement selection.
        if view.selected_track != track:
            raise RuntimeError(
                'В Ableton не выбрана тестовая дорожка. '
                'Кликни ВНУТРИ осциллограммы на дорожке "' + state['name'] +
                '" и снова нажми «Авто Split». Cmd+E не отправлена.')
        duration = state['end'] - state['start']
        if duration <= .2:
            raise RuntimeError('Слишком короткий тестовый клип.')
        target = state['start'] + min(4.0, duration / 2.0)
        # Live may read back the OLD position within this same callback.
        # Confirm on a later Live tick, via a distinct Bridge request.
        song.current_song_time = target
        state['auto_boundary'] = target
        state['auto_confirmed'] = False
        # Record other tracks, so a GUI action cannot silently affect them.
        state['other_snapshot'] = tuple(
            (str(t.name), tuple(
                (str(cl.file_path) if cl.is_audio_clip else 'MIDI',
                 round(float(cl.start_time), 4),
                 round(float(cl.end_time), 4),
                 bool(cl.muted)) for cl in t.arrangement_clips))
            for t in song.tracks if t != track)
        # Do not force the Arranger/Clip View focus here. On Live 12,
        # focus_view can change the selection that Cmd+E operates on.
        # macOS returns to the previously focused Live editing surface.
        return {'ok': True, 'target_beat': round(target, 5),
                'test_track_name': state['name']}

    def _native_confirm(self, song, req):
        """Read transport position in a SEPARATE Live main-thread callback."""
        state, track = self._native_test_track(song)
        if 'auto_boundary' not in state:
            raise RuntimeError('Точка разреза не подготовлена.')
        target = float(state['auto_boundary'])
        observed = float(song.current_song_time)
        confirmed = abs(observed - target) <= .02
        state['auto_confirmed'] = confirmed
        return {'ok': True, 'confirmed': confirmed,
                'target_beat': round(target, 5),
                'observed_beat': round(observed, 5)}

    def _native_verify(self, song, req):
        """Check real split timeline, then mute the right TEST clip only."""
        state, track = self._native_test_track(song)
        source_track = song.tracks[state['source_index']]
        if (len(source_track.arrangement_clips) != state['source_count']
                or not any(c.is_audio_clip and str(c.file_path) == state['path']
                           and abs(float(c.start_time)-state['source_start']) < .0001
                           and abs(float(c.end_time)-state['source_end']) < .0001
                           for c in source_track.arrangement_clips)):
            raise RuntimeError('Исходная дорожка неожиданно изменилась. '
                               'Проверь проект до сохранения.')
        if 'auto_boundary' in state and not state.get('auto_confirmed', False):
            raise RuntimeError('Положение playhead не подтверждено. Mute не выполнялся.')
        before = state.get('other_snapshot')
        if before is not None:
            after = tuple(
                (str(t.name), tuple(
                    (str(cl.file_path) if cl.is_audio_clip else 'MIDI',
                     round(float(cl.start_time), 4),
                     round(float(cl.end_time), 4),
                     bool(cl.muted)) for cl in t.arrangement_clips))
                for t in song.tracks if t != track)
            if after != before:
                raise RuntimeError('GUI изменила другую дорожку! '
                                   'Не сохраняй проект; проверь Undo.')
        clips = sorted(track.arrangement_clips, key=lambda c: float(c.start_time))
        if len(clips) != 2:
            return {'ok': True, 'passed': False, 'count': len(clips),
                    'message': 'На тестовой дорожке остался %d клип(ов): '
                               'команда Cmd+E не разделила её. '
                               'Вероятнее всего, фокус был не внутри '
                               'осциллограммы тестового клипа. '
                               'Другие клипы не обрабатывались. '
                               'Сначала кликни по волне внутри тестового '
                               'клипа в Arrangement, затем повтори тест '
                               '(подготовь новый тест после удаления '
                               'предыдущего).' % len(clips)}
        left, right = clips
        valid = (all(c.is_audio_clip and str(c.file_path) == state['path']
                     and not c.warping for c in clips)
                 and abs(float(left.start_time)-state['start']) < .005
                 and abs(float(right.end_time)-state['end']) < .005
                 and abs(float(left.end_time)-float(right.start_time)) < .005
                 and float(left.end_time)-float(left.start_time) > .05
                 and float(right.end_time)-float(right.start_time) > .05
                 and ('auto_boundary' not in state or
                      abs(float(right.start_time)-state['auto_boundary']) < .06))
        if not valid:
            return {'ok': True, 'passed': False, 'count': 2,
                    'message': 'Два клипа есть, но границы не совпадают '
                               'или изменился исходный аудиофайл.',
                    'pieces': [{'start': float(c.start_time),
                                'end': float(c.end_time),
                                'same_file': str(c.file_path) == state['path']}
                               for c in clips]}
        left.muted = False
        right.muted = True
        if left.muted or not right.muted:
            raise RuntimeError('Live не подтвердил Mute.')
        return {'ok': True, 'passed': True, 'count': 2,
                'boundary': round(float(right.start_time), 5),
                'source_file_preserved': True,
                'message': 'Нативный Split подтверждён: обе части ссылаются '
                           'на полный исходный WAV. Правая часть заглушена. '
                           'Можешь размьютить и растянуть её, затем удали тест.'}

    def _native_cleanup(self, song, req):
        state, track = self._native_test_track(song)
        if any(not c.is_audio_clip or str(c.file_path) != state['path']
               for c in track.arrangement_clips):
            raise RuntimeError('На тестовой дорожке появились другие клипы. '
                               'Автоматически удалять её небезопасно.')
        song.delete_track(state['index'])
        self._native_test_state = None
        return {'ok': True, 'removed': True,
                'message': 'Удалена только тестовая дорожка.'}

    def _probe_region(self, song, req):
        """Non-destructive compatibility probe on a TEMPORARY muted audio track.

        Tests whether arrangement audio can be trimmed AFTER placement without
        writing new/shortened WAV files. Does not touch the selected source
        track; no production clip replacement is attempted.
        """
        if song.is_playing or song.record_mode:
            raise RuntimeError('Останови воспроизведение/запись перед тестом.')
        ti, ci = int(req['track_index']), int(req['clip_index'])
        if not 0 <= ti < len(song.tracks):
            raise RuntimeError('Дорожка не найдена.')
        source_track = song.tracks[ti]
        clips = source_track.arrangement_clips
        if not 0 <= ci < len(clips):
            raise RuntimeError('Клип не найден.')
        source = clips[ci]
        if not source.is_audio_clip or source.warping or source.looping:
            raise RuntimeError('Для теста выбери WAV-клип без Warp/Loop.')
        source_path = str(source.file_path)
        if not os.path.isfile(source_path):
            raise RuntimeError('Не найден исходный WAV.')
        source_start, source_end = float(source.loop_start), float(source.loop_end)
        span = source_end - source_start
        if span < .18:
            raise RuntimeError('Слишком короткий исходный клип.')
        a = source_start + min(.37, span * .2)
        b = min(source_end, a + min(.73, span * .35))
        if b - a < .04:
            raise RuntimeError('Слишком короткий интервал для теста.')
        position = 8.0
        expected = position + (b - a) * float(song.tempo) / 60.0
        if not callable(getattr(song, 'create_audio_track', None)):
            raise RuntimeError('Live не разрешает создать временную дорожку.')
        if not callable(getattr(song, 'delete_track', None)):
            raise RuntimeError('Live не разрешает удалить временную дорожку.')
        original_track_count = len(song.tracks)
        results = []
        scratch_created = False
        undo_open = False
        cleanup_error = None

        def inspect(method, clip):
            """Read the actual arrangement duration, not mock expectations."""
            return {
                'method': method,
                'start': round(float(clip.start_time), 5),
                'end': round(float(clip.end_time), 5),
                'loop_start': round(float(clip.loop_start), 5),
                'loop_end': round(float(clip.loop_end), 5),
                'start_marker': round(float(clip.start_marker), 5),
                'end_marker': round(float(clip.end_marker), 5),
                'expected_end': round(expected, 5),
                'difference_beats': round(float(clip.end_time) - expected, 5),
                'same_file': str(clip.file_path) == source_path,
                'ok': (abs(float(clip.start_time) - position) <= .01
                       and abs(float(clip.end_time) - expected) <= .02
                       and abs(float(clip.loop_start) - a) <= .01
                       and abs(float(clip.loop_end) - b) <= .01
                       and str(clip.file_path) == source_path
                       and not bool(clip.warping))
            }

        def trim(clip):
            clip.warping = False
            clip.looping = False
            # Live may duplicate a full-length Session clip; trim in
            # Arrangement *after* placement. Check real start/end time.
            clip.loop_end = b
            clip.loop_start = a
            clip.end_marker = b
            clip.start_marker = a

        try:
            song.begin_undo_step()
            undo_open = True
            song.create_audio_track(original_track_count)
            scratch_created = True
            scratch = song.tracks[original_track_count]
            scratch.name = 'Clear Silence TEMP / compatibility check'
            scratch.mute = True
            if not callable(getattr(scratch, 'create_audio_clip', None)):
                results.append({'method': 'direct', 'ok': False,
                                'error': 'create_audio_clip недоступен'})
            else:
                try:
                    fresh = scratch.create_audio_clip(source_path, position)
                    trim(fresh)
                    results.append(inspect('direct_then_trim', fresh))
                except Exception as ex:
                    results.append({'method': 'direct_then_trim', 'ok': False,
                                    'error': str(ex)})
                finally:
                    for c in tuple(scratch.arrangement_clips):
                        scratch.delete_clip(c)
            if not callable(getattr(scratch, 'duplicate_clip_to_arrangement', None)):
                results.append({'method': 'session_then_trim', 'ok': False,
                                'error': 'duplicate_clip_to_arrangement недоступен'})
            else:
                try:
                    slot = next((s for s in scratch.clip_slots
                                 if not s.has_clip and
                                    callable(getattr(s, 'create_audio_clip', None))), None)
                    if slot is None:
                        raise RuntimeError('Нет пустого Session-слота')
                    slot.create_audio_clip(source_path)
                    session = slot.clip
                    session.warping = False
                    session.looping = False
                    created = scratch.duplicate_clip_to_arrangement(session, position)
                    trim(created)
                    results.append(inspect('session_then_trim', created))
                except Exception as ex:
                    results.append({'method': 'session_then_trim', 'ok': False,
                                    'error': str(ex)})
                finally:
                    for c in tuple(scratch.arrangement_clips):
                        scratch.delete_clip(c)
                    for slot in scratch.clip_slots:
                        if slot.has_clip:
                            slot.delete_clip()
        finally:
            if scratch_created:
                try:
                    song.delete_track(original_track_count)
                except Exception as ex:
                    cleanup_error = str(ex)
            if undo_open:
                try:
                    song.end_undo_step()
                except Exception as ex:
                    cleanup_error = cleanup_error or str(ex)
            if len(song.tracks) != original_track_count or cleanup_error:
                try:
                    song.undo()
                except Exception as ex:
                    raise RuntimeError('Не удалось удалить тестовую дорожку; '
                                       'НЕ СОХРАНЯЙ проект. %s; undo: %s' %
                                       (cleanup_error, ex))
                if len(song.tracks) != original_track_count:
                    raise RuntimeError('Не удалось восстановить число дорожек. '
                                       'НЕ СОХРАНЯЙ проект.')
        return {
            'ok': True, 'version': VERSION,
            'expected_start': position,
            'expected_end': round(expected, 5),
            'source_range_seconds': [round(a, 5), round(b, 5)],
            'results': results,
            'supported': any(item.get('ok') for item in results),
            'original_tracks_unchanged': len(song.tracks) == original_track_count,
            'message': ('Проверка на временной дорожке завершена; оригинал не изменялся.'
                        if any(item.get('ok') for item in results)
                        else 'Live не подтвердил ни один безопасный способ. '
                             'Применение к исходным клипам заблокировано.')
        }

    def _split_mute(self, song, req):
        """Rebuild a clip as source-referencing regions, muting only the gaps.

        Unlike the old WAV slice method, every new region references the FULL
        original WAV. Editing/unmuting/revealing source material is possible.
        Do not run against anything but a copy of the Live Set until verified.
        """
        if song.is_playing or song.record_mode:
            raise RuntimeError('Останови воспроизведение и запись перед обработкой.')
        for attr in ('begin_undo_step','end_undo_step','undo'):
            if not callable(getattr(song,attr,None)):
                raise RuntimeError('Не поддерживается Song.%s (нужен откат Undo).' % attr)
        ti = int(req['track_index'])
        if ti < 0 or ti >= len(song.tracks):
            raise RuntimeError('Дорожка изменила положение. Повтори анализ.')
        track = song.tracks[ti]
        source = req['source']
        if str(track.name) != str(req['track_name']):
            raise RuntimeError('Дорожка изменилась. Повтори анализ.')
        if not bool(track.has_audio_input) or bool(track.is_frozen):
            raise RuntimeError('Доступна только незамороженная аудиодорожка.')
        if not callable(getattr(track,'duplicate_clip_to_arrangement',None)):
            raise RuntimeError('Отсутствует дублирование клипа из Session в Arrangement.')
        if abs(float(song.tempo)-float(req['tempo'])) > 0.00001:
            raise RuntimeError('Темп изменился. Повтори анализ.')
        matches=[]
        for candidate in list(track.arrangement_clips):
            if not candidate.is_audio_clip:
                continue
            try:
                same=(str(candidate.file_path)==str(source['file_path'])
                      and str(candidate.name)==str(source['name'])
                      and abs(float(candidate.start_time)-float(source['start']))<0.0001
                      and abs(float(candidate.end_time)-float(source['end']))<0.0001
                      and abs(float(candidate.loop_start)-float(source['file_offset']))<0.0001
                      and abs(float(candidate.loop_end)-float(source['file_end']))<0.0001
                      and abs(float(candidate.gain)-float(source['gain']))<0.0001
                      and bool(candidate.muted)==bool(source['muted'])
                      and not candidate.warping and not candidate.looping
                      and not bool(getattr(candidate,'has_envelopes',False))
                      and not bool(getattr(candidate,'has_groove',False)))
                if same:
                    matches.append(candidate)
            except Exception:
                continue
        if len(matches)!=1:
            raise RuntimeError('Исходный клип изменён или не найден однозначно (%d).' % len(matches))
        original=matches[0]
        regions=req.get('regions',[])
        if not isinstance(regions,list) or not 1 <= len(regions) <= 150:
            raise RuntimeError('Некорректное количество регионов.')
        if bool(original.muted):
            raise RuntimeError('Клип уже заглушён — пропускаю.')
        reference=float(source['file_offset'])
        last_file=reference
        last_beat=float(source['start'])
        for region in regions:
            a,b=float(region['file_start']),float(region['file_end'])
            st,ed=float(region['time']),float(region['end'])
            if (abs(a-last_file)>.00008 or b<=a or ed<=st
                    or abs(st-last_beat)>.0001 or st < -0.0001):
                raise RuntimeError('Границы регионов содержат разрыв или наложение.')
            expected= float(source['start'])+(a-reference)*float(req['tempo'])/60
            if abs(st-expected)>.002 or abs(ed-st-(b-a)*float(req['tempo'])/60)>.002:
                raise RuntimeError('Несовпадение времени между оригиналом и регионами.')
            last_file,last_beat=b,ed
        if abs(last_file-float(source['file_end']))>.00008 or abs(last_beat-float(source['end']))>.003:
            raise RuntimeError('Регионы не покрывают весь исходный клип.')
        if len(regions)==1 and not bool(regions[0]['muted']):
            return {'ok':True,'created':0,'muted':0,'unchanged':True}

        # Only full-source clips are used. No trimmed/new WAV file is generated.
        # If no sound survived the threshold, simply deactivate the same clip.
        if len(regions)==1 and bool(regions[0]['muted']):
            song.begin_undo_step()
            try:
                original.muted=True
            finally:
                song.end_undo_step()
            return {'ok':True,'created':1,'muted':1}

        slot=None
        for candidate in track.clip_slots:
            if not bool(candidate.has_clip) and callable(getattr(candidate,'create_audio_clip',None)):
                slot=candidate
                break
        if slot is None:
            raise RuntimeError('Нужен хотя бы один пустой слот Session View на этой дорожке.')

        source_path=str(source['file_path'])
        if not os.path.isfile(source_path):
            raise RuntimeError('Исходный WAV недоступен: '+source_path)
        song.begin_undo_step()
        error=None
        did_change=False
        count=0
        muted_count=0
        try:
            slot.create_audio_clip(source_path)
            session=slot.clip
            session.warping=False
            session.looping=False
            # Ensure the source remains full length and can later be revealed
            # by dragging clip boundaries. Never call crop()/write_slice().
            if str(session.file_path)!=source_path:
                raise RuntimeError('Session clip references the wrong source WAV.')
            # Probe marker support before touching the Arrangement source.
            # Live may expose the setters but reject / clamp a narrow range.
            first = regions[0]
            a0, b0 = float(first['file_start']), float(first['file_end'])
            session.loop_end = b0
            session.loop_start = a0
            session.end_marker = b0
            session.start_marker = a0
            for name, expected in (('loop_start', a0), ('loop_end', b0),
                                   ('start_marker', a0), ('end_marker', b0)):
                if abs(float(getattr(session, name)) - expected) > .002:
                    raise RuntimeError('Live не принял маркер %s ещё до изменения клипа.' % name)

            track.delete_clip(original)
            did_change=True
            for region in regions:
                a,b=float(region['file_start']),float(region['file_end'])
                st,ed=float(region['time']),float(region['end'])
                # With Loop OFF, Live's Session->Arrangement duplicator uses
                # the content start/end markers to determine Arrangement length.
                # Changing only loop_start/loop_end can leave the *full sample*
                # length, so the resulting region extends into the next one.
                # Set the end first, then the start, for both pairs of markers.
                session.loop_end = b
                session.loop_start = a
                session.end_marker = b
                session.start_marker = a
                for name, expected in (
                        ('loop_start', a), ('loop_end', b),
                        ('start_marker', a), ('end_marker', b)):
                    actual = float(getattr(session, name))
                    if abs(actual - expected) > .002:
                        raise RuntimeError(
                            'Live не установил %s: %.5f вместо %.5f. '
                            'Исходный клип будет восстановлен.' %
                            (name, actual, expected))
                session.muted=bool(region['muted'])
                track.duplicate_clip_to_arrangement(session,st)
                found=[]
                for c in list(track.arrangement_clips):
                    try:
                        if (c.is_audio_clip and str(c.file_path)==source_path
                            and abs(float(c.start_time)-st)<.003):
                            found.append(c)
                    except Exception:
                        pass
                if len(found)!=1:
                    raise RuntimeError('Live не создал однозначный регион: %.4f' % st)
                new=found[0]
                if abs(float(new.end_time)-ed)>.02:
                    raise RuntimeError(
                        'Нарушена длительность региона: %.4f vs %.4f; '
                        'Session: start_marker=%.5f, end_marker=%.5f, '
                        'loop_start=%.5f, loop_end=%.5f' %
                        (float(new.end_time), ed, float(session.start_marker),
                         float(session.end_marker), float(session.loop_start),
                         float(session.loop_end)))
                if new.warping:
                    raise RuntimeError('Live автоматически включил Warp; остановлено.')
                for name, expected in (('loop_start', a), ('loop_end', b),
                                       ('start_marker', a), ('end_marker', b)):
                    try:
                        actual = float(getattr(new, name))
                    except Exception:
                        raise RuntimeError('Не удаётся проверить %s у созданного клипа.' % name)
                    if abs(actual - expected) > .005:
                        raise RuntimeError(
                            'Созданный клип ссылается на неверный участок WAV: '
                            '%s=%.5f вместо %.5f' % (name, actual, expected))
                new.muted=bool(region['muted'])
                new.name=str(source['name'])[:120]
                new.gain=float(source['gain'])
                try:
                    new.color=int(source['color'])
                except Exception:
                    pass
                count+=1
                if new.muted:
                    muted_count+=1
            # Temporary Session clip is removed; no new scene or track added.
            slot.delete_clip()
        except Exception as exc:
            error=exc
            try:
                if slot.has_clip:
                    slot.delete_clip()
            except Exception:
                pass
        finally:
            try:
                song.end_undo_step()
            except Exception as exc:
                error=error or exc
        if error is not None:
            try:
                song.undo()
            except Exception as undo_error:
                raise RuntimeError('Ошибка нарезки: %s; откат тоже не удался: %s. Не сохраняй проект.' %
                                   (error,undo_error))
            raise RuntimeError('Live откатил изменения текущего клипа: %s' % error)
        return {'ok':True,'created':count,'muted':muted_count,
                'track_name':str(track.name),'clip_name':source['name']}

    def _replace(self, song, req):
        """A single clip replacement on its EXISTING track; one undo unit per clip.

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
        # Fully silent clips are deleted only when explicitly authorised
        # by the UI's confirmation flow.
        if not items and not bool(req.get('allow_empty', False)):
            raise ValueError('Refusing to delete all-silent clip without explicit permission')
        song.begin_undo_step()
        n = 0
        error = None
        did_change = False
        try:
            track.delete_clip(clip)
            did_change = True
            # Check deletion before inserting at identical positions.
            if len(track.arrangement_clips) >= int(req['before_count']):
                raise RuntimeError('Original clip was not removed; aborting')
            for item in items:
                new_clip = track.create_audio_clip(str(item['path']), float(item['time']))
                if new_clip is None:
                    raise RuntimeError('Live returned no clip after create_audio_clip')
                new_clip.warping = False
                new_clip.looping = False
                new_clip.name = str(source['name'])[:120]
                new_clip.gain = float(source['gain'])
                new_clip.muted = bool(source['muted'])
                try:
                    new_clip.color = int(source['color'])
                except Exception:
                    pass
                n += 1
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
            if did_change or len(track.arrangement_clips) != int(req['before_count']):
                try:
                    song.undo()
                except Exception as rollback_error:
                    raise RuntimeError('REPLACEMENT FAILED: %s. ALSO UNDO FAILED: %s. Stop and inspect the project; original WAV is intact.' % (error, rollback_error))
                raise RuntimeError('Replacement failed and Live undo was invoked: %s. Inspect this track before continuing.' % error)
            raise RuntimeError('Replacement refused before modification: %s' % error)
        return {'ok': True, 'created': n, 'removed': 1,
                'track_name': str(track.name), 'clip_name': source['name']}
