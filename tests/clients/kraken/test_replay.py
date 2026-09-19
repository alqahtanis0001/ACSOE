"""Spec 129: the replay client, over fabricated partitions and the real fee schedule.

The spec's three checks are here by name: construction refused in paper and in live
(each proven, and proven to happen before any fixture is opened); engine 9's own walk
over the declared book reproducing a hand computation on a thin bucket and a deep one;
and the stream never yielding a trade stamped after `now`, proven with a clock that
lags a planted trade.

The hand computations use `fractions.Fraction`, which is exact, so they share no
arithmetic with the client or engine 9. The comparison allows a relative 1e-20, and
that tolerance is the Decimal context's and nothing else: `walk_the_bid_side` divides
at 28 significant digits, and a level's `1000 / price` is not a terminating decimal.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.kraken.errors import KrakenUnavailableError
from acsoe.clients.kraken.replay import ReplayKrakenClient, ReplayModeError
from acsoe.clients.kraken.replay_scenario import DECLARED_STATEMENT, ScenarioError
from acsoe.core.contracts import EngineContext
from acsoe.engines.order_book.engine import OrderBookEngine
from acsoe.platform.clock import FixedClock
from acsoe.platform.config import derive_config, load_config
from tests.clients.kraken.replay_fixtures import BUCKETS, REPO, WEEK_0, Scenario, write_scenario

#: A Tuesday inside the second partition week, on a bar close.
NOW = WEEK_0 + 7 * 24 * 3600 + 3 * 24 * 3600 + 12 * 3600
HOUR = 3600


def at(moment_s: int | float) -> datetime:
    return datetime.fromtimestamp(moment_s, UTC)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def client_for(scenario: Scenario, clock: FixedClock) -> ReplayKrakenClient:
    return ReplayKrakenClient.from_config(scenario.config, clock=clock, root=scenario.root)


def steady(archive: str, *, price: str, qty: str, start: int, end: int, every: int) -> list[tuple[int, str, str]]:
    return [(ts, price, qty) for ts in range(start, end, every)]


@pytest.fixture
def scenario(tmp_path: Path) -> Scenario:
    # BTC trades $250 every minute for two days: $360,000 a day, the $100k-1M bucket.
    # THIN trades $100 an hour: $2,400 a day, the <$10k bucket.
    return write_scenario(
        tmp_path,
        {
            "XBTUSD": steady("XBTUSD", price="50000", qty="0.005", start=NOW - 2 * 86400, end=NOW + 86400, every=60),
            "THINUSD": steady("THINUSD", price="100", qty="1", start=NOW - 2 * 86400, end=NOW + 86400, every=HOUR),
            "ETHUSD": [(NOW - 3 * 86400, "3000", "1")],
            "GONEUSD": [(NOW - 60, "1", "1")],
        },
    )


# --------------------------------------------------------------------------- #
# Construction: replay mode only (invariant 2's amendment, spec 126)
# --------------------------------------------------------------------------- #


def test_construction_is_refused_in_paper_mode_before_any_fixture_is_read(tmp_path: Path) -> None:
    """The committed config is paper. Its `replay:` section is pointed here at files that
    do not exist, so a client that opened a fixture before looking at the mode would fail
    with `ScenarioError` naming a missing file. It fails with the mode instead, which is
    what proves which refusal ran first."""
    committed = load_config(REPO / "config" / "default.yaml", load_env=False)
    assert committed.mode == "paper"
    missing = {key: (tmp_path / f"absent-{key}.json").as_posix() for key in (
        "asset_pairs_file", "instrument_file", "pair_names_file", "spread_table_file",
        "fee_schedule_file",
    )}
    replay = committed.get("replay")
    assert replay is not None
    paper = derive_config(committed, {"replay": {**replay.model_dump(), **missing}})
    with pytest.raises(ReplayModeError, match="mode 'paper'"):
        ReplayKrakenClient.from_config(paper, clock=FixedClock(at(NOW)), root=REPO)


def test_construction_is_refused_in_live_mode_before_any_fixture_is_read() -> None:
    """`Config` refuses live itself (invariant 1), so a live config can only reach this
    client as something shaped like one. It is refused on its mode, and `get` is never
    called, so no file named in it is opened."""

    class LiveShaped:
        mode = "live"

        def get(self, key: str) -> Any:
            raise AssertionError(f"read {key} before refusing the mode")

    with pytest.raises(ReplayModeError, match="mode 'live'"):
        ReplayKrakenClient.from_config(LiveShaped(), clock=FixedClock(at(NOW)), root=REPO)


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_the_constructor_itself_refuses_outside_replay(scenario: Scenario, mode: str) -> None:
    built = client_for(scenario, FixedClock(at(NOW)))
    with pytest.raises(ReplayModeError, match=f"refused in mode '{mode}'"):
        ReplayKrakenClient(
            mode=mode,
            clock=FixedClock(at(NOW)),
            scenario=built.scenario,
            tape=built._tape,
            interval_s=900,
            published_bars=200,
        )


def test_it_constructs_in_replay_mode(scenario: Scenario) -> None:
    client = client_for(scenario, FixedClock(at(NOW)))
    assert client.connected is True


# --------------------------------------------------------------------------- #
# The stream: never a second past `now`
# --------------------------------------------------------------------------- #


def test_the_stream_never_yields_a_trade_stamped_after_now(tmp_path: Path) -> None:
    """A trade planted one second after the clock. At `now` it is not served, not even
    at `now` plus half a second (a trade's second is served only once the clock has
    reached it); at the planted second it is."""
    planted = NOW + 1
    scenario = write_scenario(
        tmp_path,
        {"XBTUSD": [(NOW - 600, "50000", "0.1"), (planted, "51000", "0.2")]},
    )
    clock = FixedClock(at(NOW))
    client = client_for(scenario, clock)
    client.set_subscription(["BTC/USD"])

    def stamps() -> list[int]:
        return [int(trade.ts.timestamp()) for trade in client.recent_trades()]

    assert stamps() == [NOW - 600]
    clock.set(at(NOW) + timedelta(microseconds=500_000))
    assert stamps() == [NOW - 600]
    assert client.trailing_volume_usd("BTC/USD") == Decimal("5000.0")
    clock.set(at(planted))
    assert stamps() == [NOW - 600, planted]
    assert client.trailing_volume_usd("BTC/USD") == Decimal("5000.0") + Decimal("10200.0")


def test_recent_trades_is_the_bar_aligned_published_window(tmp_path: Path) -> None:
    """`[bar_open(now) - 200 bars, now]`: the first trade of the oldest published bar is
    in, the last trade of the bar before it is out, so no published candle is partial."""
    bar_open = (NOW // 900) * 900
    lower = bar_open - 200 * 900
    scenario = write_scenario(
        tmp_path,
        {"XBTUSD": [(lower - 1, "1", "1"), (lower, "2", "1"), (NOW, "3", "1")]},
    )
    client = client_for(scenario, FixedClock(at(NOW)))
    client.set_subscription(["BTC/USD"])
    assert [str(trade.price) for trade in client.recent_trades()] == ["2", "3"]


def test_only_subscribed_pairs_are_served(scenario: Scenario) -> None:
    client = client_for(scenario, FixedClock(at(NOW)))
    assert client.recent_trades() == ()
    client.set_subscription(["THIN/USD"])
    assert {trade.pair for trade in client.recent_trades()} == {"THIN/USD"}


def test_an_archive_pair_with_no_rules_is_never_served_and_is_named(scenario: Scenario) -> None:
    """Survivorship: GONEUSD traded and has no recorded rules. It is absent, not patched,
    and the scenario description names it."""
    client = client_for(scenario, FixedClock(at(NOW)))
    client.set_subscription(["BTC/USD", "ETH/USD", "THIN/USD", "GONEUSD", "GONE/USD"])
    assert {trade.pair for trade in client.recent_trades()} <= {"BTC/USD", "THIN/USD", "ETH/USD"}
    description = json.loads(client.scenario_description)
    assert description["partitions"]["archive_pairs_without_rules"] == ["GONEUSD"]


def test_no_frame_and_no_gap_is_ever_drained(scenario: Scenario) -> None:
    """A replay writes nothing to the archive, and history has no outages."""
    client = client_for(scenario, FixedClock(at(NOW)))
    assert client.drain() == ()
    assert client.drain_gaps() == ()
    assert client.gaps == ()


# --------------------------------------------------------------------------- #
# The declared book
# --------------------------------------------------------------------------- #


def test_a_pair_with_no_trade_in_24_hours_has_no_quote_and_no_book(scenario: Scenario) -> None:
    """ETH last traded three days ago. Absent, never a zero spread."""
    client = client_for(scenario, FixedClock(at(NOW)))
    assert client.latest_quote("ETH/USD") is None
    with pytest.raises(KrakenUnavailableError, match="no trade in the trailing 24 hours"):
        run(client.order_book("ETH/USD", 10))


def test_the_24_hour_window_excludes_a_trade_exactly_24_hours_old(tmp_path: Path) -> None:
    scenario = write_scenario(tmp_path, {"THINUSD": [(NOW - 86400, "1", "1")]})
    clock = FixedClock(at(NOW - 1))
    client = client_for(scenario, clock)
    assert client.latest_quote("THIN/USD") is not None
    clock.set(at(NOW))
    assert client.latest_quote("THIN/USD") is None


def test_the_quote_is_the_declared_spread_around_the_last_price_stamped_now(scenario: Scenario) -> None:
    client = client_for(scenario, FixedClock(at(NOW)))
    quote = client.latest_quote("THIN/USD")
    assert quote is not None
    assert quote.ts == at(NOW)
    # THIN: <$10k bucket, 30.4 bps, so 15.2 bps each side of 100.
    assert quote.bid == Decimal("99.848")
    assert quote.ask == Decimal("100.152")


@pytest.mark.parametrize(
    ("qty", "bucket"),
    [("99.99", "<$10k"), ("100", "$10k-100k"), ("999.99", "$10k-100k"), ("1000", "$100k-1M"),
     ("99999", "$1M-10M"), ("100000", ">$10M")],
)
def test_the_bucket_follows_trailing_24_hour_dollar_volume(tmp_path: Path, qty: str, bucket: str) -> None:
    """One trade at $100 sets the volume. Lower bounds are inclusive, upper exclusive."""
    scenario = write_scenario(tmp_path, {"THINUSD": [(NOW - 60, "100", qty)]})
    client = client_for(scenario, FixedClock(at(NOW)))
    volume = client.trailing_volume_usd("THIN/USD")
    assert volume is not None
    assert client.scenario.table.bucket_for(volume).name == bucket


def _walk_by_hand(mid: Fraction, spread_bps: Fraction, depth_bps: Fraction, basis: Fraction) -> tuple[Fraction, Fraction, int]:
    """Engine 9's walk re-done in exact rationals over the book spec 129 describes: ten
    bid levels from the half-spread to the declared depth, evenly spaced, $1,000 each."""
    half = spread_bps / 10_000 / 2
    far = depth_bps / 10_000
    levels = [(mid * (1 - (half + (far - half) * i / 9)), Fraction(1000)) for i in range(10)]
    remaining, base, used = basis, Fraction(0), 0
    for price, notional in levels:
        used += 1
        if notional >= remaining:
            base += remaining / price
            remaining = Fraction(0)
            break
        base += notional / price
        remaining -= notional
    fill = basis / base
    return levels[0][0], fill, used


@pytest.mark.parametrize(
    ("archive", "symbol", "price", "qty", "bucket"),
    [
        ("THINUSD", "THIN/USD", "100", "1", BUCKETS[0]),
        ("XBTUSD", "BTC/USD", "50000", "40", BUCKETS[3]),
    ],
)
def test_engine_9_walks_the_declared_book_to_the_hand_computed_slippage(
    tmp_path: Path, archive: str, symbol: str, price: str, qty: str, bucket: dict[str, Any]
) -> None:
    """The real engine 9, unchanged, walking a $5,000 balance into the declared book of a
    thin bucket and of a deep one."""
    scenario = write_scenario(tmp_path, {archive: [(NOW - 60, price, qty)]})
    clock = FixedClock(at(NOW))
    client = client_for(scenario, clock)
    volume = client.trailing_volume_usd(symbol)
    assert volume is not None
    assert client.scenario.table.bucket_for(volume).name == bucket["name"]

    class Clients:
        kraken = client
        store = None
        recorder = None

    rules = run(client.asset_pairs())
    state = {
        "scout": {"pair": symbol},
        "exchange": {"pair_rules": rules.state_dict(), "balances": {"USD": "5000.00"}},
    }
    context = EngineContext(mode="replay", run_id="t", now=at(NOW), config=scenario.config, clients=Clients())
    published = OrderBookEngine().process(context, state).data

    best, fill, used = _walk_by_hand(
        Fraction(price), Fraction(bucket["spread_bps"]), Fraction(bucket["depth_bps"]), Fraction(5000)
    )
    assert Fraction(published["best_bid"]) == best
    assert published["levels_consumed"] == used == 5
    engine_fill = Fraction(Decimal(published["fill_price"]))
    assert abs(engine_fill - fill) / fill < Fraction(1, 10**20)
    expected_slippage = (best - fill) / best
    engine_slippage = Fraction(Decimal(published["estimated_slippage_pct"]))
    assert abs(engine_slippage - expected_slippage) < Fraction(1, 10**20)


def test_the_book_is_ten_levels_reaching_the_notional_at_the_declared_depth(scenario: Scenario) -> None:
    client = client_for(scenario, FixedClock(at(NOW)))
    book = run(client.order_book("THIN/USD", 10))
    assert len(book.bids) == len(book.asks) == 10
    # The tenth level sits at the declared depth, 60.2 bps from the mid of 100.
    assert book.bids[-1][0] == Decimal("99.398")
    assert book.asks[-1][0] == Decimal("100.602")
    total = sum(price * qty for price, qty in book.bids)
    assert abs(total - Decimal(10_000)) < Decimal("1e-20")
    assert len(run(client.order_book("THIN/USD", 3)).bids) == 3


# --------------------------------------------------------------------------- #
# Rules, fees, account and orders
# --------------------------------------------------------------------------- #


def test_rules_are_keyed_by_v2_symbol_and_read_exactly(scenario: Scenario) -> None:
    client = client_for(scenario, FixedClock(at(NOW)))
    rules = run(client.asset_pairs())
    assert set(rules.pairs) == {"BTC/USD", "ETH/USD", "THIN/USD", "NEW/USD"}
    btc = rules.pairs["BTC/USD"]
    assert (btc.base, btc.quote) == ("BTC", "USD")
    assert btc.state_dict()["ordermin"] == "0.0001"
    assert btc.state_dict()["tick_size"] == "0.1"
    assert client.scenario.rules.archive_symbols == {
        "XBTUSD": "BTC/USD", "ETHUSD": "ETH/USD", "THINUSD": "THIN/USD", "NEWUSD": "NEW/USD",
    }


def test_a_long_increment_survives_the_json_read_exactly(tmp_path: Path) -> None:
    """`0.00000001` as a JSON number is read as a Decimal, not through a float."""
    extra = {"symbol": "DUST/USD", "base": "DUST", "quote": "USD", "status": "online",
             "qty_precision": 8, "price_precision": 9, "qty_min": 0.00000001,
             "cost_min": 0.5, "tick_size": 0.000000001}
    scenario = write_scenario(tmp_path, {"XBTUSD": [(NOW, "1", "1")]}, instrument_extra=[extra])
    rules = run(client_for(scenario, FixedClock(at(NOW))).asset_pairs())
    assert rules.pairs["DUST/USD"].ordermin == Decimal("0.00000001")
    assert rules.pairs["DUST/USD"].state_dict()["tick_size"] == "0.000000001"


@pytest.mark.parametrize(("tier", "maker", "taker"), [(3, "0.0022", "0.0038"), (5, "0.0015", "0.0030")])
def test_the_fee_is_the_declared_schedule_at_the_configured_tier(
    tmp_path: Path, tier: int, maker: str, taker: str
) -> None:
    scenario = write_scenario(tmp_path, {"XBTUSD": [(NOW, "1", "1")]}, tier=tier)
    fee = run(client_for(scenario, FixedClock(at(NOW))).trade_volume())
    assert (fee.tier, fee.maker_fee_pct, fee.taker_fee_pct) == (tier, Decimal(maker), Decimal(taker))


def test_a_tier_absent_from_the_schedule_is_refused(tmp_path: Path) -> None:
    scenario = write_scenario(tmp_path, {"XBTUSD": [(NOW, "1", "1")]}, tier=99)
    with pytest.raises(ScenarioError, match="0 rows named 'Tier 99'"):
        client_for(scenario, FixedClock(at(NOW)))


def test_there_is_no_balance_and_no_order_here(scenario: Scenario) -> None:
    client = client_for(scenario, FixedClock(at(NOW)))
    with pytest.raises(KrakenUnavailableError, match="paper broker"):
        run(client.balance())
    with pytest.raises(KrakenUnavailableError, match="places no order"):
        run(client.open_orders())
    with pytest.raises(KrakenUnavailableError, match="places no order"):
        run(client.cancel_order(1))


# --------------------------------------------------------------------------- #
# The table's own refusals
# --------------------------------------------------------------------------- #


def test_a_table_with_a_gap_is_refused(tmp_path: Path) -> None:
    broken = [dict(row) for row in BUCKETS]
    broken[1]["lower_usd"] = "10001"
    scenario = write_scenario(tmp_path, {"XBTUSD": [(NOW, "1", "1")]}, buckets=broken)
    with pytest.raises(ScenarioError, match="leave a gap or overlap"):
        client_for(scenario, FixedClock(at(NOW)))


def test_a_depth_inside_the_half_spread_is_refused(tmp_path: Path) -> None:
    broken = [dict(row) for row in BUCKETS]
    broken[0]["depth_bps"] = "15.1"
    scenario = write_scenario(tmp_path, {"XBTUSD": [(NOW, "1", "1")]}, buckets=broken)
    with pytest.raises(ScenarioError, match="inside the half-spread"):
        client_for(scenario, FixedClock(at(NOW)))


# --------------------------------------------------------------------------- #
# Identity (spec 134) and determinism across a resume
# --------------------------------------------------------------------------- #


def test_the_digest_is_the_hash_of_the_description_and_says_declared(scenario: Scenario) -> None:
    import hashlib

    client = client_for(scenario, FixedClock(at(NOW)))
    description = client.scenario_description
    assert client.scenario_digest == hashlib.sha256(description.encode("ascii")).hexdigest()
    parsed = json.loads(description)
    assert parsed["declared"] == DECLARED_STATEMENT
    assert parsed["fee"]["maker_fee_pct"] == "0.0022"
    assert [bucket["spread_bps"] for bucket in parsed["spread_book_table"]["buckets"]] == [
        "30.4", "25.8", "12.3", "5.5", "5.5"
    ]


@pytest.mark.parametrize("change", ["tier", "table", "extras"])
def test_the_digest_moves_with_every_input(tmp_path: Path, change: str) -> None:
    trades = {"XBTUSD": [(NOW, "1", "1")]}
    base = write_scenario(tmp_path / "a", trades)
    before = client_for(base, FixedClock(at(NOW))).scenario_digest
    if change == "tier":
        other = write_scenario(tmp_path / "b", trades, tier=5)
        after = client_for(other, FixedClock(at(NOW))).scenario_digest
    elif change == "table":
        rows = [dict(row) for row in BUCKETS]
        rows[2]["spread_bps"] = "12.5"
        rows[2]["depth_bps"] = "24.25"
        other = write_scenario(tmp_path / "b", trades, buckets=rows)
        after = client_for(other, FixedClock(at(NOW))).scenario_digest
    else:
        after = ReplayKrakenClient.from_config(
            base.config, clock=FixedClock(at(NOW)), root=base.root, extras={"ranking": "x"}
        ).scenario_digest
    assert after != before


def test_the_rolling_state_walked_minute_by_minute_equals_a_fresh_client(scenario: Scenario) -> None:
    """What a resumed run relies on: a client started cold at T serves exactly the book a
    client that walked every minute up to T serves. Exact Decimal sums, not approximate."""
    clock = FixedClock(at(NOW - 2 * HOUR))
    walked = client_for(scenario, clock)
    for minute in range(2 * 60 + 1):
        clock.set(at(NOW - 2 * HOUR + minute * 60))
        walked.latest_quote("BTC/USD")
    fresh = client_for(scenario, FixedClock(at(NOW)))
    for pair in ("BTC/USD", "THIN/USD", "ETH/USD"):
        assert walked.trailing_volume_usd(pair) == fresh.trailing_volume_usd(pair)
        assert walked.latest_quote(pair) == fresh.latest_quote(pair)


def test_the_clock_may_not_run_backwards(scenario: Scenario) -> None:
    clock = FixedClock(at(NOW))
    client = client_for(scenario, clock)
    client.latest_quote("BTC/USD")
    clock.set(at(NOW - 60))
    with pytest.raises(ValueError, match="backwards"):
        client.latest_quote("BTC/USD")


def test_a_config_built_for_replay_keeps_the_committed_file_paper() -> None:
    committed = load_config(REPO / "config" / "default.yaml", load_env=False)
    assert committed.mode == "paper"
    assert derive_config(committed, {"mode": "replay"}).mode == "replay"


# --------------------------------------------------------------------------- #
# The seams, with no double: engine 3 reading the stream, the broker wrapping it
# --------------------------------------------------------------------------- #


def test_engine_3_publishes_the_declared_spread_exactly(scenario: Scenario) -> None:
    from acsoe.engines.market_sensor.engine import MarketSensorEngine

    client = client_for(scenario, FixedClock(at(NOW)))
    client.set_subscription(["BTC/USD", "THIN/USD"])

    class Clients:
        kraken = client
        store = None
        recorder = None

    context = EngineContext(
        mode="replay", run_id="t", now=at(NOW), config=scenario.config, clients=Clients(),
        previous_now=at(NOW - 60),
    )
    published = MarketSensorEngine().process(context, {}).data
    assert Decimal(published["quotes"]["THIN/USD"]["spread_pct"]) == Decimal("0.00304")
    assert Decimal(published["quotes"]["BTC/USD"]["spread_pct"]) == Decimal("0.00123")
    assert published["quotes"]["THIN/USD"]["age_s"] == 0
    assert published["bar_closed"] is True
    # 200 closed hourly-traded THIN bars would need 50 hours; the tape holds 48 of trades.
    assert {candle["pair"] for candle in published["candles"]} == {"BTC/USD", "THIN/USD"}


def test_the_paper_broker_rests_and_fills_a_post_only_buy_over_the_replay(
    tmp_path: Path, migrated_db: Path
) -> None:
    """B's broker, unchanged, wrapping this client: the post-only buy at the declared bid
    rests, a later trade at the bid does not fill it, one strictly below does, and the fee
    is the declared tier-3 maker rate."""
    from acsoe.clients.kraken.contracts import OrderRequest, OrderSide, OrderStatus, OrderType
    from acsoe.clients.paper.broker import PaperBroker
    from acsoe.clients.store.client import StoreClient

    scenario = write_scenario(
        tmp_path,
        {"THINUSD": [(NOW - 60, "100", "1"), (NOW + 30, "99.848", "1"), (NOW + 90, "99.8", "1")]},
    )
    clock = FixedClock(at(NOW))
    client = client_for(scenario, clock)
    client.set_subscription(["THIN/USD"])
    store = StoreClient(migrated_db)
    try:
        broker = PaperBroker(client, store=store, config=scenario.config, clock=clock)
        quote = client.latest_quote("THIN/USD")
        assert quote is not None
        ack = run(
            broker.add_order(
                OrderRequest(pair="THIN/USD", side=OrderSide.BUY, order_type=OrderType.LIMIT,
                             qty=Decimal("10"), limit_price=quote.bid, post_only=True, userref=7)
            )
        )
        assert str(ack.status) == "resting"
        clock.set(at(NOW + 60))
        (state,) = run(broker.query_orders([7]))
        assert state.status is OrderStatus.RESTING
        clock.set(at(NOW + 120))
        (state,) = run(broker.query_orders([7]))
        assert state.status is OrderStatus.FILLED
        assert state.avg_fill_price == Decimal("99.848")
        assert state.fee == Decimal("99.848") * Decimal("10") * Decimal("0.0022")
    finally:
        store.close()


def test_the_committed_recordings_and_a_real_partition_load_with_no_double(tmp_path: Path) -> None:
    """The seams with spec 127 and spec 128, with nothing fabricated between them: the
    committed `instrument` capture and name join, and a partition written by a-data's own
    `scripts/partition_trades.py` from a source file in the archive's shape. The rule
    values asserted are the recording's own, as the capture holds them."""
    import importlib.util

    import polars as pl

    from acsoe.clients.kraken.replay import TradeTape
    from acsoe.clients.kraken.replay_scenario import load_pair_rules

    fixtures = REPO / "tests" / "fixtures" / "kraken"
    rules = load_pair_rules(
        fixtures / "instrument_recorded_2026-09-19.json",
        fixtures / "pair_names_recorded_2026-09-19.json",
        asset_pairs_path=fixtures / "asset_pairs_recorded_2026-09-19.json",
    )
    assert rules.archive_symbols["XBTUSD"] == "BTC/USD"
    assert rules.archive_symbols["XDGUSD"] == "DOGE/USD"
    btc = rules.rules["BTC/USD"]
    assert (btc.base, btc.quote) == ("BTC", "USD")
    assert len(rules.rules) == 1450

    spec = importlib.util.spec_from_file_location("partition_script", REPO / "scripts" / "partition_trades.py")
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    source = tmp_path / "XBTUSD.csv"
    first = WEEK_0 + 7 * 86400
    source.write_bytes(
        f"{first + 5},63810.0,0.10000000\r\n{first + 5},63809.9,0.0031459\r\n{first + 700},1E-8,2\r\n".encode()
    )
    out = tmp_path / "partitions"
    stats = script.partition_pair("XBTUSD", source, out, start=first, end=first + 7 * 86400)
    tape = TradeTape(
        out,
        manifest={"pairs": {"XBTUSD": stats}},
        archive_symbols=rules.archive_symbols,
        keep_s=3600,
    )
    tape.ensure(first + 3600)
    start, end = tape.bounds(first, first + 3600)
    served = [tape.tick(index) for index in range(start, end)]
    assert [(trade.pair, str(trade.price), str(trade.qty)) for trade in served] == [
        ("BTC/USD", "63810.0", "0.10000000"),
        ("BTC/USD", "63809.9", "0.0031459"),
        ("BTC/USD", "1E-8", "2"),
    ]
    assert pl.read_parquet(out / "XBTUSD" / f"{datetime.fromtimestamp(first, UTC):%Y-%m-%d}.parquet").height == 3


def test_the_committed_bucket_table_loads_with_its_medians_and_its_mapped_row() -> None:
    """Spec 130's committed fixture, read by the real loader: five buckets covering every
    volume, each serving its median exactly as written, `>$10M` serving `$1M-10M`'s."""
    from acsoe.clients.kraken.replay_scenario import load_spread_table

    table = load_spread_table(REPO / "tests" / "fixtures" / "replay" / "spread_book_table_2026-09-19.json")
    names = [bucket.name for bucket in table.buckets]
    assert names == ["<$10k", "$10k-100k", "$100k-1M", "$1M-10M", ">$10M"]
    thin, top = table.buckets[0], table.buckets[-1]
    assert thin.spread_bps == Decimal("30.395200000000003")
    assert thin.depth_bps == Decimal("86.2069")
    assert (top.spread_bps, top.depth_bps, top.values_from) == (
        table.buckets[3].spread_bps, table.buckets[3].depth_bps, "$1M-10M"
    )
    assert table.bucket_for(Decimal("9999.99")).name == "<$10k"
    assert table.bucket_for(Decimal("10000000")).name == ">$10M"


def test_a_capture_that_does_not_match_its_own_hash_is_refused(tmp_path: Path) -> None:
    """Spec 127 records each payload's sha256. A capture edited afterwards is refused."""
    import hashlib as _hashlib

    from acsoe.clients.kraken.replay_scenario import load_pair_rules
    from tests.clients.kraken.replay_fixtures import instrument_snapshot, pair_names

    text = json.dumps(instrument_snapshot())
    edited = text.replace('"qty_min": 0.0001', '"qty_min": 0.001')
    assert edited != text
    capture = tmp_path / "instrument.json"
    capture.write_text(
        json.dumps({"provenance": {"payload_sha256": _hashlib.sha256(text.encode()).hexdigest()},
                    "payload": edited}),
        encoding="utf-8",
    )
    names = tmp_path / "names.json"
    names.write_text(json.dumps(pair_names()), encoding="utf-8")
    with pytest.raises(ScenarioError, match="does not match its own hash"):
        load_pair_rules(capture, names)


def test_the_scenario_description_names_the_no_quote_window(scenario: Scenario) -> None:
    """D7: the trailing window that decides which pairs quote is part of the identity."""
    description = json.loads(client_for(scenario, FixedClock(at(NOW))).scenario_description)
    assert description["quote_rule"]["trailing_window_s"] == 86400
