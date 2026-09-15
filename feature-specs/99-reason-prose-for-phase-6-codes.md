# 99 — Operator prose for every Phase 6 code, and a test that finds the next missing one

**Owner:** C — Interface and models

**Phase:** 6. `console/format.py` and `tests/console/` are C's.

## Goal

A code absent from `REASON_PROSE` renders "No reason was recorded." silently, with no error
anywhere. Phase 6 adds codes from engines 9, 14, 11 (spec 89), 18, 21 and 22, and none of 9, 14,
18, 21, 22 is a gate, so the existing enumeration — which walks gates — cannot see them. At the end
of this spec every code has prose, and a test walks **every** engine's published codes so the next
one missing goes red instead of silent.

## Implementation

1. One `REASON_PROSE` entry per code, written for the operator: what happened and, for a
   fail-closed shape, what to do. Codes arrive from B and from C's own engines by message; the list
   is closed when specs 89, 91, 92, 93, 96 and 97 have landed their `contracts.py`.
2. `hold_reason` values from engine 21 are rendered through the same map: the console shows why the
   manage chain held.
3. `tests/console/test_reason_prose.py`: a test that imports every `acsoe.engines.*.contracts`
   module, collects every module-level `Final` string constant whose name begins `REASON_` or
   `HOLD_`, and asserts each value is a key of `REASON_PROSE`. **It must be shown to fail**: add a
   `REASON_` constant to a scratch copy of one contracts module, observe red naming it, restore
   from the byte copy with the hash compared.
4. The inverse, as a warning list rather than a failure: prose keys no engine publishes, so a
   retired code is noticed.
5. Walk the naming across engines before writing the test: if an engine publishes codes under
   another naming convention, the test must still see them — bring the convention to the lead
   rather than exempting the engine.

## Scope Limits

- Do **not** edit another agent's `contracts.py` to fit the test's naming. Escalate a mismatch.
- Do **not** render a bare code on screen as a fallback.

## Check When Done

- The walking test observed red on an unmapped scratch constant, restored by hash.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
