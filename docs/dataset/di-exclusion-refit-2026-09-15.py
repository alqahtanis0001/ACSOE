"""Refit every fold's DI leave-one-out distribution with the 48-bar exclusion, and report refusal.

Operator ruling 1 of 2026-09-15, amending ruling 6 of 2026-09-12: the leave-one-out statistic
excludes **every reference row within 48 bars of the row being scored, across all pairs**, not the
row alone. 78 of the 117 DI columns are macro features shared by every pair on a bar, so the plain
leave-one-out kept near-identical same-moment neighbours and its threshold measured time
proximity rather than distributional distance (`di-anomaly-distributions-2026-09-14.md`).

Only the reference distribution changes. A test row's DI is its mean distance to the 10 nearest
reference rows, and the reference window ends at least the embargo before the test window, so
no reference row is within 48 bars of a test row and the saved test DI of
`di-anomaly-fit-2026-09-14.py` stands unchanged. That is asserted per fold, not assumed.

Per fold: the reference set rebuilt exactly as before (`di_reference`, which is the trainer's
selection), then for each decision bar t the rows with `|decision_ts - t| <= 48 x 900 s` are
removed from the candidate neighbours of every reference row at t, by searching the rows before the
excluded span and the rows after it with scikit-learn's exact brute-force k-nearest, 32 bars of
queries per call, the band between them in numpy with each query's own span masked, and merging. Held to plain numpy on 16 sampled rows per fold (squared-norm expansion, the span masked to
infinity, mean of the 10 smallest), refusing beyond 1e-9.

    python di-exclusion-refit-2026-09-15.py <repo> <config> fit
    python di-exclusion-refit-2026-09-15.py <repo> <config> report
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

REPO, CONFIG, COMMAND = sys.argv[1], sys.argv[2], sys.argv[3]
THREADS = int(os.environ.get("DI_THREADS", "16"))
VERIFY_ROWS = 16
TOLERANCE = 1e-9
PERCENTILES = [0.95, 0.99, 0.999]

sys.argv = [sys.argv[0], REPO, CONFIG, "import"]
_spec = importlib.util.spec_from_file_location("fit", Path(REPO) / "docs/dataset/di-anomaly-fit-2026-09-14.py")
fit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fit)
OUT = fit.OUT


def excluded_loo(
    reference: np.ndarray, stamps: np.ndarray, neighbours: int, span_s: int, group_bars: int = 32
) -> np.ndarray:
    """Mean distance to the `neighbours` nearest reference rows more than `span_s` away in time.

    Queries are taken `group_bars` decision bars at a time. Rows earlier than the group's first
    bar minus the span, and later than its last bar plus the span, are outside every query's
    exclusion and are searched with scikit-learn's exact brute force; the band between those
    two cuts is searched in numpy with each query's own span masked to infinity. The candidates
    are merged and the `neighbours` smallest averaged. Grouping only removes call overhead: every
    query still sees exactly the rows with `|decision_ts - t| > span_s`.
    """
    from sklearn.metrics._pairwise_distances_reduction import ArgKmin

    order = np.argsort(stamps, kind="stable")
    ref = np.ascontiguousarray(reference[order])
    ts = stamps[order]
    norms = np.sum(ref**2, axis=1)
    out_sorted = np.empty(ref.shape[0], dtype=np.float64)
    bars, starts = np.unique(ts, return_index=True)
    ends = np.append(starts[1:], ts.size)
    for g in range(0, bars.size, group_bars):
        last = min(g + group_bars, bars.size) - 1
        qs, qe = int(starts[g]), int(ends[last])
        queries, qts = ref[qs:qe], ts[qs:qe]
        lo = int(np.searchsorted(ts, bars[g] - span_s, side="left"))
        hi = int(np.searchsorted(ts, bars[last] + span_s, side="right"))
        parts = []
        for block in (ref[:lo], ref[hi:]):
            if block.shape[0]:
                k = min(neighbours, block.shape[0])
                parts.append(np.asarray(ArgKmin.compute(queries, block, k, metric="euclidean", return_distance=True)[0]))
        if hi > lo:
            band = ref[lo:hi]
            squared = np.sum(queries**2, axis=1)[:, None] - 2.0 * queries @ band.T + norms[None, lo:hi]
            np.maximum(squared, 0.0, out=squared)
            distances = np.sqrt(squared)
            distances[np.abs(ts[None, lo:hi] - qts[:, None]) <= span_s] = np.inf
            k = min(neighbours, band.shape[0])
            parts.append(np.partition(distances, k - 1, axis=1)[:, :k])
        merged = np.concatenate(parts, axis=1) if parts else np.empty((queries.shape[0], 0))
        if merged.shape[1] < neighbours:
            raise fit.Refused(f"bars from {bars[g]}: fewer than {neighbours} candidate rows")
        merged.sort(axis=1)
        if not np.isfinite(merged[:, neighbours - 1]).all():
            raise fit.Refused(f"bars from {bars[g]}: fewer than {neighbours} rows outside the exclusion span")
        out_sorted[qs:qe] = merged[:, :neighbours].mean(axis=1)
    out = np.empty_like(out_sorted)
    out[order] = out_sorted
    return out


def direct(reference: np.ndarray, stamps: np.ndarray, rows: np.ndarray, neighbours: int, span_s: int) -> np.ndarray:
    norms = np.sum(reference**2, axis=1)
    block = reference[rows]
    squared = np.sum(block**2, axis=1)[:, None] - 2.0 * block @ reference.T + norms[None, :]
    np.maximum(squared, 0.0, out=squared)
    distances = np.sqrt(squared)
    distances[np.abs(stamps[None, :] - stamps[rows][:, None]) <= span_s] = np.inf
    return np.partition(distances, neighbours - 1, axis=1)[:, :neighbours].mean(axis=1)


def fit_all() -> None:
    from threadpoolctl import threadpool_limits

    threadpool_limits(THREADS)
    indices = fit.fold_indices()
    # DI_ORDER=ascending lets a second process work up from fold 0 while the first works down.
    for index in sorted(indices, reverse=os.environ.get("DI_ORDER", "descending") != "ascending"):
        target = OUT / f"excl_fold_{index:03d}.npz"
        if target.exists():
            continue
        started = time.perf_counter()
        f = fit.load_fold(index)
        config, run, train, names, seed = (f[k] for k in ("config", "run", "train", "names", "seed"))
        span_s = int(config.get("backtest.embargo_bars")) * int(config.get("timeframes.decision_bar_s"))
        neighbours = int(config.get("prediction.di_neighbours"))
        reference, ids = fit.di_reference(f["training"], config, train, run.scaler, names, seed)
        stamps = np.array([int(e.split("|")[1]) for e in ids], dtype=np.int64)
        summary = json.loads((OUT / f"fold_{index:03d}.json").read_bytes())
        identity = f["identity_digest"]([e.split("|")[0] for e in ids], [int(e.split("|")[1]) for e in ids])
        if identity != summary["di"]["reference_identity"]:
            raise fit.Refused(f"fold {index}: reference identity differs from the first fit")
        if int(stamps.max()) >= int(f["fold"].test_start_ts) - span_s:
            raise fit.Refused(f"fold {index}: a reference row is within the exclusion span of the test window")
        distribution = excluded_loo(reference, stamps, neighbours, span_s)
        rows = np.random.default_rng(index).choice(reference.shape[0], size=min(VERIFY_ROWS, reference.shape[0]), replace=False)
        worst = float(np.max(np.abs(direct(reference, stamps, rows, neighbours, span_s) - distribution[rows])))
        if worst > TOLERANCE:
            raise fit.Refused(f"fold {index}: excluded leave-one-out differs from direct numpy by {worst}")
        tmp = OUT / f"excl_fold_{index:03d}.tmp.npz"
        np.savez(tmp, di_distribution=distribution, span_s=np.int64(span_s), worst=np.float64(worst))
        os.replace(tmp, target)
        print(
            f"{time.strftime('%H:%M:%S')} fold {index}: ref {reference.shape[0]}, diff {worst:.1e}, "
            f"median {np.median(distribution):.3f}, {time.perf_counter() - started:.0f}s",
            flush=True,
        )


def report() -> None:
    oos = pl.read_parquet(
        fit.REPO / "data" / "derived" / f"oos_{fit.RUN_ID}.parquet",
        columns=["pair", "decision_ts", "fold_index", "label", "return_pct", "weight", "is_buy"],
    )
    # Only the folds refitted so far. The coverage is written into the report, so a partial
    # report says it is one rather than passing for the whole run.
    indices = [k for k in fit.fold_indices() if (OUT / f"excl_fold_{k:03d}.npz").exists()]
    oos = oos.filter(pl.col("fold_index").is_in(indices))
    scores = pl.concat([pl.read_parquet(OUT / f"fold_{k:03d}.parquet") for k in indices])
    joined = oos.join(scores, on=["pair", "decision_ts", "fold_index"], how="inner")
    if joined.height != oos.height:
        raise fit.Refused(f"join keeps {joined.height} of {oos.height}")
    complete = joined.filter(pl.col("di").is_not_nan()).with_columns(
        pl.from_epoch("decision_ts", time_unit="s").dt.year().alias("year")
    )
    result: dict = {
        "run_id": fit.RUN_ID,
        "folds_refitted": len(indices),
        "folds_in_run": len(fit.fold_indices()),
        "fold_indices": indices,
        "scored_rows": complete.height,
        "percentiles": {},
    }
    worst = 0.0
    for p in PERCENTILES:
        table = []
        for k in indices:
            with np.load(OUT / f"excl_fold_{k:03d}.npz") as payload:
                table.append((k, float(np.quantile(payload["di_distribution"], p))))
                worst = max(worst, float(payload["worst"]))
        thresholds = pl.DataFrame(table, schema={"fold_index": complete.schema["fold_index"], "_thr": pl.Float64}, orient="row")
        marked = complete.join(thresholds, on="fold_index").with_columns((pl.col("di") > pl.col("_thr")).alias("_refused"))

        def rates(frame: pl.DataFrame) -> dict:
            if frame.height == 0:
                return {"rows": 0}
            return {
                "rows": frame.height,
                "effective": float(frame["weight"].sum()),
                "target_rate": float((frame["label"] == "target").mean()),
                "stop_rate": float((frame["label"] == "stop").mean()),
                "mean_return_pct": float(frame["return_pct"].mean()),
            }

        per_fold = marked.group_by("fold_index").agg(pl.col("_refused").mean().alias("s"))["s"]
        result["percentiles"][str(p)] = {
            "refused_share": float(marked["_refused"].mean()),
            "nominal": round(1 - p, 6),
            "folds_refused_share": {"min": float(per_fold.min()), "median": float(per_fold.median()), "max": float(per_fold.max())},
            "refused": rates(marked.filter(pl.col("_refused"))),
            "kept": rates(marked.filter(~pl.col("_refused"))),
            "buy_refused_share": float(marked.filter(pl.col("is_buy"))["_refused"].mean()),
            "by_year": {
                str(y): float(g["_refused"].mean())
                for (y,), g in sorted(marked.group_by(["year"]), key=lambda item: item[0][0])
            },
        }
        print(p, json.dumps(result["percentiles"][str(p)]), flush=True)
    result["largest_difference_from_direct_numpy"] = worst
    target = fit.REPO / "docs" / "dataset" / "di-exclusion-refit-2026-09-15.json"
    target.write_bytes(json.dumps(result, indent=1, sort_keys=True).encode("utf-8") + b"\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    try:
        {"fit": fit_all, "report": report}[COMMAND]()
    except fit.Refused as exc:
        print(f"REFUSED: {exc}", flush=True)
        raise SystemExit(1) from exc
