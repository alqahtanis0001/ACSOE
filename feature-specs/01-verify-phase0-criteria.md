# 01 — Phase 0 criteria in `scripts/verify.py`

**Owner:** C — Interface and models

## Goal

The six Phase 0 exit criteria from `context/ai-workflow-rules.md` exist as named, executable
checks, reporting PENDING until the thing each judges is built.

## Implementation

1. In `scripts/verify.py`, register the Phase 0 criteria:
   - `orchestrator_empty_registry` — builds an `EngineContext` and runs one tick against an
     empty registry, asserting it completes without raising and that an empty chain is valid.
   - `db_migrates_from_empty` — applies `db/migrations/` to a temporary database file and
     asserts the schema matches the expected table set.
   - `seed_fixtures_present` — opens the seeded database and asserts every fixture Phase 3
     will test `safety` against: trades, rejections, a `block_records` run of consecutive
     `data_guard` ticks longer than `safety.max_consecutive_data_blocks`, at least one open
     position, at least one resting entry order, an `equity_snapshots` series with a
     drawdown past the configured limit, and a trailing losing-trade streak past the limit.
   - `record_sample_valid` — parses `tests/fixtures/record_sample.jsonl` and validates every
     line against the recorder schema.
   - `toolchain_green` — runs `pytest -q`, `mypy --strict src/` and `ruff check src/` as
     subprocesses and reports their combined result.
   - `is_gate_matches_registry` — asserts every registered engine's `is_gate` matches the
     Gate column of the registry table in `context/engine-contracts.md`, including the
     offline-chain engines assembled in `cli/research.py`. PENDING while no engine exists.
2. Each criterion reports PENDING, not FAIL, when its subject does not exist yet: no
   `bootstrap.py`, no `db/migrations/`, no seeded database, no fixture file.
3. The temporary database goes in a pytest `tmp_path` or the system temp directory — never
   in `data/`.
4. Add `tests/verify/test_phase0_criteria.py` proving each criterion returns PENDING on an
   empty tree and PASS against a minimal fabricated subject.

## Scope Limits

- Do **not** build the things being checked. Every subject here belongs to A, B or the lead.
- Do **not** read the real `data/db/acsoe.sqlite`; the seeded database path comes from config.
- Do **not** weaken a criterion to make it pass. A criterion that cannot be expressed as a
  check is badly written and gets raised with the lead, not skipped.
- Do **not** add criteria for later phases.

## Check When Done

- On the current tree, `python scripts/verify.py --phase 0` reports all six as PENDING and
  exits zero.
- Each criterion flips to PASS against a fabricated minimal subject in its unit test.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
