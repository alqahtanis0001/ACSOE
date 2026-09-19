"""Recorded spreads per pair from the recorder's minute summaries, 11-18 September. Read-only."""

import glob

import polars as pl

files = sorted(glob.glob(r"C:\Users\saad2\Documents\GitHub\ACSOE\data\summaries\summary*_2026-09-1*.jsonl"))
print("files", [f.rsplit("\\", 1)[-1] for f in files])
frames = []
for f in files:
    d = pl.read_ndjson(f, infer_schema_length=2000, ignore_errors=True)
    d = d.filter(pl.col("kind") == "summary").select(
        "pair", "minute",
        pl.col("spread_bps").list.get(0).alias("p25"),
        pl.col("spread_bps").list.get(1).alias("p50"),
        pl.col("depth_bid_bps"),
    )
    frames.append(d)
df = pl.concat(frames).unique(subset=["pair", "minute"], keep="first")
print("pair-minutes", df.height, "pairs", df["pair"].n_unique(),
      "minutes from", df["minute"].min(), "to", df["minute"].max())
usd = df.filter(pl.col("pair").str.ends_with("/USD"))
per = (
    usd.group_by("pair")
    .agg(pl.len().alias("minutes"), pl.col("p50").median().alias("spread_p50_bps"),
         pl.col("p25").median().alias("spread_p25_bps"), pl.col("depth_bid_bps").median().alias("depth10k_bps"))
    .sort("pair")
)
print("USD pairs", per.height)
print(per.head(12))
print(per.sort("spread_p50_bps").head(8))
# Tier 3 reference (invariant 5): maker 0.22%, taker 0.38%. Bar on the expected move is
# 2.5 x (fees + spread + slippage); slippage bounded above by depth10k, below by 0.
fees = 0.0022 + 0.0038
per = per.with_columns(
    (2.5 * (fees + pl.col("spread_p50_bps") / 10_000)).alias("bar_no_slip"),
    (2.5 * (fees + pl.col("spread_p50_bps") / 10_000 + pl.col("depth10k_bps").fill_null(0) / 10_000)).alias("bar_depth"),
)
print(per.select("pair", "spread_p50_bps", "bar_no_slip", "bar_depth").head(12))
print("USD pairs whose bar at zero slippage is below 3.0%:", per.filter(pl.col("bar_no_slip") < 0.03).height)
print("median bar_no_slip over USD pairs", per["bar_no_slip"].median())
