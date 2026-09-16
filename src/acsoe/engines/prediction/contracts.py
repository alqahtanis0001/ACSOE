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
engine 8 having to know what engine 10 does with it. ``is_buy`` follows the same shape for
the same reason, spec 95: it is absent on every refusal and present only when the model
scored, so a consumer can tell *no call* from *not a BUY*.
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
    "IS_BUY_FIELD",
    "KEY_DI_PERCENTILE",
    "KEY_PREDICTION_RUN_ID",
    "MACRO_CONTEXT_KEY",
    "MACRO_FEATURES_FIELD",
    "REASON_DI_PERCENTILE_MISMATCH",
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

#: The percentile the DI's threshold was fitted at. **Read here only to check it against the
#: artefact's**, never to compute anything: the threshold travels inside `di.npz` and is a
#: property of the training run, so once any percentile is baked in, changing this key changes
#: nothing the running system does. B-2's rehearsal of engines 13 and 8 found that gap, and the
#: ruling of 2026-09-13 is that a mismatch blocks rather than letting the operator read a
#: number the system is not using. Absent, the artefact's own percentile stands unquestioned.
KEY_DI_PERCENTILE: Final = "prediction.di_percentile"

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

#: `prediction.di_percentile` is set and disagrees with the percentile the loaded artefact's
#: DI was fitted at. **Separate from `prediction_unavailable` because the fix is different**:
#: the model is fine and the artefact is fine, and what is wrong is that the operator has
#: changed a number believing it takes effect. It does not — the threshold is baked in — so
#: the honest answer is to stop and say both numbers rather than to keep refusing at the old
#: line while the config claims a new one.
REASON_DI_PERCENTILE_MISMATCH: Final = "di_percentile_mismatch"

# --------------------------------------------------------------------------- #
# Published
# --------------------------------------------------------------------------- #

EXPECTED_MOVE_FIELD: Final = "expected_move_pct"

#: Whether the scored model called a BUY. **Published only when the model scored**, and
#: absent from the payload on every refusal — spec 95. It used to be `bool = False`
#: published unconditionally, which made a refusing engine 8 look exactly like a predictor
#: that ran and called no BUY, and left engine 15's non-BUY pass one omission away from
#: being reached on a tick where nothing was predicted at all.
IS_BUY_FIELD: Final = "is_buy"

DI_FIELD: Final = "di"
DI_THRESHOLD_FIELD: Final = "di_threshold"
SHAP_FIELD: Final = "shap"


class PredictionState(BaseModel):
    """What engine 8 publishes into ``state["prediction"]``.

    ``expected_move_pct`` is ``str | None`` rather than a float, and the `None` is load
    bearing: it is absent from the published mapping entirely on a refusal, so engine 10
    fails closed on a key that is not there rather than on a number it has to interpret.

    ``is_buy`` is ``bool | None`` for the same reason and is the same shape, spec 95.
    ``None`` is *no call was made*; ``False`` is *the model scored and called no BUY*.
    Those are two different facts with two different readers — engine 15 blocks on the
    first and passes on the second — and a default of ``False`` published on every path
    made them one.
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
    is_buy: bool | None = None
    di: float | None = None
    di_threshold: float | None = None
    shap: dict[str, float] | None = None
    reason_code: str | None = None

    def to_state(self) -> dict[str, Any]:
        """The JSON-serialisable form, with ``expected_move_pct`` and ``is_buy``
        **omitted** when absent.

        Omitted rather than null, and for ``expected_move_pct`` the difference matters at
        exactly one place: engine 10 treats an absent key and a null identically, so both
        fail closed, but a null that travelled would look in a log like a prediction that
        produced no move rather than like a prediction that never happened.

        For ``is_buy`` the difference is larger, because engine 15's reader distinguishes
        three cases and not two. An explicit ``False`` is a non-BUY and passes; anything
        that is not a ``bool`` — absent included — blocks with `skeptic_unavailable`. A
        ``null`` here would satisfy that reader too, so the omission is not what makes
        engine 15 safe; what it buys is that nothing downstream can read the key at all on
        a tick where no model ran, which is the same guarantee ``expected_move_pct``
        already gives engine 10. Spec 95.
        """
        payload: dict[str, Any] = {
            "pair": self.pair,
            "bar_ts": self.bar_ts,
            "model_run_id": self.model_run_id,
            "feature_version": self.feature_version,
            "p_target": self.p_target,
            "p_stop": self.p_stop,
            "p_timeout": self.p_timeout,
            DI_FIELD: self.di,
            DI_THRESHOLD_FIELD: self.di_threshold,
            SHAP_FIELD: self.shap,
            "reason_code": self.reason_code,
        }
        if self.expected_move_pct is not None:
            payload[EXPECTED_MOVE_FIELD] = self.expected_move_pct
        if self.is_buy is not None:
            payload[IS_BUY_FIELD] = self.is_buy
        return payload
