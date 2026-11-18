# Clear Silence

Clear Silence is a local macOS Apple Silicon utility for Ableton Live 12.

## v0.5.3 — native Arrangement Split test

**This is a diagnostic beta, not a working multitrack Strip Silence release.** Real Live 12.4.6 showed that changing Clip.loop_end/start_marker/end_marker did not resize the Arrangement clip. The old bulk editing path is deliberately blocked.

In this build:
1. Select an original unwarped/unlooped WAV in Clear Silence.
2. Click **1. Подготовить тест Split**. The bridge creates a *new muted temporary Arrangement track* containing the **full original WAV**.
3. In Ableton Arrangement, **click inside that test clip** and press **Cmd+E** to invoke Live's native Split.
4. Return to Clear Silence, click **2. Проверить Split + Mute**. The bridge verifies the two adjacent regions refer to the same WAV with no gap, and sets `Clip.muted` on the right **test clip**.
5. Try unmuting / extending the right clip in Live. Click **3. Удалить тест** to remove the test track.

**Use a COPY of the Live Set** for diagnostic testing. This prototype does not programmatically invoke Cmd+E yet; it isolates and verifies the native command before automation. It does not edit the selected original WAV or its Arrangement clips. No truncated WAV files are generated.

Development issue: https://github.com/geroevboris/strip-silence/issues/1

[Russian instructions](README_RU.md).
