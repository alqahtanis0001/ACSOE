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
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import EquitySnapshotRow, PositionRow, PositionStatus
from acsoe.core.contracts import EngineStatus
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.risk.contracts import (
    FALLBACK_BALANCE_FROM_PAPER,
    REASON_BELOW_COSTMIN,
    REASON_BELOW_ORDERMIN,
    REASON_INPUTS_UNAVAILABLE,
    REASON_INSUFFICIENT_QUOTE_BALANCE,
    REASON_MAX_CONCURRENT_POSITIONS,
    REASON_NO_FX_RATE,
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


def open_position(position_id: str, pair: str) -> PositionRow:
    """One open position, for the portfolio cap. Only `status` and `pair` matter here."""
    base, _, quote = pair.partition("/")
    return PositionRow(
        position_id=position_id,
        run_id="test-run",
        cycle_id=1,
        pair=pair,
        base=base,
        quote=quote,
        status=PositionStatus.OPEN,
        qty=Decimal("1.00000000"),
        entry_price=Decimal("100.00"),
        target_price=Decimal("103.00"),
        stop_price=Decimal("98.50"),
        timeout_at=9_999,
        opened_at=1_000,
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
        "fallbacks_used",
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
    names no EUR, which is an account holding nothing rather than an outage, so it blocks
    rather than reaching the paper-mode fallback below.
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
    assert "EUR" in (result.reason or "")
    assert FALLBACK_BALANCE_FROM_PAPER not in (result.reason or "")


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
    reads the store. `max_concurrent_positions` is 3 in the committed config."""
    for index, pair in enumerate(("BTC/USD", "ETH/USD", "XRP/USD")):
        store.write_position(open_position(f"p-{index}", pair))

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_MAX_CONCURRENT_POSITIONS
    assert "qty" not in result.data, "the cap is checked before sizing, so nothing is sized"


# --------------------------------------------------------------------------- #
# The balance fallback — invariant 2's last surviving one, built by spec 41
# --------------------------------------------------------------------------- #


def test_paper_mode_falls_back_to_the_configured_starting_balances_and_records_it(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """The paper half of the pair.

    Spec 37 retired "assume tier 1", so balance is the only row of invariant 2's
    paper-mode table that still substitutes a value instead of refusing — and until spec
    41 nothing in the system implemented it. Engine 1 deliberately applies no fallback of
    its own and leaves it to the consumer that has to record which one fired, so this is
    the consumer doing both halves: substituting, and recording.

    `paper.starting_balances` is `{USD: "5000.00"}` in the committed config, which is the
    same figure the balances carry, so the sizing is unchanged and the *only* observable
    difference is the recorded fallback. That is deliberate: it isolates the recording.
    """
    kraken.fail("balance")
    state = build_state(sized_context)
    assert state["exchange"]["balances"] is None, "engine 1 publishes null, never a default"

    result = risk.process(sized_context, state)

    assert result.blocks_trading is False
    assert result.data["approved"] is True
    assert result.data["fallbacks_used"] == [FALLBACK_BALANCE_FROM_PAPER]
    assert Decimal(result.data["qty"]) == Decimal("33.33333333")


def test_live_mode_blocks_on_the_same_failed_balance_fetch(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """The live half, and the pair is why it exists.

    The paper test alone passes against an implementation that never looks at the mode and
    always falls back — which would be invariant 2 inverted, since a failed fetch in live
    mode always blocks and the one exception in that document is rule 14's liquidation.
    So the two are written as a pair against the same failure.
    """
    import dataclasses

    kraken.fail("balance")
    live = dataclasses.replace(sized_context, mode="live")

    result = risk.process(live, build_state(live))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "live" in (result.reason or "")
    assert "qty" not in result.data


def test_a_rejection_on_a_fallback_tick_still_records_the_fallback(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 2: *every decision* affected by a fallback records which fallback fired.

    A rejection is a decision. Recording the fallback only on approvals would leave the
    `rejections` rows — which are the research dataset — unable to say that the tick was
    priced against a configured balance rather than a fetched one, and rejections are the
    rows this system produces most of.
    """
    kraken.fail("balance")
    kraken.set_pair_rule(PAIR, ordermin="500")

    result = risk.process(sized_context, build_state(sized_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_BELOW_ORDERMIN
    assert result.data["fallbacks_used"] == [FALLBACK_BALANCE_FROM_PAPER]


def test_an_approved_sizing_with_no_failure_records_no_fallback(
    risk: RiskEngine, sized_context: Any
) -> None:
    """The other side of the recording: a fallback that did not fire is not reported.

    Worth one test because the old implementation read a key nothing published and so
    reported `[]` on every tick including the ones where a fallback *should* have fired.
    An empty list means something now.
    """
    data = risk.process(sized_context, build_state(sized_context)).data

    assert data["approved"] is True
    assert data["fallbacks_used"] == []


def test_the_fallback_is_not_applied_when_the_map_names_no_such_currency(
    risk: RiskEngine, sized_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """Falling back to a map that does not name this pair's quote currency would be
    substituting nothing for something. `paper.starting_balances` is `{USD: ...}`, so a
    GBP-quoted pair whose `Balance` fetch failed blocks and names the currency."""
    gbp_pair = "SOL/GBP"
    kraken.set_pair_rule(
        gbp_pair,
        base="SOL",
        quote="GBP",
        ordermin="0.05",
        costmin="5.00",
        tick_size="0.001",
        lot_decimals=8,
        pair_decimals=3,
    )
    kraken.set_order_book(gbp_pair, bids=[(DEFAULT_BID, "500")], asks=[(DEFAULT_ASK, "500")])
    kraken.stream_pairs([gbp_pair], at=sized_context.now - timedelta(seconds=60))
    kraken.fail("balance")

    result = risk.process(sized_context, build_state(sized_context, pair=gbp_pair))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "GBP" in (result.reason or "")


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
    error anywhere. `ownership.md` now carries this as a seam row."""
    from acsoe.console.format import REASON_PROSE

    for code in (
        REASON_BELOW_ORDERMIN,
        REASON_BELOW_COSTMIN,
        REASON_INSUFFICIENT_QUOTE_BALANCE,
        REASON_MAX_CONCURRENT_POSITIONS,
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
