"""Spec 64 — engine 5 `feature`.

**Every fixture here is engine 3's real output.** Not a hand-built `state["market_sensor"]`
payload: the Phase 3 audit found engines 10, 11 and 17 green against a `state["exchange"]`
shape engine 1 does not publish, because every test built that payload by hand in the shape
the engine expected, and the operator ruled the fixtures be rewritten from the producer's
real output rather than repointed. So `MarketSensorEngine` is driven over a trade stream
derived from the committed archive slice, and whatever it publishes is what engine 5 is
handed.

The prices are real. `tests/fixtures/candles_sample.parquet` is the OHLCVT slice of
`data/historical/SOLUSD_15.csv` the labelled sample was produced from, and the trades below
are constructed so that engine 3 rebuilds exactly those bars: four trades per bar at the
open, high, low and close, in that order, with the bar's volume split between them.

Three properties, and each is one of spec 64's named mutations:

* `bar_closed` false means `PASS` and nothing else. Ignoring it computes features on every
  tick, which is not a crash — it is fourteen wasted computations in fifteen and, worse, a
  `state["feature"]` present on ticks when no bar closed, which every downstream engine is
  entitled to read as "a bar closed".
* a pair with too little history is **listed, never dropped**. Dropping it makes it
  invisible to engine 7, which is the gate that is supposed to consider it.
* the grouping is keyed on `pair`. Keyed on anything else, two pairs' candles merge into
  one series and every feature is computed over a price series that never existed.
"""

from __future__ import annotations

import dataclasses
import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import require_module

from acsoe.clients.kraken.contracts import TradeTick
from acsoe.core.contracts import EngineStatus
from acsoe.engines.feature.contracts import (
    KEY_MAX_LOOKBACK_BARS,
    KEY_MIN_LOOKBACK_FILL,
    STATE_KEY,
    FeatureState,
    MissingInputError,
)
from acsoe.engines.feature.engine import FeatureEngine
from acsoe.engines.market_sensor.contracts import STATE_KEY as SENSOR_KEY
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.modelling.features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    LOOKBACK_BARS,
    MAX_LOOKBACK_BARS,
    compute,
)

pl = require_module("polars", reason="polars is not installed")

BAR = 900
TICK = 60
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "candles_sample.parquet"
PAIR = "SOLUSD"

pytestmark = pytest.mark.skipif(
    not FIXTURE.is_file(), reason="tests/fixtures/candles_sample.parquet is not committed"
)


# --------------------------------------------------------------------------- #
# Engine 3's real output, over real prices
# --------------------------------------------------------------------------- #


class FakeStream:
    """A market stream double: a rolling trade window and no quotes.

    The same shape as the one in `test_market_sensor.py`. It is written out rather than
    imported so that this file does not go red when A refactors a test of A's own, and it
    is deliberately *not* a fourth stand-in for engine 3 — engine 3 itself runs below;
    this only feeds it.
    """

    def __init__(self, trades: list[TradeTick]) -> None:
        self._trades = list(trades)

    def recent_trades(self) -> tuple[TradeTick, ...]:
        return tuple(self._trades)

    def latest_quote(self, pair: str) -> None:
        return None


def archive_bars(limit: int | None = None) -> list[dict[str, Any]]:
    """The committed OHLCVT slice as plain rows, newest last."""
    frame = pl.read_parquet(FIXTURE).sort("ts")
    if limit is not None:
        frame = frame.tail(limit)
    return frame.to_dicts()


def trades_for(bars: list[dict[str, Any]], *, pair: str = PAIR) -> list[TradeTick]:
    """Four trades per bar — open, high, low, close — that rebuild the bar exactly.

    `build_candles` takes the first price as the open, the last as the close, the max as
    the high and the min as the low, breaking ties by input order. On real OHLC the high
    is never below the open or close and the low is never above them, so this ordering
    reproduces all four. The volume is split so the four quantities sum to the bar's own
    volume exactly, with the remainder on the last trade rather than spread by rounding.
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
                    pair=pair,
                    ts=datetime.fromtimestamp(ts, tz=UTC) + timedelta(seconds=offset),
                    price=Decimal(str(price)),
                    qty=qty,
                )
            )
    return out


def sensor_payload(
    engine_context: Any, bars: list[dict[str, Any]], *, pair: str = PAIR
) -> tuple[dict[str, Any], int, Any]:
    """Run the **real** engine 3 over those bars and return what it published.

    Returns `(payload, closed_bar_ts, context)`. `now` is placed one bar and one second
    after the newest bar, which is the first tick on which that bar has closed.
    """
    last_ts = int(bars[-1]["ts"])
    now = datetime.fromtimestamp(last_ts + BAR + 1, tz=UTC)
    context = dataclasses.replace(engine_context, now=now)
    object.__setattr__(context.clients, "kraken", FakeStream(trades_for(bars, pair=pair)))
    result = MarketSensorEngine().process(context, {})
    payload = dict(result.data)
    assert payload["bar_closed"] is True, "the fixture places `now` on a bar boundary"
    assert payload["closed_bar_ts"] == last_ts
    return payload, last_ts, context


@pytest.fixture
def bars() -> list[dict[str, Any]]:
    """Enough bars for engine 3's `market_sensor.published_bars` cap to be the binding
    constraint, which is the live situation."""
    return archive_bars(limit=260)


@pytest.fixture
def engine() -> FeatureEngine:
    return FeatureEngine()


def run(
    engine: FeatureEngine, engine_context: Any, payload: dict[str, Any]
) -> tuple[Any, dict[str, Any]]:
    state: dict[str, Any] = {SENSOR_KEY: payload}
    result = engine.process(engine_context, state)
    return result, dict(result.data)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table(engine: FeatureEngine) -> None:
    assert engine.name == "feature"
    assert engine.number == 5
    assert engine.is_gate is False


# --------------------------------------------------------------------------- #
# The cadence
# --------------------------------------------------------------------------- #


def test_a_non_bar_tick_is_a_pass_with_no_data(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """Fourteen ticks in fifteen end here, and this is what stops the opportunity chain.

    `PASS`, not `BLOCK`: nothing is wrong and nothing should be recorded as a blocker.

    The payload is engine 3's **real** output at a mid-bar moment, not a hand-built
    `{"bar_closed": False}`. The difference is the Phase 3 audit's whole finding: three
    engines were green against a `state` shape their producer does not publish, because
    every test built that payload by hand in the shape the engine expected. Engine 3
    publishes `closed_bar_ts` as `None` on a non-bar tick while still carrying candles,
    and a hand-built payload would not have said so.
    """
    last_ts = int(bars[-1]["ts"])
    mid_bar = datetime.fromtimestamp(last_ts + BAR + 300, tz=UTC)
    context = dataclasses.replace(engine_context, now=mid_bar)
    object.__setattr__(context.clients, "kraken", FakeStream(trades_for(bars)))
    payload = dict(MarketSensorEngine().process(context, {}).data)
    assert payload["bar_closed"] is False
    assert payload["closed_bar_ts"] is None
    assert payload["candles"], "the tick carries candles; only the bar boundary is absent"

    result, data = run(engine, context, payload)
    assert result.status is EngineStatus.PASS
    assert result.blocks_trading is False
    assert data == {}


def test_an_absent_market_sensor_key_is_also_a_pass(
    engine: FeatureEngine, engine_context: Any
) -> None:
    """Engine 3 not having run is not engine 5's business to judge. The guard chain has
    already decided whether the tick is trustworthy; an engine 5 that raised here would
    turn a quiet startup tick into an ERROR that blocks."""
    result = engine.process(engine_context, {})
    assert result.status is EngineStatus.PASS


def test_features_appear_on_a_bar_tick_from_engine_3s_real_output(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    payload, closed_bar_ts, context = sensor_payload(engine_context, bars)
    result, data = run(engine, context, payload)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert data["bar_ts"] == closed_bar_ts
    assert data["feature_version"] == FEATURE_VERSION
    assert tuple(data["feature_names"]) == FEATURE_NAMES
    assert set(data["pairs"]) == {PAIR}
    assert set(data["pairs"][PAIR]) == set(FEATURE_NAMES)
    assert data["row_ts"][PAIR] == closed_bar_ts


def test_the_published_row_equals_the_modelling_function_over_the_same_candles(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """The engine shapes and publishes; it computes nothing.

    Engine 3's own published candles are read back out of `state`, cast the way the
    engine casts them, and handed straight to `modelling.features.compute`. Every value
    must match exactly — this engine may group, cast, truncate and turn NaN into `null`,
    and it may not change a number.
    """
    payload, closed_bar_ts, context = sensor_payload(engine_context, bars)
    _result, data = run(engine, context, payload)

    published = pl.DataFrame(
        [
            {
                "ts": int(candle["ts"]),
                **{k: float(candle[k]) for k in ("open", "high", "low", "close", "volume")},
                "trades": int(candle["trades"]),
            }
            for candle in payload["candles"]
            if candle["pair"] == PAIR
        ]
    ).sort("ts")
    direct = compute(
        published,
        interval_s=BAR,
        min_lookback_fill=float(engine_context.config.get(KEY_MIN_LOOKBACK_FILL)),
    )
    expected = direct.filter(pl.col("ts") == closed_bar_ts).to_dicts()[0]

    row = data["pairs"][PAIR]
    for name in FEATURE_NAMES:
        want = expected[name]
        want_null = want is None or math.isnan(float(want))
        if want_null:
            assert row[name] is None, name
        else:
            assert row[name] == float(want), name


def test_engine_3s_candles_reproduce_the_archive_bars_they_were_built_from(
    engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """The fixture's own premise, asserted rather than assumed.

    If the constructed trade stream did not rebuild the archive's bars, every test above
    would still pass — against a price series nobody chose. This is the seam check:
    a double that is simpler than the real thing *in the dimension the test is about*
    cannot fail.
    """
    payload, _closed, _context = sensor_payload(engine_context, bars)
    published = {int(c["ts"]): c for c in payload["candles"] if c["pair"] == PAIR}
    checked = 0
    for bar in bars:
        candle = published.get(int(bar["ts"]))
        if candle is None:
            continue  # the published window is capped per pair; the older bars drop out
        for field in ("open", "high", "low", "close", "volume"):
            assert Decimal(candle[field]) == Decimal(str(bar[field])), (field, bar["ts"])
        checked += 1
    assert checked > 100, checked


# --------------------------------------------------------------------------- #
# Look-ahead
# --------------------------------------------------------------------------- #


def test_a_candle_after_the_closed_bar_changes_nothing(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """Engine 3 never publishes the in-progress bar, and engine 5 does not rely on that.

    Spec 64 asks for this explicitly: the engine must still exclude a candle whose `ts`
    is `closed_bar_ts` plus one interval **if one appeared**. The defect it guards is
    look-ahead, and look-ahead makes a backtest *better*, which is the direction nothing
    downstream ever questions.
    """
    payload, closed_bar_ts, context = sensor_payload(engine_context, bars)
    _result, clean = run(engine, context, payload)

    intruder = dict(payload["candles"][-1])
    intruder["ts"] = closed_bar_ts + BAR
    intruder["close"] = str(Decimal(intruder["close"]) * Decimal("1.25"))
    intruder["high"] = str(Decimal(intruder["high"]) * Decimal("1.25"))
    polluted_payload = {**payload, "candles": (*payload["candles"], intruder)}
    _result2, polluted = run(engine, context, polluted_payload)

    assert polluted["pairs"] == clean["pairs"]
    assert polluted["row_ts"] == clean["row_ts"]


# --------------------------------------------------------------------------- #
# Pairs are reported, never dropped
# --------------------------------------------------------------------------- #


def test_a_pair_with_short_history_is_published_with_nulls_and_listed(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """Engine 5 is not a gate. A pair it cannot judge is still a pair engine 7 must be
    able to see was considered, and that is a different fact from a pair nobody looked
    at."""
    short_bars = bars[-4:]
    payload, closed_bar_ts, context = sensor_payload(engine_context, bars)
    short_trades = trades_for(short_bars, pair="AAAUSD")
    object.__setattr__(
        context.clients,
        "kraken",
        FakeStream([*trades_for(bars), *short_trades]),
    )
    payload = dict(MarketSensorEngine().process(context, {}).data)

    _result, data = run(engine, context, payload)

    assert "AAAUSD" in data["pairs"], "a short-history pair must never be dropped"
    assert "AAAUSD" in data["pairs_with_short_history"]
    assert PAIR not in data["pairs_with_short_history"]

    row = data["pairs"]["AAAUSD"]
    assert row[f"bars_in_lookback_{MAX_LOOKBACK_BARS}"] == float(len(short_bars))
    blanked = [
        name
        for name in FEATURE_NAMES
        if name.endswith(f"_{MAX_LOOKBACK_BARS}")
        and not name.startswith("bars_in_lookback")
    ]
    assert blanked, "the lookback naming changed and this test stopped checking anything"
    for name in blanked:
        assert row[name] is None, name
    assert data["row_ts"]["AAAUSD"] == closed_bar_ts


def test_two_pairs_are_grouped_separately(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """Grouped on `pair`. Keyed on anything else the two series merge, and every feature
    describes a price path that never existed — a defect that produces numbers rather
    than an error."""
    _payload, _closed, context = sensor_payload(engine_context, bars)
    shifted = [{**bar, "close": float(bar["close"]) * 1.5} for bar in bars]
    object.__setattr__(
        context.clients,
        "kraken",
        FakeStream([*trades_for(bars), *trades_for(shifted, pair="BBBUSD")]),
    )
    payload = dict(MarketSensorEngine().process(context, {}).data)

    _result, data = run(engine, context, payload)

    assert set(data["pairs"]) == {PAIR, "BBBUSD"}
    assert data["pairs"][PAIR] != data["pairs"]["BBBUSD"], (
        "two pairs with different prices produced identical feature rows, which is what "
        "a grouping keyed on something other than the pair name looks like"
    )


def test_a_pair_that_did_not_trade_in_the_bar_keeps_its_own_row_ts(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """No trades means no candle, and nothing may invent one.

    The pair is neither dropped nor dated to a bar it has no data for: it gets the row of
    its most recent closed bar and `row_ts` says which. A consumer that cares about
    staleness compares `row_ts[pair]` against `bar_ts`.
    """
    _payload, closed_bar_ts, context = sensor_payload(engine_context, bars)
    quiet = [bar for bar in bars if int(bar["ts"]) < closed_bar_ts]
    object.__setattr__(
        context.clients,
        "kraken",
        FakeStream([*trades_for(bars), *trades_for(quiet, pair="QUIETUSD")]),
    )
    payload = dict(MarketSensorEngine().process(context, {}).data)

    _result, data = run(engine, context, payload)

    assert "QUIETUSD" in data["pairs"]
    assert data["bar_ts"] == closed_bar_ts
    assert data["row_ts"]["QUIETUSD"] == int(quiet[-1]["ts"])
    assert data["row_ts"]["QUIETUSD"] < data["bar_ts"]
    assert data["row_ts"][PAIR] == closed_bar_ts


def test_gaps_are_counted_per_pair_from_that_pairs_own_candles(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """Not read through from engine 3's `missing_bars`, which pools every pair's
    timestamps before looking for holes — so a slot is absent from that union only when
    no pair anywhere traded in it, and on a multi-pair tick it reports nearly nothing and
    reports it identically for every pair."""
    _payload, _closed, context = sensor_payload(engine_context, bars)
    holed = [bar for index, bar in enumerate(bars) if index % 7 != 3 or index > len(bars) - 5]
    object.__setattr__(
        context.clients,
        "kraken",
        FakeStream([*trades_for(bars), *trades_for(holed, pair="HOLEUSD")]),
    )
    payload = dict(MarketSensorEngine().process(context, {}).data)

    _result, data = run(engine, context, payload)

    assert data["gaps_in_range"][PAIR] == 0
    assert data["gaps_in_range"]["HOLEUSD"] > 0
    assert data["gaps_in_range"]["HOLEUSD"] != data["gaps_in_range"][PAIR], (
        "both pairs were given the same gap count, which is the signature of a count "
        "read through from engine 3 rather than computed per pair"
    )


# --------------------------------------------------------------------------- #
# What crosses `state`
# --------------------------------------------------------------------------- #


def test_no_nan_crosses_state_and_the_payload_is_json_serialisable(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """Contract rule 8. A float NaN survives `json.dumps` only as a non-standard token
    that some readers accept and some reject, and `null` is the honest spelling of "not
    computable from the bars that were there"."""
    _payload, _closed, context = sensor_payload(engine_context, bars[-6:])
    payload = dict(MarketSensorEngine().process(context, {}).data)
    _result, data = run(engine, context, payload)

    encoded = json.dumps(data, allow_nan=False)
    assert "NaN" not in encoded
    for row in data["pairs"].values():
        for value in row.values():
            assert value is None or isinstance(value, float)
            if isinstance(value, float):
                assert not math.isnan(value)


def test_a_null_is_never_published_as_a_zero(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """The distinction the whole payload turns on. A zero is a value a model will happily
    learn from and is indistinguishable downstream from a genuinely quiet market."""
    _payload, _closed, context = sensor_payload(engine_context, bars[-5:])
    payload = dict(MarketSensorEngine().process(context, {}).data)
    _result, data = run(engine, context, payload)

    row = data["pairs"][PAIR]
    longest = [
        name
        for name in FEATURE_NAMES
        if name.endswith(f"_{MAX_LOOKBACK_BARS}") and not name.startswith("bars_in_lookback")
    ]
    assert any(row[name] is None for name in longest)
    assert all(row[name] != 0.0 for name in longest if row[name] is not None)


def test_the_payload_validates_against_its_own_contract(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    payload, _closed, context = sensor_payload(engine_context, bars)
    _result, data = run(engine, context, payload)
    FeatureState.model_validate(data)


# --------------------------------------------------------------------------- #
# Refusals that are deliberate
# --------------------------------------------------------------------------- #


def test_a_closed_bar_with_no_timestamp_raises(
    engine: FeatureEngine, engine_context: Any
) -> None:
    """A shape engine 3 cannot produce. The orchestrator turns a raise into `ERROR`,
    which blocks, and that is the correct answer: guessing which bar closed would date
    every row in the tick to a bar nobody chose."""
    with pytest.raises(MissingInputError, match="closed_bar_ts"):
        engine.process(
            engine_context,
            {SENSOR_KEY: {"bar_closed": True, "closed_bar_ts": None, "interval_s": BAR}},
        )


def test_a_missing_interval_raises(engine: FeatureEngine, engine_context: Any) -> None:
    with pytest.raises(MissingInputError, match="interval_s"):
        engine.process(
            engine_context,
            {SENSOR_KEY: {"bar_closed": True, "closed_bar_ts": 1_700_000_000}},
        )


def test_a_lookback_longer_than_the_configured_ceiling_raises(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """The live path publishes `market_sensor.published_bars` candles. A lookback longer
    than the configured ceiling can never be filled live while the offline builder fills
    it every time, so the two paths differ on every bar — silently, with the offline
    number being the one that looks right."""
    payload, _closed, context = sensor_payload(engine_context, bars)

    class Narrow:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def get(self, key: str) -> Any:
            if key == KEY_MAX_LOOKBACK_BARS:
                return MAX_LOOKBACK_BARS - 1
            return self._inner.get(key)

    narrowed = dataclasses.replace(context, config=Narrow(context.config))
    with pytest.raises(MissingInputError, match="MAX_LOOKBACK_BARS"):
        engine.process(narrowed, {SENSOR_KEY: payload})


def test_the_configured_ceiling_and_the_module_agree_in_the_committed_config(
    engine_context: Any,
) -> None:
    """The control for the test above, against the config that actually ships. Without
    it, a ceiling set below the longest window would make engine 5 raise on every bar
    tick and only the negative test would be green."""
    assert int(engine_context.config.get(KEY_MAX_LOOKBACK_BARS)) >= MAX_LOOKBACK_BARS
    assert max(LOOKBACK_BARS) == MAX_LOOKBACK_BARS


def test_it_never_blocks_trading(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """Engine 5 is not a gate, and `is_gate` is what `is_gate_matches_registry` checks."""
    payload, _closed, context = sensor_payload(engine_context, bars)
    for state in ({SENSOR_KEY: payload}, {SENSOR_KEY: {"bar_closed": False}}, {}):
        result = engine.process(context, state)
        assert result.blocks_trading is False
        assert result.status in (EngineStatus.OK, EngineStatus.PASS)


def test_it_writes_exactly_one_state_key(
    engine: FeatureEngine, engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """Contract rule 2. The orchestrator files `result.data` under the engine's name, so
    what this asserts is that the engine returns a payload and mutates nothing."""
    payload, _closed, context = sensor_payload(engine_context, bars)
    state: dict[str, Any] = {SENSOR_KEY: payload}
    before = set(state)
    engine.process(context, state)
    assert set(state) == before
    assert STATE_KEY == "feature"
