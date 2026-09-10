# Build log — Phase 3 — c-interface

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem
and its fix, and every decision where two approaches were viable. Not at the end of
the session — three IDE crashes in Phase 1 each took the code and the log at different
moments, and only the entries already written survived.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-3.md` at phase close.

## Entries

### `verify.py` threw away every line of toolchain output on one non-UTF-8 byte

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

**What happened.** Capturing the pre-spec-45 baseline, `--phase 0` printed

```
FAIL    toolchain_green              pytest exit 1: (no output)
```

and, above the banner, an unhandled `UnicodeDecodeError: 'utf-8' codec can't decode
byte 0x97 in position 3880: invalid start byte` raised inside a `subprocess`
`_readerthread`. The same run under phases 1, 2 and 3 printed the full list of failing
tests. The verdict was right in every case — the tree is genuinely red from A's and B's
in-flight work — but on phase 0 the *reason* was gone.

**Why.** `_run_tool` (`scripts/verify.py:1264`) calls `subprocess.run(..., text=True)`
and names no encoding, so the child's bytes are decoded with whatever
`locale.getencoding()` returns for this process. Byte `0x97` is an em-dash in cp1252,
which is what pytest emitted, and it is not a valid UTF-8 start byte. The three
baseline phases ran under the default locale and decoded it as an em-dash. Phase 0 I
happened to run with `-X utf8`, which flips the same call to strict UTF-8, and the
decode raised **on the reader thread** rather than at the call site — so
`subprocess.run` returned an empty `stdout` and an empty `stderr` instead of
propagating, and `_run_tool` handed back `(1, "")`. `check_toolchain_green` rendered
that as `(no output)`. The gate reported a FAIL it could not explain, which is the one
thing the standing rule about never piping this script through `tail` exists to
prevent.

It is latent rather than exotic: `PYTHONUTF8=1` is a common Windows setting, and any
operator who has it on loses all toolchain detail from every phase, not just phase 0.
The mirror-image bug exists in the default locale — a genuinely UTF-8 byte in a tool's
output mojibakes silently rather than raising.

**Fix.** Pending — see the next entry.

*(Fix, completing the entry above.)* `_run_tool` and `_interpreter_with_toolchain` now pass
`encoding="utf-8", errors="replace"` explicitly to `subprocess.run`. The decode is
deterministic regardless of the operator's codepage or UTF-8 mode, it cannot raise, and a
byte that is not valid UTF-8 costs one replacement character instead of the whole report.
`errors="replace"` rather than `errors="strict"` on purpose: the output is diagnostic prose
for a human, and one mangled dash in a pytest summary is worth incomparably more than a
clean exception that deletes the summary. Every other read in this file already names
`encoding="utf-8"`; these two calls were the only place an encoding was inherited.

### A crash mid-run printed nothing at all, including the criteria that had already passed

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

**What happened.** The first baseline capture ran `--phase 0` with stdout redirected to a
file. The process died — exit 139, the bash rendering of the 0xC0000005 access violation
this machine is known for — and `phase0.txt` was **zero bytes**. Not truncated: empty. Six
criteria had run and four of them had already reached a verdict, and none of that reached
disk. I re-ran it and got a clean 7 PASS, so the fault was the known intermittent one and
not a defect in any criterion.

**Why.** Two causes, and only the second is mine to fix. Redirected stdout is
block-buffered, so nothing is flushed until the buffer fills or the process exits cleanly —
a hard crash discards it. But the deeper reason is `main`: it builds the entire report
**after every criterion has run**, with a single `print(format_report(...))` at the end. So
even line-buffered, a run that dies on criterion 4 of 7 prints nothing, because there is
nothing to print yet. The verdicts exist only inside a list comprehension until the run
finishes.

That matters more here than it would in most scripts. This gate is the one place the
project looks to decide whether a phase is real, `PHASE-3-TASKS.md` tells every agent never
to pipe it through `tail` because the detail is what makes a FAIL diagnosable, and this
machine has a documented intermittent fault that kills processes mid-run. Those three facts
together mean the run most worth reading is exactly the run that prints nothing.

**Fix.** `format_report` is split into `report_header`, `criterion_line` and
`report_summary`, and `main` now prints the header, then each criterion's line as that
criterion returns, flushing each one, then the summary. `format_report` is kept and
composes the same three pieces, so the unit tests that call it directly still hold and the
**bytes on stdout are identical to before** — the report is not reformatted, only emitted
progressively. The one thing that had to move is the column width, which `format_report`
computed from the finished results; it is computed from the criterion *names* instead,
which are known before the first check runs, so a streamed line lands in the same column
the batched one did.

A crash now leaves every verdict up to the crash on disk, and the missing tail is itself
the evidence of where it died.

### A criterion that reads `pending_commands()` cannot see a command the daemon has already obeyed

**Agent:** C · **Task:** spec 45, criterion 4 · **Date:** 2026-09-10

**What happened.** `safety_freezes_on_drawdown_without_opportunity_chain` drives the real
orchestrator over the seeded database with `safety` alone in the guard chain, ticks three
times, and asserts one `freeze` row was written and no `close_all`. It reported

```
the breaker tripped on the seeded drawdown and wrote no `freeze` row. Commands written: []
```

while `tripped` correctly carried `drawdown`. Engine 17 was doing exactly the right thing
and the criterion could not see it.

**Why.** Two causes, one after the other, and both are the criterion's.

The first is that a daemon starts `idle`, and `safety` does not re-emit a `freeze` for a
system that is not running — correctly, because freezing something already stopped is a
no-op and would append a row every tick forever. The criterion was ticking an orchestrator
nobody had activated, so it was asking whether the breaker stops a system that was already
stopped. Fixed by writing a real `activate` row to the `commands` table before the first
tick, the way the console writes one, and letting the real command reader apply it — which
has the side benefit of exercising the console-to-reader-to-breaker path rather than
asserting around it.

The second survived that fix. The helper read `store.pending_commands()`, which by
definition returns rows **nobody has claimed yet**. The orchestrator's command reader runs
at the top of every tick: the `activate` is claimed and consumed on tick 1, and the `freeze`
that `safety` writes during tick 1 is claimed and consumed at the top of tick 2. By the
third tick both rows are consumed and `pending_commands()` is empty — which is not "no row
was written", it is "every row was obeyed". The criterion was reading a *queue* and asking
it a question about *history*.

B's `tests/engines/test_safety.py` uses the same helper shape and is right to: those tests
call `SafetyEngine.process` directly, so no reader ever runs and nothing is ever consumed.
The moment a criterion puts a real orchestrator around the engine, the queue empties behind
it. This is a general hazard for anything in `verify.py` that drives a daemon rather than an
engine, and `check_commands_round_trip` already reads the `commands` table directly through
SQLite for the same reason — I had the precedent in front of me in this file and reached for
the store accessor anyway.

**Fix.** `_safety_command_rows` reads the `commands` table directly, selecting every row
whose `source` is `CommandSource.SAFETY` ordered by `id`, claimed or not. The source value
comes from B's enum rather than the string `'safety'`, for the same reason the exposure
query now takes its three status values from `PositionStatus`, `OrderStatus` and
`OrderIntent` — see the next entry.

**Consequence.** Criterion 4's idempotency assertion is now a claim about what was written
over three ticks rather than about what is still queued, which is what "re-emits no command
while the condition persists" actually means. Worth carrying into Phase 4: engine 19
`memory` will write to this table too, and any criterion asking "did this get written" must
read the table, not the queue.

### `safety_inputs_all_from_the_seed` was comparing zero against zero on one of its six inputs

**Agent:** C · **Task:** spec 45, criterion 6 · **Date:** 2026-09-10

**What happened.** The criterion went green with the message

```
all six inputs match the seeded tables (drawdown 0.2000..., 8 losing trade(s),
0 error block(s), 18 outage tick(s), 2 position(s), 2 resting order(s))
```

Five of those numbers are evidence. `0 error block(s)` is not. `--phase 0`'s
`seed_fixtures_present` reports **23** ERROR blocks in the seed, so the criterion and the
engine had agreed on a number that is wrong on both sides.

**Why.** The criterion clocked its `EngineContext` at `PHASE3_NOW`, a fixed instant I chose
so two runs a week apart give the same verdict. The seed's rows are stamped at the seed's
own epoch, which is earlier, and `safety`'s error-rate input is "ERROR rows inside
`safety.error_rate_window_s` counted back from `context.now`". At my instant that window
lands entirely after the seeded rows and contains none of them. The engine returned 0 and
the criterion's own SQL, using the same window, also returned 0.

This is precisely the failure mode spec 45 warns about in as many words — *"would it still
pass if the thing it names were false?"* An engine that ignored the error-rate input
entirely and returned a hardcoded 0 would have passed this criterion, and so would one that
read the wrong table. Two independent computations agreeing on zero is not agreement about
anything; it is both of them looking at an empty set. A fixed clock is the right instinct
for determinism and the wrong one for a fixture whose rows carry their own timestamps.

**Fix.** `_seed_now` reads the newest `block_records.ts` out of the seeded database and
criteria 4 and 6 clock themselves from that instead. It is still deterministic — the seed is
generated from a fixed seed value, so the instant is the same on every machine and every run
— but it is now the seed's instant rather than one I picked, so the error window contains
the rows it is supposed to contain. The other five inputs are unaffected: drawdown, loss
streak, positions and resting orders are not time-windowed, and the outage walk is anchored
on `(run_id, cycle_id)` rather than on the clock.

**Consequence.** A criterion asserting `reported == expected` needs one more question asked
of it than "do they match": *can this comparison distinguish anything?* Both sides being
derived from the same wrong assumption is the shape that survives review, because the code
looks like it is checking something. The other five comparisons here were fine only because
the seed's values for them are large and specific.

### The `safety` criteria were seeding against the seed module's defaults, not the operator's config

**Agent:** C · **Task:** spec 45, criteria 4, 5 and 6 · **Date:** 2026-09-10

**What happened.** With the clock fixed, criterion 6 reported **13** ERROR blocks where
`--phase 0`'s `seed_fixtures_present` reports **23** over what is nominally the same seed.
Both numbers are right; they are two different fixtures.

**Why.** `seeded_console_db` calls `seed_database(db_path)` with no `thresholds` argument, so
the seed scales its fixtures against `seed.py`'s module defaults. Those defaults are
documented as "fixture-shape constants, not recommended values", and one of them has
diverged: the default `max_errors_in_window` is 10 where `config/default.yaml` says 20. The
seed overshoots whatever limit it is given by three, so the default-scaled fixture holds 13
ERROR rows — which overshoots 10 and sits comfortably under 20, so the *configured* error
rate never trips against it. `check_seed_fixtures_present` already avoids this by building
`SeedThresholds` from the config through `_seed_threshold_kwargs`; `seeded_console_db` was
written for the console criteria, which do not care what the thresholds are, and I reused it
for three criteria that care a great deal.

Nothing was failing, which is what makes it worth writing down. All three criteria passed
against the default-scaled seed. The defect is latent and it is in the direction the seed
exists to prevent: **the moment the operator raises a limit, the criteria stop testing what
they claim to.** `safety_escalates_on_sustained_outage` asserts the seeded outage run is at
least `safety.max_consecutive_data_blocks` long; the default-scaled run is 18 and the
configured limit is 15, so it fits today. Raise `max_consecutive_data_blocks` to 20 and the
criterion FAILs, accusing the seed of being too short — while the config-scaled seed it
should have been reading would have carried 23. `_seed_threshold_kwargs`'s own docstring
describes exactly this: "a fixture pinned to a constant stops overshooting the moment the
operator raises a limit, and the criterion accuses the seed of a bug the criterion caused."

B independently found the same defect in the shared `seed_fixtures` fixture in
`tests/conftest.py` — also mine — and shadowed it locally in `tests/engines/test_safety.py`
rather than depending on it. That is two places now, from two directions, which says the
convenience helper is the wrong default rather than that either caller was careless.

**Fix.** `_phase3_seeded_db` seeds through the same config-derived `SeedThresholds` path
`seed_fixtures_present` uses, and criteria 4, 5 and 6 call it instead of
`seeded_console_db`. `seeded_console_db` is left alone: the console criteria genuinely do
not care, and changing it would be a Phase 1 and Phase 2 change inside a Phase 3 spec.

**Still open, and not mine to close inside this spec.** The shared `seed_fixtures` fixture in
`tests/conftest.py` has the same defect and spec 45's scope limits keep me out of it. Raised
to the lead as its own item.

### The induced failures: what each of the seven criteria was made to fail against

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

Spec 45 requires each criterion observed PENDING, observed PASS and **observed FAIL**, with
the induced failure recorded here — *"a check nobody has seen fail is a comment."* All
twenty-one observations are in `tests/verify/test_phase3_criteria.py`; this is the account of
what was broken to produce the FAIL half and what it cost to learn.

**How the failures are induced, and why it is not a fabricated tree.** `phase3_tree` copies
the **real** `src/acsoe`, the real `db/migrations/`, the real `config/` and the real harness,
and a FAIL is induced by changing exactly one string in one real module in the copy. The
alternative — fabricating an engine to be wrong — is what `check_data_guard_blocks_bad_data`
did, and its fabricated `EngineContext` agreed with the criterion's own mistake so precisely
that the criterion's body never executed while both halves of its two-sided proof passed.
`patch_module` refuses to apply when its anchor is not found exactly once, so a test cannot
silently degrade into asserting that the criterion fails for some unrelated reason.

**`cost_gate_uses_live_fee_tier`** — four failures. A cost engine with the fee schedule
compiled in as module constants, otherwise a faithful implementation of invariant 5 that
blocks below the hurdle; this is what `AGENTS.md` opens by warning about, and it is why the
criterion runs two tiers rather than one. An engine reading the maker fee and forgetting the
taker fee, which moves the net edge with the tier but by the wrong amount — this is why the
criterion asserts the *exact* fee delta rather than "the two differ", and it would otherwise
have accepted a gate mispricing every candidate in the system by the taker leg. `clears =
True`, a gate that lets everything through. `clears = False`, a gate that refuses
everything, which the block half alone would accept. A fifth case is not a FAIL and is the
interesting one: pointing `EXCHANGE_FEE_TIER_KEY` back at the audit's wrong `"fees"` makes
the engine fail closed with `cost_inputs_unavailable`, and the criterion reports **PENDING
naming spec 40** rather than FAIL — that is unfinished wiring, not a broken gate, and a FAIL
there would stop the phase over work in flight.

**`risk_rejects_sub_ordermin`** — three. A gate that bumps a sub-minimum size *up* to
`ordermin` and approves it instead of refusing, which is the failure the second half of the
criterion exists for and the reason "no order was placed" is not a sufficient assertion: it
places a trade at a size nothing sized. A gate that refuses and publishes the quantity
anyway — this needed **two** patches, because `to_state_data` omits the four sizing fields
when `approved` is false *and* `qty` is `None` on a rejection, so either alone leaves the
payload unchanged; `_reject`'s own docstring names this refactor ("a field a later refactor
could quietly start filling with `ordermin`") as the thing to guard against, so the induced
defect is exactly that refactor. And a gate refusing for `below_costmin` instead of
`below_ordermin`.

That last one is worth its own note, because the first version of the test was worthless. I
induced it by renaming the constant `REASON_BELOW_ORDERMIN` in `risk/contracts.py` — and the
criterion reads *that same constant* to decide what it expects. Renaming it moved the
expectation and the answer together and the test passed while proving nothing: the exact
"mock that agrees with its caller" shape this phase exists to correct, reproduced by me,
inside the test written to prove I had not done it. The patch now goes in the **engine**, at
the `_reject` call site, so only the answer moves.

**`universe_varies_with_balance`** — one, against a fabricated engine 7 since none exists: a
filter that runs, publishes a universe and never looks at the balance, which a criterion
checking only that a universe came back would accept. The stand-in's real rule had to be
chosen with some care. `held >= costmin` does not discriminate over the committed fixtures —
every pair's `costmin` is 5.00, so $10 and $5,000 both admit all four pairs and the PASS half
failed. It now requires the balance to fund `costmin` on every concurrent position the
operator allows, which is invariant 7 crossed with a configured limit rather than a constant
invented in a test.

**`safety_freezes_on_drawdown_without_opportunity_chain`** — two, plus a PENDING. A breaker
that emits `close_all` where spec 37's ruling says `freeze`, induced by leaving
`CONDITION_ACTION` correct and changing `command_for` — the shape a half-applied ruling
leaves behind, where the policy is corrected and the code reading it is not. And a breaker
with its emission suppression removed, which appends a row every tick forever; the criterion
ticks three times for exactly this. The PENDING case restores the pre-ruling
`CONDITION_ACTION[DRAWDOWN] = CLOSE_ALL` and asserts the criterion waits and names spec 42
rather than failing B for work not yet claimed.

**`safety_escalates_on_sustained_outage`** — three. `>` weakened to `>=` on the outage
comparison, which fires the breaker a tick early and liquidates an account over an outage
that has not reached the operator's threshold; this is the half usually missing and a
criterion asserting only the escalation passes against it. The outage mapped to `freeze`, so
the breaker declines the one thing invariant 14 reserves for it. And the outage walk ordered
by `cycle_id` instead of `ts`, which interleaves the seed's two `run_id`s — the seeded run
spans a restart on purpose and this is the defect that arrangement exists to catch.

**`safety_inputs_all_from_the_seed`** — two, and they catch different things. A breaker that
prefers a `state["memory"]` payload when one is present: it would pass every test written
against a database and read nothing on a live tick, and only the poisoned-state half notices
it. A breaker returning a hardcoded loss streak of 0: the poisoned half **cannot** catch that
one, because a constant does not move when `state` moves either, and it is the
compare-against-the-seeded-rows half that does. Neither half is redundant.

**`phase_3_gates_have_both_tests`** — two. A gate whose tests all assert `BLOCK` and none
assert `OK`, parametrised across all four engines so a failure names which. And the one the
criterion's design is for: two tests named `test_it_blocks_on_a_wide_spread` and
`test_it_passes_on_a_tight_spread` whose bodies are `assert True`. A criterion grepping test
*names* calls that complete. This one parses the AST and looks for the assertions, in both
the `EngineStatus` and the `blocks_trading is True/False` spellings — engines in this repo are
tested in both styles, and recognising only one would report a gate as untested because of
the assertion style its author happened to prefer.

**What the exercise actually bought.** Two of the twenty-one observations found real defects
in criteria that were already green: the `REASON_BELOW_ORDERMIN` self-agreement above, and
the zero-against-zero comparison recorded in its own entry earlier. Both were criteria that
looked right, passed against the real engines, and were checking less than they claimed.
Neither would have been found by writing more PASS cases.

### A Phase 1 timing test failed once under the full suite and passes in isolation

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

**What happened.** With spec 45's criteria and tests landed, one `--phase 1` gate run reported

```
FAIL toolchain_green  pytest exit 1: FAILED
  tests/verify/test_phase1_criteria.py::test_pass_against_a_fabricated_console[console_websocket_pushes_on_change]
  1 failed, 1197 passed
```

In the same run, the criterion that test drives **passed** at the top level, reporting a push
508ms after the watermark moved. Run in isolation three times it passed in 8.07s, 1.65s and
2.19s. Recording it rather than smoothing it over, per `PHASE-3-TASKS.md`.

**Why.** I do not think this is the machine's intermittent native fault, and it is worth
saying so because the standing advice on a FAIL — re-run the named test alone — gives the
same answer for both and the two want different responses.

`console_websocket_pushes_on_change` asserts a push arrives inside a **1000ms budget** against
a console polling at `console.poll_interval_ms`, 500ms in the committed config. That is a
factor of two of headroom, measured on a machine also running the rest of the suite. It is a
wall-clock assertion, and wall-clock assertions get slower under contention rather than
wrong. The isolated runs took 1.65s to 8.07s for the same eight parametrised cases, which is
itself a fivefold spread on an idle machine.

**What I think my part in it is.** Spec 45 added 45 tests, nineteen of which copy the package,
the migrations, the config and the harness into a temporary tree. The suite went from 1052 to
1197 tests and got measurably more I/O-bound, and the flake surfaced on the first full run
after that. The sensitivity was already there; I made it likelier to fire. I have narrowed
the copy to `src/acsoe` rather than all of `src/`, which drops the editable install's
`acsoe.egg-info` from nineteen copies a run — a small improvement, not a fix.

**Fix.** None, deliberately. Widening the budget or adding a retry would be **changing a
Phase 1 criterion**, which spec 45's scope limits forbid in as many words, and doing it
inside a Phase 3 spec is exactly how a timing assertion gets quietly loosened until it
asserts nothing. Raised to the lead as its own item instead. My view, for whoever picks it
up: the honest fix is to stop measuring the budget in wall-clock time under a shared CPU —
the interesting property is "the push happens on the first poll after the watermark moves",
which is a count of polls and does not care how loaded the machine is. The 1000ms is standing
in for two poll intervals and could say so directly.

**What I am not claiming.** One observation is not a pattern. If it recurs on a run where
nothing else is loading the machine, that is evidence for the native fault instead and this
entry is wrong; a later entry should say so rather than this one being edited.

### Decision: how each criterion decides between PENDING and FAIL when its subject exists but is not wired

**Agent:** C · **Task:** spec 45 · **Date:** 2026-09-10

**Options.** Three of the four Phase 3 engines existed when the criteria were registered but
were not wired to engine 1, and `safety`'s policy table still carried the pre-ruling
`CONDITION_ACTION`. `try_import`'s rule — a module of ours that is not written is PENDING, a
missing third-party dependency is FAIL — does not reach that state, because the module *is*
written. So each criterion had to choose: judge the engine as it stands and report FAIL, or
detect the unwired state and report PENDING.

**Chose.** PENDING, named to the spec that will land the wiring, and detected from the
engine's **own answer** rather than from a version marker. `cost` and `risk` both fail closed
with `cost_inputs_unavailable` / `risk_inputs_unavailable` when handed a `state["exchange"]`
whose keys they do not recognise, so the criteria drive engine 1's real payload in and treat
that specific reason code as "spec 40 / spec 41 is not done" — quoting the engine's own
operator sentence in the PENDING line. `safety` has no equivalent, so criterion 4 reads
`CONDITION_ACTION[DRAWDOWN]` and reports PENDING naming spec 42 while it is not `FREEZE`.

**Because.** Mid-phase the bar is no FAIL and a FAIL is a stop at any point in a phase. A
criterion that goes red the moment another agent's in-flight work is halfway landed stops the
phase over work that is progressing normally, and the agent whose spec is named cannot fix it
except by finishing — at which point it goes green on its own. That is what PENDING is for.
The reverse risk, that PENDING becomes a way of not noticing, is answered by what the PENDING
is keyed on: each one is keyed to the *engine's own refusal*, so the criterion starts judging
behaviour the moment the engine stops refusing. Nobody has to remember to switch it on.

**Cost, and it is real.** A genuinely broken gate that happens to fail closed for one of
those reasons reports PENDING rather than FAIL, and would keep reporting PENDING. The
mitigation is that the PENDING message quotes the engine's own reason verbatim rather than
saying "not wired yet", so a reason that is not the expected one is visible in the gate
output rather than hidden behind a category. `test_a_cost_gate_that_cannot_read_engine_one_is_pending_not_a_fail`
pins the behaviour so it is a decision rather than an accident.

**It expired within the session, which is the point.** B landed specs 41 and 42 while spec 45
was being built, and both criteria came off PENDING and started judging behaviour without
anything of mine changing. Criterion 4 in particular went from PENDING to a real FAIL — the
freeze row was not being written — and that FAIL was correct and led somewhere, twice: first
to a daemon nobody had activated, then to a criterion reading the command queue instead of
the command table. A criterion that had reported FAIL from the start would have been noise
for the hours before that and indistinguishable from the FAIL that mattered.
