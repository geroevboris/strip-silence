# Clear Silence v0.5.6 — Auto Split diagnostic

This patch fixes a real macOS Monterey process-discovery failure: Ableton Live runs as an application process named **Live**, not necessarily a name containing "Ableton Live". The previous AppleScript returned an invented accessibility suggestion on an AppleScript error -2700.

Now identify by exact bundle identifier com.ableton.live, fallback name Live, and then Ableton Live text, requiring exactly one process before sending Cmd+Shift+Space and Cmd+E. User permissions are already granted. Unit tests distinguish discovery from macOS TCC failures. macOS CI compiles the AppleScript with osacompile before building the PKG.

Still an isolated, muted test-track diagnostic. Do not process source clips. Test on a COPY of a Live Set; bulk operations remain disabled. See issue #1.
