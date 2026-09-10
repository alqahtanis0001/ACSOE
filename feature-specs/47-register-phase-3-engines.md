# 47 — Register engines 7, 10, 11 and 17

**Owner:** Lead

**Phase:** 3 — Economics. **This lands last**, after specs 40 to 44 are green.

## Goal

`bootstrap.py` carries the four Phase 3 engines in registry order, and the daemon runs them.

## Implementation

1. Add to `src/acsoe/bootstrap.py`, in the order the registry table in
   `context/engine-contracts.md` fixes:
   - `GUARD_CHAIN` — `SafetyEngine` **last**, after `DataGuardEngine`. Engine 17 is a
     gatekeeper on the account, not a judgement about a candidate, and it must run on every
     tick in every mode. It comes last because it reads the current tick's
     `state["trading_blocked_by"]`, which `data_guard` sets.
   - `OPPORTUNITY_CHAIN` — `ScoutEngine`, then `CostEngine`, then `RiskEngine`. Engines 5, 6,
     12, 13, 8 and 9 do not exist yet; the chain is 7, 10, 11 until they do, and the
     orchestrator skips an unregistered engine by design.
2. All four carry `is_gate = True`. `is_gate_matches_registry` asserts each against the
   registry table's Gate column and will catch a gate registered as an ordinary engine.
3. **Registration was deferred in Phase 2 for a stated reason, and the reason is now the
   check.** `safety` in the guard chain runs on every tick of `orchestrator_empty_registry`
   (Phase 0) and `commands_round_trip` (Phase 2), both against a real `StoreClient` on an
   empty database. Nothing should trip — and "should" was doing the work in that sentence.
   Re-run **all four phase gates** after registering, and treat any change in Phase 0, 1 or
   2 as a finding to have in isolation rather than a thing to absorb.
4. Update the `bootstrap.py` module docstring: which engines are registered, which are not,
   and why the chain is not yet in full registry order.

## Scope Limits

- Do **not** register engines 5, 6, 8, 9, 12, 13, 14, 15, 16, 18, 19, 21 or 22. They do not
  exist and an unregistered engine is skipped by design.
- Do **not** register 20 or 23. They are `OFFLINE_CHAIN`, assembled in `cli/research.py`, and
  `bootstrap.py` importing from `research/` breaks architecture invariant 5.
- Do **not** reorder, add to, or remove from the registry table in `engine-contracts.md`.
- Do **not** register before specs 40 to 44 are green. A half-wired gate in the live chain
  turns every other criterion's failures into a puzzle.

## Check When Done

- `python scripts/verify.py --phase 3` and `--phase 0`, `--phase 1`, `--phase 2` all re-run,
  with the real output pasted into `docs/build-log/phase-3.md`. Phases 0 to 2 unchanged.
- `is_gate_matches_registry` PASSes with all four new engines present.
- A daemon tick with the registered chains completes and records, on an empty database and
  on the seeded one.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
