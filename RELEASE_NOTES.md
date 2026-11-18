Clear Silence 0.6.1 for macOS Apple Silicon — native Arrangement Split + Mute.

Fixes the missing Arrangement activation in 0.6.0. Each boundary now reselects its source fragment, focuses the Live API's `Arranger` view, activates its standby selection with Option+2, transfers the exact playhead to the insert marker, checks the enabled Cmd+E menu command, rechecks the bridge state, and sends one physical Cmd+E key event. Russian/Latin keyboard input no longer changes the E event. A changed foreground process or focused editor stops dispatch.

Every resulting boundary and WAV offset is checked with a two-source-sample tolerance before silent fragments receive Clip.muted. Neighbouring clips on the same track are protected as well as other tracks. Source WAV files are never rewritten by this workflow. No clip recreation, rendering or deletion fallback is used. Muted pieces can be reactivated and their edges extended.

Install the PKG, launch Clear Silence once to update its bridge, then fully restart Ableton Live. Allow Clear Silence in macOS Accessibility and Automation → System Events if requested. The UI and bridge must both report 0.6.1 (protocol 10).

Validation: automated worker/bridge tests include seven clips across two tracks, sequential cuts, incorrect source offsets, incorrect boundaries, tempo/selection changes, cancellation and disabled Split. Native key events are mocked in tests. macOS CI compiles the AppleScript and builds/checks the frozen app. This is a beta: these checks do not establish successful UI operation in the user's Live 12.4.6. No Live instance is available in CI. An interrupted run can leave already completed native splits in the Set; native Undo remains available. The app does not claim sample-accurate operation until Live has returned matching boundaries.

The installer is ad-hoc signed, not notarized. Runtime details: ~/Library/Logs/ClearSilence/automation.log.
