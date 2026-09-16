# Progress — c-interface

Your file. Only you write here. The lead merges into `context/progress-tracker.md`.
Never edit the tracker directly.

## Current Task

### CLAIM 2026-09-16 — Phase 6, the engines-and-models half of lane C (C-5, Opus 5 1M)

Written before any code, per Phase 6 rule 1. This session is **specs 95, 102, 96, 97 and 98
only**, in that order. A second C session may take the verification-and-interface half (99, 100,
101); those files are **not mine** and I will not write them — `scripts/verify.py`,
`tests/verify/`, `tests/harness/`, `console/`, `tests/console/`. Where a spec of mine needs a
console reason-code line (spec 95 may), I hand it over by message rather than editing
`console/format.py`.

| Spec | Files I will touch |
|---|---|
| **95** — engine 8 omits `is_buy` on a refusal; engine 15's read in the same change | `engines/prediction/contracts.py`, `engines/prediction/engine.py`, `engines/prediction/README.md`, `engines/skeptic/engine.py`, `engines/skeptic/contracts.py`, `engines/skeptic/README.md`, `tests/engines/test_prediction.py`, `tests/engines/test_skeptic.py` |
| **102** — the DI's fit and score at size, plus the peak-memory test | `src/acsoe/modelling/di.py`, `src/acsoe/research/training.py`, `tests/modelling/test_di.py`, `tests/research/test_di.py` |
| **96** — engine 9 `order_book` and the book fixture | `engines/order_book/` (four files), `tests/engines/test_order_book.py`, `tests/fixtures/book_sample.jsonl`, `tests/fixtures/README.md` |
| **97** — engine 14 `adaptive_router` and the leaderboard fixture | `engines/adaptive_router/` (four files), `tests/engines/test_adaptive_router.py`, `tests/fixtures/leaderboard_sample.json`, `tests/fixtures/README.md` |
| **98** — engine 19 records what 18 and 22 publish | `engines/memory/engine.py`, `engines/memory/contracts.py`, `engines/memory/README.md`, `tests/engines/test_memory_rows.py` |

**Held for the lead before I build them:** engine 14's weighting rule (spec 97 step 3 — a
methodology choice, proposed in the build log and approved before any code); `order_book.depth`
and any other new config key (spec 80); registration of engines 9 and 14 in `bootstrap.py`
(spec 82). **Held for a stop from the lead:** every baseline run and every timing or memory
benchmark in spec 102, which is worthless under contention.

**Seams I owe a message on:** B, for spec 98's payload shapes from engines 18 and 22 (specs 91,
93) before either side lands; A, for `scripts/cut_book_fixture.py` (spec 86) — I choose the two
pairs and the window and deposit the fixture, and I build engine 9 against the fake client's
book while I wait.

#### 95 — status

Claimed 2026-09-16. In progress.

### DONE 2026-09-15 — C-3 (Opus 5): the DI's leave-one-out excludes every pair within 48 bars (operator ruling 2026-09-15, amending ruling 6). Not committed.

`modelling/di.py` `fit(..., decision_ts, exclusion_s)` (keyword-only, required; three new refusals), `DiFit`/`di.npz` record `decision_ts` and `exclusion_s`, `load` refuses an npz without a positive span (engine 8 turns it into `prediction_unavailable`); `research/training.py` passes `backtest.embargo_bars x timeframes.decision_bar_s` and manifest `extras.di.exclusion_s`. New Phase 5 criterion `di_leave_one_out_excludes_48_bars` in `scripts/verify.py` (own subject percentile 0.90, recomputes both distributions, plus a boundary probe): **PASS**. Tests in `tests/modelling/test_di.py`, `tests/research/test_di.py`, `tests/engines/test_prediction.py`, `tests/verify/test_phase5_criteria.py`. Mutations (a) row-only, (b) `<`, (c) embargo ignored / span 0, (d) `load` accepting legacy: all red in round two; the criterion survived (b) in round one and gained the boundary probe. Targeted suite 446 passed; mypy and ruff clean on these files. `verify --phase 5`: 12 PASS, 1 PENDING (`di_fitted_on_predictor_training_set`, `di_percentile`), 1 FAIL `toolchain_green` — pytest timeout at 900 s under load, `bootstrap.py` I001 and a `test_skeptic.py` case that was C-4's mutation arm on disk (05:12:40 to 05:14:29), not a defect; all from other sessions' concurrent edits. Details: `docs/build-log/phase-5/c-interface.md`, last entry.

**For the lead:** `context/` and `feature-specs/68` still describe leave-one-out on the row alone wherever they did (not mine to edit). `test_all_twelve_criteria_are_registered_for_phase_5` now names twelve; any context file counting Phase 5 criteria as eleven is stale.

### CLAIM 2026-09-13 21:50 — specs 74 and 75, review-to-green, by the lead session (Opus 5)

C-2 is gone (session limit). The operator assigned **specs 74 and 75 only** to this session;
73 and 77 are running in a separate session on another model and are **not** touched here.
What this claim covers: adversarial review of `engines/tournament/`, `tests/engines/
test_tournament.py`, `research/ranking_study.py`, `tests/research/test_ranking_study.py`,
the `--ranking-study` branch of `research/training.py`, criterion
`tournament_writes_leaderboard_from_oos` in `scripts/verify.py` and its tests; every assertion
proven able to fail; fixes where a boundary is wrong; commit of the 74 and 75 files only.
Diagnoses go in `docs/build-log/phase-5/c-interface.md` under "Lead session, specs 74 and 75"
before any fix.

**Status 2026-09-14 23:10: DONE, gated and committed.** Spec 74 at `d590548`, spec 75 at `531d240`, pushed; `verify.py --phase 5` on each exact tree: 11 PASS, 0 FAIL, 2 PENDING (`di_percentile`, spec 73). The first gate on the combined tree timed out in pytest under contention with the artefact rebuild, no test failing; re-run quiet, green. Spec 74: four defects fixed, 15 mutations killed. Spec 75: four defects fixed, 13 mutations killed. The ranking study over the real run is now possible: the rebuilt out-of-sample file exists (405 of 457 folds). Not run yet.

**Open question for the operator, not acted on:** `n_trades` and `win_rate` count every
out-of-sample BUY call, including calls the DI refused. Live, engine 8 blocks those before the
cost gate, so they are never trades. Spec 74 says "BUY calls" and that is what is built; whether
the leaderboard should count only the calls a model version would have let through is a ruling.
While `prediction.di_percentile` is absent (the full run's state) no call is refused and the two
readings coincide.

**Commit scope, deliberately:** 74 and 75 files, the two older tests engine 20 turned red
(`tests/research/test_backtest.py` A-2's, `tests/verify/test_phase0_criteria.py`), the SHAP pane
sentence C-2 corrected during 74's hand check, and `tests/research/test_training_main.py` (the
75 branch tests live there beside the spec 67 close-out tests for code already committed at
`a5ff4cc`). Mixed files (`console/format.py`, `tests/console/test_reason_prose.py`,
`tests/verify/test_phase5_criteria.py`) are staged as HEAD plus the 74 hunks only. **Not
committed, left on disk as found:** everything of spec 73, the `di_percentile_mismatch` work in
engine 8, the `missing_candle` prose, the joblib comment in engine 13.

The full 234-pair run was started 21:46 by this session, detached, from a worktree at
`6e09881` (`../ACSOE-fullrun-6e09881`), cwd the main checkout, log
`logs/fullrun-20260913T214616.log`, cmd PID 45492, python worker PID 41504, `--write-fixture`.

### DONE 2026-09-14 — the skeptic against p_target at matched counts (lead session): `docs/dataset/skeptic-vs-ptarget-2026-09-14.*`, entry in `docs/build-log/phase-5/lead.md`. Not committed.

### CLAIM 2026-09-14 23:30 — the skeptic veto sweep, by the lead session (Opus 5)

Operator request: apply each fold's trained skeptic to that fold's out-of-sample BUY rows and sweep veto thresholds 0.30 to 0.70 by 0.05, reporting survivors (count, share, effective sample size), survivor and vetoed target rates; a different-fold control proving the check can fail. No retraining, no config change. Output to `docs/dataset/`, entry in `docs/build-log/phase-5/lead.md`. Status: **done 2026-09-14, not committed** (evidence files in `docs/dataset/skeptic-veto-sweep-2026-09-14.*` and the identity check beside them).

### Phase 5 — claimed 2026-09-13, before any code was written

Fourteen specs, claimed here in the order the lead fixed. Each entry names the files it will
touch. The previous C session for this phase died on a usage limit before writing anything, so
nothing below is carried over from it.

- **Spec 60 — the Phase 5 exit criteria in `scripts/verify.py`. Claimed, and DONE.**
  Eleven criteria registered for phase 5. **As landed:** 4 PASS, 7 PENDING, 0 FAIL.
  **Today, with 63 to 75 built: 10 PASS and 1 PENDING** — every criterion has a subject and
  the one remaining waits on the operator's `prediction.di_percentile`. Files:
  `scripts/verify.py`, `tests/verify/test_phase5_criteria.py` (28 tests), plus two of my
  earlier files that had to be narrowed — `tests/verify/test_phase0_criteria.py` and
  `tests/verify/test_runner.py`. See "Spec 60 — what landed" below.
  **Two of these criteria were wrong and their own first FAIL observation found it**: the
  skeptic's eligible set ignored the purge (spec 69), and the leaderboard's idempotence check
  compared two reads of the same moment and could never fail (spec 74). Both are in the build
  log; the second had carried a docstring claiming it proved idempotence since the day it was
  written.
- **Spec 63 — `src/acsoe/modelling/`. Claimed, and DONE.** `__init__.py`, `features.py`,
  `artefacts.py`, `weights.py`, `di.py`, `expected_move.py`; `tests/modelling/` (82 tests).
  See "Spec 63 — what landed" below.
- **Spec 64 — engine 5 `feature`. Claimed, and DONE.** `engines/feature/engine.py`,
  `contracts.py`, `README.md`, `__init__.py`; `tests/engines/test_feature.py` (20 tests).
  Every fixture is engine 3's **real** output, driven over a trade stream reconstructed
  from `candles_sample.parquet`, per the Phase 3 ruling that no test hand-builds another
  engine's payload — and a test asserts that reconstruction rebuilds the archive's bars,
  because otherwise the whole file would be green against a price series nobody chose.
  Seven mutations, seven killed, including spec 64's three named ones.
- **Spec 65 — engine 6 `macro_context`. Claimed, and DONE.** `engines/macro_context/`
  (four files); `tests/engines/test_macro_context.py` (14 tests). Selection and renaming
  only; both pair spellings from config; a missing asset published as `null`, named in
  `missing`, never zero and never substituted from a previous bar. Four mutations, four
  killed.
- **Spec 66 — engine 12 `regime`. Claimed, and DONE.** `engines/regime/` (four files);
  `tests/engines/test_regime.py` (17 tests). Three labels, each reached twice: end to end
  from three constructed price series through engines 3, 5 and 12, and again from one real
  engine 5 payload with **exactly one** input changed. `di_regime_shift` is a declared
  `null` with the reasoning in the README. Four mutations, four killed.
- **Spec 67 — `research/training.py`, the walk-forward predictor. Claimed, and DONE.**
  `src/acsoe/research/training.py` (1,270 lines), `src/acsoe/modelling/macro.py`,
  `tests/research/test_training.py` (20 tests), `tests/fixtures/walkforward_digest.json`
  from a real archive run. Six mutations, six killed — two of them only after two
  attempts. See "Spec 67 — what landed" below. **Original claim line, for the record:**
  `research/training.py`, `tests/research/test_training.py`,
  `tests/fixtures/walkforward_digest.json`.
- **Spec 68 — the Dissimilarity Index. Claimed, and DONE.** `modelling/di.py` (landed with
  spec 63), the fit hook in `research/training.py`, `tests/research/test_di.py` (8 tests).
  Four mutations, four killed, including **FAIL both ways**: the fit pointed at the test
  rows and the fit pointed at the BUY subset. **Landed together with spec 67** against 67's
  scope limit, which says the DI belongs to 68 — the fit is one helper inside the fold loop
  and a stub would have been a scaffold nobody could test. Flagged to the lead.
  The DI is **inert today**: `prediction.di_percentile` is the operator's and is absent, so
  every fold reports `di_rows: null`, no `di.npz` is written, and
  `di_fitted_on_predictor_training_set` reports PENDING naming the key. The tests supply a
  percentile through a config wrapper so the arithmetic is exercised without anybody
  inventing the number.
- **Spec 69 — skeptic training on predictor BUY rows. Claimed, and DONE.**
  `research/training.py`, `tests/research/test_skeptic_training.py` (12 tests), plus
  `scripts/verify.py` and `tests/verify/test_phase5_criteria.py` — the criterion was the
  other half of this seam and it was wrong. Three mutations, three killed.
  `skeptic_trains_only_on_predictor_buy_rows` now PASSes. See "Spec 69 — what landed" below.
- **Spec 70 — anomaly detector training. Claimed, and DONE.** `research/training.py`,
  `tests/research/test_anomaly_training.py` (14 tests), plus one corrected docstring in
  `modelling/artefacts.py`. Four mutations, four killed — one only after a second attempt.
  **Carries a finding the operator has to read before choosing the threshold.** See
  "Spec 70 — what landed" below.
- **Spec 71 — engine 8 `prediction`. Claimed, and DONE.** `engines/prediction/` (four
  files), `tests/engines/test_prediction.py` (20 tests), plus `console/format.py` and two
  console tests for the reason codes. Three named mutations, three killed. **One code
  retired from `REASON_PROSE` and one spelling in B's `seed.py` raised with the lead.** See
  "Spec 71 — what landed" below.
- **Spec 72 — engine 13 `anomaly`. Claimed, and DONE.** `engines/anomaly/` (four files),
  `tests/engines/test_anomaly.py` (16 tests), `console/format.py` and its enumeration tests.
  Four mutations, four killed. **Carries a second, sharper statement of the spec 70
  finding**: no single market-quality column, and no ten-sigma volume spike, clears any
  threshold that lets ordinary bars through. See "Spec 72 — what landed" below.
- **Spec 73 — engine 15 `skeptic`. Claimed, and DONE.** `engines/skeptic/` (four files),
  `tests/engines/test_skeptic.py` (17 tests), `console/format.py`, and fixture changes in
  `tests/research/test_training.py` and `tests/engines/test_prediction.py`. Five mutations,
  five killed — **one survived first and found a real defect in the engine**. See "Spec 73 —
  what landed" below.
- **Spec 74 — engine 20 `tournament`. Claimed, and DONE.** `engines/tournament/` (four
  files), `tests/engines/test_tournament.py` (18 tests), `console/format.py`,
  `console/reader.py`, `scripts/verify.py` and `tests/verify/test_phase5_criteria.py`. Five
  mutations, five killed, from a **verified green baseline**. The console hand check is in
  the build log. `tournament_writes_leaderboard_from_oos` PASSes, and fixing it found an
  assertion of mine that had never been able to fail. See "Spec 74 — what landed" below.
- **Spec 75 — the candidate-ranking study. Claimed, and DONE.**
  `research/ranking_study.py`, the `--ranking-study` mode in `research/training.py`,
  `tests/research/test_ranking_study.py` (16 tests),
  `docs/dataset/ranking-study-2026-09-13.json`. **Its numbers are not evidence yet** and the
  report says so in its own provenance. See "Spec 75 — what landed" below.

**Not mine and not to be built by me:** spec 61 (A — the config fields, the models root, the
research runner), spec 62 (B — `StoreClient(models_dir=...)`, `model_run_dir`,
`new_model_run_dir`), spec 76 (B — `rank_universe`), specs 59 and 77 (the lead).
`research/walkforward.py` is read, never changed: if a Phase 5 change makes
`walkforward_trains_on_the_past_only` red, the change is wrong.

### Spec 75 — what landed

`research/ranking_study.py` and a `--ranking-study` mode on the trainer that **trains
nothing**: the study is a reading of a run that already happened, and re-training to produce
it would make the table describe a different model from the one the operator is ruling on.

79 rows over 2,688 decision bars: the alphabetical control plus all 39 features in both
directions, which is spec 75's acceptance check. Per row: bars covered, target, stop and
timeout rates of the taken pair, its mean return, its DI-refusal rate, and the BUY-conditioned
count and target rate.

**It recommends nothing and the rows are in feature order, not outcome order.** An ordering by
outcome is a recommendation with the word left off. There is no "best" key and a test asserts
the JSON contains no such word.

**The numbers are not evidence and the report says so.** Best to worst across the whole
feature set is 0.4952 against 0.4874, with the control at 0.4907 — 78 basis points, which is
what a binary choice between two pairs from one generator looks like. The run is the
constructed 140-day two-pair series because **the full-archive run has not been started**, and
the report carries a `limitation` field saying to re-run it over the real out-of-sample file
before the ruling. Summary table in the build log.

**The break-even column is a formula, not a number — a deliberate deviation from step 2 and
flagged for the lead.** Break-even is `(stop_pct + friction) / (target_pct + stop_pct)` and
friction is live fees plus spread plus slippage, none of which is in `config/default.yaml` by
design. The report carries the formula, the two barriers and `friction: null`. This is the
same wall spec 67 hit and the lead amended that spec for it.

**A null feature value sorts last in both directions**, so a pair whose lookback has not filled
is never taken by default — the rule `rank_universe` follows. The alternative ranks exactly the
pairs with no history first in ascending order, and the table becomes a study of which pairs
are new.

### Spec 74 — what landed

`engines/tournament/` with the four files. Reads the training digest and that run's
out-of-sample parquet, writes one `leaderboard` row per fold through `StoreClient`, and
publishes what it wrote, what it skipped and the Brier extremes with each fold's own
base-rate Brier beside them.

**The fold's artefact run id is the model version**, `training_run_id` is the parent run.
Each fold writes a separate artefact and each is a model somebody could promote; a leaderboard
keyed on the parent would make every fold of a run look like one model with several scores,
and Phase 6's router would weight it as one. The criterion's own fixture says the same —
its digest carries a `run_id` per fold and calls them versions — which is how I found it.

**Nothing is promoted and the four Phase 7 metrics stay null.** A Sharpe over label returns
with no friction, no position sizing and no holding period is not a worse Sharpe; it is a
different quantity wearing the name, and the person who reads it later will not be the person
who wrote it. `TournamentState` has no field for any of them either.

**Idempotent through the store's own existence read**, `leaderboard_entries`, not the
console's newest-fifty `leaderboard()`. A test watches both methods and asserts the truncating
one is never called, so the fifty-first-fold defect is caught with three folds rather than
with fifty-one.

`trained_at` comes from the digest's `created_at`, falling back to the last fold's
`test_end_ts`. Not `now`: the console orders the leaderboard by `trained_at`, and a clock read
would put an old run at the top every time anybody re-ran the chain over it — invariant 9
besides.

**Five mutations, five killed**, and the sweep script now runs a **baseline first** and stops
if the tree is red. `promoted` forced true; a Sharpe computed from the label returns; the
existence check swapped for the console's read; `net_pnl` summed over every row rather than
the BUY calls; the model version taken from the parent run.

**Fixing the criterion found an assertion that could never fail.**
`tournament_writes_leaderboard_from_oos` ran the engine twice and then read the leaderboard
twice, so its idempotence check compared two reads of the same moment. It has been that way
since spec 60, with a docstring claiming it proved idempotence; it was proved PENDING and then
PASS and never FAIL, and a first FAIL observation is exactly when that surfaces. It now reads
between the two runs. Two SQLite handles were leaking beside it — the criterion's own
`StoreClient` and a `sqlite3.connect` in a `with`, which commits and does not close — and on
Windows that turned the criterion into `raised - PermissionError` after it had already
answered its own question.

**One console message had also stopped being true.** The SHAP pane said "nothing has been
trained and nothing has been explained yet", which engine 8 falsified. It now names both
phases: produced in 5, stored and rendered in 7. Its test had asserted only that the message
contained the phase number it was built from, so it could not notice the sentence around the
number going wrong.

### Spec 73 — what landed

`engines/skeptic/` with the four files. `is_gate = True`, number 15, the last gate before the
decision. Loads the artefact for `models.skeptic_run_id`, rebuilds the trained input vector —
the feature list then `p_target, p_stop, p_timeout, expected_move_pct` — and blocks when
`p_wrong` exceeds `skeptic.veto_threshold`.

**It can only veto, asserted on the published shape rather than on behaviour.** `SkepticState`
has seven fields and none of them is an approval, a confidence or a margin; a test pins that
set. A second test parses the engine's source with docstrings stripped and asserts no
approval word survives in the executable code — stripped because the module's own prose
explains at length that it must never approve, so a raw substring scan fails on the sentence
forbidding the thing.

**A non-BUY call is `OK`, not a block**, and it does not load the model at all. A `BLOCK`
there would write a veto the skeptic never made into the one table the research reads, and
the leaderboard would credit it with every bar the predictor simply did not like. Two tests:
one on the result, one proving the loader is never reached, because the second is invisible
in the first.

**An absent threshold blocks rather than passing.** Failing open would make the one gate meant
to catch the predictor's mistakes the one gate not running.

**Five mutations, five killed. One survived the first sweep and the survivor was right.**
"The input vector built from the state row's own order" could not be distinguished, because
the published row happened to hold exactly the manifest's names in exactly its order — and
chasing that would have missed what it exposed: **engine 15 never read the macro columns at
all.** They come from engine 6 under `state["macro_context"]["features"]`, engine 8 reads
them, and engine 15 looked every name up in the pair's own row. Live, against an artefact
trained on the real archive, it would have blocked **every call** with `skeptic_unavailable`
naming thirty-nine macro columns.

Nothing caught it because `dataset_for` built its dataset with no `macro_archive`, so every
engine fixture's manifest named 39 features and no macro columns — which also means the macro
half of engine 8's vector builder had never executed, and its order test had been reversing an
empty dict since it was written. The fixture now trains **with** a macro asset: the candidate
pair itself, which is exactly the macro self-identification case ruled on at 13:20 and left
documented for Phase 5, and which keeps the macro values in the trained range so the DI still
accepts the bar. With macro columns present the order mutation is killable, and engine 8's
three mutations were re-run against the new fixture and still kill.

**Two mutation readings in that sweep were taken against a red baseline** — the fixture change
had reached one of the two files sharing it and not the other — and reported KILLED on a
non-zero exit that meant nothing. Caught because the failure list looked wrong for the
mutation named beside it, which is a weak signal to rely on. Re-run clean. A pre-flight
baseline check belongs in the sweep script and is recorded as a known gap.

`anomaly_and_skeptic_have_both_tests` moves to PASS with both test files present, and its FAIL
observation is written: engine 15's tests with every passing marker inverted, which is what a
gate's tests look like when whoever wrote them thought about the failures and not about the one
case that has to work.

### Spec 67 close-out — the streamed dataset builder

Ruled at 12:15 and repeated at 13:20, 13:50 and in Handoff 2, done 2026-09-13 after 72.

`_archive_frames` is a **generator** of `(pair, frame)` with the `--pairs` filter inside it,
matching `ArchiveReplay.frames()` since spec 79 and never wrapped in a `dict`.
`build_dataset_to_parquet` turns one pair at a time into rows through
`dataset_rows_for_pair` — the one place a pair becomes dataset rows, shared with the eager
`build_dataset` so the two paths cannot drift — and appends a row group per pair through
pyarrow, the same shape spec 78 gave engine 23. `main()` reads the finished parquet back.
Provenance is stamped into the file's footer afterwards, because pyarrow cannot add key-value
metadata to a file it has already closed.

**`tests/research/test_training_main.py`, eight tests, no double anywhere.** Real CSVs in the
archive's layout, the committed `config/default.yaml` with `models.dir` redirected into
`tmp_path`, and the real replay, labeller, feature builder, trainer and artefact writer.
`main()` had never been driven by a test, which is why A-2's generator change sat there
broken and green.

**The frame count is asserted, not the memory.** `ArchiveReplay.frame` is wrapped so every
frame registers its own death through a weakref and the high-water mark is checked. It
reported **three**, and the third was a stale `for` target: `main()`'s macro loop left the
second macro pair's Decimal frame bound for the whole streaming loop that followed. Invisible
on a three-pair archive, one frame held across 234 iterations on the real one, and invisible
to a memory measurement too. The fix is `_macro_features(...)` as a function, so its locals
die on return — not a `del`, which is a line somebody deletes while tidying.

The assertion is `<= 2` rather than `<= 1`, stated in its own failure message: a
generator-driven loop has two frames live at the hand-over, and the property that matters is
not-234.

**Fixture note.** The committed candles sample is 12.5 days and the walk-forward needs 97
before its first fold, so that file cycles the sample's **returns** into a 110-day path, each
lap continuing from the last close. Every bar-to-bar return is real; the series is not, and
nothing there asserts a model number.

### Spec 72 — what landed

`engines/anomaly/` with the four files. A data-quality gate, `is_gate = True`, loading the
detector for `models.anomaly_run_id` through the store, scoring the candidate's
`MARKET_QUALITY_FEATURES` against the artefact's own threshold. Three reason codes, each with
its own test. **It cannot see the prediction**, and that is structural rather than careful:
its contracts module names no key belonging to one, and a test asserts that on the source,
because contract rule 3 means an engine reaches another engine's keys only by naming them.

`Scaler.subset(names)` was added to `modelling/artefacts.py` for it, with three tests. Engine
13 reads 21 of the model's 39-plus columns and has no macro vector to build a wide row from,
so it narrows the scaler rather than scaling wide and slicing — and `research/training.py`'s
anomaly path now narrows the same way, so the offline fit and the live score go through one
narrowing and one `transform` instead of two copies of the arithmetic.

**Four mutations, four killed**: the comparison inverted (spec 72's named one), the score
orientation flipped, a null input scored as zero, and the threshold defaulted when the
artefact records none.

**The finding, sharper than spec 70's and measured three ways.** Spec 72 asks for a block and
a pass differing in one input. Neither form of "one input" works:

| | score | quantile of the training scores |
|---|---|---|
| an ordinary bar | 0.5210 | 0.607 |
| the same bar, ten sigma of volume and ten times the trades | 0.5263 | 0.664 |
| the best single feature column moved 1000 scaled units out | 0.5415 | — |
| threshold at 0.85 | 0.5491 | — |

Nothing clears it. Seven of the twenty-one columns move the score by **exactly nothing**,
being constant across the training window. The spike does reach the features — `volume_z_96`
goes 1.53 to 6.93, `trades_z_96` goes −1.15 to 9.54 — and the forest moves five thousandths.
The cause is the model: an isolation forest does not isolate an extreme point in one split,
because the split value is drawn inside the node's own data range, so a point beyond the
training maximum travels outward *with* the largest training points and is isolated only when
that tail thins to one. Its depth is bounded by the size of the tail, not by how far outside
it sits — which is why the score is identical at ten sigma, a hundred and a thousand.

**There is no percentile at which this detector both blocks a broken market and passes an
ordinary one.** The threshold that separates them sits near 0.63, where the gate refuses 37%
of ordinary bars. That is not a defect in engine 13, which does exactly what spec 72 asks.

**What I did with the test rather than around it.** The pass path runs at a plausible 0.85.
The block path uses a second artefact whose recorded threshold is set *by the fixture* to the
midpoint of the two scores it has just measured, so what is under test is engine 13's
**comparison** — its responsibility — rather than the detector's separation, which is not.
The fixture computes that midpoint instead of hardcoding it, so the test says what it depends
on. I also deleted a test asserting that no single column can trip the gate: true of the bar I
measured, false of the next one, and a characterisation test that depends on which bar you
started from goes red for no reason anyone can act on.

### Spec 71 — what landed

`engines/prediction/` with `engine.py`, `contracts.py`, `README.md` and `__init__.py`. Loads
the active artefact through `store.model_run_dir(run_id)` — never `models/` by path — scores
the Dissimilarity Index **first**, and only then predicts, calibrates and publishes. Three
probabilities as floats, the expected move as an exact decimal string formatted once through
`repr` the way the labeller crosses the same boundary, the DI and its threshold, and SHAP
attributions. `is_gate` is `False` and it blocks under contract rule 6.

The artefact is held on the engine keyed by the run id it was loaded for, so a changed run id
reloads; the `TreeExplainer` is dropped with it, because serving the previous run's explainer
beside a new booster would attribute the decision to the wrong splits with nothing going
wrong. Nothing loads at import.

**Three reason codes, each with its own test asserting the code and not only the status.**
`prediction_unavailable` covers six load failures because they are one fact to an operator;
`prediction_inputs_incomplete` is separate because it is a different fault with a different
owner; `di_refused` is the one refusal that says nothing is broken.

**Two fixture faults, both of which made a green file test nothing.** First, engine 3's
four-trades-per-bar stream makes the published trade count constant, so `trades_z_n` is a
z-score of a constant and every candidate blocked on an incomplete vector. Second, with that
fixed, every candidate was refused by the DI at 1.0240 against a threshold of 1.0233 — the
fixture trains on the constructed series and was scoring real SOLUSD archive bars, which to
that model are exactly what the DI exists to refuse. The mechanism was right and the fixture
was wrong about what it measured. Both faults produce a *uniformly refusing* engine, which is
the shape that looks safe; a file asserting only `BLOCK` would have been green through both.

**Three mutations, three killed.** The one worth noting is the DI ordering: predict-then-veto
produces the same status, the same code, the same DI and the same absent `expected_move_pct`,
so no assertion about the result can tell the two apart. The test watches
`lightgbm.Booster.predict` and asserts it is never called on a refused candidate.

**One console change that needs the lead.** `engine-contracts.md` fixes the code as
`di_refused` and the engine emits it; `clients/store/seed.py` writes `dissimilarity_index` for
the same fact. Mapping both gave one sentence to two codes, which
`test_no_two_codes_share_a_sentence` correctly refuses. I retired `dissimilarity_index` from
`REASON_PROSE` and proved by test that seeded rows are unaffected, because they carry their
own prose and `operator_reason` prefers it. **`seed.py` is B's file and the spelling there
should follow the contract.**

### Spec 70 — what landed

An `IsolationForest` per fold over the 21 `MARKET_QUALITY_FEATURES`, fitted on the fold's own
training rows, scaled by the **predictor's** scaler so both models read one space, seeded from
`seeds.train`. No labels, no macro columns, no probabilities: this model answers whether the
market is broken, not whether the trade is good. Scores are oriented so larger means more
anomalous, and the manifest says so, because a sign that flips between the artefact and engine
13 is a detector that blocks the ordinary markets and passes the broken ones.

`anomaly.joblib` is **the one artefact in a run directory that is not text**, because
scikit-learn has no text dump for an isolation forest. `write_run` hashes it and `load_run`
refuses a file whose hash differs — which defends against a swapped file and not against a
hostile original, and that limit is stated rather than implied. joblib itself is a hard
dependency of scikit-learn rather than a declared one in `pyproject.toml`; it is imported with
a named `# type: ignore[import-untyped]`, the same shape `clients/store/parquet.py` uses for
pyarrow. **Raised with the lead** to declare it and add `joblib.*` to the mypy overrides.

**The finding, and it is the reason this spec is not just "done".** Spec 70's own acceptance
check is that a ten-sigma volume spike scores above the threshold. It does not. Measured with
the spike injected into the candles and the features recomputed, on fold 0:

| | score | quantile of the training scores |
|---|---|---|
| the bar, unspiked | 0.5284 | 0.683 |
| the same bar, ten-sigma volume and trade spike | 0.5595 | 0.904 |

The 0.99 threshold is 0.5954 and the 0.95 threshold is 0.5713. The spike clears neither. Two
causes stacked. **The features cap it before the model sees it** — `volume_z_n` is a rolling
z-score, so an outlier inflates its own denominator and is bounded by roughly sqrt(n); the
score is identical at ten sigma, a hundred and a thousand. **Isolation dilutes it** — the
spike is extreme in 8 of 21 columns and ordinary in the other 13, and the forest picks its
split dimension at random. I did not widen the feature set, change the scaling or swap the
model to make the check pass; all three are decisions above this lane and the third would be
choosing a detector by whether it satisfied a test. The trade the operator now has in front of
them: this detector blocks a volume spike only at about a 0.90 percentile, where it also
blocks one training bar in ten.

**Four mutations, four killed.** The outcome joined into the inputs (spec 70's named one),
fitted on the test rows, the threshold taken from the test scores, and the score orientation
flipped. **The third survived the first sweep** with the whole file green, and the fault was
my own test: `test_the_threshold_is_the_quantile_of_the_training_scores` compared the digest to
the manifest, which are two numbers written by one function from one variable. That is ruling 7
in the form I have now walked into three times this phase — the calibrator, the scaler, and
this. The test recomputes the quantile from the fitted forest and the fold's own training rows
now. The leak it had missed: a threshold taken from the test window blocks a fixed share of
that window whatever happened in it, so the block rate stops being a measurement.

One docstring in `modelling/artefacts.py` was wrong and is corrected: it said engine 13 passes
`MARKET_QUALITY_FEATURES` to `load_run`. It passes the full list, because the manifest records
what the *run* was trained on; the detector's narrower inputs live in
`extras["anomaly"]["input_names"]`. Left alone it would have sent spec 72 into a refusal for
the right reason at the wrong place.

### Spec 69 — what landed

Meta-labelling inside the fold loop: `wrong = label != "target"`, inputs are the scaled
feature vector plus the predictor's own three probabilities and its expected move, recorded
in the manifest in that order because engine 15 rebuilds the same vector live. **It can only
veto** — there is no output of this path that makes a trade more likely, and a test asserts
that on the source, because the behaviour itself only appears in engine 15.

Over four folds of the constructed dataset:

| fold | skeptic rows | effective |
|---|---|---|
| 0 | 0 | — |
| 1 | 612 | 53.09 |
| 2 | 1,295 | 108.39 |
| 3 | 2,037 | 167.70 |

Fold 0 correctly produces none: there are no earlier out-of-sample calls for it to learn
from, the digest says `skeptic_rows: 0`, no `skeptic.txt` is written, and engine 15 will
block with `skeptic_unavailable` for a model version without one. That is a reported absence,
not an omission.

**The veto numbers wait for the operator.** `skeptic.veto_threshold` is absent by ruling
until the walk-forward reports, so `skeptic_veto_rate` and `skeptic_surviving_target_rate`
are `null`. `skeptic_all_buy_target_rate` is reported regardless — it needs no threshold, and
it is half of the only comparison that says whether the skeptic is worth having. The tests
supply a threshold through a config wrapper so the arithmetic is exercised without anybody
inventing the number.

**The criterion and the trainer disagreed, and the criterion was wrong.** `verify.py`
recomputed the eligible set as earlier out-of-sample BUY calls and stopped there; the trainer
also applies this fold's purge and embargo. 647 rows against 612. Spec 69 says the skeptic's
rows are subject to the same purge and embargo as the predictor's, and the reason is not
symmetry: a row whose label window reaches into the test window already knows how that window
ended, and the skeptic's out-of-sample numbers are what an operator would read to decide
whether to keep the veto. The criterion was wrong in the direction that hides a defect — it
would have passed a trainer that skipped the purge and it FAILed the one that applies it. Both
halves are mine; `label_window_end_ts` joined `OOS_COLUMNS` in both files and the criterion now
recomputes with both filters, against a test window recomputed from `purged_walk_forward`
rather than read back from the digest. Flagged to the lead in advance as a seam I expected to
have to close.

**Three mutations, three killed:** the `is_buy` filter dropped (FAIL naming a second predictor
wearing a veto), the purge and embargo dropped (FAIL naming the label window), the training
identity not recorded (FAIL naming the row count). **The fourth exclusion has no mutation and
that is deliberate** — `train_walkforward` builds `previous_oos` from folds already finished,
so the `fold_index <` filter is belt-and-braces and flipping it to `<=` changes nothing
observable. A mutation that cannot change behaviour is not a survivor. The guard is proved live
one level down by a test that calls `_skeptic_training_rows` directly with a frame that *does*
contain this fold's calls.

**The vacuity trap this opens.** Once the criterion applies the same two filters the trainer
applies, a trainer that applied neither is caught only if those filters actually remove rows on
this dataset. `test_the_purge_and_embargo_remove_rows_rather_than_nothing` asserts the gap is
real, and the criterion's PASS line prints it: 35 of 647 earlier BUY calls removed.

### Spec 67 — what landed

`research/training.py`: dataset assembly, average-uniqueness weights, the weekly
walk-forward, LightGBM multiclass with per-class isotonic calibration, the expected move,
the out-of-sample file, the per-fold digest, the artefacts, and a `python -m
acsoe.research.training` entry point. `modelling/macro.py` holds the macro column names,
moved out of engine 6 because `research/` may not import an engine (the lead amended spec
65 for it).

**It has been run against the real archive.** `--pairs SOLUSD --start 1640995200
--max-folds 3`, 8 minutes, SOLUSD plus the two macro pairs, 420,081 rows:

| fold | rows | effective | Brier | base-rate Brier |
|---|---|---|---|---|
| 0 | 2,016 | 101.0 | 0.1470 | 0.1345 |
| 1 | 2,016 | 92.1 | 0.0992 | 0.0945 |
| 2 | 2,016 | 65.7 | 0.1200 | 0.1318 |

Two things in that table matter more than the Brier. **The effective sample size is about
5% of the row count** — 2,016 test rows are roughly 101 independent observations, which is
the overlapping-label reality the weighting exists to make visible. And the model is at or
slightly worse than the base rate on two folds of three, which is the honest first-pass
result and is what "a negative result is a valid result" anticipates. A leak would show as
a Brier near zero; it does not.

That digest is now `tests/fixtures/walkforward_digest.json`, byte-identical through a git
round trip, and `walkforward_weekly_retrain_reports_oos` PASSes against it. **It is a
three-pair bounded run, not the full archive**, and the digest says so in its own `pairs`
field. The full run is hours and needs the lead's approval.

**The anti-leak test and its control.** `test_a_random_walk_cannot_be_predicted` trains on
a series that is unpredictable by construction and asserts the Brier does not beat the
base rate; `test_a_deterministic_series_is_learned` is its control, because the first is
satisfied by a trainer that always returns the base rate. Measured: 0.1718 against 0.1556
on the random walk, 0.0000 against 0.2446 on the deterministic one.

**Two leaks that no metric can see, and the random-walk test did not catch either.** A
calibrator fitted on the test window and a scaler fitted on train plus test both survived
the whole suite, twice — the second time even after I had added identity fields to the
manifest, because the manifest recorded what the caller intended while the mutation
changed what the fit was handed. They are killed now by tests that **recompute** the
expected rows from the public splitter and compare the artefact against that. Full account
in the build log; the transferable part is that a detector's docstring claiming it catches
"every leak" is the claim to distrust, including when I wrote it.

**Known limit, stated rather than hidden.** `build_dataset` holds every pair's frame at
once, which is roughly 60 GB over 234 pairs. That is the same shape as the engine 23
problem specs 78 and 79 exist for, one module over, and the fix is the same: build per
pair and append row groups. Until then the full run is `--pairs`-bounded. The docstring on
`_archive_frames` carries the warning.

### Spec 60 — what landed

`--phase 5` now registers **13 criteria** (the eleven of spec 60 plus `docs_vocabulary` and
`toolchain_green`) where it registered two. The false green is gone: it printed *"Phase 5 is
green: every criterion PASS, zero PENDING"* over a phase that by then held the modelling
package, three engines and B-2's ranking function.

| Criterion | Today |
|---|---|
| `features_reproduce_in_replay` | PASS |
| `feature_lookbacks_are_time_not_rows` | PASS |
| `predictor_trains_and_calibrates` | PENDING — spec 67 |
| `training_is_reproducible_from_config_and_data` | PENDING — spec 67 |
| `di_fitted_on_predictor_training_set` | PENDING — spec 67/68 |
| `skeptic_trains_only_on_predictor_buy_rows` | PENDING — spec 67/69 (now **PASS**, spec 69) |
| `walkforward_weekly_retrain_reports_oos` | PENDING — spec 67 |
| `anomaly_and_skeptic_have_both_tests` | PENDING — specs 72, 73 |
| `scout_ranks_by_feature_not_arrival` | PASS |
| `tournament_writes_leaderboard_from_oos` | PENDING — spec 74 |
| `walkforward_trains_on_the_past_only` | PASS — re-registered from phase 4, same object |

**Two of my own earlier tests were too strict and had to be narrowed, not excepted.**
`test_no_registered_criterion_reads_data_models_or_logs` was a substring scan for `"data"`,
`"models"` and `"logs"`, and it went red on `getattr(result, "data", {})` — an `EngineResult`
field — and on `tmp / "run" / "models"`, a directory inside a `TemporaryDirectory`. Neither
reads a gitignored path. Replaced by an AST check that looks for a path *rooted at `ctx.root`*,
with its own two-direction test and its residual gap (a computed directory name) pinned as a
known limit. `code-standards.md` names this exact shape and says to narrow rather than add an
exception, because an exception keeps a check that cannot tell a path from a word.
`test_runner.py` pinned phases 5 to 8 as carrying only the every-phase criteria and now pins
Phase 5's set.

**The design decisions worth knowing before spec 67**, in full in the build log: criterion 1
hands the two paths deliberately different inputs; criterion 5 asks membership rather than
equality because the DI subsamples; criterion 6 recomputes the skeptic's eligible set from the
out-of-sample file rather than trusting what the skeptic recorded; criterion 9's *ascending*
call is the one that separates ranking from passing through; criterion 10 constructs its inputs
and is safe only because criteria 6 and 7 pin those shapes against the real producer.

**The seam spec 67 must build to** is fixed in `scripts/verify.py` as `TRAINING_CONTRACT`,
`DATASET_COLUMNS`, `OOS_COLUMNS` and `FOLD_DIGEST_FIELDS`, and the PENDING lines print it.
Summary: `build_dataset(labelled, candles, *, config, macro_archive=None)` returning a pooled
frame, and `train_walkforward(dataset, *, config, models_dir, derived_dir, now, max_folds=None)`
returning a report with `.run_id`, `.fold_runs`, `.folds`, `.digest`, `.digest_path`,
`.oos_path` and `.models_dir`.

### Spec 63 — what landed

`src/acsoe/modelling/`, the leaf package both the live loop and `research/` import. Six
modules, 82 tests in `tests/modelling/`, nine mutations run.

- **`features.py`** — 38 named, ordered, versioned features (`FEATURE_VERSION = "f1"`) over
  OHLCVT only. Lookbacks are `(4, 16, 48, 96)` bars and every window is
  `n * interval_s` **seconds**, so a hole shortens the window rather than stretching it;
  `bars_in_lookback_<n>` is a feature in its own right and a window below
  `features.min_lookback_fill` yields NaN for **that window's** features and no others.
  `MARKET_QUALITY_FEATURES` is the no-spread subset engine 13 is fitted on.
  `compute` is never told the pair, so no feature can encode pair identity.
- **`weights.py`** — average uniqueness and `effective_sample_size`, linear in rows via
  prefix sums. Concurrency is counted on the bars that exist, never on a synthetic
  contiguous grid, so a hole cannot inflate the uniqueness of the windows spanning it.
- **`artefacts.py`** — the `models/<run_id>/` layout: manifest, JSON scaler (never a
  pickle), a sha256 per file, and `identity_digest` over `(pair, decision_ts)`. It never
  creates a directory; the path comes from B's `new_model_run_dir`.
- **`di.py`** — leave-one-out fit, mean k-nearest distance, threshold at a supplied
  percentile, and the reference set's row identity stored in `di.npz` so the Phase 5
  criterion can check membership rather than a count. `np.load` needs no `allow_pickle`.
- **`expected_move.py`** — the one expected-move arithmetic the trainer and engine 8 share.

**Mutations: nine applied, nine killed, one survivor found and closed.** Each applied, run,
restored and the restore verified by sha256 in the same pass before the next was applied.
The survivor was spec 63's own named mutation — the manifest loader accepting a permuted
feature list — which survived the **whole** suite because `load_run` checks the order twice
and the only test reached the second check. Two tests now reach one branch each. Full
account, both red messages, and a second entry about an M1 that killed seven tests by
*raising* (which proves nothing, and which I nearly filed as strong evidence) are in
`docs/build-log/phase-5/c-interface.md`.

**Four commands, run 2026-09-13 after spec 63:**

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
2102 passed, 3 skipped in 207.68s (0:03:27)

$ .venv/Scripts/python.exe -m mypy --strict src/ scripts/
Success: no issues found in 106 source files

$ .venv/Scripts/python.exe -m ruff check src/ tests/ scripts/
scripts\verify.py:8025:24: RUF100 [*] Unused `noqa` directive (non-enabled: `BLE001`)
Found 1 error.

$ .venv/Scripts/python.exe scripts/verify.py --phase 5
PASS    docs_vocabulary  14 files scanned, 12 retired terms, no hit
FAIL    toolchain_green  ruff exit 1: scripts\verify.py:8025:24: RUF100 ...
2 criteria: 1 PASS, 1 FAIL, 0 PENDING
```

`ruff check src/acsoe/modelling/ tests/modelling/` is clean. **The one FAIL is not mine and
I have not touched it**: it is a dead `# noqa: BLE001` in the other C instance's Phase 5
section of `scripts/verify.py`, reported to that instance with the narrower fix for the
`except Exception` underneath it. `--phase 5` still registers only `docs_vocabulary` and
`toolchain_green`, which is spec 60's open half.

**A's numpy fix, recorded because it unblocked me.** `modelling/di.py` was the first module
in `src/` to import numpy by name, and that aborted `mypy --strict` entirely — numpy 2.5's
stub uses a PEP 695 `type` statement, a syntax error under `python_version = "3.11"`, and
`follow_imports = "skip"` silences a module's source but not its stub. I escalated with
three options, all of which changed the environment. A found a fourth and better one,
`follow_imports_for_stubs = true`, which keeps the 3.11 floor and needs no dependency change.

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

### Phase 5, 2026-09-13

- **All fourteen of my Phase 5 specs are DONE**: 60, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72,
  73, 74, 75. `--phase 5` reports **12 PASS, 0 FAIL, 1 PENDING**, and the one PENDING is
  `di_fitted_on_predictor_training_set` waiting on the operator's `prediction.di_percentile`.
- **The full 234-pair training run has NOT been started, and that is a decision rather than an
  omission.** The `build_dataset` per-pair fix is done and committed, which was its
  precondition, and the lead's guard of 18:20 then said to measure first and stop above about
  three hours. **Measured: 22.2 hours**, and that is a floor — it excludes the dataset build
  over 47 GB of CSVs and the skeptic's growing training set.

  One fold timed at three sizes gives `4.87s + 109.74s per million training rows`, with the
  middle point predicted within 2%. The archive is 2,021,760 training rows per fold over 352
  weekly folds. `purged_walk_forward`, which was the suspected wall, is **not** the problem:
  272 ns per row per fold, about half an hour in total. The 352 gradient-boosting fits are.
  Memory is fine: 13.8 GB for the dataset plus 4.1 GB for the splitter's dicts.

  The command, when the lead and the operator decide to run it:
  `.venv/Scripts/python.exe -m acsoe.research.training --write-fixture`, optionally with
  `--max-folds N` or `--pairs`. Numbers and reasoning in the build log under "The full run is
  twenty-two hours, measured".
- **`di_percentile_mismatch` in engine 8, ruled after B-2's rehearsal, is DONE.** The DI
  threshold is baked into `di.npz`, so engine 8 never read `prediction.di_percentile` and an
  operator editing it would change nothing while believing otherwise. Engine 8 now compares the
  artefact's percentile against the key **when the key is present** and blocks with
  `di_percentile_mismatch` naming both numbers; absent is unchanged, which is the committed
  state. Three tests (block, match-predicts, absent-predicts) and the prose in `REASON_PROSE`
  pointing at the setting rather than at a missing model. Four mutations, four killed.
- **Not mine and still open:** spec 77 (the lead's registration and the gate), the engines 13,
  8, 15 rehearsal (B-2 leads), and one line of A-2's — `tests/research/test_backtest.py`
  asserts `build_offline_chain() == ["backtest"]` and engine 20 now joins that chain, so it is
  red until A-2 changes it. Raised and ruled; A-2 has been asked.
- **The joblib ignore is permanent**, ruled 2026-09-13: `joblib.*` is deliberately not in the
  mypy overrides because this project runs `warn_unused_ignores`, which would turn the named
  ignore in `engines/anomaly/engine.py` into an error rather than remove it. pyarrow's
  treatment. Nothing to wait for.

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

## `TOOLCHAIN` widened beyond `src/` — 2026-09-11, operator ruling

Not a spec. The widening deferred since Phase 0 and declined once at the Phase 1 boundary,
ruled by the operator after `tests/scripts/test_fixture_bytes.py` shipped a **SyntaxError on
the declared Python 3.11** that nothing in the gate could see.

**Done.** `ruff` now reads `src/`, `tests/` and `scripts/`; `mypy --strict` reads `src/` and
`scripts/`; `pytest` already read `tests/`. `TOOLCHAIN_ROOTS` is derived from `TOOLCHAIN` and
the criterion's existence guard reads it, so a path added to a command cannot fall out of the
PENDING check. Full write-up, every mutation and every red message in
`docs/build-log/phase-4/c-interface.md`.

- **The acceptance test passes.** The exact `1811069` f-string form, reintroduced under
  `tests/harness/`, makes `--phase 0` FAIL naming the file, the line, the column and
  *"Cannot use an escape sequence (backslash) in f-strings on Python 3.11"* — while `pytest` on
  that same file reports `1 passed`. Scratch file removed.
- **Six mypy errors in `verify.py` fixed**, not suppressed. The one that mattered:
  `_command_row` declared `sqlite3.Row` over a `fetchone()` that returns `None`, with three
  callers indexing it on the next line.
- **`--output-format=concise` added to ruff.** Without it the criterion's one line reads
  `Found 4 errors` and names nothing — ruff's default format is eight lines of gutter art per
  finding and `describe_exit` has room for three.
- **Five mutations, five reds**, each restored by hash in the statement that applied it. One
  was cross-lane on `pyproject.toml`; `git diff --quiet` clean afterwards.
- **Re-verified:** `pytest tests/ -q` → 1678 passed, 1 skipped. Phases 0-4 → 7/7, 10/10, 9/9,
  9/9, 9/9 with `replay_full_archive` skipped as `--live`. Identical counts to before the change.

**Left alone, in A's lane.** `scripts/build_archive.py:277` (`no-any-return`) and two in
`scripts/recording_report.py` (`I001`, `RUF100`) — reported to the lead, fixed by the lead in
`8e32c32`.

**The `RUF001` obstacle the tracker records no longer exists.** `ruff check tests/` is clean;
`tests/console/test_format.py:25` already carries a rule-named `noqa` with its reason. The
previous C session discharged it.

### Open Questions — for the lead

1. **`context/code-standards.md`, Verification section, is now wrong.** It lists the four
   commands as `mypy --strict src/` and `ruff check src/`. An agent following it by hand will
   pass checks the gate fails. `context/` is the lead's; I did not edit it. The gate is the
   definition of done, so the list is the half that is wrong.
2. **`context/progress-tracker.md:328`** still records this as *"Deferred from Phase 0, still
   deferred"*, and its account of both obstacles is stale.
3. **`mypy --strict tests/` was excluded deliberately and is not done.** It would need a return
   annotation on ~1680 test functions and every fixture. The hole: a type error inside a test
   file is caught by nothing but the test failing. Named in the `TOOLCHAIN` comment so it is a
   decision on the record. Whether to take it is yours.
4. **The `toolchain_green` intermittency did not reproduce here** — none across seven full gate
   runs and three standalone suite runs. That is an observation, not a diagnosis, and it rules
   nothing out.

**Correction to point 4 above: the intermittency did appear**, on the second pass of the gate
over phases 0-4. Phase 3 went red with `ERROR
tests/engines/test_safety_guard_chain.py::test_on_the_seeded_database_safety_trips_and_blocks_the_tick`
and `1677 passed, 1 skipped, 1 error`; phase 4 ran the same suite immediately after and was
green. Not re-run, not attributed, full output captured. Write-up in the build log, including a
finding for the lead's investigation: **for a failure inside `toolchain_green` the criterion's
one line is the only record that exists** — `describe_exit` keeps three lines and drops the rest,
so an `ERROR`'s traceback is gone. The fix is small and I have not made it; it is outside this
session's one change and the lead is investigating the fault in parallel.

**Two data points the lead asked for.** (1) The widening costs ~400 ms cold and nothing
measurable warm for mypy, ~45 ms cold for ruff, against a gate whose pytest takes 95-100 s —
under 1% of the criterion. The first cold measurement claimed the widened mypy was *four times
faster*; it was first-touch cost after a cache wipe, caught by running the comparison in reverse
order. (2) The phase-3 error did **not** reproduce on the immediately following identical suite
run with the tree untouched: ten consecutive identical `pytest tests/ -q` runs across two
five-phase passes, one error, and the run straight after it was green.


## Engine 15 review fixes — 2026-09-15 (C-4)

- Closed two fail-open paths in engine 15, spec 73. An absent, `None` or non-boolean `is_buy` now blocks with `skeptic_unavailable`, where it used to return `OK` as not a BUY. A non-finite `p_wrong` now blocks with `skeptic_unavailable` before the comparison, where it used to pass.
- The veto reason prints `p_wrong` and the threshold at 6 significant digits or more, so the two numbers can be told apart. `:.4f` printed "0.0000 … 0.0000" (B-3's rehearsal).
- Tests: 129 passed across `test_skeptic.py` and `test_reason_prose.py`. ruff and mypy --strict are clean.
- Sweep 1: mutations (a), (b), (c1) and (c2) were all observed red; kills are in the build log. Sweep 2 (a to d, on the final code) is pending.
- Open for engine 8's owner: its refusal publishes `is_buy: False` by default, so engine 15 returns `OK` on a tick engine 8 already blocked. That doesn't fail open, but it conflates "no call" with "not a BUY".

## C-verification (specs 99, 100, 101) — 2026-09-16

**This heading is mine and nothing under it is another session's.** Lane C is split for
Phase 6: `C-models` owns 95, 96, 97, 98, 102 and writes under its own heading; this session
owns **99, 100, 101** and the files `src/acsoe/console/`, `scripts/verify.py`, `tests/verify/`,
`tests/harness/`, `tests/console/`.

### Claimed now — spec 99, the first two codes

Claiming `src/acsoe/console/format.py` (`REASON_PROSE`) and `tests/console/test_reason_prose.py`.

First increment only: prose for B's spec 89 codes `position_open_on_pair` and
`entry_resting_on_pair`, which is the one red on the tree and is blocking the team's baseline
run. The rest of spec 99 — the walking test over **every** engine's contracts, and the codes
still arriving from B (engines 16, 18, 21, 22) and `C-models` (9, 14) — comes after the lead
releases me.

**Landing this turns one of B's tests red on purpose.**
`tests/engines/test_risk.py::test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose`
asserts both codes are *absent* from the map; it is B's tripwire and B deletes it. That file is
B's and I did not touch it. Lead and B told at the moment the prose landed.
