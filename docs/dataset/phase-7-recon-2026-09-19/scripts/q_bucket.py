"""Read-only. A DECLARED spread table by liquidity bucket, read off the 2026 recording, applied to
every candidate by its own trailing-24h quote volume in the archive; then the funnel again with
per-candidate friction = fees + bucket spread + bucket slippage (at engine 9's $5,000 basis)."""
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

HERE = Path(__file__).parent
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
sys.stdout.reconfigure(encoding="utf-8")
g = {"__file__": str(HERE / "q_funnel.py"), "__name__": "head"}
exec(compile((HERE / "q_funnel.py").read_text(encoding="utf-8").split('print(f"window bars')[0], "head", "exec"), g)

# ---- the table, from the recording: per pair daily $ volume vs its median spread / slippage bound
m = pl.read_parquet(HERE / "spread_minutes.parquet", columns=["pair", "minute", "quote_volume"])
days = (m["minute"].max() - m["minute"].min()).total_seconds() / 86400
qv = m.group_by("pair").agg((pl.col("quote_volume").sum() / days).alias("usd_day"))
per = pl.read_parquet(HERE / "per_pair_spread_depth.parquet").join(qv, on="pair")
EDGES = [0, 1e4, 1e5, 1e6, 1e7, float("inf")]
LABELS = ["<$10k", "$10k-100k", "$100k-1M", "$1M-10M", ">$10M"]


def bucket(v):
    return pl.when(v < EDGES[1]).then(0).when(v < EDGES[2]).then(1).when(v < EDGES[3]).then(2).when(v < EDGES[4]).then(3).otherwise(4)


per = per.with_columns(bucket(pl.col("usd_day")).alias("b"))
table = per.group_by("b").agg(
    pl.len().alias("pairs"), pl.col("spread_med").median().alias("spread"),
    pl.col("spread_med").quantile(0.25).alias("s25"), pl.col("spread_med").quantile(0.75).alias("s75"),
    (pl.col("slip10k_ub_bps") * 0.25).median().alias("slip5k")).sort("b")
print(f"recording spans {days:.1f} days; declared table (median of per-pair medians, bps):")
for r in table.iter_rows(named=True):
    print(f"  {LABELS[r['b']]:>10}: {r['pairs']:>3} pairs  spread {r['spread']:.1f} (IQR {r['s25']:.1f}-{r['s75']:.1f})  slippage@$5k ~{(r['slip5k'] or float('nan')):.1f}")
spread_of = {r["b"]: r["spread"] / 1e4 for r in table.iter_rows(named=True)}
slip_of = {r["b"]: (r["slip5k"] or 0) / 1e4 for r in table.iter_rows(named=True)}

# ---- each archive pair's trailing 24h $ volume at every bar in the window
frames = []
for csv in sorted((REPO / "data/historical").glob("*USD_15.csv")):
    b = pl.read_csv(csv, has_header=False, new_columns=["ts", "o", "h", "l", "c", "v", "n"],
                    schema_overrides={"ts": pl.Int64, "c": pl.Float64, "v": pl.Float64})
    b = b.with_columns(pl.from_epoch("ts", time_unit="s").alias("t"), (pl.col("v") * pl.col("c")).alias("qv")).sort("t")
    r = b.rolling(index_column="t", period="24h").agg(pl.col("qv").sum().alias("usd_day"), pl.col("ts").last().alias("decision_ts"))
    frames.append(r.select(["decision_ts", "usd_day"]).with_columns(pl.lit(csv.name[:-7]).alias("pair")))
vol = pl.concat(frames)
FEES = [0.0060, 0.0050, 0.0040]
for rank in ("alphabetical", "log_return_4 asc"):
    c = g["CANDS"][rank].join(vol, on=["pair", "decision_ts"], how="left").with_columns(bucket(pl.col("usd_day").fill_null(0)).alias("b"))
    c = c.with_columns(pl.col("b").replace_strict(spread_of, default=spread_of[3]).alias("sp"), pl.col("b").replace_strict(slip_of, default=slip_of[3]).alias("sl"))
    print(f"\n{rank}: candidate buckets over 18m:", dict(zip(*[list(x) for x in zip(*c['b'].value_counts().sort('b').rows())])))
    for fee in FEES:
        for lo_name, lo in (("6m", g["TEST_START"][379]), ("12m", g["TEST_START"][353]), ("18m", g["TEST_START"][326])):
            cc = c.filter(pl.col("decision_ts") >= lo)
            stages = dict(bars=cc.height, an=0, di=0, cost=0, risk=0, sk=0)
            trades, open_until = [], {}
            for r in cc.iter_rows(named=True):
                a, d = r["anomaly_score"], r["sdi"]
                if a is None or not math.isfinite(a) or a > r["an_thr"]:
                    continue
                stages["an"] += 1
                if d is None or not math.isfinite(d) or d > r["di_thr"]:
                    continue
                stages["di"] += 1
                fr = fee + r["sp"] + r["sl"]
                if not r["expected_move_pct"] > 2.5 * fr:
                    continue
                stages["cost"] += 1
                open_until = {p: e for p, e in open_until.items() if e > r["decision_ts"]}
                if r["pair"] in open_until or len(open_until) >= 3:
                    continue
                stages["risk"] += 1
                if r["p_capped"] > 0.50:
                    continue
                stages["sk"] += 1
                open_until[r["pair"]] = r["label_window_end_ts"]
                trades.append((r["pair"], r["return_pct"] - fr, r["label"], r["b"]))
            n = len(trades)
            net = np.array([t[1] for t in trades]) if n else np.array([])
            hw = 1.96 * net.std(ddof=1) / math.sqrt(n) if n > 1 else float("nan")
            print(f"  fees {fee:.2%} {lo_name}: bars {stages['bars']} -> anomaly {stages['an']} -> DI {stages['di']} -> cost {stages['cost']} "
                  f"-> risk {stages['risk']} -> skeptic(capped .50) {n}"
                  + (f" | {len({t[0] for t in trades})} pairs, {sum(t[2] == 'target' for t in trades)} target, net {net.mean():+.2%} +/-{hw:.2%}" if n else ""))
