"""Engine 19 `memory`, part 2 — equity, positions, orders, trades, rejections. Spec 50.

**The governing rule of this file is that absent must mean nothing-to-record, never
record-a-zero.** Engines 18, 21 and 22 are Phase 6. Their `state` keys are absent today,
and an absent key is not a position count of zero, not an equity of zero, and not a
closed trade. Each of the five tables therefore has its own absent-is-not-zero test, and
the equity one is the dangerous case: a zero equity row is a 100% drawdown against any
earlier peak and would freeze the account on the first tick of a fresh install.

The `state` payloads here are fabricated — there is nothing else to publish them until
Phase 6 — but they are built through the **real** row contracts, dumped the way an
engine would have to publish them: `mode="json"`, so money crosses `state` as an exact
decimal string and never as a `Decimal` or a float.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.store.contracts import (
    OrderIntent,
    OrderRow,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionRow,
    PositionStatus,
    TradeOutcome,
    TradeRow,
    to_micros,
)
from acsoe.engines.memory.contracts import (
    BALANCES_FIELD,
    CLOSED_TRADES_FIELD,
    CYCLE_ID_KEY,
    EXCHANGE_KEY,
    EXIT_KEY,
    GUARD_BLOCKERS_KEY,
    ORDERS_FIELD,
    POSITION_MANAGER_KEY,
    POSITIONS_FIELD,
    POSITIONS_VALUE_FIELD,
    MissingInputError,
)
from acsoe.engines.memory.engine import MemoryEngine

RUN = "run-rows"
CURRENCY = "USD"


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #


@pytest.fixture
def context_at(fake_clients_with_store: Any, paper_config: Any, fixed_now: Any) -> Any:
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


def tick(cycle_id: int, **extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "system": {"mode": "running", "close_intent": False},
        CYCLE_ID_KEY: cycle_id,
        GUARD_BLOCKERS_KEY: [],
    }
    state.update(extra)
    return state


def balances(amount: str, currency: str = CURRENCY) -> dict[str, Any]:
    """`state["exchange"]` as engine 1 publishes it: money as an exact decimal string."""
    return {EXCHANGE_KEY: {BALANCES_FIELD: {currency: amount}, "fetched_at": 0}}


def rows_in(db_path: Path, table: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
    finally:
        conn.close()


def a_position(fixed_now: Any, position_id: str = "pos-1") -> dict[str, Any]:
    """One open position, as engine 21 will publish it, through the real contract."""
    stamp = to_micros(fixed_now)
    return PositionRow(
        position_id=position_id,
        run_id="whatever-the-publisher-said",
        cycle_id=999,
        pair="AAA/USD",
        base="AAA",
        quote="USD",
        status=PositionStatus.OPEN,
        qty=Decimal("3.5"),
        entry_price=Decimal("100.00"),
        target_price=Decimal("103.00"),
        stop_price=Decimal("98.50"),
        timeout_at=stamp + 43_200_000_000,
        opened_at=stamp,
        updated_at=stamp,
    ).model_dump(mode="json")


def a_resting_entry(fixed_now: Any, userref: int = 4242) -> dict[str, Any]:
    stamp = to_micros(fixed_now)
    return OrderRow(
        userref=userref,
        run_id="whatever-the-publisher-said",
        cycle_id=999,
        pair="AAA/USD",
        side=OrderSide.BUY,
        intent=OrderIntent.ENTRY,
        order_type=OrderType.LIMIT,
        oflags="post",
        status=OrderStatus.RESTING,
        qty=Decimal("3.5"),
        limit_price=Decimal("99.50"),
        filled_qty=Decimal("0"),
        placed_at=stamp,
        updated_at=stamp,
    ).model_dump(mode="json")


def a_closed_trade(fixed_now: Any, trade_id: str, pnl: str) -> dict[str, Any]:
    stamp = to_micros(fixed_now)
    return TradeRow(
        trade_id=trade_id,
        position_id="pos-1",
        run_id="whatever-the-publisher-said",
        cycle_id=999,
        pair="AAA/USD",
        base="AAA",
        quote="USD",
        qty=Decimal("3.5"),
        entry_price=Decimal("100.00"),
        exit_price=Decimal("101.00"),
        entry_fee=Decimal("0.35"),
        exit_fee=Decimal("0.35"),
        opened_at=stamp - 3_600_000_000,
        closed_at=stamp,
        outcome=TradeOutcome.TARGET,
        realised_pnl=Decimal(pnl),
        realised_pnl_pct=Decimal("0.01"),
        realised_pnl_quote=Decimal(pnl),
        reporting_currency=CURRENCY,
        fx_rate_entry=Decimal("1"),
        fx_rate_exit=Decimal("1"),
        updated_at=stamp,
    ).model_dump(mode="json")


def a_rejection(pair: str = "AAA/USD") -> dict[str, Any]:
    """`state` as it stands when the opportunity chain refused a candidate."""
    return {
        "scout": {"pair": pair},
        "trading_blocked_by": "cost",
        "block_reason": "Net edge -0.21% after fees",
        "cost": {
            "reason_code": "net_edge_below_hurdle",
            "expected_move_pct": "0.0191",
            "friction_pct": "0.0093",
            "net_edge_pct": "-0.0021",
            "hurdle_pct": "0.01395",
        },
    }


# --------------------------------------------------------------------------- #
# Absent is not zero — one per table, because each is a different wrong answer
# --------------------------------------------------------------------------- #


def test_a_tick_with_no_equity_information_writes_no_equity_row(
    context_at: Any, migrated_db: Path
) -> None:
    """**The dangerous one.** A zero equity row is a 100% drawdown.

    Engine 1's balances are absent whenever the fetch failed — invariant 2 — and on
    every tick before engine 1 exists at all. Writing a zero there would trip the
    breaker over a network blip, which is precisely the behaviour invariant 2 replaces
    with "block the trade", not "invent an account value".
    """
    result = MemoryEngine().process(context_at(0), tick(1))

    assert rows_in(migrated_db, "equity_snapshots") == []
    assert result.data["written"]["equity_snapshots"] == 0
    assert result.data["equity"] is None
    assert result.data["equity_skipped_reason"]


def test_a_failed_balance_fetch_is_not_an_equity_of_zero(
    context_at: Any, migrated_db: Path
) -> None:
    """`state["exchange"]` present, `balances` null — engine 1 ran and the fetch failed.

    A different fact from "engine 1 has not been built", and the engine reports which
    one it saw rather than collapsing them into a single silent skip.
    """
    result = MemoryEngine().process(
        context_at(0), tick(1, **{EXCHANGE_KEY: {BALANCES_FIELD: None, "fetched_at": 0}})
    )

    assert rows_in(migrated_db, "equity_snapshots") == []
    assert "fetch" in (result.data["equity_skipped_reason"] or "")
    assert EXCHANGE_KEY in result.data["sources_present"]


def test_a_balance_response_without_the_reporting_currency_writes_no_row(
    context_at: Any, migrated_db: Path
) -> None:
    """Balances arrived; none of them is the currency equity is reported in.

    Not hypothetical: that is what a balance response looks like for an account holding
    only crypto, or one whose reporting-currency balance is exactly zero and therefore
    omitted from the payload. Substituting a zero there writes a 100% drawdown into the
    curve.

    **This test exists because a mutation survived without it.** `_write_equity` has
    three separate ways to decide there is nothing to record — no `exchange` key, a null
    `balances`, and a `balances` mapping missing the currency — and the first two were
    covered while the third was not. Every line was executed by the suite; nothing
    asserted on the branch.
    """
    result = MemoryEngine().process(context_at(0), tick(1, **balances("7.5", "XBT")))

    assert rows_in(migrated_db, "equity_snapshots") == []
    assert CURRENCY in (result.data["equity_skipped_reason"] or "")
    assert result.data["equity"] is None


def test_an_absent_position_manager_writes_no_positions_and_no_orders(
    context_at: Any, migrated_db: Path
) -> None:
    """Engine 21 is Phase 6. Absent is nothing-to-record, not zero positions recorded."""
    MemoryEngine().process(context_at(0), tick(1, **balances("1000.00")))

    assert rows_in(migrated_db, "positions") == []
    assert rows_in(migrated_db, "orders") == []
    # The equity row still gets written, with a position count read from the store
    # rather than guessed from the absent key.
    snapshot = rows_in(migrated_db, "equity_snapshots")[0]
    assert snapshot["open_position_count"] == 0


def test_an_absent_exit_engine_writes_no_trade(context_at: Any, migrated_db: Path) -> None:
    MemoryEngine().process(context_at(0), tick(1, **balances("1000.00")))

    assert rows_in(migrated_db, "trades") == []


def test_a_tick_with_no_candidate_writes_no_rejection(
    context_at: Any, migrated_db: Path
) -> None:
    """The opportunity chain stopping without a candidate is not a rejection.

    On roughly fourteen ticks in fifteen, engine 5 `feature` returns PASS because no bar
    closed and the chain stops there. A writer that recorded a rejection per blocked
    tick would fill the console's history screen with candidates that never existed.
    """
    MemoryEngine().process(
        context_at(0),
        tick(1, trading_blocked_by="feature", block_reason="no bar closed"),
    )

    assert rows_in(migrated_db, "rejections") == []


def test_a_guard_chain_block_is_not_a_rejection(context_at: Any, migrated_db: Path) -> None:
    """A block record is one *tick*; a rejection is one *candidate*.

    `scout` can have published a candidate and `data_guard` can still block the tick
    afterwards — the guard chain runs first, but `state` carries both by the time engine
    19 runs on a tick where the daemon was mid-flight. The blocker being a guard is what
    settles it, and a writer keying off "a candidate exists" alone records a rejection
    for a candidate no gate ever judged.
    """
    state = tick(
        1,
        scout={"pair": "AAA/USD"},
        trading_blocked_by="data_guard",
        block_reason="stale candles",
    )
    state[GUARD_BLOCKERS_KEY] = [
        {"engine": "data_guard", "reason": "stale candles", "status": "BLOCK"}
    ]

    MemoryEngine().process(context_at(0), state)

    assert rows_in(migrated_db, "rejections") == []
    assert len(rows_in(migrated_db, "block_records")) == 1


# --------------------------------------------------------------------------- #
# What it writes when the payloads are there
# --------------------------------------------------------------------------- #


def test_positions_and_orders_are_stamped_with_the_recording_tick(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """Not with whatever `run_id` the publisher happened to carry.

    `(run_id, cycle_id)` is the join between a position and the block record for the
    tick, and a row carrying somebody else's run cannot be joined to anything.
    """
    MemoryEngine().process(
        context_at(0),
        tick(
            5,
            **{
                POSITION_MANAGER_KEY: {
                    POSITIONS_FIELD: [a_position(fixed_now)],
                    ORDERS_FIELD: [a_resting_entry(fixed_now)],
                }
            },
        ),
    )

    position = rows_in(migrated_db, "positions")[0]
    order = rows_in(migrated_db, "orders")[0]
    assert (position["run_id"], position["cycle_id"]) == (RUN, 5)
    assert (order["run_id"], order["cycle_id"]) == (RUN, 5)
    assert position["status"] == PositionStatus.OPEN.value
    assert order["status"] == OrderStatus.RESTING.value


def test_the_same_position_written_on_two_ticks_is_one_row(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """Engine 21 republishes every open position on every tick, for its whole life.

    An insert rather than an upsert fails on tick two with a primary-key violation, and
    a position that lives for twelve hours is seven hundred ticks.
    """
    engine = MemoryEngine()
    payload = {POSITION_MANAGER_KEY: {POSITIONS_FIELD: [a_position(fixed_now)]}}
    engine.process(context_at(0), tick(1, **payload))
    engine.process(context_at(1), tick(2, **payload))

    rows = rows_in(migrated_db, "positions")
    assert len(rows) == 1
    assert rows[0]["cycle_id"] == 2


def test_money_crosses_state_as_a_string_and_reaches_sqlite_as_a_string(
    context_at: Any, migrated_db: Path
) -> None:
    """The money columns are declared `ANY` with a `typeof` CHECK precisely so a float
    is refused rather than quietly stringified. This asserts the value that landed, not
    only that a row landed."""
    MemoryEngine().process(context_at(0), tick(1, **balances("1234.56")))

    snapshot = rows_in(migrated_db, "equity_snapshots")[0]
    assert snapshot["equity"] == "1234.56"
    assert isinstance(snapshot["equity"], str)
    assert snapshot["currency"] == CURRENCY


def test_a_float_balance_is_refused_rather_than_coerced(context_at: Any) -> None:
    """A float that has already been constructed has already lost precision, so
    coercing it to `Decimal` preserves the wrong number exactly."""
    with pytest.raises(MissingInputError, match="float"):
        MemoryEngine().process(
            context_at(0), tick(1, **{EXCHANGE_KEY: {BALANCES_FIELD: {CURRENCY: 1234.56}}})
        )


# --------------------------------------------------------------------------- #
# peak_equity, which is the mutation spec 50 names
# --------------------------------------------------------------------------- #


def test_peak_equity_is_the_running_maximum_read_from_the_store(
    context_at: Any, migrated_db: Path
) -> None:
    """**Never recomputed from `state`**, which is fresh every tick.

    An engine that took the maximum of this tick alone reports a peak equal to the
    current equity, a drawdown of permanently zero, and a breaker that never fires on a
    drawdown again. Nothing about that raises, and the equity curve still looks
    plausible on the console.
    """
    engine = MemoryEngine()
    engine.process(context_at(0), tick(1, **balances("1000.00")))
    engine.process(context_at(1), tick(2, **balances("900.00")))
    engine.process(context_at(2), tick(3, **balances("800.00")))

    rows = rows_in(migrated_db, "equity_snapshots")
    assert [row["equity"] for row in rows] == ["1000.00", "900.00", "800.00"]
    assert [row["peak_equity"] for row in rows] == ["1000.00", "1000.00", "1000.00"]
    # The drawdown `safety` would read off the latest row.
    latest = rows[-1]
    peak, equity = Decimal(latest["peak_equity"]), Decimal(latest["equity"])
    assert (peak - equity) / peak == Decimal("0.2")


def test_a_new_high_moves_the_peak(context_at: Any, migrated_db: Path) -> None:
    """The other half. A peak that only ever came from the store and never rose would
    also give a permanently wrong drawdown, in the opposite direction."""
    engine = MemoryEngine()
    engine.process(context_at(0), tick(1, **balances("1000.00")))
    engine.process(context_at(1), tick(2, **balances("1500.00")))

    rows = rows_in(migrated_db, "equity_snapshots")
    assert [row["peak_equity"] for row in rows] == ["1000.00", "1500.00"]


def test_realised_pnl_accumulates_across_ticks(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """`realised_pnl_cum` is the previous row's total plus this tick's closes.

    Recomputing it from this tick alone makes the Phase 7 alpha curve the last trade's
    PnL repeated, which is a chart that looks fine.
    """
    engine = MemoryEngine()
    engine.process(
        context_at(0),
        tick(
            1,
            **balances("1000.00"),
            **{EXIT_KEY: {CLOSED_TRADES_FIELD: [a_closed_trade(fixed_now, "t-1", "12.50")]}},
        ),
    )
    engine.process(
        context_at(1),
        tick(
            2,
            **balances("1012.50"),
            **{EXIT_KEY: {CLOSED_TRADES_FIELD: [a_closed_trade(fixed_now, "t-2", "-4.00")]}},
        ),
    )

    rows = rows_in(migrated_db, "equity_snapshots")
    assert [row["realised_pnl_cum"] for row in rows] == ["12.50", "8.50"]
    assert len(rows_in(migrated_db, "trades")) == 2


def test_equity_includes_the_value_of_open_positions(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """Equity is cash plus what the positions are worth, not the quote balance.

    Invariant 6 sizes against *total account equity*; a system holding one position and
    almost no cash would otherwise report itself as nearly broke and refuse to trade.
    """
    MemoryEngine().process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{
                POSITION_MANAGER_KEY: {
                    POSITIONS_FIELD: [a_position(fixed_now)],
                    POSITIONS_VALUE_FIELD: "350.00",
                    "unrealised_pnl": "12.50",
                }
            },
        ),
    )

    snapshot = rows_in(migrated_db, "equity_snapshots")[0]
    assert snapshot["cash"] == "500.00"
    assert snapshot["positions_value"] == "350.00"
    assert snapshot["equity"] == "850.00"
    assert snapshot["unrealised_pnl"] == "12.50"
    assert snapshot["open_position_count"] == 1


# --------------------------------------------------------------------------- #
# Rejections
# --------------------------------------------------------------------------- #


def test_the_position_count_comes_from_the_store_not_from_this_tick_s_state(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """A position opened on tick 1 is still open on tick 2 whatever `state` says.

    Whether engine 21 republishes every open position on every tick is engine 21's
    business, and it is Phase 6. The `positions` table is the record. A count taken from
    `state` reports the account as flat on any tick where the publisher said nothing,
    and `open_position_count` is what the Phase 7 attribution reads to tell a cash
    period from an invested one.

    **This test exists because a mutation survived without it.** Every earlier fixture
    happened to supply the same number on both sides, so no assertion could tell the two
    sources apart.
    """
    engine = MemoryEngine()
    engine.process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{POSITION_MANAGER_KEY: {POSITIONS_FIELD: [a_position(fixed_now)]}},
        ),
    )
    # Tick 2 publishes no position_manager key at all. The position is still open.
    engine.process(context_at(1), tick(2, **balances("500.00")))

    rows = rows_in(migrated_db, "equity_snapshots")
    assert [row["open_position_count"] for row in rows] == [1, 1]
    assert len(rows_in(migrated_db, "positions")) == 1


def test_a_rejection_carries_its_reason_code_and_its_economics(
    context_at: Any, migrated_db: Path
) -> None:
    """Invariant 12. The console maps `reason_code` to prose and renders `reason`; the
    economics are what make the refusal analysable in Phase 7."""
    MemoryEngine().process(context_at(0), tick(8, **a_rejection()))

    row = rows_in(migrated_db, "rejections")[0]
    assert row["pair"] == "AAA/USD"
    assert row["rejected_by"] == "cost"
    assert row["reason_code"] == "net_edge_below_hurdle"
    assert row["reason"] == "Net edge -0.21% after fees"
    assert row["net_edge_pct"] == "-0.0021"
    assert row["hurdle_pct"] == "0.01395"
    # It joins to the block record for the tick on `(run_id, cycle_id)`.
    assert (row["run_id"], row["cycle_id"]) == (RUN, 8)


def test_a_gate_that_publishes_no_economics_still_records_the_rejection(
    context_at: Any, migrated_db: Path
) -> None:
    """Engine 11 `risk` refuses a sub-`ordermin` position and publishes no net edge.

    Four nulls is the honest record. A writer that skipped the row because the
    economics were missing would lose every `risk` rejection, and invariant 12 puts a
    lost rejection on the same footing as a lost trade.
    """
    MemoryEngine().process(
        context_at(0),
        tick(
            2,
            scout={"pair": "BBB/USD"},
            trading_blocked_by="risk",
            block_reason="Below the pair's minimum order size",
            risk={"reason_code": "below_ordermin"},
        ),
    )

    row = rows_in(migrated_db, "rejections")[0]
    assert row["rejected_by"] == "risk"
    assert row["reason_code"] == "below_ordermin"
    assert row["net_edge_pct"] is None
    assert row["expected_move_pct"] is None


def test_a_refusal_without_a_reason_code_raises_rather_than_recording_a_silent_row(
    context_at: Any,
) -> None:
    """A rejection with no code renders as "No reason was recorded." on the history
    screen — silently, with no error anywhere. Failing the tick is the louder outcome
    and therefore the right one."""
    state = tick(3, **a_rejection())
    state["cost"] = {}

    with pytest.raises(MissingInputError, match="reason_code"):
        MemoryEngine().process(context_at(0), state)


def test_a_published_payload_of_the_wrong_shape_raises(context_at: Any) -> None:
    """"Engine 21 has not been built" and "engine 21 published something unreadable"
    are two different facts, and a broad `except` would record the second as the first —
    a tick logged as clean when the writer had failed on it."""
    with pytest.raises(MissingInputError, match="not a list of rows"):
        MemoryEngine().process(
            context_at(0), tick(1, **{POSITION_MANAGER_KEY: {POSITIONS_FIELD: "pos-1"}})
        )
