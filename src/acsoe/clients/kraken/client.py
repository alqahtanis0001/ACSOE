"""The one object an engine sees as ``context.clients.kraken``.

``Clients`` names exactly three members and ``kraken`` is one of them, so the REST
calls and the market stream have to arrive as a single object. This is that object
and it is deliberately thin: it holds the two transports and forwards. No logic
lives here, because logic here would be logic no engine test could reach.

It satisfies ``KrakenClientProtocol``, ``MarketStreamProtocol`` and — since spec
84 — ``OrderClientProtocol``, which is what lets engine 1 take the first, engines
2 and 3 the second and engines 18, 21 and 22 the third, without any of them
knowing the others exist. The order half **refuses** here until Phase 8; paper
mode reaches it through B's broker, which wraps this object.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from acsoe.clients.kraken.contracts import (
    BalancesSnapshot,
    FeeTierSnapshot,
    OrderAck,
    OrderBookSnapshot,
    OrderRequest,
    OrderState,
    PairRulesSnapshot,
    QuoteTick,
    RawFrame,
    RetainedValue,
    TradeTick,
)
from acsoe.clients.kraken.rest import KrakenRestClient
from acsoe.clients.kraken.ws import KrakenWebSocketClient

__all__ = ["KrakenClient"]


class KrakenClient:
    """REST plus stream, forwarded."""

    def __init__(self, *, rest: KrakenRestClient, stream: KrakenWebSocketClient) -> None:
        self._rest = rest
        self._stream = stream

    # -- lifecycle -------------------------------------------------------- #

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    # -- REST ------------------------------------------------------------- #

    async def asset_pairs(self) -> PairRulesSnapshot:
        return await self._rest.asset_pairs()

    async def trade_volume(self) -> FeeTierSnapshot:
        return await self._rest.trade_volume()

    async def balance(self) -> BalancesSnapshot:
        return await self._rest.balance()

    async def order_book(self, pair: str, depth: int = 10) -> OrderBookSnapshot:
        return await self._rest.order_book(pair, depth)

    @property
    def last_known_good_asset_pairs(self) -> RetainedValue | None:
        return self._rest.last_known_good_asset_pairs

    @property
    def last_known_good_balances(self) -> RetainedValue | None:
        return self._rest.last_known_good_balances

    # -- orders ----------------------------------------------------------- #
    #
    # Forwarded, exactly like the four read calls, so the refusal lives in one
    # place. `rest.py` is where the Phase 8 refusal is written and this facade must
    # not grow a second copy of it: two refusals is two things to remove in Phase 8
    # and one of them would be missed.
    #
    # In paper mode B's broker wraps *this* object and answers these four itself,
    # so the forward below is never reached; in live mode it is reached and it
    # raises. There is no mode in which it places an order.

    async def add_order(self, request: OrderRequest) -> OrderAck:
        return await self._rest.add_order(request)

    async def cancel_order(self, userref: int) -> OrderState:
        return await self._rest.cancel_order(userref)

    async def query_orders(self, userrefs: Sequence[int]) -> tuple[OrderState, ...]:
        return await self._rest.query_orders(userrefs)

    async def open_orders(self) -> tuple[OrderState, ...]:
        return await self._rest.open_orders()

    # -- stream ----------------------------------------------------------- #

    def set_subscription(self, pairs: Sequence[str]) -> bool:
        """Forwarded so engine 2 can move the scope without knowing about `ws.py`."""
        return self._stream.set_subscription(pairs)

    @property
    def subscription(self) -> tuple[str, ...]:
        return self._stream.subscription

    def drain(self) -> tuple[RawFrame, ...]:
        return self._stream.drain()

    def drain_trades(self) -> tuple[TradeTick, ...]:
        return self._stream.drain_trades()

    def recent_trades(self) -> tuple[TradeTick, ...]:
        """The buffered window, **not** consumed. What engine 3 reads every tick.

        Forwarded for the same reason as `drain_trades`, and its absence here was F1 of
        the Phase 7 live-path findings: engine 3 guards the call with `getattr` and
        publishes `stream_available: false` when it is missing, so live and paper the
        chain saw no candles, no quotes and no trade ranges — and the paper broker, which
        needs the window to decide whether a resting entry filled, raised on every tick.
        """
        return self._stream.recent_trades()

    def drain_gaps(self) -> tuple[Mapping[str, Any], ...]:
        """Every break recorded since the last call. Consuming, as engine 2 expects.

        The same omission as `recent_trades` and quieter: engine 2 guards it with
        `getattr` too, so a facade without it records **zero gaps** and the archive reads
        as continuous across every reconnect, which is what invariant 11 is about.
        """
        return self._stream.drain_gaps()

    def latest_quote(self, pair: str) -> QuoteTick | None:
        return self._stream.latest_quote(pair)

    @property
    def connected(self) -> bool:
        return self._stream.connected

    @property
    def gaps(self) -> tuple[Mapping[str, Any], ...]:
        return self._stream.gaps
