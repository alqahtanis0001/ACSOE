"""The push side of the console. Spec 23.

The daemon and the console are separate processes sharing one SQLite file, so
there is no callback between them and nothing to subscribe to. ``ui-context.md``
fixes the mechanism: **the server polls a monotonically increasing ``updated_at``
watermark at ``console.poll_interval_ms`` and pushes over the WebSocket only when
that watermark moves.** No triggers, no file watching, no polling from the
browser, and no second transport.

Three properties of this module are load-bearing and each one is a decision that
could have gone another way.

**The baseline watermark is read before the handshake is accepted, not after.**
A client that connects and then immediately changes the database — which is
exactly what ``scripts/verify.py``'s ``console_websocket_pushes_on_change`` does,
and exactly what a daemon writing a row a millisecond after the operator opened
the page does — must not have that change swallowed. Reading the baseline after
accepting leaves a window in which a write lands *before* the first read and is
therefore already reflected in it, so the value never appears to move and the
push never happens. Reading it first makes the window empty: everything from the
moment of acceptance onward is a change.

**Nothing is pushed on connect.** The socket carries changes and only changes,
because that is what ``ui-context.md`` says it carries, and because a snapshot on
connect would make "did a push happen?" unable to distinguish a working watermark
from a broken one. The page gets its first content from the four ``GET``
endpoints, fetched once when the socket opens — once at load, not on a timer,
which is the browser-side polling the spec forbids. The client opens the socket
*first* and fetches *after*, so the fetch can only ever return data at or ahead
of the baseline; a change in between produces one redundant push, which is
invisible because the flash only fires on a value that actually differs.

**The interval is read from config on every iteration.** Not captured at
construction, not defaulted here, and never written as a literal. ``ui-context.md``
makes both numbers configuration; the README's 500 and 120000 are default values,
not a second source of truth. Reading it per iteration also means an operator who
retunes the file gets the new cadence on the next tick of an already-open socket.

The socket is **one-directional and read-only**. Nothing here writes to the
database, nothing here opens a read-write connection, and no command may be sent
over it — the three commands are ``POST`` routes in ``console/commands.py``. Any
frame the client sends is ignored.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any, Final

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from acsoe.console.payloads import (
    feed_payload,
    history_payload,
    research_payload,
    state_payload,
)
from acsoe.console.reader import ConsoleReader

if TYPE_CHECKING:  # pragma: no cover - typing only
    from acsoe.core.contracts import Config

__all__ = [
    "KEY_POLL_INTERVAL",
    "UPDATE_MESSAGE",
    "poll_interval_seconds",
    "screen_payloads",
    "update_payload",
    "watermark_socket",
]

#: The one config key this module reads. `console.port` is A's, and
#: `console.stale_after_ms` is read once by `create_app`; only the lead adds a
#: fourth.
KEY_POLL_INTERVAL: Final = "console.poll_interval_ms"

#: Every frame this socket sends carries this type. There is exactly one kind of
#: message and it is named rather than implied, so a client can tell a payload it
#: understands from one a later phase added.
UPDATE_MESSAGE: Final = "update"

_MILLIS_PER_SECOND: Final = 1000.0


def poll_interval_seconds(config: Config) -> float:
    """How long to wait before reading the watermark again.

    Read from `config` on every call. A non-positive interval would turn the poll
    loop into a busy loop against SQLite, so it is refused rather than clamped: a
    silently corrected interval is a misconfiguration nobody ever finds. Config
    validation already rejects an interval above a quarter of
    `console.stale_after_ms`, which is the other end of the same range.
    """
    interval_ms = int(config.get(KEY_POLL_INTERVAL))
    if interval_ms <= 0:
        raise ValueError(f"{KEY_POLL_INTERVAL} must be positive, got {interval_ms}")
    return interval_ms / _MILLIS_PER_SECOND


def screen_payloads(reader: ConsoleReader, *, mode: str) -> dict[str, Any]:
    """Every screen, composed from **the same view models as the GET routes**.

    That is the point of building it here rather than assembling a smaller delta:
    the socket and the plain endpoints can never disagree about what a screen
    says, because there is one composition and both call it. A delta would be
    cheaper on the wire and would be a second description of every screen.
    """
    return {
        "state": state_payload(reader.status_band(mode=mode), reader.positions()),
        "feed": feed_payload(reader.feed(), reader.feed_summary()),
        "history": history_payload(reader.history()),
        "research": research_payload(reader.research()),
    }


def update_payload(reader: ConsoleReader, *, mode: str, watermark: int) -> dict[str, Any]:
    """One push. The watermark travels with it so a client can see it move."""
    payload: dict[str, Any] = {"type": UPDATE_MESSAGE, "watermark": int(watermark)}
    payload.update(screen_payloads(reader, mode=mode))
    return payload


async def _send(socket: WebSocket, payload: dict[str, Any]) -> None:
    """Send one frame as text.

    `WebSocket.send_json` encodes with `ensure_ascii=True`, which would put
    `Idle \\u2014 restarted, not trading` on the wire while `JSONResponse` — which
    every `GET` route returns — puts the em dash there literally. Same bytes from
    both transports is worth one line.
    """
    await socket.send_text(json.dumps(payload, ensure_ascii=False))


async def _drain_client_frames(socket: WebSocket) -> None:
    """Read and discard whatever the client sends, until it disconnects.

    The socket is one-directional, so nothing the browser sends means anything
    here — but something has to call `receive()` or the disconnect is never
    noticed and the poll loop keeps reading SQLite for a page that closed. This
    is that call, and discarding the frame is the whole of its handling: a
    command arriving over the socket is ignored rather than acted on, because the
    three commands are `POST` routes and the socket is read-only.
    """
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        while True:
            await socket.receive()


async def watermark_socket(
    socket: WebSocket,
    *,
    reader: ConsoleReader,
    config: Config,
    mode: str,
) -> None:
    """Accept a socket and push a payload whenever the watermark moves.

    Runs until the client disconnects or the task is cancelled. Cancellation is
    what uvicorn's shutdown looks like and it is **not** swallowed: it is allowed
    to propagate after the drain task is torn down, because a coroutine that
    catches its own cancellation and returns normally is how a server ends up
    waiting on a task it already told to stop.
    """
    # Before `accept`, deliberately. See the module docstring.
    last_seen = reader.watermark()
    await socket.accept()
    drain = asyncio.ensure_future(_drain_client_frames(socket))
    try:
        while True:
            await asyncio.sleep(poll_interval_seconds(config))
            # The drain task notices the disconnect and moves the state; checking
            # it after the sleep is what stops a closed page being polled for as
            # long as the process lives.
            if socket.client_state is not WebSocketState.CONNECTED:
                break
            current = reader.watermark()
            if current == last_seen:
                # The watermark is monotonic, so a value that has not changed
                # means there is nothing to say. Never push on a bare poll.
                continue
            last_seen = current
            await _send(socket, update_payload(reader, mode=mode, watermark=current))
    except WebSocketDisconnect:
        return
    finally:
        drain.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await drain
