"""What engine 14 `adaptive_router` reads out of ``state`` and what it publishes back.

**Every key name this engine reads lives here and nowhere else**, with the engine that
owns it written beside it. Contract rule 3 forbids importing another engine to find out
what its keys are called, and a key renamed upstream without a matching change here does
not raise — engine 14 would simply publish a weight set with no basis, silently, on every
tick.

**Nothing here is money and nothing here decides anything.** The weights are statistics,
so they are floats (`code-standards.md`: float is fine for features, indicators, model
inputs and statistics). Engine 14 sits after engine 10 `cost` and before engine 15
`skeptic`, it is not a gate, and by invariant 4 no weight it publishes may make the system
more willing to trade. Lowering willingness would be a veto, which only a gate may issue.
So the honest description is that this engine **records** a judgement about model versions
and changes nothing about this tick.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ACTIVE_MODEL_FIELD",
    "BASIS_FIELD",
    "DI_FIELD",
    "DI_MARGIN_FIELD",
    "DI_THRESHOLD_FIELD",
    "LEADERBOARD_ENUMERATION",
    "MODEL_ID",
    "PREDICTION_IS_BUY_FIELD",
    "PREDICTION_KEY",
    "PREDICTION_RUN_ID_FIELD",
    "REASON_LEADERBOARD_EMPTY",
    "REASON_LEADERBOARD_TRUNCATED",
    "REASON_LEADERBOARD_UNREADABLE",
    "REASON_NO_MODEL_BEATS_ITS_BASE_RATE",
    "REGIME_KEY",
    "REGIME_LABEL_FIELD",
    "STATE_KEY",
    "WEIGHTS_FIELD",
    "RouterState",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "adaptive_router"

#: The model family the leaderboard is keyed on. Engine 20 `tournament` writes exactly
#: this constant into every row it produces (`engines/tournament/contracts.py`), and
#: there is one family today. Named here rather than imported, because contract rule 3
#: forbids one engine importing another — and this is the seam where that rule costs
#: something real, so it is written down rather than reached for.
MODEL_ID: Final = "predictor"

# --------------------------------------------------------------------------- #
# Read from the store (agent B)
# --------------------------------------------------------------------------- #

#: The **non-truncating** enumeration of leaderboard rows, requested of B and queued
#: beside migration 0004. Resolved by name off the store client rather than imported, so
#: that engine 14 lands before the method does and says so instead of failing to import.
#:
#: **It cannot be `leaderboard_entries`**, which spec 97 step 2 named: that is B's
#: *existence check* for engine 20's idempotency and takes `model_version` as an argument,
#: so it cannot enumerate the versions engine 14 exists to weight. Found by building
#: against the store rather than against the spec's description of it.
LEADERBOARD_ENUMERATION: Final = "all_leaderboard_rows"

# --------------------------------------------------------------------------- #
# Read from engine 12 `regime` (agent C, spec 66)
# --------------------------------------------------------------------------- #

#: `trending`, `choppy`, `high_volatility`, or `null` with a reason. **Published as
#: provenance and never used in the arithmetic** — see the README. The leaderboard holds
#: one Brier per model version over the whole out-of-sample window with no regime
#: breakdown anywhere, so a regime-conditional weight would be invented rather than
#: measured.
REGIME_KEY: Final = "regime"
REGIME_LABEL_FIELD: Final = "label"

# --------------------------------------------------------------------------- #
# Read from engine 8 `prediction` (agent C, specs 71 and 95)
# --------------------------------------------------------------------------- #

PREDICTION_KEY: Final = "prediction"

#: Which model version actually produced this tick's call. Reported beside the weights so
#: an operator can see whether the version carrying the weight is the one that traded;
#: engine 14 does **not** select it, and `models.prediction_run_id` governs. Spec 97's
#: first scope limit.
PREDICTION_RUN_ID_FIELD: Final = "model_run_id"

DI_FIELD: Final = "di"
DI_THRESHOLD_FIELD: Final = "di_threshold"

#: Whether engine 8 called a BUY. **Absent on every refusal since spec 95**, which is how
#: engine 8 reports that no model scored — so engine 14 is the first reader of that field
#: outside a gate, and it treats the absence as "no call" rather than as "not a BUY".
PREDICTION_IS_BUY_FIELD: Final = "is_buy"

# --------------------------------------------------------------------------- #
# Reason codes, enumerated by tests/console/test_reason_prose.py out of this module's
# `REASON_*` attributes, so a code added here without operator prose turns that test red
# rather than reaching the console as silence.
# --------------------------------------------------------------------------- #

#: No leaderboard rows at all — nothing has been through engine 20 yet. Weights absent,
#: which is the state a fresh clone is in and is not an error.
REASON_LEADERBOARD_EMPTY: Final = "leaderboard_empty"

#: The store offers no non-truncating enumeration, so engine 14 cannot see the whole
#: table. **No weights**, rather than weights over whatever a windowed read returned.
REASON_LEADERBOARD_UNREADABLE: Final = "leaderboard_unreadable"

#: A windowed read came back **exactly full**, so rows beyond the window exist and were
#: not looked at. No weights — the failure this prevents is that the weights would still
#: sum to one, over the wrong set, and a version outside the window would be absent
#: because nobody looked rather than zero because it had no edge. Those two are
#: indistinguishable downstream.
REASON_LEADERBOARD_TRUNCATED: Final = "leaderboard_truncated"

#: Every model version scored at or below its own base rate, so every weight is zero.
#: Not an error and not a refusal: it is the leaderboard saying nothing here has edge,
#: which is a finding rather than a fault.
REASON_NO_MODEL_BEATS_ITS_BASE_RATE: Final = "no_model_beats_its_base_rate"

# --------------------------------------------------------------------------- #
# Published
# --------------------------------------------------------------------------- #

WEIGHTS_FIELD: Final = "weights"
ACTIVE_MODEL_FIELD: Final = "active_model_run_id"
BASIS_FIELD: Final = "basis"
DI_MARGIN_FIELD: Final = "di_margin"


class RouterState(BaseModel):
    """What engine 14 publishes into ``state["adaptive_router"]``.

    There is no field here that a downstream engine could read as permission. Invariant 4
    and spec 97 step 5: engine 14 sits after engine 10, so no weight may raise willingness
    to trade, and lowering it would be a veto only a gate may issue. Engine 15 does not
    read this payload at all, and a test asserts that on engine 15's source.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Weight per **model version**, summing to 1.0, or all zero, or absent. Floats:
    #: these are statistics, not money.
    weights: dict[str, float] | None = None

    #: The version engine 8 actually scored with this tick, echoed rather than chosen.
    active_model_run_id: str | None = None

    #: How each weight was arrived at, per version, plus the counts that make the set
    #: checkable — how many rows were read, how many versions they covered, and how many
    #: duplicate `(version, fold)` rows were collapsed.
    basis: dict[str, Any] | None = None

    regime: str | None = None

    #: `di_threshold - di`, positive when the candidate sits inside the reference set.
    #: **Provenance only**, like the regime.
    di_margin: float | None = None

    reason_code: str | None = None

    def to_state_data(self) -> dict[str, Any]:
        """The JSON-serialisable payload.

        `weights` is **omitted** when there is none, following `expected_move_pct` and
        `is_buy`: a consumer reading the key on a tick where nothing could be weighted
        should get a `KeyError` rather than an empty mapping it has to interpret. An
        empty mapping and "every weight is zero" are different facts, and the second is
        published as an actual mapping of zeros.

        There is deliberately **no `pair` and no bar timestamp**. Engine 16's coherence
        walk checks any payload carrying either, and this payload is about model versions
        rather than about this tick's candidate — a `pair` here would be a field engine 16
        checks and nothing produces from the candidate.
        """
        payload: dict[str, Any] = {
            ACTIVE_MODEL_FIELD: self.active_model_run_id,
            BASIS_FIELD: self.basis,
            REGIME_KEY: self.regime,
            DI_MARGIN_FIELD: self.di_margin,
            "reason_code": self.reason_code,
        }
        if self.weights is not None:
            payload[WEIGHTS_FIELD] = dict(self.weights)
        return payload
