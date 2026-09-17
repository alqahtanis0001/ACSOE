# Engine 22 — `exit`

**Owner:** B · **Chain:** manage, after 21 `position_manager`, before 19 `memory` ·
**Gate:** no · **Spec:** 93

The only engine in this system that sells. It runs every tick, in every mode, and it
carries **invariant 14** — the one deliberate override in the whole document.

## What it does, in order

1. **A liquidation sells everything.** `close_intent` set means every open position in
   the store, as a market sell, whatever the guard said and whatever the exchange is
   answering.
2. **An ordinary tick sells what engine 21 triggered**, and nothing else. This engine
   decides no barrier of its own, so the two cannot disagree about whether a stop was
   touched.
3. **A `data_guard` tick sells nothing at all**, unless it is a liquidation.

## Every exit is a taker, and that is a choice rather than an oversight

Invariant 8 *permits* a maker exit on target and *requires* an immediate one on stop.
Phase 6 takes every exit as a market sell, target included.

Invariant 5's friction already assumes a taker exit when it prices the hurdle, so a
maker target exit would make a trade cheaper than the gate that approved it priced —
which is never a defect in itself, but it means nothing is *rejected* for the want of
it. And a resting maker exit is a second order to manage, cancel, reconcile and survive
a restart with, for a saving the gate never counted on.

## The hold

When `state["trading_blocked_by"] == "data_guard"` and `close_intent` is not set: **no
exit of any kind.** Not a target, not a stop, not a timeout. `reason_code` is
`data_guard_blocked` — the same spelling engine 21 publishes as its `hold_reason`,
because it is the same fact about the same tick.

Engine 21 already publishes no `triggered` entries on such a tick, so this is a second
lock on one door, and it is deliberate. `engine-contracts.md` states the hold of engines
21 **and** 22. A trigger computed from data engine 4 has just rejected is a fabricated
trigger acting on real money, and the cost of the duplicate check is one comparison.

**A block by any other engine does not hold.** A `cost` or `safety` block is a statement
about whether to *open* something; a position already open still has to be got out of.

## Invariant 14 — what the liquidation overrides

| Overridden | Not overridden |
|---|---|
| a `data_guard` block | rounding **down** to `lot_decimals` |
| a failed `AssetPairs` fetch (retained metadata is read **past its TTL**) | the `userref` idempotency check |
| a failed balance fetch — see below | the ban on opening, adding to or re-entering anything |
| | inventing a fee when the tier cannot be fetched |

Every tolerated failure is recorded on the trade's `fallbacks_used`, so a fill is never
mistaken for one priced on good data. Today that list has exactly one member,
`asset_pairs_last_known_good`.

### This engine never reads a balance

Spec 93 names a `balance_last_known_good` fallback. It is deliberately **not defined**,
and the reason is worth stating rather than leaving as an absence.

An exit's quantity is the position's, from the `positions` row. The only thing a balance
could add is a cap at the base currency actually held — and the paper ledger is
**quote-side only** by the spec 88 ruling, so the base balance of every paper position
is zero and such a cap would round every paper exit to nothing. A fallback constant that
nothing ever emits is worse than an absent one: it reads as a behaviour the system has.

What invariant 14 actually needs here is that a **failing** balance fetch does not stop
the liquidation, and it does not, because nothing on this path asks for one. Escalated to
the lead rather than settled in an engine.

### The one stale read, and its boundary

`clients.kraken.last_known_good_asset_pairs` is read **only** when `close_intent` is
set. On an ordinary tick, a pair with no rules published is a refusal — invariant 2 gives
pair rules no fallback in any mode, because a wrong `lot_decimals` produces an invalid
order.

It is a **property** on A's client and on the paper broker, not a method. Spec 93 writes
it as a call; the surface is what it is, and this is recorded so the next reader does not
think the engine is missing a pair of parentheses.

## Idempotency

`exit_userref_for(position_id)` is a `blake2b` digest, never `hash()` — Python salts
string hashing per process, so a restart between placing and checking would compute a
different identifier and sell the position twice, which is invariant 8's exact failure
arriving through a builtin that looks pure.

The input is the **position**, not the barrier. A position triggered on `stop` this tick
and on `timeout` next tick is one exit; hashing the barrier would place a second market
sell for a position already being sold.

A `userref` found in the store against a **different** position is a digest collision,
and a collision is a defect rather than a retry: neither order could afterwards be
cancelled or reconciled by `userref`.

## What it publishes

`state["exit"]`, read by engine 19 `memory`:

| Field | Meaning |
|---|---|
| `orders` | the exit order rows, engine 19's shape minus `run_id`, `cycle_id`, `updated_at` |
| `positions` | the closed position rows, same shape |
| `closed_trades` | one row per closed round trip |
| `positions_closed` | **the boolean `True` only when no open position remains.** Half the kill switch's completion signal |
| `reason_code` | what this engine did |

`positions_closed` is published on every tick, including ordinary ones: a field that
appears only during a liquidation is a field whose absence has two meanings. Absent or
false always means "not finished", and a position this tick could not exit leaves it
false, so the orchestrator keeps `close_intent` set and the next tick tries again.

A `close_all` on an account with nothing open is **finished**, and this engine says so.
Hardcoding `False` when there is nothing to sell would leave `close_intent` set forever
on exactly that account.

## Reason codes

| Code | Meaning |
|---|---|
| `exits_placed` | at least one exit was placed this tick |
| `exit_already_placed` | every exit asked for was already at the exchange; nothing new placed |
| `nothing_to_exit` | nothing triggered and no liquidation running |
| `data_guard_blocked` | the guard rejected the tick's data and this is not a liquidation |
| `exit_incomplete` | at least one position could not be got out of; `positions_closed` is false and the tick reports `ERROR` |

Engine 22 is not a gate, so none of these is a refusal. The field is how every engine
says what it did.

## The trade row

`realised_pnl = qty × (exit_price − entry_price) − entry_fee − exit_fee`, exact
`Decimal` throughout, and `realised_pnl_pct` is that over the cost basis.

`entry_fee` comes from the entry order's row in the store, which is the only place it
exists. A position with no `entry_userref`, or an entry row with no fee, **raises**: a
zero entry fee is a trade that looks more profitable than it was, in the series
`safety`'s loss streak is counted from.

`fx_rate_entry` and `fx_rate_exit` are `1`, and the equality that makes them `1` is
**asserted rather than assumed**. Invariant 7 forbids absorbing FX exposure into PnL,
and engine 11 refuses any pair whose quote is not the reporting currency today
(`no_fx_rate`), so a position reaching here with a foreign quote is the chain
contradicting itself — not a case to price at a rate nobody fetched.

`net_proceeds = qty × exit_price − exit_fee` (spec 113) is the cash the sale put into
the account, computed from the same `qty`, `exit_price` and `exit_fee` the row carries.
On a tick where this engine closed positions, engine 19 adds it to engine 1's
start-of-tick balance for the equity row (spec 114). It reads neither engine 21's
valuation nor engine 1's balance: the operator withdrew a design in which this engine
subtracted engine 21's marks, because that tied a fact about a sale to how another
engine values positions. It is a payload field, not a `trades` column.

## A partial failure is reported, never smoothed

One position that cannot be exited does not stop the others: on a liquidation, flat on
two of three beats flat on none. The one that failed is published as still open, the
reason code is `exit_incomplete`, the engine's status is `ERROR`, and `positions_closed`
is false. The manage chain never breaks early, so engine 19 still records the tick.

## What it never does

Decides a barrier — engine 21 does. Writes a relational row — engine 19 does. Opens,
adds to or re-enters a position, under any circumstances, including a liquidation.
