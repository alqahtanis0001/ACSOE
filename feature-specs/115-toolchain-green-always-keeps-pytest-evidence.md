# 115 — `toolchain_green` keeps the pytest output and count on a PASS too

**Owner:** C — Interface and models

**Phase:** 6. Operator ruling 2026-09-17: the lead's gate drops its separate `pytest` run and relies
on `verify.py`'s `toolchain_green`, which runs the identical command.

## Goal

When pytest passes, `toolchain_green` still writes the complete captured output to
`logs/verify/toolchain_green/` and puts pytest's summary line (`N passed, M skipped …`) in its PASS
message, so the number of tests that ran is on record at every boundary — the one thing the
lead's separate pytest run provided that the wrapper did not.

## Implementation

1. `scripts/verify.py`, `check_toolchain_green`: on returncode 0, write the evidence file for
   pytest as for a failure, and include pytest's final summary line in the PASS message.
2. Test: on a fabricated tree whose suite passes, the PASS message contains the summary line and
   the evidence file exists; mutation (no evidence on PASS) killed.
3. Build-log entry.

## Scope Limits

- No change to the retry, the timeout, the exit-code classification or what counts as a crash.
- Do not change the TOOLCHAIN commands.

## Check When Done

- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
