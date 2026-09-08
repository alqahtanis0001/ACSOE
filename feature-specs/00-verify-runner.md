# 00 — `scripts/verify.py`: runner and criterion framework

**Owner:** C — Interface and models

## Goal

An executable phase gate exists. `python scripts/verify.py --phase N` runs that phase's
named criteria and prints PASS, FAIL or PENDING for each. Nothing else in Phase 0 can be
reported complete until this runs, because it is the thing that decides what "complete"
means.

## Implementation

1. Create `scripts/verify.py` as a standalone script. It may import from `src/acsoe/` and
   from `src/acsoe/research/` — it is neither the live loop nor research code, per
   architecture invariant 5 — but it must not require either to exist.
2. Define a criterion as a named callable returning one of three results and a one-line
   message. PASS = checked and satisfied. FAIL = checked and not satisfied. PENDING = the
   thing it checks does not exist yet.
3. Register criteria per phase, 0 to 8. `--phase N` runs phase N's set.
4. Print one line per criterion: result, name, message. Print a summary line with counts.
5. Exit non-zero if any criterion is FAIL. Exit zero when there are no FAILs, even with
   PENDINGs — mid-phase the bar is no FAIL, and PENDING only has to reach zero at phase
   close. The phase-close judgement is the lead's, from the printed counts.
6. Add `--live`, opt-in, enabling criteria that need the network or an API key. Never
   required for a phase to be green.
7. Every criterion that is not behind `--live` must run offline, with no API key, and
   **pass on a fresh clone**. `data/`, `models/` and `logs/` are gitignored, so no
   criterion may read anything inside them.
8. Create `tests/verify/test_runner.py` covering result precedence, exit codes, and that a
   criterion raising an exception is reported FAIL rather than crashing the run.

## Scope Limits

- Do **not** implement the Phase 0 criteria here. That is spec 01.
- Do **not** implement `docs_vocabulary` here. That is spec 02.
- Do **not** register criteria for phases 1 to 8. Later phases add their own.
- Do **not** make any criterion depend on `data/`, `logs/`, `models/`, or on a live network.
- Do **not** import `bootstrap.py` at module import time; a missing registry must report
  PENDING, not raise.

## Check When Done

- `python scripts/verify.py --phase 0` runs and prints a per-criterion table with no
  traceback, on a checkout where `src/acsoe/` does not yet exist.
- `--live` is accepted and changes which criteria run.
- A deliberately failing criterion produces a non-zero exit; a PENDING one does not.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
