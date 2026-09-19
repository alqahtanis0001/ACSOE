"""Read-only. What ranking the universe by engine 8's output buys, against log_return_4, under the
same declared bucket spread + slippage and the capped skeptic at 0.50. Ranking needs every pair
scored, so the anomaly and DI refusals apply to every pair BEFORE the choice:
  expected_move : the pair with the highest expected_move_pct among those anomaly and DI pass
  net_margin    : the highest expected_move_pct - 2.5 x its own friction (what engine 10 tests)
"""
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8")
g = {"__file__": str(HERE / "q_bucket.py"), "__name__": "head"}
exec(compile((HERE / "q_bucket.py").read_text(encoding="utf-8").split("FEES = [")[0], "head", "exec"), g)
f, pl_ = g, pl
win = f["g"]["win"].join(f["vol"], on=["pair", "decision_ts"], how="left").with_columns(
    f["bucket"](pl.col("usd_day").fill_null(0)).alias("b"))
win = win.with_columns(pl.col("b").replace_strict(f["spread_of"], default=f["spread_of"][3]).alias("sp"),
                       pl.col("b").replace_strict(f["slip_of"], default=f["slip_of"][3]).alias("sl"))
ok = win.filter(pl.col("anomaly_score").is_finite() & (pl.col("anomaly_score") <= pl.col("an_thr"))
                & pl.col("sdi").is_finite() & (pl.col("sdi") <= pl.col("di_thr")))
TS = f["g"]["TEST_START"]
for fee in (0.0060, 0.0050, 0.0040):
    scored = ok.with_columns((pl.col("expected_move_pct") - 2.5 * (fee + pl.col("sp") + pl.col("sl"))).alias("margin"))
    for rank, key in (("expected_move", "expected_move_pct"), ("net_margin", "margin")):
        c = scored.sort(["decision_ts", key, "pair"], descending=[False, True, False]).group_by("decision_ts", maintain_order=True).first()
        for lo_name, lo in (("6m", TS[379]), ("12m", TS[353])):
            cc = c.filter(pl.col("decision_ts") >= lo)
            trades, open_until, cost = [], {}, 0
            for r in cc.iter_rows(named=True):
                fr = fee + r["sp"] + r["sl"]
                if not r["expected_move_pct"] > 2.5 * fr:
                    continue
                cost += 1
                open_until = {p: e for p, e in open_until.items() if e > r["decision_ts"]}
                if r["pair"] in open_until or len(open_until) >= 3 or r["p_capped"] is None or r["p_capped"] > 0.50:
                    continue
                open_until[r["pair"]] = r["label_window_end_ts"]
                trades.append((r["pair"], r["return_pct"] - fr, r["label"]))
            n = len(trades)
            net = np.array([t[1] for t in trades]) if n else np.array([])
            hw = 1.96 * net.std(ddof=1) / math.sqrt(n) if n > 1 else float("nan")
            print(f"fees {fee:.2%} {rank:<13} {lo_name:>3}: clear cost {cost:>5} -> trades {n:>3}"
                  + (f" ({len({t[0] for t in trades})} pairs, {sum(t[2] == 'target' for t in trades)} target) net {net.mean():+.2%} +/-{hw:.2%}" if n else ""))
