"""Q8/Q9, read-only: time and size the per-bar work that grows with the pair count, on fold 404's
real artefacts. No engine is run; the modelling functions the engines call are timed directly."""
import json
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from winmem import peak, peak_commit, rss  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
D = REPO / "models/train-20260913T205245-067b2b9d-f404"
PAIRS = 127
print(f"start rss {rss():.0f} MiB")

from acsoe.modelling import di as di_module  # noqa: E402
from acsoe.modelling.features import MAX_LOOKBACK_BARS, compute  # noqa: E402

# ---- engine 5: features per pair per bar
csv = pl.read_csv(REPO / "data/historical/AAVEUSD_15.csv", has_header=False,
                  new_columns=["ts", "open", "high", "low", "close", "volume", "trades"])
csv = csv.with_columns([pl.col(c).cast(pl.Float64) for c in ("open", "high", "low", "close", "volume")])
window = MAX_LOOKBACK_BARS + 8
starts = np.linspace(100_000, csv.height - window - 1, PAIRS).astype(int)
frames = [csv.slice(int(s), window) for s in starts]
compute(frames[0], interval_s=900, min_lookback_fill=0.8)  # warm
t = time.perf_counter()
for f in frames:
    out = compute(f, interval_s=900, min_lookback_fill=0.8)
    out.tail(1).to_dicts()
feat_s = time.perf_counter() - t
print(f"engine 5 features: {PAIRS} pairs x {window} bars: {feat_s:.3f} s per decision bar "
      f"({feat_s / PAIRS * 1000:.1f} ms/pair); MAX_LOOKBACK_BARS {MAX_LOOKBACK_BARS}")

# ---- engine 8: predictor, calibration, SHAP on one candidate row
import lightgbm as lgb  # noqa: E402
manifest = json.loads((D / "manifest.json").read_bytes())
width = len(manifest["feature_names"])
x = np.random.default_rng(1).normal(size=(1, width))
t = time.perf_counter(); booster = lgb.Booster(model_file=str(D / "model.txt")); load_s = time.perf_counter() - t
t = time.perf_counter()
for _ in range(50):
    booster.predict(x)
pred_s = (time.perf_counter() - t) / 50
import shap  # noqa: E402
t = time.perf_counter(); explainer = shap.TreeExplainer(booster); expl_build = time.perf_counter() - t
t = time.perf_counter()
for _ in range(10):
    explainer.shap_values(x)
shap_s = (time.perf_counter() - t) / 10
print(f"engine 8: booster load {load_s:.2f} s (once per fold); predict {pred_s * 1000:.1f} ms; "
      f"TreeExplainer build {expl_build:.2f} s (once per fold); shap one row {shap_s * 1000:.0f} ms")

# ---- DI score of one row against a reference of the configured size (200,000 x width)
before = rss()
ref = np.random.default_rng(2).normal(size=(200_000, width))
stamps = np.arange(200_000, dtype=np.int64) * 900
fit = di_module.DiFit(reference=ref, identity=tuple(f"P|{s}" for s in stamps), distribution=np.ones(200_000),
                      threshold=1.0, neighbours=10, percentile=0.99, decision_ts=stamps, exclusion_s=43200)
t = time.perf_counter()
for _ in range(10):
    di_module.score(fit, x[0])
di_s = (time.perf_counter() - t) / 10
print(f"DI: reference in memory +{rss() - before:.0f} MiB; score one row {di_s * 1000:.0f} ms")

# ---- engine 13 anomaly and engine 15 skeptic
import joblib  # noqa: E402
t = time.perf_counter(); forest = joblib.load(D / "anomaly.joblib"); an_load = time.perf_counter() - t
xa = np.random.default_rng(3).normal(size=(1, 21))
t = time.perf_counter()
for _ in range(20):
    forest.score_samples(xa)
an_s = (time.perf_counter() - t) / 20
sk = lgb.Booster(model_file=str(D / "skeptic.txt"))
xs = np.random.default_rng(4).normal(size=(1, width + 4))
t = time.perf_counter()
for _ in range(50):
    sk.predict(xs)
sk_s = (time.perf_counter() - t) / 50
print(f"engine 13: load {an_load:.2f} s, score one row {an_s * 1000:.1f} ms | engine 15: predict {sk_s * 1000:.1f} ms")
print(f"end rss {rss():.0f} MiB | peak working set {peak():.0f} MiB | peak commit {peak_commit():.0f} MiB")
