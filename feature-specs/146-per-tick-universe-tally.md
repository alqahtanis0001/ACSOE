# 146 — The per-tick universe tally and the ranking on every bar

**Owner:** B (migration 0007 and the store surface); C (engine 19 writes it).

**Phase:** 7. Operator ruling 2026-09-19 (Q8): the funnel section of `phase-7-findings.md` must be
fillable from stored data, and it is not. Built before the launch, after spec 145 and 140's SHAP
writer, each through its own gate, one change at a time through engine 19.

## Goal

Every tick on which engine 7 `scout` ran records, in one row, the whole universe step of the
funnel: how many pairs were scanned, how many entered the tradable universe, how many were
excluded and why, how many the ranking skipped and why, the full ranked order, and what engine 7
decided. That includes the ticks where it produced **no candidate**, which today leave no row at
all. So the funnel counts from bars down to the candidate come from rows, not from arithmetic on
absences.

## Implementation

1. **B, `db/migrations/0007_tick_tallies.sql`**, forward-only: a table `scout_tallies` with
   `run_id`, `cycle_id`, `ts`, `bar_ts`, `scanned`, `entered`, `excluded` (JSON reason → count),
   `rank_skipped` (JSON reason → count, or the list engine 7 publishes), `ranked` (JSON, the full
   ordered list with each expected move exactly as published), `candidate` (the chosen pair, or
   NULL), `status` (engine 7's status), `reason_code` (NULL when none) and `updated_at`. Unique on
   `(run_id, cycle_id)`. Store `write_scout_tally` (write-once) and `scout_tallies(run_id)`. The
   documented-tables list and `architecture-context.md` gain the table in the same boundary
   (the lead writes the context row; C the `DOCUMENTED_TABLES` line).
2. **C, engine 19:** on every tick where `state["scout"]` is present and engine 7 did not error,
   write one row from engine 7's published payload, **verbatim**. Nothing is recomputed, and a
   field engine 7 did not publish is NULL, never zero. An errored engine 7 writes no tally (its
   block record already exists).
3. `scanned == entered + sum(excluded)` is asserted on the written row, as engine 7 already
   asserts it on its payload.

## Scope Limits

- **No engine publishes anything new.** Engine 7's payload already carries every field; this spec
  only stores it.
- No change to what any gate decides, or to the chain.
- Not a rejection: a tally is a tick-level fact and never goes into `rejections`, whose rows mean
  one refused candidate (invariant 12).

## Check When Done

- On the rehearsal harness, every tick where engine 7 ran has exactly one tally row, including
  no-candidate ticks, and each row equals engine 7's published payload, recomputed from `state`
  and not read back.
- Mutations: skip no-candidate ticks; record `ranked` only when a candidate exists; null-fill as
  zero. Each is killed.
- Migrate-from-empty and migrate-from-0006 both green.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
