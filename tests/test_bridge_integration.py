"""Live API doubles: verify replacement, backup ordering and rollback.

These tests do not claim to run Ableton Live; macOS CI builds the actual app.
"""
import copy
import math
import queue
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
    def update_display(self): self._song.tick()
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
    clip_type=Clip
    return_none=False; wrong_length=False; fail_create=False
    def __init__(self): self.name='Take'; self.arrangement_clips=[]
    def create_audio_clip(self,path,beat):
        if self.fail_create: raise RuntimeError('Simulated file import failure')
        with wave.open(path,'rb') as f: duration=f.getnframes()/f.getframerate()
        c=self.clip_type(path,beat,beat+duration*2)
        if self.wrong_length: c.end_time+=.5
        self.arrangement_clips.append(c)
        return None if self.return_none else c

class DeferredClip(Clip):
    """Model the documented deferred Warp setter and stale beat geometry."""
    early_false=False
    never_settles=False
    def __init__(self,path,st,ed):
        super().__init__(path,st,ed)
        self._real_end=ed
        self._duration=(ed-st)/2
        self.end_time=ed+.75
        self.loop_end=self._duration*2
        self._warp=True
        self._ticks=None
    @property
    def warping(self):
        return False if self.early_false and self._ticks is not None else self._warp
    @warping.setter
    def warping(self,value):
        if value: self._warp=True
        else: self._ticks=2
    def __setattr__(self,name,value):
        if name in ('loop_start','loop_end') and getattr(self,'_warp',False):
            raise AssertionError('Wrote seconds while Warp conversion was still pending')
        super().__setattr__(name,value)
    def tick(self):
        if self._ticks is None or self.never_settles: return
        self._ticks-=1
        if self._ticks<=0:
            self._warp=False
            self.end_time=self._real_end
            self.loop_end=self._duration
            self._ticks=None

class DeferredLane(Lane):
    clip_type=DeferredClip

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
    def tick(self):
        for track in self.tracks:
            for lane in [track] + track.take_lanes:
                for clip in lane.arrangement_clips:
                    advance=getattr(clip,'tick',None)
                    if advance: advance()
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

    def call(self,action,**kwargs):
        result=self.bridge._execute(dict(action=action,**kwargs))
        if not isinstance(result,types.GeneratorType): return result
        for _ in range(1000):
            try: next(result)
            except StopIteration as done: return done.value
            self.song.tick()
        self.fail('Replacement generator did not finish')
    def plan(self,backup=True):
        result=app.plan_batch(dict(track_indices=list(range(len(self.song.tracks))),strength=50,backup_originals=backup))
        return app.batch_plans.pop(result['plan_id'])
    def run_worker(self,backup=True,plan=None,cancel=False):
        app.jobs['test-batch-123456']=dict(cancel=cancel,state='running',completed=0)
        app._batch_worker('test-batch-123456',plan or self.plan(backup))
        return app.jobs['test-batch-123456']
    def assert_source_intact(self): self.assertEqual(self.original,Path(self.path).read_bytes())

    def test_group_headers_are_not_queried_and_child_indices_are_preserved(self):
        class Group:
            name='Group'; is_foldable=True; has_audio_input=True; fold_state=True
            @property
            def arrangement_clips(self):
                raise RuntimeError('Main, Group and Return Tracks have no arrangement clips')
        outer,inner=Group(),Group()
        first,second=Track([Clip(self.path)]),Track([Clip(self.path)])
        first.group_track=outer; second.group_track=inner
        self.song.tracks=[outer,first,inner,second]
        self.song.view.selected_track=second
        listing=self.call('list')
        self.assertEqual([t['index'] for t in listing['tracks']],[1,3])
        self.assertEqual(listing['selected_track_index'],3)
        plan=app.plan_batch(dict(track_indices=[3],strength=50,backup_originals=True))
        self.assertEqual(plan['replace_clips'],1)
        self.song.view.selected_track=outer
        self.assertEqual(self.call('list')['selected_track_index'],0)

    def test_non_audio_tracks_do_not_expose_arrangement_clips(self):
        class NonAudio:
            is_foldable=False; has_audio_input=False
            @property
            def arrangement_clips(self):
                raise AssertionError('Non-audio track clips should not be queried')
        self.song.tracks=[NonAudio(),self.song.tracks[0]]
        self.assertEqual([t['index'] for t in self.call('list')['tracks']],[1])

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
        with patch.object(app,'bridge',return_value=dict(protocol=12,actions=['replace'],version='0.7.0')):
            with self.assertRaisesRegex(RuntimeError,'старый'): app.require_replace_bridge()
        self.assertFalse(self.call('auto_begin')['ok'])
        self.assertNotIn('auto_begin',self.call('status')['actions'])

    def test_deferred_warp_waits_before_reading_bounds_and_markers(self):
        track=self.song.tracks[0]
        track.clip_type=DeferredClip; track.lane_factory=DeferredLane
        result=self.run_worker()
        self.assertEqual(result['state'],'done',result)
        self.assertEqual(len(track.arrangement_clips),2)
        self.assertTrue(all(not c.warping for c in track.arrangement_clips))
        self.assertEqual(track.take_lanes[0].arrangement_clips[0].end_time,20.)
        self.assert_source_intact()

    def test_false_warp_getter_does_not_allow_same_event_geometry_check(self):
        class EarlyClip(DeferredClip): early_false=True
        class EarlyLane(Lane): clip_type=EarlyClip
        track=self.song.tracks[0]
        track.clip_type=EarlyClip; track.lane_factory=EarlyLane
        result=self.run_worker()
        self.assertEqual(result['state'],'done',result)

    def test_warp_that_does_not_settle_rolls_back_before_source_deletion(self):
        class StuckClip(DeferredClip): never_settles=True
        class StuckLane(Lane): clip_type=StuckClip
        track=self.song.tracks[0]; track.lane_factory=StuckLane
        result=self.run_worker()
        self.assertEqual(result['state'],'error',result)
        self.assertIn('резерв Take Lane: Warp',result['message'])
        self.assertEqual(track.delete_calls,0)
        self.assertEqual(self.song.undo_calls,1)
        self.assertEqual(self.song.tracks[0].arrangement_clips[0].file_path,self.path)

    def test_import_restores_full_new_file_markers_after_warp_is_off(self):
        class CroppedLane(Lane):
            def create_audio_clip(self,path,beat):
                clip=super().create_audio_clip(path,beat)
                clip.loop_start=.02; clip.loop_end-=.03
                return clip
        self.song.tracks[0].lane_factory=CroppedLane
        result=self.run_worker()
        self.assertEqual(result['state'],'done',result)
        clip=self.song.tracks[0].take_lanes[0].arrangement_clips[0]
        self.assertEqual((clip.loop_start,clip.loop_end),(0.,2.))

    def test_equivalent_file_path_is_accepted_by_identity(self):
        class AliasLane(Lane):
            def create_audio_clip(self,path,beat):
                clip=super().create_audio_clip(path,beat)
                alias=Path(path).with_suffix('.alias.wav'); alias.symlink_to(path)
                clip.file_path=str(alias)
                return clip
        self.song.tracks[0].lane_factory=AliasLane
        result=self.run_worker(); self.assertEqual(result['state'],'done',result)

    def test_boundary_error_names_stage_field_expected_and_observed(self):
        class BadLane(Lane): wrong_length=True
        self.song.tracks[0].lane_factory=BadLane
        result=self.run_worker()
        self.assertEqual(result['state'],'error',result)
        self.assertIn('резерв Take Lane: end_time: Live=20.50000000; ожидалось=20.00000000',result['message'])
        self.assertIn('Undo',result['message'])

    def test_deadline_exception_rolls_back_pending_backup(self):
        original_call=self.call
        def expire(action,**kwargs):
            if action!='replace': return original_call(action,**kwargs)
            command=self.bridge._execute(dict(action=action,**kwargs))
            next(command)  # Backup imported, Warp conversion has not run yet.
            command.throw(RuntimeError('Simulated command deadline'))
        with patch.object(app,'bridge',expire): result=self.run_worker()
        self.assertEqual(result['state'],'error',result)
        self.assertEqual(self.song.undo_calls,1)
        self.assertEqual(self.song.tracks[0].take_lanes,[])
        self.assertEqual(self.song.tracks[0].arrangement_clips[0].file_path,self.path)

    def test_dispatcher_returns_to_live_between_generator_steps(self):
        self.bridge._requests=queue.Queue(); self.bridge._pending_command=None
        reply=queue.Queue(); seen=[]
        def command():
            seen.append('created'); yield
            seen.append('validated'); return dict(ok=True)
        self.bridge._requests.put((dict(action='replace'),reply,time.monotonic()+5))
        with patch.object(self.bridge,'_execute',return_value=command()):
            self.bridge.update_display()
            self.assertEqual(seen,['created']); self.assertTrue(reply.empty())
            self.bridge.update_display()
        self.assertEqual(seen,['created','validated'])
        self.assertTrue(reply.get_nowait()['ok'])
        self.assertIsNone(self.bridge._pending_command)

    def test_dispatcher_never_starts_an_expired_queued_edit(self):
        self.bridge._requests=queue.Queue(); self.bridge._pending_command=None
        reply=queue.Queue(); self.bridge._requests.put((dict(action='replace'),reply,0.))
        with patch.object(self.bridge,'_execute') as execute:
            self.bridge.update_display(); execute.assert_not_called()
        self.assertFalse(reply.get_nowait()['ok'])

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
