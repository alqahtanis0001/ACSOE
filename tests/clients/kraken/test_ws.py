"""Spec 25 — the WebSocket v2 client: buffering, parsing, and gaps.

The socket is injected, so every one of these runs offline with the network guard
armed exactly as strict as it is everywhere else.

The property worth stating out loud is the one about **leniency**: a frame is
recorded verbatim whether or not the trade and quote parsers understand it. If
Kraken renames a field, the archive stays correct and complete — which is the half
that cannot be recovered later — and candles simply stop building, which engine 4
turns into a block. A strict parser would throw away the irreplaceable half.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from acsoe.clients.kraken import KrakenWebSocketClient, StreamChannel
from acsoe.clients.kraken.ws import subscriptions

START = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


class SteppingClock:
    """Advances one second per read, so a gap has a measurable length."""

    def __init__(self, start: datetime = START, step_s: float = 1.0) -> None:
        self._now = start
        self._step = timedelta(seconds=step_s)

    def now(self) -> datetime:
        moment = self._now
        self._now = self._now + self._step
        return moment


class StillClock:
    def __init__(self, at: datetime = START) -> None:
        self._at = at

    def now(self) -> datetime:
        return self._at


def trade_frame(pair: str, price: str, qty: str, ts: str) -> str:
    return json.dumps(
        {
            "channel": "trade",
            "type": "update",
            "data": [{"symbol": pair, "price": price, "qty": qty, "timestamp": ts}],
        }
    )


def ticker_frame(pair: str, bid: str, ask: str, ts: str) -> str:
    return json.dumps(
        {
            "channel": "ticker",
            "type": "update",
            "data": [{"symbol": pair, "bid": bid, "ask": ask, "timestamp": ts}],
        }
    )


def build(clock: Any = None, **kwargs: Any) -> KrakenWebSocketClient:
    return KrakenWebSocketClient(
        clock=clock or StillClock(),
        pairs=["BTC/USD"],
        connect=lambda *a, **k: None,  # never used by the ingest-only tests
        jitter=lambda: 0.0,
        backoff_initial_s=0.001,
        backoff_max_s=0.001,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Subscriptions
# --------------------------------------------------------------------------- #


def test_only_the_book_subscription_carries_a_depth() -> None:
    subs = subscriptions([StreamChannel.BOOK, StreamChannel.TRADE], ["BTC/USD"], 10)
    assert subs[0]["params"]["depth"] == 10
    assert "depth" not in subs[1]["params"]


# --------------------------------------------------------------------------- #
# Buffering and parsing
# --------------------------------------------------------------------------- #


def test_a_trade_frame_yields_a_tick_and_the_frame_is_kept_verbatim() -> None:
    client = build()
    client.ingest(trade_frame("BTC/USD", "50000.1", "0.25", "2026-03-01T12:00:00.000000Z"))

    trades = client.drain_trades()
    assert len(trades) == 1
    assert trades[0].price == Decimal("50000.1")
    assert trades[0].qty == Decimal("0.25")
    assert trades[0].pair == "BTC/USD"

    frames = client.drain()
    assert len(frames) == 1
    assert frames[0].channel == "trade"
    assert frames[0].payload["data"][0]["price"] == "50000.1"


def test_draining_empties_the_buffer_so_a_tick_never_sees_a_frame_twice() -> None:
    client = build()
    client.ingest(trade_frame("BTC/USD", "1", "1", "2026-03-01T12:00:00Z"))
    assert len(client.drain()) == 1
    assert client.drain() == ()


def test_a_ticker_frame_becomes_the_latest_quote_and_absent_stays_absent() -> None:
    client = build()
    assert client.latest_quote("BTC/USD") is None
    client.ingest(ticker_frame("BTC/USD", "50000.0", "50000.2", "2026-03-01T12:00:00Z"))
    quote = client.latest_quote("BTC/USD")
    assert quote is not None
    assert quote.spread == Decimal("0.2")
    assert client.latest_quote("ETH/USD") is None


def test_a_crossed_quote_is_reported_rather_than_clamped() -> None:
    client = build()
    client.ingest(ticker_frame("BTC/USD", "50000.5", "50000.0", "2026-03-01T12:00:00Z"))
    quote = client.latest_quote("BTC/USD")
    assert quote is not None
    assert quote.spread == Decimal("-0.5")


def test_an_unrecognised_trade_shape_is_still_recorded_verbatim() -> None:
    """The half that cannot be recovered is the recording, so it never depends on
    the parse succeeding."""
    client = build()
    client.ingest(
        json.dumps({"channel": "trade", "data": [{"symbol": "BTC/USD", "px": "1", "sz": "1"}]})
    )
    assert client.drain_trades() == ()
    frames = client.drain()
    assert len(frames) == 1
    assert frames[0].payload["data"][0]["px"] == "1"
    assert client.unparsed_frames == 1


def test_a_frame_naming_two_symbols_gets_no_pair_rather_than_a_guess() -> None:
    client = build()
    client.ingest(
        json.dumps(
            {
                "channel": "trade",
                "data": [
                    {"symbol": "BTC/USD", "price": "1", "qty": "1"},
                    {"symbol": "ETH/USD", "price": "2", "qty": "1"},
                ],
            }
        )
    )
    frames = client.drain()
    assert frames[0].pair is None


def test_a_non_json_frame_is_counted_and_never_crashes_the_stream() -> None:
    client = build()
    client.ingest(b"not json at all")
    assert client.drain() == ()
    assert client.unparsed_frames == 1


def test_a_subscribe_ack_is_recorded_on_the_reserved_channel() -> None:
    client = build()
    client.ingest(json.dumps({"method": "subscribe", "success": True, "result": {}}))
    frames = client.drain()
    assert frames[0].channel == "_ack"


def test_a_full_buffer_drops_the_oldest_and_records_the_loss_as_a_gap() -> None:
    client = build(max_buffered_frames=2)
    for index in range(3):
        client.ingest(trade_frame("BTC/USD", str(index + 1), "1", "2026-03-01T12:00:00Z"))
    assert client.dropped_frames == 1
    assert len(client.gaps) == 1
    assert "overflow" in client.gaps[0]["cause"]


# --------------------------------------------------------------------------- #
# Reconnection and gaps
# --------------------------------------------------------------------------- #


class FakeSocket:
    """Yields frames, then does what `then` says."""

    def __init__(self, frames: list[str], then: Exception | None, owner: Any) -> None:
        self._frames = list(frames)
        self._then = then
        self._owner = owner
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        if self._then is not None:
            raise self._then
        # Last session: end the run rather than blocking forever.
        self._owner._stopping.set()
        if self._owner._async_stop is not None:
            self._owner._async_stop.set()
        return trade_frame("BTC/USD", "3", "1", "2026-03-01T12:00:02Z")


class FakeConnect:
    def __init__(self, sessions: list[FakeSocket]) -> None:
        self._sessions = sessions
        self.opened = 0
        self._current: FakeSocket | None = None

    def __call__(self, url: str, **kwargs: Any) -> FakeConnect:
        return self

    async def __aenter__(self) -> FakeSocket:
        self._current = self._sessions[min(self.opened, len(self._sessions) - 1)]
        self.opened += 1
        return self._current

    async def __aexit__(self, *exc: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_a_dropped_connection_reconnects_and_records_the_break_as_a_gap() -> None:
    clock = SteppingClock(step_s=2.0)
    client = KrakenWebSocketClient(
        clock=clock,
        pairs=["BTC/USD"],
        connect=lambda *a, **k: None,
        jitter=lambda: 0.0,
        backoff_initial_s=0.001,
        backoff_max_s=0.001,
    )
    connector = FakeConnect(
        [
            FakeSocket(
                [trade_frame("BTC/USD", "1", "1", "2026-03-01T12:00:00Z")],
                OSError("connection reset"),
                client,
            ),
            FakeSocket([trade_frame("BTC/USD", "2", "1", "2026-03-01T12:00:01Z")], None, client),
        ]
    )
    client._connect = connector

    await client._run()

    assert connector.opened == 2
    gaps = client.gaps
    assert len(gaps) == 1
    assert "connection reset" in gaps[0]["cause"]
    assert gaps[0]["gap_ms"] > 0
    # Nothing was healed: both sessions' frames are present and nothing was
    # invented to bridge the break.
    prices = [f.payload["data"][0]["price"] for f in client.drain()]
    assert prices == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_every_subscription_is_sent_on_every_connect() -> None:
    client = KrakenWebSocketClient(
        clock=StillClock(),
        pairs=["BTC/USD", "ETH/USD"],
        channels=[StreamChannel.TRADE],
        connect=lambda *a, **k: None,
        jitter=lambda: 0.0,
        backoff_initial_s=0.001,
    )
    socket = FakeSocket([], None, client)
    client._connect = FakeConnect([socket])
    await client._run()
    assert len(socket.sent) == 1
    assert json.loads(socket.sent[0])["params"]["symbol"] == ["BTC/USD", "ETH/USD"]
