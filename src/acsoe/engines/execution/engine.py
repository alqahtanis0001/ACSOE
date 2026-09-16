"""Engine 18 `execution` — the only thing in this system that places an entry.

## What it does

On a tick where every gate passed, exactly one post-only limit buy, for the quantity
engine 11 approved, at the best bid, under a `userref` derived from the pair and the
bar. Then it publishes the row engine 19 records. That is all of it.

## What it must never do

**No market entry, under any condition or flag.** Invariant 8. A market buy pays the
taker fee on entry, and engine 10's whole hurdle was computed against a *maker* entry —
so a market entry trades an edge the cost gate never approved. There is no branch in
this module that constructs a market order, and a test walks the source to say so.

**No chase, no re-price, no replace.** A post-only order the exchange rejects because it
would have crossed is recorded and the candidate is abandoned for this tick. Re-placing
it a tick lower is chasing by another name. Cancelling a stale one is engine 21's.

**No re-sizing.** The quantity is engine 11's, carried through engine 16's intent
untouched.

**No relational write.** Engine 19 records. This engine publishes a row into `state` and
engine 21 reads the same key on the same tick, before engine 19 has run.

## Invariant 8's idempotency, and the probe that is not `query_orders`

The rule is "never place an order without first checking whether that `userref` already
exists". Two sources are asked, and the order matters:

1. **`store.order_by_userref`** — the authoritative record, across restarts and across
   every status. Engine 19 writes it at the end of the tick that placed.
2. **`kraken.open_orders()`** — for the one case the store cannot cover: the order was
   placed and engine 19 never recorded it, because the process died between the two.

**The second probe is `open_orders()` and deliberately not `query_orders([userref])`,
which is what spec 91 step 3 names.** `OrderClientProtocol` says a call that cannot be
completed **raises** rather than returning an empty result, and B's paper broker raises
for an unknown `userref` for exactly that reason — so `query_orders` answers "I have
never heard of this order" and "I cannot reach the exchange" with the same exception, and
those two require opposite actions. Treat the raise as "unknown" and an outage becomes a
duplicate order, which is invariant 8's named failure. Treat it as "cannot tell" and the
**first** placement of every candidate is refused, because a first placement is always
unknown, and the system never trades at all.

`open_orders()` has a well-defined negative: the order is not in the list. It still
raises during an outage, so invariant 3 still holds — an outage abandons the tick.

It cannot miss the case it is there for. A post-only limit buy at the best bid **cannot
fill at placement** — that is what post-only means — so an entry placed earlier in this
same bar and not yet recorded is still resting, and resting is what `open_orders()`
lists. Deviation from the spec's named mechanism, flagged to the lead; the spec's
conclusion is right and its mechanism is the one that cannot work.

## The price: the best bid, rounded down, and it is a recorded absence

**Every Phase 6 entry rests at the best bid.** Not a choice anybody defended — the
execution offset bandit is a Locked Decision that the operator **deferred to Phase 7** on
2026-09-16, because it needs a table that does not exist and learns from a fill history
that does not exist either. Joining the bid never crosses while the spread is positive,
and engine 4 `data_guard` already refuses a crossed book.

Rounded **down** to the pair's `pair_decimals`. Down rather than to-nearest because a
lower buy limit is the pessimistic direction on both edges that matter: it is further
from crossing, so post-only rejects less often, and it is less likely to fill, so the
simulator never reports a fill a real exchange would not have given.
"""

from __future__ import annotations

import ast
import time
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NamedTuple

# **The two-enum rule, `code-standards.md` under Money and numbers.** `OrderSide`,
# `OrderType` and `OrderStatus` are declared in *both* `clients/kraken/contracts.py`
# and `clients/store/contracts.py` with matching spellings, on purpose, so they
# compare equal and are never identical. Engine 21 lost thirteen tests to that. Here
# the client's are aliased and used only for the `OrderRequest` this engine sends;
# the store's keep their names and are used only for the row payload it publishes.
from acsoe.clients.kraken.contracts import OrderAckStatus, OrderRequest, money_text, to_micros
from acsoe.clients.kraken.contracts import OrderSide as ClientOrderSide
from acsoe.clients.kraken.contracts import OrderType as ClientOrderType
from acsoe.clients.store.contracts import OrderIntent, OrderSide, OrderStatus, OrderType
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.execution.contracts import (
    DECISION_KEY,
    EXCHANGE_KEY,
    INTENT_FIELD,
    MARKET_SENSOR_KEY,
    PAIR_DECIMALS_FIELD,
    PAIR_RULES_KEY,
    PAIR_RULES_PAIRS_KEY,
    QUOTE_BID_FIELD,
    QUOTES_FIELD,
    REASON_ENTRY_ALREADY_PLACED,
    REASON_ENTRY_NOT_A_LIMIT,
    REASON_ENTRY_PLACED,
    REASON_ENTRY_RECOVERED,
    REASON_ENTRY_UNRECORDED,
    REASON_POST_ONLY_WOULD_CROSS,
    ExecutionState,
    userref_for,
)
from acsoe.platform.aio import run_blocking


class _AlreadyPlaced(NamedTuple):
    """What the invariant 8 probe found: the order's row, and why it was not placed.

    `row` is `None` in exactly two cases, both of them an exchange answer this engine
    will not turn into a record: an entry with no `limit_price`, which contradicts the
    only order it places, and an order with no `opened_at`, which cannot be dated
    without inventing a time. See :meth:`ExecutionEngine._unrecorded`.
    """

    row: dict[str, Any] | None
    reason_code: str


class ExecutionError(RuntimeError):
    """An input this engine needs is absent, or a `userref` collided.

    Raised rather than returned. Engine 18 is **not** a gate and has no refusal of its
    own to publish: every reason a trade should not happen was already somebody else's
    decision, and reaching this engine at all means they all said yes. So an input that
    is not there is not "no trade this tick" — it is the chain contradicting itself, and
    contract rule 7 turns it into `ERROR` with no order placed.
    """


def _require(container: Any, key: str, where: str) -> Any:
    """Fetch `key`, or say precisely what was missing. A `None` is an absence.

    The same helper engine 10 uses, and for the same reason: pydantic alone would say
    "field required", and "which input, from which engine" is what an operator needs.
    """
    if not isinstance(container, dict):
        raise ExecutionError(f"{where} is {type(container).__name__}, expected a mapping")
    if key not in container or container[key] is None:
        raise ExecutionError(f"{where}.{key} is not there, so no order can be built")
    return container[key]


def _money(value: Any, where: str) -> Decimal:
    """A published money string as an exact `Decimal`, refusing a float.

    A float has already lost precision by the time it arrives, and `str()`-ing it first
    hides that — the defect found in engine 16 on 2026-09-16 and recorded in the build
    log. So the type is checked before the parse rather than after.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise ExecutionError(
            f"{where} is the float {value!r}; money crosses `state` as a decimal string"
        )
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ExecutionError(f"{where} is {value!r}, which is not a number") from exc


def round_down_to_tick(price: Decimal, pair_decimals: int) -> Decimal:
    """The largest price on the pair's grid that is not above `price`.

    Pure and exported so a test can recompute it rather than compare engine 18's answer
    with engine 18's answer. `ROUND_DOWN` on a positive price truncates toward zero,
    which for a **buy** limit is the pessimistic direction: further from crossing and
    less likely to fill.
    """
    if pair_decimals < 0:
        raise ExecutionError(f"pair_decimals is {pair_decimals}, which is not a grid")
    return price.quantize(Decimal(1).scaleb(-pair_decimals), rounding=ROUND_DOWN)


class ExecutionEngine(BaseEngine):
    """Engine 18. Opportunity chain, runtime stage 4, after engine 16.

    Not a gate: `is_gate = False`. It has no criteria of its own, which is the point —
    everything that could refuse this trade already ran.
    """

    name = "execution"
    number = 18
    is_gate = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()
        intent = self._intent(state)
        pair = str(_require(intent, "pair", f"{DECISION_KEY}.{INTENT_FIELD}"))
        bar_ts = int(_require(intent, "closed_bar_ts", f"{DECISION_KEY}.{INTENT_FIELD}"))
        qty = _money(
            _require(intent, "qty", f"{DECISION_KEY}.{INTENT_FIELD}"),
            f"{DECISION_KEY}.{INTENT_FIELD}.qty",
        )
        userref = userref_for(pair, bar_ts)

        found = self._already_placed(context, pair, userref)
        if found is not None:
            return EngineResult(
                engine=self.name,
                status=EngineStatus.OK,
                blocks_trading=False,
                data=ExecutionState(
                    pair=pair,
                    userref=userref,
                    placed=False,
                    orders=() if found.row is None else (found.row,),
                    reason_code=found.reason_code,
                ).to_state(),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        limit = self._limit_price(state, pair)
        ack = run_blocking(
            context.clients.kraken.add_order(
                OrderRequest(
                    pair=pair,
                    side=ClientOrderSide.BUY,
                    # Invariant 8, and the only `OrderType` named anywhere in this
                    # module. `test_no_market_order_is_ever_constructed` reads the source
                    # to prove there is no second one.
                    order_type=ClientOrderType.LIMIT,
                    qty=qty,
                    limit_price=limit,
                    post_only=True,
                    userref=userref,
                )
            )
        )
        now = to_micros(context.now)
        rejected = ack.status is OrderAckStatus.REJECTED
        row = {
            "userref": userref,
            "order_id": str(ack.order_id),
            "pair": pair,
            "side": OrderSide.BUY.value,
            "intent": OrderIntent.ENTRY.value,
            "order_type": OrderType.LIMIT.value,
            "oflags": "post",
            "status": (
                OrderStatus.REJECTED.value if rejected else OrderStatus.RESTING.value
            ),
            "qty": money_text(qty),
            "limit_price": money_text(limit),
            "filled_qty": "0",
            "placed_at": now,
        }
        if rejected:
            # A rejection is terminal, and `OrderRow` requires `closed_at` on a terminal
            # status. It is this tick: the exchange refused at the moment of placing.
            row["closed_at"] = now
            row["reason"] = str(ack.reason)
        return self._published(
            row,
            pair,
            userref,
            placed=not rejected,
            started=started,
            reason_code=REASON_POST_ONLY_WOULD_CROSS if rejected else REASON_ENTRY_PLACED,
        )

    # ------------------------------------------------------------------ the result

    def _published(
        self,
        row: dict[str, Any],
        pair: str,
        userref: int,
        *,
        placed: bool,
        started: float,
        reason_code: str,
    ) -> EngineResult:
        """`OK`, always, and **never `PASS`**.

        The orchestrator stops the opportunity chain on a `PASS`, which downstream reads
        as "nothing to do here". An order that was just placed is the opposite of nothing
        to do, and engine 21 runs in the manage chain on the same tick expecting to see
        it. `OK` with `placed` carrying the fact is the shape that says both.
        """
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=ExecutionState(
                pair=pair,
                userref=userref,
                placed=placed,
                orders=(row,),
                reason_code=reason_code,
            ).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ inputs

    @staticmethod
    def _intent(state: State) -> dict[str, Any]:
        """Engine 16's order intent, or nothing at all.

        Engine 16 is a gate and publishes **no intent** on any block, so the chain does
        not reach here without one. An absent intent is therefore the chain contradicting
        itself, which is a raise and not a quiet skip — spec 91 step 2 in as many words:
        "absent means no approval — raise, never default".
        """
        decision = state.get(DECISION_KEY)
        if not isinstance(decision, dict) or INTENT_FIELD not in decision:
            raise ExecutionError(
                f"{DECISION_KEY}.{INTENT_FIELD} is absent: engine 16 approved nothing, "
                "so there is no order to place and nothing to default to"
            )
        intent = decision[INTENT_FIELD]
        if not isinstance(intent, dict):
            raise ExecutionError(f"{DECISION_KEY}.{INTENT_FIELD} is not a mapping")
        return intent

    def _limit_price(self, state: State, pair: str) -> Decimal:
        """The best bid on the pair's price grid, rounded down. See the module docstring."""
        quotes = _require(state.get(MARKET_SENSOR_KEY), QUOTES_FIELD, MARKET_SENSOR_KEY)
        where = f"{MARKET_SENSOR_KEY}.{QUOTES_FIELD}"
        quote = _require(quotes, pair, where)
        bid = _money(_require(quote, QUOTE_BID_FIELD, f"{where}.{pair}"), f"{where}.{pair}.bid")
        if bid <= 0:
            raise ExecutionError(
                f"{where}.{pair}.bid is {bid}: engine 3 published no usable price"
            )

        rules = _require(state.get(EXCHANGE_KEY), PAIR_RULES_KEY, EXCHANGE_KEY)
        pairs = _require(rules, PAIR_RULES_PAIRS_KEY, f"{EXCHANGE_KEY}.{PAIR_RULES_KEY}")
        rule = _require(pairs, pair, f"{EXCHANGE_KEY}.{PAIR_RULES_KEY}.{PAIR_RULES_PAIRS_KEY}")
        decimals = int(_require(rule, PAIR_DECIMALS_FIELD, f"pair rules for {pair}"))

        limit = round_down_to_tick(bid, decimals)
        if limit <= 0:
            raise ExecutionError(
                f"the best bid {bid} rounds to {limit} on a {decimals}-decimal grid, "
                "which is not a price an order can rest at"
            )
        return limit

    # ------------------------------------------------------------------ invariant 8

    def _already_placed(
        self, context: EngineContext, pair: str, userref: int
    ) -> _AlreadyPlaced | None:
        """What is already known about this `userref`, or None if nothing is.

        A collision — the same `userref` on a **different** pair — raises. It is a defect
        in `userref_for`, not a condition to work around, and the alternative is placing
        this candidate's order under an identifier that already belongs to another pair's,
        after which neither can be cancelled by `userref` with any confidence.
        """
        store = getattr(context.clients, "store", None)
        if store is None:
            raise ExecutionError("clients.store is not available, so invariant 8 cannot be met")
        recorded = store.order_by_userref(userref)
        if recorded is not None:
            if str(recorded.pair) != pair:
                raise ExecutionError(
                    f"userref {userref} is already recorded against {recorded.pair} and "
                    f"this candidate is {pair}: a collision is a defect, not a retry"
                )
            return _AlreadyPlaced(
                row={
                    "userref": int(recorded.userref),
                    "order_id": recorded.order_id,
                    "pair": str(recorded.pair),
                    "side": str(recorded.side),
                    "intent": str(recorded.intent),
                    "order_type": str(recorded.order_type),
                    "oflags": recorded.oflags,
                    "status": str(recorded.status),
                    "qty": money_text(recorded.qty),
                    "limit_price": (
                        None
                        if recorded.limit_price is None
                        else money_text(recorded.limit_price)
                    ),
                    "filled_qty": money_text(recorded.filled_qty),
                    "placed_at": int(recorded.placed_at),
                },
                reason_code=REASON_ENTRY_ALREADY_PLACED,
            )

        # The second probe. `open_orders()` and not `query_orders([userref])` — the
        # module docstring says why at length, and the short version is that
        # `query_orders` answers "never heard of it" and "cannot reach the exchange"
        # with one exception, and those two require opposite actions.
        for order in run_blocking(context.clients.kraken.open_orders()):
            if int(order.userref) == userref:
                return self._unrecorded(order, pair, userref)
        return None

    @staticmethod
    def _unrecorded(order: Any, pair: str, userref: int) -> _AlreadyPlaced:
        """Describe an order the exchange holds and the store has never heard of.

        **This published nothing until 2026-09-16**, because `OrderState` carried no
        `qty`, no `limit_price` and no placement time, and all three could only have
        been guessed — from this tick's approved quantity, this tick's best bid and
        this tick's clock, every one of them wrong the moment equity, the book or the
        hour moved. A's spec 84 amendment added `qty`, `limit_price` and `opened_at`
        for exactly this case, so the numbers are read rather than invented.

        Publishing the row is what closes the gap that mattered: an order nothing
        recorded is an order **nothing will ever cancel**, because engine 21 assembles
        entries from the store plus `state["execution"]`. That is unmanaged exposure
        and it is the failure invariant 8 exists to prevent. With `opened_at` carrying
        the real placement time, engine 21 then cancels it in the **ordinary** unfilled
        window rather than one window late.

        `pair`, `side`, `intent`, `order_type` and `oflags` are filled from what this
        engine structurally knows rather than from anything observed, and that is the
        distinction the operator's ruling draws: invariant 8 makes every entry a
        post-only buy limit, the `userref` is `userref_for(pair, bar)` so an order
        resting under it is this candidate's pair by construction, and a `userref`
        recorded against a different pair already raises as a collision two branches
        above. Substituting a *market observation* would be the fabrication; restating
        the system's own contract is not.

        **Two refusals, and neither raises.** Both publish no row under their own
        reason code, leave the `userref` in the payload so an operator can find the
        order by hand, and abandon the candidate for the tick:

        * **no `limit_price`.** `OrderState` deliberately carries no `order_type` —
          the presence of a limit price is a total discriminator and a second field
          holding the same bit is one more thing that can disagree — so the model
          cannot refuse this and the consumer that knows what it asked for must. An
          entry with no limit price is the exchange contradicting the placement.
        * **no `opened_at`.** The exchange did not say when the order opened, and a
          clock reading substituted here is a time that never happened written into
          the column research and the console read as a placement time. `OrderRow`
          carries no `fallbacks_used`, so there is nowhere to record the substitution
          either — the `trades` table has that column and `orders` does not.

        **Neither is an `ERROR`, by the lead's ruling of 2026-09-16, and the reason is
        the circuit breaker.** Contract rule 7 would turn a raise into `ERROR`, engine
        19 writes `block_records.status = 'ERROR'`, and engine 17 `safety` counts those
        against `safety.max_errors_in_window` and freezes the account. An exchange
        contradicting itself about one order is not the system malfunctioning and must
        not spend the breaker's budget.
        """
        if order.limit_price is None:
            return _AlreadyPlaced(row=None, reason_code=REASON_ENTRY_NOT_A_LIMIT)
        if order.opened_at is None:
            return _AlreadyPlaced(row=None, reason_code=REASON_ENTRY_UNRECORDED)
        return _AlreadyPlaced(
            row={
                "userref": userref,
                "order_id": str(order.order_id),
                "pair": pair,
                "side": OrderSide.BUY.value,
                "intent": OrderIntent.ENTRY.value,
                "order_type": OrderType.LIMIT.value,
                "oflags": "post",
                "status": OrderStatus(str(order.status)).value,
                "qty": money_text(order.qty),
                "limit_price": money_text(order.limit_price),
                "filled_qty": money_text(order.filled_qty),
                "placed_at": int(order.opened_at),
            },
            reason_code=REASON_ENTRY_RECOVERED,
        )


def order_types_named_in_this_module() -> set[str]:
    """Every order-type member this module's source references, by AST rather than text.

    Exported so `tests/engines/test_execution.py` can assert invariant 8 structurally
    instead of behaviourally. A behavioural test can only prove that the paths it drove
    placed no market order; this proves there is no path that could, including one added
    later under a flag nobody drove. Walking the AST rather than the text is what lets
    the docstrings above talk about market orders — the thing that must not exist is a
    reference, not a mention.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"OrderType", "ClientOrderType"}
    }
