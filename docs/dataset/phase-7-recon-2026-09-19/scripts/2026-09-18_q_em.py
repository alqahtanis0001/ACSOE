"""How often does engine 8's out-of-sample expected move clear a given bar? Read-only."""

import polars as pl

path = r"C:\Users\saad2\Documents\GitHub\ACSOE\data\derived\oos_train-20260913T205245-067b2b9d.parquet"
df = pl.read_parquet(path, columns=["pair", "decision_ts", "expected_move_pct", "is_buy", "di_refused", "p_target"])
n = df.height
em = df["expected_move_pct"]
print("rows", n, "null expected_move", em.null_count())
valid = df.filter(pl.col("expected_move_pct").is_not_null())
print("rows with an expected move", valid.height)
print("expected_move max", valid["expected_move_pct"].max(), "p99", valid["expected_move_pct"].quantile(0.99),
      "p999", valid["expected_move_pct"].quantile(0.999), "median", valid["expected_move_pct"].median())
print("p_target max", valid["p_target"].max())
latest = valid.filter(pl.col("decision_ts") >= 1735689600)  # 2025 test weeks
print("2025 rows", latest.height)
for bar in (0.0125, 0.015, 0.0155, 0.01625, 0.0175, 0.02, 0.025, 0.03):
    all_n = valid.filter(pl.col("expected_move_pct") > bar).height
    no_di = valid.filter((pl.col("expected_move_pct") > bar) & (~pl.col("di_refused"))).height
    y25 = latest.filter(pl.col("expected_move_pct") > bar).height
    print(f"bar {bar*100:.3f}%: rows above {all_n} ({all_n/valid.height:.5%}), not DI-refused {no_di}, in 2025 {y25}")
