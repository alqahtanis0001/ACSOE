# Progress Tracker

**Lead-only file.** Teammates write `context/progress/<agent>.md`. The lead merges here after a passing verify run.

## Current Phase

**Phase 5 — Models. OPENED 2026-09-12.** Phase 4 preflight re-run on the clean tree at `ef8f1f0`: **10 criteria, 10 PASS, 0 FAIL, 0 PENDING**, `replay_full_archive` skipped as `--live`. Nineteen specs (59 to 77) written from the Phase 5 row and the ownership map, approved by the operator with all nine rulings confirmed (recorded under Locked Decisions) and one addition: the effective sample size is reported per fold beside that fold's row count, not only in aggregate. The shared task list is `feature-specs/PHASE-5-TASKS.md`. Three operator values stay absent until the walk-forward reports; see Open Questions. **This is the phase where a mistake looks like success**, so every assertion is proven capable of failing and the proof goes in the build log.

*Phase 4 — Memory and replay.* Green on its gate 2026-09-11; the operator withheld the close and the consolidation, so `docs/build-log/phase-4.md` does not exist and the four per-agent logs under `docs/build-log/phase-4/` are the record. The three operator rulings of 2026-09-12 (past-only walk-forward, 2017 cutoff, thin-pair floor as a named knob) were applied against the full 234-pair archive; the dataset is 20,331,237 labelled decision bars, 23.89% target, 51.27% stop, 24.84% timeout, 0.376% decided by the both-barriers rule.

*Phase 3 — Economics. GREEN AND CLOSED*, verified **2026-09-10**: 9 criteria, **9 PASS, 0 FAIL, 0 PENDING**. All eleven specs (37 to 47) delivered across A, B, C and the lead. All four gates re-run at close on a quiet tree, every one exit 0 — Phase 0 7/7, Phase 1 10/10, Phase 2 9/9, Phase 3 9/9 — with `pytest` 1340 passed, `mypy --strict src/` clean across 71 files and `ruff check src/` clean. Engines 7 `scout`, 10 `cost`, 11 `risk` and 17 `safety` are built, wired to A's real Kraken client, and registered in `bootstrap.py`: `is_gate_matches_registry` reports **8 engines registered; 0 mismatches (5 gates)**. The narrative account is `docs/build-log/phase-3.md`.

The phase's opening problem was the audit: engines 10, 11 and 17 were **built, not done** — all three read a `state["exchange"]` payload engine 1 does not publish, and one read a price *nothing* publishes. They were green against a payload nothing writes, because every test built that payload by hand in the shape the engine expected. The operator ruled the fixtures be rewritten from engine 1's real output rather than repointed. **Phase 4 is next.**

**Phase 4 — Memory and replay is next.** It opens carrying the deferred items under Open Questions below, including the console tally that needs engine 19 and the remaining mutation survivors A did not reach.

*Phase 2 — Data spine. Green and closed*, verified **2026-09-10**: 9 criteria, **9 PASS, 0 FAIL, 0 PENDING**. Nine specs (25 to 33) across A, B, C and the lead, plus three Phase 3 engines (34 to 36) built concurrently by B and deliberately excluded from this gate. The lead re-verified independently at close and re-ran all three phase gates: Phase 0 7/7, Phase 1 10/10, Phase 2 9/9. The two criteria PENDING at the last checkpoint are both resolved — `data_guard_blocks_bad_data` once the operator supplied `data_guard.max_data_age_s`, and `recording_span_continuous` on a clean 24-hour recording reporting **99.98% of its span actually recorded** against a newly enforced 0.98 floor. The narrative account is `docs/build-log/phase-2.md`.

*Phase 1 — Interface. Green and closed*, verified 2026-09-09: 10 criteria, 10 PASS, 0 FAIL, 0 PENDING. All nine specs (16 to 24) built by C alone; A and B had no Phase 1 work and none was invented for them. The lead re-verified independently of C's report: `pytest` 707 passed, `mypy --strict src/` clean across 35 files, `ruff check src/` clean. Survived three IDE crashes mid-phase with no lost work. **Phase 2 — Data spine is next**, and it opens carrying two obligations recorded under Open Questions, one of them a live defect in `core/`.

*Phase 0 — Structure. Green and closed*, verified 2026-09-08: 7 criteria, 7 PASS, 0 FAIL, 0 PENDING. All 16 feature specs built, all three teammates and the lead reporting nothing outstanding.

## Current Goal

**Phase 3 — economics.** Engines 7, 10, 11 and 17, zero ML. Three engines wired to A's real Kraken client rather than to a mock, plus engine 7 `scout`, which needs a real tradable universe and was deliberately excluded from the overlap for that reason. `CONDITION_ACTION` is ratified — see Decision history — and the daemon stops running with three empty client slots.

**The audit that opened the phase is the reason it is not a small phase.** Engines 10 and 11 read `state["exchange"]["fees"]` and `state["exchange"]["pairs"]`; engine 1 publishes `fee_tier` and `pair_rules`. Engine 11 reads a `last_price` that **nothing in the system publishes** — the only `last_price` in the codebase is a column on an open-position row. Both read a `fallbacks_used` key that does not exist. Every test builds `state["exchange"]` by hand, so both engines are green against a shape their publisher does not produce. This is the third appearance of that failure in this project and the operator ruled that the fixtures are rewritten, not repointed.

*Phase 2's goal, for the record:* the data spine — engines 1, 2, 3 and 4, the historical OHLCVT loader, and the recorder engine superseding `scripts/record.py`. The `core/` command reader was fixed first, before any engine work. The persisted system mode was spec 31 (B) and spec 32 (C), with the `core/` write staying lead work. All delivered.

*Phase 1's goal, for the record:* the full console against the seeded database — status band, positions, cycle feed, history, research views, WebSocket updates and the three commands. Nothing in the console reads a live exchange; it renders the Phase 0 seed, which is the whole point of building the interface before the backend. All delivered.

*Phase 0's goal, for the record:* `scripts/verify.py` first, then the package skeleton, `core/` contracts and three-chain orchestrator, `platform/` config, clock, logging and live guard, CLI entrypoints, `config/default.yaml`, SQLite schema and migrations, store client, seed generator, fake Kraken client, test harness, and `scripts/record.py`. No engines. All delivered.

## Phase Status

A phase is green only when `python scripts/verify.py --phase N` passes every criterion.

| Phase | Status | Verified |
|---|---|---|
| 0 — Structure | **Green** | 2026-09-08 — 7 PASS, 0 FAIL, 0 PENDING; re-verified 2026-09-09 at the Phase 1 gate, same result |
| 1 — Interface | **Green** | 2026-09-09 — 10 PASS, 0 FAIL, 0 PENDING (9 at close, plus `toolchain_green` once it was registered for every phase) |
| 2 — Data spine | **Green** | 2026-09-10 — 9 PASS, 0 FAIL, 0 PENDING; all three phase gates re-run clean at close |
| 3 — Economics | **Green** | 2026-09-10 — 9 PASS, 0 FAIL, 0 PENDING |
| 4 — Memory and replay | **Green on its gate; close and consolidation withheld by the operator** | 2026-09-11 — 10 PASS, 0 FAIL, 0 PENDING; re-verified 2026-09-12 at the Phase 5 preflight, same result, `replay_full_archive` skipped as `--live` |
| 5 — Models | **In progress — opened 2026-09-12** | Specs 59–77, approved by the operator with nine rulings confirmed and one addition (per-fold effective sample size). Team: A (61), B (62, 76), C (60, 63–75), Lead (59, 77) |
| 6 — Decision and execution | Blocked on 5 | — |
| 7 — Evaluation | Blocked on 6 | — |
| 8 — Live readiness | Blocked on 7 | — |

## Completed

- Phase 0 feature specs written to `feature-specs/`, 16 of them, and approved by the operator with three additions (spec 11 `is_primary` as a database constraint, spec 12 carrying the off-by-one reasoning, spec 14 requiring a negative test for the network guard).
- **Phase 0 itself. Green on 2026-09-08.** All 16 specs built, across four workers. Merged from the three progress files at phase close; the narrative account is `docs/build-log/phase-0.md`.

| Agent | Specs | Delivered |
|---|---|---|
| C — Interface | 00, 01, 02, 14, 15 | `scripts/verify.py` and its criterion framework, the seven Phase 0 criteria each proved twice (PENDING on an empty tree, PASS on a fabricated subject), `docs_vocabulary` registered for every phase with the retired-term table parsed rather than hardcoded, the test harness and `tests/fixtures/` structure, the network guard with its negative test, and the fake Kraken client. |
| A — Platform | 03, 07, 08, 09, 10 | The src-layout package and `pyproject.toml` with the `dev`/`research` split, `platform/config.py` and every refusal it owes, clock and structlog JSON logging with two-layer redaction, the three CLI entry points with a lazily-importing dispatcher, and `scripts/record.py` with a committed 25-line sample carrying a genuine `gap` marker. |
| B — Store | 11, 12, 13 | `db/migrations/` and the forward-only runner, the store client, and the seed generator producing all six Phase 3 fixtures — each overshooting its threshold rather than sitting on it. |
| Lead | 04, 05, 06 | `core/` contracts and the three-chain orchestrator, `bootstrap.py` and the engine registry, and `config/default.yaml`. |

- **Nothing is outstanding for any agent.** Every open question and escalation raised during the phase is resolved: the `Config` Protocol mismatch, `.gitattributes`, `pyyaml`'s absence from the stack table, `is_primary` scoping, the `safety` threshold key names, the `docs_vocabulary` false FAIL, and the entry-point shapes in `core/` and `cli/research.py`.
- **The operator's nine values landed mid-phase** and broke three of A's tests by making the config *more* valid. The assertions were moved onto a fabricated config rather than deleted, the shipped file gained the opposite assertions, and a new test scans the file's `Operator-chosen` marker so a tenth key that arrives *with* a value is still noticed.

- **Phase 1 itself. Green on 2026-09-09.** All nine specs (16 to 24) built by C alone. The narrative account is `docs/build-log/phase-1.md`.

| Agent | Specs | Delivered |
|---|---|---|
| C — Interface | 16–24 | The eight Phase 1 criteria in `verify.py`, each proved PENDING on an absent subject and PASS on a fabricated one; the console read layer over a read-only SQLite connection proved read-only by attempting real writes; the design tokens, self-hosted Plex faces and single-page shell with the live-mode amber frame; the status band with presence-based restart detection; the cycle feed with its counts-based empty state; history; the research views with the SHAP pane's honest empty state; the WebSocket watermark push; and the three commands behind a SQLite authorizer that denies every table but `commands`. |
| Lead | — | Specs 16–24 and the shared task list; the checkpoint review; three rulings taken to the operator; the `run_id` presence-test correction across `ui-context.md`, spec 16 and spec 19; the seam row for the Phase 2 persisted mode; and the diagnosis of the seed-path fault and the `core/` command-reader defect. No implementation — Phase 1 needed none from `core/`. |

- **Three IDE crashes mid-phase cost no work.** Each time the tree was re-assessed against the gate rather than the agent's transcript, and C was restarted from verified state. What the crashes did cost was C's two documentation files, twice — both times the code had landed and the build log had not. Recorded here because it is an argument for the "write as you work" rule rather than a mishap: the rule is what made the loss recoverable in minutes.

- **Phase 2 itself. Green on 2026-09-10.** All nine specs (25 to 33) built, across three teammates and the lead. The narrative account is `docs/build-log/phase-2.md`. Merged at close from the three progress files.

| Agent | Specs | Delivered |
|---|---|---|
| A — Platform | 25, 26, 27, 28, 29, 30 | The Kraken REST and WebSocket clients, with the envelope check and its paired positive test; engine 1 `exchange`; engine 2 `market_data_recorder` and `scripts/recording_report.py`, whose digest accounts for unrecorded silence as well as explicit `gap` markers and refuses to write a span under 24 hours; engine 3 `market_sensor`, building 15-minute candles that match a Kraken OHLC fixture within one tick size and 0.1% of volume; engine 4 `data_guard` with four distinct operator-readable block reasons; and the historical OHLCVT loader, which marks gaps and never interpolates. |
| B — Store | 31 | The persisted system mode as a column on `runs` rather than a single-row state table, migration `0002`, and the store surface the `core/` write and C's reader both sit on. Also 34, 35 and 36 — engines 10 `cost`, 11 `risk` and 17 `safety` — built concurrently under the Phase 3 overlap ruling and **deliberately not counted toward this gate**. |
| C — Interface | 32, 33 | All six Phase 2 criteria in `verify.py`, each proved twice — PENDING on an absent subject and PASS on a fabricated one — and each shown able to FAIL; and the status band reading `Running` and `Frozen` from the persisted mode, which was the Phase 1 debt this phase was required to pay. |
| Lead | — | The `core/` command reader, broken in three places rather than one; the run record at startup and the persisted-mode write; `bootstrap.py` registration of engines 1 to 4; the four config keys; the spec set; and the `recorded_fraction` floor that closed the `recording_span_continuous` defect. |

- **Nothing is outstanding for any agent.** A, B and C all report clear. Two items deliberately survive the close and are carried in Next Up rather than hidden: `cli/engine.py` still passes a `Clients()` of three `None`s, and engine 17's `CONDITION_ACTION` table is unratified.

## Phase 3 — how it closed

*Merged at close from the three progress files, 2026-09-10. Shared task list:
`feature-specs/PHASE-3-TASKS.md`.*

**All eleven specs delivered.** A: 38 TTL-bounded caching, 39 real clients and the derived
subscription scope. B: 40 `cost`, 41 `risk` and the balance fallback, 42 `safety`'s ratified
escalation table, 43 and 44 engine 7 `scout`. C: 45 the seven Phase 3 criteria, 46 the operator
prose for all nineteen reason codes. Lead: 37 the three rulings into the authority documents, 47
the registration of all four engines.

### FINDING: three mechanisms had been charged to one cause for two phases

Intermittent test failures across Phases 2 and 3 were attributed to a native memory fault on this
machine. **There were three distinct mechanisms and two of them were deterministic, fixable
defects.**

1. **`scripts/verify.py::sweep_stale_workspaces` deleted other processes' live databases.** It
   removed every `acsoe-verify-*` directory in the shared temporary directory, and its docstring
   asserted that a directory in use "simply will not delete" — a POSIX assumption written as a fact
   about Windows. `ignore_errors=True` guaranteed *partial* deletion rather than none, so one defect
   produced two symptoms: a vanished directory gives `unable to open database file`, a surviving
   directory with its database removed gives a freshly created empty database and then
   `no such table`. `tests/verify/test_runner.py` calls `main()` nine times, so one `pytest tests/`
   sweeps nine times — and three agents each running the suite is this project's normal state.
   **Fixed:** only leftovers whose newest internal mtime predates this process's start are removed.
2. **A Phase 1 wall-clock criterion was measuring connection setup rather than the push latency it
   named.** Its reported figure fell from 509ms to 6ms once measured from a steady-state connection.
   It could never have detected a promptness regression, because the quantity it reported was
   dominated by something else. **Fixed:** safety net, assertion and evidence are now three
   mechanisms instead of one number.
3. **A genuine native fault remains.** It presents as an `ACCESS_VIOLATION` or `STACK_BUFFER_OVERRUN`
   process crash, not as a test failure, and was seen again at phase close. It is now charged **only
   with what it actually causes.**

**Standing rule, so the third does not re-absorb the others:** a failure is attributed to the
sweeper only if it carries a database error. Anything else is unexplained until it is explained, and
*unexplained* is an acceptable thing to write in a build log. The rule exists because an agent
warned, within an hour of the sweeper being named, that a newly named mechanism will absorb every
flake exactly as the native fault had — and was right that it had already started.

### FINDING: a diagnostic procedure that cannot fail is the same defect as a test that cannot fail

The standing instruction in `PHASE-3-TASKS.md` was *re-run the named test in isolation, and if it
passes it was the intermittent fault.* **That instruction worked every time — because in isolation
nothing else was sweeping.** The mitigation was manufacturing the evidence for its own diagnosis,
and it confirmed the wrong answer on every occasion it was applied, over two phases and four agents.
It was not merely inherited: a fresh entry attributing a zero-byte report file to hardware was
written on the last morning of the phase, by an agent reaching for the rule rather than for the
evidence.

This project spent Phase 3 cataloguing tests that cannot fail while running on a *diagnostic* that
cannot fail. **Apply to a diagnostic the question you apply to a test: under what observation would
this have told me something else?** Now a rule in `context/code-standards.md`, alongside the three
shapes of unfailable test and the mutation practice that catches them.

### The rest of what closed


| Agent | Specs | State |
|---|---|---|
| Lead | 37, 47 | 37 **done**. 47 is the last spec in the phase and waits on 44 |
| A — Platform | 38, 39 | **Both done.** Then a commissioned audit — see below |
| B — Store and trading | 40, 41, 42, 43, 44 | 40, 41, 42, 43 **done**. 44 in progress |
| C — Interface and models | 45, 46 | **Both done.** Then the Phase 1 timing criterion and the harness findings |

**Ten of eleven specs are done.** `verify.py --phase 3` went from *"2 criteria: 2 PASS — Phase 3 is
green"* over four unbuilt or unwired engines, to **9 criteria driving four real engines**. That
false green was the reason spec 45 was ordered first, and it is gone.

**Two paired landings, both done, and the rule they produced.** `kraken.cache_ttl_s` landed first,
then `trading.stable_quote_currencies` — a key the operator had to supply because invariant 7
defines a crypto-quoted pair against a set of stable assets that existed nowhere in the repository
and is not derivable from Kraken's data. `extra="forbid"` means either half alone breaks every test
that reads the committed config, so the field lands with the YAML in one commit.

A's generalisation, now in `code-standards.md`: **the landing order is universal; the resting state
is not.** `cache_ttl_s` was tightened to required because every reader raises on absence, so startup
is the same refusal delivered earlier. `stable_quote_currencies` stays optional because its readers
were *ruled to disagree* — engine 7 fails closed and excludes, engine 2 fails open and publishes the
fact — and a required field overrules both by stopping the process, which would mean the recorder
never runs. A's second half: **a half-landed key is not uniformly safe just because the reader
raises.** `Config.get` raises, the orchestrator turns a raised engine into `ERROR`, `ERROR` blocks —
so a missing key briefly made engine 2 the tick's *primary blocker* and displaced `data_guard`,
which would have written a wrong `block_records.is_primary` for every tick in that window. A
corrupted audit row is worse than a stopped daemon, because it looks like data.


- **Spec 47 waits on spec 44**, which is B's and in progress. That ordering is deliberate: a
  half-wired gate in the live chain turns every other criterion's failure into a puzzle.
- **`scripts/verify.py::sweep_stale_workspaces` is a live defect and C is fixing it.** It deletes
  every `acsoe-verify-*` directory in the shared temp directory, including ones other processes are
  using. Its docstring claims a directory in use "simply will not delete" — a POSIX assumption that
  is false on Windows, and `ignore_errors=True` guarantees *partial* deletion rather than none.
  Reproduced by the lead first try: one sweep took a live seeded database plus two other running
  workspaces. **This is what has been reported as "the intermittent fault" for two phases.** The
  standing advice — re-run the named test in isolation, and if it passes record it as the fault —
  worked, because in isolation nothing else is sweeping, so the mitigation confirmed the wrong
  diagnosis every time it was applied.
- **Three flake mechanisms are now distinguished and must stay distinguished.** The sweeper, which
  always presents as a *database* error; a load-sensitive wall-clock assertion in a Phase 1
  criterion, which C diagnosed independently and has fixed; and the genuine native
  `access violation`, which C saw again today. B's warning, taken as a standing rule: **a newly
  named mechanism will absorb every flake in the tree the way the native memory fault did for two
  phases** — so a failure is attributed to the sweeper only if it carries a database error, and
  *unexplained* stays an acceptable thing to write in the log.

## Phase 2 — how it closed

Kept in full because the phase's difficulties are dissertation material and the summary in `docs/build-log/phase-2.md` points back at it.

### The two PENDING criteria, both now resolved

1. **`recording_span_continuous` — PASS.** The clean 24-hour single-recorder run started `2026-09-09T14:15:29Z` and completed `2026-09-10T14:15:30Z`. `scripts/recording_report.py --write` produced a digest over a **24.07-hour span, 10 segments, 9 accounted breaks, 11,924,857 lines, 20.25 seconds missing in total — `recorded_fraction` 0.9998**. Every one of the nine breaks is a websocket reconnect of between 0.9 and 3.1 seconds. The criterion now enforces a 0.98 floor on that fraction; see the entry below and in the build log.
2. **`data_guard_blocks_bad_data` — PASS.** The operator supplied `data_guard.max_data_age_s`. Stale data, a negative spread and a missing candle each block with a distinct operator-readable reason, and clean data passes. Reporting PENDING while the key was unset was the correct fail-closed reading and never a defect in the engine or the gate.

### The criterion defect, and how it was closed

**`recording_span_continuous` enforced "every break accounted for" rigorously and "a continuous span of at least 24 hours" not at all.** It measured start-to-end elapsed time, so a 24-hour span with nothing missing and a 24-hour span with eleven hours missing tiled identically, carried causes identically, and passed identically. Found by A dry-running the report before depositing rather than after.

**Closed 2026-09-10 with a `recorded_fraction` floor of 0.98**, and the criterion now prints the measured fraction beside the floor so the number the gate turns on is in the output. The floor was deliberately not set when the defect was found: the only archive available then was 49% recorded, and any floor chosen to admit it would have fixed the bar at the number we happened to have rather than at one anybody would choose. Setting it against a clean run is what made 0.98 principled rather than rationalised.

**The full archive is kept as separate evidence.** `tests/fixtures/recording_report_full_archive.json` reports **76.2% recorded across 47.24 hours** — dragged down by a ten-hour silence when no recorder was running (36,122 of the 40,471 missing seconds, 89% of the total) and by the self-inflicted disk-full outage of `2026-09-09T13:06:37Z` with the restarts either side of it. **Both causes predate the clean run**, which starts an hour after the disk incident. **The archive was not modified** — invariant 11 holds; the window is applied to the report and never to the data, and the nine gaps in the windowed report are exactly the nine the full archive reports at or after the clean-run start. Both artefacts are committed, so nobody has to take the good number on trust.

### The five operator rulings this phase

1. **Phase 3's deterministic engines overlap Phase 2.** Engines 10, 11 and 17 built by B against a mocked client and the Phase 0 seed, because they depend on the exchange only through a contract and the seed already carries every fixture `safety` needs. Engine 7 `scout` stays in Phase 3 proper — it needs real data, not a contract. They do not count toward Phase 2's gate.
2. **Spec 25's envelope check needs its paired positive test.** A parser that raised on every response would satisfy the negative half alone.
3. **Spec 30 marks gaps and never interpolates**, stated in the spec rather than implied, because a synthesised candle at a price that never traded invents a barrier touch and fabricates a Phase 4 label.
4. **Spec 32's Phase 1 deferral test is deleted and the deletion recorded** with the decision that retired it. C found the test never existed — the claim came from a docstring that was false when written.
5. **Phase 2 waits for a clean 24-hour recording** rather than closing on a 49%-recorded archive carrying a disk outage we caused ourselves. Everything else in the phase is finished and waiting.

### The pattern this phase kept producing, now eight instances

**A check whose output resembles the claim while the claim is untrue.** `mypy --strict` returning no answer at all behind a numpy stub syntax error; `ignore_errors=True` turning "do not fail the criterion" into "say nothing"; a `b'"gap"'` payload match that would have split segments silently; a fabricated `EngineContext` that agreed with the mistake it was meant to catch; `recording_span_continuous` measuring elapsed time and calling it continuity; assertions in three separate files holding `guard_blockers == []` while naming an empty registry; C's shallow-copy regression test, which passed with the defect it was written to catch deliberately reverted, because module reloading had already made the leak it tested for impossible; and — at the close — `recording_span_continuous` again, unable to tell a 76.2%-recorded archive from a 99.98%-recorded one because tiling, causes and elapsed time are all properties of the *shape* of the evidence rather than its content.

*(The seventh was recorded in C's build log and had not been merged here; the count of six carried in this file until the close was one short.)*

A's generalisation remains the useful form: **an assertion is decayed if it would still pass when the thing it names is false.** Its sibling, already in `ai-workflow-rules.md`, is *fabricate the subject a criterion judges; never fabricate a contract it is held to.* The close adds a third: **a gate satisfied by the shape of the evidence rather than by its content will accept fabricated evidence of the right shape.**

**None of the eight was caught by running the suite.** They were caught by an agent reading source before building against it, by making a green test go red on purpose, and by dry-running an artefact before depositing it. Those appear to be the only three techniques that work on this class of defect, and all three are cheap.

**Phase 3 produced far more than eight, and separated them into shapes.** Three distinct tells,
each needing a different question, all now rules in `code-standards.md`:

1. **A double too simple to exhibit the property under test** — a fake transport that counted
   nothing; a client built without a TTL, so the TTL check raised before the credential check the
   test existed to exercise; a `FakeTime.sleep` with no `await`, so the lock was never contended;
   the lead's own orchestrator built with no logger, so `_log` returned before the line under test.
2. **A claim and its evidence moving together** — B's fixtures agreeing with their caller; C's
   reason-code assertion importing the constant it checked against; B reading `pending_commands()`
   after the orchestrator had emptied it; C comparing zero error rows against zero.
3. **A double standing where the subject should be** — A's Phase 2 tripwire, which passes the "can
   it fail?" question and simply is not connected to what it claims to watch.

A fourth was found by A's commissioned sweep and is the decayed assertion from the opposite
direction: **a fallback for a thing that does not exist yet has an expiry date and nothing records
it.** `try: import real / except: define our own`, `getattr(mod, "Name", None)` then skip,
`except KeyError: continue`. Each was correct when written; each was a silent branch firing on a
condition that should be impossible. A's fix formulation is the one that matters: **never delete
the fallback — add the assertion that it is unreachable**, which turns a stale workaround into a
tripwire for the day someone breaks what it stood in for.

**Two techniques were added to the three above, and both earned their place by catching the
lead.** *Break the code and watch the test go red* became a standard after the lead wrote the rule
about doubles and then committed a regression test that passed against unfixed code, in the commit
citing that rule by name. And A's caveat, which makes mutation usable rather than noisy: **a
mutation that survives a subset has not survived — it has not been asked.** Two of A's 23 survivors
died when re-run against the wider suite. A false survivor is worse than a missed one: it sends
someone to write a test for a covered case and makes the real survivors look less urgent.

**The sharpest single result was A's**, and it inverts an assumption worth naming: **coverage counts
executions, a mutation asks whether anything would object.** A's surviving mutant sat on a branch
with *excellent* line coverage — every test in `test_market_data_recorder.py` runs engine 2 without
engine 1, so that path executed constantly and nothing asserted what it reported. A line everybody
runs is the line nobody thinks to assert on.

### Known gap, recorded not hidden

`cli/engine.py` still passes `Clients()` with three `None`s, so with the engines registered **`acsoe engine` blocks every tick** — engine 1 raises, the orchestrator converts it to `ERROR`, `data_guard` follows with its own missing-key error, and the tick completes recording both. That is contract rule 7 working, and a daemon doing nothing useful. A has pinned the current behaviour in a test so wiring the real clients turns it red and forces a deliberate rewrite. Blocked on `market_data.pairs` and `market_data.book_depth`; no Phase 2 criterion depended on it, because every Phase 2 criterion runs the orchestrator against the fake client rather than through the CLI. **Carried into Phase 3 and CLOSED there by spec 39.** `acsoe engine` now builds real clients and the subscription set is derived per tick from the pairs whose quote currency the account actually holds. Neither `market_data.pairs` nor `book_depth` was ever added: the operator's ruling retired both, and the universe is engine 7's per-tick computation. A's tripwire for this — written in Phase 2 precisely so that wiring real clients would turn it red — **did not fire**, because it built the empty `Clients()` itself instead of going through `cli/engine.py`, so it pinned a fact the test supplied rather than one about the daemon. That produced a standing rule: *a test whose purpose is "this goes red when X changes" must reach X through the code path X lives on.*

## Next Up

- **Phase 3 — economics. Unblocked and not yet planned.** It opens with two things, in this order. First, **wire B's engines 10 `cost`, 11 `risk` and 17 `safety` to A's real Kraken client**: all three were built during the Phase 2 overlap against a mock and the Phase 0 seed, they did not count toward Phase 2's gate, and *built* is not *done* — the Phase 3 criteria judge them against the real client. Second, **engine 7 `scout`**, which needs a real tradable universe and was deliberately left out of the overlap because it depends on data rather than on a contract.
- **~~Engine 17's `CONDITION_ACTION` table is still unratified~~ — RATIFIED 2026-09-10.** The drawdown and loss-streak limits **freeze**; `close_all` is reserved for the invariant 14 data-outage escalation and for the operator's own button. Written into invariant 14 by spec 37, applied to the table by spec 42. B held on it for four specs and was right to.
- **The ranking score inside engine 7 `scout` is absent on purpose and is a recorded absence
  rather than a design.** Spec 44 asked for one candidate per tick and deliberately did not say
  how to choose it; ordering is alphabetical over the whole universe, which is a placeholder that
  cannot be mistaken for a judgement. No agent invented one, and B held the line on it through two
  specs. **Phase 5 closes it**, and `rank_universe` in `engines/scout/contracts.py` is the single
  named seam to edit — it exists as a separate function for that reason and for no other. Recorded
  here at B's request because spec 44 step 3 asks for it and the tracker is the lead's file.

  The blind spot found while proving it is worth carrying with it: the engine builds its scan set
  as `sorted(set(rules) | set(quotes))`, so `rank_universe` is always handed an already-ordered
  sequence, and a ranking that merely preserved arrival order still answers alphabetically end to
  end. Whoever replaces the placeholder must test `rank_universe` **directly** on input where
  arrival order and the intended order disagree on every element; an end-to-end fixture cannot see
  the difference.

- **~~`cli/engine.py` and its three `None` clients, blocked on `market_data.pairs` and `market_data.book_depth`~~ — RULED 2026-09-10, and the answer is that neither key exists.** They stay undefaulted. The subscription set is derived per tick from the pairs whose quote currency the account actually holds, in engine 2, from `state["exchange"]`; the tradable universe is engine 7's and is a different question. `acsoe engine` does **not** refuse to start without credentials — paper mode is the default and must run on a fresh clone, and the gates block on their own. Spec 39.
- **~~Phase 2 carries a debt from Phase 1~~ — PAID, 2026-09-10.** The status band gained its `Running` and `Frozen` readings in Phase 2 as required. B added the column (spec 31), the lead wrote the run record and the mode write in `core/`, and C's reader takes the mode as a fact rather than inferring it (spec 32). `console_reads_persisted_mode` PASSes against a real daemon driving a real store. Kept here struck through rather than deleted, because a debt that is quietly removed from a list is indistinguishable from one that was never recorded.
- **Before Phase 4:** replace the cycle feed's full scan of `block_records` with a most-recent-N read on B's store surface. Harmless while the table holds a seed; engine 19 `memory` starts writing a row per guard per tick in Phase 4, which is when it stops being harmless.
- **`RUF001` on `tests/console/test_format.py` is suppressed deliberately, not fixed.** `U2212 = "−"` must be the U+2212 glyph: it is the fixture for the minus-sign rule, and "correcting" it to an ASCII hyphen would make the test pass against the exact character it exists to reject. Carries a rule-named `noqa` with its reason, and the general policy now lives in `context/code-standards.md` under Python — name the rule, give the reason, and never suppress a lint to make a failing check pass.
- **The console's scan tally is DEFERRED, and spec 57 step 3 was wrong to promise it.** Ruled
  by the lead 2026-09-11. The Phase 3 handoff said the empty state's tally *needs engine 19,
  which is Phase 4*, and I wrote that into spec 57 as though engine 19 arriving were
  sufficient. It is not. Engine 7 `scout` publishes `scanned`, `entered` and a per-reason
  `excluded` tally into `state["scout"]`, where they live for exactly one tick; **no column in
  any table has room for any of the three**, and engine 19 can only write what the schema
  holds. C stopped and asked rather than inventing, which is the correct move and the reason
  this is a deferral rather than a defect.
  The three options C set out, with what each costs:
  1. `rejections.details` as JSON, one row per tick — no schema change, but it puts a
     tick-level fact in a candidate-level table, and **anyone counting refused trades counts
     it**. That is invariant 12's table meaning something different depending on who reads it.
  2. One `rejections` row per excluded pair — defensible, since engine 7 is a gate and an
     excluded pair is a refused candidate, and Phase 3 already mapped all six per-exclusion
     codes into `REASON_PROSE`, which only makes sense if they reach that table. But it
     reconstructs `scanned` and **not** `entered`, and writes tens of rows per tick.
  3. A new column or a small table — lead approval, B's edit.
  **Deferred because option 2 changes what `rejections` means**, and that is invariant 12
  territory rather than a console nicety. Deferring is reversible; a table whose rows mean two
  things is not. Revisit when there is a reason to decide about tick-level telemetry in
  general — Phase 7's attribution is the natural forcing function, since it reads the equity
  curve including cash periods and will want to know what the system was doing while flat.
  What C **did** fix, because it was in scope and simply false: the empty state said the
  universe filter was engine 4 and its counts arrived in Phase 2. It is engine 7 and it
  shipped in Phase 3, so the console was telling an operator to wait for something already
  built. The stage still shows no count and still refuses to show a zero, because a zero there
  reads as *no pair qualified*, which is a result, when the truth is that nobody counted.
- **The branch-coverage backlog lives in one place and that place is not this file.** Phase 3
  recorded it inside the handoff box at the top of `feature-specs/PHASE-3-TASKS.md` and
  nowhere else. B went looking for it in `docs/build-log/phase-3.md`, the per-agent logs and
  this tracker — the three places a careful agent searches — and correctly reported it absent.
  It is not absent; it is in a fourth location that neither canonical file mirrors, because a
  handoff box is written at phase close and is neither a merged progress file nor a
  consolidated build log. **An open item recorded only in a handoff box is an open item the
  next phase will lose**, and this is the first time one nearly was. Carried here now:
  `clients/kraken/contracts.py::_to_money` (4), `limiter.py::acquire` (the `cost <= 0` guard),
  `engines/market_data_recorder/contracts.py::validate_line` (1), `platform/config.py` (5), and
  `clients/store/migrations.py::discover_migrations`. That last count was recorded as 3 and B
  re-checked it wide in Phase 4: it is **five** refusal branches, all raising `MigrationError`,
  plus a sixth path for the non-`.sql` skip. The handoff's own warning that the counts came
  from a narrow subset and that some would die on contact was right in both directions — some
  die, and at least one was undercounted.
- **~~Deferred from Phase 0, still deferred: widening `TOOLCHAIN` beyond `src/`~~ — DONE
  2026-09-11, by operator ruling.** `TOOLCHAIN` is now `pytest tests/`, `mypy --strict src/
  scripts/`, `ruff check src/ tests/ scripts/`. It was ruled because the deferral finally cost
  something: a file committed this phase could not be imported on Python 3.11, the declared
  floor, and a second defect in `scripts/build_archive.py` that presented as a typing
  complaint turned out to be a crash. Both sat in files the gate could not see.

  **Two things this entry said were wrong, and the staleness is the lesson.** It recorded
  `mypy --strict scripts/` as 2 errors — it was 7 — and `ruff check tests/` as 3 violations,
  when it is **clean**: the `RUF001` `noqa` had already landed with its reason. So a
  deferred-decision note had been quietly overstating the cost of the decision for four
  phases, which is part of why it kept being deferred. **A stale obstacle in a deferred item
  is its own hazard**: nobody re-measures a cost they have already accepted, and the note
  outlives the thing it describes. Re-measure before re-deferring.

  One measurement note worth keeping, from C: `mypy --strict scripts/` alone reports the
  `build_archive` error and `mypy --strict src/ scripts/` does not, because the argument list
  changes how the `acsoe` imports resolve. **An error count is only true for the exact command
  that produced it.**

  `mypy --strict` is deliberately **not** widened to `tests/` — roughly 1,680 test functions
  would each need a return annotation. The hole is stated rather than implied and a test
  asserts the exclusion, so the next person to "fix" it meets a red and a decision.
- **A's standing instruction, and it does not expire with the phase:** `scripts/record.py` should be left running from now on. Order-book and spread history cannot be recovered retroactively — Kraken's free archives carry OHLCV and no bid, ask, spread or depth — so every hour the recorder is not running is an hour of cost-model input that money cannot buy back later. Phase 2's criterion is satisfied, which is exactly when the temptation to switch it off appears; engine 9 `order_book` and the spread half of engine 10 `cost` still have nothing else to read. **Note the recorder has no working graceful shutdown on Windows** — `loop.add_signal_handler` raises on the Proactor loop and the exception is suppressed, so the `stop` marker never runs and a kill has to be forced. The archive is append-only and every line is flushed, so a kill costs at most a partial final line.

## Locked Decisions

Settled with evidence. Do not relitigate. Changing one requires the operator, not an agent.

- Kraken Pro, spot only. No margin, futures, leverage, or shorting.
- Fees read live from `TradeVolume`. Minimums read live from `AssetPairs`. Never hardcoded.
- Reference friction: ~1.25% round trip at tier 1, ~0.65% at tier 3.
- Break-even win rate: ~61% at tier 1, ~48% at tier 3.
- Decision bar 15 minutes; hold 2–12 hours; loop tick 1 minute.
- Triple-barrier labels: +3% / −1.5% / 48-bar timeout.
- Post-only limit entry, cancel if unfilled, never chase.
- Tradable universe computed per tick from `ordermin`, `costmin`, tick size, live spread and balance. No account-size thresholds.
- All Kraken quote currencies scanned; crypto-quoted pairs disabled by default.
- DI fitted on the predictor's training set, MinMax-scaled, rolling percentile threshold, 30-day per-pair window.
- DI threshold crossings also feed the regime engine.
- Alpha attribution uses the full equity curve including cash periods, not trade windows.
- Execution offset bandit pooled by spread tier, not per pair.
- Promotion metric haircut for the number of models tried.
- Backtest training window is the 90 days **before** each test window and nothing after it — past-only, never two-sided; retrains weekly during walk-forward. Operator ruling 2026-09-12; the earlier wording *capped at a rolling 90 days* was read as two-sided and is retired.
- Decision bars before `dataset.decision_start_date` (2017-01-01) are excluded from the labelled dataset. A tradability exclusion, not a data-quality one: the 2013–2016 bars are real but describe a market no position could have been taken in. Operator ruling 2026-09-12.
- Every pair that clears the archive's two-year rule is in the dataset, thin ones included. `dataset.min_labelled_rows` is the per-pair floor, 0 today (no floor); a cross-sectional model may want one, and the decision is deferred behind that named knob. Operator ruling 2026-09-12.
- An LLM is not the predictor. Any alternative method must first clear the fee hurdle.
- Build order is structure, then interface, then backend.
- Console is built against the real schema with seeded fake data, so no rework when real data arrives.
- Paper mode until a validated model exists. A readiness gate, not an account-size gate.

### Lead rulings of 2026-09-12 for Phase 5, each confirmed by the operator the same day and overturnable by the operator only

- **Engine 20 `tournament` is Phase 5 work.** Its leaderboard is what engine 14 reads in Phase 6.
- **`src/acsoe/modelling/` is the one package both the live loop and `research/` import**, C-owned, so live and replay compute from one implementation. Invariant 5 in `architecture-context.md` says so.
- **Engine 8 `prediction` blocks on a DI refusal** under contract rule 6, reason code `di_refused`, publishing no `expected_move_pct`, and stays a non-gate in the registry. The alternative put the veto after cost and risk had already run on a distrusted prediction.
- **The evaluation number is the Brier of P(target) against the fold's base-rate Brier**, with log loss beside it and the BUY-call target rate against the break-even rates in invariant 5.
  Accuracy is never computed: the base rate is 23.89% and a model that always predicts `stop` is right 51% of the time. Retired as a term in `ai-workflow-rules.md`.
- **Rows are weighted by average uniqueness**, and the effective sample size is reported **per fold on the same line as that fold's row count** and in aggregate. Operator addition: a fold with 8,000 rows and an effective size of 300 is a fold whose numbers mean almost nothing, and an aggregate hides exactly that fold.
- **The DI reference set** is the predictor's training rows for the fold, per pair the last `prediction.di_window_days`, mean k-nearest distance, thresholded at `prediction.di_percentile` of the leave-one-out distribution, refitted each weekly retrain.
- **Engine 7's ranking is a config-named feature**, `scout.rank_feature` with `scout.rank_descending`; alphabetical while absent, and the engine says so. The feature is ruled after spec 75's study reports.
- **`lightgbm`, `scikit-learn` and `shap` are base dependencies** from Phase 5; `hmmlearn` and `statsmodels` stay in the `research` extra.

### Operator rulings of 2026-09-12, recorded here so Phase 5 inherits them rather than asking

Context: the same day, the historical loader was pointed at the whole archive instead of
three hand-picked pairs — 234 USD-quoted pairs with at least two years of history,
20,443,861 bars — and the labelled dataset was measured over all of it. The measurement
surfaced three things the operator ruled on.

**RULING 1 — The walk-forward is past-only, not two-sided.** A fold trains on the 90 days
before its test window and nothing after it. What was built trained on 90 days on both sides
of the test window, which is purged cross-validation: legitimate for hyperparameter selection,
but it lets a model see data from after the period it is scored on, so it reports a number
better than the same model would achieve live and nothing says so. The project's goal is a
system that trades, so the validation must answer "would this have worked if I had been
trading it". **Applied:** `research/walkforward.py` now sets `train_end = test_start` and
counts every row after the test window in `Fold.after_test_count` rather than training on it;
the embargo moved to the training side of the boundary (the last `embargo_bars` before the test
window). The Locked Decision above was reworded, and the retired wording is now a
`docs_vocabulary` row. A new Phase 4 criterion, `walkforward_trains_on_the_past_only`, proves
on every rolling fold that no training row's decision bar or label window end post-dates its
test window, with mutation proofs in `tests/verify/test_phase4_criteria.py`. Measured effect on
the three original pairs: median training rows fell from ~17,175 to
~8,586, which is the ruling doing what it says.

**RULING 2 — Exclude decision bars before 2017-01-01.** The archive begins 2013-10-07 and the
earliest bars are single trades of 0.1 BTC in fifteen minutes. Those bars are real but describe
a market no position could have been taken in at any size, and a model trained on them will
learn patterns that do not transfer. **The exclusion is about tradability, not data quality.**
**Applied:** `dataset.decision_start_date: "2017-01-01"` in `config/default.yaml`, read by
`research/labelling.py` with no default (a null raises), applied in `label_series`, and
reported per pair as `LabelledSeries.excluded_before_start` and by engine 23 as
`excluded_before_start_by_pair`. **Cost, measured:** 92,791 labelled rows
removed (0.45% of 20,424,028), across the 6 pairs whose history
predates 2017 — XBTUSD 46,671, ETHUSD 25,973,
LTCUSD 10,411, ETCUSD 7,221, ZECUSD 2,724,
REPUSD 475. The dataset is 20,331,237 rows. Both figures are in
`docs/PROJECT-STATE.md` section 10 and `docs/dataset/`.

**RULING 3 — Keep the eleven thin pairs; add the floor as a named knob.** Eleven of 234 pairs
carry fewer than 20,000 labelled rows (TUSDUSD 4,659 and ETHPYUSD 4,812 the
smallest). They stay. `dataset.min_labelled_rows` is the per-pair floor, reads `0` today so
nothing is excluded, and engine 23 names any pair it leaves out in `pairs_below_floor`. A
cross-sectional model may want a floor; that decision is deferred with a named knob, not
overlooked. **One deviation from the ruling's letter, stated:** the operator asked for a
default of null. `platform/config.py` refuses every null key at load — null means OPERATOR
REQUIRED and stops the process, which is the right rule for a trading threshold and is
documented as deliberately not special-cased — so the absence of a floor is spelled `0`, with
the reason in the YAML comment and in `DatasetConfig`.

## Open Questions

- **OPEN for the operator, Phase 5, deliberately: three values are absent until the walk-forward reports.** `prediction.di_percentile`, `anomaly.threshold_percentile` and `skeptic.veto_threshold`. The operator ruled 2026-09-12 that the lead's recommendations (0.95, 0.99, 0.5) are guesses until there is a distribution to place them on. Engines 8, 13 and 15 fail closed while the keys are absent and the Phase 5 criteria that judge them report PENDING naming the key. The fourth, `scout.rank_feature`, waits on spec 75's ranking study.
- **OPEN, Phase 5, for the operator at leisure: where a previous bar's DI would live so that engine 12 `regime` can read DI threshold crossings.** The locked decision says crossings feed the regime engine; engine 12 runs before engine 8 on the same tick and `state` is fresh, so nothing persists last bar's DI. Engine 12 publishes `di_regime_shift: null` with the reason (spec 66). Persisting it is a schema question, B's edit and the lead's approval, and Phase 6's router is the first reader that would need it.
- **DECIDED 2026-09-09, and it is the first task of Phase 2, before any engine work.** The operator ruled on the defect below. The fix composes the reader from the four methods `StoreClient` already has — `pending_commands()`, `claim_command(command_id, *, claimed_at, run_id)`, `claimed_unconsumed_commands()` and `mark_command_consumed(command_id, *, consumed_at)` — **entirely inside `core/`, renaming nothing in B's directory.** It also wires the startup re-application of claimed-but-unconsumed rows, which is absent today. And it lands with a **Phase 2 criterion that drives the real `StoreClient` — not a double — through `activate`, `freeze` and `close_all`, asserting the mode changed and the row was consumed**: a criterion that would have caught this. **Phase 0 was reported green with the kill switch inert**, and that is the point worth carrying: `orchestrator_empty_registry` runs against an empty registry and every other test of the command path uses a test double, so nothing in the suite ever put the real store behind the real reader. A gate that only ever exercises a seam through a double does not test the seam; it tests the double. The same question should be asked of every other seam in `ownership.md` before its phase closes.
- **RESOLVED 2026-09-09, before Phase 2 engine work began — the orchestrator reads no commands, so the kill switch does not work.** Fixed by the lead as the first task of the phase, composed from the four methods `StoreClient` already exposes, entirely inside `core/`, renaming nothing in B's directory; the startup re-application of claimed-but-unconsumed rows is wired and had never existed. A third break in the same path turned up while fixing it: `_clear_close_intent_if_finished` called a `mark_close_all_consumed` the store has never had, so even a *successful* liquidation left its row unconsumed for the startup replay to re-run on the next boot against an already-flat account. `commands_round_trip` is registered for phase 2 and PASSes. The original finding, kept because the lesson is the transferable part: Found 2026-09-09 by C while building spec 24, confirmed and widened by the lead. `core/orchestrator.py:173` looks up `store.claim_pending_commands` via `getattr`; **`StoreClient` has no such method.** It exposes `pending_commands()`, `claimed_unconsumed_commands()`, `claim_command(command_id, *, claimed_at, run_id)` and `mark_command_consumed(command_id, *, consumed_at)`. So the lookup returns `None`, the reader logs `commands_skipped` at debug level and returns, and **a daemon wired to the real store would silently ignore every Activate, Freeze and Close-all ever written.** Two further faults in the same method: `_mark_consumed` calls `mark_command_consumed(command, now=...)` against a signature of `(command_id, *, consumed_at)`, which would raise if it were ever reached; and **the startup re-application of claimed-but-unconsumed rows is not wired at all** — nothing in `src/` calls `claimed_unconsumed_commands()`, though `architecture-context.md` requires it and names the exact failure it prevents, a daemon killed mid-liquidation coming back with `close_all` marked done and positions still open. The only implementations of the orchestrator's shape are a test double in `tests/core/test_orchestrator.py` and C's documented adapter in `tests/console/test_commands.py`, which is why every gate to date has passed over it. **This is Phase 0 work in `core/orchestrator.py`, which is lead-only, so it is the lead's to fix and no teammate's.** Harmless in Phase 1 — no daemon runs and the console only writes rows — and it bites the moment one does, which is Phase 2. The cheapest correct fix stays entirely inside `core/`: compose the reader from the four methods the store already has, rather than renaming anything in B's directory. **Fix before any Phase 2 work begins.**
- **RESOLVED 2026-09-09 — `toolchain_green` is now registered for every phase**, via `register_every_phase`, exactly as `docs_vocabulary` is. `TOOLCHAIN` stays scoped to `src/`: the operator deliberately did not widen it to `tests/` or `scripts/`, so the two Phase 0 findings in `verify.py` and the three in `tests/` remain out of scope for the gate. One consequence to expect: every phase's gate now runs `pytest`, so the intermittent seed-path crash below can now surface as a FAIL on any phase rather than only Phase 0. The account of the hole this closed:
- *Was open, for the operator at the Phase 1 boundary — `toolchain_green` was registered for Phase 0 only, so from Phase 1 onward the gate never ran the tests.* Found 2026-09-09: `scripts/verify.py --phase 1` reported `7 PASS, 0 FAIL, 2 PENDING` while `pytest` was reporting `2 failed, 639 passed`. Nothing in the report was wrong — no Phase 1 criterion makes a claim about the suite — but "a phase is done when `verify.py --phase N` passes every criterion" is the project's definition of done, and for every phase after 0 that definition currently cannot see a red suite. Run-protocol step 4 covers the gap by making each agent run all four commands themselves, which is why this was caught, but it depends on a person following a procedure rather than on the gate. **The obvious fix is to register `toolchain_green` for every phase, exactly as `docs_vocabulary` already is.** It is a change to what every phase asserts, so it belongs at a phase boundary and to the operator, not mid-phase and not to an agent — the same reasoning that deferred widening `TOOLCHAIN` beyond `src/` out of Phase 0. Note the two interact: registering it for every phase also spreads the intermittent seed-path crash across every phase's gate, so the crash question above should be settled first or at the same time.
- **OPEN, and deliberately so: engine 7 `scout` has no ranking score, and Phase 3 does not give it one.** Operator ruling 2026-09-10. Invariant 4 says the candidate ranking is "a deterministic score over features"; features are engine 5, which is Phase 5. The operator's words, which belong in the record verbatim: *a deterministic score over features is meaningless before features exist, and a placeholder score would be a check whose output resembles the claim while the claim is untrue — this phase has produced enough of those. The universe filter is the contribution; ranking one candidate out of a filtered set is a Phase 5 decision made with real features in front of us.* So Phase 3 orders the universe **alphabetically**, which is equal treatment of every pair when nothing yet distinguishes them, and spec 44 isolates the ordering behind one named function so Phase 5 is a single edit. **An agent arriving in Phase 5 must not read alphabetical ordering as a choice anyone defended.** It is a recorded absence.
- None otherwise blocking. The nine operator-required values are set; see below.
- **Resolved 2026-09-09 — the console screens with no design.** History, the research views, the leaderboard and the SHAP view are named in the Phase 1 criteria and designed in no context file. Split in two at planning: history and the leaderboard have no design but do have data in the Phase 0 seed, and `ui-context.md` already grants an undesigned screen the cycle feed's table treatment, so specs 21 and 22 build them under it. The SHAP view has neither design nor data — `rejections.shap_ref` points at a Parquet artefact the training pipeline does not write until Phase 5 — so spec 22 renders an honest empty state and bans a placeholder chart. Put to the operator at approval rather than decided silently; the operator confirmed the empty state stands.

## Operator-chosen starting values (2026-09-08)

The operator supplied the nine values the context files name but never specify. **These are starting values, not settled ones — explicitly subject to revision once Phase 3 measures what the economics actually are.** They exist so Phase 3 can run, not because anyone yet knows they are right.

| Key | Value |
|---|---|
| `trading.hurdle_multiple` | 1.5 |
| `trading.risk_fraction_per_trade` | 0.01 |
| `trading.max_concurrent_positions` | 3 |
| `trading.entry_unfilled_window_s` | 300 |
| `trading.base_reporting_currency` | USD |
| `paper.starting_balances` | `{USD: "5000.00"}` |
| `safety.max_drawdown_pct` | 0.10 |
| `safety.max_consecutive_losses` | 5 |
| `safety.max_errors_in_window` | 20 |

The OPERATOR REQUIRED machinery stays in place. It is what will protect the tenth such key, and the loader still refuses to start on a null.

### Two consequences of these values, checked by arithmetic before they surprise anyone

**1. At tier 1, nothing clears the cost gate — by construction.** Invariant 5 requires `net_edge > hurdle_multiple x friction`, which rearranges to `expected_move > (1 + hurdle) x friction`. At `hurdle_multiple: 1.5` that is `2.5 x friction`. Tier 1 friction is ~1.25%, so a candidate needs an expected move above **3.125%** — and the target barrier is **3.0%**. The gate is therefore unreachable at tier 1 with these barriers. At tier 3 (~0.65% friction) the bar is 1.625% and clears comfortably.

This is consistent with the project's cost-adaptive selectivity and with "a negative result is a valid result", so it is recorded rather than corrected. But **Phase 6 must not read zero trades at tier 1 as a bug**: that is these three numbers interacting exactly as specified. Either the hurdle comes down, the target goes up, or tier 1 is understood to be a no-trade regime.

**2. `max_concurrent_positions: 3` is inert at this balance.** Risk of 1% of $5,000 is $50; a 1.5% stop implies ~$3,333 of notional per position. Three would need ~$10,000 against a $5,000 balance, so the **balance binds first and concurrency is effectively 1**. Invariant 6 already forbids allocating cash the account does not hold, so nothing is wrong — but a Phase 6 test asserting three simultaneous positions would fail for reasons unrelated to the code under test.

## Decision history

Four onboarding audits, in order. Later sections override earlier ones where they conflict; superseded lines are struck through. The current design is always `engine-contracts.md` and `architecture-context.md` — this section is the record of how it got there.

### After the first audit

The lead's onboarding audit found 25 issues. These were resolved by the operator:

- `core/` holds contracts and the orchestrator only. Config, clock and logging moved to `platform/`, owned by A.
- ~~The orchestrator has three runtime chains: ingest (1–4), opportunity (5–18), manage (21, 22, 19).~~ **Superseded by the fifth audit** — the first chain is the *guard* chain and carries engine 17 as well: 1, 2, 3, 4, 17. The opportunity chain is 5–16 plus 18. Engines 20 and 23 still run in an offline chain via `acsoe research`. Without this split, positions were never watched, and freeze would have stopped the recorder.
- `scripts/verify.py` is sequenced first in Phase 0 and reports PASS, FAIL or PENDING, so criteria can exist before the code they judge.
- Every criterion runs offline against a recorded artefact. `--live` is opt-in and never required for a phase to be green.
- Each agent owns `tests/` mirroring its own source paths, and its own `docs/build-log/phase-N/<agent>.md`.
- One working tree, one branch, no per-teammate branches. The ownership map is the only concurrency control. The lead commits at task boundaries; teammates do not commit.
- Timeout is 48 bars, which is 12 hours and consistent with the 2–12 hour horizon. It was 24 bars, which is 6.
- Break-even at tier 3 is ~48%, not 54%. The tier 1 figure of ~61% was correct.
- Engine 6 renamed `macro_context` to stop colliding with the `context/` directory.
- Engine 13 `anomaly` moved from B to C — it is a model engine built in Phase 5.
- The Dissimilarity Index lives inside `engines/prediction/`. The execution offset bandit lives inside `engines/execution/`. Neither is an engine.
- A `recorder` client was added to `Clients` so engine 2 can append JSONL without violating contract rule 4.
- Friction assumes maker entry and taker exit — the worst realistic case.
- Paper mode falls back to tier 1 on a failed fee fetch and logs it. Live mode still blocks.
- `config/LIVE_CONFIRMED` is compared against `context.now` in UTC.
- The lead authors `config/default.yaml`.

### After the second audit

The lead's second audit found 22 issues, most of them decisions that had reached some files and not others. Resolved:

- `code-standards.md` corrected — config, clock and logging are in `platform/`, not `core/`.
- `core/` imports nothing. `Config`, `Clock` and `Clients` are Protocols declared in `core/contracts.py` and implemented in `platform/` and `clients/`.
- ~~Chain 2 is exactly three engines: 21, 22, 19.~~ **Superseded by the fourth audit** — there are now three runtime chains; see below. Engine 20 still runs offline.
- Paper-mode fallbacks are stated once, in a table, scoped to mode. Live mode always blocks. Fee falls back to tier 1; balance falls back to `paper.starting_balances`, a per-currency map; pair rules and spread have no fallback and block the pair.
- `clients/recorder/` exists and belongs to A.
- Per-task done is **no FAIL**. PENDING is expected mid-phase and only reaches zero at phase close.
- Every criterion must pass on a fresh clone. Evidence lives in committed fixtures under `tests/fixtures/`, never in gitignored `data/`. `--live` verifies the real run and is never required for green.
- `logs/` exists, belongs to A, and is gitignored.
- The command table has defined semantics and a reader: the orchestrator, in `core/`, at the top of every tick, marking each command consumed.
- The three-switch live check is `platform/live_guard.py`, A's. Three conditions, not three read paths.
- `feature-specs/` has a mandatory template, so Scope Limits is a defined section.
- C owns `tests/` root, `conftest.py` and `tests/fixtures/`. A creates `data/` and `logs/`.
- "Within one tick" means one `tick_size` from `AssetPairs`.
- `console.poll_interval_ms` must be under a quarter of `console.stale_after_ms`, enforced by config validation.
- ~~The eight non-ML engines are enumerated: 1, 2, 3, 4, 10, 11, 16, 17.~~ **Superseded by the third audit** — scout is deterministic, so there are nine and engine 7 is among them.
- `.claude/settings.local.json` and `logs/` restored to `.gitignore`.

### After the third audit

- `.gitignore` gained `!tests/fixtures/**`. Without it `*.jsonl` and `*.parquet` silently swallowed every committed fixture, and the entire fresh-clone verification strategy failed without an error message.
- The four phase criteria that depended on gitignored directories now name committed fixtures: `record_sample.jsonl`, `recording_report.json`, `labelled_sample.parquet`, `soak_digest.json`. The real runs moved behind `--live`.
- Engine 20 has a caller. A third `OFFLINE_CHAIN` is invoked by `acsoe research`, never by the daemon. Engine 23 runs there too.
- **Scout is deterministic.** Design question resolved: engine 7 contains no model — the universe filter is arithmetic and the ranking is a fixed score. It is therefore protected by invariant 4, and the non-ML count is nine, not eight. Engine 15 `skeptic` is the only model gate, and it can only veto.
- ~~`state["system_mode"]` is now an orchestrator key.~~ **Superseded by the fourth audit** — the persistent key is `state["system"]`, holding `mode` and `close_intent`.
- **The kill switch is `close_all`.** No fourth mechanism. Freeze stops new trades and keeps managing open ones; close_all ends exposure.
- The orchestrator mints `run_id` and `cycle_id`, and holds the `Clock`. Engines see only `context.now`.
- `paper.starting_balances` is a currency-to-amount map, not a scalar. One number cannot satisfy the per-quote-currency invariants.
- Creating a directory is not owning the runtime data written into it. Rule 1 governs source files.
- `console.poll_interval_ms` default dropped to 500 so the Phase 1 criterion is achievable; the criterion is now twice the poll interval.
- `is_gate` is asserted by `verify.py` against the registry table, so a mis-registered gate fails loudly.

### After the fourth audit

- **Freeze no longer stops the recorder.** ~~Engines 1–4 are now their own ingest chain.~~ **Renamed by the fifth audit** — it is the guard chain, 1, 2, 3, 4, 17. It runs in every mode; only the opportunity chain is switched off by freeze. Order-book history is never lost to a freeze.
- **The safety engine freezes via the commands table.** It cannot write `state["system"]`, so it writes a `freeze` or `close_all` row through the store, which the orchestrator consumes next tick. Same channel as the console, and every stop is an audit row.
- **State is fresh every tick.** The only persistent region is `state["system"]` — `mode` and `close_intent` — carried by the orchestrator. Manage-chain engines read prior decisions from the store, never from stale state keys.
- `close_intent` is the kill switch's data path. `frozen` alone means stop opening; `frozen` plus `close_intent` means liquidate now.
- `run_id` lives only on `context.run_id`. The duplicate state key is gone.
- Engine 23 is registered in `OFFLINE_CHAIN` only, which `cli/research.py` assembles. `bootstrap.py` never imports from `research/`, so invariant 5 holds.
- Each agent deposits its own evidence fixtures under `tests/fixtures/`; C owns the structure and shared fixtures.
- Anomaly is a data-quality gate (unsupervised, over market data) and stays protected. Skeptic is a learned opinion about the trade and stays excused. The distinction is now stated.
- `acsoe research` ships in Phase 0 as a stub.
- The stray empty code fence in `engine-contracts.md` is removed.

### After the fifth audit

The fifth audit found nine issues. Four of them were one question wearing four hats — what runs unconditionally, and who may write the persistent state — so they were resolved together rather than patched one at a time.

- **Engine 17 `safety` moved from the opportunity chain to the guard chain.** It was second to last in a chain that stops at the first block or PASS, so the circuit breaker only ever ran on ticks where every other gate had already passed. An account in drawdown whose candidates were all being rejected by the cost gate would never have tripped it. The guard chain is now 1, 2, 3, 4, 17, runs every tick in every mode, and never breaks early — a bad-data block must not stop safety from evaluating. Safety is stage 1 gatekeeping, not stage 3 judgement.
- **The guard chain records the first blocker, not the last.** Two guards can block on one tick; the reason `memory` logs is the first one.
- **Safety is idempotent about what it emits.** It runs every tick now, so it writes a command row only when that row would change the state: `freeze` only while running, `close_all` only when positions are open and no intent is already set. Otherwise a sustained drawdown would append a freeze row every sixty seconds forever.
- **`close_all` cancels resting entry orders as well as closing positions.** A post-only limit still on the book is not a position and survived the old definition, so the emergency stop could leave an order that filled minutes later and re-opened exposure. Engine 21 cancels, engine 22 closes.
- **The orchestrator clears `close_intent`, not engine 22.** The old wording had an engine writing `state["system"]`, which rule 2 and the state-keys section both forbid. Engines now report `entry_orders_cancelled` and `positions_closed` in their own `data`; the orchestrator clears the intent only when both are true, so a failed cancel or close retries next tick instead of being lost.
- **Command consumption is two-phase.** `claimed_at` when read, `consumed_at` when the effect completes. A daemon killed part-way through a liquidation used to restart with the command marked done, the in-memory intent gone and positions still open. Unconsumed rows are now re-applied at startup.
- **Mode always starts `idle` and is never restored from the store.** A crashed daemon comes back not trading, with the manage chain still watching what is open.
- **Engine 3 `market_sensor` owns the decision-bar clock.** It publishes `bar_closed`; engine 5 `feature` returns PASS when it is false. Nothing previously named which engine stopped the chain on a non-bar tick, which is the mechanism the entire cadence rests on.
- **`scripts/verify.py` may import both the live path and `research/`.** It is neither, which is what lets its `is_gate` assertion cover engines 20 and 23.
- **A `docs_vocabulary` criterion runs in every phase.** Every audit so far has found a decision that reached three files and not the fourth; each file stays self-consistent, so reading does not catch it and grep does. Retiring a term now includes adding it to the table in `ai-workflow-rules.md`.

### After the sixth audit

- **README said eight non-ML engines; it is nine.** `project-overview.md` had been corrected when scout was ruled deterministic, and the README had not. The `docs_vocabulary` check passed over it because a bare count is not a distinctive token, so `eight` used as a count of the engines without ML is now a retired term in its own right. A check that only catches renamed identifiers misses corrected facts.
- **Ownership's Phase 0 row for A listed two CLI entrypoints; the phase scope lists three.** A builds `acsoe engine`, `acsoe console`, and `acsoe research` as a stub reporting no offline engines until Phase 4.
- **The manage chain now holds when `data_guard` blocks.** Previously undecided: with the opportunity chain skipped but the manage chain still running, engine 22 could have exited a position on a target or stop computed from the same stale or negative-spread data the guard had just rejected — a fabricated trigger acting on real money. Engines 21 and 22 now place no exit on such a tick, still run so that engine 19 records it, and engine 21 reports `hold_reason`.
- **`close_intent` is the one exception, and the only deliberate override of a gate in the system.** An emergency stop proceeds regardless of the guard, because a bad fill is a smaller risk than unknown exposure. It overrides in the direction of less exposure, never more, which is why it does not violate invariant 4. Blocks from engines other than `data_guard` do not hold the manage chain: they concern whether a new trade is wise, not whether an open position's data is trustworthy.
- Phase 6 gained a criterion that proves both halves — a triggered stop does not exit on a `data_guard` tick, and the same position under `close_intent` does.

### After the seventh audit

The sixth audit's own fixes produced most of this list. Four of the nine issues it found were introduced by the fix before it, which is the honest shape of a converging spec.

**The unbounded hold, and what it dragged in.**

- **The manage-chain hold is now bounded.** Holding exits on a `data_guard` block was right; leaving the hold unbounded was not. A position with a breached stop would have sat unexited for as long as the feed stayed bad, silently. Engine 17 `safety` now counts consecutive `data_guard` blocks and emits `close_all` past `safety.max_consecutive_data_blocks`, default **15** — one full decision bar at a one-minute tick, long enough to ride out a websocket reconnect, short enough that nothing is carried through a second bar on data nobody trusts.
- **The counter lives in the store, not in `state`.** `state` is fresh every tick and `safety` cannot write `state["system"]`, so there was nowhere in memory to keep it. Engine 19 `memory` writes a block record on every blocked tick — candidate or not — and `safety` counts the trailing run. It therefore survives a restart: a daemon that dies mid-outage does not reset the clock on an outage that is still running.
- **The off-by-one is specified, not left to the implementer.** `data_guard` runs before `safety` in the guard chain; `memory` runs after both, in the manage chain. So the count is stored blocks through tick T−1 plus one if the current tick is also blocked. Left implicit, this fires the breaker a minute early or a minute late.
- **Emergency liquidation now overrides a failed fetch, not just a `data_guard` block.** This was the sharpest gap: a feed outage triggers the escalation, and the same outage is failing the balance and book fetches, so under invariant 2 the `close_all` would have been blocked by the exact condition that raised it. Engines 21 and 22 may now use last known good balances and `AssetPairs` metadata past its TTL — the only place in the system where a stale cache is acceptable. Rounding still goes down, `userref` idempotency still applies, and every tolerated failure is recorded on the resulting trade.
- Phase 3 proves the breaker fires after the threshold and not one tick before, counting across a simulated restart. Phase 6 proves the escalation completes while `data_guard` is still blocking and the balance fetch is still failing.

**The override belongs in the authority file.**

- **Invariant 14 now exists.** The one deliberate override in the system was documented only in `engine-contracts.md`, while `trading-invariants.md` said gates are never bypassed and paper fallbacks were "the only exception", and `project-overview.md` said "Nothing overrides a gate". An agent reading in the prescribed order would have hit the override in a subordinate file and correctly concluded it was a bug. It is now rule 14, rules 2, 3 and 4 point at it, `project-overview.md` is corrected, and `engine-contracts.md` points at the invariant instead of restating the reasoning.
- It was appended as 14 rather than inserted after 4 on purpose: other files reference invariants by number, and renumbering would have broken every one of those references silently.

**The check's blind spot.**

- **`docs_vocabulary` no longer excludes the whole tracker**, only its `## Decision history` section. Current-state sections — Current Goal, Locked Decisions, Architecture Decisions, Known Risks — are now scanned like any other file. The blanket exclusion is how a stale claim about the memory engine survived three audits inside a section labelled Architecture Decisions.
- **What the check cannot catch is now written down.** A new rule that was never propagated has no retired token to grep for; the check reported PASS across thirteen files while three contradictory statements about gate overrides stood. `ai-workflow-rules.md` now states plainly that a PASS is not a consistency guarantee, and gives the lead a three-step manual procedure: write the rule in the authority file first, grep for the absolute claim it contradicts rather than for the new rule, and make every other mention point rather than restate.

**Smaller.**

- The cross-chain keys table is referred to by field name, not by position. Appending `hold_reason` had silently redirected "the last two" onto a field that means the opposite.
- `hold_reason` (B → C) and the per-tick block record (C writes, B reads) are now seams in `ownership.md`.
- `state["system"]` is written by **the orchestrator** in two named places — the command reader at step 0, and step 4 clearing `close_intent` — not by "the command reader" alone.
- Pseudocode step 4 uses explicit `state[...]` paths like the steps above it.
- Phase 8's soak criterion is a positive assertion: one unbroken `run_id` with a contiguous `cycle_id` sequence across the period. Counting exceptions could not distinguish a clean run from a daemon that died on day 2 and sat idle for five.
- The console shows `Idle — restarted, not trading` when the `run_id` changed and the mode is `idle`, so a silent overnight restart is visible. Text only; amber stays reserved for live mode.

### After the eighth audit

Six of the eight findings came from the seventh audit's own fixes. The pattern in them is worth naming, because it is not the pattern the earlier audits found: the *rule* was propagated correctly every time, and the *assumptions the rule rested on* were not. Contradiction-hunting does not find that. Dependency-hunting does, and the manual procedure now has a step for it.

**The forward dependency, and the chain behind it.**

- **Phase 3 depended on a Phase 4 deliverable.** Its escalation criterion counted block records written by engine 19, whose real implementation lands in Phase 4. Phases are gates; a gate that needs a later phase can never go green. Phase 3 now counts against **seeded** `block_records` from Phase 0 — offline and committed, which the criteria already demanded.
- **Seeded block records are now a Phase 0 deliverable for B**, in the ownership split and the Phase 0 exit criteria, including a consecutive `data_guard` run longer than the threshold so Phase 3 has something to count. Previously a later phase assumed them and no phase produced them.
- **`block_records` is its own table, not a column on `rejections`.** A rejection is one candidate refused; a block record is one blocked tick, and most blocked ticks never had a candidate because `data_guard` blocks before the opportunity chain runs. Folding them together would write candidate-less rejection rows and inflate the counterfactual dataset that is the point of the project. They join on `cycle_id`. Columns are fixed in `architecture-context.md`.
- **The counter orders by `ts`, never by `cycle_id`.** `cycle_id` restarts with the process, and surviving a restart is exactly why the counter lives in the store. Ordering by it would silently interleave two runs.
- **Phase 4 now proves the write the breaker depends on**: engine 19 writes a row on every blocked tick *including one with no candidate*, and `safety` counting live rows reaches the same total it reached against the seed. That requirement lived in `engine-contracts.md` and was verified nowhere — an implementer reading invariant 12 literally would have skipped candidate-less ticks and left the breaker silently inert with every test green.

**The escalation's preconditions.**

- **The trigger is now in invariant 14.** "The system liquidates your positions after fifteen minutes of bad data" is a money rule; it was stated in four files, none of them the invariants. Rule 14 now has a *When it fires* section holding the conditions, the threshold and its default, and the other files point at it.
- **A stale cache is two rules sharing a word, now separated.** For trading it does not exist. For an emergency liquidation it is the last thing the system knows, so `clients/kraken/` retains the last successful value of every fetch and never discards it on failure. Read literally, the old wording said discard, which would have made rule 14 unimplementable at the exact moment it is needed. It is a requirement on A consumed by B, and it now has a seam row.
- **Engine 21 still cancels a stale entry order during a hold.** The hold suppresses exits only. Cancelling is a decision about elapsed time, not price — no market data, and it reduces exposure. Read as "the manage chain does nothing", the hold would have left a live post-only buy on the book through an outage, which is the hazard invariant 8 exists to prevent.
- **`safety` escalates on open positions *or resting entry orders*.** The old condition was positions only, so an outage with no position but a live entry order escalated nothing and left that order to fill into a market the system had already declared untrustworthy.

**Smaller.**

- The console compares `run_id` against the previous row of the `runs` table, server-side in SQLite. "Since the console last saw one" was not implementable: the console is a separate process with no memory across its own restarts, and Phase 1 has to verify it.
- Invariant 14 no longer ends with a footnote about how other files are worded. That is the same coupling as the "last two" bug — a rule that describes its neighbours goes stale when a neighbour is reworded. It states the rule and stops.

**Correction, recorded by the ninth audit.** The step-4 dependency table reported with this audit listed `hold_reason` as producer B / Phase 6, consumer Phase 6. The seam row written in the same commit says the consumer is C — engine 19 `memory`, built in Phase 4, and the console, built in Phase 1. A consumer therefore *does* precede its producer, and the conclusion "no consumer precedes its producer's phase" was not supported by the check that was supposed to establish it. The dependency is harmless in practice, because a missing key reads as null exactly like the close-all flags — but the table was filled in from memory rather than read off the seam rows, and then presented as verification. Step 4 is now run against the parsed seam table, not by recall.

### After the ninth audit

All five findings were from the eighth audit's own fixes. The theme is narrower than last time and worse: a new clause was written into a rule without asking what the rule would need in order to run.

**The circuit breaker had no defined inputs.**

- Engine 17 asks about equity drawdown, consecutive losses, error rate, open positions and resting entry orders. Only the block count had a named source. It cannot read `state` — it runs in the guard chain, before the manage chain, and `state` is fresh every tick — so every input must come from the store, and none of them were specified. B would have invented five schemas.
- `architecture-context.md` now names the table and fields for each of the six inputs, and adds the three tables that were assumed everywhere and listed nowhere: `positions`, `orders` and `equity_snapshots`. The equity series was already required by the locked decision that alpha attribution uses the full curve including cash periods; nothing had ever given it a home.
- **Engine 19 `memory` is the single writer of every relational row** — trades, positions, orders, equity snapshots, block records, rejections. That was implicit and is now stated, because it is what makes the manage chain's always-runs guarantee sufficient for invariant 12, and it is why `memory` sits underneath `safety`'s entire input surface.
- Money columns are exact decimal strings in TEXT, never `REAL`. A drifting float equity series moves a drawdown threshold that liquidates the account.
- **All six producers are Phase 4 and `safety` is Phase 3.** The eighth audit fixed that forward dependency for one input and left it standing for five. Every one now takes the same seeded-fixture treatment.

**The seeded fixtures are named rather than assumed.**

- Phase 3's escalation criterion only passed because B's seed happens to contain an open position — invariant 14 gates emission on positions open or orders resting. Nothing said so. The Phase 0 split and the Phase 0 exit criteria now name all six fixtures explicitly: the consecutive block run, an open position, a resting entry order, an equity series with a drawdown past the limit, and a losing-trade streak past the limit.

**Two rules that promised more than they delivered.**

- **Retention is scoped to what rule 14 authorises.** Invariant 2 had required retaining the last successful value of *every* row in its table, including Spread — an input rule 2's own paper-mode table says must never have a fallback because an assumed spread invalidates the cost gate. Retention is now balances and `AssetPairs` only, and the file says plainly that spread and fee tier are not retained and why: a liquidation sells as a taker at whatever the book is, having already decided that getting flat beats getting a good price.
- **The guard chain records every blocker.** It never breaks early, so `data_guard` and `safety` can block on the same tick — and only the first was written, so a breaker firing during an outage left no row in `block_records` at all. The orchestrator now collects `state["guard_blockers"]`, engine 19 writes one row per blocker with `is_primary` on the first, and invariant 12 says so. The command row records the decision; the block row records the evaluation, and research needs both.
- The outage count is consecutive `cycle_id`s carrying a `data_guard` row, not consecutive rows. A tick where two guards blocked contributes one.

### The three rulings that opened Phase 3, 2026-09-10

**1. A drawdown breach freezes. It does not liquidate.** Engine 17's `CONDITION_ACTION` had been unratified since B built the engine, because invariant 14 and spec 36 could not both be satisfied by the Phase 0 seed: §14 listed the drawdown and loss-streak limits as escalation conditions, the seed carries a breached drawdown *and* an open position *and* a resting order, and spec 36's exit criterion required a freeze. No fixture could satisfy both. The ruling: **`close_all` is reserved for the invariant 14 data-outage escalation** and for the operator's Close all button. Drawdown, loss streak and error rate all write `freeze`. Freeze stops new positions while the manage chain keeps watching the open ones, and the operator decides whether to liquidate. The reasoning is what the condition is a statement *about*: a drawdown is a statement about past trades and liquidating on it realises a loss on the system's own authority at the moment it has least evidence it is reading the market correctly; a data outage is a statement about present knowledge, and unknown exposure is worse than a bad fill.

**2. Invariant 2's fee-tier fallback is retired.** The paper-mode table told the system to fall back to a named worst tier when `TradeVolume` failed. It was never implementable: `AssetPairs` carries no fee schedule, so there was no runtime source the value could come from, and the only way to honour the row was to write a fee percentage into the code — the hardcoded fee `AGENTS.md` forbids in its first paragraph. A confirmed pair with no fee data now **blocks that pair**, for the same reason an assumed spread does. Two consequences recorded rather than discovered: **balance is now the only paper-mode fallback in the whole system**, and it has no implementer — spec 41 builds it. And an unauthenticated fresh clone now runs its loop and records the order book but takes no paper trades, because every pair blocks at the cost gate. That is the honest description and it is preferable to a research dataset priced on a guess. A `docs_vocabulary` row was added for the retired wording, qualified so it only fires on a line that also tells the system to assume one, and it was **observed to FAIL** against a reinstatement before being trusted.

**3. `kraken.cache_ttl_s` is two keys: 300 seconds for `AssetPairs`, 60 for `TradeVolume`.** There was no cache at all, so invariant 2's *"a cache stale beyond its TTL counts as a failed fetch"* had nothing to be true of. Two keys and not one because pair rules change when Kraken lists something and a fee tier can move on a single trade. The cache and the last-known-good retention are separate mechanisms with separate readers and must not be merged: the cache answers *may I use this now*, retention answers *what is the last thing we knew*, and only invariant 14 may read the second.

**And one ruling on how the wiring is tested.** Every test that hand-builds `state["exchange"]` is rewritten to build it from engine 1's actual output. The operator's reason: *a mock that agrees with its caller is what hid this for a whole phase, and it is the third time that shape has appeared.* The first was the command reader whose every test used a store double; the second was a criterion held to a fabricated `EngineContext` whose body never once executed.

## Architecture Decisions

- Engines communicate only through `state`. No engine imports another.
- `context.now` is injected everywhere, so replay is faithful and look-ahead is structurally impossible.
- Engine 19 `memory` runs in the manage chain, every tick, so a rejection is recorded even on a tick where the opportunity chain never ran. `safety`'s outage counter is built from those records, which is why the per-tick block write is not optional.
- Live loop code and `research/` never import from each other. `scripts/verify.py` is outside both and may import either.
- Phase exit criteria are executable in `scripts/verify.py`, not a checklist anyone reads.

## Known Risks

- **Historical archives carry no order book or spread.** Engine 9 and the spread half of Engine 10 cannot be backtested before live recording began. `scripts/record.py` ships in Phase 0 for exactly this reason and must not be switched off.
- **A read-and-trade Kraken key exists on the dev machine.** Use a separate read-only key until Phase 8. The three live switches are the only thing between a bug and real money.
- **Every Kraken pair is a lot of pairs.** Develop against a config-limited subset; the universe filter handles the rest at runtime.
- **Building the interface before the backend risks guessing at data shapes.** Mitigated by fixing the schema in Phase 0 and seeding it. If a later phase needs a schema change, it goes through the lead and the console is updated in the same change.
- **An intermittent native memory fault in the seed write path.** Roughly 20% of full-suite runs die rather than reporting a verdict, always inside `seed.py` → `write_trade` / `write_position` → pydantic `model_dump`, with three different Windows fault statuses. **Not root-caused**; pyarrow, `pytest-asyncio`, test ordering, `root_import_path` and the pydantic-core version were each ruled out by test, and the one experiment that would have separated software from silicon was overridden by the power plan. Hardware is suspected and is out of scope. Mitigated by a crash-aware retry in `toolchain_green`: a crash is retried once and named in the PASS, a verdict is never retried, and a second crash FAILs. This is a closed question, not an open one — see `docs/build-log/phase-0.md`. It re-opens if the fault appears on other hardware, appears outside the seed write path, or starts failing the retry.

  **Re-opened 2026-09-09 with a captured trace. Two of this entry's three re-open conditions are met, and the recorded signature is wrong.**

  A `--phase 0` run mid-Phase-1 reported `6 PASS, 1 FAIL, 0 PENDING`; three immediate re-runs were clean. The lead re-ran before capturing the message, which was a mistake — but the underlying fault was then reproduced deliberately and captured in full. What it shows:

  - **It is not confined to `write_trade` / `write_position` → `model_dump`.** The captured trace is `seed_database` → `build` → `_write_equity` → `StoreClient.write_equity_snapshot` → `StoreClient._insert` at `client.py:194`, with `Windows fatal exception: access violation` as the innermost frame — inside `sqlite3`'s C extension, not pydantic's. `_insert` is plain parameter-bound SQL with no obvious hazard. **So this is not a pydantic bug**: the fault has now been seen inside two unrelated C extensions in the same process, which is what memory corruption looks like and is not what a library defect looks like.
  - **It does not need the full suite.** `pytest tests/clients/store/test_seed.py -q` alone crashed 1 in 8 runs. Test ordering and cross-test interaction are therefore not prerequisites, and the reproduction is far cheaper than the entry assumed.
  - **It may need pytest, but that is not proven.** `seed_database` called in a loop with no pytest in the process survived **1,120 consecutive seeds with zero faults**. `test_seed.py` collects 77 tests against a function-scoped `seeded` fixture, so those 8 runs performed roughly 480 seeds for 1 fault — about 0.2% per seed. At that rate 1,120 clean seeds is worth roughly two expected faults, so the difference is **suggestive at around p ≈ 0.1 and not conclusive**. It is the cheapest open lead: if pytest's process really is required, the candidates are things `tests/conftest.py` installs — the autouse network guard's socket patching, `hypothesis`, `pytest-asyncio` — rather than the store code, and none of those can reach production.

  **A third site, 2026-09-09, and this one is not a native crash at all.** C's first full-suite run of its final session reported `1 failed, 640 passed` — `tests/platform/test_config.py::test_a_missing_required_key_is_refused` raising `TypeError: object of type 'ScalarEvent' has no len()` from inside pyyaml's own `parser.py:118`. That file alone then passed 82/82, and two later full-suite runs passed 641 and 707. No randomised ordering plugin is installed, so the same code ran in the same order and disagreed once. C captured the trace before re-running, as instructed; it is in `docs/build-log/phase-1/c-interface.md`. **pyyaml is pure Python**, so a parser state object being handed to `len()` is not a fault in a C extension at all — it is a wrong value appearing in ordinary interpreter state. Together with the pydantic and sqlite3 sites, that is three unrelated libraries, one of them not compiled, which is consistent with process-level memory corruption and inconsistent with a defect in any of the three.

  **RE-OPENED AND WIDENED 2026-09-09. The "seed write path" in this entry's title is now wrong, and the retry does not cover the worst shape.** A escalated two further instances, neither touching SQLite or `seed.py`:

  - **Inside CPython's own `ast.walk`**, during `tests/console/test_reader.py::test_no_console_module_reads_wall_time`: `todo` is a `deque` created two lines earlier and had become an `ast.Load` object — `AttributeError: 'Load' object has no attribute 'extend'`. **A local variable changed identity mid-function.** Not a test bug and not a library bug; it is interpreter state being corrupted, which is the signature this entry already describes. Passed in isolation, and C reported 1068 passing at the same moment.
  - `pytest tests/engines/test_market_sensor.py` died with a faulthandler dump **after all 20 of its tests had passed**. That file touches no seed and no SQLite.

  **The dangerous consequence, and the reason this matters more than the crash count.** The `ast.walk` instance **did not crash**. It produced an ordinary failing verdict with a non-zero exit. `toolchain_green` retries a *crash* and never retries a *verdict* — which is correct policy, and means **this shape is reported as a genuine test failure in whoever's file it lands in.** It looks exactly like another agent broke something. It landed in C's test during A's run.

  **So, standing guidance until this is understood: a one-off failure in another agent's tests, which passes in isolation and which that agent did not touch, should be suspected as this fault before it is treated as their defect.** Capture the full output — head included, never a `tail` pipe — and compare against the instances above.

  Nothing here is a request to chase the cause. Hardware remains suspected and out of scope by the operator's ruling. What has changed is that the entry's own scope statement is stale and the mitigation's coverage is narrower than it reads.

  **Consequences.** The `toolchain_green` retry is not sufficient on its own: at roughly a 20% per-run crash rate, two consecutive crashes is about 4%, which is how often a spurious FAIL should be expected. That matches what was seen. It does not block Phase 1 — the mid-phase bar is no FAIL, and `--phase 1` has been clean throughout — but it does mean a FAIL must be **captured in full before re-running**, and a spurious FAIL must never be assumed without the trace to prove it. Whether to widen the retry, quarantine the seed fixture, or chase the pytest lead is a decision for the operator at a phase boundary, not something to settle mid-phase.

  **Fired again at the Phase 2 close, 2026-09-10, and it is now a stated limitation of the work rather than only a risk on this register.**

  The fault appeared on the **first gate run of the closing session** and **cleared on the crash-aware retry in `toolchain_green`** — the mitigation behaving exactly as designed: one crash retried and named, a verdict never retried. It then fired **repeatedly across the rest of the close**, and the session became the densest sample of this fault the project has taken. Closing the phase meant running the gates again after each documentation change, so roughly **twenty gate runs** were made in one session — about ten of Phase 2 and five each of Phases 0 and 1 — plus three direct full-suite runs.

  **Four of those runs reported FAIL. Every one was this fault, and none was a defect.** Two landed on Phase 2, one on Phase 0 and one on Phase 1, which is itself diagnostic: the tree did not change between them. Of the three direct full-suite runs, two reported `1075 passed` and one died with a faulthandler dump.

  The failing tests were different every time and scattered across unrelated files:

  > `ERROR tests/clients/store/test_seed.py::test_a_tick_with_two_blockers_contributes_one_to_the_outage` — `1074 passed, 1 error`, first attempt crashed with `0xC0000005 ACCESS_VIOLATION`
  > `ERROR tests/engines/test_exchange.py::...` **and** `FAILED tests/platform/test_record_format.py::test_sample_contains_no_secret_shaped_key` — `1 failed, 1073 passed, 1 error`
  > `ERROR tests/cli/test_entrypoints.py::test_the_console_port_comes_from_config_and_never_from_a_constant` — `1074 passed, 1 error`
  > `RETRIED AFTER CRASH: the process died with 3221226505 (0xC0000409 STACK_BUFFER_OVERRUN) [...] the retry was clean`

  **All three named tests were then run together in isolation and passed in 0.72s**, and the only changes staged at the time were Markdown — the tracker and the build logs. No source file, test file or fixture was touched. So the tree that "failed" and the tree that passed were byte-identical.

  **Two of the four defeated the mitigation, and that is the shape that matters.** The retried run returned a wrong *verdict* rather than a second crash, and policy is that a crash is retried once and a verdict is never retried — so the gate correctly reported FAIL. That policy is right and must not be relaxed to make this go away: **a rule that retries verdicts is a rule that retries real defects until they pass.** B recorded the first instance of this shape earlier in the phase; there are now four.

  **One of them is worth singling out.** `test_sample_contains_no_secret_shaped_key` is the test that proves no credential was committed into the recorder sample. A spurious FAIL there reads as a leaked secret in a public repository, which is the single most alarming thing this suite could say, and it was false. A fault that can fabricate *that* verdict is a fault that can fabricate any of them, in either direction. The criterion named it in its own PASS line rather than hiding it:

  > `RETRIED AFTER CRASH: pytest CRASHED: the process died with 3221226505 (0xC0000409 STACK_BUFFER_OVERRUN), which is outside the 0-5 range pytest returns [...] the retry was clean`

  Four spurious FAILs and at least two native crashes across roughly twenty gate runs is a materially higher rate than the ~20% per-run this entry has recorded since Phase 0. Whether the rate has genuinely risen or this session simply sampled it far more heavily than any previous one is **not established**, and one session is not enough to claim a trend — the honest reading is that the earlier estimate was taken from far fewer runs. **Phase 2 is closed on gates that had to be run more than once**, and that is stated here rather than smoothed over: the PASSes are real, reproducible and were re-obtained on a byte-identical tree, the mitigation did what it was designed to do, and the fact that it had to is the limitation.

  **Why this moves it into the dissertation's limitations chapter.** It is no longer a hazard that might materialise; it has now materialised in every phase of the project — Phase 0 where it was found, Phase 1 where its recorded signature turned out to be wrong, Phase 2 where it beat the retry once (B's entry) and where it has now fired at the phase boundary itself. Across those phases it has been seen inside pydantic-core, inside `sqlite3`'s C extension, inside pure-Python pyyaml, inside CPython's own `ast.walk`, and as a lax pydantic validator returning a strict validator's error. That spread is not a defect in any one library, and it is not going to be fixed by this project.

  What it means for the claims the dissertation makes is specific and limited, and it should be written down in exactly these terms rather than as a general disclaimer:

  - **Every phase gate in this project is a retried measurement on hardware with a known intermittent fault.** A green gate means green on a run that completed; at roughly a 20% per-run crash rate, two consecutive crashes is about 4%, which is how often a spurious FAIL should be expected and has been seen.
  - **The retry covers crashes and not wrong answers.** The `ast.walk` instance produced an ordinary failing verdict, not a crash, and the lax-validator instance produced a `ValidationError` naming a real field. Those shapes reach the operator as somebody's defect. The standing guidance already on this register — suspect this fault before treating a one-off failure in an untouched file as an agent's defect — is a *procedural* mitigation, and procedural mitigations belong in a limitations section because they depend on a person following them.
  - **It is not reproducible on demand and the root cause was not established.** Hardware is suspected; pyarrow, `pytest-asyncio`, test ordering, `root_import_path` and the pydantic-core version were each ruled out by test; the one experiment that would have separated software from silicon was overridden by the power plan. 1,120 consecutive seeds outside pytest produced zero faults, which is suggestive at around p ≈ 0.1 and not conclusive.
  - **What is unaffected.** None of the five sites is in a code path that runs in production: they are the seed generator, the test harness and the verifier. No engine, no store write on the live path and no orchestrator tick has ever exhibited it. The limitation is on the *evidence-gathering apparatus*, not on the system under test — and that distinction is the honest way to state it.

  Still not a request to chase the cause. The operator's ruling that hardware is out of scope stands. What changed at this close is where it gets written up.

## Session Notes

- 2026-09-13 — Phase 5 opened and run for one session, then wound down by the operator at
  the session limit. Done and committed: specs 59, 61, 62, 63, 76. Half-finished and
  uncommitted: 60 (helper block only) and 64 (engine 5 landed, one lint finding); untouched:
  65 to 75, 77. The full handoff, the rulings made after spec 59, and the agent-team incident
  (a revived team, two writers per lane, sends by name reaching the wrong session) are at the
  top of `feature-specs/PHASE-5-TASKS.md` and in `docs/build-log/phase-5/lead.md`. The three
  operator thresholds are deliberately absent from config until the walk-forward reports.
- 2026-09-12 — full-archive rebuild (234 pairs), dataset measured, three operator rulings applied (past-only walk-forward, 2017 cutoff, thin-pair floor as a named knob). Phase 5 not started. The Phase 4 gate was not re-run in full after the new criterion landed; every Phase 4 criterion was run directly and the full pytest suite was run — see the lead's build log for the outputs.
- Project starts from scratch. Any earlier ACSOE code was throwaway scaffolding and must not be carried over or referenced.
