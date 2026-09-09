"""The console application object. Specs 09 and 17.

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

What is asserted here is as much about what the console *is not* as what it is.
The console holds no credentials and can never place an order (`ui-context.md`),
so its inability to reach the exchange is a property worth a test rather than a
comment — and after spec 17 it also opens a database, which makes the *read-only*
half of that property worth asserting from the application's side as well as the
reader's.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from acsoe.console.app import create_app, default_db_path, health_payload

STALE_AFTER_MS = 120_000


class _StubConfig:
    """The narrowest thing satisfying the `Config` Protocol.

    Written here rather than reusing the `paper_config` fixture on purpose: this
    test must run on a tree where `config/default.yaml` is absent, and it pins
    exactly which keys `create_app` is allowed to read. A console that started
    reading a threshold it was not given would raise `KeyError` here and say which
    key, rather than picking up a default nobody chose.
    """

    #: Every key `create_app` may look up. One entry, deliberately.
    ALLOWED = {"console.stale_after_ms": STALE_AFTER_MS}

    def __init__(self, mode: str = "paper") -> None:
        self._mode = mode
        self.asked: list[str] = []

    @property
    def mode(self) -> Any:
        return self._mode

    def get(self, dotted_key: str, /) -> Any:
        self.asked.append(dotted_key)
        try:
            return self.ALLOWED[dotted_key]
        except KeyError:
            raise KeyError(
                f"the console may not read {dotted_key!r}; console.port, "
                "console.poll_interval_ms and console.stale_after_ms are the three keys "
                "it has, and only the lead adds a fourth"
            ) from None


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


@pytest.fixture
def console_app(seeded_db: Path, seed_clock: Any) -> Any:
    app = create_app(_StubConfig(), db_path=seeded_db, clock=seed_clock)
    try:
        yield app
    finally:
        app.state.reader.close()


# --------------------------------------------------------------------------- #
# The entry point A owns must keep working unchanged
# --------------------------------------------------------------------------- #


def test_create_app_is_still_callable_with_config_alone() -> None:
    """Spec 17's whole reason for making both new parameters keyword-only.

    `src/acsoe/cli/console.py` calls `create_app(config)` and is Agent A's file.
    If this signature stopped accepting one positional argument, Phase 1 would
    require an edit in A's directory — which is an escalation, not a refactor.
    """
    signature = inspect.signature(create_app)
    parameters = list(signature.parameters.values())
    assert parameters[0].name == "config"
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    for name in ("db_path", "clock"):
        parameter = signature.parameters[name]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is None


def test_a_s_entry_point_builds_the_app_without_touching_a_database(tmp_path: Path) -> None:
    """`acsoe console` must start on a machine where the daemon has never run.

    The database file does not exist yet on a fresh clone — `data/` is gitignored
    — so the reader connects lazily. Building the application eagerly against a
    missing file would tie the entry point's liveness to B's schema having been
    migrated, and an operator would meet a stack trace instead of a health check.
    """
    app = create_app(_StubConfig(), db_path=tmp_path / "never-created.sqlite")
    try:
        assert app.state.reader.db_path.exists() is False
    finally:
        app.state.reader.close()


def test_the_default_database_path_comes_from_platform_paths() -> None:
    """Resolved through `pathlib`, never assembled from string concatenation.

    The target OS is Windows and a hardcoded `data/db/acsoe.sqlite` is a defect
    waiting for a path with a space in it.
    """
    assert default_db_path().name == "acsoe.sqlite"
    assert default_db_path().parent.name == "db"


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_health_reports_ready_and_phase_one(console_app: Any) -> None:
    """The one field an operator looks at to tell this from the Phase 0 placeholder."""
    status, body = await _asgi_get(console_app, "/health")
    assert status == 200
    assert body["status"] == "ok"
    assert body["mode"] == "paper"
    assert body["console"] == "ready"
    assert body["phase"] == 1


@pytest.mark.asyncio
async def test_health_reports_the_configured_mode(seeded_db: Path, seed_clock: Any) -> None:
    """The mode comes from the injected config, never from an environment read.

    A console that reported a mode of its own could disagree with the daemon about
    whether real money is at risk, which is the one thing the status band exists
    to say. `trading-invariants.md` rule 1 keeps the switches in `platform/`; this
    only echoes what it was handed.
    """
    app = create_app(_StubConfig(mode="replay"), db_path=seeded_db, clock=seed_clock)
    try:
        _, body = await _asgi_get(app, "/health")
    finally:
        app.state.reader.close()
    assert body["mode"] == "replay"


def test_the_console_reads_exactly_one_config_key(seeded_db: Path, seed_clock: Any) -> None:
    """`console.stale_after_ms` and nothing else, at construction time.

    `_StubConfig.get` raises on anything else, so a console that started reading a
    fourth key — which only the lead may add — fails here and names it.
    """
    config = _StubConfig()
    app = create_app(config, db_path=seeded_db, clock=seed_clock)
    try:
        assert config.asked == ["console.stale_after_ms"]
        assert health_payload(config, app.state.reader)["console"] == "ready"
    finally:
        app.state.reader.close()


# --------------------------------------------------------------------------- #
# Scope limits, made executable
# --------------------------------------------------------------------------- #


def test_the_console_exposes_nothing_beyond_the_page_and_its_assets(console_app: Any) -> None:
    """Scope limits, made executable, and updated as each spec lands.

    The page and `/static` are spec 18; the four screen payloads are specs 19 to
    22; `/ws` is spec 23 and `/api/command/{name}` is spec 24. **The set is
    exhaustive on purpose**: a route appearing here ahead of its spec is the
    failure this asserts against, and the only way to add one is to add it here
    too and say which spec it belongs to. `/openapi.json` is off: a schema browser
    on a read-only operator instrument is surface with no reader.

    Phase 1 closes with this set complete, so from here the assertion changes
    meaning: it stops tracking progress and starts guarding the surface.
    """
    paths = {getattr(route, "path", None) for route in console_app.routes}
    assert paths == {
        "/",
        "/health",
        "/static",
        "/api/state",
        "/api/feed",
        "/api/history",
        "/api/research",
        "/ws",
        "/api/command/{name}",
    }


def test_there_is_exactly_one_write_route_and_it_is_the_command_table(
    console_app: Any,
) -> None:
    """`ui-context.md`: the page is read-only except for three commands.

    Asserted on the method rather than on the path, because a `POST` added
    somewhere else would keep the path set above honest and still be a second
    write path. `GET` and `HEAD` are the only other methods anything answers.
    """
    writing = {
        (getattr(route, "path", None), method)
        for route in console_app.routes
        for method in (getattr(route, "methods", None) or set())
        if method not in {"GET", "HEAD"}
    }
    assert writing == {("/api/command/{name}", "POST")}


def test_the_console_constructs_no_exchange_client_and_reads_no_credential() -> None:
    """The console holds no credentials and can never place an order.

    That is a property of the *process*, so the cheapest way to keep it true is
    for the package to import nothing that could reach the exchange or the
    environment. Asserted on the import statements rather than on runtime
    behaviour, because behaviour only proves the path was not taken this time
    while an absent import proves it cannot be taken at all.

    Spec 17 legitimately adds `acsoe.clients.store` and `acsoe.platform`, which
    the Phase 0 placeholder had to do without. `acsoe.clients.kraken`, `os` and
    the credential surface are still forbidden — spec 24 asks for exactly this
    assertion in as many words — and `sqlite3` may appear only in the two modules
    that hold a connection: `reader.py`, which is read-only, and `commands.py`,
    which is read-write and refuses every table but `commands`.
    """
    offences: list[str] = []
    for path, imported in sorted(_console_imports().items()):
        for name in sorted(imported):
            if name.startswith("acsoe.clients.kraken") or name in {"os", "dotenv", "httpx"}:
                offences.append(f"{path}: {name}")
            if name == "sqlite3" and path not in _CONNECTION_MODULES:
                offences.append(f"{path}: sqlite3 outside {sorted(_CONNECTION_MODULES)}")
    assert offences == [], offences


#: The only two modules allowed to hold a database connection. `reader.py` is the
#: read-only one from spec 17; `commands.py` is the narrow read-write one from
#: spec 24. A third would be a third thing to prove cannot write the wrong table.
_CONNECTION_MODULES = {"reader.py", "commands.py"}


def _console_imports() -> dict[str, set[str]]:
    """Every module name imported by each file of the console package.

    Read off the import statements rather than at runtime, because behaviour only
    proves the path was not taken this time while an absent import proves it
    cannot be taken at all.
    """
    import ast

    import acsoe.console as package

    directory = Path(str(package.__file__)).parent
    imports: dict[str, set[str]] = {}
    for path in sorted(directory.glob("*.py")):
        found: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                found.add(node.module)
        imports[path.name] = found
    return imports


def test_the_console_package_imports_nothing_from_the_kraken_client() -> None:
    """Spec 24 asks for this one on its own, and it is worth having on its own.

    The console holds no credentials and can never place an order. That is a
    property of the *process*, and the cheapest way to keep it true is for the
    package never to import the thing that could reach the exchange — including
    transitively through a module that looks innocent. Every file is checked, not
    just `commands.py`, because the write path is not the only place a client
    could be constructed.
    """
    reaching: list[str] = []
    for path, imported in sorted(_console_imports().items()):
        for name in sorted(imported):
            if "kraken" in name.lower():
                reaching.append(f"{path}: {name}")
    assert reaching == [], reaching


@pytest.mark.asyncio
async def test_an_unknown_path_is_a_404_not_a_crash(console_app: Any) -> None:
    """A liveness check aimed at the wrong path must not take the process down."""
    status, _ = await _asgi_get(console_app, "/status-band")
    assert status == 404


def test_the_application_cannot_write_to_the_database(console_app: Any) -> None:
    """Asserted from the application's side as well as the reader's.

    `app.state.reader` is the console's only handle on the database, so proving
    the write is refused *here* is proving it for the process rather than for one
    module.
    """
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        console_app.state.reader.store.connection.execute("DELETE FROM commands")
