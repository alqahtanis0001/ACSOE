"""The console application object.

``acsoe console`` (Agent A, ``cli/console.py``) imports :func:`create_app` from
here and hands the resulting object to uvicorn. **The signature stays
call-compatible with ``create_app(config)``**: the two new parameters are
keyword-only and both default, so A's entry point needs no change and is not
edited.

Spec 17 builds the *read layer* and nothing above it. There is deliberately no
markup, no stylesheet, no WebSocket and no write route in this file yet — those
are specs 18 to 24. What changed from the Phase 0 placeholder is that the
application now opens a database and can answer questions about it:

* ``db_path`` is injected, defaulting to ``runtime_paths().db / "acsoe.sqlite"``.
  That default is the real one an operator gets; the injection is what lets a
  test and ``scripts/verify.py`` point the console at a seeded temporary database
  instead. ``data/`` is gitignored, so a check that could only read the default
  path could not pass on a fresh clone.
* ``clock`` is injected, defaulting to :class:`~acsoe.platform.clock.SystemClock`.
  Staleness is computed from it and never from wall time. Engines follow the same
  rule through ``context.now``; the console is a different process, but a
  staleness test against ``datetime.now()`` is a race either way.

Two properties of the Phase 0 placeholder are kept, because they are security
properties of the process rather than conveniences:

* **It constructs no exchange client and reads no credential.**
  ``ui-context.md``: "The console holds no credentials and can never place an
  order." The cheapest way to keep that true is for this package never to import
  ``clients/kraken/`` at all.
* **It cannot write to the database.** The reader's connection is opened
  ``mode=ro``; see ``console/reader.py``. Spec 24 will add one narrow read-write
  path for the ``commands`` table and nothing else.

The health payload's ``console`` field reads ``"ready"`` from Phase 1 onward, and
``phase`` reads ``1``. That is the one field an operator looks at to tell a
running console from the placeholder that preceded it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from acsoe.console.commands import (
    COMMAND_NAMES,
    RECORDED_MESSAGE,
    UNKNOWN_COMMAND_MESSAGE,
    CommandWriter,
    command_label,
)
from acsoe.console.payloads import (
    feed_payload,
    history_payload,
    research_payload,
    state_payload,
)
from acsoe.console.reader import ConsoleReader
from acsoe.console.websocket import watermark_socket
from acsoe.platform.clock import Clock, SystemClock
from acsoe.platform.paths import runtime_paths

if TYPE_CHECKING:  # pragma: no cover - typing only
    from acsoe.core.contracts import Config

__all__ = [
    "DATABASE_FILENAME",
    "MODE_PLACEHOLDER",
    "STATIC_DIR",
    "TEMPLATE_PATH",
    "console_detail",
    "create_app",
    "default_db_path",
    "health_payload",
    "render_page",
]


#: The database file name, fixed by B's layout in ``architecture-context.md``.
DATABASE_FILENAME = "acsoe.sqlite"

#: The one page, and the assets it draws from. Both are shipped inside the
#: package, so ``acsoe console`` serves them from wherever it was installed.
TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "index.html"
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: The single substitution the server makes in the template.
#:
#: Not a template engine. ``jinja2`` is not in the stack table of
#: ``architecture-context.md`` and adding a dependency is an escalation, not a
#: convenience — and one attribute does not need one. The placeholder is the
#: *real default value* rather than a ``{{ mode }}`` marker, so
#: ``templates/index.html`` stays a valid page that opens in a browser on its own.
MODE_PLACEHOLDER = 'data-mode="paper"'

#: What a refused cross-origin write answers with. Phase 8, operator ruling 2026-09-21.
FOREIGN_ORIGIN_MESSAGE = (
    "This request came from another origin, so nothing was written. The console's controls "
    "can only be used from the console's own page."
)


def foreign_origin(origin: str | None, host: str | None) -> dict[str, str] | None:
    """The refusal body when `origin` belongs to somewhere else, or `None` to serve.

    **One rule, used by the POST route and the websocket**, so the two cannot drift apart:

    * no `Origin` header at all — serve. That is a non-browser client (curl, the ASGI call a
      criterion makes, uvicorn's own health probe), where the loopback bind is the control.
      Refusing it would demand a token for the operator's own kill switch, which
      `api_command`'s docstring refuses on purpose.
    * `Origin` whose host and port match `Host` — serve. That is the console's own page,
      including the `fetch` the page makes, which browsers do send an `Origin` for.
    * anything else — refuse. A page on another origin can otherwise POST `close_all` with no
      body, no token and no preflight, from inside the operator's browser.

    Compared on the authority (host and port) rather than the scheme, because the console is
    served over http on loopback and a scheme comparison would refuse its own page.
    """
    if not origin:
        return None
    authority = origin.split("//", 1)[-1].strip().rstrip("/")
    if host and authority.lower() == host.strip().lower():
        return None
    return {
        "status": "foreign_origin",
        "message": FOREIGN_ORIGIN_MESSAGE,
        "origin": authority,
    }


def render_page(mode: str) -> str:
    """The page, with the root element told which mode the daemon is in.

    ``console.css`` keys the 3px amber frame off ``html[data-mode="live"]`` and
    off nothing else, so this one attribute is the whole of the live-mode
    treatment. A mode the template does not expect still substitutes cleanly —
    the frame simply does not appear, which is the correct behaviour for
    ``replay``.
    """
    markup = TEMPLATE_PATH.read_text(encoding="utf-8")
    if markup.count(MODE_PLACEHOLDER) != 1:
        raise RuntimeError(
            f"templates/index.html must carry {MODE_PLACEHOLDER!r} exactly once; "
            f"found {markup.count(MODE_PLACEHOLDER)}"
        )
    return markup.replace(MODE_PLACEHOLDER, f'data-mode="{mode}"')


def default_db_path() -> Path:
    """Where the daemon's database lives when nothing was injected.

    Resolved through ``platform/paths.py`` rather than assembled here, because
    the target OS is Windows and a hardcoded ``data/db/acsoe.sqlite`` is a string
    concatenation waiting for a path with a space in it.
    """
    return runtime_paths().db / DATABASE_FILENAME


def console_detail(reader: ConsoleReader) -> str:
    """One line an operator can read to see what this process is attached to."""
    return (
        f"Read-only console over {reader.db_path}. "
        f"Figures older than {reader.stale_after_ms}ms render stale."
    )


def health_payload(config: Config, reader: ConsoleReader) -> dict[str, Any]:
    """The body of ``GET /health``.

    Split out from the route so a test can assert the payload without standing up
    an HTTP server. ``mode`` is read through the `Config` Protocol rather than an
    environment variable, so it can never disagree with what the daemon loaded.
    Reporting it is not a live-mode switch: ``trading-invariants.md`` rule 1 keeps
    all three switches in ``platform/live_guard.py``, and this console reads a
    value it can neither set nor promote.
    """
    return {
        "status": "ok",
        "mode": config.mode,
        "console": "ready",
        "phase": 1,
        "detail": console_detail(reader),
    }


def create_app(
    config: Config,
    *,
    db_path: Path | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Build the console application.

    A factory rather than a module-level ``app`` object on purpose. A module-level
    instance would be constructed at import time, which means ``import
    acsoe.console.app`` — something ``mypy``, ``ruff`` and every test will do —
    would build an application, and open a database, before a validated `Config`
    exists.

    The reader is constructed here but **connects lazily**: ``acsoe console`` must
    start and answer a health check on a machine where the daemon has never run
    and the database file does not exist yet. Failing at construction would make
    the entry point's liveness depend on B's schema having been migrated.

    ``docs_url`` and ``redoc_url`` are off. The console is a local operator
    instrument, not a public API.
    """
    resolved_db = default_db_path() if db_path is None else Path(db_path)
    resolved_clock = SystemClock() if clock is None else clock
    reader = ConsoleReader(
        resolved_db,
        clock=resolved_clock,
        stale_after_ms=int(config.get("console.stale_after_ms")),
    )
    # The console's only write path, and a second connection rather than a
    # widening of the first. Spec 17's reader stays `mode=ro`; this one is
    # read-write and refuses every table but `commands` through a SQLite
    # authorizer. Both connect lazily.
    writer = CommandWriter(resolved_db, clock=resolved_clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Close both databases when the server stops.

        A lifespan handler rather than `@app.on_event("shutdown")`, which FastAPI
        deprecates. It matters on Windows more than elsewhere: SQLite holds the
        file open until the connection is closed, and a console that leaked its
        reader would leave the daemon's database locked after the process that
        was only *reading* it had gone.
        """
        try:
            yield
        finally:
            reader.close()
            writer.close()

    app = FastAPI(
        title="ACSOE console",
        version="1",
        summary="Local read-only operator console.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    # Held on `app.state` so a test or `scripts/verify.py` can release the file
    # handle without running a full server lifespan.
    app.state.reader = reader
    app.state.command_writer = writer

    # The stylesheets and the four self-hosted font files. Served from inside the
    # package: no CDN, no npm, no build step, and the page renders with the
    # machine offline.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return health_payload(config, reader)

    @app.get("/", response_class=HTMLResponse)
    def page() -> HTMLResponse:
        return HTMLResponse(render_page(str(config.mode)))

    # Every screen endpoint below is `async def`, and that is not a style choice.
    # FastAPI runs a *synchronous* endpoint in a worker thread from a pool, so two
    # requests can reach one `sqlite3.Connection` from two different threads and
    # sqlite3 raises. The reader holds one connection for the life of the process,
    # so the connection stays on the event-loop thread by keeping every reader
    # touch on it. The reads are small and local; a blocking call of that size on
    # the loop is cheaper than a connection per request or a lock around one.
    #
    # They return `JSONResponse` rather than the view models themselves for a
    # sharper reason: FastAPI serialises a returned object through
    # `jsonable_encoder`, which renders a `Decimal` by calling `float()` on it.
    # Every money field would have lost precision on the way out, silently. See
    # `console/payloads.py`.

    @app.get("/api/state")
    async def api_state() -> JSONResponse:
        """The status band and the open-positions region. Spec 19."""
        return JSONResponse(
            state_payload(reader.status_band(mode=str(config.mode)), reader.positions())
        )

    @app.get("/api/feed")
    async def api_feed() -> JSONResponse:
        """The cycle feed, and the empty state that is the main state. Spec 20."""
        return JSONResponse(feed_payload(reader.feed(), reader.feed_summary()))

    @app.get("/api/history")
    async def api_history() -> JSONResponse:
        """Closed trades and past rejections. Spec 21."""
        return JSONResponse(history_payload(reader.history()))

    @app.get("/api/research")
    async def api_research() -> JSONResponse:
        """The leaderboard, and the SHAP pane's honest empty state. Spec 22."""
        return JSONResponse(research_payload(reader.research()))

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        """Push a payload whenever the store watermark moves. Spec 23.

        One-directional and read-only. `config` is passed rather than a captured
        interval, because `console/websocket.py` reads
        `console.poll_interval_ms` on every iteration — an operator who retunes
        the file gets the new cadence on an already-open socket, and neither
        number is ever written as a literal.

        **A socket from another origin is closed rather than accepted** (Phase 8, operator
        ruling 2026-09-21), by the same rule the POST route uses. Every screen the console
        renders — the balance, the positions, the trades — goes down this socket, and before
        this any local page could open it and read all of it.
        """
        if foreign_origin(socket.headers.get("origin"), socket.headers.get("host")) is not None:
            # 1008 is "policy violation". Closed without `accept`, so nothing is ever sent.
            await socket.close(code=1008)
            return
        await watermark_socket(socket, reader=reader, config=config, mode=str(config.mode))

    @app.post("/api/command/{name}")
    async def api_command(name: str, request: Request) -> JSONResponse:
        """The console's only write. Spec 24.

        Exactly three names; anything else is a 404 that writes no row. The
        response says the command was **recorded**, not that the mode changed —
        the mode changes when the orchestrator claims the row at the top of its
        next tick. There is no confirmation parameter here on purpose: the
        confirmation for `close_all` is a step in the interface, and a server that
        demanded a token would be a second gate on the kill switch.

        **A cross-origin request is refused** (Phase 8, operator ruling 2026-09-21).
        This endpoint takes no body and no token, and a simple cross-origin form POST
        triggers no preflight, so before this any page the operator's browser happened to
        visit could fire `close_all`. The check is on `Origin` against `Host`, and a request
        with no `Origin` at all is still served: that is a non-browser client, where the
        loopback bind is the control, and refusing it would put a token in front of the
        operator's own kill switch — which the paragraph above refuses to do.
        """
        foreign = foreign_origin(request.headers.get("origin"), request.headers.get("host"))
        if foreign is not None:
            return JSONResponse(status_code=403, content=foreign)
        if name not in COMMAND_NAMES:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "unknown_command",
                    "message": UNKNOWN_COMMAND_MESSAGE.format(
                        name=name, names=", ".join(COMMAND_NAMES)
                    ),
                },
            )
        row = writer.append(name)
        return JSONResponse(
            status_code=201,
            content={
                "status": "recorded",
                "command": row.command,
                "label": command_label(name),
                "id": row.id,
                "created_at": row.created_at,
                "message": RECORDED_MESSAGE.format(label=command_label(name)),
            },
        )

    return app
