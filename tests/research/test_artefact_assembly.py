"""Spec 135 — the DI and the anomaly threshold, assembled from the Phase 5 study into new runs.

The subject is built the way the real one was:

* a **source run** trained here with ``prediction.di_percentile`` and
  ``anomaly.threshold_percentile`` both absent, so, like ``train-20260913T205245-067b2b9d``, it
  carries no ``di.npz``, no anomaly threshold, and an uncapped skeptic;
* a **study** for its last fold, in the study's file shapes, computed by the **trainer's own**
  ``_fit_and_score_di`` (handed a placeholder percentile, as the study's ``selfcheck`` did) and
  the fold's own forest, rather than by anything in the module under test;
* a **staged capped skeptic** from spec 136's module.

Then the fold is assembled through B's real ``StoreClient`` and loaded by the real engines 8, 13
and 15, which is what spec 135's Check When Done asks for; a double of any of them would be a
claim about the loader rather than a load.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import require_module

np = require_module("numpy", reason="numpy is not installed")
pl = require_module("polars", reason="polars is not installed")
require_module("lightgbm", reason="lightgbm is not installed")
joblib = require_module("joblib", reason="joblib is not installed")

from acsoe.clients.store.client import StoreClient, StoreError  # noqa: E402
from acsoe.engines.anomaly.engine import _read as read_anomaly  # noqa: E402
from acsoe.engines.prediction.engine import _read as read_prediction  # noqa: E402
from acsoe.engines.skeptic.engine import _read as read_skeptic  # noqa: E402
from acsoe.modelling import di as di_module  # noqa: E402
from acsoe.modelling.artefacts import identity_digest, sha256_file  # noqa: E402
from acsoe.research import artefact_assembly as assembly  # noqa: E402
from acsoe.research import skeptic_cap, training  # noqa: E402
from tests.harness.doubles import load_default_config  # noqa: E402
from tests.research.test_skeptic_cap import WithCap  # noqa: E402
from tests.research.test_training import NOW, dataset_for  # noqa: E402

FOLDS = 4
LAST = FOLDS - 1
ASSEMBLED_AT = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


class Answering:
    """The committed config with the named keys answered, and nothing else changed."""

    def __init__(self, inner: Any, **answers: Any) -> None:
        self._inner = inner
        self._answers = answers

    def get(self, key: str) -> Any:
        if key in self._answers:
            return self._answers[key]
        return self._inner.get(key)


def today() -> Any:
    """The config the thresholds are read from: the committed one, which carries both."""
    config = load_default_config()
    assert config.get("prediction.di_percentile") is not None
    assert config.get("anomaly.threshold_percentile") is not None
    return config


def tree_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
    }


@pytest.fixture(scope="module")
def world(tmp_path_factory: Any) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("assembly")
    base = load_default_config()
    # The source run as the real one was trained: both percentiles absent.
    trained_under = Answering(
        base, **{"prediction.di_percentile": None, "anomaly.threshold_percentile": None}
    )
    dataset = dataset_for(base, random_walk=False)
    models = root / "models"
    report = training.train_walkforward(
        dataset,
        config=trained_under,
        models_dir=models,
        derived_dir=root / "derived",
        now=NOW,
        max_folds=FOLDS,
    )
    source_dir = models / f"{report.run_id}-f{LAST}"
    assert not (source_dir / "di.npz").exists(), "the source run must carry no DI, as the real one"
    assert (source_dir / "skeptic.txt").is_file(), "the source fold trained no skeptic to exclude"

    study = root / "study"
    study.mkdir()
    dataset.sort(["decision_ts", "pair"]).write_parquet(
        study / "dataset_sorted_by_decision_ts.parquet"
    )
    source = skeptic_cap.load_source_fold(models, report.run_id, LAST)
    fold = source.manifest.fold
    names = tuple(source.manifest.feature_names)
    train = dataset.filter(
        (pl.col("decision_ts") >= fold.train_start_ts)
        & (pl.col("decision_ts") < fold.test_start_ts)
        & (pl.col("label_window_end_ts") < fold.test_start_ts)
        & (
            pl.col("decision_ts")
            < fold.test_start_ts
            - int(base.get("backtest.embargo_bars")) * int(base.get("timeframes.decision_bar_s"))
        )
    ).sort(["decision_ts", "pair"])
    assert identity_digest(list(train["pair"]), list(train["decision_ts"])) == (
        source.manifest.training_identity
    ), "the fixture's training rows are not the fold's"

    # The study's DI: the trainer's own function with a discarded placeholder percentile.
    fit, _values, _refusals = training._fit_and_score_di(
        Answering(base, **{"prediction.di_percentile": 0.5}),
        train,
        train.head(0),
        source.scaler,
        names,
        int(source.manifest.seeds["train"]),
        np.empty((0, len(names))),
    )
    reference_identity = identity_digest(
        [entry.split("|")[0] for entry in fit.identity],
        [int(entry.split("|")[1]) for entry in fit.identity],
    )
    # The study's anomaly scores: the fold's own forest over its complete training rows.
    inputs = training._anomaly_input_names(names)
    matrix = training._anomaly_matrix(train, source.scaler, names, inputs)
    complete = np.isfinite(matrix).all(axis=1)
    forest = joblib.load(source_dir / "anomaly.joblib")
    scores = -forest.score_samples(matrix[complete])

    np.savez(study / f"fold_{LAST:03d}.npz", anomaly_train_scores=scores,
             di_distribution=np.zeros(3))
    np.savez(study / f"excl_fold_{LAST:03d}.npz", di_distribution=fit.distribution,
             span_s=np.int64(fit.exclusion_s))
    summary = {
        "fold_index": LAST,
        "run_id": source.manifest.run_id,
        "training_identity": source.manifest.training_identity,
        "di": {"reference_rows": fit.rows, "reference_identity": reference_identity},
    }
    (study / f"fold_{LAST:03d}.json").write_bytes(json.dumps(summary).encode("utf-8"))

    staging = root / "staging"
    skeptic_cap.stage_fold(
        LAST,
        config=WithCap(base, 2),
        config_digest=training._config_digest(base),
        source=source,
        oos=pl.read_parquet(report.oos_path, columns=list(skeptic_cap.OOS_READ)),
        dataset_path=study / "dataset_sorted_by_decision_ts.parquet",
        staging_root=staging,
    )
    return {
        "report": report,
        "models": models,
        "source_dir": source_dir,
        "study": study,
        "staging": staging,
        "fit": fit,
        "scores": scores,
        "root": root,
    }


def inputs_of(world: dict[str, Any], **overrides: Any) -> Any:
    arguments = {
        "models_dir": world["models"],
        "study_dir": world["study"],
        "staging_dir": world["staging"],
        "oos_path": world["report"].oos_path,
        "source_run_id": world["report"].run_id,
    }
    arguments.update(overrides)
    return assembly.AssemblyInputs(**arguments)


def store_for(world: dict[str, Any], artefact_root: Path) -> Any:
    return StoreClient(world["root"] / "unused.sqlite", models_dir=artefact_root)


@pytest.fixture(scope="module")
def assembled(world: dict[str, Any], tmp_path_factory: Any) -> dict[str, Any]:
    """One fold assembled into a fresh artefact root, with the source tree hashed around it."""
    before = tree_hashes(world["source_dir"])
    root = tmp_path_factory.mktemp("assembled")
    directory = assembly.assemble_fold(
        LAST,
        inputs=inputs_of(world),
        config=today(),
        store=store_for(world, root),
        now=ASSEMBLED_AT,
    )
    return {
        "directory": directory,
        "root": root,
        "before": before,
        "manifest": json.loads((directory / "manifest.json").read_bytes().decode("utf-8")),
    }


# --------------------------------------------------------------------------- #
# What an assembled fold is
# --------------------------------------------------------------------------- #


def test_the_run_id_is_the_source_fold_run_plus_the_phase_7_suffix(
    world: dict[str, Any], assembled: dict[str, Any]
) -> None:
    expected = f"{world['report'].run_id}-f{LAST}-p7"
    assert assembled["directory"].name == expected
    assert assembled["manifest"]["run_id"] == expected
    assert assembly.assembled_run_id(LAST, world["report"].run_id) == expected


def test_engines_8_13_and_15_load_the_assembled_fold(assembled: dict[str, Any]) -> None:
    """Spec 135's first check, through each engine's own loader: every hash, the feature order,
    a DI with its exclusion span, an anomaly threshold, a skeptic input order."""
    directory, run_id = assembled["directory"], assembled["directory"].name
    prediction = read_prediction(directory, run_id)
    anomaly = read_anomaly(directory, run_id)
    skeptic = read_skeptic(directory, run_id)
    assert prediction.di.exclusion_s == 48 * 900
    assert anomaly.threshold == assembled["manifest"]["extras"]["anomaly"]["threshold"]
    assert skeptic.input_names == tuple(assembled["manifest"]["extras"]["skeptic"]["input_names"])


def test_both_thresholds_are_the_quantiles_of_the_study_files_at_todays_percentiles(
    world: dict[str, Any], assembled: dict[str, Any]
) -> None:
    """Recomputed here from the study's arrays, never read back from what the module wrote."""
    config = today()
    di_fit = di_module.load(assembled["directory"] / "di.npz")
    assert di_fit.threshold == float(
        np.quantile(world["fit"].distribution, float(config.get("prediction.di_percentile")))
    )
    assert np.array_equal(di_fit.distribution, world["fit"].distribution)
    assert di_fit.identity == world["fit"].identity
    assert np.array_equal(di_fit.reference, world["fit"].reference)
    assert assembled["manifest"]["extras"]["anomaly"]["threshold"] == float(
        np.quantile(world["scores"], float(config.get("anomaly.threshold_percentile")))
    )
    result = assembly.verify_assembled(
        assembled["directory"], study_dir=world["study"], fold_index=LAST, config=config
    )
    assert result["di_threshold"] == result["di_threshold_recomputed"]


def test_the_skeptic_is_the_staged_capped_one_and_never_the_source_s(
    world: dict[str, Any], assembled: dict[str, Any]
) -> None:
    staged = skeptic_cap.read_staged(world["staging"], LAST)
    copied = assembled["directory"] / "skeptic.txt"
    assert sha256_file(copied) == staged.meta["skeptic_sha256"]
    assert sha256_file(copied) != sha256_file(world["source_dir"] / "skeptic.txt"), (
        "the capped skeptic is byte-identical to the uncapped one, so this fixture cannot tell "
        "which was copied"
    )
    recorded = assembled["manifest"]["extras"]["skeptic"]
    assert recorded["training_identity"] == staged.meta["training_identity"]
    assert recorded["cap_folds"] == 2


def test_the_predictor_files_are_the_source_s_byte_for_byte(
    world: dict[str, Any], assembled: dict[str, Any]
) -> None:
    for name in ("model.txt", "calibrators.json", "anomaly.joblib", "scaler.json"):
        assert sha256_file(assembled["directory"] / name) == sha256_file(
            world["source_dir"] / name
        ), name
    provenance = assembled["manifest"]["extras"]["provenance"]
    assert provenance["source_sha256"]["model.txt"] == sha256_file(
        world["source_dir"] / "model.txt"
    )


def test_the_manifest_names_both_config_digests_and_which_is_which(
    world: dict[str, Any], assembled: dict[str, Any]
) -> None:
    source_manifest = json.loads((world["source_dir"] / "manifest.json").read_bytes())
    provenance = assembled["manifest"]["extras"]["provenance"]
    assert assembled["manifest"]["config_digest"] == source_manifest["config_digest"]
    assert provenance["training_config_digest"] == source_manifest["config_digest"]
    assert provenance["threshold_config_digest"] == training._config_digest(today())
    assert provenance["training_config_digest"] != provenance["threshold_config_digest"], (
        "the fixture trained and assembled under one digest, so it cannot show the two recorded"
    )
    assert "not a di.fit output" in assembled["manifest"]["extras"]["di"]["distribution_source"]


def test_the_source_directory_is_never_written(
    world: dict[str, Any], assembled: dict[str, Any]
) -> None:
    assert tree_hashes(world["source_dir"]) == assembled["before"]


def test_a_fold_is_assembled_once(world: dict[str, Any], assembled: dict[str, Any]) -> None:
    with pytest.raises(StoreError, match="already exists"):
        assembly.assemble_fold(
            LAST,
            inputs=inputs_of(world),
            config=today(),
            store=store_for(world, assembled["root"]),
            now=ASSEMBLED_AT,
        )


# --------------------------------------------------------------------------- #
# What is refused, and that a refusal leaves nothing behind
# --------------------------------------------------------------------------- #


def refused(world: dict[str, Any], tmp_path: Path, match: str, **overrides: Any) -> None:
    root = tmp_path / "models"
    with pytest.raises(assembly.AssemblyError, match=match):
        assembly.assemble_fold(
            LAST,
            inputs=inputs_of(world, **overrides),
            config=today(),
            store=store_for(world, root),
            now=ASSEMBLED_AT,
        )
    assert not root.exists() or not any(root.iterdir()), "a refused fold left a directory"


def study_copy(world: dict[str, Any], tmp_path: Path) -> Path:
    import shutil

    target = tmp_path / "study"
    shutil.copytree(world["study"], target)
    return target


def test_a_reference_one_row_off_the_study_s_is_refused(
    world: dict[str, Any], tmp_path: Path
) -> None:
    """Spec 135's planted wrong reference: the study's recorded identity is the reference minus
    its last row, so the rebuilt reference is one row off what the study saw."""
    study = study_copy(world, tmp_path)
    path = study / f"fold_{LAST:03d}.json"
    summary = json.loads(path.read_bytes())
    ids = world["fit"].identity[:-1]
    summary["di"]["reference_identity"] = identity_digest(
        [entry.split("|")[0] for entry in ids], [int(entry.split("|")[1]) for entry in ids]
    )
    path.write_bytes(json.dumps(summary).encode("utf-8"))
    refused(world, tmp_path, "is not the study's", study_dir=study)


def test_a_fold_with_no_staged_capped_skeptic_is_refused(
    world: dict[str, Any], tmp_path: Path
) -> None:
    """Never assembled with the uncapped skeptic instead."""
    with pytest.raises(skeptic_cap.CappedSkepticError, match="no staged capped skeptic"):
        assembly.assemble_fold(
            LAST,
            inputs=inputs_of(world, staging_dir=tmp_path / "empty"),
            config=today(),
            store=store_for(world, tmp_path / "models"),
            now=ASSEMBLED_AT,
        )
    assert not (tmp_path / "models").exists()


def test_a_distribution_that_is_not_the_module_s_statistic_is_refused(
    world: dict[str, Any], tmp_path: Path
) -> None:
    """Every value moved by 1e-6: an order of magnitude past the tolerance, far inside anything
    a threshold would show."""
    study = study_copy(world, tmp_path)
    np.savez(
        study / f"excl_fold_{LAST:03d}.npz",
        di_distribution=world["fit"].distribution + 1e-6,
        span_s=np.int64(world["fit"].exclusion_s),
    )
    refused(world, tmp_path, "differs from modelling.di", study_dir=study)


def test_a_distribution_of_the_wrong_length_is_refused(
    world: dict[str, Any], tmp_path: Path
) -> None:
    """One value per reference row, in the reference's order; one short is another fold's."""
    study = study_copy(world, tmp_path)
    np.savez(
        study / f"excl_fold_{LAST:03d}.npz",
        di_distribution=world["fit"].distribution[:-1],
        span_s=np.int64(world["fit"].exclusion_s),
    )
    refused(world, tmp_path, "distribution values against", study_dir=study)


def test_a_distribution_measured_over_another_span_is_refused(
    world: dict[str, Any], tmp_path: Path
) -> None:
    study = study_copy(world, tmp_path)
    np.savez(
        study / f"excl_fold_{LAST:03d}.npz",
        di_distribution=world["fit"].distribution,
        span_s=np.int64(world["fit"].exclusion_s - 900),
    )
    refused(world, tmp_path, "the study excluded", study_dir=study)


def test_anomaly_scores_that_are_not_the_detector_s_training_rows_are_refused(
    world: dict[str, Any], tmp_path: Path
) -> None:
    study = study_copy(world, tmp_path)
    np.savez(
        study / f"fold_{LAST:03d}.npz",
        anomaly_train_scores=world["scores"][:-1],
        di_distribution=np.zeros(3),
    )
    refused(world, tmp_path, "anomaly training scores against", study_dir=study)


def test_a_study_of_another_run_is_refused(world: dict[str, Any], tmp_path: Path) -> None:
    study = study_copy(world, tmp_path)
    path = study / f"fold_{LAST:03d}.json"
    summary = json.loads(path.read_bytes())
    summary["run_id"] = "train-00000000T000000-00000000-f3"
    path.write_bytes(json.dumps(summary).encode("utf-8"))
    refused(world, tmp_path, "is for", study_dir=study)


def test_a_withheld_percentile_is_refused_rather_than_defaulted(
    world: dict[str, Any], tmp_path: Path
) -> None:
    with pytest.raises(assembly.AssemblyError, match="nothing here chooses a threshold"):
        assembly.assemble_fold(
            LAST,
            inputs=inputs_of(world),
            config=Answering(today(), **{"prediction.di_percentile": None}),
            store=store_for(world, tmp_path / "models"),
            now=ASSEMBLED_AT,
        )


def test_a_reference_that_is_all_buy_calls_is_refused(
    world: dict[str, Any], tmp_path: Path
) -> None:
    """``di_fitted_on_predictor_training_set``'s second question. An out-of-sample file in which
    every reference row is a BUY call stands in for a reference drawn from the BUY subset."""
    oos = pl.read_parquet(world["report"].oos_path)
    reference = pl.DataFrame(
        {
            "pair": [entry.split("|")[0] for entry in world["fit"].identity],
            "decision_ts": [int(entry.split("|")[1]) for entry in world["fit"].identity],
        }
    )
    forged = pl.concat(
        [
            oos.select(["pair", "decision_ts", "is_buy"]),
            reference.with_columns(pl.lit(True).alias("is_buy")).cast(
                {"decision_ts": oos.schema["decision_ts"]}
            ),
        ]
    )
    path = tmp_path / "oos_all_buy.parquet"
    forged.write_parquet(path)
    refused(world, tmp_path, "BUY subset", oos_path=path)


def test_a_dataset_that_is_not_the_one_the_fold_trained_on_is_refused(
    world: dict[str, Any], tmp_path: Path
) -> None:
    """One extra row the purge would remove: the training rows, and so their identity, are
    unchanged, and only the recomputed purge count says the dataset is not the fold's."""
    study = study_copy(world, tmp_path)
    path = study / "dataset_sorted_by_decision_ts.parquet"
    frame = pl.read_parquet(path)
    source = skeptic_cap.load_source_fold(world["models"], world["report"].run_id, LAST)
    fold = source.manifest.fold
    purged = frame.filter(
        (pl.col("decision_ts") < fold.test_start_ts)
        & (pl.col("label_window_end_ts") >= fold.test_start_ts)
    )
    assert purged.height, "the fold purged nothing, so there is no purged row to copy"
    extra = purged.head(1).with_columns(pl.lit("ZZZUSD").alias("pair"))
    path.unlink()
    pl.concat([frame, extra]).sort(["decision_ts", "pair"]).write_parquet(path)
    refused(world, tmp_path, "purged_count recomputed", study_dir=study)


def test_a_skeptic_staged_for_another_run_is_refused(world: dict[str, Any], tmp_path: Path) -> None:
    import shutil

    staging = tmp_path / "staging"
    shutil.copytree(world["staging"], staging)
    meta_path = staging / f"fold_{LAST:03d}" / skeptic_cap.SKEPTIC_META_NAME
    meta = json.loads(meta_path.read_bytes())
    meta["source_run_id"] = "train-00000000T000000-00000000-f3"
    meta_path.write_bytes(json.dumps(meta).encode("utf-8"))
    refused(world, tmp_path, "the staged skeptic was trained for", staging_dir=staging)


def test_the_verification_leaves_out_a_row_exactly_one_span_away() -> None:
    """The exclusion is inclusive at the span, as `modelling.di.fit` draws it. The fixture puts
    a duplicate of each row exactly one span later, so a verification that kept rows at the span
    would find a neighbour at distance zero and disagree with the fit on every row."""
    rng = np.random.default_rng(3)
    span_bars, rows = 2, 16
    base = rng.normal(size=(rows, 3))
    reference = base.copy()
    reference[span_bars:] = base[:-span_bars]
    stamps = np.arange(rows, dtype=np.int64) * 900
    fitted = di_module.fit(
        reference,
        [f"AAAUSD|{int(ts)}" for ts in stamps],
        neighbours=1,
        percentile=0.5,
        decision_ts=stamps,
        exclusion_s=span_bars * 900,
    )
    worst = assembly._verify_distribution(
        reference,
        stamps,
        fitted.distribution,
        neighbours=1,
        exclusion_s=span_bars * 900,
        fold_index=0,
    )
    assert worst <= assembly.MODULE_TOLERANCE


def test_a_training_row_that_is_not_the_fold_s_is_refused(
    world: dict[str, Any], tmp_path: Path
) -> None:
    """The oldest training row renamed: every count is unchanged and the row is far older than
    the DI's thirty-day window, so the reference is unchanged too. Only the training identity,
    recomputed and compared with the fold's, can see it."""
    study = study_copy(world, tmp_path)
    path = study / "dataset_sorted_by_decision_ts.parquet"
    frame = pl.read_parquet(path)
    source = skeptic_cap.load_source_fold(world["models"], world["report"].run_id, LAST)
    first = int(source.manifest.fold.train_start_ts)
    oldest = frame.filter(pl.col("decision_ts") == first)
    assert oldest.height, "no row sits on the first training bar"
    renamed = frame.with_columns(
        pl.when((pl.col("decision_ts") == first) & (pl.col("pair") == oldest["pair"][0]))
        .then(pl.lit("ZZZUSD"))
        .otherwise(pl.col("pair"))
        .alias("pair")
    )
    path.unlink()
    renamed.sort(["decision_ts", "pair"]).write_parquet(path)
    refused(world, tmp_path, "are not the fold's", study_dir=study)


def test_without_a_store_the_run_is_created_once_beside_its_source(
    world: dict[str, Any],
) -> None:
    """The command line's path: no store client, because `research/` never imports `clients/`,
    and the trainer's own `mkdir(exist_ok=False)` under the source run's artefact root. The
    refusal of an existing run is the same primitive the store uses."""
    directory = assembly.assemble_fold(
        LAST, inputs=inputs_of(world), config=today(), store=None, now=ASSEMBLED_AT
    )
    assert directory == world["models"] / f"{world['report'].run_id}-f{LAST}-p7"
    assert read_prediction(directory, directory.name).di.exclusion_s == 48 * 900
    with pytest.raises(FileExistsError):
        assembly.assemble_fold(
            LAST, inputs=inputs_of(world), config=today(), store=None, now=ASSEMBLED_AT
        )
