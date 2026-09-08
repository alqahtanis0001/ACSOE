# 13 — `clients/store/seed.py`: the seeded database

**Owner:** B — Store and trading

## Goal

A queryable database of realistic fake data that the Phase 1 console renders and, critically,
that Phase 3 tests `safety` against — because every one of `safety`'s six inputs is written by
engine 19, which is Phase 4.

## Implementation

1. Create `src/acsoe/clients/store/seed.py` generating a full database from the migrated
   schema, deterministically from a config seed.
2. Produce realistic `trades`, `rejections` and `leaderboard` rows — enough variety that the
   console's cycle feed, history and empty state all have something honest to render.
3. Produce, as **named fixtures rather than incidental data**, the six things Phase 3 reads:
   - a run of consecutive `data_guard` `block_records` longer than
     `safety.max_consecutive_data_blocks`, spanning two `run_id`s so the `ts` ordering is
     actually exercised;
   - at least one open position;
   - at least one resting entry order;
   - an `equity_snapshots` series containing a drawdown past the configured limit;
   - a trailing run of losing `trades` past the loss-streak limit;
   - `block_records` rows with `status = 'ERROR'` inside the error-rate window.
4. Thresholds are **injected**, not read from config — the seed takes a `SeedThresholds`
   value so a Phase 3 test can pass whatever the config actually says. Generate each fixture
   as a **multiple** of the injected threshold rather than a fixed number: a drawdown of twice
   the limit, a losing streak of the limit plus three, an outage run of the block limit plus
   three. A fixture pinned to a constant silently stops overshooting the moment the operator
   sets a larger limit, and Phase 3 then fails for a reason that has nothing to do with the
   code under test.
5. Expose each fixture by name so a Phase 3 test asks for "the outage run" rather than
   rediscovering it by query.
6. Rejection reasons are written for the operator, not the log — the console renders them.
7. Add `tests/clients/store/test_seed.py` asserting every one of the six fixtures is present
   and past its threshold, and that seeding twice with the same seed produces the same database.

## Scope Limits

- Do **not** seed a `mode: live` state, a real API key, or a real account balance.
- Do **not** invent a schema column; if a fixture needs one, it goes through the lead.
- Do **not** make Phase 3 depend on incidental seed data — if Phase 3 reads it, it is a named
  fixture with a test asserting it exists.
- Do **not** write into `data/db/` during tests; use a temporary path.

## Check When Done

- `python scripts/verify.py --phase 0` reports `seed_fixtures_present` as PASS, with all six
  fixtures found.
- Seeding twice from the same seed is byte-identical.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
