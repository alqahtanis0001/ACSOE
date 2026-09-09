# 31 — Persisted system mode: schema and store access

**Owner:** B — Store and trading

## Goal

Somewhere in the database for the daemon to record the system mode it is actually in, so the
console can stop reading `Idle` over a running system. Deferred from Phase 1 by the operator, with
the approach already fixed.

## Implementation

1. Add a forward-only migration under `db/migrations/` carrying the current system mode. Two
   shapes are viable — a column on the current `runs` row, or a small single-row state table —
   and the choice is yours to make and to record in your build log with the reasoning. Whichever
   you pick, it must be readable by `run_id`, so the console can tell *this* run's mode from a
   previous one's.
2. Add the matching read and write to `src/acsoe/clients/store/client.py` and the row model to
   `src/acsoe/clients/store/contracts.py`.
3. **The writer is the command reader in `src/acsoe/core/orchestrator.py`, which is lead-only.**
   You provide the method; the lead calls it. Do not write into `core/`.
4. The reader is C's console, spec 32. Land `contracts.py` first so C can mock against it and
   neither of you waits.
5. **Mode is still never restored from the store.** A daemon always starts `idle` and only reaches
   `running` through an `activate` command. This value is written *for the console to read*, not
   for the daemon to resume from, and nothing in this spec may read it back into `state`.
6. Migrations are forward-only and re-running them is a no-op. `db_migrates_from_empty` asserts the
   documented table set, so **if this adds a table, tell the lead** — the criterion and
   `architecture-context.md`'s storage table both need updating, and that is a lead edit.

## Scope Limits

- Do **not** write into `src/acsoe/core/`, `bootstrap.py`, or `src/acsoe/console/`.
- Do **not** make the daemon restore its mode from this value. That would invert the safety
  property that a crashed daemon comes back not trading.
- Do **not** alter any existing column or table. Forward-only, additive.
- Do **not** update `architecture-context.md` or `scripts/verify.py` yourself — raise both with
  the lead.
- Do **not** seed a mode into `seed.py` that would let C's console test pass without a daemon ever
  writing one.

## Check When Done

- The migration applies from empty and re-applying is a no-op.
- The write-then-read round trip returns the mode for the right `run_id`, and a different run's
  mode does not leak into it.
- `db_migrates_from_empty` still passes, and `seed_fixtures_present` still passes.
- Phase 0 and Phase 1 both still report green — a mid-phase migration must not break anyone's
  fixtures.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
