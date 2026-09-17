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
    ESCALATING_CONDITION,
    REASON_INPUTS_UNAVAILABLE,
    SafetyAction,
    SafetyCondition,
)
from acsoe.engines.safety.engine import SafetyEngine
from acsoe.platform.config import load_config

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


def outage_tick(
    store: StoreClient, paper_config: Any, fake_clients: Any, **kwargs: Any
) -> Any:
    """One tick standing just past the outage limit. The only condition that escalates.

    Rewritten under spec 42. These three tests used a deep drawdown to reach the
    `close_all` branch, which the operator's 2026-09-10 ruling closed off: a drawdown now
    emits `freeze`, so a drawdown fixture no longer exercises the escalation precondition
    at all and the tests were passing on the wrong branch. Exposure gates exactly one
    condition now, and the fixture has to be that condition.
    """
    limit = paper_config.get("safety.max_consecutive_data_blocks")
    run_id, cycle_id = write_outage(store, limit)
    return run_safety(
        store,
        paper_config,
        fake_clients,
        run_id=run_id,
        cycle_id=cycle_id,
        now_micros=2_000_000_000,
        trading_blocked_by="data_guard",
        **kwargs,
    )


def test_exposure_permits_the_escalation_on_the_seed(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """The seed carries both halves: an outage past the limit, and something to close.

    `cycle_id=1` is load-bearing here and is the opposite choice from the drawdown tests
    below. A fresh `run_id` at cycle 1 is treated as the first tick after a restart, so the
    walk is allowed to cross into the seeded runs and picks up their 18-tick outage — which
    is exactly the property being tested. At cycle 2 the adjacency check breaks and the
    stored count is zero.
    """
    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=1,
        now_micros=seed_fixtures.seed_now,
    )

    assert SafetyCondition.DATA_OUTAGE.value in result.data["tripped"]
    assert result.data["open_positions"] == len(seed_fixtures.open_positions)
    assert result.data["resting_entry_orders"] == len(seed_fixtures.resting_entry_orders)
    assert result.data["command_emitted"] == CommandName.CLOSE_ALL.value


def test_no_exposure_suppresses_the_escalation(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """The pass half for both exposure inputs. An outage past the limit and nothing open,
    so the assessment still records the breach and no `close_all` is written — liquidating
    an account with nothing in it is a command with no effect.

    The suppression sentence has to name the condition, not just the absence. After the
    ruling a suppressed `close_all` is always the data outage and never the drawdown a
    reader might assume, and an operator seeing "the breaker did nothing" needs to know
    which.
    """
    result = outage_tick(calm, paper_config, fake_clients)

    assert SafetyCondition.DATA_OUTAGE.value in result.data["tripped"]
    assert result.data["open_positions"] == 0
    assert result.data["resting_entry_orders"] == 0
    assert result.data["command_emitted"] is None
    assert "no open position" in (result.data["suppressed_because"] or "")
    assert SafetyCondition.DATA_OUTAGE.value in (result.data["suppressed_because"] or "")
    assert safety_commands(calm) == ()


def test_a_resting_entry_order_alone_is_exposure(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Invariant 14 counts entry orders: "an outage with no position but a live post-only
    buy is still exposure waiting to happen". Left on the book through a blackout it can
    open a position into a market the system has already declared untrustworthy."""
    write_resting_entry_order(calm, userref=4242)

    result = outage_tick(calm, paper_config, fake_clients)

    assert result.data["open_positions"] == 0
    assert result.data["resting_entry_orders"] == 1
    assert result.data["command_emitted"] == CommandName.CLOSE_ALL.value


def test_an_open_position_alone_is_exposure(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    write_open_position(calm, "p-1")

    result = outage_tick(calm, paper_config, fake_clients)

    assert result.data["command_emitted"] == CommandName.CLOSE_ALL.value


# --------------------------------------------------------------------------- #
# Invariant 14's resting-entry clause, and the day it becomes reachable
# --------------------------------------------------------------------------- #

#: The three committed values the clause's reachability is a function of. Named as dotted
#: keys and read through the real loader, never copied here as numbers: `Config.get` raises
#: on a key that does not exist, so a rename of any of the three fires this as loudly as a
#: retune does.
ENTRY_WINDOW_KEY = "trading.entry_unfilled_window_s"
OUTAGE_LIMIT_KEY = "safety.max_consecutive_data_blocks"
LOOP_TICK_KEY = "timeframes.loop_tick_s"


def assert_entry_window_below_escalation(config: Any) -> None:
    """The comparison, lifted out of the test so the can-it-fail proof can drive it with a
    copied config rather than by editing the committed one, which is not B's file."""
    window = int(config.get(ENTRY_WINDOW_KEY))
    blocks = int(config.get(OUTAGE_LIMIT_KEY))
    tick = int(config.get(LOOP_TICK_KEY))
    escalation_s = blocks * tick
    assert window < escalation_s, (
        f"{ENTRY_WINDOW_KEY} is {window}s, which is no longer below "
        f"{OUTAGE_LIMIT_KEY} ({blocks}) x {LOOP_TICK_KEY} ({tick}s) = {escalation_s}s. "
        "Invariant 14's resting-entry clause has become reachable through a `safety` "
        "escalation and now needs an escalation test of its own. Nothing is wrong yet: "
        "this test is the notice, not a veto."
    )


def test_a_resting_entry_is_cancelled_by_its_window_before_safety_could_escalate(
    repo_root: Path,
) -> None:
    """Why invariant 14's "or resting entry orders" clause has no escalation test here.

    `safety` escalates on exactly one condition: `data_guard` blocking more than
    `safety.max_consecutive_data_blocks` consecutive ticks, which at
    `timeframes.loop_tick_s` seconds per tick cannot happen sooner than the product of the
    two. A resting entry is cancelled after `trading.entry_unfilled_window_s` — invariant
    8 — and engine 21 cancels it **even while the manage chain is holding on a `data_guard`
    block**, because that is a decision about elapsed time rather than about price: it
    reads `context.now`, needs no market data, and reduces exposure.

    So while the window is the shorter of the two, every resting entry is already off the
    book by the time an outage could escalate, and the clause is reachable only through an
    operator Close all — which is the leg `escalation_completes_during_outage` exercises.
    That is why `test_a_resting_entry_order_alone_is_exposure` above proves the
    *precondition* is counted and no test proves the escalation cancels a resting entry:
    on the committed config, no tick can present one.

    **If this test fires, nothing is broken.** The clause has become reachable through a
    `safety` escalation and is untested, and the failure message names all three values so
    the next reader can see which one moved. It does not forbid the change; it makes it
    visible — A's Phase 5 rule, that an unreachable path earns an assertion that it is
    unreachable rather than a deletion.

    The values come from the committed `config/default.yaml` through the real loader.
    Literals here would pin this file's memory of the config instead of the config, and
    the change this test exists to notice is a change to the config.
    """
    assert_entry_window_below_escalation(
        load_config(repo_root / "config" / "default.yaml", load_env=False)
    )


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
# The ruled policy table — spec 42
#
# The operator ruled on 2026-09-10: three conditions freeze, one liquidates. Each of the
# four gets a block half and a pass half **with the emitted command asserted**, because a
# table-driven test that asserted only "a row was written" would pass identically against
# the pre-ruling table, where drawdown and loss streak both escalated.
#
# Each condition is tripped in isolation on a fresh database rather than on the seed. The
# seed trips all four at once, so a command emitted against it says nothing about which
# condition produced it — and after the ruling that is the entire question.
# --------------------------------------------------------------------------- #


def exposed(store: StoreClient) -> StoreClient:
    """Exposure present: one open position and one resting entry order.

    Every freeze test runs against this, which is the point. Invariant 14's escalation
    precondition is satisfied, so an implementation that still mapped these conditions to
    `close_all` would liquidate — and the assertion that it emits `freeze` instead is
    therefore about the ruling rather than about the precondition.
    """
    write_open_position(store, "p-exposed")
    write_resting_entry_order(store, userref=9001)
    return store


def test_a_breached_drawdown_freezes_and_does_not_liquidate(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Ruled 2026-09-10. A drawdown is a statement about *past* trades: the data is
    trustworthy and the positions are being managed, so liquidating realises a paper loss
    on the system's own authority at the moment it has least evidence it is reading the
    market correctly. Freeze stops new positions and the operator decides."""
    write_equity(exposed(calm), equity="500.00", peak="1000.00", ts=2_000)

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=3_000
    )

    assert result.data["tripped"] == [SafetyCondition.DRAWDOWN.value]
    assert result.data["command_emitted"] == CommandName.FREEZE.value
    assert [row.command for row in safety_commands(calm)] == [CommandName.FREEZE.value]


def test_a_breached_loss_streak_freezes_and_does_not_liquidate(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Ruled 2026-09-10, and for the same reason as the drawdown: a losing streak is a
    statement about trades that have already closed."""
    for index in range(5):
        write_trade(exposed(calm), f"t-{index}", pnl="-10.00", closed_at=1_000 + index)

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=2_000
    )

    assert result.data["tripped"] == [SafetyCondition.LOSS_STREAK.value]
    assert result.data["command_emitted"] == CommandName.FREEZE.value
    assert [row.command for row in safety_commands(calm)] == [CommandName.FREEZE.value]


def test_a_breached_error_rate_freezes_and_does_not_liquidate(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Unchanged by the ruling and asserted anyway. Invariant 14 never listed the error
    rate as an escalation condition: it is an engine-health problem rather than account
    exposure, and liquidating because the system is throwing exceptions would be the
    breaker causing the loss it exists to prevent."""
    now = 3_600 * 1_000_000 * 2
    for index in range(20):
        write_error_block(exposed(calm), cycle_id=index + 1, ts=now - 1_000 * (index + 1))

    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=100, now_micros=now
    )

    assert result.data["tripped"] == [SafetyCondition.ERROR_RATE.value]
    assert result.data["command_emitted"] == CommandName.FREEZE.value
    assert [row.command for row in safety_commands(calm)] == [CommandName.FREEZE.value]


def test_a_sustained_outage_liquidates(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """The one condition that still escalates. Invariant 14: a sustained outage is a
    statement about *present* knowledge — the system no longer knows what it holds or what
    it is worth — and unknown exposure is worse than a bad fill."""
    result = outage_tick(exposed(calm), paper_config, fake_clients)

    assert result.data["tripped"] == [SafetyCondition.DATA_OUTAGE.value]
    assert result.data["command_emitted"] == CommandName.CLOSE_ALL.value
    assert [row.command for row in safety_commands(calm)] == [CommandName.CLOSE_ALL.value]


@pytest.mark.parametrize(
    "condition",
    [c for c in SafetyCondition if c is not SafetyCondition.DATA_OUTAGE],
)
def test_the_pass_half_of_each_freeze_condition_emits_nothing(
    calm: StoreClient, paper_config: Any, fake_clients: Any, condition: SafetyCondition
) -> None:
    """The pass halves, together, because they are the same assertion three times:
    nothing tripped, nothing emitted, nothing written. The `calm` fixture is a database in
    which none of the four conditions holds, so a pass half that started passing for the
    wrong reason would have to be a condition silently ceasing to be evaluated."""
    result = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=3_000
    )

    assert condition.value not in result.data["tripped"]
    assert result.data["command_emitted"] is None
    assert result.blocks_trading is False
    assert safety_commands(calm) == ()


def test_the_pass_half_of_the_outage_emits_nothing(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """The outage's pass half is its own test because its boundary is the only strictly
    greater one, and because it is the only condition whose pass half needs exposure
    present to be worth anything — otherwise it would be indistinguishable from the
    precondition suppressing it."""
    limit = paper_config.get("safety.max_consecutive_data_blocks")
    run_id, cycle_id = write_outage(exposed(calm), limit - 1)

    result = run_safety(
        calm,
        paper_config,
        fake_clients,
        run_id=run_id,
        cycle_id=cycle_id,
        now_micros=2_000_000_000,
        trading_blocked_by="data_guard",
    )

    assert result.data["consecutive_data_blocks"] == limit
    assert SafetyCondition.DATA_OUTAGE.value not in result.data["tripped"]
    assert result.data["command_emitted"] is None
    assert safety_commands(calm) == ()


def test_a_drawdown_and_an_outage_together_liquidate_rather_than_freeze(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """Spec 42 step 6: the more severe action wins and the two are not both emitted.

    This is the case the ruling created. Before it, every condition that could co-occur
    with the outage also escalated, so "the strongest wins" was never observable. Now a
    tick can genuinely ask for both, and it must produce exactly one `close_all` row —
    carrying **both** conditions in its reason, because the row is the permanent record of
    the decision and "drawdown *and* an outage" is a materially different account state.
    """
    write_equity(exposed(calm), equity="500.00", peak="1000.00", ts=2_000)

    result = outage_tick(calm, paper_config, fake_clients)
    rows = safety_commands(calm)

    assert set(result.data["tripped"]) == {
        SafetyCondition.DRAWDOWN.value,
        SafetyCondition.DATA_OUTAGE.value,
    }
    assert result.data["command_emitted"] == CommandName.CLOSE_ALL.value
    assert [row.command for row in rows] == [CommandName.CLOSE_ALL.value]
    assert SafetyCondition.DRAWDOWN.value in (rows[0].reason or "")
    assert SafetyCondition.DATA_OUTAGE.value in (rows[0].reason or "")


def test_the_seeded_drawdown_freezes_and_emits_no_close_all(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """Spec 42's headline assertion, and the one the pre-ruling table could not satisfy.

    The seed carries a drawdown of 0.20 against a 0.10 limit, a streak of 8 against 5,
    **and** two open positions and two resting entry orders — every precondition invariant
    14 names for an escalation. Under the old table that emitted `close_all`. Under the
    ruling it freezes, and the absence of the liquidation is asserted rather than implied.

    `cycle_id=2` is load-bearing and is the opposite choice from the escalation tests.
    The seed also carries an 18-tick outage, and a *cycle-1* anchor under a fresh `run_id`
    is treated as the first tick after a restart, so the walk crosses into the seeded runs
    and picks it up — which would emit `close_all` for a reason that has nothing to do
    with the drawdown. At cycle 2 the adjacency check breaks immediately, the stored count
    is zero, and what remains is exactly the account-state conditions.

    `trading_blocked_by="data_guard"` is the tick on which the opportunity chain is
    skipped entirely — no candidate, no `scout`, no `cost`, no `risk`. The breaker still
    acts, which is why it is a guard rather than the last link of the opportunity chain.
    """
    result = run_safety(
        seeded_store,
        paper_config,
        fake_clients,
        run_id=RUN,
        cycle_id=2,
        now_micros=seed_fixtures.seed_now,
        trading_blocked_by="data_guard",
    )
    rows = safety_commands(seeded_store)

    assert result.data["stored_data_blocks"] == 0, "the seeded outage must not be in scope"
    assert result.data["consecutive_data_blocks"] == 1, "this tick's own block, and only it"
    assert SafetyCondition.DATA_OUTAGE.value not in result.data["tripped"]
    assert SafetyCondition.DRAWDOWN.value in result.data["tripped"]
    assert result.data["open_positions"] > 0, "the escalation precondition is satisfied"
    assert result.data["resting_entry_orders"] > 0

    assert result.data["command_emitted"] == CommandName.FREEZE.value
    assert [row.command for row in rows] == [CommandName.FREEZE.value]
    assert CommandName.CLOSE_ALL.value not in [row.command for row in rows]


def test_a_suppressed_close_all_falls_through_to_the_freeze_that_was_due(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """**Ruled by the operator on 2026-09-10 and written into invariant 14.**

    Raised as an open question while implementing spec 42, escalated rather than patched
    because it is a change to what the breaker does, and ruled the way it was recommended:
    "when the winning action is suppressed, `safety` emits the strongest action that is not
    suppressed, rather than emitting nothing."

    The case: a drawdown is breached, a data outage is running, and the account has nothing
    open and nothing resting. `close_all` is the strongest action so it wins; it is then
    suppressed for want of anything to close; and the drawdown's `freeze` must still be
    emitted. More bad conditions producing less action is the wrong direction for a circuit
    breaker, and it is the one shape the rule exists to forbid.

    The operator's earlier ruling on `CONDITION_ACTION` is what made this reachable. Under
    the old table every condition that could co-occur with the outage also escalated, so a
    suppressed `close_all` could only ever swallow another `close_all` — the same command,
    so nothing was lost.

    **Both halves of the emission are asserted.** The `freeze` row is written, *and*
    `suppressed_because` still names the escalation that could not happen: a tick that
    suppressed one action and emitted another is the one case where both are true, and an
    operator reading "it froze" needs to know the outage wanted to liquidate and could not.
    """
    write_equity(calm, equity="500.00", peak="1000.00", ts=2_000)
    with_only_drawdown = run_safety(
        calm, paper_config, fake_clients, run_id=RUN, cycle_id=1, now_micros=3_000
    )
    assert with_only_drawdown.data["command_emitted"] == CommandName.FREEZE.value

    # Clear the row above so the second half is judged on what *this* tick emitted.
    calm.connection.execute("DELETE FROM commands")
    calm.connection.commit()

    with_the_outage_too = outage_tick(calm, paper_config, fake_clients)

    assert set(with_the_outage_too.data["tripped"]) == {
        SafetyCondition.DRAWDOWN.value,
        SafetyCondition.DATA_OUTAGE.value,
    }
    assert with_the_outage_too.data["command_emitted"] == CommandName.FREEZE.value, (
        "the suppressed close_all must not swallow the drawdown's freeze"
    )
    assert [row.command for row in safety_commands(calm)] == [CommandName.FREEZE.value]

    suppressed = with_the_outage_too.data["suppressed_because"] or ""
    assert SafetyCondition.DATA_OUTAGE.value in suppressed
    assert "no open position" in suppressed

    assert with_the_outage_too.blocks_trading is True
    assert with_the_outage_too.status is EngineStatus.BLOCK


def test_the_fall_through_does_not_fire_when_the_outage_is_the_only_condition(
    calm: StoreClient, paper_config: Any, fake_clients: Any
) -> None:
    """The other direction, so the ruling is pinned in both.

    A suppressed `close_all` with nothing else tripped has no lesser action to fall through
    to, and must emit nothing rather than inventing a `freeze` the account state does not
    justify. Without this, "emit the strongest action that is not suppressed" could be
    implemented as "always freeze if you cannot liquidate", which would freeze a healthy
    account on an outage it had no exposure to.
    """
    result = outage_tick(calm, paper_config, fake_clients)

    assert result.data["tripped"] == [SafetyCondition.DATA_OUTAGE.value]
    assert result.data["command_emitted"] is None
    assert safety_commands(calm) == ()


def test_nothing_but_the_outage_can_reach_close_all() -> None:
    """The scope limit, asserted rather than trusted to review.

    Spec 42: "do not make `close_all` reachable from any condition other than the data
    outage". Enumerated over the enum rather than hand-listed, so a condition added later
    has to be considered here instead of quietly inheriting whatever it was mapped to.
    """
    escalating = {
        condition
        for condition, action in CONDITION_ACTION.items()
        if action is SafetyAction.CLOSE_ALL
    }

    assert escalating == {ESCALATING_CONDITION}
    assert ESCALATING_CONDITION is SafetyCondition.DATA_OUTAGE


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


def test_no_second_close_all_while_the_outage_persists(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """The `close_all` half of spec 42's idempotency check, asserted across several ticks.

    It runs every tick, so without this a sustained outage re-triggers a liquidation
    already under way. The first tick emits; the rest see `close_intent` set — which is
    what the orchestrator does with the row at the top of the next tick — and emit nothing
    while still evaluating and still publishing the assessment.

    Every tick anchors at `cycle_id=1` under a different `run_id`. That is not tidiness:
    the outage only counts from a cycle-1 anchor, because the walk treats cycle 1 as the
    first tick after a restart and is allowed to cross into the seeded runs. Anchoring at
    2, 3, 4 the way an earlier version of this test did makes the outage stop tripping
    entirely, and the test then asserts idempotency of a condition that is not tripped.

    **The later ticks are `frozen`, not `running`, and that became load-bearing with the
    fall-through ruling.** `close_intent` is set by the command reader, which sets the mode
    to `frozen` in the same step — so `running` plus `close_intent` is a state the
    orchestrator cannot produce. An earlier version of this test held the mode at `running`
    and went red the moment a suppressed `close_all` began falling through to a `freeze`:
    correctly, because against that fixture a freeze genuinely was due. The seed trips the
    drawdown as well as the outage, so both suppressions have to hold for nothing to be
    emitted, and both are asserted.
    """
    ticks = [
        run_safety(
            seeded_store,
            paper_config,
            fake_clients,
            run_id=f"{RUN}-{index}",
            cycle_id=1,
            now_micros=seed_fixtures.seed_now + index,
            close_intent=index > 0,
            mode="running" if index == 0 else "frozen",
        )
        for index in range(5)
    ]

    assert ticks[0].data["command_emitted"] == CommandName.CLOSE_ALL.value
    assert [tick.data["command_emitted"] for tick in ticks[1:]] == [None, None, None, None]
    assert len(safety_commands(seeded_store)) == 1, "one row for one condition, not five"
    for tick in ticks[1:]:
        assert tick.data["tripped"] != [], "it still evaluates while suppressed"
        assert tick.blocks_trading is True, "it still blocks while suppressed"
        suppressed = tick.data["suppressed_because"] or ""
        assert "close_intent" in suppressed, "the escalation is suppressed"
        assert "already" in suppressed, "and so is the freeze it fell through to"


def test_no_second_freeze_while_the_drawdown_persists(
    seeded_store: StoreClient, seed_fixtures: Any, paper_config: Any, fake_clients: Any
) -> None:
    """The `freeze` half, and spec 42 requires the two separately.

    This is load-bearing in a way it was not before the ruling. Three of the four
    conditions now emit `freeze`, so a drawdown persisting across a thousand ticks is the
    common path rather than the rare one, and it must produce exactly one row.

    The mode transition is modelled rather than held fixed, because that is what makes the
    suppression work: `safety` writes the row, the orchestrator consumes it at the top of
    the next tick and sets the mode to `frozen`, and every later tick is suppressed because
    freezing a frozen system changes nothing. Holding the mode at `running` across all five
    ticks would be asserting against a state the orchestrator cannot produce — and it would
    fail, correctly, because five running ticks in drawdown genuinely are five freezes.
    """
    ticks = []
    mode = "running"
    for cycle in range(2, 7):
        result = run_safety(
            seeded_store,
            paper_config,
            fake_clients,
            run_id=RUN,
            cycle_id=cycle,
            now_micros=seed_fixtures.seed_now + cycle,
            mode=mode,
        )
        ticks.append(result)
        if result.data["command_emitted"] == CommandName.FREEZE.value:
            mode = "frozen"  # what the orchestrator does with the row on the next tick

    assert ticks[0].data["command_emitted"] == CommandName.FREEZE.value
    assert [tick.data["command_emitted"] for tick in ticks[1:]] == [None, None, None, None]
    assert len(safety_commands(seeded_store)) == 1, "one row for one drawdown, not five"
    for tick in ticks[1:]:
        assert SafetyCondition.DRAWDOWN.value in tick.data["tripped"]
        assert tick.blocks_trading is True, "it still blocks while suppressed"
        assert "already" in (tick.data["suppressed_because"] or "")


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
