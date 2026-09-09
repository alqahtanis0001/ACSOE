"""Spec 25 — the REST client: the envelope, the mapping, the retention.

The envelope test is the point of this file and it is deliberately written as a
**pair**. A parser that raised on every response would satisfy "a 200 with a
populated `error` array raises" perfectly well and be useless, so the positive
assertion — a 200 with an *empty* `error` array parses cleanly and yields its
`result` — is not a nicety. Neither assertion is worth anything without the other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.kraken import (
    KrakenAPIError,
    KrakenRestClient,
    KrakenUnavailableError,
    RateLimiter,
    parse_envelope,
)
from acsoe.clients.kraken.rest import (
    HttpResponse,
    map_asset_pairs,
    map_order_book,
    map_trade_volume,
    sign_request,
)
from acsoe.platform.clock import FixedClock
from acsoe.platform.config import Credentials

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "kraken"
AT = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

PLANTED_KEY = "kR4k3n-Ap1-K3y-DO-NOT-LOG-9f2c1a7b"
# Valid base64, so signing succeeds and the secret genuinely travels through the
# code path being scanned. A secret that made signing fail would prove nothing.
PLANTED_SECRET = "c2VjcmV0LWJhc2U2NC1raW5kLW9mLXRoaW5nLXRoYXQta3Jha2VuLXVzZXM="


def fixture(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return loaded


@dataclass
class FakeTransport:
    """HTTP, replaced at the seam the real client injects.

    Not an `httpx.MockTransport`: `tests/conftest.py`'s autouse guard patches
    `httpx.AsyncClient.send` itself, so nothing reaches a mock transport inside a
    test. Injecting one level higher is what keeps the guard strict and the
    envelope covered at the same time.
    """

    bodies: dict[str, bytes] = field(default_factory=dict)
    status: int = 200
    seen: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)

    def serve(self, path_fragment: str, payload: Any, *, status: int = 200) -> None:
        self.bodies[path_fragment] = json.dumps(payload).encode()
        self.status = status

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Any,
        content: bytes | None,
        timeout_s: float,
    ) -> HttpResponse:
        self.seen.append((method, url, dict(headers)))
        for fragment, body in self.bodies.items():
            if fragment in url:
                return HttpResponse(status_code=self.status, body=body)
        raise AssertionError(f"no fake response registered for {url}")


def build_client(transport: FakeTransport, *, credentials: Credentials | None = None) -> Any:
    return KrakenRestClient(
        clock=FixedClock(AT),
        limiter=RateLimiter(capacity=20, refill_per_second=20),
        transport=transport,
        credentials=credentials
        or Credentials(key=PLANTED_KEY, secret=PLANTED_SECRET),
        base_url="https://example.invalid",
    )


# --------------------------------------------------------------------------- #
# The envelope — both halves, as a pair
# --------------------------------------------------------------------------- #


def test_a_200_with_a_populated_error_array_raises() -> None:
    with pytest.raises(KrakenAPIError) as caught:
        parse_envelope(
            json.dumps({"error": ["EGeneral:Invalid arguments"], "result": {}}), "trade_volume"
        )
    assert caught.value.errors == ["EGeneral:Invalid arguments"]


def test_a_200_with_an_empty_error_array_parses_and_yields_its_result() -> None:
    """The half that makes the half above mean something.

    Without this, a parser that raised unconditionally would pass the test above
    and fail every real call. The two assertions only prove discrimination
    together, which is the only property the envelope has.
    """
    result = parse_envelope(json.dumps({"error": [], "result": {"tier": 1}}), "trade_volume")
    assert result == {"tier": 1}


@pytest.mark.asyncio
async def test_the_client_raises_on_a_populated_error_array_despite_http_200() -> None:
    transport = FakeTransport()
    transport.serve("AssetPairs", {"error": ["EService:Unavailable"], "result": {}})
    client = build_client(transport)
    with pytest.raises(KrakenAPIError):
        await client.asset_pairs()


@pytest.mark.asyncio
async def test_the_client_parses_a_clean_200_and_returns_the_mapped_result() -> None:
    transport = FakeTransport()
    transport.serve("AssetPairs", fixture("asset_pairs"))
    client = build_client(transport)
    pairs = await client.asset_pairs()
    assert "BTC/USD" in pairs.pairs
    assert isinstance(pairs.pairs["BTC/USD"].ordermin, Decimal)


def test_a_body_that_is_not_an_envelope_is_unavailable_not_a_success() -> None:
    with pytest.raises(KrakenUnavailableError):
        parse_envelope(b"<html>maintenance</html>", "balance")


def test_an_envelope_with_neither_an_error_nor_a_result_is_refused() -> None:
    """Neither a yes nor a no. Invariant 3: the absence of a "no" is never a "yes"."""
    with pytest.raises(KrakenUnavailableError):
        parse_envelope(json.dumps({"error": []}), "balance")


# --------------------------------------------------------------------------- #
# Fetched, never constant
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pair_rules_come_from_the_payload_and_change_when_it_changes() -> None:
    transport = FakeTransport()
    transport.serve("AssetPairs", fixture("asset_pairs"))
    client = build_client(transport)
    first = (await client.asset_pairs()).pairs["BTC/USD"]

    altered = fixture("asset_pairs")
    altered["result"]["BTC/USD"]["ordermin"] = "0.5"
    altered["result"]["BTC/USD"]["tick_size"] = "0.7"
    transport.serve("AssetPairs", altered)
    second = (await client.asset_pairs()).pairs["BTC/USD"]

    assert second.ordermin == Decimal("0.5")
    assert second.tick_size == Decimal("0.7")
    assert second.ordermin != first.ordermin


@pytest.mark.asyncio
async def test_the_fee_tier_comes_from_the_payload_and_changes_when_it_changes() -> None:
    transport = FakeTransport()
    transport.serve("TradeVolume", fixture("trade_volume"))
    client = build_client(transport)
    first = await client.trade_volume()

    altered = fixture("trade_volume")
    altered["result"]["tier"] = 3
    altered["result"]["maker_fee_pct"] = "0.0011"
    altered["result"]["taker_fee_pct"] = "0.0019"
    transport.serve("TradeVolume", altered)
    second = await client.trade_volume()

    assert (second.tier, second.maker_fee_pct) == (3, Decimal("0.0011"))
    assert second.maker_fee_pct != first.maker_fee_pct


def test_a_missing_fee_field_is_a_failure_and_never_an_assumed_tier() -> None:
    """Invariant 2's paper fallback is the consumer's decision, recorded as such.

    A client that quietly supplied a tier would make that record impossible, and a
    fallback that nobody recorded is indistinguishable from a real fetch.
    """
    incomplete = dict(fixture("trade_volume")["result"])
    del incomplete["maker_fee_pct"]
    with pytest.raises(KrakenUnavailableError):
        map_trade_volume(incomplete, fetched_at=0)


def test_a_pair_missing_a_rule_is_dropped_rather_than_defaulted() -> None:
    result = dict(fixture("asset_pairs")["result"])
    result["BROKEN/USD"] = {"base": "BROKEN", "quote": "USD"}
    snapshot = map_asset_pairs(result, fetched_at=0)
    assert "BROKEN/USD" not in snapshot.pairs
    assert "BTC/USD" in snapshot.pairs


# --------------------------------------------------------------------------- #
# Absent is not zero
# --------------------------------------------------------------------------- #


def test_an_empty_book_side_is_a_failure_and_never_a_zero_spread() -> None:
    with pytest.raises(KrakenUnavailableError):
        map_order_book(
            {"BTC/USD": {"bids": [], "asks": [["1", "1"]]}},
            pair="BTC/USD",
            depth=10,
            fetched_at=0,
        )


def test_an_unknown_pair_is_a_failure_not_an_empty_book() -> None:
    with pytest.raises(KrakenAPIError):
        map_order_book({"BTC/USD": {"bids": [["1", "1"]], "asks": [["2", "1"]]}},
                       pair="NOPE/USD", depth=10, fetched_at=0)


def test_a_crossed_book_is_reported_rather_than_clamped() -> None:
    """Engine 4 blocks on a negative spread, so the client must not tidy one away."""
    book = map_order_book(
        {"X/USD": {"bids": [["100.5", "1"]], "asks": [["100.0", "1"]]}},
        pair="X/USD",
        depth=10,
        fetched_at=0,
    )
    assert book.spread == Decimal("-0.5")


# --------------------------------------------------------------------------- #
# Retention — invariant 2, so that invariant 14 can work
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pair_rules_and_balances_are_retained_across_a_later_failure() -> None:
    transport = FakeTransport()
    transport.serve("AssetPairs", fixture("asset_pairs"))
    transport.serve("Balance", fixture("balance"))
    client = build_client(transport)
    await client.asset_pairs()
    await client.balance()

    transport.serve("AssetPairs", {"error": ["EService:Unavailable"], "result": {}})
    transport.serve("Balance", {"error": ["EService:Unavailable"], "result": {}})
    with pytest.raises(KrakenAPIError):
        await client.asset_pairs()
    with pytest.raises(KrakenAPIError):
        await client.balance()

    retained_pairs = client.last_known_good_asset_pairs
    retained_balances = client.last_known_good_balances
    assert retained_pairs is not None
    assert retained_balances is not None
    assert retained_pairs.value.pairs["BTC/USD"].ordermin == Decimal("0.00005")
    assert retained_balances.value.balances["USD"] == Decimal("1000.00")


@pytest.mark.asyncio
async def test_the_fee_tier_and_the_book_are_deliberately_not_retained() -> None:
    """A retained stale spread is a loaded gun pointed at the cost gate."""
    transport = FakeTransport()
    transport.serve("TradeVolume", fixture("trade_volume"))
    client = build_client(transport)
    await client.trade_volume()
    assert getattr(client, "last_known_good_trade_volume", None) is None
    assert set(client._retained) <= {"asset_pairs", "balance"}


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_private_call_without_credentials_blocks_rather_than_defaulting() -> None:
    transport = FakeTransport()
    transport.serve("TradeVolume", fixture("trade_volume"))
    client = KrakenRestClient(
        clock=FixedClock(AT),
        limiter=RateLimiter(capacity=20, refill_per_second=20),
        transport=transport,
        credentials=None,
        base_url="https://example.invalid",
    )
    with pytest.raises(KrakenUnavailableError):
        await client.trade_volume()


def test_the_signature_is_deterministic_and_refuses_a_malformed_secret() -> None:
    first = sign_request(path="/0/private/Balance", nonce=1, form={}, secret=PLANTED_SECRET)
    second = sign_request(path="/0/private/Balance", nonce=1, form={}, secret=PLANTED_SECRET)
    third = sign_request(path="/0/private/Balance", nonce=2, form={}, secret=PLANTED_SECRET)
    assert first == second
    assert first != third
    with pytest.raises(KrakenUnavailableError) as caught:
        sign_request(path="/0/private/Balance", nonce=1, form={}, secret="not base64 !!")
    assert "not base64 !!" not in str(caught.value)


@pytest.mark.asyncio
async def test_the_nonce_strictly_increases_under_a_clock_that_stands_still() -> None:
    """A replay clock does not move, and Kraken rejects a nonce that does not rise."""
    transport = FakeTransport()
    transport.serve("Balance", fixture("balance"))
    client = build_client(transport)
    await client.balance()
    await client.balance()
    nonces = [client._nonce]
    await client.balance()
    assert client._nonce > nonces[0]
