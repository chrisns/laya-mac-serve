#!/usr/bin/env bash
# Start the server with the stub model and check a real n8n Text Classifier request.
#
# Set PYTHON to the interpreter to use. The default is the bundled runtime when it
# exists, and python3 otherwise.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-5399}"
BUNDLED="$REPO_ROOT/build/runtime/python/bin/python3"
PYTHON="${PYTHON:-$([[ -x "$BUNDLED" ]] && echo "$BUNDLED" || echo python3)}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"; [[ -n "${SERVER_PID:-}" ]] && kill "$SERVER_PID" 2>/dev/null || true' EXIT

export LAYA_SERVE_FAKE_MODEL=1
export LAYA_SERVE_HOME="$WORK"
export LAYA_SERVE_PORT="$PORT"
export PYTHONPATH="$REPO_ROOT/server"

echo "==> Starting the server on port $PORT with the stub model"
"$PYTHON" -m laya_serve > "$WORK/server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
	if curl -fsS -m 1 "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then break; fi
	sleep 0.5
done

if ! curl -fsS -m 2 "http://127.0.0.1:$PORT/health" > /dev/null; then
	echo "The server did not start. Log:" >&2
	cat "$WORK/server.log" >&2
	exit 1
fi

echo "==> GET /v1/models"
curl -fsS "http://127.0.0.1:$PORT/v1/models" | "$PYTHON" -c '
import json, sys
data = json.load(sys.stdin)
ids = [m["id"] for m in data["data"]]
assert ids == ["laya", "laya-multilingual", "laya-typed-decisions", "laya-router"], ids
print("    models:", ", ".join(ids))
'

echo "==> POST /v1/chat/completions with the recorded n8n request"
curl -fsS -X POST "http://127.0.0.1:$PORT/v1/chat/completions" \
	-H 'Content-Type: application/json' \
	-d @"$REPO_ROOT/server/tests/fixtures/n8n_text_classifier_request.json" \
	| "$PYTHON" -c '
import json, sys
body = json.load(sys.stdin)
assert body["object"] == "chat.completion", body
content = body["choices"][0]["message"]["content"]
assert content.startswith("```json"), content
payload = json.loads(content.split("\n", 1)[1].rsplit("\n```", 1)[0])
expected = {"Billing", "Technical", "Sales", "fallback"}
assert set(payload) == expected, payload
assert all(isinstance(v, bool) for v in payload.values()), payload
assert sum(payload.values()) == 1, payload
print("    classified:", json.dumps(payload))
'

echo "==> POST /v1/chat/completions with a request that is not a classification"
STATUS="$(curl -s -o "$WORK/error.json" -w '%{http_code}' -X POST \
	"http://127.0.0.1:$PORT/v1/chat/completions" -H 'Content-Type: application/json' \
	-d '{"model":"laya","messages":[{"role":"user","content":"Write a poem."}]}')"
test "$STATUS" = "400" || { echo "Expected 400, got $STATUS" >&2; exit 1; }
grep -q "unsupported_request" "$WORK/error.json"
echo "    rejected with 400"

echo "==> POST /admin/unload"
curl -fsS -X POST "http://127.0.0.1:$PORT/admin/unload" > /dev/null
curl -fsS "http://127.0.0.1:$PORT/status" | grep -q '"state":"unloaded"'
echo "    the model unloaded"

echo "==> Smoke test passed"
