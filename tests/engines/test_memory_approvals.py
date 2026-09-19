"""Spec 133 — engine 19 records why a trade was approved.

The economics exist in `state` only on the tick engine 18 places the entry; the `trades` row
is written ticks later when engine 22 closes it. Engine 19 writes one `approvals` row (B's
migration 0006) on the placing tick and copies it onto the trade. These tests hold that
against the real store, with an absent figure recorded as absent and never zero, and then
drive a whole round trip through the real chain and recompute engine 10's four figures from
the inputs it read on the placing tick.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.engines.test_memory_rows import (
    a_closed_trade,
    balances,
    context_at,  # noqa: F401 - a fixture, used by name
    rows_in,
    tick,
)
from tests.engines.test_trade_chain_rehearsal import (  # A's rehearsal harness, reused whole
    _close_stores,  # noqa: F401 - an autouse fixture: closes the rehearsal's store
    trained,  # noqa: F401 - a fixture, used by name
    window,  # noqa: F401 - a fixture, used by name
)

from acsoe.engines.memory.contracts import (
    APPROVAL_TRADE_FIELDS,
    CLOSED_TRADES_FIELD,
    EXECUTION_KEY,
    EXIT_KEY,
    MissingInputError,
)
from acsoe.engines.memory.engine import MemoryEngine

USERREF = 777_001
PAIR = "AAA/USD"

#: Engine 10's four figures as it publishes them: exact decimal strings, trailing zeros kept,
#: so a test can tell a copy that kept the form from one that normalised it.
COST = {
    "pair": PAIR,
    "expected_move_pct": "0.018300",
    "friction_pct": "0.00650",
    "net_edge_pct": "0.011800",
    "hurdle_pct": "0.009750",
    "clears_hurdle": True,
}
RUN_IDS = {
    "prediction": {"model_run_id": "train-x-f390"},
    "anomaly": {"model_run_id": "anomaly-x-f390"},
    "skeptic": {"model_run_id": "skeptic-x-f390"},
}


def placing_tick(cycle_id: int, *, placed: bool = True, **extra: Any) -> dict[str, Any]:
    """The tick engine 18 placed an entry on, with engines 8, 10, 13 and 15's payloads."""
    state = tick(
        cycle_id,
        **balances("500.00"),
        scout={"pair": PAIR},
        cost=dict(COST),
        **RUN_IDS,
    )
    state[EXECUTION_KEY] = {"pair": PAIR, "userref": USERREF, "placed": placed, "orders": []}
    state.update(extra)
    return state


def closing_tick(cycle_id: int, fixed_now: Any, *, entry_userref: int | None) -> dict[str, Any]:
    trade = a_closed_trade(fixed_now, "trade-1", "3.15")
    trade["entry_userref"] = entry_userref
    return tick(cycle_id, **balances("500.00"), **{EXIT_KEY: {CLOSED_TRADES_FIELD: [trade]}})


# --------------------------------------------------------------------------- #
# The placing tick
# --------------------------------------------------------------------------- #


def test_the_placing_tick_writes_one_approval_with_engine_10s_figures(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    result = MemoryEngine().process(context_at(0), placing_tick(3))
    assert result.data["written"]["approvals"] == 1
    (row,) = rows_in(migrated_db, "approvals")
    assert (row["userref"], row["cycle_id"], row["pair"]) == (USERREF, 3, PAIR)
    assert [row[f] for f in ("expected_move_pct", "friction_pct", "net_edge_pct", "hurdle_pct")] == [
        "0.018300", "0.00650", "0.011800", "0.009750"
    ]
    assert (row["prediction_run_id"], row["anomaly_run_id"], row["skeptic_run_id"]) == (
        "train-x-f390", "anomaly-x-f390", "skeptic-x-f390",
    )


def test_an_order_found_already_placed_is_not_this_ticks_approval(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    result = MemoryEngine().process(context_at(0), placing_tick(3, placed=False))
    assert result.data["written"]["approvals"] == 0
    assert rows_in(migrated_db, "approvals") == []


def test_a_tick_with_no_engine_18_writes_no_approval(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = placing_tick(3)
    del state[EXECUTION_KEY]
    MemoryEngine().process(context_at(0), state)
    assert rows_in(migrated_db, "approvals") == []


def test_absent_economics_are_written_absent_not_zero(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = placing_tick(3)
    del state["cost"]
    del state["skeptic"]
    MemoryEngine().process(context_at(0), state)
    (row,) = rows_in(migrated_db, "approvals")
    assert [row[f] for f in ("expected_move_pct", "friction_pct", "net_edge_pct", "hurdle_pct")] == [
        None, None, None, None
    ]
    assert row["skeptic_run_id"] is None
    assert row["prediction_run_id"] == "train-x-f390"


def test_a_float_economic_is_refused_rather_than_laundered_into_a_string(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = placing_tick(3)
    state["cost"]["friction_pct"] = 0.0065
    with pytest.raises(MissingInputError, match=r"'friction_pct'\] is the float 0\.0065"):
        MemoryEngine().process(context_at(0), state)


def test_an_errored_engine_18_gets_no_approval_whatever_its_payload_says(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    state = placing_tick(
        3,
        trading_blocked_by="execution",
        block_reason="unhandled ExecutionError",
        block_status="ERROR",
    )
    MemoryEngine().process(context_at(0), state)
    assert rows_in(migrated_db, "approvals") == []


def test_a_second_approval_for_one_entry_is_refused_by_the_store(
    context_at: Any, migrated_db: Path  # noqa: F811
) -> None:
    MemoryEngine().process(context_at(0), placing_tick(3))
    with pytest.raises(sqlite3.IntegrityError):
        MemoryEngine().process(context_at(1), placing_tick(4))


# --------------------------------------------------------------------------- #
# The closing tick
# --------------------------------------------------------------------------- #


def test_the_trade_carries_its_placing_ticks_approval(
    context_at: Any, migrated_db: Path, fixed_now: Any  # noqa: F811
) -> None:
    engine = MemoryEngine()
    engine.process(context_at(0), placing_tick(3))
    engine.process(context_at(90), closing_tick(94, fixed_now, entry_userref=USERREF))
    (trade,) = rows_in(migrated_db, "trades")
    assert [trade[f] for f in APPROVAL_TRADE_FIELDS] == [
        "0.018300", "0.00650", "0.011800", "0.009750",
        "train-x-f390", "anomaly-x-f390", "skeptic-x-f390",
    ]
    assert trade["cycle_id"] == 94, "the trade is the closing tick's row"


def test_a_trade_with_no_recorded_approval_is_written_with_the_fields_absent(
    context_at: Any, migrated_db: Path, fixed_now: Any  # noqa: F811
) -> None:
    MemoryEngine().process(context_at(90), closing_tick(94, fixed_now, entry_userref=USERREF))
    (trade,) = rows_in(migrated_db, "trades")
    assert [trade[f] for f in APPROVAL_TRADE_FIELDS] == [None] * 7


def test_a_trade_with_no_entry_userref_is_written_with_the_fields_absent(
    context_at: Any, migrated_db: Path, fixed_now: Any  # noqa: F811
) -> None:
    engine = MemoryEngine()
    engine.process(context_at(0), placing_tick(3))
    engine.process(context_at(90), closing_tick(94, fixed_now, entry_userref=None))
    (trade,) = rows_in(migrated_db, "trades")
    assert [trade[f] for f in APPROVAL_TRADE_FIELDS] == [None] * 7


def test_another_entrys_approval_is_not_copied(
    context_at: Any, migrated_db: Path, fixed_now: Any  # noqa: F811
) -> None:
    engine = MemoryEngine()
    engine.process(context_at(0), placing_tick(3))
    engine.process(context_at(90), closing_tick(94, fixed_now, entry_userref=USERREF + 1))
    (trade,) = rows_in(migrated_db, "trades")
    assert [trade[f] for f in APPROVAL_TRADE_FIELDS] == [None] * 7


# --------------------------------------------------------------------------- #
# Spec 133's Check When Done: a round trip through the real chain
# --------------------------------------------------------------------------- #


def test_a_rehearsed_round_trips_trade_carries_engine_10s_figures_recomputed(
    tmp_path: Path, trained: Any, window: Any  # noqa: F811
) -> None:
    """The whole chain places, fills and stops out one trade (A's rehearsal harness). The
    trade's four figures must equal engine 10's arithmetic redone here from the inputs it read
    on the placing tick: engine 8's expected move, engine 1's fee tier, engine 3's spread,
    engine 9's slippage, and the configured hurdle multiple. Not read back from engine 10."""
    from tests.engines.test_trade_chain_rehearsal import (
        SPREAD,
        TICK,
        TRADED,
        build,
        the_entry,
        the_fill,
    )

    rehearsal = build(tmp_path, trained, window)
    entry, placing = the_entry(rehearsal)
    filled, _ = the_fill(rehearsal, entry)

    fees = placing["exchange"]["fee_tier"]
    friction = (
        Decimal(fees["maker_fee_pct"])
        + Decimal(fees["taker_fee_pct"])
        + Decimal(placing["market_sensor"]["quotes"][TRADED]["spread_pct"])
        + Decimal(placing["order_book"]["estimated_slippage_pct"])
    )
    expected_move = Decimal(placing["prediction"]["expected_move_pct"])
    multiple = Decimal(repr(rehearsal.config.get("trading.hurdle_multiple")))

    touched = filled.opened_at // 1_000_000 + 30
    exit_bid = (filled.stop - Decimal("0.6")).quantize(Decimal("0.001"))
    rehearsal.trade(datetime.fromtimestamp(touched, tz=UTC), filled.stop - Decimal("0.5"))
    rehearsal.quote(exit_bid, exit_bid + SPREAD)
    closing = rehearsal.tick(
        datetime.fromtimestamp(filled.opened_at // 1_000_000 + TICK, tz=UTC), check=False
    )
    assert closing["exit"]["closed_trades"], closing["exit"]

    (trade,) = rehearsal.store.recent_closed_trades(limit=10)
    assert trade.entry_userref == entry.userref
    assert trade.expected_move_pct == expected_move
    assert trade.friction_pct == friction
    assert trade.net_edge_pct == expected_move - friction
    assert trade.hurdle_pct == multiple * friction
    assert trade.prediction_run_id == placing["prediction"]["model_run_id"]
    assert trade.anomaly_run_id == placing["anomaly"]["model_run_id"]
    assert trade.skeptic_run_id == placing["skeptic"]["model_run_id"]
    assert trade.prediction_run_id is not None
