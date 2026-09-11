"""Engine 19 `memory`, part 1 — the block record on every blocked tick. Spec 49.

`safety` derives its outage count from `block_records`, and **a missed row does not
fail — it makes the breaker inert, silently, with every test green.** So every
assertion here was written, then broken, then watched go red; the mutations and the
messages they produced are in `docs/build-log/phase-4/c-interface.md`.

**The store is the real `StoreClient` over a temporary database.** A store double that
accepts any row and remembers nothing cannot fail a test about what was written, and
this whole file is a test about what was written.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.store.contracts import BlockStatus
from acsoe.core.contracts import EngineStatus
from acsoe.engines.memory.contracts import (
    CYCLE_ID_KEY,
    GUARD_BLOCKERS_KEY,
    STATE_KEY,
    MissingInputError,
)
from acsoe.engines.memory.engine import MemoryEngine

RUN = "run-memory"


def blocker(engine: str, reason: str, status: str = "BLOCK") -> dict[str, Any]:
    """One entry of `state["guard_blockers"]`, in the orchestrator's own shape."""
    return {"engine": engine, "reason": reason, "status": status}


def tick_state(cycle_id: int, *blockers: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "system": {"mode": "running", "close_intent": False},
        CYCLE_ID_KEY: cycle_id,
        GUARD_BLOCKERS_KEY: list(blockers),
    }
    if blockers:
        state["trading_blocked_by"] = blockers[0]["engine"]
        state["block_reason"] = blockers[0]["reason"]
    return state


def block_rows(db_path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM block_records ORDER BY ts, rowid"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


@pytest.fixture
def context_at(fake_clients_with_store: Any, paper_config: Any, fixed_now: Any) -> Any:
    """A factory for an `EngineContext` at a given offset from the fixed instant."""
    from acsoe.core.contracts import EngineContext

    def make(minutes: int = 0, run_id: str = RUN) -> EngineContext:
        return EngineContext(
            mode="paper",
            run_id=run_id,
            now=fixed_now + timedelta(minutes=minutes),
            config=paper_config,
            clients=fake_clients_with_store,
        )

    return make


# --------------------------------------------------------------------------- #
# The three cases spec 48 criterion 1 names, each hiding a different bug
# --------------------------------------------------------------------------- #


def test_a_blocked_tick_with_no_candidate_still_writes_a_row(
    context_at: Any, migrated_db: Path
) -> None:
    """`data_guard` blocked and nothing ever produced a candidate.

    This is the common case, not the edge case: `data_guard` blocks in the guard chain,
    which runs before the opportunity chain, so no candidate can exist. An implementer
    reading invariant 12 as "rejections are logged" writes nothing here, and the outage
    counter is then built from a table that is empty on exactly the ticks it counts.
    """
    state = tick_state(1, blocker("data_guard", "stale candles"))
    assert "scout" not in state  # nothing anywhere in this tick names a pair

    result = MemoryEngine().process(context_at(0), state)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    rows = block_rows(migrated_db)
    assert len(rows) == 1
    assert rows[0]["blocked_by"] == "data_guard"
    assert rows[0]["block_reason"] == "stale candles"
    assert bool(rows[0]["is_primary"]) is True
    assert rows[0]["run_id"] == RUN
    assert rows[0]["cycle_id"] == 1


def test_two_guards_blocking_at_once_write_two_rows_primary_on_the_first(
    context_at: Any, migrated_db: Path
) -> None:
    """The guard chain never breaks early, so `data_guard` and `safety` can both block.

    One row per tick passes a naive count and destroys invariant 12: the tick where the
    breaker fired during an outage would record the outage and lose the breaker.
    """
    MemoryEngine().process(
        context_at(0),
        tick_state(
            4,
            blocker("data_guard", "stale candles"),
            blocker("safety", "drawdown past the limit"),
        ),
    )

    rows = block_rows(migrated_db)
    assert [row["blocked_by"] for row in rows] == ["data_guard", "safety"]
    assert [bool(row["is_primary"]) for row in rows] == [True, False]
    assert {row["cycle_id"] for row in rows} == {4}


def test_an_unblocked_tick_writes_no_row(context_at: Any, migrated_db: Path) -> None:
    """A row on every tick makes the outage run indistinguishable from the uptime."""
    result = MemoryEngine().process(context_at(0), tick_state(9))

    assert block_rows(migrated_db) == []
    assert result.data["written"]["block_records"] == 0


def test_an_error_status_reaches_the_column_as_the_string_error(
    context_at: Any, migrated_db: Path
) -> None:
    """Not `EngineStatus.ERROR`, and the difference is the whole error-rate input.

    `safety` counts the error rate with `status = 'ERROR'`. Under `(str, Enum)` rather
    than `StrEnum`, `str(EngineStatus.ERROR)` is `'EngineStatus.ERROR'`, the comparison
    matches nothing, and the count reads zero forever without raising anywhere.
    """
    MemoryEngine().process(
        context_at(0),
        tick_state(2, blocker("market_sensor", "engine raised", status="ERROR")),
    )

    rows = block_rows(migrated_db)
    assert len(rows) == 1
    # Asserted against the *column*, as a plain string, because that is what the
    # breaker's SQL compares against. Comparing against `BlockStatus.ERROR` would pass
    # under the defect this test exists to catch, since the enum compares equal to its
    # own value either way.
    assert rows[0]["status"] == "ERROR"
    assert rows[0]["status"] == BlockStatus.ERROR.value
    assert "EngineStatus" not in str(rows[0]["status"])


# --------------------------------------------------------------------------- #
# The tick identity, and what happens when it is not there
# --------------------------------------------------------------------------- #


def test_rows_across_a_restart_keep_their_own_run_id(
    context_at: Any, migrated_db: Path
) -> None:
    """`cycle_id` restarts at 1 with the process, so it identifies nothing alone.

    `safety` walks this table ordered by `ts` across `run_id`s precisely because a
    daemon that dies mid-outage and comes back must not reset the clock on an outage
    that is still happening.
    """
    engine = MemoryEngine()
    engine.process(context_at(0, run_id="run-a"), tick_state(7, blocker("data_guard", "x")))
    engine.process(context_at(1, run_id="run-b"), tick_state(1, blocker("data_guard", "y")))

    rows = block_rows(migrated_db)
    assert [(row["run_id"], row["cycle_id"]) for row in rows] == [("run-a", 7), ("run-b", 1)]
    assert rows[0]["ts"] < rows[1]["ts"]


def test_an_absent_guard_blockers_key_raises_rather_than_recording_a_clean_tick(
    context_at: Any,
) -> None:
    """The contract says an empty list on an unblocked tick, **never absent**.

    Treating absent as empty would make "the orchestrator did not populate it" and
    "nothing blocked" the same reading, and the first of those is a tick whose blocks
    were silently discarded.
    """
    state = tick_state(1)
    del state[GUARD_BLOCKERS_KEY]

    with pytest.raises(MissingInputError, match="never absent"):
        MemoryEngine().process(context_at(0), state)


def test_a_tick_without_a_cycle_id_raises(context_at: Any) -> None:
    """A row that cannot name its tick cannot be counted as consecutive with another."""
    state = tick_state(1, blocker("data_guard", "x"))
    del state[CYCLE_ID_KEY]

    with pytest.raises(MissingInputError, match="run_id, cycle_id"):
        MemoryEngine().process(context_at(0), state)


def test_a_second_primary_on_one_tick_is_refused_by_the_database(
    context_at: Any, migrated_db: Path
) -> None:
    """`ux_block_records_primary` is `(run_id, cycle_id)`, and it is not to be caught.

    Driving the same tick twice is the shape of the defect: an engine that wrote its
    rows more than once per tick, or an orchestrator that ran the manage chain twice.
    The database refusing it is the visible symptom; catching the exception to keep the
    tick alive would replace that symptom with a duplicate outage count.
    """
    engine = MemoryEngine()
    state = tick_state(3, blocker("data_guard", "x"))
    engine.process(context_at(0), state)

    with pytest.raises(sqlite3.IntegrityError):
        engine.process(context_at(0), state)


# --------------------------------------------------------------------------- #
# What the engine publishes
# --------------------------------------------------------------------------- #


def test_the_engine_publishes_counts_even_on_a_tick_that_wrote_nothing(
    context_at: Any,
) -> None:
    """Zeros included, so "ran and recorded nothing" is legible in a log line.

    A payload that omitted the zeros would make that state indistinguishable from
    "engine 19 did not run", which is the one thing an operator needs to be able to
    tell apart when the tables look empty.
    """
    result = MemoryEngine().process(context_at(0), tick_state(5))

    data = result.data
    assert data["cycle_id"] == 5
    assert data["run_id"] == RUN
    assert data["written"]["block_records"] == 0
    assert data["rows_written"] == 0
    assert data["equity_skipped_reason"]  # no state["exchange"] on this tick


def test_the_engine_writes_exactly_one_state_key(context_at: Any) -> None:
    """Contract rule 2. The orchestrator assigns `state[engine.name] = result.data`, so
    what this asserts is that the engine itself mutated nothing on the way past."""
    state = tick_state(6, blocker("data_guard", "x"))
    before = set(state)

    MemoryEngine().process(context_at(0), state)

    assert set(state) == before
    assert STATE_KEY not in state


def test_it_is_not_a_gate() -> None:
    """`is_gate = False`, and `bootstrap.py`'s registry table is checked against it by
    `is_gate_matches_registry`. Engine 19 records; it never refuses."""
    assert MemoryEngine.is_gate is False
    assert MemoryEngine.name == "memory"
    assert MemoryEngine.number == 19
