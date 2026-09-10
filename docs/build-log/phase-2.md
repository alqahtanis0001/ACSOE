# Build log — Phase 2: Data spine

Written by the agents as work happens, per `context/script-rules.md`.
Record every non-trivial problem and its fix. This cannot be reconstructed later.

The per-agent files are `docs/build-log/phase-2/{lead,a-platform,b-store,c-interface}.md` and
they remain exactly as the agents wrote them. This file is the consolidation made at phase close.

## Phase 2 summary

*Written by the lead at phase close, 2026-09-10.*

**What this phase was for.** Phase 0 built the structure and Phase 1 built the operator console
against fake data. Phase 2 is where the system first touches a real exchange. It builds the
*data spine*: the connection to Kraken, the thing that records what comes back, the thing that
turns a stream of individual trades into price bars, and a gate that refuses to let the rest of
the system act on data it should not trust. Nothing in this phase decides a trade. Its entire
job is to get honest data in and to be able to prove the data is honest.

**Built.** Nine specifications, 25 to 33, across three teammates and the lead.

- **Agent A — the exchange side.** A client for Kraken's REST API and one for its WebSocket
  stream; engine 1 `exchange`, which fetches account and pair information; engine 2
  `market_data_recorder`, which writes every incoming frame to an append-only file and produces
  the recording digest described below; engine 3 `market_sensor`, which builds 15-minute price
  bars from individual trades and is checked against Kraken's own published bars to within one
  price tick and a tenth of a percent of volume; engine 4 `data_guard`, which blocks the system
  when data is stale, when a spread is negative, or when a bar is missing, each with a different
  message an operator can act on; and a loader for Kraken's free historical archives that marks
  gaps and never invents a price to fill one.
- **Agent B — storage.** The system's operating mode (Idle, Running, Frozen) is now written to
  the database and survives a restart, as a column on the run record rather than as a separate
  state table. Agent B also built three engines belonging to Phase 3 — `cost`, `risk` and
  `safety` — concurrently, under an explicit operator ruling described below. Those three are
  **built but not done**, they were tested only against a mock exchange, and they were
  deliberately excluded from this phase's gate.
- **Agent C — the checks.** All six new Phase 2 exit criteria in `scripts/verify.py`. Each was
  proved twice before being trusted: once against a tree where the thing it judges does not
  exist, where it must report PENDING, and once against a deliberately fabricated subject, where
  it must report PASS. Each was also made to FAIL on purpose, because a check nobody has seen
  fail is a comment. Agent C also made the console's status band read the persisted mode, which
  was a debt carried over from Phase 1.
- **Lead.** The command reader in the orchestrator, which turned out to be broken in three
  separate places; the run record written at start-up and the mode written alongside it;
  registering engines 1 to 4; the configuration keys; the specifications themselves; and the
  minimum-recorded-fraction floor that closed the criterion defect described below.

**Verify output.** Re-run by the lead at close, independently of any teammate's report.

```
ACSOE verify - phase 2
repo: C:\Users\saad2\Documents\GitHub\ACSOE

PASS    docs_vocabulary                 14 files scanned, 9 retired terms, no hit
PASS    toolchain_green                 pytest, mypy --strict and ruff all green (python.exe)
PASS    commands_round_trip             real StoreClient through the real reader: activate and freeze applied and consumed on the claiming tick, close_all claimed but not consumed, and an interrupted close_all re-applied on restart and consumed only once done
PASS    recording_span_continuous       24.1h span tiled exactly by 10 recorded segment(s) and 9 accounted break(s); every break carries a cause; 99.98% of the span actually recorded, floor 98%
PASS    candles_match_kraken_ohlc       3 pairs, 9 bar(s): every OHLC field within one tick_size as AssetPairs reports it, volume within 0.1%
PASS    data_guard_blocks_bad_data      stale, negative-spread and missing-candle each block with a distinct operator-readable reason, and clean data passes
PASS    historical_loader_reports_gaps  3 gaps of 1/2/4 bars reported exactly, over 41 rows, and no timestamp in the output was absent from the input
PASS    console_shows_live_rows         a tick of exchange, market_data_recorder, market_sensor, data_guard wrote rows under the daemon's own run_id, and /api/state render them alongside the seed
PASS    console_reads_persisted_mode    a real daemon applied activate then freeze through the real store, and the band followed to `Running` then `Frozen`

9 criteria: 9 PASS, 0 FAIL, 0 PENDING
Phase 2 is green: every criterion PASS, zero PENDING.
```

Phases 0 and 1 were re-run at the same time and remain green: 7 PASS and 10 PASS respectively,
no FAIL and no PENDING in either.

**The recording, which is the part of this phase that could not be rushed.** Kraken publishes
free historical price archives going back years, so price history can be obtained at any time.
Those archives contain only open, high, low, close and volume. They contain no bid, no ask, no
spread and no order-book depth. That information exists only in the moment it happens; nobody
sells it afterwards, and if nothing was listening at three in the morning then that spread is
gone permanently. The project's central claim concerns whether a strategy can clear its own
trading costs, and trading costs are fees plus spread plus slippage. Fees come from Kraken's
API. Spread and slippage can only come from a recording somebody made at the time. That is why
`scripts/record.py` has been running since Phase 0 and why one of this phase's exit criteria
demands a continuous 24-hour recording — 24 hours specifically, because spreads are much wider
overnight than during European trading hours, and a recording covering only a working day would
report costs lower than they really are.

**Problems of note.** Four are worth reading in full below.

*The kill switch had never worked.* The orchestrator's command reader called a method on the
store that has never existed, so it silently did nothing: a running system would have ignored
every Activate, Freeze and Close-all command an operator ever issued. Two further faults sat in
the same forty lines, including one that would have re-run a liquidation against an already-flat
account on every subsequent restart. None of this was visible to any test, and the reason is
worth stating precisely: **every test of that seam used a stand-in for the store**, and each
stand-in implemented the shape the orchestrator asked for rather than the shape the store
actually had. Both sides passed their own tests while disagreeing with each other. A seam
exercised only through a stand-in is not tested; the stand-in is. The same question — *has
anything ever driven this seam without a stand-in on one side?* — is now asked of every other
seam before its phase closes.

*A gate that could not tell good evidence from bad.* The criterion for the recording required a
span of at least 24 hours, an exact accounting of every break, and a stated cause for each
break. The real archive satisfied all three while being **less than half recorded**. It would
have passed. The word *continuous* in the requirement did no work at all, because the check
measured the time between the first frame and the last and never asked how much of that time
had anything in it. This was found by an agent dry-running the report before depositing it
rather than after — the last moment at which finding it was still cheap. It is now closed by a
floor on the recorded fraction, set at 98% against a clean run.

*The recorder recorded its own death.* Part-way through the phase the machine's disk filled up,
and the recording contains the line `disconnect: OSError: [Errno 28] No space left on device`,
timestamped to the second. The one failure this whole apparatus exists to make impossible is a
break in the data that nobody notices, and the apparatus caught the break that killed it. That
is the strongest single piece of evidence in the phase that the gap-accounting design earns its
keep.

*A wrong belief that two people held and a thirty-second check dissolved.* Agent A reported that
two recorders were running at once and corrupting the archive with duplicate data. The lead
"corrected" the timeline and relayed a more confident version of it to the operator, and a
specification was written around the supposed corruption. It was false in both directions.
Windows lists a parent and a child process with identical command lines, so a single recorder
appears twice; and the timestamps that seemed to confirm it were being read as UTC when they
were local. Agent A settled it empirically by counting duplicate frames either side of the
supposed boundary and finding none. Both entries are left in the log uncorrected, with the
retraction appended after them, because this project's rule is that history is not rewritten.

**The pattern this phase produced eight times, which is the finding most worth carrying into the
dissertation.** Eight separate times, a check produced output that looked exactly like the claim
being made while the claim was untrue: a type checker that returned no answer at all because a
dependency's stub file would not parse, and was read as a clean result; a cleanup routine told
to ignore errors, which turned "do not fail the run" into "say nothing" while it silently filled
a disk; a byte-pattern match that would have split the recording in the wrong places; a
fabricated test fixture that agreed with the very mistake it was written to catch; the recording
criterion measuring elapsed time and calling it continuity; three separate files asserting that
a list was empty and calling that proof that a registry was empty; a regression test that passed
with the defect it targeted deliberately reinstated, because something else in the file already
made the failure impossible; and, at the close, the recording criterion again — unable to
distinguish an archive that was 76% recorded from one that was 99.98% recorded.

**Not one of the eight was caught by running the test suite.** They were caught by three things
only: an agent reading source code before building against it, an agent making a green test go
red on purpose, and an agent dry-running an artefact before committing it. All three are cheap,
and the phase produced a rule for the class as a whole — **an assertion is decayed if it would
still pass when the thing it names is false**, and its close relative, **a gate satisfied by the
shape of the evidence rather than by its content will accept fabricated evidence of the right
shape.**

**The recording window, and why the honest number is reported twice.** The clean 24-hour run
reports 99.98% of its span recorded. The full archive on disk, covering 47 hours, reports 76.2%
— pulled down by a ten-hour period when no recorder was running at all and by the disk-full
outage, both of which happened before the clean run began. The archive itself was **not
modified**: the window is applied to the report, never to the data, which is what invariant 11
requires. Both reports are committed side by side in `tests/fixtures/`, so the phase does not
close on a good number with the bad one quietly discarded.

**Deliberately deferred.**

- **The three Phase 3 engines are built, not done → Phase 3.** `cost`, `risk` and `safety` have
  only ever seen a mocked exchange. They did not count toward this phase's gate and Phase 3
  opens by wiring them to the real client.
- **`acsoe engine` cannot usefully run → Phase 3.** With the engines registered, the command-line
  daemon blocks on every tick because it is still constructed with three empty client slots. The
  tick *completes* and records both errors rather than crashing, which is the fail-closed
  behaviour the contract specifies, but the daemon does nothing useful. It needs two
  configuration values that do not exist, and an agent declined to invent a list of trading pairs
  to fill the gap. A test pins the current behaviour so that wiring the real clients turns it red
  and forces a deliberate rewrite.
- **Engine 17's condition-to-action table is unratified → operator.** It is policy, not
  implementation, and Agent B stopped rather than choose it.
- **Widening the lint and type-check scope beyond `src/` → still deferred**, for the third phase
  boundary running, deliberately and by the operator.
- **The cycle feed's full table scan → before Phase 4**, when the memory engine starts writing a
  row per guard per tick and it stops being harmless.

**A limitation that is now permanent enough to state plainly.** An intermittent fault on the
development machine has produced wrong results or outright crashes in every phase of this
project, inside five unrelated pieces of software — including one that is not compiled and one
that is CPython itself. It has never appeared in code that would run in production; it appears
in the seed generator, the test harness and the verifier, which is to say **in the apparatus
that gathers the evidence rather than in the system being evidenced**. The root cause was not
established, hardware is suspected, and the operator ruled it out of scope. It is mitigated by
retrying a crashed run once and never retrying a run that returned a verdict. Closing this phase produced the densest sample of it the project has taken. The gates were
re-run after every documentation change — roughly twenty gate runs in one session — and **four of
them reported FAIL: two on Phase 2, one on Phase 0, one on Phase 1.** Every one was this fault and
none was a defect. The failing tests differed every time and were scattered across unrelated
files; all of them passed when run in isolation immediately afterwards; and the only changes
staged at the time were Markdown, so the tree that failed and the tree that passed were identical.
One of the spurious failures landed on the test asserting that no credential was committed into
the recording sample — a false alarm that reads as a leaked secret in a public repository, which
is the clearest illustration available of why this matters. **Phase 2 is therefore closed on gates
that had to be run more than once**, stated plainly rather than smoothed over: the passes are real
and reproducible, the mitigation did what it was designed to do, and the fact that it had to is
the limitation. This belongs in the
dissertation's limitations chapter, stated in those terms, and it is recorded in full under
Known Risks in `context/progress-tracker.md`.

## Entries — lead

### Registration, and the sixth instance of the phase's pattern

**Agent:** Lead · **Date:** 2026-09-09

**What happened.** Engines 1 to 4 were registered in `bootstrap.py` in registry order, held back
until A had driven all four through two real orchestrator ticks in
`tests/engines/test_guard_chain_rehearsal.py`. `is_gate_matches_registry` went from a vacuous
"0 engines registered" to "4 engines registered; 0 mismatches (1 gates)", and
`console_shows_live_rows` went PENDING to PASS.

**Why it was held.** A read `check_orchestrator_empty_registry` before asking for registration and
found it reads the **live** `bootstrap.GUARD_CHAIN` while asserting `state["guard_blockers"] == []`
— so registering would have taken a **closed, green Phase 0** red. A's rehearsal is what supplied
the evidence: against the REST-only fake client the guard chain blocks every tick with
`no_market_data`, correctly, because `market_sensor` publishes no quotes.

**Fix.** C rebuilt the criterion to construct its own empty `Chains()`, keeping both `failed(...)`
branches untouched, and added a test driving the same fabrication through the *live* chains to
prove the blockers those branches refuse actually appear — without which the first test could pass
against a shape that could never have tripped the old code.

**Consequence, and it is the sixth instance.** Registration then broke three more tests holding the
same coincidence: two in A's `tests/cli/` and one in the lead's `tests/core/`. All three asserted
`guard_blockers == []` while their names claimed something about an *empty registry*. A's
generalisation is the form worth keeping: **an assertion is decayed if it would still pass when the
thing it names is false.** `guard_blockers == []` says nothing about an empty registry; it says
something about whichever registry it was handed.

The sibling rule — *fabricate the subject a criterion judges; never fabricate a contract it is held
to* — is already in `ai-workflow-rules.md`. This one belongs beside it and is recorded here pending
that edit.

**Worth stating about the phase as a whole:** six instances of *a check whose output looks like the
claim while the claim is not true*, and **not one was caught by running the suite.** Four were
caught by an agent reading source before building against it, one by making a green test go red on
purpose, one by dry-running an artefact before depositing it. Those appear to be the only three
techniques that work on this class of defect, and all three are cheap.

### Correction: there were never two recorders, and the lead amplified the error

**Agent:** Lead · **Date:** 2026-09-09

**What happened.** A reported two `record.py` processes appending to one archive. The lead
"corrected" A's timeline by checking process creation times and told both A and the operator that
the archive was single-recorded before 13:19:34Z and doubled after — which shaped a spec 28
instruction about de-duplicating across a boundary, and a warning to the operator that a mid-file
step would look like a market event.

**Why it was wrong, twice over.** Windows lists a **parent and a child with identical command
lines**, because this venv's `python.exe` re-executes the interpreter; starting one recorder
produces exactly that pair. And `1:19:34 PM` was **local** on a BST machine — `12:19:34Z`, not
`13:19:34Z` — which matches a restart after a recorded outage from `11:58:23Z` to `12:19:20Z`.

**How it was settled.** Empirically, by A, running its own duplicate-frame counter either side of
the supposed boundary: **zero duplicates at 12:30Z and zero at 05:00Z.** There is no duplication
anywhere in the archive.

**Fix.** The frame-level de-duplication stays — it is correct whether or not duplicates occur, and
the trade-level version A rejected would have deleted real volume. What does not survive is the
claim about *this* archive.

**Consequence.** The lead reasoned forward from a teammate's inference rather than back to the
evidence, and then relayed the result to the operator with more confidence than the underlying
observation supported. A already had the tool that settled it, written that same morning. The
phase's own lesson — *the evidence points somewhere other than the cause* — applied to the lead
this time, and the check that resolved it took thirty seconds.

### Decision: Phase 2 waits a day rather than closing on a half-empty archive

**Agent:** Lead · **Date:** 2026-09-09 · **Decided by:** the operator

**What happened.** A dry-ran `scripts/recording_report.py` against the real archive before
depositing the fixture, and found that the span would satisfy `recording_span_continuous` at
about 16:01Z while being **10.93 hours recorded out of 22.16, with 11.24 hours missing** across
eight accounted breaks.

**Why it would have passed.** The Phase 2 row asks for "a continuous span of at least 24 hours
with every break accounted for". The criterion enforces the accounting rigorously — exact tiling,
a non-empty `cause` on every gap — and enforces continuity **not at all**: it measures start-to-end
elapsed time, which makes the word *continuous* do no work. A 24-hour span with nothing missing
and a 24-hour span with eleven hours missing tile identically and pass identically.

That is the fifth instance this phase of **a check whose output looks like the claim while the
claim is not true**, after the mypy abort, `ignore_errors` on the workspace removal, the
`b'"gap"'` payload match and the fabricated `EngineContext`. It is the first that is a defect in a
spec the lead wrote rather than in an implementation, which is worth stating plainly: the pattern
is not something the teammates keep doing.

**Options.** Deposit as the criterion allows and close today; wait for the denser 09-09 span;
restart cleanly and take the report 24 hours later; or deposit now and add a recorded-fraction
floor.

**Chose.** The clean 24-hour run. The operator ruled.

**Because.** The current archive carries the duplicate-recorder boundary from 13:19:34 *and* a
self-inflicted disk outage at 13:06:37, in the phase whose entire subject is the data spine.

> **Correction, same day, and left in place rather than edited out per rule 6:** the
> duplicate-recorder boundary **did not exist**. See the entry above — a parent-and-child process
> listing plus a local-versus-UTC timestamp, settled empirically at zero duplicate frames either
> side. The decision stands on its other half: a 49%-recorded archive containing an outage we
> caused ourselves is still the wrong evidence to close a data-spine phase on. But one of the two
> reasons given here was false when it was given, and the operator decided partly on it.
Closing on it would be the weak PASS this project has refused five times in one phase. The fourth
option was rejected for a specific reason worth keeping: a floor set now would have to sit below
today's 49% to let this artefact through, which sets the bar at the number we happened to get
rather than at one anybody would choose.

**Cost.** Phase 2 cannot close today. Everything else in it is finished and waiting, which is an
uncomfortable state and an honest one. A restarted the recorder as a single process on a disk with
room, and the 24 hours runs from that moment.

**The row that made the case better than the argument did.** The recorder recorded its own death:

```
09-09 13:06:37 -> 13:06:39   disconnect: OSError: [Errno 28] No space left on device
```

The disk incident, timestamped to the second, from an independent source, corroborating B's
report exactly — including that the 736s and 1258s silences either side are processes dying and
being restarted. The one failure mode the whole recording apparatus exists to make impossible is a
break that goes unrecorded, and it caught its own. That is the strongest evidence in the phase
that the tiling requirement earns its keep, and it argues for keeping the requirement while fixing
what sits beside it.

**Still open:** a floor on `recorded_fraction`. Better asked once a genuinely clean 24 hours gives
a principled number to set it at. `recorded_fraction` itself is now reported either way.

### The command reader was broken in three places, not one

**Agent:** Lead · **Task:** first task of Phase 2, before any engine work · **Date:** 2026-09-09

**What happened.** `Orchestrator._consume_commands` looked up `store.claim_pending_commands`
through `getattr`. `StoreClient` has never had that method, so the lookup returned `None`, the
reader logged one debug line and returned, and a daemon wired to the real store ignored every
Activate, Freeze and Close-all ever written. Fixing it surfaced two more faults in the same forty
lines:

- `_mark_consumed` called `mark_command_consumed(command, now=...)`. The real signature is
  `(command_id, *, consumed_at)`. It would have raised if it had ever been reached — it never was,
  because the reader returned before getting there.
- `_clear_close_intent_if_finished` called `store.mark_close_all_consumed(run_id=..., now=...)`.
  Also absent. So even a **successful** liquidation left its row claimed-and-unconsumed, which is
  precisely the shape the startup replay looks for. The next restart would re-apply `close_all`
  against an already-flat account.
- The startup re-application of claimed-but-unconsumed rows did not exist at all. Nothing in
  `src/` called `claimed_unconsumed_commands()`, though `architecture-context.md` requires it and
  names the exact failure it prevents.

**Why.** Every one of these is a seam between two owners — the lead's `core/` and B's
`clients/store/` — and every test of that seam went through a double: `_Store` in
`tests/core/test_orchestrator.py`, and an adapter in `tests/console/test_commands.py`. Both doubles
implemented the shape the orchestrator *asked for* rather than the shape the store *has*, so both
sides passed their own tests while disagreeing with each other. **A seam exercised only through a
double is not tested; the double is.**

**Fix.** The reader is composed from the four methods `StoreClient` actually exposes —
`claimed_unconsumed_commands`, `pending_commands`, `claim_command`, `mark_command_consumed` —
entirely inside `core/`, renaming nothing in B's directory, per the operator's instruction. The
`close_all` row id is carried on the orchestrator until both manage engines report done, which is
what phase two of the two-phase consumption needs. `_to_micros` is duplicated in `core/` rather
than imported from `clients/store/contracts.py`, because invariant 0 says `core/` imports nothing
from the rest of the package and that boundary is worth more than six lines of reuse.

**Consequence.** `commands_round_trip` is registered for phase 2 and refuses every double: real
migration, real `StoreClient`, real `Orchestrator`. Only the config and clock are fabricated and
neither is part of the seam. C proves it can fail as part of spec 33 — a criterion nobody has seen
fail is a comment.

The question worth asking of every other row in `ownership.md`'s seam table before its phase
closes: *has anything ever driven this seam without a double on one side?*

### Decision: an unrecognised command is now consumed, not merely ignored

**Agent:** Lead · **Date:** 2026-09-09

**Options.** `architecture-context.md` says an unrecognised command is ignored and logged and never
blocks the loop. It says nothing about consumption, so either leaving it unconsumed or consuming it
was defensible.

**Chose.** Consume it, and log it.

**Because.** `pending_commands` filters on `claimed_at IS NULL`. A row claimed on the tick that
ignored it would never appear as pending again, and would sit claimed-and-unconsumed forever —
which is exactly what the startup replay hunts for. Every restart for the life of the database
would re-apply it. Ignoring a command is a *decision*, and a decision is complete the moment it is
taken, so `consumed_at` is the honest stamp.

**Cost.** A behaviour the context file does not describe, so it is recorded here and asserted in
`tests/core/test_orchestrator.py` rather than left to be rediscovered.

### Two edits outside the lead's lane, declared

**Agent:** Lead · **Date:** 2026-09-09

Fixing the reader broke two test files. `tests/core/test_orchestrator.py` mirrors `core/` and is
the lead's, so rewriting its `_Store` double to the real store's shape was in lane.
`tests/console/test_commands.py` is **C's**, and its `_StoreAdapter` existed only to work around
the defect I had just fixed — C had raised it as an open question rather than editing B's file,
which was the right call. I deleted the adapter and passed the real `StoreClient` straight in,
which makes that test strictly stronger: an adapter is a place a mismatch can hide.

That is still a write in C's directory, and rule 1 says no exceptions. Declared here rather than
left silent. The same judgement as the Phase 1 close: an operator-directed change, mechanical,
with the owning agent not running. If it becomes a habit rather than an exception, the rule has
stopped meaning anything.

### Decision: Phase 3's deterministic engines overlap Phase 2

**Agent:** Lead · **Date:** 2026-09-09 · **Decided by:** the operator

**Options.** Run Phase 2 with A carrying almost everything and B nearly idle, then start Phase 3
cold; or bring engines 10 `cost`, 11 `risk` and 17 `safety` forward and build them concurrently
against mocks.

**Chose.** The overlap, with a hard boundary.

**Because.** The phase rule exists to stop work standing on foundations that do not exist yet, and
these three do not. **They depend on the exchange only through a contract** — B agrees the
fee-tier and pair-rule shape with A against `clients/kraken/contracts.py` and builds against a
mock, which is the same "agree, mock, continue" rule that governs every other seam in the project.
And **`safety`'s six inputs have never depended on anything later than the Phase 0 seed**: all six
are written by engine 19 `memory`, which is Phase 4, and B built those fixtures in Phase 0 for
exactly this reason. Testing `safety` against the seed is the designed path, not a shortcut.

**Where the line is drawn.** Engine 7 `scout` stays in Phase 3 proper. It needs a real tradable
universe computed from live pair rules and balances — it depends on *data*, not on a contract, and
that is the whole distinction. The overlap covers engines that can be finished against an agreed
shape; it does not cover engines that need something real.

**Cost.** Three engines will exist having only ever seen a mock, which is not the same as being
finished. So they do not count toward Phase 2's gate, and **Phase 3 stays closed until Phase 2 is
green and all three are wired to A's real client.** The risk is that "built" gets mistaken for
"done" at the Phase 2 close; the tracker and the task list both say so explicitly, and the Phase 3
criteria will judge them against the real client regardless.

### Why the order book had to be recorded from day one

**Agent:** Lead · **Date:** 2026-09-09

Kraken publishes free historical archives going back years, so price history is available at any time. But those archives contain only open, high, low, close and volume. No bid, no ask, no spread, no order book depth.

That data exists only in the moment. Nobody sells it. If you were not listening at 03:14 last night, that spread is gone permanently.

The cost engine computes fees + spread + slippage. Fees come from Kraken's API. Spread and slippage can only come from the order book.

Without the recording: engine 10's cost gate cannot be backtested, which is the project's central contribution; engine 9 order_book has nothing to read; and any backtest would have to assume zero spread, which would flatter results and make them worthless.

Why 24 hours and not one: spreads are much wider at 4am than during European trading hours. A recording covering only a working day would report costs lower than they are. The 24-hour requirement forces a full daily cycle, quiet overnight periods included, so the friction estimate is honest.

It is the only input to the cost model that money cannot buy back later, which is why scripts/record.py has been running since Phase 0 and why the criterion insists on a clean unbroken day.

### The recording window: 76.2% over the whole archive, 99.98% over the clean day

**Agent:** Lead · **Task:** spec 27, phase close · **Date:** 2026-09-10

**What happened.** The clean 24-hour run finished at `2026-09-10T14:15:30Z` and
`scripts/recording_report.py` was run twice against the same untouched archive: once over
everything on disk, and once windowed to the clean run.

```
full archive   2026-09-08T16:01:22Z -> 2026-09-10T15:15:44Z   47.24h
               18 segments, 17 gaps, 17,870,629 lines
               recorded 36.00h  missing 11.24h  recorded_fraction 0.7620

clean window   2026-09-09T14:15:29Z -> 2026-09-10T14:19:59Z   24.07h
               10 segments,  9 gaps, 11,924,857 lines
               recorded 24.07h  missing 20.25s  recorded_fraction 0.9998
```

**Why the full-archive number is so much worse, and why it is not a recording defect.** Almost
all of the missing 11.24 hours is a **single ten-hour silence** from `2026-09-08T16:02:17Z` to
`2026-09-09T02:04:19Z` — 36,122 seconds of the 40,471 missing, 89% of the total — when no
recorder was running at all. The rest is the **disk-full outage** and its aftermath: the
recorder logging `OSError: [Errno 28] No space left on device` at `2026-09-09T13:06:37Z`, and
the 736s, 1258s and 583s silences either side of it that are processes dying and being
restarted. **Both causes predate the clean run**, which starts at `2026-09-09T14:15:29Z`, an
hour after the disk incident. Neither is a property of the recorder; both are properties of the
machine it was running on during the days the phase was being built.

**Why windowing is legitimate and not a thumb on the scale.** The window is applied to the
**report**, never to the archive. `--from` / `--to` select which frames the digest is computed
over; nothing is deleted, rewritten, backfilled or interpolated, and the raw JSONL on disk is
byte-identical before and after. That is invariant 11 exactly as written — *recorded data is
immutable, corrections belong in a derived layer with the original preserved* — and the digest
is that derived layer. The check that proves it: the full archive reports 9 gaps at or after
the clean-run start, and the windowed report contains those same 9 gaps and no others. The
window is a pure selection over one immutable input.

**And the full-archive report is kept as evidence, not discarded.**
`tests/fixtures/recording_report_full_archive.json` is committed beside
`tests/fixtures/recording_report.json`. A phase that closes on a 24-hour window while quietly
binning the report showing 47 hours at 76% is doing something this project would refuse if it
saw anyone else do it. Both artefacts are in the tree, the criterion judges the window, and
anybody reading the fixture directory sees both numbers.

**The part that belongs in the dissertation, and it is the eighth instance.** Until this week
`recording_span_continuous` **could not tell the two reports apart.** It required a span of at
least 24 hours, an exact tiling of segments and gaps, and a non-empty `cause` on every gap. The
full archive satisfies all three: 47 hours is more than 24, the tiling is exact, and every one
of the 17 gaps carries a cause — including the ten-hour hole, which is honestly described as
*"the recorder was not running"*. So the archive that is 76% recorded and the archive that is
99.98% recorded **tiled identically, carried causes identically, and would have passed
identically.** The word *continuous* in the phase row did no work at all.

What closed it is a `recorded_fraction` floor, now set at **0.98** and enforced. The criterion
prints the measured fraction beside the floor — `99.98% of the span actually recorded, floor
98%` — so the number the gate turned on is in the output rather than buried in the code. The
floor was deliberately not set back when the defect was found: the only archive available then
was 49% recorded, and any floor chosen to admit it would have fixed the bar at the number we
happened to have rather than at one anybody would choose. Setting it against a clean run is
what made 0.98 a principled number instead of a rationalised one.

**This is the eighth instance this phase of a check whose output resembles the claim while the
claim is untrue** — after the mypy abort behind a numpy stub error, `ignore_errors=True` turning
"do not fail" into "say nothing", the `b'"gap"'` payload match, the fabricated `EngineContext`
that agreed with the mistake it was meant to catch, `recording_span_continuous` measuring
elapsed time and calling it continuity, `guard_blockers == []` standing in for "empty registry"
in three separate files, and C's shallow-copy regression test that passed with the defect it
was written to catch deliberately reverted. **Eight in one phase, and not one of the eight was
caught by running the test suite.** They were caught by reading source before building against
it, by making a green test go red on purpose, and — this one — by dry-running an artefact
before depositing it.

The generalisation the phase has earned: **a gate that is satisfied by the shape of the evidence
rather than by its content will accept fabricated evidence of the right shape.** Tiling, causes
and elapsed time are all shape. `recorded_fraction` is content, and it is the only one of the
four that could tell a good day from a bad one.

### The intermittent fault beat the retry twice at the close, and a `tail` pipe nearly hid one

**Agent:** Lead · **Task:** phase close · **Date:** 2026-09-10

**What happened.** Closing the phase meant running the gates again after every documentation change — roughly **twenty gate runs in one session**, plus three direct full-suite runs. **Four runs reported FAIL: two on Phase 2, one on Phase 0, one on Phase 1.** Every one was the intermittent fault. None was a defect. The tree did not change between them, and by the end the only staged changes were Markdown.

**The failing tests were different every time, and scattered across unrelated files.** That is the tell: a real defect lands in the same place twice.

```
RETRIED AFTER CRASH: pytest CRASHED: the process died with 3221226505
(0xC0000409 STACK_BUFFER_OVERRUN) [...] the retry was clean
```

```
FAIL  toolchain_green   pytest exit 1:
ERROR tests/clients/store/test_seed.py::test_a_tick_with_two_blockers_contributes_one_to_the_outage
1074 passed, 1 error in 49.72s
(the first attempt crashed: the process died with 3221225477 (0xC0000005 ACCESS_VIOLATION))
```

```
FAIL  toolchain_green   pytest exit 1:
ERROR tests/engines/test_exchange.py::test_a_pair_removed_from_the_fixture_disappears_from_state
FAILED tests/platform/test_record_format.py::test_sample_contains_no_secret_shaped_key
1 failed, 1073 passed, 1 error in 48.16s
```

```
FAIL  toolchain_green   pytest exit 1:
ERROR tests/cli/test_entrypoints.py::test_the_console_port_comes_from_config_and_never_from_a_constant
1074 passed, 1 error in 47.33s
```

**Proved spurious rather than assumed spurious.** All three named tests were run together in isolation and passed in 0.72 seconds. The staged diff at that moment contained no source file, no test file and no fixture — only the tracker and these build logs. The tree that failed and the tree that passed were the same bytes. Three further full-suite runs gave `1075 passed`, `1075 passed`, and one native crash.

**The one that should worry a reader most.** `test_sample_contains_no_secret_shaped_key` is the test asserting that no credential was committed into the recorder sample. A spurious FAIL there reads as a leaked secret in a public repository — the most alarming sentence this suite is capable of producing — and it was false. **A fault that can fabricate that verdict can fabricate any verdict, in either direction**, which is the real reason this belongs in the limitations chapter rather than on a risk register.

**Why the crash-then-verdict shape is the important one.** The first attempt crashed, the retry ran, and **the retry returned a verdict rather than a crash** — 1074 passed with one ERROR, in `test_seed.py`, which is this fault's original recorded site from Phase 0. The mitigation retries a crash once and never retries a verdict, so the gate reported FAIL. That is the policy working as designed, not failing: **a rule that retries verdicts is a rule that retries real defects until they pass.** B recorded the first instance of this shape earlier in the phase; this is the second, and it is now a thing that happens rather than a thing that happened once.

**The mistake worth recording, which is mine.** The run that produced the first of the two FAILs was piped through `tail -3`. It printed `9 criteria: 8 PASS, 1 FAIL, 0 PENDING` and nothing else — **no criterion name, no message, no crash status.** Known Risks has said since Phase 1 to capture the full output, head included, and never to use a `tail` pipe. I wrote part of that warning and then did the thing it warns against, at the phase boundary, on the one run where the evidence mattered. The FAIL was only diagnosable because it recurred three runs later and was captured in full the second time. **If it had not recurred, this phase would have closed with an unexplained FAIL in its history and no way to tell whether it was the fault or a defect.**

**Fix.** None in code, and deliberately so. The evidence needed to tell this fault from a real failure is already in the criterion's output — both FAILs named the native crash in the same message — so nothing needs to be added; it needs to be *read*. What changes is the Known Risks entry, which now carries the captured output of both shapes and states plainly that a `toolchain_green` FAIL on this machine is not evidence of a defect until its full line has been read.

**Consequence for the dissertation.** This is the entry that moves the fault out of the risk register and into the limitations chapter. It is no longer a hazard that might affect the evidence; it demonstrably affected the evidence-gathering at every phase boundary, including this one, and the honest statement is that **every phase gate in this project is a retried measurement taken on hardware with a known intermittent fault.** What keeps that from undermining the results is narrow and worth stating precisely: all five sites the fault has been seen at — pydantic-core, `sqlite3`, pyyaml, CPython's `ast`, and the seed generator — are in the seed generator, the test harness and the verifier. **None is in a code path that runs in production.** The corruption is in the apparatus that gathers the evidence, not in the system being evidenced, and the four clean runs of the same gate in the same session are what make the PASS reproducible rather than lucky.


## Consolidated from the per-agent logs

Merged at phase close from `docs/build-log/phase-2/{a-platform,b-store,c-interface}.md`, which remain as the agents wrote them. The lead's own entries are above. Where an event appears in two agents' files — the recorder-count correction most of all — both accounts are kept, because the disagreement between them is the record of how it was settled.


## Agent A — Platform

*From `docs/build-log/phase-2/a-platform.md`, 28 entries.*

### `websockets` no longer exposes `exceptions` as a package attribute

**Agent:** A · **Task:** spec 25 · **Date:** 2026-09-09

**What happened.** `ws.py` did `import websockets` and referred to
`websockets.exceptions.WebSocketException` at module scope, copying the pattern in
`scripts/record.py`. Under `websockets` 17.1 that raises `AttributeError: module
'websockets' has no attribute 'exceptions'`. Because `tests/harness/fake_kraken.py`
imports the error types from `acsoe.clients.kraken`, the failure landed inside
`conftest.py` and **pytest exited 4 with nothing collected** — so the whole team's
suite reported nothing, not just mine. C and the lead both hit it within minutes.

**Why.** `websockets` uses lazy attribute loading (`websockets/imports.py`), and the
top-level package's `__getattr__` no longer resolves `exceptions`. `record.py` gets
away with the same expression only because it evaluates it inside a running
coroutine, by which time something else has imported the submodule.

**Fix.** `import websockets.exceptions` and `from websockets.asyncio.client import
connect` explicitly. Both submodules, no package-attribute lookups.

**Consequence.** `scripts/record.py` has the same latent expression and is *not*
changed — its line schema is validated by a Phase 0 criterion and spec 27 says do not
touch it. It works today because of when it evaluates, which is luck rather than
design; worth revisiting if that file is ever reopened for another reason.

### A token bucket that spun forever on a fraction of a token

**Agent:** A · **Task:** spec 25 · **Date:** 2026-09-09

**What happened.** `RateLimiter.acquire` hung. Not slowly — permanently, with no
error, no CPU spike attributable to it and no output. `pytest tests/clients/kraken`
sat at `..` and had to be killed twice; the first kill produced a faulthandler dump
whose only useful frame was `limiter.py:112 in acquire`.

**Why.** Floating point, in the classic place. The first version looped: refill, and
if the bucket is still short of `cost`, sleep the shortfall and try again. With a
capacity of 5 and a refill of 10/s the sixth acquisition sleeps 0.1s and the refill
returns exactly one token. The *eleventh* does not: the clock is at 0.5, `0.5 + 0.1`
is `0.6`, and `0.6 - 0.5` is `0.09999999999999998`, so the refill lands about `2e-16`
under one token. The next shortfall is therefore `2e-16`, the sleep computed for it is
`2e-17`, and adding `2e-17` to a float already at `0.6` changes nothing at all.
Elapsed time is then zero forever, the refill adds nothing forever, and the loop never
terminates. The injected clock made it deterministic; against a real clock it would
have been an intermittent stall in the path that prices every REST call, which is a
far worse thing to own.

**Fix.** Removed the loop. `acquire` now refills once, sleeps the shortfall at most
once, refills again, and then deducts `cost` **unconditionally** — letting the balance
go very slightly negative. That is exact over any number of calls, because the next
refill starts from the deficit, and it has no loop that can fail to terminate.

**Consequence.** The negative balance looks like sloppiness and is the opposite, so it
carries a comment in the code saying why, and the tolerance is a fraction of one token
rather than an epsilon somebody has to choose. Worth remembering as a shape:
*re-checking a float condition in a loop that sleeps the difference* will always
eventually fail to make progress. Compute the wait once and carry the remainder.

### Two test modules called `test_contracts.py` stopped the whole suite collecting

**Agent:** A · **Task:** spec 25 · **Date:** 2026-09-09

**What happened.** `tests/clients/kraken/test_contracts.py` collided with
`tests/core/test_contracts.py`, which has existed since Phase 0. pytest aborted
collection: `845 tests collected, 1 error`, **zero executed**. Under the operator's
new commit-at-every-boundary rule this blocked B and C from confirming finished work,
not just me — B had spec 35 green on its own subset and could not report it.

**Why.** Neither directory had an `__init__.py`, so pytest's rootdir-relative import
gave both files the bare module name `test_contracts`, and the second one imported
loses.

**Fix.** Added empty `tests/clients/__init__.py` and
`tests/clients/kraken/__init__.py`, and cleared the stale `__pycache__` in
`tests/clients/`, `tests/clients/kraken/`, `tests/clients/store/` and `tests/core/`.
Two levels, not one: `tests/__init__.py` already exists, so both are needed for
`tests.clients.kraken.test_contracts` to resolve.

**Consequence.** Chosen over renaming the file. A rename fixes this collision;
`test_rest.py`, `test_ws.py` and `test_limiter.py` are equally generic and the next
one would come free. Nothing else moved: `tests/clients/store/` still has no
`__init__.py`, so its modules keep exactly the names they had.

### Decision: the HTTP transport is injected above `httpx`, not at `httpx`

**Agent:** A · **Date:** 2026-09-09

**Options.** Test the REST client through `httpx.MockTransport`, the ordinary way, or
define a narrow `HttpTransport` Protocol the client depends on and inject a fake.

**Chose.** The Protocol.

**Because.** `tests/conftest.py`'s autouse network guard patches
`httpx.AsyncClient.send` itself, not the socket underneath it. A `MockTransport` sits
*below* `send`, so nothing reaches it inside a test and the only way to use one would
be to relax the guard — which spec 25 forbids in as many words and which C's spec 14
forbids for the same reason. Injecting one level higher leaves the guard exactly as
strict as it is while the envelope, the field mapping, the retention and the
credential handling are all covered offline.

**Cost.** One extra indirection, and a real `HttpxTransport` that no unit test
exercises. That transport does nothing but call `httpx` and wrap its error type; it is
confirmed by `--live`.

### Decision: the WebSocket client owns a thread, and the parse is lenient

**Agent:** A · **Date:** 2026-09-09

**Options.** Poll the socket once per tick from the synchronous loop, or run it
continuously on its own thread and let the engines drain a buffer.

**Chose.** The thread and the buffer.

**Because.** The loop tick is 60 seconds and the socket delivers continuously. Polling
once a minute would discard almost everything, and order-book and spread history is
the one class of data that cannot be recovered retroactively — which is why
`scripts/record.py` exists at all.

**The second half of the decision is the one worth recording.** The frame parse is
deliberately *lenient*: every frame is buffered verbatim regardless of whether the
trade and quote extractors understand it, and a frame they do not understand
increments `unparsed_frames` rather than raising. `AGENTS.md` says any Kraken payload
shape an agent remembers may be stale, so the field names in `_extract_trades` are an
assumption. If that assumption is wrong, the lenient version keeps a correct and
complete archive and simply stops building candles, which engine 4 turns into a block
— fail-closed, with the irreplaceable half intact. A strict parser would raise on
every frame and throw the archive away to protect the part that can be rebuilt from
it.

**Cost.** A wrong field name is quiet rather than loud, so `unparsed_frames` is exposed
and engine 2's report has to surface it.

### The one thing in this package that cannot be proved offline

**Agent:** A · **Task:** spec 25 · **Date:** 2026-09-09

**What happened.** Nothing yet — this is a recorded limitation rather than a fix, and
it is here so the next session does not mistake green tests for a working client.

**Why.** Two things in `rest.py` are assumptions about Kraken that no offline test can
falsify: the four `map_*` functions' **field names**, and `sign_request`'s **signing
scheme**. `AGENTS.md` says any endpoint shape an agent remembers is stale, the operator
has rotated the key so no live call can succeed, and the committed fixtures in
`tests/fixtures/kraken/` are a simplified shape C's harness owns rather than recorded
responses. So the tests prove the envelope, the retention, the money handling and the
redaction — all of which are ours — and prove nothing about whether Kraken would accept
or answer any of it.

**Fix.** Isolation and honesty rather than cleverness. The field mapping lives in four
named functions with no logic around them, so correcting it is a small obvious edit; a
renamed field surfaces as a `KrakenUnavailableError` **naming the field**, never as a
default. `sign_request` is one function, deterministic, and tested as such.

**Consequence.** Confirming both is a `--live` task for whenever the operator restores
a key, and it is recorded as the only open question in
`context/progress/a-platform.md`. It blocks nothing: every Phase 2 criterion runs
offline.

### The recording digest could not be deposited: the archive is 21 hours old, not 24

**Agent:** A · **Task:** spec 27 · **Date:** 2026-09-09

**What happened.** Spec 27's committed evidence is
`tests/fixtures/recording_report.json`, showing a continuous span of at least 24 hours
with every break accounted for. The real archive does not yet contain 24 hours:

    kraken_v2_2026-09-08.jsonl     2.5MB  2026-09-08T16:01:22Z -> 2026-09-08T16:02:17Z
    kraken_v2_2026-09-09.jsonl  1575.0MB  2026-09-09T02:04:19Z -> 2026-09-09T13:25:41Z

Total span **21h24m**, with a ~10-hour hole between 09-08T16:02 and 09-09T02:04 where
no recorder was running at all. The span crosses 24h at about **2026-09-09T16:01Z**,
provided `scripts/record.py` keeps running.

**Why it matters that the report was not written anyway.** The digest built from this
archive would be entirely *truthful* — the 10-hour hole appears as a gap with a cause,
because the digest accounts for unrecorded silence as well as for explicit `gap`
markers — and it would still **FAIL** `recording_span_continuous`, which requires 24
hours. That is strictly worse than the PENDING the criterion reports today. PENDING
means "the subject does not exist yet", which is true. FAIL means "the subject exists
and is wrong", which would not be. **Depositing early converts an accurate absence into
an inaccurate presence.**

**Fix.** None available in code, and that is the point worth recording: **the criterion
is satisfied by wall-clock time, not by anything anyone can write.**
`scripts/recording_report.py` refuses to write a digest whose span is under
`--min-hours` (default 24) and prints the numbers instead, so the refusal is mechanical
rather than a matter of somebody remembering. There is deliberately no flag that
fabricates a span.

**Consequence.** Everything else in spec 27 is finished and green; only the fixture
waits. Regenerating it later is one command — `python scripts/recording_report.py
--write` — rather than an archaeology exercise, which is why the script lives in
`scripts/` rather than being a throwaway.

### Two recorders were running at once, and the duplication is not uniform

**Agent:** A · **Task:** spec 27 · **Date:** 2026-09-09

**What happened.** Two `scripts/record.py` processes (PIDs 6968 and 46512) were
appending to the same daily file. I first assumed the whole 1.5GB file was doubled and
told the lead so. The lead checked the process creation times and corrected it: **both
started at the same second, 13:19:34 on 09-09** — about an hour before I looked, not
eleven. So everything before 13:19 is single-recorded and only the tail is doubled.

**Why the correction matters more than the original observation.** A uniform 2x would
be obvious in any volume series and easy to spot. **A discontinuity part-way through a
file is not** — it looks like a market event. Spec 28 builds 15-minute candles from
`trade` frames and its criterion asserts volume within 0.1% of a Kraken OHLC fixture, so
a naive build over this archive is correct up to 13:19 and doubled after, which no
tolerance would forgive and no eyeball would attribute to the right cause.

**Fix.** De-duplication belongs in the **derived** layer, not in the archive. Invariant
11: a recording is append-only and is never edited, backfilled or cleaned in place, so
the duplicate lines stay on disk exactly as they arrived and the candle builder is what
has to be idempotent over them. It also has to be correct **across the boundary** rather
than tuned to the doubled section — a de-duplicator calibrated on the tail would corrupt
the head.

**Consequence.** Neither process was killed. They are the operator's, they are
collecting data that cannot be recovered retroactively, and killing the wrong one loses
an open file handle mid-line. It is with the operator. Recorded here because a future
reader looking at that file's volume profile will otherwise spend an afternoon on it.

### A fast field scan that matched the value instead of the key

**Agent:** A · **Task:** spec 27 · **Date:** 2026-09-09

**What happened.** The digest scans gigabytes, so it reads `ts_recv` and `kind` out of
each line with a byte search rather than parsing the JSON. The first version searched
for the literal `b'"ts_recv":"'`. Every test in `test_report.py` failed with "no usable
line found in the recording": the fixtures are written with `json.dumps`, which emits
`"ts_recv": "..."` **with a space**, while `orjson` — which the recorder uses — emits
the compact form.

**Why.** Two serialisers, one hardcoded byte pattern. The production path happened to
match and the test path did not, which is the least useful arrangement of the two: it
would have passed CI on real files and failed on any recording that had been through
any other writer.

**Fix.** `_string_field(raw, key)` steps past the key, the colon, any whitespace and the
opening quote instead of matching a fixed prefix.

**The mistake worth recording is the one I made while fixing it.** The first repair also
loosened the `kind` detection from `b'"kind":"gap"'` to a bare `b'"gap"'`. That made the
tests pass and was wrong: a Kraken frame whose *payload* merely contained the word
"gap" would have been classified as a break in the archive, silently splitting a
segment. Matching the key and reading its value is the only version that is not a
guess. The first occurrence is safe because the recorder writes the seven schema keys
before `payload`, so a same-named key nested in a frame can never be reached first.

### Decision: the digest reports a tiling, not a gap count

**Agent:** A · **Date:** 2026-09-09

**Options.** Report an uptime percentage and a gap count, or report a `span`, a list of
`segments` and a list of `gaps` that together account for every microsecond in the span.

**Chose.** The tiling. C's criterion asks for it and it is the stronger property, so
this is a decision to agree rather than to negotiate — but it is worth recording why it
is stronger.

**Because.** A gap count can be **right while a break sits unaccounted for**. Two
segments with a hole between them that nobody compared produce a perfectly plausible
count of zero. A tiling has nowhere for that to hide: if the pieces do not abut, the
assertion fails. It also forces the digest to treat *unrecorded silence* — what a
recorder that was not running leaves behind, writing no marker precisely because it was
not there to write one — as a first-class gap rather than as an absence of evidence.

**Cost.** The digest has to reason about both kinds of break and about their
boundaries, which is more code than counting markers. `assert_tiles` in
`tests/clients/recorder/test_report.py` is the assertion that makes it worth it.

### numpy's stubs took `mypy --strict` from "one error" to "no answer at all"

**Agent:** A · **Task:** spec 28 · **Date:** 2026-09-09

**What happened.** The first module in `src/` to import `polars` — `market_sensor`'s
candle builder — turned `mypy --strict src/` into:

    numpy/__init__.pyi:737: error: Type statement is only supported in Python 3.12
    and greater  [syntax]
    Found 1 error in 1 file (errors prevented further checking)

**Why.** numpy 2.5's bundled stubs use PEP 695 `type` statements, and `pyproject.toml`
pins `python_version = "3.11"` — the project's declared floor. mypy treats a PEP 695
statement under a 3.11 target as a **syntax error**, and a syntax error inside a
followed import aborts the whole run. So the check did not return a wrong answer, it
returned **no answer**, in one of the four commands the definition of done leans on.
That is the part worth remembering: a tool that stops checking looks a lot like a tool
that found nothing wrong.

**Fix.** `follow_imports = "skip"` for numpy — which alone did **not** work, because
mypy still reaches the stubs through polars' own annotations, so `polars` had to be
listed too.

**Why not just raise `python_version` to 3.12**, which also makes it pass. Because
`requires-python = ">=3.11"` and `architecture-context.md` both declare 3.11 as the
floor, and pinning mypy to it is the only thing that actually checks the code runs
there. Raising it to satisfy a dependency's stubs would silently stop checking the
promise the packaging makes.

**Cost, stated rather than buried.** `polars` and `numpy` are now `Any` to mypy, so a
typo in a polars call is not caught. `engines/market_sensor/candles.py` is the only
module using polars today and every value it produces is re-validated through a pydantic
`Candle`, which is what makes that acceptable for now. Three ways out, none of them mine
alone: bump the declared floor to 3.12, pin `numpy<2.3` whose stubs parse under 3.11, or
keep this. Raised with the lead.

### Decision: the OHLC fixture's trades are real; its expected bars are not Kraken's

**Agent:** A · **Task:** spec 28 · **Date:** 2026-09-09

**Options.** Compare built candles against Kraken's own published OHLC, or against a
reference computation over the same recorded trades.

**Chose.** The reference computation — because the first option is not available, not
because it is better.

**Because.** `scripts/record.py` subscribes to `book`, `ticker` and `trade`, so the
archive contains **no OHLC channel** to compare against, and no live call can be made:
the operator has rotated the key. So `tests/fixtures/kraken/ohlc.json` holds real Kraken
v2 `trade` frames taken verbatim from `data/raw/` — 1,997 trades across three bars for
BTC/USD, ETH/USD and SOL/USD — and the expected bars are computed by a deliberately
naive pure-Python reduction in `scripts/ohlc_fixture.py` that shares no code with the
`polars` implementation under test.

**What that is worth, and what it is not.** It catches a bug in the bucketing, the
grouping or the `Decimal` handling, which is what the criterion is actually for. It
**cannot** catch a shared misunderstanding of what a candle is, because both
implementations are mine. That limitation is written into the fixture's own
`provenance` field rather than left for a reader to infer, and confirming these bars
against Kraken's published OHLC is a `--live` task.

**Cost.** A weaker guarantee than an independent source, stated as such in three places
so nobody mistakes a PASS for more than it is.

### Frame-level de-duplication, never trade-level

**Agent:** A · **Task:** spec 28 · **Date:** 2026-09-09

**What happened.** Two `record.py` processes ran concurrently from 2026-09-09T13:19:34Z,
so part of the archive holds every frame twice. The obvious de-duplication — drop
duplicate *trades* — is wrong, and would have been very hard to notice.

**Why.** Two recorders produce byte-identical **frames**. Two genuinely identical trades
— same price, same quantity, same second — arrive inside **one** frame, not two, and are
a normal thing for a busy pair. De-duplicating at the trade level would therefore delete
real volume, quietly, in proportion to how active the market was.

**Fix.** `scripts/ohlc_fixture.py` de-duplicates on a SHA-256 of the frame payload plus
its exchange timestamp, and `build_candles` does not de-duplicate at all. The archive
itself is never edited — invariant 11 — so this happens on the way into the derived
artefact and nowhere else.

**Consequence.** The fixture was extracted from 03:00Z on 09-09, comfortably before the
duplication began, and reports `frame_duplicates_dropped: 0` — so the de-duplication is
in place and was not needed for this artefact. That is the right order: build it before
the comparison, not after the comparison surprises somebody.

### A native crash after a clean pass, not reproducible

**Agent:** A · **Task:** spec 28 · **Date:** 2026-09-09

**What happened.** `pytest tests/engines/test_market_sensor.py -q` died after the tests
themselves had all passed, dumping a faulthandler trace whose visible frames were all
pytest session teardown and `runpy`. I had piped to `tail`, so **I do not have the head
of the trace** — which is the only part that names the fault.

**Why it is recorded anyway.** Four immediate re-runs of the same file all exited 0 with
20 passed, and the full suite ran clean at 983 passed. Known Risks records an
intermittent native fault in the seed write path; this file touches no seed and no
SQLite, so it may be a different one — but with no head to the trace I cannot say that,
and saying it without evidence would be worse than saying nothing.

**Fix.** None. Flagged to the lead. The lesson is procedural and was already in the
brief: **capture the head of the output, not the tail.** The tail of one of these is
always `runpy` frames and says nothing at all.

### The loader's pydantic boundary, and exactly what it does not cover

**Agent:** A · **Task:** spec 30 · **Date:** 2026-09-09

**What happened.** `research/historical.py` is the second module in `src/` to import
`polars`, which is the point at which the mypy compromise recorded above stops being
comfortable. That compromise was acceptable because `engines/market_sensor/candles.py`
re-validates every value it emits through a pydantic `Candle`; a loader that returned a
dataframe would have no such boundary.

**Fix.** `load_archive` returns an `ArchiveReport` — a frozen pydantic model — and every
number a caller acts on is a validated field on it: `gap_count`, `row_count`,
`timestamps`, `duration_buckets`, `largest_gap_bars`, `missing_bars`,
`duplicate_timestamps`, `out_of_order_rows`. So the same property holds for both polars
users.

**What it does not cover, stated rather than implied.** **The dataframe itself is
unvalidated.** `to_frame` builds a `pl.DataFrame` and `load_archive` writes it to Parquet
when asked, and nothing type-checks that call chain while polars is `Any` to mypy. The
guarantee is "every value the loader *reports* is validated", not "the loader is
type-checked". A reader who takes the pydantic boundary as covering the frame would be
wrong.

**Money never goes through polars' parser at all.** The CSV is read with `csv.reader` and
the money columns become `Decimal` in Python before polars ever sees them, so an exact
value cannot be lost to a float on the way in. polars does the columnar work afterwards,
on values that are already exact. That is a stronger property than reading the CSV with
polars and casting, and it is the reason the reader is `csv` rather than
`pl.read_csv`.

### Measured: `numpy<2.3` restores full type checking, and nothing objects

**Agent:** A · **Task:** spec 30 · **Date:** 2026-09-09

**What happened.** The lead asked for a measured answer rather than a third hypothetical
about the mypy compromise. Tested without touching the shared virtualenv — other agents
run against it — by installing numpy 2.2.6 into a scratch directory and prepending it to
`PYTHONPATH`.

**Result, with the `numpy`/`polars` override in `pyproject.toml` disabled entirely:**

    mypy --strict src/   -> Success: no issues found in 65 source files
    pytest tests/ -q     -> 1029 passed in 45.57s

And polars typing is genuinely live rather than merely silent, which is the part worth
proving separately — a scratch file calling a method that does not exist:

    error: "DataFrame" has no attribute "sort_bogus"  [attr-defined]

Under the current arrangement that call type-checks clean, because polars is `Any`.

**Why the proof needed its own step.** "mypy passes" is exactly what the broken state
produced too. A configuration that stops checking and a configuration that finds nothing
wrong print the same line, which is the failure this phase has now hit four times in four
different places. The only way to tell them apart is to hand the checker something it
ought to reject.

**Not committed.** The finding went to the lead with the other two options; the version
ceiling is a dependency decision and not A's to take alone.

### Spec 30's fabricated archives, and the assertion that matters

**Agent:** A · **Date:** 2026-09-09

**Options.** Assert the loader's gap statistics, or also assert the output's timestamps
against the input's.

**Chose.** Both, as separate tests, and the second one is the one to keep if either has
to go.

**Because.** A loader that counts gaps correctly **and** emits filled rows passes every
gap assertion. It reports three gaps of 1, 2 and 4 bars, buckets them correctly, names
the largest — and quietly hands Phase 4 a continuous series containing candles at prices
that never traded. The triple-barrier labeller then walks forward from a decision bar,
touches a barrier that never existed, and produces a label the model learns from. Nothing
raises, nothing looks wrong, and every chart looks tidier than the truth.

`test_no_timestamp_in_the_output_was_absent_from_the_input` is the only assertion in the
file that catches it, and `test_the_series_is_left_discontinuous_on_purpose` states the
same thing positively: after loading an archive with a hole, consecutive output
timestamps are **not** all one interval apart, and that is correct.

**Also worth recording: a test I wrote badly and rewrote.** The first version of
"the loader offers no way to fill a gap" scanned the module's *text* for `interpolate`,
`forward_fill` and friends. It failed immediately — because the module's docstring says
"interpolate" repeatedly, on purpose, since saying so is most of that docstring's job. A
text scan would have forced the prose to stop saying the thing it exists to say. It now
walks the module's AST and looks for those names as *identifiers*, which is what was
meant. A second test in the same file was circular in the same way — it scanned its own
source for a string it itself contained — and was deleted rather than patched, because it
asserted nothing a fresh clone does not already enforce.

**Cost.** Three of the loader's tests are about what the loader must *not* do, which
reads oddly next to the ones about what it does. That is the correct ratio here.

### A shared fixture that three tests quietly rewrote for each other

**Agent:** A · **Task:** spec 29 · **Date:** 2026-09-09

**What happened.** `test_each_bad_scenario_differs_from_clean_in_exactly_one_respect`
failed with `('stale', ['missing_bars', 'quotes'])` — the `stale` fixture had somehow
acquired a missing bar. It had not been written that way.

**Why.** `BAD_DATA_SCENARIOS` is a module-level mapping of nested dicts, and my test
helper did `dict(BAD_DATA_SCENARIOS[name])` — a **shallow** copy. The outer dict is new;
`state["market_sensor"]` is the *same object* as the fixture's. An earlier test set
`state["market_sensor"]["missing_bars"]` to exercise a multi-finding tick, and from that
point on every test in the file, and every consumer of the module, saw a `stale` fixture
that was also missing a candle. The failure surfaced three tests away from the cause and
blamed the fixture rather than the test that had rewritten it.

**Fix.** `bad_data_state(name)` in `engines/data_guard/contracts.py` returns a
`copy.deepcopy`, and every test that intends to modify a scenario goes through it.

**Consequence, and the reason this is worth an entry.** `scripts/verify.py` does the
same shallow copy — `dict(scenarios[key])` — and is **correct today** only because the
engine does not mutate what it is handed. That is a property of the current
implementation, not of the interface, so it is exactly the kind of thing that stops being
true without anyone noticing. C has been told; the deep-copy factory is documented as
the way to take a scenario you intend to change; and the assertion that each bad scenario
differs from `clean` in exactly one respect is what caught it and stays.

The fixture-sharing itself is right and I would do it again: the fixtures live in the
engine's own contracts module so that a criterion and a test suite cannot drift from the
engine's idea of `state["market_sensor"]`. Sharing the *shape* is the point; sharing
mutable *instances* was the mistake.

### A fourth reason code, and why it is not just "stale"

**Agent:** A · **Task:** spec 29 · **Date:** 2026-09-09

**What happened.** The spec names three block conditions. Engine 4 emits four, and the
extra one is `no_market_data`.

**Why.** Invariant 3 says a gate that cannot reach its data blocks, so the empty case
needs a verdict whether or not the spec enumerates it — and it is not hypothetical: C's
fake Kraken client is REST-only, so on the real tree `market_sensor` publishes no quotes
and this is the code that fires.

I tried folding it into `market_data_stale` first, and the **prose** is what stopped me.
"Market data is older than the guard allows" is a false sentence when there is none, and
it would send an operator looking for a lagging feed rather than an absent one. Those
have different causes and different fixes.

**Fix.** A distinct code, agreed with C before landing rather than after — C's own
standing request, and the right order: `REASON_PROSE` is C's surface, and a code missing
from it renders as "No reason was recorded." **silently, with no error anywhere.**

**Consequence.** `test_every_reason_code_exists_in_the_consoles_prose_map` derives the
list from this engine's own constants rather than repeating it, so adding a fifth code
without telling C fails in A's own suite instead of going quiet on the console.

### Decision: the gate blocks on a hole in the candle series, and the loader still must not fill one

**Agent:** A · **Date:** 2026-09-09

**Options.** Treat a missing candle as a data fault and block, or treat it as the quiet
market it is and pass — which is what `architecture-context.md` says about the *archive*.

**Chose.** Block, and write down at length why that is not a contradiction.

**Because.** The two rules are about different acts. `architecture-context.md` and spec
30 govern **labelling**: a missing candle means no trades occurred, so inventing one
fabricates a barrier touch and poisons a label. Engine 4 governs **trading**: acting on a
series with a hole in it risks money on a price nobody observed. Fail-closed points in
opposite directions for the two, and both directions are the cautious one.

**Cost.** It reads like a contradiction on first encounter, and the obvious "fix" for
either half breaks the other. So it is stated three times — next to the constant in
`contracts.py`, in the engine README, and in a test whose name is the claim — and C
carried it into the comment above the reason codes as well.

### The registration rehearsal, run before asking for it

**Agent:** A · **Task:** specs 26-29 · **Date:** 2026-09-09

**What happened.** The lead deferred `bootstrap.py` registration until the tree was
globally green, on the grounds that registering `data_guard` as a real gate changes what
`orchestrator_empty_registry` — a **Phase 0** criterion — exercises on every tick.

**Fix.** `tests/engines/test_guard_chain_rehearsal.py` drives the **real** `Orchestrator`
over all four engines against C's fake client, twice, before the request is sent. Two
ticks rather than one on purpose: `state` is fresh every tick except `state["system"]`,
and an engine that quietly depended on something surviving would pass a single-tick test
and fail the second.

**What it found, which is worth knowing before registration rather than after.** Against
the fake client the guard chain **blocks every tick**, with
`state["data_guard"]["reason_code"] == "no_market_data"` — the fake is REST-only, so
there are no quotes. That is correct, and it completes the tick rather than raising,
which is the thing that matters: C's `console_shows_live_rows` turns an exception during
a tick into a FAIL naming it.

And with `data_guard.max_data_age_s` still absent from the config, the tick **still
completes**: `config.get` raises, the orchestrator converts it to `ERROR` with
`blocks_trading=True`, and engines 1 to 3 have already reported. So registering engine 4
before the operator supplies the key degrades the loop to "blocked" rather than breaking
it — which is the fail-closed outcome, and is asserted rather than assumed.

### The Windows file-handle teardown ERROR: hardened, not fixed, and the difference matters

**Agent:** A · **Task:** Phase 2 housekeeping · **Date:** 2026-09-09

**What happened.** B saw `tests/cli/test_entrypoints.py::test_console_refuses_an_unset_operator_key`
produce a teardown **ERROR** — not a FAILED — on one run, and it did not reproduce. The
fixture's own docstring already predicted the class of fault: `configure_logging()`
replaces the root logger's handlers process-wide, and a `TimedRotatingFileHandler` left
open holds a file inside a directory pytest is about to remove, which on Windows is an
error rather than a warning.

**Why it could not have been that test.** I could not reproduce it either, and reading
the code says why: `_isolated_runtime` is **autouse** in that module and already closed
every root handler on teardown, and the test in question returns 2 from the config
refusal *before* `configure_logging()` is ever called. So nothing in that module opened
a handle and nothing in that module failed to close one.

**What it probably was.** A handler leaked by a test in **another** module points at
*that* module's `tmp_path`, survives into this one, and is still open whenever pytest
gets round to collecting the older directory. The error then lands on whichever test
happens to be running when the collection happens — which is exactly the shape of the
observation: seen once, here, unreproducible, and with no local cause.

**Fix.** `_release_log_handlers()` is now called **before** the yield as well as after.
Releasing on entry means this module cannot be the place a stranger's handle comes due.

**Why this is filed as hardening rather than a fix, deliberately.** It does not stop
another module leaking a handler; it stops that leak being charged to this one. Claiming
it fixed a fault I could not reproduce would be worse than saying what it actually does.
If the ERROR reappears somewhere else, the same treatment belongs in whichever module
opens the handle — and the search should start with modules that call
`configure_logging()` without an autouse teardown, not with the module that reports it.

### A background thread that would have died silently

**Agent:** A · **Task:** Phase 2 hardening · **Date:** 2026-09-09

**What happened.** Reviewing `ws.py` after spec 29, not because anything failed:
`_run` caught only `_TRANSPORT_ERRORS` — `OSError` and `WebSocketException`. Anything
else escaping `_session` would end the coroutine, end `asyncio.run`, and end the thread.

**Why that is worse than an ordinary uncaught exception.** There is no caller to raise
into. The thread is a daemon, the traceback goes nowhere anybody looks, and the process
carries on perfectly happily with `connected` false and no frames arriving. **A dead
recorder is indistinguishable from a quiet market** — which is the single failure the
entire recording apparatus exists to make impossible, and the reason the digest reports a
tiling rather than a gap count. Every candidate cause is real: a pydantic
`ValidationError` from a frame shape nobody predicted, a `RecursionError` on a pathological
payload, a `MemoryError`.

**Fix.** `_run` now also catches `Exception`, records the break as a **gap** carrying
`unexpected <ExceptionType>: <message>` as its cause, and reconnects on the same backoff.
Engine 2 appends that gap to `data/raw/` on the next tick exactly like a disconnect.

**Why that is not a swallowed exception, which is the obvious objection.**
`code-standards.md` forbids `except Exception` without re-raising *or logging with the
traceback*. This does the durable equivalent of the second: the failure reaches the
append-only archive, where it outlives the process, rather than a log line that
`logs/` rotates away in fourteen days. It reconnects rather than stopping because a
recorder that gives up loses data nothing can recover; and if the fault is permanent the
backoff climbs to its 60-second ceiling and the archive fills with identically-caused
gaps, which says so about as plainly as anything could.

**Also added while there.** `test_start_and_stop_are_idempotent_and_the_thread_actually_exits`
drives the real thread against a socket that connects and then delivers nothing — the
shape a real socket has on a quiet market, and the one that would hang shutdown if
`stop()` did not reach the loop thread through `call_soon_threadsafe`. The thread
lifecycle was the only part of this client with no coverage at all, which is a poor place
for that to be true.

### The recorder recorded its own death, and the criterion could not see the hole

**Agent:** A · **Task:** spec 27 · **Date:** 2026-09-09

**What happened.** A dry run of `scripts/recording_report.py` on the real archive — ten
seconds over 5.3 million lines — before the span had reached 24 hours, so that the final
step would hold no surprises. It held one:

    span 2026-09-08T16:01:22Z -> 2026-09-09T14:11:09Z  (22.16h)
    segments 9  gaps 8  lines 5315829
    recorded 10.93h  missing 11.24h

**Nearly half the span is missing**, across an overnight hole of ten hours when nothing
was running, four silences of 5 to 23 minutes, and two recorded disconnects.

**The row that matters most:**

    09-09 13:06:37 -> 13:06:39  disconnect: OSError: [Errno 28] No space left on device

**The recorder recorded its own death.** That is the disk-full incident timestamped to
the second, from a source entirely independent of the process that reported it, and it
corroborates B's account including the restarts either side of it. It is also the
strongest demonstration in the phase that the gap-accounting design earns its keep: the
one failure mode the whole apparatus exists to make impossible is a break that goes
unrecorded, and the apparatus caught the break that killed it.

**Why it was escalated rather than deposited.** The criterion would have **passed** on
this archive at 16:01Z. `check_recording_span_continuous` requires a span of 24 hours,
an exact tiling, and a non-empty cause on every gap — and requires **no minimum recorded
fraction at all**. It measures start-to-end elapsed time, so 24 hours with zero missing
and 24 hours with eleven hours missing tile identically, carry causes identically, and
pass identically. The phase row says "a continuous span of at least 24 hours"; the
criterion enforces the accounting rigorously and the word *continuous* not at all.

That is the fifth instance this phase of the same pattern — **a check whose output looks
like the claim while the claim is not true** — and the first that lives in a criterion
rather than in an implementation.

**Fix, as far as it is mine.** `build_report` now reports `recorded_fraction` beside
`recorded_seconds` and `missing_seconds`, so the weakness is visible **in the artefact**
rather than only to a reader who divides one by the other in their head. It is
deliberately **not** a threshold: a minimum recorded fraction changes what the gate
requires, and that is the operator's decision, not an implementer's and not the lead's.

**Consequence.** Nothing was deposited. Depositing is the irreversible half, the archive
is contaminated twice over — the duplicate-recorder boundary at 13:19:34 and a
self-inflicted disk outage — and it is contaminated evidence for the phase whose entire
subject is the data spine. The lead's recommendation to the operator is a clean
single-recorder 24-hour run; the cost is that Phase 2 cannot close today, and that is why
the operator decides it.

### Correction: there were never two recorders. I was wrong, and so was the correction to me

**Agent:** A · **Task:** spec 27/28 · **Date:** 2026-09-09

Per rule 6 of `script-rules.md` this corrects two earlier entries with a new one rather
than editing them. The entries "Two recorders were running at once, and the duplication
is not uniform" and the de-duplication decision in spec 28 both rest on a premise that is
false.

**What I claimed.** Two `scripts/record.py` processes (PIDs 6968 and 46512) were running
concurrently and appending to the same daily file, so every frame after their start time
appeared in the archive twice. The lead then refined it: both were created at the same
second, so the duplication began at that moment rather than running all day.

**What is actually true.** They were **one recorder**. Windows `Get-CimInstance` lists a
parent and a child with identical command lines, because the venv's `python.exe` on this
machine re-executes the interpreter:

    ProcessId : 5140   ParentProcessId : 29348   ... python.exe scripts/record.py
    ProcessId : 2144   ParentProcessId : 5140    ... python.exe scripts/record.py

The second is the *child of the first*. Starting a single clean recorder just now produced
exactly the same pair, which is what made it obvious.

**And the timestamps compounded it.** Their creation time read `9/9/2026 1:19:34 PM`,
which is **local** — this machine is on BST, UTC+1 — so it is `12:19:34Z`, not `13:19:34Z`.
The digest shows an unrecorded silence from `11:58:23Z` to `12:19:20Z`: that pair *is*
the restart after that outage, not a second recorder joining a first.

**How it was settled.** Not by argument. `scripts/ohlc_fixture.py` counts byte-identical
duplicate frames, so it was run over a window either side of the supposed boundary:

    2026-09-09T12:30:00Z, 2 bars -> frame duplicates dropped: 0
    2026-09-09T05:00:00Z, 2 bars -> frame duplicates dropped: 0

Zero on both sides. There is no duplication anywhere in the archive.

**What survives, and what does not.** The **de-duplication is still correct code** and
stays: frame-level rather than trade-level is the right granularity whether or not
duplicates ever occur, and the reasoning about why trade-level would silently delete real
volume is sound and worth keeping. What does not survive is the *claim about this
archive*, and the inference in the spec 28 entry that a naive candle build over it would
be doubled after 13:19. It would not. It never was.

**The lesson, which is the phase's own lesson pointing at me.** I inferred a data
corruption from a process listing, told the lead, and the lead reasoned further from my
inference rather than back to the evidence. Two people then held a wrong belief that a
thirty-second empirical check would have settled — and I already had the tool that settles
it, because I had written it that morning. **The evidence pointed somewhere other than the
cause, again, and this time I was the one pointing.** Check the artefact, not the
process table.

### The clean 24-hour run: what was done and when it finishes

**Agent:** A · **Task:** spec 27 · **Date:** 2026-09-09

**Why.** The operator ruled against depositing on the existing archive. It is 49%
recorded, and it contains an outage this project caused itself — for the phase whose
entire subject is the data spine, that is contaminated evidence.

**What was done.** Both listed recorder processes were stopped and exactly one started.

`taskkill` without `/F` **refused** — "This process can only be terminated forcefully" —
so it was a hard kill, and that is worth stating plainly: `scripts/record.py` has **no
working graceful shutdown path on Windows.** It installs SIGINT/SIGTERM handlers through
`loop.add_signal_handler`, which raises `NotImplementedError` on the Proactor loop and is
swallowed by a `contextlib.suppress`, so the handler is never attached and the
`_write_session("stop")` marker in its `finally` never runs. The archive is append-only
and every line is flushed on write, so at most a partial final line was lost — a marked
defect, not lost data — but the absence of a `stop` marker at a kill is a property of the
recorder nobody had written down.

**The numbers, for whoever picks this up:**

    clean run session start : 2026-09-09T14:15:29.997349Z
    24 hours complete at    : 2026-09-10T14:15:30Z
    disk before starting    : 165G free, 83% used
    handover gap            : under the 60s silence threshold, so the digest shows none

Then: `python scripts/recording_report.py --write`, and re-run `--phase 2`. The script
refuses to write below 24 hours, so it cannot be run too early by accident.

### Two more decayed assertions, in my file, of the family C had just named

**Agent:** A · **Task:** specs 26-29 · **Date:** 2026-09-09

**What happened.** The lead registered engines 1 to 4 in `bootstrap.py` and two tests in
`tests/cli/test_entrypoints.py` went red — mine, and neither for a reason connected to
what its name claimed.

**Why.** Both asserted something true only while the registry was empty.

`test_an_empty_registry_produces_a_valid_tick` built its orchestrator with
`build_orchestrator(...)`, which reads `bootstrap`, and then asserted
`state["guard_blockers"] == []`. Those are two different claims — "an empty registry
ticks cleanly" and "nothing blocked" — that coincided only while nothing was registered.

`test_the_offline_chain_is_not_in_bootstrap` asserted the real invariant, that there is
no `OFFLINE_CHAIN` in `bootstrap`, **and then three `== ()` assertions on the chains.**
Those were scaffolding that read as part of the claim. "The chains are empty" is a fact
about Phase 0; "there is no offline chain here" is architecture invariant 5. Only the
second survives an engine being registered.

**Fix.** The first constructs `Chains()` explicitly and keeps every strong assertion. The
second drops the emptiness assertions and asserts the invariant on the source instead:
`bootstrap` imports nothing from `acsoe.research`. Two new tests were added in their
place — one naming what `bootstrap` actually holds, and one asserting the current
behaviour of a tick over the real registry with the CLI's placeholder clients.

**Consequence, and it is the point.** C had found and named this exact defect in
`orchestrator_empty_registry` hours earlier — a criterion whose body was held to
"whatever `bootstrap` currently holds" while its name said "empty registry". **Neither of
us went looking for a second instance, and there were two, in a file I had already
touched twice that day.** A named defect is not a fixed defect until somebody greps for
its siblings.

The generalisation worth carrying: **an assertion is decayed if it would still pass when
the thing it names is false.** `guard_blockers == []` says nothing about an empty
registry; it says something about whichever registry it was handed. C's rule covers
fabricating a contract a criterion is held to; this is its sibling — do not assert a
coincidence and name it a property.

### `acsoe engine` now blocks every tick, and that is written down rather than hidden

**Agent:** A · **Task:** spec 09 follow-on · **Date:** 2026-09-09

**What happened.** `cli/engine.py` has passed a `Clients()` of three `None`s since Phase
0, which was correct when no engine was registered. With engines 1 to 4 registered, every
tick now produces `AttributeError: 'NoneType' object has no attribute 'asset_pairs'` from
engine 1 and a `ConfigKeyError` from engine 4, both converted to `ERROR` with
`blocks_trading=True`.

**Why it is not a defect in the engines.** The tick **completes** and records both
failures, which is contract rule 7 working exactly as specified. Nothing raises out of the
loop, the manage chain would still run, and the daemon does not die. It simply does
nothing useful, which is the honest fail-closed outcome for a daemon wired to no clients.

**Fix.** Not yet — it needs `market_data.pairs` and `market_data.book_depth`, which do
not exist, and the WebSocket stream cannot subscribe without a pair list I refuse to
invent. What *is* done is that the state is asserted:
`test_a_tick_over_the_real_registry_records_errors_rather_than_raising` pins the current
behaviour, so **wiring the real clients turns that test red** and forces it to be
rewritten deliberately rather than quietly passing against a changed system. A test that
documents a known gap is worth more than a comment, because a comment does not fail.


## Agent B — Store and trading logic

*From `docs/build-log/phase-2/b-store.md`, 20 entries.*

### Decision: the persisted mode is a column on `runs`, not a single-row state table

**Agent:** B · **Task:** spec 31 · **Date:** 2026-09-09

**Options.** Spec 31 offers both shapes explicitly. A single-row `system_state` table,
or additive columns on the existing `runs` row.

**Chose.** Two nullable columns on `runs`: `system_mode TEXT CHECK (... IN ('idle',
'running', 'frozen'))` and `system_mode_at INTEGER`. Migration
`0002_persisted_system_mode.sql`. Nothing existing is altered and no table is added.

**Because.** The spec requires the value to be readable **by `run_id`** so the console
can tell this run's mode from a previous one's. A single-row table can only satisfy
that by carrying a `run_id` column of its own and having every reader remember to
compare it — which is `runs`' identity re-implemented with no UNIQUE constraint behind
it. On `runs` the scoping is structural rather than conventional: one row per daemon
process, `run_id` already UNIQUE, so a previous run's mode is physically in a different
row and there is no query you can get wrong. Three consequences point the same way.
Lifecycle matches exactly — mode is a property of one daemon process and `runs` is one
row per daemon process, whereas a global single-row table holds one row for a thing
whose natural cardinality is N. `runs` is already in `StoreClient.WATERMARK_TABLES`, so
persisting a mode moves the console's poll watermark for free; a new table would have
had to be added to that tuple, changing behaviour under every existing watermark test
mid-phase. And a new table is a lead escalation — `db_migrates_from_empty` asserts the
documented table set and `architecture-context.md` carries the storage table — while a
column is not. Same result, no gate reopened, no lead edit.

**Cost.** Two nullable columns on a row that is otherwise write-once, and a split
writer: `write_run` may not touch them. See the entry below.

**Two naming notes, both load-bearing.** The column is not called `mode` because
`runs.mode` already exists and holds paper/live/replay. System mode is a different axis
— idle/running/frozen — and two columns called `mode` on one row is the kind of
collision that reads fine and is wrong. `system_mode_at` is separate from `updated_at`
because `updated_at` is bumped by any write to the row and so cannot answer "how old is
this mode reading", which is the one question an operator asks of a status band that
might be stale. Recording it costs a nullable integer; not recording it destroys the
fact, and the migration is forward-only.

**NULL is not `idle`.** NULL means no daemon has written a mode for this run yet;
`'idle'` means a daemon actively reported being idle. Both render as an idle reading per
spec 32, but only one is ordinary, and collapsing them is how a status band ends up
confidently wrong. The two are kept distinct all the way out to `SystemModeRow`, where
"no such run" is a `None` return and "run exists, no mode yet" is a row with `mode is
None`.

### `write_run` would have clobbered the mode on the shutdown write

**Agent:** B · **Task:** spec 31 · **Date:** 2026-09-09

**What happened.** `write_run` is `_upsert("runs", row.model_dump(exclude={"id"}), ...)`.
Adding two columns to the table added them to `RunRow`, which silently added them to
that payload — so `write_run` became a writer of the system mode without anyone
deciding it should be.

**Why it matters.** The orchestrator writes the run row at startup, when no mode has
been decided, and writes it again at shutdown to stamp `ended_at`. The `RunRow` it holds
was built at startup and carries `system_mode=None`. With the columns in the payload,
the `DO UPDATE SET` clause resets a `frozen` daemon's persisted mode to NULL on the way
out — the console's last reading of a frozen system, erased by a bookkeeping write that
had nothing to do with mode.

**Fix.** `exclude={"id", "system_mode", "system_mode_at"}`. Excluded from the INSERT the
columns default to NULL; excluded from the `DO UPDATE` set they are left exactly as they
were. `set_system_mode` is now the only writer of either column — one column, one
writer. Two tests pin it: one with a `RunRow` built fresh, and one with a `RunRow` read
back out of the database that genuinely carries `system_mode=RUNNING`, because the
exclusion has to be on the column and not on whether the caller happened to leave it
null.

**Consequence.** A read-modify-write through `write_run` is a deliberate no-op on the
mode. `RunRow`'s docstring says so, and it is a property C can rely on.

### A test that pinned the migration count as a literal

**Agent:** B · **Task:** spec 31 · **Date:** 2026-09-09

**What happened.** Adding `0002` turned `tests/db/test_migrations.py` red in two places:
`assert applied == [1]` gave `[1, 2] == [1]`, and `assert conn.execute("PRAGMA
user_version").fetchone()[0] == 1` gave `2 == 1`. Both are my own tests and both had
hardcoded "there is exactly one migration".

**Why.** The number of migrations is not a property of the system worth pinning. What is
worth pinning is that *every* migration on disk got applied, in ascending contiguous
order, and that `user_version` names the newest one. A literal asserts none of those and
must be edited by every future migration — and the edit that makes it pass is the edit
that makes it agree with whatever just happened rather than with what should have
happened. That is a test that will eventually be changed carelessly, and the careless
change is invisible in review.

**Fix.** Both expectations now derive from `default_migrations_dir().glob("*.sql")`.
Deliberately a plain glob rather than `discover_migrations`, which is itself under test
in the same module and would have made the expectation agree with the implementation by
construction; a glob is an independent count that fails if a file goes missing.
`test_fresh_database_migrates_from_empty` still asserts the full list and its ordering,
so a migration skipped, applied twice, or applied out of order still fails, plus a floor
of `>= 2` so the derivation cannot quietly collapse to a vacuous empty list.

**Consequence, and an asymmetry worth naming.** The criterion `db_migrates_from_empty`
**passed throughout** — it tolerates extra tables and reports them as a note, and 0002
adds no table at all, so it saw nothing. Only the stricter unit tests failed. The gate is
the criterion, and the criterion did not notice a schema change; the tests that did are
the ones I had just weakened by deriving their expectation. The net is still stronger —
ordering and completeness are asserted where a literal asserted neither — but it is worth
recording that the phase gate's schema check is coarser than it reads, and that the fine
check lives in `tests/db/`.

### Three new tests on 0002 itself, at the SQL level

**Agent:** B · **Task:** spec 31 · **Date:** 2026-09-09

**What happened.** `runs.system_mode` carries a CHECK constraint while `commands.command`
deliberately does not, and the contrast needed recording rather than just implementing.

**Why.** An unrecognised *command* must be storable so the orchestrator's "ignore it and
log a warning" path stays reachable and testable. An unrecognised *mode* is the opposite
case: there is no ignore-and-warn path for a status band, because a mode the console
cannot render is a reading it would have to invent. So the database refuses the write.

**Fix.** `test_an_unrecognised_system_mode_is_refused`,
`test_a_new_run_row_has_no_system_mode` (NULL, no default — the fact that no daemon has
written yet is preserved rather than defaulted away), and
`test_the_system_mode_columns_did_not_disturb_the_existing_runs_contract`, which asserts
both CHECKs in one place so the `mode` / `system_mode` collision cannot creep back.

### The seed still writes no system mode, and there is now a test saying so

**Agent:** B · **Task:** spec 31 · **Date:** 2026-09-09

**What happened.** `seed.py` needed no change — it builds `RunRow`s whose mode fields
default to `None`, and `write_run` excludes the columns anyway — so this could have been
left as an absence.

**Why an absence is not enough.** Spec 31 forbids seeding a mode for a specific reason: a
seeded `running` would let C's console test for the Running band pass without a daemon
ever having written one, leaving the entire persisted-mode path unproven and green. An
absence that nothing asserts is an absence someone adds a fixture to later, in good
faith, to make a console test easier.

**Fix.** `test_the_seed_writes_no_system_mode` reads every seeded run back and asserts
every `system_mode` is NULL, with a non-empty guard so it cannot pass on zero runs.

### No reader puts this value back into `state`, and that is deliberate

**Agent:** B · **Task:** spec 31 · **Date:** 2026-09-09

**Decision, recorded because its absence is invisible.** `StoreClient.system_mode` exists
and `StoreClient.set_system_mode` exists; there is no third method that restores a mode
into `state["system"]`, and none should be added. A daemon always starts `idle` and
reaches `running` only through an `activate` command, so a crashed daemon comes back not
trading with the manage chain still watching whatever is open. Restoring the mode would
invert that safety property, and it would do so in a way that looks like a bug fix.
`set_system_mode`'s docstring carries the same statement, because the next person to want
resume-after-crash will read the client and not this log.

**One shape note.** `set_system_mode` returns `False` for an unknown `run_id` rather than
raising. The caller is the command reader in `core/`, which has already applied the
transition to `state` by the time it persists it; a raise there would abort a `freeze`
that has in fact happened, over a bookkeeping row. False is returned and logged. A
missing `runs` row is a defect or a race, and it is not a mode.

### An intermittent teardown ERROR in `tests/cli/`, recorded before re-running

**Agent:** B · **Task:** spec 31 · **Date:** 2026-09-09

**What happened.** The first `scripts/verify.py --phase 0` after spec 31 landed reported
`FAIL toolchain_green` with, verbatim:

```
FAIL    toolchain_green              pytest exit 1: =========================== short test summary info =========================== | ERROR tests/cli/test_entrypoints.py::test_console_refuses_an_unset_operator_key | 722 passed, 1 error in 33.80s
```

**Why it is not the known seed-path fault, and not spec 31.** It is an `ERROR`, not a
`FAILED` — a fixture setup or teardown, not an assertion — and pytest returned exit 1
rather than dying with an NTSTATUS, so it is neither the `0xC0000005` family from the seed
write path nor anything in `clients/store/`. `test_console_refuses_an_unset_operator_key`
sits in A's `tests/cli/`, reaches nothing I own, and its neighbouring fixture
`_isolated_runtime` already documents that this file's teardown deletes a `tmp_path`
directory that logging handlers may still hold open — which on Windows is a failure
rather than a warning. The full suite passed 723/723 immediately before and after, and
the immediate re-run of `--phase 0` was green with no change to any file.

**Recorded rather than fixed.** It is A's file and A's fixture; I own none of it. Flagged
to the lead. **Separately, and visible on the green run too:** `scripts/verify.py` prints
an unhandled `PermissionError: [WinError 32] ... acsoe-verify-doubles-*\acsoe.sqlite` from
its own `TemporaryDirectory` finalizer on every phase-0 run. Same Windows shape — a
SQLite file still open when the temp directory is collected — in C's script rather than in
a test. It is noise above the report and does not change the result, but it is the same
defect twice and it is worth one fix rather than two shrugs.

### Money cannot cross `state` as a `Decimal` — the orchestrator refuses it

**Agent:** B · **Task:** spec 34 · **Date:** 2026-09-09

**What happened.** I started engine 10 assuming the fee tier would reach me from
`state["exchange"]` as a `Decimal`, because everything else in this project that touches
money is one. It cannot. `EngineResult.data` runs `_assert_json_serialisable`, whose
scalar set is `None | str | int | float | bool`, and the orchestrator assigns
`result.data` directly into `state[engine.name]` — so every value published by another
engine has already been through that validator.

**Why it matters more than it looks.** `Decimal` is refused loudly, which is fine. The
hazard is that **`float` is accepted**. An engine publishing a fee as `0.0022` satisfies
the validator, loses precision on the way, and arrives in a hurdle comparison as a number
that is wrong in the fourth decimal — which is exactly the magnitude at which this gate
operates. The one type that must never reach the edge calculation is the one type the
orchestrator's check waves through.

**Fix.** Money crosses `state` as an **exact decimal string**. `CostInputs` types every
money field as `Money`, the annotated `Decimal` from `clients/store/contracts.py` whose
`BeforeValidator` raises on a float rather than coercing it, so a float published upstream
is refused at this engine's boundary with the field name attached. On the way out,
`format(d, "f")` — plain notation, never scientific, which matters because these strings
land in `rejections`' TEXT columns and `str(Decimal("1E-4"))` compares unequal to
`"0.0001"` under any text comparison. `test_a_float_fee_is_refused_rather_than_coerced`
and `test_the_published_payload_is_json_serialisable` pin both directions.

**Consequence.** Told A directly, with the reproduction, because A's engine 1 is the
publisher and the natural thing for A to do on hitting the validator is to cast to
`float`, which is the one wrong answer. Verified against the real class rather than read
off the source.

### Decision: proposed state paths as `Final` constants rather than a stop-and-escalate

**Agent:** B · **Task:** spec 34 · **Date:** 2026-09-09

**Options.** Engine 10 needs six inputs. Spec 34 fixes exactly one location in prose —
the fee tier arrives in `state["exchange"]` — and `engine-contracts.md` fixes four
cross-chain keys, none of which is mine. The expected move (C's engine 8), the spread
(A's engine 1), the slippage estimate (C's engine 9) and the candidate pair (my engine 7,
Phase 3 proper) have no ratified key name. Either stop the unit and escalate, or build
and flag.

**Chose.** Build, with every unratified path declared as a `Final` constant in
`engines/cost/contracts.py` under a heading that says it is a proposal, and the open
question recorded in my progress file for the lead.

**Because.** "Never guess at trading behaviour" is about behaviour, and the behaviour here
is not guessed: the arithmetic is invariant 5, quoted verbatim at the top of the engine,
and the third line of it is not adjustable. What is unratified is wiring — four key names
— and stopping the whole engine over a key name would have burned the concurrency the
operator authorised this work for. Collecting them in one place means re-pointing one is a
single-line edit and a reviewer sees the entire uncertain surface at once, rather than
finding `state["prediction"]["expected_move_pct"]` inlined three levels down.

**Cost.** Four constants that may be renamed, and a test file that will need its fixture
rebuilt when they are. Both are cheap; scattering the same guesses through the engine
would not have been.

### The reason codes were already fixed, by C, and nothing said so

**Agent:** B · **Task:** spec 34 · **Date:** 2026-09-09

**What happened.** I was about to invent `reason_code` values for the cost gate. Reading
`console/format.py` first, C's `REASON_PROSE` table already contains
`net_edge_below_hurdle`, `spread_wider_than_move`, `below_ordermin`, `below_costmin`,
`insufficient_quote_balance` and `max_concurrent_positions` — every code engines 10 and 11
need, decided in Phase 1 by the agent who owns the screen that renders them.

**Why it matters.** `operator_reason` falls back to "No reason was recorded." for a code
absent from that table. An invented code would not raise, would not fail a test, and would
surface months later as a blank cell on the rejections screen. Nothing in either spec, in
`ownership.md`'s seam table or in the Phase 2 task list names this as a seam.

**Fix.** Engine 10 emits C's codes verbatim, and
`test_every_reason_code_this_engine_emits_is_renderable_by_the_console` imports
`REASON_PROSE` and asserts they are present — a test in my file, over C's data, which is
the only place the two halves meet. The one code I did have to add,
`cost_inputs_unavailable` for the fail-closed path, is flagged to C; until C adds it the
console still renders correctly, because `operator_reason` prefers a stored prose reason
over the code mapping and that path always writes prose.

**Also duplicated deliberately:** `format_signed_pct`, so the blocking reason carries a
U+2212 minus and two decimal places like every other number on the screen. Imported would
have been tidier and would have put a FastAPI-adjacent module on the live trading path;
the console is a separate process that reads the database, and an engine importing it
inverts that. `test_the_local_percentage_formatter_agrees_with_the_console` compares the
two implementations over a table of values so the copy cannot drift silently.

### The cost gate is unreachable at tier 1, and the test says so on purpose

**Agent:** B · **Task:** spec 34 · **Date:** 2026-09-09

**What happened.** The obvious pass test — a 3% expected move, tier 1 fees — blocks. That
is not a bug in the engine.

**Why.** Invariant 5 requires `net_edge > hurdle_multiple x friction`, which rearranges to
`expected_move > (1 + hurdle_multiple) x friction`. At the operator's `hurdle_multiple:
1.5` that is `2.5 x friction`; tier 1 friction is around 1.25% round trip, so a candidate
needs a move above roughly 3.125% while the target barrier is 3.0%. Nothing clears this
gate at tier 1 with these barriers. The tracker already carries the finding; this is the
first code that runs into it.

**Fix.** The pass tests use tier 3, and
`test_at_tier_one_nothing_clears_the_gate_and_at_tier_three_it_does` asserts the
consequence in both directions rather than leaving it as a comment. Its docstring says
what to conclude if it ever fails: not that the test is stale, but that `hurdle_multiple`,
the barriers or the reference fees have moved and the tracker note needs revisiting with
them.

**One further guard.** `trading-invariants.md` calls its reference fees "for
sanity-checking only — never for use in code", and a constant that happened to equal tier 1
would satisfy every behavioural test above on a tier-1 fixture. So
`test_no_reference_fee_appears_in_the_engine_source` reads the engine's own source and
asserts none of the six reference figures is written into it. Behavioural tests cannot
catch a constant that agrees with the fixture; only reading the source can.

### The spread moved from engine 1 to engine 3, and it cost one constant

**Agent:** B · **Task:** spec 34 · **Date:** 2026-09-09

**What happened.** The lead ratified three of my four proposed state paths and re-pointed
the fourth: the measured spread is `state["market_sensor"]["quotes"][pair]["spread_pct"]`,
not `state["exchange"]["pairs"][pair]["spread_pct"]`.

**Why the ruling is right.** Engine 1 `exchange` is the *account* engine — balances, fee
tier, pair rules. Engine 3 `market_sensor` is the *market-data* engine. Spread is market
data. The deciding argument is engine 4 `data_guard`, which blocks on stale data, a
negative spread and a missing candle: all three are market-data faults and having them
arrive from two publishers would split one responsibility across two engines.

**What it cost.** One `Final` constant in `engines/cost/contracts.py`, one fixture key in
the test file, one README row. That is the entire point of having declared the unratified
paths as named constants under a heading saying they were unratified, rather than inlining
guessed key names three levels down in `_read_inputs`. Worth recording as a pattern rather
than as an event: **when you have to propose an interface, propose it in one visible
place, and a later ruling is an edit instead of an argument.**

### Engine 11: asserting the absence of a resized quantity, and getting it wrong first

**Agent:** B · **Task:** spec 35 · **Date:** 2026-09-09

**What happened.** Spec 35 requires the sub-`ordermin` test to assert on the *absence of a
resized quantity*, because "a test that only checked 'did not place' would pass against a
rounding implementation". My first attempt asserted that no value anywhere in the payload
equalled `ordermin`. It failed immediately — against a correct implementation.

**Why.** `RiskSizing` legitimately publishes `ordermin` itself, so the console and the
`rejections` row can say what the minimum was. The check could not distinguish "the
minimum, reported as the minimum" from "the quantity, bumped to the minimum". Worse, it
would not have caught the defect it was aimed at anyway: an implementation that bumped to
`ordermin + one lot` would have passed it.

**Fix.** Assert the whole key set instead. On a rejection the payload is exactly
`{pair, approved, ordermin, costmin, reason_code, fallbacks_used}` — `to_state_data` omits
`qty`, `notional` and `risk_amount` entirely rather than emitting them as `null`. There is
no field for a quantity to be bumped *into*, which is a structural guarantee rather than a
behavioural one, and the test now says so by pinning the shape.

**Consequence.** Two further orderings that are easy to get backwards, each with a test.
Rounding is **down**, never to-nearest — to-nearest would round a quantity one lot below
`ordermin` *up to* it, the rounding-up defect arriving through a rounding mode rather than
an explicit bump. And rounding happens **before** the minimum is tested, so the number
compared against `ordermin` is the number that would actually be sent; checking first and
rounding after would let a quantity that passed be rounded below the minimum and placed.

### The sizing rule had a 66x reading, and the config settled it

**Agent:** B · **Task:** spec 35 · **Date:** 2026-09-09

**What happened.** `trading.risk_fraction_per_trade: 0.01` has two readings — 1% of equity
as *notional*, or 1% of equity as *money at risk*. At the configured 1.5% stop they differ
by a factor of 66.

**Why it is not a judgement call.** Invariant 6 says "risk per trade never exceeds the
configured fraction of total account equity", and the money at risk on a position is the
distance to its stop, which gives `notional = equity x fraction / stop_pct`. The
confirmation is in `config/default.yaml` itself: the operator's comment on
`max_concurrent_positions` reads "the balance binds first at $5,000: one position is
~$3,333 notional", and $5,000 x 1% / 1.5% is $3,333.33. So the intended reading is stated
in the committed config and did not have to be inferred.

**Fix.** The sizing test asserts against that worked example by name, so a change to the
rule fails against the operator's stated intent rather than against a number this file
invented. The notional reading would have sized every position at 0.5 units — an error
that looks conservative, produces no exception, and would have made every downstream
economics result meaningless.

**One decision alongside it.** Equity comes from `store.latest_equity_snapshot()`, not from
the quote balance, and an absent snapshot blocks rather than falling back to cash. Sizing
against one currency's cash would shrink the risk budget every time a position opened,
which is not what a fixed fraction of equity means; and a fallback to cash would let the
system size a trade against an equity figure nothing had computed, which is the optimistic
kind of fallback invariant 2 forbids outright.

### Two documents disagree about what a drawdown breach emits

**Agent:** B · **Task:** spec 36 · **Date:** 2026-09-09

**What happened.** Before writing engine 17's condition-to-command mapping I found that
`trading-invariants.md` §14 and `feature-specs/36-engine-17-safety.md` cannot both be
satisfied by the Phase 0 seed.

§14: `safety` escalates — sets `close_intent`, i.e. writes `close_all` — on "its configured
drawdown and loss-streak limits are breached" or "a sustained data outage", and escalates
"when there are open positions or resting entry orders". Spec 36's Check When Done: "It
**freezes** on the seeded drawdown on a tick where the opportunity chain never runs."

**Why the seed makes it unavoidable.** The seed carries drawdown 0.2000 against a 0.10
limit, a losing streak of 8 against a limit of 5, **and** 2 open positions and 2 resting
entry orders. Every precondition §14 names for escalation is satisfied, deliberately — I
built it that way in Phase 0 to satisfy §14. So under §14 the seeded drawdown emits
`close_all` and under spec 36 it emits `freeze`. There is no fixture on which both are
true.

**Not fixed — escalated.** This decides whether a drawdown liquidates the account or only
stops it opening, which is precisely the class of question `AGENTS.md` says to stop on. The
lead has the three candidate readings and the two further gaps: which command the error
rate emits, and whether an escalating condition emits `freeze` first or goes straight to
`close_all`. Everything unambiguous is being built meanwhile — the six store reads, the
outage arithmetic, the exposure precondition, the idempotency rule — with the mapping
isolated as a single table in `engines/safety/contracts.py` so the ruling is one edit.

### The seed can never sit on a boundary, and the outage test needed to

**Agent:** B · **Task:** spec 36 · **Date:** 2026-09-09

**What happened.** Spec 36 requires `close_all` "on the tick after
`max_consecutive_data_blocks` and **not one tick before**", counted from the seeded
`block_records`. I could not write the "not one before" half against the seed.

**Why.** The seed overshoots every threshold by three, deliberately — `outage_run_length =
max_consecutive_data_blocks + 3` — so that a fixture pinned to a literal cannot stop
overshooting when the operator raises a limit. That is right for proving the breaker
*fires*, and it makes the seed structurally **incapable of sitting at the boundary**. A
second constraint compounded it: the outage walker anchors on the current tick and requires
the newest stored tick to be `(run_id, cycle_id - 1)`, so anchoring part-way into the
seeded run returns zero rather than a partial count. That is correct behaviour — it is what
stops "an outage that ended two ticks ago" reading as one still running — but it removes
the other way of reaching the boundary.

**Fix.** Split the claim. The boundary is tested on a controlled `block_records` fixture
that reproduces the seed's load-bearing property — two `run_id`s with reused `cycle_id`
values, `run-a` cycles 5-9 then `run-b` restarting at 1 — with 14 stored ticks plus this
one giving exactly the limit and no escalation, and 15 plus this one giving one past it and
an escalation. The seed is then used for the realistic case and for the
`ts`-versus-`cycle_id` discrimination, which spec 36 names explicitly. Both halves are
separate tests so a failure names which side of the boundary broke.

**Consequence worth stating.** "Test it against the seed" and "test the boundary" are not
compatible instructions for a fixture built to overshoot. Recorded in the engine's README
so the next person does not spend the same half hour discovering it.

### The shared seed fixture disagrees with the committed config

**Agent:** B · **Task:** spec 36 · **Date:** 2026-09-09

**What happened.** `test_error_rate_blocks_on_the_seeded_window` failed: the seeded
database carried 13 ERROR rows against a configured limit of 20, so engine 17's error-rate
condition did not trip.

**Why.** `seed_database` takes its thresholds by injection and `SeedThresholds`' defaults
are documented as "fixture-shape constants, not recommended values". One has since
diverged: the default `max_errors_in_window` is 10 — my own Phase 0 proposal, which the
operator did not take — while `config/default.yaml` says 20. The seed overshoots by three,
so the defaults produce 13, which clears 10 and sits well under 20.
`tests/conftest.py`'s shared `seed_fixtures` fixture calls `seed_database` with no
`thresholds` argument, so every test using it gets the stale numbers.

**This is exactly the defect `seed.py`'s own docstring warns about**, arriving through the
shared fixture rather than through a literal in a test — and `scripts/verify.py` already
avoids it by building `SeedThresholds` from the config, which is why
`seed_fixtures_present` has been passing with 23 ERROR rows while the shared fixture
produced 13.

**Fix.** `tests/engines/test_safety.py` defines its own `seed_fixtures` that injects the
committed config's five `safety.*` values, doing what verify does. Not fixed in `seed.py`:
the defaults are documented as shape constants and changing them would make the seed claim
to know a trading threshold, which is the coupling the injection exists to prevent.
Reported to C, who owns the shared fixture.

**The failure mode is the point.** It does not raise. A Phase 3 test of the error-rate input
against the shared fixture would simply find the condition not tripped and fail with
"expected error_rate in tripped", pointing at the engine rather than at the fixture.

### A lax pydantic validator behaved as a strict one, and it was not a crash

**Agent:** B · **Task:** spec 36 · **Date:** 2026-09-09

**What happened.** A reported, from a full-suite baseline run before touching any code:
`ValidationError: BlockRecordRow.is_primary — Input should be a valid boolean
[input_value=0, input_type=int]`, raised from `client.py`'s `block_records_in_window`. Not
reproducible when that file was run alone, and it has not recurred.

**Why it is worth an entry despite being unreproducible.** `_Row` is not strict, and in lax
mode pydantic accepts `0` and `1` for a `bool` — so that error should be unreachable. A lax
validator behaving as a strict one is the signature of the known intermittent pydantic-core
fault already in Known Risks, which has produced `0xC0000005`, `0xC0000374`, `0xC0000409`
and an `AttributeError` from inside `to_python`. **This is the same fault arriving as a
wrong answer rather than as a crash**, which is materially worse: a crash is obviously a
crash, while a `ValidationError` naming a field looks like a schema bug and invites
somebody to loosen that field's type — which would then accept a genuinely bad value
forever.

**Fix.** `_row_to_dict` now converts `is_primary` and `promoted` explicitly, via a
`_BOOLEAN_COLUMNS` constant beside the existing `_JSON_COLUMNS`. It is honest on its own
terms — SQLite has no boolean type and these columns are `INTEGER ... CHECK (col IN (0, 1))`
— and it makes the whole class of failure unreachable rather than merely rarer, at one dict
lookup per row. `test_sqlite_integers_become_real_booleans_at_the_client_boundary` asserts
`type(value) is bool` rather than truthiness, so the conversion cannot be quietly dropped.

**Escalation note.** Per my Phase 0 entry the intermittent fault becomes mine again "if the
fault appears outside this write path". It has: this is a *read* path, and it manifested as
a validation error rather than a native crash. Flagged to the lead as a widening of the
known signature rather than a new defect, since the mitigation here closes this instance
and hardware remains the suspected root cause.

### The verify script leaked 114GB of temp directories and filled the disk

**Agent:** B · **Task:** spec 36 · **Date:** 2026-09-09

**What happened.** A `write_text` to `context/progress/b-store.md` failed with
`OSError: [Errno 28] No space left on device` and **truncated the file to zero bytes**. The
disk was at 100% — 118MB free of 923GB. Restored from `git checkout`, losing nothing,
because the lead had committed the file at `84321dd`.

**Why.** Not the test suite: `pytest-of-saad2` held only 96MB. The temp directory carried
**over 250 `acsoe-verify-console-*` directories**, one per run of the console criteria in
`scripts/verify.py`, none ever removed. Deleting them freed **114GB**, so each was roughly
450MB — a full console fixture set per criterion per run, retained forever. Three agents
running `verify.py` repeatedly through Phase 1 and Phase 2 is what turned a leak into an
outage.

**Fix.** Removed the leaked directories plus four stale `pytest-*` trees and the
`acsoe-verify-doubles-*` leftovers. Disk went from 118MB free to 114GB. The leak itself is
in `scripts/verify.py`, which is C's file — reported, not touched.

**Why it is the same defect C fixed this morning, one directory over.** C had just fixed
`acsoe-verify-doubles-*` leaking because `check_orchestrator_empty_registry` never called
`VerifyDoubles.close()` and the removal then happened in a `TemporaryDirectory` finalizer at
GC where nothing could catch the refusal. The console criteria have the same shape and were
not covered by that fix. The `doubles` leak was visible as a `PermissionError` printed above
the report; the console one was **completely silent** and two orders of magnitude larger.

**Consequence worth recording.** The failure did not present as a disk problem. It presented
as a truncated progress file mid-write, and if the lead had not been committing at every
task boundary it would have destroyed a session's worth of reasoning rather than five
minutes of it. The commit-per-boundary rule, introduced after a different incident, is what
made this a nuisance instead of a loss.

### The intermittent native fault beat the gate's retry for the first time

**Agent:** B · **Task:** spec 31 follow-up (`start_run`) · **Date:** 2026-09-09

**What happened.** `scripts/verify.py --phase 2` reported `FAIL toolchain_green` with
**both** the run and its retry crashing, captured verbatim before any re-run:

```
FAIL    toolchain_green   CRASH - pytest CRASHED: the process died with 3221225477
(0xC0000005 ACCESS_VIOLATION), which is outside the 0-5 range pytest returns. Last
output: File ".venv\Lib\site-packages\pytest\__main__.py", line 9 in <module> | File
"<frozen runpy>", line 88 in _run_code | File "<frozen runpy>", line 198 in
_run_module_as_main; the retry crashed too - pytest CRASHED: the process died with
3221226505 (0xC0000409 STACK_BUFFER_OVERRUN), which is outside the 0-5 range pytest
returns. Last output: ........ [ 64%] | ........ [ 72%] | ..............
```

Immediately before it, my own `pytest tests/ -q` had reported **1000 passed in 43.76s**,
and immediately after, the same gate ran clean. So the suite is not broken; the process
is dying.

**Why it is escalation-worthy rather than another instance.** My Phase 0 entry closed this
as a risk with two named conditions that would reopen it: the fault appearing outside the
seed write path, or **"the gate starts reporting `CRASH -` after its retry — which would
mean the rate has moved and the mitigation no longer holds."** Both have now happened
within one session. The read-path `ValidationError` earlier today was the first; this is
the second, and it is the one the mitigation was specifically built to absorb.

Two details that are new. The first crash carries **no test progress at all** — its last
output is the `pytest/__main__.py` and `runpy` frames, so the process died during
collection or start-up rather than inside any test, which is the first observation not
located in a write path. And the two crashes carry **different NTSTATUS codes in one gate
run** (`0xC0000005` then `0xC0000409`), which is the signature of memory corruption rather
than of a reproducible defect in a particular code path.

**Not fixed. Escalated.** The retry-once mitigation is what has been holding this phase's
gate together, and a double crash means one retry is no longer enough. Recorded here
rather than worked around: raising the retry count would hide the rate change, which is
the one fact worth having.


## Agent C — Interface and models

*From `docs/build-log/phase-2/c-interface.md`, 12 entries.*

### `verify.py` printed a `PermissionError` above its own report on every phase-0 run

**Agent:** C · **Task:** spec 33 (found by B) · **Date:** 2026-09-09

**What happened.** `python scripts/verify.py --phase 0` printed an unhandled
`PermissionError: [WinError 32] The process cannot access the file because it is being
used by another process: '...\acsoe-verify-doubles-...\acsoe.sqlite'` above the report,
on **every** run including green ones. It changed no verdict, so it had been read as
cosmetic and left alone for two phases.

**Why.** `check_orchestrator_empty_registry` builds its tick out of
`tests.harness.doubles.build_verify_doubles()`, which opens a real `StoreClient` on a
database inside a `tempfile.TemporaryDirectory`. The criterion never called
`VerifyDoubles.close()`, so nothing closed that connection and nothing removed the
directory in the criterion's own scope. The removal happened later, in
`TemporaryDirectory`'s weakref finalizer at garbage collection — where SQLite still held
the file open, Windows refused the unlink, and no caller was left to catch it. Two
defects, and only both together produce the message: an unclosed connection, and a
cleanup path with no error handling.

**Fix.** `VerifyDoubles.close()` now closes the store *before* touching the directory,
detaches `TemporaryDirectory`'s finalizer so the unguarded path cannot run at all, and
removes the tree with `shutil.rmtree(..., ignore_errors=True)`. The criterion calls
`doubles.close()` in a `finally`. Order matters more than the swallow: closing the store
is what makes the removal succeed, and `ignore_errors` is there only so that failing to
delete a throwaway database can never be reported as a verdict about the orchestrator.

**Consequence.** `--phase 0` is clean above the report. The same Windows shape appears
once more in A's `tests/cli/` fixture teardown, which B captured in the same note; that
one is A's and is not touched here.

A second instance of the same leak turned up while writing spec 33's tests. When
`build_verify_doubles()` itself raises — which it does routinely against a fabricated
tree, because a `StoreClient` that exists and does not answer `migrate()` is exactly the
subject some criteria judge — the temporary directory was already made and no caller had
the object to close. It now cleans up and re-raises.

### The spec 19 test I was told to delete did not exist

**Agent:** C · **Task:** spec 32 · **Date:** 2026-09-09

**What happened.** Spec 32 step 3 says to remove the spec 19 test asserting the status
band never renders `Running` or `Frozen`, and to record the deletion here with the
decision that retired it. There is no such test. `grep` for `IDLE_READINGS` across the
whole repository returns `src/acsoe/console/views.py`, `context/progress/c-interface.md`
and nothing under `tests/`; the only assertions on `band.state` in the suite are the four
restart-banner ones, and every one of them checks a *positive* reading.

**Why it looked like it existed.** `views.IDLE_READINGS` carried this sentence:
"`tests/console/test_reader.py` asserts the State field never leaves this tuple, so the
deferral is enforced by the suite rather than remembered by a person." My own progress
file repeated it, and spec 32 was written from those two. The sentence was false when it
was written. This is the third time in this project that a module docstring has claimed a
test that the session was killed before writing — `console/payloads.py` and the
`_shap_payload` docstring were the first two, both found and backfilled at the Phase 1
close. It is the same failure mode and it survived a phase close, because the claim reads
as a description of existing work rather than as a promise.

**Fix.** Nothing was deleted, because there was nothing to delete. What was removed is the
*claim*: the `IDLE_READINGS` docstring no longer says the suite enforces the deferral, and
the deferral itself is over. `views.STATE_READINGS` now names all four readings, and
`tests/console/test_reader.py::test_every_reading_the_state_field_takes_is_declared`
asserts the band's output is a subset of that tuple and that `Running` and `Frozen` are
both actually reachable. That test is the positive statement replacing the negative one:
adding a fifth reading is now a deliberate edit to `STATE_READINGS` rather than a silent
widening.

**The record, since the operator's decision still needs one.** The Phase 1 deferral of
`Running` and `Frozen` was ended by the operator's Phase 2 approval on **2026-09-09**. It
was retired because it was a statement about a phase in which no daemon ran; from Phase 2
a daemon does run, and a band reading `Idle` over a running system is actively wrong. Had
the test existed, this is the entry that would have justified deleting it.

**Consequence, and the thing worth carrying.** A docstring that claims a test is not
evidence of one. Three instances now, all from the same cause — a session that wrote the
module and died before the test — and all three were only found because someone went
looking for the test by name. The cheap check is a grep for the test module or symbol a
docstring names, at the point the docstring is written.

### The reader's unrecognised-mode fallback is unreachable, and B is why

**Agent:** C · **Task:** spec 32 · **Date:** 2026-09-09

**What happened.** `_state_reading` treats a persisted mode it does not recognise exactly
as a missing one — an idle reading, never the raw database string in front of an operator.
I wrote a test to drive that branch with a direct `UPDATE runs SET system_mode =
'liquidating'` and it failed with `sqlite3.IntegrityError: CHECK constraint failed:
system_mode IS NULL OR system_mode IN ('idle', 'running', 'frozen')`.

**Why.** Spec 31's migration constrains the column. The state I was trying to fabricate
cannot exist in any database this schema produced.

**Fix.** The fallback stays — a schema outlives the release that wrote it, and this console
may one day read a database carrying a fourth mode — but the test now asserts what is
actually true: the *database* refuses the value, proved by `pytest.raises` on the write.
A branch with no coverage and no explanation is the thing a later reader deletes; a test
saying "this is defence, and here is why it cannot fire" is not.

**Consequence.** `system_mode = 'idle'` is a *permitted* value and is deliberately not in
`MODE_READINGS`, so it falls through to the restart test — which is right, because `Idle`
and `Idle — restarted, not trading` are the two things an idle daemon can be and the
schema does not know which. That has its own test.

### The seed's timestamps sit in the future, so a daemon driven from a fixed clock sorts before it

**Agent:** C · **Task:** spec 33 · **Date:** 2026-09-09

**What happened.** `console_shows_live_rows` and `console_reads_persisted_mode` both seed a
database, run a real `Orchestrator` over it, then ask the console what it shows. Both
failed on their fabricated subjects with the console rendering seeded history: the band
reported a seeded `run_id` as current and no persisted mode, while the daemon's own row sat
in the table carrying one.

**Why.** The console's current run is the newest `runs` row. B's seed uses fixed constant
timestamps — deliberately, so two seedings are byte-identical — and they land around
2027-01. Both criteria drove their daemon from a fixed clock set in 2026-09, so the row the
daemon wrote sorted *before* every seeded row and was never the current one.

**Fix.** `_moment_after_newest_run(db_path)` reads `MAX(started_at)` out of `runs` and both
criteria start their daemon a minute after it. That is what a real daemon does — it runs
after the history in the database — and it weakens nothing: the rows being asserted on are
still written by a real orchestrator through a real store.

**Consequence worth stating.** The alternative was to stop seeding and run against a
migrated-empty database, which would have made the criteria pass more easily and proved
less: with no seeded history, "the band follows the daemon's run rather than a previous
one" is not a claim the criterion is making at all.

### The console criteria leaked a temp directory on every run, silently, and filled the disk

**Agent:** C · **Task:** spec 33 (found by B, confirmed by the lead) · **Date:** 2026-09-09

**What happened.** B hit `OSError: [Errno 28] No space left on device` mid-write, which
truncated its progress file to zero bytes. The disk was at 923G of 923G. B cleared a large
number of `acsoe-verify-console-*` directories out of `%TEMP%` and freed it. The lead
confirmed the mechanism and counted nine more accumulating afterwards, from ordinary verify
runs. **Magnitude unconfirmed** — the evidence for what actually consumed the space was
deleted with the leak, and the directories present now are 16K each, so the per-directory
figure in the first report is not something to build on. The mechanism is not in doubt.

**Why. Two defects, and the second is the one worth reading.**

First, `close_console` closed `app.state.reader` and nothing else. The console has **two**
SQLite connections by design: spec 17's read-only reader, and spec 24's narrow read-write
writer for the `commands` table alone. The application closes both in its ASGI lifespan
shutdown — and these criteria drive the ASGI callable directly, which they must in order to
avoid an HTTP client the network guard would refuse, so no lifespan ever runs. The writer
stayed open on `acsoe.sqlite`. `check_console_restart_banner` also had one chained
`sqlite3.connect(db_path).execute(...)` with no close, which leaked a third handle.

Second, and this is the actual bug: `console_workspace` ended in
`shutil.rmtree(tmp, ignore_errors=True)`. The reasoning in its docstring is right —
failing to delete a throwaway database is not a verdict about the console, and it must not
turn a PASS into a FAIL. But "do not fail the criterion" had quietly become "do not say
anything", so a workspace that survived produced no output at all. Twelve criteria go
through that helper.

**Fix.** `close_console` now closes every attribute in `CONSOLE_CONNECTION_ATTRS`
(`reader`, `command_writer`); the chained connect is a `_count_runs` helper that closes in
a `finally`. `remove_workspace` replaces the bare `ignore_errors` call: it tries, runs
`gc.collect()` — a connection dropped without being closed is released when its object is
collected, and a criterion returning early through one of two dozen `return pending(...)`
paths may well have left one — tries again, and if the directory still stands prints a
warning **to stderr with its size in MB**. stderr rather than the criterion's message,
because it is still not a verdict; but visible, because invisibility is what let this run
for two phases. `main()` also sweeps stale `acsoe-verify-*` directories at the start and
end of every run, scoped to that exact prefix and skipped inside a `toolchain_green`
subprocess where a concurrent outer run may be using one. A phase-1 gate run now leaves
zero behind, measured.

**The lesson B stated and I want recorded in my own words.** I fixed the
`acsoe-verify-doubles-*` leak this morning *because it announced itself* — it printed a
`PermissionError` above the report on every phase-0 run. The console leak had the same
shape, was far larger, and was completely silent, so nobody looked. **The visible leak was
the small one.** Neither `PermissionError` handling nor `ignore_errors=True` would have
caught the silent one. The only thing that catches it is asking whether the directory is
gone afterwards, which is now
`tests/verify/test_phase1_criteria.py::test_the_console_workspace_is_gone_after_the_block`.

### The shared `seed_fixtures` fixture was built against a threshold nobody uses

**Agent:** C · **Task:** spec 33 (found by B) · **Date:** 2026-09-09

**What happened.** `tests/conftest.py`'s `seed_fixtures` called `seed_database` with no
`thresholds` argument, so it took `SeedThresholds`' defaults. Those are documented as
fixture-*shape* constants rather than recommended values, and one has diverged:
`max_errors_in_window` defaults to 10 while the operator set 20 on 2026-09-08. The seed
overshoots a count by three, so the shared fixture produced **13** `status='ERROR'` block
records — over the default, comfortably under the config. Engine 17's error-rate condition
therefore does not trip against it, and a Phase 3 test asserting that block fails
**pointing at the engine** rather than at the fixture. Nothing raises.

**Why it was invisible.** `scripts/verify.py` has always built `SeedThresholds` from the
config in `_seed_threshold_kwargs`, which is why `seed_fixtures_present` reports 23 ERROR
rows against the same generator. The gate and the shared fixture were seeding two different
databases and neither said so.

**Fix.** `seed_thresholds_from_config()` in `tests/conftest.py`, injected by `seed_fixtures`.
A missing `config/default.yaml` falls back to the shape constants, which is honest for the
trees where it has not been written; a key that is *present and null* is deliberately left
to default rather than being given a number this file invented — "the operator has not
decided yet" is not a threshold.

**What was deliberately not done.** Making `seed.py`'s defaults track the config. B raised
that and rejected it, and the reasoning is right: it would have the seed generator claim to
know a trading threshold, which is precisely the coupling the injection parameter exists to
prevent. The injection belongs at the call site.

### The intermittent native fault fired once, and the gate's retry did its job

**Agent:** C · **Task:** spec 33 · **Date:** 2026-09-09

**What happened.** `scripts/verify.py --phase 1` reported
`FAIL toolchain_green` with the pytest subprocess having died before returning a code.
Captured verbatim before re-running, as the phase rules require:

```
pytest CRASHED: the process died with 3221225477 (0xC0000005 ACCESS_VIOLATION), which is
outside the 0-5 range pytest returns. Last output:
  File "C:\Users\saad2\Documents\GitHub\ACSOE\.venv\Lib\site-packages\pytest\__main__.py", line 9 in <module>
  File "<frozen runpy>", line 88 in _run_code
  File "<frozen runpy>", line 198 in _run_module_as_main
```

The very next run reported `PASS toolchain_green ... RETRIED AFTER CRASH ... the retry was
clean`, with the same trace quoted in the PASS line.

**Whether it matches.** The NTSTATUS is the same `0xC0000005` recorded against the seed write
path in `docs/build-log/phase-0.md`, and the timing is the same — a full-suite run, no pattern.
**The trace does not confirm the path**, and I want that stated rather than assumed: what the
criterion captured is the interpreter's top three frames, not the frames of whatever faulted, so
`seed.py:_write_trading_history` does not appear and neither does anything else. It is
consistent with the known fault and it is not evidence of it. Not escalated as something new,
because nothing about it is inconsistent either; recorded here so a second occurrence has
something to be compared against.

**Worth noting about the mitigation.** This is the first time in my work that the crash retry
has actually fired in anger rather than in its own tests. It behaved exactly as designed:
classified the returncode as a crash rather than as a failing suite, named the NTSTATUS, retried
once, and carried the crash forward into the PASS message so a green line still says a crash
happened. The alternative — the version that compared a returncode against zero — would have
filed this as a red suite, and a red suite is something you re-run until it goes green.

**Unrelated, in the same output, and A's.** The same run reported
`mypy exit 2: .venv\Lib\site-packages\numpy\__init__.pyi:737: error: Type statement is only
supported in Python 3.12 and greater [syntax]`. That is `[tool.mypy] python_version = "3.11"`
in `pyproject.toml` meeting numpy's stubs, which A has already documented and fixed in that file
with a comment explaining why raising the floor to 3.12 would be the wrong answer. It appeared
because I ran the gate while A was mid-write on `pyproject.toml`, not because of anything on the
committed tree. Concurrent-work noise, not a defect.

### A PENDING test went red the moment A landed the engine it was pretending did not exist

**Agent:** C · **Task:** spec 33 · **Date:** 2026-09-09

**What happened.** `test_candles_are_pending_with_a_fixture_and_no_builder` passed when written
and failed a few hours later with
`criterion raised - ValueError: a trade must carry 'qty'`. Nothing in my code had changed.

**Why.** The editable install is a plain `.pth` adding `src` to `sys.path`, so
`root_import_path` shadows the real `acsoe` **only when the fabricated tree has a `src/acsoe/`
of its own**. That is the entire reason `unbuilt_tree` exists next to `bare_tree`. My candles
and data-guard PENDING tests used `tree_with_harness`, which is built on `bare_tree` and carries
no `src/` at all — so once A landed engine 3, the criterion asked for `build_candles`, found
**A's real one in this checkout**, handed it my fabricated trades and got a `ValueError`. The
criterion was right to FAIL; the test was asserting on the developer's own repository instead of
on the tree it built.

**Fix.** `shadow_real_package(root)` writes an empty `src/acsoe/__init__.py` into the tree, and
every test asserting "the subject does not exist yet" calls it. The PASS and FAIL tests were
never affected because `fabricate_package` writes a `src/acsoe/` as a side effect of fabricating
anything.

**Consequence worth carrying.** A test that asserts absence has a hidden dependency on the
current state of the repository, and it decays silently as teammates build. The conftest
docstring warned about exactly this for `unbuilt_tree` and I did not carry the warning across to
`tree_with_harness`, which needed it more — it is the fixture used by the criteria that reach the
package by import.

### `data_guard_blocks_bad_data` passed both halves of its proof over a body that could not run

**Agent:** C · **Task:** spec 33 follow-up (found by A, confirmed by the lead) · **Date:** 2026-09-09

**What happened.** A read `_guard_context` before building engine 4 and found that it constructs
`EngineContext(now=..., cycle_id=1, run_id=..., config=..., clients=...)`. The real
`EngineContext` in `core/contracts.py` is `@dataclass(frozen=True, slots=True)` with exactly
`mode`, `run_id`, `now`, `config`, `clients`. **`cycle_id` is not a field** — a tick is
`(run_id, cycle_id)` and the cycle half lives in `state`, which I have written into my own
progress file twice — and **`mode` is required and was absent**. The call raises `TypeError`.
The criterion would have gone from PENDING to a red gate for everyone the moment A landed the
module.

**Why the tests did not catch it, which is the part worth reading.** Both halves of the
two-sided proof passed. They passed because `tests/verify/test_phase2_criteria.py` **fabricated
its own `acsoe.core.contracts`**, and the fabrication agreed with the mistake: it declared
`cycle_id` and no `mode`. The criterion's body ran, against a contract written by the same hand
that got the contract wrong, and proved nothing. A two-sided proof is only worth what its
fabricated subject is worth.

**Fix, and the rule that comes out of it.** `use_real_core(root)` copies the real
`src/acsoe/core/` into the fabricated tree; nothing hand-writes `EngineContext` or `Chains` any
more. `core/` imports nothing from the rest of the package (architecture invariant 0), so that
copy is cheap. The rule: **fabricate the subject a criterion judges; never fabricate a contract
the criterion is supposed to be held to.** The same change went into the daemon fabrication,
which now takes real `Chains` and `EngineContext` and overwrites only `Orchestrator` — which is
legitimately fabricated, because the behaviour under test is one the real orchestrator does not
have yet.

`_guard_context` no longer passes a fixed argument list either. It reads
`inspect.signature(EngineContext).parameters` and supplies what it can from `_context_values`,
reporting any required field it has no value for **by name** as PENDING. A corrected argument
list is the same defect one edit later: `core/contracts.py` is the lead's and may gain a field
at any time, and this script should say so rather than raise from inside a criterion.
`test_a_context_field_the_criterion_cannot_supply_is_named_not_raised` is the proof, and it is
the one place in the file that still fabricates a core contract — deliberately, because there
the subject under test is this script's adaptability to a contract it does not own.

### An unset OPERATOR REQUIRED threshold is a PENDING subject, not a FAIL

**Agent:** C · **Task:** spec 33 follow-up · **Date:** 2026-09-09

**What happened.** Engine 4's staleness threshold is `data_guard.max_data_age_s`, which is still
with the operator and is not in `config/default.yaml`. A is letting the `KeyError` stand in the
engine rather than substituting a placeholder, which is right — an engine silently receiving
`None` for a threshold is precisely the failure this project refuses. My criterion builds its
context from a `MappingConfig` over the committed file, so the `KeyError` surfaces inside
`process` and the criterion read a *fail-closed* gate as a broken one.

**Why PENDING.** A *configured* data guard does not exist yet, and "the thing it checks does not
exist yet" is what PENDING means. FAIL would make the criterion lie about whose problem it is,
and under the commit-at-every-boundary rule a FAIL blocks every other agent's finished work.
The general shape, which the lead asked for and which I agree with: **a missing OPERATOR
REQUIRED value is a PENDING subject.** `config/default.yaml`'s own machinery already treats an
unset trading threshold as a refusal to start rather than as an error, and the gate should agree
with it.

**Fix, and the half that keeps it from being a hole.** `_unset_config_key` pulls the dotted key
out of the `KeyError` and **checks** it against the parsed config. Absent from the file:
PENDING, naming the key. Present in the file and still raising: not this, and it propagates to a
FAIL — the engine asked for something that exists, in a shape it did not expect. Both directions
have a test; without the second, the PENDING branch would swallow every `KeyError` and the
criterion could never go red for a real defect.

**Also.** A's three `data_guard` reason codes — `market_data_stale`, `negative_spread`,
`missing_candle` — are in `REASON_PROSE`. A's note about `missing_candle` is carried into the
comment there, because it reads like a contradiction and is not: the historical loader must
never invent a missing bar, and the gate must never trade on a series with a hole in it. One is
about labelling, the other about acting, and fail-closed points the opposite way in each.

### A regression test that passed against the very defect it was written to catch

**Agent:** C · **Task:** spec 33 follow-up (found by A) · **Date:** 2026-09-09

**What happened.** A pointed out that `check_data_guard_blocks_bad_data` did
`dict(scenarios[key])` on `BAD_DATA_SCENARIOS`, which is a mapping *of mappings*: the outer
dict is copied and every nested region — `state["market_sensor"]`, `state["exchange"]` — stays
the same object as the module-level fixture. A had already been bitten by it on his own side,
where a test set a nested key and quietly changed the fixture for every test after it, with the
failure surfacing somewhere unrelated. Nothing in today's engine 4 mutates the region, but
engines publish into `state` by design — it is how they communicate at all — so "nothing mutates
it" is a property of one engine on one day, not of the contract.

**Fix.** `_guard_state` prefers A's `bad_data_state(name)` accessor, which returns a fresh deep
copy, and falls back to `copy.deepcopy` so the criterion keeps working against a `contracts.py`
that only exposes the mapping. One producer of a scenario rather than two.

**The part worth the entry.** My first regression test ran the criterion twice and asserted the
second run still PASSed. It passed — **and it passed with `_guard_state` deliberately reverted to
the shallow copy**, which meant it was proving nothing. The reason is a property of
`root_import_path` I had not thought about while writing the test: it drops and re-imports every
`acsoe` module for each criterion, so a module-level fixture is rebuilt from source on every run
and nothing a criterion writes into one can reach the next. **Cross-run contamination is already
impossible.** The leak that is reachable is within a single run, to the *next scenario*.

So the test was rewritten to fabricate that: a scenario module where `clean` and `missing_candle`
name one `market_sensor` region — not a contrived shape, since the four scenarios differ by a
flag each and a natural fixture builds them from a common base — and a guard that writes into
whatever region it is handed. Under a shallow copy the clean case arrives carrying a mark the
engine wrote while judging `missing_candle`, and the criterion reports a gate that blocks
everything: a real verdict, and one that reads as a defect in the engine. `test_a_shallow_copy_
really_would_have_leaked` monkeypatches `_guard_state` back to `dict(...)` and asserts exactly
that FAIL, so the positive test can be shown to fail.

Twice in one day now: a check that produced output that looked like checking while checking
nothing. The first was a fabricated contract that agreed with the mistake; this one was a test
whose mechanism was already prevented by something else in the file. **The cheap defence in both
cases is the same — make the green test go red on purpose before believing it.**

**Also.** A's fourth `data_guard` code, `no_market_data`, is in `REASON_PROSE`. It is
deliberately not folded into `market_data_stale`: "older than the guard allows" is a false
sentence when nothing has arrived, and it sends an operator after a lagging feed when the fault
is an absent one. A slow socket and a stream that never connected have different causes and
different fixes.

### `orchestrator_empty_registry` did not test an empty registry

**Agent:** C · **Task:** spec 33 follow-up (found by A, escalated by the lead) · **Date:** 2026-09-09

**What happened.** The criterion built its `Chains` from the **live**
`acsoe.bootstrap.GUARD_CHAIN` / `OPPORTUNITY_CHAIN` / `MANAGE_CHAIN`, ticked, and then asserted
that no guard blocked and that `trading_blocked_by` was absent. Those two assertions are true
only of an *empty* registry. Its name, its message and its whole premise say "empty registry";
its body said "whatever `bootstrap` currently holds". The two coincided because Phase 0
registers nothing, and they would have stopped coinciding the moment engines 1 to 4 were
registered.

A rehearsed it rather than assuming: with all four registered against the fake Kraken client —
which is REST-only, so `market_sensor` publishes no quotes — the guard chain blocks every tick
with `no_market_data`, which is invariant 3 working exactly as intended. **Registering the
engines would have turned a closed, green Phase 0 criterion red for nobody's defect.**

**Fix.** The tick runs over `chains_cls(guard=(), opportunity=(), manage=())` — constructed
empty here, never read from `bootstrap`. The two `failed(...)` branches are untouched: the
property they defend is that an empty chain is valid and a tick over one completes cleanly,
which is what stops a future orchestrator quietly requiring at least one engine, and it is worth
keeping permanently. `bootstrap` is still read for the three chain symbols, because their
presence and shape are the registry contract and their absence is what makes this criterion
report PENDING before spec 03 — but the tick no longer depends on what is in them. Keyword
arguments rather than `chains_cls()`, because the real `Chains` defaults every field to `()` and
a fabricated one in a test tree need not.

Nothing is lost by not reading the registry here. `is_gate_matches_registry` asserts the live
registry against the table in `engine-contracts.md` — I checked it for the mirror-image problem
at the lead's request and it is sound: it iterates every registered engine and compares `is_gate`
and `number` against the parsed table, so it does real work the moment the count stops being
zero, and its documented vacuous pass prints the count so a `0` in a phase that should have
registered engines is visible. `console_shows_live_rows` then exercises the real chain end to
end. Reading the live registry in this criterion was conflating two questions.

**Two tests, and the second is the point.** One registers a gate that blocks and asserts the
criterion still PASSes. The other drives the same fabrication through the orchestrator with the
*live* chains — what the criterion used to do — and asserts the blockers the two `failed(...)`
branches refuse actually appear, so the fabrication is a real reproduction of the regression
rather than a shape that could never have tripped it.

**Third time today.** A fabricated contract that agreed with a mistake; a regression test whose
mechanism was already prevented by module reloading; and now a criterion held to a registry that
happened to agree with it. All three produced output that looked like checking while checking
nothing, and none was caught by running the suite. Two were caught by A reading the source before
building against it, and one by making a green test go red on purpose. Those are the two things
that work.
