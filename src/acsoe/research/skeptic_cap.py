"""The capped skeptic, trained for folds that already exist, into a staging directory. Spec 136.

The operator ruled on 2026-09-16 that fold *k*'s skeptic learns only from the eligible BUY calls
of folds *k*-13 to *k*-1 (``training.skeptic_cap_folds``), and on 2026-09-19 (R2) that the
Phase 7 simulation runs it. The walk-forward that trained the predictors,
``train-20260913T205245-067b2b9d``, trained every skeptic uncapped, and **nothing retrains a
predictor this phase**. So this module trains only the skeptic, for folds whose predictor,
scaler and out-of-sample calls already exist, through **the trainer's own** ``_fit_skeptic`` —
the same row selection, the same purge and embargo, the same model settings — with the cap read
from the config exactly as the walk-forward reads it.

**It writes nowhere near ``models/``.** Each fold's skeptic goes to its own directory under a
staging root in ``data/derived/``, which spec 135's assembly reads. A run directory is written
once and complete, with a manifest whose hashes cover every file, so a skeptic added to one
afterwards would be either refused by the store or unhashed.

**Why the replication comes first.** The cap is a filter in front of an unchanged selection, so
the only way this module could train something other than what the ruling describes is by not
being the trainer. With the cap disabled it must reproduce the saved, uncapped ``skeptic.txt`` of
an early fold exactly — same training identity, same row count, same probability on every one of
that fold's BUY calls — and :func:`replicate` refuses otherwise. Measured on 2026-09-19 by the
reconnaissance's ``q_capped.py`` on folds 20 and 40; this is that check with the code in ``src/``.

The dataset read is the Phase 5 study's copy sorted by ``decision_ts``
(``data/derived/di_anomaly_<run>/dataset_sorted_by_decision_ts.parquet``), because the committed
build writes one row group per pair and a fold's window would otherwise read the whole 14.7 GB.
The study checked it against the original by row count and null count per column; the
replication above checks what matters here, that the rows it yields train the same skeptic.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import polars as pl

from acsoe.modelling.artefacts import LoadedRun, identity_digest, load_run, sha256_file
from acsoe.modelling.features import FEATURE_VERSION
from acsoe.research import training

__all__ = [
    "CAP_KEY",
    "SKEPTIC_META_NAME",
    "SKEPTIC_NAME",
    "CappedSkepticError",
    "StagedSkeptic",
    "read_cap",
    "read_staged",
    "recompute_identity",
    "replicate",
    "stage_fold",
    "train_fold_skeptic",
]

CAP_KEY: Final = "training.skeptic_cap_folds"
SKEPTIC_NAME: Final = "skeptic.txt"
#: Written **last**, so its presence is what says a staged fold is complete.
SKEPTIC_META_NAME: Final = "skeptic.json"

#: The columns of the out-of-sample file the skeptic's selection reads.
OOS_READ: Final[tuple[str, ...]] = (
    "pair",
    "decision_ts",
    "label_window_end_ts",
    "fold_index",
    "is_buy",
    "p_target",
    "p_stop",
    "p_timeout",
    "expected_move_pct",
    "label",
    "weight",
)


class CappedSkepticError(ValueError):
    """A fold this module will not train or stage. Every message names the cause."""


@dataclass(frozen=True)
class StagedSkeptic:
    """One staged fold, as :func:`read_staged` reads it back."""

    directory: Path
    fold_index: int
    meta: dict[str, Any]

    @property
    def model_path(self) -> Path:
        return self.directory / SKEPTIC_NAME


def fold_run_dir(models_dir: Path, source_run_id: str, fold_index: int) -> Path:
    return models_dir / f"{source_run_id}-f{fold_index}"


def load_source_fold(models_dir: Path, source_run_id: str, fold_index: int) -> LoadedRun:
    """The fold's verified predictor artefact: every hash, its own feature order, and f1."""
    directory = fold_run_dir(models_dir, source_run_id, fold_index)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise CappedSkepticError(f"fold {fold_index}: no manifest at {manifest_path}")
    names = tuple(json.loads(manifest_path.read_bytes())["feature_names"])
    return load_run(directory, expected_features=names, expected_version=FEATURE_VERSION)


def read_cap(config: Any) -> int | None:
    """``training.skeptic_cap_folds``: a positive number of folds, or ``None`` for uncapped.

    Read through ``Config.get``, which raises on a key the config model does not declare, so a
    process without the key's model field stops here rather than training uncapped by default.
    """
    value = config.get(CAP_KEY)
    if value is None:
        return None
    cap = int(value)
    if cap <= 0:
        raise CappedSkepticError(f"{CAP_KEY} is {value!r}; a cap is a positive number of folds")
    return cap


def train_fold_skeptic(
    fold_index: int,
    *,
    config: Any,
    cap_folds: int | None,
    source: LoadedRun,
    oos: pl.DataFrame,
    dataset_path: Path,
) -> tuple[Any, dict[str, Any]]:
    """Fold ``fold_index``'s skeptic, through ``training._fit_skeptic`` with ``cap_folds``.

    ``oos`` is the source run's out-of-sample file (at least :data:`OOS_READ`). The trainer
    handed ``_fit_skeptic`` every out-of-sample row of the folds before this one, and so does
    this: the cap is applied inside the trainer, not here, so the two paths cannot differ in
    where it bites.

    **The dataset read starts at the capped window's first bar**, which bounds a late fold's
    memory to about fourteen weeks of rows instead of seven years. A consequence worth knowing:
    behind that read, an earlier fold's calls find no feature row and fall out of the trainer's
    join whatever the cap says, so this function's output does not show whether the trainer's
    own filter works. `test_the_trainer_applies_the_cap_itself_over_the_whole_dataset` asks the
    trainer directly, with the whole dataset, for that reason.
    """
    manifest = source.manifest
    fold = manifest.fold
    if int(fold.fold_index) != fold_index:
        raise CappedSkepticError(
            f"the artefact for fold {fold_index} records fold {fold.fold_index}"
        )
    names = tuple(manifest.feature_names)
    previous = oos.filter(pl.col("fold_index") < fold_index)
    own = oos.filter(pl.col("fold_index") == fold_index)
    if own.height != int(fold.test_rows):
        raise CappedSkepticError(
            f"fold {fold_index}: {own.height} out-of-sample rows against the manifest's "
            f"{fold.test_rows} test rows, so this is not that fold's out-of-sample file"
        )
    earliest = 0 if cap_folds is None else max(0, fold_index - cap_folds)
    reachable = previous.filter(pl.col("fold_index") >= earliest)
    lo = int(reachable["decision_ts"].min()) if reachable.height else int(fold.test_start_ts)
    data = (
        pl.scan_parquet(dataset_path)
        .filter((pl.col("decision_ts") >= lo) & (pl.col("decision_ts") < int(fold.test_end_ts)))
        .select(["pair", "decision_ts", *names])
        .collect()
    )
    return training._fit_skeptic(
        previous if previous.height else None,
        data,
        fold,  # type: ignore[arg-type]
        config=config,
        names=names,
        seed=int(manifest.seeds["train"]),
        scaler=source.scaler,
        oos=own,
        buys=[bool(value) for value in own["is_buy"]],
        cap_folds=cap_folds,
    )


def _buy_probabilities(
    model_or_booster: Any, source: LoadedRun, oos: pl.DataFrame, dataset_path: Path
) -> np.ndarray[Any, Any]:
    """P(wrong) on every BUY call of the source fold, in ``(decision_ts, pair)`` order."""
    fold = source.manifest.fold
    names = tuple(source.manifest.feature_names)
    buys = oos.filter(
        (pl.col("fold_index") == int(fold.fold_index)) & pl.col("is_buy")
    ).sort(["decision_ts", "pair"])
    features = (
        pl.scan_parquet(dataset_path)
        .filter(
            (pl.col("decision_ts") >= int(fold.test_start_ts))
            & (pl.col("decision_ts") < int(fold.test_end_ts))
        )
        .select(["pair", "decision_ts", *names])
        .collect()
    )
    joined = buys.join(features, on=["pair", "decision_ts"], how="inner")
    if joined.height != buys.height:
        raise CappedSkepticError(
            f"fold {fold.fold_index}: {buys.height - joined.height} BUY calls have no feature "
            "row in the dataset"
        )
    matrix = training._skeptic_matrix(joined, source.scaler, names)
    predict = getattr(model_or_booster, "predict_proba", None)
    if predict is not None:
        return np.asarray(predict(matrix)[:, 1], dtype=np.float64)
    return np.asarray(model_or_booster.predict(matrix), dtype=np.float64)


def replicate(
    fold_index: int,
    *,
    config: Any,
    source: LoadedRun,
    oos: pl.DataFrame,
    dataset_path: Path,
) -> dict[str, Any]:
    """Retrain ``fold_index``'s skeptic **with the cap disabled** and compare with the saved one.

    The cap is passed as ``None`` whatever the config says, because the saved skeptics were
    trained uncapped and this compares like with like. Returns the comparison and refuses unless
    the training identity, the row count and every probability are equal.
    """
    import lightgbm as lgb

    recorded = source.manifest.extras.get("skeptic")
    if not isinstance(recorded, Mapping):
        raise CappedSkepticError(f"fold {fold_index}'s source artefact carries no skeptic")
    model, report = train_fold_skeptic(
        fold_index,
        config=config,
        cap_folds=None,
        source=source,
        oos=oos,
        dataset_path=dataset_path,
    )
    if model is None:
        raise CappedSkepticError(f"fold {fold_index}: the retrain produced no skeptic")
    saved = lgb.Booster(model_file=str(source.directory / SKEPTIC_NAME))
    mine = _buy_probabilities(model, source, oos, dataset_path)
    theirs = _buy_probabilities(saved, source, oos, dataset_path)
    result = {
        "fold_index": fold_index,
        "rows": int(report["skeptic_rows"]),
        "recorded_rows": int(recorded["rows"]),
        "identity": report["skeptic_training_identity"],
        "recorded_identity": recorded["training_identity"],
        "buy_calls": int(mine.size),
        "largest_probability_difference": float(np.max(np.abs(mine - theirs)))
        if mine.size
        else 0.0,
    }
    if (
        result["rows"] != result["recorded_rows"]
        or result["identity"] != result["recorded_identity"]
        or result["largest_probability_difference"] != 0.0
    ):
        raise CappedSkepticError(f"fold {fold_index} does not replicate: {result}")
    return result


def stage_fold(
    fold_index: int,
    *,
    config: Any,
    config_digest: str,
    source: LoadedRun,
    oos: pl.DataFrame,
    dataset_path: Path,
    staging_root: Path,
) -> StagedSkeptic:
    """Train fold ``fold_index``'s capped skeptic and write it to ``staging_root/fold_NNN/``.

    Refuses an existing fold directory: a staged skeptic is written once, like the run directory
    it is assembled into. Refuses an uncapped config: staging the uncapped skeptic under this
    name is the one mistake spec 135 must never be able to assemble.
    """
    cap = read_cap(config)
    if cap is None:
        raise CappedSkepticError(
            f"{CAP_KEY} is not set, so this would stage an uncapped skeptic; R2 ruled the "
            "capped one"
        )
    model, report = train_fold_skeptic(
        fold_index,
        config=config,
        cap_folds=cap,
        source=source,
        oos=oos,
        dataset_path=dataset_path,
    )
    if model is None:
        raise CappedSkepticError(
            f"fold {fold_index}: the capped selection left {report['skeptic_rows']} rows, too "
            "few to train a skeptic; nothing is staged, and spec 135 refuses the fold"
        )
    directory = staging_root / f"fold_{fold_index:03d}"
    staging_root.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    model_path = directory / SKEPTIC_NAME
    model_path.write_bytes(model.booster_.model_to_string().encode("utf-8"))
    meta = {
        "fold_index": fold_index,
        "source_run_id": source.manifest.run_id,
        "cap_folds": cap,
        "earliest_fold": max(0, fold_index - cap),
        "rows": int(report["skeptic_rows"]),
        "effective_sample_size": float(report["skeptic_effective_sample_size"]),
        "training_identity": report["skeptic_training_identity"],
        "input_names": list(report["skeptic_input_names"] or []),
        "veto_rate": report.get("skeptic_veto_rate"),
        "surviving_target_rate": report.get("skeptic_surviving_target_rate"),
        "all_buy_target_rate": report.get("skeptic_all_buy_target_rate"),
        "seed": int(source.manifest.seeds["train"]),
        "config_digest": config_digest,
        "skeptic_sha256": sha256_file(model_path),
        "label": "wrong = label != 'target'",
    }
    tmp = directory / (SKEPTIC_META_NAME + ".tmp")
    tmp.write_bytes(json.dumps(meta, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    tmp.replace(directory / SKEPTIC_META_NAME)
    return StagedSkeptic(directory=directory, fold_index=fold_index, meta=meta)


def read_staged(staging_root: Path, fold_index: int) -> StagedSkeptic:
    """A staged fold, verified: complete, for this fold, capped, and its file unchanged."""
    directory = staging_root / f"fold_{fold_index:03d}"
    meta_path = directory / SKEPTIC_META_NAME
    if not meta_path.is_file():
        raise CappedSkepticError(
            f"fold {fold_index} has no staged capped skeptic at {directory}; it is refused "
            "rather than assembled with the uncapped one"
        )
    meta = json.loads(meta_path.read_bytes().decode("utf-8"))
    if int(meta.get("fold_index", -1)) != fold_index:
        raise CappedSkepticError(f"{meta_path} is for fold {meta.get('fold_index')}")
    if not meta.get("cap_folds"):
        raise CappedSkepticError(f"{meta_path} records no cap")
    model_path = directory / SKEPTIC_NAME
    if not model_path.is_file() or sha256_file(model_path) != meta.get("skeptic_sha256"):
        raise CappedSkepticError(f"{model_path} is missing or differs from its recorded hash")
    return StagedSkeptic(directory=directory, fold_index=fold_index, meta=meta)


def recompute_identity(
    fold_index: int,
    *,
    cap_folds: int,
    source: LoadedRun,
    oos: pl.DataFrame,
    dataset_path: Path,
    embargo_bars: int,
    interval_s: int,
) -> str:
    """The capped training identity, recomputed from the out-of-sample file independently.

    Written from the ruling rather than through ``_skeptic_training_rows``: BUY calls of folds
    ``k - cap`` to ``k - 1`` whose label window ends before fold *k*'s test window and whose bar
    is before its embargo, present in the dataset. Spec 136's Check When Done compares it with
    the staged skeptic's recorded identity.
    """
    fold = source.manifest.fold
    test_start = int(fold.test_start_ts)
    chosen = oos.filter(
        pl.col("is_buy")
        & (pl.col("fold_index") >= max(0, fold_index - cap_folds))
        & (pl.col("fold_index") < fold_index)
        & (pl.col("label_window_end_ts") < test_start)
        & (pl.col("decision_ts") < test_start - embargo_bars * interval_s)
    ).select(["pair", "decision_ts"])
    if chosen.height:
        lo = int(chosen["decision_ts"].min())
        present = (
            pl.scan_parquet(dataset_path)
            .filter((pl.col("decision_ts") >= lo) & (pl.col("decision_ts") < test_start))
            .select(["pair", "decision_ts"])
            .collect()
        )
        chosen = chosen.join(present, on=["pair", "decision_ts"], how="inner")
    return identity_digest(
        [str(value) for value in chosen["pair"]], [int(value) for value in chosen["decision_ts"]]
    )


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m acsoe.research.skeptic_cap <replicate|stage> <folds> [--config ...]``."""
    import argparse

    from acsoe.platform.config import load_config

    parser = argparse.ArgumentParser(prog="acsoe.research.skeptic_cap")
    parser.add_argument("command", choices=("replicate", "stage"))
    parser.add_argument("folds", help="comma-separated fold indices, or LO-HI inclusive")
    parser.add_argument("--config", type=Path, default=Path("config/default.yaml"))
    parser.add_argument("--models", type=Path, default=Path("models"))
    parser.add_argument("--run", default="train-20260913T205245-067b2b9d")
    parser.add_argument("--derived", type=Path, default=Path("data/derived"))
    parser.add_argument(
        "--cap",
        type=int,
        default=None,
        help="the ruled cap, for a config whose model does not yet declare "
        f"{CAP_KEY}; refused if the config declares a different value",
    )
    args = parser.parse_args(argv)

    folds = _parse_folds(args.folds)
    config: Any = load_config(args.config)
    if args.cap is not None:
        config = _with_cap(config, int(args.cap))
    oos = pl.read_parquet(args.derived / f"oos_{args.run}.parquet", columns=list(OOS_READ))
    dataset = args.derived / f"di_anomaly_{args.run}" / "dataset_sorted_by_decision_ts.parquet"
    staging = args.derived / f"skeptic_cap_{args.run}"
    digest = training._config_digest(config)
    for fold_index in folds:
        source = load_source_fold(args.models, args.run, fold_index)
        if args.command == "replicate":
            result = replicate(
                fold_index,
                config=config,
                source=source,
                oos=oos,
                dataset_path=dataset,
            )
            _emit(result)
        else:
            staged = stage_fold(
                fold_index,
                config=config,
                config_digest=digest,
                source=source,
                oos=oos,
                dataset_path=dataset,
                staging_root=staging,
            )
            _emit(staged.meta)
    return 0


class _CapSupplied:
    """A config answering ``training.skeptic_cap_folds`` with the ruled value from the command
    line, and everything else as loaded."""

    def __init__(self, inner: Any, cap: int) -> None:
        self._inner = inner
        self._cap = cap

    def get(self, key: str) -> Any:
        if key == CAP_KEY:
            return self._cap
        return self._inner.get(key)


def _with_cap(config: Any, cap: int) -> Any:
    """``config`` with ``--cap`` supplied, refusing a config that already says otherwise.

    The ruling is 13 folds and its home is ``training.skeptic_cap_folds``. The flag exists for
    the window in which the key's model field has not landed, so the config cannot say anything
    and the one refusal left is the one that matters: **a config that declares the key and
    disagrees with the flag is refused**, never overridden, because then two sources would name
    two caps and the staged record would describe only one of them.
    """
    from acsoe.platform.config import ConfigKeyError

    if cap <= 0:
        raise CappedSkepticError(f"--cap is {cap}; a cap is a positive number of folds")
    try:
        declared = config.get(CAP_KEY)
    except ConfigKeyError:
        # The config model does not declare the key yet: the flag is the only source.
        return _CapSupplied(config, cap)
    if declared is not None and int(declared) != cap:
        raise CappedSkepticError(f"--cap {cap} disagrees with the config's {CAP_KEY} {declared}")
    return _CapSupplied(config, cap)


def _emit(payload: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    sys.stdout.flush()


def _parse_folds(text: str) -> list[int]:
    if "-" in text and "," not in text:
        lo, hi = (int(part) for part in text.split("-", 1))
        return list(range(lo, hi + 1))
    return [int(part) for part in text.split(",")]


if __name__ == "__main__":
    raise SystemExit(main())
