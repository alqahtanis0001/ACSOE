# Agent B — Store and trading

## Claimed

- **Spec 11** — `db/migrations/`, SQLite schema and forward-only migration runner. *Complete.*
- **Spec 12** — `src/acsoe/clients/store/`, store client and contracts. *Complete.*
- **Spec 13** — `src/acsoe/clients/store/seed.py`, seed generator. *Complete.*

## Status

All three are built, and both criteria that judge them report PASS:

- `db_migrates_from_empty` — a fresh database migrates to all 9 documented tables; a second
  `migrate()` returns `[]`, so "re-migrating is a no-op" is checked on the returned list
  rather than on a schema diff.
- `seed_fixtures_present` — all six Phase 3 fixtures present, each overshooting its threshold
  rather than sitting on it.

Nothing of mine is outstanding. Spec 11 unblocked 12, which unblocked 13, in that order.

## Open questions — both resolved

### 1. `is_primary` uniqueness scoped by `run_id`, not `cycle_id` alone — RESOLVED

Implemented as a partial unique index on `(run_id, cycle_id) WHERE is_primary = 1`. Escalated
before implementing further. **The lead approved it, amended spec 11, and fixed the root cause
in `architecture-context.md`,** which now states that a tick is `(run_id, cycle_id)` and never
`cycle_id` alone. Every "once per tick" constraint and cross-table join in the schema is scoped
to both columns as a result. The seed deliberately overlaps the two runs' `cycle_id` ranges and
says so in its docstring — that overlap is load-bearing, and tidying the runs apart would
silently disarm the Phase 3 test that proves ordering is by `ts`.

### 2. `safety` threshold key names and values — RESOLVED

The lead fixed the key names and **the operator supplied the values on 2026-09-08.** The seed
does not read `config/default.yaml`; it takes a `SeedThresholds` dataclass, so a Phase 3 test
seeds against whatever the config actually says. What the committed config now asks for, and
what the seed produces against it:

| Key | Operator value | Seed produces |
|---|---|---|
| `safety.max_consecutive_data_blocks` | 15 | 18 consecutive `data_guard` ticks, over 2 `run_id`s |
| `safety.max_drawdown_pct` | 0.10 | drawdown of 0.2000017843760037115020877199 at the trough |
| `safety.max_consecutive_losses` | 5 | losing streak of 8 |
| `safety.error_rate_window_s` | 3600 | — (fixed by `architecture-context.md`: "the trailing hour") |
| `safety.max_errors_in_window` | 20 | 23 `status='ERROR'` block records in the window |

My earlier proposal of `max_errors_in_window: 10` was not what the operator chose; the table
above is the committed state. The seed also writes 2 open positions, 2 resting entry orders,
33 trades and 46 rejections.

## Three decisions in the schema and the migration runner

Recorded in full in `docs/build-log/phase-0/b-store.md`; summarised here because each one is a
property another agent will rely on rather than an implementation detail of mine.

- **The database refuses a float in a money column.** Every money column is `TEXT` **and**
  carries `CHECK (typeof(col) = 'text')`. SQLite is dynamically typed, so a `TEXT` column stores
  a float without complaint and hands it back as one — "money is never `REAL`" was an assertion
  in a document rather than a property of the database. A single write bypassing the client, in
  any phase, would have seeded a drifting number into the equity series that moves the drawdown
  threshold that liquidates the account. The client now passes `str(Decimal)`.
- **`executescript` discards the transaction wrapped around it.** It issues an implicit `COMMIT`
  of any pending transaction before running its script, so the first runner's `BEGIN` was
  committed away by the very call it was meant to protect. `BEGIN`/`COMMIT` moved inside the
  script string, and the `schema_migrations` insert moved in with them — otherwise a crash
  between the two transactions leaves a database whose schema is applied and whose version row
  is not, and the next startup tries to create tables that already exist.
- **Migration bookkeeping records no wall-clock time by default.** `apply_migrations(...,
  applied_at: int | None = None)`. Spec 13 requires two seedings of the same seed to be
  byte-identical and the seed migrates the database it seeds, so a clock-stamped column would
  make every seeded database differ for reasons unrelated to the seed. The checksum, which is
  the field that protects anything, is always recorded.

## Known issue in my code path — closed as a risk, not root-caused

`toolchain_green` fails intermittently — roughly 20% of full-suite runs — with a native memory
fault, and every observed instance surfaces inside my write path:
`seed.py:_write_trading_history` → `client.write_trade` / `write_position` → pydantic
`model_dump`. Three distinct Windows statuses have been seen (`0xC0000005` access violation,
`0xC0000374` heap corruption, `0xC0000409` stack buffer overrun) plus an
`AttributeError: 'NoneType' object has no attribute '__dict__'` raised from inside `to_python`.

It is **not** a logic defect in the seed: every test passes when the process survives, and
`seed_database` called 60 times outside pytest is clean. My suspicion of pydantic-core 2.46.5
was checked and did not hold — pinning a different build did not settle it. The lead
investigated it at length and closed it without a root cause; pyarrow, `pytest-asyncio`, test
ordering, `root_import_path` and the pydantic-core version were each ruled out, hardware is
suspected and is out of scope, and the gate now retries a crash once. Full account in
`docs/build-log/phase-0.md`.

**Do not re-run the suite to see whether the result changes.** That experiment has been run. It
becomes mine again if the fault appears outside this write path, or if the gate starts
reporting `CRASH -` after its retry — which would mean the rate has moved and the mitigation no
longer holds.

## Blocked on

Nothing.

## Verification

```
$ .venv/Scripts/python.exe scripts/verify.py --phase 0
PASS    db_migrates_from_empty       fresh database migrated to all 9 documented tables
PASS    seed_fixtures_present        all six fixtures present: outage run 18 ticks over 2 run_ids
                                     (11 double-blocker), 2 open position(s), 2 resting order(s),
                                     drawdown 0.2000017843760037115020877199, losing streak 8,
                                     23 ERROR blocks in the window, 33 trades / 46 rejections

7 criteria: 7 PASS, 0 FAIL, 0 PENDING
Phase 0 is green: every criterion PASS, zero PENDING.
```
