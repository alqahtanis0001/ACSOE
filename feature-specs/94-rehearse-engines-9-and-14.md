# 94 — Rehearse engines 9 and 14 through real orchestrator ticks

**Owner:** B — Store and trading

**Phase:** 6. `tests/engines/test_feature_chain_rehearsal.py`, B's rehearsal file since Phase 5 —
the orchestrator wiring, not C's engines.

## Goal

Before the lead registers 9 and 14 (spec 82), an agent that did not build them drives the chain
5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15 through real ticks, and the Phase 5 assertion that the tick
stops at `cost` for want of engine 9 is replaced by one that reaches engine 15.

## Implementation

1. Extend the file's full-registry scenario to include 9 and 14 in their registry positions, bar
   tick then quiet tick, against the fake client at tier 3 with a book whose walk is known.
2. Assert engine 10 reads engine 9's `estimated_slippage_pct` by recomputing friction from the
   published parts, not by reading engine 10's total back.
3. Assert engine 15 now runs on the bar tick and is absent on the quiet tick.
4. Assert engine 14 publishes on the bar tick with the leaderboard fixture loaded into the store,
   and that nothing engine 14 publishes changes whether 15 blocks (invariant 4).
5. Delete the Phase 5 assertion that `skeptic` never appears in the full chain, and record the
   deletion and why in the build log — it was true of a chain that no longer exists.
6. Mutations, killing test named: engine 9's slippage key renamed; engine 14 publishing a weight
   that engine 15's decision reads. **If red for a real reason, do not fix engines 9 or 14** —
   report to C and the lead.

## Scope Limits

- Do **not** edit engines 9, 14, 10 or 15, `bootstrap.py` or `core/`.
- Do **not** register anything.

## Check When Done

- Every scenario green on C's final code, every mutation red with its killing test named.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
