"""Frozen Clear Silence app launcher. PKG installation never touches ~/Music."""
import runpy
import subprocess
import sys
from pathlib import Path

from bootstrap_bridge import BridgeInstallError, install_bridge


def show_message(title, message):
    if sys.platform != 'darwin':
        print(title + ': ' + message, file=sys.stderr)
        return
    source = ('on run argv\n'
              'display dialog (item 2 of argv) with title (item 1 of argv) '
              'buttons {"OK"} default button "OK"\n'
              'end run')
    try:
        subprocess.run(['/usr/bin/osascript', '-e', source, title, message],
                       capture_output=True, timeout=60, check=False)
    except Exception:
        pass


if '--self-test' in sys.argv:
    import app
    import audio
    import native_automation
    import webview
    assert app.APP_VERSION == '0.5.7'
    assert app.HTML.startswith('<!doctype html>')
    assert callable(native_automation.send_native_split)
    assert callable(audio.WavFile)
    assert callable(install_bridge)
    print('Clear Silence frozen application import check OK')
    raise SystemExit(0)

script = Path(sys.executable).parent.parent / 'Resources' / 'ClearSilenceBridge' / '__init__.py'
try:
    updated = install_bridge(script, Path.home())
except BridgeInstallError as exc:
    show_message('Clear Silence — ошибка настройки', str(exc))
    raise SystemExit(1) from exc

if updated:
    show_message('Clear Silence — обновление Remote Script',
                 'ClearSilenceBridge обновлён. Полностью перезапусти Ableton Live '
                 'и выбери ClearSilenceBridge в настройках Control Surface.')

runpy.run_module('app', run_name='__main__')
