"""The scripted market, checked against the engine that actually reads it. Spec 100.

Every assertion here is either about a property a criterion will depend on, or about a
way this harness could be *kinder than the real stream* — which is the one thing a test
double must never be, because a kind double hides fail-closed bugs.

The important ones drive **engine 3 `market_sensor`** rather than reading the harness's
own fields back. A stream double that satisfies its own tests and not the engine's
expectations is a double that will make a Phase 6 criterion green for the wrong reason.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import acsoe.clients.paper
from tests.conftest import require_module
from tests.harness.doubles import FixedClock, load_default_config
from tests.harness.market_script import MAX_TRADES_PER_BAR, Bar, ScriptedMarket, bar_trades

INTERVAL = 900
TICK = 60
PUBLISHED = 200
PAIR = "BTC/USD"
ORIGIN = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())


def rising_bars(count: int, *, start: str = "100.00", step: str = "0.10") -> list[Bar]:
    """A plain ascending series, each bar's high and low straddling its close."""
    price = Decimal(start)
    bars: list[Bar] = []
    for index in range(count):
        close = price + Decimal(step) * index
        bars.append(
            Bar(
                ts=ORIGIN + index * INTERVAL,
                open=close - Decimal("0.05"),
                high=close + Decimal("0.08"),
                low=close - Decimal("0.09"),
                close=close,
                volume=Decimal("12.5"),
                # Varying on purpose; `trades_z_*` is a z-score and a constant count
                # divides by zero. See the module docstring.
                trades=30 + index * 3,
            )
        )
    return bars


@pytest.fixture
def market() -> ScriptedMarket:
    clock = FixedClock(datetime.fromtimestamp(ORIGIN, tz=UTC))
    return ScriptedMarket(
        clock=clock, interval_s=INTERVAL, published_bars=PUBLISHED, pairs=(PAIR,)
    )


# --------------------------------------------------------------------------- #
# Rebuilding a bar
# --------------------------------------------------------------------------- #


def test_the_trades_rebuild_the_bar_exactly() -> None:
    """Open, high, low and close come back out, and the volume adds up to the cent.

    Checked through the **real** `build_candles`, not by re-deriving the four numbers
    here: two implementations of one rule agree with each other for exactly as long as
    they are wrong in the same way.
    """
    candles_module = require_module(
        "acsoe.engines.market_sensor.candles", reason="the candle builder does not exist yet"
    )
    bar = Bar(
        ts=ORIGIN,
        open=Decimal("100.00"),
        high=Decimal("101.50"),
        low=Decimal("99.25"),
        close=Decimal("100.75"),
        volume=Decimal("12.5"),
        trades=37,
    )
    candles = candles_module.build_candles(
        tuple(bar_trades(bar, pair=PAIR, interval_s=INTERVAL)), interval_s=INTERVAL
    )
    assert len(candles) == 1
    built = candles[0]
    assert built.open == bar.open
    assert built.high == bar.high
    assert built.low == bar.low
    assert built.close == bar.close
    assert built.volume == bar.volume


def test_the_trade_count_varies_bar_to_bar() -> None:
    """The requirement that is correctness rather than realism.

    `trades_z_*` is a z-score over a lookback of trade counts. A constant count is a
    zero-variance window, which divides by zero, publishes null, and makes engine 13
    refuse the whole market-quality vector as incomplete — correctly. A fixture that
    cannot exhibit the property the criterion is about is worse than no fixture, and B
    hit this twice building the Phase 5 rehearsal.
    """
    counts = {
        len(bar_trades(bar, pair=PAIR, interval_s=INTERVAL)) for bar in rising_bars(12)
    }
    assert len(counts) > 1, counts
    assert max(counts) <= MAX_TRADES_PER_BAR


def test_the_count_does_not_saturate_at_the_ceiling() -> None:
    """B's second finding, which the first fix reintroduced.

    `min(trades, 24)` looks like the obvious bound and it saturates: real bars routinely
    carry hundreds of trades, so every bar sits at the ceiling and the count is constant
    again — the same zero-variance defect one level down. A bar with a thousand trades
    must still differ from its neighbour.
    """
    busy = [
        Bar.flat(ORIGIN + index * INTERVAL, "100.00", trades=1000 + index)
        for index in range(6)
    ]
    counts = {len(bar_trades(bar, pair=PAIR, interval_s=INTERVAL)) for bar in busy}
    assert len(counts) > 1, counts


def test_a_flat_bar_cannot_touch_a_barrier_by_accident() -> None:
    """`Bar.flat` is what a criterion fills the uninteresting stretches with.

    Its high and low equal its close, so the only thing that can touch a stop or a
    target in a scripted market is a touch somebody planted. A filler bar that wandered
    would make a round trip's outcome depend on the filler.
    """
    bar = Bar.flat(ORIGIN, "100.00")
    prices = {trade.price for trade in bar_trades(bar, pair=PAIR, interval_s=INTERVAL)}
    assert prices == {Decimal("100.00")}


# --------------------------------------------------------------------------- #
# The clock is the only thing that moves
# --------------------------------------------------------------------------- #


def test_no_trade_from_the_future_is_ever_visible(market: ScriptedMarket) -> None:
    """Look-ahead, and it is the failure hardest to see from outside.

    Every number involved is real; the only thing wrong is *when* the engine saw it. A
    stream that handed engine 3 a trade from two bars ahead would produce a feature row
    that predicts beautifully and cannot exist live.
    """
    market.plant(PAIR, rising_bars(6))
    assert market.recent_trades() == ()
    market.clock.advance(INTERVAL * 2)
    seen = market.recent_trades()
    assert seen
    assert max(trade.ts for trade in seen) <= market.clock.now()


def test_the_window_is_trimmed_to_published_bars() -> None:
    """The harness must not keep more history than the live stream does.

    `market_sensor.published_bars` bounds what a daemon can see, and a feature lookback
    that fills here but could never fill live is a criterion passing on a window the
    system does not have.
    """
    clock = FixedClock(datetime.fromtimestamp(ORIGIN, tz=UTC))
    small = ScriptedMarket(clock=clock, interval_s=INTERVAL, published_bars=3, pairs=(PAIR,))
    small.plant(PAIR, rising_bars(20))
    clock.advance(INTERVAL * 20)
    seen = small.recent_trades()
    assert seen
    floor = clock.now() - timedelta(seconds=3 * INTERVAL)
    assert min(trade.ts for trade in seen) > floor


def test_recent_trades_does_not_consume_and_drain_trades_does(
    market: ScriptedMarket,
) -> None:
    """The two halves of `MarketStreamProtocol` that are easy to get the wrong way round.

    Engine 3 rebuilds the same open bar on each of the fifteen ticks it spans, so its
    read must not consume; a consumer that genuinely processes each trade once needs one
    that does. A harness with both the same way silently breaks whichever engine it is
    not shaped for.
    """
    market.plant(PAIR, rising_bars(4))
    market.clock.advance(INTERVAL * 4)
    first = market.recent_trades()
    assert market.recent_trades() == first
    drained = market.drain_trades()
    assert drained
    assert market.drain_trades() == ()


# --------------------------------------------------------------------------- #
# Quotes and gaps
# --------------------------------------------------------------------------- #


def test_an_unknown_pair_has_no_quote_rather_than_a_zero_one(
    market: ScriptedMarket,
) -> None:
    """Absent is not zero, and engine 4 has to be able to tell them apart.

    A zeroed quote would read as a pair with a zero spread, which is a tradable market;
    the truth is a pair the stream has never seen, which is a block.
    """
    assert market.latest_quote("ZZZ/USD") is None


def test_a_pair_with_no_trades_yet_has_no_quote(market: ScriptedMarket) -> None:
    """Planted but not reached is still nothing seen.

    The clock has not moved, so no trade has happened, so there is no top of book — and
    the quote must not be derived from a bar the stream has not reached.
    """
    market.plant(PAIR, rising_bars(3))
    assert market.latest_quote(PAIR) is None


def test_the_quote_follows_the_last_trade_until_it_is_pinned(
    market: ScriptedMarket,
) -> None:
    """A moving mark is what spec 101's criterion turns on.

    Unpinned, the book straddles the last trade, so a second tick's trade moves the
    rendered figure. Pinned, it stays — which is how a criterion produces the crossed or
    stale book engine 4 blocks on without having to fabricate a trade that never
    happened.
    """
    market.plant(PAIR, rising_bars(4))
    market.clock.advance(INTERVAL * 2)
    first = market.latest_quote(PAIR)
    assert first is not None and first.bid < first.ask
    market.clock.advance(INTERVAL * 2)
    second = market.latest_quote(PAIR)
    assert second is not None
    assert second.bid > first.bid, "the mark did not move with the market"

    market.set_quote(PAIR, bid="1.00", ask="0.90")
    crossed = market.latest_quote(PAIR)
    assert crossed is not None
    assert crossed.bid > crossed.ask, "a pinned book must stay crossed for engine 4"


def test_gaps_are_drained_once_and_recorded_not_healed(market: ScriptedMarket) -> None:
    """Invariant 11, in the harness.

    A gap is marked and never closed, and it is drained rather than read so engine 2
    stays stateless across cycles. The `PaperBroker` dropping this very method is the
    Phase 6 finding that made it worth a test here: nobody writes a test for the method
    they forgot.
    """
    market.record_gap({"start": ORIGIN, "end": ORIGIN + 30, "cause": "reconnect"})
    assert len(market.gaps) == 1
    assert len(market.drain_gaps()) == 1
    assert market.drain_gaps() == ()


def test_the_raw_frame_drain_is_empty_and_says_so(market: ScriptedMarket) -> None:
    """Deliberately empty, and the docstring is the reason it is not a defect.

    Engine 2 writes what `drain()` returns into the archive. Fabricating raw frames
    would put invented JSONL in front of the one engine whose job is to record what
    actually arrived, and no Phase 6 criterion judges the archive.
    """
    market.plant(PAIR, rising_bars(4))
    market.clock.advance(INTERVAL * 4)
    assert market.drain() == ()


# --------------------------------------------------------------------------- #
# Against the engine that reads it
# --------------------------------------------------------------------------- #


def test_engine_3_builds_closed_candles_and_never_the_open_one(
    market: ScriptedMarket,
) -> None:
    """The harness checked against its real consumer rather than against itself.

    Engine 3 publishes only bars that have closed — publishing the bar containing `now`
    would put a partial high, low and close in front of the feature engine, which is
    look-ahead by another name and invariant 10 forbids it. This asserts the harness
    feeds it in a shape where that distinction still holds.
    """
    sensor_module = require_module(
        "acsoe.engines.market_sensor.engine", reason="engine 3 does not exist yet"
    )
    contracts = require_module("acsoe.core.contracts", reason="core/contracts.py is absent")
    market.plant(PAIR, rising_bars(8))
    market.clock.advance(INTERVAL * 5 + TICK)

    config = load_default_config()
    context = contracts.EngineContext(
        mode="paper",
        run_id="market-script",
        now=market.clock.now(),
        config=config,
        clients=_Clients(market),
        previous_now=market.clock.now() - timedelta(seconds=TICK),
    )
    result = sensor_module.MarketSensorEngine().process(context, {})
    published = result.data["candles"]
    assert published, result.data
    open_bar = (int(context.now.timestamp()) // INTERVAL) * INTERVAL
    assert max(int(candle["ts"]) for candle in published) < open_bar


def test_engine_3_sees_a_trade_planted_between_two_ticks(market: ScriptedMarket) -> None:
    """Why `plant_trade` exists, and why `previous_now` does.

    A stop touched between one loop tick and the next has to be visible, or engines 21
    and 22 miss it. The range engine 3 publishes is bounded by `context.previous_now`
    rather than by `now - loop_tick_s`, so a loop that ran late still covers the
    overshoot — and a harness that could only plant trades on tick boundaries could
    never show that.
    """
    sensor_module = require_module(
        "acsoe.engines.market_sensor.engine", reason="engine 3 does not exist yet"
    )
    contracts = require_module("acsoe.core.contracts", reason="core/contracts.py is absent")
    market.plant(PAIR, rising_bars(6))
    market.clock.advance(INTERVAL * 4)
    previous = market.clock.now()
    spike = previous + timedelta(seconds=17)
    market.plant_trade(PAIR, at=spike, price="999.00")
    market.clock.advance(TICK)

    context = contracts.EngineContext(
        mode="paper",
        run_id="market-script",
        now=market.clock.now(),
        config=load_default_config(),
        clients=_Clients(market),
        previous_now=previous,
    )
    result = sensor_module.MarketSensorEngine().process(context, {})
    ranges = result.data["trade_ranges"]
    assert PAIR in ranges, ranges
    assert Decimal(str(ranges[PAIR]["high"])) == Decimal("999.00")


class _Clients:
    """The three injected clients, with one object serving `kraken` — as the daemon does."""

    def __init__(self, kraken: ScriptedMarket) -> None:
        self.kraken = kraken
        self.store = None
        self.recorder = None


def test_every_method_the_real_stream_declares_is_here() -> None:
    """The double checked against the Protocol, walked rather than listed.

    **Nobody writes a test for the method they forgot.** That is not a maxim here, it is
    this phase's own finding: `PaperBroker` forwarded six of `MarketStreamProtocol`'s
    seven methods and dropped `drain_gaps`, so engine 2 would have recorded no `gap`
    line and a recording made through the daemon would have claimed to be continuous
    while spanning reconnects — invariant 11, and it disarms the book cutter's gap
    refusal. It was found by measurement, not by a test, because the test that would
    have caught it would have had to be written by the person who forgot.

    So this walks `__protocol_attrs__` instead of naming the seven. A method added to
    the Protocol tomorrow turns this red rather than leaving a hole.
    """
    contracts = require_module(
        "acsoe.clients.kraken.contracts", reason="A's contracts do not exist yet"
    )
    protocol = contracts.MarketStreamProtocol
    declared = getattr(protocol, "__protocol_attrs__", None)
    assert declared, "the Protocol declares nothing, so this check would pass vacuously"
    missing = [name for name in sorted(declared) if not hasattr(ScriptedMarket, name)]
    assert not missing, (
        f"ScriptedMarket is missing {missing} from MarketStreamProtocol. A double that "
        "answers most of an interface is a double that hides whichever engine reads the "
        "rest."
    )


def test_every_name_the_paper_broker_forwards_is_here_too() -> None:
    """The surface that actually matters in paper mode, derived rather than listed.

    The Protocol walk above is necessary and it is **not sufficient**, and finding that
    out cost a chain run. `ScriptedMarket` answered all seven names in
    `MarketStreamProtocol.__protocol_attrs__` and the guard chain still died on
    `'ScriptedMarket' object has no attribute 'set_subscription'`.

    Two things a Protocol cannot see. Engine 2 reaches the stream's *lifecycle* by
    `getattr` — `set_subscription`, and `subscription` read back afterwards — and
    `PaperBroker` forwards ten names to the client it wraps, four of which the Protocol
    does not declare. Engine 2's `getattr` degrades politely when a name is absent;
    the broker's forwarder does not, and must not, because a forwarder that swallowed a
    missing method is the `drain_gaps` defect over again. **In paper mode the broker is
    the stream every engine sees**, so its forwarded surface is the real contract.

    Derived from B's file by AST rather than listed here, so a name B adds tomorrow is
    covered without anybody remembering to come back — the same property the reason-code
    walk has, arrived at from the other direction.
    """
    import ast

    broker = Path(acsoe.clients.paper.__file__).with_name("broker.py")
    if not broker.is_file():  # pragma: no cover - B's spec 88 is landed
        pytest.skip("the paper broker does not exist yet (B, spec 88)")
    tree = ast.parse(broker.read_text(encoding="utf-8"))
    forwarded = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "_real"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
    }
    assert forwarded, "no forwarded names were found, so this check would pass vacuously"
    missing = sorted(name for name in forwarded if not hasattr(ScriptedMarket, name))
    assert not missing, (
        f"PaperBroker forwards {missing} to the client it wraps and ScriptedMarket does "
        "not answer them. In paper mode the broker is the stream every engine sees, so "
        "this raises inside the guard chain rather than degrading."
    )
