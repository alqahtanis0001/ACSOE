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

import json
import time
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, NamedTuple

from acsoe.clients.store.contracts import (
    ApprovalRow,
    BlockRecordRow,
    BlockStatus,
    CashSource,
    EquitySnapshotRow,
    OrderRow,
    PositionRow,
    PositionStatus,
    RejectionRow,
    ScoutTallyRow,
    TradeRow,
    to_micros,
)
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.memory.contracts import (
    APPROVAL_TRADE_FIELDS,
    BALANCES_FIELD,
    BLOCK_REASON_KEY,
    BLOCK_STATUS_KEY,
    CANDIDATE_PAIR_PATH,
    CLOSED_BAR_TS_FIELD,
    CLOSED_TRADES_FIELD,
    COST_KEY,
    CYCLE_ID_KEY,
    DETAILS_VERSION,
    ECONOMICS_FIELDS,
    EXCHANGE_KEY,
    EXECUTION_KEY,
    EXIT_KEY,
    GUARD_BLOCKERS_KEY,
    HOLD_REASON_FIELD,
    MARKET_SENSOR_KEY,
    MODEL_RUN_ID_FIELD,
    MODEL_RUN_KEYS,
    NET_PROCEEDS_FIELD,
    ORDERS_FIELD,
    PAIR_FIELD,
    PLACED_FIELD,
    POSITION_ID_FIELD,
    POSITION_MANAGER_KEY,
    POSITION_STATUS_FIELD,
    POSITION_VALUE_FIELD,
    POSITIONS_FIELD,
    POSITIONS_VALUE_FIELD,
    PREDICTION_KEY,
    REASON_CODE_FIELD,
    REASON_ENGINE_ERRORED,
    SCOUT_KEY,
    SHAP_FIELD,
    STATE_KEY,
    TALLY_JSON_FIELDS,
    TALLY_SCALAR_FIELDS,
    TRADING_BLOCKED_BY_KEY,
    UNREALISED_PNL_FIELD,
    USERREF_FIELD,
    VERDICT_FIELDS,
    WRITTEN_TABLES,
    MemoryState,
    MissingInputError,
    decimal_field,
)

KEY_REPORTING_CURRENCY = "trading.base_reporting_currency"


class ClosedTrade(NamedTuple):
    """One round trip engine 22 closed on this tick, and what it paid into the account.

    The row is the stored one. ``net_proceeds`` is the payload fact beside it, which the
    `trades` table has no column for, and it is ``None`` when engine 22 published none —
    a different fact from zero, and handled as one in :meth:`MemoryEngine._after_exit`.
    """

    row: TradeRow
    net_proceeds: Decimal | None


class WrittenShap(NamedTuple):
    """This tick's SHAP write: the ref and the pair it explains, or why nothing was written."""

    ref: str | None = None
    pair: str | None = None
    skipped: str | None = None


class Account(NamedTuple):
    """The three figures an `equity_snapshots` row is built from, for one tick."""

    cash: Decimal
    positions_value: Decimal
    unrealised_pnl: Decimal


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

        executing = self._payload(state, EXECUTION_KEY)
        manager = self._payload(state, POSITION_MANAGER_KEY)
        exiting = self._payload(state, EXIT_KEY)
        exchange = self._payload(state, EXCHANGE_KEY)

        written["approvals"] = self._write_approval(
            store, context, state, executing, cycle_id=cycle_id, ts=ts
        )

        # Positions and trades land before the equity snapshot, because the snapshot's
        # `open_position_count` and `realised_pnl_cum` are read back out of the store
        # once this tick's rows are in it. Reordering these is silent.
        #
        # Within each table the publisher order is chain order and it decides which row
        # survives the upsert — 21 then 22 for positions, 18 then 21 then 22 for orders.
        # `WRITTEN_TABLES` in `contracts.py` carries the reasoning; the short version is
        # that a position closed this tick must not be stored as open with a mark on it,
        # and an entry placed and immediately cancelled must be stored as cancelled.
        written["positions"] = self._write_positions(
            store, context, manager, cycle_id=cycle_id, ts=ts
        ) + self._write_positions(store, context, exiting, cycle_id=cycle_id, ts=ts)
        written["orders"] = (
            self._write_orders(store, context, executing, cycle_id=cycle_id, ts=ts)
            + self._write_orders(store, context, manager, cycle_id=cycle_id, ts=ts)
            + self._write_orders(store, context, exiting, cycle_id=cycle_id, ts=ts)
        )
        closed = self._write_trades(store, context, exiting, cycle_id=cycle_id, ts=ts)
        written["trades"] = len(closed)
        written["scout_tallies"] = self._write_scout_tally(
            store, context, state, cycle_id=cycle_id, ts=ts
        )
        shap = self._write_shap(store, context, state, cycle_id=cycle_id, ts=ts)
        written["rejections"] = self._write_rejection(
            store, context, state, cycle_id=cycle_id, ts=ts, shap=shap
        )

        equity, peak, skipped = self._write_equity(
            store,
            context,
            exchange,
            manager,
            exiting,
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
                    (EXECUTION_KEY, executing),
                    (POSITION_MANAGER_KEY, manager),
                    (EXIT_KEY, exiting),
                )
                if payload is not None
            ),
            equity=equity,
            peak_equity=peak,
            equity_skipped_reason=skipped,
            hold_reason=self._hold_reason(manager),
            shap_ref=shap.ref,
            shap_skipped_reason=shap.skipped,
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
        """One row per entry in ``state["guard_blockers"]``, `is_primary` on the first,
        plus one for an opportunity-chain engine that returned ``ERROR``.

        **No row at all on a tick where nothing blocked**, and none for an
        opportunity-chain ``BLOCK``, which is a rejection rather than an evaluation. A row
        on every tick makes every count that reads this table meaningless — the outage run
        becomes the uptime.

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

        errored = self._errored_opportunity_engine(state)
        if errored is None:
            return len(blockers)
        # Invariant 12, operator ruling 2026-09-16: the tick this table most needs. The
        # reason is engine 19's code and never one read from the engine, which decided
        # nothing — rule 7 has emptied its payload, and asking it for a code is what
        # used to lose the whole tick. `is_primary` is true because the opportunity chain
        # runs only when no guard blocked, so no guard row above can also be primary.
        store.write_block_record(
            BlockRecordRow(
                cycle_id=cycle_id,
                run_id=context.run_id,
                ts=ts,
                blocked_by=errored,
                block_reason=REASON_ENGINE_ERRORED,
                is_primary=True,
                status=BlockStatus.ERROR,
                updated_at=ts,
            )
        )
        return len(blockers) + 1

    def _errored_opportunity_engine(self, state: State) -> str | None:
        """The opportunity-chain engine that returned ``ERROR`` this tick, or ``None``.

        **Read from ``state["block_status"]``, never inferred from an empty payload.** An
        engine that raised and a gate that blocked without publishing its `reason_code`
        both leave ``{}`` behind, and they are different facts: the first is recorded here
        and is not a rejection, the second is a gate breaking its contract and still
        raises in `_write_rejection`.

        A guard that errored is not this case. It is already in ``guard_blockers`` with
        its status and gets its row there; a second row for it would be a second primary.
        """
        blocked_by = state.get(TRADING_BLOCKED_BY_KEY)
        if not blocked_by or state.get(BLOCK_STATUS_KEY) != BlockStatus.ERROR:
            return None
        guards = {
            str(entry.get("engine"))
            for entry in state.get(GUARD_BLOCKERS_KEY) or ()
            if isinstance(entry, Mapping)
        }
        if str(blocked_by) in guards:
            return None
        return str(blocked_by)

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
        hold = self._hold_reason(manager)
        for row in rows:
            stamped = self._stamped(row, context, cycle_id=cycle_id, ts=ts)
            # The hold is a property of the **tick**, published once by engine 21, and it
            # lands on every position that tick marked. Written unconditionally rather
            # than only when there is one, because `write_position` upserts every column:
            # setting it to `None` on a tick that did not hold is what *clears* the
            # previous tick's reason. Skipping the assignment instead would carry an
            # hour-old hold forward forever, rendering a paused manage chain over one
            # running normally. Lead ruling, 2026-09-16, condition 2.
            stamped[HOLD_REASON_FIELD] = hold
            # `value` is spec 113's payload fact, not a `positions` column, and `_Row` is
            # `extra="forbid"`: left on, it raises here and contract rule 7 turns that
            # into an `ERROR` that loses the whole tick. Taken off this copy only — the
            # caller's list still carries it, because `_write_equity` sums it. Nothing
            # else is stripped, so the next unknown key on a stored row still raises.
            stamped.pop(POSITION_VALUE_FIELD, None)
            store.write_position(PositionRow.model_validate(stamped))
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
    ) -> list[ClosedTrade]:
        """One row per closed round trip. Returns them, for the equity snapshot.

        **`net_proceeds` comes off before the row is validated and is carried beside it.**
        It is spec 113's payload fact and the `trades` table has no column for it, so
        leaving it on `TradeRow.model_validate` raises and loses the tick. It is read
        through `decimal_field`, which refuses a float: the exit tick's cash is built from
        it, and a float that reached here has already lost precision.
        """
        closed: list[ClosedTrade] = []
        where = f"{EXIT_KEY}.{CLOSED_TRADES_FIELD}"
        for row in self._rows(exiting, CLOSED_TRADES_FIELD):
            published = row.get(NET_PROCEEDS_FIELD)
            proceeds = (
                None if published is None else decimal_field(row, NET_PROCEEDS_FIELD, where=where)
            )
            stamped = self._stamped(row, context, cycle_id=cycle_id, ts=ts)
            stamped.pop(NET_PROCEEDS_FIELD, None)
            stamped.update(self._approved_as(store, stamped.get("entry_userref")))
            trade = TradeRow.model_validate(stamped)
            store.write_trade(trade)
            closed.append(ClosedTrade(row=trade, net_proceeds=proceeds))
        return closed

    # ---------------------------------------------------------- scout_tallies

    def _write_scout_tally(
        self, store: Any, context: EngineContext, state: State, *, cycle_id: int, ts: int
    ) -> int:
        """Engine 7's universe step on this tick, stored verbatim. Spec 146.

        **On every tick engine 7 ran, candidate or not**: the no-candidate ticks are the
        ones the funnel could not count before. Nothing is recomputed; a field engine 7 did
        not publish is `NULL`, never zero. An engine 7 that raised writes no tally, since its
        block record already is the record of that tick.

        No status is stored (the lead's ruling): engine 7 publishes none, and its
        `reason_code` and candidate carry the outcome. The store holds `scanned == entered +
        sum(excluded)`, so a payload breaking it is refused there, loudly.
        """
        scout = self._payload(state, SCOUT_KEY)
        if scout is None or self._errored_opportunity_engine(state) == SCOUT_KEY:
            return 0
        fields: dict[str, Any] = {
            column: scout.get(key) for column, key in TALLY_SCALAR_FIELDS
        }
        if fields["candidate"] == "":
            fields["candidate"] = None
        for column in TALLY_JSON_FIELDS:
            value = scout.get(column)
            fields[column] = (
                None if value is None
                else json.dumps(value, sort_keys=True, separators=(",", ":"))
            )
        sensor = self._payload(state, MARKET_SENSOR_KEY) or {}
        bar = sensor.get(CLOSED_BAR_TS_FIELD)
        store.write_scout_tally(
            ScoutTallyRow(
                run_id=context.run_id,
                cycle_id=cycle_id,
                ts=ts,
                # Engine 3's published value, verbatim (the lead's ruling): the opening
                # second of the bar that just closed. The column name is b-store's.
                closed_bar_ts=None if bar is None else int(bar),
                updated_at=ts,
                **fields,
            )
        )
        return 1

    # ------------------------------------------------------------------- shap

    def _write_shap(
        self, store: Any, context: EngineContext, state: State, *, cycle_id: int, ts: int
    ) -> WrittenShap:
        """Engine 8's per-feature contributions, written as Parquet through the store. Spec 140.

        On every tick engine 8 scored a candidate, approved or refused. **Nothing is written,
        and no ref is set**, when engine 8 did not run, raised (the status decides, whatever
        its payload says), refused (it publishes no `shap` then), or published an empty
        explanation: an empty file would look like an explanation of nothing.

        A refusal **by the store** (no Parquet root configured, an unusable run id, a
        non-finite contribution, a file already there) is recorded as the skip reason and
        never fails the tick: engine 19 is the single writer, and a lost tick is worse than a
        missing explanation. Any other exception still raises (contract rule 7).
        """
        from acsoe.clients.store import StoreError

        prediction = self._payload(state, PREDICTION_KEY)
        if prediction is None or self._errored_opportunity_engine(state) == PREDICTION_KEY:
            return WrittenShap()
        contributions = prediction.get(SHAP_FIELD)
        if not isinstance(contributions, Mapping) or not contributions:
            return WrittenShap()
        pair = str(prediction.get(PAIR_FIELD) or "")
        run_id = prediction.get(MODEL_RUN_ID_FIELD)
        try:
            ref = store.write_shap(
                run_id=context.run_id,
                cycle_id=cycle_id,
                ts=ts,
                pair=pair,
                model_run_id=None if run_id is None else str(run_id),
                contributions=contributions,
            )
        except StoreError as refused:
            return WrittenShap(skipped=str(refused))
        return WrittenShap(ref=str(ref), pair=pair)

    # -------------------------------------------------------------- approvals

    def _write_approval(
        self,
        store: Any,
        context: EngineContext,
        state: State,
        executing: Mapping[str, Any] | None,
        *,
        cycle_id: int,
        ts: int,
    ) -> int:
        """Why this tick's entry was approved, written on the tick it was placed. Spec 133.

        **Only when engine 18 placed an entry on this tick** (`placed: true`). An order
        found already recorded is not this tick's approval, and the economics in `state`
        now are not the ones that approved it.

        The four economics are engine 10's, the figures it compared against the hurdle, and
        the three run ids are the models engines 8, 13 and 15 scored with. **An absent
        figure is written absent, never zero** (spec 133): a fill whose placing tick
        published none is still recorded, with nothing claimed about why.

        The store inserts and never upserts: a second approval for one `userref` raises
        `sqlite3.IntegrityError`, which is not caught here, for the same reason a second
        primary block record is not — it is the database refusing a second answer to a
        question that has one.
        """
        if executing is None or executing.get(PLACED_FIELD) is not True:
            return 0
        if self._errored_opportunity_engine(state) == EXECUTION_KEY:
            # An engine that raised decided nothing, whatever its payload says (invariant
            # 12's reading, which `_write_rejection` applies to reason codes too).
            return 0
        userref = executing.get(USERREF_FIELD)
        pair = executing.get(PAIR_FIELD)
        if not isinstance(userref, int) or isinstance(userref, bool) or not pair:
            raise MissingInputError(
                f"engine 18 placed an entry and published userref {userref!r} and pair "
                f"{pair!r}; the approval is keyed by the userref and cannot be written "
                "without it"
            )
        cost = self._payload(state, COST_KEY) or {}
        economics: dict[str, Any] = {}
        for column, field in ECONOMICS_FIELDS:
            value = cost.get(field)
            if isinstance(value, float):
                # Contract rule 8: money crosses `state` as an exact decimal string. A float
                # here has already lost the digits the hurdle was decided on, and `str()`
                # would launder it into a string the column then accepts.
                raise MissingInputError(
                    f"state[{COST_KEY!r}][{field!r}] is the float {value!r}; money crosses "
                    "state as an exact decimal string"
                )
            # `str` and not `decimal_field`: the column is `Money`, which parses the string
            # exactly, and `decimal_field` would turn absent into zero.
            economics[column] = None if value is None else str(value)
        for column, key in MODEL_RUN_KEYS:
            payload = self._payload(state, key) or {}
            value = payload.get(MODEL_RUN_ID_FIELD)
            economics[column] = None if value is None else str(value)
        store.write_approval(
            ApprovalRow(
                userref=userref,
                run_id=context.run_id,
                cycle_id=cycle_id,
                ts=ts,
                pair=str(pair),
                details=self._verdicts(state, refused_by=None),
                updated_at=ts,
                **economics,
            )
        )
        return 1

    def _approved_as(self, store: Any, entry_userref: Any) -> dict[str, Any]:
        """The seven approval fields for a trade, from its entry's approval, or all absent.

        No `entry_userref`, or no approval recorded for it (an entry placed before
        migration 0006, or a placing tick that published nothing), gives every field
        `None`. The trade is written either way: spec 133 never refuses a fill for it.
        """
        approval = None if entry_userref is None else store.approval(int(entry_userref))
        return {
            field: None if approval is None else getattr(approval, field)
            for field in APPROVAL_TRADE_FIELDS
        }

    # ------------------------------------------------------- verdict snapshot

    def _verdicts(self, state: State, *, refused_by: str | None) -> str:
        """Every judging engine's verdict this tick, as canonical JSON. Spec 145.

        Engines in chain order, **stopping at the refuser** on a refusal (marked
        `refused_by`); on an approval every one present. A field an engine did not publish
        is absent, never null-filled: absent and null are different facts. Values are
        copied exactly as published, so money stays an exact decimal string and a
        statistic stays a float. An engine that raised records `{"status": "ERROR"}` and
        nothing else, whatever its payload; a payload that is not a mapping records
        `{"status": "UNREADABLE"}`. **Never raises**: engine 19 is the single writer, and a
        lost tick is worse than a partial snapshot.
        """
        errored = self._errored_opportunity_engine(state)
        engines: dict[str, Any] = {}
        for engine, fields in VERDICT_FIELDS:
            if engine not in state:
                if engine == refused_by:
                    break
                continue
            payload = state[engine]
            if engine == errored:
                engines[engine] = {"status": "ERROR"}
            elif not isinstance(payload, Mapping):
                engines[engine] = {"status": "UNREADABLE"}
            else:
                engines[engine] = {name: payload[name] for name in fields if name in payload}
            if engine == refused_by:
                break
        snapshot: dict[str, Any] = {"details_version": DETAILS_VERSION, "engines": engines}
        if refused_by is not None:
            snapshot["refused_by"] = refused_by
        try:
            return json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return json.dumps(
                {"details_version": DETAILS_VERSION, "unserialisable": True, "refused_by": refused_by},
                sort_keys=True,
                separators=(",", ":"),
            )

    # ------------------------------------------------------------- rejections

    def _write_rejection(
        self,
        store: Any,
        context: EngineContext,
        state: State,
        *,
        cycle_id: int,
        ts: int,
        shap: WrittenShap,
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
        if self._errored_opportunity_engine(state) is not None:
            # An engine that raised refused nothing — it failed to decide — so there is no
            # rejection to write and no `reason_code` to demand. Its block record is
            # written in `_write_block_records`. Invariant 12, operator ruling 2026-09-16.
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
                # Only the explanation of this candidate: engine 8 scores the pair engine 7
                # chose, and a ref for any other pair would explain a different decision.
                shap_ref=shap.ref if shap.pair == str(pair) else None,
                details=self._verdicts(state, refused_by=str(blocked_by)),
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
        exiting: Mapping[str, Any] | None,
        *,
        closed: Sequence[ClosedTrade],
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

        **On a tick where engine 22 closed positions the row describes the account after
        those sales** (operator ruling 2026-09-17), and it is built by *filtering and
        summing* facts the other engines published — see :meth:`_after_exit`. Engine 1's
        balance is from the start of the tick, engine 21's totals are from before the
        sale, and the store's position count is from after it: three moments that never
        coexisted, which is how the exit tick's row came to read 0 open positions beside a
        positions value of 3281.10. `cash_source` records which of the two meanings the
        row carries, because the difference is the proceeds and no reader can re-derive
        it from the row alone.
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

        # **An unmarked position is not a position worth nothing.** `decimal_field`
        # returns `Decimal(0)` for an absent field, which is right for a flat account and
        # catastrophic for an invested one: `equity = cash + 0` drops the position's whole
        # value out of that tick of the series, engine 17 computes
        # `(peak_equity - equity) / peak_equity` against a peak read from the store, and on
        # a fully invested account one unmarked tick is a drawdown approaching 100% against
        # a `safety.max_drawdown_pct` of 0.10. The account freezes over a missing quote.
        #
        # Spec 92 has engine 21 publish `positions_value` **absent**, never zero, precisely
        # so this is detectable — but only if the two cases are told apart, and
        # `decimal_field`'s default makes them identical. The count comes from the store
        # rather than from `state`, and it is read here rather than at the write below
        # because this tick's positions have already landed: it is the count that decides
        # whether a cash-only equity is the truth or a hole. Lead ruling, 2026-09-16.
        open_positions = int(store.count_open_positions())
        marked = manager or {}
        sold = self._closed_position_ids(exiting)

        if sold or closed:
            account, skipped = self._after_exit(
                marked, sold, closed, cash=cash, open_positions=open_positions
            )
            if account is None:
                return None, None, skipped
            cash_source = CashSource.AFTER_EXIT
        else:
            for field in (POSITIONS_VALUE_FIELD, UNREALISED_PNL_FIELD):
                if open_positions and marked.get(field) is None:
                    return None, None, (
                        f"{open_positions} open position(s) and no {field} this tick, so the "
                        "only equity available is cash and a cash-only equity on an invested "
                        "account is a drawdown that did not happen"
                    )
            account = Account(
                cash=cash,
                positions_value=decimal_field(
                    marked, POSITIONS_VALUE_FIELD, where=POSITION_MANAGER_KEY
                ),
                unrealised_pnl=decimal_field(
                    marked, UNREALISED_PNL_FIELD, where=POSITION_MANAGER_KEY
                ),
            )
            cash_source = CashSource.CYCLE_START

        cash, positions_value, unrealised = account
        equity = cash + positions_value

        # The whole previous row, not `store.peak_equity()`, because this tick needs the
        # carried-forward `realised_pnl_cum` as well as the peak. The two readers cannot
        # disagree - `peak_equity()` is a thin read over exactly this row.
        #
        # **Read B's docstring on `StoreClient.peak_equity` before touching the peak
        # below.** It carries the reasoning that has no home on this side and is the
        # trap anyone revisiting this line will fall into: money is stored as an exact
        # decimal string, so `SELECT MAX(peak_equity)` compares lexicographically and
        # decides '9.50' > '10000.00'. That returns a plausible number, a too-small
        # peak, a too-small drawdown, and a breaker that sits quiet through exactly the
        # loss it exists to stop. Nothing raises.
        previous = store.latest_equity_snapshot()
        realised_cum = previous.realised_pnl_cum if previous is not None else Decimal(0)
        realised_cum = realised_cum + sum(
            (trade.row.realised_pnl for trade in closed), start=Decimal(0)
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
                cash_source=cash_source,
                updated_at=ts,
            )
        )
        return equity, peak, None

    def _closed_position_ids(self, exiting: Mapping[str, Any] | None) -> frozenset[str]:
        """Every `position_id` engine 22 closed on this tick.

        Read from the rows engine 22 published rather than from the store, because the
        store cannot say *when* a position was closed to the tick — and a position closed
        three ticks ago must not be filtered out of a valuation it no longer appears in.
        A closed row with no `position_id` raises rather than being skipped: skipping it
        would leave engine 21's mark of a sold position in the sum, which is the defect
        this whole branch exists to remove.
        """
        sold: set[str] = set()
        for index, row in enumerate(self._rows(exiting, POSITIONS_FIELD)):
            if str(row.get(POSITION_STATUS_FIELD)) != PositionStatus.CLOSED.value:
                continue
            position_id = row.get(POSITION_ID_FIELD)
            if not position_id:
                raise MissingInputError(
                    f"state[{EXIT_KEY!r}][{POSITIONS_FIELD!r}][{index}] is closed and names "
                    f"no {POSITION_ID_FIELD!r}, so the position it sold cannot be dropped "
                    "from engine 21's valuation and the equity row would count it twice"
                )
            sold.add(str(position_id))
        return frozenset(sold)

    def _after_exit(
        self,
        marked: Mapping[str, Any],
        sold: frozenset[str],
        closed: Sequence[ClosedTrade],
        *,
        cash: Decimal,
        open_positions: int,
    ) -> tuple[Account | None, str | None]:
        """The account after this tick's sales, by filtering and summing and nothing else.

        The operator's ruling of 2026-09-17, in full: positions value and unrealised PnL
        are engine 21's rows **minus every `position_id` engine 22 closed**, summed; cash
        is engine 1's start-of-tick balance **plus** the `net_proceeds` of every closed
        trade. Engine 19 performs no arithmetic on account figures of its own — it does
        not subtract a mark, it does not price a sale, and it reads no engine's valuation
        method. An earlier design in which engine 22 subtracted engine 21's marks was
        withdrawn for exactly that coupling.

        Three things make it skip the row instead, and each is the fail-closed reading of
        a hole that would otherwise look like a working row:

        1. **A remaining position with no `value` or no `unrealised_pnl`.** The operator's
           first concern. Summing the rows that have one gives the account minus that
           position — a drawdown that did not happen, from a row that looks complete. An
           absent total does this already on an ordinary tick; filtering must not be a way
           around it. A *closed* position with no mark is dropped and blocks nothing.
        2. **Engine 21's remaining rows not covering what the account still holds.** The
           count comes from the store after this tick's rows landed, so it is the number
           of positions that survived the sale. Fewer rows than that is the same hole as
           (1) arriving through a position engine 21 never published at all.
        3. **A closed trade with no `net_proceeds`.** Treating it as zero puts the sale's
           cash nowhere: the row would read as an account that sold a position and was
           paid nothing for it, which is a loss the account did not take.
        """
        remaining = [
            row
            for row in self._rows(marked, POSITIONS_FIELD)
            if str(row.get(POSITION_ID_FIELD)) not in sold
        ]
        if len(remaining) != open_positions:
            return None, (
                f"engine 22 closed {len(sold)} position(s) and engine 21 published "
                f"{len(remaining)} row(s) for the {open_positions} the account still "
                "holds, so the rows do not cover the account and summing them would "
                "value less than it holds"
            )

        positions_value = Decimal(0)
        unrealised = Decimal(0)
        for row in remaining:
            for field in (POSITION_VALUE_FIELD, UNREALISED_PNL_FIELD):
                if row.get(field) is None:
                    return None, (
                        f"engine 22 closed {len(sold)} position(s) and the remaining "
                        f"position {str(row.get(POSITION_ID_FIELD))!r} has no {field} this "
                        "tick, so the only positions value available is a partial sum and "
                        "a partial sum on an invested account is a drawdown that did not "
                        "happen"
                    )
            positions_value += decimal_field(row, POSITION_VALUE_FIELD, where=POSITION_MANAGER_KEY)
            unrealised += decimal_field(row, UNREALISED_PNL_FIELD, where=POSITION_MANAGER_KEY)

        proceeds = Decimal(0)
        for trade in closed:
            if trade.net_proceeds is None:
                return None, (
                    f"the closed trade {trade.row.trade_id!r} carries no "
                    f"{NET_PROCEEDS_FIELD}, so this tick's cash cannot include what the "
                    "sale paid in and the row would report a position sold for nothing"
                )
            proceeds += trade.net_proceeds

        return Account(
            cash=cash + proceeds, positions_value=positions_value, unrealised_pnl=unrealised
        ), None


__all__ = ["STATE_KEY", "MemoryEngine"]
