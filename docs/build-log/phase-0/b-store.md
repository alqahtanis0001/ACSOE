# Phase 0 — Agent B (Store and trading)

### Spec 11 as written could not produce the seed spec 13 mandates

**Agent:** B · **Task:** spec 11 · **Date:** 2026-09-08

**What happened.** Spec 11 step 5 requires a partial unique index on `(cycle_id)` where
`is_primary` is true. Spec 13 step 3 requires the seeded outage run to span two `run_id`s.
Those two cannot both hold.

**Why.** `architecture-context.md` says `cycle_id` "is minted per tick within a run and
restarts with the process". Two runs therefore reuse the same low `cycle_id` values, and a
unique index on `cycle_id` alone rejects the second run's primary block record — the exact
row the Phase 0 exit criteria require.

The sharper half is not the collision. It is that if the two seeded runs did *not* overlap in
`cycle_id`, then ordering by `cycle_id` would give the same answer as ordering by `ts`, and
the Phase 3 criterion that exists specifically to prove "order by `ts`, never by `cycle_id`"
would pass against an implementation that orders by the wrong column. The overlap is
load-bearing: it is what makes the fixture able to fail.

**Fix.** `CREATE UNIQUE INDEX ux_block_records_primary ON block_records (run_id, cycle_id)
WHERE is_primary = 1`. Escalated before implementing further. The lead approved, amended spec
11, and fixed the root cause in `architecture-context.md`, which now states that a tick is
`(run_id, cycle_id)` and never `cycle_id` alone.

**Consequence.** Every "once per tick" constraint and every cross-table join in the schema is
scoped to both columns: `rejections` joins `block_records` on `(run_id, cycle_id)`, and
`ux_equity_snapshots_tick` is `(run_id, cycle_id)`. The seed deliberately overlaps the two
runs' `cycle_id` ranges and says so in its docstring, because the next person to read it will
otherwise "tidy" them apart and silently disarm the Phase 3 test.

### Decision: the database refuses a float in a money column, rather than trusting callers

**Agent:** B · **Date:** 2026-09-08

**Options.** Declare money columns `TEXT` and rely on the store client to be the only writer,
or additionally constrain them at the database.

**Chose.** Both. Every money column is `TEXT` and carries `CHECK (typeof(col) = 'text')`.

**Because.** SQLite is dynamically typed: a column declared `TEXT` will store a float without
complaint, and `SELECT` will hand it back as a float. "Money is never `REAL`" was therefore an
assertion in a document rather than a property of the database — a single write that bypassed
the client, in any phase, would have silently seeded a drifting number into the equity series
that moves the drawdown threshold that liquidates the account. Now that write fails.

**Cost.** A `CHECK` per money column, and the client must pass `str(Decimal)` rather than
letting sqlite3 adapt whatever it is given. That is the conversion boundary the spec wanted
anyway, and the constraint is what proves it holds.

### `executescript` discards the transaction you wrapped around it

**Agent:** B · **Task:** spec 11 · **Date:** 2026-09-08

**What happened.** The first migration runner did `conn.execute("BEGIN")`, then
`conn.executescript(migration.sql)`, then `COMMIT`, and would have applied the schema
statement by statement with no atomicity at all.

**Why.** `sqlite3.Connection.executescript` issues an implicit `COMMIT` of any pending
transaction *before* running its script. The `BEGIN` was committed away by the very call it
was supposed to protect.

**Fix.** The `BEGIN` and `COMMIT` moved inside the script string, and the bookkeeping
`INSERT` into `schema_migrations` moved in with them. That second part matters independently:
had the insert stayed a separate statement, a crash between the two transactions would leave a
database whose schema was applied and whose version row was not, and the next startup would
try to create tables that already exist. `executescript` takes no bound parameters, so the
three values interpolated into that insert are a parsed integer, a name matched against
`[a-z0-9_]+`, and a hex digest — nothing that can carry an injection.

**Consequence.** `apply_migrations` returns the list of versions it applied, so "re-migrating
is a no-op" is a check on `== []` rather than on a schema diff.

### Decision: migration bookkeeping records no wall-clock time by default

**Agent:** B · **Date:** 2026-09-08

**Options.** Stamp `schema_migrations.applied_at` from the clock, which is what a migration
runner normally does, or leave it null unless a caller supplies it.

**Chose.** `apply_migrations(..., applied_at: int | None = None)`, defaulting to null.

**Because.** Spec 13 requires two seedings of the same seed to be byte-identical, and the seed
migrates the database it seeds. A wall-clock column would make every seeded database differ
from every other one in a way that has nothing to do with the seed. Nothing in this package
reads a clock; the operator gets the timestamp by passing one.

**Cost.** A migrated database carries no record of when it was migrated unless the caller
asked for one. The checksum, which is the field that actually protects anything, is always
recorded.
