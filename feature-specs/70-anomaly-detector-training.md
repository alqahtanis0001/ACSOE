# 70 — The anomaly detector, fitted on market data only

**Owner:** C — Interface and models

**Phase:** 5. Training in `research/training.py`; the artefact under its own `run_id` per fold.

## Goal

An unsupervised outlier model over **market-data** features, fitted per fold on the
predictor's training window, whose score and threshold engine 13 uses to decide whether the
market is broken rather than whether the trade is good.

## Implementation

1. Inputs are a named subset of `FEATURE_NAMES` declared in `modelling/features.py` as
   `MARKET_QUALITY_FEATURES`: velocity (absolute return magnitudes), volume and trade-count
   z-scores, range measures and `bars_in_lookback` fill. **No spread.** The invariants describe
   anomaly's inputs as velocity, volume and spread; the archive carries no spread, so the
   spread input is stated absent in the manifest and in engine 13's README, and if it is
   wanted later it is a stop and a question, not a reach for the recorder.
2. `IsolationForest` from scikit-learn, `seeds.train`, fitted on the fold's training rows,
   MinMax-scaled with the predictor's scaler. The threshold is the `anomaly.threshold_percentile`
   quantile of the training rows' own scores, recorded in the manifest.
3. Serialised with `joblib`, and the manifest carries its sha256; the loader refuses a file
   whose hash differs. Stated in the build log as the one artefact that is not a text format,
   and why.
4. Reported per fold: the out-of-sample block rate at the threshold. A rate that is zero or
   near one on every fold is a finding, not a pass.
5. `tests/research/test_anomaly_training.py`, C lane.

## Scope Limits

- Do **not** use labels. This is unsupervised by definition; a label reaching it makes it a
  second predictor.
- Do **not** default `anomaly.threshold_percentile`. Absent means no threshold is recorded and
  engine 13 blocks with `anomaly_unavailable`.
- Do **not** read a spread from anywhere.

## Check When Done

- ~~A constructed fold where one test row has a ten-sigma volume spike scores above the
  threshold and an ordinary row scores below it.~~ **Amended 2026-09-13 to the
  measurement:** the spiked row scores strictly above the same row unspiked, sits above the
  0.85 quantile while the unspiked row sits below it, and a run at a 0.85 threshold blocks the
  spike and passes the ordinary bar. At 0.99 or 0.95 it clears neither, for reasons recorded
  in the tracker; the threshold is the operator's and the model choice is an open question.
- Mutation observed red: the label column joined into the inputs.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
