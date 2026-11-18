"""Local Clear Silence preview application: no pip dependencies, no cloud."""
import html
import json
import os
import secrets
import socket
import sys
import threading
import time
import uuid
import logging
from logging.handlers import RotatingFileHandler
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from audio import WavFile
from silence_math import settings_for_strength, regions_with_muted_gaps

BRIDGE_PORT = 47861
WEB_PORT = 47862
TOKEN_FILE = os.path.expanduser('~/Library/Application Support/ClearSilence/bridge_token')
PREVIEW_ROOT = os.path.expanduser('~/Music/ClearSilence Preview')
OUTPUT_ROOT = os.path.expanduser('~/Music/ClearSilence Output')
SESSION_TOKEN = secrets.token_urlsafe(32)
APP_VERSION = '0.6.2'
plans = {}
batch_plans = {}
jobs = {}
lock = threading.Lock()


def bridge(action, **args):
    if not os.path.isfile(TOKEN_FILE):
        raise RuntimeError('Remote Script not running. Install ClearSilenceBridge and select it as Control Surface in Ableton, then restart Live.')
    with open(TOKEN_FILE, 'r') as f:
        token = f.read().strip()
    req = {'token': token, 'action': action, **args}
    try:
        with socket.create_connection(('127.0.0.1', BRIDGE_PORT), timeout=3) as conn:
            conn.settimeout(30)
            conn.sendall((json.dumps(req, ensure_ascii=False) + '\n').encode('utf-8'))
            out = bytearray()
            while not out.endswith(b'\n') and len(out) < 1000000:
                data = conn.recv(65536)
                if not data:
                    break
                out.extend(data)
    except OSError as e:
        raise RuntimeError('Cannot connect to Live bridge (127.0.0.1:%d): %s' % (BRIDGE_PORT, e)) from e
    if not out:
        raise RuntimeError('Live returned no response')
    result = json.loads(out)
    if not result.get('ok'):
        raise RuntimeError(result.get('error', 'Unknown Live error'))
    return result


def require_replace_bridge():
    """Fail BEFORE creating files or editing Live when the installed script is old."""
    status = bridge('status')
    if status.get('protocol') != 11 or 'auto_begin' not in status.get('actions', []):
        raise RuntimeError('В Ableton запущен старый ClearSilenceBridge. Установи новую версию Clear Silence и полностью перезапусти Ableton. Текущий мост: %s, нужен v0.6.2.' % status.get('version', 'неизвестен'))
    if not status.get('can_replace', False):
        raise RuntimeError('Live не предоставил безопасные операции Undo. Разделение клипов отключено.')
    return status


def get_clip(data, ti, ci):
    for tr in data['tracks']:
        if tr['index'] == ti:
            for clip in tr['clips']:
                if clip['index'] == ci:
                    return clip
    raise ValueError('Clip is missing. Refresh clip list.')


def analyze(req):
    ti = int(req['track_index']); ci = int(req['clip_index'])
    threshold = float(req.get('threshold', -45))
    min_ms = int(req.get('min_silence_ms', 150))
    padding = int(req.get('padding_ms', 30))
    snapshot = bridge('list')
    clip = get_clip(snapshot, ti, ci)
    if 'error' in clip:
        raise ValueError('Unable to read selected clip: ' + clip['error'])
    if clip['warping'] or clip['looping']:
        raise ValueError('Prototype: disable Warp and Loop on a test clip')
    if clip['has_envelopes'] or clip['pitch_coarse'] or clip['pitch_fine']:
        raise ValueError('Prototype: use a test clip without envelopes/pitch changes')
    if not os.path.isfile(clip['file_path']):
        raise ValueError('Audio file not found: ' + clip['file_path'])
    tempo = float(snapshot['tempo'])
    if tempo <= 0:
        raise ValueError('Invalid Live tempo')
    wav = WavFile(clip['file_path'])
    file_offset = clip['file_offset']
    duration = (clip['end'] - clip['start']) * 60 / tempo
    # Unwarped audio uses seconds; reject any implicit discrepancy rather than shifting notes.
    reported_duration = clip['file_end'] - clip['file_offset']
    if abs(reported_duration - duration) > 0.09:
        raise ValueError('Arrangement duration does not match sample length. Tempo automation or unusual clip trimming may be present; not safe for v0.1. (%.3f vs %.3f sec)' % (duration, reported_duration))
    segments = wav.detect(file_offset, duration, threshold, min_ms, padding)
    if len(segments) > 60:
        raise ValueError('Found %d fragments. v0.1 caps preview at 60; increase Min Silence.' % len(segments))
    plan_id = uuid.uuid4().hex
    plan = {'snapshot': clip, 'tempo': tempo, 'track_index': ti, 'clip_index': ci, 'segments': segments,
            'wav_path': clip['file_path'], 'file_offset': file_offset, 'rate': wav.rate,
            'created': time.time()}
    with lock:
        plans.clear()
        plans[plan_id] = plan
    return {'ok': True, 'plan_id': plan_id, 'segments': len(segments),
            'total_audio_sec': round(sum((b-a)/wav.rate for a,b in segments), 2),
            'source_sec': round(duration, 2),
            'positions': [round((a/wav.rate-file_offset), 3) for a,b in segments[:12]],
            'format': '%s Hz, %s channels, %s-bit %s' % (wav.rate, wav.channels, wav.bits, 'float' if wav.tag == 3 else 'PCM')}


def visualize_clip(req):
    """Read-only, exact kept/removed ranges plus approximate overview waveform."""
    ti = int(req['track_index']); ci = int(req['clip_index'])
    threshold = float(req.get('threshold', -45))
    min_ms = int(req.get('min_silence_ms', 150))
    padding = int(req.get('padding_ms', 30))
    if not (-90 <= threshold <= -1 and 30 <= min_ms <= 5000 and 0 <= padding <= 1000):
        raise ValueError('Параметры вне допустимого диапазона')
    listing = bridge('list')
    clip = get_clip(listing, ti, ci)
    if 'error' in clip:
        raise ValueError(clip['error'])
    if clip['warping'] or clip['looping']:
        raise ValueError('Предпросмотр пока доступен только для клипов без Warp и Loop')
    if clip['has_envelopes'] or clip.get('has_groove') or clip['pitch_coarse'] or clip['pitch_fine']:
        raise ValueError('В клипе есть автоматизация, Groove или транспонирование')
    tempo = float(listing['tempo'])
    duration = (clip['end'] - clip['start']) * 60 / tempo
    if duration <= 0 or abs((clip['file_end'] - clip['file_offset']) - duration) > .09:
        raise ValueError('Нестандартная длительность или смещение клипа; предпросмотр недоступен')
    wav = WavFile(clip['file_path'])
    segments = wav.detect(clip['file_offset'], duration, threshold, min_ms, padding)
    active = []
    for a,b in segments:
        active.append([round(max(0., a / wav.rate - clip['file_offset']), 5),
                       round(min(duration, b / wav.rate - clip['file_offset']), 5)])
    kept = sum(b-a for a,b in segments) / wav.rate
    return {'ok': True, 'track': clip['name'], 'duration': round(duration, 5),
            'waveform': wav.envelope(clip['file_offset'], duration, 550),
            'kept_ranges': active, 'kept_seconds': round(kept, 3),
            'removed_seconds': round(max(0, duration-kept), 3),
            'fragments': len(active)}


def create_preview(req):
    pid = req.get('plan_id')
    with lock:
        plan = plans.pop(pid, None)
    if plan is None or time.time() - plan['created'] > 3600:
        raise ValueError('Preview has expired. Analyze again.')
    if not plan['segments']:
        raise ValueError('No audio above threshold. Preview not created.')
    wav = WavFile(plan['wav_path'])
    out_dir = os.path.join(PREVIEW_ROOT, time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4))
    os.makedirs(out_dir, exist_ok=False)
    fragments = []
    for i, (a, b) in enumerate(plan['segments']):
        path = os.path.join(out_dir, 'fragment_%03d.wav' % (i + 1))
        wav.write_slice(a, b, path)
        beat_start = plan['snapshot']['start'] + ((a / wav.rate) - plan['file_offset']) * plan['tempo'] / 60
        beat_end = beat_start + (b-a) / wav.rate * plan['tempo'] / 60
        fragments.append({'path': path, 'time': beat_start, 'end': beat_end})
    try:
        result = bridge('preview', track_index=plan['track_index'], clip_index=plan['clip_index'],
                        source=plan['snapshot'], tempo=plan['tempo'], fragments=fragments)
    except Exception as e:
        raise RuntimeError('%s. Generated WAVs remain at %s' % (e, out_dir)) from e
    result['folder'] = out_dir
    return result



def _settings(req):
    if 'strength' in req:
        return settings_for_strength(req['strength'])
    return {'threshold': float(req.get('threshold', -45)),
            'min_silence_ms': int(req.get('min_silence_ms', 150)),
            'padding_ms': int(req.get('padding_ms', 30))}


def clip_profile(req):
    """One high-resolution peak read; changes to the single knob are local in JS."""
    ti, ci = int(req['track_index']), int(req['clip_index'])
    listing = bridge('list')
    clip = get_clip(listing, ti, ci)
    if 'error' in clip or clip['warping'] or clip['looping'] or clip['has_envelopes']:
        raise ValueError('Этот клип не поддерживает предпросмотр (Warp, Loop или автоматизация).')
    tempo = float(listing['tempo'])
    duration = (clip['end'] - clip['start']) * 60 / tempo
    if duration <= 0 or abs((clip['file_end'] - clip['file_offset']) - duration) > .09:
        raise ValueError('Клип имеет нестандартную длительность или смещение.')
    wav = WavFile(clip['file_path'])
    peaks, hop, first, end = wav.peak_windows(clip['file_offset'], duration)
    return {'ok': True, 'duration': duration, 'peaks': peaks, 'hop': hop,
            'rate': wav.rate, 'first_frame': first, 'end_frame': end,
            'waveform': wav.envelope(clip['file_offset'], duration, 550),
            'muted': bool(clip['muted'])}


def plan_batch(req):
    """Read-only inspection and sample analysis; never changes Live or its WAVs."""
    tis = req.get('track_indices', [])
    if not isinstance(tis, list) or len(tis) > 120:
        raise ValueError('Выбери не больше 120 аудиодорожек.')
    indices = sorted(set(int(x) for x in tis))
    opts = _settings(req)
    threshold, minimum, padding = opts['threshold'], opts['min_silence_ms'], opts['padding_ms']
    if not (-90 <= threshold <= -1 and 30 <= minimum <= 5000 and 0 <= padding <= 1000):
        raise ValueError('Invalid threshold / silence / padding')
    snapshot = bridge('list')
    if not indices:
        chosen = snapshot.get('selected_track_index')
        if chosen is None or not any(t['index'] == chosen for t in snapshot['tracks']):
            raise ValueError('Не выбрана аудиодорожка с клипами.')
        indices = [chosen]
    tempo = float(snapshot['tempo'])
    if tempo <= 0:
        raise ValueError('Invalid Live tempo')
    selected = {tr['index']: tr for tr in snapshot['tracks'] if tr['index'] in indices}
    if not selected:
        raise ValueError('Selected tracks have no audio clips')
    entries, skipped, unchanged = [], [], []
    if sum(len(t['clips']) for t in selected.values()) > 150:
        raise ValueError('Max 150 audio clips per batch. Select fewer tracks.')
    for ti, track in selected.items():
        for clip in track['clips']:
            label = track['name'] + ' / ' + clip.get('name', '?')
            try:
                if 'error' in clip:
                    raise ValueError(clip['error'])
                if bool(clip.get('muted', False)):
                    unchanged.append(label)
                    continue
                if clip['warping'] or clip['looping']:
                    raise ValueError('Warp or Loop enabled')
                if clip['has_envelopes'] or clip.get('has_groove') or clip['pitch_coarse'] or clip['pitch_fine']:
                    raise ValueError('Clip automation/groove/pitch enabled')
                if not os.path.isfile(clip['file_path']):
                    raise ValueError('Source WAV not available')
                wav = WavFile(clip['file_path'])
                duration = (clip['end'] - clip['start']) * 60 / tempo
                if duration <= 0:
                    raise ValueError('Invalid clip duration')
                if abs((clip['file_end'] - clip['file_offset']) - duration) > 0.09:
                    raise ValueError('Clip duration differs from file range (tempo automation/trim)')
                segments = wav.detect(clip['file_offset'], duration, threshold, minimum, padding)
                if len(segments) > 150:
                    raise ValueError('Over 150 fragments; increase Min Silence')
                # All-silent clips become muted, not deleted; the audio remains restorable.
                full_start = round(clip['file_offset'] * wav.rate)
                full_end = round((clip['file_offset'] + duration) * wav.rate)
                if len(segments) == 1 and segments[0][0] <= full_start + wav.rate * .015 and segments[0][1] >= full_end - wav.rate * .015:
                    unchanged.append(label)
                    continue
                entries.append({'track_index':ti, 'track_name':track['name'], 'source':clip,
                                'segments':segments, 'tempo':tempo,
                                'file_path':clip['file_path'], 'rate':wav.rate,
                                'duration':duration, 'label':label})
            except (ValueError, OSError) as ex:
                skipped.append({'name':label, 'reason':str(ex)})
    if len(entries) > 150:
        raise ValueError('Batch too large')
    total_silence = sum(1 for e in entries if not e['segments'])
    total_fragments = sum(len(e['segments']) for e in entries)
    pid = uuid.uuid4().hex
    with lock:
        batch_plans.clear()
        batch_plans[pid] = {'created':time.time(), 'entries':entries, 'tempo':tempo,
                            'allow_empty':True}
    return {'ok': True, 'plan_id':pid,
            'replace_clips':len(entries), 'fragments':total_fragments,
            'silent_clips':total_silence,
            'skipped':skipped[:60], 'skipped_count':len(skipped),
            'unchanged_count':len(unchanged),
            'examples':[{'name':e['label'], 'fragments':len(e['segments'])} for e in entries[:25]]}


def _mute_worker(job_id, plan):
    """Retain full source files and mute gaps, one Undo group per source clip."""
    def set_job(**items):
        with lock:
            jobs[job_id].update(items)
    completed = 0
    try:
        require_replace_bridge()
        for i, e in enumerate(plan['entries']):
            with lock:
                canceled = jobs[job_id].get('cancel', False)
            if canceled:
                set_job(state='canceled', message='Остановлено после %d клипов.' % completed)
                return
            set_job(current=i+1, message='Разделяю: '+e['label'])
            wav = WavFile(e['file_path'])
            origin = e['source']
            first = round(origin['file_offset']*wav.rate)
            end = round((origin['file_offset']+e['duration'])*wav.rate)
            if end > wav.frames and end - wav.frames <= 2:
                end = wav.frames
            regions = regions_with_muted_gaps(e['segments'], first, end,
                                               min_region_frames=round(wav.rate*.012))
            if len(regions) > 150:
                raise RuntimeError('Слишком много границ (%d) на одном клипе; уменьшай жёсткость.' % len(regions))
            payload = []
            for a,b,is_muted in regions:
                st = origin['start'] + ((a/wav.rate)-origin['file_offset'])*e['tempo']/60
                ed = origin['start'] + ((b/wav.rate)-origin['file_offset'])*e['tempo']/60
                payload.append({'file_start': a/wav.rate, 'file_end': b/wav.rate,
                                'time': st, 'end': ed, 'muted': bool(is_muted)})
            response = bridge('split_mute', track_index=e['track_index'],
                              track_name=e['track_name'], source=origin,
                              tempo=e['tempo'], regions=payload)
            completed += 1
            set_job(completed=completed,
                    message='Готово: %s · %d регионов, %d заглушено' %
                    (e['label'], response['created'], response['muted']))
        set_job(state='done', message='Готово. %d клипов разделено; исходные WAV не тронуты.' % completed)
    except Exception as exc:
        set_job(state='error', errors=[str(exc)], message=('Остановлено после %d клипов. %s' % (completed,exc)))


def _batch_worker(job_id, plan):
    entries=plan['entries']
    def set_job(**kw):
        with lock:
            jobs[job_id].update(kw)
    completed=0
    errors=[]
    output_dir=os.path.join(OUTPUT_ROOT, time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4))
    try:
        require_replace_bridge()
        os.makedirs(output_dir, exist_ok=False)
        for k, e in enumerate(entries):
            with lock:
                canceled=jobs[job_id].get('cancel',False)
            if canceled:
                set_job(state='canceled',message='Остановлено после %d клипов. Уже заменённые клипы не отменены.' % completed)
                return
            set_job(current=k+1, message='Обрабатывается: '+e['label'])
            wav=WavFile(e['file_path'])
            folder=os.path.join(output_dir, 'track_%03d_clip_%03d' % (e['track_index'],k))
            os.makedirs(folder, exist_ok=False)
            frags=[]
            for n,(a,b) in enumerate(e['segments']):
                path=os.path.join(folder, 'part_%04d.wav' % (n+1))
                wav.write_slice(a,b,path)
                beat_start=e['source']['start'] + ((a / wav.rate)-e['source']['file_offset']) * e['tempo']/60
                beat_end=beat_start + (b-a)/wav.rate * e['tempo']/60
                frags.append({'path':path,'time':beat_start,'end':beat_end})
            # Give Live a chance to verify source identity after prior edits on same track.
            listing=bridge('list')
            track=next((t for t in listing['tracks'] if t['index']==e['track_index']),None)
            if track is None:
                raise RuntimeError('Track moved or no longer exists: '+e['track_name'])
            result=bridge('replace', track_index=e['track_index'], track_name=e['track_name'],
                          source=e['source'], tempo=e['tempo'], before_count=len(track['clips']),
                          fragments=frags,allow_empty=plan['allow_empty'])
            completed+=1
            set_job(completed=completed, message='Готово: '+e['label']+' (%d фрагментов)' % result['created'])
        set_job(state='done', message='Готово. Заменено %d клипов, исходные WAV сохранены.' % completed)
    except Exception as exc:
        errors.append(str(exc))
        set_job(state='error', message=('Ошибка после %d успешных замен. Следующие клипы не обрабатывались. '
                                        'Проверь последнюю дорожку. %s' % (completed,exc)), errors=errors)
    finally:
        set_job(output_dir=output_dir)


def _auto_native_worker(job_id, plan):
    """Native Arrangement splitting by analyzed WAV silence; no WAV writes."""
    import native_automation

    def update(**kw):
        with lock:
            jobs[job_id].update(kw)

    logger=logging.getLogger('ClearSilence.automation')
    if not logger.handlers:
        try:
            folder=os.path.expanduser('~/Library/Logs/ClearSilence')
            os.makedirs(folder,exist_ok=True)
            handler=RotatingFileHandler(os.path.join(folder,'automation.log'),
                                        maxBytes=1000000,backupCount=2,encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        except OSError:
            logger.addHandler(logging.NullHandler())
    logger.info('job=%s app=%s clips=%d',job_id,APP_VERSION,len(plan['entries']))
    done = 0
    entries = plan['entries']
    try:
        require_replace_bridge()
        for i,e in enumerate(entries):
            with lock:
                canceled = jobs[job_id]['cancel']
            if canceled:
                update(state='canceled',
                       message='Остановлено после %d клипов.' % done)
                return
            wav=WavFile(e['file_path'])
            origin=e['source']
            first=round(origin['file_offset']*wav.rate)
            last=round((origin['file_offset']+e['duration'])*wav.rate)
            if last > wav.frames and last-wav.frames <= 2:
                last=wav.frames
            regions=regions_with_muted_gaps(e['segments'],first,last,
                       min_region_frames=round(wav.rate*.04))
            if len(regions)>120:
                raise RuntimeError('Более 120 фрагментов. Уменьши чувствительность.')
            ranges=[]
            for x,y,muted in regions:
                st=origin['start']+(x/wav.rate-origin['file_offset'])*e['tempo']/60
                ed=origin['start']+(y/wav.rate-origin['file_offset'])*e['tempo']/60
                ranges.append({'start':st,'end':ed,'muted':muted})
            update(current=i+1,message='Обрабатываю: %s · %d регионов' %
                    (e['label'],len(ranges)))
            bridge('auto_begin',track_index=e['track_index'],
                   track_name=e['track_name'],source=origin,regions=ranges,
                   tempo=e['tempo'],rate=wav.rate)
            try:
                for cut in range(max(0,len(ranges)-1)):
                    with lock:
                        canceled = jobs[job_id]['cancel']
                    if canceled:
                        raise RuntimeError('Отменено после %d разрезов.' % cut)
                    arm=bridge('auto_arm')
                    confirmed=None
                    for retry in range(12):
                        time.sleep(.14)
                        confirmed=bridge('auto_confirm')
                        if confirmed['confirmed']:
                            break
                    if not confirmed or not confirmed['confirmed']:
                        raise RuntimeError(
                            'Playhead не достиг позиции %.5f (фактически %.5f).' %
                            (arm['target_beat'],
                             confirmed['observed_beat'] if confirmed else -1))
                    try:
                        prepared=native_automation.prepare_native_split()
                    except native_automation.SplitUnavailable:
                        # Focus is not a lane selection. A fresh disabled menu
                        # permits ONE non-editing recovery, never a Split retry.
                        lane=bridge('auto_lane')
                        selected=native_automation.select_native_lane(lane['track_name'])
                        logger.info('clip=%d cut=%d selection=%s',i+1,cut+1,selected)
                        bridge('auto_reposition')
                        for retry in range(12):
                            time.sleep(.14)
                            position=bridge('auto_confirm',position_only=True)
                            if position['confirmed']:
                                break
                        if not position['confirmed']:
                            raise RuntimeError('Не удалось восстановить точную позицию после выбора дорожки.')
                        # Keep the actual clicked lane active. Option+2 or a
                        # detail_clip assignment would replace this selection.
                        prepared=native_automation.prepare_native_split(selected=selected)
                    logger.info('clip=%d cut=%d target=%.9f prepared=%s',
                                i+1,cut+1,arm['target_beat'],prepared)
                    # Focus/navigation can change selection or transport. Check
                    # again AFTER placing the insert marker, before any edit.
                    ready=bridge('auto_confirm')
                    if not ready['confirmed']:
                        raise RuntimeError('Позиция Live изменилась при выборе клипа; Split не отправлен.')
                    with lock:
                        canceled=jobs[job_id]['cancel']
                    if canceled:
                        raise RuntimeError('Обработка отменена перед разрезом.')
                    native_automation.send_native_split(prepared=prepared)
                    verified=None
                    for retry in range(12):
                        time.sleep(.16)
                        verified=bridge('auto_verify')
                        if verified['verified']:
                            break
                    if not verified or not verified['verified']:
                        raise RuntimeError(
                            'Ableton не разделил клип: разрез %d/%d, '
                            'позиция %.5f, найдено фрагментов %s. '
                            'Live не подтвердил Split после выбора Arrangement.' %
                            (cut+1,len(ranges)-1,arm['target_beat'],
                             verified['count'] if verified else 'неизвестно'))
                    logger.info('clip=%d cut=%d verified=%s',i+1,cut+1,verified)
                    update(message='%s · разрез %d/%d'%
                           (e['label'],cut+1,len(ranges)-1))
                result=bridge('auto_finish')
                done+=1
                update(completed=done,message='%s · %d регионов, %d заглушено' %
                       (e['label'],result['created'],result['muted']))
            finally:
                try:
                    bridge('auto_abort')
                except Exception:
                    pass
        update(state='done',message='Готово: %d клипов. WAV не изменены.' % done)
    except Exception as exc:
        logger.exception('job=%s stopped after %d clips',job_id,done)
        update(state='error',errors=[str(exc)],
               message='Остановлено на клипе %d/%d. %s' %
                       (done+1,len(entries),exc))


def start_batch(req):
    require_replace_bridge()
    pid=req.get('plan_id')
    with lock:
        if any(j['state']=='running' for j in jobs.values()):
            raise RuntimeError('Обработка уже выполняется.')
        plan=batch_plans.pop(pid,None)
    if plan is None or time.time()-plan['created']>3600:
        raise ValueError('Анализ устарел. Попробуй ещё раз.')
    if not plan['entries']:
        return {'ok':True,'done':True,
                'message':'Нет тишины, которую нужно заглушать.'}
    job_id=uuid.uuid4().hex
    with lock:
        jobs[job_id]={'state':'running','current':0,'total':len(plan['entries']),
                      'completed':0,'message':'Начинаю автоматическую нарезку…',
                      'errors':[],'cancel':False}
    threading.Thread(target=_auto_native_worker,args=(job_id,plan),
                     daemon=True).start()
    return {'ok':True,'job_id':job_id}


def get_job(job_id):
    with lock:
        if job_id not in jobs:
            raise ValueError('Job not found')
        return {'ok':True,**{k:v for k,v in jobs[job_id].items() if k != 'cancel'}}


def cancel_job(job_id):
    with lock:
        if job_id not in jobs:
            raise ValueError('Job not found')
        jobs[job_id]['cancel']=True
    return {'ok':True,'message':'Will stop after the current clip'}


HTML = open(os.path.join(os.path.dirname(__file__), 'ui.html'), encoding='utf-8').read()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write('[ClearSilence] ' + fmt % args + '\n')

    def answer(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            body = HTML.replace('__CSRF__', SESSION_TOKEN).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == '/api/batch/status':
            try:
                from urllib.parse import parse_qs
                job_id=parse_qs(urlparse(self.path).query).get('id',[''])[0]
                self.answer(200,get_job(job_id))
            except Exception as e:
                self.answer(400,{'ok':False,'error':str(e)})
        elif path in ('/api/status', '/api/list'):
            try:
                self.answer(200, bridge('status' if path.endswith('status') else 'list'))
            except Exception as e:
                self.answer(500, {'ok': False, 'error': str(e)})
        else:
            self.answer(404, {'ok': False, 'error': 'Not found'})

    def do_POST(self):
        origin = self.headers.get('Origin', '')
        if (origin and origin != 'http://127.0.0.1:%d' % WEB_PORT) or self.headers.get('X-ClearSilence-Token') != SESSION_TOKEN:
            return self.answer(403, {'ok': False, 'error': 'Unauthorized request'})
        try:
            n = int(self.headers.get('Content-Length','0'))
            if n <= 0 or n > 10000:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(n))
            if self.path == '/api/clip/profile':
                result = clip_profile(data)
            elif self.path == '/api/native/prepare':
                result = bridge('native_prepare', track_index=int(data['track_index']), clip_index=int(data['clip_index']))
            elif self.path == '/api/native/auto':
                # Never target source clips: bridge arms its tagged test track
                # and exact beat before the macOS shortcut is dispatched.
                armed = bridge('native_arm')
                # A same-tick read of song.current_song_time can be stale.
                # Wait for separate Live callbacks before dispatching keys.
                last = None
                for _ in range(8):
                    time.sleep(0.18)
                    last = bridge('native_confirm')
                    if last['confirmed']:
                        break
                if not last or not last['confirmed']:
                    raise RuntimeError(
                        'Live не подтвердил playhead: нужно %.5f доли, '
                        'фактически %.5f. Cmd+E не отправлена.' % (
                            armed['target_beat'],
                            last['observed_beat'] if last else -1))
                import native_automation
                sent = native_automation.send_native_split()
                result = bridge('native_verify')
                result['armed_beat'] = armed['target_beat']
                result['shortcuts_sent'] = sent['sent']
            elif self.path == '/api/native/verify':
                result = bridge('native_verify')
            elif self.path == '/api/native/cleanup':
                result = bridge('native_cleanup')
            elif self.path == '/api/region/probe':
                result = bridge('probe_region', track_index=int(data['track_index']), clip_index=int(data['clip_index']))
            elif self.path == '/api/clip/visualize':
                result = visualize_clip(data)
            elif self.path == '/api/batch/analyze':
                result = plan_batch(data)
            elif self.path == '/api/batch/start':
                result = start_batch(data)
            elif self.path == '/api/batch/cancel':
                result = cancel_job(data.get('job_id'))
            elif self.path == '/api/shutdown':
                with lock:
                    busy=any(j['state']=='running' for j in jobs.values())
                if busy:
                    raise ValueError('Wait until processing completes or cancel after current clip')
                result = {'ok':True,'message':'Clear Silence closed'}
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif self.path == '/api/analyze':
                result = analyze(data)
            elif self.path == '/api/apply':
                result = create_preview(data)
            else:
                return self.answer(404, {'ok': False, 'error': 'Unknown action'})
            self.answer(200, result)
        except Exception as e:
            self.answer(400, {'ok': False, 'error': str(e)})


if __name__ == '__main__':
    # The window is deliberately NOT a regular browser tab. Cocoa/WebKit is
    # hosted in its own macOS application window via pywebview.
    if sys.platform != 'darwin':
        raise SystemExit('This packaged application currently supports macOS only.')
    try:
        import webview
    except ImportError as e:
        raise SystemExit('Нужен pywebview для отдельного окна. Один раз запусти 03_SETUP_UI.command из папки Clear Silence. (%s)' % e)
    try:
        httpd = ThreadingHTTPServer(('127.0.0.1', WEB_PORT), Handler)
    except OSError as e:
        raise SystemExit('Не удалось открыть интерфейс на порту %d: %s. Закрой прежнюю версию Clear Silence.' % (WEB_PORT, e))

    class NativeWindowApi:
        def close(self):
            # Called from pywebview JS bridge; never block the UI thread.
            threading.Thread(target=window.destroy, daemon=True).start()
            return True

    t = threading.Thread(target=httpd.serve_forever, daemon=True, name='ClearSilenceUI')
    t.start()
    try:
        window = webview.create_window('Clear Silence', 'http://127.0.0.1:%d' % WEB_PORT,
                                       width=485, height=630, min_size=(420, 530),
                                       js_api=NativeWindowApi())
        webview.start(gui='cocoa', debug=False)
    finally:
        httpd.shutdown()
        httpd.server_close()
