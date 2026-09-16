"""Engine 9 `order_book` — the slippage term of invariant 5's friction.

Invariant 5 computes friction as four terms:

```
friction = live_maker_fee + live_taker_fee + measured_spread + estimated_slippage
```

Three of them the exchange states outright. The fourth does not exist as a quoted
number anywhere: slippage is a property of how deep the book is *relative to the size
being sold*, so it has to be walked. This engine walks it, and engine 10 `cost` adds
the result to the other three.

**What is estimated: a taker sell walking the bid side.** Invariant 5 assumes maker on
entry and taker on exit, because a stop must always exit as a taker. A post-only maker
entry pays no slippage at all — if it would cross the book Kraken cancels it, which is
invariant 8's intended behaviour — so the entry is not estimated here and estimating it
would double-count a cost the system does not pay.

**The size it is estimated at: the account's whole balance in the pair's quote
currency.** Engine 9 runs before engine 11 sizes the order, so the size is not yet
known. Invariant 6 forbids allocating more than the quote balance, and slippage does
not fall as size rises, so the whole balance is an **upper bound** on anything engine
11 could approve and the cost gate errs toward refusing. Lead ruling 2026-09-16,
flagged as overturnable by the operator.

**This engine never blocks.** `is_gate = False`, and on every fail-closed shape it
returns `OK`, omits `estimated_slippage_pct`, and publishes a reason code. The refusal
is engine 10's, which is a gate, and it refuses on the absent key. A non-gate that
refused on its own criteria would make `is_gate` wrong — the principle the operator
applied to engine 16. Engine 8's `di_refused` is the one operator-ruled exception,
2026-09-12, and is not a precedent to extend.

**What it does not do.** It does not read `data/`. It does not extrapolate past the
fetched depth. It does not size the order, and it duplicates none of engine 11's
sizing arithmetic — the basis notional is a balance, not a position size, and the two
are different numbers on purpose.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from pydantic import ValidationError

from acsoe.clients.kraken.contracts import coerce_order_book
from acsoe.clients.kraken.errors import KrakenError
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.order_book.contracts import (
    DEPTH_KEY,
    EXCHANGE_BALANCES_KEY,
    EXCHANGE_KEY,
    EXCHANGE_PAIR_RULES_KEY,
    PAIR_QUOTE_FIELD,
    PAIR_RULES_PAIRS_KEY,
    REASON_BOOK_FETCH_FAILED,
    REASON_BOOK_TOO_THIN,
    REASON_BOOK_UNUSABLE,
    REASON_INPUTS_UNAVAILABLE,
    REASON_NO_QUOTE_BALANCE,
    SCOUT_KEY,
    SCOUT_PAIR_FIELD,
    SlippageEstimate,
    walk_the_bid_side,
)
from acsoe.platform.aio import run_blocking


class SetupError(Exception):
    """An input needed before the walk could be set up was absent or unusable.

    Carried as an exception rather than a sentinel so that the one place which turns a
    missing input into a published reason code is also the one place that formats the
    operator sentence. It maps to `OK` with :data:`REASON_INPUTS_UNAVAILABLE`, never to
    a block — this engine is not a gate.
    """


def _require(container: Any, key: str, where: str) -> Any:
    """Fetch `key` out of a published mapping, or say precisely what was missing.

    A `None` is treated exactly like an absent key, the same posture engine 10 takes:
    engine 1 publishing `balances: null` because the `Balance` call failed must not be
    read as an account holding nothing, which would be a different fact with a
    different reason code.
    """
    if not isinstance(container, dict):
        raise SetupError(f"{where} is {type(container).__name__}, expected a mapping")
    if key not in container or container[key] is None:
        raise SetupError(f"{where}.{key}")
    return container[key]


class OrderBookEngine(BaseEngine):
    """Engine 9. Opportunity chain, runtime stage 3, after 8 and before 10."""

    name: ClassVar[str] = "order_book"
    number: ClassVar[int] = 9
    #: The registry table in `context/engine-contracts.md` marks engine 9 with no
    #: Gate. `is_gate_matches_registry` asserts this exact value, and the whole
    #: fail-closed design below depends on it staying `False`.
    is_gate: ClassVar[bool] = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        try:
            depth = self._depth(context)
            pair = str(_require(state.get(SCOUT_KEY), SCOUT_PAIR_FIELD, SCOUT_KEY))
            quote_currency = self._quote_currency(state, pair)
            basis_notional = self._basis_notional(state, quote_currency)
        except SetupError as missing:
            return self._published(
                SlippageEstimate(reason_code=REASON_INPUTS_UNAVAILABLE),
                started,
                f"Slippage was not estimated: {missing}",
            )

        partial = SlippageEstimate(
            pair=pair, depth=depth, quote_currency=quote_currency, reason_code=None
        )

        if basis_notional is None:
            return self._published(
                partial.model_copy(update={"reason_code": REASON_NO_QUOTE_BALANCE}),
                started,
                (
                    f"Slippage was not estimated for {pair}: the account holds no "
                    f"spendable {quote_currency}, so there is no notional to walk"
                ),
            )

        partial = partial.model_copy(update={"basis_notional": basis_notional})

        try:
            book = coerce_order_book(
                run_blocking(context.clients.kraken.order_book(pair, depth))
            )
        except (KrakenError, ValidationError, ValueError) as failure:
            # The client refused. An outage, an unknown pair, a malformed payload, or
            # a side the client's own model would not build — an **empty** side is
            # refused at construction by `OrderBookSnapshot`, deliberately, so that
            # "no book" arrives as a failure rather than as a zero spread. Those
            # cannot be told apart through the client boundary and this does not
            # pretend to; the client's own message goes into the sentence.
            #
            # Anything that is *not* exchange-shaped propagates. Contract rule 7: an
            # engine must not swallow its own exceptions to avoid ERROR, and a defect
            # on this side of the boundary is not a thin book.
            return self._published(
                partial.model_copy(update={"reason_code": REASON_BOOK_FETCH_FAILED}),
                started,
                f"Slippage was not estimated for {pair}: the order book did not "
                f"answer ({failure})",
            )

        unusable = self._unusable(book.bids, book.asks)
        if unusable is not None:
            return self._published(
                partial.model_copy(update={"reason_code": REASON_BOOK_UNUSABLE}),
                started,
                f"Slippage was not estimated for {pair}: {unusable}",
            )

        partial = partial.model_copy(update={"best_bid": book.best_bid})
        walk = walk_the_bid_side(book.bids, basis_notional)
        if walk is None:
            return self._published(
                partial.model_copy(update={"reason_code": REASON_BOOK_TOO_THIN}),
                started,
                (
                    f"Slippage was not estimated for {pair}: {depth} levels of bids "
                    f"cannot absorb {basis_notional:f} {quote_currency}, and an "
                    f"estimate past the fetched depth would be a guess"
                ),
            )

        return self._published(
            partial.model_copy(
                update={
                    "fill_price": walk.fill_price,
                    "levels_consumed": walk.levels_consumed,
                    "estimated_slippage_pct": walk.slippage_pct,
                }
            ),
            started,
            None,
        )

    # ------------------------------------------------------------------ inputs

    def _depth(self, context: EngineContext) -> int:
        """`order_book.depth`, as a positive integer.

        Three failures, told apart rather than conflated, because
        `code-standards.md` makes that the difference between a handler and a guess:
        `Config.get` **raises** on a key this model does not declare, **returns
        `None`** for a declared key the operator left unset, and returns whatever was
        written for a key set to something that is not a count. `ConfigKeyError` is a
        `KeyError` subclass, which is why nothing here imports from `platform/`.

        None of the three defaults to a depth. A depth silently chosen here decides
        how much of the book a slippage estimate is allowed to see, and therefore
        which candidates the cost gate lets through.
        """
        try:
            value = context.config.get(DEPTH_KEY)
        except KeyError as missing:
            raise SetupError(f"config {DEPTH_KEY} is not declared ({missing})") from missing
        if value is None:
            raise SetupError(f"config {DEPTH_KEY} is null (OPERATOR REQUIRED)")
        if isinstance(value, bool) or not isinstance(value, int):
            raise SetupError(f"config {DEPTH_KEY} is not a whole number of levels: {value!r}")
        if value <= 0:
            raise SetupError(f"config {DEPTH_KEY} must be at least one level, not {value}")
        return value

    def _quote_currency(self, state: State, pair: str) -> str:
        """The currency the pair is quoted in, from engine 1's `AssetPairs` snapshot.

        Two levels through :func:`_require`, the same way engine 11 reads it, so a
        failed `AssetPairs` fetch reports as the missing snapshot it is rather than as
        an unknown pair. Invariant 2 gives pair rules no fallback in any mode.
        """
        exchange = state.get(EXCHANGE_KEY)
        pair_rules = _require(exchange, EXCHANGE_PAIR_RULES_KEY, EXCHANGE_KEY)
        rules_where = f"{EXCHANGE_KEY}.{EXCHANGE_PAIR_RULES_KEY}"
        pairs = _require(pair_rules, PAIR_RULES_PAIRS_KEY, rules_where)
        facts = _require(pairs, pair, f"{rules_where}.{PAIR_RULES_PAIRS_KEY}")
        return str(
            _require(
                facts,
                PAIR_QUOTE_FIELD,
                f"{rules_where}.{PAIR_RULES_PAIRS_KEY}.{pair}",
            )
        )

    def _basis_notional(self, state: State, quote_currency: str) -> Decimal | None:
        """The whole spendable balance in `quote_currency`, or `None` when there is none.

        `None` is the "no quote balance" shape and is a fact about the **account**. A
        `balances` map that engine 1 could not fetch is a fact about the **call**, and
        raises :class:`SetupError` instead — an operator acts on those differently, and
        a handler that cannot tell two situations apart will silently pick the wrong
        one.

        **No paper-mode fallback, deliberately, and this differs from engine 11.**
        Engine 11 `risk` falls back to `paper.starting_balances` when engine 1
        published no balances, because it must still size something; engine 9 has
        nothing it must still do, so the conservative reading is to publish no estimate
        and let the gate refuse. Spec 96 step 4 lists it as a fail-closed shape and
        this follows that list verbatim. Recorded in the README as a deliberate
        asymmetry rather than an oversight.

        A currency **missing from a published map** is zero, not a failed fetch: engine
        1 publishes what the account holds, and an asset with no balance is not listed.
        """
        exchange = state.get(EXCHANGE_KEY)
        balances = _require(exchange, EXCHANGE_BALANCES_KEY, EXCHANGE_KEY)
        if not isinstance(balances, dict):
            raise SetupError(
                f"{EXCHANGE_KEY}.{EXCHANGE_BALANCES_KEY} is "
                f"{type(balances).__name__}, expected a mapping"
            )
        held = balances.get(quote_currency)
        if held is None:
            return None
        if isinstance(held, float):
            # Rule 8 of the engine contract: money crosses `state` as an exact decimal
            # string. A float arrived here having already lost precision, and coercing
            # it would launder that loss into a Decimal that looks exact.
            raise SetupError(
                f"{EXCHANGE_KEY}.{EXCHANGE_BALANCES_KEY}.{quote_currency} is a float; "
                f"money crosses state as an exact decimal string"
            )
        try:
            amount = Decimal(str(held))
        except (InvalidOperation, ValueError) as exc:
            raise SetupError(
                f"{EXCHANGE_KEY}.{EXCHANGE_BALANCES_KEY}.{quote_currency} is not a "
                f"number: {held!r}"
            ) from exc
        if not amount.is_finite():
            raise SetupError(
                f"{EXCHANGE_KEY}.{EXCHANGE_BALANCES_KEY}.{quote_currency} is not "
                f"finite: {held!r}"
            )
        return amount if amount > 0 else None

    # ------------------------------------------------------------------ the book

    def _unusable(
        self,
        bids: tuple[tuple[Decimal, Decimal], ...],
        asks: tuple[tuple[Decimal, Decimal], ...],
    ) -> str | None:
        """Why this book cannot be walked, or `None` when it can.

        Every check here is about a book the client **did** return. An empty side
        never reaches this method: `OrderBookSnapshot` refuses one at construction, so
        it arrives as a fetch failure. The emptiness check is kept anyway, as the
        assertion that the client's refusal is the live branch — deleting a guard for
        something that cannot happen throws away the tripwire for the day it can.
        """
        if not bids or not asks:
            return "the book came back with an empty side"
        best_bid, best_ask = bids[0][0], asks[0][0]
        if best_bid <= 0 or best_ask <= 0:
            return f"the top of book is not a positive price (bid {best_bid}, ask {best_ask})"
        if best_bid > best_ask:
            # A crossed book is a feed fault, not a free lunch. Engine 4 `data_guard`
            # blocks the tick on a negative spread; this engine cannot block, so it
            # declines to price the walk and lets engine 10 refuse.
            return f"the book is crossed: best bid {best_bid} is above best ask {best_ask}"
        previous: Decimal | None = None
        for price, quantity in bids:
            if price <= 0:
                return f"a bid level has a non-positive price: {price}"
            if quantity < 0:
                return f"a bid level has a negative quantity: {quantity}"
            if previous is not None and price >= previous:
                # Not merely untidy. The walk takes levels in the order given and calls
                # the first one "best"; an out-of-order side would make the reference
                # price wrong and the slippage measured against it meaningless.
                return f"the bid side is not in descending price order at {price}"
            previous = price
        return None

    # ------------------------------------------------------------------ output

    def _published(
        self, estimate: SlippageEstimate, started: float, reason: str | None
    ) -> EngineResult:
        """Always `OK`, always `blocks_trading=False`. See the module docstring.

        `reason` carries the operator sentence on the fail-closed shapes even though
        nothing blocked, because the contract requires a reason only when
        `blocks_trading` is true and forbids it nowhere — and engine 10's block
        message names the absent key, not why it is absent. The sentence is the only
        place the "why" is written in prose.
        """
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            reason=reason,
            data=estimate.to_state_data(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


__all__ = ["OrderBookEngine", "SetupError"]
