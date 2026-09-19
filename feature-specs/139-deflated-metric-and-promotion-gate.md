# 139 — The deflated metric and the promotion gate

**Owner:** C — Interface and models (engine 20 `tournament`)

**Phase:** 7. The Phase 7 row's second criterion. Engine 20 has promoted nothing since Phase 5.

## Goal

A model is promotable only if its edge survives a haircut for the number of configurations tried
on the same data. The gate rejects a model that does not survive, and records why.

## Implementation

1. **The deflated metric:** the deflated Sharpe ratio (Bailey and López de Prado), computed from
   the run's per-period returns, with the skew and kurtosis terms and the number of trials as
   inputs. The formula is cited in the module docstring, and its arithmetic is held to a worked
   example.
2. **The trial count. RULING REQUIRED (R9).** The lead's proposal: every configuration evaluated
   on the out-of-sample data counts. That means every leaderboard row plus every cell of the
   reconnaissance grids in `docs/dataset/phase-7-recon-2026-09-19/` (rankings × frictions ×
   skeptic variants × thresholds × windows). The ledger listing them is committed, so the count can
   be checked.
3. **The gate** lives in engine 20. It reads the leaderboard and the run's report (spec 138) and
   writes `promoted` true only when the deflated metric clears the configured bar. Otherwise it
   writes a reason code, mapped in `REASON_PROSE` in the same change.
4. **The bar** is a lead config key with the operator's value. **RULING REQUIRED (R10):** none is
   proposed here.

## Scope Limits

- Promotion never changes which model the running system uses. `models.*_run_id` stays the
  operator's key, and invariant 4 is untouched.
- No model output feeds the gate's decision except through the returns it is judging.

## Check When Done

- A fabricated model whose raw Sharpe clears the bar but whose deflated metric does not, given the
  trial count, is rejected with its reason. The same model with a trial count of one is promoted.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
