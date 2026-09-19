"""OOS shape for a cost estimate, and a fee-only upper bound on tier-3 trades. Read-only.

Tier 3 at invariant 5's reference fees (0.22% + 0.38% = 0.60%), zero spread, zero
slippage: the bar on the expected move is 2.5 x 0.60% = 1.50%. Zero spread is the
OPTIMISTIC direction, so every count here is an upper bound, never an estimate.
"""

import polars as pl

path = r"C:\Users\saad2\Documents\GitHub\ACSOE\data\derived\oos_train-20260913T205245-067b2b9d.parquet"
df = pl.read_parquet(path, columns=["pair", "decision_ts", "expected_move_pct", "fold_index"])
bars = df["decision_ts"].n_unique()
per_bar = df.group_by("decision_ts").agg(pl.len().alias("n"))
print("rows", df.height, "decision bars", bars, "folds", df["fold_index"].n_unique())
print("pairs per bar: mean", round(per_bar["n"].mean(), 1), "max", per_bar["n"].max())
print("span", df["decision_ts"].min(), df["decision_ts"].max())

bar = 0.015
any_pair = df.filter(pl.col("expected_move_pct") > bar)["decision_ts"].n_unique()
print(f"bars where ANY pair clears {bar:.3%} (best-case ranking):", any_pair)

first = df.sort(["decision_ts", "pair"]).group_by("decision_ts", maintain_order=True).first()
alpha = first.filter(pl.col("expected_move_pct") > bar).height
print(f"bars where the alphabetically first pair clears {bar:.3%} (engine 7 today):", alpha)
