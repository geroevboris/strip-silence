import math, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from silence_math import settings_for_strength,regions_with_muted_gaps

class TestStrength(unittest.TestCase):
    def test_monotonic(self):
        levels=[settings_for_strength(x) for x in range(0,101,5)]
        self.assertLess(levels[0]['threshold'],levels[-1]['threshold'])
        for a,b in zip(levels,levels[1:]):
            self.assertLessEqual(a['threshold'],b['threshold'])
            self.assertGreaterEqual(a['min_silence_ms'],b['min_silence_ms'])
            self.assertGreaterEqual(a['padding_ms'],b['padding_ms'])
    def test_reject_invalid(self):
        for x in (-1,101,math.inf,float('nan')):
            with self.assertRaises(ValueError):settings_for_strength(x)

class TestNonDestructiveRegions(unittest.TestCase):
    def test_all_silence_mutes_original(self):
        self.assertEqual(regions_with_muted_gaps([],100,900),[(100,900,True)])
    def test_complete_coverage_and_mute(self):
        intervals=regions_with_muted_gaps([(180,250),(500,690)],100,900)
        self.assertEqual(intervals,[(100,180,True),(180,250,False),(250,500,True),(500,690,False),(690,900,True)])
    def test_short_edge_absorbed_into_sound(self):
        intervals=regions_with_muted_gaps([(105,250)],100,600,min_region_frames=10)
        self.assertEqual(intervals,[(100,250,False),(250,600,True)])
    def test_bad_ranges_rejected(self):
        for ranges in ([(150,200),(190,250)],[(100,700)],[(90,150)]):
            with self.assertRaises(ValueError):regions_with_muted_gaps(ranges,100,600)

if __name__=='__main__':unittest.main()
