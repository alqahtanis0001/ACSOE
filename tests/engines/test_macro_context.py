"""Spec 65 — engine 6 `macro_context`.

Fixtures are **engine 5's real output**, which is in turn engine 3's real output over the
committed archive slice. Nothing here hand-builds `state["feature"]`: the helpers are
imported from `test_feature.py` so that there is one reconstruction of engine 3's payload
in the suite rather than a second one that can drift from it.

The property this file is mostly about is the one spec 65 names as its mutation: **a
missing macro pair silently published as zeros**. That is the shape worth guarding,
because it does not fail — it feeds the predictor a Bitcoin that did not move on exactly
the bars where the macro feed was broken, and a model learns from it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.engines.test_feature import (
    FakeStream,
    archive_bars,
    sensor_payload,
    trades_for,
)

from acsoe.core.contracts import EngineStatus
from acsoe.engines.feature.engine import FeatureEngine
from acsoe.engines.macro_context.contracts import (
    KEY_MACRO,
    STATE_KEY,
    MacroContextState,
    macro_column,
    macro_feature_names,
    macro_pair_names,
)
from acsoe.engines.macro_context.engine import MacroContextEngine
from acsoe.engines.market_sensor.contracts import STATE_KEY as SENSOR_KEY
from acsoe.modelling.features import FEATURE_NAMES

BTC = "BTC/USD"
ETH = "ETH/USD"
MACRO = {"btc": {"live": BTC, "archive": "XBTUSD"}, "eth": {"live": ETH, "archive": "ETHUSD"}}


@pytest.fixture
def engine() -> MacroContextEngine:
    return MacroContextEngine()


def feature_state(
    engine_context: Any, *, pairs: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, Any], Any]:
    """Engine 5's real payload over these pairs' bars, through engine 3."""
    base = archive_bars(limit=260)
    _payload, _closed, context = sensor_payload(engine_context, base)
    trades = list(trades_for(base))
    for pair, bars in pairs.items():
        trades.extend(trades_for(bars, pair=pair))
    object.__setattr__(context.clients, "kraken", FakeStream(trades))

    from acsoe.engines.market_sensor.engine import MarketSensorEngine

    sensor = dict(MarketSensorEngine().process(context, {}).data)
    features = dict(FeatureEngine().process(context, {SENSOR_KEY: sensor}).data)
    return features, context


def both_macro_pairs(engine_context: Any) -> tuple[dict[str, Any], Any]:
    base = archive_bars(limit=260)
    shifted = [{**bar, "close": float(bar["close"]) * 1.1} for bar in base]
    return feature_state(engine_context, pairs={BTC: base, ETH: shifted})


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table(engine: MacroContextEngine) -> None:
    assert engine.name == "macro_context"
    assert engine.number == 6
    assert engine.is_gate is False


# --------------------------------------------------------------------------- #
# The column names
# --------------------------------------------------------------------------- #


def test_the_macro_columns_are_derived_from_the_feature_list_and_the_assets() -> None:
    names = macro_feature_names(["btc", "eth"])
    assert len(names) == 2 * len(FEATURE_NAMES)
    assert names[0] == macro_column("btc", FEATURE_NAMES[0])
    assert len(set(names)) == len(names)


def test_the_asset_order_is_sorted_and_not_the_config_files_order() -> None:
    """The configured mapping is a YAML dict whose iteration order is the file's.

    Sorting is what stops reordering two lines in `config/default.yaml` from permuting
    the trained feature order — and a model handed its columns permuted returns confident
    nonsense with nothing raising.
    """
    assert macro_feature_names(["eth", "btc"]) == macro_feature_names(["btc", "eth"])


def test_a_macro_asset_with_no_live_spelling_is_refused() -> None:
    """Both spellings are config and neither may be inferred from the other: Kraken
    calls the same pair `BTC/USD` live and `XBTUSD` in the archive."""
    with pytest.raises(ValueError, match="no 'live' pair name"):
        macro_pair_names({"btc": {"archive": "XBTUSD"}}, spelling="live")


def test_both_spellings_are_read_from_the_same_mapping() -> None:
    assert macro_pair_names(MACRO, spelling="live") == {"btc": BTC, "eth": ETH}
    assert macro_pair_names(MACRO, spelling="archive") == {"btc": "XBTUSD", "eth": "ETHUSD"}


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def test_it_selects_and_renames_engine_5s_rows_without_changing_a_number(
    engine: MacroContextEngine, engine_context: Any
) -> None:
    features, context = both_macro_pairs(engine_context)
    result = engine.process(context, {"feature": features})
    data = dict(result.data)

    assert result.status is EngineStatus.OK
    assert data["available"] is True
    assert data["missing"] == []
    assert data["assets"] == ["btc", "eth"]

    for asset, pair in (("btc", BTC), ("eth", ETH)):
        row = features["pairs"][pair]
        for name in FEATURE_NAMES:
            assert data["features"][macro_column(asset, name)] == row[name], (asset, name)


def test_every_configured_column_is_present(
    engine: MacroContextEngine, engine_context: Any
) -> None:
    features, context = both_macro_pairs(engine_context)
    data = dict(engine.process(context, {"feature": features}).data)
    assert set(data["features"]) == set(macro_feature_names(["btc", "eth"]))


# --------------------------------------------------------------------------- #
# A missing asset
# --------------------------------------------------------------------------- #


def test_a_missing_macro_pair_is_named_and_its_columns_are_null_not_zero(
    engine: MacroContextEngine, engine_context: Any
) -> None:
    """Spec 65's named mutation, from the other side.

    Zeros would not fail anything. They would tell the predictor that Bitcoin did not
    move, on exactly the bars where the macro feed was broken, and a model would learn
    from it — which is this phase's whole failure mode: a wrong answer that is in range.
    """
    base = archive_bars(limit=260)
    features, context = feature_state(engine_context, pairs={BTC: base})

    result = engine.process(context, {"feature": features})
    data = dict(result.data)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert data["available"] is False
    assert data["missing"] == ["eth"]

    for name in FEATURE_NAMES:
        assert data["features"][macro_column("eth", name)] is None, name

    filled = [
        name
        for name in FEATURE_NAMES
        if data["features"][macro_column("btc", name)] is not None
    ]
    assert filled, "the BTC columns must still be published when ETH is missing"


def test_a_missing_asset_does_not_remove_its_columns(
    engine: MacroContextEngine, engine_context: Any
) -> None:
    """Absent would make a downstream feature-order check complain about the shape
    rather than about the data, and the artefact loader's message would name the wrong
    problem."""
    base = archive_bars(limit=260)
    features, context = feature_state(engine_context, pairs={BTC: base})
    data = dict(engine.process(context, {"feature": features}).data)
    assert set(data["features"]) == set(macro_feature_names(["btc", "eth"]))


def test_it_never_substitutes_a_previous_bars_macro_row(
    engine: MacroContextEngine, engine_context: Any
) -> None:
    """Two ticks, the second with ETH absent. The second must not carry the first's ETH
    values: that would be stale data presented as current, on the one input whose job is
    to say whether the whole market moved."""
    base = archive_bars(limit=260)
    shifted = [{**bar, "close": float(bar["close"]) * 1.1} for bar in base]

    with_eth, context = feature_state(engine_context, pairs={BTC: base, ETH: shifted})
    first = dict(engine.process(context, {"feature": with_eth}).data)
    assert first["available"] is True

    without_eth, context2 = feature_state(engine_context, pairs={BTC: base})
    second = dict(engine.process(context2, {"feature": without_eth}).data)

    assert second["available"] is False
    for name in FEATURE_NAMES:
        column = macro_column("eth", name)
        assert second["features"][column] is None, column


# --------------------------------------------------------------------------- #
# Cadence, refusals and what crosses `state`
# --------------------------------------------------------------------------- #


def test_no_bar_closed_is_a_pass(engine: MacroContextEngine, engine_context: Any) -> None:
    result = engine.process(engine_context, {})
    assert result.status is EngineStatus.PASS
    assert result.data == {}


def test_an_empty_macro_section_raises(
    engine: MacroContextEngine, engine_context: Any
) -> None:
    """A pair name nobody has set is not something to guess at, and a silent empty macro
    set would drop every macro column from the predictor's feature list."""
    features, context = both_macro_pairs(engine_context)

    class Blank:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def get(self, key: str) -> Any:
            return {} if key == KEY_MACRO else self._inner.get(key)

    import dataclasses

    blanked = dataclasses.replace(context, config=Blank(context.config))
    with pytest.raises(ValueError, match="is empty or is not a mapping"):
        engine.process(blanked, {"feature": features})


def test_the_payload_is_json_serialisable_with_no_nan(
    engine: MacroContextEngine, engine_context: Any
) -> None:
    features, context = both_macro_pairs(engine_context)
    data = dict(engine.process(context, {"feature": features}).data)
    encoded = json.dumps(data, allow_nan=False)
    assert "NaN" not in encoded
    MacroContextState.model_validate(data)


def test_it_never_blocks_trading(engine: MacroContextEngine, engine_context: Any) -> None:
    features, context = both_macro_pairs(engine_context)
    for state in ({"feature": features}, {}):
        result = engine.process(context, state)
        assert result.blocks_trading is False
    assert STATE_KEY == "macro_context"
