#!/usr/bin/env bash
# Download the Laya checkpoint that ships inside LayaServe.app.
#
# The application holds the weights, so it never talks to Hugging Face at run time.
# By default it fetches the typed-decisions checkpoint, which is about 810 MB.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$REPO_ROOT/build}"
MODEL_DIR="${MODEL_DIR:-$BUILD_DIR/model}"
CHECKPOINTS="${CHECKPOINTS:-typed-decisions}"
BUNDLED="$BUILD_DIR/runtime/python/bin/python3"
PYTHON="${PYTHON:-$([[ -x "$BUNDLED" ]] && echo "$BUNDLED" || echo python3)}"

mkdir -p "$MODEL_DIR"

echo "==> Fetching: $CHECKPOINTS"
MODEL_DIR="$MODEL_DIR" CHECKPOINTS="$CHECKPOINTS" "$PYTHON" - <<'PY'
import os
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

REPO = "convaiinnovations/laya"
target = Path(os.environ["MODEL_DIR"])
names = [n.strip() for n in os.environ["CHECKPOINTS"].split(",") if n.strip()]

for name in names:
    destination = target / name
    if (destination / "rl_agent_config.json").exists():
        print(f"    {name}: already present")
        continue
    patterns = None if name == "english" else [f"{name}/*"]
    print(f"    {name}: downloading")
    snapshot = Path(snapshot_download(REPO, allow_patterns=patterns))
    source = snapshot if name == "english" else snapshot / name
    if destination.exists():
        shutil.rmtree(destination)
    # Copy and follow the symbolic links of the cache, so the bundle holds real files.
    shutil.copytree(source, destination, symlinks=False, ignore=shutil.ignore_patterns(".*"))
    print(f"    {name}: copied to {destination}")

# Apply the tokenizer fix now. The bundle is signed and read only after that, so the
# model loader must not need to write to it.
from laya.agent import _fix_tokenizer_config  # noqa: E402

for name in names:
    _fix_tokenizer_config(str(target / name))
print("    tokenizer configuration fixed")
PY

echo "==> Checking that the checkpoint loads with no network"
MODEL_DIR="$MODEL_DIR" CHECKPOINTS="$CHECKPOINTS" "$PYTHON" - <<'PY'
import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import laya

name = os.environ["CHECKPOINTS"].split(",")[0].strip()
path = os.path.join(os.environ["MODEL_DIR"], name)
agent = laya.load(path, device="cpu")
result = agent.predict(
    {"body": "We were billed twice. Please refund the duplicate."},
    {
        "department": {
            "type": "choice",
            "instructions": "Which department should handle this?",
            "criteria": {"billing": "invoices and refunds", "technical": "bugs and outages"},
        }
    },
)
answer = result["answers"]["department"]
print("    choice:", answer["choice"], "probability:", answer["probabilities"][answer["choice"]])
assert answer["choice"] == "billing", answer
PY

echo "==> Model size: $(du -sh "$MODEL_DIR" | cut -f1)"
