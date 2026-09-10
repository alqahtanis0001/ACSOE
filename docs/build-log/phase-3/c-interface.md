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

### Correction: `tests/conftest.py` was already fixed, and I escalated it without opening the file

**Agent:** C · **Task:** spec 45, follow-up · **Date:** 2026-09-10

**Correcting the entry above**, "The `safety` criteria were seeding against the seed module's
defaults". Per rule 6 this is a new entry rather than an edit to that one.

**What that entry got right, and it still stands.** `seeded_console_db` in `scripts/verify.py`
genuinely did call `seed_database` with no `thresholds`, my three `safety` criteria genuinely
were reading a default-scaled seed, and the fix — `_phase3_seeded_db`, taking the same
config-derived path `seed_fixtures_present` uses — is real. I verified that one empirically:
13 ERROR rows before, 23 after, against a configured limit of 20.

**What it got wrong.** It also said the shared `seed_fixtures` fixture in `tests/conftest.py`
had the same defect, and I raised that to the lead as its own item. It does not. At HEAD it
reads:

```python
return seed.seed_database(tmp_path / "acsoe.sqlite", thresholds=seed_thresholds_from_config())
```

The lead checked it, then ran the fixture and counted **30 non-`data_guard` block rows out of
55** — 13 is what the module defaults would give. `tests/conftest.py` was last touched in
`3765e0d`, which is my own Phase 2 commit for specs 32 and 33, and its docstring already
describes the 13-row bug in the past tense.

**Why I believed otherwise.** B's `tests/engines/test_safety.py` carries a fixture whose
docstring says it "deliberately shadows the shared `seed_fixtures` fixture in
`tests/conftest.py`, which calls `seed_database` with no `thresholds` argument", and ends
"Reported to C, who owns the shared fixture". That was true when B wrote it. I read it,
recognised the shape from the defect I had just found in my own file, treated the two as one
finding, and escalated — **without opening `tests/conftest.py`.** Two independent-looking
reports of the same defect felt like corroboration; one of them was a note about the past.

**The generalisation, and it is not really about this fixture.** A comment describing another
agent's state goes stale silently, because nothing fails when it does. B's `cost/contracts.py`
docstring went stale the same way in the same week — "deliberately not in C's `REASON_PROSE`
yet; C has been asked to add it", while B's own test had been asserting the opposite for days
— and I caught that one only because I went to action the request and looked at the file
first. Here I did not, and the direction was reversed: B's note said a thing was broken when
it was fixed, and mine then said the same. The lead has since seen the mirror image, a
progress file claiming a ruling had been applied when it had not.

Three notes, three drifts, in both directions, in one phase. The rule that follows is the
lead's and I am adopting it: **re-check the file before citing a defect from any note,
including my own.** Reading is what produced the wrong belief; only running it produced the
right one.

**Consequence.** The item is struck from `context/progress/c-interface.md` rather than left
for the next reader to act on. No code changes — `_phase3_seeded_db` was the right fix for
the defect that was real, and `tests/conftest.py` needs nothing.

### Spec 46: the enumeration, broken on purpose, and the empty state that does not read the tally

**Agent:** C · **Task:** spec 46 · **Date:** 2026-09-10

**Seven codes added to `REASON_PROSE`**, all with the producing agent's wording kept
verbatim: engine 7's six new per-exclusion codes plus `scout_inputs_unavailable`, and
`safety_inputs_unavailable` on B's explicit yes. `below_ordermin`, `below_costmin` and
`insufficient_quote_balance` needed nothing — `scout` reuses engine 11's codes deliberately
rather than minting parallel ones, which is right: it is the same arithmetic and should read
the same on screen, and two codes for one condition would give the operator two different
sentences depending on which gate got there first.

**The enumeration reads the module's attributes, not its `EXCLUSION_REASONS` tuple, and the
difference is load-bearing.** The tuple is the exhaustive list of ways a *pair* can be
excluded, ordered by the filter's own application order, and B deliberately keeps
`scout_inputs_unavailable` out of it: that code is a statement about the tick rather than
about a pair, and counting it in the tally would break `scanned == entered + sum(tally)`. A
test enumerating only the tuple would therefore have left exactly that code unmapped — and
it is the one an operator meets when something is *broken*, as opposed to when the market is
merely quiet. So `declared_reason_codes` walks `vars(module)` for `REASON_*` strings, which
covers a code whether or not B remembers to put it in the tuple, and a separate test pins
both halves of B's arrangement: the code is in `REASON_PROSE` *and* is not in
`EXCLUSION_REASONS`.

**I broke the check before trusting it**, per the standing rule the lead added to
`code-standards.md` today. Two ways, because they prove different things:

1. Against a fabricated module carrying a code absent from the table — `unmapped()` returns
   it, which shows the *mechanism* discriminates.
2. By deleting the real `barriers_below_tick_size` line from `format.py` and running the
   suite. Two tests went red with
   `AssertionError: assert {'REASON_TICK_GRID_TOO_COARSE': 'barriers_below_tick_size'} == {}`,
   and the entry was restored. That is the one that matters: the first test would still pass
   against a hand-written list, and the whole argument for enumerating is what happens when a
   code is *added*.

A third test records why any of this is worth doing — `operator_reason("quote_delisted_mid_tick")`
returns "No reason was recorded." No exception, no log line, no degraded rendering. The
failure mode is silence in the column whose entire job is to say why.

**`quote_not_provably_stable` is the one I would have got wrong**, and the test now pins the
distinction rather than just the presence. It exists beside `crypto_quoted` on the lead's
spec 43 ruling because a universe that shrank *by policy* and one that shrank because nobody
supplied `trading.stable_quote_currencies` look identical from the outside, and only the
second is a fault somebody must fix. Two codes rendering the same sentence would undo that
ruling in the view layer, where nothing else would notice — so
`test_the_two_crypto_quoted_codes_do_not_share_a_sentence` asserts the sentences differ and
that the second one points at configuration rather than at the market.

### Spec 46 step 5: the empty state does not read engine 7's tally, and the gap is structural

**What happened.** Step 5 asks me to confirm the existing counts-based empty state reads the
tally B publishes in `state["scout"]`, and to say so in the build log if it does not. **It
does not.** `ConsoleReader.feed_summary` in `src/acsoe/console/reader.py:462` builds four
stages and the first two are hardcoded absent:

```python
FeedStage(label="Pairs scanned", count=None, detail=_NOT_RECORDED),
FeedStage(label="Entered the tradable universe", count=None, detail=_NOT_RECORDED),
```

So the screen `ui-context.md` describes as the single most-viewed state in the product —
*"Scanned 412 pairs. 38 entered the tradable universe."* — currently renders its first two
lines as not recorded. Per the spec's scope limits I have not touched it.

**Why, and this is the part worth recording rather than the mismatch itself.** It is not a
wiring oversight, and it is not one line. **The console is a separate process that reads
SQLite; it never sees `state` at all.** B publishes the tally into `state["scout"]`, which
lives in the daemon's memory for the duration of a tick. For the console to render it,
something has to persist it — and the engine that writes engine output to the store is
engine 19 `memory`, which is Phase 4. `feed_summary` deliberately shows `None` rather than a
zero for exactly this reason, and its docstring says so: a zero in that column would read as
"no pair qualified", which is a *result*, when the truth is that nobody counted. That
judgement is right and should survive whoever wires this up.

**One thing in that docstring is wrong and it is mine.** It says "the universe filter is
engine 4 and its counts are Phase 2". The universe filter is engine **7** `scout` and it is
Phase **3** — engine 4 is `data_guard`. I wrote that in Phase 1 when the numbering was less
settled in my head. It is a comment rather than behaviour, and correcting it is a change to
`console/reader.py` inside a spec whose scope limits say "do not rebuild, restyle or extend
the empty state; report a mismatch, do not fix it inside this spec". I am reporting it here
and to the lead rather than reaching for it, because the honest version of that fix is the
same change that wires the tally up, and it wants to be one task in Phase 4 rather than a
stale comment corrected now and a rewrite later.

### A spec 45 test asserted a fact about the calendar rather than a property of the criterion

**Agent:** C · **Task:** spec 45, follow-up during spec 46 · **Date:** 2026-09-10

**What happened.** B landed `tests/engines/test_scout.py` for spec 43, and
`test_both_tests_passes_against_the_real_tree_for_the_three_built_gates` went red:

```
assert <Result.PASS: 'PASS'> is <Result.PENDING: 'PENDING'>
  Outcome(PASS, 'every Phase 3 gate has a test asserting it blocks and one asserting
  it passes (block/pass per engine: cost 10/3, risk 17/4, safety 6/4, scout 2/1)')
```

The criterion did exactly the right thing — engine 7's tests arrived carrying both
directions, so it came off PENDING and passed, with no change to `verify.py`. My test was
what broke.

**Why.** It asserted `assert_pending(...)` and `"test_scout.py" in outcome.message`, because
when I wrote it that was the state of the tree. That is a fact about what had been built by
lunchtime, not a property of the criterion, and it had a guaranteed expiry date — the whole
point of registering the criterion was that somebody would land that file. It is the same
defect as a fixture pinned to a literal threshold, which this phase has already produced
twice: correct on the day it is written, wrong the moment the thing it describes moves, and
red for a reason that has nothing to do with a defect.

**Fix.** Rewritten as `test_both_tests_never_fails_against_the_real_tree`, which asserts the
durable property instead: against the real repository the criterion must **never FAIL**, and
if it is PENDING the message must name a `tests/engines/test_*.py` path so the operator is
not left guessing what the gate waits for. A FAIL there would mean a gate has a test file
carrying only one direction, which is a real defect in somebody's tests; that is the thing
worth asserting and it holds whatever B has landed so far.

**Worth carrying.** The PENDING half of every two-sided proof is vulnerable to this in a way
the PASS and FAIL halves are not, because PENDING is by definition the state a subject is
*passing through*. The other six PENDING tests in that file are safe because they build their
own tree with the subject deliberately absent — `unbuilt_tree` and friends — rather than
relying on the real repository still lacking it. This was the one that asserted PENDING
against `repo_root`, and it is the one that expired.

### `universe_varies_with_balance` was under-supplying `state`, and the first missing input hid the rest

**Agent:** C · **Task:** spec 45, follow-up when engine 7 landed · **Date:** 2026-09-10

**What happened.** B landed `engines/scout/`, the criterion came off PENDING and started
judging for real, and it reported

```
FAIL universe_varies_with_balance  engine 7 published no 'pairs' at the $10.00 balance;
                                   the universe is what every later gate iterates over
```

which is a true sentence and an unhelpful one. Driving B's engine directly:

```
status: BLOCK  reason: Scout could not read the pairs it needs: missing market_sensor is absent
data: {"reason_code": "scout_inputs_unavailable"}
```

The engine was right. My criterion built a `state` carrying only `state["exchange"]`, and
engine 7 reads the live book per pair as well — it needs a bid and an ask to value a
position, the same way engines 10 and 11 do. It also reaches the store for an equity
snapshot. I had supplied none of that, so the gate fail-closed exactly as invariant 3 says
it should, and my criterion accused it of publishing no universe.

**Why it matters beyond the missing key.** Two things, and the second is the one worth
keeping.

The first is that this is the wrong verdict, not merely a wrong message. An engine that
cannot reach its inputs is unfinished wiring or an under-supplied caller; it is not a filter
that ignores the balance, which is what `universe_varies_with_balance` exists to catch. I had
already built the guard for this on `cost` and `risk` — both report **PENDING naming their
spec** when they answer `*_inputs_unavailable` against a real payload — and wrote a decision
entry about why. `scout` did not get the guard because `scout` did not exist when I wrote it,
so the one criterion registered furthest ahead of its subject was the one missing the
protection that being ahead of your subject requires.

The second is A's finding, relayed by the lead the same day, arriving from a different
direction: **a fail-closed path with several possible causes tells you only that one of them
fired.** A's `test_a_private_call_without_credentials_blocks_rather_than_defaulting` built a
client missing two things, the first raised before the check the test was named for, and both
raise the same type — green for a phase, asserting nothing. Here the same shape appears in a
criterion rather than a test: `scout` raises `MissingInputError` for an absent
`market_sensor`, an absent `exchange`, an unreachable store, a missing equity snapshot, a
null config key and a currency mismatch, and every one of them renders as the single code
`scout_inputs_unavailable`. Fixing only the market-sensor half would have moved the failure
to the next missing input and told me nothing I had not already guessed.

**Fix.** Two changes, and the second is the general one:

1. The criterion now supplies the full opportunity-chain `state` engine 7 actually reads —
   engine 1's real payload, plus quotes built through engine 3's real `QuoteView` for every
   pair engine 1 publishes — and hands it a real `StoreClient` over the config-scaled seed so
   the equity snapshot is there.
2. It reports **PENDING naming spec 43** when engine 7 answers `REASON_INPUTS_UNAVAILABLE`,
   **quoting the engine's own sentence verbatim**. That sentence is what distinguishes
   "missing market_sensor" from "no equity_snapshots row yet", and without it the PENDING
   would be the same undiagnosable category the code itself is. Same shape as `cost` and
   `risk`, and the reason it is worth the line is precisely that one code covers six causes.

**Consequence, and it generalises past this criterion.** When a gate has one fail-closed code
for many causes, a caller that reports only the code has thrown away the diagnosis. Every
PENDING and FAIL message in this section now carries the producing engine's own reason string
rather than restating the category — which is also the argument for never piping this gate's
output through `tail`, made concrete.

### Changing a Phase 1 criterion from Phase 3: the websocket budget was measuring the machine

**Agent:** C · **Task:** lead's ruling, following the entry above · **Date:** 2026-09-10

**Crossing a phase boundary, so the justification first.** `console_websocket_pushes_on_change`
is a Phase 1 criterion and this is a Phase 3 change to it, made on the lead's explicit
ruling after I escalated rather than touched it inside spec 45. The escalation was the right
call and the fix is not the one I would have made unprompted: I had proposed counting polls
instead of milliseconds, and the lead's answer is better — **separate the three jobs that
were being done by one number.**

**What was wrong.** `budget_ms = poll_ms * 2` was simultaneously the safety net stopping a
broken console hanging the gate, and the assertion that the push was prompt. The second is
load-sensitive: it is a factor of two of headroom, measured on a machine also running the
rest of the suite. It went red once during a full run and passed three times in isolation
(1.65s, 2.19s, 8.07s for the same eight parametrised cases, which is a fivefold spread on an
idle machine). Spec 45 added 45 tests, nineteen copying a tree, and made the suite more
I/O-bound; the sensitivity pre-existed and I made it likelier to fire.

**And the promptness assertion was never the interesting property.** A console that polls on
an interval is at most one interval late by construction, so the tight bound was standing in
for "the poll loop is actually running" — which can be demonstrated from a generous bound,
and now is.

**Fix — three jobs, three mechanisms.**

- **Safety net:** twenty poll intervals, still from config. Its only job is that a dead
  poller fails in finite time. It carries no promptness claim, and the FAIL message says so
  in as many words: "a dead poller rather than a slow one".
- **Assertion:** behavioural. The socket stays silent through a **quiet window** of two poll
  intervals in which nothing changed and the client sent nothing, and *then* pushes once the
  watermark moves. That pair is what `ui-context.md` actually specifies.
- **Evidence:** the measured elapsed time stays in the PASS message — "silent through 1000ms
  with nothing changed, then pushed 508ms after the watermark moved". A promptness regression
  stays visible in gate output without being a spurious FAIL.

**The quiet window's load behaviour is the opposite of the old budget's, and that is the
point.** Waiting longer only makes it stricter. A loaded machine cannot turn it into a false
accusation; the worst it can do is fail to notice a console that pushes on a timer, which is
a missed detection rather than a wrong verdict. The fabricated console in `tests/verify/`
catches that case deterministically on an idle machine.

**Mutated both ways, per the ruling.** `if current != seen:` to `if False:` — nothing is ever
pushed, FAIL, which the old form also caught. And `if current != seen:` to `if True:` —
pushes on every poll regardless, **which the old form could not catch**: "a push arrived
within the budget" is true of a console that pushes constantly, and that console is wrong in
a way the operator would feel, as a screen that refreshes forever and never means anything.
That second mutation is why this change is strictly stronger than what it replaced rather
than a loosening.

**Consequence.** A wall-clock number in an assertion is worth asking two questions of: what
property is it standing in for, and does a slower machine make it *stricter* or *wronger*?
The old budget answered "the poll loop runs" and "wronger". Both halves were fixable and
neither needed the number widened.

*(Follow-up to the entry above, recorded because the standing instruction is to say so
rather than smooth it over.)* On the first combined run after the change,
`test_a_socket_that_accepts_and_never_pushes_is_a_failure` failed once across
`tests/verify/ tests/console/ tests/harness/` — 1 failed, 514 passed. It has not reproduced
since: the same test passes in isolation (11.59s, which is the expected quiet window plus
the full safety net), the same combined selection passed on the next run at 515 passed, and
`test_phase1_criteria.py` has since run three times at 41 passed. I did not capture the
assertion message before it stopped happening, which was a mistake — the failing verdict
would have said whether it went PENDING on a handshake that never answered, or FAIL for a
different reason, and those want different responses.

Two candidates and I am not able to choose between them on one observation: this machine's
known intermittent fault, or a handshake exceeding `WS_ACCEPT_TIMEOUT_S` under contention.
What I can say is that this test is now the longest in the suite at ~11s, because it is the
one where the console is *designed* never to push and therefore pays the whole safety net —
and a longer test is a wider window for a transient to land in. That cost is bounded to one
test and is the deliberate price of a generous timeout, so I have not touched the number.
If it recurs, the message is the thing to capture.

### The spec 46 enumeration earned itself inside a day

**Agent:** C · **Task:** spec 46, follow-up · **Date:** 2026-09-10

**What happened.** Six consecutive runs of `tests/verify/ tests/harness/ tests/console/`
came back `2 failed, 519 passed` — deterministic, not the load flake I was chasing:

```
AssertionError: engine 7 declares exclusion reason(s) with no operator prose:
['no_fx_rate']. Each renders as 'No reason was recorded.' on the console, silently.
```

B had added `REASON_NO_FX_RATE = "no_fx_rate"` to `scout/contracts.py` on an operator
ruling made the same day, and the enumeration went red within minutes of it landing.

**Why it is worth an entry.** This is the seam working, and it is the case the spec argued
about in the abstract: *"a hand-written list drifts the first time B adds a code, and it
drifts silently, which is the failure mode this seam is known for."* B added a code, in good
faith, for a good reason, and told nobody — because there was nothing to tell; the code is
correct and its docstring is thorough. A hand-listed test would have stayed green and the
console would have rendered "No reason was recorded." for a real exclusion, with no error
anywhere. The gap between the code landing and the test going red was one test run.

It also lands on the right side of a distinction I had not thought about when writing it:
`no_fx_rate` **is** in `EXCLUSION_REASONS`, so even the narrower tuple-based enumeration
would have caught this one. The `vars(module)` scan earns its keep on the codes B keeps *out*
of the tuple, of which `scout_inputs_unavailable` is the only one so far.

**Fix, and the part of it I am least comfortable with.** I added the prose immediately rather
than waiting for B, because the alternative was leaving the tree red for everyone over a
one-line mapping. **The wording is mine, not the producer's**, which breaks the arrangement
every other entry follows — B has been asked to replace it if it is wrong. The sentence is
"No exchange rate to value this pair's quote currency", and it is deliberately not a variant
of `no_quote_balance` beside it: that one is "you hold none of it", a fact about the account,
while this one is "we cannot tell what it is worth", a fact about a mechanism nobody has
built. An operator handed the same sentence for both would go looking at their balances for a
fault that is not there.

**And a new invariant, which that pair is what suggested it.** `test_no_two_codes_share_a_sentence`
asserts no two codes render identically. The lead's spec 43 ruling is the specific case —
`crypto_quoted` and `quote_not_provably_stable` exist separately so a universe that shrank by
policy is distinguishable from one that shrank for want of a config key — but the property is
general, and two codes sharing a sentence is exactly how such a ruling gets undone in the view
layer, where nothing else is looking. There were no duplicates when I added it; the point is
that there cannot silently become one.

*(Follow-up, and it changes the reading of the two entries above.)* A second test showed the
same behaviour: `test_persisted_mode_is_pending_when_core_never_calls_the_writer` failed once
in a full-suite run, then passed twice in isolation and again across its whole directory
(248 passed). **That is a Phase 2 criterion test I have not touched**, driving a fabricated
console the same way the websocket one does.

Two different tests, in two different phases' criteria, one of them nothing to do with my
change, showing the same shape: green in isolation, green in their own directory,
occasionally red in a full run. That points away from the websocket quiet window as the
cause and towards something environmental about running ~1300 tests on this machine — which
is the same suspicion the intermittent native fault already carries. It does not exonerate
the old two-interval budget, which was separately and provably load-sensitive; it does mean I
should stop attributing every full-run flake to that change.

What the criteria have in common is that both drive an ASGI console through
`asyncio.run` in-process, with wall-clock waits, inside a suite that spawns hundreds of
event loops. I have not root-caused it and I am not going to guess further on three
observations. Recorded so the next person sees two data points rather than one, and so that
"C changed the websocket criterion and now things are flaky" is not the story that gets told.

### A's three cannot-fail findings in the shared harness, and one fix that was wrong twice

**Agent:** C · **Task:** A's sweep, files are C's · **Date:** 2026-09-10

A swept `tests/conftest.py` and `tests/harness/` for tests that cannot fail and found three,
all mine. A's framing is the right one and worth keeping: **each is a fallback that fires
silently when an import fails**, each was correct when written because the thing it fell back
from did not exist yet, and none has an assertion that the *real* branch is the live one — so
none notices when its own reason for existing has expired. The failure mode is not a red
test; it is a green suite that has quietly stopped testing.

**1. The fake Kraken client's error types.** `fake_kraken.py` imports `KrakenError` and its
two subclasses from `acsoe.clients.kraken` and defines its own on `ImportError`. The test
whose entire purpose is proving the fake raises *the real client's* type imports `KrakenError`
**from the harness** — so against the fallback both sides move together and it passes while
asserting nothing. A demonstrated it by blocking `acsoe.clients.kraken` at the import system:
the test still passes, against classes that are not the real error type.

Fixed with an identity check —
`test_the_harness_is_using_the_real_error_types_not_its_own_fallbacks` asserts all three
`is` the real ones. **The fallback stays**, because it is still reachable: `tests/verify/`
drives criteria against fabricated trees carrying `tests/` and no `src/`, and the harness
imports there with no real client to find. What was missing was anything noticing which
branch is live. The older test now carries a line saying it depends on the new one and is not
a tautology, because it reads like one.

**2. `migrated_store` returning `None`, and I got the fix wrong twice before getting it
right.** This is the part worth recording.

`migrated_store` caught `ModuleNotFoundError` and returned `None`, which `build_verify_doubles`
hands to `scripts/verify.py` — so a criterion could tick an orchestrator against a client
bundle with no store and still report PASS. A's comparison is exact: it is the shape that
made `Orchestrator._record_run` unexecutable for a whole phase.

**First attempt: require a store in `_harness_doubles`.** Eighteen tests went from green to
PENDING. Several criteria are *supposed* to run on trees with no store —
`data_guard_blocks_bad_data` judges an engine that never touches one, against a fabricated
tree with no `src/` at all. I had turned "this criterion cannot check everything" into "this
criterion refuses to check anything", which is the same defect pointed the other way.

**Second attempt: make it opt-in, `require_store=True`, on the two criteria that reach the
store.** Five tests still failed, for the same reason one level down: those two criteria are
*also* designed to run against fabricated trees, and a fabricated tree legitimately has no
store.

**What was actually wrong** was none of that. It is the same defect as finding 3, in a
different file: `except ModuleNotFoundError` catches the module's own absence *and* a missing
dependency raised from inside it. "Not written yet" and "written and will not import" are
different facts with different right answers, and the handler could not tell them apart. The
fix is four lines in `migrated_store` — narrow the `except` to a `ModuleNotFoundError` naming
the store client itself, re-raise anything else. Absent still returns `None`; broken now
raises. No criterion changed, no test moved.

**The lesson is about where I reached first.** Twice I went for the consumer — make the
criterion demand more — when the defect was in the producer's inability to distinguish two
cases. Both attempts made the gate *stricter* and both were wrong, and "stricter" is a
seductive direction when the finding is "this could pass when it should not". The question
that would have got me there first is the one A's finding already contained: *what are the two
situations this handler is conflating, and does the caller have any way to tell them apart?*

**3. `pytest.importorskip` and 370 tests.** A found that an `ImportError` from inside a module
is re-raised by pytest 9.1.1 — so a genuinely broken module fails loudly, which A expected to
be wrong about and was glad to be. But a **`ModuleNotFoundError`** from inside is skipped, and
that is what an absent dependency produces. About 370 test functions, a third of the suite,
reach a fixture guarded that way. All of them would vanish, the run would report green, and
the skip reason would read "the store client does not exist yet" — false, and pointing the
reader away from the cause.

Fixed with `require_module` in `tests/conftest.py`, which skips only when the named module
*itself* is what is missing and re-raises otherwise — the same discrimination
`scripts/verify.py`'s `try_import` has drawn since Phase 0. The tests should not be looser
than the gate that judges them. All five `importorskip` calls now use it, and
`pytest_sessionstart` aborts the run once, up front, if one of those modules is on disk and
unimportable — because the same fault otherwise surfaces as several hundred separate fixture
errors, which is loud but unreadable and blames the fixture rather than the thing that broke.

`tests/harness/test_require_module.py` proves the discrimination both ways against a real
temporary package whose import genuinely fails, including the negative half —
`pytest.importorskip` **is** shown swallowing the same module, so if pytest ever changes
behaviour the replacement stops being justified from a red test rather than from somebody's
memory. It also covers the prefix case (`acsoe.a.b.c` when the package is missing raises with
`name` set to the *package*), which a naive `exc.name == name` check gets wrong and which
would have turned every genuinely-unwritten module into a hard error — breaking the whole
working method of registering criteria ahead of their subjects.

**What A found that was not a finding, and is worth recording as such.** A went looking for a
hole in the network guard and did not find one: real sockets, real httpx, `NetworkAccessError.layer`
asserted so a half-guard is distinguishable from a whole one, plus the restore, loopback and
`socketpair` scoping tests. A green report from someone actively trying to break it is worth
more than the absence of complaints.

*(Second occurrence, and this one is the case the wider net was built for.)* B landed
`REASON_EMPTY_UNIVERSE = "empty_universe"` for spec 44 and the enumeration went red again.
Unlike `no_fx_rate`, this code is **deliberately not in `EXCLUSION_REASONS`** — like
`scout_inputs_unavailable` it is a statement about the tick rather than about a pair, and
every pair that produced it is already counted under its own exclusion code, so counting it
in the tally would double-count the whole universe. **A tuple-based enumeration would not
have seen it.** Two codes now sit outside that tuple and both need prose; the `vars(module)`
scan is what finds them.

The prose needed more care than the others because **this one is a `PASS`, not a refusal.**
B's docstring is emphatic about it: nothing qualifying is this system's honest default state
on a small account, and recording it as a block would fill `block_records` with a normal
Tuesday and corrupt engine 17's error rate, which counts those rows. `ui-context.md` says the
same thing from the other side — a console that looks empty most of the time is telling the
truth rather than failing. So the sentence is "No pair was tradable on this bar": what the
system did, past tense, no apology, and nothing suggesting a fault. A sentence borrowed from
the refusal codes around it would have made the system's normal state read as a problem on
the screen that is most often on display.

### The intermittent fault was mine: `sweep_stale_workspaces` deletes other runs' live databases

**Agent:** C · **Task:** the lead's root-cause finding · **Date:** 2026-09-10

**What happened.** B hypothesised and the lead reproduced on the first attempt: create one
workspace with a seeded database, close the connection, call `sweep_stale_workspaces` — and
it deletes that workspace *and two others that were live at that moment*.

```
seeded, db exists: True
sweep removed: 3 dir(s)
db still exists: False | workspace still exists: False
sqlite3.OperationalError: unable to open database file
```

**Why, and the docstring is the defect rather than a description of it.** It says:

> Best effort throughout: a directory another verify run is using right now simply will not
> delete, and that is fine - it is swept by whichever run goes last.

That is a POSIX assumption stated as a fact about Windows, and it is wrong twice over. An
*open* file cannot be unlinked on Windows — but **a SQLite database between connections is
not open**, and every criterion here seeds, closes, and reopens, so it is unlocked for that
entire window. And `ignore_errors=True` means the call does not stop at what it cannot
remove: it deletes everything it can and skips the rest, so **partial deletion is guaranteed
rather than possible**.

That is why there were two signatures and one bug. Directory gone before the next connection
opens → `unable to open database file`. Directory survives with the database deleted inside
it → `sqlite3.connect` helpfully **creates a fresh empty one** and the next statement says
`no such table: equity_snapshots`. The criterion that "seeded a database and then found it
empty" was not confused; its database had been deleted between the write and the read.

The concurrency required is our normal working state. `tests/verify/test_runner.py` calls
`main()` nine times, so one ordinary `pytest tests/` sweeps the shared temp directory nine
times, and three agents each running the full suite is three of those at once.

**I wrote that docstring, and it is the sentence that stopped anyone looking.** Worse, there
*is* a recursion guard immediately above it for the nested `toolchain_green` subprocess — so
a related concurrency case was genuinely considered, which made the unconsidered one look
handled. A comment asserting a property nobody checked is the same shape as the fallbacks A
found this morning, one door along: the assertion was in prose instead of in code, so nothing
could notice it going false. It was never true.

**Fix.** Next entry.

### Correction: three entries above attribute to a native fault what was my own sweeper

**Agent:** C · **Task:** the same · **Date:** 2026-09-10

Per rule 6, correcting with a new entry rather than editing the old ones.

Three entries above blame this machine's intermittent native fault, and at least the first is
certainly wrong: **the zero-byte `phase0.txt`** that opened this session's work. I recorded
that as "exit 139, the bash rendering of the 0xC0000005 access violation this machine is
known for", and used it to justify the streaming-output fix. The streaming fix stands on its
own merits — a run that dies mid-way should leave the verdicts it reached — but the reason it
died was almost certainly a concurrent sweep pulling the seeded database out from under
`seed_fixtures_present`, not the hardware.

The other two are the websocket test and `test_persisted_mode_is_pending_when_core_never_calls_the_writer`.
The lead has since made a standing rule that a failure is attributed to the sweeper **only if
it carries a database error**, and B pushed for it specifically to stop a newly-named
mechanism absorbing everything the way the native fault did. By that rule the Phase 2 one is
the sweeper — B captured `OperationalError: unable to open database file` on a sibling of it —
and the websocket one is **not**, because it is a wall-clock assertion and no amount of
deleted temp directories makes a measured duration wrong. That one still has no mechanism.
The native fault is also still real: a full run today died with `Windows fatal exception:
access violation`. Three mechanisms, not one.

**What is worth keeping from this, and it is uncomfortable.** `PHASE-3-TASKS.md` has told
every agent for two phases that on a FAIL you re-run the named test in isolation and, if it
passes, write it up as the intermittent fault. That advice *works* — the test does pass in
isolation, because in isolation nothing else is sweeping. **So the mitigation confirmed the
wrong diagnosis every single time it was applied**, and it did so with the authority of the
phase rules behind it. Four spurious FAILs while Phase 2 closed, one of them landing on the
test asserting no credential was committed. A real, deterministic, fixable defect sat behind
a folk explanation load-bearing enough to be written into the process.

I did not merely inherit that explanation, I extended it: I wrote a fresh entry this morning
attributing a zero-byte file to the hardware, having reached for the rule rather than the
evidence. The rule told me what the answer was before I had looked, and the check it
prescribed could not distinguish the two causes. A diagnostic procedure that cannot fail is
the same defect as a test that cannot fail, and this project has spent a whole phase on the
second while running on the first.

*(Fix, completing the entry two above.)* `sweep_stale_workspaces` now removes only
directories whose **newest mtime anywhere inside them** predates this process's start by more
than a minute. Four changes, and the middle two are the ones I would have missed:

**The cutoff is this process's start time, not a fixed age.** `PROCESS_STARTED_AT` is captured
at import. A run that has not finished has, by definition, written to its workspace since this
process started — so its directory cannot be older than this process and cannot be selected.
The ordering is the entire argument, which is why no lock file or inter-process protocol is
needed. "Anything older than an hour" would have been a guess about how long a run takes.

**The newest mtime *inside*, not the directory's own.** A directory's mtime changes when an
entry is added or removed from it, not when a file inside it is written — so a long-running
run's workspace carries the mtime of the moment it was created. Reading only that would have
left the bug exactly where it was for any run outlasting the margin, and `toolchain_green`
alone takes ninety seconds. `test_a_workspace_being_written_to_now_survives_even_if_it_was_created_long_ago`
is that case, and it fails against the naive version.

**A minute of margin, and the direction it errs in is the whole justification.** Filesystem
and system clocks do not agree to better than a second or two on Windows and are coarser on
FAT-derived filesystems. The two errors are not symmetric: keeping a leftover one run too long
costs some disk; deleting a live database costs a wrong verdict on a gate that decides whether
real money trades. The asymmetry picks the number.

**The suppression moved inside the loop.** `contextlib.suppress(OSError)` wrapped the whole
`for`, so a single entry that would not stat aborted the sweep and every workspace after it
alphabetically was kept forever — the 450MB-per-run leak this function exists to prevent,
reintroduced by its own error handling. Found by writing the unreadable-entry test, not by
reading the code. It has its own test now.

`ignore_errors=True` is kept and now means what the old docstring wrongly claimed: everything
reaching `rmtree` has already been established as nobody's, so a failure to remove one is a
genuine best-effort miss and the next run gets it. What it is no longer doing is deciding
*whether* a directory is safe to delete by trying and seeing what happens. **The false
docstring is gone**, replaced by the reasoning above — it was the sentence that stopped anyone
looking, and leaving it while fixing the code would have left the more durable half of the
defect in place.

**Ten tests in `tests/verify/test_workspace_sweep.py`, where there were none — which is the
other half of why this survived two phases.** Both directions are asserted, because each alone
is satisfiable by a broken sweeper: "delete everything" passes the stale-leftover test and
"delete nothing" passes the live-workspace test, so
`test_the_live_one_survives_while_the_stale_one_beside_it_goes` runs both in one sweep.
Mutated as the lead asked: removing the mtime guard turns **four** of the ten red, including
the headline one. Every test runs against a fabricated temp root — a regression test for this
bug that swept the real temp directory would be the bug, committed by its own test.

### The strongest instance yet of a test that cannot fail, and it is B's

**Agent:** C · **Task:** recorded at the lead's request · **Date:** 2026-09-10

Not my work, and it belongs here because it is the same argument as this file's
induced-failure entry approached from the other side, and it is a better example than any
of mine.

B mutated `rank_universe`'s `sorted(pairs)` to arrival order, expecting three ordering tests
to go red. **All three stayed green.** The engine sorts its scan set *before* ranking, so a
ranking that merely preserved arrival order still answered alphabetically — the shuffled
input never reached the function under test.

The part that makes it the best example is the docstring. That test **claimed to be "the
assertion carrying the ordering"** and described an accidentally-stable sort as precisely the
thing it would catch. It was the one case it could not detect. And no amount of *reading*
would have revealed that, because the docstring is persuasive and the test does something
real — it drives the engine, it asserts an order, the order is right.

My own entry above says the induced failures found two criteria that "looked right, passed
against the real engines, and were checking less than they claimed", and I wrote there that
neither would have been found by adding PASS cases. B's is stronger: **it would not have been
found by review either.** A test can be well-written, well-named, well-documented and still be
untestable prose. The only thing that distinguishes it from a real test is breaking the
subject and watching, which is why `code-standards.md` now requires it rather than commending
it.

Worth pairing with the correction two entries up, because they are the same failure at
different scales: a diagnostic procedure that cannot fail told four agents for two phases
that a deterministic bug was a hardware fault, and a test that cannot fail told B its ordering
was pinned. In both cases the check ran, produced an answer, and the answer was
unfalsifiable — and in both cases the prose around it was what made it convincing.
