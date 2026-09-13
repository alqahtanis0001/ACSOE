"""What engine 13 `anomaly` reads out of ``state``, and what it publishes back into it.

**Every key name this engine reads lives here and nowhere else**, with the engine that owns
it written beside it. Contract rule 3 forbids importing another engine to find out what its
keys are called.

Engine 13 is a **data-quality gate**: it asks whether the candidate's market is broken, not
whether the trade is good. That is why nothing in this module names `state["prediction"]`.
The absence is structural rather than a matter of care — an engine cannot read a key it has
no name for, and a gate that could see the prediction would be a gate with an opinion about
the trade, which invariant 4 forbids.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "FEATURE_BAR_TS_FIELD",
    "FEATURE_KEY",
    "FEATURE_PAIRS_FIELD",
    "KEY_ANOMALY_RUN_ID",
    "REASON_INPUTS_INCOMPLETE",
    "REASON_MARKET_ANOMALOUS",
    "REASON_UNAVAILABLE",
    "SCOUT_CANDIDATE_FIELD",
    "SCOUT_KEY",
    "STATE_KEY",
    "AnomalyState",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "anomaly"

# --------------------------------------------------------------------------- #
# Read from engine 7 `scout` (agent B) and engine 5 `feature` (agent C)
# --------------------------------------------------------------------------- #

SCOUT_KEY: Final = "scout"
SCOUT_CANDIDATE_FIELD: Final = "pair"

FEATURE_KEY: Final = "feature"
FEATURE_PAIRS_FIELD: Final = "pairs"
FEATURE_BAR_TS_FIELD: Final = "bar_ts"

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

#: The active anomaly detector. **Optional on the config model and absent from
#: `config/default.yaml`.** Absent, the gate blocks: a data-quality gate that cannot tell a
#: broken market from an ordinary one has no basis for letting anything through.
KEY_ANOMALY_RUN_ID: Final = "models.anomaly_run_id"

# --------------------------------------------------------------------------- #
# Reason codes, enumerated by tests/console/test_reason_prose.py
# --------------------------------------------------------------------------- #

#: No run id, no directory, a failed hash, or an artefact whose manifest records no
#: threshold — which is what a run trained while `anomaly.threshold_percentile` was absent
#: produces, and that key is the operator's.
REASON_UNAVAILABLE: Final = "anomaly_unavailable"

#: A market-quality feature arrived null, NaN or infinite.
REASON_INPUTS_INCOMPLETE: Final = "anomaly_inputs_incomplete"

#: The detector scored this bar above the artefact's threshold. **The market is broken, not
#: the trade bad** — this gate has no opinion about the trade and could not form one, since
#: nothing it reads says anything about the prediction.
REASON_MARKET_ANOMALOUS: Final = "market_anomalous"


class AnomalyState(BaseModel):
    """What engine 13 publishes into ``state["anomaly"]``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    bar_ts: int
    model_run_id: str | None = None
    score: float | None = None
    threshold: float | None = None
    anomalous: bool = False
    reason_code: str | None = None

    def to_state(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
