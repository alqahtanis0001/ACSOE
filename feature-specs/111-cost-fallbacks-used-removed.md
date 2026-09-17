# 111 — `CostAssessment.fallbacks_used` removed

**Owner:** B — Store and trading

**Phase:** 6. Operator ruling 2026-09-17 on open question Q1
(`docs/build-log/phase-6/overnight-decisions-2026-09-17.md`).

## Goal

Engine 10's payload no longer carries `fallbacks_used`: a field that is always empty, that nothing
produces a value for and nothing reads, and that reads as "no fallback fired" on a record that
cannot record one. Engine 22's `fallbacks_used` stays — it carries a real value.

## Implementation

1. Build-log entry first.
2. `src/acsoe/engines/cost/{contracts,engine}.py` and `README.md`: remove the field, `_fallbacks`
   if it has no other use, and the prose about it; say why in the README in one paragraph.
3. `tests/engines/test_cost.py`: the assertion that it is `[]` becomes an assertion that the key is
   absent, and the published key set is pinned.
4. **Before and after**, run `tests/verify/test_phase3_criteria.py`. Its fake cost engine (C's
   file, around line 227) publishes `"fallbacks_used": []`. **If that test goes red, do not edit
   it** — report to the lead with the failure; C will first establish what that test was
   asserting (a fake publishing a field no real engine produces may mean it was passing against a
   shape the real engines never had) before anything is made green.
5. A mutation that re-adds the field to the payload, killed by the key-set test.

## Scope Limits

- Engine 10 only; no behaviour change to the cost gate. Do not touch engine 22 or other lanes.

## Check When Done

- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
