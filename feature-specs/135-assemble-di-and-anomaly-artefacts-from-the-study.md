# 135 — The DI and the anomaly threshold, assembled from the Phase 5 study into new run directories

**Owner:** C — Interface and models

**Phase:** 7. Operator ruling 2026-09-19: rebuilt from the study, not refitted.

## Goal

For every fold in the simulation window, a new run directory that engines 8 and 13 load. It holds
the fold's predictor, calibrators and scaler unchanged, plus:

- a `di.npz` whose reference is rebuilt and whose threshold comes from the study's saved
  leave-one-out distribution with the 48-bar exclusion;
- the anomaly threshold, taken from the study's saved training scores.

Today both engines refuse all 405 folds: there is no `di.npz`, and the anomaly threshold is `null`.

## Implementation

1. **A module in `research/`**, new and C's. For fold *k* of `train-20260913T205245-067b2b9d`:
   - **Rebuild the DI reference** with the trainer's own selection. The study's `di_reference` is
     line-for-line `_fit_and_score_di` stopping before `di.fit`.
   - **Assert that the reference identity equals the study's recorded `reference_identity`**
     (`data/derived/di_anomaly_…/fold_NNN.json`). Measured 2026-09-19 on folds 326, 360 and 404:
     4–9 s per fold, peak 5.7 GB, identity equal on all three
     (`docs/dataset/phase-7-recon-2026-09-19/`).
   - Take `distribution` from `excl_fold_NNN.npz`, and `threshold = np.quantile(distribution,
     prediction.di_percentile)`, which is `di.fit`'s own line.
   - Take `exclusion_s` from the study file's `span_s`.
   - Save with `modelling.di.save`, so `modelling.di.load` reads it back.
2. **Anomaly:** `threshold = np.quantile(anomaly_train_scores, anomaly.threshold_percentile)`.
   These are the study's saved `-score_samples` values, the trainer's own orientation and quantile.
   Record it in the manifest's anomaly extras.
3. **A new run directory per fold**, through `StoreClient.new_model_run_dir`, which refuses an
   existing one.
   - Name: the source run id plus a Phase 7 suffix.
   - Files: copies of `model.txt`, `calibrators.json`, `scaler.json`, `anomaly.joblib` (and
     `skeptic.txt` unless spec 136 supplies a capped one), plus `di.npz`.
   - A manifest written by `modelling/artefacts.py`, carrying a sha256 per file.
4. **Provenance in the manifest:**
   - the source run id and each copied file's source sha256;
   - the study files' sha256s;
   - **both config digests**: the training digest `067b2b9d…`, and the digest of the config the
     thresholds were read from. The study script refuses today's config because the digest now
     covers the three thresholds ruled after training, so the two digests differ, and the manifest
     must say which is which.
   - that the DI distribution is the study's, verified against the module on 16 rows per fold at
     1e-9, **not** a `di.fit` output.

## Scope Limits

- `models/train-20260913T205245-067b2b9d-f*` are **never written to**. The store refuses an
  existing directory anyway.
- No retraining of any predictor, calibrator, scaler or forest.
- Only the folds the ruled window needs (R4), not all 405, unless the operator asks.

## Check When Done

- For every assembled fold: engines 8 and 13 load it, `di_fitted_on_predictor_training_set`
  PASSes on it, and the threshold recomputed from the study file equals the manifest's.
- A planted wrong reference (off by one row) is refused by the identity check.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
