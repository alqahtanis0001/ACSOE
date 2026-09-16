"""Engine 21 `position_manager` — spec 92.

**No upstream payload is hand-built.** `state["exchange"]` and `state["market_sensor"]`
are A's real engines 1 and 3 run against C's fake Kraken client, per the Phase 3 ruling,
and the order client is B's real `PaperBroker` from spec 88 wrapping that same fake. So a
fill in this file is a fill the simulator decided, at a price the fake's book produced,
for a fee from the fake's tier 3 — not a value a fixture asserted into existence.

The one thing written by hand is a store row engine 19 would have written on a *previous*
tick, because engine 19 is C's and does not run in this chain. Those go through
`OrderRow` and `PositionRow`, so a shape engine 19 could not produce is refused before
engine 21 sees it.

Every block-and-pass pair below differs in **one input**: the blocker's name, the
position's age, the traded low, whether `close_intent` is set. That is spec 92 step 10's
requirement and it is what stops "the hold holds" passing against an engine that never
triggers anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from tests.harness.fake_kraken import FakeKrakenClient

from acsoe.clients.kraken.contracts import OrderState, QuoteTick, TradeTick
from acsoe.clients.kraken.contracts import OrderStatus as ClientOrderStatus
from acsoe.clients.paper.broker import PaperBroker
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import (
    MICROSECONDS_PER_SECOND,
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
from acsoe.engines.position_manager.contracts import (
    ENTRY_ORDERS_CANCELLED_FIELD,
    HOLD_DATA_GUARD_BLOCKED,
    HOLD_REASON_FIELD,
    ORDERS_FIELD,
    POSITIONS_FIELD,
    POSITIONS_VALUE_FIELD,
    TRIGGERED_FIELD,
    UNREALISED_PNL_FIELD,
    Barrier,
    position_id_for,
)
from acsoe.engines.position_manager.engine import PositionManagerEngine

PAIR = "SOL/USD"

#: Tier 3, standing rule 8 of the Phase 6 task list.
MAKER = "0.0022"
TAKER = "0.0038"

#: The committed config: `barriers.target_pct` 0.03, `stop_pct` 0.015, `timeout_bars` 48,
#: `timeframes.decision_bar_s` 900, `trading.entry_unfilled_window_s` 300. Every
#: expectation below is derived from these rather than from a number this file chose, so
#: a retune by the operator fails the test that names the value instead of passing
#: quietly against a stale one.
LIMIT = Decimal("99.00")
TARGET = LIMIT * (Decimal(1) + Decimal("0.03"))
STOP = LIMIT * (Decimal(1) - Decimal("0.015"))
WINDOW_S = 300
USERREF = 4_242


class FakeKrakenWithStream(FakeKrakenClient):
    """C's fake plus the stream half engine 3 reads and the broker forwards."""

    def __init__(self, *, now: int = 0) -> None:
        super().__init__(now=now)
        self._trades: list[TradeTick] = []
        self._quotes: dict[str, QuoteTick] = {}

    def add_trade(self, pair: str, price: str, at: datetime) -> None:
        self._trades.append(
            TradeTick(pair=pair, ts=at, price=Decimal(price), qty=Decimal("1"))
        )

    def recent_trades(self) -> tuple[TradeTick, ...]:
        return tuple(self._trades)

    def drain_trades(self) -> tuple[TradeTick, ...]:
        trades = tuple(self._trades)
        self._trades.clear()
        return trades

    def quote(self, pair: str, *, bid: str, ask: str, at: datetime) -> None:
        self._quotes[pair] = QuoteTick(
            pair=pair, ts=at, bid=Decimal(bid), ask=Decimal(ask)
        )

    def latest_quote(self, pair: str) -> QuoteTick | None:
        return self._quotes.get(pair)


@pytest.fixture
def kraken(engine_context: Any) -> FakeKrakenWithStream:
    client = FakeKrakenWithStream()
    client.set_balances({"USD": "5000.00"})
    client.set_fee_tier(tier=3, maker_fee_pct=MAKER, taker_fee_pct=TAKER)
    client.set_order_book(PAIR, bids=[("99.99", "500")], asks=[("100.00", "500")])
    client.quote(PAIR, bid="99.99", ask="100.00", at=engine_context.now)
    # Engine 3 publishes a quote only for a pair it has seen *trade* — `_quotes` walks
    # the trade set, not the subscription — so a pair with a book and no print has no
    # quote and no mark. One old trade, ten minutes back, is what makes the pair visible
    # to engine 3 at all. It is deliberately outside every `trade_ranges` window a test
    # opens (60 seconds) and above every limit any test rests at, so it can neither fire
    # a barrier nor fill an entry.
    client.add_trade(PAIR, "99.99", engine_context.now - timedelta(seconds=600))
    return client


@pytest.fixture
def broker(
    kraken: FakeKrakenWithStream, store: StoreClient, paper_config: Any, fixed_clock: Any
) -> PaperBroker:
    return PaperBroker(kraken, store=store, config=paper_config, clock=fixed_clock)


@pytest.fixture
def context(engine_context: Any, broker: PaperBroker, store: StoreClient) -> Any:
    engine_context.clients.kraken = broker
    engine_context.clients.store = store
    return engine_context


@pytest.fixture
def manager() -> PositionManagerEngine:
    return PositionManagerEngine()


class _BrokerAnswering:
    """The real `PaperBroker` with **one** answer overridden, and nothing else changed.

    The four tests below need an answer the simulator cannot produce: a fill at a price
    that is not the limit, a query that reports on fewer orders than it was asked about,
    and a cancel that comes back filled or still resting. Each is a state a real exchange
    reaches and the paper broker, correctly, never does — it fills a resting maker buy at
    its own limit and it raises on a `userref` it does not know.

    This is deliberately a *wrapper* rather than a fake order client. Everything the
    engine reads still comes from the real broker over the real fake's book; only the
    single field under test is replaced, and it is replaced with a freshly constructed
    `OrderState` so A's validators still apply. A hand-built fake would have let the
    whole surface drift into agreement with the engine, which is the failure mode the
    module docstring above exists to prevent.
    """

    def __init__(
        self,
        real: PaperBroker,
        *,
        query: str = "pass through",
        cancel: str = "pass through",
        fill_price: Decimal | None = None,
    ) -> None:
        self._real = real
        self._query = query
        self._cancel = cancel
        self._fill_price = fill_price

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    async def query_orders(self, userrefs: Sequence[int]) -> tuple[OrderState, ...]:
        if self._query == "reports on nothing":
            return ()
        states = await self._real.query_orders(userrefs)
        if self._fill_price is None:
            return states
        return tuple(
            state
            if state.avg_fill_price is None
            else OrderState(
                userref=state.userref,
                order_id=state.order_id,
                status=state.status,
                # What the order *is* is passed through; only what the exchange reports
                # about it is replaced. `limit_price` in particular must stay the real
                # 99.00 while `avg_fill_price` becomes 98.50 — the whole point of this
                # wrapper is that the two are different numbers, so an engine reading
                # the wrong one is visible.
                qty=state.qty,
                limit_price=state.limit_price,
                filled_qty=state.filled_qty,
                avg_fill_price=self._fill_price,
                fee=state.fee,
                closed_at=state.closed_at,
            )
            for state in states
        )

    async def cancel_order(self, userref: int) -> OrderState:
        state = await self._real.cancel_order(userref)
        if self._cancel == "filled instead":
            return OrderState(
                userref=state.userref,
                order_id=state.order_id,
                status=ClientOrderStatus.FILLED,
                qty=state.qty,
                limit_price=state.limit_price,
                filled_qty=Decimal("10"),
                avg_fill_price=LIMIT,
                fee=Decimal("10") * LIMIT * Decimal(MAKER),
                # The real cancel reports a terminal state, so it carries one. Passed
                # through rather than invented: `OrderState` requires `closed_at` on a
                # terminal status, so a `None` here fails loudly at construction instead
                # of teaching the engine that a filled order has no close time.
                closed_at=state.closed_at,
            )
        if self._cancel == "did not take":
            return OrderState(
                userref=state.userref,
                order_id=state.order_id,
                status=ClientOrderStatus.RESTING,
                qty=state.qty,
                limit_price=state.limit_price,
                filled_qty=Decimal("0"),
                fee=Decimal("0"),
            )
        return state


def build_state(
    context: Any,
    *,
    blocked_by: str | None = None,
    close_intent: bool = False,
    previous_now: datetime | None = None,
) -> dict[str, Any]:
    """`state` as the manage chain would have it, from the real engines 1 and 3.

    `previous_now` is what gives engine 3 a `trade_ranges` at all — it publishes none on
    a process's first tick, correctly, because "since the previous tick" has no meaning
    then. A test that wants a barrier decided has to supply one.
    """
    import dataclasses

    tick = context if previous_now is None else dataclasses.replace(
        context, previous_now=previous_now
    )
    state: dict[str, Any] = {
        "system": {"mode": "running", "close_intent": close_intent},
        "cycle_id": 1,
        "guard_blockers": [] if blocked_by is None else [blocked_by],
        "exchange": ExchangeEngine().process(tick, {}).data,
        "market_sensor": MarketSensorEngine().process(tick, {}).data,
    }
    if blocked_by is not None:
        state["trading_blocked_by"] = blocked_by
    return state


def resting_entry(
    context: Any, *, age_s: int = 120, userref: int = USERREF, limit: Decimal = LIMIT
) -> OrderRow:
    """An entry engine 19 recorded on a previous tick. `age_s` is its only real variable.

    The default is two minutes: inside the 300-second window so nothing is cancelled by
    accident, and older than the 30 seconds `traded` uses, because the broker fills only
    on a trade **strictly after** `placed_at`. An entry and a trade at the same instant
    do not fill, which is correct and is not what these tests are about.
    """
    placed_at = to_micros(context.now) - age_s * MICROSECONDS_PER_SECOND
    return OrderRow(
        userref=userref,
        order_id=f"paper-{userref}",
        run_id="test-run",
        cycle_id=1,
        pair=PAIR,
        side=OrderSide.BUY,
        intent=OrderIntent.ENTRY,
        order_type=OrderType.LIMIT,
        oflags="post",
        status=OrderStatus.RESTING,
        qty=Decimal("10"),
        limit_price=limit,
        filled_qty=Decimal("0"),
        placed_at=placed_at,
        updated_at=placed_at,
    )


def open_position(
    context: Any,
    *,
    entry_price: Decimal = LIMIT,
    age_s: int = 60,
    timeout_in_s: int = 43_200,
    position_id: str = "pos-1",
) -> PositionRow:
    """An open position engine 19 recorded earlier. Barriers from the committed config."""
    opened_at = to_micros(context.now) - age_s * MICROSECONDS_PER_SECOND
    return PositionRow(
        position_id=position_id,
        run_id="test-run",
        cycle_id=1,
        pair=PAIR,
        base="SOL",
        quote="USD",
        status=PositionStatus.OPEN,
        qty=Decimal("10"),
        entry_price=entry_price,
        target_price=entry_price * (Decimal(1) + Decimal("0.03")),
        stop_price=entry_price * (Decimal(1) - Decimal("0.015")),
        timeout_at=to_micros(context.now) + timeout_in_s * MICROSECONDS_PER_SECOND,
        entry_userref=USERREF,
        opened_at=opened_at,
        updated_at=opened_at,
    )


def traded(
    kraken: FakeKrakenWithStream, context: Any, prices: Sequence[str], *, ago_s: int = 30
) -> None:
    """Make the pair trade at each price since the previous tick."""
    for price in prices:
        kraken.add_trade(PAIR, price, context.now - timedelta(seconds=ago_s))


def one_minute_ago(context: Any) -> datetime:
    return context.now - timedelta(seconds=60)


# --------------------------------------------------------------------------- #
# Registry shape
# --------------------------------------------------------------------------- #


def test_the_engine_declares_itself_as_the_registry_will_have_it(
    manager: PositionManagerEngine,
) -> None:
    """Not a gate. It refuses nothing — it acts — and invariant 3's gate list must not
    grow a name that never returns BLOCK."""
    assert (manager.name, manager.number, manager.is_gate) == ("position_manager", 21, False)


def test_the_published_field_names_are_engine_nineteens() -> None:
    """Contract rule 3 forbids importing engine 19, so the names are restated — and a
    restatement that nobody checks is a rename waiting to happen. Engine 19 reads these
    exact strings out of `state["position_manager"]`, and a drift would record nothing
    while everything stayed green."""
    from acsoe.engines.memory import contracts as memory

    assert POSITIONS_FIELD == memory.POSITIONS_FIELD
    assert ORDERS_FIELD == memory.ORDERS_FIELD
    assert POSITIONS_VALUE_FIELD == memory.POSITIONS_VALUE_FIELD
    assert UNREALISED_PNL_FIELD == memory.UNREALISED_PNL_FIELD
    assert HOLD_REASON_FIELD == memory.HOLD_REASON_FIELD


def test_the_two_order_status_enums_are_different_objects_that_compare_equal() -> None:
    """The hazard this engine cost thirteen red tests to find, stated as a fact.

    `OrderRow.status` is the store's `OrderStatus`; `OrderState.status` is the kraken
    contracts' `OrderStatus`. Same five spellings, equal under `==`, **not** the same
    object — so `is` between them is always `False`. Engine 21 reads the second and
    writes the first, and comparing a client answer against the store's enum sent every
    resting entry down the "already terminal, nothing to do" branch: no cancel, no fill,
    and `entry_orders_cancelled: True` with a live post-only buy on the book.

    `mypy --strict` cannot see it. `context.clients.kraken` is structural and typed
    `Any`, so there is nothing to compare. This test is the guard instead, and it is
    written to state the trap rather than to prove the fix — the behavioural tests do
    that — so the next person to import one of these meets it in words.
    """
    from acsoe.clients.kraken.contracts import OrderStatus as ClientOrderStatus

    assert ClientOrderStatus.RESTING == OrderStatus.RESTING
    assert ClientOrderStatus.RESTING is not OrderStatus.RESTING


# --------------------------------------------------------------------------- #
# A resting entry that filled becomes a position
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("trade_price", "fills"),
    [("98.99", True), ("99.00", False)],
    ids=["a trade below the limit fills", "a touch does not"],
)
def test_an_entry_becomes_a_position_only_when_the_broker_says_it_filled(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
    trade_price: str,
    fills: bool,
) -> None:
    """Engine 21 does not decide fills and must not look like it does.

    The fill comes from `query_orders` — the broker in paper, the exchange in live — and
    the only thing that moves between these two cases is the traded price the simulator
    is given. An engine that compared the price itself would be a third opinion about
    what filled, and the three would diverge on exactly the ticks that matter.
    """
    store.write_order(resting_entry(context))
    traded(kraken, context, [trade_price])

    data = manager.process(context, build_state(context)).data

    assert (len(data[POSITIONS_FIELD]) == 1) is fills
    assert (len(data[ORDERS_FIELD]) == 1) is fills


def test_a_fill_sets_the_barriers_from_the_fill_price_and_not_the_bar_close(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
) -> None:
    """The lead ruling, asserted on the arithmetic rather than on its existence.

    The entry rests at 99.00 and fills there, so target is 99.00 x 1.03 and stop is
    99.00 x 0.985 — **not** anything derived from the decision bar's close, which is a
    different price and is what the training label measures from. Engine 11 sized the
    quantity by dividing the risk budget by the stop distance from the price paid, so a
    stop placed from another price risks a different amount than the gate approved.
    """
    store.write_order(resting_entry(context))
    traded(kraken, context, ["98.00"])

    position = manager.process(context, build_state(context)).data[POSITIONS_FIELD][0]

    assert Decimal(position["entry_price"]) == LIMIT
    assert Decimal(position["target_price"]) == TARGET
    assert Decimal(position["stop_price"]) == STOP
    assert position["position_id"] == position_id_for(USERREF)
    assert position["entry_userref"] == USERREF


def test_the_barriers_come_from_the_price_the_client_reports_not_the_limit_on_record(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
    broker: PaperBroker,
) -> None:
    """The same ruling as the test above, asked of a fixture that can tell the two apart.

    The test above compares `entry_price` against `LIMIT`, and the paper broker fills a
    resting post-only buy **at its limit** — so `avg_fill_price` and `limit_price` are
    the same number there and the assertion passes whichever one the engine reads. A
    mutation swapping `filled.avg_fill_price` for `entry.limit_price` survived all forty
    tests in this file. The test was not wrong about its subject; it was wrong about its
    witness, which is Phase 5's closing finding in a different engine.

    Here the client answers 98.50 for an order resting at 99.00, so only the client's
    answer produces these numbers. It is not a hypothetical distinction: `entry` may be a
    `_PublishedEntry` built out of this tick's `state["execution"]`, which is engine 18's
    claim about what it asked for, while `avg_fill_price` is the exchange's answer about
    what happened. Engine 11 sized the quantity against the stop distance from the price
    actually paid, so barriers from any other price risk a different amount of money than
    the gate approved.
    """
    paid = Decimal("98.50")
    assert paid != LIMIT, "the whole point is a fill price the record does not carry"
    store.write_order(resting_entry(context))
    traded(kraken, context, ["98.00"])
    context.clients.kraken = _BrokerAnswering(broker, fill_price=paid)

    position = manager.process(context, build_state(context)).data[POSITIONS_FIELD][0]

    assert Decimal(position["entry_price"]) == paid
    assert Decimal(position["target_price"]) == paid * (Decimal(1) + Decimal("0.03"))
    assert Decimal(position["stop_price"]) == paid * (Decimal(1) - Decimal("0.015"))


def test_the_timeout_is_the_configured_bars_after_the_fill(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
) -> None:
    """48 bars of 900 seconds, from the moment of the fill. Twelve hours, and it is
    measured from the fill for the same reason the barriers are."""
    store.write_order(resting_entry(context))
    traded(kraken, context, ["98.00"])

    data = manager.process(context, build_state(context)).data
    position = data[POSITIONS_FIELD][0]
    order = data[ORDERS_FIELD][0]

    assert position["timeout_at"] == order["closed_at"] + 48 * 900 * MICROSECONDS_PER_SECOND


def test_the_published_rows_carry_no_tick_identifiers(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
) -> None:
    """Engine 19's `_stamped` sets `run_id`, `cycle_id` and `updated_at` itself, and says
    why: a row carrying somebody else's `run_id` cannot be joined to the block record for
    the tick, and `(run_id, cycle_id)` is the join. A publisher that set them would win,
    silently, because `_stamped` overwrites rather than refusing."""
    store.write_order(resting_entry(context))
    traded(kraken, context, ["98.00"])

    data = manager.process(context, build_state(context)).data

    for row in list(data[POSITIONS_FIELD]) + list(data[ORDERS_FIELD]):
        assert "run_id" not in row
        assert "cycle_id" not in row
        assert "updated_at" not in row


def test_a_fill_the_pair_rules_cannot_describe_publishes_nothing_for_that_order(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
) -> None:
    """`base` and `quote` have one publisher and invariant 2 gives it no fallback.

    Publishing the *order* row alone would record the entry as filled with no position
    against it — money spent and nothing holding it, and the entry would no longer be
    resting so nothing would ever pick it up. So nothing at all is published for that
    order: it stays resting in the store and next tick the same fill is recorded. The
    tick still completes, because the other positions still have to be managed.
    """
    kraken.fail("asset_pairs")
    store.write_order(resting_entry(context))
    traded(kraken, context, ["98.00"])
    state = build_state(context)
    assert state["exchange"]["pair_rules"] is None, "engine 1 publishes null on a failure"

    result = manager.process(context, state)

    assert result.status is EngineStatus.OK
    assert result.data[POSITIONS_FIELD] == []
    assert result.data[ORDERS_FIELD] == []
    assert result.data["reason_code"] == "position_unrecordable"
    assert result.data[ENTRY_ORDERS_CANCELLED_FIELD] is False, "it is still resting"


# --------------------------------------------------------------------------- #
# The stale-entry cancel
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("age_s", "cancelled"),
    [(WINDOW_S, True), (WINDOW_S - 1, False)],
    ids=["at the window it is cancelled", "one second inside it is not"],
)
def test_an_entry_is_cancelled_at_its_window_and_not_before(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    age_s: int,
    cancelled: bool,
) -> None:
    """`trading.entry_unfilled_window_s` is 300. The boundary is `>=`, so an entry
    exactly at its window is cancelled — invariant 8 says an entry unfilled *after* the
    window is abandoned, and waiting one more tick to be sure is a tick of unpriced
    exposure."""
    store.write_order(resting_entry(context, age_s=age_s))

    data = manager.process(context, build_state(context)).data

    assert (len(data[ORDERS_FIELD]) == 1) is cancelled
    if cancelled:
        assert data[ORDERS_FIELD][0]["status"] == OrderStatus.CANCELLED.value
        assert data[ORDERS_FIELD][0]["filled_qty"] == "0"


def test_a_stale_entry_is_still_cancelled_during_a_data_guard_hold(
    manager: PositionManagerEngine, context: Any, store: StoreClient
) -> None:
    """Invariant 8, in as many words: *that cancellation still happens while the manage
    chain is holding on a `data_guard` block.*

    It is a decision about elapsed time, not about price — it reads `context.now`, needs
    no market data, and reduces exposure. The hold suppresses **exits**, never this. A
    held cancel would leave a post-only buy on the book through a blackout, which is
    exposure the system has already declared it does not trust the data for.
    """
    store.write_order(resting_entry(context, age_s=WINDOW_S + 60))

    data = manager.process(context, build_state(context, blocked_by="data_guard")).data

    assert data[HOLD_REASON_FIELD] == HOLD_DATA_GUARD_BLOCKED
    assert len(data[ORDERS_FIELD]) == 1
    assert data[ORDERS_FIELD][0]["status"] == OrderStatus.CANCELLED.value


def test_an_entry_that_filled_during_the_cancel_becomes_a_position_not_a_cancellation(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    broker: PaperBroker,
) -> None:
    """The race between the query and the cancel, and it is the expensive one.

    The engine asked to cancel and the exchange answered "it filled". The money is
    already spent. Recording a cancellation would leave the account holding a position
    with no `positions` row against it — nothing marks it, no barrier can fire on it and
    engine 22 will never exit it, so it sits until someone reads the exchange by hand.

    The engine handles this and the branch carries a comment saying why; nothing asked
    for it until a mutation that reported the fill as a cancellation survived all forty
    tests. The entry is stale, so an ordinary tick reaches the cancel without needing a
    liquidation.
    """
    store.write_order(resting_entry(context, age_s=WINDOW_S + 1))
    context.clients.kraken = _BrokerAnswering(broker, cancel="filled instead")

    data = manager.process(context, build_state(context)).data

    assert [row["status"] for row in data[ORDERS_FIELD]] == [OrderStatus.FILLED.value]
    assert len(data[POSITIONS_FIELD]) == 1, "the money bought something, so it is held"
    assert data[POSITIONS_FIELD][0]["entry_userref"] == USERREF


def test_a_cancel_that_did_not_take_leaves_the_completion_flag_false(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    broker: PaperBroker,
) -> None:
    """The kill switch's retry, which `_manage`'s comment states in three lines and
    nothing asserted.

    `entry_orders_cancelled` means **only** "nothing is resting any more". A cancel the
    exchange did not act on leaves the order on the book, so the flag must stay `False`,
    the orchestrator must keep `close_intent` set, and the next tick must try again. A
    `True` here ends the liquidation with a live post-only buy still able to fill —
    invariant 8's named failure.

    One input differs from `test_close_intent_cancels_a_fresh_entry_inside_its_window`:
    what the cancel comes back as.
    """
    store.write_order(resting_entry(context, age_s=1))
    context.clients.kraken = _BrokerAnswering(broker, cancel="did not take")

    data = manager.process(context, build_state(context, close_intent=True)).data

    assert data[ENTRY_ORDERS_CANCELLED_FIELD] is False
    assert data[ORDERS_FIELD] == [], "nothing is recorded as cancelled, because nothing was"


def test_an_entry_is_never_replaced_or_re_placed(
    manager: PositionManagerEngine, context: Any, store: StoreClient
) -> None:
    """Invariant 8: never chase with a market order, and cancelling is the whole of the
    response. The published rows are checked for any order that is not the cancellation
    — a re-place would appear as a second row with a `resting` status."""
    store.write_order(resting_entry(context, age_s=WINDOW_S + 60))

    data = manager.process(context, build_state(context)).data

    assert [row["status"] for row in data[ORDERS_FIELD]] == [OrderStatus.CANCELLED.value]


# --------------------------------------------------------------------------- #
# The hold
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("blocker", "holds"),
    [("data_guard", True), ("cost", False), ("safety", False), (None, False)],
    ids=["data_guard holds", "cost does not", "safety does not", "no blocker does not"],
)
def test_only_a_data_guard_block_holds(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
    blocker: str | None,
    holds: bool,
) -> None:
    """One input moves: the name of the blocker.

    A `cost` or `safety` block is a statement about whether to *open* something. A
    position already open still has to be managed, and holding on either would leave a
    stop unactioned because the account was frozen — which is the opposite of what a
    freeze is for.
    """
    store.write_position(open_position(context))
    traded(kraken, context, ["90.00"])
    state = build_state(context, blocked_by=blocker, previous_now=one_minute_ago(context))

    data = manager.process(context, state).data

    assert (data[HOLD_REASON_FIELD] == HOLD_DATA_GUARD_BLOCKED) is holds
    assert (len(data[TRIGGERED_FIELD]) == 0) is holds


def test_the_hold_reason_is_null_rather_than_omitted_on_a_tick_that_did_not_hold(
    manager: PositionManagerEngine, context: Any
) -> None:
    """Null is the answer here — "I considered holding and did not" — where an omission
    is indistinguishable from an engine that never ran. Engine 19 records it either way,
    and the console renders it."""
    data = manager.process(context, build_state(context)).data

    assert HOLD_REASON_FIELD in data
    assert data[HOLD_REASON_FIELD] is None


def test_a_liquidation_never_holds_even_on_a_data_guard_block(
    manager: PositionManagerEngine, context: Any, store: StoreClient
) -> None:
    """Invariant 14: a feed outage is what triggers the escalation, and the same outage
    is what would hold it. If the hold applied here, `close_all` would be blocked by the
    exact condition it exists to answer."""
    store.write_order(resting_entry(context, age_s=1))

    state = build_state(context, blocked_by="data_guard", close_intent=True)
    data = manager.process(context, state).data

    assert data[HOLD_REASON_FIELD] is None
    assert data[ORDERS_FIELD][0]["status"] == OrderStatus.CANCELLED.value


# --------------------------------------------------------------------------- #
# Barriers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("low", "high", "barrier"),
    [
        ("97.51", "101.98", Barrier.STOP),
        ("97.52", "101.98", Barrier.TARGET),
        ("97.52", "101.96", None),
        ("97.51", "101.96", Barrier.STOP),
        ("97.515", "101.96", Barrier.STOP),
        ("97.52", "101.97", Barrier.TARGET),
    ],
    ids=[
        "both touched resolves to stop",
        "target only",
        "neither",
        "stop only",
        "a print exactly at the stop is a touch",
        "a print exactly at the target is a touch",
    ],
)
def test_both_barriers_in_one_tick_resolve_to_stop(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
    low: str,
    high: str,
    barrier: str | None,
) -> None:
    """The ambiguity, resolved the way the labels resolve it.

    Stop is 97.515 and target is 101.97 on a 99.00 entry. Within one tick the order of
    two prints is unknown; resolving to `target` would count as a win a trade that may
    well have stopped out first. Resolving to `stop` cannot flatter the strategy, and it
    keeps the live outcome and the label computed the same way — which is the only thing
    that makes the backtest comparable to the live record.

    **The last two cases are the boundary itself, and they are here because a sweep found
    nothing asking for it.** The first four straddle each barrier by a cent and never land
    on one, so `<=` and `<` were indistinguishable across all forty tests in this file.
    The comparison has to be inclusive, and not as a matter of taste:
    `research/labelling.py:343-344` computes the training label with `high >= target_price`
    and `low <= stop_price`, so a strict engine would disagree with the label on exactly
    the bars that touch — which would break the one property the paragraph above rests on.
    """
    store.write_position(open_position(context))
    traded(kraken, context, [low, high])
    state = build_state(context, previous_now=one_minute_ago(context))

    triggered = manager.process(context, state).data[TRIGGERED_FIELD]

    assert [entry["barrier"] for entry in triggered] == ([] if barrier is None else [barrier])


def test_a_pair_that_did_not_trade_triggers_no_price_barrier(
    manager: PositionManagerEngine, context: Any, store: StoreClient
) -> None:
    """Absent is not zero, and spec 85's `TradeRange` refuses a zero count so the pair is
    simply missing. A range of `{"low": 0, "high": 0}` would tell this engine the market
    traded at zero and stop every position in the book."""
    store.write_position(open_position(context))
    state = build_state(context, previous_now=one_minute_ago(context))
    assert state["market_sensor"]["trade_ranges"] == {}, "no trades, so no range"

    assert manager.process(context, state).data[TRIGGERED_FIELD] == []


@pytest.mark.parametrize(
    ("timeout_in_s", "fires"),
    [(0, True), (1, False)],
    ids=["at the timeout it fires", "one second short does not"],
)
def test_the_timeout_fires_at_its_moment_and_not_before(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    timeout_in_s: int,
    fires: bool,
) -> None:
    """`context.now >= timeout_at`, and the boundary is inclusive because the timeout is
    a deadline rather than a duration to exceed. Needs no trade at all: it is arithmetic
    over the injected clock, which is why it is the one barrier a silent pair can hit."""
    store.write_position(open_position(context, timeout_in_s=timeout_in_s))

    triggered = manager.process(context, build_state(context)).data[TRIGGERED_FIELD]

    assert [entry["barrier"] for entry in triggered] == ([Barrier.TIMEOUT] if fires else [])


def test_a_touched_barrier_wins_over_an_elapsed_timeout(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
) -> None:
    """Both are true and the market's answer is the real one.

    A position that hit its stop *and* ran out of time exited on the stop: that is what
    happened, and `trades.outcome` is a record of what happened. Recording `timeout`
    would put a trade that lost 1.5% into the bucket research uses to ask whether the
    horizon is too long.
    """
    store.write_position(open_position(context, timeout_in_s=0))
    traded(kraken, context, ["90.00"])
    state = build_state(context, previous_now=one_minute_ago(context))

    triggered = manager.process(context, state).data[TRIGGERED_FIELD]

    assert [entry["barrier"] for entry in triggered] == [Barrier.STOP]


# --------------------------------------------------------------------------- #
# Marking
# --------------------------------------------------------------------------- #


def test_a_position_is_marked_at_the_bid(
    manager: PositionManagerEngine, context: Any, store: StoreClient
) -> None:
    """The bid is what a sale would receive. The ask would value every holding at a
    price nobody is offering to pay, which overstates equity on every tick and
    understates the drawdown engine 17 acts on."""
    store.write_position(open_position(context))

    data = manager.process(context, build_state(context)).data
    position = data[POSITIONS_FIELD][0]

    assert Decimal(position["last_price"]) == Decimal("99.99")
    assert Decimal(position["unrealised_pnl"]) == Decimal("10") * (
        Decimal("99.99") - LIMIT
    )
    assert Decimal(data[POSITIONS_VALUE_FIELD]) == Decimal("10") * Decimal("99.99")


def test_the_totals_are_absent_and_not_zero_when_a_mark_could_not_be_taken(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
) -> None:
    """A partial sum is worse than no sum.

    Engine 19 would write it into `equity_snapshots` as the account's whole value while
    `peak_equity` kept the real figure, and the difference is a drawdown engine 17 acts
    on — a circuit breaker firing on a quote that did not arrive. Absent makes engine 19
    skip the row, which is what its own docstring says it does.
    """
    store.write_position(open_position(context))
    kraken.set_order_book("BTC/USD", bids=[("60000", "1")], asks=[("60001", "1")])
    store.write_position(
        PositionRow(
            **{
                **open_position(context, position_id="pos-2").model_dump(),
                "pair": "BTC/USD",
                "base": "BTC",
                "quote": "USD",
            }
        )
    )

    data = manager.process(context, build_state(context)).data

    assert POSITIONS_VALUE_FIELD not in data, "BTC/USD has no quote, so there is no total"
    assert UNREALISED_PNL_FIELD not in data
    assert len(data[POSITIONS_FIELD]) == 2, "both are still published and still managed"


def test_a_position_opened_by_this_ticks_fill_is_counted_in_the_portfolio_value(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    kraken: FakeKrakenWithStream,
) -> None:
    """A position that exists only because of this tick's fill still has value.

    Found by a mutation that deleted the `value +=` in the fills loop and survived all
    forty tests: every marking test used a position the store already held, so nothing
    asked what the totals do with a brand-new one. Left out, engine 19 writes an
    `equity_snapshots` row short by the whole notional of every position opened that
    tick, `peak_equity` keeps the real figure, and the difference is a drawdown engine 17
    acts on — a breaker firing on a position that was just opened successfully.

    It is valued at what was paid rather than re-marked at the bid, which is why the
    expectation is `qty x entry_price` and the unrealised total is exactly zero: a
    position that has existed for no time has made and lost nothing.
    """
    store.write_order(resting_entry(context))
    traded(kraken, context, ["98.00"])

    data = manager.process(context, build_state(context)).data

    assert len(data[POSITIONS_FIELD]) == 1, "the fill became a position"
    assert Decimal(data[POSITIONS_VALUE_FIELD]) == Decimal("10") * LIMIT
    assert Decimal(data[UNREALISED_PNL_FIELD]) == 0


def test_a_position_with_no_quote_carries_no_last_price(
    manager: PositionManagerEngine, context: Any, store: StoreClient, kraken: Any
) -> None:
    """Per position, the same rule as the totals: absent, never a stale or copied price.
    A `last_price` carried from a previous tick is a fabricated mark, and the console
    renders it as if it were current."""
    store.write_position(open_position(context))
    kraken._quotes.clear()

    position = manager.process(context, build_state(context)).data[POSITIONS_FIELD][0]

    assert "last_price" not in position
    assert "unrealised_pnl" not in position


# --------------------------------------------------------------------------- #
# `close_intent`
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("close_intent", "cancelled"),
    [(True, True), (False, False)],
    ids=["close_intent cancels it", "an ordinary tick does not"],
)
def test_close_intent_cancels_a_fresh_entry_inside_its_window(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    close_intent: bool,
    cancelled: bool,
) -> None:
    """Invariant 8: a `close_all` cancels every resting entry **immediately, regardless
    of that window**, before positions are closed.

    An uncancelled post-only limit is not a position, so it survives a liquidation and
    can fill minutes later — re-opening exposure after the emergency stop was pulled. The
    entry here is one second old, so nothing but `close_intent` could cancel it.
    """
    store.write_order(resting_entry(context, age_s=1))

    data = manager.process(context, build_state(context, close_intent=close_intent)).data

    assert (len(data[ORDERS_FIELD]) == 1) is cancelled
    assert data[ENTRY_ORDERS_CANCELLED_FIELD] is cancelled


def test_the_flag_is_false_while_an_entry_the_client_will_not_report_on_still_rests(
    manager: PositionManagerEngine, context: Any, store: StoreClient, kraken: Any
) -> None:
    """Invariant 3 and the kill switch's retry, together.

    An order the client cannot answer for is not an order that is gone. Reporting
    `entry_orders_cancelled: True` would let the orchestrator clear `close_intent` and
    mark the `close_all` row consumed with a live buy on the book — spec 81 fixed the
    truthiness half of this and this is the other half.
    """
    store.write_order(resting_entry(context))
    traded(kraken, context, ["98.00"])  # it filled...
    kraken.fail("trade_volume")  # ...and the broker cannot price the fee, so it raises

    result = manager.process(context, build_state(context, close_intent=True))

    assert result.status is EngineStatus.ERROR
    assert result.data[ENTRY_ORDERS_CANCELLED_FIELD] is False


def test_the_flag_is_false_while_the_client_answers_for_fewer_orders_than_it_was_asked(
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    broker: PaperBroker,
) -> None:
    """Invariant 3 again, through the branch the test above does not reach.

    There are two ways the client can fail to say where an order stands, and they are
    different branches three lines apart. The test above drives the one where it
    **raises**; this one drives the one where it **answers, and the order is not in the
    answer**. A mutation deleting `still_resting = True` from the second survived all
    forty tests, because the name of the first test covers both readings and nothing
    exercised the second.

    The paper broker cannot produce this — it raises on a `userref` it does not know,
    which is `test_an_unknown_userref_raises_rather_than_answering_nothing` over in
    `tests/clients/paper/`. A live exchange returning a short list is the case this
    guards, and an order missing from the answer is not an order that is gone.
    """
    store.write_order(resting_entry(context))
    context.clients.kraken = _BrokerAnswering(broker, query="reports on nothing")

    data = manager.process(context, build_state(context, close_intent=True)).data

    assert data[ENTRY_ORDERS_CANCELLED_FIELD] is False
    assert data[ORDERS_FIELD] == []


def test_the_completion_flag_is_the_literal_true_the_orchestrator_requires(
    manager: PositionManagerEngine, context: Any
) -> None:
    """Spec 81: the orchestrator accepts only the boolean `True`, because `bool("false")`
    is `True` and a text-shaped flag would clear a liquidation. Asserted on the type as
    well as the value, so a publisher that started emitting `"true"` is caught here
    rather than by the orchestrator silently accepting it."""
    data = manager.process(context, build_state(context, close_intent=True)).data

    assert data[ENTRY_ORDERS_CANCELLED_FIELD] is True


@pytest.mark.parametrize("value", ["true", 1, [], None])
def test_a_close_intent_that_is_not_the_boolean_true_is_not_a_liquidation(
    manager: PositionManagerEngine, context: Any, store: StoreClient, value: Any
) -> None:
    """The same fail-closed reading applied from the other side. Anything text-shaped
    arriving here would start liquidating an account nobody asked to close, and the
    entry below is one second old so only a liquidation could touch it."""
    store.write_order(resting_entry(context, age_s=1))
    state = build_state(context)
    state["system"]["close_intent"] = value

    assert manager.process(context, state).data[ORDERS_FIELD] == []


# --------------------------------------------------------------------------- #
# This tick's placement
# --------------------------------------------------------------------------- #


def test_an_entry_placed_this_tick_is_seen_before_engine_nineteen_records_it(
    manager: PositionManagerEngine, context: Any, broker: PaperBroker
) -> None:
    """Engine 19 writes at the **end** of the manage chain, so an entry engine 18 placed
    earlier in this tick is not in the store yet.

    Without the second source a `close_all` arriving on the same tick as a placement
    reports every entry cancelled while one is resting, and the orchestrator clears
    `close_intent` with a live post-only buy on the book — which invariant 8 names as
    the uncancelled order that survives a liquidation and re-opens exposure.
    """
    from acsoe.clients.kraken.contracts import OrderRequest

    run = __import__("acsoe.platform.aio", fromlist=["run_blocking"]).run_blocking
    run(
        broker.add_order(
            OrderRequest(
                pair=PAIR,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                qty=Decimal("10"),
                limit_price=LIMIT,
                post_only=True,
                userref=USERREF,
            )
        )
    )
    state = build_state(context, close_intent=True)
    state["execution"] = {
        "orders": [
            {
                "userref": USERREF,
                "pair": PAIR,
                "intent": OrderIntent.ENTRY.value,
                "status": OrderStatus.RESTING.value,
                "qty": "10",
                "limit_price": format(LIMIT, "f"),
                "placed_at": to_micros(context.now),
            }
        ]
    }

    data = manager.process(context, state).data

    assert [row["status"] for row in data[ORDERS_FIELD]] == [OrderStatus.CANCELLED.value]
    assert data[ENTRY_ORDERS_CANCELLED_FIELD] is True


def test_an_entry_in_both_the_store_and_this_ticks_payload_is_settled_once(
    manager: PositionManagerEngine, context: Any, store: StoreClient
) -> None:
    """The two sources overlap on the tick after a placement, and one order is one order.

    Engine 18 publishes the placement, engine 19 records it at the end of that tick, and
    on the next tick engine 21 sees the same `userref` from both `store.resting_orders()`
    and `state["execution"]`. `_resting_entries` dedupes on `userref`; a mutation
    removing that check survived all forty tests, because every test supplied exactly one
    of the two sources.

    Settled twice, one order produces two cancel rows for engine 19 to write against one
    `userref` — or, when it filled, **two positions out of one fill**, which double-counts
    the account's exposure everywhere downstream and would let engine 11's per-pair
    refusal be the only thing standing between it and a third.
    """
    store.write_order(resting_entry(context, age_s=WINDOW_S + 1))
    state = build_state(context)
    state["execution"] = {
        "orders": [
            {
                "userref": USERREF,
                "pair": PAIR,
                "intent": OrderIntent.ENTRY.value,
                "status": OrderStatus.RESTING.value,
                "qty": "10",
                "limit_price": format(LIMIT, "f"),
                "placed_at": to_micros(context.now) - (WINDOW_S + 1) * MICROSECONDS_PER_SECOND,
            }
        ]
    }

    data = manager.process(context, state).data

    assert [row["userref"] for row in data[ORDERS_FIELD]] == [USERREF], "one order, one row"


def test_no_execution_payload_at_all_is_an_ordinary_tick(
    manager: PositionManagerEngine, context: Any
) -> None:
    """Fourteen ticks in fifteen the opportunity chain did not run. An absent
    `state["execution"]` is the normal case, not a failure."""
    result = manager.process(context, build_state(context))

    assert result.status is EngineStatus.OK
    assert result.data[ORDERS_FIELD] == []
    assert result.data[POSITIONS_FIELD] == []
