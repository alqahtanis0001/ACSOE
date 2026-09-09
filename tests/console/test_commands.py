"""Activate, Freeze and Close all. Spec 24.

The console's only write path, and most of what is asserted here is what it must
*not* do:

* It writes to `commands` and to nothing else, and that is enforced by a SQLite
  authorizer rather than by discipline — a real `INSERT` into `runs` through the
  command connection is attempted and must raise.
* It leaves `claimed_at`, `claimed_by_run_id` and `consumed_at` null. Two-phase
  consumption is what stops a crash swallowing a kill switch, and a console that
  pre-stamped any of them would hand the daemon a command already marked done.
* There is no fourth command. The kill switch is `close_all`; an unrecognised
  name is a 404 that writes nothing.
* Spec 17's reader connection is still read-only after the write path has been
  exercised.

The interesting one is the round trip: a row written here is claimed and consumed
by the **real** command reader in `src/acsoe/core/orchestrator.py`, not by a mock
of it. What sits between them is a thin adapter, because `StoreClient` does not
expose `claim_pending_commands` — see the open question in
`context/progress/c-interface.md`. The adapter is the store side of the seam; the
reader under test is the orchestrator's own code.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import CommandName, CommandSource, to_micros
from acsoe.console.app import TEMPLATE_PATH, create_app
from acsoe.console.commands import (
    COMMAND_NAMES,
    COMMAND_TABLE,
    CONFIRMED_COMMANDS,
    CommandWriter,
    command_label,
)
from acsoe.core.orchestrator import Orchestrator
from acsoe.platform.clock import FixedClock

STALE_AFTER_MS = 120_000

#: Any fixed moment. `FixedClock` refuses a naive datetime, so a fixture cannot
#: silently encode the author's timezone.
_A_MOMENT = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def _visible_markup() -> str:
    """The page with its comments removed.

    Every assertion about copy below has to run against what the operator sees.
    The comments in `index.html` quote the wording they exist to rule out — which
    is the one thing that always looks exactly like the defect.
    """
    return re.sub(r"<!--.*?-->", " ", TEMPLATE_PATH.read_text(encoding="utf-8"), flags=re.S)


class _StubConfig:
    ALLOWED = {"console.stale_after_ms": STALE_AFTER_MS, "console.poll_interval_ms": 500}

    @property
    def mode(self) -> Any:
        return "paper"

    def get(self, dotted_key: str, /) -> Any:
        return self.ALLOWED[dotted_key]


async def _post(app: Any, path: str) -> tuple[int, dict[str, Any]]:
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
        "headers": [(b"host", b"console.test"), (b"content-length", b"0")],
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
    return int(status), json.loads(body) if body else {}


@pytest.fixture
def console_app(seeded_db: Path, seed_clock: Any) -> Any:
    app = create_app(_StubConfig(), db_path=seeded_db, clock=seed_clock)
    try:
        yield app
    finally:
        app.state.reader.close()
        app.state.command_writer.close()


def _rows(db_path: Path, *, source: str | None = None) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM commands"
        params: tuple[Any, ...] = ()
        if source is not None:
            sql += " WHERE source = ?"
            params = (source,)
        return [dict(row) for row in conn.execute(sql + " ORDER BY id", params)]
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# One correct row each
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", ["activate", "freeze", "close_all"])
@pytest.mark.asyncio
async def test_each_command_writes_exactly_one_unclaimed_console_row(
    console_app: Any, seeded_db: Path, name: str
) -> None:
    """`source = 'console'`, and all three stamping fields null.

    The console announces an intention; the daemon's reader is the only thing that
    may mark a row claimed or consumed, and it stamps `claimed_at` before applying
    the effect and `consumed_at` only once the effect is complete.
    """
    before = {row["id"] for row in _rows(seeded_db)}
    status, body = await _post(console_app, "/api/command/" + name)
    added = [row for row in _rows(seeded_db) if row["id"] not in before]

    assert status == 201
    assert len(added) == 1
    row = added[0]
    assert row["command"] == name
    assert row["source"] == CommandSource.CONSOLE.value
    assert row["claimed_at"] is None
    assert row["claimed_by_run_id"] is None
    assert row["consumed_at"] is None
    assert row["created_at"] > 0
    assert body["status"] == "recorded"
    assert body["command"] == name


@pytest.mark.asyncio
async def test_the_response_says_recorded_and_never_that_the_mode_changed(
    console_app: Any,
) -> None:
    """The mode changes when the orchestrator claims the row at the top of its next
    tick, not when this endpoint returns. Claiming the two are the same thing would
    make the console lie about the daemon's state — which is the one thing the
    status band exists not to do."""
    _, body = await _post(console_app, "/api/command/freeze")
    assert "recorded" in body["message"].lower()
    assert "frozen" not in body["message"].lower()
    assert "running" not in body["message"].lower()
    assert body["label"] == "Freeze"


@pytest.mark.asyncio
async def test_the_timestamps_come_from_the_injected_clock(
    seeded_db: Path, seed_clock: Any
) -> None:
    """Never from wall time. The console is a separate process from the daemon, but
    a timestamp read off `datetime.now()` makes every test of it a race."""
    app = create_app(_StubConfig(), db_path=seeded_db, clock=seed_clock)
    try:
        await _post(app, "/api/command/activate")
    finally:
        app.state.reader.close()
        app.state.command_writer.close()
    written = _rows(seeded_db, source="console")[-1]
    assert written["created_at"] == to_micros(seed_clock.now())
    assert written["updated_at"] == to_micros(seed_clock.now())


# --------------------------------------------------------------------------- #
# There is no fourth command
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", ["stop", "shutdown", "close-all", "CLOSE_ALL", "", "kill"])
@pytest.mark.asyncio
async def test_an_unrecognised_name_is_a_404_that_writes_nothing(
    console_app: Any, seeded_db: Path, name: str
) -> None:
    """`stop` and `shutdown` are in the list deliberately. The kill switch is
    `close_all` and there is no other mechanism; a name that sounds like one is
    the shape of the mistake this refuses."""
    before = _rows(seeded_db)
    status, body = await _post(console_app, "/api/command/" + name)
    assert status == 404
    assert _rows(seeded_db) == before
    # A name the router matched reaches the endpoint and gets the console's own
    # message; an empty segment never matches the route at all and gets FastAPI's.
    # Both are a 404 that wrote nothing, which is the whole requirement.
    assert body.get("status", "unknown_command") == "unknown_command"


def test_the_three_names_come_from_the_store_contract_rather_than_being_retyped() -> None:
    """The enum and the endpoint cannot drift apart if only one of them exists."""
    assert tuple(name.value for name in CommandName) == COMMAND_NAMES
    assert set(COMMAND_NAMES) == {"activate", "freeze", "close_all"}


def test_the_writer_refuses_a_name_that_is_not_one_of_the_three() -> None:
    """Refused below the route as well as at it, so a future caller inside the
    package cannot route around the check by calling `append` directly."""
    writer = CommandWriter(Path("unused.sqlite"), clock=FixedClock(_A_MOMENT))
    with pytest.raises(ValueError, match="is not one of"):
        writer.append("shutdown")


# --------------------------------------------------------------------------- #
# The connection is narrow, and the reader is still read-only
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_the_command_connection_cannot_write_any_other_table(
    console_app: Any,
) -> None:
    """A real `INSERT` into a real table that really exists, refused by SQLite.

    Spec 24 says the write path touches only `commands`. A subclass that merely
    never *calls* the other writes would be a promise; an authorizer that denies
    them is a property, and this is the test that tells them apart.
    """
    await _post(console_app, "/api/command/activate")
    connection = console_app.state.command_writer.store.connection
    for statement in (
        "INSERT INTO runs (run_id, mode, started_at, updated_at) VALUES ('x', 'paper', 1, 1)",
        "UPDATE positions SET status = 'closed'",
        "DELETE FROM trades",
        "DROP TABLE rejections",
    ):
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(statement)


@pytest.mark.asyncio
async def test_the_command_connection_can_still_write_its_own_table(
    console_app: Any, seeded_db: Path
) -> None:
    """The other direction. An authorizer that denied everything would pass the
    test above and break the feature, which is the classic way a negative test
    passes for the wrong reason."""
    before = len(_rows(seeded_db))
    await _post(console_app, "/api/command/freeze")
    assert len(_rows(seeded_db)) == before + 1


@pytest.mark.asyncio
async def test_the_reader_connection_still_refuses_a_write_afterwards(
    console_app: Any,
) -> None:
    """Spec 24's own check. Opening a read-write connection for `commands` must not
    have widened the read-only one beside it."""
    await _post(console_app, "/api/command/close_all")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        console_app.state.reader.store.connection.execute("DELETE FROM commands")


def test_the_command_table_name_is_stated_once() -> None:
    assert COMMAND_TABLE == "commands"


@pytest.mark.asyncio
async def test_the_reader_still_reads_the_database_after_a_command_is_written(
    console_app: Any,
) -> None:
    """Two connections to one file, and the read-only one must survive the write.

    Worth its own test rather than assumed. `clients/store/connection.py` opens
    every connection in WAL mode, and a `mode=ro` connection to a WAL database
    needs the `-shm` sidecar it cannot itself create — so a reader that had never
    been used before the first write is exactly the case that could fail, on
    Windows more readily than elsewhere. It is also the normal case: an operator
    opens the console and presses Freeze before any screen has been polled.
    """
    fresh = console_app.state.reader
    fresh.close()
    await _post(console_app, "/api/command/freeze")
    assert fresh.watermark() > 0
    assert fresh.status_band(mode="paper").state


@pytest.mark.asyncio
async def test_the_watermark_moves_when_a_command_is_written(
    seeded_db: Path, seed_clock: Any
) -> None:
    """`commands` is one of the watermark tables, so the operator's own command is
    what makes the socket push the screen that will eventually show its effect.

    The clock is advanced a second past the seed's last moment on purpose. The
    console stamps `updated_at` from its own injected clock, and `seed_clock`
    stands exactly *at* the newest seeded row — so a command written at that
    instant ties the watermark rather than moving it, and the test would assert
    nothing. In a running console the clock is always ahead of every seeded row;
    here that has to be arranged rather than assumed.
    """
    later = FixedClock(seed_clock.now() + dt.timedelta(seconds=1))
    app = create_app(_StubConfig(), db_path=seeded_db, clock=later)
    try:
        before = app.state.reader.watermark()
        await _post(app, "/api/command/activate")
        assert app.state.reader.watermark() > before
    finally:
        app.state.reader.close()
        app.state.command_writer.close()


# --------------------------------------------------------------------------- #
# The round trip through the real orchestrator reader
# --------------------------------------------------------------------------- #


class _StoreAdapter:
    """The store shape `Orchestrator._consume_commands` reaches for.

    `StoreClient` exposes `pending_commands`, `claim_command` and
    `mark_command_consumed`, and the orchestrator calls `claim_pending_commands`
    and a differently-shaped `mark_command_consumed`. That mismatch is a real gap
    on B's surface, recorded as an open question rather than papered over by
    editing B's file; this adapter is the seam, and it does nothing but rename.

    **The reader under test is the orchestrator's own code**, not this. Every
    decision — which row to claim, what effect to apply, when to stamp
    `consumed_at`, and that `close_all` defers it — happens in `core/`.
    """

    def __init__(self, store: StoreClient) -> None:
        self._store = store

    def claim_pending_commands(self, *, run_id: str, now: dt.datetime) -> list[Any]:
        claimed = []
        for row in self._store.pending_commands():
            assert row.id is not None
            if self._store.claim_command(row.id, claimed_at=to_micros(now), run_id=run_id):
                claimed.append(row)
        return claimed

    def mark_command_consumed(self, command: Any, *, now: dt.datetime) -> None:
        self._store.mark_command_consumed(command.id, consumed_at=to_micros(now))


class _Clients:
    def __init__(self, store: Any) -> None:
        self._store = store

    @property
    def kraken(self) -> Any:
        return object()

    @property
    def store(self) -> Any:
        return self._store

    @property
    def recorder(self) -> Any:
        return object()


@pytest.mark.parametrize(
    ("name", "expected_mode", "expected_intent", "consumed_in_the_same_tick"),
    [
        ("activate", "running", False, True),
        ("freeze", "frozen", False, True),
        ("close_all", "frozen", True, False),
    ],
)
@pytest.mark.asyncio
async def test_a_console_row_is_claimed_and_applied_by_the_real_reader(
    migrated_db: Path,
    fixed_clock: FixedClock,
    name: str,
    expected_mode: str,
    expected_intent: bool,
    consumed_in_the_same_tick: bool,
) -> None:
    """Written by the console, read by `core/`, with nothing in between but SQLite.

    A migrated database rather than the seed, so the only command row in it is the
    one the console wrote and the assertion cannot be satisfied by a seeded row.

    `close_all` is the row that must **not** be consumed in the same tick: its
    effect is not complete until every resting entry order is cancelled and every
    position closed, and stamping `consumed_at` early is exactly the failure the
    two-phase design exists to prevent — a daemon killed mid-liquidation would
    come back with the command marked done and positions still open.
    """
    app = create_app(_StubConfig(), db_path=migrated_db, clock=fixed_clock)
    try:
        status, _ = await _post(app, "/api/command/" + name)
        assert status == 201
    finally:
        app.state.reader.close()
        app.state.command_writer.close()

    with StoreClient(migrated_db) as store:
        orchestrator = Orchestrator(
            config=_StubConfig(),
            clock=fixed_clock,
            clients=_Clients(_StoreAdapter(store)),
        )
        orchestrator.tick()

        assert orchestrator.system["mode"] == expected_mode
        assert orchestrator.system["close_intent"] is expected_intent

        written = _rows(migrated_db)
        assert len(written) == 1
        row = written[0]
        # Claimed by the daemon, and unchanged in every field the console wrote.
        assert row["command"] == name
        assert row["source"] == CommandSource.CONSOLE.value
        assert row["claimed_at"] is not None
        assert row["claimed_by_run_id"] == orchestrator.run_id
        assert (row["consumed_at"] is not None) is consumed_in_the_same_tick


@pytest.mark.asyncio
async def test_a_claimed_row_is_never_applied_twice_within_a_run(
    migrated_db: Path, fixed_clock: FixedClock
) -> None:
    """`claimed_at IS NULL` is what gives the reader its idempotency, and a console
    that pre-stamped it would make every command invisible to the daemon."""
    app = create_app(_StubConfig(), db_path=migrated_db, clock=fixed_clock)
    try:
        await _post(app, "/api/command/activate")
    finally:
        app.state.reader.close()
        app.state.command_writer.close()

    with StoreClient(migrated_db) as store:
        adapter = _StoreAdapter(store)
        orchestrator = Orchestrator(
            config=_StubConfig(), clock=fixed_clock, clients=_Clients(adapter)
        )
        orchestrator.tick()
        assert adapter.claim_pending_commands(run_id="second", now=fixed_clock.now()) == []
        orchestrator.tick()
        assert orchestrator.system["mode"] == "running"


# --------------------------------------------------------------------------- #
# The interface: names that do not change, and one confirmation
# --------------------------------------------------------------------------- #


def test_the_buttons_say_what_happens_and_never_submit() -> None:
    """`ui-context.md`: buttons say what happens. Never `Submit`."""
    markup = _visible_markup()
    for name, label in (
        ("activate", "Activate"),
        ("freeze", "Freeze"),
        ("close_all", "Close all positions"),
    ):
        pattern = r'data-command="' + name + r'"[^>]*>' + re.escape(label) + r"<"
        assert re.search(pattern, markup), name
    assert "Submit" not in markup
    for name in COMMAND_NAMES:
        assert command_label(name) in markup


def test_close_all_is_the_only_confirmed_command() -> None:
    assert {"close_all"} == CONFIRMED_COMMANDS


def test_the_confirmation_restates_the_action_by_its_own_name() -> None:
    """An action keeps its name through the whole flow.

    The confirmation is a separate control beside the button, and it carries the
    same three words. A step that turned the button into `Confirm` would be a
    different action as far as the operator is concerned, and `Are you sure?` is
    the vague copy `ui-context.md` rules out in the same breath.
    """
    markup = _visible_markup()
    assert re.search(r'data-confirm="yes"[^>]*>Close all positions<', markup)
    assert "Are you sure" not in markup
    assert not re.search(r'data-confirm="yes"[^>]*>Confirm<', markup)

    import acsoe.console as package

    script = (Path(str(package.__file__)).parent / "static" / "console.js").read_text(
        encoding="utf-8"
    )
    # The button's own text is never rewritten; only the confirmation bar is shown.
    assert "button.textContent" not in script
    assert 'needsConfirmation(name)' in script
    assert 'name === "close_all"' in script


def test_only_close_all_takes_the_confirmation_path_in_the_browser() -> None:
    """Activate and Freeze are not confirmed. A confirmation on every command is a
    confirmation the operator stops reading, which is worse than none on the one
    that matters."""
    import acsoe.console as package

    script = (Path(str(package.__file__)).parent / "static" / "console.js").read_text(
        encoding="utf-8"
    )
    body = script[script.index("function needsConfirmation") :]
    body = body[: body.index("}")]
    assert "activate" not in body
    assert "freeze" not in body
