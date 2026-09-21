"""Spec 29 — engine 4 `data_guard`, the first real gate.

**Six tests carry this file: a block and a pass for each of the three conditions.** A
gate with only a happy path is incomplete; a gate with only block cases is satisfied by
one that refuses everything. Neither half proves anything without the other, which is
the same shape as the envelope check in spec 25.

Each bad scenario differs from `clean` in **exactly one** respect, so a block can never
be attributed to the wrong fault — a fixture that was stale *and* crossed would let a
gate that only checked staleness pass the negative-spread test.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from tests.harness.doubles import MappingConfig

from acsoe.core.contracts import BaseEngine, Chains, EngineResult, EngineStatus
from acsoe.core.orchestrator import Orchestrator
from acsoe.engines.data_guard.contracts import (
    BAD_DATA_SCENARIOS,
    REASON_MISSING_CANDLE,
    REASON_NEGATIVE_SPREAD,
    REASON_NO_MARKET_DATA,
    REASON_STALE,
    STATE_KEY,
    bad_data_state,
)
from acsoe.engines.data_guard.engine import DataGuardEngine

MAX_AGE_S = 120.0


@pytest.fixture
def engine() -> DataGuardEngine:
    return DataGuardEngine()


@pytest.fixture
def guard_config(engine_context: Any) -> MappingConfig:
    """The committed config plus the one threshold the operator has not set yet.

    Injected rather than read, per the standing convention: a test that needs a
    threshold passes it explicitly, so it pins the value it asserts against instead of
    drifting when the operator retunes the file.
    """
    data = engine_context.config.as_dict()
    data["data_guard"] = {"max_data_age_s": MAX_AGE_S}
    return MappingConfig(data)


@pytest.fixture
def guard_context(engine_context: Any, guard_config: MappingConfig) -> Any:
    return dataclasses.replace(engine_context, config=guard_config)


def scenario(name: str) -> dict[str, Any]:
    """A deep copy. A shallow one shares `state["market_sensor"]` with the module-level
    fixture, so a test that modifies it silently changes every test after it."""
    return bad_data_state(name)


def run(engine: DataGuardEngine, context: Any, name: str) -> EngineResult:
    return engine.process(context, scenario(name))


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_it_is_a_gate_and_matches_the_registry_table(engine: DataGuardEngine) -> None:
    """`is_gate_matches_registry` asserts this too. Changing it to False silently
    demotes the first real gate in the system to a reporter."""
    assert engine.name == "data_guard"
    assert engine.number == 4
    assert engine.is_gate is True
    assert engine.name == STATE_KEY


# --------------------------------------------------------------------------- #
# Stale data — block, then pass
# --------------------------------------------------------------------------- #


def test_stale_data_blocks(engine: DataGuardEngine, guard_context: Any) -> None:
    result = run(engine, guard_context, "stale")
    assert result.blocks_trading is True
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_STALE
    assert "old" in (result.reason or "")


def test_fresh_data_passes(engine: DataGuardEngine, guard_context: Any) -> None:
    result = run(engine, guard_context, "clean")
    assert result.blocks_trading is False
    assert result.status is EngineStatus.OK
    assert result.reason is None
    assert result.data["reason_code"] is None


def test_the_threshold_is_the_one_from_config_and_not_a_constant(
    engine: DataGuardEngine, engine_context: Any
) -> None:
    """Move the threshold and the same data changes verdict. A hardcoded age would
    give the same answer to both."""
    data = engine_context.config.as_dict()

    # The clean fixture's quote is 1.0s old, so a 0.5s threshold makes it stale and a
    # very large one makes the deliberately stale fixture fresh. A hardcoded age would
    # give the same answer to both.
    data["data_guard"] = {"max_data_age_s": 0.5}
    tight = dataclasses.replace(engine_context, config=MappingConfig(dict(data)))
    assert run(engine, tight, "clean").blocks_trading is True

    data["data_guard"] = {"max_data_age_s": 999_999.0}
    loose = dataclasses.replace(engine_context, config=MappingConfig(dict(data)))
    assert run(engine, loose, "stale").blocks_trading is False


def test_a_missing_threshold_raises_rather_than_defaulting(
    engine: DataGuardEngine, engine_context: Any
) -> None:
    """The orchestrator turns the raise into ERROR and ERROR blocks. Fail closed.

    A placeholder here would be inventing the one number this gate exists to apply,
    and `data_guard.max_data_age_s` is trading behaviour only the operator may set.

    The config is built here with the key **removed**, rather than relying on
    `config/default.yaml` not carrying it. It did not until 2026-09-09, when the
    operator supplied 120 and this test went red — the assertion said "a missing
    threshold" while being held to whatever the shipped file happened to contain, which
    is the decayed-assertion shape this phase found six times. The property is worth
    keeping permanently: an absent threshold must raise rather than default, whatever
    the shipped config says today.
    """
    stripped = MappingConfig(
        {k: v for k, v in engine_context.config.as_dict().items() if k != "data_guard"}
    )
    context = dataclasses.replace(engine_context, config=stripped)
    with pytest.raises(KeyError, match="data_guard"):
        run(engine, context, "clean")


# --------------------------------------------------------------------------- #
# Negative spread — block, then pass
# --------------------------------------------------------------------------- #


def test_a_negative_spread_blocks(engine: DataGuardEngine, guard_context: Any) -> None:
    result = run(engine, guard_context, "negative_spread")
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_NEGATIVE_SPREAD
    assert "crossed" in (result.reason or "")


def test_a_positive_spread_passes(engine: DataGuardEngine, guard_context: Any) -> None:
    result = run(engine, guard_context, "clean")
    assert result.blocks_trading is False
    assert REASON_NEGATIVE_SPREAD not in str(result.data["findings"])


def test_a_zero_spread_is_not_a_negative_one(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """This gate blocks on a *crossed* book. A zero spread is engine 10's problem —
    invariant 2 says an assumed spread invalidates the cost gate, and that is a
    different refusal in a different place."""
    state = scenario("clean")
    state["market_sensor"]["quotes"]["BTC/USD"]["spread_pct"] = "0"
    assert engine.process(guard_context, state).blocks_trading is False


# --------------------------------------------------------------------------- #
# Missing candle — block, then pass
# --------------------------------------------------------------------------- #


def test_a_missing_candle_blocks(engine: DataGuardEngine, guard_context: Any) -> None:
    result = run(engine, guard_context, "missing_candle")
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_MISSING_CANDLE
    assert "no candle" in (result.reason or "")


def test_a_complete_candle_series_passes(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    result = run(engine, guard_context, "clean")
    assert result.blocks_trading is False
    assert result.data["missing_bars"] == 0


def test_blocking_here_does_not_contradict_the_loader_refusing_to_invent_one(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """Both hold, and someone "fixing" one by breaking the other is the hazard.

    The loader must never **invent** a bar; this gate must never **act** on a series
    with a hole in it. Fail-closed points in opposite directions for labelling and for
    trading. Asserted here as a statement about the gate's own behaviour: it reports
    the hole and refuses, and it does not alter the candles it was handed.
    """
    state = scenario("missing_candle")
    before = tuple(state["market_sensor"]["candles"])
    result = engine.process(guard_context, state)
    assert result.blocks_trading is True
    assert tuple(state["market_sensor"]["candles"]) == before


# --------------------------------------------------------------------------- #
# Fail closed on absent data
# --------------------------------------------------------------------------- #


def test_no_market_data_at_all_blocks(engine: DataGuardEngine, guard_context: Any) -> None:
    """Invariant 3: a gate that cannot reach its data blocks. Distinct from stale on
    purpose — "the feed is behind" and "there is no feed" are different things."""
    result = run(engine, guard_context, "no_market_data")
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_NO_MARKET_DATA
    assert result.data["pairs_seen"] == 0


def test_an_absent_market_sensor_key_blocks_rather_than_raising(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """Engine 3 has always run by now, but a chain missing an engine must not make the
    gate throw — absence of a "no" is never a "yes"."""
    result = engine.process(
        guard_context,
        {"system": {"mode": "running", "close_intent": False}, "cycle_id": 1},
    )
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_NO_MARKET_DATA


# --------------------------------------------------------------------------- #
# Reasons, and everything the tick found
# --------------------------------------------------------------------------- #


def test_the_three_conditions_report_distinct_operator_readable_reasons(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """An operator has to be able to tell a stale feed from a crossed book."""
    reasons = {
        name: run(engine, guard_context, name).reason
        for name in ("stale", "negative_spread", "missing_candle")
    }
    assert all(reason and reason.strip() for reason in reasons.values())
    assert len(set(reasons.values())) == 3


def test_every_finding_is_published_not_only_the_primary_one(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """A tick can be stale *and* crossed. An operator looking at why trading stopped
    should see both rather than whichever the engine checked first."""
    state = scenario("stale")
    state["market_sensor"]["quotes"]["BTC/USD"]["spread_pct"] = "-0.00002"
    state["market_sensor"]["missing_bars"] = (1_700_001_800,)
    result = engine.process(guard_context, state)

    codes = {finding["reason_code"] for finding in result.data["findings"]}
    assert codes == {REASON_STALE, REASON_NEGATIVE_SPREAD, REASON_MISSING_CANDLE}
    assert result.data["reason_code"] == REASON_STALE  # the most fundamental first


def test_every_reason_code_exists_in_the_consoles_prose_map() -> None:
    """A code that is not in `REASON_PROSE` renders as "No reason was recorded."
    silently, with no error anywhere. Agreed with C on 2026-09-09.

    **Enumerated from the engine's own module, never hand-listed.** It used to list
    the four codes by hand, which meant a fifth code added to `contracts.py` was
    simply not checked — the test could still fail, but not for the thing it exists
    to catch, and the failure it was guarding against is a silent blank in the
    console rather than an error anywhere. Spec 46 makes enumeration the rule for
    engine 7's codes; `data_guard` predates it and this brings it into line.

    Reading `contracts.__all__` rather than `dir()` is deliberate: `__all__` is the
    module's own declaration of what it publishes, so a code that is defined and
    deliberately not exported is out of scope here rather than a false failure.
    """
    from acsoe.console.format import REASON_PROSE
    from acsoe.engines.data_guard import contracts

    declared = {
        name: getattr(contracts, name)
        for name in contracts.__all__
        if name.startswith("REASON_")
    }
    assert declared, "no REASON_* constant found; this test has stopped enumerating"
    # The four known today, so that a code silently *disappearing* is also caught.
    assert set(declared.values()) >= {
        REASON_STALE,
        REASON_NEGATIVE_SPREAD,
        REASON_MISSING_CANDLE,
        REASON_NO_MARKET_DATA,
    }
    for name, code in declared.items():
        assert code in REASON_PROSE, f"{name} = {code!r} has no operator prose"


def test_a_block_always_carries_a_reason(engine: DataGuardEngine, guard_context: Any) -> None:
    """`core/contracts.py` enforces this and the engine must not work around it."""
    for name in ("stale", "negative_spread", "missing_candle", "no_market_data"):
        result = run(engine, guard_context, name)
        assert result.blocks_trading is True
        assert result.reason and result.reason.strip()


def test_the_state_payload_carries_no_float_money(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    data = run(engine, guard_context, "negative_spread").data
    for finding in data["findings"]:
        for value in finding.values():
            assert not isinstance(value, float)


# --------------------------------------------------------------------------- #
# The scenarios themselves
# --------------------------------------------------------------------------- #


def test_each_bad_scenario_differs_from_clean_in_exactly_one_respect() -> None:
    """Otherwise a gate that only checked staleness would pass the negative-spread
    test, because the fixture happened to be stale as well."""
    clean = BAD_DATA_SCENARIOS["clean"]["market_sensor"]
    for name in ("stale", "negative_spread", "missing_candle"):
        bad = BAD_DATA_SCENARIOS[name]["market_sensor"]
        differing = [key for key in clean if bad[key] != clean[key]]
        assert len(differing) == 1, (name, differing)


def test_the_scenarios_are_not_mutated_by_running_them(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """They are module-level fixtures shared with `scripts/verify.py`."""
    before = repr(BAD_DATA_SCENARIOS)
    for name in BAD_DATA_SCENARIOS:
        run(engine, guard_context, name)
    assert repr(BAD_DATA_SCENARIOS) == before


# --------------------------------------------------------------------------- #
# The guard chain never breaks early
# --------------------------------------------------------------------------- #


class _Probe(BaseEngine):
    """Stands in for engine 17 `safety`: a later guard that must still run."""

    name = "safety"
    number = 17
    is_gate = True

    def __init__(self) -> None:
        self.ran = 0

    def process(self, context: Any, state: Any) -> EngineResult:
        self.ran += 1
        return EngineResult(
            engine=self.name, status=EngineStatus.OK, data={"ran": self.ran}, duration_ms=0.0
        )


class _Stream:
    """A Kraken client double with no stream, so `market_sensor` reports absence."""


def test_a_second_guard_still_runs_on_a_tick_this_gate_blocked(
    guard_config: MappingConfig, fixed_clock: Any, fake_clients: Any
) -> None:
    """A bad-data block must not stop `safety` from evaluating.

    The orchestrator owns that behaviour, so this drives the **real** `Orchestrator`
    rather than asserting it about this engine in isolation — an engine cannot prove a
    property of the chain it sits in.
    """
    probe = _Probe()
    orchestrator = Orchestrator(
        config=guard_config,
        clock=fixed_clock,
        clients=fake_clients,
        chains=Chains(guard=[DataGuardEngine(), probe]),
    )
    state = orchestrator.tick()

    assert state["trading_blocked_by"] == "data_guard"
    assert probe.ran == 1
    assert [blocker["engine"] for blocker in state["guard_blockers"]] == ["data_guard"]
    assert state["safety"] == {"ran": 1}


# --------------------------------------------------------------------------- #
# D10: the feed, not one pair (operator ruling 2026-09-21)
# --------------------------------------------------------------------------- #
#
# Every scenario above uses ONE pair, and with one pair the oldest quote and the freshest
# are the same quote. That is how the engine judged the tick on its *oldest* pair for a
# fortnight while its own contract said "the freshest" — no test could tell the two apart.
# Against the real exchange's 668 USD pairs it blocked 18 of the first smoke run's 22 ticks.
# These use several pairs, so the two readings finally disagree.


def several(**ages: float) -> dict[str, Any]:
    """The clean scenario, re-quoted: one healthy quote per named pair, each at its age.

    Pair names use `_` for `/` so they can be keyword arguments; the published name keeps
    the slash. Every quote is the clean scenario's own, so a test differs from a healthy
    multi-pair tick only in the ages and spreads it sets.
    """
    state = scenario("clean")
    healthy = next(iter(state["market_sensor"]["quotes"].values()))
    quotes: dict[str, Any] = {}
    for key, age in ages.items():
        pair = key.replace("_", "/")
        quotes[pair] = {**healthy, "pair": pair, "age_s": age}
    state["market_sensor"]["quotes"] = quotes
    return state


def test_one_stale_pair_among_fresh_ones_does_not_block(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """**The D10 defect, pinned.** Tick 19 of the smoke run — the one tick that carried a
    closed decision bar — was blocked on `COOKIE/USD` at 438 s while other pairs were
    quoting. One quiet pair is that pair's problem: engine 7 excludes it."""
    state = several(BTC_USD=4.0, ETH_USD=11.0, COOKIE_USD=438.0)

    result = engine.process(guard_context, state)

    assert result.blocks_trading is False, result.reason
    assert result.data["oldest_quote_age_s"] == 438.0, "recorded, never judged"
    assert result.data["freshest_quote_age_s"] == 4.0


def test_the_heartbeat_blocks_when_even_the_freshest_quote_is_stale(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """Nothing on the subscription has moved within the bound: the feed is dead."""
    state = several(BTC_USD=125.0, ETH_USD=300.0, CSPR_USD=369.0)

    result = engine.process(guard_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_STALE
    assert "freshest" in (result.reason or "") and "125s" in (result.reason or "")


def test_the_heartbeat_is_the_freshest_quote_at_the_boundary(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """At exactly the bound the feed is alive; one second past it, it is not. Same `<=`
    as engine 7's per-pair rule, so the two engines agree on what "too old" means."""
    alive = engine.process(guard_context, several(BTC_USD=MAX_AGE_S, ETH_USD=900.0))
    dead = engine.process(guard_context, several(BTC_USD=MAX_AGE_S + 1, ETH_USD=900.0))

    assert alive.blocks_trading is False, alive.reason
    assert dead.blocks_trading is True


def test_quotes_carrying_no_age_cannot_show_the_feed_is_alive(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """Engine 3 stamps `age_s` on every quote, so this is a defect upstream — and the
    absence of a no is never a yes (invariant 3). It must not read as a healthy feed."""
    state = several(BTC_USD=1.0, ETH_USD=1.0)
    for quote in state["market_sensor"]["quotes"].values():
        del quote["age_s"]

    result = engine.process(guard_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_STALE
    assert "cannot be shown to be alive" in (result.reason or "")


def test_one_crossed_pair_among_good_ones_does_not_block(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """A thin book crossing for a moment is that pair's problem (operator ruling
    2026-09-21: engine 7, under `no_live_quote`). It used to halt every pair."""
    state = several(BTC_USD=2.0, ETH_USD=2.0, AEVO_USD=2.0)
    state["market_sensor"]["quotes"]["AEVO/USD"]["spread_pct"] = "-0.00010"

    result = engine.process(guard_context, state)

    assert result.blocks_trading is False, result.reason


def test_every_pair_crossed_is_a_corrupt_feed_and_blocks(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """Bid and ask swapped in a parser looks exactly like this. Left to engine 7 alone it
    would be every pair excluded, an empty universe and a quiet PASS — the defect hidden."""
    state = several(BTC_USD=2.0, ETH_USD=2.0, AEVO_USD=2.0)
    for quote in state["market_sensor"]["quotes"].values():
        quote["spread_pct"] = "-0.00010"

    result = engine.process(guard_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_NEGATIVE_SPREAD
    assert "Every one of the 3" in (result.reason or "")


def test_the_fresh_pair_fraction_is_recorded_on_every_tick(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """Operator ruling: record it, no screen yet. Published on a passing tick as well as a
    blocked one — a figure that only appears when trading stops says nothing about the
    ticks where it did not."""
    passing = engine.process(guard_context, several(A_USD=5.0, B_USD=60.0, C_USD=500.0))
    blocked = engine.process(guard_context, several(A_USD=500.0, B_USD=600.0))

    assert (passing.data["fresh_pairs"], passing.data["pairs_seen"]) == (2, 3)
    assert (blocked.data["fresh_pairs"], blocked.data["pairs_seen"]) == (0, 2)


def test_the_threshold_is_published_for_engine_sixteen(
    engine: DataGuardEngine, guard_context: Any
) -> None:
    """Engine 16 may not read config, so it re-checks the chosen pair against this
    published copy (D10 fix 3). It must be there on a passing tick — the only kind on
    which engine 16 ever runs."""
    result = engine.process(guard_context, several(BTC_USD=3.0))

    assert result.blocks_trading is False
    assert result.data["max_data_age_s"] == MAX_AGE_S


def test_the_staleness_key_is_shared_by_the_three_gates() -> None:
    """D10 fix 1: one key, one meaning of "too old". Engines do not import each other, so
    each names the string; this is what stops them drifting apart."""
    from acsoe.engines.data_guard.contracts import MAX_DATA_AGE_KEY, STATE_KEY, DataGuardState
    from acsoe.engines.decision import contracts as decision
    from acsoe.engines.scout import engine as scout

    assert scout.MAX_QUOTE_AGE_KEY == MAX_DATA_AGE_KEY == "data_guard.max_data_age_s"
    assert decision.DATA_GUARD_KEY == STATE_KEY
    assert decision.DATA_GUARD_MAX_AGE_FIELD in DataGuardState.model_fields
    assert decision.QUOTE_AGE_FIELD == scout.QUOTE_AGE_FIELD == "age_s"
