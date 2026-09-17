# 107 — Engine 9's stale fallback prose; spec 105's criterion requires a stored mark

**Owner:** C — Interface and models

**Phase:** 6. Follow-ups from spec 106 (B's report, 2026-09-17). Lead decision D3 in
`docs/build-log/phase-6/overnight-decisions-2026-09-17.md`.

## Goal

Engine 9's documentation no longer describes a fallback engine 11 no longer has, and
`paper_equity_continuous_across_fill` no longer accepts a fill-tick position with no stored
mark, since spec 106 makes engine 21 store one.

## Implementation

1. `src/acsoe/engines/order_book/README.md` ("One deliberate asymmetry with engine 11") and
   the `_basis_notional` docstring in `src/acsoe/engines/order_book/engine.py`: rewrite so
   they state engine 9's own rule (no balance, no estimate) without describing engine 11 as
   substituting one. Invariant 2 is the authority; point at it rather than restating it.
2. `scripts/verify.py`, `_judge_fill`: a fill-tick `positions` row with `last_price` NULL is a
   FAIL naming the missing mark; the mark-to-bid term is computed from the stored mark only.
   Do not widen or remove any other part of the bound.
3. `tests/verify/test_phase6_criteria.py`: a test that goes red if the criterion accepts a
   NULL mark — produced in the copied tree by making engine 21 store `last_price` NULL again
   (B's mutant P1), which the criterion did not catch before this spec.
4. Mutations from byte copies, killing test named; build-log entry at diagnosis.

## Scope Limits

- Do not edit engines 9's behaviour, engine 21, or anything outside C's lane.
- Do not change the criterion's tolerance other than removing the NULL-mark acceptance.

## Check When Done

- B's mutant P1 is red on the criterion's test.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
