# Progress — c-interface

Your file. Only you write here. The lead merges into `context/progress-tracker.md`.
Never edit the tracker directly.

## Current Task

### Phase 4 — claimed 2026-09-11, before any code was written

Seven specs, claimed here in the order the task list fixes:

- **Spec 48 — the Phase 4 exit criteria in `scripts/verify.py`. Claimed, first in the
  phase.** `--phase 4` registers `docs_vocabulary` and `toolchain_green` alone and prints
  *"Phase 4 is green: every criterion PASS, zero PENDING"* over a phase in which nothing
  exists. Seven non-live criteria plus one `--live`, each PENDING until its subject lands.
- **Spec 49 — engine 19 `memory`, the block record on every blocked tick. Claimed.**
- **Spec 50 — engine 19 `memory`, the five live-row tables. Claimed.**
- **Spec 52 — triple-barrier labelling, `research/labelling.py`. Claimed.**
- **Spec 53 — the purged, embargoed walk-forward splitter. Claimed.**
- **Spec 56 — `tests/fixtures/labelled_sample.parquet`. Claimed.**
- **Spec 57 — the console on real rows. Claimed.**

### Phase 4 state at handoff

`python scripts/verify.py --phase 4` reports **9 criteria: 9 PASS, 0 FAIL, 0 PENDING**, with
`replay_full_archive` skipped as `--live`. Phases 0, 1, 2 and 3 all still report green and
byte-identical summaries to what they reported before this phase: 7/7, 10/10, 9/9, 9/9.
**I have not closed the phase and have not consolidated the build logs.** Both are the lead's.

All seven specs are finished except one numbered step, recorded under Open Questions below.

- **48 — the Phase 4 criteria. Done.** Seven non-live criteria plus `replay_full_archive`
  (`--live`). Each observed PENDING against an unbuilt tree, PASS against the real repository,
  and **FAIL against a deliberately broken subject** — 34 tests in
  `tests/verify/test_phase4_criteria.py`, every induced failure and its message written up in
  `docs/build-log/phase-4/c-interface.md`.

  One change outside Phase 4 and it touches a Phase 0 test.
  `test_no_phase_zero_criterion_reads_data_models_or_logs` enforced "no criterion reads a
  gitignored path" as a **line scan over the whole of `scripts/verify.py`**, which was correct
  only while no criterion was `--live`. `replay_full_archive` is the project's first, and
  reading `data/historical/` is the point of it. The test now walks `inspect.getsource` per
  **registered non-live** criterion across every phase — strictly more coverage than before —
  and a second test pins the exception: `replay_full_archive` must be registered `live=True`.
  Both mutated, both observed red.

- **49 — engine 19 `memory`, block records. Done.** `MemoryEngine` in `engines/memory/`,
  contracts, README and `tests/engines/test_memory.py`. Six mutations, six red.

- **50 — engine 19, the five live-row tables. Done.** `tests/engines/test_memory_rows.py`.
  Eight mutations: six red on the first pass, **two survived and both were real gaps** — no
  test covered a balance response that omits the reporting currency, and no fixture ever made
  the store's and `state`'s position counts disagree. Both now covered, both mutations red.

  **The six totals match.** `safety` reading engine 19's live rows reaches the same six numbers
  it reaches against B's Phase 0 seed: drawdown 0.2000017843760037115020877199, 8 losing
  trades, 23 error blocks, 18 outage ticks, 2 open positions, 2 resting entry orders. That is
  the forward dependency Phase 3 was forced to seed around, closed.

- **52 — triple-barrier labelling. Done.** `research/labelling.py`, 41 tests, and
  `tests/fixtures/labels_hand_verified.json` — 20 labels from the real SOLUSD archive whose
  expectations came from a **second implementation written from the spec's prose**, with three
  verified by hand and the working in the build log. Eight mutations: seven red,
  **one survived** — `label_window_end_ts` set to the decision bar, which is the field the
  splitter purges on. Two tests added, mutation now red.

- **53 — the purged, embargoed splitter. Done.** `research/walkforward.py`, 12 tests. All three
  named mutations — embargo zero, purge no-op, purge on `decision_ts` — observed red **twice
  each**: against the unit tests and against the phase criterion. Writing the tests found a
  real defect in the module (a malformed call raised when there were rows and returned `[]`
  when there were not).

- **56 — `labelled_sample.parquet`. Done.** 960 labelled bars, produced by running A's
  `ArchiveReplay` over A's archive and my labeller over the frame it returned. Provenance lives
  **in the file** as parquet key-value metadata. 25,111 bytes, byte-identical through a git
  round trip.

- **Late additions after the lead's, A's and B's review messages.** The CRLF mechanism the
  lead explained was live in two of my own deposits: `tests/fixtures/README.md` (73 CRLF, 0
  bare LF, against a committed file that is pure LF) and `labels_hand_verified.json` (7,015
  CRLF), both from `Path.write_text()`, both under the `-text` attribute where no clean filter
  normalises them. Fixed by writing bytes; the builder can no longer reintroduce it; all three
  fixtures verify byte-identical through a git round trip. `tests/fixtures/recording_report.json`
  has the same signature and is A's — reported, not touched.

  `replay_full_archive` now has five observations including **both** PENDING branches, reached
  in a tree with no `data/` because the real archive makes them unreachable here. `--live`
  reports `3 archive(s), 859248 bars spanning 4469 days, 18745 gap run(s)`.

  A's `holes_mean_no_trades` warning changed the fixture builder and the criterion, and caught
  two real mistakes: `from_archives` never reads `PROVENANCE.json` so the flag came back `None`,
  and `from_directory`'s merged report was giving the sample XBTUSD's 2013 span as SOLUSD's —
  which would have silently weakened the timeout-horizon assertion.

- **One more defect, found by A's answer about `interval_s`.** `check_replay_full_archive`
  was loading the operator's real archive at a **hardcoded 900** rather than at
  `timeframes.decision_bar_s`. The interval is the grid every gap statistic is measured
  against, so the wrong one makes most real gaps vanish and prints a confident, plausible,
  wrong number. Harmless only because the constant equalled the config value — the condition
  that makes a remembered value invisible. Now read from config, PENDING if unset, and proved
  by mutation: at 1800 the reported gap total moves over the same files. The constructed-fold
  interval stays a literal and is renamed `_CONSTRUCTED_INTERVAL_S`, because one name serving
  both uses is how the archive read borrowed it.

- **Two Phase 0 assertions decoupled from prose, on the lead's push-back.** Adding the word
  `runtime` to `orchestrator_empty_registry`'s message turned two tests red because they
  substring-matched an English sentence. My reading was "a message an operator reads is a
  contract"; the lead's was "a substring match on prose taxes exactly the improvements you most
  want someone to make". Both are right about different claims, so they are now two tests: the
  count is read out with a regex and asserted as an integer, and a separate test pins the
  disambiguating word against the **real** repository, asserting first that the two criteria's
  totals genuinely differ by one. Mutations separate cleanly — tidying the word away reddens
  only the wording test; an off-by-one count reddens the count tests.

- **Spec 51's swap is landed and B verified it independently.** `console/reader.py` calls
  `recent_blocked_ticks(self._feed_limit)`; the primary-preference loop and both
  `_TS_MIN`/`_TS_MAX` sentinels are gone.

- **57 — the console on real rows. Done except step 3, which the lead has now deferred.**
  The lead ruled step 3 a spec error rather than a gap: engine 19 arriving is not sufficient,
  because no column holds the tally, and option 2 would change what `rejections` means — a
  tick-level fact in a candidate-level table. Recorded in the tracker with Phase 7's attribution
  named as the forcing function. History renders live rows, the cycle
  feed goes through B's bounded `recent_blocked_ticks`, the two sentinel `_TS_MIN`/`_TS_MAX`
  bounds are gone with the last unbounded read, and all 19 reason codes across engines 7, 10,
  11 and 17 are confirmed present in `REASON_PROSE`. 10 tests in
  `tests/console/test_real_rows.py`. **Step 3 stopped** — see Open Questions.


- **Phase 3. Claimed: spec 45.** Claimed 2026-09-10, before any code was written, and first in
  the phase for the same reason spec 00 was first in Phase 0 and spec 16 was first in Phase 1:
  `verify.py --phase 3` reported `2 criteria: 2 PASS, 0 FAIL, 0 PENDING` and printed
  *"Phase 3 is green: every criterion PASS, zero PENDING"* over a phase where engines 7, 10, 11
  and 17 are unbuilt or unwired. `docs_vocabulary` and `toolchain_green` alone were claiming a
  finished phase. Seven criteria, each PENDING until its subject lands. **Finished.**

  `--phase 3` now reports **9 criteria: 7 PASS, 0 FAIL, 2 PENDING** and prints *"Phase 3 is not
  green: 2 PENDING"*. The two PENDING are `universe_varies_with_balance` and
  `phase_3_gates_have_both_tests`, both waiting on engine 7 `scout` and both naming specs 43
  and 44 in their message. That is the mid-phase bar — no FAIL — and the false green is gone.

  All twenty-one observations are in `tests/verify/test_phase3_criteria.py`: each criterion
  PENDING against a tree without its subject, PASS against the subject, and FAIL against a
  deliberately broken one. Every induced failure is written up in
  `docs/build-log/phase-3/c-interface.md`. Two of them found real defects in criteria that
  were already green — a reason-code assertion that renamed the constant it was checking
  against, so expectation and answer moved together; and an error-count comparison that was
  zero on both sides. Neither would have been found by adding PASS cases.

  Three side items landed in `scripts/verify.py` while I was in there, all recorded in the
  build log: the toolchain subprocess decode is now explicit (`encoding="utf-8",
  errors="replace"`) after a `UnicodeDecodeError` on a cp1252 em-dash threw away every line
  of a FAIL's explanation; the report is now **streamed and flushed per criterion** instead of
  printed once at the end, so a run killed by this machine's intermittent native fault leaves
  the verdicts it reached on disk rather than an empty file; and the Phase 3 safety criteria
  seed through config-derived `SeedThresholds` rather than `seed.py`'s module defaults.

- **Phase 3. Claimed: spec 46. Finished.** Started once B landed `scout/contracts.py`.
  Seven codes added to `REASON_PROSE`, all with the producing agent's wording verbatim:
  engine 7's six new per-exclusion codes, `scout_inputs_unavailable`, and
  `safety_inputs_unavailable` on B's explicit yes. `below_ordermin`, `below_costmin` and
  `insufficient_quote_balance` needed nothing — `scout` reuses engine 11's codes deliberately
  rather than minting parallel ones. **All 19 codes across engines 7, 10, 11 and 17 are now
  mapped, none of them unmapped**, and no prose string carries a digit.

  `tests/console/test_reason_prose.py` enumerates out of the producing module, and it walks
  `vars(module)` for `REASON_*` rather than the `EXCLUSION_REASONS` tuple. The difference is
  load-bearing: B deliberately keeps `scout_inputs_unavailable` out of that tuple because it
  is a fact about the tick rather than about a pair and would break
  `scanned == entered + sum(tally)` — so a test enumerating only the tuple would have left
  exactly that code unmapped, and it is the one an operator meets when something is broken.

  **The enumeration was broken before being trusted**, per the rule the lead added to
  `code-standards.md`: against a fabricated module, and then by deleting the real
  `barriers_below_tick_size` line from `format.py` and confirming two tests went red. The
  second is the one that matters — the first would still pass against a hand-written list.

  **Spec 46 step 5, reported not fixed:** the console's empty state does **not** read engine
  7's tally. `ConsoleReader.feed_summary` hardcodes "Pairs scanned" and "Entered the tradable
  universe" as `count=None, detail=_NOT_RECORDED`. The gap is structural rather than a
  missed wire — the console is a separate process reading SQLite and never sees `state`, so
  the tally needs engine 19 `memory` (Phase 4) to persist it. Its docstring also misnames the
  universe filter as engine 4 / Phase 2; it is engine 7 / Phase 3, and that comment is mine
  from Phase 1. Both left alone per the spec's scope limits and written up in the build log.

- **Phase 3. Lead-assigned: `console_websocket_pushes_on_change`. Finished.** A **Phase 1
  criterion changed from Phase 3**, on the lead's explicit ruling after I escalated rather
  than touching it inside spec 45. `budget_ms = poll_ms * 2` was doing three jobs with one
  number; it is now three mechanisms. Safety net: twenty poll intervals, still from config,
  carrying no promptness claim. Assertion: the socket stays silent through a two-interval
  quiet window in which nothing changed and the client sent nothing, then pushes when the
  watermark moves. Evidence: the measured time stays in the PASS message.

  **Strictly stronger than what it replaced.** Mutated both ways: `if False:` (never pushes)
  FAILs as before, and `if True:` (pushes every poll regardless) now FAILs too — which the
  old form could not catch, because "a push arrived within the budget" is true of a console
  that pushes constantly. Phases 0 and 2 are byte-identical to their baselines; phase 1
  differs on that one line only.

- **Phase 3. Taken from A's harness sweep: three cannot-fail findings, all in my files.
  Finished.** `fake_kraken.py`'s error-type test could not tell the real classes from its own
  fallbacks — fixed with an identity assertion, fallback kept because fabricated trees still
  reach it. `migrated_store` returned `None` for both "not written" and "written and will not
  import" — fixed by narrowing the `except`, after **two wrong attempts** that tried to make
  the consumer stricter and turned eighteen then five green tests red. And
  `pytest.importorskip` would have skipped ~370 tests with a false reason if a dependency ever
  moved to an extra — replaced with `require_module`, plus a `pytest_sessionstart` check so
  the fault is one loud abort rather than hundreds of quiet skips. All written up.

- **Phase 3. The sweeper. Finished, and it was the "intermittent fault".**
  `sweep_stale_workspaces` in `scripts/verify.py` was deleting other runs' live databases.
  B hypothesised it, the lead reproduced it first try, and the file and the false docstring
  are both mine. It now removes only directories whose **newest mtime anywhere inside them**
  predates this process's start by more than a minute — the ordering is the whole argument, so
  no lock file is needed. Four parts, and the two I would have missed are (a) the newest mtime
  *inside* rather than the directory's own, because a directory's mtime does not change when a
  file in it is written, and (b) the `contextlib.suppress(OSError)` that wrapped the loop
  rather than the body, so one unreadable entry silently stopped every workspace after it
  being swept — the leak this function exists to prevent, reintroduced by its own error
  handling. Found by writing the test, not by reading the code.

  **Ten tests in `tests/verify/test_workspace_sweep.py`, where there were none** — which is
  the other half of why it survived two phases. Both directions in one sweep, because "delete
  everything" and "delete nothing" each satisfy one half alone. Removing the mtime guard turns
  four of the ten red; setting the margin to zero turns two red. Every test runs against a
  fabricated temp root: a regression test for this bug that swept the real temp directory
  would *be* the bug.

  Two of my own tests were wrong first and are worth remembering: both anchored to
  `time.time()` where the cutoff is anchored to process start, so they passed alone and failed
  in a full run, and one of them passed for a reason that had nothing to do with the margin it
  was named after.

- **Phase 3. A's finding 8. Finished, and it was three times the size A estimated.**
  `engine_context` in `tests/conftest.py` skipped silently if `EngineContext` were renamed.
  I measured it by simulating the rename rather than counting by eye: **`1196 passed, 141
  skipped`, exit zero** — ten and a half percent of the suite gone, every engine any of us has
  written among them, and the skip reason a false sentence pointing at Phase 0. A said 44 and
  was right when counted; the engine suites tripled the same day.

  Fixed per A's rule rather than my instinct: **the fallbacks all stay, and the assertion that
  they are unreachable is what was added.** `REQUIRED_SURFACES` pairs each module with the
  attribute its fixture reaches for, and `pytest_sessionstart` aborts with `UsageError` — exit
  4, inside pytest's range, so `toolchain_green` reads it as a verdict rather than a crash.
  Deleting the `getattr`-then-skip would have broken the fabricated trees `tests/verify/`
  needs, which is the mistake I made twice on `migrated_store` this morning.

  Three tests, and the load-bearing one calls the hook against the live repository — so if a
  fixture ever starts answering "does not exist yet" about something that shipped, it says so.

### Open questions and handoffs

- ~~**For the lead — `tests/conftest.py`'s shared `seed_fixtures` fixture is wrong and it is
  mine.**~~ **STRUCK 2026-09-10. It was already fixed and I escalated it without opening the
  file.** At HEAD the fixture passes `thresholds=seed_thresholds_from_config()`; the lead
  checked it and then ran it, counting 30 non-`data_guard` block rows out of 55, where the
  module defaults would give 13. It was last touched in `3765e0d` — my own Phase 2 commit —
  and its docstring already describes the old bug in the past tense.

  What I actually had was B's `test_safety.py` fixture docstring, which says it shadows the
  shared fixture "which calls `seed_database` with no `thresholds` argument" and ends
  "Reported to C". That was true when B wrote it. I recognised the shape from the defect I
  had just found in `seeded_console_db` — which was real, and is fixed by `_phase3_seeded_db`
  — treated the two as one finding, and escalated. Two notes agreeing felt like
  corroboration; one of them was about the past. Written up in the build log; the rule I have
  taken from it is to re-check the file before citing a defect from any note, my own included.

- **For B — `safety_inputs_unavailable` is not in `REASON_PROSE`.** `cost_inputs_unavailable`
  and `risk_inputs_unavailable` both are, added 2026-09-09 from B's wording; B's
  `cost/contracts.py` docstring saying otherwise is stale. `safety/contracts.py` says the same
  of its own code and is accurate. Asked B whether to map it and proposed "The safety breaker
  could not read its inputs"; not adding it until B answers, because those three entries are
  deliberately the producer's wording rather than mine.

- **Queued, not started: consolidating the stream doubles in `tests/harness/`.** B counted
  three separate fakes for engine 3's stream — A's `FakeStream` in `test_market_sensor.py`
  and two of B's — and my Phase 3 criteria work around the same gap a fourth way, building
  quotes through `QuoteView` directly because `FakeKrakenClient` answers no `recent_trades`.
  Four workarounds for one missing capability. B has sketched a `FakeKrakenWithStream` that
  derives quotes from the committed `order_book.json` through the fake's own `order_book`
  call rather than inventing prices, which is the right design and which I intend to take
  close to verbatim. `tests/harness/` is mine so the call is mine. **B has been told to keep
  its local doubles until I land it and not to refactor onto it speculatively.**

- **Unexplained, two data points, not attributed.** Two criterion tests have each failed once
  in a full-suite run and passed in isolation and across their own directory:
  `test_a_socket_that_accepts_and_never_pushes_is_a_failure` (Phase 1, mine, touched today)
  and `test_persisted_mode_is_pending_when_core_never_calls_the_writer` (Phase 2, mine,
  **untouched**). Both drive an ASGI console through `asyncio.run` in-process. The second one
  is why I stopped attributing this to the websocket change. Not root-caused; recorded rather
  than guessed at. Re-run in isolation before believing either.

- **Not a question, but worth the lead knowing.** `is_gate_matches_registry` is Phase 0's and
  gains four gates at spec 47. Nothing I registered pins a gate count, so spec 47 does not
  have to edit anything of mine. `tests/verify/test_runner.py` does pin the phase 3
  *criterion set*, which is deliberate — adding a criterion to the wrong phase is otherwise
  silent — and spec 47 adds no criteria, so it does not touch that either.

- **Phase 2. Claimed: specs 33 then 32.** Claimed 2026-09-09, before any code was written, in the
  order `PHASE-2-TASKS.md` sets: 33 concurrently with A from the first commit, so the criteria
  exist and report PENDING while A builds the engines they judge; then 32, the Phase 1 debt.
  **Both are finished.** `--phase 2` reports 3 PASS, 0 FAIL, 6 PENDING, which is the mid-phase
  bar; every PENDING names the subject it is waiting for and who owns it.
- **Phase 1. Claimed: specs 19, 20, 21, 22, 23, 24** — the operator's checkpoint after 18 has
  been held and cleared, and all three rulings below are folded into the specs. Claimed
  2026-09-09, before any code was written, in the order `PHASE-1-TASKS.md` sets: 19, 20, 21, 22,
  then 23 and 24. **All six are finished.** The session that built 19 to 22 was killed by an IDE
  crash before it wrote its two files or finished the tests those files' docstrings claimed; 23
  and 24 were not begun. Both gaps are closed and the backfill is in
  `docs/build-log/phase-1/c-interface.md`.
- **Phase 1. Claimed: specs 16, 17, 18** — in that order, and stopping after 18 for the
  operator checkpoint on the shell and tokens. Spec 16 first for the same reason spec 00 was
  first in Phase 0: `verify.py --phase 1` reported `1 criteria: 1 PASS` on the current tree,
  which is `docs_vocabulary` alone claiming a green phase over an empty console. Claimed
  2026-09-09, before any code was written. **All three are finished**; stopped at the checkpoint.
- **Phase 0. Claimed: specs 00, 01, 02, 14, 15.** All five are finished. Built in that order —
  `scripts/verify.py` first, because nothing else in Phase 0 could be reported complete
  until it ran.

## Completed

- **Spec 33 — the Phase 2 criteria in `verify.py`.** Six registered for phase 2 alongside the
  lead's `commands_round_trip`, each proved twice and most of them a third time in the red
  direction: 42 tests in `tests/verify/test_phase2_criteria.py`. Five of the six judge code A
  has not written, so each names the surface it expects in its own PENDING line — the pattern
  spec 16 set with `CONSOLE_CONTRACT`, where the failure tells the owner what to build. All six
  contracts were messaged to A and accepted unchanged. `commands_round_trip` now has the negative
  test it never had: the **real** `core/` orchestrator over a store with no command reader, which
  is the Phase 1 defect exactly, reproduced.
- **Spec 32 — the status band reads `Running` and `Frozen`.** The mode is read as a fact through
  B's `system_mode(run_id)` accessor and never inferred from the `commands` trail, which a source
  scan asserts across the whole read path. `views.STATE_READINGS` names all four readings and a
  test pins the band's output to that tuple. B's two nulls are kept apart on the band —
  `system_mode` and `run_record_missing` — and the abnormal one is logged; both render idle.

- **Spec 00 — `scripts/verify.py` runner and criterion framework.** `--phase N`, the three
  results (PASS / FAIL / PENDING), `VerifyContext` carrying `root` as a parameter rather than
  a module constant, and `root_import_path()` so a unit test can point a criterion at a
  fabricated tree without poisoning the interpreter for the criterion that runs next.
- **Spec 01 — the Phase 0 criteria.** Seven registered for phase 0, each proved twice: PENDING
  against a tree where its subject does not exist, and PASS against a minimal fabricated
  subject, plus a third red direction wherever the criterion has a real failure mode.
- **Spec 02 — `docs_vocabulary`,** registered for every phase. The retired-term table is
  parsed out of `ai-workflow-rules.md`, never hardcoded, so adding a row extends the check.
- **Spec 14 — test harness,** `tests/conftest.py`, `tests/fixtures/` structure, network guard
  with its negative test.
- **Spec 15 — fake Kraken client.**
- **Spec 16 — the Phase 1 criteria in `verify.py`.** Eight registered for phase 1, each proved
  PENDING against a console that does not answer and PASS against a fabricated subject. The
  console's HTTP surface is named by the gate rather than discovered from the route table, and
  the contract is printed in every PENDING line through `CONSOLE_CONTRACT`, so specs 19 to 24
  are told what to build by the failure itself. `console_restart_banner` seeds one `runs` row
  for its negative half rather than two matching `run_id`s, which the schema forbids — see the
  open question below.
- **Spec 17 — the console read layer.** `console/reader.py`, `views.py` and `format.py`, with
  `create_app` gaining injected `db_path` and `clock` while staying call-compatible with A's
  `cli/console.py`. The connection is read-only via a `ReadOnlyStore(StoreClient)` subclass that
  overrides only where the connection comes from, so B's directory is untouched and the screens
  still compose from B's existing reads; a real `INSERT`, a real `UPDATE` and `write_run` are
  each proved to raise. Staleness is decided against the injected clock on both sides of the
  threshold, never wall time.
- **Spec 18 — tokens, stylesheet and the page shell.** `templates/index.html`, `static/tokens.css`
  and `static/console.css`, with IBM Plex self-hosted so the page makes zero external requests.
  Every hex lives in the `:root` block and nowhere else, the 3px amber frame appears under live
  and no border at all under paper, `.num` is the only tabular-figure rule, focus is visibly
  ringed, and the reduced-motion block drops the flash. Four of the five PASSing Phase 1
  criteria are the gate on this spec.
- **Specs 19 to 22 — the four screens.** The status band and the open-positions region
  (`GET /api/state`), the cycle feed and its empty state (`/api/feed`), the history screen
  (`/api/history`) and the research views (`/api/research`). `console/payloads.py` was added
  under all four: FastAPI's `jsonable_encoder` renders a `Decimal` by calling `float()` on it,
  so returning a view model would have floated every money field on the way out, silently. Every
  payload emits strings and integers only and the routes return `JSONResponse`, which
  short-circuits the encoder. The history screen is **two tables**, so `reader.history()`
  returns a `HistoryView` carrying `.trades` and `.rejections`; that shape change is what left
  the two stale tests below. The SHAP pane is an empty state with no `rows` key and no `chart`
  key, per the operator's ruling.
- **Spec 23 — the WebSocket watermark push.** `console/websocket.py` and
  `static/console.js`. The server reads the baseline watermark **before** accepting the
  handshake — reading it after leaves a window in which a write lands first and is never seen to
  move — then polls `console.poll_interval_ms`, read from config on **every** iteration, and
  pushes only when the value has changed. Nothing is pushed on connect: the page's first content
  is a one-time fetch of the four `GET` endpoints on the socket's `open` event, which keeps
  "did a push happen?" able to tell a working watermark from a broken one. The push payload is
  built from the same view models as the endpoints, so the two transports cannot disagree. A
  dropped socket is a visible state that reconnects with doubling backoff; the page never polls
  the API on a timer. Neither `500` nor `120000` is a literal anywhere in the package, asserted
  on the parsed AST for Python and by grep for JavaScript and markup.
- **Spec 24 — Activate, Freeze and Close all.** `console/commands.py` and
  `POST /api/command/{name}` for exactly three names; anything else is a 404 that writes no row.
  Each writes one `CommandRow` with `source = console` and `claimed_at`, `claimed_by_run_id` and
  `consumed_at` all null. The write path has its own connection, narrowed by a
  `sqlite3.set_authorizer` that refuses every write to every table but `commands` — so the
  scope limit is enforced by the database rather than by discipline — and spec 17's reader stays
  `mode=ro`. `close_all` is confirmed by a step that restates the action **by its own name**;
  the button still reads `Close all positions` throughout. The response says the command was
  *recorded*, never that the mode changed.

## Three properties of the criteria worth carrying forward

In full in `docs/build-log/phase-0/c-interface.md`. Here because each is invisible from the code
and a later "simplification" would break the gate without saying so.

- **`seed_fixtures_present` derives all six fixtures from SQL and *then* cross-checks B's
  `SeedFixtures` accessor,** failing on a disagreement and naming both numbers. Asserting on the
  accessor alone cannot catch the case the gate exists for — `consecutive_data_block_run.length`
  reporting 18 while `block_records` holds three rows is exactly the defect, and it PASSes. The
  cost is real coupling to six documented column names: a schema change moves this criterion.
- **A tick is `(run_id, cycle_id)`, never `cycle_id` alone.** The counter keys every tick on the
  pair, orders strictly by `ts` with `rowid` as a tiebreak, and counts a tick once no matter how
  many guards blocked on it. B's seed deliberately reuses `cycle_id` values across two runs, so
  grouping by `cycle_id` collapses overlapping ticks, under-counts an 18-tick outage run, and
  reports a FAIL that is a bug in my query.
- **The word-boundary rule in `docs_vocabulary` is load-bearing in three separate places.** A
  plain substring scan FAILs the current tree three times over, all false:
  `paper.starting_balance` is a prefix of the live `paper.starting_balances`, and `eight` is a
  substring of "weight", "Weight" and "eighth". `term_pattern()` applies the boundary only where
  the term itself begins or ends in a word character, so `state["system_mode"]` gets a leading
  boundary and no trailing one.

## In Progress

- Nothing. Specs 33 and 32 are both complete and self-tested; the four checks are below.
- All nine of my Phase 1 specs — 16, 17, 18, 19, 20, 21, 22, 23, 24 — are complete and
  self-tested, and `scripts/verify.py --phase 1` reports **9 PASS, 0 FAIL, 0 PENDING**.
- **Two test modules that spec 19-22 docstrings claimed and did not have** are now written.
  `console/payloads.py` said `tests/console/test_payloads.py` asserts no JSON float anywhere in
  an encoded body, and `_shap_payload` said `tests/console/test_research.py` fails on a `rows`
  or `chart` key. Neither file existed — the IDE crash landed between writing the module and
  writing its tests. Both exist now and assert what was claimed.

## Blocked On

- Not blocked. Nothing in Phase 1 is waiting on another agent.
- The Running/Frozen dependency below is **answered**: the operator ruled on 2026-09-09 that the
  fix lands in Phase 2, where the command reader in `core/` that already owns
  `state["system"]["mode"]` also persists it and the console reads it as a fact. The State field
  renders the two idle readings for Phase 1 and `tests/console/test_reader.py` asserts it never
  leaves that tuple, so the deferral is enforced by the suite rather than remembered.

## Open Questions

### Phase 4 — one open, for the lead

- **Nothing persists engine 7 `scout`'s scan tally, so spec 57 step 3 cannot be done.**
  Engine 7 publishes `scanned`, `pairs` (from which `entered` derives) and a per-reason
  `excluded` tally into `state["scout"]`, where they live for one tick. The console is a
  separate process reading SQLite and never sees `state`, and **no column in any table holds
  any of those three numbers.** Engine 19 can only write what the schema has room for, so the
  empty state still says the counts are not recorded.

  I have not invented a place to put them. Three options, and the choice is a schema decision:

  1. **`rejections.details` as JSON, one row per tick.** No schema change. But a rejection is
     one *candidate* and the tally is a fact about the *tick*, so it puts a tick-level fact in
     a candidate-level table and anyone counting refused trades would count it.
  2. **One `rejections` row per excluded pair.** More defensible than it first looks: engine 7
     is a gate, an excluded pair is a refused candidate, and B asked me to map all six of its
     per-exclusion codes into `REASON_PROSE` in Phase 3 — which only makes sense if those codes
     were meant to reach this table. It reconstructs `scanned` but **not** `entered`, and it
     writes tens of rows per tick.
  3. **A column or a small table.** The lead's approval and B's edit.

  **What I did do**, because spec 57 puts it in scope: the line was factually wrong and is now
  right. It said the universe filter was engine 4 and its counts arrived in Phase 2 — it is
  engine 7 and it shipped in Phase 3, so the console was telling an operator to wait for
  something already built. The stage still shows no count and still refuses to show a zero,
  because a zero there reads as "no pair qualified", which is a result, when the truth is that
  nobody wrote the number down.

### Phase 0 — both resolved

- **Config key names for the `safety` thresholds.** The lead fixed the names and the operator
  supplied the values on 2026-09-08. `seed_fixtures_present` reads them and asserts the seed is
  past each one; it no longer reports PENDING on a missing key.
- **`docs_vocabulary` FAILing on a legitimate sentence.** The bare term `eight` retired the word
  everywhere, including `progress-tracker.md:76` where it counted config values, not engines. I
  did not edit the context file to make my own check pass — spec 02 forbids it — and sent it to
  the lead with both readings. **The lead fixed the class, not the instance:** the retired-term
  table gained a qualifier column, and the row now reads ``eight`` qualified by `machine
  learning`, `non-ML` or `engines`. The parser reads that column as data, so no term-specific
  rule entered the checker.

### Phase 1 — three raised at the spec-18 checkpoint; one now answered

Full accounts in `docs/build-log/phase-1/c-interface.md`. All three are for the lead and the
operator; none is blocking the work I have done, and I have not acted on any of them.

**The second — Running versus Frozen — was answered on 2026-09-09 and is left below verbatim
rather than deleted, because the reasoning behind the rejected option is the part that matters
later.** The operator chose neither of my two options as stated: the fix lands in **Phase 2**,
where the command reader in `core/` that already owns `state["system"]["mode"]` also persists it
and the console reads the mode as a fact. Deriving it from the claimed-`commands` trail was
rejected outright — a transition that leaves no claimed row makes the band confidently wrong,
and for the one element whose job is to answer *is this safe*, silent beats wrong. The Phase 1
console renders the two idle readings and nothing else, and the suite enforces that.

- **`runs.run_id` is UNIQUE, so the "two `run_id`s match" state cannot exist.** Spec 16 asks
  `console_restart_banner` to assert plain `Idle` "when the two `run_id`s match", and
  `ui-context.md` describes the same comparison as "the current `run_id` and the `run_id` of the
  previous row". `db/migrations/0001_initial.sql` declares `run_id TEXT NOT NULL UNIQUE`, so no
  database can ever hold two rows carrying the same value — two rows always differ, and the only
  row without a predecessor is the first ever run. The comparison the operator actually meets is
  a **presence** test, not a value test: no previous row means a system waiting to be started;
  a previous row means a system that stopped on its own. My criterion and my reader both
  implement the presence rule, and the criterion reduces the database to one `runs` row for its
  negative half. **What I am asking for:** the wording in spec 16 and in `ui-context.md` to say
  "a previous run exists" rather than "the `run_id`s differ". Both files are the lead's; I have
  not touched either. No code change follows from the answer — the behaviour is already right.

- **The console cannot tell Running from Frozen, and no store read exists that would let it.**
  The status band has a State field. `ui-context.md` fixes the two idle readings — `Idle` and
  `Idle — restarted, not trading` — but the daemon also has `running` and `frozen`, and nothing
  the console can read distinguishes them. Mode lives only in `state["system"]` in the daemon's
  memory; a daemon always starts `idle` and only reaches `running` through an `activate` command;
  `runs.mode` is paper/live/replay, which is a different thing entirely. I rendered the two idle
  readings and stopped rather than guess. Two ways out, and both cost something:

  1. **Derive it from the `commands` table, scoped to the current run.** The one trace a running
     daemon leaves is the command row it claimed: `claim_command` stamps `claimed_at` and
     `claimed_by_run_id`. If the console could read the most recent command claimed by the latest
     `run_id`, it could say that the last effect this run applied was an `activate` (Running) or
     a `freeze` (Frozen), and Idle when the run has claimed nothing. **Cost.** `StoreClient`
     exposes `pending_commands()` and `claimed_unconsumed_commands()` and no read for claimed
     history, so this is a new method in `clients/store/client.py` and `contracts.py` — B's
     directory, therefore a small task for B and a change to a phase that was planned with one
     teammate. It also needs an index: `commands` is indexed on `created_at` for the pending and
     unconsumed partials only, and nothing indexes `claimed_by_run_id`. And it is *inference*,
     not fact — the console would reconstruct a mode from a command history rather than read the
     mode itself, so it is only ever as correct as the assumption that every mode transition
     leaves a claimed command row. Any transition that does not — and I cannot prove from here
     that none exists — makes the band confidently wrong, which is worse than the band being
     silent.
  2. **Have the daemon persist the mode where the console can read it.** `state["system"]["mode"]`
     is written in exactly one place, the command reader in `core/`; that writer would also write
     the value to the store, on a column of the current `runs` row or a small single-row state
     table. The console then reads the mode as a fact and the band is right by construction, with
     no inference and no new index. **Cost.** It is the more invasive of the two by a distance: a
     schema change, which is a migration through B under rule 4 plus the lead's approval, *and*
     an edit in `core/`, which is lead-only under rule 2. It also puts a store write on the
     daemon's mode transition, and a write that fails or lags leaves the console showing a mode
     the daemon has already left — a smaller failure than option 1's, since it is staleness
     rather than a wrong reading, but it is not free either.

  **What I am asking for:** which of the two, or an instruction to leave the State field showing
  only the idle readings for Phase 1 and defer the rest. I have not opened B's directory, have
  not proposed a schema change, and have not invented a third reading. This reaches the operator
  at the spec 18 checkpoint deliberately, rather than being discovered inside spec 19, which is
  the screen that would otherwise have had to guess.

- **The cycle feed full-scans `block_records` because it cannot anchor its window on the clock.**
  `StoreClient.block_records_in_window` takes an explicit `start_ts`/`end_ts`, and the obvious
  window — the last N hours from the injected clock — returns nothing at all against B's seed,
  whose timestamps are fixed constants with no relationship to wall time. The feed rendered empty
  and read as a bug in the screen. My reader therefore asks for the full `ts` range and does the
  ordering and limiting itself, which is correct against seeded and live data alike and keeps
  `ts` as the ordering key that `architecture-context.md` requires. **Cost:** one full scan of
  `block_records` per feed render. That is fine at Phase 1 volumes, where the table is a seed,
  and it is not fine once engine 19 `memory` is writing a block record per tick per guard in
  Phase 4. **What would replace it:** a most-recent-N read on B's surface — `block_records`
  ordered by `ts` descending with a limit, no window at all — which is a new method in
  `clients/store/client.py` and so B's to write, not mine to reach across for. Not urgent; the
  right time is whenever B next has work on the store client, and before Phase 4 fills the table.

### Phase 1 — two more, opened while building 23 and 24

- **`StoreClient` does not expose the command reader the orchestrator calls, so no daemon wired
  to the real store would read a command at all.** `Orchestrator._consume_commands` reaches for
  `store.claim_pending_commands(run_id=..., now=...)` and
  `store.mark_command_consumed(command, now=...)`. `StoreClient` has `pending_commands()`,
  `claim_command(command_id, *, claimed_at, run_id)` and
  `mark_command_consumed(command_id, *, consumed_at)` — different names, different shapes. The
  only implementation of the orchestrator's shape anywhere in the repository is a test double in
  `tests/core/test_orchestrator.py`. The orchestrator reaches for them through `getattr` and, on
  finding neither, logs `commands_skipped` at debug level and continues, so the failure is
  silent. **This does not affect Phase 1** — the console writes the row and the row is correct,
  which is all spec 24 asks — and `tests/console/test_commands.py` proves the round trip through
  the real reader across a thin adapter that does nothing but rename. **It affects Phase 2**,
  which is the first phase where a daemon runs and therefore the first phase where a command
  the operator presses has to reach it. **What I am asking for:** a decision on which side the
  rename belongs — two new methods on `StoreClient` (B's file) or an adapter in `core/` (the
  lead's). I have edited neither and have not proposed a schema change; no column is missing and
  no migration is involved.

- **Widening the toolchain gate beyond `src/`, carried forward from Phase 0 and now due.** The
  lead deferred it to Phase 1 deliberately as a phase-boundary decision, and Phase 1 is now at
  its boundary. Unchanged since it was recorded: `mypy --strict scripts/` reports 2 errors in
  `verify.py` and `ruff check tests/` reports 3 — the 2 already recorded plus `RUF001` on
  `tests/console/test_format.py:25`, where the constant `U2212 = "−"` **must** be the U+2212
  glyph, because it is the fixture that would otherwise start passing on a pasted hyphen. That
  third one argues the widening needs a `noqa` policy alongside it rather than being a
  straight switch. Related and separate: **`toolchain_green` is registered for Phase 0 only, so
  from Phase 1 onward the phase gate does not run the tests at all** — a suite can be red while
  `--phase 1` reports 0 FAIL, which is exactly what happened on the tree this session picked up.
  I have not changed the registration; the lead is raising it with the operator.

## Escalations To Lead — both resolved

- **No YAML library in the architecture stack table.** Resolved: `pyyaml` was added to the table.
- **Entry-point shapes in `core/`, `bootstrap.py` and `cli/research.py`.** Resolved: the lead and
  A agreed the surface I proposed — module-level `GUARD_CHAIN`, `OPPORTUNITY_CHAIN`,
  `MANAGE_CHAIN`, an `Orchestrator` with a single-tick method, and `OFFLINE_CHAIN` in
  `cli/research.py`. Both criteria now report PASS against the real code.

## Known issues in my code

1. **`toolchain_green` is not deterministic. Closed as a known risk, not root-caused.** It fails
   on roughly 20% of runs — my own 6-of-20 was a small sample — because the pytest subprocess
   dies of a native memory fault, always inside B's seed write path at pydantic `model_dump`.
   Every test passes when the process survives. Ruled out: pyarrow, `pytest-asyncio`, test
   ordering, my own `root_import_path` — that swapper does create a second `PositionRow` class
   while instances of the first are live, but 40 enter/exit cycles hammering `model_dump` across
   both do not crash, and `test_seed.py` alone still fails 1 in 15 without ever touching it —
   and the pydantic-core version, which was my proposed next step and did not settle it. The
   turbo-clock test was inconclusive because the power plan overrode it. The remaining variable
   is hardware and it is out of scope. **Mitigated, not fixed:** the criterion now retries a
   *crash* once — a clean retry PASSes with the crash named, a second crash FAILs, and a verdict
   is never retried at any exit code. Four tests pin those boundaries. Full account in
   `docs/build-log/phase-0.md`. Do not re-run the suite to see whether the result changes.
2. **The criterion could not tell a crash from a verdict, and now can.** It compared a returncode
   against zero, so a process that printed `520 passed` and then died read exactly like a failing
   suite — which is how a memory fault gets filed as a flaky test and re-run until it goes green.
   `describe_exit()` now classifies each tool's returncode against that tool's own documented
   range (pytest 0-5, mypy and ruff 0-2), names the Windows NTSTATUS or POSIX signal, quotes the
   summary line the run had already printed, and prefixes the criterion's one line with `CRASH -`.
   Four tests cover both directions.
3. **The gate lints and type-checks `src/` only.** `mypy --strict scripts/` reports 2 errors in
   `verify.py` itself — `candidate` is bound to a `Path` in one loop and a `str` in the next, at
   the top of `_interpreter_with_toolchain` — and `ruff check tests/` reports 2 violations
   (`UP031` in `tests/core/test_contracts.py`, `SIM300` in `tests/db/test_migrations.py`). None
   is reachable by the gate that implements them. Widening `TOOLCHAIN` to cover `scripts/` and
   `tests/` is a change to what the phase gate asserts, so it is the lead's call, not mine.
   **Lead's answer: deferred to Phase 1, deliberately.** Widening the gate is a change to what
   every phase asserts and it lands better at a phase boundary than at a phase close; the four
   findings are recorded here so they are not rediscovered.
4. **A fifth site for the intermittent native fault, captured rather than shrugged off.** The
   first full-suite run of 2026-09-09's second session reported `1 failed, 640 passed`, in
   `tests/platform/test_config.py::test_a_missing_required_key_is_refused`, with
   `TypeError: object of type 'ScalarEvent' has no len()` raised out of pyyaml's own
   `parser.py:118`. That file alone then passed 82/82 and two subsequent full-suite runs passed
   641/641 and 707/707. The suite has no randomised ordering — neither `pytest-randomly` nor
   `pytest-xdist` is installed — so the same code ran in the same order three times and
   disagreed with itself once. The tracker's Known Risks entry is already re-opened and already
   records the fault inside `pydantic-core` and inside `sqlite3`'s C extension; a bogus
   `TypeError` out of pure-Python pyyaml is a third unrelated site, consistent with the
   memory-corruption reading and inconsistent with a pyyaml bug. **Full trace in
   `docs/build-log/phase-1/c-interface.md`, captured before the re-run.** Not root-caused, not
   in my paths, and the tracker entry is the lead's — escalated rather than edited.
5. **Two stale docstrings of mine, fixed.** A flagged both. `tests/conftest.py`'s `paper_config`
   still said the OPERATOR REQUIRED nulls were left as nulls; the file now carries none, all nine
   supplied. `verify.py`'s `KEY_MAX` comment said four of the five `safety` keys were written as
   null — it was three, and the same sentence wrongly implied only the error-rate window was ever
   a real value when `max_consecutive_data_blocks` was 15 from the start.

## Verification

Paste the real output of your last run. Never report a task complete without it.

Last run 2026-09-09, after specs 33 and 32. Phase 1's run is kept below it.

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
940 passed in 41.97s

$ .venv/Scripts/python.exe -m mypy --strict src/
Success: no issues found in 60 source files

$ .venv/Scripts/python.exe -m ruff check src/
All checks passed!

$ .venv/Scripts/python.exe scripts/verify.py --phase 2
PASS    docs_vocabulary                 14 files scanned, 9 retired terms, no hit
PASS    toolchain_green                 pytest, mypy --strict and ruff all green (python.exe)
PASS    commands_round_trip             real StoreClient through the real reader: activate and
                                        freeze applied and consumed on the claiming tick,
                                        close_all claimed but not consumed, and an interrupted
                                        close_all re-applied on restart and consumed only once done
PENDING recording_span_continuous       tests/fixtures/recording_report.json does not exist yet
                                        (spec 27) - <contract>
PENDING candles_match_kraken_ohlc       tests/fixtures/kraken/ohlc.json does not exist yet
                                        (spec 28) - <contract>
PENDING data_guard_blocks_bad_data      engine 4 `data_guard` does not exist yet (spec 29)
                                        - <contract>
PENDING historical_loader_reports_gaps  acsoe.research.historical does not exist yet (spec 30)
                                        - <contract>
PENDING console_shows_live_rows         no Phase 2 engine is registered in bootstrap.py yet
                                        (specs 26-29) - <contract>
PENDING console_reads_persisted_mode    the daemon left no `runs` row for its own run_id, so
                                        set_system_mode had nothing to update. The run record is
                                        written at startup by the orchestrator and that write
                                        does not exist yet - <contract>

9 criteria: 3 PASS, 0 FAIL, 6 PENDING
Phase 2 is not green: 6 PENDING. Mid-phase the bar is no FAIL, so this is expected.
```

**Re-run after the spec 33 follow-ups**, on a tree carrying A's engines 1-3 and loader and the
lead's two `core/` writes. `pytest` 1029 passed, `mypy --strict src/` clean over 65 files,
`ruff check src/` clean, `--phase 0` 7/7 and `--phase 1` 10/10 both still green:

```
$ .venv/Scripts/python.exe scripts/verify.py --phase 2
PASS    docs_vocabulary
PASS    toolchain_green
PASS    commands_round_trip
PENDING recording_span_continuous       tests/fixtures/recording_report.json does not exist yet
PASS    candles_match_kraken_ohlc       3 pairs, 9 bar(s): every OHLC field within one tick_size
                                        as AssetPairs reports it, volume within 0.1%
PENDING data_guard_blocks_bad_data      engine 4 `data_guard` does not exist yet (spec 29)
PASS    historical_loader_reports_gaps  3 gaps of 1/2/4 bars reported exactly, over 41 rows, and
                                        no timestamp in the output was absent from the input
PENDING console_shows_live_rows         no Phase 2 engine is registered in bootstrap.py yet
PASS    console_reads_persisted_mode    a real daemon applied activate then freeze through the
                                        real store, and the band followed to `Running` then
                                        `Frozen`

9 criteria: 6 PASS, 0 FAIL, 3 PENDING
```

Three criteria have gone PENDING to PASS against their real subjects without a line of mine
changing, which is what the two-sided proof was for.

Every `<contract>` above is the full expected surface, printed in the real output and elided
here only for width. The six PENDINGs are five of A's subjects and one of the lead's; none is
mine. `--phase 0` and `--phase 1` both still report every criterion PASS and zero PENDING.

### Phase 1, for the record

Last run 2026-09-09, after specs 23 and 24, on the tree carrying all nine of my Phase 1 specs.

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
707 passed in 34.30s

$ .venv/Scripts/python.exe -m mypy --strict src/
Success: no issues found in 35 source files

$ .venv/Scripts/python.exe -m ruff check src/
All checks passed!

$ .venv/Scripts/python.exe scripts/verify.py --phase 1
ACSOE verify - phase 1
repo: C:\Users\saad2\Documents\GitHub\ACSOE

PASS    docs_vocabulary                     14 files scanned, 9 retired terms, no hit
PASS    console_renders_seeded_screens      all 5 screens answered over a seeded database
PASS    console_websocket_pushes_on_change  pushed 524ms after the watermark moved, inside the 1000ms budget
PASS    console_commands_write_rows         one correct unclaimed row each for activate, freeze, close_all
PASS    console_live_frame_amber            live renders a 3px var(--live) frame and paper declares no border anywhere
PASS    console_tokens_no_raw_hex           11 hex values, all inside the src/acsoe/console/static/tokens.css token block; 12 console files scanned
PASS    console_tabular_figures             21 numeric cell(s) carry `.num`, and `.num` is the only tabular-figure rule
PASS    console_focus_and_reduced_motion    2 visible `:focus-visible` rule(s); the reduced-motion block drops the flash
PASS    console_restart_banner              a changed run_id reads the restart banner; a first start reads plain `Idle`

9 criteria: 9 PASS, 0 FAIL, 0 PENDING
Phase 1 is green: every criterion PASS, zero PENDING.
```

**This meets the phase-close bar for my nine specs**, which is every criterion PASS and zero
PENDING. Whether Phase 1 is *marked* green is the lead's call after review, not mine, and I have
not touched `context/progress-tracker.md`.

The suite grew from 641 to 707 in this session: 66 new tests across
`tests/console/test_payloads.py`, `test_research.py`, `test_websocket.py` and
`test_commands.py`, plus the widened assertions in `test_app.py` and `test_page.py`. Two of the
641 were failing on the tree I picked up and are fixed; see the entries in the build log.

## Two properties of the Phase 2 criteria worth carrying forward

Same shape as the three carried out of Phase 0: invisible from the code, and a later
"simplification" would break the gate without saying so.

- **Fabricate the subject a criterion judges; never fabricate a contract the criterion is held
  to.** `data_guard_blocks_bad_data` passed both halves of its two-sided proof over a body that
  could not run, because the test module had hand-written an `acsoe.core.contracts` that agreed
  with the mistake in `_guard_context`. `use_real_core()` now copies the real `src/acsoe/core/`
  into every fabricated tree that needs `EngineContext` or `Chains`. A two-sided proof is only
  worth what its fabricated subject is worth.
- **`root_import_path` re-imports every `acsoe` module for each criterion**, so a module-level
  fixture is rebuilt from source on every run. Cross-run contamination between criteria is
  therefore impossible, and a regression test written on that assumption passes against the
  defect it was meant to catch — mine did. The leak that *is* reachable is within one run, to
  the next thing the criterion does.
- **A test asserting a subject is *absent* decays silently as teammates build.**
  `tree_with_harness` carries no `src/`, so `root_import_path` does not shadow the editable
  install and a criterion asking for an unbuilt module finds the real one. Every "PENDING on an
  absent subject" test now calls `shadow_real_package()`. `test_candles_are_pending_with_a_
  fixture_and_no_builder` went red hours after it was written, with nothing of mine changed,
  the moment A landed engine 3.

## Open Questions — Phase 2

- **RESOLVED, same day.** The lead landed both writes and `console_reads_persisted_mode` is
  **PASS**: a real daemon applies activate then freeze through the real store and the band
  follows to `Running` then `Frozen`, with no double anywhere in the seam. Spec 32's reader is
  now proven end to end rather than only against a fabricated subject. The question is left
  below verbatim, because the *second* half of it — the missing run record — was not in B's note
  or in the spec, and the reasoning for why it is upstream of the mode write is the part worth
  keeping.

- **`console_reads_persisted_mode` was blocked on two writes in `core/`, not one.** Spec 31 gave
  the store `set_system_mode(run_id, mode, *, at)` and B's note to the lead names the first: the
  command reader must call it after applying each transition. There is a second, and it is
  upstream of it. **The orchestrator writes no `runs` row at all.** `ownership.md`'s seam table
  says the run record is "written at startup" by the lead's orchestrator, and `Orchestrator`
  mints `run_id` onto the context and never stores it. `set_system_mode` returns `False` for an
  unknown `run_id`, so even once the reader calls it there is no row to update, and the console —
  which reads the latest `runs` row to decide what the current run is — would keep rendering the
  previous process. My criterion reports these as two distinct PENDINGs with different messages
  and never as a FAIL, because neither is mine. **What I am asking for:** both writes, in the
  order run-record-then-mode. No console change follows from either; spec 32 is complete and its
  reader is already correct against a database that has them.

- **`toolchain_green` still lints and type-checks `src/` only.** Carried from the Phase 0 and
  Phase 1 boundaries and now due for the third time. `ruff check scripts/verify.py` reports 5
  findings and `mypy --strict scripts/` reports 2, none reachable by the gate that implements
  them. Two of the five are mine and old (`UP041` on `asyncio.TimeoutError`); one is a legitimate
  `RUF001` on the U+2212 glyph in a comment, which is the case the `noqa` policy exists for. The
  widening is a change to what every phase asserts, so it stays the lead's call. Unchanged
  otherwise.

## Notes For Next Session

- Recorder line schema received from A and pinned: seven outer keys, `kind` in
  `{tick, gap, session}`, `_recorder` channel on markers.
- Do not generate Python through a shell heredoc on this machine. Backslashes in the body are
  not literal even with a quoted delimiter: a `\b` written into a regex arrived as a raw
  backspace byte, and `\n` inside a test string arrived as a real newline and broke the file.
  Use a direct file write for anything containing escapes.
- The heredoc hazard above bit again this session, in the other direction: a Windows path
  written into a heredoc'd Python string raised
  `SyntaxError: (unicode error) 'unicodeescape' codec can't decode bytes ... truncated \UXXXXXXXX
  escape`, because the path segment reached Python as a literal backslash-U. Same rule, wider
  than the note said: **write the script to a file first.** It applies to any backslash, not
  only to regex escapes.
- Phase 1's console surface is now complete and `tests/console/test_app.py` asserts the route
  set exhaustively. From here that assertion changes meaning — it stops tracking progress and
  starts guarding the surface, so a Phase 2 route has to be added there deliberately.
- **A docstring that names a test is not evidence of one.** Three instances now, all from a
  session killed between writing a module and writing its tests, and all three found only
  because someone went looking for the test by name. The third — `views.IDLE_READINGS`
  claiming the suite enforced the Running/Frozen deferral — survived a phase close. Grep for
  the test module or symbol at the point the docstring is written.
- **A cleanup that cannot fail is a cleanup nobody can see fail.** `console_workspace`'s
  `ignore_errors=True` was right about not turning a leaked directory into a FAIL and wrong
  about saying nothing, and it silently filled a 923GB disk. The visible leak, in
  `tests/harness/doubles.py`, was two orders of magnitude smaller and was fixed first
  *because* it printed something. Anything defensive here should be designed for the leak that
  cannot be seen: ask whether the directory is gone, do not just try to remove it.
- **The console has two SQLite connections and the ASGI lifespan never runs in a criterion.**
  `close_console` must close `reader` **and** `command_writer`; `CONSOLE_CONNECTION_ATTRS` is
  the list, and a third connection added to `app.state` has to go in it.
