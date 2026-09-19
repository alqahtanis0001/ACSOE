"""Phase 7 scoping, questions 1-3 and 5. Read-only: reads manifests, the OOS parquet, the Phase 5
DI/anomaly study outputs and the dataset; writes nothing but stdout.

The bound reproduces the method of the 2026-09-18 answer (session 2027b2be, q_year.py / q_net.py):
per decision bar, the alphabetical candidate is the first pair by name among the OOS rows at that
bar; it clears the cost gate when expected_move_pct > (1 + hurdle_multiple) x friction, with
friction = round-trip fees + spread. Tier 3 fees are invariant 5's REFERENCE figures
(0.22% + 0.38% = 0.60%), sanity-check values the invariant says are never for code.
"""
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
RUN = "train-20260913T205245-067b2b9d"
OOS = REPO / "data/derived" / f"oos_{RUN}.parquet"
STUDY = REPO / "data/derived" / f"di_anomaly_{RUN}"
DATASET = REPO / "data/derived/dataset_20260913T205245.parquet"
HURDLE = 1.5
TIER3_FEES = 0.0022 + 0.0038
VETO = 0.50
PCT = 0.99


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M")


# ---- Q1/Q2: fold windows from the manifests
folds = {}
for k in range(405):
    m = json.loads((REPO / "models" / f"{RUN}-f{k}" / "manifest.json").read_bytes())
    folds[k] = m["fold"]
f404 = folds[404]
print(f"Q1 fold 404 test window: {iso(f404['test_start_ts'])} to {iso(f404['test_end_ts'])} (end exclusive), "
      f"test_rows {f404['test_rows']}, train {iso(f404['train_start_ts'])} to {iso(f404['train_end_ts'])}")
end = f404["test_end_ts"]
start_target = end - int(1.5 * 365.25 * 86400)
containing = [k for k, f in folds.items() if f["test_start_ts"] <= start_target < f["test_end_ts"]]
print(f"Q2 1.5 years (547.875 days) before fold 404's test end is {iso(start_target)}; "
      f"fold containing it: {containing}")
steps = sorted({folds[k + 1]["test_start_ts"] - folds[k]["test_start_ts"] for k in range(404)})
print(f"   fold-to-fold test_start steps (s): {steps[:5]}{'...' if len(steps) > 5 else ''}")
for k in (325, 326, 327, 328):
    f = folds[k]
    print(f"   fold {k}: test {iso(f['test_start_ts'])} to {iso(f['test_end_ts'])}, test_rows {f['test_rows']}")
first = containing[0]
span = list(range(first, 405))
lo, hi = folds[first]["test_start_ts"], end
print(f"   span used below: folds {first}-404 ({len(span)} folds), {iso(lo)} to {iso(hi)} "
      f"({(hi - lo) / 86400:.1f} days)")

# ---- Q3
oos = pl.read_parquet(OOS, columns=["pair", "decision_ts", "label_window_end_ts", "fold_index",
                                     "expected_move_pct", "p_target", "p_stop", "p_timeout",
                                     "return_pct", "label", "weight"])
win = oos.filter((pl.col("decision_ts") >= lo) & (pl.col("decision_ts") < hi))
per_bar = win.group_by("decision_ts").agg(pl.len().alias("n"))
print(f"Q3 folds in span {win['fold_index'].n_unique()} ({win['fold_index'].min()}-{win['fold_index'].max()}); "
      f"OOS rows {win.height}; decision bars with >=1 row {per_bar.height}; calendar 15m bars "
      f"{(hi - lo) // 900}; pairs per bar mean {per_bar['n'].mean():.1f} median {per_bar['n'].median():.0f} "
      f"max {per_bar['n'].max()} min {per_bar['n'].min()}; distinct pairs {win['pair'].n_unique()}")
for y0, y1, lab in ((lo, 1704067200, "2023 part"), (1704067200, hi, "2024+")):
    pb = win.filter((pl.col("decision_ts") >= y0) & (pl.col("decision_ts") < y1)).group_by("decision_ts").agg(pl.len().alias("n"))
    print(f"   {lab}: bars {pb.height}, pairs/bar mean {pb['n'].mean():.1f} max {pb['n'].max()}")

# ---- study outputs: completeness, DI, anomaly per row, thresholds per fold
study_rows, thresholds = [], {}
for k in span:
    study_rows.append(pl.read_parquet(STUDY / f"fold_{k:03d}.parquet"))
    di_dist = np.load(STUDY / f"excl_fold_{k:03d}.npz")["di_distribution"]
    an = np.load(STUDY / f"fold_{k:03d}.npz")["anomaly_train_scores"]
    thresholds[k] = (float(np.quantile(di_dist, PCT)), float(np.quantile(an, PCT)))
study = pl.concat(study_rows).rename({"di": "study_di"})
thr = pl.DataFrame({"fold_index": list(thresholds), "di_thr": [v[0] for v in thresholds.values()],
                    "an_thr": [v[1] for v in thresholds.values()]}).with_columns(pl.col("fold_index").cast(pl.Int32))
win = win.join(study, on=["pair", "decision_ts", "fold_index"], how="left").join(thr, on="fold_index", how="left")
print(f"   study join: {win['study_di'].is_not_null().sum()} rows joined; finite DI (complete vector) {(win['study_di'].is_finite()).sum()}; finite anomaly {(win['anomaly_score'].is_finite()).sum()} of {win.height}")

# ---- the alphabetical candidate per bar (the 2026-09-18 definition)
def alphabetical(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.sort(["decision_ts", "pair"]).group_by("decision_ts", maintain_order=True).first()


cand = alphabetical(win)
top = cand["pair"].value_counts().sort("count", descending=True).head(6)
print("   alphabetical candidate pairs (top 6):", [(r[0], r[1]) for r in top.iter_rows()])

# reproduce the 71
year_start = oos["decision_ts"].max() - 365 * 86400
yr = alphabetical(oos.filter(pl.col("decision_ts") > year_start))
print(f"CHECK 2024 reproduction: {yr.filter(pl.col('expected_move_pct') > (1 + HURDLE) * TIER3_FEES).height} "
      f"(the 2026-09-18 figure was 71)")


def stats(frame: pl.DataFrame, friction: float) -> str:
    n = frame.height
    if n == 0:
        return "n 0"
    net = frame["return_pct"] - friction
    mean = float(net.mean())
    sd = float(net.std()) if n > 1 else float("nan")
    se = sd / math.sqrt(n) if n > 1 else float("nan")
    return (f"n {n}; realised {float(frame['return_pct'].mean()):+.3%}; net {mean:+.3%}/trade sd {sd:.3%} "
            f"95% CI [{mean - 1.96 * se:+.3%}, {mean + 1.96 * se:+.3%}]; half-width {1.96 * se:.3%}")


def one_position_per_pair(frame: pl.DataFrame) -> pl.DataFrame:
    """Keep a candidate only if no earlier kept trade on the same pair is still open."""
    open_until: dict[str, int] = {}
    keep = []
    for pair, ts, end_ts in frame.select(["pair", "decision_ts", "label_window_end_ts"]).iter_rows():
        if open_until.get(pair, -1) > ts:
            keep.append(False)
            continue
        keep.append(True)
        open_until[pair] = end_ts
    return frame.filter(pl.Series(keep, dtype=pl.Boolean))


print("\nQ5 UPPER BOUND, alphabetical candidate, folds", f"{first}-404")
print("   (a) bars clearing = the 2026-09-18 bound; (b) + one open position per pair, using each "
      "label's own resolution time")
for s_bps in (0, 10, 25):
    fr = TIER3_FEES + s_bps / 10_000
    hit = cand.filter(pl.col("expected_move_pct") > (1 + HURDLE) * fr)
    hit_b = one_position_per_pair(hit)
    print(f"   tier 3 ref fees, spread {s_bps:>2} bps: friction {fr:.2%}, bar {(1 + HURDLE) * fr:.3%} | "
          f"(a) {hit.height} | (b) {hit_b.height}\n      (a) {stats(hit, fr)}\n      (b) {stats(hit_b, fr)}")

print("\n   The bound depends on friction alone. Count (a) by total round-trip friction "
      "(fees + spread), for reading off any tier's figure once one is sourced:")
line = []
for f_bp in range(20, 125, 5):
    fr = f_bp / 10_000
    line.append(f"{f_bp / 100:.2f}%:{cand.filter(pl.col('expected_move_pct') > (1 + HURDLE) * fr).height}")
print("   " + "  ".join(line))
print(f"   max expected_move_pct over the span, any pair {win['expected_move_pct'].max():.4%}; "
      f"alphabetical candidate {cand['expected_move_pct'].max():.4%}")

# ---- stricter, still offline: gates that can be applied from existing outputs
print("\nQ5 STRICTER (still not the chain): tier 3 ref fees, each gate added in chain order")
names = tuple(json.loads((REPO / "models" / f"{RUN}-f404" / "manifest.json").read_bytes())["feature_names"])
for s_bps in (0, 10, 25):
    fr = TIER3_FEES + s_bps / 10_000
    hit = cand.filter(pl.col("expected_move_pct") > (1 + HURDLE) * fr)
    complete = hit.filter(pl.col("study_di").is_not_null() & pl.col("study_di").is_finite())
    anomaly_ok = complete.filter(pl.col("anomaly_score").is_not_null() & pl.col("anomaly_score").is_finite() & (pl.col("anomaly_score") <= pl.col("an_thr")))
    di_ok = anomaly_ok.filter(pl.col("study_di") <= pl.col("di_thr"))
    # skeptic (uncapped, as trained) on the survivors
    if di_ok.height:
        keys = di_ok.select(["pair", "decision_ts"])
        feats = (pl.scan_parquet(DATASET).select(["pair", "decision_ts", *names])
                 .join(keys.lazy(), on=["pair", "decision_ts"], how="inner").collect())
        rows = di_ok.join(feats, on=["pair", "decision_ts"], how="inner")
        assert rows.height == di_ok.height, (rows.height, di_ok.height)
        p_wrong = np.empty(rows.height)
        from acsoe.modelling.artefacts import load_run
        from acsoe.modelling.features import FEATURE_VERSION
        from acsoe.research import training
        for k in sorted(set(rows["fold_index"].to_list())):
            sel = (rows["fold_index"] == k).to_numpy()
            d = REPO / "models" / f"{RUN}-f{k}"
            run = load_run(d, expected_features=names, expected_version=FEATURE_VERSION)
            booster = lgb.Booster(model_file=str(d / "skeptic.txt"))
            p_wrong[sel] = booster.predict(training._skeptic_matrix(rows.filter(pl.Series(sel)), run.scaler, names))
        sk_ok = rows.filter(pl.Series(p_wrong <= VETO))
    else:
        sk_ok = di_ok
    final = one_position_per_pair(sk_ok)
    print(f"   spread {s_bps:>2} bps: clear {hit.height} -> complete vector {complete.height} -> anomaly "
          f"{anomaly_ok.height} -> DI {di_ok.height} -> skeptic(uncapped) {sk_ok.height} -> one-per-pair "
          f"{final.height} | {stats(final, fr)}")
