# 108 — Stale fallback remnants in B's lane

**Owner:** B — Store and trading

**Phase:** 6. Follow-ups from spec 106 (B's own report and the lead's review, 2026-09-17).

## Goal

Nothing in B's lane describes a paper-mode fallback that no longer exists, or a column that
is not where it says.

## Implementation

0. **First, before anything else:** write the spec 106 mutation-sweep build-log entry (draft
   at `scratchpad/b106/entry3.md`, if it still exists; otherwise from your spec 106 report
   and `logs/verify/b106-*`) into `docs/build-log/phase-6/b-store.md`, with the wide R0/P0
   results, and mark spec 106 DONE in `context/progress/b-store.md`.
1. `src/acsoe/engines/cost/contracts.py` and the cost `README.md`: `fallbacks_used` is a
   `trades` column (migration 0001), not a `rejections` one. Correct the prose; decide from
   the code whether `CostAssessment.fallbacks_used` still has a reader, and report it — do
   not remove a field another lane reads.
2. `src/acsoe/clients/paper/broker.py`: `FALLBACK_PAPER_LEDGER` is exported and unused —
   confirm by grep across `src/`, `tests/` and `scripts/`, then remove it; rewrite the comment
   calling the starting balance "invariant 2's one substituted value" to match invariant 2 as
   now written (the broker is the authority; no fallback).
3. If any other remnant of the removed fallback turns up in B's lane, fix it in the same
   change and list it.
4. `src/acsoe/engines/cost/engine.py` is CRLF in the working tree and is yours: convert it to
   LF in this spec, **after** confirming no `tests/verify/` patcher anchor on that file spans
   a line break, and re-run `tests/verify/test_phase3_criteria.py` to prove the anchors still
   match exactly once.

## Scope Limits

- No behaviour change to any engine or the broker. Comments, one unused constant, line
  endings.
- Do not edit other lanes.

## Check When Done

- `grep -rn FALLBACK_PAPER_LEDGER src tests scripts` finds nothing.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
