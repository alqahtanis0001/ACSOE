"""What engine 11 `risk` reads out of `state` and what it writes back into it.

The same two boundary rules as engine 10, for the same reasons, and they are restated
here rather than imported because an engine never imports another engine:

- **Money crosses `state` as an exact decimal string.** `EngineResult.data` refuses a
  `Decimal` and *accepts* a `float`, which is the dangerous half — a float has already
  lost precision by the time it arrives, and spec 35 is explicit that float drift in an
  order quantity produces a Kraken rejection that is miserable to diagnose. Every money
  field below is :data:`Money`, the `Decimal` that raises on a float rather than
  coercing it.
## What is the publisher's, and what was assumed — corrected 2026-09-10, spec 41

An earlier version of this docstring said the state paths were "B's proposal". They were,
and the Phase 3 audit found two of them wrong and one of them impossible. The distinction
is worth writing down rather than quietly fixing, because it is the same distinction spec
40 drew for the cost gate.

| Assumed | What is actually there |
|---|---|
| `exchange.pairs[pair]` | `exchange.pair_rules.pairs[pair]` — engine 1 publishes the whole `AssetPairs` snapshot, `{fetched_at, pairs: {...}}` |
| `exchange.pairs[pair].last_price` | **Nothing publishes a price into `state["exchange"]` at all.** See below |
| `exchange.fallbacks_used` | `exchange.failed_fetches`, which is a different thing — spec 40's finding, and the same fix: the dead read is deleted |

`exchange.balances` was audited and is **correct**: a flat `{currency: decimal string}`
map, straight off `BalancesSnapshot.state_dict()`.

**The price is not a renamed field — there was no field.** `AssetPairs` carries no price
and engine 1 does not fetch one; the only `last_price` in this codebase is a column on an
open position row, which is a fact about a position rather than about the market. The
entry price now comes from :data:`MARKET_SENSOR_QUOTES_KEY`, the same publisher engine 10
reads its spread from, and *which side of the book* it comes from is a lead ruling
recorded in the `README.md` rather than an implementation detail: the quantity is sized
from the **ask** and `costmin` is tested against the **bid**.

`ordermin`, `costmin` and `lot_decimals` still come from `AssetPairs` through engine 1,
never from a constant or a config key — spec 35 fixes that and it has not changed. Every
path is a `Final` constant so the next re-point is a single-line edit and is greppable,
which is the property that made this repair small.

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
    "EXCHANGE_KEY",
    "EXCHANGE_PAIR_RULES_KEY",
    "FALLBACK_BALANCE_FROM_PAPER",
    "MARKET_SENSOR_KEY",
    "MARKET_SENSOR_QUOTES_KEY",
    "MINUS_SIGN",
    "PAIR_COSTMIN_FIELD",
    "PAIR_LOT_DECIMALS_FIELD",
    "PAIR_ORDERMIN_FIELD",
    "PAIR_QUOTE_FIELD",
    "PAIR_RULES_PAIRS_KEY",
    "QUOTE_ASK_FIELD",
    "QUOTE_BID_FIELD",
    "REASON_BELOW_COSTMIN",
    "REASON_BELOW_ORDERMIN",
    "REASON_INPUTS_UNAVAILABLE",
    "REASON_INSUFFICIENT_QUOTE_BALANCE",
    "REASON_MAX_CONCURRENT_POSITIONS",
    "REASON_NO_FX_RATE",
    "SCOUT_KEY",
    "RiskInputs",
    "RiskSizing",
    "round_down_to_lot",
]

# --------------------------------------------------------------------------- #
# State paths — see the module docstring for what was assumed and what is real
# --------------------------------------------------------------------------- #

#: Engine 1 `exchange` (A). The account engine: balances, fee tier, pair rules.
EXCHANGE_KEY: Final = "exchange"

#: The whole `AssetPairs` snapshot, under :data:`EXCHANGE_KEY`. Corrected from `"pairs"`
#: on 2026-09-10: engine 1 publishes the snapshot, not the mapping inside it, so the real
#: path is one level deeper than the assumed one and every live tick blocked.
EXCHANGE_PAIR_RULES_KEY: Final = "pair_rules"

#: The per-pair mapping *inside* that snapshot, beside its `fetched_at`. Kept as its own
#: constant rather than folded into a dotted path so a null `pair_rules` — the failed
#: `AssetPairs` case — reports as the missing thing it is rather than as a missing pair.
PAIR_RULES_PAIRS_KEY: Final = "pairs"

#: A flat `{currency: decimal string}` map, under :data:`EXCHANGE_KEY`. Audited and
#: correct as written. **Absent when the `Balance` fetch failed**, which is the one place
#: in this system where invariant 2's paper-mode fallback still applies — see the engine.
EXCHANGE_BALANCES_KEY: Final = "balances"

#: Engine 3 `market_sensor` (A). The market-data engine, and the publisher of the entry
#: price. Not engine 1, which is the account engine and states no price at all.
MARKET_SENSOR_KEY: Final = "market_sensor"

#: Per-pair top-of-book quotes, under :data:`MARKET_SENSOR_KEY`, keyed by pair name. The
#: same mapping engine 10 `cost` reads its spread from.
MARKET_SENSOR_QUOTES_KEY: Final = "quotes"

#: The two sides of the book, as `QuoteView.state_dict()` writes them. **Which side is
#: used where is a lead ruling, not an implementation choice** — the quantity is sized
#: from the ask and `costmin` is tested against the bid. The reasoning is in the
#: `README.md`, because the next agent has to be able to see it was decided.
QUOTE_ASK_FIELD: Final = "ask"
QUOTE_BID_FIELD: Final = "bid"

#: Engine 7 `scout` (B). Which pair the tick is considering.
SCOUT_KEY: Final = "scout"

#: The name of invariant 2's one surviving paper-mode fallback, as it is recorded on the
#: decision. Written into `rejections.fallbacks_used` by engine 19, and it is the only
#: string this engine ever puts there.
FALLBACK_BALANCE_FROM_PAPER: Final = "balance_from_paper_starting_balances"

#: `AssetPairs` fields, per pair. **Never a constant and never a config key** — spec 35
#: quotes `AGENTS.md`: any remembered order minimum is stale.
PAIR_ORDERMIN_FIELD: Final = "ordermin"
PAIR_COSTMIN_FIELD: Final = "costmin"

#: Decimal places the exchange accepts on a quantity. Quantities are rounded **down** to
#: this, always: rounding up produces an order Kraken rejects, and dust is cheaper than a
#: rejection. Invariant 14 states the rule for a liquidation; it is the same arithmetic
#: here, and there is no case where rounding a quantity up is correct.
PAIR_LOT_DECIMALS_FIELD: Final = "lot_decimals"

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

#: Affordability cannot be computed: the notional is in `trading.base_reporting_currency`
#: and the balance is in the pair's quote currency, and **nothing in this system publishes
#: an exchange rate between them.**
#:
#: **Ruled by the operator on 2026-09-10.** This engine has carried the comparison since
#: spec 35 and no test ever reached it, because no fixture had a pair whose quote is not the
#: reporting currency that got this far. It surfaced while engine 7 `scout` was being
#: written — the third caller of the same arithmetic — rather than by anything failing.
#:
#: Refusing claims nothing about the world, which is what separates it from inventing a rate
#: or assuming parity. Shared with engine 7, which excludes such a pair from the universe
#: under the same code and for the same reason.
REASON_NO_FX_RATE: Final = "no_fx_rate"

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

    **Two prices, not one.** `ask` and `bid` are carried separately and are never blended
    into a mid, because the two questions this engine asks of the book are different ones:
    how many units the money buys (the ask, the worst the buy could pay) and what the
    position is then worth (the bid, the lowest it could be valued at). A single mid price
    would answer both slightly optimistically, and this is a gate.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    pair: str
    quote_currency: str
    reporting_currency: str
    ask: Money
    bid: Money
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

    **`notional` and `value_at_bid` are two different numbers and both are published.**
    `notional` is `qty x ask` — the cash the order commits at the worst price the buy
    could pay. `value_at_bid` is `qty x bid` — what the position is immediately worth, and
    the figure `costmin` was actually tested against. They are equal only on a zero
    spread. Publishing one and calling it both would put the number a decision was *not*
    made on into the record of that decision.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    approved: bool
    qty: Money | None = None
    notional: Money | None = None
    value_at_bid: Money | None = None
    risk_amount: Money | None = None
    ordermin: Money
    costmin: Money
    reason_code: str | None = None
    fallbacks_used: tuple[str, ...] = ()

    def to_state_data(self) -> dict[str, Any]:
        """The JSON-serialisable payload, money as exact decimal strings.

        On a rejection `qty`, `notional`, `value_at_bid` and `risk_amount` are **omitted
        entirely** rather than emitted as `null`. A `null` would be honest but it would
        also be a key called `qty` sitting in the payload of a refused candidate, and the
        failure this engine exists to prevent is precisely a quantity being read where
        none was approved.
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
                ("value_at_bid", self.value_at_bid),
                ("risk_amount", self.risk_amount),
            ):
                if value is not None:
                    payload[field] = format(value, "f")
        return payload
