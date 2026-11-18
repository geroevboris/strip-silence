# Clear Silence v0.5.4 — native auto Split diagnostic

**Experimental diagnostic only, NOT working multitrack Strip Silence.** The user already confirmed that manual Cmd+E on a new muted test track creates two clips pointing to the original full WAV, and the right clip can be muted, unmuted and extended again.

This version tests keyboard automation of the native command using macOS System Events, still only on a muted temporary test track. It does not cut/overwrite WAVs and original Arrangement clips are not intended to change.

On a COPY of your Live Set: install PKG, launch Clear Silence to update the MIDI Remote Script, fully restart Live, select an unwarped/unlooped WAV, click **1. Подготовить тест Split**, select the *temporary test clip* in Live Arrangement, return to Clear Silence and click **2. Авто Split**. The bridge sets Live playhead to a target beat; macOS sends **Cmd+Shift+Space** to move the insert marker to the playhead, then **Cmd+E**. The bridge reads the real clip boundaries, checks the exact cut point and other tracks, and mutes the right test clip only if all checks pass. Check unmuting/revealing audio then click **3. Удалить тест**.

macOS Accessibility permission for Clear Silence / osascript may be required. If automation fails, manually split with Cmd+E and click **Проверить вручную**. If a non-test clip changes, do not save the copy of the Live Set; inspect Undo.

**Bulk operation on original tracks is still disabled.** The test must pass in real Ableton Live 12.4.6 before we build multi-boundary and multitrack processing.

Project acceptance criteria: https://github.com/geroevboris/strip-silence/issues/1
