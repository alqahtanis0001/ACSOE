# Agent B — Store and trading

## Claimed

- **Spec 11** — `db/migrations/`, SQLite schema and forward-only migration runner. *Complete.*
- **Spec 12** — `src/acsoe/clients/store/`, store client and contracts. *Complete.*
- **Spec 13** — `src/acsoe/clients/store/seed.py`, seed generator. *Complete.*
- **Spec 31** — persisted system mode: `db/migrations/0002_persisted_system_mode.sql`,
  `clients/store/{client,contracts}.py`, `tests/db/`, `tests/clients/store/`. *Complete,
  green on all three phase gates.*

- **Spec 34** — engine 10 `cost`. *Complete, committed at `3581e87`.*
- **Spec 35** — engine 11 `risk`. *Complete, committed at `5b0dd2b`.*
- **Spec 36** — engine 17 `safety`. *Complete and green, committed at `5b0dd2b`. **One
  policy table in it is an open question, not a decision** — see below.*

Nothing is in progress. Holding, per the lead, until the operator rules on
`CONDITION_ACTION`.

## OPEN QUESTION — engine 17's `CONDITION_ACTION` is NOT ratified

**Read this before treating `engines/safety/contracts.py`'s mapping as settled.** It is my
implemented reading of a contradiction, not a decision anyone has approved.

`trading-invariants.md` §14 and `feature-specs/36` cannot both be satisfied by the Phase 0
seed. §14 says `safety` escalates — writes `close_all` — on "its configured drawdown and
loss-streak limits are breached" or "a sustained data outage", when there are open positions
or resting entry orders. Spec 36's Check When Done says "it **freezes** on the seeded
drawdown". The seed carries drawdown 0.2000 against a 0.10 limit, a streak of 8 against 5,
**and** 2 open positions and 2 resting entry orders — every precondition §14 names, because
I built it that way in Phase 0 *to* satisfy §14. So under §14 the seeded drawdown emits
`close_all`; under spec 36 it emits `freeze`. There is no fixture on which both are true.

Escalated 2026-09-09 with three candidate readings and two further gaps: which command the
error rate emits, and whether an escalating condition emits `freeze` first. **With the
operator.**

What is implemented meanwhile, isolated in one dictionary so the ruling is one edit:
drawdown, loss streak and outage map to `close_all`; the error rate maps to `freeze`,
because §14 does not list it among the escalation conditions at all — it is an
engine-health problem rather than account exposure, and liquidating because the system is
throwing exceptions would be the breaker causing the loss it exists to prevent.

**Ratified by the lead, and separate from the above:** the `BOUNDARY_SOURCE` table beside
it, fixing whether each threshold trips *at* its limit or *above* it, each with the sentence
in the documents that fixes it. Drawdown, loss streak and error rate trip at the limit; the
outage is the only strictly-greater one.

## `core/`'s two writes — landed, primitives only

`core/` imports nothing from the rest of the package, so it cannot construct a `RunRow`
to hand to `write_run`. Two entry points now take `str` and `int` and nothing else:

```python
def start_run(self, run_id: str, *, mode: str, started_at: int,
              acsoe_version: str | None = None,
              config_digest: str | None = None) -> None: ...
def set_system_mode(self, run_id: str, mode: SystemMode | str, *, at: int) -> bool: ...
```

Four decisions in them:

- **`start_run` refuses a duplicate `run_id`** rather than upserting. `run_id` is minted
  once per process, so a second start is a bug; an upsert would rewrite `started_at`, and
  the console decides the current run from the newest `runs` row — so the silent version
  of that defect reorders the two rows the restart banner compares. Raises `StoreError`.
- **It names its columns explicitly** instead of dumping a payload, so it cannot become a
  writer of `system_mode` the way `write_run` silently did when spec 31 added the columns
  to `RunRow`. `set_system_mode` stays the only writer of both.
- **`set_system_mode` takes a plain `str`**, and that is now a guarantee rather than a
  `StrEnum` implementation detail that happened to work.
- **An unrecognised mode raises; an unknown run returns `False`.** The two are not alike:
  a missing row is a race the caller logs and continues past, a misspelled mode is a
  defect, and sharing a return value would leave the console on a stale mode with nothing
  saying why.

Proved with no double, the way `commands_round_trip` is: a **fresh interpreter** whose
entire import of this package is `StoreClient`, running the whole path on real SQLite,
plus a test that reads that caller's own source and asserts it names no contract and
constructs no row. `tests/clients/store/test_core_entry_points.py`, 17 tests.

## `bootstrap.py` — requested, deliberately deferred by the lead

- `CostEngine` — opportunity chain, after 9, before 11. `is_gate=True`.
- `RiskEngine` — opportunity chain, after 10, before 14. `is_gate=True`.
- `SafetyEngine` — **guard** chain, last, after 4. `is_gate=True`.

Deferred until the tree is globally green: `safety` in the guard chain runs on every tick of
`orchestrator_empty_registry` (a Phase 0 gate) and `commands_round_trip` (Phase 2), both
against a real `StoreClient`. On an empty database nothing should trip — but "should" is
doing work in that sentence, and if it does trip that is a finding worth having in isolation
rather than tangled with A's in-flight engine work. Engines 10 and 11 are opportunity-chain
and inert in both criteria.

## Spec 31 — persisted system mode

**Shape.** Two nullable additive columns on `runs`, not a new table:
`system_mode TEXT CHECK (... IN ('idle','running','frozen'))` and
`system_mode_at INTEGER`. Nothing existing is altered, nothing is dropped, no table is
added — so `db_migrates_from_empty` and `architecture-context.md`'s storage table need
no lead edit. Reasoning in full in `docs/build-log/phase-2/b-store.md`; the short version
is that `runs` already carries a UNIQUE `run_id`, so scoping by run is structural rather
than conventional and there is no query a reader can get wrong.

**The seam C builds against — this is the whole contract:**

```python
# src/acsoe/clients/store/contracts.py
class SystemMode(StrEnum):
    IDLE = "idle"; RUNNING = "running"; FROZEN = "frozen"

class SystemModeRow(_Row):
    run_id: str
    mode: SystemMode | None = None
    at: Micros | None = None          # microseconds, UTC; None iff mode is None

# src/acsoe/clients/store/client.py
def system_mode(self, run_id: str) -> SystemModeRow | None: ...
def set_system_mode(self, run_id: str, mode: SystemMode, *, at: int) -> bool: ...

# RunRow also carries `system_mode` / `system_mode_at`, read-only, for a caller that
# already holds a RunRow and does not want a second query.
```

**Two nulls, two different facts, and the console must not collapse them.**
`system_mode(...)` returns `None` when there is no `runs` row for that `run_id` — a
defect or a race, not a mode. It returns a row with `mode is None` when the run exists
and no daemon has written a mode yet — the ordinary case before the first command is
read. Both render as an idle reading per spec 32, but only the second is normal, and a
reader that cannot tell them apart cannot log the abnormal one.

**Writer.** `set_system_mode` is the only writer of both columns. `write_run` explicitly
excludes them, so the orchestrator's shutdown write of `ended_at` cannot clobber a
`frozen` daemon's persisted mode with the stale `None` its startup `RunRow` carries. The
caller is the command reader in `src/acsoe/core/orchestrator.py`, which is lead-only: I
provide the method, the lead calls it. `set_system_mode` bumps `runs.updated_at` too,
because `runs` is in `WATERMARK_TABLES` and without that the console would never repoll.

**Mode is never restored from the store.** There is no third method that reads this back
into `state["system"]`, and none should be added. A daemon always starts `idle` and
reaches `running` only through an `activate` command; restoring it would invert the
safety property that a crashed daemon comes back not trading, and it would look like a
bug fix while doing so.

**Nothing is seeded.** `seed.py` writes no system mode and
`test_the_seed_writes_no_system_mode` now asserts it, so C's Running-band test cannot
pass without a daemon having written one.

## Status

Spec 31 is green. All three gates, run 2026-09-09:

```
Phase 0 is green: every criterion PASS, zero PENDING.   (7 criteria: 7 PASS)
Phase 1 is green: every criterion PASS, zero PENDING.   (10 criteria: 10 PASS)
Phase 2 is green: every criterion PASS, zero PENDING.   (3 criteria: 3 PASS)
```

`723 passed` · `mypy --strict src/` clean, 35 files · `ruff check src/` clean.

The two `tests/db/test_migrations.py` failures the migration caused are fixed, and the
fix is not a bumped literal: both expectations now derive from the migrations directory
while still asserting the count and the ordering. See the build log for why the literal
was the wrong shape and for the asymmetry it exposed — `db_migrates_from_empty` passed
throughout, because it tolerates extra tables and 0002 adds none, so the phase gate did
not notice a schema change that my own unit tests did.

Spec 11 and 12's criteria still report PASS:

- `db_migrates_from_empty` — a fresh database migrates to all 9 documented tables; a second
  `migrate()` returns `[]`, so "re-migrating is a no-op" is checked on the returned list
  rather than on a schema diff.
- `seed_fixtures_present` — all six Phase 3 fixtures present, each overshooting its threshold
  rather than sitting on it.

Nothing of mine is outstanding. Spec 11 unblocked 12, which unblocked 13, in that order.

## For the lead — two things, neither of them mine to fix

1. **`core/` must now call `store.set_system_mode(run_id, mode, at=now)`** from the
   command reader, after the transition is applied to `state["system"]["mode"]` and not
   before. It returns `False` for an unknown `run_id`; log it, do not raise. Until that
   call exists the column stays NULL and the console renders idle, which is correct but
   is spec 31 only half-delivered.
2. **An intermittent Windows teardown fault outside my paths.** The first `--phase 0`
   run reported `FAIL toolchain_green — ERROR tests/cli/test_entrypoints.py::
   test_console_refuses_an_unset_operator_key | 722 passed, 1 error`. An `ERROR`, not a
   `FAILED`, exit 1 rather than an NTSTATUS, in A's `tests/cli/` — so it is neither the
   known seed-path native fault nor anything of mine. Captured verbatim in the build log
   before re-running, as the phase rules require; the re-run was green with no change.
   Separately, `scripts/verify.py` prints an unhandled `PermissionError [WinError 32]`
   on `acsoe-verify-doubles-*\acsoe.sqlite` from its own `TemporaryDirectory` finalizer
   on **every** phase-0 run, green ones included. Same Windows shape twice — a SQLite
   file still open when a temp directory is collected — one in A's test, one in C's
   script.

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
