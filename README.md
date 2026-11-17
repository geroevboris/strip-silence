# Clear Silence

Personal Ableton Live 12 tool for splitting clips and muting silence while retaining the original WAV source. **Current: v0.5.1 beta, unverified in real Live.**

- One Strength dial and instantaneous local waveform prediction.
- Cyan = audible, magenta = muted.
- Python Remote Script + small standalone macOS WebKit window.
- Non-destructive *intent*: each generated clip links to the entire original WAV; gaps become muted clips, not removed audio.

**Safety:** always test on a copy of your Live Set first. Live's Session-to-Arrangement duplication behavior must be validated on the actual Mac before relying on the tool. See [README_RU.md](README_RU.md).

## v0.5.1: Session marker fix

Arrangement duplication derives the length of an unlooped Session clip from `start_marker` and `end_marker`, not only `loop_start` and `loop_end`. The bridge now updates both pairs, validates the Session region before removing the Arrangement original, then verifies the inserted clips. Protocol 4 refuses old bridge 0.5.0 until Live restarts. Still test on a copy of the Live Set.
