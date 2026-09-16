"""The paper broker: `context.clients.kraken` in paper mode.

Operator ruling, 2026-09-16. The fill simulator is **a client, not an engine**, and it
lives here rather than under `engines/execution/` because a resting post-only entry fills
on a later tick that only engine 21 sees, and contract rule 3 forbids engine 21 importing
engine 18. The correction is the operator's own; the earlier ruling is superseded.

It wraps the real :class:`~acsoe.clients.kraken.client.KrakenClient`, forwards every
read and every stream call to it untouched, and answers the four order calls itself.
Engines 18, 21 and 22 call `context.clients.kraken.add_order / cancel_order /
query_orders / open_orders` identically in every mode and never learn which object they
hold — which is the property that makes a paper run and a live run the same code path
rather than two.

## What it never does

**No transport call from any order method, in any mode.** Spec 88's first scope limit.
The real client's order methods refuse until Phase 8 and this object never reaches them:
`self._real` is used for reads and the stream only, and a test reads this module's source
to prove the four names do not appear against it.

**No relational write.** Engine 19 `memory` is the single writer of every table. This
object reads `orders` and nothing else, and it holds what it accepted this tick only
until engine 19 has recorded it.

## The two pieces of state, and why each is the shape it is

**Resting orders are the store's rows.** Spec 88 step 2. An in-memory book would be lost
by a restart and the system would then hold a position whose entry order it had forgotten
— the exact failure invariant 8's `userref` idempotency exists to prevent. So the broker
asks the store what is resting, every time, and `_pending` holds only what it accepted on
*this* tick, before engine 19 has written it.

**Observed trades are per-process, and a restart loses them.** They cannot be anything
else: the stream itself is per-process. The consequence is stated rather than hidden — a
resting entry that "should" have filled during the gap does not fill after a restart, and
waits for the next trade below its limit or for engine 21's unfilled window to cancel it.
That is the pessimistic direction, which is the only direction a simulator may err in.

## Where the trades come from

A client cannot read `state`, so it cannot read engine 3's `trade_ranges` (spec 85). It
does not need to: it reads the same source engine 3 reads, `recent_trades()` on the
stream, so the two cannot disagree about which trades happened.

**Spec 88 says engine 3 *drains*, and it does not.** `engines/market_sensor/engine.py`
calls `recent_trades()`, which `ws.py` documents as a rolling window that deliberately
does **not** clear, because engine 3 rebuilds the same 15-minute bar on each of the
fifteen ticks that bar spans and an engine is stateless across cycles. `drain_trades()`
exists on the client and in A's protocol and nothing in `src/` calls it. The spec's
conclusion holds and its mechanism does not, which is why this broker keeps no
observation buffer and no tick boundary: reading is non-destructive, so there is nothing
for two readers to race over. Seeing one trade repeatedly cannot double-fill — the order
fills once and is terminal after that — and every candidate is still filtered to
`ts > placed_at`. Build log, 2026-09-16.

**The window is bounded by count, not by time.** `max_buffered_trades`, again `ws.py`'s
own wording. A resting entry older than that window cannot see the trade that would have
filled it, so on a very busy pair an entry may go unfilled that a real exchange would
have filled. Engine 21 cancels an entry at `trading.entry_unfilled_window_s`, which
bounds it, and the direction is pessimistic — but the two windows have never been checked
against each other and should be.

## Fees

Taken from the fee tier the real client returns **on the tick the fill is priced**, maker
on a post-only fill and taker on a market fill. There is no fallback. If `TradeVolume`
gives nothing, a fill cannot be priced and :class:`PaperBrokerError` is raised naming the
call — spec 88's scope limit says to escalate rather than choose a rate, and spec 93 says
the same thing from the liquidation side. `AGENTS.md` forbids a remembered fee in its
first paragraph.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from acsoe.clients.kraken.contracts import (
    TERMINAL_ORDER_STATUSES,
    BalancesSnapshot,
    OrderAck,
    OrderAckStatus,
    OrderRequest,
    OrderSide,
    OrderState,
    OrderStatus,
    OrderType,
    TradeTick,
    coerce_fee_tier,
    to_micros,
)
from acsoe.clients.paper.fills import (
    apply_fill_to_ledger,
    fee_on,
    post_only_would_cross,
    resting_buy_fill_price,
    walk_bids,
)
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import OrderIntent, OrderRow
from acsoe.clients.store.contracts import OrderStatus as RowStatus
from acsoe.platform.clock import Clock

__all__ = ["FALLBACK_PAPER_LEDGER", "PaperBroker", "PaperBrokerError"]

#: The depth the broker fetches when it has to walk the book for a market sell. It is the
#: same default the real client uses, so the simulated sweep sees exactly the book a live
#: sweep's caller would have seen and no more.
_BOOK_DEPTH = 10

#: Recorded on a fill priced against the paper ledger rather than a fetched balance. The
#: ledger is *always* the balance in paper mode (operator ruling 3, 2026-09-16), so this
#: is a statement of provenance rather than of failure, and invariant 2 requires the
#: decision to carry it either way.
FALLBACK_PAPER_LEDGER = "balance_from_paper_ledger"

#: The opening balance the ledger adjusts. Invariant 2's one substituted value, and
#: operator ruling 3 of 2026-09-16 makes it paper mode's balance outright rather than a
#: fallback for a failed fetch.
#:
#: **It is the only config key this broker reads.** An earlier draft also read
#: `trading.entry_unfilled_window_s`, to bound an observation buffer that no longer
#: exists — the buffer went when `recent_trades()` turned out to be the seam rather than
#: `drain_trades()`, and the key went with it rather than staying as a read nothing uses.
PAPER_STARTING_BALANCES_KEY = "paper.starting_balances"


class ConfigReader(Protocol):
    """The two config keys this broker reads, through the dotted accessor.

    Typed as a Protocol rather than as `platform.config.Config` on purpose. The daemon
    passes a `Config`; a test passes the harness's `MappingConfig`, which wraps
    `config/default.yaml` verbatim **including its nulls** and is deliberately not a
    `Config`. Naming the concrete class here would make every test either construct a
    validated config it does not need or lie about the type, and the broker uses exactly
    one method of it.
    """

    def get(self, dotted_key: str, /) -> Any: ...


class PaperBrokerError(RuntimeError):
    """The simulator cannot answer honestly, so it refuses.

    Never returned as an empty result. Invariant 3: the absence of a "no" is never a
    "yes", and A's `OrderClientProtocol` says the same thing about this surface — an
    `open_orders` answering `()` during an outage would tell engine 21 there was nothing
    resting to cancel.
    """


class _Pending:
    """One order accepted this tick, before engine 19 has written its row.

    Deliberately not a store row and deliberately short-lived. It exists only because
    engine 18 places an order and engine 19 records it later in the same tick, so between
    those two moments the store does not know about an order the system has placed.
    """

    __slots__ = ("fee", "fill_price", "filled_qty", "placed_at", "request", "status")

    def __init__(
        self,
        *,
        request: OrderRequest,
        status: OrderStatus,
        placed_at: int,
        filled_qty: Decimal,
        fill_price: Decimal | None,
        fee: Decimal,
    ) -> None:
        self.request = request
        self.status = status
        self.placed_at = placed_at
        self.filled_qty = filled_qty
        self.fill_price = fill_price
        self.fee = fee


class PaperBroker:
    """Reads and the stream forwarded; the four order calls simulated.

    `real` is typed `Any` for the reason A's `coerce_*` functions are: the object is
    genuinely structural. In the daemon it is `KrakenClient`; in a test it is C's
    `tests/harness/fake_kraken.py`, which is an independently-owned class that may not
    import this one. A Protocol here would restate A's `KrakenClientProtocol` and
    `MarketStreamProtocol` a third time and would still not cover the retention
    properties, which are plain attributes.
    """

    def __init__(
        self, real: Any, *, store: StoreClient, config: ConfigReader, clock: Clock
    ) -> None:
        self._real = real
        self._store = store
        self._config = config
        self._clock = clock
        # The only mutable state, and it is deliberately tiny: orders accepted on this
        # tick that engine 19 has not written yet. Everything else the broker knows it
        # asks the store or the stream for, every time, so a restart loses nothing it
        # was relying on.
        self._pending: dict[int, _Pending] = {}

    # ------------------------------------------------------------------ time

    def _now(self) -> int:
        """The injected clock, in microseconds. Invariant 9: never a direct read."""
        return to_micros(self._clock.now())

    # --------------------------------------------------------- forwarded reads
    #
    # Every one of these is `self._real`'s answer, unchanged. The broker adds no
    # fallback of its own to any of them: invariant 2 gives pair rules, the spread and
    # the fee tier none, and the one row of that table that does substitute a value is
    # the balance, which is below and is not a fallback here but the ruled behaviour.

    async def asset_pairs(self) -> Any:
        return await self._real.asset_pairs()

    async def trade_volume(self) -> Any:
        return await self._real.trade_volume()

    async def order_book(self, pair: str, depth: int = _BOOK_DEPTH) -> Any:
        return await self._real.order_book(pair, depth)

    @property
    def last_known_good_asset_pairs(self) -> Any:
        return self._real.last_known_good_asset_pairs

    @property
    def last_known_good_balances(self) -> Any:
        return self._real.last_known_good_balances

    # --------------------------------------------------------- forwarded stream

    def start(self) -> None:
        self._real.start()

    def stop(self) -> None:
        self._real.stop()

    def set_subscription(self, pairs: Sequence[str]) -> bool:
        result: bool = self._real.set_subscription(pairs)
        return result

    @property
    def subscription(self) -> tuple[str, ...]:
        subscription: tuple[str, ...] = self._real.subscription
        return subscription

    def drain(self) -> Any:
        return self._real.drain()

    def latest_quote(self, pair: str) -> Any:
        return self._real.latest_quote(pair)

    @property
    def connected(self) -> bool:
        connected: bool = self._real.connected
        return connected

    @property
    def gaps(self) -> Any:
        return self._real.gaps

    def drain_trades(self) -> tuple[TradeTick, ...]:
        """Forwarded untouched. **The broker never calls this itself.**

        Draining clears the buffer. Nothing in `src/` calls it today and the broker reads
        `recent_trades()` instead, so this exists only so the paper object presents the
        same surface as the real one and a caller that appears later is not silently
        missing a method it would have had in live mode.
        """
        trades: tuple[TradeTick, ...] = self._real.drain_trades()
        return trades

    def recent_trades(self) -> tuple[TradeTick, ...]:
        """Forwarded untouched — the same rolling window engine 3 reads.

        Not copied, not filtered and not cached. Engine 3 and the broker have to agree
        about which trades happened, and the only way to guarantee that is for both to
        read one source; a cache here would be a second answer that drifts.
        """
        trades: tuple[TradeTick, ...] = self._real.recent_trades()
        return trades

    def _trade_prices_after(self, pair: str, placed_at: int) -> tuple[Decimal, ...]:
        """Prices printed on `pair` strictly after `placed_at`, oldest first.

        Strictly after, because engine 18 places in the opportunity chain and engine 3
        has already read the window in the guard chain of the same tick. A trade the
        broker can see now but which printed before the order existed would fill it on
        the past — invariant 10's look-ahead, arriving through the simulator rather than
        through a feature.
        """
        recent = getattr(self._real, "recent_trades", None)
        if not callable(recent):
            raise PaperBrokerError(
                "the wrapped client has no `recent_trades`, so the simulator cannot see "
                "which trades happened and cannot decide whether anything filled"
            )
        return tuple(
            Decimal(trade.price)
            for trade in recent()
            if str(trade.pair) == pair and to_micros(trade.ts) > placed_at
        )

    # ------------------------------------------------------------- the ledger

    async def balance(self) -> BalancesSnapshot:
        """`paper.starting_balances` adjusted by every recorded fill.

        **Operator ruling 3, 2026-09-16: in paper mode this is always the balance**,
        whether or not the real `Balance` call works, because no simulated fill spends
        the real account. Recorded in planning as a defect the invariant had promised and
        nothing implemented: engine 11 was sizing against cash an earlier paper fill had
        already spent, and engine 19's equity counted that cash twice.

        The real call is therefore never made here. That is not an optimisation — calling
        it and then discarding the answer would leave a private endpoint in the paper path
        whose result nothing uses, and the first person to "fix" the unused value would
        reintroduce the double count.

        Money is read out of the store as exact decimal strings and summed as `Decimal`.
        **Never `SUM()` in SQL**: money columns are TEXT, so SQLite would sum them
        lexicographically or coerce them to floats, and `code-standards.md` forbids it.
        """
        quotes = await self._quote_currencies()
        balances = self._starting_balances()
        for row in self._filled_orders():
            price = row.avg_fill_price
            if price is None:
                # `OrderState` refuses this shape at its own boundary, so a row like it in
                # the store came from somewhere else. A fill with no price cannot be
                # valued and must not reach the ledger as a zero.
                raise PaperBrokerError(
                    f"order {row.userref} is filled with no avg_fill_price; a fill "
                    "without a price cannot be valued"
                )
            quote = quotes.get(row.pair)
            if quote is None:
                raise PaperBrokerError(
                    f"no pair rules for {row.pair}, so the ledger cannot tell which "
                    "currency its fills spent; AssetPairs has no fallback (invariant 2)"
                )
            balances = apply_fill_to_ledger(
                balances,
                quote=quote,
                is_entry=row.intent is OrderIntent.ENTRY,
                filled_qty=row.filled_qty,
                fill_price=price,
                fee=row.fee if row.fee is not None else Decimal(0),
            )
        return BalancesSnapshot(balances=balances, fetched_at=self._now())

    def _starting_balances(self) -> dict[str, Decimal]:
        """`paper.starting_balances` as exact `Decimal`, refusing anything else.

        The conversion goes through `repr` for a float, which gives the shortest string
        that round-trips. A YAML scalar written unquoted as `5000.00` parses to a Python
        float and `Decimal(5000.00)` is not `5000.00` — the committed config quotes its
        amounts, and this is what stops that staying true by luck.
        """
        raw = self._config.get(PAPER_STARTING_BALANCES_KEY)
        if not isinstance(raw, Mapping) or not raw:
            raise PaperBrokerError(
                f"config {PAPER_STARTING_BALANCES_KEY} is not a currency-to-amount map; "
                "the paper ledger has no opening balance to adjust"
            )
        balances: dict[str, Decimal] = {}
        for code, amount in raw.items():
            try:
                balances[str(code)] = Decimal(
                    repr(amount) if isinstance(amount, float) else str(amount)
                )
            except (InvalidOperation, ValueError) as exc:
                raise PaperBrokerError(
                    f"config {PAPER_STARTING_BALANCES_KEY}[{code}] is not a number: "
                    f"{amount!r}"
                ) from exc
        return balances

    def _filled_orders(self) -> tuple[OrderRow, ...]:
        """Every order the store has recorded as filled, entry and exit alike.

        Read through the store's own surface rather than by SQL here: this module writes
        no row and issues no query of its own, so there is one place that knows the
        schema and it is not this one.
        """
        return tuple(row for row in self._store.filled_orders() if row.filled_qty > 0)

    async def _quote_currencies(self) -> dict[str, str]:
        """`pair` to quote currency, from `AssetPairs`.

        Never from splitting the pair name. `OrderRow` carries no quote column and a
        Kraken pair name is not reliably `BASE/QUOTE` — `XBTUSD` is the counter-example
        the lead already ruled on from the other side.
        """
        snapshot = await self._real.asset_pairs()
        return {str(name): str(rule.quote) for name, rule in dict(snapshot.pairs).items()}

    # -------------------------------------------------------------- the orders

    async def add_order(self, request: OrderRequest) -> OrderAck:
        """Accept, reject or fill one order. **No transport call, in any mode.**"""
        if self._lookup(request.userref) is not None:
            # Invariant 8 makes `userref` the idempotency token, and a second placement
            # under one is a defect rather than a retry: the engine is required to check
            # first. Refusing rather than silently returning the old ack means the defect
            # surfaces where it happened.
            raise PaperBrokerError(
                f"userref {request.userref} has already been placed; invariant 8 requires "
                "the caller to check before placing, and a second placement under one "
                "userref is a defect, not a retry"
            )

        if request.order_type is OrderType.MARKET:
            return await self._fill_market(request)
        if not request.post_only:
            raise PaperBrokerError(
                "a limit order that is not post-only is not simulated: this system places "
                "post-only entries (invariant 8) and taker exits (invariant 14), and a "
                "third behaviour here would be a capability nothing asked for"
            )
        return await self._rest_post_only(request)

    async def _rest_post_only(self, request: OrderRequest) -> OrderAck:
        """A post-only buy: rejected if it would cross, otherwise resting."""
        if request.side is not OrderSide.BUY:
            raise PaperBrokerError(
                "the only post-only order this system places is an entry, and every "
                f"entry is a buy; got {request.side}"
            )
        book = await self._real.order_book(request.pair, _BOOK_DEPTH)
        limit = request.limit_price
        if limit is None:  # pragma: no cover - OrderRequest refuses this shape
            raise PaperBrokerError("a limit order with no limit price has nothing to rest at")
        if post_only_would_cross(limit_price=limit, best_ask=Decimal(book.best_ask)):
            return OrderAck(
                userref=request.userref,
                order_id=self._order_id(request.userref),
                status=OrderAckStatus.REJECTED,
                reason=(
                    f"post-only buy at {limit} is at or above the best ask "
                    f"{book.best_ask} and would take liquidity; Kraken cancels such an "
                    "order and so does the simulator"
                ),
            )
        self._pending[request.userref] = _Pending(
            request=request,
            status=OrderStatus.RESTING,
            placed_at=self._now(),
            filled_qty=Decimal(0),
            fill_price=None,
            fee=Decimal(0),
        )
        return OrderAck(
            userref=request.userref,
            order_id=self._order_id(request.userref),
            status=OrderAckStatus.RESTING,
        )

    async def _fill_market(self, request: OrderRequest) -> OrderAck:
        """A market sell, walked down the bid side of the book fetched this tick."""
        if request.side is not OrderSide.SELL:
            raise PaperBrokerError(
                "the only market order this system places is a taker exit, and every "
                f"exit is a sell; got {request.side}"
            )
        book = await self._real.order_book(request.pair, _BOOK_DEPTH)
        levels = tuple((Decimal(price), Decimal(volume)) for price, volume in book.bids)
        walk = walk_bids(levels=levels, qty=request.qty)
        fee = fee_on(
            notional=walk.avg_price * walk.filled_qty, rate=await self._taker_rate()
        )
        self._pending[request.userref] = _Pending(
            request=request,
            status=OrderStatus.FILLED,
            placed_at=self._now(),
            filled_qty=walk.filled_qty,
            fill_price=walk.avg_price,
            fee=fee,
        )
        return OrderAck(
            userref=request.userref,
            order_id=self._order_id(request.userref),
            status=OrderAckStatus.FILLED,
        )

    async def cancel_order(self, userref: int) -> OrderState:
        """Cancel a resting order. Terminal orders are returned as they stand."""
        known = self._lookup(userref)
        if known is None:
            raise PaperBrokerError(
                f"no order with userref {userref}; a cancel that found nothing is not a "
                "cancel that succeeded (invariant 3)"
            )
        state = await self._state_of(known)
        if state.status in TERMINAL_ORDER_STATUSES:
            return state
        return OrderState(
            userref=userref,
            order_id=self._order_id(userref),
            status=OrderStatus.CANCELLED,
            filled_qty=Decimal(0),
            fee=Decimal(0),
            closed_at=self._now(),
        )

    async def query_orders(self, userrefs: Sequence[int]) -> tuple[OrderState, ...]:
        """Where each order stands, **including a fill that happened since**."""
        states: list[OrderState] = []
        for userref in userrefs:
            known = self._lookup(int(userref))
            if known is None:
                raise PaperBrokerError(
                    f"no order with userref {userref}; an unknown order must not come "
                    "back as an absence of news (invariant 3)"
                )
            states.append(await self._state_of(known))
        return tuple(states)

    async def open_orders(self) -> tuple[OrderState, ...]:
        """Everything still resting, through the same path `query_orders` uses.

        One code path deliberately. Two readings of "is this order still open" is the
        shape where a cancel loop and a fill check disagree, and engine 21 runs both on
        one tick.
        """
        resting = self._store.resting_orders()
        states = await self.query_orders([row.userref for row in resting])
        return tuple(
            state for state in states if state.status not in TERMINAL_ORDER_STATUSES
        )

    # ------------------------------------------------------------- resolution

    def _order_id(self, userref: int) -> str:
        """The exchange's identifier, which in paper mode is derived, not minted.

        Derived from the `userref` so it is the same string every time the same order is
        described. A counter or a UUID would give one order two ids across a restart, and
        `order_id` is what reconciliation joins on.
        """
        return f"paper-{userref}"

    def _lookup(self, userref: int) -> _Pending | OrderRow | None:
        """This tick's placement, or the store's row, or nothing.

        **The store wins whenever it has the row**, because engine 19 is the record and
        `_pending` is only the gap between placing an order and recording it. Within one
        tick `_pending` is the only thing that knows; after engine 19 writes, it is a
        stale duplicate and is dropped.
        """
        recorded = self._store.order_by_userref(userref)
        if recorded is not None:
            # Engine 19 has written it, so `_pending`'s copy is now a second answer to a
            # question with one right answer. Dropped here rather than at a tick
            # boundary: see the build log of 2026-09-16 — the drain that was going to be
            # the tick boundary turned out to be a method nothing calls.
            self._pending.pop(userref, None)
            return recorded
        return self._pending.get(userref)

    async def _state_of(self, known: _Pending | OrderRow) -> OrderState:
        """One order's current state, resolving a resting entry's fill.

        This is where the fill rule is actually applied: everything else routes here, so
        `query_orders`, `open_orders` and `cancel_order` cannot disagree about whether an
        order has filled.
        """
        if isinstance(known, _Pending):
            return await self._state_of_pending(known)
        return await self._state_of_row(known)

    async def _state_of_pending(self, pending: _Pending) -> OrderState:
        if pending.status is OrderStatus.FILLED:
            return OrderState(
                userref=pending.request.userref,
                order_id=self._order_id(pending.request.userref),
                status=OrderStatus.FILLED,
                filled_qty=pending.filled_qty,
                avg_fill_price=pending.fill_price,
                fee=pending.fee,
                closed_at=pending.placed_at,
            )
        return await self._resolve_resting(
            userref=pending.request.userref,
            pair=pending.request.pair,
            qty=pending.request.qty,
            limit_price=pending.request.limit_price,
            placed_at=pending.placed_at,
        )

    async def _state_of_row(self, row: OrderRow) -> OrderState:
        if row.status is not RowStatus.RESTING:
            return self._terminal_state_of_row(row)
        return await self._resolve_resting(
            userref=row.userref,
            pair=row.pair,
            qty=row.qty,
            limit_price=row.limit_price,
            placed_at=row.placed_at,
        )

    def _terminal_state_of_row(self, row: OrderRow) -> OrderState:
        """A recorded order that is already over, restated in A's shape.

        `pending` is the one recorded status that is not terminal and not resting. It
        means engine 19 wrote the row before the ack came back, which nothing in this
        system does, so it is refused rather than mapped to something plausible.
        """
        if row.status is RowStatus.PENDING:
            raise PaperBrokerError(
                f"order {row.userref} is recorded as pending, which no engine writes; "
                "the simulator will not guess whether it rested or filled"
            )
        filled = row.filled_qty > 0
        return OrderState(
            userref=row.userref,
            order_id=row.order_id or self._order_id(row.userref),
            status=OrderStatus(str(row.status)),
            filled_qty=row.filled_qty,
            avg_fill_price=row.avg_fill_price if filled else None,
            fee=(row.fee or Decimal(0)) if filled else Decimal(0),
            closed_at=row.closed_at if row.closed_at is not None else self._now(),
        )

    async def _resolve_resting(
        self,
        *,
        userref: int,
        pair: str,
        qty: Decimal,
        limit_price: Decimal | None,
        placed_at: int,
    ) -> OrderState:
        """Has this resting buy filled yet?

        Only trades observed **after** `placed_at` are considered. Engine 18 places after
        engine 3 has drained on the same tick, so a trade the broker saw earlier in this
        tick happened before the order existed and filling on it would be look-ahead —
        invariant 10, arriving through the simulator rather than through a feature.
        """
        if limit_price is None:
            raise PaperBrokerError(
                f"resting order {userref} has no limit price, so there is nothing for a "
                "trade to print below"
            )
        prices = self._trade_prices_after(pair, placed_at)
        fill_price = resting_buy_fill_price(limit_price=limit_price, trade_prices=prices)
        if fill_price is None:
            return OrderState(
                userref=userref,
                order_id=self._order_id(userref),
                status=OrderStatus.RESTING,
                filled_qty=Decimal(0),
                fee=Decimal(0),
            )
        return OrderState(
            userref=userref,
            order_id=self._order_id(userref),
            status=OrderStatus.FILLED,
            filled_qty=qty,
            avg_fill_price=fill_price,
            fee=fee_on(notional=fill_price * qty, rate=await self._maker_rate()),
            closed_at=self._now(),
        )

    # ----------------------------------------------------------------- fees

    async def _maker_rate(self) -> Decimal:
        """The maker rate, through `coerce_fee_tier` so the fake and the real client
        pass the same ratio validator — `0.22` instead of `0.0022` is refused at this
        boundary rather than becoming a fee a hundred times too large."""
        return coerce_fee_tier(await self._fee_tier()).maker_fee_pct

    async def _taker_rate(self) -> Decimal:
        return coerce_fee_tier(await self._fee_tier()).taker_fee_pct

    async def _fee_tier(self) -> Any:
        """This tick's fee tier, or a refusal. **Never a remembered rate.**

        Spec 88's scope limit and spec 93's say the same thing from either side: if a fill
        needs a fee and no tier is available — a liquidation during an outage is the case
        that matters — **stop and escalate, do not choose one.** So this raises, and the
        caller's caller decides. `AGENTS.md`'s first paragraph forbids the alternative and
        invariant 2 retired the one row of its table that ever named a tier.
        """
        try:
            tier = await self._real.trade_volume()
        except Exception as exc:
            raise PaperBrokerError(
                "no fee tier is available, so this fill cannot be priced. Inventing a "
                "rate is forbidden (AGENTS.md, invariant 2); escalate to the operator "
                f"with the options rather than choosing one. Cause: {exc}"
            ) from exc
        if tier is None:
            raise PaperBrokerError(
                "the fee tier fetch returned nothing, so this fill cannot be priced; "
                "escalate rather than assume a rate"
            )
        return tier
