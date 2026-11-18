"""Mock Live LOM integration. Real Live 12.4.6 still requires on-device validation."""
import copy, math, os, struct, sys, tempfile, threading, time, types, unittest, wave
from unittest.mock import patch
root=os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0,root)
frame=types.ModuleType('_Framework'); surf=types.ModuleType('_Framework.ControlSurface')
class ControlSurface:
    def __init__(self,c):self._song=c
    def song(self):return self._song
    def application(self):return self._song.application
    def log_message(self,*a):pass
    def update_display(self):pass
    def disconnect(self):pass
surf.ControlSurface=ControlSurface
sys.modules['_Framework']=frame;sys.modules['_Framework.ControlSurface']=surf
from ClearSilenceBridge import ClearSilenceBridge
import app
from silence_math import regions_with_muted_gaps,settings_for_strength

class Clip:
    is_audio_clip=True;warping=False;looping=False;gain=0.7;has_envelopes=False
    pitch_coarse=0;pitch_fine=0;muted=False;color=0x88ccbb;has_groove=False
    start_marker=0.;end_marker=2.
    def __init__(self,path='',st=16.,ed=20.,loopstart=0.,loopend=2.):
        self.file_path=path;self.name='Test';self.start_time=st;self.end_time=ed
        self.loop_start=loopstart;self.loop_end=loopend
        # In unlooped Live clips, Arrangement duplication length is derived
        # from start/end markers, not just loop brace coordinates.
        self.start_marker=loopstart;self.end_marker=loopend

class Slot:
    def __init__(self):self.clip=None
    @property
    def has_clip(self):return self.clip is not None
    def create_audio_clip(self,path):
        assert not self.has_clip and os.path.isfile(path)
        with wave.open(path,'rb') as f:duration=f.getnframes()/f.getframerate()
        self.clip=Clip(path,loopstart=0.,loopend=duration)
    def delete_clip(self):self.clip=None

class Track:
    has_audio_input=True;is_frozen=False
    def __init__(self,clips):
        self.name='Sound';self.arrangement_clips=clips;self.clip_slots=[Slot()]
        self.view=types.SimpleNamespace(is_collapsed=False)
        self.mute=False;self.fail_next_duplicate=False;self.ignore_content_markers=False
    def duplicate_clip_to_arrangement(self,session,beat):
        if self.fail_next_duplicate:
            self.fail_next_duplicate=False
            raise RuntimeError('Simulated duplication failure')
        # Live's unlooped Session clip length comes from the content markers,
        # not merely the loop brace. Ignore them only for rollback regression.
        duration=((session.loop_end if self.ignore_content_markers else session.end_marker)
                  -(0. if self.ignore_content_markers else session.start_marker))*2
        cl=copy.copy(session);cl.start_time=beat;cl.end_time=beat+duration
        self.arrangement_clips.append(cl)
        return cl
    def create_audio_clip(self,path,beat):
        with wave.open(path,'rb') as f:duration=f.getnframes()/f.getframerate()
        c=Clip(path,beat,beat+duration*2,0.,duration)
        self.arrangement_clips.append(c);return c
    def delete_clip(self,clip):self.arrangement_clips.remove(clip)

class Song:
    def __init__(self,path):
        self.tempo=120.;self.tracks=[Track([Clip(path)])]
        self.is_playing=False;self.record_mode=False
        self.current_song_time=0.
        self.focused_views=[]
        self.application=types.SimpleNamespace(view=types.SimpleNamespace(
            focus_view=self.focused_views.append))
        self.view=types.SimpleNamespace(selected_track=None,detail_clip=None)
    def create_audio_track(self,i):self.tracks.insert(i,Track([]))
    def delete_track(self,i):self.tracks.pop(i)
    def begin_undo_step(self):self._pending=copy.deepcopy(self.tracks)
    def end_undo_step(self):
        if getattr(self,'_pending',None) is not None:
            self._undo=self._pending;self._pending=None
    def undo(self):self.tracks=self._undo

class TestClearSilenceBridge(unittest.TestCase):
    def make_audio(self,path):
        sr=24000
        with wave.open(path,'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr)
            frames=[int(15000*math.sin(i*.1)) if .1 < i/sr < .5 or 1.2 < i/sr < 1.6 else 0 for i in range(sr*2)]
            f.writeframes(struct.pack('<%dh'%len(frames),*frames))

    def _run(self,scenario,one_clip=False):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as d:
            old_home=os.environ.get('HOME');old_token=app.TOKEN_FILE
            bridge_mod=sys.modules['ClearSilenceBridge'];old_bridge_token=bridge_mod.TOKEN_FILE
            old_preview=app.PREVIEW_ROOT
            try:
                os.environ['HOME']=home
                bridge_mod.TOKEN_FILE=os.path.join(home,'bridge_token')
                app.TOKEN_FILE=bridge_mod.TOKEN_FILE
                app.PREVIEW_ROOT=os.path.join(home,'Music','ClearSilence Preview')
                path=os.path.join(d,'source.wav');self.make_audio(path)
                song=Song(path)
                if not one_clip: song.tracks[0].arrangement_clips.append(Clip(path,24.,28.))
                if scenario=='failure':song.tracks[0].fail_next_duplicate=True
                if scenario=='wrong_length':song.tracks[0].ignore_content_markers=True
                bridge=ClearSilenceBridge(song)
                until=time.time()+2
                while bridge._server_socket is None and time.time()<until:
                    time.sleep(.005)
                self.assertIsNotNone(bridge._server_socket, 'Test bridge listener failed to start')
                results=[]
                def work():
                    try:
                        s=app.bridge('status')
                        assert s['protocol']==11 and 'auto_begin' in s['actions']
                        profile=app.clip_profile({'track_index':0,'clip_index':0})
                        assert len(profile['peaks'])>100
                        if scenario=='preview':
                            plan=app.analyze({'track_index':0,'clip_index':0,'threshold':-40,'min_silence_ms':200,'padding_ms':20})
                            r=app.create_preview({'plan_id':plan['plan_id']});results.append(r)
                            return
                        plan=app.plan_batch({'track_indices':[0],'strength':50})
                        assert plan['replace_clips']==(1 if one_clip else 2),plan
                        j=app.start_batch({'plan_id':plan['plan_id']})
                        while True:
                            status=app.get_job(j['job_id'])
                            if status['state']!='running':results.append(status);return
                            time.sleep(.01)
                    except Exception as e:results.append({'state':'exception','error':repr(e)})
                th=threading.Thread(target=work);th.start();end=time.time()+25
                while th.is_alive() and time.time()<end:bridge.update_display();time.sleep(.005)
                th.join(.5);bridge.disconnect();self.assertFalse(th.is_alive(),'Bridge hung')
                self.assertEqual(len(results),1,results)
                return song,results[0],path
            finally:
                app.TOKEN_FILE=old_token;app.PREVIEW_ROOT=old_preview
                bridge_mod.TOKEN_FILE=old_bridge_token
                if old_home is None:os.environ.pop('HOME',None)
                else:os.environ['HOME']=old_home

    def test_preview_legacy_remains_safe(self):
        song,result,path=self._run('preview',one_clip=True)
        self.assertEqual(result['created'],2,result)
        self.assertEqual(len(song.tracks),2)
        self.assertEqual(len(song.tracks[0].arrangement_clips),1)
        self.assertEqual(len(song.tracks[1].arrangement_clips),2)

    @unittest.skip('Split + Mute disabled pending compatibility probe on real Live')
    def test_split_muted_gaps_retains_original_wav(self):
        song,status,path=self._run('success')
        self.assertEqual(status['state'],'done',status)
        self.assertEqual(status['completed'],2,status)
        arr=song.tracks[0].arrangement_clips
        self.assertGreater(len(arr),5)
        self.assertEqual([c.file_path for c in arr],[path]*len(arr))
        self.assertTrue(all(abs((c.loop_end-c.loop_start) * 2-(c.end_time-c.start_time))<0.005 for c in arr))
        self.assertTrue(all(abs(c.start_marker-c.loop_start)<0.005 and
                            abs(c.end_marker-c.loop_end)<0.005 for c in arr))
        self.assertTrue(any(c.muted for c in arr))
        self.assertTrue(any(not c.muted for c in arr))
        self.assertFalse(song.tracks[0].clip_slots[0].has_clip)
        self.assertAlmostEqual(arr[0].start_time,16.,places=3)
        self.assertAlmostEqual(arr[-1].end_time,28.,places=3)

    @unittest.skip('Split + Mute disabled pending compatibility probe on real Live')
    def test_undo_if_session_duplication_fails(self):
        song,status,path=self._run('failure')
        self.assertEqual(status['state'],'error',status)
        self.assertEqual(status['completed'],0,status)
        self.assertEqual(len(song.tracks[0].arrangement_clips),2)
        self.assertFalse(song.tracks[0].clip_slots[0].has_clip)
        self.assertEqual({c.file_path for c in song.tracks[0].arrangement_clips},{path})

    def test_non_macos_automatic_split_fails_without_editing_audio(self):
        # CI cannot synthesize native macOS keystrokes. Ensure Linux refuses
        # and never modifies the original WAV/Arrangement clip.
        # Native CI runners include macOS, but must never send live keystrokes.
        with patch('native_automation.prepare_native_split',
                   side_effect=RuntimeError('Автоматизация отключена в тесте')):
            song,status,path=self._run('wrong_length',one_clip=True)
        self.assertEqual(status['state'],'error',status)
        self.assertIn('отключена в тесте',status['errors'][0])
        self.assertEqual(len(song.tracks),1)
        self.assertEqual(len(song.tracks[0].arrangement_clips),1)
        original=song.tracks[0].arrangement_clips[0]
        self.assertEqual((original.start_time,original.end_time),(16.,20.))
        self.assertEqual(original.file_path,path)
        self.assertFalse(song.tracks[0].clip_slots[0].has_clip)

    def test_previous_0_5_bridge_is_refused_before_any_edit(self):
        # Both versions expose split_mute; the new protocol prevents reusing
        # the buggy bridge just because its command names match.
        with patch.object(app, 'bridge', return_value={
            'ok':True, 'version':'0.5.0', 'protocol':3,
            'actions':['status','list','split_mute'], 'can_replace':True
        }):
            with self.assertRaisesRegex(RuntimeError, 'старый ClearSilenceBridge'):
                app.require_replace_bridge()

    def test_full_auto_multiple_splits_and_muted_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'source.wav')
            self.make_audio(path)
            song=Song(path)
            song.view.selected_track=song.tracks[0]
            bridge=ClearSilenceBridge(song)
            try:
                regions=[
                    {'start':16.,'end':16.6,'muted':True},
                    {'start':16.6,'end':17.8,'muted':False},
                    {'start':17.8,'end':18.4,'muted':True},
                    {'start':18.4,'end':20.,'muted':False},
                ]
                started=bridge._execute({'action':'auto_begin',
                    'track_index':0,'track_name':'Sound',
                    'tempo':120.,'rate':24000,
                    'source':{'file_path':path,'start':16.,'end':20.,'file_offset':0.,'file_end':2.},
                    'regions':regions})
                self.assertEqual(started['cuts'],3)
                for boundary in (18.4,17.8,16.6):
                    armed=bridge._execute({'action':'auto_arm'})
                    self.assertAlmostEqual(armed['target_beat'],boundary,places=4)
                    self.assertTrue(bridge._execute({'action':'auto_confirm'})['confirmed'])
                    track=song.tracks[0]
                    left=next(c for c in track.arrangement_clips
                              if c.start_time < boundary < c.end_time)
                    right=copy.copy(left)
                    right.start_time=boundary
                    right.loop_start=(boundary-16.)/2
                    left.loop_end=right.loop_start
                    left.end_time=boundary
                    track.arrangement_clips.append(right)
                    verified=bridge._execute({'action':'auto_verify'})
                    self.assertTrue(verified['verified'],verified)
                finish=bridge._execute({'action':'auto_finish'})
                self.assertEqual(finish['created'],4)
                self.assertEqual(finish['muted'],2)
                ordered=sorted(song.tracks[0].arrangement_clips,
                               key=lambda c:c.start_time)
                self.assertEqual([c.muted for c in ordered],
                                 [True,False,True,False])
                self.assertEqual([c.file_path for c in ordered],[path]*4)
            finally:
                bridge.disconnect()

    def test_full_auto_wrong_split_does_not_mute(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'source.wav')
            self.make_audio(path)
            song=Song(path)
            bridge=ClearSilenceBridge(song)
            try:
                bridge._execute({'action':'auto_begin',
                    'track_index':0,'track_name':'Sound',
                    'tempo':120.,'rate':24000,
                    'source':{'file_path':path,'start':16.,'end':20.,'file_offset':0.,'file_end':2.},
                    'regions':[{'start':16.,'end':18.,'muted':True},
                               {'start':18.,'end':20.,'muted':False}]})
                bridge._execute({'action':'auto_arm'})
                bridge._execute({'action':'auto_confirm'})
                left=song.tracks[0].arrangement_clips[0]
                right=copy.copy(left)
                left.end_time=19.
                right.start_time=19.
                right.loop_start=1.5
                left.loop_end=1.5
                song.tracks[0].arrangement_clips.append(right)
                with self.assertRaisesRegex(RuntimeError,'не в нужной точке'):
                    bridge._execute({'action':'auto_verify'})
                self.assertFalse(left.muted)
                self.assertFalse(right.muted)
            finally:
                bridge.disconnect()

    def test_native_split_and_mute_on_disposable_track(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'source.wav')
            self.make_audio(path)
            song=Song(path)
            original=song.tracks[0].arrangement_clips[0]
            bridge=ClearSilenceBridge(song)
            try:
                result=bridge._execute({'action':'native_prepare',
                                        'track_index':0, 'clip_index':0})
                self.assertTrue(result['ok'],result)
                self.assertEqual(len(song.tracks),2)
                temp=song.tracks[1]
                self.assertTrue(temp.mute)
                self.assertEqual(len(temp.arrangement_clips),1)
                self.assertEqual(temp.arrangement_clips[0].start_time,
                                 original.start_time)
                # Without a real native GUI split, verification must refuse.
                pending=bridge._execute({'action':'native_verify'})
                self.assertFalse(pending['passed'],pending)
                # Simulate Live's Cmd+E producing two adjacent Arrangement
                # clips referencing the exact same full source file.
                left=temp.arrangement_clips[0]
                right=copy.copy(left)
                cut=left.start_time+1.
                right.start_time=cut
                left.end_time=cut
                temp.arrangement_clips=[left,right]
                passed=bridge._execute({'action':'native_verify'})
                self.assertTrue(passed['passed'],passed)
                self.assertFalse(left.muted)
                self.assertTrue(right.muted)
                self.assertEqual(left.file_path,path)
                self.assertEqual(right.file_path,path)
                self.assertIs(song.tracks[0].arrangement_clips[0],original)
                self.assertEqual((original.start_time,original.end_time),(16.,20.))
                clean=bridge._execute({'action':'native_cleanup'})
                self.assertTrue(clean['removed'],clean)
                self.assertEqual(len(song.tracks),1)
                self.assertIs(song.tracks[0].arrangement_clips[0],original)
            finally:
                bridge.disconnect()

    def test_auto_split_arms_exact_playhead_and_validates_cut(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'source.wav')
            self.make_audio(path)
            song=Song(path)
            source=song.tracks[0].arrangement_clips[0]
            bridge=ClearSilenceBridge(song)
            try:
                bridge._execute({'action':'native_prepare',
                                 'track_index':0,'clip_index':0})
                armed=bridge._execute({'action':'native_arm'})
                beat=armed['target_beat']
                self.assertAlmostEqual(song.current_song_time,beat,places=4)
                self.assertTrue(bridge._execute({'action':'native_confirm'})['confirmed'])
                self.assertIs(song.view.selected_track,song.tracks[1])
                self.assertIs(song.view.detail_clip,
                              song.tracks[1].arrangement_clips[0])
                left=song.tracks[1].arrangement_clips[0]
                right=copy.copy(left)
                # Wrong split position must be rejected without Mute.
                left.end_time=beat+1
                right.start_time=beat+1
                song.tracks[1].arrangement_clips=[left,right]
                wrong=bridge._execute({'action':'native_verify'})
                self.assertFalse(wrong['passed'],wrong)
                self.assertFalse(right.muted)
                # At the planned beat this same sample passes.
                left.end_time=beat
                right.start_time=beat
                passed=bridge._execute({'action':'native_verify'})
                self.assertTrue(passed['passed'],passed)
                self.assertTrue(right.muted)
                self.assertIs(song.tracks[0].arrangement_clips[0],source)
                bridge._execute({'action':'native_cleanup'})
            finally:
                bridge.disconnect()

    def test_delayed_playhead_acknowledgement(self):
        class DeferredSong(Song):
            def __init__(self, path):
                self._actual_time = 0.
                self._pending_time = None
                super().__init__(path)
            @property
            def current_song_time(self):
                return self._actual_time
            @current_song_time.setter
            def current_song_time(self, value):
                self._pending_time = float(value)
            def advance_live_tick(self):
                self._actual_time = self._pending_time

        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'source.wav')
            self.make_audio(path)
            song=DeferredSong(path)
            bridge=ClearSilenceBridge(song)
            try:
                bridge._execute({'action':'native_prepare',
                                 'track_index':0,'clip_index':0})
                armed=bridge._execute({'action':'native_arm'})
                early=bridge._execute({'action':'native_confirm'})
                self.assertFalse(early['confirmed'])
                song.advance_live_tick()
                late=bridge._execute({'action':'native_confirm'})
                self.assertTrue(late['confirmed'],late)
                self.assertAlmostEqual(late['target_beat'],
                                       armed['target_beat'])
                bridge._execute({'action':'native_cleanup'})
            finally:
                bridge.disconnect()

    def test_native_arm_preserves_existing_waveform_focus(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d, 'original.wav')
            self.make_audio(path)
            song=Song(path)
            bridge=ClearSilenceBridge(song)
            try:
                bridge._execute({'action':'native_prepare',
                                 'track_index':0,'clip_index':0})
                # A focused waveform may coexist with another detail_clip:
                # arming must not change either UI selection property.
                focused_track=song.tracks[1]
                previous_detail=object()
                song.view.detail_clip=previous_detail
                result=bridge._execute({'action':'native_arm'})
                self.assertTrue(result['ok'])
                self.assertIs(song.view.selected_track,focused_track)
                self.assertIs(song.view.detail_clip,previous_detail)
                bridge._execute({'action':'native_cleanup'})
            finally:
                bridge.disconnect()

    def test_native_arm_refuses_wrong_selected_track_before_cmd_e(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d, 'original.wav')
            self.make_audio(path)
            song=Song(path)
            bridge=ClearSilenceBridge(song)
            try:
                bridge._execute({'action':'native_prepare',
                                 'track_index':0,'clip_index':0})
                # User accidentally selects the original track, not the test.
                song.view.selected_track=song.tracks[0]
                song.current_song_time=0.
                with self.assertRaisesRegex(RuntimeError,'не выбрана тестовая'):
                    bridge._execute({'action':'native_arm'})
                self.assertEqual(song.current_song_time,0.)
                bridge._execute({'action':'native_cleanup'})
            finally:
                bridge.disconnect()

    def test_auto_split_detects_changes_to_other_tracks(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'source.wav')
            self.make_audio(path)
            song=Song(path)
            bridge=ClearSilenceBridge(song)
            try:
                bridge._execute({'action':'native_prepare',
                                 'track_index':0,'clip_index':0})
                bridge._execute({'action':'native_arm'})
                self.assertTrue(bridge._execute({'action':'native_confirm'})['confirmed'])
                song.tracks[0].arrangement_clips[0].name='Changed'
                # Name alone is not the fingerprint; timing modification is.
                song.tracks[0].arrangement_clips[0].end_time+=1
                with self.assertRaisesRegex(RuntimeError,'Исходная дорожка'):
                    bridge._execute({'action':'native_verify'})
                bridge._execute({'action':'native_cleanup'})
            finally:
                bridge.disconnect()

    def test_native_cleanup_refuses_unrelated_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'source.wav')
            self.make_audio(path)
            song=Song(path)
            bridge=ClearSilenceBridge(song)
            try:
                bridge._execute({'action':'native_prepare',
                                 'track_index':0,'clip_index':0})
                song.tracks[1].arrangement_clips[0].file_path='unrelated.wav'
                with self.assertRaisesRegex(RuntimeError,'другие клипы'):
                    bridge._execute({'action':'native_cleanup'})
                self.assertEqual(len(song.tracks),2)
            finally:
                bridge.disconnect()

    def test_safe_probe_never_edits_source_clip(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'source.wav')
            self.make_audio(path)
            song=Song(path)
            original=song.tracks[0].arrangement_clips[0]
            before=(original.start_time,original.end_time,
                    original.loop_start,original.loop_end,
                    original.file_path,original.muted)
            bridge=ClearSilenceBridge(song)
            try:
                data=bridge._probe_region(song,{'track_index':0,'clip_index':0})
                self.assertTrue(data['ok'],data)
                self.assertEqual(len(data['results']),2,data)
                self.assertTrue(data['original_tracks_unchanged'],data)
                self.assertEqual(len(song.tracks),1)
                self.assertIs(song.tracks[0].arrangement_clips[0],original)
                after=(original.start_time,original.end_time,
                       original.loop_start,original.loop_end,
                       original.file_path,original.muted)
                self.assertEqual(before,after)
            finally:
                bridge.disconnect()

    def test_stale_bridge_rejected(self):
        sentinel={'created':time.time(),'entries':[{'name':'whatever'}], 'allow_empty':False}
        app.batch_plans['old-bridge']=sentinel
        def old(action, **kw):
            if action=='status': return {'ok':True,'version':'0.4.0','protocol':2,'actions':['replace'],'can_replace':True}
            raise ValueError('old')
        try:
            with patch.object(app,'bridge',old):
                with self.assertRaisesRegex(RuntimeError,'старый ClearSilenceBridge'):
                    app.start_batch({'plan_id':'old-bridge'})
            self.assertIs(app.batch_plans['old-bridge'],sentinel)
        finally:
            app.batch_plans.pop('old-bridge',None)

if __name__=='__main__':unittest.main()
