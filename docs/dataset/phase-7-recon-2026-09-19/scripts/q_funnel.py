"""Read-only. The chain's funnel, approximated offline from saved outputs, over a grid of declared
values, to answer: is there a defensible configuration that produces a shape rather than a point?

Per decision bar, in chain order:
  engine 7   candidate = first pair by the ranking (alphabetical, or scout.rank_feature ascending
             with pairs lacking the feature after, alphabetically - engine 7's rule)
  engine 13  refuses an incomplete anomaly vector, or a score above the fold's 0.99 threshold
  engine 8   refuses an incomplete DI vector or DI above the fold's 0.99 threshold
  engine 10  expected_move_pct > (1 + 1.5) x friction   (friction = fees + spread + slippage)
  engine 11  refuses when the pair already has an open position or 3 are open
  engine 15  vetoes when P(wrong) > threshold
  -> a trade, held until the label resolves (label_window_end_ts), return = return_pct - friction
NOT modelled: entry fill (post-only at the bid may not fill), engine 9 depth refusals, engine 16,
the ordermin/costmin rules, sizing, and the drawdown/loss-streak freezes of engine 17.
"""
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
RUN = "train-20260913T205245-067b2b9d"
STUDY = REPO / "data/derived" / f"di_anomaly_{RUN}"
FOLDS = list(range(326, 405))
TEST_START = {k: 1688169600 + (k - 326) * 604800 for k in FOLDS}
HI = 1735948800

oos = pl.read_parquet(REPO / "data/derived" / f"oos_{RUN}.parquet",
                      columns=["pair", "decision_ts", "label_window_end_ts", "fold_index", "expected_move_pct", "return_pct", "label"])
win = oos.filter((pl.col("decision_ts") >= TEST_START[326]) & (pl.col("decision_ts") < HI))
study, thr = [], []
for k in FOLDS:
    study.append(pl.read_parquet(STUDY / f"fold_{k:03d}.parquet"))
    thr.append((k, float(np.quantile(np.load(STUDY / f"excl_fold_{k:03d}.npz")["di_distribution"], 0.99)),
                float(np.quantile(np.load(STUDY / f"fold_{k:03d}.npz")["anomaly_train_scores"], 0.99))))
thr_df = pl.DataFrame(thr, schema=["fold_index", "di_thr", "an_thr"], orient="row").with_columns(pl.col("fold_index").cast(pl.Int32))
win = win.join(pl.concat(study).rename({"di": "sdi"}), on=["pair", "decision_ts", "fold_index"], how="left").join(thr_df, on="fold_index")
lr4 = (pl.scan_parquet(STUDY / "dataset_sorted_by_decision_ts.parquet")
       .filter((pl.col("decision_ts") >= TEST_START[326]) & (pl.col("decision_ts") < HI))
       .select(["pair", "decision_ts", "log_return_4"]).collect())
win = win.join(lr4, on=["pair", "decision_ts"], how="left")
sk = pl.concat([pl.read_parquet(HERE / "capped" / f"fold_{k:03d}.parquet") for k in FOLDS]).select(["pair", "decision_ts", "p_capped", "p_uncapped"])
win = win.join(sk, on=["pair", "decision_ts"], how="left")

alpha = win.sort(["decision_ts", "pair"]).group_by("decision_ts", maintain_order=True).first()
ranked = (win.with_columns(pl.col("log_return_4").is_nan().or_(pl.col("log_return_4").is_null()).alias("_nofeat"))
          .sort(["decision_ts", "_nofeat", "log_return_4", "pair"], nulls_last=True)
          .group_by("decision_ts", maintain_order=True).first())
CANDS = {"alphabetical": alpha, "log_return_4 asc": ranked}


def simulate(c: pl.DataFrame, friction: float, variant: str, veto: float, lo: int):
    c = c.filter(pl.col("decision_ts") >= lo)
    bar = 2.5 * friction
    stages = dict(bars=c.height, anomaly=0, di=0, cost=0, risk=0, skeptic=0)
    trades, open_until = [], {}
    for r in c.iter_rows(named=True):
        an, di = r["anomaly_score"], r["sdi"]
        if an is None or not math.isfinite(an) or an > r["an_thr"]:
            continue
        stages["anomaly"] += 1
        if di is None or not math.isfinite(di) or di > r["di_thr"]:
            continue
        stages["di"] += 1
        if not r["expected_move_pct"] > bar:
            continue
        stages["cost"] += 1
        ts = r["decision_ts"]
        live = {p: e for p, e in open_until.items() if e > ts}
        open_until = live
        if r["pair"] in live or len(live) >= 3:
            continue
        stages["risk"] += 1
        p = r["p_capped" if variant == "capped" else "p_uncapped"]
        assert p is not None, r
        if p > veto:
            continue
        stages["skeptic"] += 1
        open_until[r["pair"]] = r["label_window_end_ts"]
        trades.append((ts, r["pair"], r["return_pct"] - friction, r["label"]))
    return stages, trades


def fmt(trades):
    n = len(trades)
    if n == 0:
        return "trades 0"
    net = np.array([t[2] for t in trades])
    hw = 1.96 * net.std(ddof=1) / math.sqrt(n) if n > 1 else float("nan")
    wins = sum(t[3] == "target" for t in trades)
    pairs = len({t[1] for t in trades})
    return f"trades {n:>3} ({pairs} pairs, {wins} target) net {net.mean():+.2%} +/-{hw:.2%}"


print(f"window bars {alpha.height}; candidate pairs, alphabetical: {alpha['pair'].n_unique()}, "
      f"log_return_4 asc: {ranked['pair'].n_unique()}")
for months, lo in (("18m (79 folds)", TEST_START[326]), ("12m (52 folds)", TEST_START[353]), ("6m (26 folds)", TEST_START[379])):
    print(f"\n=== {months} ===")
    for rank, c in CANDS.items():
        for friction in (0.0040, 0.0050, 0.0060, 0.0070, 0.0085):
            parts = []
            for variant in ("uncapped", "capped"):
                for veto in (0.50, 0.60, 0.70):
                    stages, trades = simulate(c, friction, variant, veto, lo)
                    parts.append(f"{variant[:3]}@{veto:.2f}: {fmt(trades)}")
            s = stages
            print(f"{rank:<17} friction {friction:.2%} | bars {s['bars']} -> anomaly {s['anomaly']} -> DI {s['di']} -> cost {s['cost']} -> risk {s['risk']}")
            for p in parts:
                print("      " + p)
