Clear Silence 0.7.2 — clearer waveform and zoom.

- Removed regions now have a brighter coral fill, diagonal hatching and explicit boundaries. Kept audio stays amber.
- Minus/plus zoom, Fit (Весь), direct dragging and a full-clip overview navigator. Inspect a window as small as one second, with millisecond time labels.
- The preview now renders the existing 10 ms analysis peaks at the visible scale instead of stretching the old 550-point overview. Strength changes retain the current view and update the cut regions immediately.
- Zoom and panning never restrict the batch or change the cleanup settings. Totals always describe the full clip. Loading another clip clears the old view immediately.
- Groups and Take Lanes behavior is documented: grouped audio tracks are included; existing take clips are left intact; main-lane comp clips are processed normally.

Close Clear Silence, install the PKG and open the app. Its interface should show 0.7.2. Updating from 0.7.1 does not require restarting Live: the bridge, protocol 13, audio detector and replacement engine are unchanged. Earlier bridge versions require the usual restart after the app updates the Remote Script.

Validation: Python regression tests, browser checks for zoom, pan, overview, reset, detailed peaks, live strength changes, loading state, unchanged processing scope and compact layout; macOS arm64 build and frozen-app import/signature/package checks. Actual Live runtime is not available on CI. Version 0.7.1's replacement workflow was confirmed working by the user.
