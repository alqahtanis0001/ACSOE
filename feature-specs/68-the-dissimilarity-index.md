# 68 — The Dissimilarity Index, fitted on the predictor's training set

**Owner:** C — Interface and models

**Phase:** 5. Fitting lives in `research/training.py`; the arithmetic in `modelling/di.py`;
the artefact beside the predictor under the same `run_id`.

## Goal

A per-fold DI artefact that lets engine 8 refuse to predict on a feature vector unlike
anything the predictor was trained on, fitted on **exactly the rows the predictor trained on**
and provably not on the skeptic's BUY subset.

## Why this spec exists on its own

Fitted on BUY rows, the DI learns that "normal" means a BUY-shaped setup and then vetoes every
ordinary market state. Nothing goes red: the veto rate is high, the few trades it lets through
look clean, and the leaderboard flatters the model. The only defence is to prove which rows the
DI saw, so this spec is mostly about that proof.

## Implementation

1. Inside spec 67's fold loop, after the predictor's scaler is fitted: the reference rows are
   the fold's training rows, scaled with the predictor's scaler, restricted per pair to the
   last `prediction.di_window_days` of the training window, then subsampled to at most
   `prediction.di_reference_rows` with `seeds.train`. `modelling.di.fit` returns the reference
   matrix, the leave-one-out distribution and the threshold at `prediction.di_percentile`.
2. **Identity, not a count.** The DI artefact records a hash over the sorted
   `(pair, decision_ts)` of every reference row, and the predictor's manifest records the same
   hash over its training rows and over its BUY subset. `di_fitted_on_predictor_training_set`
   asserts the DI hash is a subset-hash of the training identity and is **not** derivable
   from the BUY identity. A count of rows would pass whenever the two sets happened to be the
   same size.
3. Written as `di.npz` plus its entry in the manifest with the percentile and the neighbour
   count, under the fold's `run_id`.
4. The DI of every out-of-sample row is scored and written into spec 67's OOS file, with
   `di_refused: bool`, so the veto rate per fold is a reported number and spec 75 can see it.
5. Reported per fold in the digest: reference rows, threshold, out-of-sample veto rate.
6. `tests/research/test_di.py`, C lane, including a constructed case where the BUY subset
   is a tight cluster and the full training set is not, so the two fits disagree on an
   ordinary row.

## Scope Limits

- Do **not** fit on the skeptic's rows, the test rows, or the BUY subset, and do **not**
  accept a caller who passes them; the fit takes the fold and reads the training index itself.
- Do **not** default `prediction.di_percentile`. Absent means the fit stops and the criterion
  reports PENDING naming the key.
- Do **not** score the DI live here. That is engine 8, spec 71.

## Check When Done

- `di_fitted_on_predictor_training_set` PASS, and observed FAIL when the fit is pointed at the
  BUY subset and when it is pointed at the test rows.
- Mutation observed red: the identity hash computed over row count instead of row identity.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
