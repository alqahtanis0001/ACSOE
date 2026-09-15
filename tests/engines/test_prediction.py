"""Spec 71 — engine 8 `prediction`.

**Every artefact in this file is trained here, into a temporary root.** Never read from
`models/`, which is gitignored: a test that loaded one would pass only on the machine that
produced it, and on every other machine it would pass for the wrong reason — by blocking
with `prediction_unavailable`, which is a green test asserting nothing.

**Every `state` this engine reads is the real engines 3, 5 and 6's output**, per the Phase 3
ruling that no test hand-builds another engine's payload. Changing exactly one value inside
a payload the real engine produced is a controlled experiment rather than a fabricated
contract, and every place this file does it says so.

**The bars are the tail of the series the fixture model was trained on, not the archive
sample**, and that is the Dissimilarity Index rather than a convenience: real SOLUSD bars
scored by a model trained on the constructed series are refused at DI 1.024 against a
threshold of 1.023, which is the mechanism working. The passing path therefore runs on bars
from the training distribution and the refusal is induced deliberately, because a fixture
that blocked every candidate would leave every assertion past the DI unreachable.

The three refusals each get their own test asserting the **reason code**, not only the
status. A test that asserts `BLOCK` passes whichever of the three fired, and the three mean
different things to the operator: no model at all, a model with an incomplete input, and a
model declining to answer a question it was never trained on.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import require_module
from tests.engines.test_feature import BAR, FakeStream, sensor_payload

require_module("polars", reason="polars is not installed")
require_module("lightgbm", reason="lightgbm is not installed")
require_module("sklearn", reason="scikit-learn is not installed")

from acsoe.core.contracts import EngineStatus  # noqa: E402
from acsoe.engines.feature.engine import FeatureEngine  # noqa: E402
from acsoe.engines.macro_context.engine import MacroContextEngine  # noqa: E402
from acsoe.engines.market_sensor.contracts import STATE_KEY as SENSOR_KEY  # noqa: E402
from acsoe.engines.market_sensor.engine import MarketSensorEngine  # noqa: E402
from acsoe.engines.prediction.contracts import (  # noqa: E402
    KEY_DI_PERCENTILE,
    KEY_PREDICTION_RUN_ID,
    REASON_DI_PERCENTILE_MISMATCH,
    REASON_DI_REFUSED,
    REASON_INPUTS_INCOMPLETE,
    REASON_UNAVAILABLE,
    STATE_KEY,
)
from acsoe.engines.prediction.engine import PredictionEngine  # noqa: E402

PAIR = "AAAUSD"

#: Supplied to the trainer through a wrapper so the fixtures have a DI to refuse with.
#: **Not written into `config/default.yaml`**: absent is what engine 8 fails closed on and
#: what `di_fitted_on_predictor_training_set` reports PENDING for, and a number in the
#: committed config would be this lane deciding when a model may refuse a trade.
DI_PERCENTILE = 0.99

#: The dataset is built **with** macro columns, so the manifest names them and engines 8 and
#: 15 assemble the vector from two publishers the way they do live. Without this the macro
#: half of both engines is unreachable and every test passes anyway — found by a surviving
#: mutation in the spec 73 sweep.
#:
#: The macro asset is the candidate pair itself, which is not a shortcut: it is exactly the
#: macro self-identification case the lead ruled on (a BTC row whose `macro_btc_*` equals its
#: own features), left for Phase 5 and documented. It also keeps the macro values inside the
#: trained range, so the Dissimilarity Index still accepts the bar and everything past it
#: stays reachable — which zeros would not.
MACRO_ARCHIVE = {"btc": "AAAUSD"}


class Wrapped:
    """The committed config with named keys answered, and nothing else changed."""

    def __init__(self, inner: Any, **overrides: Any) -> None:
        self._inner = inner
        self._overrides = overrides

    def get(self, key: str) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        return self._inner.get(key)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


# --------------------------------------------------------------------------- #
# A trained artefact, and the state the engine reads
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def trained(tmp_path_factory: Any) -> tuple[Path, str, Any]:
    """One fold trained from the committed sample into a temporary artefact root.

    Module-scoped because it trains a real model: one fit shared by every test here, and
    the tests that need to break an artefact copy the directory rather than mutate it.
    """
    from tests.harness.doubles import load_default_config
    from tests.research.test_training import NOW, dataset_for

    from acsoe.research import training

    config = load_default_config()
    root = tmp_path_factory.mktemp("prediction-models")
    report = training.train_walkforward(
        dataset_for(config, random_walk=False, macro_archive=MACRO_ARCHIVE),
        config=Wrapped(config, **{"prediction.di_percentile": DI_PERCENTILE}),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=1,
    )
    run_id = report.fold_runs[0]
    assert (report.models_dir / run_id / "di.npz").is_file(), (
        "the fixture trained no DI, so every test below would exercise the block path"
    )
    return report.models_dir, run_id, report


@pytest.fixture
def artefact_root(trained: tuple[Path, str, Any]) -> Path:
    return trained[0]


@pytest.fixture
def run_id(trained: tuple[Path, str, Any]) -> str:
    return trained[1]


def context_with(engine_context: Any, models_dir: Path | None, **overrides: Any) -> Any:
    """`engine_context` with a store that knows an artefact root and a config that names a run.

    The store is B's real `StoreClient` pointed at the temporary root, not a fake: a fake
    `model_run_dir` would be a second implementation of the one method whose refusals this
    engine turns into blocks.
    """
    import dataclasses

    from acsoe.clients.store.client import StoreClient

    if models_dir is not None:
        # The database is never opened. Engine 8 asks the store for one thing — where a
        # run's artefacts live — and touches no table, so the path here is a name rather
        # than a migrated file. If that stops being true this fixture will say so by
        # failing to find a schema, which is the right way to find out.
        store = StoreClient(models_dir.parent / "acsoe.sqlite", models_dir=models_dir)
        object.__setattr__(engine_context.clients, "store", store)
    return dataclasses.replace(
        engine_context, config=Wrapped(engine_context.config, **overrides)
    )


def varied_trades(bars: list[dict[str, Any]], *, pair: str = PAIR) -> list[Any]:
    """A trade stream whose tick count per bar is **the bar's own `trades` field**.

    `tests/engines/test_feature.py` emits exactly four trades per bar — open, high, low,
    close — which rebuilds the bar exactly and is right for what that file tests. It also
    makes engine 3 publish a trade count of 4 on every bar, so `trades_z_n` is a z-score of
    a constant: zero over zero, NaN, on every bar and every window. Engine 8 then blocks
    every candidate with `prediction_inputs_incomplete` and the DI, the calibration and the
    expected move are never reached — a whole file green against a path that never ran.

    Taking the count from the bar rather than from the loop index also means a test can
    *change* it, which is what engine 13's spike test needs: a bar with ten times the trades
    has to reach the features as a bar with ten times the trades.

    The extra ticks are priced at the **close**, which leaves the bar identical: the open is
    still first, the close still last, and a price already inside the bar can be neither a
    new high nor a new low. The volume is split across however many ticks there are, with
    the remainder on the last, so the bar's volume is unchanged too.
    """
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from acsoe.clients.kraken.contracts import TradeTick

    out: list[Any] = []
    for bar in bars:
        ts = int(bar["ts"])
        count = max(int(bar.get("trades") or 4), 4)
        prices = [bar["open"], bar["high"], bar["low"], *([bar["close"]] * (count - 3))]
        volume = Decimal(str(bar["volume"]))
        part = (volume / len(prices)).quantize(Decimal("1e-12"))
        quantities = [part] * (len(prices) - 1) + [volume - part * (len(prices) - 1)]
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


def live_state(engine_context: Any, bars: list[dict[str, Any]]) -> tuple[dict[str, Any], Any]:
    """`state` as engines 3, 5, 6 and 7 actually produce it for one candidate."""
    _payload, _closed, context = sensor_payload(engine_context, bars, pair=PAIR)
    object.__setattr__(context.clients, "kraken", FakeStream(varied_trades(bars, pair=PAIR)))
    sensor = dict(MarketSensorEngine().process(context, {}).data)
    features = dict(FeatureEngine().process(context, {SENSOR_KEY: sensor}).data)
    macro = dict(
        MacroContextEngine().process(context, {SENSOR_KEY: sensor, "feature": features}).data
    )
    return (
        {"feature": features, "macro_context": macro, "scout": {"pair": PAIR}},
        context,
    )


@pytest.fixture(scope="module")
def bars() -> list[dict[str, Any]]:
    """The tail of **the same series the fixture model was trained on**.

    Not `archive_bars`, and the reason is the whole point of the DI rather than a fixture
    convenience. The model here is trained on the constructed 140-day series
    `tests/research/test_training.py` builds; real SOLUSD bars from the archive are, to a
    model that has never seen them, exactly the market the Dissimilarity Index exists to
    refuse — measured at DI 1.024 against a threshold of 1.023, which is the mechanism
    working and not a bug.

    So the passing path is exercised on bars drawn from the training distribution, and the
    refusal is exercised deliberately by moving features outside it. A fixture that scored
    out-of-distribution bars would block every candidate and every assertion past the DI
    would be unreachable.
    """
    from tests.research.test_training import candle_frame

    frame = candle_frame(PAIR, interval_s=BAR, random_walk=False, days=140)
    return [
        {
            "ts": int(row["ts"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "trades": int(row["trades"]),
        }
        for row in frame.tail(300).to_dicts()
    ]


def complete_state(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str
) -> tuple[dict[str, Any], Any]:
    """A state whose feature vector is complete, with the manifest's own macro columns.

    Engine 6 publishes macro columns only for the assets it could reach, and the committed
    sample has none of them, so the values are supplied here from the manifest's feature
    list. **That is the one fabricated part of this fixture** and it is named: without it
    every test would block with `prediction_inputs_incomplete` and the DI, the calibration
    and the expected move would never run at all.
    """
    state, context = live_state(engine_context, bars)
    manifest = json.loads(
        (artefact_root / run_id / "manifest.json").read_bytes().decode("utf-8")
    )
    row = state["feature"]["pairs"][PAIR]
    macro: dict[str, Any] = {}
    for name in manifest["feature_names"]:
        if not name.startswith("macro_") or name in row:
            continue
        # `macro_<asset>_<feature>` back to `<feature>`, and the value is this pair's own —
        # which is what the artefact was trained on, because the fixture's macro asset is the
        # pair itself. Engine 6 publishes the same shape live from the real macro pair.
        stem = name.split("_", 2)[2]
        macro[name] = row.get(stem)
    assert macro, (
        "the fixture trained with no macro columns, so the macro half of engines 8 and 15 "
        "is unreachable and every assertion past it proves nothing"
    )
    state["macro_context"] = {**state["macro_context"], "features": macro}
    return state, context


def run(engine: PredictionEngine, context: Any, state: dict[str, Any]) -> Any:
    return engine.process(context, state)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table() -> None:
    engine = PredictionEngine()
    assert engine.name == "prediction"
    assert engine.number == 8
    assert engine.is_gate is False


def test_it_is_not_a_gate_and_blocks_anyway() -> None:
    """Spec 59 decision 3, and the reason the two are not a contradiction.

    `is_gate` is the declaration `verify.py` checks against the Gate column of
    `engine-contracts.md`; contract rule 6 lets any engine return `BLOCK`. Making this a
    gate would put a model output in a policy gate's position, which invariant 4 forbids.
    """
    assert PredictionEngine.is_gate is False


# --------------------------------------------------------------------------- #
# The three refusals, each by its own reason code
# --------------------------------------------------------------------------- #


def test_with_no_run_id_configured_it_blocks_with_prediction_unavailable(
    engine_context: Any, bars: list[dict[str, Any]]
) -> None:
    """Invariant 3 on a fresh clone, which is the state this repository is actually in.

    `models.prediction_run_id` is absent from `config/default.yaml` by ruling and there is
    no `models/` directory at all. The system refusing to trade is correct behaviour, not
    an error to work around.
    """
    from tests.harness.doubles import load_default_config

    assert load_default_config().get(KEY_PREDICTION_RUN_ID) is None
    state, context = live_state(engine_context, bars)
    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert KEY_PREDICTION_RUN_ID in (result.reason or "")


def test_with_a_run_id_pointing_nowhere_it_blocks_with_prediction_unavailable(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path
) -> None:
    """The store's own refusal, turned into a block rather than allowed to raise."""
    state, context = live_state(engine_context, bars)
    context = context_with(
        context, artefact_root, **{KEY_PREDICTION_RUN_ID: "train-nothing-ever-wrote-this"}
    )
    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE


def test_a_tampered_artefact_blocks_rather_than_predicting_from_it(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str,
    tmp_path: Path
) -> None:
    """A failed hash is `prediction_unavailable`, not a warning and not a degraded load.

    The directory is copied first: the module-scoped fixture is shared, and a test that
    corrupted it would make every test after it fail for a reason belonging to this one.
    """
    root = tmp_path / "models"
    shutil.copytree(artefact_root, root)
    target = root / run_id / "model.txt"
    target.write_bytes(target.read_bytes() + b"\n")

    state, context = live_state(engine_context, bars)
    context = context_with(context, root, **{KEY_PREDICTION_RUN_ID: run_id})
    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert "model.txt" in (result.reason or "")


def test_an_artefact_with_no_di_blocks_rather_than_predicting_unguarded(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str,
    tmp_path: Path
) -> None:
    """A run trained while `prediction.di_percentile` was absent carries no `di.npz`.

    Engine 8 will not predict without the refusal it exists to make. Predicting anyway
    would be the whole spec 68 guarantee quietly removed by a config key nobody set: every
    number would look ordinary and the model would be extrapolating on markets it has never
    seen.
    """
    from acsoe.modelling.artefacts import MANIFEST_NAME

    root = tmp_path / "models"
    shutil.copytree(artefact_root, root)
    (root / run_id / "di.npz").unlink()
    # The manifest hashes every file in the directory, so a removed file is a refusal for
    # a different reason. Rewritten without its entry, so the DI's absence is what is
    # actually being tested.
    manifest_path = root / run_id / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    manifest["files"].pop("di.npz", None)
    manifest_path.write_bytes(json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"))

    state, context = live_state(engine_context, bars)
    context = context_with(context, root, **{KEY_PREDICTION_RUN_ID: run_id})
    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert "di.npz" in (result.reason or "")


def test_a_di_fitted_without_the_exclusion_span_blocks_rather_than_loading(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str,
    tmp_path: Path
) -> None:
    """A `di.npz` written before the ruling of 2026-09-15 records no `exclusion_s`.

    Its threshold was taken over a leave-one-out that kept every same-moment neighbour, so
    it measures time proximity and refuses nearly every candidate — or, read with a default
    span, would claim a refusal line it was never fitted at. `modelling.di.load` refuses it,
    and the refusal is `prediction_unavailable` rather than an `ERROR` escaping the engine.
    """
    import numpy as np

    from acsoe.modelling.artefacts import MANIFEST_NAME, sha256_file

    root = tmp_path / "models"
    shutil.copytree(artefact_root, root)
    di_path = root / run_id / "di.npz"
    with np.load(di_path) as payload:
        legacy = {
            name: payload[name]
            for name in payload.files
            if name not in {"exclusion_s", "decision_ts"}
        }
    np.savez_compressed(di_path, **legacy)
    # Re-hashed, so the manifest's integrity check passes and the missing span is what is
    # actually being refused rather than a changed file.
    manifest_path = root / run_id / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    manifest["files"]["di.npz"] = sha256_file(di_path)
    manifest_path.write_bytes(json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"))

    state, context = live_state(engine_context, bars)
    context = context_with(context, root, **{KEY_PREDICTION_RUN_ID: run_id})
    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert "exclusion_s" in (result.reason or "")
    assert "time proximity" in (result.reason or "")


def test_a_null_feature_blocks_with_prediction_inputs_incomplete(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str
) -> None:
    """One value changed inside a payload the real engine 5 produced.

    The message names the feature, because "some input was missing" sends an operator to
    read forty columns.
    """
    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    context = context_with(context, artefact_root, **{KEY_PREDICTION_RUN_ID: run_id})
    row = dict(state["feature"]["pairs"][PAIR])
    name = next(key for key in row if key.startswith("log_return_"))
    row[name] = None
    state["feature"] = {
        **state["feature"],
        "pairs": {**state["feature"]["pairs"], PAIR: row},
    }

    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_INPUTS_INCOMPLETE
    assert name in (result.reason or "")
    assert result.engine == STATE_KEY


def test_a_nan_feature_is_treated_as_missing_rather_than_scored(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str
) -> None:
    """A NaN is not a value. Scaled it stays NaN, and `modelling.di` refuses to score one
    by raising — which would be an `ERROR` where a `BLOCK` is the honest answer."""
    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    context = context_with(context, artefact_root, **{KEY_PREDICTION_RUN_ID: run_id})
    row = dict(state["feature"]["pairs"][PAIR])
    name = next(key for key in row if key.startswith("log_return_"))
    row[name] = float("nan")
    state["feature"] = {
        **state["feature"],
        "pairs": {**state["feature"]["pairs"], PAIR: row},
    }

    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_INPUTS_INCOMPLETE


def test_a_dissimilar_market_blocks_with_di_refused_and_publishes_no_expected_move(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str
) -> None:
    """Spec 71's third refusal, and the one that says nothing is broken.

    The candidate is made dissimilar by moving one feature far outside the training range,
    which is what an unprecedented market does to a feature vector. The assertion that
    matters as much as the code is the **absent** `expected_move_pct`: engine 10 fails
    closed on a key that is not there.
    """
    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    context = context_with(context, artefact_root, **{KEY_PREDICTION_RUN_ID: run_id})
    row = dict(state["feature"]["pairs"][PAIR])
    for name in row:
        if name.startswith(("log_return_", "realised_vol_", "volume_z_")):
            row[name] = 500.0
    state["feature"] = {
        **state["feature"],
        "pairs": {**state["feature"]["pairs"], PAIR: row},
    }

    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_DI_REFUSED
    assert "expected_move_pct" not in result.data
    assert result.data["di"] is not None
    assert result.data["di_threshold"] is not None
    assert result.data["di"] > result.data["di_threshold"]


def test_a_configured_di_percentile_that_is_not_the_artefacts_blocks(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str
) -> None:
    """Ruled 2026-09-13 after B-2's rehearsal of engines 13 and 8.

    **The DI threshold is baked into `di.npz`** and this engine never computes one, so once a
    run is trained at some percentile, editing `prediction.di_percentile` changes nothing the
    running system does. Without this block the engine goes on refusing at the percentile it
    was trained on while the config claims another, and the operator reads a number that is
    not in use — which is the quietest possible way for a safety threshold to be wrong.

    The reason names **both** numbers, because "they disagree" without saying which is which
    leaves the operator unable to tell whether to retrain or to change the key back.
    """
    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    context = context_with(
        context,
        artefact_root,
        **{KEY_PREDICTION_RUN_ID: run_id, KEY_DI_PERCENTILE: DI_PERCENTILE - 0.04},
    )
    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_DI_PERCENTILE_MISMATCH
    assert "0.95" in (result.reason or "")
    assert str(DI_PERCENTILE) in (result.reason or "")
    assert "expected_move_pct" not in result.data


def test_a_configured_di_percentile_that_matches_the_artefact_predicts(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str
) -> None:
    """The pass half, one number apart from the block above.

    Without it the check is satisfied by an engine that blocks whenever the key is set at all,
    which would make supplying the operator's own threshold the thing that stops trading.
    """
    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    context = context_with(
        context,
        artefact_root,
        **{KEY_PREDICTION_RUN_ID: run_id, KEY_DI_PERCENTILE: DI_PERCENTILE},
    )
    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.OK, (result.data.get("reason_code"), result.reason)
    assert "expected_move_pct" in result.data


def test_with_the_percentile_absent_the_artefacts_own_stands(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str
) -> None:
    """Absent is **not** a disagreement.

    It means the operator has not chosen, so the artefact's own percentile stands
    unquestioned and the engine behaves exactly as it did before this check existed.

    **The absence is supplied here, not inherited.** It was the committed state until
    2026-09-15, when the operator ruled `prediction.di_percentile: 0.99`. Left inherited,
    this test would have started comparing the artefact's percentile against a real config
    value — which is the *mismatch* branch, the opposite of what it is named for — and it
    would have gone on passing whenever the two happened to agree.
    """
    from tests.harness.doubles import load_default_config

    assert load_default_config().get(KEY_DI_PERCENTILE) is not None, (
        "the operator's DI percentile is absent from config/default.yaml. This test "
        "supplies the absent case itself, so an absent key here means the ruled value "
        "has been lost rather than that this test is stale."
    )
    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    context = context_with(
        context, artefact_root, **{KEY_PREDICTION_RUN_ID: run_id, KEY_DI_PERCENTILE: None}
    )
    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.OK, (result.data.get("reason_code"), result.reason)


# --------------------------------------------------------------------------- #
# The prediction itself
# --------------------------------------------------------------------------- #


@pytest.fixture
def predicted(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str
) -> Any:
    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    context = context_with(context, artefact_root, **{KEY_PREDICTION_RUN_ID: run_id})
    result = run(PredictionEngine(), context, state)
    assert result.status is EngineStatus.OK, (result.data.get("reason_code"), result.reason)
    return result


def test_a_candidate_the_di_accepts_is_predicted(predicted: Any) -> None:
    """The control. Without a passing case every refusal above is satisfied by an engine
    that refuses everything, which is a very safe system that never trades."""
    assert predicted.status is EngineStatus.OK
    assert predicted.blocks_trading is False
    assert predicted.data["reason_code"] is None


def test_the_three_probabilities_are_a_distribution(predicted: Any) -> None:
    """Calibrated per class and renormalised. Three independently calibrated probabilities
    do not sum to one, and an unrenormalised set rescales every expected move by an unknown
    factor — the ranking between candidates survives it, so the BUY boundary moves while
    everything still looks internally consistent."""
    values = [
        predicted.data["p_target"],
        predicted.data["p_stop"],
        predicted.data["p_timeout"],
    ]
    assert all(0.0 <= value <= 1.0 for value in values), values
    assert sum(values) == pytest.approx(1.0, abs=1e-9)


def test_the_expected_move_crosses_as_an_exact_decimal_string(predicted: Any) -> None:
    """Engine 10 does `Decimal` arithmetic with this key. A float crossing the boundary
    would be rounded twice, once on each side, and the two roundings would not agree."""
    from decimal import Decimal

    raw = predicted.data["expected_move_pct"]
    assert isinstance(raw, str), type(raw)
    assert Decimal(raw) == Decimal(raw)  # parses, and parses exactly
    assert "e" not in raw.lower(), (
        "the expected move is in scientific notation, which `Decimal` reads but a human "
        "reading a log does not: " + raw
    )


def test_the_published_payload_is_json_serialisable(predicted: Any) -> None:
    """Contract rule 8, and the one an engine publishing numpy floats fails silently until
    something tries to write the state."""
    json.dumps(predicted.data)


def test_it_publishes_the_run_id_and_the_feature_version_it_predicted_with(
    predicted: Any, run_id: str
) -> None:
    """Which model produced this number is part of the number. Phase 7's SHAP view and the
    leaderboard both join on it, and a prediction that does not say which run made it is
    not reproducible from the config plus the data."""
    assert predicted.data["model_run_id"] == run_id
    assert predicted.data["feature_version"] == "f1"


def test_the_attributions_name_the_manifests_features(predicted: Any, artefact_root: Path,
                                                      run_id: str) -> None:
    """`data["shap"]` is `{feature: float}` over the model's own feature list.

    Empty is allowed — an explainer that fails does not turn a good prediction into a block
    — but a non-empty mapping keyed on anything other than the manifest's features would be
    attributing the decision to columns the model does not have.
    """
    shap_values = predicted.data["shap"]
    assert isinstance(shap_values, dict)
    if shap_values:
        manifest = json.loads(
            (artefact_root / run_id / "manifest.json").read_bytes().decode("utf-8")
        )
        assert list(shap_values) == list(manifest["feature_names"])
        assert all(isinstance(value, float) for value in shap_values.values())


# --------------------------------------------------------------------------- #
# The order of the vector, and the order of the two model steps
# --------------------------------------------------------------------------- #


def test_the_vector_is_built_in_the_manifests_order_not_the_state_rows(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str
) -> None:
    """The same features, published in a different order, must predict identically.

    A mapping has no order that means anything, and an engine that built its vector by
    iterating the published row would hand the model whichever order engine 5 happened to
    serialise: every value in range, every value in the wrong column, and nothing anywhere
    to notice. This is the assertion that makes that impossible to write.
    """
    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    context = context_with(context, artefact_root, **{KEY_PREDICTION_RUN_ID: run_id})
    first = run(PredictionEngine(), context, state)

    row = state["feature"]["pairs"][PAIR]
    reversed_row = dict(reversed(list(row.items())))
    assert list(reversed_row) != list(row), "the row has one key, so the reversal proves nothing"
    shuffled = {
        **state,
        "feature": {
            **state["feature"],
            "pairs": {**state["feature"]["pairs"], PAIR: reversed_row},
        },
        "macro_context": {
            **state["macro_context"],
            "features": dict(reversed(list(state["macro_context"]["features"].items()))),
        },
    }
    second = run(PredictionEngine(), context, shuffled)

    assert first.status is EngineStatus.OK and second.status is EngineStatus.OK
    assert first.data["p_target"] == second.data["p_target"]
    assert first.data["expected_move_pct"] == second.data["expected_move_pct"]
    assert first.data["di"] == second.data["di"]


def test_the_di_is_scored_before_the_prediction(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str,
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 71's named mutation, asserted by observation rather than by reading the source.

    Predict-then-veto produces the same `BLOCK` with the same reason code, so no assertion
    about the *result* can tell the two apart. The booster's `predict` is watched instead:
    on a refused candidate it must never be called at all. A prediction made on a market
    unlike anything in training is not a weak prediction — it is a confident number produced
    by extrapolation, and one that was computed is one something downstream can reach.
    """
    import lightgbm as lgb

    calls: list[int] = []
    original = lgb.Booster.predict

    def watched(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(lgb.Booster, "predict", watched)

    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    context = context_with(context, artefact_root, **{KEY_PREDICTION_RUN_ID: run_id})
    row = dict(state["feature"]["pairs"][PAIR])
    for name in row:
        if name.startswith(("log_return_", "realised_vol_", "volume_z_")):
            row[name] = 500.0
    state["feature"] = {
        **state["feature"],
        "pairs": {**state["feature"]["pairs"], PAIR: row},
    }

    result = run(PredictionEngine(), context, state)
    assert result.data["reason_code"] == REASON_DI_REFUSED
    assert calls == [], (
        "the model was asked for a prediction on a candidate the DI refused. The refusal "
        "must come first: a number computed here is a number something downstream can "
        "reach, and it is an extrapolation rather than a weak prediction."
    )


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def test_nothing_is_loaded_and_nothing_trains_at_import() -> None:
    """Spec 71's scope limit. A model loaded at import makes the process refuse to start on
    a machine with no artefacts, where invariant 3 says it must start and block."""
    engine = PredictionEngine()
    assert engine._artefact is None


def test_a_changed_run_id_reloads_rather_than_serving_the_old_model(
    engine_context: Any, bars: list[dict[str, Any]], artefact_root: Path, run_id: str,
    tmp_path: Path
) -> None:
    """The failure the cache would otherwise introduce, which is silent.

    The artefact is held between ticks because loading hashes every file in the directory.
    Keyed by run id, so pointing the config at a second run loads the second run — an
    engine that cached on first use alone would serve the old model under the new id and
    every number would look ordinary.
    """
    second_root = tmp_path / "second"
    shutil.copytree(artefact_root, second_root)
    renamed = second_root / (run_id + "-b")
    (second_root / run_id).rename(renamed)

    state, context = complete_state(engine_context, bars, artefact_root, run_id)
    engine = PredictionEngine()

    first = run(engine, context_with(context, artefact_root,
                                     **{KEY_PREDICTION_RUN_ID: run_id}), state)
    assert first.data["model_run_id"] == run_id

    second = run(engine, context_with(context, second_root,
                                      **{KEY_PREDICTION_RUN_ID: renamed.name}), state)
    assert second.data["model_run_id"] == renamed.name
    assert engine._artefact is not None
    assert engine._artefact.run_id == renamed.name


def test_with_no_candidate_it_passes_rather_than_blocking(engine_context: Any) -> None:
    """Nothing qualified this tick. Engine 7 already returned `PASS` and the chain stopped;
    there is no candidate to refuse, and a `BLOCK` here would record a refusal that never
    happened in the one table the research reads."""
    result = run(PredictionEngine(), engine_context, {"scout": {}})
    assert result.status is EngineStatus.PASS
    assert result.blocks_trading is False
    assert result.data == {}
