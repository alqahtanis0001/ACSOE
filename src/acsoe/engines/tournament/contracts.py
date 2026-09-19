"""What engine 20 `tournament` reads and what it publishes. Spec 74.

Engine 20 runs in `OFFLINE_CHAIN` through `acsoe research`, never in the live loop, and it
reads **two files and one table**: spec 67's training digest, that run's out-of-sample
parquet, and the `leaderboard` table through `StoreClient`. It reads no archive and writes no
relational row but `leaderboard`.

It has no `state` inputs at all, which is why nothing here names one. The digest path arrives
through the constructor from `acsoe research --digest`, because a digest names one training
run's output file rather than a system-wide setting.

**Spec 139 adds the promotion gate**, a second job run when the constructor names a run to
judge: it reads that run's closed trades through the store and the committed trial ledger's
count, applies `modelling/promotion.py`'s bar, and writes one leaderboard row carrying the
verdict. The bar's statistics live in that module and nowhere else.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "BRIER_TOLERANCE",
    "CHAIN_RUN_MODEL_ID",
    "DIGEST_FOLDS_FIELD",
    "DIGEST_RUN_ID_FIELD",
    "KEY_REPORTING_CURRENCY",
    "MODEL_ID",
    "OOS_REQUIRED_COLUMNS",
    "PROMOTION_REASONS",
    "PROMOTION_TRADE_CAP",
    "REASON_DIGEST_MISMATCH",
    "REASON_NO_DIGEST",
    "REASON_NO_OOS",
    "REASON_NO_STORE",
    "REASON_PROMOTION_BAD_TRADE",
    "REASON_PROMOTION_LOWER_BOUND",
    "REASON_PROMOTION_NO_LEDGER",
    "REASON_PROMOTION_TOO_FEW_TRADES",
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

#: The `model_id` of a promotion verdict's row (spec 139). **A verdict judges a run of the
#: whole chain**, not one fold's predictor: the Phase 7 runs replay 26 weekly models in sequence
#: behind every gate, and the trades being judged are the chain's. So the row sits beside the
#: predictor's per-fold rows under its own id, with the judged run's `run_id` as its version,
#: and engine 14 — which weights only its own model family — never reads it.
CHAIN_RUN_MODEL_ID: Final = "chain_run"

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

# --------------------------------------------------------------------------- #
# The promotion gate, spec 139. The first two are verdicts, written on the leaderboard row
# with `promoted` false; the last two are refusals that write nothing.
# --------------------------------------------------------------------------- #

#: Fewer than ten closed trades: no interval, so no promotion.
REASON_PROMOTION_TOO_FEW_TRADES: Final = "promotion_too_few_trades"

#: The overlap-robust interval, widened for the ledger's trial count, does not lie above zero.
REASON_PROMOTION_LOWER_BOUND: Final = "promotion_lower_bound_not_above_zero"

#: No trial ledger, or one whose count disagrees with its own rows. **Nothing is written**: a
#: verdict without the trial count is a verdict at N = 1, the most generous there is.
REASON_PROMOTION_NO_LEDGER: Final = "promotion_no_ledger"

#: A trade the net return cannot be computed from honestly: no entry notional, or a quote
#: currency other than the reporting currency (so `realised_pnl` and the notional would be in
#: two units). **Nothing is written**, because excluding it would judge a different run.
REASON_PROMOTION_BAD_TRADE: Final = "promotion_bad_trade"

#: The most closed trades the gate will read in one store. It reads one more and refuses if
#: it gets it, because the store's read is a window and a truncated window is a different run.
PROMOTION_TRADE_CAP: Final = 1_000_000

#: The verdict codes, by `modelling.promotion.Verdict`. A promoted row carries none.
PROMOTION_REASONS: Final[dict[str, str]] = {
    "too_few_trades": REASON_PROMOTION_TOO_FEW_TRADES,
    "lower_bound_not_above_zero": REASON_PROMOTION_LOWER_BOUND,
}


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
    #: The promotion gate's verdict (spec 139), present only when a run was judged. Every
    #: figure is published whatever the verdict, and the deflated Sharpe ratio beside it.
    promotion_run_id: str | None = None
    promoted: bool | None = None
    promotion_reason_code: str | None = None
    trial_count: int | None = None
    trades_judged: int | None = None
    hac_lag: int | None = None
    mean_net_return: float | None = None
    se_hac: float | None = None
    se_naive: float | None = None
    confidence: float | None = None
    t_quantile: float | None = None
    lower_bound: float | None = None
    sharpe: float | None = None
    deflated_sharpe: float | None = None

    def to_state(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
