"""Command line entry point. The macOS application starts the server this way."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="laya-serve")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--log-file", action="store_true", help="also write to the log file")
    args = parser.parse_args(argv)

    configure_logging(args.log_file)
    config = Config.load()
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    config.validate()

    import uvicorn

    from .app import create_app

    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, log_config=None, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
