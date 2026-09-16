"""The fill rules, as pure functions. No clock, no I/O, no state.

Everything here is arithmetic over values the broker hands it, so each rule can be
tested at its boundary without a store, a client or a tick. The broker decides *when*
to ask; this module decides *what the answer is*, and the two are separated because the
rules are the part a reader has to be able to check against the spec by eye.

## Every rule is the pessimistic reading, and that is the whole design

A simulator that flatters the strategy is worse than no simulator, because it produces
a number somebody will put in a dissertation. Each rule below therefore resolves its
ambiguity against the strategy:

- **A post-only buy at or above the best ask is rejected**, not repriced and not filled.
  Kraken cancels such an order outright — invariant 8 says so and calls it the intended
  behaviour — so the simulator does the same thing rather than inventing a kinder one.
- **A resting buy at L fills only when a trade printed strictly below L.** A trade *at*
  L is not a fill. Queue position is unknown: somebody else's order may have been at
  that price first and taken the whole print. Requiring a strictly better price is the
  only assumption that cannot be optimistic. Spec 88 names the boundary explicitly and
  two tests pin it, one tick each side.
- **Partial fills are not simulated.** An order fills in full or not at all. This is the
  one rule that is not obviously pessimistic in both directions and it is the operator's
  spec rather than a choice made here: a half-filled entry would need a partial position,
  a partial exit and a re-quote, and none of those exist in Phase 6.
- **A market sell walks the bid side level by level** and pays the volume-weighted
  average of what it actually eats, never the top of book. If the fetched depth cannot
  absorb the quantity the remainder is priced at the **worst fetched level** and the
  fill records ``book_depth_exhausted``, so a liquidation into a thin book is expensive
  in the simulator exactly as it would be in life.

## Fees are never invented

:func:`fee_on` takes a rate and multiplies. There is no default rate, no fallback tier
and no "assume maker". `AGENTS.md` forbids a remembered fee in its first paragraph and
invariant 2 retired the one fallback that ever named a tier. A fill that has no rate
available is not priced here at all — the broker raises, and spec 88's scope limit says
to escalate rather than choose one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

__all__ = [
    "DEPTH_EXHAUSTED",
    "BookWalk",
    "apply_fill_to_ledger",
    "fee_on",
    "post_only_would_cross",
    "resting_buy_fill_price",
    "walk_bids",
]

#: Recorded on a fill whose quantity the fetched book could not absorb. The remainder is
#: priced at the worst level actually fetched, which is an under-estimate of what a real
#: sweep would pay — so the flag is not decoration, it says the number is a floor.
DEPTH_EXHAUSTED = "book_depth_exhausted"


def post_only_would_cross(*, limit_price: Decimal, best_ask: Decimal) -> bool:
    """True when a post-only **buy** at `limit_price` would take liquidity.

    At or above the ask crosses. The comparison is `>=` and not `>`: a buy limit exactly
    at the best ask matches the resting sell immediately and is a taker, which is
    precisely what `oflags=post` exists to refuse.

    Only the buy side is expressed, because the only post-only order this system places
    is an entry and every entry is a buy (the system is long-only; see
    `context/project-overview.md`). A sell version would be dead code that looked like a
    capability.
    """
    return limit_price >= best_ask


def resting_buy_fill_price(
    *, limit_price: Decimal, trade_prices: tuple[Decimal, ...]
) -> Decimal | None:
    """The price a resting post-only buy at `limit_price` fills at, or `None`.

    It fills **in full at its own limit** the first time a trade prints *strictly below*
    it, and at no other time. Two consequences worth stating, because both are the
    pessimistic direction and both look like mistakes at a glance:

    - The fill price is `limit_price`, not the lower trade price. The order is resting at
      L; the market trading through it does not improve it. Filling at the trade price
      would hand the strategy price improvement the exchange never offers a maker.
    - A trade exactly at L does not fill. See the module docstring: queue position is
      unknown.

    `trade_prices` is whatever the caller decided happened after the order was placed.
    Deciding *which* trades those are is the broker's job and it needs a clock; deciding
    what they mean is this function's and it does not.
    """
    for price in trade_prices:
        if price < limit_price:
            return limit_price
    return None


class BookWalk(NamedTuple):
    """What a market sell got, walking the bids.

    `filled_qty` is always the full requested quantity — the remainder is priced, not
    dropped — and `flags` says whether the book could really have absorbed it.
    """

    avg_price: Decimal
    filled_qty: Decimal
    flags: tuple[str, ...]


def walk_bids(*, levels: tuple[tuple[Decimal, Decimal], ...], qty: Decimal) -> BookWalk:
    """Sell `qty` into `levels`, best bid first, and report the average price paid.

    `levels` is `OrderBookSnapshot.bids` — `(price, volume)` pairs, best first. The walk
    takes volume from each level in turn until the quantity is met. The price is the
    volume-weighted average of what was actually eaten, which is the number a real sweep
    would realise and is strictly worse than the top of book whenever more than one level
    is touched.

    **Depth exhausted.** If every fetched level together cannot absorb `qty`, the
    remainder is priced at the worst level fetched and :data:`DEPTH_EXHAUSTED` is
    recorded. That is deliberately an *under*-estimate of the real cost — the true book
    continues below the last level we fetched — so the flag has to travel with the fill
    rather than being swallowed, and spec 93 records it on the trade.

    Raises on a non-positive quantity or an empty book. Neither is a thin book: they are
    a caller that has already gone wrong, and returning a price for them would be
    inventing one.
    """
    if qty <= 0:
        raise ValueError(f"a market sell needs a positive quantity, got {qty}")
    if not levels:
        raise ValueError(
            "an empty bid side has no price to sell into; absent is not zero, and a "
            "zero here would value the whole position at nothing"
        )

    remaining = qty
    proceeds = Decimal(0)
    for price, volume in levels:
        if remaining <= 0:
            break
        taken = volume if volume < remaining else remaining
        proceeds += taken * price
        remaining -= taken

    if remaining > 0:
        worst = levels[-1][0]
        proceeds += remaining * worst
        return BookWalk(proceeds / qty, qty, (DEPTH_EXHAUSTED,))
    return BookWalk(proceeds / qty, qty, ())


def fee_on(*, notional: Decimal, rate: Decimal) -> Decimal:
    """The fee on `notional` at `rate`, where `rate` is a ratio and 0.22% is `0.0022`.

    `FeeTierSnapshot` validates the ratio convention at its own boundary, so a rate that
    arrived as `0.22` has already been refused before it reaches here. The check below is
    not a duplicate of that one: it refuses a **negative** rate, which is a rebate, and a
    rebate is a thing Kraken's top tiers genuinely have and this system has never priced.
    Paying the strategy money on a fill is the one fee error that cannot be conservative.

    No rounding. The fee is exact and the ledger is exact; rounding to a currency's minor
    unit is a presentation concern and doing it here would put a rounding rule in the one
    place nothing can see it.
    """
    if rate < 0:
        raise ValueError(
            f"a negative fee rate is a rebate, and this system has never priced one; got {rate}"
        )
    if notional < 0:
        raise ValueError(f"a fee is charged on a positive notional, got {notional}")
    return notional * rate


def apply_fill_to_ledger(
    balances: dict[str, Decimal],
    *,
    quote: str,
    is_entry: bool,
    filled_qty: Decimal,
    fill_price: Decimal,
    fee: Decimal,
) -> dict[str, Decimal]:
    """`balances` with one filled order applied, quote side only. Returns a new map.

    **A buy spends; a sell receives; the fee is a cost in both directions.** An entry
    debits `filled_qty x fill_price + fee`; an exit credits `filled_qty x fill_price`
    less `fee`. Getting the fee's sign right on the exit is the arithmetic worth checking: the
    fee reduces what the sale brings in, so it is subtracted from a credit, not added to
    it.

    **Only the quote currency moves.** A buy is not credited with base, and that is spec
    88's own wording — "minus every filled entry's notional and fee, plus every filled
    exit's proceeds less fee" — rather than an omission. Engine 19 computes equity as
    `cash + positions_value`, where `cash` is the reporting currency's balance and the
    base leg is the `positions` row it already reads. Crediting base here would be a
    second representation of one exposure, and the two would disagree the first time a
    fill and a position row did.

    A currency absent from `balances` starts at zero rather than raising: a paper account
    configured with only USD that somehow fills a EUR-quoted pair should show the debt,
    not hide it. Engine 11 refuses such a pair long before this (`no_fx_rate`), so this is
    a floor under a case that should not arise, not a supported currency.
    """
    notional = filled_qty * fill_price
    delta = -(notional + fee) if is_entry else (notional - fee)
    updated = dict(balances)
    updated[quote] = updated.get(quote, Decimal(0)) + delta
    return updated
