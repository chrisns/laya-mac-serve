"""Tests for the command line entry point."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent


def test_the_server_stops_when_its_parent_dies(tmp_path):
    """A killed parent must not leave the server holding the port."""
    env = {
        **os.environ,
        "LAYA_SERVE_FAKE_MODEL": "1",
        "LAYA_SERVE_HOME": str(tmp_path),
        "LAYA_SERVE_PORT": "5391",
        "PYTHONPATH": str(SERVER),
    }
    # A shell stands in for the application. The server is its child.
    parent = subprocess.Popen(
        [sys.executable, "-m", "laya_serve", "--watch-parent"],
        env=env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        assert parent.poll() is None, "the server should still run"
    finally:
        parent.send_signal(signal.SIGTERM)
        parent.wait(timeout=10)


def test_watch_parent_exits_when_the_parent_pid_changes(monkeypatch):
    from laya_serve.__main__ import watch_parent

    killed = []
    monkeypatch.setattr("laya_serve.__main__.os.getppid", lambda: 999_999)
    monkeypatch.setattr("laya_serve.__main__.os.kill", lambda pid, sig: killed.append(sig))
    watch_parent(parent_pid=1234, interval=0.01)
    deadline = time.time() + 3
    while not killed and time.time() < deadline:
        time.sleep(0.02)
    assert killed == [signal.SIGTERM]
