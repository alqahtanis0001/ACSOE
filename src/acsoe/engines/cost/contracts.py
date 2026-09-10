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

## What was ratified, and what was assumed — corrected 2026-09-10, spec 40

An earlier version of this docstring said all four state paths were ratified. Two of them
were not, and the distinction matters enough to write down rather than quietly fix.

**What the lead ratified on 2026-09-09 was a set of *positions* in the cross-chain key
table in `engine-contracts.md`** — which engine publishes each value and under which state
key. That table says the fee tier arrives on `state["exchange"]`, published by engine 1;
it does not fix engine 1's *field names*, and it never did.

**The field names below `state["exchange"]` were B's assumption**, written against a
contract that did not yet exist, and the Phase 3 audit found three of them wrong:

| Assumed | What engine 1 publishes |
|---|---|
| `exchange.fees` | `exchange.fee_tier` |
| `exchange.fees.maker_pct` / `taker_pct` | `exchange.fee_tier.maker_fee_pct` / `taker_fee_pct` |
| `exchange.fallbacks_used` | `exchange.failed_fetches` — a different thing, see below |

Every one of them was a `BLOCK` on a live tick, and the gate was fail-closed in the least
useful possible way: refusing everything, for the wrong reason, in prose naming a key
nothing writes. It stayed invisible for a whole phase because every test built
`state["exchange"]` by hand in the shape this engine expected. The fixtures are now built
from engine 1's own output; a mock that agrees with its caller is not a test of the seam.

**The spread path was ratified and is correct.** It is
`state["market_sensor"]["quotes"][pair]["spread_pct"]`, not
`state["exchange"]["pairs"][pair]["spread_pct"]` where B first proposed it. Engine 1
`exchange` is the *account* engine — balances, fee tier, pair rules — and engine 3
`market_sensor` is the *market-data* engine. Spread is market data. The deciding argument
is engine 4 `data_guard`, which blocks on stale data, a negative spread and a missing
candle: all three are market-data faults and should arrive from one publisher rather than
two. The one path that went through ratification is the one path that was right.

## `failed_fetches` is not `fallbacks_used`

Engine 1 deliberately applies no paper-mode fallback of its own — it reports which calls
failed and leaves the fallback decision to the consumer that has to record it. So there
is no `fallbacks_used` on `state["exchange"]` and there never was; this engine's read of
one returned an empty tuple on every tick, silently.

After spec 37 retired the fee-tier row of invariant 2's paper-mode table, **there is no
fee-tier fallback in any mode**: a confirmed pair with no fee data blocks. So this engine
applies no fallback at all, and :attr:`CostAssessment.fallbacks_used` — a real `rejections`
column — is correspondingly empty. It is kept, and it is sourced from fallbacks *this
engine applied*, not from engine 1's failed fetches. Copying a failed fetch into that
column would misreport the record invariant 2 asks for: a failure to fetch is not a
fallback, it is the opposite of one.

`failed_fetches` is still read, for one purpose only: when the fee tier is missing and the
`trade_volume` call is named there, the operator sentence quotes *that call's* reason.
"missing exchange.fee_tier" is true and sends the operator to the wrong place.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import Money

__all__ = [
    "CANDIDATE_PAIR_PATH",
    "EXCHANGE_FAILED_FETCHES_KEY",
    "EXCHANGE_FEE_TIER_KEY",
    "EXCHANGE_KEY",
    "FEE_MAKER_FIELD",
    "FEE_TAKER_FIELD",
    "FEE_TIER_CALL",
    "MARKET_SENSOR_KEY",
    "MARKET_SENSOR_QUOTES_KEY",
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
# State paths — see the module docstring for what was ratified and what was assumed
# --------------------------------------------------------------------------- #

#: Engine 1 `exchange` (A). The account engine: balances, fee tier, pair rules.
EXCHANGE_KEY: Final = "exchange"

#: Account-level fee tier, under :data:`EXCHANGE_KEY`. One tier per account, so it is
#: not keyed by pair. Corrected from `"fees"` on 2026-09-10: engine 1 publishes
#: `fee_tier`, and the assumed name blocked every live tick.
EXCHANGE_FEE_TIER_KEY: Final = "fee_tier"

#: The two rate fields under :data:`EXCHANGE_FEE_TIER_KEY`, as
#: `FeeTierSnapshot.state_dict()` writes them. Lifted out of `_read_inputs` so the next
#: mismatch is one edit and is greppable — the previous pair were string literals buried
#: in a call and nothing pointed at them.
FEE_MAKER_FIELD: Final = "maker_fee_pct"
FEE_TAKER_FIELD: Final = "taker_fee_pct"

#: Calls engine 1 reports as failed, under :data:`EXCHANGE_KEY`: a list of
#: `{call, kind, reason}`. **Not a fallback record** — see the module docstring. Read for
#: exactly one purpose: naming the call that failed in the operator sentence.
EXCHANGE_FAILED_FETCHES_KEY: Final = "failed_fetches"

#: The name engine 1 gives the fee-tier call in :data:`EXCHANGE_FAILED_FETCHES_KEY`.
#: Declared here rather than imported from `engines/exchange/`: engine contract rule 3,
#: an engine never imports another engine.
FEE_TIER_CALL: Final = "trade_volume"

#: Engine 3 `market_sensor` (A). The market-data engine, and therefore the publisher of
#: the measured spread — not engine 1, which is the account engine.
MARKET_SENSOR_KEY: Final = "market_sensor"

#: Per-pair top-of-book quotes, under :data:`MARKET_SENSOR_KEY`, keyed by pair name.
#: Per-tick, alongside `bar_closed`, which is per-bar.
MARKET_SENSOR_QUOTES_KEY: Final = "quotes"

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

    `fallbacks_used` is one of those columns and is kept for that reason. It holds the
    fallbacks **this engine applied**, and after spec 37 retired the fee-tier row of
    invariant 2's paper-mode table there are none, in any mode — so it is empty and this
    engine has nothing to put in it. It is not a copy of engine 1's `failed_fetches`: a
    failed fetch is the opposite of a fallback, and recording one there would misreport
    exactly the thing invariant 2 wants recorded.
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
