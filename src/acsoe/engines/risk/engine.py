"""Engine 11 `risk` — sizes a position, and refuses one that cannot be placed honestly.

## The sizing

Invariant 6: "Risk per trade never exceeds the configured fraction of total account
equity." **Risk, not notional.** The money at risk on a position is the distance to its
stop, so:

```
risk_amount = equity x trading.risk_fraction_per_trade
notional    = risk_amount / barriers.stop_pct
qty         = round_down(notional / ask, lot_decimals)
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

## One position per pair, and a resting entry counts as one

Invariant 6's last clause — "one open position per pair" — is enforced here, by
:meth:`RiskEngine._pair_exposure`, and it was enforced **nowhere** before spec 89: the
portfolio cap counts open positions and never asks which pair they are on. A resting
post-only entry on the pair refuses a second candidate exactly as an open position does,
because it is exposure that has not happened yet; that is the reading invariant 14
already applies to `safety`'s escalation precondition, and a second entry placed beside
an unfilled one doubles the money at risk the moment both fill.

**It is asked before the portfolio cap**, by a lead ruling of 2026-09-16 that reverses
the order spec 89 shipped with. The cap is inert at the configured balance — three
allowed positions against a balance that affords one — so cap-first would have hidden
this clause on every tick where it is the rule doing the work.

## Which side of the book, and why it is two sides

**The quantity is sized from the ask; `costmin` is tested against the bid.** A lead
ruling of 2026-09-10, made under spec 41 because nothing published a price at all and one
had to be chosen. The entry is a buy, so the ask is the worst price it could pay, and a
higher assumed price yields *fewer* units for the same money — the position is never
larger than the sizing chose. The bid is the lowest the resulting position could be
valued at, so testing the minimum order value there refuses a marginal position rather
than admitting one. Rounding down and then valuing at the lower side is fail-closed on
both edges.

It does not double-count the spread against engine 10. That gate charges the spread as
*friction on a round trip*; this one uses the book to answer *how many units the money
buys*. Two different questions asked of the same data.

## Invariant 2's one surviving paper-mode fallback

Spec 37 retired the fee-tier row, so **balance is the only paper-mode fallback left in
this system**, and :meth:`RiskEngine._balances` is its only implementation. In `paper`
mode a failed `Balance` fetch sizes against `paper.starting_balances` and records
`balance_from_paper_starting_balances` on the decision; in every other mode it blocks.
The fallback is never optimistic and never silent — invariant 2 requires both.

## What is fetched, never remembered

`ordermin`, `costmin` and `lot_decimals` come from `AssetPairs` through engine 1, and the
two prices from the live book through engine 3. `AGENTS.md`: any remembered order minimum
is stale. Nothing in this module or its contracts contains one, and a test reads the
source to prove it.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any, NamedTuple

from pydantic import ValidationError

from acsoe.clients.store.contracts import OrderIntent
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.risk.contracts import (
    EXCHANGE_BALANCES_KEY,
    EXCHANGE_KEY,
    EXCHANGE_PAIR_RULES_KEY,
    FALLBACK_BALANCE_FROM_PAPER,
    MARKET_SENSOR_KEY,
    MARKET_SENSOR_QUOTES_KEY,
    PAIR_COSTMIN_FIELD,
    PAIR_LOT_DECIMALS_FIELD,
    PAIR_ORDERMIN_FIELD,
    PAIR_QUOTE_FIELD,
    PAIR_RULES_PAIRS_KEY,
    QUOTE_ASK_FIELD,
    QUOTE_BID_FIELD,
    REASON_BELOW_COSTMIN,
    REASON_BELOW_ORDERMIN,
    REASON_ENTRY_RESTING_ON_PAIR,
    REASON_INPUTS_UNAVAILABLE,
    REASON_INSUFFICIENT_QUOTE_BALANCE,
    REASON_MAX_CONCURRENT_POSITIONS,
    REASON_NO_FX_RATE,
    REASON_POSITION_OPEN_ON_PAIR,
    SCOUT_KEY,
    RiskInputs,
    RiskSizing,
    round_down_to_lot,
)

RISK_FRACTION_KEY = "trading.risk_fraction_per_trade"
REPORTING_CURRENCY_KEY = "trading.base_reporting_currency"
MAX_CONCURRENT_KEY = "trading.max_concurrent_positions"
STOP_PCT_KEY = "barriers.stop_pct"

#: The currency-to-amount map invariant 2 names as the balance fallback. Read only in
#: paper mode, only when engine 1 published no balances at all, and never otherwise.
PAPER_STARTING_BALANCES_KEY = "paper.starting_balances"

#: The one mode the balance fallback applies in. `live` blocks because invariant 2 says a
#: failed fetch always blocks in live mode; `replay` blocks because it is not `paper` and
#: because blocking is the direction a gate defaults in. See the README.
PAPER_MODE = "paper"


class MissingInputError(Exception):
    """An input this gate needs is absent, null, or the wrong shape."""


class PairExposure(NamedTuple):
    """Exposure this pair already carries, and how the refusal reads.

    Carried as a value rather than raised, because it is a *refusal* and not a missing
    input: the gate knows the answer and the answer is no. A `MissingInputError` here
    would report a working store as unreachable.
    """

    reason_code: str
    reason: str


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
            inputs, fallbacks = self._read_inputs(context, state)
            exposure = self._pair_exposure(context, inputs.pair)
        except MissingInputError as missing:
            return self._blocked_on_missing_input(str(missing), started)

        # Invariant 6: **one open position per pair.** Checked before sizing, because what
        # this candidate would have been sized to is not a question worth answering once
        # it is refused, and answering it would put a quantity in the payload of a refused
        # candidate.
        #
        # **Asked before the portfolio cap below, and the order is a lead ruling of
        # 2026-09-16 that reverses the one spec 89 shipped with.** Both refusals can be
        # true on one tick and both block, so the order decides only which `reason_code`
        # the rejection row carries. It matters because the cap is *inert* at the
        # configured balance: `max_concurrent_positions` is 3, and at $5,000 with 1% risk
        # against a 1.5% stop one position is ~$3,333 notional, so the balance binds at
        # one. Checking the cap first would therefore hide invariant 6's specific clause
        # on every tick where it is the rule actually doing the work, not merely on a rare
        # tie. The earlier order was chosen to keep pre-spec-89 rejection codes stable,
        # and there are no such rows: no engine before Phase 6 could open a position.
        if exposure is not None:
            return self._reject(inputs, exposure.reason_code, exposure.reason, fallbacks, started)

        # The portfolio as a whole is full. The coarser of the two statements, and the one
        # that refuses a candidate on a pair the account does *not* already hold — which
        # is the only case where it is reachable once the per-pair rule has been asked.
        if open_positions >= max_concurrent:
            return self._reject(
                inputs,
                REASON_MAX_CONCURRENT_POSITIONS,
                f"Already holding {open_positions} of {max_concurrent} allowed positions",
                fallbacks,
                started,
            )

        risk_amount = inputs.equity * inputs.risk_fraction
        target_notional = risk_amount / inputs.stop_pct

        # Invariant 6: never allocate cash the account does not hold in that pair's quote
        # currency. Rejected rather than silently capped to the balance — a gate answers
        # yes or no, and a position quietly resized to fit is no longer the position the
        # sizing rule chose, which is the same objection as rounding up to a minimum.
        #
        # **Affordability cannot be computed across currencies, so the candidate is
        # refused.** `target_notional` derives from equity, which invariant 7 expresses in
        # `trading.base_reporting_currency`; the balance is in the pair's quote currency.
        # Comparing them needs an FX rate and nothing in this system publishes one, though
        # invariant 7 says one is converted "at the trade timestamp".
        #
        # Ruled by the operator on 2026-09-10. This engine has carried the comparison since
        # spec 35 and no test ever reached it: no fixture has a pair whose quote is not the
        # reporting currency that gets this far. It surfaced while engine 7 was being
        # written — the third caller of the same arithmetic — rather than by anything
        # failing. Engine 7 excludes such a pair from the universe under the same code.
        if inputs.quote_currency != inputs.reporting_currency:
            return self._reject(
                inputs,
                REASON_NO_FX_RATE,
                (
                    f"Position is priced in {inputs.reporting_currency} and the balance is "
                    f"in {inputs.quote_currency}, and there is no exchange rate to convert "
                    "between them"
                ),
                fallbacks,
                started,
            )

        # Tested on the notional the sizing *asked* for, before rounding. Rounding down at
        # the ask can only reduce the cash committed, so checking the larger figure is the
        # conservative direction.
        if target_notional > inputs.quote_balance:
            return self._reject(
                inputs,
                REASON_INSUFFICIENT_QUOTE_BALANCE,
                (
                    f"Position needs {target_notional:f} {inputs.quote_currency} and the "
                    f"account holds {inputs.quote_balance:f}"
                ),
                fallbacks,
                started,
            )

        # Sized at the **ask**: the entry is a buy, the ask is the worst price it could
        # pay, and a higher assumed price yields fewer units for the same money — so the
        # position is never larger than the sizing chose. Rounded down to the exchange's
        # precision *before* the minimum is tested, so the number compared against
        # `ordermin` is the number that would actually be sent.
        qty = round_down_to_lot(target_notional / inputs.ask, inputs.lot_decimals)

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

        # `costmin` is tested on the rounded quantity's real value **at the bid**, not on
        # the notional the sizing asked for. Two things are going on and both matter:
        # rounding down can drop the value below the minimum even when the requested
        # notional cleared it, and the bid is the lowest the position could be valued at,
        # so a marginal position is refused rather than admitted.
        value_at_bid = qty * inputs.bid
        if value_at_bid < inputs.costmin:
            return self._reject(
                inputs,
                REASON_BELOW_COSTMIN,
                (
                    f"Position value of {value_at_bid:f} {inputs.quote_currency} at the "
                    f"bid is below the pair's minimum order value of {inputs.costmin:f}"
                ),
                fallbacks,
                started,
            )

        sizing = RiskSizing(
            pair=inputs.pair,
            approved=True,
            qty=qty,
            notional=qty * inputs.ask,
            value_at_bid=value_at_bid,
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

    def _pair_exposure(self, context: EngineContext, pair: str) -> PairExposure | None:
        """Exposure this pair already carries, or `None` if it carries none.

        Invariant 6's "one open position per pair", which until spec 89 was enforced
        nowhere in `src/`: the portfolio cap above counts open positions and never asks
        which pair they are on, and engine 7 does not look. It was unreachable only
        because nothing in the system could open a position, and Phase 6 changes that.

        **A resting entry order counts as a position.** It is the same reading invariant
        14 applies to `safety`'s escalation precondition — "a resting post-only buy is
        exposure that has not happened yet" — and the arithmetic is unforgiving: a second
        entry placed beside an unfilled one doubles the money at risk the moment both
        fill, at which point no gate is left to refuse it.

        Read from the store and not from `state` for the structural reason the cap is:
        this gate runs in the opportunity chain and the manage chain runs after it, so
        `state["position_manager"]` does not exist yet.

        Any store failure is "cannot reach my data", which invariant 3 makes a block. The
        `except` is deliberately broad for the reason :meth:`_count_open_positions` gives:
        a database error escaping as an unexpected exception would still become ERROR at
        the orchestrator, but with a reason nobody can read.
        """
        store = getattr(context.clients, "store", None)
        if store is None:
            raise MissingInputError("clients.store is not available")
        try:
            positions = tuple(store.open_positions())
            resting = tuple(store.resting_orders(intent=OrderIntent.ENTRY))
        except Exception as exc:
            raise MissingInputError(f"could not read existing exposure on {pair}: {exc}") from exc

        for position in positions:
            if str(position.pair) == pair:
                return PairExposure(
                    REASON_POSITION_OPEN_ON_PAIR,
                    (
                        f"{pair} already has an open position, {position.position_id}, and "
                        "only one position per pair is allowed"
                    ),
                )
        for order in resting:
            if str(order.pair) == pair:
                return PairExposure(
                    REASON_ENTRY_RESTING_ON_PAIR,
                    (
                        f"{pair} already has an entry order resting on the book, userref "
                        f"{order.userref}, which is a position that has not filled yet"
                    ),
                )
        return None

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
        reporting = str(context.config.get(REPORTING_CURRENCY_KEY))
        if currency != reporting:
            raise MissingInputError(
                f"latest equity snapshot is in {currency}, not the reporting currency {reporting}"
            )
        equity: Decimal = snapshot.equity
        return equity

    def _read_inputs(
        self, context: EngineContext, state: State
    ) -> tuple[RiskInputs, tuple[str, ...]]:
        """The sizing inputs, and any fallback that had to fire to assemble them.

        The fallbacks travel with the inputs rather than being recomputed later, because
        invariant 2 requires the *decision* to record which fallback fired and there is
        exactly one place that knows: the point where the substitution happened.
        """
        pair = _require(state.get(SCOUT_KEY), "pair", SCOUT_KEY)

        # Two levels, both through `_require`. Engine 1 publishes the whole `AssetPairs`
        # snapshot, so a null `pair_rules` — the failed-fetch case — has to report as the
        # missing snapshot it is rather than as an unknown pair. Invariant 2 gives pair
        # rules no fallback in any mode: a wrong `ordermin` produces invalid orders.
        exchange = state.get(EXCHANGE_KEY)
        pair_rules = _require(exchange, EXCHANGE_PAIR_RULES_KEY, EXCHANGE_KEY)
        rules_where = f"{EXCHANGE_KEY}.{EXCHANGE_PAIR_RULES_KEY}"
        pairs = _require(pair_rules, PAIR_RULES_PAIRS_KEY, rules_where)
        facts = _require(pairs, str(pair), f"{rules_where}.{PAIR_RULES_PAIRS_KEY}")
        where = f"{rules_where}.{PAIR_RULES_PAIRS_KEY}.{pair}"
        quote = str(_require(facts, PAIR_QUOTE_FIELD, where))

        balances, fallbacks = self._balances(context, exchange, quote)
        quotes = _require(
            state.get(MARKET_SENSOR_KEY), MARKET_SENSOR_QUOTES_KEY, MARKET_SENSOR_KEY
        )
        quotes_where = f"{MARKET_SENSOR_KEY}.{MARKET_SENSOR_QUOTES_KEY}"
        book = _require(quotes, str(pair), quotes_where)

        raw: dict[str, Any] = {
            "pair": pair,
            "quote_currency": quote,
            "reporting_currency": str(context.config.get(REPORTING_CURRENCY_KEY)),
            "ask": _require(book, QUOTE_ASK_FIELD, f"{quotes_where}.{pair}"),
            "bid": _require(book, QUOTE_BID_FIELD, f"{quotes_where}.{pair}"),
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
        # A non-positive price is not a cheap entry, it is an unusable quote. Checked on
        # both sides: a zero ask divides, and a zero bid would value every position at
        # nothing and refuse it for the wrong reason.
        if inputs.ask <= 0 or inputs.bid <= 0:
            raise MissingInputError(f"{quotes_where}.{pair} has a non-positive price")
        if inputs.stop_pct <= 0:
            raise MissingInputError(f"config {STOP_PCT_KEY} must be positive")
        return inputs, fallbacks

    def _balances(
        self, context: EngineContext, exchange: Any, quote: str
    ) -> tuple[Any, tuple[str, ...]]:
        """The account's balances — or invariant 2's one surviving paper-mode fallback.

        **This is the only fallback left in the system.** Spec 37 retired "assume tier 1"
        on 2026-09-10, and pair rules and the spread block in every mode, so the balance
        row is the last one in invariant 2's paper-mode table that still substitutes a
        value instead of refusing. Engine 1 deliberately applies no fallback of its own —
        it reports the failed call and leaves the decision to the consumer that has to
        record which one fired — so this method is where the row is implemented.

        Three cases, and only the second is a fallback:

        - `balances` present: use it. A currency *missing from* a published map is not a
          failed fetch — it is an account that holds nothing in that currency, and it is
          refused by the caller's `_require` rather than substituted here.
        - `balances` absent, mode is `paper`: `paper.starting_balances`, recorded.
        - `balances` absent, any other mode: block. Invariant 2 is explicit that in live
          mode a failed fetch always blocks, and the one exception in that document is
          rule 14's liquidation, which is not this. `replay` is not `paper` either, and a
          gate defaults towards refusing.

        The map is used exactly as configured. "Adjusted by simulated fills" is the fill
        simulator's contribution and that is Phase 6; the `README.md` names the phase so
        the gap is recorded rather than discovered.
        """
        published = exchange.get(EXCHANGE_BALANCES_KEY) if isinstance(exchange, dict) else None
        if published is not None:
            return published, ()

        if context.mode != PAPER_MODE:
            raise MissingInputError(
                f"{EXCHANGE_KEY}.{EXCHANGE_BALANCES_KEY} in {context.mode} mode, where a "
                "failed fetch blocks (invariant 2); the balance fallback is paper-mode only"
            )
        try:
            starting = context.config.get(PAPER_STARTING_BALANCES_KEY)
        except Exception as exc:
            # An absent key raises by contract. That is a gate that cannot reach its
            # configuration, which blocks — it is never a reason to invent a balance.
            raise MissingInputError(
                f"config {PAPER_STARTING_BALANCES_KEY} is unreadable: {exc}"
            ) from exc
        if not isinstance(starting, dict) or not starting:
            raise MissingInputError(
                f"config {PAPER_STARTING_BALANCES_KEY} is not a currency-to-amount map"
            )
        if quote not in starting:
            # Falling back to a map that does not name this pair's quote currency would
            # be substituting nothing for something. Refused, and named, so the operator
            # can see which currency the paper account was never given.
            raise MissingInputError(
                f"config {PAPER_STARTING_BALANCES_KEY} names no {quote} balance to fall "
                "back to"
            )
        return dict(starting), (FALLBACK_BALANCE_FROM_PAPER,)

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


__all__ = ["MissingInputError", "PairExposure", "RiskEngine"]
