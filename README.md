# Clear Silence

Personal Ableton Live 12 tool for splitting clips and muting silence while retaining the original WAV source. **Current: v0.5.0 beta, unverified in real Live.**

- One Strength dial and instantaneous local waveform prediction.
- Cyan = audible, magenta = muted.
- Python Remote Script + small standalone macOS WebKit window.
- Non-destructive *intent*: each generated clip links to the entire original WAV; gaps become muted clips, not removed audio.

**Safety:** always test on a copy of your Live Set first. Live's Session-to-Arrangement duplication behavior must be validated on the actual Mac before relying on the tool. See [README_RU.md](README_RU.md).
