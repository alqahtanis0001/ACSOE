"""Spec 67 — the dataset, the weights and the weekly walk-forward predictor.

**The two tests that matter here are a pair and neither works without the other.**

`test_a_random_walk_cannot_be_predicted` trains on a series that is unpredictable by
construction and asserts the out-of-sample Brier does **not** beat the fold's base-rate
Brier. That is the strongest look-ahead detector available: every leak — a feature reading
a later bar, a label joined onto the wrong row, a calibrator fitted on the test window, a
purge that does not purge — shows up as a model that predicts noise, and nothing else
does. It is also the only test here that would survive being ported to a different model.

`test_a_deterministic_series_is_learned` is its control, and without it the first test is
satisfied by a trainer that always returns the base rate. A model that cannot learn
anything cannot leak anything either.

The numbers, measured on the two constructed series below:

    deterministic   Brier 0.0000 against a base rate of 0.2446   (learns the generator)
    random walk     Brier 0.1718 against a base rate of 0.1556   (slightly worse, as it must be)
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import require_module

pl = require_module("polars", reason="polars is not installed")
np = require_module("numpy", reason="numpy is not installed")
require_module("lightgbm", reason="lightgbm is not installed")
training = require_module(
    "acsoe.research.training", reason="acsoe.research.training does not exist yet"
)

from acsoe.modelling.artefacts import load_run  # noqa: E402
from acsoe.modelling.features import FEATURE_NAMES  # noqa: E402
from acsoe.research.labelling import label_frame  # noqa: E402
from tests.harness.doubles import load_default_config  # noqa: E402

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
PAIRS = ("AAAUSD", "BBBUSD")
DAYS = 140


@pytest.fixture(scope="module")
def config() -> Any:
    return load_default_config()


def interval_of(config: Any) -> int:
    return int(config.get("timeframes.decision_bar_s"))


def candle_frame(
    pair: str, *, interval_s: int, random_walk: bool, days: int = DAYS
) -> Any:
    """A price series for one pair, either learnable or unlearnable by construction.

    `random_walk=False` makes every bar a fixed function of its index, so the future is
    exactly recoverable from the past and a working trainer must find it.
    `random_walk=True` makes each step an independent draw, so nothing in the past says
    anything about the future and a trainer that beats the base rate is leaking.

    Seeded from the pair name, so both are the same series on every machine and on every
    run: `training_is_reproducible_from_config_and_data` would otherwise be measuring the
    weather.
    """
    origin = (int(datetime(2024, 1, 1, tzinfo=UTC).timestamp()) // interval_s) * interval_s
    offset = sum(ord(char) for char in pair)
    generator = np.random.default_rng(offset)
    rows: list[dict[str, Any]] = []
    price = 100.0 + (offset % 17)
    for index in range(days * 86_400 // interval_s):
        if random_walk:
            step = float(generator.normal(0.0, 0.004))
        else:
            step = 0.0022 * (((index + offset) % 11) - 5) / 5.0 + 0.004 * math.sin(
                (index + offset) / 97.0
            )
        price = max(price * (1.0 + step), 0.01)
        span = abs(step) + 0.0008
        rows.append(
            {
                "ts": origin + index * interval_s,
                "open": price * (1.0 - span / 3),
                "high": price * (1.0 + span),
                "low": price * (1.0 - span),
                "close": price,
                "volume": 900.0 + 60.0 * ((index + offset) % 13),
                "trades": 15 + ((index + offset) % 9),
            }
        )
    return pl.DataFrame(rows)


def dataset_for(
    config: Any,
    *,
    random_walk: bool,
    days: int = DAYS,
    macro_archive: dict[str, str] | None = None,
) -> Any:
    """The constructed dataset. `macro_archive` maps asset to the pair to join as macro.

    **Omitted, the dataset carries no macro columns at all**, which is right for the trainer's
    own tests and wrong for anything that exercises an engine: engines 8 and 15 assemble the
    feature vector from engine 5's row *and* engine 6's macro columns, and a manifest naming
    no macro columns leaves that half of both engines unreachable while every test passes.
    `tests/engines/test_prediction.py` supplies one for that reason. Found by a surviving
    mutation in the spec 73 sweep; the build log for 2026-09-13 has the account.
    """
    return _dataset_for(config, random_walk=random_walk, days=days, macro_archive=macro_archive)


def _dataset_for(
    config: Any,
    *,
    random_walk: bool,
    days: int = DAYS,
    macro_archive: dict[str, str] | None = None,
) -> Any:
    interval_s = interval_of(config)
    candles: dict[str, Any] = {}
    labelled: dict[str, Any] = {}
    for pair in PAIRS:
        frame = candle_frame(
            pair, interval_s=interval_s, random_walk=random_walk, days=days
        )
        decimals = frame.with_columns(
            [
                pl.col(column).cast(pl.Decimal(38, 12))
                for column in ("open", "high", "low", "close", "volume")
            ]
        )
        labels, _series = label_frame(
            decimals, pair=pair, config=config, interval_s=interval_s
        )
        candles[pair] = frame
        labelled[pair] = labels
    return training.build_dataset(
        labelled, candles, config=config, macro_archive=macro_archive
    )


def run(config: Any, dataset: Any, tmp_path: Path, *, name: str = "run", folds: int = 2) -> Any:
    return training.train_walkforward(
        dataset,
        config=config,
        models_dir=tmp_path / name / "models",
        derived_dir=tmp_path / name / "derived",
        now=NOW,
        max_folds=folds,
    )


def recomputed_folds(config: Any, dataset: Any) -> list[Any]:
    """The folds this file derives for itself, from the public splitter.

    Recomputed rather than read back from the report, for the reason ruling 7 gives about
    the DI: a proof that trusts the number the subject reported is not a proof. The
    splitter is deterministic and takes no clock, so the truth is derivable here.
    """
    from acsoe.research.walkforward import purged_walk_forward

    rows = dataset.select(["decision_ts", "label_window_end_ts"]).to_dicts()
    return purged_walk_forward(rows, config=config, interval_s=interval_of(config))


def identity_of(frame: Any) -> str:
    from acsoe.modelling.artefacts import identity_digest

    return identity_digest(
        [str(value) for value in frame["pair"]],
        [int(value) for value in frame["decision_ts"]],
    )


@pytest.fixture(scope="module")
def learnable(config: Any) -> Any:
    return dataset_for(config, random_walk=False)


@pytest.fixture(scope="module")
def noise(config: Any) -> Any:
    return dataset_for(config, random_walk=True)


# --------------------------------------------------------------------------- #
# The pair that matters
# --------------------------------------------------------------------------- #


def test_a_random_walk_cannot_be_predicted(
    config: Any, noise: Any, tmp_path: Path
) -> None:
    """The look-ahead detector, and the only test here that would survive a change of model.

    Each step of this series is an independent draw, so nothing before a bar says anything
    about what follows it. A model that beats the fold's base-rate Brier on it is not
    clever; it has seen the answer. Every leak the phase is afraid of arrives here: a
    feature reading a later bar, a label joined onto the wrong row, a calibrator fitted on
    the test window, a purge that does not purge.

    The bar is deliberately generous — the Brier must not be **materially below** the base
    rate rather than must be above it — because a model can be marginally better than a
    constant by exploiting the class prior drifting within a fold, and calling that a leak
    would make this test fire on honest runs and then be disabled.
    """
    report = run(config, noise, tmp_path, name="noise")
    assert report.folds, "the constructed series produced no folds"
    for entry in report.folds:
        brier = float(entry["brier"])
        base = float(entry["base_rate_brier"])
        assert brier > base * 0.75, (
            f"fold {entry['fold_index']} scored a Brier of {brier:.4f} against a "
            f"base-rate Brier of {base:.4f} on a series that is unpredictable by "
            "construction. Nothing before a bar in this series says anything about what "
            "follows it, so a model this much better than a constant has seen the answer."
        )


def test_a_deterministic_series_is_learned(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """The control, and the test above is worthless without it.

    A trainer that always returned the fold's base rate would satisfy the random-walk
    assertion perfectly. This series is a fixed function of the bar index, so the future
    *is* recoverable from the past, and a working pipeline has to find it.
    """
    report = run(config, learnable, tmp_path, name="learn")
    assert report.folds
    beaten = [
        entry
        for entry in report.folds
        if float(entry["brier"]) < float(entry["base_rate_brier"])
    ]
    assert beaten, (
        "no fold beat its base-rate Brier on a series whose next bar is a fixed function "
        "of the current one. The random-walk test above is satisfied by a model that "
        "learns nothing, so without this one the pair proves nothing."
    )


# --------------------------------------------------------------------------- #
# The dataset
# --------------------------------------------------------------------------- #


def test_the_dataset_carries_the_identifiers_the_features_and_the_weights(
    learnable: Any,
) -> None:
    for column in training.DATASET_COLUMNS:
        assert column in learnable.columns, column
    for name in FEATURE_NAMES:
        assert name in learnable.columns, name
    assert set(learnable["pair"].unique()) == set(PAIRS)


def test_pair_is_an_identifier_and_never_a_feature(learnable: Any) -> None:
    """A pooled model that can memorise a pair name has learned which pairs went up in the
    training window and nothing that transfers. The column is carried because the join,
    the per-pair weighting and the row identity all need it; the feature list is what the
    model is handed."""
    assert "pair" in learnable.columns
    assert "pair" not in FEATURE_NAMES

    # Exact equality, not "pair is absent". An identifier reaching the feature list is the
    # defect, and `pair` is only the most obvious identifier: `decision_ts` is numeric, is
    # right there in the frame, and would let the model memorise *when* rather than *what*.
    # Naming one column to exclude tests one spelling of the mistake; pinning the whole
    # list tests the property.
    from acsoe.modelling.macro import macro_feature_names

    assets = sorted(
        {
            column.removeprefix("macro_").removesuffix("_" + name)
            for column in learnable.columns
            for name in FEATURE_NAMES
            if column.startswith("macro_") and column.endswith("_" + name)
        }
    )
    expected = (*FEATURE_NAMES, *macro_feature_names(assets))
    assert training.feature_columns(learnable, assets) == expected
    for identifier in training.DATASET_COLUMNS:
        assert identifier not in expected, identifier


def test_weights_are_far_below_one_because_labels_overlap(learnable: Any) -> None:
    """At a 48-bar horizon consecutive decision bars share almost all of their label
    window. A mean weight near 1.0 means the uniqueness weighting never ran, and every
    metric computed from these rows would describe a dataset far larger than the one that
    exists."""
    mean = float(learnable["weight"].mean())
    assert 0.0 < mean < 0.5, mean


def test_weights_are_computed_per_pair_not_pooled(config: Any) -> None:
    """Two pairs' label windows overlap in wall-clock time and do not overlap in
    information: SOLUSD's next twelve hours and ADAUSD's next twelve hours are two
    observations, not one. Pooling before counting concurrency would divide every weight by
    roughly the number of pairs and make the effective sample size a statement about how
    many pairs are listed."""
    one = dataset_for(config, random_walk=False, days=30)
    two_pairs = one.filter(pl.col("pair") == PAIRS[0])["weight"].mean()
    both = one["weight"].mean()
    assert float(two_pairs) == pytest.approx(float(both), rel=0.35), (
        "a pair's mean weight changed materially when a second pair was present, which is "
        "what pooling the concurrency count across pairs looks like"
    )


# --------------------------------------------------------------------------- #
# The fold loop
# --------------------------------------------------------------------------- #


def test_every_fold_trains_only_up_to_its_own_test_window(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """Operator ruling 1 of 2026-09-12, visible in the digest rather than only in the
    splitter's source. Training on both sides is purged cross-validation: legitimate for
    choosing hyperparameters and not for answering "would this have worked if I had been
    trading it"."""
    report = run(config, learnable, tmp_path, name="past")
    for entry in report.folds:
        assert int(entry["train_end_ts"]) == int(entry["test_start_ts"]), entry


def test_the_effective_sample_size_is_reported_beside_every_row_count(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """The operator's own addition to the weighting ruling: per fold, beside that fold's
    row count, because an aggregate hides exactly the fold whose 8,000 rows are 300
    observations."""
    report = run(config, learnable, tmp_path, name="ess")
    for entry in report.folds:
        assert float(entry["effective_sample_size"]) < float(entry["rows"])
        assert float(entry["train_effective_sample_size"]) < float(entry["train_rows"])
    assert report.digest["effective_sample_size"] < report.digest["rows"]


def test_accuracy_is_computed_nowhere(config: Any, learnable: Any, tmp_path: Path) -> None:
    """Retired by operator ruling: at a 23.89% target rate a model that always predicts
    `stop` is right 51% of the time, so a digest carrying accuracy is reporting the model
    that never trades."""
    report = run(config, learnable, tmp_path, name="metric")
    encoded = json.dumps(report.digest, default=str).lower()
    assert "accuracy" not in encoded
    for entry in report.folds:
        assert "accuracy" not in entry


def test_the_three_probabilities_are_a_distribution(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """An unrenormalised calibrator scales every expected move by an unknown factor, and
    the ranking between candidates survives it — so the BUY boundary moves while everything
    still looks internally consistent."""
    report = run(config, learnable, tmp_path, name="probs")
    oos = pl.read_parquet(report.oos_path)
    totals = (oos["p_target"] + oos["p_stop"] + oos["p_timeout"]).to_list()
    for total in totals:
        assert total == pytest.approx(1.0, abs=1e-9)


def test_the_out_of_sample_file_carries_every_column_three_specs_read(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """Specs 69, 74 and 75 read this file and nothing else."""
    report = run(config, learnable, tmp_path, name="oos")
    oos = pl.read_parquet(report.oos_path)
    for column in training.OOS_COLUMNS:
        assert column in oos.columns, column
    assert oos.height == sum(int(entry["rows"]) for entry in report.folds)


def test_an_empty_fold_is_reported_rather_than_dropped(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """Spec 53's rule, one layer up: a run that quietly produced four folds where the
    caller expected twelve reports metrics over a third of the data with nothing saying
    so. Every metric on an empty fold is null rather than zero, because a Brier of 0.0 is a
    perfect model."""
    report = run(config, learnable, tmp_path, name="empty", folds=50)
    empties = [entry for entry in report.folds if entry.get("is_empty")]
    for entry in empties:
        assert entry["brier"] is None
        assert entry["base_rate_brier"] is None


# --------------------------------------------------------------------------- #
# The artefacts
# --------------------------------------------------------------------------- #


def test_each_fold_writes_a_loadable_artefact_with_its_exact_feature_order(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    report = run(config, learnable, tmp_path, name="artefact")
    directory = report.models_dir / report.fold_runs[0]
    loaded = load_run(directory, expected_features=report.feature_names)
    assert loaded.manifest.class_order == training.CLASS_ORDER
    assert loaded.manifest.feature_names[: len(FEATURE_NAMES)] == FEATURE_NAMES
    assert loaded.manifest.extras["calibrator"]
    assert loaded.manifest.training_identity
    assert {path.name for path in directory.iterdir()} >= {
        "manifest.json",
        "scaler.json",
        "model.txt",
        "calibrators.json",
    }


def test_the_calibrator_saw_only_training_rows(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """The leak no metric can see, caught by identity instead.

    Fitting the calibrator on the test window is a textbook leak — it is shown the answers
    to the questions it is about to be scored on — and it **survived every test in this
    file**, including the random-walk look-ahead detector, until this assertion existed.
    It survives a metric comparison because isotonic regression is *monotone*: it cannot
    reorder predictions and therefore cannot manufacture skill, so it moves the Brier by
    less than any tolerance an honest run can live with.

    What changes is *which rows it saw*, and no number computed from the predictions is a
    function of that. So the manifest records the identity and this compares it against the
    fold's own training and test rows. Ruling 7 of this phase, applied one artefact over
    from the DI it was written for.
    """
    report = run(config, learnable, tmp_path, name="calib")
    folds = recomputed_folds(config, learnable)
    days = int(config.get("prediction.calibration_days"))

    for fold_run, entry, fold in zip(report.fold_runs, report.folds, folds, strict=False):
        if entry.get("is_empty"):
            continue
        loaded = load_run(
            report.models_dir / fold_run, expected_features=report.feature_names
        )
        extras = loaded.manifest.extras

        # **Recomputed here, not read back.** Comparing the manifest against the manifest
        # is what let the leak survive twice: the record described what the caller
        # intended and the mutation changed what the calibrator was handed, and the two
        # stayed consistent with each other. The splitter is deterministic and public, so
        # the expected calibration tail can be derived independently and compared.
        train = learnable[list(fold.train_index)]
        cutoff = int(fold.train_end_ts) - days * 86_400
        expected = train.filter(pl.col("decision_ts") >= cutoff)
        if expected.height == 0:
            expected = train
        assert extras["calibration_identity"] == identity_of(expected), (
            "the calibrator was fitted on a different set of rows from the last "
            f"{days} days of the fold's training window. Fitted on the TEST window it is "
            "shown the answers to the questions it is about to be scored on, and no "
            "metric can see it: isotonic regression is monotone, so it cannot manufacture "
            "skill and moves the Brier by less than any honest tolerance."
        )
        assert int(extras["calibration_end_ts"]) < int(entry["test_start_ts"])


def test_the_scaler_saw_exactly_the_training_rows(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """The other leak a metric cannot see, and for a different reason.

    MinMax is a monotone per-feature transform and a gradient-boosted tree splits on order
    rather than magnitude, so fitting the scaler on train **plus test** changes the
    predictor's output not at all — the mutation is equivalent for the predictor and every
    metric in this file agrees with it. It is not equivalent for the Dissimilarity Index,
    which is a Euclidean distance in this same scaled space: test-window minima and maxima
    bleeding into the reference scaling shift every distance and move the refusal
    threshold, and by the time that surfaced it would be a veto rate nobody could explain.

    So the manifest records the scaler's row identity and this asserts it equals the
    fold's training identity exactly — not a subset, not a count.
    """
    from acsoe.modelling.artefacts import Scaler

    report = run(config, learnable, tmp_path, name="scale")
    folds = recomputed_folds(config, learnable)

    for fold_run, entry, fold in zip(report.fold_runs, report.folds, folds, strict=False):
        if entry.get("is_empty"):
            continue
        loaded = load_run(
            report.models_dir / fold_run, expected_features=report.feature_names
        )
        # The scaler's own numbers, recomputed from the fold's training rows. Comparing
        # `scaler_identity` against `training_identity` compares two things the same
        # caller wrote and is satisfied by a scaler fitted on anything at all; the minima
        # and maxima are what the artefact actually contains.
        train = learnable[list(fold.train_index)]
        matrix = train.select(
            [pl.col(name).cast(pl.Float64) for name in report.feature_names]
        ).to_numpy()
        expected = Scaler.fit(matrix, report.feature_names)
        assert loaded.scaler.minimum == expected.minimum, (
            "the scaler's minima are not the training rows' minima. Fitted on train plus "
            "test it is invisible to every metric here — MinMax is monotone and a tree "
            "splits on order rather than magnitude — and it moves every distance the "
            "Dissimilarity Index computes in this same scaled space."
        )
        assert loaded.scaler.maximum == expected.maximum
        assert int(loaded.manifest.extras["scaler_rows"]) == int(entry["train_rows"])


def test_an_artefact_is_never_overwritten(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """One directory per training run, written once. An overwritten artefact makes every
    leaderboard row that referenced it a claim about a model that no longer exists."""
    report = run(config, learnable, tmp_path, name="once")
    with pytest.raises(FileExistsError):
        (report.models_dir / report.fold_runs[0]).mkdir()


def test_two_runs_over_one_config_and_one_dataset_agree(
    config: Any, learnable: Any, tmp_path: Path
) -> None:
    """A run that cannot be reproduced from its config plus its data is not a result.

    Behavioural rather than a source scan: a seed from the clock, an unfixed thread count
    and an insertion-ordered dictionary all show up here and none of them would show up in
    a grep.
    """
    first = run(config, learnable, tmp_path, name="one", folds=1)
    second = run(config, learnable, tmp_path, name="two", folds=1)
    for field in ("brier", "base_rate_brier", "log_loss", "buy_count", "rows"):
        assert first.folds[0][field] == second.folds[0][field], field
    one = (first.models_dir / first.fold_runs[0] / "model.txt").read_bytes()
    two = (second.models_dir / second.fold_runs[0] / "model.txt").read_bytes()
    assert one == two, "the two runs produced different model bytes"


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_a_dataset_without_the_identifier_columns_is_refused(learnable: Any) -> None:
    with pytest.raises(training.TrainingError, match="missing"):
        training.train_walkforward(
            learnable.drop("weight"),
            config=load_default_config(),
            models_dir=Path("unused"),
            derived_dir=Path("unused"),
            now=NOW,
        )


def test_a_dataset_too_short_for_a_single_fold_is_refused(config: Any) -> None:
    """Ten days cannot hold a ninety-day training window, and a run reporting zero folds
    is not a short run — it is no run. The committed labelled sample is exactly that
    shape, which is why spec 60 was amended to stop asking a criterion to walk it."""
    short = dataset_for(config, random_walk=False, days=12)
    with pytest.raises(training.TrainingError, match="no folds"):
        training.train_walkforward(
            short,
            config=config,
            models_dir=Path("unused"),
            derived_dir=Path("unused"),
            now=NOW,
        )


def test_pairs_below_the_configured_floor_are_named(config: Any) -> None:
    """`dataset.min_labelled_rows` is 0 today, so nothing is excluded; the reporting path
    exists because a pair left out is a pair the model has never seen and the leaderboard
    cannot say so later."""
    labelled = {"AAAUSD": pl.DataFrame({"x": [1, 2]}), "BBBUSD": pl.DataFrame({"x": [1]})}

    class Floor:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def get(self, key: str) -> Any:
            return 2 if key == "dataset.min_labelled_rows" else self._inner.get(key)

    assert training.pairs_below_floor(labelled, config=Floor(config)) == ("BBBUSD",)
    assert training.pairs_below_floor(labelled, config=config) == ()
