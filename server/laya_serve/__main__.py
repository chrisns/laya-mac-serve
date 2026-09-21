"""Command line entry point. The macOS application starts the server this way."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time

from .config import Config, log_path


def configure_logging(to_file: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if to_file:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2)
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )


def watch_parent(parent_pid: int, interval: float = 5.0) -> None:
    """Exit when the parent process dies.

    The macOS application starts this server as a child. If the application is killed
    with SIGKILL, its shutdown handler never runs, and this server would keep the port
    for ever. A new application instance could then not bind to it.
    """

    def loop() -> None:
        while True:
            time.sleep(interval)
            if os.getppid() != parent_pid:
                logging.getLogger("laya_serve").warning(
                    "the parent process %s is gone, so the server stops", parent_pid
                )
                os.kill(os.getpid(), signal.SIGTERM)
                return

    thread = threading.Thread(target=loop, name="parent-watch", daemon=True)
    thread.start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="laya-serve")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--log-file", action="store_true", help="also write to the log file")
    parser.add_argument(
        "--watch-parent",
        action="store_true",
        help="stop when the process that started this server dies",
    )
    args = parser.parse_args(argv)

    configure_logging(args.log_file)
    config = Config.load()
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    config.validate()

    if args.watch_parent:
        parent = os.getppid()
        if parent > 1:
            watch_parent(parent)

    import uvicorn

    from .app import create_app

    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, log_config=None, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
