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
