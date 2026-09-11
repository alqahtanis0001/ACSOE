# 58 — Register engine 19, and the one config key Phase 4 adds

**Owner:** Lead

**Phase:** 4. `bootstrap.py`, `core/` and `config/default.yaml` are lead-only.

## Goal

Engine 19 `memory` joins the manage chain, and `backtest.embargo_bars` exists.

## Implementation

0. **The two-halves dance, spec 38's pattern, because `extra="forbid"` makes it mandatory.**
   A adds `embargo_bars` to `BacktestConfig` in `platform/config.py` as **optional at load**
   and messages the lead; the lead then pastes the YAML block; A then tightens the field to
   required. Whichever half lands alone breaks every test in the tree that loads the committed
   config — the lead tried the YAML first on 2026-09-11 and reverted it within the minute.
1. Add `backtest.embargo_bars` to `config/default.yaml`. **Lead-chosen and provisional**, like
   `market_sensor.published_bars` and `kraken.cache_ttl_s`, and flagged to the operator in the
   phase report. The default is `48`, one full label horizon: the purge already removes every
   literally overlapping window, and the embargo exists for the serial correlation that
   survives the purge, so a span equal to the horizon is the defensible starting value rather
   than a number chosen for its shape. Invariant 10 requires the embargo; it does not name its
   length, and nothing in the repository did.
2. Register `MemoryEngine` in `MANAGE_CHAIN` in `bootstrap.py`, at the end, after 21 and 22 —
   registry order, and the order matters: engine 19 records what 21 and 22 did on this tick.
   21 and 22 are Phase 6 and stay absent, so the chain is registry order with holes, exactly
   as the opportunity chain has been since Phase 3.
3. **Hold registration until engine 19 has been driven through two real orchestrator ticks.**
   Two, not one: `state` is fresh every tick except `state["system"]`, so an engine quietly
   depending on something surviving passes a single-tick test and fails the second. Phase 2
   and Phase 3 both did this and both times it turned registration from a discovery into a
   formality.
4. Record the rulings this phase made in the authority documents, in the same change as the
   code that depends on them: the two labelling rulings from spec 52 and the ownership
   assignment from spec 55. Then run the propagation procedure in `ai-workflow-rules.md` —
   grep for the claim each new rule contradicts, not for the new rule.

## Scope Limits

- Do **not** register engines 20, 21, 22 or 23 in `bootstrap.py`. 23 is the offline chain and
  never appears there at all.
- Do **not** add a second config key. If Phase 4 needs one, it is a finding to report, not a
  value to invent.
- Do **not** close the phase, consolidate the build logs, or mark the tracker green.

## Check When Done

- `is_gate_matches_registry` reports engine 19 registered and not a gate.
- `python scripts/verify.py --phase 4` runs with engine 19 in the manage chain.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
