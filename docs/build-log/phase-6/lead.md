# Build log — Phase 6 — lead

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is diagnosis-before-fix.** Write **What happened** and **Why** the moment you know why
something is broken, *before* you write the fix; come back and add **Fix** afterwards. The code
survives on disk whatever happens to the session; the reasoning that found it does not.

Minimum headings per entry: What happened, Why, Fix.

**Rule 2, carried from Phase 5 and not retired with it:** every assertion is proven capable of
failing, and the proof goes here. Name the mutation, quote the red message, and say the file was
restored from a byte copy with its hash compared in the same statement that applied it. A claim
that an assertion works is not evidence. A mutation that survives a *subset* of the suite has not
survived — it has not been asked. An equivalent mutant is a checked negative, not a survivor.

**What Phase 6 is, and what that changes about these entries.** Phase 5 built components that
can be wrong while looking right. Phase 6 connects them to money: engines 9, 14, 16, 18, 21 and
22, and the fill simulator. For the first time the whole chain runs end to end, which means two
things for this log. First, **every number Phase 5 produced was measured on one gate in
isolation** — the skeptic's lift, the DI's refusal rate, the anomaly block rate — and this is the
phase that finds out what they are worth in sequence, after friction. Second, the manage chain
holds real positions, so a defect here costs money rather than a metric. Record what you checked
and found *sound*, not only what you found broken: an audit that lists hits alone says nothing
about coverage.

Three things from Phase 5 that will be in someone's way here, so they are written down rather
than rediscovered:

- **Engine 8 publishes `is_buy: false` when it refuses**, so its payload cannot distinguish "no
  call" from "not a BUY". It is an open item for this phase, it is not a fail-open today because
  engine 8's own `BLOCK` stops the tick, and it moves together with engine 15's read of that
  field. `expected_move_pct` is the field that got this right: omitted from the payload on a
  refusal, so the consumer fails closed on an absent key rather than on a value it must interpret.
- **50.2% of out-of-sample rows carry an incomplete feature vector** and engines 8 and 13 refuse
  those at any threshold. A chain that produces few candidates is that number showing up, not
  necessarily a defect.
- **At tier 1 nothing clears the cost gate, by construction** — the hurdle needs an expected move
  above 3.125% and the target barrier is 3.0%. Zero trades at tier 1 is these numbers interacting
  exactly as specified, and is not a bug to chase.

## Entries

### Four things found while writing the Phase 6 specs, before any code

**Agent:** Lead · **Task:** specs 80 to 102 · **Date:** 2026-09-16

Recorded at diagnosis, per rule 1. None is fixed; three need the operator and one is a spec.

**1. The fill simulator cannot live under `engines/execution/` without breaking two rules.**
*What happened.* The operator ruled the simulator B's, under `engines/execution/`, from my
reconnaissance finding that it had no owner. Writing its spec, I followed a resting post-only entry
through its life: it is placed by engine 18 on a bar tick and fills on some *later* tick, which only
the manage chain sees — engine 21 — and exits fill in engine 22. *Why.* Contract rule 3 forbids 21
and 22 importing `engines/execution/`, and `architecture-context.md` says mode differences live only
in the client layer. The reconnaissance report named the owner gap and did not follow the order far
enough to see the import gap; that is my miss, and the ruling was made on it. *Not fixed* — put to
the operator with a recommendation (a B-owned paper broker in `clients/paper/` wrapping
`clients.kraken`), spec 88.

**2. Invariant 6's "one open position per pair" is enforced nowhere.** *What happened.* `grep`
across `src/` finds no per-pair check; engine 11 counts open positions against
`max_concurrent_positions` without asking which pair. *Why it has been invisible.* Nothing could
open a position until this phase, so no test could reach it. *Fix, to be built:* spec 89, a refusal
in engine 11 that lands before engine 18 does.

**3. `Orchestrator._flag` reads a non-boolean truthy value as "finished".** *What happened.*
`bool(payload.get(field, False))` turns the string `"false"` into `True`, so a publisher that
serialised `entry_orders_cancelled` as text would clear `close_intent` with orders still resting.
*Why it matters now.* Until 21 and 22 exist the flags are always absent and the absent case is the
only one exercised. *Fix, to be built:* spec 81 — the test first, observed red, then `is True`.

**4. Nothing implements invariant 2's "adjusted by simulated fills", and the unadjusted balance
double-counts.** *What happened.* Engine 11's paper fallback uses `paper.starting_balances` as a
constant, and engine 19's equity is fetched cash plus positions value. *Why.* A simulated fill never
touches either source, so after one paper entry the cash is unspent: sizing allocates it again and
equity counts it twice. With real credentials the fetch succeeds and returns the real account's
cash, which no paper fill spends either. *Not fixed* — a money rule, put to the operator with a
recommendation (paper mode always reads a ledger of starting balances adjusted by recorded fills),
spec 88.

**Checked and found sound, so the list above is not mistaken for coverage:** engine 19 already reads
the fields 21 and 22 were always going to publish (`positions`, `orders`, `positions_value`,
`unrealised_pnl`, `hold_reason`, `closed_trades`), and fails to *nothing* rather than to a zero when
they are absent; the `close_intent` spy tests in `tests/core/test_orchestrator.py` build their own
`Chains`, so registering 21 and 22 cannot silently remove their absent case — what they do not cover
is a present payload (finding 3, spec 81); `TradeOutcome` already carries `liquidation`; the store
already exposes `resting_orders(intent=...)`, `order_by_userref` and `open_positions`, so specs 89
and 92 need no migration.

### The kill switch could be cleared by the string "false"

**Agent:** Lead · **Task:** spec 81 · **Date:** 2026-09-16

**What happened.** `Orchestrator._clear_close_intent_if_finished` clears `close_intent` when both
manage-chain flags are true, and it read them through
`bool(payload.get(field, False))`. Written out as a test, four of seven present-but-not-`True`
values clear a liquidation:

```
FAILED tests/core/test_orchestrator.py::test_only_the_boolean_true_clears_the_intent[false]
FAILED tests/core/test_orchestrator.py::test_only_the_boolean_true_clears_the_intent[0_0]
FAILED tests/core/test_orchestrator.py::test_only_the_boolean_true_clears_the_intent[1]
FAILED tests/core/test_orchestrator.py::test_only_the_boolean_true_clears_the_intent[true]
4 failed, 33 passed in 0.35s
```

`'true'` is in that list as a control and `'false'` is the one that matters: `bool("false")` is
`True`, so a publisher that serialised `entry_orders_cancelled` as text would clear the intent
**while entry orders were still resting on the book**, the orchestrator would mark the `close_all`
row consumed, and the kill switch would report a liquidation that had not happened. `[]`, `{}` and
`0` were already safe, which is why the hole is easy to miss: the coercion is right for three of
the seven shapes and silently wrong for the other four.

**Why it has been invisible.** Until Phase 6 the manage chain is engine 19 alone, so
`state["position_manager"]` and `state["exit"]` are always **absent**, `.get` returns the
default `False`, and only the absent branch has ever executed. Registering 21 and 22 makes the
payload always present — the branch stops being dead on exactly the change that gives it
something to be wrong about. The existing tests cover absent, and absent cannot stand in for
present: `engine-contracts.md` says these fields are booleans, so nothing had asked what happens
when a publisher's shape changes.

**Fix.** `_flag` accepts only the boolean `True` (`payload.get(field) is True`). Anything else —
absent, `False`, `None`, a string, a number — reads as *not finished*, the intent survives, the
command stays unconsumed and the manage chain retries next tick. That is the same fail-closed
default the gates use and the one `engine-contracts.md` already states for these two fields:
"absent or false always means 'not finished', never 'finished'".

**Consequence.** Seven-shape parametrised test plus a raised engine 21 (contract rule 7 gives
`ERROR` with `data={}`, which is present-and-empty, a shape the absent case also cannot produce).
B is told, because engines 21 and 22 must publish real booleans rather than anything
string-shaped; a publisher that sends `"true"` now fails to finish a liquidation loudly instead
of finishing one falsely.

**Mutation proof for the fix above.** Three mutations of `_flag`, each applied by an anchor whose
occurrence count was asserted to be exactly one, each restored from a byte copy taken before the
first mutation with the sha256 compared in the same statement (`restored byte-identical: True` on
all three). Scope `tests/core`, which owns the code.

| Mutation | Result | Killed by |
|---|---|---|
| A — a missing payload reads as finished | 4 failed, 49 passed | `test_close_all_sets_intent_and_freezes`, `test_close_intent_survives_when_a_flag_is_missing`, `test_close_all_is_not_marked_consumed_on_the_claiming_tick`, `test_an_interrupted_close_all_is_re_applied_before_the_first_tick` |
| B — a **missing field** reads as finished | 1 failed, 52 passed | `test_close_intent_survives_when_the_position_manager_raised` **only** |
| C — the original `bool()` coercion | 4 failed, 49 passed | `test_only_the_boolean_true_clears_the_intent[false, 0, 1, true]` |

**B is the answer to the question spec 81 was written to ask.** One test kills it, and that test
did not exist an hour ago: before today, a present payload that simply lacked the field read as
*finished* and **nothing in the suite objected**. The absent-payload case (mutation A) is killed
four times over and cannot stand in for it, because it exits at the `isinstance` branch above.
That is the shape the operator predicted — a fail-closed default that stops being exercised when
the absent case stops occurring — arriving one branch lower than expected: not at the payload, at
the field inside it.

### Engine 19 records equity as cash alone when a position cannot be marked

**Agent:** Lead · **Task:** spec 98 review, raised by B · **Date:** 2026-09-16

**What happened.** B asked me to confirm that engine 19 treats an absent `positions_value` as
"nothing to record" rather than defaulting, because spec 92 has engine 21 publish it **absent**,
never zero, on a tick where no mark could be taken. It does not. `MemoryEngine._write_equity`
reads it through `decimal_field(manager or {}, POSITIONS_VALUE_FIELD, ...)`, and `decimal_field`
returns **`Decimal(0)`** for an absent field. The equity row is still written; only an absent
`balances` skips it.

**Why it matters, and why it is invisible today.** `equity = cash + positions_value`. With an open
position and no mark, the row records equity as the cash alone — the position's entire value
missing from one tick of the series. Engine 17's drawdown is
`(peak_equity − equity) / peak_equity` against a peak read from the store, so a single unmarked
tick on a fully invested account is a drawdown approaching 100%, which trips
`safety.max_drawdown_pct` (0.10) and freezes the account over a missing quote. It has been
unreachable for exactly the same reason as the `_flag` defect: no engine has ever published a
`position_manager` payload, so the zero default has only ever been applied to an account with no
positions, where zero is the right answer.

**Fix (C's, spec 98 gains it).** Distinguish *no positions* from *positions that could not be
marked*: engine 19 already calls `store.count_open_positions()` for the snapshot, so when that
count is non-zero and `positions_value` is absent, write **no** equity row and name it in
`equity_skipped_reason`, exactly as an absent `balances` already does. When the count is zero, a
`positions_value` of zero is correct and the row stands. `unrealised_pnl` takes the same treatment
for the same reason.

**Consequence.** The general shape, which is the third instance this phase: **a default that is
correct in the only state the system has ever been in.** `_flag`'s `bool()` was right for the
absent payload, `decimal_field`'s zero is right for a flat account, and engine 11's
`max_concurrent_positions` check was right while nothing could open a position. All three become
wrong on the first tick that holds a position, which is what Phase 6 is for.

### An engine can measure an instant but not an interval, and the overshoot fell in neither

**Agent:** Lead · **Task:** spec 85's question, raised by A · **Date:** 2026-09-16

**What happened.** A built engine 3's per-tick trade ranges and stopped to report what it could
not express: `since_ts` had to be `context.now − timeframes.loop_tick_s`, because an engine is
stateless across cycles, `state` is fresh every tick, and `EngineContext` carried nothing about
the previous one. A named the precedent honestly — `bar_closed_on` has used the same device since
Phase 2 — and then named the difference, which is the part that matters.

**Why the precedent does not carry.** `bar_closed_on` asks about an **index**: which decision bar
this tick falls in. A late loop still lands in some bar and the question still answers once. A
**range** is an interval, and `now − loop_tick_s` is the previous tick only in a loop that ran on
time. Overshoot by four minutes and the interval starts four minutes after the previous tick
ended: every trade in that gap is inside no range any engine ever published. Engines 21 and 22
decide a stop touch from exactly those ranges, so the missed window is a missed stop — silent, on
real money, on precisely the ticks where the machine was busy, which is when a market is moving.
Nothing would have gone red: each range is internally consistent and the gap is between them.

**Fix.** `EngineContext.previous_now`, the previous tick's stamp, carried by the orchestrator —
`core/`, so the lead's. `None` on the first tick of a process and after a restart, never a
fabricated start, and a consumer measuring an interval publishes nothing for that tick rather than
guessing. A `previous_now` after `now`, or naive, is refused at construction: an interval running
backwards is a clock fault, not a small number. The clock is still read exactly once per tick.
A can now drop the `state["cycle_id"]` read it had added for the first-tick case, so engine 3
returns to reading no `state` at all.

**Mutations**, `tests/core`, each anchored on a literal asserted to occur exactly once and
restored from a byte copy with the sha256 compared in the same statement (all five
`restored byte-identical: True`):

| Mutation | Result | Killed by |
|---|---|---|
| N1 — `previous_now` is a computed offset, not the previous stamp | 2 failed, 56 passed | `test_previous_now_is_the_previous_ticks_now_not_a_computed_offset`, `test_a_late_tick_still_reports_the_interval_that_actually_elapsed` |
| N2 — the first tick claims a previous tick | 1 failed, 57 passed | `test_the_first_tick_has_no_previous_now` |
| N3 — the stamp is never carried forward | 2 failed, 56 passed | the same two as N1 |
| N4 — a backwards interval is accepted | 1 failed, 57 passed | `test_previous_now_is_refused_when_it_is_after_now` |
| N5 — a naive `previous_now` is accepted | 1 failed, 57 passed | `test_a_naive_previous_now_is_refused` |

**N1 is the mutation this change exists for**, and only the late-tick test can see it: on a
punctual loop the offset and the real stamp are the same value, so every test built on the
auto-advancing `_Clock` passes under N1. A double that advances by exactly one loop tick per read
cannot exhibit lateness — the property under test — which is the Phase 3 rule about doubles
arriving in a new place.

**A wrong turn of my own, worth recording.** My first late-clock double stepped the time on every
`now()` call, and the test failed reporting a seven-minute interval where it expected five. The
code was right: the orchestrator reads the clock more than once per tick (the run record, the
command stamp), so a per-read step measures how many times unrelated paths looked at the time. A
clock the test holds steady and advances explicitly between ticks makes the interval exact. The
failure looked like the feature and was the instrument — the same shape as the benchmark lesson in
`code-standards.md`, arriving in a test rather than a measurement.

### All four teammates died one minute before the limit reset, and the write-before rule paid

**Agent:** Lead · **Task:** Phase 6 team · **Date:** 2026-09-16

**What happened.** A, B, C-models and C-verify all hit the usage limit within 40 seconds of each
other at 23:49Z, one minute before it reset. Nobody was stopped and nothing was abandoned by
choice. The tree was left exactly as four sessions mid-task left it.

**What it cost, measured rather than assumed.** Every one of the four had written its claim into
`context/progress/<agent>.md` **before** starting and its findings into
`docs/build-log/phase-6/<agent>.md` **at diagnosis**. So the specs, the mutation tables, the two
findings raised in the last hour and every state-of-play line survived on disk; what was lost is
in-flight reasoning and nothing else. Phase 3 lost three build logs to an interruption because
they were being written *after* the work; this is the same event with the rule applied, and the
difference is the whole argument for it.

**What it did not cost.** No daemon has run at any point in Phase 6 — only the two `record.py`
processes and their supervisor, alive since 14:49 and untouched — so A's `drain_gaps` finding
(engine 2 records no `gap` markers through the paper broker) has damaged no recording. The
archive is intact and the fix is a one-line forward in B's lane.

**Two half-applied edits the deaths left, both found by reading the tree rather than the
reports.** `modelling/di.py` exports `score_many` in `__all__` and does not define it — C-models
landed the export and the `_BLOCK_ELEMENTS` reasoning and died before the function. And
`engines/risk/engine.py` still checks the portfolio cap before the per-pair refusal, with a
comment arguing the old order: the reversal I ruled had not been applied when B died. Neither is
a defect anybody introduced; both are what an interrupted edit looks like, and both are in the
handoff at the top of `feature-specs/PHASE-6-TASKS.md` rather than in anybody's memory.

**One red that is a tripwire working.** C-verify landed the two `REASON_PROSE` entries B was
waiting on, which fires B's `test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose` —
a test written to go red at exactly this moment and to tell whoever sees it what to do. It is
expected, it is B's to delete, and it is named here so the next reader does not diagnose it.

**Procedural note for the next time, and there will be one.** Four simultaneous deaths is not
four independent events: every session in this team shares one usage limit, so the limit is a
single point of failure for the whole team and it will always take them together. The mitigation
is not more agents, it is the discipline that made this cheap — claim before, diagnose before,
and a lead who reads the tree instead of the transcript.

### The baseline: two independent reds, one of them mine, and `compileall` was the wrong check

**Agent:** Lead · **Task:** Phase 6 baseline · **Date:** 2026-09-16

**What happened.** `verify.py --phase 6` on the quiet tree left by the four deaths:
`2 criteria: 1 PASS, 1 FAIL`. `toolchain_green` reported **56 failed, 2570 passed, 124 errors**
in 551 s, plus `mypy` and `ruff` each naming `src/acsoe/modelling/di.py`. Log:
`logs/verify/phase6-20260916-baseline-lead.log`, full pytest output under
`logs/verify/toolchain_green/20260916T000131_807204-pytest-attempt1.log`.

**Attribution, by counting rather than by path.** `_CHUNK` appears **359 times** in that output.
Every failing and erroring file except two is downstream of one broken module: C-models renamed
`_CHUNK` to `_BLOCK_ELEMENTS` at the top of `di.py` and died before renaming its two uses inside
`_mean_nearest`. Tournament, skeptic, prediction, anomaly, the DI's own tests, the training and
research suites and nine Phase 5 criteria all error on a `NameError` in a module they import.

**My earlier assessment of that file was wrong, and the way it was wrong is the lesson.** I ran
`python -m compileall` over `src/`, got a clean exit, and wrote that the module "imports and
compiles" and that only `from ... import *` would break. `compileall` checks **syntax**, not name
resolution: an undefined global inside a function body is a perfectly valid parse and a
`NameError` at call time. The check I ran could not have told me what I used it to conclude —
a check whose output resembles the claim while the claim is untrue, which is this project's most
repeated defect, committed by the lead in the middle of assessing somebody else's. `ruff`
(`F821`) and `mypy` (`name-defined`) both name it in one line, and I had run neither on that file.

**Fix.** The partial edit is saved to the scratchpad as `di-102-partial.diff` and quoted in the
handoff; `di.py` is restored to its committed state so the tree is usable by everyone else. It is
twelve insertions containing a rename and a comment and **no finished work** — `score_many` was
never written — so nothing of value is lost, and C-models re-applies it as part of a complete
spec 102 change. Restoring an uncommitted, half-applied edit by a dead session is not patching a
teammate's work: it is returning a shared tree to its last known good state, and the diff was
preserved before the file was touched.

**The second red is mine and it is correct.** `test_is_gate_parses_the_registry_out_of_the_document`
pins the set of gates parsed out of `engine-contracts.md`, and spec 80 added the **Y** for engine
16 by operator ruling. The test is doing its job: the gate list grew, and it is meant to take a
human decision to agree. It is C's file, so C-verify updates the expected set — the point of that
test is that nobody widens the gate list silently, including me.

**The third red is B's tripwire firing exactly as designed** and is B's to delete.

**So the baseline's verdict, stated honestly: one broken module, one document change awaiting its
test, one deliberate tripwire. No defect in any of the work the four sessions completed.**

### The two rehearsal findings ruled, and `state["block_status"]` landed in `core/`

**Agent:** Lead · **Task:** spec 87 review, specs 103–105 · **Date:** 2026-09-16

**What happened.** A's spec 87 rehearsal found two defects between engines (A's build log has
the diagnoses). I confirmed finding 1 against the code before reporting it:
`PaperBroker.balance()` adjusts by recorded fills only, and engine 21's `_mark` counts this
tick's fills in the portfolio value by design. The operator ruled on both — the paper-ledger
amendment (invariant 2) and the errored-engine record (invariant 12, contract rule 7).

**Why `core/` had to change for finding 2.** The opportunity chain put only the blocker's name
and reason into `state`, never its status. Engine 19 could therefore tell an engine that raised
from one that refused only by the empty payload — and an empty payload is also what a refusal
missing its `reason_code` looks like, the conflation `code-standards.md` warns about. A fix in
engine 19 alone would have had to guess.

**Fix.** `state["block_status"]` beside `block_reason` in both chains, absent when unblocked. Two
tests added. Three mutations, each killed by exactly one test (`tests/core`, 60 tests):
L1 opportunity status dropped → `test_an_opportunity_engine_that_raised_is_distinguishable_from_one_that_blocked`;
L2 guard status dropped → `test_a_raising_engine_becomes_error_and_blocks_without_killing_the_tick`;
L3 opportunity status hardcoded `BLOCK` → the first again. Restored file sha256
`52abd51c32e02b21734e1d925a652cd0ee5c22c643b0bd8b6500b0be37936731`.

**My own wrong turn, recorded.** The first sweep script wrote mutant L1 to disk and then raised
before running anything — `subprocess` could not find `.venv/Scripts/python.exe` by relative path —
and its restore sat after the call rather than in a `finally`. The mutant stayed on disk. I found
it by grepping for the line, restored it by a single-anchor patch, and re-ran with
`sys.executable` and a per-arm `try/finally` restore checked by hash. Nobody else was in the tree.
It is the "restore before the next mutation" rule from the other side: **a restore that is not in
a `finally` is a restore that only runs when nothing went wrong.**

**Also.** `core/orchestrator.py`, `tests/core/test_orchestrator.py` and
`context/architecture-context.md` were CRLF on every line in the working tree against LF blobs;
all three were written back as LF.
