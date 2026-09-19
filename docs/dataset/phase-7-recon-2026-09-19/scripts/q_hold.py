"""Q5/Q8 supplement, read-only: one-position-per-pair counts and holding minutes by friction."""
import math
import sys
from pathlib import Path

import polars as pl

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
OOS = REPO / "data/derived/oos_train-20260913T205245-067b2b9d.parquet"
LO, HI = 1688169600, 1735948800  # fold 326 test start .. fold 404 test end
oos = pl.read_parquet(OOS, columns=["pair", "decision_ts", "label_window_end_ts", "expected_move_pct", "return_pct"])
win = oos.filter((pl.col("decision_ts") >= LO) & (pl.col("decision_ts") < HI))
cand = win.sort(["decision_ts", "pair"]).group_by("decision_ts", maintain_order=True).first()


def one_per_pair(frame):
    open_until, keep = {}, []
    for pair, ts, end in frame.select(["pair", "decision_ts", "label_window_end_ts"]).iter_rows():
        ok = open_until.get(pair, -1) <= ts
        keep.append(ok)
        if ok:
            open_until[pair] = end
    return frame.filter(pl.Series(keep, dtype=pl.Boolean))


for f_bp in (30, 35, 40, 45, 50, 55, 60, 70, 85):
    fr = f_bp / 10_000
    hit = one_per_pair(cand.filter(pl.col("expected_move_pct") > 2.5 * fr))
    if hit.height == 0:
        print(f"friction {fr:.2%}: 0")
        continue
    mins = ((hit["label_window_end_ts"] - hit["decision_ts"]) / 60)
    net = hit["return_pct"] - fr
    se = float(net.std()) / math.sqrt(hit.height) if hit.height > 1 else float("nan")
    print(f"friction {fr:.2%}: trades {hit.height:>4}; hold minutes mean {mins.mean():.0f} max {mins.max():.0f} "
          f"total {mins.sum():.0f}; net {float(net.mean()):+.3%} +/- {1.96 * se:.3%} (95% half-width)")
