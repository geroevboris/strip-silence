"""The unit test mocks subprocess: it never sends keyboard events."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_automation


class TestNativeAutomation(unittest.TestCase):
    def test_only_live_shortcuts_are_dispatched(self):
        calls=[]
        def pretend(args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        result=native_automation.send_native_split(run=pretend, platform='darwin')
        self.assertTrue(result['ok'])
        script=calls[0][0][2]
        self.assertIn('name contains "Ableton Live"', script)
        self.assertIn('frontmost of targetApp', script)
        self.assertIn('key code 49 using {command down, shift down}', script)
        self.assertIn('keystroke "e" using {command down}', script)
        self.assertEqual(len(calls), 1)

    def test_accessibility_failure_shows_a_real_error(self):
        def blocked(*args, **kwargs):
            return SimpleNamespace(returncode=1, stdout='', stderr='Not authorized')
        with self.assertRaisesRegex(RuntimeError, 'Универсальный доступ'):
            native_automation.send_native_split(run=blocked, platform='darwin')

    def test_linux_does_not_send_keys(self):
        with self.assertRaisesRegex(RuntimeError, 'macOS'):
            native_automation.send_native_split(platform='linux')

if __name__ == '__main__':
    unittest.main()
