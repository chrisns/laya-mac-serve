"""Translate OpenAI chat requests into Laya typed questions, and back.

The n8n Text Classifier node sends a system message that holds a JSON Schema, and a
user message that holds the text to classify. It parses the reply with the LangChain
``StructuredOutputParser``, so the reply must be a JSON object that matches the schema.

Laya does not generate text. It answers typed questions. This module maps one onto the
other. It imports no PyTorch, so the tests run without the model.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# A long option description eats the 192 token option budget of the model.
MAX_DESCRIPTION_CHARS = 240
FALLBACK_KEY = "fallback"
FALLBACK_LABEL_CANDIDATES = ("other", "none", "none_of_these", "unmatched", "no_category")

_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)
_CATEGORY_DESC_RE = re.compile(
    r'Should be true if the input has category "(?P<name>.*?)"'
    r"(?:\s*\(description:\s*(?P<desc>.*?)\s*\))?\s*$",
    re.DOTALL,
)
_FIX_PROMPT_RE = re.compile(
    r"Completion:\s*\n-+\n(?P<completion>.*?)\n-+\s*\n+Above, the Completion did not satisfy",
    re.DOTALL,
)


class UnsupportedRequest(Exception):
    """The request is not a classification that Laya can answer."""


class RepairedRequest(Exception):
    """The request is an output-fixing retry and the earlier answer is good."""

    def __init__(self, payload: dict[str, Any]):
        super().__init__("repaired earlier completion")
        self.payload = payload


@dataclass
class Category:
    key: str
    label: str
    description: str


@dataclass
class NumberField:
    key: str
    minimum: float
    maximum: float
    description: str
    is_integer: bool = False
    # "confidence" and "strength" come from the answer of the main question. Every other
    # number comes from its own noul question.
    derived: str | None = None


@dataclass
class EnumField:
    key: str
    values: list[str]
    description: str


@dataclass
class ClassificationRequest:
    text: str
    categories: list[Category] = field(default_factory=list)
    enums: list[EnumField] = field(default_factory=list)
    numbers: list[NumberField] = field(default_factory=list)
    multi_label: bool = False
    has_fallback: bool = False
    fallback_label: str = "other"
    schema: dict[str, Any] = field(default_factory=dict)


def message_text(message: dict[str, Any]) -> str:
    """Return the text of one OpenAI message. Handle string and content-part forms."""
    content = message.get("content")
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "\n".join(parts)
    return str(content)


def _iter_json_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in _FENCE_RE.finditer(text):
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
    return blocks


def _looks_like_schema(obj: dict[str, Any]) -> bool:
    return isinstance(obj.get("properties"), dict) and bool(obj["properties"])


def find_schema(text: str) -> dict[str, Any] | None:
    """Find the last JSON Schema in a block of prompt text."""
    candidates = [b for b in _iter_json_blocks(text) if _looks_like_schema(b)]
    if candidates:
        return candidates[-1]
    # Some clients send the schema without a markdown fence.
    for match in re.finditer(r"\{.*\}", text, re.DOTALL):
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and _looks_like_schema(parsed):
            return parsed
    return None


def _clean_description(raw: str) -> str:
    desc = " ".join(raw.split())
    if len(desc) > MAX_DESCRIPTION_CHARS:
        desc = desc[:MAX_DESCRIPTION_CHARS].rstrip() + "..."
    return desc


def _parse_category(key: str, spec: dict[str, Any]) -> Category:
    description = str(spec.get("description", "") or "")
    label = key
    match = _CATEGORY_DESC_RE.search(description.strip())
    if match:
        label = match.group("name") or key
        description = match.group("desc") or ""
    return Category(key=key, label=label, description=_clean_description(description))


def _pick_fallback_label(taken: set[str]) -> str:
    lowered = {t.lower() for t in taken}
    for candidate in FALLBACK_LABEL_CANDIDATES:
        if candidate not in lowered:
            return candidate
    return "none_of_the_above_option"


# These names have an obvious answer already, so they need no extra question.
DERIVED_NUMBER_KEYS = {
    "confidence": "confidence",
    "strength": "probability",
    "score": "probability",
}


def _parse_number(key: str, spec: dict[str, Any], is_integer: bool) -> NumberField:
    minimum = float(spec.get("minimum", 0.0))
    maximum = float(spec.get("maximum", 1.0))
    if maximum <= minimum:
        maximum = minimum + 1.0
    return NumberField(
        key=key,
        minimum=minimum,
        maximum=maximum,
        description=_clean_description(str(spec.get("description", "") or "")),
        is_integer=is_integer,
        derived=DERIVED_NUMBER_KEYS.get(key.lower()),
    )


def parse_schema(
    schema: dict[str, Any],
) -> tuple[list[Category], list[EnumField], list[NumberField], bool]:
    categories: list[Category] = []
    enums: list[EnumField] = []
    numbers: list[NumberField] = []
    has_fallback = False
    for key, spec in schema.get("properties", {}).items():
        if not isinstance(spec, dict):
            continue
        spec_type = spec.get("type")
        if isinstance(spec_type, list):
            spec_type = next((t for t in spec_type if t != "null"), None)
        if key == FALLBACK_KEY and spec_type == "boolean":
            has_fallback = True
            continue
        if spec_type == "boolean":
            categories.append(_parse_category(key, spec))
        elif spec_type == "string" and isinstance(spec.get("enum"), list) and spec["enum"]:
            enums.append(
                EnumField(
                    key=key,
                    values=[str(v) for v in spec["enum"]],
                    description=_clean_description(str(spec.get("description", "") or "")),
                )
            )
        elif spec_type in ("number", "integer"):
            numbers.append(_parse_number(key, spec, spec_type == "integer"))
    return categories, enums, numbers, has_fallback


def _check_repair(user_text: str, schema: dict[str, Any] | None) -> None:
    """Handle a LangChain OutputFixingParser retry without another model call."""
    match = _FIX_PROMPT_RE.search(user_text)
    if not match:
        return
    completion = match.group("completion")
    for block in _iter_json_blocks(completion) or _loose_objects(completion):
        if schema is None or _satisfies(block, schema):
            raise RepairedRequest(block)
    raise UnsupportedRequest("laya-serve received an output-fixing retry that it cannot repair.")


def _loose_objects(text: str) -> list[dict[str, Any]]:
    out = []
    for match in re.finditer(r"\{.*?\}", text, re.DOTALL):
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def _satisfies(obj: dict[str, Any], schema: dict[str, Any]) -> bool:
    props = schema.get("properties", {})
    if not props:
        return False
    return all(key in obj for key in props)


def extract_request(messages: list[dict[str, Any]]) -> ClassificationRequest:
    """Build a ClassificationRequest from OpenAI chat messages."""
    system_parts = []
    user_parts = []
    for message in messages:
        role = message.get("role")
        text = message_text(message)
        if role in ("system", "developer"):
            system_parts.append(text)
        elif role == "user":
            user_parts.append(text)
    system_text = "\n".join(system_parts)
    user_text = user_parts[-1] if user_parts else ""

    schema = find_schema(system_text) or find_schema(user_text)
    _check_repair(user_text, schema)

    if schema is None:
        raise UnsupportedRequest(
            "laya-serve only supports structured classification requests. "
            "No JSON Schema was found in the prompt."
        )

    categories, enums, numbers, has_fallback = parse_schema(schema)
    answerable_numbers = [n for n in numbers if not n.derived]
    if not categories and not enums and not answerable_numbers:
        raise UnsupportedRequest(
            "laya-serve found a JSON Schema with no boolean category, no string enum and "
            "no number field. Laya cannot generate free text."
        )
    if not user_text.strip():
        raise UnsupportedRequest("laya-serve found no text to classify in the request.")

    multi_label = "not mutually exclusive" in system_text.lower()
    taken = {c.label for c in categories}
    return ClassificationRequest(
        text=user_text,
        categories=categories,
        enums=enums,
        numbers=numbers,
        multi_label=multi_label,
        has_fallback=has_fallback,
        fallback_label=_pick_fallback_label(taken),
        schema=schema,
    )


def build_questions(req: ClassificationRequest) -> dict[str, dict[str, Any]]:
    """Build the Laya question set for one request."""
    questions: dict[str, dict[str, Any]] = {}
    if req.categories:
        if req.multi_label:
            for index, cat in enumerate(req.categories):
                # This wording scored best against the model. "Does this text belong to
                # the category X?" put the probability of a true category near 0.5.
                if cat.description:
                    instructions = (
                        f"Does this message concern {cat.label}, meaning {cat.description}?"
                    )
                else:
                    instructions = f"Does this message concern {cat.label}?"
                questions[f"cat_{index}"] = {"type": "noul", "instructions": instructions}
        else:
            criteria = {c.label: (c.description or c.label) for c in req.categories}
            if req.has_fallback:
                criteria[req.fallback_label] = "none of the other categories apply"
            questions["category"] = {
                "type": "choice",
                "instructions": "Which single category does this text belong to?",
                "criteria": criteria,
            }
    for index, enum_field in enumerate(req.enums):
        instructions = enum_field.description or f'Choose the value for "{enum_field.key}".'
        questions[f"enum_{index}"] = {
            "type": "choice",
            "instructions": instructions,
            "criteria": {value: value for value in enum_field.values},
        }
    for index, number in enumerate(req.numbers):
        if number.derived:
            continue
        instructions = number.description or f'How high is "{number.key}" for this text?'
        questions[f"num_{index}"] = {"type": "noul", "instructions": instructions}
    return questions


def render_answer(
    req: ClassificationRequest,
    answers: dict[str, Any],
    multi_label_threshold: float = 0.5,
    fallback_probability_floor: float = 0.35,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Turn Laya answers into the JSON object the caller expects.

    Returns the payload and a detail object with the probabilities.
    """
    payload: dict[str, Any] = {}
    detail: dict[str, Any] = {}
    # A "confidence" or "strength" property takes its value from the main question.
    primary: dict[str, float] = {"confidence": 0.0, "probability": 0.0}

    if req.categories:
        if req.multi_label:
            any_true = False
            for index, cat in enumerate(req.categories):
                answer = answers.get(f"cat_{index}", {})
                probability = float(answer.get("noul", 0.0))
                chosen = probability >= multi_label_threshold
                any_true = any_true or chosen
                payload[cat.key] = chosen
                detail[cat.key] = {
                    "probability": round(probability, 4),
                    "confidence": round(float(answer.get("confidence", 0.0)), 4),
                }
            if req.has_fallback:
                payload[FALLBACK_KEY] = not any_true
            best: dict[str, Any] = max(
                (answers.get(f"cat_{i}", {}) for i in range(len(req.categories))),
                key=lambda a: float(a.get("noul", 0.0)),
                default={},
            )
            primary["probability"] = float(best.get("noul", 0.0))
            primary["confidence"] = float(best.get("confidence", 0.0))
        else:
            answer = answers.get("category", {})
            probabilities = {k: float(v) for k, v in (answer.get("probabilities") or {}).items()}
            winner = answer.get("choice")
            confidence = float(answer.get("confidence", 0.0))
            # Laya reports an entropy based confidence. The winning probability is the
            # value a user expects, so the fallback test uses that instead.
            top_probability = probabilities.get(winner, 0.0) if winner else 0.0
            use_fallback = req.has_fallback and (
                winner == req.fallback_label or top_probability < fallback_probability_floor
            )
            for cat in req.categories:
                payload[cat.key] = (not use_fallback) and (winner == cat.label)
            if req.has_fallback:
                payload[FALLBACK_KEY] = use_fallback
            primary["confidence"] = confidence
            primary["probability"] = top_probability
            detail["category"] = {
                "choice": winner,
                "top_probability": round(top_probability, 4),
                "confidence": round(confidence, 4),
                "used_fallback": use_fallback,
                "probabilities": {k: round(v, 4) for k, v in probabilities.items()},
            }

    for index, enum_field in enumerate(req.enums):
        answer = answers.get(f"enum_{index}", {})
        choice = answer.get("choice")
        if choice not in enum_field.values:
            choice = enum_field.values[0]
        payload[enum_field.key] = choice
        enum_probabilities = {k: float(v) for k, v in (answer.get("probabilities") or {}).items()}
        if index == 0 and not req.categories:
            primary["confidence"] = float(answer.get("confidence", 0.0))
            primary["probability"] = enum_probabilities.get(choice, 0.0)
        detail[enum_field.key] = {
            "choice": choice,
            "confidence": round(float(answer.get("confidence", 0.0)), 4),
            "probabilities": {
                k: round(float(v), 4) for k, v in (answer.get("probabilities") or {}).items()
            },
        }

    for index, number in enumerate(req.numbers):
        if number.derived:
            value = primary.get(number.derived, 0.0)
        else:
            value = float(answers.get(f"num_{index}", {}).get("noul", 0.0))
        scaled = number.minimum + value * (number.maximum - number.minimum)
        # An integer property must not receive a decimal, because the parser rejects it.
        payload[number.key] = int(round(scaled)) if number.is_integer else round(scaled, 4)

    # Keep the property order of the schema, because it reads better in n8n.
    ordered = {key: payload[key] for key in req.schema.get("properties", {}) if key in payload}
    for key, value in payload.items():
        ordered.setdefault(key, value)
    return ordered, detail


def fence(payload: dict[str, Any]) -> str:
    """Wrap the answer in the markdown code block that StructuredOutputParser reads."""
    return "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
