"""Engine 17 `safety` — spec 36.

**Twelve of these are the spec's core: a block test and a pass test for each of the six
inputs.** A gate with only a happy path is incomplete, and this one has six independent
trip conditions, so a single happy path would leave five of them unexercised.

The block halves run against the **Phase 0 seed**, which carries all six fixtures by
construction. The pass halves run against a fresh migrated database, because the seed
trips everything — that asymmetry is the point of the seed and is why the two halves
cannot share a fixture.

Nothing here touches a live engine 19 `memory`. Every one of `safety`'s inputs is written
by engine 19, which is Phase 4; the seed exists precisely to resolve that forward
dependency, and Phase 3 may not depend on the live engine.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import (
    BlockRecordRow,
    BlockStatus,
    CommandName,
    CommandSource,
    EquitySnapshotRow,
    OrderIntent,
    OrderRow,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionRow,
    PositionStatus,
    TradeOutcome,
    TradeRow,
    from_micros,
)
from acsoe.core.contracts import EngineContext, EngineStatus
from acsoe.engines.safety.contracts import (
    CONDITION_ACTION,
    REASON_INPUTS_UNAVAILABLE,
    SafetyAction,
    SafetyCondition,
)
from acsoe.engines.safety.engine import SafetyEngine

RUN = "run-fresh"


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #


def run_safety(
    store: StoreClient,
    config: Any,
    clients: Any,
    *,
    run_id: str,
    cycle_id: int,
    now_micros: int,
    mode: str = "running",
    close_intent: bool = False,
    trading_blocked_by: str | None = None,
    extra_state: dict[str, Any] | None = None,
) -> Any:
    """One `safety` tick, with `state` as the guard chain would have it when 17 runs.

    `state["exit"]` and `state["position_manager"]` are deliberately never set: the manage
    chain runs *after* the guard chain, so they do not exist at this point in a real tick,
    and a fixture that provided them would be testing a state the orchestrator cannot
    produce.
    """
    clients.store = store
    context = EngineContext(
        mode="paper",
        run_id=run_id,
        now=from_micros(now_micros),
        config=config,
        clients=clients,
    )
    state: dict[str, Any] = {
        "system": {"mode": mode, "close_intent": close_intent},
        "cycle_id": cycle_id,
        "guard_blockers": [],
    }
    if trading_blocked_by is not None:
        state["trading_blocked_by"] = trading_blocked_by
        state["block_reason"] = "seeded"
    if extra_state:
        state.update(extra_state)
    return SafetyEngine().process(context, state)


def safety_commands(store: StoreClient) -> tuple[Any, ...]:
    """Every command row `safety` wrote. The console's rows are a different source."""
    return tuple(
        row for row in store.pending_commands() if row.source is CommandSource.SAFETY
    )


@pytest.fixture
def seed_fixtures(tmp_path: Path, paper_config: Any) -> Any:
    """The Phase 0 seed, seeded against **the committed config's** thresholds.

    Deliberately shadows the shared `seed_fixtures` fixture in `tests/conftest.py`, which
    calls `seed_database` with no `thresholds` argument and therefore gets `seed.py`'s
    module defaults. Those defaults are documented as "fixture-shape constants, not
    recommended values", and one of them has since diverged: the default
    `max_errors_in_window` is 10 while `config/default.yaml` says 20. The seed overshoots
    by three, so the shared fixture produces **13** ERROR rows — which overshoots 10 and
    sits well under 20, so engine 17's error-rate condition would silently not trip
    against it and a test asserting the block would fail for a reason unrelated to the
    engine.

    That is precisely the defect `seed.py`'s own docstring warns about and that
    `scripts/verify.py` avoids by building `SeedThresholds` from the config. This fixture
    does the same thing verify does. Reported to C, who owns the shared fixture.
    """
    from acsoe.clients.store.seed import SeedThresholds, seed_database

    thresholds = SeedThresholds(
        max_consecutive_data_blocks=paper_config.get("safety.max_consecutive_data_blocks"),
        max_drawdown_pct=Decimal(str(paper_config.get("safety.max_drawdown_pct"))),
        max_consecutive_losses=paper_config.get("safety.max_consecutive_losses"),
        error_rate_window_s=paper_config.get("safety.error_rate_window_s"),
        max_errors_in_window=paper_config.get("safety.max_errors_in_window"),
    )
    return seed_database(tmp_path / "seeded.sqlite", thresholds=thresholds)


@pytest.fixture
def seeded_store(seed_fixtures: Any) -> Any:
    """B's real `StoreClient` over the Phase 0 seed."""
    client = StoreClient(seed_fixtures.db_path)
    try:
        yield client
    finally:
        client.close()


# --------------------------------------------------------------------------- #
# Row builders for the fresh-database pass halves
# --------------------------------------------------------------------------- #


def write_equity(store: StoreClient, *, equity: str, peak: str, ts: int = 1_000) -> None:
    store.write_equity_snapshot(
        EquitySnapshotRow(
            cycle_id=ts,
            run_id=RUN,
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
    )


def write_trade(store: StoreClient, trade_id: str, *, pnl: str, closed_at: int) -> None:
    store.write_trade(
        TradeRow(
            trade_id=trade_id,
            run_id=RUN,
            cycle_id=closed_at,
            pair="SOL/USD",
            base="SOL",
            quote="USD",
            qty=Decimal("1.00000000"),
            entry_price=Decimal("100.00"),
            exit_price=Decimal("99.00"),
            entry_fee=Decimal("0.40"),
            exit_fee=Decimal("0.80"),
            opened_at=closed_at - 100,
            closed_at=closed_at,
            outcome=TradeOutcome.STOP if Decimal(pnl) < 0 else TradeOutcome.TARGET,
            realised_pnl=Decimal(pnl),
            realised_pnl_pct=Decimal("-0.0100"),
            realised_pnl_quote=Decimal(pnl),
            reporting_currency="USD",
            fx_rate_entry=Decimal("1.00"),
            fx_rate_exit=Decimal("1.00"),
            updated_at=closed_at,
        )
    )


def write_error_block(store: StoreClient, *, cycle_id: int, ts: int) -> None:
    store.write_block_record(
        BlockRecordRow(
            cycle_id=cycle_id,
            run_id=RUN,
            ts=ts,
            blocked_by="prediction",
            block_reason="boom",
            is_primary=True,
            status=BlockStatus.ERROR,
            updated_at=ts,
        )
    )


def write_open_position(store: StoreClient, position_id: str, pair: str = "SOL/USD") -> None:
    base, _, quote = pair.partition("/")
    store.write_position(
        PositionRow(
            position_id=position_id,
            run_id=RUN,
            cycle_id=1,
            pair=pair,
            base=base,
            quote=quote,
            status=PositionStatus.OPEN,
            qty=Decimal("1.00000000"),
            entry_price=Decimal("100.00"),
            target_price=Decimal("103.00"),
            stop_price=Decimal("98.50"),
            timeout_at=9_999,
            opened_at=1_000,
            updated_at=1_000,
        )
    )


def write_resting_entry_order(store: StoreClient, userref: int) -> None:
    store.write_order(
        OrderRow(
            userref=userref,
            run_id=RUN,
            cycle_id=1,
            pair="SOL/USD",
            intent=OrderIntent.ENTRY,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.RESTING,
            qty=Decimal("1.00000000"),
            limit_price=Decimal("99.00"),
            filled_qty=Decimal("0.00000000"),
            oflags="post",
            placed_at=1_000,
            updated_at=1_000,
        )
    )


@pytest.fixture
def calm(store: StoreClient) -> StoreClient:
    """A fresh database in which **nothing** trips: shallow drawdown, no losing streak,
    no errors, no exposure, no data blocks. Every pass half starts here and perturbs one
    input, so a pass test cannot pass for the wrong reason."""
    write_equity(store, equity="1000.00", peak="1000.00")
    return store


# --------------------------------------------------------------------------- #
# Registry shape and placement
# --------------------------------------------------------------------------- #


def test_the_engine_declares_itself_as_the_registry_has_it() -> None:
    engine = SafetyEngine()
    assert (engine.name, engine.number, engine.is_gate) == ("safety", 17, True)


# --------------------------------------------------------------------------- #
# Input 1 — equity drawdown
# --------------------------------------------------------------------------- #


def test_drawdown_blocks_on_the_seeded_trough(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    )

    assert result.status is EngineStatus.BLOCK
    assert SafetyCondition.DRAWDOWN.value in result.data["tripped"]
    assert Decimal(result.data["drawdown_pct"]) == seed_fixtures.drawdown.drawdown_pct


def test_drawdown_passes_when_equity_is_at_its_peak(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=2_000
    )

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["tripped"] == []
    assert Decimal(result.data["drawdown_pct"]) == Decimal("0")


def test_no_equity_snapshot_is_not_read_as_no_drawdown(
    store: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """`None` and zero are different facts. An empty `equity_snapshots` means engine 19
    has not run, not that the account is flat, and the breaker must not confuse them."""
    result = run_safety(
        store, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=2_000
    )

    assert result.data["drawdown_pct"] is None
    assert SafetyCondition.DRAWDOWN.value not in result.data["tripped"]


def test_a_non_positive_peak_does_not_divide_by_zero(
    store: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """A `DivisionByZero` inside a circuit breaker is the breaker failing, and the
    orchestrator would convert it to ERROR — which blocks, but with a reason nobody can
    act on."""
    write_equity(store, equity="0.00", peak="0.00")

    result = run_safety(
        store, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=2_000
    )

    assert result.data["drawdown_pct"] is None
    assert result.status is EngineStatus.OK


# --------------------------------------------------------------------------- #
# Input 2 — consecutive losses
# --------------------------------------------------------------------------- #


def test_loss_streak_blocks_on_the_seeded_run(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    )

    assert SafetyCondition.LOSS_STREAK.value in result.data["tripped"]
    assert result.data["consecutive_losses"] == seed_fixtures.losing_streak.length


def test_loss_streak_passes_below_the_limit(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """`max_consecutive_losses` is 5. Four losses is not a streak."""
    for index in range(4):
        write_trade(calm, f"t-{index}", pnl="-10.00", closed_at=1_000 + index)

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=2_000
    )

    assert result.data["consecutive_losses"] == 4
    assert SafetyCondition.LOSS_STREAK.value not in result.data["tripped"]
    assert result.blocks_trading is False


def test_a_win_ends_the_streak_however_recent(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Trailing run, ordered by `closed_at`. Six losses followed by one win is a streak of
    zero, not of six — the run is trailing, not cumulative."""
    for index in range(6):
        write_trade(calm, f"t-{index}", pnl="-10.00", closed_at=1_000 + index)
    write_trade(calm, "t-win", pnl="5.00", closed_at=2_000)

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=3_000
    )

    assert result.data["consecutive_losses"] == 0
    assert SafetyCondition.LOSS_STREAK.value not in result.data["tripped"]


def test_a_loss_is_negative_pnl_not_a_stop_outcome(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """`architecture-context.md` names both `realised_pnl` and `outcome`. The decision is
    money: a `timeout` can close slightly up, and a breaker counting outcomes rather than
    money would trip on a run of profitable timeouts."""
    for index in range(6):
        write_trade(calm, f"t-{index}", pnl="1.00", closed_at=1_000 + index)

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=2_000
    )

    assert result.data["consecutive_losses"] == 0


# --------------------------------------------------------------------------- #
# Input 3 — error rate in the trailing window
# --------------------------------------------------------------------------- #


def test_error_rate_blocks_on_the_seeded_window(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    )

    assert SafetyCondition.ERROR_RATE.value in result.data["tripped"]
    assert result.data["errors_in_window"] == seed_fixtures.error_blocks.count


def test_error_rate_passes_below_the_limit(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """`max_errors_in_window` is 20."""
    now = 3_600 * 1_000_000 * 2
    for index in range(19):
        write_error_block(calm, cycle_id=index + 1, ts=now - 1_000 * (index + 1))

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=100, now_micros=now
    )

    assert result.data["errors_in_window"] == 19
    assert SafetyCondition.ERROR_RATE.value not in result.data["tripped"]


def test_errors_outside_the_window_are_not_counted(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """`error_rate_window_s` is 3600 — "the trailing hour", fixed by
    `architecture-context.md` rather than operator-chosen. Errors older than that are a
    different hour's problem and must not accumulate forever."""
    now = 3_600 * 1_000_000 * 10
    hour = 3_600 * 1_000_000
    for index in range(25):
        write_error_block(calm, cycle_id=index + 1, ts=now - hour - 1_000 * (index + 1))

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=100, now_micros=now
    )

    assert result.data["errors_in_window"] == 0
    assert SafetyCondition.ERROR_RATE.value not in result.data["tripped"]


# --------------------------------------------------------------------------- #
# Input 4 — open positions, and input 5 — resting entry orders
#
# Neither is a trip condition. Both are invariant 14's escalation *precondition*: a
# `close_all` is emitted only when there is something to close. The block half is that
# exposure permits the emission; the pass half is that its absence suppresses it.
# --------------------------------------------------------------------------- #


def test_exposure_permits_the_escalation_on_the_seed(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    )

    assert result.data["open_positions"] == len(seed_fixtures.open_positions)
    assert result.data["resting_entry_orders"] == len(seed_fixtures.resting_entry_orders)
    assert result.data["command_emitted"] == CommandName.CLOSE_ALL.value


def test_no_exposure_suppresses_the_escalation(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """The pass half for both exposure inputs. A drawdown deep enough to escalate, and
    nothing open — so the assessment still records the breach and no `close_all` is
    written, because liquidating an account with nothing in it is a command with no
    effect."""
    write_equity(calm, equity="500.00", peak="1000.00", ts=2_000)

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=3_000
    )

    assert SafetyCondition.DRAWDOWN.value in result.data["tripped"]
    assert result.data["open_positions"] == 0
    assert result.data["resting_entry_orders"] == 0
    assert result.data["command_emitted"] is None
    assert "no open position" in (result.data["suppressed_because"] or "")
    assert safety_commands(calm) == ()


def test_a_resting_entry_order_alone_is_exposure(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Invariant 14 counts entry orders: "an outage with no position but a live post-only
    buy is still exposure waiting to happen". Left on the book through a blackout it can
    open a position into a market the system has already declared untrustworthy."""
    write_equity(calm, equity="500.00", peak="1000.00", ts=2_000)
    write_resting_entry_order(calm, userref=4242)

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=3_000
    )

    assert result.data["open_positions"] == 0
    assert result.data["resting_entry_orders"] == 1
    assert result.data["command_emitted"] == CommandName.CLOSE_ALL.value


def test_an_open_position_alone_is_exposure(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    write_equity(calm, equity="500.00", peak="1000.00", ts=2_000)
    write_open_position(calm, "p-1")

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=3_000
    )

    assert result.data["command_emitted"] == CommandName.CLOSE_ALL.value


# --------------------------------------------------------------------------- #
# Input 6 — consecutive data blocks
# --------------------------------------------------------------------------- #


def write_outage(store: StoreClient, ticks: int, *, base_ts: int = 1_000_000) -> tuple[str, int]:
    """`ticks` consecutive `data_guard`-blocked ticks, **spanning two `run_id`s with
    reused `cycle_id` values**, and the anchor tick that follows them.

    A controlled fixture rather than the seed, and the reason is structural: the seed
    overshoots every threshold by three, deliberately, so that a fixture pinned to a
    literal cannot stop overshooting when the operator raises a limit. That is right for
    proving the breaker *fires*, and it makes the seed incapable of ever sitting **at**
    the boundary — which is exactly what "and not one tick before" has to test.

    So the boundary is tested here and the `ts`-versus-`cycle_id` discrimination is tested
    against the seed as well, below. This fixture reproduces the seed's load-bearing
    property anyway: `run-a` uses cycles 5-9 and `run-b` restarts at 1, so cycle ids 5-9
    appear under both runs and an implementation grouping by `cycle_id` collapses them.
    """
    first_run = [("outage-run-a", cycle) for cycle in range(5, 10)][:ticks]
    remaining = ticks - len(first_run)
    second_run = [("outage-run-b", cycle) for cycle in range(1, remaining + 1)]
    timeline = first_run + second_run

    for index, (run_id, cycle_id) in enumerate(timeline):
        ts = base_ts + index * 60_000_000
        store.write_block_record(
            BlockRecordRow(
                cycle_id=cycle_id,
                run_id=run_id,
                ts=ts,
                blocked_by="data_guard",
                block_reason="stale tick",
                is_primary=True,
                status=BlockStatus.BLOCK,
                updated_at=ts,
            )
        )

    last_run, last_cycle = timeline[-1]
    return last_run, last_cycle + 1


def test_the_outage_does_not_escalate_one_tick_before_the_limit(
    store: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Half of the arithmetic spec 36 names, and the half that is usually missing.

    `max_consecutive_data_blocks` is 15 and invariant 14 says "more **than**", so with the
    current tick blocked too, 14 stored + this tick = 15 — at the limit, and it must not
    fire. A test asserting only the escalation would pass against an implementation that
    fires a tick early, and firing early liquidates an account over an outage that has not
    reached the threshold the operator chose.
    """
    limit = paper_config.get("safety.max_consecutive_data_blocks")
    write_equity(store, equity="1000.00", peak="1000.00")
    write_open_position(store, "p-1")

    run_id, cycle_id = write_outage(store, limit - 1)
    at_limit = run_safety(
        store,
        paper_config,
        fake_clients,
        run_id=run_id,
        cycle_id=cycle_id,
        now_micros=2_000_000_000,
        trading_blocked_by="data_guard",
    )

    assert at_limit.data["consecutive_data_blocks"] == limit
    assert SafetyCondition.DATA_OUTAGE.value not in at_limit.data["tripped"]
    assert at_limit.data["command_emitted"] is None
    assert safety_commands(store) == ()


def test_one_more_blocked_tick_fires_the_escalation(
    store: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """The other side of the boundary, as its own test so a failure names which side.

    15 stored + this tick = 16, past the limit, and it escalates — but only because the
    fixture also carries an open position. Invariant 14 gates escalation on exposure.
    """
    limit = paper_config.get("safety.max_consecutive_data_blocks")
    write_equity(store, equity="1000.00", peak="1000.00")
    write_open_position(store, "p-1")

    run_id, cycle_id = write_outage(store, limit)
    past_limit = run_safety(
        store,
        paper_config,
        fake_clients,
        run_id=run_id,
        cycle_id=cycle_id,
        now_micros=2_000_000_000,
        trading_blocked_by="data_guard",
    )

    assert past_limit.data["consecutive_data_blocks"] == limit + 1
    assert SafetyCondition.DATA_OUTAGE.value in past_limit.data["tripped"]
    assert past_limit.data["command_emitted"] == CommandName.CLOSE_ALL.value


def test_the_count_survives_a_restart_mid_outage(
    store: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """The whole reason this counter lives in SQLite rather than in `state`.

    The fixture's ticks span two `run_id`s — `run-a` cycles 5-9, then `run-b` restarting
    at cycle 1 — so a daemon that died mid-outage and came back is counted as one
    continuous run. Resetting the clock on a restart would mean an outage could never
    reach the threshold as long as the process kept crashing, which is the case the
    threshold most needs to cover.
    """
    limit = paper_config.get("safety.max_consecutive_data_blocks")
    write_equity(store, equity="1000.00", peak="1000.00")
    run_id, cycle_id = write_outage(store, limit)

    result = run_safety(
        store,
        paper_config,
        fake_clients,
        run_id=run_id,
        cycle_id=cycle_id,
        now_micros=2_000_000_000,
        trading_blocked_by="data_guard",
    )

    runs = {row.run_id for row in store.block_records_in_window(start_ts=0, end_ts=10**18)}
    assert len(runs) == 2, "the fixture must span a restart or this test proves nothing"
    assert result.data["stored_data_blocks"] == limit


def test_the_current_tick_is_added_to_the_stored_count_exactly_once(
    store: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """The off-by-one `engine-contracts.md` fixes in prose.

    Engine 4 runs before engine 17, so this tick's block is already in `state`; engine 19
    runs in the manage chain, so the store holds records only through T-1. Adding the
    current tick inside the store method would double-count it; omitting it here would
    fire a minute late. The same anchor is run twice and only `state` differs.
    """
    write_equity(store, equity="1000.00", peak="1000.00")
    run_id, cycle_id = write_outage(store, 10)

    blocked = run_safety(
        store,
        paper_config,
        fake_clients,
        run_id=run_id,
        cycle_id=cycle_id,
        now_micros=2_000_000_000,
        trading_blocked_by="data_guard",
    )
    clean = run_safety(
        store,
        paper_config,
        fake_clients,
        run_id=run_id,
        cycle_id=cycle_id,
        now_micros=2_000_000_000,
        trading_blocked_by=None,
    )

    assert blocked.data["stored_data_blocks"] == clean.data["stored_data_blocks"] == 10
    assert blocked.data["consecutive_data_blocks"] == 11
    assert clean.data["consecutive_data_blocks"] == 10
    assert blocked.data["current_tick_blocked_by_data_guard"] is True
    assert clean.data["current_tick_blocked_by_data_guard"] is False


def naive_cycle_id_count(store: StoreClient) -> int:
    """What a counter grouping and ordering by `cycle_id` alone would report."""
    rows = store.connection.execute(
        "SELECT cycle_id, "
        "MAX(CASE WHEN blocked_by = 'data_guard' THEN 1 ELSE 0 END) AS has_dg "
        "FROM block_records GROUP BY cycle_id ORDER BY cycle_id DESC"
    ).fetchall()
    count = 0
    for row in rows:
        if not int(row["has_dg"]):
            break
        count += 1
    return count


def test_ordering_by_cycle_id_gives_a_different_answer(
    store: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Proves the fixture discriminates, per the pattern the operator set on spec 20.

    The outage spans two `run_id`s with **reused `cycle_id` values**, so a counter
    grouping by `cycle_id` alone collapses the overlapping cycles into one and reaches a
    different number. Asserting only that the correct count is 15 would pass against a
    `cycle_id`-grouped implementation on a fixture that happened not to overlap; asserting
    the two disagree is what proves this fixture can tell them apart.
    """
    limit = paper_config.get("safety.max_consecutive_data_blocks")
    write_equity(store, equity="1000.00", peak="1000.00")
    run_id, cycle_id = write_outage(store, limit)

    correct = run_safety(
        store,
        paper_config,
        fake_clients,
        run_id=run_id,
        cycle_id=cycle_id,
        now_micros=2_000_000_000,
        trading_blocked_by="data_guard",
    ).data["stored_data_blocks"]

    assert correct == limit
    assert naive_cycle_id_count(store) != correct, (
        "grouping by cycle_id gave the same answer, so this fixture cannot discriminate "
        f"between the two implementations (both {correct})"
    )


def test_the_seeded_outage_also_discriminates_by_ts(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """The same property on the Phase 0 seed, which spec 36 names by name.

    The seed's run is 18 ticks across two `run_id`s with reused `cycle_id`s, built in
    Phase 0 for exactly this. It overshoots the limit by three and so can never sit at the
    boundary — that half is on the controlled fixture above — but it is the realistic
    fixture and the discrimination has to hold on it too.
    """
    last_run, last_cycle = seed_fixtures.consecutive_data_block_run.ticks[-1]

    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=last_run,
        cycle_id=last_cycle + 1,
        now_micros=seed_fixtures.seed_now,
        trading_blocked_by="data_guard",
    )

    assert seed_fixtures.cycle_ids_shared_across_runs, (
        "the seed must reuse cycle_id across runs or this test proves nothing"
    )
    assert result.data["stored_data_blocks"] == seed_fixtures.consecutive_data_block_run.length
    assert naive_cycle_id_count(seeded_store) != result.data["stored_data_blocks"]
    assert SafetyCondition.DATA_OUTAGE.value in result.data["tripped"]


def test_no_data_blocks_is_the_pass_half(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=5, now_micros=2_000
    )

    assert result.data["consecutive_data_blocks"] == 0
    assert SafetyCondition.DATA_OUTAGE.value not in result.data["tripped"]


# --------------------------------------------------------------------------- #
# The breaker is not gated behind the other gates
# --------------------------------------------------------------------------- #


def test_it_acts_on_a_tick_where_the_opportunity_chain_never_ran(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """Spec 36's headline check, and the reason engine 17 is a guard rather than the last
    link of the opportunity chain.

    The fixture is a tick that is already blocked by `data_guard`, which is exactly the
    tick on which the opportunity chain is skipped entirely — no candidate, no `scout`, no
    `cost`, no `risk`. `safety` still evaluates and still writes its command row. An
    account bleeding while every candidate is rejected by an earlier gate would never trip
    a breaker placed at the end of that chain.
    """
    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
        trading_blocked_by="data_guard",
    )

    assert SafetyCondition.DRAWDOWN.value in result.data["tripped"]
    assert result.data["command_emitted"] == CommandName.CLOSE_ALL.value
    assert len(safety_commands(seeded_store)) == 1


def test_it_evaluates_while_frozen(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """Freeze stops the opportunity chain, never the guard chain. `safety` runs in every
    mode, on every tick."""
    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
        mode="frozen",
    )

    assert result.data["tripped"] != []
    assert result.blocks_trading is True


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #


def test_no_second_command_while_the_condition_persists(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """Spec 36, asserted across several ticks.

    It runs every tick, so without this a sustained drawdown appends a freeze row every
    sixty seconds forever and re-triggers a liquidation already under way. The first tick
    emits; the rest see `close_intent` set — which is what the orchestrator does with the
    row at the top of the next tick — and emit nothing while still evaluating and still
    publishing the assessment.
    """
    first = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    )

    later = [
        run_safety(
            seeded_store,
            paper_config,
            fake_clients,
            run_id=RUN,
            cycle_id=cycle,
            now_micros=seed_fixtures.seed_now + cycle,
            close_intent=True,
        )
        for cycle in (2, 3, 4, 5)
    ]

    assert first.data["command_emitted"] == CommandName.CLOSE_ALL.value
    assert [tick.data["command_emitted"] for tick in later] == [None, None, None, None]
    assert len(safety_commands(seeded_store)) == 1, "one row for one condition, not five"
    for tick in later:
        assert tick.data["tripped"] != [], "it still evaluates while suppressed"
        assert tick.blocks_trading is True, "it still blocks while suppressed"
        assert "close_intent" in (tick.data["suppressed_because"] or "")


def test_a_freeze_is_not_re_emitted_when_the_system_is_not_running(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """`freeze` only while the mode is `running`. Freezing a frozen system changes
    nothing, and the row would be appended once a minute forever."""
    now = 3_600 * 1_000_000 * 2
    for index in range(25):
        write_error_block(calm, cycle_id=index + 1, ts=now - 1_000 * (index + 1))

    running = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=100, now_micros=now
    )
    frozen = run_safety(
        calm,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=101,
        now_micros=now + 1,
        mode="frozen",
    )

    assert SafetyCondition.ERROR_RATE.value in running.data["tripped"]
    assert running.data["command_emitted"] == CommandName.FREEZE.value
    assert frozen.data["command_emitted"] is None
    assert "already" in (frozen.data["suppressed_because"] or "")
    assert len(safety_commands(calm)) == 1


def test_the_emitted_row_is_attributed_to_safety_and_carries_every_condition(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """The command row is the audit record of the decision. Every tripped condition is on
    it, not just the strongest — "drawdown *and* a loss streak" is a materially different
    account state from either alone, and the row is what survives."""
    run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    )

    rows = safety_commands(seeded_store)

    assert len(rows) == 1
    assert rows[0].source is CommandSource.SAFETY
    assert rows[0].created_by_run_id == RUN
    assert rows[0].claimed_at is None, "the orchestrator claims it, not the engine"
    assert SafetyCondition.DRAWDOWN.value in (rows[0].reason or "")
    assert SafetyCondition.LOSS_STREAK.value in (rows[0].reason or "")


# --------------------------------------------------------------------------- #
# Every input comes from the store, none from `state`
# --------------------------------------------------------------------------- #


def test_every_input_is_read_from_the_store_and_none_from_state(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Spec 36: "asserted by a test that fails if any read reaches `state` instead of the
    store".

    `state` is poisoned with plausible keys an implementation might reach for — the very
    keys `state["position_manager"]` and `state["exit"]` that do not exist at this point
    in a real tick, because the manage chain runs after the guard chain. Every reading
    must come back as the store has it and none as `state` claims.
    """
    write_equity(calm, equity="1000.00", peak="1000.00", ts=2_000)
    write_open_position(calm, "p-1")

    poisoned = {
        "position_manager": {"open_positions": 99, "entry_orders_cancelled": True},
        "exit": {"positions_closed": True, "consecutive_losses": 99},
        "equity": {"drawdown_pct": "0.99", "equity": "1.00", "peak_equity": "1000.00"},
        "memory": {"errors_in_window": 99, "consecutive_data_blocks": 99},
        "drawdown_pct": "0.99",
        "consecutive_losses": 99,
    }

    result = run_safety(
        calm,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=3_000,
        extra_state=poisoned,
    )

    assert result.data["open_positions"] == 1, "the store says 1; state claims 99"
    assert result.data["consecutive_losses"] == 0
    assert result.data["errors_in_window"] == 0
    assert result.data["consecutive_data_blocks"] == 0
    assert Decimal(result.data["drawdown_pct"]) == Decimal("0")
    assert result.data["tripped"] == []


def test_an_unreachable_store_blocks_rather_than_waving_the_tick_through(
    paper_config: Any, fake_clients: Any
) -> None:
    """Invariant 3, and this is the one gate that is not gated behind the other gates. A
    breaker that cannot read its inputs must stop the system."""
    fake_clients.store = None
    context = EngineContext(
        mode="paper",
        run_id=RUN,
        now=from_micros(1_000),
        config=paper_config,
        clients=fake_clients,
    )

    result = SafetyEngine().process(
        context, {"system": {"mode": "running", "close_intent": False}, "cycle_id": 1}
    )

    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


# --------------------------------------------------------------------------- #
# Policy shape
# --------------------------------------------------------------------------- #


def test_every_condition_has_an_action_and_none_of_them_is_none() -> None:
    """The policy table is the part a person rules on. A condition that tripped and mapped
    to `NONE` would be a breaker with a silent hole in it."""
    for condition in SafetyCondition:
        assert condition in CONDITION_ACTION
        assert CONDITION_ACTION[condition] is not SafetyAction.NONE


def test_the_blocking_reason_carries_the_numbers(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    )
    reason = result.reason or ""

    assert reason.startswith("Safety breaker:")
    assert str(seed_fixtures.losing_streak.length) in reason
    assert "limit" in reason


def test_the_published_payload_is_json_serialisable(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    import json

    data = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    ).data

    assert json.loads(json.dumps(data))["drawdown_pct"] == data["drawdown_pct"]
    assert isinstance(data["drawdown_pct"], str)


def test_the_engine_reads_no_clock(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """Invariant 9. The error-rate window is anchored to `context.now`, so a direct clock
    read here would silently make replay unfaithful — the same tick would count a
    different set of errors on every run."""
    import acsoe.engines.safety.engine as module

    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "datetime.now" not in source
    assert "time.time" not in source
    assert "utcnow" not in source

    earlier = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    )
    much_later = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=2,
        now_micros=seed_fixtures.seed_now
        + int(timedelta(days=30).total_seconds() * 1_000_000),
        close_intent=True,
    )

    assert earlier.data["errors_in_window"] > 0
    assert much_later.data["errors_in_window"] == 0, "the window moved with context.now"
