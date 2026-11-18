"""Opt-in macOS keyboard dispatch for a temporary Ableton Arrangement clip.

The Bridge arms Live on its own main thread first; this host utility sends
only the two documented keyboard shortcuts, then returns for verification.
"""
import subprocess
import sys

APPLESCRIPT = """
tell application "System Events"
    set liveApps to (every application process whose name contains "Ableton Live")
    if (count of liveApps) is not 1 then
        error "No unique Ableton Live process was found."
    end if
    set targetApp to item 1 of liveApps
    set frontmost of targetApp to true
    delay 0.4
    if not (frontmost of targetApp) then
        error "Ableton Live is not frontmost."
    end if
    key code 49 using {command down, shift down}
    delay 0.3
    keystroke "e" using {command down}
end tell
"""

def send_native_split(run=None, platform=None):
    if (sys.platform if platform is None else platform) != 'darwin':
        raise RuntimeError('Автоматический Split требует macOS.')
    runner = subprocess.run if run is None else run
    try:
        result = runner(['/usr/bin/osascript', '-e', APPLESCRIPT],
                        capture_output=True, text=True, timeout=22, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError('macOS не ответила на автоматизацию. '
                           'Проверь разрешения Accessibility и Automation.')
    except OSError as exc:
        raise RuntimeError('AppleScript не запустился: %s' % exc)
    if result.returncode:
        details = (result.stderr or result.stdout or '').strip()[-700:]
        raise RuntimeError('macOS отклонила автоматизацию: ' + details +
                           '. Разреши Clear Silence/osascript управление '
                           'компьютером в Конфиденциальность и безопасность '
                           '→ Универсальный доступ.')
    return {'ok': True, 'sent': ['Cmd+Shift+Space', 'Cmd+E']}
