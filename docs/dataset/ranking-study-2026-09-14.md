# Candidate ranking study over the full run, `train-20260913T205245-067b2b9d`

**Evidence for the operator's ruling on `scout.rank_feature`. It recommends nothing and sets nothing.** Ruled 2026-09-15: no feature; alphabetical stays. Recorded as an open question for Phase 7, not a finding (see the last section).
Covers 405 of 457 folds (test weeks 2017-04-01 to 2024-12-28; the run died at fold 405).
Supersedes `ranking-study-2026-09-13.json` as evidence: that one was two pairs on a constructed
series and said so in its own `limitation`.

Produced by the committed spec 75 command, unmodified, on `690b4d3`:

    python -m acsoe.research.training --config config/default.yaml \
      --ranking-study data/derived/oos_train-20260913T205245-067b2b9d.parquet \
      --dataset data/derived/dataset_20260913T205245.parquet

exit 0 in 3.5 minutes, writing `ranking-study-2026-09-14.json`. On every decision bar with two or
more pairs (271,645 bars, 15,978,781 of 15,978,803 out-of-sample rows, 234 pairs), the pair
engine 7's `rank_universe` rule would put first by each feature in each direction is taken and its
realised triple-barrier outcome counted. The DI is not fitted for this run, so `di_refused_rate` is
null throughout. The by-year and thinness split below is
`ranking-study-2026-09-14-by-year.py` / `.json`, which takes the chosen pair from the study's own
`chosen_pairs` and joins nothing else.

**All rates are before friction.** `mean_return_pct` is the mean realised barrier return of the
taken pair (+3% target, −1.5% stop, the close at timeout), which is the one column that nets the
target rate against the stop rate. `effective_bars` discounts label overlap within a pair and not
correlation between pairs, so it is an upper bound on independent outcomes.

## The whole table, rows that differ from the control

The control, alphabetical: target 0.2571, stop 0.5606, timeout 0.1822, mean return **+0.025%**,
effective 24,350. It takes 32 distinct pairs in eight years, 98.8% of bars from ten of them.

`hour_sin`, `hour_cos`, `weekday_sin`, `weekday_cos` are identical across pairs on a bar, so every
bar ties and they **are** the control. `bars_in_lookback_4/16/48/96` descending tie on almost every
bar (every liquid pair traded every bar) and are close to it.

| feature | direction | effective | target | stop | timeout | mean return | BUY-call target rate |
|---|---|---|---|---|---|---|---|
| (alphabetical control) | | 24,350 | 0.2571 | 0.5606 | 0.1822 | +0.025% | 0.2682 |
| bar_body_pct | ascending | 59,606 | 0.3748 | 0.5079 | 0.1173 | **+0.417%** | 0.4072 |
| log_return_4 | ascending | 53,316 | 0.3320 | 0.5296 | 0.1384 | +0.252% | 0.3486 |
| log_return_16 | ascending | 45,785 | 0.3179 | 0.5286 | 0.1536 | +0.212% | 0.3274 |
| high_low_position_16 | ascending | 23,778 | 0.2426 | 0.3912 | 0.3661 | +0.222% | 0.2271 |
| high_low_position_4 | ascending | 23,718 | 0.2549 | 0.4342 | 0.3109 | +0.200% | 0.2471 |
| bars_in_lookback_96 | ascending | 56,231 | 0.2474 | 0.4529 | 0.2997 | +0.176% | 0.2524 |
| log_return_48 | ascending | 38,771 | 0.2962 | 0.5309 | 0.1729 | +0.146% | 0.2989 |
| realised_vol_16 | descending | 69,166 | 0.3167 | 0.6380 | 0.0453 | +0.013% | 0.3609 |
| range_atr_4 | descending | 74,494 | 0.3054 | 0.6377 | 0.0570 | −0.015% | 0.3478 |
| bar_range_pct | descending | 74,967 | 0.3124 | 0.6216 | 0.0661 | +0.036% | 0.3741 |
| bar_body_pct | descending | 59,799 | 0.2277 | 0.6773 | 0.0950 | −0.302% | 0.2414 |
| log_return_4 | descending | 56,726 | 0.2446 | 0.6394 | 0.1160 | −0.197% | 0.2382 |
| realised_vol_16 | ascending | 6,818 | 0.0337 | 0.0828 | 0.8835 | +0.006% | 0.0204 |

Every feature and direction, all 79 rows, is in the JSON.

**Two different things raise the target rate, and only one of them moves the mean return.**

1. **Volatility** (`realised_vol_*`, `range_atr_*`, `bar_range_pct` descending): the target rate
   rises to about 0.31, but the stop rate rises to about 0.64 with it and timeouts fall to 5%. The
   most volatile pair touches *a* barrier sooner, in both directions; the mean return is
   −0.015% to +0.036%, no better than the control. A target rate read alone would call these the
   best rows in the table; netted, they choose nothing.
2. **Short-horizon reversal** (the pair that fell most: `bar_body_pct`, `log_return_4`,
   `log_return_16` ascending, and the pair closing nearest its range low, `high_low_position_*`
   ascending): the target rate rises and the stop rate **falls** against the control. The
   descending direction of the same features is the mirror image (−0.30%, −0.20%).

## By test year, the reversal rows and one volatility row

| feature, direction | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|---|
| control | −0.013% | −0.022% | +0.019% | +0.123% | −0.013% | +0.010% | +0.067% | +0.014% |
| bar_body_pct asc | +0.397% | +0.156% | +0.175% | +0.334% | +0.273% | +0.552% | +0.696% | +0.740% |
| log_return_4 asc | +0.320% | +0.113% | +0.141% | +0.244% | +0.241% | +0.274% | +0.330% | +0.367% |
| log_return_16 asc | +0.305% | +0.099% | +0.150% | +0.213% | +0.241% | +0.218% | +0.227% | +0.263% |
| high_low_position_16 asc | +0.363% | +0.133% | +0.127% | +0.202% | +0.197% | +0.204% | +0.248% | +0.327% |
| realised_vol_16 desc | +0.004% | −0.009% | +0.041% | +0.093% | +0.045% | −0.031% | −0.022% | −0.019% |

Mean realised return per taken bar, before friction. The reversal rows are positive in every
year; the volatility row is not distinguishable from the control in any year.

## Where the reversal return comes from: thin pairs, which this archive cannot price

Share of taken bars whose pair traded in fewer than 48 of its last 96 decision bars
(`bars_in_lookback_96 < 48`), against the control's:

| feature, direction | all years | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|
| control | 0.10 | 0.07 | 0.18 | 0.25 | 0.17 |
| bar_body_pct asc | **0.21** | 0.05 | **0.37** | **0.44** | **0.37** |
| log_return_4 asc | 0.08 | 0.03 | 0.16 | 0.17 | 0.14 |
| log_return_16 asc | **0.03** | 0.01 | 0.05 | 0.05 | 0.04 |
| high_low_position_16 asc | 0.01 | 0.00 | 0.02 | 0.03 | 0.02 |

`bar_body_pct` ascending has the largest return, and its return grows in exactly the years its
choice moved into intermittently traded pairs (0.37 to 0.44 of bars from 2022). A single-bar
close-to-close reversal in a pair that trades a few times an hour is the shape a **bid-ask bounce**
leaves: a close printed at the bid, followed by one printed at the ask. The historical archive is
OHLCVT with no book and no spread (`architecture-context.md`), so nothing here can separate a real
reversal from a bounce, and the live spread on such a pair is what the cost gate will charge.
`log_return_16` ascending earns less (+0.21%) but takes intermittent pairs on 3% of bars, fewer
than the control, and is positive in every year. That difference is measured; which one survives
a spread is not measurable offline.

## What this study does not show

* **No friction, and the mean return here is not comparable with it.** The study reports the mean
  realised barrier return **per bar** of the pair ranked first; friction is paid **per round trip**
  over a 2 to 12 hour hold spanning many bars. The two cannot be set against each other, and this
  file does not. Operator ruling 2026-09-15: `scout.rank_feature` stays absent (alphabetical), and
  whether any feature pays for a trade is an open question for Phase 7, when the chain runs end to
  end and returns are measured over the actual holding period. The thin-pair caveat above stays
  attached to `bar_body_pct`.
* **No fill.** The label enters at the decision bar's close. Engine 18 enters with a post-only limit,
  and a limit bid on the pair that has just fallen hardest is the order most exposed to adverse
  selection: it fills when the fall continues.
* **One candidate per bar, before every later gate.** The rates are for the pair ranked first,
  not for trades: engines 13, 8, 10, 11 and 15 still stand between that pair and an order.
* **Correlation between pairs.** `effective_bars` is an upper bound; the reversal rows are
  dominated by market-wide sell-offs, when many pairs fall together.
