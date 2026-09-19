import runpy, sys
from pathlib import Path
sys.argv = ["x"]
HERE = Path(r"C:\Users\saad2\AppData\Local\Temp\claude\C--Users-saad2-Documents-GitHub-ACSOE\68f2f338-890a-4482-a92d-71cf33e31012\scratchpad")
src = (HERE / "q_funnel.py").read_text(encoding="utf-8").split('print(f"window bars')[0]
g = {"__file__": str(HERE / "q_funnel.py"), "__name__": "q_funnel_head"}
exec(compile(src, "q_funnel_head", "exec"), g)
import polars as pl
per = pl.read_parquet(HERE / "per_pair_spread_depth.parquet")
norm = {"XBT": "BTC", "XDG": "DOGE"}
for fr in (0.0060, 0.0070):
    for lo_name, lo in (("12m", g["TEST_START"][353]), ("18m", g["TEST_START"][326])):
        st, trades = g["simulate"](g["CANDS"]["log_return_4 asc"], fr, "capped", 0.50, lo)
        t = pl.DataFrame(trades, schema=["ts", "pair", "net", "label"], orient="row").with_columns(
            pl.col("pair").map_elements(lambda p: f"{norm.get(p[:-3], p[:-3])}/USD", return_dtype=pl.Utf8).alias("slash"))
        j = t.join(per.select(["pair", "spread_med", "slip10k_ub_bps"]).rename({"pair": "slash"}), on="slash", how="left")
        rec = j.filter(pl.col("spread_med").is_not_null())
        print(f"friction {fr:.2%} {lo_name}: trades {t.height}, of which on a recorded pair {rec.height}; "
              f"recorded spread of those: median {rec['spread_med'].median()}, p75 {rec['spread_med'].quantile(0.75)}, max {rec['spread_med'].max()}; "
              f"net on recorded {rec['net'].mean() if rec.height else None}, unrecorded {j.filter(pl.col('spread_med').is_null())['net'].mean()}")
        print("   top pairs:", t["pair"].value_counts().sort("count", descending=True).head(8).rows())
