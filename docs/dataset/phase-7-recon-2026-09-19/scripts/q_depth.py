"""Read-only. Per recorded USD pair: median spread and median bid depth distance at $10,000,
and from them an upper bound on engine 9's slippage (measured from the best bid) for any
notional up to $10,000: depth_bid_bps(10k) - spread_bps/2. Also which archive pairs are covered.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import orjson
import polars as pl

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
rows = defaultdict(list)
for path in sorted((REPO / "data/summaries").glob("summary*.jsonl")):
    with path.open("rb") as fh:
        for line in fh:
            try:
                d = orjson.loads(line)
            except orjson.JSONDecodeError:
                continue
            if d.get("kind") != "summary" or not str(d.get("pair", "")).endswith("/USD"):
                continue
            if d.get("v") != 2 or not d.get("clean") or d.get("samples", 0) <= 0:
                continue
            rows["pair"].append(d["pair"])
            rows["p50"].append(d["spread_bps"][1])
            rows["depth_bid"].append(d.get("depth_bid_bps"))
            rows["depth_samples"].append(d.get("depth_samples", 0))
            rows["qv"].append(d.get("quote_volume") or 0.0)
df = pl.DataFrame(rows, schema_overrides={"p50": pl.Float64, "depth_bid": pl.Float64, "qv": pl.Float64})
per = df.group_by("pair").agg(
    pl.col("p50").median().alias("spread_med"),
    pl.col("p50").quantile(0.9).alias("spread_p90"),
    pl.col("depth_bid").filter(pl.col("depth_samples") > 0).median().alias("depth10k_med"),
    (pl.col("depth_samples") > 0).mean().alias("depth_reached_share"),
    pl.col("qv").sum().alias("qv_total"),
    pl.len().alias("minutes"),
).with_columns((pl.col("depth10k_med") - pl.col("spread_med") / 2).alias("slip10k_ub_bps"))
per.write_parquet(Path(__file__).parent / "per_pair_spread_depth.parquet")

manifest = json.loads((REPO / "models/train-20260913T205245-067b2b9d-f404/manifest.json").read_bytes())
norm = {"XBT": "BTC", "XDG": "DOGE"}
arch = {f"{norm.get(p[:-3], p[:-3])}/USD": p for p in manifest["dataset"]["pairs"] if p.endswith("USD")}


def q(series, qs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    s = series.drop_nulls()
    return ", ".join(f"p{int(x * 100)} {s.quantile(x):.1f}" for x in qs) + f"  (n {s.len()})"


for label, frame in (("all recorded", per), ("recorded AND in archive", per.filter(pl.col("pair").is_in(list(arch))))):
    print(f"\n{label}: {frame.height} pairs")
    print("  median spread bps          ", q(frame["spread_med"]))
    print("  depth-to-$10k bps (median) ", q(frame["depth10k_med"]))
    print("  share of minutes the 10-level book reached $10k:", q(frame["depth_reached_share"] * 100))
    print("  slippage UB at <=$10k, bps ", q(frame["slip10k_ub_bps"]))
for p in ("AAVE/USD", "ADA/USD", "BTC/USD", "ETH/USD", "SOL/USD"):
    r = per.filter(pl.col("pair") == p)
    if r.height:
        r = r.row(0, named=True)
        print(f"  {p}: spread {r['spread_med']:.2f}, depth10k {r['depth10k_med']}, reached {r['depth_reached_share']:.0%}, slipUB {r['slip10k_ub_bps']}")
