"""Spec 84 — the order surface, and the live client's refusal to use it.

Two halves, and they fail for different reasons.

**The models.** `OrderRequest`, `OrderAck` and `OrderState` are strict about
*coupling*, not about values — a limit order with no price, a fill with no average
price, a resting order with a close time. Every one of those is a
self-contradiction the consumer would otherwise have to re-check, and "absent is
never zero" is only true if something enforces it at the boundary. Each coupling
here has a test that passes and a test that fails, because a model that refused
everything would satisfy the refusal half perfectly and be useless.

**The refusal.** The four order calls on the live client raise and make **no
request**. The assertion is on the transport's count, not on the exception alone,
for the reason `test_cache.py` spends a paragraph on: the exception proves the
call did not succeed and says nothing about whether the network was touched.
`CountingTransport` here is the same shape and — this is the part that matters —
is proven capable of counting inside the same test, by serving a real call through
it and watching the count move. A transport that counted nothing would make every
zero-call assertion in this file pass forever, which is the exact defect Phase 3
found four times.

The client is built **with credentials and with both TTLs**. Every fail-closed
path in `clients/kraken/` raises `KrakenUnavailableError` on purpose, so a client
missing either would refuse for a reason that has nothing to do with Phase 8 and
`pytest.raises(KrakenUnavailableError)` could not tell the difference. Every
refusal assertion here matches the message.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from acsoe.clients.kraken import (
    TERMINAL_ORDER_STATUSES,
    USERREF_MAX,
    USERREF_MIN,
    KrakenClient,
    KrakenRestClient,
    KrakenUnavailableError,
    KrakenWebSocketClient,
    OrderAck,
    OrderAckStatus,
    OrderClientProtocol,
    OrderRequest,
    OrderSide,
    OrderState,
    OrderStatus,
    OrderType,
    RateLimiter,
)
from acsoe.clients.kraken.rest import HttpResponse
from acsoe.platform.clock import FixedClock
from acsoe.platform.config import Credentials

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "kraken"
AT = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

PLANTED_SECRET = "c2VjcmV0LWJhc2U2NC1raW5kLW9mLXRoaW5nLXRoYXQta3Jha2VuLXVzZXM="
CREDENTIALS = Credentials(key="test-key", secret=PLANTED_SECRET)

#: Each order call, and a zero-argument way to make it. Parametrising over this
#: is what stops a fifth call being added later with no refusal test: the tuple
#: and `rest.ORDER_CALLS` are compared in a test below.
ORDER_CALLS: list[tuple[str, Any]] = [
    ("add_order", lambda client: client.add_order(a_request())),
    ("cancel_order", lambda client: client.cancel_order(7)),
    ("query_orders", lambda client: client.query_orders((7, 8))),
    ("open_orders", lambda client: client.open_orders()),
]


def a_request(**overrides: Any) -> OrderRequest:
    """A valid post-only limit buy. Overridden field by field by the model tests."""
    fields: dict[str, Any] = {
        "pair": "XBT/USD",
        "side": OrderSide.BUY,
        "order_type": OrderType.LIMIT,
        "qty": Decimal("0.01"),
        "limit_price": Decimal("50000.00"),
        "post_only": True,
        "userref": 4242,
    }
    fields.update(overrides)
    return OrderRequest(**fields)


def fixture(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return loaded


@dataclass
class CountingTransport:
    """Records one entry per request, and answers what it has been served.

    The double has to be able to exhibit the property under test, and the property
    is *a request was made*. So this counts, and every test that asserts a zero
    count also drives one real call through the same object and asserts the count
    moved. Without that control, deleting `self.calls.append(...)` would leave the
    whole file green.
    """

    bodies: dict[str, bytes] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def serve(self, fragment: str, payload: Any) -> None:
        self.bodies[fragment] = json.dumps(payload).encode()

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Any,
        content: bytes | None,
        timeout_s: float,
    ) -> HttpResponse:
        for fragment, body in self.bodies.items():
            if fragment in url:
                self.calls.append(fragment)
                return HttpResponse(status_code=200, body=body)
        self.calls.append(url)
        raise AssertionError(f"no fake response registered for {url}")


def build_rest(transport: CountingTransport) -> KrakenRestClient:
    """A client with credentials and both TTLs, so nothing else can refuse first."""
    return KrakenRestClient(
        clock=FixedClock(AT),
        limiter=RateLimiter(capacity=50, refill_per_second=50),
        transport=transport,
        credentials=CREDENTIALS,
        base_url="https://example.invalid",
        asset_pairs_ttl_s=300,
        trade_volume_ttl_s=60,
    )


def build_facade(transport: CountingTransport) -> KrakenClient:
    """The object an engine actually holds as `context.clients.kraken`.

    The stream is the real `KrakenWebSocketClient`, constructed and never started,
    for the same reason spec 39's tests use it: a stub here would be a second
    implementation of the thing the facade forwards to.
    """
    return KrakenClient(
        rest=build_rest(transport),
        stream=KrakenWebSocketClient(clock=FixedClock(AT), pairs=("XBT/USD",)),
    )


def serve_asset_pairs(transport: CountingTransport) -> None:
    transport.serve("AssetPairs", fixture("asset_pairs"))


# --------------------------------------------------------------------------- #
# The refusal: it names the method, it names the phase, it makes no request
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "invoke"), ORDER_CALLS, ids=[c[0] for c in ORDER_CALLS])
async def test_a_live_order_call_refuses_naming_the_method_and_phase_8(
    name: str, invoke: Any
) -> None:
    transport = CountingTransport()
    serve_asset_pairs(transport)
    client = build_rest(transport)

    with pytest.raises(KrakenUnavailableError) as caught:
        await invoke(client)

    message = str(caught.value)
    assert name in message, message
    assert "Phase 8" in message, message


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "invoke"), ORDER_CALLS, ids=[c[0] for c in ORDER_CALLS])
async def test_a_live_order_call_makes_zero_transport_calls(name: str, invoke: Any) -> None:
    """Zero requests — and the transport proves it can count them in the same test.

    The control is not decoration. `assert transport.calls == []` is satisfied by
    a transport that never appends, so the second half drives a call that *does*
    reach the network through the same object and asserts the count moved. The
    control runs after the refusal so it cannot mask an order call by arriving
    first.
    """
    transport = CountingTransport()
    serve_asset_pairs(transport)
    client = build_rest(transport)

    with pytest.raises(KrakenUnavailableError):
        await invoke(client)

    assert transport.calls == [], f"{name} touched the network: {transport.calls}"

    await client.asset_pairs()
    assert transport.calls == ["AssetPairs"], (
        "the control failed: this transport cannot count, so the zero above proves "
        f"nothing. calls={transport.calls}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "invoke"), ORDER_CALLS, ids=[c[0] for c in ORDER_CALLS])
async def test_the_facade_refuses_the_same_way_and_makes_no_request(
    name: str, invoke: Any
) -> None:
    """Through `KrakenClient`, which is what an engine holds.

    `rest.py` owns the refusal and the facade forwards, so this is the test that
    would notice the facade growing an implementation of its own.
    """
    transport = CountingTransport()
    serve_asset_pairs(transport)
    facade = build_facade(transport)

    with pytest.raises(KrakenUnavailableError) as caught:
        await invoke(facade)

    assert "Phase 8" in str(caught.value)
    assert name in str(caught.value)
    assert transport.calls == []

    await facade.asset_pairs()
    assert transport.calls == ["AssetPairs"]


@pytest.mark.asyncio
async def test_the_refusal_is_not_the_missing_credential_refusal() -> None:
    """Both refusals raise the same type, so the messages have to be told apart.

    A client with no credentials refuses `trade_volume` for a reason that has
    nothing to do with orders. If `add_order`'s refusal were deleted, a
    credential-less client would still raise `KrakenUnavailableError` from
    `_private` and a bare `pytest.raises` would stay green.
    """
    transport = CountingTransport()
    serve_asset_pairs(transport)
    with_credentials = build_rest(transport)
    without = KrakenRestClient(
        clock=FixedClock(AT),
        limiter=RateLimiter(capacity=50, refill_per_second=50),
        transport=transport,
        credentials=None,
        base_url="https://example.invalid",
        asset_pairs_ttl_s=300,
        trade_volume_ttl_s=60,
    )

    with pytest.raises(KrakenUnavailableError) as credentialled:
        await with_credentials.add_order(a_request())
    with pytest.raises(KrakenUnavailableError) as anonymous:
        await without.trade_volume()

    assert "Phase 8" in str(credentialled.value)
    assert "Phase 8" not in str(anonymous.value)
    assert "API credentials" in str(anonymous.value)


def test_no_order_call_is_left_without_a_refusal_test() -> None:
    """The parametrisation and the client's own list agree.

    A fifth call added to `OrderClientProtocol` and implemented in `rest.py`
    without a refusal is exactly the half-working live client spec 84 forbids, and
    it would otherwise be invisible: the tests above would keep passing on four.
    """
    from acsoe.clients.kraken import rest

    assert tuple(name for name, _ in ORDER_CALLS) == rest.ORDER_CALLS
    protocol_methods = set(OrderClientProtocol.__protocol_attrs__)
    assert protocol_methods == set(rest.ORDER_CALLS)


def test_both_clients_satisfy_the_order_protocol() -> None:
    transport = CountingTransport()
    assert isinstance(build_rest(transport), OrderClientProtocol)
    assert isinstance(build_facade(transport), OrderClientProtocol)


# --------------------------------------------------------------------------- #
# userref — the bound, asserted on the constraint
# --------------------------------------------------------------------------- #
#
# Matching the *field name* cannot fail in a model with `extra="forbid"`: the
# refusal for an unknown key always contains the key name, so `match="userref"`
# passes whether the bound rejected the value or the field was deleted outright.
# A found one of its own assertions surviving exactly that mutation in Phase 4.
# Every assertion below matches pydantic's constraint text.


@pytest.mark.parametrize(
    ("value", "constraint"),
    [
        (USERREF_MIN - 1, "greater than or equal to"),
        (USERREF_MAX + 1, "less than or equal to"),
    ],
    ids=["below the signed 32-bit floor", "above the signed 32-bit ceiling"],
)
def test_a_userref_outside_the_signed_32_bit_range_is_refused(
    value: int, constraint: str
) -> None:
    with pytest.raises(ValidationError, match=constraint):
        a_request(userref=value)


@pytest.mark.parametrize("value", [USERREF_MIN, USERREF_MAX, 0], ids=["floor", "ceiling", "zero"])
def test_the_userref_bound_is_inclusive_at_both_edges(value: int) -> None:
    """The other half of the pair. A model that refused every userref would pass
    the two refusal cases above and be unusable."""
    assert a_request(userref=value).userref == value


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (
            OrderAck,
            {"order_id": "O-1", "status": OrderAckStatus.RESTING},
        ),
        (
            OrderState,
            {
                "order_id": "O-1",
                "status": OrderStatus.RESTING,
                "filled_qty": Decimal("0"),
                "fee": Decimal("0"),
            },
        ),
    ],
    ids=["OrderAck", "OrderState"],
)
def test_the_same_userref_bound_holds_on_the_ack_and_the_state(
    model: Any, kwargs: dict[str, Any]
) -> None:
    """One bound, three models. A request refusing a value the ack would accept is
    an idempotency token that changes shape between placing and reading."""
    with pytest.raises(ValidationError, match="less than or equal to"):
        model(userref=USERREF_MAX + 1, **kwargs)
    assert model(userref=USERREF_MAX, **kwargs).userref == USERREF_MAX


# --------------------------------------------------------------------------- #
# OrderRequest — the couplings
# --------------------------------------------------------------------------- #


def test_a_limit_order_without_a_price_is_refused() -> None:
    with pytest.raises(ValidationError, match="nothing for it to rest at"):
        a_request(limit_price=None)


def test_a_market_order_with_a_price_is_refused() -> None:
    with pytest.raises(ValidationError, match="market order has no limit_price"):
        a_request(order_type=OrderType.MARKET, post_only=False, limit_price=Decimal("50000"))


def test_a_market_order_without_a_price_is_accepted() -> None:
    """Rule 14's liquidation exits as a taker. A contract that could not express
    one would make the emergency stop unimplementable."""
    request = a_request(order_type=OrderType.MARKET, post_only=False, limit_price=None)
    assert request.limit_price is None
    assert request.order_type is OrderType.MARKET


def test_post_only_on_a_market_order_is_refused() -> None:
    with pytest.raises(ValidationError, match="always takes liquidity"):
        a_request(order_type=OrderType.MARKET, post_only=True, limit_price=None)


def test_post_only_has_no_default() -> None:
    """Invariant 8 makes an entry post-only and invariant 14 makes a liquidation a
    taker, so a default is silently wrong at one of the two call sites — and the
    wrong direction is an entry that crosses the book and pays taker fees the cost
    gate never priced."""
    with pytest.raises(ValidationError, match="Field required"):
        OrderRequest(
            pair="XBT/USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            qty=Decimal("0.01"),
            limit_price=Decimal("50000.00"),
            userref=1,
        )


@pytest.mark.parametrize("qty", [Decimal("0"), Decimal("-0.01")], ids=["zero", "negative"])
def test_a_non_positive_quantity_is_refused(qty: Decimal) -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        a_request(qty=qty)


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1")], ids=["zero", "negative"])
def test_a_non_positive_limit_price_is_refused(price: Decimal) -> None:
    with pytest.raises(ValidationError, match="limit price must be greater than zero"):
        a_request(limit_price=price)


def test_a_float_price_is_refused_rather_than_coerced() -> None:
    """By the time a float reaches a validator the precision is already gone."""
    with pytest.raises(ValidationError, match="has already lost precision"):
        a_request(limit_price=50000.01)


def test_an_unknown_field_is_refused_and_the_request_is_frozen() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        a_request(oflags="post")
    request = a_request()
    with pytest.raises(ValidationError):
        request.qty = Decimal("1")  # type: ignore[misc]


def test_the_request_crosses_state_with_money_as_strings() -> None:
    """`EngineResult.data` refuses a `Decimal` and silently accepts a `float`, so
    the conversion has to be exact and has to keep the trailing zeros."""
    assert a_request().state_dict() == {
        "pair": "XBT/USD",
        "side": "buy",
        "order_type": "limit",
        "qty": "0.01",
        "limit_price": "50000.00",
        "post_only": True,
        "userref": 4242,
    }


# --------------------------------------------------------------------------- #
# OrderAck — reason exactly when rejected
# --------------------------------------------------------------------------- #


def an_ack(**overrides: Any) -> OrderAck:
    fields: dict[str, Any] = {
        "userref": 4242,
        "order_id": "OQCLML-BW3P3-BUCMWZ",
        "status": OrderAckStatus.RESTING,
    }
    fields.update(overrides)
    return OrderAck(**fields)


def test_a_rejection_names_its_cause() -> None:
    ack = an_ack(status=OrderAckStatus.REJECTED, reason="post-only order would have crossed")
    assert ack.status is OrderAckStatus.REJECTED
    assert ack.reason == "post-only order would have crossed"


@pytest.mark.parametrize("reason", [None, "", "   "], ids=["absent", "empty", "whitespace"])
def test_a_rejection_with_no_cause_is_refused(reason: str | None) -> None:
    with pytest.raises(ValidationError, match="must name why it was rejected"):
        an_ack(status=OrderAckStatus.REJECTED, reason=reason)


@pytest.mark.parametrize(
    "status", [OrderAckStatus.RESTING, OrderAckStatus.FILLED], ids=["resting", "filled"]
)
def test_a_reason_on_an_accepted_order_is_refused(status: OrderAckStatus) -> None:
    with pytest.raises(ValidationError, match="reason belongs to a rejection"):
        an_ack(status=status, reason="something happened")


def test_an_accepted_ack_carries_no_reason() -> None:
    assert an_ack().reason is None


def test_the_ack_statuses_compare_equal_to_the_order_statuses_they_share() -> None:
    """Two enums, one vocabulary. A consumer holding either may compare against
    either, which is what keeps `ack.status == state.status` meaningful across the
    placement and the first query."""
    assert OrderAckStatus.RESTING == OrderStatus.RESTING
    assert OrderAckStatus.FILLED == OrderStatus.FILLED
    assert OrderAckStatus.REJECTED == OrderStatus.REJECTED
    assert {str(s) for s in OrderAckStatus} < {str(s) for s in OrderStatus}


# --------------------------------------------------------------------------- #
# OrderState — the four couplings
# --------------------------------------------------------------------------- #


def a_state(**overrides: Any) -> OrderState:
    fields: dict[str, Any] = {
        "userref": 4242,
        "order_id": "OQCLML-BW3P3-BUCMWZ",
        "status": OrderStatus.RESTING,
        "filled_qty": Decimal("0"),
        "fee": Decimal("0"),
    }
    fields.update(overrides)
    return OrderState(**fields)


def a_filled_state(**overrides: Any) -> OrderState:
    return a_state(
        status=OrderStatus.FILLED,
        filled_qty=Decimal("0.01"),
        avg_fill_price=Decimal("49999.90"),
        fee=Decimal("1.10"),
        closed_at=1_772_000_000_000_000,
        **overrides,
    )


def test_a_resting_order_has_no_fill_no_fee_and_no_close_time() -> None:
    state = a_state()
    assert state.avg_fill_price is None
    assert state.closed_at is None
    assert state.filled_qty == Decimal("0")


def test_a_filled_order_carries_its_price_fee_and_close_time() -> None:
    state = a_filled_state()
    assert state.avg_fill_price == Decimal("49999.90")
    assert state.fee == Decimal("1.10")
    assert state.closed_at == 1_772_000_000_000_000


def test_a_fill_without_an_average_price_is_refused() -> None:
    with pytest.raises(ValidationError, match="cannot be valued"):
        a_state(
            status=OrderStatus.FILLED,
            filled_qty=Decimal("0.01"),
            avg_fill_price=None,
            fee=Decimal("1.10"),
            closed_at=1,
        )


def test_an_average_price_on_an_unfilled_order_is_refused() -> None:
    """Zero is not a cost basis and neither is a price for a fill that never
    happened."""
    with pytest.raises(ValidationError, match="absent is not"):
        a_state(avg_fill_price=Decimal("49999.90"))


def test_a_fee_on_an_order_that_filled_nothing_is_refused() -> None:
    with pytest.raises(ValidationError, match="filled nothing paid no fee"):
        a_state(fee=Decimal("0.01"))


def test_a_filled_status_with_nothing_filled_is_refused() -> None:
    with pytest.raises(ValidationError, match="filled_qty is zero"):
        a_state(status=OrderStatus.FILLED, closed_at=1)


@pytest.mark.parametrize("status", sorted(TERMINAL_ORDER_STATUSES), ids=str)
def test_a_terminal_status_without_a_close_time_is_refused(status: OrderStatus) -> None:
    filled = status is OrderStatus.FILLED
    with pytest.raises(ValidationError, match="which is over"):
        a_state(
            status=status,
            filled_qty=Decimal("0.01") if filled else Decimal("0"),
            avg_fill_price=Decimal("1") if filled else None,
            fee=Decimal("0.01") if filled else Decimal("0"),
            closed_at=None,
        )


def test_a_resting_order_with_a_close_time_is_refused() -> None:
    with pytest.raises(ValidationError, match="which is not over"):
        a_state(closed_at=1)


@pytest.mark.parametrize(
    "status",
    [OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED],
    ids=str,
)
def test_an_order_cancelled_after_a_partial_fill_keeps_its_fill(status: OrderStatus) -> None:
    """The case the couplings must not forbid. A post-only entry that filled half
    and was then cancelled at the unfilled window has a real fill, a real fee and a
    real close time, and B's ledger has to be able to express it."""
    state = a_state(
        status=status,
        filled_qty=Decimal("0.004"),
        avg_fill_price=Decimal("50000.00"),
        fee=Decimal("0.44"),
        closed_at=1_772_000_000_000_000,
    )
    assert state.filled_qty == Decimal("0.004")
    assert state.status is status


def test_a_partially_filled_order_may_still_be_resting() -> None:
    state = a_state(filled_qty=Decimal("0.004"), avg_fill_price=Decimal("50000.00"),
                    fee=Decimal("0.44"))
    assert state.closed_at is None
    assert state.status is OrderStatus.RESTING


@pytest.mark.parametrize("field_name", ["filled_qty", "fee"], ids=str)
def test_a_negative_quantity_or_fee_is_refused(field_name: str) -> None:
    with pytest.raises(ValidationError, match="never negative"):
        a_state(**{field_name: Decimal("-0.01")})


def test_the_state_crosses_state_with_money_as_strings() -> None:
    assert a_filled_state().state_dict() == {
        "userref": 4242,
        "order_id": "OQCLML-BW3P3-BUCMWZ",
        "status": "filled",
        "filled_qty": "0.01",
        "avg_fill_price": "49999.90",
        "fee": "1.10",
        "closed_at": 1_772_000_000_000_000,
    }
