"""What engine 20 `tournament` reads and what it publishes. Spec 74.

Engine 20 runs in `OFFLINE_CHAIN` through `acsoe research`, never in the live loop, and it
reads **two files and one table**: spec 67's training digest, that run's out-of-sample
parquet, and the `leaderboard` table through `StoreClient`. It reads no archive and writes no
relational row but `leaderboard`.

It has no `state` inputs at all, which is why nothing here names one. The digest path arrives
through the constructor from `acsoe research --digest`, because a digest names one training
run's output file rather than a system-wide setting.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "BRIER_TOLERANCE",
    "DIGEST_FOLDS_FIELD",
    "DIGEST_RUN_ID_FIELD",
    "KEY_REPORTING_CURRENCY",
    "MODEL_ID",
    "OOS_REQUIRED_COLUMNS",
    "REASON_DIGEST_MISMATCH",
    "REASON_NO_DIGEST",
    "REASON_NO_OOS",
    "REASON_NO_STORE",
    "STATE_KEY",
    "TournamentState",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "tournament"

#: Every row this engine writes carries it. **The leaderboard holds model versions, and a
#: version belongs to a model**; today there is one model and the id is fixed, and when
#: Phase 6 adds a second the rows already have the column that tells them apart. A
#: leaderboard that identified rows by version alone would need a migration to hold two
#: models, and the migration would be written while somebody was trying to compare them.
MODEL_ID: Final = "predictor"

DIGEST_RUN_ID_FIELD: Final = "run_id"
DIGEST_FOLDS_FIELD: Final = "folds"

#: What engine 20 needs out of the out-of-sample file. Named here and checked before
#: anything is written, so a schema change upstream is a refusal rather than a leaderboard of
#: zeros.
OOS_REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "fold_index",
    "is_buy",
    "label",
    "p_target",
    "return_pct",
)

#: How far a Brier recomputed from the out-of-sample rows may sit from the digest's before the
#: two are called different numbers. Both are `mean((p_target - hit) ** 2)` over the same
#: float64 values in the same order, so they agree to the last bits or they describe different
#: rows; the tolerance absorbs a summation-order difference and nothing a real disagreement
#: could hide in.
BRIER_TOLERANCE: Final = 1e-9

#: The unit `net_pnl` is expressed in. Read from config rather than assumed, and written into
#: the row beside the number: a money column with no currency is a number nobody can add up.
KEY_REPORTING_CURRENCY: Final = "trading.base_reporting_currency"

# --------------------------------------------------------------------------- #
# Reason codes, enumerated by tests/console/test_reason_prose.py
# --------------------------------------------------------------------------- #

#: No `--digest`, or a path that is not a readable training digest.
REASON_NO_DIGEST: Final = "tournament_no_digest"

#: The digest names an out-of-sample file that is absent, unreadable, or missing a column
#: engine 20 scores from.
REASON_NO_OOS: Final = "tournament_no_oos"

#: No store client, so there is nowhere to write. **A block rather than a silent skip**: a
#: research run that reported success having written nothing is the failure this code exists
#: to make impossible, and Phase 6's router would weight by an empty leaderboard.
REASON_NO_STORE: Final = "tournament_no_store"

#: The digest and the out-of-sample file disagree about a fold: its row count, its BUY count,
#: its Brier or base-rate Brier, whether it is empty, or whether it exists at all. **Nothing is
#: written.** Two numbers for one fold means one of the two files describes rows the other did
#: not score, and a leaderboard built from either would carry a score nobody can trace.
REASON_DIGEST_MISMATCH: Final = "tournament_digest_mismatch"


class TournamentState(BaseModel):
    """What engine 20 publishes into ``state["tournament"]``.

    **The Brier extremes are reported with their fold ids and with each fold's own base-rate
    Brier beside them.** A Brier on its own says nothing: 0.18 is excellent on a base rate of
    50% and poor on one of 5%, and a leaderboard read without the comparison is a ranking of
    which folds had the rarest targets.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str | None = None
    rows_written: int = 0
    rows_skipped: int = 0
    folds: int = 0
    #: Folds the trainer reported empty. They trained no model, so they get no row: a
    #: leaderboard row names a model version somebody could weight or promote, and an empty
    #: fold has no artefact behind its name.
    folds_empty: int = 0
    best_fold: str | None = None
    best_brier: float | None = None
    best_base_rate_brier: float | None = None
    worst_fold: str | None = None
    worst_brier: float | None = None
    worst_base_rate_brier: float | None = None
    reporting_currency: str | None = None
    reason_code: str | None = None

    def to_state(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
