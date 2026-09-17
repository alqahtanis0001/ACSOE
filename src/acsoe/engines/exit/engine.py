"""Engine 22 `exit` — the only engine in this system that sells.

Manage chain, after engine 21 and before engine 19, **every tick and in every mode**.

Three things happen here and the order is the behaviour:

1. **A liquidation sells everything.** `close_intent` set means every open position in
   the store, as a market sell, whatever the guard said and whatever the exchange is
   answering. Invariant 14, and the whole of it.
2. **An ordinary tick sells what engine 21 triggered**, and nothing else. Engine 22
   decides no barrier of its own — it reads `state["position_manager"]["triggered"]` —
   so the two engines cannot disagree about whether a stop was touched.
3. **A `data_guard` tick sells nothing at all**, unless it is a liquidation.

## Every exit is a taker, in Phase 6, and that is a recorded choice

Invariant 8 **permits** a maker exit on target and requires an immediate one on stop.
Phase 6 takes every exit as a market sell, including on target. Two reasons, and neither
is that it is easier: invariant 5's friction already assumes a taker exit when it prices
the hurdle, so a maker target exit would make every trade cheaper than the gate that
approved it priced — never a defect in itself, but it means no trade is *rejected* for
the want of it. And a resting maker exit is a second order to manage, cancel and
reconcile, with its own window and its own failure to survive a restart, for a saving
the gate never counted on. Written here so nobody reads it as an oversight.

## The hold, and why it is belt and braces

When `state["trading_blocked_by"] == "data_guard"` and `close_intent` is not set, this
engine places **no exit of any kind** — not a target, not a stop, not a timeout — and
publishes `data_guard_blocked`.

Engine 21 already publishes no `triggered` entries on such a tick, so this check is a
second lock on one door. It is here on purpose. A trigger computed from data engine 4
has just rejected is a fabricated trigger acting on real money, and the cost of the
duplicate check is one comparison against the cost of an engine 21 defect reaching the
exchange. `engine-contracts.md` states the hold of engines 21 **and** 22, not of 21
alone.

## Invariant 14: what a liquidation overrides, and what it does not

**A `data_guard` block does not hold it.** The system stops reasoning about price
quality and gets flat.

**A failed fetch does not block it, in any mode.** This is the case that matters and the
easiest to miss: the outage that fires the escalation is the same outage failing the
balance and `AssetPairs` calls, so a liquidation that needed a fresh fetch would be
blocked by the exact condition it exists to answer. During a liquidation and **only**
during one, this engine reads `clients.kraken.last_known_good_asset_pairs` — the cached
`AssetPairs` metadata **past its TTL**, which is the one place in the system where a
stale cache may be read — and records `asset_pairs_last_known_good` on the resulting
trade.

What still holds:

- **Quantities are still rounded down**, with the cached `lot_decimals`. Rounding up
  produces an order the exchange rejects, and a rejected order during an emergency is
  worse than dust.
- **Every order still carries a `userref` and is still checked for idempotency.** A
  liquidation that double-sells is not a liquidation.
- **The override applies only to exiting.** Nothing here opens, adds to or re-enters a
  position, and no gate is relaxed for a new one.
- **No fee is ever invented.** If the fee tier cannot be fetched the fill raises, this
  engine records the position as not closed, `positions_closed` stays `False` and the
  liquidation is retried. Spec 93's scope limit and spec 88's are the same limit from
  either side, and `AGENTS.md`'s first paragraph forbids the alternative.

**This engine never reads a balance**, and `contracts.py` says at length why the
`balance_last_known_good` fallback spec 93 names is therefore not defined. An exit's
quantity is the position's.

## Two `OrderStatus` enums, and this module touches both

`acsoe.clients.store.contracts.OrderStatus` is what an `OrderRow` carries;
`acsoe.clients.kraken.contracts.OrderStatus` is what an `OrderState` carries. Same five
spellings, equal under `==`, never identical, so `is` between them is always `False`.
Engine 21 lost thirteen tests and published `entry_orders_cancelled: True` over a live
post-only buy before that was written down. Here the client's is imported as
`ClientOrderStatus` and compared only against client answers; the store's keeps its name
and appears only in the row payloads published for engine 19.

## What it never does

It decides no barrier — engine 21 does — and writes no relational row — engine 19 does.
It reads the store for positions rather than `state`, because `state` is rebuilt every
tick and an engine is stateless across cycles.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, NamedTuple

from acsoe.clients.kraken.contracts import OrderRequest
from acsoe.clients.kraken.contracts import OrderSide as ClientOrderSide
from acsoe.clients.kraken.contracts import OrderStatus as ClientOrderStatus
from acsoe.clients.kraken.contracts import OrderType as ClientOrderType
from acsoe.clients.store.contracts import (
    OrderIntent,
    OrderStatus,
    PositionStatus,
    TradeOutcome,
    to_micros,
)
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.exit.contracts import (
    CLOSE_INTENT_FIELD,
    DATA_GUARD_NAME,
    EXCHANGE_KEY,
    EXCHANGE_PAIR_RULES_KEY,
    FALLBACK_ASSET_PAIRS_RETAINED,
    LOT_DECIMALS_FIELD,
    NET_PROCEEDS_FIELD,
    PAIR_RULES_PAIRS_KEY,
    POSITION_ID_FIELD,
    POSITION_MANAGER_KEY,
    REASON_DATA_GUARD_BLOCKED,
    REASON_EXIT_ALREADY_PLACED,
    REASON_EXIT_INCOMPLETE,
    REASON_EXITS_PLACED,
    REASON_NOTHING_TO_EXIT,
    SYSTEM_KEY,
    TRADING_BLOCKED_BY_KEY,
    TRIGGERED_BARRIER_FIELD,
    TRIGGERED_FIELD,
    ExitState,
    exit_userref_for,
    round_down_to_lot,
    trade_id_for,
)
from acsoe.platform.aio import run_blocking

REPORTING_CURRENCY_KEY = "trading.base_reporting_currency"

__all__ = ["ExitEngine", "ExitError"]


class ExitError(RuntimeError):
    """One position could not be exited, or the engine could not run at all.

    Raised rather than returned, because engine 22 is not a gate and has no refusal of
    its own to publish. A position it cannot exit is recorded as still open and the
    liquidation is retried; it is never reported as closed.
    """


class _Exit(NamedTuple):
    """One position to get out of, and why."""

    position: Any
    outcome: TradeOutcome


def _money(value: Any) -> Decimal:
    """A published decimal string as an exact `Decimal`, refusing a float.

    `EngineResult.data` accepts a float and refuses a `Decimal`, which is the dangerous
    half of that boundary, so the refusal is here rather than assumed upstream.
    """
    if isinstance(value, float):
        raise ExitError("money must never be a float; a price arrived as one")
    return Decimal(str(value))


def _config_str(context: EngineContext, key: str) -> str:
    value = context.config.get(key)
    if value is None or not str(value).strip():
        raise ExitError(f"config {key} is null (OPERATOR REQUIRED)")
    return str(value)


class ExitEngine(BaseEngine):
    """Engine 22. Manage chain, after 21. Not a gate: it refuses nothing, it acts."""

    name = "exit"
    number = 22
    is_gate = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()
        try:
            payload, problems = self._exit(context, state)
        except Exception as exc:
            # Contract rule 7 would give `data={}` and the orchestrator reads an absent
            # `positions_closed` as "not finished" — which is right. Publishing the
            # explicit `False` anyway leaves a reason code beside it, so the operator
            # sees *why* a liquidation did not complete rather than only that it did
            # not. The same shape engine 21 uses.
            failed = ExitState(positions_closed=False, reason_code=REASON_EXIT_INCOMPLETE)
            return EngineResult(
                engine=self.name,
                status=EngineStatus.ERROR,
                reason=f"exit could not complete this tick: {exc}",
                data=failed.to_state(),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        status = (
            EngineStatus.ERROR
            if payload.reason_code == REASON_EXIT_INCOMPLETE
            else EngineStatus.OK
        )
        return EngineResult(
            engine=self.name,
            status=status,
            blocks_trading=False,
            # **The failures are named, not counted.** A per-position exception is
            # caught so the other positions are still liquidated, and swallowing the
            # message with it would leave an operator holding "exit_incomplete" and no
            # way to tell a missing fee tier from a foreign quote currency from an
            # order the exchange refused. Found by mutation: removing the entry-fee
            # guard left every assertion green, because the next line raised a
            # `TypeError` instead and both arrive as the same reason code.
            reason=(
                "exit could not get out of every position it was asked to: "
                + "; ".join(problems)
                if status is EngineStatus.ERROR
                else None
            ),
            data=payload.to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ state

    @staticmethod
    def _close_intent(state: State) -> bool:
        """Only the boolean `True` is a liquidation.

        Spec 81's fail-closed reading, applied from the publisher's side: `bool("false")`
        is `True`, so anything text-shaped arriving here would start selling an account
        nobody asked to close. Absent is not a liquidation.
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
    def _client(context: EngineContext, name: str) -> Any:
        client = getattr(context.clients, name, None)
        if client is None:
            raise ExitError(f"clients.{name} is not available")
        return client

    # ------------------------------------------------------------------ the tick

    def _exit(
        self, context: EngineContext, state: State
    ) -> tuple[ExitState, tuple[str, ...]]:
        store = self._client(context, "store")
        close_intent = self._close_intent(state)

        if self._held(state):
            # No exit of any kind. `positions_closed` is False and not "there is nothing
            # to close": a held tick has not finished anything, and the orchestrator's
            # fail-closed read of this flag is what keeps a liquidation alive across it.
            return (
                ExitState(
                    positions_closed=False, reason_code=REASON_DATA_GUARD_BLOCKED
                ),
                (),
            )

        wanted = self._wanted(store, state, close_intent=close_intent)
        if not wanted:
            # Nothing triggered and no liquidation. `positions_closed` is still computed
            # from the store rather than hardcoded: a `close_all` on a flat account has
            # nothing to sell and **is** finished, and hardcoding False here would leave
            # `close_intent` set forever on exactly that account.
            return (
                ExitState(
                    positions_closed=not store.open_positions(),
                    reason_code=REASON_NOTHING_TO_EXIT,
                ),
                (),
            )

        orders: list[dict[str, Any]] = []
        positions: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        closed_ids: set[str] = set()
        problems: list[str] = []
        placed_any = False

        for wants in wanted:
            try:
                result = self._sell(context, state, store, wants, close_intent=close_intent)
            except Exception as exc:
                # One position that cannot be got out of must not stop the others. On a
                # liquidation, flat on two of three beats flat on none, and the one that
                # failed is reported as still open so the next tick retries it.
                #
                # **The message is kept, not only the fact.** Swallowing it leaves an
                # operator holding `exit_incomplete` with no way to tell a missing fee
                # tier from a foreign quote currency from an order the exchange refused,
                # and every one of those needs a different response during an emergency.
                problems.append(f"{wants.position.position_id}: {exc}")
                continue
            orders.append(result.order)
            placed_any = placed_any or result.placed
            if result.position is None:
                problems.append(
                    f"{wants.position.position_id}: the exit order is "
                    f"{result.order['status']}, so nothing was sold"
                )
                continue
            positions.append(result.position)
            trades.append(result.trade)
            closed_ids.add(str(wants.position.position_id))

        still_open = [
            row
            for row in store.open_positions()
            if str(row.position_id) not in closed_ids
        ]
        if problems:
            reason = REASON_EXIT_INCOMPLETE
        elif placed_any:
            reason = REASON_EXITS_PLACED
        else:
            reason = REASON_EXIT_ALREADY_PLACED
        return (
            ExitState(
                orders=tuple(orders),
                positions=tuple(positions),
                closed_trades=tuple(trades),
                # **Only** "no open position remains". A position this tick could not
                # exit leaves this `False`, the orchestrator keeps `close_intent` set,
                # and the next tick tries again — the retry the kill switch depends on.
                positions_closed=not still_open and not problems,
                reason_code=reason,
            ),
            tuple(problems),
        )

    # ------------------------------------------------------------------ what to sell

    def _wanted(self, store: Any, state: State, *, close_intent: bool) -> list[_Exit]:
        """Every position to get out of this tick.

        A liquidation takes **every open position in the store**, and its outcome is
        `liquidation` rather than whichever barrier a position happened to be near: the
        reason it was sold is the kill switch, and recording a `stop` would put a
        market event in `trades.outcome` that never decided anything.

        An ordinary tick takes engine 21's `triggered` and nothing else. A triggered
        `position_id` the store does not hold is skipped rather than raising — engine 21
        publishes positions opened by *this* tick's fill, and engine 19 records them at
        the end of the chain, so on that one tick the position genuinely is not in the
        store yet and it will be triggered again next tick if the barrier still holds.
        """
        if close_intent:
            return [_Exit(row, TradeOutcome.LIQUIDATION) for row in store.open_positions()]

        manager = state.get(POSITION_MANAGER_KEY)
        entries = manager.get(TRIGGERED_FIELD) if isinstance(manager, dict) else None
        if not isinstance(entries, list):
            return []

        wanted: list[_Exit] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            position = store.position(str(entry[POSITION_ID_FIELD]))
            if position is None or position.status is not PositionStatus.OPEN:
                continue
            wanted.append(_Exit(position, TradeOutcome(str(entry[TRIGGERED_BARRIER_FIELD]))))
        return wanted

    # ------------------------------------------------------------------ one exit

    class _Sold(NamedTuple):
        order: dict[str, Any]
        position: dict[str, Any] | None
        trade: dict[str, Any]
        placed: bool

    def _sell(
        self,
        context: EngineContext,
        state: State,
        store: Any,
        wants: _Exit,
        *,
        close_intent: bool,
    ) -> _Sold:
        """Place (or find) one market sell and describe what it did."""
        kraken = self._client(context, "kraken")
        position = wants.position
        position_id = str(position.position_id)
        userref = exit_userref_for(position_id)
        now = to_micros(context.now)

        decimals, fallbacks = self._lot_decimals(
            context, state, str(position.pair), close_intent=close_intent
        )
        qty = round_down_to_lot(_money(position.qty), decimals)
        if qty <= 0:
            raise ExitError(
                f"{position_id} rounds to {qty} on a {decimals}-decimal lot grid, and "
                "an order for nothing is not an order; the quantity is never rounded up"
            )

        placed = False
        recorded = store.order_by_userref(userref)
        if recorded is not None:
            # Invariant 8. A `userref` this engine would have chosen and did not is a
            # digest collision, and a collision is a defect: selling under an identifier
            # that already belongs to another order means neither can be cancelled or
            # reconciled by `userref` afterwards.
            if str(recorded.position_id) != position_id:
                raise ExitError(
                    f"exit userref {userref} is already recorded against "
                    f"{recorded.position_id!r} and this exit is for {position_id!r}: "
                    "a collision is a defect, not a retry"
                )
        else:
            ack = run_blocking(
                kraken.add_order(
                    OrderRequest(
                        pair=str(position.pair),
                        side=ClientOrderSide.SELL,
                        # Every Phase 6 exit is a taker. The module docstring says why,
                        # and `post_only` is False because a market order cannot carry
                        # Kraken's `oflags=post` at all.
                        order_type=ClientOrderType.MARKET,
                        qty=qty,
                        post_only=False,
                        userref=userref,
                    )
                )
            )
            placed = True
            _ = ack

        current = self._state_of(kraken, userref)
        order_row = self._order_row(position, current, userref=userref, qty=qty, now=now)

        if current.status is not ClientOrderStatus.FILLED:
            # Rejected, still working, or an answer this engine will not interpret. The
            # order row is published so engine 19 records the attempt; the position is
            # not closed and no trade is written, because nothing was sold.
            return self._Sold(order=order_row, position=None, trade={}, placed=placed)

        closed_at = int(current.closed_at) if current.closed_at is not None else now
        exit_price = _money(current.avg_fill_price)
        exit_fee = _money(current.fee)
        entry_fee = self._entry_fee(store, position)

        position_row = self._closed_position_row(position, closed_at, position_id)
        trade_row = self._trade_row(
            context,
            position,
            outcome=wants.outcome,
            qty=_money(current.filled_qty),
            exit_price=exit_price,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            exit_userref=userref,
            closed_at=closed_at,
            fallbacks=fallbacks,
        )
        return self._Sold(
            order=order_row, position=position_row, trade=trade_row, placed=placed
        )

    @staticmethod
    def _state_of(kraken: Any, userref: int) -> Any:
        """Where the exit order stands, through the client's own answer.

        `query_orders` and not the `add_order` ack: an ack says the exchange accepted
        the order, not that it filled, and a market sell's fill price is the one number
        this engine may not compute for itself. Invariant 3 makes an answer that cannot
        be given a raise rather than an empty result, so a short answer here is a defect
        and is treated as one.
        """
        states = run_blocking(kraken.query_orders([userref]))
        for order in states:
            if int(order.userref) == userref:
                return order
        raise ExitError(
            f"the client answered about {len(states)} orders and none of them was "
            f"{userref}; an exit whose state is unknown is not an exit that happened"
        )

    # ------------------------------------------------------------------ pair rules

    def _lot_decimals(
        self,
        context: EngineContext,
        state: State,
        pair: str,
        *,
        close_intent: bool,
    ) -> tuple[int, tuple[str, ...]]:
        """`lot_decimals` for the pair, and the fallbacks used to get it.

        This tick's `AssetPairs` first, from engine 1's payload. On an ordinary tick
        that is the only source and its absence is a refusal: invariant 2 gives pair
        rules no fallback in any mode, because a wrong `lot_decimals` produces an
        invalid order.

        **Only during a liquidation** does the retained snapshot come into it, and then
        it is read past its TTL — the one place in the system where a stale cache is
        acceptable (invariant 14). The fallback is recorded on the trade, so the fill is
        never mistaken for one priced on good data.
        """
        published = self._published_lot_decimals(state, pair)
        if published is not None:
            return published, ()
        if not close_intent:
            raise ExitError(
                f"no pair rules for {pair} this tick, so there is no lot grid to round "
                "onto; retained rules may be read only during a liquidation "
                "(invariant 14)"
            )
        retained = getattr(self._client(context, "kraken"), "last_known_good_asset_pairs", None)
        rule = None if retained is None else retained.value.pairs.get(pair)
        if rule is None:
            raise ExitError(
                f"no pair rules for {pair}, fresh or retained, so the exit quantity "
                "cannot be rounded down and this engine will not guess a grid"
            )
        return int(rule.lot_decimals), (FALLBACK_ASSET_PAIRS_RETAINED,)

    @staticmethod
    def _published_lot_decimals(state: State, pair: str) -> int | None:
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
        if not isinstance(facts, dict) or facts.get(LOT_DECIMALS_FIELD) is None:
            return None
        return int(facts[LOT_DECIMALS_FIELD])

    # ------------------------------------------------------------------ the rows

    @staticmethod
    def _entry_fee(store: Any, position: Any) -> Decimal:
        """What the entry cost, from the order that opened the position.

        Invariant 7 wants the round trip's two fees recorded separately, and this is the
        only place the entry's is available: engine 19 wrote it onto the `orders` row
        when engine 21 reported the fill. A position with no `entry_userref`, or whose
        entry row carries no fee, raises rather than recording a zero — a zero entry fee
        is a trade that looks more profitable than it was, in the series `safety`'s loss
        streak is counted from.
        """
        userref = position.entry_userref
        if userref is None:
            raise ExitError(
                f"{position.position_id} has no entry_userref, so the entry fee cannot "
                "be read and a zero would overstate the round trip"
            )
        row = store.order_by_userref(int(userref))
        if row is None or row.fee is None:
            raise ExitError(
                f"the entry order {userref} for {position.position_id} carries no fee, "
                "so the round trip cannot be priced; a zero would overstate it"
            )
        return Decimal(row.fee)

    @staticmethod
    def _order_row(
        position: Any, current: Any, *, userref: int, qty: Decimal, now: int
    ) -> dict[str, Any]:
        filled = current.filled_qty > 0
        row: dict[str, Any] = {
            "userref": userref,
            "order_id": str(current.order_id),
            "position_id": str(position.position_id),
            "pair": str(position.pair),
            "side": "sell",
            "intent": OrderIntent.EXIT.value,
            "order_type": "market",
            "oflags": "",
            "status": OrderStatus(str(current.status)).value,
            "qty": format(qty, "f"),
            "filled_qty": format(_money(current.filled_qty), "f"),
            "placed_at": now,
        }
        if filled:
            row["avg_fill_price"] = format(_money(current.avg_fill_price), "f")
            row["fee"] = format(_money(current.fee), "f")
        if current.closed_at is not None:
            row["closed_at"] = int(current.closed_at)
        return row

    @staticmethod
    def _closed_position_row(position: Any, closed_at: int, position_id: str) -> dict[str, Any]:
        """The position, closed. Every column engine 19 upserts, because it upserts them
        all: a field left out here is a field set back to null in the database."""
        return {
            "position_id": position_id,
            "pair": str(position.pair),
            "base": str(position.base),
            "quote": str(position.quote),
            "side": str(position.side),
            "status": PositionStatus.CLOSED.value,
            "qty": format(position.qty, "f"),
            "entry_price": format(position.entry_price, "f"),
            "target_price": format(position.target_price, "f"),
            "stop_price": format(position.stop_price, "f"),
            "timeout_at": int(position.timeout_at),
            "entry_userref": position.entry_userref,
            "opened_at": int(position.opened_at),
            "closed_at": closed_at,
            "trade_id": trade_id_for(position_id),
        }

    def _trade_row(
        self,
        context: EngineContext,
        position: Any,
        *,
        outcome: TradeOutcome,
        qty: Decimal,
        exit_price: Decimal,
        entry_fee: Decimal,
        exit_fee: Decimal,
        exit_userref: int,
        closed_at: int,
        fallbacks: tuple[str, ...],
    ) -> dict[str, Any]:
        """One closed round trip, priced in the quote currency and reported in the
        reporting currency.

        **The FX rates are `1` because the quote currency *is* the reporting currency**,
        and that is asserted rather than assumed. Invariant 7 forbids absorbing FX
        exposure into PnL, and engine 11 refuses any pair whose quote is not the
        reporting currency today (`no_fx_rate`), so a position that reaches here with a
        foreign quote is the chain contradicting itself — not a case to price at a rate
        nobody fetched.

        **`net_proceeds` is the sale's own arithmetic** (spec 113): the `proceeds` below
        minus the `exit_fee` below, the same two numbers the row reports. It reads neither
        engine 21's valuation nor engine 1's balance, so engine 19's exit-tick cash cannot
        change because either of them changed how it works.
        """
        reporting = _config_str(context, REPORTING_CURRENCY_KEY)
        quote = str(position.quote)
        if quote != reporting:
            raise ExitError(
                f"{position.position_id} is quoted in {quote} and the reporting "
                f"currency is {reporting}: invariant 7 wants the FX rate recorded per "
                "trade and nothing in this system fetches one, so there is no honest "
                "rate to write (engine 11 refuses such a pair with no_fx_rate)"
            )

        entry_price = Decimal(position.entry_price)
        cost_basis = qty * entry_price
        proceeds = qty * exit_price
        realised = proceeds - cost_basis - entry_fee - exit_fee
        return {
            "trade_id": trade_id_for(str(position.position_id)),
            "position_id": str(position.position_id),
            "pair": str(position.pair),
            "base": str(position.base),
            "quote": quote,
            "side": str(position.side),
            "qty": format(qty, "f"),
            "entry_price": format(entry_price, "f"),
            "exit_price": format(exit_price, "f"),
            "entry_fee": format(entry_fee, "f"),
            "exit_fee": format(exit_fee, "f"),
            NET_PROCEEDS_FIELD: format(proceeds - exit_fee, "f"),
            "entry_userref": position.entry_userref,
            "exit_userref": exit_userref,
            "opened_at": int(position.opened_at),
            "closed_at": closed_at,
            "outcome": outcome.value,
            "realised_pnl": format(realised, "f"),
            "realised_pnl_pct": format(
                realised / cost_basis if cost_basis else Decimal(0), "f"
            ),
            # The quote-currency figure and the reporting-currency figure are the same
            # number while the rates are 1, and they are still both written: invariant 7
            # wants the exposure recorded per trade, and a column that is populated only
            # when it differs is a column nobody can query.
            "realised_pnl_quote": format(realised, "f"),
            "reporting_currency": reporting,
            "fx_rate_entry": "1",
            "fx_rate_exit": "1",
            "fallbacks_used": list(fallbacks),
        }
