"""Read-only measurement: train the 13-fold-capped skeptic for given folds IN MEMORY, with the
trainer's own row selection (`_skeptic_training_rows`) and the trainer's own model settings, and
save only its P(wrong) on (a) every BUY call of that fold and (b) nothing else. Nothing is written
to models/ or data/. Output: a small parquet per fold in the scratchpad.

`validate` mode refits an EARLY fold uncapped (small) and compares with the saved skeptic.txt, to
prove this replication reproduces the trainer before any capped number is trusted.
"""
import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
REPO = Path(r"C:\Users\saad2\Documents\GitHub\ACSOE")
RUN = "train-20260913T205245-067b2b9d"
OOS = REPO / "data/derived" / f"oos_{RUN}.parquet"
SORTED = REPO / "data/derived" / f"di_anomaly_{RUN}" / "dataset_sorted_by_decision_ts.parquet"
CAP = 13

from acsoe.modelling.artefacts import load_run  # noqa: E402
from acsoe.modelling.features import FEATURE_VERSION  # noqa: E402
from acsoe.platform.config import load_config  # noqa: E402
from acsoe.research import training  # noqa: E402

config = load_config(REPO / "config/default.yaml")
mode = sys.argv[1]
folds = [int(v) for v in sys.argv[2].split(",")]
oos_all = pl.read_parquet(OOS, columns=["pair", "decision_ts", "label_window_end_ts", "fold_index", "is_buy",
                                         "p_target", "p_stop", "p_timeout", "expected_move_pct", "label", "weight"])
for k in folds:
    t0 = time.perf_counter()
    d = REPO / "models" / f"{RUN}-f{k}"
    names = tuple(json.loads((d / "manifest.json").read_bytes())["feature_names"])
    run = load_run(d, expected_features=names, expected_version=FEATURE_VERSION)
    fold = run.manifest.fold
    lo_fold = 0 if mode == "validate" else max(0, k - CAP)
    prev = oos_all.filter((pl.col("fold_index") >= lo_fold) & (pl.col("fold_index") < k))
    lo_ts, hi_ts = int(prev["decision_ts"].min()), int(fold.test_end_ts)
    data = (pl.scan_parquet(SORTED).filter((pl.col("decision_ts") >= lo_ts) & (pl.col("decision_ts") < hi_ts))
            .select(["pair", "decision_ts", *names]).collect())
    rows = training._skeptic_training_rows(prev, data, fold, names=names, interval_s=900,
                                           embargo_bars=int(config.get("backtest.embargo_bars")))
    wrong = (rows["label"] != training.LABEL_TARGET).cast(pl.Int64).to_numpy()
    model = lgb.LGBMClassifier(
        objective="binary", n_estimators=int(config.get("training.num_trees")),
        learning_rate=float(config.get("training.learning_rate")), num_leaves=int(config.get("training.num_leaves")),
        min_child_samples=int(config.get("training.min_data_in_leaf")), random_state=int(run.manifest.seeds["train"]),
        deterministic=True, force_row_wise=True, n_jobs=int(config.get("prediction.threads")), verbose=-1)
    model.fit(training._skeptic_matrix(rows, run.scaler, names), wrong, sample_weight=rows["weight"].cast(pl.Float64).to_numpy())
    buys = oos_all.filter((pl.col("fold_index") == k) & pl.col("is_buy")).join(data, on=["pair", "decision_ts"], how="inner")
    x = training._skeptic_matrix(buys, run.scaler, names)
    mine = model.predict_proba(x)[:, 1]
    saved = lgb.Booster(model_file=str(d / "skeptic.txt")).predict(x) if (d / "skeptic.txt").exists() else np.full(len(mine), np.nan)
    if mode == "validate":
        ident = training.identity_digest([str(v) for v in rows["pair"]], [int(v) for v in rows["decision_ts"]]) \
            if hasattr(training, "identity_digest") else None
        recorded = run.manifest.metrics.get("skeptic_training_identity") or (run.manifest.extras.get("skeptic") or {}).get("training_identity")
        print(f"VALIDATE fold {k}: rows {rows.height} (manifest {run.manifest.metrics.get('skeptic_rows')}); identity "
              f"{'MATCH' if ident == recorded else f'{ident} vs {recorded}'}; max |P mine - P saved| {np.nanmax(np.abs(mine - saved)):.2e}")
        continue
    out = buys.select(["pair", "decision_ts", "fold_index", "label"]).with_columns(
        pl.Series("p_capped", mine), pl.Series("p_uncapped", saved))
    out.write_parquet(HERE / "capped" / f"fold_{k:03d}.parquet")
    print(f"fold {k}: capped rows {rows.height} vs uncapped manifest {run.manifest.metrics.get('skeptic_rows')}; "
          f"BUY calls {buys.height}; veto@0.5 capped {(mine > 0.5).mean():.3f} uncapped {(saved > 0.5).mean():.3f}; "
          f"{time.perf_counter() - t0:.0f} s", flush=True)
