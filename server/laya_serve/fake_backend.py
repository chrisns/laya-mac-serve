"""A deterministic stand-in for a Laya checkpoint.

Set LAYA_SERVE_FAKE_MODEL=1 to use it. Continuous integration uses it, so CI needs
neither PyTorch nor the 843 MB of weights. The answers are stable for a given input,
so tests can assert on them.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(*parts: str) -> int:
    joined = "\u0000".join(parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(joined).digest()[:8], "big")


def _unit(*parts: str) -> float:
    """A stable pseudo-random float in [0, 1)."""
    return (_digest(*parts) % 1_000_000) / 1_000_000.0


def _state_text(state: Any) -> str:
    if isinstance(state, str):
        return state
    if isinstance(state, dict):
        return "\n".join(f"{k}: {v}" for k, v in state.items())
    return json.dumps(state, sort_keys=True, default=str)


class FakeAgent:
    """Answer typed questions with stable made-up probabilities."""

    def __init__(self, model_id: str = "fake"):
        self.model_id = model_id
        self.device = "fake"

    def predict(self, state: Any, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        text = _state_text(state)
        answers: dict[str, Any] = {}
        for qid, question in questions.items():
            qtype = question.get("type", "choice")
            if qtype == "choice":
                answers[qid] = self._choice(text, qid, question)
            elif qtype == "score":
                answers[qid] = self._score(text, qid, question)
            else:
                answers[qid] = self._noul(text, qid)
        return {
            "model": f"fake-{self.model_id}",
            "answers": answers,
            "usage": {"input_tokens": max(1, len(text) // 4), "output_tokens": 0},
        }

    def _choice(self, text: str, qid: str, question: dict[str, Any]) -> dict[str, Any]:
        keys = list(question.get("criteria", {}).keys()) or ["unknown"]
        weights = [_unit(text, qid, key) + 0.01 for key in keys]
        total = sum(weights)
        probabilities = {k: round(w / total, 4) for k, w in zip(keys, weights, strict=True)}
        winner = max(probabilities, key=lambda k: probabilities[k])
        return {
            "type": "choice",
            "choice": winner,
            "probabilities": probabilities,
            "confidence": probabilities[winner],
            "action": {"act_probability": 0.99},
        }

    def _score(self, text: str, qid: str, question: dict[str, Any]) -> dict[str, Any]:
        levels = list(question.get("criteria", []) or ["low", "high"])
        weights = [_unit(text, qid, str(i)) + 0.01 for i in range(len(levels))]
        total = sum(weights)
        probabilities = {str(i): round(w / total, 4) for i, w in enumerate(weights)}
        score = sum(i * (w / total) for i, w in enumerate(weights))
        return {
            "type": "score",
            "score": round(score, 4),
            "legend": {str(i): level for i, level in enumerate(levels)},
            "probabilities": probabilities,
            "confidence": max(probabilities.values()),
            "action": {"act_probability": 0.99},
        }

    def _noul(self, text: str, qid: str) -> dict[str, Any]:
        probability = round(_unit(text, qid, "noul"), 4)
        return {
            "type": "noul",
            "noul": probability,
            "confidence": round(max(probability, 1.0 - probability), 4),
            "action": {"act_probability": 0.99},
        }

    def unload(self) -> None:
        return None
