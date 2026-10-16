# Engine 21 — `position_manager`

**Not a gate.** Manage chain, first, before engine 22 `exit` and engine 19 `memory`.
Owner: B.

It runs **every tick, in every mode, and never stops**. The opportunity chain runs on one
tick in fifteen and halts at the first gate that refuses; the manage chain does neither,
because a position that exists has to be watched whether or not anything new is being
considered.

## What it does, in order

1. **Turns filled entries into positions.** The fill comes from the client's
   `query_orders` — the paper broker in paper mode, the exchange in live — never from a
   price comparison of this engine's own. Three opinions about what filled would diverge
   on exactly the ticks that matter.
2. **Cancels entries that outran their window.** Never replaced, never chased.
3. **Marks every open position to the market**, at the bid.
4. **Decides barriers** — stop, target, timeout — and publishes them for engine 22.
5. **Cancels every resting entry when `close_intent` is set**, regardless of the window.

## Inputs

| Value | Read from | Published by |
|---|---|---|
| Resting entries | `store.resting_orders(intent=entry)` | 19 `memory` (C), on earlier ticks |
| This tick's placement | `state["execution"]["orders"]`, **when present** | 18 `execution` (B) |
| Open positions | `store.open_positions()` | 19 `memory` (C) |
| Fills and cancels | `clients.kraken.query_orders`, `cancel_order` | A's order surface (spec 84); B's paper broker in paper mode |
| The mark | `state["market_sensor"]["quotes"][pair]["bid"]` | 3 `market_sensor` (A) |
| Whether a position's own pair is live | `state["market_sensor"]["quotes"][pair]` — `bid`, `ask`, `age_s` | 3 `market_sensor` (A) |
| The barrier test | `state["market_sensor"]["trade_ranges"][pair]` | 3 `market_sensor` (A), spec 85 |
| `base`, `quote` | `state["exchange"]["pair_rules"]["pairs"][pair]` | 1 `exchange` (A) |

Configuration: `barriers.target_pct`, `barriers.stop_pct`, `barriers.timeout_bars`,
`timeframes.decision_bar_s`, `trading.entry_unfilled_window_s`, and
`data_guard.max_data_age_s` — engine 4's key, shared on purpose (see the hold).

**Last tick's decisions come from the store, never from `state`.** `state` is rebuilt
every tick and an engine is stateless across cycles.

**This tick's placement comes from `state`, and it has to.** Engine 19 writes at the end
of the manage chain, so an entry engine 18 placed earlier in *this* tick is not in the
store yet. Without that second source, a `close_all` arriving on the same tick as a
placement reports every entry cancelled while one is resting — and the orchestrator then
clears `close_intent` with a live post-only buy on the book, which invariant 8 names as
the uncancelled order that survives a liquidation and re-opens exposure.

## The mark and the barrier are two different readings, deliberately

A **mark** is a valuation: what would this position fetch if sold right now. That is the
bid. The ask is a price nobody is offering to pay, and marking there overstates equity on
every tick and understates the drawdown engine 17 acts on.

A **barrier** is an event: did the market *trade* at my stop between the last tick and
this one. A quote sampled once a minute cannot answer that. Two ticks sixty seconds apart
see two prices and the market did everything in between, so a stop touched at second 30
and recovered by second 59 is invisible to a quote comparison — and that is precisely the
case a stop exists for. Spec 85's `trade_ranges` is the record of the interval, and its
`low` and `high` are **traded** prices: a book that quoted 100 and never traded there did
not touch 100.

A pair that did not trade has **no** `trade_ranges` entry at all — `TradeRange` refuses a
zero count — so no price barrier can fire for it and only the timeout can.

## Both barriers in one tick resolve to stop

The same rule the training labels use, and for the same reason. Within one tick the order
of two prints is unknown; resolving to `target` would count as a win a trade that may
well have stopped out first. Resolving to `stop` cannot flatter the strategy, and it
keeps the live outcome and the label computed the same way — which is the only thing that
makes the backtest comparable to the live record.

A **touched barrier beats an elapsed timeout** for the matching reason: a position that
hit its stop *and* ran out of time exited on the stop, and `trades.outcome` is a record
of what happened. Recording `timeout` would put a trade that lost 1.5% into the bucket
research uses to ask whether the horizon is too long.

## Barriers are measured from the fill

`target_price` and `stop_price` come from the price actually paid, not from the decision
bar's close the training label was measured against.

**Lead ruling, flagged to the operator as overturnable.** Engine 11 sized the quantity by
dividing the risk budget by the stop *distance*, taken from the entry price. A stop placed
from any other price risks a different amount of money than the risk gate approved —
which is that gate being overridden by an arithmetic detail nobody chose.

**The cost, stated rather than left to be found.** When the fill differs from the bar
close, a live trade's barriers and its label's barriers are not identical, so the live
outcome and the labelled outcome can disagree on a marginal bar. Anyone comparing the
backtest with the live record needs to know that before they read the difference as
alpha decay.

## The hold

There are two, and they differ in scope, not in what they suppress: each decides **no
barrier at all** — no stop, no target, no timeout — for what it holds.

**The feed-wide hold.** When `state["trading_blocked_by"] == "data_guard"` and
`close_intent` is not set, no barrier is decided for any position, `triggered` is empty,
and `hold_reason` is `data_guard_blocked` — on the tick and on every position row. A
trigger computed from data engine 4 has just rejected is a fabricated trigger acting on
real money.

**The per-pair hold** (D10, operator ruling 2026-09-21, option 1). Otherwise, a position
whose **own** pair has no live quote is held alone: no barrier is decided for it and its
row carries `hold_reason: pair_quote_not_live`. Every position on a live pair is decided
exactly as before, so a stale quote on some unrelated thin pair no longer freezes every
stop. Positions opened by this tick's fill are judged the same way. "Live" is engine 7's
`no_live_quote` predicate, restated:

| Not live when | |
|---|---|
| the quote is absent | |
| the bid or ask is absent, unparseable, or not positive | a float is "not a price" here, which holds the one position, rather than an error that would stop the tick and every other stop with it |
| the bid is above the ask | a crossed book |
| the quote carries no `age_s`, or it is not a number, or it is a bool | engine 3 stamps one on every quote, so its absence is a defect upstream |
| `age_s` is past `data_guard.max_data_age_s` | **exactly at the bound is live** — the `<=` engines 4, 7 and 16 use |

The bound is **the key engines 4 and 7 read** (D10 fix 1), restated in `contracts.py` as
`MAX_DATA_AGE_KEY` and pinned to theirs by a test. It is read with **no default**: null
errors the tick. It is read only when there is a position to judge and neither the
feed-wide hold nor a liquidation applies — a tick on which it decides nothing never
consults it.

**The tick-level `hold_reason` is the feed-wide hold only** (`data_guard_blocked` or
null): it is a property of the tick. The per-pair reason lives on the row, and engine 19
stores the row's reason when the tick's is null. So **every row carries the key, set
every tick, never copied from the store** — a row republished with an earlier tick's
reason would carry that hold forward forever.

**The per-pair hold is not counted by `safety`'s outage escalation**, which counts
`data_guard` blocks only. A position on a pair that stops quoting for good is held without
escalating — OPEN for the operator as D17 in
`docs/build-log/phase-8/decisions-2026-09-21.md`.

**A block by any other engine does not hold.** A `cost` or `safety` block is a statement
about whether to *open* something; a position already open is still managed. Holding on a
`safety` freeze would leave a stop unactioned because the account was frozen, which is the
opposite of what a freeze is for.

**A liquidation never holds anything**, and every `hold_reason` — the tick's and each
row's — is null throughout one. Invariant 14: a feed outage is what triggers the
escalation and the same outage is what would hold it, so if either hold applied,
`close_all` would be blocked by the exact condition it exists to answer.

**The stale-entry cancel still happens during either hold.** Invariant 8 says so in as many
words: it is a decision about elapsed time, it reads `context.now`, it needs no market
data, and it reduces exposure. The hold suppresses **exits**, never this.

## Output written to `state["position_manager"]`

`positions`, `orders`, `positions_value`, `unrealised_pnl`, `triggered`, `hold_reason`,
`entry_orders_cancelled`, `reason_code`.

`positions` and `orders` are store-contract row payloads **minus `run_id`, `cycle_id` and
`updated_at`**. Engine 19's `_stamped` sets those three itself, because a row carrying
somebody else's `run_id` cannot be joined to the block record for the tick and
`(run_id, cycle_id)` is the join. A publisher that set them would win silently, since
`_stamped` overwrites rather than refusing.

**`positions_value` and `unrealised_pnl` are omitted, never zero, when any position could
not be marked.** A partial sum is worse than no sum: engine 19 would write it as the
account's whole value while `peak_equity` kept the real figure, and the difference is a
drawdown engine 17 acts on. Absent makes engine 19 skip the equity row, which is what its
own docstring says it does. The same rule per position: no `last_price` and no
`unrealised_pnl` on a position with no quote, never a price carried over from a previous
tick.

**A position opened by this tick's fill is valued at the fill price, and its row says
so:** `last_price` is the fill price and `unrealised_pnl` is zero, from the same mark the
totals use, so the stored position and the equity row describe one valuation. It is not
re-marked at the bid until the next tick. Spec 106: before it, the row carried neither and
engine 19 stored both NULL while the totals valued the position at cost.

**Every row with a `last_price` also carries `value = qty × last_price`, and a row without
one carries no `value`** (spec 113). Absent means the position could not be valued. It
never means zero, and it is never the position's cost. On a tick where engine 22 closed
positions, engine 19 drops the closed rows and sums `value` over the rest (spec 114). On
every other tick it reads the totals. The row values are computed beside the totals,
not from them, and a test checks that they sum exactly to `positions_value` whenever
the total is present. That test is what keeps engine 19's two paths in agreement, and
it has been shown to fail when they disagree. `value` is a payload field, not a
`positions` column.

**`hold_reason` is null rather than omitted** on a tick that did not hold, and on every
position row that was not held. Null is the answer there; an omission is
indistinguishable from an engine that never ran.

**`entry_orders_cancelled` is the literal boolean `True` only when no resting entry
remains.** A failed cancel, or an order the client will not report on, leaves it `False`,
the orchestrator keeps `close_intent` set and the cancel is retried next tick. Spec 81
fixed the orchestrator's truthiness fail-open on this field; absent or false always means
"not finished".

## A fill the pair rules cannot describe is published as nothing at all

`base` and `quote` for a position row have exactly one publisher, engine 1, and invariant
2 gives pair rules no fallback in any mode. If the `AssetPairs` fetch failed on the tick
an entry filled, this engine publishes **neither** the order row nor the position row for
that order, sets `reason_code: position_unrecordable`, and leaves the entry resting.

Publishing the order row alone would record the entry as filled with no position against
it — money spent and nothing holding it — and it would no longer be resting, so nothing
would ever pick it up. Leaving it resting means `query_orders` reports the same fill on
the next tick and it is recorded then, as soon as the pair rules come back.

## Two `OrderStatus` enums, and this engine touches both

`clients/store/contracts.py` and `clients/kraken/contracts.py` each define an
`OrderStatus` with the same five spellings. They compare equal under `==` and they are
**different objects**, so `is` between them is always `False`.

This engine reads the kraken one (from the order client) and writes the store one (in row
payloads), so it imports both — the client's as `ClientOrderStatus`. Comparison stays
identity rather than `==`, because `==` would also accept a bare string from anywhere,
which is the shape that hid this in the first place. Getting it wrong cost thirteen red
tests and, had the tests not existed, a `close_all` reporting itself complete with a live
order on the book. `mypy --strict` cannot see it: `context.clients.kraken` is structural
and typed `Any`. The account is in `docs/build-log/phase-6/b-store.md`, 2026-09-16.

## What it never does

- **Places no exit.** Engine 22 places exits.
- **Writes no relational row.** Engine 19 is the single writer.
- **Never replaces, re-prices or re-places an entry.** Invariant 8.
- **Never holds on any blocker other than `data_guard`, and never holds a liquidation.**
  The one hold without a blocker is per position, on that position's own pair's quote.
- **Never decides a fill itself.** The client decides.
