# 67 — `research/training.py`: the dataset, the weights and the weekly walk-forward predictor

**Owner:** C — Interface and models

**Phase:** 5. `research/training.py` is C's.

## Goal

A predictor that trains at the same cadence the live system retrains, on a dataset assembled
from the historical archive and nothing else, and reports the metric decided before it
trained. `python -m acsoe.research.training --config config/default.yaml` runs it end to end
and writes one artefact directory per fold under `models/`.

## The three rulings this spec is held to

**The walk-forward is past-only.** `research/walkforward.py` is used as it is. Operator
ruling 1 of 2026-09-12, and `walkforward_trains_on_the_past_only` exists to keep it that way.
If a change here makes that criterion red, the change is wrong.

**The metric is the Brier score of P(target) against the base-rate Brier**, per fold, with
multiclass log loss beside it and the target rate among BUY calls reported as a number.
**The break-even rates are never in code** (amended 2026-09-13, C-2's finding): break-even is
a function of live fees, measured spread and slippage, none of which exists offline, and the
figures in invariant 5 are marked for sanity-checking only; writing 0.61 into the trainer would
be the hardcoded fee `AGENTS.md` forbids under another name. The digest reports
`buy_target_rate` and says in its notes that the comparison against invariant 5 is the
reader's.
**Accuracy is not computed, because the base rate is 23.89% and a model predicting `stop`
always scores 51%**: it rewards the model that never trades. Spec 59 decision 4, confirmed by
the operator 2026-09-12.

**Rows are weighted by average uniqueness.** Spec 59 decision 5. **The effective sample size
is reported per fold, on the same line as that fold's row count, and again in aggregate.** A
fold with 8,000 rows and an effective size of 300 is a fold whose metrics mean almost nothing,
and an aggregate figure hides exactly that fold. Operator addition, 2026-09-12.

## Implementation

1. **Dataset assembly.** `ArchiveReplay.from_directory` (A's) gives the archive; per pair,
   `label_frame` (spec 52) gives labels with `label_window_end_ts`, and
   `modelling.features.compute` gives features on the same frame; joined on `decision_ts`.
   Macro columns come from the configured archive spelling of each macro pair, joined by
   `decision_ts`, with `macro_available` false where the macro bar is missing. Pairs below
   `dataset.min_labelled_rows` are excluded by name, as engine 23 does. The result is one
   pooled frame across pairs with `pair` carried as an identifier column that is **never** a
   feature. Written once to `data/derived/dataset_<stamp>.parquet` with the archive
   provenance as Parquet metadata, and reused by the training loop.
2. **Weights.** `modelling.weights.average_uniqueness` per pair, joined back as `weight`.
3. **Folds.** `purged_walk_forward` over the pooled rows at `backtest.training_window_days`,
   `backtest.retrain_interval_days` and `backtest.embargo_bars`. Folds are cut on time, so the
   pooled frame produces one fold per week across every pair at once.
4. **The predictor.** LightGBM multiclass over `FEATURE_NAMES` plus the macro columns, in that
   order, with `weight` as the sample weight, `seeds.train` as every seed it accepts,
   `deterministic=True` and a fixed thread count from config. MinMax scaling fitted on the
   training rows only. Probability calibration fitted on a **held-out tail of the training
   window** (the last `prediction.calibration_days`), never on the test window; isotonic per
   class then renormalised. Class order is `(target, stop, timeout)` and is written into the
   manifest.
5. **Expected move.** `expected_move_pct = p_target * target_pct - p_stop * stop_pct +
   p_timeout * mean_timeout_return`, where the last term is the mean `return_pct` of timeout
   rows in the training window. Barrier values from config. A BUY call is
   `expected_move_pct > 0`. The same function is exported from `modelling/` so engine 8
   computes it identically.
6. **Out-of-sample predictions** for every test row of every fold are written to
   `data/derived/oos_<run_id>.parquet` with the fold index, the three probabilities, the DI
   (spec 68), `expected_move_pct`, `is_buy`, the label and the weight. Specs 69, 74 and 75
   read this file and nothing else.
7. **Metrics per fold** into the manifest and into a digest
   `data/derived/walkforward_digest_<run_id>.json`: rows, effective sample size, Brier,
   base-rate Brier, log loss, BUY count, BUY target rate, and the counts of purged, embargoed
   and after-test rows from the `Fold`. `--write-fixture` copies the digest to
   `tests/fixtures/walkforward_digest.json`, which is the committed evidence
   `walkforward_weekly_retrain_reports_oos` reads offline.
8. **Artefacts** through `modelling.artefacts` into `store.new_model_run_dir(run_id)` per
   fold, `run_id` minted as `train-<utc stamp>-<config digest prefix>-f<fold>`. Never
   overwritten.
9. `--pairs`, `--max-folds` and `--start`/`--end` flags for smoke runs; the full run over 234
   pairs and roughly 450 weekly folds is expected to take hours and is the `--live` half.
10. `tests/research/test_training.py`, C lane, over `tests/fixtures/candles_sample.parquet`
    joined to the 960-row labelled sample (spec 60's corrected inputs) and over constructed
    frames long enough to hold several folds, where the right answer is known.

## Scope Limits

- Do **not** touch `research/walkforward.py` except to read it. If it needs a change, stop.
- Do **not** read `data/raw/`, `data/summaries/` or any spread. The archive is the only input.
- Do **not** fit the DI, the skeptic or the anomaly detector here. Specs 68, 69, 70 hook into
  the fold loop this spec exposes.
- Do **not** compute accuracy, and do **not** pick a BUY threshold other than the sign of the
  expected move.
- Do **not** promote anything. `promoted` is Phase 7.

## Check When Done

- `predictor_trains_and_calibrates`, `training_is_reproducible_from_config_and_data` and
  `walkforward_weekly_retrain_reports_oos` PASS.
- Mutations observed red, each named with its message in the build log: the calibrator fitted
  on the test window; a seed read from `time`; weights all ones; the scaler fitted on train
  plus test; `pair` included as a feature; the feature order in the manifest permuted.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
