"""The live facade forwards every member of the protocols it claims. Phase 8, F1.

**The test whose absence let the defect survive.** `KrakenClient`'s docstring says it
satisfies `MarketStreamProtocol`; it did not. `recent_trades` and `drain_gaps` existed on the
transport and were never forwarded, and both callers guard the call with `getattr`, so nothing
raised at the seam:

* engine 3 published `stream_available: false` and therefore no candles, no quotes and no trade
  ranges, on every tick, live and paper;
* engine 2 recorded **zero gaps**, so the archive read as continuous across every reconnect
  (invariant 11);
* the paper broker — which wraps this very client in the only mode that can start today — raised
  `PaperBrokerError` from `_observe_trades` on every tick.

The identical walk exists against `PaperBroker` (`tests/clients/paper/test_broker.py`), and its
docstring makes the argument this file acts on: *nobody writes a test for the method they
forgot*. So the walk here is over the **protocol's own members**, discovered at runtime, never a
list retyped by hand — a list would be the same omission in a different file.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, get_type_hints

import pytest

from acsoe.clients.kraken.client import KrakenClient
from acsoe.clients.kraken.contracts import (
    KrakenClientProtocol,
    MarketStreamProtocol,
    TradeTick,
)
from acsoe.clients.kraken.ws import KrakenWebSocketClient
from tests.harness.doubles import FixedClock

AT = datetime(2026, 9, 21, 4, 0, tzinfo=UTC)


def members(protocol: type[Protocol]) -> tuple[str, ...]:  # type: ignore[valid-type]
    """The protocol's own members, from the protocol itself."""
    found = getattr(protocol, "__protocol_attrs__", None)
    assert found, f"{protocol.__name__} declares no members to walk"
    return tuple(sorted(found))


@pytest.fixture
def facade() -> KrakenClient:
    """The object an engine holds as `context.clients.kraken`.

    The stream is the real websocket client, constructed and never started: a stub would be a
    second implementation of the thing under test, which is exactly how the gap was missed.
    """
    return KrakenClient(
        rest=None,  # type: ignore[arg-type]
        stream=KrakenWebSocketClient(clock=FixedClock(AT), pairs=("XBT/USD",)),
    )


def test_the_facade_forwards_every_member_of_the_stream_protocol(
    facade: KrakenClient,
) -> None:
    absent = [name for name in members(MarketStreamProtocol) if not hasattr(facade, name)]

    assert not absent, (
        "KrakenClient does not forward " + ", ".join(absent) + " - engine 3 and the paper "
        "broker both reach these through getattr, so the omission is silent at the seam"
    )


def test_every_forwarded_stream_member_is_callable_or_a_property(
    facade: KrakenClient,
) -> None:
    """Presence is not enough: an attribute of the right name and the wrong kind satisfies
    `hasattr` and still cannot be called by the chain."""
    wrong: list[str] = []
    for name in members(MarketStreamProtocol):
        attribute = getattr(type(facade), name, None)
        if not (callable(attribute) or isinstance(attribute, property)):
            wrong.append(name)

    assert not wrong, ", ".join(wrong) + " are not methods or properties on KrakenClient"


def test_the_two_members_f1_named_answer_against_the_real_transport(
    facade: KrakenClient,
) -> None:
    """The specific defect, asserted by behaviour rather than by presence.

    A never-started stream has seen nothing, so both answer empty — which is the point: they
    answer instead of raising `AttributeError`, and `recent_trades` does not consume.
    """
    assert facade.recent_trades() == ()
    assert facade.drain_gaps() == ()
    assert facade.recent_trades() == (), "recent_trades must not consume its buffer"


def test_recent_trades_returns_the_streams_window_without_draining_it(
    facade: KrakenClient,
) -> None:
    """Engine 3 rebuilds the same bar on each of the fifteen ticks it spans, so the window has
    to survive being read. Proven against the real transport's own buffer."""
    stream = facade._stream  # the facade's own collaborator, by design of this test
    # Put one trade where the pump puts them. Reaching into the buffer is deliberate: the
    # alternative is a live socket, and what is under test is the facade's forwarding, not
    # the transport's parsing (which `test_ws.py` already covers).
    stream._trades.append(  # type: ignore[attr-defined]
        TradeTick(pair="XBT/USD", ts=AT, price=Decimal("60000.0"), qty=Decimal("0.01"))
    )

    first = facade.recent_trades()
    second = facade.recent_trades()

    assert len(first) == 1, first
    assert first == second, "the window was consumed by reading it"
    assert facade.drain_trades() == first, "drain_trades sees the same trades"
    assert facade.drain_trades() == (), "drain_trades consumes, recent_trades does not"


def test_the_facade_forwards_every_member_of_the_client_protocol(
    facade: KrakenClient,
) -> None:
    """The other protocol the module docstring claims. Walked for the same reason: the claim
    is in the docstring and nothing checked it."""
    absent = [name for name in members(KrakenClientProtocol) if not hasattr(facade, name)]

    assert not absent, "KrakenClient does not forward " + ", ".join(absent)


def test_the_walk_would_fail_on_a_facade_that_forgot_one() -> None:
    """The walk is proven capable of failing, here rather than by mutating the real class.

    A facade missing one member must be caught. Without this, a walk that silently found no
    members — a renamed `__protocol_attrs__`, say — would pass against anything.
    """

    class Forgetful:
        def drain(self) -> tuple[Any, ...]:
            return ()

    absent = [name for name in members(MarketStreamProtocol) if not hasattr(Forgetful(), name)]

    assert "recent_trades" in absent and "drain_gaps" in absent, absent


def test_the_stream_protocol_members_are_discovered_not_retyped() -> None:
    """If this file listed the members by hand it would carry the same blind spot as the class
    it checks. The list comes from the protocol, and it is not empty."""
    found = members(MarketStreamProtocol)

    assert len(found) >= 5, found
    assert "recent_trades" in found and "drain_gaps" in found
    # And the protocol's own annotations resolve, so a member added there reaches this walk.
    assert get_type_hints(MarketStreamProtocol, include_extras=False) is not None
    assert inspect.isclass(MarketStreamProtocol)
