"""Spec 38 — the TTL-bounded cache, and the line between it and the retention.

Every assertion in this file is about **the transport**, not about the value that
came back. Two calls that return equal snapshots prove nothing about whether the
network was touched: the cache returns the same object the fetch would have, so an
identity or equality check passes just as happily against a client with no cache in
it at all. `CountingTransport` records one entry per request and the tests read the
count.

Time moves only through the injected clock. There is no `sleep` anywhere here and
there must not be: a test that waits for a TTL is a test that is slow when it passes
and flaky when the machine is busy, and this client exists partly so that a replay
is faithful, which a real clock would break in the one layer replay depends on.

The two mechanisms this file keeps apart:

* the **cache** answers *may I use this now* — bounded, and past its bound the
  answer is no and the call fails;
* the **retention** answers *what is the last thing we knew* — unbounded, kept past
  any TTL, and readable only by invariant 14's emergency liquidation.

`test_rest.py` proves the same boundary from the retention side. This file proves it
from the cache side.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from acsoe.clients.kraken import (
    KrakenAPIError,
    KrakenRestClient,
    KrakenUnavailableError,
    RateLimiter,
)
from acsoe.clients.kraken.rest import HttpResponse
from acsoe.platform.clock import FixedClock
from acsoe.platform.config import Config, Credentials, load_config

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_YAML = REPO_ROOT / "config" / "default.yaml"
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "kraken"
AT = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

PLANTED_SECRET = "c2VjcmV0LWJhc2U2NC1raW5kLW9mLXRoaW5nLXRoYXQta3Jha2VuLXVzZXM="
CREDENTIALS = Credentials(key="test-key", secret=PLANTED_SECRET)

#: The endpoint fragment each cached call reaches for, and the config key holding
#: its TTL. Written as a table so a test can be parametrised over "the two cached
#: calls" without naming either twice.
ASSET_PAIRS = ("asset_pairs", "AssetPairs", "kraken.cache_ttl_s.asset_pairs")
TRADE_VOLUME = ("trade_volume", "TradeVolume", "kraken.cache_ttl_s.trade_volume")
CACHED_CALLS = [ASSET_PAIRS, TRADE_VOLUME]

UNAVAILABLE = {"error": ["EService:Unavailable"], "result": {}}


def fixture(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return loaded


@dataclass
class CountingTransport:
    """A transport that remembers how many times each endpoint was asked.

    The whole point of the file. `serve` replaces what an endpoint answers with
    without resetting its count, so a test can make a later call fail and still
    assert that the call was attempted.
    """

    bodies: dict[str, bytes] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def serve(self, fragment: str, payload: Any) -> None:
        self.bodies[fragment] = json.dumps(payload).encode()

    def count(self, fragment: str) -> int:
        return self.calls.count(fragment)

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
        raise AssertionError(f"no fake response registered for {url}")


def build(
    transport: CountingTransport,
    clock: FixedClock,
    *,
    asset_pairs_ttl_s: int | None = 300,
    trade_volume_ttl_s: int | None = 60,
) -> KrakenRestClient:
    return KrakenRestClient(
        clock=clock,
        limiter=RateLimiter(capacity=50, refill_per_second=50),
        transport=transport,
        credentials=CREDENTIALS,
        base_url="https://example.invalid",
        asset_pairs_ttl_s=asset_pairs_ttl_s,
        trade_volume_ttl_s=trade_volume_ttl_s,
    )


def serve_both(transport: CountingTransport) -> None:
    transport.serve("AssetPairs", fixture("asset_pairs"))
    transport.serve("TradeVolume", fixture("trade_volume"))
    transport.serve("Balance", fixture("balance"))


async def call(client: KrakenRestClient, name: str) -> Any:
    return await getattr(client, name)()


def ttl_for(name: str, *, asset_pairs: int, trade_volume: int) -> int:
    return asset_pairs if name == "asset_pairs" else trade_volume


# --------------------------------------------------------------------------- #
# Both halves, as a pair: inside the TTL no request, outside it a request
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "fragment", "_key"), CACHED_CALLS)
async def test_a_second_call_inside_the_ttl_makes_no_http_request(
    name: str, fragment: str, _key: str
) -> None:
    """The assertion is the request count, deliberately.

    An identical snapshot proves nothing: the cache hands back the very object the
    fetch would have produced, so equality holds either way. Only the transport can
    say whether the network was touched.
    """
    transport = CountingTransport()
    serve_both(transport)
    clock = FixedClock(AT)
    client = build(transport, clock)
    ttl_s = ttl_for(name, asset_pairs=300, trade_volume=60)

    first = await call(client, name)
    assert transport.count(fragment) == 1

    clock.advance(timedelta(seconds=ttl_s - 1))
    second = await call(client, name)

    assert transport.count(fragment) == 1
    assert second is first


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "fragment", "_key"), CACHED_CALLS)
async def test_a_call_after_the_ttl_makes_a_request(
    name: str, fragment: str, _key: str
) -> None:
    """The half that makes the half above mean something.

    A client that never cached would pass nothing above; a client that cached
    forever would pass everything above and fail here. Neither assertion is worth
    anything on its own — the property is the discrimination.
    """
    transport = CountingTransport()
    serve_both(transport)
    clock = FixedClock(AT)
    client = build(transport, clock)
    ttl_s = ttl_for(name, asset_pairs=300, trade_volume=60)

    await call(client, name)
    clock.advance(timedelta(seconds=ttl_s + 1))
    await call(client, name)

    assert transport.count(fragment) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "fragment", "_key"), CACHED_CALLS)
async def test_the_boundary_is_expired_at_exactly_the_ttl_and_fresh_a_microsecond_before(
    name: str, fragment: str, _key: str
) -> None:
    """Both readings of "stale beyond its TTL" are defensible on the boundary itself.

    Fail-closed is the tie-breaker: at exactly its TTL an entry has reached the end
    of the interval it was permitted, so it is fetched again. Pinned to the
    microsecond either side, because a boundary nobody tested is a boundary that
    moves the next time this code is edited.
    """
    ttl_s = ttl_for(name, asset_pairs=300, trade_volume=60)

    just_inside = CountingTransport()
    serve_both(just_inside)
    clock = FixedClock(AT)
    client = build(just_inside, clock)
    await call(client, name)
    clock.advance(timedelta(seconds=ttl_s) - timedelta(microseconds=1))
    await call(client, name)
    assert just_inside.count(fragment) == 1

    exactly_on = CountingTransport()
    serve_both(exactly_on)
    clock = FixedClock(AT)
    client = build(exactly_on, clock)
    await call(client, name)
    clock.advance(timedelta(seconds=ttl_s))
    await call(client, name)
    assert exactly_on.count(fragment) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "fragment", "_key"), CACHED_CALLS)
async def test_a_clock_that_moved_backwards_counts_as_expired(
    name: str, fragment: str, _key: str
) -> None:
    """A negative age is not a very fresh entry.

    `FixedClock.advance` refuses to go backwards, so this uses `set` — which is the
    honest reproduction anyway: the case is a replay repositioned to an earlier
    instant, or a host whose clock was stepped, not a clock that ran in reverse.
    """
    transport = CountingTransport()
    serve_both(transport)
    clock = FixedClock(AT)
    client = build(transport, clock)

    await call(client, name)
    clock.set(AT - timedelta(seconds=1))
    await call(client, name)

    assert transport.count(fragment) == 2


# --------------------------------------------------------------------------- #
# A cache past its TTL is a failed fetch, not a stale value
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "fragment", "_key"), CACHED_CALLS)
async def test_an_expired_entry_whose_refetch_fails_raises_and_is_never_returned(
    name: str, fragment: str, _key: str
) -> None:
    """Invariant 2: for trading, a stale value does not exist.

    The failure is asserted three ways, because "it raised" alone is compatible
    with a client that held the expired entry and would hand it back on the next
    call. The re-fetch is proved to have been attempted; the call is proved to
    raise; and a subsequent successful fetch of a **different** payload is proved
    to be what comes back, which is only true if the expired entry was discarded
    rather than merely withheld once.
    """
    transport = CountingTransport()
    serve_both(transport)
    clock = FixedClock(AT)
    client = build(transport, clock)
    ttl_s = ttl_for(name, asset_pairs=300, trade_volume=60)

    before = await call(client, name)
    attempts = transport.count(fragment)

    transport.serve(fragment, UNAVAILABLE)
    clock.advance(timedelta(seconds=ttl_s + 1))
    with pytest.raises(KrakenAPIError):
        await call(client, name)
    assert transport.count(fragment) == attempts + 1

    altered = copy.deepcopy(fixture(name))
    if name == "asset_pairs":
        altered["result"]["BTC/USD"]["ordermin"] = "0.5"
    else:
        altered["result"]["maker_fee_pct"] = "0.0011"
    transport.serve(fragment, altered)
    after = await call(client, name)

    assert after is not before
    if name == "asset_pairs":
        assert after.pairs["BTC/USD"].ordermin == Decimal("0.5")
    else:
        assert after.maker_fee_pct == Decimal("0.0011")


@pytest.mark.asyncio
async def test_retention_survives_the_expiry_that_blocked_trading() -> None:
    """One test, both facts — spec 38's own wording.

    The expiry is what turns the second call into a re-fetch; the re-fetch fails;
    the call raises rather than returning the expired snapshot. And through all of
    it `last_known_good_asset_pairs` still holds the pre-expiry value, with the
    `fetched_at` it was fetched at, because rule 14's emergency liquidation has to
    complete during exactly the outage that made the cache say no.

    The failure the cache reports and the value the retention keeps are the *same
    snapshot*. That is the part a single-mechanism implementation cannot express:
    it would have to either return the stale value to trading or throw away the
    only thing a liquidation could size against.
    """
    transport = CountingTransport()
    serve_both(transport)
    clock = FixedClock(AT)
    client = build(transport, clock)

    fresh = await client.asset_pairs()
    retained_before = client.last_known_good_asset_pairs
    assert retained_before is not None

    transport.serve("AssetPairs", UNAVAILABLE)
    clock.advance(timedelta(seconds=301))
    with pytest.raises(KrakenAPIError):
        await client.asset_pairs()

    retained_after = client.last_known_good_asset_pairs
    assert retained_after is not None
    assert retained_after.fetched_at == retained_before.fetched_at
    assert retained_after.value.pairs["BTC/USD"].ordermin == fresh.pairs["BTC/USD"].ordermin


@pytest.mark.asyncio
async def test_the_fee_tier_is_cached_and_still_never_retained() -> None:
    """The one call that is cached and not retained, asserted after the expiry.

    A TTL cache says "this is still good". A last-known-good says "use it anyway".
    For a fee the second must not exist, because the cost gate is its only reader
    and an assumed fee invalidates that gate outright. So once the TTL has expired
    and the re-fetch has failed there is nowhere in the client holding a fee at all.
    """
    transport = CountingTransport()
    serve_both(transport)
    clock = FixedClock(AT)
    client = build(transport, clock)

    await client.trade_volume()
    transport.serve("TradeVolume", UNAVAILABLE)
    clock.advance(timedelta(seconds=61))
    with pytest.raises(KrakenAPIError):
        await client.trade_volume()

    assert getattr(client, "last_known_good_trade_volume", None) is None
    assert "trade_volume" not in client._retained


# --------------------------------------------------------------------------- #
# Two TTLs, and they are independent — proved in both directions
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_pairs_ttl_s", "trade_volume_ttl_s", "expired", "still_fresh"),
    [
        (60, 300, "AssetPairs", "TradeVolume"),
        (300, 60, "TradeVolume", "AssetPairs"),
    ],
    ids=["asset_pairs_is_the_short_one", "trade_volume_is_the_short_one"],
)
async def test_the_two_ttls_expire_independently(
    asset_pairs_ttl_s: int,
    trade_volume_ttl_s: int,
    expired: str,
    still_fresh: str,
) -> None:
    """Different values, and the clock parked between them — in both directions.

    One direction alone does not settle it. An implementation that read a single
    shared TTL would pick *some* number, and whichever it picked it would pass the
    case where that number happens to be right and fail the other. Running both
    orders is what leaves it nowhere to stand.

    The clock advances to 90 seconds, which is past the 60 and short of the 300, so
    on the same tick one call must reach the network and the other must not.
    """
    transport = CountingTransport()
    serve_both(transport)
    clock = FixedClock(AT)
    client = build(
        transport,
        clock,
        asset_pairs_ttl_s=asset_pairs_ttl_s,
        trade_volume_ttl_s=trade_volume_ttl_s,
    )

    await client.asset_pairs()
    await client.trade_volume()
    assert transport.count("AssetPairs") == 1
    assert transport.count("TradeVolume") == 1

    clock.advance(timedelta(seconds=90))
    await client.asset_pairs()
    await client.trade_volume()

    assert transport.count(expired) == 2
    assert transport.count(still_fresh) == 1


# --------------------------------------------------------------------------- #
# What is not cached, and what happens with no TTL at all
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_the_balance_is_never_cached() -> None:
    """Balances change on every fill. A cached one sizes an order that cannot fill."""
    transport = CountingTransport()
    serve_both(transport)
    client = build(transport, FixedClock(AT))

    await client.balance()
    await client.balance()

    assert transport.count("Balance") == 2


@pytest.mark.asyncio
async def test_the_order_book_is_never_cached() -> None:
    """A stale spread is the loaded gun invariant 2 names, and it is not fired here."""
    transport = CountingTransport()
    transport.serve("Depth", {"error": [], "result": fixture("order_book")["result"]})
    client = build(transport, FixedClock(AT))

    await client.order_book("BTC/USD")
    await client.order_book("BTC/USD")

    assert transport.count("Depth") == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "fragment", "key"), CACHED_CALLS)
async def test_a_missing_ttl_raises_naming_the_key_and_reaches_no_network(
    name: str, fragment: str, key: str
) -> None:
    """An absent TTL is not "cache forever" and not "never cache".

    It is an unanswerable question about whether a value is still good, and
    invariant 3 says the absence of a no is never a yes. The call fails the way a
    failed fetch fails, names the key an operator would have to supply, and does
    not spend a request finding that out.
    """
    transport = CountingTransport()
    serve_both(transport)
    client = build(
        transport,
        FixedClock(AT),
        asset_pairs_ttl_s=None if name == "asset_pairs" else 300,
        trade_volume_ttl_s=None if name == "trade_volume" else 300,
    )

    with pytest.raises(KrakenUnavailableError) as caught:
        await call(client, name)

    assert key in str(caught.value)
    assert transport.count(fragment) == 0


# --------------------------------------------------------------------------- #
# The TTLs come from config, and from two separate keys
# --------------------------------------------------------------------------- #


def config_with(tmp_path: Path, *, asset_pairs: int, trade_volume: int) -> Config:
    """The shipped config with the two TTLs replaced, and nothing else touched."""
    raw: dict[str, Any] = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    raw["kraken"]["cache_ttl_s"] = {"asset_pairs": asset_pairs, "trade_volume": trade_volume}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return load_config(path, load_env=False)


@pytest.mark.asyncio
async def test_from_config_reads_each_ttl_from_its_own_key(tmp_path: Path) -> None:
    """No literal, and no single shared value — asserted through behaviour.

    Reading the private fields back would only prove the constructor stored what it
    was handed. This drives the clock to an instant between the two configured
    values and asserts which call reached the network, which is the same property
    the independence test above proves and is the reason it is worth repeating on
    the config path: the construction site is where the two keys could quietly
    become one.
    """
    config = config_with(tmp_path, asset_pairs=1000, trade_volume=10)
    transport = CountingTransport()
    serve_both(transport)
    clock = FixedClock(AT)
    client = KrakenRestClient.from_config(
        config,
        clock=clock,
        limiter=RateLimiter(capacity=50, refill_per_second=50),
        transport=transport,
        credentials=CREDENTIALS,
        base_url="https://example.invalid",
    )

    await client.asset_pairs()
    await client.trade_volume()
    clock.advance(timedelta(seconds=20))
    await client.asset_pairs()
    await client.trade_volume()

    assert transport.count("AssetPairs") == 1
    assert transport.count("TradeVolume") == 2


@pytest.mark.asyncio
async def test_the_committed_config_supplies_both_ttls_to_a_real_client() -> None:
    """The shipped file is what the daemon will build from, so it is what is checked.

    Values are asserted here rather than in a fabricated config on purpose: this is
    the one test that would notice the lead's paste going missing, or one of the two
    keys being dropped, which is the failure that made the whole call raise before
    spec 38 landed.
    """
    if not DEFAULT_YAML.is_file():
        pytest.skip("config/default.yaml does not exist yet")
    config = load_config(DEFAULT_YAML, load_env=False)

    assert config.kraken.cache_ttl_s.asset_pairs == 300
    assert config.kraken.cache_ttl_s.trade_volume == 60

    transport = CountingTransport()
    serve_both(transport)
    clock = FixedClock(AT)
    client = KrakenRestClient.from_config(
        config,
        clock=clock,
        limiter=RateLimiter(capacity=50, refill_per_second=50),
        transport=transport,
        credentials=CREDENTIALS,
        base_url="https://example.invalid",
    )

    await client.asset_pairs()
    await client.trade_volume()
    # Past `trade_volume`'s 60 and short of `asset_pairs`' 300.
    clock.advance(timedelta(seconds=120))
    await client.asset_pairs()
    await client.trade_volume()

    assert transport.count("AssetPairs") == 1
    assert transport.count("TradeVolume") == 2
