import tempfile, os, sys, types, threading, time, struct, math, wave, unittest, copy
root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,root)

# Minimal stub of Live's ControlSurface used only for testing code flow outside Live.
frame=types.ModuleType('_Framework'); surf=types.ModuleType('_Framework.ControlSurface')
class ControlSurface:
    def __init__(self,c):self._song=c
    def song(self):return self._song
    def log_message(self,*a):pass
    def update_display(self):pass
    def disconnect(self):pass
surf.ControlSurface=ControlSurface
sys.modules['_Framework']=frame;sys.modules['_Framework.ControlSurface']=surf
from ClearSilenceBridge import ClearSilenceBridge
import app

class Clip:
    is_audio_clip=True; warping=False; looping=False; gain=0.7; has_envelopes=False
    pitch_coarse=0;pitch_fine=0;muted=False;color=0x88ccbb;has_groove=False
    def __init__(self,path=None, st=16.,ed=20., end=2.):
        self.file_path=path or '';self.name='Test';self.start_time=st;self.end_time=ed
        self.loop_start=0.;self.loop_end=end
class Track:
    has_audio_input=True;is_frozen=False
    def __init__(self, clips):self.name='Sound';self.arrangement_clips=clips;self.mute=False
    def create_audio_clip(self,path,beat):
        if getattr(self,'fail_next_creation',False):
            self.fail_next_creation=False
            raise RuntimeError('Simulated create failure')
        assert os.path.isfile(path)
        with wave.open(path,'rb') as f:
            dur=f.getnframes()/f.getframerate()
        cl=Clip(path,beat,beat+dur*2,dur)
        self.arrangement_clips.append(cl)
        return cl
    def delete_clip(self,clip):
        self.arrangement_clips.remove(clip)
class Song:
    def __init__(self, path):
        self.tempo=120.;self.tracks=[Track([Clip(path)])];self.is_playing=False;self.record_mode=False
    def create_audio_track(self,i):self.tracks.insert(i, Track([]))
    def delete_track(self,i):self.tracks.pop(i)
    def begin_undo_step(self):self._pending=copy.deepcopy(self.tracks)
    def end_undo_step(self):
        if getattr(self,'_pending',None) is not None:
            self._undo=self._pending
            self._pending=None
    def undo(self):self.tracks=self._undo
class TestBridge(unittest.TestCase):
    def test_full_preview(self):
        with tempfile.TemporaryDirectory() as home:
            original_home = os.environ.get('HOME')
            os.environ['HOME'] = home
            # Override module globals to prevent test files in user's home
            bridge_mod=sys.modules['ClearSilenceBridge']
            bridge_mod.TOKEN_FILE=os.path.join(home,'bridge_token')
            app.TOKEN_FILE=bridge_mod.TOKEN_FILE
            app.PREVIEW_ROOT=os.path.join(home,'Music','ClearSilence Preview')
            with tempfile.TemporaryDirectory() as d:
                path=os.path.join(d,'test.wav');sr=24000
                with wave.open(path,'wb') as f:
                    f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr)
                    frames=[int(15000*math.sin(i*0.1)) if .1 < i/sr < .5 or 1.2 < i/sr < 1.6 else 0 for i in range(sr*2)]
                    f.writeframes(struct.pack('<%dh'%len(frames),*frames))
                song=Song(path)
                bridge=ClearSilenceBridge(song)
                results=[]
                def client_fn():
                    try:
                        st=app.bridge('status');assert st['tracks']==1 and st['protocol']==2 and 'replace' in st['actions']
                        tracks=app.bridge('list');assert tracks['tracks'][0]['clips'][0]['name']=='Test'
                        plan=app.analyze({'track_index':0,'clip_index':0,'threshold':-40,'min_silence_ms':200,'padding_ms':20})
                        assert plan['segments']==2, plan
                        visual=app.visualize_clip({'track_index':0,'clip_index':0,'threshold':-40,'min_silence_ms':200,'padding_ms':20})
                        assert visual['fragments']==2 and len(visual['waveform'])==550, visual
                        assert visual['removed_seconds']>0.3, visual
                        result=app.create_preview({'plan_id':plan['plan_id']})
                        assert result['created']==2, result
                        results.append('OK')
                    except Exception as e:results.append(repr(e))
                t=threading.Thread(target=client_fn)
                t.start()
                deadline=time.time()+15
                while t.is_alive() and time.time()<deadline:
                    bridge.update_display();time.sleep(.01)
                t.join(timeout=0.5)
                bridge.disconnect()
                if original_home is not None: os.environ['HOME'] = original_home
                self.assertFalse(t.is_alive(),'Client deadlocked')
                self.assertEqual(results,['OK'])
                self.assertEqual(len(song.tracks),2)
                self.assertEqual(len(song.tracks[0].arrangement_clips),1)
                self.assertEqual(len(song.tracks[1].arrangement_clips),2)
                self.assertTrue(song.tracks[1].mute)


class TestBatch(unittest.TestCase):
    def make_audio(self, path):
        sr=24000
        with wave.open(path,'wb') as f:
            f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr)
            frames=[int(15000*math.sin(i*.1)) if .1 < i/sr < .5 or 1.2 < i/sr < 1.6 else 0 for i in range(sr*2)]
            f.writeframes(struct.pack('<%dh'%len(frames),*frames))

    def _run_case(self, fail_creation):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as d:
            old_home=os.environ.get('HOME')
            old_token=app.TOKEN_FILE
            old_output=app.OUTPUT_ROOT
            bridge_mod=sys.modules['ClearSilenceBridge']
            old_bridge_token=bridge_mod.TOKEN_FILE
            try:
                os.environ['HOME']=home
                bridge_mod.TOKEN_FILE=os.path.join(home,'bridge_token')
                app.TOKEN_FILE=bridge_mod.TOKEN_FILE
                app.OUTPUT_ROOT=os.path.join(home,'Music','ClearSilence Output')
                path=os.path.join(d,'test.wav')
                self.make_audio(path)
                song=Song(path)
                song.tracks[0].arrangement_clips.append(Clip(path,24.,28.,2.))
                if fail_creation:
                    song.tracks[0].fail_next_creation=True
                control=ClearSilenceBridge(song)
                result=[]
                def task():
                    try:
                        s=app.bridge('status')
                        assert s['can_replace']
                        plan=app.plan_batch({'track_indices':[0],'threshold':-40,
                           'min_silence_ms':200,'padding_ms':20})
                        assert plan['replace_clips']==2,plan
                        assert plan['fragments']==4,plan
                        job=app.start_batch({'plan_id':plan['plan_id']})
                        while True:
                            status=app.get_job(job['job_id'])
                            if status['state']!='running':
                                result.append(status)
                                return
                            time.sleep(.01)
                    except Exception as e:
                        result.append({'state':'exception','error':repr(e)})
                t=threading.Thread(target=task)
                t.start()
                until=time.time()+18
                while t.is_alive() and time.time()<until:
                    control.update_display();time.sleep(.005)
                t.join(.5)
                control.disconnect()
                self.assertFalse(t.is_alive(),'Remote bridge hung')
                self.assertEqual(len(result),1,result)
                status=result[0]
                if fail_creation:
                    self.assertEqual(status['state'],'error',status)
                    self.assertEqual(status['completed'],0,status)
                    # Snapshot rollback restores the first clip and stops before second.
                    self.assertEqual(len(song.tracks[0].arrangement_clips),2)
                    self.assertTrue(all(c.file_path==path for c in song.tracks[0].arrangement_clips))
                else:
                    self.assertEqual(status['state'],'done',status)
                    self.assertEqual(status['completed'],2,status)
                    self.assertEqual(len(song.tracks[0].arrangement_clips),4)
                    self.assertTrue(all(os.path.isfile(c.file_path) for c in song.tracks[0].arrangement_clips))
                    self.assertEqual(len(song.tracks),1)
            finally:
                app.TOKEN_FILE=old_token
                app.OUTPUT_ROOT=old_output
                bridge_mod.TOKEN_FILE=old_bridge_token
                if old_home is None: os.environ.pop('HOME',None)
                else: os.environ['HOME']=old_home

    def test_old_bridge_rejected_before_changes(self):
        from unittest.mock import patch
        sentinel={'created':time.time(),'entries':[{'name':'anything'}], 'allow_empty':False}
        app.batch_plans['test_old'] = sentinel
        def old_bridge(action, **kwargs):
            if action=='status': return {'ok':True, 'version':'0.1.0', 'can_replace':True}
            return {'ok':False, 'error':'Unknown action'}
        try:
            with patch.object(app,'bridge',old_bridge):
                with self.assertRaisesRegex(RuntimeError,'старый ClearSilenceBridge'):
                    app.start_batch({'plan_id':'test_old'})
            self.assertIs(app.batch_plans['test_old'],sentinel)
        finally:
            app.batch_plans.pop('test_old',None)

    def test_replace_multiple_clips_in_place(self):
        self._run_case(False)

    def test_undo_if_creation_fails(self):
        self._run_case(True)

if __name__=='__main__':unittest.main()
