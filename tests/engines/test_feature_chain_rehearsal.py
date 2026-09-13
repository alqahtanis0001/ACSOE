"""Engine 5 `feature` through two real orchestrator ticks, before it is registered.

Written by B, and engine 5 is C's. That is deliberate and it is the same exception A's
`test_guard_chain_rehearsal.py` and B's `test_manage_chain_rehearsal.py` were written
under: **this file tests the orchestrator wiring, not the engine.** Whether engine 5
computes the right feature row given candles is C's `tests/engines/test_feature.py`;
whether the *orchestrator* hands it a `state` it can use, on a tick nobody staged by hand,
is nobody's until someone writes it. Registration in `bootstrap.py` is the lead's, and it
should be a formality rather than a discovery.

**Two ticks rather than one, and this is the whole point of the file.** `state` is rebuilt
from scratch every tick except `state["system"]`, so an engine quietly caching an input on
`self` passes a single-tick test and stamps tick 2 with tick 1's facts. Here the two ticks
are deliberately *different in kind* — a bar closes on the first and not on the second —
because engine 5's entire contribution to the chain's cadence is telling those apart.

**Nothing here stages a `state` dict.** Engine 5's inputs arrive from A's real engine 3
through the real `Orchestrator`, because a hand-built `state` that agrees with its caller
is the failure this project has now found five times.

## What is deliberately not in the chain, and why saying so matters

`data_guard` (4) is **out of the guard chain here**. The fake Kraken client is REST-only
and publishes no fresh book, so engine 4 blocks every tick — and a blocked tick skips the
opportunity chain entirely, which would make every assertion below vacuously true while
looking like a passing rehearsal. Leaving it out is not fabricating a pass: the last test
in this file puts engine 4 **back in** and asserts that engine 5 then does not run at all,
which is the other half of the same wiring and the half that matters for invariant 3.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import require_module
from tests.harness.doubles import MappingConfig

from acsoe.clients.kraken.contracts import TradeTick
from acsoe.clients.store.contracts import CommandName, CommandRow, CommandSource
from acsoe.core.contracts import Chains, EngineStatus
from acsoe.core.orchestrator import Orchestrator
from acsoe.engines.data_guard.engine import DataGuardEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine

pl = require_module("polars", reason="polars is not installed")

BAR = 900
TICK = 60
PAIR = "SOLUSD"
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "candles_sample.parquet"

#: Engine 5 is C's and lands in spec 64. Until it does, this whole file skips **naming the
#: module**, and `require_module` re-raises anything that is not that module — so a wrong
#: class name or a broken import inside engine 5 fails loudly here rather than skipping
#: quietly under a reason that has stopped being true.
feature_module = require_module(
    "acsoe.engines.feature.engine", reason="engine 5 `feature` (C, spec 64) does not exist yet"
)
FeatureEngine = feature_module.FeatureEngine

pytestmark = pytest.mark.skipif(
    not FIXTURE.is_file(), reason="tests/fixtures/candles_sample.parquet is not committed"
)


class ArchiveStream:
    """A market stream double: a rolling trade window and no quotes.

    Written out rather than imported from `test_feature.py` or `test_market_sensor.py`, so
    this file does not go red when another agent refactors a test of its own. It is **not**
    a stand-in for engine 3 — engine 3 itself runs below; this only feeds it, and the
    prices are the committed archive's so the candles engine 5 sees are real ones.
    """

    def __init__(self, trades: list[TradeTick]) -> None:
        self._trades = list(trades)

    def recent_trades(self) -> tuple[TradeTick, ...]:
        return tuple(self._trades)

    def latest_quote(self, pair: str) -> None:
        return None


def archive_bars(limit: int) -> list[dict[str, Any]]:
    """The newest `limit` rows of the committed OHLCVT slice, oldest first."""
    return pl.read_parquet(FIXTURE).sort("ts").tail(limit).to_dicts()


def trades_for(bars: list[dict[str, Any]]) -> list[TradeTick]:
    """Four trades per bar — open, high, low, close — that rebuild the bar exactly.

    `build_candles` takes the first price as the open, the last as the close, the max as
    the high and the min as the low. On real OHLC the high is never below the open or the
    close and the low is never above them, so this ordering reproduces all four.
    """
    out: list[TradeTick] = []
    for bar in bars:
        ts = int(bar["ts"])
        volume = Decimal(str(bar["volume"]))
        part = (volume / 4).quantize(Decimal("1e-12"))
        quantities = [part, part, part, volume - 3 * part]
        prices = [bar["open"], bar["high"], bar["low"], bar["close"]]
        for offset, (price, qty) in enumerate(zip(prices, quantities, strict=True), start=1):
            out.append(
                TradeTick(
                    pair=PAIR,
                    ts=datetime.fromtimestamp(ts, tz=UTC) + timedelta(seconds=offset),
                    price=Decimal(str(price)),
                    qty=qty,
                )
            )
    return out


def activate(store: Any, *, at: int = 1) -> None:
    """Put the system into `running` the way the console does, through a command row.

    The opportunity chain runs only when `state["system"]["mode"] == "running"`, and the
    only way into that state is a command the orchestrator's reader consumes at the top of a
    tick. Setting `state["system"]` by hand would be writing the one region of `state` the
    contract reserves for the orchestrator, and would prove nothing about whether the
    opportunity chain is reachable at all.
    """
    store.append_command(
        CommandRow(
            command=CommandName.ACTIVATE.value,
            source=CommandSource.CONSOLE,
            reason="feature-chain rehearsal",
            created_at=at,
            updated_at=at,
        )
    )


@pytest.fixture
def bars() -> list[dict[str, Any]]:
    """Enough real bars for the longest lookback to have something to stand on."""
    return archive_bars(200)


@pytest.fixture
def rehearsal_clock(bars: list[dict[str, Any]], fixed_clock: Any) -> Any:
    """A clock standing one bar and one second past the newest bar.

    That is the first instant on which the newest bar has closed, so tick 1 is a bar tick.
    The test advances it by one loop tick between ticks, which is what makes tick 2 a
    non-bar tick without anything being staged.
    """
    last_ts = int(bars[-1]["ts"])
    fixed_clock._now = datetime.fromtimestamp(last_ts + BAR + 1, tz=UTC)
    return fixed_clock


def build(
    config: MappingConfig,
    clock: Any,
    clients: Any,
    bars: list[dict[str, Any]],
    *,
    with_data_guard: bool = False,
) -> Orchestrator:
    """The real orchestrator with engine 5 first in the opportunity chain."""
    object.__setattr__(clients, "kraken", ArchiveStream(trades_for(bars)))
    guard: list[Any] = [MarketSensorEngine()]
    if with_data_guard:
        guard.append(DataGuardEngine())
    return Orchestrator(
        config=config,
        clock=clock,
        clients=clients,
        chains=Chains(guard=guard, opportunity=[FeatureEngine()]),
    )


@pytest.fixture
def rehearsal_config(paper_config: MappingConfig) -> MappingConfig:
    """The committed config plus the threshold engine 4 needs in the last test.

    Copied from the other two rehearsals for the same reason: without it engine 4 raises
    and the tick is blocked by an ERROR rather than by the data verdict, which would make
    the assertion true for the wrong reason.
    """
    data = paper_config.as_dict()
    data["data_guard"] = {"max_data_age_s": 120.0}
    return MappingConfig(data)


# --------------------------------------------------------------------------- #
# 1. Two real ticks, and the second is its own tick
# --------------------------------------------------------------------------- #


def test_two_real_ticks_complete_and_the_second_is_not_the_first(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    activate(fake_clients_with_store.store)
    orchestrator = build(rehearsal_config, rehearsal_clock, fake_clients_with_store, bars)

    first = orchestrator.tick()
    rehearsal_clock.advance(TICK)
    second = orchestrator.tick()

    assert first["cycle_id"] == 1
    assert second["cycle_id"] == 2
    assert second["system"]["mode"] == "running", "the command reader never reached running"


def test_the_bar_tick_publishes_features_and_the_next_tick_does_not(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """**The cadence mechanism, end to end through the orchestrator.**

    `engine-contracts.md`: engine 3 owns the decision-bar clock, engine 5 returns `PASS`
    when `bar_closed` is false, and the chain stops there. Every part of that is asserted
    on one run of two ticks that differ only by sixty seconds of injected clock — nothing
    is staged, and the two ticks are the same code path with a different `now`.

    The failure this is really about: an engine 5 that ignored `bar_closed` would publish
    a feature row on all fifteen ticks of every bar, and `state["feature"]` would then be
    present on ticks where no bar closed — which every downstream engine reads as "a bar
    closed", including engine 7's ranking. It is also the mutation C's own tests name.
    """
    activate(fake_clients_with_store.store)
    orchestrator = build(rehearsal_config, rehearsal_clock, fake_clients_with_store, bars)

    bar_tick = orchestrator.tick()
    rehearsal_clock.advance(TICK)
    quiet_tick = orchestrator.tick()

    assert bar_tick["market_sensor"]["bar_closed"] is True
    assert quiet_tick["market_sensor"]["bar_closed"] is False

    published = bar_tick["feature"]
    assert published["pairs"], "a bar closed and engine 5 published no pair"
    assert published["bar_ts"] == bar_tick["market_sensor"]["closed_bar_ts"]

    # `PASS` writes an empty payload, and that is the distinction the Phase 3 audit was
    # about: an absent key and a key holding an empty dict are different facts, and only
    # the first one means "no bar closed" to a reader using `.get`.
    assert quiet_tick["feature"] == {}
    # **And the empty payload alone does not say which fact it is.** Contract rule 7 turns
    # an engine that raises into `ERROR` with `data={}`, so a crashed engine 5 and a quiet
    # one are byte-identical here. They are not remotely the same tick: the second sets
    # `trading_blocked_by`, halts the chain, and writes a row engine 17 counts toward its
    # error rate. Found by mutation — removing engine 5's `bar_closed` guard left this
    # test green until this line was added, because the engine then fell over on the quiet
    # tick's absent `closed_bar_ts` and produced the same empty dict.
    assert "trading_blocked_by" not in quiet_tick, "engine 5 did not pass, it failed"


def test_the_feature_row_on_tick_two_is_recomputed_and_not_cached(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """Contract invariant 1: engines are stateless across cycles.

    Two bar ticks in a row, an hour apart, so the second closes a **different** bar. An
    engine 5 that cached its frame or its `bar_ts` on `self` at construction would be
    indistinguishable from a correct one on tick 1 and would stamp tick 2 with tick 1's
    bar — which is exactly the defect a single-tick rehearsal cannot see, and the one that
    justified this file's two-tick rule in Phase 4.
    """
    activate(fake_clients_with_store.store)
    orchestrator = build(rehearsal_config, rehearsal_clock, fake_clients_with_store, bars)

    first = orchestrator.tick()
    rehearsal_clock.advance(BAR)
    second = orchestrator.tick()

    assert second["market_sensor"]["bar_closed"] is True, "the fixture no longer closes a bar"
    assert second["feature"]["bar_ts"] != first["feature"]["bar_ts"]
    assert second["feature"]["bar_ts"] - first["feature"]["bar_ts"] == BAR


def test_the_payload_engine_7_reads_is_present_and_json_serialisable(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """The seam my own engine 7 depends on, asserted from the consumer's side.

    `ownership.md` names `state["feature"]["pairs"][pair]` as the C-to-B seam, and
    `engine-contracts.md` fixes it in the cross-chain key table. Engine 7 reads exactly
    three things out of this payload — `pairs`, `feature_names`, and each row's values —
    so those three are what a rehearsal owes the next person. Contract rule 8 requires the
    whole payload to be JSON-serialisable, which is also what forbids a NaN reaching it.
    """
    import json

    activate(fake_clients_with_store.store)
    orchestrator = build(rehearsal_config, rehearsal_clock, fake_clients_with_store, bars)

    published = orchestrator.tick()["feature"]

    assert json.loads(json.dumps(published)) == published, "the payload is not JSON-safe"

    names = published["feature_names"]
    assert names and all(isinstance(name, str) for name in names)

    for pair, row in published["pairs"].items():
        assert isinstance(pair, str)
        assert set(row) == set(names), f"{pair} publishes a different name set from feature_names"
        for value in row.values():
            # Floats or null, never NaN — ruling 8 of the phase task list, and the reason
            # engine 7 can treat null and NaN alike without the two agents disagreeing.
            assert value is None or isinstance(value, float)
            # Self-comparison on purpose: NaN is the one float that fails it, and from out
            # here that is the only way to catch one. No `noqa` because the rule that would
            # flag it is not enabled in this project, and a directive naming a rule nobody
            # runs is noise that `RUF100` correctly refuses.
            assert value is None or value == value


# --------------------------------------------------------------------------- #
# 2. The other half: a blocked guard chain means engine 5 never runs
# --------------------------------------------------------------------------- #


def test_a_guard_block_stops_the_chain_before_engine_5_runs(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """`data_guard` back in the chain, and this is why leaving it out above is honest.

    The orchestrator skips the opportunity chain entirely when anything blocked, so engine
    5 does not run and `state["feature"]` is **absent rather than empty**. Both halves are
    asserted: without the second, an engine 5 that ran anyway and published nothing would
    look identical to one that never ran.
    """
    activate(fake_clients_with_store.store)
    orchestrator = build(
        rehearsal_config, rehearsal_clock, fake_clients_with_store, bars, with_data_guard=True
    )

    state = orchestrator.tick()

    assert state["trading_blocked_by"] == "data_guard", "the fixture no longer blocks"
    assert "feature" not in state, "the opportunity chain ran on a blocked tick"


def test_the_opportunity_chain_does_not_run_while_the_system_is_idle(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """No `activate`, so the mode stays `idle` and engine 5 never runs — on a tick where a
    bar genuinely closed, which is what makes the assertion mean anything.

    A daemon always starts `idle` and reaches `running` only through a command. This is
    the pass half of the `activate` helper above: without it, every test in this file
    could be satisfied by an orchestrator that ran the opportunity chain unconditionally.
    """
    orchestrator = build(rehearsal_config, rehearsal_clock, fake_clients_with_store, bars)

    state = orchestrator.tick()

    assert state["system"]["mode"] == "idle"
    assert state["market_sensor"]["bar_closed"] is True, "the bar did close; only the mode differs"
    assert "feature" not in state


def test_engine_5_declares_itself_as_the_registry_has_it() -> None:
    """The registry table in `engine-contracts.md`: engine 5 `feature`, not a gate.

    `scripts/verify.py` asserts this too, and it is repeated here because a rehearsal held
    *before* registration is the last moment it is cheap to find wrong. A gate registered
    as an ordinary engine, or the reverse, is silent and expensive.
    """
    engine = FeatureEngine()

    assert (engine.name, engine.number, engine.is_gate) == ("feature", 5, False)


def test_engine_5_returns_pass_and_not_ok_on_a_non_bar_tick(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """`PASS` and `OK` are different answers and only `PASS` stops the chain.

    The orchestrator writes `result.data` into `state` either way, so the empty payload
    asserted above cannot tell them apart: an engine 5 returning `OK` with no data would
    leave `state["feature"] == {}` and let engines 6, 7 and the rest run on a tick where
    no bar closed. The status is the only place that distinction exists, so this reaches
    the engine directly with the `state` the orchestrator built for it.
    """
    activate(fake_clients_with_store.store)
    orchestrator = build(rehearsal_config, rehearsal_clock, fake_clients_with_store, bars)
    orchestrator.tick()
    rehearsal_clock.advance(TICK)
    quiet = orchestrator.tick()

    # The orchestrator's own context rather than one this test builds: a context assembled
    # here would be a local reproduction of the symptom, and a tripwire attached to one of
    # those cannot move when the real wiring changes.
    context = dataclasses.replace(orchestrator._context(), now=rehearsal_clock.now())
    result = FeatureEngine().process(context, quiet)

    assert result.status is EngineStatus.PASS
    assert result.blocks_trading is False
