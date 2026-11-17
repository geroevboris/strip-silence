# Clear Silence

Independent, local Ableton Live 12 utility for macOS (Apple Silicon).

**v0.5.2 is a safety-first compatibility probe, NOT a functioning bulk Strip Silence release.** The previous v0.5.1 produced Arrangement clips of incorrect length in real Live and aborted via Undo.

This build adds **Test region trimming**: using the currently chosen audio clip, the Remote Script creates a temporary *muted* audio track, tries both direct Arrangement placement and Session-to-Arrangement placement, changes region markers **after** placement, reads back the actual start/end times, and cleans up the temporary track. Your original audio track and WAV are not touched. Bulk editing is disabled until these real-world results establish a safe technique.

Install the PKG, restart Live, select `ClearSilenceBridge` as a Control Surface, select one WAV clip without Warp, and use **Проверить нарезку безопасно**. Please provide the resulting report.

Long-term requirement: non-destructive Split + Mute of silent intervals, with every region referencing the full source audio. See [issue #1](https://github.com/geroevboris/strip-silence/issues/1).

[Russian setup and limitations](README_RU.md).
