"""Engine 10 `cost` — the gate that refuses a trade which cannot pay for itself.

Invariant 5, verbatim, because this engine is the only implementation of it:

```
friction  = live_maker_fee + live_taker_fee + measured_spread + estimated_slippage
net_edge  = expected_move - friction
TRADE ONLY IF net_edge > hurdle_multiple x friction
```

"`net_edge` is what you compute. The rule is the third line. They are not the same
thing." The third line is the one thing in this module that may not be adjusted to make
anything pass.

**Friction assumes maker on entry and taker on exit.** A stop must always exit as a
taker, so that is the worst realistic round trip, and sizing the hurdle against a maker
exit would price a cost the system will not always achieve. Both rates are added once.

**Nothing here is a constant.** No fee, no tier threshold, no spread. They arrive
through `state["exchange"]`, published by engine 1 from the live client. `hurdle_multiple`
is the single configured input, and it is a multiplier on measured friction rather than a
percentage of its own — `glossary.md`: "Hurdle — the minimum net edge a candidate must
show before it is allowed to trade. Derived from friction, never a constant."

**At tier 1 this gate is unreachable, by construction, and that is not a bug.** With
`hurdle_multiple: 1.5`, `net_edge > 1.5 x friction` rearranges to
`expected_move > 2.5 x friction`; tier 1 friction is around 1.25% round trip, so a
candidate needs an expected move above roughly 3.125% while the target barrier is 3.0%.
The system is designed to report honestly that no edge survives tier 1 fees at a fresh
account. Any pass test written against this engine therefore has to use a better tier,
which is the same lever the "the fee is fetched, not constant" test pulls.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.cost.contracts import (
    CANDIDATE_PAIR_PATH,
    EXCHANGE_FAILED_FETCHES_KEY,
    EXCHANGE_FEE_TIER_KEY,
    EXCHANGE_KEY,
    FEE_MAKER_FIELD,
    FEE_TAKER_FIELD,
    FEE_TIER_CALL,
    MARKET_SENSOR_KEY,
    MARKET_SENSOR_QUOTES_KEY,
    ORDER_BOOK_KEY,
    PREDICTION_KEY,
    REASON_INPUTS_UNAVAILABLE,
    REASON_NET_EDGE_BELOW_HURDLE,
    REASON_SPREAD_WIDER_THAN_MOVE,
    CostAssessment,
    CostInputs,
    format_signed_pct,
)

HURDLE_MULTIPLE_KEY = "trading.hurdle_multiple"


class MissingInputError(Exception):
    """An input this gate needs is absent, null, or the wrong shape.

    Carried as an exception rather than as a sentinel return so that the one place that
    turns a missing input into a block is the one place that formats its reason. Invariant
    3: a gate that cannot reach its data blocks.
    """


def _require(container: Any, key: str, where: str) -> Any:
    """Fetch `key` out of a published mapping, or say precisely what was missing.

    A `None` is treated exactly like an absent key. That is the whole fail-closed
    posture in one line: engine 1 publishing `spread_pct: null` because the order book
    fetch failed must not be read as a spread of zero, which would be the most
    optimistic possible reading of a failure.
    """
    if not isinstance(container, dict):
        raise MissingInputError(f"{where} is {type(container).__name__}, expected a mapping")
    if key not in container or container[key] is None:
        raise MissingInputError(f"{where}.{key}")
    return container[key]


class CostEngine(BaseEngine):
    """Gate 10. Opportunity chain, runtime stage 3."""

    name = "cost"
    number = 10
    is_gate = True

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        try:
            inputs = self._read_inputs(state)
            hurdle_multiple = self._read_hurdle_multiple(context)
        except MissingInputError as missing:
            return self._blocked_on_missing_input(str(missing), state, started)

        friction = (
            inputs.maker_fee_pct + inputs.taker_fee_pct + inputs.spread_pct + inputs.slippage_pct
        )
        net_edge = inputs.expected_move_pct - friction
        hurdle = hurdle_multiple * friction

        # Invariant 5's third line, and the only comparison in this file. Strictly
        # greater than: a candidate that exactly equals the hurdle has not beaten it,
        # and "with margin to spare" is the project's stated posture.
        clears = net_edge > hurdle

        assessment = CostAssessment(
            pair=inputs.pair,
            expected_move_pct=inputs.expected_move_pct,
            friction_pct=friction,
            net_edge_pct=net_edge,
            hurdle_pct=hurdle,
            clears_hurdle=clears,
            reason_code=None if clears else self._reason_code(inputs),
            fallbacks_used=self._fallbacks(),
        )
        duration_ms = (time.perf_counter() - started) * 1000.0

        if clears:
            return EngineResult(
                engine=self.name,
                status=EngineStatus.OK,
                blocks_trading=False,
                data=assessment.to_state_data(),
                duration_ms=duration_ms,
            )

        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=self._operator_reason(assessment, inputs),
            data=assessment.to_state_data(),
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------ inputs

    def _read_inputs(self, state: State) -> CostInputs:
        """Gather the six numbers invariant 5 needs, from four publishers.

        Everything is pulled through :func:`_require` first so that an absent value is
        reported by name, then handed to pydantic, which does the string-to-`Decimal`
        parse and refuses a `float`. Doing it in that order matters: pydantic alone
        would report "field required", and "which of six inputs was missing, from which
        engine" is the thing an operator actually needs at 3am.
        """
        candidate_key, pair_field = CANDIDATE_PAIR_PATH
        pair = _require(state.get(candidate_key), pair_field, candidate_key)

        exchange = state.get(EXCHANGE_KEY)
        fees = _require(exchange, EXCHANGE_FEE_TIER_KEY, EXCHANGE_KEY)

        # Spread comes from engine 3, not engine 1: `market_sensor` is the market-data
        # engine and `exchange` is the account engine, and `data_guard` needs every
        # market-data fault to arrive from one publisher.
        quotes = _require(
            state.get(MARKET_SENSOR_KEY), MARKET_SENSOR_QUOTES_KEY, MARKET_SENSOR_KEY
        )
        quote_where = f"{MARKET_SENSOR_KEY}.{MARKET_SENSOR_QUOTES_KEY}"
        pair_quote = _require(quotes, str(pair), quote_where)

        raw: dict[str, Any] = {
            "pair": pair,
            "expected_move_pct": _require(
                state.get(PREDICTION_KEY), "expected_move_pct", PREDICTION_KEY
            ),
            "maker_fee_pct": _require(
                fees, FEE_MAKER_FIELD, f"{EXCHANGE_KEY}.{EXCHANGE_FEE_TIER_KEY}"
            ),
            "taker_fee_pct": _require(
                fees, FEE_TAKER_FIELD, f"{EXCHANGE_KEY}.{EXCHANGE_FEE_TIER_KEY}"
            ),
            "spread_pct": _require(pair_quote, "spread_pct", f"{quote_where}.{pair}"),
            "slippage_pct": _require(
                state.get(ORDER_BOOK_KEY), "estimated_slippage_pct", ORDER_BOOK_KEY
            ),
        }
        try:
            return CostInputs.model_validate(raw)
        except ValidationError as exc:
            # A float in a fee, a malformed decimal string, or a non-numeric value. All
            # three are "cannot reach usable data", which invariant 3 makes a block. The
            # float case is the one worth naming: it passes the orchestrator's
            # JSON-serialisable check and would otherwise reach the hurdle comparison
            # having already lost precision.
            raise MissingInputError(f"unusable cost input: {exc}") from exc

    def _read_hurdle_multiple(self, context: EngineContext) -> Decimal:
        """`trading.hurdle_multiple`, as a `Decimal`.

        `Config.get` raises on an absent key by contract, and a present-but-null key
        returns `None` — the OPERATOR REQUIRED state. Both are a gate that cannot reach
        its configuration, so both block rather than defaulting to something plausible.
        A default here would be a number silently deciding how much money is at risk.
        """
        value = context.config.get(HURDLE_MULTIPLE_KEY)
        if value is None:
            raise MissingInputError(f"config {HURDLE_MULTIPLE_KEY} is null (OPERATOR REQUIRED)")
        if isinstance(value, float):
            # The config loader parses YAML, and `hurdle_multiple: 1.5` is a float there.
            # `Decimal(1.5)` is 1.5 exactly, but `Decimal(0.1)` is not 0.1, so the only
            # safe conversion from a YAML number is through its shortest repr.
            value = repr(value)
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise MissingInputError(f"config {HURDLE_MULTIPLE_KEY} is not a number: {value!r}") from exc

    def _fallbacks(self) -> tuple[str, ...]:
        """The fallbacks **this engine applied**. There are none, and that is the point.

        Invariant 2: "Every decision affected by a fallback records which fallback
        fired", and `CostAssessment.fallbacks_used` is where this engine would record
        it. It is a payload field, not a `rejections` column: `fallbacks_used` is a
        `trades` column (migration 0001), and nothing in `src/` reads this one.

        Spec 37 retired the fee-tier row of the paper-mode table on 2026-09-10 —
        `AssetPairs` carries no fee schedule, so there was no runtime source
        the named tier could have come from, and the only way to honour that row was to
        write a fee percentage into the code. A confirmed pair with no fee data now
        blocks, in every mode, and this gate has no fallback left to apply.

        It used to read `state["exchange"]["fallbacks_used"]`, which **engine 1 does not
        publish and never did**, so it returned an empty tuple on every tick regardless.
        The dead read is deleted rather than re-pointed at `failed_fetches`: a failed
        fetch is not a fallback, and putting one in this column would misreport exactly
        the thing invariant 2 asks to be recorded.
        """
        return ()

    # ------------------------------------------------------------------ reasons

    def _reason_code(self, inputs: CostInputs) -> str:
        """The more specific code wins.

        A spread wider than the whole expected move is already a guaranteed failure of
        the hurdle, so the two are not independent — but "the spread is wider than the
        move" tells an operator that the market is the problem, while "net edge below
        hurdle" suggests the candidate is. C's `REASON_PROSE` carries both, so both are
        worth distinguishing.
        """
        if inputs.spread_pct > inputs.expected_move_pct:
            return REASON_SPREAD_WIDER_THAN_MOVE
        return REASON_NET_EDGE_BELOW_HURDLE

    def _operator_reason(self, assessment: CostAssessment, inputs: CostInputs) -> str:
        """Prose with the actual number in it, per `ui-context.md`.

        "Net edge -0.21% after fees" beats `cost_gate_fail`, and it beats the generic
        sentence keyed on the code too: `console/format.py`'s `operator_reason` prefers
        a stored reason that is already prose precisely because no mapping keyed on a
        code can ever carry the number.
        """
        if assessment.reason_code == REASON_SPREAD_WIDER_THAN_MOVE:
            return (
                f"Spread {format_signed_pct(inputs.spread_pct)} is wider than the "
                f"expected move {format_signed_pct(inputs.expected_move_pct)}"
            )
        return (
            f"Net edge {format_signed_pct(assessment.net_edge_pct)} after fees, "
            f"below the {format_signed_pct(assessment.hurdle_pct)} hurdle "
            f"on {format_signed_pct(assessment.friction_pct)} friction"
        )

    def _failed_fetch_reason(self, state: State, call: str) -> str | None:
        """Why engine 1 says `call` did not answer this tick, or `None` if it did.

        `failed_fetches` is a list of `{call, kind, reason}`. It is **not** a fallback
        record — see the module docstring of `contracts.py` — and it is read here for one
        purpose only: so the operator sentence can name the call rather than the state
        key.
        """
        exchange = state.get(EXCHANGE_KEY)
        if not isinstance(exchange, dict):
            return None
        failures = exchange.get(EXCHANGE_FAILED_FETCHES_KEY)
        if not isinstance(failures, (list, tuple)):
            return None
        for failure in failures:
            if isinstance(failure, dict) and failure.get("call") == call:
                kind = failure.get("kind")
                reason = failure.get("reason")
                return f"{kind}: {reason}" if kind else str(reason)
        return None

    def _blocked_on_missing_input(
        self, detail: str, state: State, started: float
    ) -> EngineResult:
        """Fail closed, naming what was missing.

        `data` is deliberately empty rather than a half-filled assessment: publishing
        three of four economics figures would put numbers into `rejections` that were
        never used to decide anything, and a partially populated row is worse research
        data than an absent one.

        **When the fee tier is the missing thing, the sentence names the call, not the
        key.** "missing exchange.fee_tier" is true and sends the operator to look at
        `state`, where they will find a `None` that tells them nothing. The useful
        sentence is the one that says `trade_volume` failed and why, because that is
        where the problem is and it is the only thing they can act on.
        """
        reason = f"Cost gate could not price this candidate: missing {detail}"
        if detail.startswith(f"{EXCHANGE_KEY}.{EXCHANGE_FEE_TIER_KEY}"):
            failure = self._failed_fetch_reason(state, FEE_TIER_CALL)
            if failure is not None:
                reason = (
                    f"Cost gate could not price this candidate: {FEE_TIER_CALL} failed "
                    f"({failure}), so there is no fee for this pair"
                )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=reason,
            data={"reason_code": REASON_INPUTS_UNAVAILABLE, "clears_hurdle": False},
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


__all__ = ["CostEngine", "MissingInputError"]
