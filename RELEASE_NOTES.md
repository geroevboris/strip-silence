Clear Silence 0.6.2 for macOS Apple Silicon — native Arrangement Split + Mute.

Addresses the reported 0.6.1 failure `CS_SPLIT_DISABLED: Split [AXStaticText: Arrangement Editor]`.

The Cmd+E menu is now opened before its enabled state is read, allowing native menu validation to run. If it remains disabled, Clear Silence unfolds the target track and initializes a genuine content-lane selection: Escape focuses the highlighted track title, its AX text is checked against the expected track name, and live title/editor bounds determine a click inside that row. There are no fixed screen coordinates. The bridge then checks the actual selected track and restores only the exact playhead. The subsequent insert-marker command preserves the clicked lane; it does not reactivate an unrelated standby selection. Split is sent only after a fresh enabled-menu and bridge check.

Recovery is attempted once before any edit. A wrong track, unknown editor, off-screen title, stale timing or still-disabled Split stops the operation. Permissions and timeouts never trigger blind edit retries.

Every resulting boundary and WAV offset is checked with a two-source-sample tolerance before silent fragments receive Clip.muted. Neighbouring clips on the same track are protected as well as other tracks. Source WAV files are never rewritten by this workflow. No clip recreation, rendering or deletion fallback is used. Muted pieces can be reactivated and their edges extended.

Install the PKG, launch Clear Silence once to update its bridge, then fully restart Ableton Live. Allow Clear Silence in macOS Accessibility and Automation → System Events if requested. The UI and bridge must both report 0.6.2 (protocol 11).

Validation: automated worker/bridge tests include seven clips across two tracks, sequential cuts, incorrect source offsets, incorrect boundaries, tempo/selection changes, cancellation and disabled Split. Native key events are mocked in tests. macOS CI compiles the AppleScript and builds/checks the frozen app. This is a beta: these checks do not establish successful UI operation in the user's Live 12.4.6. No Live instance is available in CI. An interrupted run can leave already completed native splits in the Set; native Undo remains available. The app does not claim sample-accurate operation until Live has returned matching boundaries.

The installer is ad-hoc signed, not notarized. Runtime details: ~/Library/Logs/ClearSilence/automation.log.
