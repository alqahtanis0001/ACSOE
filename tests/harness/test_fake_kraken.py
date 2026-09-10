"""The fake exchange must match the real client's contract. Spec 15.

The three checks spec 15 names are `test_satisfies_the_protocol`,
`test_configured_transport_failure_raises_the_real_error_type` and
`test_http_200_with_a_populated_error_array_is_a_failure`. The rest exist because a
fake that is *kinder* than reality hides fail-closed bugs, and the retention rules
of invariant 2 are the easiest place to be accidentally kind.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.harness.fake_kraken import (
    FakeKrakenClient,
    KrakenAPIError,
    KrakenClientProtocol,
    KrakenError,
    KrakenUnavailableError,
)
from tests.harness.network_guard import NetworkAccessError


def test_satisfies_the_protocol(fake_kraken: FakeKrakenClient) -> None:
    assert isinstance(fake_kraken, KrakenClientProtocol)


def test_is_accepted_where_the_real_clients_protocol_is_expected(
    fake_kraken: FakeKrakenClient,
) -> None:
    """Checked against the lead's declaration too, once it exists.

    Skips rather than passing vacuously while `core/contracts.py` is unwritten, so
    this becomes a real assertion the moment spec 04 lands instead of quietly
    staying green.
    """
    contracts = pytest.importorskip(
        "acsoe.core.contracts", reason="core/contracts.py does not exist yet"
    )
    clients_protocol = getattr(contracts, "Clients", None)
    if clients_protocol is None:
        pytest.skip("acsoe.core.contracts.Clients does not exist yet")
    for method in ("asset_pairs", "trade_volume", "balance", "order_book"):
        assert callable(getattr(fake_kraken, method, None)), method


@pytest.mark.asyncio
async def test_reads_the_committed_fixtures_as_decimals(fake_kraken: FakeKrakenClient) -> None:
    """Money never crosses this boundary as a float. `code-standards.md`."""
    pairs = await fake_kraken.asset_pairs()
    rule = pairs.pairs["BTC/USD"]
    assert isinstance(rule.ordermin, Decimal)
    assert isinstance(rule.costmin, Decimal)
    assert isinstance(rule.tick_size, Decimal)

    fees = await fake_kraken.trade_volume()
    assert isinstance(fees.maker_fee_pct, Decimal)
    assert isinstance(fees.taker_fee_pct, Decimal)

    balances = await fake_kraken.balance()
    assert all(isinstance(v, Decimal) for v in balances.balances.values())

    book = await fake_kraken.order_book("BTC/USD")
    assert isinstance(book.spread, Decimal)
    assert book.spread > 0


@pytest.mark.asyncio
async def test_every_value_is_injectable(fake_kraken: FakeKrakenClient) -> None:
    """Phase 3 varies the fee tier and the balances and watches the universe filter
    and the cost gate respond, so both have to be settable per test."""
    fake_kraken.set_fee_tier(tier=3, maker_fee_pct="0.0011", taker_fee_pct="0.0019")
    fees = await fake_kraken.trade_volume()
    assert fees.tier == 3
    assert fees.maker_fee_pct == Decimal("0.0011")

    fake_kraken.set_balances({"USD": "12.34"})
    balances = await fake_kraken.balance()
    assert balances.balances == {"USD": Decimal("12.34")}

    fake_kraken.set_pair_rule("BTC/USD", ordermin="0.5", costmin="25000.00")
    pairs = await fake_kraken.asset_pairs()
    assert pairs.pairs["BTC/USD"].ordermin == Decimal("0.5")

    fake_kraken.set_order_book("BTC/USD", bids=[("100.0", "1")], asks=[("101.0", "1")])
    book = await fake_kraken.order_book("BTC/USD")
    assert book.spread == Decimal("1.0")


def test_the_harness_is_using_the_real_error_types_not_its_own_fallbacks() -> None:
    """The assertion the test below needs and did not have. Found by A, 2026-09-10.

    `fake_kraken.py` imports the three error classes from `acsoe.clients.kraken` and
    defines its own on `ImportError` — correct when written, because `clients/kraken/`
    was Phase 2 and this harness is Phase 0. The fallback is still reachable today:
    `tests/verify/` drives criteria against fabricated trees carrying `tests/` and no
    `src/`, and the harness imports there with no real client to find.

    So the fallback stays. What was missing is anything noticing **which branch is
    live**, and the test below cannot: it imports `KrakenError` from the harness, so
    against the fallback both sides move together and it passes while asserting
    nothing about the real client. A simulated the fallback by blocking
    `acsoe.clients.kraken` at the import system and confirmed the whole test still
    passes against classes that are not the real error type.

    That is the same shape as a mock agreeing with its caller, and it is the third
    time this project has found it. One identity check settles it.
    """
    from acsoe.clients.kraken import KrakenAPIError as RealAPIError
    from acsoe.clients.kraken import KrakenError as RealError
    from acsoe.clients.kraken import KrakenUnavailableError as RealUnavailable

    assert KrakenError is RealError
    assert KrakenAPIError is RealAPIError
    assert KrakenUnavailableError is RealUnavailable


@pytest.mark.asyncio
async def test_configured_transport_failure_raises_the_real_error_type(
    fake_kraken: FakeKrakenClient,
) -> None:
    """Same type the real client raises, so a fail-closed test keeps asserting on
    the same exception across the Phase 2 handover.

    "The real error type" is only true because the test above asserts it. On its own
    this test is satisfied by the harness's fallback classes, which are not the real
    ones — see that test for why, and do not delete it thinking it is a tautology.
    """
    fake_kraken.fail("balance")
    with pytest.raises(KrakenUnavailableError) as caught:
        await fake_kraken.balance()
    assert isinstance(caught.value, KrakenError)


@pytest.mark.asyncio
async def test_http_200_with_a_populated_error_array_is_a_failure(
    fake_kraken: FakeKrakenClient,
) -> None:
    """The failure mode `code-standards.md` singles out.

    Kraken does not use HTTP status to signal application errors. A client that
    treats 2xx as success records rejected orders as fills, so the fake has to be
    able to produce exactly that shape and it has to raise.
    """
    fake_kraken.fail_with_envelope_error("trade_volume", ["EGeneral:Invalid arguments"])
    with pytest.raises(KrakenAPIError) as caught:
        await fake_kraken.trade_volume()
    assert caught.value.errors == ["EGeneral:Invalid arguments"]
    assert isinstance(caught.value, KrakenError)


@pytest.mark.asyncio
async def test_an_unknown_pair_is_a_failure_not_an_empty_book(
    fake_kraken: FakeKrakenClient,
) -> None:
    """Absence of a "no" is never a "yes" (invariant 3). An empty book returned for
    an unknown pair would read as a zero spread, which is the one thing a cost gate
    must never be handed."""
    with pytest.raises(KrakenAPIError):
        await fake_kraken.order_book("NOPE/USD")


@pytest.mark.asyncio
async def test_balances_and_pair_rules_are_retained_and_survive_a_later_failure(
    fake_kraken: FakeKrakenClient,
) -> None:
    """Invariant 2, and it exists only so invariant 14 can work.

    A liquidation is triggered by an outage and has to complete *during* it, so the
    client keeps the last successful balances and `AssetPairs` metadata with the
    time each was fetched and never discards them on a failure.
    """
    fake_kraken.set_now(1_000_000)
    await fake_kraken.balance()
    await fake_kraken.asset_pairs()

    fake_kraken.fail("balance")
    fake_kraken.fail("asset_pairs")
    with pytest.raises(KrakenError):
        await fake_kraken.balance()
    with pytest.raises(KrakenError):
        await fake_kraken.asset_pairs()

    retained_balances = fake_kraken.last_known_good_balances
    retained_pairs = fake_kraken.last_known_good_asset_pairs
    assert retained_balances is not None
    assert retained_pairs is not None
    assert retained_balances.fetched_at == 1_000_000
    assert retained_pairs.value.pairs["BTC/USD"].ordermin == Decimal("0.00005")


@pytest.mark.asyncio
async def test_the_fee_tier_and_the_order_book_are_deliberately_not_retained(
    fake_kraken: FakeKrakenClient,
) -> None:
    """The other half of invariant 2, and the half that is easy to get wrong by
    being generous.

    Their only reader is the cost gate, and the paper-mode table says an assumed
    spread invalidates that gate. A retained stale spread would be a loaded gun
    pointed at the one input that must never have a fallback - and a liquidation
    does not need it, because it sells as a taker at whatever the book is.
    """
    await fake_kraken.trade_volume()
    await fake_kraken.order_book("BTC/USD")
    assert getattr(fake_kraken, "last_known_good_trade_volume", None) is None
    assert getattr(fake_kraken, "last_known_good_order_book", None) is None
    assert fake_kraken._retained.keys() <= {"asset_pairs", "balance"}


@pytest.mark.asyncio
async def test_the_fake_never_touches_the_network(fake_kraken: FakeKrakenClient) -> None:
    """Belt and braces: the guard is armed for this test, so a fake that reached for
    a socket would raise `NetworkAccessError` rather than pass quietly."""
    try:
        await fake_kraken.asset_pairs()
        await fake_kraken.trade_volume()
        await fake_kraken.balance()
        await fake_kraken.order_book("BTC/USD")
    except NetworkAccessError as exc:  # pragma: no cover - the point is that it does not
        pytest.fail(f"the fake reached for the network: {exc}")
    assert fake_kraken.calls == ("asset_pairs", "trade_volume", "balance", "order_book")


def test_clearing_a_failure_restores_the_envelope(fake_kraken: FakeKrakenClient) -> None:
    fake_kraken.fail_with_envelope_error("balance", ["EAPI:Rate limit exceeded"])
    fake_kraken.fail("asset_pairs")
    fake_kraken.clear_failures()
    assert fake_kraken._envelopes["balance"]["error"] == []
    assert fake_kraken._transport_failures == {}


def test_an_unknown_call_name_is_refused(fake_kraken: FakeKrakenClient) -> None:
    """A typo in a test's failure injection must not silently inject nothing."""
    with pytest.raises(ValueError, match="unknown call"):
        fake_kraken.fail("tradevolume")
