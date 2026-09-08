"""Spec 12 — the store client.

Every money assertion here is an exact `Decimal` comparison. `pytest.approx` is banned
by `code-standards.md` for anything involving money, and it would defeat the point of
the file: the whole reason money crosses this boundary as `Decimal` and exact decimal
strings is that approximate equality is what kills an equity series.
"""

from __future__ import annotations

import sqlite3
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
    CommandName,
    CommandRow,
    CommandSource,
    EquitySnapshotRow,
    OrderIntent,
    OrderRow,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionRow,
    PositionStatus,
    RunMode,
    RunRow,
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
    *, position_id: str, pair: str, status: PositionStatus = PositionStatus.OPEN
) -> PositionRow:
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
) -> OrderRow:
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
        filled_qty=Decimal("0.00000000"),
        placed_at=1_000,
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

    assert store.stored_consecutive_data_block_ticks_excluding_current_tick() == 3


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

    assert store.stored_consecutive_data_block_ticks_excluding_current_tick() == 2


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

    assert store.stored_consecutive_data_block_ticks_excluding_current_tick() == 2


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

    assert store.stored_consecutive_data_block_ticks_excluding_current_tick() == 2


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

    assert store.stored_consecutive_data_block_ticks_excluding_current_tick() == 4


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
    assert store.stored_consecutive_data_block_ticks_excluding_current_tick() == 4


def test_the_method_name_says_the_current_tick_is_excluded(store: StoreClient) -> None:
    """The stored count is off by one from the number the breaker acts on, and the
    correction belongs to the caller: `effective = stored + (1 if this tick is blocked
    by data_guard else 0)`. `data_guard` runs before `safety` in the guard chain, but
    `memory` runs after both, so the store holds records only through tick T-1."""
    write_timeline(
        store,
        [("run-a", index, index * 1_000, ["data_guard"]) for index in range(1, 15)],
    )

    stored = store.stored_consecutive_data_block_ticks_excluding_current_tick()

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

    outage = store.stored_data_guard_outage_excluding_current_tick()

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

    One case is excluded because it is a documented blind spot rather than a bug: a
    clean tick as the *last* tick of a run leaves no trace anywhere, and after a restart
    nothing in `block_records` can say how many ticks the dead run had. It over-counts,
    which fires the breaker early rather than late; closing it would mean reading the
    tick timeline from `equity_snapshots`, and `architecture-context.md` fixes this
    counter's source as `block_records`.
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

        assert store.stored_consecutive_data_block_ticks_excluding_current_tick() == expected


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
