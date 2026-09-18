# The first paper trade, read from the database

**Lead, 2026-09-18, for the operator (Q4 of `overnight-decisions-2026-09-18.md`, ruled: "the
database walk-through").** One complete trade, in plain prose, with every number read from the
rows engine 19 wrote. Where a number is **not** in the database, that is said at the point it is
used, and where it came from instead.

## What this trade is, before any number is believed

- **It is the committed criterion's own trade.** `paper_trade_round_trip_target` drives it in every
  Phase 6 gate. The walk-through ran that criterion's code unchanged, keeping the SQLite file it
  normally deletes (method: decision D3 of `overnight-decisions-2026-09-18-night.md`). Its PASS
  message was identical, digit for digit, to tonight's gate line.
- **The market is scripted, not recorded.** The harness plants one constructed candle series on
  BTC/USD, ETH/USD and SOL/USD alike and pins every bid at 126.925. **"BTC/USD at 126.9" is not a
  Bitcoin price**; the timestamps (17 May 2024) are where the constructed series happens to sit.
- **The models were trained inside the drive**, on that constructed series, into a temporary
  directory. They are the subject a criterion needs, not a model anyone should read skill into.
- **The fees are the fake exchange's tier 3**: maker 0.0011, taker 0.0019. They are invented test
  data (`tests/fixtures/kraken/fee_tiers.json` says so in its own comment), and they are **not**
  the invariant's reference tier 3 of 0.22% / 0.38%. See S3 in tonight's decision list: the
  sentence every Phase 6 criterion appends ("reference friction about 0.65% … hurdle of 1.625%")
  does not describe this run, whose friction was 0.308% and hurdle 0.462%.
- **Paper mode**, opening balance 5000.00 USD (`paper.starting_balances`), run id
  `verify-phase-6-drive`.

So this walk-through shows **the machinery** doing exactly what the rows say it did. It shows
nothing about whether a trade like this would make money.

## What the database does and does not hold

The database holds **ten tables**. For this run `runs` has 1 row, `commands` 1, `orders` 2,
`positions` 1, `trades` 1, `equity_snapshots` 8, and `rejections`, `block_records` and
`leaderboard` hold **none**.

**The database holds no record of why this trade was taken.** Nothing was refused, so
`rejections` is empty, and that is the only table with columns for expected move, friction, net
edge and hurdle. Nothing was blocked, so `block_records` is empty. `trades` carries the outcome and
the money but **no column for any gate's verdict or for the economics that approved the entry**,
and no decision or SHAP row is written for an approval. **The candidate and the gate verdicts
below are therefore read from the engines' published payloads on the entry tick, kept in the
drive's process, not from the database.** Each figure from there is marked *(state)*. This is a
finding in its own right (F-new-1 in tonight's list): an approved trade's reasons live in `state`
for one tick and then are gone.

## The ticks

One tick per minute. The drive runs eight of them (one more than the criterion, to show the equity
row after the exit):

| Cycle | Time (UTC) | What happened |
|---|---|---|
| 1 | 2024-05-17 21:59:01 | Quiet tick before the bar closes; writes the first equity row |
| 2 | 22:00:01 | A 15-minute bar closed. The opportunity chain ran and **the entry was placed** |
| 3 | 22:01:01 | **The entry filled**; the position opened |
| 4, 5, 6 | 22:02:01 – 22:04:01 | The watch: marked each minute, nothing triggered |
| 7 | 22:05:01 | A trade crossed the target the minute before; **the exit** |
| 8 | 22:06:01 | The tick after: flat, cash only |

The one command in the store is the `activate` the drive wrote (source `console`, reason
`verify.py spec 100`), claimed and consumed at 21:59:01 by run `verify-phase-6-drive`. `runs`
records `system_mode` `running` from that moment.

## The candidate, and why that pair *(state)*

Engine 7 `scout`, on the bar-close tick (cycle 2), scanned **4** pairs and let **3** into the
tradable universe: BTC/USD, ETH/USD and SOL/USD. The fourth, ETH/BTC, was excluded with
`no_live_quote`, because the scripted market publishes no quote for it (it is crypto-quoted and
disabled by invariant 7 in any case).

**Why BTC/USD: alphabetical order.** `scout.rank_feature` is `null`, so engine 7 does not rank by
any feature. It keeps the universe in its sorted order until the operator rules on spec 75's
ranking study, and BTC/USD is first. The three pairs carry identical candles and identical quotes
here, so no pair *could* have been preferred on its merits. That is the honest answer, and it is a
recorded absence, not a choice.

## Each gate's verdict, in the order the chain ran them *(state)*

The chain on cycle 2 was the guard chain (1, 2, 3, 4, 17), then the opportunity chain (5, 6, 7,
12, 13, 8, 9, 10, 11, 14, 15, 16, 18). The eight gates, in the order they ran:

**A passing gate has no reason string.** `engine-contracts.md` rule 6 makes a reason mandatory only
when an engine blocks, so every gate below published `reason_code: null`. What each gate decided
on is given instead.

1. **Engine 4 `data_guard` — pass.** `blocked: false`, no findings. Oldest quote 0.0 s old against
   `max_data_age_s` 120.0; 3 pairs seen; 0 missing bars.
2. **Engine 17 `safety` — pass.** `action: none`, nothing tripped. Drawdown 0 (equity 5000.00,
   peak 5000.00); 0 consecutive losses; 0 errors in the window; 0 open positions; 0 resting
   entries; 0 consecutive data blocks.
3. **Engine 7 `scout` — pass.** The universe above; candidate BTC/USD.
4. **Engine 13 `anomaly` — pass.** Score 0.4949463747723813 against threshold 0.603100400911309,
   `anomalous: false`, model `train-20260913T120000-8b12f900-f3`.
5. **Engine 10 `cost` — pass.** Expected move 0.029999999932724522 (engine 8's, 3.0%). Friction
   0.003078783581501615063420783109: maker 0.0011, plus taker 0.0019, plus measured spread
   0.0000787835815…, plus estimated slippage 0 (engine 9 walked one book level of the pinned book).
   Net edge 0.02692121635122290693657921689 against a hurdle of 0.004618175372252422595131174664
   (1.5 × friction). `clears_hurdle: true`.
6. **Engine 11 `risk` — pass.** `approved: true`. Risk amount 50.0000 (1% of 5000.00 equity).
   Notional 3333.33333216965 = that risk ÷ the 1.5% stop, **sized at the ask 126.935**, giving
   quantity 26.26015939 rounded down to 8 lot decimals. The pair's `ordermin` is 0.00005 and its
   `costmin` 5.00; the value at the bid is 3333.07073057575.
7. **Engine 15 `skeptic` — pass.** P(wrong) 0.000007844180605057358 against the veto threshold
   0.5, `vetoed: false`.
8. **Engine 16 `decision` — pass.** `coherent: true`. It checked that scout, prediction,
   order_book, cost, risk, adaptive_router and skeptic all judged the same pair on the same bar
   (`closed_bar_ts` 1715982300), and it composed the order intent: BTC/USD, quantity 26.26015939,
   the net edge and hurdle above.

The non-gates between them, for completeness. Engine 12 `regime`: `trending`. Engine 8
`prediction`: P(target) 0.9999999979999998, P(stop) and P(timeout) 9.99999998e-10 each, DI
1.240601686375737 under a threshold of 2.0541314397998427. That is a model trained on a
steadily rising constructed series, and it says so by being certain. Engine 9 `order_book`:
slippage 0. Engine 14 `adaptive_router`: **`leaderboard_empty`**. This database has no leaderboard
rows, so the router weighted nothing and named the model it was handed. It is not a gate, and it
changed nothing.

## The order placed

From `orders`, userref **1690626088**. A **buy**, intent `entry`, type `limit`, `oflags` **`post`**
(post-only). Quantity **26.26015939**, limit price **126.9**, placed at 22:00:01
(`placed_at` 1715983201000000). Paper order id `paper-1690626088`.

The limit is the best bid 126.925 rounded **down** onto the pair's grid of one decimal
(`pair_decimals` 1): 126.9. Rounding down is why a post-only buy at the bid cannot cross the book.

*One observation about the row itself:* its `cycle_id` is **3**, not the 2 it was placed on. The
row is upserted by each tick that touches it, and the fill tick wrote it last. "Which tick placed
this order" is answered by `placed_at`, not by `cycle_id` (F-new-2 in tonight's list).

## The fill

The same `orders` row, at 22:01:01 (`closed_at` 1715983261000000): status **`filled`**,
`filled_qty` **26.26015939**, `avg_fill_price` **126.9** (its own limit), fee
**3.6656556492501**.

That fee is 26.26015939 × 126.9 × 0.0011 (maker), and it recomputes exactly. The fill happened
because the scripted market printed one trade at **126.7731** (engine 3's published trade range
for that minute) — 0.1% under the limit. The paper broker fills a resting buy only on a trade
**strictly below** its limit, because the queue position is unknown.

The position it opened, from `positions`: **`pos-1690626088`**, long, 26.26015939 BTC/USD at entry
**126.9**, opened 22:01:01. The barriers are measured from the fill price. Target **130.707** is
126.9 × 1.03. Stop **124.9965** is 126.9 × 0.985. Timeout at **1716026461000000** (2024-05-18
10:01:01) is the opening plus 48 bars of 900 s.

## The watch, minute by minute

The `positions` row is updated in place, so its per-minute marks do not survive in it. Its
`last_price` is `null` now that it is closed. **The minute-by-minute record in the database is
`equity_snapshots`**, one row per tick:

| Cycle | Time | Cash | Positions value | Unrealised PnL | Equity | Open |
|---|---|---|---|---|---|---|
| 3 (fill) | 22:01:01 | 1663.9201177597499 | 3332.414226591 | 0.000000000 | 4996.3343443507499 | 1 |
| 4 | 22:02:01 | 1663.9201177597499 | 3333.07073057575 | 0.65650398475 | 4996.9908483354999 | 1 |
| 5 | 22:03:01 | 1663.9201177597499 | 3333.07073057575 | 0.65650398475 | 4996.9908483354999 | 1 |
| 6 | 22:04:01 | 1663.9201177597499 | 3333.07073057575 | 0.65650398475 | 4996.9908483354999 | 1 |

On the fill tick the position is marked at its own fill price, 126.9. That is spec 106's rule, and
it is why unrealised is exactly zero and equity falls by exactly the maker fee: 5000.00 −
3.6656556492501 = 4996.3343443507499. From cycle 4 it is marked at the bid, 126.925:
26.26015939 × 126.925 = 3333.07073057575, and 26.26015939 × 0.025 = 0.65650398475 unrealised.
Engine 21 triggered nothing and held for nothing on all three watch ticks *(state)*.

## The exit, and which barrier fired

**The target.** In the minute before 22:05:01 the scripted market printed one trade at
**130.757**, above the target 130.707. On the tick at 22:05:01 engine 21 published
`triggered: [{position_id: pos-1690626088, barrier: target}]` *(state)*, and engine 22 sold.

From `orders`, the exit: userref **300065105**, a **sell**, intent `exit`, type **`market`** (a
taker — Phase 6 takes every exit as a taker, a recorded choice in engine 22's docstring), quantity
26.26015939, filled 26.26015939 at **130.757**, fee **6.524029356580637** (= 26.26015939 × 130.757
× 0.0019), placed and filled at 22:05:01.

From `positions`: `pos-1690626088` is **`closed`** at 22:05:01, with trade id
`trade-pos-1690626088`.

From `trades`, the one row:

- outcome **`target`**
- quantity 26.26015939, entry price 126.9, exit price 130.757
- entry fee 3.6656556492501, exit fee 6.524029356580637
- entry userref 1690626088, exit userref 300065105
- opened 22:01:01, closed 22:05:01
- **realised PnL 91.095749761399263** USD. That is proceeds 3433.69966135823, less cost
  3332.414226591, less both fees. It is **0.02733626241134751773049645390** of the entry
  notional, about +2.73%.
- reporting currency USD, FX rate 1 at entry and exit
- `fallbacks_used` **`[]`**: nothing was priced on stale data

## The equity row before, during and after the exit, with the cash source on each

| | Cycle | Time | `cash_source` | Cash | Positions value | Equity | Peak | Realised to date | Open |
|---|---|---|---|---|---|---|---|---|---|
| **Before** | 6 | 22:04:01 | `cycle_start` | 1663.9201177597499 | 3333.07073057575 | 4996.9908483354999 | 5000.00 | 0 | 1 |
| **During** (the exit tick) | 7 | 22:05:01 | **`after_exit`** | 5091.095749761399263 | 0 | 5091.095749761399263 | 5091.095749761399263 | 91.095749761399263 | 0 |
| **After** | 8 | 22:06:01 | `cycle_start` | 5091.095749761399263 | 0 | 5091.095749761399263 | 5091.095749761399263 | 91.095749761399263 | 0 |

**Why the exit tick says `after_exit`.** Engine 1's cash that tick was still 1663.9201177597499,
read at the start of the tick before the sale *(state)*. Engine 21 had valued the position at
130.757 before the sale, at 3433.69966135823 *(state)*. A row built from those would describe no
instant that ever existed. That was the exit-cycle defect ruled on 2026-09-17. So engine 19 drops
the closed position and adds engine 22's net proceeds, 3427.175632001649363 *(state)* =
3433.69966135823 − 6.524029356580637, to the start-of-tick cash: 1663.9201177597499 +
3427.175632001649363 = **5091.095749761399263**, and records `after_exit`.

**Why the row after says `cycle_start` with the same figure.** On cycle 8 engine 1 read the
broker's ledger at the start of the tick, and it already held **5091.095749761399263** *(state)*.
**The `after_exit` figure engine 19 computed on the exit tick equals, to the last digit, the
balance the broker reported independently one minute later.** That is the strongest single check
in this walk-through, and the only one that compares two different writers' answers to the same
question.

**The whole account, reconciled:** 5000.00 − 3332.414226591 (bought) − 3.6656556492501 (maker fee)
+ 3433.69966135823 (sold) − 6.524029356580637 (taker fee) = **5091.095749761399263**, which is
cash, equity and peak on the last two rows, and 5000.00 + the realised 91.095749761399263.
