#!/bin/bash
# Build OmniServ.app — a self-contained, double-clickable macOS bundle with the
# engine inside. Ad-hoc signed (local use). Run: ./build-app.sh
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="OmniServ"
VERSION="${1:-${VERSION:-1.0.4}}"
DIST="dist"
APP="$DIST/$APP_NAME.app"

echo "▶ building release binary..."
swift build -c release
BIN="$(swift build -c release --show-bin-path)/$APP_NAME"
[ -x "$BIN" ] || { echo "✗ release binary not found"; exit 1; }

echo "▶ assembling $APP..."
# Keep Spotlight/LaunchServices from indexing the dev build as a 2nd "OmniServ" app
# (the installed copy in /Applications is the one users should see).
mkdir -p "$DIST"; : > "$DIST/.metadata_never_index"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/$APP_NAME"
# bundle the engine so the app does not depend on the dev checkout path
cp ../engine/omniserv "$APP/Contents/Resources/omniserv"
chmod +x "$APP/Contents/Resources/omniserv"
# app icon (regenerate with icon/make-icon.sh if missing)
if [ -f icon/AppIcon.icns ]; then
  cp icon/AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"
else
  echo "  (no icon/AppIcon.icns — run icon/make-icon.sh; building without icon)"
fi

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.emon.omniserv</string>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# LaunchAgent: launches OmniServ at login with --background (menu-bar-only, auto-starts
# services). Registered/unregistered from Settings via SMAppService.agent(plistName:).
mkdir -p "$APP/Contents/Library/LaunchAgents"
cat > "$APP/Contents/Library/LaunchAgents/com.emon.omniserv.helper.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.emon.omniserv.helper</string>
  <!-- Launch via LaunchServices (/usr/bin/open), NOT a direct exec of the binary.
       launchd exec'ing an ad-hoc-signed app trips a macOS code-signing Launch
       Constraint → SIGKILL. `open` honors the Gatekeeper approval and still passes
       --background through to the app. -->
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-a</string>
    <string>/Applications/$APP_NAME.app</string>
    <string>--args</string>
    <string>--background</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>LimitLoadToSessionType</key><string>Aqua</string>
</dict>
</plist>
PLIST

# Sign LAST — any edit after signing invalidates it ("damaged" on Apple Silicon).
echo "▶ ad-hoc codesign..."
codesign --force --deep --sign - "$APP" || codesign --force --sign - "$APP"
codesign --verify "$APP" || true
echo "✓ signature applied"

echo "✓ built $APP"
echo "  run:  open \"$PWD/$APP\""
echo "  install:  cp -R \"$APP\" /Applications/"
