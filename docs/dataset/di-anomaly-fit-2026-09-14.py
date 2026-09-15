"""Fit each fold's Dissimilarity Index and anomaly score distribution from its own training rows.

Operator ruling 2026-09-14, for `prediction.di_percentile` and `anomaly.threshold_percentile`.
The full run `train-20260913T205245-067b2b9d` trained with both keys absent, so none of its 405
folds carries a `di.npz` or an anomaly threshold, and its digest holds no distribution to choose
either percentile from. **Nothing is retrained.** This script recovers each fold's training rows
from the dataset, proves by identity that they are the rows the fold was trained on, and then:

* **DI**: builds the reference set exactly as the trainer's `_fit_and_score_di` does (its
  `_di_reference_rows` for the per-pair last `prediction.di_window_days`, the fold's verified
  scaler, complete rows only, capped at `prediction.di_reference_rows` with the fold's seed), and
  computes the statistic `modelling.di` defines: the leave-one-out mean distance to the
  `prediction.di_neighbours` nearest reference rows, and the same mean for every complete test
  row. **The search is scikit-learn's multithreaded brute force, not `di._mean_nearest`**, and
  that is a measured necessity rather than a preference: the module's numpy loop costs about 15
  minutes of leave-one-out per 200,000-row fold on one core, and `_fit_and_score_di` scores test
  rows one `di.score` call at a time at about 136 ms each (93,166 rows in fold 404 alone is 3.5
  hours), so the trainer's own path over 405 folds is days to weeks. Held to the module twice:
  every fold recomputes 16 sampled leave-one-out values and 16 sampled test scores through
  `di._mean_nearest` and `di.score` and refuses beyond 1e-9; and `selfcheck` runs the trainer's
  `_fit_and_score_di` in full (placeholder percentile 0.5, discarded; empty test frame) on small
  folds and requires identical reference identity and matrix and every distribution value within
  1e-9. No threshold is fitted here: every threshold reported is `np.quantile` of the saved
  distribution, as `di.fit` computes it.
* **Anomaly**: loads the fold's saved isolation forest (`anomaly.joblib`, hash-verified by
  `load_run`; never refitted), rebuilds its inputs with the trainer's `_anomaly_input_names` and
  `_anomaly_matrix`, checks the complete-row identity against the manifest's
  `anomaly.training_identity`, and saves `-score_samples` over the training rows (the
  distribution `_fit_anomaly` takes its quantile of) and over the test rows.

Run on the commit that trained the artefacts (`PYTHONPATH` on the `6e09881` worktree; `research/`,
`modelling/` and `config/` are unchanged between it and `690b4d3`).

    python di-anomaly-fit-2026-09-14.py <repo> <config> prepare
    python di-anomaly-fit-2026-09-14.py <repo> <config> fit <workers> [fold,fold,...]
    python di-anomaly-fit-2026-09-14.py <repo> <config> controls
    python di-anomaly-fit-2026-09-14.py <repo> <config> selfcheck <fold,fold,...>

**Checks before a fold's numbers are kept**, any failure writes nothing for that fold:
the config digest and seed equal the manifest's; the test window is the splitter's; the training
rows recomputed with the splitter's rule (`train_start <= decision_ts < test_start`, label window
ending before the test window, decision bar before the embargo) match the manifest's train row
count, purged count, embargoed count, `training_identity` and `scaler_identity`; the test rows
match `test_rows`; the anomaly inputs equal the manifest's `input_names` and the complete-row
count and identity equal `anomaly.rows` and `anomaly.training_identity`.

Writes to `data/derived/di_anomaly_<run_id>/` (gitignored runtime output): one `fold_NNN.npz`
(the two distributions), one `fold_NNN.parquet` (per test row DI and anomaly score) and one
`fold_NNN.json` (checks and timings, written last, so its presence means the fold is complete).
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

REPO = Path(sys.argv[1])
CONFIG = Path(sys.argv[2])
RUN_ID = "train-20260913T205245-067b2b9d"
DATASET = REPO / "data" / "derived" / "dataset_20260913T205245.parquet"
MODELS = REPO / "models"
OUT = REPO / "data" / "derived" / f"di_anomaly_{RUN_ID}"
SORTED = OUT / "dataset_sorted_by_decision_ts.parquet"
PLACEHOLDER_PERCENTILE = 0.5
BLAS_THREADS = int(os.environ.get("DI_THREADS", "32"))
ANOMALY_THREADS = BLAS_THREADS
VERIFY_ROWS = 16
MODULE_TOLERANCE = 1e-9


class Refused(Exception):
    pass


class _PlaceholderPercentile:
    """The run's config, with `prediction.di_percentile` supplied as a discarded placeholder."""

    def __init__(self, config: Any) -> None:
        self._config = config

    def get(self, key: str) -> Any:
        if key == "prediction.di_percentile":
            return PLACEHOLDER_PERCENTILE
        return self._config.get(key)


def fold_dir(index: int) -> Path:
    return MODELS / f"{RUN_ID}-f{index}"


def fold_indices() -> list[int]:
    found = sorted(int(path.name.rsplit("-f", 1)[1]) for path in MODELS.glob(f"{RUN_ID}-f*"))
    if found != list(range(len(found))):
        raise Refused(f"fold directories are not contiguous from 0: {found[:3]}...{found[-3:]}")
    return found


# --------------------------------------------------------------------------- #
# prepare: one reordering of the dataset so a fold's window is a cheap scan
# --------------------------------------------------------------------------- #


def prepare() -> None:
    """The dataset rewritten ordered by `(decision_ts, pair)` in small row groups.

    The committed build writes one row group per pair, so a filter on `decision_ts` cannot skip
    anything and every fold would read 14.7 GB. Same rows, same values, a different order; the
    row count and the per-column null counts are checked against the original.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    if SORTED.exists():
        raise Refused(f"{SORTED} exists; this script never overwrites")
    source = pl.scan_parquet(DATASET)
    tmp = SORTED.with_suffix(".tmp")
    source.sort(["decision_ts", "pair"]).sink_parquet(tmp, row_group_size=250_000)
    original = pl.scan_parquet(DATASET).select(pl.len(), pl.all().null_count().name.suffix("__n")).collect()
    rewritten = pl.scan_parquet(tmp).select(pl.len(), pl.all().null_count().name.suffix("__n")).collect()
    if original.to_dicts() != rewritten.to_dicts():
        raise Refused("the reordered dataset differs from the original in row count or null counts")
    tmp.rename(SORTED)
    sys.stdout.write(f"prepared {SORTED}: {original['len'][0]} rows\n")


# --------------------------------------------------------------------------- #
# fit: one fold
# --------------------------------------------------------------------------- #


def training_rows(frame: pl.DataFrame, fold: Any, embargo_s: int) -> tuple[pl.DataFrame, int, int]:
    """The splitter's rule (`research/walkforward._one_fold`) over one fold's window."""
    before = frame.filter(pl.col("decision_ts") < fold.test_start_ts)
    purged = pl.col("label_window_end_ts") >= fold.test_start_ts
    embargoed = pl.col("decision_ts") >= fold.test_start_ts - embargo_s
    return (
        before.filter(~purged & ~embargoed),
        before.filter(purged).height,
        before.filter(~purged & embargoed).height,
    )


def di_reference(
    training: Any, config: Any, train: pl.DataFrame, scaler: Any, names: tuple[str, ...], seed: int
) -> tuple[np.ndarray, list[str]]:
    """The reference set `_fit_and_score_di` builds, line for line, stopping before `di.fit`.

    `di.fit` is not called because its leave-one-out search is the numpy loop that costs ~15
    minutes per capped fold on one core; the statistic is computed by `di_search` instead and held
    to the module's arithmetic by `verify_against_module` on every fold, and to the trainer's own
    `_fit_and_score_di` in full by `selfcheck`.
    """
    window_days = int(config.get("prediction.di_window_days"))
    cap = int(config.get("prediction.di_reference_rows"))
    eligible = training._di_reference_rows(train, window_days)
    matrix = np.asarray(scaler.transform(training._matrix(eligible, names)), dtype=np.float64)
    identity = [
        f"{row['pair']}|{int(row['decision_ts'])}"
        for row in eligible.select(["pair", "decision_ts"]).iter_rows(named=True)
    ]
    complete = [index for index, row in enumerate(matrix) if np.isfinite(row).all()]
    if len(complete) > cap:
        generator = np.random.default_rng(seed)
        complete = sorted(generator.choice(complete, size=cap, replace=False).tolist())
    return matrix[complete], [identity[index] for index in complete]


def di_search(reference: np.ndarray, queries: np.ndarray, neighbours: int) -> tuple[np.ndarray, np.ndarray]:
    """Leave-one-out mean k-nearest distance over the reference, and mean k-nearest per query.

    Brute-force Euclidean search (scikit-learn, multithreaded). Leave-one-out drops the query's
    own index, exactly as `di._mean_nearest(exclude_self=True)` sets its own column to infinity;
    an exact duplicate at distance zero is kept, as the module keeps it.
    """
    from sklearn.neighbors import NearestNeighbors

    index = NearestNeighbors(n_neighbors=neighbours + 1, algorithm="brute").fit(reference)
    distances, positions = index.kneighbors(reference, n_neighbors=neighbours + 1)
    own = positions == np.arange(reference.shape[0])[:, None]
    has_own = own.any(axis=1)
    # Rows whose own index was returned: drop it and keep the first k others. A row whose own
    # index was not returned has more than k exact duplicates at distance zero, and its first k
    # are what the module would take too.
    kept = np.where(own, np.inf, distances)
    kept.sort(axis=1)
    distribution = np.where(has_own, kept[:, :neighbours].mean(axis=1), distances[:, :neighbours].mean(axis=1))
    if queries.shape[0]:
        test_distances, _ = index.kneighbors(queries, n_neighbors=neighbours)
        scores = test_distances.mean(axis=1)
    else:
        scores = np.empty(0, dtype=np.float64)
    return distribution, scores


def verify_against_module(
    reference: np.ndarray,
    distribution: np.ndarray,
    queries: np.ndarray,
    scores: np.ndarray,
    neighbours: int,
    fold: int,
) -> float:
    """Sampled rows recomputed through `modelling.di` itself; refuses beyond `MODULE_TOLERANCE`."""
    from acsoe.modelling import di

    generator = np.random.default_rng(fold)
    worst = 0.0
    for j in generator.choice(reference.shape[0], size=min(VERIFY_ROWS, reference.shape[0]), replace=False):
        others = np.delete(reference, j, axis=0)
        value = float(di._mean_nearest(reference[j][None, :], others, neighbours=neighbours, exclude_self=False)[0])
        worst = max(worst, abs(value - float(distribution[j])))
    if queries.shape[0]:
        fitted = di.DiFit(
            reference=reference, identity=(), distribution=distribution, threshold=math.inf,
            neighbours=neighbours, percentile=PLACEHOLDER_PERCENTILE,
        )
        for j in generator.choice(queries.shape[0], size=min(VERIFY_ROWS, queries.shape[0]), replace=False):
            worst = max(worst, abs(di.score(fitted, queries[j]).di - float(scores[j])))
    if worst > MODULE_TOLERANCE:
        raise Refused(f"fold {fold}: DI differs from modelling.di by {worst}")
    return worst


def load_fold(index: int) -> dict[str, Any]:
    """One fold's verified artefacts and its identity-checked training and test rows."""
    from acsoe.modelling.artefacts import identity_digest, load_run
    from acsoe.modelling.features import FEATURE_VERSION
    from acsoe.platform.config import load_config
    from acsoe.research import training
    from acsoe.research.walkforward import read_settings

    directory = fold_dir(index)
    names = tuple(json.loads((directory / "manifest.json").read_bytes())["feature_names"])
    run = load_run(directory, expected_features=names, expected_version=FEATURE_VERSION)
    manifest = run.manifest
    fold = manifest.fold
    config = load_config(CONFIG)
    if manifest.config_digest != training._config_digest(config):
        raise Refused(f"fold {index}: trained under config {manifest.config_digest}")
    seed = int(manifest.seeds["train"])
    if seed != int(config.get("seeds.train")):
        raise Refused(f"fold {index}: seed {seed} is not the config's")
    interval_s = int(config.get("timeframes.decision_bar_s"))
    settings = read_settings(config)
    if fold.train_start_ts != fold.test_start_ts - settings.training_window_s:
        raise Refused(f"fold {index}: training window is not the splitter's")

    frame = (
        pl.scan_parquet(SORTED)
        .filter((pl.col("decision_ts") >= fold.train_start_ts) & (pl.col("decision_ts") < fold.test_end_ts))
        .collect()
        .sort(["decision_ts", "pair"])
    )
    train, purged, embargoed = training_rows(frame, fold, settings.embargo_s(interval_s))
    test = frame.filter(pl.col("decision_ts") >= fold.test_start_ts)
    del frame
    counts = {
        "train_rows": (train.height, fold.train_rows),
        "purged_count": (purged, fold.purged_count),
        "embargoed_count": (embargoed, fold.embargoed_count),
        "test_rows": (test.height, fold.test_rows),
    }
    for key, (got, recorded) in counts.items():
        if got != recorded:
            raise Refused(f"fold {index}: {key} recomputed {got}, manifest {recorded}")
    identity = identity_digest([str(v) for v in train["pair"]], [int(v) for v in train["decision_ts"]])
    if identity != manifest.training_identity:
        raise Refused(f"fold {index}: training identity differs from the manifest")
    if identity != manifest.extras.get("scaler_identity"):
        raise Refused(f"fold {index}: scaler identity differs from the training identity")
    return {"training": training, "identity_digest": identity_digest, "config": config, "run": run,
            "manifest": manifest, "fold": fold, "names": names, "seed": seed, "train": train,
            "test": test, "identity": identity, "directory": directory}


def fit_fold(index: int) -> str:
    from threadpoolctl import threadpool_limits

    threadpool_limits(BLAS_THREADS)
    marker = OUT / f"fold_{index:03d}.json"
    if marker.exists():
        return f"fold {index}: already done"

    import joblib

    started = time.perf_counter()
    loaded_fold = load_fold(index)
    training, identity_digest, config, run = (loaded_fold[k] for k in ("training", "identity_digest", "config", "run"))
    manifest, fold, names, seed = (loaded_fold[k] for k in ("manifest", "fold", "names", "seed"))
    train, test, identity, directory = (loaded_fold[k] for k in ("train", "test", "identity", "directory"))
    loaded = time.perf_counter()

    # ---- DI: the trainer's reference set, the module's statistic, a faster search ----
    reference, reference_ids = di_reference(training, config, train, run.scaler, names, seed)
    neighbours = int(config.get("prediction.di_neighbours"))
    x_test = np.asarray(run.scaler.transform(training._matrix(test, names)), dtype=np.float64)
    test_complete = np.isfinite(x_test).all(axis=1)
    distribution, test_di = di_search(reference, x_test[test_complete], neighbours)
    di_values = np.full(test.height, math.nan, dtype=np.float64)
    di_values[test_complete] = test_di
    worst = verify_against_module(reference, distribution, x_test[test_complete], test_di, neighbours, index)
    del x_test
    reference_identity = identity_digest(
        [entry.split("|")[0] for entry in reference_ids],
        [int(entry.split("|")[1]) for entry in reference_ids],
    )
    di_done = time.perf_counter()

    # ---- Anomaly, the saved forest, never refitted ----
    recorded = manifest.extras.get("anomaly")
    anomaly_block: dict[str, Any] = {"present": recorded is not None}
    train_scores = np.empty(0, dtype=np.float64)
    test_scores = np.full(test.height, math.nan, dtype=np.float64)
    if recorded is not None:
        inputs = training._anomaly_input_names(names)
        if list(inputs) != list(recorded["input_names"]):
            raise Refused(f"fold {index}: anomaly inputs differ from the manifest")
        forest = joblib.load(directory / training.ANOMALY_MODEL_NAME)
        matrix = training._anomaly_matrix(train, run.scaler, names, inputs)
        complete = np.isfinite(matrix).all(axis=1)
        if int(complete.sum()) != int(recorded["rows"]):
            raise Refused(f"fold {index}: {int(complete.sum())} complete anomaly rows, manifest {recorded['rows']}")
        rows = train.filter(pl.Series(values=complete, dtype=pl.Boolean))
        if identity_digest([str(v) for v in rows["pair"]], [int(v) for v in rows["decision_ts"]]) != recorded[
            "training_identity"
        ]:
            raise Refused(f"fold {index}: anomaly training identity differs from the manifest")
        test_matrix = training._anomaly_matrix(test, run.scaler, names, inputs)
        scored = np.isfinite(test_matrix).all(axis=1)
        # A threading context parallelises scoring and changes no score (sklearn's own note).
        with joblib.parallel_backend("threading", n_jobs=ANOMALY_THREADS):
            train_scores = -forest.score_samples(matrix[complete])
            if scored.any():
                test_scores[scored] = -forest.score_samples(test_matrix[scored])
        anomaly_block.update(rows=int(complete.sum()), test_scored=int(scored.sum()))
    anomaly_done = time.perf_counter()

    stem = OUT / f"fold_{index:03d}"
    np.savez(
        stem.with_suffix(".npz.tmp.npz"),
        di_distribution=np.asarray(distribution, dtype=np.float64),
        anomaly_train_scores=np.asarray(train_scores, dtype=np.float64),
    )
    os.replace(stem.with_suffix(".npz.tmp.npz"), stem.with_suffix(".npz"))
    test.select(["pair", "decision_ts"]).with_columns(
        pl.lit(index).alias("fold_index"),
        pl.Series("di", di_values, dtype=pl.Float64),
        pl.Series("anomaly_score", test_scores, dtype=pl.Float64),
    ).write_parquet(stem.with_suffix(".parquet.tmp"))
    os.replace(stem.with_suffix(".parquet.tmp"), stem.with_suffix(".parquet"))
    summary = {
        "fold_index": index,
        "run_id": manifest.run_id,
        "test_start_ts": fold.test_start_ts,
        "train_rows": train.height,
        "test_rows": test.height,
        "training_identity": identity,
        "di": {
            "reference_rows": int(reference.shape[0]),
            "neighbours": neighbours,
            "reference_identity": reference_identity,
            "test_scored": int(test_complete.sum()),
            "largest_difference_from_module": worst,
        },
        "anomaly": anomaly_block,
        "seconds": {
            "load_and_verify": round(loaded - started, 1),
            "di": round(di_done - loaded, 1),
            "anomaly": round(anomaly_done - di_done, 1),
        },
    }
    marker.write_bytes(json.dumps(summary, indent=1, sort_keys=True).encode("utf-8"))
    return (
        f"fold {index}: train {train.height}, DI ref {reference.shape[0]} (diff {worst:.1e}), anomaly rows "
        f"{anomaly_block.get('rows')}, {summary['seconds']}"
    )


def _safe_fit(index: int) -> str:
    try:
        return fit_fold(index)
    except Refused as exc:
        return f"REFUSED: {exc}"


def fit(workers: int, only: list[int] | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not SORTED.exists():
        raise Refused("run `prepare` first")
    indices = only if only is not None else fold_indices()
    # Largest folds first, so the long ones start while every worker is free.
    todo = sorted(
        (i for i in indices if not (OUT / f"fold_{i:03d}.json").exists()),
        key=lambda i: -json.loads((fold_dir(i) / "manifest.json").read_bytes())["fold"]["train_rows"],
    )
    sys.stdout.write(f"{len(todo)} fold(s) to fit with {workers} worker(s)\n")
    sys.stdout.flush()
    if workers <= 1:
        for index in todo:
            sys.stdout.write(_safe_fit(index) + "\n")
            sys.stdout.flush()
        return
    with get_context("spawn").Pool(workers, maxtasksperchild=1) as pool:
        for line in pool.imap_unordered(_safe_fit, todo):
            sys.stdout.write(time.strftime("%H:%M:%S ") + line + "\n")
            sys.stdout.flush()


# --------------------------------------------------------------------------- #
# controls: the identity check refuses what it should
# --------------------------------------------------------------------------- #


def controls() -> None:
    """Three rows each of which must REFUSE, and the true row that must be ACCEPTED."""
    from acsoe.modelling.artefacts import identity_digest
    from acsoe.platform.config import load_config
    from acsoe.research.walkforward import read_settings

    config = load_config(CONFIG)
    settings = read_settings(config)
    embargo_s = settings.embargo_s(int(config.get("timeframes.decision_bar_s")))

    def manifest(index: int) -> dict[str, Any]:
        return json.loads((fold_dir(index) / "manifest.json").read_bytes())

    def window(fold: dict[str, Any]) -> pl.DataFrame:
        return (
            pl.scan_parquet(SORTED)
            .filter((pl.col("decision_ts") >= fold["train_start_ts"]) & (pl.col("decision_ts") < fold["test_end_ts"]))
            .select(["pair", "decision_ts", "label_window_end_ts"])
            .collect()
        )

    class _Fold:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.__dict__.update(payload)

    def verdict(rows: pl.DataFrame, target: dict[str, Any]) -> str:
        digest = identity_digest([str(v) for v in rows["pair"]], [int(v) for v in rows["decision_ts"]])
        same = rows.height == target["fold"]["train_rows"] and digest == target["training_identity"]
        return f"rows {rows.height}/{target['fold']['train_rows']}, identity {'MATCH' if same else 'DIFFERS'} -> {'ACCEPTED' if same else 'REFUSED'}"

    for index in (200, 404):
        own = manifest(index)
        fold = _Fold(own["fold"])
        frame = window(own["fold"])
        train, _, _ = training_rows(frame, fold, embargo_s)
        sys.stdout.write(f"fold {index} rows, fold {index} manifest: {verdict(train, own)}\n")
        neighbour = manifest(index - 1)
        sys.stdout.write(f"fold {index} rows, fold {index - 1} manifest: {verdict(train, neighbour)}\n")
        unpurged = frame.filter(
            (pl.col("decision_ts") < fold.test_start_ts) & (pl.col("decision_ts") < fold.test_start_ts - embargo_s)
        )
        sys.stdout.write(f"fold {index} rows without the purge: {verdict(unpurged, own)}\n")
        unembargoed = frame.filter(
            (pl.col("decision_ts") < fold.test_start_ts) & (pl.col("label_window_end_ts") < fold.test_start_ts)
        )
        sys.stdout.write(f"fold {index} rows without the embargo: {verdict(unembargoed, own)}\n")


def selfcheck(indices: list[int]) -> None:
    """The whole DI distribution against the trainer's own `_fit_and_score_di`, on small folds.

    The trainer's function runs `di.fit` in full (the slow search), handed an empty test frame so
    it scores nothing. Its reference identity must equal `di_reference`'s exactly and its
    leave-one-out distribution must equal `di_search`'s within `MODULE_TOLERANCE` on every row.
    """
    from threadpoolctl import threadpool_limits

    threadpool_limits(BLAS_THREADS)
    for index in indices:
        f = load_fold(index)
        training, config, run, train, names, seed = (f[k] for k in ("training", "config", "run", "train", "names", "seed"))
        width = len(names)
        fit_, _, _ = training._fit_and_score_di(
            _PlaceholderPercentile(config), train, f["test"].head(0), run.scaler, names, seed,
            np.empty((0, width), dtype=np.float64),
        )
        reference, ids = di_reference(training, config, train, run.scaler, names, seed)
        distribution, _ = di_search(reference, np.empty((0, width)), int(config.get("prediction.di_neighbours")))
        same_ids = tuple(ids) == tuple(fit_.identity)
        same_ref = reference.shape == fit_.reference.shape and bool(np.array_equal(reference, fit_.reference))
        diff = float(np.max(np.abs(distribution - fit_.distribution))) if same_ref else math.inf
        verdict = "AGREES" if same_ids and same_ref and diff <= MODULE_TOLERANCE else "DISAGREES"
        sys.stdout.write(
            f"fold {index}: reference {reference.shape[0]} rows, identity {'equal' if same_ids else 'DIFFERENT'}, "
            f"matrix {'equal' if same_ref else 'DIFFERENT'}, largest distribution difference {diff:.2e} -> {verdict}\n"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    command = sys.argv[3]
    try:
        if command == "prepare":
            prepare()
        elif command == "fit":
            chosen = [int(v) for v in sys.argv[5].split(",")] if len(sys.argv) > 5 else None
            fit(int(sys.argv[4]), chosen)
        elif command == "controls":
            controls()
        elif command == "selfcheck":
            selfcheck([int(v) for v in sys.argv[4].split(",")])
        else:
            raise Refused(f"unknown command {command!r}")
    except Refused as exc:
        sys.stdout.write(f"REFUSED: {exc}\n")
        raise SystemExit(1) from exc
