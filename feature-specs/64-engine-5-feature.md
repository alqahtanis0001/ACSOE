# 64 — Engine 5 `feature`

**Owner:** C — Interface and models

**Phase:** 5. `engines/feature/` is C's.

## Goal

The first engine of the opportunity chain computes the feature vector for every pair engine 3
published candles for, on the tick where a decision bar closed, and publishes it under
`state["feature"]`. On every other tick it returns `PASS` and the chain stops, which is the
cadence mechanism in `engine-contracts.md`.

## Implementation

1. `engines/feature/engine.py`, `contracts.py`, `README.md`. `name = "feature"`,
   `number = 5`, `is_gate = False`.
2. Reads `state["market_sensor"]["bar_closed"]`; when false, `PASS` with no data. When true,
   groups `state["market_sensor"]["candles"]` by `pair`, builds the per-pair frame with the
   money strings converted to float **here and only here**, and calls
   `modelling.features.compute` per pair. The in-progress bar is never present because engine
   3 never publishes it; a test asserts the engine would still exclude a candle whose `ts`
   equals `closed_bar_ts` plus one interval if one appeared.
3. Publishes `state["feature"] = {"bar_ts", "feature_version", "feature_names",
   "pairs": {pair: {name: float | null}}, "pairs_with_short_history": [...]}`. A pair whose
   candles cover less than `MAX_LOOKBACK_BARS` of time is published with NaN-as-null features
   and listed, never dropped: engine 7 must be able to see it was considered.
4. ~~`missing_bars` from engine 3 is reported through as `gaps_in_range` per pair.~~
   **Amended 2026-09-13.** Engine 3's `missing_bars` is a union across pairs, and that is
   correct for its only consumer, `data_guard`: a per-pair reading would block permanently on
   the ordinary fact that a thin pair did not trade. Engine 5 therefore counts each pair's
   holes **from that pair's own candles** and publishes them per pair; a test asserts two
   pairs get different counts so a later read-through of the union goes red. Engine 3 is not
   asked to publish a per-pair map.
5. Every read of another engine's key is a named constant in `contracts.py` with the owning
   engine beside it, the pattern `engines/memory/contracts.py` set.
6. `tests/engines/test_feature.py`, C lane. The fixtures are **engine 3's real output**: drive
   `MarketSensorEngine` through the real orchestrator against the harness's stream double and
   take `state["market_sensor"]` from it, per the Phase 3 ruling that no test hand-builds
   another engine's payload.

## Scope Limits

- Do **not** compute a feature here. The arithmetic is `modelling/features.py`; this engine
  shapes inputs and publishes outputs.
- Do **not** block. Engine 5 is not a gate; a pair with no usable history is reported, not
  refused. Refusing is engine 7's and engine 13's.
- Do **not** read quotes, spread or the order book.
- Do **not** cache anything on the engine across ticks. Contract invariant 1.

## Check When Done

- `features_reproduce_in_replay` PASS through this engine's path.
- Mutations observed red: `bar_closed` ignored (features on every tick); a pair with short
  history dropped instead of listed; the candle grouping keyed on something other than `pair`.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
