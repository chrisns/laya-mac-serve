"""Tests for the OpenAI to Laya translation."""

import json

import pytest
from n8n_prompt import chat_request, json_schema, output_fixing_message, system_message

from laya_serve import translator

CATEGORIES = [
    ("Billing", "invoices, payments and refunds"),
    ("Technical", "bugs, outages and system errors"),
    ("Sales", "pricing and new contracts"),
]
EMAIL = "We were billed twice for March. Please refund the duplicate today."


def test_extracts_categories_from_the_n8n_prompt():
    body = chat_request(EMAIL, CATEGORIES)
    req = translator.extract_request(body["messages"])
    assert req.text == EMAIL
    assert [c.key for c in req.categories] == ["Billing", "Technical", "Sales"]
    assert [c.label for c in req.categories] == ["Billing", "Technical", "Sales"]
    assert req.categories[0].description == "invoices, payments and refunds"
    assert req.multi_label is False
    assert req.has_fallback is False


def test_detects_the_fallback_property():
    body = chat_request(EMAIL, CATEGORIES, fallback="other")
    req = translator.extract_request(body["messages"])
    assert req.has_fallback is True
    assert "fallback" not in [c.key for c in req.categories]
    assert req.fallback_label == "other"


def test_detects_multi_label():
    body = chat_request(EMAIL, CATEGORIES, multi_class=True)
    req = translator.extract_request(body["messages"])
    assert req.multi_label is True


def test_picks_a_free_fallback_label():
    categories = [*CATEGORIES, ("other", "anything else")]
    body = chat_request(EMAIL, categories, fallback="other")
    req = translator.extract_request(body["messages"])
    assert req.fallback_label == "none"


def test_single_label_questions_include_the_fallback_option():
    body = chat_request(EMAIL, CATEGORIES, fallback="other")
    req = translator.extract_request(body["messages"])
    questions = translator.build_questions(req)
    assert list(questions) == ["category"]
    assert questions["category"]["type"] == "choice"
    assert list(questions["category"]["criteria"]) == [
        "Billing",
        "Technical",
        "Sales",
        "other",
    ]


def test_multi_label_builds_one_noul_question_per_category():
    body = chat_request(EMAIL, CATEGORIES, multi_class=True)
    req = translator.extract_request(body["messages"])
    questions = translator.build_questions(req)
    assert list(questions) == ["cat_0", "cat_1", "cat_2"]
    assert all(q["type"] == "noul" for q in questions.values())
    assert "Billing" in questions["cat_0"]["instructions"]


def test_renders_a_single_label_answer():
    body = chat_request(EMAIL, CATEGORIES)
    req = translator.extract_request(body["messages"])
    answers = {
        "category": {
            "type": "choice",
            "choice": "Billing",
            "probabilities": {"Billing": 0.83, "Technical": 0.06, "Sales": 0.11},
            "confidence": 0.54,
        }
    }
    payload, detail = translator.render_answer(req, answers)
    assert payload == {"Billing": True, "Technical": False, "Sales": False}
    assert detail["category"]["top_probability"] == 0.83


def test_a_low_probability_winner_becomes_the_fallback():
    body = chat_request(EMAIL, CATEGORIES, fallback="other")
    req = translator.extract_request(body["messages"])
    answers = {
        "category": {
            "choice": "Sales",
            "probabilities": {"Billing": 0.3, "Technical": 0.3, "Sales": 0.31, "other": 0.09},
            "confidence": 0.1,
        }
    }
    payload, _ = translator.render_answer(req, answers, fallback_probability_floor=0.35)
    assert payload == {
        "Billing": False,
        "Technical": False,
        "Sales": False,
        "fallback": True,
    }


def test_the_fallback_option_winning_sets_the_fallback_property():
    body = chat_request(EMAIL, CATEGORIES, fallback="other")
    req = translator.extract_request(body["messages"])
    answers = {
        "category": {
            "choice": "other",
            "probabilities": {"Billing": 0.1, "Technical": 0.1, "Sales": 0.1, "other": 0.7},
            "confidence": 0.6,
        }
    }
    payload, _ = translator.render_answer(req, answers)
    assert payload["fallback"] is True
    assert payload["Billing"] is False


def test_renders_a_multi_label_answer():
    body = chat_request(EMAIL, CATEGORIES, multi_class=True, fallback="other")
    req = translator.extract_request(body["messages"])
    answers = {
        "cat_0": {"noul": 0.9, "confidence": 0.9},
        "cat_1": {"noul": 0.2, "confidence": 0.8},
        "cat_2": {"noul": 0.61, "confidence": 0.61},
    }
    payload, _ = translator.render_answer(req, answers, multi_label_threshold=0.5)
    assert payload == {
        "Billing": True,
        "Technical": False,
        "Sales": True,
        "fallback": False,
    }


def test_multi_label_with_no_match_sets_the_fallback():
    body = chat_request(EMAIL, CATEGORIES, multi_class=True, fallback="other")
    req = translator.extract_request(body["messages"])
    answers = {f"cat_{i}": {"noul": 0.1, "confidence": 0.9} for i in range(3)}
    payload, _ = translator.render_answer(req, answers)
    assert payload["fallback"] is True


def test_the_payload_keeps_the_schema_property_order():
    body = chat_request(EMAIL, CATEGORIES, fallback="other")
    req = translator.extract_request(body["messages"])
    answers = {
        "category": {"choice": "Billing", "probabilities": {"Billing": 0.9}, "confidence": 0.9}
    }
    payload, _ = translator.render_answer(req, answers)
    assert list(payload) == ["Billing", "Technical", "Sales", "fallback"]


def test_a_string_enum_becomes_a_choice_question():
    schema = {
        "type": "object",
        "properties": {
            "sentiment": {
                "type": "string",
                "enum": ["Positive", "Neutral", "Negative"],
                "description": "How does the writer feel?",
            }
        },
    }
    messages = [
        {"role": "system", "content": "Classify.\n```json\n" + json.dumps(schema) + "\n```"},
        {"role": "user", "content": EMAIL},
    ]
    req = translator.extract_request(messages)
    questions = translator.build_questions(req)
    assert list(questions) == ["enum_0"]
    assert list(questions["enum_0"]["criteria"]) == ["Positive", "Neutral", "Negative"]
    payload, _ = translator.render_answer(
        req,
        {"enum_0": {"choice": "Negative", "probabilities": {"Negative": 0.7}, "confidence": 0.7}},
    )
    assert payload == {"sentiment": "Negative"}


def test_content_parts_are_joined():
    body = chat_request(EMAIL, CATEGORIES)
    body["messages"][1]["content"] = [{"type": "text", "text": EMAIL}]
    req = translator.extract_request(body["messages"])
    assert req.text == EMAIL


def test_a_prompt_with_no_schema_is_rejected():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write me a poem about ducks."},
    ]
    with pytest.raises(translator.UnsupportedRequest) as excinfo:
        translator.extract_request(messages)
    assert "No JSON Schema" in str(excinfo.value)


def test_a_schema_with_only_free_text_fields_is_rejected():
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string", "description": "a summary"}},
    }
    messages = [
        {"role": "system", "content": "```json\n" + json.dumps(schema) + "\n```"},
        {"role": "user", "content": EMAIL},
    ]
    with pytest.raises(translator.UnsupportedRequest) as excinfo:
        translator.extract_request(messages)
    assert "cannot generate free text" in str(excinfo.value)


def test_an_empty_input_is_rejected():
    body = chat_request("   ", CATEGORIES)
    with pytest.raises(translator.UnsupportedRequest):
        translator.extract_request(body["messages"])


def test_an_output_fixing_retry_returns_the_earlier_answer():
    schema = json_schema(CATEGORIES)
    instructions = system_message(CATEGORIES)
    completion = '```json\n{"Billing": true, "Technical": false, "Sales": false}\n```'
    messages = [
        {"role": "system", "content": instructions},
        {
            "role": "user",
            "content": output_fixing_message(instructions, completion, "Some parse error"),
        },
    ]
    with pytest.raises(translator.RepairedRequest) as excinfo:
        translator.extract_request(messages)
    assert excinfo.value.payload == {"Billing": True, "Technical": False, "Sales": False}
    assert set(schema["properties"]) == set(excinfo.value.payload)


def test_an_unrepairable_retry_is_rejected():
    instructions = system_message(CATEGORIES)
    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": output_fixing_message(instructions, "not json at all", "bad")},
    ]
    with pytest.raises(translator.UnsupportedRequest):
        translator.extract_request(messages)


def test_a_long_description_is_truncated():
    long_description = "word " * 200
    body = chat_request(EMAIL, [("Billing", long_description)])
    req = translator.extract_request(body["messages"])
    assert len(req.categories[0].description) <= translator.MAX_DESCRIPTION_CHARS + 3


def test_the_fence_is_parseable():
    text = translator.fence({"Billing": True})
    assert text.startswith("```json\n")
    assert json.loads(text.split("\n", 1)[1].rsplit("\n```", 1)[0]) == {"Billing": True}


def test_the_sentiment_analysis_schema_is_answerable():
    from n8n_prompt import sentiment_request

    body = sentiment_request(EMAIL)
    req = translator.extract_request(body["messages"])
    assert [e.key for e in req.enums] == ["sentiment"]
    assert [n.key for n in req.numbers] == ["strength", "confidence"]
    # Both numbers come from the choice, so they need no extra question.
    assert all(n.derived for n in req.numbers)
    questions = translator.build_questions(req)
    assert list(questions) == ["enum_0"]

    payload, _ = translator.render_answer(
        req,
        {
            "enum_0": {
                "choice": "Negative",
                "probabilities": {"Positive": 0.1, "Neutral": 0.2, "Negative": 0.7},
                "confidence": 0.55,
            }
        },
    )
    assert payload == {"sentiment": "Negative", "strength": 0.7, "confidence": 0.55}
    assert set(payload) == set(sentiment_request(EMAIL) and ["sentiment", "strength", "confidence"])


def test_a_plain_number_field_gets_its_own_question():
    schema = {
        "type": "object",
        "properties": {
            "urgency": {
                "type": "number",
                "minimum": 0,
                "maximum": 10,
                "description": "How urgent is this message?",
            }
        },
    }
    messages = [
        {"role": "system", "content": "```json\n" + json.dumps(schema) + "\n```"},
        {"role": "user", "content": EMAIL},
    ]
    req = translator.extract_request(messages)
    questions = translator.build_questions(req)
    assert questions == {"num_0": {"type": "noul", "instructions": "How urgent is this message?"}}
    payload, _ = translator.render_answer(req, {"num_0": {"noul": 0.5, "confidence": 0.5}})
    assert payload == {"urgency": 5.0}


def test_a_number_field_alone_is_not_rejected():
    schema = {"type": "object", "properties": {"risk": {"type": "number"}}}
    messages = [
        {"role": "system", "content": "```json\n" + json.dumps(schema) + "\n```"},
        {"role": "user", "content": EMAIL},
    ]
    assert translator.extract_request(messages).numbers[0].key == "risk"


def test_a_derived_number_alone_is_rejected():
    # Nothing here can be classified, so the request must fail loudly.
    schema = {"type": "object", "properties": {"confidence": {"type": "number"}}}
    messages = [
        {"role": "system", "content": "```json\n" + json.dumps(schema) + "\n```"},
        {"role": "user", "content": EMAIL},
    ]
    with pytest.raises(translator.UnsupportedRequest):
        translator.extract_request(messages)
