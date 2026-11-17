# Clear Silence — macOS PKG packaging

Native Apple Silicon installer built on a macOS GitHub Actions runner using Apple's `pkgbuild`.

The installer installs a self-contained, PyInstaller-frozen `Clear Silence.app` into `/Applications` but does not modify any user home folder while Installer runs. On the first app launch (under the logged-in user), the app installs/updates the packaged `ClearSilenceBridge` Remote Script into `~/Music/Ableton/User Library/Remote Scripts/`, backing up an older copy.

- Runs without separately installing Python or pywebview on the user's Mac.
- Doesn't change Ableton's application files or touch audio projects.
- **Launch Clear Silence once to install the bridge**, then restart Ableton Live; choose `ClearSilenceBridge` as a Control Surface, MIDI Input and Output `None`.
- No code signing/notarization in this build, so macOS may show a security warning. Apple Developer ID signing and notarization must be added before wider distribution.
- Only the Apple Silicon (M1/M2/M3/M4) build is currently published.
- The bridge acts only when its Control Surface is enabled in Ableton Live.
- A macOS `.pkg` cannot be runtime-tested inside a Linux container; the macOS Actions build performs import tests and validates the package archive.

Build on a Mac with Xcode command-line tools, Python 3.11, `pyinstaller` and `pywebview` installed:

```bash
bash packaging/build_installer.sh
```

This project remains a prototype. **Test on a copy of the Ableton Set** before processing real sessions.
