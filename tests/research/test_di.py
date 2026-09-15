"""Spec 68 — the Dissimilarity Index, fitted on the predictor's training set.

**This spec exists on its own because the wrong version of it is invisible.** Fitted on the
skeptic's BUY subset the DI learns that "normal" means a BUY-shaped setup and then vetoes
every ordinary market state: the veto rate is high, the few trades that survive look clean,
and the leaderboard flatters the model. Nothing crashes, no metric moves in a direction
anybody would question, and no test that looks at predictions can tell.

So almost every test here is about **row identity**, and every expected set is
**recomputed** from the public splitter rather than read back from the artefact. Ruling 7 of
2026-09-13, and the reason it is a ruling rather than a preference: a proof that trusts a
number the subject reported about itself is not a proof.

`prediction.di_percentile` is absent from `config/default.yaml` by operator ruling until the
walk-forward reports, and the trainer correctly fits no DI without it. These tests supply a
percentile through a config wrapper so the fitting path is exercised; the *live* behaviour
with the key absent is the last test in the file, and it is the state the phase is actually
in.
"""

from __future__ import annotations

import math
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

from acsoe.modelling import di as di_module  # noqa: E402
from acsoe.modelling.artefacts import load_run  # noqa: E402
from tests.harness.doubles import load_default_config  # noqa: E402
from tests.research.test_training import (  # noqa: E402
    NOW,
    dataset_for,
    recomputed_folds,
)

#: A value for the fitting path only. It is **not** a proposal: the operator supplies the
#: real one after the walk-forward reports, and the lead's recommendation of 0.95 is
#: recorded as a guess until there is a distribution to place it on. Chosen here at 0.90 so
#: a constructed test row lands clearly on either side of it rather than near the edge.
TEST_PERCENTILE = 0.90


class WithPercentile:
    """The committed config plus the one value the operator has withheld.

    A wrapper rather than an edit to `config/default.yaml`: that file must keep the key
    **absent**, because absent is what the engines fail closed on and what the Phase 5
    criteria report PENDING for. Supplying it here exercises the arithmetic without
    claiming a number nobody has chosen.
    """

    def __init__(self, inner: Any, percentile: float = TEST_PERCENTILE) -> None:
        self._inner = inner
        self._percentile = percentile

    def get(self, key: str) -> Any:
        if key == "prediction.di_percentile":
            return self._percentile
        return self._inner.get(key)


@pytest.fixture(scope="module")
def config() -> Any:
    return load_default_config()


@pytest.fixture(scope="module")
def dataset(config: Any) -> Any:
    return dataset_for(config, random_walk=False)


def trained(config: Any, dataset: Any, tmp_path: Path, *, name: str = "di") -> Any:
    return training.train_walkforward(
        dataset,
        config=WithPercentile(config),
        models_dir=tmp_path / name / "models",
        derived_dir=tmp_path / name / "derived",
        now=NOW,
        max_folds=1,
    )


# --------------------------------------------------------------------------- #
# Which rows the DI saw
# --------------------------------------------------------------------------- #


def test_the_di_is_fitted_and_written_beside_its_own_fold(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """One DI per fold, under that fold's run id. A DI from another fold is a reference set
    from another market."""
    report = trained(config, dataset, tmp_path)
    directory = report.models_dir / report.fold_runs[0]
    assert (directory / "di.npz").is_file()
    loaded = load_run(directory, expected_features=report.feature_names)
    entry = loaded.manifest.extras["di"]
    assert entry["file"] == "di.npz"
    assert entry["rows"] > 0
    assert entry["percentile"] == pytest.approx(TEST_PERCENTILE)
    assert math.isfinite(float(entry["threshold"]))

    # The manifest's digest must be over the rows, not over how many of them there were.
    # Spec 68's named mutation is exactly that substitution, and until this line existed
    # nothing read `reference_identity` at all — a field nobody checks is a field that can
    # say anything.
    from acsoe.modelling.artefacts import identity_digest

    fit = di_module.load(directory / "di.npz")
    assert entry["reference_identity"] == identity_digest(
        [value.split("|")[0] for value in fit.identity],
        [int(value.split("|")[1]) for value in fit.identity],
    )
    assert entry["rows"] == fit.rows


def test_every_reference_row_is_one_of_the_folds_training_rows(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """The first of the three questions, and the expected set is recomputed here.

    Fitted on the **test** rows the DI accepts exactly the conditions the model is about to
    be scored on, which is the one thing it exists to refuse.
    """
    report = trained(config, dataset, tmp_path, name="train-rows")
    fold = recomputed_folds(config, dataset)[0]
    train_ids = set(identity_of_rows(dataset[list(fold.train_index)]))
    test_ids = set(identity_of_rows(dataset[list(fold.test_index)]))

    fit = di_module.load(report.models_dir / report.fold_runs[0] / "di.npz")
    reference = set(fit.identity)
    assert reference, "di.npz records no reference identities"

    outside = sorted(reference - train_ids)
    assert outside == [], (
        f"{len(outside)} DI reference rows are not among the fold's training rows; "
        f"{sum(1 for entry in outside if entry in test_ids)} of them are TEST rows"
    )
    assert not (reference & test_ids)


def test_at_least_one_reference_row_is_not_a_buy_call(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """The question that separates "the training rows" from "the BUY subset of them".

    A count cannot make it: on a fold where most calls are BUY the two sets are nearly the
    same size, and a DI fitted on the subset would report a plausible number of reference
    rows. What distinguishes them is whether an ordinary, non-BUY market state is in the
    reference set at all.
    """
    report = trained(config, dataset, tmp_path, name="not-buy")
    oos = pl.read_parquet(report.oos_path)
    buy_ids = set(identity_of_rows(oos.filter(pl.col("is_buy"))))

    fit = di_module.load(report.models_dir / report.fold_runs[0] / "di.npz")
    reference = set(fit.identity)
    assert reference - buy_ids, (
        "every DI reference row is a BUY call. Fitted on the BUY subset the DI learns that "
        "`normal` means a BUY-shaped setup and vetoes every ordinary market state — a high "
        "veto rate, a handful of clean-looking trades, a flattering leaderboard, and "
        "nothing red anywhere."
    )


def test_the_reference_set_is_the_last_window_of_the_training_span_per_pair(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """`prediction.di_window_days`, applied **per pair**.

    Per pair rather than globally, because a pair that stopped trading a month before the
    boundary would otherwise contribute nothing and every live vector of it would read as
    dissimilar — a veto on the thin pairs produced by the reference set's shape rather than
    by anything about the market.
    """
    window_days = int(config.get("prediction.di_window_days"))
    report = trained(config, dataset, tmp_path, name="window")
    fold = recomputed_folds(config, dataset)[0]
    train = dataset[list(fold.train_index)]

    fit = di_module.load(report.models_dir / report.fold_runs[0] / "di.npz")
    by_pair: dict[str, list[int]] = {}
    for entry in fit.identity:
        pair, stamp = entry.split("|")
        by_pair.setdefault(pair, []).append(int(stamp))

    assert by_pair, "the reference set carries no pairs"
    for pair, stamps in by_pair.items():
        latest = int(
            train.filter(pl.col("pair") == pair)["decision_ts"].max() or 0
        )
        assert min(stamps) >= latest - window_days * 86_400, (
            f"{pair} contributes a reference row older than the configured "
            f"{window_days}-day window"
        )


def test_the_reference_set_is_capped_and_the_cap_is_seeded(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """`prediction.di_reference_rows`, and the subsample comes from `seeds.train`.

    A run that cannot be reproduced from its config plus its data is not a result, and an
    unseeded subsample would make the DI's threshold — the number that decides when a model
    may refuse a trade — different on every run over the same data.
    """
    # The committed cap is 200,000 and the constructed fold has a few thousand eligible
    # rows, so asserting against it would assert nothing. Lowered here so the cap actually
    # binds and the subsample path is the one under test.
    cap = 400

    class Capped(WithPercentile):
        def get(self, key: str) -> Any:
            if key == "prediction.di_reference_rows":
                return cap
            return super().get(key)

    def with_cap(name: str) -> Any:
        return training.train_walkforward(
            dataset,
            config=Capped(config),
            models_dir=tmp_path / name / "models",
            derived_dir=tmp_path / name / "derived",
            now=NOW,
            max_folds=1,
        )

    first = with_cap("cap-one")
    second = with_cap("cap-two")
    one = di_module.load(first.models_dir / first.fold_runs[0] / "di.npz")
    two = di_module.load(second.models_dir / second.fold_runs[0] / "di.npz")
    assert one.rows == cap, (one.rows, cap)
    assert one.identity == two.identity, (
        "two runs over the same config and data drew different reference rows. The "
        "subsample comes from `seeds.train`; unseeded, the DI's threshold — the number "
        "that decides when a model may refuse a trade — would differ on every run."
    )
    assert one.threshold == two.threshold


def test_the_leave_one_out_excludes_every_pair_within_the_embargo(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """Ruling of 2026-09-15: the span is `backtest.embargo_bars x timeframes.decision_bar_s`,
    read from config by the trainer, and it excludes rows of **every** pair.

    Leaving out the row alone keeps its same-bar rows on the other pairs and its own
    adjacent bars, so the threshold measures time proximity. The distribution is recomputed
    here for a sample of reference rows, from the matrix and the identity's timestamps, with
    the span taken from config rather than from the artefact.
    """
    span = int(config.get("backtest.embargo_bars")) * int(
        config.get("timeframes.decision_bar_s")
    )
    report = trained(config, dataset, tmp_path, name="exclusion")
    directory = report.models_dir / report.fold_runs[0]
    fit = di_module.load(directory / "di.npz")
    loaded = load_run(directory, expected_features=report.feature_names)

    assert fit.exclusion_s == span
    assert loaded.manifest.extras["di"]["exclusion_s"] == span
    stamps = np.array([int(entry.split("|")[1]) for entry in fit.identity], dtype=np.int64)
    assert np.array_equal(fit.decision_ts, stamps)
    pairs_per_bar = np.unique(stamps, return_counts=True)[1]
    assert int(pairs_per_bar.max()) >= 2, (
        "no two reference rows share a bar, so this fixture cannot show the exclusion "
        "reaching across pairs"
    )

    sample = np.random.default_rng(3).choice(fit.rows, size=min(60, fit.rows), replace=False)
    block = fit.reference[sample]
    distances = np.sqrt(
        np.maximum(
            (block**2).sum(axis=1)[:, None]
            - 2.0 * block @ fit.reference.T
            + (fit.reference**2).sum(axis=1)[None, :],
            0.0,
        )
    )
    row_only = distances.copy()
    row_only[np.arange(sample.size), sample] = np.inf
    excluded = distances.copy()
    excluded[np.abs(stamps[sample][:, None] - stamps[None, :]) <= span] = np.inf
    k = fit.neighbours
    expected = np.sort(excluded, axis=1)[:, :k].mean(axis=1)
    plain = np.sort(row_only, axis=1)[:, :k].mean(axis=1)

    assert np.allclose(fit.distribution[sample], expected, rtol=1e-7, atol=1e-9)
    assert float(np.median(expected)) > float(np.median(plain)), (
        "on this fixture the exclusion changes nothing, so the assertion above could not "
        "tell it from leave-one-out on the row alone"
    )


# --------------------------------------------------------------------------- #
# What it scores
# --------------------------------------------------------------------------- #


def test_every_out_of_sample_row_carries_a_di_and_a_refusal(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """Spec 68 step 4: the veto rate per fold is a reported number, so spec 75 can see it."""
    report = trained(config, dataset, tmp_path, name="scored")
    oos = pl.read_parquet(report.oos_path)
    assert oos["di"].null_count() < oos.height
    entry = report.folds[0]
    assert entry["di_rows"] is not None
    assert entry["di_threshold"] is not None
    assert 0.0 <= float(entry["di_refusal_rate"]) <= 1.0


def test_a_distant_vector_is_refused_and_an_ordinary_one_is_not(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """The arithmetic, end to end through a fitted artefact rather than a constructed fit.

    The reference rows are scaled to roughly [0, 1] by the predictor's own scaler, so a
    vector of tens is far outside anything the model was trained on and must be refused,
    while a reference row itself must not be.
    """
    report = trained(config, dataset, tmp_path, name="score")
    fit = di_module.load(report.models_dir / report.fold_runs[0] / "di.npz")
    ordinary = di_module.score(fit, fit.reference[0])
    distant = di_module.score(fit, np.full(fit.width, 40.0))
    assert not ordinary.refused
    assert distant.refused
    assert distant.di > ordinary.di


# --------------------------------------------------------------------------- #
# What happens while the operator has not chosen
# --------------------------------------------------------------------------- #


def test_no_di_is_fitted_while_the_percentile_is_absent(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """The state the phase is actually in, and it is not a failure.

    `prediction.di_percentile` decides when a model may refuse a trade. The operator
    supplies it after the walk-forward reports, and nothing in this repository defaults it:
    the fold reports `di_rows: null`, no `di.npz` is written, and
    `di_fitted_on_predictor_training_set` reports PENDING naming the key rather than
    accusing the trainer of not writing a file it was right not to write.
    """
    assert config.get("prediction.di_percentile") is None
    report = training.train_walkforward(
        dataset,
        config=config,
        models_dir=tmp_path / "absent" / "models",
        derived_dir=tmp_path / "absent" / "derived",
        now=NOW,
        max_folds=1,
    )
    assert not (report.models_dir / report.fold_runs[0] / "di.npz").exists()
    entry = report.folds[0]
    assert entry["di_rows"] is None
    assert entry["di_threshold"] is None
    loaded = load_run(
        report.models_dir / report.fold_runs[0], expected_features=report.feature_names
    )
    assert loaded.manifest.extras["di"] is None


def identity_of_rows(frame: Any) -> list[str]:
    return [
        f"{row['pair']}|{int(row['decision_ts'])}"
        for row in frame.select(["pair", "decision_ts"]).iter_rows(named=True)
    ]
