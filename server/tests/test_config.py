"""Tests for the settings file."""

import json

from laya_serve.config import Config, new_api_key


def test_defaults():
    config = Config()
    assert config.host == "127.0.0.1"
    assert config.port == 5292
    assert config.default_model == "laya-typed-decisions"
    assert config.idle_unload_seconds == 900


def test_a_round_trip_through_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYA_SERVE_HOME", str(tmp_path))
    config = Config(port=6000, idle_unload_seconds=60)
    config.save()
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["port"] == 6000
    assert Config.load().idle_unload_seconds == 60


def test_environment_variables_win(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYA_SERVE_HOME", str(tmp_path))
    Config(port=6000).save()
    monkeypatch.setenv("LAYA_SERVE_PORT", "7000")
    assert Config.load().port == 7000


def test_an_unknown_key_in_the_file_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYA_SERVE_HOME", str(tmp_path))
    (tmp_path / "config.json").write_text(json.dumps({"port": 6001, "nonsense": True}))
    assert Config.load().port == 6001


def test_a_broken_file_falls_back_to_the_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYA_SERVE_HOME", str(tmp_path))
    (tmp_path / "config.json").write_text("{not json")
    assert Config.load().port == 5292


def test_a_network_bind_without_a_key_is_flagged():
    assert Config(host="0.0.0.0").exposed_without_key is True
    assert Config(host="0.0.0.0", api_key="k").exposed_without_key is False
    assert Config(host="127.0.0.1").exposed_without_key is False


def test_a_generated_key_is_long_enough():
    key = new_api_key()
    assert key.startswith("laya-")
    assert len(key) > 24
