"""The console application object — a **Phase 0 placeholder**.

`acsoe console` (Agent A, `cli/console.py`) imports `create_app` from here and hands
the resulting object to uvicorn. Spec 09 fixes what that object has to do in Phase 0
and nothing more: *"In Phase 0 the app is a placeholder; C builds it in Phase 1. It
must start and serve a health response."*

So this module is deliberately, aggressively small. Everything `ui-context.md`
describes — the status band, open positions, the cycle feed, the WebSocket that
pushes on a moving `updated_at` watermark, and the three commands — is **Phase 1**
and is not started here. Building any of it now would exceed spec 09's Scope Limits,
and it would be built against a database seeded by work that is still landing.

What this placeholder deliberately does *not* do, and why each one matters:

* **It opens no database connection.** The console is a separate process sharing
  only SQLite with the daemon; opening that file at import time would make
  `acsoe console` fail on a fresh clone that has not migrated yet, and would tie
  the entry point's liveness to B's schema.
* **It constructs no exchange client and reads no credential.** `ui-context.md`:
  "The console holds no credentials and can never place an order." That is a
  security property of the process, so the cheapest way to keep it true is for the
  console package to never import `clients/kraken/` at all.
* **It exposes no write path.** The three commands write rows to the `commands`
  table. There is no such endpoint here, so this process cannot change the
  daemon's state by any route.

The health payload's shape is not arbitrary: `status`, `mode` and `console` match
Agent A's fallback `build_placeholder_app` key-for-key, so the entry point behaves
identically whether or not this module exists. `console` reads `"placeholder"` in
Phase 0 and becomes `"ready"` when the Phase 1 console lands, which gives an
operator one field to look at to tell the two apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

if TYPE_CHECKING:  # pragma: no cover - typing only
    from acsoe.core.contracts import Config

__all__ = ["PLACEHOLDER_DETAIL", "create_app", "health_payload"]


PLACEHOLDER_DETAIL = (
    "Phase 0 placeholder. The console entry point starts and answers a health "
    "check; the status band, positions, cycle feed, WebSocket and commands are "
    "Phase 1."
)


def health_payload(config: Config) -> dict[str, Any]:
    """The body of `GET /health`.

    Split out from the route so a test can assert the payload without standing up
    an HTTP server, and so the *only* configuration this module touches is visible
    in one place: `config.mode`, and nothing else.

    `mode` is included because it is the one fact an operator checking liveness
    actually needs. It is read through the `Config` Protocol rather than an
    environment variable, so it can never disagree with what the daemon loaded.
    Reporting it here is not a live-mode switch: `trading-invariants.md` rule 1
    requires all three switches through `platform/live_guard.py`, and this console
    reads a value it can neither set nor promote.
    """
    return {
        "status": "ok",
        "mode": config.mode,
        "console": "placeholder",
        "phase": 0,
        "detail": PLACEHOLDER_DETAIL,
    }


def create_app(config: Config) -> FastAPI:
    """Build the console application.

    A factory rather than a module-level `app` object on purpose. A module-level
    instance would be constructed at import time, which means `import
    acsoe.console.app` — something `mypy`, `ruff` and any Phase 1 test will do —
    would build an application before a validated `Config` exists. The factory also
    lets a test pass a fake `Config` without touching `config/default.yaml`.

    `docs_url` and `redoc_url` are off. The console is a local operator instrument,
    not a public API, and an interactive schema browser on a read-only placeholder
    is surface with no reader.
    """
    app = FastAPI(
        title="ACSOE console",
        version="0",
        summary="Phase 0 placeholder. The operator console is built in Phase 1.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return health_payload(config)

    return app
