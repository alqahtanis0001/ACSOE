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
    EXECUTION_KEY,
    EXIT_KEY,
    GUARD_BLOCKERS_KEY,
    HOLD_REASON_FIELD,
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
        # The orchestrator publishes the status beside the name and the reason, in both
        # chains. A gate that refused is `BLOCK`; spec 104's tests below vary it.
        "block_status": "BLOCK",
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

    **Both ticks now publish a mark, and that is spec 98 rather than a workaround.** Until
    spec 98 an absent `positions_value` read as `Decimal(0)`, so this test was green over
    two equity rows that valued an open position at nothing — and on tick 2, where `state`
    said nothing at all, the row it asserted `open_position_count == 1` on carried an
    equity of cash alone. Engine 19 now writes no row in that case, so the mark has to be
    supplied for the count assertion to be reachable at all. The subject is sharper for it:
    tick 2's `state` carries a mark and **no positions list**, so the store says one open
    position while `state` says none, and a count taken from `state` reports zero.
    """
    engine = MemoryEngine()
    engine.process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{
                POSITION_MANAGER_KEY: {
                    POSITIONS_FIELD: [a_position(fixed_now)],
                    "positions_value": "350.00",
                    "unrealised_pnl": "0.00",
                }
            },
        ),
    )
    # Tick 2 publishes a mark and no positions list. The position is still open.
    engine.process(
        context_at(1),
        tick(
            2,
            **balances("500.00"),
            **{POSITION_MANAGER_KEY: {"positions_value": "352.10", "unrealised_pnl": "2.10"}},
        ),
    )

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


# --------------------------------------------------------------------------- #
# Spec 98 — engines 18 and 22 reach the store, and an unmarked position does not
# become a drawdown
# --------------------------------------------------------------------------- #
#
# Engine 19 is the single writer of relational rows, so a row engine 18 or 22 publishes
# and engine 19 does not read is a row that never exists. The tests below are in two
# groups: the three new sources, and the equity defect the lead found while confirming
# the first group.


def a_filled_entry(fixed_now: Any, userref: int = 4242) -> dict[str, Any]:
    """The same order as `a_resting_entry`, filled. Engine 18 places, 21 resolves."""
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
        status=OrderStatus.CANCELLED,
        qty=Decimal("3.5"),
        limit_price=Decimal("99.50"),
        filled_qty=Decimal("0"),
        placed_at=stamp,
        updated_at=stamp,
    ).model_dump(mode="json")


def an_exit_order(fixed_now: Any, userref: int = 7777) -> dict[str, Any]:
    stamp = to_micros(fixed_now)
    return OrderRow(
        userref=userref,
        run_id="whatever-the-publisher-said",
        cycle_id=999,
        pair="AAA/USD",
        side=OrderSide.SELL,
        intent=OrderIntent.EXIT,
        order_type=OrderType.LIMIT,
        oflags="post",
        status=OrderStatus.RESTING,
        qty=Decimal("3.5"),
        limit_price=Decimal("103.00"),
        filled_qty=Decimal("0"),
        placed_at=stamp,
        updated_at=stamp,
    ).model_dump(mode="json")


def a_closed_position(fixed_now: Any, position_id: str = "pos-1") -> dict[str, Any]:
    """The same position as `a_position`, as engine 22 publishes it once it is closed."""
    closed = dict(a_position(fixed_now, position_id))
    closed["status"] = PositionStatus.CLOSED.value
    return closed


def test_the_entry_order_engine_18_places_reaches_the_store(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """Spec 98's first new source, and the one with no other route into the store.

    Engine 18 runs on the **opportunity** chain and engine 19 on the manage chain, both
    on the same tick. Before this spec engine 19 read `orders` from engine 21 alone, so
    an entry placed and then filled or cancelled before engine 21 next published it would
    have no `orders` row at all — and `orders` is where the `userref` idempotency check
    invariant 8 requires is answered from.
    """
    MemoryEngine().process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{EXECUTION_KEY: {ORDERS_FIELD: [a_resting_entry(fixed_now)]}},
        ),
    )
    rows = rows_in(migrated_db, "orders")
    assert [row["userref"] for row in rows] == [4242]
    assert rows[0]["status"] == OrderStatus.RESTING.value
    assert rows[0]["run_id"] == RUN, (
        "engine 19 stamps the tick that recorded the row; a publisher's run_id cannot be "
        "joined to that tick's block record"
    )


def test_the_exit_orders_and_closed_positions_engine_22_publishes_reach_the_store(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """Spec 98's other two new sources. Engine 22 already had `closed_trades` read; its
    orders and its positions did not, so an exit order was placed and recorded nowhere
    and a position closed by engine 22 stayed `open` in the table forever."""
    MemoryEngine().process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{
                EXIT_KEY: {
                    ORDERS_FIELD: [an_exit_order(fixed_now)],
                    POSITIONS_FIELD: [a_closed_position(fixed_now)],
                }
            },
        ),
    )
    orders = rows_in(migrated_db, "orders")
    positions = rows_in(migrated_db, "positions")
    assert [row["userref"] for row in orders] == [7777]
    assert [row["status"] for row in positions] == [PositionStatus.CLOSED.value]


def test_an_absent_execution_or_exit_key_records_nothing_and_not_a_zero(
    context_at: Any, migrated_db: Path
) -> None:
    """The governing rule of this file, extended to the three new sources.

    Fourteen ticks in fifteen close no decision bar, so engine 18 is absent on almost
    every tick, and absent on a bar tick where the chain stopped at an earlier gate.
    `sources_present` is what keeps "did not publish" distinguishable from "published
    nothing" — a count of zero cannot.
    """
    result = MemoryEngine().process(context_at(0), tick(1, **balances("500.00")))
    assert rows_in(migrated_db, "orders") == []
    assert rows_in(migrated_db, "positions") == []
    assert result.data["written"]["orders"] == 0
    assert EXECUTION_KEY not in result.data["sources_present"]
    assert EXIT_KEY not in result.data["sources_present"]


def test_execution_is_named_in_sources_present_when_it_published(
    context_at: Any, fixed_now: Any
) -> None:
    """The other half, so the test above is not satisfied by an engine that never names
    any source at all."""
    result = MemoryEngine().process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{EXECUTION_KEY: {ORDERS_FIELD: [a_resting_entry(fixed_now)]}},
        ),
    )
    assert EXECUTION_KEY in result.data["sources_present"]


def test_a_placement_and_its_same_tick_cancel_end_as_cancelled(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """Spec 98 step 4, tested rather than assumed.

    Engine 18 places an entry on the opportunity chain and engine 21 cancels it on the
    manage chain, same tick, same `userref`. `write_order` upserts, so the stored row is
    whichever engine 19 wrote **last** — and engine 18 runs first, so 18's row must be
    written first and 21's must overwrite it. The reverse order stores a cancelled order
    as resting, which is a live post-only buy as far as anything reading the table is
    concerned, and invariant 8 is about exactly that order.

    One row, not two: the assertion is on the count as well as the status, because an
    upsert that had silently become an insert would leave both rows present and the
    status assertion would pass on whichever came back first.
    """
    MemoryEngine().process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{
                EXECUTION_KEY: {ORDERS_FIELD: [a_resting_entry(fixed_now)]},
                POSITION_MANAGER_KEY: {ORDERS_FIELD: [a_filled_entry(fixed_now)]},
            },
        ),
    )
    rows = rows_in(migrated_db, "orders")
    assert len(rows) == 1, f"the upsert on userref did not collapse the two writes: {rows}"
    assert rows[0]["status"] == OrderStatus.CANCELLED.value, (
        "the placement overwrote the cancel, so a cancelled entry is stored as resting — "
        "which is a live post-only buy to everything that reads this table"
    )


def test_a_position_marked_and_closed_on_one_tick_ends_closed(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """The same rule for `positions`, and the lead's ruling of 2026-09-16.

    Engine 21 marks every open position and engine 22 closes the ones that hit a barrier,
    both on the same tick and both publishing a row for the same `position_id`. Engine 22
    runs after 21 in the manage chain, so closed must win. Written the other way, a
    position closed this tick is stored as open with a mark on it — a row the console
    renders as a live position and `safety` counts towards its escalation precondition.
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
                    "unrealised_pnl": "0.00",
                },
                EXIT_KEY: {POSITIONS_FIELD: [a_closed_position(fixed_now)]},
            },
        ),
    )
    rows = rows_in(migrated_db, "positions")
    assert len(rows) == 1, f"the upsert on position_id did not collapse the two writes: {rows}"
    assert rows[0]["status"] == PositionStatus.CLOSED.value, (
        "engine 21's mark overwrote engine 22's close, so a position closed this tick is "
        "stored as open"
    )


def test_the_hold_reason_is_written_and_then_cleared(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """B3's column, and the condition that makes it safe rather than misleading.

    Engine 21 publishes `hold_reason` once per tick, not per position, and engine 19 is
    the only writer of the column. **The clearing half is the load-bearing one**: a hold
    written and never cleared renders an hour-old hold forever and reports a paused
    manage chain over one running normally. `write_position` upserts every column, so
    writing `None` on a tick that did not hold is what clears it — and skipping the
    assignment instead would carry it forward, which is the defect this pins.

    B3 pins the same property at the store boundary. This pins it **through engine 19**,
    which is where it can actually go wrong: the store cannot know whether engine 19
    chose not to write the field or engine 21 chose not to publish one.

    **The two sources are given different values on purpose, and the first version of
    this test did not do that.** `a_position` dumps a real `PositionRow`, which carries
    `hold_reason: None` as a model default — so the *row* already said null on tick 2,
    the column came out null whether or not engine 19 assigned anything, and a mutation
    setting the field only when there is a reason survived the whole sweep. Here tick 2's
    row carries a **stale** reason, which is not a contrivance: engine 21 builds its
    published rows from the open positions it read out of the store, so last tick's value
    is exactly what comes back. Only engine 19's tick-level assignment can clear it.
    """
    engine = MemoryEngine()

    def marked(row: dict[str, Any]) -> dict[str, Any]:
        return {
            POSITIONS_FIELD: [row],
            POSITIONS_VALUE_FIELD: "350.00",
            "unrealised_pnl": "0.00",
        }

    fresh = a_position(fixed_now)
    assert fresh[HOLD_REASON_FIELD] is None, (
        "the row already carries a hold reason, so tick 1 cannot show that engine 19 is "
        "the one that put it there"
    )
    engine.process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{POSITION_MANAGER_KEY: {**marked(fresh), HOLD_REASON_FIELD: "data_guard"}},
        ),
    )
    assert [row["hold_reason"] for row in rows_in(migrated_db, "positions")] == ["data_guard"], (
        "the row said null and the tick said `data_guard`, so a stored null means engine "
        "19 is not applying the tick's reason at all"
    )

    # Tick 2 did not hold. The row still carries last tick's reason, because engine 21
    # republishes what the store gave it; the tick-level key is absent.
    stale = {**a_position(fixed_now), HOLD_REASON_FIELD: "data_guard"}
    engine.process(
        context_at(1), tick(2, **balances("500.00"), **{POSITION_MANAGER_KEY: marked(stale)})
    )
    assert [row["hold_reason"] for row in rows_in(migrated_db, "positions")] == [None], (
        "last tick's hold reason survived a tick that did not hold, so the console shows "
        "an hour-old hold on a manage chain that is running normally"
    )


# --- the equity defect ------------------------------------------------------ #


def test_an_open_position_with_no_mark_writes_no_equity_row(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """The defect, and it is the most expensive thing in spec 98.

    `decimal_field` returns `Decimal(0)` for an absent field. That is right for a flat
    account and catastrophic for an invested one: `equity = cash + 0` drops the position's
    entire value out of that tick of the series, and engine 17 computes
    `(peak_equity - equity) / peak_equity` against a peak read from the store. On a fully
    invested account one unmarked tick is a drawdown approaching 100% against a
    `safety.max_drawdown_pct` of 0.10 — the account freezes over a missing quote.

    Spec 92 has engine 21 publish `positions_value` **absent**, never zero, precisely so
    this is detectable. It is only detectable if the two cases are told apart, and the
    default made them identical.
    """
    MemoryEngine().process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{POSITION_MANAGER_KEY: {POSITIONS_FIELD: [a_position(fixed_now)]}},
        ),
    )
    assert rows_in(migrated_db, "equity_snapshots") == [], (
        "an equity row was written valuing an open position at nothing, which is a "
        "drawdown that did not happen"
    )
    assert len(rows_in(migrated_db, "positions")) == 1, (
        "the position itself must still be recorded; the skip is the equity row alone"
    )


def test_the_skipped_equity_row_says_why(
    context_at: Any, fixed_now: Any
) -> None:
    """A silent gap in the equity curve is indistinguishable from a silent bug, which is
    why `equity_skipped_reason` exists and why this asserts on it rather than only on the
    absence of a row."""
    result = MemoryEngine().process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{POSITION_MANAGER_KEY: {POSITIONS_FIELD: [a_position(fixed_now)]}},
        ),
    )
    reason = result.data["equity_skipped_reason"]
    assert reason is not None
    assert POSITIONS_VALUE_FIELD in reason, reason
    assert "1 open position" in reason, reason
    assert result.data["written"]["equity_snapshots"] == 0


def test_a_flat_account_still_writes_its_equity_row(
    context_at: Any, migrated_db: Path
) -> None:
    """The other half, and without it the fix is satisfied by an engine that never writes
    an equity row at all — which would be a silent, permanent hole in the one series the
    drawdown breaker reads.

    With no open position, an absent `positions_value` is not a missing mark: there is
    nothing to mark, `cash` is the whole of equity, and the row stands. These two tests
    differ in exactly one input — whether a position was published — and that is the
    distinction `decimal_field`'s default could not make.
    """
    result = MemoryEngine().process(context_at(0), tick(1, **balances("500.00")))
    rows = rows_in(migrated_db, "equity_snapshots")
    assert len(rows) == 1, "a flat account wrote no equity row"
    assert rows[0]["equity"] == "500.00"
    assert rows[0]["open_position_count"] == 0
    assert result.data["equity_skipped_reason"] is None


def test_an_open_position_with_a_mark_writes_the_marked_equity(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """The third case, so "skip when invested" is not satisfied by skipping always.

    The witness rule: `cash` and `positions_value` are given **different** values, so an
    engine that summed the wrong one twice, or dropped either, produces a number this
    assertion can see. Exact `Decimal`, never `approx` — this is money.
    """
    MemoryEngine().process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{
                POSITION_MANAGER_KEY: {
                    POSITIONS_FIELD: [a_position(fixed_now)],
                    POSITIONS_VALUE_FIELD: "352.10",
                    "unrealised_pnl": "2.10",
                }
            },
        ),
    )
    rows = rows_in(migrated_db, "equity_snapshots")
    assert len(rows) == 1
    assert Decimal(rows[0]["equity"]) == Decimal("500.00") + Decimal("352.10")
    assert Decimal(rows[0]["cash"]) == Decimal("500.00")
    assert Decimal(rows[0]["positions_value"]) == Decimal("352.10")
    assert Decimal(rows[0]["unrealised_pnl"]) == Decimal("2.10")
    assert rows[0]["open_position_count"] == 1


def test_an_open_position_with_a_value_but_no_unrealised_pnl_also_skips(
    context_at: Any, migrated_db: Path, fixed_now: Any
) -> None:
    """`unrealised_pnl` gets the same treatment as `positions_value`, and for the same
    reason: an absent one reads as zero, and a zero unrealised PnL on an invested account
    is a claim that the position is exactly at its entry price — which Phase 7's
    attribution would read as fact."""
    MemoryEngine().process(
        context_at(0),
        tick(
            1,
            **balances("500.00"),
            **{
                POSITION_MANAGER_KEY: {
                    POSITIONS_FIELD: [a_position(fixed_now)],
                    POSITIONS_VALUE_FIELD: "352.10",
                }
            },
        ),
    )
    assert rows_in(migrated_db, "equity_snapshots") == []


# --------------------------------------------------------------------------- #
# Spec 104 — an opportunity-chain engine that errored is recorded, not refused
# --------------------------------------------------------------------------- #
#
# Operator ruling 2026-09-16, invariant 12 and contract rule 7. Rule 7 empties the payload
# of an engine that raised, so the orchestrator publishes `state["block_status"]` and engine
# 19 reads it. The tests below are in two groups: one through the real orchestrator and a
# real raising engine, where nothing about the status is hand-built, and hand-built ticks
# that name apart the cases the status exists to separate.


def an_errored_tick(cycle_id: int, **payload: Any) -> dict[str, Any]:
    """`state` as the orchestrator leaves it when engine 18 raised on a real candidate."""
    return tick(
        cycle_id,
        **balances("500.00"),
        scout={"pair": "AAA/USD"},
        trading_blocked_by="execution",
        block_reason="unhandled ExecutionError: decision.intent is absent",
        block_status="ERROR",
        execution=dict(payload),
    )


def block_rows(db_path: Path) -> list[tuple[Any, ...]]:
    return [
        (row["cycle_id"], row["blocked_by"], row["status"], row["block_reason"], row["is_primary"])
        for row in rows_in(db_path, "block_records")
    ]


class _EngineErrors:
    """The orchestrator's log, kept so an engine that raised can be named by cause."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def debug(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))

    def for_engine(self, engine: str) -> list[str]:
        return [
            str(fields.get("error", ""))
            for event, fields in self.events
            if event == "engine_error" and fields.get("engine") == engine
        ]


def test_an_engine_that_raised_is_recorded_through_the_real_orchestrator(
    tmp_path: Path,
) -> None:
    """The finding, end to end: a real engine raises and the tick is recorded in full.

    **Nothing about the error is staged.** The chain is the real one in registry order with
    engine 16 left out and most of the judgement engines with it: guard 1, 2, 3, 4, 17;
    opportunity 5, 7, 18; manage 19. Engine 7 ranks alphabetically while no ranking feature
    is configured, so flat bars are enough for a real candidate, and engine 18 then raises
    its own `ExecutionError` because no decision was made. The orchestrator turns that into
    `ERROR` and publishes the status; engine 19 reads it. No model is trained, because the
    defect needs none.

    Before spec 104 this tick wrote nothing: engine 19 read the empty payload as a refusal
    with no `reason_code` and raised, after positions and orders and before equity.

    The market is at fee tier 3, the regime every Phase 6 trade runs in, though nothing here
    reaches the cost gate.
    """
    from datetime import UTC, datetime

    from tests.harness.doubles import FakeClients, FixedClock, load_default_config
    from tests.harness.fake_kraken import TIER_3, FakeRecorder
    from tests.harness.market_script import Bar, ScriptedMarket

    from acsoe.clients.paper.broker import PaperBroker
    from acsoe.clients.store.client import StoreClient
    from acsoe.clients.store.contracts import CommandName, CommandRow, CommandSource
    from acsoe.clients.store.migrations import apply_migrations
    from acsoe.core.contracts import Chains
    from acsoe.core.orchestrator import Orchestrator
    from acsoe.engines.data_guard.engine import DataGuardEngine
    from acsoe.engines.exchange.engine import ExchangeEngine
    from acsoe.engines.execution.engine import ExecutionEngine
    from acsoe.engines.feature.engine import FeatureEngine
    from acsoe.engines.market_data_recorder.engine import MarketDataRecorderEngine
    from acsoe.engines.market_sensor.engine import MarketSensorEngine
    from acsoe.engines.safety.engine import SafetyEngine
    from acsoe.engines.scout.engine import ScoutEngine

    bar = 900
    pairs = ("BTC/USD", "ETH/USD")
    last = (int(datetime(2026, 9, 1, tzinfo=UTC).timestamp()) // bar) * bar
    clock = FixedClock(datetime.fromtimestamp(last, tz=UTC))
    market = ScriptedMarket(clock=clock, interval_s=bar, published_bars=200, pairs=pairs)
    market.use_fee_tier(TIER_3)
    flat = [Bar.flat(last - bar * k, "100.000", trades=17 + k % 5) for k in range(300, -3, -1)]
    for pair in pairs:
        market.plant(pair, flat)
        market.set_quote(pair, bid="100.000", ask="100.010")
        market.set_order_book(pair, bids=[("100.000", "1000")], asks=[("100.010", "1000")])

    db = tmp_path / "acsoe.sqlite"
    apply_migrations(db)
    store = StoreClient(db)
    try:
        config = load_default_config()
        store.append_command(
            CommandRow(
                command=CommandName.ACTIVATE.value,
                source=CommandSource.CONSOLE,
                reason="spec 104",
                created_at=1,
                updated_at=1,
            )
        )
        log = _EngineErrors()
        orchestrator = Orchestrator(
            config=config,
            clock=clock,
            clients=FakeClients(
                kraken=PaperBroker(market, store=store, config=config, clock=clock),
                store=store,
                recorder=FakeRecorder(),
            ),
            chains=Chains(
                guard=[
                    ExchangeEngine(),
                    MarketDataRecorderEngine(),
                    MarketSensorEngine(),
                    DataGuardEngine(),
                    SafetyEngine(),
                ],
                opportunity=[FeatureEngine(), ScoutEngine(), ExecutionEngine()],
                manage=[MemoryEngine()],
            ),
            logger=log,
        )

        # A quiet tick first, so the errored tick has an equity row before it and the
        # scout has an equity figure to size against.
        clock.set(datetime.fromtimestamp(last + bar - 59, tz=UTC))
        quiet = orchestrator.tick()
        assert "trading_blocked_by" not in quiet, quiet.get("block_reason")
        clock.set(datetime.fromtimestamp(last + bar + 1, tz=UTC))
        state = orchestrator.tick()
    finally:
        store.close()

    # The subject: a real engine raised, on a tick that had a real candidate - which is
    # what made the old code treat it as a rejection.
    assert state["trading_blocked_by"] == "execution", state.get("block_reason")
    assert state["block_status"] == "ERROR"
    assert state["guard_blockers"] == []
    assert state["scout"]["pair"], "no candidate, so the rejection path was never reachable"
    assert state["execution"] == {}
    assert any("decision.intent is absent" in error for error in log.for_engine("execution"))

    # The property.
    assert log.for_engine("memory") == [], "engine 19 raised on the errored tick"
    assert state["memory"], "engine 19 published nothing on the errored tick"
    cycle = state["cycle_id"]
    assert block_rows(db) == [(cycle, "execution", "ERROR", "engine_errored", 1)], (
        "the errored engine is not recorded as one primary ERROR row with engine 19's code"
    )
    assert rows_in(db, "rejections") == [], "an engine that raised refused nothing"
    equity = [row for row in rows_in(db, "equity_snapshots") if row["cycle_id"] == cycle]
    assert len(equity) == 1, "the errored tick has no equity row, so the tick was lost"
    assert state["memory"]["written"]["block_records"] == 1
    assert state["memory"]["written"]["rejections"] == 0
    assert state["memory"]["written"]["equity_snapshots"] == 1


def test_an_errored_engine_writes_a_block_record_no_rejection_and_the_equity_row(
    context_at: Any, migrated_db: Path
) -> None:
    """The same three facts on a hand-built tick, with the columns named one by one."""
    result = MemoryEngine().process(context_at(0), an_errored_tick(4))

    (row,) = rows_in(migrated_db, "block_records")
    assert (row["run_id"], row["cycle_id"]) == (RUN, 4)
    assert row["blocked_by"] == "execution"
    assert row["status"] == "ERROR", "engine 17's error rate counts status = 'ERROR'"
    assert row["block_reason"] == "engine_errored"
    assert row["is_primary"] == 1
    assert rows_in(migrated_db, "rejections") == []
    assert [snapshot["equity"] for snapshot in rows_in(migrated_db, "equity_snapshots")] == [
        "500.00"
    ]
    assert result.data["written"]["block_records"] == 1
    assert result.data["written"]["rejections"] == 0


def test_an_engine_that_raised_and_a_gate_that_blocked_without_a_code_are_different_facts(
    context_at: Any,
) -> None:
    """Spec 104 step 4: the two cases an empty payload cannot tell apart.

    Both ticks are identical except for `block_status`, and both payloads are `{}`. A gate
    that returned `BLOCK` without its `reason_code` has broken its contract, and the
    console would render its rejection as silence, so engine 19 still refuses the tick. An
    engine that raised decided nothing and is recorded. An engine 19 that inferred the
    error from the empty payload would record both, and the first half goes red.
    """
    refused = an_errored_tick(5)
    refused["block_status"] = "BLOCK"
    with pytest.raises(MissingInputError, match="without publishing a 'reason_code'"):
        MemoryEngine().process(context_at(0), refused)

    raised = an_errored_tick(6)
    result = MemoryEngine().process(context_at(1), raised)
    assert result.data["written"]["block_records"] == 1


def test_an_errored_engine_is_never_asked_for_a_reason_code(
    context_at: Any, migrated_db: Path
) -> None:
    """The status decides, whatever the payload carries.

    The orchestrator always empties an errored engine's payload, so this payload is not one
    it would produce. It is here to pin that engine 19 neither reads a code on this path nor
    decides the case from the payload's shape: a non-empty payload with a code in it is
    still an error, still gets engine 19's own code, and is still not a rejection.
    """
    MemoryEngine().process(
        context_at(0), an_errored_tick(7, reason_code="entry_placed", placed=True)
    )

    assert [row[3] for row in block_rows(migrated_db)] == ["engine_errored"]
    assert rows_in(migrated_db, "rejections") == []


def test_an_errored_engine_with_no_candidate_is_still_recorded(
    context_at: Any, migrated_db: Path
) -> None:
    """A block record is one tick, candidate or not. Engine 5 raising has no candidate."""
    state = tick(
        8,
        **balances("500.00"),
        trading_blocked_by="feature",
        block_reason="unhandled KeyError: 'candles'",
        block_status="ERROR",
        feature={},
    )
    MemoryEngine().process(context_at(0), state)

    assert block_rows(migrated_db) == [(8, "feature", "ERROR", "engine_errored", 1)]
    assert rows_in(migrated_db, "rejections") == []


def test_a_guard_that_errored_keeps_its_one_row_and_its_own_reason(
    context_at: Any, migrated_db: Path
) -> None:
    """Spec 104's scope limit: guard-chain blockers are recorded exactly as before.

    A guard that raised is already in `guard_blockers` with its status, so it has its row.
    A second one for it would be a second primary on the tick, which the database refuses.
    """
    state = tick(
        9,
        trading_blocked_by="exchange",
        block_reason="unhandled KrakenError: nonce",
        block_status="ERROR",
        exchange={},
    )
    state[GUARD_BLOCKERS_KEY] = [
        {"engine": "exchange", "reason": "unhandled KrakenError: nonce", "status": "ERROR"}
    ]
    MemoryEngine().process(context_at(0), state)

    assert block_rows(migrated_db) == [
        (9, "exchange", "ERROR", "unhandled KrakenError: nonce", 1)
    ]


def test_an_opportunity_gate_that_blocked_writes_a_rejection_and_no_block_record(
    context_at: Any, migrated_db: Path
) -> None:
    """The other side of the status: a `BLOCK` with its code is a rejection only.

    A rejection is one candidate, a block record is one tick of an evaluation. An engine 19
    that wrote an error row for every opportunity-chain blocker would put every cost-gate
    refusal into engine 17's error rate.
    """
    MemoryEngine().process(context_at(0), tick(10, **a_rejection()))

    assert rows_in(migrated_db, "block_records") == []
    assert [row["rejected_by"] for row in rows_in(migrated_db, "rejections")] == ["cost"]
