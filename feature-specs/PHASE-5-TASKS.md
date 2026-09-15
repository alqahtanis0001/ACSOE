# Phase 5 — shared task list

## HANDOFF 4, 2026-09-15 ~08:10 — the operator is shutting down. Read this first.

**Phase 5 is NOT closed and NOT consolidated** (both withheld by the operator). The session ran
out of time before the gates for phases 0 to 4 and before the ruled config values could land
green. Exact state of every piece:

| Piece | State |
|---|---|
| Operator rulings of 2026-09-15 (DI exclusion; `anomaly.threshold_percentile: 0.99` provisional; `scout.rank_feature` none, open for Phase 7; 50.2% incomplete vectors as Phase 7 prerequisite 6) and of 2026-09-14 (`skeptic.veto_threshold: 0.50` provisional) | **Recorded** in the tracker (Open Questions, Locked Decisions, prerequisites 5 and 6), spec 68's amendment, the glossary, `docs/build-log/phase-5/lead.md`. |
| DI 48-bar exclusion (C-3): `modelling/di.py` (`fit(..., decision_ts, exclusion_s)`, `load` refuses an unexcluded DI), `research/training.py` (span from `backtest.embargo_bars`), engine 8 blocks `prediction_unavailable` on a refused load, criterion `di_leave_one_out_excludes_48_bars` in `scripts/verify.py` with tests | **Built, C-3 reported the criterion PASS and 446 targeted tests green, mypy clean**; four mutations red. Included in the gate run below. |
| Spec 73 engine 15 review | **Done by the lead.** Two fail-open defects (absent/non-bool `is_buy` read as non-BUY; NaN `p_wrong` passed) fixed by C-4 with block tests, plus the veto sentence precision; `engine.py` sha256 `022039a7…`; 129 tests green; sweep 1 killed every arm. **C-4's sweep 2 (the same arms on the final code, plus the reason-format revert) was still pending at the stop: re-run it.** |
| Engine 15 rehearsal (B-3, did not build it) | **Done**, 29 tests in `tests/engines/test_feature_chain_rehearsal.py`. In the full chain the bar tick stops at engine 10 for want of engine 9, so engine 15 is unreachable this phase; with 10 and 11 omitted it blocks unconfigured and vetoes/passes correctly with a trained skeptic. |
| Registration of 5, 6, 12, 13, 8, 15 in `bootstrap.py` | **Done**: opportunity chain 5, 6, 7, 12, 13, 8, 10, 11, 15. `tests/cli`, `tests/core`, Phase 0 and 3 criterion tests 207 passed. |
| `skeptic.veto_threshold: 0.50` and `anomaly.threshold_percentile: 0.99` into `config/default.yaml` | **NOT LANDED.** Pasting them turns 6 tests red that pin the keys as absent or train fixtures with the committed config (listed below). Backed out so the commit is green. **Next session: land the YAML and repoint those 6 tests in the same change.** |
| DI refit with the exclusion over all 405 folds | **Done.** Out-of-sample refusal with the exclusion: **0.95 → 6.79%, 0.99 → 3.31%, 0.999 → 2.06%** (was 94.7%, 74.9%, 31.1%). `docs/dataset/di-exclusion-refit-2026-09-15.py` and `.json`. `prediction.di_percentile` stays absent until the operator rules on these. |
| Gates | **Only `--phase 5` was run, on the committed tree: `14 criteria: 13 PASS, 0 FAIL, 1 PENDING`, exit 0** (PENDING `di_fitted_on_predictor_training_set` on `prediction.di_percentile`, as ruled). The first run failed `toolchain_green` on one test, `tests/verify/test_runner.py::test_each_phase_registers_its_own_criteria_and_no_others`, whose phase 5 list lacked C-3's new criterion; the lead added the name (C lane, under the deadline) and the re-run was green. **Phases 0 to 4 were not gated this session. Run all six in order on a quiet tree.** |

**The config change to land** (it was in the tree and backed out):

```yaml
anomaly:                         # Engine 13, specs 70, 72.
  threshold_percentile: 0.99     # OPERATOR, ruled 2026-09-15, PROVISIONAL. 1.24% blocked out of
                                 # sample against 1% nominal, stable by year, the volatile tail.
                                 # 0.95 rejected. The spec 70 ten-sigma question stays open.
skeptic:                         # Engine 15, specs 69, 73.
  veto_threshold: 0.50           # OPERATOR, ruled 2026-09-14, from the veto sweep, PROVISIONAL
                                 # until the chain runs end to end.
```

and the header comment above `models:` updated to say three keys remain absent
(`prediction.di_percentile`, `models.*_run_id`, `scout.rank_feature`).

**The 6 tests that go red with it** (each pins the committed config's absence; the absent case
must be supplied by the test instead, not deleted):
`tests/engines/test_skeptic.py::test_with_no_threshold_configured_it_blocks_rather_than_passing`
(line 227 precondition only), `tests/research/test_anomaly_training.py::test_no_threshold_is_recorded_while_the_key_is_absent`,
`tests/research/test_skeptic_training.py::test_the_veto_numbers_wait_for_the_operators_threshold`
(both train with the committed config, so a threshold is now baked in: train with the key removed),
`tests/harness/test_doubles.py::test_a_leaf_the_model_declares_optional_and_the_file_omits_reads_as_none`
(drop the two ruled keys from its list), and
`tests/engines/test_feature_chain_rehearsal.py::test_a_buy_call_with_the_skeptic_unconfigured_blocks_with_skeptic_unavailable[no-threshold|no-run-id|neither]`
(its "unconfigured" config must remove `skeptic.veto_threshold` explicitly).

**Then, in order:** land config plus those 6 tests; C-4's sweep 2; gates `--phase 0` to
`--phase 5` on a quiet tree, each to a file; commit; report. Expected `--phase 5` then: every
criterion PASS except `di_fitted_on_predictor_training_set` PENDING on `prediction.di_percentile`.

**One lesson, recorded because it cost this session its gates:** the lead waited about two hours
for a teammate message that never came instead of checking the teammate's files. Check the tree
on a timer; never block on a message.


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
- **The full-archive `acsoe research` run finished: exit 0, "backtest OK", about 36
  minutes, a 429 MB parquet of 20,331,237 labelled rows, peak 51.9 GB resident.** So spec
  61's acceptance is proven against the real 234-pair archive, and the process exited on its
  own; nothing to kill. **A-2's earlier "multi-pair divergence" diagnosis was wrong and A-2
  corrected it itself**: it had reasoned from the Phase 4 archive (3 pairs, 859,248 bars) when
  the directory now holds 234 CSVs and 20,443,861 bars; at the measured 3 KB per bar, 20.3
  million rows is about 60 GB, so the memory is linear and there is no anomaly. What remains
  is narrower and cheap: engine 23 accumulates every labelled row of every pair in one Python
  list and writes one parquet at the end, so it needs ~50 GB to produce a 429 MB file. **Fix
  before spec 67** as a small A spec on `research/backtest.py`: stream, one parquet per pair or
  appended row groups. A-2's build log has the misdiagnosis as its own entry; the lesson is
  that a benchmark control cannot catch a wrong assumption about the thing the benchmark is
  compared against.
- **Two open questions from A-2's progress file.** Whether `acsoe research` should replay the
  whole archive on every invocation, since engine 20 in the same chain will pay engine 23
  first every time and no spec asks for `--only` or a bar limit; and that nothing has yet run
  engine 20 through the chain, so the first real run is the first test of the
  `TournamentEngine(*, digest_path=None)` seam.

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

## HANDOFF 3, 2026-09-13 17:35 — the LEAD is switching model mid-phase. Read this first.

The operator is switching the lead from Fable 5.1 to Opus 5 to reduce usage. The teammates
(`A-2`, `B-2`, `C-2`, all Opus) keep running; the lead's context does not carry over, so
this section is what the new lead knows. The operator's standing rules still apply:
`AGENTS.md` first, then `context/*` in order, then this file top to bottom.

**Committed state, latest `e4da453`.** Done: 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70,
71, 72, 76, 78, 79 (17 of 21). Gate at the last lead run: 10 PASS, 0 FAIL, 3 PENDING
(`di_fitted_on_predictor_training_set` waits on the operator's `di_percentile`;
`anomaly_and_skeptic_have_both_tests` on 73; `tournament_writes_leaderboard_from_oos` on 74).
`joblib` is a declared dependency with a stack-table row.

**In flight on disk, uncommitted, at 17:33 — do not commit until each owner reports green:**

- **C-2**: spec 73 engine 15 `skeptic` (`src/acsoe/engines/skeptic/`, `tests/engines/
  test_skeptic.py`), a `tests/research/test_training_main.py` (the no-double `main()` test
  ruled at 11:50), and touches to `training.py`, `prediction/engine.py`,
  `console/format.py` and its tests, `test_phase5_criteria.py`. C-2 was ordered at 16:50 to
  report 71 and 72's four-gate state, then do the `build_dataset` per-pair fix, then start the
  full 234-pair run in the background with `--write-fixture` and report its command and PID,
  then 73, 74, 75. It has not yet reported since the resume; its next report says which of
  those happened.
- **B-2**: the engines 13 and 8 rehearsal in `tests/engines/test_feature_chain_rehearsal.py`
  under the 17:25 request below; engine 15 joins that rehearsal when 73 lands.
- **A-2**: idle, nothing outstanding; reviews B-2's rehearsal read-only if asked.

**What the lead does at each report.** Run the owner's lane tests, tree-wide ruff and mypy,
**to files with the exit code checked from `$?`** (never through a pipe), commit the
owner's files with a message naming the spec and the agent, push, then answer in this
channel with a dated entry and, where a reply matters quickly, one `SendMessage` to the
`-2` name followed by `ListAgents` to confirm no bare-letter session was resurrected.
**Never send to `A`, `B` or `C`.** Teammates send to `main`.

**Still ahead.** 73, 74, 75 (C-2); the full run and its digest as the committed fixture;
the three operator thresholds from that digest, plus `scout.rank_feature` from 75's study;
the `build_dataset` fix (tracked item 1 in Handoff 2); the suite-runtime item after 74;
then 77: the two-tick rehearsals complete, every teammate asked for an explicit stop, the
six gates `--phase 0` to `--phase 5` run in order to files on a quiet tree, registration of
5, 6, 12, 13, 8, 15 in `bootstrap.py` in registry order with holes for 9, 14, 16, 18, and the
report. **Do not close the phase or consolidate the build logs; the operator has withheld
both.** The open questions for the operator are in the tracker (anomaly threshold, macro
self-identification, previous-bar DI, the `acsoe research` full-replay-every-time question).

## RESUMED 3, 2026-09-13 16:50 — same team. Handoff 2 below is still the state of record.

C-2 died on its session limit at 14:08 while running spec 72's gates, after building
engines 8 and 13 on disk (uncommitted); nothing moved since. Order now: C-2 reports 71 and
72, then the `build_dataset` fix and the full run in the background, then 73, 74, 75. A-2
takes the `joblib` item. B-2 rehearses engines 13, 8 and 15 after 73 lands; the request will
appear in the channel. Lead commits at each boundary.

**To C-2, 18:20 — answers, and one hard guard on the run.**

1. **Break-even in the ranking study: the same ruling as spec 67, do not write one.** Friction
   is live fees plus spread plus slippage and none of it exists offline; the reference figures
   in invariant 5 are marked for sanity-checking only. The report carrying the formula, both
   barriers and `friction: null` is exactly right. Spec 75 is amended to say so.
2. **joblib: the ruling is already made and it is option 1.** Keep your named local ignore
   permanently; `joblib.*` is deliberately **not** going into the mypy overrides, because this
   project runs `warn_unused_ignores` and an override would turn your ignore into an error.
   That is pyarrow's established treatment. Nothing to wait for.
3. **The offline-chain test is A-2's and A-2 has been asked**, with your better assertion
   (backtest present and first) recommended. Your own engine-count change is right.
4. **The guard on the run, and it overrides the instruction to start it.** Produce the
   measured projection **first** and send it to `main` before starting anything. If it comes
   out above about three hours, **do not start** — report the number and stop. Your own
   finding is why: `purged_walk_forward` materialises every row as a Python dict and visits
   every row once per fold, so 20.3M rows against roughly 340 weekly folds is billions of
   row-visits, and that is a different kind of job from the 29-minute labelling run. A run
   that has to be killed after four hours teaches us nothing and costs a day. If the number is
   large, the options are the lead's and the operator's, not yours to pick: subsample pairs,
   make the splitter index-based instead of dict-based, or accept a bounded dataset for
   Phase 5 and carry the full run into Phase 7. Measure, report, wait.

Everything else in your report is accepted. The engine 15 macro-column finding is the best
catch of the phase: a fixture that trained with no macro asset meant thirty-nine columns of
engine 8's vector builder had never executed and its order test was reversing an empty dict,
and only a mutation you were right to call a survivor exposed it.

**To B-2, 17:55 — rehearsal accepted; your escalation is ruled.** 21 tests, committed. Your
correction to the request was right and the lead's wording was wrong: engine 8 never reads
`prediction.di_percentile`, the trainer does, and the refusal travels as the absence of
`di.npz`. Building it as written and watching it fail with `assert 'cost' == 'prediction'` is
the rehearsal doing its job on the lead.

**The ruling on the gap you found.** A model whose baked-in DI threshold disagrees with the
config the operator is reading is a model nobody can reason about, and the divergence is
silent, which is this phase's whole failure mode. **Engine 8 compares the manifest's
percentile against `prediction.di_percentile` when the key is present and blocks on a
mismatch**, reason code `di_percentile_mismatch`, the reason naming both numbers. When the
key is absent, today's behaviour is unchanged: the artefact's own threshold governs and a run
trained without one is refused. This only ever makes the system less willing to trade, so
invariant 4 is untouched, and it is fail-closed under invariant 3 for the case the system
cannot tell which threshold governs. C-2 implements it in engine 8 with a block test and a
pass test and the prose in `REASON_PROSE`; B-2 extends the rehearsal to drive it once it
lands. Flagged to the operator as overturnable and recorded in the tracker.

**Your T2 survivor is filed correctly** — killed by C-2's own manifest-order test and nine
others, unreachable from any end-to-end fixture because engine 5 builds rows in
`FEATURE_NAMES` order, so the live chain can never construct the disagreement. Reporting it
as a survivor would have sent someone to write a test that already exists. The thin-pair note
(a constant trade count makes the z-score a division by zero, so engine 13 refuses for want
of dispersion rather than for anomaly) is in the tracker as live behaviour the operator
should know about, not a fixture artefact.

Engine 15 joins the rehearsal when 73 lands; the request will appear here.

**To C-2, 17:40 — start the full run NOW, in parallel with 73.** The lead has verified on
disk that your `build_dataset` per-pair fix is in (*"At most one archive frame is resident"*,
iterating pairs), and that the committed `walkforward_digest.json` is still the three-pair,
three-fold one. So the only thing between this phase and a real dataset is starting the run,
and it is **hours of wall clock that nobody is spending while it has not begun**. Start it in
the background now, before finishing 73: the full 234-pair training with `--write-fixture`,
output redirected to a file, and tell `main` the exact command, the log path and the PID in
your next message. Then carry on with 73 while it runs. The three thresholds the operator
has withheld (`prediction.di_percentile`, `anomaly.threshold_percentile`,
`skeptic.veto_threshold`) are read off that digest and cannot be chosen before it exists, so
this run is on the critical path for closing the phase and 73, 74 and 75 are not.

Two notes with it. Engines 8, 13 and 15 load artefacts by `run_id`; when the run finishes,
report the fold `run_id`s so the lead can decide with the operator which fold the committed
config points at. And if the run needs more than the machine can give while B-2 is
rehearsing, say so rather than racing it.

**To B-2, 17:25 — rehearsal request, engines 13 and 8 (15 follows when 73 lands).**
Engines 13 `anomaly` and 8 `prediction` are committed at `48521a7`. Extend
`tests/engines/test_feature_chain_rehearsal.py` (your file, sole author) to the chain
5, 6, 7, 12, 13, 8, 10, 11 with the real engines 10 and 11 in their positions, two real
ticks each, two configurations: (a) **no artefact**: `models.anomaly_run_id` and
`models.prediction_run_id` absent, so engine 13 blocks with `anomaly_unavailable` on the bar
tick and nothing after it runs, and engine 19 would have recorded a rejection with that code;
(b) **trained artefacts**: a fixture trains a predictor, DI and anomaly detector from the
committed sample into a temporary models root through `research/training.py` and sets the
two run ids in a fabricated config; on the bar tick engine 13 passes, engine 8 publishes
three probabilities, an `expected_move_pct` string, a DI and a threshold, and engine 10 reads
the expected move (with `prediction.di_percentile` absent engine 8 must block with
`di_refused`-unavailable rather than predict; assert that first, then supply a percentile
through the fabricated config for the passing path and say in the test that the number is
the test's, not config's). Mutations you must run: the DI compared after prediction instead
of before; the feature order taken from the state row instead of the manifest; engine 13's
comparison inverted. Report red for a real reason to `main`; never a fix. A-2 reviews the
file read-only and runs the A/B with hashes if a red needs a second pair of eyes.

**To A-2, 17:25.** Your packaging note change is committed. The rehearsal is B-2's file and
B-2's to author; you co-run read-only as above. Stand by.

**To A-2, 17:10.** `joblib` accepted; the stack table in `architecture-context.md` now has
its row, so drop the "document has not caught up" note from your test's copy. Override:
**option 1**, keep the two local ignores and no override, matching pyarrow's treatment;
nothing further. Stand by for the rehearsal.

## HANDOFF 2, session closed by the operator 2026-09-13 ~14:00. Read this before the one below.

**State.** Done and committed: 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, **70**, 76, 78,
79 (15 of 21; 70 landed at `2f49292` after this handoff was first written). Gate `--phase 5`: **10 PASS, 0 FAIL, 3 PENDING** (`di_fitted_on_predictor_training_set`
on the operator's `di_percentile`; `anomaly_and_skeptic_have_both_tests` on 72 and 73;
`tournament_writes_leaderboard_from_oos` on 74). Tree-wide pytest, mypy and ruff green at the
last lead run. Engines 5, 6, 7 and 12 rehearsed together through the real orchestrator.

**Remaining.** 71 prediction, 72 anomaly, 73 skeptic, 74 tournament, 75 ranking study (all
C); the engines 13, 8, 15 rehearsal (B-2 leads, A-2 may co-run); 77 registration and the
gate (lead). Plus two small A items from spec 70: declare `joblib` as a direct dependency in
`pyproject.toml` and add `joblib.*` to the mypy overrides, so C-2 can drop the named type
ignore in the anomaly loader.

**A finding from spec 70 that the operator needs before choosing
`anomaly.threshold_percentile`.** A ten-sigma volume-and-trade-count spike scores at the
0.904 quantile of the training scores and clears **neither** a 0.99 nor a 0.95 threshold.
Two causes stacked: the rolling z-score caps the spike before the model sees it (an outlier
inflates its own denominator, bounded by about the square root of the window, so ten sigma,
a hundred and a thousand score identically), and the forest splits at random across 21
columns of which the spike is extreme in 8. The detector as built blocks such a spike only
at about the 0.90 percentile, where it also blocks one ordinary training bar in ten. C-2 did
not widen features, change scaling or swap the model to make the spec's check pass; the test
asserts the true ordering and that a 0.85 run blocks the spike. The choice (a lower
percentile, a narrower velocity-and-volume input set for engine 13, or a different model) is
the operator's, and the lead's recommendation to bring to that ruling is the narrower input
set, because it addresses the dilution rather than the bar.

**Two items tracked to closure, in this order, first thing next session:**

1. **`build_dataset` per-pair fix, then the full 234-pair training run.** The trainer's
   dataset builder held every pair's frame at once (about 60 GB over 234 pairs), the same
   shape spec 78 fixed in engine 23. The fix is ruled (per pair, appended row groups, `--pairs`
   inside the loop, one frame resident, a test that it never holds two); C-2's progress file
   says whether it landed before the stop. **The full run was deliberately not started at the
   close**: it is hours, nobody would be present to harvest it, and a fixture appearing
   uncommitted mid-run is a mystery for the next reader. Start it in the background with
   `--write-fixture` once the fix is green, carry on with 70 while it runs, commit the digest
   it writes as `tests/fixtures/walkforward_digest.json`. The three operator thresholds are
   supplied from that digest, not before.
2. **Suite runtime, 173 s to about 340 s** because 51 new tests train models, paid once per
   phase in `toolchain_green`. Deferred by ruling until after 74; then share one training run
   across the read-only tests in `test_training.py`, deliberately, measured in both orders,
   with a check that no mutation now hides in a shared fixture.

**Also outstanding and small.** `REASON_PROSE["missing_candle"]` becomes "No pair traded
for a whole decision bar" (C-2, `console/format.py`, ruled 12:55). The macro
self-identification and the previous-bar DI are open questions for the operator in the
tracker, not blockers.

**Everything below this line is the running record of the session; the rulings log and the
lead-to-teammate channel are still authoritative.**

## RESUMED, 2026-09-13 09:50 — the same team, A-2, B-2, C-2, continues

The stop order below is lifted. All three `-2` sessions were idle with nothing moved since
the wind-down, and no original is live. The lead's channel stays this file, plus one direct
send per resume. New today: **spec 78** (A-2, engine 23 streams the slice per pair, before
spec 67 needs the dataset). Order of work: C-2 records and fixes the rank-feature defect it
found, clears the two lint findings, completes 65 and 66, then **60 before anything else**,
then 67 onward. A-2: the `training` config section first (field, then message `main`), then
78, then assess C-2's engine 3 `missing_bars` finding (it pools all pairs, so no consumer can
tell which pair has the hole) and report to `main` without changing a cross-chain key. B-2:
finish the engine 5 two-tick rehearsal you had begun, report, then stand by.

**To C-2, 10:05.** 65 and 66 are committed with the rank-feature fix; 64's step 4 is
amended in the spec to what you built (per-pair holes from each pair's own candles; engine 3
keeps the union; no per-pair map asked of A). One correction to what you are building to:
the mypy 3.12 ruling was **withdrawn** on 2026-09-13 (rulings log item 3); `pyproject.toml`
carries `python_version = "3.11"` with `follow_imports_for_stubs = true`, and the gate runs
the plain `mypy --strict src/ scripts/`, which is clean on 115 files; run that, not
`--python-version 3.12`. Your two bare-name sends resurrected nothing that is still live;
the roster is clean. Spec 60 now, as you said.

**To A-2, 10:25.** The `training` YAML is in (`num_trees: 400`, `learning_rate: 0.05`,
`num_leaves: 31`, `min_data_in_leaf: 200`, provisional, reasons beside each) and proven to
load. Tighten `TrainingConfig` to required, move `training` into `LANDED_SECTIONS`, delete
the two-halves test in the same change, message `main`, and the lead commits it with the
YAML. Your "constraint table first, interesting test second" habit goes into
`code-standards.md`. Then 78.

**To A-2, 10:35.** The `training` section is committed, field and YAML together. The
`datetime.now` in `BacktestEngine._write` is an invariant 9 breach and you take it inside 78
as you proposed: one line to `context.now`, with its own entry in the build log and a test
that the slice name follows the injected clock, since a direct clock read is a defect
whether or not it can bias a label.

**To C-2, 13:50.** 68 and 69 are committed together. Your four "still open" items were all
ruled at 12:15 and 13:20 below and you have not yet acknowledged either entry: 67 and 68
together is accepted; the macro self-identification is left for Phase 5 and documented; the
suite cost is deferred until after 74; and **yes, run the full 234-pair archive**, but only
after the `build_dataset` per-pair fix, in the background with `--write-fixture`, then
carry on with 70. Fixing the criterion rather than the trainer in 69 was right and the reason
you gave (the criterion would have passed a trainer that skipped the purge) is the one that
matters. Do the `build_dataset` fix now, start the run, then 70.

**To C-2, 13:20 — spec 68 rulings.** 68 is accepted; it will be committed together with 69,
because `research/training.py` was mid-edit for the skeptic (`_fit_skeptic` undefined at line
660) when the lead ran the lane, and the eight `test_di.py` failures that produced are yours
in flight, not a verdict on 68. Rulings: (1) 67 and 68 landing together stands, no split.
(2) `label_window_end_ts` joins `OOS_COLUMNS`: yes, the purge is on the window end and both
halves are yours. (3) The macro self-identification (a BTC row's `macro_btc_*` equals its
own features): **leave it for Phase 5 and document it** in the manifest notes and the
dataset digest with the fraction of affected rows; nulling would create a stronger signal
than it removes and excluding the two most liquid pairs is a trading decision; recorded for
the operator in the tracker. (4) The 173 s to 337 s suite cost is accepted for now; sharing
one training run across read-only tests is deferred until after 74, done deliberately and
measured both ways as you said. (5) You have not acknowledged the 12:15 entry: fix
`build_dataset` (per pair, appended row groups, `--pairs` inside the loop, one frame
resident) **before** the full run, then start the full run in the background with
`--write-fixture` and carry on. Say in your next report whether that is done.

**To C-2, 12:55 — one line in `console/format.py`, relayed from A-2 under the
`missing_bars` ruling.** `REASON_PROSE["missing_candle"]` reads "A decision bar has no
candle", which reads as a per-pair hole. Ruled wording, A-2's first option:
`"missing_candle": "No pair traded for a whole decision bar"`. Land it whenever you next touch
that file; the existing enumeration test covers it.

**To A-2, 12:55.** Seam work accepted and committed. Nothing outstanding on your side; stand
by for the engines 13, 8, 15 rehearsal.

**To A-2, 12:40.** Spec 79 is accepted at 3.57 GB with identical labels across all three
runs; your records are committed. The 479 versus 429 MB compression residual stays as
recorded, not chased. Your A/B hashing procedure is now a rule in `code-standards.md`. Next
and last for you this phase: the `missing_bars` seam work under the 11:05 ruling. Then stand
by for the engines 13, 8, 15 rehearsal, which B-2 will lead and you may be asked to co-run.

**To C-2, 12:15 — spec 67 rulings.** (1) 67 and 68's DI hook land together; one commit, no
split. (2) `build_dataset` holding every pair's frame at once is fixed **before** any full
run, as part of 67's close-out: build per pair and append row groups, the same shape as spec
78, the `--pairs` filter inside the loop, and a test that the builder never holds more than
one pair's frame. (3) Then start the full 234-pair run in the background with
`--write-fixture` and carry on with 68, 69, 70 while it runs; report its per-fold table and
the aggregate when it lands, and commit the digest it writes as the fixture. Until then the
three-pair digest stands and says what it is. (4) Your finding that a manifest entry written
beside a call is not a check on that call, and that only recomputing the expected rows from
the public splitter catches a calibrator fitted on the test window, goes into
`code-standards.md` in your words. The double-fitted scaler as a checked-negative for the
predictor and a live mutation for the DI: correct, and it becomes 68's named mutation the day
the percentile lands.

**To C-2, 11:50 — a seam that will not go red, relayed from A-2.** Under spec 79
`ArchiveReplay.frames()` is now a **generator of `(pair, frame)`** in `report.pairs` order,
not a dict. `research/training.py` `_archive_frames` (line ~1112) annotates it as a dict and
`main()` uses `pair not in frames`, `frames[pair]` and `frames.items()`; no test exercises
`main()`, so the suite is green with that path broken, and with `--pairs` the failure is a
plausible "the archive has no XBTUSD" blaming the operator's argument. Ruling: do not wrap it
in `dict(...)`; iterate `for pair, frame in _archive_frames(...)`, label as you go, keep only
the labels and features, one pair resident, with the `--pairs` filter inside the loop. The
trainer as written would otherwise hold every frame and every label at once and hit the 51.9
GB wall engine 23 just came off. Add one test with no double that drives `main()` over the
committed candles sample with and without `--pairs`, so this seam is tested by someone.

**To A-2, 11:35.** Spec 78 is accepted at 23.6 GB; its acceptance number is amended to
the measurement and the reader floor is **spec 79**, yours, written now: `ArchiveReplay`
loads one pair at a time, drops the eager dict copy, `frames()` a generator. Then the
`missing_bars` seam test under the ruling at 11:05 above, which you have not yet read: the
union stays, no per-pair map, the meaning stated at producer and consumer, one no-double test
with its two mutations. Read that entry before writing.

**To C-2, 11:20.** Spec 60 is committed. Three rulings on your three findings. (1) Macro
names move to `modelling/macro.py` with engine 6 re-exporting: accepted; spec 65 step 4 is
amended to say so. (2) The break-even rates are never in code: correct, and spec 67 is
amended; the digest reports `buy_target_rate` and the comparison is the reader's. (3) The
last-bits drift between the live path and the trainer is a fact about the system; your
criterion's two-part assertion (exact over the same candles, 1e-9 across frame lengths, worst
difference printed) is the right shape and the manifest should record `FEATURE_VERSION` and
the frame length the trainer used so the next reader of a drift number knows what moved.
For 67 as drafted: fix the three you named (the unasserted `joblib` import, the row-by-row
matrix build, and a numpy fast path inside `Scaler.transform` rather than beside it) before
it lands, and remember spec 59 decision 5 as the operator amended it: effective sample size
per fold on the same line as that fold's row count. Report the 4 and 5 sweep results.

**To A-2, 11:05 — ruling on `missing_bars`.** Your assessment is accepted and the ruling is
to change less than C-2 asked and more than nothing. (1) Engine 3 grows no per-pair map;
engine 5 derives per-pair holes from the candles engine 3 already publishes (spec 64 as
amended). (2) `data_guard`'s missing-candle condition **stays**, and its meaning is stated
where it is produced and where it is consumed: `missing_bars` is *bars in which no subscribed
pair traded at all*, which is a feed-level silence and a genuine data fault; per-pair holes
are ordinary market behaviour and are the feature layer's to mark. The field is not renamed
(it is a seam between two of your engines and a rename buys nothing the docstring does not).
The `data_guard` README, the `market_sensor` README and `contracts.py` docstrings say this in
one sentence each, and `REASON_PROSE` for the missing-candle code is checked against that
meaning (C-2's file; if the prose needs to say "the feed went silent", message `main` with the
wording and C-2 lands it). (3) Write the seam test with no double: engine 3 driven with two
pairs whose holes differ, asserting `data_guard` does not block on a per-pair hole and does
block when every pair is silent for a bar. Its two mutations: the union replaced by a
per-pair reading (blocks on the thin pair), and the condition deleted (never blocks). The
lead records the finding in the tracker as a gate whose scope changed by measurement. Take it
after 78's full-run report.

**To B-2, 10:50.** The engines 5, 6, 7, 12 rehearsal is committed at `8fdc275`. Stand by;
the next request, engines 13, 8 and 15 once C-2 lands 71 to 73, will appear here. Two of
your findings are recorded for that rehearsal: the fixture must stream under the live
spelling (`SOL/USD`), never the archive stem (`SOLUSD`), or engine 7's universe is empty for a
reason unrelated to wiring; and the account must hold spendable quote currency for engine 7
to choose anything at the committed risk fraction.

**To B-2, 10:10 — rehearsal request.** Engines 6 `macro_context` and 12 `regime` are
committed at `7dd0f1d`. After the engine 5 rehearsal, extend the same file to drive engines
5, 6 and 12 together through the real orchestrator against the fake client, two real ticks:
non-bar tick PASSes at engine 5 and nothing downstream runs; bar tick publishes a feature row,
a macro payload (with `available` reflecting whether the fake's pairs include the configured
macro pairs) and a regime label or a null with a reason. No engine 7 candidate is needed for
this; if `state["scout"]` gates engine 12, say so rather than fabricate one. Report red for a
real reason to `main` and C-2's lane, never a fix.

## STOP ORDER, 2026-09-13 02:55 — the operator is closing the session (LIFTED, see above)

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
