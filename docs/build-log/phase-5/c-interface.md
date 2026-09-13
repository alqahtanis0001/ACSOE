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

### The spec 64 fixture's premise is asserted, not assumed

**Agent:** C (second instance) · **Task:** spec 64 · **Date:** 2026-09-13

Engine 3 builds candles from *trades*, so
the tests feed it four trades per bar — open, high, low, close, with the bar's volume split so
the four quantities sum to it exactly — derived from `candles_sample.parquet`. If that
reconstruction did not rebuild the archive's bars, every other test in the file would still pass,
against a price series nobody chose. `test_engine_3s_candles_reproduce_the_archive_bars_they_were_built_from`
compares all five money fields as `Decimal` across more than a hundred bars, which is the check
that keeps the rest of the file meaningful.
