Clear Silence 0.7.3 — fix grouped track listing.

Fixes “Main, Group and Return Tracks have no arrangement clips”. The bridge now skips group and non-audio headers before requesting clips, while retaining audio children of collapsed/nested groups and their original Live track indices.

The UI distinguishes project-list errors from a disconnected Live bridge. Older bridges are rejected before querying clips. Audio detection, replacement, Take Lane backups and waveform zoom are unchanged.

Close Clear Silence, install the PKG and open the app once to update the bridge. Then fully restart both Ableton Live and Clear Silence. Version 0.7.3 requires bridge protocol 14; this update DOES require restarting Live even when upgrading from 0.7.2.

Regression checks cover group headers whose clip access throws the reported exception, nested/collapsed groups, child-track indices, selected group headers, non-audio tracks, and separate connection/list/old-bridge UI states. Existing audio and packaging checks remain enabled. Tests use Live API doubles; actual Live runtime is not available on CI.
