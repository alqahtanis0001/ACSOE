# Phase 7 findings: the system's economic behaviour, measured before the chain simulation

**What this document is.** It gathers every measurement of the system's economic behaviour made
before the Phase 7 chain simulation ran. Its sources are the walk-forward's out-of-sample file, the
Phase 5 DI and anomaly study, the Phase 5 skeptic studies, the ranking study, and the reconnaissance
measurements of 2026-09-18 and 2026-09-19. **Nothing here comes from the chain.** No engine was run
over history to produce any figure below. Each figure is arithmetic over saved outputs, and each
table says which chain behaviour it does and does not model.

**How to read the markers.**

- **SIMULATED VALUE PENDING** marks a slot the chain simulation will fill, or a figure it will
  replace. A sentence built around such a slot can be written now and the value substituted later.
- **FINAL** marks a finding the simulation will not touch: it is a property of the model outputs,
  the arithmetic of the cost gate, or a comparison the simulation does not repeat.
- **NOT MEASURED** marks a figure that would need a fresh computation. It was deliberately not
  computed for this document, and the slot is left empty rather than filled.

Written 2026-09-19, at `f0e7514` plus this document. **Revised the same day** (§R) after four
operator rulings made after the first version was written; every section below that the rulings
touch now says so. Scripts and their raw outputs are in
`docs/dataset/phase-7-recon-2026-09-19/` (`scripts/` and `outputs/`). Where an output was only
printed to a terminal, it is transcribed verbatim in `outputs/transcribed-terminal-outputs.txt`,
cited below as **[T]**.

---

## R. What the project ruled on 2026-09-19, after this document was first written

**R.1 The tiers simulated are 3 and 5.** Operator ruling, overturning the lead's earlier
recommendation of 3 and 4. The reason is the framing:

- **Tier 3 is reachable by a small retail account.** It needs $10,000 of 30-day spot volume or
  $20,000 of assets on platform.
- **Tier 5 needs $50,000 of 30-day volume or $100,000 held**, a scale most retail accounts never
  reach.

The two runs state the cost-adaptive selectivity claim at both ends. Round-trip fees under the
fetched schedule (§2) are 0.60% at tier 3 and 0.45% at tier 5.

The contrast was first argued from `log_return_4` figures: 3 trades at 0.60% and about 35 at 0.45%.
**Those belong to the ranking the next ruling replaced.** Under the ruled ranking, the measured grid
has 46 trades at fees of 0.60%, 119 at 0.50% and 254 at 0.40% over 12 months (§4). Fees of 0.45%
were not computed, so tier 5's count lies between the 0.40% and 0.50% rows and is **NOT MEASURED**.

**R.2 Engine 7 ranks its universe by engine 8's expected move, batched.** Invariant 4 is amended to
permit it, narrowly, in the operator's words: *a model's output may order candidates for
examination, provided every gate judges the chosen candidate independently and no gate's verdict
is influenced by the ranking. The prohibition on a model overriding or softening a gate is
untouched.*

- **Why expected move and not `log_return_4`.** `log_return_4` was chosen from a study computed
  over the same out-of-sample data this report uses, and the lead had warned of exactly that.
  Expected move is not a selected feature. It is the predictor's own output, and the number engine
  10 already compares against the hurdle. In the operator's words, *the circularity is gone*.
- **What remains, stated so that an examiner does not have to find it.** The decision to amend
  was taken after the expected-move grid in §4 had been computed on the same out-of-sample data.
  The ranking variable was not selected by a study. The decision to adopt it was still made with
  that grid in view. Three things bound what that choice could have bought:
  - the stated criterion was sample size, not return;
  - the net stayed at about zero in every cell (§4);
  - the promotion bar (R.4) was fixed before anything runs.
- **What the amendment changed.** At tier 3 (fees 0.60%, 12 months, the bucket spread, the capped
  skeptic at 0.50) it raises the trade count **from 3 under `log_return_4` to 46**. The net per
  trade is roughly zero under every row of the grid (−0.30% to +0.04%, every interval including
  zero). **It was made to obtain a measurable sample, not a favourable result.** The operator
  records: *had the net moved from negative to positive, I would have treated that as a warning
  and not amended.*
- **Net-margin ranking is rejected on live feasibility, not cost.** Ranking by expected move minus
  each pair's own friction needs every pair's slippage every bar: 127 order-book calls per bar,
  unchecked against the rate limiter. Simulating it would measure a system that could not run live.

**R.3 The fee schedule is sourced.** Kraken's published schedule was fetched on 2026-09-19 and is
committed with its URL and fetch time (`tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`,
extracted verbatim from the committed raw page). It agrees with the figures the operator had from a
web search: tier 3 0.22%/0.38%, tier 4 0.20%/0.35%, tier 5 0.15%/0.30%. **Kraken restructured its
fee tiers on 9 July 2026.** Its support article, committed beside the schedule, says tiers are now
set by the best of spot volume, futures volume and assets on platform. **Nothing on disk dates any
earlier schedule, so the 2026 schedule is applied to a 2023–24 window.**

**R.4 The promotion bar is set before anything runs.** In the operator's words: *a model is
promoted only if the lower bound of the 95% interval on net return per trade is above zero, after
friction, on the deflated metric.* The operator expects nothing to pass it, and setting it in
advance is the point. **Its operational form is fixed in spec 139 before any run.** In particular,
how the interval is widened for the number of trials, and which covariance allows for overlapping
holds, are fixed there and not chosen after a result exists.

---

## 0. Data, windows and conventions

**The model run.** `train-20260913T205245-067b2b9d`: a purged, embargoed walk-forward with weekly
retraining over Kraken's own time-and-sales archive, reduced to 15-minute bars. It trained 405 of
457 planned folds before running out of memory at fold 405, so the out-of-sample file covers test
weeks from 2017-04 to 2025-01-03 and **no 2025 test week**.

| Quantity | Value | Source |
|---|---|---|
| Out-of-sample rows (pair-bars) | 15,978,803 | `outputs/2026-09-18_q_em.log` |
| Decision bars, full span | 271,667 over 405 folds; mean 58.8 pairs per bar, max 232 | `outputs/2026-09-18_q_bars.log` |
| Fold 404's test window | 2024-12-28 00:00 to 2025-01-04 00:00 UTC | `outputs/q_window.out` |
| **The 1.5-year window** | folds 326 to 404: 2023-07-01 to 2025-01-04, 553 days | `outputs/q_window.out` |
| Decision bars in the window | 53,022 (53,088 calendar bars); 6,712,659 pair-bars | `outputs/q_window.out` |
| Pairs per bar in the window | mean 126.6, median 124, max 232, min 6; 234 distinct pairs | `outputs/q_window.out` |

**The cost gate** (invariant 5): a candidate clears when its expected move exceeds
`(1 + hurdle_multiple) × friction`, which is 2.5 × friction at `hurdle_multiple: 1.5`. **Friction**
is round-trip fees plus spread plus slippage. **Tier 3's fees**, maker 0.22% and taker 0.38%
(0.60% round trip), are invariant 5's reference figures. Kraken's published schedule, fetched
2026-09-19, agrees (§R.3). The reconnaissance used the reference figures; the fetched schedule
confirmed them rather than changing them.

**The ranking.** Every table in §1 and §2, and the §3 inversion, was computed under alphabetical or
`log_return_4` ranking, before §R.2 ruled expected-move ranking. Each says which. They stand as
measurements of the arms they name. The ruled system's own figures are the expected-move rows of §4
and the simulation's pending slots.

**The alphabetical candidate.** With `scout.rank_feature` absent, engine 7 orders its universe by
pair name. Offline, the candidate on each bar is the first pair by name among that bar's
out-of-sample rows. That approximates engine 7's universe filter by "has a row", because the
archive supplies none of the filter's inputs (§7).

**One position per pair.** Engine 11 refuses a candidate whose pair already has an open position.
Offline, a trade is held until its label resolved (`label_window_end_ts`). Where stated, a limit of
three concurrent positions is also applied.

**Realised return.** `return_pct`, the triple-barrier outcome from the bar's close: +3.0% at the
target, −1.5% at the stop, or the close at the 48-bar timeout. **Net** is realised minus friction.

---

## 1. The funnel

### 1a. The 1.5-year window, one arm in full

The arm: alphabetical candidate, tier-3 reference fees, **zero spread**, the uncapped skeptic as
trained. The gates are applied in the order the reconnaissance script applied them (the cost bar
first), not in the chain's order. §1b gives the chain's order.
Source: `outputs/q_window.out`.

| Stage | Survivors | Which stage refuses, and on what |
|---|---|---|
| Decision bars | 53,022 | Engine 7: one candidate per bar, the alphabetically first pair |
| Clear the cost bar (1.50%) | **74** | Engine 10: expected move ≤ 2.5 × 0.60% |
| Complete feature vector | 48 | Engines 13 and 8: a 48- or 96-bar lookback not filled |
| Anomaly at the 0.99 percentile | 47 | Engine 13: market state beyond its fold's threshold |
| DI at the 0.99 percentile | 31 | Engine 8: dissimilar to the training reference |
| Skeptic, uncapped, veto at 0.50 | 2 | Engine 15: P(wrong) > 0.50 |
| One position per pair | **1** | Engine 11: the pair already holds a position |

The same arm at 10 bps of spread: 29 clear, then 18, 18, 5, 2 and 1. At 25 bps: 10, 5, 5, 1, 0 and
0. The skeptic does the largest share of the refusing at the end of the funnel; the cost bar does
it at the start.

**SIMULATED VALUE PENDING:** the chain's own stage counts over the same window, which add engine
9's book, the entry-fill rule, `ordermin`/`costmin`, and engine 17's freezes.

### 1b. The same window in the chain's order, capped against uncapped skeptic

Engine 13 runs before engine 8 and both run before engine 10, so in the chain the anomaly and DI
refusals come first. Here the anomaly stage includes the incomplete-vector refusal, because the
saved study outputs record one outcome per row. Friction is total friction; the trade count is
after the skeptic at 0.50 and one position per pair with at most three open.
Source: `outputs/q_funnel.out`.

| Alphabetical, 18 months | Bars | Anomaly passes | DI passes | Cost passes | Risk passes | Uncapped skeptic | Capped skeptic |
|---|---|---|---|---|---|---|---|
| friction 0.40% | 53,022 | 20,223 | 19,807 | 129 | 64 | 1 | 35 |
| friction 0.50% | 53,022 | 20,223 | 19,807 | 52 | 24 | 1 | 18 |
| friction 0.60% | 53,022 | 20,223 | 19,807 | 31 | 17 | 1 | 15 |
| friction 0.70% | 53,022 | 20,223 | 19,807 | 5 | 4 | 1 | 4 |
| friction 0.85% | 53,022 | 20,223 | 19,807 | 1 | 1 | 0 | 1 |

In chain order, **62% of bars are refused before any prediction** (53,022 → 20,223). That is
mostly the incomplete-vector refusal of Phase 5's Finding 3. The cost gate then refuses 99.3% to
99.99% of what remains, depending on friction.

### 1c. The full 405-fold span

Only the cost stage was measured over the full span. Source: [T] `2026-09-18_q_net.py`,
`outputs/2026-09-18_q_bars.log`.

| Stage | Full span (271,667 bars) |
|---|---|
| Alphabetical candidate clears 1.50% (tier 3, zero spread) | 938 |
| … at 5, 10 and 25 bps of spread | 681, 541, 253 |
| Any pair on the bar clears 1.50% | 8,303 bars |
| Complete vector, anomaly, DI, skeptic, one position per pair | **NOT MEASURED** |

---

## 2. The friction grid

The trade bound depends only on total friction. Column (a) counts bars whose alphabetical candidate
clears the cost bar. Column (b) adds one position per pair. No other gate is applied. The window is
the 1.5 years. Sources: (a) `outputs/q_window.out`; (b) [T] `q_hold.py`.

| Total friction | (a) bars clearing | (b) one position per pair | Net per trade for (b), 95% interval | Fee-only mark |
|---|---|---|---|---|
| 0.20% | 1,961 | NOT MEASURED | — | |
| 0.25% | 1,108 | NOT MEASURED | — | |
| 0.30% | 659 | 267 | +0.05% ± 0.26% | |
| 0.35% | 428 | 187 | −0.02% ± 0.31% | |
| 0.40% | 298 | 127 | +0.04% ± 0.38% | |
| 0.45% | 197 | 87 | +0.34% ± 0.46% | **tier 5, simulated** (0.15% + 0.30%) |
| 0.50% | 128 | 55 | +0.26% ± 0.59% | |
| 0.55% | 98 | 43 | +0.23% ± 0.67% | tier 4 (0.20% + 0.35%) |
| 0.60% | 74 | 34 | +0.18% ± 0.75% | **tier 3, simulated** (0.22% + 0.38%) |
| 0.65% | 44 | NOT MEASURED | — | |
| 0.70% | 29 | 12 | −0.05% ± 1.29% | |
| 0.85% | 10 | 6 | −0.10% (interval not meaningful) | |
| 0.90% | 2 | NOT MEASURED | — | |
| 0.95% | 1 | NOT MEASURED | — | |
| 1.00% and above | 0 | 0 | — | |
| 1.20% | 0 | 0 | — | tier 1 (0.40% + 0.80%) |

This grid is the **alphabetical** arm at **zero spread**. The ruled system's counts are in §4.

**The grid is indexed by total friction, and the tier labels are mapped onto it.** Each label
marks that tier's round-trip fee from the fetched schedule (§R.3). Its real friction sits to the
right of the mark by the spread and slippage the pair pays. Had the schedule differed, only the
labels would have moved; the measurements are indexed by friction and stand either way.

| Tier | Maker | Taker | Round-trip fee | Qualifies by (any one of) |
|---|---|---|---|---|
| 1 | 0.40% | 0.80% | 1.20% | $0+ of 30-day spot volume |
| 3 | 0.22% | 0.38% | 0.60% | $10K+ spot volume, or $20k assets on platform, or ≥ $10M futures volume |
| 4 | 0.20% | 0.35% | 0.55% | $25K+, or $50k, or ≥ $15M |
| 5 | 0.15% | 0.30% | 0.45% | $50K+, or $100k, or ≥ $25M |

Source: `tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`, fetched 2026-09-19T02:59:51Z
from `https://www.kraken.com/features/fee-schedule`, "Spot Crypto" table.

**SIMULATED VALUE PENDING:** the chain's trade count and net per trade at each simulated tier.

### Tier 1 is provably zero. FINAL.

**The primary proof is structural, not observed.** At tier 1's fees (0.40% + 0.80% = 1.20%, the
fetched schedule and invariant 5 agreeing), the cost bar is 2.5 × 1.20% = **3.0%** before any
spread or slippage, and spread and slippage only raise it. The expected move is

`p_target × 3.0% − p_stop × 1.5% + p_timeout × m`,

where `m` is the fold's mean timeout return. The calibrated probabilities are renormalised to sum
to one (`modelling/calibration.py`, `apply_calibration`), and `m` lies between 0.17% and 0.54% in
all 405 fold manifests. So the expected move is a weighted average of 3.0%, −1.5% and `m`, and can
never exceed 3.0%. The gate needs it to be **strictly greater** than 3.0%, so no candidate at tier 1
can clear, whatever the market does and whatever the model learns. This holds for any model the
calibration and the barriers allow, not only the 405 trained.

**Corroboration, observed.** Over all 15,978,803 out-of-sample rows, the highest expected move the
model produced is **2.9999999930%** (`outputs/2026-09-18_q_em.log`): at the bound, and never past
it.

---

## 3. The spread inversion. FINAL, as the offline comparison it is.

**The finding.** A single constant spread applied to every pair produced a positive and, in three
cells, nominally significant return per trade. A spread that depends on each pair's liquidity,
applied to the same candidates, produced returns consistent with zero and slightly negative. **The
simpler assumption inverted the sign of the point estimate** in seven of the eight matched cells
that traded.

**The arms.** Both arms rank by `log_return_4` ascending, use the capped skeptic at 0.50, and
apply one position per pair with at most three open. They differ in one respect:

- **Flat:** tier fees plus a constant 10 bps of spread for every pair, no slippage (`q_funnel.py`).
- **Bucket:** tier fees plus a spread and a slippage looked up from the pair's trailing 24-hour
  dollar volume, using the declared table below (`q_bucket.py`).

The bucket arm therefore also adds slippage. Slippage is a liquidity cost of the same kind, and the
table shows it scales with the same volume buckets.

| Fees | Window | Flat 10 bps: trades, net per trade | Bucket table: trades, pairs, net per trade |
|---|---|---|---|
| 0.60% | 6 months | 18, +0.55% ± 1.04% | 0 |
| 0.60% | 12 months | 24, +0.43% ± 0.91% | 3, 3 pairs, −0.67% (interval not meaningful) |
| 0.60% | 18 months | 28, +0.53% ± 0.83% | 3, 3 pairs, −0.67% (interval not meaningful) |
| 0.50% | 6 months | 48, +0.43% ± 0.64% | 12, 10 pairs, +0.06% ± 1.34% |
| 0.50% | 12 months | 65, +0.39% ± 0.55% | 23, 17 pairs, −0.19% ± 0.93% |
| 0.50% | 18 months | 79, +0.29% ± 0.50% | 26, 20 pairs, −0.25% ± 0.87% |
| 0.40% | 6 months | 102, **+0.51% ± 0.44%** | 36, 22 pairs, −0.32% ± 0.72% |
| 0.40% | 12 months | 147, **+0.49% ± 0.36%** | 58, 35 pairs, −0.03% ± 0.58% |
| 0.40% | 18 months | 197, **+0.36% ± 0.31%** | 71, 42 pairs, −0.15% ± 0.52% |

Sources: flat, `outputs/q_funnel.out` (rows `log_return_4 asc`, `cap@0.50`, at total friction =
fees + 0.10%); bucket, [T] `q_bucket.py`. **Bold** marks the flat cells whose interval excludes
zero. No bucket cell's interval excludes zero.

**Where the positive result came from.** Take the flat arm at 0.60% total friction over 12 months:
65 trades. **Only 11 of them are on a pair the recorder measured.** Those 11 pairs' recorded median
spreads are 24.7 bps at the median and up to 127.4 bps, against the 10 bps the flat arm charged
them. Those 11 trades netted −0.05%; the 54 on unrecorded pairs netted +0.48% ([T] `q_picks.py`).
The most-traded pairs were BSXUSD (13 trades), HDXUSD (10), STORJUSD (4) and CQTUSD (4), all thin.
The ranking favours the pair that fell furthest over the last four bars. On a thin pair that is
often a print at the bid, which later prints at the ask repay. That gain is the spread itself, and
the flat constant did not charge it. **The positive result came from pricing thin pairs as if
they were liquid.**

**The declared table** (bps; the median of per-pair medians in each bucket, with the interquartile
range across pairs). Source: [T] `q_bucket.py`; per-pair values from `q_depth.py`.

| Pair's trailing 24-hour volume | Recorded pairs | Spread | Spread IQR | Slippage at $5,000 |
|---|---|---|---|---|
| under $10k | 16 | 30.4 | 12.2–36.0 | ~17.7 |
| $10k–$100k | 49 | 25.8 | 11.2–39.2 | ~20.8 |
| $100k–$1M | 84 | 12.3 | 7.2–19.4 | ~7.5 |
| $1M–$10M | 36 | 5.5 | 2.7–9.4 | ~1.7 |
| over $10M | 0 | *mapped to the $1M–$10M row* | | |

- Slippage is modelled as a book whose notional is spread evenly out to the recorded $10,000
  depth. On that assumption it is a quarter of the upper bound (depth to $10,000 minus half the
  spread), because engine 9 walks the whole quote balance ($5,000) rather than the position.
- No recorded pair exceeds $10M a day because BTC, ETH and SOL are recorded as full books rather
  than as summaries, so that bucket borrows the next one's values.
- The IQRs are wide, and they are the declared uncertainty of every value in the table.

**Coverage.** The recording holds 187 USD pairs for **7.4 days**, 2026-09-11 16:13 to 2026-09-19
00:45 UTC ([T] `q_spread_agg.py`). Of the archive's 231 USD pairs, **72 were recorded**; the rest,
including the alphabetical candidate 1INCHUSD, take their bucket's value ([T] `q_spread_extrap.py`).
Candidates by bucket over the 1.5 years, from the 0th (thinnest) to the 4th:

| Ranking | under $10k | $10k–$100k | $100k–$1M | $1M–$10M | over $10M |
|---|---|---|---|---|---|
| Alphabetical | 3,851 | 20,265 | 22,444 | 6,423 | 39 |
| `log_return_4` ascending | 3,557 | 18,431 | 23,924 | 6,501 | 609 |

**Why a fitted spread model was not used instead.** A regression of log spread on the five
predictors the archive can reproduce explained 84% of spread variance as differences between pairs.
It predicted a held-out pair's spread only to within a factor of 3.3 to 6.4 at 95%, or 3.1 to 4.2
for its average level. It backcast 1INCHUSD at 25 bps with a band of 7.7 to 84 bps, wide enough
that the cost gate's verdict would come from the model's error rather than the market ([T]
`q_spread_fit.py`, `q_spread_extrap.py`). The bucket table is a declared lookup, not a fitted model.
It gets the direction right (thin pairs cost more) without claiming per-pair precision the data
cannot support.

**Under the ruled ranking.** Both arms above rank by `log_return_4`, computed before §R.2. The same
flat-against-bucket comparison under expected-move ranking is **NOT MEASURED**. The finding stands
as a statement about the arms it names. That a constant spread flatters thin-pair trades does not
depend on which ranking produced the candidates.

**Why this is FINAL.** The inversion is a comparison between two spread assumptions over identical
candidates and outcomes. The simulation runs one arm, the bucket table, and does not repeat the
comparison. **SIMULATED VALUE PENDING:** the bucket arm's chain figures, which add entry fills.

---

## 4. The ranking comparison

**How much alphabetical ordering constrains the system.** Over the 1.5 years the alphabetical
candidate was **1INCHUSD on 29,857 of 53,022 bars (56.3%)** and AAVEUSD on 20,082 (37.9%). 17
pairs were ever the candidate, and six of them account for 53,009 of the 53,022 bars
(`outputs/q_window.out`, `outputs/q_funnel.out`). With a mean of 126.6 pairs present per bar,
**about 126 pairs per bar were passed over on their name alone.** FINAL: this is a property of the
ordering, not of the market.

**Trades by ranking**, all under the declared bucket spread and slippage, capped skeptic at 0.50,
one position per pair with at most three open. Sources: alphabetical and `log_return_4`, [T]
`q_bucket.py`; expected move and net margin, [T] `q_emrank.py`.

| Fees | Window | Alphabetical | `log_return_4` ascending | Expected move | Net margin |
|---|---|---|---|---|---|
| 0.60% | 6 months | 0 | 0 | 22 (18 pairs), −0.21% ± 0.95% | 28 (22 pairs), −0.30% ± 0.84% |
| 0.60% | 12 months | 1 (1 pair), −2.17% (n = 1) | 3 (3 pairs), −0.67% (interval not meaningful) | 46 (35 pairs), −0.20% ± 0.65% | 55 (40 pairs), −0.10% ± 0.60% |
| 0.50% | 6 months | 1 (1 pair), −2.07% (n = 1) | 12 (10 pairs), +0.06% ± 1.34% | 71 (47 pairs), −0.26% ± 0.52% | 83 (51 pairs), −0.14% ± 0.48% |
| 0.50% | 12 months | 3 (2 pairs), −2.11% (interval not meaningful) | 23 (17 pairs), −0.19% ± 0.93% | 119 (75 pairs), −0.11% ± 0.40% | 145 (76 pairs), +0.04% ± 0.37% |
| 0.40% | 6 months | 3 (2 pairs), −2.01% (interval not meaningful) | 36 (22 pairs), −0.32% ± 0.72% | 150 (70 pairs), −0.17% ± 0.35% | 173 (74 pairs), −0.24% ± 0.33% |
| 0.40% | 12 months | 12 (2 pairs), −0.94% ± 1.14% | 58 (35 pairs), −0.03% ± 0.58% | 254 (110 pairs), −0.08% ± 0.27% | 283 (111 pairs), −0.06% ± 0.26% |

- **Expected move:** the pair with the highest expected move among those the anomaly and DI gates
  pass.
- **Net margin:** the highest expected move minus 2.5 × its own friction, which is exactly what
  engine 10 tests.

**Expected move is the ruled ranking** (§R.2, with invariant 4 amended). The trade counts it gives
at each friction are this document's best offline statement of what the simulated system will do,
before entry fills are modelled. In the table above, anomaly and DI are applied to every pair before
the choice. The engine arrangement that achieves this without any gate's verdict depending on the
ranking is fixed in spec 144. **Net margin is rejected**, on live feasibility (§R.2), and its
column is kept only as a measured comparison.

**The finding: the ranking changes how many trades are taken, not what each trade earns.** Across
the three rankings other than alphabetical, wherever there are enough trades for an interval, every net per
trade lies between −0.32% and +0.06%, and every interval includes zero. Alphabetical ordering
yields too few trades to say anything about its return. Its point estimates are worse, but they
rest on one to twelve trades on two pairs.

**SIMULATED VALUE PENDING:** the expected-move ranking's chain trade count, pair count and net per
trade, at tiers 3 and 5.

---

## 5. The skeptic

### 5a. Capped against uncapped, over the 1.5-year window. FINAL.

The operator ruled on 2026-09-16 that the skeptic trains on a rolling window of the last 13 folds'
BUY calls. The walk-forward trained it on every earlier fold's calls, uncapped. For the 79 folds of
the window, capped skeptics were trained in memory with the trainer's own row selection and model
settings. The replication was first shown to reproduce the trainer exactly: on folds 20 and 40,
retrained uncapped, the training rows and identity matched the manifests and the probabilities
differed by 0 ([T] `q_capped.py validate`). Scored on the window's 3,751,522 out-of-sample BUY calls
(base target rate 0.2438; [T] `q_capped_compare.py`):

| Veto threshold | Uncapped: passing | Uncapped: target rate | Capped: passing | Capped: target rate |
|---|---|---|---|---|
| 0.50 | **1.57%** | **0.581** | **6.22%** | **0.408** |
| 0.60 | 5.93% | 0.469 | 17.29% | 0.366 |
| 0.70 | 33.60% | 0.353 | 41.89% | 0.327 |

At 0.50 the two sets share 49,032 calls, and the two skeptics' scores correlate at 0.83. At a
matched pass rate the uncapped skeptic ranks better: at about 6% passing, uncapped at 0.60 reaches
0.469 against capped at 0.50's 0.408.

**In the funnel** (§1b; alphabetical, tier-3 reference fees, **zero spread**, 18 months): the
uncapped skeptic leaves **1 trade** and the capped one **15**. That comparison is after fees and
before spread. Ranked by `log_return_4` at the same friction: 52 against 79
(`outputs/q_funnel.out`).

### 5b. The veto sweep of 2026-09-14, uncapped skeptic, all 405 folds. FINAL for the skeptic it measured.

**Every figure in 5b describes the uncapped skeptic.** The capped skeptic's sweep across all 405
folds is **NOT MEASURED** (capped skeptics exist for folds 326 to 404 only).

Out-of-sample BUY calls, folds 1 to 404: 8,948,485, target rate 0.2383 (all test rows 0.2422).
Survivors are calls with P(wrong) ≤ threshold. The no-skill band shuffles each fold's own scores
across its calls, 20 times. Source: `docs/dataset/skeptic-veto-sweep-2026-09-14.md`.

| Threshold | Survivors | Share | Survivor target rate | No-skill band |
|---|---|---|---|---|
| 0.30 | 9,373 | 0.10% | 0.6349 ± 0.0085 | 0.2711–0.2892 |
| 0.40 | 51,145 | 0.57% | 0.6035 ± 0.0037 | 0.2563–0.2621 |
| 0.50 | 154,979 | 1.73% | 0.5309 ± 0.0023 | 0.2550–0.2596 |
| 0.60 | 583,121 | 6.52% | 0.4403 ± 0.0014 | 0.2602–0.2629 |
| 0.70 | 2,859,743 | 31.96% | 0.3482 ± 0.0007 | 0.2645–0.2653 |

At 0.50 the survivors beat the vetoed calls in every test year from 2017 to 2024 (0.43 to 0.58
against 0.19 to 0.27).

**Against the predictor's own confidence at matched counts.** For each fold, the top N BUY calls by
calibrated `p_target` were taken, where N is the skeptic's survivor count in that fold. Source:
`docs/dataset/skeptic-vs-ptarget-2026-09-14.md`.

| Threshold | N | Skeptic target rate | Top N by `p_target` | Skeptic's margin | Calls in both sets |
|---|---|---|---|---|---|
| 0.30 | 9,373 | 0.6349 | 0.5605 | +0.0744 | 29% |
| 0.50 | 154,979 | 0.5309 | 0.4731 | +0.0578 | 44% |
| 0.60 | 583,121 | 0.4403 | 0.4097 | +0.0306 | 47% |
| 0.70 | 2,859,743 | 0.3482 | 0.3433 | +0.0049 | 68% |

The skeptic adds selection beyond the predictor's own ranking at the strict end, and almost none
at the loose end.

**Two caveats that travel with 5b:**

- All its rates are before friction.
- The progress tracker's Finding 1 requires every number measured on the uncapped skeptic to be
  re-measured on the capped one before it is cited as describing the ruled system. §5a shows that
  in this window the two differ by a factor of four in pass rate.

---

## 6. The predictor's overconfidence

Candidates that clear the cost bar carry expected moves of at least the bar (1.50% at tier 3) and
at most just under 3.0% (§2). What they realise, before any friction:

| Set | Calls | Realised mean | Source |
|---|---|---|---|
| Alphabetical candidates clearing 1.50%, full span | 938 | **+0.320%** | [T] `2026-09-18_q_net.py` |
| The same, 1.5-year window | 74 | +1.251% | `outputs/q_window.out` |
| The same, one position per pair, 1.5-year window | 34 | +0.781% | `outputs/q_window.out` |
| All out-of-sample BUY calls (expected move > 0), full span | 8,950,912 | target rate 0.2383 against 0.2422 for all rows | `skeptic-veto-sweep-2026-09-14.md` |

**Across the full span, the calls confident enough to clear the cost gate realised about a fifth of
the smallest expected move they could carry**: +0.32% against at least 1.50%. The fee of 0.60% was
charged against that +0.32% and left −0.28% per trade, with an interval excluding zero
([−0.42%, −0.14%]). **That shortfall between what the model promises and what the market delivers
is what the cost gate is left to absorb**, and at every tier the gate is priced on the promise.

**The window was kinder.** The same selection realised +1.25% there, and +0.78% with one position
per pair. The shortfall is real across eight years, and its size varies by period.

The period difference has a section of its own, §6a.

**Whether the most confident calls are the most overconfident is NOT MEASURED.** That would need
the realised return by expected-move decile, or a calibration curve of expected move against
realised return, and neither was computed. The measured statement is narrower: the calls above the
bar realise far less than the bar.

**SIMULATED VALUE PENDING:** the chain trades' mean expected move at entry beside their realised
return. That comparison needs the approval record Phase 7 prerequisite 7 adds.

### 6a. The shortfall depends on the period. A caveat on §6, raised here rather than waited for

The same selection (the alphabetical candidate clearing 1.50%, tier-3 fees, zero spread) realised
very different means in different periods:

| Period | Calls | Realised mean | How obtained |
|---|---|---|---|
| Full span, 405 folds (2017-04 to 2025-01) | 938 | +0.320% | measured ([T] `2026-09-18_q_net.py`) |
| The 1.5-year window (2023-07 to 2025-01) | 74 | +1.251% | measured (`outputs/q_window.out`) |
| The final 365 days (2024) | 71 | +1.177% | measured ([T] `2026-09-18_q_net.py`) |
| Full span **excluding** the final 365 days | 867 | about +0.25% | derived: (938 × 0.320 − 71 × 1.177) / 867 |
| Full span **excluding** the 1.5-year window | 864 | about +0.24% | derived: (938 × 0.320 − 74 × 1.251) / 864 |

- The two derived rows are arithmetic on the published means, which are rounded to three decimals.
  They are not a recomputation.
- **71 of the window's 74 calls fall in its final 365 days.** The window's strength is
  essentially 2024's.

**What this means.** The full-span shortfall (+0.32% realised against at least 1.50% expected) is
an average over periods that behave very differently: about +0.25% before 2024, about +1.2% in
2024. It is therefore a caveat on §6. It is possibly a property of the early years rather than of
the model. The skeptic's survivor target rates at 0.50 point the same way (§5b): 0.58 and 0.57 in
2023 and 2024, against 0.43 to 0.51 in 2017 to 2022.

**What cannot be separated from what is on disk.** Two explanations fit:

- a model that improves as its training history lengthens and the universe widens;
- a market in 2023–24 that happened to reward the same calls.

The per-year realised mean of cost-clearing calls, for years other than the final 365 days, is
**NOT MEASURED**, and neither is any control that separates the two explanations.

**Why it matters for the simulation.** The simulated window is the six months ending 2025-01-04,
inside the strong period. A simulated result, favourable or not, describes that period. It must not
be read as the full span's behaviour.

---

## 7. What the archive cannot test

Each item is a property of the data. Each states what the simulation substitutes and what the
substitution costs.

| Missing | What the simulation substitutes | What it costs |
|---|---|---|
| **Spread.** The archive is trades only; bid and ask were never published. | The declared bucket table of §3, served as a synthetic top of book around the last traded price. | Spread is declared, not observed. The table comes from 7.4 days of 2026 and is applied to 2023–24; its IQRs span roughly a factor of 2 to 3 within a bucket. 159 of 231 archive pairs never had their own spread measured. |
| **The order book.** Engine 9 has no depth to walk, so it would publish nothing and engine 10 would refuse every candidate. | A synthetic book with declared depth from the same buckets, walked by engine 9 unchanged. | Slippage rests on an evenly-spread-book assumption fitted to one depth point per pair ($10,000). The one real walk on file is a single BTC/USD fixture. For a tenth of the 72 recorded archive pairs the 10-level book held $10,000 in fewer than 19% of minutes ([T] `q_depth.py`), so live, engine 9 would refuse some of them as too thin, and the synthetic book will not. |
| **Pair rules for the window.** The only `AssetPairs` on disk is invented Phase 0 data. | A genuine `AssetPairs` recorded in 2026 (Phase 7 prerequisite 9). | **Tick size, checked:** of 72 pairs comparable between the 2023–24 archive and the 2026 recording, 57 have the same price grid, 15 are finer in 2026, none coarser (`outputs/q_ticks.out`), so entries can sit between historical ticks on about a fifth of pairs. **`ordermin` and `costmin`: unverifiable**; the smallest prints are not the minimum order, because partial fills print below it. |
| **Survivorship.** A 2026 `AssetPairs` omits pairs delisted since 2023–24, and engine 7 excludes a pair with no rules. | Nothing: those pairs leave the universe. | The count of window pairs missing from the recorded `AssetPairs` is **NOT MEASURED**; it can only be taken once the file is recorded. The recorder's own pair list cannot answer it, since it holds only USD pairs above a volume floor. |
| **Fees for the period.** No `TradeVolume` response was ever recorded, and nothing on disk dates any schedule before the one in force on 2026-09-19. Kraken restructured its tiers on 9 July 2026. | Kraken's published schedule fetched 2026-09-19, committed with its URL and time, read only in replay mode (invariant 2 amendment). | The 2026 schedule is applied to a 2023–24 window. The fee is the input the result is most sensitive to: under the ruled ranking, 46 trades at fees of 0.60% against 254 at 0.40% over 12 months (§4). |
| **The fee schedule's pair classes.** The published schedule has a separate table for FX pairs, stablecoins in the base currency and pegged tokens. | One tier from the "Spot Crypto" table for every pair, unless spec 130 maps the other class. | Eleven archive USD pairs would plausibly fall under that other table: AUDUSD, EURUSD, GBPUSD, USDTUSD, USDCUSD, DAIUSD, TUSDUSD, PYUSDUSD, TBTCUSD, WBTCUSD, and possibly PAXGUSD. Whether any of them is ever a candidate is NOT MEASURED. |
| **Entry fills.** Every offline figure assumes the trade was entered at the bar's close. | The paper broker's pessimistic rule: a post-only buy fills only on a trade strictly below its limit, from the time-and-sales. | The offline counts are upper bounds on fills. Fills that do happen are selected towards falling markets (adverse selection). |
| **Complete features.** 50.2% of out-of-sample rows carry an unfilled lookback (Phase 5, Finding 3). | Nothing: engines 13 and 8 refuse them, correctly. | The surviving population is the more liquid half, and 62% of window bars are refused before a prediction (§1b). |
| **2025.** The walk-forward died at fold 405. | Nothing. | No test week after 2025-01-03. |
| **Choosing configurations on the same data.** The grids above were searched on the out-of-sample file, and the ranking study behind `log_return_4` used it too. | Expected-move ranking replaces the studied feature with the predictor's own output (§R.2), and the promotion bar is fixed in advance (§R.4). | The residual is stated in §R.2: the amendment was decided with the §4 grid in view. The deflated metric's trial count should include every cell searched here. |

---

## 8. On every interval in this document

Each interval is the mean ± 1.96 standard errors, treating the trades as independent. **They are
not independent.** Consecutive decision bars share most of a 48-bar label window. Pairs move
together, and so do overlapping trades across the three concurrent slots. **The true intervals are
wider than those reported.** The one-position-per-pair filter removes the worst overlap within a
pair, but none of the overlap across pairs.

**Where a count is too small for an interval to mean anything.** Below about ten trades, and
wherever the trades come from two or three pairs, an interval says nothing about the system. It
describes a handful of outcomes on a handful of assets. Every such cell above is marked "interval
not meaningful" or shows its n. Those include:

- the alphabetical cells with 1 to 12 trades;
- the 3-trade bucket cells at 0.60% fees;
- the 1-trade end of the §1a funnel.

---

## 9. Slots the simulation fills

| Section | Slot |
|---|---|
| §1a, §1b | The chain's stage-by-stage counts, including engine 9, entry fills, `ordermin`/`costmin` and engine 17 |
| §2 | The chain's trade count and net per trade at tiers 3 and 5 |
| §3 | The bucket arm's chain figures |
| §4 | The expected-move ranking's chain trade count, pairs and net, at tiers 3 and 5 |
| §6 | The chain trades' expected move at entry against realised return |
| New | The equity curve including cash periods; alpha against the buy-and-hold benchmark; the per-trade reasons for approval (prerequisite 7); the promotion verdict against the bar fixed in §R.4 |

## 10. Findings the simulation will not change

- **The tier-1 proof (§2).** Structural: the calibration and barriers cap the expected move at
  3.0%, and the gate needs strictly more. The observed 2.9999999930% corroborates it.
- **The spread inversion (§3).** A constant spread made thin-pair trades look profitable; a
  liquidity-dependent spread removed the gain.
- **Alphabetical ordering's concentration (§4).** One pair on 56% of bars.
- **The capped against uncapped skeptic (§5a)**, and the 2026-09-14 sweep for the skeptic it
  measured (§5b).
- **The overconfidence of cost-clearing calls over the full span (§6).** +0.32% realised against at
  least 1.50% expected, **with its caveat (§6a)**: about +0.25% before 2024 and about +1.2% in 2024.
- **The fee schedule (§R.3).** The figures, and the fact that nothing dates a schedule before 9 July
  2026.
