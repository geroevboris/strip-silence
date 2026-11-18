"""Dispatch a native Split only to one confirmed running Ableton Live process.

On macOS the Ableton process often appears as "Live" even though the .app
bundle is named Ableton Live 12 Suite. Use bundle id first, name fallback.
"""
import subprocess
import sys

APPLESCRIPT = """
tell application "System Events"
    set liveApps to (every application process whose bundle identifier is "com.ableton.live")
    if (count of liveApps) is 0 then
        set liveApps to (every application process whose name is "Live")
    end if
    if (count of liveApps) is 0 then
        set liveApps to (every application process whose name contains "Ableton Live")
    end if
    if (count of liveApps) is not 1 then
        set candidates to (name of every application process whose name contains "Live")
        error "Expected 1 Ableton Live process; found " & (count of liveApps) & ". Live-like processes: " & (candidates as string)
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
        raise RuntimeError('macOS не ответила на автоматизацию. Проверь разрешения.')
    except OSError as exc:
        raise RuntimeError('AppleScript не запустился: %s' % exc)
    if result.returncode:
        details = (result.stderr or result.stdout or '').strip()[-700:]
        if 'Expected 1 Ableton Live process' in details or 'No unique Ableton Live process' in details:
            raise RuntimeError('Не удалось однозначно найти запущенный Live: ' + details)
        if any(word in details.lower() for word in ('not authorized', 'not allowed', 'assistive access', 'не разрешено')):
            raise RuntimeError('macOS не разрешает управление приложением: ' + details +
                               '. Проверь в Monterey: Защита и безопасность → Конфиденциальность → Универсальный доступ / Автоматизация.')
        raise RuntimeError('AppleScript не смог выполнить Split: ' + details)
    return {'ok': True, 'sent': ['Cmd+Shift+Space', 'Cmd+E']}
