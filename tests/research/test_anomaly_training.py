"""Spec 70 — the anomaly detector, fitted on market data only.

This model answers **one** question: is the market broken. It does not answer whether the
trade is good, and the difference is not philosophical. An outlier model that can see a
macro column, a probability or a label stops refusing broken markets and starts refusing
*unattractive* ones, and it does that while its refusal rate stays in a range nobody would
query. So the assertions below are mostly about **which columns it saw**, recomputed here
rather than read back from what it recorded about itself, which is ruling 7 of this phase.

The two checks spec 70 names by hand are both here and neither is a number the detector
reported: a ten-sigma volume spike scores above the threshold while the *same row*
unspiked scores below it, and the training identity is the fold's own training rows
recomputed from the public splitter.

**The threshold is the operator's.** `anomaly.threshold_percentile` is absent from
`config/default.yaml` and nothing here defaults it. The forest is still fitted — it needs
no number from anybody and its score distribution is a finding in its own right — but the
threshold and the block rate are `null` until the operator supplies one, and engine 13
blocks with `anomaly_unavailable` meanwhile. The tests that need a threshold supply one
through a wrapper so the arithmetic is exercised without anybody inventing the number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import require_module

pl = require_module("polars", reason="polars is not installed")
require_module("lightgbm", reason="lightgbm is not installed")
require_module("sklearn", reason="scikit-learn is not installed")
joblib = require_module("joblib", reason="joblib is not installed")
training = require_module(
    "acsoe.research.training", reason="acsoe.research.training does not exist yet"
)

import numpy as np  # noqa: E402

from acsoe.modelling.artefacts import ArtefactError, identity_digest, load_run  # noqa: E402
from acsoe.modelling.features import MARKET_QUALITY_FEATURES  # noqa: E402
from tests.harness.doubles import load_default_config  # noqa: E402
from tests.research.test_training import (  # noqa: E402
    NOW,
    dataset_for,
    recomputed_folds,
)

FOLDS = 3

#: Supplied here and **never** written into `config/default.yaml`. Absent is what engine 13
#: fails closed on and what the Phase 5 criteria report PENDING for; a number in the
#: committed config would be this lane choosing when a market counts as broken.
PERCENTILE = 0.99

#: The test's number and nothing else's, chosen to sit clearly below the 0.904 quantile a
#: ten-sigma volume spike was measured to land at so the spike assertions have margin. See
#: the build-log entry of 2026-09-13: at 0.99 and at 0.95 the spike is not blocked, which is
#: a property of rolling z-scores rather than of this fit, and the operating percentile is
#: the operator's to choose with that measurement in front of them.
SPIKE_PERCENTILE = 0.85


class WithPercentile:
    """The committed config with one absent key answered, and nothing else changed."""

    def __init__(self, inner: Any, value: float | None) -> None:
        self._inner = inner
        self._value = value

    def get(self, key: str) -> Any:
        if key == "anomaly.threshold_percentile":
            return self._value
        return self._inner.get(key)


@pytest.fixture(scope="module")
def config() -> Any:
    return load_default_config()


@pytest.fixture(scope="module")
def dataset(config: Any) -> Any:
    return dataset_for(config, random_walk=False)


@pytest.fixture(scope="module")
def bare(config: Any, dataset: Any, tmp_path_factory: Any) -> Any:
    """A run under the committed config, where the threshold percentile is absent."""
    root = tmp_path_factory.mktemp("anomaly-bare")
    return training.train_walkforward(
        dataset,
        config=config,
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=FOLDS,
    )


@pytest.fixture(scope="module")
def thresholded(config: Any, dataset: Any, tmp_path_factory: Any) -> Any:
    """The same run with a percentile supplied, so the threshold arithmetic is exercised."""
    root = tmp_path_factory.mktemp("anomaly-threshold")
    return training.train_walkforward(
        dataset,
        config=WithPercentile(config, PERCENTILE),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=FOLDS,
    )


@pytest.fixture(scope="module")
def sensitive(config: Any, dataset: Any, tmp_path_factory: Any) -> Any:
    """One fold at a percentile the spike clears, so the mechanism is proved end to end."""
    root = tmp_path_factory.mktemp("anomaly-sensitive")
    return training.train_walkforward(
        dataset,
        config=WithPercentile(config, SPIKE_PERCENTILE),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=1,
    )


def folds_with_a_detector(report: Any) -> list[dict[str, Any]]:
    return [dict(entry) for entry in report.folds if entry.get("anomaly_rows")]


def artefact(report: Any, fold_index: int) -> Path:
    return report.models_dir / f"{report.run_id}-f{fold_index}"


def manifest_of(report: Any, fold_index: int) -> dict[str, Any]:
    raw = (artefact(report, fold_index) / "manifest.json").read_bytes()
    return dict(json.loads(raw.decode("utf-8")))


def detector_of(report: Any, fold_index: int) -> Any:
    return joblib.load(artefact(report, fold_index) / training.ANOMALY_MODEL_NAME)


def scored(model: Any, matrix: Any) -> Any:
    """Larger is more anomalous, which is the orientation the manifest records.

    Written once here rather than in each test, because a sign that flips between two
    assertions is a detector that blocks exactly the ordinary markets and passes the broken
    ones while every test stays green.
    """
    return -model.score_samples(matrix)


# --------------------------------------------------------------------------- #
# Which columns it saw
# --------------------------------------------------------------------------- #


def test_a_detector_is_fitted_at_all(bare: Any) -> None:
    """The control. Without it every exclusion below is satisfied by a run that never
    fitted a detector, and an artefact directory with no `anomaly.joblib` in it would
    quietly pass the lot."""
    later = folds_with_a_detector(bare)
    assert later, "no fold fitted an anomaly detector, so nothing below is being tested"
    for entry in later:
        assert (artefact(bare, int(entry["fold_index"])) / "anomaly.joblib").is_file()


def test_the_inputs_are_the_market_quality_features_and_nothing_else(bare: Any) -> None:
    """Spec 70's first line, asserted against `MARKET_QUALITY_FEATURES` itself.

    Recorded in the manifest because engine 13 rebuilds this vector live and a permuted
    order there is the same confident nonsense a permuted predictor vector would be.
    """
    for entry in folds_with_a_detector(bare):
        recorded = manifest_of(bare, int(entry["fold_index"]))["extras"]["anomaly"]
        assert set(recorded["input_names"]) == set(MARKET_QUALITY_FEATURES)
        assert recorded["input_names"] == entry["anomaly_input_names"]


def test_no_macro_column_no_probability_and_no_label_reaches_it(
    bare: Any, dataset: Any
) -> None:
    """The three ways this stops being a market-health model, asserted by exclusion.

    A macro column makes it an opinion about the wider market rather than about this pair's
    bars. A probability or an expected move makes it a second opinion on the predictor's
    call. A label makes it a supervised model of the outcome — which is not a detector with
    a bug in it, it is a predictor whose refusals would look like caution.
    """
    forbidden = {
        "label",
        "return_pct",
        "weight",
        "label_window_end_ts",
        "p_target",
        "p_stop",
        "p_timeout",
        "expected_move_pct",
        "pair",
        "decision_ts",
    }
    macro = {name for name in dataset.columns if name.startswith("macro_")}
    for entry in folds_with_a_detector(bare):
        names = set(entry["anomaly_input_names"])
        assert names & forbidden == set()
        assert names & macro == set()


def test_the_fitted_model_saw_exactly_the_columns_the_manifest_names(bare: Any) -> None:
    """The assertion that makes the recorded input list evidence rather than a comment.

    Every check above reads `anomaly_input_names`, which is what the trainer *says* the
    detector saw. A column appended to the matrix after that list is built — the outcome,
    a probability, a macro column — changes what the model was fitted on and changes the
    list not at all, and every name-based assertion in this file stays green while the
    detector quietly becomes a supervised model of the outcome. `n_features_in_` is what
    the fitted forest itself reports, so the two can be compared.
    """
    for entry in folds_with_a_detector(bare):
        model = detector_of(bare, int(entry["fold_index"]))
        assert int(model.n_features_in_) == len(entry["anomaly_input_names"]), (
            "the anomaly detector was fitted on "
            f"{int(model.n_features_in_)} columns and its manifest names "
            f"{len(entry['anomaly_input_names'])}. Whatever the extra column is, engine 13 "
            "cannot rebuild it from the manifest and a label or a probability among them "
            "makes this a second predictor rather than a market-health model."
        )


def test_no_input_is_a_spread_and_the_manifest_says_so(bare: Any) -> None:
    """The archive is OHLCVT. The invariants describe engine 13's inputs as velocity,
    volume and spread, so the spread's absence is **stated** rather than left to be
    inferred from a list that happens not to contain one — a reader who finds no spread in
    the list cannot tell a deliberate absence from an oversight."""
    for entry in folds_with_a_detector(bare):
        for name in entry["anomaly_input_names"]:
            for word in ("spread", "bid", "ask", "depth", "book"):
                assert word not in name, name
        recorded = manifest_of(bare, int(entry["fold_index"]))["extras"]["anomaly"]
        assert "absent" in recorded["spread_input"]
        assert recorded["labels"] == "none - unsupervised"


def test_it_is_fitted_on_the_folds_training_rows_recomputed(
    bare: Any, config: Any, dataset: Any
) -> None:
    """Ruling 7: the expected rows are recomputed from the public splitter here, and the
    artefact's identity is compared against that rather than against a count.

    Fitted on the test rows, an outlier model calls the test window normal by construction
    and its block rate collapses towards zero, which reads as a calm market.
    """
    folds = {int(fold.fold_index): fold for fold in recomputed_folds(config, dataset)}
    for entry in folds_with_a_detector(bare):
        index = int(entry["fold_index"])
        train = dataset[list(folds[index].train_index)]
        complete = train.filter(
            ~pl.any_horizontal(
                [
                    pl.col(name).is_nan() | pl.col(name).is_null()
                    for name in entry["anomaly_input_names"]
                ]
            )
        )
        assert complete.height == int(entry["anomaly_rows"])
        assert entry["anomaly_training_identity"] == identity_digest(
            [str(value) for value in complete["pair"]],
            [int(value) for value in complete["decision_ts"]],
        ), (
            f"fold {index}'s anomaly detector was fitted on a different set of rows from "
            "its own training window. Fitted on the test rows it calls the test window "
            "normal by construction; fitted on everything it has seen the window it is "
            "about to report a block rate over."
        )


# --------------------------------------------------------------------------- #
# The threshold, which is the operator's
# --------------------------------------------------------------------------- #


def test_no_threshold_is_recorded_while_the_key_is_absent(bare: Any) -> None:
    """`anomaly.threshold_percentile` is absent from the committed config by ruling.

    The forest is fitted anyway — it needs no number from anybody — but the number that
    decides when the market is declared broken is not this module's to invent, so the
    threshold and the block rate are null and engine 13 blocks with `anomaly_unavailable`.
    """
    assert load_default_config().get("anomaly.threshold_percentile") is None
    for entry in folds_with_a_detector(bare):
        assert entry["anomaly_threshold"] is None
        assert entry["anomaly_percentile"] is None
        assert entry["anomaly_block_rate"] is None
        recorded = manifest_of(bare, int(entry["fold_index"]))["extras"]["anomaly"]
        assert recorded["threshold"] is None


def test_the_threshold_is_the_quantile_of_the_training_scores(
    thresholded: Any, config: Any, dataset: Any
) -> None:
    """Recomputed here from the fitted forest and the fold's own training rows.

    **The first version of this test compared the digest to the manifest**, which are two
    numbers written by one function from one variable, and a mutation that took the
    threshold from the *test* scores survived it with the whole file green. Ruling 7: a
    proof that compares two things the subject said about itself is not a proof.

    The leak it missed is worth naming. A threshold at the 99th percentile of the test
    window's own scores blocks exactly one per cent of that window whatever happened in it,
    so the block rate stops being a measurement and becomes a constant — a calm week and a
    week of broken books report the same number, and the detector blocks its calmest one
    per cent of a genuinely broken week.
    """
    folds = {int(fold.fold_index): fold for fold in recomputed_folds(config, dataset)}
    for entry in folds_with_a_detector(thresholded):
        index = int(entry["fold_index"])
        recorded = manifest_of(thresholded, index)["extras"]["anomaly"]
        assert recorded["percentile"] == pytest.approx(PERCENTILE)
        assert float(entry["anomaly_threshold"]) == pytest.approx(
            float(recorded["threshold"])
        )

        loaded = load_run(
            artefact(thresholded, index), expected_features=thresholded.feature_names
        )
        train = dataset[list(folds[index].train_index)]
        matrix = training._anomaly_matrix(
            train, loaded.scaler, thresholded.feature_names, list(entry["anomaly_input_names"])
        )
        complete = np.array([row for row in matrix if np.isfinite(row).all()])
        expected = float(
            np.quantile(scored(detector_of(thresholded, index), complete), PERCENTILE)
        )
        assert float(entry["anomaly_threshold"]) == pytest.approx(expected, abs=1e-12), (
            f"fold {index}'s threshold is not the {PERCENTILE} quantile of its own "
            "training rows' scores. Taken from the test window instead, it blocks a fixed "
            "share of that window whatever the market did and the block rate stops being "
            "a measurement."
        )


def test_the_block_rate_is_reported_per_fold_and_is_a_finding(thresholded: Any) -> None:
    """Spec 70: a rate that is zero or near one on every fold is a finding, not a pass.

    Zero on every fold means the threshold cannot fire and the detector is decoration; near
    one means it blocks the ordinary market and the live loop would never trade. Either is
    a result to report rather than a test to loosen, so this asserts the run is not in
    either state and names what it would mean if it were.
    """
    rates = [float(entry["anomaly_block_rate"]) for entry in folds_with_a_detector(thresholded)]
    assert rates, "no fold reported a block rate"
    assert not all(rate == 0.0 for rate in rates), (
        "every fold blocked nothing at the "
        f"{PERCENTILE} percentile: the threshold cannot fire and the detector is "
        "decoration. A finding, not a test to loosen."
    )
    assert not all(rate > 0.95 for rate in rates), (
        "every fold blocked almost everything: the detector refuses the ordinary market "
        "and the live loop would never trade. A finding, not a test to loosen."
    )
    for rate in rates:
        assert 0.0 <= rate <= 1.0


# --------------------------------------------------------------------------- #
# What it actually does to a broken bar
# --------------------------------------------------------------------------- #


def spiked_pair_and_bar(config: Any, dataset: Any, fold: Any) -> tuple[str, int]:
    """One pair and one bar inside the fold's test window, chosen deterministically."""
    test = dataset[list(fold.test_index)]
    pair = str(test["pair"][0])
    own = test.filter(pl.col("pair") == pair)
    return pair, int(own["decision_ts"][own.height // 2])


def spiked_row(config: Any, dataset: Any, pair: str, bar_ts: int) -> Any:
    """The dataset's own row for `(pair, bar_ts)` with a ten-sigma volume spike in it.

    **Injected into the candles and the features recomputed**, not written straight into
    the feature vector. A spike written into eight scaled columns by hand is a bar with
    enormous volume and a perfectly ordinary everything-else, which is not a market event
    and would let a detector pass this test for a reason that never occurs live. Injected
    into the bar, the spike propagates exactly as far as the feature definitions carry it —
    which turns out to be the whole point of what this measures.
    """
    from acsoe.modelling.features import compute
    from tests.research.test_training import candle_frame, interval_of

    interval_s = interval_of(config)
    frame = candle_frame(pair, interval_s=interval_s, random_walk=False, days=140)
    sigma = float(frame["volume"].std() or 1.0)
    mean = float(frame["volume"].mean() or 0.0)
    spiked = frame.with_columns(
        pl.when(pl.col("ts") == bar_ts)
        .then(pl.lit(mean + 10.0 * sigma))
        .otherwise(pl.col("volume"))
        .alias("volume"),
        pl.when(pl.col("ts") == bar_ts)
        .then(pl.col("trades") * 10)
        .otherwise(pl.col("trades"))
        .alias("trades"),
    )
    features = compute(
        spiked,
        interval_s=interval_s,
        min_lookback_fill=float(config.get("features.min_lookback_fill")),
    ).filter(pl.col("ts") == bar_ts)
    row = dataset.filter((pl.col("pair") == pair) & (pl.col("decision_ts") == bar_ts))
    assert row.height == 1, (pair, bar_ts, row.height)
    return row.with_columns(
        [pl.lit(float(features[name][0])).alias(name) for name in MARKET_QUALITY_FEATURES]
    )


def test_a_ten_sigma_volume_spike_raises_the_score_and_where_it_lands(
    thresholded: Any, config: Any, dataset: Any
) -> None:
    """Spec 70's named check, and the measurement that says it does not hold at 0.99.

    **One bar, one field changed, the features recomputed.** An ordinary row and a spiked
    row drawn independently would differ in every feature, and a detector that ranked them
    correctly for the wrong reason would pass.

    The spike moves the score in the right direction and lands at roughly the 0.90 quantile
    of the training distribution. It does **not** clear a 0.99 threshold, and it does not
    clear 0.95. That is a property of the features rather than of this fit: `volume_z_n` is
    a rolling z-score, so an outlier inflates its own denominator and a bar ten sigma above
    the series mean moves the four-bar view by about a tenth of a scaled unit. The score is
    identical at ten sigma, a hundred and a thousand. The build-log entry for this date has
    the numbers and hands the operator the trade it implies; this test asserts the part
    that is true and load-bearing rather than a boolean tuned until it held.
    """
    entry = folds_with_a_detector(thresholded)[0]
    index = int(entry["fold_index"])
    folds = {int(fold.fold_index): fold for fold in recomputed_folds(config, dataset)}
    fold = folds[index]
    loaded = load_run(
        artefact(thresholded, index), expected_features=thresholded.feature_names
    )
    model = detector_of(thresholded, index)
    inputs = list(entry["anomaly_input_names"])
    names = thresholded.feature_names

    pair, bar_ts = spiked_pair_and_bar(config, dataset, fold)
    plain = dataset.filter((pl.col("pair") == pair) & (pl.col("decision_ts") == bar_ts))
    spiked = spiked_row(config, dataset, pair, bar_ts)

    changed = [
        name
        for name in MARKET_QUALITY_FEATURES
        if abs(float(plain[name][0]) - float(spiked[name][0])) > 1e-9
    ]
    assert changed, "the injected spike changed no market-quality feature at all"

    plain_score = float(scored(model, training._anomaly_matrix(plain, loaded.scaler, names, inputs))[0])
    spiked_score = float(scored(model, training._anomaly_matrix(spiked, loaded.scaler, names, inputs))[0])
    assert spiked_score > plain_score, (
        "a ten-sigma volume and trade-count spike did not make the bar score as more "
        "anomalous than the same bar without it. Engine 13 exists to stop the system "
        "trading through exactly that bar."
    )

    train = dataset[list(fold.train_index)]
    matrix = training._anomaly_matrix(train, loaded.scaler, names, inputs)
    train_scores = scored(model, np.array([row for row in matrix if np.isfinite(row).all()]))
    assert float(np.mean(train_scores < spiked_score)) > SPIKE_PERCENTILE
    assert float(np.mean(train_scores < plain_score)) < SPIKE_PERCENTILE


def test_at_a_threshold_it_clears_the_spike_is_blocked_and_the_bar_beside_it_is_not(
    sensitive: Any, config: Any, dataset: Any
) -> None:
    """The mechanism end to end, through the trainer's own recorded threshold.

    `SPIKE_PERCENTILE` is **the test's number**, chosen to sit clearly below the measured
    0.904 quantile the spike lands at so the assertion has margin. It is not an operating
    point and it is not written into `config/default.yaml`: the percentile that decides
    when a market is declared broken is the operator's by ruling, and the build log hands
    them the measurement rather than a number this lane picked.
    """
    entry = folds_with_a_detector(sensitive)[0]
    index = int(entry["fold_index"])
    fold = {int(f.fold_index): f for f in recomputed_folds(config, dataset)}[index]
    loaded = load_run(artefact(sensitive, index), expected_features=sensitive.feature_names)
    model = detector_of(sensitive, index)
    inputs = list(entry["anomaly_input_names"])
    names = sensitive.feature_names
    threshold = float(entry["anomaly_threshold"])

    pair, bar_ts = spiked_pair_and_bar(config, dataset, fold)
    plain = dataset.filter((pl.col("pair") == pair) & (pl.col("decision_ts") == bar_ts))
    spiked = spiked_row(config, dataset, pair, bar_ts)

    assert float(scored(model, training._anomaly_matrix(plain, loaded.scaler, names, inputs))[0]) <= threshold
    assert float(scored(model, training._anomaly_matrix(spiked, loaded.scaler, names, inputs))[0]) > threshold


def test_the_detector_is_reproducible_from_the_config_and_the_data(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """Two runs over one config and one dataset agree on the threshold to the bit.

    `IsolationForest` is randomised; `seeds.train` is what makes the refusal boundary a
    property of the data rather than of the run that happened to produce it, and a
    threshold that moved between runs would make every leaderboard row incomparable.
    """
    reports = [
        training.train_walkforward(
            dataset,
            config=WithPercentile(config, PERCENTILE),
            models_dir=tmp_path / name / "models",
            derived_dir=tmp_path / name / "derived",
            now=NOW,
            max_folds=1,
        )
        for name in ("first", "second")
    ]
    first, second = (folds_with_a_detector(report)[0] for report in reports)
    assert first["anomaly_threshold"] == second["anomaly_threshold"]
    assert first["anomaly_training_identity"] == second["anomaly_training_identity"]
    assert first["anomaly_block_rate"] == second["anomaly_block_rate"]


# --------------------------------------------------------------------------- #
# The one binary artefact
# --------------------------------------------------------------------------- #


def test_the_artefact_is_hashed_in_the_manifest(bare: Any) -> None:
    """Spec 70 item 3. Every other file in a run directory is text precisely because a
    pickle is code that runs when a model is loaded, inside the process that places orders.
    scikit-learn has no text dump for an isolation forest, so this one is joblib and the
    hash is what stands in — against a **swapped** file, which is what a hash can do."""
    for entry in folds_with_a_detector(bare):
        files = manifest_of(bare, int(entry["fold_index"]))["files"]
        assert training.ANOMALY_MODEL_NAME in files
        assert len(files[training.ANOMALY_MODEL_NAME]) == 64


def test_a_changed_anomaly_file_is_refused_by_the_loader(bare: Any, tmp_path: Path) -> None:
    """The other half of the hash, which is the half that matters: a manifest that records
    a digest nothing checks is a comment.

    The run directory is copied first so the fixture the other tests share is left intact.
    """
    import shutil

    entry = folds_with_a_detector(bare)[0]
    source = artefact(bare, int(entry["fold_index"]))
    copy = tmp_path / "run"
    shutil.copytree(source, copy)
    load_run(copy, expected_features=bare.feature_names)

    target = copy / training.ANOMALY_MODEL_NAME
    target.write_bytes(target.read_bytes() + b"\x00")
    with pytest.raises(ArtefactError) as caught:
        load_run(copy, expected_features=bare.feature_names)
    assert training.ANOMALY_MODEL_NAME in str(caught.value)
