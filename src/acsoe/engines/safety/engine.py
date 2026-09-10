"""Engine 17 `safety` — the circuit breaker on the account.

**Guard chain, stage 1 — not the opportunity chain.** It asks an account-level question:
how far is equity down, how many losses in a row, how many errors this hour, how long has
the feed been bad. None of that has anything to do with the candidate under consideration,
and all of it must be answered on ticks where there is no candidate at all. Placed at the
end of the opportunity chain it would run only when every other gate had already passed —
on roughly fourteen ticks in fifteen that chain stops at `feature` because no bar closed,
and on the rest any earlier gate stops it sooner. An account bleeding while every
candidate is rejected by the cost gate would never trip the breaker. The guard chain is
the only placement that makes this a circuit breaker rather than a formality.

**All six inputs come from the store.** `state` is fresh every tick and this engine runs
*before* the manage chain, so `state["position_manager"]` and `state["exit"]` do not
exist when it runs. Their producer is engine 19 `memory`, which is Phase 4; the Phase 0
seed exists to resolve that forward dependency, and nothing here may touch a live
engine 19.

**It cannot freeze the system itself.** Only the orchestrator writes `state["system"]`.
When this engine must act it writes a `freeze` or `close_all` row to the `commands`
table with `source = CommandSource.SAFETY` — the same channel the console uses — and the
orchestrator consumes it at the top of the next tick. Its `BLOCK` suppresses the
opportunity chain for the current tick; the command row is what makes the decision
persist.

**It emits a row only when that row would change the state.** It runs every tick, so
without this a sustained drawdown would append a freeze row every sixty seconds forever,
and a sustained outage would re-trigger a liquidation already under way. It still
evaluates and still publishes its assessment on those ticks — the assessment is the record
of the evaluation, the command row is the record of the decision, and research needs both.

**Three of the four conditions freeze; only the data outage liquidates.** Ruled by the
operator on 2026-09-10 and written into invariant 14 by spec 37. The table is
:data:`CONDITION_ACTION` and the reasoning belongs to invariant 14, not here. What belongs
here is the consequence for this module: `freeze` idempotency is now the common path
rather than the rare one, and a tick that trips several conditions emits exactly one row —
the strongest action, so drawdown plus outage is a `close_all` and never a `freeze`.

## The outage arithmetic, which is off by one in the obvious reading

Engine 4 `data_guard` runs *before* this engine in the guard chain, so the current tick's
block is already visible in `state["trading_blocked_by"]`. Engine 19 `memory` runs
*later*, in the manage chain, so the store holds records only through tick T-1. Therefore:

```
effective = stored_consecutive_blocks_through_T_minus_1 + (1 if this tick blocked by data_guard)
```

Getting it wrong fires the breaker a minute early or a minute late. The store method is
named `stored_consecutive_data_block_ticks_excluding_current_tick` precisely so the
correction cannot be forgotten at the call site, and it is passed this tick's
`(run_id, cycle_id)` because "consecutive through T-1" is not answerable without knowing
T — a clean tick writes no `block_records` row at all, so an outage that ended two ticks
ago is otherwise indistinguishable from one still running.

The count is **consecutive most-recent `cycle_id`s carrying any `data_guard` row, ordered
by `ts`, never by `cycle_id`**. `cycle_id` restarts at 1 with each process, and surviving
a restart is the whole reason the counter lives in SQLite rather than in `state`. A tick
where two guards blocked contributes one, not two.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

from acsoe.clients.store.contracts import (
    BlockStatus,
    CommandRow,
    CommandSource,
    OrderIntent,
    to_micros,
)
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.safety.contracts import (
    BOUNDARY_SOURCE,
    CONDITION_ACTION,
    DATA_GUARD_ENGINE,
    LOSS_STREAK_SCAN_LIMIT,
    REASON_INPUTS_UNAVAILABLE,
    SafetyAction,
    SafetyAssessment,
    SafetyCondition,
    SafetyReadings,
    SafetyThresholds,
    command_for,
    escalating_conditions,
    strongest,
)

MICROSECONDS_PER_SECOND = 1_000_000


class MissingInputError(Exception):
    """An input the breaker needs is absent or unusable."""


class SafetyEngine(BaseEngine):
    """Gate 17. Guard chain, runtime stage 1. Runs every tick, in every mode."""

    name = "safety"
    number = 17
    is_gate = True

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        try:
            thresholds = self._read_thresholds(context)
            readings = self._read_store(context, state, thresholds)
        except MissingInputError as missing:
            return self._blocked_on_missing_input(str(missing), started)

        tripped = self._tripped(readings, thresholds)
        action = strongest(tuple(CONDITION_ACTION[condition] for condition in tripped))
        emitted, suppressed = self._emit(context, state, action, readings, tripped)

        assessment = SafetyAssessment(
            readings=readings,
            tripped=tripped,
            action=action,
            command_emitted=emitted,
            suppressed_because=suppressed,
        )
        duration_ms = (time.perf_counter() - started) * 1000.0

        if not tripped:
            return EngineResult(
                engine=self.name,
                status=EngineStatus.OK,
                blocks_trading=False,
                data=assessment.to_state_data(),
                duration_ms=duration_ms,
            )

        # Blocks whenever a condition is tripped, whether or not a row was emitted. The
        # emission is about persisting the decision; the block is about this tick, and a
        # condition that still holds must still stop the opportunity chain even on the
        # ticks where the command table already says so.
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=self._operator_reason(tripped, readings, thresholds),
            data=assessment.to_state_data(),
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------ inputs

    def _store(self, context: EngineContext) -> Any:
        store = getattr(context.clients, "store", None)
        if store is None:
            raise MissingInputError("clients.store is not available")
        return store

    def _read_thresholds(self, context: EngineContext) -> SafetyThresholds:
        raw: dict[str, Any] = {}
        for field in (
            "max_drawdown_pct",
            "max_consecutive_losses",
            "error_rate_window_s",
            "max_errors_in_window",
            "max_consecutive_data_blocks",
        ):
            value = context.config.get(f"safety.{field}")
            if value is None:
                raise MissingInputError(f"config safety.{field} is null (OPERATOR REQUIRED)")
            raw[field] = repr(value) if isinstance(value, float) else value
        try:
            return SafetyThresholds.model_validate(raw)
        except (InvalidOperation, ValueError) as exc:
            raise MissingInputError(f"unusable safety threshold: {exc}") from exc

    def _read_store(
        self, context: EngineContext, state: State, thresholds: SafetyThresholds
    ) -> SafetyReadings:
        """All six inputs, in one place, every one of them a store read.

        A `state` lookup appears exactly once in this method — `trading_blocked_by`, to
        learn whether *this* tick is blocked by `data_guard`. That is not one of the six:
        the store cannot know it, because engine 19 has not run yet this tick, and the
        arithmetic in the module docstring depends on it.
        """
        store = self._store(context)
        now_micros = to_micros(context.now)

        drawdown, equity, peak = self._drawdown(store)
        losses, saturated = self._loss_streak(store)

        window_start = now_micros - thresholds.error_rate_window_s * MICROSECONDS_PER_SECOND
        errors = int(
            store.count_block_records_in_window(
                start_ts=window_start, end_ts=now_micros, status=BlockStatus.ERROR
            )
        )

        cycle_id = state.get("cycle_id")
        if not isinstance(cycle_id, int):
            raise MissingInputError("state['cycle_id'] is absent; cannot anchor the outage walk")
        stored_blocks = int(
            store.stored_consecutive_data_block_ticks_excluding_current_tick(
                current_tick=(context.run_id, cycle_id)
            )
        )
        blocked_now = state.get("trading_blocked_by") == DATA_GUARD_ENGINE

        return SafetyReadings(
            drawdown_pct=drawdown,
            equity=equity,
            peak_equity=peak,
            consecutive_losses=losses,
            loss_streak_saturated=saturated,
            errors_in_window=errors,
            error_window_start_ts=window_start,
            open_positions=int(store.count_open_positions()),
            resting_entry_orders=int(store.count_resting_orders(intent=OrderIntent.ENTRY)),
            stored_data_blocks=stored_blocks,
            current_tick_blocked_by_data_guard=blocked_now,
            consecutive_data_blocks=stored_blocks + (1 if blocked_now else 0),
        )

    def _drawdown(self, store: Any) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        """`(peak_equity - equity) / peak_equity` from the latest snapshot.

        `None` when there is no snapshot at all, which is a different fact from a
        drawdown of zero and must not be read as "no drawdown". A non-positive peak is
        also `None` rather than a division: an account with no peak has no drawdown to
        measure, and `DivisionByZero` inside a circuit breaker is the breaker failing.
        """
        snapshot = store.latest_equity_snapshot()
        if snapshot is None:
            return None, None, None
        equity: Decimal = snapshot.equity
        peak: Decimal = snapshot.peak_equity
        if peak <= 0:
            return None, equity, peak
        return (peak - equity) / peak, equity, peak

    def _loss_streak(self, store: Any) -> tuple[int, bool]:
        """The trailing run of losing closed trades, ordered by `closed_at`.

        A loss is `realised_pnl < 0`. `outcome` is read into the assessment for research
        but does not decide this: a `timeout` can close slightly up, and a breaker that
        counted it as a loss would be counting outcomes rather than money.

        Returns the streak and whether it hit the scan bound. Saturation is reported
        rather than hidden, because "500 losses in a row" and "at least 500" are the same
        decision but not the same fact.
        """
        trades = store.recent_closed_trades(LOSS_STREAK_SCAN_LIMIT)
        streak = 0
        for trade in trades:
            if trade.realised_pnl < 0:
                streak += 1
                continue
            break
        return streak, streak == LOSS_STREAK_SCAN_LIMIT

    # ------------------------------------------------------------------ policy

    def _tripped(
        self, readings: SafetyReadings, thresholds: SafetyThresholds
    ) -> tuple[SafetyCondition, ...]:
        """Which conditions are breached. Boundaries are per-condition; see
        :data:`BOUNDARY_SOURCE` for the sentence fixing each one."""
        tripped: list[SafetyCondition] = []

        if readings.drawdown_pct is not None and readings.drawdown_pct >= thresholds.max_drawdown_pct:
            tripped.append(SafetyCondition.DRAWDOWN)
        if readings.consecutive_losses >= thresholds.max_consecutive_losses:
            tripped.append(SafetyCondition.LOSS_STREAK)
        if readings.errors_in_window >= thresholds.max_errors_in_window:
            tripped.append(SafetyCondition.ERROR_RATE)
        # Strictly greater, and the only one of the four that is. Invariant 14: "more
        # than `max_consecutive_data_blocks` consecutive ticks"; spec 36: "on the tick
        # after the limit and not one before".
        if readings.consecutive_data_blocks > thresholds.max_consecutive_data_blocks:
            tripped.append(SafetyCondition.DATA_OUTAGE)

        return tuple(tripped)

    def _emit(
        self,
        context: EngineContext,
        state: State,
        action: SafetyAction,
        readings: SafetyReadings,
        tripped: tuple[SafetyCondition, ...],
    ) -> tuple[str | None, str | None]:
        """Write the command row, but only when it would change the system's state.

        **At most one row per tick, and it is the strongest action.** `strongest` has
        already collapsed several tripped conditions into one action before this method
        sees it, so a tick that is both in drawdown and mid-outage emits `close_all` and
        not `freeze`, and never both. Spec 42 step 6.

        Three suppressions, each from `engine-contracts.md` or invariant 14:

        - **`freeze` only while the mode is `running`.** Freezing a frozen or idle system
          changes nothing and appends a row every sixty seconds forever. After the
          2026-09-10 ruling three of the four conditions emit `freeze`, so this is now the
          common path rather than the rare one.
        - **`close_all` only when there is exposure** — an open position or a resting
          entry order. Invariant 14 gates escalation on exactly that, and liquidating an
          account with nothing open is a command with no effect.
        - **`close_all` only when `close_intent` is not already set.** Re-emitting
          re-triggers a liquidation already under way.

        The suppression sentences name the condition that wanted to act, not just the
        action. An operator reading "the breaker did nothing" needs to know *which*
        condition was suppressed, and after the ruling the answer for a `close_all` is
        always the data outage and never the drawdown they might assume.

        **A suppressed `close_all` falls through** to the strongest action that is not
        suppressed rather than emitting nothing — invariant 14, ruled 2026-09-10. See
        :meth:`_fall_through`.

        Returns `(command emitted, why it was suppressed)`. Exactly one is set, except on a
        fall-through, where both are: that tick suppressed one action and emitted another.
        """
        command = command_for(action)
        if command is None:
            return None, None

        system = state.get("system")
        mode = system.get("mode") if isinstance(system, dict) else None
        close_intent = bool(system.get("close_intent")) if isinstance(system, dict) else False

        if action is SafetyAction.FREEZE and mode != "running":
            return None, (
                f"{self._named(tripped)} would freeze, but the mode is already {mode!r}; "
                "a freeze would change nothing"
            )
        if action is SafetyAction.CLOSE_ALL:
            escalating = self._named(escalating_conditions(tripped))
            blocked_by: str | None = None
            if not readings.has_exposure:
                blocked_by = (
                    f"{escalating} would escalate, but there is no open position and no "
                    "resting entry order to close"
                )
            elif close_intent:
                blocked_by = (
                    f"{escalating} would escalate, but close_intent is already set; a "
                    "liquidation is under way"
                )
            if blocked_by is not None:
                return self._fall_through(context, state, blocked_by, readings, tripped)

        now_micros = to_micros(context.now)
        store = self._store(context)
        store.append_command(
            CommandRow(
                command=command.value,
                source=CommandSource.SAFETY,
                reason=self._command_reason(tripped),
                created_at=now_micros,
                created_by_run_id=context.run_id,
                updated_at=now_micros,
            )
        )
        return command.value, None

    # ------------------------------------------------------------------ prose

    def _fall_through(
        self,
        context: EngineContext,
        state: State,
        blocked_by: str,
        readings: SafetyReadings,
        tripped: tuple[SafetyCondition, ...],
    ) -> tuple[str | None, str | None]:
        """The escalation was suppressed. Emit the strongest action that is not.

        **Ruled by the operator on 2026-09-10 and written into invariant 14:** "a suppressed
        escalation never swallows a freeze that was independently due". The case it answers:
        a drawdown is breached, a data outage is running, and the account has nothing open
        and nothing resting. `close_all` wins, is suppressed for want of anything to close,
        and before the ruling *nothing at all* was emitted — including the `freeze` the
        drawdown would have emitted on its own. More bad conditions producing less action is
        the wrong direction for a circuit breaker.

        It does not repeal spec 42 step 6. Still one command per tick, still no `freeze`
        alongside a `close_all` that actually emitted; only the fall-through is new.

        **The re-entry is bounded at one further call.** The lesser action is chosen from
        the conditions that did *not* ask for `CLOSE_ALL`, so the branch that got here
        cannot be reached again — and re-entering `_emit` rather than duplicating the freeze
        suppression is deliberate: a second copy of "only while the mode is `running`" is a
        second place for it to drift.

        Returns both values when the fall-through emits, which is the one case where both
        are set: the tick genuinely suppressed one action and emitted another, and an
        operator reading "it froze" needs to know the outage wanted to liquidate and could
        not.
        """
        lesser = strongest(
            tuple(
                CONDITION_ACTION[condition]
                for condition in tripped
                if CONDITION_ACTION[condition] is not SafetyAction.CLOSE_ALL
            )
        )
        if lesser is SafetyAction.NONE:
            return None, blocked_by
        emitted, also_suppressed = self._emit(context, state, lesser, readings, tripped)
        if emitted is None:
            return None, f"{blocked_by}; and {also_suppressed}"
        return emitted, blocked_by

    def _named(self, conditions: tuple[SafetyCondition, ...]) -> str:
        """Conditions as an operator-readable list, or a placeholder if somehow empty."""
        if not conditions:
            return "no condition"
        return " and ".join(condition.value for condition in conditions)

    def _command_reason(self, tripped: tuple[SafetyCondition, ...]) -> str:
        """Why the system stopped itself, on the audit row.

        Every tripped condition, not just the strongest: the row is the permanent record
        of the decision, and "drawdown *and* a loss streak" is a materially different
        account state from either alone.
        """
        return "safety: " + ", ".join(condition.value for condition in tripped)

    def _operator_reason(
        self,
        tripped: tuple[SafetyCondition, ...],
        readings: SafetyReadings,
        thresholds: SafetyThresholds,
    ) -> str:
        """Prose carrying the actual numbers, per `ui-context.md`."""
        parts: list[str] = []
        for condition in tripped:
            if condition is SafetyCondition.DRAWDOWN and readings.drawdown_pct is not None:
                parts.append(
                    f"drawdown {_pct(readings.drawdown_pct)} at or past the "
                    f"{_pct(thresholds.max_drawdown_pct)} limit"
                )
            elif condition is SafetyCondition.LOSS_STREAK:
                parts.append(
                    f"{readings.consecutive_losses} consecutive losses, limit "
                    f"{thresholds.max_consecutive_losses}"
                )
            elif condition is SafetyCondition.ERROR_RATE:
                parts.append(
                    f"{readings.errors_in_window} engine errors in the trailing "
                    f"{thresholds.error_rate_window_s}s, limit {thresholds.max_errors_in_window}"
                )
            elif condition is SafetyCondition.DATA_OUTAGE:
                parts.append(
                    f"{readings.consecutive_data_blocks} consecutive ticks blocked by "
                    f"data_guard, limit {thresholds.max_consecutive_data_blocks}"
                )
        return "Safety breaker: " + "; ".join(parts)

    def _blocked_on_missing_input(self, detail: str, started: float) -> EngineResult:
        """Fail closed. Invariant 3, and this is the gate that is not gated behind the
        other gates — a breaker that cannot read its inputs must stop the system, not
        wave it through."""
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=f"Safety breaker could not read its inputs: missing {detail}",
            data={"reason_code": REASON_INPUTS_UNAVAILABLE, "tripped": []},
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


def _pct(value: Decimal) -> str:
    """A ratio as a plain percentage, two places. Not signed: a drawdown is a magnitude
    and a `+` on it would suggest a direction it does not have."""
    return format((value * 100).quantize(Decimal("0.01")), "f") + "%"


__all__ = ["BOUNDARY_SOURCE", "MissingInputError", "SafetyEngine"]
