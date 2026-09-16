"""Spec 88 — the fill rules, at their boundaries.

Every rule here is the *pessimistic* reading and the boundary is where that word does
its work. A simulator that fills on a touch, or walks the ask side, or adds a fee to a
sale instead of subtracting it, still produces plausible numbers on a happy path and
still passes any test that only checks "something filled". So each rule is asserted one
tick either side of the line it draws, and the two assertions differ in one input.

The Hypothesis properties are here rather than in the broker tests because these are the
functions with arithmetic in them. A property answers a question a table of examples
cannot: **is there any book at all** for which the walk beats the top of book, and **is
there any sequence of fills** for which the ledger disagrees with itself.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from acsoe.clients.paper.fills import (
    DEPTH_EXHAUSTED,
    apply_fill_to_ledger,
    fee_on,
    post_only_would_cross,
    resting_buy_fill_price,
    walk_bids,
)


def d(value: str) -> Decimal:
    return Decimal(value)


#: Prices and volumes as exact decimals, at the scale a real book uses. Money is never a
#: float anywhere in this system and a strategy that generated one would be testing a
#: shape the code is entitled to refuse.
prices = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("100000"), places=2, allow_nan=False
)
volumes = st.decimals(
    min_value=Decimal("0.00000001"), max_value=Decimal("1000"), places=8, allow_nan=False
)


# --------------------------------------------------------------------------- #
# Post-only: at the ask is a cross
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("limit", "crosses"),
    [("99.99", False), ("100.00", True), ("100.01", True)],
    ids=["below the ask rests", "at the ask crosses", "above the ask crosses"],
)
def test_a_post_only_buy_crosses_at_the_ask_and_not_a_tick_below(
    limit: str, crosses: bool
) -> None:
    """The boundary is `>=`, and the middle case is the whole reason this test exists.

    A buy limit exactly at the best ask matches the resting sell immediately and pays
    the taker fee — which is precisely what `oflags=post` exists to refuse, and what
    invariant 8 means by "if it would cross the book, Kraken cancels it, and that is the
    intended behaviour". An implementation using `>` rests such an order and the strategy
    then pays maker fees the exchange charged as taker, which the cost gate never priced.
    """
    assert post_only_would_cross(limit_price=d(limit), best_ask=d("100.00")) is crosses


# --------------------------------------------------------------------------- #
# A resting buy fills strictly below its limit
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("trade", "fills"),
    [("99.99", True), ("100.00", False), ("100.01", False)],
    ids=["strictly below fills", "a touch does not", "above does not"],
)
def test_a_resting_buy_fills_only_on_a_trade_strictly_below_its_limit(
    trade: str, fills: bool
) -> None:
    """Spec 88's named boundary, one tick each side.

    Touching the limit is not a fill because **queue position is unknown**: somebody
    else's order may have been at that price first and taken the whole print. Requiring a
    strictly better price is the only assumption that cannot flatter the strategy, and
    the difference is not small — on a quiet pair the touch is the common case, so a
    simulator that filled on it would report a fill rate the exchange would never give.
    """
    got = resting_buy_fill_price(limit_price=d("100.00"), trade_prices=(d(trade),))
    assert (got is not None) is fills


def test_the_fill_is_at_the_limit_and_never_at_the_better_trade_price() -> None:
    """A trade at 90 does not fill a resting buy at 100 *at 90*.

    The order is resting at its limit; the market trading through it does not improve it.
    Filling at the trade price would hand the strategy price improvement no exchange
    offers a maker, and it would do so exactly on the ticks where the market moved
    hardest against the position about to be opened.
    """
    assert resting_buy_fill_price(
        limit_price=d("100.00"), trade_prices=(d("90.00"),)
    ) == d("100.00")


def test_no_trades_at_all_is_no_fill_rather_than_an_error() -> None:
    """A quiet pair is the ordinary case, not a failure: fourteen ticks in fifteen."""
    assert resting_buy_fill_price(limit_price=d("100.00"), trade_prices=()) is None


# --------------------------------------------------------------------------- #
# The bid walk
# --------------------------------------------------------------------------- #


def test_a_walk_inside_one_level_pays_that_level() -> None:
    walk = walk_bids(levels=((d("100.00"), d("10")),), qty=d("4"))

    assert walk == (d("100.00"), d("4"), ())


def test_a_walk_across_two_levels_pays_the_volume_weighted_average() -> None:
    """Hand-computed, so the assertion is not the implementation restated.

    Two units at 100 and three at 99 is 200 + 297 = 497 for five units, 99.40. A
    simulator pricing the whole sweep at the top of book would say 100.00 and would
    understate the cost of every exit through a thin book — which is exactly the number
    a liquidation's realised PnL turns on.
    """
    walk = walk_bids(levels=((d("100.00"), d("2")), (d("99.00"), d("5"))), qty=d("5"))

    assert walk.avg_price == d("99.40")
    assert walk.filled_qty == d("5")
    assert walk.flags == ()


def test_a_book_too_thin_prices_the_remainder_at_the_worst_level_and_says_so() -> None:
    """Depth exhausted, and the flag matters as much as the price.

    One unit at 100 and one at 99, selling three: the two fetched units cost 199 and the
    third is priced at 99, the worst level we actually saw. That is an **under**-estimate
    — the real book continues below the last level fetched — so the number is a floor and
    :data:`DEPTH_EXHAUSTED` is what says so. Swallowing the flag would leave a fill that
    reads like any other.
    """
    walk = walk_bids(levels=((d("100.00"), d("1")), (d("99.00"), d("1"))), qty=d("3"))

    assert walk.avg_price == (d("100") + d("99") + d("99")) / d("3")
    assert walk.filled_qty == d("3")
    assert walk.flags == (DEPTH_EXHAUSTED,)


def test_an_empty_book_raises_rather_than_pricing_at_zero() -> None:
    """Absent is not zero. A zero here would value the whole position at nothing, which
    is a realised loss of 100% arriving as a price rather than as an error."""
    with pytest.raises(ValueError, match="empty bid side"):
        walk_bids(levels=(), qty=d("1"))


@pytest.mark.parametrize("qty", ["0", "-1"])
def test_a_non_positive_quantity_raises(qty: str) -> None:
    with pytest.raises(ValueError, match="positive quantity"):
        walk_bids(levels=((d("100.00"), d("1")),), qty=d(qty))


@settings(max_examples=200, deadline=None)
@given(
    levels=st.lists(st.tuples(prices, volumes), min_size=1, max_size=8),
    qty=volumes,
)
def test_a_walk_never_beats_the_best_bid_and_never_loses_quantity(
    levels: list[tuple[Decimal, Decimal]], qty: Decimal
) -> None:
    """The two properties a table of examples cannot establish.

    **The average never beats the top of book**, on any book at all — the strategy can
    only do worse by eating into depth, never better, and an implementation that walked
    the *ask* side or sorted the levels ascending would violate this on the first
    multi-level example. The strategy sorts descending first, because `OrderBookSnapshot`
    guarantees best-first and Hypothesis does not.

    **The quantity is never lost.** The remainder is priced, not dropped, so a sweep
    into a book too thin to absorb it still reports the full size — a partial here would
    leave a position half-closed with nothing recording the half.
    """
    book = tuple(sorted(levels, key=lambda level: level[0], reverse=True))
    walk = walk_bids(levels=book, qty=qty)

    assert walk.filled_qty == qty
    assert walk.avg_price <= book[0][0]
    assert walk.avg_price >= book[-1][0]


# --------------------------------------------------------------------------- #
# Fees
# --------------------------------------------------------------------------- #


def test_a_fee_is_the_notional_times_the_ratio() -> None:
    """0.22% of $1,000 is $2.20. The convention is a ratio and the field name says so."""
    assert fee_on(notional=d("1000"), rate=d("0.0022")) == d("2.20")


def test_a_negative_rate_is_refused_rather_than_paid_to_the_strategy() -> None:
    """Kraken's top tiers genuinely have maker rebates and this system has never priced
    one. Paying the strategy money on a fill is the single fee error that cannot be
    conservative, so it raises rather than quietly crediting the ledger."""
    with pytest.raises(ValueError, match="rebate"):
        fee_on(notional=d("1000"), rate=d("-0.0001"))


# --------------------------------------------------------------------------- #
# The ledger
# --------------------------------------------------------------------------- #


def test_an_entry_debits_the_notional_and_the_fee() -> None:
    """$5,000 less 10 x $100 less $2.20 of fee."""
    after = apply_fill_to_ledger(
        {"USD": d("5000.00")},
        quote="USD",
        is_entry=True,
        filled_qty=d("10"),
        fill_price=d("100.00"),
        fee=d("2.20"),
    )

    assert after["USD"] == d("3997.80")


def test_an_exit_credits_the_proceeds_less_the_fee_and_not_plus_it() -> None:
    """The sign that is easy to get wrong, asserted on its own.

    The fee reduces what the sale brings in. An implementation adding it credits twice
    the fee on every round trip — a small number that compounds across every trade and
    moves the realised PnL in the flattering direction.
    """
    after = apply_fill_to_ledger(
        {"USD": d("0")},
        quote="USD",
        is_entry=False,
        filled_qty=d("10"),
        fill_price=d("100.00"),
        fee=d("3.80"),
    )

    assert after["USD"] == d("996.20")


def test_only_the_quote_currency_moves() -> None:
    """Spec 88's own wording, and the reason is engine 19's equity formula.

    Equity is `cash + positions_value`, where `cash` is the reporting currency's balance
    and the base leg is already the `positions` row. Crediting base here would be a
    second representation of one exposure and the two would disagree the first time a
    fill and a position row did.
    """
    after = apply_fill_to_ledger(
        {"USD": d("5000.00")},
        quote="USD",
        is_entry=True,
        filled_qty=d("10"),
        fill_price=d("100.00"),
        fee=d("0"),
    )

    assert set(after) == {"USD"}, "a buy credits no base currency"


def test_the_input_map_is_not_mutated() -> None:
    """A new map each time, so a caller folding fills in a loop cannot half-apply one
    and keep the result."""
    before = {"USD": d("5000.00")}

    apply_fill_to_ledger(
        before,
        quote="USD",
        is_entry=True,
        filled_qty=d("1"),
        fill_price=d("100.00"),
        fee=d("0"),
    )

    assert before == {"USD": d("5000.00")}


@settings(max_examples=200, deadline=None)
@given(
    start=st.decimals(min_value=0, max_value=Decimal("1000000"), places=2),
    qty=st.decimals(
        min_value=Decimal("0.00000001"), max_value=Decimal("100"), places=8
    ),
    price=prices,
    fee=st.decimals(min_value=0, max_value=Decimal("100"), places=8),
)
def test_a_round_trip_at_one_price_costs_exactly_the_two_fees(
    start: Decimal, qty: Decimal, price: Decimal, fee: Decimal
) -> None:
    """The ledger's defining property, over any quantity, price and fee.

    Buy `qty` at `price` and sell it straight back at the same price: the notionals
    cancel exactly and what is left is the two fees. **Exactly**, with no tolerance —
    money is `Decimal` here precisely so this can be an equality, and a float
    implementation fails it on the first eight-decimal quantity Hypothesis tries.

    This is the property the "add the fee on the exit" defect breaks: the balance comes
    back at `start` rather than `start` less twice the fee, which reads like a system that trades
    for free.
    """
    after_entry = apply_fill_to_ledger(
        {"USD": start},
        quote="USD",
        is_entry=True,
        filled_qty=qty,
        fill_price=price,
        fee=fee,
    )
    after_exit = apply_fill_to_ledger(
        after_entry,
        quote="USD",
        is_entry=False,
        filled_qty=qty,
        fill_price=price,
        fee=fee,
    )

    assert after_exit["USD"] == start - fee - fee
