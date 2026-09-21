"""HTTP routes for laya-serve.

The server speaks enough of the OpenAI chat completions protocol for the n8n Text
Classifier node. It also exposes a native endpoint for Laya typed questions.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse

from . import translator
from .config import MODEL_IDS, Config
from .engine import LayaEngine, ModelError

log = logging.getLogger("laya_serve.app")

IDLE_CHECK_SECONDS = 15


def openai_error(
    message: str,
    status: int = 400,
    err_type: str = "invalid_request_error",
    code: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": err_type, "param": None, "code": code}},
    )


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def create_app(config: Config | None = None, engine: LayaEngine | None = None) -> FastAPI:
    config = config or Config.load()
    engine = engine or LayaEngine(config)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if config.exposed_without_key:
            log.warning(
                "laya-serve listens on %s with no api_key. Anyone on the network can use it.",
                config.host,
            )
        task = asyncio.create_task(_idle_loop(engine))
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            engine.unload()

    app = FastAPI(title="laya-serve", version="0.1.0", docs_url="/docs", lifespan=lifespan)
    app.state.config = config
    app.state.engine = engine

    @app.middleware("http")
    async def _auth(request: Request, call_next: Any) -> Any:
        key = config.api_key
        if key and request.url.path.startswith(("/v1", "/admin")):
            header = request.headers.get("authorization", "")
            presented = header[7:] if header.lower().startswith("bearer ") else ""
            if presented != key:
                return openai_error(
                    "Incorrect API key provided.",
                    status=401,
                    err_type="invalid_request_error",
                    code="invalid_api_key",
                )
        return await call_next(request)

    # -- plain routes ------------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "version": app.version}

    @app.get("/status")
    async def status() -> dict[str, Any]:
        payload = engine.status()
        payload["host"] = config.host
        payload["port"] = config.port
        payload["api_key_set"] = bool(config.api_key)
        payload["exposed_without_key"] = config.exposed_without_key
        return payload

    @app.post("/admin/unload")
    async def admin_unload() -> dict[str, Any]:
        return {"unloaded": await run_in_threadpool(engine.unload)}

    @app.get("/admin/config")
    async def admin_get_config() -> dict[str, Any]:
        return config.as_dict()

    @app.post("/admin/config")
    async def admin_set_config(body: dict[str, Any]) -> dict[str, Any]:
        changed = config.update(body)
        config.save()
        # A change of device or default model must not keep a stale model resident.
        if "device" in changed:
            await run_in_threadpool(engine.unload)
        return {
            "changed": changed,
            "config": config.as_dict(),
            "restart_required": _needs_restart(changed),
        }

    # -- OpenAI routes -----------------------------------------------------

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        created = int(time.time())
        return {
            "object": "list",
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "created": created,
                    "owned_by": "convaiinnovations",
                }
                for model_id in MODEL_IDS
            ],
        }

    @app.get("/v1/models/{model_id}")
    async def get_model(model_id: str) -> Any:
        if model_id not in MODEL_IDS:
            return openai_error(
                f"The model {model_id!r} does not exist.", status=404, code="model_not_found"
            )
        return {
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "convaiinnovations",
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(body: dict[str, Any]) -> Any:
        messages = body.get("messages") or []
        if not isinstance(messages, list) or not messages:
            return openai_error("'messages' is required and must be a non-empty array.")

        model_id = body.get("model") or config.default_model
        if model_id not in MODEL_IDS:
            model_id = config.default_model

        detail: dict[str, Any] = {}
        try:
            request = translator.extract_request(messages)
        except translator.RepairedRequest as repaired:
            payload = repaired.payload
            detail = {"repaired": True}
            prompt_tokens = sum(approx_tokens(translator.message_text(m)) for m in messages)
            return _completion_response(body, model_id, payload, detail, prompt_tokens)
        except translator.UnsupportedRequest as exc:
            return openai_error(str(exc), code="unsupported_request")

        questions = translator.build_questions(request)
        try:
            result = await run_in_threadpool(engine.predict, request.text, questions, model_id)
        except ModelError as exc:
            return openai_error(str(exc), status=503, err_type="server_error", code="model_error")

        payload, detail = translator.render_answer(
            request,
            result.get("answers", {}),
            multi_label_threshold=config.multi_label_threshold,
            fallback_probability_floor=config.fallback_probability_floor,
        )
        detail["questions"] = questions
        prompt_tokens = int(
            result.get("usage", {}).get("input_tokens") or approx_tokens(request.text)
        )
        return _completion_response(body, model_id, payload, detail, prompt_tokens)

    def _completion_response(
        body: dict[str, Any],
        model_id: str,
        payload: dict[str, Any],
        detail: dict[str, Any],
        prompt_tokens: int,
    ) -> Any:
        content = translator.fence(payload)
        completion_id = "chatcmpl-" + uuid.uuid4().hex[:24]
        created = int(time.time())
        completion_tokens = approx_tokens(content)
        response = {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content, "refusal": None},
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "system_fingerprint": "laya-serve",
            "x_laya": detail,
        }
        if not body.get("stream"):
            return response
        return StreamingResponse(
            _stream(response, content),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # -- native route ------------------------------------------------------

    @app.post("/v1/classify")
    async def classify(body: dict[str, Any]) -> Any:
        state = body.get("state")
        questions = body.get("questions")
        if state is None or not isinstance(questions, dict) or not questions:
            return openai_error("'state' and a non-empty 'questions' object are required.")
        model_id = body.get("model") or config.default_model
        if model_id not in MODEL_IDS:
            return openai_error(
                f"The model {model_id!r} does not exist.", status=404, code="model_not_found"
            )
        try:
            result = await run_in_threadpool(engine.predict, state, questions, model_id)
        except ModelError as exc:
            return openai_error(str(exc), status=503, err_type="server_error", code="model_error")
        result["model"] = model_id
        return result

    return app


def _needs_restart(changed: list[str]) -> bool:
    return any(key in changed for key in ("host", "port", "api_key"))


async def _stream(response: dict[str, Any], content: str) -> AsyncIterator[bytes]:
    base = {
        "id": response["id"],
        "object": "chat.completion.chunk",
        "created": response["created"],
        "model": response["model"],
        "system_fingerprint": "laya-serve",
    }
    first = {
        **base,
        "choices": [
            {"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}
        ],
    }
    last = {
        **base,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": response["usage"],
    }
    yield f"data: {json.dumps(first)}\n\n".encode()
    yield f"data: {json.dumps(last)}\n\n".encode()
    yield b"data: [DONE]\n\n"


async def _idle_loop(engine: LayaEngine) -> None:
    while True:
        await asyncio.sleep(IDLE_CHECK_SECONDS)
        try:
            if await run_in_threadpool(engine.maybe_unload_idle):
                log.info("unloaded the model after the idle timeout")
        except Exception:  # noqa: BLE001 - the loop must keep running
            log.exception("idle check failed")
