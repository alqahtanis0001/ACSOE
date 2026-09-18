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
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import require_module
from tests.harness.doubles import MappingConfig
from tests.harness.fake_kraken import TIER_3, FakeKrakenClient, fee_tier_profile

from acsoe.clients.kraken.contracts import QuoteTick, TradeTick
from acsoe.clients.store.contracts import (
    CashSource,
    CommandName,
    CommandRow,
    CommandSource,
    EquitySnapshotRow,
    LeaderboardRow,
)
from acsoe.core.contracts import Chains, EngineStatus
from acsoe.core.orchestrator import Orchestrator
from acsoe.engines.adaptive_router.contracts import MODEL_ID as ROUTER_MODEL_ID
from acsoe.engines.adaptive_router.contracts import REASON_LEADERBOARD_EMPTY
from acsoe.engines.adaptive_router.engine import AdaptiveRouterEngine
from acsoe.engines.cost.contracts import REASON_INPUTS_UNAVAILABLE as COST_INPUTS_UNAVAILABLE
from acsoe.engines.cost.engine import CostEngine
from acsoe.engines.data_guard.engine import DataGuardEngine
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.order_book.engine import OrderBookEngine
from acsoe.engines.risk.engine import RiskEngine
from acsoe.engines.scout.engine import ScoutEngine

pl = require_module("polars", reason="polars is not installed")

#: A book as the fake client takes it: `(bids, asks)`, each level a `(price, volume)` pair
#: of decimal strings.
Book = tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]

BAR = 900
TICK = 60
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "candles_sample.parquet"

#: The **live** spelling, which is what a stream publishes and what `AssetPairs` lists.
#: `candles_sample.parquet` is SOLUSD because that is the archive *filename* spelling; the
#: prices are the same prices. The lead's ruling of 2026-09-13 fixes the same distinction
#: for BTC: `BTC/USD` live, `XBTUSD` only as an archive filename. Streaming under the
#: archive spelling would build a universe engine 7 cannot match against `AssetPairs`, and
#: the rehearsal would then "pass" with an empty universe for a reason unrelated to wiring.
PAIR = "SOL/USD"

#: The two macro assets `config/default.yaml` names, in their live spelling. Engine 6 looks
#: for exactly these, so they are what decides `available`.
MACRO_PAIRS = ("BTC/USD", "ETH/USD")

#: Engine 5 is C's and lands in spec 64. Until it does, this whole file skips **naming the
#: module**, and `require_module` re-raises anything that is not that module — so a wrong
#: class name or a broken import inside engine 5 fails loudly here rather than skipping
#: quietly under a reason that has stopped being true.
feature_module = require_module(
    "acsoe.engines.feature.engine", reason="engine 5 `feature` (C, spec 64) does not exist yet"
)
FeatureEngine = feature_module.FeatureEngine

MacroContextEngine = require_module(
    "acsoe.engines.macro_context.engine",
    reason="engine 6 `macro_context` (C, spec 65) does not exist yet",
).MacroContextEngine

RegimeEngine = require_module(
    "acsoe.engines.regime.engine", reason="engine 12 `regime` (C, spec 66) does not exist yet"
).RegimeEngine

AnomalyEngine = require_module(
    "acsoe.engines.anomaly.engine", reason="engine 13 `anomaly` (C, spec 72) does not exist yet"
).AnomalyEngine

PredictionEngine = require_module(
    "acsoe.engines.prediction.engine",
    reason="engine 8 `prediction` (C, spec 71) does not exist yet",
).PredictionEngine

#: Engine 13's refusal when no anomaly artefact is configured. Imported from C's contracts
#: rather than retyped: a code that drifted would make the assertion below pass against a
#: string nobody publishes.
ANOMALY_UNAVAILABLE = require_module(
    "acsoe.engines.anomaly.contracts", reason="engine 13 `anomaly` does not exist yet"
).REASON_UNAVAILABLE

#: Engine 8's refusal when the configured run cannot be loaded or carries no DI.
PREDICTION_UNAVAILABLE = require_module(
    "acsoe.engines.prediction.contracts", reason="engine 8 `prediction` does not exist yet"
).REASON_UNAVAILABLE

#: Engine 8's refusal when the Dissimilarity Index says the market is unlike the training
#: set. Spec 59 decision 3: a block under contract rule 6, with no `expected_move_pct`.
PREDICTION_DI_REFUSED = require_module(
    "acsoe.engines.prediction.contracts", reason="engine 8 `prediction` does not exist yet"
).REASON_DI_REFUSED

SkepticEngine = require_module(
    "acsoe.engines.skeptic.engine", reason="engine 15 `skeptic` (C, spec 73) does not exist yet"
).SkepticEngine

#: Engine 15's codes and its not-a-BUY sentence, imported from C's contracts for the reason
#: engine 13's are: a retyped string that drifted would be asserted against nothing.
skeptic_contracts = require_module(
    "acsoe.engines.skeptic.contracts", reason="engine 15 `skeptic` does not exist yet"
)
SKEPTIC_UNAVAILABLE = skeptic_contracts.REASON_UNAVAILABLE
SKEPTIC_VETO = skeptic_contracts.REASON_VETO
NOT_A_BUY_CALL = skeptic_contracts.NOT_A_BUY_CALL

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


class BookedArchiveStream(FakeKrakenClient):
    """C's fake Kraken client plus the two stream methods engine 3 reads.

    One object serves engines 1 and 3, which is how the daemon runs. The prices come from
    the committed archive and the book comes from the fake's own `order_book.json`, so
    engine 7's universe is filtered against the same fixture every other engine 7 test
    uses. The shape is `FakeKrakenWithStream` in `test_scout.py`, written out again rather
    than imported for the reason this file's other double is: a test of mine should not go
    red when another test of mine is refactored.
    """

    def __init__(
        self,
        bars: list[dict[str, Any]],
        pairs: tuple[str, ...],
        *,
        books: dict[str, Book] | None = None,
        fee_tier: int | None = None,
    ) -> None:
        super().__init__()
        from acsoe.platform.aio import run_blocking

        # Before the quotes below are taken, because the stream quote is read off this
        # same book: engine 3's spread and engine 9's walk must describe one market, and a
        # book scripted after construction would leave the quote on the fake's default.
        for pair, (bids, asks) in (books or {}).items():
            self.set_order_book(pair, bids=bids, asks=asks)
        if fee_tier is not None:
            self.use_fee_tier(fee_tier)

        # Engine 7 compares a position it sizes from equity against the **quote
        # currency's** balance, so an account with no USD excludes every USD pair for
        # `insufficient_quote_balance`. At the committed 1% risk fraction and 1.5% stop
        # that position is equity/1.5, so $5,000 of equity needs about $3,334 to be
        # affordable. Found by this rehearsal failing on its own fixture rather than on
        # anything an engine did.
        self.set_balances({"USD": "5000.00", "BTC": "0.01000000", "ETH": "0.50000000"})

        self._stream_trades = tuple(t for pair in pairs for t in trades_for(bars, pair=pair))
        last = datetime.fromtimestamp(int(bars[-1]["ts"]) + BAR, tz=UTC)
        self._stream_quotes: dict[str, QuoteTick] = {}
        for pair in pairs:
            book = run_blocking(self.order_book(pair, 10))
            self._stream_quotes[pair] = QuoteTick(
                pair=pair, ts=last, bid=book.best_bid, ask=book.best_ask
            )

    def recent_trades(self) -> tuple[TradeTick, ...]:
        return self._stream_trades

    def latest_quote(self, pair: str) -> QuoteTick | None:
        return self._stream_quotes.get(pair)


def archive_bars(limit: int) -> list[dict[str, Any]]:
    """The newest `limit` rows of the committed OHLCVT slice, oldest first."""
    return pl.read_parquet(FIXTURE).sort("ts").tail(limit).to_dicts()


#: Trades per bar never exceed this. The count only has to *vary*; a bar with thousands of
#: real trades would make the fixture slow for no gain.
MAX_TRADES_PER_BAR = 24


def trades_for(bars: list[dict[str, Any]], *, pair: str = PAIR) -> list[TradeTick]:
    """Trades that rebuild each bar exactly, in a count that **varies bar to bar**.

    `build_candles` takes the first price as the open, the last as the close, the max as
    the high and the min as the low. On real OHLC the high is never below the open or the
    close and the low is never above them, so opening with those four reproduces all four,
    and any number of filler trades at the close price leaves them untouched.

    **The count has to vary, and that is a correctness requirement rather than realism.**
    An earlier version emitted exactly four trades per bar. `modelling/features.py`
    computes `trades_z_*`, a z-score of the trade count over a lookback window, and a
    z-score over a constant series is a division by zero — NaN, published as null, and
    engine 13 then refuses the whole market-quality vector as incomplete, correctly. The
    fixture could not exhibit the property the test was about, which is the defect
    `code-standards.md` warns is worse than no test.
    """
    out: list[TradeTick] = []
    for bar in bars:
        ts = int(bar["ts"])
        volume = Decimal(str(bar["volume"]))
        # **Derived from the bar's own trade count, not clamped to it.** `min(trades, 24)`
        # was the first attempt and it saturates: real archive bars routinely carry
        # hundreds of trades, so every bar hit the ceiling and the count was constant
        # again — the same zero-dispersion defect one level down, and it reappeared on the
        # archive after being fixed on the constructed series. A modulus keeps the count
        # varying with the real one while staying small enough to build quickly.
        count = 4 + int(bar.get("trades") or 0) % (MAX_TRADES_PER_BAR - 3)
        part = (volume / count).quantize(Decimal("1e-12"))
        quantities = [part] * (count - 1) + [volume - (count - 1) * part]
        prices = [bar["open"], bar["high"], bar["low"], bar["close"]]
        prices += [bar["close"]] * (count - 4)
        for offset, (price, qty) in enumerate(zip(prices, quantities, strict=True), start=1):
            out.append(
                TradeTick(
                    pair=pair,
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
    opportunity: list[Any] | None = None,
    stream_pairs: tuple[str, ...] = (PAIR,),
    quotes: bool = False,
    books: dict[str, Book] | None = None,
    fee_tier: int | None = None,
) -> Orchestrator:
    """The real orchestrator with engine 5 first in the opportunity chain.

    `stream_pairs` decides which pairs trade, which is how engine 6's `available` is varied
    without touching config: the same archive prices are replayed under each name. **That
    is a fabrication of market data and it is deliberately confined to structure** — no
    test below asserts anything about a macro *value*, only about which assets were found
    and which were named missing. Prices that happen to be identical across three pairs
    would make a correlation meaningless, and nothing here reads one.

    `quotes` adds top-of-book, which engine 1 and engine 7 need and engine 3 republishes.
    Without it engine 7 excludes every pair for `no_live_quote`, which is correct behaviour
    and useless as a fixture.
    """
    stream: Any = (
        BookedArchiveStream(bars, stream_pairs, books=books, fee_tier=fee_tier)
        if quotes
        else ArchiveStream([t for p in stream_pairs for t in trades_for(bars, pair=p)])
    )
    object.__setattr__(clients, "kraken", stream)
    guard: list[Any] = [MarketSensorEngine()]
    if quotes:
        # Engine 1 is the account engine and engine 7 reads its balances and pair rules.
        guard.insert(0, ExchangeEngine())
    if with_data_guard:
        guard.append(DataGuardEngine())
    return Orchestrator(
        config=config,
        clock=clock,
        clients=clients,
        chains=Chains(guard=guard, opportunity=opportunity or [FeatureEngine()]),
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


# --------------------------------------------------------------------------- #
# 3. Engines 6 and 12 behind engine 5, in registry order
#
# The registry order is 5, 6, 7, 12 — engine 7 `scout` sits between them and is mine.
# Engine 12 reads `state["scout"]["pair"]` and returns PASS when there is no candidate,
# so a chain of 5, 6, 12 alone can never reach engine 12's classifier. Rather than
# fabricate a scout payload, which the rehearsal request forbids and which would be a
# hand-built `state` besides, the chain below carries the **real engine 7** in its real
# position. Nothing here is staged.
# --------------------------------------------------------------------------- #


def write_equity(store: Any, amount: str = "5000.00") -> None:
    """Engine 7 sizes against total equity, which only engine 19 computes and which is
    Phase 4. Same forward dependency engines 11 and 17 have, resolved the same way."""
    store.write_equity_snapshot(
        EquitySnapshotRow(
            cycle_id=1,
            run_id="rehearsal",
            ts=1_000,
            currency="USD",
            equity=Decimal(amount),
            peak_equity=Decimal(amount),
            cash=Decimal(amount),
            positions_value=Decimal("0.00"),
            unrealised_pnl=Decimal("0.00"),
            realised_pnl_cum=Decimal("0.00"),
            open_position_count=0,
            cash_source=CashSource.CYCLE_START,
            updated_at=1_000,
        )
    )


def full_chain() -> list[Any]:
    """Engines 5, 6, 7 and 12 in the order `engine-contracts.md` fixes."""
    return [FeatureEngine(), MacroContextEngine(), ScoutEngine(), RegimeEngine()]


def test_engine_6_reports_available_when_the_macro_pairs_are_streaming(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """Engine 6 finds both configured macro assets and says so.

    The macro pairs are streamed under their **live** spelling, which is what
    `config/default.yaml` names and what the real recorder writes. The prices replayed
    under each name are the same archive series, and this test asserts nothing about a
    macro *value* for exactly that reason — only which assets were found.
    """
    activate(fake_clients_with_store.store)
    orchestrator = build(
        rehearsal_config,
        rehearsal_clock,
        fake_clients_with_store,
        bars,
        opportunity=[FeatureEngine(), MacroContextEngine()],
        stream_pairs=(PAIR, *MACRO_PAIRS),
    )

    macro = orchestrator.tick()["macro_context"]

    assert macro["available"] is True
    assert tuple(macro["missing"]) == ()


def test_engine_6_names_the_missing_asset_rather_than_substituting_one(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """Spec 65's acceptance: `available: false` with the missing asset named.

    Only SOL/USD trades here, so neither macro pair has a candle. The engine must say
    which assets are missing rather than substitute a proxy or drop the key — a macro
    context that silently stood in for BTC would be read downstream as BTC.
    """
    activate(fake_clients_with_store.store)
    orchestrator = build(
        rehearsal_config,
        rehearsal_clock,
        fake_clients_with_store,
        bars,
        opportunity=[FeatureEngine(), MacroContextEngine()],
    )

    macro = orchestrator.tick()["macro_context"]

    assert macro["available"] is False
    assert set(macro["missing"]) == {"btc", "eth"}


def test_engine_12_passes_when_no_candidate_exists_rather_than_classifying_nothing(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """**`state["scout"]` gates engine 12, and this is the file saying so.**

    The rehearsal request asked whether a scout candidate is needed and said to report it
    rather than fabricate one. It is: engine 12 reads `state["scout"]["pair"]` and returns
    `PASS` with an empty payload when there is none. Without engine 7 in the chain there is
    never a candidate, so a 5-6-12 chain reaches engine 12 and it correctly declines to
    classify. That is the honest behaviour and it is asserted here rather than worked
    around; the next test puts the real engine 7 in and gets a label.
    """
    activate(fake_clients_with_store.store)
    orchestrator = build(
        rehearsal_config,
        rehearsal_clock,
        fake_clients_with_store,
        bars,
        opportunity=[FeatureEngine(), MacroContextEngine(), RegimeEngine()],
        stream_pairs=(PAIR, *MACRO_PAIRS),
    )

    state = orchestrator.tick()

    assert state["feature"]["pairs"], "the bar tick published no features"
    assert state["regime"] == {}, "engine 12 classified without a candidate"
    assert "trading_blocked_by" not in state, "engine 12 blocked rather than passed"


def test_the_whole_screening_chain_runs_and_engine_12_labels_the_candidate(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """Engines 5, 6, 7 and 12 in registry order, one real tick, nothing staged.

    Engine 7 is mine and sits between 6 and 12 in the registry, so putting it in is the
    chain rather than a convenience. Its candidate is what engine 12 classifies.

    The label is asserted as **a member of the closed set or null with a reason**, not as a
    particular label: which regime the archive's last bars are in is C's arithmetic and is
    tested in C's own file. What a rehearsal owes is that the payload crosses the chain
    intact and that a null carries its reason instead of a default label.
    """
    write_equity(fake_clients_with_store.store)
    activate(fake_clients_with_store.store)
    orchestrator = build(
        rehearsal_config,
        rehearsal_clock,
        fake_clients_with_store,
        bars,
        opportunity=full_chain(),
        stream_pairs=(PAIR, *MACRO_PAIRS),
        quotes=True,
    )

    state = orchestrator.tick()

    candidate = state["scout"].get("pair")
    assert candidate, f"engine 7 found no candidate: {state['scout']['excluded']}"
    assert state["regime"]["pair"] == candidate, "engine 12 classified a different pair"

    label = state["regime"]["label"]
    if label is None:
        assert state["regime"]["reason"], "a null label must carry its reason"
    else:
        assert label in {"trending", "choppy", "high_volatility"}, label
        assert state["regime"]["reason"] is None


def test_the_screening_chain_stops_at_engine_5_on_a_non_bar_tick(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """The cadence rule, now with three engines behind engine 5 to prove it stops them.

    `engine-contracts.md`: engine 5 returns `PASS` when no bar closed **and the chain stops
    there**. With only engine 5 registered that claim is untestable from outside — nothing
    downstream exists to not-run. This is the assertion the earlier tests could not make,
    and it is the reason a rehearsal of three engines is more than three rehearsals.
    """
    write_equity(fake_clients_with_store.store)
    activate(fake_clients_with_store.store)
    orchestrator = build(
        rehearsal_config,
        rehearsal_clock,
        fake_clients_with_store,
        bars,
        opportunity=full_chain(),
        stream_pairs=(PAIR, *MACRO_PAIRS),
        quotes=True,
    )

    bar_tick = orchestrator.tick()
    rehearsal_clock.advance(TICK)
    quiet_tick = orchestrator.tick()

    assert bar_tick["macro_context"], "the bar tick did not reach engine 6"
    for engine in ("macro_context", "scout", "regime"):
        assert engine not in quiet_tick, f"{engine} ran on a tick where no bar closed"
    assert quiet_tick["feature"] == {}
    assert "trading_blocked_by" not in quiet_tick


# --------------------------------------------------------------------------- #
# 4. Engines 13 and 8 behind them, in the two configurations that matter
#
# Registry order 5, 6, 7, 12, 13, 8, 9, 10, 11 — engines 10 `cost` and 11 `risk` are mine and
# sit in their real positions. Engine 9 `order_book` is C's, landed in Phase 6 (spec 96), and
# sits in its registry position since spec 94; the chain without it is kept below as the
# fail-closed half of the seam, named as such.
#
# Configuration (a) is the committed config, where `models.anomaly_run_id` and
# `models.prediction_run_id` are deliberately absent — a fresh clone has no artefact. (b)
# trains real artefacts from the committed sample into a temporary root.
# --------------------------------------------------------------------------- #

#: The DI percentile the passing path needs. **This number is the test's, not config's**,
#: and it stays the test's now that the operator has ruled one (0.99, 2026-09-15,
#: provisional). The rehearsal asserts what engine 8 does with a percentile, not what the
#: operator chose; reading the committed value would make these ticks move whenever that
#: provisional number is retuned. Engine 8 still fails closed where no percentile reaches
#: it at all — the artefact carries the one it was trained at, so a run trained without a
#: percentile carries no `di.npz` and is refused on load.
TEST_DI_PERCENTILE = 0.99


class Wrapped:
    """The committed config with named keys answered, and nothing else changed.

    The same shape C-2 uses in `test_prediction.py`. Written out rather than imported for
    this file's standing reason, and because importing a fixture from another agent's test
    would make my rehearsal go red when they refactor theirs.
    """

    def __init__(self, inner: Any, **overrides: Any) -> None:
        self._inner = inner
        self._overrides = overrides

    def get(self, key: str) -> Any:
        if key in self._overrides:
            value = self._overrides[key]
            if value is _ABSENT_KEY:
                raise KeyError(f"config has no key {key!r}")
            return value
        return self._inner.get(key)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _AbsentKey:
    """Sentinel: the key is not there at all, which is not the same as `None`."""


_ABSENT_KEY = _AbsentKey()


def judgement_chain(*, with_order_book: bool = True) -> list[Any]:
    """Engines 5, 6, 7, 12, 13, 8, 9, 10, 11 in the order `engine-contracts.md` fixes.

    `with_order_book=False` drops engine 9 and nothing else, for the one test about what
    engine 10 does when nothing published a slippage estimate. It is not the registry.
    """
    chain = [
        FeatureEngine(),
        MacroContextEngine(),
        ScoutEngine(),
        RegimeEngine(),
        AnomalyEngine(),
        PredictionEngine(),
        OrderBookEngine(),
        CostEngine(),
        RiskEngine(),
    ]
    if not with_order_book:
        chain = [engine for engine in chain if not isinstance(engine, OrderBookEngine)]
    return chain


def test_without_an_artefact_engine_13_blocks_and_nothing_after_it_runs(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """Configuration (a): the committed config, which names no artefact.

    `models.anomaly_run_id` is deliberately absent — a fresh clone has no `models/` — so
    engine 13 blocks with `anomaly_unavailable`. **The assertion that matters is the
    second one**: engines 8, 9, 10 and 11 must not appear in `state` at all. A gate that
    blocked while the chain kept running would be a gate in name only, and invariant 4
    rests on the chain stopping.
    """
    write_equity(fake_clients_with_store.store)
    activate(fake_clients_with_store.store)
    orchestrator = build(
        rehearsal_config,
        rehearsal_clock,
        fake_clients_with_store,
        bars,
        opportunity=judgement_chain(),
        stream_pairs=(PAIR, *MACRO_PAIRS),
        quotes=True,
    )

    state = orchestrator.tick()

    assert state["trading_blocked_by"] == "anomaly"
    assert state["anomaly"]["reason_code"] == ANOMALY_UNAVAILABLE
    for engine in ("prediction", "order_book", "cost", "risk"):
        assert engine not in state, f"{engine} ran after the chain was blocked"
    # And the engines before it did run, so this is a block at 13 rather than a chain that
    # never started: without this the test would pass against a broken engine 5.
    assert state["scout"].get("pair"), "the chain never reached engine 7"
    assert state["regime"]["pair"] == state["scout"]["pair"]


def test_the_block_carries_a_reason_the_console_can_render(
    rehearsal_config: MappingConfig, rehearsal_clock: Any, fake_clients_with_store: Any, bars: Any
) -> None:
    """Invariant 12: a rejection is research data, and `anomaly_unavailable` is the code
    engine 19 would write. A code absent from the console's `REASON_PROSE` renders "No
    reason was recorded." silently, so the seam is checked here rather than assumed."""
    from acsoe.console.format import REASON_PROSE

    write_equity(fake_clients_with_store.store)
    activate(fake_clients_with_store.store)
    orchestrator = build(
        rehearsal_config,
        rehearsal_clock,
        fake_clients_with_store,
        bars,
        opportunity=judgement_chain(),
        stream_pairs=(PAIR, *MACRO_PAIRS),
        quotes=True,
    )

    state = orchestrator.tick()

    assert state["block_reason"], "a block with no reason violates contract rule 6"
    assert ANOMALY_UNAVAILABLE in REASON_PROSE, "the console cannot render this code"


# --------------------------------------------------------------------------- #
# 4b. Configuration (b): real artefacts, trained from the committed sample
# --------------------------------------------------------------------------- #

#: The anomaly threshold percentile the fixture trains with. **The test's number, not
#: config's**, for the same reason as `TEST_DI_PERCENTILE`: `anomaly.threshold_percentile`
#: is the operator's key and is deliberately absent from `config/default.yaml`.
TEST_ANOMALY_PERCENTILE = 0.99


@pytest.fixture(scope="module")
def trained(tmp_path_factory: Any) -> tuple[Path, str]:
    """One fold trained from the committed sample into a temporary artefact root.

    Module-scoped because it fits real models: one fit shared by every test below. The
    artefacts are written through **B's real `StoreClient`** path that `research/training.py`
    uses, so this also exercises `new_model_run_dir` in the position it was built for.

    Both percentiles are supplied here and nowhere else. They are the operator's keys, they
    are absent from the committed config on purpose, and a number in that file would be a
    test lane deciding when a model may refuse a trade.
    """
    from tests.harness.doubles import load_default_config
    from tests.research.test_training import NOW, dataset_for

    from acsoe.research import training

    config = load_default_config()
    root = tmp_path_factory.mktemp("rehearsal-models")
    report = training.train_walkforward(
        dataset_for(config, random_walk=False),
        config=Wrapped(
            config,
            **{
                "prediction.di_percentile": TEST_DI_PERCENTILE,
                "anomaly.threshold_percentile": TEST_ANOMALY_PERCENTILE,
            },
        ),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=1,
    )
    run_id = report.fold_runs[0]
    directory = report.models_dir / run_id
    assert (directory / "di.npz").is_file(), "no DI was fitted; every path below would block"
    assert (directory / "anomaly.joblib").is_file(), "no anomaly detector; 13 would block"
    return report.models_dir, run_id


@pytest.fixture(scope="module")
def trained_bars() -> list[dict[str, Any]]:
    """The tail of **the same series the fixture models were trained on**.

    Not the archive, and the reason is the Dissimilarity Index rather than convenience: to
    a model that has never seen them, real archive bars are exactly the market the DI
    exists to refuse — C measured that at DI 1.024 against a 1.023 threshold. A rehearsal
    that scored out-of-distribution bars would refuse every candidate and everything past
    the DI would be unreachable, so the passing path is driven from the training
    distribution and the refusal is C's own test to induce.
    """
    from tests.research.test_training import candle_frame

    frame = candle_frame("AAAUSD", interval_s=BAR, random_walk=False, days=140)
    return [
        {
            "ts": int(row["ts"]),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "trades": int(row["trades"]),
        }
        for row in frame.tail(300).to_dicts()
    ]


@pytest.fixture
def trained_clock(trained_bars: list[dict[str, Any]], fixed_clock: Any) -> Any:
    """One bar and one second past the newest trained bar: the first bar tick."""
    fixed_clock._now = datetime.fromtimestamp(int(trained_bars[-1]["ts"]) + BAR + 1, tz=UTC)
    return fixed_clock


def artefact_config(
    base: MappingConfig, root: Path, run_id: str, **overrides: Any
) -> Any:
    """The committed config naming the trained run, plus whatever the test needs.

    **The pair the model sees is not the pair it was trained on, and that is deliberate.**
    `modelling/features.py` encodes no pair identity — spec 63 forbids it, because a pooled
    model that can memorise a pair name has learned nothing that transfers — so replaying
    the training distribution under a tradable pair name is exactly the situation the live
    system is in, and it is what lets engine 7 select a candidate at all.
    """
    return Wrapped(
        base,
        **{
            "models.prediction_run_id": run_id,
            "models.anomaly_run_id": run_id,
            "data_guard.max_data_age_s": 120.0,
            **overrides,
        },
    )


def build_trained(
    config: Any,
    clock: Any,
    clients: Any,
    bars: list[dict[str, Any]],
    root: Path,
    *,
    opportunity: list[Any] | None = None,
) -> Orchestrator:
    """The judgement chain, or the chain given, against a store that knows the artefact root."""
    from acsoe.clients.store.client import StoreClient

    store = StoreClient(clients.store.db_path, models_dir=root)
    object.__setattr__(clients, "store", store)
    write_equity(store)
    activate(store)
    return build(
        config,
        clock,
        clients,
        bars,
        opportunity=opportunity if opportunity is not None else judgement_chain(),
        stream_pairs=(PAIR, *MACRO_PAIRS),
        quotes=True,
    )


@pytest.fixture(scope="module")
def trained_without_di(tmp_path_factory: Any) -> tuple[Path, str]:
    """A run trained while `prediction.di_percentile` was absent, so it carries no DI.

    This is what the operator's unset key actually produces, and it is the fixture the
    refusal below needs. The anomaly percentile is still supplied, so engine 13 passes and
    the chain reaches engine 8 — otherwise the test would pass on engine 13's block and
    prove nothing about engine 8.
    """
    from tests.harness.doubles import load_default_config
    from tests.research.test_training import NOW, dataset_for

    from acsoe.research import training

    config = load_default_config()
    root = tmp_path_factory.mktemp("rehearsal-models-no-di")
    report = training.train_walkforward(
        dataset_for(config, random_walk=False),
        config=Wrapped(
            config,
            **{
                "anomaly.threshold_percentile": TEST_ANOMALY_PERCENTILE,
                # Removed explicitly since 2026-09-15: the operator ruled a percentile, so
                # inheriting the committed config would train a run that *has* a DI, and the
                # assertion below would void this fixture rather than describe it.
                "prediction.di_percentile": None,
            },
        ),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=1,
    )
    run_id = report.fold_runs[0]
    assert not (report.models_dir / run_id / "di.npz").exists(), (
        "the trainer fitted a DI with no percentile configured; this fixture is void"
    )
    return report.models_dir, run_id


def test_a_run_trained_without_the_di_percentile_makes_engine_8_block(
    paper_config: MappingConfig,
    trained_clock: Any,
    fake_clients_with_store: Any,
    trained_bars: Any,
    trained_without_di: tuple[Path, str],
) -> None:
    """**Asserted before the passing path, deliberately, and it corrects the request.**

    The rehearsal request expected engine 8 to block while `prediction.di_percentile` is
    absent. It does, but **not by reading that key** — the key is read by
    `research/training.py` and nowhere else, and a run trained without it simply carries no
    `di.npz`. Engine 8 then refuses to load the run at all, saying so in as many words:
    *"That run was trained while `prediction.di_percentile` was absent, which is the
    operator's key; engine 8 will not predict without the refusal it exists to make."*

    So the fail-closed property spec 59 decision 9 asks for is real and is enforced at the
    artefact rather than at the config read. **The distinction matters and is reported to
    the lead rather than papered over**: an artefact trained with somebody else's
    percentile predicts happily while the operator's key is still absent, because the
    threshold travels in the artefact. That is a question about when a model may refuse a
    trade, so it is the operator's, not this rehearsal's.
    """
    root, run_id = trained_without_di
    config = artefact_config(paper_config, root, run_id)
    orchestrator = build_trained(config, trained_clock, fake_clients_with_store, trained_bars, root)

    state = orchestrator.tick()

    assert state["anomaly"]["reason_code"] is None, (
        f"engine 13 blocked; this is engine 8's test: {state.get('block_reason')}"
    )
    assert state["trading_blocked_by"] == "prediction"
    assert state["prediction"]["reason_code"] == PREDICTION_UNAVAILABLE
    assert state["prediction"].get("expected_move_pct") is None, (
        "a refusal published an expected move, which engine 10 would price a hurdle from"
    )
    assert "di_percentile" in str(state["block_reason"]), (
        "the block does not say which operator key is missing, so nobody can act on it"
    )
    for engine in ("order_book", "cost", "risk"):
        assert engine not in state, f"{engine} ran on a prediction that never happened"


def test_with_artefacts_the_chain_reaches_engine_8_and_publishes_what_10_reads(
    paper_config: MappingConfig,
    trained_clock: Any,
    fake_clients_with_store: Any,
    trained_bars: Any,
    trained: tuple[Path, str],
) -> None:
    """Configuration (b): engine 13 passes, engine 8 predicts, engine 10 reads it.

    The DI percentile supplied here is **the test's number and not config's**, and it is
    supplied only after the refusal above has been asserted, so the passing path cannot be
    mistaken for the default.

    `expected_move_pct` is asserted to be a **string**: contract rule 8 requires money to
    cross `state` as an exact decimal string, and engine 10 parses it as one. A float here
    would arrive in a hurdle comparison wrong in the fourth decimal, which is the magnitude
    the cost gate operates at.
    """
    root, run_id = trained
    config = artefact_config(
        paper_config, root, run_id, **{"prediction.di_percentile": TEST_DI_PERCENTILE}
    )
    orchestrator = build_trained(config, trained_clock, fake_clients_with_store, trained_bars, root)

    state = orchestrator.tick()

    assert state["anomaly"]["reason_code"] is None
    assert state["trading_blocked_by"] != "anomaly"

    prediction = state["prediction"]
    assert prediction.get("reason_code") is None, prediction.get("reason_code")
    probabilities = [prediction["p_target"], prediction["p_stop"], prediction["p_timeout"]]
    assert all(isinstance(p, float) for p in probabilities)
    assert all(0.0 <= p <= 1.0 for p in probabilities), probabilities
    assert abs(sum(probabilities) - 1.0) < 1e-9, "calibrated probabilities must sum to 1"

    assert isinstance(prediction["expected_move_pct"], str), "money crosses state as a string"
    Decimal(prediction["expected_move_pct"])
    assert isinstance(prediction["di"], float)
    assert isinstance(prediction["di_threshold"], float)

    # Engine 10 read it. Whether it then blocks is a separate question and is the next test.
    assert "cost" in state, "engine 10 never ran on a tick engine 8 completed"


def test_the_di_refuses_market_data_the_model_never_saw_and_publishes_no_expected_move(
    paper_config: MappingConfig,
    rehearsal_clock: Any,
    fake_clients_with_store: Any,
    bars: Any,
    trained: tuple[Path, str],
) -> None:
    """**The refusal, driven by real out-of-distribution data rather than by a stub.**

    The artefacts are trained on the constructed series; these are real SOLUSD bars from
    the committed archive. To a model that has never seen them that is exactly the market
    the Dissimilarity Index exists to refuse, and C measured it at DI 1.024 against a
    1.023 threshold — the mechanism working, not a bug.

    **The assertion that carries the weight is the absent `expected_move_pct`.** Spec 59
    decision 3: engine 8 blocks on a DI refusal and publishes no expected move, so engine
    10 fails closed on the absent key. An engine that compared the DI *after* asking the
    model would have an expected move in hand at this point, and publishing it would let
    the cost gate price a hurdle from a prediction the DI had already distrusted.
    """
    root, run_id = trained
    config = artefact_config(
        paper_config, root, run_id, **{"prediction.di_percentile": TEST_DI_PERCENTILE}
    )
    orchestrator = build_trained(config, rehearsal_clock, fake_clients_with_store, bars, root)

    state = orchestrator.tick()

    assert "prediction" in state, (
        f"the chain stopped before engine 8: blocked by {state.get('trading_blocked_by')} "
        f"reason {state.get('block_reason')}"
    )
    prediction = state["prediction"]
    assert prediction["reason_code"] == PREDICTION_DI_REFUSED, (
        f"the archive bars did not refuse: {prediction}"
    )
    assert state["trading_blocked_by"] == "prediction"
    assert prediction.get("expected_move_pct") is None, (
        "a DI refusal published an expected move, which engine 10 would price a hurdle from"
    )
    # The DI and its threshold are still published: the console renders them and engine 14
    # will weight by them in Phase 6, so a refusal is a reading rather than a silence.
    assert isinstance(prediction["di"], float)
    assert isinstance(prediction["di_threshold"], float)
    assert prediction["di"] > prediction["di_threshold"]
    for engine in ("order_book", "cost", "risk"):
        assert engine not in state, f"{engine} ran on a refused prediction"


def test_without_engine_9_before_it_engine_10_blocks_and_names_the_missing_estimate(
    paper_config: MappingConfig,
    trained_clock: Any,
    fake_clients_with_store: Any,
    trained_bars: Any,
    trained: tuple[Path, str],
) -> None:
    """**The fail-closed half of the 9-to-10 seam, and it is no longer the registry.**

    Until spec 94 this was the honest end of the chain: engine 9 did not exist, so engine 10
    met an absent `estimated_slippage_pct` and blocked, and this test said so under the name
    `test_engine_10_stops_the_chain_for_want_of_engine_9_and_says_so`. Engine 9 has landed
    and the registry chain is rehearsed in section 6; this keeps the other half. Invariant 2
    gives slippage no fallback and invariant 3 says a gate that cannot reach its data
    blocks, so a chain with engine 9 removed must stop at engine 10 **naming the publisher it
    could not read** — `order_book` as a whole, since nothing wrote the payload at all. (A
    payload carrying the estimate under another name is named down to the key instead; that
    case is the spec 94 mutation M1, and section 6 is what kills it.)
    """
    root, run_id = trained
    config = artefact_config(
        paper_config, root, run_id, **{"prediction.di_percentile": TEST_DI_PERCENTILE}
    )
    orchestrator = build_trained(
        config,
        trained_clock,
        fake_clients_with_store,
        trained_bars,
        root,
        opportunity=judgement_chain(with_order_book=False),
    )

    state = orchestrator.tick()

    assert "order_book" not in state, "the chain under test was supposed to omit engine 9"
    assert state["trading_blocked_by"] == "cost"
    assert state["cost"]["reason_code"] == COST_INPUTS_UNAVAILABLE, state["cost"]
    assert "missing order_book is NoneType" in str(state["block_reason"]), state["block_reason"]
    assert "risk" not in state, "engine 11 ran after the cost gate blocked"


def test_engines_13_and_8_declare_themselves_as_the_registry_has_them() -> None:
    """Engine 13 is a gate; engine 8 is not, even though it blocks on a DI refusal.

    That asymmetry is spec 59 decision 3 and it is easy to read as a mistake: `is_gate` is
    the declaration `verify.py` checks against the registry table, and contract rule 6
    already lets any engine halt the tick. Asserted here so a rehearsal held before
    registration is where a wrong declaration surfaces.
    """
    assert (AnomalyEngine().name, AnomalyEngine().number, AnomalyEngine().is_gate) == (
        "anomaly",
        13,
        True,
    )
    assert (PredictionEngine().name, PredictionEngine().number, PredictionEngine().is_gate) == (
        "prediction",
        8,
        False,
    )


def test_engines_6_and_12_declare_themselves_as_the_registry_has_them() -> None:
    """Neither is a gate. `scripts/verify.py` asserts this against the registry table, and
    a rehearsal held before registration is the last cheap moment to find it wrong."""
    assert (MacroContextEngine().name, MacroContextEngine().number) == ("macro_context", 6)
    assert MacroContextEngine().is_gate is False
    assert (RegimeEngine().name, RegimeEngine().number) == ("regime", 12)
    assert RegimeEngine().is_gate is False


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


# --------------------------------------------------------------------------- #
# 5. Engine 15 `skeptic` behind them
# --------------------------------------------------------------------------- #

#: Folds the skeptic fixture trains. Spec 69: fold 0 has no earlier out-of-sample BUY calls
#: and trains no skeptic, so a one-fold run — which is what `trained` above is — can only
#: ever exercise `skeptic_unavailable`.
SKEPTIC_FOLDS = 4

#: The macro asset the skeptic fixture joins, spelled as `tests/engines/test_prediction.py`
#: spells it and written out for this file's standing reason. With it the manifest names
#: macro columns, so engine 15 assembles its vector from engines 5 **and** 6 the way it does
#: live; without it the macro half of `_vector` never runs here.
SKEPTIC_MACRO_ARCHIVE = {"btc": "AAAUSD"}


def skeptic_chain() -> list[Any]:
    """Engines 5, 6, 7, 12, 13, 8 and 15, registry order kept, **9, 10, 11 and 14 omitted**.

    Written in Phase 5, when engine 10 `cost` blocked for want of engine 9 and engine 15 was
    unreachable in the registry chain, so it was rehearsed without the engines between it
    and engine 8. That reason is gone — section 6 drives the full registry chain to engine
    15 — and this chain is kept for what it is still good for: engine 15's unavailable,
    not-a-BUY, veto and pass cases alone, with no cost or sizing arithmetic between the
    prediction and the gate that could stop the tick first.
    """
    return [
        FeatureEngine(),
        MacroContextEngine(),
        ScoutEngine(),
        RegimeEngine(),
        AnomalyEngine(),
        PredictionEngine(),
        SkepticEngine(),
    ]


@pytest.fixture(scope="module")
def trained_skeptic(tmp_path_factory: Any) -> tuple[Path, str]:
    """`(models root, the latest fold run whose manifest records a skeptic)`.

    Both percentiles are the test's numbers, as in `trained`. The run id is chosen by reading
    each fold's manifest for `extras.skeptic` and `skeptic.txt` on disk, not by trusting the
    report's row count, and fold 0 is asserted to carry none so the fixture is known to be
    exercising spec 69's rule rather than a trainer that stopped following it.
    """
    import json

    from tests.harness.doubles import load_default_config
    from tests.research.test_training import NOW, dataset_for

    from acsoe.research import training

    config = load_default_config()
    root = tmp_path_factory.mktemp("rehearsal-models-skeptic")
    report = training.train_walkforward(
        dataset_for(config, random_walk=False, macro_archive=SKEPTIC_MACRO_ARCHIVE),
        config=Wrapped(
            config,
            **{
                "prediction.di_percentile": TEST_DI_PERCENTILE,
                "anomaly.threshold_percentile": TEST_ANOMALY_PERCENTILE,
            },
        ),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=SKEPTIC_FOLDS,
    )

    def has_skeptic(run_id: str) -> bool:
        directory = report.models_dir / run_id
        manifest = json.loads((directory / "manifest.json").read_bytes().decode("utf-8"))
        recorded = (manifest.get("extras") or {}).get("skeptic")
        return isinstance(recorded, dict) and (directory / "skeptic.txt").is_file()

    assert not has_skeptic(report.fold_runs[0]), "fold 0 trained a skeptic; spec 69 says never"
    with_skeptic = [run_id for run_id in report.fold_runs if has_skeptic(run_id)]
    assert with_skeptic, "no fold trained a skeptic, so every veto assertion is unreachable"
    run_id = with_skeptic[-1]
    directory = report.models_dir / run_id
    assert (directory / "di.npz").is_file(), "no DI; engine 8 would block before 15"
    assert (directory / "anomaly.joblib").is_file(), "no anomaly detector; 13 would block"
    return report.models_dir, run_id


def skeptic_config(base: MappingConfig, root: Path, run_id: str, **overrides: Any) -> Any:
    """`artefact_config` plus the DI percentile, with the skeptic keys left to the caller."""
    return artefact_config(
        base, root, run_id, **{"prediction.di_percentile": TEST_DI_PERCENTILE, **overrides}
    )


#: Where the two market windows below end, in bars before the end of the constructed series.
#: **Both are the test's choice, found by replaying windows through this same chain**, and
#: both are asserted on every run rather than trusted: the window ending at the series' end
#: makes engine 8 call no BUY (`expected_move_pct` -0.015), and the one ending 200 bars
#: earlier makes it call a BUY (+0.030). A retrained model that moves either answer turns the
#: test that needs it red by name instead of leaving a vacuous branch green.
NOT_A_BUY_WINDOW_END = 0
BUY_WINDOW_END = 200

#: Bars per replayed window, as `trained_bars` uses.
WINDOW_BARS = 300


@pytest.fixture(scope="module")
def constructed_rows() -> list[dict[str, Any]]:
    """The whole constructed series `trained_bars` is the tail of, as bar mappings."""
    from tests.research.test_training import candle_frame

    frame = candle_frame("AAAUSD", interval_s=BAR, random_walk=False, days=140)
    return [
        {
            "ts": int(row["ts"]),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "trades": int(row["trades"]),
        }
        for row in frame.to_dicts()
    ]


def window(rows: list[dict[str, Any]], bars_before_end: int) -> list[dict[str, Any]]:
    end = len(rows) - bars_before_end
    return rows[end - WINDOW_BARS : end]


def at_bar_tick(clock: Any, bars: list[dict[str, Any]]) -> Any:
    """One bar and one second past the window's newest bar: the first bar tick."""
    clock._now = datetime.fromtimestamp(int(bars[-1]["ts"]) + BAR + 1, tz=UTC)
    return clock


class RecordingSkeptic(SkepticEngine):  # type: ignore[misc, valid-type]
    """The real engine 15, with every result it returned kept.

    **Not a double**: `process` is the real one, called unchanged. It exists because `state`
    carries a payload and never a status, and `OK` and `BLOCK` are the two answers this
    section is about. A payload alone can be matched by an `ERROR` — contract rule 7 — so
    the status is asserted beside it, from what the engine returned.
    """

    def __init__(self) -> None:
        super().__init__()
        self.results: list[Any] = []

    def process(self, context: Any, state: Any) -> Any:
        result = super().process(context, state)
        self.results.append(result)
        return result


def run_two_ticks(
    config: Any,
    clock: Any,
    clients: Any,
    bars: list[dict[str, Any]],
    root: Path,
    skeptic: RecordingSkeptic,
    *,
    first_build: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A bar tick, then a tick sixty seconds later on which no bar closes.

    `first_build=False` reuses a store `build_trained` already seeded, for a test that needs
    two orchestrators over one bar: the equity snapshot it writes is unique per cycle.
    """
    chain = [*skeptic_chain()[:-1], skeptic]
    if first_build:
        orchestrator = build_trained(config, clock, clients, bars, root, opportunity=chain)
    else:
        orchestrator = build(
            config,
            clock,
            clients,
            bars,
            opportunity=chain,
            stream_pairs=(PAIR, *MACRO_PAIRS),
            quotes=True,
        )
        activate(clients.store, at=2)
    bar_tick = orchestrator.tick()
    clock.advance(TICK)
    quiet_tick = orchestrator.tick()
    return bar_tick, quiet_tick


def the_prediction(state: dict[str, Any]) -> dict[str, Any]:
    """Engine 8's payload, asserted to be a prediction rather than a refusal or an absence."""
    assert "prediction" in state, (
        f"the chain stopped before engine 8: {state.get('trading_blocked_by')} "
        f"{state.get('block_reason')}"
    )
    prediction: dict[str, Any] = state["prediction"]
    assert prediction.get("reason_code") is None, (prediction.get("reason_code"), prediction)
    return prediction


def assert_quiet_tick(quiet_tick: dict[str, Any], skeptic: RecordingSkeptic) -> None:
    """Configuration 3: engine 5 passes, and engine 15 neither runs nor leaves a key.

    The empty feature payload is also what an engine 5 that raised would leave, so the
    absence of a blocker is asserted beside it; and engine 15's own record says it ran on
    exactly one of the two ticks.
    """
    assert quiet_tick["market_sensor"]["bar_closed"] is False
    assert quiet_tick["feature"] == {}
    assert "trading_blocked_by" not in quiet_tick, "engine 5 did not pass, it failed"
    assert "skeptic" not in quiet_tick, "engine 15 ran on a tick where no bar closed"
    assert len(skeptic.results) == 1, "engine 15 ran on the quiet tick"


def recomputed_p_wrong(state: dict[str, Any], root: Path, run_id: str) -> float:
    """`p_wrong` from the artefact itself, never from what engine 15 published.

    The manifest's recorded input order, the run's own scaler, `skeptic.txt`, and the values
    engines 5, 6 and 8 put into this tick's `state`. A threshold derived from the engine's
    own number would move with any mutation of that number — reading P(right), say — and
    the veto and pass tests would both stay green around it.
    """
    import json

    import lightgbm as lgb
    import numpy as np

    from acsoe.modelling.artefacts import load_run

    directory = root / run_id
    manifest = json.loads((directory / "manifest.json").read_bytes().decode("utf-8"))
    feature_names = list(manifest["feature_names"])
    extras = ["p_target", "p_stop", "p_timeout", "expected_move_pct"]
    assert list(manifest["extras"]["skeptic"]["input_names"]) == [*feature_names, *extras]
    assert any(name.startswith("macro_") for name in feature_names), (
        "the manifest names no macro column, so engine 6's half of the vector is untested"
    )

    prediction = state["prediction"]
    row = state["feature"]["pairs"][prediction["pair"]]
    macro = state["macro_context"]["features"]
    raw = [float(macro[name]) if name in macro else float(row[name]) for name in feature_names]
    loaded = load_run(directory, expected_features=tuple(feature_names))
    vector = [*loaded.scaler.transform([raw])[0], *(float(prediction[name]) for name in extras)]
    booster = lgb.Booster(model_file=str(directory / "skeptic.txt"))
    scored = booster.predict(np.asarray([vector], dtype=np.float64))
    return float(np.asarray(scored, dtype=np.float64).reshape(-1)[0])


# --- (a) the full registry chain: moved to section 6 by spec 94 ------------- #
#
# `test_in_the_full_registry_chain_engine_15_is_never_reached_this_phase` asserted that the
# registry chain stopped at `cost` on every bar tick because engine 9 did not exist, so
# `skeptic` never appeared in it. Deleted by spec 94 step 5: engine 9 has landed, the chain
# it described no longer exists, and section 6 asserts the opposite — engine 15 runs on the
# bar tick of the full registry chain. Recorded in `docs/build-log/phase-6/b-store.md`.


# --- (b1) no threshold, or no skeptic run ----------------------------------- #


@pytest.mark.parametrize(
    ("configured", "named_key"),
    [
        pytest.param(
            {"models.skeptic_run_id": True, "skeptic.veto_threshold": None},
            "skeptic.veto_threshold",
            id="no-threshold",
        ),
        pytest.param(
            {"skeptic.veto_threshold": 1.0, "models.skeptic_run_id": None},
            "models.skeptic_run_id",
            id="no-run-id",
        ),
        pytest.param(
            {"skeptic.veto_threshold": None, "models.skeptic_run_id": None},
            "skeptic.veto_threshold",
            id="neither",
        ),
    ],
)
def test_a_buy_call_with_the_skeptic_unconfigured_blocks_with_skeptic_unavailable(
    paper_config: MappingConfig,
    fixed_clock: Any,
    fake_clients_with_store: Any,
    constructed_rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
    configured: dict[str, Any],
    named_key: str,
) -> None:
    """Chain 5, 6, 7, 12, 13, 8, 15; engine 8 calls a BUY; a skeptic key is missing.

    **Each absence is spelled in the table, not inherited from the committed config.** It
    was inherited until 2026-09-15, when the operator ruled `skeptic.veto_threshold: 0.50`
    and that key stopped being absent — at which point every "unconfigured" case here would
    have quietly become a configured one, and the three parametrisations would have tested
    the same passing chain three times while reading as coverage of the refusal. A `None`
    override is the right spelling of absence and `_ABSENT_KEY` is not: the real `Config`
    answers an optional leaf the file omits with `None` and raises only on an *unknown* key,
    and a raise here would reach engine 15 as `ERROR` rather than as its own block.

    `True` in the table stands for the trained run id, and a threshold of 1.0 where one is
    supplied is the test's number. The block must name the key that is missing — with both
    missing the threshold is checked first, so that is the one named.
    """
    assert paper_config.get("skeptic.veto_threshold") is not None, (
        "the operator's veto threshold is absent from config/default.yaml. This test "
        "supplies every absence itself, so an absent key here means the ruled value has "
        "been lost rather than that this test is stale."
    )
    assert paper_config.get("models.skeptic_run_id") is None, (
        "models.skeptic_run_id is now committed. A fresh clone has no artefact under "
        "models/, so this key staying absent is what the engines fail closed on."
    )
    root, run_id = trained_skeptic
    overrides = {key: (run_id if value is True else value) for key, value in configured.items()}
    bars = window(constructed_rows, BUY_WINDOW_END)
    skeptic = RecordingSkeptic()

    bar_tick, quiet_tick = run_two_ticks(
        skeptic_config(paper_config, root, run_id, **overrides),
        at_bar_tick(fixed_clock, bars),
        fake_clients_with_store,
        bars,
        root,
        skeptic,
    )

    assert the_prediction(bar_tick)["is_buy"] is True, (
        "the fixture could not produce a BUY call, so the unavailable block is not reached"
    )
    assert bar_tick["trading_blocked_by"] == "skeptic", bar_tick.get("block_reason")
    published = bar_tick["skeptic"]
    assert published["reason_code"] == SKEPTIC_UNAVAILABLE, published
    assert published["vetoed"] is False, "an unavailable skeptic recorded a veto it never made"
    assert published["p_wrong"] is None
    assert named_key in str(bar_tick["block_reason"]), bar_tick["block_reason"]
    assert [result.status for result in skeptic.results] == [EngineStatus.BLOCK]
    assert_quiet_tick(quiet_tick, skeptic)


def test_a_call_that_is_not_a_buy_is_ok_with_the_skeptic_unconfigured(
    paper_config: MappingConfig,
    fixed_clock: Any,
    fake_clients_with_store: Any,
    constructed_rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
) -> None:
    """The same chain with neither skeptic key, on a window where engine 8 calls no BUY.

    `OK`, `vetoed: false`, the not-a-BUY sentence and **no blocker**: a `BLOCK` here would
    record a veto of a call nobody made, and turning a non-BUY into no trade is Phase 6's
    decision engine. It is `OK` *before* the missing threshold is looked at, which is why an
    unconfigured skeptic does not block this tick.
    """
    root, run_id = trained_skeptic
    bars = window(constructed_rows, NOT_A_BUY_WINDOW_END)
    skeptic = RecordingSkeptic()

    bar_tick, quiet_tick = run_two_ticks(
        skeptic_config(paper_config, root, run_id),
        at_bar_tick(fixed_clock, bars),
        fake_clients_with_store,
        bars,
        root,
        skeptic,
    )

    assert the_prediction(bar_tick)["is_buy"] is False, (
        "the fixture could not produce a non-BUY call, so the not-a-BUY path is not reached"
    )
    assert "trading_blocked_by" not in bar_tick, bar_tick.get("block_reason")
    published = bar_tick["skeptic"]
    assert published["pair"] == bar_tick["prediction"]["pair"]
    assert published["vetoed"] is False
    assert published["reason"] == NOT_A_BUY_CALL
    assert published["reason_code"] is None
    assert [result.status for result in skeptic.results] == [EngineStatus.OK]
    assert_quiet_tick(quiet_tick, skeptic)


# --- (b2) a trained skeptic, either side of its threshold -------------------- #


def judged_either_side(
    paper_config: MappingConfig,
    clock: Any,
    clients: Any,
    rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
    *,
    offset: float,
) -> tuple[dict[str, Any], dict[str, Any], float, float, RecordingSkeptic]:
    """Measure `p_wrong` on the BUY bar, then judge that bar at `p_wrong + offset`.

    The first orchestrator runs with no threshold, which blocks at engine 15 and leaves the
    tick's feature row and prediction in `state`; `p_wrong` is recomputed from those and the
    artefact. The second runs the same bar with the threshold set from it. **The threshold is
    the test's number**, a millionth either side of a measured value, clamped into (0, 1).
    """
    root, run_id = trained_skeptic
    bars = window(rows, BUY_WINDOW_END)
    measuring = RecordingSkeptic()
    measured_tick, _ = run_two_ticks(
        skeptic_config(paper_config, root, run_id, **{"models.skeptic_run_id": run_id}),
        at_bar_tick(clock, bars),
        clients,
        bars,
        root,
        measuring,
    )
    assert the_prediction(measured_tick)["is_buy"] is True, "the BUY window called no BUY"
    expected = recomputed_p_wrong(measured_tick, root, run_id)
    threshold = min(max(expected + offset, 1e-12), 1.0 - 1e-12)

    judging = RecordingSkeptic()
    bar_tick, quiet_tick = run_two_ticks(
        skeptic_config(
            paper_config,
            root,
            run_id,
            **{"models.skeptic_run_id": run_id, "skeptic.veto_threshold": threshold},
        ),
        at_bar_tick(clock, bars),
        clients,
        bars,
        root,
        judging,
        first_build=False,
    )
    assert bar_tick["prediction"] == measured_tick["prediction"], "the two runs saw different bars"
    return bar_tick, quiet_tick, expected, threshold, judging


def test_a_trained_skeptic_vetoes_a_buy_call_above_the_threshold(
    paper_config: MappingConfig,
    fixed_clock: Any,
    fake_clients_with_store: Any,
    constructed_rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
) -> None:
    """Threshold a millionth below the measured `p_wrong`: `skeptic_veto`, and it blocks.

    `p_wrong` and `threshold` are published with the veto, because a veto with no numbers is
    one nobody can check. `p_wrong` is compared against the recomputed value, so an engine
    reading the model's column as P(right) fails here even where it would still veto.
    """
    bar_tick, quiet_tick, expected, threshold, skeptic = judged_either_side(
        paper_config,
        fixed_clock,
        fake_clients_with_store,
        constructed_rows,
        trained_skeptic,
        offset=-1e-6,
    )

    assert bar_tick["trading_blocked_by"] == "skeptic", bar_tick.get("block_reason")
    published = bar_tick["skeptic"]
    assert published["reason_code"] == SKEPTIC_VETO, published
    assert published["vetoed"] is True
    assert published["model_run_id"] == trained_skeptic[1]
    assert published["p_wrong"] == pytest.approx(expected, abs=1e-12)
    assert published["threshold"] == threshold
    assert published["p_wrong"] > published["threshold"]
    assert [result.status for result in skeptic.results] == [EngineStatus.BLOCK]
    assert_quiet_tick(quiet_tick, skeptic)


def test_a_trained_skeptic_passes_the_same_call_below_the_threshold(
    paper_config: MappingConfig,
    fixed_clock: Any,
    fake_clients_with_store: Any,
    constructed_rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
) -> None:
    """Threshold a millionth above the same `p_wrong`: `OK`, not vetoed, and no blocker.

    The pass half, two millionths of threshold apart from the veto above. Without it the
    veto test is satisfied by a gate that vetoes every BUY.
    """
    bar_tick, quiet_tick, expected, threshold, skeptic = judged_either_side(
        paper_config,
        fixed_clock,
        fake_clients_with_store,
        constructed_rows,
        trained_skeptic,
        offset=1e-6,
    )

    assert "trading_blocked_by" not in bar_tick, bar_tick.get("block_reason")
    published = bar_tick["skeptic"]
    assert published["reason_code"] is None, published
    assert published["vetoed"] is False
    assert published["model_run_id"] == trained_skeptic[1]
    assert published["p_wrong"] == pytest.approx(expected, abs=1e-12)
    assert published["threshold"] == threshold
    assert published["p_wrong"] <= published["threshold"]
    assert [result.status for result in skeptic.results] == [EngineStatus.OK]
    assert_quiet_tick(quiet_tick, skeptic)


# --- (b4) the declaration ---------------------------------------------------- #


def test_engine_15_declares_itself_as_the_registry_has_it() -> None:
    """The registry table in `engine-contracts.md`: engine 15 `skeptic`, a gate."""
    engine = SkepticEngine()

    assert (engine.name, engine.number, engine.is_gate) == ("skeptic", 15, True)


# --------------------------------------------------------------------------- #
# 6. The full registry chain, 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15. Spec 94.
#
# Engines 9 `order_book` and 14 `adaptive_router` are C's; this section rehearses the
# orchestrator carrying them, not their arithmetic. Every engine is the real one in its
# registry position, the artefacts are trained in this module, and the store is B's real
# client. Two things are scripted and both are named: the fee tier, and the book.
#
# **The book is the recorded one, because the fake's default cannot witness the seam.** Its
# top BTC/USD bid level holds 37,500 USD against a 5,000 USD basis, so engine 9's walk
# consumes one level and publishes an estimate of exactly zero — measured by B. A friction
# recomputed with a zero slippage term equals one recomputed with no slippage term, so an
# engine 10 that ignored engine 9 would pass the recomputation. The operator: "Spec 94 uses
# the thin book. Engine 9's estimate on the fake's default book is exactly zero, and a zero
# proves nothing."
# --------------------------------------------------------------------------- #

#: The fee tier this section runs at, by name. Ruling 8 of the Phase 6 task list: at tier 1
#: the cost gate is unreachable by construction, so a chain meant to reach engine 15 has to
#: say which tier let it through.
REGISTRY_FEE_TIER = TIER_3

#: The pair engine 7 selects on the BUY window — asserted on every run, never trusted.
REGISTRY_PAIR = "BTC/USD"

#: The engines of the opportunity chain, by `state` key, in registry order.
REGISTRY_KEYS = (
    "feature",
    "macro_context",
    "scout",
    "regime",
    "anomaly",
    "prediction",
    "order_book",
    "cost",
    "risk",
    "adaptive_router",
    "skeptic",
)

BOOK_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "book_sample.jsonl"
LEADERBOARD_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "leaderboard_sample.json"

#: Engine 14's weights are statistics, so a float tolerance is right for them. Money in this
#: section is compared exactly.
WEIGHT_TOLERANCE = 1e-12


def registry_chain(skeptic: RecordingSkeptic) -> list[Any]:
    """The opportunity chain in the order `engine-contracts.md` fixes, engine 15 recorded."""
    return [
        FeatureEngine(),
        MacroContextEngine(),
        ScoutEngine(),
        RegimeEngine(),
        AnomalyEngine(),
        PredictionEngine(),
        OrderBookEngine(),
        CostEngine(),
        RiskEngine(),
        AdaptiveRouterEngine(),
        skeptic,
    ]


def recorded_opening_book(pair: str) -> Book:
    """The first frame the committed book fixture holds for `pair`, which is a snapshot.

    **The opening snapshot only, and no deltas**, so nothing here reconstructs a book: a
    Kraken v2 `snapshot` frame is an absolute ten-level book on its own, and the delta
    replay is C's, in `test_order_book.py`. Numbers are parsed as `Decimal` from the JSON
    text, so the recorded digits reach the fake unchanged — a float round trip is how a
    price stops being the one that was recorded.
    """
    with BOOK_FIXTURE.open("rb") as handle:
        header = json.loads(handle.readline())
        assert header["_fixture"] == "book_frames", header
        for raw in handle:
            frame = json.loads(raw, parse_float=Decimal)
            if frame.get("pair") != pair:
                continue
            payload = frame["payload"]
            assert payload["type"] == "snapshot", f"the first {pair} frame is not a snapshot"
            data = payload["data"][0]
            return (
                tuple((format(lv["price"], "f"), format(lv["qty"], "f")) for lv in data["bids"]),
                tuple((format(lv["price"], "f"), format(lv["qty"], "f")) for lv in data["asks"]),
            )
    raise AssertionError(f"{BOOK_FIXTURE.name} holds no frame for {pair}")


def hand_walked_slippage(
    bids: tuple[tuple[str, str], ...], notional: Decimal
) -> tuple[Decimal, int]:
    """`(slippage, levels touched)` for a taker sell of `notional`, from the definition.

    Written from engine 9's README rather than by calling `walk_the_bid_side`, so it is a
    second implementation: sell whole levels from the best bid down until the remainder
    fits, then `(best_bid - volume-weighted price) / best_bid`. The same operations in the
    same order, so the 28-digit context rounds both alike and the comparison can be exact.
    """
    remaining = notional
    base = Decimal(0)
    touched = 0
    for price_text, qty_text in bids:
        price, qty = Decimal(price_text), Decimal(qty_text)
        touched += 1
        if price * qty >= remaining:
            base += remaining / price
            remaining = Decimal(0)
            break
        base += qty
        remaining -= price * qty
    assert remaining == 0, "the recorded book cannot absorb the basis; this fixture is void"
    best = Decimal(bids[0][0])
    return (best - notional / base) / best, touched


def leaderboard_rows() -> list[LeaderboardRow]:
    """The committed fixture's rows as real `LeaderboardRow`s, `why` dropped."""
    payload = json.loads(LEADERBOARD_FIXTURE.read_bytes().decode("utf-8"))
    rows: list[LeaderboardRow] = []
    for row in payload["rows"]:
        fields = {key: value for key, value in row.items() if key != "why"}
        fields["net_pnl"] = Decimal(fields["net_pnl"])
        rows.append(LeaderboardRow(**fields))
    return rows


def expected_weights(rows: list[LeaderboardRow]) -> dict[str, float]:
    """The weights, recomputed here from the rule engine 14's README states.

    Latest row per `(version, fold)` within the engine's own family; per-fold skill
    `max(0, 1 - brier / base_rate_brier)`; unweighted mean per version; normalised.
    """
    latest: dict[tuple[str, str | None], LeaderboardRow] = {}
    for row in rows:
        if row.model_id != ROUTER_MODEL_ID:
            continue
        key = (row.model_version, row.fold)
        if key not in latest or row.updated_at >= latest[key].updated_at:
            latest[key] = row
    per_version: dict[str, list[float]] = {}
    for (version, _fold), row in latest.items():
        assert row.brier is not None and row.base_rate_brier is not None
        per_version.setdefault(version, []).append(
            max(0.0, 1.0 - row.brier / row.base_rate_brier)
        )
    skills = {version: sum(folds) / len(folds) for version, folds in per_version.items()}
    total = sum(skills.values())
    assert total > 0, "the fixture no longer gives any version a weight; the witness is void"
    return {version: skill / total for version, skill in skills.items()}


@pytest.fixture
def fresh_store(tmp_path: Path) -> Iterator[Callable[[Path], Any]]:
    """A factory for B's real store over a newly migrated database, one per run.

    One database per run rather than one per test, because the invariant 4 test compares a
    run with the leaderboard loaded against one without it, and a row once written cannot
    be taken back out through the store's surface.
    """
    from acsoe.clients.store.client import StoreClient
    from acsoe.clients.store.migrations import apply_migrations

    opened: list[Any] = []

    def make(models_root: Path) -> Any:
        db_path = tmp_path / f"registry-{len(opened)}.sqlite"
        apply_migrations(db_path)
        store = StoreClient(db_path, models_dir=models_root)
        opened.append(store)
        return store

    yield make
    for store in opened:
        store.close()


@dataclasses.dataclass(frozen=True)
class RegistryRun:
    bar_tick: dict[str, Any]
    quiet_tick: dict[str, Any]
    skeptic: RecordingSkeptic
    bids: tuple[tuple[str, str], ...]


def run_full_registry(
    paper_config: MappingConfig,
    clock: Any,
    clients: Any,
    rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
    make_store: Callable[[Path], Any],
    *,
    threshold: float | None,
    leaderboard: bool,
) -> RegistryRun:
    """The full registry chain on the BUY window: a bar tick, then a tick sixty seconds on.

    The recorded BTC/USD book, fee tier 3, a trained skeptic, and `threshold` as the veto
    line (the test's number). `leaderboard` loads the committed leaderboard fixture into the
    run's own store before the first tick.
    """
    root, run_id = trained_skeptic
    bars = window(rows, BUY_WINDOW_END)
    config = skeptic_config(
        paper_config,
        root,
        run_id,
        **{"models.skeptic_run_id": run_id, "skeptic.veto_threshold": threshold},
    )
    store = make_store(root)
    object.__setattr__(clients, "store", store)
    write_equity(store)
    activate(store)
    if leaderboard:
        for row in leaderboard_rows():
            store.write_leaderboard_entry(row)
    book = recorded_opening_book(REGISTRY_PAIR)
    skeptic = RecordingSkeptic()
    orchestrator = build(
        config,
        at_bar_tick(clock, bars),
        clients,
        bars,
        opportunity=registry_chain(skeptic),
        stream_pairs=(PAIR, *MACRO_PAIRS),
        quotes=True,
        books={REGISTRY_PAIR: book},
        fee_tier=REGISTRY_FEE_TIER,
    )
    bar_tick = orchestrator.tick()
    clock.advance(TICK)
    quiet_tick = orchestrator.tick()
    assert the_prediction(bar_tick)["is_buy"] is True, "the BUY window no longer calls a BUY"
    assert bar_tick["scout"]["pair"] == REGISTRY_PAIR, (
        f"engine 7 chose {bar_tick['scout'].get('pair')}; the recorded book is "
        f"{REGISTRY_PAIR}'s, so every slippage assertion would be about the wrong pair"
    )
    return RegistryRun(bar_tick, quiet_tick, skeptic, book[0])


def test_the_full_registry_chain_reaches_engine_15_on_the_bar_tick_and_not_the_quiet_one(
    paper_config: MappingConfig,
    fixed_clock: Any,
    fake_clients_with_store: Any,
    constructed_rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
    fresh_store: Callable[[Path], Any],
) -> None:
    """Every engine of the registry chain ran on the bar tick; none after 5 on the quiet one.

    **Replaces the Phase 5 assertion that `skeptic` never appears in this chain.** At fee
    tier 3 — named, because at tier 1 engine 10 stops every candidate — with the recorded
    book and a threshold of 1.0 nothing blocks, so engine 15 is reached and answers `OK`.
    Its status is read from what it returned: `state` holds a payload, and contract rule 7
    lets an `ERROR` leave any payload behind.
    """
    run = run_full_registry(
        paper_config,
        fixed_clock,
        fake_clients_with_store,
        constructed_rows,
        trained_skeptic,
        fresh_store,
        threshold=1.0,
        leaderboard=True,
    )
    bar, quiet = run.bar_tick, run.quiet_tick

    profile = fee_tier_profile(REGISTRY_FEE_TIER)
    fees = bar["exchange"]["fee_tier"]
    assert fees["tier"] == profile.tier == 3
    assert Decimal(fees["maker_fee_pct"]) == Decimal(profile.maker_fee_pct)
    assert Decimal(fees["taker_fee_pct"]) == Decimal(profile.taker_fee_pct)

    assert "trading_blocked_by" not in bar, (bar.get("trading_blocked_by"), bar.get("block_reason"))
    for engine in REGISTRY_KEYS:
        assert engine in bar, f"{engine} did not run on the bar tick"
    assert bar["cost"]["clears_hurdle"] is True
    assert bar["risk"]["approved"] is True
    assert [result.status for result in run.skeptic.results] == [EngineStatus.OK]
    assert bar["skeptic"]["pair"] == REGISTRY_PAIR
    assert bar["skeptic"]["vetoed"] is False
    assert bar["skeptic"]["reason_code"] is None

    assert quiet["market_sensor"]["bar_closed"] is False
    assert quiet["feature"] == {}
    assert "trading_blocked_by" not in quiet, "engine 5 did not pass on the quiet tick, it failed"
    for engine in REGISTRY_KEYS[1:]:
        assert engine not in quiet, f"{engine} ran on a tick where no bar closed"
    assert len(run.skeptic.results) == 1, "engine 15 was called on the quiet tick"


def test_engine_10_prices_the_nonzero_slippage_engine_9_walked_on_the_recorded_book(
    paper_config: MappingConfig,
    fixed_clock: Any,
    fake_clients_with_store: Any,
    constructed_rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
    fresh_store: Callable[[Path], Any],
) -> None:
    """**The 9-to-10 seam, proven by recomputation on a book that can tell.**

    First, engine 9's estimate is **strictly positive** — asserted before anything else,
    because a zero makes every later line unable to fail. Then it is the walk of the book
    this test loaded, recomputed here. Then friction is rebuilt from its published parts —
    tier 3's two fees from the named profile, engine 3's spread, engine 9's slippage, in
    invariant 5's order — and compared with engine 10's figure; engine 10's total is never
    read back against itself. Last, the same rebuild **without** the slippage term must
    differ, which is the assertion that this witness discriminates at all.
    """
    run = run_full_registry(
        paper_config,
        fixed_clock,
        fake_clients_with_store,
        constructed_rows,
        trained_skeptic,
        fresh_store,
        threshold=1.0,
        leaderboard=True,
    )
    bar = run.bar_tick
    order_book = bar["order_book"]
    assert order_book["reason_code"] is None, order_book
    assert "estimated_slippage_pct" in order_book, order_book

    slippage = Decimal(order_book["estimated_slippage_pct"])
    assert slippage > 0, f"engine 9 estimated {slippage}: the book is not thin enough to witness"
    assert order_book["levels_consumed"] > 1

    basis = Decimal(order_book["basis_notional"])
    assert basis == Decimal(bar["exchange"]["balances"]["USD"])
    walked, touched = hand_walked_slippage(run.bids, basis)
    assert slippage == walked
    assert order_book["levels_consumed"] == touched

    profile = fee_tier_profile(REGISTRY_FEE_TIER)
    maker, taker = Decimal(profile.maker_fee_pct), Decimal(profile.taker_fee_pct)
    spread = Decimal(bar["market_sensor"]["quotes"][REGISTRY_PAIR]["spread_pct"])
    friction = Decimal(bar["cost"]["friction_pct"])

    assert friction == maker + taker + spread + slippage
    assert friction != maker + taker + spread, (
        "friction is the same with and without the slippage term; this book cannot witness it"
    )

    expected_move = Decimal(bar["prediction"]["expected_move_pct"])
    hurdle_multiple = Decimal(repr(paper_config.get("trading.hurdle_multiple")))
    assert Decimal(bar["cost"]["net_edge_pct"]) == expected_move - friction
    assert Decimal(bar["cost"]["hurdle_pct"]) == hurdle_multiple * friction


def test_engine_14_weights_the_leaderboard_in_the_real_store_on_the_bar_tick(
    paper_config: MappingConfig,
    fixed_clock: Any,
    fake_clients_with_store: Any,
    constructed_rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
    fresh_store: Callable[[Path], Any],
) -> None:
    """Engine 14 read the committed leaderboard fixture out of B's store, in the chain.

    The weights are recomputed from the fixture rows and compared, and the fixture's other
    model family must not appear: a weight for it would be a predictor's weight handed to
    something else. Provenance is checked against its sources in this tick's `state`.
    """
    run = run_full_registry(
        paper_config,
        fixed_clock,
        fake_clients_with_store,
        constructed_rows,
        trained_skeptic,
        fresh_store,
        threshold=1.0,
        leaderboard=True,
    )
    bar = run.bar_tick
    router = bar["adaptive_router"]
    assert router["reason_code"] is None, router

    expected = expected_weights(leaderboard_rows())
    assert set(router["weights"]) == set(expected)
    for version, weight in expected.items():
        assert abs(router["weights"][version] - weight) <= WEIGHT_TOLERANCE, (version, router)
    assert router["active_model_run_id"] == bar["prediction"]["model_run_id"]
    assert router["regime"] == bar["regime"]["label"]
    assert "adaptive_router" not in run.quiet_tick


@pytest.mark.parametrize("side", ["pass", "veto"])
def test_nothing_engine_14_publishes_changes_whether_engine_15_blocks(
    paper_config: MappingConfig,
    fixed_clock: Any,
    fake_clients_with_store: Any,
    constructed_rows: list[dict[str, Any]],
    trained_skeptic: tuple[Path, str],
    fresh_store: Callable[[Path], Any],
    side: str,
) -> None:
    """Invariant 4: no router decision may skip, soften or override a gate.

    One bar is judged twice at one threshold — once with the leaderboard fixture in the
    store, so engine 14 publishes weights, and once with an empty store, so it publishes
    none. Engine 14's payload must differ between the two, or the comparison proves
    nothing; engine 15's answer must be **the one its threshold dictates** in both runs, and
    identical across them.

    The threshold is the test's number: `p_wrong` recomputed from the artefact and this bar,
    then a millionth above it (`pass`) or below it (`veto`). The expected answer is asserted
    and not only the equality: a router output engine 15 read on both runs would move both
    answers the same way, and equality alone would call that sound.
    """
    root, run_id = trained_skeptic
    measured = run_full_registry(
        paper_config,
        fixed_clock,
        fake_clients_with_store,
        constructed_rows,
        trained_skeptic,
        fresh_store,
        threshold=None,
        leaderboard=False,
    )
    p_wrong = recomputed_p_wrong(measured.bar_tick, root, run_id)
    offset = 1e-6 if side == "pass" else -1e-6
    threshold = min(max(p_wrong + offset, 1e-12), 1.0 - 1e-12)

    runs = {
        loaded: run_full_registry(
            paper_config,
            fixed_clock,
            fake_clients_with_store,
            constructed_rows,
            trained_skeptic,
            fresh_store,
            threshold=threshold,
            leaderboard=loaded,
        )
        for loaded in (False, True)
    }
    without, with_weights = runs[False].bar_tick, runs[True].bar_tick
    assert without["prediction"] == with_weights["prediction"], "the two runs saw different bars"

    assert without["adaptive_router"]["reason_code"] == REASON_LEADERBOARD_EMPTY
    assert not any((without["adaptive_router"].get("weights") or {}).values())
    assert with_weights["adaptive_router"]["reason_code"] is None
    weights = with_weights["adaptive_router"]["weights"]
    assert abs(sum(weights.values()) - 1.0) <= WEIGHT_TOLERANCE, weights

    expected_status = EngineStatus.OK if side == "pass" else EngineStatus.BLOCK
    for loaded, run in runs.items():
        where = "with weights" if loaded else "without weights"
        assert [result.status for result in run.skeptic.results] == [expected_status], where
        published = run.bar_tick["skeptic"]
        assert published["threshold"] == threshold, where
        assert published["p_wrong"] == pytest.approx(p_wrong, abs=1e-12), where
        if side == "veto":
            assert run.bar_tick["trading_blocked_by"] == "skeptic", where
            assert published["reason_code"] == SKEPTIC_VETO, where
        else:
            assert "trading_blocked_by" not in run.bar_tick, (where, run.bar_tick.get("block_reason"))
            assert published["reason_code"] is None, where
    assert with_weights["skeptic"] == without["skeptic"]
    assert with_weights.get("block_reason") == without.get("block_reason")
