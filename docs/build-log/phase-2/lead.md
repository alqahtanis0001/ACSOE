# Build log — Phase 2 — lead

Entries the lead owns directly. Consolidated into `docs/build-log/phase-2.md` at phase close.

Minimum headings per entry: What happened, Why, Fix.

## Entries

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
