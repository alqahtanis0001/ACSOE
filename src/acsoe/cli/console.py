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
import os
import sys
from typing import Final

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


#: Addresses that reach this machine only.
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"})

#: The environment variable that says "I meant to expose this". Phase 8, operator ruling
#: 2026-09-21. Its *value* is not checked here — checking it is the token work the operator
#: deferred — so this is a deliberate act, not a security control.
CONSOLE_TOKEN_ENV: Final = "ACSOE_CONSOLE_TOKEN"

OFF_LOOPBACK_REFUSAL: Final = (
    "acsoe console: refusing to start.\n"
    "--host {host} is not a loopback address, and the console has no login: anyone who can "
    "reach that address can read the account and press Freeze or Close all.\n"
    "Bind it to 127.0.0.1 (the default), or set {env} to say you meant it.\n"
    "Setting {env} does not authenticate anything yet — the token check is not built — so "
    "only do it behind something that does."
)


def off_loopback_refusal(host: str, token: str | None) -> str | None:
    """The refusal text for an off-loopback bind with no token set, or `None` to proceed.

    A separate function so the rule can be tested without binding a port. **The console has
    no authentication at all**: loopback is what has been protecting it, and `--host 0.0.0.0`
    was one flag away from publishing the account and the kill switch to the network. This
    makes that a deliberate act rather than a typo.
    """
    if host.strip().lower() in LOOPBACK_HOSTS:
        return None
    if token and token.strip():
        return None
    return OFF_LOOPBACK_REFUSAL.format(host=host, env=CONSOLE_TOKEN_ENV)


def run(args: argparse.Namespace) -> int:
    refusal = off_loopback_refusal(str(args.host), os.environ.get(CONSOLE_TOKEN_ENV))
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 2

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
