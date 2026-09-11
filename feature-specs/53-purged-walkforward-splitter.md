# 53 — The purged, embargoed walk-forward splitter

**Owner:** C — Interface and models

**Phase:** 4. `research/walkforward.py` is C under the permanent ownership map.

## Goal

`src/acsoe/research/walkforward.py` produces walk-forward folds in which **no training row
whose label window overlaps the test window survives**, and a further embargo span after each
test window is dropped as well. Invariant 10: *walk-forward folds are purged and embargoed;
overlapping label windows must not straddle a train/test boundary.*

## Why this is the most dangerous module in the phase

A splitter that forgets to purge produces a model that looks excellent and is worthless, and
**nothing fails to say so**. There is no crash, no red test and no operator-visible symptom.
A backtest run on leaked folds reports a Sharpe the live system will never see, the promotion
gate in Phase 7 passes it, and the first honest number arrives from a real account. The
defect is invisible to every end-to-end check, because the fold *indices* do not overlap
whether or not the purge ran — the leak is in the **label windows**, which only a test that
builds a straddling window on purpose can see.

## Implementation

1. Folds are rolling: a training window of `backtest.training_window_days`, a test window of
   `backtest.retrain_interval_days`, advancing by the test window. Both come from config.
2. **Purge.** Every label carries the timestamp at which its window ends — spec 52 emits it.
   A training row whose label window ends at or after the start of the test window is
   dropped. Purge on the **label window**, never on the decision bar timestamp: a decision bar
   comfortably inside the training period still has a label built from bars inside the test
   period, and that row is the leak.
3. **Embargo.** After the test window, drop training rows for a further
   `backtest.embargo_bars` bars before allowing training rows back in. This exists because
   serial correlation carries information across the boundary even where no label window
   literally straddles it.
4. The function returns, per fold, the training index, the test index, and the counts purged
   and embargoed — **exposed, not internal.** A count of zero purged rows on a dataset with
   overlapping windows is the symptom of the bug, and it is visible only if the number is
   reported.
5. `tests/research/test_walkforward.py`, C lane.

## The test the operator named, and it is not optional

**Construct a fold in which a training row label window straddles the boundary, and assert
that row is excluded by identity.** Then construct a training row inside the embargo span and
assert the same. Build the rows so the two cases are distinguishable from each other: a test
that would pass with the embargo set to zero is not testing the embargo.

**An end-to-end test cannot see the difference between a correct embargo and none at all.**
Do not substitute one.

## Rules this spec is held to

- **Every assertion must be proven capable of failing**, with the exact mutation and the exact
  red message recorded in `docs/build-log/phase-4/c-interface.md`. Two mutations are named for
  you and both must be observed red: **set the embargo to zero**, and **make the purge a
  no-op**. Each, separately. If either leaves a test green, that test is judging fold indices
  rather than label windows, and it must be rewritten before anything else proceeds.
- A third: **purge on the decision bar timestamp instead of the label window end.** It is the
  most plausible wrong implementation and it passes any test that does not deliberately place
  a decision bar early and its label window late.

## Scope Limits

- Do **not** train, fit or evaluate a model. Phase 5.
- Do **not** label here — spec 52 produces the label and its window end.
- Do **not** read the clock; fold boundaries come from the data timestamps.
- Do **not** silently drop a fold that comes out empty after purging. Report it.

## Check When Done

- `walkforward_folds_purged_and_embargoed` is PASS, and has been observed FAIL under each of
  the three mutations above.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
