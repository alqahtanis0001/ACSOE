"""The Phase 0 console placeholder starts and answers a health check. Spec 09.

Driven through the **ASGI interface directly**, not through
`fastapi.testclient.TestClient`. That is not a stylistic preference. `TestClient`
subclasses `httpx.Client`, and `tests/harness/network_guard.py` patches
`httpx.Client.send` for every test in this repository — so a `TestClient` request
raises `NetworkAccessError` before it reaches the in-process transport. The
choices were to weaken the guard for the convenience of one test, or to call the
application the way uvicorn calls it. Spec 14 forbids the first in as many words,
and the second is a truer test anyway: it exercises the real routing, the real
endpoint function and the real JSON encoder, with no HTTP client and no socket
anywhere in the path.

What is deliberately asserted here is as much about what the console *is not* as
what it is. The console holds no credentials and can never place an order
(`ui-context.md`), so the placeholder having no write route and no client
construction is a property worth a test rather than a comment.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from acsoe.console.app import PLACEHOLDER_DETAIL, create_app, health_payload


class _StubConfig:
    """The narrowest thing satisfying the `Config` Protocol.

    Written here rather than reusing the `paper_config` fixture on purpose: this
    test must run on a tree where `config/default.yaml` is absent, and it proves
    `create_app` needs nothing from the configuration but `mode`. If a later
    change made the console read a threshold at construction time, this stub would
    raise `KeyError` and say which key.
    """

    def __init__(self, mode: str = "paper") -> None:
        self._mode = mode

    @property
    def mode(self) -> Any:
        return self._mode

    def get(self, dotted_key: str, /) -> Any:
        raise KeyError(
            f"the Phase 0 console placeholder must not read config; it asked for {dotted_key!r}"
        )


async def _asgi_get(app: Any, path: str) -> tuple[int, dict[str, Any]]:
    """Call an ASGI app the way a server does, and decode one JSON response."""
    sent: list[dict[str, Any]] = []

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"console.test")],
        "client": ("test", 0),
        "server": ("console.test", 80),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)

    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, json.loads(body) if body else {}


@pytest.mark.asyncio
async def test_health_is_served() -> None:
    """Spec 09's whole Phase 0 requirement: it starts and serves a health response."""
    status, body = await _asgi_get(create_app(_StubConfig()), "/health")
    assert status == 200
    assert body["status"] == "ok"
    assert body["mode"] == "paper"
    assert body["console"] == "placeholder"
    assert body["detail"] == PLACEHOLDER_DETAIL


@pytest.mark.asyncio
async def test_health_reports_the_configured_mode() -> None:
    """The mode comes from the injected config, never from an environment read.

    A console that reported a mode of its own could disagree with the daemon about
    whether real money is at risk, which is the one thing the status band exists to
    say. `trading-invariants.md` rule 1 keeps the switches in `platform/`; this only
    echoes what it was handed.
    """
    _, body = await _asgi_get(create_app(_StubConfig(mode="replay")), "/health")
    assert body["mode"] == "replay"


def test_health_payload_reads_only_the_mode() -> None:
    """`_StubConfig.get` raises, so any other config read fails loudly here."""
    assert health_payload(_StubConfig())["mode"] == "paper"


def test_the_placeholder_exposes_nothing_but_health() -> None:
    """Scope Limits, made executable.

    The Phase 1 console has a status band, a cycle feed, a WebSocket and three
    command endpoints. None of them are Phase 0 work, and a route appearing here
    ahead of its phase is the failure this asserts against. `/openapi.json` is off
    too — a schema browser on a read-only placeholder is surface with no reader.
    """
    app = create_app(_StubConfig())
    paths = {getattr(route, "path", None) for route in app.routes}
    assert paths == {"/health"}


def test_the_console_constructs_no_client_and_opens_no_database() -> None:
    """The console holds no credentials and cannot place an order.

    That is a property of the process, so the cheapest way to keep it true is for
    the module to import nothing that could reach the exchange or the command
    table. Asserted on the module's own import statements rather than on runtime
    behaviour, because behaviour only proves the path was not taken *this* time,
    while an absent import proves it cannot be taken at all.
    """
    import ast
    import pathlib

    import acsoe.console.app as module

    source = pathlib.Path(str(module.__file__)).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)

    forbidden = {
        name
        for name in imported
        if name.startswith(("acsoe.clients", "acsoe.platform")) or name in {"sqlite3", "os"}
    }
    assert forbidden == set(), (
        f"the Phase 0 console placeholder must not import {sorted(forbidden)}: "
        "it opens no database, constructs no exchange client and reads no environment"
    )


@pytest.mark.asyncio
async def test_an_unknown_path_is_a_404_not_a_crash() -> None:
    """A liveness check aimed at the wrong path must not take the process down."""
    status, _ = await _asgi_get(create_app(_StubConfig()), "/status-band")
    assert status == 404
