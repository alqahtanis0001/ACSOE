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

Written 2026-09-19, at `f0e7514` plus this document. **Revised the same day** (§R), twice: first for
four operator rulings made after the first version was written, then for the last seven (R2, R4,
R8, R9, R10b, R11, R12) and a check of the $60 figure (§R.1). Every section below that the rulings
touch says so. Scripts and their raw outputs are in
`docs/dataset/phase-7-recon-2026-09-19/` (`scripts/` and `outputs/`). Where an output was only
printed to a terminal, it is transcribed verbatim in `outputs/transcribed-terminal-outputs.txt`,
cited below as **[T]**.

---

## R. What the project ruled on 2026-09-19, after this document was first written

**R.1 The tiers simulated are 3 and 5.** Operator ruling, overturning the lead's earlier
recommendation of 3 and 4. The reason is the framing:

- **Tier 3 is reachable by a small retail account.** It needs $10,000 of 30-day spot volume or
  $20,000 of assets on platform.
- **Reaching tier 3 by volume costs about $60 in fees at most.** The $60 is the **fee cost** of
  generating the $10,000 of volume. It is not the volume.
  - The arithmetic: a $1,000 balance bought and sold back generates $2,000 of volume per round trip.
    At tier 1's 1.20% round trip (maker 0.40% in, taker 0.80% out), that round trip costs about $12
    in fees. Five round trips make $10,000 of volume and cost about $60.
  - The cost does not depend on the balance. It is the volume times the average fee per side: $10,000
    × 0.60% = $60. A larger balance needs fewer round trips for the same total.
  - **$60 is an upper bound.** It charges every trade at tier 1's rates. The fetched schedule (§2)
    has a tier 2 from $2,500 of volume, at 0.30%/0.60%. If the tier moves up as the volume accrues,
    the first $2,500 costs $15 (0.60% average per side) and the remaining $7,500 costs $33.75 (0.45%),
    **about $49 in all**. How quickly Kraken re-tiers an account is not on disk, so the range is
    stated: **about $49 to $60**.
  - Not counted in either figure: the spread paid on each taker exit, and the price risk of holding
    between the buy and the sell.
- **Tier 5 needs $50,000 of 30-day volume or $100,000 held**, a scale most retail accounts never
  reach.

The two runs state the cost-adaptive selectivity claim at both ends. Round-trip fees under the
fetched schedule (§2) are 0.60% at tier 3 and 0.45% at tier 5.

The contrast was first argued from `log_return_4` figures: 3 trades at 0.60% and about 35 at 0.45%.
**Those belong to the ranking the next ruling replaced.** Under the ruled ranking, the measured grid
has 46 trades at fees of 0.60%, 119 at 0.50% and 254 at 0.40% over 12 months (§4). Fees of 0.45%
were not computed, so tier 5's count lies between the 0.40% and 0.50% rows and is **NOT MEASURED**.

**R.2 Engine 7 ranks its universe by engine 8's expected move, batched.** Invariant 4 is amended to
permit it. The sentence "a model may only ever make the system less willing to trade, never more"
is replaced by the operator's wording (R12, ruled 2026-09-19):

> A model may never cause a trade that a gate would refuse, and may never soften, bypass or
> override a gate's verdict. A model's output may order candidates for examination, provided every
> gate judges the chosen candidate independently and no gate's verdict is influenced by the
> ordering. Ordering changes which candidate is examined, never whether an examined candidate is
> approved.

The invariant records beneath it that it was amended on 2026-09-19 to permit this ranking. It
raises trades from 3 to 46 at tier 3 with the net unchanged at roughly zero. It was amended to
obtain a sample large enough to measure, not a more favourable result, and had the net moved from
negative to positive the operator would have treated that as a warning and not amended. **The
ranking skips pairs the anomaly and DI gates would refuse (R11)**, because the 46 was measured that
way, and the simulation must match the measurement. Each gate still judges the chosen pair itself.
This closes spec 75, open since Phase 3.

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
advance is the point. **Its working form was ruled on 2026-09-19 (R10b), as proposed:** the
interval is computed allowing for overlapping holds, then widened for the number of trials, and a
model is promoted only if the widened interval's lower bound is above zero. The operator notes that
this is stricter than the original wording, which is correct. The exact statistics are fixed in
spec 139 and committed as code with a worked example before any simulated figure exists.

**R.5 The simulation runs the capped skeptic (R2).** The skeptic is trained on the last 13 folds'
BUY calls, as ruled on 2026-09-16. In the operator's words: *1.6% passing at a 58% hit rate against
6.2% at 41% is a difference in this data at the step that decides the funnel's end, not a
difference in principle* (§5a).

**R.6 The window is THREE months (R4 as amended by the operator, 2026-09-19 evening).** It is folds
392 to 404, test weeks from 2024-10-05 00:15Z to fold 404's test close at 2025-01-04 00:00 UTC.
R4 first ruled six months (folds 379 to 404). The operator cut it to three because the report
deadline is Sunday 2026-09-20 13:00 and six months does not fit (D23 in the overnight decision
log). **Only the window is shorter:** every engine and every gate runs, guard through manage, as
live. The limitations the cut brings are stated in §7b. **Two runs: tier 3 and tier 5, both on engine 8's
expected-move ranking.** There is no alphabetical run: it is the name of the limitation the
ranking removed, and whether the model has skill is answered by the benchmark basket (§R.7) and
the promotion bar (§R.4) (operator ruling 2026-09-19). Nothing else is configured. The tiers run in parallel on separate databases. The folds within a tier
run in sequence, because account state crosses fold boundaries and a freeze in one week changes
every week after it.

**R.7 Two benchmarks (R8).**

- **BTC/USD buy-and-hold** answers the question an examiner asks first: would holding Bitcoin have
  done better?
- **An equal-weighted basket of the pairs the run actually held**, held while the run held them and
  in cash otherwise, answers the second: would holding the same pairs over the same periods have
  done as well without the barriers?

Each is reported against the run's equity curve including its cash periods.

**R.8 What counts as a trial (R9).** Every configuration ever evaluated against the out-of-sample
data counts as a trial, **listed one by one, not summarised**:

- the leaderboard rows;
- every cell of the reconnaissance grids;
- the ranking study's features;
- the skeptic veto sweep's thresholds;
- the DI and anomaly percentiles compared on this data;
- this phase's runs (the committed ledger counts four; two run, a deliberate overcount of two).

The count errs high on purpose, and the ledger says so. An overstated trial count makes the haircut
harsher and the result harder to claim, which is the right direction to err (spec 139).

**R.9 The residual circularity, stated by the project rather than found by a reader.** §R.2's
"What remains" is a limitation of the evaluation and goes into the write-up as one. The
expected-move grid was computed on the same out-of-sample data this report uses. Three things bound
it: sample size was the stated criterion for amending, the net stayed at about zero under every
row, and the promotion bar was fixed before anything ran.

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
trade at tiers 3 and 5 over the three months (§R.6).

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

**Why it matters for the simulation.** The simulated window is the three months ending 2025-01-04
(folds 392 to 404), inside the strong period, and narrower still (§7b). A simulated result, favourable or not, describes that period. It must not
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
| **Choosing configurations on the same data.** The grids above were searched on the out-of-sample file, and the ranking study behind `log_return_4` used it too. | Expected-move ranking replaces the studied feature with the predictor's own output (§R.2), and the promotion bar is fixed in advance (§R.4). | The residual is stated in §R.2 and §R.9: the amendment was decided with the §4 grid in view. Every cell searched here is a trial in the deflated metric's ledger (§R.8, ruled R9). |

---

## 7a. The declared substitutes the chain simulation runs on (written before launch, 2026-09-19)

The simulation is **two runs: tier 3 and tier 5, engine 8's expected-move ranking, the median
column of the bucket table, over the three months ending 2025-01-04** (operator rulings
2026-09-19). Every input below that the 2023–24
archive does not hold is either **declared** or **recorded in 2026**, and each is named with its
source and date. None is a measurement of the period it is applied to.

| Input | What the run uses | Source and date |
|---|---|---|
| **Spread** | Per pair, the **median** spread of its liquidity bucket, keyed on the pair's trailing 24-hour dollar volume computed from the replayed trades: 30.4 bps (< $10k), 25.8 ($10k–100k), 12.3 ($100k–1M), 5.5 ($1M–10M); the > $10M bucket uses the $1M–10M row. Served as half the spread either side of the last traded price. A pair with no trade in 24 h has **no quote**, never a zero spread. | `tests/fixtures/replay/spread_book_table_2026-09-19.json`, built by `scripts/build_bucket_table.py` from the recorder's minute summaries of 185 recorded USD pairs, 2026-09-11 16:13Z to 2026-09-19 00:45Z (7.36 days). Per pair, the median of each clean minute's median spread; per bucket, the median of the per-pair medians. The interquartile ranges are published there as declared uncertainty. |
| **Book depth** | Per bucket, the median bid depth to $10,000 from mid: 86.2 / 100.5 / 35.2 / 8.9 bps. Laid as 10 evenly spaced levels from the half-spread to that depth, and walked by engine 9 with its own arithmetic. That serves $5k slippage of 15.8 / 19.5 / 6.5 / 1.4 bps. | Same fixture and recording span. The table's continuous-book check figures (17.7 / 20.8 / 7.5 / 1.7) differ because the served book is ten discrete levels. |
| **Pair rules** | Kraken's `AssetPairs` as recorded (REST, verbatim), keyed by the engines' names through the websocket `instrument` snapshot captured with it. The 2026 tick sizes apply, finer than 2024's on 15 pairs. | `tests/fixtures/kraken/asset_pairs_recorded_2026-09-19.json`, `instrument_recorded_2026-09-19.json` and `pair_names_recorded_2026-09-19.json`, captured 2026-09-19 (spec 127). |
| **Fee tier** | Kraken's **Spot Crypto** schedule, served to every pair (D8): tier 3 at 0.22% maker / 0.38% taker, tier 5 at 0.15% / 0.30%. The FX, stablecoin and pegged-token pairs are overcharged by this, the conservative direction. | `tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`, fetched 2026-09-19T02:59:51Z from kraken.com/features/fee-schedule, with the raw page and the 9 July 2026 restructuring article committed beside it. |

**Declared limitations, stated before any figure exists:**

1. **Every substitute is 2026 applied to 2024.** The spread and depth come from 7.4 days of
   September 2026; the pair rules and the fee schedule are as of 2026-09-19. Liquidity, pair rules
   and Kraken's fees in July 2024 to January 2025 are not on disk, and the run does not know them.
2. **Survivorship: 39 of the 231 archive USD pairs trading in the window are absent from the 2026
   rules and are excluded from the universe** (42 of 234 over the 1.5-year window; spec 127). Some
   are probable rebrands (MATIC/POL, FTM, MKR, and RNDR in the 1.5-year count), so 39 is an upper
   bound on delistings. The universe is therefore biased towards pairs that still trade in 2026,
   the survivors. Pairs that failed between 2024 and 2026 cannot be traded in the simulation even
   if they were candidates in 2024. That can flatter or harm the result, and the direction is not
   known.
3. **The fee schedule is 2026's too.** Kraken restructured its tiers on 9 July 2026, and nothing on
   disk dates any earlier schedule. Fees are the input the result is most sensitive to (§4: under
   the ruled ranking, 46 trades at 0.60% fees against 254 at 0.40% over 12 months).
4. **Spread sensitivity was NOT run through the chain** (operator ruling 2026-09-19: the extra
   runs would push the tier-3 run past 32 hours). **A different spread changes WHICH trades
   happen, not only what they earn.** Spread is part of friction, friction decides the cost gate,
   and the gates after it, the entry fills and the account's path follow from that. So the effect
   of a different spread on the trade set is **unrecoverable without a re-run.** What is available
   instead:
   - the offline flat-against-bucket comparison of §3, which found that a constant spread inverted
     the sign of the result;
   - a post-run script that re-prices the trades that did happen under another spread, which
     answers what they would have earned and nothing about which trades would have happened.

## 7b. Stated before any simulated figure exists (written 2026-09-19, before launch)

Everything in this section was written before either run began, so none of it was chosen after a
result was seen.

### The three-month window: chosen constraints, with their cost

1. **Three months and 13 retrained models, not six and 26.** The claim that the system was tested
   across weekly retraining rests on 13 retrains and one season.
2. **The window sits inside a strong directional market** (§6a), and three months narrows that
   warning further. The alpha regression has **91 daily returns**.
3. **Expected trades: about 8–11 at tier 3 and 27–55 at tier 5.** Tier 3 is at or below spec 139's
   10-trade threshold, below which the promotion gate reports no interval, so **tier 3's result is
   descriptive.**
4. **The three-month cell was never measured offline.** Those estimates are scaled from the six- and
   twelve-month cells of §4 (22 and 46 trades at 0.60% fees), with a 3-in-4 entry fill rate taken
   from the rehearsal.

### What the promotion bar can find at these trade counts: expected to be unreachable

The bar is fixed (§R.4, spec 139): the lower bound of an interval widened by Bonferroni over **N =
1,679 trials** must exceed zero. The minimum mean net return per trade that could clear it is
`q × SD / √n`. Here `q` is the committed code's Student-t quantile at confidence `1 − 0.05/N`, and SD
is the per-trade standard deviation of the §4 expected-move cells (about 2.2–2.3%). HAC can only
widen the standard error, so these are lower bounds:

| Tier | Expected n | q | Minimum mean net return per trade |
|---|---|---|---|
| 3 | 10–11 (fewer gives no interval) | 7.71–7.19 | **4.9–5.5%** |
| 5 | 27–55 | 5.05–4.56 | **1.35–2.14%** |

- **Tier 3 cannot clear the bar.** The required mean exceeds the net return of a single target exit
  (about +2.3% after tier-3 friction), so no possible mix of outcomes reaches it. The only exception
  is a degenerate run in which every trade returns the same amount.
- **Tier 5 cannot plausibly clear it.** Ignoring timeouts, it needs a target-hit rate of roughly 76–94%.
  The skeptic's survivors hit targets at 0.39–0.58 (§5), and the expected-move cells net −0.26% to
  −0.17% per trade (§4).

**So a non-promotion is the expected outcome of this design, not a finding about skill.** It follows
from the trade counts and the pre-registered trial count. The run's value is its record (the funnel,
the approvals and refusals with every gate's numbers, the equity curve against both benchmarks), not
a promotion verdict.

### The trial count

**N = 1,679, pre-registered** (`docs/dataset/phase-7-trial-ledger.json`). It is built by a script
from the committed outputs, counting every configuration ever evaluated on the out-of-sample data.
The ledger counts **four** Phase 7 runs (two rankings at two tiers, as first planned). **Two run**, so
the ledger **overcounts by two, deliberately, in the harsher direction**. N is not changed after any
figure exists.

### The benchmarks

- **BTC/USD buy-and-hold** over the run's own window.
- **An equal-weighted basket of the pairs the run held, while it held them, cash otherwise** (R8).
- **Two secondary baskets, computed after the run from stored data:** the held pairs bought and held
  over the whole window, and the equal-weighted universe.

**No claim is made that any of these is the standard benchmark in the crypto backtesting
literature.** No source was verified for such a claim.

### Measured before the run, and stated with their limits

- **F4, the capped skeptic against the predictor's own confidence, in the simulation window.** Over
  1,237,399 out-of-sample BUY calls (folds 379–404), the capped skeptic at 0.50 passes 8.38%
  (about 103,700 calls) at a target rate of 0.3935. The same number of calls taken by the
  predictor's own `p_target`, per fold, reaches 0.3953.
  - The difference, 0.0018, is about 0.8–1.2 standard errors under an independent-binomial
    approximation. The two sets overlap heavily and share 48-bar label windows, so the true band is
    wider.
  - **Stated as: no detectable difference.** Not "the skeptic adds nothing". No formal test was run.
  - The uncapped skeptic did beat the same comparison over all 405 folds (+0.058, §5b).
  - Source: `docs/build-log/phase-7/c-interface.md` (c-models).
- **F6, a train/serve skew in the features of unmoving pairs.** Engine 5 over 200 published bars
  yields exact zeros where the training dataset carries floating-point residues.
  - **Measured** (c-models, all 2,216,920 out-of-sample rows of folds 379–404 re-scored with the
    residues zeroed): 12 columns affected; 23,155 rows carry a residue; the expected move changes on
    2,308 rows, by at most 0.453 pp. **No complete row crosses a cost bar of 1.25% or above.** The
    measurement assumes live yields exactly 0.0 wherever the dataset has a residue.
  - **Calculated, not measured:** the lowest cost bar the simulation can apply, 2.5 × friction in the
    most liquid bucket, is **about 1.30% at tier 5** and **about 1.67% at tier 3**. This is arithmetic
    from the declared table and the fee schedule.
  - So F6 can change which pair is ranked first, and **cannot change a cost verdict.** The run matches
    what the live daemon computes; it is the training data and the offline grids that carry the
    residue.
- **F5, the target exit.** A target exit sells at market on the next minute's tick, as built. In the
  rehearsal, one target exit realised +2.0% where the label books +3.0%. **The run's realised returns
  on targets are expected to sit below every offline grid in this document**, because the grids use
  the label's +3.0%. The run measures the exit rule as built. Changing it now would be changing the
  system to help it pass its own test.

### How the runs were run: two facts stated before launch

- **An intermittent native fault, and resumes.** The gating rehearsal on the final code
  (`19c5a11`) crashed once, 2026-09-19: an access violation in polars' row export to Python
  (`export.rs:59`), 54 ticks into the day. Two identical reruns of the same span on the same code
  ran cleanly, so the fault is not deterministic.
  - **By operator ruling**, a watchdog resumes a run whose process has died, with its exact
    command plus `--resume`. It never touches a live one.
  - **A resume does not change the result.** The rehearsal's kill-and-resume check shows a
    resumed run writes the same rows as an uninterrupted one.
  - **Every resume is recorded** (run, tick, time, number), and **the count per run is reported
    with the results.**
  - **An A/B test decided that SHAP stays in.** A second rehearsal also crashed, in engine 3's
    candle build, a different polars entry point. The operator then fixed a decision rule before
    any result, and the same full day ran four times at the commit without the SHAP writer
    (`3efe958`) and four times at the launch commit (`19c5a11`), in parallel. **Neither arm
    crashed** (1,700 ticks each). **That exonerates nothing.**
    - At the observed rate on the launch commit (2 crashes in 3,531 ticks, about 1 in 1,765),
      each arm expected about 0.96 crashes.
    - Zero in one arm has a probability of about 0.38. Zero in both, if the rates were equal,
      about 0.15. So zero in both is ordinary whether or not the writer is implicated.
    - What the A/B established is that **the rate is lower than the first estimate** (1 in
      about 900 ticks): low enough to launch on, not low enough to clear anything.
    - For comparison: 0 crashes in 5,988 ticks on earlier code.
    - The two crashes faulted in two different Windows modules, with no hardware errors logged.
      That is consistent with heap corruption, and leaves the machine as suspect as the library.

    **By the pre-set rule, the runs launch with SHAP**, with the watchdog allowed up to 40
    resumes per run and 8 per hour. The loop detector is unchanged: two consecutive resumes
    dying at the same tick stop a run.
- **The loss-streak breaker trips correctly; its recovery path does not exist.** Found by running
  the system on 2026-09-20, not by reading the code: the tier-5 run froze on `loss_streak` at
  2024-10-20 05:30Z, after five consecutive stops, and stayed frozen for the rest of the window.
  - **What the check measures, correctly:** `safety._loss_streak` counts a **consecutive** streak
    — losses counted backwards from the most recent closed trade until any non-losing trade
    breaks the run — **not** a running total. A single winning closed trade resets it to zero,
    however many losses came before. That is the intended rule, implemented correctly.
  - **What it cannot do:** it **recomputes from trade history every tick and holds no state.** It
    has no reference to the system mode, the `commands` table, or any clear event. So **an
    operator reactivation cannot reset it**: the same five losses are counted again on the next
    tick and the freeze re-trips.
  - **The gap is the recovery path.** The intended behaviour is that clearing a freeze starts a
    **fresh** streak — the operator has seen those five and decided to continue, so the system
    should count from zero and freeze again only on five new consecutive losses. It cannot,
    because the count comes from history and history does not change. **The fix:** record the
    clear's timestamp and count only losses closed after it. Phase 8; not changed during the runs.
- **One launch precondition was judged met by hand, and is declared here rather than left
  silent.** The gating rehearsal's `kill-and-resume identical` check was false. The cause is the
  check, not the system: `rejections.shap_ref` embeds the writing tick's cycle number, and a
  resumed process restarts `cycle_id` at 1 by design. The harness excludes `cycle_id` and
  `run_id` as columns, but not the copy of them inside that path.
  - **Evidence, in all five gating rehearsals:** with `shap_ref` excluded, **every table is
    byte-identical** between the uninterrupted run and the killed-and-resumed one, and the 71
    SHAP refs match one for one once the run and cycle segments are ignored.
  - So a resume changes no decision, and the operator ruled the precondition met on that
    evidence. Every other precondition was met by the committed check script. Correcting the
    harness's exclusion rule is a Phase 8 item.
- **Each run's first decision bar is skipped by design.** On a fresh database engine 7 has no
  stored equity to size positions against until engine 19 writes the first row at the end of
  tick 1. Engine 7 fails closed rather than fall back to a balance, so it blocks tick 1
  (`scout_inputs_unavailable`). That is one bar per run, 2024-10-05 00:15Z, the same at both
  tiers.

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
| New | The equity curve including cash periods; alpha against both benchmarks (§R.7); the per-trade reasons for approval (prerequisite 7); the promotion verdict against the bar fixed in §R.4; the trial count from the committed ledger (§R.8) |

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

---

# Part II. The chain simulation: how it runs, and what it has produced so far

**Written 2026-09-20 at 16:25 local, with both runs still going.** Everything here was read from
snapshot copies of the live databases (SQLite's backup API); neither run was stopped, touched or
reconfigured. Figures are "as at 16:25" unless they are marked final.

## 1. THE SIMULATION AS BUILT

**What it is.** Engine 23 `backtest` drives the *same* engines, in the *same* orchestrator, over
history instead of a live feed. No engine is stubbed, disabled or given a shortcut. The only
substitutions are the inputs the 2023–24 archive never recorded, and those are declared in §7a.

**The clock and the two kinds of tick.** The loop ticks every simulated minute.

- **A bar tick** is the minute in which a 15-minute decision bar closes: 96 a day, **8,736 over
  the window**. Engine 3 `market_sensor` publishes `bar_closed`, and only then does engine 5
  `feature` let the opportunity chain continue. This is where a candidate is chosen and judged.
- **A minute tick** is any other minute. Engine 5 returns `PASS` and the opportunity chain stops
  at once, but **the guard and manage chains still run**, so an open position is watched every
  minute rather than every quarter hour. Its stop, target and timeout are decided from the
  per-minute trade range. **Minute ticks are only run while the run is exposed** — holding a
  position or a resting entry — which is why a run with no open trades advances in bar ticks
  alone.

**The full chain, every bar tick, guard through manage** (`engine-contracts.md`'s registry):

- **Guard, always, in every mode:** 1 `exchange`, 2 `market_data_recorder`, 3 `market_sensor`,
  4 `data_guard`, 17 `safety`. The guard chain never breaks early: two guards can block on one
  tick and both are recorded.
- **Opportunity, only when running and unblocked:** 5 `feature`, 6 `macro_context`, 7 `scout`
  (the universe filter and the expected-move ranking), 12 `regime`, 13 `anomaly`, 8 `prediction`,
  9 `order_book`, 10 `cost`, 11 `risk`, 14 `adaptive_router`, 15 `skeptic`, 16 `decision`,
  18 `execution`. It **stops at the first block**, so the record says which gates never ran.
- **Manage, always:** 21 `position_manager`, 22 `exit`, 19 `memory`.

**The replay client** (`clients/kraken/`, spec 129) stands where the live Kraken client stands,
and refuses to be constructed outside replay mode. It serves: the period's **real trades** from
committed weekly partitions, walked forward and never past `now`; a **declared fee tier** from
Kraken's committed schedule; and a **synthetic order book** built from the declared
liquidity-bucket table around the last traded price — ten discrete levels, which engine 9 walks
with its own unchanged arithmetic to price slippage. A pair with no trade in 24 hours has **no
quote**, never a zero spread.

**What engine 19 `memory` records, every tick, as the single writer:** the equity snapshot;
positions, orders and closed trades; one `block_records` row per blocker; one `rejections` row
per refused candidate, carrying the refusing gate, its reason code, the economics and
`details` — every gate's verdict on that candidate; one `approvals` row per placed entry with
the same economics and verdicts on the approving side; one `scout_tallies` row for every tick
engine 7 ran, candidate or not (spec 146); and a SHAP parquet file per explained decision.

**How a run resumes.** Each run writes a run record beside its database. On `--resume` the driver
restarts after the **later** of the store's last tick and the record's last tick, so no tick is
decided twice, seeds `previous_now` so the first resumed tick measures its trade range from where
the killed process stopped, and mints a new `run_id`. The rehearsals show a resumed run writes
the same rows as an uninterrupted one.

### Why tier 3 and tier 5

- **Tier 3 rather than tier 4**, against tier 5: the contrast has to be visible. Tier 3's round
  trip is 0.60% and tier 4's is 0.55% — too close to separate from noise. Tier 5's is 0.45%.
- **Tier 3 is reachable by a small retail account:** $10,000 of 30-day volume or $20,000 of assets
  on platform, and reaching it by volume costs about $49–60 in fees (§R.1).
- **Tier 5 needs $50,000 of 30-day volume or $100,000 held**, a scale most retail accounts never
  reach.
- **The pair isolates cost as the only variable.** Same models, same window, same code, same
  declared spread and depth, same seed capital; only the fee tier differs. So any difference
  between the two runs is attributable to cost alone — which is the whole cost-adaptive claim.

## 2. WHAT IS RUNNING AND WHERE IT HAS REACHED

Both launched **2026-09-19 23:12:35 local** from commit `19c5a11`, detached through WMI, over
folds 392–404: test weeks **2024-10-05 00:15Z to 2025-01-04 00:00Z**.

| | Tier 3 | Tier 5 |
|---|---|---|
| Bar ticks | 6,127 of 8,736 (70.1%) | 6,587 of 8,736 (75.4%) |
| Simulated date reached | 2024-12-07 19:45Z | 2024-12-12 14:45Z |
| Fold | 401 of 404 (10 switches so far) | 401 of 404 (10 switches) |
| Minute ticks (exposure) | 613 | 152 |
| Candidates examined | 6,029 ticks | 1,452 ticks |
| Rejections | 6,016 | 1,445 |
| Approvals | 13 | 7 |
| Entries filled / cancelled | 9 / 4 | 5 / 2 |
| Closed trades | 9 | 5 |
| Open positions | 0 | 0 |
| Equity (from 5,000) | **4,920.06 (−1.6%)** | **4,645.59 (−7.1%)** |
| Range seen | 4,883.33 to 5,143.94 | 4,645.59 to 5,014.18 |
| State | trading | **frozen since 2024-10-20 05:30Z** |
| Crashes / resumes | 0 / 0 | 0 / 0 |

**Tier 5's figures are FINAL.** It is frozen on the loss-streak breaker and can take no further
trade for the remaining ~2,100 bar ticks: 5 trades, all stops, −354.41, −7.1%. Its remaining ticks
record the guard and manage chains and nothing else.

**Tier 3's figures are PARTIAL.** It is unfrozen, holding nothing, with about 2,600 bar ticks
(roughly four simulated weeks) to run.

**Tier 3's trades in full, as at 16:25:**

| # | Pair | Opened | Closed | Held | Outcome | PnL | Return |
|---|---|---|---|---|---|---|---|
| 1 | STORJ/USD | 10-20 04:34 | 10-20 05:22 | 0.8 h | stop | −71.03 | −2.13% |
| 2 | STORJ/USD | 10-20 05:49 | 10-20 06:42 | 0.9 h | target | +45.98 | +1.40% |
| 3 | DOGE/USD | 10-20 13:20 | 10-20 17:10 | 3.8 h | target | +83.55 | +2.52% |
| 4 | NEAR/USD | 10-25 23:46 | 10-26 02:47 | 3.0 h | target | +80.98 | +2.40% |
| 5 | DOGE/USD | 11-14 22:31 | 11-14 22:35 | 0.1 h | stop | −75.00 | −2.19% |
| 6 | DOGE/USD | 11-14 22:46 | 11-14 23:00 | 0.2 h | stop | −76.16 | −2.26% |
| 7 | CRV/USD | 11-15 05:17 | 11-15 06:19 | 1.0 h | target | +86.61 | +2.61% |
| 8 | OXT/USD | 11-25 22:33 | 11-25 22:39 | 0.1 h | stop | −80.03 | −2.37% |
| 9 | APT/USD | 12-02 03:47 | 12-02 03:57 | 0.2 h | stop | −74.84 | −2.25% |

Four targets, five stops, net −80.94 on closed trades. **Tier 5's five, all stops:** STORJ/USD
−82.23, −68.37, −72.00, −69.62 (all 19 Oct) and −62.19 (20 Oct).

## 3. DECISIONS — CHECKED AGAINST WHAT ACTUALLY RAN

Each recorded decision was checked against the running system's own rows. **Nothing on record
needed changing.**

| Decision | Checked against | Result |
|---|---|---|
| Two runs only, tiers 3 and 5, expected-move ranking | two `runs` rows, two databases; both record `ranking: expected_move`, `alphabetical_baseline: false`, and every `scout_tallies` row carries `rank_feature = expected_move` | holds |
| Three months, folds 392–404 | both began at 2024-10-05 00:15Z and are in fold 401 of 404 | holds |
| The declared substitutes (§7a) | tier 3's approvals price friction at 0.67% (fees 0.60% + bucket spread and served slippage); tier 5's at 0.52–0.64% | holds |
| The promotion bar and its statistics, fixed in code before the run | `modelling/promotion.py` and the trial ledger are unchanged since `bd96346`; nothing has been computed from the runs yet | holds |
| N = 1,679, with its deliberate overcount of two | ledger unchanged; two runs ran, as already declared in §7b | holds, and the overcount stands as declared |
| R8's basket: the pairs held, while held, cash otherwise | not yet computed; it is post-run arithmetic over stored rows, and the stored rows carry what it needs | holds |
| F5's exit rule run as built | confirmed in the data: the four target exits realised +1.40%, +2.52%, +2.40% and +2.61% against the label's +3.0% | holds, and see §4 |
| Spread sensitivity dropped (no q25/q75 runs) | only the two runs exist | holds |
| Invariant 10, no labels on the live path | no labelling module is imported by the replay chain; labelled outcomes remain post-run arithmetic | holds |
| Stop-at-first-block | visible in the record: 6,016 of tier 3's rejections name the cost gate and nothing later | holds |

## 4. FINDINGS FROM THE SIMULATION

**4.1 The breaker's recovery path does not exist (F7).** Recorded above in this section and in the
tracker as a Phase 8 item: tier 5 froze on five consecutive losses, `safety._loss_streak`
recomputes from trade history every tick and holds no state, so an operator reactivation cannot
reset it, and a replay has no operator anyway. Tier 5 therefore spent 5,116 ticks — and will spend
about 2,100 more — blocked.

**4.2 The funnel's real ratios, from stored rows** (tier 3, 6,118 tallies):

| Stage | Count | Note |
|---|---|---|
| Pairs scanned each tick | 1,450 | the recorded `AssetPairs` universe |
| Pairs entering the universe | 0–190 | the rest excluded, dominated by **`no_live_quote`: 1,260** on the last tally |
| Ticks with a candidate | 6,029 of 6,118 | the ranking almost always finds something to examine |
| Ticks with no candidate | 88 | plus 1 tick where engine 7 itself blocked (the first tick, no equity row yet) |
| Candidates refused | 6,016 | **6,006 `cost:net_edge_below_hurdle`**, 10 `cost:spread_wider_than_move` |
| Approved | 13 | |
| Entries filled | 9 of 13 (69%) | 4 cancelled at the 300 s window; fills land 1–5 minutes after placement |
| Closed trades | 9 | |

**4.3 Only one gate ever refused anything.** Every rejection in both runs names engine 10 `cost`.
No anomaly, DI, risk, skeptic, router or decision refusal exists in either database. Two causes,
and they matter for how the counterfactual dataset can be read: the ranking already skips pairs
the anomaly and DI gates would refuse (R11), so those pairs never become the candidate; and
stop-at-first-block means the cost gate ends the tick before the later gates are consulted.
**So this run says nothing about how often the skeptic or the risk gate would have refused.**

**4.4 What the cost gate refuses, and why it is not close.** Over tier 3's 6,016 refusals the
median expected move is **0.48%** against a median hurdle of **1.00%** — a median shortfall of
**1.22 percentage points**. The closest miss in the whole run was 0.039 pp. The ranking's most
frequent picks are **EUR/USD (1,253 ticks), AUD/USD (1,236), USDC/USD (539), USDT/USD (328),
GBP/USD (313)** — FX and stablecoin pairs sitting on the calibrators' low plateau. So the system
spends the overwhelming majority of its bars examining the highest-ranked pair available and
refusing it by a wide margin, and the trades that do happen come from the minority of bars where
a volatile pair tops the ranking.

**4.5 Both tiers ended in a protective freeze before the window closed. REWRITTEN 2026-09-20
21:55.** The earlier version of this passage read the contrast as "the cheaper tier admitted bad
trades while tier 3 refused them and stayed positive". **That reading is wrong and is withdrawn**:
it was written while tier 3 was at +1.5% and still trading. Tier 3 finished **worse** than tier 5.

What the run shows instead: **two runs differing only in cost, both stopped by their own
protective breaker before the window ended, and neither able to recover.**

- **Tier 5 froze on the loss streak at 2024-10-20 05:30Z — day 15 of 91** — after five consecutive
  stops on STORJ/USD inside 27 hours. Final: 5 trades, −7.1%.
- **Tier 3 froze on drawdown at 2024-12-19 20:06Z — day 76 of 91** — at 10.07% against the 10%
  limit, after eight consecutive stops. Final: 12 trades, **−8.4%**.
- The cost difference is real and visible (tier 5's friction 0.52–0.64% and hurdle 0.78–0.96%
  against tier 3's 0.67–0.79% and 1.00–1.18%; tier 5 took entries tier 3 refused). **It did not
  decide the outcome.** Both tiers lost, the more expensive tier lost more, and each stopped
  itself by a different limit.

Neither freeze can lift, for the same structural reason (Part III §3).

**4.6 Entries, fills and exposure.** 9 of 13 tier-3 approvals filled, close to the 3-in-4 rate
taken from the rehearsal. Unfilled entries were cancelled by the 300 s window exactly as invariant
8 requires (EWT, OCEAN, STORJ, LCX). Holding times are short: 0.1 h to 3.8 h, median about 0.8 h,
well under the 82 minutes per approval assumed in the timing estimate. Tier 3 has been exposed on
651 ticks of 6,740 — under 10% of the run.

**4.7 Weekly retraining ran ten times with no incident.** Both runs have crossed folds 392→401 on
schedule, switching predictor, calibrators, DI, anomaly and skeptic artefacts per fold. The
rehearsal never tested a fold boundary; the run has now done it twenty times between them.

**4.8 No data-guard block occurred at all.** Tier 3 holds zero `block_records`. That is the
declared consequence of stamping the synthetic quote at `now` (D7): history has no outages, so
`data_guard`'s staleness condition is structurally inert in replay. It is an artefact of the
substitution, not evidence the guard works.

**4.9 Two surprises worth naming.** The first tick of each run blocks at engine 7, because no
equity row exists to size against until engine 19 writes one — one bar lost per run, by design.
And `scout_tallies` stops being written while a run is frozen, because the opportunity chain never
runs: tier 5's funnel therefore describes its first 15 days only, which is why its tally count
(1,461) is a quarter of tier 3's.

## 5. PROJECTED FINAL RESULT — SUPERSEDED BY PART III, KEPT FOR THE RECORD

**This section is superseded. Part III holds the measured results.** It is kept unchanged below
so the projection can be compared with what happened — and it was wrong in an instructive way:
it put the plausible range at −6% to +4% on the assumption that one trade moves equity by about
±2%. The LUNA/USD stop alone took −6.12%, three times that, because a market exit on the next
minute tick does not cap a loss at the stop. **Tier 3 finished at −8.4%, below the bottom of the
range projected here.**

### The projection as written at 16:25, before the last three trades

**Tier 5 is a result, not a projection.** Final: **5 trades, all stops, −354.41, equity 4,645.59,
−7.1%**, frozen from 2024-10-20 05:30Z. Nothing in the remaining ticks can change it.

**Tier 3 below is a PROJECTION, NOT A RESULT. It is replaced with measured figures when the run
finishes.**

At 16:25 tier 3 stands at 9 trades and −1.6% with about four simulated weeks left. Its trades have
arrived at roughly one per 6.5 simulated days, so **1 to 3 more trades** are plausible, for a final
count of **10 to 12** — in line with the pre-registered 8–11. Each closed trade has moved equity by
about 1.4% to 2.6%, so a single trade is worth roughly ±2%.

- **Plausible final range: about −6% to +4%**, centred near flat, dominated by how two or three
  trades land rather than by anything systematic.
- **The promotion bar cannot be cleared** at n ≈ 10–12: §7b fixed the required mean net return per
  trade at 4.9–5.5% for tier 3, which exceeds what a single target exit returns after friction.
  That was pre-registered, and remains the expected outcome of the design.
- **What would change this projection:** a burst of trades in late December (volume falls, so more
  likely fewer), or one unusually large move. December's remaining weeks are the quietest of the
  window by trade count, which argues for the low end of the trade range.

## 6. FUTURE WORK — WHERE THE SYSTEM COULD BE IMPROVED

**Read this warning first. Nothing in this section was changed during the run.** Every item below
was derived after figures existed, and **proposing changes after seeing results is how backtests
get fitted.** These are mechanisms the run exposed, not a reaction to which individual trades
lost; none of them is justified by "trade 5 would have won". **Anything acted on must be declared
in advance of a new run, with its expected effect stated before that run starts**, or the result
is worthless.

**6.1 The breaker has no recovery path.** *Mechanism:* `safety._loss_streak` recounts from trade
history every tick and holds no state, so a cleared freeze re-trips immediately; and in a replay
nothing clears it at all. *Why it matters:* a five-loss run on one pair over 27 hours ended tier
5's participation for 76 of 91 days. Live, the same account would sit frozen until a human noticed.
*Cost to test properly:* record the clear's timestamp and count only losses closed after it —
engine 17 plus the command reader, a gate, and a rehearsal; then a re-run of this window with the
change declared in advance. Roughly half a day.

**6.2 The exit rule realises less than the label.** *Mechanism:* a target exit sells at market on
the next minute tick (F5), so the fill is whatever the book holds a minute later, not the barrier.
*Evidence from the run:* the four target exits realised +1.40%, +2.52%, +2.40% and +2.61% against
the label's +3.0%, a shortfall of 0.4–1.6 pp each. With four wins against five losses at about
−2.2%, that shortfall is the difference between roughly flat and modestly positive. *Option:* a
resting maker limit at the target, which invariant 8 already permits. *Cost:* engine 22 and the
fill simulator, a gate, and a re-run; the maker exit also changes which exits complete at all, so
it cannot be evaluated by repricing.

**6.3 Immediate re-entry into a pair that just stopped out.** *Mechanism:* one position per pair is
enforced, but nothing prevents re-entering the same pair minutes after a stop. *Evidence:* tier 5
took five STORJ/USD entries inside 27 hours, all stopped; tier 3 took three DOGE/USD entries in 24
hours, two of them stops four minutes apart. *Why it plausibly matters:* consecutive entries into
one falling pair are not independent bets, and they are what drove the breaker. *Caution:* this is
the item closest to fitting, because the losing trades suggested it. *Cost:* a per-pair cooldown
after a stop is a change to engine 7's filter or engine 16's composition; it must be pre-declared
with a stated cooldown, not tuned.

**6.4 The cost gate's hurdle and what it refuses.** *Mechanism:* `hurdle_multiple: 1.5` means a
candidate needs an expected move above 2.5× friction, about 1.00% at tier 3. The median refused
candidate offers 0.48%. *Why it matters:* the bar is what makes the system selective, and it is
also why 6,006 of 6,029 examined candidates were refused. Lowering it would multiply trades; the
offline grids say the net stays near zero while the count rises, which is a sample-size gain rather
than an edge. *Cost:* a declared sensitivity run at another multiple, pre-registered, on the same
window. It is one more run of this length per value tested.

**6.5 Spread is the assumption the result is most sensitive to.** *Mechanism:* spread enters
friction, friction sets the hurdle, and the hurdle decides which candidates are examined at all —
so a different spread changes **which trades happen**, not merely what they earn. *Evidence:* §3's
offline comparison found a flat 10 bps inverted the sign of the result against the bucket table.
Spread sensitivity was dropped from this phase (D25), so this run cannot speak to it. *Cost:* the
only sound test is re-running the window at the q25 and q75 spread columns — two more runs of this
length, declared in advance. The post-run repricing script answers a narrower question and must not
be read as the sensitivity.

**6.6 The ranking picks pairs the cost gate will not clear.** *Mechanism:* the universe is ordered
by expected move, and the top of that order is usually an FX or stablecoin pair on the calibrators'
low plateau — EUR/USD and AUD/USD alone topped 2,489 of 6,029 candidate ticks. Every one of those
bars is examined and refused. *Why it matters:* the system is not choosing between plausible
trades; on most bars it has none, and the ranking's job on those bars is only to nominate something
for refusal. A ranking that considered the cost bar would change which candidate is examined —
which invariant 4 permits, since ordering may never approve anything a gate would refuse. *Cost:*
net-margin ranking was rejected on live feasibility (§R.2: 127 order-book calls per bar), so any
version of this must be feasible live before it is simulated.

---

# Part III. Final results of the chain simulation

**Written 2026-09-20 from the runs' own databases, read through snapshot copies.** Every figure
below is measured. Nothing here is a projection.

**BOTH RUNS ARE COMPLETE.** Tier 5 ended 2026-09-20 21:21 local and tier 3 at 00:58 on 2026-09-21,
each having run **all 8,736 bar ticks** to 2025-01-04 00:00Z and written `finished: true`. Every
figure below is final. The watchdog detected each finish by itself and recorded it in the
handover. **Neither run crashed and neither was resumed**, across about 25.8 hours of wall clock.

The figure script was run twice against the finished databases and produced **byte-identical
output on all 26 files**, so the figures in this document reproduce exactly.

## 1. FINAL RESULTS, BOTH RUNS

| | Tier 3 | Tier 5 |
|---|---|---|
| Launched | 2026-09-19 23:12:35 local, commit `19c5a11` | same |
| Window | 2024-10-05 00:15Z to 2025-01-04 00:00Z, folds 392–404 | same |
| Bar ticks run | **8,736 of 8,736, complete** | **8,736 of 8,736, complete** |
| Total ticks (bar + minute) | 9,654 | 8,888 |
| Simulated end reached | **2025-01-04 00:00Z** (trading ended 12-19) | **2025-01-04 00:00Z** |
| Minute ticks (exposure) | 918 | 152 |
| Ticks engine 7 ran | 7,280 | 1,461 |
| Ticks with a candidate | 7,170 | 1,452 |
| Rejections | 7,152 | 1,445 |
| Approvals | 18 | 7 |
| Entries filled / cancelled | 12 / 6 | 5 / 2 |
| **Closed trades** | **12** (4 targets, 8 stops) | **5** (0 targets, 5 stops) |
| **Final equity (from 5,000)** | **4,578.04 = −8.44%** | **4,645.59 = −7.09%** |
| Peak equity reached | 5,143.94 | 5,014.18 |
| **Freeze** | **drawdown, 2024-12-19 20:06Z** (10.07% against the 10% limit) | **loss streak, 2024-10-20 05:30Z** (5 consecutive losses, limit 5) |
| Blocked ticks after the freeze | 1,465 (16.8% of the window) | 7,278 (83.3% of the window) |
| Crashes / resumes | **0 / 0** | **0 / 0** |

**Tier 3's twelve trades, complete and final:**

| # | Pair | Opened (UTC) | Closed (UTC) | Held | Outcome | PnL (USD) | Return |
|---|---|---|---|---|---|---|---|
| 1 | STORJ/USD | 10-20 04:34 | 10-20 05:22 | 0.8 h | stop | −71.03 | −2.13% |
| 2 | STORJ/USD | 10-20 05:49 | 10-20 06:42 | 0.9 h | target | +45.98 | +1.40% |
| 3 | DOGE/USD | 10-20 13:20 | 10-20 17:10 | 3.8 h | target | +83.55 | +2.52% |
| 4 | NEAR/USD | 10-25 23:46 | 10-26 02:47 | 3.0 h | target | +80.98 | +2.40% |
| 5 | DOGE/USD | 11-14 22:31 | 11-14 22:35 | 0.1 h | stop | −75.00 | −2.19% |
| 6 | DOGE/USD | 11-14 22:46 | 11-14 23:00 | 0.2 h | stop | −76.16 | −2.26% |
| 7 | CRV/USD | 11-15 05:17 | 11-15 06:19 | 1.0 h | target | +86.61 | +2.61% |
| 8 | OXT/USD | 11-25 22:33 | 11-25 22:39 | 0.1 h | stop | −80.03 | −2.37% |
| 9 | APT/USD | 12-02 03:47 | 12-02 03:57 | 0.2 h | stop | −74.84 | −2.25% |
| 10 | **LUNA/USD** | 12-09 21:03 | 12-09 21:04 | **0.02 h** | stop | **−200.71** | **−6.12%** |
| 11 | XTZ/USD | 12-18 21:01 | 12-19 01:59 | 5.0 h | stop | −75.26 | −2.39% |
| 12 | SC/USD | 12-19 20:04 | 12-19 20:11 | 0.1 h | stop | −66.05 | −2.14% |

Sum of realised PnL: **−421.96**. The last eight trades were all stops.

**Tier 5's five trades, complete and final:** STORJ/USD only, all stops, all inside 27 hours:
−82.23 (−2.47%), −68.37 (−2.09%), −72.00 (−2.23%), −69.62 (−2.19%), −62.19 (−1.98%). Sum
**−354.41**.

## 2. THE DEADLOCK, AS A CLASS AND NOT AN INCIDENT

**Two independent instances of one defect, found by running the system rather than by reviewing
it.** Both of the account-level limits that can stop trading are computed from stored history on
every tick, hold no state of their own, and have no reference to the freeze that they caused. So
**neither has a recovery path**, and the condition that each needs in order to clear is a
condition that only trading can produce — which the freeze prevents.

**Instance 1 — the loss streak (tier 5).** `engines/safety/engine.py:241`, `_loss_streak`, reads
`store.recent_closed_trades(500)` and counts losses backwards from the most recent closed trade
until a non-losing trade breaks the run. It clears only when a **winning closed trade** becomes
the most recent one. After the freeze no trade can open, so the five losses stay the five most
recent trades for ever. Tier 5 spent **7,278 ticks — 76 of 91 days — blocked**.

**Instance 2 — the drawdown (tier 3).** `_drawdown` in the same engine reads the latest equity
snapshot and its stored `peak_equity` (`clients/store/client.py:358`, `peak_equity`, carried
forward on the row rather than aggregated over the column). The breaker trips while
`(peak − equity) / peak >= 10%`. It clears only when **equity recovers toward the stored peak**,
and equity cannot rise without a winning trade. Tier 3's block records show the arithmetic
standing still: 10.07%, then 10.18%, 10.30%, and 11.00% while both conditions were live.

**The common mechanism, stated for the write-up:** *a circuit breaker whose input is derived from
history, and whose effect is to prevent new history, cannot reset itself.* Both limits are
correct as detectors — five consecutive losses did occur, a 10% drawdown did occur — and both are
incomplete as controls, because the system has no way back. Live, a human would clear the freeze;
in a replay there is no human, and, as §3 of Part II records, clearing it would not help either,
because the same stored history would re-trip the breaker on the next tick.

## 3. EXIT SLIPPAGE, MEASURED

Every closed trade, with the barrier it was aiming at and what it actually realised at exit,
gross of fees. Barrier levels come from the `positions` row written when the trade opened
(`target_price`, `stop_price`); realised is `(exit − entry) / entry`.

| Run | Pair | Outcome | Barrier | Realised | Difference |
|---|---|---|---|---|---|
| t3 | STORJ/USD | stop | −1.50% | −1.54% | −0.04 pp |
| t3 | STORJ/USD | target | +3.00% | +2.01% | **−0.99 pp** |
| t3 | DOGE/USD | target | +3.00% | +3.13% | +0.13 pp |
| t3 | NEAR/USD | target | +3.00% | +3.01% | +0.01 pp |
| t3 | DOGE/USD | stop | −1.50% | −1.60% | −0.10 pp |
| t3 | DOGE/USD | stop | −1.50% | −1.66% | −0.16 pp |
| t3 | CRV/USD | target | +3.00% | +3.22% | +0.22 pp |
| t3 | OXT/USD | stop | −1.50% | −1.78% | −0.28 pp |
| t3 | APT/USD | stop | −1.50% | −1.65% | −0.15 pp |
| t3 | **LUNA/USD** | stop | −1.50% | **−5.54%** | **−4.04 pp** |
| t3 | XTZ/USD | stop | −1.50% | −1.80% | −0.30 pp |
| t3 | SC/USD | stop | −1.50% | −1.54% | −0.04 pp |
| t5 | STORJ/USD | stop | −1.50% | −2.03% | −0.53 pp |
| t5 | STORJ/USD | stop | −1.50% | −1.64% | −0.14 pp |
| t5 | STORJ/USD | stop | −1.50% | −1.79% | −0.29 pp |
| t5 | STORJ/USD | stop | −1.50% | −1.74% | −0.24 pp |
| t5 | STORJ/USD | stop | −1.50% | −1.54% | −0.04 pp |

**Was LUNA the only one? No — and that is the finding.**

- **Every stop overshot. 13 of 13**, in both runs, without exception. Median overshoot **0.16 pp**,
  mean **0.51 pp**, worst **4.04 pp** (LUNA/USD). Excluding LUNA the mean is 0.19 pp.
- **Targets did not systematically fall short.** 4 of 4: one shortfall of 0.99 pp, and three at or
  slightly above the barrier (+0.13, +0.01, +0.22). Mean **−0.16 pp**, median **+0.07 pp**.
- **So the asymmetry is not "both sides slip a little".** F5's earlier note — the target side
  booking +3.0% and realising +2.0% — described **one** trade, the first STORJ target, and is not
  typical of the four. The measured asymmetry is: **the upside is capped at the barrier by
  construction and the downside is not capped at all.** A target exit cannot realise much more
  than +3.0% because the position is sold once the barrier is touched; a stop exit can realise any
  amount below −1.5%, because the market sells at whatever the book holds on the next minute tick.
- **Its cost here:** −4.04 pp on LUNA/USD is −200.71 against the roughly −70 a normal stop costs.
  That single trade took tier 3's drawdown from 4.4% to 8.3% (F2) and is most of the distance to
  the 10% limit that froze it.

## 4. AGAINST THE PRE-REGISTRATION

Everything in this subsection was fixed in §7b **before either run started** and has not been
adjusted since. No statistic, threshold or rule was changed after a figure existed.

| Pre-registered, before any figure | Outcome |
|---|---|
| **The promotion bar** (§R.4, spec 139): a model is promoted only if the lower bound of the Bonferroni-widened interval on net return per trade is above zero, at N = 1,679 trials | Not cleared. Both runs are negative before any interval is computed |
| **The minimum mean net return per trade** that could clear the bar at the expected trade counts: **4.9–5.5% at tier 3**, 1.35–2.14% at tier 5 | Unreachable, as declared. Tier 3 realised **−0.70% mean per trade** measured as realised PnL per trade over the 5,000.00 starting balance (12 trades); as the mean of the trades' own net returns, the definition the promotion module and the bar use, it is **−1.08%**; tier 5 **−2.19%** |
| **Below 10 trades the gate reports no interval**, so tier 3's result is descriptive | Tier 3 closed 12 trades, just above that line; tier 5 closed 5, below it |
| **"Non-promotion is the expected outcome of this design, not a finding about skill"** | Confirmed |
| **Expected trades: 8–11 at tier 3, 27–55 at tier 5** | Tier 3 **12**, just above. Tier 5 **5**, far below — because the breaker stopped it on day 15, a mechanism the estimate did not model |
| **The offline expected-move cells: −0.26% to −0.17% net per trade under honest spread** (§4) | Consistent in sign. The runs' realised means are more negative, and §3 above gives the mechanism the offline grids do not model: stops overshoot, targets do not |

**Stated plainly: the pre-registered expectation was confirmed.** The system did not promote a
model, it was not expected to, and the reason it was not expected to was written down before the
runs began. The result adds two things the pre-registration did not anticipate: **both runs were
stopped early by their own breakers**, and **the realised loss per stop is worse than any offline
grid assumes.**

## 5. THE FUNNEL AND THE COUNTERFACTUAL RECORD

| | Tier 3 | Tier 5 |
|---|---|---|
| Bar ticks run | 8,736 | 8,736 |
| Bar ticks with engine 7 running (not frozen) | 7,280 (83.3%) | 1,461 (16.7%) |
| Ticks where engine 7 published a candidate | 7,170 | 1,452 |
| Refusals, **all by engine 10 `cost`** | 7,152 (`net_edge_below_hurdle` 7,142; `spread_wider_than_move` 10) | 1,445 (all `net_edge_below_hurdle`) |
| Approvals | 18 | 7 |
| Entry orders filled | 12 | 5 |
| `block_records` after the freeze | 1,465 | 7,278 |
| `rejections` rows carrying `details` (every gate's verdict) | 7,152 of 7,152 | 1,445 of 1,445 |
| `rejections` rows carrying a `shap_ref` | 7,152 of 7,152 | 1,445 of 1,445 |
| SHAP files written | 7,170 | 1,452 |
| `scout_tallies` rows | 7,280 | 1,461 |
| `equity_snapshots` rows | 9,653 | 8,887 |

**What this dataset contains, and what can be asked of it.** For every decision bar: the universe
engine 7 scanned (1,450 pairs), how many entered and why each was excluded, the full ranked list
with each pair's expected move as an exact decimal, the candidate chosen, and the gate verdicts on
it — on **both** sides, refusal and approval. For every refusal: the expected move, friction, net
edge and hurdle, plus a SHAP file naming the features behind that prediction. For every tick: the
account's equity, cash and open positions. For every blocked tick: which breaker, with the
arithmetic in its message.

So the dataset answers, without re-running anything: what the system examined and refused and by
how much; how the refusal margin moved with fees between the two tiers; which pairs dominated the
ranking; what the model said about each refused candidate; how the account evolved tick by tick;
and exactly when and why trading stopped. **What it cannot answer:** how often the later gates
would have refused — the cost gate stops the chain first, so anomaly, risk, skeptic and decision
recorded no refusal in either run — and anything about a different spread, since spread is an
input the run declares rather than measures.

## 6. FIGURES

Eight figures, regenerated by one committed script:
`docs/dataset/phase-7-figures/make_phase7_figures.py`, run with the separate figures venv (its
docstring gives the two commands that create it). Each figure is written as **vector PDF** and
**300 dpi PNG**, beside **the CSV it was plotted from**, so every number is checkable.
`captions.tex` holds the captions ready to paste. The script reads the runs through SQLite's
backup API, never locking or writing to them, plots measured data only, and distinguishes series
by line style, marker and hatch so the figures survive greyscale printing.

| Figure | Shows |
|---|---|
| **F1** `F1_equity_curves` | Both equity curves over the window, trade closes marked, each freeze marked with date and trigger |
| **F2** `F2_tier3_drawdown` | Tier 3's drawdown against its stored peak, the 10% limit, the LUNA stop, and the crossing on 2024-12-19 20:05Z |
| **F3** `F3_per_trade_pnl` | Per-trade PnL in time order, hatched by outcome, LUNA labelled |
| **F4** `F4_barrier_vs_realised` | Realised return against the barrier aimed at, with the 45° line: every stop below it, targets on or near it |
| **F5** `F5_decision_funnel` | The funnel for both runs, from bar ticks run to trades closed, log scale |
| **F6** `F6_rejections_over_time` | Refusals per simulated week by gate and reason; gaps are frozen weeks |
| **F7** `F7_trading_vs_frozen` | When each run could trade, with the frozen remainder shaded |
| **F8** `F8_engine_chain` | The chain as it ran, gates marked, where a refusal stops it, and what engine 19 records. Mermaid source committed as `F8_engine_chain.mmd`; the rendered figure is drawn by the script so it reproduces offline |

**Every figure requested was produced from stored data.** One note on F8: it is drawn by the
script rather than rendered from the Mermaid source, because rendering Mermaid needs a toolchain
this machine does not have; the `.mmd` source is committed beside it and produces the same
structure.

## 7. FUTURE WORK

**The warning first. Nothing in this section was changed during the runs.** Every item was
identified after figures existed, and **proposing changes after seeing results is how backtests
get fitted.** These are mechanisms, not reactions to which trades lost. **Anything acted on must
be declared in advance of a new run, with its expected effect written down before that run
starts.**

**7.1 Neither breaker can recover (Part III §2).** *Mechanism:* both limits recompute from stored
history every tick, hold no state, and block the trading that alone could clear them. *Why it
matters:* it ended tier 5 on day 15 and tier 3 on day 76, so 76% and 16% of the respective windows
produced no decision at all; live, an account would sit frozen until a human intervened.
*To test properly:* record the clear's timestamp and count only history after it (loss streak),
and re-base the peak on the clear (drawdown). Engine 17 plus the command reader, a gate, a
rehearsal, and a re-run of this window with the change declared in advance. Roughly a day.

**7.2 Exit slippage is asymmetric (Part III §3).** *Mechanism:* both barriers exit at market on
the next minute tick, which caps the gain at the target and leaves the loss uncapped. Measured: 13
of 13 stops overshot, mean 0.51 pp, worst 4.04 pp. *Options:* a resting maker limit at the target
(invariant 8 already permits it), and an intra-minute stop that acts on the trade range rather
than at the next tick. *Why it matters:* the mean overshoot is roughly a quarter of a typical
stop's cost, and the tail (LUNA) is what froze tier 3. *To test properly:* engine 22 and the fill
simulator, a gate, and a re-run — repricing cannot answer it, because a different exit rule
changes which positions are still open later.

**7.3 Repeated entries into a pair that just stopped out.** *Mechanism:* one position per pair is
enforced, but nothing stops an immediate re-entry. Tier 5 took **five STORJ/USD entries inside 27
hours**, all stopped; tier 3 took three DOGE/USD entries in 24 hours, two stopping four minutes
apart. *Why it matters:* consecutive entries into one falling pair are not independent bets, and
they are what tripped both breakers. *Caution:* this is the item closest to fitting, because the
losing trades suggested it. *To test properly:* a per-pair cooldown after a stop, in engine 7's
filter, with the cooldown declared in advance rather than tuned.

**7.4 The cost gate's hurdle.** *Mechanism:* `hurdle_multiple: 1.5` sets the bar at 2.5× friction,
about 1.00% at tier 3. The median refused candidate offered 0.48%, a median shortfall of 1.22 pp,
and 7,152 of 7,170 examined candidates were refused. *Why it matters:* it is what makes the system
selective, and it is also why three months produced twelve trades. Lowering it multiplies trades;
the offline grids say the net stays near zero as the count rises. *To test properly:* a declared
sensitivity run at another multiple — one more run of this length per value.

**7.5 Spread, the assumption that inverted the sign offline.** *Mechanism:* spread enters
friction, friction sets the hurdle, and the hurdle decides which candidates are examined — so a
different spread changes **which trades happen**, not just what they earn. §3's offline comparison
found a flat 10 bps inverted the sign of the result against the bucket table. *Why it matters:*
it is the single input this result is most sensitive to, and the runs declare it rather than
measure it. *To test properly:* re-run the window at the q25 and q75 spread columns — two further
runs, declared in advance. The post-run repricing script answers a narrower question and must not
be presented as the sensitivity.
