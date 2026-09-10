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
    "ESCALATING_CONDITION",
    "LOSS_STREAK_SCAN_LIMIT",
    "REASON_INPUTS_UNAVAILABLE",
    "SafetyAction",
    "SafetyAssessment",
    "SafetyCondition",
    "SafetyReadings",
    "SafetyThresholds",
    "command_for",
    "escalating_conditions",
    "strongest",
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

#: **The policy table. Ruled by the operator on 2026-09-10 and written into invariant 14
#: by spec 37; applied here by spec 42.** No longer provisional, and no longer this
#: engine's reading of a contradiction.
#:
#: `CLOSE_ALL` is reserved for invariant 14's data-outage escalation and for the
#: operator's own Close all button. Nothing else in this table may reach it, and adding a
#: condition that does is an escalation rather than an edit.
#:
#: **The distinction is what the condition is a statement about**, and it is invariant
#: 14's to state rather than this module's to restate — the short form, so a reader here
#: knows there is a reason and where to find it: a drawdown or a losing streak is a
#: statement about *past* trades, so liquidating on one realises a paper loss on the
#: system's own authority at the moment it has least evidence it is reading the market
#: correctly. A sustained outage is a statement about *present* knowledge, and unknown
#: exposure is worse than a bad fill. Freeze stops new positions while the manage chain
#: keeps watching the open ones, and the operator decides whether to liquidate.
#:
#: The error rate freezes for a related but separate reason: it is an engine-health
#: problem rather than account exposure, and liquidating an account because the system is
#: throwing exceptions would be the breaker causing the loss it exists to prevent.
#:
#: Two rows changed on 2026-09-10 — `DRAWDOWN` and `LOSS_STREAK`, both from `CLOSE_ALL`.
#: `ERROR_RATE` and `DATA_OUTAGE` were already as ruled.
CONDITION_ACTION: Final[Mapping[SafetyCondition, SafetyAction]] = {
    SafetyCondition.DRAWDOWN: SafetyAction.FREEZE,
    SafetyCondition.LOSS_STREAK: SafetyAction.FREEZE,
    SafetyCondition.ERROR_RATE: SafetyAction.FREEZE,
    SafetyCondition.DATA_OUTAGE: SafetyAction.CLOSE_ALL,
}

#: The one condition permitted to escalate, named rather than inferred from the table
#: above. Read by :func:`escalating_conditions` and asserted by the tests, so "nothing but
#: the outage reaches `close_all`" is a property the code states rather than one a reader
#: has to check by eye. Invariant 14, and spec 42's scope limit in as many words: "do not
#: make `close_all` reachable from any condition other than the data outage".
ESCALATING_CONDITION: Final = SafetyCondition.DATA_OUTAGE

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
    """The most severe action among those asked for. Empty means :data:`SafetyAction.NONE`.

    **One tick emits at most one command, and it is the strongest one.** Spec 42 step 6:
    when several conditions trip together the more severe action wins and the two are not
    both emitted. A drawdown and a data outage on the same tick emit `close_all`, not
    `freeze` and not both.

    Ranked rather than ordered, deliberately. `_ACTION_RANK` is a decision someone took;
    the order `SafetyCondition` happens to be declared in is not, and a table that relied
    on it would silently change behaviour the next time a condition was added in the
    middle. `max` with an explicit key cannot be reordered into being wrong.
    """
    return max(actions, key=lambda action: _ACTION_RANK[action], default=SafetyAction.NONE)


def escalating_conditions(tripped: tuple[SafetyCondition, ...]) -> tuple[SafetyCondition, ...]:
    """Those of `tripped` that asked for a `close_all`.

    Used for the suppression sentence, which an operator reads when the breaker did
    nothing. "No open position and no resting entry order" is only half an answer — the
    useful half names *which* condition wanted to liquidate, because after the ruling that
    is always the data outage and never the drawdown a reader might assume.
    """
    return tuple(
        condition
        for condition in tripped
        if CONDITION_ACTION[condition] is SafetyAction.CLOSE_ALL
    )


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

    **`action` is what the tripped conditions asked for, not necessarily what was
    emitted.** They differ on a fall-through: invariant 14, ruled 2026-09-10, says a
    suppressed escalation emits the strongest action that is not suppressed instead of
    emitting nothing — so a tick can record `action: close_all` alongside
    `command_emitted: freeze`, with `suppressed_because` naming the escalation that could
    not happen. That is the one case where all three are set, and it is deliberate:
    collapsing them would lose the fact that a liquidation was wanted and refused.
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
