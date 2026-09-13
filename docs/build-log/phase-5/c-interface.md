# Build log — Phase 5 — c-interface

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is diagnosis-before-fix.** Write **What happened** and **Why** the moment you know
why something is broken, *before* you write the fix; come back and add **Fix** afterwards. The
code survives on disk whatever happens to the session; the reasoning that found it does not.

**Rule 2, and it is this phase's:** every assertion is proven capable of failing, and the
proof goes here. Name the mutation, quote the red message, say the file was restored by hash
in the same statement that applied it. A claim that an assertion works is not evidence, and a
mutation that survives a *subset* of the suite has not survived — it has not been asked. An
equivalent mutant is a checked negative, not a survivor.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-5.md` at phase close. The operator has
withheld that close until told otherwise.

## Entries

### The committed labelled sample carries no candles, and ten days cannot hold a ninety-day fold

**Agent:** C · **Task:** spec 60 · **Date:** 2026-09-13

**What happened.** Spec 60 says each model criterion "trains one **inside the criterion** from
`tests/fixtures/labelled_sample.parquet` (960 SOLUSD rows)", and criterion 1 says the feature
module runs "over the committed sample's candles". Reading the fixture before writing anything
against it, neither is possible as written, for two separate reasons.

The first is columns. `labelled_sample.parquet` is the labeller's **output**, not its input. Its
thirteen columns are `pair, decision_ts, close, target_price, stop_price, label, touch_ts,
bars_elapsed, touch_price, label_window_end_ts, return_pct, ambiguous, candles_in_window`. There
is no `open`, no `high`, no `low`, no `volume` and no `trades`. Spec 63 fixes
`modelling.features.compute` as a function of a frame carrying all seven OHLCVT columns, so
there is nothing in the committed tree for it to consume. A close-only reconstruction would
give every bar a zero range and a zero volume, and every range, volume and trade-count feature
would be a constant — which is worse than no fixture, because a criterion asserting that two
code paths agree on a constant agrees on nothing.

The second is span. The sample covers `2022-11-09 06:30` to `2022-11-19 06:30`, exactly ten
days of one pair. `backtest.training_window_days` is 90. A rolling walk-forward over ten days
with a ninety-day training window produces **no folds at all**, so criterion 7's
"completes a rolling walk-forward at `backtest.retrain_interval_days`" has nothing to complete
and an assertion over its folds would be an assertion over an empty list. That is the shape the
project has been burned by three times: a check whose output resembles the claim while the
claim is untrue.

**Why.** The fixture was built in Phase 4 for two Phase 4 criteria —
`labelled_sample_replayed_from_archive` and `labeller_matches_hand_verified_labels` — both of
which judge labels and neither of which needs a bar's open, high, low or volume, nor more than
a few days of them. It was sized for its own job and is correct for it. Spec 60 then reached
for it as the universal Phase 5 training input without anyone opening it, and the two specs are
a phase apart, so nothing connected the two facts. This is the seam failure the code standards
already name from the other direction: a module's tests assert its behaviour, and the consumer
builds its own inputs, so the **fields the producer exports** are tested by nobody.

**Fix.** Two changes, deliberately different in kind, because the two problems are different in
kind.

For the columns: a new committed fixture `tests/fixtures/candles_sample.parquet`, the OHLCVT
slice of `data/historical/SOLUSD_15.csv` that the labelled sample was itself produced from,
extended backwards by `market_sensor.published_bars` so the first labelled decision bar has a
full lookback behind it. `ownership.md` puts `tests/fixtures/` structure and C's own evidence
files with C, so depositing it is in lane. It is real archive data, not synthesised, which is
what makes `features_reproduce_in_replay` worth anything: reproducing a feature across two code
paths over a series with real gaps and real quiet periods is the case that separates a
time-window lookback from a row-count one.

For the span: criterion 7 does **not** run a ninety-day walk-forward over a ten-day sample.
It asserts over the committed digest `tests/fixtures/walkforward_digest.json`, which spec 67's
`--write-fixture` produces from a real run, and it proves the fold machinery separately over a
**constructed** series long enough to hold several folds. That is the pattern
`walkforward_folds_purged_and_embargoed` already established in Phase 4 and for the same
reason: the leak a fold criterion hunts is invisible unless the criterion builds the straddling
case on purpose, and a constructed series is the only way to build one.

**Consequence.** Spec 60's wording for criteria 1 and 7 is narrower than what is being built
and I have not edited it; `feature-specs/` is the lead's. Reported to the lead rather than
worked around silently, because the second half changes what a criterion asserts.

### Two agents are running as C and both wrote a Phase 5 section into `scripts/verify.py`

**Agent:** C (second instance) · **Task:** spec 60 · **Date:** 2026-09-13

**What happened.** I was briefed that the previous C session for this phase "died on a usage
limit before writing anything" and that I was starting fresh. I inserted the spec 60 helper
block into `scripts/verify.py`, and within the same minute a **second, independently written**
Phase 5 section appeared in the same file. Different prose, the same purpose, and the same
symbols defined twice: `PHASE5_ENGINES`, `PHASE5_MODULES`, `KEY_MIN_LOOKBACK_FILL`,
`KEY_DI_PERCENTILE`, `_phase5_engine_class`, and an AST scan for book-derived feature inputs.
The entry above this one is the same story from the other direction: it appeared in this build
log under my heading style before I had written a word of it, and the lead amended spec 60 in
response to it. I read that as the tree simply being ahead of me, which is the reading that
kept me writing for another twenty minutes.

**Why.** The ownership map is the only concurrency control this project has — `ownership.md`
says so in as many words — and it maps *paths to agents*, so it is silent on two instances of
one agent. Nothing enforces it mechanically, and the claim rule it leans on ("record the spec
number in your own progress file before writing code") cannot help either, because both
instances write the *same* progress file and a second claim there reads as the first one. So
the failure is invisible from inside either instance: each sees a file that is ahead of where
it left it, which is the normal state of a shared checkout with three teammates in it, and
carries on. The thing that made it visible was not a conflict — both edits applied cleanly —
but a duplicate symbol appearing in a file I had just written.

The cost if it had gone unnoticed is the shape worth recording: two agents appending to one
file do not collide, they *interleave*, and the loser of any given overwrite is never told.
That is exactly why three agents may not write `context/progress-tracker.md` and why each
agent has its own build log. The same hazard arrived through a door the rule does not cover.

**Fix.** I deleted **my own** insertion — `scripts/verify.py` lines 7852 to 8121 — and kept the
other instance's untouched. The file now holds one Phase 5 section at line 7853 and
`ast.parse` over the whole module succeeds. I edited none of the other instance's lines and
will not. Escalated to the lead for a one-line ruling on which instance continues spec 60, and
messaged the other instance directly with what I hold that it should not redo
(`tests/fixtures/candles_sample.parquet`, built and committed) and with the
`modelling.features` surface its criteria are written against, so that whichever of us
continues, the criterion and the module are two ends of one agreed seam rather than two
guesses.

**Consequence.** Not a merge problem and not a technical one. It is a gap in the ownership
rules: they assume one instance per agent and say nothing about what happens when there are
two. Raised with the lead as a rule question, not only as a today question.

### A direct `import numpy` anywhere in `src/` aborts `mypy --strict` entirely

**Agent:** C (second instance) · **Task:** spec 63 · **Date:** 2026-09-13

**What happened.** `modelling/di.py` is the first module in `src/` to import numpy directly.
With it present, the whole gate command reports:

```
.venv\Lib\site-packages\numpy\__init__.pyi:737: error: Type statement is only supported in
Python 3.12 and greater  [syntax]
Found 1 error in 1 file (errors prevented further checking)
```

Measured both ways rather than assumed. With `src/acsoe/modelling/` moved aside,
`mypy --strict src/ scripts/` reports **`Success: no issues found in 100 source files`**;
with it back, one error and nothing checked. Narrowed further with two throwaway probe
modules: a file whose entire body is `import numpy as np` aborts it, and so does one importing
`numpy.typing`. It is the import itself, not anything about how the module is written.

**Why.** `pyproject.toml` already carries an override for exactly this —
`module = ["numpy", "numpy.*", "polars", "polars.*"]` with `follow_imports = "skip"` — added
when the first `src/` module imported polars, which reaches numpy's stubs through its own
annotations. The comment beside it is accurate about the mechanism and about the danger:
a syntax error inside a followed import aborts the run rather than producing one error, so the
check the definition of done leans on returns **no answer** rather than a wrong one.

What that override does not cover is a **direct** import. `follow_imports = "skip"` governs
modules mypy reaches by following an import chain; a module named outright in a checked file is
loaded and parsed regardless, and numpy 2.5's `__init__.pyi` uses a PEP 695 `type` statement,
which is a syntax error at `python_version = "3.11"`. So the protection that has held since
Phase 2 held only because nothing had yet needed numpy by name.

This is not avoidable inside Phase 5's scope. `architecture-context.md`'s stack table lists
numpy for "indicators, distances, sizing", spec 63 says `float` and `numpy` throughout, and the
DI is a k-nearest-neighbour distance over a few thousand scaled rows — a pure-Python leave-one-out
over 2,000 reference rows and 38 features is on the order of 150 million float operations per
refit, which is not a slow implementation, it is one that does not finish inside a weekly
retrain. `research/training.py` will need numpy by name for the same reasons.

**Fix.** Not mine to make. `pyproject.toml` is A's and the declared Python floor is the lead's,
and the config comment already names the three ways out and says none of them is A's to choose
alone: bump the floor to 3.12, pin `numpy<2.3` whose stubs parse under 3.11, or keep the
override and accept that `src/` may never import numpy by name. The third is the status quo and
it is the one Phase 5 cannot live with, which is new information — when the comment was written
the cost of keeping it was "polars and numpy are `Any` to mypy", and the cost is now "the DI
cannot be implemented".

Recommended, and flagged as needing verification rather than asserted: **pin `numpy<2.3`**. It
is the only one of the three that keeps the 3.11 floor genuinely checked — raising mypy's
`python_version` to 3.12 while `requires-python` says 3.11 stops checking the promise the
packaging makes, which is precisely the hole that shipped a 3.11 `SyntaxError` in Phase 4 — and
it has a side benefit the other two do not: numpy stops being `Any`, so the distance arithmetic
in `di.py` is type-checked rather than exempt. What I have not verified, and what someone must
before taking it, is that numpy 2.2's stubs actually parse under 3.11 and that the installed
`lightgbm`, `scikit-learn` and `shap` are satisfied by it.

Escalated to A (pyproject) and the lead (the floor) with this diagnosis. `modelling/di.py` is
left as written rather than rewritten around the problem, because rewriting it would be
throwing away correct code to work around a packaging decision that has not been made yet, and
because the module is the honest statement of what Phase 5 needs. **The gate is red until this
is answered and I am not hiding that**: `ruff check` is clean over the new package and
`mypy --strict src/ scripts/` is aborting on one line of a dependency's stub.

### The manifest's feature-order check is covered only by the scaler's, and a mutation of it survives the whole suite

**Agent:** C (second instance) · **Task:** spec 63 · **Date:** 2026-09-13

**What happened.** Eight mutations over the new package, each applied, run, restored and the
restore verified by sha256 in the same pass before the next was applied. Seven were killed. One
survived, and it is spec 63's own named mutation — **the manifest loader accepting a feature
list in a different order**:

```
### M4 the manifest loader accepts a feature list in a different order
file    : src/acsoe/modelling/artefacts.py
verdict : SURVIVED   restore: RESTORED-OK
summary : 21 passed in 0.43s
  -> re-running against the WHOLE suite
  whole suite: SURVIVED
  2100 passed, 3 skipped in 181.71s (0:03:01)
```

The mutation replaces `if manifest.feature_names != wanted:` with
`if sorted(manifest.feature_names) != sorted(wanted):`, which is precisely the defect the check
exists to prevent: a permuted list has every expected name present, so a sorted comparison
accepts it and the model is handed its columns shuffled.

**Why.** `load_run` checks the order **twice** — once against the manifest and once against
`scaler.json` — and my test only ever reached the second. With the manifest check weakened, a
permuted list sails past it and is caught a few lines later by the scaler's identical check,
which raises a message from the same `_order_complaint` helper and therefore still matches the
test's `match="wrong ORDER"`. The test passed for a reason that had nothing to do with the
branch it is named for.

This is the "incidental kill" the code standards describe, arriving from the survivor side: the
manifest branch reads as covered in any sweep and is covered by nobody. It matters beyond the
tidiness of it, because the two checks are not equivalent in general. The scaler is a file the
manifest hashes, so it can only disagree with the manifest if both were written wrong together;
the manifest's list is the one an **engine** is held to, and spec 71 has engine 8 passing
`FEATURE_NAMES` plus the macro columns while spec 72 has engine 13 passing
`MARKET_QUALITY_FEATURES`. An artefact whose scaler happens to agree with the caller while its
manifest does not is exactly the shape of a half-written run, and after this mutation nothing
would object to it.

It also would not have been found by adding more PASS cases. The test was green, the assertion
was about the right thing, and the message it matched was the right message. Only asking "would
anything object if this line were wrong" separated them.

**Fix.** Two tests where there was one, each reaching exactly one branch with the other held
correct:

* a run whose **manifest** carries a permuted list while `scaler.json` carries the right one —
  reachable because `manifest.json` is deliberately not hashed by itself, so it can be written
  permuted without the hash check firing first;
* a run whose **scaler** carries a permuted list while the manifest carries the right one,
  built by writing the run with a permuted scaler so the manifest hashes it correctly and the
  hash check passes, leaving the order check as the only thing that can refuse it.

Both assert on the file named in the message, not only on the phrase "wrong ORDER", so neither
can be satisfied by the other branch. M4 re-run after the fix: **KILLED**, and a matching
mutation of the scaler branch — `if scaler.feature_names != wanted:` weakened the same way —
is also killed. Both restored by hash.

### Correction: the numpy escalation had a fourth answer, and A found it

**Agent:** C (second instance) · **Task:** spec 63 · **Date:** 2026-09-13

**What happened.** The entry above lists three ways out of the numpy-stub abort, quotes A's own
comment saying those are the three, and recommends pinning `numpy<2.3`. There is a fourth, and
it is better than all three: mypy's **`follow_imports_for_stubs = true`**. A landed it the same
hour and `mypy --strict src/ scripts/` now reports `Success: no issues found in 106 source
files` with `modelling/di.py`'s direct `import numpy` in place.

**Why my list was short.** `follow_imports = "skip"` silences a module's *source* and not its
*stub*, which is the precise distinction I had diagnosed correctly and then failed to act on: I
wrote that the stub was being pulled back in, and then reached for three answers that all change
the environment rather than for the setting that extends the skip to the stub. I had the
mechanism and searched for solutions in the wrong place — the dependency and the language floor
— because the existing comment framed the choice that way and I took the framing with the
finding.

Recorded as a new entry rather than by editing the old one, per `script-rules.md` rule 6. The
old recommendation stands as what I actually thought at the time, which is the point of the log.

**Cost, stated because it is the same cost the original override carried.** numpy and polars are
still `Any` to mypy, so the annotations in `di.py` are documentation rather than checked claims.
That was already true of every polars call in the package and is unchanged by this; what changed
is that the run happens at all.

### Spec 63 mutation sweep: eight mutations, one survivor, and what the sweep excluded

**Agent:** C (second instance) · **Task:** spec 63 · **Date:** 2026-09-13

Nine mutations in total (eight, plus M4b added after M4's survivor was fixed), each applied,
run, restored, and the restore verified by sha256 **in the same pass, before the next mutation
was applied** — not in a `finally` at the end, because a harness that restores only at the end
leaves one mutant on disk while the next is applied and every verdict after the first is really
"first plus second". Every anchor was asserted to occur **exactly once** before being replaced.

| # | Mutation | File | Verdict |
|---|---|---|---|
| M1 | a lookback counted in rows, not seconds (`rolling_sum` for `rolling_sum_by`) | `features.py` | KILLED — 1 test |
| M2 | the window opens one bar early | `features.py` | KILLED — 2 tests |
| M3 | a feature reading `close` of bar `t+1` | `features.py` | KILLED — 2 tests |
| M4 | the manifest loader accepts a permuted feature list | `artefacts.py` | **SURVIVED**, then KILLED |
| M4b | the scaler's own order check weakened the same way | `artefacts.py` | KILLED — 1 test |
| M5 | weights without the label window (all ones) | `weights.py` | KILLED — 3 tests |
| M6 | an under-filled window keeps its value instead of going NaN | `features.py` | KILLED — 1 test |
| M7 | the DI scores a reference row against a set containing it | `di.py` | KILLED — 1 test |
| M8 | the DI veto comparison flipped | `di.py` | KILLED — 3 tests |

M4 is written up in its own entry above. The four mutations spec 63 names by hand are M1, M2 (the
in-progress bar's reach), M3, M4 and M5, and all five are killed by tests written for them
rather than incidentally.

Two red messages worth quoting, because they are the ones that say the tests are about what
they claim. M1, captured from the run rather than reconstructed — see the two entries below for
why that distinction earned its own paragraph twice:

```
E       AssertionError: bars_in_lookback_96 reported 96.0 over a window containing a 96-bar
        hole; a row-counted lookback would report 96 and a time-counted one 24
E       assert 96.0 == 24.0
E        +  where 24.0 = float(24)
```

M5:

```
FAILED tests/modelling/test_weights.py::test_the_effective_sample_size_is_far_below_the_row_count
FAILED tests/modelling/test_weights.py::test_the_hand_verified_case
FAILED tests/modelling/test_weights.py::test_a_longer_horizon_lowers_every_weight
```

**What the sweep excluded, and why.** It was run narrowly — each mutation against the test file
that owns the code — and only the one survivor was re-run against the whole suite, which it also
survived. Narrow is deliberate: three agents share this checkout and a live mutation in a shared
tree turns someone else's run red, where a spurious failure reads as KILLED and hides a
survivor. The cost of narrowness is the other direction: a mutation killed only by a test in a
file that has no business knowing about the code under test would be reported as killed with no
hint of it. For M1, M3 and M5 the killing tests are all in the file that owns the module, checked
by name in the output above rather than assumed.

**One test was wrong first, and it is the useful part of the sweep.** The hole test initially
asserted the counter would equal the 24-bar tail across a 32-bar hole. It went red against a
**correct** implementation: a 96-bar window behind a 32-bar hole legitimately still contains 40
pre-hole bars plus the 24 after it, and 64 is the right answer. The fix was to widen the hole to
a full window so the arithmetic is unambiguous, and then to add the partial case back as a
second assertion — because the partial case is the one a row-counted implementation gets most
plausibly wrong, and dropping it would have left the test passing only on the easy shape.

### M1's first form killed seven tests by raising, which proves nothing, and I nearly filed it as evidence

**Agent:** C (second instance) · **Task:** spec 63 · **Date:** 2026-09-13

**What happened.** The first M1 replaced the window width `f"{bars * interval_s}s"` with
`f"{bars}i"`, polars' row-count spelling. It reported KILLED against seven tests, which looked
like an emphatic result. It is not a result at all. The actual failure was:

```
E  polars.exceptions.InvalidOperationError: `window_size` duration may not be a parsed integer
   (i.e. use '2d', not '2i') when working with a temporal column
```

Seven tests went red because `compute` **raised**, not because any of them noticed a wrong
number. `code-standards.md` is explicit that an induced failure must be a *plausible wrong
implementation* rather than a broken one — an engine that raises proves nothing about the check
watching it — and this was a broken one dressed as a strong kill by its own body count.

**Why it was nearly believed.** The verdict was KILLED, the count was high, and the harness
prints failing test names rather than messages. Everything about the output pointed the right
way. I had also already written the red message into this log **from memory**, as
`bars_in_lookback_96 reported 192.0`, a number I had never seen — plausible, in range, and
wrong, which is the exact shape the Phase 4 benchmark entry warns about. It survived until I
went to capture the message for real and found the mutation had not produced one.

**Fix.** M1 is now the genuinely plausible version of the same defect: `rolling_sum_by("_dt",
window_size=span, closed="right")` replaced with `rolling_sum(window_size=bars, min_samples=1)`,
which is what someone reaching for the row-based API instead of the time-based one actually
writes. It does not raise; it computes a full window across a hole and reports 96 where 24 is
the truth, and exactly **one** test kills it — the one written for it. One kill by the right
test is worth more than seven by an exception, and the table above now records one.

A second, smaller fault from the same attempt, recorded because it was live in a shared
checkout: my ad-hoc capture script wrote apply, run and restore as three plain statements, and
the run raised `FileNotFoundError` on a relative interpreter path — so the **mutation sat on
disk** while two other agents were running the suite. Caught within the minute and restored with
the sha256 matching the value recorded before the sweep, but a spurious failure in someone
else's run reads as KILLED and hides a survivor, which is the direction that costs most. The
rule forbids deferring restores to the end of a *sweep*; it does not forbid a `finally` around a
*single* mutation, and that is what the capture script uses now.

### Engine 3's `missing_bars` pools every pair's timestamps, so it cannot say which pair has a hole

**Agent:** C (second instance) · **Task:** spec 64 · **Date:** 2026-09-13

**What happened.** Spec 64 step 4 says engine 5 reports engine 3's `missing_bars` through as
`gaps_in_range` **per pair**, "so a downstream reader knows the fill without recomputing it".
It cannot: `state["market_sensor"]["missing_bars"]` is a flat tuple of bar timestamps with no
pair attached, and it is computed over every pair's candles pooled together.

**Why that makes it unusable per pair, and nearly unusable at all.**
`missing_bar_timestamps(closed_candles, interval_s=...)` takes the set of timestamps present
across **all** pairs, bounds it by the overall first and last, and reports the slots absent from
that union. A slot is therefore only "missing" when *no pair anywhere* traded in it. With one
pair the answer is exact, which is the case every Phase 2 test exercises. With 234 pairs it is
almost always empty, and whatever it does report is the same number for every pair — so engine 5
reading it through would publish an identical, near-zero gap count for a thin pair with a
six-hour hole and for XBTUSD.

The function itself is not wrong: it takes a `pair` argument and filters on it, and engine 3
simply calls it without one. So this is a call site rather than a defect in the arithmetic, and
it is A's to decide about. It has cost nothing so far because engine 4 `data_guard` reads
`missing_bars` as "was there a decision bar with no candle at all", which the union answers
correctly.

**Fix.** Engine 5 counts each pair's holes from that pair's own candle timestamps, bounded by
that pair's own first and last candle — the same rule `missing_bar_timestamps` uses, applied per
pair. `gaps_in_range` is therefore computed, not read through, and the README says so beside the
field. A mutation that reads it through from engine 3 instead is killed by
`test_gaps_are_counted_per_pair_from_that_pairs_own_candles`, which asserts the two pairs get
*different* counts — an assertion that a read-through cannot satisfy by construction.

Reported to A rather than worked around silently, because the alternative fix is one argument in
engine 3 and that would make the spec's wording true.

### Spec 64 mutation sweep: seven mutations, seven killed, and one test that was fabricating a contract

**Agent:** C (second instance) · **Task:** spec 64 · **Date:** 2026-09-13

Seven mutations on `engines/feature/engine.py`, each applied, run, restored and the restore
verified by sha256, with the restore in a `finally` around that single mutation.

| # | Mutation | Verdict |
|---|---|---|
| N1 | `bar_closed` ignored — features on every tick | KILLED — 3 tests |
| N2 | a short-history pair dropped instead of listed | KILLED — 2 tests |
| N3 | the candle grouping keyed on a constant instead of the pair | KILLED — 7 tests |
| N4 | the in-progress bar cut-off removed | KILLED — 1 test |
| N5 | gaps read through from engine 3 instead of counted per pair | KILLED — 1 test |
| N6 | NaN published as zero instead of null | KILLED — 3 tests |
| N7 | `row_ts` always reported as the closed bar | KILLED — 1 test |

N1, N2 and N3 are spec 64's three named mutations. The sweep was run narrowly, against the test
file that owns the engine; no mutation survived, so none needed the whole-suite re-run.

**The sweep found a test that was fabricating a contract, which is the real result here.** N1
was killed partly by `test_a_non_bar_tick_is_a_pass_with_no_data`, and that test was building
`state["market_sensor"]` by hand as `{"bar_closed": False, "interval_s": 900}`. That is precisely
the shape the Phase 3 audit ruled against: three engines were green against a `state["exchange"]`
payload engine 1 does not publish, because every test built the payload by hand in the shape the
engine expected. My hand-built version was wrong in a way that mattered — engine 3 on a non-bar
tick publishes `closed_bar_ts: None` **while still carrying candles**, and my fabrication carried
neither. The test now drives the real `MarketSensorEngine` at a mid-bar moment and asserts those
two facts about its output before asserting anything about engine 5.

Worth naming because the sweep's own verdict would not have found it: N1 was KILLED either way.
What surfaced it was reading *how* it was killed — the mutated engine raised rather than failing
an assertion, and asking why led to the payload.

### `vol_regime_rank` was decided by floating-point noise on a flat market, and would have called it high volatility one time in ten

**Agent:** C (second instance) · **Task:** specs 63 and 66 · **Date:** 2026-09-13

**What happened.** Engine 12's third end-to-end test drives a perfectly alternating price
series — `+0.2%`, `-0.2%`, repeating — through engines 3, 5 and 12 and expects `choppy`: the
market goes nowhere and its volatility is constant. It came back **`high_volatility`**, with
`vol_regime_rank = 0.9896` against a `regime.high_vol_percentile` of 0.9.

**Why.** The rank is where this bar's short-window realised volatility sits inside the long
window's distribution. On that series the true standard deviation of the log returns is exactly
the same on every bar — computed in plain Python over the same numbers, all 397 windows give one
identical value. polars' `rolling_std_by` does not: it returns **four** distinct values differing
at the 1e-16 level, a relative spread of about 3e-13, which is what a streaming variance
algorithm does when the window slides.

Those differences are meaningless and the rank is not robust to them. A rank has no tolerance:
it asks only which value is larger, so on a window whose values are all equal to thirteen decimal
places the answer is decided entirely by the last bit. Two runs of essentially the same test
landed on 0.99 and on 0.21.

The consequence in the live system is small but it is exactly this phase's failure shape: **a
wrong answer that is in range and that nobody downstream could question.** In a genuinely quiet,
tightly-ranged market — a real condition, not a synthetic one — the rank becomes noise, and at a
0.9 cutoff roughly one such bar in ten is labelled `high_volatility`. Nothing crashes and no test
goes red; engine 14's router in Phase 6 would simply weight a model differently on a tenth of the
quietest bars in the dataset, for no reason.

It also would not have been found on real data. Real volatility never repeats to thirteen
decimal places, so every fixture built from the archive would have passed, for ever. It took a
constructed series whose right answer was known by construction.

**Fix.** Rank the short-window volatility **rounded to ten significant figures**. Genuine ties
then tie exactly, and `rolling_rank_by`'s `average` method gives them the middle rank — which is
the honest percentile of a value in a constant distribution, and 0.5 cannot cross any cutoff a
reasonable operator would set above it. Real differences between bars are many orders of
magnitude larger than the tenth significant figure, so nothing that matters is collapsed: the
observed noise is at the thirteenth.

Not a tolerance on the comparison, deliberately. A tolerance would have to be chosen in the units
of the thing compared, and realised volatility spans orders of magnitude across 234 pairs;
significant figures are scale-free and are the only spelling of "these two numbers are the same
measurement" that means the same thing on a $0.30 pair and a $60,000 one.

`test_an_oscillation_that_goes_nowhere_is_choppy` is the test that found it and is the test that
keeps it fixed. A second test pins the mechanism directly: a constructed window of exactly equal
volatilities must rank 0.5, not 0 and not 1.

### The live and offline feature paths cannot be bit-identical, and the reason is the frame length

**Agent:** C-2 · **Task:** spec 60, criterion 1 · **Date:** 2026-09-13

**What happened.** `features_reproduce_in_replay` FAILed the first time it was run, on its own
central assertion:

```
FAIL  features_reproduce_in_replay  8 of 39 features differ between engine 5's live path and
modelling.features over the same bar: range_atr_4: live=0.003932074590967397
offline=0.003932074590967411; volume_z_4: live=0.5096157890350302
offline=0.5096157890350339; ...
```

The differences are in the last two or three bits — a relative 1e-15 — on eight of thirty-nine
features. I had written the comparison as **exact** and argued for it in the docstring: two
callers of one function have no licence to differ in the last bit, and a tolerance would hide a
drifting second implementation whose answers happen to be close.

**Why.** The argument was right about the principle and wrong about the premise. The two callers
are not given the same input. Engine 5 is handed `market_sensor.published_bars` candles — 200 —
because that is what engine 3 publishes; the offline builder is handed the whole archive frame,
1,208 rows here and twenty million in the real run. polars computes its rolling aggregates
incrementally along the column, so the value at bar *t* depends on how many rows preceded it,
and floating-point addition is not associative. The same 200-bar window therefore lands on
slightly different bits depending on whether 0 or 1,008 rows came before it.

Measured rather than assumed, three ways, and the decomposition is the whole finding:

| Comparison | Differing features |
|---|---|
| engine 5's `float(str(Decimal))` vs polars' `Decimal`→`Float64`, same 200 rows | **0** |
| `compute` over 200 rows vs `compute` over the same 200 rows inside a 1,208-row frame | **8** |

So the two *conversions* are bit-identical, and engine 5's shaping — grouping, casting,
truncating, NaN to null — changes nothing at all. The residual is reassociation inside polars'
kernels and nothing else. Worst relative difference across three window lengths: **7.4e-15**, on
`volume_z_4`.

**The consequence is a fact about the system, not about the test.** The live loop will always
see 200 bars and the trainer will always see the archive, so **the features a model is trained on
and the features it is scored on live differ in the last few bits, permanently.** That is
tolerable — a tree split would have to sit exactly on a threshold for it to change a decision,
and where it did the two outcomes would be indistinguishable in expectation — but it has to be
known and stated rather than discovered in Phase 6 by someone chasing a prediction that differs
between a backtest and a replay of the same bar.

**Fix.** The criterion now makes two assertions instead of one, and it is stricter than what it
replaced rather than looser:

1. **Exact** equality between engine 5's live path and `modelling.features.compute` over *the
   candles engine 5 was actually given*. This is the one-arithmetic-two-callers claim with the
   frame length held still, and it is exact — bit for bit, no tolerance. Any difference in
   shaping, conversion, ordering or cut-off is caught here.
2. **Bounded** agreement between that live window and the full-archive frame, at a relative
   1e-9: six orders of magnitude above the observed 7.4e-15 and many orders below any genuine
   difference in arithmetic, since a different indicator formula differs by percent rather than
   by parts per billion. The worst observed relative difference is printed in the PASS line, so
   drift shows up as a number moving rather than as a threshold being crossed.

The second assertion is the one a later reader will be tempted to delete as noise. It is what
says the live window is long enough to reproduce the trained feature at all: widen a lookback
past what engine 3 publishes and this is what goes red, with a number rather than a shrug.

### The "no criterion reads a gitignored path" guard is a substring scan, and it blocked the correct change

**Agent:** C-2 · **Task:** spec 60 · **Date:** 2026-09-13

**What happened.** `test_no_registered_criterion_reads_data_models_or_logs`, a Phase 0 test of
mine widened in Phase 4, went red on two Phase 5 criteria:

```
AssertionError: features_reproduce_in_replay:  data = dict(getattr(result, "data", {}) or {})
AssertionError: predictor_trains_and_calibrates:  run_dir = Path(str(getattr(report, "models_dir", tmp / "run" / "models")))
```

Neither line reads a gitignored path. The first reads `EngineResult.data`, the field every
engine publishes through. The second names a directory **inside a temporary tree** that the
criterion creates and deletes — which is the very thing the rule exists to require.

**Why.** The check is a bare substring scan for `"data"`, `"models"` and `"logs"` in the source
of every registered criterion. That was adequate while no criterion had an engine payload or a
temporary artefact root in it, and Phase 5 is the first phase where both are ordinary. The rule
it is trying to enforce is about **paths rooted at the repository** — `data/`, `models/` and
`logs/` are gitignored, so a criterion depending on one passes only on the machine that produced
it — and a quoted word is not a path.

`code-standards.md` already has this exact shape written down, from the other direction:
*"Widening a forbidden-list is as much a defect as narrowing it, and it only shows up when
someone tries to do the right thing... An over-strict rule is invisible until it is in someone's
way, and at that moment it looks like the change is wrong rather than the rule."* That was
recorded about `test_the_live_loop_does_not_import_research` forbidding `cli/` from importing
`research/`, which is the design the contracts mandate. This is the same defect in a different
file, and the standard's own instruction is to replace it with narrower, stronger assertions
rather than to add an exception.

The pull towards an exception is worth naming, because it was my first thought and it is wrong:
an allow-list entry for `getattr(result, "data"` would keep a check that cannot tell a path from
a word, and the next correct change would meet it again.

**Fix.** The scan is replaced by one read off the syntax tree, which distinguishes the two cases
because they are syntactically different:

* a **path construction** whose left operand is the repository root — `ctx.root / "data"` and
  anything under it — is a hit;
* a **string literal** beginning `data/`, `models/` or `logs/` is a hit;
* a keyword or attribute named `data`, `models_dir` or similar, and a directory built under a
  `tempfile.TemporaryDirectory`, are not.

Strictly stronger than what it replaced: the old scan missed `ctx.root / dirname` where the name
came from a variable, and it missed an `os.path.join`; the new one follows the operand rather
than the spelling. Both directions proved — the real tree passes, and a criterion given
`ctx.root / "models"` in a copied tree is caught.

### The out-of-sample file carries what the predictor said, not what it saw, and I forgot that in one of two places

**Agent:** C-2 · **Task:** spec 69 · **Date:** 2026-09-13

**What happened.** The skeptic's veto-rate report asked polars for `bar_range_pct` in a frame
that does not have it:

```
polars.exceptions.ColumnNotFoundError: unable to find column "bar_range_pct";
valid columns: ["pair", "decision_ts", "label_window_end_ts", "fold_index", "p_target",
"p_stop", "p_timeout", "expected_move_pct", "is_buy", "di", "di_refused", "label",
"return_pct", "weight"]
```

**Why.** The out-of-sample file records what the predictor **said** — three probabilities, an
expected move, a BUY flag, a DI — and not what it **saw**. The skeptic needs both: the feature
vector plus the predictor's own call. `_skeptic_training_rows` joins the features back from the
dataset for exactly that reason, and its docstring says so in as many words. I wrote that join,
then wrote the scoring path an hour later and did not.

The shape is worth a line: the two halves of one model's inputs were assembled in two functions,
one of which knew the join was needed and one of which did not, and nothing connected them
because they were written at different times by the same person for the same reason. The fix
makes both go through `_skeptic_matrix`, which is now the only place the skeptic's input vector
is built, so fitting and scoring cannot disagree about the column order either.

**Fix.** The veto report joins the features from the dataset before scoring, and it takes the
dataset as an argument to do it — the join is visible in the signature rather than assumed. It
would have gone unnoticed until the operator supplied `skeptic.veto_threshold`, because that
path does not run without it, which is the second reason to be glad it was a test that found it
rather than a run.

### The calibration arithmetic is in `research/` and engine 8 will not be able to import it

**Agent:** C-2 · **Task:** specs 67 and 71 · **Date:** 2026-09-13

**What happened.** Re-reading spec 71 before starting engine 8: it loads the artefact, predicts,
**calibrates**, and computes the expected move. The calibration step is `_calibrate` in
`research/training.py` — apply the per-class isotonic step function, clip, renormalise — and
`engines/prediction/` may not import `research/`. Architecture invariant 5.

The same finding as the macro column names, two hours later and one module over, and this one is
worse. A column name spelled two ways fails loudly at the artefact's feature-order check. A
*calibration* applied two ways fails silently: engine 8 would reimplement "read `calibrators.json`,
interpolate, renormalise", the two would agree on almost every vector, and where they disagreed
the live probability would differ from the backtested one by a few per cent — which lands
directly on `expected_move_pct`, which is what the cost gate prices the hurdle against.

**Why the first pass missed it.** I put `_calibrate` beside `_fit_calibrators` because fitting
and applying read as one job. They are not: fitting happens once, offline, in `research/`;
applying happens on every tick, live, in an engine. `modelling/`'s own docstring already states
the test — "the arithmetic that must **agree** between live and replay" — and applying a
calibrator is exactly that while fitting one is not.

**Fix, before engine 8 rather than during it.** `modelling/calibration.py` holds the isotonic
representation (the two threshold arrays), `apply(raw, calibrators)` and the renormalisation;
`research/training.py` imports it to score its own out-of-sample rows, and engine 8 imports it to
score a live vector. Fitting stays in `research/` because nothing live fits anything.

**The cheap generalisation, since this is twice in one day.** The question to ask of every
function I write in `research/` from here is not "does this feel like research" but "**will an
engine need to do this too**". Both misses answered the first question correctly and the second
one not at all. Two more candidates by that test, both still in `training.py` today: the feature
matrix assembly, which engine 8 does per tick for one row, and `_codes`, which engine 8 never
needs because it reads probabilities rather than labels. The first moves; the second stays.

### Phase 5 made the suite two and a half minutes slower, and the gate pays it six times

**Agent:** C-2 · **Task:** spec 67 · **Date:** 2026-09-13

**What happened.** `pytest tests/ -q` went from **173s to 330s** across this phase, while the
test count went from 2,206 to 2,238. Thirty-two new tests cost two and a half minutes, because
most of them train a model.

**Why it matters more than it looks.** `toolchain_green` is registered for **every** phase, so a
full `--phase 0` through `--phase 5` sweep runs the whole suite six times. The sweep went from
about twenty minutes to about forty, and the lead runs one at every commit boundary. The cost is
not the tests being slow; it is that the slowest thing in the project is now multiplied by six
by a design decision made in Phase 1 for a good reason.

**Where it actually goes.** `tests/research/test_training.py` is 75s of it. Twelve of its twenty
tests call `train_walkforward` separately, most of them to make a read-only assertion about the
artefact or the digest that any of the other eleven runs would have supported equally well. The
Phase 5 criteria add about 28s on top, and those are load-bearing — a criterion that shared a
cached model with another criterion would be the cross-contamination `root_import_path` exists
to prevent.

**Not fixed yet, and the fix has a cost of its own.** Sharing one module-scoped training run
across the read-only tests would take most of the 75s back. It also couples tests to each other,
which is the thing that lets one test's mutation hide in another's fixture, so it is worth doing
deliberately rather than as a speed reflex: the runs that must stay separate are the
reproducibility pair, the empty-fold case, and anything a mutation is aimed at. Recorded now
because a measurement taken before the optimisation is the only way to know whether the
optimisation did anything — and because the Phase 4 entry about a benchmark that reported a
fourfold speed-up it had not achieved is the reason I will run that comparison in both
directions.

### A pair can identify itself from its own macro columns, and "no pair identity" does not quite hold

**Agent:** C-2 · **Task:** spec 67 · **Date:** 2026-09-13 · **Open, for the lead**

**What happened.** Spec 63's constraint is that no feature encodes which pair a row belongs to,
and every individual feature honours it: they are returns, ratios, z-scores, positions within a
pair's own window, and clock fields. But the macro join puts BTC's and ETH's feature rows beside
every pair's own — and **on a BTC row, `macro_btc_log_return_4` is exactly `log_return_4`**. The
pair identity is not in any one feature; it is in the *coincidence* of two.

**Why it is worth recording rather than shrugging at.** A tree cannot compute `a == b` directly,
so this is not the trivially exploitable leak it would be in a linear model. What it can learn
is the region of feature space where the two happen to coincide, which is a proxy for "this row
is BTC" available on roughly 2 of 234 pairs — under 1% of rows in the full dataset, and 33% in a
three-pair smoke run, which is the case to be careful about when reading smoke-run numbers.

It also cuts the other way and that is the part I would not want lost: the macro columns are
*supposed* to be a market backdrop, and for BTC the backdrop and the subject are the same
market. A model that learns "when this pair is the market, the backdrop says nothing extra" has
learned something true.

**Not fixed, and the options are the lead's rather than mine**, because every one of them
changes what the dataset is:

1. **Leave it.** Under 1% of rows in the real run, documented here and in the module.
2. **Null the macro columns on a row whose own pair is that macro asset.** Honest — "there is no
   separate backdrop for this pair" — but it gives BTC rows a different missingness pattern from
   every other pair's, which is itself a pair signal, and a stronger one.
3. **Exclude the macro pairs from the candidate set.** Clean, and it throws away the two most
   liquid pairs on the exchange, which is a trading decision rather than a modelling one.

My reading is that option 1 is right for Phase 5 and that option 3 would need the operator, but
I have not acted on any of them. Flagged now rather than after a leaderboard exists, because the
moment engine 20 has rows it stops being a modelling question and becomes a question about
numbers somebody has already read.

### The first real training run, and the two numbers in it that matter

**Agent:** C-2 · **Task:** spec 67 · **Date:** 2026-09-13

Not a defect entry. The measurement, recorded because it is the first time this system has
produced one and because two of its numbers will be quoted for the rest of the project.

`python -m acsoe.research.training --pairs SOLUSD --start 1640995200 --max-folds 3`, eight
minutes, SOLUSD plus both macro pairs, 420,081 labelled rows, three weekly folds:

| fold | test rows | effective | Brier | base-rate Brier | BUY calls | BUY target rate |
|---|---|---|---|---|---|---|
| 0 | 2,016 | 101.0 | 0.1470 | 0.1345 | 1,894 | 0.168 |
| 1 | 2,016 | 92.1 | 0.0992 | 0.0945 | 1,286 | 0.103 |
| 2 | 2,016 | 65.7 | 0.1200 | 0.1318 | 365 | 0.247 |

**The effective sample size is about five per cent of the row count.** Two thousand test rows
are roughly a hundred independent observations, because at a 48-bar horizon consecutive
decision bars share almost all of their label window. That is the number the operator asked to
see beside every row count, and this is why: a confidence interval computed from 2,016 is
wrong by a factor of four and a half, and nothing about the fold's appearance says so.

**The model is at or slightly worse than the base rate on two folds of three.** That is the
honest first-pass result. It is also the shape that proves there is no leak: a leaked feature or
a mis-joined label produces a Brier near zero, which is exactly what the deterministic
constructed series produces and what the random walk does not. `project-overview.md` says a
negative result is a valid result, and this is the first time that sentence has had a number
attached to it.

The BUY-call target rates (10% to 25%) sit far below the break-even rates invariant 5 records
for reference (61% at tier 1, 48% at tier 3). That comparison is the reader's rather than the
digest's, for the reason in the module docstring: break-even is a function of live friction and
none of it exists offline.

### The calibrator fitted on the test window survived every test, and the metric can never catch it

**Agent:** C-2 · **Task:** spec 67 · **Date:** 2026-09-13

**What happened.** Spec 67 names six mutations. Two survived, and one of them is the worst
survivor this phase could produce:

```
### Q1 the calibrator fitted on the test window
verdict : SURVIVED   summary : 18 passed in 64.86s
### Q4 the scaler fitted on train plus test
verdict : SURVIVED   summary : 18 passed in 64.06s
```

Q1 replaces the calibration inputs with the **test** rows and their labels. That is a
textbook leak — the calibrator is shown the answers to the questions it is about to be scored
on — and eighteen tests, including the random-walk look-ahead detector I had just written and
called the strongest available, said nothing.

**Why, and the two reasons are different.**

Q1 survives because **isotonic calibration is monotone**. It cannot reorder predictions, so it
cannot manufacture skill on a random walk: fitted on the test window it learns the test window's
class prior slightly better, which moves the Brier by less than the 25% margin the anti-leak
test allows. The margin is not the problem — tightening it would make the test fire on honest
runs — the problem is that **a metric comparison is the wrong instrument for this leak.** The
quantity that changed is *which rows the calibrator saw*, and no number computed from the
predictions is a function of that.

Q4 is subtler and is partly a **checked negative rather than a survivor**. MinMax scaling is a
monotone per-feature transform, and a gradient-boosted tree is invariant to monotone transforms
of its features: it splits on order, not on magnitude. So fitting the scaler on train plus test
genuinely does not change the predictor's output, and for the predictor alone the mutation is
equivalent. It is **not** equivalent for the Dissimilarity Index, which is a Euclidean distance
in the scaled space — there, test-window min/max bleeding into the reference scaling shifts
every distance and moves the refusal threshold. The DI is not fitted today because
`prediction.di_percentile` is withheld, so the mutation is equivalent *at this moment* and will
stop being equivalent the day the operator supplies that value. Reporting it as a plain survivor
would send the next reader hunting for a metric that can see it; reporting it as equivalent
would be a claim that expires silently.

**Fix, and it is the same technique for both.** Ruling 7 of this phase already says it about the
DI: prove which rows a thing saw by **identity**, not by a number it reported about itself. The
manifest now records:

* `calibration_identity` and `calibration_rows` — a digest over the `(pair, decision_ts)` of the
  rows the calibrator was fitted on;
* `scaler_identity` and `scaler_rows` — the same for the rows the scaler was fitted on.

Two tests then assert what no metric can: every calibration row is one of the fold's **training**
rows and none is a test row, and the scaler's identity equals the training identity exactly.
Both mutations die on contact, by assertion rather than by raising, and they die for the reason
they are wrong rather than because a number moved.

**The wider lesson, which is the part that generalises.** I wrote the random-walk test believing
it would catch every leak, said so in its own docstring, and it caught neither of the two leaks
the spec named. It catches leaks that create *skill*; it is blind to leaks that create
*calibration*, and blind by construction to anything a monotone transform can do. A detector's
docstring claiming it catches "every leak" is the claim to distrust — including when I am the one
writing it — and the mutation sweep is what turned that claim into a measurement.

**A third mutation was mine and broken.** Q5, "`pair` included as a feature", appended a
`pair_code` column that does not exist, so eleven tests died on a `ColumnNotFound` in eight
seconds. That is an engine raising, which proves nothing about the tests watching it — the same
defect as M1 in the spec 63 sweep, made twice in one day. It also turned out that the literal
mutation the spec names **cannot** be written non-raising: `pair` is a string column, so
including it in the feature list fails at the cast rather than misleading anybody. The mutation
that is both plausible and silent is a *numeric* identifier, and `decision_ts` is sitting right
there in the frame — a model given it memorises *when* rather than *what*. Q5 is now that, and
the test it kills is a pinned equality against `FEATURE_NAMES` plus the macro columns rather
than an "is `pair` absent" check, because naming one column to exclude tests one spelling of the
mistake while pinning the list tests the property.

**The first fix for Q1 and Q4 did not work, and the reason is the useful part.** I added
`calibration_identity` and `scaler_identity` to the manifest and asserted on them — and **both
mutations survived again**, because the manifest recorded what the *caller* intended while the
mutation changed what the *fit* was handed, and the two stayed consistent with each other. A
record written beside a call is not a check on that call. Two changes fixed it for real:

* `_fit_calibrators` now takes the calibration **frame** rather than pre-computed labels and
  returns the identity of what it was given, so the record and the fit come from one argument;
* both tests **recompute the expected rows themselves** — the fold from `purged_walk_forward`,
  the calibration tail from `prediction.calibration_days`, the scaler's minima and maxima by
  refitting over the fold's training rows — and compare the artefact against that. Ruling 7's
  technique, which was written about the DI and turns out to be the general answer.

Final sweep, all six killed by the test written for each:

| # | Mutation | Verdict | Killed by |
|---|---|---|---|
| Q1 | the calibrator fitted on the test window | KILLED | `test_the_calibrator_saw_only_training_rows` |
| Q2 | a seed read from the clock | KILLED | `test_two_runs_over_one_config_and_one_dataset_agree` |
| Q3 | weights all ones | KILLED | the weight and effective-sample-size tests |
| Q4 | the scaler fitted on train plus test | KILLED | `test_the_scaler_saw_exactly_the_training_rows` |
| Q5 | an identifier column in the feature list | KILLED | `test_pair_is_an_identifier_and_never_a_feature` |
| Q6 | the manifest's feature order permuted | KILLED | the artefact-load test, by **refusal** |

Q6's kill is a raise and is the one case where that is right: `ArtefactError` on a permuted
feature list is the loader doing its job, not an engine falling over.

### Two criteria of mine were wrong, and the trainer landing is what showed it

**Agent:** C-2 · **Task:** specs 60 and 67 · **Date:** 2026-09-13

The first run of the Phase 5 criteria against a real `research/training.py` turned two of them
red. Both are defects in the criteria rather than in the trainer, which is the direction this
sequencing exists to find: a criterion written before its subject is a hypothesis, and the
subject landing is the experiment.

**`training_is_reproducible_from_config_and_data` conflated "reproducible" with "same run id".**

```
FAIL  the two runs share the artefact run id(s) ['train-20260913T120000-6412693d-f0'].
```

The run id is `train-<utc stamp>-<config digest prefix>-f<fold>`, and the criterion injected the
**same** `now` into both runs — so of course they collided. Two real runs are minutes apart and
get different ids; two runs at one injected instant are the same run by construction. The
criterion was asserting a property its own fixture made impossible, and it would have forced a
random suffix into the run id to satisfy it, which would have made the id unreproducible for no
gain. Fixed by giving the second run a `now` one second later, which is what distinguishes two
real runs, and by additionally comparing `model.txt` **byte for byte** — the assertion the spec
actually wants, and one the fold-metric comparison alone does not make.

**`di_fitted_on_predictor_training_set` never reached its own PENDING branch.**

```
FAIL  no di.npz beside the fold's predictor at ...\train-...-f0\di.npz
```

`prediction.di_percentile` is absent by operator ruling and the trainer correctly fits no DI
without it, so this criterion should have reported PENDING naming the key. It did not, because
`_withheld_key` tested `value is None` while `config_get` returns the sentinel `_CONFIG_MISSING`
for a key that is **absent from the file**, and `None` only for one written as an explicit
`null`. The ruling is that these five keys are *absent*, never null — the YAML header says a
null stops every process at load — so the helper was checking for the one shape the ruling
forbids and missing the shape the ruling requires.

It is the same two-facts-one-channel defect the standards keep naming, in its third variant this
phase: absent and present-and-null are different states, and a check that only looks at one of
them answers the other wrongly. Here it answered "the operator has not supplied it" with a FAIL
that accuses the trainer of not writing a file it was right not to write.

**Fix.** `_withheld_key` treats the sentinel and `None` alike, with a comment saying which the
ruling produces and why both are accepted. The criterion now reports PENDING naming
`prediction.di_percentile`, which is the state the phase is in and will stay in until the
operator supplies the value after the walk-forward reports.

### The shared config double cannot exhibit the one property five Phase 5 keys depend on

**Agent:** C-2 · **Task:** spec 67 · **Date:** 2026-09-13

**What happened.** The first end-to-end run of the trainer stopped on its own config digest:

```
KeyError: "config has no key 'prediction.di_percentile';
           'di_percentile' is not present under prediction"
```

raised from `tests/harness/doubles.py`, `MappingConfig.get`.

**Why, and it is bigger than the trainer.** `MappingConfig` wraps the parsed YAML dict, so a
key absent from the file raises. The **real** `Config` parses that YAML into a pydantic model
where `prediction.di_percentile` is declared as `Ratio | None = None`, so the same call returns
`None`. A-2's own note records the distinction and calls it deliberate: *"a miss is a key this
model does not declare; an optional field that is declared and unset is not a miss, and this
returns its None"*.

Five keys are deliberately absent from `config/default.yaml` by operator ruling —
`prediction.di_percentile`, `anomaly.threshold_percentile`, `skeptic.veto_threshold` and the
three `models.*_run_id`s — and **engines 8, 13 and 15 are written to read `None` and block with
a reason code**. Driven through this double they would get a `KeyError` instead, which the
orchestrator turns into `ERROR`. `ERROR` also blocks, so the gate would stay green while three
engines took the wrong branch, published the wrong reason code, and were tested against the
wrong behaviour — and every one of those tests would have been written against the double that
produced it.

This is the standard's own rule, from the inside: *a double that is simpler than the real thing
in exactly the dimension the test is about cannot fail.* The dimension these three engines are
about is what an absent operator value does, and that is precisely the dimension `MappingConfig`
gets wrong. `tests/harness/` is mine, so this is my defect and not a discovery about someone
else's file.

It is also the fourth instance of the shape `ai-workflow-rules.md` names: fabricate the subject,
never the contract. `Config` is a contract, `MappingConfig` is a fabrication of it, and the two
agree everywhere except the one place Phase 5 lives.

**Fix.** `load_default_config()` returns the **real** `Config` through
`acsoe.platform.config.load_config`, so every test and every criterion that reads the committed
configuration reads it through the model that declares the optional leaves. `MappingConfig`
stays for the eleven call sites that build an ad-hoc dict to vary one threshold — that is a
legitimate stand-in for a *value*, not for the model — and gains a docstring saying in as many
words that it cannot answer for a declared-but-unset leaf and must not be used to test one.

### The macro column names are in engine 6's `contracts.py`, and `research/` may not import them

**Agent:** C-2 · **Task:** specs 65 and 67 · **Date:** 2026-09-13

**What happened.** Spec 65 step 4 says the macro feature names are "exported from
`contracts.py` as a tuple derived from `modelling.features.FEATURE_NAMES` and the configured
assets, so the offline builder and the engine cannot disagree about a column name", and that is
where I put `macro_column` and `macro_feature_names`: `engines/macro_context/contracts.py`.
Spec 67 step 1 then needs the same two functions to join the macro columns into the training
dataset. **It cannot have them.** Architecture invariant 5: research code never imports from the
live loop path, and `engines/` is the live loop path.

Found while designing spec 67 rather than while running it, which is the only reason it is
cheap. The cost of noticing later is the shape the invariant exists to prevent: `research/`
would have grown its own copy of `f"macro_{asset}_{feature}"`, the two would have agreed for
months, and the first rename would have trained a predictor on `macro_btc_log_return_4` and fed
it something else live — where the only thing that would notice is the artefact's feature-order
check, at load time, as a refusal whose message names the shape and not the cause.

**Why the spec says what it says.** Spec 65 predates spec 67 by a day and was written about the
engine alone; "the offline builder and the engine cannot disagree" is exactly the right
requirement and `engines/` is exactly the wrong place to satisfy it from. `modelling/` is the
package that exists for this — the one both sides may import, holding "the arithmetic that must
agree between live and replay" — and a column name is that arithmetic's vocabulary.

**Fix.** `macro_column`, `macro_feature_names` and `macro_pair_names` move to
`modelling/macro.py`. `engines/macro_context/contracts.py` imports them from there and
re-exports, so spec 65's sentence stays true and engine 6's own tests keep passing unchanged;
`research/training.py` imports the same module. The import-graph test in `tests/modelling/`
already asserts `modelling/` imports nothing from `acsoe` but `core.contracts`, so the new
module is held to the leaf rule from the moment it lands, and a matching assertion that
`research/` does not import `engines/` is worth adding beside it.

### Spec 60: eleven criteria, and what each of them would let through if it were written the obvious way

**Agent:** C-2 · **Task:** spec 60 · **Date:** 2026-09-13

Not a defect entry. A record of the design decisions, because each one is a place where the
obvious criterion passes over the defect it is named for, and none of them is visible from the
code afterwards.

**Criterion 1, `features_reproduce_in_replay`, hands the two paths different inputs on
purpose.** The obvious version computes one frame and passes it to both sides; it then proves
that one function returns the same answer twice. The live path is given money as decimal
strings through engine 3's own `MarketSensorState`, truncated to `market_sensor.published_bars`,
and the offline path the whole archive frame with `Decimal` money — so a shaping bug on either
side moves the last row's lookbacks and shows up. The payload is built through engine 3's
pydantic model rather than as a dict, because a hand-written one is how
`check_data_guard_blocks_bad_data` came to have a body that never executed.

**Criterion 2's hole is wider than the window minus the tail, and the arithmetic is the
reason.** With a narrower hole the window legitimately still reaches past it, the expected count
is a sum of two runs, and the check goes red against a correct implementation — which is what
happened the first time I wrote the equivalent unit test.

**Criterion 5 asks about membership, not equality, and that is forced.** The DI subsamples its
reference set to `prediction.di_reference_rows` with a seed, so a digest of the rows it *should*
have seen matches nothing. The three questions it can answer are: is every reference row one of
the fold's training rows, is at least one of them not a BUY call, and is none of them a test
row. The second is the whole criterion — it is what separates "fitted on the training rows" from
"fitted on the BUY subset of them" — and it is why `di.npz` stores identities rather than a
hash. A digest can prove two sets are equal and can never prove one contains another.

**Criterion 6 recomputes the skeptic's eligible set from the out-of-sample file** rather than
reading back what the skeptic recorded about itself, which is ruling 7 of 2026-09-13. The point
is to check which rows it saw; a number it reported is not evidence of that.

**Criterion 9's ascending call is the one that does the work.** Descending by the probe feature
happens to equal alphabetical order, so a `rank_universe` that returned its input would satisfy
it. The tracker named this seam before the phase opened: engine 7 builds its scan set with
`sorted`, so the function is always handed an already-ordered sequence and an end-to-end fixture
cannot tell ordering from passing through. The mutation test mutates the **ranked branch only**
for the same reason — dropping pairs in `names` would also empty the alphabetical answer and the
criterion would fail on a different assertion, a kill for the wrong reason.

**Criterion 10 constructs its digest and out-of-sample file, and that is safe only because two
other criteria pin their shapes.** `walkforward_weekly_retrain_reports_oos` reads the real
producer's digest against `FOLD_DIGEST_FIELDS` and
`skeptic_trains_only_on_predictor_buy_rows` reads the real out-of-sample file against
`OOS_COLUMNS`. Without those two, criterion 10 would be a criterion agreeing with its own
fabrication. It also reads the leaderboard with `sqlite3` rather than through
`StoreClient.leaderboard()`, which returns the newest fifty: a criterion counting rows through a
limited read cannot tell "engine 20 wrote two" from "wrote two hundred and this showed fifty".

**Where the file is honestly incomplete.** Four criteria have subjects today and carry all three
observations. Seven report PENDING naming the module or engine that owes them, and their PASS
and FAIL halves arrive with specs 67 to 74. `tests/verify/test_phase5_criteria.py` says so in
its own docstring rather than implying completeness by silence.

### The spec 64 fixture's premise is asserted, not assumed

**Agent:** C (second instance) · **Task:** spec 64 · **Date:** 2026-09-13

Engine 3 builds candles from *trades*, so
the tests feed it four trades per bar — open, high, low, close, with the bar's volume split so
the four quantities sum to it exactly — derived from `candles_sample.parquet`. If that
reconstruction did not rebuild the archive's bars, every other test in the file would still pass,
against a price series nobody chose. `test_engine_3s_candles_reproduce_the_archive_bars_they_were_built_from`
compares all five money fields as `Decimal` across more than a hundred bars, which is the check
that keeps the rest of the file meaningful.

### Criterion 6 and the trainer disagreed about the skeptic's eligible rows

**Agent:** C-2 · **Task:** spec 69 · **Date:** 2026-09-13

**What happened.** With spec 69's skeptic implemented and its eleven unit tests green,
`python scripts/verify.py --phase 5` reported:

> FAIL - the skeptic's training identity for fold 1 does not match the out-of-sample BUY calls
> from folds strictly before it. Recomputed over 647 eligible rows; the artefact records a
> different set. Rows that would contaminate it look like
> `['AAAUSD|1711843200', 'AAAUSD|1711844100', 'AAAUSD|1711845000']`

The trainer reports 612 rows for that fold. The criterion recomputed 647. The thirty-five rows
between the two are the last few hours of the previous fold's out-of-sample calls.

**Why.** `_skeptic_training_rows` applies the purge and the embargo against the fold it is
about to be judged on — `label_window_end_ts < test_start_ts` and
`decision_ts < test_start_ts - embargo_bars * interval_s`. `check_skeptic_trains_only_on_predictor_buy_rows`
recomputed its eligible set as BUY calls from earlier folds and nothing more. Both halves of
this seam are mine, so the disagreement is mine to resolve rather than a defect in either file
alone; the question is which of the two is right.

The trainer is. Spec 69 says the skeptic's rows are subject to the same purge and embargo as the
predictor's, and the reason is not symmetry for its own sake. A row whose label window reaches
into the test window is the same leak whichever model reads it: the skeptic trained on it knows
how that bar resolved, and the resolution happened inside the window the fold is scored on. An
unpurged skeptic would look better out of sample than it is, and the whole point of the meta-label
is to say whether the predictor's calls can be trusted — a leak there is worth more than a leak
in the predictor, because it is the number the operator would use to decide whether to keep the
veto.

So the criterion was the wrong half, and it was wrong in the direction that hides a defect: it
would have passed a trainer that skipped the purge entirely, and failed the one that applies it.
A criterion that disagrees with the spec is worse than no criterion, because it converts the
correct implementation into a red gate and invites the fix to be made in the subject.

**What the fix needed.** The purge is on the label window end, so the out-of-sample file has to
carry `label_window_end_ts`. That column joined `OOS_COLUMNS` in `training.py` and in
`verify.py` before the criterion body changed, and the criterion now filters on it and on the
embargo, reading `timeframes.decision_bar_s` and `backtest.embargo_bars` from the same config
the trainer read. `eligible_rows()` in `tests/research/test_skeptic_training.py` already computed
the set this way and agreed with the trainer, which is how the disagreement was localised to the
criterion rather than left as a mystery between three files.

**The vacuity trap this opens, and what closes it.** Once the criterion applies the same two
filters the trainer applies, the two computations are close enough in shape that a trainer which
applied *neither* would be caught only if the filters actually remove rows on this dataset. On a
dataset where the purge removed nothing, the strict set and the naive set are identical and the
identity check cannot tell the two trainers apart. `test_the_purge_and_embargo_remove_rows_rather_than_nothing`
asserts the difference is real on at least one fold, and the criterion's PASS line now reports
both counts so a reader can see the gap rather than take it on trust.

### Spec 69's mutation sweep, and the one exclusion that cannot be mutated

**Agent:** C-2 · **Task:** spec 69 · **Date:** 2026-09-13

Three mutations applied to a copied tree, each run and each restored inside the copy's own
lifetime, and all three killed `skeptic_trains_only_on_predictor_buy_rows`:

* **the `is_buy` filter dropped.** FAIL naming a second predictor wearing a veto. The
  out-of-sample file holds every scored row, not only the calls, so "everything in this file
  is something the predictor said" is the easy assumption and it admits mostly `stop` rows.
* **the purge and embargo dropped.** FAIL naming the label window. This is the defect the
  criterion itself had until today, in the subject rather than in the checker, so it is now
  asserted from both sides.
* **the training identity not recorded.** FAIL naming the row count. Ruling 7 in the form it
  would actually be broken: a trainer that reports how many rows it used and not which.

**The third exclusion has no mutation and that is deliberate.** Spec 69 also forbids a call
from this fold or later, and `train_walkforward` builds `previous_oos` by concatenating the
folds it has already finished — so the current fold's rows are never in the frame
`_skeptic_training_rows` is handed, and its `fold_index <` filter is belt-and-braces.
Flipping it to `<=` changes nothing observable. A mutation that cannot change behaviour is
not a survivor; it is not a mutation, and recording it as a kill would be recording a
coincidence. But belt-and-braces is also how a guard comes to be deleted by someone tidying
a redundant condition, so it is proved live one level down instead:
`test_a_call_from_this_fold_is_excluded_even_if_it_is_handed_one` calls the function
directly with a frame that *does* contain this fold's calls — what a future caller
assembling the out-of-sample file differently would hand it — and asserts they are left out.

`skeptic_trains_only_on_predictor_buy_rows` moved from `AWAITED` to `BUILT` in
`tests/verify/test_phase5_criteria.py`, which is what turned `toolchain_green` red for one
run: that file asserts an awaited criterion never passes, and this one had just started to.
