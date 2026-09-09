"""Kraken WebSocket v2: a background stream a synchronous loop can read.

The shape of this class is forced by two facts that pull in opposite directions.
The runtime loop is **synchronous** and ticks once a minute; the socket delivers
**continuously** and cannot be polled once a minute without losing almost all of
it. So the stream runs on its own thread with its own event loop, buffers what
arrives, and the engines take everything buffered since the last tick. Engine 2
drains the raw frames to the recorder; engine 3 drains the trades and builds
candles from them.

Four decisions worth knowing before changing anything here.

**A break is recorded, never healed.** A disconnect is written into :attr:`gaps`
with its start, its end and its cause, and the gap is only complete once the
reconnect happens, because the length of a gap is not known until it ends.
Invariant 11: a recording is append-only and a break is a fact about the feed.

**Frames are buffered verbatim and parsed leniently.** ``AGENTS.md`` says any
Kraken payload shape an agent remembers may be stale. So the *recording* never
depends on the parse: every frame reaches :meth:`drain` exactly as it arrived, and
the trade and quote extraction is best-effort on top. If Kraken renames a field,
the archive is still correct and complete, candles simply stop building, and engine
4 ``data_guard`` blocks on missing candles — which is the fail-closed outcome. A
strict parser would instead throw away the recording, which cannot be recovered.

**The buffers are bounded.** An engine that stops draining must not grow the
process until it dies. When a buffer is full the *oldest* entries are dropped and
the loss is recorded as a gap, so a silent overflow is impossible.

**Nothing here reads the wall clock.** The clock is injected, exactly as it is for
the REST client.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import threading
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import orjson
import websockets.exceptions
from websockets.asyncio.client import connect as _ws_connect

from acsoe.clients.kraken.contracts import QuoteTick, RawFrame, StreamChannel, TradeTick
from acsoe.platform.clock import Clock
from acsoe.platform.logging import get_logger

__all__ = ["KrakenWebSocketClient", "subscriptions"]

KRAKEN_WS_V2_URL = "wss://ws.kraken.com/v2"

#: The reserved ``channel`` value for a Kraken method response. Matches
#: ``scripts/record.py``, because engine 2 supersedes that script and a recording
#: whose channel names disagreed with the day-one archive would split the dataset.
ACK_CHANNEL = "_ack"
UNKNOWN_CHANNEL = "_unknown"

_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    websockets.exceptions.WebSocketException,
)

BACKOFF_INITIAL_S = 1.0
BACKOFF_MAX_S = 60.0
BACKOFF_FACTOR = 2.0

#: Consecutive sessions ended by the *same* cause before the log level goes critical.
#: Three, because two can be coincidence on a flaky link and the backoff has reached
#: four seconds by then — long enough that the fault is not clearing on its own.
REPEAT_ESCALATION = 3


def subscriptions(
    channels: Sequence[str], pairs: Sequence[str], depth: int
) -> list[dict[str, Any]]:
    """The subscribe payloads, in a stable order."""
    subs: list[dict[str, Any]] = []
    for channel in channels:
        params: dict[str, Any] = {"channel": channel, "symbol": list(pairs)}
        if channel == StreamChannel.BOOK:
            params["depth"] = depth
        subs.append({"method": "subscribe", "params": params})
    return subs


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _channel_of(payload: Mapping[str, Any]) -> str:
    channel = _text(payload.get("channel"))
    if channel is not None:
        return channel
    if _text(payload.get("method")) is not None:
        return ACK_CHANNEL
    return UNKNOWN_CHANNEL


def _items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        return [data]
    return []


def _pair_of(payload: Mapping[str, Any]) -> str | None:
    """The single symbol a frame concerns, or None when it names more than one."""
    symbols = {
        symbol for item in _items(payload) if (symbol := _text(item.get("symbol"))) is not None
    }
    if len(symbols) == 1:
        return symbols.pop()
    result = payload.get("result")
    if isinstance(result, Mapping):
        return _text(result.get("symbol"))
    return None


def _ts_exchange_of(payload: Mapping[str, Any]) -> str | None:
    for item in _items(payload):
        stamp = _text(item.get("timestamp"))
        if stamp is not None:
            return stamp
    return None


def _iso(moment: datetime) -> str:
    """ISO-8601 UTC ending in `Z`, the form the recording schema requires."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_ts(value: Any, fallback: datetime) -> datetime:
    text = _text(value)
    if text is None:
        return fallback
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _decimal(value: Any) -> Decimal | None:
    """Exact, or nothing. A float is refused rather than rounded into place."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, str)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, float):
        # Kraken v2 sends numbers as JSON numbers, so this is the normal path for a
        # price off the socket. `repr` of a float is its shortest round-tripping
        # form, which is the closest to "the number that was sent" available once
        # the JSON parser has already made it a float. Money that reaches an *order*
        # never comes from here: order sizing reads `AssetPairs` and the balances,
        # which arrive as strings and stay exact.
        try:
            return Decimal(repr(value))
        except InvalidOperation:
            return None
    return None


class KrakenWebSocketClient:
    """A buffered Kraken v2 market stream.

    :param clock: injected. Used only to timestamp gaps and fall back for a frame
        that carries no exchange timestamp.
    :param connect: how to open the socket. Injected, so the reconnect, the gap
        marking and the parsing are all provable offline without relaxing the
        network guard.
    """

    def __init__(
        self,
        *,
        clock: Clock,
        pairs: Sequence[str],
        channels: Sequence[str] = (StreamChannel.BOOK, StreamChannel.TICKER, StreamChannel.TRADE),
        depth: int = 10,
        url: str = KRAKEN_WS_V2_URL,
        connect: Callable[..., Any] | None = None,
        max_buffered_frames: int = 200_000,
        max_buffered_trades: int = 200_000,
        jitter: Callable[[], float] = random.random,
        backoff_initial_s: float = BACKOFF_INITIAL_S,
        backoff_max_s: float = BACKOFF_MAX_S,
    ) -> None:
        self._clock = clock
        self._url = url
        self._subs = subscriptions(channels, pairs, depth)
        self._connect = connect if connect is not None else _ws_connect
        self._jitter = jitter
        self._backoff_initial_s = backoff_initial_s
        self._backoff_max_s = backoff_max_s

        self._lock = threading.Lock()
        self._frames: deque[RawFrame] = deque(maxlen=max_buffered_frames)
        self._trades: deque[TradeTick] = deque(maxlen=max_buffered_trades)
        self._quotes: dict[str, QuoteTick] = {}
        self._gaps: list[dict[str, Any]] = []
        self._undrained_gaps: list[dict[str, Any]] = []
        self._dropped_frames = 0
        self._unparsed = 0
        self._connected = False

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping = threading.Event()
        self._async_stop: asyncio.Event | None = None
        self._disconnected_at: datetime | None = None
        self._disconnect_reason: str | None = None
        self._attempt = 0
        self._backoff = backoff_initial_s
        self._last_cause: str | None = None
        self._repeated_cause = 0

    # -- lifecycle -------------------------------------------------------- #

    def start(self) -> None:
        """Open the stream on its own thread. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._thread_main, name="kraken-ws", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 10.0) -> None:
        """Close the stream and wait for the thread. Idempotent."""
        self._stopping.set()
        loop, event = self._loop, self._async_stop
        if loop is not None and event is not None and not loop.is_closed():
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(event.set)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout_s)
        self._thread = None
        with self._lock:
            self._connected = False

    def _thread_main(self) -> None:
        asyncio.run(self._run())

    # -- the read side, called from the loop thread ----------------------- #

    def drain(self) -> tuple[RawFrame, ...]:
        with self._lock:
            frames = tuple(self._frames)
            self._frames.clear()
        return frames

    def drain_trades(self) -> tuple[TradeTick, ...]:
        with self._lock:
            trades = tuple(self._trades)
            self._trades.clear()
        return trades

    def recent_trades(self) -> tuple[TradeTick, ...]:
        """The buffered trades **without** clearing them, oldest first.

        A rolling window rather than a queue, because engine 3 has to rebuild the same
        15-minute bar on each of the fifteen ticks that bar spans, and an engine is
        stateless across cycles — so the window has to live in the client, which is
        injected and long-lived, exactly as the frame buffer does.

        Bounded by ``max_buffered_trades``, so it is a window by *count* rather than by
        time. A longer history belongs in `data/derived/` through the replay path, not
        in a live buffer.
        """
        with self._lock:
            return tuple(self._trades)

    def drain_gaps(self) -> tuple[Mapping[str, Any], ...]:
        """Every break recorded since the last call, and clear them.

        Drained rather than read so engine 2 stays stateless across cycles: it never
        has to remember which breaks it has already written into the archive.
        `gaps` remains available as the accumulated view the digest reads.
        """
        with self._lock:
            drained = tuple(dict(gap) for gap in self._undrained_gaps)
            self._undrained_gaps.clear()
        return drained

    def latest_quote(self, pair: str) -> QuoteTick | None:
        with self._lock:
            return self._quotes.get(pair)

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def gaps(self) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            return tuple(dict(gap) for gap in self._gaps)

    @property
    def dropped_frames(self) -> int:
        """Frames lost to a full buffer. Reported, never hidden."""
        with self._lock:
            return self._dropped_frames

    @property
    def unparsed_frames(self) -> int:
        """Frames recorded verbatim that yielded no trade and no quote."""
        with self._lock:
            return self._unparsed

    # -- ingestion -------------------------------------------------------- #

    def ingest(self, raw: str | bytes) -> None:
        """Parse one frame and buffer it. Public so a test can drive the stream."""
        try:
            payload = orjson.loads(raw)
        except orjson.JSONDecodeError:
            with self._lock:
                self._unparsed += 1
            return
        if not isinstance(payload, dict):
            payload = {"_nonobject": payload}
        frame = RawFrame(
            channel=_channel_of(payload),
            pair=_pair_of(payload),
            ts_exchange=_ts_exchange_of(payload),
            ts_recv=_iso(self._clock.now()),
            payload=payload,
        )
        trades = self._extract_trades(payload, frame.channel)
        quotes = self._extract_quotes(payload, frame.channel)
        with self._lock:
            if len(self._frames) == self._frames.maxlen:
                self._dropped_frames += 1
                self._note_gap_locked("buffer overflow: the oldest frame was dropped")
            self._frames.append(frame)
            for trade in trades:
                self._trades.append(trade)
            for quote in quotes:
                self._quotes[quote.pair] = quote
            if not trades and not quotes and frame.channel in tuple(StreamChannel):
                self._unparsed += 1

    def _fallback_now(self) -> datetime:
        return self._clock.now()

    def _extract_trades(self, payload: Mapping[str, Any], channel: str) -> list[TradeTick]:
        if channel != StreamChannel.TRADE:
            return []
        now = self._fallback_now()
        out: list[TradeTick] = []
        for item in _items(payload):
            symbol = _text(item.get("symbol"))
            price = _decimal(item.get("price"))
            qty = _decimal(item.get("qty"))
            if symbol is None or price is None or qty is None or price <= 0 or qty <= 0:
                continue
            out.append(
                TradeTick(
                    pair=symbol,
                    ts=_parse_ts(item.get("timestamp"), now),
                    price=price,
                    qty=qty,
                )
            )
        return out

    def _extract_quotes(self, payload: Mapping[str, Any], channel: str) -> list[QuoteTick]:
        if channel != StreamChannel.TICKER:
            return []
        now = self._fallback_now()
        out: list[QuoteTick] = []
        for item in _items(payload):
            symbol = _text(item.get("symbol"))
            bid = _decimal(item.get("bid"))
            ask = _decimal(item.get("ask"))
            if symbol is None or bid is None or ask is None:
                continue
            out.append(
                QuoteTick(
                    pair=symbol, ts=_parse_ts(item.get("timestamp"), now), bid=bid, ask=ask
                )
            )
        return out

    # -- gaps ------------------------------------------------------------- #

    def _append_gap_locked(self, gap: dict[str, Any]) -> None:
        """One place a break is recorded, so nothing can be added to the accumulated
        view without also reaching engine 2's drain."""
        self._gaps.append(gap)
        self._undrained_gaps.append(gap)

    def _note_gap_locked(self, cause: str) -> None:
        moment = _iso(self._clock.now())
        self._append_gap_locked(
            {
                "cause": cause,
                "started_at": moment,
                "ended_at": moment,
                "gap_ms": 0,
            }
        )

    def _close_gap(self) -> None:
        """Write the break down, on reconnect.

        On reconnect and not on disconnect, because the length of a gap is not known
        until it ends, and a marker written at disconnect time would have to be
        edited afterwards — which invariant 11 forbids.
        """
        started = self._disconnected_at
        if started is None:
            return
        ended = self._clock.now()
        with self._lock:
            self._append_gap_locked(
                {
                    "cause": self._disconnect_reason or "unknown",
                    "started_at": _iso(started),
                    "ended_at": _iso(ended),
                    "gap_ms": int((ended - started).total_seconds() * 1000),
                    "attempt": self._attempt,
                }
            )
        self._disconnected_at = None
        self._disconnect_reason = None

    # -- the socket ------------------------------------------------------- #

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._async_stop = asyncio.Event()
        if self._stopping.is_set():
            return
        while not self._stopping.is_set():
            try:
                await self._session()
            except _TRANSPORT_ERRORS as exc:
                # An expected failure: the socket dropped. The gap record carries it and
                # no traceback is warranted — a stack for "the network went away" is
                # noise that trains a reader to skip the ones that matter.
                self._note_disconnect(f"{type(exc).__name__}: {exc}")
                await self._back_off()
            except Exception as exc:
                # **Not a swallowed exception.** This runs on a background thread with
                # no caller to raise into: an uncaught error here kills the recorder
                # silently, and a dead recorder is indistinguishable from a quiet
                # market — which is the single failure the whole recording exists to
                # make impossible.
                #
                # So it is written down where it cannot be missed. The break becomes a
                # `gap` in the archive, carrying the exception's type and message as
                # its cause, and engine 2 appends it to `data/raw/` on the next tick
                # exactly like a disconnect. That is a more durable record than a log
                # line, and `unparsed_frames` and `dropped_frames` are visible in
                # `state` beside it.
                #
                # It reconnects rather than stopping, on the same backoff, because a
                # recorder that gives up loses data it can never recover — and if the
                # fault is permanent the backoff reaches its ceiling and the archive
                # fills with identically-caused gaps.
                #
                # **The traceback is logged as well, and the two are not the same
                # artefact.** The gap record carries the *cause string*, which tells an
                # operator the recorder died; `unexpected RecursionError: maximum
                # recursion depth exceeded` tells a developer nothing about *where*. A
                # `MemoryError` or a validation failure on an unpredicted frame shape is
                # diagnosable from a stack and close to undiagnosable without one. So:
                # the archive gets the durable operator-facing fact, the log gets the
                # traceback, and neither does the other's job.
                cause = f"unexpected {type(exc).__name__}: {exc}"
                repeats = self._note_disconnect(cause)
                self._log_unexpected(exc, cause, repeats)
                await self._back_off()

    def _log_unexpected(self, exc: BaseException, cause: str, repeats: int) -> None:
        """Log the traceback, escalating once the same fault keeps recurring.

        A permanent fault wears the costume of a transient one: the backoff absorbs it,
        the stream keeps reconnecting, and the only evidence is a pile of
        identically-caused gaps in an archive nobody is reading at the time. After
        :data:`REPEAT_ESCALATION` consecutive identical causes the level goes to
        ``critical``, which puts it where somebody is actually looking.
        """
        logger = get_logger("acsoe.clients.kraken.ws")
        event = "stream_unexpected_error"
        fields: dict[str, Any] = {
            "cause": cause,
            "consecutive": repeats,
            "attempt": self._attempt,
            "backoff_s": self._backoff,
            "url": self._url,
        }
        if repeats >= REPEAT_ESCALATION:
            logger.critical(
                event,
                **fields,
                note=(
                    f"the same fault has ended {repeats} consecutive sessions; the "
                    "backoff is absorbing a permanent failure"
                ),
                exc_info=exc,
            )
        else:
            logger.error(event, **fields, exc_info=exc)

    def _note_disconnect(self, reason: str) -> int:
        """Record the break and return how many consecutive times this cause has hit."""
        self._attempt += 1
        if reason == self._last_cause:
            self._repeated_cause += 1
        else:
            self._last_cause = reason
            self._repeated_cause = 1
        if self._disconnected_at is None:
            self._disconnected_at = self._clock.now()
            self._disconnect_reason = reason
        with self._lock:
            self._connected = False
        return self._repeated_cause

    async def _back_off(self) -> None:
        delay = min(self._backoff, self._backoff_max_s) * (0.5 + self._jitter())
        await self._wait(delay)
        self._backoff = min(self._backoff * BACKOFF_FACTOR, self._backoff_max_s)

    async def _wait(self, delay: float) -> None:
        event = self._async_stop
        if event is None:  # pragma: no cover - set before the loop starts
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), timeout=delay)

    async def _session(self) -> None:
        async with self._connect(self._url, max_size=None) as socket:
            self._close_gap()
            self._attempt = 0
            self._backoff = self._backoff_initial_s
            with self._lock:
                self._connected = True
            for sub in self._subs:
                await socket.send(orjson.dumps(sub).decode())
            event = self._async_stop
            assert event is not None
            while not self._stopping.is_set():
                receive = asyncio.ensure_future(socket.recv())
                stop = asyncio.ensure_future(event.wait())
                done, pending = await asyncio.wait(
                    {receive, stop}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                if receive in done:
                    self.ingest(receive.result())
                else:
                    return
        with self._lock:
            self._connected = False
