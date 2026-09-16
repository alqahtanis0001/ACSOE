"""Engine 16 `decision` — the check nothing else performs, and the intent engine 18 reads.

## What it decides, which is one thing

**Every approving engine judged *this* tick's candidate.** By the time engine 16 runs,
four gates have already said yes — 7 `scout`, 10 `cost`, 11 `risk`, 15 `skeptic` — so
"combine their verdicts" was never a job worth an engine. What nothing in the system did
until spec 90 was ask whether they were all answering the *same question*. If engine 7
picked SOL/USD and engine 10 approved BTC/USD, or a `state` key survived from a previous
bar, every gate is individually correct and the order that results is not the order any
of them approved.

That is deterministic arithmetic, it fails closed, and it can only ever make the system
less willing to trade — which is why the operator made it a gate on 2026-09-16 and why
invariant 4 protects it. There is no model in it.

## What it does *not* decide

Everything else. It **composes** the order intent and it re-derives nothing: the pair is
engine 7's, the quantity engine 11's, the edge and hurdle engine 10's, the model engine
8's. Disagreement is a block, never a correction — a quantity adjusted here would be a
veto wearing a sizing costume, and a number recomputed here would be a second opinion
that diverges from the first on exactly the ticks that matter.

Nothing here mints a `userref` either. That is engine 18's, deterministic from the pair
and the bar.

## Why the clauses are a walk and not four comparisons

`_coherence` iterates `CHECKED_SOURCES` and asks each payload whether it names a pair or
a bar, rather than naming the four comparisons that exist today. Engines 9 `order_book`
and 14 `adaptive_router` are not built yet; when they land, whatever they publish is
checked with no edit here. A hand-written list of comparisons is written by the same
person who forgot the one that matters — the argument that produced the `drain_gaps`
protocol walk in `clients/paper/` on the same day.

## Where the fail-closed edges are

Invariant 3, "the absence of a no is never a yes", lands in three places:

* a clause that **cannot be evaluated** blocks, rather than being skipped;
* a payload the chain says ran but which is **absent** blocks (`input_missing`), because
  the opportunity chain stops at the first block or `PASS`, so engine 16 running at all
  means every engine before it ran;
* the intent is **absent in its entirety** on every block, so there is no half-intent for
  engine 18 to read. `state["decision"]["intent"]` either exists and is complete or does
  not exist.

The one deliberate asymmetry is provenance from engines 9 and 14: copied when present,
omitted when absent, never blocked on. The reasoning is on `OPTIONAL_SOURCES` in
`contracts.py`, and it is not a softening — engine 10 already refuses the tick when the
slippage is missing, so the absence is caught by a gate either way.
"""

from __future__ import annotations

import time
from typing import Any, NamedTuple

from pydantic import ValidationError

from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.decision.contracts import (
    BAR_FIELDS,
    CHECKED_SOURCES,
    CLOSED_BAR_TS_FIELD,
    CYCLE_ID_KEY,
    MARKET_SENSOR_KEY,
    PAIR_FIELD,
    REASON_INPUT_MISSING,
    REASON_INPUTS_UNAVAILABLE,
    REASON_NO_APPROVED_QUANTITY,
    REASON_PAIR_DISAGREEMENT,
    REASON_STALE_BAR,
    REQUIRED_SOURCES,
    RISK_APPROVED_FIELD,
    RISK_KEY,
    RISK_QTY_FIELD,
    SCOUT_KEY,
    DecisionState,
    OrderIntent,
)


class IncoherentError(Exception):
    """A clause failed, or could not be evaluated.

    Carried as an exception rather than a sentinel so that the one place which turns an
    incoherent tick into a block is the one place that formats its sentence, exactly as
    engine 10's `MissingInputError` does. `code` is what the `rejections` row carries;
    the message is what the operator reads.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _Verdict(NamedTuple):
    """The coherence answer, plus which payloads were actually examined."""

    checked: tuple[str, ...]


def _payload(state: State, key: str) -> dict[str, Any] | None:
    """The payload under `key`, or None when it is absent or not a mapping.

    A non-mapping is treated as absent rather than raising here, so the caller decides
    whether this source was required. An engine that published a list where a mapping
    belongs has not published a payload engine 16 can read either way.
    """
    value = state.get(key)
    return value if isinstance(value, dict) else None


class DecisionEngine(BaseEngine):
    """Gate 16. Opportunity chain, runtime stage 3, after 15 and before 18."""

    name = "decision"
    number = 16
    is_gate = True

    def process(self, context: EngineContext, state: State) -> EngineResult:
        # **Nothing is read from `context`.** No client, no clock, no config key —
        # engine 16 is arithmetic over what the engines before it published, and that
        # is why it is deterministic enough to be a gate invariant 4 protects. If a
        # config threshold ever appears here, it has stopped being a coherence check.
        _ = context
        started = time.perf_counter()
        checked: tuple[str, ...] = ()

        try:
            pair = self._candidate_pair(state)
            bar_ts = self._closed_bar_ts(state)
            checked = self._coherence(state, pair=pair, bar_ts=bar_ts).checked
            qty = self._approved_quantity(state)
            intent = self._compose(
                state, pair=pair, bar_ts=bar_ts, qty=qty, cycle_id=self._cycle_id(state)
            )
        except IncoherentError as failure:
            return self._block(failure, checked, started)

        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=DecisionState(coherent=True, checked=checked, intent=intent).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _block(
        self, failure: IncoherentError, checked: tuple[str, ...], started: float
    ) -> EngineResult:
        """Every refusal, with **no intent in the payload at all**."""
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=str(failure),
            data=DecisionState(
                coherent=False, checked=checked, reason_code=failure.code
            ).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ the two anchors

    def _candidate_pair(self, state: State) -> str:
        """Engine 7's candidate — the pair every other payload is measured against.

        Engine 7 omits `pair` entirely when it chose nothing and returns `PASS`, which
        stops the chain, so an absent candidate here is the chain contradicting itself
        rather than an ordinary quiet tick.
        """
        scout = _payload(state, SCOUT_KEY)
        if scout is None:
            raise IncoherentError(
                REASON_INPUT_MISSING,
                f"{SCOUT_KEY} published nothing, but the chain reached engine 16",
            )
        pair = scout.get(PAIR_FIELD)
        if not isinstance(pair, str) or not pair:
            raise IncoherentError(
                REASON_INPUT_MISSING,
                f"{SCOUT_KEY} named no candidate pair, so there is nothing to agree about",
            )
        return pair

    def _closed_bar_ts(self, state: State) -> int:
        """This tick's decision bar, from engine 3.

        Engine 5 `feature` returns `PASS` when no bar closed, which stops the chain on
        the fourteen ticks in fifteen where none did. So a null here is not "no bar yet"
        — it is engine 16 running on a tick that had no bar to decide on.
        """
        sensor = _payload(state, MARKET_SENSOR_KEY)
        if sensor is None:
            raise IncoherentError(
                REASON_INPUT_MISSING,
                f"{MARKET_SENSOR_KEY} published nothing, so this tick has no decision bar",
            )
        bar_ts = sensor.get(CLOSED_BAR_TS_FIELD)
        if bar_ts is None:
            raise IncoherentError(
                REASON_INPUT_MISSING,
                f"{MARKET_SENSOR_KEY}.{CLOSED_BAR_TS_FIELD} is null: no bar closed on this "
                "tick, so there is nothing for the approvals to be about",
            )
        if not isinstance(bar_ts, int) or isinstance(bar_ts, bool):
            raise IncoherentError(
                REASON_INPUTS_UNAVAILABLE,
                f"{MARKET_SENSOR_KEY}.{CLOSED_BAR_TS_FIELD} is {bar_ts!r}, not a timestamp",
            )
        return bar_ts

    # ------------------------------------------------------------------ the walk

    def _coherence(self, state: State, *, pair: str, bar_ts: int) -> _Verdict:
        """Every payload names this pair and this bar, or the tick is refused.

        A walk rather than a list of comparisons, so a payload that starts carrying a
        `pair` is checked the day it does. `checked` records what was actually examined,
        which is what distinguishes "everything agreed" from "there was nothing to
        disagree with".
        """
        checked: list[str] = []
        for source in CHECKED_SOURCES:
            payload = _payload(state, source)
            if payload is None:
                if source in REQUIRED_SOURCES:
                    raise IncoherentError(
                        REASON_INPUT_MISSING,
                        f"{source} approved this candidate and published no payload, so "
                        "there is no way to tell whether it judged this tick",
                    )
                continue
            checked.append(source)
            self._same_pair(source, payload, pair)
            self._same_bar(source, payload, bar_ts)
        return _Verdict(checked=tuple(checked))

    @staticmethod
    def _same_pair(source: str, payload: dict[str, Any], pair: str) -> None:
        """A payload that names a pair names the candidate's.

        A payload that names none is not checked and is not a failure: engines 14
        `adaptive_router` and 15 `skeptic` need not restate it. Only a *disagreement* is
        a disagreement.
        """
        named = payload.get(PAIR_FIELD)
        if named is None:
            return
        if named != pair:
            raise IncoherentError(
                REASON_PAIR_DISAGREEMENT,
                f"{SCOUT_KEY} chose {pair} and {source} judged {named!r}: the approvals "
                "are not about the same candidate",
            )

    @staticmethod
    def _same_bar(source: str, payload: dict[str, Any], bar_ts: int) -> None:
        """A payload that names a decision bar names this tick's.

        Both spellings are checked. `bar_ts` travels 3 -> 5 -> 8 unchanged, so a payload
        carrying a different one was computed on a bar that has already closed and been
        superseded — which every engine downstream would read as current.
        """
        for field in BAR_FIELDS:
            named = payload.get(field)
            if named is None:
                continue
            if named != bar_ts:
                raise IncoherentError(
                    REASON_STALE_BAR,
                    f"{source} carries {field} {named!r} and this tick closed bar "
                    f"{bar_ts}: it judged a bar that is no longer the one being decided",
                )

    # ------------------------------------------------------------------ the quantity

    def _approved_quantity(self, state: State) -> Any:
        """Engine 11 approved, and named how much.

        Engine 11 omits `qty` from the payload of a refused candidate entirely, so an
        approval with no quantity is not a missing field — it is one payload asserting
        an approval and a refusal at once, and neither half can be trusted over the
        other.

        **Returned exactly as published, and deliberately not coerced to `str`.** The
        first version of this returned `str(qty)`, which looks harmless and is not:
        `Money` refuses a float precisely because a float has already lost precision,
        and `str(33.33)` hands it `"33.33"`, which parses cleanly. Stringify here and
        an engine 11 publishing a float would sail straight through the one validator
        in the system built to stop it. Found by
        `test_a_clause_that_cannot_be_evaluated_blocks[quantity is a float]` rather than
        by reading the line, which is the argument for writing that case at all.

        Parsing is `OrderIntent`'s job. Re-deriving is nobody's.
        """
        risk = _payload(state, RISK_KEY)
        if risk is None:  # pragma: no cover - `_coherence` refuses this first
            raise IncoherentError(REASON_INPUT_MISSING, f"{RISK_KEY} published no payload")
        if risk.get(RISK_APPROVED_FIELD) is not True:
            raise IncoherentError(
                REASON_NO_APPROVED_QUANTITY,
                f"{RISK_KEY} did not approve this candidate, but the chain reached "
                "engine 16 as though it had",
            )
        qty = risk.get(RISK_QTY_FIELD)
        if qty is None:
            raise IncoherentError(
                REASON_NO_APPROVED_QUANTITY,
                f"{RISK_KEY} approved this candidate and published no {RISK_QTY_FIELD}: "
                "an approval and a refusal inside one payload",
            )
        return qty

    @staticmethod
    def _cycle_id(state: State) -> int:
        cycle_id = state.get(CYCLE_ID_KEY)
        if not isinstance(cycle_id, int) or isinstance(cycle_id, bool):
            raise IncoherentError(
                REASON_INPUTS_UNAVAILABLE,
                f"{CYCLE_ID_KEY} is {cycle_id!r}, not a cycle number",
            )
        return cycle_id

    # ------------------------------------------------------------------ composition

    def _compose(
        self, state: State, *, pair: str, bar_ts: int, qty: Any, cycle_id: int
    ) -> OrderIntent:
        """Copy, and copy only.

        Every value below is `state`'s, verbatim. The provenance fields are taken from
        the engine whose gate decision they justify — `net_edge_pct`, `hurdle_pct` and
        `expected_move_pct` all from engine 10 rather than `expected_move_pct` from
        engine 8, so the three numbers in one comparison come from one publisher and
        cannot disagree with each other in the record.
        """
        cost = _payload(state, "cost") or {}
        prediction = _payload(state, "prediction") or {}
        skeptic = _payload(state, "skeptic") or {}
        book = _payload(state, "order_book") or {}
        router = _payload(state, "adaptive_router") or {}

        # `model_validate` rather than the constructor, the same way engine 10 builds
        # `CostInputs`: every value here arrived as a published string and pydantic is
        # what turns it into a `Decimal` and refuses a float. Calling the constructor
        # would make the *type checker* the thing insisting on a `Decimal`, which would
        # push a `Decimal(...)` cast up into this method — and a cast here is engine 16
        # doing arithmetic on a number it is supposed to be copying.
        raw: dict[str, Any] = {
            "pair": pair,
            "qty": qty,
            "closed_bar_ts": bar_ts,
            "cycle_id": cycle_id,
            "net_edge_pct": cost.get("net_edge_pct"),
            "hurdle_pct": cost.get("hurdle_pct"),
            "expected_move_pct": cost.get("expected_move_pct"),
            "estimated_slippage_pct": book.get("estimated_slippage_pct"),
            "p_wrong": skeptic.get("p_wrong"),
            "model_run_id": prediction.get("model_run_id"),
            "active_model_run_id": router.get("active_model_run_id"),
        }
        try:
            return OrderIntent.model_validate(raw)
        except ValidationError as exc:
            # A float where money belongs, a malformed decimal string, a quantity that
            # is not a number. All three are "the approvals cannot be assembled into an
            # order", which invariant 3 makes a block rather than a best effort.
            raise IncoherentError(
                REASON_INPUTS_UNAVAILABLE, f"the approvals do not compose an order: {exc}"
            ) from exc
