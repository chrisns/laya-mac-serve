#!/usr/bin/env bash
# Package LayaServe.app as a zip and a disk image for a GitHub release.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$REPO_ROOT/build}"
APP="$BUILD_DIR/LayaServe.app"
DIST_DIR="$BUILD_DIR/dist"
VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"

test -d "$APP"
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

echo "==> Making the zip"
ditto -c -k --keepParent --sequesterRsrc "$APP" "$DIST_DIR/LayaServe-$VERSION-arm64.zip"

echo "==> Making the disk image"
STAGING="$BUILD_DIR/dmg-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"
# Use ditto, because it keeps the metadata that the code signature covers.
ditto "$APP" "$STAGING/LayaServe.app"
ln -s /Applications "$STAGING/Applications"
codesign --verify --deep --strict "$STAGING/LayaServe.app"
echo "    the staged application still has a valid signature"
DMG="$DIST_DIR/LayaServe-$VERSION-arm64.dmg"

# hdiutil fails now and then on a busy build machine. Try again before giving up.
for attempt in 1 2 3; do
	if hdiutil create -volname "Laya Serve" -srcfolder "$STAGING" -ov -format UDZO "$DMG"; then
		break
	fi
	if [[ $attempt -eq 3 ]]; then
		echo "hdiutil failed three times." >&2
		exit 1
	fi
	echo "    hdiutil attempt $attempt failed. Trying again."
	hdiutil detach /Volumes/"Laya Serve" -force 2> /dev/null || true
	sleep 5
done
rm -rf "$STAGING"

echo "==> Wrote:"
ls -lh "$DIST_DIR"
