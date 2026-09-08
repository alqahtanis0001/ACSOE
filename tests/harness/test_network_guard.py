"""Proof that the network guard actually fires. Spec 14 step 7.

A guard that has never been shown to fail is not a guard, it is a comment - the
same reasoning as spec 02's `docs_vocabulary` negative test.

These tests make **genuine** outbound attempts: a real `socket` object calling
`connect` on a real address, and a real `httpx` client issuing a real request.
Nothing is mocked on the calling side. The addresses are RFC 5737 TEST-NET-3
(`203.0.113.0/24`), which is reserved for documentation and is not routable, and
every attempt carries a short timeout - so in the one case that matters, where the
guard is broken and the call goes through, the test fails on a timeout against a
black hole rather than contacting a real service. Proving the guard works must not
itself be the thing that touches the network.

Both layers are proved separately, and by the layer that caught the call rather
than merely by "something raised". `NetworkAccessError.layer` is what makes that
possible: an httpx request that reported `layer == "socket"` would mean the httpx
patch was absent and the call had reached the socket functions, which is exactly
the half-guard spec 14 warns about.
"""

from __future__ import annotations

import socket

import pytest

from tests.harness.network_guard import NetworkAccessError, network_guard

# Reserved for documentation (RFC 5737). Not routable, and needs no DNS lookup.
BLACKHOLE_HOST = "203.0.113.1"
BLACKHOLE_PORT = 9  # discard
TIMEOUT_S = 0.25


def test_socket_connect_is_blocked() -> None:
    """A real socket, a real connect, a real address."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT_S)
    try:
        with pytest.raises(NetworkAccessError) as caught:
            sock.connect((BLACKHOLE_HOST, BLACKHOLE_PORT))
    finally:
        sock.close()

    assert caught.value.layer == "socket"
    assert BLACKHOLE_HOST in caught.value.destination
    assert "No test touches the network" in str(caught.value)


def test_socket_connect_ex_is_blocked() -> None:
    """`connect_ex` returns an error code instead of raising, so code that uses it
    would slip past a guard that only patched `connect`."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT_S)
    try:
        with pytest.raises(NetworkAccessError) as caught:
            sock.connect_ex((BLACKHOLE_HOST, BLACKHOLE_PORT))
    finally:
        sock.close()
    assert caught.value.layer == "socket"


def test_create_connection_is_blocked() -> None:
    """`socket.create_connection` is a module-level function, not a method, so it
    is a third patch and not a consequence of the first two."""
    with pytest.raises(NetworkAccessError) as caught:
        socket.create_connection((BLACKHOLE_HOST, BLACKHOLE_PORT), timeout=TIMEOUT_S)
    assert caught.value.layer == "socket"


def test_httpx_request_is_blocked_at_the_http_layer() -> None:
    """The HTTP client layer fires on its own, before any socket is reached.

    `layer == "httpx"` is the assertion that matters. If this reported `"socket"`
    it would mean the httpx patch was missing and the request had fallen through to
    the socket functions - which is the exact bypass spec 14 describes, and it
    would still have raised, so asserting only "it raised" would not catch it.
    """
    httpx = pytest.importorskip("httpx")
    with httpx.Client(timeout=TIMEOUT_S) as client, pytest.raises(NetworkAccessError) as caught:
        client.get(f"http://{BLACKHOLE_HOST}:{BLACKHOLE_PORT}/")

    assert caught.value.layer == "httpx"
    assert BLACKHOLE_HOST in caught.value.destination


@pytest.mark.asyncio
async def test_httpx_async_request_is_blocked_at_the_http_layer() -> None:
    """The async client is a separate class with a separate `send`.

    The exchange client is async (`code-standards.md`), so this is the path a real
    accidental call would take, not the sync one.
    """
    httpx = pytest.importorskip("httpx")
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        with pytest.raises(NetworkAccessError) as caught:
            await client.get(f"http://{BLACKHOLE_HOST}:{BLACKHOLE_PORT}/")
    assert caught.value.layer == "httpx"


def test_guard_restores_what_it_patched() -> None:
    """A guard that leaks its patches would silently disarm the next test.

    Entered inside the autouse guard, so what it must restore is the *outer*
    guard's functions, not the pristine ones.
    """
    before_connect = socket.socket.connect
    before_create = socket.create_connection
    with network_guard():
        assert socket.socket.connect is not before_connect
    assert socket.socket.connect is before_connect
    assert socket.create_connection is before_create


def test_the_guard_is_installed_for_every_test_without_asking() -> None:
    """The autouse fixture is what makes the rule true rather than asserted.

    No test in this repository opts in to the guard, and there is deliberately no
    fixture that opts out.
    """
    with pytest.raises(NetworkAccessError):
        socket.create_connection((BLACKHOLE_HOST, BLACKHOLE_PORT), timeout=TIMEOUT_S)


def test_loopback_is_still_blocked_for_ordinary_code() -> None:
    """The `socketpair` exemption is not a loopback exemption.

    `asyncio` needs a loopback connect to build an event loop on Windows, and the
    guard lets exactly that one call through. Everything else aimed at loopback -
    a console on 127.0.0.1, a local proxy, anything a test might reach for out of
    convenience - is still refused.
    """
    with pytest.raises(NetworkAccessError) as caught:
        socket.create_connection(("127.0.0.1", 8765), timeout=TIMEOUT_S)
    assert caught.value.layer == "socket"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(TIMEOUT_S)
    try:
        with pytest.raises(NetworkAccessError):
            sock.connect(("127.0.0.1", 8765))
    finally:
        sock.close()


def test_socketpair_still_works_and_leaves_the_guard_armed() -> None:
    """The exemption is scoped to the call and puts the guard straight back."""
    left, right = socket.socketpair()
    try:
        left.sendall(b"ping")
        assert right.recv(4) == b"ping"
    finally:
        left.close()
        right.close()

    with pytest.raises(NetworkAccessError):
        socket.create_connection((BLACKHOLE_HOST, BLACKHOLE_PORT), timeout=TIMEOUT_S)
