# Clear Silence 0.6.2

Native Split + Mute utility for Ableton Live 12 on macOS Apple Silicon.
Select audio tracks, adjust Strength, and click **Разделить и заглушить**.
The app analyzes the original WAV, splits Arrangement clips with Live's own
command, verifies the resulting boundaries and source offsets, then mutes quiet
pieces. WAV files are not rewritten; muted pieces retain the original audio.

## Arrangement editing

1. Resolve the current fragment by source path and timeline range (indices change after splitting).
2. Set the track/detail clip and call `focus_view('Arranger')`. `detail_clip` alone is not proof of an Arrangement selection.
3. Set the exact playhead, wait for Live to acknowledge it, activate Arrangement with Option+2, then move the insert marker with Cmd+Shift+Space.
4. Open the Cmd+E menu before reading its enabled state. If still disabled, unfold the target track and perform one non-editing recovery: validate the focused track title by name, read its AX bounds and the observed Arrangement Editor bounds, and click inside that content row. Check the selected track and restore only the playhead; do not overwrite the clicked selection. A second prepare preserves that selection.
5. Require an enabled Split and a confirmed track/clip/position before sending physical key code 14. Never blindly repeat Split after a timeout.
6. Verify all expected boundaries, full source coverage, WAV path and source offsets within two source samples. Check other tracks AND neighbouring clips on the same track.
7. Apply Mute only after all boundaries pass. Mute changes are grouped in one undo step; native splits remain native Live edits. An interruption may leave completed splits in place.

The 0.6.1 report demonstrated that focus alone did not enable Split. This
release also refreshes the native menu and can establish an actual lane click.
The AX geometry recovery requires validation in actual Live 12.4.6. The regression suite models the editor; it
cannot establish real macOS focus behavior.

## Install

Use the latest PKG from Releases. Launch Clear Silence to install/update the
bridge, then fully restart Live. Select ClearSilenceBridge in Control Surface
with Input/Output None. Both components must be 0.6.2, protocol 11.
Allow Clear Silence in macOS Accessibility and Automation → System Events.
No screen capture is used. Detailed logs: `~/Library/Logs/ClearSilence/automation.log`.
The source `.app` launcher uses the root Python files; it has no stale embedded
copy of the old application. `packaging/build_installer.sh` builds the standalone app.

Supported analysis: available WAV files, Warp/Loop off, no clip envelopes,
groove or pitch changes, and a constant tempo over the analyzed material.
Already muted clips are skipped.

## Validation

`python -m unittest discover -s tests -v`

`PYTHONPATH=packaging python -m unittest discover -s packaging/tests -v`

macOS CI compiles AppleScript, runs tests, checks the frozen app, and builds the
PKG. Native OS events are always mocked in automated tests. See RELEASE_NOTES.md.

Navigation references:
- https://docs.cycling74.com/apiref/lom/application_view/
- https://help.ableton.com/hc/en-us/articles/12840878679452-New-Keyboard-Shortcuts-in-Live-12
- https://www.ableton.com/en/live-manual/12/accessibility-and-keyboard-navigation/
