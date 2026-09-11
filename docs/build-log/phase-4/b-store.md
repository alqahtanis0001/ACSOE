# Build log — Phase 4 — b-store

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is now diagnosis-before-fix.** Write **What happened** and **Why** the moment you know
why something is broken, *before* you write the fix; come back and add **Fix** afterwards. The
code survives on disk whatever happens to the session; the reasoning that found it does not.
Phase 3 opened with an interruption that took every build log and no progress file, because
progress files are written before the work and logs were being written after it.

Minimum headings per entry: What happened, Why, Fix.

Two habits Phase 3 turned into standards, both of which belong in entries here:

- **Break the code and watch the test go red**, then put it back, and say in the entry that you
  did. A test nobody has seen fail is a claim, not a check. A mutation that survives a *subset*
  of the suite has not survived — it has not been asked.
- **Record what you checked and found sound**, not only what you found broken. An audit that
  lists hits alone says nothing about coverage.

The lead consolidates these into `docs/build-log/phase-4.md` at phase close.

## Entries

### Decision: two bounded `block_records` reads, because a row is not a tick

**Agent:** B · **Task:** spec 51 · **Date:** 2026-09-11

**Options.** Spec 51 asks for one thing: a most-recent-N read of `block_records` ordered by
`ts`, bounded by a caller's limit, to replace the console's
`block_records_in_window(start_ts=0, end_ts=<maxint>)`. The obvious delivery is one method
returning N rows, with the console grouping them per tick exactly as it does today.

**Chose.** Two methods. `recent_block_records(limit)` returns N *rows*.
`recent_blocked_ticks(limit)` returns N *ticks*, one row each, the primary blocker preferred.

**Because.** The guard chain never breaks early, so one tick writes one row per blocker, and
the console renders one row per tick. Truncate rows and *then* group and the oldest tick in
the window keeps whichever of its rows survived the limit — if the primary row was the one
cut, that tick renders as blocked by the wrong engine. Nothing raises, the row is
well-formed, and an operator reading the feed sees a plausible wrong answer. This is not
hypothetical: mutation M8 below is the naive implementation, and against B's real Phase 0
seed it disagrees with the unbounded scan from the seventh tick onward —
`('seed-run-0002', 3, 'data_guard')` where the truth is `('seed-run-0002', 3, 'exchange')` —
and drops twenty ticks that should have been there. `recent_blocked_ticks` picks whole ticks
first and reads only their rows, so a tick is either absent or complete.

**Cost.** Two statements instead of one, and one assumption stated in the docstring: engine
19 stamps every row of a tick with the same `context.now`, which is what makes the second
statement's `ts >= oldest` bound exact. A tick ever written across two timestamps would
appear twice in the first statement and the method would return *fewer* than `limit` ticks —
it under-fills, it does not mis-attribute.

### `SELECT MAX(peak_equity)` is the wrong query and it fails silently

**Agent:** B · **Task:** spec 51 · **Date:** 2026-09-11

**What happened.** Spec 51 item 3 asks that `peak_equity` be obtainable without reading the
whole equity series, and spec 50 requires engine 19 to take the running maximum from storage
rather than recompute it from `state`. The one-line answer anybody reaches for is
`SELECT MAX(peak_equity) FROM equity_snapshots`. It is wrong.

**Why.** Money in this schema is an exact decimal **string** — the columns are declared `ANY`
with `CHECK (typeof(col) = 'text')` precisely so a float is refused rather than stringified.
SQLite therefore compares them lexicographically, and decides `'9.50'` is larger than
`'10000.00'`. The aggregate returns a number, it is plausible, and it is too small. A
too-small peak is a too-small drawdown, so engine 17 `safety`'s breaker sits quiet through
exactly the loss it exists to stop. Nothing raises and no test about *equity* would notice.

**Fix.** `StoreClient.peak_equity()` returns the newest row's own carried-forward
`peak_equity` — one indexed row, the running maximum by construction, and the same value
`safety` already reads through `latest_equity_snapshot()`, so the two readers cannot
disagree. The trap is written into the docstring so the next person to "optimise" it into an
aggregate reads why not first.

**Consequence.** `test_peak_equity_is_not_a_lexicographic_max_over_the_column` asserts the
wrong query is *actually wrong* on its fixture (`MAX(peak_equity) == '9.50'`) before
asserting the right answer. Without that first assertion the test would pass on a fixture
where both queries happen to agree, and it would stop being a check the day somebody changed
the numbers. Mutation M6 is that aggregate, and it goes red.

### Mutations run for spec 51 — eight, all red

**Agent:** B · **Task:** spec 51 · **Date:** 2026-09-11

Each was applied to `src/acsoe/clients/store/client.py`, run against
`tests/clients/store/ tests/console/`, and reverted. None survived, so none needed re-running
against the whole suite. M8 was additionally run against the full suite (382 passed,
3 failed). Harness in the session scratchpad, not committed.

| # | Mutation | Result | Red message |
|---|---|---|---|
| M1 | `recent_block_records` ordered by `cycle_id DESC` instead of `ts DESC` — **the mutation spec 51 names** | RED | `assert [('run-a', 90... ('run-b', 1)] == [('run-b', 2)...'run-a', 900)]` |
| M2 | `recent_block_records` limit made ineffective (`LIMIT ? * 1000`) | RED | `assert [('run-b', 2)...'run-a', 900)] == [('run-b', 2), ('run-b', 1)]` |
| M3 | `recent_blocked_ticks` tick selection ordered by `cycle_id DESC` | RED | `assert [('run-a', 90...'run-a', 901)] == [('run-b', 2), ('run-b', 1)]` |
| M4 | `recent_blocked_ticks` limit made ineffective | RED | `assert [('run-b', 2)...'run-a', 900)] == [('run-b', 2), ('run-b', 1)]` |
| M5 | `recent_blocked_ticks` loses the `is_primary` preference, keeps the first row seen | RED | `assert 'safety' == 'data_guard'` |
| M6 | `peak_equity` implemented as `SELECT MAX(peak_equity)` | RED | `assert Decimal('9.50') == Decimal('10000.00')` |
| M7 | `peak_equity` returns the latest row's `equity` instead of its `peak_equity` | RED | `assert Decimal('4000.00') == Decimal('10000.00')` |
| M8 | `recent_blocked_ticks` implemented naively — group over `recent_block_records(limit)` | RED, 3 tests | `assert [('run-a', 5), ('run-a', 4)] == [('run-a', 5)... ('run-a', 3)]`; `assert 'safety' == 'data_guard'`; on the real seed, `At index 6 diff: ('seed-run-0002', 3, 'data_guard') != ('seed-run-0002', 3, 'exchange')` |

Two things the mutations taught that review had not:

**M1 and M3 are only killable on a two-run fixture.** `TWO_RUNS` in `test_store.py` spans
`run-a` cycles 900-902 and `run-b` cycles 1-2, so the `ts` and `cycle_id` orderings do not
merely reorder — under a limit they disagree about *which rows exist at all*. On a
single-run fixture both mutations survive. That last sentence was a claim until it was run:
the same five ticks written under one `run_id` give `[('run-a', 904), ('run-a', 903)]` from
*both* orderings, because within one run `cycle_id` and `ts` rise together and the two
queries are indistinguishable. This is the same fixture shape the Phase 0 seed was built
with and the reason it was built that way.

**Stated as the rule it actually is: a fixture must be capable of exhibiting the property
under test.** That is `code-standards.md`'s "a double must be capable of exhibiting the
property under test" aimed at the *data* rather than at a stub, and it is the same defect
wearing different clothes — a fixture that is simpler than the real thing in exactly the
dimension the test is about cannot fail, and reads as coverage. Here the dimension is
*more than one run in one database*. A single-run fixture is not a weaker version of the
ordering test; it is not the ordering test at all, because `ts` and `cycle_id` are the same
ordering within a run and no implementation can tell them apart. Every assertion in this
spec about ordering by `ts` is worth exactly what its fixture spans, and the question to
ask of any fixture is the one asked of a double: **what is the single property this exists
to demonstrate, and can this data exhibit it?** Asking it is not enough on its own, which
is why the paragraph above reports a run and not a judgement — the claim that a single-run
fixture lets M1 and M3 survive was believed before it was checked, and checking it cost one
throwaway script.

**M5 and M8 fail differently on the no-primary tick, and that distinction is load-bearing.**
With no row marked primary, the naive version keeps `safety` and mine keeps `data_guard` —
because `recent_block_records` orders `id DESC` and the second statement of
`recent_blocked_ticks` orders `id ASC`. The fallback is the *lowest* id on the tick, which
is the first blocker the guard chain recorded. Getting that backwards would put the last
blocker of the tick in the feed, which is the least informative row on it.

### A new query copied an ORDER BY string another agent's test anchors on

**Agent:** B · **Task:** spec 51 · **Date:** 2026-09-11

**What happened.** With spec 51's three methods green and `mypy`/`ruff` clean, the full suite
came back with `tests/verify/test_phase3_criteria.py::test_an_outage_counted_by_cycle_id_is_a_fail`
failing:

```
AssertionError: acsoe.clients.store.client: anchor appears 2 times, expected exactly once.
The engine moved underneath this test and the induced failure would not be the one it
claims to induce.
```

It is in C's lane by path, but it is my defect. It reproduces every time and it names my file.

**Why.** That test is C's proof that the Phase 3 outage criterion can fail: it rewrites the
literal string `ORDER BY ts DESC, run_id DESC, cycle_id DESC` inside
`clients/store/client.py` into a `cycle_id`-first ordering and requires the criterion to go
FAIL. The string was unique, because exactly one query in that file ordered ticks that way —
the outage walk in `stored_data_guard_outage_excluding_current_tick`. My new
`recent_blocked_ticks` selects its tick keys and reached for the same words, so the anchor
matched twice and C's patcher refused rather than patching an arbitrary one of them.

Worth saying plainly: **C's guard is the only reason this surfaced as a failure instead of a
false pass.** A patcher that took the first match would have mutated my brand-new feed query,
left the outage counter untouched, seen the Phase 3 criterion stay PASS, and reported that a
test proving the criterion can fail had itself stopped being able to fail. That is precisely
the shape this phase exists to catch, and it was caught by a one-line count assertion.

**Fix.** `recent_blocked_ticks` now orders its tick-key statement
`ORDER BY ts DESC, cycle_id DESC, run_id DESC`. The two queries order different things — one
orders grouped aggregates for the outage walk, the other distinct tick keys for the feed —
and giving them byte-identical text was mine to undo. The tie-break between `run_id` and
`cycle_id` is arbitrary within one `ts` and only has to be deterministic, so nothing about
the method's behaviour moves; `ts DESC` leads in both, which is the part that matters and the
part M3 mutates.

**Consequence.** Flagged to C, because the anchor stays single-occurrence only by
convention — nothing stops the next query in this file colliding with it again, and the next
person may not have C's counter to catch them.

### Audit for C: the six writers engine 19 needs, and the three that raise on purpose

**Agent:** B · **Task:** spec 51 · **Date:** 2026-09-11

**What was asked.** C's reading of spec 50 is that engine 19 persists the same position and
the same resting order on many consecutive ticks, and asked whether `write_position` and
`write_order` are upserts — because plain inserts would raise on tick two, and that would be
a spec 51 gap rather than anything C could fix in their own lane.

**What I found, and it is sound.** Both are upserts. Every writer except
`write_block_record`, `write_equity_snapshot` and `write_rejection` goes through `_upsert`,
which is `ON CONFLICT (<pk>) DO UPDATE` and deliberately **not** `INSERT OR REPLACE` —
`REPLACE` resolves a conflict on *any* unique index by deleting the conflicting row, so a
second open position for a pair would silently delete the first and defeat
`ux_positions_open_pair`. Keys: `positions` on `position_id`, `orders` on `userref`,
`trades` on `trade_id`, each the table's own PRIMARY KEY. Re-writing the same row every tick
is free. No writer is missing and none was added for spec 51.

**The three that still raise, all deliberately.** Worth recording because the natural reflex
on seeing an `IntegrityError` in a tick loop is to catch it:

- `ux_positions_open_pair` — UNIQUE `(pair) WHERE status = 'open'`. The same `position_id`
  re-written is fine; a *different* `position_id` opened on a pair that already has one open
  raises. That is invariant 6 enforced by the database rather than by convention.
- `ux_equity_snapshots_tick` — UNIQUE `(run_id, cycle_id)`, and `write_equity_snapshot` is a
  plain INSERT. One equity row per tick; a second write for the same tick raises.
- `ux_block_records_primary` — UNIQUE `(run_id, cycle_id) WHERE is_primary = 1`, which spec
  49 already tells C not to catch.

**Also confirmed for C:** `latest_equity_snapshot()` is
`ORDER BY ts DESC, id DESC LIMIT 1` — ordered by `ts`, with `id` only as a tie-break inside
one `ts`, never by `cycle_id` and never by `id` across two runs. C had asked specifically
because a database holding two runs would give the wrong newest row under an `id` ordering.
`peak_equity()` is a thin read over that same row, so the two readers cannot disagree.

### Branch sweep of `discover_migrations`: two survivors, and two worse than survivors

**Agent:** B · **Task:** Phase 3 branch-coverage backlog · **Date:** 2026-09-11

**What happened.** The backlog entry says `clients/store/migrations.py::discover_migrations`
(3), with the standing warning that the counts came from a narrow subset and some would die
on contact. Re-run wide, the function has **five** refusal branches, not three, all raising
`MigrationError` — the one-type-many-causes shape — plus a sixth path, the `continue` that
skips a non-`.sql` file. Disabling each in turn:

| Branch | Verdict | Killed by |
|---|---|---|
| directory not found | killed | `tests/engines/test_memory_rows.py::test_peak_equity_is_the_running_maximum_read_from_the_store` |
| filename not `NNNN_lower_snake_case` | killed | `test_malformed_migration_sets_are_refused`, both parameters |
| **duplicate version** | **SURVIVED** | nothing |
| **no migration files in the directory** | **SURVIVED** | nothing |
| versions not contiguous from 1 | killed | `test_malformed_migration_sets_are_refused[0002_second.sql-contiguous]` |
| non-`.sql` files skipped | killed | `tests/research/test_historical.py::test_the_live_loop_does_not_import_research` |

**Why the count was wrong in both directions, which is the useful part.** The handoff warned
that some of three would die. Two did not: two of the five are genuinely untested and the
third claimed survivor was one of the branches that had a real test all along. So the narrow
subset had **overstated** one and **understated** the total, and the warning was right for a
better reason than the one it gave.

**The finding the sweep was not looking for.** Two branches are killed only by tests in other
agents' files that are not about migrations at all — a Phase 4 engine test that happens to
build a store over a missing directory, and a research import-boundary test that happens to
walk the migrations directory. Those branches read as covered in any sweep and are covered by
nobody: the tests that kill them assert something else entirely, and either could be deleted
or rewritten tomorrow for reasons having nothing to do with this file, silently taking the
only coverage of a refusal branch with it. That is `code-standards.md`'s "a line everybody
runs is the line nobody thinks to assert on" arriving as an *incidental kill* rather than as
a survivor — and an incidental kill is worse than a survivor, because a survivor is at least
on a list.

**Fix.** Four tests in `tests/db/test_migrations.py`, my lane: the two genuine survivors, plus
one each for the two incidentally-killed branches so their coverage stops depending on
strangers. Every one asserts on the message, never the bare type — all five branches raise
`MigrationError`, so `pytest.raises(MigrationError)` alone cannot tell the induced failure
from a neighbour, which is the rule that started this whole backlog.

**Coverage hole in the sweep, stated so the next reader knows its shape.** `tests/scripts/`
was excluded from every run. It is red right now for reasons in A's lane — spec 54, mid-save
— and leaving it in marks every mutation "killed" regardless, which manufactures a clean
sweep out of somebody else's broken tree. The harness refuses to report at all unless the
baseline is green first, for the same reason. So: these verdicts are true of the whole tree
**except** `tests/scripts/`, and a branch killed only by something in there would show here as
a survivor. Given what that directory tests — A's archive builder — none of these six is
plausibly reached from it, but the hole is real and this is its shape.

### The mutation harness was compounding mutants across files, and it flattered itself

**Agent:** B · **Task:** manage-chain rehearsal · **Date:** 2026-09-11

**What happened.** The rehearsal's mutation run reported N5 (engine 19 caching `cycle_id`
on `self` across ticks) as killing six tests, including
`test_a_data_guard_block_is_recorded_by_the_manage_chain`, and reported that a
*single-tick* rehearsal would also have caught it — which would have meant the two-tick
rule this whole file is built on was not earning its keep. Run by hand, the same mutation
kills **five** tests, that test is not among them, and the single-tick check passes. The
harness and the hand run disagreed about which tests failed.

**Why.** My harness restores every mutated file in a `finally` at the *end of the run*,
not between mutations. It rebuilds each mutant from the pristine text of **its own file**,
so two mutations of the same file cannot accumulate — but N4 mutates
`core/orchestrator.py` and N5 mutates `engines/memory/engine.py`, and when N5 wrote the
engine, **N4's orchestrator mutation was still on disk.** N5's reported result was
N4+N5 together. With the manage chain skipped on blocked ticks — that is N4 — the
`data_guard` test fails for N4's reason and the single-tick check goes red for N4's reason,
and both were credited to N5.

**Why it matters more than a miscount.** Compounded mutants fail *more* tests, so every
verdict drifts toward KILLED. A sweep that silently compounds cannot report a survivor it
should have found, and it produces its most confident output exactly when it is most
wrong — the same shape as a sweep run against a red tree, which this harness already
refuses. It also nearly cost the rehearsal its central claim: I would have written in the
build log that a one-tick rehearsal catches N5, on the strength of a check that was
measuring something else.

**Fix.** Restore **every** tracked file to its pristine bytes before applying each
mutation, not only the file being mutated. Then re-run the whole set.

**Consequence.** `engines/memory/engine.py` is C's and `core/orchestrator.py` is the
lead's; both were verified byte-identical to their pristine bytes by sha256 after the
fault, and C's 41 tests pass. Nothing was left modified. The restore-and-verify discipline
is what made this recoverable at all — I could compare a hand run against a harness run
precisely because the harness put the file back between runs, and the files are untracked
by git, so `git checkout` was never available as a safety net.

### The manage-chain rehearsal: engine 19 is clean through the orchestrator

**Agent:** B · **Task:** manage-chain rehearsal · **Date:** 2026-09-11

**What it is.** `tests/engines/test_manage_chain_rehearsal.py`, ten tests, engine 19 driven
through the **real** `Orchestrator` over two consecutive ticks against a temporary store,
before the lead registers it in `bootstrap.py`. Written by B for C's engine on purpose, the
same exception A's guard-chain rehearsal was written under: **it tests the orchestrator
wiring, not the engine.** Nothing in it stages a `state` dict — every payload engine 19
reads arrives from a real engine through a real tick.

**The result is that there is nothing to report about engine 19.** All ten pass. It records
a `data_guard` block on a blocked tick with the manage chain still running, writes no
`block_records` row on a clean tick while still reporting per-table counts including the
zeros, reports Phase 6 publishers as absent rather than as zeros, and its second tick is
genuinely its own tick. C built it right and the registration pass should be a formality.

**`ux_equity_snapshots_tick` has now been seen to fire, which is the point of asking.** Two
ticks in one run mint two `cycle_id`s and do not trip it. Two orchestrators sharing one
`run_id` — a process restarting under a reused id, not a contrivance — each mint
`cycle_id` 1, and the second is the *same tick* by the only identity the schema recognises.
What happens is the right thing and it is worth writing down: contract rule 7 turns the
`IntegrityError` into ERROR, the tick completes, engine 19 publishes nothing, and the first
tick's row survives untouched. A second equity row for one tick would be two different
answers to "what was equity at tick 1", and `safety` reads the latest one, so it would
silently pick one.

Asserting that needed the orchestrator's logger, because a manage-chain engine that raises
leaves `state[engine.name] == {}` and nothing else — no status, no reason, unlike a guard
blocker. `assert state["memory"] == {}` alone would have been satisfied by engine 19 raising
for any of half a dozen unrelated reasons, which is the weak-assertion rule again. The test
asserts `IntegrityError` and `equity_snapshots` both appear in what the orchestrator logged.

**Mutations — six run, five killed, one equivalent.**

| # | Mutation | Result |
|---|---|---|
| N1 | rows keyed on the **previous** tick's `cycle_id` — *the mutation the lead named* | KILLED, 7 tests |
| N2 | no `block_records` row written on a blocked tick | KILLED, 4 tests |
| N3 | drop the `dict.fromkeys(WRITTEN_TABLES, 0)` initialiser | **SURVIVED — equivalent mutant** |
| N4 | manage chain skipped when the guard blocked (`core/orchestrator.py`) | KILLED, 5 tests |
| N5 | engine 19 caches `cycle_id` on `self` across ticks | KILLED, 5 tests |
| N6 | `written` reports only the tables it actually wrote | KILLED, 2 tests |

**N3 is an equivalent mutant and is recorded rather than fixed.** All six `WRITTEN_TABLES`
keys are assigned unconditionally later in `process`, so removing the initialiser changes
nothing observable and no test can kill it. It is not dead weight either: it is what would
keep the zeros guarantee if any of those six assignments ever became conditional. N6 is the
non-equivalent form of the same claim and it dies properly. Recording a checked negative
matters here — reported as a bare survivor it would send the next person to write a test
for a case that cannot fail.

**N5 is the one that justifies the whole file.** With engine 19 caching `cycle_id`, the
single-tick test `test_a_data_guard_block_is_recorded_by_the_manage_chain` **passes**, and
five two-tick assertions fail. That is the two-tick rule measured rather than asserted: a
one-tick rehearsal would have signed this off. I nearly published the opposite claim from a
harness that was compounding mutants — see the entry above.
