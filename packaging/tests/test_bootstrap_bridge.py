import tempfile
from pathlib import Path
from unittest import TestCase

from bootstrap_bridge import BridgeInstallError, install_bridge


class BridgeBootstrapTests(TestCase):
    def test_first_install_then_noop(self):
        with tempfile.TemporaryDirectory() as work:
            home = Path(work) / 'home'
            home.mkdir()
            source = Path(work) / 'source.py'
            source.write_text('version=1')
            self.assertTrue(install_bridge(source, home))
            self.assertFalse(install_bridge(source, home))
            dst = home / 'Music/Ableton/User Library/Remote Scripts/ClearSilenceBridge/__init__.py'
            self.assertEqual(dst.read_text(), 'version=1')

    def test_update_keeps_backup(self):
        with tempfile.TemporaryDirectory() as work:
            home = Path(work) / 'home'
            home.mkdir()
            source = Path(work) / 'source.py'
            source.write_text('version=1')
            install_bridge(source, home)
            source.write_text('version=2')
            self.assertTrue(install_bridge(source, home))
            library = home / 'Music/Ableton/User Library'
            dst = library / 'Remote Scripts/ClearSilenceBridge/__init__.py'
            self.assertEqual(dst.read_text(), 'version=2')
            backups = list((library / '.ClearSilence Backups').glob('ClearSilenceBridge.backup.*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / '__init__.py').read_text(), 'version=1')

    def test_missing_source_never_modifies_home(self):
        with tempfile.TemporaryDirectory() as work:
            home = Path(work) / 'home'
            home.mkdir()
            with self.assertRaises(BridgeInstallError):
                install_bridge(Path(work) / 'missing.py', home)
            self.assertFalse((home / 'Music').exists())
