# `clients/paper` — the paper broker

**Client, not engine. Owner: B.** Operator ruling 2026-09-16.

In paper mode `build_clients` wraps the real `KrakenClient` in `PaperBroker` and hands
that to the engines as `context.clients.kraken`. Engines 18, 21 and 22 call `add_order`,
`cancel_order`, `query_orders` and `open_orders` identically in every mode and never
learn which object they hold. That is the property the whole design is for: a paper run
and a live run are one code path, not two.

## Why it is a client

The operator first ruled the simulator into `engines/execution/` and then corrected it.
**The correction is the operator's own.** A resting post-only entry fills on a *later*
tick, and the engine that notices is 21 `position_manager`, not 18 `execution`. Contract
rule 3 forbids engine 21 importing engine 18, so a simulator living inside 18 could not
be reached by the engine that needs it. In the client layer, both reach it the same way
they reach the exchange.

## Constructor

```python
PaperBroker(real, *, store, config, clock)
```

`real` is the live client — every read and every stream call is forwarded to it
untouched. `store` is the record of what is resting and what has filled. `config`
supplies `paper.starting_balances` and nothing else. `clock` is invariant 9's injected
clock, needed because `BalancesSnapshot.fetched_at` is required and the ledger must
answer whether or not the real `Balance` call worked.

Keyword-only after `real`, deliberately. Phase 5 cost a collision where `models_dir`
landed positional after B had told A it would be keyword-only.

## The fill rules, and why each is the pessimistic reading

A simulator that flatters the strategy is worse than no simulator, because it produces a
number somebody will put in a dissertation. Every rule below resolves its ambiguity
against the strategy.

| Rule | Behaviour | Why this way |
|---|---|---|
| Post-only placement | A buy limit **at or above** the best ask is **rejected**, not repriced | Kraken cancels such an order; invariant 8 calls that the intended behaviour. The comparison is `>=`: a buy exactly at the ask matches the resting sell and pays taker, which the cost gate never priced |
| Resting fill | Fills in full **at its own limit**, and only once a trade printed **strictly below** it | Queue position is unknown — somebody else may have been at that price first and taken the whole print. A trade *at* the limit is not a fill |
| Fill price | The limit, never the lower trade price | The order is resting at L; the market trading through it does not improve it. Filling at the trade price is price improvement no exchange offers a maker |
| Partial fills | **Not simulated.** In full or not at all | Spec 88. A half-filled entry needs a partial position, a partial exit and a re-quote, none of which exist in Phase 6 |
| Market sell | Walks the **bid** side level by level; the fill price is the volume-weighted average of what it actually ate | The top of book is what a one-lot sale gets. A sweep pays worse, and that difference is the whole cost of a liquidation |
| Depth exhausted | The remainder is priced at the **worst fetched level** and the fill records `book_depth_exhausted` | It is an *under*-estimate — the real book continues below the last level fetched — so the number is a floor and the flag says so |
| Fees | Maker on a post-only fill, taker on a market fill, from the tier the real client returns **that tick** | No fallback, no remembered rate. See below |

## Fees are never invented

If a fill needs a fee and no tier is available, the broker raises `PaperBrokerError` and
the message says to escalate. It does not reach for the last tier it saw, and there is
nothing to reach for: invariant 2 deliberately does **not** retain the fee tier, for the
same reason it does not retain the spread. Spec 88's scope limit and spec 93's say the
same thing from either side, and the case they are both about is a liquidation during an
outage.

`AGENTS.md`'s first paragraph forbids a fee percentage written into the code.
`test_the_broker_holds_no_fee_rate_of_its_own` walks both modules' ASTs and refuses one
as a literal — narrower than a text search, because the docstrings here legitimately
quote "0.22% is 0.0022" when explaining the ratio convention, and wider, because it
catches a rate written as a bare float too.

## The balance is the ledger, always

**Operator ruling 3, 2026-09-16.** In paper mode `balance()` is `paper.starting_balances`
adjusted by every recorded fill, **whether or not the real fetch works**, because no
simulated fill spends the real account. The real endpoint is never called — calling it
and discarding the answer would leave an unused private call in the paper path, and the
first person to "fix" the unused value would reintroduce the defect the ruling removes.

That defect was found in planning and is worth keeping written down: invariant 2 promised
an adjustment nothing implemented, so engine 11 sized against cash an earlier paper fill
had already spent, and engine 19's equity counted that cash twice.

**Quote side only.** An entry debits `qty x price + fee`; an exit credits `qty x price`
less `fee`. A buy is **not** credited with base currency. Engine 19 computes
`equity = cash + positions_value`, where `cash` is the reporting currency's balance and
the base leg is already the `positions` row — crediting it here would be a second
representation of one exposure, and the two would disagree the first time a fill and a
position row did.

**Never `SUM()` in SQL.** Money columns are TEXT with a `typeof` check, so SQLite would
add them lexicographically or coerce them to floats. `StoreClient.filled_orders()` returns
rows and the addition happens in Python over `Decimal`.

## What it holds, and what a restart loses

**Resting orders are the store's rows.** The broker reads
`StoreClient.resting_orders()` and `order_by_userref()` every time. An in-memory book
would be lost by a restart and the system would then hold a position whose entry order it
had forgotten — the exact failure invariant 8's `userref` idempotency exists to prevent.

`_pending` holds only what the broker accepted on this tick, in the gap between engine 18
placing an order and engine 19 recording it. **The store wins whenever it has the row**,
and `_pending`'s copy is dropped at that moment.

> **Deviation from spec 88 step 2, flagged to the lead.** The spec says `_pending` is held
> "only until the tick's end". The tick's end was going to be the trade drain, and the
> drain turned out to be a method nothing calls (below). With no tick edge the broker can
> see, `_pending` is pruned by *recording* instead. For the normal path that is stricter
> than the spec; for the abnormal one it is safer, because an order engine 19 failed to
> record lingers rather than vanishing from a system that has accepted it.

**Observed trades are not held at all.** The broker reads `recent_trades()` when it needs
them. A restart therefore loses nothing of its own, but it does lose the stream's buffer
along with the process, so a resting entry that "should" have filled during the gap waits
for the next trade below its limit or for engine 21's unfilled window. Pessimistic, which
is the only direction a simulator may err in.

## The trade seam — spec 88 says `drain_trades()`, and nothing calls it

Spec 88 step 3 says engine 3 *drains* trades through `clients.kraken`. It does not.
`engines/market_sensor/engine.py` calls `recent_trades()`, which `ws.py` documents as a
rolling window that deliberately does **not** clear, because engine 3 rebuilds the same
15-minute bar on each of the fifteen ticks that bar spans and an engine is stateless
across cycles. `drain_trades()` exists on the client, on `ws.py` and in A's
`MarketStreamProtocol`, and no caller in `src/` uses it.

The spec's conclusion holds — the broker is in the path, so it and engine 3 cannot
disagree about which trades happened — and its mechanism does not. So the broker keeps no
observation buffer and no tick boundary: reading is non-destructive, there is nothing for
two readers to race over, and seeing one trade repeatedly cannot double-fill because the
order is terminal after the first. Every candidate trade is still filtered to
`ts > placed_at`, which is invariant 10: engine 3 reads the window in the guard chain and
engine 18 places in the opportunity chain, so a trade that printed before the order
existed would fill it on the past.

`test_the_broker_and_engine_three_see_the_same_trades_on_one_tick` runs the real engine 3
against the broker and compares its published `trade_ranges` with what the broker will
resolve a fill against. `test_the_broker_never_drains_the_trade_window_itself` counts the
drains across a placement and a fill resolution and requires zero.

**One real limitation.** `recent_trades()` is bounded by `max_buffered_trades` — a window
by **count**, not by time. A resting entry older than that window cannot see the trade
that would have filled it. Engine 21 cancels an entry at
`trading.entry_unfilled_window_s`, which bounds the exposure, but on a very busy pair the
count window could be shorter than the time window. The direction is pessimistic, so this
is a number to check once both have real values against each other, not a defect to fix
here.

## What it never does

- **No transport call from any order method, in any mode.** Asserted against the source:
  `self._real.add_order` and the other three names do not appear in `broker.py`.
- **No relational write.** Engine 19 `memory` is the single writer of every table.
- **No market buy, and no limit order that is not post-only.** This system places
  post-only entries (invariant 8) and taker exits (invariant 14). A third behaviour would
  be a capability nothing asked for.
- **No second placement under one `userref`.** Invariant 8 requires the caller to check
  first, so a second placement is a defect and refusing it is where that becomes visible.
- **No empty answer.** An unknown `userref`, an unreadable window or a missing fee tier
  raises. Invariant 3: the absence of a "no" is never a "yes", and A's
  `OrderClientProtocol` says the same about this surface — an `open_orders` answering
  `()` during an outage would tell engine 21 there was nothing resting to cancel.
