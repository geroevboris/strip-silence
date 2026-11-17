#!/bin/bash
# Build a fully self-contained macOS Apple Silicon app and its native .pkg.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=0.3.2
OUTPUT_DIR="$PWD/package-output"
ROOT="$PWD/package-build/root"
APPNAME='Clear Silence.app'

python3 -m unittest discover -s tests -v
PYTHONPATH=packaging python3 -m unittest discover -s packaging/tests -v
python3 -m PyInstaller --noconfirm --clean --windowed --onedir \
  --name 'Clear Silence' \
  --osx-bundle-identifier 'local.clearsilence.app' \
  --add-data 'ui.html:.' \
  --collect-all webview \
  --hidden-import app \
  --hidden-import audio \
  packaging/launch_frozen.py

APP="$PWD/dist/$APPNAME"
test -f "$APP/Contents/Info.plist"
# The bridge is a separate Python script that Live loads, not code inside
# the application's frozen interpreter.
mkdir -p "$APP/Contents/Resources/ClearSilenceBridge"
cp ClearSilenceBridge/__init__.py "$APP/Contents/Resources/ClearSilenceBridge/__init__.py"

/usr/bin/python3 - "$APP/Contents/Info.plist" <<'PY'
import plistlib, sys
p=sys.argv[1]
with open(p,'rb') as f: d=plistlib.load(f)
d['CFBundleDisplayName']='Clear Silence'
d['CFBundleName']='Clear Silence'
d['CFBundleShortVersionString']='0.3.2'
d['CFBundleVersion']='0.3.2'
d['LSMinimumSystemVersion']='11.0'
with open(p,'wb') as f: plistlib.dump(d,f)
PY

# Re-sign after changing Info.plist and adding the embedded Remote Script.
# This is an ad-hoc signature, NOT Apple Developer ID distribution signing.
codesign --force --deep --sign - "$APP"
codesign --verify --deep "$APP"

# Local build validation requires no Ableton: it confirms all Python modules
# are present in the self-contained executable.
"$APP/Contents/MacOS/Clear Silence" --self-test

rm -rf "$ROOT"
mkdir -p "$ROOT/Applications" "$OUTPUT_DIR"
ditto "$APP" "$ROOT/Applications/$APPNAME"
PKG="$OUTPUT_DIR/Clear_Silence_${VERSION}_macOS_Apple_Silicon.pkg"
pkgbuild --root "$ROOT" \
  --identifier 'local.clearsilence.installer' \
  --version "$VERSION" \
  --install-location / \
  "$PKG"
# Confirm metadata and verify that the installer can be expanded on macOS.
pkgutil --expand "$PKG" "$OUTPUT_DIR/expanded"
test -f "$OUTPUT_DIR/expanded/PackageInfo"
test ! -e "$OUTPUT_DIR/expanded/Scripts" # no privileged user-folder modification
rm -rf "$OUTPUT_DIR/expanded"
shasum -a 256 "$PKG" > "$PKG.sha256"
echo "BUILT: $PKG"
