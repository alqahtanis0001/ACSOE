"""Read-only timing: scoring EVERY universe pair per bar (127) with fold 404's real predictor,
calibrators, anomaly forest and a DI reference of the configured size - looped the way engine 8
scores one candidate today, and batched through the same modelling functions."""
import json
import sys
import time
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
D = REPO / "models/train-20260913T205245-067b2b9d-f404"
N = 127
from acsoe.modelling import di as di_module  # noqa: E402
from acsoe.modelling.calibration import apply_calibration, from_json  # noqa: E402

width = len(json.loads((D / "manifest.json").read_bytes())["feature_names"])
rng = np.random.default_rng(5)
X = rng.normal(size=(N, width))
booster = lgb.Booster(model_file=str(D / "model.txt"))
cal = list(from_json((D / "calibrators.json").read_bytes()))
forest = joblib.load(D / "anomaly.joblib")
XA = rng.normal(size=(N, 21))
ref = rng.normal(size=(200_000, width))
stamps = np.arange(200_000, dtype=np.int64) * 900
fit = di_module.DiFit(reference=ref, identity=tuple(f"P|{s}" for s in stamps), distribution=np.ones(200_000),
                      threshold=1.0, neighbours=10, percentile=0.99, decision_ts=stamps, exclusion_s=43200)


def timed(fn, reps=3):
    fn()
    t = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - t) / reps


pred_loop = timed(lambda: [apply_calibration(booster.predict(X[i:i + 1]), cal) for i in range(N)])
pred_batch = timed(lambda: apply_calibration(booster.predict(X), cal))
an_loop = timed(lambda: [forest.score_samples(XA[i:i + 1]) for i in range(N)])
an_batch = timed(lambda: forest.score_samples(XA))
di_loop = timed(lambda: [di_module.score(fit, X[i]) for i in range(N)], reps=1)
di_batch = timed(lambda: di_module._mean_nearest(X, fit.reference, neighbours=10, exclude_self=False))
print(f"{N} pairs per bar, fold 404 artefacts:")
print(f"  predict + calibrate : looped {pred_loop:.3f} s | batched {pred_batch:.3f} s")
print(f"  anomaly score       : looped {an_loop:.3f} s | batched {an_batch:.3f} s")
print(f"  DI score            : looped {di_loop:.3f} s | batched {di_batch:.3f} s")
print(f"  total               : looped {pred_loop + an_loop + di_loop:.2f} s | batched {pred_batch + an_batch + di_batch:.2f} s")
