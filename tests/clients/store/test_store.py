"""Spec 12 — the store client.

Every money assertion here is an exact `Decimal` comparison. `pytest.approx` is banned
by `code-standards.md` for anything involving money, and it would defeat the point of
the file: the whole reason money crosses this boundary as `Decimal` and exact decimal
strings is that approximate equality is what kills an equity series.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from acsoe.clients.store.client import StoreClient, StoreError, money_to_text
from acsoe.clients.store.contracts import (
    BlockRecordRow,
    BlockStatus,
    CashSource,
    CommandName,
    CommandRow,
    CommandSource,
    EquitySnapshotRow,
    LeaderboardRow,
    OrderIntent,
    OrderRow,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionRow,
    PositionStatus,
    RunMode,
    RunRow,
    SystemMode,
    SystemModeRow,
    TradeOutcome,
    TradeRow,
)

# --------------------------------------------------------------------------- #
# Row builders. Defaults are deliberately boring; every test overrides what it means.
# --------------------------------------------------------------------------- #


def make_equity(
    *,
    ts: int,
    equity: str,
    peak: str,
    cycle_id: int = 1,
    run_id: str = "run-a",
) -> EquitySnapshotRow:
    return EquitySnapshotRow(
        cycle_id=cycle_id,
        run_id=run_id,
        ts=ts,
        currency="USD",
        equity=Decimal(equity),
        peak_equity=Decimal(peak),
        cash=Decimal(equity),
        positions_value=Decimal("0.00"),
        unrealised_pnl=Decimal("0.00"),
        realised_pnl_cum=Decimal("0.00"),
        open_position_count=0,
        cash_source=CashSource.CYCLE_START,
        updated_at=ts,
    )


def make_trade(
    *, trade_id: str, closed_at: int, pnl: str, outcome: TradeOutcome = TradeOutcome.STOP
) -> TradeRow:
    return TradeRow(
        trade_id=trade_id,
        position_id=None,
        run_id="run-a",
        cycle_id=1,
        pair="SOL/USD",
        base="SOL",
        quote="USD",
        qty=Decimal("1.00000000"),
        entry_price=Decimal("100.00"),
        exit_price=Decimal("98.50"),
        entry_fee=Decimal("0.20"),
        exit_fee=Decimal("0.20"),
        opened_at=closed_at - 1_000,
        closed_at=closed_at,
        outcome=outcome,
        realised_pnl=Decimal(pnl),
        realised_pnl_pct=Decimal("-0.019000"),
        realised_pnl_quote=Decimal(pnl),
        reporting_currency="USD",
        fx_rate_entry=Decimal("1.00000000"),
        fx_rate_exit=Decimal("1.00000000"),
        updated_at=closed_at,
    )


def make_position(
    *,
    position_id: str,
    pair: str,
    status: PositionStatus = PositionStatus.OPEN,
    hold_reason: str | None = None,
) -> PositionRow:
    """One position row. `hold_reason` defaults to `None` — "did not hold"."""
    return PositionRow(
        position_id=position_id,
        run_id="run-a",
        cycle_id=1,
        pair=pair,
        base=pair.split("/")[0],
        quote=pair.split("/")[1],
        status=status,
        qty=Decimal("0.50000000"),
        entry_price=Decimal("148.20"),
        target_price=Decimal("152.65"),
        stop_price=Decimal("145.98"),
        timeout_at=9_999_999,
        hold_reason=hold_reason,
        opened_at=1_000,
        closed_at=None if status is PositionStatus.OPEN else 2_000,
        updated_at=1_000,
    )


def make_order(
    *,
    userref: int,
    status: OrderStatus = OrderStatus.RESTING,
    intent: OrderIntent = OrderIntent.ENTRY,
    pair: str = "XBT/USD",
    filled_qty: str = "0.00000000",
    avg_fill_price: str | None = None,
    fee: str | None = None,
    placed_at: int = 1_000,
) -> OrderRow:
    """One order row. The fill fields default to an unfilled order.

    `filled_qty`, `avg_fill_price`, `fee` and `placed_at` are keywords with the values
    every existing caller already had, so spec 88's `filled_orders` tests vary one field
    each without moving any test that was written before them.
    """
    return OrderRow(
        userref=userref,
        order_id=f"O-{userref}",
        run_id="run-a",
        cycle_id=1,
        pair=pair,
        side=OrderSide.BUY if intent is OrderIntent.ENTRY else OrderSide.SELL,
        intent=intent,
        order_type=OrderType.LIMIT,
        oflags="post",
        status=status,
        qty=Decimal("0.00100000"),
        limit_price=Decimal("61000.00"),
        filled_qty=Decimal(filled_qty),
        avg_fill_price=None if avg_fill_price is None else Decimal(avg_fill_price),
        fee=None if fee is None else Decimal(fee),
        placed_at=placed_at,
        closed_at=None if status is OrderStatus.RESTING else placed_at + 1,
        updated_at=1_000,
    )


def make_block(
    *,
    run_id: str,
    cycle_id: int,
    ts: int,
    blocked_by: str = "data_guard",
    is_primary: bool = True,
    status: BlockStatus = BlockStatus.BLOCK,
) -> BlockRecordRow:
    return BlockRecordRow(
        cycle_id=cycle_id,
        run_id=run_id,
        ts=ts,
        blocked_by=blocked_by,
        block_reason="reason",
        is_primary=is_primary,
        status=status,
        updated_at=ts,
    )


# --------------------------------------------------------------------------- #
# The money boundary
# --------------------------------------------------------------------------- #


def test_money_round_trips_exactly(store: StoreClient) -> None:
    store.write_equity_snapshot(make_equity(ts=1_000, equity="1000.00", peak="1120.84"))

    row = store.latest_equity_snapshot()

    assert row is not None
    assert row.equity == Decimal("1000.00")
    assert row.peak_equity == Decimal("1120.84")
    # Exact, not approximately: the stored text keeps the quantum the caller chose.
    assert str(row.equity) == "1000.00"


def test_money_is_stored_as_text_not_a_number(store: StoreClient) -> None:
    store.write_equity_snapshot(make_equity(ts=1_000, equity="1000.00", peak="1000.00"))

    types = store.connection.execute(
        "SELECT typeof(equity) AS t, equity AS v FROM equity_snapshots"
    ).fetchone()

    assert types["t"] == "text"
    assert types["v"] == "1000.00"


def test_a_float_is_refused_before_it_reaches_the_database() -> None:
    """The contract model refuses it. A float that already exists has already lost
    precision, so coercing it would preserve the wrong number exactly."""
    with pytest.raises(ValidationError, match="never be a float"):
        make_equity(ts=1, equity="1.00", peak="1.00").model_copy(update={"equity": 1000.0})
        EquitySnapshotRow(
            cycle_id=1,
            run_id="run-a",
            ts=1,
            currency="USD",
            equity=1000.0,  # type: ignore[arg-type]
            peak_equity=Decimal("1000.00"),
            cash=Decimal("0.00"),
            positions_value=Decimal("0.00"),
            unrealised_pnl=Decimal("0.00"),
            realised_pnl_cum=Decimal("0.00"),
            open_position_count=0,
            cash_source=CashSource.CYCLE_START,
            updated_at=1,
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("1000.00"), "1000.00"),
        (Decimal("1000"), "1000"),
        (Decimal("1E+3"), "1000"),
        (Decimal("1E-8"), "0.00000001"),
        (Decimal("-0.015000"), "-0.015000"),
    ],
)
def test_money_text_is_plain_and_keeps_its_quantum(value: Decimal, expected: str) -> None:
    """Never scientific notation, and trailing zeros survive.

    `str(Decimal("1E+3"))` is `"1E+3"`, which round-trips but compares unequal to
    `"1000"` under any SQL text comparison. Trailing zeros are the quantum the caller
    chose — `1000.00` means cents — so normalising them away would throw precision.
    """
    assert money_to_text(value) == expected
    assert Decimal(money_to_text(value)) == value


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_a_non_finite_money_value_is_refused(value: Decimal) -> None:
    """`Decimal("NaN")` compares false against everything including itself — a drawdown
    threshold that silently never trips."""
    with pytest.raises(StoreError, match="non-finite"):
        money_to_text(value)


# --------------------------------------------------------------------------- #
# The six reads `safety` depends on
# --------------------------------------------------------------------------- #


def test_latest_equity_snapshot_is_the_newest_by_ts(store: StoreClient) -> None:
    store.write_equity_snapshot(
        make_equity(ts=3_000, equity="900.00", peak="1120.84", cycle_id=3)
    )
    store.write_equity_snapshot(
        make_equity(ts=1_000, equity="1000.00", peak="1000.00", cycle_id=1)
    )
    store.write_equity_snapshot(
        make_equity(ts=2_000, equity="1120.84", peak="1120.84", cycle_id=2)
    )

    row = store.latest_equity_snapshot()

    assert row is not None
    assert row.ts == 3_000
    assert row.equity == Decimal("900.00")
    assert (row.peak_equity - row.equity) / row.peak_equity == Decimal(
        "220.84"
    ) / Decimal("1120.84")


def test_latest_equity_snapshot_is_none_on_an_empty_database(store: StoreClient) -> None:
    assert store.latest_equity_snapshot() is None


@pytest.mark.parametrize("source", list(CashSource), ids=str)
def test_the_cash_source_is_written_and_read_back_as_given(
    store: StoreClient, source: CashSource
) -> None:
    """Spec 113. Both values survive the round trip through the column. The stored text
    is asserted as well as the model, so a writer that dropped the field and let the
    database default fill it would fail the `after_exit` case."""
    store.write_equity_snapshot(
        make_equity(ts=1_000, equity="1000.00", peak="1000.00").model_copy(
            update={"cash_source": source}
        )
    )

    stored = store.connection.execute(
        "SELECT cash_source FROM equity_snapshots"
    ).fetchone()["cash_source"]
    row = store.latest_equity_snapshot()

    assert stored == source.value
    assert row is not None
    assert row.cash_source is source
    assert [r.cash_source for r in store.equity_series()] == [source]


def test_a_row_built_without_a_cash_source_is_refused() -> None:
    """**The replacement for the test of the default, not its deletion** (operator ruling
    2026-09-18). While `cash_source` defaulted to `CYCLE_START`, a writer that forgot the
    field was handed a label rather than an error — and on an exit tick that label is
    false, in the one series engine 17 reads to compute the drawdown that freezes the
    account. Spec 114 made engine 19 pass the field on both branches, which is the
    precondition the default was waiting on, so the default is gone and its absence is
    now a refusal at construction.

    Retiring the old test without this one would have removed a check instead of
    tightening one: nothing would then hold the field required, and the next fixture to
    omit it would simply get whatever a future default said.
    """
    fields = {
        "cycle_id": 1,
        "run_id": "run-a",
        "ts": 1,
        "currency": "USD",
        "equity": Decimal("1.00"),
        "peak_equity": Decimal("1.00"),
        "cash": Decimal("1.00"),
        "positions_value": Decimal("0.00"),
        "unrealised_pnl": Decimal("0.00"),
        "realised_pnl_cum": Decimal("0.00"),
        "open_position_count": 0,
        "updated_at": 1,
    }
    # The same fields with a source are accepted, so the refusal below is about the
    # missing field and not about the rest of the row.
    assert EquitySnapshotRow(**fields, cash_source=CashSource.AFTER_EXIT).cash_source is (
        CashSource.AFTER_EXIT
    )
    with pytest.raises(ValidationError, match="cash_source"):
        EquitySnapshotRow(**fields)
    assert [member.value for member in CashSource] == ["cycle_start", "after_exit"]


def test_a_cash_source_outside_the_two_is_refused_by_the_model() -> None:
    """Matched on the constraint, not on the field name. An `extra="forbid"` refusal
    would name the field as well, so matching on the name alone could not fail."""
    with pytest.raises(ValidationError, match="Input should be 'cycle_start' or 'after_exit'"):
        EquitySnapshotRow.model_validate(
            {
                **make_equity(ts=1, equity="1.00", peak="1.00").model_dump(),
                "cash_source": "after_entry",
            }
        )


def test_recent_closed_trades_are_ordered_by_closed_at(store: StoreClient) -> None:
    """Ordered by `closed_at`, not by insertion: a trade opened earlier can close later."""
    store.write_trade(make_trade(trade_id="t-1", closed_at=3_000, pnl="-1.50"))
    store.write_trade(make_trade(trade_id="t-2", closed_at=1_000, pnl="2.25"))
    store.write_trade(make_trade(trade_id="t-3", closed_at=2_000, pnl="-0.75"))

    trades = store.recent_closed_trades(limit=10)

    assert [t.trade_id for t in trades] == ["t-1", "t-3", "t-2"]
    assert [t.realised_pnl for t in trades] == [
        Decimal("-1.50"),
        Decimal("-0.75"),
        Decimal("2.25"),
    ]


def test_error_rows_in_the_window_are_counted(store: StoreClient) -> None:
    for index, (ts, status) in enumerate(
        [
            (1_000, BlockStatus.ERROR),
            (2_000, BlockStatus.BLOCK),
            (3_000, BlockStatus.ERROR),
            (9_000, BlockStatus.ERROR),
        ]
    ):
        store.write_block_record(
            make_block(run_id="run-a", cycle_id=index + 1, ts=ts, status=status)
        )

    assert (
        store.count_block_records_in_window(
            start_ts=1_000, end_ts=5_000, status=BlockStatus.ERROR
        )
        == 2
    )
    assert store.count_block_records_in_window(start_ts=1_000, end_ts=5_000) == 3


def test_open_position_and_resting_order_counts(store: StoreClient) -> None:
    store.write_position(make_position(position_id="p-1", pair="SOL/USD"))
    store.write_position(make_position(position_id="p-2", pair="ETH/USD"))
    store.write_position(
        make_position(position_id="p-3", pair="ADA/USD", status=PositionStatus.CLOSED)
    )
    store.write_order(make_order(userref=1, status=OrderStatus.RESTING))
    store.write_order(make_order(userref=2, status=OrderStatus.FILLED, pair="ETH/USD"))
    store.write_order(
        make_order(
            userref=3, status=OrderStatus.RESTING, intent=OrderIntent.EXIT, pair="ADA/USD"
        )
    )

    assert store.count_open_positions() == 2
    assert store.count_resting_orders() == 2
    assert store.count_resting_orders(intent=OrderIntent.ENTRY) == 1


def test_writing_a_second_open_position_for_one_pair_raises(store: StoreClient) -> None:
    """`_upsert` uses `ON CONFLICT (<pk>) DO UPDATE`, never `INSERT OR REPLACE`.

    `REPLACE` resolves a conflict on *any* unique index by deleting the conflicting row,
    so this write would have silently deleted the first position and defeated invariant
    6 without an error anywhere.
    """
    store.write_position(make_position(position_id="p-1", pair="SOL/USD"))

    with pytest.raises(sqlite3.IntegrityError):
        store.write_position(make_position(position_id="p-2", pair="SOL/USD"))

    assert store.count_open_positions() == 1


def test_order_by_userref_is_the_idempotency_lookup(store: StoreClient) -> None:
    store.write_order(make_order(userref=700_001))

    assert store.order_by_userref(700_001) is not None
    assert store.order_by_userref(700_002) is None


# --------------------------------------------------------------------------- #
# The consecutive-tick counter, and its off-by-one
# --------------------------------------------------------------------------- #


def write_timeline(store: StoreClient, timeline: list[tuple[str, int, int, list[str]]]) -> None:
    """`(run_id, cycle_id, ts, engines)` per blocked tick, oldest first."""
    for run_id, cycle_id, ts, engines in timeline:
        for index, engine in enumerate(engines):
            store.write_block_record(
                make_block(
                    run_id=run_id,
                    cycle_id=cycle_id,
                    ts=ts,
                    blocked_by=engine,
                    is_primary=index == 0,
                )
            )


def test_a_tick_with_two_blockers_counts_once(store: StoreClient) -> None:
    """The guard chain never breaks early, so `data_guard` and `safety` can both block
    on one tick. That is one tick, not two."""
    write_timeline(
        store,
        [
            ("run-a", 1, 1_000, ["data_guard", "safety"]),
            ("run-a", 2, 2_000, ["data_guard", "safety"]),
            ("run-a", 3, 3_000, ["data_guard"]),
        ],
    )

    stored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
        current_tick=("run-a", 4)
    )

    assert stored == 3


def test_a_tick_without_a_data_guard_row_ends_the_run(store: StoreClient) -> None:
    write_timeline(
        store,
        [
            ("run-a", 1, 1_000, ["data_guard"]),
            ("run-a", 2, 2_000, ["data_guard"]),
            ("run-a", 3, 3_000, ["market_sensor"]),
            ("run-a", 4, 4_000, ["data_guard"]),
            ("run-a", 5, 5_000, ["data_guard"]),
        ],
    )

    stored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
        current_tick=("run-a", 6)
    )

    assert stored == 2


def test_a_clean_tick_inside_a_run_ends_the_run(store: StoreClient) -> None:
    """An unblocked tick writes no row at all, so adjacency in the table is not
    adjacency in time. Within a run, `cycle_id` increments by one per tick, and the hole
    at cycle 3 proves a tick passed the guard."""
    write_timeline(
        store,
        [
            ("run-a", 1, 1_000, ["data_guard"]),
            ("run-a", 2, 2_000, ["data_guard"]),
            ("run-a", 4, 4_000, ["data_guard"]),
            ("run-a", 5, 5_000, ["data_guard"]),
        ],
    )

    stored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
        current_tick=("run-a", 6)
    )

    assert stored == 2


def test_a_clean_tick_before_the_current_tick_ends_the_run(store: StoreClient) -> None:
    """The hole the anchor exists to see. Ticks 4 and 5 passed the guard and wrote
    nothing, so by tick 6 the outage is over — but the newest row in the table is still
    tick 3, and a walk that starts there reports an outage that ended two minutes ago.

    Anchored, the answer is 0 and `safety` does nothing. Unanchored, it is 3, and with a
    real threshold in front of it that is an account liquidated over a feed hiccup that
    already recovered. The two calls below are the same table asked two questions.
    """
    write_timeline(
        store,
        [
            ("run-a", 1, 1_000, ["data_guard"]),
            ("run-a", 2, 2_000, ["data_guard"]),
            ("run-a", 3, 3_000, ["data_guard"]),
        ],
    )

    anchored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
        current_tick=("run-a", 6)
    )
    unanchored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
        current_tick=None
    )

    assert anchored == 0
    assert unanchored == 3


def test_a_clean_first_tick_after_a_restart_ends_the_run(store: StoreClient) -> None:
    """`run-b` cycle 2 is blocked but cycle 1 left no row, so the restart began with a
    clean tick and the earlier run's outage is a different outage."""
    write_timeline(
        store,
        [
            ("run-a", 8, 1_000, ["data_guard"]),
            ("run-a", 9, 2_000, ["data_guard"]),
            ("run-b", 2, 3_000, ["data_guard"]),
            ("run-b", 3, 4_000, ["data_guard"]),
        ],
    )

    stored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
        current_tick=("run-b", 4)
    )

    assert stored == 2


def test_a_restart_mid_outage_does_not_reset_the_count(store: StoreClient) -> None:
    """The case the counter exists for: a daemon that dies mid-outage and comes back
    does not reset the clock on an outage that is still happening."""
    write_timeline(
        store,
        [
            ("run-a", 900, 1_000, ["data_guard"]),
            ("run-a", 901, 2_000, ["data_guard"]),
            ("run-b", 1, 3_000, ["data_guard"]),
            ("run-b", 2, 4_000, ["data_guard"]),
        ],
    )

    stored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
        current_tick=("run-b", 3)
    )

    assert stored == 4


def test_ordering_by_cycle_id_would_give_a_different_answer(store: StoreClient) -> None:
    """The reason the docs say "order by `ts`, never by `cycle_id`", made concrete.

    `run-b` restarts at cycle 1, so a `cycle_id`-ordered walk starts at `run-a` cycle
    901 and never reaches the newer, lower-numbered ticks. The count it produces is the
    wrong one, and this fixture is what distinguishes the two implementations.
    """
    write_timeline(
        store,
        [
            ("run-a", 899, 500, ["market_sensor"]),
            ("run-a", 900, 1_000, ["data_guard"]),
            ("run-a", 901, 2_000, ["data_guard"]),
            ("run-b", 1, 3_000, ["data_guard"]),
            ("run-b", 2, 4_000, ["data_guard"]),
        ],
    )

    by_cycle = store.connection.execute(
        """
        SELECT run_id, cycle_id,
               MAX(CASE WHEN blocked_by = 'data_guard' THEN 1 ELSE 0 END) AS dg
        FROM block_records GROUP BY run_id, cycle_id
        ORDER BY cycle_id DESC
        """
    ).fetchall()
    wrong = 0
    for row in by_cycle:
        if not row["dg"]:
            break
        wrong += 1

    assert wrong == 2
    assert (
        store.stored_consecutive_data_block_ticks_excluding_current_tick(
            current_tick=("run-b", 3)
        )
        == 4
    )


def test_the_method_name_says_the_current_tick_is_excluded(store: StoreClient) -> None:
    """The stored count is off by one from the number the breaker acts on, and the
    correction belongs to the caller: `effective = stored + (1 if this tick is blocked
    by data_guard else 0)`. `data_guard` runs before `safety` in the guard chain, but
    `memory` runs after both, so the store holds records only through tick T-1."""
    write_timeline(
        store,
        [("run-a", index, index * 1_000, ["data_guard"]) for index in range(1, 15)],
    )

    stored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
        current_tick=("run-a", 15)
    )

    assert stored == 14
    assert stored + 1 == 15  # what `safety` acts on when this tick is also blocked


def test_the_outage_detail_reports_ticks_in_ts_order(store: StoreClient) -> None:
    write_timeline(
        store,
        [
            ("run-a", 900, 1_000, ["data_guard", "safety"]),
            ("run-b", 1, 2_000, ["data_guard"]),
        ],
    )

    outage = store.stored_data_guard_outage_excluding_current_tick(
        current_tick=("run-b", 2)
    )

    assert outage.ticks == (("run-a", 900), ("run-b", 1))
    assert outage.first_ts == 1_000
    assert outage.last_ts == 2_000
    assert outage.length == 2


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    pattern=st.lists(st.sampled_from("DOC"), min_size=1, max_size=40),
    boundary=st.integers(min_value=0, max_value=40),
)
def test_the_counter_matches_the_timeline_across_a_restart(
    tmp_path_factory: pytest.TempPathFactory, pattern: list[str], boundary: int
) -> None:
    """Property: the stored count equals the trailing run of `data_guard` ticks in the
    real timeline, whatever the restart does to `cycle_id`.

    `D` is a tick blocked by `data_guard` (sometimes with `safety` too), `O` is a tick
    blocked by something else, `C` is a clean tick that writes no row at all. The
    expected answer is read off the timeline, not recomputed by the implementation.

    The pattern is the timeline through tick T-1; the current tick T is the one after
    it, and it is what the counter is anchored to. That anchor is not decoration — a
    clean tick writes nothing, so without knowing T the walk cannot tell "T-1 was
    blocked" from "T-1 passed the guard and left no row", and the two answers differ
    every time a pattern ends in `C`.

    One case is excluded because it is a documented blind spot rather than a bug: a
    clean tick as the *last* tick of a run leaves no trace anywhere, and after a restart
    nothing in `block_records` can say how many ticks the dead run had. `cycle_id`
    restarts at 1, so no anchor arithmetic reaches back across the restart either. It
    over-counts, which fires the breaker early rather than late; closing it would mean
    reading the tick timeline from `equity_snapshots`, and `architecture-context.md`
    fixes this counter's source as `block_records`.
    """
    boundary = min(boundary, len(pattern))
    if 0 < boundary <= len(pattern) and pattern[boundary - 1] == "C":
        boundary -= 1
        while boundary > 0 and pattern[boundary - 1] == "C":
            boundary -= 1

    expected = 0
    for kind in reversed(pattern):
        if kind != "D":
            break
        expected += 1

    db_path = tmp_path_factory.mktemp("counter") / "acsoe.sqlite"
    with StoreClient(db_path) as store:
        store.migrate()
        for index, kind in enumerate(pattern):
            if kind == "C":
                continue
            run_id = "run-a" if index < boundary else "run-b"
            cycle_id = index + 1 if index < boundary else index - boundary + 1
            engines = ["data_guard", "safety"] if kind == "D" and index % 3 == 0 else None
            if engines is None:
                engines = ["data_guard"] if kind == "D" else ["market_sensor"]
            write_timeline(store, [(run_id, cycle_id, (index + 1) * 1_000, engines)])

        # Tick T, minted by the same rule the loop uses for tick index `len(pattern)`.
        # `safety` runs on it, and asks the store for everything through T-1.
        current_tick = ("run-b", len(pattern) - boundary + 1)
        stored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
            current_tick=current_tick
        )

    assert stored == expected


# --------------------------------------------------------------------------- #
# Spec 51 — the bounded `block_records` reads the cycle feed and engine 19 need
#
# Every fixture below writes MORE rows than the limit under test. A limit-bounded
# read whose test uses fewer rows than the limit cannot fail: it returns everything
# either way, and so does the implementation with the LIMIT clause deleted.
# --------------------------------------------------------------------------- #

#: Two runs whose `cycle_id` ordering and `ts` ordering disagree completely. `run-b`
#: restarts at cycle 1, so a `cycle_id` walk puts the *older* run's high numbers in
#: front of the newer run's low ones. This is the shape of B's Phase 0 seed and it is
#: the only fixture on which the two orderings can be told apart.
TWO_RUNS: list[tuple[str, int, int, list[str]]] = [
    ("run-a", 900, 1_000, ["data_guard"]),
    ("run-a", 901, 2_000, ["data_guard"]),
    ("run-a", 902, 3_000, ["data_guard"]),
    ("run-b", 1, 4_000, ["data_guard"]),
    ("run-b", 2, 5_000, ["data_guard"]),
]


def test_recent_block_records_are_ordered_by_ts_and_not_by_cycle_id(
    store: StoreClient,
) -> None:
    """The named mutation for this spec: order by `cycle_id` and this goes red.

    `cycle_id` restarts at 1 with the process, so ordering a cross-restart sequence by
    it reports `run-a`'s stale cycle 902 as the newest thing that happened and never
    reaches `run-b` at all.
    """
    write_timeline(store, TWO_RUNS)

    assert [(row.run_id, row.cycle_id) for row in store.recent_block_records(5)] == [
        ("run-b", 2),
        ("run-b", 1),
        ("run-a", 902),
        ("run-a", 901),
        ("run-a", 900),
    ]
    # Truncated, the two orderings do not merely reorder — they disagree about which
    # rows exist at all. A `cycle_id` ordering answers `run-a` 902 and 901 here.
    assert [(row.run_id, row.cycle_id) for row in store.recent_block_records(2)] == [
        ("run-b", 2),
        ("run-b", 1),
    ]


def test_recent_block_records_returns_no_more_than_the_limit(store: StoreClient) -> None:
    """Nine rows, a limit of four. The count is the assertion the LIMIT clause owns."""
    write_timeline(
        store,
        [("run-a", index, index * 1_000, ["data_guard"]) for index in range(1, 10)],
    )

    rows = store.recent_block_records(4)

    assert len(rows) == 4
    assert [row.cycle_id for row in rows] == [9, 8, 7, 6]


def test_recent_block_records_counts_rows_and_not_ticks(store: StoreClient) -> None:
    """A row is a blocker. Three two-blocker ticks under a limit of four is four rows
    spanning two ticks, which is exactly why `recent_blocked_ticks` exists."""
    write_timeline(
        store,
        [
            ("run-a", 1, 1_000, ["data_guard", "safety"]),
            ("run-a", 2, 2_000, ["data_guard", "safety"]),
            ("run-a", 3, 3_000, ["data_guard", "safety"]),
        ],
    )

    rows = store.recent_block_records(4)

    assert len(rows) == 4
    assert {(row.run_id, row.cycle_id) for row in rows} == {("run-a", 3), ("run-a", 2)}


def test_recent_block_records_is_empty_on_an_empty_table(store: StoreClient) -> None:
    assert store.recent_block_records(10) == ()


def test_recent_blocked_ticks_are_ordered_by_ts_and_not_by_cycle_id(
    store: StoreClient,
) -> None:
    """The same named mutation, against the method the console will actually call."""
    write_timeline(store, TWO_RUNS)

    assert [(row.run_id, row.cycle_id) for row in store.recent_blocked_ticks(2)] == [
        ("run-b", 2),
        ("run-b", 1),
    ]


def test_recent_blocked_ticks_limits_ticks_and_not_rows(store: StoreClient) -> None:
    """Five two-blocker ticks, a limit of three: three ticks, not three rows.

    A row-limited implementation returns one and a half ticks here and the half is
    silent — it renders as a tick blocked by whichever engine happened to survive the
    truncation.
    """
    write_timeline(
        store,
        [
            ("run-a", index, index * 1_000, ["data_guard", "safety"])
            for index in range(1, 6)
        ],
    )

    rows = store.recent_blocked_ticks(3)

    assert [(row.run_id, row.cycle_id) for row in rows] == [
        ("run-a", 5),
        ("run-a", 4),
        ("run-a", 3),
    ]
    # Every one of them is the tick's primary blocker, the oldest included. That is
    # the assertion a row-limited implementation fails on the boundary tick.
    assert [row.blocked_by for row in rows] == ["data_guard"] * 3
    assert all(row.is_primary for row in rows)


def test_recent_blocked_ticks_keeps_the_primary_row_whatever_order_it_was_written(
    store: StoreClient,
) -> None:
    """`is_primary` decides, not insertion order. Written second here, kept anyway."""
    store.write_block_record(
        make_block(run_id="run-a", cycle_id=1, ts=1_000, blocked_by="safety", is_primary=False)
    )
    store.write_block_record(
        make_block(
            run_id="run-a", cycle_id=1, ts=1_000, blocked_by="data_guard", is_primary=True
        )
    )

    rows = store.recent_blocked_ticks(5)

    assert len(rows) == 1
    assert rows[0].blocked_by == "data_guard"


def test_recent_blocked_ticks_falls_back_to_the_lowest_id_with_no_primary(
    store: StoreClient,
) -> None:
    """What a seeded fixture and a half-written tick look like: no row marked primary.

    The tick still happened and still renders, so it is reported rather than dropped.
    """
    store.write_block_record(
        make_block(run_id="run-a", cycle_id=1, ts=1_000, blocked_by="data_guard", is_primary=False)
    )
    store.write_block_record(
        make_block(run_id="run-a", cycle_id=1, ts=1_000, blocked_by="safety", is_primary=False)
    )

    rows = store.recent_blocked_ticks(5)

    assert len(rows) == 1
    assert rows[0].blocked_by == "data_guard"


def test_recent_blocked_ticks_is_empty_on_an_empty_table(store: StoreClient) -> None:
    assert store.recent_blocked_ticks(10) == ()


def test_recent_blocked_ticks_matches_the_seeded_feed_row_for_row(seeded_db: Path) -> None:
    """The bounded read answers what the unbounded scan answered, on the real seed.

    The console has grouped the whole table in Python since Phase 1. Replacing that with
    a bounded query is only safe if the two agree, and the seed is the one fixture that
    spans two `run_id`s with reused `cycle_id` values.
    """
    with StoreClient(seeded_db) as client:
        every_row = client.block_records_in_window(start_ts=0, end_ts=2**62)
        chosen: dict[tuple[str, int], BlockRecordRow] = {}
        for row in every_row:
            tick = (row.run_id, row.cycle_id)
            held = chosen.get(tick)
            if held is None or (row.is_primary and not held.is_primary):
                chosen[tick] = row
        expected = sorted(
            chosen.values(), key=lambda row: (row.ts, row.run_id, row.cycle_id), reverse=True
        )
        assert len(expected) > 5, "the seed must span more ticks than the limit under test"

        bounded = client.recent_blocked_ticks(len(expected))

        assert [(row.run_id, row.cycle_id, row.blocked_by) for row in bounded] == [
            (row.run_id, row.cycle_id, row.blocked_by) for row in expected
        ]


# --------------------------------------------------------------------------- #
# Spec 51 — `peak_equity` without walking the series
# --------------------------------------------------------------------------- #


def test_peak_equity_is_not_a_lexicographic_max_over_the_column(store: StoreClient) -> None:
    """`SELECT MAX(peak_equity)` is wrong, and wrong quietly.

    Money is stored as an exact decimal *string*, so SQLite compares it
    lexicographically: `'9.50' > '10000.00'`. A too-small peak is a too-small drawdown,
    and the circuit breaker sits quiet through exactly the loss it exists to stop.
    """
    store.write_equity_snapshot(
        make_equity(ts=1_000, equity="9.50", peak="9.50", cycle_id=1)
    )
    store.write_equity_snapshot(
        make_equity(ts=2_000, equity="10000.00", peak="10000.00", cycle_id=2)
    )
    store.write_equity_snapshot(
        make_equity(ts=3_000, equity="4000.00", peak="10000.00", cycle_id=3)
    )

    lexicographic = store.connection.execute(
        "SELECT MAX(peak_equity) AS m FROM equity_snapshots"
    ).fetchone()["m"]
    assert lexicographic == "9.50", "the wrong query has to actually be wrong here"

    assert store.peak_equity() == Decimal("10000.00")


def test_peak_equity_survives_a_drawdown_and_a_restart(store: StoreClient) -> None:
    """The peak is carried forward on the row, so it outlives the run that set it.

    Recomputing it from `state` — which is rebuilt every tick — would report the peak as
    the current equity and a drawdown of zero.
    """
    store.write_equity_snapshot(
        make_equity(ts=1_000, equity="1000.00", peak="1000.00", cycle_id=1, run_id="run-a")
    )
    store.write_equity_snapshot(
        make_equity(ts=2_000, equity="800.00", peak="1000.00", cycle_id=1, run_id="run-b")
    )

    assert store.peak_equity() == Decimal("1000.00")
    assert store.peak_equity() != store.latest_equity_snapshot().equity  # type: ignore[union-attr]


def test_peak_equity_is_none_on_an_empty_series(store: StoreClient) -> None:
    """`None` is not `Decimal("0")`. A zero peak makes every drawdown a division by
    zero or a 100% loss, and engine 19 writes no row at all when there is no equity."""
    assert store.peak_equity() is None


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def make_command(
    *, command: str = CommandName.FREEZE.value, source: CommandSource = CommandSource.SAFETY
) -> CommandRow:
    return CommandRow(
        command=command,
        source=source,
        reason="drawdown past limit",
        created_at=1_000,
        updated_at=1_000,
    )


def test_a_command_is_pending_until_claimed_and_unconsumed_until_complete(
    store: StoreClient,
) -> None:
    command_id = store.append_command(make_command())

    assert [row.id for row in store.pending_commands()] == [command_id]
    assert store.claimed_unconsumed_commands() == ()

    assert store.claim_command(command_id, claimed_at=2_000, run_id="run-a") is True

    assert store.pending_commands() == ()
    interrupted = store.claimed_unconsumed_commands()
    assert [row.id for row in interrupted] == [command_id]
    assert interrupted[0].claimed_by_run_id == "run-a"

    assert store.mark_command_consumed(command_id, consumed_at=3_000) is True
    assert store.claimed_unconsumed_commands() == ()


def test_claiming_twice_within_a_run_is_refused(store: StoreClient) -> None:
    """`claimed_at` is what makes the reader idempotent: a row already claimed is never
    applied twice."""
    command_id = store.append_command(make_command())

    assert store.claim_command(command_id, claimed_at=2_000, run_id="run-a") is True
    assert store.claim_command(command_id, claimed_at=2_500, run_id="run-a") is False
    assert store.mark_command_consumed(command_id, consumed_at=3_000) is True
    assert store.mark_command_consumed(command_id, consumed_at=3_500) is False


def test_an_unrecognised_command_survives_the_round_trip(store: StoreClient) -> None:
    """The reader ignores it and logs a warning. It has to be able to read it first."""
    store.append_command(make_command(command="go_faster", source=CommandSource.CONSOLE))

    assert [row.command for row in store.pending_commands()] == ["go_faster"]


# --------------------------------------------------------------------------- #
# Console reads
# --------------------------------------------------------------------------- #


def test_watermark_moves_on_every_write_and_is_zero_when_empty(store: StoreClient) -> None:
    assert store.watermark() == 0

    store.write_position(make_position(position_id="p-1", pair="SOL/USD"))
    first = store.watermark()
    store.write_equity_snapshot(make_equity(ts=5_000, equity="1000.00", peak="1000.00"))

    assert first == 1_000
    assert store.watermark() == 5_000


def test_latest_runs_supports_restart_detection(store: StoreClient) -> None:
    """The console compares the current `run_id` against the previous row's, server-side,
    because it is a separate process with no memory across its own restarts."""
    for index, run_id in enumerate(("run-a", "run-b", "run-c")):
        store.write_run(
            RunRow(
                run_id=run_id,
                mode=RunMode.PAPER,
                started_at=(index + 1) * 1_000,
                updated_at=(index + 1) * 1_000,
            )
        )

    runs = store.latest_runs(limit=2)

    assert [row.run_id for row in runs] == ["run-c", "run-b"]


def test_no_seeded_or_written_run_is_ever_live(store: StoreClient) -> None:
    store.write_run(
        RunRow(run_id="run-a", mode=RunMode.PAPER, started_at=1_000, updated_at=1_000)
    )

    assert [row.mode for row in store.latest_runs()] == [RunMode.PAPER]


# --------------------------------------------------------------------------- #
# The persisted system mode — spec 31. The command reader in `core/` writes it;
# C's console reads it. Nothing here or anywhere reads it back into `state`.
# --------------------------------------------------------------------------- #


def _write_run(store: StoreClient, run_id: str, *, started_at: int = 1_000) -> None:
    store.write_run(
        RunRow(
            run_id=run_id,
            mode=RunMode.PAPER,
            started_at=started_at,
            updated_at=started_at,
        )
    )


def test_the_system_mode_round_trips_for_the_run_it_was_written_for(
    store: StoreClient,
) -> None:
    _write_run(store, "run-a")

    assert store.set_system_mode("run-a", SystemMode.RUNNING, at=2_000) is True

    row = store.system_mode("run-a")
    assert row is not None
    assert (row.run_id, row.mode, row.at) == ("run-a", SystemMode.RUNNING, 2_000)


def test_one_runs_mode_does_not_leak_into_another(store: StoreClient) -> None:
    """The whole reason spec 31 requires the value to be readable by `run_id`: a console
    attached to a fresh daemon must not render the previous process's Running."""
    _write_run(store, "run-a", started_at=1_000)
    _write_run(store, "run-b", started_at=2_000)
    store.set_system_mode("run-a", SystemMode.RUNNING, at=1_500)

    previous = store.system_mode("run-a")
    current = store.system_mode("run-b")

    assert previous is not None and previous.mode is SystemMode.RUNNING
    assert current is not None and current.mode is None and current.at is None


def test_an_unwritten_mode_and_an_unknown_run_are_different_answers(
    store: StoreClient,
) -> None:
    """Both render as an idle reading, but only one of them is ordinary. A reader handed
    the same `None` for each could not log the abnormal one."""
    _write_run(store, "run-a")

    assert store.system_mode("run-a") == SystemModeRow(run_id="run-a", mode=None, at=None)
    assert store.system_mode("run-missing") is None


def test_setting_a_mode_for_an_unknown_run_reports_false_and_writes_nothing(
    store: StoreClient,
) -> None:
    """Returned rather than raised: the command reader must not abort a `freeze` it has
    already applied to `state` because a bookkeeping row was missing."""
    assert store.set_system_mode("run-missing", SystemMode.FROZEN, at=2_000) is False
    assert store.system_mode("run-missing") is None


def test_the_last_mode_written_is_the_one_read_back(store: StoreClient) -> None:
    _write_run(store, "run-a")
    for at, mode in ((2_000, SystemMode.RUNNING), (3_000, SystemMode.FROZEN)):
        store.set_system_mode("run-a", mode, at=at)

    row = store.system_mode("run-a")

    assert row is not None
    assert (row.mode, row.at) == (SystemMode.FROZEN, 3_000)


def test_writing_the_mode_moves_the_console_watermark(store: StoreClient) -> None:
    """`runs` is in `WATERMARK_TABLES`. Without the `updated_at` bump the console would
    never repoll and the status band would sit stale on the previous reading — which is
    the failure spec 31 exists to end, arriving by a different route."""
    _write_run(store, "run-a")
    before = store.watermark()

    store.set_system_mode("run-a", SystemMode.RUNNING, at=9_000)

    assert before == 1_000
    assert store.watermark() == 9_000


def test_write_run_never_overwrites_a_mode_it_was_not_asked_to_change(
    store: StoreClient,
) -> None:
    """`set_system_mode` is the only writer of these two columns.

    The orchestrator writes the run row again at shutdown to stamp `ended_at`, and the
    `RunRow` it holds was built at startup when no mode existed. If `write_run` carried
    these columns, that second write would silently reset a `frozen` daemon's persisted
    mode to null.
    """
    _write_run(store, "run-a")
    store.set_system_mode("run-a", SystemMode.FROZEN, at=2_000)

    store.write_run(
        RunRow(
            run_id="run-a",
            mode=RunMode.PAPER,
            started_at=1_000,
            ended_at=5_000,
            updated_at=5_000,
        )
    )

    row = store.system_mode("run-a")
    assert row is not None
    assert (row.mode, row.at) == (SystemMode.FROZEN, 2_000)
    assert store.latest_runs()[0].ended_at == 5_000


def test_a_stale_run_row_carrying_a_mode_still_cannot_write_one(store: StoreClient) -> None:
    """The exclusion is on the column, not on whether the caller left it null — a
    `RunRow` read back out of the database carries the mode, and re-writing it must
    still be a no-op on that column rather than a clobber that happens to agree."""
    _write_run(store, "run-a")
    store.set_system_mode("run-a", SystemMode.RUNNING, at=2_000)
    stale = store.latest_runs()[0]
    assert stale.system_mode is SystemMode.RUNNING

    store.set_system_mode("run-a", SystemMode.FROZEN, at=3_000)
    store.write_run(stale.model_copy(update={"updated_at": 4_000}))

    row = store.system_mode("run-a")
    assert row is not None
    assert (row.mode, row.at) == (SystemMode.FROZEN, 3_000)


def test_the_seed_writes_no_system_mode(seeded_db: Path) -> None:
    """Spec 31 forbids seeding a mode. A seeded `running` would let C's console test for
    the Running band pass without a daemon ever having written one, which would leave
    the whole persisted-mode path unproven and green."""
    with StoreClient(seeded_db) as seeded:
        modes = [row.system_mode for row in seeded.latest_runs(limit=100)]

    assert modes != []
    assert modes == [None] * len(modes)


def test_sqlite_integers_become_real_booleans_at_the_client_boundary(
    store: StoreClient,
) -> None:
    """SQLite has no boolean type: `is_primary` and `promoted` are `INTEGER ... CHECK
    (col IN (0, 1))` and read back as `0`/`1`.

    Converted in `_row_to_dict` rather than left to pydantic's lax coercion. Lax mode
    accepts `0` and `1` for a `bool`, so this is normally unnecessary — except that A
    observed `BlockRecordRow.is_primary — Input should be a valid boolean
    [input_value=0, input_type=int]` out of this module in one full-suite run, not
    reproducible alone, on a model that is not strict. A lax validator behaving as a
    strict one is the known intermittent pydantic-core fault arriving as a wrong answer
    rather than as a crash.

    The hazard is the diagnosis, not the failure: a `ValidationError` naming a field
    invites loosening that field's type, which would then accept a genuinely bad value
    forever. This asserts the values are real `bool`s and not truthy integers, so the
    conversion cannot be quietly dropped.
    """
    store.write_block_record(
        BlockRecordRow(
            cycle_id=1,
            run_id="run-a",
            ts=1_000,
            blocked_by="data_guard",
            block_reason="stale",
            is_primary=True,
            status=BlockStatus.BLOCK,
            updated_at=1_000,
        )
    )
    store.write_block_record(
        BlockRecordRow(
            cycle_id=1,
            run_id="run-a",
            ts=1_000,
            blocked_by="safety",
            block_reason="drawdown",
            is_primary=False,
            status=BlockStatus.BLOCK,
            updated_at=1_000,
        )
    )

    rows = store.block_records_in_window(start_ts=0, end_ts=10_000)
    flags = {row.blocked_by: row.is_primary for row in rows}

    assert flags == {"data_guard": True, "safety": False}
    for value in flags.values():
        assert type(value) is bool, "a truthy int is not a bool; the conversion was dropped"


def test_equity_series_returns_the_whole_curve_oldest_first(store: StoreClient) -> None:
    for index in range(5):
        store.write_equity_snapshot(
            make_equity(
                ts=(index + 1) * 1_000,
                equity=f"{1000 + index}.00",
                peak="1004.00",
                cycle_id=index + 1,
            )
        )

    series = store.equity_series()

    assert [row.ts for row in series] == [1_000, 2_000, 3_000, 4_000, 5_000]
    assert series[0].equity == Decimal("1000.00")
    assert store.equity_series(start_ts=3_000, end_ts=4_000) == series[2:4]


def test_a_transaction_rolls_back_on_failure(store: StoreClient) -> None:
    with pytest.raises(sqlite3.IntegrityError), store.transaction():
        store.write_position(make_position(position_id="p-1", pair="SOL/USD"))
        store.write_position(make_position(position_id="p-2", pair="SOL/USD"))

    assert store.count_open_positions() == 0


def test_the_store_reads_and_writes_nothing_under_data(store: StoreClient, tmp_path: Path) -> None:
    """`data/` is gitignored, so no test or criterion may depend on anything inside it."""
    assert tmp_path in store.db_path.parents


# --------------------------------------------------------------------------- #
# Spec 62 — the store surface for model artefacts
#
# Every assertion below is on the **message**, never on the type. `StoreError` has one
# type and, in this surface alone, six causes: no root configured, the root missing, the
# run never trained, the run already written, and two shapes of unusable run id. A bare
# `pytest.raises(StoreError)` cannot tell the failure the test induced from one that
# happened first, which is exactly the defect `code-standards.md` records for
# `KrakenUnavailableError`.
# --------------------------------------------------------------------------- #


@pytest.fixture
def artefact_store(tmp_path: Path) -> Iterator[StoreClient]:
    """A store with a real artefact root beside its database.

    The root is created here rather than by the client, because creating `models/` at
    startup is A's (spec 61 item 3). The client creates it only when a training run asks
    to write into it — the lead's ruling of 2026-09-13 — and never when a reader asks.
    """
    root = tmp_path / "models"
    root.mkdir()
    client = StoreClient(tmp_path / "artefacts.sqlite", models_dir=root)
    try:
        yield client
    finally:
        client.close()


def make_leaderboard(
    *,
    model_version: str = "run-1",
    fold: str | None = "fold-0",
    model_id: str = "predictor",
    trained_at: int = 1_000,
    n_trades: int = 7,
    brier: float | None = 0.18,
    win_rate: float | None = 0.25,
    training_run_id: str | None = "train-1",
    net_pnl: str | None = "12.34",
    promoted: bool = False,
    base_rate_brier: float | None = None,
) -> LeaderboardRow:
    return LeaderboardRow(
        model_id=model_id,
        model_version=model_version,
        training_run_id=training_run_id,
        trained_at=trained_at,
        fold=fold,
        n_trades=n_trades,
        win_rate=win_rate,
        brier=brier,
        base_rate_brier=base_rate_brier,
        net_pnl=None if net_pnl is None else Decimal(net_pnl),
        reporting_currency="USD",
        promoted=promoted,
        updated_at=trained_at,
    )


def test_a_store_built_without_a_models_dir_reports_none(tmp_path: Path) -> None:
    """The default is not an oversight: the console, the seed and every Phase 0 to 4
    caller build a store that never asks for an artefact, and none of them may be made
    to pass a path they have no use for."""
    with StoreClient(tmp_path / "no-models.sqlite") as client:
        assert client.models_dir is None


def test_model_run_dir_returns_the_run_directory_and_reads_nothing_inside_it(
    artefact_store: StoreClient,
) -> None:
    root = artefact_store.models_dir
    assert root is not None
    (root / "run-7").mkdir()
    # Deliberately not a manifest. The store hands back a path; what is in it is C's
    # `modelling/artefacts.py`, and a client that validated the contents would be two
    # owners in one file. A directory holding nothing but junk must still resolve.
    (root / "run-7" / "not-a-manifest.txt").write_bytes(b"junk\n")

    assert artefact_store.model_run_dir("run-7") == root / "run-7"


def test_model_run_dir_refuses_when_no_artefact_root_was_configured(tmp_path: Path) -> None:
    with StoreClient(tmp_path / "no-models.sqlite") as client, pytest.raises(
        StoreError, match="built with no models_dir"
    ):
        client.model_run_dir("run-7")


def test_model_run_dir_refuses_when_the_artefact_root_does_not_exist(tmp_path: Path) -> None:
    """A fresh clone: `models/` is gitignored, so it is absent until something trains."""
    with StoreClient(tmp_path / "db.sqlite", models_dir=tmp_path / "models") as client, pytest.raises(
        StoreError, match=r"artefact root .* does not exist"
    ):
        client.model_run_dir("run-7")


def test_model_run_dir_refuses_a_run_that_was_never_trained(artefact_store: StoreClient) -> None:
    """What engines 8, 13 and 15 hit when `models.*_run_id` names a run nobody trained.
    They block on it; spec 59 decision 9."""
    with pytest.raises(StoreError, match="model run 'run-7' is not in the artefact root"):
        artefact_store.model_run_dir("run-7")


def test_model_run_dir_refuses_a_file_standing_where_the_run_directory_should_be(
    artefact_store: StoreClient,
) -> None:
    """`exists()` would accept this and hand back a path that cannot hold a manifest."""
    root = artefact_store.models_dir
    assert root is not None
    (root / "run-7").write_bytes(b"not a directory\n")

    with pytest.raises(StoreError, match="is not in the artefact root"):
        artefact_store.model_run_dir("run-7")


def test_new_model_run_dir_creates_the_directory(artefact_store: StoreClient) -> None:
    created = artefact_store.new_model_run_dir("run-7")

    assert created.is_dir()
    assert created == artefact_store.models_dir / "run-7"  # type: ignore[operator]
    assert artefact_store.model_run_dir("run-7") == created


def test_new_model_run_dir_refuses_an_existing_directory(artefact_store: StoreClient) -> None:
    """The safety property of the whole spec. `code-standards.md`, Models: a trained
    artefact is never overwritten, because a directory whose files came from two runs
    cannot be reproduced from its config plus its data and is not a result."""
    first = artefact_store.new_model_run_dir("run-7")
    (first / "manifest.json").write_bytes(b"{}\n")

    with pytest.raises(StoreError, match="already exists"):
        artefact_store.new_model_run_dir("run-7")

    assert (first / "manifest.json").read_bytes() == b"{}\n", "the first run was disturbed"


def test_new_model_run_dir_refuses_a_file_of_the_same_name(artefact_store: StoreClient) -> None:
    root = artefact_store.models_dir
    assert root is not None
    (root / "run-7").write_bytes(b"squatting\n")

    with pytest.raises(StoreError, match="already exists"):
        artefact_store.new_model_run_dir("run-7")


def test_new_model_run_dir_creates_a_missing_artefact_root(tmp_path: Path) -> None:
    """A writer creates the root. The lead's ruling of 2026-09-13, after B raised it.

    `platform/paths.py` creates `models/` at startup beside `data/` and `logs/`, but C's
    trainer runs as `python -m acsoe.research.training` and never goes through A's
    startup path. A writer that demanded the root already exist would therefore refuse
    the first training run on every fresh clone, reporting a misconfiguration where
    there was only an empty tree.
    """
    root = tmp_path / "models"
    assert not root.exists(), "the fixture no longer starts from a fresh clone"

    with StoreClient(tmp_path / "db.sqlite", models_dir=root) as client:
        created = client.new_model_run_dir("run-7")

    assert root.is_dir(), "the writer did not create the artefact root"
    assert created == root / "run-7"
    assert created.is_dir()


def test_a_reader_never_creates_the_artefact_root(tmp_path: Path) -> None:
    """The other half of the same ruling, and the half that can rot silently.

    `model_run_dir` is a read, and the two methods now disagree about a missing root on
    purpose. Nothing stops someone "tidying" them back into one path — and the tidy
    direction is towards creating it, because that is what makes the writer work. This
    test is what should stop them: a reader that created the root would report the run
    missing *inside a directory it had just invented*, turning a true message into a
    less true one and leaving an empty tree behind on every failed engine startup.
    """
    root = tmp_path / "models"
    with StoreClient(tmp_path / "db.sqlite", models_dir=root) as client, pytest.raises(
        StoreError, match=r"artefact root .* does not exist"
    ):
        client.model_run_dir("run-7")

    assert not root.exists(), "the reader invented the artefact root"


@pytest.mark.parametrize(
    ("run_id", "expected"),
    [
        ("", "refusing an empty run id"),
        ("   ", "refusing an empty run id"),
        (" run-7", "leading or trailing whitespace"),
        ("run-7 ", "leading or trailing whitespace"),
        ("..", "names a directory relative to the artefact root"),
        (".", "names a directory relative to the artefact root"),
        ("../evil", "a run id is one directory name"),
        ("..\\evil", "a run id is one directory name"),
        ("nested/run", "a run id is one directory name"),
        ("nested\\run", "a run id is one directory name"),
        ("/abs", "a run id is one directory name"),
        ("C:run", "absolute or carries a drive"),
        ("C:\\abs", "a run id is one directory name"),
        ("run\x00null", "null byte"),
    ],
)
def test_an_unusable_run_id_is_refused_by_both_methods(
    artefact_store: StoreClient, run_id: str, expected: str
) -> None:
    """Each cause has its own message. Matching on `StoreError` alone would pass for any
    of them, including one raised before the check under test ran."""
    with pytest.raises(StoreError, match=re.escape(expected)):
        artefact_store.model_run_dir(run_id)
    with pytest.raises(StoreError, match=re.escape(expected)):
        artefact_store.new_model_run_dir(run_id)


def test_a_traversal_run_id_writes_nothing_outside_the_artefact_root(
    artefact_store: StoreClient, tmp_path: Path
) -> None:
    """The refusal is checked for its effect and not only for its message: `models/` and
    its parent are both inspected afterwards, so a future implementation that validated
    the joined path instead of the run id would be caught here as well."""
    root = artefact_store.models_dir
    assert root is not None
    before = sorted(p.name for p in tmp_path.iterdir())

    with pytest.raises(StoreError):
        artefact_store.new_model_run_dir("../escaped")

    assert list(root.iterdir()) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert not (tmp_path / "escaped").exists()


def test_the_run_id_is_checked_before_any_path_is_built(tmp_path: Path) -> None:
    """Both faults are present at once: no artefact root, and a traversal-shaped run id.
    The run-id message is the one that comes back, which is what "raises before any path
    is built" means — an implementation that resolved the root first would report the
    missing root and would have joined the string by the time it noticed."""
    with StoreClient(tmp_path / "db.sqlite") as client, pytest.raises(
        StoreError, match="a run id is one directory name"
    ):
        client.new_model_run_dir("../escaped")


# --------------------------------------------------------------------------- #
# Spec 62 item 3 — the leaderboard audit, and the one gap it found
# --------------------------------------------------------------------------- #


def test_a_leaderboard_row_round_trips_every_field_engine_20_writes(
    store: StoreClient,
) -> None:
    """The audit, executable. Spec 74 names `brier`, `n_trades`, `win_rate`,
    `training_run_id`, `fold` and `promoted`; the row also carries `model_id`,
    `model_version`, `trained_at` and `net_pnl`, which engine 20 sets. Nothing was added
    to the schema — this asserts that nothing needed to be."""
    store.write_leaderboard_entry(make_leaderboard())

    (row,) = store.leaderboard()

    assert row.model_id == "predictor"
    assert row.model_version == "run-1"
    assert row.training_run_id == "train-1"
    assert row.fold == "fold-0"
    assert row.n_trades == 7
    assert row.win_rate == 0.25
    assert row.brier == 0.18
    assert row.net_pnl == Decimal("12.34")
    assert row.promoted is False
    assert type(row.promoted) is bool, "a truthy int is not a bool; the conversion was dropped"
    # Phase 7's, and null here on purpose: a number written now would be read as one.
    assert (row.sharpe, row.deflated_sharpe, row.alpha, row.beta) == (None, None, None, None)


def test_leaderboard_entries_finds_one_version_and_fold(store: StoreClient) -> None:
    store.write_leaderboard_entry(make_leaderboard(model_version="run-1", fold="fold-0"))
    store.write_leaderboard_entry(make_leaderboard(model_version="run-1", fold="fold-1"))
    store.write_leaderboard_entry(make_leaderboard(model_version="run-2", fold="fold-0"))

    found = store.leaderboard_entries(
        model_id="predictor", model_version="run-1", fold="fold-0"
    )

    assert [(r.model_version, r.fold) for r in found] == [("run-1", "fold-0")]
    assert store.leaderboard_entries(model_id="predictor", model_version="run-3", fold="fold-0") == ()


def test_leaderboard_entries_finds_the_row_whose_fold_is_null(store: StoreClient) -> None:
    """`fold IS ?`, never `fold = ?`. SQL equality against NULL is NULL rather than true,
    so the aggregate row with no fold would look absent on every idempotency check and be
    rewritten on every run — a duplicate that looks exactly like a second training run."""
    store.write_leaderboard_entry(make_leaderboard(model_version="run-1", fold=None))
    store.write_leaderboard_entry(make_leaderboard(model_version="run-1", fold="fold-0"))

    found = store.leaderboard_entries(model_id="predictor", model_version="run-1", fold=None)

    assert [r.fold for r in found] == [None]


def test_leaderboard_entries_returns_every_duplicate_rather_than_the_first(
    store: StoreClient,
) -> None:
    """There is no unique index on `(model_id, model_version, fold)` and spec 62 forbids
    a schema change, so idempotency is the caller's convention. A read that collapsed two
    rows into one would hide the state that proves the convention was broken."""
    store.write_leaderboard_entry(make_leaderboard(brier=0.18))
    store.write_leaderboard_entry(make_leaderboard(brier=0.19))

    found = store.leaderboard_entries(
        model_id="predictor", model_version="run-1", fold="fold-0"
    )

    assert [r.brier for r in found] == [0.18, 0.19]


def test_leaderboard_entries_sees_a_fold_the_console_read_would_have_truncated(
    store: StoreClient,
) -> None:
    """Why this method exists at all. `leaderboard()` is the console's read: the newest 50
    by `trained_at`. Deciding "have I written this fold already" from a truncating window
    is spec 51's rows-versus-ticks defect again, and a walk-forward with more folds than
    the limit would silently start writing duplicates."""
    for index in range(60):
        store.write_leaderboard_entry(
            make_leaderboard(fold=f"fold-{index}", trained_at=1_000 + index)
        )

    oldest = "fold-0"
    assert oldest not in {row.fold for row in store.leaderboard()}, "fixture no longer truncates"
    assert len(store.leaderboard_entries(
        model_id="predictor", model_version="run-1", fold=oldest
    )) == 1


# --------------------------------------------------------------------------- #
# `filled_orders` — the paper ledger's read, spec 88
# --------------------------------------------------------------------------- #


def test_filled_orders_returns_only_the_fills(store: StoreClient) -> None:
    """One row per status, so the filter is proved to be a filter.

    A read that returned everything would still make the paper ledger *look* right on a
    fixture where nothing else exists, and would then spend cash on a rejected order the
    first time one appeared.
    """
    store.write_order(make_order(userref=1, status=OrderStatus.RESTING))
    store.write_order(make_order(userref=2, status=OrderStatus.CANCELLED))
    store.write_order(make_order(userref=3, status=OrderStatus.REJECTED))
    store.write_order(make_order(userref=4, status=OrderStatus.EXPIRED))
    store.write_order(
        make_order(
            userref=5,
            status=OrderStatus.FILLED,
            filled_qty="0.00100000",
            avg_fill_price="61000.00",
            fee="1.34",
        )
    )

    assert [row.userref for row in store.filled_orders()] == [5]


def test_filled_orders_is_ordered_by_when_the_order_was_placed(store: StoreClient) -> None:
    """Addition is commutative, so the order does not change the ledger — it changes
    whether a difference between two runs is reproducible. Written second so the
    insertion order and the expected order disagree."""
    for userref, placed_at in ((7, 3_000), (8, 1_000), (9, 2_000)):
        store.write_order(
            make_order(
                userref=userref,
                status=OrderStatus.FILLED,
                filled_qty="0.00100000",
                avg_fill_price="61000.00",
                fee="1.34",
                placed_at=placed_at,
            )
        )

    assert [row.userref for row in store.filled_orders()] == [8, 9, 7]


def test_filled_orders_hands_back_exact_decimals_and_never_a_float(
    store: StoreClient,
) -> None:
    """The whole reason the ledger sums in Python.

    The amount below is chosen so a float round trip is visibly wrong: `0.1 + 0.2` in
    binary floating point is not `0.3`, and a fee of `0.1` on a price of `0.2` is the
    smallest thing that demonstrates it. The assertion is an exact equality on
    `Decimal`, which a float column would fail.
    """
    store.write_order(
        make_order(
            userref=11,
            status=OrderStatus.FILLED,
            filled_qty="0.30000000",
            avg_fill_price="0.20000000",
            fee="0.10000000",
        )
    )

    row = store.filled_orders()[0]

    assert isinstance(row.avg_fill_price, Decimal)
    assert isinstance(row.fee, Decimal)
    assert row.avg_fill_price == Decimal("0.20000000")
    assert row.fee + Decimal("0.20000000") == Decimal("0.30000000")


def test_filled_orders_is_empty_on_a_database_with_no_fills(store: StoreClient) -> None:
    """Empty, not an error: a paper account that has never traded is the ordinary
    starting state and its ledger is the opening balance."""
    assert store.filled_orders() == ()


# --------------------------------------------------------------------------- #
# Migration 0003 — `positions.hold_reason`, ruled by the lead 2026-09-16
#
# B provides the column and the row model. Engine 19 `memory` is the only writer
# (spec 98, C's), so nothing here writes it through an engine: these tests are
# about what the store will carry and what it refuses to carry.
#
# The value is read by the **console**, a separate process, which is the whole
# reason the fact has to reach the database at all: engine 21 publishes it into
# `state` and `state` dies at the end of the tick.
# --------------------------------------------------------------------------- #

#: Engine 21's one hold reason today, spelled here rather than imported. A store
#: test importing an engine constant would assert the two agree by construction,
#: and the column deliberately carries no enumeration of them — see 0003's comment.
HELD_ON_GUARD = "data_guard_blocked"

#: A second, different reason, so an assertion can tell one row's value from
#: another's rather than from "some hold reason was written".
HELD_ON_SOMETHING_ELSE = "manage_chain_paused_by_operator"


def test_a_hold_reason_round_trips_on_the_position_it_was_written_for(
    store: StoreClient,
) -> None:
    """Two open positions, two *different* reasons, read back through `open_positions`.

    One position with one reason would be satisfied by a client that read the column
    from the wrong row, or that returned a constant. Two differing values make the
    assertion about which position held and why.
    """
    store.write_position(
        make_position(position_id="p-1", pair="XBT/USD", hold_reason=HELD_ON_GUARD)
    )
    store.write_position(
        make_position(position_id="p-2", pair="ETH/USD", hold_reason=HELD_ON_SOMETHING_ELSE)
    )

    by_id = {row.position_id: row.hold_reason for row in store.open_positions()}

    assert by_id == {"p-1": HELD_ON_GUARD, "p-2": HELD_ON_SOMETHING_ELSE}


def test_a_position_that_did_not_hold_reads_back_none(store: StoreClient) -> None:
    """`None` is the answer, not `''` and not a missing attribute.

    The ruling is explicit that NULL means "did not hold" and never "unknown", so a
    reader may treat `hold_reason is None` as a statement about the tick rather than
    as an absence of information.
    """
    store.write_position(make_position(position_id="p-1", pair="XBT/USD"))

    assert store.open_positions()[0].hold_reason is None


def test_rewriting_the_position_without_a_hold_reason_clears_it(store: StoreClient) -> None:
    """Condition 2 of the ruling, which is the one that matters.

    `hold_reason` is a fact about *now*, exactly like `last_price`: a hold written on
    one tick and left in place on the next renders an hour-old reason forever, so the
    console reports a paused manage chain over one running normally. The mechanism is
    that `write_position` upserts every column, so the writer clears it by writing the
    row it would have written anyway — it does not have to remember to blank a field.

    `last_price` moves in the same write, so this also fails if the upsert stopped
    updating the row at all rather than specifically stopping at `hold_reason`.
    """
    store.write_position(
        make_position(position_id="p-1", pair="XBT/USD", hold_reason=HELD_ON_GUARD)
    )
    held = store.open_positions()[0]
    assert held.hold_reason == HELD_ON_GUARD

    store.write_position(
        held.model_copy(update={"hold_reason": None, "last_price": Decimal("149.00")})
    )

    cleared = store.open_positions()[0]
    assert cleared.hold_reason is None
    assert cleared.last_price == Decimal("149.00")


@pytest.mark.parametrize("blank", ["", " ", "\t", "\n  "])
def test_a_blank_hold_reason_is_refused_by_the_row_model(blank: str) -> None:
    """A blank string is how "unknown" gets past a nullable column.

    It is non-null, so every `is not None` read calls it a hold, and it renders as
    nothing, so the console shows a held position with no reason on it. `None` is the
    only way to say "did not hold". The same refusal is in migration 0003's CHECK,
    down to `trim()`, and the test below drives that one through SQL.
    """
    with pytest.raises(ValidationError, match="hold_reason is a reason or None"):
        make_position(position_id="p-1", pair="XBT/USD", hold_reason=blank)


def test_the_seed_writes_no_hold_reason(seeded_db: Path) -> None:
    """A seeded position was never held, so every one of them reads back `None`.

    Not a vacuous assertion: the seed carries at least one open position by Phase 0's
    own requirement, and the count is asserted before the values are.
    """
    conn = sqlite3.connect(seeded_db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT position_id, hold_reason FROM positions").fetchall()
    finally:
        conn.close()

    assert len(rows) > 0
    assert [row["hold_reason"] for row in rows] == [None] * len(rows)


def test_open_positions_breaks_a_tie_on_position_id_and_not_on_insertion_order(
    store: StoreClient,
) -> None:
    """`ORDER BY opened_at ASC, position_id ASC` — the tie-break is the whole point.

    Every position the seed and these builders make shares one `opened_at`, and two
    positions opened on the same tick is the ordinary case rather than a contrived one:
    a liquidation closes them together and the console renders them together. With no
    tie-break SQLite may return them in any order, and the console's list would reorder
    itself between two polls of a database nothing had written to.

    Found by a mutation — `position_id DESC` survived all 244 tests in this lane — and
    the tie is created here by writing the rows in the opposite order to the one
    expected, so insertion order and sort order disagree.
    """
    store.write_position(make_position(position_id="p-z", pair="SOL/USD"))
    store.write_position(make_position(position_id="p-a", pair="XBT/USD"))

    opened_at = {row.opened_at for row in store.open_positions()}
    order = [row.position_id for row in store.open_positions()]

    assert opened_at == {1_000}, "the tie-break is untested unless the first key ties"
    assert order == ["p-a", "p-z"]


# --------------------------------------------------------------------------- #
# Migration 0004 and the enumeration engine 14 weights from
#
# Both landed on the lead's ruling of 2026-09-16, after C-models found that
# neither existing leaderboard read could enumerate model versions.
# --------------------------------------------------------------------------- #


def test_the_base_rate_brier_round_trips_and_is_none_when_not_recorded(
    store: StoreClient,
) -> None:
    """Two rows, one with a baseline and one without, so the assertion is about which
    row carries which rather than about "a float came back"."""
    store.write_leaderboard_entry(
        make_leaderboard(model_version="v1", trained_at=1_000, base_rate_brier=0.2475)
    )
    store.write_leaderboard_entry(make_leaderboard(model_version="v2", trained_at=2_000))

    by_version = {
        row.model_version: row.base_rate_brier
        for row in store.all_leaderboard_rows(model_id="predictor")
    }

    assert by_version == {"v1": 0.2475, "v2": None}


def test_all_leaderboard_rows_returns_what_the_console_read_would_have_truncated(
    store: StoreClient,
) -> None:
    """The whole reason this method exists, asserted against the read it replaces.

    Sixty rows against the console's limit of fifty, so the oldest ten are exactly the
    ones `leaderboard()` drops. C's finding is what makes that a defect rather than an
    inconvenience: a model version outside the window gets **no weight because nobody
    looked**, not zero weight for having no edge, and the two are indistinguishable
    downstream — the weights still sum to one, over the wrong set.

    More rows than the limit, deliberately: a fixture with fifty or fewer would pass
    against both reads and prove nothing.
    """
    for index in range(60):
        store.write_leaderboard_entry(
            make_leaderboard(model_version=f"v{index:02d}", trained_at=1_000 + index)
        )

    everything = store.all_leaderboard_rows(model_id="predictor")
    console = store.leaderboard()

    assert len(everything) == 60
    assert len(console) == 50, "the console read is still the truncating one"
    assert "v00" in {row.model_version for row in everything}
    assert "v00" not in {row.model_version for row in console}


def test_all_leaderboard_rows_is_scoped_to_one_model(store: StoreClient) -> None:
    """Scoping by `model_id` is what makes "no limit" safe: one model's folds are
    bounded by its walk-forward, where the table as a whole is bounded by nothing.

    Two models with the **same** version string, so an implementation that filtered on
    nothing, or on the wrong column, comes back with two rows instead of one.
    """
    store.write_leaderboard_entry(make_leaderboard(model_version="v1", trained_at=1_000))
    store.write_leaderboard_entry(
        make_leaderboard(model_version="v1", trained_at=2_000, model_id="skeptic")
    )

    rows = store.all_leaderboard_rows(model_id="predictor")

    assert [(row.model_id, row.trained_at) for row in rows] == [("predictor", 1_000)]


def test_all_leaderboard_rows_orders_by_insertion_and_not_by_trained_at(
    store: StoreClient,
) -> None:
    """`ORDER BY id ASC`, and the fixture is built so the two candidate keys disagree.

    **It took two goes to get the fixture right, and both misses are the same mistake.**
    The first version wrote three rows sharing one `trained_at`: with the key equal
    everywhere, `ORDER BY trained_at DESC` leaves the tie unbroken, SQLite happened to
    return insertion order anyway, and the mutation survived. The second wrote 9000,
    8000, 7000 in that order — which `trained_at DESC` reproduces exactly, so it
    survived too. Both times the witness agreed with the claim while measuring nothing.

    The sequence below is **non-monotonic in insertion order**, which is the only shape
    that separates all three candidates at once:

    | order by | result |
    |---|---|
    | `id ASC` (correct) | 8000, 9000, 7000 |
    | `trained_at ASC` | 7000, 8000, 9000 |
    | `trained_at DESC` | 9000, 8000, 7000 |
    """
    for index, trained_at in enumerate((8_000, 9_000, 7_000)):
        store.write_leaderboard_entry(
            make_leaderboard(
                model_version="v1", trained_at=trained_at, fold=f"fold-{index}"
            )
        )

    rows = store.all_leaderboard_rows(model_id="predictor")

    assert [row.trained_at for row in rows] == [8_000, 9_000, 7_000], (
        "insertion order; sorting by trained_at in either direction gives a "
        "different list, which is what makes this assertion about the sort key"
    )
    assert [row.fold for row in rows] == ["fold-0", "fold-1", "fold-2"]


def test_all_leaderboard_rows_breaks_a_trained_at_tie_deterministically(
    store: StoreClient,
) -> None:
    """The other half, and the reason `trained_at` is not the sort key at all.

    A walk-forward writes every fold of one run with the same `trained_at`, so the tie
    is the **ordinary** case rather than the edge one. `id` is the primary key, so the
    order is total and two reads of a database nothing wrote to cannot disagree.
    """
    for fold in ("fold-c", "fold-a", "fold-b"):
        store.write_leaderboard_entry(
            make_leaderboard(model_version="v1", trained_at=7_000, fold=fold)
        )

    first = store.all_leaderboard_rows(model_id="predictor")
    second = store.all_leaderboard_rows(model_id="predictor")

    assert {row.trained_at for row in first} == {7_000}, "the tie is untested unless it ties"
    assert [row.fold for row in first] == ["fold-c", "fold-a", "fold-b"]
    assert [row.id for row in first] == sorted(row.id or 0 for row in first)
    assert first == second


def test_all_leaderboard_rows_is_empty_on_a_model_that_has_never_trained(
    store: StoreClient,
) -> None:
    """Empty is a real answer, not an error. Engine 14 refuses on it with
    `leaderboard_empty` rather than weighting an empty set, which is its decision to
    make and not this client's."""
    assert store.all_leaderboard_rows(model_id="predictor") == ()
