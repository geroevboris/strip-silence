# Clear Silence v0.6.0 — one-button automatic native Split + Mute beta

Experimental Ableton Live 12 native audio-only Strip Silence utility for Apple Silicon, macOS Monterey and later.

## Workflow
Select one or more audio tracks; set the single Strength slider; click **Разделить и заглушить**. The app calculates every quiet/active region in the original WAV, issues native Arrangement splits at all computed boundaries (right to left), verifies each resulting audio clip's actual Arrangement position and WAV reference, and finally sets Clip.muted on silent regions. No source WAV is overwritten, shortened or rendered. Muted clips remain available for unmute and edge extension.

The app supports all selected tracks sequentially, provides a live progress display and an optional Stop command. If a split fails, processing stops and reports which boundary was not confirmed; the TEST Live Set may remain partially split. No automatic Undo is attempted.

## macOS permissions
For macOS Monterey 12: System Preferences → Security & Privacy → Privacy → Accessibility (Clear Silence); allow System Events in Privacy → Automation if prompted. The app sends keyboard shortcuts via macOS System Events, not screen capture, so Screen Recording permission is not needed; Full Disk Access is not needed by this workflow.

**Beta caveat:** CI has unit tests, but cannot prove reliable UI focus when making many successive cuts on actual Live 12.4.6. The tool validates every generated boundary before muting and can abort if the GUI selection is wrong. Use on a TEST Live Set until this is verified on the user's Mac M1.

Development record: https://github.com/geroevboris/strip-silence/issues/1.
