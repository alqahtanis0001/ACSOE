"""Spec 88 — the paper broker.

**Nothing here is a mock of A's surface.** `OrderRequest`, `OrderAck` and `OrderState`
are A's real models from `clients/kraken/contracts.py`, with their real validators, so a
fill this broker constructs is refused here for the same reason the exchange's would be:
an average price on an order that filled nothing, a fee on an order that paid none, a
`closed_at` on something still resting. The store is a real `StoreClient` on a migrated
temporary database and the wrapped client is C's real `FakeKrakenClient`. The subclass
below adds only the stream half, which the fake does not have and the broker forwards —
the same thing `tests/engines/test_risk.py` does, for the same reason.

The seam that needed proving is the trade one, and it is the last test in the file:
engine 3 and the broker must agree about which trades happened on a tick. They agree
because they read one source rather than because two implementations were written to
match, and `test_the_broker_and_engine_three_see_the_same_trades_on_one_tick` runs the
real engine 3 to say so.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.harness.fake_kraken import FakeKrakenClient

from acsoe.clients.kraken.contracts import (
    OrderAckStatus,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    QuoteTick,
    TradeTick,
    to_micros,
)
from acsoe.clients.paper.broker import PaperBroker, PaperBrokerError
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import OrderIntent, OrderRow
from acsoe.clients.store.contracts import OrderStatus as RowStatus
from acsoe.platform.aio import run_blocking

PAIR = "SOL/USD"
OTHER = "BTC/USD"

#: A $100 pair with a one-cent spread, set on the fake through `set_order_book` so the
#: broker reads the fake exchange's own book rather than a number this file invented.
BID = "99.99"
ASK = "100.00"

#: Tier 3. Standing rule 8 of the Phase 6 task list: everything that drives a trade runs
#: at tier 3, and every assertion that turns on a fee names it. Maker 0.22%, taker 0.38%
#: as decimal ratios, which is the convention `FeeTierSnapshot` validates.
MAKER = "0.0022"
TAKER = "0.0038"

USERREF = 4_242


class FakeKrakenWithStream(FakeKrakenClient):
    """C's fake plus the stream half, which the broker forwards and engine 3 reads.

    `recent_trades` is a **window, not a queue** — it does not clear — because that is
    what `ws.py` documents and what engine 3 depends on to rebuild one bar across the
    fifteen ticks it spans. A fake that drained here would make the broker look correct
    against behaviour the real client does not have.
    """

    def __init__(self, *, now: int = 0) -> None:
        super().__init__(now=now)
        self._trades: list[TradeTick] = []
        self._quotes: dict[str, QuoteTick] = {}
        self.drain_trades_calls = 0

    def add_trade(self, pair: str, price: str, at: datetime) -> None:
        self._trades.append(
            TradeTick(pair=pair, ts=at, price=Decimal(price), qty=Decimal("1"))
        )

    def recent_trades(self) -> tuple[TradeTick, ...]:
        return tuple(self._trades)

    def drain_trades(self) -> tuple[TradeTick, ...]:
        self.drain_trades_calls += 1
        trades = tuple(self._trades)
        self._trades.clear()
        return trades

    def set_quote(self, pair: str, *, bid: str, ask: str, at: datetime) -> None:
        self._quotes[pair] = QuoteTick(
            pair=pair, ts=at, bid=Decimal(bid), ask=Decimal(ask)
        )

    def latest_quote(self, pair: str) -> QuoteTick | None:
        return self._quotes.get(pair)


@pytest.fixture
def kraken() -> FakeKrakenWithStream:
    client = FakeKrakenWithStream()
    client.set_balances({"USD": "5000.00"})
    client.set_fee_tier(tier=3, maker_fee_pct=MAKER, taker_fee_pct=TAKER)
    client.set_order_book(PAIR, bids=[(BID, "500")], asks=[(ASK, "500")])
    return client


@pytest.fixture
def broker(
    kraken: FakeKrakenWithStream, store: StoreClient, paper_config: Any, fixed_clock: Any
) -> PaperBroker:
    return PaperBroker(kraken, store=store, config=paper_config, clock=fixed_clock)


def buy(
    *, limit: str = "99.00", userref: int = USERREF, pair: str = PAIR, post_only: bool = True
) -> OrderRequest:
    """A post-only limit buy, which is the only entry invariant 8 permits."""
    return OrderRequest(
        pair=pair,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=Decimal("10"),
        limit_price=Decimal(limit),
        post_only=post_only,
        userref=userref,
    )


def sell(*, qty: str = "10", userref: int = USERREF + 1, pair: str = PAIR) -> OrderRequest:
    """A market sell, which is the only order invariant 14's liquidation permits."""
    return OrderRequest(
        pair=pair,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        qty=Decimal(qty),
        post_only=False,
        userref=userref,
    )


def recorded(
    request: OrderRequest,
    *,
    status: RowStatus,
    placed_at: int,
    filled_qty: str = "0",
    avg_fill_price: str | None = None,
    fee: str | None = None,
    closed_at: int | None = None,
) -> OrderRow:
    """Engine 19's row for an order, as it would land in the store.

    Written here by the test because engine 19 is C's and is not in this chain. The
    fields are the store contract's, so a shape engine 19 could not produce is refused
    by `OrderRow` before the broker ever sees it.
    """
    return OrderRow(
        userref=request.userref,
        order_id=f"paper-{request.userref}",
        run_id="test-run",
        cycle_id=1,
        pair=request.pair,
        side=request.side.value,
        intent=OrderIntent.ENTRY if request.side is OrderSide.BUY else OrderIntent.EXIT,
        order_type=request.order_type.value,
        oflags="post" if request.post_only else "",
        status=status,
        qty=request.qty,
        limit_price=request.limit_price,
        filled_qty=Decimal(filled_qty),
        avg_fill_price=None if avg_fill_price is None else Decimal(avg_fill_price),
        fee=None if fee is None else Decimal(fee),
        placed_at=placed_at,
        closed_at=closed_at,
        updated_at=placed_at,
    )


# --------------------------------------------------------------------------- #
# The first scope limit: no transport call from any order method
# --------------------------------------------------------------------------- #


def test_no_order_method_is_ever_forwarded_to_the_real_client() -> None:
    """Spec 88's first scope limit, checked against the source rather than a run.

    A behavioural test can only prove the four order calls were not forwarded *on the
    paths it took*. This asserts the names do not appear against `self._real` anywhere
    in the module, which is the whole claim. The real client's order methods refuse
    until Phase 8, so a forward would not silently trade — it would fail loudly in paper
    mode, which is a different defect and an equally bad one.
    """
    source = Path("src/acsoe/clients/paper/broker.py").read_text(encoding="utf-8")

    for call in ("add_order", "cancel_order", "query_orders", "open_orders"):
        assert f"self._real.{call}" not in source, f"{call} must never reach the exchange"


def test_the_fake_is_never_asked_to_place_anything(
    broker: PaperBroker, kraken: FakeKrakenWithStream
) -> None:
    """The behavioural half. C's fake records every call it serves, so an order that
    leaked to it would show up in `calls` — and the fake has no order methods at all, so
    it would have raised first."""
    run_blocking(broker.add_order(buy()))

    assert "add_order" not in kraken.calls


# --------------------------------------------------------------------------- #
# Placement
# --------------------------------------------------------------------------- #


def test_a_post_only_buy_below_the_ask_rests(broker: PaperBroker) -> None:
    ack = run_blocking(broker.add_order(buy(limit="99.00")))

    assert ack.status is OrderAckStatus.RESTING
    assert ack.reason is None, "A's OrderAck: a reason belongs to a rejection"


def test_a_post_only_buy_at_the_ask_is_rejected_and_names_the_cause(
    broker: PaperBroker,
) -> None:
    """Invariant 8: Kraken cancels a post-only order that would cross, and that is the
    intended behaviour. The reason is asserted because A's `OrderAck` requires one on a
    rejection — "a rejection with no cause cannot be told from a rejection nobody
    recorded" — and because C maps it to operator prose."""
    ack = run_blocking(broker.add_order(buy(limit=ASK)))

    assert ack.status is OrderAckStatus.REJECTED
    assert "post-only" in (ack.reason or "")
    assert ASK in (ack.reason or "")


def test_a_rejected_placement_rests_nothing(
    broker: PaperBroker, kraken: FakeKrakenWithStream, fixed_clock: Any
) -> None:
    """The rejection is not a resting order under another name.

    Without this, "rejected" could be a label on an order the simulator went on to fill
    the moment a trade printed below it — which is the crossing entry the post-only flag
    exists to prevent, arriving one tick later.
    """
    run_blocking(broker.add_order(buy(limit=ASK)))
    kraken.add_trade(PAIR, "50.00", fixed_clock.now() + timedelta(seconds=1))

    with pytest.raises(PaperBrokerError, match="no order with userref"):
        run_blocking(broker.query_orders([USERREF]))


def test_a_second_placement_under_one_userref_is_refused(broker: PaperBroker) -> None:
    """Invariant 8 makes `userref` the idempotency token and requires the caller to
    check before placing. A second placement under one is a defect, not a retry, and
    returning the first ack would hide it at the only place it is visible."""
    run_blocking(broker.add_order(buy()))

    with pytest.raises(PaperBrokerError, match="already been placed"):
        run_blocking(broker.add_order(buy()))


def test_a_limit_order_that_is_not_post_only_is_refused(broker: PaperBroker) -> None:
    """This system places post-only entries and taker exits and nothing else. Simulating
    a third behaviour would be a capability nothing asked for, and spec 88's scope limit
    forbids simulating live-only behaviour beyond what it lists."""
    with pytest.raises(PaperBrokerError, match="not post-only"):
        run_blocking(broker.add_order(buy(post_only=False)))


# --------------------------------------------------------------------------- #
# The resting fill, through the broker rather than through `fills.py`
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("trade_price", "expect_filled"),
    [("98.99", True), ("99.00", False)],
    ids=["one cent below fills", "a touch does not"],
)
def test_a_resting_entry_fills_only_on_a_trade_strictly_below_it(
    broker: PaperBroker,
    kraken: FakeKrakenWithStream,
    fixed_clock: Any,
    trade_price: str,
    expect_filled: bool,
) -> None:
    """Spec 88's boundary, driven all the way through the broker.

    `test_fills.py` pins the rule; this pins that the broker applies it, with the trade
    arriving through the stream the way one really does and the fee coming from the
    fake's tier 3 rather than from a constant.
    """
    run_blocking(broker.add_order(buy(limit="99.00")))
    kraken.add_trade(PAIR, trade_price, fixed_clock.now() + timedelta(seconds=1))

    state = run_blocking(broker.query_orders([USERREF]))[0]

    assert (state.status is OrderStatus.FILLED) is expect_filled
    if expect_filled:
        assert state.avg_fill_price == Decimal("99.00")
        assert state.filled_qty == Decimal("10")
        assert state.fee == Decimal("99.00") * Decimal("10") * Decimal(MAKER)
    else:
        assert state.avg_fill_price is None, "A's OrderState: no fill, no price"
        assert state.fee == 0


def test_a_trade_printed_before_the_order_existed_does_not_fill_it(
    broker: PaperBroker, kraken: FakeKrakenWithStream, fixed_clock: Any
) -> None:
    """Invariant 10, arriving through the simulator instead of through a feature.

    Engine 3 reads the trade window in the guard chain and engine 18 places in the
    opportunity chain, so by the time an order exists the broker can already see trades
    that printed before it. Filling on one is look-ahead: the order would be filled on
    the past, at a price the strategy chose after seeing it.
    """
    kraken.add_trade(PAIR, "50.00", fixed_clock.now() - timedelta(seconds=1))

    run_blocking(broker.add_order(buy(limit="99.00")))
    state = run_blocking(broker.query_orders([USERREF]))[0]

    assert state.status is OrderStatus.RESTING


def test_a_trade_on_another_pair_does_not_fill_this_one(
    broker: PaperBroker, kraken: FakeKrakenWithStream, fixed_clock: Any
) -> None:
    run_blocking(broker.add_order(buy(limit="99.00")))
    kraken.add_trade(OTHER, "1.00", fixed_clock.now() + timedelta(seconds=1))

    assert run_blocking(broker.query_orders([USERREF]))[0].status is OrderStatus.RESTING


def test_an_unknown_userref_raises_rather_than_answering_nothing(
    broker: PaperBroker,
) -> None:
    """Invariant 3, and A's `OrderClientProtocol` says it about this surface in as many
    words: a call that cannot be completed raises, because an absence of news would tell
    engine 21 there was nothing resting to cancel."""
    with pytest.raises(PaperBrokerError, match="no order with userref"):
        run_blocking(broker.query_orders([9_999]))


# --------------------------------------------------------------------------- #
# The market sell
# --------------------------------------------------------------------------- #


def test_a_market_sell_walks_the_bids_and_fills_at_the_weighted_average(
    broker: PaperBroker, kraken: FakeKrakenWithStream
) -> None:
    """Two units at 100 and three at 99 is 99.40 for five, hand-computed.

    The taker rate is used and not the maker one: a market order always takes liquidity
    and invariant 5's friction assumes exactly this on the exit.
    """
    kraken.set_order_book(PAIR, bids=[("100.00", "2"), ("99.00", "5")], asks=[(ASK, "500")])

    ack = run_blocking(broker.add_order(sell(qty="5")))
    state = run_blocking(broker.query_orders([ack.userref]))[0]

    assert ack.status is OrderAckStatus.FILLED
    assert state.avg_fill_price == Decimal("99.40")
    assert state.fee == Decimal("99.40") * Decimal("5") * Decimal(TAKER)


def test_a_market_sell_into_a_thin_book_still_fills_in_full(
    broker: PaperBroker, kraken: FakeKrakenWithStream
) -> None:
    """Depth exhausted: the remainder is priced at the worst fetched level, never
    dropped. A partial here would leave a position half-closed with nothing recording
    the other half — during a liquidation, which is the one time that cannot happen."""
    kraken.set_order_book(PAIR, bids=[("100.00", "1")], asks=[(ASK, "500")])

    ack = run_blocking(broker.add_order(sell(qty="3")))
    state = run_blocking(broker.query_orders([ack.userref]))[0]

    assert state.filled_qty == Decimal("3")
    assert state.avg_fill_price == Decimal("100.00")


def test_a_market_buy_is_refused(broker: PaperBroker) -> None:
    """Invariant 8: never chase with a market order. The only market order this system
    places is a taker exit and every exit is a sell."""
    request = OrderRequest(
        pair=PAIR,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        qty=Decimal("1"),
        post_only=False,
        userref=USERREF,
    )

    with pytest.raises(PaperBrokerError, match=r"every.*exit is a sell"):
        run_blocking(broker.add_order(request))


# --------------------------------------------------------------------------- #
# Fees are never invented — spec 88 and spec 93's shared scope limit
# --------------------------------------------------------------------------- #


def test_a_fill_with_no_fee_tier_refuses_rather_than_choosing_a_rate(
    broker: PaperBroker, kraken: FakeKrakenWithStream
) -> None:
    """The case that matters is a liquidation during an outage, and both spec 88 and
    spec 93 say the same thing about it from either side: **escalate, do not choose
    one.** So the broker raises and the message says so, rather than reaching for the
    last tier it saw — which invariant 2 does not retain, deliberately."""
    kraken.fail("trade_volume")

    with pytest.raises(PaperBrokerError, match="escalate"):
        run_blocking(broker.add_order(sell()))


def test_the_broker_holds_no_fee_rate_of_its_own() -> None:
    """`AGENTS.md`, first paragraph: any fee percentage you remember is stale.

    A constant that happened to match tier 3 would satisfy every fee assertion in this
    file, so the absence is checked against the source.

    **Docstrings are excluded and that is not a loophole.** Both modules explain the
    ratio convention by quoting "0.22% is 0.0022", which is documentation doing its job;
    the thing that must not exist is a *value*. So the check walks the AST and looks at
    every literal that is not a docstring — which is strictly narrower than a text
    search and catches the one shape a text search would miss too, a rate written as a
    bare float rather than as a string.
    """
    import ast

    for module in ("fills.py", "broker.py"):
        tree = ast.parse(Path(f"src/acsoe/clients/paper/{module}").read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        literals = {
            str(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and id(node) not in docstrings
        }
        for remembered in ("0.0022", "0.0038", "0.004", "0.008", "0.22", "0.38"):
            assert remembered not in literals, (
                f"{module} carries {remembered} as a literal, and a fee is fetched at "
                "runtime or the fill is not priced at all"
            )


# --------------------------------------------------------------------------- #
# Cancellation
# --------------------------------------------------------------------------- #


def test_cancelling_a_resting_entry_closes_it(broker: PaperBroker, fixed_clock: Any) -> None:
    run_blocking(broker.add_order(buy()))

    state = run_blocking(broker.cancel_order(USERREF))

    assert state.status is OrderStatus.CANCELLED
    assert state.filled_qty == 0
    assert state.closed_at == to_micros(fixed_clock.now())


def test_cancelling_an_order_that_already_filled_reports_the_fill(
    broker: PaperBroker, kraken: FakeKrakenWithStream, fixed_clock: Any
) -> None:
    """A cancel that arrives after the fill must not erase it.

    Engine 21 cancels a stale entry on elapsed time alone and does not know whether the
    fill landed first. Reporting `cancelled` here would lose a real position: the money
    is spent and nothing would record it.
    """
    run_blocking(broker.add_order(buy(limit="99.00")))
    kraken.add_trade(PAIR, "98.00", fixed_clock.now() + timedelta(seconds=1))

    state = run_blocking(broker.cancel_order(USERREF))

    assert state.status is OrderStatus.FILLED
    assert state.filled_qty == Decimal("10")


def test_cancelling_an_unknown_order_raises(broker: PaperBroker) -> None:
    with pytest.raises(PaperBrokerError, match="no order with userref"):
        run_blocking(broker.cancel_order(9_999))


# --------------------------------------------------------------------------- #
# The store is the record, not an in-memory book
# --------------------------------------------------------------------------- #


def test_a_restarted_broker_still_knows_about_a_recorded_order(
    kraken: FakeKrakenWithStream,
    store: StoreClient,
    paper_config: Any,
    fixed_clock: Any,
) -> None:
    """Spec 88 step 2: resting orders are the store's rows.

    A second `PaperBroker` over the same store is a restart with no shared state at all.
    It finds the entry, because engine 19 wrote it — an in-memory book would have lost
    it and the system would hold a position whose entry order it had forgotten, which is
    the exact failure `userref` idempotency exists to prevent.
    """
    request = buy(limit="99.00")
    store.write_order(
        recorded(request, status=RowStatus.RESTING, placed_at=to_micros(fixed_clock.now()))
    )

    restarted = PaperBroker(kraken, store=store, config=paper_config, clock=fixed_clock)
    state = run_blocking(restarted.query_orders([USERREF]))[0]

    assert state.status is OrderStatus.RESTING


def test_a_recorded_order_wins_over_this_ticks_copy(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """Engine 19 is the record and `_pending` is only the gap before it writes.

    Two answers to one question is the shape where a cancel loop and a fill check
    disagree, and engine 21 runs both on one tick. So once the row exists it is the
    answer, and the broker's own copy is dropped.
    """
    request = buy(limit="99.00")
    run_blocking(broker.add_order(request))
    store.write_order(
        recorded(
            request,
            status=RowStatus.CANCELLED,
            placed_at=to_micros(fixed_clock.now()),
            closed_at=to_micros(fixed_clock.now()),
        )
    )

    assert run_blocking(broker.query_orders([USERREF]))[0].status is OrderStatus.CANCELLED


def test_open_orders_reports_what_is_resting_and_nothing_terminal(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """One code path with `query_orders`, deliberately: engine 21 asks both on one tick
    and two readings of "is this order still open" is where they would disagree."""
    placed_at = to_micros(fixed_clock.now())
    store.write_order(recorded(buy(limit="99.00"), status=RowStatus.RESTING, placed_at=placed_at))
    store.write_order(
        recorded(
            buy(limit="99.00", userref=USERREF + 9),
            status=RowStatus.CANCELLED,
            placed_at=placed_at,
            closed_at=placed_at,
        )
    )

    open_now = run_blocking(broker.open_orders())

    assert [state.userref for state in open_now] == [USERREF]


def test_open_orders_reports_an_order_accepted_this_tick_that_the_store_has_not_seen(
    broker: PaperBroker, store: StoreClient
) -> None:
    """The gap between placing and recording, which is every tick anything is placed.

    Engine 19 writes at the **end** of the manage chain, so between `add_order` and that
    write the broker's `_pending` is the only thing that knows the order exists. Until
    2026-09-16 `open_orders()` was derived from `store.resting_orders()` alone and
    answered "nothing is open" while a post-only buy sat on the book.

    That is invariant 3's shape, and it is also a difference between paper and live: a
    real exchange lists an order the moment it rests, whatever this system has recorded.
    The broker exists so engines 18, 21 and 22 run the same code in both modes, and a
    read that answers differently defeats the point of it.

    The test that was here drove only orders the store already held, which is why it
    could not fail on this. One input differs: nothing is written to the store.
    """
    run_blocking(broker.add_order(buy(limit="99.00")))
    assert store.order_by_userref(USERREF) is None, "engine 19 has not run"

    open_now = run_blocking(broker.open_orders())

    assert [state.userref for state in open_now] == [USERREF]


def test_open_orders_reports_one_order_once_when_both_sources_hold_it(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """The union must not double-count on the tick engine 19 catches up.

    `_lookup` prefers the store's row and drops `_pending`'s copy, so one `userref`
    resolves once — but that is a property of `_lookup`, and `open_orders` builds the
    list of `userref`s before `_lookup` is reached. This is the assertion that says the
    list itself is deduplicated rather than relying on the resolver downstream.
    """
    run_blocking(broker.add_order(buy(limit="99.00")))
    store.write_order(
        recorded(buy(limit="99.00"), status=RowStatus.RESTING, placed_at=to_micros(fixed_clock.now()))
    )

    open_now = run_blocking(broker.open_orders())

    assert [state.userref for state in open_now] == [USERREF]


# --------------------------------------------------------------------------- #
# The ledger
# --------------------------------------------------------------------------- #


def test_the_ledger_is_the_starting_balance_when_nothing_has_filled(
    broker: PaperBroker,
) -> None:
    """`paper.starting_balances` is `{USD: "5000.00"}` in the committed config."""
    assert run_blocking(broker.balance()).balances["USD"] == Decimal("5000.00")


def test_the_real_balance_is_never_fetched_in_paper_mode(
    broker: PaperBroker, kraken: FakeKrakenWithStream
) -> None:
    """Operator ruling 3, 2026-09-16: in paper mode the balance is **always** the ledger,
    whether or not the real fetch works, because no simulated fill spends the real
    account. Calling the real endpoint and discarding the answer would leave a private
    call in the paper path whose result nothing uses, and the first person to "fix" the
    unused value would reintroduce the double count the ruling exists to remove."""
    run_blocking(broker.balance())

    assert "balance" not in kraken.calls


def test_the_ledger_after_a_round_trip_is_exact_to_the_cent(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """Spec 88's acceptance line, at tier 3 and hand-computed.

    Buy 10 at 99.00: 990.00 out, plus 0.22% maker = 2.178, so 992.178.
    Sell 10 at 101.00: 1010.00 in, less 0.38% taker = 3.838, so 1006.162.
    5000.00 - 992.178 + 1006.162 = 5013.984.

    Asserted as an exact `Decimal` equality with no tolerance, which is the point of
    money being `Decimal` at all: a float ledger is wrong in the eighth place on the
    first fill and the error compounds across every trade.
    """
    placed_at = to_micros(fixed_clock.now())
    entry = buy(limit="99.00")
    store.write_order(
        recorded(
            entry,
            status=RowStatus.FILLED,
            placed_at=placed_at,
            filled_qty="10",
            avg_fill_price="99.00",
            fee="2.178",
            closed_at=placed_at,
        )
    )
    exit_order = sell(qty="10")
    store.write_order(
        recorded(
            exit_order,
            status=RowStatus.FILLED,
            placed_at=placed_at,
            filled_qty="10",
            avg_fill_price="101.00",
            fee="3.838",
            closed_at=placed_at,
        )
    )

    assert run_blocking(broker.balance()).balances["USD"] == Decimal("5013.984")


def test_a_restart_rebuilds_the_same_ledger_from_the_store(
    broker: PaperBroker,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
    paper_config: Any,
    fixed_clock: Any,
) -> None:
    """The ledger holds no running total, so there is nothing for a restart to lose.

    A cached balance would be the defect this test exists to forbid: it would survive a
    restart as whatever it was when the process died, and would then diverge from the
    `orders` rows with nothing saying which was right.
    """
    placed_at = to_micros(fixed_clock.now())
    store.write_order(
        recorded(
            buy(limit="99.00"),
            status=RowStatus.FILLED,
            placed_at=placed_at,
            filled_qty="10",
            avg_fill_price="99.00",
            fee="2.178",
            closed_at=placed_at,
        )
    )
    before = run_blocking(broker.balance()).balances["USD"]

    restarted = PaperBroker(kraken, store=store, config=paper_config, clock=fixed_clock)

    assert run_blocking(restarted.balance()).balances["USD"] == before
    assert before == Decimal("5000.00") - Decimal("992.178")


def test_an_unfilled_order_does_not_move_the_ledger(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """A resting entry has spent nothing. Debiting it would size the next candidate
    against money still in the account, which is the conservative direction and still
    wrong: engine 11 would refuse trades it should take, and nothing would say why."""
    store.write_order(
        recorded(buy(limit="99.00"), status=RowStatus.RESTING, placed_at=to_micros(fixed_clock.now()))
    )

    assert run_blocking(broker.balance()).balances["USD"] == Decimal("5000.00")


def test_the_ledger_never_sums_money_in_sql() -> None:
    """`code-standards.md`: money columns are TEXT with a `typeof` check, so SQLite
    would sum them lexicographically or coerce them to floats. The addition happens in
    Python over `Decimal`, and the store read is a row read. Checked against the source
    because a `SUM()` added later would be green on every example in this file — the
    error only appears once two amounts differ in string length."""
    source = Path("src/acsoe/clients/store/client.py").read_text(encoding="utf-8")
    ledger_read = source[source.index("def filled_orders") : source.index("def order_by_userref")]
    sql = [line for line in ledger_read.splitlines() if "SELECT" in line.upper()]

    assert sql, "the ledger read still issues a query, so there is something to check"
    assert not any("SUM(" in line.upper() for line in sql)


# --------------------------------------------------------------------------- #
# Forwarding, and the seam with engine 3
# --------------------------------------------------------------------------- #


def test_every_read_is_the_real_clients_answer_unchanged(
    broker: PaperBroker, kraken: FakeKrakenWithStream
) -> None:
    """Not asserted field by field: the same object, so there is nothing to drift."""
    assert run_blocking(broker.asset_pairs()) == run_blocking(kraken.asset_pairs())
    assert run_blocking(broker.trade_volume()) == run_blocking(kraken.trade_volume())
    assert run_blocking(broker.order_book(PAIR, 10)) == run_blocking(kraken.order_book(PAIR, 10))


class _RecordingStream:
    """Records which attribute the broker reached for, and answers nothing.

    Not a subclass of the fake and not typed against anything: the only question here is
    *which names* the broker touches on the object it wraps, so answering every call with
    an empty tuple is enough and giving realistic answers would only add ways to be wrong.
    """

    def __init__(self) -> None:
        self.touched: list[str] = []

    def __getattr__(self, name: str) -> Any:
        self.touched.append(name)
        return lambda *args: ()


def test_the_broker_forwards_every_member_of_the_stream_protocol(
    store: StoreClient, paper_config: Any, fixed_clock: Any
) -> None:
    """Walks `MarketStreamProtocol` rather than listing its members by hand.

    Asked for by A after measuring the omission this replaces: the broker declared six of
    the protocol's seven stream members and dropped `drain_gaps`. Engine 2 takes gaps with
    `getattr(stream, "drain_gaps", None)` and records none when it is absent, so in paper
    mode — where the broker *is* the stream every engine sees — the archive got no `gap`
    line at all and would have read as continuous across a reconnect. Invariant 11, and it
    disarms the book cutter's refusal to cut a window containing a gap.

    **A test per method cannot find that class of defect**, which is why this one walks the
    protocol. The omission and the missing test have one cause: nobody writes a test for
    the method they forgot. A hand-written list here would be written by the same person
    who wrote the hand-written forwarding.

    Both halves are asserted, because presenting a member and forwarding it are different
    failures: a stub that returned `()` without asking the real client would pass a
    `hasattr` check and would be exactly as silent.
    """
    import inspect

    from acsoe.clients.kraken.contracts import MarketStreamProtocol

    members = set(MarketStreamProtocol.__protocol_attrs__)

    # `__protocol_attrs__` is a private typing detail. If a future version renames it the
    # attribute access would raise, but an *empty* set would make the walk below pass
    # vacuously — a test that checks nothing while staying green is worse than a red one.
    assert "drain_gaps" in members, "the walk is reading the wrong protocol"
    assert len(members) >= 7, f"MarketStreamProtocol shrank unexpectedly: {sorted(members)}"

    for name in sorted(members):
        real = _RecordingStream()
        broker = PaperBroker(real, store=store, config=paper_config, clock=fixed_clock)

        # Asked of the **class**, not the instance: `hasattr` on an instance evaluates a
        # property, which would forward it here and again below and leave the forwarding
        # assertion reading two calls where it expects one.
        assert hasattr(PaperBroker, name), (
            f"the broker does not present `{name}`; in paper mode it is the stream every "
            "engine sees, so a caller reaching for it gets an AttributeError or a silent "
            "getattr fallback"
        )

        declared = inspect.getattr_static(PaperBroker, name)
        if isinstance(declared, property):
            getattr(broker, name)
        else:
            bound = getattr(broker, name)
            required = [
                PAIR
                for parameter in inspect.signature(bound).parameters.values()
                if parameter.default is inspect.Parameter.empty
            ]
            bound(*required)

        assert real.touched == [name], (
            f"`{name}` did not reach the wrapped client: touched {real.touched!r}"
        )


def test_the_broker_never_drains_the_trade_window_itself(
    broker: PaperBroker, kraken: FakeKrakenWithStream, fixed_clock: Any
) -> None:
    """Draining clears the buffer, so a broker that drained would take the trades engine
    3 needs to rebuild the bar.

    Spec 88 assumed engine 3 drains; it reads `recent_trades()`, a rolling window that
    does not clear (`ws.py`). This counts the drains across a full placement and a fill
    resolution — the two places the broker looks at trades — and requires zero.
    """
    kraken.add_trade(PAIR, "98.00", fixed_clock.now() + timedelta(seconds=1))
    run_blocking(broker.add_order(buy(limit="99.00")))
    run_blocking(broker.query_orders([USERREF]))

    assert kraken.drain_trades_calls == 0


def test_the_broker_and_engine_three_see_the_same_trades_on_one_tick(
    broker: PaperBroker,
    kraken: FakeKrakenWithStream,
    engine_context: Any,
    fixed_clock: Any,
) -> None:
    """The seam spec 88 asks for, with **no double on either side**.

    A client cannot read `state`, so it cannot read engine 3's `trade_ranges`. It does
    not need to — both read `recent_trades()` on the same client — and this is the test
    that says the two cannot disagree. The real engine 3 runs against the broker as
    `context.clients.kraken`, exactly as the daemon wires it in paper mode, and its
    published range is compared with the trades the broker will resolve a fill against.
    """
    import dataclasses

    from acsoe.engines.market_sensor.engine import MarketSensorEngine

    for price in ("98.00", "101.00", "99.50"):
        kraken.add_trade(PAIR, price, fixed_clock.now() - timedelta(seconds=30))
    engine_context.clients.kraken = broker
    # `previous_now` is `None` on a process's first tick and engine 3 then publishes no
    # range at all — correctly, since "since the previous tick" has no meaning yet. A
    # second tick is what this seam is about, so the context is given one.
    tick = dataclasses.replace(
        engine_context, previous_now=engine_context.now - timedelta(seconds=60)
    )

    published = MarketSensorEngine().process(tick, {}).data
    seen = [trade.price for trade in broker.recent_trades() if trade.pair == PAIR]

    ranges = published["trade_ranges"]
    assert PAIR in ranges, "engine 3 saw the trades the broker forwarded"
    assert Decimal(str(ranges[PAIR]["low"])) == min(seen)
    assert Decimal(str(ranges[PAIR]["high"])) == max(seen)
    assert ranges[PAIR]["trades"] == len(seen)


# --------------------------------------------------------------------------- #
# What the order *is* — `qty` and `limit_price`, A's spec 84 amendment of
# 2026-09-16
#
# Every `OrderState` this broker builds must describe the order and not only what
# has happened to it. The reason is engine 18's: an order at the exchange that the
# store never recorded could be detected and not *described*, so no row could be
# written and nothing would ever cancel it — unmanaged exposure, and the failure
# invariant 8 exists to prevent.
#
# There are five construction sites in `broker.py` and one test below per shape,
# because a mutation in one of them is invisible to a test that drives another.
# --------------------------------------------------------------------------- #


def test_a_resting_order_describes_its_quantity_as_well_as_its_progress(
    broker: PaperBroker,
) -> None:
    """`qty` is what was asked for; `filled_qty` is what has happened. On a resting
    order they are 10 and 0, which is what makes this assertion able to tell them
    apart — the same two numbers would be indistinguishable on a full fill."""
    run_blocking(broker.add_order(buy(limit="99.00")))

    state = run_blocking(broker.query_orders([USERREF]))[0]

    assert state.status is OrderStatus.RESTING
    assert state.qty == Decimal("10")
    assert state.filled_qty == Decimal("0")
    assert state.limit_price == Decimal("99.00")


def test_a_filled_entry_still_says_what_it_asked_for_and_at_what_limit(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """A recorded order that filled **partially, below its limit** — the one shape
    where all four numbers differ.

    The simulator itself cannot reach it: it fills a resting maker buy in full at its
    own limit, so `qty`, `filled_qty`, `limit_price` and `avg_fill_price` would be
    10, 10, 99.00 and 99.00 and the assertion could not tell which field the broker
    read. Engine 19's row can carry it, a real exchange produces it, and the row is
    built through `OrderRow` so a shape engine 19 could not write is refused before
    the broker sees it.
    """
    request = buy(limit="99.00")
    store.write_order(
        recorded(
            request,
            status=RowStatus.FILLED,
            placed_at=to_micros(fixed_clock.now()) - 1,
            filled_qty="4",
            avg_fill_price="98.50",
            fee="1.00",
            closed_at=to_micros(fixed_clock.now()),
        )
    )

    state = run_blocking(broker.query_orders([USERREF]))[0]

    assert state.qty == Decimal("10")
    assert state.filled_qty == Decimal("4")
    assert state.limit_price == Decimal("99.00")
    assert state.avg_fill_price == Decimal("98.50")


def test_a_market_sell_reports_no_limit_price_because_it_has_none(
    broker: PaperBroker,
) -> None:
    """Presence **is** the statement — A's `OrderState` carries no `order_type`
    precisely so the two cannot disagree. A market order's `limit_price` is `None`
    because the order has none, not because the field was left out, and a consumer
    asking "is this a limit order" reads exactly this."""
    run_blocking(broker.add_order(sell(qty="3")))

    state = run_blocking(broker.query_orders([USERREF + 1]))[0]

    assert state.status is OrderStatus.FILLED
    assert state.qty == Decimal("3")
    assert state.limit_price is None


def test_a_cancel_still_describes_the_order_it_cancelled(broker: PaperBroker) -> None:
    """A cancel changes what has *happened* to an order, never what the order *is*.

    This is the one the kill switch needs: engine 21 cancels a stale entry and engine
    19 records the row, and a cancellation row with no quantity is a record nobody can
    reconcile against the placement.
    """
    run_blocking(broker.add_order(buy(limit="99.00")))

    state = run_blocking(broker.cancel_order(USERREF))

    assert state.status is OrderStatus.CANCELLED
    assert state.qty == Decimal("10")
    assert state.limit_price == Decimal("99.00")


def test_open_orders_describes_every_order_it_lists(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """The surface engine 18's second invariant 8 probe reads.

    Two resting entries with **different** quantities and limits, one from the store
    and one only in `_pending`, so the assertion is about which order each description
    belongs to rather than about "some description was produced".
    """
    other = USERREF + 7
    store.write_order(
        recorded(
            buy(limit="99.00"),
            status=RowStatus.RESTING,
            placed_at=to_micros(fixed_clock.now()) - 1,
        )
    )
    run_blocking(
        broker.add_order(
            OrderRequest(
                pair=PAIR,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                qty=Decimal("2"),
                limit_price=Decimal("97.25"),
                post_only=True,
                userref=other,
            )
        )
    )

    described = {
        state.userref: (state.qty, state.limit_price)
        for state in run_blocking(broker.open_orders())
    }

    assert described == {
        USERREF: (Decimal("10"), Decimal("99.00")),
        other: (Decimal("2"), Decimal("97.25")),
    }


# --------------------------------------------------------------------------- #
# `opened_at` — A's spec 84 amendment, second half
#
# Kraken's `opentm`. It is what lets engine 18 date an order it found at the
# exchange and never recorded, which is what lets engine 21 cancel it in the
# **ordinary** unfilled window instead of one window late. The broker knows the
# placement time exactly, from the injected clock, so there is never a reason for
# it to answer `None`.
# --------------------------------------------------------------------------- #


def test_a_resting_order_is_dated_by_when_it_was_placed_and_not_by_now(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """The witness needs the two times to differ, so the order is one the store
    recorded ten minutes ago rather than one placed on this tick — where `placed_at`
    and `_now()` would be the same number and either source would pass."""
    placed_at = to_micros(fixed_clock.now()) - 600 * 1_000_000
    store.write_order(recorded(buy(limit="99.00"), status=RowStatus.RESTING, placed_at=placed_at))

    state = run_blocking(broker.query_orders([USERREF]))[0]

    assert state.opened_at == placed_at
    assert state.opened_at != to_micros(fixed_clock.now())
    assert state.closed_at is None, "a resting order has not closed"


def test_a_market_fill_opens_and_closes_on_the_same_clock_reading(
    broker: PaperBroker, fixed_clock: Any
) -> None:
    """A's seventh coupling allows `closed_at == opened_at` **on purpose**, and this is
    the case it was allowed for: a marketable order opens and closes inside one tick and
    the simulator has one reading of the injected clock per tick. A stricter bound would
    refuse every simulated taker exit."""
    run_blocking(broker.add_order(sell(qty="3")))

    state = run_blocking(broker.query_orders([USERREF + 1]))[0]

    assert state.opened_at == to_micros(fixed_clock.now())
    assert state.closed_at == state.opened_at


def test_a_cancel_keeps_the_time_the_order_opened(
    broker: PaperBroker, store: StoreClient, fixed_clock: Any
) -> None:
    """A cancel changes what has happened to an order, never when it began.

    The two timestamps must be different numbers for this to mean anything, so the
    order is again one placed ten minutes ago: `opened_at` stays there and `closed_at`
    moves to now.
    """
    placed_at = to_micros(fixed_clock.now()) - 600 * 1_000_000
    store.write_order(recorded(buy(limit="99.00"), status=RowStatus.RESTING, placed_at=placed_at))

    state = run_blocking(broker.cancel_order(USERREF))

    assert state.status is OrderStatus.CANCELLED
    assert state.opened_at == placed_at
    assert state.closed_at == to_micros(fixed_clock.now()) != placed_at


def test_every_order_state_the_broker_builds_carries_an_opening_time(
    broker: PaperBroker, store: StoreClient, kraken: FakeKrakenWithStream, fixed_clock: Any
) -> None:
    """A sweep over all five construction sites rather than one test each.

    `opened_at` is optional on `OrderState` because a real exchange may omit `opentm`,
    and engine 18 has a fail-closed branch for that. **The simulator never has an
    excuse**: it placed the order, or the store recorded when it was placed. A site that
    quietly left the field out would look exactly like an exchange that did not answer,
    and engine 18 would refuse a row it could perfectly well have written.

    Five shapes: a resting pending order, a resting recorded order, a resting order that
    filled, a market fill, and a terminal recorded order.
    """
    older = to_micros(fixed_clock.now()) - 600 * 1_000_000
    run_blocking(broker.add_order(buy(limit="99.00")))
    store.write_order(
        recorded(buy(limit="98.00", userref=USERREF + 3), status=RowStatus.RESTING, placed_at=older)
    )
    store.write_order(
        recorded(
            buy(limit="97.00", userref=USERREF + 4),
            status=RowStatus.FILLED,
            placed_at=older,
            filled_qty="10",
            avg_fill_price="97.00",
            fee="2.13",
            closed_at=older + 1,
        )
    )
    run_blocking(broker.add_order(sell(qty="2")))
    kraken.add_trade(PAIR, "96.00", fixed_clock.now() + timedelta(seconds=1))

    refs = [USERREF, USERREF + 1, USERREF + 3, USERREF + 4]
    states = run_blocking(broker.query_orders(refs))

    assert len(states) == 4
    assert [state.opened_at for state in states] == [
        to_micros(fixed_clock.now()),
        to_micros(fixed_clock.now()),
        older,
        older,
    ]
