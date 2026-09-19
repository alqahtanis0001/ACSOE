"""Spec 136 — the 13-fold skeptic cap, trained for folds that already exist, into staging.

The subject is a four-fold run trained here from the constructed series, exactly as
`tests/research/test_skeptic_training.py` trains its own, so the saved skeptics are the
trainer's and the staging module can be held to them. The dataset is written to a parquet
file because that is how the module reads it; the rows are the ones the run trained on.

Three claims, each proved against something the module did not compute:

* **uncapped, it is the trainer.** The replication retrains a fold with the cap disabled and must
  reproduce the saved `skeptic.txt` exactly: identity, row count and every probability;
* **capped, it trains on the ruled window and nothing else.** The staged identity is compared
  with one recomputed from the out-of-sample file by `recompute_identity`, which is written from
  the ruling rather than through `_skeptic_training_rows`;
* **a staged skeptic is written once and read back only if it is intact and capped**, because
  spec 135 assembles from it and must never fall back to the uncapped one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import require_module

pl = require_module("polars", reason="polars is not installed")
require_module("lightgbm", reason="lightgbm is not installed")

from acsoe.modelling.artefacts import identity_digest  # noqa: E402
from acsoe.research import skeptic_cap, training  # noqa: E402
from tests.harness.doubles import load_default_config  # noqa: E402
from tests.research.test_skeptic_training import WithVetoThreshold  # noqa: E402
from tests.research.test_training import NOW, dataset_for  # noqa: E402

FOLDS = 4
LAST = FOLDS - 1


class WithCap:
    """A config answering ``training.skeptic_cap_folds``, and everything else as given.

    Supplied here rather than read from `config/default.yaml`, so the tests do not move when
    the committed value does and do not depend on the order in which the key's model field and
    its YAML land.
    """

    def __init__(self, inner: Any, cap: int | None) -> None:
        self._inner = inner
        self._cap = cap

    def get(self, key: str) -> Any:
        if key == skeptic_cap.CAP_KEY:
            return self._cap
        return self._inner.get(key)


@pytest.fixture(scope="module")
def config() -> Any:
    return WithVetoThreshold(load_default_config(), 0.5)


@pytest.fixture(scope="module")
def run(config: Any, tmp_path_factory: Any) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("skeptic-cap")
    dataset = dataset_for(load_default_config(), random_walk=False)
    report = training.train_walkforward(
        dataset,
        config=config,
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=FOLDS,
    )
    dataset_path = root / "dataset_sorted.parquet"
    dataset.sort(["decision_ts", "pair"]).write_parquet(dataset_path)
    return {
        "report": report,
        "dataset_path": dataset_path,
        "oos": pl.read_parquet(report.oos_path, columns=list(skeptic_cap.OOS_READ)),
        "root": root,
    }


def source(run: dict[str, Any], fold_index: int) -> Any:
    report = run["report"]
    return skeptic_cap.load_source_fold(report.models_dir, report.run_id, fold_index)


def trained(run: dict[str, Any], config: Any, cap: int | None, fold_index: int = LAST) -> Any:
    return skeptic_cap.train_fold_skeptic(
        fold_index,
        config=config,
        cap_folds=cap,
        source=source(run, fold_index),
        oos=run["oos"],
        dataset_path=run["dataset_path"],
    )


def recomputed(run: dict[str, Any], config: Any, cap: int, fold_index: int = LAST) -> str:
    return skeptic_cap.recompute_identity(
        fold_index,
        cap_folds=cap,
        source=source(run, fold_index),
        oos=run["oos"],
        dataset_path=run["dataset_path"],
        embargo_bars=int(config.get("backtest.embargo_bars")),
        interval_s=int(config.get("timeframes.decision_bar_s")),
    )


# --------------------------------------------------------------------------- #
# Uncapped, it is the trainer
# --------------------------------------------------------------------------- #


def test_the_uncapped_retrain_reproduces_the_saved_skeptic_exactly(
    run: dict[str, Any], config: Any
) -> None:
    """Spec 136 step 2, on the constructed run. Zero, not a tolerance: the same rows, seed,
    settings and thread count give LightGBM's deterministic mode the same trees."""
    result = skeptic_cap.replicate(
        LAST,
        config=config,
        source=source(run, LAST),
        oos=run["oos"],
        dataset_path=run["dataset_path"],
    )
    assert result["identity"] == result["recorded_identity"]
    assert result["rows"] == result["recorded_rows"]
    assert result["buy_calls"] > 0, "the fold has no BUY call, so no probability was compared"
    assert result["largest_probability_difference"] == 0.0


def test_a_retrain_that_differs_from_the_saved_skeptic_is_refused(
    run: dict[str, Any], config: Any
) -> None:
    """The control for the test above: the replication must be able to say no. A quarter of the
    trees trains a different model on the same rows, so the identity and the row count still
    agree and only the probabilities differ, which is the comparison this control exercises.

    Two weaker controls stayed silent when first tried, and both are recorded so nobody reaches
    for them again. A different seed: with no bagging and no feature sampling LightGBM's trees do
    not depend on it. One fewer tree: on this learnable series the last rounds change nothing."""

    class QuarterTrees:
        def get(self, key: str) -> Any:
            if key == "training.num_trees":
                return int(config.get(key)) // 4
            return config.get(key)

    with pytest.raises(skeptic_cap.CappedSkepticError, match="does not replicate"):
        skeptic_cap.replicate(
            LAST,
            config=QuarterTrees(),
            source=source(run, LAST),
            oos=run["oos"],
            dataset_path=run["dataset_path"],
        )


# --------------------------------------------------------------------------- #
# Capped, it trains on the ruled window and nothing else
# --------------------------------------------------------------------------- #


def test_a_capped_skeptic_trains_only_on_the_last_cap_folds(
    run: dict[str, Any], config: Any
) -> None:
    """Fold 3 capped at one fold learns from fold 2's calls only. Its identity must equal the
    one recomputed from the ruling, and must differ from the uncapped identity, which also holds
    fold 1's calls: without the second assertion a cap that did nothing would pass the first
    whenever the earlier folds happened to contribute no eligible row."""
    model, report = trained(run, config, cap=1)
    assert model is not None, report
    assert report["skeptic_training_identity"] == recomputed(run, config, cap=1)

    _uncapped_model, uncapped = trained(run, config, cap=None)
    assert uncapped["skeptic_training_identity"] != report["skeptic_training_identity"]
    assert uncapped["skeptic_rows"] > report["skeptic_rows"]


def test_the_capped_rows_come_from_the_window_and_are_all_eligible(
    run: dict[str, Any], config: Any
) -> None:
    """The same claim from the other side, by fold index: every row the capped selection keeps
    is a BUY call of fold ``LAST - 1`` that the purge and embargo let through."""
    report = run["report"]
    entry = next(item for item in report.folds if int(item["fold_index"]) == LAST)
    interval_s = int(config.get("timeframes.decision_bar_s"))
    embargo = int(config.get("backtest.embargo_bars")) * interval_s
    expected = run["oos"].filter(
        pl.col("is_buy")
        & (pl.col("fold_index") == LAST - 1)
        & (pl.col("label_window_end_ts") < int(entry["test_start_ts"]))
        & (pl.col("decision_ts") < int(entry["test_start_ts"]) - embargo)
    )
    _model, capped = trained(run, config, cap=1)
    assert capped["skeptic_training_identity"] == identity_digest(
        [str(value) for value in expected["pair"]],
        [int(value) for value in expected["decision_ts"]],
    )


def test_a_cap_wider_than_the_history_is_the_uncapped_skeptic(
    run: dict[str, Any], config: Any
) -> None:
    """Fold 3 capped at thirteen folds reaches back past fold 0, so it sees everything the
    uncapped skeptic sees. The cap bites at ``k - cap`` and nowhere else."""
    _a, capped = trained(run, config, cap=13)
    _b, uncapped = trained(run, config, cap=None)
    assert capped["skeptic_training_identity"] == uncapped["skeptic_training_identity"]


def test_the_trainer_applies_the_cap_itself_over_the_whole_dataset(
    run: dict[str, Any], config: Any
) -> None:
    """The cap as `_fit_skeptic` applies it, handed **every** earlier fold and the whole dataset.

    The staging module reads only the dataset rows from the capped window onward, to keep a
    fold's memory bounded, so behind it the earlier folds' calls find no feature row and drop
    out of the join whatever the trainer does. That makes the module's own tests blind to the
    trainer's filter: a mutation removing it survived them. So the trainer is asked directly,
    with nothing narrowed in front of it, and its identity must be the capped one.
    """
    report = run["report"]
    loaded = source(run, LAST)
    oos = run["oos"]
    own = oos.filter(pl.col("fold_index") == LAST)
    _model, capped = training._fit_skeptic(
        oos.filter(pl.col("fold_index") < LAST),
        pl.read_parquet(run["dataset_path"]),
        loaded.manifest.fold,  # type: ignore[arg-type]
        config=config,
        names=report.feature_names,
        seed=int(loaded.manifest.seeds["train"]),
        scaler=loaded.scaler,
        oos=own,
        buys=[bool(value) for value in own["is_buy"]],
        cap_folds=1,
    )
    assert capped["skeptic_training_identity"] == recomputed(run, config, cap=1)


def test_a_replication_whose_identity_or_row_count_disagrees_is_refused(
    run: dict[str, Any], config: Any
) -> None:
    """The replication's other two comparisons, each broken alone. The saved skeptic is left
    as it is and only the record of it is changed, so the probabilities still agree and the
    refusal can only come from the comparison under test."""
    loaded = source(run, LAST)
    recorded = dict(loaded.manifest.extras["skeptic"])
    for field, wrong in (("training_identity", "0" * 64), ("rows", int(recorded["rows"]) + 1)):
        extras = {**loaded.manifest.extras, "skeptic": {**recorded, field: wrong}}
        altered = loaded.model_copy(
            update={"manifest": loaded.manifest.model_copy(update={"extras": extras})}
        )
        with pytest.raises(skeptic_cap.CappedSkepticError, match="does not replicate"):
            skeptic_cap.replicate(
                LAST,
                config=config,
                source=altered,
                oos=run["oos"],
                dataset_path=run["dataset_path"],
            )


def test_an_out_of_sample_file_missing_a_row_of_the_fold_is_refused(
    run: dict[str, Any], config: Any
) -> None:
    """The fold's own out-of-sample rows must be the fold's test rows, every one of them: a
    short file would score the veto report on a subset and say nothing."""
    oos = run["oos"]
    own = oos.filter(pl.col("fold_index") == LAST)
    short = pl.concat([oos.filter(pl.col("fold_index") != LAST), own.tail(own.height - 1)])
    with pytest.raises(skeptic_cap.CappedSkepticError, match="out-of-sample rows against"):
        skeptic_cap.train_fold_skeptic(
            LAST,
            config=config,
            cap_folds=1,
            source=source(run, LAST),
            oos=short,
            dataset_path=run["dataset_path"],
        )


def test_a_cap_that_is_not_positive_is_refused_by_the_trainer() -> None:
    frame = pl.DataFrame({"fold_index": [0, 1]})
    with pytest.raises(training.TrainingError, match="positive number of folds"):
        training._capped(frame, 2, 0)


# --------------------------------------------------------------------------- #
# Staging: written once, read back only intact and capped
# --------------------------------------------------------------------------- #


def stage(run: dict[str, Any], config: Any, root: Path, cap: int | None = 1) -> Any:
    return skeptic_cap.stage_fold(
        LAST,
        config=WithCap(config, cap),
        config_digest="d" * 64,
        source=source(run, LAST),
        oos=run["oos"],
        dataset_path=run["dataset_path"],
        staging_root=root,
    )


def test_a_staged_skeptic_reads_back_with_its_identity(
    run: dict[str, Any], config: Any, tmp_path: Path
) -> None:
    staged = stage(run, config, tmp_path)
    back = skeptic_cap.read_staged(tmp_path, LAST)
    assert back.meta == staged.meta
    assert back.meta["cap_folds"] == 1
    assert back.meta["earliest_fold"] == LAST - 1
    assert back.meta["training_identity"] == recomputed(run, config, cap=1)
    assert back.meta["source_run_id"] == f"{run['report'].run_id}-f{LAST}"


def test_a_fold_is_staged_once(run: dict[str, Any], config: Any, tmp_path: Path) -> None:
    stage(run, config, tmp_path)
    with pytest.raises(FileExistsError):
        stage(run, config, tmp_path)


def test_an_uncapped_config_stages_nothing(
    run: dict[str, Any], config: Any, tmp_path: Path
) -> None:
    """Staging the uncapped skeptic under this name is the one mistake spec 135 must never be
    able to assemble, so the refusal is here rather than there."""
    with pytest.raises(skeptic_cap.CappedSkepticError, match="uncapped skeptic"):
        stage(run, config, tmp_path, cap=None)
    assert not (tmp_path / f"fold_{LAST:03d}").exists()


def test_an_unstaged_fold_is_refused_rather_than_read(tmp_path: Path) -> None:
    with pytest.raises(skeptic_cap.CappedSkepticError, match="no staged capped skeptic"):
        skeptic_cap.read_staged(tmp_path, LAST)


def test_a_staged_skeptic_whose_file_changed_is_refused(
    run: dict[str, Any], config: Any, tmp_path: Path
) -> None:
    staged = stage(run, config, tmp_path)
    staged.model_path.write_bytes(staged.model_path.read_bytes() + b"\n")
    with pytest.raises(skeptic_cap.CappedSkepticError, match="differs from its recorded hash"):
        skeptic_cap.read_staged(tmp_path, LAST)


def test_a_staged_record_with_no_cap_is_refused(
    run: dict[str, Any], config: Any, tmp_path: Path
) -> None:
    staged = stage(run, config, tmp_path)
    meta_path = staged.directory / skeptic_cap.SKEPTIC_META_NAME
    meta = json.loads(meta_path.read_bytes().decode("utf-8"))
    meta["cap_folds"] = None
    meta_path.write_bytes(json.dumps(meta).encode("utf-8"))
    with pytest.raises(skeptic_cap.CappedSkepticError, match="records no cap"):
        skeptic_cap.read_staged(tmp_path, LAST)


# --------------------------------------------------------------------------- #
# The command line's --cap, for the window before the key's model field lands
# --------------------------------------------------------------------------- #


class Undeclared:
    """A config whose model does not declare the cap key, as `Config.get` reports it."""

    def get(self, key: str) -> Any:
        from acsoe.platform.config import ConfigKeyError

        if key == skeptic_cap.CAP_KEY:
            raise ConfigKeyError(key)
        return None


def test_the_flag_supplies_the_cap_to_a_config_that_cannot_declare_it() -> None:
    assert skeptic_cap._with_cap(Undeclared(), 13).get(skeptic_cap.CAP_KEY) == 13


def test_the_flag_agreeing_with_a_declared_cap_is_accepted() -> None:
    config = WithCap(Undeclared(), 13)
    assert skeptic_cap._with_cap(config, 13).get(skeptic_cap.CAP_KEY) == 13


def test_the_flag_disagreeing_with_a_declared_cap_is_refused_never_overriding_it() -> None:
    with pytest.raises(skeptic_cap.CappedSkepticError, match="disagrees with the config"):
        skeptic_cap._with_cap(WithCap(Undeclared(), 12), 13)


def test_a_flag_that_is_not_positive_is_refused() -> None:
    with pytest.raises(skeptic_cap.CappedSkepticError, match="positive number of folds"):
        skeptic_cap._with_cap(Undeclared(), 0)
