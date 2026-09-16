# Engine 18 — `execution`

**Not a gate.** `is_gate = False`. Opportunity chain, runtime stage 4, after engine 16
`decision`. It has no criteria of its own, which is the point: everything that could
refuse this trade has already run and said yes.

On a tick where every gate passed, engine 18 places **exactly one** post-only limit buy,
for the quantity engine 11 approved, at the best bid, under a `userref` derived from the
pair and the bar — and then publishes the row engine 19 records.

## Inputs read from `state`

| Key | Used for |
|---|---|
| `decision.intent` | `pair`, `qty`, `closed_bar_ts` — engine 16's order intent |
| `market_sensor.quotes[pair].bid` | the price the entry rests at |
| `exchange.pair_rules.pairs[pair].pair_decimals` | the grid the price is rounded onto |

Plus `context.clients.store` and `context.clients.kraken` for the idempotency probe and
the placement.

**It reads engine 16's intent rather than five engines' keys.** That is spec 90's whole
purpose: engine 16 has already checked that the pair, the bar and the quantity belong to
one another, so engine 18 does not re-check and does not re-derive.

## Output written to `state`

`state["execution"]`:

```
{"pair": str, "userref": int, "placed": bool,
 "orders": [ {order row} ],           # at most one; empty in one case, below
 "reason_code": str}
```

Engine 21 reads this key **on the same tick**, before engine 19 has written anything, so
that a `close_all` arriving on the tick of a placement does not report every entry
cancelled while one is resting.

`placed` is *this tick's* placement and nothing else. An order found already recorded
publishes `placed: False` and still publishes its row.

## It returns `OK`, never `PASS`

The orchestrator stops the opportunity chain on a `PASS`, and downstream that reads as
"nothing to do here". An order that was just placed is the opposite of nothing to do.
`OK` with `placed` carrying the fact is the shape that says both.

## Reason codes

| Code | Meaning |
|---|---|
| `entry_placed` | a post-only limit buy is now resting |
| `entry_already_placed` | this `userref` is already in the store; nothing placed |
| `post_only_would_cross` | the exchange refused; the candidate is abandoned this tick |
| `entry_unrecorded_at_exchange` | the order is at the exchange and not in the store |

Engine 18 is not a gate, so none of these is a refusal. The field is how every engine in
this system says what it did, and a placement with no code would be the one outcome the
console cannot narrate.

## Invariant 8, and the probe that is **not** `query_orders`

The rule is "never place an order without first checking whether that `userref` already
exists". Two sources are asked:

1. **`store.order_by_userref`** — the authoritative record, across restarts and across
   every status.
2. **`kraken.open_orders()`** — for the one case the store cannot cover: the order was
   placed and engine 19 never recorded it, because the process died between the two.

**Spec 91 step 3 names `query_orders` for the second probe, and `query_orders` cannot do
this job.** `OrderClientProtocol` says a call that cannot be completed *raises* rather
than returning an empty result, and the paper broker raises for an unknown `userref` for
exactly that reason. So `query_orders` answers "I have never heard of this order" and "I
cannot reach the exchange" with the same exception, and those two require opposite
actions:

- treat the raise as *unknown* and an outage becomes a duplicate order — invariant 8's
  named failure;
- treat it as *cannot tell* and the **first** placement of every candidate is refused,
  because a first placement is always unknown, and the system never trades at all.

`open_orders()` has a well-defined negative — the order is not in the list — and still
raises during an outage, so invariant 3 still holds and an outage abandons the tick.

It cannot miss the case it exists for. A post-only limit buy at the best bid **cannot
fill at placement**; that is what post-only means. So an entry placed earlier in this
same bar and not yet recorded is still resting, and resting is what `open_orders()`
lists.

The spec's conclusion is right and its mechanism is the one that cannot work. Flagged to
the lead rather than treated as settled.

## The order the exchange holds and the store has never heard of

Placed, then the process died before engine 19 recorded it. Engine 18 finds it on its
second invariant 8 probe, places no duplicate, and **publishes its row** under
`entry_recovered_from_exchange`.

**It published nothing until 2026-09-16**, and the reason is worth keeping because it is
the argument that got `OrderState` changed. The model carried `userref`, `order_id`,
`status`, `filled_qty`, `avg_fill_price`, `fee` and `closed_at` — no `qty`, no
`limit_price`, no placement time — so an order found this way could be *detected* and
not *described*. All three could have been guessed, from this tick's approved quantity,
this tick's best bid and this tick's clock, and every one of them would be wrong the
moment equity, the book or the hour moved.

The consequence of publishing nothing was worse than a missing record. An order engine 21
cannot see is an order **nothing will ever cancel**, because engine 21 assembles entries
from the store plus `state["execution"]`. That is unmanaged exposure and it is the
failure invariant 8 exists to prevent. A's spec 84 amendment added `qty`, `limit_price`
and `opened_at`, and this branch now builds the row from the exchange's own answer —
including the placement time, so engine 21 cancels the order in the **ordinary** unfilled
window rather than one window late.

### What is filled from the contract rather than from an observation

`pair`, `side`, `intent`, `order_type` and `oflags`. Invariant 8 makes every entry a
post-only buy limit; the `userref` is `userref_for(pair, bar)`, so an order resting under
it is this candidate's pair by construction, and a `userref` recorded against a different
pair already raises as a collision two branches above.

That is the distinction the operator's ruling draws, and the two look identical in a
diff: substituting a **market observation** is fabrication, restating the system's own
contract is not.

### Two refusals, and neither of them raises

Both publish no row, leave the `userref` in the payload so an operator can find the order
by hand, and abandon the candidate for the tick.

| Code | When | Why no row |
|---|---|---|
| `entry_at_exchange_is_not_a_limit` | the answer carries no `limit_price` | invariant 8 makes every entry a limit order, so this is the exchange contradicting the placement. A limit order with a null price in `orders` is a row engine 21 cannot reason about |
| `entry_unrecorded_at_exchange` | the answer carries no `opened_at` | a clock reading substituted for a missing `opentm` is a time that never happened, written into the column research and the console read as a placement time — and `fallbacks_used` is a `trades` column, so there is nowhere to record the substitution either |

`OrderState` deliberately carries no `order_type`: the presence of a limit price is a
total discriminator, and a second field holding the same bit is one more thing that can
disagree. So the model cannot refuse the first case and the consumer that knows what it
asked for must.

**Neither is an `ERROR`, and the reason is the circuit breaker.** Lead ruling,
2026-09-16. Contract rule 7 would turn a raise into `ERROR`, engine 19 writes
`block_records.status = 'ERROR'`, and engine 17 `safety` counts those rows in the
trailing hour against `safety.max_errors_in_window` and freezes the account. An exchange
contradicting itself about one order is not the system malfunctioning and must not spend
the breaker's budget.

## The price: the best bid, and it is a recorded absence

**Every Phase 6 entry rests at the best bid.** Nobody defended this as the right offset.
The execution offset bandit is a Locked Decision the operator **deferred to Phase 7** on
2026-09-16: it needs a table that does not exist and learns from a fill history that does
not exist either. It is written here so nobody reads best-bid placement as a choice
someone argued for.

Joining the bid never crosses while the spread is positive, and engine 4 `data_guard`
already refuses a crossed book.

Rounded **down** to the pair's `pair_decimals`, never to-nearest. Down is the pessimistic
direction on both edges that matter: further from crossing, so post-only rejects less
often; and less likely to fill, so the simulator never reports a fill a real exchange
would not have given.

## The `userref`

Derived from `(pair, closed_bar_ts)` with `blake2b`, mapped into `[1, USERREF_MAX - 1]`.

**`hash()` is ruled out** and that is not a style preference: Python salts string hashing
per process, so a restart between placing and checking would compute a *different*
`userref` for the same candidate and place a second order on it. Invariant 8's exact
failure, arriving through a builtin that looks pure.

The pair and the bar are what make a candidate one candidate: one bar yields at most one
entry per pair, because invariant 6's per-pair clause says so and engine 11 enforces it.

**A collision is a defect, not a retry.** If the store holds this `userref` against a
different pair, engine 18 raises. Placing anyway would put this candidate's order under
an identifier that already belongs to another pair's, after which neither can be
cancelled by `userref` with any confidence.

## What this engine must never do

- **Place a market or taker entry, under any condition or flag.** Invariant 8. Engine
  10's hurdle was computed against a *maker* entry, so a market entry trades an edge the
  cost gate never approved. `order_types_named_in_this_module()` walks the module's AST
  and a test asserts the only `OrderType` it references is `LIMIT` — structural, because
  a behavioural test can only prove the paths it drove placed no market order.
- **Chase, re-price or replace.** A rejected post-only order is recorded and the
  candidate is abandoned for this tick.
- **Re-size.** The quantity is engine 11's.
- **Write a relational row.** Engine 19 records.
- **Default anything.** An absent intent, quote or pair rule raises. Engine 18 has no
  refusal of its own to publish, so an input that is not there is the chain
  contradicting itself rather than "no trade this tick".
