"""``acsoe console`` — serve the local read-only console.

The console is a **separate process** from the daemon. It shares nothing with it
but SQLite, holds no credentials, and cannot place an order. That is a security
property, not an implementation detail, so this entry point never constructs an
exchange client and never imports one.

The FastAPI application itself belongs to Agent C in ``src/acsoe/console/`` and
is built in Phase 1. This module asks for it and, until it exists, serves a
placeholder that answers a health check and says so. When C's app lands the
placeholder stops being used with no change here.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from acsoe.platform.config import Config, ConfigError, load_config
from acsoe.platform.logging import configure_logging, get_logger
from acsoe.platform.paths import ensure_runtime_directories

PLACEHOLDER_MESSAGE = (
    "The ACSOE console is a Phase 1 deliverable. This process is serving a "
    "placeholder so the entry point can be verified in Phase 0."
)


def build_placeholder_app(config: Config) -> Any:
    """A minimal app with a health endpoint, used until Phase 1.

    Deliberately built here rather than in ``src/acsoe/console/``: that package
    is Agent C's, and a placeholder written into it would have to be deleted by
    someone who did not write it.
    """
    from fastapi import FastAPI

    app = FastAPI(title="ACSOE console (placeholder)", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": config.mode,
            "console": "placeholder",
            "detail": PLACEHOLDER_MESSAGE,
        }

    return app


def build_app(config: Config) -> Any:
    """C's console app if it exists, otherwise the placeholder."""
    try:
        from acsoe.console.app import create_app
    except ImportError:
        return build_placeholder_app(config)
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

    log.info("console_starting", host=args.host, port=port, mode=config.mode)
    uvicorn.run(app, host=args.host, port=port, log_config=None)
    return 0
