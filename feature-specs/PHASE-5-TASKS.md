# Phase 5 — shared task list

## HANDOFF — session closed by the operator 2026-09-13 ~03:00. Read this first.

**Phase 5 is in progress, not closed.** Phase 4 is green on its gate (10/10, re-verified at
the Phase 5 preflight) with its close and consolidation still withheld by the operator.

### The nineteen specs

| State | Specs |
|---|---|
| **Done, committed, four gates green at the time** | 59 (rulings into the documents, lead), 61 (config fields, dependencies, models root, research runner, A-2), 62 (store surface for artefacts, B-2), 63 (`modelling/` package, C-2), 76 (engine 7 ranking by a named feature, B-2) |
| **In flight, half-finished, uncommitted** | 60: only the helper block exists in `scripts/verify.py` (constants and helpers before the Registration banner, no criterion, no `register` call), so `--phase 5` still registers only `docs_vocabulary` and `toolchain_green` and can print green over a phase with real code in it. C-2 was told to build 60 before 64 and had not yet. 64: `src/acsoe/engines/feature/` landed untracked with one ruff finding (`engine.py:123 SIM300`); B-2's seam test in `test_scout.py` passes against it. See C-2's progress file for the exact state. |
| **Untouched** | 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75 (all C-2), 77 (lead) |
| **Lead's YAML half of 61 still open** | A `training` section (`num_trees`, `learning_rate`, `num_leaves`, `min_data_in_leaf`) was requested of A-2 at 02:15 for the LightGBM hyperparameters; field first, then the lead pastes the YAML. Not started as far as the lead knows; A-2's progress file says. |

### The nine rulings, all confirmed by the operator 2026-09-12 (spec 59, tracker Locked Decisions)

1. Engine 20 `tournament` is Phase 5 work. 2. `src/acsoe/modelling/` is a C-owned leaf package both sides import. 3. Engine 8 blocks on a DI refusal (`di_refused`), stays a non-gate. 4. Metric: Brier vs base-rate Brier per fold, log loss, BUY-call target rate vs break-even; accuracy never computed (retired term). 5. Uniqueness weights; effective sample size **per fold beside that fold's row count** (operator addition). 6. DI reference = predictor's training rows, per pair the last `di_window_days`, mean k-NN distance, percentile of the leave-one-out distribution, refitted weekly. 7. `scout.rank_feature` is ruled after spec 75's study; alphabetical meanwhile, engine publishes null. 8. lightgbm, scikit-learn, shap in the base install. 9. Three thresholds absent until the operator supplies them after the walk-forward reports.

### Deliberately absent from `config/default.yaml`, and must stay absent (never `null`)

`prediction.di_percentile`, `anomaly.threshold_percentile`, `skeptic.veto_threshold` (the
operator's, after the walk-forward reports; engines 8, 13, 15 fail closed meanwhile);
`models.prediction_run_id`, `models.anomaly_run_id`, `models.skeptic_run_id` (no artefact on
a fresh clone); `scout.rank_feature` (after spec 75). A `null` for any of them stops every
process at load; absent reads as `None`.

### What the next session would otherwise rediscover

- **The lead-side rulings log and channel below** hold every ruling made after spec 59,
  including: `StoreClient(db_path, *, models_dir=None)`; `new_model_run_dir` creates a missing
  root, `model_run_dir` refuses one; `follow_imports_for_stubs = true` is why mypy checks
  numpy-importing code (a 3.12 ruling was made and withdrawn); `macro.btc.live` is `BTC/USD`
  because the real recorder writes it; `TournamentEngine(*, digest_path: Path | None = None)`
  resolved by name in `cli/research.py`; `rank_universe(pairs, *, features, feature,
  descending)`; an unfilled lookback is `null` in `state["feature"]`, never NaN; identity
  proofs recompute both candidate sets; no unique index on `leaderboard` this phase;
  `candles_sample.parquet` is the feature fixture and its one hole is load-bearing; restore
  mutations from a byte copy, never `git checkout`.
- **Agent teams and this runtime.** A teammate that reports a usage-limit failure at spawn is
  not dead: it resumes when the limit resets. Spawning a replacement under the same name
  produced two writers per lane; sends by name reached the wrong session and resurrected
  stopped ones; `TaskStop` by name is what works. **Next session: spawn teammates under
  names never used in this project before, check `ListAgents` before and after, and expect
  to communicate through this file.** The whole incident is in `docs/build-log/phase-5/lead.md`.
- **Commits.** Lead commits only; every commit this session ran the lane's tests to a file
  and checked the exit code (one did not, and the entry says so). Latest commit hash is in the
  lead's final report and `git log`.
- **The full-archive `acsoe research` run is a finding, not just a run.** A-2 started it
  over the committed 859,248-bar archive (three pairs): at 33 minutes it held **39.6 GB
  resident and climbing**, CPU-bound, nothing failed. A-2 measured the single-pair path and
  found it linear (about 0.44 ms and 3 KB per bar, controlled by running the comparison in
  reverse order), which projects to six minutes and 2.5 GB, so the divergence is in the
  multi-pair path: the merged replay stream across pairs, or the accumulation of every labelled
  row before one parquet write, with most of the memory outside Python's allocator (polars and
  arrow buffers). A-2 did not widen spec 61 to fix it. **It must be fixed before spec 67**,
  because the dataset every model trains on comes out of this command, and on a machine
  smaller than this one's 96 GB the failure is a killed process, not a message. Open it as its
  own A spec (`research/replay.py` and `research/backtest.py`, A's). A-2's measurement harness
  is in its scratchpad, not the repo. The process (PID 42016 at the time) was still running
  when the session closed; A-2 was refused permission to stop it and the lead did not kill it
  either; the operator may.

---

**STATUS: APPROVED 2026-09-12 AND STARTED.** All nine questions at the bottom of this file
were confirmed as proposed, with two amendments: the three operator values (question 7) are
supplied **after** the walk-forward reports, not now; and spec 67 reports the effective sample
size **per fold beside that fold's row count**, not only in aggregate. Team formed: A, B, C
and the lead.

> **NOTICE, 2026-09-13 00:58, superseding the one it replaces.** The three original sessions
> (`A`, `B`, `C`), revived by the usage-limit reset, were stopped mechanically at 00:57 after
> stand-down messages failed to reach them; `ListAgents` now shows only `A-2`, `B-2` and
> `C-2`. **The `-2` set owns every lane and is the only writer in it.** Everything the
> originals wrote is kept and owned by the `-2` session of that lane. The incident is in
> `docs/build-log/phase-5/lead.md`.

## Rulings log — read before every spec step; messages have been misdelivered

Every lead ruling of the phase, in order, because sends addressed to `A-2`, `B-2` and `C-2`
have reached the stopped originals instead and nobody can see a misdelivery. **Never send
to `A`, `B` or `C`: a send to a stopped session's name resurrects it.** Teammates are `A-2`,
`B-2`, `C-2`; the lead is `main`.

1. **Lanes.** `A-2` owns spec 61 entire. `B-2` owns 62 and 76. `C-2` owns 60 and 63 to 75.
   Everything the stopped originals wrote is kept and owned by the `-2` session of that lane.
2. **`StoreClient(db_path, *, models_dir=None)`**, keyword-only. `model_run_dir` refuses a
   missing artefact root; `new_model_run_dir` creates one (the trainer runs outside A's startup)
   and refuses an existing run directory atomically via `mkdir(exist_ok=False)`.
3. **SUPERSEDED, 01:40: mypy stays at `python_version = "3.11"`.** A-2 found the fourth
   option: `follow_imports_for_stubs = true` on the numpy-and-polars override, one line, no
   version change, no pin, no venv change; `mypy --strict src/ scripts/` is back to
   *"Success: no issues found in 106 source files"* (lead verified). The 3.12 ruling is
   withdrawn; do not add a 3.12 probe or a ruff-target test for it.
4. **`macro.btc.live` is `BTC/USD`**, which is what the real recorder writes
   (`tests/fixtures/record_sample.jsonl` and `data/raw/`); `XBT/USD` is the stale remembered
   naming; `XBTUSD` survives only as the archive filename.
5. **`TournamentEngine(*, digest_path: Path | None = None)`**, so `build_offline_chain()` stays
   constructible with no arguments by `is_gate_matches_registry`.
6. **Spec 60 criteria 1 and 7 and spec 67 step 10 are amended**: `candles_sample.parquet`
   (real SOLUSD OHLCVT, 1,208 rows, one deliberate hole, do not rebuild) is the feature input;
   criterion 7 is the committed digest plus a constructed series long enough for several folds.
7. **Identity proofs recompute both candidate sets** (training rows and BUY subset) and assert
   the artefact matches the first and not the second. Never a bare hash, never a row count.
8. **An unfilled lookback is `null` in `state["feature"]`, never NaN**, and `rank_universe`
   treats null, absent and NaN alike as no value, sorted after every valued pair.
9. **No unique index on `leaderboard (model_id, model_version, fold)` this phase**; recorded as
   an open question for the next schema window. `leaderboard_entries` plus engine 20's own check
   stands meanwhile.
10. **Restore a mutation from a byte copy, never `git checkout`**: a teammate's working tree is
    the only copy of its work. Now in `code-standards.md`.
11. **The verify.py Phase 5 helper block on disk (line 7853) is C-2's to keep or delete
    wholesale.** One author of the criteria from here.

## STOP ORDER, 2026-09-13 02:55 — the operator is closing the session

**Every agent: stop at your current task boundary. Start nothing new.** Then, in this order:

1. Write `context/progress/<agent>.md` now, as if the next session has never seen this one,
   because it has not: which spec you claimed, what is done, what is half-done and in which
   files, what you were about to do next, every open question.
2. Append every diagnosis you are holding to `docs/build-log/phase-5/<agent>.md`, even where
   the fix is not written. The diagnosis is the only thing an interruption can take.
3. Send `main` one message: "WOUND DOWN" plus the list of files that are green and complete
   versus half-finished, so the lead commits the first set and leaves the second uncommitted
   with your progress file saying exactly what state it is in.

Then do nothing further.

**To B-2, at wind-down.** Your spec 76 defect (a misspelt `scout.rank_feature` silently
ranking alphabetically while publishing the name; fixed by checking the name against
`state["feature"]["feature_names"]` and blocking with `scout_inputs_unavailable`; three tests,
N14 killed by the new test alone) is committed at `7a64d88`. Credit to C-2 for finding it from
the consumer side while writing criterion 9. The `row_ts` staleness demotion stays unused: a
ranking decision nobody asked for, for the operator later. The engine 5 rehearsal is **not
started** this session; the next session assigns it to one agent by name in this file.

## Messages from the lead to teammates — THIS FILE IS THE CHANNEL

**Established 01:40: a send from the lead to `A-2`, `B-2` or `C-2` is delivered to the
stopped original of that lane and resurrects it; the `-2` sessions receive nothing from the
lead by message.** Your sends to `main` do arrive. So: the lead answers here, dated, under
your name. **Re-read this section every time you send to `main` and before every spec step.**
Do not wait for a reply by message; it will not come. The lead has stopped sending to your
names for exactly this reason.

**To A-2, 01:40.** Your `follow_imports_for_stubs` fix is accepted and supersedes the lead's
3.12 ruling; the lead has verified 106 files checked. Step 2 (that line plus the dependency
move, both on disk) is being committed now. You own steps 3 and 4 and the whole lane; the
surviving test block is the one to keep. The original A's pin advice and the lead's own
"land 3.12 first" note are both void. Your macro spelling doubt: `BTC/USD` is what the real
recorder writes (`tests/fixtures/record_sample.jsonl`, `data/raw/`); keep it. Report step 3
and step 4 to `main` as they land; the answer will be here.

**To B-2, 01:40.** Lane B is yours alone; specs 62 and 76 are committed at `16c5685`. Re-run
M2 and M8 yourself against the current `_artefact_root`; the original B is stopped for good.
NaN as no value: accepted. The unique index on `(model_id, model_version, fold)`: deferred to
the next schema window (Phase 6), recorded. Fix the two `RUF043` findings if not yet done, run
the four gates once `toolchain_green` is clean, and mark both specs complete in your progress
file. Then stay available for the two-tick rehearsal when C-2's engines exist; the request
will appear here.

**To B-2, 01:52.** Your final report is received: both specs done, 24 mutations killed, your
paths green. The two answers you are still asking for are in the two paragraphs above and in
rulings 1 and 9: lane B is yours alone, and the unique index is deferred to the next schema
window. Mark 62 and 76 complete in your progress file now; the four-gate bar was met on your
last run except for A-2's mid-save import, which is A-2's. Nothing more is asked of you until
C-2's engines exist; the rehearsal request will appear here.

**To C-2, 02:45, a seam catch from the stopped original B.** You told a B session that
criterion 9 (`scout_ranks_by_feature_not_arrival`) will call
`rank_universe(..., rank_feature=...)`. The function on disk and committed at `16c5685` is
`rank_universe(pairs, *, features, feature, descending)`, spec 76's own wording; the config
key is `scout.rank_feature`, the parameter is `feature`. The criterion must import the real
`acsoe.engines.scout.contracts` and call that signature; if it raises `TypeError`, the
criterion is wrong, not the module, and a criterion that catches it and reports PENDING would
be the Phase 4 labeller failure again (a signature agreed by message, a module under another
name, everything green against a double). Read `engines/scout/contracts.py` before writing
criterion 9; do not agree signatures by message with anyone, read the file.

**To A-2, 02:35.** Spec 61 is accepted in full and steps 3 and 4 are committed. Two answers
you have asked for twice, both here since 01:40: (1) `BTC/USD` is deliberate and it is what
the real stream writes, measured, not remembered: `tests/fixtures/record_sample.jsonl` carries
`"symbol":"BTC/USD"` and `"ETH/USD"`, and the newest file in `data/raw/` carries BTC/USD,
ETH/USD, EUR/USD, HYPE/USD, NEAR/USD. `XBT/USD` is the stale naming AGENTS.md warns about;
`XBTUSD` survives only as the archive filename. Keep it. (2) One more small section for spec
61, requested at 02:15 above: `training` with `num_trees`, `learning_rate`, `num_leaves`,
`min_data_in_leaf`. Field first, message `main`, the lead pastes. Report the full-archive
`acsoe research` result when it lands. The rehearsal request will appear here when C-2's
engines exist; engine 5 already does, so the first two-tick rehearsal (engine 5 alone, PASS on
a non-bar tick and a feature row on a bar tick, against the real orchestrator and the fake
client) can start now if you want it; B-2 has the same offer.

**To B-2, 02:25.** Received: 62 and 76 complete, 24 of 24 killed, the stopped original's six
agreeing on every overlap. Your CRLF correction is accepted: the `git diff` warning fires the
first time an already-CRLF working file appears in a diff and says nothing about the edit,
136 tracked files are CRLF in this tree from before this session, and your sha256 check of
every committed fixture against its blob is the check that matters; the lead's note to you
was wrong and is withdrawn. Stand by for the rehearsal request here.

**To A-2, 02:25, relayed from B-2.** Final signature `StoreClient(db_path, *, models_dir=None)`;
the client creates a missing `models/` in the writer only, so keep creating it at startup and
keep passing `models_dir` from both `cli/engine.py` and `cli/research.py`.

**To C-2, 02:25, relayed from B-2.** `leaderboard_entries(model_id=, model_version=, fold=)`
is on the client for engine 20's idempotency check, unlimited, null fold matched with `IS`.
And the one thing failing `--phase 5` at 02:20 is yours:
`src/acsoe/engines/feature/engine.py:123 SIM300 Yoda condition`. Also noted with thanks:
B-2's engine 5 seam test went from skipped to passing the moment your engine landed, with no
edit, which is the no-double rule paying out.

**To C-2, 02:15.** Spec 63 is accepted and committed. Two things before spec 64. (1) The
"two C instances" question has been answered here since 01:40 and in rulings 1 and 11: the
original C is stopped; you own `scripts/verify.py`; **build spec 60 next, before 64**, because
`--phase 5` registering two criteria over a phase with real code in it is the exact false
green spec 60 exists to stop, and every later spec's four-gate claim needs its criterion to
exist. Keep or delete the helper block on disk wholesale. (2) LightGBM hyperparameters are
**config keys, not module constants**: a run must be reproducible from its config plus its
data, and a tree count in a constant is a number the manifest cannot prove. A-2 adds a
`training` section (`num_trees`, `learning_rate`, `num_leaves`, `min_data_in_leaf`, all
plumbing the lead chooses) and the lead pastes the YAML; read them through `load_config` and
write them into the manifest. Until the section lands, read them from config with a clear
`MissingSettingError` rather than a default, the way `walkforward.read_settings` does.

**To A-2, 02:15.** One more config section for spec 61, small: `training` with
`num_trees: int > 0`, `learning_rate: Ratio in (0, 1)`, `num_leaves: int > 1`,
`min_data_in_leaf: int > 0`, `extra="forbid"`, required once the YAML lands. Field first,
message `main`, the lead pastes. Then steps 3 and 4 as planned.

**To C-2, 02:05.** The `RUF100` at verify.py:8025 was removed by the stopped original C
(resurrected by a misdelivered message, then stopped again); the directive is gone and the
reasoning kept as a plain comment, ruff is clean. Do not redo it; do still narrow the
`except Exception` on that line as asked below. Seam confirmation for spec 74: A-2 registers
engine 20 in `cli/research.py` by resolving `TournamentEngine` by name at chain-build time and
passing `digest_path=...`, with a `RuntimeError` naming the seam if the class or the keyword is
absent. Your constructor must therefore be exactly `TournamentEngine(*, digest_path: Path |
None = None)` (ruling 5). A-2's messages to you are landing in the stopped C's mailbox; A-2
has been told to route through `main`, and the lead relays here.

**To A-2, 02:05.** Your message to `C-2` about the RUF100 and the seam was delivered to the
stopped original C, which then fixed the lint itself. Do not send to `C-2`; send to `main` and
the lead relays in this file. Your engine 20 resolution-by-name with the RuntimeError tripwire
is accepted; the seam line is in C-2's note above.

**To C-2, 01:40.** You continue spec 60 from the verify.py section on disk; the original C is
stopped for good. The single `toolchain_green` failure in the tree right now is yours:
`scripts/verify.py:8025 RUF100 Unused noqa directive (non-enabled: BLE001)`. Fix it, and look
at the same line: `except Exception` there catches `ConfigKeyError` for an absent key **and**
any other failure in the config walk, answering both with `None`, so a criterion that should
report PENDING naming a key would wait forever on a genuine error. Catch the absent-key case
by its own type. mypy is checking again (A-2's fix), so `mypy --strict src/ scripts/` is
usable as written. Engine 5 publishes `null`, never NaN, for an unfilled lookback (ruling 8).
Report each spec to `main`; the answer will be here.

Lead-owned. Teammates do not edit this file: **claim by recording the spec number in your own
`context/progress/<agent>.md` before writing code**, per ownership rule 5.

`SendMessage` is the coordination channel. Talk to each other directly.

## The rule this phase is governed by, and it outranks the schedule

Every phase so far failed loudly. **Phase 5 fails quietly.** A subtly wrong walk-forward, a
leaked feature, a metric that flatters, a DI fitted on the wrong rows: each produces a model
that looks excellent and is worthless, and nothing goes red. The cost is not a bad session; it
is a result nobody can trust and no way to tell.

**Every assertion must be proven capable of failing, and the proof goes in the build log.**
Write the assertion, break the thing it tests, record that it went red, then fix it. A claim
that an assertion works is not evidence. Phase 4's own new criterion used a label window
exactly equal to the embargo, so a splitter with its purge deleted still passed on the
embargo's back; it was caught by trying to break it, not by reading it.

Four traps, each of which has already produced a defect in this codebase:

1. **The DI is fitted on the predictor's training set, never the skeptic's subset.** Prove
   which rows it saw, by identity. Spec 68.
2. **The walk-forward is past-only.** `walkforward_trains_on_the_past_only` is re-registered
   under phase 5. If a Phase 5 change makes it red, the change is wrong. Specs 60, 67.
3. **Accuracy is a useless metric here** and is never computed. Base rate 23.89%, break-even
   about 61% at tier 1. The metric is Brier against base-rate Brier. Spec 59 decision 4.
4. **Labels overlap almost completely at a 48-bar horizon.** Rows are weighted by average
   uniqueness and the effective sample size is reported beside every row count. Spec 59
   decision 5.

And the seam the tracker named: **`rank_universe` is always handed an already-sorted
sequence.** Test it directly, on input where arrival order and intended order disagree on
every element. Spec 76.

## Headcount: four

| Agent | Specs | Count |
|---|---|---|
| **C — Interface and models** | 60 criteria, 63 `modelling/`, 64 engine 5, 65 engine 6, 66 engine 12, 67 trainer, 68 DI, 69 skeptic training, 70 anomaly training, 71 engine 8, 72 engine 13, 73 engine 15, 74 engine 20, 75 ranking study | 14 |
| **A — Platform** | 61 config fields, dependencies, models root, research runner | 1 |
| **B — Store and trading** | 62 store surface for artefacts, 76 engine 7 ranking | 2 |
| **Lead** | 59 rulings into the documents, 77 registration and verify | 2 |

Phase 5 is C-heavy the way Phase 3 was B-heavy and Phase 4 was C-heavy: ownership is
permanent and the models are C's. **No filler was invented.** A has one spec of four small
parts, each of which blocks C; B has one small spec that blocks C and one real spec that
waits on an operator ruling.

## Task table

| # | Owner | Files | Acceptance |
|---|---|---|---|
| 59 | Lead | `context/*`, `config/default.yaml` (after 61) | `docs_vocabulary` PASS with the `accuracy` row and observed FAIL; phase 4 still 10/10 |
| 60 | C | `scripts/verify.py`, `tests/verify/test_phase5_criteria.py` | Eleven criteria, each PENDING/PASS/FAIL observed; `--phase 5` not green with 0 FAIL |
| 61 | A | `platform/config.py`, `pyproject.toml`, `platform/paths.py`, `cli/engine.py`, `cli/research.py`, `tests/platform/`, `tests/cli/` | Fields refuse bad values; `acsoe research` runs engine 23 and exits 0 |
| 62 | B | `clients/store/client.py`, `tests/clients/store/` | `model_run_dir` and `new_model_run_dir` with refusals observed red |
| 63 | C | `src/acsoe/modelling/`, `tests/modelling/` | `features_reproduce_in_replay`, `feature_lookbacks_are_time_not_rows` PASS; named mutations red |
| 64 | C | `engines/feature/`, `tests/engines/test_feature.py` | PASS on a non-bar tick; features on a bar tick from engine 3's real output |
| 65 | C | `engines/macro_context/`, `tests/engines/test_macro_context.py` | `available: false` with the missing asset named |
| 66 | C | `engines/regime/`, `tests/engines/test_regime.py` | Three labels each reached by a one-input change |
| 67 | C | `research/training.py`, `tests/research/test_training.py`, `tests/fixtures/walkforward_digest.json` | `predictor_trains_and_calibrates`, `training_is_reproducible_from_config_and_data`, `walkforward_weekly_retrain_reports_oos` PASS |
| 68 | C | `research/training.py`, `modelling/di.py`, `tests/research/test_di.py` | `di_fitted_on_predictor_training_set` PASS, FAIL both ways |
| 69 | C | `research/training.py`, `tests/research/test_skeptic_training.py` | `skeptic_trains_only_on_predictor_buy_rows` PASS, FAIL both ways |
| 70 | C | `research/training.py`, `tests/research/test_anomaly_training.py` | Spike scores above threshold; label-join mutation red |
| 71 | C | `engines/prediction/`, `tests/engines/test_prediction.py` | Three block tests by reason code, one pass; `cost_gate_uses_live_fee_tier` still PASS |
| 72 | C | `engines/anomaly/`, `tests/engines/test_anomaly.py`, `console/format.py` | Block and pass differing in one input; reason codes in `REASON_PROSE` |
| 73 | C | `engines/skeptic/`, `tests/engines/test_skeptic.py`, `console/format.py` | Block and pass; not-a-BUY pass; codes in `REASON_PROSE` |
| 74 | C | `engines/tournament/`, `tests/engines/test_tournament.py` | `tournament_writes_leaderboard_from_oos` PASS; `promoted` never true |
| 75 | C | `research/training.py`, `docs/dataset/ranking-study-<date>.json` | Every feature both directions plus the alphabetical control |
| 76 | B | `engines/scout/`, `tests/engines/test_scout.py` | `scout_ranks_by_feature_not_arrival` PASS, FAIL against `tuple(pairs)` |
| 77 | Lead | `bootstrap.py`, `config/default.yaml`, tracker | 15 engines, 0 mismatches, 7 gates; phases 0 to 4 unchanged |

## Ordering

**Spec 59 and spec 60 first, from the first commit.** The rulings so nobody infers them; the
criteria so `--phase 5` stops claiming green over nothing.

**Spec 61 and 62 next and quickly.** Both are small and both block C: the config fields gate
the YAML, the store surface gates every artefact load.

**Spec 63 before any engine or trainer.** One implementation of the arithmetic; everything
else calls it.

**64, 65, 66 in parallel with 67.** The engines need `modelling/`; the trainer needs
`modelling/` and A's archive, which exists.

**67 before 68, 69, 70.** The fold loop is what they hook into. **68 before 71**, **69 before
73**, **70 before 72**: an engine loads the artefact its trainer writes.

**74 after 67**, **75 after 67 and 68**, **76 after 75 and the operator's ruling.**

**77 last**, after every engine has been driven through two real orchestrator ticks by an
agent that did not build it.

**Nobody idles.** Mock a contract you are waiting on and message its owner.

## The stop rule for gate runs

Before any baseline or comparison run, the lead asks every teammate for an explicit stop and
waits for it. An idle-looking tree is not quiescence; that cost three full gate runs in Phase
3. "Re-run the named test in isolation" is retired as a diagnostic. Redirect every gate run to
a file and read the file.

## Write your two files as you go

`context/progress/<agent>.md` before the work. `docs/build-log/phase-5/<agent>.md` **at the
moment you diagnose a problem, before you write the fix.** The diagnosis is the only part of
a fix that exists solely in your head.

**Do not consolidate the build logs and do not close the phase.** Both are the lead's, and the
operator has withheld the close.

## Questions for the operator, before any task is claimed

1. **Engine 20 into the Phase 5 row.** The row lists engines 5, 6, 8, 12, 13, 15 today and
   engine 20 sits in Phase 7. Spec 59 moves it on your instruction. Confirm.
2. **A new leaf package `src/acsoe/modelling/`**, C-owned, importable from both the live loop
   and `research/`, so live and replay compute from one implementation. Confirm.
3. **Engine 8 blocks on a DI refusal** under contract rule 6 while staying a non-gate in the
   registry. The alternative is skeptic applying the veto after cost and risk have run.
   Confirm or overturn.
4. **The metric ruling** (Brier against base-rate Brier; BUY-call target rate against
   break-even; no accuracy). Confirm or overturn.
5. **Uniqueness weights** as sample weights, with effective sample size reported. Confirm or
   overturn.
6. **The DI reading**: reference set is the predictor's training rows for the fold, per pair
   the last `di_window_days` of the window, mean k-nearest distance, threshold at a
   percentile of the leave-one-out distribution. Confirm or overturn.
7. **Three values are yours**, absent until you supply them, with the engines failing closed
   meanwhile: `prediction.di_percentile` (lead's recommendation 0.95),
   `anomaly.threshold_percentile` (recommendation 0.99), `skeptic.veto_threshold`
   (recommendation 0.5). Supply now, or leave absent until the walk-forward reports.
8. **`scout.rank_feature`** is chosen from spec 75's study. The study runs after the trainer;
   the ruling can wait for it. Confirm that ordering.
9. **`lightgbm`, `scikit-learn`, `shap` into the base install.** Confirm.
