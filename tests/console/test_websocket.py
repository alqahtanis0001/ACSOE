"""The watermark push. Spec 23.

Four properties get the attention, and each is a thing the spec argues for rather
than a behaviour it merely describes:

* **A push arrives within twice `console.poll_interval_ms` of a change**, measured
  against the interval read from config rather than against a number written here.
* **Silence across several intervals when the watermark has not moved.** A socket
  that pushed on every poll would pass the first assertion and fail the design:
  the watermark is monotonic, so an unchanged value means there is nothing to say.
* **A dropped socket is a visible state that reconnects with backoff**, and the
  page never falls back to polling the API on a timer.
* **Neither interval is ever a literal.** Asserted by grep over the whole console
  package, because the failure mode is a copy of the default appearing in one file
  and quietly surviving an operator retuning the config.

Driven through the ASGI interface directly, the way uvicorn drives it, for the
reason `test_app.py` gives: the repository's network guard patches
`httpx.Client.send` for every test, and `fastapi.testclient` is an `httpx.Client`.
There is no socket anywhere in this file.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from acsoe.console.app import create_app
from acsoe.console.reader import ConsoleReader
from acsoe.console.websocket import (
    KEY_POLL_INTERVAL,
    UPDATE_MESSAGE,
    poll_interval_seconds,
    screen_payloads,
)

STALE_AFTER_MS = 120_000

#: A poll interval short enough that a test does not spend seconds waiting, and
#: long enough that it is not measuring scheduler jitter. Passed through the same
#: config surface the production value comes from, so nothing about the code path
#: is special-cased for the test.
TEST_POLL_MS = 20

#: How many intervals of quiet the silence test waits through. Several, because a
#: single one cannot distinguish "does not push on a bare poll" from "has not
#: reached its first poll yet".
QUIET_INTERVALS = 6


class _StubConfig:
    """Two keys, and it raises on anything else so a third is named here first."""

    def __init__(self, poll_ms: int = TEST_POLL_MS) -> None:
        self._values = {
            "console.stale_after_ms": STALE_AFTER_MS,
            KEY_POLL_INTERVAL: poll_ms,
        }
        self.reads: list[str] = []

    @property
    def mode(self) -> Any:
        return "paper"

    def get(self, dotted_key: str, /) -> Any:
        self.reads.append(dotted_key)
        return self._values[dotted_key]


class Socket:
    """One ASGI WebSocket connection, driven without a server.

    Two queues and a task: exactly what uvicorn provides the application, minus
    the network. `frames` collects everything the endpoint sent, so a test can
    assert on what arrived *and* on nothing having arrived.
    """

    def __init__(self, app: Any, path: str = "/ws") -> None:
        self._app = app
        self._path = path
        self._inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.frames: list[dict[str, Any]] = []
        self._task: asyncio.Task[None] | None = None

    async def _receive(self) -> dict[str, Any]:
        return await self._inbound.get()

    async def _send(self, message: dict[str, Any]) -> None:
        await self.outbound.put(message)

    async def open(self) -> dict[str, Any]:
        scope: dict[str, Any] = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": self._path,
            "raw_path": self._path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"console.test")],
            "client": ("test", 0),
            "server": ("console.test", 80),
            "subprotocols": [],
        }
        await self._inbound.put({"type": "websocket.connect"})
        self._task = asyncio.ensure_future(self._app(scope, self._receive, self._send))
        return await asyncio.wait_for(self.outbound.get(), timeout=5)

    async def next_push(self, timeout: float) -> dict[str, Any] | None:
        """The next payload the endpoint sent, or None if it stayed quiet."""
        try:
            message = await asyncio.wait_for(self.outbound.get(), timeout=timeout)
        except TimeoutError:
            return None
        if message.get("type") != "websocket.send":
            return None
        payload: dict[str, Any] = json.loads(message["text"])
        self.frames.append(payload)
        return payload

    async def disconnect(self) -> None:
        await self._inbound.put({"type": "websocket.disconnect", "code": 1000})

    async def close(self) -> None:
        await self.disconnect()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task


@pytest.fixture
def poll_config() -> _StubConfig:
    return _StubConfig()


@pytest.fixture
def socket_app(seeded_db: Path, seed_clock: Any, poll_config: _StubConfig) -> Any:
    app = create_app(poll_config, db_path=seeded_db, clock=seed_clock)
    try:
        yield app
    finally:
        app.state.reader.close()
        app.state.command_writer.close()


def move_the_watermark(db_path: Path) -> None:
    """Write a row the way the daemon would, from a separate connection.

    Deliberately not through the console's own handles: the console's reader is
    read-only and its command writer touches one table, and the point is that a
    change made by *the other process* is what the socket notices.
    """
    conn = sqlite3.connect(db_path)
    try:
        highest = conn.execute("SELECT MAX(updated_at) FROM runs").fetchone()[0] or 0
        conn.execute(
            "UPDATE runs SET updated_at = ? WHERE run_id = "
            "(SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1)",
            (int(highest) + 1_000_000,),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# A push arrives within twice the configured interval
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_change_reaches_a_connected_client_within_two_poll_intervals(
    socket_app: Any, seeded_db: Path, poll_config: _StubConfig
) -> None:
    """The budget comes from config, never from a literal.

    The watermark is moved **after** the handshake is accepted, which is the case
    that fails if the server takes its baseline reading after accepting rather
    than before: the write lands first, the first read already reflects it, the
    value never appears to move, and nothing is ever pushed.
    """
    socket = Socket(socket_app)
    try:
        handshake = await socket.open()
        assert handshake["type"] == "websocket.accept"

        move_the_watermark(seeded_db)

        budget = 2 * poll_interval_seconds(poll_config)
        payload = await socket.next_push(timeout=budget + 1.0)
        assert payload is not None, f"nothing pushed inside {budget}s"
        assert payload["type"] == UPDATE_MESSAGE
        assert payload["watermark"] > 0
    finally:
        await socket.close()


@pytest.mark.asyncio
async def test_the_push_carries_every_screen_from_the_same_view_models(
    socket_app: Any, seeded_db: Path, seed_clock: Any
) -> None:
    """The socket and the plain endpoints can never disagree about what a screen
    says, because there is one composition and both call it."""
    socket = Socket(socket_app)
    try:
        await socket.open()
        move_the_watermark(seeded_db)
        payload = await socket.next_push(timeout=2.0)
        assert payload is not None
    finally:
        await socket.close()

    with ConsoleReader(seeded_db, clock=seed_clock, stale_after_ms=STALE_AFTER_MS) as reader:
        expected = screen_payloads(reader, mode="paper")
    for screen in ("state", "feed", "history", "research"):
        assert payload[screen] == json.loads(json.dumps(expected[screen]))


# --------------------------------------------------------------------------- #
# Silence when the watermark has not moved
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_nothing_is_pushed_across_several_intervals_when_nothing_changed(
    socket_app: Any, poll_config: _StubConfig
) -> None:
    """The assertion a socket that pushed on every poll would fail.

    Also the assertion that fixes the design of the *connect* path: the page's
    first content comes from the four `GET` endpoints, not from a snapshot over
    the socket, so a connected client that nothing has happened to hears nothing
    at all.
    """
    socket = Socket(socket_app)
    try:
        await socket.open()
        quiet = QUIET_INTERVALS * poll_interval_seconds(poll_config)
        assert await socket.next_push(timeout=quiet) is None
    finally:
        await socket.close()


@pytest.mark.asyncio
async def test_a_second_push_needs_a_second_change(
    socket_app: Any, seeded_db: Path, poll_config: _StubConfig
) -> None:
    """Two changes, two pushes, and nothing in between.

    The stronger form of the silence test: a socket that has already pushed once
    must go quiet again rather than repeating itself every interval.
    """
    socket = Socket(socket_app)
    try:
        await socket.open()
        move_the_watermark(seeded_db)
        first = await socket.next_push(timeout=2.0)
        assert first is not None

        quiet = QUIET_INTERVALS * poll_interval_seconds(poll_config)
        assert await socket.next_push(timeout=quiet) is None

        move_the_watermark(seeded_db)
        second = await socket.next_push(timeout=2.0)
        assert second is not None
        assert second["watermark"] > first["watermark"]
    finally:
        await socket.close()


# --------------------------------------------------------------------------- #
# The interval comes from config on every read
# --------------------------------------------------------------------------- #


def test_the_interval_is_read_from_config_and_not_captured_once() -> None:
    """An operator who retunes the file gets the new cadence on an open socket."""
    config = _StubConfig(poll_ms=500)
    assert poll_interval_seconds(config) == 0.5
    config._values[KEY_POLL_INTERVAL] = 250
    assert poll_interval_seconds(config) == 0.25


def test_a_non_positive_interval_is_refused_rather_than_clamped() -> None:
    """A silently corrected interval is a misconfiguration nobody ever finds, and
    a zero would turn the poll loop into a busy loop against SQLite."""
    for bad in (0, -1):
        with pytest.raises(ValueError, match=KEY_POLL_INTERVAL):
            poll_interval_seconds(_StubConfig(poll_ms=bad))


@pytest.mark.asyncio
async def test_the_socket_reads_the_interval_on_every_iteration(
    socket_app: Any, poll_config: _StubConfig
) -> None:
    """Not once at connect, and not once at construction."""
    socket = Socket(socket_app)
    try:
        await socket.open()
        await socket.next_push(timeout=QUIET_INTERVALS * poll_interval_seconds(poll_config))
    finally:
        await socket.close()
    assert poll_config.reads.count(KEY_POLL_INTERVAL) > 1


#: The two default values, which are the README's *defaults* and not a second
#: source of truth. Either appearing as a number in console code is the defect.
_FORBIDDEN_INTERVALS = (500, 120_000)


def _console_files(suffix: str) -> dict[str, str]:
    import acsoe.console as package

    directory = Path(str(package.__file__)).parent
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(directory.rglob("*" + suffix))
    }


def _strip_js_comments(source: str) -> str:
    """Block and line comments out, string literals left alone.

    Crude on purpose. It only has to be right enough that a *number in prose* is
    not mistaken for a number in code, and the file it runs against carries no
    `//` inside a string — the one place that would matter is a URL, and the test
    below asserts there is no absolute URL in the file at all.
    """
    without_blocks = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"^\s*//.*$", " ", without_blocks, flags=re.M)


def test_no_python_module_in_the_console_carries_either_interval_as_a_number() -> None:
    """Asserted on the parsed constants, not on a text search.

    A text search over these files finds `500` in a sentence explaining why `500`
    must not be written down, which is the check failing on its own rationale.
    Walking the AST for integer constants finds numbers in *code* and nothing
    else: a docstring is a string constant and a comment is not in the tree at
    all, so the prose can say what it needs to and the assertion stays exact.
    """
    import ast

    hits: list[str] = []
    for name, source in _console_files(".py").items():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and node.value in _FORBIDDEN_INTERVALS:
                if isinstance(node.value, bool) or not isinstance(node.value, int):
                    continue
                hits.append(f"{name}:{node.lineno}: {node.value}")
    assert hits == [], hits


def test_the_browser_carries_neither_interval_either() -> None:
    """An interval hardcoded in the page defeats the design as completely as one
    hardcoded in the server, and it is the likelier of the two."""
    hits: list[str] = []
    for name, source in _console_files(".js").items():
        code = _strip_js_comments(source)
        for number, line in enumerate(code.splitlines(), start=1):
            for literal in _FORBIDDEN_INTERVALS:
                if re.search(r"(?<![\w.])" + str(literal) + r"(?![\w.])", line):
                    hits.append(f"{name}:{number}: {line.strip()}")
    for name, source in _console_files(".html").items():
        markup = re.sub(r"<!--.*?-->", " ", source, flags=re.S)
        for literal in _FORBIDDEN_INTERVALS:
            assert not re.search(r"(?<![\w.])" + str(literal) + r"(?![\w.])", markup), name
    assert hits == [], hits


def test_the_stylesheet_declares_one_duration_and_it_is_the_flash() -> None:
    """The CSS is checked on its *time* values rather than on the two numbers.

    `500` is a legitimate font weight and appears in the type scale of
    `ui-context.md`; grepping a stylesheet for it asserts nothing about intervals
    and fails on a rule that is correct. What matters here is that the only
    duration anywhere is the 200ms flash — the one permitted motion — so that is
    what is asserted.
    """
    durations: list[str] = []
    for name, source in _console_files(".css").items():
        stripped = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
        for match in re.finditer(r"(?<![\w.-])(\d+(?:\.\d+)?)(ms|s)(?![\w-])", stripped):
            durations.append(f"{name}: {match.group(0)}")
    assert durations == ["tokens.css: 200ms"], durations


# --------------------------------------------------------------------------- #
# The socket is read-only, and one-directional
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_frame_sent_by_the_client_is_ignored_and_writes_nothing(
    socket_app: Any, seeded_db: Path
) -> None:
    """The socket is one-directional. A command arriving over it is not a command.

    Spec 24 puts the three commands on `POST` routes; a socket that accepted one
    would be a second write path that nothing in the phase criteria checks.
    """
    before = _command_count(seeded_db)
    socket = Socket(socket_app)
    try:
        await socket.open()
        await socket._inbound.put(
            {"type": "websocket.receive", "text": json.dumps({"command": "close_all"})}
        )
        assert await socket.next_push(timeout=0.2) is None
    finally:
        await socket.close()
    assert _command_count(seeded_db) == before


def _command_count(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM commands").fetchone()[0])
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_the_socket_never_opens_a_writable_connection(socket_app: Any) -> None:
    """The reader it polls is the same read-only one every `GET` route uses."""
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        socket_app.state.reader.store.connection.execute("DELETE FROM commands")


# --------------------------------------------------------------------------- #
# Motion, and the disconnected state, in the one file that owns them
# --------------------------------------------------------------------------- #


def _console_js() -> str:
    import acsoe.console as package

    return (Path(str(package.__file__)).parent / "static" / "console.js").read_text(
        encoding="utf-8"
    )


def test_the_client_never_polls_the_api_on_a_timer() -> None:
    """The scope limit spec 23 states most plainly.

    The one `setTimeout` in the file is the reconnect backoff, and there is no
    `setInterval` at all. A browser-side polling fallback would quietly replace
    the design with the thing the design rejected, and it would still pass every
    other assertion here.
    """
    source = _console_js()
    assert "setInterval" not in source
    assert source.count("setTimeout") == 1
    # The single timer must be the reconnect, not a fetch on a schedule.
    timer_line = next(line for line in source.splitlines() if "setTimeout" in line)
    assert "reconnectTimer" in timer_line


def test_the_client_uses_no_framework_no_bundler_and_no_third_party() -> None:
    """Vanilla JavaScript, no npm, no build step, nothing from a CDN."""
    source = _console_js()
    for forbidden in ("import ", "require(", "//cdn", "https://", "http://"):
        assert forbidden not in source, forbidden


def test_the_only_motion_is_the_flash_and_it_fires_on_a_real_change() -> None:
    """A value that did not change does not flash.

    That is what makes the flash worth having: the load-time fetch can overtake
    the socket's baseline and produce one redundant push, and a flash on every
    push would light the whole band up for nothing. `setText` compares against
    what is on the screen and returns early when they match.
    """
    source = _console_js()
    assert "if (element.textContent === next)" in source
    assert 'classList.add(FLASH_CLASS)' in source
    # No other animation is started from JavaScript. The duration and the
    # reduced-motion opt-out both live in CSS, so `prefers-reduced-motion` drops
    # the flash without this file knowing anything about it.
    for forbidden in ("requestAnimationFrame", ".animate(", "transition"):
        assert forbidden not in source, forbidden


def test_a_dropped_socket_is_a_visible_state_that_reconnects_with_backoff() -> None:
    """Not a silently frozen screen, and not an infinitely tight retry loop."""
    source = _console_js()
    assert "showConnection(" in source
    assert "scheduleReconnect" in source
    assert "RECONNECT_MIN_MS" in source
    assert "RECONNECT_MAX_MS" in source
    assert "Math.min(reconnectDelay * 2, RECONNECT_MAX_MS)" in source


def test_the_reconnect_backoff_is_not_the_poll_interval_wearing_a_hat() -> None:
    """They are unrelated numbers and must not be confused for one another.

    The backoff governs how hard a browser retries a socket the server is not
    answering, which has no config key; the poll interval governs how often the
    *server* reads the watermark, which does. A file that reused the config value
    for the backoff would be reading a trading-side setting to decide a browser
    retry, and would go wrong in both directions when either was retuned.
    """
    code = _strip_js_comments(_console_js())
    assert KEY_POLL_INTERVAL not in code
    assert "poll" not in code.lower()
    # Staleness still reaches the page, but as a decided verdict on the payload
    # rather than as a threshold the browser compares against its own clock.
    assert "is_stale" in code
    assert "age_text" in code
