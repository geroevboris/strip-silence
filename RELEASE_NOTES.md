Clear Silence 0.7.0 — silence removal, Take Lanes and a refreshed interface.

- Restored the original workflow: replace source clips on their existing tracks with sample-preserving WAV fragments; remove quiet intervals. Removed native Split, keyboard shortcuts and Accessibility automation.
- Optional original-audio backups in Take Lanes, enabled by default. Complete visible clip audio, including silence, is copied without resampling and verified before the main clip is removed. One new lane per processed track per run. Existing take lanes remain unchanged.
- Warm charcoal/orange interface; amber kept regions and lavender-grey hatching for removed regions. Instant slider preview. Transparent rounded app icon without an outer black square.
- Stop and Undo the current clip on an import/boundary/backup error. Preserve source WAVs and neighbouring clips. Cancellation stops after the current clip.

Install the PKG, launch Clear Silence once to update its bridge, then fully restart Ableton Live. Use Control Surface ClearSilenceBridge with Input/Output None. Both components must be 0.7.0 (protocol 12). No Accessibility setup is needed for processing.

To reveal originals: track header → Show Take Lanes → Clear Silence · Original · …. To restore audio: select the take material → Copy Selection to Main Lane. Backups are copies of the visible unwarped audio region with original gain, not complete clones of all Live clip metadata. Live's import fade settings apply. WAV only; Warp/Loop, pitch, envelopes and groove are skipped. For transferring a Set use Collect All and Save; generated files remain in ~/Music/ClearSilence Output.

Validation: sample-preserving WAV tests; seven clips on two tracks; trimmed sources; silent clips; backup-first ordering; import failures and rollback; neighbouring clips; cancellation; authenticated socket processing; UI interactions and rendering; macOS arm64 frozen-app import check and installer verification. Ableton Live itself is not available in CI, so Take Lanes runtime behaviour still requires confirmation on the user's installation.
