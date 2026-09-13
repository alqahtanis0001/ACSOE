"""Spec 28 — engine 3 `market_sensor`.

Three properties.

**`bar_closed` is true exactly once per decision bar**, asserted with the injected
clock rather than by waiting. Engine 5 `feature` returns `PASS` when it is false, so
this one boolean is what stops the opportunity chain on fourteen ticks in fifteen.

**A missing candle is reported, never invented.** A bar in which nothing traded gets no
candle and its timestamp appears in `missing_bars`. There is no flag that fills one, and
this file asserts the *absence* as well as the report — a series that was silently
forward-filled would pass any check that only counted gaps.

**A partial bar is never published as a candle.** The bar containing `now` is still
open; publishing its high, low and close would be look-ahead by another name.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.kraken.contracts import QuoteTick, TradeTick
from acsoe.core.contracts import EngineStatus
from acsoe.engines.market_sensor.candles import (
    Candle,
    bar_open_seconds,
    build_candles,
    missing_bar_timestamps,
)
from acsoe.engines.market_sensor.contracts import STATE_KEY, spread_ratio
from acsoe.engines.market_sensor.engine import MarketSensorEngine, bar_closed_on

BAR = 900
TICK = 60
ORIGIN = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "kraken" / "ohlc.json"


def trade(pair: str, offset_s: int, price: str, qty: str) -> TradeTick:
    return TradeTick(
        pair=pair,
        ts=ORIGIN + timedelta(seconds=offset_s),
        price=Decimal(price),
        qty=Decimal(qty),
    )


class FakeStream:
    """A market stream double: a rolling trade window and a top-of-book quote."""

    def __init__(self, trades: list[TradeTick] | None = None) -> None:
        self._trades = list(trades or [])
        self.quotes: dict[str, QuoteTick] = {}

    def recent_trades(self) -> tuple[TradeTick, ...]:
        return tuple(self._trades)

    def latest_quote(self, pair: str) -> QuoteTick | None:
        return self.quotes.get(pair)


@pytest.fixture
def engine() -> MarketSensorEngine:
    return MarketSensorEngine()


def context_at(engine_context: Any, moment: datetime, stream: Any = None) -> Any:
    """A context standing at `moment`, with `stream` as the Kraken client."""
    import dataclasses

    if stream is not None:
        object.__setattr__(engine_context.clients, "kraken", stream)
    return dataclasses.replace(engine_context, now=moment)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table(engine: MarketSensorEngine) -> None:
    assert engine.name == "market_sensor"
    assert engine.number == 3
    assert engine.is_gate is False
    assert engine.name == STATE_KEY


# --------------------------------------------------------------------------- #
# bar_closed
# --------------------------------------------------------------------------- #


def test_bar_closed_is_true_on_exactly_one_tick_in_fifteen() -> None:
    """Asserted with the injected clock, never by waiting."""
    base = int(ORIGIN.timestamp())
    flags = [
        bar_closed_on(base + index * TICK, interval_s=BAR, tick_s=TICK) for index in range(15)
    ]
    assert flags.count(True) == 1
    assert flags[0] is True  # the tick that landed on the boundary


def test_bar_closed_is_not_an_exact_boundary_test() -> None:
    """`context.now` comes from a real clock and carries microseconds, so
    `now % interval == 0` would essentially never fire."""
    base = int(ORIGIN.timestamp())
    assert bar_closed_on(base + 3, interval_s=BAR, tick_s=TICK) is True
    assert bar_closed_on(base + 61, interval_s=BAR, tick_s=TICK) is False


def test_a_skipped_tick_still_fires_the_bar_exactly_once() -> None:
    """The loop running late must not lose a decision bar, and must not fire twice."""
    base = int(ORIGIN.timestamp()) + BAR
    assert bar_closed_on(base + 30, interval_s=BAR, tick_s=180) is True
    assert bar_closed_on(base + 240, interval_s=BAR, tick_s=180) is False


def test_the_engine_reports_the_bar_that_closed(
    engine: MarketSensorEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    stream = FakeStream()
    at_boundary = ORIGIN + timedelta(seconds=BAR)
    data = engine.process(context_at(engine_context, at_boundary, stream), fresh_state).data
    assert data["bar_closed"] is True
    assert data["closed_bar_ts"] == int(ORIGIN.timestamp())

    mid_bar = ORIGIN + timedelta(seconds=BAR + TICK)
    data = engine.process(context_at(engine_context, mid_bar, stream), fresh_state).data
    assert data["bar_closed"] is False
    assert data["closed_bar_ts"] is None


# --------------------------------------------------------------------------- #
# Candles
# --------------------------------------------------------------------------- #


def test_a_candle_is_built_from_the_trades_in_its_bar() -> None:
    candles = build_candles(
        [
            trade("BTC/USD", 10, "100.5", "1"),
            trade("BTC/USD", 20, "101.5", "2"),
            trade("BTC/USD", 30, "99.5", "3"),
            trade("BTC/USD", 40, "100.0", "4"),
        ],
        interval_s=BAR,
    )
    assert len(candles) == 1
    candle = candles[0]
    assert (candle.open, candle.high, candle.low, candle.close) == (
        Decimal("100.5"),
        Decimal("101.5"),
        Decimal("99.5"),
        Decimal("100.0"),
    )
    assert candle.volume == Decimal("10")
    assert candle.trades == 4


def test_money_never_becomes_a_float_on_the_way_through_polars() -> None:
    candle = build_candles([trade("BTC/USD", 1, "0.1", "0.2")], interval_s=BAR)[0]
    assert isinstance(candle.open, Decimal)
    assert isinstance(candle.volume, Decimal)
    assert candle.volume == Decimal("0.2")
    assert candle.state_dict()["volume"] == "0.2"
    for value in candle.state_dict().values():
        assert not isinstance(value, float)


def test_a_float_price_is_refused_rather_than_rounded_into_place() -> None:
    with pytest.raises(ValueError, match="float"):
        build_candles([{"pair": "BTC/USD", "ts": 0, "price": 100.5, "qty": 1}], interval_s=BAR)


def test_a_bar_with_no_trades_produces_no_candle_and_is_reported_missing() -> None:
    """The single most important assertion in this file. A gap is a fact about the
    market — a quiet period — and filling it invents a barrier touch that never
    happened."""
    candles = build_candles(
        [
            trade("BTC/USD", 10, "100", "1"),
            # nothing at all in the second bar
            trade("BTC/USD", 2 * BAR + 10, "110", "1"),
        ],
        interval_s=BAR,
    )
    assert [c.ts for c in candles] == [
        int(ORIGIN.timestamp()),
        int(ORIGIN.timestamp()) + 2 * BAR,
    ]
    assert missing_bar_timestamps(candles, interval_s=BAR) == [int(ORIGIN.timestamp()) + BAR]


def test_no_candle_carries_a_timestamp_that_had_no_trade() -> None:
    """Separate from the gap count on purpose. Counting gaps correctly while also
    emitting filled rows would pass the check above and still be wrong."""
    trades = [
        trade("BTC/USD", 10, "100", "1"),
        trade("BTC/USD", 3 * BAR + 10, "110", "1"),
    ]
    candles = build_candles(trades, interval_s=BAR)
    traded_bars = {bar_open_seconds(int(t.ts.timestamp()), interval_s=BAR) for t in trades}
    assert {c.ts for c in candles} == traded_bars
    assert len(candles) == 2  # not 4


def test_missing_bars_are_bounded_by_the_data_rather_than_extrapolated() -> None:
    candles = [
        Candle(
            pair="BTC/USD", ts=0, open="1", high="1", low="1", close="1", volume="1", trades=1
        ),
        Candle(
            pair="BTC/USD",
            ts=BAR,
            open="1",
            high="1",
            low="1",
            close="1",
            volume="1",
            trades=1,
        ),
    ]
    assert missing_bar_timestamps(candles, interval_s=BAR) == []


def test_the_in_progress_bar_is_never_published_as_a_candle(
    engine: MarketSensorEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    """Look-ahead by another name: a partial high, low and close in front of the
    feature engine."""
    stream = FakeStream(
        [
            trade("BTC/USD", 10, "100", "1"),
            trade("BTC/USD", BAR + 10, "200", "1"),  # the bar `now` sits in
        ]
    )
    now = ORIGIN + timedelta(seconds=BAR + 300)
    data = engine.process(context_at(engine_context, now, stream), fresh_state).data
    assert [candle["ts"] for candle in data["candles"]] == [int(ORIGIN.timestamp())]


def test_published_candles_are_bounded_per_pair(
    engine: MarketSensorEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    """Bounded per pair rather than overall, so a busy pair cannot push a quiet one
    out of `state` entirely and leave a consumer looking at nothing."""
    import dataclasses

    from tests.harness.doubles import MappingConfig

    stream = FakeStream(
        [trade("BTC/USD", index * BAR + 10, "100", "1") for index in range(6)]
        + [trade("ETH/USD", index * BAR + 20, "10", "1") for index in range(6)]
    )
    context = context_at(engine_context, ORIGIN + timedelta(seconds=6 * BAR), stream)
    overridden = context.config.as_dict()
    overridden["market_sensor"] = {"published_bars": 2}
    context = dataclasses.replace(context, config=MappingConfig(overridden))
    data = engine.process(context, fresh_state).data
    per_pair: dict[str, int] = {}
    for candle in data["candles"]:
        per_pair[candle["pair"]] = per_pair.get(candle["pair"], 0) + 1
    assert per_pair == {"BTC/USD": 2, "ETH/USD": 2}


# --------------------------------------------------------------------------- #
# The committed fixture, three pairs
# --------------------------------------------------------------------------- #


def test_built_candles_match_the_committed_fixture_for_three_pairs() -> None:
    """The same comparison `candles_match_kraken_ohlc` makes, run here too so a
    regression fails in the suite before it fails a phase gate."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    interval = int(fixture["interval_s"])
    assert len(fixture["pairs"]) >= 3

    for pair, block in fixture["pairs"].items():
        built = build_candles(block["trades"], interval_s=interval)
        expected = block["ohlc"]
        assert [candle.ts for candle in built] == [int(bar["ts"]) for bar in expected], pair
        for candle, bar in zip(built, expected, strict=True):
            for field in ("open", "high", "low", "close", "volume"):
                assert getattr(candle, field) == Decimal(str(bar[field])), (pair, field)


def test_the_fixture_carries_real_trades_and_says_what_its_ohlc_half_is() -> None:
    """The provenance line is load-bearing: the trades are real Kraken frames, the
    expected OHLC is a reference computation and not Kraken's own published bars."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert "reference computation" in fixture["provenance"]
    assert "--live" in fixture["provenance"]


# --------------------------------------------------------------------------- #
# Quotes
# --------------------------------------------------------------------------- #


def test_the_spread_is_published_as_a_ratio_of_mid() -> None:
    assert spread_ratio(Decimal("100"), Decimal("102")) == Decimal("2") / Decimal("101")


def test_a_crossed_book_is_reported_rather_than_clamped(
    engine: MarketSensorEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    """Engine 4 blocks on a negative spread, so engine 3 must not tidy one away."""
    stream = FakeStream([trade("BTC/USD", 10, "100", "1")])
    stream.quotes["BTC/USD"] = QuoteTick(
        pair="BTC/USD", ts=ORIGIN + timedelta(seconds=20), bid="101", ask="100"
    )
    now = ORIGIN + timedelta(seconds=BAR + 60)
    data = engine.process(context_at(engine_context, now, stream), fresh_state).data
    quote = data["quotes"]["BTC/USD"]
    assert Decimal(quote["spread_pct"]) < 0
    assert quote["age_s"] > 0


def test_a_pair_with_no_quote_is_absent_rather_than_zero(
    engine: MarketSensorEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    """A zero spread is the one shape the cost gate must never be handed."""
    stream = FakeStream([trade("BTC/USD", 10, "100", "1")])
    now = ORIGIN + timedelta(seconds=BAR + 60)
    data = engine.process(context_at(engine_context, now, stream), fresh_state).data
    assert data["quotes"] == {}


# --------------------------------------------------------------------------- #
# Degraded clients
# --------------------------------------------------------------------------- #


def test_a_client_with_no_stream_still_runs_the_bar_clock(
    engine: MarketSensorEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    """The bar clock is arithmetic over `context.now` and owes nothing to the feed.
    C's fake Kraken client has no stream, and the orchestrator must still tick."""
    at_boundary = ORIGIN + timedelta(seconds=BAR)
    result = engine.process(context_at(engine_context, at_boundary), fresh_state)
    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["stream_available"] is False
    assert result.data["bar_closed"] is True
    assert result.data["candles"] == []


def test_it_never_blocks_trading(
    engine: MarketSensorEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    stream = FakeStream()
    result = engine.process(context_at(engine_context, ORIGIN, stream), fresh_state)
    assert result.blocks_trading is False
    assert result.reason is None


# --------------------------------------------------------------------------- #
# The engine 3 to engine 4 seam, with no double on either engine
# --------------------------------------------------------------------------- #
#
# Ruling of 2026-09-13. `missing_bars` is pooled across pairs, so it lists a bar only
# when *no subscribed pair traded at all*. C-2 raised that no consumer can tell which
# pair has the hole; measuring it showed something sharper, which is that past a couple
# of pairs the field is empty, and `data_guard`'s missing-candle block therefore fires
# on feed-level silence rather than on one pair being quiet. The union stays — a
# per-pair reading would block every tick a thin pair skipped a bar, which is most ticks.
#
# Neither engine is doubled here. Engine 3's own gap tests all use a single pair, where
# the union and a per-pair reading are identical by construction, and `data_guard`'s
# tests build `missing_bars` themselves as a tuple — so each side is correct about
# itself and the pair of them proves nothing about the seam. Only the stream is fake,
# because a market feed is the input.


def two_pair_stream(quiet_bars: set[int], *, bars: int = 6) -> FakeStream:
    """AAA trades in every bar; BBB skips `quiet_bars`. Fresh quotes for both.

    The quotes are here so that the only thing varying between the two tests below is
    which bars traded: without them `data_guard` blocks on "no market data" and the
    missing-candle assertion would be reading a block it did not cause.
    """
    trades: list[TradeTick] = []
    for index in range(bars):
        offset = index * BAR + 10
        trades.append(trade("AAA/USD", offset, f"{100 + index}", "1"))
        if index not in quiet_bars:
            trades.append(trade("BBB/USD", offset, f"{200 + index}", "1"))
    stream = FakeStream(trades)
    for pair in ("AAA/USD", "BBB/USD"):
        stream.quotes[pair] = QuoteTick(
            pair=pair,
            ts=ORIGIN + timedelta(seconds=bars * BAR),
            bid="100",
            ask="101",
        )
    return stream


def guard_on(engine_context: Any, stream: FakeStream, moment: datetime) -> Any:
    """Run engine 3 for real, then engine 4 for real over what engine 3 published."""
    from acsoe.engines.data_guard.engine import DataGuardEngine

    state: dict[str, Any] = {}
    sensor = MarketSensorEngine().process(context_at(engine_context, moment, stream), state)
    state["market_sensor"] = sensor.data
    return sensor, DataGuardEngine().process(context_at(engine_context, moment, stream), state)


def test_one_pair_s_hole_is_not_a_missing_candle_and_does_not_block(
    engine_context: Any,
) -> None:
    """BBB is silent for two bars AAA traded in. That is ordinary market behaviour.

    A per-pair reading would block here, every time, on any thin pair — and with 234
    pairs in the archive that is most ticks. The feature layer marks per-pair holes;
    this gate does not.
    """
    moment = ORIGIN + timedelta(seconds=6 * BAR + 60)
    sensor, guard = guard_on(engine_context, two_pair_stream({2, 3}), moment)

    published = {candle["pair"] for candle in sensor.data["candles"]}
    assert published == {"AAA/USD", "BBB/USD"}, "both pairs were published"
    assert sensor.data["missing_bars"] == [], "a per-pair hole is not a missing bar"
    assert guard.status is not EngineStatus.BLOCK
    assert guard.data["reason_code"] is None


def test_a_bar_in_which_every_pair_was_silent_blocks_as_a_missing_candle(
    engine_context: Any,
) -> None:
    """The other side, and the one the gate exists for: the feed went quiet.

    Both pairs skip bar 3 and both trade either side of it, so the hole is inside the
    covered range and is a fact about the feed rather than about a pair.
    """
    from acsoe.engines.data_guard.contracts import REASON_MISSING_CANDLE

    moment = ORIGIN + timedelta(seconds=6 * BAR + 60)
    stream = two_pair_stream(set())
    silent_bar = int(ORIGIN.timestamp()) + 3 * BAR
    # Reaching into the double's own field, which is fixture set-up rather than a
    # private access worth suppressing a rule for: `SLF001` is not in this project's
    # selected rules, so a `noqa` naming it would be a directive for a linter that is
    # not running — the exact defect the RUF100 check catches.
    stream._trades = [
        tick
        for tick in stream.recent_trades()
        if bar_open_seconds(int(tick.ts.timestamp()), interval_s=BAR) != silent_bar
    ]
    sensor, guard = guard_on(engine_context, stream, moment)

    assert sensor.data["missing_bars"] == [silent_bar]
    assert guard.status is EngineStatus.BLOCK
    assert guard.data["reason_code"] == REASON_MISSING_CANDLE
    assert guard.blocks_trading is True
