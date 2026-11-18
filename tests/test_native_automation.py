"""No OS events in tests, including on macOS CI."""
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_automation as native

class TestNativeAutomation(unittest.TestCase):
    def test_two_phase_handshake_binds_split_to_the_same_process(self):
        calls=[]
        def pretend(args, **kwargs):
            calls.append((args,kwargs))
            return SimpleNamespace(returncode=0,stdout='491\tAXGroup: Arrangement\n',stderr='')
        prepared=native.prepare_native_split(run=pretend,platform='darwin')
        self.assertEqual(prepared['pid'],491)
        self.assertEqual(calls[0][0][-3:],['prepare','0',''])
        native.send_native_split(prepared,run=pretend,platform='darwin')
        self.assertEqual(calls[1][0][-3:],['split','491','AXGroup: Arrangement'])
        script=calls[0][0][2]
        self.assertIn('key code 19 using {option down}',script)
        self.assertIn('key code 49 using {command down, shift down}',script)
        self.assertIn('key code 14 using {command down}',script)
        self.assertNotIn('keystroke "e"',script)
        self.assertIn('AXMenuItemCmdModifiers',script)
        self.assertIn('enabled of commandItem',script)

    def test_permission_failure_mentions_controls(self):
        def blocked(*args,**kwargs):
            return SimpleNamespace(returncode=1,stdout='',stderr='Not authorized -1743')
        with self.assertRaisesRegex(RuntimeError,'Универсальный доступ'):
            native.prepare_native_split(run=blocked,platform='darwin')

    def test_no_edit_on_disabled_split_or_foreground_change(self):
        for error in ('CS_SPLIT_DISABLED: Split','CS_FOCUS_LOST','CS_LIVE_CHANGED'):
            calls=[]
            def blocked(*args,**kwargs):
                calls.append(args)
                return SimpleNamespace(returncode=1,stdout='',stderr=error)
            with self.assertRaises(RuntimeError):
                native.send_native_split({'pid':491},run=blocked,platform='darwin')
            self.assertEqual(len(calls),1) # No blind retry of an edit.

    def test_timeout_does_not_retry_split(self):
        calls=[]
        def stalled(*args,**kwargs):
            calls.append(args)
            raise subprocess.TimeoutExpired('osascript',22)
        with self.assertRaisesRegex(RuntimeError,'повторно не отправлена'):
            native.send_native_split({'pid':491},run=stalled,platform='darwin')
        self.assertEqual(len(calls),1)

    def test_missing_process_is_not_misreported_as_permissions(self):
        def missing(*args,**kwargs):
            return SimpleNamespace(returncode=1,stdout='',stderr='Expected 1 Ableton Live process; found 0.')
        with self.assertRaisesRegex(RuntimeError,'найти запущенный Live'):
            native.prepare_native_split(run=missing,platform='darwin')

    def test_invalid_ack_is_rejected(self):
        def bad(*args,**kwargs):
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        with self.assertRaisesRegex(RuntimeError,'не подтвердила процесс'):
            native.prepare_native_split(run=bad,platform='darwin')

    def test_linux_does_not_send_keys(self):
        with self.assertRaisesRegex(RuntimeError,'macOS'):
            native.prepare_native_split(platform='linux')

if __name__=='__main__': unittest.main()
