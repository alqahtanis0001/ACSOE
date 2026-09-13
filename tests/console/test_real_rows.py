"""The console on rows a live engine 19 wrote. Spec 57.

**A test that passes against a seeded database is not testing what this spec is for.**
The seed has filled these tables since Phase 1 and the console has rendered them since
Phase 1; what changed in Phase 4 is that engine 19 `memory` now writes them for real. So
every test here drives the real engine 19 over a database and asserts on a value **no
seed generator produces** — a pair named `ZZZ/QQQ`, a reason carrying four decimal
places, a `run_id` that names this test.

The second half of the file is about the cycle feed's read. It scanned the whole of
`block_records` from Phase 1 until now, which was harmless while the table held a seed
and stops being harmless the moment engine 19 writes a row per guard per tick.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import BlockStatus, RunMode, RunRow
from acsoe.console.format import NO_REASON_RECORDED, REASON_PROSE
from acsoe.console.reader import ConsoleReader
from acsoe.engines.memory.contracts import CYCLE_ID_KEY, GUARD_BLOCKERS_KEY
from acsoe.engines.memory.engine import MemoryEngine

RUN = "run-live-console"

#: Deliberately unlike anything `clients/store/seed.py` produces. If this string could
#: come from the seed, every assertion below would be satisfied by the database the
#: console has been reading since Phase 1.
LIVE_PAIR = "ZZZ/QQQ"
LIVE_REASON = "Net edge -0.4471% after fees"
LIVE_CODE = "net_edge_below_hurdle"


STALE_AFTER_MS = 120_000


def reader_for(db_path: Path, clock: Any) -> ConsoleReader:
    return ConsoleReader(db_path, clock=clock, stale_after_ms=STALE_AFTER_MS)


def tick(cycle_id: int, **extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "system": {"mode": "running", "close_intent": False},
        CYCLE_ID_KEY: cycle_id,
        GUARD_BLOCKERS_KEY: [],
    }
    state.update(extra)
    return state


def a_live_rejection() -> dict[str, Any]:
    return {
        "scout": {"pair": LIVE_PAIR},
        "trading_blocked_by": "cost",
        "block_reason": LIVE_REASON,
        "cost": {
            "reason_code": LIVE_CODE,
            "expected_move_pct": "0.0191",
            "friction_pct": "0.0093",
            "net_edge_pct": "-0.004471",
            "hurdle_pct": "0.01395",
        },
    }


@pytest.fixture
def live_db(
    seeded_db: Path,
    seed_clock: Any,
    paper_config: Any,
    fake_kraken: Any,
    fake_recorder: Any,
) -> Path:
    """The Phase 0 seed, **plus** rows a live engine 19 wrote on top of it.

    Seeded first on purpose. The console reads one table and cannot know which producer
    filled it, so a database holding only live rows would let an assertion pass for the
    wrong reason — "the only rows there are live" rather than "the screen found the live
    one". Here the seed's rows are present and the live one has to be picked out of them.
    """
    from tests.harness.doubles import FakeClients

    from acsoe.core.contracts import EngineContext

    # Five minutes past the seed's own instant, so the live rows are the newest in the
    # table and cannot fall off the end of a limit-bounded read.
    now = seed_clock.now() + timedelta(minutes=5)
    with StoreClient(seeded_db) as store:
        clients = FakeClients(kraken=fake_kraken, store=store, recorder=fake_recorder)
        context = EngineContext(
            mode="paper", run_id=RUN, now=now, config=paper_config, clients=clients
        )
        engine = MemoryEngine()
        engine.process(context, tick(11, **a_live_rejection()))
        later = EngineContext(
            mode="paper",
            run_id=RUN,
            now=now + timedelta(minutes=1),
            config=paper_config,
            clients=clients,
        )
        engine.process(
            later,
            tick(
                12,
                **{
                    GUARD_BLOCKERS_KEY: [
                        {"engine": "data_guard", "reason": "stale candles", "status": "BLOCK"},
                        {"engine": "safety", "reason": "drawdown past the limit", "status": "BLOCK"},
                    ]
                },
            ),
        )
        store.write_run(
            RunRow(
                run_id=RUN,
                mode=RunMode.PAPER,
                started_at=int(now.timestamp() * 1_000_000),
                updated_at=int(now.timestamp() * 1_000_000),
            )
        )
    return seeded_db


@pytest.fixture
def live_reader(live_db: Path, seed_clock: Any) -> Any:
    reader = reader_for(live_db, seed_clock)
    try:
        yield reader
    finally:
        reader.close()


# --------------------------------------------------------------------------- #
# The history screen
# --------------------------------------------------------------------------- #


def test_the_history_screen_renders_a_rejection_a_live_engine_19_wrote(
    live_reader: Any,
) -> None:
    """Asserted on values, not on the screen returning something.

    A rendering test that checked only that `history()` came back non-empty could not
    fail for the reason it exists: the seed alone satisfies it.
    """
    rejections = live_reader.history().rejections
    live = [row for row in rejections if row.pair == LIVE_PAIR]

    assert live, "the history screen is still showing only the seed"
    assert live[0].run_id == RUN
    assert live[0].reason == LIVE_REASON
    assert live[0].rejected_by == "cost"


def test_the_seed_and_the_live_rows_are_distinguishable_by_value(live_reader: Any) -> None:
    """The precondition the test above depends on, asserted rather than assumed.

    If the seed ever started producing a `ZZZ/QQQ` pair, the test above would go on
    passing while testing nothing. This is the assertion that notices.
    """
    rejections = live_reader.history().rejections
    seeded = [row for row in rejections if row.run_id != RUN]

    assert seeded, "the fixture has no seeded rejections, so it proves nothing"
    assert all(row.pair != LIVE_PAIR for row in seeded)
    assert all(row.reason != LIVE_REASON for row in seeded)


def test_the_live_rejection_does_not_render_as_no_reason_recorded(live_reader: Any) -> None:
    """A `reason_code` absent from `REASON_PROSE` renders as silence — no error, no log
    line, just a row with nothing in its reason column. That is the console's one
    genuinely silent failure and this is the assertion against it."""
    live = [row for row in live_reader.history().rejections if row.pair == LIVE_PAIR]

    assert live[0].reason != NO_REASON_RECORDED


def test_every_reason_code_engine_19_can_write_is_in_the_map() -> None:
    """Engine 19 copies the blocking gate's `reason_code` straight into the row, so the
    set of codes it can write is exactly the set the gates publish.

    Enumerated out of the producing modules rather than from a list here: a hand-written
    list agrees with itself, and the code an operator meets when something is broken is
    the one nobody remembered to add.
    """
    import importlib

    codes: set[str] = set()
    # `prediction` joined the list with spec 71. Engine 8 is not a registry gate and it
    # blocks under contract rule 6 all the same, so engine 19 copies its codes exactly as
    # it copies a gate's — and a code left out of this tuple is one the enumeration cannot
    # see, which is the same silence the enumeration exists to prevent.
    for name in ("scout", "cost", "risk", "safety", "prediction", "anomaly"):
        module = importlib.import_module(f"acsoe.engines.{name}.contracts")
        for attr, value in vars(module).items():
            if attr.startswith("REASON_") and isinstance(value, str):
                codes.add(value)

    assert codes, "no reason codes were found; the enumeration is broken, not the map"
    missing = sorted(code for code in codes if code not in REASON_PROSE)
    assert missing == [], f"engine 19 can write these and the console renders silence: {missing}"


# --------------------------------------------------------------------------- #
# The cycle feed's read
# --------------------------------------------------------------------------- #


def test_the_cycle_feed_no_longer_scans_the_whole_of_block_records(
    live_db: Path, seed_clock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asserted by making the unbounded read fail, not by reading the code.

    `recent_blocked_ticks` is bounded and `block_records_in_window(0, maxint)` is not,
    and the difference is invisible from the outside — both return correct rows in the
    right order. So the unbounded method is replaced with one that raises: a reader
    still calling it fails here, and one that has moved on does not.
    """
    reader = reader_for(live_db, seed_clock)

    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError(
            "the cycle feed called block_records_in_window; engine 19 writes a row per "
            "guard per tick and that read has no bound on it"
        )

    monkeypatch.setattr(reader._store, "block_records_in_window", refuse)
    try:
        rows = reader.feed()
        summary = reader.feed_summary()
    finally:
        reader.close()

    assert rows
    assert summary.blocked_tick_count > 0


def test_the_feed_renders_one_row_for_a_tick_two_guards_blocked(live_reader: Any) -> None:
    """The tick engine 19 wrote two `block_records` rows for is **one thing that
    happened**, and the row kept is the primary blocker.

    This is the property the bounded read had to preserve: truncating rows and then
    grouping can cut a tick in half and render it as blocked by the wrong engine, with
    nothing raising.
    """
    blocks = [row for row in live_reader.feed() if row.kind == "block"]
    live = [row for row in blocks if row.run_id == RUN]

    assert len(live) == 1
    assert live[0].engine == "data_guard"


def test_the_feed_is_bounded_by_its_limit_across_both_sources(live_reader: Any) -> None:
    assert len(live_reader.feed(limit=4)) == 4


def test_engine_19_wrote_both_block_rows_even_though_the_feed_shows_one(
    live_db: Path,
) -> None:
    """The feed folding a tick into one row must not be mistaken for engine 19 having
    written one row. Invariant 12 needs both; the screen needs one."""
    connection = sqlite3.connect(live_db)
    try:
        rows = connection.execute(
            "SELECT blocked_by, is_primary, status FROM block_records "
            "WHERE run_id = ? ORDER BY id",
            (RUN,),
        ).fetchall()
    finally:
        connection.close()

    assert [row[0] for row in rows] == ["data_guard", "safety"]
    assert [bool(row[1]) for row in rows] == [True, False]
    assert {row[2] for row in rows} == {BlockStatus.BLOCK.value}


def test_the_empty_state_names_engine_7_rather_than_the_engine_it_used_to_name(
    live_reader: Any,
) -> None:
    """The stale line carried over from the Phase 3 handoff.

    It said the universe filter was engine 4 and its counts arrived in Phase 2. It is
    engine 7 `scout` and it shipped in Phase 3, so the line was telling an operator to
    wait for something already built. The counts are still absent — nothing persists
    them — and the line must still not show a zero, because a zero there reads as "no
    pair qualified", which is a result.
    """
    stages = {stage.label: stage for stage in live_reader.feed_summary().stages}
    scanned = stages["Pairs scanned"]

    assert scanned.count is None
    assert "Phase 2" not in scanned.detail
    assert "engine 4" not in scanned.detail
    assert "engine 7" in scanned.detail
    assert stages["Entered the tradable universe"].count is None
