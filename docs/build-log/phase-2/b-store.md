# Build log — Phase 2 — b-store

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem
and its fix, and every decision where two approaches were viable. Not at the end of
the session — three IDE crashes in Phase 1 each took the code and the log at different
moments, and only the entries already written survived.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-2.md` at phase close.

## Entries

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
