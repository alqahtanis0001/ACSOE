# 66 — Engine 12 `regime`

**Owner:** C — Interface and models

**Phase:** 5. `engines/regime/` is C's.

## Goal

The candidate's market environment, classified as one of `trending`, `choppy` or
`high_volatility` from its own feature row, and published under `state["regime"]` for engine
14 to read in Phase 6. Rule-based in Phase 5; the HMM in the stack table is an optional
upgrade and is out of scope.

## Implementation

1. `engines/regime/engine.py`, `contracts.py`, `README.md`. `name = "regime"`, `number = 12`,
   `is_gate = False`.
2. Reads the candidate from `state["scout"]["pair"]` and its row from
   `state["feature"]["pairs"][pair]`. Absent candidate is `PASS`; absent feature row publishes
   `label: null` with a reason and returns `OK`.
3. The rules are **percentile-relative to the pair's own trailing window**, never absolute
   numbers: `high_volatility` when realised volatility over the short window sits above the
   `regime.high_vol_percentile` of its long-window distribution; else `trending` when the
   efficiency ratio (net move over path length) exceeds `regime.trend_efficiency`; else
   `choppy`. Both cutoffs are config keys the lead chooses as plumbing, flagged provisional,
   because no order is sized from them and no gate reads them.
4. Publishes `{"pair", "bar_ts", "label", "inputs": {name: value}, "di_regime_shift": null}`.
   The last field is a **declared placeholder for the locked decision that DI threshold
   crossings feed the regime engine**: engine 12 runs before engine 8 in the registry order,
   so the DI is not known on this tick and nothing persists it from the last one. The field is
   published as `null` with the reason in the README, and the question of where a previous
   bar's DI would live is an open question for the operator, not something this engine
   answers by reading the store.
5. `tests/engines/test_regime.py`, C lane. Fixtures from engine 5's real output.

## Scope Limits

- Do **not** fit an HMM or any model.
- Do **not** block. No regime is a reason to refuse; that is the router's business in Phase 6.
- Do **not** read the DI from anywhere. It is not available to this engine yet.

## Check When Done

- Each of the three labels reached by a fixture that differs from the others in exactly one
  input.
- Mutation observed red: the percentile rule replaced by an absolute threshold.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
