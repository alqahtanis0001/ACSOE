"""Engine 11 `risk` — sizes a position, and refuses one that cannot be placed honestly.

## The sizing

Invariant 6: "Risk per trade never exceeds the configured fraction of total account
equity." **Risk, not notional.** The money at risk on a position is the distance to its
stop, so:

```
risk_amount = equity x trading.risk_fraction_per_trade
notional    = risk_amount / barriers.stop_pct
qty         = round_down(notional / price, lot_decimals)
```

Reading `risk_fraction_per_trade` as a fraction of *notional* rather than of money at
risk would size a position 66 times smaller than intended at the configured stop, which
is the kind of error that looks conservative and quietly makes the whole system
untestable. The committed config carries the arithmetic as a comment on
`max_concurrent_positions` — "the balance binds first at $5,000: one position is ~$3,333
notional" — and $5,000 x 1% / 1.5% is $3,333.33, so the intended reading is not inferred
here, it is stated there.

## The refusal

**A position below `ordermin` or `costmin` is rejected, not rounded up.** Invariant 6
says so, spec 35 says so "under any flag or config key", and there is no code path in
this module that could do otherwise: on a rejection the payload has no `qty` field at
all. Rounding up silently increases the money at risk beyond what the sizing decided,
which is the opposite of what a risk gate is for.

Rounding *down* to `lot_decimals` happens **before** the `ordermin` comparison, and the
order matters. Rounding after the check would let a quantity that passed `ordermin` be
rounded below it and placed anyway; rounding before means the number compared against the
minimum is the number that would actually be sent.

## What is fetched, never remembered

`ordermin`, `costmin`, `lot_decimals` and the price come from `AssetPairs` and the live
book through engine 1. `AGENTS.md`: any remembered order minimum is stale. Nothing in
this module or its contracts contains one, and a test reads the source to prove it.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.risk.contracts import (
    EXCHANGE_BALANCES_KEY,
    EXCHANGE_FALLBACKS_KEY,
    EXCHANGE_KEY,
    EXCHANGE_PAIRS_KEY,
    PAIR_COSTMIN_FIELD,
    PAIR_LOT_DECIMALS_FIELD,
    PAIR_ORDERMIN_FIELD,
    PAIR_PRICE_FIELD,
    PAIR_QUOTE_FIELD,
    REASON_BELOW_COSTMIN,
    REASON_BELOW_ORDERMIN,
    REASON_INPUTS_UNAVAILABLE,
    REASON_INSUFFICIENT_QUOTE_BALANCE,
    REASON_MAX_CONCURRENT_POSITIONS,
    SCOUT_KEY,
    RiskInputs,
    RiskSizing,
    round_down_to_lot,
)

RISK_FRACTION_KEY = "trading.risk_fraction_per_trade"
MAX_CONCURRENT_KEY = "trading.max_concurrent_positions"
STOP_PCT_KEY = "barriers.stop_pct"


class MissingInputError(Exception):
    """An input this gate needs is absent, null, or the wrong shape."""


def _require(container: Any, key: str, where: str) -> Any:
    """Fetch `key`, treating a published `None` exactly like an absent one.

    A null `ordermin` means the `AssetPairs` fetch failed. Invariant 2 is explicit that
    there is no fallback for pair rules — "block that pair, a wrong `ordermin` produces
    invalid orders" — so it must not be readable as zero, which would make every position
    trivially large enough.
    """
    if not isinstance(container, dict):
        raise MissingInputError(f"{where} is {type(container).__name__}, expected a mapping")
    if key not in container or container[key] is None:
        raise MissingInputError(f"{where}.{key}")
    return container[key]


def _config_decimal(context: EngineContext, key: str) -> Decimal:
    """A configured number as a `Decimal`, blocking on absent or null.

    A YAML scalar like `0.01` parses to a Python `float`, and `Decimal(0.01)` is not
    `0.01`. The conversion therefore goes through `repr`, which gives the shortest string
    that round-trips — the only safe route from a YAML number to an exact decimal.
    A null key is the OPERATOR REQUIRED state and blocks rather than defaulting: a
    default here would be a number silently deciding how much money is at risk.
    """
    value = context.config.get(key)
    if value is None:
        raise MissingInputError(f"config {key} is null (OPERATOR REQUIRED)")
    try:
        return Decimal(repr(value) if isinstance(value, float) else str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MissingInputError(f"config {key} is not a number: {value!r}") from exc


class RiskEngine(BaseEngine):
    """Gate 11. Opportunity chain, runtime stage 3."""

    name = "risk"
    number = 11
    is_gate = True

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        try:
            open_positions = self._count_open_positions(context)
            max_concurrent = int(_config_decimal(context, MAX_CONCURRENT_KEY))
            inputs = self._read_inputs(context, state)
        except MissingInputError as missing:
            return self._blocked_on_missing_input(str(missing), started)

        fallbacks = self._fallbacks(state)

        # Checked before sizing: the portfolio is already full, so what this candidate
        # would have been sized to is not a question worth answering, and answering it
        # would put a quantity in the payload of a refused candidate.
        if open_positions >= max_concurrent:
            return self._reject(
                inputs,
                REASON_MAX_CONCURRENT_POSITIONS,
                f"Already holding {open_positions} of {max_concurrent} allowed positions",
                fallbacks,
                started,
            )

        risk_amount = inputs.equity * inputs.risk_fraction
        notional = risk_amount / inputs.stop_pct

        # Invariant 6: never allocate cash the account does not hold in that pair's quote
        # currency. Rejected rather than silently capped to the balance — a gate answers
        # yes or no, and a position quietly resized to fit is no longer the position the
        # sizing rule chose, which is the same objection as rounding up to a minimum.
        if notional > inputs.quote_balance:
            return self._reject(
                inputs,
                REASON_INSUFFICIENT_QUOTE_BALANCE,
                (
                    f"Position needs {notional:f} {inputs.quote_currency} and the account "
                    f"holds {inputs.quote_balance:f}"
                ),
                fallbacks,
                started,
            )

        # Rounded down to the exchange's precision *before* the minimum is tested, so the
        # number compared against `ordermin` is the number that would actually be sent.
        qty = round_down_to_lot(notional / inputs.last_price, inputs.lot_decimals)

        if qty < inputs.ordermin:
            return self._reject(
                inputs,
                REASON_BELOW_ORDERMIN,
                (
                    f"Position of {qty:f} is below the pair's minimum order size of "
                    f"{inputs.ordermin:f}, short by {inputs.ordermin - qty:f}"
                ),
                fallbacks,
                started,
            )

        # `costmin` is tested on the rounded quantity's real value, not on the notional
        # the sizing asked for. Rounding down can drop the value below the minimum even
        # when the requested notional cleared it.
        value = qty * inputs.last_price
        if value < inputs.costmin:
            return self._reject(
                inputs,
                REASON_BELOW_COSTMIN,
                (
                    f"Position value of {value:f} {inputs.quote_currency} is below the "
                    f"pair's minimum order value of {inputs.costmin:f}"
                ),
                fallbacks,
                started,
            )

        sizing = RiskSizing(
            pair=inputs.pair,
            approved=True,
            qty=qty,
            notional=value,
            risk_amount=risk_amount,
            ordermin=inputs.ordermin,
            costmin=inputs.costmin,
            reason_code=None,
            fallbacks_used=fallbacks,
        )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=sizing.to_state_data(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ inputs

    def _count_open_positions(self, context: EngineContext) -> int:
        """How many positions are already open, from the store.

        Not from `state`. This engine runs in the opportunity chain and the manage chain
        runs after it, so `state["position_manager"]` does not exist yet — the same
        reason engine 17 reads the store, for the same structural cause.
        """
        store = getattr(context.clients, "store", None)
        if store is None:
            raise MissingInputError("clients.store is not available")
        try:
            return int(store.count_open_positions())
        except Exception as exc:
            # Any store failure is "cannot reach my data", which invariant 3 makes a
            # block. Deliberately broad: a gate that let a database error through as an
            # unexpected exception would still be converted to ERROR by the orchestrator,
            # but with a reason nobody can read.
            raise MissingInputError(f"could not count open positions: {exc}") from exc

    def _equity(self, context: EngineContext) -> Decimal:
        """Total account equity, from the latest `equity_snapshots` row.

        **Not the quote balance.** Invariant 6 sizes against "total account equity",
        which is cash plus the value of open positions, and only engine 19 `memory`
        computes that. Sizing against a single currency's cash balance would shrink the
        risk budget every time a position was opened, which is not what a fixed fraction
        of equity means.

        No snapshot is a block, not a fallback to the balance. A fallback here would be
        optimistic in exactly the way invariant 2 forbids: it would let the system size a
        trade against an equity figure nothing had computed.
        """
        store = getattr(context.clients, "store", None)
        if store is None:
            raise MissingInputError("clients.store is not available")
        snapshot = store.latest_equity_snapshot()
        if snapshot is None:
            raise MissingInputError("no equity_snapshots row yet; cannot size against equity")
        currency = str(snapshot.currency)
        reporting = str(context.config.get("trading.base_reporting_currency"))
        if currency != reporting:
            raise MissingInputError(
                f"latest equity snapshot is in {currency}, not the reporting currency {reporting}"
            )
        equity: Decimal = snapshot.equity
        return equity

    def _read_inputs(self, context: EngineContext, state: State) -> RiskInputs:
        pair = _require(state.get(SCOUT_KEY), "pair", SCOUT_KEY)

        exchange = state.get(EXCHANGE_KEY)
        pairs = _require(exchange, EXCHANGE_PAIRS_KEY, EXCHANGE_KEY)
        balances = _require(exchange, EXCHANGE_BALANCES_KEY, EXCHANGE_KEY)
        facts = _require(pairs, str(pair), f"{EXCHANGE_KEY}.{EXCHANGE_PAIRS_KEY}")
        where = f"{EXCHANGE_KEY}.{EXCHANGE_PAIRS_KEY}.{pair}"
        quote = str(_require(facts, PAIR_QUOTE_FIELD, where))

        raw: dict[str, Any] = {
            "pair": pair,
            "quote_currency": quote,
            "last_price": _require(facts, PAIR_PRICE_FIELD, where),
            "ordermin": _require(facts, PAIR_ORDERMIN_FIELD, where),
            "costmin": _require(facts, PAIR_COSTMIN_FIELD, where),
            "lot_decimals": _require(facts, PAIR_LOT_DECIMALS_FIELD, where),
            "equity": self._equity(context),
            "quote_balance": _require(
                balances, quote, f"{EXCHANGE_KEY}.{EXCHANGE_BALANCES_KEY}"
            ),
            "risk_fraction": _config_decimal(context, RISK_FRACTION_KEY),
            "stop_pct": _config_decimal(context, STOP_PCT_KEY),
        }
        try:
            inputs = RiskInputs.model_validate(raw)
        except ValidationError as exc:
            raise MissingInputError(f"unusable risk input: {exc}") from exc
        if inputs.last_price <= 0:
            raise MissingInputError(f"{where}.{PAIR_PRICE_FIELD} is not positive")
        if inputs.stop_pct <= 0:
            raise MissingInputError(f"config {STOP_PCT_KEY} must be positive")
        return inputs

    def _fallbacks(self, state: State) -> tuple[str, ...]:
        exchange = state.get(EXCHANGE_KEY)
        if not isinstance(exchange, dict):
            return ()
        used = exchange.get(EXCHANGE_FALLBACKS_KEY)
        if not isinstance(used, (list, tuple)):
            return ()
        return tuple(str(item) for item in used)

    # ------------------------------------------------------------------ outcomes

    def _reject(
        self,
        inputs: RiskInputs,
        reason_code: str,
        reason: str,
        fallbacks: tuple[str, ...],
        started: float,
    ) -> EngineResult:
        """Refuse the candidate. **No quantity is published, in any form.**

        `RiskSizing.to_state_data` omits `qty`, `notional` and `risk_amount` entirely
        when `approved` is false — not `null`, absent. There is therefore no field an
        execution engine could read a size out of and no field a later refactor could
        quietly start filling with `ordermin`, which is the failure spec 35 names.
        """
        sizing = RiskSizing(
            pair=inputs.pair,
            approved=False,
            ordermin=inputs.ordermin,
            costmin=inputs.costmin,
            reason_code=reason_code,
            fallbacks_used=fallbacks,
        )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=reason,
            data=sizing.to_state_data(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _blocked_on_missing_input(self, detail: str, started: float) -> EngineResult:
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=f"Risk gate could not size this candidate: missing {detail}",
            data={"reason_code": REASON_INPUTS_UNAVAILABLE, "approved": False},
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


__all__ = ["MissingInputError", "RiskEngine"]
