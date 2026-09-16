"""Engine 22 `exit` — spec 93, and invariant 14.

**No upstream payload is hand-built.** `state["exchange"]` and `state["market_sensor"]`
are A's real engines 1 and 3 against C's fake Kraken, the order client is B's real
`PaperBroker` wrapping that same fake, and `state["position_manager"]` is engine 21
itself — so a `triggered` entry in this file is one engine 21 really decided, from a
traded range the fake really printed, and a fill is one the simulator really priced at
the fake's tier 3.

The fixtures come from `test_position_manager.py` rather than being copied: engine 22's
input is engine 21's output, and two copies of "what a manage-chain tick looks like"
would drift apart about it. That is the same reason `test_execution.py` imports engine
16's.

The one thing written by hand is a store row engine 19 would have written on a
*previous* tick, because engine 19 is C's and does not run in this chain. Those go
through `OrderRow` and `PositionRow`, so a shape engine 19 could not produce is refused
before engine 22 sees it.

Tier 3 throughout, standing rule 8 of the Phase 6 task list.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from tests.engines.test_position_manager import (
    LIMIT,
    PAIR,
    TAKER,
    USERREF,
    FakeKrakenWithStream,
    broker,
    build_state,
    context,
    kraken,
    open_position,
    traded,
)

from acsoe.clients.kraken.contracts import OrderSide as ClientOrderSide
from acsoe.clients.kraken.contracts import OrderState
from acsoe.clients.kraken.contracts import OrderStatus as ClientOrderStatus
from acsoe.clients.kraken.contracts import OrderType as ClientOrderType
from acsoe.clients.paper.broker import PaperBroker
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import (
    MICROSECONDS_PER_SECOND,
    OrderIntent,
    OrderRow,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionStatus,
    TradeOutcome,
    to_micros,
)
from acsoe.core.contracts import EngineStatus
from acsoe.engines.exit.contracts import (
    CLOSED_TRADES_FIELD,
    FALLBACK_ASSET_PAIRS_RETAINED,
    ORDERS_FIELD,
    POSITIONS_CLOSED_FIELD,
    POSITIONS_FIELD,
    REASON_DATA_GUARD_BLOCKED,
    REASON_EXIT_ALREADY_PLACED,
    REASON_EXIT_INCOMPLETE,
    REASON_EXITS_PLACED,
    REASON_NOTHING_TO_EXIT,
    STATE_KEY,
    ExitState,
    exit_userref_for,
    round_down_to_lot,
    trade_id_for,
)
from acsoe.engines.exit.engine import ExitEngine
from acsoe.engines.position_manager.contracts import TRIGGERED_FIELD
from acsoe.engines.position_manager.engine import PositionManagerEngine

# `context`, `kraken` and `broker` are imported rather than redefined; importing a
# fixture by name is what makes pytest find it here.
__all__ = ["broker", "context", "kraken"]

#: The fake's only bid level, which is what a market sell walks into.
BID = Decimal("99.99")

#: The committed config: `barriers.target_pct` 0.03, `stop_pct` 0.015. Recomputed here
#: from the same constants engine 21's file uses rather than copied as literals.
TARGET = LIMIT * (Decimal(1) + Decimal("0.03"))
STOP = LIMIT * (Decimal(1) - Decimal("0.015"))
ENTRY_FEE = Decimal("2.178000")


@pytest.fixture
def exit_engine() -> ExitEngine:
    return ExitEngine()


@pytest.fixture
def manager() -> PositionManagerEngine:
    return PositionManagerEngine()


def filled_entry(context: Any, *, userref: int = USERREF, fee: Decimal = ENTRY_FEE) -> OrderRow:
    """The entry order that opened the position, as engine 19 recorded it.

    Engine 22 reads `fee` off this row and nothing else: it is the only place the round
    trip's entry cost exists, and the trade row needs both fees separately under
    invariant 7.
    """
    placed_at = to_micros(context.now) - 600 * MICROSECONDS_PER_SECOND
    return OrderRow(
        userref=userref,
        order_id=f"paper-{userref}",
        run_id="test-run",
        cycle_id=1,
        position_id="pos-1",
        pair=PAIR,
        side=OrderSide.BUY,
        intent=OrderIntent.ENTRY,
        order_type=OrderType.LIMIT,
        oflags="post",
        status=OrderStatus.FILLED,
        qty=Decimal("10"),
        limit_price=LIMIT,
        filled_qty=Decimal("10"),
        avg_fill_price=LIMIT,
        fee=fee,
        placed_at=placed_at,
        closed_at=placed_at + 1,
        updated_at=placed_at + 1,
    )


def managed(
    manager: PositionManagerEngine,
    context: Any,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Run the real engine 21 over `state` and hand back the tick engine 22 sees."""
    state["position_manager"] = manager.process(context, state).data
    return state


def holding_position(
    context: Any, store: StoreClient, *, timeout_in_s: int = 43_200
) -> None:
    """One open position and the entry order that opened it, both in the store."""
    store.write_order(filled_entry(context))
    store.write_position(open_position(context, timeout_in_s=timeout_in_s))


# --------------------------------------------------------------------------- #
# Registry shape and the seam with engine 19
# --------------------------------------------------------------------------- #


def test_the_engine_declares_itself_as_the_registry_will_have_it(
    exit_engine: ExitEngine,
) -> None:
    """`engine-contracts.md` leaves the Gate column blank for 22: it refuses nothing,
    it acts. `is_gate_matches_registry` compares this against `bootstrap.py`."""
    assert exit_engine.name == "exit"
    assert exit_engine.number == 22
    assert exit_engine.is_gate is False
    assert exit_engine.name == STATE_KEY


def test_the_field_names_are_the_ones_engine_nineteen_reads() -> None:
    """Contract rule 3 forbids importing engine 19, so the names are restated — and a
    restatement that nothing pins is a restatement that drifts. This is the pin.

    It imports `engines/memory/contracts.py` here rather than in the engine, which is
    the distinction rule 3 draws: a test may read both sides of a seam; an engine may
    not depend on another engine at runtime.
    """
    from acsoe.engines.memory import contracts as memory

    assert (ORDERS_FIELD, POSITIONS_FIELD, CLOSED_TRADES_FIELD) == (
        memory.ORDERS_FIELD,
        memory.POSITIONS_FIELD,
        memory.CLOSED_TRADES_FIELD,
    )
    assert STATE_KEY == memory.EXIT_KEY


def test_the_lot_rounding_agrees_with_engine_elevens() -> None:
    """The other restatement, and the one that decides an order quantity.

    Engine 11 sizes with `round_down_to_lot` and engine 22 exits with its own copy. If
    they ever disagreed, a position sized on one grid would be sold on another and the
    remainder would sit as an unmanaged holding nothing has a row for.
    """
    from acsoe.engines.risk.contracts import round_down_to_lot as risk_round_down

    for decimals in (0, 1, 2, 8):
        for raw in ("10", "10.123456789", "0.000000009", "3.9999999999"):
            assert round_down_to_lot(Decimal(raw), decimals) == risk_round_down(
                Decimal(raw), decimals
            )


# --------------------------------------------------------------------------- #
# The exit `userref` — invariant 8 on the sell side
# --------------------------------------------------------------------------- #


def test_the_exit_userref_is_the_same_every_time_for_one_position() -> None:
    """Deterministic across processes, which is the whole of invariant 8's idempotency:
    the identifier is chosen before the order exists, so it survives a placement whose
    answer never came back."""
    assert exit_userref_for("pos-1") == exit_userref_for("pos-1")
    assert exit_userref_for("pos-1") != exit_userref_for("pos-2")


def test_the_exit_userref_is_inside_krakens_positive_range() -> None:
    from acsoe.clients.kraken.contracts import USERREF_MAX, USERREF_MIN

    refs = [exit_userref_for(f"pos-{n}") for n in range(500)]
    assert all(USERREF_MIN <= ref <= USERREF_MAX for ref in refs)
    assert 0 not in refs, "zero is what a missing integer field decays to"


def test_the_exit_userref_scheme_is_pinned_to_its_values(
) -> None:
    """A golden value, and it is not a tautology — it is the upgrade hazard.

    `exit_userref_for` is deterministic *within* a version, which is what survives a
    restart. Nothing makes it deterministic *across* versions: change the digest, the
    salt or the range mapping and the next release computes a different identifier for
    an exit the exchange is already holding, finds no recorded order under it, and
    places a second market sell. That is invariant 8's named failure arriving through a
    deploy instead of through a crash.

    So the numbers are written down. **If this test fails, the scheme changed**, and
    the question to answer before editing it is what happens to the orders resting
    under the old identifiers — not what the new numbers are.

    Found by mutation: dropping the `|exit` salt survived every other assertion in this
    file, because every property they check (determinism, range, position-derived) is
    just as true of the changed scheme.
    """
    assert exit_userref_for("pos-1") == 844_348_027
    assert exit_userref_for("pos-2") == 347_650_531
    assert exit_userref_for("pos-4242") == 1_770_331_646


def test_the_exit_userref_does_not_depend_on_the_barrier() -> None:
    """A position triggered on `stop` this tick and `timeout` next tick is **one** exit.

    Hashing the barrier in would give the second tick a different `userref`, and engine
    22 would place a second market sell for a position already being sold — invariant
    8's named failure on the exit side. The function takes no barrier at all, which is
    the strongest form of this assertion available: there is no argument to vary.
    """
    import inspect

    assert list(inspect.signature(exit_userref_for).parameters) == ["position_id"]


# --------------------------------------------------------------------------- #
# The ordinary tick: one exit per barrier
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("prices", "timeout_in_s", "expected"),
    [
        pytest.param([str(TARGET + 1)], 43_200, TradeOutcome.TARGET, id="target"),
        pytest.param([str(STOP - 1)], 43_200, TradeOutcome.STOP, id="stop"),
        pytest.param(["99.99"], -60, TradeOutcome.TIMEOUT, id="timeout"),
    ],
)
def test_an_exit_is_placed_for_each_barrier_and_the_outcome_is_the_one_that_fired(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
    prices: list[str],
    timeout_in_s: int,
    expected: TradeOutcome,
) -> None:
    """Three barriers, three `trades.outcome` values, one code path.

    The three cases differ in **one input each** — the traded price, or the position's
    timeout — and the timeout case trades at a price that fires neither barrier, so a
    `timeout` here cannot be a `target` wearing the wrong name.
    """
    holding_position(context, store, timeout_in_s=timeout_in_s)
    traded(kraken, context, prices)
    state = managed(manager, context, build_state(context, previous_now=context.now - timedelta(seconds=60)))
    assert state["position_manager"][TRIGGERED_FIELD], "engine 21 triggered nothing"

    result = exit_engine.process(context, state)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    data = result.data
    assert data["reason_code"] == REASON_EXITS_PLACED
    (trade,) = data[CLOSED_TRADES_FIELD]
    assert trade["outcome"] == expected.value
    (position,) = data[POSITIONS_FIELD]
    assert position["status"] == PositionStatus.CLOSED.value
    assert position["trade_id"] == trade_id_for("pos-1")
    assert data[POSITIONS_CLOSED_FIELD] is True


def test_the_exit_is_a_market_sell_of_the_whole_position(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
    broker: PaperBroker,
) -> None:
    """Every Phase 6 exit is a taker, target included — the README says why.

    The order row is checked against the broker's own answer as well as against the
    payload, because a published row is a claim and "an order exists" is a different
    assertion from "a dict describes one".
    """
    from acsoe.platform.aio import run_blocking

    holding_position(context, store)
    traded(kraken, context, [str(TARGET + 1)])
    state = managed(manager, context, build_state(context, previous_now=context.now - timedelta(seconds=60)))

    (order,) = exit_engine.process(context, state).data[ORDERS_FIELD]

    assert order["side"] == "sell"
    assert order["order_type"] == "market"
    assert order["oflags"] == "", "post_only on a market order is a contradiction"
    assert order["intent"] == OrderIntent.EXIT.value
    assert Decimal(order["qty"]) == Decimal("10")
    assert order["userref"] == exit_userref_for("pos-1")
    at_exchange = run_blocking(broker.query_orders([order["userref"]]))[0]
    assert at_exchange.status is ClientOrderStatus.FILLED


def test_the_request_that_reaches_the_client_is_a_market_sell_and_not_only_the_row(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    broker: PaperBroker,
) -> None:
    """The published row is engine 22's own claim about the order it placed.

    Every assertion above reads that claim. This one captures the `OrderRequest` the
    client was actually handed, so an engine that published `"order_type": "market"`
    and sent something else fails. Found by mutation: the row-level assertions cannot
    tell those two apart, which is the same shape as "a record of intent is not a
    record of what happened".
    """
    captured: list[Any] = []

    class _Capturing:
        def __init__(self, real: PaperBroker) -> None:
            self._real = real

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

        async def add_order(self, request: Any) -> Any:
            captured.append(request)
            return await self._real.add_order(request)

    holding_position(context, store)
    context.clients.kraken = _Capturing(broker)
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    exit_engine.process(context, state)

    (request,) = captured
    assert request.side is ClientOrderSide.SELL
    assert request.order_type is ClientOrderType.MARKET
    assert request.post_only is False
    assert request.limit_price is None, "a market order carries no price"
    assert request.qty == Decimal("10")
    assert request.userref == exit_userref_for("pos-1")


def test_a_client_that_answers_for_fewer_orders_than_it_was_asked_is_a_defect(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    broker: PaperBroker,
) -> None:
    """Invariant 3, on the one call whose answer decides whether a position is closed.

    A client that answers about nothing has not said "the order is gone"; it has said
    nothing. Reading that as "no such order" would leave the exit unaccounted for while
    the sell may already have happened. The paper broker raises instead — correctly —
    so this is the one state it never reaches, and the wrapper replaces exactly that one
    answer. Named for the **mechanism** rather than the consequence, which is the lesson
    engine 21's sweep left: two branches three lines apart had one name between them.
    """

    class _AnswersAboutNothing:
        def __init__(self, real: PaperBroker) -> None:
            self._real = real

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

        async def query_orders(self, userrefs: Any) -> tuple[OrderState, ...]:
            return ()

    holding_position(context, store)
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )
    context.clients.kraken = _AnswersAboutNothing(broker)

    result = exit_engine.process(context, state)

    assert result.status is EngineStatus.ERROR
    assert result.data[POSITIONS_CLOSED_FIELD] is False
    assert result.data[CLOSED_TRADES_FIELD] == []
    assert "none of them was" in (result.reason or "")


def test_nothing_is_exited_when_nothing_reached_a_barrier(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """The pass half's opposite: an open position that is fine is left alone.

    The one input that differs from the barrier tests is that the pair did not trade at
    a barrier price, and `positions_closed` is `False` because a position is still open
    — not because nothing happened.
    """
    holding_position(context, store)
    state = managed(manager, context, build_state(context, previous_now=context.now - timedelta(seconds=60)))
    assert state["position_manager"][TRIGGERED_FIELD] == []

    data = exit_engine.process(context, state).data

    assert data["reason_code"] == REASON_NOTHING_TO_EXIT
    assert data[ORDERS_FIELD] == []
    assert data[CLOSED_TRADES_FIELD] == []
    assert data[POSITIONS_CLOSED_FIELD] is False


# --------------------------------------------------------------------------- #
# The hold — spec 93 step 3 and invariant 14
# --------------------------------------------------------------------------- #


def test_a_triggered_stop_places_no_exit_on_a_data_guard_tick(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
    broker: PaperBroker,
) -> None:
    """The headline criterion, and the block half of the pair above.

    **One input differs** from the `stop` case: `trading_blocked_by`. The same position,
    the same traded low, the same everything else — so a green here against an engine
    that never exits anything is not possible.

    The trigger is forced into `state` by hand *after* engine 21 has run, which is the
    only hand-built payload in this file and is the point of the test: engine 21
    publishes no trigger on a held tick, so the belt-and-braces check in engine 22 can
    only be reached by pretending it did. That is a defect in engine 21 simulated, not a
    fixture shortcut.
    """
    from acsoe.platform.aio import run_blocking

    holding_position(context, store)
    traded(kraken, context, [str(STOP - 1)])
    state = managed(
        manager,
        context,
        build_state(
            context,
            blocked_by="data_guard",
            previous_now=context.now - timedelta(seconds=60),
        ),
    )
    assert state["position_manager"][TRIGGERED_FIELD] == [], "engine 21 held, as it must"
    state["position_manager"] = dict(
        state["position_manager"],
        **{TRIGGERED_FIELD: [{"position_id": "pos-1", "barrier": "stop"}]},
    )

    data = exit_engine.process(context, state).data

    assert data["reason_code"] == REASON_DATA_GUARD_BLOCKED
    assert data[ORDERS_FIELD] == []
    assert data[CLOSED_TRADES_FIELD] == []
    assert data[POSITIONS_CLOSED_FIELD] is False
    assert run_blocking(broker.open_orders()) == (), "nothing reached the exchange"


def test_a_block_by_any_other_engine_does_not_hold_the_exit(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
) -> None:
    """`data_guard` and nothing else. A `safety` block is a statement about whether to
    *open* something, and a position already open still has to be got out of.

    One input differs from the held test: the blocker's name.
    """
    holding_position(context, store)
    traded(kraken, context, [str(STOP - 1)])
    state = managed(
        manager,
        context,
        build_state(
            context, blocked_by="safety", previous_now=context.now - timedelta(seconds=60)
        ),
    )

    data = exit_engine.process(context, state).data

    assert data["reason_code"] == REASON_EXITS_PLACED
    assert len(data[CLOSED_TRADES_FIELD]) == 1


# --------------------------------------------------------------------------- #
# The liquidation — invariant 14
# --------------------------------------------------------------------------- #


def test_close_intent_exits_a_position_no_barrier_touched(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """A liquidation is not a barrier: it takes every open position in the store, and
    the outcome recorded is `liquidation` rather than whichever barrier it was nearest.

    One input differs from `..._nothing_reached_a_barrier`: `close_intent`.
    """
    holding_position(context, store)
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    data = exit_engine.process(context, state).data

    (trade,) = data[CLOSED_TRADES_FIELD]
    assert trade["outcome"] == TradeOutcome.LIQUIDATION.value
    assert data[POSITIONS_CLOSED_FIELD] is True


def test_a_liquidation_is_not_held_by_a_data_guard_block(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """Invariant 14's first override. One input differs from the held test:
    `close_intent`, on the same `data_guard`-blocked tick."""
    holding_position(context, store)
    state = managed(
        manager,
        context,
        build_state(
            context,
            blocked_by="data_guard",
            close_intent=True,
            previous_now=context.now - timedelta(seconds=60),
        ),
    )

    data = exit_engine.process(context, state).data

    assert data["reason_code"] == REASON_EXITS_PLACED
    assert len(data[CLOSED_TRADES_FIELD]) == 1
    assert data[POSITIONS_CLOSED_FIELD] is True


def test_a_liquidation_completes_during_the_outage_that_fired_it(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
) -> None:
    """Invariant 14 in full, and the case the whole rule exists for.

    `data_guard` is blocking **and** the balance fetch is failing **and** the
    `AssetPairs` fetch is failing — the same outage that fired the escalation is failing
    the calls a liquidation would otherwise need. If invariant 2's live-mode block
    applied here, `close_all` would be blocked by the exact condition it exists to
    answer.

    The retained `AssetPairs` snapshot is what makes the rounding possible, and it is
    real retention rather than a fixture: engine 1 fetched successfully on the tick
    before, so the fake holds the value, and the fetch is broken only afterwards.

    **The book and the fee tier stay up, and that is a property of the simulator rather
    than of the rule.** Neither is retained — invariant 2 is explicit that a stale
    spread is a loaded gun and a fee nobody fetched invalidates the cost gate — so a
    paper market sell cannot be priced without them. In live mode the exchange prices
    the market order itself and neither call is on the path. Recorded here rather than
    silently arranged.
    """
    holding_position(context, store)
    build_state(context)  # a healthy tick, so the fake retains AssetPairs
    kraken.fail("asset_pairs")
    kraken.fail("balance")
    state = managed(
        manager,
        context,
        build_state(
            context,
            blocked_by="data_guard",
            close_intent=True,
            previous_now=context.now - timedelta(seconds=60),
        ),
    )
    assert state["exchange"]["pair_rules"] is None, "the fetch really failed this tick"

    data = exit_engine.process(context, state).data

    (trade,) = data[CLOSED_TRADES_FIELD]
    assert trade["fallbacks_used"] == [FALLBACK_ASSET_PAIRS_RETAINED]
    assert data[POSITIONS_CLOSED_FIELD] is True
    assert Decimal(trade["qty"]) == Decimal("10")


def test_the_retained_rules_are_not_read_outside_a_liquidation(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
) -> None:
    """Spec 93's first scope limit, and the boundary of the only stale read in the
    system.

    One input differs from the test above: `close_intent`. Same failing fetch, same
    retained snapshot sitting there readable — and on an ordinary tick the exit is
    refused instead, because invariant 2 gives pair rules no fallback in any mode.

    The refusal is reported rather than raised out of `process`: the position stays
    open, `positions_closed` stays false, and the tick is an `ERROR` so it is visible.
    """
    holding_position(context, store)
    build_state(context)
    kraken.fail("asset_pairs")
    traded(kraken, context, [str(STOP - 1)])
    state = managed(
        manager,
        context,
        build_state(context, previous_now=context.now - timedelta(seconds=60)),
    )
    assert kraken.last_known_good_asset_pairs is not None, "it was there to be read"
    state["position_manager"] = dict(
        state["position_manager"],
        **{TRIGGERED_FIELD: [{"position_id": "pos-1", "barrier": "stop"}]},
    )

    result = exit_engine.process(context, state)

    assert result.status is EngineStatus.ERROR
    assert result.data["reason_code"] == REASON_EXIT_INCOMPLETE
    assert result.data[CLOSED_TRADES_FIELD] == []
    assert result.data[POSITIONS_CLOSED_FIELD] is False


def test_a_liquidation_on_a_flat_account_is_finished(
    exit_engine: ExitEngine, manager: PositionManagerEngine, context: Any
) -> None:
    """`positions_closed` is computed from the store, not hardcoded.

    An operator pressing Close all with nothing open has nothing to sell and **is**
    finished. A `False` here would leave `close_intent` set forever on exactly that
    account, and the orchestrator would never mark the `close_all` row consumed.
    """
    state = managed(manager, context, build_state(context, close_intent=True))

    data = exit_engine.process(context, state).data

    assert data[POSITIONS_CLOSED_FIELD] is True
    assert data[ORDERS_FIELD] == []


# --------------------------------------------------------------------------- #
# Idempotency — invariant 8 on the sell side
# --------------------------------------------------------------------------- #


def test_the_same_tick_run_twice_places_exactly_one_exit(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    broker: PaperBroker,
) -> None:
    """Invariant 8, and the one test this engine's `userref` exists to pass.

    The same `state`, twice — that is what "the same tick twice" is. Engine 19's row is
    written by hand between the runs, because engine 19 is C's and the store is the
    record engine 22 probes; the second run must find it, place nothing, and still
    report the exit.
    """

    class _Counting:
        """The real broker, counting placements. Nothing else is replaced."""

        def __init__(self, real: PaperBroker) -> None:
            self._real = real
            self.placements = 0

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

        async def add_order(self, request: Any) -> Any:
            self.placements += 1
            return await self._real.add_order(request)

    counting = _Counting(broker)
    context.clients.kraken = counting
    holding_position(context, store)
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )
    first = exit_engine.process(context, state).data
    (placed,) = first[ORDERS_FIELD]
    store.write_order(
        OrderRow.model_validate(
            dict(placed, run_id="test-run", cycle_id=1, updated_at=to_micros(context.now))
        )
    )

    second = exit_engine.process(context, state).data

    assert first["reason_code"] == REASON_EXITS_PLACED
    assert second["reason_code"] == REASON_EXIT_ALREADY_PLACED
    assert second[ORDERS_FIELD][0]["userref"] == placed["userref"]
    # The witness. The broker refuses a second placement under one `userref` anyway, so
    # a duplicate attempt would show up as an `ERROR` too — and an error is not the same
    # claim as "it never tried". Counting the calls is the assertion that tells the two
    # apart, and it is the one that would still hold against an exchange that accepted
    # the duplicate.
    assert counting.placements == 1, "one sell reached the exchange, not two"


def test_a_userref_recorded_against_another_position_raises(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """A digest collision is a defect, not a retry.

    Selling under an identifier that already belongs to another order means neither can
    be cancelled or reconciled by `userref` afterwards — and `userref` is the only
    handle invariant 8 gives an operator during an emergency.
    """
    holding_position(context, store)
    stolen = exit_userref_for("pos-1")
    store.write_order(
        OrderRow(
            userref=stolen,
            order_id="paper-elsewhere",
            run_id="test-run",
            cycle_id=1,
            position_id="pos-somebody-else",
            pair=PAIR,
            side=OrderSide.SELL,
            intent=OrderIntent.EXIT,
            order_type=OrderType.MARKET,
            status=OrderStatus.FILLED,
            qty=Decimal("1"),
            filled_qty=Decimal("1"),
            avg_fill_price=Decimal("99.99"),
            fee=Decimal("0.38"),
            placed_at=to_micros(context.now) - 1,
            closed_at=to_micros(context.now) - 1,
            updated_at=to_micros(context.now) - 1,
        )
    )
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    result = exit_engine.process(context, state)

    assert result.status is EngineStatus.ERROR
    assert result.data[POSITIONS_CLOSED_FIELD] is False
    assert result.data[CLOSED_TRADES_FIELD] == []
    assert "collision is a defect" in (result.reason or "")
    assert "pos-somebody-else" in (result.reason or ""), "and whose order it already is"


# --------------------------------------------------------------------------- #
# The numbers on the trade row
# --------------------------------------------------------------------------- #


def test_the_trade_row_is_recomputed_from_its_sources_and_not_read_back(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """Every figure derived here from the fixture's own inputs, not from the payload.

    The entry fee is `2.178000` and the exit fee is the fake's tier-3 taker rate on the
    proceeds; entry 99.00 and exit 99.99 are **different numbers**, so an implementation
    that read the entry price where it meant the exit price fails rather than agreeing
    with itself.
    """
    holding_position(context, store)
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    (trade,) = exit_engine.process(context, state).data[CLOSED_TRADES_FIELD]

    qty = Decimal("10")
    cost_basis = qty * LIMIT
    proceeds = qty * BID
    exit_fee = proceeds * Decimal(TAKER)
    expected = proceeds - cost_basis - ENTRY_FEE - exit_fee
    assert Decimal(trade["entry_price"]) == LIMIT
    assert Decimal(trade["exit_price"]) == BID
    assert Decimal(trade["entry_fee"]) == ENTRY_FEE
    assert Decimal(trade["exit_fee"]) == exit_fee
    assert Decimal(trade["realised_pnl"]) == expected
    assert Decimal(trade["realised_pnl_pct"]) == expected / cost_basis
    assert Decimal(trade["realised_pnl_quote"]) == expected
    assert trade["exit_userref"] == exit_userref_for("pos-1")
    assert trade["entry_userref"] == USERREF


def test_the_fx_rates_are_one_because_the_quote_is_the_reporting_currency(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """Invariant 7 forbids absorbing FX into PnL, so the rates are recorded per trade
    even when they are 1 — and the equality that makes them 1 is asserted here from
    config rather than assumed from the pair name."""
    holding_position(context, store)
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    (trade,) = exit_engine.process(context, state).data[CLOSED_TRADES_FIELD]

    assert trade["reporting_currency"] == context.config.get(
        "trading.base_reporting_currency"
    )
    assert trade["quote"] == trade["reporting_currency"]
    assert (trade["fx_rate_entry"], trade["fx_rate_exit"]) == ("1", "1")


def test_a_position_quoted_in_another_currency_is_refused_rather_than_priced(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """Nothing in this system fetches an FX rate, so there is no honest one to write.

    Engine 11 refuses such a pair with `no_fx_rate`, which means a position reaching
    here with a foreign quote is the chain contradicting itself. Fail-closed: the
    position stays open and is reported as such.
    """
    store.write_order(filled_entry(context))
    store.write_position(
        open_position(context).model_copy(update={"quote": "EUR"})
    )
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    result = exit_engine.process(context, state)

    assert result.status is EngineStatus.ERROR
    assert result.data[CLOSED_TRADES_FIELD] == []
    assert result.data[POSITIONS_CLOSED_FIELD] is False
    assert "EUR" in (result.reason or "") and "no_fx_rate" in (result.reason or "")


def test_an_entry_order_with_no_fee_is_refused_rather_than_priced_at_zero(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """A zero entry fee is a trade that looks more profitable than it was, in the very
    series `safety`'s consecutive-loss limit is counted from.

    One input differs from the recomputation test: whether the entry row carries a fee.
    """
    store.write_order(
        filled_entry(context).model_copy(update={"fee": None, "avg_fill_price": LIMIT})
    )
    store.write_position(open_position(context))
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    result = exit_engine.process(context, state)

    assert result.status is EngineStatus.ERROR
    assert result.data[CLOSED_TRADES_FIELD] == []
    # **The message, not only the status.** Found by mutation: deleting the guard left
    # every other assertion green, because the next line raised a `TypeError` on
    # `Decimal(None)` instead and both arrive as `exit_incomplete`. A reason code alone
    # cannot tell a missing fee from a foreign quote from a refused order, and each of
    # those needs a different response during an emergency.
    assert "carries no fee" in (result.reason or "")
    assert "pos-1" in (result.reason or ""), "and which position it was"


# --------------------------------------------------------------------------- #
# Rounding — invariant 14 keeps this one
# --------------------------------------------------------------------------- #


def test_the_exit_quantity_is_rounded_down_and_never_up(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    kraken: FakeKrakenWithStream,
    store: StoreClient,
) -> None:
    """Rounding up produces an order Kraken rejects, and a rejected order during an
    emergency is worse than dust.

    `lot_decimals` is forced to 2 and the position holds `10.129`, so up and down are
    **different numbers** — 10.13 against 10.12 — and an assertion that could not tell
    them apart would be no assertion at all.
    """
    kraken.set_pair_rule(PAIR, lot_decimals=2)
    store.write_order(filled_entry(context))
    store.write_position(open_position(context).model_copy(update={"qty": Decimal("10.129")}))
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    data = exit_engine.process(context, state).data

    (order,) = data[ORDERS_FIELD]
    assert Decimal(order["qty"]) == Decimal("10.12")
    assert Decimal(order["qty"]) != Decimal("10.13")


# --------------------------------------------------------------------------- #
# A partial failure is reported, never smoothed
# --------------------------------------------------------------------------- #


def test_positions_closed_is_false_when_an_exit_did_not_fill(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    broker: PaperBroker,
) -> None:
    """The kill switch's retry, from this engine's side.

    The order row is still published so engine 19 records the attempt, and no trade is
    written, and `positions_closed` is false — so the orchestrator keeps `close_intent`
    set and the next tick tries again. Reporting `True` here is the failure the whole
    flag exists to prevent: the liquidation would be marked done with a position open.
    """

    class _NeverFills:
        """The real broker with one answer replaced, so A's validators still apply."""

        def __init__(self, real: PaperBroker) -> None:
            self._real = real

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

        async def query_orders(self, userrefs: Any) -> tuple[OrderState, ...]:
            return tuple(
                OrderState(
                    userref=state.userref,
                    order_id=state.order_id,
                    status=ClientOrderStatus.REJECTED,
                    qty=state.qty,
                    filled_qty=Decimal("0"),
                    fee=Decimal("0"),
                    closed_at=state.closed_at or 1,
                )
                for state in await self._real.query_orders(userrefs)
            )

    holding_position(context, store)
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )
    context.clients.kraken = _NeverFills(broker)

    data = exit_engine.process(context, state).data

    assert data[POSITIONS_CLOSED_FIELD] is False
    assert data[CLOSED_TRADES_FIELD] == []
    assert data[POSITIONS_FIELD] == []
    (order,) = data[ORDERS_FIELD]
    assert order["status"] == OrderStatus.REJECTED.value
    assert data["reason_code"] == REASON_EXIT_INCOMPLETE


def test_one_position_that_cannot_be_exited_does_not_stop_the_others(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """On a liquidation, flat on one of two beats flat on neither.

    The second position has no entry order, so its trade cannot be priced; the first is
    ordinary. The one that failed is left open, `positions_closed` is false, and the
    tick reports `ERROR` — the failure is visible rather than smoothed.
    """
    holding_position(context, store)
    store.write_position(
        open_position(context, position_id="pos-2").model_copy(
            update={"pair": "ETH/USD", "base": "ETH", "entry_userref": None}
        )
    )
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    result = exit_engine.process(context, state)

    assert result.status is EngineStatus.ERROR
    assert result.data["reason_code"] == REASON_EXIT_INCOMPLETE
    assert [row["position_id"] for row in result.data[POSITIONS_FIELD]] == ["pos-1"]
    assert result.data[POSITIONS_CLOSED_FIELD] is False


# --------------------------------------------------------------------------- #
# The console has to be able to say what happened
# --------------------------------------------------------------------------- #


def test_every_reason_code_this_engine_emits_is_renderable_by_the_console() -> None:
    """A code absent from `REASON_PROSE` renders "No reason was recorded." — silently,
    with no error anywhere, which `ownership.md` carries as a seam row and spec 99
    widened to every engine that publishes one, gate or not.

    This began as a tripwire asserting the **absence** of the four codes spec 93 adds,
    because mapping them is C's and a "these are renderable" test would have been red
    in the tree until C landed. C landed them the same day, the tripwire went red, and
    this is what its own failure message said to replace it with. Third tripwire of
    this shape in Phase 6 and the third to be acted on rather than weakened.

    `data_guard_blocked` is in the list and is **not** one of the four: engine 21 emits
    that spelling as a `hold_reason` and engine 22 as a `reason_code`, one fact and one
    word, which the test below pins separately.
    """
    from acsoe.console.format import REASON_PROSE

    for code in (
        REASON_EXITS_PLACED,
        REASON_NOTHING_TO_EXIT,
        REASON_DATA_GUARD_BLOCKED,
        REASON_EXIT_ALREADY_PLACED,
        REASON_EXIT_INCOMPLETE,
    ):
        assert code in REASON_PROSE, f"{code} renders as no reason at all"


def test_the_one_code_this_engine_shares_with_engine_twenty_one_is_one_word() -> None:
    """Engine 21 publishes `data_guard_blocked` as a `hold_reason` and engine 22 as a
    `reason_code`. Two vocabularies for one fact is how a table ends up with both
    "stop" and "stopped" in it, so the sharing is asserted rather than left for a
    reader to notice — and the constants are compared, not their spellings, so a
    rename on either side fails here."""
    from acsoe.engines.position_manager.contracts import HOLD_DATA_GUARD_BLOCKED

    assert REASON_DATA_GUARD_BLOCKED == HOLD_DATA_GUARD_BLOCKED


def test_the_payload_is_json_serialisable_with_money_as_strings(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
) -> None:
    """`core/contracts.py` refuses a `Decimal` in `EngineResult.data` and **accepts** a
    float, which is the dangerous half of that boundary."""
    import json

    holding_position(context, store)
    state = managed(
        manager,
        context,
        build_state(
            context, close_intent=True, previous_now=context.now - timedelta(seconds=60)
        ),
    )

    data = exit_engine.process(context, state).data

    assert json.loads(json.dumps(data)) == data
    (trade,) = data[CLOSED_TRADES_FIELD]
    assert isinstance(trade["realised_pnl"], str)


def test_an_unavailable_store_is_an_error_and_not_a_finished_liquidation(
    exit_engine: ExitEngine, context: Any
) -> None:
    """Contract rule 7 with the flag published anyway. An absent `positions_closed`
    already reads as "not finished"; saying so explicitly leaves a reason code beside
    it, so the operator sees *why* rather than only *that*."""
    context.clients.store = None

    result = exit_engine.process(context, {"system": {"close_intent": True}})

    assert result.status is EngineStatus.ERROR
    assert result.data[POSITIONS_CLOSED_FIELD] is False
    assert result.data["reason_code"] == REASON_EXIT_INCOMPLETE


@pytest.mark.parametrize(
    "value", [True, "true", "false", 1, "yes", [], {}, None], ids=repr
)
def test_only_the_boolean_true_is_a_liquidation(
    exit_engine: ExitEngine,
    manager: PositionManagerEngine,
    context: Any,
    store: StoreClient,
    value: Any,
) -> None:
    """Spec 81's fail-closed reading from the publisher's side. `bool("false")` is
    `True`, so anything text-shaped read with `bool()` would start selling an account
    nobody asked to close."""
    holding_position(context, store)
    state = managed(
        manager,
        context,
        build_state(context, previous_now=context.now - timedelta(seconds=60)),
    )
    state["system"]["close_intent"] = value

    data = exit_engine.process(context, state).data

    liquidated = bool(data[CLOSED_TRADES_FIELD])
    assert liquidated is (value is True)


def test_the_state_payload_has_exactly_the_five_documented_fields() -> None:
    """Engine 19 reads three of them and the orchestrator reads a fourth. A field added
    without a decision is a field nobody is recording."""
    assert set(ExitState().to_state()) == {
        ORDERS_FIELD,
        POSITIONS_FIELD,
        CLOSED_TRADES_FIELD,
        POSITIONS_CLOSED_FIELD,
        "reason_code",
    }
