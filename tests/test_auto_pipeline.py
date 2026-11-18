"""Whole worker/bridge regression with an explicit, simulated native editor.

This exercises the production protocol, not a substitute for Live on macOS.
"""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from test_bridge_integration import Clip, Song, Track, ClearSilenceBridge
import test_bridge_integration as fixture


class AutoPipeline(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=str(Path(self.temp.name)/'source.wav')
        fixture.TestClearSilenceBridge.make_audio(self,self.path)
        self.song=Song(self.path)
        self.bridge=ClearSilenceBridge.__new__(ClearSilenceBridge)
        self.bridge._song=self.song
        self.sent=0
        self.addCleanup(app.jobs.clear)
        self.addCleanup(app.batch_plans.clear)

    def call(self,action,**kwargs):
        return self.bridge._execute(dict(action=action,**kwargs))

    def begin(self,boundary=18.):
        return self.call('auto_begin',track_index=0,track_name='Sound',tempo=120.,rate=24000,
                         source=dict(file_path=self.path,start=16.,end=20.,file_offset=0.,file_end=2.),
                         regions=[dict(start=16.,end=boundary,muted=True),
                                  dict(start=boundary,end=20.,muted=False)])

    def prepare(self):
        self.assertEqual(self.song.focused_views[-1],'Arranger')
        state=self.bridge._auto_job_state
        self.assertIs(self.song.view.selected_track,state['track'])
        self.assertIs(self.song.view.detail_clip,state['pending_clip'])
        return dict(pid=123,focus='AXGroup: Arrangement')

    def split(self,prepared):
        self.assertEqual(prepared['pid'],123)
        self.sent+=1
        state=self.bridge._auto_job_state
        self.realistic_split(state['pending'])
        # Selecting the right fragment after Split must not break a subsequent
        # cut to the LEFT, or the transition to another track.
        self.song.focused_views.append('Detail/Clip')

    def realistic_split(self,boundary):
        state=self.bridge._auto_job_state
        track=state['track']
        left=next(c for c in track.arrangement_clips if c.start_time<boundary<c.end_time)
        right=copy.copy(left)
        right.start_time=boundary
        right.loop_start=left.loop_start+(boundary-left.start_time)*60/self.song.tempo
        right.start_marker=right.loop_start
        left.end_time=boundary
        left.loop_end=right.loop_start
        left.end_marker=right.loop_start
        track.arrangement_clips.append(right)
        self.song.view.detail_clip=right

    def worker(self,prepare=None):
        with patch.object(app,'bridge',self.call), \
                patch('native_automation.prepare_native_split',prepare or self.prepare), \
                patch('native_automation.send_native_split',self.split), \
                patch.object(app.time,'sleep'):
            plan=app.plan_batch(dict(track_indices=list(range(len(self.song.tracks))),strength=50))
            internal=app.batch_plans.pop(plan['plan_id'])
            app.jobs['test']=dict(cancel=False,state='running',completed=0)
            app._auto_native_worker('test',internal)
        return app.jobs['test']

    def test_seven_clips_across_tracks_are_split_muted_and_keep_wav(self):
        self.song.tracks[0].arrangement_clips=[Clip(self.path,360.+i*8,364.+i*8) for i in range(4)]
        self.song.tracks.append(Track([Clip(self.path,16.+i*8,20.+i*8) for i in range(3)]))
        self.song.tracks[1].name='Голос Катя'
        before=hashlib.sha256(Path(self.path).read_bytes()).digest()
        result=self.worker()
        self.assertEqual(result['state'],'done',result)
        self.assertEqual(result['completed'],7)
        self.assertGreater(self.sent,14)
        for track in self.song.tracks:
            self.assertTrue(any(c.muted for c in track.arrangement_clips))
            self.assertTrue(any(not c.muted for c in track.arrangement_clips))
            self.assertTrue(all(c.file_path==self.path for c in track.arrangement_clips))
            self.assertFalse(track.clip_slots[0].has_clip)
        self.assertEqual(before,hashlib.sha256(Path(self.path).read_bytes()).digest())

    def test_focus_navigation_transport_change_blocks_split(self):
        def drift():
            result=self.prepare()
            self.song.current_song_time+=1
            return result
        result=self.worker(drift)
        self.assertEqual(result['state'],'error')
        self.assertIn('изменилась',result['message'])
        self.assertEqual(self.sent,0)
        self.assertEqual(len(self.song.tracks[0].arrangement_clips),1)

    def test_disabled_menu_never_sends_split(self):
        def disabled(): raise RuntimeError('CS_SPLIT_DISABLED')
        result=self.worker(disabled)
        self.assertEqual(result['state'],'error')
        self.assertEqual(self.sent,0)
        self.assertFalse(self.song.tracks[0].arrangement_clips[0].muted)

    def test_cancel_after_prepare_never_sends_split(self):
        def cancel():
            result=self.prepare()
            app.jobs['test']['cancel']=True
            return result
        result=self.worker(cancel)
        self.assertEqual(self.sent,0)
        self.assertIn('отменена',result['message'])

    def test_wrong_track_after_prepare_blocks_split(self):
        def switch_track():
            result=self.prepare()
            self.song.view.selected_track=object()
            return result
        result=self.worker(switch_track)
        self.assertEqual(result['state'],'error')
        self.assertEqual(self.sent,0)

    def test_shift_of_10ms_is_rejected_not_accepted_as_correct_cut(self):
        self.begin()
        self.call('auto_arm');self.call('auto_confirm')
        self.realistic_split(18.02)
        with self.assertRaisesRegex(RuntimeError,'не в нужной точке'):
            self.call('auto_verify')
        self.assertFalse(any(c.muted for c in self.song.tracks[0].arrangement_clips))

    def test_repeated_first_boundary_cannot_confirm_later_split(self):
        self.begin(18.02)
        self.call('auto_arm');self.call('auto_confirm')
        self.realistic_split(18.02)
        self.call('auto_verify')
        # A previous boundary was accepted by the old any(abs(b-target)<.06).
        state=self.bridge._auto_job_state
        state['cuts'].append(18.)
        self.call('auto_arm');self.call('auto_confirm')
        self.realistic_split(17.98)
        with self.assertRaisesRegex(RuntimeError,'не в нужной точке'):
            self.call('auto_verify')

    def test_correct_geometry_with_wrong_source_offset_is_rejected(self):
        self.begin();self.call('auto_arm');self.call('auto_confirm')
        self.realistic_split(18.)
        self.song.view.detail_clip.loop_start=0.
        with self.assertRaisesRegex(RuntimeError,'смещение'):
            self.call('auto_verify')

    def test_neighbour_on_same_track_is_protected(self):
        neighbour=Clip(self.path,24.,28.)
        self.song.tracks[0].arrangement_clips.append(neighbour)
        self.begin();self.call('auto_arm');self.call('auto_confirm')
        neighbour.end_time=27.
        with self.assertRaisesRegex(RuntimeError,'соседние'):
            self.call('auto_verify')

    def test_finish_rechecks_other_tracks_even_without_any_cut(self):
        self.song.tracks.append(Track([Clip(self.path)]))
        self.call('auto_begin',track_index=0,track_name='Sound',tempo=120.,rate=24000,
                  source=dict(file_path=self.path,start=16.,end=20.,file_offset=0.,file_end=2.),
                  regions=[dict(start=16.,end=20.,muted=True)])
        self.song.tracks[1].arrangement_clips[0].muted=True
        with self.assertRaisesRegex(RuntimeError,'другие дорожки'):
            self.call('auto_finish')
        self.assertFalse(self.song.tracks[0].arrangement_clips[0].muted)

    def test_changed_tempo_recording_and_stale_offset_block_edit(self):
        self.song.tempo=121.
        with self.assertRaisesRegex(RuntimeError,'Темп'):
            self.begin()
        self.song.tempo=120.
        self.song.tracks[0].arrangement_clips[0].loop_start=.5
        with self.assertRaisesRegex(RuntimeError,'Смещение'):
            self.begin()
        self.song.tracks[0].arrangement_clips[0].loop_start=0.
        self.begin()
        self.song.record_mode=True
        with self.assertRaisesRegex(RuntimeError,'запись'):
            self.call('auto_arm')

    def test_older_auto_protocol_is_rejected(self):
        with patch.object(app,'bridge',return_value=dict(protocol=9,actions=['auto_begin'],version='0.6.0')):
            with self.assertRaisesRegex(RuntimeError,'старый'):
                app.require_replace_bridge()
