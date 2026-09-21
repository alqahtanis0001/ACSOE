"""The console refuses a cross-origin write and an accidental off-loopback bind.

Phase 8, operator ruling 2026-09-21, items 1 and 2 of the access-control work. **The console has
no authentication at all**, and until now two things followed from that:

* `POST /api/command/close_all` takes no body, no token and no confirmation parameter, and a
  simple cross-origin form POST triggers no preflight — so any page the operator's browser
  happened to visit could fire the kill switch;
* `/ws` was accepted without looking at `Origin`, so any local page could read every screen:
  the balance, the positions, the trades;
* `--host 0.0.0.0` was one flag away from publishing all of it to the network.

What is *not* built here is the token check itself (item 3), which the operator deferred. So
`ACSOE_CONSOLE_TOKEN` is an acknowledgement rather than a credential, and the refusal text says
so in as many words.

Driven through the ASGI interface directly, for the reason `test_app.py` gives: the repository's
network guard patches `httpx.Client.send`, so a `TestClient` request never reaches the app.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from acsoe.cli.console import (
    CONSOLE_TOKEN_ENV,
    LOOPBACK_HOSTS,
    off_loopback_refusal,
)
from acsoe.console.app import FOREIGN_ORIGIN_MESSAGE, create_app, foreign_origin

OWN_HOST = "console.test"


class _StubConfig:
    """The smallest config the console needs. Same shape `test_commands.py` uses."""

    @property
    def mode(self) -> str:
        return "paper"

    def get(self, dotted_key: str, /) -> Any:
        return {"console.poll_interval_ms": 500, "console.stale_after_ms": 120_000}[dotted_key]


async def _post(
    app: Any, path: str, *, headers: tuple[tuple[bytes, bytes], ...] = ()
) -> tuple[int, dict[str, Any]]:
    """One POST, driven the way uvicorn drives it.

    Not `TestClient`: it subclasses `httpx.Client`, and the repository's network guard patches
    `httpx.Client.send` for every test, so the request would raise before reaching the app.
    """
    sent: list[dict[str, Any]] = []
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", OWN_HOST.encode()), (b"content-length", b"0"), *headers],
        "client": ("test", 0),
        "server": (OWN_HOST, 80),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return int(status), json.loads(body) if body else {}


@pytest.fixture
def app(seeded_db: Path, seed_clock: Any) -> Any:
    application = create_app(_StubConfig(), db_path=seeded_db, clock=seed_clock)
    try:
        yield application
    finally:
        application.state.reader.close()
        application.state.command_writer.close()


# --------------------------------------------------------------------------- #
# The rule itself, without a server
# --------------------------------------------------------------------------- #


def test_no_origin_header_is_served() -> None:
    """curl, uvicorn's probe, and the ASGI call a verify criterion makes. The loopback bind is
    the control for those, and demanding a token here would put one in front of the operator's
    own kill switch."""
    assert foreign_origin(None, OWN_HOST) is None
    assert foreign_origin("", OWN_HOST) is None


def test_the_consoles_own_origin_is_served() -> None:
    assert foreign_origin(f"http://{OWN_HOST}", OWN_HOST) is None
    assert foreign_origin(f"https://{OWN_HOST}", OWN_HOST) is None, "scheme is not the test"
    assert foreign_origin(f"http://{OWN_HOST}/", OWN_HOST) is None, "a trailing slash is not"


def test_another_origin_is_refused_with_its_own_name() -> None:
    refusal = foreign_origin("http://evil.example", OWN_HOST)

    assert refusal is not None
    assert refusal["status"] == "foreign_origin"
    assert refusal["origin"] == "evil.example"
    assert refusal["message"] == FOREIGN_ORIGIN_MESSAGE


def test_a_different_port_on_the_same_host_is_another_origin() -> None:
    """The recording manager sits on 8766 on this very machine. It is a different origin and
    has no business firing the trading console's controls."""
    assert foreign_origin("http://127.0.0.1:8766", "127.0.0.1:8765") is not None
    assert foreign_origin("http://127.0.0.1:8765", "127.0.0.1:8765") is None


def test_a_missing_host_header_refuses_a_stated_origin() -> None:
    """Fail closed: with nothing to compare against, a request that announces an origin is
    refused rather than waved through."""
    assert foreign_origin("http://evil.example", None) is not None


# --------------------------------------------------------------------------- #
# Through the application
# --------------------------------------------------------------------------- #


FOREIGN = ((b"origin", b"http://evil.example"),)
OWN = ((b"origin", f"http://{OWN_HOST}".encode()),)


@pytest.mark.parametrize("command", ["activate", "freeze", "close_all"])
def test_a_cross_origin_post_writes_no_row(app: Any, seeded_db: Path, command: str) -> None:
    before = _command_count(seeded_db)

    status, body = asyncio.run(_post(app, f"/api/command/{command}", headers=FOREIGN))

    assert status == 403, body
    assert body["status"] == "foreign_origin"
    assert _command_count(seeded_db) == before, "a refused request still wrote a command row"


def test_the_consoles_own_page_still_writes(app: Any, seeded_db: Path) -> None:
    """The other half, and the one that matters more: the kill switch must keep working."""
    before = _command_count(seeded_db)

    status, body = asyncio.run(_post(app, "/api/command/close_all", headers=OWN))

    assert status == 201, body
    assert _command_count(seeded_db) == before + 1


def test_a_post_with_no_origin_still_writes(app: Any, seeded_db: Path) -> None:
    before = _command_count(seeded_db)

    status, body = asyncio.run(_post(app, "/api/command/freeze"))

    assert status == 201, body
    assert _command_count(seeded_db) == before + 1


def test_an_unknown_command_from_a_foreign_origin_is_refused_as_foreign(app: Any) -> None:
    """Order matters: the origin is judged before the name, so a foreign caller cannot use the
    404 to learn which command names exist."""
    status, body = asyncio.run(_post(app, "/api/command/not_a_command", headers=FOREIGN))

    assert status == 403
    assert body["status"] == "foreign_origin"


def _command_count(db_path: Path) -> int:
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        return int(connection.execute("SELECT count(*) FROM commands").fetchone()[0])
    finally:
        connection.close()


# --------------------------------------------------------------------------- #
# The bind guard
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("host", sorted(LOOPBACK_HOSTS))
def test_a_loopback_bind_needs_no_acknowledgement(host: str) -> None:
    assert off_loopback_refusal(host, None) is None


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::", "10.0.0.5"])
def test_an_off_loopback_bind_is_refused_without_the_acknowledgement(host: str) -> None:
    refusal = off_loopback_refusal(host, None)

    assert refusal is not None
    assert host in refusal
    assert CONSOLE_TOKEN_ENV in refusal
    assert "no login" in refusal


def test_the_acknowledgement_lets_it_through_and_says_it_is_not_a_credential() -> None:
    """Item 3 — an actual token check — is deferred. The variable makes exposing the console a
    deliberate act; the refusal text is where that distinction is recorded, so nobody reads the
    variable as protection."""
    assert off_loopback_refusal("0.0.0.0", "anything-at-all") is None
    text = off_loopback_refusal("0.0.0.0", None) or ""
    assert "does not authenticate anything yet" in text


@pytest.mark.parametrize("token", ["", "   "])
def test_a_blank_acknowledgement_is_no_acknowledgement(token: str) -> None:
    assert off_loopback_refusal("0.0.0.0", token) is not None
