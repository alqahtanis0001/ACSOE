# Engine 9 — `order_book`

**Number:** 9 · **Chain:** opportunity, after engine 8, before engine 10 · **Gate:** no ·
**Runtime stage:** 3

Estimates the slippage the candidate's **exit** would pay and publishes it as
`state["order_book"]["estimated_slippage_pct"]` — the fourth term of invariant 5's friction, and
the key engine 10 `cost` has read since Phase 3.

Three of friction's four terms are quoted numbers the exchange states outright: the maker fee,
the taker fee, and the measured spread. Slippage is not quoted anywhere, because it is not a
property of the market alone — it is a property of how deep the book is **relative to the size
being sold**. So it has to be walked.

## How little this is validated on

**Engine 9 is validated over seconds to minutes of recorded book, never years of archive,
because the historical archive carries no book at all.** `tests/fixtures/book_sample.jsonl` is
thirty seconds of two pairs. Nothing here says how slippage behaves across regimes, across
sizes, or across years, and **every slippage number this system reports inherits that limit** —
including every `friction_pct` in the `rejections` table and every hurdle comparison engine 10
has ever made.

This is not a gap to be closed by writing more tests. It is a gap in the *data*: Kraken's free
historical archive is OHLCVT, with no bid, no ask and no depth, which is the whole reason
`scripts/record.py` started collecting on day one of the project. Book history begins when the
recorder did and cannot be backfilled. The same sentence is in the tracker via spec 80.

## What is estimated, and at what size

**A taker sell walking the bid side.** Invariant 5 assumes maker on entry and taker on exit,
because a stop must always exit as a taker. The entry is a post-only limit (invariant 8) — if it
would cross the book Kraken cancels it, which is the intended behaviour — so a maker entry pays
**no** slippage and estimating one would charge the system for a cost it does not pay.

**At the account's whole balance in the pair's quote currency.** Engine 9 runs before engine 11
sizes the order, so the size is not yet known. Invariant 6 forbids allocating more than the
quote balance, and slippage does not fall as size rises, so the whole balance is an **upper
bound** on anything engine 11 could approve and the cost gate errs toward refusing.

Lead ruling, 2026-09-16, flagged as overturnable by the operator. The alternative — run engine 9
after engine 11 and estimate at the real size — was not taken because the registry order is
fixed and because a hurdle priced at an upper bound is the conservative direction.

```
estimated_slippage_pct = (best_bid - volume_weighted_fill_price) / best_bid
```

Measured from the **best bid**, not the mid. A taker sell lifts the bid, so the bid is the price
the exit could actually see. Measuring from the mid would fold half the spread into slippage,
and engine 10 already adds the spread as its own term — the same cost counted twice.

`basis_notional`, `levels_consumed`, `best_bid` and `fill_price` are published beside the
estimate so a criterion holding the same book can **recompute** the ratio rather than read back
a number this engine wrote about itself.

## This engine never blocks

`is_gate = False`, and on **every** fail-closed shape it returns `OK`, **omits**
`estimated_slippage_pct`, and publishes a reason code. Engine 10, which is a gate, then refuses
on the absent key — its `_require` treats absent and `None` identically, which is the fail-closed
posture stated in its own docstring.

A non-gate that refused on its own criteria would make `is_gate` wrong, which is exactly the
principle the operator applied to engine 16. Engine 8's `di_refused` block is the one
operator-ruled exception, 2026-09-12, and is not a precedent to extend.

| Reason code | The shape | Why it is not an estimate |
|---|---|---|
| `book_fetch_failed` | the `order_book` call raised | an outage, an unknown pair, a malformed payload, or a side the client's own model refused to build |
| `book_unusable` | a book that *was* returned, but is crossed, non-positively priced, negatively sized, or out of order | a feed fault; a slippage walked over one is fabricated |
| `book_too_thin` | the bid side cannot absorb the basis notional within `depth` | an estimate past the fetched depth would be a guess, and the levels nobody fetched are the worst ones |
| `no_quote_balance` | the account holds nothing spendable in the pair's quote currency | there is no notional to walk |
| `order_book_inputs_unavailable` | no candidate pair, no `AssetPairs` snapshot, a failed `Balance` fetch, or `order_book.depth` absent or null | the walk could not be set up |

**An empty side never reaches the reason table's second row.** `OrderBookSnapshot` refuses an
empty side at construction, deliberately, so that "no book" arrives at a caller as a failure
rather than as a zero spread. It therefore surfaces as `book_fetch_failed`. The emptiness check
in `_unusable` is kept anyway, as the assertion that the client's refusal is the live branch:
deleting a guard for something that cannot happen throws away the tripwire for the day it can.

### One deliberate asymmetry with engine 11

Engine 11 `risk` applies invariant 2's paper-mode fallback to `paper.starting_balances` when
engine 1 published no balances, because it must still size *something*. **Engine 9 does not.** It
has nothing it must still do, so the conservative reading is to publish no estimate and let the
gate refuse. Spec 96 step 4 lists a failed balance read as a fail-closed shape and this follows
that list verbatim.

Two engines reading one key and treating it differently is the kind of thing that looks like an
oversight later, so it is written down here. Overturnable by the lead or the operator.

A **zero** balance and an **absent** balance map are told apart: the first is a fact about the
account (`no_quote_balance`), the second a fact about the call (`order_book_inputs_unavailable`).
An operator acts on them differently, and a handler that cannot distinguish two situations will
silently pick the wrong one.

## What it reads

| Source | Owner | Used for |
|---|---|---|
| `state["scout"]["pair"]` | engine 7 (B) | the candidate pair |
| `state["exchange"]["pair_rules"]["pairs"][pair]["quote"]` | engine 1 (A) | which currency the basis notional is denominated in |
| `state["exchange"]["balances"][quote]` | engine 1 (A) | the basis notional itself |
| `context.clients.kraken.order_book(pair, depth)` | A | the book. **Fetched, not read from `state`** — a depth-limited walk needs more than engine 3's top-of-book quote |
| `config order_book.depth` | lead | how many levels a side to fetch, and therefore the bound on the walk |

Every key name is a named constant in `contracts.py` with its owning engine beside it.

The book is the one thing this engine fetches, and it does so through `context.clients.kraken`
per contract rule 4, with `platform.aio.run_blocking` around the coroutine, the same way engine 1
runs its three calls. Engines are synchronous; the client is async.

## What it writes into `state["order_book"]`

| Field | Type | Present when |
|---|---|---|
| `reason_code` | string or null | always — `null` on success. A payload is never `{}`, which is the shape shared by the engine that had nothing to do and the engine that raised |
| `pair` | string | the candidate pair was readable |
| `depth` | int | `order_book.depth` was readable |
| `quote_currency` | string | the pair's rules were readable |
| `basis_notional` | decimal string | the account holds a positive balance in that currency |
| `best_bid` | decimal string | a usable book came back |
| `fill_price` | decimal string | the walk completed |
| `levels_consumed` | int | the walk completed |
| `estimated_slippage_pct` | decimal string | the walk completed — **omitted otherwise, never null** |

Money crosses `state` as an exact decimal string in plain notation, per contract rule 8. Nothing
here is a float: `Money` raises on one rather than coercing it, so a float arrives named at this
boundary instead of three decimals into a hurdle comparison.

## Precision

`Decimal` throughout, under the ambient 28-significant-digit context, and **nothing is
quantized** — the same choice `market_sensor.spread_ratio` makes, for the same reason. Exactly
two operations are inexact and neither has an exact alternative: dividing a remainder by a price
to get base units, and dividing quote by base to get the volume-weighted price. A
volume-weighted average of rational prices is not generally representable. Rounding here would
decide in the 28th digit what the hurdle decides in the fourth.

`estimated_slippage_pct` is non-negative by construction: the walk takes levels in descending
price order, so the weighted price can never beat the top of book. It is exactly zero when the
whole notional fits in the first level.

## The fixture

`tests/fixtures/book_sample.jsonl` — thirty seconds of `ADA/USD` (thin) and `BTC/USD` (deep),
cut from the live archive by A's `scripts/cut_book_fixture.py`. Its provenance is in
`tests/fixtures/README.md`; the reason the window opens where it does is in
`docs/build-log/phase-6/c-interface.md`. The short version: the archive records book **deltas**,
so the window has to open at a resubscribe or there is no absolute book in it to start from.
