"""Frozen Clear Silence app launcher. PKG installation never touches ~/Music."""
import runpy
import subprocess
import sys
from pathlib import Path

from bootstrap_bridge import BridgeInstallError, install_bridge


def show_message(title, message):
    """Best-effort native error/status dialog, without requiring GUI Python deps."""
    if sys.platform != 'darwin':
        print(title + ': ' + message, file=sys.stderr)
        return
    # AppleScript arguments are passed as argv; no user strings are interpolated.
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
    import webview
    assert app.APP_VERSION == '0.3.0'
    assert app.HTML.startswith('<!doctype html>')
    assert callable(audio.WavFile)
    assert callable(install_bridge)
    print('Clear Silence frozen application import check OK')
    raise SystemExit(0)

# The embedded bridge ships as an app resource. Run with ordinary user rights
# only after the macOS Installer has finished, never inside a PKG postinstall.
script = Path(sys.executable).parent.parent / 'Resources' / 'ClearSilenceBridge' / '__init__.py'
try:
    updated = install_bridge(script, Path.home())
except BridgeInstallError as exc:
    show_message('Clear Silence — ошибка настройки', str(exc))
    raise SystemExit(1) from exc

if updated:
    show_message('Clear Silence — установка завершена',
                 'Remote Script установлен. Полностью перезапусти Ableton Live '
                 'и выбери ClearSilenceBridge в настройках Control Surface.')

runpy.run_module('app', run_name='__main__')
