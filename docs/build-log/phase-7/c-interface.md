### Decision: where the promotion bar's arithmetic lives, and how the t quantile is got

**Agent:** c-eval · **Task:** spec 139 · **Date:** 2026-09-19

**Options.** (a) Inline in `engines/tournament/engine.py`, which keeps the engine directory at
its three files but buries a statistical library and its worked example in a 550-line engine;
(b) `research/promotion.py`, which engine 20 cannot import (engines are the live-loop side of
invariant 5); (c) `modelling/promotion.py`, the leaf package both sides import.

**Chose (c).** Pure arithmetic, stdlib only, importable by engine 20 and by spec 138's
`research/attribution.py`. `tests/modelling/test_import_boundary.py` pins the package's file
list and gains the one name.

**The Student-t quantile is computed in the module, not imported.** `scipy` is installed (it
arrives with scikit-learn) but is not a dependency this project declares, and a dependency not
in `architecture-context.md` is a stop. Rejected: importing `scipy.stats.t` (undeclared
dependency, which is a stop and a lead ruling at 04:00); taking the quantile through
`statsmodels` (it is `scipy` underneath and `statsmodels` is only in the `research` extra).
Chose: invert the t CDF through the regularised incomplete beta (Numerical Recipes' continued
fraction) by bisection, held by a test to scipy's values to 1e-10 relative at every
(p, df) the bar can ask for. Measured in scratch against `scipy.stats.t.ppf`: agreement to
machine precision for p >= 0.9, but **up to 18% relative error near p = 0.5** (the tail sits
near a half there and the subtraction loses precision). The bar never asks below 0.975, so the
domain is `0.9 <= p < 1` and anything else raises rather than answer where nobody checked.

**A dead branch found in the draft.** The first draft capped the HAC lag at `n - 1` and
reported whether the cap "bit". It never can: the lag counts *other* trades overlapping one
trade, which is at most `n - 1` by construction. The cap and its reporting field were removed
rather than left as an equivalent mutant with a docstring promising behaviour.

### Decision: two inputs the deflated Sharpe ratio leaves open — CONTESTABLE, flagged to the lead

**Agent:** c-eval · **Task:** spec 139 · **Date:** 2026-09-19

Spec 139 fixes the promotion bar exactly and says only that the DSR is "computed from the run's
per-period returns, with the skew and kurtosis terms and the number of trials as inputs". Bailey
and Lopez de Prado's formula needs two things that sentence does not name. **The DSR is reported
beside the verdict and never decides it**, so neither choice can move a promotion, but both
change what the printed number means, which the brief makes a stop. Built with the
recommendation, flagged in the DONE message, reversible without re-running anything.

1. *The periods.* Chose **the trades** (T = n), so the verdict and the DSR beside it describe
   one series. Rejected: daily equity returns including flat days (spec 138's grid), which would
   make the DSR a statement about the equity curve while the bar judges trades.
2. *V, the variance of Sharpe ratios across trials.* Chose **1/(T-1)**, the variance of a
   Sharpe estimate under no skill. Rejected: estimating V from the ledger, which spec 139 itself
   says cannot be done (most rows are counts and target rates, not return series).

### Decision: the verdict's row, and where its reason code goes

**Agent:** c-eval · **Task:** spec 139 · **Date:** 2026-09-19

A Phase 7 run replays 26 weekly predictors in sequence behind every gate, so the thing judged is
a run of the chain, not one fold's model. Chose one leaderboard row per judged run, `model_id`
`chain_run`, `model_version` the run id, `fold` null, with `promoted`, the per-trade Sharpe and
the DSR in their columns and **the reason code plus every figure the bar computed as JSON in the
existing `notes` column**. Rejected: a new `promotion_reason` column (a schema change through B
and the lead, for a field `notes` already holds); writing onto the predictor's per-fold rows
(the verdict is not about any one fold, and engine 14 weights that family).

### The trial ledger: the rule, and what it finds on disk

**Agent:** c-eval · **Task:** spec 139 · **Date:** 2026-09-19

**What happened.** R9 says every configuration evaluated against the out-of-sample data is a
trial, listed one by one, counted conservatively. Reading the committed outputs found that
"configuration" needs a rule before anything can be counted, because the outputs report
funnels (one line, six stages), sub-windows, complements (survivors and vetoed), and the same
selection twice in two files.

**The rule chosen, and stated in the ledger.** A trial is a *selection* evaluated on the
out-of-sample data and reported with any statistic of what it selected (a count, a share, a
target rate or a return); each reported (selection, sample) is one row. So every funnel stage
counts, every sub-window counts, a selection and its complement count as two, and **the same
selection reported twice counts twice**, because nothing on disk proves two reports were one
computation. Rejected: one trial per script run (it would count a 180-cell grid as one), and
one per final funnel result (it would treat "every gate up to the DI" as not a configuration
anybody looked at, when the findings cite exactly those stage counts).

**What exists on disk for the leaderboard.** Engine 20 has written no persisted leaderboard row
for the walk-forward. The only database under `data/db/` holds six rows, `v0.1`..`v0.6` of
`seed-train-0000`..`0005`: the Phase 0 seed's fabricated rows. The rows engine 20 *would* write,
one per trained fold, are the 405 rows of the committed `walkforward-folds-2026-09-14.md`, and
those are counted. Three fold models of a three-pair smoke run
(`train-20260913T100124-067b2b9d-f0..f2`) exist only under the gitignored `models/`; whether
they count as evaluated on the out-of-sample data is unclear, so they count, named as a constant
in the builder so a fresh clone rebuilds the same ledger.

**Excluded, with the reason in the ledger:** outputs that select nothing (timings, memory, spread
fits and depth on the 2026 recording, identity checks, tick grids, fold construction, dataset
statistics), the permutation no-skill bands (null distributions), and the 2026-09-13 ranking
study, computed on the constructed two-pair series of the test suite and saying so in its own
`meta.source`.

**Against spec 139's own list.** The spec names the DI at 0.95/0.99/0.999 and the anomaly gate at
0.95/0.99. The committed study evaluated seven percentiles of each and a 3x3 joint grid, so all
of them are counted; the ledger says so.

**The builder reads every text output line by line and raises on a line it cannot classify**,
and raises on a transcribed-output section or an output file it has no reader for, so a new cell
cannot be skipped silently. First run over the committed outputs: every line classified,
**1,679 trials** (leaderboard 408, reconnaissance 674, DI and anomaly 287, ranking study 169,
skeptic sweep 92, skeptic against `p_target` 45, this phase's runs 4).

### Spec 133: where the approval economics wait between placement and close, and one test they break

**Agent:** c-eval · **Task:** spec 133 · **Date:** 2026-09-19

**What happened.** Engine 19 writes a `trades` row when engine 22 closes a round trip, ticks
after engine 18 placed the entry. The economics exist in `state` only on the placing tick. The
obvious home, columns on the entry's `orders` row, does not work: `write_order` upserts every
column and engines 21 and 22 republish the entry order on later ticks without them, so the
fill-tick write would put NULL over the economics. c-eval proposed an insert-only table to
b-store; b-store had reached the same design independently and landed it in 0006 as
`approvals`, keyed by the entry's `userref` (`write_approval` inserts and never upserts).

**Chose.** On a tick where engine 18 published `placed: true`, engine 19 writes one
`ApprovalRow`: the four economics from engine 10's payload (the same fields
`ECONOMICS_FIELDS` harvests for a rejection, and the ones engine 10 compared against the
hurdle), the three model run ids from engines 8, 13 and 15's `model_run_id`, and the placing
tick's `(run_id, cycle_id, ts)`. When it writes a trade it reads `approval(entry_userref)` and
copies the seven fields onto the row. No approval, or no `entry_userref`, writes them as
absent; the trade is never refused for it. Rejected: routing them through a new `state` key
(the spec forbids it, and `state` does not survive the tick anyway); reading engine 8's
`expected_move_pct` instead of engine 10's (they are the same string when engine 10 ran, and
engine 10's is the figure the hurdle decision was made on).

**A consequence in another lane, found before writing the code.** A's
`tests/engines/test_trade_chain_rehearsal.py::check_recorded` builds the expected `trades` row
from engine 22's published payload alone and compares it column for column with the stored
row. Once engine 19 copies the approval onto the trade, the stored row carries economics that
engine 22 never published, so every rehearsal scenario that closes a trade will fail that
comparison. The test is right to compare, and it needs the approval's seven fields in its
expectation. It is A's file, so it is A's edit; told a-replay and the lead with the exact line.

### Mutation sweeps, specs 139 (statistics and ledger) and 133

**Agent:** c-eval · **Task:** specs 139, 133 · **Date:** 2026-09-19

Harness: each mutation applied from a byte copy in the scratchpad, `PYTHONDONTWRITEBYTECODE=1`,
the named tests run with `-x`, the file restored before the next mutation and the restore
verified by sha256 (every arm `restored=True`), a pytest summary line required for every
verdict. Baseline green before each sweep. Narrow by design: the test files that own the code.

**139, `modelling/promotion.py` and `research/trial_ledger.py`** (tests
`tests/modelling/test_promotion.py`, `tests/research/test_trial_ledger.py`; baseline 48 passed).
30 applied, 27 killed on the first pass, 3 survived:

- **P9, promote at `lower >= 0` instead of `> 0`: SURVIVED**, then killed. No fixture had a
  lower bound of exactly zero. Added `test_a_lower_bound_of_exactly_zero_is_not_above_zero`:
  twelve break-even trades have no dispersion, so the bound is exactly 0.0, and zero is not
  above zero.
- **P15, the DSR's skew term with the wrong sign: SURVIVED**, then killed. The worked example
  has zero skew by construction, so the sign could not matter to it. Added a skewed series whose
  DSR is recomputed term by term in the test without the module's helpers.
- **P19, the negative-long-run-variance guard disabled: SURVIVED, and is a checked negative.**
  The Bartlett weights keep the long-run variance non-negative, and `math.sqrt` raises on a
  negative anyway, so the guard was unreachable and its comment ("a square root of it would be a
  NaN") was false. **Removed**, with a comment saying why none is needed.
- Killed and worth naming: P1 is spec 139's own planted defect, **the lag forced to zero**,
  killed first by the worked example and also by the overlapping-trades test; P6/P7/P8 (no
  Bonferroni, one-sided, `n` degrees of freedom) killed by the hand-computed quantiles; P11
  (series not put in entry order) killed only by the shuffle test; L1-L8 (a funnel stage,
  a complement, the smoke-run models, the by-year cells or this phase's four runs not counted,
  or an unclassified line, section or output tolerated) each killed, the count changes by the
  committed-ledger equality test and the tolerances by their own planted-defect tests.

Re-run of the three against the new tests (baseline 50 passed): P9 KILLED, P15 KILLED, P19
SURVIVED (then removed as above).

**133, engine 19's approvals** (tests `tests/engines/test_memory_approvals.py`,
`test_memory_rows.py`, `test_memory.py`; baseline 70 passed including the rehearsed round
trip). 11 applied, 11 killed: approval written when this tick did not place; approval for an
errored engine 18; a float laundered through `str()`; an absent figure written as zero; run ids
from the wrong key; the trade not given its approval; the approval looked up by the exit's
userref; economics taken from engine 8 instead of engine 10; the approval's `cycle_id` not the
placing tick's; one economic not copied onto the trade; the approvals count not published.
No survivors.

### Decision: spec 137 adds `score_many` over the existing chunked search, and does not resume spec 102

**Agent:** C-models · **Task:** spec 137 · **Date:** 2026-09-19

**Options.** (a) Resume spec 102's parked diff (`scratchpad/di-102-second-attempt.diff` of an
earlier session): an element-budget block in place of the 512-row chunk, reference norms hoisted,
the leave-one-out's pairwise mask replaced by `searchsorted` bounds, `exclude_self` deleted, the
partition moved onto squared distances, and the trainer switched to the batched call. (b) Add only
the public `score_many`, a thin validating wrapper over the unchanged `_mean_nearest`.

**Chose (b).** Spec 137 asks for one thing, a batch call that returns what `score` returns, and
its scope limit forbids any change to the statistic. Every piece of (a) beyond the wrapper touches
`fit`'s leave-one-out, which nothing in Phase 7 calls (spec 135 takes the distribution from the
study rather than refitting), and each is a way for `di_leave_one_out_excludes_48_bars` to move.
The ranking scores up to about 130 rows a bar, which is one 512-row chunk, so the per-chunk norm
recomputation (a)'s main saving costs nothing here.

*Rejected (a)*, which the spec's step 1 names. It is correct work, measured bit for bit on the fit
side when it was written, and it is still parked: it is spec 102's optimisation of training, and
no Phase 7 run trains.

**Cost.** Peak memory per call is one chunk against the whole reference: 127 rows x 200,000 x 8
bytes is 203 MB per temporary, about 0.6 GB transient per bar per run. Four runs in parallel is
about 2.4 GB of transients. A universe above 512 pairs would take a second chunk, not more memory.

### Spec 137: the batched DI is equal to the per-row DI within 2.4e-14 on fold 404's real reference

**Agent:** C-models · **Task:** spec 137 · **Date:** 2026-09-19

Measured, not argued: fold 404's reference was rebuilt with the Phase 5 study's own `load_fold`
and `di_reference` (identity equal to the study's recorded `reference_identity`, 200,000 x 117),
and fold 404's complete test rows were scored both ways
(`scratchpad/c-models/f404_equiv.py`, read-only).

| Rows | Largest difference, batched against per-row | Refusals identical | Batched | Looped |
|---|---|---|---|---|
| 127 | 1.399e-14 | yes (0 refused) | 0.77 s | 12.38 s |
| 1,100 | 2.343e-14 | yes (1 refused) | 4.89 s | 110.85 s |

On the constructed fixture the difference is 1.2e-15. It is not zero because a many-row matrix
product may associate a dot product differently from a one-row one. The test tolerance is 1e-12,
about 40 times the largest measured difference. It sits far below any change to what is computed:
the neighbour-count mutation moves the DI by orders of magnitude more. Refusals are asserted with
no tolerance at all.

**The residual risk, stated.** A pair whose DI lies within about 2e-14 of its threshold could be
ranked by engine 7 and refused by engine 8, or the reverse. Engine 8 re-judges every candidate, so
the cost is one bar on which the ranked candidate is refused. It is never a refused pair trading.

**Mutation sweep, `tests/modelling/test_di.py` only**, with `PYTHONDONTWRITEBYTECODE=1`, a byte-copy
restore verified by sha256 after every arm, and a pytest summary line in every verdict. Baseline:
31 passed. **10 applied, 10 killed, 0 survivors:** M1 `>=` at the line (killed by the on-the-line
test); M2 the results reversed; M3 the last row dropped; M4 the wrong row named in the refusal;
M5 the non-finite check removed; M6 the width check removed; M7 the empty-batch shortcut removed;
M8 a 1-D vector read as a batch; M9 `exclude_self=True` in the batch; M10 k + 1. Each was killed by
the test written for it. M2, M3 and M9 were also killed by the position test, which is the one
asserting that each row gets its own score across chunk boundaries.

### Decision: the ranking function restates engines 8 and 13's vector rules instead of moving them into `modelling/`

**Agent:** C-models · **Task:** spec 144 (modelling half) · **Date:** 2026-09-19

**Options.** (a) Move engines 8 and 13's `_vector` and `_as_float_or_none` into
`modelling/ranking.py` and have both engines import them, so there is one copy. (b) Restate the
two rules in `modelling/ranking.py`, leave the engines untouched, and hold the restatement to the
engines with a test that has no double in it.

**Chose (b).** Spec 144's scope limit is "no change to what engines 13, 8, 10, 11, 15 or 16
decide". A refactor of both engines' input handling is a change to the code that decides, in the
same week the chain first runs end to end. It is a behaviour-neutral change in intent, and it is
still a change to two gates that the gate would have to re-prove. The seam test
(`test_every_ranked_expected_move_is_what_engine_8_publishes`) runs the **real** engines 13 and 8
on every ranked pair and requires their published expected move, as a string, to equal the
ranking's. It also requires each probability and anomaly score to be equal, and the DI to agree
within 1e-12. A second test requires each excluded pair to be refused by the real gate with the
same reason code.

*Rejected (a)*, the cleaner end state. **Contestable:** two copies of a rule are the drift
`modelling/` exists to prevent. The test above is what stops them drifting unnoticed, and the
refactor is worth doing once Phase 7 closes.

### The ranking fixture: the learnable series gives every pair the same expected move

**Agent:** C-models · **Task:** spec 144 · **Date:** 2026-09-19

**What happened.** The first version of `tests/modelling/test_ranking.py` trained on the learnable
constructed series (`random_walk=False`), as engine 8's own tests do. The seam test passed, and the
order test failed with "the expected-move order happens to be alphabetical". Renaming the pairs
did not change that. **Every pair's expected move was the same number, −0.014999999932914516.** A
model trained on that series calls every bar a stop with certainty, so the ranking was being
decided by the name tie-break alone. The seam test was comparing one constant with itself.

**Why it matters.** That seam test was green, and green about nothing: a ranking that ignored the
expected move would have passed it.

**Fix.** The ranking fixture trains on the random-walk series and scores rows from its own tail.
On noise the probabilities move from bar to bar, so the six renamed pairs get distinct expected
moves. The order test also asserts that expected-move order, alphabetical order and arrival order
are three **different** orders. A fixture change that made two of them coincide would then fail
that test rather than weaken it.

### Spec 144's modelling half: `modelling/ranking.py` and `research/ranking_check.py`

**Agent:** C-models · **Task:** spec 144 · **Date:** 2026-09-19

**Mutation sweep, `tests/modelling/test_ranking.py` only**, with the same harness guarantees as
spec 137. Baseline: 13 passed. **18 applied, 18 killed.** R1 ascending order; R2 ties by name
descending; R3 the anomaly line inclusive; R4 DI refusals ignored; R5 the row read before the macro
mapping; R6 NaN read as present; R7 the barriers swapped; R8 calibration skipped; R9 the anomaly
sign flipped; R10 the anomaly vector unscaled; R11 a null anomaly threshold accepted; R12 the
detector's inputs unchecked; R13 the feature order read from the artefact itself; R14 an absent
`di.npz` unchecked; R15 the target and stop probabilities swapped in the published record; R17 an
anomaly-input hole recorded as a prediction-input hole; R18 the wrong row's DI published; R16b a
DI-refused pair left out of `excluded`.

**One false survivor, and it was the mutation's fault, not a gap in the tests.** The first R16 was
`extend(... for index in ()) or extend(...)`. The first `extend` returns `None`, so the `or` ran
the real one, making it an equivalent mutant. It is recorded as a checked negative. R16b, which
actually drops the DI-refused pairs, was killed by two tests. R13 needed a new test,
`test_a_run_whose_feature_order_is_permuted_is_refused`. It permutes the manifest and the scaler
together and makes every hash agree, so only the order rebuilt from `modelling/features.py`
objects.

**`research/ranking_check.py`**, the check spec 144 asks for against
`docs/dataset/phase-7-recon-2026-09-19/scripts/q_emrank.py`. Two things were checked:

- **The restatement against the script's own code, on the real window.** On 60 bars sampled from
  folds 379 to 404, `grid_order`'s first choice equals the first pair per bar from q_emrank's
  `sort(...).group_by(decision_ts).first()`, over the frame q_funnel builds. The result is
  **60 of 60** (`scratchpad/c-models/grid_equiv.py`, read-only). 17,179 window bars have a choice.
- **The rules of the choice, on constructed files:** each rule has its own case. Mutation sweep:
  **8 applied, 8 killed.** K1 and K2 the lines inclusive; K3 the row-only DI distribution in place
  of the excluded one; K4 ascending; K5 the universe ignored; K6 a NaN DI kept; K7 agreement judged
  against the outright choice; K8 ties by name descending.

**How the rehearsal must read a disagreement.** The grid ranked every pair the archive held on the
bar. Engine 7 ranks only the pairs its universe filter kept (pair rules, spread, balance), which the
grid never modelled. So `compare` judges agreement against the grid's first choice **among the
pairs engine 7 handed the ranking**, and it names the grid's preferred pairs that engine 7 never saw.
A disagreement inside the universe is the stop spec 144 describes.

### Decision: engine 20 reads the run's trades through the existing window read, with a truncation refusal

**Agent:** c-eval · **Task:** spec 139 · **Date:** 2026-09-19

**What happened.** The gate needs every closed trade of one run. The store's only read is
`recent_closed_trades(limit)`, a newest-first window over every run. c-eval asked b-store for an
unwindowed `closed_trades(run_id=)` three times and heard nothing back while spec 139 sat on the
critical path.

**Options.** (a) Wait for B; (b) have the engine reach SQLite itself (contract rule 4 forbids
it, and `tournament_writes_leaderboard_from_oos` already fails an engine that does); (c) use the
window read, asking for one row more than a cap and **refusing when it gets it**, then filter to
the run in Python.

**Chose (c).** A truncated window can never be judged: it is refused with
`promotion_bad_trade` before any verdict. The cap is 1,000,000 against tens of trades a run.
Tests pin both edges (cap reached: judged; cap exceeded: refused). The request to B was withdrawn
by message. *Cost:* one read of every trade in the database; trivial at a run's size.

### Mutation sweep, engine 20's gate

**Agent:** c-eval · **Task:** spec 139 · **Date:** 2026-09-19

Tests `test_tournament_promotion.py`, `test_tournament.py`, `tests/verify/test_phase7_criteria.py`;
baseline 61 passed. 12 applied, 11 killed on the first pass. **E3, a zero entry notional
accepted: SURVIVED** — the division raised, which the orchestrator would have turned into an
ERROR with no reason code, and no test held the refusal by name. Added
`test_a_trade_with_no_entry_notional_blocks_rather_than_crashing`; re-run: KILLED (baseline 62).
The others: net return read from `realised_pnl_pct` (killed by the test that poisons that
column), a foreign quote accepted, other runs' trades judged, the cap off by one, truncation
tolerated, a second verdict row, the ledger's count not checked against its rows, a row always
promoted, a rejection with no code, the DSR missing from the row, a missing ledger judged at one
trial.

### Spec 141: four criteria registered PENDING-first, and a trap walked into once

**Agent:** c-eval · **Task:** spec 141 · **Date:** 2026-09-19

`backtest_emits_alpha_report`, `promotion_gate_rejects_haircut_edge`, `research_screens_render`
and `fee_scenario_is_replay_only` are registered for phase 7, in the row's order then invariant
2's amendment. **Observed tonight:** `promotion_gate_rejects_haircut_edge` PASS (at the committed
ledger's 1,679 trials the fixture's bound is -0.1855% and it is rejected; at one trial +0.0720%
and promoted; the unwidened bound +0.0720% is above zero, so the rejection is the haircut's);
`fee_scenario_is_replay_only` PASS; the other two PENDING, as expected — the alpha report judges
a digest that exists only when the six-month run ends, and nothing writes a SHAP row until spec
140. Each was observed PENDING on `unbuilt_tree`. FAIL observed on planted defects in a copied
tree, the real file hashed on both sides: for the promotion criterion, no Bonferroni (the model
promoted at N), a gate that refuses everything (the one-trial control unpromoted), and engine 20
ignoring the ledger (judged at N = 1); for the fee criterion, the constructor's refusal removed,
`from_config` reading a key before refusing, a client that refuses replay too, and a stray module
naming the fee schedule three ways.

**The trap, walked into and caught by the test written for it.** The first draft returned
`problem or pending("... (spec 139)")` after `try_import`, and `try_import`'s own PENDING is
truthy, so it won and the spec number never reached the message. The `unbuilt_tree` test that
requires each PENDING to name its spec went red on two of the four. Fixed as the earlier phases
did: pass a FAIL through, otherwise return the criterion's own PENDING.

**Not built tonight, and why.** Spec 141 step 5 (the candle criterion reading `tick_size` from
spec 127's recorded `AssetPairs`) is not done: it changes a Phase 2 criterion's input and is not
on the critical path; `tests/fixtures/kraken/asset_pairs_recorded_2026-09-19.json` exists, so it
is unblocked. `backtest_emits_alpha_report`'s body waits for spec 138's report and spec 143's
digest shape.

### Decision: spec 138's attribution reads the run's database and the partitions it replayed, and nothing else

**Agent:** C-criteria · **Task:** spec 138 · **Date:** 2026-09-19

Each is a how-decision, with the option rejected.

1. **Where the benchmark prices come from.** Chose: spec 128's weekly partitions, located
   through the run's own `runs.scenario_description` (the manifest path and the recorded name
   map), each file checked against the sha256 the run recorded before it is read. *Rejected:*
   the paths in `config/default.yaml`, which describe the next run rather than this one, so a
   partition rebuilt between the run and the report would mark the benchmark on different trades
   with nothing going red. Also rejected: importing the replay client's `TradeTape`, which would
   put a replay-only class on an offline reader's path for the sake of one bisect.
2. **How the store is read.** Chose: a `mode=ro` SQLite URI, as the console's reader does, with
   every row parsed through the store's own row models. *Rejected:* `StoreClient`, which opens
   read-write and has no unwindowed read of positions, trades or rejections; adding them is B's
   lane and a read-only report does not need them.
3. **The daily grid.** Chose: the first equity row, then every whole day after it, up to the
   last row; the final part-day is left off and its length reported. *Rejected:* UTC midnights,
   which cut a partial day at *both* ends of any window not starting at 00:00; and a
   carried-forward equity on a day with no row, which would invent a flat day. A day with no row
   is refused by name.
4. **The basket, on the lead's reading of R8 ("while held").** Between consecutive run ticks it
   earns the mean return of the pairs with a position open at the first tick (`opened_at <= t <
   closed_at`), rebalanced to equal weights every tick, and cash otherwise. *Rejected:* judging
   membership once a day, which would miss nearly every hold, since the 48-bar timeout is 12
   hours. **Found while testing:** a run that held nothing makes the basket an all-zero series,
   and statsmodels fits a rank-deficient design with a pseudo-inverse and only a
   `SingularMatrixWarning`, so it would have printed a confident alpha and beta against a
   benchmark that never moved. `regress` now refuses a benchmark whose return never varies, and
   a run that held nothing reports "not regressed" with the reason. At tier 3 that run is
   plausible, so this is not a corner case.
5. **The HAC lag.** Chose: the larger of the longest hold in grid days less one and the
   Newey-West rule `floor(4 (n/100)^(2/9))`, both stated in the report. *Rejected:* the rule
   alone, 4 at 182 days, too short for a run that ever held across more days; and spec 139's
   trade-overlap lag, which counts trades, not days.
6. **Effective sample size.** Chose: `n (se_ols / se_hac)^2`, capped at `n`, for each
   regression; for trades, the count of non-overlapping hold clusters beside the count.
   *Rejected:* the count alone with a statement, which "every figure carries an effective
   sample size" rules out. **Contestable in the definition, not in any verdict:** it moves no
   interval.
7. **The t quantile** of the per-trade interval comes from `modelling/promotion.py`, so the
   report and the promotion bar share one implementation. *Rejected:* scipy, which ships no
   stubs and would need a new mypy exclusion.

### Spec 141 step 5: the candle criterion's tolerance now comes from the recorded AssetPairs

**Agent:** c-eval · **Task:** spec 141 (prerequisite 9) · **Date:** 2026-09-19

**What happened.** `candles_match_independent_reduction_of_recorded_trades` read its `tick_size`
through the fake client out of `tests/fixtures/kraken/asset_pairs.json`, invented Phase 0 data.
A's spec 127 recorded Kraken's public `AssetPairs` on 2026-09-19 with its URL, capture time and
payload hash. The recorded file is keyed by REST name (`XXBTZUSD`), not by the v2 symbol the
OHLC fixture uses (`BTC/USD`), so the join comes from spec 127's recorded name map
(`pair_names_recorded_2026-09-19.json`, `rest_key` to `v2_symbol`), derived from Kraken's two
answers rather than typed.

**Chose.** Parse the recorded payload through the live client's own `parse_envelope` and
`map_asset_pairs`, the same path a fetched `AssetPairs` takes, and key it by the recorded join.
**No fallback to the invented file**: with no recording the criterion is PENDING naming spec 127.
Rejected: keeping the fake client as a fallback (it would let the invented number back in on any
tree missing the recording, which is exactly the claim the ruling retired). One value differs
between the two files: SOL/USD's tick is 0.01 recorded against 0.001 invented, and on the
committed fixture the largest difference is 0 either way, so the verdict does not move.

**Tests changed with it.** The Phase 2 tests that edit the tolerance (the flip test and the
absent-pair test) now edit the recorded payload, and the message assertions name the recording
instead of the invented file. `test_a_candle_fail_names_the_reference_reduction_and_not_kraken`
asserted that no FAIL message contains the word "Kraken" at all; that was right while nothing in
the criterion came from Kraken and is wrong now that the tolerance does, so it now forbids the
two false claims it existed for ("vs Kraken", "Kraken's own OHLC").

### Spec 141 step 5 built, and the sweep over spec 141's criteria

**Agent:** c-eval · **Task:** spec 141 · **Date:** 2026-09-19

**A correction to the entry above, before it shipped.** The first version parsed the recording
through the live client's `parse_envelope` and `map_asset_pairs`. Ten Phase 2 tests went PENDING
on it: they fabricate `acsoe` with only a candle builder in it, so `acsoe.clients.kraken.rest`
does not exist in their tree, and the criterion reported it missing. Rejected: copying the whole
real package into each fabricated tree (it widens every one of those tests to depend on the Kraken
client). Chose: read the recorded body with `json` directly and take `tick_size` as a positive
decimal or leave the pair out; spec 127's own test already holds the recording to the live
parser. Also found: `tests/verify/test_phase2_criteria.py` was 1,768 CRLF in the working tree
against an LF blob; a literal-anchor patch matched nothing until the file was normalised back to
LF.

On the real tree: PASS, 3 pairs and 9 bars, largest difference 0, the tolerance "taken from
Kraken's public AssetPairs as recorded at 2026-09-19T04:19:59.496708Z".

**Sweep** (tests `tests/verify/test_phase2_criteria.py`, `tests/verify/test_phase7_criteria.py`;
baseline 74 passed): 9 applied, 8 killed. **S3, the oldest recording chosen instead of the
newest: SURVIVED** (only one recording exists, so the choice was invisible). Added
`test_the_newest_recording_is_the_one_read`, which plants a 2026-01-01 recording whose wider
tick would pass a shift the newest fails; re-run KILLED. Killed on the first pass: the invented
file read instead, the join by the wrong key, the tolerance ignored, a stray fee-schedule module
tolerated, string markers not read, the replay positive control dropped, the promotion
criterion's one-trial control dropped, and its rejection at N not required.

### Spec 138 mutation sweep: 24 applied, 24 killed; one first-pass survivor, and a harness that reported no verdict

**Agent:** C-criteria · **Task:** spec 138 · **Date:** 2026-09-19

**What happened.** The first sweep printed `NO SUMMARY` for every arm. The pytest summary line
ends `\r\n` on this machine and the harness's `$`-anchored pattern never matched before the
carriage return, so it could not tell a kill from a survivor. It did print the failing tests, and
the lists were plausible, which is exactly why a verdict without a summary line is not a verdict.
Fixed by stripping carriage returns before matching, and the whole sweep re-run.

**The one real survivor (first pass): M3, the basket excluding the opening tick**
(`opened_at < tick`). The planted tapes moved prices only at day boundaries, so the first six-hour
interval after an open earned nothing whether or not it was counted: the double could not exhibit
the property. Added `test_the_basket_earns_from_the_opening_tick_to_the_closing_tick_and_no_further`,
whose tape moves inside the held interval and again just after the close. It kills M3 and the
mirror arm M24 (holding through the close).

**Result**, `tests/research/test_attribution.py`, 31 tests, `PYTHONDONTWRITEBYTECODE=1`, restored
from a byte copy after every arm and the sha256 checked each time. Every verdict below carries its
pytest summary line in `sweep-138.txt` in my scratchpad. Killed: M1 flat days dropped (7 tests,
including `test_every_day_is_regressed_flat_days_included`); M2 the window pinned to the committed
six months (19); M3/M24 basket bounds; M4 an open position not held to the end; M5 the lag ignoring
holds; M6 one-sided significance; M7 an interval below ten trades; M8 a missing day carried
forward; M9 the funnel counting minute ticks; M10 no carry across an empty partition week; M11 the
sha256 check off; M12 two scenarios in one database accepted; M13 the effective sample size
dropped; M14 the reader opened read-write; M15 one incomplete-vector code forgotten; M16 the tail
not reported; M17 the basket summed rather than averaged; M18 the realised move taken net of fees;
M19 a basket fitted on an all-cash run; M20 the zero-variance guard off; M21 overlapping trades
counted separately; M22 the grid one day short; M23 BTC marked off the grid. Survivors: none.
Checked negatives: none needed.

**Excluded directories.** The sweep ran the owning test file only. The one importer outside it,
`scripts/verify.py`'s `backtest_emits_alpha_report`, stays PENDING on the absent run digest and
cannot see any of these arms.

### Spec 140, first half: the leaderboard screen shows the verdict, and says what it lacks

**Agent:** c-eval · **Task:** spec 140 · **Date:** 2026-09-19

**Built.** The leaderboard gains Fold, Brier, Base-rate Brier, Effective sample and "Why not"
columns beside Sharpe, Deflated and Promoted. The reason is spec 139's code from the verdict
row's JSON `notes`, rendered through `REASON_PROSE`; empty when promoted or never judged. The
effective sample is engine 20's `n x (se_naive / se_hac)^2`, capped at `n`, now written into the
verdict's notes. A seam test runs engine 20's gate and then the real console reader over the same
database, with no double between them.

**Decision: a fold's row shows "not recorded" for its effective sample size.** The spec asks for
the effective sample size on the leaderboard, and the `leaderboard` table has no column for it.
The walk-forward digest has one per fold, and engine 20 does not carry it across. Rejected:
showing the trade count in its place (a number that reads as the answer and is not); adding a
column (a migration through B and the lead, for one display field, the night before a run).
Chose the honest absence, worded apart from an em dash so it cannot read as a zero. Carrying the
digest's figure onto the fold rows is a one-line change in engine 20 if the operator wants it.

**Not built yet: the SHAP writer and the SHAP view.** Engine 19 must write Parquet through the
store, and `StoreClient` has no Parquet surface. A `write_shap` / `read_shap` pair was proposed to
b-store by message; no answer yet. The view waits on the same read.
