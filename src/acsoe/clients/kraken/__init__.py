"""Kraken REST and WebSocket clients, and the shared rate limiter.

The system's only route to the exchange. No engine opens a socket; everything goes
through here, and everything the exchange can tell us is fetched through here at
runtime rather than remembered.

``tests/harness/fake_kraken.py`` imports the three error types from this module and
falls back to its own definitions only while they do not exist, so the fake raises
exactly what the real client raises.
"""

from acsoe.clients.kraken.client import KrakenClient
from acsoe.clients.kraken.contracts import (
    BalancesSnapshot,
    FeeTierSnapshot,
    KrakenClientProtocol,
    MarketStreamProtocol,
    OrderBookSnapshot,
    PairRule,
    PairRulesSnapshot,
    QuoteTick,
    RawFrame,
    RetainedValue,
    StreamChannel,
    TradeTick,
    money_text,
    to_micros,
)
from acsoe.clients.kraken.errors import KrakenAPIError, KrakenError, KrakenUnavailableError
from acsoe.clients.kraken.limiter import RateLimiter
from acsoe.clients.kraken.rest import KrakenRestClient, parse_envelope
from acsoe.clients.kraken.ws import KrakenWebSocketClient

__all__ = [
    "BalancesSnapshot",
    "FeeTierSnapshot",
    "KrakenAPIError",
    "KrakenClient",
    "KrakenClientProtocol",
    "KrakenError",
    "KrakenRestClient",
    "KrakenUnavailableError",
    "KrakenWebSocketClient",
    "MarketStreamProtocol",
    "OrderBookSnapshot",
    "PairRule",
    "PairRulesSnapshot",
    "QuoteTick",
    "RateLimiter",
    "RawFrame",
    "RetainedValue",
    "StreamChannel",
    "TradeTick",
    "money_text",
    "parse_envelope",
    "to_micros",
]
