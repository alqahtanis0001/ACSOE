"""What engine 10 `cost` reads out of `state` and what it writes back into it.

**Money crosses `state` as an exact decimal string, never as a `Decimal`.** That is not
a preference. `EngineResult.data` runs `_assert_json_serialisable`, whose scalar set is
`None | str | int | float | bool`, and the orchestrator assigns `result.data` straight
into `state[engine.name]` — so everything published by another engine has already been
through that validator and a `Decimal` could not have survived it. A `float` *would*
have survived it, and would have lost precision on the way, which is why the models here
type their money fields as :data:`Money` — a `Decimal` carrying a `BeforeValidator` that
**raises on a float rather than coercing it**. A string parses exactly; a float is
refused at this boundary rather than discovered three decimals into a hurdle comparison.

`Money` is imported from `clients/store/contracts.py` rather than redeclared. There is
one money rule in this project and it should have one definition; a second copy here
would be a second place for it to drift.

## The state paths below are B's proposal, not yet ratified

`engine-contracts.md` fixes exactly four cross-chain keys and none of them is an input to
this engine. Spec 34 fixes one path in prose — the fee tier "reaches this engine as
`state["exchange"]`'s fee tier, published by A's engine 1" — and says nothing about where
the expected move, the spread or the slippage estimate arrive. Rather than scatter
guessed key names through the engine, every path this module reads is a `Final` constant
here, so re-pointing one when the lead fixes the table is a one-line edit and a reviewer
can see the whole surface at once. The open question is recorded in
`context/progress/b-store.md`.

None of this guesses at *trading behaviour*: the arithmetic is invariant 5, quoted in
:mod:`acsoe.engines.cost.engine`, and it is fixed. Only the wiring is provisional.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import Money

__all__ = [
    "CANDIDATE_PAIR_PATH",
    "EXCHANGE_BALANCES_KEY",
    "EXCHANGE_FALLBACKS_KEY",
    "EXCHANGE_FEES_KEY",
    "EXCHANGE_KEY",
    "EXCHANGE_PAIRS_KEY",
    "MINUS_SIGN",
    "ORDER_BOOK_KEY",
    "PERCENT_PLACES",
    "PREDICTION_KEY",
    "REASON_INPUTS_UNAVAILABLE",
    "REASON_NET_EDGE_BELOW_HURDLE",
    "REASON_SPREAD_WIDER_THAN_MOVE",
    "SCOUT_KEY",
    "CostAssessment",
    "CostInputs",
    "format_signed_pct",
]

# --------------------------------------------------------------------------- #
# State paths — provisional, see the module docstring
# --------------------------------------------------------------------------- #

#: Engine 1 `exchange` (A). Spec 34 fixes this one: the fee tier arrives here.
EXCHANGE_KEY: Final = "exchange"

#: Account-level fee tier, under :data:`EXCHANGE_KEY`. One tier per account, so it is
#: not keyed by pair.
EXCHANGE_FEES_KEY: Final = "fees"

#: Per-pair exchange facts, under :data:`EXCHANGE_KEY`, keyed by pair name: the measured
#: spread here, and `ordermin`/`costmin` for engine 11.
EXCHANGE_PAIRS_KEY: Final = "pairs"

#: Currency-to-amount map, under :data:`EXCHANGE_KEY`. Read by engine 11, not by this one.
EXCHANGE_BALANCES_KEY: Final = "balances"

#: Which paper-mode fallbacks fired on this tick, under :data:`EXCHANGE_KEY`. Invariant 2
#: requires every decision affected by a fallback to record which one, and a gate outcome
#: is such a decision, so it is carried through into this engine's `data` verbatim.
EXCHANGE_FALLBACKS_KEY: Final = "fallbacks_used"

#: Engine 8 `prediction` (C). The expected move for the candidate, as a signed ratio.
PREDICTION_KEY: Final = "prediction"

#: Engine 9 `order_book` (C). The slippage estimate, which is a property of book depth
#: and therefore not something the exchange states outright.
ORDER_BOOK_KEY: Final = "order_book"

#: Engine 7 `scout` (B, Phase 3 proper). Which pair the tick is considering.
SCOUT_KEY: Final = "scout"

#: Where the candidate's pair name is read from, as a `(state key, field)` pair.
CANDIDATE_PAIR_PATH: Final = (SCOUT_KEY, "pair")

# --------------------------------------------------------------------------- #
# Reason codes
# --------------------------------------------------------------------------- #

#: Machine-readable codes for `rejections.reason_code`.
#:
#: The first two are **not invented here**. They are already in
#: `console/format.py`'s `REASON_PROSE` table, which is C's mapping from a stored code
#: to the sentence an operator reads. A code this engine emits that is absent from that
#: table renders as "No reason was recorded." on the console, so the two must agree —
#: `tests/engines/test_cost.py` asserts they do, because nothing else would notice.
REASON_NET_EDGE_BELOW_HURDLE: Final = "net_edge_below_hurdle"
REASON_SPREAD_WIDER_THAN_MOVE: Final = "spread_wider_than_move"

#: Fail-closed: an input this gate needs was absent or unparseable. Invariant 3 — "a gate
#: that cannot reach its data blocks", and "absence of a 'no' is never a 'yes'".
#:
#: Deliberately **not** in C's `REASON_PROSE` yet; C has been asked to add it. Until then
#: the console still renders this correctly, because `operator_reason` prefers the row's
#: own prose whenever it is a sentence rather than a bare code, and the reason this
#: engine writes for it always is one.
REASON_INPUTS_UNAVAILABLE: Final = "cost_inputs_unavailable"

# --------------------------------------------------------------------------- #
# Percentage rendering, for the operator-facing reason
# --------------------------------------------------------------------------- #

#: U+2212 MINUS SIGN, written as a named escape so this file stays ASCII and so a reader
#: cannot mistake it for the hyphen it looks like. Rule 6 of `ui-context.md`'s number
#: rules: a hyphen is narrower than a digit in almost every face, so a column of
#: hyphen-negative numbers does not align even with tabular figures switched on.
MINUS_SIGN: Final = "\N{MINUS SIGN}"

#: Two places on a percentage, matching `console/format.py`. The system's edges are
#: fractions of a percent, so one place would round a real edge away.
PERCENT_PLACES: Final = 2


def format_signed_pct(value: Decimal, *, places: int = PERCENT_PLACES) -> str:
    """A ratio rendered as an explicitly signed percentage: `Decimal("-0.0021")` to
    the string for minus 0.21 percent, using U+2212.

    Duplicated from `console/format.py` rather than imported, and the duplication is
    deliberate. The console is a separate process that reads the database; an engine on
    the live loop importing from `console/` would invert that relationship and put a
    FastAPI-adjacent module on the trading path. The shared thing is the *rule*, which
    lives in `ui-context.md`, not the function. `tests/engines/test_cost.py` asserts the
    two implementations agree on a table of values, so the copy cannot drift silently.
    """
    if not value.is_finite():
        raise ValueError(f"refusing to render a non-finite percentage: {value!r}")
    exponent = Decimal(1).scaleb(-places)
    percent = (value * 100).quantize(exponent)
    if percent.is_signed() and percent != 0:
        return MINUS_SIGN + format(-percent, "f") + "%"
    # `is_signed()` is true for Decimal("-0.00"), which must not print as a negative
    # zero: the sign would report a direction the number does not have.
    return "+" + format(abs(percent), "f") + "%"


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #


class CostInputs(BaseModel):
    """Everything invariant 5's arithmetic needs, parsed and validated.

    `extra="ignore"` because these fields are read out of much larger published
    payloads; `frozen=True` because an engine must not mutate what another engine
    published.

    Every field is :data:`Money`. A `float` anywhere in this model is refused rather
    than coerced — spec 34 makes a float in the edge path a defect, and the point of
    refusing it here is that it is caught at the boundary with the field name attached
    instead of surfacing as a hurdle comparison that is wrong in the fourth decimal.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    pair: str
    expected_move_pct: Money
    maker_fee_pct: Money
    taker_fee_pct: Money
    spread_pct: Money
    slippage_pct: Money


class CostAssessment(BaseModel):
    """What this engine publishes into `state["cost"]`.

    The four percentage field names are **not** this engine's choice: they are the
    column names of the `rejections` table, which engine 19 `memory` fills from exactly
    this payload. Naming them anything else here would put a translation step between
    the engine that computes a number and the table that stores it, which is a place for
    them to stop meaning the same thing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    expected_move_pct: Money
    friction_pct: Money
    net_edge_pct: Money
    hurdle_pct: Money
    clears_hurdle: bool
    reason_code: str | None = None
    fallbacks_used: tuple[str, ...] = ()

    def to_state_data(self) -> dict[str, Any]:
        """The JSON-serialisable form the orchestrator will put in `state["cost"]`.

        Money leaves as an exact decimal string in plain notation. `format(d, "f")`
        rather than `str(d)`: `str(Decimal("1E-4"))` is `"1E-4"`, which round-trips
        through `Decimal()` but compares unequal to `"0.0001"` under any text
        comparison, and these strings reach a TEXT column in `rejections`.
        """
        return {
            "pair": self.pair,
            "expected_move_pct": format(self.expected_move_pct, "f"),
            "friction_pct": format(self.friction_pct, "f"),
            "net_edge_pct": format(self.net_edge_pct, "f"),
            "hurdle_pct": format(self.hurdle_pct, "f"),
            "clears_hurdle": self.clears_hurdle,
            "reason_code": self.reason_code,
            "fallbacks_used": list(self.fallbacks_used),
        }
