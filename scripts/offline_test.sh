#!/usr/bin/env bash
# Classify a real email with the bundled weights and no network access.
#
# The test points every Hugging Face setting at an address that does not answer. A pass
# proves that the application needs no download at run time.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$REPO_ROOT/build}"
PORT="${PORT:-5397}"
MODEL_DIR="${MODEL_DIR:-$BUILD_DIR/model}"
BUNDLED="$BUILD_DIR/runtime/python/bin/python3"
PYTHON="${PYTHON:-$([[ -x "$BUNDLED" ]] && echo "$BUNDLED" || echo python3)}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"; [[ -n "${SERVER_PID:-}" ]] && kill "$SERVER_PID" 2>/dev/null || true' EXIT

test -f "$MODEL_DIR/typed-decisions/rl_agent_config.json" || {
	echo "The model is missing. Run scripts/fetch_model.sh first." >&2
	exit 1
}

unset LAYA_SERVE_FAKE_MODEL || true
export LAYA_SERVE_HOME="$WORK"
export LAYA_SERVE_PORT="$PORT"
export LAYA_SERVE_MODEL_DIR="$MODEL_DIR"
export PYTHONPATH="$REPO_ROOT/server"
# Point the Hugging Face cache and endpoint at nothing that works.
export HF_HOME="$WORK/hf-empty"
export HF_ENDPOINT="http://127.0.0.1:1"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

echo "==> Starting the server with the bundled weights and no network"
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

echo "==> Checking that the server reports a bundled checkpoint"
curl -fsS "http://127.0.0.1:$PORT/status" | grep -q '"laya-typed-decisions"'
echo "    the weights are inside the application"

echo "==> Classifying the recorded n8n request"
START=$(date +%s)
curl -fsS -m 600 -X POST "http://127.0.0.1:$PORT/v1/chat/completions" \
	-H 'Content-Type: application/json' \
	-d @"$REPO_ROOT/server/tests/fixtures/n8n_text_classifier_request.json" \
	-o "$WORK/reply.json"
echo "    the first call took $(( $(date +%s) - START )) seconds, including the model load"

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

echo "==> Checking that the second call is fast"
START=$(date +%s%N)
curl -fsS -m 60 -X POST "http://127.0.0.1:$PORT/v1/chat/completions" \
	-H 'Content-Type: application/json' \
	-d @"$REPO_ROOT/server/tests/fixtures/n8n_text_classifier_request.json" > /dev/null
echo "    the second call took $(( ($(date +%s%N) - START) / 1000000 )) ms"

echo "==> Checking the unload and load cycle"
curl -fsS -X POST "http://127.0.0.1:$PORT/admin/unload" > /dev/null
curl -fsS "http://127.0.0.1:$PORT/status" | grep -q '"state":"unloaded"'
curl -fsS -m 600 -X POST "http://127.0.0.1:$PORT/admin/load" -H 'Content-Type: application/json' -d '{}' > /dev/null
curl -fsS "http://127.0.0.1:$PORT/status" | grep -q '"state":"loaded"'
echo "    the model unloaded and loaded again"

echo "==> Offline test passed"
