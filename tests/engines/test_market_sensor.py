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
from pydantic import ValidationError

from acsoe.clients.kraken.contracts import QuoteTick, TradeTick
from acsoe.core.contracts import EngineStatus
from acsoe.engines.market_sensor.candles import (
    Candle,
    bar_open_seconds,
    build_candles,
    missing_bar_timestamps,
)
from acsoe.engines.market_sensor.contracts import STATE_KEY, TradeRange, spread_ratio
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
    """The same comparison `candles_match_independent_reduction_of_recorded_trades` makes, run here too so a
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


# --------------------------------------------------------------------------- #
# Spec 85 — trade_ranges: what traded between the previous tick and this one
# --------------------------------------------------------------------------- #
#
# The property under test is what happened in the fifty-nine seconds nobody looked
# at. A resting post-only buy fills when the market trades *through* its price and a
# stop is touched when the market trades *to* it, and a quote sampled once a minute
# sees neither. So every test here drives the real engine over a stream whose trades
# are known second by second, and asserts against the arithmetic — never against a
# quote, and never against a payload the test also supplied.
#
# The window comes from `context.previous_now`, which `core/` stamps with the previous
# tick's `context.now` and leaves `None` on the first tick of a process. A context
# built by hand therefore has no previous tick and publishes no ranges, so every test
# that wants one says when the previous tick was — `ranges_at(..., previous=...)` makes
# that visible rather than incidental.

MICROS = 1_000_000


def tick_state() -> dict[str, Any]:
    return {
        "system": {"mode": "running", "close_intent": False},
        "cycle_id": 2,
        "guard_blockers": [],
    }


#: "The caller did not say", distinct from `None`, which means "there was no
#: previous tick". See `ranges_at`.
_ON_TIME: Any = object()


def one_tick_before(moment: datetime) -> datetime:
    return moment - timedelta(seconds=TICK)


def sensor_at(
    engine_context: Any,
    stream: Any,
    moment: datetime,
    *,
    previous: datetime | None,
) -> Any:
    import dataclasses

    context = dataclasses.replace(
        context_at(engine_context, moment, stream), previous_now=previous
    )
    return MarketSensorEngine().process(context, tick_state())


def ranges_at(
    engine_context: Any,
    stream: FakeStream,
    moment: datetime,
    *,
    previous: datetime | None = _ON_TIME,
) -> dict[str, Any]:
    """The ranges one tick produced. `previous` defaults to the regular loop.

    The default is a sentinel and **not** `None`, because `None` is a meaningful
    value here — it is "there was no previous tick" — and a default of `None` would
    conflate "the caller did not say" with "the caller said there is none". That is
    the one distinction the first-tick test exists to make, and it silently lost it
    the first time this helper was written.
    """
    if previous is _ON_TIME:
        previous = one_tick_before(moment)
    result = sensor_at(engine_context, stream, moment, previous=previous)
    ranges: dict[str, Any] = result.data["trade_ranges"]
    return ranges


def test_a_pair_s_range_is_the_low_the_high_and_the_count_of_what_traded(
    engine_context: Any,
) -> None:
    """Three trades inside the window, one before it. The range is the three."""
    now = ORIGIN + timedelta(seconds=10 * TICK)
    stream = FakeStream(
        [
            trade("AAA/USD", 9 * TICK - 30, "500.00", "1"),  # previous tick's window
            trade("AAA/USD", 9 * TICK + 5, "101.50", "1"),
            trade("AAA/USD", 9 * TICK + 25, "99.25", "2"),
            trade("AAA/USD", 10 * TICK, "100.00", "3"),  # exactly on `now`, included
        ]
    )

    ranges = ranges_at(engine_context, stream, now)

    assert ranges == {
        "AAA/USD": {
            "low": "99.25",
            "high": "101.50",
            "trades": 3,
            "since_ts": int((now - timedelta(seconds=TICK)).timestamp()) * MICROS,
        }
    }


def test_a_silent_pair_is_absent_and_is_never_a_zero(engine_context: Any) -> None:
    """BBB traded a minute ago and not since. It has no range, not a range of nothing.

    A range of `{"low": p, "high": p, "trades": 0}` at BBB's last price would tell a
    barrier check the market touched `p` in this window. It did not.
    """
    now = ORIGIN + timedelta(seconds=10 * TICK)
    stream = FakeStream(
        [
            trade("BBB/USD", 9 * TICK - 10, "42.00", "1"),
            trade("AAA/USD", 9 * TICK + 30, "100.00", "1"),
        ]
    )

    ranges = ranges_at(engine_context, stream, now)

    assert set(ranges) == {"AAA/USD"}
    assert "BBB/USD" not in ranges


def test_a_range_never_spans_two_ticks(engine_context: Any) -> None:
    """Two consecutive ticks over one stream. Neither range sees the other's trades.

    The spike at 300.00 belongs to tick 9 alone. If the window were anchored anywhere
    other than one tick back, it would reappear in tick 10's high and a stop far above
    the market would read as touched.
    """
    stream = FakeStream(
        [
            trade("AAA/USD", 9 * TICK - 20, "300.00", "1"),
            trade("AAA/USD", 9 * TICK - 5, "100.00", "1"),
            trade("AAA/USD", 9 * TICK + 40, "101.00", "1"),
            trade("AAA/USD", 10 * TICK, "102.00", "1"),
        ]
    )
    ninth = ORIGIN + timedelta(seconds=9 * TICK)
    tenth = ORIGIN + timedelta(seconds=10 * TICK)

    first = ranges_at(engine_context, stream, ninth)["AAA/USD"]
    second = ranges_at(engine_context, stream, tenth)["AAA/USD"]

    assert (first["low"], first["high"], first["trades"]) == ("100.00", "300.00", 2)
    assert (second["low"], second["high"], second["trades"]) == ("101.00", "102.00", 2)
    assert first["trades"] + second["trades"] == 4, "every trade counted exactly once"
    assert second["since_ts"] == int(ninth.timestamp()) * MICROS


def test_a_trade_exactly_on_since_ts_belongs_to_the_earlier_tick(
    engine_context: Any,
) -> None:
    """The window is half-open at the bottom, so consecutive ticks tile without overlap.

    Without that, the trade on the boundary is in both ranges and the two counts sum
    to one more than the number of trades.
    """
    ninth = ORIGIN + timedelta(seconds=9 * TICK)
    tenth = ORIGIN + timedelta(seconds=10 * TICK)
    stream = FakeStream(
        [
            trade("AAA/USD", 9 * TICK, "777.00", "1"),  # exactly on the boundary
            trade("AAA/USD", 10 * TICK - 1, "100.00", "1"),
        ]
    )

    first = ranges_at(engine_context, stream, ninth)["AAA/USD"]
    second = ranges_at(engine_context, stream, tenth)["AAA/USD"]

    assert first["high"] == "777.00"
    assert second["high"] == "100.00", "the boundary trade is not in the later range"
    assert first["trades"] + second["trades"] == 2


def test_a_trade_stamped_after_this_tick_is_not_in_the_range(
    engine_context: Any,
) -> None:
    """Exchange clock skew is not a licence to read the future. Invariant 10."""
    now = ORIGIN + timedelta(seconds=10 * TICK)
    stream = FakeStream(
        [
            trade("AAA/USD", 10 * TICK - 5, "100.00", "1"),
            trade("AAA/USD", 10 * TICK + 5, "900.00", "1"),
        ]
    )

    ranges = ranges_at(engine_context, stream, now)

    assert ranges["AAA/USD"]["high"] == "100.00"
    assert ranges["AAA/USD"]["trades"] == 1


def test_the_first_tick_of_a_process_publishes_no_ranges_rather_than_inventing_a_start(
    engine_context: Any,
) -> None:
    """`previous_now` is None, so there is nothing to measure from.

    `core/` leaves it None on the first tick of a process **and on the first tick
    after a restart**, and the second is the one that matters: a position restored
    from the store would otherwise be checked against a window the stream had only
    just begun to observe.
    """
    now = ORIGIN + timedelta(seconds=10 * TICK)
    stream = FakeStream([trade("AAA/USD", 10 * TICK - 5, "100.00", "1")])

    assert ranges_at(engine_context, stream, now, previous=None) == {}
    assert ranges_at(engine_context, stream, now) != {}, (
        "a tick carrying a previous stamp must publish, or the assertion above "
        "passes for the wrong reason"
    )


def test_a_loop_that_ran_late_produces_a_longer_range_and_not_a_hole(
    engine_context: Any,
) -> None:
    """The reason `previous_now` exists rather than `now - loop_tick_s`.

    The previous tick was three minutes ago, not one. Under the arithmetic this
    replaced, the 300.00 trade two and a half minutes back fell in **no** range at
    all — and a stop at 300 touched in that window was missed by engines 21 and 22.
    Here it is inside the range, because the range is bounded by when the previous
    tick actually happened.
    """
    now = ORIGIN + timedelta(seconds=10 * TICK)
    late_previous = now - timedelta(seconds=3 * TICK)
    stream = FakeStream(
        [
            trade("AAA/USD", 10 * TICK - 150, "300.00", "1"),  # inside the overshoot
            trade("AAA/USD", 10 * TICK - 30, "100.00", "1"),
        ]
    )

    with_real_stamp = ranges_at(engine_context, stream, now, previous=late_previous)["AAA/USD"]
    as_if_on_time = ranges_at(engine_context, stream, now)["AAA/USD"]

    assert with_real_stamp["high"] == "300.00"
    assert with_real_stamp["trades"] == 2
    assert with_real_stamp["since_ts"] == int(late_previous.timestamp()) * MICROS
    assert as_if_on_time["high"] == "100.00", (
        "the one-tick window must miss it, or this test is not measuring the overshoot"
    )


def test_the_ranges_and_the_candles_read_the_same_trades(engine_context: Any) -> None:
    """Spec 85 step 3. One source, so the two cannot disagree about what happened.

    Recomputed from the trades the test fed the stream, not copied from the payload:
    a comparison of `trade_ranges` against `candles` would be two readings of the
    same code agreeing with each other.
    """
    now = ORIGIN + timedelta(seconds=BAR + TICK)
    # Every trade of the bar that just closed falls inside the last tick's window.
    trades = [
        trade("AAA/USD", BAR + 5, "100.00", "1"),
        trade("AAA/USD", BAR + 20, "103.00", "1"),
        trade("AAA/USD", BAR + 40, "98.00", "1"),
    ]
    stream = FakeStream(trades)

    result = sensor_at(engine_context, stream, now, previous=one_tick_before(now))
    live = result.data["trade_ranges"]["AAA/USD"]

    assert live["low"] == format(min(tick.price for tick in trades), "f")
    assert live["high"] == format(max(tick.price for tick in trades), "f")
    assert live["trades"] == len(trades)


def test_a_client_with_no_stream_publishes_no_ranges_and_does_not_raise(
    engine_context: Any,
) -> None:
    """C's fake Kraken client has no `recent_trades`. The bar clock still runs."""

    class NoStream:
        pass

    moment = ORIGIN + timedelta(seconds=10 * TICK)
    result = sensor_at(engine_context, NoStream(), moment, previous=one_tick_before(moment))
    assert result.status is EngineStatus.OK
    assert result.data["trade_ranges"] == {}
    assert result.data["stream_available"] is False


def test_prices_cross_state_as_exact_decimal_strings(engine_context: Any) -> None:
    """A float here arrives in a barrier comparison wrong in the fourth decimal, and
    `EngineResult.data` accepts a float silently — which is what makes this worth a
    test of its own rather than an inspection."""
    now = ORIGIN + timedelta(seconds=10 * TICK)
    stream = FakeStream([trade("AAA/USD", 10 * TICK - 5, "0.000012340", "1")])

    ranges = ranges_at(engine_context, stream, now)

    assert ranges["AAA/USD"]["low"] == "0.000012340"
    assert isinstance(ranges["AAA/USD"]["low"], str)
    assert isinstance(ranges["AAA/USD"]["trades"], int)


def test_two_pairs_each_get_their_own_range(engine_context: Any) -> None:
    """A busy pair's spike must not reach a quiet pair's high."""
    now = ORIGIN + timedelta(seconds=10 * TICK)
    stream = FakeStream(
        [
            trade("AAA/USD", 10 * TICK - 50, "100.00", "1"),
            trade("AAA/USD", 10 * TICK - 10, "140.00", "1"),
            trade("BBB/USD", 10 * TICK - 30, "7.50", "1"),
        ]
    )

    ranges = ranges_at(engine_context, stream, now)

    assert ranges["AAA/USD"] == {
        "low": "100.00",
        "high": "140.00",
        "trades": 2,
        "since_ts": int((now - timedelta(seconds=TICK)).timestamp()) * MICROS,
    }
    assert ranges["BBB/USD"]["low"] == "7.50"
    assert ranges["BBB/USD"]["high"] == "7.50"
    assert ranges["BBB/USD"]["trades"] == 1


# --------------------------------------------------------------------------- #
# TradeRange — the model refuses what the rule forbids
# --------------------------------------------------------------------------- #


def a_range(**overrides: Any) -> TradeRange:
    fields: dict[str, Any] = {
        "pair": "AAA/USD",
        "low": Decimal("99.00"),
        "high": Decimal("101.00"),
        "trades": 3,
        "since_ts": 1_772_000_000_000_000,
    }
    fields.update(overrides)
    return TradeRange(**fields)


def test_a_range_of_zero_trades_cannot_be_constructed() -> None:
    """The absent-is-not-zero rule, made structural rather than remembered."""
    with pytest.raises(ValidationError, match="a range with no trades in it is not a range"):
        a_range(trades=0)


def test_a_single_trade_is_a_valid_range() -> None:
    """The other half. A model refusing every count would satisfy the test above."""
    single = a_range(trades=1, low=Decimal("100"), high=Decimal("100"))
    assert single.trades == 1
    assert single.low == single.high


def test_a_low_above_its_high_is_refused() -> None:
    with pytest.raises(ValidationError, match="is above high"):
        a_range(low=Decimal("102.00"), high=Decimal("101.00"))


def test_a_non_positive_traded_price_is_refused() -> None:
    with pytest.raises(ValidationError, match="a traded price is positive"):
        a_range(low=Decimal("0"))


def test_the_state_dict_is_exactly_the_four_keys_spec_85_names() -> None:
    """No `pair` inside the value: the map key already carries it, and a second copy
    is one more thing that can disagree with it."""
    assert a_range().state_dict() == {
        "low": "99.00",
        "high": "101.00",
        "trades": 3,
        "since_ts": 1_772_000_000_000_000,
    }
