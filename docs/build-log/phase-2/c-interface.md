# Build log — Phase 2 — c-interface

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem
and its fix, and every decision where two approaches were viable. Not at the end of
the session — three IDE crashes in Phase 1 each took the code and the log at different
moments, and only the entries already written survived.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-2.md` at phase close.

## Entries

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
