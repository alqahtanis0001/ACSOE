"""Spec 39 — the subscription scope, derived per tick and never configured.

Three things about how this file is built, because each of them is the difference
between proving the property and appearing to.

**`state["exchange"]` is never hand-built.** Every test here drives the real
`ExchangeEngine` through the real `Orchestrator` against C's fake Kraken client, and
varies the *fake* — its balances, its pair rules, whether a call fails. A test that
wrote the payload out by hand would be asserting that engine 2 agrees with the test's
idea of engine 1, which is exactly the mismatch that hid for a whole phase and is
what the operator's "rewritten, not repointed" ruling is about.

**The stream is the real `KrakenWebSocketClient`, not a double.** It is constructed
and never started, so there is no thread and no socket — but `set_subscription`,
`subscription` and the delta bookkeeping are the production ones. A double here would
be a reimplementation of the thing under test, and it would agree with whatever
engine 2 did.

**Two ticks, and the second one is the test.** "Unchanged" and "changed" are both
claims about a *pair* of ticks, so a single-tick assertion cannot express either. The
subscription lives in the stream rather than in the engine, which is why the engine
can stay stateless across cycles and still leave a scope alone.

The scope is **not the tradable universe**. Nothing economic enters it — no
`ordermin`, no `costmin`, no spread, no equity. Engine 7 `scout` is the sole
authority on what may be traded and computes that per tick; a pair in this scope is
routinely outside that universe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from tests.harness.doubles import MappingConfig
from tests.harness.fake_kraken import FakeKrakenClient, FakeRecorder

from acsoe.clients.kraken.ws import KrakenWebSocketClient
from acsoe.core.contracts import Chains
from acsoe.core.orchestrator import Orchestrator
from acsoe.engines.exchange.contracts import STATE_KEY as EXCHANGE_KEY
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_data_recorder.contracts import BOOK_DEPTH, EXCHANGE_STATE_KEY
from acsoe.engines.market_data_recorder.contracts import STATE_KEY as RECORDER_KEY
from acsoe.engines.market_data_recorder.engine import MarketDataRecorderEngine

#: The stable quote currencies these tests configure. **Not a claim about the world**
#: and not a value anyone may copy into `config/default.yaml`: the real set is
#: `trading.stable_quote_currencies`, which is requested and is the lead's to supply.
#: A test that needs a threshold passes it explicitly, which is the standing rule here.
STABLE_QUOTES = ["USD", "EUR"]


@dataclass
class RestAndStream:
    """REST from C's fake, the market stream from the real client.

    The same forwarding `clients/kraken/client.py` does. Written out here rather than
    reusing `KrakenClient` because that class is annotated for the real
    `KrakenRestClient`, and handing it a fake would be a lie in the signature rather
    than in the test.
    """

    rest: FakeKrakenClient
    stream: KrakenWebSocketClient

    async def asset_pairs(self) -> Any:
        return await self.rest.asset_pairs()

    async def trade_volume(self) -> Any:
        return await self.rest.trade_volume()

    async def balance(self) -> Any:
        return await self.rest.balance()

    @property
    def last_known_good_asset_pairs(self) -> Any:
        return self.rest.last_known_good_asset_pairs

    @property
    def last_known_good_balances(self) -> Any:
        return self.rest.last_known_good_balances

    def set_subscription(self, pairs: Any) -> bool:
        return self.stream.set_subscription(pairs)

    @property
    def subscription(self) -> tuple[str, ...]:
        return self.stream.subscription

    def drain(self) -> Any:
        return self.stream.drain()

    def drain_gaps(self) -> Any:
        return self.stream.drain_gaps()

    @property
    def connected(self) -> bool:
        return self.stream.connected

    @property
    def dropped_frames(self) -> int:
        return self.stream.dropped_frames

    @property
    def unparsed_frames(self) -> int:
        return self.stream.unparsed_frames


@dataclass
class Clients:
    kraken: RestAndStream
    recorder: FakeRecorder
    store: Any = None


def config(*, allow_crypto_quoted: bool = False, stable: list[str] | None = None) -> MappingConfig:
    """Only the keys engine 2 reads. `stable=None` reproduces the key not existing."""
    trading: dict[str, Any] = {"allow_crypto_quoted": allow_crypto_quoted}
    if stable is not None:
        trading["stable_quote_currencies"] = stable
    return MappingConfig({"mode": "paper", "trading": trading})


@dataclass
class Harness:
    orchestrator: Orchestrator
    fake: FakeKrakenClient
    stream: KrakenWebSocketClient

    def tick(self) -> dict[str, Any]:
        return self.orchestrator.tick()

    def scope(self) -> tuple[str, ...]:
        return self.stream.subscription


def build(cfg: MappingConfig, clock: Any) -> Harness:
    """Engines 1 and 2 through the real orchestrator, over one fake and one stream.

    A function rather than a fixture because every test here configures the flag or
    the stable set differently, and a fixture that took its arguments through a
    marker would be harder to read than the two lines it saved.
    """
    fake = FakeKrakenClient()
    stream = KrakenWebSocketClient(clock=clock, pairs=(), depth=BOOK_DEPTH)
    clients = Clients(kraken=RestAndStream(fake, stream), recorder=FakeRecorder())
    return Harness(
        Orchestrator(
            config=cfg,
            clock=clock,
            clients=clients,
            chains=Chains(guard=[ExchangeEngine(), MarketDataRecorderEngine()]),
        ),
        fake,
        stream,
    )


def eur_pair(fake: FakeKrakenClient, name: str, base: str) -> None:
    fake.set_pair_rule(
        name,
        base=base,
        quote="EUR",
        ordermin="0.001",
        costmin="5.00",
        tick_size="0.01",
        lot_decimals=8,
        pair_decimals=2,
    )


# --------------------------------------------------------------------------- #
# The key engine 2 reads is engine 1's, and is deliberately not imported
# --------------------------------------------------------------------------- #


def test_the_duplicated_state_key_still_matches_engine_ones() -> None:
    """Contract rule 3 forbids the import; this is what stops the copy drifting.

    `market_data_recorder/contracts.py` writes `"exchange"` out rather than importing
    `engines/exchange/contracts.STATE_KEY`, because an engine never imports another
    engine. A test may reach across the boundary that production code may not, which
    is how the duplicate is kept honest without weakening the rule.
    """
    assert EXCHANGE_STATE_KEY == EXCHANGE_KEY


# --------------------------------------------------------------------------- #
# The subscription changes when the balances change — both directions
# --------------------------------------------------------------------------- #


def test_the_scope_follows_the_balances_in_both_directions(fixed_clock: Any) -> None:
    """USD held subscribes to USD-quoted pairs; EUR held subscribes to EUR-quoted ones.

    Both directions, because one is passed by any implementation that happens to
    return the fixture's pairs — and a hardcoded list passes neither. The two
    assertions are also *disjoint sets*, so a scope that simply grew would fail the
    second half rather than quietly satisfying it.
    """
    harness = build(config(stable=STABLE_QUOTES), fixed_clock)
    eur_pair(harness.fake, "BTC/EUR", "BTC")
    eur_pair(harness.fake, "ETH/EUR", "ETH")

    harness.fake.set_balances({"USD": "1000.00"})
    first = harness.tick()
    assert harness.scope() == ("BTC/USD", "ETH/USD", "SOL/USD")
    assert first[RECORDER_KEY]["subscription"] == ["BTC/USD", "ETH/USD", "SOL/USD"]
    assert first[RECORDER_KEY]["subscription_derived"] is True

    harness.fake.set_balances({"EUR": "500.00"})
    second = harness.tick()
    assert harness.scope() == ("BTC/EUR", "ETH/EUR")
    assert second[RECORDER_KEY]["subscription"] == ["BTC/EUR", "ETH/EUR"]


def test_a_quote_currency_held_at_zero_is_not_held(fixed_clock: Any) -> None:
    """Invariant 7 says *spendable*, and zero is not spendable.

    Zero rather than absent is the case worth pinning: an absent currency is an
    obvious exclusion and a zero one looks like a holding in any check that only asks
    whether the key is there.
    """
    harness = build(config(stable=STABLE_QUOTES), fixed_clock)
    eur_pair(harness.fake, "BTC/EUR", "BTC")
    harness.fake.set_balances({"USD": "1000.00", "EUR": "0.00"})

    harness.tick()

    assert harness.scope() == ("BTC/USD", "ETH/USD", "SOL/USD")
    assert "BTC/EUR" not in harness.scope()


def test_an_unchanged_scope_queues_no_further_frames(fixed_clock: Any) -> None:
    """The common case is that nothing moved, and the common case must be silent.

    This runs every tick. A scope that re-subscribed to everything each time would
    pass every assertion about *membership* in this file and hammer the socket once a
    minute forever.

    The stream here is never started, so nothing drains the queue and the frames the
    first tick produced are still sitting in it — which is why this asserts the queue
    did not *grow* rather than that it is empty. The socket-level version, where the
    frames are actually sent and counted, is
    `test_an_unchanged_scope_sends_nothing_on_a_live_socket` in
    `tests/clients/kraken/test_ws.py`; the two are the same property observed either
    side of the send.
    """
    harness = build(config(stable=STABLE_QUOTES), fixed_clock)
    harness.fake.set_balances({"USD": "1000.00"})

    harness.tick()
    after_first = harness.scope()
    queued = len(harness.stream._pending)
    harness.tick()

    assert harness.scope() == after_first
    assert len(harness.stream._pending) == queued


# --------------------------------------------------------------------------- #
# allow_crypto_quoted excludes, and includes
# --------------------------------------------------------------------------- #


def test_a_crypto_quoted_pair_is_excluded_and_flipping_the_flag_includes_it(
    fixed_clock: Any,
) -> None:
    """`ETH/BTC` with a positive BTC balance: eligible on every rule but this one.

    The fixture carries it and `balance.json` holds BTC, which is why this is a real
    exclusion rather than an academic one — the pair passes the pair-rules test and
    the positive-quote-balance test, and invariant 7 is the only thing standing
    between it and the socket.

    Both directions in one test on purpose. Excluding proves nothing on its own: an
    implementation that dropped every pair it did not recognise would pass the first
    half and fail the second.
    """
    excluded = build(config(allow_crypto_quoted=False, stable=STABLE_QUOTES), fixed_clock)
    excluded.tick()
    assert "ETH/BTC" not in excluded.scope()
    assert excluded.scope() == ("BTC/USD", "ETH/USD", "SOL/USD")

    included = build(config(allow_crypto_quoted=True, stable=STABLE_QUOTES), fixed_clock)
    state = included.tick()
    assert "ETH/BTC" in included.scope()
    assert state[RECORDER_KEY]["crypto_quoted_excluded"] is False


def test_the_exclusion_is_reported_as_not_applied_when_the_stable_set_is_absent(
    fixed_clock: Any,
) -> None:
    """`trading.stable_quote_currencies` has not landed, and that is published.

    Escalated to the lead and pending a ruling: the two fail-closed directions point
    opposite ways here. Excluding everything unprovable subscribes to nothing and
    loses order-book history that cannot be recovered; including too much costs
    bandwidth and cannot cause a trade, because engine 7 enforces invariant 7 on the
    universe, which is where a trade is actually decided.

    What must not happen either way is silence. `crypto_quoted_excluded` is False
    here **and** `allow_crypto_quoted` is False, and those two together are the
    signal: a filter that did not run is otherwise indistinguishable from one that
    ran and excluded nothing.
    """
    harness = build(config(allow_crypto_quoted=False, stable=None), fixed_clock)
    state = harness.tick()

    assert state[RECORDER_KEY]["crypto_quoted_excluded"] is False
    assert "ETH/BTC" in harness.scope()


def test_a_missing_optional_key_never_makes_the_recorder_a_gate(fixed_clock: Any) -> None:
    """Engine 2 is not a gate and must not become one by reading config.

    `Config.get` raises on a key that does not exist, which for a gate is right and
    becomes ERROR at the orchestrator. Engine 2 records the feed in every mode
    including frozen, and a tick it fails is a minute of history gone — so the one
    key that may legitimately not exist yet is read without that consequence. This
    fired for real: before the fix, engine 2 displaced `data_guard` as
    `trading_blocked_by`.
    """
    harness = build(config(allow_crypto_quoted=False, stable=None), fixed_clock)
    state = harness.tick()

    assert state.get("trading_blocked_by") is None
    assert state[RECORDER_KEY]["stream_available"] is True


# --------------------------------------------------------------------------- #
# A failed fetch leaves the subscription exactly as it was
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("failing_call", ["asset_pairs", "balance"])
def test_a_failed_fetch_leaves_the_subscription_unchanged(
    fixed_clock: Any, failing_call: str
) -> None:
    """Asserted against the previous tick's scope, never against an empty set.

    The distinction is the whole point. Unsubscribing on a transient private-call
    failure would put a hole in the order-book history of every pair, and that
    history cannot be recovered afterwards — so "I do not know" has to be a different
    answer from "nothing qualifies", and the scope function returns `None` rather
    than `()` to keep them apart.

    Both inputs are parametrised because either can fail on its own: engine 1 gathers
    the three calls with `return_exceptions=True` precisely so one outage does not
    become three blanks.
    """
    harness = build(config(stable=STABLE_QUOTES), fixed_clock)
    harness.fake.set_balances({"USD": "1000.00"})

    first = harness.tick()
    established = harness.scope()
    assert established, "the first tick must establish a non-empty scope to be a test"

    harness.fake.fail(failing_call)
    second = harness.tick()

    # The fetch really did fail, so the assertion below is about the failure path.
    assert second[EXCHANGE_KEY]["failed_fetches"], "the injected failure did not happen"
    assert harness.scope() == established
    assert second[RECORDER_KEY]["subscription"] == first[RECORDER_KEY]["subscription"]
    assert second[RECORDER_KEY]["subscription_derived"] is False
    assert harness.scope() != ()


def test_the_scope_recovers_once_the_fetch_does(fixed_clock: Any) -> None:
    """Unchanged is a pause, not a latch.

    Worth its own test: an implementation that stopped deriving after the first
    failure would pass every assertion in the test above and never subscribe to a new
    listing again.
    """
    harness = build(config(stable=STABLE_QUOTES), fixed_clock)
    eur_pair(harness.fake, "BTC/EUR", "BTC")
    harness.fake.set_balances({"USD": "1000.00"})
    harness.tick()

    harness.fake.fail("asset_pairs")
    harness.tick()

    harness.fake.clear_failures("asset_pairs")
    harness.fake.set_balances({"EUR": "500.00"})
    state = harness.tick()

    assert harness.scope() == ("BTC/EUR",)
    assert state[RECORDER_KEY]["subscription_derived"] is True


def test_the_scope_starts_empty_rather_than_defaulting_to_a_pair_list(fixed_clock: Any) -> None:
    """Before the first tick the daemon is subscribed to nothing, by construction.

    There is no pair list, no config key holding one and no default. The socket
    learns what to listen to from engine 1's first tick, which is what makes the
    Locked Decision — the universe is computed per tick — true of the subscription
    scope as well.
    """
    harness = build(config(stable=STABLE_QUOTES), fixed_clock)

    assert harness.scope() == ()

    harness.tick()

    assert harness.scope() != ()


def test_engine_one_publishing_nothing_leaves_the_scope_alone_and_says_so(
    fixed_clock: Any,
) -> None:
    """The other absence: no `state["exchange"]` at all, rather than a failed fetch.

    It happens when engine 1 raised and the orchestrator recorded `ERROR`, and it
    happens whenever engine 2 runs in a chain engine 1 is not in — which is most of
    `test_market_data_recorder.py`. Engine 2 has nothing to derive from and must leave
    the subscription exactly as it is.

    **Found by mutation, not by design.** Flipping this branch's `subscription_derived`
    from False to True survived every other test in the file: the branch was executed
    constantly and asserted nowhere, so a tick that had left the scope alone could have
    claimed it had recomputed it and nothing would have noticed. That is the difference
    between a line being covered and a line being tested.
    """
    fake = FakeKrakenClient()
    stream = KrakenWebSocketClient(clock=fixed_clock, pairs=(), depth=BOOK_DEPTH)
    clients = Clients(kraken=RestAndStream(fake, stream), recorder=FakeRecorder())
    orchestrator = Orchestrator(
        config=config(stable=STABLE_QUOTES),
        clock=fixed_clock,
        clients=clients,
        # Engine 1 is deliberately absent from this chain.
        chains=Chains(guard=[MarketDataRecorderEngine()]),
    )
    established = ("BTC/USD", "ETH/USD")
    stream.set_subscription(established)

    state = orchestrator.tick()

    assert EXCHANGE_KEY not in state
    assert stream.subscription == established
    assert state[RECORDER_KEY]["subscription"] == list(established)
    assert state[RECORDER_KEY]["subscription_derived"] is False
    assert state[RECORDER_KEY]["crypto_quoted_excluded"] is False
