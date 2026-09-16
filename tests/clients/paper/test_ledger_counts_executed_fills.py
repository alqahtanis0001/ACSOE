"""Spec 103 — the paper ledger counts every fill the broker has executed.

Operator ruling 2026-09-16, amending invariant 2's paper ledger on *when* a fill enters it:
**the broker's balance includes every fill it has executed, whether or not engine 19 has
recorded it.** Found by A's spec 87 rehearsal: on the tick a resting entry filled, the
balance still held the pre-fill cash while engine 21 counted the new position, so engine 19
wrote equity with the notional counted twice and engine 17 froze the account.

The broker decides a resting entry's fill lazily and engine 1 reads the balance first, so
every test below is about **the order of the reads**, not the arithmetic of one: the
balance before the store knows, either read first, the store catching up, the trade window
moving on, and a process that died between the fill and the record.

The store is B's real `StoreClient`; the wrapped client is C's fake with the stream half
from `test_broker.py`; `OrderState` is A's real model. Engine 19 is not in this file, so
its row is written by hand from the broker's own answer — which is exactly what engine 19
records.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from tests.clients.paper.test_broker import (
    ASK,
    BID,
    MAKER,
    PAIR,
    TAKER,
    USERREF,
    FakeKrakenWithStream,
    buy,
    recorded,
    sell,
)

from acsoe.clients.kraken.contracts import OrderState, OrderStatus, to_micros
from acsoe.clients.paper.broker import PaperBroker
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import OrderRow
from acsoe.clients.store.contracts import OrderStatus as RowStatus
from acsoe.platform.aio import run_blocking

STARTING_USD = Decimal("5000.00")

#: The entry every test rests: 10 at 99.00, below the 100.00 ask so it is not refused.
LIMIT = Decimal("99.00")
QTY = Decimal("10")

#: Tier 3, as `test_broker.py` names it: maker on the resting fill, taker on the sweep.
ENTRY_SPEND = QTY * LIMIT + QTY * LIMIT * Decimal(MAKER)  # 990.00 + 2.178


def make_kraken() -> FakeKrakenWithStream:
    """C's fake with a book and tier 3, and an empty trade window.

    A function rather than only a fixture because the restart test needs a **second** one:
    the stream is per-process, so a restarted daemon sees none of the trades the dead one
    saw.
    """
    client = FakeKrakenWithStream()
    client.set_balances({"USD": "5000.00"})
    client.set_fee_tier(tier=3, maker_fee_pct=MAKER, taker_fee_pct=TAKER)
    client.set_order_book(PAIR, bids=[(BID, "500")], asks=[(ASK, "500")])
    return client


@pytest.fixture
def kraken() -> FakeKrakenWithStream:
    return make_kraken()


@pytest.fixture
def broker(
    kraken: FakeKrakenWithStream, store: StoreClient, paper_config: Any, fixed_clock: Any
) -> PaperBroker:
    return PaperBroker(kraken, store=store, config=paper_config, clock=fixed_clock)


def resting_on_the_book(store: StoreClient, fixed_clock: Any) -> int:
    """An entry engine 19 recorded as resting two minutes ago. Returns its `placed_at`."""
    placed_at = to_micros(fixed_clock.now() - timedelta(seconds=120))
    store.write_order(recorded(buy(limit=str(LIMIT)), status=RowStatus.RESTING, placed_at=placed_at))
    return placed_at


def trade_below_the_limit(kraken: FakeKrakenWithStream, fixed_clock: Any) -> None:
    """A print strictly below 99.00, thirty seconds ago: after `placed_at`, so it fills."""
    kraken.add_trade(PAIR, "98.90", fixed_clock.now() - timedelta(seconds=30))


def usd(broker: PaperBroker) -> Decimal:
    return run_blocking(broker.balance()).balances["USD"]


def the_state(broker: PaperBroker, userref: int = USERREF) -> OrderState:
    (state,) = run_blocking(broker.query_orders([userref]))
    return state


def record_as_engine_19_would(store: StoreClient, state: OrderState, placed_at: int) -> None:
    """The `filled` row engine 19 writes from the state engine 21 published — the broker's."""
    assert state.avg_fill_price is not None
    store.write_order(
        recorded(
            buy(limit=str(LIMIT)),
            status=RowStatus.FILLED,
            placed_at=placed_at,
            filled_qty=format(state.filled_qty, "f"),
            avg_fill_price=format(state.avg_fill_price, "f"),
            fee=format(state.fee, "f"),
            closed_at=state.closed_at,
        )
    )


# --------------------------------------------------------------------------- #
# The defect: a fill the store has not recorded
# --------------------------------------------------------------------------- #


def test_the_balance_on_the_fill_tick_counts_the_spend_before_the_store_records_it(
    broker: PaperBroker, kraken: FakeKrakenWithStream, store: StoreClient, fixed_clock: Any
) -> None:
    """**The defect, asked the way the daemon asks it: engine 1 first, nobody else yet.**

    The entry is resting in the store and a trade has printed through it. Engine 1 reads
    the balance at the top of the tick, before engine 21 has asked about the order, and
    before engine 19 could have recorded anything. The spend must already be gone:
    5000.00 - 990.00 - 2.178 = 4007.822, hand-computed at tier 3's 0.22% maker.
    """
    resting_on_the_book(store, fixed_clock)
    trade_below_the_limit(kraken, fixed_clock)

    assert usd(broker) == Decimal("4007.822") == STARTING_USD - ENTRY_SPEND
    (row,) = store.resting_orders()
    assert row.userref == USERREF, "the store recorded something; this test is about before it does"
    assert store.filled_orders() == ()


@pytest.mark.parametrize("first", ["balance", "query"])
def test_the_balance_and_engine_21s_query_agree_on_one_fill_whichever_is_asked_first(
    broker: PaperBroker,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
    fixed_clock: Any,
    first: str,
) -> None:
    """Spec 103 step 2: decide the fill once and remember it, in either order.

    The balance is compared with the fill **the query returned**, not with a constant, so
    the two reads are shown to describe one fill — the same price and the same fee — and
    the spend is counted exactly once whichever read made the decision.
    """
    resting_on_the_book(store, fixed_clock)
    trade_below_the_limit(kraken, fixed_clock)

    if first == "balance":
        balance = usd(broker)
        state = the_state(broker)
    else:
        state = the_state(broker)
        balance = usd(broker)

    assert state.status is OrderStatus.FILLED
    assert state.avg_fill_price == LIMIT
    assert balance == STARTING_USD - state.filled_qty * state.avg_fill_price - state.fee
    assert balance == STARTING_USD - ENTRY_SPEND
    assert the_state(broker) == state, "a second read decided the fill again, differently"


def test_a_fill_recorded_by_engine_19_is_not_counted_twice(
    broker: PaperBroker, kraken: FakeKrakenWithStream, store: StoreClient, fixed_clock: Any
) -> None:
    """Once the `filled` row exists the store is the record, and the broker stops counting.

    The balance is read on the fill tick, the row is written from the broker's own answer,
    and the balance is read twice more. Every read must be the same figure: a broker that
    kept counting its memory of the fill beside the recorded row would debit 992.178 twice.
    """
    placed_at = resting_on_the_book(store, fixed_clock)
    trade_below_the_limit(kraken, fixed_clock)
    on_the_fill_tick = usd(broker)

    record_as_engine_19_would(store, the_state(broker), placed_at)
    fixed_clock.advance(60)

    assert usd(broker) == on_the_fill_tick == STARTING_USD - ENTRY_SPEND
    assert usd(broker) == on_the_fill_tick
    (row,) = store.filled_orders()
    assert row.userref == USERREF


def test_an_executed_fill_is_not_undone_when_its_trade_leaves_the_window(
    broker: PaperBroker, kraken: FakeKrakenWithStream, store: StoreClient, fixed_clock: Any
) -> None:
    """A fill is a fact once executed. The window is bounded by count and rolls on.

    Engine 19 has not recorded this fill — it errored, say, which spec 104 is about — and
    by the next tick the trade that filled the order has left the stream's window. A broker
    that re-decided from the window each time would un-fill the order: the cash would come
    back and the position engine 21 already reported would have no entry behind it.
    """
    resting_on_the_book(store, fixed_clock)
    trade_below_the_limit(kraken, fixed_clock)
    filled = the_state(broker)
    assert filled.status is OrderStatus.FILLED

    kraken.drain_trades()  # the window has rolled past the trade
    assert kraken.recent_trades() == ()
    fixed_clock.advance(60)

    assert usd(broker) == STARTING_USD - ENTRY_SPEND
    assert the_state(broker) == filled


def test_a_trade_that_arrives_after_the_balance_waits_for_the_next_tick(
    broker: PaperBroker, kraken: FakeKrakenWithStream, store: StoreClient, fixed_clock: Any
) -> None:
    """**The not-filled answer is pinned for the tick too.**

    In the daemon the trade window is filled by the websocket on another thread, so a
    trade can print between engine 1's balance and engine 21's query. If the query then
    decided a fill the balance had not counted, the tick would carry the position without
    the spend — the defect again, in a narrower window. So every read after a balance sees
    the window that balance saw, and the late trade is decided on the next tick, when the
    next balance looks. The pessimistic direction: a fill observed one tick late.
    """
    resting_on_the_book(store, fixed_clock)
    assert usd(broker) == STARTING_USD

    trade_below_the_limit(kraken, fixed_clock)
    assert the_state(broker).status is OrderStatus.RESTING, (
        "the query saw a trade the balance had not, so the two reads describe two ticks"
    )

    fixed_clock.advance(60)
    assert usd(broker) == STARTING_USD - ENTRY_SPEND
    assert the_state(broker).status is OrderStatus.FILLED


def test_a_market_sell_is_counted_before_it_is_recorded(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """Engine 22's sweep, the other kind of fill, counted from the moment it executes.

    Sell 10 into a 99.99 bid at tier 3's 0.38% taker: 999.90 in, 3.79962 fee, so
    5000.00 + 999.90 - 3.79962 = 5996.10038. Then recorded, and counted once. (The ledger
    credits quote only — `apply_fill_to_ledger`'s documented rule — so a sale with no
    recorded entry shows proceeds; the arithmetic is the point here, not the round trip.)
    """
    request = sell(qty="10")
    run_blocking(broker.add_order(request))

    expected = STARTING_USD + Decimal("999.90") - Decimal("999.90") * Decimal(TAKER)
    assert usd(broker) == expected == Decimal("5996.10038")

    (state,) = run_blocking(broker.query_orders([request.userref]))
    assert state.avg_fill_price is not None
    store.write_order(
        recorded(
            request,
            status=RowStatus.FILLED,
            placed_at=to_micros(fixed_clock.now()),
            filled_qty=format(state.filled_qty, "f"),
            avg_fill_price=format(state.avg_fill_price, "f"),
            fee=format(state.fee, "f"),
            closed_at=state.closed_at,
        )
    )
    assert usd(broker) == expected


# --------------------------------------------------------------------------- #
# Restart: the store is what a restarted daemon rebuilds from
# --------------------------------------------------------------------------- #


def test_a_fill_the_process_died_before_recording_is_absent_from_the_rebuilt_ledger_and_positions(
    broker: PaperBroker,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
    paper_config: Any,
    fixed_clock: Any,
    engine_context: Any,
) -> None:
    """Invariant 2's amendment: the rebuilt ledger and the rebuilt positions must agree.

    The dead process executed the fill — its balance showed the spend and engine 21 on it
    would have opened a position — and died before engine 19 wrote anything. The restart
    gets the same store and **a fresh stream**, because the stream is per-process and the
    trade that filled the order is gone with it.

    Then, on the restarted process, through the real engines rather than by inspection:
    engine 1's balance is the untouched ledger, and engine 21 finds the entry still
    resting and **no position**. Both halves are asserted, because the failure this guards
    is the two disagreeing — a ledger that remembered the spend with no position to show
    for it, or a position with the cash still in the account.
    """
    import dataclasses

    from acsoe.engines.exchange.engine import ExchangeEngine
    from acsoe.engines.position_manager.engine import PositionManagerEngine

    resting_on_the_book(store, fixed_clock)
    trade_below_the_limit(kraken, fixed_clock)
    assert usd(broker) == STARTING_USD - ENTRY_SPEND, "the dead process never executed the fill"
    assert the_state(broker).status is OrderStatus.FILLED
    rows_before: tuple[OrderRow, ...] = store.resting_orders()

    fixed_clock.advance(60)
    restarted = PaperBroker(make_kraken(), store=store, config=paper_config, clock=fixed_clock)
    clients = dataclasses.replace(engine_context.clients, kraken=restarted, store=store)
    context = dataclasses.replace(engine_context, now=fixed_clock.now(), clients=clients)

    exchange = ExchangeEngine().process(context, {}).data
    assert Decimal(exchange["balances"]["USD"]) == STARTING_USD

    state: dict[str, Any] = {
        "system": {"mode": "running", "close_intent": False},
        "cycle_id": 1,
        "guard_blockers": [],
        "exchange": exchange,
    }
    managed = PositionManagerEngine().process(context, state).data
    assert managed["positions"] == [], managed
    assert managed["orders"] == [], "engine 21 recorded a fill the restarted process never saw"
    assert managed["entry_orders_cancelled"] is False, "the entry is still on the book"

    assert store.open_positions() == ()
    assert store.filled_orders() == ()
    assert store.resting_orders() == rows_before
    assert the_state(restarted).status is OrderStatus.RESTING


# --------------------------------------------------------------------------- #
# A fill is due and cannot be priced
# --------------------------------------------------------------------------- #


def test_a_due_fill_with_no_fee_tier_makes_the_balance_a_failed_fetch_not_an_error(
    broker: PaperBroker,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
    fixed_clock: Any,
    engine_context: Any,
) -> None:
    """The balance is **unknown** while a due fill cannot be priced, and it says so.

    Deciding fills in `balance()` gives it a dependency it did not have: the maker rate. If
    `TradeVolume` is down while a trade has printed through a resting entry, the cash cannot
    be computed. The broker reports that as the exchange-shaped failure it is, so engine 1
    records `balance` as a failed call and keeps the calls that answered — rather than
    raising a broker error engine 1 re-raises, which would empty its whole payload,
    `pair_rules` included, for as long as the outage lasts. Nothing downstream can size
    against the missing cash: engine 9 publishes no estimate and engine 10 blocks, on the
    missing fee tier as well.
    """
    import dataclasses

    from acsoe.clients.kraken.errors import KrakenUnavailableError
    from acsoe.engines.exchange.engine import ExchangeEngine

    resting_on_the_book(store, fixed_clock)
    trade_below_the_limit(kraken, fixed_clock)
    kraken.fail("trade_volume")

    with pytest.raises(KrakenUnavailableError, match=r"paper ledger cannot be computed.*no fee tier"):
        run_blocking(broker.balance())

    clients = dataclasses.replace(engine_context.clients, kraken=broker, store=store)
    context = dataclasses.replace(engine_context, clients=clients)
    published = ExchangeEngine().process(context, {}).data
    assert published["balances"] is None
    assert published["fee_tier"] is None
    assert published["pair_rules"] is not None, "engine 1 lost the calls that answered"
    assert sorted(failure["call"] for failure in published["failed_fetches"]) == [
        "balance",
        "trade_volume",
    ]


def test_with_nothing_due_the_fee_tier_outage_does_not_touch_the_balance(
    broker: PaperBroker, kraken: FakeKrakenWithStream, store: StoreClient, fixed_clock: Any
) -> None:
    """The pass half: a resting entry nothing has traded through needs no fee, so the
    ledger answers through the same outage. Without this, the test above is satisfied by a
    balance that fails whenever `TradeVolume` does."""
    resting_on_the_book(store, fixed_clock)
    kraken.fail("trade_volume")

    assert usd(broker) == STARTING_USD


def test_a_broker_defect_met_while_deciding_fills_is_raised_as_itself(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """Only an exchange call that did not answer becomes a failed balance fetch.

    A resting entry recorded with no limit price is a contradiction no engine writes, and
    the broker refuses to decide whether it filled. That refusal has no exchange failure
    behind it, so it must reach engine 1 as the defect it is - re-raised, and recorded by
    the orchestrator as an `ERROR` - and not be laundered into "the exchange was
    unavailable", which an operator would wait out rather than fix.
    """
    from acsoe.clients.kraken.errors import KrakenError
    from acsoe.clients.paper.broker import PaperBrokerError

    row = recorded(
        buy(limit=str(LIMIT)),
        status=RowStatus.RESTING,
        placed_at=to_micros(fixed_clock.now() - timedelta(seconds=120)),
    )
    store.write_order(OrderRow(**{**row.model_dump(), "limit_price": None}))

    with pytest.raises(PaperBrokerError, match="has no limit price") as raised:
        run_blocking(broker.balance())
    assert not isinstance(raised.value, KrakenError)
