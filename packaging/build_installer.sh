#!/bin/bash
# Build a self-contained native macOS app + real installer package.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=0.5.4
OUTPUT_DIR="$PWD/package-output"
ROOT="$PWD/package-build/root"
ICONSET="$PWD/package-build/ClearSilence.iconset"
ICNS="$PWD/package-build/ClearSilence.icns"
SOURCE_ICON="$PWD/packaging/assets/ClearSilenceIcon.png"
APPNAME='Clear Silence.app'

python3 -m unittest discover -s tests -v
PYTHONPATH=packaging python3 -m unittest discover -s packaging/tests -v

# Convert source artwork into a native macOS .icns with retina sizes.
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$SOURCE_ICON" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  twice=$((size * 2))
  sips -z "$twice" "$twice" "$SOURCE_ICON" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ICNS"

python3 -m PyInstaller --noconfirm --clean --windowed --onedir \
  --name 'Clear Silence' \
  --icon "$ICNS" \
  --osx-bundle-identifier 'local.clearsilence.app' \
  --add-data 'ui.html:.' \
  --collect-all webview \
  --hidden-import app \
  --hidden-import audio \
  --hidden-import silence_math \
  --hidden-import native_automation \
  packaging/launch_frozen.py

APP="$PWD/dist/$APPNAME"
test -f "$APP/Contents/Info.plist"
mkdir -p "$APP/Contents/Resources/ClearSilenceBridge"
cp ClearSilenceBridge/__init__.py "$APP/Contents/Resources/ClearSilenceBridge/__init__.py"

/usr/bin/python3 - "$APP/Contents/Info.plist" <<'PY'
import plistlib, sys
p=sys.argv[1]
with open(p,'rb') as f: d=plistlib.load(f)
d['CFBundleDisplayName']='Clear Silence'
d['CFBundleName']='Clear Silence'
d['CFBundleShortVersionString']='0.5.4'
d['CFBundleVersion']='0.5.4'
d['LSMinimumSystemVersion']='11.0'
with open(p,'wb') as f: plistlib.dump(d,f)
PY

codesign --force --deep --sign - "$APP"
codesign --verify --deep "$APP"
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
pkgutil --expand "$PKG" "$OUTPUT_DIR/expanded"
test -f "$OUTPUT_DIR/expanded/PackageInfo"
test ! -e "$OUTPUT_DIR/expanded/Scripts"
rm -rf "$OUTPUT_DIR/expanded"
shasum -a 256 "$PKG" > "$PKG.sha256"
echo "BUILT: $PKG"
