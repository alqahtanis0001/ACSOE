"""What engine 12 `regime` reads out of ``state``, and what it publishes back.

Every key it reads is named here with the owning engine beside it, per contract rule 3.

The three labels are a closed set. `trending`, `choppy` and `high_volatility` are what
`engine-contracts.md` fixes for `state["regime"]["label"]`, plus `null` with a reason when
there is no feature row to classify. A fourth label is a change to a cross-chain key and
belongs to the lead.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

from acsoe.modelling.features import REGIME_LONG_BARS, REGIME_SHORT_BARS

__all__ = [
    "EFFICIENCY_FEATURE",
    "FEATURE_BAR_TS_FIELD",
    "FEATURE_KEY",
    "FEATURE_PAIRS_FIELD",
    "KEY_HIGH_VOL_PERCENTILE",
    "KEY_TREND_EFFICIENCY",
    "REASON_NO_FEATURE_ROW",
    "REASON_NO_INPUTS",
    "REGIME_LABELS",
    "SCOUT_CANDIDATE_FIELD",
    "SCOUT_KEY",
    "STATE_KEY",
    "VOL_RANK_FEATURE",
    "RegimeLabel",
    "RegimeState",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "regime"

# --------------------------------------------------------------------------- #
# Read from engine 7 `scout` (agent B) and engine 5 `feature` (agent C)
# --------------------------------------------------------------------------- #

SCOUT_KEY: Final = "scout"
SCOUT_CANDIDATE_FIELD: Final = "pair"

FEATURE_KEY: Final = "feature"
FEATURE_PAIRS_FIELD: Final = "pairs"
FEATURE_BAR_TS_FIELD: Final = "bar_ts"

# --------------------------------------------------------------------------- #
# The two features the rules read
# --------------------------------------------------------------------------- #

#: Where this bar's short-window realised volatility sits inside the long window's own
#: distribution, 0 to 1. **This is why the rule is percentile-relative and not absolute**:
#: engine 12 is handed one feature row and therefore has no distribution of its own to
#: compute a cutoff from, so the only number it can compare against
#: `regime.high_vol_percentile` is a position that `modelling/features.py` already
#: measured against the pair's own history.
VOL_RANK_FEATURE: Final = "vol_regime_rank"

#: Net move over path length across the long window: 1.0 is a straight line, 0.0 is a
#: round trip that went nowhere. Scale-free, so the same cutoff means the same thing on a
#: $0.30 pair and a $60,000 one — which is what makes an absolute threshold legitimate
#: here and not for volatility.
EFFICIENCY_FEATURE: Final = f"efficiency_ratio_{REGIME_LONG_BARS}"

#: Reported in `inputs` so a label can be read without recomputing anything.
_SHORT_VOL_FEATURE: Final = f"realised_vol_{REGIME_SHORT_BARS}"
_LONG_VOL_FEATURE: Final = f"realised_vol_{REGIME_LONG_BARS}"
REPORTED_INPUTS: Final[tuple[str, ...]] = (
    VOL_RANK_FEATURE,
    EFFICIENCY_FEATURE,
    _SHORT_VOL_FEATURE,
    _LONG_VOL_FEATURE,
)

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

#: Both are plumbing the lead chose and both are flagged provisional: no gate reads the
#: label and no order is sized from it. They are still config rather than constants,
#: because a number that decides how a market is described belongs where it can be seen.
KEY_HIGH_VOL_PERCENTILE: Final = "regime.high_vol_percentile"
KEY_TREND_EFFICIENCY: Final = "regime.trend_efficiency"

# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

RegimeLabel = Literal["trending", "choppy", "high_volatility"]

#: The closed set, in the order the rules are applied.
REGIME_LABELS: Final[tuple[str, ...]] = ("high_volatility", "trending", "choppy")

REASON_NO_FEATURE_ROW: Final = "no_feature_row"
REASON_NO_INPUTS: Final = "regime_inputs_incomplete"


class RegimeState(BaseModel):
    """The whole of ``state["regime"]``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    bar_ts: int

    label: RegimeLabel | None
    """`null` with a `reason` when the candidate has no feature row, or when the two
    inputs the rules read are unfilled. **Not a default label.** Calling an unclassifiable
    market `choppy` would be a judgement nobody made, and Phase 6's router would weight a
    model by it."""

    reason: str | None = None

    inputs: dict[str, float | None] = {}
    """The feature values the label was decided from, echoed so a label is readable
    without the feature row beside it."""

    thresholds: dict[str, float] = {}
    """The two cutoffs applied, echoed for the same reason."""

    di_regime_shift: None = None
    """**A declared placeholder, and the null is the point.**

    A Locked Decision says DI threshold crossings also feed the regime engine. They
    cannot yet: engine 12 runs *before* engine 8 in the registry order, so this tick's DI
    does not exist when this engine runs, and ``state`` is fresh every tick so last bar's
    DI is not there either. Nothing persists it.

    Publishing the field as `null` rather than omitting it is deliberate — an absent key
    reads as an oversight, a null with this docstring reads as a decision. Where a
    previous bar's DI would live is a schema question, B's edit and the lead's approval,
    and it is an open question for the operator. **This engine does not read the store to
    answer it**, because an engine inventing its own persistence is how a cross-chain key
    ends up with two meanings.
    """

    def to_state(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
