# Clear Silence 0.7.0

Silence removal for WAV clips in Ableton Live 12 Arrangement on macOS Apple Silicon.

[Инструкция на русском](README_RU.md) · [Download installer](https://github.com/geroevboris/strip-silence/releases/tag/v0.7.0-take-lanes)

Restores the original rendered-fragment replacement workflow. Kept PCM/float samples are copied without resampling; silent sections disappear from the main lane. Original WAV files are never overwritten. The native keyboard/AX Split + Mute experiment has been removed.

An enabled-by-default option stores the entire visible audio region of each processed clip in a new Take Lane before replacement. Copies keep their timeline position, gain and colour; existing lanes remain untouched. This is an audio backup, not a clone of all hidden clip properties. Unsupported Warp/Loop, pitch, envelopes and groove are skipped. Live's import fade settings apply to newly created clips. Disable the option for the original replacement-only workflow.

The warm charcoal/orange interface previews kept regions in amber and removed regions in muted lavender hatching. The app icon has true alpha transparency outside the rounded tile.

Protocol 12 exposes only status, list, preview and replace. Source identity and tempo are rechecked per clip. Each clip's backup and replacement share one Undo step. Import boundaries and neighbours are checked; failure rolls back the current clip and stops the batch. Files live in `~/Music/ClearSilence Output`; use Live's Collect All and Save when moving a Set.

Run `python -m unittest discover -s tests -v` and `PYTHONPATH=packaging python -m unittest discover -s packaging/tests -v`. CI additionally tests the UI and builds/verifies the frozen macOS app and PKG. Mock tests do not establish runtime compatibility with the user's Live installation.
