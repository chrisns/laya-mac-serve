"""Tests for the HTTP routes."""

import json

import pytest
from fastapi.testclient import TestClient
from n8n_prompt import chat_request

from laya_serve.app import create_app
from laya_serve.config import MODEL_IDS, Config
from laya_serve.engine import LayaEngine

CATEGORIES = [
    ("Billing", "invoices, payments and refunds"),
    ("Technical", "bugs, outages and system errors"),
    ("Sales", "pricing and new contracts"),
]
EMAIL = "We were billed twice for March. Please refund the duplicate today."


def build_client(**overrides) -> TestClient:
    config = Config(**overrides)
    config.validate()
    return TestClient(create_app(config, LayaEngine(config)))


@pytest.fixture
def client():
    with build_client() as test_client:
        yield test_client


def parse_content(response) -> dict:
    content = response.json()["choices"][0]["message"]["content"]
    assert content.startswith("```json")
    return json.loads(content.split("\n", 1)[1].rsplit("\n```", 1)[0])


def test_health(client):
    assert client.get("/health").json()["ok"] is True


def test_models_lists_every_checkpoint(client):
    data = client.get("/v1/models").json()
    assert [m["id"] for m in data["data"]] == list(MODEL_IDS)
    assert data["object"] == "list"


def test_an_unknown_model_returns_404(client):
    response = client.get("/v1/models/gpt-4o")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"


def test_a_classification_returns_one_true_category(client):
    response = client.post("/v1/chat/completions", json=chat_request(EMAIL, CATEGORIES))
    assert response.status_code == 200
    payload = parse_content(response)
    assert set(payload) == {"Billing", "Technical", "Sales"}
    assert sum(1 for v in payload.values() if v) == 1
    assert all(isinstance(v, bool) for v in payload.values())


def test_the_response_has_the_openai_shape(client):
    body = client.post("/v1/chat/completions", json=chat_request(EMAIL, CATEGORIES)).json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["usage"]["total_tokens"] > 0
    assert body["model"] == "laya-typed-decisions"
    assert "category" in body["x_laya"]


def test_the_same_input_gives_the_same_answer(client):
    request = chat_request(EMAIL, CATEGORIES)
    first = parse_content(client.post("/v1/chat/completions", json=request))
    second = parse_content(client.post("/v1/chat/completions", json=request))
    assert first == second


def test_multi_label_can_return_several_true_categories(client):
    request = chat_request(EMAIL, CATEGORIES, multi_class=True, fallback="other")
    payload = parse_content(client.post("/v1/chat/completions", json=request))
    assert set(payload) == {"Billing", "Technical", "Sales", "fallback"}


def test_a_non_classification_request_returns_400(client):
    response = client.post(
        "/v1/chat/completions",
        json={"model": "laya", "messages": [{"role": "user", "content": "Write a poem."}]},
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "unsupported_request"
    assert "No JSON Schema" in error["message"]


def test_missing_messages_returns_400(client):
    assert client.post("/v1/chat/completions", json={"model": "laya"}).status_code == 400


def test_an_unknown_model_falls_back_to_the_default(client):
    request = chat_request(EMAIL, CATEGORIES, model="gpt-4o-mini")
    body = client.post("/v1/chat/completions", json=request).json()
    assert body["model"] == "laya-typed-decisions"


def test_streaming_returns_server_sent_events(client):
    request = chat_request(EMAIL, CATEGORIES)
    request["stream"] = True
    response = client.post("/v1/chat/completions", json=request)
    assert response.status_code == 200
    frames = [line for line in response.text.splitlines() if line.startswith("data: ")]
    assert frames[-1] == "data: [DONE]"
    first = json.loads(frames[0][6:])
    assert first["object"] == "chat.completion.chunk"
    assert "```json" in first["choices"][0]["delta"]["content"]


def test_the_native_classify_route(client):
    response = client.post(
        "/v1/classify",
        json={
            "state": {"subject": "Duplicate charge", "body": EMAIL},
            "questions": {
                "urgency": {
                    "type": "score",
                    "instructions": "How urgent?",
                    "criteria": ["low", "high"],
                },
                "refund": {"type": "noul", "instructions": "Does the writer want a refund?"},
            },
        },
    )
    assert response.status_code == 200
    answers = response.json()["answers"]
    assert answers["urgency"]["type"] == "score"
    assert 0.0 <= answers["refund"]["noul"] <= 1.0


def test_classify_rejects_an_empty_question_set(client):
    response = client.post("/v1/classify", json={"state": "hello", "questions": {}})
    assert response.status_code == 400


def test_the_api_key_is_enforced():
    with build_client(api_key="secret") as client:
        request = chat_request(EMAIL, CATEGORIES)
        assert client.post("/v1/chat/completions", json=request).status_code == 401
        bad = client.post(
            "/v1/chat/completions", json=request, headers={"Authorization": "Bearer wrong"}
        )
        assert bad.status_code == 401
        good = client.post(
            "/v1/chat/completions", json=request, headers={"Authorization": "Bearer secret"}
        )
        assert good.status_code == 200
        # The health route stays open, so the menu bar application can still poll it.
        assert client.get("/health").status_code == 200


def test_status_reports_the_loaded_model(client):
    assert client.get("/status").json()["state"] == "unloaded"
    client.post("/v1/chat/completions", json=chat_request(EMAIL, CATEGORIES))
    status = client.get("/status").json()
    assert status["state"] == "loaded"
    assert status["model"] == "laya-typed-decisions"
    assert status["fake_model"] is True


def test_unload_frees_the_model(client):
    client.post("/v1/chat/completions", json=chat_request(EMAIL, CATEGORIES))
    assert client.post("/admin/unload").json()["unloaded"] is True
    assert client.get("/status").json()["state"] == "unloaded"
    assert client.post("/admin/unload").json()["unloaded"] is False


def test_config_can_be_changed_at_run_time(client, tmp_path, monkeypatch):
    monkeypatch.setenv("LAYA_SERVE_HOME", str(tmp_path))
    response = client.post("/admin/config", json={"idle_unload_seconds": 60, "port": 6000})
    body = response.json()
    assert set(body["changed"]) == {"idle_unload_seconds", "port"}
    assert body["restart_required"] is True
    assert client.get("/status").json()["idle_unload_seconds"] == 60


def test_an_invalid_setting_is_corrected(client, tmp_path, monkeypatch):
    monkeypatch.setenv("LAYA_SERVE_HOME", str(tmp_path))
    client.post("/admin/config", json={"default_model": "not-a-model", "device": "quantum"})
    config = client.get("/admin/config").json()
    assert config["default_model"] == "laya-typed-decisions"
    assert config["device"] == "auto"
