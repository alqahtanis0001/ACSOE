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

### `jsonable_encoder` renders every `Decimal` by calling `float()` on it

**Agent:** C · **Task:** specs 19 to 22 · **Date:** 2026-09-09

**What happened.** The four screen endpoints were first written to return the view models
themselves — `return reader.status_band(mode=...)`, and so on. Every screen answered, every
test of the *reader* stayed green, and every money value in the served JSON had silently
passed through `float`. `Decimal("0.00012345")` reached the browser as `0.00012345` only by
luck of the value; anything with more significant digits than a double carries came out
altered, and nothing on the page could tell.

**Why.** FastAPI serialises a returned object through `jsonable_encoder`, and
`jsonable_encoder`'s `Decimal` rule is `float(value)`. The whole point of
`clients/store/contracts.Money` is that it is a `Decimal` which *refuses* a float rather than
coercing one, so that a value which has already lost precision is rejected at the boundary
instead of being rendered to two convincing decimal places. The response encoder undid that
on the way out, after every guard the store client and the view models put in the way.

**Fix.** `src/acsoe/console/payloads.py`. Nothing hands a `Decimal` to the encoder any more:
each payload emits strings and integers only — the rendered text `console/format.py` already
produced, and the exact decimal string beside it where a consumer might want to compute. The
routes return a `starlette.responses.JSONResponse`, which FastAPI passes through untouched
because a response object short-circuits `jsonable_encoder` entirely. `money()` uses
`format(value, "f")` rather than `str`, because `str(Decimal("1E+3"))` is scientific notation.

**Consequence.** The leaderboard's four *statistics* — win rate, Sharpe, deflated Sharpe,
Brier — are genuinely `float` and never were money, and they are sent as rendered text only
rather than as numbers. That is not fussiness: it lets the assertion be *"the encoded body
contains no JSON float anywhere"*, which is total and cannot rot, instead of a list of
fields exempted from a rule.

### The history screen is two tables, and that is why `history()` stopped returning a flat tuple

**Agent:** C · **Task:** spec 21 · **Date:** 2026-09-09

**Options.** One interleaved table of everything the history screen holds, ordered by time,
with a `kind` column — or two tables, trades and rejections, each ordered on its own key.

**Chose.** Two. `ConsoleReader.history()` returns a `HistoryView` carrying `.trades` and
`.rejections`.

**Because.** A closed trade carries a quantity, an exit price and two fees. A refused
candidate carries an expected move, a friction, a net edge and a hurdle, and never had a
quantity at all. Interleaving them means every row is half blank cells, and a table that is
half blank is the shape that makes an operator stop reading. The ordering keys are not even
the same column: a trade orders by `closed_at` — a trade opened earlier can close later, so
`opened_at` is wrong and B's store client already orders on `closed_at` for that reason —
and a rejection orders by `ts`.

**Cost, and it was paid later rather than at the time.** Two tests in
`tests/console/test_reader.py` still assumed the old flat tuple, and the IDE crash landed
before they were updated. See the entry below.

### Two staleness questions in the status band, not one

**Agent:** C · **Task:** spec 19 · **Date:** 2026-09-09

**What happened.** The band was first built with a single age: the age of the newest thing
in the database. Against the seed it read fresh while the balance figure beside it was
hours old.

**Why.** They are different questions. `staleness` is the age of the *balance figure*, which
is what number rule 5 fades to half opacity. `data_staleness` is the age of the **store
watermark** — the highest `updated_at` across every table the console renders — which is the
band's Data age field. A daemon can be writing a block record every tick while the equity
series has not moved, so a band that conflated them would report the whole screen fresh
because *something* changed. That is exactly the failure rule 5 exists to prevent.

**Fix.** `StatusBand` carries both, and `reader.status_band()` computes them separately from
the same injected clock. A watermark of `0` is treated as an empty database and yields
`None`, not a figure written at the epoch and therefore 56 years stale.

### Staleness has to be decided in microseconds, before the millisecond conversion

**Agent:** C · **Task:** spec 19 · **Date:** 2026-09-09

**What happened.** `Staleness` first computed an age in microseconds, floored it to
milliseconds, and compared that against `console.stale_after_ms`. A figure one microsecond
past the threshold floors to exactly the threshold and read as fresh.

**Why.** The store holds microseconds and the threshold is expressed in milliseconds, so
there is a conversion somewhere and the only question is which side of the comparison it
falls on. Putting it before the comparison throws away up to 999 microseconds of the answer
at precisely the boundary the test sits on.

**Fix.** The comparison happens in microseconds against `stale_after_ms * 1000`, and `age_ms`
is a display value derived afterwards. Strictly greater is stale, so a figure exactly at the
threshold is still fresh; the boundary has to be somewhere, and this is the one a
`FixedClock` test can sit one microsecond either side of.

### One blocked tick is one feed row, however many guards blocked on it

**Agent:** C · **Task:** spec 20 · **Date:** 2026-09-09

**What happened.** The cycle feed first rendered one row per `block_records` row. Ticks where
two guards blocked appeared twice, which reads as two outages.

**Why.** The guard chain never breaks early — `data_guard` rejecting the tick's data must not
stop `safety` evaluating the account — so engine 19 writes one row *per blocker per tick*,
with `is_primary` on the first. `architecture-context.md` says the outage count is the number
of consecutive ticks carrying a `data_guard` row, not the number of rows, for the same
reason. The feed had the same bug in display form.

**Fix.** `ConsoleReader._blocked_ticks()` keys on `(run_id, cycle_id)` and keeps the primary
blocker, falling back to the first row seen on the tick when nothing is marked primary. The
key is the pair and never `cycle_id` alone: `cycle_id` restarts at 1 with each process, and
B's seed deliberately reuses values across its two runs, so keying on it alone collapses two
different ticks from two different runs into one.

**Consequence.** A blocked tick that *also* had a candidate still produces two rows — one
from `rejections` and one from `block_records` — and that is not a duplicate. The guard
blocked and a candidate was refused; folding them together is how anyone counting refused
trades ends up counting feed outages, which is the defect `block_records` was split into its
own table to avoid.

### Decision: the empty state says "not recorded yet" where showing a zero would be a lie

**Agent:** C · **Task:** spec 20 · **Date:** 2026-09-09

**Options.** `ui-context.md`'s empty state is written as four stages — "Scanned 412 pairs. 38
entered the tradable universe. 3 reached the cost gate. None cleared it." Nothing in the
store records the first two. The choices were to render `0` for them, to omit the lines, or
to render the line with a statement that the count does not exist.

**Chose.** The third. `FeedStage.count` is `None` for those two stages and the line says the
universe filter arrives in Phase 2.

**Because.** A zero in a column of counts reads as a *result* — "no pair entered the tradable
universe" — when the truth is that nobody counted. That is the worst of the three options on
the one screen whose entire job is to make stillness legible rather than make it look like a
failure. Omitting the lines was second best but hides that two stages exist at all, which
makes the remaining two look like the whole pipeline.

**Cost.** The two lines carry a phase number, so they need revisiting when engine 4 lands.
The counts that *are* rendered are read off rows that exist and none is computed from a rule:
"reached the cost gate" counts rejections whose `rejected_by` is `cost`, and "cleared it"
counts open positions.

### Decision: the SHAP pane has nowhere to put a row, by construction

**Agent:** C · **Task:** spec 22 · **Date:** 2026-09-09

**Options.** Draw the Phase 5 attribution view now against no data — an empty chart, a
placeholder bar, a sample explanation — or give the pane a model that cannot hold one.

**Chose.** `ShapPane` carries three fields: `available`, `produced_in_phase` and `message`.
There is no `rows` key and no `chart` key, and `research_payload` emits none.

**Because.** The operator ruled at the spec-18 checkpoint that spec 22 stands as written and
a view must not be designed for data that arrives in Phase 5. Beyond the ruling: a figure
that looks like attribution and is not is worse than no figure, because the operator cannot
tell them apart. Making the *model* incapable of carrying a row is what turns that from a
rule someone has to remember into a change that has to be made deliberately.

**Cost.** Phase 5 adds the fields rather than filling them, and the test asserting their
absence has to be deleted in the same change, which is the point — it is a deliberate act
rather than a drift.

### The docstrings promised two test modules the crash took with it

**Agent:** C · **Task:** specs 19 to 22 · **Date:** 2026-09-09

**What happened.** `console/payloads.py` states that "`tests/console/test_payloads.py` asserts
the whole encoded body contains no JSON float anywhere", and `_shap_payload` states that
adding a `rows` or `chart` key "is the change `tests/console/test_research.py` exists to
fail". Neither file exists. `tests/console/` holds `test_app.py`, `test_format.py`,
`test_page.py` and `test_reader.py` and nothing else.

**Why.** The IDE crash landed between writing the module and writing its tests, and the
docstring was written in the present tense for a file that was next on the list. Nothing
caught it: the suite was green because the assertions were never there to fail, and the
`console_renders_seeded_screens` criterion asks whether a screen answers with a non-empty
body, not what is in it.

**Fix.** Both modules written. `test_payloads.py` walks the encoded body of all four
endpoints and fails on any JSON float anywhere in it — a total assertion rather than a list
of exempted fields — and pins the two properties that make it total. `test_research.py`
asserts the SHAP pane carries no row and no chart element, in the payload and in the markup.

**Consequence.** A docstring that names a test file is a claim, and an unverified claim in a
docstring is worse than no docstring: it is the thing a reviewer checks *instead of* checking
the behaviour. Recorded here rather than quietly fixed because the same failure mode will
recur — the next session that is interrupted mid-spec will also leave a true-sounding
sentence about a file that is not there.

### Two stale tests survived the shape change to `history()` because the crash landed between them

**Agent:** C · **Task:** spec 21 · **Date:** 2026-09-09

**What happened.** `pytest tests/ -q` reported 2 failed, 639 passed on the tree the next
session picked up. Both in `tests/console/test_reader.py`:
`test_every_screen_is_empty_against_an_empty_database` asserted
`empty_reader.history() == ()`, and `test_history_carries_trades_and_rejections_newest_first`
raised `AttributeError: 'tuple' object has no attribute 'ts'`.

**Why.** They were written against the flat tuple `history()` returned before spec 21 split
it into two tables, and were not updated when it changed. The second failure is the more
interesting one: `for r in rows` over a pydantic model iterates its *fields*, so the test was
walking `("trades", (...)), ("rejections", (...))` and asking a 2-tuple for a `.ts`. It had
therefore never asserted anything about ordering even before the change — it would have
passed on any ordering at all had the field values happened to have a `ts`.

**Fix.** The tests, not the return type. Checked first that nothing else depended on the flat
shape: `history()` has exactly three call sites, the route in `app.py` (which passes it to
`history_payload`, already two-table) and these two tests. Both now assert on both tables.
The ordering test asserts each table strictly newest-first on **its own** key — `closed_at`
for trades, `ts` for rejections — behind a guard that the seed carries more than one distinct
timestamp in each. Without that guard the assertion has no teeth: a column of identical
timestamps is sorted ascending and descending at once, so a reader returning rows in
insertion order would pass. The emptiness test asserts both tuples are empty rather than
comparing a `HistoryView` against `()`, which would have been a shape check wearing an
emptiness check's name.

**Consequence.** `test_every_screen_is_populated_against_the_seed` had the same defect in a
quieter form: `assert seeded_reader.history()` is vacuous, because a pydantic model with no
`__bool__` and no `__len__` is always truthy. It now asserts each table separately. Three
assertions that could not fail, all introduced by one return-type change, is the argument for
running the suite at the *end* of a shape change rather than at the end of the spec.

### The baseline watermark has to be read before the handshake is accepted

**Agent:** C · **Task:** spec 23 · **Date:** 2026-09-09

**What happened.** The first push loop accepted the socket, then read the watermark as its
baseline, then polled. `console_websocket_pushes_on_change` reported a FAIL: the watermark
moved and nothing was pushed inside the budget.

**Why.** The criterion — and a real daemon — writes at the moment the socket comes up. The
sequence was: accept, write lands, first baseline read *already includes the write*, and from
then on the value never appears to move. The change was not missed by a millisecond; it was
swallowed permanently, and the next push waited for the *second* change. Every test that
connected, waited, and only then wrote passed, which is why the shape of the criterion mattered
more than its subject.

**Fix.** `watermark_socket` reads the baseline **before** `await socket.accept()`. Acceptance
then means "baseline taken", and everything from that instant onward is a change. The client
follows the same ordering for the same reason: it opens the socket first and fetches the four
`GET` endpoints on the `open` event, never before, so the initial fetch can only ever return
data at or ahead of the baseline. A change landing between the two produces one redundant push
rather than a lost one, and a redundant push is invisible because the flash only fires on a
value that actually differs from what is on the screen.

### Decision: nothing is pushed on connect, and the page's first content is a one-time fetch

**Agent:** C · **Task:** spec 23 · **Date:** 2026-09-09

**Options.** Send a snapshot when a socket connects and only deltas afterwards, or send nothing
on connect and let the page fetch the four `GET` endpoints once at load.

**Chose.** Nothing on connect. The socket carries changes and only changes.

**Because.** Two reasons, and the second is the one that decided it. `ui-context.md` says the
console "pushes over the WebSocket only when the watermark moves", which a connect snapshot
plainly is not. But more practically: with a snapshot, "did a push happen?" can no longer tell
a working watermark from a broken one — `console_websocket_pushes_on_change` would have gone
green against a server that never read the watermark at all, and the silence test could not
have been written, because there would always be one frame to explain away. A criterion that
cannot fail is the defect the operator amended spec 20 over, and this would have been the same
defect in the socket.

**Cost.** The page makes four HTTP requests at load. That is not the browser-side polling the
spec forbids — there is no timer on it and it runs once per connection — but it is a second
path to the same data, so the payload is built from **the same view models** as the endpoints
(`websocket.screen_payloads`) and a test asserts the pushed body equals the endpoint body field
for field. One composition, two transports.

### Decision: the command connection is narrowed by a SQLite authorizer, not by a subclass

**Agent:** C · **Task:** spec 24 · **Date:** 2026-09-09

**Options.** Spec 24 says the write path "touches only the `commands` table". `StoreClient` is
B's and exposes a write method for every table, so a subclass that simply never calls the
others satisfies the sentence. The alternative is to install `sqlite3.set_authorizer` on the
connection and have the database refuse everything else.

**Chose.** The authorizer. `NarrowCommandStore` opens through B's `open_connection` — so the
WAL, autocommit and busy-timeout pragmas stay in one place — and then denies `INSERT`,
`UPDATE`, `DELETE` and the DDL actions on any table but `commands`, plus `ATTACH`, which would
otherwise let a denied write in under a different database name.

**Because.** "Touches only the commands table" as a subclass is a promise about what the code
happens to call today, and the console's write path is the one place a mistake reaches the
daemon's own data. As an authorizer it is a property the database enforces, and a test can
prove it by attempting a real `INSERT INTO runs`, a real `UPDATE positions`, a real `DELETE
FROM trades` and a real `DROP TABLE rejections` and asserting each raises. The same reasoning
put spec 17's reader behind `mode=ro` rather than behind an author's discipline.

**Cost.** Two `frozenset`s of `sqlite3.SQLITE_*` constants that a future SQLite could extend,
and the standing risk of the opposite failure — an authorizer that denied everything would pass
the negative test and break the feature. There is a paired positive test for exactly that.

### The read-only reader has to survive the first write, and WAL is why

**Agent:** C · **Task:** spec 24 · **Date:** 2026-09-09

**What happened.** Nothing failed, and this is recorded because it nearly did and because the
next person to touch it will have the same doubt. The console now holds two connections to one
file: spec 17's `mode=ro` reader and spec 24's read-write command connection.

**Why it is not obvious.** `clients/store/connection.py` opens every connection in WAL mode,
and a read-only SQLite connection to a WAL database needs the `-shm` sidecar, which a `mode=ro`
connection cannot create. The reader connects lazily, so the sequence "operator opens the
console, presses Freeze before any screen has been polled, then a screen renders" has the
reader opening for the first time against a database that is mid-WAL. That is the normal case,
not an edge one.

**Fix.** No code change — B's seed truncates the WAL on close and the sidecar is created by the
writer before the reader needs it — but a test now pins it: the reader is closed, a command is
written, and the reader is then made to read the watermark and the status band. Recorded rather
than left as luck, because if this ever breaks it will break on an operator's machine and look
like the console failing to start.

### The console's own clock ties the watermark rather than moving it, under a seed-anchored fixture

**Agent:** C · **Task:** spec 24 · **Date:** 2026-09-09

**What happened.** A test asserting that writing a command moves the store watermark failed on
equality: the watermark before and after were the same microsecond.

**Why.** The console stamps `created_at` and `updated_at` from its **injected** clock, and
`tests/conftest.py`'s `seed_clock` stands exactly at the seed's last moment — which is also the
highest `updated_at` in the database. A command written at that instant ties the maximum
instead of raising it. Not a defect in either: the clock is injected precisely so staleness is
not a race, and a running console's `SystemClock` is always ahead of every seeded row.

**Fix.** The test advances the clock one second past the seed before writing. Worth the entry
because the failure looks like "the watermark is not being updated" and is actually "the
fixture froze time at the moment the assertion depends on moving past".

### Three tests that could not fail, from one spec-18 assertion left behind

**Agent:** C · **Task:** specs 23 and 24 · **Date:** 2026-09-09

**What happened.** `test_the_page_carries_no_script` was written at spec 18 and asserted
`"<script" not in markup`. Spec 23 adds `console.js`, so it had to change — and the obvious
change is to delete it.

**Why deleting it is wrong.** The assertion was doing real work: it is what stopped a page
growing an inline handler or a second script nobody reviewed. Removing it to make a red test
green is the exact move `run-protocol.md` forbids, and the replacement has to assert *more*
than the original, not less.

**Fix.** It now asserts exactly one `<script>`, `src`-ed from `/static`, deferred, with an empty
body, no `on*` attribute anywhere in the markup, and all three command buttons still carrying
`disabled` in the served page — the script enables them, so a page whose script failed to load
offers nothing rather than offering a button that silently does nothing. The route-set
assertion and the `sqlite3`-import assertion in `test_app.py` were widened the same way: the
route set now names `/ws` and `/api/command/{name}` with the spec each belongs to, plus a new
assertion that `POST` appears on exactly one path, and `sqlite3` is allowed in `reader.py` and
`commands.py` and nowhere else rather than in `reader.py` alone.

### `StoreClient` does not expose the reader the orchestrator calls

**Agent:** C · **Task:** spec 24 · **Date:** 2026-09-09

**What happened.** Spec 24 requires a row written by the console to be claimed and consumed by
the **real** orchestrator reader, not a mock of it. `Orchestrator._consume_commands` calls
`store.claim_pending_commands(run_id=..., now=...)` and
`store.mark_command_consumed(command, now=...)`. `StoreClient` exposes neither: it has
`pending_commands()`, `claim_command(command_id, *, claimed_at, run_id)` and
`mark_command_consumed(command_id, *, consumed_at)` — different names and different shapes. The
only implementation of the orchestrator's shape in the whole repository is a test double in
`tests/core/test_orchestrator.py`.

**Why this is a real gap and not a test inconvenience.** The orchestrator reaches for the
methods through `getattr` and logs `commands_skipped` when they are absent, so a daemon wired to
the real `StoreClient` today would read no commands at all and never say anything louder than a
debug line. Phase 2 is the first phase where a daemon runs.

**Fix, for now.** `tests/console/test_commands.py` carries a `_StoreAdapter` that does nothing
but rename — it claims through `claim_command` and consumes through `mark_command_consumed`.
Every decision under test happens in `core/`: which row to claim, which effect to apply, and
that `close_all` defers `consumed_at` while `activate` and `freeze` stamp it in the same tick.
The round trip is asserted for all three commands and the row is checked to come back with
`command` and `source` unchanged.

**Escalated,** because the two files that would close it are the lead's (`core/`) and B's
(`clients/store/`) and neither is mine to edit. Written up as an open question in
`context/progress/c-interface.md`.

### An intermittent `TypeError` inside pyyaml, in a run that was green twice either side

**Agent:** C · **Task:** specs 19 to 22 · **Date:** 2026-09-09

**What happened.** The first full-suite run of the session, immediately after fixing the two
stale `test_reader.py` tests, reported `1 failed, 640 passed`. The failure was
`tests/platform/test_config.py::test_a_missing_required_key_is_refused`, and the trace ended:

```
.venv\Lib\site-packages\yaml\composer.py:89: in compose_scalar_node
    event = self.get_event()
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
self = <yaml.loader.SafeLoader object at 0x0000020667DADA90>
    def get_event(self):
        if self.current_event is None:
            if self.state:
>               self.current_event = self.state()
E               TypeError: object of type 'ScalarEvent' has no len()
.venv\Lib\site-packages\yaml\parser.py:118: TypeError
```

`tests/platform/test_config.py` alone then passed 82/82, and two subsequent full-suite runs
passed 641/641 and 705/705.

**Why it is recorded here rather than shrugged off.** The suite has no randomised ordering —
`pytest-randomly` and `pytest-xdist` are both absent — so the same code ran in the same order
three times and disagreed with itself once. That is a non-deterministic runtime fault, and it is
the fourth distinct site for the fault already re-opened in the tracker's Known Risks: the
entry's own re-opening note records it inside `pydantic-core` and inside `sqlite3`'s C
extension, "which is what memory corruption looks like and is not what a library defect looks
like". A bogus `TypeError` raised from pure-Python pyyaml — a parser state object reported as
having no `len()`, which nothing in that code path asks it for — is consistent with the same
cause and inconsistent with a pyyaml bug.

**Not fixed, and not mine to fix.** It is outside the seed write path, in A's test file, and the
Known Risks entry is the lead's. Escalated in the report and in my progress file. Captured here
in full before the re-run, per the standing instruction, so that the next occurrence has a third
signature to compare against rather than a memory of one.
