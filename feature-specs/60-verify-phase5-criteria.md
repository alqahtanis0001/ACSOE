# 60 — The Phase 5 exit criteria in `scripts/verify.py`

**Owner:** C — Interface and models

**Phase:** 5. First in the phase, before any subject it judges exists, for the reason specs 00,
16, 33, 45 and 48 were first: `--phase 5` today registers `docs_vocabulary` and
`toolchain_green` alone and prints *"Phase 5 is green"* over a phase in which nothing exists.

## Goal

Eleven criteria registered for phase 5, each reporting PENDING until its subject lands, PASS
against the real thing, and **FAIL against the named wrong implementation**. This is the phase
where a wrong implementation produces a model that looks excellent and nothing goes red, so
each criterion is written to be sensitive to a specific mistake rather than to the shape of
the evidence.

## Implementation

Each criterion runs offline on a fresh clone. Where the subject is a trained model, the
criterion trains one **inside the criterion** into a temporary models root, so no artefact is
ever read from a gitignored path.

**The committed inputs, corrected 2026-09-13 after C's finding.** `labelled_sample.parquet`
is the labeller's *output*: it carries no open, high, low, volume or trades, and it spans ten
days of one pair, which cannot hold a ninety-day fold. So: a second committed fixture,
`tests/fixtures/candles_sample.parquet`, the OHLCVT slice of the real archive that the
labelled sample was produced from, extended backwards by `market_sensor.published_bars` so the
first labelled bar has a full lookback behind it, with its real gaps, because a time-window
lookback and a row-count one only disagree where there is a hole. The labels join it on
`decision_ts`. A close-only reconstruction is forbidden: every range and volume feature would
be a constant, and two paths agreeing on a constant agree on nothing.

1. `features_reproduce_in_replay`: the feature module over `candles_sample.parquet` gives the
   same values through engine 5's live path (candles shaped as engine 3 publishes them) and
   through the offline builder over the archive frame; and no name in
   `modelling/features.py` reads `spread`, `bid`, `ask` or `depth`, asserted on the AST and on
   the column set. **FAIL** when one feature is computed differently on the two paths.
2. `feature_lookbacks_are_time_not_rows`: a lookback over a window containing a gap reports
   `bars_in_lookback` below the expected count and the value as NaN rather than stretching the
   window over the gap. **FAIL** when a lookback is counted in rows.
3. `predictor_trains_and_calibrates`: a predictor trains, emits three probabilities summing to
   one, a calibrator is present, the manifest carries the ordered feature list and the scaler,
   and the fold's Brier and base-rate Brier are both reported. **FAIL** when the artefact
   lacks the feature order, and when Brier is absent while accuracy is present.
4. `training_is_reproducible_from_config_and_data`: two runs over the same config and data
   produce identical predictions on the test fold and identical model bytes, and are written
   under two `run_id`s; writing into an existing `run_id` **refuses**. **FAIL** when a seed is
   read from anywhere but config, and when a second run overwrites the first.
5. `di_fitted_on_predictor_training_set`: the DI manifest's reference-row identity equals the
   predictor's training-row identity for that fold, **not** the BUY subset; and a DI fitted on
   the BUY subset vetoes an ordinary row that the correctly fitted DI accepts. **FAIL** in
   both directions: fitted on BUY rows, and fitted on the test rows.
6. `skeptic_trains_only_on_predictor_buy_rows`: every skeptic training row is a predictor
   **out-of-sample** BUY call from an earlier fold. **FAIL** when a non-BUY row or an
   in-sample BUY row is present.
7. `walkforward_weekly_retrain_reports_oos`, in two halves, the pattern
   `walkforward_folds_purged_and_embargoed` set. Offline: the committed digest
   `tests/fixtures/walkforward_digest.json`, produced by spec 67's `--write-fixture` from a real
   run, carries one entry per fold with Brier, base-rate Brier, log loss, BUY-call target rate,
   row count and effective sample size on the same line, and `train_end_ts == test_start_ts`
   on every fold; and, separately, the fold-and-train machinery is driven over a **constructed**
   series long enough to hold several weekly folds at the committed window settings, because
   the ten-day sample cannot. `--live` re-runs the trainer over the real dataset and compares.
   **FAIL** when any fold trains after its test window, when the effective sample size equals
   the row count on overlapping labels, and when a fold's effective size is reported only in
   aggregate.
8. `anomaly_and_skeptic_have_both_tests`: the shape of `phase_3_gates_have_both_tests` for
   engines 13 and 15.
9. `scout_ranks_by_feature_not_arrival`: `rank_universe` called **directly** with a feature
   map whose intended order disagrees with arrival order on every element returns the
   intended order; with no ranking feature configured it returns alphabetical order and the
   engine publishes `rank_feature: null`. **FAIL** when arrival order is preserved.
10. `tournament_writes_leaderboard_from_oos`: engine 20 over a training digest writes one
    `leaderboard` row per model version with `brier`, `n_trades` and `win_rate` filled and
    `promoted = 0`, through the real `StoreClient`. **FAIL** when `promoted` is ever 1 in
    Phase 5, and when the row is written by anything but engine 20.
11. Re-register the Phase 4 criterion `walkforward_trains_on_the_past_only` under phase 5
    unchanged, so the Phase 5 gate itself goes red if a Phase 5 change weakens it.

Every PENDING line names the module, class or config key it waits for and the spec that
builds it. `tests/verify/test_phase5_criteria.py` holds all three observations per criterion.

## Scope Limits

- Do **not** build any engine, the feature module or the trainer here. Fabricate the subject.
- Do **not** fabricate a contract: import the real `core/contracts.py`, the real store
  contracts and the real config model. A criterion that cannot reach its body without a
  fabricated contract is a finding.
- Do **not** read `data/`, `models/` or `logs/` from any non-live criterion.
- Do **not** compute accuracy anywhere in this file.

## Check When Done

- Every criterion observed PENDING on a tree without its subject, PASS against a fabricated
  subject, and FAIL against the named wrong implementation, with each red message quoted in
  `docs/build-log/phase-5/c-interface.md`.
- `--phase 5` prints *"Phase 5 is not green"* with every criterion PENDING and zero FAIL.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
