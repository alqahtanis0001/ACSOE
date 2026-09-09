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

import asyncio
import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import structlog

from acsoe.clients.kraken import KrakenWebSocketClient, StreamChannel
from acsoe.clients.kraken.ws import REPEAT_ESCALATION, subscriptions
from acsoe.platform.logging import configure_logging

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


# --------------------------------------------------------------------------- #
# The thread
# --------------------------------------------------------------------------- #


class _BlockingSocket:
    """Connects, then delivers nothing until it is told to stop.

    The shape a real socket has on a quiet market, and the one that would hang a
    shutdown if `stop()` did not reach the loop thread.
    """

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.opened = threading.Event()

    async def send(self, message: str) -> None:
        self.sent.append(message)
        self.opened.set()

    async def recv(self) -> str:
        await asyncio.Event().wait()  # never returns
        raise AssertionError("unreachable")  # pragma: no cover


class _BlockingConnect:
    def __init__(self, socket: _BlockingSocket) -> None:
        self._socket = socket

    def __call__(self, url: str, **kwargs: Any) -> _BlockingConnect:
        return self

    async def __aenter__(self) -> _BlockingSocket:
        return self._socket

    async def __aexit__(self, *exc: Any) -> None:
        return None


def test_start_and_stop_are_idempotent_and_the_thread_actually_exits() -> None:
    """The one part of this client that owns an OS resource.

    A `stop()` that did not reach the loop thread would leave a daemon thread parked
    on `recv()` forever — which in a test suite looks like a hang with no traceback,
    and in the daemon looks like a process that will not shut down.
    """
    socket = _BlockingSocket()
    client = KrakenWebSocketClient(
        clock=StillClock(),
        pairs=["BTC/USD"],
        connect=_BlockingConnect(socket),
        jitter=lambda: 0.0,
        backoff_initial_s=0.001,
    )

    client.start()
    client.start()  # idempotent: no second thread
    assert socket.opened.wait(timeout=5.0), "the stream never opened its subscription"
    assert client.connected is True

    thread = client._thread
    assert thread is not None

    client.stop(timeout_s=5.0)
    assert thread.is_alive() is False
    assert client.connected is False

    client.stop(timeout_s=1.0)  # idempotent


def test_stop_before_start_is_harmless() -> None:
    client = KrakenWebSocketClient(
        clock=StillClock(), pairs=["BTC/USD"], connect=lambda *a, **k: None
    )
    client.stop(timeout_s=1.0)
    assert client.connected is False


def test_an_unexpected_error_becomes_a_recorded_gap_rather_than_a_dead_thread() -> None:
    """The failure the whole recording exists to prevent.

    This loop runs on a background thread with no caller to raise into, so an uncaught
    error kills the recorder silently — and a dead recorder is indistinguishable from a
    quiet market. It reconnects, and the break is written into `gaps` carrying the
    exception's type, so engine 2 appends it to the archive like any disconnect.
    """
    clock = SteppingClock(step_s=1.0)
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
            FakeSocket([], ValueError("a parse defect, not an outage"), client),
            FakeSocket([trade_frame("BTC/USD", "1", "1", "2026-03-01T12:00:01Z")], None, client),
        ]
    )
    client._connect = connector

    await_run = client._run()
    asyncio.run(await_run)

    assert connector.opened == 2, "the stream gave up instead of reconnecting"
    gaps = client.gaps
    assert len(gaps) == 1
    assert "unexpected ValueError" in gaps[0]["cause"]
    assert "a parse defect" in gaps[0]["cause"]


def test_an_unexpected_error_logs_the_traceback_as_well_as_recording_the_gap(
    tmp_path: Any,
) -> None:
    """Two artefacts, and they are not interchangeable.

    The gap carries the *cause string*, which tells an operator the recorder died.
    `unexpected RecursionError: maximum recursion depth exceeded` tells a developer
    nothing about **where** — a stack does. So the archive gets the durable
    operator-facing fact and the log gets the traceback.
    """
    log_path = configure_logging(log_dir=tmp_path / "logs", level="DEBUG")
    try:
        client = KrakenWebSocketClient(
            clock=SteppingClock(step_s=1.0),
            pairs=["BTC/USD"],
            connect=lambda *a, **k: None,
            jitter=lambda: 0.0,
            backoff_initial_s=0.001,
            backoff_max_s=0.001,
        )
        client._connect = FakeConnect(
            [
                FakeSocket([], ValueError("a parse defect"), client),
                FakeSocket([], None, client),
            ]
        )
        asyncio.run(client._run())
        logging.getLogger().handlers[0].flush()
        captured = log_path.read_text(encoding="utf-8")
    finally:
        _release_logging()

    assert "stream_unexpected_error" in captured
    assert "a parse defect" in captured
    # The traceback, which the gap record does not carry.
    assert "Traceback" in captured
    assert "_session" in captured
    assert "unexpected ValueError" in client.gaps[0]["cause"]


def test_the_same_fault_repeating_escalates_the_log_level(tmp_path: Any) -> None:
    """A permanent fault wears the costume of a transient one: the backoff absorbs it,
    the stream keeps reconnecting, and the only evidence is a pile of identically-caused
    gaps in an archive nobody is reading at the time."""
    log_path = configure_logging(log_dir=tmp_path / "logs", level="DEBUG")
    try:
        client = KrakenWebSocketClient(
            clock=SteppingClock(step_s=1.0),
            pairs=["BTC/USD"],
            connect=lambda *a, **k: None,
            jitter=lambda: 0.0,
            backoff_initial_s=0.001,
            backoff_max_s=0.001,
        )
        client._connect = FakeConnect(
            [
                *[
                    FakeSocket([], ValueError("the same defect every time"), client)
                    for _ in range(REPEAT_ESCALATION)
                ],
                FakeSocket([], None, client),
            ]
        )
        asyncio.run(client._run())
        logging.getLogger().handlers[0].flush()
        levels = [
            json.loads(line)["level"]
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and "stream_unexpected_error" in line
        ]
    finally:
        _release_logging()

    assert levels[: REPEAT_ESCALATION - 1] == ["error"] * (REPEAT_ESCALATION - 1)
    assert levels[REPEAT_ESCALATION - 1] == "critical"


def test_an_ordinary_disconnect_does_not_log_a_traceback(tmp_path: Any) -> None:
    """A stack for "the network went away" is noise, and noise trains a reader to skip
    the ones that matter."""
    log_path = configure_logging(log_dir=tmp_path / "logs", level="DEBUG")
    try:
        client = KrakenWebSocketClient(
            clock=SteppingClock(step_s=1.0),
            pairs=["BTC/USD"],
            connect=lambda *a, **k: None,
            jitter=lambda: 0.0,
            backoff_initial_s=0.001,
            backoff_max_s=0.001,
        )
        client._connect = FakeConnect(
            [FakeSocket([], OSError("connection reset"), client), FakeSocket([], None, client)]
        )
        asyncio.run(client._run())
        logging.getLogger().handlers[0].flush()
        captured = log_path.read_text(encoding="utf-8")
    finally:
        _release_logging()

    assert "stream_unexpected_error" not in captured
    assert "connection reset" in client.gaps[0]["cause"]


def _release_logging() -> None:
    logging.shutdown()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    structlog.reset_defaults()
