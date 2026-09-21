"""Engine 4 `data_guard` — the first real gate in the system.

Fourth in the guard chain, and the engine that refuses to let the loop trade on data it
does not trust. It blocks on three conditions the phase criteria name — **stale data**,
a **negative spread**, and a **missing candle** — and on the fail-closed case invariant
3 requires: **no market data at all**.

**All four are judged on the feed, never on one pair** (D10, operator ruling 2026-09-21).
Stale means the *freshest* quote is past the bound — a heartbeat; a negative spread means
*every* pair is crossed; a missing candle means *no* pair traded in the bar. A single thin
pair that is stale or crossed is excluded by engine 7 under ``no_live_quote``, and engine 16
re-checks the chosen pair before any order. Judging the tick on its oldest pair was the
defect that blocked every tick against the real exchange.

Three properties are not negotiable and there is no flag that softens any of them.

**It has no escape hatch.** `AGENTS.md`: invariants outrank tests, and a test that fails
because a gate blocked is the test that is wrong. There is no bypass parameter, no
"warn only" mode and no confidence score that can overrule it — invariant 4.

**A block here does not stop the guard chain.** `safety` still runs on the same tick and
every blocker is recorded; the orchestrator handles that, and this engine simply reports
honestly. Nor does a block stop recording: engine 2 has already run and the archive is
written regardless, because a block says the data cannot be *traded on*, not that it is
not worth keeping.

**Every threshold comes from config and none is written here.** A key that does not
exist raises, the orchestrator turns that into `ERROR`, and `ERROR` blocks — which is
the correct fail-closed answer for a threshold nobody has set, and better documentation
of the gap than a placeholder would be.
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.data_guard.contracts import (
    MAX_DATA_AGE_KEY,
    REASON_MISSING_CANDLE,
    REASON_NEGATIVE_SPREAD,
    REASON_NO_MARKET_DATA,
    REASON_STALE,
    DataGuardState,
    Finding,
)

__all__ = ["DataGuardEngine"]

#: The order findings are evaluated in, most fundamental first. The first one becomes
#: the block's `reason`; every one of them is still published in `data`, because a tick
#: can be stale *and* carry a crossed book and an operator should see both.
_ORDER = (REASON_NO_MARKET_DATA, REASON_STALE, REASON_NEGATIVE_SPREAD, REASON_MISSING_CANDLE)


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float):
        # Money crosses `state` as a string. A float here means an upstream engine
        # published one, which is a defect worth surfacing rather than parsing around.
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


class DataGuardEngine(BaseEngine):
    """Refuses to trade on market data the system does not trust."""

    name: ClassVar[str] = "data_guard"
    number: ClassVar[int] = 4
    #: The registry table in `context/engine-contracts.md` marks engine 4 **Y**, and
    #: `is_gate_matches_registry` asserts the match. This is the first real gate in the
    #: system; changing it to False silently demotes it to a reporter.
    is_gate: ClassVar[bool] = True

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        # No default, and no fallback if the key is absent. `config.get` raises, the
        # orchestrator turns it into ERROR, and ERROR blocks. A placeholder here would
        # be inventing the one number this gate exists to apply.
        max_age_s = float(context.config.get(MAX_DATA_AGE_KEY))

        sensor = state.get("market_sensor") or {}
        quotes = sensor.get("quotes") or {}
        missing_bars = tuple(sensor.get("missing_bars") or ())

        findings: list[Finding] = []
        oldest_age: float | None = None
        freshest_age: float | None = None
        fresh_pairs = 0

        if not quotes:
            findings.append(
                Finding(
                    reason_code=REASON_NO_MARKET_DATA,
                    detail=(
                        "No market data has arrived for any pair this tick"
                        + ("; the exchange stream is not connected" if not sensor.get(
                            "stream_available", False) else "")
                        + ". Trading is refused until a quote arrives."
                    ),
                )
            )
        else:
            # **Feed-wide health only** (D10, operator ruling 2026-09-21). One stale or
            # crossed pair is that pair's problem, and engine 7 excludes it under
            # `no_live_quote`; this gate judges whether the *feed* can be trusted. Judging
            # the tick on its oldest quote was the bug: with 668 real pairs some thin one
            # is always past the bound, so the guard blocked every tick. It also disobeyed
            # `REASON_STALE`'s own contract, which has always said "the *freshest* quote".
            ages: list[float] = []
            crossed = 0
            for quote in quotes.values():
                age = self._age(quote)
                if age is not None:
                    ages.append(age)
                    if age <= max_age_s:
                        fresh_pairs += 1
                spread_pct = _decimal(quote.get("spread_pct"))
                if spread_pct is not None and spread_pct < 0:
                    crossed += 1
            if ages:
                oldest_age = max(ages)
                freshest_age = min(ages)

            # The heartbeat. If even the freshest quote is past the bound, nothing on the
            # subscription has moved within it: the feed is dead or stalled, and nothing it
            # says can be traded on. A tick whose quotes carry no age at all cannot show the
            # feed is alive — engine 3 stamps `age_s` on every quote it publishes, so this
            # is a defect upstream — and the absence of a no is never a yes (invariant 3).
            if freshest_age is None or freshest_age > max_age_s:
                findings.append(
                    Finding(
                        reason_code=REASON_STALE,
                        detail=(
                            f"None of the {len(quotes)} quoted pairs carries an age, so the "
                            "feed cannot be shown to be alive"
                            if freshest_age is None
                            else f"No pair has quoted within {max_age_s:.0f}s: the freshest "
                            f"of {len(quotes)} quotes is {freshest_age:.0f}s old"
                        ),
                    )
                )
            # A crossed book on **every** quoted pair is not a market, it is a corrupt feed
            # — bid and ask swapped in a parser, say. Left to engine 7 alone it would read as
            # every pair excluded for `no_live_quote`: an empty universe, a quiet PASS, and a
            # parser defect hidden behind it. One crossed pair among many is engine 7's.
            if crossed and crossed == len(quotes):
                findings.append(
                    Finding(
                        reason_code=REASON_NEGATIVE_SPREAD,
                        detail=(
                            f"Every one of the {len(quotes)} quoted pairs has a crossed book "
                            "(bid above ask), which is a corrupt feed rather than a market"
                        ),
                    )
                )

        if missing_bars:
            findings.append(
                Finding(
                    reason_code=REASON_MISSING_CANDLE,
                    detail=(
                        f"{len(missing_bars)} decision bar(s) in the published window have "
                        f"no candle, first at {missing_bars[0]}"
                    ),
                )
            )

        ordered = sorted(findings, key=lambda finding: _ORDER.index(finding.reason_code))
        primary = ordered[0] if ordered else None

        payload = DataGuardState(
            blocked=primary is not None,
            reason_code=primary.reason_code if primary is not None else None,
            findings=tuple(finding.model_dump(mode="json") for finding in ordered),
            max_data_age_s=max_age_s,
            oldest_quote_age_s=oldest_age,
            freshest_quote_age_s=freshest_age,
            pairs_seen=len(quotes),
            fresh_pairs=fresh_pairs,
            missing_bars=len(missing_bars),
        )
        duration_ms = (time.perf_counter() - started) * 1000.0

        if primary is None:
            return EngineResult(
                engine=self.name,
                status=EngineStatus.OK,
                blocks_trading=False,
                data=payload.to_state(),
                duration_ms=duration_ms,
            )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            # The reason is the operator's sentence, not the code. The code travels in
            # `data["reason_code"]`, where the console maps it through `REASON_PROSE`.
            reason=primary.detail,
            data=payload.to_state(),
            duration_ms=duration_ms,
        )

    @staticmethod
    def _age(quote: Any) -> float | None:
        """The quote's age in seconds, or None when it does not carry one.

        A quote with no age is **not** treated as fresh. It contributes no staleness
        finding on its own, but it also cannot satisfy the check — and if no quote in
        the tick carries an age, `oldest_quote_age_s` stays null and the operator sees
        that the guard had nothing to measure.
        """
        if not isinstance(quote, dict):
            return None
        value = quote.get("age_s")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)
