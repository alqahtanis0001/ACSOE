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
