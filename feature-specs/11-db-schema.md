# 11 — SQLite schema and forward-only migrations

**Owner:** B — Store and trading

## Goal

A fresh database migrates from empty to the full Phase 0 schema, including every table the
console renders and every table engine 17 `safety` reads.

## Implementation

1. Create `db/migrations/` with a forward-only, numbered migration runner. No down-migrations.
2. Define the tables named in the storage model of `context/architecture-context.md`:
   `trades`, `rejections`, `runs`, `leaderboard`, `positions`, `orders`, `equity_snapshots`,
   `block_records`, `commands`.
3. `commands` carries `claimed_at` and `consumed_at` for two-phase consumption, plus the
   command name and its audit fields.
4. `block_records` carries `cycle_id`, `run_id`, `ts`, `blocked_by`, `block_reason`,
   `is_primary` and `status` — one row per guard blocker per tick.
5. **Exactly one row per `cycle_id` may carry `is_primary`, enforced by the database.** Add a
   partial unique index on `(cycle_id)` where `is_primary` is true. Two primaries on one tick
   would mean two engines each claiming to be the one that gated the opportunity chain, and
   the audit trail could no longer say which block stopped the pipeline. A second insert must
   fail loudly at the database, not be resolved by whichever write happened to land last. Add
   a test that a second primary insert for the same `cycle_id` raises.
6. `equity_snapshots` carries `cycle_id`, `run_id`, `ts`, `equity`, `peak_equity`, and the
   cash and unrealised components the Phase 7 alpha curve needs.
7. `orders` is keyed by `userref` so idempotency checks are a lookup, not a scan.
8. **Money columns are exact decimal strings in TEXT, never `REAL`.** Index what the hot reads
   need: `block_records` by `ts`, `orders` by `userref` and `status`, `positions` by `status`.
9. Add `tests/db/test_migrations.py`: a fresh file migrates from empty; migrating twice is a
   no-op; the resulting table and index set matches expectations.

## Scope Limits

- Do **not** write the store client here; spec 12 owns it.
- Do **not** seed data here; spec 13 owns it.
- Do **not** store money as `REAL` anywhere, in any table.
- Do **not** change the schema after another agent has built fixtures against it without
  going through the lead.
- Do **not** put large arrays in SQLite.

## Check When Done

- `python scripts/verify.py --phase 0` reports `db_migrates_from_empty` as PASS.
- Re-running migrations on a migrated database changes nothing.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
