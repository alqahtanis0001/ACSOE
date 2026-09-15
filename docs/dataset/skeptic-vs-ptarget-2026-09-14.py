"""Does the skeptic add anything over the predictor's own confidence? A matched-count control.

Operator request 2026-09-14, after the skeptic veto sweep. For each veto threshold and each fold,
N is exactly the number of that fold's out-of-sample BUY calls the skeptic let through
(P(wrong) <= threshold). The comparator takes that fold's top N BUY calls ranked by the
predictor's own calibrated `p_target`. If the comparator reaches the skeptic's target rate at
matched counts, the skeptic adds nothing over the predictor's confidence.

**Ties.** `p_target` is calibrated by per-class isotonic regression and renormalised, so it is
piecewise constant and ties at the cut are expected. They are broken at random with a fixed
seed, the tie count at each cut is reported, and the whole comparator is run under two seeds.

**Proof the comparison can fail.** (1) Positive control: the same top-N machinery ranked by the
skeptic's own score (lowest P(wrong) first) must reproduce the skeptic's survivor count, target
rate and effective size exactly; if it does not, the matching is wrong and every comparator
number is too. (2) Negative control: the same machinery ranked at random must land in the
no-skill band the sweep reported, not near the skeptic.

Scored as in `skeptic-veto-sweep-2026-09-14.py`: the trainer's `_skeptic_matrix` on the commit
that trained the artefacts, each fold's verified scaler and `skeptic.txt`, every BUY count and
join checked against the manifest. Nothing is trained; nothing is written to config.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

from acsoe.modelling.artefacts import load_run
from acsoe.modelling.features import FEATURE_VERSION
from acsoe.research import training

REPO = Path(sys.argv[1])
RUN_ID = "train-20260913T205245-067b2b9d"
OOS = REPO / "data" / "derived" / f"oos_{RUN_ID}.parquet"
DATASET = REPO / "data" / "derived" / "dataset_20260913T205245.parquet"
MODELS = REPO / "models"
OUT = REPO / "docs" / "dataset" / "skeptic-vs-ptarget-2026-09-14.json"
THRESHOLDS = [round(0.30 + 0.05 * step, 2) for step in range(9)]
SEEDS = (20260914, 7)


def fail(message: str) -> None:
    sys.stdout.write("REFUSED: " + message + "\n")
    raise SystemExit(1)


def top_n(order_key: np.ndarray, n: int, generator: np.random.Generator) -> tuple[np.ndarray, int]:
    """Indices of the n rows with the largest key, ties at the cut broken at random.

    Returns the selection and how many rows share the key value at the cut (0 when n is 0 or
    covers every row), which is how much of the selection the tie-break decided.
    """
    size = order_key.size
    if n <= 0:
        return np.zeros(size, dtype=bool), 0
    if n >= size:
        return np.ones(size, dtype=bool), 0
    jitter = generator.random(size)
    order = np.lexsort((jitter, -order_key))  # primary: key descending; ties: random
    chosen = np.zeros(size, dtype=bool)
    chosen[order[:n]] = True
    cut = order_key[order[n - 1]]
    tied = int(np.sum(order_key == cut)) if order_key[order[n]] == cut else 0
    return chosen, tied


def stats(hit: np.ndarray, weight: np.ndarray, mask: np.ndarray) -> dict:
    n = int(mask.sum())
    ess = float(weight[mask].sum())
    rate = float(hit[mask].mean()) if n else None
    return {
        "count": n,
        "effective_sample_size": ess,
        "target_rate": rate,
        "target_rate_se_by_ess": math.sqrt(rate * (1 - rate) / ess) if n and ess > 0 else None,
    }


def main() -> int:
    buys = pl.read_parquet(OOS).filter(pl.col("is_buy"))
    first = json.loads((MODELS / f"{RUN_ID}-f0" / "manifest.json").read_bytes().decode("utf-8"))
    names = tuple(first["feature_names"])
    wanted_inputs = [*names, *training.SKEPTIC_EXTRA_INPUTS]
    dataset = pl.read_parquet(DATASET, columns=["pair", "decision_ts", *names])

    folds = []
    fold_count = len([p for p in MODELS.glob(f"{RUN_ID}-f*") if p.is_dir()])
    for index in range(fold_count):
        directory = MODELS / f"{RUN_ID}-f{index}"
        manifest = json.loads((directory / "manifest.json").read_bytes().decode("utf-8"))
        fold_buys = buys.filter(pl.col("fold_index") == index)
        if fold_buys.height != int(manifest["metrics"]["buy_count"]):
            fail(f"fold {index}: BUY count differs from the manifest")
        skeptic = (manifest.get("extras") or {}).get("skeptic")
        if skeptic is None:
            continue
        if list(skeptic["input_names"]) != wanted_inputs:
            fail(f"fold {index}: skeptic inputs differ from the features plus SKEPTIC_EXTRA_INPUTS")
        lo, hi = manifest["fold"]["test_start_ts"], manifest["fold"]["test_end_ts"]
        window = dataset.filter((pl.col("decision_ts") >= lo) & (pl.col("decision_ts") < hi))
        rows = fold_buys.join(window, on=["pair", "decision_ts"], how="inner").sort(["decision_ts", "pair"])
        if rows.height != fold_buys.height:
            fail(f"fold {index}: the dataset join lost BUY rows")
        run = load_run(directory, expected_features=names, expected_version=FEATURE_VERSION)
        booster = lgb.Booster(model_file=str(directory / "skeptic.txt"))
        p_wrong = np.asarray(booster.predict(training._skeptic_matrix(rows, run.scaler, names)), dtype=np.float64)
        folds.append({
            "index": index,
            "p_wrong": p_wrong,
            "p_target": rows["p_target"].cast(pl.Float64).to_numpy(),
            "hit": (rows["label"] == "target").cast(pl.Float64).to_numpy(),
            "weight": rows["weight"].cast(pl.Float64).to_numpy(),
        })
        if index % 100 == 0:
            sys.stdout.write(f"fold {index} scored\n")
            sys.stdout.flush()

    hit = np.concatenate([f["hit"] for f in folds])
    weight = np.concatenate([f["weight"] for f in folds])
    results = []
    positive_ok = True
    for t in THRESHOLDS:
        skeptic_mask = np.concatenate([f["p_wrong"] <= t for f in folds])
        row = {"threshold": t, "skeptic": stats(hit, weight, skeptic_mask)}
        # Positive control: top-N by the skeptic's own score must reproduce the skeptic.
        gen = np.random.default_rng(SEEDS[0])
        own = np.concatenate([top_n(-f["p_wrong"], int((f["p_wrong"] <= t).sum()), gen)[0] for f in folds])
        row["control_topN_by_skeptic_score"] = stats(hit, weight, own)
        row["control_topN_by_skeptic_score_identical_set"] = bool(np.array_equal(own, skeptic_mask))
        positive_ok &= row["control_topN_by_skeptic_score_identical_set"]
        for seed in SEEDS:
            gen = np.random.default_rng(seed)
            picks, ties = [], 0
            for f in folds:
                chosen, tied = top_n(f["p_target"], int((f["p_wrong"] <= t).sum()), gen)
                picks.append(chosen)
                ties += tied
            mask = np.concatenate(picks)
            entry = stats(hit, weight, mask)
            entry["rows_tied_at_the_cuts"] = ties
            entry["overlap_with_skeptic_survivors"] = int((mask & skeptic_mask).sum())
            row[f"topN_by_p_target_seed_{seed}"] = entry
        # Negative control: top-N by a random score.
        gen = np.random.default_rng(SEEDS[0] + 1)
        random_mask = np.concatenate([
            top_n(gen.random(f["p_wrong"].size), int((f["p_wrong"] <= t).sum()), gen)[0] for f in folds
        ])
        row["control_topN_random"] = stats(hit, weight, random_mask)
        results.append(row)
        s, p = row["skeptic"], row[f"topN_by_p_target_seed_{SEEDS[0]}"]
        sys.stdout.write(
            f"t={t:.2f} N={s['count']} skeptic {s['target_rate']:.4f} (ess {s['effective_sample_size']:.0f}) | "
            f"p_target {p['target_rate']:.4f} (ess {p['effective_sample_size']:.0f}, ties {p['rows_tied_at_the_cuts']}) | "
            f"own-score {row['control_topN_by_skeptic_score']['target_rate']:.4f} identical={row['control_topN_by_skeptic_score_identical_set']} | "
            f"random {row['control_topN_random']['target_rate']:.4f}\n"
        )
    if not positive_ok:
        fail("the top-N machinery did not reproduce the skeptic's own survivors; no comparator number is trustworthy")

    report = {
        "meta": {
            "measured_on": datetime.now(UTC).date().isoformat(),
            "run_id": RUN_ID,
            "coverage": "405 of 457 folds; folds 1 to 404 carry a skeptic",
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scored_folds": len(folds),
            "scored_buy_calls": int(hit.size),
            "scored_buy_calls_target_rate": float(hit.mean()),
            "scored_buy_calls_effective_sample_size": float(weight.sum()),
            "rule": "per fold, N = skeptic survivors (P(wrong) <= threshold); comparator = that fold's top N by p_target, ties at random",
            "seeds": list(SEEDS),
            "recommends": None,
        },
        "by_threshold": results,
    }
    if OUT.exists():
        fail(f"{OUT} exists; this script never overwrites")
    OUT.write_bytes(json.dumps(report, sort_keys=True, indent=2).encode("utf-8") + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
