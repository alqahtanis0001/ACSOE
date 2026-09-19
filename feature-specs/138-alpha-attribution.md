# 138 — Alpha against the benchmark, from the full equity curve including cash periods

**Owner:** C — Interface and models

**Phase:** 7. The Phase 7 row's first criterion. Reads a finished run's database; decides nothing.

## Goal

An offline report per run, built from the equity snapshots including every flat, cash-only period,
that separates what the benchmark's exposure earned from what selection earned. Every figure
carries an interval and an effective sample size.

## Implementation

1. `research/attribution.py`, new and C's. Read-only over a run database.
2. **Two benchmarks, RULED 2026-09-19 (R8). Report both.**
   - **BTC/USD buy-and-hold** answers the question an examiner asks first. It is built from the same
     time-and-sales partitions the run replayed (spec 128), marked at the same ticks. It is bought at
     the first tick of the window and held to the last.
   - **An equal-weighted basket of the pairs the run actually held** answers the question they ask
     second. It holds equal weights of the pairs the run held, over the periods the run held them,
     and cash otherwise. It is marked from the same partitions at the same ticks, with no fees.
     *This is the lead's reading of "the pairs actually held" as the recommendation proposed it
     ("while held"). If the operator meant the held pairs bought and held over the whole window,
     that is a third series, not a replacement.*
   - **Each benchmark is reported against the run's equity curve including its cash periods.** The
     run's curve is never trimmed to the days it held a position, for either regression.
   - **The window is the run's own**, read from its `runs` row and first and last equity rows, and
     never a constant. A benchmark over a different window than the run's is the quiet failure this
     phase is warned about. A test plants a run whose window differs from the committed six months
     and requires the benchmark to follow it.
   - The glossary's **buy-and-hold** entry points here (spec 126).
3. **Returns on a fixed grid:** daily equity returns, from `equity_snapshots` by `ts`, including
   days with no position. Regress on the benchmark's returns with `statsmodels`, using a HAC
   (Newey–West) covariance with the lag chosen and stated, because consecutive days share open
   positions.
4. **Per-trade statistics beside the regression:** count, pairs, target/stop/timeout mix, net per
   trade with an interval, and the expected move at entry beside the realised return (spec 133's
   columns).
   - **Every interval states that overlapping holds are not independent**, and that the true
     interval is wider.
   - Below ten trades, report no interval and say why.
5. **Joins carry prerequisite 8.** `cycle_id` on `orders` and `positions` is the last tick that
   wrote the row. Join an order to its placing tick by `placed_at` and a position by `opened_at`,
   never by `(run_id, cycle_id)`, and say so in the report.
6. **Coverage travels with the result:**
   - the share of bars refused for an incomplete vector (prerequisite 6);
   - the survivorship count (spec 127);
   - the scenario digest (spec 134).
7. **The funnel:** stage-by-stage counts from `block_records` and `rejections`, in the chain's
   order, so `phase-7-findings.md` §1's pending slots can be filled from the run.

## Scope Limits

- Reads only. No row written to the store, and no leaderboard change.
- No figure is reported without its interval, or without the statement of why it has none.
- Engine 14's router verdicts are not attribution: it has never weighted anything real (the
  operator's carried item 1).

## Check When Done

- On a fabricated equity series with a known alpha and beta, the report recovers both within their
  intervals **against each benchmark**, and a series with the alpha removed is reported as not
  significant.
- A fabricated run with flat days is regressed over every day, flat ones included. Dropping the
  flat days is a planted defect, and it must turn the test red.
- The benchmark window follows a planted run window, and a benchmark pinned to a constant window is
  a planted defect that must turn a test red.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
