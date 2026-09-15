"""The DI and anomaly score distributions of run `train-20260913T205245-067b2b9d`, per fold, and what
each candidate percentile would refuse out of sample. Evidence for the operator's ruling on
`prediction.di_percentile` and `anomaly.threshold_percentile`; it recommends nothing and sets
nothing.

Reads the per-fold output of `di-anomaly-fit-2026-09-14.py` (which fits nothing new: the DI through
the trainer's own `_fit_and_score_di` on identity-verified training rows, the anomaly scores from
each fold's saved forest) and the run's out-of-sample file for labels, weights and BUY calls.

**Every threshold here is computed the way the artefact would compute it.** For a percentile p,
fold k's DI threshold is `np.quantile(leave-one-out distribution, p)` (`modelling.di.fit`) and a
test row is refused when its DI is **strictly above** it (`modelling.di.score`); fold k's anomaly
threshold is `np.quantile(-score_samples over its complete training rows, p)` (`_fit_anomaly`)
and a test row is blocked when its score is **strictly above** it (engine 13). A test row whose
vector is incomplete has no DI and no anomaly score: engines 8 and 13 block it whatever the
percentile, and it is reported as its own line, never folded into either rate.

    python di-anomaly-distributions-2026-09-14.py <repo>
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl

REPO = Path(sys.argv[1])
RUN_ID = "train-20260913T205245-067b2b9d"
OOS = REPO / "data" / "derived" / f"oos_{RUN_ID}.parquet"
FITS = REPO / "data" / "derived" / f"di_anomaly_{RUN_ID}"
OUT_JSON = REPO / "docs" / "dataset" / "di-anomaly-distributions-2026-09-14.json"
PERCENTILES = [0.80, 0.90, 0.95, 0.975, 0.99, 0.995, 0.999]
BY_YEAR_PERCENTILES = [0.95, 0.99]
JOINT = [0.95, 0.99, 0.995]


def fail(message: str) -> None:
    sys.stdout.write("REFUSED: " + message + "\n")
    raise SystemExit(1)


def rates(frame: pl.DataFrame) -> dict:
    n = frame.height
    if n == 0:
        return {"rows": 0, "effective": 0.0, "target_rate": None, "stop_rate": None, "mean_return_pct": None}
    return {
        "rows": n,
        "effective": float(frame["weight"].sum()),
        "target_rate": float((frame["label"] == "target").mean()),
        "stop_rate": float((frame["label"] == "stop").mean()),
        "mean_return_pct": float(frame["return_pct"].mean()),
    }


def main() -> int:
    markers = sorted(FITS.glob("fold_*.json"))
    summaries = [json.loads(path.read_bytes()) for path in markers]
    indices = [int(s["fold_index"]) for s in summaries]
    if indices != list(range(405)):
        fail(f"expected folds 0 to 404 fitted, found {len(indices)}")

    thresholds: dict[str, dict[float, dict[int, float]]] = {"di": {}, "anomaly": {}}
    fold_rows = []
    for summary in summaries:
        k = int(summary["fold_index"])
        with np.load(FITS / f"fold_{k:03d}.npz") as payload:
            distribution = np.asarray(payload["di_distribution"], dtype=np.float64)
            train_scores = np.asarray(payload["anomaly_train_scores"], dtype=np.float64)
        if distribution.size != int(summary["di"]["reference_rows"]):
            fail(f"fold {k}: DI distribution has {distribution.size} values, reference {summary['di']['reference_rows']}")
        row = {
            "fold_index": k,
            "test_start": datetime.fromtimestamp(int(summary["test_start_ts"]), UTC).date().isoformat(),
            "di_reference_rows": int(distribution.size),
            "anomaly_train_rows": int(train_scores.size),
        }
        for p in PERCENTILES:
            thresholds["di"].setdefault(p, {})[k] = float(np.quantile(distribution, p))
            row[f"di_threshold_{p}"] = thresholds["di"][p][k]
            if train_scores.size:
                thresholds["anomaly"].setdefault(p, {})[k] = float(np.quantile(train_scores, p))
                row[f"anomaly_threshold_{p}"] = thresholds["anomaly"][p][k]
        fold_rows.append(row)

    scores = pl.concat([pl.read_parquet(FITS / f"fold_{k:03d}.parquet") for k in indices], how="vertical")
    oos = pl.read_parquet(OOS, columns=["pair", "decision_ts", "fold_index", "label", "return_pct", "weight", "is_buy"])
    joined = oos.join(scores, on=["pair", "decision_ts", "fold_index"], how="inner")
    if joined.height != oos.height or scores.height != oos.height:
        fail(f"join keeps {joined.height} of {oos.height} out-of-sample rows ({scores.height} scored rows)")
    joined = joined.with_columns(pl.from_epoch("decision_ts", time_unit="s").dt.year().alias("year"))

    di_complete = joined.filter(pl.col("di").is_not_nan())
    anomaly_complete = joined.filter(pl.col("anomaly_score").is_not_nan())
    report: dict = {
        "run_id": RUN_ID,
        "measured_at": datetime.now(UTC).isoformat(),
        "coverage": {
            "folds": len(indices),
            "test_rows": joined.height,
            "di_scored_rows": di_complete.height,
            "di_incomplete_rows": joined.height - di_complete.height,
            "anomaly_scored_rows": anomaly_complete.height,
            "anomaly_incomplete_rows": joined.height - anomaly_complete.height,
            "di_reference_rows": {
                "min": min(r["di_reference_rows"] for r in fold_rows),
                "median": float(np.median([r["di_reference_rows"] for r in fold_rows])),
                "max": max(r["di_reference_rows"] for r in fold_rows),
                "folds_at_cap": sum(1 for r in fold_rows if r["di_reference_rows"] == 200_000),
            },
        },
        "all_rows": rates(joined),
        "incomplete": {
            "di": rates(joined.filter(pl.col("di").is_nan())),
            "anomaly": rates(joined.filter(pl.col("anomaly_score").is_nan())),
            "by_year": {
                str(year): {
                    "rows": group.height,
                    "di_incomplete_share": float(group["di"].is_nan().mean()),
                    "anomaly_incomplete_share": float(group["anomaly_score"].is_nan().mean()),
                    "buy_calls_di_incomplete_share": float(
                        group.filter(pl.col("is_buy"))["di"].is_nan().mean() or 0.0
                    ),
                }
                for (year,), group in sorted(joined.group_by(["year"]), key=lambda item: item[0][0])
            },
        },
        "folds": fold_rows,
    }

    def with_threshold(frame: pl.DataFrame, gate: str, p: float) -> pl.DataFrame:
        table = pl.DataFrame(
            {"fold_index": list(thresholds[gate][p].keys()), "_thr": list(thresholds[gate][p].values())},
            schema={"fold_index": frame.schema["fold_index"], "_thr": pl.Float64},
        )
        column = "di" if gate == "di" else "anomaly_score"
        return frame.join(table, on="fold_index", how="inner").with_columns(
            (pl.col(column) > pl.col("_thr")).alias("_refused")
        )

    for gate, frame in (("di", di_complete), ("anomaly", anomaly_complete)):
        section = []
        for p in PERCENTILES:
            marked = with_threshold(frame, gate, p)
            refused = marked.filter(pl.col("_refused"))
            kept = marked.filter(~pl.col("_refused"))
            by_pair = marked.group_by("pair").agg(pl.col("_refused").mean().alias("share"))
            buys = marked.filter(pl.col("is_buy"))
            entry = {
                "percentile": p,
                "expected_if_out_of_sample_matched_training": round(1.0 - p, 6),
                "refused_share": refused.height / max(marked.height, 1),
                "refused": rates(refused),
                "kept": rates(kept),
                "pairs": by_pair.height,
                "pairs_mostly_refused": int((by_pair["share"] > 0.5).sum()),
                "buy_calls": buys.height,
                "buy_refused_share": float(buys["_refused"].mean()) if buys.height else None,
                "buy_refused": rates(buys.filter(pl.col("_refused"))),
                "buy_kept": rates(buys.filter(~pl.col("_refused"))),
                "folds_refused_share": {
                    "min": None,
                    "median": None,
                    "max": None,
                },
            }
            per_fold = marked.group_by("fold_index").agg(pl.col("_refused").mean().alias("share"))["share"]
            entry["folds_refused_share"] = {
                "min": float(per_fold.min()),
                "median": float(per_fold.median()),
                "max": float(per_fold.max()),
            }
            if p in BY_YEAR_PERCENTILES:
                entry["by_year"] = {
                    str(year): {
                        "rows": group.height,
                        "refused_share": float(group["_refused"].mean()),
                        "refused": rates(group.filter(pl.col("_refused"))),
                        "kept": rates(group.filter(~pl.col("_refused"))),
                    }
                    for (year,), group in sorted(marked.group_by(["year"]), key=lambda item: item[0][0])
                }
            section.append(entry)
            sys.stdout.write(f"{gate} p={p}: refused {entry['refused_share']:.4f}\n")
            sys.stdout.flush()
        report[gate] = section

    joint = []
    both = joined.filter(pl.col("di").is_not_nan() & pl.col("anomaly_score").is_not_nan())
    for p_anomaly in JOINT:
        for p_di in JOINT:
            marked = with_threshold(both, "anomaly", p_anomaly).rename({"_refused": "_blocked"}).drop("_thr")
            marked = with_threshold(marked, "di", p_di)
            passing = marked.filter(~pl.col("_blocked") & ~pl.col("_refused"))
            buys = passing.filter(pl.col("is_buy"))
            joint.append(
                {
                    "anomaly_percentile": p_anomaly,
                    "di_percentile": p_di,
                    "rows": marked.height,
                    "anomaly_blocked_share": float(marked["_blocked"].mean()),
                    "di_refused_share": float(marked["_refused"].mean()),
                    "both_share": float((marked["_blocked"] & marked["_refused"]).mean()),
                    "passing_share": passing.height / max(marked.height, 1),
                    "passing": rates(passing),
                    "passing_buy_calls": rates(buys),
                }
            )
    report["joint"] = joint
    OUT_JSON.write_bytes(json.dumps(report, indent=1, sort_keys=True).encode("utf-8") + b"\n")
    sys.stdout.write(f"wrote {OUT_JSON}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
