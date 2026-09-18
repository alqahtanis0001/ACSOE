# 120 — Retire the operator prose that no longer has a producer

**Owner:** C — Interface and models

**Phase:** 6. Second half of the operator's 2026-09-16 ruling. **Runs only after spec 119 (B) has
landed**, because every code must stay mapped while the seeded rows still carry it.

## Goal

`REASON_PROSE` carries an entry for every code the system can emit and none that no producer can
reach, and a test keeps it that way from the map's side.

## Implementation

1. Build-log entry first.
2. With spec 119 landed, find every `REASON_PROSE` key that no engine and no seed row can now
   produce, and retire it. **Check the seed as well as the engines** — after 119 the seed emits
   only real codes, so the map's producers are exactly: the engines' `contracts.py` codes, plus
   any `hold_reason` values.
3. **The test spec 99 could not write.** Its walking test goes from engines to the map and proves
   no code is unmapped. Add the other direction — every mapped key has a producer — and say in the
   docstring why both directions are needed: one catches a silent "No reason was recorded.", the
   other catches prose describing a refusal the system cannot make.
4. Observe the new test red before retiring the entries.
5. If a key has no producer but reads like something that *should* exist, that is a finding, not a
   deletion: report it rather than quietly removing it.

## Scope Limits

- `src/acsoe/console/format.py`, `tests/console/**`, C's records. Do not edit the seed, any engine,
  or B's tests.

## Check When Done

- Both directions of the walk are asserted, and the new one observed red before the retirement.
- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
