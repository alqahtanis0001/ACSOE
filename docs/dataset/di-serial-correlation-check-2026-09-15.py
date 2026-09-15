"""Why the DI's leave-one-out threshold refuses most out-of-sample rows: a diagnostic, not a fix.

`modelling.di` thresholds a row's mean distance to its 10 nearest reference rows at a percentile of
the **leave-one-out** distribution over the reference set, which removes only the row itself. The
reference set is the last 30 days of each pair's training rows, and consecutive 15-minute bars of
one pair carry nearly identical rolling features, so a reference row's nearest neighbours are its
own pair's adjacent bars. A test row sits at least the 48-bar embargo, and up to a week and a half,
after the last reference row of its pair, and has no such neighbours.

For sampled reference rows of one fold this recomputes the same statistic (the module's
arithmetic: squared-norm expansion, `np.partition`, mean of the 10 smallest) three ways, excluding
(a) the row itself, which is exactly leave-one-out, (b) and (c) every row of the same pair within 48
bars (the embargo) or 7 days (the retrain interval), and (d) and (e) every row of **any** pair within
48 bars or 7 days, because 78 of the 117 columns are the BTC and ETH macro features, identical for
every pair on the same bar, and the time-of-day and weekday columns are too; and compares
each distribution's percentiles with the fold's out-of-sample DI saved by
`di-anomaly-fit-2026-09-14.py`. Nothing is written to config or to any artefact.

    python di-serial-correlation-check-2026-09-15.py <repo> <config> <fold,fold,...>
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

REPO, CONFIG = sys.argv[1], sys.argv[2]
FOLDS = [int(v) for v in sys.argv[3].split(",")]
SAMPLE = 2_000
PERCENTILES = [0.5, 0.9, 0.95, 0.99, 0.999]
EXCLUSIONS = {
    "leave_one_out": None,
    "same_pair_48_bars": ("pair", 48 * 900),
    "same_pair_7_days": ("pair", 7 * 86_400),
    "any_pair_48_bars": ("any", 48 * 900),
    "any_pair_7_days": ("any", 7 * 86_400),
}

sys.argv = [sys.argv[0], REPO, CONFIG, "import"]
spec = importlib.util.spec_from_file_location("fit", Path(REPO) / "docs/dataset/di-anomaly-fit-2026-09-14.py")
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)


def excluded_mean_nearest(reference, pairs, stamps, rows, window, neighbours):
    norms = np.sum(reference**2, axis=1)
    out = np.empty(rows.size)
    for start in range(0, rows.size, 256):
        chunk = rows[start : start + 256]
        block = reference[chunk]
        squared = np.sum(block**2, axis=1)[:, None] - 2.0 * block @ reference.T + norms[None, :]
        np.maximum(squared, 0.0, out=squared)
        distances = np.sqrt(squared)
        distances[np.arange(chunk.size), chunk] = np.inf
        if window is not None:
            scope, span = window
            near = np.abs(stamps[None, :] - stamps[chunk][:, None]) <= span
            if scope == "pair":
                near &= pairs[None, :] == pairs[chunk][:, None]
            distances[near] = np.inf
        out[start : start + chunk.size] = np.partition(distances, neighbours - 1, axis=1)[:, :neighbours].mean(axis=1)
    return out


report = []
for index in FOLDS:
    f = fit.load_fold(index)
    config, run, train, names, seed = (f[k] for k in ("config", "run", "train", "names", "seed"))
    reference, ids = fit.di_reference(f["training"], config, train, run.scaler, names, seed)
    neighbours = int(config.get("prediction.di_neighbours"))
    codes = {p: i for i, p in enumerate(sorted({e.split("|")[0] for e in ids}))}
    pairs = np.array([codes[e.split("|")[0]] for e in ids])
    stamps = np.array([int(e.split("|")[1]) for e in ids])
    rows = np.sort(np.random.default_rng(index).choice(reference.shape[0], size=min(SAMPLE, reference.shape[0]), replace=False))
    with np.load(fit.OUT / f"fold_{index:03d}.npz") as payload:
        saved = np.asarray(payload["di_distribution"])
    test = pl.read_parquet(fit.OUT / f"fold_{index:03d}.parquet")["di"].to_numpy()
    test = test[~np.isnan(test)]
    entry = {"fold_index": index, "reference_rows": int(reference.shape[0]), "sampled": int(rows.size), "test_rows": int(test.size)}
    for name, window in EXCLUSIONS.items():
        values = excluded_mean_nearest(reference, pairs, stamps, rows, window, neighbours)
        if window is None:
            entry["leave_one_out_matches_saved_distribution"] = float(np.max(np.abs(values - saved[rows])))
        entry[name] = {
            "quantiles": {str(p): float(np.quantile(values, p)) for p in PERCENTILES},
            "out_of_sample_refused_at": {str(p): float(np.mean(test > np.quantile(values, p))) for p in PERCENTILES},
        }
    entry["out_of_sample_di_quantiles"] = {str(p): float(np.quantile(test, p)) for p in PERCENTILES}
    report.append(entry)
    print(json.dumps(entry), flush=True)

out = Path(REPO) / "docs" / "dataset" / "di-serial-correlation-check-2026-09-15.json"
out.write_bytes(json.dumps(report, indent=1, sort_keys=True).encode("utf-8") + b"\n")
