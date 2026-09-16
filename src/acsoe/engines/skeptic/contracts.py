"""What engine 15 `skeptic` reads out of ``state``, and what it publishes back into it.

**Every key name this engine reads lives here and nowhere else**, with the engine that owns
it written beside it. Contract rule 3 forbids importing another engine to find out what its
keys are called.

Engine 15 is the last gate before the decision and the only one that reads the prediction.
That is deliberate and it is the opposite of engine 13's arrangement: the skeptic's whole
job is to grade **the predictor's own call**, so it must see the call, while the anomaly gate
judges the market and must not.

**Nothing here can approve.** `PredictionState` publishes `p_wrong` and `vetoed`, and there
is no field an engine downstream could read as a reason to trade that it would not have
traded anyway. Invariant 4.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "FEATURE_BAR_TS_FIELD",
    "FEATURE_KEY",
    "FEATURE_PAIRS_FIELD",
    "KEY_SKEPTIC_RUN_ID",
    "KEY_VETO_THRESHOLD",
    "MACRO_CONTEXT_KEY",
    "MACRO_FEATURES_FIELD",
    "NOT_A_BUY_CALL",
    "PREDICTION_EXPECTED_MOVE_FIELD",
    "PREDICTION_IS_BUY_FIELD",
    "PREDICTION_KEY",
    "PREDICTION_PAIR_FIELD",
    "PREDICTION_PROBABILITY_FIELDS",
    "REASON_UNAVAILABLE",
    "REASON_VETO",
    "SCOUT_CANDIDATE_FIELD",
    "SCOUT_KEY",
    "STATE_KEY",
    "SkepticState",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "skeptic"

# --------------------------------------------------------------------------- #
# Read from engine 7 `scout` (agent B) and engine 5 `feature` (agent C)
# --------------------------------------------------------------------------- #

SCOUT_KEY: Final = "scout"
SCOUT_CANDIDATE_FIELD: Final = "pair"

FEATURE_KEY: Final = "feature"
FEATURE_PAIRS_FIELD: Final = "pairs"
FEATURE_BAR_TS_FIELD: Final = "bar_ts"

# --------------------------------------------------------------------------- #
# Read from engine 6 `macro_context` (agent C, spec 65)
# --------------------------------------------------------------------------- #

MACRO_CONTEXT_KEY: Final = "macro_context"

#: The `macro_*` half of the feature vector. **The skeptic's feature half is the predictor's
#: whole feature list**, macro columns included, because it was trained on exactly that — so
#: this engine assembles the vector from the same two publishers engine 8 does. Reading only
#: the pair's own row would leave every macro column missing and block every call, which is
#: what it did until a surviving mutation in the spec 73 sweep pointed at it.
MACRO_FEATURES_FIELD: Final = "features"

# --------------------------------------------------------------------------- #
# Read from engine 8 `prediction` (agent C, spec 71)
# --------------------------------------------------------------------------- #

PREDICTION_KEY: Final = "prediction"
PREDICTION_PAIR_FIELD: Final = "pair"

#: Whether engine 8 called this a BUY. False means the skeptic has no opinion: it grades BUY
#: calls, and a model asked to grade a call nobody made is answering a different question.
#: **Turning a non-BUY into no trade is the decision engine's job in Phase 6**, not this
#: gate's — a `BLOCK` here would record a veto that never happened. **Only an explicit
#: `False`**: absent, `None` or a non-boolean is engine 8 having made no call at all, and
#: blocks with `REASON_UNAVAILABLE`. Invariant 3.
#:
#: **Engine 8 omits this key on every refusal**, spec 95, so absent is that engine's way of
#: saying the model never scored — the same shape `expected_move_pct` has always had. The
#: three-way read here predates it and is unchanged by it: a reader that collapsed absent
#: into `False` would pass a tick on which nothing was predicted.
PREDICTION_IS_BUY_FIELD: Final = "is_buy"

#: The predictor's own three probabilities, in the order the manifest records them beside
#: the feature list. Engine 8 publishes floats; the skeptic was trained on the same three.
PREDICTION_PROBABILITY_FIELDS: Final[tuple[str, ...]] = ("p_target", "p_stop", "p_timeout")

#: The expected move, as the exact decimal string engine 8 publishes for engine 10. Parsed to
#: a float here and only here: the skeptic was trained on a float and a `Decimal` handed to a
#: fitted model is a type error at best and a silent cast at worst.
PREDICTION_EXPECTED_MOVE_FIELD: Final = "expected_move_pct"

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

#: The active skeptic. **Optional on the config model and absent from
#: `config/default.yaml`**; absent, the gate blocks.
KEY_SKEPTIC_RUN_ID: Final = "models.skeptic_run_id"

#: Above this probability of being wrong, the call is vetoed. **The operator's, after the
#: walk-forward reports, and absent until then.** Nothing in this repository may default it:
#: it is the number that decides how often a learned model is allowed to overrule a call the
#: rest of the chain has already cleared.
KEY_VETO_THRESHOLD: Final = "skeptic.veto_threshold"

# --------------------------------------------------------------------------- #
# Reason codes, enumerated by tests/console/test_reason_prose.py
# --------------------------------------------------------------------------- #

#: No run id, no directory, a failed hash, a fold that produced no skeptic, no configured
#: veto threshold, an absent or non-boolean `is_buy`, or a non-finite `p_wrong`. One code
#: because they are one fact to an operator — *the skeptic cannot judge this call* — and the
#: `reason` sentence names which.
REASON_UNAVAILABLE: Final = "skeptic_unavailable"

#: `p_wrong` above `skeptic.veto_threshold`.
REASON_VETO: Final = "skeptic_veto"

#: Published on the `OK` path when engine 8 did not call a BUY. **Deliberately not named
#: `REASON_*`**, because in this repository that prefix means a reason *code* — a
#: machine-readable string `console/format.py` maps to operator prose — and
#: `tests/console/test_reason_prose.py` enumerates every `REASON_*` a contracts module
#: declares and requires prose for it. This is neither: it is the sentence itself, on a
#: result that is not a refusal, saying the skeptic was reached and had nothing to say.
#: That is different from the skeptic not having run, which is why it is recorded at all.
NOT_A_BUY_CALL: Final = "not a BUY call"


class SkepticState(BaseModel):
    """What engine 15 publishes into ``state["skeptic"]``.

    `vetoed` is the only boolean and it is the only thing this engine can assert. There is no
    `approved`, no confidence and no margin: invariant 4, and a field here that made a trade
    more likely would be a model output overriding a gate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    model_run_id: str | None = None
    p_wrong: float | None = None
    threshold: float | None = None
    vetoed: bool = False
    reason: str | None = None
    reason_code: str | None = None

    def to_state(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
