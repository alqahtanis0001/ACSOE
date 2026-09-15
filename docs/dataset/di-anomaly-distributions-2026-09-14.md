# DI and anomaly score distributions, run `train-20260913T205245-067b2b9d`

**Evidence for the operator's ruling on `prediction.di_percentile` and `anomaly.threshold_percentile`.
It recommends nothing and sets nothing.** Covers 405 of 457 folds (the run died at fold 405).
Operator ruling 2 of 2026-09-14: fit each fold's DI and anomaly threshold from its own training
rows, do not retrain.

## How the numbers were produced

`di-anomaly-fit-2026-09-14.py`, on the `6e09881` code that trained the artefacts, per fold:

* **Training rows recovered, never trusted.** The fold's window read from the dataset, the
  splitter's rule applied (label window before the test window, decision bar before the 48-bar
  embargo), and the result required to equal the manifest's train row count, purged count,
  embargoed count, `training_identity` and `scaler_identity`. All 405 folds matched. Controls on
  folds 200 and 404: the neighbouring fold's manifest REFUSED, the rows without the embargo
  REFUSED. The rows without the purge were ACCEPTED, an equivalent mutant at this config: with a
  48-bar embargo equal to the 48-bar label horizon every purged row is also inside the embargo, so
  only the per-fold purged and embargoed counts can see the purge, and they are checked.
* **DI.** The reference set exactly as the trainer's `_fit_and_score_di` builds it (per-pair last
  30 days, the fold's scaler, complete rows, capped at 200,000 with the fold's seed); the
  leave-one-out mean distance to the 10 nearest reference rows, and the same mean for every
  complete test row. Searched with scikit-learn's brute-force nearest neighbours, because the
  module's own path costs days to weeks here (136 ms per scored row; ~20 min of leave-one-out
  per capped fold). Held to `modelling.di`: 16 leave-one-out values and 16 test scores per fold
  recomputed through `di._mean_nearest` and `di.score`, largest difference over all 405 folds
  **1.1e-13**; and the trainer's `_fit_and_score_di` run in full on folds 0, 1 and 60 gave an
  identical reference identity and matrix and every distribution value within 1.9e-14.
* **Anomaly.** Each fold's saved isolation forest, hash-verified and **not refitted**, scored over
  its complete training rows (count and identity equal to the manifest's on all 405 folds) and its
  test rows.
* **Thresholds as the artefact would compute them.** For percentile p: `np.quantile` of the fold's
  leave-one-out distribution (as `di.fit`) or of its training scores (as `_fit_anomaly`); a test
  row is refused when **strictly above** it (as `di.score` and engine 13).

Aggregation: `di-anomaly-distributions-2026-09-14.py` → `.json` beside this file (every fold's
thresholds at every percentile are in its `folds` list). All rates are before friction; `mean
return` is the realised barrier return; effective sizes discount label overlap within a pair only.

## First, what no percentile touches: half of every test week is an incomplete vector

15,978,803 test rows. **8,025,361 (50.2%) have an incomplete DI vector** and 7,989,605 (50.0%) an
incomplete anomaly vector; engines 8 and 13 refuse these whatever the percentile. The unfilled
columns are the 48- and 96-bar lookback features (on the fold 371 test week, 54% and 56% of rows),
from pairs that do not trade every bar; the 78 macro columns are always complete.

| test year | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|---|
| incomplete DI vector | 26% | 33% | 46% | 51% | 28% | 52% | 61% | 54% |
| of BUY calls | 28% | 36% | 45% | 52% | 28% | 54% | 62% | 54% |

Every rate below is over the complete rows only.

## Anomaly: behaves as a percentile should, and what it refuses is volatile rather than bad

Scored rows 7,989,198. Out-of-sample block rate against the nominal 1 − p:

| p | blocked | nominal | per-fold min / median / max | blocked: target, stop, mean return | kept: target, stop, mean return | pairs mostly blocked |
|---|---|---|---|---|---|---|
| 0.80 | 21.0% | 20% | 8.1% / 18.1% / 65.5% | 0.277, 0.551, +0.045% | 0.220, 0.495, +0.007% | 99 / 231 |
| 0.90 | 10.8% | 10% | 3.1% / 8.3% / 52.2% | 0.295, 0.581, +0.044% | 0.224, 0.498, +0.011% | 62 / 231 |
| 0.95 | 5.55% | 5% | 1.0% / 3.9% / 39.1% | 0.308, 0.610, +0.034% | 0.227, 0.501, +0.014% | 33 / 231 |
| 0.975 | 2.88% | 2.5% | 0.2% / 1.8% / 32.1% | 0.317, 0.636, +0.013% | 0.229, 0.503, +0.015% | 8 / 231 |
| 0.99 | 1.24% | 1% | 0.0% / 0.6% / 25.2% | 0.318, 0.666, −0.039% | 0.231, 0.505, +0.016% | 2 / 231 |
| 0.995 | 0.66% | 0.5% | 0.0% / 0.3% / 18.8% | 0.311, 0.683, −0.090% | 0.231, 0.505, +0.016% | 1 / 231 |
| 0.999 | 0.15% | 0.1% | 0.0% / 0.0% / 6.0% | 0.279, 0.720, −0.244% | 0.232, 0.506, +0.015% | 0 / 231 |

"Pairs mostly blocked": pairs with more than half of their scored test rows blocked.

* **Calibrated in aggregate and stable by year.** At 0.95 the yearly block rate is 5.0% to 6.8%;
  at 0.99, 0.9% to 1.8%. The per-fold maximum is the gate firing on market-wide weeks.
* **What it blocks is the volatile tail.** Blocked rows touch a barrier more often in both
  directions (target 0.31, stop 0.61 to 0.72) and timeout almost never. Mean return of blocked rows
  turns negative only from 0.99 upward (−0.04% at 0.99, −0.24% at 0.999).
* **Among BUY calls it blocks the better ones before friction**: at 0.95, blocked BUY calls
  +0.161% against kept +0.034%; at 0.99, +0.204% against +0.039% (17,918 effective blocked).
* **The spec 70 finding stands unresolved**: a ten-sigma volume spike scored at the 0.904 quantile
  of training scores. No percentile above ~0.90 blocks that shape; this study cannot add to it.

## DI: as ruled, it refuses most live candidates at every percentile, for a reason unrelated to the market

Scored rows 7,953,442.

| p | refused | nominal | per-fold min / median / max | refused: target, stop, mean return | kept: target, stop, mean return | BUY calls refused | pairs mostly refused |
|---|---|---|---|---|---|---|---|
| 0.80 | 99.4% | 20% | 47% / 99.7% / 100% | 0.232, 0.508, +0.015% | 0.182, 0.442, +0.027% | 99.4% | 231 / 231 |
| 0.90 | 97.9% | 10% | 29% / 98.2% / 100% | 0.233, 0.509, +0.015% | 0.193, 0.460, +0.018% | 98.0% | 231 / 231 |
| 0.95 | 94.7% | 5% | 17% / 93.8% / 100% | 0.234, 0.510, +0.015% | 0.203, 0.473, +0.021% | 94.8% | 231 / 231 |
| 0.975 | 88.5% | 2.5% | 10% / 85.0% / 99.9% | 0.235, 0.511, +0.015% | 0.209, 0.483, +0.016% | 88.9% | 231 / 231 |
| 0.99 | 74.9% | 1% | 2.7% / 66.4% / 99.7% | 0.238, 0.513, +0.018% | 0.214, 0.493, +0.006% | 75.7% | 228 / 231 |
| 0.995 | 61.2% | 0.5% | 1.2% / 48.5% / 99.1% | 0.242, 0.515, +0.023% | 0.217, 0.496, +0.003% | 62.4% | 224 / 231 |
| 0.999 | 31.1% | 0.1% | 0.1% / 19.9% / 88.4% | 0.253, 0.520, +0.040% | 0.223, 0.502, +0.004% | 32.3% | 52 / 231 |

By test year at 0.95: 70% (2017), 82%, 71%, 84%, 98% (2021), 97%, 97%, 98% (2024). At 0.99: 37%,
44%, 36%, 53%, 82%, 76%, 78%, 83%. The refusal grows with the number of pairs.

**What is refused is not worse.** At every percentile the refused rows have a slightly *higher*
target rate and mean return than the kept ones. The DI is not separating unfamiliar markets from
familiar ones.

**Why, tested and not assumed** (`di-serial-correlation-check-2026-09-15.py` / `.json`). The
leave-one-out statistic was recomputed through the module's own arithmetic on 2,000 sampled
reference rows of six folds spread over the run, excluding progressively more of the reference set.
Its leave-one-out arm reproduces the saved distribution to within 4.2e-14 on every fold.

| fold (test week) | reference rows | test DI median | LOO median | LOO, same pair ±48 bars excluded | LOO, **any pair ±48 bars** excluded | refused at 0.95: LOO | same pair ±48 bars | any pair ±48 bars | any pair ±7 days |
|---|---|---|---|---|---|---|---|---|---|
| 20 (2017-08) | 22,630 | 1.573 | 1.128 | 1.149 | 1.562 | 78.5% | 71.9% | 12.5% | 11.5% |
| 100 (2019-03) | 18,367 | 1.425 | 1.049 | 1.074 | 1.466 | 51.5% | 43.5% | 2.5% | 1.6% |
| 180 (2020-09) | 58,699 | 1.374 | 0.814 | 0.818 | 1.447 | 90.9% | 90.1% | 0.0% | 0.0% |
| 260 (2022-03) | 144,278 | 1.400 | 0.657 | 0.658 | 1.475 | 96.5% | 95.6% | 8.2% | 8.1% |
| 340 (2023-10) | 91,084 | 1.347 | 0.791 | 0.793 | 1.380 | 90.0% | 88.8% | 2.1% | 1.4% |
| 404 (2024-12) | 200,000 | 1.401 | 0.569 | 0.569 | 1.448 | 99.9% | 99.9% | 1.9% | 1.1% |

(Fold 371, run first: LOO median 0.632, any pair ±48 bars 1.423, test 1.402.)

Excluding the row's **own pair** nearby changes almost nothing. Excluding **every pair's** rows
within 48 bars puts the reference distribution on top of the test distribution on every fold. So
a reference row's ten nearest neighbours are other pairs on the same or adjacent bars: 78 of the
117 DI columns are the BTC and ETH macro features, identical for every pair on a bar, and the
calendar columns are too. Leave-one-out removes only the row itself, so the reference distribution
measures "how far is a row from rows of the same moment". A live candidate is at least the 48-bar
embargo after the reference window and has no rows of its own moment in it, so its DI lands in the
top of that distribution whatever the market is doing. It gets worse as the universe grows, because
more pairs means more same-moment neighbours.

**This is a property of the statistic as ruled (operator ruling 6 of 2026-09-12), not of the
percentile, and not a defect in the fit.** No percentile of this distribution below about 0.999
leaves engine 8 predicting on most candidates, and at 0.999 it still refuses a third of them while
refusing no worse rows. What would change it (an exclusion window in the leave-one-out, a DI
input without the shared macro and calendar columns, or a different reference construction) is a
change to ruling 6, and is the operator's.

## The two gates together

Rows with both vectors complete, 7,953,442 (every row with a complete DI vector also has a
complete anomaly vector). Almost every anomaly block is also a DI refusal:

| anomaly p | DI p | anomaly blocks | DI refuses | both | passing both | passing: target, mean return | passing BUY calls (effective) |
|---|---|---|---|---|---|---|---|
| 0.95 | 0.95 | 5.55% | 94.7% | 5.52% | 5.3% | 0.203, +0.021% | 225,926 (12,493) |
| 0.95 | 0.99 | 5.55% | 74.9% | 5.19% | 24.7% | 0.212, +0.006% | 1,053,953 (62,169) |
| 0.99 | 0.99 | 1.24% | 74.9% | 1.20% | 25.0% | 0.214, +0.006% | 1,065,908 (65,084) |
| 0.99 | 0.995 | 1.24% | 61.2% | 1.15% | 38.7% | 0.216, +0.003% | 1,651,313 (104,376) |
| 0.995 | 0.995 | 0.66% | 61.2% | 0.62% | 38.8% | 0.217, +0.003% | 1,653,102 (105,030) |

The rest of the 3-by-3 grid is in the JSON. Before either percentile applies, half of all test
rows are already refused as incomplete.

## What this does not establish

* Nothing is before or after any cost; break-even is the reader's.
* The anomaly per-year stability and the DI's growth with the universe are measured over
  2017-2024 only; 2025 is the 52 missing folds.
* The DI diagnostic samples 2,000 reference rows on seven folds, not all 405; its direction is the
  same on every one.
* No DI or anomaly artefact was written. Supplying either percentile still leaves every fold of
  this run without a `di.npz` or a recorded anomaly threshold, so engines 8 and 13 refuse it; an
  artefact carrying a ruled threshold is a new, write-once run directory, not an edit to these.
