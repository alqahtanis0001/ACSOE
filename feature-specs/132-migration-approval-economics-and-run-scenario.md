# 132 — Migration 0006: why a trade was approved, and which scenario priced it

**Owner:** B — Store and trading

**Phase:** 7. Phase 7 prerequisite 7 (F-new-1). The schema half; C's engine 19 half is spec 133,
and the lead's `runs` write is spec 134.

## Goal

Two things become recordable:

- **Why a trade was approved.** A `trades` row can hold the economics of its approval (expected
  move, friction, net edge and hurdle), which today exist only on `rejections`.
- **Which scenario priced a run.** A `runs` row can hold the replay scenario's identity.

## Implementation

1. `db/migrations/0006_*.sql`, forward-only:
   - On `trades`, add `expected_move_pct`, `friction_pct`, `net_edge_pct` and `hurdle_pct` as exact
     decimal TEXT, nullable. Rows written before this migration have none, and **absent is never
     zero**.
   - Also add the three model run ids the approving tick used.
   - On `runs`, add `scenario_digest` (TEXT, nullable; null for paper and live runs) and
     `scenario_description` (TEXT).
2. Store client and contracts: the row models gain the fields, typed `Money`-style for the four
   economics, and readers return them.
3. The migration test proves that a database holding pre-0006 rows migrates, that those rows read
   the new fields as absent, and that a float is refused at the boundary.

## Scope Limits

- No change to `rejections`' existing columns.
- No inference: nothing backfills the new columns from `rejections`. The two tables mean different
  things.
- `cycle_id` on `orders` and `positions` is not changed here. Prerequisite 8 is a fact every join
  carries, and spec 138 carries it.

## Check When Done

- Migrate-from-empty and migrate-from-seed both green.
- Each new field is observed round-tripping exactly, and a float is observed refused.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
