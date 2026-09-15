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

## Amendment, 2026-09-15 — the leave-one-out excludes 48 bars across all pairs

**Operator ruling 1 of 2026-09-15, amending ruling 6 of 2026-09-12.** The leave-one-out
distribution the threshold is taken from excludes **every reference row whose `decision_ts` is
within 48 bars of the row being scored, across all pairs** (`|Δ decision_ts| <= span`, inclusive,
the row itself included), not the row alone. The span is `backtest.embargo_bars ×
timeframes.decision_bar_s`: a live candidate is at least the embargo after the end of the
reference window, so the reference distribution excludes the same span. Scoring a live or test
row is unchanged, because no scored row is ever within that span of the reference window.

**Why.** 78 of the 117 DI columns are the BTC and ETH macro features, identical for every pair on
the same bar, and the calendar columns are too. Leave-one-out on the row alone therefore leaves
near-identical same-moment neighbours of every reference row in the reference set: its ten nearest
neighbours are other pairs on the same or adjacent bars. The threshold was measuring **time
proximity**, not distributional distance, and a live candidate, which has no same-moment rows in
the reference window, landed above it whatever the market was doing. Measured over the full run's
405 folds: a threshold at the 0.95 percentile of the old distribution refused 94.7% of complete
out-of-sample rows, 0.99 refused 74.9%, 0.999 refused 31.1%, and the refused rows were no worse
than the kept ones. Excluding the same pair's nearby rows changed nothing; excluding every pair's
rows within 48 bars put the reference distribution on top of the test distribution on each of
seven folds from 2017 to 2024 (`docs/dataset/di-anomaly-distributions-2026-09-14.md`,
`docs/dataset/di-serial-correlation-check-2026-09-15.py`).

**Rejected, by the same ruling.** Dropping the macro columns from the DI input would blind the DI
to exactly the market-wide conditions it exists to detect. Rebuilding the reference set is a
larger change with no evidence behind it.

**A DI fitted without the exclusion is the defect, not a variant.** So:

7. `modelling/di.fit` takes `decision_ts` and `exclusion_s` (both required, no default in
   `modelling/`), records `exclusion_s` in `di.npz` and the manifest, and `di.load` refuses an
   artefact that does not record a positive one; engine 8 therefore refuses such a DI.
8. `research/training.py` passes the reference rows' `decision_ts` and the span from config.
9. **Criterion `di_leave_one_out_excludes_48_bars`**, registered for phase 5, independent of
   `prediction.di_percentile` (the subject is fitted at a percentile the criterion owns): it
   recomputes from the artefact's reference rows both the plain leave-one-out and the excluded one
   with the span read from config, and PASSes only when the artefact equals the excluded
   distribution **and** the plain one differs on that subject, so the subject can exhibit the
   property. Observed FAIL on a DI fitted with the exclusion removed.

**`prediction.di_percentile` stays absent** until the operator rules on the refit's refusal rates;
engine 8 stays fail-closed meanwhile, which does not block registration.
