"""What engine 16 `decision` reads from `state` and what it writes back.

Two things live here: the **order intent**, which is the one typed record engine 18
reads instead of reaching into five engines' payloads, and the constants naming every
key engine 16 examines.

**The intent is composed, not decided.** Every number in it was chosen by the engine
whose decision it was — the pair by engine 7, the quantity by engine 11, the edge and
the hurdle by engine 10, the model by engine 8. Engine 16 copies them and re-derives
none of them. The one thing it decides is whether they are talking about the same
candidate on the same bar; see :mod:`acsoe.engines.decision.engine`.

**Money crosses `state` as an exact decimal string**, never a float — `core/contracts.py`
refuses a `Decimal` and *accepts* a `float`, so the reflexive cast on hitting that
refusal is the dangerous mistake. `p_wrong` is the exception and is a float on purpose:
it is a probability, not money, and the project splits those two the same way everywhere.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.kraken.contracts import Money, money_text

__all__ = [
    "BAR_FIELDS",
    "CHECKED_SOURCES",
    "INTENT_FIELD",
    "OPTIONAL_SOURCES",
    "PAIR_FIELD",
    "REASON_INPUTS_UNAVAILABLE",
    "REASON_INPUT_MISSING",
    "REASON_NO_APPROVED_QUANTITY",
    "REASON_PAIR_DISAGREEMENT",
    "REASON_STALE_BAR",
    "REQUIRED_SOURCES",
    "STATE_KEY",
    "DecisionState",
    "OrderIntent",
]

#: `state["decision"]`.
STATE_KEY: Final = "decision"

#: The intent, nested under the verdict. **Absent in its entirety on a block** — not an
#: empty mapping and not a null. The same shape engine 11 uses for `qty` and engine 7 for
#: `pair`, and for the same reason: a key called `intent` sitting in the payload of a
#: refused tick is a key some future consumer reads without checking the verdict first.
INTENT_FIELD: Final = "intent"

# --------------------------------------------------------------------------- #
# What engine 16 reads
# --------------------------------------------------------------------------- #

#: Engine 3, the guard chain. The bar every other payload is measured against.
MARKET_SENSOR_KEY: Final = "market_sensor"
CLOSED_BAR_TS_FIELD: Final = "closed_bar_ts"

#: Engine 7. The candidate, and therefore the pair every other payload must name.
SCOUT_KEY: Final = "scout"

#: Engine 11. `approved` and `qty`; engine 11 omits `qty` on a rejection.
RISK_KEY: Final = "risk"
RISK_APPROVED_FIELD: Final = "approved"
RISK_QTY_FIELD: Final = "qty"

#: The orchestrator's own key, set once per tick in `core/orchestrator.py`.
CYCLE_ID_KEY: Final = "cycle_id"

#: Every payload engine 16 **must** have. Each one either approved this candidate or
#: supplies a clause: engine 7 names the pair, engine 8 names the bar and the model,
#: engines 10, 11 and 15 are gates whose approvals the intent records.
#:
#: The opportunity chain stops at the first block or `PASS` (`core/orchestrator.py`), so
#: engine 16 running at all means each of these ran and approved. An absent key is
#: therefore not a judgement any of them made — it is the chain contradicting itself,
#: which is what `input_missing` says.
REQUIRED_SOURCES: Final[tuple[str, ...]] = (
    SCOUT_KEY,
    "prediction",
    "cost",
    RISK_KEY,
    "skeptic",
)

#: Payloads engine 16 copies provenance out of and **never blocks on**.
#:
#: Both are non-gates, and spec 97 says engine 14 publishes nothing engine 16 "reads to
#: decide" while spec 90 puts its `active_model_run_id` in the intent — the two hold
#: together only if the field is a record rather than a criterion. The same reading is
#: applied to engine 9: engine 10 is already the gate that refuses when the slippage is
#: missing, and refusing again here would count one absence twice.
#:
#: Being optional also costs nothing. Engine 9 failing means engine 10 blocks and the
#: chain never reaches here; engine 14 failing still leaves its key present, because the
#: orchestrator writes `result.data` on an `ERROR` too. So there is no reachable tick on
#: which requiring them would refuse something requiring the other five does not.
OPTIONAL_SOURCES: Final[tuple[str, ...]] = ("order_book", "adaptive_router")

#: Every payload the coherence walk examines, in registry order.
CHECKED_SOURCES: Final[tuple[str, ...]] = (
    SCOUT_KEY,
    "prediction",
    "order_book",
    "cost",
    RISK_KEY,
    "adaptive_router",
    "skeptic",
)

#: The key a payload names its pair with.
PAIR_FIELD: Final = "pair"

#: The keys a payload may name its decision bar with. Engine 8 publishes `bar_ts`, copied
#: from engine 5, which copied it from engine 3's `closed_bar_ts` — so the two spellings
#: are one value and comparing them is a real staleness check rather than two clocks.
BAR_FIELDS: Final[tuple[str, ...]] = ("bar_ts", CLOSED_BAR_TS_FIELD)

# --------------------------------------------------------------------------- #
# Reason codes
# --------------------------------------------------------------------------- #

#: Two payloads name different pairs. The sentence names both engines and both pairs,
#: because "they disagree" without saying which is a rejection row nobody can act on.
REASON_PAIR_DISAGREEMENT: Final = "pair_disagreement"

#: A payload carries a decision bar that is not this tick's. A `state` key that survived
#: a previous bar looks exactly like a fresh one to every engine that reads it.
REASON_STALE_BAR: Final = "stale_bar"

#: A payload the chain says ran is absent, or a field a clause needs is not there. A
#: clause that cannot be evaluated blocks — invariant 3, the absence of a "no" is never
#: a "yes".
REASON_INPUT_MISSING: Final = "input_missing"

#: Engine 11 approved and published no `qty`, or did not approve at all. Engine 11 omits
#: the field on a rejection, so an approval with no quantity is the shape that says an
#: approval and a refusal disagree inside one payload.
REASON_NO_APPROVED_QUANTITY: Final = "no_approved_quantity"

#: The check itself could not run: `state` is malformed, or a value that must be a
#: number or a timestamp is neither. The house pattern every sibling gate carries
#: (`cost_inputs_unavailable`, `risk_inputs_unavailable`, `scout_inputs_unavailable`).
REASON_INPUTS_UNAVAILABLE: Final = "decision_inputs_unavailable"


class OrderIntent(BaseModel):
    """The one record engine 18 reads, instead of five engines' keys.

    Four fields identify the trade and the rest are **provenance**: the numbers the
    approving engines published, carried so that engine 19 can record why this order
    existed without re-reading a `state` that no longer exists by then.

    Provenance is **omitted when absent**, never null, and its absence never blocks —
    see `OPTIONAL_SOURCES`. The four identifying fields are required, and a tick that
    cannot supply all four produces no intent at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    qty: Money
    closed_bar_ts: int
    cycle_id: int

    net_edge_pct: Money | None = None
    hurdle_pct: Money | None = None
    expected_move_pct: Money | None = None
    estimated_slippage_pct: Money | None = None
    p_wrong: float | None = None
    model_run_id: str | None = None
    active_model_run_id: str | None = None

    def to_state(self) -> dict[str, Any]:
        """Money as exact decimal strings; absent provenance omitted, never null."""
        payload: dict[str, Any] = {
            "pair": self.pair,
            "qty": money_text(self.qty),
            "closed_bar_ts": self.closed_bar_ts,
            "cycle_id": self.cycle_id,
        }
        for field in (
            "net_edge_pct",
            "hurdle_pct",
            "expected_move_pct",
            "estimated_slippage_pct",
        ):
            value = getattr(self, field)
            if value is not None:
                payload[field] = money_text(value)
        for field in ("p_wrong", "model_run_id", "active_model_run_id"):
            value = getattr(self, field)
            if value is not None:
                payload[field] = value
        return payload


class DecisionState(BaseModel):
    """What engine 16 publishes into `state["decision"]`.

    `coherent` is the one thing this engine asserts. `checked` is the provenance of the
    check itself — which payloads the walk actually examined — so a tick where a source
    was simply not present can be told apart from one where it was examined and agreed.
    Without it, "the pair matched everywhere" and "there was nowhere to match against"
    publish identically.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    coherent: bool
    checked: tuple[str, ...] = ()
    reason_code: str | None = None
    intent: OrderIntent | None = None

    def to_state(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "coherent": self.coherent,
            "checked": list(self.checked),
            "reason_code": self.reason_code,
        }
        if self.intent is not None:
            payload[INTENT_FIELD] = self.intent.to_state()
        return payload
