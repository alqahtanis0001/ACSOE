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
from datetime import UTC, datetime, timedelta
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


#: The two TTLs this file builds clients with, and they are **deliberately
#: unequal**. A helper that handed both calls the same number would let a
#: single-shared-TTL implementation — the shape spec 38 exists to prevent — pass
#: every test in this file without anyone noticing. `test_cache.py` proves the
#: independence directly; this is the same guard applied to the tests that are
#: about something else and merely have to live with the cache.
ASSET_PAIRS_TTL_S = 300
TRADE_VOLUME_TTL_S = 60


def build_client(
    transport: FakeTransport,
    *,
    credentials: Credentials | None = None,
    clock: FixedClock | None = None,
    asset_pairs_ttl_s: int | None = ASSET_PAIRS_TTL_S,
    trade_volume_ttl_s: int | None = TRADE_VOLUME_TTL_S,
) -> Any:
    """A client with both TTLs supplied and a clock the caller may keep and move.

    Both TTLs are supplied by default because omitting them is not "no caching" —
    it is `KrakenUnavailableError` naming the missing key, raised before the call
    does anything else. A test about the envelope or the signature that omitted
    them would fail on the TTL and prove nothing about its own subject, which is
    what happened to seven tests in this package when the cache landed.
    """
    return KrakenRestClient(
        clock=clock or FixedClock(AT),
        limiter=RateLimiter(capacity=20, refill_per_second=20),
        transport=transport,
        credentials=credentials
        or Credentials(key=PLANTED_KEY, secret=PLANTED_SECRET),
        base_url="https://example.invalid",
        asset_pairs_ttl_s=asset_pairs_ttl_s,
        trade_volume_ttl_s=trade_volume_ttl_s,
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


def test_a_body_that_is_not_json_at_all_is_unavailable_not_a_success() -> None:
    """Branch 1 of three: a proxy error page, an HTML maintenance notice.

    Renamed. It used to be called "not an envelope", which is a *different* branch —
    this input is not JSON, so it never reaches the envelope check. All three
    refusals raise `KrakenUnavailableError`, so nothing about the exception said
    which branch had run and the mislabelling left branch 2 with no test at all.
    The message is asserted here for that reason.
    """
    with pytest.raises(KrakenUnavailableError) as caught:
        parse_envelope(b"<html>maintenance</html>", "balance")
    assert "not JSON" in str(caught.value)


def test_json_that_is_not_a_kraken_envelope_is_refused_rather_than_returned() -> None:
    """Branch 2 of three, and the one that was untested — it is not defensive.

    A body carrying a `result` and **no `error` key at all** is the dangerous shape.
    Without this refusal it takes `payload.get("error") or []`, finds nothing to
    object to, finds a `result`, and is returned as a **clean success**. Kraken
    signals application errors in that array rather than in the HTTP status, so a
    body that does not carry the array is one where we cannot know whether it was a
    yes or a no — and invariant 3 says the absence of a "no" is never a "yes".

    Found by deleting the branch and watching all 82 tests in this package pass.
    """
    with pytest.raises(KrakenUnavailableError) as caught:
        parse_envelope(json.dumps({"result": {"tier": 1}}), "trade_volume")
    assert "envelope" in str(caught.value)


def test_an_envelope_with_neither_an_error_nor_a_result_is_refused() -> None:
    """Branch 3 of three. Neither a yes nor a no — invariant 3 again."""
    with pytest.raises(KrakenUnavailableError) as caught:
        parse_envelope(json.dumps({"error": []}), "balance")
    assert "neither a" in str(caught.value)


# --------------------------------------------------------------------------- #
# Fetched, never constant
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pair_rules_come_from_the_payload_and_change_when_it_changes() -> None:
    """The rule is fetched, never a constant — and the clock has to move for it.

    The TTL expiry is not incidental scaffolding here. Without it the second call
    is served from the cache and this test compares a snapshot with itself, which
    passes both value assertions and proves nothing at all about the payload. The
    request count is asserted for the same reason: it is what fails if the expiry
    ever stops working, and a value comparison is not.
    """
    transport = FakeTransport()
    transport.serve("AssetPairs", fixture("asset_pairs"))
    clock = FixedClock(AT)
    client = build_client(transport, clock=clock)
    first = (await client.asset_pairs()).pairs["BTC/USD"]
    assert len(transport.seen) == 1

    altered = fixture("asset_pairs")
    altered["result"]["BTC/USD"]["ordermin"] = "0.5"
    altered["result"]["BTC/USD"]["tick_size"] = "0.7"
    transport.serve("AssetPairs", altered)
    clock.advance(timedelta(seconds=ASSET_PAIRS_TTL_S + 1))
    second = (await client.asset_pairs()).pairs["BTC/USD"]

    assert len(transport.seen) == 2
    assert second.ordermin == Decimal("0.5")
    assert second.tick_size == Decimal("0.7")
    assert second.ordermin != first.ordermin


@pytest.mark.asyncio
async def test_the_fee_tier_comes_from_the_payload_and_changes_when_it_changes() -> None:
    """Same property for the fee, past its **own** TTL, which is the shorter one."""
    transport = FakeTransport()
    transport.serve("TradeVolume", fixture("trade_volume"))
    clock = FixedClock(AT)
    client = build_client(transport, clock=clock)
    first = await client.trade_volume()
    assert len(transport.seen) == 1

    altered = fixture("trade_volume")
    altered["result"]["tier"] = 3
    altered["result"]["maker_fee_pct"] = "0.0011"
    altered["result"]["taker_fee_pct"] = "0.0019"
    transport.serve("TradeVolume", altered)
    clock.advance(timedelta(seconds=TRADE_VOLUME_TTL_S + 1))
    second = await client.trade_volume()

    assert len(transport.seen) == 2
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
    """Retention survives the **TTL expiry** that blocked trading — one test, both facts.

    Spec 38 asks for exactly this pairing, and the pairing is the point. The clock
    is advanced past `cache_ttl_s.asset_pairs`, so the second `AssetPairs` call is
    a genuine re-fetch rather than a cache hit; the re-fetch fails; the call raises
    and does **not** hand back the expired snapshot. And after all of that the
    last-known-good still holds the pre-expiry value, because the cache and the
    retention are two mechanisms with two readers — the cache answers "may I use
    this now", which is now no, and the retention answers "what is the last thing
    we knew", which is unchanged. Rule 14's liquidation needs the second during
    precisely the outage that makes the first say no.

    `Balance` is not cached at all, so the clock does not affect it; it is here
    because retention has to hold for both retained calls, not only the cached one.
    """
    transport = FakeTransport()
    transport.serve("AssetPairs", fixture("asset_pairs"))
    transport.serve("Balance", fixture("balance"))
    clock = FixedClock(AT)
    client = build_client(transport, clock=clock)
    await client.asset_pairs()
    await client.balance()
    requests_before = len(transport.seen)

    transport.serve("AssetPairs", {"error": ["EService:Unavailable"], "result": {}})
    transport.serve("Balance", {"error": ["EService:Unavailable"], "result": {}})
    clock.advance(timedelta(seconds=ASSET_PAIRS_TTL_S + 1))
    with pytest.raises(KrakenAPIError):
        await client.asset_pairs()
    with pytest.raises(KrakenAPIError):
        await client.balance()

    # The expiry sent the call to the network. If the cache had answered instead,
    # nothing would have raised and the assertions below would be about a value
    # that was never in danger.
    assert len(transport.seen) == requests_before + 2

    retained_pairs = client.last_known_good_asset_pairs
    retained_balances = client.last_known_good_balances
    assert retained_pairs is not None
    assert retained_balances is not None
    assert retained_pairs.value.pairs["BTC/USD"].ordermin == Decimal("0.00005")
    assert retained_balances.value.balances["USD"] == Decimal("1000.00")


@pytest.mark.asyncio
async def test_the_fee_tier_and_the_book_are_deliberately_not_retained() -> None:
    """A retained stale spread or fee is a loaded gun pointed at the cost gate.

    The negative half of the test above, and it is sharpened by the cache existing:
    `TradeVolume` is the one call that is cached and **not** retained, so after its
    TTL expires and the re-fetch fails there is nowhere left in the client holding
    a fee. That is the whole distinction — a TTL cache says "this is still good", a
    last-known-good would say "use it anyway", and for a fee the second must not
    exist. Asserting it only before the expiry would leave the interesting moment
    untested.
    """
    transport = FakeTransport()
    transport.serve("TradeVolume", fixture("trade_volume"))
    clock = FixedClock(AT)
    client = build_client(transport, clock=clock)
    await client.trade_volume()
    assert getattr(client, "last_known_good_trade_volume", None) is None
    assert set(client._retained) <= {"asset_pairs", "balance"}

    transport.serve("TradeVolume", {"error": ["EService:Unavailable"], "result": {}})
    clock.advance(timedelta(seconds=TRADE_VOLUME_TTL_S + 1))
    with pytest.raises(KrakenAPIError):
        await client.trade_volume()

    assert getattr(client, "last_known_good_trade_volume", None) is None
    assert "trade_volume" not in client._retained
    assert "order_book" not in client._retained


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_a_private_call_without_credentials_blocks_rather_than_defaulting() -> None:
    """And blocks for **that** reason, which is asserted rather than assumed.

    This test was green through the whole of the cache landing, and it should not
    have been: it built the client with no TTLs as well as no credentials, so
    `_require_ttl` raised `KrakenUnavailableError` about `cache_ttl_s.trade_volume`
    several lines before the credential check ran. Same exception type, so nothing
    in `pytest.raises` could notice. Every fail-closed path in this package raises
    that one type on purpose, which makes the type alone a weak assertion — where
    the reason is the subject, the message is what gets asserted.
    """
    transport = FakeTransport()
    transport.serve("TradeVolume", fixture("trade_volume"))
    client = KrakenRestClient(
        clock=FixedClock(AT),
        limiter=RateLimiter(capacity=20, refill_per_second=20),
        transport=transport,
        credentials=None,
        base_url="https://example.invalid",
        asset_pairs_ttl_s=ASSET_PAIRS_TTL_S,
        trade_volume_ttl_s=TRADE_VOLUME_TTL_S,
    )
    with pytest.raises(KrakenUnavailableError) as caught:
        await client.trade_volume()
    message = str(caught.value)
    assert "credentials" in message
    assert "cache_ttl_s" not in message
    assert not transport.seen


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
