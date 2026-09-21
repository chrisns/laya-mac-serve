#!/usr/bin/env bash
# Classify a sample email with the real Laya checkpoint.
#
# This script downloads about 850 MB of model weights on the first run. The normal
# continuous integration run does not call it.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-5398}"
BUNDLED="$REPO_ROOT/build/runtime/python/bin/python3"
PYTHON="${PYTHON:-$([[ -x "$BUNDLED" ]] && echo "$BUNDLED" || echo python3)}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"; [[ -n "${SERVER_PID:-}" ]] && kill "$SERVER_PID" 2>/dev/null || true' EXIT

unset LAYA_SERVE_FAKE_MODEL || true
export LAYA_SERVE_HOME="$WORK"
export LAYA_SERVE_PORT="$PORT"
export PYTHONPATH="$REPO_ROOT/server"

echo "==> Starting the server with the real model"
"$PYTHON" -m laya_serve > "$WORK/server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
	if curl -fsS -m 1 "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then break; fi
	sleep 0.5
done
curl -fsS -m 2 "http://127.0.0.1:$PORT/health" > /dev/null || {
	cat "$WORK/server.log" >&2
	exit 1
}

echo "==> Classifying a billing email. The first call downloads the weights."
curl -fsS -m 1800 -X POST "http://127.0.0.1:$PORT/v1/chat/completions" \
	-H 'Content-Type: application/json' \
	-d @"$REPO_ROOT/server/tests/fixtures/n8n_text_classifier_request.json" \
	-o "$WORK/reply.json"

"$PYTHON" - "$WORK/reply.json" <<'PY'
import json
import sys

body = json.load(open(sys.argv[1]))
content = body["choices"][0]["message"]["content"]
payload = json.loads(content.split("\n", 1)[1].rsplit("\n```", 1)[0])
print("    answer:", json.dumps(payload))
print("    detail:", json.dumps(body["x_laya"]["category"]))
assert payload["Billing"] is True, "The billing email must classify as Billing."
assert payload["Technical"] is False
assert payload["Sales"] is False
assert payload["fallback"] is False
PY

echo "==> Checking the second call is fast"
START=$(date +%s%N)
curl -fsS -m 60 -X POST "http://127.0.0.1:$PORT/v1/chat/completions" \
	-H 'Content-Type: application/json' \
	-d @"$REPO_ROOT/server/tests/fixtures/n8n_text_classifier_request.json" > /dev/null
ELAPSED=$(( ($(date +%s%N) - START) / 1000000 ))
echo "    second call took ${ELAPSED} ms"

echo "==> Checking the status report"
curl -fsS "http://127.0.0.1:$PORT/status"
echo

echo "==> Real model test passed"
