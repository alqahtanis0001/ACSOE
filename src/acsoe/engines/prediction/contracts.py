"""What engine 8 `prediction` reads out of ``state``, and what it publishes back into it.

**Every key name this engine reads lives here and nowhere else**, with the engine that
owns it written beside it. Contract rule 3 forbids importing another engine to find out
what its keys are called, and a key renamed upstream without a matching change here does
not raise — engine 8 would simply block on every tick, or worse, predict from a feature
row it silently failed to find.

``state["prediction"]["expected_move_pct"]`` is a **cross-chain key**, fixed in
`context/engine-contracts.md`: engine 10 `cost` reads it and nothing else produces it. It
crosses as an **exact decimal string** because it is money-shaped and engine 10 does
`Decimal` arithmetic with it; a float crossing that boundary would be rounded twice, once
here and once there, and the two roundings would not agree. ``di`` and ``di_threshold`` are
cross-chain too, read by engine 14 in Phase 6 and by the console.

**No key here is published on a refusal.** A DI refusal and a load failure both publish a
payload with no ``expected_move_pct`` at all, because engine 10's `_require` treats an
absent key and a null identically and blocks — which is how the chain fails closed without
engine 8 having to know what engine 10 does with it.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "DI_FIELD",
    "DI_THRESHOLD_FIELD",
    "EXPECTED_MOVE_FIELD",
    "FEATURE_BAR_TS_FIELD",
    "FEATURE_INTERVAL_FIELD",
    "FEATURE_KEY",
    "FEATURE_PAIRS_FIELD",
    "FEATURE_VERSION_FIELD",
    "KEY_PREDICTION_RUN_ID",
    "MACRO_CONTEXT_KEY",
    "MACRO_FEATURES_FIELD",
    "REASON_DI_REFUSED",
    "REASON_INPUTS_INCOMPLETE",
    "REASON_UNAVAILABLE",
    "SCOUT_CANDIDATE_FIELD",
    "SCOUT_KEY",
    "SHAP_FIELD",
    "STATE_KEY",
    "PredictionState",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "prediction"

# --------------------------------------------------------------------------- #
# Read from engine 7 `scout` (agent B)
# --------------------------------------------------------------------------- #

SCOUT_KEY: Final = "scout"

#: The one candidate the opportunity chain is about this tick. Absent means nothing
#: qualified and engine 7 already returned `PASS`; engine 8 passes rather than blocking,
#: because there is nothing to refuse.
SCOUT_CANDIDATE_FIELD: Final = "pair"

# --------------------------------------------------------------------------- #
# Read from engine 5 `feature` (agent C, spec 64)
# --------------------------------------------------------------------------- #

FEATURE_KEY: Final = "feature"
FEATURE_PAIRS_FIELD: Final = "pairs"
FEATURE_BAR_TS_FIELD: Final = "bar_ts"
FEATURE_INTERVAL_FIELD: Final = "interval_s"

#: Engine 5 publishes the version it computed. Checked against the manifest's, because a
#: model trained on `f1` features scored on `f2` ones is not a degraded model — it is a
#: model reading different quantities under the same names, and every number it produces
#: would look ordinary.
FEATURE_VERSION_FIELD: Final = "feature_version"

# --------------------------------------------------------------------------- #
# Read from engine 6 `macro_context` (agent C, spec 65)
# --------------------------------------------------------------------------- #

MACRO_CONTEXT_KEY: Final = "macro_context"

#: The macro columns for this bar, keyed by the same names `modelling/macro.py` builds for
#: the offline dataset. A missing asset arrives as `null` and is treated as an incomplete
#: input rather than as a zero: engine 6 publishes the absence deliberately and reading it
#: as "no macro movement" would be the most optimistic possible reading of a gap.
MACRO_FEATURES_FIELD: Final = "features"

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

#: The active predictor run id. **Optional on the config model and absent from
#: `config/default.yaml`**, because nothing in this repository may pick which model trades.
#: Absent, the engine blocks with `prediction_unavailable`, which is invariant 3 on a fresh
#: clone with no `models/` at all.
KEY_PREDICTION_RUN_ID: Final = "models.prediction_run_id"

# --------------------------------------------------------------------------- #
# Reason codes. Enumerated by tests/console/test_reason_prose.py out of this module's
# `REASON_*` attributes, so a code added here without operator prose turns that test red
# rather than reaching the console as silence.
# --------------------------------------------------------------------------- #

#: No run id, no directory, a failed hash, a feature list in the wrong order, a feature
#: version that is not the one the manifest names, or an artefact with no DI. One code for
#: all of them because they are one fact to an operator — *there is no usable model* — and
#: the `reason` sentence names which.
REASON_UNAVAILABLE: Final = "prediction_unavailable"

#: A feature the manifest names arrived null. Named separately from the above because it is
#: a different fault with a different owner: the model is fine and the inputs are not.
REASON_INPUTS_INCOMPLETE: Final = "prediction_inputs_incomplete"

#: The Dissimilarity Index says this market looks like nothing in the training set.
#: Contract rule 6; engine 8 stays a non-gate and halts the tick anyway. **Not an error.**
#: This is the model declining to answer a question it was never trained on, which is the
#: honest outcome and is the one refusal here that says nothing is broken.
REASON_DI_REFUSED: Final = "di_refused"

# --------------------------------------------------------------------------- #
# Published
# --------------------------------------------------------------------------- #

EXPECTED_MOVE_FIELD: Final = "expected_move_pct"
DI_FIELD: Final = "di"
DI_THRESHOLD_FIELD: Final = "di_threshold"
SHAP_FIELD: Final = "shap"


class PredictionState(BaseModel):
    """What engine 8 publishes into ``state["prediction"]``.

    ``expected_move_pct`` is ``str | None`` rather than a float, and the `None` is load
    bearing: it is absent from the published mapping entirely on a refusal, so engine 10
    fails closed on a key that is not there rather than on a number it has to interpret.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    bar_ts: int
    model_run_id: str | None = None
    feature_version: str | None = None
    p_target: float | None = None
    p_stop: float | None = None
    p_timeout: float | None = None
    expected_move_pct: str | None = None
    is_buy: bool = False
    di: float | None = None
    di_threshold: float | None = None
    shap: dict[str, float] | None = None
    reason_code: str | None = None

    def to_state(self) -> dict[str, Any]:
        """The JSON-serialisable form, with ``expected_move_pct`` **omitted** when absent.

        Omitted rather than null, and the difference matters at exactly one place: engine
        10 treats an absent key and a null identically, so both fail closed, but a null
        that travelled would look in a log like a prediction that produced no move rather
        than like a prediction that never happened.
        """
        payload: dict[str, Any] = {
            "pair": self.pair,
            "bar_ts": self.bar_ts,
            "model_run_id": self.model_run_id,
            "feature_version": self.feature_version,
            "p_target": self.p_target,
            "p_stop": self.p_stop,
            "p_timeout": self.p_timeout,
            "is_buy": self.is_buy,
            DI_FIELD: self.di,
            DI_THRESHOLD_FIELD: self.di_threshold,
            SHAP_FIELD: self.shap,
            "reason_code": self.reason_code,
        }
        if self.expected_move_pct is not None:
            payload[EXPECTED_MOVE_FIELD] = self.expected_move_pct
        return payload
