# Build log — Phase 1 — c-interface

Your file. Append as you work, per context/script-rules.md.
The lead consolidates these into docs/build-log/phase-1.md at phase close.

Minimum headings per entry: What happened, Why, Fix.

## Entries

### Decision: the console's HTTP surface is pinned by the gate before the screens exist

**Agent:** C · **Task:** spec 16 · **Date:** 2026-09-09

**Options.** Spec 16 asks for criteria that post Activate, Freeze and Close-all and that read
"every screen", but no spec below it names a URL. Either the criteria discover routes from the
application's route table at run time, or they name the contract and report PENDING against a
404 until it is met.

**Chose.** Named the contract: `GET /`, `GET /api/state`, `/api/feed`, `/api/history`,
`/api/research`, `WS /ws`, and `POST /api/command/{activate|freeze|close_all}`. It is printed
in every PENDING message through the `CONSOLE_CONTRACT` constant, so an agent reading a
PENDING line is told what to build rather than only that something is absent.

**Because.** Route discovery would have made the criterion assert whatever the console happened
to expose, which is a criterion that cannot fail. It would also have coupled the gate to
Starlette's route objects — the criteria deliberately drive the application through the ASGI
interface and know nothing about the framework behind it.

**Cost.** Specs 19 to 24 are now bound to these paths. They are all mine, so the coupling is
inside one owner, but it is a real constraint and it is recorded here rather than only in code.

### `runs.run_id` is UNIQUE, so spec 16's "two run_ids match" state cannot exist

**Agent:** C · **Task:** spec 16 · **Date:** 2026-09-09

**What happened.** `console_restart_banner` was specified as: seed two `runs` rows with
different `run_id`s and assert the restart text, then assert plain `Idle` "when the two
`run_id`s match". Building the second half turned out to be impossible —
`db/migrations/0001_initial.sql` declares `run_id TEXT NOT NULL UNIQUE`, so no database can
ever hold two rows carrying the same `run_id`.

**Why.** `ui-context.md` describes the comparison as "the current `run_id` and the `run_id` of
the previous row", which reads as a value comparison but is in practice a *presence*
comparison: with a unique key, two rows always differ and one row has no predecessor. The two
states an operator actually meets are "a system waiting to be started", which is the first ever
run, and "a system that stopped on its own", which is any run with a predecessor.

**Fix.** The criterion seeds once and then reduces the copy to a single `runs` row for the
negative half, via `_keep_only_latest_run`. `tests/verify/test_phase1_criteria.py` asserts that
helper really does leave one row, so the branch cannot quietly become a test of something else.
The reader in spec 17 implements the same rule: no previous row, or a previous row with the
same `run_id`, reads plain `Idle`.

**Consequence.** Raised with the lead as an open question in `context/progress/c-interface.md` —
the wording in `ui-context.md` and in spec 16 implies a state the schema forbids, and the
document should say "a previous run exists" rather than "the run_ids differ".

### `href="#feed"` is four hex digits

**Agent:** C · **Task:** spec 16 · **Date:** 2026-09-09

**What happened.** `console_tokens_no_raw_hex` scans `src/acsoe/console/` for colour literals.
The obvious pattern, `#[0-9A-Fa-f]{3,8}`, flags every fragment link whose id happens to be
spelled in the letters a to f — and the console's own cycle feed is `#feed`, four hex digits
exactly. `#dad`, `#face` and `#added` are the same class of false positive.

**Why.** A CSS colour and an HTML fragment reference are the same characters. Nothing in the
token itself separates them.

**Fix.** The context does. A colour in CSS is preceded by `:`, a space, `(` or `,`; a fragment
reference in markup is always preceded by a quote. The pattern carries a negative lookbehind
for `"` and `'`, and a test in `test_phase1_criteria.py` writes `href="#feed"` and
`href="#dad"` into a fabricated template and asserts the criterion still PASSes.

### `CancelledError` is not an `Exception`, and the WebSocket probe reported itself as a crash

**Agent:** C · **Task:** spec 16 · **Date:** 2026-09-09

**What happened.** `console_websocket_pushes_on_change` drives the application's WebSocket
endpoint directly and then cancels the task, because a push loop is *supposed* to run until the
socket closes. Awaiting the cancelled task inside `contextlib.suppress(Exception)` did not
suppress anything: `asyncio.CancelledError` inherits from `BaseException`, not `Exception`, so
the cancellation the probe itself asked for propagated out and `run_criterion` reported the
criterion as having raised. The red test — an endpoint that accepts and never pushes — failed
with a `CancelledError` traceback instead of the FAIL it was written to prove.

**Why.** `CancelledError` was moved out of the `Exception` hierarchy in Python 3.8 so that a
broad `except Exception` cannot swallow a cancellation. Here the cancellation is deliberate, so
the broad handler was the right shape and the wrong base class.

**Fix.** `contextlib.suppress(asyncio.CancelledError, Exception)` in the probe's `finally`,
with the reason written next to it.

### Decision: the read-only connection is a `StoreClient` subclass, not a second set of SELECTs

**Agent:** C · **Task:** spec 17 · **Date:** 2026-09-09

**Options.** Spec 17 says two things that pull against each other: compose the screens from the
reads that already exist on B's `StoreClient`, and open the connection read-only. `StoreClient`
opens its connection through `clients/store/connection.py`, which is read-write, and
`clients/store/` is B's directory. Three ways out: write the console's own SELECTs, reach into
`StoreClient._conn` and swap the connection, or subclass and override where the connection comes
from.

**Chose.** `ReadOnlyStore(StoreClient)` in `console/reader.py`, overriding the `connection`
property to open a `mode=ro` URI.

**Because.** Own SELECTs would be a second statement of B's schema inside C's directory, and it
would drift the first time a column was renamed — the seam in `ownership.md` exists precisely so
that does not happen. Assigning to `_conn` from outside would be the same coupling with none of
the visibility. The subclass changes one thing, in one place, in my own file, and B's directory
is untouched.

**Cost.** The console is now bound to `StoreClient` opening its connection lazily through a
property. If B ever connects in `__init__`, this breaks loudly rather than silently — the
read-only tests attempt a real write and would start passing writes — which is why
`test_the_store_client_write_methods_are_refused_too` goes through `write_run` rather than only
through raw SQL.

**Note on WAL.** The database is in WAL mode, and opening a WAL database read-only makes SQLite
create the `-shm` and `-wal` sidecars. That needs write permission on the *directory*, not on the
database. It is satisfied everywhere the console actually runs — the daemon owns that directory —
but it is why `mode=ro` alone is enough here and an `immutable=1` URI would not be.

### The console cannot tell Running from Frozen, and no store read exists that would let it

**Agent:** C · **Task:** spec 17 · **Date:** 2026-09-09

**What happened.** The status band has a State field. `ui-context.md` fixes its two idle
readings — `Idle`, and `Idle — restarted, not trading` — but the daemon also has `running` and
`frozen`, and the console has no way to learn which.

**Why.** Mode is never restored from the store: `architecture-context.md` says a daemon always
starts `idle` and only reaches `running` through an `activate` command, and the command reader in
`core/` is the only writer of `state["system"]`, which lives in memory. The `runs` table's `mode`
column is paper/live/replay, not the system mode. The one trace a running daemon leaves is the
`commands` row it claimed — and `StoreClient` exposes `pending_commands()` and
`claimed_unconsumed_commands()` but no read for *claimed and consumed* history, which is what a
"the last thing this run applied was an activate" derivation would need.

**Fix.** None taken, deliberately. The reader renders `Idle` or `Idle — restarted, not trading`
from `latest_runs(2)` and does not guess at the other two. Adding a read to
`clients/store/client.py` would be writing in B's directory; deriving `running` from anything
else would be inventing behaviour the store cannot support.

**Consequence.** Raised as an open question in `context/progress/c-interface.md` for the lead,
with two options named there. It reaches the operator at the spec 18 checkpoint rather than being
discovered inside spec 19, which is the screen that would have had to guess.

### The cycle feed cannot anchor its window on the clock

**Agent:** C · **Task:** spec 17 · **Date:** 2026-09-09

**What happened.** `StoreClient.block_records_in_window` takes an explicit `start_ts`/`end_ts`.
The obvious window is "the last N hours from the injected clock". Against B's seeded database
that returns nothing at all: the seed's timestamps are fixed constants with no relationship to
wall time, so the whole cycle feed rendered empty and looked like a bug in the screen.

**Why.** The console is built against seeded data by design — `architecture-context.md`'s build
order is structure, then interface, then backend, precisely so the console is finished before
real rows exist. A clock-anchored window makes the screen's content depend on the gap between the
fixture and today.

**Fix.** The reader asks for the full `ts` range and does the ordering and limiting itself, on the
rows that come back. Correct against seeded and live data alike, and it keeps `ts` as the ordering
key, which `architecture-context.md` requires because `cycle_id` restarts with each process.

**Cost.** A full scan of `block_records` per feed render. Fine at Phase 1 volumes and not fine
forever; a most-recent-N read on B's surface would replace it. Recorded as an open question
rather than reached across for.
