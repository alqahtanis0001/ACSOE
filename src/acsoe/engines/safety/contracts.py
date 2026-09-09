"""What engine 17 `safety` reads, decides, and publishes.

Two tables in this module are the whole of the breaker's policy, deliberately separated
from the code that reads the store and the code that writes the command row:

- :data:`CONDITION_ACTION` — which command each tripped condition emits.
- :data:`BOUNDARY_SOURCE` — whether each threshold trips *at* its limit or *above* it,
  with the sentence in the documents that fixes it.

They are tables rather than branches because they are the part a person rules on and the
rest is mechanism. A ruling is an edit to one dictionary, not a hunt through `process`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import CommandName, Money

__all__ = [
    "BOUNDARY_SOURCE",
    "CONDITION_ACTION",
    "DATA_GUARD_ENGINE",
    "LOSS_STREAK_SCAN_LIMIT",
    "REASON_INPUTS_UNAVAILABLE",
    "SafetyAction",
    "SafetyAssessment",
    "SafetyCondition",
    "SafetyReadings",
    "SafetyThresholds",
]

#: Engine 4's registry name, as it appears in `block_records.blocked_by`.
DATA_GUARD_ENGINE: Final = "data_guard"

#: How far back the loss-streak walk reads. Bounded so a pathological `trades` table
#: cannot turn one guard-chain tick into a full scan, and generous enough that the
#: reported streak is the real one rather than one clipped at the threshold — the console
#: renders this number, and "5, and possibly more" is not a useful thing to show an
#: operator. A streak longer than this saturates, which is recorded in the assessment.
LOSS_STREAK_SCAN_LIMIT: Final = 500

#: Fail-closed code for the guard-chain side. Not yet in C's `REASON_PROSE`; the reason
#: written alongside it is always prose, and `operator_reason` prefers prose.
REASON_INPUTS_UNAVAILABLE: Final = "safety_inputs_unavailable"


class SafetyCondition(StrEnum):
    """The four account-level conditions that can trip the breaker.

    Open positions and resting entry orders are **not** conditions. They are the
    *escalation precondition* of invariant 14 — "`safety` escalates when there are open
    positions or resting entry orders" — so they gate whether a `close_all` is emitted
    rather than causing one. A resting post-only buy counts: left on the book through a
    blackout it can open a position into a market the system has already declared
    untrustworthy.
    """

    DRAWDOWN = "drawdown"
    LOSS_STREAK = "loss_streak"
    ERROR_RATE = "error_rate"
    DATA_OUTAGE = "data_outage"


class SafetyAction(StrEnum):
    """What a tripped condition asks the system to do.

    `safety` cannot write `state["system"]` — only the orchestrator may — so an action is
    a row on the `commands` table with `source = CommandSource.SAFETY`, consumed by the
    command reader at the top of the next tick. Every such row is an audit record of
    exactly when and why the system stopped itself.
    """

    NONE = "none"
    FREEZE = "freeze"
    CLOSE_ALL = "close_all"


#: Rank, so that when several conditions trip on one tick the strongest wins. A tick that
#: is both in drawdown and mid-outage must not emit two rows, and must not emit the
#: weaker of the two.
_ACTION_RANK: Final[Mapping[SafetyAction, int]] = {
    SafetyAction.NONE: 0,
    SafetyAction.FREEZE: 1,
    SafetyAction.CLOSE_ALL: 2,
}

#: **The policy table. PROVISIONAL — awaiting a lead ruling, escalated 2026-09-09.**
#:
#: `trading-invariants.md` §14 and `feature-specs/36` cannot both be satisfied by the
#: Phase 0 seed, and the disagreement is exactly about this mapping:
#:
#: - §14 says `safety` escalates — sets `close_intent`, i.e. writes `close_all` — on
#:   "its configured drawdown and loss-streak limits are breached" or "a sustained data
#:   outage", when there are open positions or resting entry orders.
#: - Spec 36's Check When Done says "it **freezes** on the seeded drawdown".
#:
#: The seed carries drawdown 0.2000 against a 0.10 limit, a streak of 8 against 5, **and**
#: 2 open positions and 2 resting entry orders — every precondition §14 names. So under
#: §14 the seeded drawdown emits `close_all`; under spec 36 it emits `freeze`.
#:
#: **Implemented reading, pending the ruling:** spec 36's "freezes" is the loose one.
#: `close_all` also sets the mode to `frozen`, so a `close_all` on the seeded drawdown
#: *is* freezing on the drawdown, and spec 36's real claim is its second half — that a
#: command appears on a tick where the opportunity chain never ran. This reading makes
#: §14 literal, and §14 is a trading invariant, which outranks a spec's wording.
#:
#: The error rate maps to `FREEZE` because §14 does not list it among the escalation
#: conditions at all: it is an engine-health problem, not account exposure, and
#: liquidating an account because the system is throwing exceptions would be the breaker
#: causing the loss it exists to prevent.
CONDITION_ACTION: Final[Mapping[SafetyCondition, SafetyAction]] = {
    SafetyCondition.DRAWDOWN: SafetyAction.CLOSE_ALL,
    SafetyCondition.LOSS_STREAK: SafetyAction.CLOSE_ALL,
    SafetyCondition.ERROR_RATE: SafetyAction.FREEZE,
    SafetyCondition.DATA_OUTAGE: SafetyAction.CLOSE_ALL,
}

#: Whether each threshold trips **at** its configured value or only **above** it, and the
#: sentence that fixes it. Written out because an off-by-one in a circuit breaker fires it
#: a tick early or a tick late, and neither is acceptable — and because "is 20 errors a
#: breach, or is 21?" is a question a reader will have and should not have to re-derive.
BOUNDARY_SOURCE: Final[Mapping[SafetyCondition, str]] = {
    SafetyCondition.DRAWDOWN: (
        "at the limit. `config/default.yaml`: `max_drawdown_pct: 0.10` is "
        "invariant 14's 'configured drawdown limits', and a drawdown that has reached "
        "its limit has reached it."
    ),
    SafetyCondition.LOSS_STREAK: (
        "at the limit. `config/default.yaml`: 'at a ~61% break-even win rate a 5-loss "
        "run is roughly a 1-in-100 event' — the fifth loss is the event, not the sixth."
    ),
    SafetyCondition.ERROR_RATE: (
        "at the limit. `config/default.yaml`: '20 engine errors inside the 3600s window "
        "trips the breaker' — the operator's own words say 20 trips it."
    ),
    SafetyCondition.DATA_OUTAGE: (
        "above the limit. Invariant 14: 'once `data_guard` has blocked **more than** "
        "`safety.max_consecutive_data_blocks` consecutive ticks', and spec 36: 'on the "
        "tick after the limit and not one before'. This one is strictly greater."
    ),
}


def strongest(actions: tuple[SafetyAction, ...]) -> SafetyAction:
    """The most severe action among those asked for. Empty means :data:`SafetyAction.NONE`."""
    return max(actions, key=lambda action: _ACTION_RANK[action], default=SafetyAction.NONE)


def command_for(action: SafetyAction) -> CommandName | None:
    """The `commands` row an action writes, or `None` for :data:`SafetyAction.NONE`."""
    if action is SafetyAction.FREEZE:
        return CommandName.FREEZE
    if action is SafetyAction.CLOSE_ALL:
        return CommandName.CLOSE_ALL
    return None


class SafetyThresholds(BaseModel):
    """The five `safety.*` keys, parsed. All five exist and are set in the committed
    config; a null one is the OPERATOR REQUIRED state and blocks rather than defaulting."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_drawdown_pct: Money
    max_consecutive_losses: int
    error_rate_window_s: int
    max_errors_in_window: int
    max_consecutive_data_blocks: int


class SafetyReadings(BaseModel):
    """The six inputs, every one of them read from the store.

    Not from `state`. `safety` runs in the guard chain *before* the manage chain, and
    `state` is fresh every tick, so `state["position_manager"]` and `state["exit"]` do
    not exist when this engine runs. That is structural, not a convention.

    `drawdown_pct` is `None` when there is no `equity_snapshots` row at all — a different
    fact from a drawdown of zero, and one the breaker must not read as "no drawdown".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    drawdown_pct: Money | None = None
    equity: Money | None = None
    peak_equity: Money | None = None
    consecutive_losses: int
    loss_streak_saturated: bool = False
    errors_in_window: int
    error_window_start_ts: int
    open_positions: int
    resting_entry_orders: int
    consecutive_data_blocks: int
    stored_data_blocks: int
    current_tick_blocked_by_data_guard: bool

    @property
    def has_exposure(self) -> bool:
        """Invariant 14's escalation precondition: an open position **or** a resting
        entry order. Entry orders count — an outage with no position but a live post-only
        buy is still exposure waiting to happen."""
        return self.open_positions > 0 or self.resting_entry_orders > 0


class SafetyAssessment(BaseModel):
    """What this engine publishes into `state["safety"]` on every tick.

    Published whether or not anything tripped, and whether or not a command was emitted.
    `engine-contracts.md`: "when the condition persists and the state already reflects
    it, `safety` still evaluates and still records its assessment in its own `data` for
    the console and the log, but emits nothing." The assessment is the record of the
    *evaluation*; the command row is the record of the *decision*, and research needs
    both.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    readings: SafetyReadings
    tripped: tuple[SafetyCondition, ...] = ()
    action: SafetyAction = SafetyAction.NONE
    command_emitted: str | None = None
    suppressed_because: str | None = None

    def to_state_data(self) -> dict[str, Any]:
        """JSON-serialisable, money as exact decimal strings."""
        readings = self.readings
        return {
            "drawdown_pct": _money_or_none(readings.drawdown_pct),
            "equity": _money_or_none(readings.equity),
            "peak_equity": _money_or_none(readings.peak_equity),
            "consecutive_losses": readings.consecutive_losses,
            "loss_streak_saturated": readings.loss_streak_saturated,
            "errors_in_window": readings.errors_in_window,
            "open_positions": readings.open_positions,
            "resting_entry_orders": readings.resting_entry_orders,
            "consecutive_data_blocks": readings.consecutive_data_blocks,
            "stored_data_blocks": readings.stored_data_blocks,
            "current_tick_blocked_by_data_guard": readings.current_tick_blocked_by_data_guard,
            "tripped": [condition.value for condition in self.tripped],
            "action": self.action.value,
            "command_emitted": self.command_emitted,
            "suppressed_because": self.suppressed_because,
        }


def _money_or_none(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")
