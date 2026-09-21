"""Settings for laya-serve.

Settings live in a JSON file that both the Python server and the macOS menu bar
application read and write. Environment variables override the file.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

MODEL_IDS = ("laya", "laya-multilingual", "laya-typed-decisions", "laya-router")
DEFAULT_MODEL = "laya-typed-decisions"
DEFAULT_PORT = 5292


def support_dir() -> Path:
    override = os.environ.get("LAYA_SERVE_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "LayaServe"


def config_path() -> Path:
    return support_dir() / "config.json"


def log_path() -> Path:
    override = os.environ.get("LAYA_SERVE_LOG")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Logs" / "LayaServe" / "server.log"


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    api_key: str | None = None
    default_model: str = DEFAULT_MODEL
    idle_unload_seconds: int = 900
    device: str = "auto"
    multi_label_threshold: float = 0.5
    fallback_probability_floor: float = 0.35
    hf_token: str | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        path = path or config_path()
        data: dict[str, Any] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                data = {}
        known = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        cfg.apply_env()
        cfg.validate()
        return cfg

    def apply_env(self) -> None:
        env = os.environ
        if "LAYA_SERVE_HOST" in env:
            self.host = env["LAYA_SERVE_HOST"]
        if "LAYA_SERVE_PORT" in env:
            self.port = int(env["LAYA_SERVE_PORT"])
        if "LAYA_SERVE_API_KEY" in env:
            self.api_key = env["LAYA_SERVE_API_KEY"] or None
        if "LAYA_SERVE_MODEL" in env:
            self.default_model = env["LAYA_SERVE_MODEL"]
        if "LAYA_SERVE_IDLE_SECONDS" in env:
            self.idle_unload_seconds = int(env["LAYA_SERVE_IDLE_SECONDS"])
        if "LAYA_SERVE_DEVICE" in env:
            self.device = env["LAYA_SERVE_DEVICE"]
        if "HF_TOKEN" in env:
            self.hf_token = env["HF_TOKEN"]

    def validate(self) -> None:
        if self.default_model not in MODEL_IDS:
            self.default_model = DEFAULT_MODEL
        if self.device not in ("auto", "mps", "cpu", "cuda"):
            self.device = "auto"
        self.idle_unload_seconds = max(0, int(self.idle_unload_seconds))
        self.multi_label_threshold = min(1.0, max(0.0, float(self.multi_label_threshold)))
        self.fallback_probability_floor = min(1.0, max(0.0, float(self.fallback_probability_floor)))

    def save(self, path: Path | None = None) -> None:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")

    def update(self, data: dict[str, Any]) -> list[str]:
        """Apply known keys and return the names of the keys that changed."""
        known = {f.name for f in fields(self)}
        changed = []
        for key, value in data.items():
            if key not in known:
                continue
            if getattr(self, key) != value:
                setattr(self, key, value)
                changed.append(key)
        self.validate()
        return changed

    @property
    def exposed_without_key(self) -> bool:
        return self.host not in ("127.0.0.1", "localhost", "::1") and not self.api_key

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def new_api_key() -> str:
    return "laya-" + secrets.token_urlsafe(24)
