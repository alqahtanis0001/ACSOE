"""Phase 7 scoping, Q6 step 2. Read-only. Can the recorded spread be predicted from what the
OHLCVT archive carries, well enough to apply backwards over 2023-07..2025-01?

Target: log of the 15-minute spread, the median of the minute p50s (minutes with samples > 0).
Predictors, each computable identically from an archive 15m bar series (volume, trades, OHLC):
  lqv16  log quote volume (sum over the trailing 16 bars of volume x bar close)
  ltr16  log(1 + trades over the trailing 16 bars)
  lrv16  log std of 15m log close-to-close returns over the trailing 16 bars
  lrng   log((high - low) / close) of the bar itself
  lpx    log close (a stand-in for tick size, which the archive does not carry)
Only bars with at least one trade: the archive has no row otherwise, so no candidate is born there.
"""
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
m = pl.read_parquet(HERE / "spread_minutes.parquet")

bars = (
    m.with_columns(pl.col("minute").dt.truncate("15m").alias("bar"))
    .sort(["pair", "minute"])
    .group_by(["pair", "bar"], maintain_order=True)
    .agg(
        pl.col("p50").filter(pl.col("samples") > 0).median().alias("spread_bps"),
        pl.col("samples").sum().alias("samples"),
        pl.col("trades").sum().alias("trades"),
        pl.col("volume").sum().alias("volume"),
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").drop_nulls().last().alias("close"),
        pl.len().alias("minutes"),
    )
)
bars = bars.with_columns((pl.col("volume") * pl.col("close")).alias("qv"))
# trailing 16-bar windows on the regular grid (holes are bars with no trade: qv 0, no close)
feat = (
    bars.sort(["pair", "bar"])
    .with_columns(
        pl.col("close").log().diff().over("pair").alias("r"),
    )
    .rolling(index_column="bar", period="4h", group_by="pair")
    .agg(
        pl.col("qv").sum().alias("qv16"),
        pl.col("trades").sum().alias("tr16"),
        pl.col("r").std().alias("rv16"),
        pl.len().alias("n16"),
    )
)
df = bars.join(feat, on=["pair", "bar"], how="left").filter(
    (pl.col("trades") > 0) & (pl.col("spread_bps") > 0) & pl.col("close").is_not_null()
    & (pl.col("high") > pl.col("low")) & (pl.col("rv16") > 0) & (pl.col("qv16") > 0)
)
df = df.with_columns(
    pl.col("spread_bps").log().alias("y"),
    pl.col("qv16").log().alias("lqv16"),
    (pl.col("tr16") + 1).log().alias("ltr16"),
    pl.col("rv16").log().alias("lrv16"),
    ((pl.col("high") - pl.col("low")) / pl.col("close")).log().alias("lrng"),
    pl.col("close").log().alias("lpx"),
)
X_COLS = ["lqv16", "ltr16", "lrv16", "lrng", "lpx"]
first_bar = df["bar"].min()
df = df.filter(pl.col("bar") >= first_bar + pl.duration(hours=4))  # warm-up
print(f"pair-bars {df.height}, pairs {df['pair'].n_unique()}, {df['bar'].min()} to {df['bar'].max()}")
print(f"spread_bps quantiles over pair-bars: " + ", ".join(
    f"p{int(q*100)} {df['spread_bps'].quantile(q):.2f}" for q in (0.05, 0.25, 0.5, 0.75, 0.95)))

# variance decomposition: how much of log spread is between pairs vs within a pair over time
pair_mean = df.group_by("pair").agg(pl.col("y").mean().alias("pm"))
d2 = df.join(pair_mean, on="pair")
tot = float(d2["y"].var())
within = float((d2["y"] - d2["pm"]).var())
print(f"log-spread variance {tot:.3f}: between pairs {1 - within / tot:.1%}, within pair over time {within / tot:.1%}")


def design(frame: pl.DataFrame) -> np.ndarray:
    x = frame.select(X_COLS).to_numpy()
    return np.hstack([np.ones((x.shape[0], 1)), x])


def fit(frame: pl.DataFrame) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(design(frame), frame["y"].to_numpy(), rcond=None)
    return beta


def score(label: str, train: pl.DataFrame, test: pl.DataFrame) -> dict:
    beta = fit(train)
    pred = design(test) @ beta
    y = test["y"].to_numpy()
    res = y - pred
    r2 = 1 - res.var() / y.var()
    # empirical 90% band from the TRAIN residuals, and its coverage on test
    tr_res = train["y"].to_numpy() - design(train) @ beta
    lo, hi = np.quantile(tr_res, [0.05, 0.95])
    cover = float(((res >= lo) & (res <= hi)).mean())
    ratio = np.exp(res)  # actual / predicted
    # per-pair mean error (what a single pair's backcast would be off by on average)
    pe = pl.DataFrame({"pair": test["pair"], "res": res}).group_by("pair").agg(pl.col("res").mean())
    pair_bias = pe["res"].to_numpy()
    print(f"  {label:<40} n_train {train.height:>7} n_test {test.height:>7} | R2(log) {r2:.3f} | "
          f"resid sd(log) {res.std():.3f} (x{math.exp(1.96 * res.std()):.2f} at 95%) | bias {res.mean():+.3f} | "
          f"actual/pred p5 {np.quantile(ratio, 0.05):.2f} p50 {np.median(ratio):.2f} p95 {np.quantile(ratio, 0.95):.2f} | "
          f"train-90% band covers {cover:.1%} | per-pair mean error sd {pair_bias.std():.3f} "
          f"(x{math.exp(1.96 * pair_bias.std()):.2f}), worst |{np.abs(pair_bias).max():.2f}|")
    return {"beta": beta}


cut = df["bar"].min() + (df["bar"].max() - df["bar"].min()) / 2
pairs = sorted(df["pair"].unique().to_list())
rng = np.random.default_rng(20260919)
perm = rng.permutation(len(pairs))
groups = {p: int(perm[i] % 5) for i, p in enumerate(pairs)}
df = df.with_columns(pl.col("pair").replace_strict(groups).alias("g"))

print("\nOut-of-sample checks (OLS, log spread on the five archive-computable predictors):")
full = score("in-sample (all rows, all pairs)", df, df)
score("time split: first half -> second half", df.filter(pl.col("bar") < cut), df.filter(pl.col("bar") >= cut))
for g in range(5):
    score(f"pair split: pairs not in group {g} -> group {g}", df.filter(pl.col("g") != g), df.filter(pl.col("g") == g))
score("time AND pair split (group 0 unseen, 2nd half)",
      df.filter((pl.col("g") != 0) & (pl.col("bar") < cut)), df.filter((pl.col("g") == 0) & (pl.col("bar") >= cut)))
print("  coefficients (all rows): " + ", ".join(f"{n} {b:+.3f}" for n, b in zip(["const", *X_COLS], full["beta"])))

print("\nCoefficient stability, one fit per UTC day:")
for day, part in df.with_columns(pl.col("bar").dt.date().alias("day")).partition_by("day", as_dict=True).items():
    if part.height < 2000:
        continue
    b = fit(part)
    print(f"  {day[0]}  n {part.height:>6}  " + ", ".join(f"{n} {v:+.3f}" for n, v in zip(["const", *X_COLS], b)))

# the pair-level question: 8 days of pair means, can pair-level archive stats explain them?
pm = df.group_by("pair").agg([pl.col("y").mean()] + [pl.col(c).mean() for c in X_COLS])
beta = np.linalg.lstsq(np.hstack([np.ones((pm.height, 1)), pm.select(X_COLS).to_numpy()]), pm["y"].to_numpy(), rcond=None)[0]
res = pm["y"].to_numpy() - np.hstack([np.ones((pm.height, 1)), pm.select(X_COLS).to_numpy()]) @ beta
print(f"\nPair-level fit ({pm.height} pairs, one mean each): R2 {1 - res.var() / pm['y'].var():.3f}, "
      f"resid sd(log) {res.std():.3f} -> a pair's typical spread predicted within x{math.exp(1.96 * res.std()):.2f} at 95%")

df.select(["pair", "bar", "spread_bps", *X_COLS]).write_parquet(HERE / "spread_bars.parquet")
