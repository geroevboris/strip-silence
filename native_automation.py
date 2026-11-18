"""Two-phase native Split: activate Arrangement, then dispatch after bridge ACK.

Physical macOS key codes work with Russian as well as Latin input sources.
The Edit menu's Cmd+E command must be enabled. No mouse coordinates, audio
rendering, clipboard operations or synthetic clip reconstruction are used.
"""
import subprocess
import sys

APPLESCRIPT = r'''
on splitCommand(targetApp)
    tell application "System Events"
        repeat with barItem in menu bar items of menu bar 1 of targetApp
            if exists menu 1 of barItem then
                repeat with commandItem in menu items of menu 1 of barItem
                    try
                        set commandChar to value of attribute "AXMenuItemCmdChar" of commandItem
                        set commandMods to value of attribute "AXMenuItemCmdModifiers" of commandItem
                        if (commandChar is "e" or commandChar is "E") and commandMods is 0 then
                            if not (enabled of commandItem) then
                                error "CS_SPLIT_DISABLED: " & (name of commandItem) number -2701
                            end if
                            return commandItem
                        end if
                    on error messageText number errorNumber
                        if errorNumber is -2701 then error messageText number errorNumber
                    end try
                end repeat
            end if
        end repeat
    end tell
    error "CS_SPLIT_MISSING: Live did not expose the Cmd+E menu command."
end splitCommand

on focusDescription(targetApp)
    tell application "System Events"
        try
            set focusedElement to value of attribute "AXFocusedUIElement" of targetApp
            set elementRole to role of focusedElement as text
            set elementDescription to description of focusedElement as text
            return elementRole & ": " & elementDescription
        on error
            return "AX focus unavailable"
        end try
    end tell
end focusDescription

on run argv
    set phase to item 1 of argv
    set expectedPID to item 2 of argv as integer
    set expectedFocus to item 3 of argv
    tell application "System Events"
        set liveApps to (every application process whose bundle identifier is "com.ableton.live")
        if (count of liveApps) is 0 then
            set liveApps to (every application process whose name is "Live")
        end if
        if (count of liveApps) is 0 then
            set liveApps to (every application process whose name contains "Ableton Live")
        end if
        if (count of liveApps) is not 1 then
            error "Expected 1 Ableton Live process; found " & (count of liveApps)
        end if
        set targetApp to item 1 of liveApps
        set livePID to unix id of targetApp
        if expectedPID is not 0 and livePID is not expectedPID then error "CS_LIVE_CHANGED"
        if phase is "prepare" then
            set frontmost of targetApp to true
            delay 0.2
        end if
        if not (frontmost of targetApp) then error "CS_FOCUS_LOST: Ableton Live is not frontmost."
        if phase is "prepare" then
            -- Live 12: focus Arrangement and activate its standby selection.
            key code 19 using {option down}
            delay 0.15
            if not (frontmost of targetApp) then error "CS_FOCUS_LOST"
            -- Move INSERT marker to the exact playhead set by the bridge.
            key code 49 using {command down, shift down}
            delay 0.15
        else if phase is not "split" then
            error "Unknown Clear Silence automation phase."
        end if
    end tell
    set focusInfo to my focusDescription(targetApp)
    if phase is "split" and focusInfo is not expectedFocus then error "CS_FOCUS_LOST: editor changed"
    try
        set splitItem to my splitCommand(targetApp)
    on error messageText number errorNumber
        error messageText & " [" & focusInfo & "]" number errorNumber
    end try
    if phase is "split" then
        tell application "System Events"
            if not (frontmost of targetApp) then error "CS_FOCUS_LOST"
            -- Key code E; do not use a layout-dependent keystroke string.
            key code 14 using {command down}
        end tell
    end if
    return (livePID as text) & tab & focusInfo
end run
'''


def _run_phase(phase, expected_pid=0, expected_focus="", run=None, platform=None):
    if (sys.platform if platform is None else platform) != 'darwin':
        raise RuntimeError('Автоматический Split требует macOS.')
    runner = subprocess.run if run is None else run
    try:
        result = runner(['/usr/bin/osascript', '-e', APPLESCRIPT,
                         phase, str(int(expected_pid)), expected_focus],
                        capture_output=True, text=True, timeout=22, check=False)
    except subprocess.TimeoutExpired:
        # Never resend Cmd+E: it may have already reached Live.
        raise RuntimeError('macOS не ответила на автоматизацию. Команда повторно не отправлена.')
    except OSError as exc:
        raise RuntimeError('AppleScript не запустился: %s' % exc)
    if result.returncode:
        details = (result.stderr or result.stdout or '').strip()[-700:]
        if 'Expected 1 Ableton Live process' in details:
            raise RuntimeError('Не удалось однозначно найти запущенный Live: ' + details)
        if any(word in details.lower() for word in (
                'not authorized', 'not allowed', 'assistive access',
                'не разрешено', '-1743', '-1719')):
            raise RuntimeError('macOS не разрешает управление Live. Разреши Clear Silence: '
                               'Универсальный доступ и Автоматизация → System Events. ' + details)
        if 'CS_SPLIT_DISABLED' in details or 'CS_SPLIT_MISSING' in details:
            raise RuntimeError('Live не разрешил Split в Arrangement. ' + details)
        if 'CS_FOCUS_LOST' in details or 'CS_LIVE_CHANGED' in details:
            raise RuntimeError('Фокус Live изменился; Split не отправлен. ' + details)
        raise RuntimeError('AppleScript не смог выполнить %s: %s' % (phase, details))
    fields = result.stdout.strip().split('\t', 1)
    try:
        pid = int(fields[0])
        if pid <= 0:
            raise ValueError()
    except (ValueError, IndexError):
        raise RuntimeError('macOS не подтвердила процесс Live; обработка остановлена.')
    return {'ok': True, 'pid': pid, 'focus': fields[1] if len(fields) > 1 else '',
            'phase': phase}


def prepare_native_split(run=None, platform=None):
    """Focus the editor and place the insert marker; never split here."""
    return _run_phase('prepare', run=run, platform=platform)


def send_native_split(prepared=None, run=None, platform=None):
    """Send exactly one Split after a separate bridge/transport check."""
    if prepared is None:  # Older single-cut diagnostic endpoint.
        prepared = prepare_native_split(run=run, platform=platform)
    return _run_phase('split', expected_pid=prepared['pid'],
                      expected_focus=prepared.get('focus',''), run=run, platform=platform)
