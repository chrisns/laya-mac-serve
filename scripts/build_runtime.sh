#!/usr/bin/env bash
# Build the self-contained Python runtime that ships inside LayaServe.app.
#
# The runtime holds CPython, PyTorch, Laya and the HTTP server dependencies. The
# application never uses the Python of the user.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$REPO_ROOT/build}"
RUNTIME_DIR="$BUILD_DIR/runtime"
CACHE_DIR="${CACHE_DIR:-$BUILD_DIR/cache}"

# Pinned CPython from python-build-standalone. Update the version and the checksum together.
PYTHON_VERSION="3.12.14"
PYTHON_RELEASE="20260901"
PYTHON_ARCH="aarch64-apple-darwin"
PYTHON_SHA256="3ee3ee547cedfeb7c2b16b2b7156039f7b470bb8f857e226fd3d2eb11db83c76"
PYTHON_ASSET="cpython-${PYTHON_VERSION}+${PYTHON_RELEASE}-${PYTHON_ARCH}-install_only.tar.gz"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_RELEASE}/${PYTHON_ASSET}"

mkdir -p "$CACHE_DIR" "$BUILD_DIR"
ARCHIVE="$CACHE_DIR/$PYTHON_ASSET"

if [[ ! -f "$ARCHIVE" ]]; then
	echo "==> Downloading $PYTHON_ASSET"
	curl -fsSL "$PYTHON_URL" -o "$ARCHIVE.part"
	mv "$ARCHIVE.part" "$ARCHIVE"
fi

echo "==> Verifying the checksum"
ACTUAL="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
if [[ "$ACTUAL" != "$PYTHON_SHA256" ]]; then
	echo "Checksum mismatch for $PYTHON_ASSET" >&2
	echo "  expected $PYTHON_SHA256" >&2
	echo "  actual   $ACTUAL" >&2
	exit 1
fi

echo "==> Extracting the runtime"
rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR"
tar -xzf "$ARCHIVE" -C "$RUNTIME_DIR"
# The archive holds a single "python" directory.
PYTHON_BIN="$RUNTIME_DIR/python/bin/python3"
test -x "$PYTHON_BIN"

echo "==> Installing the dependencies"
"$PYTHON_BIN" -m pip install --quiet --upgrade pip
"$PYTHON_BIN" -m pip install --no-cache-dir -r "$REPO_ROOT/server/requirements-runtime.txt"

echo "==> Removing files that the application does not need"
SITE_PACKAGES="$("$PYTHON_BIN" -c 'import site; print(site.getsitepackages()[0])')"
find "$RUNTIME_DIR" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$RUNTIME_DIR" -name '*.pyc' -delete 2>/dev/null || true
rm -rf "$SITE_PACKAGES/torch/test" "$SITE_PACKAGES/torch/include" \
	"$SITE_PACKAGES/torch/utils/model_dump" "$SITE_PACKAGES"/*/tests 2>/dev/null || true
rm -rf "$RUNTIME_DIR/python/lib/python3.12/test" \
	"$RUNTIME_DIR/python/lib/python3.12/idlelib" \
	"$RUNTIME_DIR/python/lib/python3.12/tkinter" \
	"$RUNTIME_DIR/python/share/man" 2>/dev/null || true

echo "==> Checking that the runtime works"
"$PYTHON_BIN" -c 'import torch, laya, fastapi, uvicorn; print("torch", torch.__version__, "mps", torch.backends.mps.is_available())'

echo "==> Runtime size: $(du -sh "$RUNTIME_DIR/python" | cut -f1)"
