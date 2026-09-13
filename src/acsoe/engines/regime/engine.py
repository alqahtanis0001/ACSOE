"""Engine 12 `regime` — what kind of market the candidate is in.

Three labels: `trending`, `choppy`, `high_volatility`. Rule-based in Phase 5; the HMM in
the stack table is an optional upgrade and spec 66 puts it explicitly out of scope.

**The volatility rule is percentile-relative to the pair's own trailing window, and it
could not be otherwise here.** An absolute volatility cutoff would classify a $0.30 pair
and a $60,000 one by the same number, and would mean something different in 2018 than in
2024. So the comparison is against `vol_regime_rank` — where this bar's short-window
realised volatility sits inside the long window's own distribution, measured in
`modelling/features.py` — and the configured `regime.high_vol_percentile` is a position
in that distribution rather than a quantity of percent. Engine 12 is handed **one feature
row** and therefore has no distribution of its own, which is the structural reason an
absolute threshold cannot creep back in.

**The trend rule is an absolute cutoff and that is legitimate**, because the efficiency
ratio is already scale-free: net move over path length is 1.0 for a straight line and 0.0
for a round trip that went nowhere, on any pair at any price.

**It is not a gate and it never blocks.** No regime is a reason to refuse a trade; that
is the router's business in Phase 6. An unclassifiable candidate gets `label: null` with
a reason, never a default label — calling an unknown market `choppy` would be a judgement
nobody made, and Phase 6's router would weight a model by it.

**It does not read the DI.** `di_regime_shift` is published as `null`; the reasoning is in
`contracts.py` and the README, and the short of it is that engine 12 runs before engine 8
and nothing persists the previous bar's DI. Reading the store to find one would be an
engine inventing its own persistence for a cross-chain key.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, ClassVar

from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.regime.contracts import (
    EFFICIENCY_FEATURE,
    FEATURE_BAR_TS_FIELD,
    FEATURE_KEY,
    FEATURE_PAIRS_FIELD,
    KEY_HIGH_VOL_PERCENTILE,
    KEY_TREND_EFFICIENCY,
    REASON_NO_FEATURE_ROW,
    REASON_NO_INPUTS,
    REPORTED_INPUTS,
    SCOUT_CANDIDATE_FIELD,
    SCOUT_KEY,
    STATE_KEY,
    VOL_RANK_FEATURE,
    RegimeLabel,
    RegimeState,
)


class RegimeEngine(BaseEngine):
    """Engine 12. Opportunity chain, before engine 13. Not a gate."""

    name: ClassVar[str] = STATE_KEY
    number: ClassVar[int] = 12
    is_gate: ClassVar[bool] = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        scout = state.get(SCOUT_KEY) or {}
        pair = scout.get(SCOUT_CANDIDATE_FIELD)
        if not pair:
            # No candidate qualified this tick. Engine 7 already returned PASS and the
            # chain stopped; reaching here means something other than the orchestrator
            # drove it, and PASS is the honest answer either way.
            return EngineResult(
                engine=self.name,
                status=EngineStatus.PASS,
                data={},
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        features = state.get(FEATURE_KEY) or {}
        bar_ts = int(features.get(FEATURE_BAR_TS_FIELD) or 0)
        row = (features.get(FEATURE_PAIRS_FIELD) or {}).get(pair)

        high_vol_percentile = float(context.config.get(KEY_HIGH_VOL_PERCENTILE))
        trend_efficiency = float(context.config.get(KEY_TREND_EFFICIENCY))
        thresholds = {
            KEY_HIGH_VOL_PERCENTILE: high_vol_percentile,
            KEY_TREND_EFFICIENCY: trend_efficiency,
        }

        if not isinstance(row, Mapping):
            return self._published(
                started,
                RegimeState(
                    pair=str(pair),
                    bar_ts=bar_ts,
                    label=None,
                    reason=REASON_NO_FEATURE_ROW,
                    thresholds=thresholds,
                ),
            )

        inputs = {name: _as_float_or_none(row.get(name)) for name in REPORTED_INPUTS}
        vol_rank = inputs.get(VOL_RANK_FEATURE)
        efficiency = inputs.get(EFFICIENCY_FEATURE)

        if vol_rank is None or efficiency is None:
            # A pair whose longest lookback is unfilled. Reported, never guessed: this is
            # the same pair engine 5 listed in `pairs_with_short_history`, and a label
            # invented for it would be indistinguishable downstream from a measured one.
            return self._published(
                started,
                RegimeState(
                    pair=str(pair),
                    bar_ts=bar_ts,
                    label=None,
                    reason=REASON_NO_INPUTS,
                    inputs=inputs,
                    thresholds=thresholds,
                ),
            )

        label: RegimeLabel
        if vol_rank >= high_vol_percentile:
            label = "high_volatility"
        elif efficiency > trend_efficiency:
            label = "trending"
        else:
            label = "choppy"

        return self._published(
            started,
            RegimeState(
                pair=str(pair),
                bar_ts=bar_ts,
                label=label,
                inputs=inputs,
                thresholds=thresholds,
            ),
        )

    def _published(self, started: float, payload: RegimeState) -> EngineResult:
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            data=payload.to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


def _as_float_or_none(value: Any) -> float | None:
    """A feature value, with NaN and infinity read as absent.

    A NaN compares False against every threshold, so an unfilled input reaching the rules
    would not raise — it would fall through to `choppy`, which is a label nobody measured
    arriving through the branch that looks like a default.
    """
    if value is None:
        return None
    number = float(value)
    return None if number != number or number in (float("inf"), float("-inf")) else number
