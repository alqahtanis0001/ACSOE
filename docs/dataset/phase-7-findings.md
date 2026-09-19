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

Written 2026-09-19, at `f0e7514` plus this document. Scripts and their raw outputs are in
`docs/dataset/phase-7-recon-2026-09-19/` (`scripts/` and `outputs/`). Where an output was only
printed to a terminal, it is transcribed verbatim in `outputs/transcribed-terminal-outputs.txt`,
cited below as **[T]**.

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
is round-trip fees plus spread plus slippage. **Tier 3's fees** are invariant 5's *reference*
figures, maker 0.22% and taker 0.38% (0.60% round trip). The invariant marks those as
sanity-check values; see §7 for what a sourced schedule changes.

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
| 0.45% | 197 | 87 | +0.34% ± 0.46% | tier 5 (operator-stated) |
| 0.50% | 128 | 55 | +0.26% ± 0.59% | |
| 0.55% | 98 | 43 | +0.23% ± 0.67% | tier 4 (operator-stated) |
| 0.60% | 74 | 34 | +0.18% ± 0.75% | tier 3 (invariant 5 reference) |
| 0.65% | 44 | NOT MEASURED | — | |
| 0.70% | 29 | 12 | −0.05% ± 1.29% | |
| 0.85% | 10 | 6 | −0.10% (interval not meaningful) | |
| 0.90% | 2 | NOT MEASURED | — | |
| 0.95% | 1 | NOT MEASURED | — | |
| 1.00% and above | 0 | 0 | — | |
| 1.20% | 0 | 0 | — | tier 1 (invariant 5 reference) |

**The tier marks are fee-only.** A tier's round-trip fee sits at its mark, and its real friction
sits to the right of it by the spread and slippage the pair pays. **The tier-4 (0.55%) and tier-5
(0.45%) fees are the operator's figures of 2026-09-19. Nothing on disk yet sources them.** They are
to be confirmed against the schedule fixture before the chapter cites them as Kraken's.

**SIMULATED VALUE PENDING:** the chain's trade count and net per trade at each simulated tier.

### Tier 1 is provably zero. FINAL.

At tier 1's reference fees (0.40% + 0.80% = 1.20%), the cost bar is 2.5 × 1.20% = **3.0%** before
any spread or slippage, and spread and slippage only raise it. The expected move is

`p_target × 3.0% − p_stop × 1.5% + p_timeout × m`,

where `m` is the fold's mean timeout return. The calibrated probabilities are renormalised to sum
to one (`modelling/calibration.py`, `apply_calibration`), and `m` lies between 0.17% and 0.54% in
all 405 fold manifests. So the expected move is a weighted average of 3.0%, −1.5% and `m`, and can
never exceed 3.0%. The gate needs it to be **strictly greater** than 3.0%, so no candidate at tier 1
can clear, whatever the market does. The model's observed maximum agrees: over all 15,978,803
out-of-sample rows the highest expected move is **2.9999999930%** (`outputs/2026-09-18_q_em.log`).

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

Neither of the last two is available to engine 7 as the contracts stand. Engine 7 runs before
engine 8, and invariant 4 describes its ranking as "a deterministic score over features" with no
model in it. These columns describe a system the operator has not ruled.

**The finding: the ranking changes how many trades are taken, not what each trade earns.** Across
the three rankings other than alphabetical, wherever there are enough trades for an interval, every net per
trade lies between −0.32% and +0.06%, and every interval includes zero. Alphabetical ordering
yields too few trades to say anything about its return. Its point estimates are worse, but they
rest on one to twelve trades on two pairs.

**SIMULATED VALUE PENDING:** the ruled ranking's chain trade count, pair count and net per trade.

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

**Whether the most confident calls are the most overconfident is NOT MEASURED.** That would need
the realised return by expected-move decile, or a calibration curve of expected move against
realised return, and neither was computed. The measured statement is narrower: the calls above the
bar realise far less than the bar.

**SIMULATED VALUE PENDING:** the chain trades' mean expected move at entry beside their realised
return. That comparison needs the approval record Phase 7 prerequisite 7 adds.

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
| **Fees for the period.** No `TradeVolume` response was ever recorded, and nothing on disk dates any Kraken fee schedule. | A schedule the operator supplies with its URL and date, as a scenario fixture read only in replay mode (invariant 2 amendment). | A current schedule is applied to a 2023–24 window. At tier 3 the difference between 0.60% and 0.40% of fees is the difference between 3 trades and 58 (§4), so the result is more sensitive to this input than to any other. |
| **Entry fills.** Every offline figure assumes the trade was entered at the bar's close. | The paper broker's pessimistic rule: a post-only buy fills only on a trade strictly below its limit, from the time-and-sales. | The offline counts are upper bounds on fills. Fills that do happen are selected towards falling markets (adverse selection). |
| **Complete features.** 50.2% of out-of-sample rows carry an unfilled lookback (Phase 5, Finding 3). | Nothing: engines 13 and 8 refuse them, correctly. | The surviving population is the more liquid half, and 62% of window bars are refused before a prediction (§1b). |
| **2025.** The walk-forward died at fold 405. | Nothing. | No test week after 2025-01-03. |
| **Choosing configurations on the same data.** The grids above were searched on the out-of-sample file, and the ranking study behind `log_return_4` used it too. | Nothing can repair this after the fact. | The ranking, spread form and fee tier must be justified on grounds other than these tables. The multiple-testing haircut of Phase 7's deflated metric should count every cell searched here. |

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
| §2 | The chain's trade count and net per trade at each simulated tier |
| §3 | The bucket arm's chain figures |
| §4 | The ruled ranking's chain trade count, pairs and net |
| §6 | The chain trades' expected move at entry against realised return |
| New | The equity curve including cash periods; alpha against the buy-and-hold benchmark; the per-trade reasons for approval (prerequisite 7) |

## 10. Findings the simulation will not change

- **The tier-1 arithmetic (§2).** The cost bar exceeds the largest expected move the model can
  produce.
- **The spread inversion (§3).** A constant spread made thin-pair trades look profitable; a
  liquidity-dependent spread removed the gain.
- **Alphabetical ordering's concentration (§4).** One pair on 56% of bars.
- **The capped against uncapped skeptic (§5a)**, and the 2026-09-14 sweep for the skeptic it
  measured (§5b).
- **The overconfidence of cost-clearing calls over the full span (§6).** +0.32% realised against at
  least 1.50% expected.
