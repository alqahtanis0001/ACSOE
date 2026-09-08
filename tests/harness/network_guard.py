"""The guard that makes "no test touches the network" true rather than asserted.

`context/code-standards.md` requires that tests use a fake Kraken client with
recorded fixtures and that no test touches the network. That is a rule nothing
enforced, so this enforces it.

Two layers are patched, not one, and that is the whole point of spec 14 step 7:

* the **socket layer** - `socket.socket.connect`, `socket.socket.connect_ex` and
  `socket.create_connection`, which is what `websockets`, `asyncio` and anything
  hand-rolled ends up calling; and
* the **HTTP client layer** - `httpx.Client.send` and `httpx.AsyncClient.send`.

Patching only one is not a guard. An `httpx` client can be handed a transport that
never reaches the socket functions we patched, and code that opens a raw socket
never touches `httpx` at all. Each layer tags the error it raises with its own
name, so the negative test can prove *which* layer fired rather than merely that
something did.

The guard is installed and removed per test by an autouse fixture in
`tests/conftest.py`. There is deliberately no opt-out fixture: spec 14 says do not
relax the guard for convenience, and an escape hatch is the shape convenience
takes.
"""

from __future__ import annotations

import contextlib
import socket
from collections.abc import Iterator
from typing import Any

__all__ = ["NetworkAccessError", "network_guard"]

_HINT = (
    "No test touches the network (context/code-standards.md). "
    "Use the fake Kraken client in tests/harness/fake_kraken.py."
)


class NetworkAccessError(RuntimeError):
    """Raised when a test attempts to reach the network.

    `layer` is `"socket"` or `"httpx"` - which guard fired. The negative test
    asserts on it, because a guard that only patches one layer looks identical to
    a guard that patches both until you check which one caught the call.
    """

    def __init__(self, layer: str, destination: str) -> None:
        super().__init__(f"blocked {layer} network access to {destination}. {_HINT}")
        self.layer = layer
        self.destination = destination


def _describe(address: Any) -> str:
    if isinstance(address, tuple) and len(address) >= 2:
        return f"{address[0]}:{address[1]}"
    return repr(address)


@contextlib.contextmanager
def network_guard() -> Iterator[None]:
    """Block outbound network access for the duration of the block."""
    restore: list[tuple[Any, str, Any]] = []

    def _remember(target: Any, attr: str) -> None:
        restore.append((target, attr, getattr(target, attr)))

    def _guarded_connect(self: socket.socket, address: Any) -> None:
        raise NetworkAccessError("socket", _describe(address))

    def _guarded_connect_ex(self: socket.socket, address: Any) -> int:
        raise NetworkAccessError("socket", _describe(address))

    def _guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
        raise NetworkAccessError("socket", _describe(address))

    real_connect = socket.socket.connect
    real_socketpair = socket.socketpair

    def _guarded_socketpair(*args: Any, **kwargs: Any) -> Any:
        """The one hole, and it is a hole in the wall of a sealed room.

        Windows has no `socketpair` syscall, so CPython emulates it by connecting
        one loopback socket to another (`socket._fallback_socketpair`). `asyncio`
        builds its event loop's self-pipe that way, so a guard that blocks it makes
        it impossible to *create an event loop* - and `pytest-asyncio` is a declared
        dependency, so "no async tests" is not an available answer. The exchange
        client is async, which makes async the path a real accidental call takes.

        This restores the real `connect` for the duration of `socketpair()` and puts
        the guard straight back. It is not a loopback exemption: an ordinary
        loopback connect is still blocked, and every route out of the machine stays
        blocked unconditionally. Both sockets here are created inside this call and
        neither can be handed an address by a test.
        """
        saved = socket.socket.connect
        socket.socket.connect = real_connect  # type: ignore[method-assign]
        try:
            return real_socketpair(*args, **kwargs)
        finally:
            socket.socket.connect = saved  # type: ignore[method-assign]

    _remember(socket.socket, "connect")
    _remember(socket.socket, "connect_ex")
    _remember(socket, "create_connection")
    _remember(socket, "socketpair")
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
    socket.create_connection = _guarded_create_connection  # type: ignore[assignment]
    socket.socketpair = _guarded_socketpair  # type: ignore[assignment]

    # httpx is a declared dependency, but the guard must not depend on it being
    # importable: the harness has to work on a tree where the install has not
    # happened yet.
    try:
        import httpx
    except ModuleNotFoundError:
        httpx = None  # type: ignore[assignment]

    if httpx is not None:

        def _guarded_send(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
            raise NetworkAccessError("httpx", str(getattr(request, "url", request)))

        async def _guarded_async_send(self: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
            raise NetworkAccessError("httpx", str(getattr(request, "url", request)))

        _remember(httpx.Client, "send")
        _remember(httpx.AsyncClient, "send")
        httpx.Client.send = _guarded_send  # type: ignore[method-assign]
        httpx.AsyncClient.send = _guarded_async_send  # type: ignore[method-assign]

    try:
        yield
    finally:
        for target, attr, original in reversed(restore):
            setattr(target, attr, original)
