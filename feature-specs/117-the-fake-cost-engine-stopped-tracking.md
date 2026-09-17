# 117 — The fake cost engine publishes a field no real engine produces

**Owner:** C — Interface and models

**Phase:** 6. Found by B while removing `CostAssessment.fallbacks_used` (spec 111), reported rather
than edited: the file is C's. The operator's standing question applies — **what was that test
asserting?**

## Goal

`tests/verify/test_phase3_criteria.py`'s `CONSTANT_FEE_COST_ENGINE` publishes the shape engine 10
actually publishes, and `check_cost_gate_uses_live_fee_tier` is no longer blind to the difference.

## The finding

The double publishes `"fallbacks_used": []` (~line 227). Engine 10 no longer publishes that key at
all (spec 111), and the file stayed **48 passed before and after**, because the criterion reads only
`net_edge_pct`, `reason_code`, `clears_hurdle` and `hurdle_pct` — it never looks at the key set, so
an extra field in the double is inert. That is `code-standards.md`'s *double that stopped tracking
what it doubles*, caught at the moment it stopped.

## Implementation

1. Build-log entry first, including the answer to: **what was this double's `fallbacks_used`
   asserting, and had it ever been load-bearing?** (Check the history of the criterion, not only
   today's code.)
2. Remove the key from the double, or — if the criterion should care about the payload's shape —
   make it care, and say which you chose and why.
3. **Decide whether the criterion's blindness is worth closing**: it drives a *fabricated* cost
   engine, so a key-set assertion there tests the fabrication, not engine 10. If you conclude the
   right check lives in `tests/engines/test_cost.py` (B's pinned key set, spec 111) and not here,
   say so — that is a legitimate answer, and it is the finding, not a dodge.
4. Whatever you change, prove it: the file was green with the stale key, so a change that leaves it
   green has demonstrated nothing. Name what would now go red that did not before.

## Scope Limits

- `tests/verify/**` only, plus your records. Do not edit engine 10 or B's tests.
- Do not add a key-set assertion to a criterion merely to have one; justify it or leave it out.

## Check When Done

- `pytest tests/verify/test_phase3_criteria.py -q` green, and the named regression observed red.
- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/`
