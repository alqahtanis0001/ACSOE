"""Engine 6 `macro_context` — the market-wide backdrop every candidate is judged against.

A candidate's own features say what that pair is doing. They say nothing about whether
the whole market is doing it, and a 2% move while Bitcoin is up 3% is a different event
from the same move while Bitcoin is flat. Engine 6 selects BTC's and ETH's feature rows
out of `state["feature"]`, renames them with a `macro_` prefix, and publishes them for
engines 8, 12 and 15 to read alongside the candidate's own row.

**It selects and renames. It computes nothing.** The rows are engine 5's, which are
`modelling.features.compute`'s, which is what `research/training.py` calls — so a macro
column in the training set and the same column live are the same arithmetic over the same
pair, differing only in whether the candles came from the stream or the archive.

**Two spellings of one pair, both from config.** Kraken calls the same market `BTC/USD`
on the live stream and `XBTUSD` in the downloadable archive. Neither is derivable from
the other, so both are named in `config/default.yaml` under `macro`, and this engine
reads the live one while spec 67's dataset builder reads the archive one. A hardcoded
either would work in exactly one of the two modes the same code has to run in.

**It does not block and it does not substitute.** A missing macro pair is published as
`available: false` with the asset named and its columns `null`. What to do about a
missing context is a judgement for the engines that read it — engine 8 will find its
feature vector incomplete and block on that, naming the features. Substituting the
previous bar's macro row would be worse than either: it is stale data presented as
current, on the one input that says whether the whole market moved.
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
from acsoe.engines.macro_context.contracts import (
    FEATURE_BAR_TS_FIELD,
    FEATURE_KEY,
    FEATURE_PAIRS_FIELD,
    KEY_MACRO,
    STATE_KEY,
    MacroContextState,
    macro_column,
    macro_pair_names,
)
from acsoe.modelling.features import FEATURE_NAMES


class MacroContextEngine(BaseEngine):
    """Engine 6. Opportunity chain, after engine 5. Not a gate."""

    name: ClassVar[str] = STATE_KEY
    number: ClassVar[int] = 6
    is_gate: ClassVar[bool] = False

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        features = state.get(FEATURE_KEY) or {}
        bar_ts = features.get(FEATURE_BAR_TS_FIELD)
        if bar_ts is None:
            # Engine 5 returned PASS, so no decision bar closed and the chain has
            # already stopped. Reaching here at all means the chain was driven by
            # something other than the orchestrator; PASS is the honest answer and
            # matches engine 5's own.
            return EngineResult(
                engine=self.name,
                status=EngineStatus.PASS,
                data={},
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        # No default. A missing `macro` section raises, the orchestrator turns it into
        # ERROR, and ERROR blocks — the right answer for a pair name nobody has set,
        # because the alternative is guessing at Kraken's spelling.
        configured = context.config.get(KEY_MACRO)
        if not isinstance(configured, Mapping) or not configured:
            raise ValueError(
                f"`{KEY_MACRO}` is empty or is not a mapping of asset to pair names. "
                "Engine 6 has nothing to select and the predictor's feature list would "
                "silently lose every macro column."
            )
        live_pairs = macro_pair_names(configured, spelling="live")

        rows = features.get(FEATURE_PAIRS_FIELD) or {}
        assets = sorted(live_pairs)
        missing: list[str] = []
        values: dict[str, float | None] = {}

        for asset in assets:
            row = rows.get(live_pairs[asset])
            if not isinstance(row, Mapping):
                missing.append(asset)
                # Published as null, not absent and not zero. Absent would make a
                # downstream feature-order check complain about the shape rather than
                # about the data; zero is a number a model learns from and cannot tell
                # from a genuinely flat market.
                values.update({macro_column(asset, name): None for name in FEATURE_NAMES})
                continue
            for name in FEATURE_NAMES:
                values[macro_column(asset, name)] = _as_float_or_none(row.get(name))

        payload = MacroContextState(
            bar_ts=int(bar_ts),
            available=not missing,
            missing=tuple(missing),
            assets=tuple(assets),
            pairs=live_pairs,
            features=values,
        )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            data=payload.to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


def _as_float_or_none(value: Any) -> float | None:
    """Engine 5 already publishes floats and `null`; this is the belt and braces.

    It exists because engine 6's output is read by engine 8 as *model input*, and a NaN
    arriving there compares False against every threshold — so a value that slipped
    through would not raise, it would quietly mean "not unusual" in the DI and "no edge"
    in the expected move.
    """
    if value is None:
        return None
    number = float(value)
    return None if number != number or number in (float("inf"), float("-inf")) else number
