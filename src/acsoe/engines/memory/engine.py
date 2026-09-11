"""Engine 19 `memory` — the single writer of relational rows.

**Manage chain, last of the three.** It runs on every tick, in every mode, whatever the
guard chain decided. `position_manager` and `exit` act; this engine records. Nothing
else in the system writes `block_records`, `positions`, `orders`, `trades`,
`rejections` or `equity_snapshots`, and keeping one writer is what makes the manage
chain's "always runs" guarantee sufficient for invariant 12.

## The failure mode this whole engine is arranged around

Engine 17 `safety` derives its outage count from `block_records`. **A missed row does
not fail — it makes the circuit breaker inert, silently, with every test green.** There
is no crash, no red test and no operator-visible symptom. The same is true one table
over: a rejection that does not reach storage counts, under invariant 12, as a defect
equal to a lost trade, and nothing anywhere says so at the time.

So two rules govern the code below, and they read as pedantic until you notice that
every one of them is a defect that leaves the suite green:

**A block record on every blocked tick, candidate or not.** Reading invariant 12 as
"rejections are logged" and writing a row only where a candidate was rejected empties
the table on exactly the ticks the outage counter counts — most blocked ticks never had
a candidate at all, because `data_guard` blocks before the opportunity chain ever runs.

**Absent means nothing-to-record, never record-a-zero.** Engines 18, 21 and 22 are
Phase 6. Their keys are absent today, and an absent key is not a position count of
zero, not an equity of zero, and not a closed trade. A zero equity row in particular is
a 100% drawdown and would trip the breaker on the first tick of a fresh install.

## What it does not do

It reads no clock — `context.now` is already stamped. It constructs no client. It
imports no other engine: every `state` key it reads is named in this package's
`contracts.py`, with the engine that owns it written beside it. It writes exactly one
`state` key, its own. It is not a gate and never blocks.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from acsoe.clients.store.contracts import (
    BlockRecordRow,
    BlockStatus,
    EquitySnapshotRow,
    OrderRow,
    PositionRow,
    RejectionRow,
    TradeRow,
    to_micros,
)
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.memory.contracts import (
    BALANCES_FIELD,
    BLOCK_REASON_KEY,
    CANDIDATE_PAIR_PATH,
    CLOSED_TRADES_FIELD,
    CYCLE_ID_KEY,
    ECONOMICS_FIELDS,
    EXCHANGE_KEY,
    EXIT_KEY,
    GUARD_BLOCKERS_KEY,
    HOLD_REASON_FIELD,
    ORDERS_FIELD,
    POSITION_MANAGER_KEY,
    POSITIONS_FIELD,
    POSITIONS_VALUE_FIELD,
    REASON_CODE_FIELD,
    STATE_KEY,
    TRADING_BLOCKED_BY_KEY,
    WRITTEN_TABLES,
    MemoryState,
    MissingInputError,
    decimal_field,
)

KEY_REPORTING_CURRENCY = "trading.base_reporting_currency"


class MemoryEngine(BaseEngine):
    """Engine 19. Manage chain. Not a gate."""

    name = "memory"
    number = 19
    is_gate = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()
        store = self._store(context)
        cycle_id = self._cycle_id(state)
        ts = to_micros(context.now)
        written = dict.fromkeys(WRITTEN_TABLES, 0)

        written["block_records"] = self._write_block_records(
            store, context, state, cycle_id=cycle_id, ts=ts
        )

        manager = self._payload(state, POSITION_MANAGER_KEY)
        exiting = self._payload(state, EXIT_KEY)
        exchange = self._payload(state, EXCHANGE_KEY)

        # Positions and trades land before the equity snapshot, because the snapshot's
        # `open_position_count` and `realised_pnl_cum` are read back out of the store
        # once this tick's rows are in it. Reordering these is silent.
        written["positions"] = self._write_positions(
            store, context, manager, cycle_id=cycle_id, ts=ts
        )
        written["orders"] = self._write_orders(store, context, manager, cycle_id=cycle_id, ts=ts)
        closed = self._write_trades(store, context, exiting, cycle_id=cycle_id, ts=ts)
        written["trades"] = len(closed)
        written["rejections"] = self._write_rejection(
            store, context, state, cycle_id=cycle_id, ts=ts
        )

        equity, peak, skipped = self._write_equity(
            store,
            context,
            exchange,
            manager,
            closed=closed,
            cycle_id=cycle_id,
            ts=ts,
        )
        written["equity_snapshots"] = 0 if skipped else 1

        published = MemoryState(
            cycle_id=cycle_id,
            run_id=context.run_id,
            written=written,
            sources_present=tuple(
                key
                for key, payload in (
                    (EXCHANGE_KEY, exchange),
                    (POSITION_MANAGER_KEY, manager),
                    (EXIT_KEY, exiting),
                )
                if payload is not None
            ),
            equity=equity,
            peak_equity=peak,
            equity_skipped_reason=skipped,
            hold_reason=self._hold_reason(manager),
        )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=published.to_state_data(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ inputs

    def _store(self, context: EngineContext) -> Any:
        store = getattr(context.clients, "store", None)
        if store is None:
            raise MissingInputError("clients.store is not available; nothing can be recorded")
        return store

    def _cycle_id(self, state: State) -> int:
        """The tick's cycle number, which is not optional.

        A row stamped with the wrong tick is worse than no row: `safety` counts
        *consecutive ticks*, and a block record that cannot say which tick it belongs to
        either merges two outages or splits one.
        """
        cycle_id = state.get(CYCLE_ID_KEY)
        if not isinstance(cycle_id, int) or isinstance(cycle_id, bool):
            raise MissingInputError(
                f"state[{CYCLE_ID_KEY!r}] is {cycle_id!r}; a tick is (run_id, cycle_id) and "
                "a row that cannot name its tick cannot be counted"
            )
        return cycle_id

    def _payload(self, state: State, key: str) -> Mapping[str, Any] | None:
        """One upstream engine's `state` payload, or ``None`` when it did not run.

        ``None`` and ``{}`` are deliberately different answers. An engine that is not in
        the chain yet writes no key at all; an engine that ran and had nothing to say
        writes an empty payload. Only the first means *nothing to record*.
        """
        if key not in state:
            return None
        payload = state[key]
        if payload is None:
            return None
        if not isinstance(payload, Mapping):
            raise MissingInputError(
                f"state[{key!r}] is a {type(payload).__name__}, not a mapping. That is an "
                "engine publishing a shape nothing can read, which is not the same fact "
                "as the engine not having run."
            )
        return payload

    def _hold_reason(self, manager: Mapping[str, Any] | None) -> str | None:
        if manager is None:
            return None
        value = manager.get(HOLD_REASON_FIELD)
        return None if value is None else str(value)

    # --------------------------------------------------------- block_records

    def _write_block_records(
        self,
        store: Any,
        context: EngineContext,
        state: State,
        *,
        cycle_id: int,
        ts: int,
    ) -> int:
        """One row per entry in ``state["guard_blockers"]``, `is_primary` on the first.

        **No row at all when the list is empty.** A row on every tick makes every count
        that reads this table meaningless — the outage run becomes the uptime.

        The unique index `ux_block_records_primary` is `(run_id, cycle_id)`, so a second
        primary row for one tick raises `sqlite3.IntegrityError` at the database. That
        exception is **not caught here**: it is the database refusing to let two engines
        both claim to have gated the opportunity chain, a write that violates it is a
        defect in this engine, and contract rule 7 turns the uncaught exception into an
        `ERROR` result — which is the visible symptom the alternative would suppress.
        """
        blockers = state.get(GUARD_BLOCKERS_KEY)
        if blockers is None:
            raise MissingInputError(
                f"state[{GUARD_BLOCKERS_KEY!r}] is absent. The contract says an empty list "
                "on an unblocked tick, never absent, because absent and empty would "
                "otherwise be the same reading."
            )
        if not isinstance(blockers, Sequence) or isinstance(blockers, (str, bytes)):
            raise MissingInputError(
                f"state[{GUARD_BLOCKERS_KEY!r}] is a {type(blockers).__name__}, not a list"
            )

        for index, entry in enumerate(blockers):
            if not isinstance(entry, Mapping):
                raise MissingInputError(
                    f"guard_blockers[{index}] is a {type(entry).__name__}, not a mapping"
                )
            store.write_block_record(
                BlockRecordRow(
                    cycle_id=cycle_id,
                    run_id=context.run_id,
                    ts=ts,
                    blocked_by=str(entry["engine"]),
                    block_reason=str(entry.get("reason") or ""),
                    # The first blocker is the one that gated the opportunity chain.
                    # Marking every row primary makes the unique index meaningless;
                    # marking none loses which gate actually stopped the tick.
                    is_primary=index == 0,
                    # `EngineStatus` is a `StrEnum` so this reaches the column as
                    # "ERROR" rather than "EngineStatus.ERROR". `safety` counts the
                    # error rate with `status = 'ERROR'`; the mismatch never raises and
                    # the count simply reads zero forever.
                    status=BlockStatus(str(entry["status"])),
                    updated_at=ts,
                )
            )
        return len(blockers)

    # ------------------------------------------------------- positions, orders

    def _rows(self, payload: Mapping[str, Any] | None, field: str) -> list[Mapping[str, Any]]:
        """A list of row payloads an upstream engine published, or an empty list.

        Absent key and absent field both mean *nothing to record*. A present field that
        is not a list means the publisher's shape changed, which is a defect and raises.
        """
        if payload is None or field not in payload:
            return []
        rows = payload[field]
        if rows is None:
            return []
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise MissingInputError(f"{field} is a {type(rows).__name__}, not a list of rows")
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise MissingInputError(
                    f"{field}[{index}] is a {type(row).__name__}, not a mapping"
                )
        return [dict(row) for row in rows]

    def _stamped(
        self, row: Mapping[str, Any], context: EngineContext, *, cycle_id: int, ts: int
    ) -> dict[str, Any]:
        """The publisher's payload, stamped with the tick that recorded it.

        The tick identifiers are this engine's to set, never the publisher's: a row
        carrying somebody else's `run_id` cannot be joined to the block record for the
        tick, and `(run_id, cycle_id)` is the join.
        """
        stamped = dict(row)
        stamped["run_id"] = context.run_id
        stamped["cycle_id"] = cycle_id
        stamped["updated_at"] = ts
        return stamped

    def _write_positions(
        self,
        store: Any,
        context: EngineContext,
        manager: Mapping[str, Any] | None,
        *,
        cycle_id: int,
        ts: int,
    ) -> int:
        rows = self._rows(manager, POSITIONS_FIELD)
        for row in rows:
            store.write_position(
                PositionRow.model_validate(self._stamped(row, context, cycle_id=cycle_id, ts=ts))
            )
        return len(rows)

    def _write_orders(
        self,
        store: Any,
        context: EngineContext,
        manager: Mapping[str, Any] | None,
        *,
        cycle_id: int,
        ts: int,
    ) -> int:
        rows = self._rows(manager, ORDERS_FIELD)
        for row in rows:
            store.write_order(
                OrderRow.model_validate(self._stamped(row, context, cycle_id=cycle_id, ts=ts))
            )
        return len(rows)

    # ----------------------------------------------------------------- trades

    def _write_trades(
        self,
        store: Any,
        context: EngineContext,
        exiting: Mapping[str, Any] | None,
        *,
        cycle_id: int,
        ts: int,
    ) -> list[TradeRow]:
        """One row per closed round trip. Returns them, for the equity snapshot."""
        closed: list[TradeRow] = []
        for row in self._rows(exiting, CLOSED_TRADES_FIELD):
            trade = TradeRow.model_validate(
                self._stamped(row, context, cycle_id=cycle_id, ts=ts)
            )
            store.write_trade(trade)
            closed.append(trade)
        return closed

    # ------------------------------------------------------------- rejections

    def _write_rejection(
        self,
        store: Any,
        context: EngineContext,
        state: State,
        *,
        cycle_id: int,
        ts: int,
    ) -> int:
        """One row for a candidate the **opportunity chain** refused.

        A guard-chain block is not a rejection. A rejection is one *candidate*; a block
        record is one *tick*, and most blocked ticks never had a candidate at all. They
        join on `(run_id, cycle_id)`, which is why both are stamped from the same tick.

        The test for "this was a rejection" is that the blocking engine is not one of
        the tick's guard blockers. Using "a candidate exists" alone would record a
        rejection on every tick where `data_guard` blocked after `scout` had already
        run, and using "the guard chain did not block" alone would lose a rejection on a
        tick where a guard blocked as well.
        """
        blocked_by = state.get(TRADING_BLOCKED_BY_KEY)
        if not blocked_by:
            return 0
        guards = {
            str(entry.get("engine"))
            for entry in state.get(GUARD_BLOCKERS_KEY) or ()
            if isinstance(entry, Mapping)
        }
        if str(blocked_by) in guards:
            return 0

        scout_key, pair_field = CANDIDATE_PAIR_PATH
        candidate = state.get(scout_key) or {}
        pair = candidate.get(pair_field) if isinstance(candidate, Mapping) else None
        if not pair:
            # The opportunity chain stopped without a candidate — engine 5 `feature`
            # returning PASS on a non-bar tick is the common case. Nothing was rejected.
            return 0

        blocker = state.get(str(blocked_by))
        blocker = blocker if isinstance(blocker, Mapping) else {}
        economics: dict[str, Any] = {}
        for column, field in ECONOMICS_FIELDS:
            value = blocker.get(field)
            economics[column] = None if value is None else str(value)

        reason_code = blocker.get(REASON_CODE_FIELD)
        if not reason_code:
            raise MissingInputError(
                f"engine {blocked_by!r} refused {pair!r} without publishing a "
                f"{REASON_CODE_FIELD!r}. The console maps that code to operator prose and "
                "a rejection without one renders as silence, so recording the row without "
                "it would be worse than failing the tick."
            )

        store.write_rejection(
            RejectionRow(
                cycle_id=cycle_id,
                run_id=context.run_id,
                ts=ts,
                pair=str(pair),
                rejected_by=str(blocked_by),
                reason_code=str(reason_code),
                reason=str(state.get(BLOCK_REASON_KEY) or ""),
                candidate_score=self._score(blocker),
                updated_at=ts,
                **economics,
            )
        )
        return 1

    def _score(self, blocker: Mapping[str, Any]) -> float | None:
        """The candidate's score, which is a statistic and therefore a float."""
        value = blocker.get("candidate_score")
        return None if value is None else float(value)

    # ------------------------------------------------------- equity_snapshots

    def _write_equity(
        self,
        store: Any,
        context: EngineContext,
        exchange: Mapping[str, Any] | None,
        manager: Mapping[str, Any] | None,
        *,
        closed: Sequence[TradeRow],
        cycle_id: int,
        ts: int,
    ) -> tuple[Decimal | None, Decimal | None, str | None]:
        """One row per tick, unless there is no equity information to write.

        Returns ``(equity, peak_equity, skipped_reason)``. **A tick with nothing to say
        about equity writes no row rather than a zero.** A zero equity row is a 100%
        drawdown against any earlier peak, and engine 17 would freeze the account over a
        failed balance fetch — which invariant 2 already handles by blocking the trade,
        not by inventing an account value.

        ``peak_equity`` is the running maximum **read from the store**. It cannot be
        recomputed from `state`, which is fresh every tick and has never seen the
        series; an engine that took the maximum of this tick alone reports a peak equal
        to the current equity, a drawdown of permanently zero, and a circuit breaker
        that never fires on a drawdown again.
        """
        currency = str(context.config.get(KEY_REPORTING_CURRENCY))
        if exchange is None:
            return None, None, f"no state[{EXCHANGE_KEY!r}] this tick"
        balances = exchange.get(BALANCES_FIELD)
        if balances is None:
            return None, None, "the balance fetch produced nothing this tick"
        if not isinstance(balances, Mapping):
            raise MissingInputError(
                f"state[{EXCHANGE_KEY!r}][{BALANCES_FIELD!r}] is a "
                f"{type(balances).__name__}, not a mapping of currency to amount"
            )
        if currency not in balances:
            return None, None, f"no {currency} balance in this tick's fetch"

        cash = decimal_field(balances, currency, where=f"{EXCHANGE_KEY}.{BALANCES_FIELD}")
        positions_value = decimal_field(
            manager or {}, POSITIONS_VALUE_FIELD, where=POSITION_MANAGER_KEY
        )
        unrealised = decimal_field(
            manager or {}, "unrealised_pnl", where=POSITION_MANAGER_KEY
        )
        equity = cash + positions_value

        previous = store.latest_equity_snapshot()
        realised_cum = previous.realised_pnl_cum if previous is not None else Decimal(0)
        realised_cum = realised_cum + sum(
            (trade.realised_pnl for trade in closed), start=Decimal(0)
        )
        peak = equity if previous is None else max(previous.peak_equity, equity)

        store.write_equity_snapshot(
            EquitySnapshotRow(
                cycle_id=cycle_id,
                run_id=context.run_id,
                ts=ts,
                currency=currency,
                equity=equity,
                peak_equity=peak,
                cash=cash,
                positions_value=positions_value,
                unrealised_pnl=unrealised,
                realised_pnl_cum=realised_cum,
                open_position_count=int(store.count_open_positions()),
                updated_at=ts,
            )
        )
        return equity, peak, None


__all__ = ["STATE_KEY", "MemoryEngine"]
