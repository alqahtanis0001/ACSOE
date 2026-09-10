"""The one object an engine sees as ``context.clients.kraken``.

``Clients`` names exactly three members and ``kraken`` is one of them, so the REST
calls and the market stream have to arrive as a single object. This is that object
and it is deliberately thin: it holds the two transports and forwards. No logic
lives here, because logic here would be logic no engine test could reach.

It satisfies both ``KrakenClientProtocol`` and ``MarketStreamProtocol``, which is
what lets engine 1 take the first and engines 2 and 3 take the second without any
of them knowing the other half exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from acsoe.clients.kraken.contracts import (
    BalancesSnapshot,
    FeeTierSnapshot,
    OrderBookSnapshot,
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

    def latest_quote(self, pair: str) -> QuoteTick | None:
        return self._stream.latest_quote(pair)

    @property
    def connected(self) -> bool:
        return self._stream.connected

    @property
    def gaps(self) -> tuple[Mapping[str, Any], ...]:
        return self._stream.gaps
