"""Engine 17 `safety` in a real guard chain, against a real `StoreClient`. Spec 42.

B deferred exactly this check when spec 36 landed, and said why in
`context/progress/b-store.md`: `safety` sits in the guard chain and therefore runs on
every tick of `orchestrator_empty_registry` (a **Phase 0** criterion) and of
`commands_round_trip` (Phase 2), both against a real store. On an empty database nothing
should trip — but "should" was doing the work in that sentence, and if it did trip, that
finding was worth having here rather than tangled with A's in-flight engine work in a
phase gate. Spec 42 makes it due.

So this file drives the **real** `Orchestrator` over the real guard chain with a real
`StoreClient`, twice: once over an empty migrated database, and once over the Phase 0
seed. `bootstrap.py` is the lead's and registration is spec 47, so the chain is assembled
here — which is also the point. If anything surprising happens when engine 17 joins the
guard chain, it happens in B's own lane first.

**Engines 1 to 4 are A's and this file asserts nothing about them.** They are present
because a guard chain without them is not a guard chain: `data_guard` blocking is what
makes the tick realistic, and `safety` evaluating anyway on that tick is the property
being demonstrated. A's own rehearsal of engines 1 to 4 is
`tests/engines/test_guard_chain_rehearsal.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.harness.doubles import MappingConfig

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import CommandName, CommandSource
from acsoe.core.contracts import Chains, EngineStatus
from acsoe.core.orchestrator import Orchestrator
from acsoe.engines.data_guard.engine import DataGuardEngine
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_data_recorder.engine import MarketDataRecorderEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.safety.contracts import SafetyCondition
from acsoe.engines.safety.engine import SafetyEngine

#: The guard chain in registry order: 1, 2, 3, 4, 17. `engine-contracts.md` puts `safety`
#: last, after `data_guard`, and that order is load-bearing rather than cosmetic — engine 4
#: must have published `trading_blocked_by` before engine 17 reads it, or the outage count
#: is a tick behind.
GUARD_ORDER = ("exchange", "market_data_recorder", "market_sensor", "data_guard", "safety")


@pytest.fixture
def guard_config(paper_config: MappingConfig) -> MappingConfig:
    return paper_config


def build(config: MappingConfig, clock: Any, clients: Any, store: StoreClient) -> Orchestrator:
    clients.store = store
    return Orchestrator(
        config=config,
        clock=clock,
        clients=clients,
        chains=Chains(
            guard=[
                ExchangeEngine(),
                MarketDataRecorderEngine(),
                MarketSensorEngine(),
                DataGuardEngine(),
                SafetyEngine(),
            ]
        ),
    )


def safety_commands(store: StoreClient) -> tuple[str, ...]:
    """Every command `safety` wrote, **claimed or not**, oldest first.

    Read straight off the table rather than through `pending_commands()`, and the
    difference is the whole point of this file. The orchestrator claims and consumes a
    command at the top of the next tick, so by the end of tick two the row `safety` wrote
    on tick one is no longer pending — and a test counting pending rows to prove "one
    liquidation, not one per tick" would pass against an engine emitting a row every
    single tick, as long as each was consumed. An earlier version of this test did exactly
    that and passed vacuously.
    """
    rows = store.connection.execute(
        "SELECT command FROM commands WHERE source = ? ORDER BY id",
        (CommandSource.SAFETY.value,),
    ).fetchall()
    return tuple(str(row["command"]) for row in rows)


@pytest.fixture
def seeded_store(tmp_path: Path, paper_config: MappingConfig) -> Any:
    """A real `StoreClient` over the Phase 0 seed, thresholds taken from the config.

    Deliberately not the shared `seed_fixtures` fixture, for the reason
    `tests/engines/test_safety.py` records at length: that one takes `seed.py`'s module
    defaults, whose `max_errors_in_window` is 10 against the committed config's 20, so it
    produces 13 ERROR rows and the error-rate condition silently does not trip.
    """
    from decimal import Decimal

    from acsoe.clients.store.seed import SeedThresholds, seed_database

    fixtures = seed_database(
        tmp_path / "seeded.sqlite",
        thresholds=SeedThresholds(
            max_consecutive_data_blocks=paper_config.get("safety.max_consecutive_data_blocks"),
            max_drawdown_pct=Decimal(str(paper_config.get("safety.max_drawdown_pct"))),
            max_consecutive_losses=paper_config.get("safety.max_consecutive_losses"),
            error_rate_window_s=paper_config.get("safety.error_rate_window_s"),
            max_errors_in_window=paper_config.get("safety.max_errors_in_window"),
        ),
    )
    client = StoreClient(fixtures.db_path)
    try:
        yield client
    finally:
        client.close()


# --------------------------------------------------------------------------- #
# An empty database — the deferred check
# --------------------------------------------------------------------------- #


def test_on_an_empty_database_safety_trips_nothing_and_writes_nothing(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any, store: StoreClient
) -> None:
    """The check deferred in Phase 2, now due.

    An empty database has no equity snapshot, no closed trades, no error blocks, no open
    positions and no block records. Every condition must therefore read as untripped —
    and, specifically, the absent equity snapshot must read as *no drawdown measurable*
    rather than as a drawdown of zero or, worse, as a division by zero inside the breaker.

    Two ticks, because `state` is fresh every tick except `state["system"]`, and an engine
    that quietly depended on something surviving would pass a single-tick test.
    """
    orchestrator = build(guard_config, fixed_clock, fake_clients, store)

    first = orchestrator.tick()
    second = orchestrator.tick()

    for state in (first, second):
        assert state["safety"]["tripped"] == []
        assert state["safety"]["action"] == "none"
        assert state["safety"]["command_emitted"] is None
        assert state["safety"]["drawdown_pct"] is None, "absent is not a drawdown of zero"
    assert safety_commands(store) == ()


def test_safety_runs_last_in_the_guard_chain_and_after_data_guard_has_blocked(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any, store: StoreClient
) -> None:
    """The placement, asserted through the orchestrator rather than assumed.

    C's fake Kraken client is REST-only, so `market_sensor` reports no quotes and
    `data_guard` refuses the tick — which makes this a tick on which the opportunity chain
    is skipped entirely. The guard chain never breaks early, so `safety` still runs, still
    evaluates and still publishes. That is the whole reason engine 17 is a guard.

    It also has to run *after* engine 4: the outage arithmetic adds one for the current
    tick, and it can only know the current tick blocked because `data_guard` has already
    written `trading_blocked_by`.
    """
    state = build(guard_config, fixed_clock, fake_clients, store).tick()

    for name in GUARD_ORDER:
        assert name in state, name
    assert state["trading_blocked_by"] == "data_guard", "engine 4 blocked, engine 17 did not"
    assert state["safety"]["current_tick_blocked_by_data_guard"] is True
    assert state["safety"]["consecutive_data_blocks"] == 1, "this tick, and nothing stored"


def test_safety_does_not_block_a_tick_it_has_no_reason_to_block(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any, store: StoreClient
) -> None:
    """Invariant 12: every blocker is recorded, and `is_primary` on the first only.

    On an empty database `safety` must not appear among them. This is the assertion that
    would have caught a breaker tripping on nothing when the lead registers it under spec
    47, and it is the specific worry that made the registration deferrable in Phase 2.
    """
    state = build(guard_config, fixed_clock, fake_clients, store).tick()

    blockers = [blocker["engine"] for blocker in state["guard_blockers"]]
    assert "safety" not in blockers
    assert blockers == ["data_guard"]
    assert state["guard_blockers"][0]["status"] == EngineStatus.BLOCK


# --------------------------------------------------------------------------- #
# The seeded database — it trips
# --------------------------------------------------------------------------- #


def test_on_the_seeded_database_safety_trips_and_blocks_the_tick(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any, seeded_store: Any
) -> None:
    """The other half. The seed exists to carry every one of engine 17's inputs, because
    their producer is engine 19 `memory` and that is Phase 4.

    Two blockers on one tick, which is invariant 12's own example: `data_guard` on bad
    data and `safety` on an account condition. The guard chain records both and marks the
    first primary — without that rule a `safety` block co-occurring with a `data_guard`
    block would leave no trace in `block_records` at all.
    """
    state = build(guard_config, fixed_clock, fake_clients, seeded_store).tick()

    assert state["safety"]["tripped"] != []
    assert SafetyCondition.DRAWDOWN.value in state["safety"]["tripped"]
    assert SafetyCondition.LOSS_STREAK.value in state["safety"]["tripped"]

    blockers = [blocker["engine"] for blocker in state["guard_blockers"]]
    assert blockers == ["data_guard", "safety"], "both recorded, in chain order"
    assert state["trading_blocked_by"] == "data_guard", "the first one is primary"


def test_the_seeded_outage_escalates_through_the_real_chain_and_only_once(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any, seeded_store: Any
) -> None:
    """The kill switch, end to end, with nothing doubled on either side.

    The orchestrator mints `cycle_id` 1 for the first tick, and a fresh `run_id` at cycle 1
    is treated as the first tick after a restart — so the outage walk crosses into the
    seeded runs and finds their 18-tick run, which with this tick's own `data_guard` block
    is 19 against a limit of 15. The seed carries open positions and resting entry orders,
    so the escalation precondition holds and `close_all` is written.

    The second tick is what makes this worth running through the real orchestrator rather
    than through the engine alone: the command reader consumes the row at the top of it and
    sets the mode to `frozen` and `close_intent` to true. Nothing in the engine's own tests
    exercises that hand-off, because the hand-off is the orchestrator's.

    **Two things about the second tick are worth stating rather than leaving to be
    rediscovered, because the obvious prediction is wrong.**

    The outage stops tripping on it. `cycle_id` is 2, and the adjacency walk requires the
    newest stored tick to be `(this run, 1)` — it is not, so the walk breaks immediately
    and the stored count is zero. Only a *cycle-1* anchor is allowed to cross a restart
    boundary into the seeded runs.

    And that is not merely a fixture artefact: it is the Phase 3 / Phase 4 boundary
    showing through. In a running system tick 1's `data_guard` block would be written to
    `block_records` by engine 19 `memory` in the manage chain, and tick 2 would find it and
    continue the outage. Engine 19 is Phase 4 and is not in this chain, so nothing records
    the tick and the count does not carry. The suppression that fires on tick 2 is
    therefore the `freeze` one — drawdown and loss streak still trip, and the mode is
    already `frozen` — rather than the `close_intent` one. Either way exactly one row
    exists, which is the property under test.
    """
    orchestrator = build(guard_config, fixed_clock, fake_clients, seeded_store)

    first = orchestrator.tick()
    second = orchestrator.tick()
    rows = safety_commands(seeded_store)

    assert SafetyCondition.DATA_OUTAGE.value in first["safety"]["tripped"]
    assert first["safety"]["command_emitted"] == CommandName.CLOSE_ALL.value

    assert second["system"]["close_intent"] is True, "the orchestrator consumed the row"
    assert second["system"]["mode"] == "frozen"
    assert second["safety"]["tripped"] != [], "it still evaluates while suppressed"
    assert second["safety"]["command_emitted"] is None
    assert "already" in (second["safety"]["suppressed_because"] or "")

    assert rows == (CommandName.CLOSE_ALL.value,), "one liquidation, not one per tick"
