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

## Known issue in my code path — not yet root-caused

`toolchain_green` fails on roughly 30% of runs with a native memory fault, and every observed
instance surfaces inside my write path: `seed.py:_write_trading_history` → `client.write_trade`
/ `write_position` → pydantic `model_dump`. Three distinct Windows statuses have been seen
(`0xC0000005` access violation, `0xC0000374` heap corruption, `0xC0000409` stack buffer
overrun) plus an `AttributeError: 'NoneType' object has no attribute '__dict__'` raised from
inside `to_python`.

It is **not** a logic defect in the seed as far as anything has shown: every test passes when
the process survives, and `seed_database` called 60 times outside pytest is clean. Current
suspicion is pydantic-core 2.46.5 on Python 3.13.5. Recorded here because it is my path and I
should be the one to check it if the version pin does not settle it.

## Blocked on

Nothing.

## Verification

```
python scripts/verify.py --phase 0
PASS    db_migrates_from_empty       fresh database migrated to all 9 documented tables
PASS    seed_fixtures_present        all six fixtures present: outage run 18 ticks over 2 run_ids
                                     (11 double-blocker), 2 open position(s), 2 resting order(s),
                                     drawdown 0.2000017843760037115020877199, losing streak 8,
                                     23 ERROR blocks in the window, 33 trades / 46 rejections
```
