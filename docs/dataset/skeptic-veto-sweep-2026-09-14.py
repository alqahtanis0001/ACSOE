"""The skeptic veto sweep over the full run's 405 folds. Evidence for the operator's ruling on
`skeptic.veto_threshold`; it sets nothing.

Operator request 2026-09-14: using only what exists (no retraining, no new models), apply each
fold's trained skeptic to that fold's out-of-sample BUY calls and report, for veto thresholds
0.30 to 0.70 in steps of 0.05, the survivors (count, share, effective sample size), the target
rate of the survivors and of the vetoed rows.

**Why fold k's skeptic on fold k's BUY calls is out of sample.** The trainer fits fold k's
skeptic on BUY calls from folds before k whose label windows end before fold k's test window
and outside its embargo (`_skeptic_training_rows`), so none of fold k's own calls was seen.

**Scored exactly as the trainer scores.** Run with `PYTHONPATH` on the commit that trained the
artefacts (`6e09881`): `research.training._skeptic_matrix` (the fold's scaled features, then
`p_target, p_stop, p_timeout, expected_move_pct`), the fold's own verified scaler, and
LightGBM's text `skeptic.txt`; `P(wrong)` is the booster's binary output, and a call **survives
when `P(wrong) <= threshold`**, the rule `_skeptic_veto_report` and engine 15 apply.

**Checks before a number is kept.** `load_run` verifies every file hash including
`skeptic.txt`; the manifest's recorded skeptic inputs must equal the feature list plus
`SKEPTIC_EXTRA_INPUTS`; each fold's BUY-call count must equal its manifest's `buy_count`; the
join to the dataset must keep every BUY row.

**Two controls.** (1) The operator's: fold k's BUY calls scored with a *different* fold's
skeptic (that fold's scaler and model) must give different probabilities and a different
surviving set, or the sweep is measuring nothing. (2) A no-skill band: within each fold the
skeptic's own scores are shuffled across that fold's BUY calls, 20 seeded permutations, and the
same thresholds applied. Each permutation vetoes the same number of calls per fold with no
information, so its surviving target rate is what a veto rate alone buys.
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
OUT_DIR = REPO / "docs" / "dataset"
THRESHOLDS = [round(0.30 + 0.05 * step, 2) for step in range(9)]
PERMUTATIONS = 20
CONTROLS = [(404, 403), (404, 250), (300, 150), (200, 350)]


def fail(message: str) -> None:
    sys.stdout.write("REFUSED: " + message + "\n")
    raise SystemExit(1)


def fold_dir(index: int) -> Path:
    return MODELS / f"{RUN_ID}-f{index}"


def skeptic_scores(rows: pl.DataFrame, artefact_index: int, names: tuple[str, ...]) -> np.ndarray:
    directory = fold_dir(artefact_index)
    run = load_run(directory, expected_features=names, expected_version=FEATURE_VERSION)
    booster = lgb.Booster(model_file=str(directory / "skeptic.txt"))
    matrix = training._skeptic_matrix(rows, run.scaler, names)
    return np.asarray(booster.predict(matrix), dtype=np.float64)


def summarise(p_wrong: np.ndarray, hit: np.ndarray, weight: np.ndarray, threshold: float) -> dict:
    survive = p_wrong <= threshold
    n = int(hit.size)
    kept, vetoed = int(survive.sum()), int((~survive).sum())
    ess_kept = float(weight[survive].sum())
    rate_kept = float(hit[survive].mean()) if kept else None
    return {
        "threshold": threshold,
        "buy_calls": n,
        "survivors": kept,
        "survivor_share": kept / n if n else None,
        "survivor_effective_sample_size": ess_kept,
        "survivor_target_rate": rate_kept,
        "survivor_target_rate_se_by_ess": (
            math.sqrt(rate_kept * (1 - rate_kept) / ess_kept) if kept and ess_kept > 0 else None
        ),
        "vetoed": vetoed,
        "vetoed_effective_sample_size": float(weight[~survive].sum()),
        "vetoed_target_rate": float(hit[~survive].mean()) if vetoed else None,
    }


def main() -> int:
    oos = pl.read_parquet(OOS)
    buys = oos.filter(pl.col("is_buy"))
    all_rows_rate = float((oos["label"] == "target").mean())
    all_buy_rate = float((buys["label"] == "target").mean())
    sys.stdout.write(f"OOS {oos.height} rows, {buys.height} BUY calls, BUY target rate {all_buy_rate:.4f}\n")

    first = json.loads((fold_dir(0) / "manifest.json").read_bytes().decode("utf-8"))
    names = tuple(first["feature_names"])
    wanted_inputs = [*names, *training.SKEPTIC_EXTRA_INPUTS]
    dataset = pl.read_parquet(DATASET, columns=["pair", "decision_ts", *names])

    fold_count = len([p for p in MODELS.glob(f"{RUN_ID}-f*") if p.is_dir()])
    per_fold: dict[int, dict] = {}
    no_skeptic = {"folds": [], "buy_calls": 0, "target_hits": 0, "effective_sample_size": 0.0}
    for index in range(fold_count):
        manifest = json.loads((fold_dir(index) / "manifest.json").read_bytes().decode("utf-8"))
        metrics = manifest["metrics"]
        fold_buys = buys.filter(pl.col("fold_index") == index)
        if fold_buys.height != int(metrics["buy_count"]):
            fail(f"fold {index}: {fold_buys.height} BUY rows, manifest buy_count {metrics['buy_count']}")
        skeptic = (manifest.get("extras") or {}).get("skeptic")
        if skeptic is None:
            no_skeptic["folds"].append(index)
            no_skeptic["buy_calls"] += fold_buys.height
            no_skeptic["target_hits"] += int((fold_buys["label"] == "target").sum())
            no_skeptic["effective_sample_size"] += float(fold_buys["weight"].sum())
            continue
        if list(skeptic["input_names"]) != wanted_inputs:
            fail(f"fold {index}: the skeptic's recorded inputs are not the features plus SKEPTIC_EXTRA_INPUTS")
        lo, hi = manifest["fold"]["test_start_ts"], manifest["fold"]["test_end_ts"]
        window = dataset.filter((pl.col("decision_ts") >= lo) & (pl.col("decision_ts") < hi))
        rows = fold_buys.join(window, on=["pair", "decision_ts"], how="inner").sort(["decision_ts", "pair"])
        if rows.height != fold_buys.height:
            fail(f"fold {index}: the dataset join kept {rows.height} of {fold_buys.height} BUY rows")
        per_fold[index] = {
            "p_wrong": skeptic_scores(rows, index, names),
            "hit": (rows["label"] == "target").cast(pl.Float64).to_numpy(),
            "weight": rows["weight"].cast(pl.Float64).to_numpy(),
            "rows": rows if any(index == c[0] for c in CONTROLS) else None,
            "year": datetime.fromtimestamp(lo, tz=UTC).year,
        }
        if index % 50 == 0:
            sys.stdout.write(f"fold {index}: {rows.height} BUY calls scored\n")
            sys.stdout.flush()

    scored_folds = sorted(per_fold)
    p_all = np.concatenate([per_fold[k]["p_wrong"] for k in scored_folds])
    hit_all = np.concatenate([per_fold[k]["hit"] for k in scored_folds])
    w_all = np.concatenate([per_fold[k]["weight"] for k in scored_folds])
    scored_rate = float(hit_all.mean())

    table = [summarise(p_all, hit_all, w_all, t) for t in THRESHOLDS]

    # The no-skill band: each fold's scores shuffled across that fold's own BUY calls.
    generator = np.random.default_rng(20260914)
    band: dict[float, list[float]] = {t: [] for t in THRESHOLDS}
    for _ in range(PERMUTATIONS):
        shuffled = np.concatenate([generator.permutation(per_fold[k]["p_wrong"]) for k in scored_folds])
        for t in THRESHOLDS:
            survive = shuffled <= t
            band[t].append(float(hit_all[survive].mean()) if survive.any() else float("nan"))
    for row in table:
        values = band[row["threshold"]]
        row["no_skill_survivor_target_rate_min"] = min(values)
        row["no_skill_survivor_target_rate_max"] = max(values)

    by_year = {}
    for year in sorted({per_fold[k]["year"] for k in scored_folds}):
        ks = [k for k in scored_folds if per_fold[k]["year"] == year]
        p = np.concatenate([per_fold[k]["p_wrong"] for k in ks])
        h = np.concatenate([per_fold[k]["hit"] for k in ks])
        w = np.concatenate([per_fold[k]["weight"] for k in ks])
        by_year[year] = [summarise(p, h, w, t) for t in (0.5, 0.6, 0.7)]

    controls = []
    for own, other in CONTROLS:
        entry = per_fold.get(own)
        if entry is None or other not in per_fold:
            fail(f"control ({own}, {other}) names a fold without a skeptic")
        other_scores = skeptic_scores(entry["rows"], other, names)
        own_scores = entry["p_wrong"]
        control = {
            "rows_of_fold": own,
            "skeptic_of_fold": other,
            "buy_calls": int(own_scores.size),
            "mean_abs_p_wrong_difference": float(np.mean(np.abs(own_scores - other_scores))),
            "max_abs_p_wrong_difference": float(np.max(np.abs(own_scores - other_scores))),
            "by_threshold": [],
        }
        for t in (0.5, 0.6, 0.7):
            a, b = own_scores <= t, other_scores <= t
            control["by_threshold"].append({
                "threshold": t,
                "own_survivors": int(a.sum()),
                "other_survivors": int(b.sum()),
                "calls_whose_verdict_differs": int((a != b).sum()),
                "own_survivor_target_rate": float(entry["hit"][a].mean()) if a.any() else None,
                "other_survivor_target_rate": float(entry["hit"][b].mean()) if b.any() else None,
            })
        controls.append(control)

    report = {
        "meta": {
            "measured_on": datetime.now(UTC).date().isoformat(),
            "run_id": RUN_ID,
            "coverage": "405 of 457 folds; the run died at fold 405 (see the digest's coverage block)",
            "oos_file": str(OOS.relative_to(REPO)),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "rule": "a BUY call survives when the skeptic's P(wrong) <= threshold; vetoed when above",
            "all_test_rows_target_rate": all_rows_rate,
            "all_buy_calls": int(buys.height),
            "all_buy_calls_target_rate": all_buy_rate,
            "scored_folds": len(scored_folds),
            "scored_buy_calls": int(hit_all.size),
            "scored_buy_calls_target_rate": scored_rate,
            "scored_buy_calls_effective_sample_size": float(w_all.sum()),
            "folds_without_a_skeptic": no_skeptic["folds"],
            "buy_calls_without_a_skeptic": no_skeptic["buy_calls"],
            "buy_calls_without_a_skeptic_target_rate": (
                no_skeptic["target_hits"] / no_skeptic["buy_calls"] if no_skeptic["buy_calls"] else None
            ),
            "effective_sample_size_note": (
                "the sum of the survivors' uniqueness weights (spec 59 decision 5). The standard "
                "error beside it is sqrt(p(1-p)/effective size), an approximation that ignores "
                "correlation between pairs and between folds, so it is a floor on the uncertainty"
            ),
            "no_skill_band_note": (
                f"{PERMUTATIONS} permutations of each fold's own skeptic scores across that fold's "
                "BUY calls; the same per-fold veto counts with no information in them"
            ),
            "recommends": None,
        },
        "sweep": table,
        "by_test_year_at_0.5_0.6_0.7": by_year,
        "different_fold_controls": controls,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "skeptic-veto-sweep-2026-09-14.json"
    if out.exists():
        fail(f"{out} exists; this script never overwrites")
    out.write_bytes(json.dumps(report, sort_keys=True, indent=2).encode("utf-8") + b"\n")
    sys.stdout.write(json.dumps({"meta": report["meta"], "sweep": table, "controls": controls}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
