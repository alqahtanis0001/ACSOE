"""Engine 11 `risk` — specs 35 and 41.

The test that carries spec 35 is `test_a_sub_ordermin_position_is_rejected_not_resized`.
Spec 35 is explicit about why: "a test that only checked 'did not place' would pass
against a rounding implementation". So the assertion is on the **absence of a resized
quantity** — no field in the payload holds one, and no field equals `ordermin` — rather
than on the block alone.

**No fixture here builds `state["exchange"]` or `state["market_sensor"]`.** Spec 35's
version of this file built both by hand, and the hand-built `state["exchange"]` carried a
`last_price` field that **no engine in this system has ever published**. That is the
sharpest form of the failure the Phase 3 audit found: a mock that agrees with its caller
cannot notice a missing publisher, because supplying the input is what the mock is for.

So every `state` below is assembled from `ExchangeEngine().process(...).data` and
`MarketSensorEngine().process(...).data` — A's real engines 1 and 3, run against C's fake
Kraken client. A test that needs a specific `ordermin`, fee, balance or price varies the
*fake exchange's* fixture through `set_pair_rule`, `set_balances` or `set_order_book` and
lets the real engines publish the result. `ordermin` has the same property the fee tier has
in engine 10: a constant that happened to match would satisfy every behavioural test here,
so one test moves it in the fixture and another reads the engine's own source.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.harness.fake_kraken import FakeKrakenClient

from acsoe.clients.kraken.contracts import QuoteTick, TradeTick
from acsoe.clients.paper.broker import PaperBroker
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import (
    CashSource,
    EquitySnapshotRow,
    OrderIntent,
    OrderRow,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionRow,
    PositionStatus,
    to_micros,
)
from acsoe.core.contracts import EngineStatus
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.risk.contracts import (
    REASON_BELOW_COSTMIN,
    REASON_BELOW_ORDERMIN,
    REASON_ENTRY_RESTING_ON_PAIR,
    REASON_INPUTS_UNAVAILABLE,
    REASON_INSUFFICIENT_QUOTE_BALANCE,
    REASON_MAX_CONCURRENT_POSITIONS,
    REASON_NO_FX_RATE,
    REASON_POSITION_OPEN_ON_PAIR,
    round_down_to_lot,
)
from acsoe.engines.risk.engine import RiskEngine

PAIR = "SOL/USD"

#: The committed config's own worked example, quoted in `config/default.yaml` on
#: `max_concurrent_positions`: "the balance binds first at $5,000: one position is ~$3,333
#: notional". $5,000 x 1% / 1.5% = $3,333.33. Every sizing test here is anchored to it, so
#: a change to the sizing rule fails against the operator's stated intent rather than
#: against a number this file invented.
EQUITY = "5000.00"
EXPECTED_NOTIONAL = Decimal("3333.33")

#: The default book this file gives the fake exchange: a one-cent spread on a $100 pair.
#: It is a *fixture of the fake*, set through `set_order_book` and republished by engine 3,
#: which is the only route this file is allowed to introduce a price by. The ask is a round
#: 100.00 so the sizing lands on the config's own worked example rather than on a number
#: chosen to be tidy.
DEFAULT_BID = "99.99"
DEFAULT_ASK = "100.00"

#: A book wide enough that the ask and the bid give visibly different answers. Used by the
#: tests that prove which side is used where; a mid-price implementation gives 29.62962962
#: units here instead of 26.66666666 and fails on the exact `Decimal`.
WIDE_BID = "100.00"
WIDE_ASK = "125.00"


# --------------------------------------------------------------------------- #
# The client: C's fake, plus the stream half engine 3 reads
# --------------------------------------------------------------------------- #


class FakeKrakenWithStream(FakeKrakenClient):
    """C's fake Kraken client with the two stream methods engine 3 `market_sensor` reads.

    One object serves both engines, which is how the daemon runs: `context.clients.kraken`
    is a single client and engines 1 and 3 both reach the exchange through it.

    **The quotes are not invented here.** They are read out of the same committed
    `order_book.json` the fake already serves, through the fake's own `order_book` call, so
    the bid and ask this gate sizes against are the fake exchange's book and vary with it.
    A test that wants a particular spread calls `set_order_book`, exactly as a test that
    wants a particular fee calls `set_fee_tier`.
    """

    def __init__(self, *, now: int = 0) -> None:
        super().__init__(now=now)
        self._stream_quotes: dict[str, QuoteTick] = {}
        self._stream_trades: tuple[TradeTick, ...] = ()

    def stream_pairs(self, pairs: Sequence[str], *, at: datetime) -> None:
        """Make the stream report a trade and a top-of-book quote for each pair.

        Engine 3 derives its quote set from the pairs it saw trade in the window, so a
        pair with no trade gets no quote — which is the behaviour a "pair with no quote"
        test needs, and the reason this is a call rather than a constructor argument.
        """
        from acsoe.platform.aio import run_blocking

        trades: list[TradeTick] = []
        quotes: dict[str, QuoteTick] = {}
        for pair in pairs:
            book = run_blocking(self.order_book(pair, 10))
            quotes[pair] = QuoteTick(
                pair=pair, ts=at, bid=book.best_bid, ask=book.best_ask
            )
            trades.append(
                TradeTick(pair=pair, ts=at, price=book.best_bid, qty=Decimal("1"))
            )
        self._stream_quotes = quotes
        self._stream_trades = tuple(trades)

    def recent_trades(self) -> tuple[TradeTick, ...]:
        return self._stream_trades

    def latest_quote(self, pair: str) -> QuoteTick | None:
        return self._stream_quotes.get(pair)


def build_state(context: Any, *, pair: str = PAIR) -> dict[str, Any]:
    """A `state` as the opportunity chain would have it by the time gate 11 runs.

    `state["exchange"]` and `state["market_sensor"]` are A's real engines' `data`,
    verbatim. Nothing here writes a pair rule, a balance or a price into a dict this gate
    then reads back — that is the whole point of spec 41, and
    `test_no_fixture_in_this_file_hand_builds_a_publisher_payload` holds it.
    """
    return {
        "system": {"mode": "running", "close_intent": False},
        "cycle_id": 1,
        "guard_blockers": [],
        "scout": {"pair": pair},
        "exchange": ExchangeEngine().process(context, {}).data,
        "market_sensor": MarketSensorEngine().process(context, {}).data,
    }


def open_position(
    position_id: str, pair: str, *, status: PositionStatus = PositionStatus.OPEN
) -> PositionRow:
    """One position. Only `status` and `pair` matter to the two gates that read it.

    `status` is a keyword with the open default the portfolio-cap tests already rely on,
    so spec 89's closed-position case varies exactly one argument against its open twin.
    """
    base, _, quote = pair.partition("/")
    return PositionRow(
        position_id=position_id,
        run_id="test-run",
        cycle_id=1,
        pair=pair,
        base=base,
        quote=quote,
        status=status,
        qty=Decimal("1.00000000"),
        entry_price=Decimal("100.00"),
        target_price=Decimal("103.00"),
        stop_price=Decimal("98.50"),
        timeout_at=9_999,
        opened_at=1_000,
        closed_at=2_000 if status is PositionStatus.CLOSED else None,
        updated_at=1_000,
    )


def entry_order(
    userref: int,
    pair: str,
    *,
    status: OrderStatus = OrderStatus.RESTING,
    intent: OrderIntent = OrderIntent.ENTRY,
) -> OrderRow:
    """One order on `pair`, resting and an entry unless a test says otherwise.

    Invariant 8: entry is always a post-only limit, so `oflags` says `post` and the type
    is a limit. Neither field is read by engine 11 — the row shape is kept honest anyway,
    because a fixture that could not exist on the real exchange proves nothing about a
    gate that will meet the real one.
    """
    side = OrderSide.BUY if intent is OrderIntent.ENTRY else OrderSide.SELL
    return OrderRow(
        userref=userref,
        run_id="test-run",
        cycle_id=1,
        pair=pair,
        side=side,
        intent=intent,
        order_type=OrderType.LIMIT,
        oflags="post" if intent is OrderIntent.ENTRY else "",
        status=status,
        qty=Decimal("1.00000000"),
        limit_price=Decimal("99.00"),
        filled_qty=Decimal("0.00000000"),
        placed_at=1_000,
        updated_at=1_000,
    )


@pytest.fixture
def risk() -> RiskEngine:
    return RiskEngine()


@pytest.fixture
def kraken(engine_context: Any) -> FakeKrakenWithStream:
    """The fake exchange both real engines run against, attached to the context.

    The default book is set here rather than left to the committed fixture so the sizing
    lands on the config's own worked example. It still travels the whole way through
    `set_order_book` and engine 3; nothing shortcuts the publisher.
    """
    client = FakeKrakenWithStream()
    client.set_balances({"USD": EQUITY})
    client.set_order_book(
        PAIR, bids=[(DEFAULT_BID, "500")], asks=[(DEFAULT_ASK, "500")]
    )
    engine_context.clients.kraken = client
    client.stream_pairs([PAIR], at=engine_context.now - timedelta(seconds=60))
    return client


@pytest.fixture
def sized_context(engine_context: Any, store: StoreClient, kraken: Any) -> Any:
    """An `EngineContext` whose store carries the equity snapshot sizing reads.

    Invariant 6 sizes against *total account equity*, which only engine 19 `memory`
    computes, and engine 19 is Phase 4. This is the same forward dependency engine 17
    has and it is resolved the same way: a real `StoreClient` against a migrated
    temporary database, with the row written here rather than by a live engine.
    """
    store.write_equity_snapshot(
        EquitySnapshotRow(
            cycle_id=1,
            run_id="test-run",
            ts=1_000,
            currency="USD",
            equity=Decimal(EQUITY),
            peak_equity=Decimal(EQUITY),
            cash=Decimal(EQUITY),
            positions_value=Decimal("0.00"),
            unrealised_pnl=Decimal("0.00"),
            realised_pnl_cum=Decimal("0.00"),
            open_position_count=0,
            cash_source=CashSource.CYCLE_START,
            updated_at=1_000,
        )
    )
    engine_context.clients.store = store
    return engine_context


def widen_the_book(kraken: FakeKrakenWithStream, context: Any, *, pair: str = PAIR) -> None:
    """Give `pair` a book where the ask and the bid give different answers."""
    kraken.set_order_book(pair, bids=[(WIDE_BID, "500")], asks=[(WIDE_ASK, "500")])
    kraken.stream_pairs([pair], at=context.now - timedelta(seconds=60))


# --------------------------------------------------------------------------- #
# Registry shape
# --------------------------------------------------------------------------- #


def test_the_engine_declares_itself_as_the_registry_has_it(risk: RiskEngine) -> None:
    assert (risk.name, risk.number, risk.is_gate) == ("risk", 11, True)


# --------------------------------------------------------------------------- #
# The seam: engines 1 and 3's own output, no double on either side
# --------------------------------------------------------------------------- #


def test_the_real_publishers_drive_this_gate_to_a_real_sizing(
    risk: RiskEngine, sized_context: Any
) -> None:
    """The check spec 41 exists for.

    A's real engines 1 and 3 run against C's fake client, their `data` becomes `state`,
    and this gate sizes a position from it. Before spec 41 this path could not reach a
    sizing at all: the pair rules were one level shallower than engine 1 publishes them,
    and the price was read from a field nothing has ever written.

    So the assertion that carries the spec is the negative one — not a missing-input
    block — with the pair rules and the price pinned to what the publishers actually said.
    """
    state = build_state(sized_context)
    published_rules = state["exchange"]["pair_rules"]["pairs"][PAIR]
    published_quote = state["market_sensor"]["quotes"][PAIR]

    result = risk.process(sized_context, state)

    assert result.data["reason_code"] != REASON_INPUTS_UNAVAILABLE
    assert result.data["approved"] is True
    assert Decimal(result.data["ordermin"]) == Decimal(published_rules["ordermin"])
    assert Decimal(published_quote["ask"]) == Decimal(DEFAULT_ASK)


def test_no_fixture_in_this_file_hand_builds_a_publisher_payload() -> None:
    """Operator ruling 2026-09-10: the fixtures are rewritten, not repointed.

    Renaming a key inside a hand-built dict would make this file green again and leave the
    seam as untested as it was, so the ruling is checked mechanically: the publishers' own
    payload keys may not appear here as dict-key literals — a quoted name followed by a
    colon. Reading one back out of a published dict is subscript syntax and is untouched.

    `last_price` is on the list even though nothing publishes it, and that is the point: it
    is the field the old fixture conjured, and the guard should fail if it comes back.

    The pattern is assembled from a bare name at runtime so this test does not trip on its
    own source, which the equivalent guard in `test_cost.py` did on its first run.
    """
    forbidden = ("pair_rules", "balances", "fee_tier", "quotes", "last_price")
    source = Path(__file__).read_text(encoding="utf-8")
    for name in forbidden:
        literal = '"' + name + '":'
        assert literal not in source, f"{name} is a publisher's to write, not this file's"


# --------------------------------------------------------------------------- #
# The gate: a pass test and the block test the spec names
# --------------------------------------------------------------------------- #


def test_a_position_at_or_above_ordermin_passes(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """The pass half. $3,333.33 notional at a $100 ask is 33.33333333 units at
    `lot_decimals` 8, well above a 0.1 minimum."""
    kraken.set_pair_rule(PAIR, ordermin="0.1")

    result = risk.process(sized_context, build_state(sized_context))

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["approved"] is True
    assert Decimal(result.data["qty"]) == Decimal("33.33333333")


def test_the_sizing_is_the_configured_fraction_of_equity_at_the_configured_stop(
    risk: RiskEngine, sized_context: Any
) -> None:
    """Anchored to the worked example in `config/default.yaml` itself.

    risk_amount = 5000.00 x 0.01        = 50.00
    notional    = 50.00 / 0.015         = 3333.33...
    qty         = 3333.33... / 100.00   = 33.3333...

    Reading `risk_fraction_per_trade` as a fraction of *notional* rather than of money at
    risk would size this at 0.5 units instead of 33.33 — 66 times smaller, an error that
    looks conservative and would quietly make the whole system untestable. The operator's
    own comment on `max_concurrent_positions` says $3,333, so this is asserted against
    stated intent rather than against a number invented here.
    """
    data = risk.process(sized_context, build_state(sized_context)).data

    assert Decimal(data["risk_amount"]) == Decimal("50.0000")
    assert Decimal(data["notional"]).quantize(Decimal("0.01")) == EXPECTED_NOTIONAL


def test_a_sub_ordermin_position_is_rejected_not_resized(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """The test spec 35 names, asserted the way spec 35 requires.

    A test that only checked "did not place" would pass against a rounding
    implementation, because a rounding implementation also does not place *this* size —
    it places `ordermin` instead. So the assertion is on the **absence of a resized
    quantity**: no `qty` field at all, and no field anywhere in the payload carrying the
    minimum. Rounding up silently increases the money at risk beyond what the sizing
    decided, which is the opposite of what a risk gate is for.
    """
    # A minimum far above the 33.33 units the sizing produces.
    kraken.set_pair_rule(PAIR, ordermin="500")

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["approved"] is False
    assert result.data["reason_code"] == REASON_BELOW_ORDERMIN

    # The absence, asserted on the whole key set rather than on values.
    #
    # An earlier version of this checked that no *value* in the payload equalled
    # `ordermin`, which was wrong twice over: `ordermin` is legitimately published so the
    # console and the `rejections` row can say what the minimum was, so the check fired
    # on a correct payload — and value-sniffing would not have caught a bump to
    # `ordermin + 1` anyway. Pinning the key set is both stricter and honest: there is no
    # `qty`, no `notional`, no `value_at_bid` and no `risk_amount` field for anything to
    # be bumped *into*.
    assert set(result.data) == {
        "pair",
        "approved",
        "ordermin",
        "costmin",
        "reason_code",
    }, "a refused candidate must publish no quantity field at all, in any form"
    assert Decimal(result.data["ordermin"]) == Decimal("500")


def test_a_position_one_increment_below_the_minimum_is_still_rejected(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """The boundary, which is where a rounding implementation is most tempting.

    At `lot_decimals` 8 the sizing gives 33.33333333. A minimum one increment above that
    is 33.33333334, and the answer must still be no — one satoshi-equivalent short is
    short.
    """
    kraken.set_pair_rule(PAIR, ordermin="33.33333334")
    just_above = risk.process(sized_context, build_state(sized_context))

    kraken.set_pair_rule(PAIR, ordermin="33.33333333")
    exactly_at = risk.process(sized_context, build_state(sized_context))

    assert just_above.blocks_trading is True
    assert just_above.data["reason_code"] == REASON_BELOW_ORDERMIN
    assert exactly_at.blocks_trading is False, "at the minimum is allowed; below it is not"


# --------------------------------------------------------------------------- #
# Which side of the book — the lead ruling of 2026-09-10
# --------------------------------------------------------------------------- #


def test_the_quantity_is_sized_from_the_ask_and_the_value_taken_at_the_bid(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """The ruling, on a book wide enough that the two answers differ.

    Bid 100.00, ask 125.00, $3,333.33 notional:

    - at the ask:  3333.33... / 125.00 = 26.66666666 after rounding down
    - at the bid:  3333.33... / 100.00 = 33.33333333
    - at the mid:  3333.33... / 112.50 = 29.62962962

    All three are exact `Decimal`s and all three differ, so this asserts the ruling rather
    than merely being consistent with it. The entry is a buy: the ask is the worst price
    it could pay, and a higher assumed price yields *fewer* units, so the position is
    never larger than the sizing chose.

    `value_at_bid` is the other half. It is what the position is immediately worth, and it
    is the figure `costmin` is tested against — the lowest the position could be valued at,
    so a marginal one is refused rather than admitted.
    """
    widen_the_book(kraken, sized_context)
    kraken.set_pair_rule(PAIR, ordermin="0.1", costmin="5.00")

    data = risk.process(sized_context, build_state(sized_context)).data

    assert Decimal(data["qty"]) == Decimal("26.66666666")
    assert Decimal(data["notional"]) == Decimal("3333.3333325000")
    assert Decimal(data["value_at_bid"]) == Decimal("2666.6666660000")


def test_costmin_is_tested_against_the_bid_not_the_ask(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """The discriminating case, and the reason the ruling has two halves rather than one.

    On the wide book the position is worth 3333.33 at the ask and 2666.67 at the bid. A
    `costmin` of 3000.00 sits between them: valued at the ask this candidate is admitted,
    valued at the bid it is refused. An implementation that used one price for both
    questions passes every other test in this file and fails this one.
    """
    widen_the_book(kraken, sized_context)
    kraken.set_pair_rule(PAIR, ordermin="0.1", costmin="3000.00")

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_BELOW_COSTMIN
    assert "2666.6666660000" in (result.reason or "")
    assert "qty" not in result.data


# --------------------------------------------------------------------------- #
# The minimum is fetched, never remembered
# --------------------------------------------------------------------------- #


def test_changing_ordermin_changes_which_sizes_are_rejected(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """Proves the value is fetched. A constant would pass every single-value test above
    and fail this one — and it now proves it the whole way through engine 1, so what it
    rules out is a constant anywhere on the path rather than only one inside engine 11."""
    kraken.set_pair_rule(PAIR, ordermin="0.1")
    generous = risk.process(sized_context, build_state(sized_context))

    kraken.set_pair_rule(PAIR, ordermin="500")
    strict = risk.process(sized_context, build_state(sized_context))

    assert generous.blocks_trading is False
    assert strict.blocks_trading is True


def test_no_order_minimum_is_written_into_the_engine_source() -> None:
    """`AGENTS.md`: any remembered order minimum is stale. A constant that happened to
    match the fixture would satisfy every behavioural test in this file, so the source is
    read directly — the same guard engine 10 carries for the reference fees."""
    import acsoe.engines.risk as package

    source = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted(Path(package.__file__).parent.glob("*.py"))
    )
    for remembered in ("0.1", "500", "5.00", "ordermin =", "costmin ="):
        assert remembered not in source, f"{remembered!r} looks like a remembered pair rule"


# --------------------------------------------------------------------------- #
# Rounding
# --------------------------------------------------------------------------- #


def test_quantities_round_down_never_to_nearest() -> None:
    """Rounding to nearest would round a quantity one ulp below `ordermin` *up to* it —
    the rounding-up defect arriving through a rounding mode rather than an explicit bump.
    Invariant 14 fixes the same rule for a liquidation: dust is cheaper than a rejected
    order."""
    assert round_down_to_lot(Decimal("1.999999999"), 8) == Decimal("1.99999999")
    assert round_down_to_lot(Decimal("0.99999999999"), 2) == Decimal("0.99")
    assert round_down_to_lot(Decimal("5"), 0) == Decimal("5")


def test_rounding_happens_before_the_minimum_is_tested(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """The ordering that is easy to get backwards.

    At `lot_decimals` 0 the 33.3333 units round down to 33. A minimum of 33.5 must
    therefore reject: the number compared against `ordermin` has to be the number that
    would actually be sent, not the unrounded one that passed.
    """
    kraken.set_pair_rule(PAIR, lot_decimals=0, ordermin="33.5")

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_BELOW_ORDERMIN


# --------------------------------------------------------------------------- #
# The other three refusals
# --------------------------------------------------------------------------- #


def test_a_position_below_costmin_is_rejected(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """`costmin` is tested on the rounded quantity's real value, not on the notional the
    sizing asked for: rounding down can drop the value below the minimum even when the
    request cleared it."""
    kraken.set_pair_rule(PAIR, costmin="999999.00")

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_BELOW_COSTMIN
    assert "qty" not in result.data


def test_a_notional_larger_than_the_quote_balance_is_rejected(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 6: never allocate cash the account does not hold in that pair's quote
    currency. Rejected rather than capped to fit — a position quietly resized is no
    longer the position the sizing rule chose, which is the same objection as rounding
    up to a minimum."""
    kraken.set_balances({"USD": "100.00"})

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INSUFFICIENT_QUOTE_BALANCE
    assert "qty" not in result.data, "not capped to the balance — refused"


def test_the_balance_is_read_per_quote_currency(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 7: a pair is only executable if the account holds spendable balance in
    *that* quote currency. A EUR-quoted pair may not spend the USD pot.

    Note what this is **not**: a failed `Balance` fetch. The map was published and simply
    names no EUR, which is an account holding nothing rather than an outage, so the reason
    names the currency and not the absent map the tests below refuse on.
    """
    eur_pair = "SOL/EUR"
    kraken.set_pair_rule(
        eur_pair,
        base="SOL",
        quote="EUR",
        ordermin="0.05",
        costmin="5.00",
        tick_size="0.001",
        lot_decimals=8,
        pair_decimals=3,
    )
    kraken.set_order_book(eur_pair, bids=[(DEFAULT_BID, "500")], asks=[(DEFAULT_ASK, "500")])
    kraken.stream_pairs([PAIR, eur_pair], at=sized_context.now - timedelta(seconds=60))

    result = risk.process(sized_context, build_state(sized_context, pair=eur_pair))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "exchange.balances.EUR" in (result.reason or "")
    assert NO_BALANCE_PUBLISHED not in (result.reason or "")


def test_a_pair_quoted_in_another_currency_is_refused_for_want_of_a_rate(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """**Ruled by the operator on 2026-09-10**, and this engine has carried the defect since
    spec 35.

    `target_notional` derives from equity, which invariant 7 expresses in
    `trading.base_reporting_currency`; the balance it is compared against is in the pair's
    quote currency. Comparing them needs an FX rate and nothing publishes one, though
    invariant 7 says one is converted "at the trade timestamp".

    No test ever reached it, because no fixture had a pair whose quote is not the reporting
    currency *and* a balance in it — the balance check refused those first, for a different
    reason. It surfaced while engine 7 `scout` was being written, as the third caller of the
    same arithmetic, rather than by anything failing.

    The account holds EUR here, so the pair clears every earlier rule and this is the only
    thing refusing it. Refusing claims nothing about the world; inventing a rate or assuming
    parity would.
    """
    eur_pair = "SOL/EUR"
    kraken.set_pair_rule(
        eur_pair,
        base="SOL",
        quote="EUR",
        ordermin="0.05",
        costmin="5.00",
        tick_size="0.001",
        lot_decimals=8,
        pair_decimals=3,
    )
    kraken.set_order_book(eur_pair, bids=[(DEFAULT_BID, "500")], asks=[(DEFAULT_ASK, "500")])
    kraken.set_balances({"USD": "5000.00", "EUR": "5000.00"})
    kraken.stream_pairs([PAIR, eur_pair], at=sized_context.now - timedelta(seconds=60))

    result = risk.process(sized_context, build_state(sized_context, pair=eur_pair))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_NO_FX_RATE
    assert "qty" not in result.data, "nothing is sized against a balance it cannot compare"
    assert "EUR" in (result.reason or "")
    assert "USD" in (result.reason or ""), "the sentence names both currencies"


def test_a_reporting_currency_pair_is_unaffected_by_the_rate_rule(
    risk: RiskEngine, sized_context: Any
) -> None:
    """The other half, so the refusal above is proved to be about the currency mismatch and
    not about having quietly stopped approving anything."""
    result = risk.process(sized_context, build_state(sized_context))

    assert result.data["approved"] is True
    assert result.data["reason_code"] is None


def test_the_portfolio_cap_is_counted_from_the_store_not_from_state(
    risk: RiskEngine, sized_context: Any, store: StoreClient
) -> None:
    """This gate runs in the opportunity chain and the manage chain runs after it, so
    `state["position_manager"]` does not exist yet — the same structural reason engine 17
    reads the store. `max_concurrent_positions` is 3 in the committed config.

    None of the three positions is on the candidate's pair, which is what keeps the cap
    reachable now that the per-pair rule is asked first: this is the shape the cap still
    refuses on its own, and the paired test below is the shape where it no longer does.
    """
    for index, pair in enumerate(("BTC/USD", "ETH/USD", "XRP/USD")):
        store.write_position(open_position(f"p-{index}", pair))

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_MAX_CONCURRENT_POSITIONS
    assert "qty" not in result.data, "the cap is checked before sizing, so nothing is sized"


# --------------------------------------------------------------------------- #
# One position per pair — invariant 6's last clause, spec 89
#
# Enforced nowhere in `src/` before this spec: the portfolio cap above counts open
# positions and never asks which pair they are on, and engine 7 does not look. It was
# unreachable only because nothing could open a position, and Phase 6 changes that.
#
# Every pair of cases below differs in exactly **one argument** to the fixture helper —
# the stored pair, the stored status, or the stored intent — so a block that is really
# "this gate refuses everything once a row exists" cannot pass as enforcement.
# --------------------------------------------------------------------------- #

OTHER_PAIR = "BTC/USD"


@pytest.mark.parametrize(
    ("stored_pair", "expected_code"),
    [(PAIR, REASON_POSITION_OPEN_ON_PAIR), (OTHER_PAIR, None)],
    ids=["same pair refuses", "another pair does not"],
)
def test_an_open_position_refuses_a_second_one_on_that_pair_and_only_that_pair(
    risk: RiskEngine,
    sized_context: Any,
    store: StoreClient,
    stored_pair: str,
    expected_code: str | None,
) -> None:
    """Invariant 6: "One open position per pair."

    The candidate is `SOL/USD` in both cases and the only thing that moves is which pair
    the already-open position is on. `max_concurrent_positions` is 3, so one position
    never reaches the cap — the refusal below can only be the per-pair one.
    """
    store.write_position(open_position("p-1", stored_pair))

    result = risk.process(sized_context, build_state(sized_context))

    assert result.data["reason_code"] == expected_code
    assert result.blocks_trading is (expected_code is not None)
    assert result.data["approved"] is (expected_code is None)


@pytest.mark.parametrize(
    ("stored_status", "expected_code"),
    [
        (PositionStatus.OPEN, REASON_POSITION_OPEN_ON_PAIR),
        (PositionStatus.CLOSED, None),
    ],
    ids=["open refuses", "closed does not"],
)
def test_a_closed_position_on_the_pair_does_not_refuse_the_next_candidate(
    risk: RiskEngine,
    sized_context: Any,
    store: StoreClient,
    stored_status: PositionStatus,
    expected_code: str | None,
) -> None:
    """The pair is the same row, on the same pair, with one field changed.

    Without this the check would be satisfied by "this pair has ever been traded", which
    would take the system out of every pair it had exited once and would look, from the
    rejection rows alone, exactly like the rule working.
    """
    store.write_position(open_position("p-1", PAIR, status=stored_status))

    result = risk.process(sized_context, build_state(sized_context))

    assert result.data["reason_code"] == expected_code
    assert result.data["approved"] is (expected_code is None)


@pytest.mark.parametrize(
    ("stored_pair", "expected_code"),
    [(PAIR, REASON_ENTRY_RESTING_ON_PAIR), (OTHER_PAIR, None)],
    ids=["same pair refuses", "another pair does not"],
)
def test_a_resting_entry_refuses_a_second_candidate_on_that_pair_and_only_that_pair(
    risk: RiskEngine,
    sized_context: Any,
    store: StoreClient,
    stored_pair: str,
    expected_code: str | None,
) -> None:
    """A resting post-only buy is a position that has not filled yet.

    The same reading invariant 14 already applies to `safety`'s escalation precondition —
    "a resting post-only buy is exposure that has not happened yet". Counting only *open*
    positions here would let the system place a second entry beside an unfilled one and
    double the money at risk the moment both fill, with no gate left to refuse it.
    """
    store.write_order(entry_order(4_242, stored_pair))

    result = risk.process(sized_context, build_state(sized_context))

    assert result.data["reason_code"] == expected_code
    assert result.blocks_trading is (expected_code is not None)
    assert result.data["approved"] is (expected_code is None)


@pytest.mark.parametrize(
    ("stored_status", "stored_intent", "expected_code"),
    [
        (OrderStatus.RESTING, OrderIntent.ENTRY, REASON_ENTRY_RESTING_ON_PAIR),
        (OrderStatus.FILLED, OrderIntent.ENTRY, None),
        (OrderStatus.CANCELLED, OrderIntent.ENTRY, None),
        (OrderStatus.RESTING, OrderIntent.EXIT, None),
    ],
    ids=["resting entry", "filled entry", "cancelled entry", "resting exit"],
)
def test_only_an_entry_still_resting_on_the_book_refuses_the_candidate(
    risk: RiskEngine,
    sized_context: Any,
    store: StoreClient,
    stored_status: OrderStatus,
    stored_intent: OrderIntent,
    expected_code: str | None,
) -> None:
    """Each row below differs from the first in exactly one field.

    A **filled** entry is not exposure of its own: whatever it bought is a position row,
    and that row is what the position check above reads — counting the order too would
    refuse on the same exposure twice. A **cancelled** entry is off the book. A resting
    **exit** is the system getting out of something and must never stop it getting in; it
    is also the one row engine 22 will be writing constantly, so a check reading `orders`
    without filtering `intent` would refuse every candidate on a pair being exited.
    """
    store.write_order(entry_order(4_242, PAIR, status=stored_status, intent=stored_intent))

    result = risk.process(sized_context, build_state(sized_context))

    assert result.data["reason_code"] == expected_code
    assert result.data["approved"] is (expected_code is None)


def test_the_refusal_names_the_pair_and_the_position_it_already_holds(
    risk: RiskEngine, sized_context: Any, store: StoreClient
) -> None:
    """Spec 89 step 2: the sentence names the pair and the existing `position_id`.

    A reason code alone tells an operator a rule fired; the identifier tells them which
    row to look at, and this is a rejection they may have to act on rather than a metric.
    Nothing is sized, so no quantity reaches the payload of a refused candidate.
    """
    store.write_position(open_position("pos-7f3a", PAIR))

    result = risk.process(sized_context, build_state(sized_context))

    assert PAIR in (result.reason or "")
    assert "pos-7f3a" in (result.reason or "")
    assert "qty" not in result.data


def test_the_resting_entry_refusal_names_the_pair_and_the_userref(
    risk: RiskEngine, sized_context: Any, store: StoreClient
) -> None:
    """The same, for the order half: the `userref`, because that is the key invariant 8
    makes the idempotency lookup on and the only handle a cancellation has."""
    store.write_order(entry_order(918_273, PAIR))

    result = risk.process(sized_context, build_state(sized_context))

    assert PAIR in (result.reason or "")
    assert "918273" in (result.reason or "")
    assert "qty" not in result.data


def test_a_full_portfolio_that_also_holds_this_pair_reports_the_pair_rule(
    risk: RiskEngine, sized_context: Any, store: StoreClient
) -> None:
    """Both refusals are true at once; the order between them is fixed, not accidental.

    Either code is a correct refusal, so this pins *which* one the rejection row carries
    rather than claiming one rule outranks the other.

    The per-pair rule is first, by the lead's ruling of 2026-09-16 reversing the order
    spec 89 shipped with. The cap is inert at the configured balance — three allowed
    positions against a balance that affords one, which `config/default.yaml` states on
    the key itself — so cap-first would not have shadowed the specific clause on a rare
    tie: with one position open on the pair it would shadow it on every tick, which is
    precisely where invariant 6's per-pair clause is the rule doing the work.
    """
    for index, pair in enumerate((PAIR, "ETH/USD", "XRP/USD")):
        store.write_position(open_position(f"p-{index}", pair))

    result = risk.process(sized_context, build_state(sized_context))

    assert result.data["reason_code"] == REASON_POSITION_OPEN_ON_PAIR


def test_an_unreadable_orders_table_blocks_rather_than_reading_as_no_exposure(
    risk: RiskEngine, sized_context: Any, store: StoreClient
) -> None:
    """Invariant 3: absence of a "no" is never a "yes".

    `orders` is dropped on the real connection, so `positions` still reads and the
    portfolio cap and the open-position check both succeed — the *only* read that fails
    is the resting-entry one, which is the branch this test is about. Closing the whole
    store would have blocked three reads earlier, in
    `_count_open_positions`, and passed this assertion without ever reaching the code it
    claims to cover.

    No double: this is what `sqlite3` itself raises at a missing table.
    """
    store.connection.execute("DROP TABLE orders")

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "exposure" in (result.reason or ""), "the resting-entry read is the one that failed"
    assert PAIR in (result.reason or "")


# --------------------------------------------------------------------------- #
# No published balance blocks, in every mode — spec 106
#
# Invariant 2 has had no balance fallback since the operator's ruling of 2026-09-16.
# Until then this section tested a paper-mode substitution of `paper.starting_balances`
# on an account that had never traded — the one account on which the configured balance
# and the real one agree, so those tests could not have shown what the substitution did
# wrong. The first test below uses an account that has already traded, which is the
# witness that can.
# --------------------------------------------------------------------------- #

#: How the refusal names an absent map. A currency missing from a *published* map is also
#: `risk_inputs_unavailable`, so the reason is what tells the two facts apart —
#: `code-standards.md`: where one code has several causes, assert the cause.
NO_BALANCE_PUBLISHED = "missing exchange.balances: engine 1 published no balance this tick"

#: The first fill, on another pair: 0.06664 BTC at 50,000.00 is 3,332.00, plus a 3.6652
#: fee. Cash is then 5,000.00 - 3,335.6652 = 1,664.3348, and equity — what the sizing
#: reads — is that cash plus the position at cost, 4,996.3348. The lead's worked example
#: for spec 106, in exact figures.
FIRST_FILL_QTY = Decimal("0.06664")
FIRST_FILL_PRICE = Decimal("50000.00")
FIRST_FILL_FEE = Decimal("3.6652")
CASH_AFTER_FIRST_FILL = (
    Decimal(EQUITY) - FIRST_FILL_QTY * FIRST_FILL_PRICE - FIRST_FILL_FEE
)
EQUITY_AFTER_FIRST_FILL = CASH_AFTER_FIRST_FILL + FIRST_FILL_QTY * FIRST_FILL_PRICE

#: The second entry, resting on a third pair, with a trade printed through its limit so the
#: paper broker must price a fill before it can say what the account holds. Tier 3 maker.
DUE_PAIR = "ETH/USD"
DUE_QTY = Decimal("0.1")
DUE_LIMIT = Decimal("1980.00")
MAKER = "0.0022"
DUE_SPEND = DUE_QTY * DUE_LIMIT + DUE_QTY * DUE_LIMIT * Decimal(MAKER)

MICROS = 1_000_000


def _decimal(value: Any) -> Decimal:
    return Decimal(repr(value) if isinstance(value, float) else str(value))


def an_account_that_has_already_traded(
    context: Any, store: StoreClient, kraken: FakeKrakenWithStream, clock: Any
) -> None:
    """The store and the order client as the daemon would have them, one fill later.

    Engine 19's rows are written by hand, through the real row models, because engine 19
    does not run here: the first entry `filled`, the position it opened, and the equity row
    that counts it. The order client is the real `PaperBroker` wrapping the fake, so what
    engine 1 publishes as the balance is the paper ledger, computed from those rows — not
    a figure this file asserts into existence.

    A second entry rests on another pair with a trade printed through its limit, so the
    broker has a fill to price before it can answer. That is invariant 2's own example of
    the broker being unable to answer: when the fee tier does not return, engine 1
    publishes no balance.
    """
    now = to_micros(context.now)
    store.write_order(
        OrderRow.model_validate(
            {
                **entry_order(1_001, OTHER_PAIR).model_dump(),
                "order_id": "paper-1001",
                "status": OrderStatus.FILLED,
                "qty": FIRST_FILL_QTY,
                "limit_price": FIRST_FILL_PRICE,
                "filled_qty": FIRST_FILL_QTY,
                "avg_fill_price": FIRST_FILL_PRICE,
                "fee": FIRST_FILL_FEE,
                "placed_at": now - 20 * 60 * MICROS,
                "closed_at": now - 15 * 60 * MICROS,
            }
        )
    )
    store.write_position(
        PositionRow.model_validate(
            {
                **open_position("pos-btc", OTHER_PAIR).model_dump(),
                "qty": FIRST_FILL_QTY,
                "entry_price": FIRST_FILL_PRICE,
                "target_price": FIRST_FILL_PRICE * Decimal("1.03"),
                "stop_price": FIRST_FILL_PRICE * Decimal("0.985"),
                "entry_userref": 1_001,
            }
        )
    )
    store.write_equity_snapshot(
        EquitySnapshotRow(
            cycle_id=2,
            run_id="test-run",
            ts=now - 60 * MICROS,
            currency="USD",
            equity=EQUITY_AFTER_FIRST_FILL,
            peak_equity=Decimal(EQUITY),
            cash=CASH_AFTER_FIRST_FILL,
            positions_value=FIRST_FILL_QTY * FIRST_FILL_PRICE,
            unrealised_pnl=Decimal("0"),
            realised_pnl_cum=Decimal("0"),
            open_position_count=1,
            cash_source=CashSource.CYCLE_START,
            updated_at=now - 60 * MICROS,
        )
    )
    store.write_order(
        OrderRow.model_validate(
            {
                **entry_order(1_002, DUE_PAIR).model_dump(),
                "order_id": "paper-1002",
                "qty": DUE_QTY,
                "limit_price": DUE_LIMIT,
                "placed_at": now - 2 * 60 * MICROS,
            }
        )
    )
    kraken.set_fee_tier(tier=3, maker_fee_pct=MAKER, taker_fee_pct="0.0038")
    # The best bid sits a cent below the resting limit, so the stream's print at the bid
    # is strictly below it and after `placed_at`: the broker must fill it.
    kraken.set_order_book(DUE_PAIR, bids=[("1979.99", "5")], asks=[("1980.01", "5")])
    kraken.stream_pairs([PAIR, DUE_PAIR], at=context.now - timedelta(seconds=60))
    context.clients.kraken = PaperBroker(
        kraken, store=store, config=context.config, clock=clock
    )


@pytest.mark.parametrize(
    "ledger_answers",
    [False, True],
    ids=["the ledger cannot answer", "the ledger answers"],
)
def test_after_a_paper_fill_a_tick_with_no_published_balance_blocks(
    risk: RiskEngine,
    sized_context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
    fixed_clock: Any,
    ledger_answers: bool,
) -> None:
    """**The test that would have caught the fallback** — spec 106 step 3.

    A paper account that has already traded: ~3,335 of 5,000 spent, ~1,664 held, equity
    ~4,996. The candidate is sized from equity, ~3,331. The precondition below states the
    window the defect lived in: that notional is **more** than the account holds and
    **less** than `paper.starting_balances`. Against the fetched ledger the gate refuses
    it; against the configured map, which is what the removed fallback supplied when
    engine 1 published nothing, it approved it — invariant 6 broken by the gate that
    enforces it.

    One input differs between the two cases: whether the fee tier that prices the due
    fill returns. When it does, the ledger answers and the refusal is the affordability
    rule, naming what the account holds. When it does not, engine 1 publishes no balance
    and the refusal is the absence — never a size.
    """
    assert sized_context.mode == "paper"
    an_account_that_has_already_traded(sized_context, store, kraken, fixed_clock)
    if not ledger_answers:
        kraken.fail("trade_volume")
    state = build_state(sized_context)

    config = sized_context.config
    notional = (
        EQUITY_AFTER_FIRST_FILL
        * _decimal(config.get("trading.risk_fraction_per_trade"))
        / _decimal(config.get("barriers.stop_pct"))
    )
    opening = _decimal(config.get("paper.starting_balances")["USD"])
    assert CASH_AFTER_FIRST_FILL < notional < opening, (
        "the witness must sit where the configured balance and the real one disagree"
    )

    result = risk.process(sized_context, state)

    assert result.blocks_trading is True
    assert result.data["approved"] is False
    assert "qty" not in result.data
    if ledger_answers:
        held = Decimal(state["exchange"]["balances"]["USD"])
        assert held == CASH_AFTER_FIRST_FILL - DUE_SPEND, "the ledger counts both fills"
        assert result.data["reason_code"] == REASON_INSUFFICIENT_QUOTE_BALANCE
        assert f"the account holds {held:f}" in (result.reason or "")
    else:
        assert state["exchange"]["balances"] is None, "the broker could not answer"
        assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
        assert NO_BALANCE_PUBLISHED in (result.reason or "")


@pytest.mark.parametrize("mode", ["paper", "live", "replay"])
def test_a_failed_balance_fetch_blocks_in_every_mode_and_names_the_absence(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream, mode: str
) -> None:
    """The plain block, in each mode, with the whole payload pinned.

    Invariant 2: every row of the paper-mode table blocks, and live always did. The payload
    is compared whole, so a refusal that also carried a size — or any key naming a
    substitution — fails here rather than passing on the status alone.
    """
    import dataclasses

    kraken.fail("balance")
    context = dataclasses.replace(sized_context, mode=mode)
    state = build_state(context)
    assert state["exchange"]["balances"] is None, "engine 1 publishes null, never a default"

    result = risk.process(context, state)

    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data == {"reason_code": REASON_INPUTS_UNAVAILABLE, "approved": False}
    assert NO_BALANCE_PUBLISHED in (result.reason or "")


def test_the_same_paper_tick_with_its_balance_published_is_sized(
    risk: RiskEngine, sized_context: Any
) -> None:
    """The pass half of the test above: one input differs, the `Balance` call answering."""
    state = build_state(sized_context)
    assert state["exchange"]["balances"] is not None

    result = risk.process(sized_context, state)

    assert result.blocks_trading is False
    assert result.data["approved"] is True
    assert Decimal(result.data["qty"]) == Decimal("33.33333333")


def test_a_missing_balance_is_refused_before_anything_is_sized(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """Formerly "a rejection on a fallback tick still records the fallback".

    With this `ordermin` a sized candidate is refused `below_ordermin` —
    `test_a_sub_ordermin_position_is_rejected_not_resized` is the twin with the balance
    published. With no balance there is nothing to size against, so the refusal must be
    the absence: a sizing refusal here would mean a size was computed from a balance
    nobody published.
    """
    kraken.fail("balance")
    kraken.set_pair_rule(PAIR, ordermin="500")

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert NO_BALANCE_PUBLISHED in (result.reason or "")


def test_an_approval_publishes_no_fallback_field(
    risk: RiskEngine, sized_context: Any
) -> None:
    """`fallbacks_used` left the payload with the fallback it named (spec 106).

    It had no reader: `rejections` has no such column, and engines 16 and 19 and the
    console never read it from here. An always-empty list would read as "no fallback
    fired" on a record that can no longer record one. The refusal's key set is pinned in
    `test_a_sub_ordermin_position_is_rejected_not_resized`.
    """
    data = risk.process(sized_context, build_state(sized_context)).data

    assert data["approved"] is True
    assert set(data) == {
        "pair",
        "approved",
        "qty",
        "notional",
        "value_at_bid",
        "risk_amount",
        "ordermin",
        "costmin",
        "reason_code",
    }


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #


def test_a_failed_asset_pairs_fetch_blocks_and_is_never_read_as_zero(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 2 gives pair rules no fallback at all, in any mode — "block that pair, a
    wrong `ordermin` produces invalid orders" — and zero is the one value that would make
    every position trivially large enough.

    Driven by failing the real call rather than by nulling a field in a fixture, so what
    is tested is the state engine 1 actually publishes on an `AssetPairs` outage.
    """
    kraken.fail("asset_pairs")
    state = build_state(sized_context)
    assert state["exchange"]["pair_rules"] is None

    result = risk.process(sized_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "pair_rules" in (result.reason or ""), "the missing snapshot, not a missing pair"
    assert "qty" not in result.data


def test_a_pair_with_no_quote_blocks_and_the_reason_names_it(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 2 gives the spread — and therefore the book this price comes from — no
    fallback either. Engine 3 leaves a pair with no usable quote *absent* rather than
    publishing a zero, so the gate must block on the absence and say which pair."""
    kraken.stream_pairs([], at=sized_context.now - timedelta(seconds=60))

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert PAIR in (result.reason or "")


def test_no_equity_snapshot_blocks_rather_than_sizing_against_the_balance(
    risk: RiskEngine, engine_context: Any, store: StoreClient, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 6 sizes against *total account equity* — cash plus open positions —
    which only engine 19 computes. Falling back to the cash balance would let the system
    size a trade against an equity figure nothing had computed, and a fallback is never
    allowed to be the optimistic reading."""
    engine_context.clients.store = store

    result = risk.process(engine_context, build_state(engine_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "equity" in (result.reason or "")


def test_a_float_price_is_refused_rather_than_coerced(
    risk: RiskEngine, sized_context: Any
) -> None:
    """A float survives the orchestrator's JSON check. Spec 35: float drift in an order
    quantity produces a Kraken rejection that is miserable to diagnose.

    The float is written into engine 3's real payload rather than into a fixture. Engine 3
    cannot currently publish one — its money goes through `money_text` — and the point is
    that this gate must not depend on that staying true, because the validator between
    them accepts a float silently.
    """
    state = build_state(sized_context)
    state["market_sensor"]["quotes"][PAIR]["ask"] = 100.0

    result = risk.process(sized_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


@pytest.mark.parametrize("drop", ["scout", "exchange", "market_sensor"])
def test_a_missing_publisher_blocks(
    risk: RiskEngine, sized_context: Any, drop: str
) -> None:
    state = build_state(sized_context)
    del state[drop]

    result = risk.process(sized_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


# --------------------------------------------------------------------------- #
# The seam with C's console
# --------------------------------------------------------------------------- #


def test_every_reason_code_this_engine_emits_is_renderable_by_the_console() -> None:
    """A code absent from C's `REASON_PROSE` renders "No reason was recorded." with no
    error anywhere. `ownership.md` now carries this as a seam row.

    `position_open_on_pair` and `entry_resting_on_pair` joined this list when C landed
    spec 99's prose. Until then they were held by a tripwire asserting their *absence*,
    which went red the moment C was right and was deleted here, as its own failure
    message instructed. The tripwire is gone; the codes it guarded are now checked the
    same way as the other five.
    """
    from acsoe.console.format import REASON_PROSE

    for code in (
        REASON_BELOW_ORDERMIN,
        REASON_BELOW_COSTMIN,
        REASON_INSUFFICIENT_QUOTE_BALANCE,
        REASON_MAX_CONCURRENT_POSITIONS,
        REASON_NO_FX_RATE,
        REASON_POSITION_OPEN_ON_PAIR,
        REASON_ENTRY_RESTING_ON_PAIR,
    ):
        assert code in REASON_PROSE


def test_the_published_payload_is_json_serialisable(
    risk: RiskEngine, sized_context: Any
) -> None:
    import json

    data = risk.process(sized_context, build_state(sized_context)).data

    assert json.loads(json.dumps(data))["qty"] == data["qty"]
    assert isinstance(data["qty"], str)
    assert isinstance(data["value_at_bid"], str)
