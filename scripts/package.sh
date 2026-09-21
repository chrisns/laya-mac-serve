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
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
hdiutil create -quiet -volname "Laya Serve" -srcfolder "$STAGING" -ov -format UDZO \
	"$DIST_DIR/LayaServe-$VERSION-arm64.dmg"
rm -rf "$STAGING"

echo "==> Wrote:"
ls -lh "$DIST_DIR"
