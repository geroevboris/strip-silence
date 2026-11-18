"""OS events are mocked; no actual keys are sent in tests."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_automation

class TestNativeAutomation(unittest.TestCase):
    def test_process_resolution_is_by_bundle_id_then_mac_name(self):
        calls=[]
        def pretend(args, **kwargs):
            calls.append((args,kwargs))
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        result=native_automation.send_native_split(run=pretend,platform='darwin')
        self.assertTrue(result['ok'])
        script=calls[0][0][2]
        self.assertIn('bundle identifier is "com.ableton.live"',script)
        self.assertIn('name is "Live"',script)
        self.assertIn('name contains "Ableton Live"',script)
        self.assertIn('if (count of liveApps) is not 1',script)
        self.assertIn('frontmost of targetApp',script)
        self.assertIn('key code 49 using {command down, shift down}',script)
        self.assertIn('keystroke "e" using {command down}',script)
        self.assertEqual(len(calls),1)

    def test_permission_failure_mentions_monterey_controls(self):
        def blocked(*args,**kwargs):
            return SimpleNamespace(returncode=1,stdout='',stderr='Not authorized')
        with self.assertRaisesRegex(RuntimeError,'Универсальный доступ'):
            native_automation.send_native_split(run=blocked,platform='darwin')

    def test_missing_process_is_not_misreported_as_permissions(self):
        def missing(*args,**kwargs):
            return SimpleNamespace(returncode=1,stdout='',stderr='Expected 1 Ableton Live process; found 0.')
        with self.assertRaisesRegex(RuntimeError,'найти запущенный Live'):
            native_automation.send_native_split(run=missing,platform='darwin')

    def test_linux_does_not_send_keys(self):
        with self.assertRaisesRegex(RuntimeError,'macOS'):
            native_automation.send_native_split(platform='linux')

if __name__=='__main__':
    unittest.main()
