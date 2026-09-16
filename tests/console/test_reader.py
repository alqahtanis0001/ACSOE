"""The console read layer. Spec 17.

Four properties get most of the attention here, and each is a property the spec
argues for rather than a behaviour it merely describes:

* **The connection is read-only, proved by attempting a write.** Not by reading
  the URI back, not by checking the open mode. A typo in the URI, a fallback that
  quietly reopens read-write, or a future refactor would all pass a check on the
  string and none of them would pass a real `INSERT`.
* **Staleness comes from the injected clock.** Asserted one microsecond either
  side of `console.stale_after_ms`. Against wall time that assertion is a race.
* **Restart detection is made in SQLite.** Both directions.
* **Money never becomes a float.** The view models refuse one rather than
  coercing it.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import RunMode, RunRow, SystemMode
from acsoe.console.format import MINUS_SIGN, format_age
from acsoe.console.reader import ConsoleReader, ReadOnlyStore, open_readonly_connection
from acsoe.console.views import (
    FROZEN,
    IDLE,
    IDLE_READINGS,
    IDLE_RESTARTED,
    RUNNING,
    STATE_READINGS,
    PositionView,
    RejectionRowView,
    StatusBand,
    TradeRowView,
)
from acsoe.platform.clock import FixedClock

STALE_AFTER_MS = 120_000


def reader_for(db_path: Path, clock: Any, *, stale_after_ms: int = STALE_AFTER_MS) -> ConsoleReader:
    return ConsoleReader(db_path, clock=clock, stale_after_ms=stale_after_ms)


@pytest.fixture
def seeded_reader(seeded_db: Path, seed_clock: Any) -> Any:
    reader = reader_for(seeded_db, seed_clock)
    try:
        yield reader
    finally:
        reader.close()


@pytest.fixture
def empty_reader(migrated_db: Path, fixed_clock: Any) -> Any:
    reader = reader_for(migrated_db, fixed_clock)
    try:
        yield reader
    finally:
        reader.close()


# --------------------------------------------------------------------------- #
# The read-only connection, proved by attempting a write
# --------------------------------------------------------------------------- #


def test_a_real_insert_through_the_reader_raises(seeded_reader: ConsoleReader) -> None:
    """Spec 17 step 9, and the operator's fourth addition at approval.

    A negative test in the spirit of spec 14's network guard: a guard that has
    never been shown to fire is not a guard, it is a comment. The `INSERT` below
    is a real statement against a real table that really exists in the database.
    """
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        seeded_reader.store.connection.execute(
            "INSERT INTO runs (run_id, mode, started_at, updated_at) "
            "VALUES ('console-should-not-write', 'paper', 1, 1)"
        )


def test_a_real_update_through_the_reader_raises(seeded_reader: ConsoleReader) -> None:
    """The other half. `INSERT` and `UPDATE` take different paths in SQLite's
    authorizer, and a connection that refused one is not proof about the other."""
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        seeded_reader.store.connection.execute("UPDATE runs SET mode = 'live'")


def test_the_write_that_was_refused_really_would_have_worked(seeded_db: Path) -> None:
    """The negative test has to be able to fail.

    An `INSERT` that raised because the table was missing, or because the SQL was
    malformed, would satisfy `pytest.raises` and prove nothing about read-only
    mode. The same statement is run here on a normal connection to the same file
    and is asserted to succeed.
    """
    conn = sqlite3.connect(seeded_db)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, mode, started_at, updated_at) "
            "VALUES ('console-should-not-write', 'paper', 1, 1)"
        )
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM runs WHERE run_id = 'console-should-not-write'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_the_reader_still_reads_after_a_refused_write(seeded_reader: ConsoleReader) -> None:
    """A refused write must not poison the connection the screens are drawn from."""
    with pytest.raises(sqlite3.OperationalError):
        seeded_reader.store.connection.execute("DELETE FROM runs")
    assert seeded_reader.watermark() > 0
    assert seeded_reader.status_band(mode="paper").run_id is not None


def test_the_store_client_write_methods_are_refused_too(seeded_reader: ConsoleReader) -> None:
    """Not just raw SQL. B's own write helpers go through the same connection.

    This is what makes the read-only property structural: the console could call
    `write_run` by mistake and the database would still refuse it.
    """
    row = RunRow(
        run_id="console-should-not-write",
        mode=RunMode.PAPER,
        started_at=1,
        updated_at=1,
    )
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        seeded_reader.store.write_run(row)


def test_the_connection_is_opened_through_a_uri_that_survives_an_awkward_path(
    tmp_path: Path,
) -> None:
    """`Path.as_uri()` percent-encodes; string formatting does not.

    A database under a directory containing a `#` truncates at the fragment if the
    URI is assembled by concatenation, and SQLite then opens - or creates - a
    different file entirely. The target OS is Windows, where paths with spaces are
    the normal case.
    """
    awkward = tmp_path / "a folder #1"
    awkward.mkdir()
    db_path = awkward / "acsoe.sqlite"
    sqlite3.connect(db_path).close()
    conn = open_readonly_connection(db_path)
    try:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()


def test_the_read_only_store_is_b_s_client(seeded_reader: ConsoleReader) -> None:
    """Composed from the reads that already exist, not a second set of SELECTs.

    A parallel implementation in the console would be a second statement of B's
    schema, and it would drift the first time a column was renamed.
    """
    from acsoe.clients.store.client import StoreClient

    assert isinstance(seeded_reader.store, ReadOnlyStore)
    assert isinstance(seeded_reader.store, StoreClient)


# --------------------------------------------------------------------------- #
# Staleness, from the injected clock
# --------------------------------------------------------------------------- #


def test_one_microsecond_inside_the_threshold_is_fresh(seeded_db: Path) -> None:
    """Spec 17 step 6, and the operator's third addition at approval."""
    anchor = datetime(2026, 1, 1, tzinfo=UTC)
    ts = int(anchor.timestamp() * 1_000_000)
    clock = FixedClock(anchor + timedelta(microseconds=STALE_AFTER_MS * 1000 - 1))
    reader = reader_for(seeded_db, clock)
    try:
        staleness = reader.staleness(ts)
    finally:
        reader.close()
    assert staleness.is_stale is False
    assert staleness.age_us == STALE_AFTER_MS * 1000 - 1


def test_one_microsecond_outside_the_threshold_is_stale(seeded_db: Path) -> None:
    """The other side of the same boundary.

    `age_ms` floors to exactly `stale_after_ms` here, which is why `is_stale` is
    decided in microseconds *before* the conversion. A console that compared
    milliseconds would call this figure fresh and the screen would stop fading at
    the one moment it is supposed to.
    """
    anchor = datetime(2026, 1, 1, tzinfo=UTC)
    ts = int(anchor.timestamp() * 1_000_000)
    clock = FixedClock(anchor + timedelta(microseconds=STALE_AFTER_MS * 1000 + 1))
    reader = reader_for(seeded_db, clock)
    try:
        staleness = reader.staleness(ts)
    finally:
        reader.close()
    assert staleness.is_stale is True
    assert staleness.age_ms == STALE_AFTER_MS


def test_exactly_at_the_threshold_is_fresh(seeded_db: Path) -> None:
    """The boundary has to be somewhere and it is stated rather than discovered."""
    anchor = datetime(2026, 1, 1, tzinfo=UTC)
    ts = int(anchor.timestamp() * 1_000_000)
    clock = FixedClock(anchor + timedelta(milliseconds=STALE_AFTER_MS))
    reader = reader_for(seeded_db, clock)
    try:
        assert reader.staleness(ts).is_stale is False
    finally:
        reader.close()


def test_no_console_module_reads_wall_time() -> None:
    """Asserted on the source, because behaviour only proves the path was not taken
    this time while an absent call proves it cannot be taken at all.

    `SystemClock` is the one sanctioned reader of wall time and it lives in
    `platform/`, where A owns it. The console receives it, and the default in
    `create_app` is the only place the console names it.
    """
    import ast

    import acsoe.console as package

    forbidden = {"now", "utcnow", "today", "time", "monotonic", "perf_counter"}
    offences: list[str] = []
    for path in sorted(Path(str(package.__file__)).parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in forbidden:
                continue
            owner = node.func.value
            name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
            if name in {"datetime", "date", "time"}:
                offences.append(f"{path.name}: {name}.{node.func.attr}()")
    assert offences == [], offences


# --------------------------------------------------------------------------- #
# Restart detection, made in SQLite
# --------------------------------------------------------------------------- #


def test_a_changed_run_id_with_an_idle_mode_reads_restarted(seeded_reader: ConsoleReader) -> None:
    """`ui-context.md`: a crash at 3am leaves a system that is up, watching its
    open positions, and not trading. That is safe behaviour, and it is silent
    unless the band says so."""
    band = seeded_reader.status_band(mode="paper")
    assert band.restarted is True
    assert band.state == IDLE_RESTARTED
    assert band.state == "Idle \N{EM DASH} restarted, not trading"
    assert band.previous_run_id is not None
    assert band.previous_run_id != band.run_id


def test_a_first_start_reads_plain_idle(seeded_db: Path, seed_clock: Any) -> None:
    """The other state: a system waiting to be started, which has no predecessor.

    `runs.run_id` is `NOT NULL UNIQUE`, so "the two run_ids match" is a state the
    schema forbids outright. The equivalent - and the one an operator actually
    meets - is the first ever run.
    """
    conn = sqlite3.connect(seeded_db)
    try:
        conn.execute(
            "DELETE FROM runs WHERE run_id <> "
            "(SELECT run_id FROM runs ORDER BY started_at DESC, id DESC LIMIT 1)"
        )
        conn.commit()
    finally:
        conn.close()

    reader = reader_for(seeded_db, seed_clock)
    try:
        band = reader.status_band(mode="paper")
    finally:
        reader.close()
    assert band.restarted is False
    assert band.state == IDLE
    assert band.previous_run_id is None


def test_an_empty_database_reads_plain_idle_and_does_not_raise(
    empty_reader: ConsoleReader,
) -> None:
    """A migrated-but-empty database is what a fresh install looks like."""
    band = empty_reader.status_band(mode="paper")
    assert band.state == IDLE
    assert band.run_id is None
    assert band.balance is None
    assert band.staleness is None


def test_the_restart_comparison_reads_the_store_and_nothing_the_process_remembers(
    seeded_db: Path, seed_clock: Any
) -> None:
    """The console is a separate process with no memory across its own restarts.

    Two readers built one after the other over the same database must agree, and a
    reader built after the rows change must follow the rows rather than what the
    first one saw.
    """
    first = reader_for(seeded_db, seed_clock)
    try:
        assert first.status_band(mode="paper").restarted is True
    finally:
        first.close()

    conn = sqlite3.connect(seeded_db)
    try:
        conn.execute(
            "DELETE FROM runs WHERE run_id <> "
            "(SELECT run_id FROM runs ORDER BY started_at DESC, id DESC LIMIT 1)"
        )
        conn.commit()
    finally:
        conn.close()

    second = reader_for(seeded_db, seed_clock)
    try:
        assert second.status_band(mode="paper").restarted is False
    finally:
        second.close()


# --------------------------------------------------------------------------- #
# The State field's four readings. Spec 32.
# --------------------------------------------------------------------------- #
#
# Through Phase 1 this field had two readings and the other two were deferred,
# because mode lived only in the daemon's memory and nothing the console could read
# distinguished a running daemon from a frozen one. The operator ended that deferral
# with the Phase 2 approval on 2026-09-09, and the mode is now persisted by the
# command reader in `core/` and read here as a fact.
#
# The deferral was supposed to be held by a test asserting the field never leaves
# the idle pair. That test never existed - `views.IDLE_READINGS` said it did. See
# `docs/build-log/phase-2/c-interface.md`.


def persist_mode(db_path: Path, run_id: str, mode: str) -> None:
    """Write the mode the way the daemon does: through B's accessor, not raw SQL.

    `set_system_mode` is the column's only writer by design - `write_run` excludes
    it - so a test that reached past it with an `UPDATE` would be asserting against
    a state the system cannot actually produce.
    """
    with StoreClient(db_path) as store:
        assert store.set_system_mode(run_id, SystemMode(mode), at=1_800_000_000_000_000)


def latest_run_id(db_path: Path) -> str:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT run_id FROM runs ORDER BY started_at DESC, id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    return str(row[0])


def test_a_daemon_that_persisted_running_reads_running(
    seeded_db: Path, seed_clock: Any
) -> None:
    persist_mode(seeded_db, latest_run_id(seeded_db), "running")
    reader = reader_for(seeded_db, seed_clock)
    try:
        band = reader.status_band(mode="paper")
    finally:
        reader.close()
    assert band.state == RUNNING
    assert band.system_mode == "running"
    assert band.run_record_missing is False


def test_a_daemon_that_persisted_frozen_reads_frozen(seeded_db: Path, seed_clock: Any) -> None:
    """`Freeze` produces the state `Frozen` - an action keeps its name through the
    whole flow, per the copy rules."""
    persist_mode(seeded_db, latest_run_id(seeded_db), "frozen")
    reader = reader_for(seeded_db, seed_clock)
    try:
        band = reader.status_band(mode="paper")
    finally:
        reader.close()
    assert band.state == FROZEN
    assert band.system_mode == "frozen"


def test_a_persisted_running_mode_wins_over_the_restart_banner(
    seeded_db: Path, seed_clock: Any
) -> None:
    """The seed carries two runs, so the restart test is true and the mode is not idle.

    A band that showed `Idle - restarted, not trading` over a daemon that is
    actually trading would be the exact failure the restart banner exists to
    prevent, pointed the other way.
    """
    persist_mode(seeded_db, latest_run_id(seeded_db), "running")
    reader = reader_for(seeded_db, seed_clock)
    try:
        band = reader.status_band(mode="paper")
    finally:
        reader.close()
    assert band.restarted is True
    assert band.state == RUNNING


def test_a_run_that_exists_with_no_persisted_mode_reads_idle(
    seeded_reader: ConsoleReader,
) -> None:
    """The ordinary null: the run exists and no daemon has written a mode yet.

    B asserts in `test_the_seed_writes_no_system_mode` that the seed writes none,
    which is what makes the two tests above worth having - they cannot pass without
    a mode actually being persisted.
    """
    band = seeded_reader.status_band(mode="paper")
    assert band.system_mode is None
    assert band.run_record_missing is False
    assert band.state in IDLE_READINGS


def test_the_two_nulls_are_not_collapsed(seeded_db: Path, seed_clock: Any) -> None:
    """`None` from the accessor is a **missing runs row**, not a missing mode.

    B's `SystemModeRow` docstring is explicit: both render an idle reading and only
    one is normal, and a reader that cannot tell them apart cannot log the abnormal
    one. This drives the abnormal branch by deleting the row the band just named as
    current, which is the shape of the race it stands for.
    """
    run_id = latest_run_id(seeded_db)
    reader = reader_for(seeded_db, seed_clock)
    try:
        real = reader.status_band(mode="paper")
        assert real.run_record_missing is False

        original = reader.store.system_mode

        def missing_row(_: str) -> None:
            return None

        reader.store.system_mode = missing_row  # type: ignore[method-assign]
        try:
            band = reader.status_band(mode="paper")
        finally:
            reader.store.system_mode = original  # type: ignore[method-assign]
    finally:
        reader.close()
    assert band.run_id == run_id
    assert band.system_mode is None
    assert band.run_record_missing is True
    assert band.state in IDLE_READINGS


def test_the_database_itself_refuses_a_mode_the_band_could_not_render(
    seeded_db: Path,
) -> None:
    """The reader's fallback for an unrecognised mode is unreachable, and that is B's doing.

    `_state_reading` treats a mode it does not know exactly as a missing one, and I
    expected to drive that branch with a direct `UPDATE`. The column carries
    `CHECK (system_mode IS NULL OR system_mode IN ('idle', 'running', 'frozen'))`,
    so the write is refused by SQLite before the console is ever involved. The
    fallback stays - a schema outlives the release that wrote it and this console
    may one day read a database with a fourth mode in it - but it is defence, not a
    reachable path, and this test is what says so rather than leaving a reader to
    wonder why the branch has no coverage.
    """
    conn = sqlite3.connect(seeded_db)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="system_mode"):
            conn.execute(
                "UPDATE runs SET system_mode = 'liquidating' WHERE run_id = ?",
                (latest_run_id(seeded_db),),
            )
    finally:
        conn.close()


def test_the_persisted_idle_mode_reads_as_an_idle_reading(
    seeded_db: Path, seed_clock: Any
) -> None:
    """`idle` is a value the column permits, and it is not in the mode map.

    It falls through to the restart test, which is the right answer: `Idle` and
    `Idle - restarted, not trading` are the two things an idle daemon can be, and
    which of them applies is decided by whether a previous run exists.
    """
    persist_mode(seeded_db, latest_run_id(seeded_db), "idle")
    reader = reader_for(seeded_db, seed_clock)
    try:
        band = reader.status_band(mode="paper")
    finally:
        reader.close()
    assert band.system_mode == "idle"
    assert band.state == IDLE_RESTARTED


def test_every_reading_the_state_field_takes_is_declared(
    seeded_db: Path, seed_clock: Any
) -> None:
    """All four, and nothing else.

    This replaces the Phase 1 assertion that the field never left the idle pair.
    That one enforced a deferral the operator has ended; this one enforces the
    positive statement that took its place - `views.STATE_READINGS` is the whole
    set, and a fifth reading has to be added there deliberately.
    """
    seen = set()
    for persisted in (None, "idle", "running", "frozen"):
        conn = sqlite3.connect(seeded_db)
        try:
            conn.execute(
                "UPDATE runs SET system_mode = ? WHERE run_id = ?",
                (persisted, latest_run_id(seeded_db)),
            )
            conn.commit()
        finally:
            conn.close()
        reader = reader_for(seeded_db, seed_clock)
        try:
            seen.add(reader.status_band(mode="paper").state)
        finally:
            reader.close()

    assert seen <= set(STATE_READINGS)
    assert {RUNNING, FROZEN} <= seen
    assert set(STATE_READINGS) == {IDLE, IDLE_RESTARTED, RUNNING, FROZEN}


def test_the_console_never_reads_the_commands_table_to_decide_a_mode(
    repo_root: Path,
) -> None:
    """Rejected at the Phase 1 close, and asserted on the source rather than trusted.

    Deriving the mode from the trail of claimed `commands` rows reconstructs it from
    a command history, so it is only ever as correct as the assumption that every
    transition leaves a claimed row - and a transition that leaves none makes the
    band confidently wrong. `console/commands.py` *writes* that table, which is
    spec 24 and is fine; nothing in the read path may select from it.
    """
    read_path = ("reader.py", "views.py", "payloads.py", "websocket.py", "app.py")
    package = repo_root / "src" / "acsoe" / "console"
    for name in read_path:
        source = (package / name).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        lowered = code.lower()
        assert "from commands" not in lowered, name
        assert "claimed_by_run_id" not in lowered, name
        assert "claimed_unconsumed" not in lowered, name
        assert "pending_commands" not in lowered, name


# --------------------------------------------------------------------------- #
# Populated against the seed, empty against an empty database
# --------------------------------------------------------------------------- #


def test_every_screen_is_populated_against_the_seed(
    seeded_reader: ConsoleReader, seed_fixtures: Any
) -> None:
    band = seeded_reader.status_band(mode="paper")
    assert band.balance is not None
    assert isinstance(band.balance, Decimal)
    assert band.currency == seed_fixtures.reporting_currency
    assert band.open_position_count == len(seed_fixtures.open_positions)
    assert band.resting_order_count >= len(seed_fixtures.resting_entry_orders)

    assert len(seeded_reader.positions()) == len(seed_fixtures.open_positions)
    assert seeded_reader.feed()
    # `HistoryView` is a pydantic model and is truthy whether or not it holds a
    # row, so a bare `assert seeded_reader.history()` would pass against an empty
    # database. Both tables are asserted individually.
    assert seeded_reader.history().trades
    assert seeded_reader.history().rejections
    assert len(seeded_reader.leaderboard()) <= seed_fixtures.leaderboard_count
    assert seeded_reader.watermark() > 0


def test_every_screen_is_empty_against_an_empty_database(empty_reader: ConsoleReader) -> None:
    """Empty, not raising. `ui-context.md`: a console that looks empty most of the
    time is not broken, it is telling the truth."""
    assert empty_reader.positions() == ()
    assert empty_reader.feed() == ()
    # Two tables, not one: `history()` returns a `HistoryView`, so an empty
    # history is two empty tuples rather than one. Both are asserted, because a
    # `HistoryView` compares unequal to `()` whatever it holds and an assertion
    # against `()` would have been a shape check dressed as an emptiness check.
    assert empty_reader.history().trades == ()
    assert empty_reader.history().rejections == ()
    assert empty_reader.leaderboard() == ()
    assert empty_reader.watermark() == 0


def test_the_feed_is_newest_first_and_carries_both_kinds(
    seeded_reader: ConsoleReader,
) -> None:
    """A rejection is one candidate refused; a block record is one tick on which
    trading was blocked, and most blocked ticks never had a candidate at all."""
    rows = seeded_reader.feed()
    assert [r.ts for r in rows] == sorted((r.ts for r in rows), reverse=True)
    kinds = {row.kind for row in rows}
    assert kinds <= {"rejection", "block"}
    assert all(row.pair is None for row in rows if row.kind == "block")


def test_the_feed_honours_its_limit(seeded_reader: ConsoleReader) -> None:
    assert len(seeded_reader.feed(limit=5)) == 5


def test_history_carries_trades_and_rejections_newest_first(
    seeded_reader: ConsoleReader,
) -> None:
    """Two tables, each newest-first, on its own ordering key.

    Spec 21 is two tables rather than one interleaved list, so `history()` returns
    a `HistoryView` and the ordering has to be asserted on both halves — an
    earlier version of this test iterated the view itself, which walks pydantic's
    fields and not any row, and so asserted nothing about either table.

    The keys differ and that is why both are checked. A trade is ordered by
    `closed_at`, never `opened_at`: a trade opened earlier can close later, and
    the store orders on `closed_at` for exactly that reason. A rejection is
    ordered by `ts`.

    The distinctness guard above each ordering assertion is what gives it teeth. A
    column of identical timestamps is sorted ascending and descending at once, so
    without it a reader that returned rows in insertion order would pass.
    """
    history = seeded_reader.history()

    assert all(isinstance(row, TradeRowView) for row in history.trades)
    assert all(isinstance(row, RejectionRowView) for row in history.rejections)

    closed_at = [row.closed_at for row in history.trades]
    rejected_at = [row.ts for row in history.rejections]

    assert len(set(closed_at)) > 1, "seed must carry trades closing at different times"
    assert len(set(rejected_at)) > 1, "seed must carry rejections at different times"

    assert closed_at == sorted(closed_at, reverse=True)
    assert rejected_at == sorted(rejected_at, reverse=True)
    assert closed_at != sorted(closed_at)
    assert rejected_at != sorted(rejected_at)


def test_a_position_says_how_long_it_has_been_open(
    seeded_reader: ConsoleReader,
) -> None:
    """Spec 101: the age is shown, and it is computed here rather than in the view.

    Two facts an operator uses together — how long a position has been open, and when
    it times out — and neither means anything without the other. Before spec 101 the
    table rendered eight columns and none of them was age; Phase 1 rendered seeded rows
    and how old a fixture is was not a question anybody had.

    The age comes from the reader's injected clock and not from the view model, which is
    the rule `views.py` already states for `Staleness`: a view model working out its own
    age is a view model reading a clock, and the console has exactly one.
    """
    position = seeded_reader.positions()[0]
    assert position.age_us == max(seeded_reader.now_micros() - position.opened_at, 0)
    assert position.age_text
    assert position.age_text == format_age(position.age_us // 1000)


def test_the_age_is_not_the_staleness_and_the_two_can_disagree(
    seeded_reader: ConsoleReader,
) -> None:
    """Two ages on one row, answering two different questions.

    `staleness` is how old the **figures** are — it is what fades the row past
    `console.stale_after_ms`, and it is measured from `updated_at`, the last time the
    daemon touched the row. `age_us` is how long the **position** has been open, from
    `opened_at`. A position opened four hours ago and marked a second ago is old and
    fresh at once, and conflating them would either fade every long-held position or
    tell an operator a stale row was new.
    """
    position = seeded_reader.positions()[0]
    assert position.opened_at != position.staleness.age_us
    assert position.age_us >= position.staleness.age_us, (
        "a position cannot have been updated before it was opened"
    )


def test_a_console_clock_behind_the_row_reports_no_age_rather_than_a_negative_one(
    seeded_db: Path, seed_clock: Any
) -> None:
    """Two processes, two clock reads, and the console cannot fix the skew.

    The daemon writes `opened_at` and the console reads its own clock, so a console
    marginally behind the daemon produces a negative age. `format_age` already renders
    a negative as `0s` for exactly this reason; this pins the same answer one level up,
    so the number on the view model is never negative either — a negative age would
    read as a position that has not started yet.

    Driven by moving the **reader's** clock behind the seeded row rather than by
    arithmetic on the view, because the clamp lives in the reader and an assertion that
    recomputed it here would be checking its own sum.
    """
    behind = type(seed_clock)(seed_clock.now() - timedelta(days=365))
    reader = reader_for(seeded_db, behind)
    try:
        position = reader.positions()[0]
        assert reader.now_micros() < position.opened_at, "the clock is not actually behind"
        assert position.age_us == 0
        assert position.age_text == format_age(0)
    finally:
        reader.close()


def test_a_position_view_renders_every_figure_as_a_string_too(
    seeded_reader: ConsoleReader,
) -> None:
    """The screens must not each decide where the sign and the minus go."""
    position = seeded_reader.positions()[0]
    assert isinstance(position, PositionView)
    assert position.entry_price_text == str(position.entry_price)
    assert position.unrealised_pnl_pct_text.startswith(("+", MINUS_SIGN))
    assert position.staleness.stale_after_ms == STALE_AFTER_MS


# --------------------------------------------------------------------------- #
# Money never becomes a float
# --------------------------------------------------------------------------- #


def test_a_view_model_refuses_a_float_where_money_is_expected() -> None:
    """Refused at the boundary rather than coerced.

    A float that has already been constructed has already lost precision, so
    coercing it to `Decimal` preserves the wrong number exactly.
    """
    with pytest.raises(ValidationError, match="float"):
        StatusBand(
            mode="paper",
            state=IDLE,
            restarted=False,
            run_id=None,
            previous_run_id=None,
            balance=1000.0,  # type: ignore[arg-type]
            balance_text="1000.00",
            currency="USD",
            open_position_count=0,
            resting_order_count=0,
            equity_ts=None,
            staleness=None,
        )


def test_no_money_value_round_trips_through_float(seeded_reader: ConsoleReader) -> None:
    """Every money field arriving from the store is still a `Decimal` here."""
    band = seeded_reader.status_band(mode="paper")
    assert isinstance(band.balance, Decimal)
    for position in seeded_reader.positions():
        for value in (position.qty, position.entry_price, position.target_price):
            assert isinstance(value, Decimal)
            assert not isinstance(value, float)


def test_a_non_positive_stale_threshold_is_refused(seeded_db: Path, seed_clock: Any) -> None:
    """`console.stale_after_ms` is validated in `platform/config.py`; this is the
    second line, so a reader built by hand in a test cannot be built wrong."""
    with pytest.raises(ValueError, match="stale_after_ms"):
        ConsoleReader(seeded_db, clock=seed_clock, stale_after_ms=0)
