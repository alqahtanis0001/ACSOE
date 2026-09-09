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

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from acsoe.console.payloads import (
    feed_payload,
    history_payload,
    research_payload,
    state_payload,
)
from acsoe.console.reader import ConsoleReader
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
    reader = ConsoleReader(
        default_db_path() if db_path is None else Path(db_path),
        clock=SystemClock() if clock is None else clock,
        stale_after_ms=int(config.get("console.stale_after_ms")),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Close the database when the server stops.

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

    return app
