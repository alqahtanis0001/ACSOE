# 104 — Engine 19 records an engine that errored

**Owner:** C — Interface and models

**Phase:** 6. Operator ruling 2026-09-16, invariant 12 and contract rule 7. Found by A's spec 87
rehearsal: `docs/build-log/phase-6/a-platform.md`, "an ERROR anywhere in the opportunity chain
leaves the tick unrecorded".

## Goal

A tick on which an opportunity-chain engine returned `ERROR` is recorded in full: a
`block_records` row for the errored engine, no `rejections` row, and positions, orders and equity
exactly as on any other tick. The code `engine_errored` renders as operator prose.

## Implementation

1. **Landed by the lead first:** `core/orchestrator.py` publishes `state["block_status"]`
   (`BLOCK` or `ERROR`) beside `trading_blocked_by` and `block_reason`, in both chains, absent on
   an unblocked tick. Read it; do not infer an error from an empty payload.
2. `src/acsoe/engines/memory/`: when `block_status` is `ERROR` and the blocker is not a guard
   (guard errors already arrive in `guard_blockers`), write one `block_records` row — `blocked_by`
   the engine's name, `status` `ERROR`, `block_reason` the new code `engine_errored`,
   `is_primary` true — and **no** rejection. Never read or require a `reason_code` for it. The
   code lives in `engines/memory/contracts.py`.
3. The rest of the tick is written regardless: engine 19 must not raise on this path, and the
   equity row must be present.
4. A `BLOCK` with no `reason_code` is a different fact — a gate breaking its contract — and keeps
   its current treatment. Name the two cases apart in a test.
5. `src/acsoe/console/format.py`: `engine_errored` in `REASON_PROSE` **in the same change**, so
   spec 99's walking test stays green.
6. Tests in `tests/engines/test_memory_rows.py`, one of them with the real orchestrator and a real
   raising engine (no double for `block_status`), and a mutation per clause, killing test named.
7. The build-log entry is written at diagnosis, before the change.

## Scope Limits

- Do not edit `core/`, `bootstrap.py`, any engine but 19, or the store schema — the existing
  `block_records` columns are sufficient.
- Do not change how guard-chain blockers are recorded.
- Do not write rejection rows for errors.

## Check When Done

- Under `m: engine 19 treats ERROR as a rejection`, the full-orchestrator test is red.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
