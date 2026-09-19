"""Phase 7's run directories, assembled from a trained run and the Phase 5 study. Spec 135.

Operator ruling 2026-09-19: the DI and anomaly thresholds are **rebuilt from the Phase 5
study, not refitted**. The walk-forward ``train-20260913T205245-067b2b9d`` trained with
``prediction.di_percentile`` and ``anomaly.threshold_percentile`` both absent, so none of its
folds carries a ``di.npz`` or an anomaly threshold, and engines 8 and 13 refuse every one of
them. The study of 2026-09-14 and 2026-09-15 recovered, per fold, the DI's reference set and
its leave-one-out distribution with the 48-bar exclusion, and the anomaly detector's training
scores. This module turns those into what the engines load, **one new directory per fold**,
written once and complete:

* ``model.txt``, ``calibrators.json`` and ``anomaly.joblib`` copied byte for byte from the
  source fold, and ``scaler.json`` rewritten from the verified scaler and required to equal the
  source's bytes, each with its source sha256 recorded;
* ``di.npz``: the reference **rebuilt with the trainer's own selection** and required to equal
  the study's recorded ``reference_identity``; the study's distribution; the threshold
  ``np.quantile(distribution, prediction.di_percentile)``, which is ``di.fit``'s own line;
* the anomaly threshold, ``np.quantile(training scores, anomaly.threshold_percentile)``, the
  trainer's own orientation and quantile;
* the **capped** skeptic spec 136 staged for the fold (R2). The source's uncapped
  ``skeptic.txt`` is never copied, so no Phase 7 run can load it by mistake, and a fold with no
  staged capped skeptic is refused rather than assembled without one.

**The distribution is the study's and the manifest says so.** It was computed by a faster
exact search than ``modelling.di``'s loop, and it is held to the module here on 16 rows per fold
at 1e-9 before anything is written. It is not a ``di.fit`` output and is not described as one.

**Two config digests, and the manifest says which is which.** The source run was trained under
the config whose digest begins ``067b2b9d``. Today's config differs from it by the three
thresholds ruled after training, which is why the study's own digest guard refuses it. The
manifest keeps the training digest as ``config_digest`` and records today's, the one the
thresholds were read from, under ``extras["provenance"]``.

**Every check runs before the directory is created**, so a refused fold leaves nothing behind
and can be assembled later under the same id. The source directories are only ever read.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import polars as pl

from acsoe.modelling import di as di_module
from acsoe.modelling.artefacts import (
    LoadedRun,
    Manifest,
    identity_digest,
    load_run,
    sha256_file,
    write_run,
)
from acsoe.modelling.calibration import CALIBRATORS_NAME
from acsoe.modelling.features import FEATURE_VERSION
from acsoe.modelling.ranking import RankingError, load_ranking_artefacts
from acsoe.research import skeptic_cap, training
from acsoe.research.walkforward import read_settings

__all__ = [
    "SOURCE_RUN_ID",
    "SUFFIX",
    "AssemblyError",
    "AssemblyInputs",
    "assemble_fold",
    "assembled_run_id",
    "rebuild_reference",
    "verify_assembled",
]

SOURCE_RUN_ID: Final = "train-20260913T205245-067b2b9d"
#: Agreed with A-replay, whose engine 23 driver points every ``models.*_run_id`` at the fold's
#: assembled run: ``<source fold run id>-p7``.
SUFFIX: Final = "-p7"
#: Rows per fold on which the study's distribution is recomputed through ``modelling.di``.
VERIFY_ROWS: Final = 16
MODULE_TOLERANCE: Final = 1e-9

#: Copied byte for byte. ``scaler.json`` is not in this list: ``write_run`` writes it from the
#: verified scaler, and :func:`assemble_fold` checks the bytes it wrote equal the source's.
_COPIED: Final[tuple[str, ...]] = ("model.txt", CALIBRATORS_NAME, training.ANOMALY_MODEL_NAME)


class AssemblyError(ValueError):
    """A fold that is not assembled. Every message names the fold and the cause."""


def assembled_run_id(fold_index: int, source_run_id: str = SOURCE_RUN_ID) -> str:
    return f"{source_run_id}-f{fold_index}{SUFFIX}"


@dataclass(frozen=True)
class AssemblyInputs:
    """Where everything is read from. Nothing is written except the new run directory."""

    models_dir: Path
    study_dir: Path
    staging_dir: Path
    oos_path: Path
    source_run_id: str = SOURCE_RUN_ID

    @property
    def sorted_dataset(self) -> Path:
        return self.study_dir / "dataset_sorted_by_decision_ts.parquet"

    def source_dir(self, fold_index: int) -> Path:
        return self.models_dir / f"{self.source_run_id}-f{fold_index}"


# --------------------------------------------------------------------------- #
# The training rows and the reference, recomputed and proven
# --------------------------------------------------------------------------- #


def _source(inputs: AssemblyInputs, fold_index: int) -> LoadedRun:
    directory = inputs.source_dir(fold_index)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise AssemblyError(f"fold {fold_index}: no source manifest at {manifest_path}")
    names = tuple(json.loads(manifest_path.read_bytes())["feature_names"])
    loaded = load_run(directory, expected_features=names, expected_version=FEATURE_VERSION)
    if int(loaded.manifest.fold.fold_index) != fold_index:
        raise AssemblyError(
            f"fold {fold_index}: the source artefact records fold {loaded.manifest.fold.fold_index}"
        )
    return loaded


def _fold_frames(
    inputs: AssemblyInputs, source: LoadedRun, config: Any
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """``(train, test)`` recomputed with the splitter's rule, proven equal to the fold's.

    The rule is ``research/walkforward``'s: training rows are before the test window, with a
    label window ending before it and a bar before its embargo. The counts and the training
    identity must equal what the fold recorded, and the scaler must have been fitted on exactly
    those rows.
    """
    fold = source.manifest.fold
    index = int(fold.fold_index)
    interval_s = int(config.get("timeframes.decision_bar_s"))
    embargo_s = read_settings(config).embargo_s(interval_s)
    frame = (
        pl.scan_parquet(inputs.sorted_dataset)
        .filter(
            (pl.col("decision_ts") >= int(fold.train_start_ts))
            & (pl.col("decision_ts") < int(fold.test_end_ts))
        )
        .collect()
        .sort(["decision_ts", "pair"])
    )
    test_start = int(fold.test_start_ts)
    before = frame.filter(pl.col("decision_ts") < test_start)
    purged = pl.col("label_window_end_ts") >= test_start
    embargoed = pl.col("decision_ts") >= test_start - embargo_s
    train = before.filter(~purged & ~embargoed)
    test = frame.filter(pl.col("decision_ts") >= test_start)
    counts = {
        "train_rows": (train.height, int(fold.train_rows)),
        "purged_count": (before.filter(purged).height, int(fold.purged_count)),
        "embargoed_count": (before.filter(~purged & embargoed).height, int(fold.embargoed_count)),
        "test_rows": (test.height, int(fold.test_rows)),
    }
    for key, (got, recorded) in counts.items():
        if got != recorded:
            raise AssemblyError(f"fold {index}: {key} recomputed {got}, manifest {recorded}")
    identity = _digest_of(train)
    if identity != source.manifest.training_identity:
        raise AssemblyError(f"fold {index}: the recomputed training rows are not the fold's")
    if identity != source.manifest.extras.get("scaler_identity"):
        raise AssemblyError(f"fold {index}: the scaler was not fitted on the training rows")
    return train, test


def _digest_of(frame: pl.DataFrame) -> str:
    return identity_digest(
        [str(value) for value in frame["pair"]], [int(value) for value in frame["decision_ts"]]
    )


def rebuild_reference(
    train: pl.DataFrame, source: LoadedRun, config: Any
) -> tuple[np.ndarray[Any, Any], list[str]]:
    """The DI reference ``_fit_and_score_di`` builds, line for line, stopping before ``di.fit``.

    Per pair, the last ``prediction.di_window_days`` of the training window; scaled by the fold's
    own scaler; complete rows only; subsampled to ``prediction.di_reference_rows`` with the fold's
    seed. A second copy of the trainer's selection, and it is held to the trainer by the identity
    check against the study, which recorded what the trainer's own selection produced; the
    study's ``selfcheck`` ran ``_fit_and_score_di`` itself and matched it.
    """
    names = tuple(source.manifest.feature_names)
    window_days = int(config.get("prediction.di_window_days"))
    cap = int(config.get("prediction.di_reference_rows"))
    seed = int(source.manifest.seeds["train"])
    eligible = training._di_reference_rows(train, window_days)
    matrix = np.asarray(
        source.scaler.transform(training._matrix(eligible, names)), dtype=np.float64
    )
    identity = [
        f"{row['pair']}|{int(row['decision_ts'])}"
        for row in eligible.select(["pair", "decision_ts"]).iter_rows(named=True)
    ]
    complete = [index for index, row in enumerate(matrix) if np.isfinite(row).all()]
    if len(complete) > cap:
        generator = np.random.default_rng(seed)
        complete = sorted(generator.choice(complete, size=cap, replace=False).tolist())
    return matrix[complete], [identity[index] for index in complete]


def _reference_digest(identity: Sequence[str]) -> str:
    return identity_digest(
        [entry.split("|")[0] for entry in identity],
        [int(entry.split("|")[1]) for entry in identity],
    )


def _verify_distribution(
    reference: np.ndarray[Any, Any],
    stamps: np.ndarray[Any, Any],
    distribution: np.ndarray[Any, Any],
    *,
    neighbours: int,
    exclusion_s: int,
    fold_index: int,
) -> float:
    """Recompute ``VERIFY_ROWS`` sampled rows through ``modelling.di``; refuse past 1e-9.

    A sampled row's value is the module's mean k-nearest distance against the reference with
    every row within ``exclusion_s`` of it removed, itself included, which is the leave-one-out
    ``modelling.di.fit`` defines. Seeded by the fold index, so a rerun samples the same rows.
    """
    generator = np.random.default_rng(fold_index)
    worst = 0.0
    size = min(VERIFY_ROWS, reference.shape[0])
    for j in generator.choice(reference.shape[0], size=size, replace=False):
        keep = np.abs(stamps - stamps[j]) > exclusion_s
        value = float(
            di_module._mean_nearest(
                reference[j][None, :], reference[keep], neighbours=neighbours, exclude_self=False
            )[0]
        )
        worst = max(worst, abs(value - float(distribution[j])))
    if worst > MODULE_TOLERANCE:
        raise AssemblyError(
            f"fold {fold_index}: the study's DI distribution differs from modelling.di by "
            f"{worst} on a sampled row"
        )
    return worst


def _check_reference_rows(
    identity: Sequence[str], train: pl.DataFrame, test: pl.DataFrame, oos_path: Path,
    fold_index: int,
) -> None:
    """``di_fitted_on_predictor_training_set``'s three questions, asked of this fold.

    Every reference row is a training row; at least one is **not** a BUY call, so the set is
    not the skeptic's BUY subset; none is a test row. The first holds by construction here and
    is asked anyway, because a rebuilt reference that drifted from the recomputed training rows
    is exactly what this module must not write.
    """
    reference = set(identity)
    train_ids = {f"{p}|{int(t)}" for p, t in zip(train["pair"], train["decision_ts"], strict=True)}
    test_ids = {f"{p}|{int(t)}" for p, t in zip(test["pair"], test["decision_ts"], strict=True)}
    outside = reference - train_ids
    if outside:
        raise AssemblyError(
            f"fold {fold_index}: {len(outside)} DI reference rows are not training rows"
        )
    if reference & test_ids:
        raise AssemblyError(f"fold {fold_index}: DI reference rows are test rows")
    buys = (
        pl.scan_parquet(oos_path)
        .filter(pl.col("is_buy"))
        .select(["pair", "decision_ts"])
        .collect()
    )
    buy_ids = {f"{p}|{int(t)}" for p, t in zip(buys["pair"], buys["decision_ts"], strict=True)}
    if not reference - buy_ids:
        raise AssemblyError(
            f"fold {fold_index}: every DI reference row is a BUY call, so the reference is the "
            "skeptic's BUY subset rather than the predictor's training rows"
        )


# --------------------------------------------------------------------------- #
# One fold
# --------------------------------------------------------------------------- #


def assemble_fold(
    fold_index: int,
    *,
    inputs: AssemblyInputs,
    config: Any,
    store: Any | None,
    now: datetime,
) -> Path:
    """Assemble fold ``fold_index`` into a new run directory and return its path.

    ``config`` is today's: the two percentiles, the DI window, cap and neighbours, the embargo.
    ``store`` supplies ``new_model_run_dir``, which refuses an existing run; injected, as in
    ``research/training.py``, because ``research/`` never imports ``clients/``. ``None`` uses
    the trainer's own ``mkdir(exist_ok=False)`` under ``inputs.models_dir``, the identical atomic
    refusal the trainer's command line relies on. ``now`` is injected
    and becomes the manifest's ``created_at``.
    """
    source = _source(inputs, fold_index)
    manifest = source.manifest
    staged = skeptic_cap.read_staged(inputs.staging_dir, fold_index)
    if staged.meta.get("source_run_id") != manifest.run_id:
        raise AssemblyError(
            f"fold {fold_index}: the staged skeptic was trained for "
            f"{staged.meta.get('source_run_id')}, not {manifest.run_id}"
        )

    di_percentile = config.get("prediction.di_percentile")
    anomaly_percentile = config.get("anomaly.threshold_percentile")
    if di_percentile is None or anomaly_percentile is None:
        raise AssemblyError(
            "prediction.di_percentile and anomaly.threshold_percentile are the operator's and "
            "both must be set; nothing here chooses a threshold"
        )
    neighbours = int(config.get("prediction.di_neighbours"))
    exclusion_s = int(config.get("backtest.embargo_bars")) * int(
        config.get("timeframes.decision_bar_s")
    )

    study_json = inputs.study_dir / f"fold_{fold_index:03d}.json"
    study_npz = inputs.study_dir / f"fold_{fold_index:03d}.npz"
    excl_npz = inputs.study_dir / f"excl_fold_{fold_index:03d}.npz"
    for path in (study_json, study_npz, excl_npz):
        if not path.is_file():
            raise AssemblyError(f"fold {fold_index}: the study file {path} does not exist")
    summary = json.loads(study_json.read_bytes().decode("utf-8"))
    if summary.get("run_id") != manifest.run_id:
        raise AssemblyError(f"fold {fold_index}: {study_json.name} is for {summary.get('run_id')}")
    if summary.get("training_identity") != manifest.training_identity:
        raise AssemblyError(f"fold {fold_index}: {study_json.name} saw other training rows")

    # ---- the DI ------------------------------------------------------------------------
    train, test = _fold_frames(inputs, source, config)
    reference, identity = rebuild_reference(train, source, config)
    digest = _reference_digest(identity)
    if digest != (summary.get("di") or {}).get("reference_identity"):
        raise AssemblyError(
            f"fold {fold_index}: the rebuilt DI reference ({len(identity)} rows) is not the "
            "study's; its identity differs from the recorded reference_identity"
        )
    _check_reference_rows(identity, train, test, inputs.oos_path, fold_index)
    stamps = np.asarray([int(entry.split("|")[1]) for entry in identity], dtype=np.int64)
    with np.load(excl_npz) as payload:
        distribution = np.asarray(payload["di_distribution"], dtype=np.float64)
        span_s = int(payload["span_s"])
    if span_s != exclusion_s:
        raise AssemblyError(
            f"fold {fold_index}: the study excluded {span_s} s and the config says {exclusion_s} s"
        )
    if distribution.shape != (reference.shape[0],):
        raise AssemblyError(
            f"fold {fold_index}: {distribution.shape[0]} distribution values against "
            f"{reference.shape[0]} reference rows"
        )
    worst = _verify_distribution(
        reference,
        stamps,
        distribution,
        neighbours=neighbours,
        exclusion_s=exclusion_s,
        fold_index=fold_index,
    )
    di_fit = di_module.DiFit(
        reference=reference,
        identity=tuple(identity),
        distribution=distribution,
        threshold=float(np.quantile(distribution, float(di_percentile))),
        neighbours=neighbours,
        percentile=float(di_percentile),
        decision_ts=stamps,
        exclusion_s=exclusion_s,
    )

    # ---- the anomaly threshold ---------------------------------------------------------
    anomaly = manifest.extras.get("anomaly")
    if not isinstance(anomaly, Mapping):
        raise AssemblyError(f"fold {fold_index}: the source fold carries no anomaly detector")
    with np.load(study_npz) as payload:
        scores = np.asarray(payload["anomaly_train_scores"], dtype=np.float64)
    if scores.shape[0] != int(anomaly["rows"]):
        raise AssemblyError(
            f"fold {fold_index}: {scores.shape[0]} anomaly training scores against the "
            f"detector's {anomaly['rows']} training rows"
        )
    anomaly_threshold = float(np.quantile(scores, float(anomaly_percentile)))

    # ---- write, once -------------------------------------------------------------------
    run_id = f"{manifest.run_id}{SUFFIX}"
    source_hashes = {
        name: sha256_file(source.directory / name) for name in (*_COPIED, "scaler.json")
    }
    study_hashes = {path.name: sha256_file(path) for path in (study_json, study_npz, excl_npz)}
    directory = training._new_run_dir(store, inputs.models_dir, run_id)
    for name in _COPIED:
        shutil.copyfile(source.directory / name, directory / name)
    di_module.save(di_fit, directory / "di.npz")
    shutil.copyfile(staged.model_path, directory / skeptic_cap.SKEPTIC_NAME)

    extras = dict(manifest.extras)
    extras["anomaly"] = {
        **dict(anomaly),
        "percentile": float(anomaly_percentile),
        "threshold": anomaly_threshold,
        "threshold_source": "np.quantile of the Phase 5 study's saved -score_samples over "
        "the detector's training rows; the forest is the source fold's, not refitted",
    }
    extras["di"] = {
        "file": "di.npz",
        "rows": int(reference.shape[0]),
        "neighbours": neighbours,
        "percentile": float(di_percentile),
        "exclusion_s": exclusion_s,
        "threshold": di_fit.threshold,
        "reference_identity": digest,
        "distribution_source": "the Phase 5 study's leave-one-out with the 48-bar exclusion "
        f"({excl_npz.name}), not a di.fit output; verified against modelling.di on "
        f"{VERIFY_ROWS} sampled rows, largest difference {worst:.3e}",
    }
    extras["skeptic"] = {
        "file": skeptic_cap.SKEPTIC_NAME,
        "rows": int(staged.meta["rows"]),
        "input_names": list(staged.meta["input_names"]),
        "training_identity": staged.meta["training_identity"],
        "label": staged.meta["label"],
        "cap_folds": int(staged.meta["cap_folds"]),
        "earliest_fold": int(staged.meta["earliest_fold"]),
        "effective_sample_size": staged.meta["effective_sample_size"],
    }
    extras["provenance"] = {
        "assembled_by": "research/artefact_assembly.py, spec 135",
        "source_run_id": manifest.run_id,
        "source_sha256": source_hashes,
        "study_sha256": study_hashes,
        "training_config_digest": manifest.config_digest,
        "threshold_config_digest": training._config_digest(config),
        "skeptic_staging": {
            "sha256": staged.meta["skeptic_sha256"],
            "config_digest": staged.meta["config_digest"],
        },
        "uncapped_skeptic": "not copied; R2 ruled the capped skeptic",
    }
    metrics = dict(manifest.metrics)
    metrics.update(
        run_id=run_id,
        di_rows=int(reference.shape[0]),
        di_threshold=di_fit.threshold,
        anomaly_percentile=float(anomaly_percentile),
        anomaly_threshold=anomaly_threshold,
        skeptic_rows=int(staged.meta["rows"]),
        skeptic_effective_sample_size=staged.meta["effective_sample_size"],
        skeptic_training_identity=staged.meta["training_identity"],
        skeptic_veto_rate=staged.meta.get("veto_rate"),
        skeptic_surviving_target_rate=staged.meta.get("surviving_target_rate"),
    )
    assembled = manifest.model_copy(
        update={
            "run_id": run_id,
            "created_at": now,
            "metrics": metrics,
            "extras": extras,
            "files": {},
        }
    )
    write_run(directory, manifest=Manifest.model_validate(assembled.model_dump()),
              scaler=source.scaler)
    if sha256_file(directory / "scaler.json") != source_hashes["scaler.json"]:
        raise AssemblyError(
            f"fold {fold_index}: the scaler written into {directory} differs from the source's; "
            "the directory is incomplete and must be removed by hand before a retry"
        )
    return directory


def verify_assembled(
    directory: Path, *, study_dir: Path, fold_index: int, config: Any
) -> dict[str, Any]:
    """Re-read one assembled directory as the ranking and engines 8 and 13 would, and recompute.

    Loads it through :func:`~acsoe.modelling.ranking.load_ranking_artefacts`, which makes
    engines 8 and 13's checks, and requires the two thresholds it carries to equal the ones
    recomputed from the study files and today's percentiles. Returns what it compared.
    """
    try:
        artefacts = load_ranking_artefacts(directory, directory)
    except RankingError as problem:
        raise AssemblyError(f"fold {fold_index}: {directory.name} does not load: {problem}") from problem
    with np.load(study_dir / f"excl_fold_{fold_index:03d}.npz") as payload:
        di_threshold = float(
            np.quantile(payload["di_distribution"], float(config.get("prediction.di_percentile")))
        )
    with np.load(study_dir / f"fold_{fold_index:03d}.npz") as payload:
        anomaly_threshold = float(
            np.quantile(
                payload["anomaly_train_scores"], float(config.get("anomaly.threshold_percentile"))
            )
        )
    result = {
        "run_id": directory.name,
        "di_threshold": artefacts.di.threshold,
        "di_threshold_recomputed": di_threshold,
        "anomaly_threshold": artefacts.anomaly_threshold,
        "anomaly_threshold_recomputed": anomaly_threshold,
    }
    if di_threshold != artefacts.di.threshold or anomaly_threshold != artefacts.anomaly_threshold:
        raise AssemblyError(f"fold {fold_index}: a threshold differs from the study's: {result}")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m acsoe.research.artefact_assembly <folds>``: assemble, then verify, each fold."""
    import argparse

    from acsoe.platform.config import load_config

    parser = argparse.ArgumentParser(prog="acsoe.research.artefact_assembly")
    parser.add_argument("folds", help="comma-separated fold indices, or LO-HI inclusive")
    parser.add_argument("--config", type=Path, default=Path("config/default.yaml"))
    parser.add_argument("--models", type=Path, default=Path("models"))
    parser.add_argument("--derived", type=Path, default=Path("data/derived"))
    args = parser.parse_args(argv)

    config = load_config(args.config)
    inputs = AssemblyInputs(
        models_dir=args.models,
        study_dir=args.derived / f"di_anomaly_{SOURCE_RUN_ID}",
        staging_dir=args.derived / f"skeptic_cap_{SOURCE_RUN_ID}",
        oos_path=args.derived / f"oos_{SOURCE_RUN_ID}.parquet",
    )
    for fold_index in skeptic_cap._parse_folds(args.folds):
        directory = assemble_fold(
            fold_index, inputs=inputs, config=config, store=None, now=datetime.now(UTC)
        )
        result = verify_assembled(
            directory, study_dir=inputs.study_dir, fold_index=fold_index, config=config
        )
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
