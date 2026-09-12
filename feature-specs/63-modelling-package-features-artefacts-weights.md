# 63 — `modelling/`: the feature arithmetic, the artefact manifest and the sample weights

**Owner:** C — Interface and models

**Phase:** 5. `src/acsoe/modelling/` is C's under spec 59's ownership change.

## Goal

One implementation of every number that has to agree between the live loop and the training
pipeline. A feature computed here reproduces in replay because replay runs the same function;
an artefact written here is loadable by an engine because the engine reads the same manifest.

## Why a leaf package

Invariant 5: the live loop never imports `research/` and `research/` never imports the live
loop. Engine 5 and `research/training.py` both need the feature arithmetic; engines 8, 13 and
15 and the trainer both need the artefact layout and the DI arithmetic. `modelling/` is the
one package both may import. It imports nothing from `acsoe` except types in
`core/contracts.py`, reads no `state`, opens no client, holds no engine, and a test walks its
import graph to prove it.

## Implementation

1. **`modelling/features.py`.** A pure function from a polars frame of closed candles for one
   pair (`ts, open, high, low, close, volume, trades`, the loader's columns and engine 3's) to
   a frame of features keyed by `ts`. Constraints, not a list:
   - **OHLCVT only.** No column named `spread`, `bid`, `ask` or `depth` is read, and a test
     asserts it on the AST. If a spread-derived feature is wanted, stop and say so.
   - **A feature at bar `t` uses bars at or before `t`.** Closed bars only; the in-progress
     bar never enters. Invariant 10.
   - **Lookbacks are windows of time, not counts of rows**, for the reason the timeout barrier
     is. A window of `n` bars is `n * interval_s` seconds; `bars_in_lookback_<n>` is itself a
     feature; a window whose fill is below `features.min_lookback_fill` yields NaN for every
     feature over it. Nothing is interpolated.
   - **No pair identity.** No feature encodes which pair a row belongs to; every feature is a
     return, a ratio, a z-score, a rank within the pair's own window, or a clock field
     (hour of day, day of week from `ts`). A pooled model that can memorise a pair name has
     learned nothing that transfers.
   - **Named, ordered, versioned.** `FEATURE_NAMES` is an ordered tuple; `FEATURE_VERSION` is
     a string; the largest lookback is `MAX_LOOKBACK_BARS`, asserted at most
     `features.max_lookback_bars`.
   - `float` and `numpy` throughout: these are model inputs, not money.
2. **`modelling/artefacts.py`.** The `models/<run_id>/` layout, read and written here only:
   `manifest.json` (run id, created at from an injected clock, config digest, seeds,
   `FEATURE_VERSION`, the ordered feature list, fold bounds, dataset provenance from the
   archive report, metrics, and a sha256 per file), `scaler.json` (MinMax min and max per
   feature, JSON and never a pickle), one file per model. Loading verifies every hash and
   refuses a manifest whose feature list is not exactly `FEATURE_NAMES` in order. Writing goes
   through the path B's store hands over and never creates a directory itself.
3. **`modelling/weights.py`.** Average-uniqueness weights: per pair, concurrency at each bar is
   the number of labels whose `[decision_ts, label_window_end_ts]` covers it; a row's weight is
   the mean of `1 / concurrency` over its own window. Linear in rows via prefix sums.
   `effective_sample_size(weights)` is `sum(weights)`.
4. **`modelling/di.py`.** Fit and score for the Dissimilarity Index exactly as spec 59
   decision 6 states. Fitting takes the reference rows and the scaler and returns the reference
   matrix, the leave-one-out statistic distribution and the threshold at the given percentile;
   scoring takes one vector and returns the DI and whether it exceeds the threshold. Both pure.
5. `tests/modelling/`, C lane.

## Scope Limits

- Do **not** train anything here. Fitting the DI is arithmetic; training a predictor is spec 67.
- Do **not** read config, the clock, `state` or any client. Every input is an argument.
- Do **not** choose the ranking feature for engine 7; expose the names, that is all.
- Do **not** write a feature that needs the order book. The archive has none.

## Check When Done

- `features_reproduce_in_replay` and `feature_lookbacks_are_time_not_rows` PASS.
- Mutations observed red: a lookback counted in rows; the in-progress bar included; a feature
  reading `close` of bar `t+1`; the manifest loader accepting a feature list in a different
  order; weights computed without the label window (all ones).
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
