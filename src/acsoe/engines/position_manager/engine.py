"""Engine 21 `position_manager` — what happens to a position after it is opened.

Manage chain, first, **every tick and in every mode**. The opportunity chain runs on one
tick in fifteen and stops at the first gate that refuses; the manage chain never stops
and never skips, because a position that exists has to be watched on every tick whether
or not anything new is being considered.

Five things happen here, in this order, and the order is part of the behaviour:

1. **Resting entries that filled become positions.** Fills come from the client's
   `query_orders`, never from a price comparison of our own — in paper mode the broker
   decides, in live mode the exchange does, and this engine must not be a third opinion.
2. **Entries that outran their window are cancelled.** Never replaced and never chased.
3. **Open positions are marked to the market**, at the bid.
4. **Barriers are decided** — stop, target or timeout — and published for engine 22.
5. **`close_intent` cancels every resting entry**, regardless of its window.

## Where each number comes from, and why it is two publishers

The mark is `quotes[pair]["bid"]` and the barrier test is `trade_ranges[pair]`, and they
are deliberately different readings of the same market.

A **mark** is a valuation: what would this position fetch if it were sold right now. The
bid is that, and the ask is not — the ask is a price nobody is offering to pay.

A **barrier** is an event: did the market *trade* at my stop between the last tick and
this one. A quote sampled once a minute cannot answer it. Two ticks 60 seconds apart see
two prices and the market did everything in between, so a stop touched at second 30 and
recovered by second 59 is invisible to a quote comparison and is exactly the case a stop
exists for. Spec 85's `trade_ranges` is the record of that interval, and its `low` and
`high` are **traded** prices, so a book that quoted 100 and never traded there did not
touch 100.

## The hold, and the one thing it does not suppress

When `state["trading_blocked_by"] == "data_guard"` and `close_intent` is not set, no
barrier is decided and `triggered` is empty. A trigger computed from data engine 4 has
just rejected is a fabricated trigger acting on real money.

**The stale-entry cancel still happens during a hold.** Invariant 8 says so in as many
words: it is a decision about elapsed time, it reads `context.now`, it needs no market
data, and it reduces exposure. Suppressing it would leave a post-only buy on the book
through a blackout, which is the thing invariant 14 escalates over.

**A block by any other engine does not hold.** A `cost` or `safety` block is a statement
about whether to *open* something. A position already open is still managed.

**A liquidation never holds**, and `hold_reason` is null throughout one.

## Barriers are measured from the fill

`target_price` and `stop_price` come from the price actually paid, not from the decision
bar's close the training label was measured against.

**Lead ruling, and it is flagged to the operator as overturnable.** The reason is engine
11: it sized the quantity by dividing the risk budget by the stop *distance*, and that
distance was taken from the entry price. A stop placed from any other price risks a
different amount of money than the one the risk gate approved — which is the gate being
silently overridden by an arithmetic detail. The cost is that a live trade's barriers and
its label's barriers are not identical when the fill differs from the bar close, so the
live outcome and the labelled outcome can disagree on a marginal bar. That is recorded in
the README rather than left for the first person who compares them.

## Two `OrderStatus` enums, and this module touches both

`acsoe.clients.store.contracts.OrderStatus` is what an `OrderRow` carries.
`acsoe.clients.kraken.contracts.OrderStatus` is what A's `OrderState` carries. They have the
same five spellings, they compare equal with `==`, and they are **different objects**, so
`is` between them is always `False`.

This engine reads the second and writes the first, so it imports both: the client's is
`ClientOrderStatus` and is used for every comparison against something `query_orders` or
`cancel_order` returned; the store's keeps its name and appears only in the row payloads
published for engine 19. Comparison stays identity rather than `==` — `==` would also have
silently accepted a bare string from anywhere, which is the shape that hid this the first
time. It cost thirteen red tests and a fail-open on the kill switch; the account is in the
build log for 2026-09-16.

## What it never does

It places no exit — engine 22 does — and writes no relational row — engine 19 does. It
reads last tick's decisions from the **store**, never from `state`, because `state` is
rebuilt every tick and an engine is stateless across cycles.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

from acsoe.clients.kraken.contracts import OrderStatus as ClientOrderStatus
from acsoe.clients.store.contracts import (
    MICROSECONDS_PER_SECOND,
    OrderIntent,
    OrderStatus,
    PositionStatus,
    to_micros,
)
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.position_manager.contracts import (
    BARRIER_FIELD,
    CLOSE_INTENT_FIELD,
    DATA_GUARD_NAME,
    EXCHANGE_KEY,
    EXCHANGE_PAIR_RULES_KEY,
    EXECUTION_KEY,
    EXECUTION_ORDERS_FIELD,
    HOLD_DATA_GUARD_BLOCKED,
    MARKET_SENSOR_KEY,
    PAIR_RULES_PAIRS_KEY,
    POSITION_ID_FIELD,
    QUOTE_BID_FIELD,
    QUOTES_FIELD,
    REASON_POSITION_UNRECORDABLE,
    SYSTEM_KEY,
    TRADE_RANGE_HIGH_FIELD,
    TRADE_RANGE_LOW_FIELD,
    TRADE_RANGES_FIELD,
    TRADING_BLOCKED_BY_KEY,
    Barrier,
    ManagedPositions,
    position_id_for,
)
from acsoe.platform.aio import run_blocking

TARGET_PCT_KEY = "barriers.target_pct"
STOP_PCT_KEY = "barriers.stop_pct"
TIMEOUT_BARS_KEY = "barriers.timeout_bars"
DECISION_BAR_S_KEY = "timeframes.decision_bar_s"
ENTRY_WINDOW_KEY = "trading.entry_unfilled_window_s"

__all__ = ["PositionManagerEngine"]


def _config_decimal(context: EngineContext, key: str) -> Decimal:
    """A configured number as an exact `Decimal`, raising on absent or null.

    `repr` for a float, because a YAML scalar like `0.015` parses to a Python float and
    `Decimal(0.015)` is not `0.015`. A null key is OPERATOR REQUIRED and raises rather
    than defaulting: a default here would be a number silently deciding where a stop
    goes.
    """
    value = context.config.get(key)
    if value is None:
        raise ValueError(f"config {key} is null (OPERATOR REQUIRED)")
    try:
        return Decimal(repr(value) if isinstance(value, float) else str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"config {key} is not a number: {value!r}") from exc


def _money(value: Any) -> Decimal:
    """A published decimal string as an exact `Decimal`, refusing a float.

    A float has already lost precision by the time it arrives, so coercing it preserves
    the wrong number exactly. `EngineResult.data` accepts a float, which is the dangerous
    half of that boundary, so the refusal is here rather than assumed upstream.
    """
    if isinstance(value, float):
        raise ValueError("money must never be a float; a price arrived as one")
    return Decimal(str(value))


class PositionManagerEngine(BaseEngine):
    """Engine 21. Manage chain, first. Not a gate: it refuses nothing, it acts."""

    name = "position_manager"
    number = 21
    is_gate = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()
        try:
            payload = self._manage(context, state)
        except Exception as exc:
            # Contract rule 7 would turn this into ERROR with `data={}` anyway. Catching
            # it here means the manage chain still publishes `entry_orders_cancelled`
            # and `hold_reason` — as False and as the reason below — rather than nothing
            # at all, and `False` is what the orchestrator must read on a tick this
            # engine could not complete: absent already means "not finished", and saying
            # so explicitly leaves a reason code beside it.
            failed = ManagedPositions(
                hold_reason=HOLD_DATA_GUARD_BLOCKED if self._held(state) else None,
                reason_code=REASON_POSITION_UNRECORDABLE,
            )
            return EngineResult(
                engine=self.name,
                status=EngineStatus.ERROR,
                reason=f"position_manager could not complete this tick: {exc}",
                data=failed.to_state(),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=payload.to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ state

    @staticmethod
    def _close_intent(state: State) -> bool:
        """Only the boolean `True` is a liquidation.

        The same fail-closed reading spec 81 gave the orchestrator's completion flags,
        applied from the other side: `bool("false")` is `True`, so anything
        text-shaped arriving here would start liquidating an account nobody asked to
        close. Absent is not a liquidation.
        """
        system = state.get(SYSTEM_KEY)
        if not isinstance(system, dict):
            return False
        return system.get(CLOSE_INTENT_FIELD) is True

    def _held(self, state: State) -> bool:
        """`data_guard` blocked and this is not a liquidation."""
        if self._close_intent(state):
            return False
        return state.get(TRADING_BLOCKED_BY_KEY) == DATA_GUARD_NAME

    @staticmethod
    def _store(context: EngineContext) -> Any:
        store = getattr(context.clients, "store", None)
        if store is None:
            raise ValueError("clients.store is not available")
        return store

    @staticmethod
    def _kraken(context: EngineContext) -> Any:
        kraken = getattr(context.clients, "kraken", None)
        if kraken is None:
            raise ValueError("clients.kraken is not available")
        return kraken

    # ------------------------------------------------------------------ the tick

    def _manage(self, context: EngineContext, state: State) -> ManagedPositions:
        store = self._store(context)
        now = to_micros(context.now)
        close_intent = self._close_intent(state)
        held = self._held(state)

        entries = self._resting_entries(store, state)
        fills, cancels, unrecordable, still_resting = self._settle_entries(
            context, state, entries, now=now, close_intent=close_intent
        )

        positions = list(store.open_positions())
        marked, value, unrealised = self._mark(state, positions, fills)

        triggered: tuple[dict[str, str], ...] = ()
        if not held:
            triggered = self._barriers(context, state, marked, now=now)

        return ManagedPositions(
            positions=tuple(row for _, row in marked),
            orders=tuple(cancels) + tuple(row for row, _ in fills),
            positions_value=value,
            unrealised_pnl=unrealised,
            triggered=triggered,
            hold_reason=HOLD_DATA_GUARD_BLOCKED if held else None,
            # **Only** "nothing is resting any more". A failed cancel leaves something
            # resting and leaves this `False`, and the orchestrator then keeps
            # `close_intent` set and retries on the next tick — which is the retry the
            # kill switch depends on.
            entry_orders_cancelled=not still_resting,
            reason_code=REASON_POSITION_UNRECORDABLE if unrecordable else None,
        )

    # ------------------------------------------------------------------ entries

    def _resting_entries(self, store: Any, state: State) -> list[Any]:
        """Every entry that might still be on the book: the store's, plus this tick's.

        The store is the record, but engine 19 writes at the **end** of the manage chain,
        so an entry engine 18 placed earlier in *this* tick is not there yet. Without the
        second source, a `close_all` arriving on the same tick as a placement would
        report every entry cancelled while one was resting — and the orchestrator would
        clear `close_intent` with a live post-only buy on the book, which invariant 8
        calls the uncancelled order that survives a liquidation and re-opens exposure.
        """
        entries = list(store.resting_orders(intent=OrderIntent.ENTRY))
        known = {int(row.userref) for row in entries}

        execution = state.get(EXECUTION_KEY)
        if not isinstance(execution, dict):
            return entries
        published = execution.get(EXECUTION_ORDERS_FIELD)
        if not isinstance(published, list):
            return entries
        for row in published:
            if not isinstance(row, dict):
                continue
            if str(row.get("status")) != OrderStatus.RESTING.value:
                continue
            if str(row.get("intent")) != OrderIntent.ENTRY.value:
                continue
            userref = int(row["userref"])
            if userref not in known:
                entries.append(_PublishedEntry(row))
                known.add(userref)
        return entries

    def _settle_entries(
        self,
        context: EngineContext,
        state: State,
        entries: list[Any],
        *,
        now: int,
        close_intent: bool,
    ) -> tuple[
        list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]], bool, bool
    ]:
        """Fills, cancels, whether anything was unrecordable, and whether any still rest."""
        if not entries:
            return [], [], False, False

        kraken = self._kraken(context)
        window_s = int(_config_decimal(context, ENTRY_WINDOW_KEY))
        states = {
            int(order.userref): order
            for order in run_blocking(
                kraken.query_orders([int(entry.userref) for entry in entries])
            )
        }

        fills: list[tuple[dict[str, Any], dict[str, Any]]] = []
        cancels: list[dict[str, Any]] = []
        unrecordable = False
        still_resting = False

        for entry in entries:
            current = states.get(int(entry.userref))
            if current is None:
                # Invariant 3: an entry the client will not report on is not an entry
                # that is gone. It stays resting, so `entry_orders_cancelled` stays
                # False and the liquidation is retried.
                still_resting = True
                continue

            if current.status is ClientOrderStatus.FILLED:
                pair_facts = self._pair_facts(state, entry.pair)
                if pair_facts is None:
                    # The fill is real and the position cannot be *described*: `base`
                    # and `quote` come from `AssetPairs` and nothing published it this
                    # tick. Publishing the order row alone would record the entry as
                    # filled with no position against it — money spent and nothing
                    # holding it. So **nothing at all** is published for this order: it
                    # stays resting in the store, and next tick `query_orders` reports
                    # the same fill and it is recorded then. Invariant 2 gives pair
                    # rules no fallback in any mode.
                    unrecordable = True
                    still_resting = True
                    continue
                fills.append(self._fill(context, entry, current, pair_facts))
                continue

            if current.status is not ClientOrderStatus.RESTING:
                # Already cancelled, rejected or expired at the exchange. Engine 19 has
                # the terminal row or will get it from whoever cancelled; nothing to do
                # and nothing resting.
                continue

            expired = now - int(entry.placed_at) >= window_s * MICROSECONDS_PER_SECOND
            if close_intent or expired:
                cancelled = run_blocking(kraken.cancel_order(int(entry.userref)))
                if cancelled.status is ClientOrderStatus.CANCELLED:
                    cancels.append(self._cancelled_row(entry, cancelled, now))
                    continue
                if cancelled.status is ClientOrderStatus.FILLED:
                    # It filled between the query and the cancel. Not an error and not a
                    # cancellation: the money is spent, and reporting `cancelled` here
                    # would lose a real position.
                    pair_facts = self._pair_facts(state, entry.pair)
                    if pair_facts is None:
                        unrecordable = True
                        still_resting = True
                        continue
                    fills.append(self._fill(context, entry, cancelled, pair_facts))
                    continue
                still_resting = True
                continue
            still_resting = True

        return fills, cancels, unrecordable, still_resting

    def _fill(
        self,
        context: EngineContext,
        entry: Any,
        filled: Any,
        pair_facts: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """The order row and the position row one fill produces.

        The barriers are computed from `avg_fill_price` — the price actually paid — for
        the reason in the module docstring: engine 11 sized the quantity against the stop
        *distance* from that price, and a stop placed from another one risks a different
        amount of money than the gate approved.
        """
        entry_price = _money(filled.avg_fill_price)
        target_pct = _config_decimal(context, TARGET_PCT_KEY)
        stop_pct = _config_decimal(context, STOP_PCT_KEY)
        timeout_bars = int(_config_decimal(context, TIMEOUT_BARS_KEY))
        bar_s = int(_config_decimal(context, DECISION_BAR_S_KEY))
        filled_at = int(filled.closed_at)

        order_row: dict[str, Any] = {
            "userref": int(entry.userref),
            "order_id": str(filled.order_id),
            "position_id": position_id_for(int(entry.userref)),
            "pair": str(entry.pair),
            "side": "buy",
            "intent": OrderIntent.ENTRY.value,
            "order_type": "limit",
            "oflags": "post",
            "status": OrderStatus.FILLED.value,
            "qty": format(_money(entry.qty), "f"),
            "limit_price": format(_money(entry.limit_price), "f"),
            "filled_qty": format(_money(filled.filled_qty), "f"),
            "avg_fill_price": format(entry_price, "f"),
            "fee": format(_money(filled.fee), "f"),
            "placed_at": int(entry.placed_at),
            "closed_at": filled_at,
        }
        position_row: dict[str, Any] = {
            "position_id": position_id_for(int(entry.userref)),
            "pair": str(entry.pair),
            "base": str(pair_facts["base"]),
            "quote": str(pair_facts["quote"]),
            "side": "long",
            "status": PositionStatus.OPEN.value,
            "qty": format(_money(filled.filled_qty), "f"),
            "entry_price": format(entry_price, "f"),
            "target_price": format(entry_price * (Decimal(1) + target_pct), "f"),
            "stop_price": format(entry_price * (Decimal(1) - stop_pct), "f"),
            "timeout_at": filled_at + timeout_bars * bar_s * MICROSECONDS_PER_SECOND,
            "entry_userref": int(entry.userref),
            "opened_at": filled_at,
        }
        return order_row, position_row

    @staticmethod
    def _cancelled_row(entry: Any, cancelled: Any, now: int) -> dict[str, Any]:
        return {
            "userref": int(entry.userref),
            "order_id": str(cancelled.order_id),
            "pair": str(entry.pair),
            "side": "buy",
            "intent": OrderIntent.ENTRY.value,
            "order_type": "limit",
            "oflags": "post",
            "status": OrderStatus.CANCELLED.value,
            "qty": format(_money(entry.qty), "f"),
            "limit_price": format(_money(entry.limit_price), "f"),
            "filled_qty": "0",
            "placed_at": int(entry.placed_at),
            "closed_at": int(cancelled.closed_at) if cancelled.closed_at else now,
        }

    # ------------------------------------------------------------------ marking

    @staticmethod
    def _pair_facts(state: State, pair: str) -> dict[str, Any] | None:
        exchange = state.get(EXCHANGE_KEY)
        if not isinstance(exchange, dict):
            return None
        rules = exchange.get(EXCHANGE_PAIR_RULES_KEY)
        if not isinstance(rules, dict):
            return None
        pairs = rules.get(PAIR_RULES_PAIRS_KEY)
        if not isinstance(pairs, dict):
            return None
        facts = pairs.get(pair)
        return facts if isinstance(facts, dict) else None

    @staticmethod
    def _bid(state: State, pair: str) -> Decimal | None:
        sensor = state.get(MARKET_SENSOR_KEY)
        if not isinstance(sensor, dict):
            return None
        quotes = sensor.get(QUOTES_FIELD)
        if not isinstance(quotes, dict):
            return None
        quote = quotes.get(pair)
        if not isinstance(quote, dict) or quote.get(QUOTE_BID_FIELD) is None:
            return None
        bid = _money(quote[QUOTE_BID_FIELD])
        # A non-positive bid is not a cheap market, it is an unusable quote, and marking
        # against it would report a position worth nothing.
        return bid if bid > 0 else None

    def _mark(
        self,
        state: State,
        positions: list[Any],
        fills: list[tuple[dict[str, Any], dict[str, Any]]],
    ) -> tuple[list[tuple[Any, dict[str, Any]]], Decimal | None, Decimal | None]:
        """Every open position, marked at the bid, plus the two portfolio totals.

        **The totals are absent, never zero, if any position could not be marked.** A
        partial sum is worse than no sum: engine 19 would write it into `equity_snapshots`
        as the account's whole value, `peak_equity` would keep the real figure, and the
        difference is a drawdown engine 17 acts on. An absent field makes engine 19 skip
        the row, which is the behaviour its own docstring describes.

        Positions opened by a fill on *this* tick are included in the totals but are not
        re-marked: they are worth what was just paid for them, and `last_price` on a
        position that has existed for no time is the fill price.
        """
        marked: list[tuple[Any, dict[str, Any]]] = []
        value = Decimal(0)
        unrealised = Decimal(0)
        complete = True

        for position in positions:
            row: dict[str, Any] = {
                "position_id": str(position.position_id),
                "pair": str(position.pair),
                "base": str(position.base),
                "quote": str(position.quote),
                "side": str(position.side),
                "status": PositionStatus.OPEN.value,
                "qty": format(position.qty, "f"),
                "entry_price": format(position.entry_price, "f"),
                "target_price": format(position.target_price, "f"),
                "stop_price": format(position.stop_price, "f"),
                "timeout_at": int(position.timeout_at),
                "entry_userref": position.entry_userref,
                "opened_at": int(position.opened_at),
            }
            bid = self._bid(state, str(position.pair))
            if bid is None:
                complete = False
            else:
                row["last_price"] = format(bid, "f")
                row["unrealised_pnl"] = format(position.qty * (bid - position.entry_price), "f")
                value += position.qty * bid
                unrealised += position.qty * (bid - position.entry_price)
            marked.append((position, row))

        for _, position_row in fills:
            qty = Decimal(str(position_row["qty"]))
            entry_price = Decimal(str(position_row["entry_price"]))
            value += qty * entry_price
            marked.append((_FilledPosition(position_row), position_row))

        if not complete:
            return marked, None, None
        return marked, value, unrealised

    # ------------------------------------------------------------------ barriers

    def _barriers(
        self,
        context: EngineContext,
        state: State,
        marked: list[tuple[Any, dict[str, Any]]],
        *,
        now: int,
    ) -> tuple[dict[str, str], ...]:
        """Which positions reached a barrier this tick.

        **Stop wins when both were touched in one tick.** The same rule the training
        labels use, and for the same reason: within one tick the order of the two prints
        is unknown, and resolving the ambiguity to `target` would count as a win a trade
        that may well have stopped out first. Resolving it to `stop` cannot flatter the
        strategy, and it keeps the live outcome and the label computed the same way,
        which is the only thing that makes the backtest comparable.

        A pair with **no** `trade_ranges` entry did not trade this tick. It is absent
        rather than a range of zero — spec 85's `TradeRange` refuses a zero count — so
        no price barrier can fire and only the timeout can.
        """
        sensor = state.get(MARKET_SENSOR_KEY)
        ranges = sensor.get(TRADE_RANGES_FIELD) if isinstance(sensor, dict) else None
        ranges = ranges if isinstance(ranges, dict) else {}

        triggered: list[dict[str, str]] = []
        for position, row in marked:
            pair = str(row["pair"])
            stop_price = Decimal(str(row["stop_price"]))
            target_price = Decimal(str(row["target_price"]))
            traded = ranges.get(pair)

            barrier: str | None = None
            if isinstance(traded, dict):
                low = traded.get(TRADE_RANGE_LOW_FIELD)
                high = traded.get(TRADE_RANGE_HIGH_FIELD)
                if low is not None and _money(low) <= stop_price:
                    barrier = Barrier.STOP
                elif high is not None and _money(high) >= target_price:
                    barrier = Barrier.TARGET
            if barrier is None and now >= int(row["timeout_at"]):
                barrier = Barrier.TIMEOUT
            if barrier is not None:
                triggered.append(
                    {POSITION_ID_FIELD: str(position.position_id), BARRIER_FIELD: barrier}
                )
        _ = context
        return tuple(triggered)


class _PublishedEntry:
    """An entry engine 18 placed on this tick, before engine 19 recorded it.

    A thin view over the published payload so `_settle_entries` has one shape to read
    whether the entry came from the store or from `state`. Not a store row: the payload
    deliberately carries no `run_id` or `cycle_id`, because engine 19 sets those.
    """

    __slots__ = ("limit_price", "pair", "placed_at", "qty", "userref")

    def __init__(self, row: dict[str, Any]) -> None:
        self.userref = int(row["userref"])
        self.pair = str(row["pair"])
        self.qty = _money(row["qty"])
        self.limit_price = _money(row["limit_price"])
        self.placed_at = int(row["placed_at"])


class _FilledPosition:
    """A position opened on this tick, for the barrier walk's `position_id`."""

    __slots__ = ("position_id",)

    def __init__(self, row: dict[str, Any]) -> None:
        self.position_id = str(row["position_id"])
