"""What engine 9 `order_book` reads out of `state`, and what it writes back into it.

`estimated_slippage_pct` is a **cross-chain key**, fixed in `engine-contracts.md`:
engine 10 `cost` has read it since Phase 3 and it is one of the four terms of invariant
5's friction. Nothing here may rename it without the lead.

## Money crosses `state` as an exact decimal string

The same rule as every other engine, for the same reason: the orchestrator's
`_assert_json_serialisable` refuses a `Decimal` and **accepts a `float`**, so the
dangerous half is the one that passes. Every money field below is :data:`Money` — a
`Decimal` carrying a validator that raises on a float rather than coercing it — and
leaves through :func:`money_text`, which is `format(d, "f")` and never scientific
notation.

`estimated_slippage_pct` is a ratio, not a currency amount, and it is money in exactly
the sense that matters: engine 10 adds it to two fee rates and a spread and compares
the result against a hurdle, and this system's edges are fractions of a percent. A
float here arrives in that comparison wrong in the fourth decimal.

## The published payload is designed to be recomputed, not trusted

`basis_notional`, `levels_consumed`, `best_bid` and `fill_price` are published beside
the estimate because a criterion holding the same book must be able to **rederive the
ratio** rather than read back a number this engine wrote about itself. That is the
Phase 5 closing finding — "a record of intent is not a record of what happened" —
applied at the point where the record is written.

## Absence, and why it is an omission rather than a null

On every fail-closed shape this engine **omits** `estimated_slippage_pct` from its
payload entirely and publishes a `reason_code` instead. Engine 10's `_require` treats
an absent key and a `None` identically, so either would block it; the omission is the
one that cannot be misread by a future consumer that checks `in` rather than `is None`.

Engine 9 is **not a gate** and never blocks on any of these shapes. A non-gate that
refuses on its own criteria makes `is_gate` wrong, which is the principle the operator
applied to engine 16; engine 8's `di_refused` is the one operator-ruled exception and
is not a precedent. The refusal is engine 10's, and it is a refusal for the absent
input rather than for the reason code — which is why a test drives both engines
together rather than asserting on this one alone.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.kraken.contracts import money_text
from acsoe.clients.store.contracts import Money

__all__ = [
    "BASIS_NOTIONAL_FIELD",
    "DEPTH_KEY",
    "ESTIMATED_SLIPPAGE_FIELD",
    "EXCHANGE_BALANCES_KEY",
    "EXCHANGE_KEY",
    "EXCHANGE_PAIR_RULES_KEY",
    "LEVELS_CONSUMED_FIELD",
    "PAIR_QUOTE_FIELD",
    "PAIR_RULES_PAIRS_KEY",
    "REASON_BOOK_FETCH_FAILED",
    "REASON_BOOK_TOO_THIN",
    "REASON_BOOK_UNUSABLE",
    "REASON_INPUTS_UNAVAILABLE",
    "REASON_NO_QUOTE_BALANCE",
    "SCOUT_KEY",
    "SCOUT_PAIR_FIELD",
    "BookWalk",
    "SlippageEstimate",
    "walk_the_bid_side",
]

# --------------------------------------------------------------------------- #
# State paths
# --------------------------------------------------------------------------- #

#: Engine 7 `scout` (B). Which pair the tick is considering.
SCOUT_KEY: Final = "scout"

#: The candidate pair's field under :data:`SCOUT_KEY`. The cross-chain key table in
#: `engine-contracts.md` fixes this one; engines 10 and 11 read the same path.
SCOUT_PAIR_FIELD: Final = "pair"

#: Engine 1 `exchange` (A). The **account** engine: balances, fee tier, pair rules.
#: Engine 3 is the market-data engine; the book is not read from `state` at all, it is
#: fetched, because a depth-limited walk needs more than a top-of-book quote.
EXCHANGE_KEY: Final = "exchange"

#: Per-currency spendable balance under :data:`EXCHANGE_KEY`, as decimal strings.
#: `None` when the `Balance` call failed — which is not a zero balance, and is the
#: whole reason this engine distinguishes them.
EXCHANGE_BALANCES_KEY: Final = "balances"

#: The whole `AssetPairs` snapshot under :data:`EXCHANGE_KEY`, and the mapping inside
#: it. Read for one field only: which currency the pair is quoted in.
EXCHANGE_PAIR_RULES_KEY: Final = "pair_rules"
PAIR_RULES_PAIRS_KEY: Final = "pairs"

#: The pair's quote currency, inside a :data:`PAIR_RULES_PAIRS_KEY` entry. Invariant 7:
#: a pair is only executable if the account holds spendable balance in this currency,
#: so this is also the currency the basis notional is denominated in.
PAIR_QUOTE_FIELD: Final = "quote"

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

#: How many levels a side to fetch. Requested of the lead under spec 80.
#:
#: **It is not a free parameter.** It bounds the walk, so it bounds what
#: :data:`REASON_BOOK_TOO_THIN` means: a basis notional the book cannot absorb *within
#: this many levels* is refused rather than extrapolated. A `depth` larger than the
#: depth the committed fixture was recorded at would configure the live engine to walk
#: further than any committed evidence can validate, which is why the value asked for
#: matches `scripts/record.py`'s `DEFAULT_DEPTH`.
DEPTH_KEY: Final = "order_book.depth"

# --------------------------------------------------------------------------- #
# Published field names
# --------------------------------------------------------------------------- #

#: The cross-chain key, read by engine 10 `cost` since Phase 3. Omitted — never null —
#: on every fail-closed shape. Fixed in `engine-contracts.md`.
ESTIMATED_SLIPPAGE_FIELD: Final = "estimated_slippage_pct"

#: The notional the estimate was taken at, and how many levels the walk consumed.
#: Published so a criterion can recompute the ratio from the same book instead of
#: believing this engine's arithmetic about itself.
BASIS_NOTIONAL_FIELD: Final = "basis_notional"
LEVELS_CONSUMED_FIELD: Final = "levels_consumed"

# --------------------------------------------------------------------------- #
# Reason codes
# --------------------------------------------------------------------------- #
#
# Every one of these is published with status `OK` and `blocks_trading=False`, beside
# an **absent** `estimated_slippage_pct`. They are codes for the console, not blocks:
# `ownership.md`'s rejection-reason row was widened on 2026-09-16 to cover every engine
# that publishes a `reason_code`, not only the gates, and spec 99's walking test reads
# these constants out of this module by name.

#: The `order_book` call did not answer. An outage, an unknown pair, a malformed
#: payload, or a book the client's own model refused to build — **including an empty
#: side**, which `OrderBookSnapshot` rejects at construction so that "no book" reaches
#: a caller as a failure rather than as a zero spread. Engine 9 cannot tell those apart
#: through the client boundary and does not pretend to; the operator sentence carries
#: the client's own message.
REASON_BOOK_FETCH_FAILED: Final = "book_fetch_failed"

#: A book the client *did* return, which this engine then found unusable: crossed
#: (best bid above best ask), a non-positive price, a negative quantity, or a bid side
#: that is not in descending price order. None of those is a small number — each is a
#: feed fault, and a slippage walked over one is a fabricated figure.
REASON_BOOK_UNUSABLE: Final = "book_unusable"

#: The bid side cannot absorb the basis notional within `depth` levels. An estimate
#: past the fetched depth would be a guess, and a guess here is optimistic by
#: construction: the levels nobody fetched are the worst ones.
REASON_BOOK_TOO_THIN: Final = "book_too_thin"

#: The account holds nothing in the pair's quote currency, so there is no notional to
#: walk. Distinct from a failed `Balance` fetch, which is
#: :data:`REASON_INPUTS_UNAVAILABLE`: a zero balance is a fact about the account and an
#: absent balance map is a fact about the fetch, and an operator acts on them
#: differently.
REASON_NO_QUOTE_BALANCE: Final = "no_quote_balance"

#: An input needed before the walk could even be set up was absent or unusable: no
#: candidate pair, no `AssetPairs` snapshot, no quote currency for the pair, a
#: `Balance` call that failed, or `order_book.depth` missing or left null.
REASON_INPUTS_UNAVAILABLE: Final = "order_book_inputs_unavailable"


# --------------------------------------------------------------------------- #
# The walk
# --------------------------------------------------------------------------- #


class BookWalk(BaseModel):
    """What a taker sell of `basis_notional` would achieve against the bid side.

    Pure arithmetic over levels, with no `state` and no client in it, so the walk can
    be tested against a hand computation without building an engine around it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    best_bid: Money
    """The top bid, and the reference the slippage is measured from.

    **Not the mid.** Slippage is what the exit gives up against the price it could see
    at the moment it decided, and a taker sell lifts the bid. Measuring from the mid
    would fold half the spread into slippage, and engine 10 already adds the spread as
    its own term — the same cost would be counted twice.
    """

    fill_price: Money
    """The volume-weighted price the whole basis notional achieves."""

    base_filled: Money
    """How much of the base asset the walk sold. Carried so the weighting can be
    checked: `fill_price * base_filled` is `basis_notional` to the working precision."""

    levels_consumed: int
    """How many bid levels the walk touched, counting a partially filled level."""

    @property
    def slippage_pct(self) -> Decimal:
        """`(best_bid - fill_price) / best_bid`, as a ratio.

        Non-negative by construction: the walk takes levels in descending price order,
        so the volume-weighted price can never beat the top of book. Zero exactly when
        the whole notional fits in the first level.
        """
        return (self.best_bid - self.fill_price) / self.best_bid


def walk_the_bid_side(
    bids: tuple[tuple[Decimal, Decimal], ...], basis_notional: Decimal
) -> BookWalk | None:
    """Sell `basis_notional` worth into `bids`, or `None` if the side cannot absorb it.

    `None` rather than an exception, and rather than a partial fill reported as a
    whole one: a walk that runs out of book has not measured anything, and the levels
    it did not reach are by definition worse than the ones it did. Extrapolating past
    the fetched depth would produce a number that is optimistic exactly where the risk
    is.

    The caller is responsible for having checked the book is usable —
    :data:`REASON_BOOK_UNUSABLE` — because "this side is nonsense" and "this side is
    too thin" are two different facts and a single `None` could not tell them apart.

    Arithmetic is `Decimal` under the ambient context, which is 28 significant digits.
    Two of the operations are inexact — dividing a remainder by a price to get base
    units, and dividing quote by base to get the weighted price — and there is no
    exact alternative, because a volume-weighted average of rational prices is not
    generally representable. Nothing is quantized, for the same reason
    `market_sensor.spread_ratio` quantizes nothing: the consumer is a comparison
    against a hurdle at four decimal places, and rounding here would decide in the
    28th digit what the hurdle decides in the fourth.
    """
    if basis_notional <= 0:
        return None

    remaining = basis_notional
    base_filled = Decimal(0)
    levels_consumed = 0

    for price, quantity in bids:
        level_notional = price * quantity
        levels_consumed += 1
        if level_notional >= remaining:
            base_filled += remaining / price
            remaining = Decimal(0)
            break
        base_filled += quantity
        remaining -= level_notional

    if remaining > 0 or base_filled <= 0:
        return None

    return BookWalk(
        best_bid=bids[0][0],
        fill_price=basis_notional / base_filled,
        base_filled=base_filled,
        levels_consumed=levels_consumed,
    )


# --------------------------------------------------------------------------- #
# The payload
# --------------------------------------------------------------------------- #


class SlippageEstimate(BaseModel):
    """What this engine publishes into `state["order_book"]`.

    Every field is optional, because every fail-closed shape publishes as much as it
    got to before it stopped and nothing it did not. A shape that could not read the
    quote currency publishes no `basis_notional`; one that could not fetch publishes no
    `best_bid`; one that never learned which pair it was looking at publishes no
    `pair`. Filling those with zeros would put numbers into the record that were never
    used to decide anything.

    `reason_code` is always written, `None` included, so the payload is never `{}` —
    which `code-standards.md` names as the shape shared by the engine that had nothing
    to do and the engine that raised.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str | None = None
    depth: int | None = None
    quote_currency: str | None = None
    basis_notional: Money | None = None
    best_bid: Money | None = None
    fill_price: Money | None = None
    levels_consumed: int | None = None
    estimated_slippage_pct: Money | None = None
    reason_code: str | None = None

    def to_state_data(self) -> dict[str, Any]:
        """The JSON-serialisable mapping the orchestrator puts in `state["order_book"]`.

        **An absent money value is dropped, not written as null.** The cross-chain
        contract says engine 9 *omits* `estimated_slippage_pct` when it has none, and
        the same treatment is given to every other optional field so that the payload
        never carries a key whose value says nothing.

        `reason_code` is the exception: it is written as `None` on the success path,
        because "there was no reason" is a fact the console renders and engine 19
        stores, and dropping it would make a successful tick indistinguishable from a
        payload that predates the field.
        """
        payload: dict[str, Any] = {"reason_code": self.reason_code}
        if self.pair is not None:
            payload["pair"] = self.pair
        if self.depth is not None:
            payload["depth"] = self.depth
        if self.quote_currency is not None:
            payload["quote_currency"] = self.quote_currency
        for field, value in (
            (BASIS_NOTIONAL_FIELD, self.basis_notional),
            ("best_bid", self.best_bid),
            ("fill_price", self.fill_price),
            (ESTIMATED_SLIPPAGE_FIELD, self.estimated_slippage_pct),
        ):
            if value is not None:
                payload[field] = money_text(value)
        if self.levels_consumed is not None:
            payload[LEVELS_CONSUMED_FIELD] = self.levels_consumed
        return payload
