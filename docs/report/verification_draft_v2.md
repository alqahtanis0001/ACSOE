# Draft v2 — verification against the committed repository

Read at `4316940` (`main`), 2026-09-21. Databases: `data/db/phase7-t3-expected_move.sqlite` (tier 3) and
`data/db/phase7-t5-expected_move.sqlite` (tier 5), opened read-only. Nothing in the report was edited.
The scripts that produced every figure below are in the session scratchpad (`verify_ch6.py`,
`label_refusals.py`); every query is quoted inline so it can be re-run without them.

## 1. The tier 3 mean net return per trade: −0.70% against −1.08%

Both figures are arithmetic on the same twelve rows; they differ in the denominator.

| Figure | Where | Definition | Value from the database |
|---|---|---|---|
| **−0.70%** | `docs/dataset/phase-7-findings.md:1309` ("Tier 3 realised −0.70% mean per trade (12 trades)") | No derivation is given. It is the sum of realised PnL divided by the trade count and by the **starting account balance**: −421.96 / 12 / 5,000 = −0.7033%. Equivalently, the −8.44% equity return divided by 12. | `SELECT sum(realised_pnl)/count(*)/5000 FROM trades` → −0.7033% |
| **−1.08%** | `src/acsoe/engines/tournament/engine.py:700–725` (`_holds`: `net_return = realised_pnl / (qty × entry_price)`) and `src/acsoe/modelling/promotion.py:414` (`mean = fsum(returns) / n`) | The arithmetic mean of each trade's net return on its **own entry notional**. The stored column `trades.realised_pnl_pct` holds the same ratio on all seventeen rows (asserted to 1e-12). | `SELECT avg(realised_pnl_pct) FROM trades` → −1.0766%; `promotion_verdict(holds, 1679)` → mean −1.0766% |

The findings row is internally inconsistent: its tier 5 figure in the same cell, −2.19%, is the *per-trade* mean
(the same-definition figure as −0.70% would be −354.41 / 5 / 5,000 = −1.42%). The pre-registered bar
(`q × SD / √n`, findings §7b) is stated in per-trade units, so the committed module's −1.08% is the figure the
bar is compared against. The report's usage — "−1.08%, computed by the committed acceptance module" — is
correct. Every other Table 6.10 figure reproduces from the module: overlap lag 0, HAC standard error 0.7446%,
Bonferroni quantile 6.7939 (11 df), lower bound −6.1357%, deflated Sharpe 0.0000; tier 5: too few trades,
mean −2.1918%.

*Suggested correction to the findings file (not made):* "Tier 3 realised −1.08% mean net return per trade
(12 trades; −0.70% of the starting balance per trade); tier 5 −2.19%".

## 2. Chapter 6 against the databases

Note on numbering: in the PDF the heading "The simulation at tier 3" is rendered as the literal text
"## The simulation at tier 3" inside the caption of Table 6.6, so that section has no number and every
section after it is numbered one lower than the cross-references assume (Table 6.11 FR10 cites "Section 6.8"
for the deadlock finding, printed as 6.7; Table 6.12 EQ4 cites "Section 6.9; Table 6.10" for acceptance,
printed as 6.8). Below, sections are named by their printed number and their subject.

### Discrepancies

| Section | Sentence | What the database says | Query |
|---|---|---|---|
| 6.7 Two findings, second paragraph | "every stop overshot, 13 of 13 in both runs, by a median of 0.16 and a **mean of 0.51** percentage points" | 13 of 13 overshot; median **0.163 pp**; **mean 0.488 pp** (0.49). The same 0.51 is in `phase-7-findings.md` §3, so the source document carries it too. | per stop: `(exit_price/entry_price − 1) − (stop_price/entry_price − 1)` from `trades JOIN positions USING (position_id)`, both databases; median and mean of the 13 differences |
| 6.8 Acceptance, and Table 6.10 "Bitcoin held over the window" | "Bitcoin held over the window rose **58.2%**" / "+58.2%" | **+58.0%**: last XBT/USD trade at or before the first tick (2024-10-05 00:15Z) 62,090.2 → last trade at or before the last tick (2025-01-03 23:45Z, or 00:00Z) 98,111.1 = +58.01%; from the 00:00 tick, +58.04%. The 15-minute archive gives the same. The evidence pack's daily-close figure is +58.10%. Nothing in the repository yields 58.2. "About 7,900" (Section 6.5) holds under every convention (7,901–7,905). | `data/derived/trades_weekly/XBTUSD/2024-10-05.parquet` and `2024-12-28.parquet`: `price` of the last row with `ts ≤ tick`; `data/historical/XBTUSD_15.csv` closes at the same instants |
| 6.6 Tier 5 | "For 76 days the run then recorded market data and **7,278 blocked bars**" | **7,274 bar ticks** were blocked by the breaker after the freeze (7,275 counting the 05:30 tick on which it fired). 7,278 is the number of *block-record rows*: the terminal 2025-01-04 00:00 tick carries four rows (safety, plus `exchange` and `market_sensor` errors and a `data_guard` block, because the replay has no partition for that instant). The 76 days holds (75.76). | `SELECT count(DISTINCT cycle_id) FROM block_records WHERE ts > freeze AND (ts/1000000) % 900 = 0` → 7,274; `SELECT count(*) FROM block_records` → 7,278; freeze from `commands WHERE command='freeze'` |
| Figure 6.5 (cited in 6.6) | Panel title "tier 3: 12 trades, 15.2 h exposed of **1876 h** simulated (**0.8%**)" | The committed, regenerated figure `docs/dataset/phase-7-figures/F7_trading_vs_frozen.png` and its CSV read **2184 h (0.7%)**; both runs span 2,183.5 h (first tick 2024-10-05 00:15Z to last equity row 2025-01-03 23:45Z). The PDF embeds a render made before the tier 3 run had finished. Tier 5's panel (2.3 h of 2184 h) is current. | `F7_trading_vs_frozen.csv` TOTAL rows; `max(equity_snapshots.ts) − min(scout_tallies.ts)` |
| 6.5 Tier 3 paragraph | "On 19 December at 20:06 UTC the drawdown from the stored peak reached 10.07% … and the circuit breaker froze the account" | The equity row that first shows a 10.07% drawdown is stamped **20:05:00Z**; the breaker's block record and the freeze command are stamped **20:06:00Z** (the next tick, which read it). Figure 6.4's label says "limit crossed 2024-12-19 20:05Z". Not a numeric error; the sentence conflates the reading and the action by one minute. | `SELECT ts FROM equity_snapshots WHERE equity <= 0.9*peak_equity ORDER BY ts LIMIT 1`; `SELECT created_at FROM commands WHERE command='freeze'` |
| 6.6 Tier 5 | "on **day fifteen** of ninety one" | 15.22 days had elapsed from the first tick; the freeze falls on the sixteenth calendar day if 5 October is day one. The findings document uses the same convention ("day 15"). | `freeze − min(scout_tallies.ts)` = 15.22 d |
| 6.7 Two findings, second paragraph | "cost 200.71 against the **roughly 70** a normal stop costs" | Tier 3's seven other stops average **74.05**; tier 5's five stops average 70.88. | `SELECT avg(abs(realised_pnl)) FROM trades WHERE outcome='stop' AND pair<>'LUNA/USD'` |

### Confirmed, with the query

Tier 3 (Section 6.5 tail, Table 6.7): 7,170 bars with a candidate (`scout_tallies WHERE candidate IS NOT NULL`);
7,152 refusals, all `rejected_by='cost'`, 7,142 `net_edge_below_hurdle` + 10 `spread_wider_than_move`;
median refused expected move 0.476% against median bar 1.004%; 18 approvals; entry orders 12 filled, 6 cancelled;
trades 4 target / 8 stop / 0 timeout; last eight all stops (entry order); peak 5,143.94, end 4,578.04 = −8.44%;
freeze `safety: drawdown` 2024-12-19 20:06Z; no refusal, approval or scout row after the freeze. Every row of
Table 6.7 — pair, entry time, hold, outcome, PnL, net return — matches `trades` to the printed precision
(e.g. CRV/USD 15 Nov 05:17, 62 min, +86.61, +2.61%); sum −421.96; mean −1.08%.

Tier 5 (Section 6.6, Table 6.8): 1,452 candidates, 1,445 refused, all cost, all `net_edge_below_hurdle`; 7 approvals,
5 filled, 2 cancelled; entries 19 Oct 08:31, 09:03, 10:18, 11:31 (closed 11:45) and 20 Oct 04:34 (closed 05:22);
the 04:30Z bar of 20 Oct is the only (bar, pair) approved in both runs (`approvals(ts, pair)` intersected);
freeze `safety: loss_streak` 2024-10-20 05:30Z; end 4,645.59 = −7.09%; peak 5,014.18; all five rows of
Table 6.8; sum −354.41; mean −2.19%.

Section 6.7 (Two findings) and Table 6.9: distinct safety block reasons at tier 3 are exactly 10.07%, 10.18%,
10.30% and 11.00% (`SELECT DISTINCT block_reason FROM block_records WHERE blocked_by='safety'`); all 17 rows
of Table 6.9 (barrier from `positions.target_price` / `stop_price`, realised from `exit_price/entry_price − 1`);
worst −4.04 pp LUNA/USD; targets +0.13, +0.01, +0.22 and −0.99; LUNA took the drawdown from 4.35% (21:02Z row)
to 8.25% (21:04Z row).

Section 6.8 / Table 6.10: every module figure (above); expected trades 8–11 / 27–55 and required means
4.9–5.5% / 1.35–2.14% agree with `phase-7-findings.md` §7b (a document, not a database, figure); end and peak
equity; freeze times.

Section 6.9 / Table 6.11: FR2 7,280 `scout_tallies` rows at tier 3; FR5 8,597 = 7,152 + 1,445 refusals, none
missing any of the four cost figures; FR6 entry notionals 3,091.79–3,424.42 (tier 3) and 3,136.76–3,329.18
(tier 5) around 3,333; FR8 six and two cancelled entries; FR9 seventeen exits, every one target or stop;
FR11 all 7,152 (and all 1,445) refusals carry `details.engines` with the six examining components
(scout, prediction, order_book, regime, anomaly, cost), a `shap_ref`, and the referenced attribution file
exists under `data/derived/`; every approval's `details.engines.decision.checked` lists all seven checks.
Table 6.12: 8,597 refusals and 25 approvals; "twelve times over 76 days" = 75.83 days first tick to freeze.

Not database-verifiable (out of scope, noted only): FR4's 3.3% / 1.2% refusal rates and Section 6.4's
walk-forward statistics come from the fold digests; Table 6.10's pre-registered rows come from the findings
document.

## 3. Console screenshot — `docs/report/figures/fig5_5_console.png`

Taken 2026-09-21 with headless Microsoft Edge (viewport 1440×1200 at 2× device scale = 2880×2400, content
only, no browser chrome) against a **copy** of the tier 3 database made with SQLite's backup API into a scratch
directory; the live files were opened read-only and not touched. In the copy the run identifier was rewritten
to `replay-tier3-expected_move-20241005T001500Z` in every table (the console does not render the run
identifier on any pane, but the copy carries no build-phase name anywhere: a `LIKE '%phase%'` scan over every
text column returns nothing). The console was served by its own factory (`create_app(config, db_path=…,
clock=…)`) with the clock pinned to 2025-01-03 23:46:30Z, 90 s after the last equity row, so the band's
staleness reads against the replayed instant rather than against 2026 (with the system clock it read
"625d 02h" and faded the balance). The config was `config/default.yaml` with `mode: replay`.

Three things to know before using it:

- **There is no light mode.** The console has one palette — the "cool slate ground" of
  `context/ui-context.md` and `console/static/tokens.css` — and no theme switch, so the screenshot is in the
  console's only theme.
- **The balance renders at full stored precision** ("4578.035500852170510190512713 USD"). That is
  `console/format.py:663` `format_money` by design ("a money value at exactly the precision it was stored
  at, no quantizing"); the replay stores 28-digit decimals. It is what the console shows.
- **"60 entrys"** in the feed's count is a pluralisation defect in the console.

The delivered file is the **History** tab: the status band, the twelve closed trades (newest first, with
quantity, entry, exit, result and change) and the head of the refused-candidates record with the four cost
figures per refusal. The Live tab at the end of this run shows only the frozen tail (the safety block repeated
every bar and the terminal replay error on the 00:00 tick); that capture is in the session scratchpad
(`shot_live_alternate.png`) if preferred. Neither view carries build vocabulary; the Research tab's
empty-state text does, so it must not be used.

## 4. Statement coverage per package — `docs/report/data/coverage_by_package.csv`

One full run, `pytest tests --cov=acsoe` (pytest 9.1.1, coverage 7.16.1), 2026-09-21, 52 min 38 s:
**3,925 passed, 1 failed, 2 skipped** of 3,928. The failure, `tests/verify/test_runner.py::
test_each_phase_registers_its_own_criteria_and_no_others`, is not a defect in the suite: `scripts/verify.py`
and that test file were being edited in the working tree by another session while the run was in progress
(both show as modified in `git status` and were clean at the start), and the test passes on its own against
the tree as it now stands. Coverage is over `src/acsoe/` only (139 files); the tests that copy the source
tree into temporary directories were excluded from the aggregation. Packages are the first directory under
`src/acsoe/`, with `engines/` and `clients/` split one level further; "lines" are statements.

| Package | Coverage | Statements covered / total |
|---|---|---|
| top-level modules (`bootstrap.py`, `__init__.py`) | 100.0% | 31 / 31 |
| cli | 93.0% | 411 / 442 |
| clients/kraken | 93.5% | 1,460 / 1,561 |
| clients/paper | 96.5% | 275 / 285 |
| clients/recorder | 92.8% | 218 / 235 |
| clients/store | 98.4% | 1,311 / 1,332 |
| console | 97.1% | 594 / 612 |
| core | 95.9% | 302 / 315 |
| engines/adaptive_router | 95.1% | 135 / 142 |
| engines/anomaly | 94.3% | 132 / 140 |
| engines/cost | 94.9% | 130 / 137 |
| engines/data_guard | 92.7% | 102 / 110 |
| engines/decision | 99.4% | 162 / 163 |
| engines/exchange | 97.7% | 85 / 87 |
| engines/execution | 94.0% | 141 / 150 |
| engines/exit | 95.3% | 245 / 257 |
| engines/feature | 98.3% | 116 / 118 |
| engines/macro_context | 100.0% | 68 / 68 |
| engines/market_data_recorder | 94.0% | 110 / 117 |
| engines/market_sensor | 91.9% | 227 / 247 |
| engines/memory | 96.6% | 368 / 381 |
| engines/order_book | 95.1% | 173 / 182 |
| engines/position_manager | 94.3% | 282 / 299 |
| engines/prediction | 93.6% | 218 / 233 |
| engines/regime | 100.0% | 79 / 79 |
| engines/risk | 93.9% | 184 / 196 |
| engines/safety | 97.6% | 204 / 209 |
| engines/scout | 93.3% | 374 / 401 |
| engines/skeptic | 92.7% | 165 / 178 |
| engines/tournament | 94.1% | 272 / 289 |
| modelling | 92.6% | 860 / 929 |
| platform | 97.9% | 605 / 618 |
| research | 93.1% | 2,591 / 2,784 |
| **Total** | **94.8%** | **12,630 / 13,327** |

## 5. Refused candidates labelled with the triple-barrier outcome — `docs/report/data/refused_candidates_labelled.csv`

Rule: `src/acsoe/research/labelling.py` `label_candles`, unchanged, with the committed barriers
(`config/default.yaml`: target +3.0%, stop −1.5%, timeout 48 bars = 12 h), over the 15-minute archive in
`data/historical/` (BTC/USD → `XBTUSD_15.csv`, DOGE/USD → `XDGUSD_15.csv`, otherwise the pair without its
slash). The decision bar is `scout_tallies.closed_bar_ts` joined on `(run_id, cycle_id)`, which is the tick
minus 900 s for every refusal (asserted). The reference price is the archive candle's close, as in the rule —
not the engine's quoted price. A bar touching both barriers in one candle is `stop` and flagged `ambiguous`.

| | Tier 3 | Tier 5 |
|---|---|---|
| Refused candidates | 7,152 | 1,445 |
| **target** | 715 (10.0%) | 40 (2.8%) |
| **stop** | 1,033 (14.4%) | 61 (4.2%) |
| — of which ambiguous (both barriers in one bar) | 18 | 3 |
| **timeout** | 5,251 (73.4%) | 1,321 (91.4%) |
| unlabelled: no archive candle at the decision bar (no trade printed in that 15 minutes) | 153 (2.1%) | 23 (1.6%) |

Of the labelled refusals, targets were 10.2% at tier 3 and 2.8% at tier 5. The CSV has one row per refusal:
run, rejection id, cycle, tick, decision bar, pair, refusing check and reason, expected move, bar, label,
ambiguous flag, bars to the touch, touch time, return at the label, candles in the window, note.
