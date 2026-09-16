"""Engine 18 `execution` — spec 91.

**The order client is B's real `PaperBroker` wrapping C's fake Kraken**, and `state` is
built by the same helper `test_decision.py` uses: real engines 1, 3, 7, 10, 11 and 16,
with only engines 8, 9, 14 and 15 supplied. So a placement in this file is a placement
the simulator accepted, at a price the fake's own book produced, and a rejection is one
the post-only rule really refused.

Tier 3 throughout, standing rule 8 of the Phase 6 task list.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from tests.engines.test_decision import (
    ASK,
    BID,
    OTHER_PAIR,
    PAIR,
    FakeKrakenWithStream,
    approving_state,
    context,
    expected_closed_bar_ts,
    kraken,
)

# The client's enums are aliased and the store's keep their names — the two-enum rule
# in `code-standards.md`. `OrderRequest.side` is the *client's* `OrderSide`, and the
# published row's fields are the *store's*; they compare equal and are never
# identical, and this file asserted `is` against the wrong one on its first run.
from acsoe.clients.kraken.contracts import USERREF_MAX, USERREF_MIN, OrderRequest
from acsoe.clients.kraken.contracts import OrderSide as ClientOrderSide
from acsoe.clients.kraken.contracts import OrderType as ClientOrderType
from acsoe.clients.paper.broker import PaperBroker
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import (
    OrderIntent,
    OrderRow,
    OrderSide,
    OrderStatus,
    OrderType,
    to_micros,
)
from acsoe.core.contracts import EngineStatus
from acsoe.engines.decision.engine import DecisionEngine
from acsoe.engines.execution.contracts import (
    ORDERS_FIELD,
    PLACED_FIELD,
    REASON_ENTRY_ALREADY_PLACED,
    REASON_ENTRY_PLACED,
    REASON_ENTRY_UNRECORDED,
    REASON_POST_ONLY_WOULD_CROSS,
    STATE_KEY,
    ExecutionState,
    to_userref,
    userref_for,
)
from acsoe.engines.execution.engine import (
    ExecutionEngine,
    ExecutionError,
    order_types_named_in_this_module,
    round_down_to_tick,
)

# `context` and `kraken` are imported from `test_decision.py` rather than redefined:
# engine 18's inputs are engine 16's outputs, so a second copy of that setup would be
# two fixtures drifting apart about what an approving tick looks like. Importing a
# fixture by name is what makes pytest find it here.
__all__ = ["context", "kraken"]


@pytest.fixture
def broker(
    kraken: FakeKrakenWithStream, store: StoreClient, paper_config: Any, fixed_clock: Any
) -> PaperBroker:
    return PaperBroker(kraken, store=store, config=paper_config, clock=fixed_clock)


@pytest.fixture
def trading_context(context: Any, broker: PaperBroker) -> Any:
    """The decision tick, with the paper broker in the client's place.

    Exactly how `cli/engine.py` wires paper mode: the broker *is*
    `context.clients.kraken`, so engines 1 and 3 keep reading the fake through it.
    """
    context.clients.kraken = broker
    return context


@pytest.fixture
def execution() -> ExecutionEngine:
    return ExecutionEngine()


def decided(context: Any, **kwargs: Any) -> dict[str, Any]:
    """`state` with engine 16's real verdict in it — the tick engine 18 was built for."""
    state = approving_state(context, **kwargs)
    state["decision"] = DecisionEngine().process(context, state).data
    return state


def expected_userref(context: Any) -> int:
    return userref_for(PAIR, expected_closed_bar_ts(context.now))


# --------------------------------------------------------------------------- #
# Registry shape and the seam with engine 16
# --------------------------------------------------------------------------- #


def test_the_engine_declares_itself_as_the_registry_will_have_it(
    execution: ExecutionEngine,
) -> None:
    """`engine-contracts.md` leaves the Gate column blank for 18. It has no criteria of
    its own; everything that could refuse this trade already ran."""
    assert execution.name == "execution"
    assert execution.number == 18
    assert execution.is_gate is False
    assert execution.name == STATE_KEY


def test_engine_sixteen_really_approved_before_engine_eighteen_is_asked(
    trading_context: Any,
) -> None:
    """The premise of every placement test here, asserted rather than assumed.

    Engine 16 blocks on five clauses and publishes no intent on any of them, so a
    fixture that quietly stopped producing one would turn every test below into an
    `ExecutionError` — or worse, would turn a "nothing was placed" assertion green for
    the wrong reason. The same check `test_decision.py` makes of its own upstream.
    """
    state = decided(trading_context)

    assert state["decision"]["coherent"] is True
    assert "intent" in state["decision"]


# --------------------------------------------------------------------------- #
# The placement
# --------------------------------------------------------------------------- #


def test_a_passing_tick_places_one_post_only_limit_buy_at_the_bid(
    execution: ExecutionEngine, trading_context: Any, store: StoreClient
) -> None:
    """The whole engine, against the real broker, with every figure recomputed.

    The quantity is engine 11's, through engine 16's intent. The price is the bid the
    fake's book produced, rounded down onto the pair's own grid — both recomputed here
    from their sources rather than read back out of the payload, so an engine 18 that
    invented either fails rather than agreeing with itself.
    """
    state = decided(trading_context)
    rules = state["exchange"]["pair_rules"]["pairs"][PAIR]
    expected_price = round_down_to_tick(Decimal(BID), int(rules["pair_decimals"]))

    result = execution.process(trading_context, state)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    data = result.data
    assert data[PLACED_FIELD] is True
    assert data["reason_code"] == REASON_ENTRY_PLACED
    assert data["userref"] == expected_userref(trading_context)

    (row,) = data[ORDERS_FIELD]
    assert row["status"] == OrderStatus.RESTING.value
    assert row["intent"] == OrderIntent.ENTRY.value
    assert row["side"] == OrderSide.BUY.value
    assert row["order_type"] == OrderType.LIMIT.value
    assert row["oflags"] == "post"
    assert row["qty"] == state["decision"]["intent"]["qty"]
    assert Decimal(row["limit_price"]) == expected_price
    assert row["placed_at"] == to_micros(trading_context.now)
    assert "closed_at" not in row, "a resting order has not closed"
    assert store.order_by_userref(row["userref"]) is None, "engine 19 records, not this one"


def test_the_order_really_reaches_the_broker_and_rests_there(
    execution: ExecutionEngine, trading_context: Any, broker: PaperBroker
) -> None:
    """The payload says an order was placed; this says one exists.

    A published row is a claim. Asking the broker what is open afterwards is the only
    assertion that distinguishes "engine 18 placed an order" from "engine 18 built a
    dict that describes one".
    """
    from acsoe.platform.aio import run_blocking

    data = execution.process(trading_context, decided(trading_context)).data

    resting = run_blocking(broker.open_orders())
    assert [order.userref for order in resting] == [data["userref"]]


def test_the_price_is_rounded_down_onto_the_grid_and_never_up(
    trading_context: Any,
) -> None:
    """`round_down_to_tick` on its own, against hand arithmetic.

    Down rather than to-nearest is the pessimistic direction for a **buy** limit: further
    from crossing, so post-only rejects less often, and less likely to fill, so the
    simulator never reports a fill a real exchange would not have given. Asserted against
    values chosen so that to-nearest would round the other way.
    """
    _ = trading_context
    assert round_down_to_tick(Decimal("99.98999"), 2) == Decimal("99.98")
    assert round_down_to_tick(Decimal("99.99999"), 2) == Decimal("99.99")
    assert round_down_to_tick(Decimal("0.123456789"), 5) == Decimal("0.12345")
    assert round_down_to_tick(Decimal("100"), 0) == Decimal("100")


def test_no_market_order_is_ever_constructed(execution: ExecutionEngine) -> None:
    """Invariant 8, asserted **structurally** rather than behaviourally.

    A behavioural test can only prove that the paths it drove placed no market order.
    This walks the module's AST and requires that the only `OrderType` member it
    references anywhere is `LIMIT` — so a branch added later, under a flag nobody drove,
    fails here.

    The AST rather than a text search, for the reason the paper broker's fee-literal
    guard uses one: the module docstring *explains* why there is no market entry, and a
    string search would fail on the explanation. The thing that must not exist is a
    reference, not a mention.
    """
    _ = execution

    assert order_types_named_in_this_module() == {"LIMIT"}


def test_the_request_handed_to_the_client_is_a_post_only_limit_buy(
    execution: ExecutionEngine, trading_context: Any, broker: PaperBroker
) -> None:
    """The other half of the structural test: what was actually asked for.

    The request is captured on its way into the real broker rather than reconstructed, so
    this asserts on the object the exchange would have received — `post_only` True, side
    buy, type limit, and a limit price present. `post_only` has no default on
    `OrderRequest` precisely because the right answer differs between an entry and a
    liquidation; this is the entry side of that.
    """
    captured: list[OrderRequest] = []
    real_add = broker.add_order

    async def watching(request: OrderRequest) -> Any:
        captured.append(request)
        return await real_add(request)

    broker.add_order = watching  # type: ignore[method-assign]

    execution.process(trading_context, decided(trading_context))

    (request,) = captured
    assert request.post_only is True
    assert request.side is ClientOrderSide.BUY
    assert request.order_type is ClientOrderType.LIMIT
    assert request.limit_price is not None


# --------------------------------------------------------------------------- #
# Invariant 8 — the same tick twice places once
# --------------------------------------------------------------------------- #


def test_the_same_tick_run_twice_places_exactly_one_order(
    execution: ExecutionEngine, trading_context: Any, store: StoreClient, broker: PaperBroker
) -> None:
    """Invariant 8, the whole of it, and the one test this engine exists to pass.

    **The same `state`, twice** — because that is what "the same tick twice" is: one
    tick's approvals, replayed. Re-deriving the chain would not be a replay, and would
    not even reach engine 18; see
    `test_a_recorded_entry_stops_the_chain_at_engine_eleven_before_engine_eighteen`.

    Between the two runs, engine 19's row is written by hand — engine 19 is C's and does
    not run in this chain, and the store is the authoritative record engine 18 probes.
    The second run must find it, place nothing, and still publish the row so engine 21
    sees the entry.
    """
    from acsoe.platform.aio import run_blocking

    state = decided(trading_context)
    first = execution.process(trading_context, state).data
    store.write_order(
        recorded_entry(trading_context, userref=first["userref"], row=first[ORDERS_FIELD][0])
    )

    second = execution.process(trading_context, state).data

    assert first[PLACED_FIELD] is True
    assert second[PLACED_FIELD] is False
    assert second["reason_code"] == REASON_ENTRY_ALREADY_PLACED
    assert second[ORDERS_FIELD][0]["userref"] == first["userref"]
    assert len(run_blocking(broker.open_orders())) == 1, "one order on the book, not two"


def test_an_order_at_the_exchange_that_the_store_never_recorded_places_nothing(
    execution: ExecutionEngine, trading_context: Any, broker: PaperBroker
) -> None:
    """The case the store cannot cover: placed, then the process died before engine 19.

    The broker keeps the order in `_pending` and reports it through `open_orders()`,
    while the store has no row — which is exactly the state a crash between the
    opportunity chain and the end of the manage chain leaves behind. Engine 18 must not
    place a second one.

    **And it publishes no order row.** `OrderState` carries no `qty` and no
    `limit_price`, so the order cannot be described well enough to build engine 19's row,
    and guessing the two would write a price nothing ever rested at into `orders`. The
    `userref` is published so an operator can find it by hand. Reported to the lead and
    to A as a seam gap rather than papered over here.
    """
    from acsoe.platform.aio import run_blocking

    execution.process(trading_context, decided(trading_context))
    assert len(run_blocking(broker.open_orders())) == 1

    second = execution.process(trading_context, decided(trading_context)).data

    assert second[PLACED_FIELD] is False
    assert second["reason_code"] == REASON_ENTRY_UNRECORDED
    assert second[ORDERS_FIELD] == [], "nothing is described that cannot be described"
    assert len(run_blocking(broker.open_orders())) == 1, "still one order, not two"


def test_a_userref_recorded_against_another_pair_raises(
    execution: ExecutionEngine, trading_context: Any, store: StoreClient
) -> None:
    """A collision is a defect, not a retry.

    Placing anyway would put this candidate's order under an identifier that already
    belongs to another pair's, after which neither can be cancelled by `userref` with any
    confidence. So it raises, which contract rule 7 turns into `ERROR` and no placement,
    rather than being worked around.
    """
    state = decided(trading_context)
    userref = expected_userref(trading_context)
    store.write_order(
        recorded_entry(
            trading_context,
            userref=userref,
            row={"qty": "10", "limit_price": "99.98", "status": OrderStatus.RESTING.value},
            pair=OTHER_PAIR,
        )
    )

    with pytest.raises(ExecutionError, match="collision"):
        execution.process(trading_context, state)


def test_the_userref_is_the_same_for_one_pair_and_bar_and_differs_otherwise(
    trading_context: Any,
) -> None:
    """Determinism is the whole idempotency scheme, so it is asserted directly.

    `hash()` would satisfy the first line of this test and fail the property it is about:
    Python salts string hashing per process, so the same candidate after a restart would
    get a different `userref` and a second order. There is no way to observe that in one
    process, which is why `userref_for` uses `blake2b` and why this test's docstring
    carries the argument the assertion cannot.
    """
    bar = expected_closed_bar_ts(trading_context.now)

    assert userref_for(PAIR, bar) == userref_for(PAIR, bar)
    assert userref_for(PAIR, bar) != userref_for(OTHER_PAIR, bar)
    assert userref_for(PAIR, bar) != userref_for(PAIR, bar - 900)


@pytest.mark.parametrize(
    ("pair", "bar"),
    [("SOL/USD", 0), ("SOL/USD", 1_757_000_000), ("XBT/USD", 2**40), ("A/B", -1)],
    ids=["bar zero", "a real bar", "a far future bar", "a negative bar"],
)
def test_every_userref_is_inside_krakens_signed_32_bit_range(pair: str, bar: int) -> None:
    """A value outside the range is not truncated by the exchange in any way this system
    could predict, so `UserRef` refuses it — and a `userref` refused at the boundary is a
    placement that never happens. Asserted on the constraint, over inputs chosen to
    stress the modulo rather than to be realistic."""
    userref = userref_for(pair, bar)

    assert USERREF_MIN <= userref <= USERREF_MAX
    assert userref > 0, "zero is what a missing integer field decays to"


@pytest.mark.parametrize(
    "digest",
    [0, 1, USERREF_MAX - 2, USERREF_MAX - 1, USERREF_MAX, 2**63 - 1],
    ids=["zero", "one", "one below the modulus", "the modulus", "one above", "the widest digest"],
)
def test_the_range_mapping_never_produces_zero_at_any_edge(digest: int) -> None:
    """The range guarantee, at the only inputs where it can fail.

    `userref_for` hashes and then maps, and the mapping is what carries the property.
    A test over the whole function can only *sample* the digest space, and dropping the
    `1 +` changes the answer for exactly one input in 2^31 — a mutation no sampling test
    will ever find, and one that did survive the first sweep. Splitting `to_userref` out
    makes the boundary reachable: the digest that maps to the low end is simply 0.

    Zero matters because it is the value a missing integer field decays to in too many
    places to be safe as an identifier; the upper bound matters because a value outside
    Kraken's signed 32-bit range is not truncated in any way this system could predict.
    """
    userref = to_userref(digest)

    assert 0 < userref <= USERREF_MAX
    assert to_userref(0) == 1, "the low edge is 1, not 0"


# --------------------------------------------------------------------------- #
# The rejection
# --------------------------------------------------------------------------- #


def test_a_post_only_order_that_would_cross_is_recorded_and_the_candidate_abandoned(
    execution: ExecutionEngine, trading_context: Any, kraken: FakeKrakenWithStream
) -> None:
    """A real rejection from the real broker, not an injected one.

    The book is inverted so that the bid engine 3 published is at or above the ask, which
    is what makes a post-only buy cross. One input differs from the placement test: the
    ask side of the fake's book.

    The row is published with status `rejected` and a `closed_at`, because a rejection is
    terminal and `OrderRow` requires a close time on a terminal status. Nothing is
    re-placed: re-placing a tick lower is chasing by another name.
    """
    state = decided(trading_context)
    # The quote engine 3 published still carries the old bid; the broker prices the
    # post-only check against the book it is asked about, so moving the ask under that
    # bid is what makes the placement cross.
    kraken.set_order_book(PAIR, bids=[("90.00", "500")], asks=[("99.00", "500")])

    data = execution.process(trading_context, state).data

    assert data[PLACED_FIELD] is False
    assert data["reason_code"] == REASON_POST_ONLY_WOULD_CROSS
    (row,) = data[ORDERS_FIELD]
    assert row["status"] == OrderStatus.REJECTED.value
    assert row["closed_at"] == to_micros(trading_context.now)
    assert row["reason"], "a rejection with no cause cannot be told from one nobody recorded"


def test_a_recorded_entry_stops_the_chain_at_engine_eleven_before_engine_eighteen(
    trading_context: Any, store: StoreClient, broker: PaperBroker
) -> None:
    """The layer in front of engine 18's idempotency check, and it is not decoration.

    Once engine 19 has recorded the entry, a *re-derived* chain never reaches engine 18
    at all: engine 11 sees a resting entry on the pair, refuses under invariant 6's
    per-pair clause (spec 89), and engine 16 publishes no intent. So in the ordinary
    course invariant 8's check here never fires, and the temptation is to conclude it is
    not needed.

    It is needed, and this test is what says why in one place rather than in a comment.
    Engine 11's refusal is a **gate's** decision: it depends on `max_concurrent_positions`,
    on the store being readable and on spec 89 continuing to exist. Invariant 8 is not
    allowed to depend on any of those. Engine 18's own probe is what holds when this one
    does not — the `entry_unrecorded_at_exchange` case below is exactly a tick where
    engine 11 approves, because the store has nothing, and the order is on the book
    anyway.

    Found by writing the test above the wrong way round: it re-derived the chain between
    the two runs and failed with "engine 16 approved nothing", which is this behaviour
    reported as a fixture problem.
    """
    from acsoe.engines.risk.contracts import REASON_ENTRY_RESTING_ON_PAIR

    # `broker` is requested so the paper broker is what `trading_context` wires in; the
    # placement below goes through it and the assertions are about the chain, not it.
    _ = broker
    first = ExecutionEngine().process(trading_context, decided(trading_context)).data
    store.write_order(
        recorded_entry(trading_context, userref=first["userref"], row=first[ORDERS_FIELD][0])
    )

    replayed = decided(trading_context)

    assert replayed["risk"]["reason_code"] == REASON_ENTRY_RESTING_ON_PAIR
    assert "intent" not in replayed["decision"], "engine 16 composes nothing on a refusal"


# --------------------------------------------------------------------------- #
# Absent inputs raise, never default
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("drop", "why"),
    [
        ("intent", "engine 16 approved nothing"),
        ("qty", "no quantity was approved"),
        ("bid", "engine 3 published no quote for the pair"),
        ("pair_decimals", "the pair rules did not arrive"),
    ],
)
def test_an_absent_input_raises_rather_than_defaulting(
    execution: ExecutionEngine, trading_context: Any, drop: str, why: str
) -> None:
    """Spec 91 step 2: "absent means no approval — raise, never default".

    Engine 18 is not a gate and has no refusal of its own to publish, so an input that is
    not there is not "no trade this tick" — it is the chain contradicting itself. A
    default here would be a price, a size or a grid nobody chose, attached to real money.
    """
    state = decided(trading_context)
    if drop == "intent":
        del state["decision"]["intent"]
    elif drop == "qty":
        del state["decision"]["intent"]["qty"]
    elif drop == "bid":
        del state["market_sensor"]["quotes"][PAIR]
    else:
        del state["exchange"]["pair_rules"]["pairs"][PAIR]["pair_decimals"]

    with pytest.raises(ExecutionError):
        execution.process(trading_context, state)


def test_a_quantity_that_is_a_float_raises_rather_than_being_stringified(
    execution: ExecutionEngine, trading_context: Any
) -> None:
    """The engine 16 defect, guarded on this side of the seam as well.

    `str(33.33)` is `"33.33"` and parses as a clean `Decimal`, so stringifying before
    parsing turns off the one check in the system that refuses a value which has already
    lost precision. Engine 16 had exactly that bug on 2026-09-16; engine 18 reads the
    same field and would have inherited it.
    """
    state = decided(trading_context)
    state["decision"]["intent"]["qty"] = 33.33

    with pytest.raises(ExecutionError, match="float"):
        execution.process(trading_context, state)


def test_a_non_positive_bid_raises(execution: ExecutionEngine, trading_context: Any) -> None:
    """Absent is not zero and zero is not a price. A bid of zero rounds to a limit of
    zero, which `OrderRequest` would refuse anyway — but it would refuse it as a
    validation error deep in the client rather than as "engine 3 published no price",
    and the second is what an operator can act on."""
    state = decided(trading_context)
    state["market_sensor"]["quotes"][PAIR]["bid"] = "0"

    # Matched on a phrase that belongs to **this** guard and to no other. The first
    # version matched "not a price", which also appears in the message the *rounded*
    # limit's guard raises — so the assertion passed whichever of the two fired, and a
    # mutation deleting this one survived. The same failure as engine 16's expected-move
    # test: a witness that both hypotheses satisfy.
    with pytest.raises(ExecutionError, match="engine 3 published no usable price"):
        execution.process(trading_context, state)


# --------------------------------------------------------------------------- #
# The payload
# --------------------------------------------------------------------------- #


def test_the_published_payload_is_json_serialisable(
    execution: ExecutionEngine, trading_context: Any
) -> None:
    """Money leaves as a string; nothing here is a `Decimal`."""
    import json

    data = execution.process(trading_context, decided(trading_context)).data

    assert json.loads(json.dumps(data)) == data
    assert isinstance(data[ORDERS_FIELD][0]["qty"], str)
    assert isinstance(data[ORDERS_FIELD][0]["limit_price"], str)


def test_the_published_row_is_the_shape_engine_twenty_one_reads(
    execution: ExecutionEngine, trading_context: Any
) -> None:
    """The seam with engine 21, with **no double on either side**.

    Engine 21's `_resting_entries` picks this tick's placements out of
    `state["execution"]` and wraps each in `_PublishedEntry`, which reads `userref`,
    `pair`, `qty`, `limit_price` and `placed_at`. That class is engine 21's and is used
    here directly: if engine 18's row loses a field engine 21 needs, this fails rather
    than the two engines agreeing separately and disagreeing at runtime.
    """
    from acsoe.engines.position_manager.engine import _PublishedEntry

    (row,) = execution.process(trading_context, decided(trading_context)).data[ORDERS_FIELD]

    entry = _PublishedEntry(row)

    assert entry.pair == PAIR
    assert entry.userref == expected_userref(trading_context)
    assert entry.qty > 0
    assert entry.limit_price > 0
    assert entry.placed_at == to_micros(trading_context.now)


def test_the_engine_never_returns_pass(
    execution: ExecutionEngine, trading_context: Any, store: StoreClient
) -> None:
    """A `PASS` stops the opportunity chain, and downstream that reads as "nothing to do
    here". An order that was just placed is the opposite of nothing to do, and engine 21
    runs on the same tick expecting to see it. Checked on both outcomes, because the
    already-placed path is the one where "nothing happened" is tempting.

    One `state`, replayed, for the reason
    `test_the_same_tick_run_twice_places_exactly_one_order` gives.
    """
    state = decided(trading_context)
    first = execution.process(trading_context, state)
    store.write_order(
        recorded_entry(
            trading_context,
            userref=first.data["userref"],
            row=first.data[ORDERS_FIELD][0],
        )
    )
    second = execution.process(trading_context, state)

    assert first.status is EngineStatus.OK
    assert second.status is EngineStatus.OK


def test_the_state_payload_model_refuses_an_unknown_field() -> None:
    """`extra="forbid"`, so a field renamed on one side of the engine 19 seam fails here
    rather than being silently carried and silently dropped."""
    with pytest.raises(ValueError, match="extra"):
        ExecutionState(pair=PAIR, userref=1, placed=True, unexpected="x")  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def recorded_entry(
    context: Any, *, userref: int, row: dict[str, Any], pair: str = PAIR
) -> OrderRow:
    """Engine 19's row for an order engine 18 placed, written by hand.

    Engine 19 is C's and does not run in this chain. The fields come from engine 18's own
    published row wherever it has them, so this is engine 19's *recording* of engine 18's
    output rather than a second opinion about what the order was. It goes through
    `OrderRow`, so a shape engine 19 could not produce is refused before the store sees
    it.
    """
    placed_at = int(row.get("placed_at") or to_micros(context.now))
    return OrderRow(
        userref=userref,
        order_id=str(row.get("order_id") or f"paper-{userref}"),
        run_id="test-run",
        cycle_id=1,
        pair=pair,
        side=OrderSide.BUY,
        intent=OrderIntent.ENTRY,
        order_type=OrderType.LIMIT,
        oflags="post",
        status=OrderStatus(str(row["status"])),
        qty=Decimal(str(row["qty"])),
        limit_price=Decimal(str(row["limit_price"])),
        filled_qty=Decimal("0"),
        placed_at=placed_at,
        updated_at=placed_at,
    )


def test_the_fixtures_book_is_the_one_the_placement_assertions_assume() -> None:
    """`BID` and `ASK` are imported from `test_decision.py` rather than retyped, so the
    price assertions above cannot drift from the book that produced them."""
    assert Decimal(BID) < Decimal(ASK), "an uncrossed book, or post-only means nothing"
