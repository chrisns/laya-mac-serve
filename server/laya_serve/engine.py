"""Model lifecycle for laya-serve.

The engine loads one Laya checkpoint on demand. It unloads the checkpoint after an
idle period, because the model holds about 1.6 GB of resident memory. The next request
loads it again.
"""

from __future__ import annotations

import gc
import logging
import os
import subprocess
import threading
import time
from typing import Any

from .config import MODEL_IDS, Config

log = logging.getLogger("laya_serve.engine")

# Map an OpenAI model identity onto a Laya checkpoint.
CHECKPOINTS: dict[str, str | None] = {
    "laya": None,
    "laya-multilingual": "multilingual",
    "laya-typed-decisions": "typed-decisions",
}
ROUTER_MODEL = "laya-router"
HF_REPO = "convaiinnovations/laya"


def fake_model_enabled() -> bool:
    return os.environ.get("LAYA_SERVE_FAKE_MODEL", "") not in ("", "0", "false", "no")


class ModelError(RuntimeError):
    """The model could not be loaded or could not answer."""


class LayaEngine:
    """Hold at most one loaded checkpoint and answer typed questions."""

    def __init__(self, config: Config):
        self.config = config
        self._lock = threading.RLock()
        self._agent: Any = None
        self._model_id: str | None = None
        self._device: str = "unloaded"
        self._loaded_at: float = 0.0
        self._last_used: float = 0.0
        self._error: str | None = None

    # -- lifecycle ---------------------------------------------------------

    def _build_agent(self, model_id: str) -> tuple[Any, str]:
        if fake_model_enabled():
            from .fake_backend import FakeAgent

            agent = FakeAgent(model_id)
            return agent, "fake"

        import laya  # imported late, because it pulls in PyTorch

        device = None if self.config.device == "auto" else self.config.device
        token = self.config.hf_token or None
        if model_id == ROUTER_MODEL:
            agent = laya.Router(device=device, token=token, max_loaded=1, preload=False)
            return agent, device or "auto"
        agent = laya.load(HF_REPO, subfolder=CHECKPOINTS[model_id], device=device, token=token)
        return agent, str(getattr(agent, "device", device or "auto"))

    def ensure_loaded(self, model_id: str) -> Any:
        if model_id not in MODEL_IDS:
            raise ModelError(f"Unknown model {model_id!r}. Known models: {', '.join(MODEL_IDS)}.")
        with self._lock:
            if self._agent is not None and self._model_id == model_id:
                self._last_used = time.time()
                return self._agent
            if self._agent is not None:
                log.info("switching model from %s to %s", self._model_id, model_id)
                self._drop()
            started = time.time()
            log.info("loading %s", model_id)
            try:
                agent, device = self._build_agent(model_id)
            except Exception as exc:  # noqa: BLE001 - reported to the caller
                self._error = f"{type(exc).__name__}: {exc}"
                log.exception("failed to load %s", model_id)
                raise ModelError(self._error) from exc
            self._agent = agent
            self._model_id = model_id
            self._device = str(device)
            self._loaded_at = time.time()
            self._last_used = self._loaded_at
            self._error = None
            log.info("loaded %s on %s in %.1fs", model_id, device, time.time() - started)
            return agent

    def _drop(self) -> None:
        agent = self._agent
        self._agent = None
        self._model_id = None
        self._device = "unloaded"
        self._loaded_at = 0.0
        if agent is not None and hasattr(agent, "unload"):
            try:
                agent.unload()
            except Exception:  # noqa: BLE001 - unload must never raise
                log.exception("agent unload failed")
        del agent
        gc.collect()
        self._empty_cache()

    @staticmethod
    def _empty_cache() -> None:
        if fake_model_enabled():
            return
        try:
            import torch

            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except Exception:  # noqa: BLE001 - best effort only
            pass

    def unload(self) -> bool:
        with self._lock:
            if self._agent is None:
                return False
            log.info("unloading %s", self._model_id)
            self._drop()
            return True

    def maybe_unload_idle(self, now: float | None = None) -> bool:
        """Unload when the model has been idle for longer than the setting."""
        timeout = self.config.idle_unload_seconds
        if timeout <= 0:
            return False
        with self._lock:
            if self._agent is None:
                return False
            now = now or time.time()
            if now - self._last_used < timeout:
                return False
        return self.unload()

    # -- inference ---------------------------------------------------------

    def predict(self, state: Any, questions: dict[str, Any], model_id: str) -> dict[str, Any]:
        agent = self.ensure_loaded(model_id)
        with self._lock:
            try:
                result = agent.predict(state, questions)
            except Exception as exc:  # noqa: BLE001 - reported to the caller
                log.exception("prediction failed")
                raise ModelError(f"{type(exc).__name__}: {exc}") from exc
            self._last_used = time.time()
        return result

    # -- reporting ---------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            loaded = self._agent is not None
            idle = time.time() - self._last_used if self._last_used else None
            return {
                "state": "error" if self._error else ("loaded" if loaded else "unloaded"),
                "model": self._model_id,
                "default_model": self.config.default_model,
                "device": self._device,
                "loaded_at": self._loaded_at or None,
                "last_used": self._last_used or None,
                "idle_seconds": round(idle, 1) if idle is not None else None,
                "idle_unload_seconds": self.config.idle_unload_seconds,
                "rss_mb": _rss_mb(),
                "peak_rss_mb": _peak_rss_mb(),
                "error": self._error,
                "fake_model": fake_model_enabled(),
            }


def _rss_mb() -> float | None:
    """Return the resident memory of this process in megabytes."""
    try:
        output = subprocess.run(
            ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout.strip()
        return round(int(output) / 1024, 1)
    except Exception:  # noqa: BLE001 - reporting only
        return None


def _peak_rss_mb() -> float | None:
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes. Linux reports kilobytes.
        divisor = 1024 * 1024 if os.uname().sysname == "Darwin" else 1024
        return round(usage / divisor, 1)
    except Exception:  # noqa: BLE001 - reporting only
        return None
