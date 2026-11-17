"""Regression for the empty-track-selection bug reported in v0.3.2."""
import math
import os
import struct
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app


class TestSelection(unittest.TestCase):
    def test_empty_indices_use_selected_audio_track_for_analysis_only(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'test.wav')
            rate = 8000
            with wave.open(src, 'wb') as f:
                f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate)
                data = [int(12000 * math.sin(i * .21)) if 1000 < i < 4500 else 0 for i in range(rate*2)]
                f.writeframes(struct.pack('<%dh' % len(data), *data))
            clip = {'index':0,'name':'Test','file_path':src,'start':16.,'end':20.,
                    'file_offset':0.,'file_end':2.,'warping':False,'looping':False,
                    'has_envelopes':False,'has_groove':False,'pitch_coarse':0,'pitch_fine':0}
            snapshot = {'ok':True,'tempo':120.,'selected_track_index':3,
                        'tracks':[{'index':3,'name':'Voice','clips':[clip]}]}
            with patch.object(app,'bridge',return_value=snapshot):
                plan = app.plan_batch({'track_indices':[], 'threshold':-40,
                                       'min_silence_ms':150, 'padding_ms':30})
            self.assertEqual(plan['replace_clips'], 1)
            self.assertGreater(plan['fragments'], 0)
            self.assertTrue(os.path.isfile(src))

    def test_no_selection_without_selected_audio_track_fails_safely(self):
        snapshot = {'ok':True,'tempo':120.,'selected_track_index':None,
                    'tracks':[{'index':4,'name':'Sound','clips':[{'index':0}]}]}
        with patch.object(app,'bridge',return_value=snapshot):
            with self.assertRaisesRegex(ValueError,'Не выбрана аудиодорожка'):
                app.plan_batch({'track_indices':[]})

if __name__=='__main__':
    unittest.main()
