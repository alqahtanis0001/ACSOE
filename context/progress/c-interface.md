# Progress — c-interface

Your file. Only you write here. The lead merges into `context/progress-tracker.md`.
Never edit the tracker directly.

## Current Task

- **Claimed: specs 00, 01, 02, 14, 15.** All five are finished. Built in that order —
  `scripts/verify.py` first, because nothing else in Phase 0 could be reported complete
  until it ran.

## Completed

- **Spec 00 — `scripts/verify.py` runner and criterion framework.** `--phase N`, the three
  results (PASS / FAIL / PENDING), `VerifyContext` carrying `root` as a parameter rather than
  a module constant, and `root_import_path()` so a unit test can point a criterion at a
  fabricated tree without poisoning the interpreter for the criterion that runs next.
- **Spec 01 — the Phase 0 criteria.** Seven registered for phase 0, each proved twice: PENDING
  against a tree where its subject does not exist, and PASS against a minimal fabricated
  subject, plus a third red direction wherever the criterion has a real failure mode.
- **Spec 02 — `docs_vocabulary`,** registered for every phase. The retired-term table is
  parsed out of `ai-workflow-rules.md`, never hardcoded, so adding a row extends the check.
- **Spec 14 — test harness,** `tests/conftest.py`, `tests/fixtures/` structure, network guard
  with its negative test.
- **Spec 15 — fake Kraken client.**

## In Progress

- Nothing.

## Blocked On

- Nothing.

## Open Questions — both resolved

- **Config key names for the `safety` thresholds.** The lead fixed the names and the operator
  supplied the values on 2026-09-08. `seed_fixtures_present` reads them and asserts the seed is
  past each one; it no longer reports PENDING on a missing key.
- **`docs_vocabulary` FAILing on a legitimate sentence.** The bare term `eight` retired the word
  everywhere, including `progress-tracker.md:76` where it counted config values, not engines. I
  did not edit the context file to make my own check pass — spec 02 forbids it — and sent it to
  the lead with both readings. **The lead fixed the class, not the instance:** the retired-term
  table gained a qualifier column, and the row now reads ``eight`` qualified by `machine
  learning`, `non-ML` or `engines`. The parser reads that column as data, so no term-specific
  rule entered the checker.

## Escalations To Lead — both resolved

- **No YAML library in the architecture stack table.** Resolved: `pyyaml` was added to the table.
- **Entry-point shapes in `core/`, `bootstrap.py` and `cli/research.py`.** Resolved: the lead and
  A agreed the surface I proposed — module-level `GUARD_CHAIN`, `OPPORTUNITY_CHAIN`,
  `MANAGE_CHAIN`, an `Orchestrator` with a single-tick method, and `OFFLINE_CHAIN` in
  `cli/research.py`. Both criteria now report PASS against the real code.

## Known issues in my code — open

1. **`toolchain_green` is not deterministic.** It fails on roughly 30% of runs (measured: 6 of
   20) because the pytest subprocess dies of a native memory fault, always inside B's seed write
   path at pydantic `model_dump`. Every test passes when the process survives. **Not root-caused.**
   Ruled out: pyarrow, `pytest-asyncio`, test ordering, and my own `root_import_path` — that
   swapper does create a second `PositionRow` class while instances of the first are live, but 40
   enter/exit cycles hammering `model_dump` across both do not crash, and `test_seed.py` alone
   still fails 1 in 15 without ever touching it. Next step is pinning a different pydantic-core.
2. **The criterion could not tell a crash from a verdict, and now can.** It compared a returncode
   against zero, so a process that printed `520 passed` and then died read exactly like a failing
   suite — which is how a memory fault gets filed as a flaky test and re-run until it goes green.
   `describe_exit()` now classifies each tool's returncode against that tool's own documented
   range (pytest 0-5, mypy and ruff 0-2), names the Windows NTSTATUS or POSIX signal, quotes the
   summary line the run had already printed, and prefixes the criterion's one line with `CRASH -`.
   Four tests cover both directions.
3. **The gate lints and type-checks `src/` only.** `mypy --strict scripts/` reports 2 errors in
   `verify.py` itself — `candidate` is bound to a `Path` in one loop and a `str` in the next, at
   the top of `_interpreter_with_toolchain` — and `ruff check tests/` reports 2 violations
   (`UP031` in `tests/core/test_contracts.py`, `SIM300` in `tests/db/test_migrations.py`). None
   is reachable by the gate that implements them. Widening `TOOLCHAIN` to cover `scripts/` and
   `tests/` is a change to what the phase gate asserts, so it is the lead's call, not mine.
4. **Two stale docstrings of mine, fixed.** A flagged both. `tests/conftest.py`'s `paper_config`
   still said the OPERATOR REQUIRED nulls were left as nulls; the file now carries none, all nine
   supplied. `verify.py`'s `KEY_MAX` comment said four of the five `safety` keys were written as
   null — it was three, and the same sentence wrongly implied only the error-rate window was ever
   a real value when `max_consecutive_data_blocks` was 15 from the start.

## Verification

Paste the real output of your last run. Never report a task complete without it.

```
$ pytest tests/ -q
524 passed in 12.88s

$ mypy --strict src/
Success: no issues found in 29 source files

$ ruff check src/
All checks passed!

$ python scripts/verify.py --phase 0
PASS    docs_vocabulary              14 files scanned, 9 retired terms, no hit
PASS    orchestrator_empty_registry  one tick completed against 0 registered engines; empty chains are valid, state["system"]["mode"]='idle'
PASS    db_migrates_from_empty       fresh database migrated to all 9 documented tables
PASS    seed_fixtures_present        all six fixtures present: outage run 18 ticks over 2 run_ids (11 double-blocker), 2 open position(s), 2 resting order(s), drawdown 0.2000017843760037115020877199, losing streak 8, 23 ERROR blocks in the window, 33 trades / 46 rejections
PASS    record_sample_valid          25 lines valid against the recorder schema; kinds present: gap, session, tick
PASS    toolchain_green              pytest, mypy --strict and ruff all green (python.exe)
PASS    is_gate_matches_registry     0 engines registered; 0 mismatches

7 criteria: 7 PASS, 0 FAIL, 0 PENDING
```

**That run is one sample, not the state of the phase.** `toolchain_green` fails about 3 runs in
10; see known issue 1. Phase 0 is not green until that is settled.

## Notes For Next Session

- Recorder line schema received from A and pinned: seven outer keys, `kind` in
  `{tick, gap, session}`, `_recorder` channel on markers.
- Do not generate Python through a shell heredoc on this machine. Backslashes in the body are
  not literal even with a quoted delimiter: a `\b` written into a regex arrived as a raw
  backspace byte, and `\n` inside a test string arrived as a real newline and broke the file.
  Use a direct file write for anything containing escapes.
