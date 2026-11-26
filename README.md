# Clear Silence 0.7.3

Silence removal for WAV clips in Ableton Live 12 Arrangement on macOS Apple Silicon.

[Инструкция на русском](README_RU.md) · [Download installer](https://github.com/geroevboris/strip-silence/releases/tag/v0.7.3-group-tracks)

Restores the original rendered-fragment replacement workflow. Kept PCM/float samples are copied without resampling; silent sections disappear from the main lane. Original WAV files are never overwritten. The native keyboard/AX Split + Mute experiment has been removed.

An enabled-by-default option stores the entire visible audio region of each processed clip in a new Take Lane before replacement. Copies keep their timeline position, gain and colour; existing lanes remain untouched. This is an audio backup, not a clone of all hidden clip properties. Unsupported Warp/Loop, pitch, envelopes and groove are skipped. Live's import fade settings apply to newly created clips. Disable the option for the original replacement-only workflow.

The warm charcoal/orange interface previews kept regions in amber and removed regions in bright coral fill/hatching with clear boundaries. Zoom buttons, direct waveform dragging and an overview navigator let you inspect down to a one-second window. Rendering max-pools the existing 10 ms analysis peaks, so zoom reveals real detail without rereading the audio. Totals and processing scope always cover the full clip/selected tracks. The app icon has true alpha transparency outside the rounded tile.

Audio tracks inside collapsed/nested groups are included normally. Select their children explicitly to process only that group; selecting a group header in Live is not a group-only scope and may cause the UI to choose All. Existing Take Lane clips are not analyzed or edited; supported comp clips on the main lane are processed normally.

Version 0.7.3 fixes listing projects with grouped tracks: group and non-audio headers are filtered before accessing arrangement_clips; child track indices remain unchanged. Listing failures are distinguished from connection failures. Install and launch the app to update the bridge, then fully restart Live and Clear Silence. Protocol 14 rejects older bridges before querying groups.

Protocol 14 exposes only status, list, preview and replace. Source identity and tempo are rechecked per clip. Each clip's backup and replacement share one Undo step. Import boundaries and neighbours are checked; failure rolls back the current clip and stops the batch. Files live in `~/Music/ClearSilence Output`; use Live's Collect All and Save when moving a Set.

Run `python -m unittest discover -s tests -v` and `PYTHONPATH=packaging python -m unittest discover -s packaging/tests -v`. CI additionally tests the UI and builds/verifies the frozen macOS app and PKG. Mock tests do not establish runtime compatibility with the user's Live installation.

The 0.7.1 bridge yields to Live between Warp conversion and duration checks, normalizes full-file markers in seconds only once Warp is off, and reports individual mismatching fields. Import requests have bounded deadlines and rollback through the same transaction handler. The app logs failures to `~/Library/Logs/ClearSilence/clear-silence.log`.
