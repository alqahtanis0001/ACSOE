"""Spec 69 — the skeptic, trained only on the predictor's out-of-sample BUY calls.

Three ways to get this wrong, and every one of them is silent:

* **a non-BUY row.** The skeptic grades the predictor's BUY calls. Trained on rows the
  predictor never called, it is a second predictor wearing a veto.
* **an in-sample BUY call.** The predictor is right about its own training set far more
  often than it is right live, so a skeptic trained on those calls learns the predictor's
  overfit rather than its mistakes and vetoes almost nothing.
* **a call from this fold or later.** That is the window it is about to be judged on.

So the expected training set is **recomputed here from the out-of-sample file** and the
artefact's identity is compared against it. Ruling 7 of this phase: a proof that trusts a
number the subject reported about itself is not a proof, and a row *count* passes whenever
two sets happen to be the same size — which, on a fold where most calls are BUY, they
nearly are.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.conftest import require_module

pl = require_module("polars", reason="polars is not installed")
require_module("lightgbm", reason="lightgbm is not installed")
training = require_module(
    "acsoe.research.training", reason="acsoe.research.training does not exist yet"
)

from acsoe.modelling.artefacts import identity_digest, load_run  # noqa: E402
from tests.harness.doubles import load_default_config  # noqa: E402
from tests.research.test_training import NOW, dataset_for  # noqa: E402

FOLDS = 4


@pytest.fixture(scope="module")
def config() -> Any:
    return load_default_config()


@pytest.fixture(scope="module")
def dataset(config: Any) -> Any:
    return dataset_for(config, random_walk=False)


@pytest.fixture(scope="module")
def report(config: Any, dataset: Any, tmp_path_factory: Any) -> Any:
    """One run of four folds, shared. Four folds because the skeptic needs history: fold 0
    has no earlier out-of-sample calls at all and correctly produces none."""
    root = tmp_path_factory.mktemp("skeptic")
    return training.train_walkforward(
        dataset,
        config=config,
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=FOLDS,
    )


def eligible_rows(report: Any, config: Any, fold_index: int) -> Any:
    """The rows this fold's skeptic may train on, recomputed from the out-of-sample file.

    Read back from the file specs 69, 74 and 75 all read, with the same purge and embargo
    the predictor's own training rows are subject to. If this disagrees with the trainer,
    one of the two is wrong and the test says which by naming the count.
    """
    oos = pl.read_parquet(report.oos_path)
    entry = next(item for item in report.folds if int(item["fold_index"]) == fold_index)
    interval_s = int(config.get("timeframes.decision_bar_s"))
    embargo = int(config.get("backtest.embargo_bars")) * interval_s
    return oos.filter(
        pl.col("is_buy")
        & (pl.col("fold_index") < fold_index)
        & (pl.col("label_window_end_ts") < int(entry["test_start_ts"]))
        & (pl.col("decision_ts") < int(entry["test_start_ts"]) - embargo)
    ).sort(["decision_ts", "pair"])


def digest_of(frame: Any) -> str:
    return identity_digest(
        [str(value) for value in frame["pair"]],
        [int(value) for value in frame["decision_ts"]],
    )


def folds_with_a_skeptic(report: Any) -> list[dict[str, Any]]:
    return [dict(entry) for entry in report.folds if entry.get("skeptic_rows")]


# --------------------------------------------------------------------------- #
# Which rows it saw
# --------------------------------------------------------------------------- #


def test_the_first_fold_produces_no_skeptic_and_says_so(report: Any) -> None:
    """Not a failure and not an omission. There are no earlier out-of-sample calls for it
    to learn from, the digest records `skeptic_rows: 0`, and engine 15 blocks with
    `skeptic_unavailable` for a model version without one."""
    first = dict(report.folds[0])
    assert first["skeptic_rows"] == 0
    assert first["skeptic_training_identity"] is None
    assert not (report.models_dir / report.fold_runs[0] / "skeptic.txt").exists()


def test_a_later_fold_trains_a_skeptic(report: Any) -> None:
    """The control. Without it every assertion below is satisfied by a pipeline that never
    trains a skeptic at all."""
    later = folds_with_a_skeptic(report)
    assert later, "no fold trained a skeptic, so nothing below is being tested"
    for entry in later:
        assert (
            report.models_dir / f"{report.run_id}-f{entry['fold_index']}" / "skeptic.txt"
        ).is_file()


def test_every_training_row_is_an_earlier_out_of_sample_buy_call(
    report: Any, config: Any
) -> None:
    """The spec's own assertion, made by identity against a recomputed set.

    A count would pass whenever the trainer's set and the correct one happened to be the
    same size, and on a fold where most calls are BUY they nearly are.
    """
    for entry in folds_with_a_skeptic(report):
        expected = eligible_rows(report, config, int(entry["fold_index"]))
        assert expected.height == int(entry["skeptic_rows"]), (
            entry["fold_index"],
            expected.height,
            entry["skeptic_rows"],
        )
        assert entry["skeptic_training_identity"] == digest_of(expected), (
            f"fold {entry['fold_index']}'s skeptic trained on a different set of rows from "
            "the out-of-sample BUY calls of folds strictly before it. An in-sample call "
            "teaches the predictor's overfit rather than its mistakes; a non-BUY row makes "
            "the skeptic a second predictor; a call from this fold is the window it is "
            "about to be judged on."
        )


def test_no_training_row_is_a_non_buy_call(report: Any, config: Any) -> None:
    """Stated separately from the identity check because it is the exclusion a reader will
    want to see asserted on its own terms."""
    oos = pl.read_parquet(report.oos_path)
    non_buy = oos.filter(~pl.col("is_buy"))
    assert non_buy.height, "the run produced no non-BUY rows, so this test proves nothing"
    for entry in folds_with_a_skeptic(report):
        expected = eligible_rows(report, config, int(entry["fold_index"]))
        assert expected.filter(~pl.col("is_buy")).height == 0


def test_no_training_row_comes_from_this_fold_or_later(report: Any, config: Any) -> None:
    for entry in folds_with_a_skeptic(report):
        index = int(entry["fold_index"])
        expected = eligible_rows(report, config, index)
        assert int(expected["fold_index"].max()) < index


def test_the_purge_and_embargo_remove_rows_rather_than_nothing(
    report: Any, config: Any
) -> None:
    """The test that keeps the two above from being vacuous.

    If the purge and embargo removed nothing on this dataset, the recomputed set and a
    naive "all earlier BUY calls" set would be identical and the identity check could not
    tell a trainer that applied them from one that did not. At a weekly test window and a
    twelve-hour label horizon they should remove roughly the last half-day of the previous
    fold, so this asserts the difference is real.
    """
    oos = pl.read_parquet(report.oos_path)
    checked = 0
    for entry in folds_with_a_skeptic(report):
        index = int(entry["fold_index"])
        naive = oos.filter(pl.col("is_buy") & (pl.col("fold_index") < index))
        strict = eligible_rows(report, config, index)
        assert strict.height <= naive.height
        if naive.height > strict.height:
            checked += 1
    assert checked, (
        "the purge and embargo removed nothing on any fold, so the identity assertions "
        "above cannot distinguish a trainer that applies them from one that does not"
    )


def test_a_call_from_this_fold_is_excluded_even_if_it_is_handed_one(
    report: Any, dataset: Any, config: Any
) -> None:
    """The third exclusion, proved where it is the only thing standing between the skeptic
    and the window it is about to be judged on.

    `train_walkforward` concatenates the folds it has already finished, so in the run above
    the current fold's rows are never in the frame `_skeptic_training_rows` receives and its
    `fold_index <` filter is belt-and-braces. That makes the filter untestable end to end —
    flipping it to `<=` changes nothing observable — and untestable is exactly how a guard
    comes to be deleted by someone tidying a redundant condition. So it is handed a frame
    that *does* contain this fold's calls, which is what a future caller assembling the
    out-of-sample file differently would hand it, and asked to leave them out.
    """
    from acsoe.research.walkforward import Fold

    oos = pl.read_parquet(report.oos_path)
    index = max(int(entry["fold_index"]) for entry in report.folds)
    own = oos.filter(pl.col("fold_index") == index)
    assert own.height, "this fold produced no out-of-sample rows, so nothing is excluded"
    entry = next(item for item in report.folds if int(item["fold_index"]) == index)

    rows = training._skeptic_training_rows(
        oos,
        dataset,
        Fold(
            fold_index=index,
            train_start_ts=int(entry["train_end_ts"]) - 1,
            train_end_ts=int(entry["train_end_ts"]),
            test_start_ts=int(entry["test_start_ts"]),
            test_end_ts=int(entry["test_end_ts"]),
            train_index=(),
            test_index=(),
            purged_count=0,
            embargoed_count=0,
            out_of_window_count=0,
        ),
        names=report.feature_names,
        interval_s=int(config.get("timeframes.decision_bar_s")),
        embargo_bars=int(config.get("backtest.embargo_bars")),
    )
    assert rows.height, "the guard excluded everything, so it proves nothing about this fold"
    assert int(rows["fold_index"].max()) < index


# --------------------------------------------------------------------------- #
# What it reports, and what it cannot report yet
# --------------------------------------------------------------------------- #


def test_the_effective_sample_size_is_reported_beside_the_row_count(report: Any) -> None:
    for entry in folds_with_a_skeptic(report):
        assert 0.0 < float(entry["skeptic_effective_sample_size"]) < float(
            entry["skeptic_rows"]
        )


def test_the_input_order_is_recorded_for_engine_15(report: Any) -> None:
    """Engine 15 builds the same vector live. A permuted order there is the same confident
    nonsense it is for the predictor, and the manifest is the only thing that says what the
    order was."""
    for entry in folds_with_a_skeptic(report):
        run_id = f"{report.run_id}-f{entry['fold_index']}"
        loaded = load_run(
            report.models_dir / run_id, expected_features=report.feature_names
        )
        recorded = loaded.manifest.extras["skeptic"]["input_names"]
        assert tuple(recorded) == (
            *report.feature_names,
            *training.SKEPTIC_EXTRA_INPUTS,
        )
        assert recorded == entry["skeptic_input_names"]


def test_the_veto_numbers_wait_for_the_operators_threshold(report: Any) -> None:
    """`skeptic.veto_threshold` is the operator's, after the walk-forward reports.

    Training still runs; only the numbers that need a threshold wait for one. The target
    rate among *all* BUY calls is reported regardless, because it needs no threshold and it
    is half of the comparison that says whether the skeptic helps.
    """
    assert load_default_config().get("skeptic.veto_threshold") is None
    for entry in folds_with_a_skeptic(report):
        assert entry["skeptic_veto_rate"] is None
        assert entry["skeptic_surviving_target_rate"] is None
        assert entry["skeptic_all_buy_target_rate"] is not None


def test_with_a_threshold_supplied_both_target_rates_are_reported(
    config: Any, dataset: Any, tmp_path: Path
) -> None:
    """The pair of numbers that is the only thing saying whether the skeptic is worth
    having: the target rate among the calls that survive the veto, beside the target rate
    among all BUY calls. A skeptic that vetoes a third of the calls and leaves the rate
    unchanged has cost a third of the opportunities for nothing.

    The threshold is supplied through a wrapper rather than written into
    `config/default.yaml`, which must keep the key **absent**: absent is what engine 15
    fails closed on and what the Phase 5 criterion reports PENDING for.
    """

    class WithVeto:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def get(self, key: str) -> Any:
            return 0.5 if key == "skeptic.veto_threshold" else self._inner.get(key)

    report = training.train_walkforward(
        dataset,
        config=WithVeto(config),
        models_dir=tmp_path / "models",
        derived_dir=tmp_path / "derived",
        now=NOW,
        max_folds=FOLDS,
    )
    later = folds_with_a_skeptic(report)
    assert later
    for entry in later:
        assert 0.0 <= float(entry["skeptic_veto_rate"]) <= 1.0
        assert entry["skeptic_all_buy_target_rate"] is not None


def test_the_skeptic_can_only_veto(report: Any) -> None:
    """Invariant 4, asserted on the source because the behaviour only appears in engine 15.

    There is no output of this training path that makes a trade more likely: it produces a
    probability of being **wrong**, and the only thing an engine can do with that is refuse.
    A `skeptic_approves`, a boost, or a confidence that widened a threshold would each be a
    model output overriding a gate.
    """
    import inspect

    source = inspect.getsource(training)
    for forbidden in ("skeptic_approve", "skeptic_boost", "approve=", "confidence_boost"):
        assert forbidden not in source, forbidden
    assert "wrong = label != 'target'" in source or "0 if label == LABEL_TARGET else 1" in source
