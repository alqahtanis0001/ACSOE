#!/usr/bin/env python
"""Standalone Kraken WebSocket v2 to JSONL recorder.

This script imports **nothing** from ``src/acsoe/``. That is deliberate and it is
not laziness: order-book and spread history cannot be recovered retroactively, so
recording has to start on day one, before the engine framework exists. Engines 1
and 2 supersede it in Phase 2 and this script keeps running regardless.

It records **public** market data only and therefore holds no credentials. There
is no API key anywhere in this file and none is needed: Kraken's ``book``,
``ticker`` and ``trade`` channels on ``wss://ws.kraken.com/v2`` are unauthenticated.

Line schema — one JSON object per line, exactly these seven keys::

    v            int    always 1
    kind         str    "tick" | "gap" | "session"
    pair         str|None  Kraken v2 symbol, null when the frame names no single one
    channel      str    Kraken's channel name, or "_recorder" for a marker
    ts_exchange  str|None  ISO-8601 UTC ending "Z", copied verbatim from the payload
    ts_recv      str    ISO-8601 UTC ending "Z", recorder wall clock at frame read
    payload      dict   the Kraken frame verbatim, or the marker's own object

Recordings are immutable (invariant 11). Nothing here edits, backfills,
interpolates or reorders a line. A break in the stream is written down as a
``gap`` marker rather than silently healed.

Usage::

    python scripts/record.py                              # default pairs, runs until Ctrl-C
    python scripts/record.py --pairs BTC/USD ETH/USD
    python scripts/record.py --duration-s 900 --out data/raw
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import random
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Self

import orjson
import websockets
from websockets.asyncio.client import connect

SCHEMA_VERSION: Final = 1
KRAKEN_WS_V2_URL: Final = "wss://ws.kraken.com/v2"

#: ``channel`` value for lines the recorder wrote about itself rather than about
#: the market. Reserved: no Kraken channel may ever be called this.
RECORDER_CHANNEL: Final = "_recorder"

#: ``channel`` value for a Kraken method response (a subscribe/unsubscribe ack).
#: Those frames carry ``method`` instead of ``channel``.
ACK_CHANNEL: Final = "_ack"

LINE_KEYS: Final = frozenset(
    {"v", "kind", "pair", "channel", "ts_exchange", "ts_recv", "payload"}
)
LINE_KINDS: Final = frozenset({"tick", "gap", "session"})

DEFAULT_PAIRS: Final = ("BTC/USD", "ETH/USD", "SOL/USD")
DEFAULT_CHANNELS: Final = ("book", "ticker", "trade")
DEFAULT_DEPTH: Final = 10
DEFAULT_OUT_DIR: Final = Path("data") / "raw"

BACKOFF_INITIAL_S: Final = 1.0
BACKOFF_MAX_S: Final = 60.0
BACKOFF_FACTOR: Final = 2.0


class SchemaError(ValueError):
    """A line failed validation on write. Never suppressed: a malformed line in an
    append-only recording is unfixable later, so the recorder refuses to write it."""


def utc_now_iso() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SS.ffffffZ``.

    Not injected, because this script is not an engine. Invariant 9 constrains
    engines, which receive ``context.now``; this is the process that produces
    timestamps in the first place.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def utc_date_from_iso(ts: str) -> str:
    """The UTC calendar date of an ISO timestamp, for daily file rotation."""
    return ts[:10]


def _first_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def extract_pair(payload: dict[str, Any]) -> str | None:
    """The single symbol a frame concerns, or None.

    Kraken v2 delivers ``data`` as a list, and a frame may carry several symbols.
    Reading a symbol out of the payload is not a mutation of it — the payload is
    still written verbatim — but a frame covering two pairs has no single pair,
    so it gets null rather than a guess.
    """
    data = payload.get("data")
    if isinstance(data, list) and data:
        symbols: set[str] = set()
        for item in data:
            symbol = _first_str(item.get("symbol")) if isinstance(item, dict) else None
            if symbol is not None:
                symbols.add(symbol)
        if len(symbols) == 1:
            return symbols.pop()
        return None
    if isinstance(data, dict):
        return _first_str(data.get("symbol"))
    result = payload.get("result")
    if isinstance(result, dict):
        return _first_str(result.get("symbol"))
    return None


def extract_channel(payload: dict[str, Any]) -> str:
    """Kraken's own channel name, or a reserved marker for a method response."""
    channel = _first_str(payload.get("channel"))
    if channel is not None:
        return channel
    if _first_str(payload.get("method")) is not None:
        return ACK_CHANNEL
    return "_unknown"


def extract_ts_exchange(payload: dict[str, Any]) -> str | None:
    """The exchange's own timestamp, copied verbatim, or None when there is none.

    Book snapshots and heartbeats carry no timestamp. That absence is recorded as
    null rather than filled in with the receive time, which would silently turn a
    measurement of network latency into zero.
    """
    data = payload.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return _first_str(data[0].get("timestamp"))
    if isinstance(data, dict):
        return _first_str(data.get("timestamp"))
    return None


def build_line(
    *,
    kind: str,
    pair: str | None,
    channel: str,
    ts_exchange: str | None,
    ts_recv: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "v": SCHEMA_VERSION,
        "kind": kind,
        "pair": pair,
        "channel": channel,
        "ts_exchange": ts_exchange,
        "ts_recv": ts_recv,
        "payload": payload,
    }


def validate_line(line: dict[str, Any]) -> None:
    """Validate on write. Raises :class:`SchemaError` on anything malformed.

    Spec 10 step 4. A recording is append-only, so a line that is wrong when
    written is wrong forever — validation has to happen before the bytes hit the
    file, not in a later cleaning pass that invariant 11 forbids anyway.
    """
    keys = set(line)
    if keys != LINE_KEYS:
        missing = sorted(LINE_KEYS - keys)
        extra = sorted(keys - LINE_KEYS)
        raise SchemaError(f"line keys wrong: missing={missing} extra={extra}")
    if line["v"] != SCHEMA_VERSION:
        raise SchemaError(f"unknown schema version {line['v']!r}")
    if line["kind"] not in LINE_KINDS:
        raise SchemaError(f"unknown kind {line['kind']!r}")
    if line["pair"] is not None and not isinstance(line["pair"], str):
        raise SchemaError(f"pair must be a string or null, got {type(line['pair']).__name__}")
    if not isinstance(line["channel"], str) or not line["channel"]:
        raise SchemaError("channel must be a non-empty string")
    if line["kind"] in ("gap", "session") and line["channel"] != RECORDER_CHANNEL:
        raise SchemaError(f"a {line['kind']} marker must use channel {RECORDER_CHANNEL!r}")
    for field in ("ts_exchange", "ts_recv"):
        value = line[field]
        if field == "ts_recv" and value is None:
            raise SchemaError("ts_recv may not be null")
        if value is None:
            continue
        if not isinstance(value, str) or not value.endswith("Z"):
            raise SchemaError(f"{field} must be an ISO-8601 UTC string ending 'Z', got {value!r}")
    if not isinstance(line["payload"], dict):
        raise SchemaError(f"payload must be an object, got {type(line['payload']).__name__}")


class JsonlWriter:
    """Append-only JSONL writer with daily UTC rotation.

    Opens in binary append mode and never truncates, seeks or rewrites. If the
    process is killed mid-line the partial line stays; it is not repaired, because
    repairing a recording is exactly what invariant 11 forbids.
    """

    def __init__(self, out_dir: Path, *, prefix: str = "kraken_v2") -> None:
        self._out_dir = out_dir
        self._prefix = prefix
        self._date: str | None = None
        self._handle: Any = None
        self.lines_written = 0

    def __enter__(self) -> Self:
        self._out_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def path_for(self, date: str) -> Path:
        return self._out_dir / f"{self._prefix}_{date}.jsonl"

    def write(self, line: dict[str, Any]) -> None:
        validate_line(line)
        date = utc_date_from_iso(line["ts_recv"])
        if date != self._date:
            self._rotate(date)
        assert self._handle is not None
        self._handle.write(orjson.dumps(line))
        self._handle.write(b"\n")
        self._handle.flush()
        self.lines_written += 1

    def _rotate(self, date: str) -> None:
        if self._handle is not None:
            self._handle.close()
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._handle = self.path_for(date).open("ab")
        self._date = date

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def subscriptions(
    channels: tuple[str, ...], pairs: tuple[str, ...], depth: int
) -> list[dict[str, Any]]:
    """The subscribe payloads, in a stable order so a session marker is comparable."""
    subs: list[dict[str, Any]] = []
    for channel in channels:
        params: dict[str, Any] = {"channel": channel, "symbol": list(pairs)}
        if channel == "book":
            params["depth"] = depth
        subs.append({"method": "subscribe", "params": params})
    return subs


class Recorder:
    def __init__(
        self,
        *,
        writer: JsonlWriter,
        url: str,
        pairs: tuple[str, ...],
        channels: tuple[str, ...],
        depth: int,
        ping_interval: float = 20.0,
        ping_timeout: float = 20.0,
    ) -> None:
        self._writer = writer
        self._url = url
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._subs = subscriptions(channels, pairs, depth)
        self._stopping = asyncio.Event()
        #: Set when a connection drops; consumed by the next successful connect,
        #: which is what turns a reconnect into a recorded gap rather than a
        #: silent resume.
        self._disconnected_at: str | None = None
        self._disconnect_reason: str | None = None
        self._attempt = 0
        #: Reconnect delay. Reset on a *successful connect*, not on a clean
        #: return from the session loop — see the comment in `_session`.
        self._backoff = BACKOFF_INITIAL_S

    def stop(self) -> None:
        self._stopping.set()

    def _write_session(self, event: str) -> None:
        self._writer.write(
            build_line(
                kind="session",
                pair=None,
                channel=RECORDER_CHANNEL,
                ts_exchange=None,
                ts_recv=utc_now_iso(),
                payload={
                    "event": event,
                    "url": self._url,
                    "subscriptions": [sub["params"] for sub in self._subs],
                },
            )
        )

    def _write_gap(self) -> None:
        """Record the break. Called on reconnect, never on disconnect.

        Writing it on reconnect is what makes ``gap_ms`` truthful: the length of a
        gap is not known until it ends, and a marker written at disconnect time
        would have to be edited afterwards, which is forbidden.
        """
        if self._disconnected_at is None:
            return
        reconnected_at = utc_now_iso()
        gap_ms = int(
            (
                datetime.fromisoformat(reconnected_at.replace("Z", "+00:00"))
                - datetime.fromisoformat(self._disconnected_at.replace("Z", "+00:00"))
            ).total_seconds()
            * 1000
        )
        self._writer.write(
            build_line(
                kind="gap",
                pair=None,
                channel=RECORDER_CHANNEL,
                ts_exchange=None,
                ts_recv=reconnected_at,
                payload={
                    "reason": self._disconnect_reason or "unknown",
                    "disconnected_at": self._disconnected_at,
                    "reconnected_at": reconnected_at,
                    "gap_ms": gap_ms,
                    "attempt": self._attempt,
                },
            )
        )
        self._disconnected_at = None
        self._disconnect_reason = None

    def _write_frame(self, raw: str | bytes) -> None:
        ts_recv = utc_now_iso()
        payload = orjson.loads(raw)
        if not isinstance(payload, dict):
            # Kraken v2 sends objects. Anything else is recorded rather than
            # dropped, wrapped so the schema still holds and nothing is lost.
            payload = {"_nonobject": payload}
            self._writer.write(
                build_line(
                    kind="tick",
                    pair=None,
                    channel="_unknown",
                    ts_exchange=None,
                    ts_recv=ts_recv,
                    payload=payload,
                )
            )
            return
        self._writer.write(
            build_line(
                kind="tick",
                pair=extract_pair(payload),
                channel=extract_channel(payload),
                ts_exchange=extract_ts_exchange(payload),
                ts_recv=ts_recv,
                payload=payload,
            )
        )

    async def _session(self) -> None:
        async with connect(
            self._url,
            max_size=None,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
        ) as ws:
            self._write_gap()
            # Reset here, on a successful connect. Resetting after `_session`
            # returns is wrong: `_session` only ever returns normally when the
            # recorder is stopping, so the backoff would compound across
            # independent, individually successful reconnects. A process that
            # drops once an hour would, half a day later, be waiting a full
            # minute to reconnect after a fault it recovers from instantly, and
            # that minute is order-book data nothing can recover.
            self._attempt = 0
            self._backoff = BACKOFF_INITIAL_S
            for sub in self._subs:
                await ws.send(orjson.dumps(sub).decode())
            while not self._stopping.is_set():
                receive = asyncio.ensure_future(ws.recv())
                stop = asyncio.ensure_future(self._stopping.wait())
                done, pending = await asyncio.wait(
                    {receive, stop}, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                if receive in done:
                    self._write_frame(receive.result())

    async def run(self) -> None:
        self._write_session("start")
        try:
            while not self._stopping.is_set():
                try:
                    await self._session()
                except (OSError, websockets.exceptions.WebSocketException) as exc:
                    self._attempt += 1
                    if self._disconnected_at is None:
                        self._disconnected_at = utc_now_iso()
                        self._disconnect_reason = f"{type(exc).__name__}: {exc}"
                    # Jitter, so a Kraken-side outage does not produce a
                    # thundering herd of reconnects on the same second.
                    delay = min(self._backoff, BACKOFF_MAX_S) * (0.5 + random.random())
                    print(
                        f"disconnected ({type(exc).__name__}), "
                        f"reconnecting in {delay:.1f}s (attempt {self._attempt})",
                        file=sys.stderr,
                    )
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._stopping.wait(), timeout=delay)
                    self._backoff = min(self._backoff * BACKOFF_FACTOR, BACKOFF_MAX_S)
        finally:
            self._write_session("stop")


async def _run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    with JsonlWriter(out_dir) as writer:
        recorder = Recorder(
            writer=writer,
            url=args.url,
            pairs=tuple(args.pairs),
            channels=tuple(args.channels),
            depth=args.depth,
            ping_interval=args.ping_interval,
            ping_timeout=args.ping_timeout,
        )

        loop = asyncio.get_running_loop()
        with contextlib.suppress(NotImplementedError):
            for signame in ("SIGINT", "SIGTERM"):
                sig = getattr(signal, signame, None)
                if sig is not None:
                    loop.add_signal_handler(sig, recorder.stop)

        task = asyncio.ensure_future(recorder.run())
        try:
            if args.duration_s > 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(task), timeout=args.duration_s)
                recorder.stop()
            await task
        except KeyboardInterrupt:
            recorder.stop()
            await task
        print(f"wrote {writer.lines_written} lines to {out_dir}", file=sys.stderr)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="record.py",
        description="Standalone Kraken WebSocket v2 to JSONL recorder. Public data only.",
    )
    parser.add_argument("--url", default=KRAKEN_WS_V2_URL, help="Kraken WebSocket v2 endpoint")
    parser.add_argument(
        "--pairs", nargs="+", default=list(DEFAULT_PAIRS), help="Kraken v2 symbols, e.g. BTC/USD"
    )
    parser.add_argument(
        "--channels", nargs="+", default=list(DEFAULT_CHANNELS), help="book, ticker, trade"
    )
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="order book depth")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="output directory")
    parser.add_argument(
        "--ping-interval",
        type=float,
        default=20.0,
        help="keepalive ping interval in seconds",
    )
    parser.add_argument(
        "--ping-timeout",
        type=float,
        default=20.0,
        help=(
            "keepalive pong deadline in seconds. Lowering it below the round trip to Kraken "
            "deliberately induces a disconnect, which is how the reconnect and gap-marker path "
            "is exercised against the live exchange rather than against a mock."
        ),
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        default=0.0,
        help="stop after this many seconds; 0 runs until interrupted",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
