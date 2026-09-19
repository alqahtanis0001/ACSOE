"""The last 365 days of the out-of-sample file: folds, bars, pairs, and the fee-only bound. Read-only."""

from datetime import UTC, datetime

import polars as pl

path = r"C:\Users\saad2\Documents\GitHub\ACSOE\data\derived\oos_train-20260913T205245-067b2b9d.parquet"
df = pl.read_parquet(path, columns=["pair", "decision_ts", "expected_move_pct", "fold_index", "return_pct"])
end = df["decision_ts"].max()
start = end - 365 * 86400
year = df.filter(pl.col("decision_ts") > start)
print("window", datetime.fromtimestamp(start, UTC), "to", datetime.fromtimestamp(end, UTC))
print("folds", year["fold_index"].n_unique(), "min fold", year["fold_index"].min(), "max fold", year["fold_index"].max())
print("rows", year.height, "decision bars", year["decision_ts"].n_unique())
per_bar = year.group_by("decision_ts").agg(pl.len().alias("n"))
print("pairs per bar: mean", round(per_bar["n"].mean(), 1), "max", per_bar["n"].max(), "distinct pairs", year["pair"].n_unique())
bar = 0.015
first = year.sort(["decision_ts", "pair"]).group_by("decision_ts", maintain_order=True).first()
print("alphabetical-candidate bars clearing 1.5% (tier 3, zero spread, upper bound):",
      first.filter(pl.col("expected_move_pct") > bar).height)
print("any-pair bars clearing 1.5%:", year.filter(pl.col("expected_move_pct") > bar)["decision_ts"].n_unique())
