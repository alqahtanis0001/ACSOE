"""What engine 11 `risk` reads out of `state` and what it writes back into it.

The same two boundary rules as engine 10, for the same reasons, and they are restated
here rather than imported because an engine never imports another engine:

- **Money crosses `state` as an exact decimal string.** `EngineResult.data` refuses a
  `Decimal` and *accepts* a `float`, which is the dangerous half — a float has already
  lost precision by the time it arrives, and spec 35 is explicit that float drift in an
  order quantity produces a Kraken rejection that is miserable to diagnose. Every money
  field below is :data:`Money`, the `Decimal` that raises on a float rather than
  coercing it.
- **The state paths are B's proposal.** `ordermin`, `costmin` and `lot_decimals` come
  from `AssetPairs` through A's engine 1; spec 35 fixes that they come from there and
  not from a constant or a config key, and does not fix the key names. They are `Final`
  constants so re-pointing one is a single-line edit.

## What is deliberately *not* here

There is no rounding-up path, no `allow_round_up` flag, and no configuration key that
could introduce one. Spec 35 forbids it "under any flag or config key", and invariant 6
says a position below `ordermin` or `costmin` is a rejection, "never round up to meet a
minimum". The absence is the feature: rounding up silently increases the money at risk
beyond what the sizing decided, which is the opposite of what a risk gate is for.

:class:`RiskSizing` therefore has no `qty` field at all on a rejection. Not `None`, not
zero, not the minimum — absent, so there is no field an execution engine could read a
quantity out of by mistake.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import Money

__all__ = [
    "EXCHANGE_BALANCES_KEY",
    "EXCHANGE_FALLBACKS_KEY",
    "EXCHANGE_KEY",
    "EXCHANGE_PAIRS_KEY",
    "MINUS_SIGN",
    "PAIR_COSTMIN_FIELD",
    "PAIR_LOT_DECIMALS_FIELD",
    "PAIR_ORDERMIN_FIELD",
    "PAIR_PRICE_FIELD",
    "PAIR_QUOTE_FIELD",
    "REASON_BELOW_COSTMIN",
    "REASON_BELOW_ORDERMIN",
    "REASON_INPUTS_UNAVAILABLE",
    "REASON_INSUFFICIENT_QUOTE_BALANCE",
    "REASON_MAX_CONCURRENT_POSITIONS",
    "SCOUT_KEY",
    "RiskInputs",
    "RiskSizing",
    "round_down_to_lot",
]

# --------------------------------------------------------------------------- #
# State paths — provisional, see the module docstring
# --------------------------------------------------------------------------- #

EXCHANGE_KEY: Final = "exchange"
EXCHANGE_PAIRS_KEY: Final = "pairs"
EXCHANGE_BALANCES_KEY: Final = "balances"
EXCHANGE_FALLBACKS_KEY: Final = "fallbacks_used"
SCOUT_KEY: Final = "scout"

#: `AssetPairs` fields, per pair. **Never a constant and never a config key** — spec 35
#: quotes `AGENTS.md`: any remembered order minimum is stale.
PAIR_ORDERMIN_FIELD: Final = "ordermin"
PAIR_COSTMIN_FIELD: Final = "costmin"

#: Decimal places the exchange accepts on a quantity. Quantities are rounded **down** to
#: this, always: rounding up produces an order Kraken rejects, and dust is cheaper than a
#: rejection. Invariant 14 states the rule for a liquidation; it is the same arithmetic
#: here, and there is no case where rounding a quantity up is correct.
PAIR_LOT_DECIMALS_FIELD: Final = "lot_decimals"

#: The reference price a notional is converted to a quantity at. Sizing needs *a* price;
#: the actual post-only limit price is engine 16's decision and engine 18's order.
PAIR_PRICE_FIELD: Final = "last_price"

#: The pair's quote currency, so the balance check looks at the right pot. Invariant 7:
#: a pair is only executable if the account holds spendable balance in that quote
#: currency, and it is a per-pair fact rather than a global one.
PAIR_QUOTE_FIELD: Final = "quote"

# --------------------------------------------------------------------------- #
# Reason codes — C's, from `console/format.py`'s REASON_PROSE
# --------------------------------------------------------------------------- #

#: All four already exist in C's mapping from a stored code to the sentence an operator
#: reads. A code absent from that table renders "No reason was recorded.", silently, so
#: `tests/engines/test_risk.py` asserts these are present.
REASON_BELOW_ORDERMIN: Final = "below_ordermin"
REASON_BELOW_COSTMIN: Final = "below_costmin"
REASON_INSUFFICIENT_QUOTE_BALANCE: Final = "insufficient_quote_balance"
REASON_MAX_CONCURRENT_POSITIONS: Final = "max_concurrent_positions"

#: Fail-closed. Not in C's table yet; flagged. The reason written alongside it is always
#: prose, and `operator_reason` prefers prose over the mapping, so it renders correctly
#: meanwhile.
REASON_INPUTS_UNAVAILABLE: Final = "risk_inputs_unavailable"

MINUS_SIGN: Final = "\N{MINUS SIGN}"


def round_down_to_lot(quantity: Decimal, lot_decimals: int) -> Decimal:
    """Round a quantity **down** to the exchange's accepted precision.

    Down, never to-nearest. `ROUND_HALF_UP` on a quantity one ulp below `ordermin` would
    round it *to* `ordermin` and hand the caller a position the sizing never chose — the
    rounding-up defect arriving through the back door of a rounding mode rather than
    through an explicit bump. Invariant 14 fixes the same rule for a liquidation:
    "rounding down leaves dust; rounding up produces an order Kraken rejects".
    """
    if lot_decimals < 0:
        raise ValueError(f"lot_decimals must not be negative, got {lot_decimals}")
    return quantity.quantize(Decimal(1).scaleb(-lot_decimals), rounding=ROUND_DOWN)


class RiskInputs(BaseModel):
    """Everything the sizing arithmetic needs, parsed and validated.

    `lot_decimals` is an `int` rather than :data:`Money` because it is a count of digits,
    not an amount. Everything else is money and refuses a float.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    pair: str
    quote_currency: str
    last_price: Money
    ordermin: Money
    costmin: Money
    lot_decimals: int
    equity: Money
    quote_balance: Money
    risk_fraction: Money
    stop_pct: Money


class RiskSizing(BaseModel):
    """What this engine publishes into `state["risk"]`.

    **`qty` is absent on every rejection.** Not `None`, not zero, not the minimum: the
    field does not appear in the payload at all, so there is no value an execution engine
    could pick up by mistake and no field a future refactor could quietly start filling
    with `ordermin`. That is the whole behavioural claim of spec 35, expressed in the
    shape of the payload rather than only in a branch.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    approved: bool
    qty: Money | None = None
    notional: Money | None = None
    risk_amount: Money | None = None
    ordermin: Money
    costmin: Money
    reason_code: str | None = None
    fallbacks_used: tuple[str, ...] = ()

    def to_state_data(self) -> dict[str, Any]:
        """The JSON-serialisable payload, money as exact decimal strings.

        On a rejection `qty`, `notional` and `risk_amount` are **omitted entirely**
        rather than emitted as `null`. A `null` would be honest but it would also be a
        key called `qty` sitting in the payload of a refused candidate, and the failure
        this engine exists to prevent is precisely a quantity being read where none was
        approved.
        """
        payload: dict[str, Any] = {
            "pair": self.pair,
            "approved": self.approved,
            "ordermin": format(self.ordermin, "f"),
            "costmin": format(self.costmin, "f"),
            "reason_code": self.reason_code,
            "fallbacks_used": list(self.fallbacks_used),
        }
        if self.approved:
            for field, value in (
                ("qty", self.qty),
                ("notional", self.notional),
                ("risk_amount", self.risk_amount),
            ):
                if value is not None:
                    payload[field] = format(value, "f")
        return payload
