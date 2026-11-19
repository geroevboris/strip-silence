Clear Silence 0.7.1 — wait for Live audio imports before checking boundaries.

Fixes a confirmed sequencing defect in 0.7.0: the bridge set Warp off and immediately validated clip geometry in the same Live event. Live documents Warp changes as deferred. This could reject a valid import using stale duration/marker values, including an original-audio backup in a Take Lane.

- Return control to Live between import, Warp conversion, full-file marker setup and validation. Never sleep on the Live main thread. Require separate unwarped observations before writing seconds-based markers.
- Use the generated WAV's exact frame count for the imported audio range. Keep boundary checks and backup-before-delete ordering, and roll back the current clip on an actual mismatch.
- Accept equivalent paths referring to the same file; do not reject aliases merely because their strings differ.
- Report the affected stage (Take Lane backup or numbered fragment), property, actual value, expected value and tolerance. Record failures in ~/Library/Logs/ClearSilence/clear-silence.log.
- Bound pending commands with deadlines; expired queued edits never start. Exceptions/timeouts pass through Undo and close the active transaction.

Close Clear Silence, install the PKG, launch it once to update ClearSilenceBridge, then fully restart both Live and Clear Silence. The interface should show 0.7.1; protocol 13 rejects the old 0.7.0 bridge. The interface design and silence detection settings are unchanged.

Validation: 37 Python tests plus 3 bridge installer tests, including deferred Warp state, early False getters, a conversion that never settles, full-file marker restoration, path aliases, detailed mismatch reporting, transaction rollback and per-event command dispatch. CI also verifies the interface and builds/tests the frozen macOS arm64 app. The reported 0.7.0 error did not identify its failing property, so this release addresses the confirmed sequencing defect without claiming the user's exact failing field has been observed. Actual Live runtime still requires verification.

API reference: https://docs.cycling74.com/apiref/lom/clip/ (warping technical note).
