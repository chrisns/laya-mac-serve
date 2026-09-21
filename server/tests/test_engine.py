"""Tests for the model lifecycle."""

import time

import pytest

from laya_serve.config import Config
from laya_serve.engine import LayaEngine, ModelError


@pytest.fixture
def engine():
    config = Config(idle_unload_seconds=900)
    return LayaEngine(config)


def test_the_model_loads_on_demand(engine):
    assert engine.status()["state"] == "unloaded"
    engine.ensure_loaded("laya")
    status = engine.status()
    assert status["state"] == "loaded"
    assert status["model"] == "laya"


def test_loading_a_second_model_replaces_the_first(engine):
    first = engine.ensure_loaded("laya")
    second = engine.ensure_loaded("laya-multilingual")
    assert first is not second
    assert engine.status()["model"] == "laya-multilingual"


def test_loading_the_same_model_reuses_it(engine):
    assert engine.ensure_loaded("laya") is engine.ensure_loaded("laya")


def test_an_unknown_model_raises(engine):
    with pytest.raises(ModelError):
        engine.ensure_loaded("gpt-4o")


def test_the_idle_timeout_unloads_the_model(engine):
    engine.config.idle_unload_seconds = 60
    engine.ensure_loaded("laya")
    assert engine.maybe_unload_idle(now=time.time() + 30) is False
    assert engine.status()["state"] == "loaded"
    assert engine.maybe_unload_idle(now=time.time() + 120) is True
    assert engine.status()["state"] == "unloaded"


def test_a_zero_timeout_never_unloads(engine):
    engine.config.idle_unload_seconds = 0
    engine.ensure_loaded("laya")
    assert engine.maybe_unload_idle(now=time.time() + 100_000) is False
    assert engine.status()["state"] == "loaded"


def test_a_prediction_resets_the_idle_clock(engine):
    engine.config.idle_unload_seconds = 60
    engine.ensure_loaded("laya")
    before = engine.status()["last_used"]
    time.sleep(0.01)
    engine.predict("hello", {"q": {"type": "noul", "instructions": "Is this a greeting?"}}, "laya")
    assert engine.status()["last_used"] > before


def test_unloading_an_unloaded_engine_is_safe(engine):
    assert engine.unload() is False


def test_status_reports_the_idle_seconds(engine):
    engine.ensure_loaded("laya")
    assert engine.status()["idle_seconds"] >= 0.0
