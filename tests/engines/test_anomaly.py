"""Spec 72 — engine 13 `anomaly`.

A data-quality gate: is the candidate's **market** broken. Not whether the trade is good, and
the tests below are mostly about that distinction, because it is the one that would be lost
silently. A gate that quietly began reading the prediction would still block and pass at
plausible rates, and the only thing separating the two is which keys it names.

Every artefact here is trained into a temporary root from the constructed series, never read
from `models/`, which is gitignored: a test that loaded one would pass on the machine that
produced it and pass for the wrong reason everywhere else — by blocking with
`anomaly_unavailable`, which is a green test asserting nothing.

The block and the pass **differ in one input**, which spec 72 asks for in as many words. Two
independently drawn bars differ in every feature, so a gate scoring them correctly for the
wrong reason would pass.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import require_module
from tests.engines.test_prediction import (
    DI_PERCENTILE,
    PAIR,
    Wrapped,
    bars,  # noqa: F401 - a fixture, used by name
    context_with,
    live_state,
)

require_module("polars", reason="polars is not installed")
require_module("lightgbm", reason="lightgbm is not installed")
require_module("sklearn", reason="scikit-learn is not installed")
joblib = require_module("joblib", reason="joblib is not installed")

from acsoe.core.contracts import EngineStatus  # noqa: E402
from acsoe.engines.anomaly.contracts import (  # noqa: E402
    KEY_ANOMALY_RUN_ID,
    REASON_INPUTS_INCOMPLETE,
    REASON_MARKET_ANOMALOUS,
    REASON_UNAVAILABLE,
)
from acsoe.engines.anomaly.engine import AnomalyEngine  # noqa: E402
from acsoe.modelling.features import MARKET_QUALITY_FEATURES  # noqa: E402

#: Supplied through a wrapper, never written into `config/default.yaml`. Absent is what this
#: gate fails closed on. Low enough that the constructed bars sit below it and a spiked one
#: sits above: at 0.99 a ten-sigma volume spike is **not** blocked, which is the finding in
#: the build log for 2026-09-13 and is the operator's to act on rather than this file's to
#: paper over.
THRESHOLD_PERCENTILE = 0.85


@pytest.fixture(scope="module")
def trained_anomaly(tmp_path_factory: Any) -> tuple[Path, str]:
    from tests.harness.doubles import load_default_config
    from tests.research.test_training import NOW, dataset_for

    from acsoe.research import training

    config = load_default_config()
    root = tmp_path_factory.mktemp("anomaly-models")
    report = training.train_walkforward(
        dataset_for(config, random_walk=False),
        config=Wrapped(
            config,
            **{
                "anomaly.threshold_percentile": THRESHOLD_PERCENTILE,
                "prediction.di_percentile": DI_PERCENTILE,
            },
        ),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=1,
    )
    run_id = report.fold_runs[0]
    assert (report.models_dir / run_id / "anomaly.joblib").is_file(), (
        "the fixture fitted no detector, so every test below would exercise the block path"
    )
    return report.models_dir, run_id


@pytest.fixture
def root(trained_anomaly: tuple[Path, str]) -> Path:
    return trained_anomaly[0]


@pytest.fixture
def run_id(trained_anomaly: tuple[Path, str]) -> str:
    return trained_anomaly[1]


def scored(
    engine_context: Any, bar_rows: list[dict[str, Any]], root: Path, run_id: str,
    overrides: dict[str, Any] | None = None
) -> Any:
    state, context = live_state(engine_context, bar_rows)
    context = context_with(context, root, **{KEY_ANOMALY_RUN_ID: run_id, **(overrides or {})})
    return AnomalyEngine().process(context, state)


def with_one_feature(state: dict[str, Any], name: str, value: Any) -> dict[str, Any]:
    row = {**state["feature"]["pairs"][PAIR], name: value}
    return {
        **state,
        "feature": {**state["feature"], "pairs": {**state["feature"]["pairs"], PAIR: row}},
    }


# --------------------------------------------------------------------------- #
# Registry, and what it cannot see
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table() -> None:
    engine = AnomalyEngine()
    assert engine.name == "anomaly"
    assert engine.number == 13
    assert engine.is_gate is True


def test_it_names_no_key_belonging_to_the_prediction() -> None:
    """Invariant 4, asserted structurally rather than by reading the engine's behaviour.

    Contract rule 3 means an engine reaches another engine's keys only by naming them in its
    contracts module. So a gate that cannot form an opinion about the trade is a gate whose
    contracts module contains no name for one — and that is checkable, where "it does not
    use the prediction" is not.
    """
    import inspect

    from acsoe.engines.anomaly import contracts

    source = inspect.getsource(contracts)
    for forbidden in ("prediction", "p_target", "expected_move", "is_buy", "skeptic"):
        for line in source.splitlines():
            if line.lstrip().startswith(("#", '"', "'")) or "=" not in line:
                continue
            assert forbidden not in line.split("=", 1)[1], (forbidden, line)


def test_no_input_is_a_spread(run_id: str, root: Path) -> None:
    """The archive is OHLCVT and the detector was never fitted on a book. A live spread
    scored here would be a column the model has never seen."""
    manifest = json.loads((root / run_id / "manifest.json").read_bytes().decode("utf-8"))
    recorded = manifest["extras"]["anomaly"]
    assert set(recorded["input_names"]) == set(MARKET_QUALITY_FEATURES)
    for name in recorded["input_names"]:
        for word in ("spread", "bid", "ask", "depth", "book"):
            assert word not in name, name
    assert "absent" in recorded["spread_input"]


# --------------------------------------------------------------------------- #
# The unavailable shapes, each by its reason code
# --------------------------------------------------------------------------- #


def test_with_no_run_id_configured_it_blocks_with_anomaly_unavailable(
    engine_context: Any, bars: list[dict[str, Any]]  # noqa: F811
) -> None:
    from tests.harness.doubles import load_default_config

    assert load_default_config().get(KEY_ANOMALY_RUN_ID) is None
    state, context = live_state(engine_context, bars)
    result = AnomalyEngine().process(context, state)
    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert KEY_ANOMALY_RUN_ID in (result.reason or "")


def test_with_a_run_id_pointing_nowhere_it_blocks_with_anomaly_unavailable(
    engine_context: Any, bars: list[dict[str, Any]], root: Path  # noqa: F811
) -> None:
    result = scored(engine_context, bars, root, "train-nothing-ever-wrote-this")
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE


def test_a_tampered_artefact_blocks_rather_than_scoring_from_it(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    tmp_path: Path
) -> None:
    """The hash is the only thing standing between a pickled model and whatever replaced it.
    A manifest recording a digest nothing checks is a comment."""
    copy = tmp_path / "models"
    shutil.copytree(root, copy)
    target = copy / run_id / "anomaly.joblib"
    target.write_bytes(target.read_bytes() + b"\x00")

    result = scored(engine_context, bars, copy, run_id)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert "anomaly.joblib" in (result.reason or "")


def test_an_artefact_with_no_threshold_blocks_rather_than_inventing_one(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    tmp_path: Path
) -> None:
    """A run trained while `anomaly.threshold_percentile` was absent records `threshold:
    null`, and that key is the operator's. Nothing here invents the number that decides when
    a market is broken."""
    from acsoe.modelling.artefacts import MANIFEST_NAME, sha256_file

    copy = tmp_path / "models"
    shutil.copytree(root, copy)
    manifest_path = copy / run_id / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    manifest["extras"]["anomaly"]["threshold"] = None
    manifest_path.write_bytes(json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"))
    # The manifest is not hashed by itself, so editing it does not trip the file check —
    # asserted here so a reader does not have to wonder which refusal fired.
    assert sha256_file(copy / run_id / "anomaly.joblib") == manifest["files"]["anomaly.joblib"]

    result = scored(engine_context, bars, copy, run_id)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_UNAVAILABLE
    assert "threshold" in (result.reason or "")


def test_a_null_market_feature_blocks_with_anomaly_inputs_incomplete(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """One value changed inside a payload the real engine 5 produced. A gate that scored a
    partial vector would be reporting the feature pipeline's gaps as a healthy market."""
    state, context = live_state(engine_context, bars)
    context = context_with(context, root, **{KEY_ANOMALY_RUN_ID: run_id})
    name = MARKET_QUALITY_FEATURES[0]
    result = AnomalyEngine().process(context, with_one_feature(state, name, None))
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_INPUTS_INCOMPLETE
    assert name in (result.reason or "")


# --------------------------------------------------------------------------- #
# The block and the pass, one input apart
# --------------------------------------------------------------------------- #


def test_an_ordinary_bar_passes(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """The control, and the half that stops every assertion above being satisfied by a gate
    that refuses everything — which is a very safe system that never trades."""
    result = scored(engine_context, bars, root, run_id)
    assert result.status is EngineStatus.OK, (result.data.get("reason_code"), result.reason)
    assert result.blocks_trading is False
    assert result.data["anomalous"] is False
    assert result.data["score"] <= result.data["threshold"]
    assert result.data["model_run_id"] == run_id


def spiked_bars(bar_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The same bars with **one thing about the market** changed: the last bar's volume.

    Ten sigma of the series' own volume, with the trade count raised in step, injected into
    the **candles** so the real engines 3 and 5 compute what it does to the features. Not
    written into a feature column, and the difference is not pedantry — it is the only form
    of "one input" this gate can be tripped by.

    Measured on 2026-09-13: moving any **single** market-quality column a thousand scaled
    units outside its training range moves the score from 0.5125 to at most 0.5415, against
    a 0.85-percentile threshold of 0.5491. Seven of the twenty-one columns move it by exactly
    nothing, because they are constant across the training window and a random split has no
    range to fall inside. An isolation forest over twenty-one features is a multi-column
    instrument: it sees a market that has gone strange in several ways at once and is nearly
    blind to one channel breaking. A real volume spike propagates into eight columns, which
    is what makes it visible at all.
    """
    spiked = [dict(row) for row in bar_rows]
    volumes = [float(row["volume"]) for row in bar_rows]
    mean = sum(volumes) / len(volumes)
    variance = sum((value - mean) ** 2 for value in volumes) / max(len(volumes) - 1, 1)
    sigma = variance**0.5
    spiked[-1]["volume"] = mean + 10.0 * sigma
    spiked[-1]["trades"] = int(spiked[-1]["trades"]) * 10
    return spiked


def with_threshold_between(
    root: Path, run_id: str, destination: Path, low: float, high: float
) -> Path:
    """A copy of the artefact whose recorded threshold sits midway between two scores.

    **Set by the fixture rather than reached by choosing a percentile, and that is the
    honest construction.** What is under test here is engine 13's *comparison* — does a
    score above the artefact's threshold block, and does one below it pass — which is engine
    13's responsibility. The detector's *separation* is not: measured on 2026-09-13, a bar
    carrying ten sigma of volume and ten times the trades scores 0.5263 against an ordinary
    bar's 0.5210, so the threshold percentile that separates them is about 0.63, where the
    gate would also refuse 37% of ordinary bars. Training the fixture at 0.63 and calling it
    an operating point would be this file quietly agreeing that such a gate is fine.

    The manifest is not itself hashed — every *other* file in the directory is — so this
    edit does not trip the artefact check, which `test_an_artefact_with_no_threshold...`
    asserts rather than assumes.
    """
    from acsoe.modelling.artefacts import MANIFEST_NAME

    shutil.copytree(root, destination)
    manifest_path = destination / run_id / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    manifest["extras"]["anomaly"]["threshold"] = (low + high) / 2.0
    manifest_path.write_bytes(json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"))
    return destination


def test_a_ten_sigma_volume_spike_blocks_and_the_bar_beside_it_does_not(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    tmp_path: Path
) -> None:
    """Spec 72's block-and-pass pair, differing in one thing about the market.

    One input in the sense a reader means it: the bar's volume and trade count, injected
    into the candle stream so the real engines 3 and 5 compute what it does to the features.
    It reaches them — `volume_z_96` moves from about 1.5 to about 6.9 — and the detector's
    score moves by five thousandths, which is the finding in the build log rather than
    anything this test can fix.

    So the threshold is placed between the two measured scores by the fixture, and what this
    asserts is that engine 13 compares in the right direction and says the right things when
    it does. The reason carries the score and the threshold, because "the market looks
    broken" with no numbers is a sentence an operator cannot check against anything.
    """
    plain = scored(engine_context, bars, root, run_id)
    spiked = scored(engine_context, spiked_bars(bars), root, run_id)
    assert spiked.data["score"] > plain.data["score"], (
        "a bar carrying ten sigma of volume and ten times the trades did not score as more "
        "anomalous than the bar beside it. That is the one thing about the detector this "
        "gate depends on."
    )

    separated = with_threshold_between(
        root, run_id, tmp_path / "models", plain.data["score"], spiked.data["score"]
    )
    ordinary = scored(engine_context, bars, separated, run_id)
    assert ordinary.status is EngineStatus.OK, (ordinary.data, ordinary.reason)
    assert ordinary.data["anomalous"] is False

    broken = scored(engine_context, spiked_bars(bars), separated, run_id)
    assert broken.status is EngineStatus.BLOCK, (broken.data, broken.reason)
    assert broken.blocks_trading is True
    assert broken.data["reason_code"] == REASON_MARKET_ANOMALOUS
    assert broken.data["anomalous"] is True
    assert broken.data["score"] > broken.data["threshold"]
    assert f"{broken.data['score']:.4f}" in (broken.reason or "")
    assert f"{broken.data['threshold']:.4f}" in (broken.reason or "")


def test_a_score_exactly_on_the_threshold_passes(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    tmp_path: Path
) -> None:
    """The boundary, in the same direction every other gate in this system rounds: the
    threshold is the last acceptable value, not the first refused one.

    Worth an assertion of its own because the two comparisons differ by one character and
    the difference shows up only on the one bar that lands exactly on the line.
    """
    plain = scored(engine_context, bars, root, run_id)
    exact = with_threshold_between(
        root, run_id, tmp_path / "models", plain.data["score"], plain.data["score"]
    )
    result = scored(engine_context, bars, exact, run_id)
    assert result.data["score"] == pytest.approx(result.data["threshold"], abs=1e-12)
    assert result.status is EngineStatus.OK


def test_the_gate_can_only_veto(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """Invariant 4. There is no output of this engine that makes a trade more likely: it
    either passes a candidate through unchanged or it blocks. No score, no confidence and no
    margin that anything downstream could widen a threshold with."""
    result = scored(engine_context, bars, root, run_id)
    assert set(result.data) == {
        "pair",
        "bar_ts",
        "model_run_id",
        "score",
        "threshold",
        "anomalous",
        "reason_code",
    }


def test_the_published_payload_is_json_serialisable(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    json.dumps(scored(engine_context, bars, root, run_id).data)


def test_with_no_candidate_it_passes_rather_than_blocking(engine_context: Any) -> None:
    result = AnomalyEngine().process(engine_context, {"scout": {}})
    assert result.status is EngineStatus.PASS
    assert result.blocks_trading is False


# --------------------------------------------------------------------------- #
# The score's direction, which no result can reveal on its own
# --------------------------------------------------------------------------- #


def test_larger_means_more_anomalous_in_the_same_direction_the_trainer_recorded(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str  # noqa: F811
) -> None:
    """The engine's score, recomputed here from the artefact, in the trainer's orientation.

    A sign that flipped between `research/training.py` and this engine would produce a gate
    that blocks exactly the ordinary markets and passes the broken ones, at a refusal rate
    that looks entirely reasonable — and every other test in this file would still pass,
    because they compare the engine against itself.
    """
    import numpy as np

    from acsoe.modelling.artefacts import load_run

    state, context = live_state(engine_context, bars)
    context = context_with(context, root, **{KEY_ANOMALY_RUN_ID: run_id})
    result = AnomalyEngine().process(context, state)
    assert result.status is EngineStatus.OK

    manifest = json.loads((root / run_id / "manifest.json").read_bytes().decode("utf-8"))
    names = list(manifest["extras"]["anomaly"]["input_names"])
    loaded = load_run(root / run_id, expected_features=tuple(manifest["feature_names"]))
    model = joblib.load(root / run_id / "anomaly.joblib")

    row = state["feature"]["pairs"][PAIR]
    vector = [[float(row[name]) for name in names]]
    scaled = loaded.scaler.subset(names).transform(vector)
    expected = float(-model.score_samples(np.asarray(scaled, dtype=np.float64))[0])

    assert result.data["score"] == pytest.approx(expected, abs=1e-12)
    assert result.data["threshold"] == pytest.approx(
        float(manifest["extras"]["anomaly"]["threshold"]), abs=1e-12
    )


def test_a_changed_run_id_reloads_rather_than_serving_the_old_detector(
    engine_context: Any, bars: list[dict[str, Any]], root: Path, run_id: str,  # noqa: F811
    tmp_path: Path
) -> None:
    second = tmp_path / "second"
    shutil.copytree(root, second)
    renamed = second / (run_id + "-b")
    (second / run_id).rename(renamed)

    state, context = live_state(engine_context, bars)
    engine = AnomalyEngine()
    first = engine.process(
        context_with(context, root, **{KEY_ANOMALY_RUN_ID: run_id}), state
    )
    assert first.data["model_run_id"] == run_id
    later = engine.process(
        context_with(context, second, **{KEY_ANOMALY_RUN_ID: renamed.name}), state
    )
    assert later.data["model_run_id"] == renamed.name
