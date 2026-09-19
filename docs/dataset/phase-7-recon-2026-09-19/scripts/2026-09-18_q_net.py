"""Arithmetic only, no chain: rows that clear the tier-3 cost bar, and their realised outcome net.

Tier 3 at invariant 5's reference fees (maker 0.22% + taker 0.38% = 0.60%). Spread s is a stated
assumption per line. Bar on the expected move: 2.5 x (0.60% + s). Net per trade: realised barrier
return minus (0.60% + s). NOT the chain: no fill model, no one-position rule, no skeptic, anomaly
or incomplete-feature refusals, no slippage. Read-only.
"""

import math

import polars as pl

path = r"C:\Users\saad2\Documents\GitHub\ACSOE\data\derived\oos_train-20260913T205245-067b2b9d.parquet"
df = pl.read_parquet(path, columns=["pair", "decision_ts", "expected_move_pct", "return_pct"])
print("return_pct sample", df["return_pct"].head(3).to_list(), "nulls", df["return_pct"].null_count())
year_start = df["decision_ts"].max() - 365 * 86400
alpha = df.sort(["decision_ts", "pair"]).group_by("decision_ts", maintain_order=True).first()

fees = 0.0060
for label, frame in (("all years, alphabetical candidate", alpha),
                     ("2024, alphabetical candidate", alpha.filter(pl.col("decision_ts") > year_start))):
    for s_bps in (0, 5, 10, 25):
        friction = fees + s_bps / 10_000
        hit = frame.filter(pl.col("expected_move_pct") > 2.5 * friction)
        n = hit.height
        if n == 0:
            print(f"{label}, spread {s_bps} bps: 0 clear")
            continue
        net = hit["return_pct"] - friction
        mean, sd = net.mean(), net.std()
        se = sd / math.sqrt(n) if n > 1 else float("nan")
        print(f"{label}, spread {s_bps} bps: {n} clear; realised {hit['return_pct'].mean():+.3%}; "
              f"net {mean:+.3%} per trade, sd {sd:.3%}, se {se:.3%}, 95% ci [{mean-1.96*se:+.3%}, {mean+1.96*se:+.3%}]")
