"""Q6 step 3, read-only. Are the window's candidate pairs in the recording, and do their 2023-25
archive predictors fall inside the range the 2026 fit saw? Also: the model's backcast spread for
them, and what the fit's own error band does to the cost gate's count."""
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
rec = pl.read_parquet(HERE / "spread_bars.parquet")
X = ["lqv16", "ltr16", "lrv16", "lrng", "lpx"]
recorded = set(rec["pair"].unique().to_list())
norm = {"XBT": "BTC", "XDG": "DOGE"}


def to_slash(archive: str) -> str:
    base = archive[:-3]
    return f"{norm.get(base, base)}/USD"


manifest_pairs = __import__("json").loads((REPO / "models/train-20260913T205245-067b2b9d-f404/manifest.json").read_bytes())["dataset"]["pairs"]
arch = {p: to_slash(p) for p in manifest_pairs if p.endswith("USD")}
overlap = sorted(a for a, s in arch.items() if s in recorded)
print(f"archive USD pairs {len(arch)}; recorded USD pairs {len(recorded)}; in both {len(overlap)}")
beta = np.linalg.lstsq(np.hstack([np.ones((rec.height, 1)), rec.select(X).to_numpy()]), rec["spread_bps"].log().to_numpy(), rcond=None)[0]
sd = 0.61  # per-pair mean error sd, from the pair-split checks (0.58-0.73)
LO, HI = 1704067200 - 184 * 86400, 1735948800  # 2023-07-01 .. 2025-01-04
for pair in ("1INCHUSD", "AAVEUSD", "ADAUSD", "ACHUSD", "ACAUSD"):
    csv = REPO / "data/historical" / f"{pair}_15.csv"
    b = pl.read_csv(csv, has_header=False, new_columns=["ts", "open", "high", "low", "close", "volume", "trades"])
    b = b.with_columns(pl.from_epoch("ts", time_unit="s").dt.replace_time_zone("UTC").alias("bar")).sort("bar")
    b = b.with_columns((pl.col("volume") * pl.col("close")).alias("qv"), pl.col("close").log().diff().alias("r"))
    f = b.rolling(index_column="bar", period="4h").agg(pl.col("qv").sum().alias("qv16"), pl.col("trades").sum().alias("tr16"), pl.col("r").std().alias("rv16"))
    b = b.join(f, on="bar").filter((pl.col("ts") >= LO) & (pl.col("ts") < HI) & (pl.col("high") > pl.col("low")) & (pl.col("rv16") > 0))
    b = b.with_columns(pl.col("qv16").log().alias("lqv16"), (pl.col("tr16") + 1).log().alias("ltr16"), pl.col("rv16").log().alias("lrv16"),
                       ((pl.col("high") - pl.col("low")) / pl.col("close")).log().alias("lrng"), pl.col("close").log().alias("lpx"))
    pred = np.exp(np.hstack([np.ones((b.height, 1)), b.select(X).to_numpy()]) @ beta)
    outside = {c: float(((b[c] < rec[c].quantile(0.01)) | (b[c] > rec[c].quantile(0.99))).mean()) for c in X}
    s = to_slash(pair)
    measured = rec.filter(pl.col("pair") == s)["spread_bps"]
    print(f"{pair}: recorded? {s in recorded}"
          + (f" (2026 measured median {measured.median():.1f} bps)" if measured.len() else "")
          + f" | window bars {b.height} | backcast median {np.median(pred):.1f} bps, 95% band for the pair's level "
          f"{np.median(pred) * np.exp(-1.96 * sd):.1f}-{np.median(pred) * np.exp(1.96 * sd):.1f} bps | share of window bars "
          "outside the 2026 fit's 1-99% range: " + ", ".join(f"{c} {v:.0%}" for c, v in outside.items()))
