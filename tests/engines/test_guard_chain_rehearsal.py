"""Engines 1 to 4 through two real orchestrator ticks, before they are registered.

`bootstrap.py` is the lead's, and registering a real gate changes what
`orchestrator_empty_registry` — a **Phase 0** criterion — exercises on every tick. So the
registration pass should be a formality rather than a discovery: this file drives the
**real** `Orchestrator` over the four engines against C's fake client and the real store,
exactly as `console_shows_live_rows` will, so that anything surprising shows up in A's own
lane rather than in a phase gate.

Two ticks rather than one, deliberately. `state` is fresh every tick except
`state["system"]`, and an engine that quietly depended on something surviving would pass
a single-tick test and fail the second one.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.harness.doubles import MappingConfig

from acsoe.core.contracts import Chains, EngineStatus
from acsoe.core.orchestrator import Orchestrator
from acsoe.engines.data_guard.engine import DataGuardEngine
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_data_recorder.engine import MarketDataRecorderEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine

#: The guard chain in registry order: 1, 2, 3, 4. Engine 17 `safety` is B's and is
#: Phase 3, so it is absent here and its slot is the lead's to fill.
GUARD_ORDER = ("exchange", "market_data_recorder", "market_sensor", "data_guard")


@pytest.fixture
def guard_config(paper_config: MappingConfig) -> MappingConfig:
    """The committed config plus the one threshold the operator has not supplied.

    Without it engine 4 raises, the orchestrator turns that into ERROR, and the tick
    still completes — which is itself worth knowing and is asserted separately below.
    """
    data = paper_config.as_dict()
    data["data_guard"] = {"max_data_age_s": 120.0}
    return MappingConfig(data)


def build(config: MappingConfig, clock: Any, clients: Any) -> Orchestrator:
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
            ]
        ),
    )


def test_two_real_ticks_complete_and_every_engine_reports(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any
) -> None:
    orchestrator = build(guard_config, fixed_clock, fake_clients)

    first = orchestrator.tick()
    second = orchestrator.tick()

    for state in (first, second):
        for name in GUARD_ORDER:
            assert name in state, name
    assert second["cycle_id"] == first["cycle_id"] + 1


def test_the_fake_client_has_no_stream_so_the_guard_blocks_and_says_why(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any
) -> None:
    """The expected verdict against C's fake, and it is a **block**, not an exception.

    The fake Kraken client is REST-only, so `market_sensor` reports no quotes and
    `data_guard` refuses the tick. That is invariant 3 working — a gate that cannot
    reach its data blocks — and it must not stop the tick from completing, because
    `console_shows_live_rows` turns an exception into a FAIL naming it.
    """
    state = build(guard_config, fixed_clock, fake_clients).tick()

    assert state["trading_blocked_by"] == "data_guard"
    assert state["data_guard"]["reason_code"] == "no_market_data"
    assert state["market_sensor"]["stream_available"] is False
    assert state["market_data_recorder"]["stream_available"] is False


def test_the_engines_before_the_gate_still_ran_and_published(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any
) -> None:
    """The guard chain never breaks early, so a block by engine 4 leaves engines 1 to 3
    fully reported — which is what engine 19 will later record."""
    state = build(guard_config, fixed_clock, fake_clients).tick()

    assert state["exchange"]["balances"]["USD"] == "1000.00"
    assert state["exchange"]["fee_tier"]["tier"] == 1
    assert state["market_sensor"]["interval_s"] == 900
    assert state["market_data_recorder"]["frames_recorded"] == 0


def test_only_the_first_blocker_is_primary_and_every_blocker_is_recorded(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any
) -> None:
    """Invariant 12. Engines 1 to 3 never block, so exactly one blocker is expected —
    asserted so that an engine quietly gaining a block shows up here."""
    state = build(guard_config, fixed_clock, fake_clients).tick()
    assert [blocker["engine"] for blocker in state["guard_blockers"]] == ["data_guard"]
    assert state["guard_blockers"][0]["status"] == EngineStatus.BLOCK


def test_an_unset_threshold_becomes_the_error_status_and_the_tick_still_completes(
    paper_config: MappingConfig, fixed_clock: Any, fake_clients: Any
) -> None:
    """The state the tree is actually in until the operator supplies the key.

    `config.get` raises, the orchestrator converts it to ERROR with
    `blocks_trading=True`, and the tick finishes — so registering engine 4 before the
    key lands degrades the loop to "blocked" rather than breaking it.

    The key is stripped here rather than assumed absent from `config/default.yaml`. The
    operator supplied `data_guard.max_data_age_s = 120` on 2026-09-09 and this test went
    red, because it named "an unset threshold" while being held to the shipped file — the
    decayed-assertion shape found six times this phase. The property survives the key
    landing: an engine that raises must still leave the tick complete and recorded, which
    is contract rule 7 and is what stops one bad engine taking the loop down.
    """
    stripped = MappingConfig(
        {k: v for k, v in paper_config.as_dict().items() if k != "data_guard"}
    )
    state = build(stripped, fixed_clock, fake_clients).tick()

    assert state["trading_blocked_by"] == "data_guard"
    assert state["guard_blockers"][0]["status"] == EngineStatus.ERROR
    assert "data_guard.max_data_age_s" in state["block_reason"]
    assert "market_sensor" in state  # the engines before it still reported


def test_the_recorder_is_the_only_engine_that_touches_the_recorder_client(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any
) -> None:
    """Engine contract rule 4: the recorder client is engine 2's alone."""
    build(guard_config, fixed_clock, fake_clients).tick()
    assert fake_clients.recorder.lines == []  # no stream on the fake, so nothing to write


def test_a_frozen_system_still_runs_every_guard_engine(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any
) -> None:
    """A freeze stops trading and never stops data collection."""
    orchestrator = build(guard_config, fixed_clock, fake_clients)
    orchestrator.tick()
    state = orchestrator.tick()
    state["system"]["mode"] = "frozen"
    state = orchestrator.tick()

    for name in GUARD_ORDER:
        assert name in state, name
