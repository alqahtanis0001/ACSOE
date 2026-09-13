"""Spec 66 — engine 12 `regime`.

Two kinds of evidence, deliberately, because neither alone is enough.

**End to end.** Three constructed price series — a calm stretch ending in one violent
bar, a steady one-directional drift, and an oscillation that goes nowhere — driven
through the real engine 3, the real engine 5 and then engine 12. Nothing hand-builds a
`state` payload. This is the half that proves the labels are reachable from candles.

**One input at a time.** One real engine 5 payload, with exactly **one** feature value
changed per case. This is the half spec 66 asks for in as many words, and it is the only
way to show that each label is decided by the input it is supposed to be decided by: an
end-to-end fixture varies dozens of features at once, so a rule reading the wrong one
would still produce the right answer on all three series.

Changing one value inside a payload the real engine produced is a controlled experiment,
not a fabricated contract. The shape, the key names and every other value are engine 5's.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
from tests.engines.test_feature import BAR, FakeStream, archive_bars, sensor_payload, trades_for

from acsoe.core.contracts import EngineStatus
from acsoe.engines.feature.engine import FeatureEngine
from acsoe.engines.market_sensor.contracts import STATE_KEY as SENSOR_KEY
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.regime.contracts import (
    EFFICIENCY_FEATURE,
    KEY_HIGH_VOL_PERCENTILE,
    KEY_TREND_EFFICIENCY,
    REASON_NO_FEATURE_ROW,
    REASON_NO_INPUTS,
    REGIME_LABELS,
    STATE_KEY,
    VOL_RANK_FEATURE,
    RegimeState,
)
from acsoe.engines.regime.engine import RegimeEngine
from acsoe.modelling.features import REGIME_LONG_BARS

PAIR = "AAAUSD"


@pytest.fixture
def engine() -> RegimeEngine:
    return RegimeEngine()


def series(steps: list[float], *, start_price: float = 100.0) -> list[dict[str, Any]]:
    """Candles whose per-bar return is exactly `steps[i]`, on a contiguous grid.

    The origin is snapped **onto** the decision-bar grid. Engine 3 decides `bar_closed`
    by asking whether the bar index changed since one tick ago, so a series whose bars
    sit at 1,700,000,000 — which is not a multiple of 900 — never produces a tick where
    `now` is one bar past the last candle and the index has just moved. The fixture then
    reports `bar_closed: False` and the test fails somewhere far from the cause.
    """
    origin = (1_700_000_000 // BAR) * BAR
    out: list[dict[str, Any]] = []
    price = start_price
    for index, step in enumerate(steps):
        price = price * (1.0 + step)
        out.append(
            {
                "ts": origin + index * BAR,
                "open": price * 0.9999,
                "high": price * (1.0 + abs(step) * 0.5 + 0.0002),
                "low": price * (1.0 - abs(step) * 0.5 - 0.0002),
                "close": price,
                "volume": 1000.0 + (index % 7),
                "trades": 20 + (index % 5),
            }
        )
    return out


def feature_row(engine_context: Any, bars: list[dict[str, Any]]) -> tuple[dict[str, Any], Any]:
    """Engine 5's real payload over `bars`, through the real engine 3."""
    _payload, _closed, context = sensor_payload(engine_context, bars, pair=PAIR)
    object.__setattr__(context.clients, "kraken", FakeStream(trades_for(bars, pair=PAIR)))
    sensor = dict(MarketSensorEngine().process(context, {}).data)
    features = dict(FeatureEngine().process(context, {SENSOR_KEY: sensor}).data)
    return features, context


def classify(
    engine: RegimeEngine, context: Any, features: dict[str, Any], *, pair: str = PAIR
) -> dict[str, Any]:
    state = {"feature": features, "scout": {"pair": pair}}
    return dict(engine.process(context, state).data)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table(engine: RegimeEngine) -> None:
    assert engine.name == "regime"
    assert engine.number == 12
    assert engine.is_gate is False


def test_the_label_set_is_closed() -> None:
    """Three labels and `null`. A fourth is a change to a cross-chain key fixed in
    `engine-contracts.md` and belongs to the lead."""
    assert set(REGIME_LABELS) == {"trending", "choppy", "high_volatility"}


# --------------------------------------------------------------------------- #
# End to end, from candles
# --------------------------------------------------------------------------- #


def test_a_calm_stretch_ending_in_one_violent_bar_is_high_volatility(
    engine: RegimeEngine, engine_context: Any
) -> None:
    steps = [0.0004 * ((i % 5) - 2) for i in range(REGIME_LONG_BARS * 3)]
    steps[-1] = 0.14
    features, context = feature_row(engine_context, series(steps))
    data = classify(engine, context, features)
    assert data["label"] == "high_volatility", data["inputs"]


def test_a_steady_one_directional_drift_is_trending(
    engine: RegimeEngine, engine_context: Any
) -> None:
    steps = [0.002] * (REGIME_LONG_BARS * 3)
    features, context = feature_row(engine_context, series(steps))
    data = classify(engine, context, features)
    assert data["label"] == "trending", data["inputs"]


def test_an_oscillation_that_goes_nowhere_is_choppy(
    engine: RegimeEngine, engine_context: Any
) -> None:
    steps = [0.002 if i % 2 == 0 else -0.002 for i in range(REGIME_LONG_BARS * 3)]
    features, context = feature_row(engine_context, series(steps))
    data = classify(engine, context, features)
    assert data["label"] == "choppy", data["inputs"]


# --------------------------------------------------------------------------- #
# One input at a time
# --------------------------------------------------------------------------- #


@pytest.fixture
def baseline(engine_context: Any) -> tuple[dict[str, Any], Any]:
    """A real engine 5 payload over a real archive slice, to vary one value inside."""
    return feature_row(engine_context, archive_bars(limit=260))


def with_one_input(
    features: dict[str, Any], *, name: str, value: float, pair: str = PAIR
) -> dict[str, Any]:
    row = {**features["pairs"][pair], name: value}
    return {**features, "pairs": {**features["pairs"], pair: row}}


def test_each_label_is_reached_by_changing_exactly_one_input(
    engine: RegimeEngine, baseline: tuple[dict[str, Any], Any]
) -> None:
    """The assertion spec 66 asks for, and the one an end-to-end fixture cannot make.

    Three payloads, identical in every value but one. If the rules read a different
    feature than the one they name, all three would land on the same label.
    """
    features, context = baseline
    high_vol = float(context.config.get(KEY_HIGH_VOL_PERCENTILE))
    trend = float(context.config.get(KEY_TREND_EFFICIENCY))

    calm_and_directionless = with_one_input(features, name=VOL_RANK_FEATURE, value=0.1)
    calm_and_directionless = with_one_input(
        calm_and_directionless, name=EFFICIENCY_FEATURE, value=trend / 2
    )
    assert classify(engine, context, calm_and_directionless)["label"] == "choppy"

    # ONE value away from the choppy fixture: the trend measure.
    trending = with_one_input(
        calm_and_directionless, name=EFFICIENCY_FEATURE, value=min(trend * 2, 1.0)
    )
    assert classify(engine, context, trending)["label"] == "trending"

    # ONE value away from the same choppy fixture: the volatility position. Set exactly
    # **on** the configured percentile, which also pins the comparison as inclusive — a
    # `>` where a `>=` belongs is a one-character change that no metric would reveal.
    volatile = with_one_input(calm_and_directionless, name=VOL_RANK_FEATURE, value=high_vol)
    assert classify(engine, context, volatile)["label"] == "high_volatility"


def test_volatility_outranks_trend(
    engine: RegimeEngine, baseline: tuple[dict[str, Any], Any]
) -> None:
    """Rule order, pinned. A violently volatile market that also happens to be moving in
    one direction is `high_volatility`: the volatility is the fact a router needs."""
    features, context = baseline
    both = with_one_input(features, name=VOL_RANK_FEATURE, value=1.0)
    both = with_one_input(both, name=EFFICIENCY_FEATURE, value=1.0)
    assert classify(engine, context, both)["label"] == "high_volatility"


def test_the_rule_is_percentile_relative_and_not_an_absolute_volatility(
    engine: RegimeEngine, baseline: tuple[dict[str, Any], Any]
) -> None:
    """Spec 66's named mutation: the percentile rule replaced by an absolute threshold.

    The raw short-window volatility is raised a hundredfold while the **rank** stays low.
    An absolute rule would call that high volatility; a percentile-relative rule says
    this pair is no more volatile than it usually is, which is the whole claim. The
    reverse case is the second half: a tiny raw volatility that is nonetheless the top of
    this pair's own distribution **is** high volatility.
    """
    features, context = baseline
    from acsoe.modelling.features import REGIME_SHORT_BARS

    raw = f"realised_vol_{REGIME_SHORT_BARS}"

    loud_but_ordinary = with_one_input(features, name=VOL_RANK_FEATURE, value=0.2)
    loud_but_ordinary = with_one_input(loud_but_ordinary, name=raw, value=5.0)
    loud_but_ordinary = with_one_input(loud_but_ordinary, name=EFFICIENCY_FEATURE, value=0.05)
    assert classify(engine, context, loud_but_ordinary)["label"] == "choppy"

    quiet_but_extreme = with_one_input(features, name=VOL_RANK_FEATURE, value=1.0)
    quiet_but_extreme = with_one_input(quiet_but_extreme, name=raw, value=1e-9)
    assert classify(engine, context, quiet_but_extreme)["label"] == "high_volatility"


def test_the_configured_thresholds_are_applied_and_echoed(
    engine: RegimeEngine, baseline: tuple[dict[str, Any], Any]
) -> None:
    """Not constants. The cutoffs are read from config on every tick and reported beside
    the label, so a label is readable without the config file open."""
    features, context = baseline
    data = classify(engine, context, features)
    assert data["thresholds"][KEY_HIGH_VOL_PERCENTILE] == float(
        context.config.get(KEY_HIGH_VOL_PERCENTILE)
    )
    assert data["thresholds"][KEY_TREND_EFFICIENCY] == float(
        context.config.get(KEY_TREND_EFFICIENCY)
    )

    class Always:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def get(self, key: str) -> Any:
            if key == KEY_HIGH_VOL_PERCENTILE:
                return 0.0  # every bar is at or above the zeroth percentile
            return self._inner.get(key)

    forced = dataclasses.replace(context, config=Always(context.config))
    assert classify(engine, forced, features)["label"] == "high_volatility"


# --------------------------------------------------------------------------- #
# Null is not a fourth label
# --------------------------------------------------------------------------- #


def test_no_candidate_is_a_pass(engine: RegimeEngine, engine_context: Any) -> None:
    result = engine.process(engine_context, {"scout": {}})
    assert result.status is EngineStatus.PASS
    assert result.data == {}


def test_a_candidate_with_no_feature_row_publishes_a_null_label_and_a_reason(
    engine: RegimeEngine, baseline: tuple[dict[str, Any], Any]
) -> None:
    features, context = baseline
    data = classify(engine, context, features, pair="NOSUCHUSD")
    assert data["label"] is None
    assert data["reason"] == REASON_NO_FEATURE_ROW


def test_an_unfilled_input_publishes_a_null_label_rather_than_falling_through_to_choppy(
    engine: RegimeEngine, baseline: tuple[dict[str, Any], Any]
) -> None:
    """The branch that looks like a default is the dangerous one.

    A NaN compares False against every threshold, so an unfilled input reaching the rules
    would land on `choppy` — a label nobody measured, indistinguishable downstream from a
    measured one, and one Phase 6's router would weight a model by.
    """
    features, context = baseline
    blank = with_one_input(features, name=VOL_RANK_FEATURE, value=float("nan"))
    data = classify(engine, context, blank)
    assert data["label"] is None
    assert data["reason"] == REASON_NO_INPUTS

    missing = {**features, "pairs": {**features["pairs"], PAIR: {}}}
    assert classify(engine, context, missing)["reason"] == REASON_NO_INPUTS


def test_a_pair_with_short_history_gets_a_null_label(
    engine: RegimeEngine, engine_context: Any
) -> None:
    """End to end, and the same pair engine 5 lists in `pairs_with_short_history`."""
    features, context = feature_row(engine_context, series([0.001] * 6))
    assert PAIR in features["pairs_with_short_history"]
    data = classify(engine, context, features)
    assert data["label"] is None
    assert data["reason"] == REASON_NO_INPUTS


# --------------------------------------------------------------------------- #
# The DI placeholder, and what crosses `state`
# --------------------------------------------------------------------------- #


def test_di_regime_shift_is_published_as_null(
    engine: RegimeEngine, baseline: tuple[dict[str, Any], Any]
) -> None:
    """A declared placeholder, not an oversight.

    Engine 12 runs before engine 8, so this tick's DI does not exist yet, and `state` is
    fresh every tick so last bar's is not there either. Published as `null` with the
    reasoning in the README; where a previous bar's DI would live is a schema question
    and an open question for the operator.
    """
    features, context = baseline
    data = classify(engine, context, features)
    assert "di_regime_shift" in data
    assert data["di_regime_shift"] is None


def test_the_engine_never_reads_the_store() -> None:
    """The temptation this placeholder creates, closed off by assertion.

    An engine inventing its own persistence for a cross-chain key is how that key ends up
    with two meanings. Asserted on the source rather than on behaviour, because the
    behaviour only appears once someone writes the read.
    """
    import ast
    from pathlib import Path

    source = Path(
        str(__import__("acsoe.engines.regime.engine", fromlist=["engine"]).__file__)
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    hits = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"store", "clients"}
    ]
    assert hits == [], hits


def test_the_payload_is_json_serialisable_and_validates(
    engine: RegimeEngine, baseline: tuple[dict[str, Any], Any]
) -> None:
    features, context = baseline
    data = classify(engine, context, features)
    json.dumps(data, allow_nan=False)
    RegimeState.model_validate(data)


def test_it_never_blocks_trading(
    engine: RegimeEngine, baseline: tuple[dict[str, Any], Any]
) -> None:
    features, context = baseline
    for state in (
        {"feature": features, "scout": {"pair": PAIR}},
        {"feature": features, "scout": {"pair": "NOSUCHUSD"}},
        {"scout": {}},
    ):
        result = engine.process(context, state)
        assert result.blocks_trading is False
    assert STATE_KEY == "regime"
