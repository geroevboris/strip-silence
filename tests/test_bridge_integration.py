"""Live API doubles: verify replacement, backup ordering and rollback.

These tests do not claim to run Ableton Live; macOS CI builds the actual app.
"""
import copy
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import types
import unittest
import wave
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
frame=types.ModuleType('_Framework'); surf=types.ModuleType('_Framework.ControlSurface')
class ControlSurface:
    def __init__(self,c): self._song=c
    def song(self): return self._song
    def log_message(self,*args): pass
    def update_display(self): pass
    def disconnect(self): pass
surf.ControlSurface=ControlSurface
sys.modules['_Framework']=frame; sys.modules['_Framework.ControlSurface']=surf
from ClearSilenceBridge import ClearSilenceBridge
import ClearSilenceBridge as bridge_module
import app

class Clip:
    is_audio_clip=True; warping=False; looping=False; gain=.7; has_envelopes=False
    pitch_coarse=0; pitch_fine=0; muted=False; color=0xcc8844; has_groove=False
    def __init__(self,path,st=16.,ed=20.,offset=0.):
        self.file_path=path; self.name='Voice'; self.start_time=st; self.end_time=ed
        self.loop_start=offset; self.loop_end=offset+(ed-st)/2

class Lane:
    return_none=False; wrong_length=False; fail_create=False
    def __init__(self): self.name='Take'; self.arrangement_clips=[]
    def create_audio_clip(self,path,beat):
        if self.fail_create: raise RuntimeError('Simulated file import failure')
        with wave.open(path,'rb') as f: duration=f.getnframes()/f.getframerate()
        c=Clip(path,beat,beat+duration*2)
        if self.wrong_length: c.end_time+=.5
        self.arrangement_clips.append(c)
        return None if self.return_none else c

class Track(Lane):
    has_audio_input=True; is_frozen=False
    def __init__(self,clips):
        super().__init__(); self.name='Voice'; self.arrangement_clips=clips; self.take_lanes=[]
        self.mute=False; self.delete_calls=0; self.lane_factory=Lane
    def create_take_lane(self): self.take_lanes.append(self.lane_factory())
    def delete_clip(self,clip):
        self.delete_calls+=1; self.arrangement_clips.remove(clip)

class Song:
    def __init__(self,path):
        self.tempo=120.; self.tracks=[Track([Clip(path)])]
        self.is_playing=False; self.record_mode=False; self.undo_calls=0
        self.view=types.SimpleNamespace(selected_track=self.tracks[0])
    def begin_undo_step(self): self._pending=copy.deepcopy(self.tracks)
    def end_undo_step(self): self._undo=self._pending
    def undo(self): self.undo_calls+=1; self.tracks=self._undo
    def create_audio_track(self,i): self.tracks.insert(i,Track([]))
    def delete_track(self,i): self.tracks.pop(i)


def make_audio(path,silent=False):
    sr=24000
    samples=[int(15000*math.sin(i*.1)) if not silent and (.1<i/sr<.5 or 1.2<i/sr<1.6) else 0 for i in range(sr*2)]
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes(struct.pack('<%dh'%len(samples),*samples))


def pcm(path):
    with wave.open(str(path),'rb') as f: return f.readframes(f.getnframes())

class ReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name); self.path=str(self.home/'source.wav'); make_audio(self.path)
        self.original=Path(self.path).read_bytes()
        self.song=Song(self.path)
        self.bridge=ClearSilenceBridge.__new__(ClearSilenceBridge); self.bridge._song=self.song
        self.output=self.home/'Music'/'ClearSilence Output'
        for patcher in [patch.dict(os.environ,HOME=str(self.home)),patch.object(app,'OUTPUT_ROOT',str(self.output)),patch.object(app,'bridge',self.call)]:
            patcher.start(); self.addCleanup(patcher.stop)
        app.jobs.clear(); app.batch_plans.clear()
        self.addCleanup(app.jobs.clear); self.addCleanup(app.batch_plans.clear)

    def call(self,action,**kwargs): return self.bridge._execute(dict(action=action,**kwargs))
    def plan(self,backup=True):
        result=app.plan_batch(dict(track_indices=list(range(len(self.song.tracks))),strength=50,backup_originals=backup))
        return app.batch_plans.pop(result['plan_id'])
    def run_worker(self,backup=True,plan=None,cancel=False):
        app.jobs['test-batch-123456']=dict(cancel=cancel,state='running',completed=0)
        app._batch_worker('test-batch-123456',plan or self.plan(backup))
        return app.jobs['test-batch-123456']
    def assert_source_intact(self): self.assertEqual(self.original,Path(self.path).read_bytes())

    def test_seven_clips_two_tracks_with_full_backups(self):
        for t,count in [(self.song.tracks[0],4),(Track([]),3)]:
            t.arrangement_clips=[Clip(self.path,360+i*8,364+i*8) for i in range(count)]
            if t not in self.song.tracks: t.name='Голос 2'; self.song.tracks.append(t)
        result=self.run_worker()
        self.assertEqual(result['state'],'done',result); self.assertEqual(result['completed'],7)
        for track,count in zip(self.song.tracks,(4,3)):
            self.assertEqual(len(track.arrangement_clips),count*2)
            self.assertEqual(len(track.take_lanes),1)
            backups=track.take_lanes[0].arrangement_clips
            self.assertEqual(len(backups),count)
            for i,backup in enumerate(backups):
                self.assertEqual(pcm(backup.file_path),pcm(self.path))
                self.assertEqual((backup.start_time,backup.end_time),(360+i*8,364+i*8))
                self.assertEqual(backup.gain,.7)
            self.assertTrue(all(not c.muted for c in track.arrangement_clips))
            self.assertTrue(all(c.gain==.7 and c.color==0xcc8844 for c in track.arrangement_clips))
        self.assert_source_intact()

    def test_offset_backup_is_exact_visible_region(self):
        self.song.tracks[0].arrangement_clips=[Clip(self.path,50.,53.,.25)]
        result=self.run_worker(); self.assertEqual(result['state'],'done',result)
        backup=self.song.tracks[0].take_lanes[0].arrangement_clips[0]
        self.assertEqual((backup.start_time,backup.end_time),(50.,53.))
        self.assertEqual(pcm(backup.file_path),pcm(self.path)[int(.25*24000)*2:int(1.75*24000)*2])
        self.assert_source_intact()

    def test_silence_removed_only_from_main_lane(self):
        make_audio(self.path,silent=True)
        result=self.run_worker(); self.assertEqual(result['state'],'done',result)
        self.assertEqual(self.song.tracks[0].arrangement_clips,[])
        backup=self.song.tracks[0].take_lanes[0].arrangement_clips[0]
        self.assertEqual(pcm(backup.file_path),pcm(self.path))

    def test_backup_can_be_disabled(self):
        self.song.tracks[0].create_take_lane=None
        result=self.run_worker(backup=False); self.assertEqual(result['state'],'done',result)
        self.assertEqual(self.song.tracks[0].take_lanes,[])
        self.assertEqual(len(self.song.tracks[0].arrangement_clips),2)
        self.assert_source_intact()

    def test_capability_preflight_checks_every_track_before_edits(self):
        self.song.tracks.append(Track([Clip(self.path)])); self.song.tracks[1].create_take_lane=None
        result=self.run_worker(); self.assertEqual(result['state'],'error')
        self.assertEqual(result['completed'],0); self.assertFalse(self.output.exists())
        self.assertEqual(self.song.tracks[0].delete_calls,0)

    def test_backup_failure_never_deletes_original(self):
        original=self.song.tracks[0]
        class BadLane(Lane): fail_create=True
        original.lane_factory=BadLane
        result=self.run_worker(); self.assertEqual(result['state'],'error',result)
        self.assertEqual(original.delete_calls,0); self.assertEqual(self.song.undo_calls,1)
        self.assertEqual(self.song.tracks[0].take_lanes,[])
        self.assertEqual(self.song.tracks[0].arrangement_clips[0].file_path,self.path)

    def test_wrong_backup_boundaries_refuse_main_edit(self):
        original=self.song.tracks[0]
        class BadLane(Lane): wrong_length=True
        original.lane_factory=BadLane
        result=self.run_worker(); self.assertEqual(result['state'],'error',result)
        self.assertEqual(original.delete_calls,0); self.assertEqual(self.song.undo_calls,1)

    def test_fragment_import_failure_undo_restores_source_and_lane(self):
        self.song.tracks[0].fail_create=True
        result=self.run_worker(); self.assertEqual(result['state'],'error',result)
        self.assertEqual(self.song.undo_calls,1)
        self.assertEqual(len(self.song.tracks[0].arrangement_clips),1)
        self.assertEqual(self.song.tracks[0].arrangement_clips[0].file_path,self.path)
        self.assertEqual(self.song.tracks[0].take_lanes,[])
        self.assert_source_intact()

    def test_wrong_fragment_boundaries_undo(self):
        self.song.tracks[0].wrong_length=True
        result=self.run_worker(); self.assertEqual(result['state'],'error',result)
        self.assertEqual(self.song.undo_calls,1)
        self.assertEqual(self.song.tracks[0].arrangement_clips[0].end_time,20.)

    def test_none_return_from_live_is_supported(self):
        self.song.tracks[0].return_none=True
        class VoidLane(Lane): return_none=True
        self.song.tracks[0].lane_factory=VoidLane
        result=self.run_worker(); self.assertEqual(result['state'],'done',result)

    def test_existing_take_lane_is_not_reused_or_modified(self):
        lane=Lane(); lane.name='My vocal take'; lane.arrangement_clips=[Clip(self.path)]
        self.song.tracks[0].take_lanes.append(lane)
        result=self.run_worker(); self.assertEqual(result['state'],'done',result)
        self.assertEqual(len(self.song.tracks[0].take_lanes),2)
        self.assertIs(self.song.tracks[0].take_lanes[0],lane)
        self.assertEqual(lane.arrangement_clips[0].file_path,self.path)

    def test_changed_source_after_analysis_refused(self):
        plan=self.plan(); self.song.tracks[0].arrangement_clips[0].gain=.3
        result=self.run_worker(plan=plan); self.assertEqual(result['state'],'error',result)
        self.assertEqual(self.song.tracks[0].delete_calls,0); self.assertEqual(self.song.undo_calls,0)

    def test_changed_neighbour_rolls_back(self):
        neighbour=Clip(self.path,24.,28.); neighbour.muted=True
        track=self.song.tracks[0]; track.arrangement_clips.append(neighbour)
        create=track.create_audio_clip
        def overwrite(path,beat):
            neighbour.end_time=25.
            return create(path,beat)
        track.create_audio_clip=overwrite
        result=self.run_worker(); self.assertEqual(result['state'],'error',result)
        self.assertEqual(self.song.undo_calls,1)
        self.assertEqual(self.song.tracks[0].arrangement_clips[1].end_time,28.)

    def test_cancel_leaves_audio_and_arrangement_untouched(self):
        result=self.run_worker(cancel=True); self.assertEqual(result['state'],'canceled')
        self.assertEqual(self.song.tracks[0].delete_calls,0); self.assert_source_intact()

    def test_stale_bridge_and_native_actions_are_refused(self):
        with patch.object(app,'bridge',return_value=dict(protocol=11,actions=['auto_begin'],version='0.6.2')):
            with self.assertRaisesRegex(RuntimeError,'старый'): app.require_replace_bridge()
        self.assertFalse(self.call('auto_begin')['ok'])
        self.assertNotIn('auto_begin',self.call('status')['actions'])

    def test_socket_start_batch_runs_restored_worker(self):
        # Exercise the real authenticated socket and main-thread dispatcher.
        token=str(self.home/'bridge_token')
        with patch.object(bridge_module,'TOKEN_FILE',token),patch.object(app,'TOKEN_FILE',token):
            surface=ClearSilenceBridge(self.song)
            self.addCleanup(surface.disconnect)
            deadline=time.time()+3
            while surface._server_socket is None and time.time()<deadline: time.sleep(.005)
            self.assertIsNotNone(surface._server_socket)
            # The setUp method patches app.bridge. Obtain the original function
            # from that patch so this integration test uses the socket instead.
            import socket,json
            def wire(action,**kwargs):
                with socket.create_connection(('127.0.0.1',bridge_module.PORT),timeout=3) as conn:
                    conn.sendall((json.dumps(dict(token=Path(token).read_text().strip(),action=action,**kwargs))+'\n').encode())
                    data=b''
                    while not data.endswith(b'\n'): data+=conn.recv(65536)
                result=json.loads(data)
                if not result.get('ok'): raise RuntimeError(result.get('error'))
                return result
            results=[]
            def start():
                try:
                    plan=app.plan_batch(dict(track_indices=[0],strength=50))
                    job=app.start_batch(dict(plan_id=plan['plan_id']))
                    while app.get_job(job['job_id'])['state']=='running': time.sleep(.005)
                    results.append(app.get_job(job['job_id']))
                except Exception as exc: results.append(dict(error=str(exc)))
            with patch.object(app,'bridge',wire):
                thread=threading.Thread(target=start,daemon=True); thread.start(); deadline=time.time()+8
                while thread.is_alive() and time.time()<deadline: surface.update_display(); time.sleep(.005)
                thread.join(.1)
            self.assertFalse(thread.is_alive()); self.assertEqual(results[0].get('state'),'done',results)
            self.assertEqual(len(self.song.tracks[0].take_lanes),1)
