#!/usr/bin/env bash
# Assemble LayaServe.app from the Swift executable and the bundled Python runtime.
#
# Run scripts/build_runtime.sh and scripts/fetch_model.sh first. Set SKIP_RUNTIME=1 and
# SKIP_MODEL=1 to build a small application for a user interface test. That application
# cannot serve requests.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$REPO_ROOT/build}"
RUNTIME_DIR="$BUILD_DIR/runtime"
MODEL_DIR="${MODEL_DIR:-$BUILD_DIR/model}"
APP="$BUILD_DIR/LayaServe.app"
CONFIGURATION="${CONFIGURATION:-release}"

echo "==> Building the Swift executable"
swift build --package-path "$REPO_ROOT/app" -c "$CONFIGURATION" --arch arm64
BINARY="$(swift build --package-path "$REPO_ROOT/app" -c "$CONFIGURATION" --arch arm64 --show-bin-path)/LayaServe"
test -x "$BINARY"

echo "==> Assembling the bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BINARY" "$APP/Contents/MacOS/LayaServe"
cp "$REPO_ROOT/app/Resources/Info.plist" "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"

echo "==> Copying the server sources"
mkdir -p "$APP/Contents/Resources/server"
cp -R "$REPO_ROOT/server/laya_serve" "$APP/Contents/Resources/server/"
find "$APP/Contents/Resources/server" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> Copying the model"
if [[ -d "$MODEL_DIR" ]]; then
	cp -R "$MODEL_DIR" "$APP/Contents/Resources/model"
	echo "    $(du -sh "$APP/Contents/Resources/model" | cut -f1) of weights"
elif [[ "${SKIP_MODEL:-0}" == "1" ]]; then
	echo "    SKIP_MODEL=1, so the bundle holds no weights"
else
	echo "The model is missing. Run scripts/fetch_model.sh first." >&2
	exit 1
fi

if [[ "${SKIP_RUNTIME:-0}" != "1" ]]; then
	echo "==> Copying the Python runtime"
	test -d "$RUNTIME_DIR/python" || {
		echo "The runtime is missing. Run scripts/build_runtime.sh first." >&2
		exit 1
	}
	cp -R "$RUNTIME_DIR/python" "$APP/Contents/Resources/python"
else
	echo "==> SKIP_RUNTIME=1, so the bundle holds no Python runtime"
fi

echo "==> Signing the bundle"
# Every nested binary needs its own signature before the bundle signature.
if [[ "${SKIP_RUNTIME:-0}" != "1" ]]; then
	find "$APP/Contents/Resources/python" \( -name '*.so' -o -name '*.dylib' \) -print0 |
		xargs -0 -P 8 -n 32 codesign --force --sign - --timestamp=none 2>/dev/null || true
	find "$APP/Contents/Resources/python/bin" -type f -perm +111 -print0 |
		xargs -0 -n 16 codesign --force --sign - --timestamp=none 2>/dev/null || true
fi
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "    signature verified"

echo "==> Built $APP ($(du -sh "$APP" | cut -f1))"
