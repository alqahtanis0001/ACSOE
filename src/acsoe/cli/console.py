"""``acsoe console`` — serve the local read-only console.

The console is a **separate process** from the daemon. It shares nothing with it
but SQLite, holds no credentials, and cannot place an order. That is a security
property, not an implementation detail, so this entry point never constructs an
exchange client and never imports one.

The application object itself belongs to Agent C in ``src/acsoe/console/app.py``.
This module loads the config, prepares the runtime directories and logging, asks
C for the app, and hands it to uvicorn. There is deliberately **no fallback app
here**: an ``acsoe console`` that quietly served something other than the console
when C's module was missing would look healthy while being wrong, and a health
endpoint that can be answered by two different applications is a health endpoint
that proves nothing.
"""

from __future__ import annotations

import argparse
import sys

from fastapi import FastAPI

from acsoe.console.app import create_app
from acsoe.platform.config import Config, ConfigError, load_config
from acsoe.platform.logging import configure_logging, get_logger
from acsoe.platform.paths import ensure_runtime_directories


def build_app(config: Config) -> FastAPI:
    """C's console application, built over this process's validated config.

    A thin wrapper rather than a direct call at the use site, so a test can build
    the app and exercise ``/health`` without binding a port or starting uvicorn.
    """
    return create_app(config)


def run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"acsoe console: refusing to start.\n{exc}", file=sys.stderr)
        return 2

    paths = ensure_runtime_directories()
    configure_logging(
        log_dir=paths.logs,
        level=config.logging.level,
        retention_days=config.logging.retention_days,
        also_stderr=True,
    )
    log = get_logger("acsoe.console")

    # The port is `console.port` in config. The README's 127.0.0.1:8765 is that
    # key's default value, not a second source of truth.
    port = args.port if args.port is not None else config.console.port
    app = build_app(config)

    import uvicorn

    # `log_config=None` is deliberate. structlog is already configured by this
    # point and uvicorn's default dictConfig would reset the root logger,
    # replacing the JSON handler — and its redaction — with plain lines.
    log.info("console_starting", host=args.host, port=port, mode=config.mode)
    uvicorn.run(app, host=args.host, port=port, log_config=None)
    return 0
