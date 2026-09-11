# Agent B — Store and trading

## Claimed

- **Spec 11** — `db/migrations/`, SQLite schema and forward-only migration runner. *Complete.*
- **Spec 12** — `src/acsoe/clients/store/`, store client and contracts. *Complete.*
- **Spec 13** — `src/acsoe/clients/store/seed.py`, seed generator. *Complete.*
- **Spec 31** — persisted system mode: `db/migrations/0002_persisted_system_mode.sql`,
  `clients/store/{client,contracts}.py`, `tests/db/`, `tests/clients/store/`. *Complete,
  green on all three phase gates.*

- **Spec 34** — engine 10 `cost`. *Complete, committed at `3581e87`. Superseded by spec 40.*
- **Spec 35** — engine 11 `risk`. *Complete, committed at `5b0dd2b`. Superseded by spec 41.*
- **Spec 36** — engine 17 `safety`. *Complete and green, committed at `5b0dd2b`. Its one
  open question is closed by spec 42 — see below.*

### Phase 3 — claimed 2026-09-10

- **Spec 40** — wire engine 10 `cost` to the real `state["exchange"]`.
  `src/acsoe/engines/cost/{contracts,engine}.py`, `README.md`, `tests/engines/test_cost.py`.
  ***Complete, all four gates green 2026-09-10.*** Fixtures rewritten, not repointed: every
  `state["exchange"]` in `test_cost.py` is `ExchangeEngine().process(...).data` verbatim,
  from A's real engine 1 against C's `FakeKrakenClient`, and a source-reading test refuses
  any of engine 1's payload keys written as a dict-key literal in that file.
  `test_cost.py:376` deleted, not edited; reason in the build log.
- **Spec 41** — wire engine 11 `risk`, give it a price, and **build** the paper-mode balance
  fallback. `src/acsoe/engines/risk/{contracts,engine}.py`, `README.md`,
  `tests/engines/test_risk.py`. ***Complete, all four gates green 2026-09-10.*** Pair rules
  re-pointed to `exchange.pair_rules.pairs`; the price now comes from
  `market_sensor.quotes[pair]` — **ask** sizes the quantity, **bid** values it for `costmin`,
  per the lead's ruling. The balance fallback is built as new behaviour: paper falls back and
  records `balance_from_paper_starting_balances`, live and replay block. Every `state` in
  `test_risk.py` is engines 1 and 3's real output against C's fake client. **One open item for
  the lead — see below.**

#### For the lead — `replay` mode's balance fallback is my reading, not a ruling

Spec 41 names paper (fall back) and live (block). `EngineContext.mode` has a third value,
`replay`, and the spec does not mention it. I implemented `if context.mode != "paper"` —
so replay blocks — because invariant 2's table is headed *paper mode*, invariant 3 says a
gate that is unsure refuses, and "not paper" cannot silently extend the fallback to a mode
added later the way "is live" would.

**The cost is real and deferred, not absent.** If replay is later meant to reproduce paper
faithfully, a replayed tick will block where the paper run fell back, and the two diverge
exactly where invariant 10's faithful-replay property should hold. Nothing in Phase 3
exercises replay. One line and one constant to reverse; full reasoning in the build log.
- **Spec 42** — apply the ratified `CONDITION_ACTION` and prove `safety` in a real guard
  chain. `src/acsoe/engines/safety/{contracts,engine}.py`, `README.md`,
  `tests/engines/test_safety.py`, `tests/engines/test_safety_guard_chain.py`.
  ***Complete, all four gates green 2026-09-10.*** The ruled table is applied — **it was
  not, despite the note below saying it was; see the build log.** `ESCALATING_CONDITION`
  names the one condition that may reach `close_all` and a test enumerates the table
  against it. 46 tests in `test_safety.py` and 5 in the new guard-chain file, which drives
  the real `Orchestrator` over engines 1, 2, 3, 4, 17 against a real `StoreClient` on an
  empty database and on the seed.

### Phase 3 wave 2 — claimed 2026-09-10

- **Spec 43** — engine 7 `scout`, the tradable universe. `src/acsoe/engines/scout/`
  (`engine.py`, `contracts.py`, `README.md`), `tests/engines/test_scout.py`.
  ***Complete, all four gates green 2026-09-10, and `--phase 3` is 9 PASS / 0 FAIL /
  0 PENDING.*** 24 tests. Nine exclusion codes, each rule proved to be the *only* thing
  excluding its pair; the tick-grid rule made to fire and its boundary pinned as strict;
  counts asserted to add up including on a tick where four rules fire at once; the sizing
  cross-checked against the real engine 11 over a table straddling `ordermin` by one lot
  increment each way. Four mutations run and each caught by the test written for it.
  **One escalation to the lead — see below.**
- **Spec 44** — engine 7 `scout`, the candidate and the gate. `src/acsoe/engines/scout/`,
  `tests/engines/test_scout.py`. ***Complete, all four gates green 2026-09-10, and
  `--phase 3` is 9 PASS / 0 FAIL / 0 PENDING.*** 44 tests. One candidate under
  `state["scout"]["pair"]`, absent and never null when there is none; empty universe is
  `PASS` and not `BLOCK`; the handoff run as one tick through the real engines 10 and 11.
  Ordering is alphabetical, isolated as `rank_universe` in `contracts.py`.

### Phase 4 — claimed 2026-09-11

- **Spec 51** — the store surface engine 19 `memory` and the cycle feed need.
  `src/acsoe/clients/store/client.py`, `src/acsoe/clients/store/__init__.py`,
  `tests/clients/store/test_store.py`. *Claimed, in progress.* Three parts: a bounded
  most-recent-N read for `block_records` ordered by `ts`; an audit of every write and
  read engine 19 needs against what `StoreClient` already has; and a `peak_equity`
  read that does not walk the whole equity series. **No schema change, no migration,
  no edit to `console/` or to any `safety` read path.** ***Complete 2026-09-11.***
  Three methods, 14 tests, eight mutations run and all eight red — including the one
  spec 51 names by hand. `pytest tests/ -q` clean in my lane; `mypy --strict src/` and
  `ruff check src/` green.

#### Spec 51 — what landed, and the one thing that is C's to finish

Three methods on `StoreClient`, all handed to C by `SendMessage` the moment they
existed rather than at the end of the task:

- `recent_block_records(limit: int) -> tuple[BlockRecordRow, ...]` — most recent
  `limit` **rows**, `ORDER BY ts DESC, id DESC`, no default limit.
- `recent_blocked_ticks(limit: int) -> tuple[BlockRecordRow, ...]` — most recent
  `limit` **ticks**, one row each, primary blocker preferred, lowest `id` on the tick
  as the fallback. This is the one the cycle feed wants; a rows-limited read can cut a
  tick in half and render it as blocked by the wrong engine. Reasoned out in the build
  log and proved by mutation M8 against the real Phase 0 seed.
- `peak_equity(self) -> Decimal | None` — spec 51 item 3 and spec 50's running maximum.
  **`SELECT MAX(peak_equity)` is the wrong query**: money is an exact decimal string,
  SQLite compares it lexicographically, and `'9.50' > '10000.00'`. A too-small peak is
  a too-small drawdown and a breaker that sits quiet through the loss it exists to
  stop. Build log entry, and a test that asserts the wrong query is actually wrong on
  its own fixture before asserting the right answer.

**Audited and found sound, nothing added:** all six writes engine 19 needs already
exist — `write_block_record`, `write_equity_snapshot`, `write_position`, `write_order`,
`write_trade`, `write_rejection` — as do `count_open_positions` and
`latest_equity_snapshot`. Specs 49 and 50 need no new write surface.

**Still open, and it is C's:** `console/reader.py:453` `_blocked_ticks` still calls
`block_records_in_window(start_ts=_TS_MIN, end_ts=_TS_MAX)` and builds a row model for
every record in the table. Spec 51 says hand C the method name and stop, so I have.
Spec 51's "the cycle feed no longer performs an unbounded scan" is not satisfied until
C makes that one-line swap to `recent_blocked_ticks(self._feed_limit)`.

- **Manage-chain rehearsal for engine 19** — `tests/engines/test_manage_chain_rehearsal.py`,
  new file, my lane. *Claimed 2026-09-11, in progress.* Lead task, and the deliberate
  exception to "nobody writes a test for another agent's code": the rehearsal tests the
  **orchestrator wiring**, which is the lead's, not engine 19, which is C's. Held before
  registration, the same way A's guard-chain rehearsal was held before engines 7, 10, 11
  and 17 were registered. Two real ticks, not one. **If it goes red for a real reason I do
  not fix engine 19** — report to the lead and to C.
  ***Complete and green 2026-09-11. Ten tests, all passing — nothing to report about
  engine 19.*** It records a `data_guard` block with the manage chain still running on a
  blocked tick, writes no row on a clean tick while still reporting per-table counts
  including zeros, reports Phase 6 publishers absent rather than zero, and its second tick
  is genuinely its own. `ux_equity_snapshots_tick` has now been *seen* to fire: two
  orchestrators sharing a `run_id` collide on `cycle_id` 1, contract rule 7 turns the
  `IntegrityError` into ERROR, the tick completes and the first row survives. Six
  mutations, five killed, one equivalent and recorded as such. **N5 is the one that
  justifies the file**: with `cycle_id` cached on `self`, a single-tick rehearsal passes
  and five two-tick assertions fail — the two-tick rule measured rather than asserted.

  **One defect of my own, in the harness rather than the tests.** It restored mutated
  files only at the end of the run, so a mutation of `core/orchestrator.py` was still on
  disk while `engines/memory/engine.py` was mutated, and that verdict was really both
  together. Compounded mutants fail more tests, so every verdict drifts toward KILLED and
  a real survivor can hide. It very nearly cost the rehearsal its central claim — I would
  have written that a one-tick rehearsal catches N5, on a check that was measuring
  something else. Both files verified byte-identical by sha256 afterwards; neither is
  tracked by git, so `git checkout` was never a safety net and the verify step is the only
  reason this was recoverable.

#### Phase 3 branch-coverage backlog — `discover_migrations` closed 2026-09-11

Backlog item, not phase-gate work, picked up after spec 51. `tests/db/test_migrations.py`,
my lane. **The backlog said three survivors; the function has five refusal branches plus a
sixth path, and two survived wide — not three.** The count was overstated in one direction
and understated in the other, which is a better argument for re-checking wide than the
handoff's own. The item itself lives in `feature-specs/PHASE-3-TASKS.md` and in neither
the consolidated build log nor the tracker — the lead has since carried the whole backlog
into the tracker's open items.

Genuine survivors, now tested: **duplicate migration version** (unrefused, the second file
silently overwrites the first in a dict keyed on version and the set still looks
contiguous) and **no migration files in the directory** (unrefused, returns `()`, which
passes the contiguity check trivially and reports success over a database with no tables).

**The finding I was not sent to make, and it is the one worth keeping.** Two further
branches — directory-not-found and the non-`.sql` skip — are killed *only* by tests in
other agents' files that are not about migrations: a Phase 4 engine test that happens to
build a store over a missing path, and a research import-boundary test that happens to walk
this directory. They read as covered in any sweep and are covered by nobody. **An
incidental kill is worse than a survivor, because a survivor is at least on a list.** Both
now have tests next to the code they are about. All six branches are killed by
`tests/db/test_migrations.py` itself; every assertion is on the message and not the bare
type, because all five refusals raise `MigrationError`.

Sweep excluded `tests/scripts/`, which was red in A's lane at the time; the harness refuses
to report at all unless its baseline is green, because a sweep over a red tree marks every
mutation killed and manufactures a clean result out of someone else's broken tree. Shape of
that hole recorded in the build log.

#### For C — the ORDER BY anchor in `test_phase3_criteria.py` is single-occurrence by convention only

My first cut of `recent_blocked_ticks` reached for the same literal
`ORDER BY ts DESC, run_id DESC, cycle_id DESC` the outage walk uses, and
`test_an_outage_counted_by_cycle_id_is_a_fail` correctly refused: *anchor appears 2
times, expected exactly once*. Fixed in my lane — the feed query now tie-breaks
`cycle_id` before `run_id` — with a comment at the site saying not to tidy the two into
one wording. **C's count assertion is the only reason this surfaced at all**: a patcher
taking the first match would have mutated my new query, left the outage counter intact,
watched the Phase 3 criterion stay PASS, and reported a can-it-fail proof that had
itself stopped being able to fail. Worth knowing the anchor is textual and that the
next query in that file can collide with it again.

#### OPEN QUESTION for the tracker — engine 7 has no ranking score, and that is recorded

**Ruled by the operator on 2026-09-10 and not a defect**, but it belongs in
`context/progress-tracker.md`, which is the lead's, so it is raised here.

Invariant 4 describes engine 7's ranking as "a deterministic score over features". There
are no features in Phase 3, so **the ordering is the tie-break alone: pair name,
ascending**. The operator's reasoning: a placeholder score would be a check whose output
resembles the claim while the claim is untrue, and ranking one candidate out of a filtered
set is a Phase 5 decision made with real features in front of us.

**Phase 5 closes it.** It is isolated as one named function, `rank_universe` in
`scout/contracts.py`, so the fix is one edit against a named seam. `engines/scout/README.md`
says in as many words that alphabetical ordering is a recorded absence rather than a design,
so nobody reads it as a choice someone defended.

#### For the lead — the affordability check compares two currencies

`target_notional` derives from equity, which invariant 7 expresses in
`trading.base_reporting_currency`; the balance it is compared against is in the pair's
**quote** currency. Comparing them needs an FX rate and nothing in this system publishes
one, though invariant 7 says one is converted "at the trade timestamp".

**Engine 11 has carried the identical comparison since spec 35** and no test has ever
reached it on a pair whose quote is not the reporting currency, because no fixture has one
that gets that far. Found by writing the third caller, not by anything failing.

I ask the comparison only when the currencies match, with the reason at the call site. I
did **not** invent a rate, assume parity, or mint a "cannot be converted" exclusion — the
last would be inventing trading behaviour under cover of caution, and the ruling on A's
crypto-quoted heuristic is the precedent. The residue: a non-reporting-currency pair can
enter the universe without being shown affordable, which is the *over*-including direction
and the wrong one for `scout`. Unreachable today, reachable the moment
`allow_crypto_quoted` is enabled — and my own crypto-quoted test flips exactly that flag.

## CLOSED — engine 17's `CONDITION_ACTION`, ruled 2026-09-10

**The operator ruled on 2026-09-10 and spec 37 wrote it into invariant 14.** The table is
now a decision, not my reading of a contradiction:

| Condition | Action |
|---|---|
| `DRAWDOWN` | `freeze` |
| `LOSS_STREAK` | `freeze` |
| `ERROR_RATE` | `freeze` |
| `DATA_OUTAGE` | `close_all` |

`close_all` is reserved for the invariant 14 data-outage escalation and for the operator's
own Close all button. The reasoning, which is invariant 14's and is not restated in the
code: a drawdown or a losing streak is a statement about *past* trades — the data is
trustworthy and the positions are being managed — so liquidating on it realises a paper
loss on the system's own authority at the moment it has least evidence it is reading the
market correctly. A sustained outage is a statement about *present* knowledge, and unknown
exposure is worse than a bad fill.

Two of the four rows changed. `ERROR_RATE` and `DATA_OUTAGE` were already as ruled.

**Applied in the code on 2026-09-10, verified.** An earlier version of this line claimed
the same thing while `engines/safety/contracts.py` still carried the pre-ruling table
under a heading reading PROVISIONAL. It was written in the same edit that *claimed* spec
42, and this file has no way to distinguish a claim from a completion — so the note
described work that had not happened. The build log carries the account.

**Changed how I use this file as a result: a spec is marked complete here only after its
four gates are green, never in the edit that claims it.**

**Ratified earlier and unchanged:** the `BOUNDARY_SOURCE` table beside it, fixing whether
each threshold trips *at* its limit or *above* it, each with the sentence in the documents
that fixes it. Drawdown, loss streak and error rate trip at the limit; the outage is the
only strictly-greater one.

## CLOSED — a suppressed `close_all` swallowed a co-occurring `freeze`, ruled 2026-09-10

**The operator ruled the way it was recommended, and invariant 14 now says so** (committed
`db50392`): *"When the winning action is suppressed, `safety` emits the strongest action
that is not suppressed"*, rather than emitting nothing. Implemented under spec 42 as a
fall-through in `_emit`, with both directions tested — it fires when a lesser action was
genuinely due, and does **not** fire when the outage is the only condition tripped, because
"always freeze if you cannot liquidate" would freeze a healthy account over an outage it had
no exposure to. Both mutations confirmed caught.

Spec 42 step 6 is unrepealed: still one command per tick, still no `freeze` alongside a
`close_all` that actually emitted. Only the fall-through is new.

The original statement is kept below, because the reasoning is what the ruling was made on.

---

**Raised 2026-09-10 while implementing spec 42. Not invented behaviour: the literal spec
is implemented and this is the case it does not cover.**

`_emit` takes the strongest action among the tripped conditions and emits at most one row —
spec 42 step 6, "the more severe action wins and the two are not both emitted". Correct on
its face. But the `close_all` branch has two suppressions of its own (no exposure, and
`close_intent` already set), and when the strongest action is suppressed **nothing is
emitted at all**, including the `freeze` that a co-occurring drawdown, loss streak or error
rate would have emitted on its own.

Concretely: drawdown breached, account has no open position and no resting entry order,
and a data outage is also running. Drawdown alone emits `freeze`. Drawdown *plus* the
outage emits nothing, because `close_all` wins and is then suppressed for want of anything
to close. More bad conditions produce less action, which is the wrong direction.

The practical impact is bounded and worth stating so the ruling is not read as more urgent
than it is: `safety` returns `BLOCK` on every tick where any condition is tripped, so the
opportunity chain is stopped regardless. What is lost is the *persistence* — the mode never
goes `frozen`, so the console shows a running system and the block is re-derived every tick
rather than recorded once.

**I have not fixed it.** The obvious fix is "emit the strongest action that is not
suppressed", which would be one line, and it is a change to what the breaker does — so it
is the operator's, not mine. Recommending that reading.

*(Ruled that way on 2026-09-10 and implemented under spec 42. See the heading above.)*

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

1. ~~**`core/` must now call `store.set_system_mode(run_id, mode, at=now)`** from the
   command reader.~~ **DONE and this note is struck, 2026-09-10.** The lead wired
   `_persist_mode` at the command reader and asserted in `tests/core/` that the
   `system_mode` column staying NULL on an idle daemon is *correct* — a mode never entered
   is a mode never recorded — so that it does not get "fixed" later. Spec 31 is fully
   delivered.
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

## The one-type-many-causes shape, audited in my own lane — 2026-09-10

The lead asked whether `StoreError` in `clients/store/` has the shape A found in
`clients/kraken/`, where every fail-closed path raises one type so `pytest.raises(That)`
cannot tell the induced failure from one that happened first.

**Audited: four `raise StoreError` sites, so the shape is present but small.** They are the
non-finite money refusal, an unknown run mode, a duplicate `run_id`, and an unknown system
mode. Three of the four assertions already used `match=`; one did not —
`test_the_two_failures_are_distinguishable_by_type` — and it is now `match="unknown system
mode"`. That test is about `False`-versus-raise rather than about the cause, so it was not
wrong, but the bare form would have been satisfied by any of the four.

Nothing else in my lane raises one type from many places. `MissingInputError` in the three
engines is per-module and every assertion on it goes through `reason_code`, which is the
generalisation the standard actually asks for: **assert the reason, not only the `BLOCK`.**

## Reading a moving tree by path, and not re-running to find out — 2026-09-11

Recorded at the lead's request because it is process rather than code, and because the
habit is the deliverable.

Four times in Phase 4 the tree was red while I was working in it, and none of them was
mine. Each was settled **by path and by lane, without re-running anything and without
opening a file I do not own**:

- 26 failures in `tests/scripts/test_build_archive.py` — A's spec 54, mid-save. Left
  alone; green again on its own later, which is what landing looks like.
- `rejections_survive_restart` and `console_history_reads_real_rows` raising
  `AttributeError: module 'acsoe.engines.memory.contracts' has no attribute
  'DECISION_KEY'` — C's engine 19, mid-save.
- 2 pytest failures, 1 `mypy` error and 1 `ruff` error, all in
  `research/walkforward.py` and `tests/research/test_walkforward.py` — C's spec 53,
  mid-save.
- One failure that **was** mine, `test_an_outage_counted_by_cycle_id_is_a_fail`, which
  sits in C's `tests/verify/` by path and was still my defect. Path is the first
  question, not the last one: it named my file, it reproduced every time, and it was
  caused by a string I had just written.

**The rule that makes this work is the one Phase 3 paid for:** a defect of mine
reproduces every time, in isolation, in my own paths — and *re-running to see whether the
result changes* is the diagnostic that cannot fail, because in isolation nothing else is
touching the temp directory. The counter-example above is the important half. "It is in
another agent's path" is evidence, not a verdict; the verdict came from asking whether
the failure names my code and whether it reproduces, and once it did I stopped and wrote
the diagnosis before the fix.

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
