"""Engine 20 `tournament` — one leaderboard row per trained model version. Spec 74.

Reads spec 67's training digest and that run's out-of-sample file, scores every fold's model
version against the realised outcomes, and writes one `leaderboard` row per version through
the store. Phase 6's adaptive router weights by those rows; Phase 7's promotion gate judges
by them.

**In Phase 5 the realised outcomes are the labels.** From Phase 6 they will also be trades.
That is the whole reason `n_trades` counts BUY *calls* here rather than fills: nothing has
been filled, and a column that counted zero would make every model look untraded rather than
untested.

## It runs offline, in `OFFLINE_CHAIN`, never in the live loop

It has no `state` inputs at all. The digest path comes through the constructor from
`acsoe research --digest`, because a digest names one training run's output file rather than a
system-wide setting, and `cli/research.py` resolves this class by name.

## Every number on a row comes from the out-of-sample rows, and the digest is a cross-check

`n_trades`, `win_rate`, `net_pnl` **and `brier`** are computed here from the fold's own
out-of-sample rows, selected by the `fold_index` the splitter assigned — never by a timestamp
window this engine would have to draw again. The out-of-sample file carries `p_target`, the
**calibrated** probability the trainer scored, so the Brier is recomputable and is recomputed:
a leaderboard whose trade columns came from one source and whose headline metric came from
another would have nothing to say when the two stopped describing the same rows.

The digest's own numbers are then compared against those recomputed ones — row count, BUY
count, Brier and base-rate Brier per fold, which folds exist and which are empty — and **any
disagreement writes nothing** and blocks with `tournament_digest_mismatch`. The two files are
one run's output; when they disagree, one of them describes rows the other did not score, and
a wrong boundary anywhere upstream shows up here as exactly that.

## What it will not do

**It never promotes.** `promoted` is always false. The promotion gate is Phase 7 and it is a
different question from "which model scored best" — a model can top this table and still fail
on stability, on sample size, or on an operator's judgement about the period it was fitted in.

**It computes no Sharpe, no deflated Sharpe, no alpha and no beta.** Those four stay null.
They are Phase 7's, and a number written into them now would be read as one later by somebody
who did not write it: a Sharpe over label returns with no friction, no position sizing and no
holding period is not a worse Sharpe, it is a different quantity wearing the name.

**It writes no row for an empty fold.** The trainer reports a fold with no training or no test
rows as empty and writes no artefact for it. A leaderboard row names a model version somebody
could weight or promote, and an empty fold has nothing behind its name.

**It reads no archive and writes no relational row but `leaderboard`.**

## Idempotent, and the existence read is the store's

A `(model_id, model_version, fold)` already present is not written again, and the engine
reports how many it wrote and how many it found. The check uses
`StoreClient.leaderboard_entries`, which B-2 added for exactly this: deciding "have I written
this fold already" from `leaderboard()` — the console's newest-fifty read — would silently
start writing duplicates on a walk-forward with more than fifty folds, and a duplicate looks
exactly like a second training run.

## `trained_at` and `updated_at` are different instants

`trained_at` is when the run was trained (the digest's `created_at`). `updated_at` is when the
row was written, from `context.now`. `leaderboard` is one of the tables the console's poll
watermark reads, and that watermark only moves for a row stamped from the injected clock: a
row stamped with its training time is older than the watermark it lands under, and an open
console would go on showing the old leaderboard with nothing to say so.

## The Brier extremes carry their base rates

A Brier on its own says nothing. 0.18 is excellent against a base rate of 50% and poor
against one of 5%, so the best and worst folds are reported with **each fold's own base-rate
Brier beside them**. Without it the report ranks which folds had the rarest targets.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.tournament.contracts import (
    BRIER_TOLERANCE,
    DIGEST_FOLDS_FIELD,
    DIGEST_RUN_ID_FIELD,
    KEY_REPORTING_CURRENCY,
    MODEL_ID,
    OOS_REQUIRED_COLUMNS,
    REASON_DIGEST_MISMATCH,
    REASON_NO_DIGEST,
    REASON_NO_OOS,
    REASON_NO_STORE,
    STATE_KEY,
    TournamentState,
)

#: The label that counts as a win and as a hit in the Brier. The labeller's own spelling.
_TARGET = "target"


class TournamentError(ValueError):
    """A digest or an out-of-sample file this engine will not score from.

    Carries the reason code, because three different refusals travel through this one type
    and the code is the only thing that says which one ran.
    """

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class TournamentEngine(BaseEngine):
    """Engine 20. Offline chain, after engine 23. Not a gate."""

    name: ClassVar[str] = STATE_KEY
    number: ClassVar[int] = 20
    is_gate: ClassVar[bool] = False

    def __init__(self, *, digest_path: Path | None = None) -> None:
        """`digest_path` is `acsoe research --digest`. Keyword-only, and agreed by name.

        `cli/research.py` calls `TournamentEngine(digest_path=...)` and raises loudly if the
        keyword does not exist, rather than falling back to a no-argument call — which is how
        engine 23 spent a phase green against a labeller signature that never existed.
        """
        self._digest_path = None if digest_path is None else Path(digest_path)

    def process(self, context: EngineContext, state: State) -> EngineResult:
        del state  # Engine 20 has no `state` inputs. Contract rule 3, by having no names.
        started = time.perf_counter()

        store = getattr(context.clients, "store", None)
        if store is None or not hasattr(store, "write_leaderboard_entry"):
            return self._blocked(
                started,
                REASON_NO_STORE,
                "no store client is available, so there is nowhere to write the "
                "leaderboard. A research run that reported success having written nothing "
                "is worse than one that failed: Phase 6's router would weight by an empty "
                "table.",
            )

        try:
            digest = self._digest()
        except TournamentError as problem:
            return self._blocked(started, problem.reason_code, str(problem))

        run_id = str(digest.get(DIGEST_RUN_ID_FIELD) or "") or None
        try:
            scores = _fold_scores(self._oos_path(digest), digest)
        except TournamentError as problem:
            return self._blocked(started, problem.reason_code, str(problem), run_id=run_id)

        from acsoe.clients.store.contracts import to_micros

        currency = str(context.config.get(KEY_REPORTING_CURRENCY))
        written, skipped = _write_rows(
            store,
            digest,
            scores.rows,
            currency=currency,
            written_at=to_micros(context.now),
        )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=_report(digest, scores, written, skipped, currency).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ inputs

    def _digest(self) -> Mapping[str, Any]:
        import json

        if self._digest_path is None:
            raise TournamentError(
                REASON_NO_DIGEST,
                "no training digest was given. `acsoe research --digest` names the file "
                "spec 67 wrote; engine 20 scores what a training run reported and has "
                "nothing to score without it.",
            )
        if not self._digest_path.is_file():
            raise TournamentError(
                REASON_NO_DIGEST,
                f"{self._digest_path} is not a file. It is the digest spec 67's trainer "
                "writes beside its artefacts.",
            )
        try:
            payload = json.loads(self._digest_path.read_bytes().decode("utf-8"))
        except (OSError, ValueError) as problem:
            raise TournamentError(
                REASON_NO_DIGEST,
                f"{self._digest_path} could not be read as a training digest: {problem}",
            ) from problem
        if not isinstance(payload, Mapping) or DIGEST_FOLDS_FIELD not in payload:
            raise TournamentError(
                REASON_NO_DIGEST,
                f"{self._digest_path} has no `{DIGEST_FOLDS_FIELD}`, so it is not a "
                "training digest. Engine 20 writes one leaderboard row per fold.",
            )
        return dict(payload)

    def _oos_path(self, digest: Mapping[str, Any]) -> Path:
        """The out-of-sample parquet beside the digest, by the trainer's own naming.

        Derived from the digest's own `run_id` rather than configured, because the two files
        are one run's output and a caller that could point at a mismatched pair would produce
        a leaderboard scoring one model against another's calls.
        """
        run_id = str(digest.get(DIGEST_RUN_ID_FIELD) or "")
        if not run_id:
            raise TournamentError(
                REASON_NO_DIGEST,
                f"{self._digest_path} records no `{DIGEST_RUN_ID_FIELD}`, so its "
                "out-of-sample file cannot be found and its rows could not be identified "
                "if it were.",
            )
        assert self._digest_path is not None
        return self._digest_path.parent / f"oos_{run_id}.parquet"

    # ------------------------------------------------------------------ results

    def _blocked(
        self, started: float, reason_code: str, reason: str, *, run_id: str | None = None
    ) -> EngineResult:
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=reason,
            data=TournamentState(run_id=run_id, reason_code=reason_code).to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _FoldScore:
    """One fold's row, before it is a `LeaderboardRow`. Every number from the OOS rows."""

    fold: str
    version: str
    trained_at: int
    n_trades: int
    win_rate: float | None
    net_pnl: Decimal
    brier: float
    base_rate_brier: float


@dataclass(frozen=True, slots=True)
class _Scores:
    rows: tuple[_FoldScore, ...]
    folds: int
    empty: int


def _fold_scores(oos_path: Path, digest: Mapping[str, Any]) -> _Scores:
    """One score per non-empty fold, from the out-of-sample rows, cross-checked on the digest.

    **Nothing is written until every fold has been checked.** The caller writes only after
    this returns, so a disagreement found on the last fold still leaves the leaderboard as it
    was rather than half-updated from a run that turned out not to add up.
    """
    import polars as pl

    if not oos_path.is_file():
        raise TournamentError(
            REASON_NO_OOS,
            f"{oos_path} is not a file. The digest names a run whose out-of-sample rows are "
            "not beside it, and a leaderboard written without them would report zero trades "
            "for every model.",
        )
    try:
        frame = pl.read_parquet(oos_path)
    except Exception as problem:
        raise TournamentError(
            REASON_NO_OOS, f"{oos_path} could not be read: {problem}"
        ) from problem

    absent = [name for name in OOS_REQUIRED_COLUMNS if name not in frame.columns]
    if absent:
        raise TournamentError(
            REASON_NO_OOS,
            f"{oos_path} is missing " + ", ".join(absent) + ". Engine 20 scores from these "
            "columns; a schema change upstream must be a refusal rather than a leaderboard "
            "of zeros.",
        )

    entries = [dict(entry) for entry in (digest.get(DIGEST_FOLDS_FIELD) or ())]
    listed = {int(entry["fold_index"]) for entry in entries}
    present = {int(value) for value in frame["fold_index"].unique().to_list()}
    stray = sorted(present - listed)
    if stray:
        raise TournamentError(
            REASON_DIGEST_MISMATCH,
            f"{oos_path} carries out-of-sample rows for fold(s) "
            + ", ".join(str(index) for index in stray)
            + " that the digest does not list. The two files are one run's output; rows for "
            "a fold the digest never reported were scored by a model nobody can name.",
        )

    run_id = str(digest.get(DIGEST_RUN_ID_FIELD) or "")
    trained_at = _micros(digest, entries)
    rows: list[_FoldScore] = []
    empty = 0
    for entry in entries:
        index = int(entry["fold_index"])
        fold_rows = frame.filter(pl.col("fold_index") == index)
        if entry.get("is_empty"):
            if fold_rows.height:
                raise _mismatch(
                    index,
                    f"the digest reports it empty and the out-of-sample file holds "
                    f"{fold_rows.height} row(s) for it",
                )
            # No model was trained, so there is no version to rank. See the module docstring.
            empty += 1
            continue
        rows.append(_score_one(index, entry, fold_rows, run_id=run_id, trained_at=trained_at))
    return _Scores(rows=tuple(rows), folds=len(entries), empty=empty)


def _score_one(
    index: int,
    entry: Mapping[str, Any],
    fold_rows: Any,
    *,
    run_id: str,
    trained_at: int,
) -> _FoldScore:
    """Score one fold from its out-of-sample rows and refuse if the digest disagrees."""
    import numpy as np
    import polars as pl

    # **The fold's own artefact run id is the model version.** Each fold produces a separate
    # artefact directory and each is a model somebody could promote; `training_run_id` is what
    # groups them back into one walk-forward. Never invented: a non-empty fold whose entry lost
    # its run id is a digest this engine cannot attribute, not one it may guess a name for.
    version = entry.get(DIGEST_RUN_ID_FIELD)
    if not version:
        raise TournamentError(
            REASON_NO_DIGEST,
            f"fold {index} trained a model and its digest entry records no `run_id`, so the "
            f"model version is unknown. The leaderboard names versions; guessing "
            f"`{run_id}-f{index}` would name a directory this engine never checked exists.",
        )

    reported_rows = entry.get("rows")
    if reported_rows is None or int(reported_rows) != fold_rows.height:
        raise _mismatch(
            index,
            f"the digest reports {reported_rows} test row(s) and the out-of-sample file "
            f"holds {fold_rows.height}",
        )

    hits = (fold_rows["label"] == _TARGET).cast(pl.Float64).to_numpy()
    p_target = fold_rows["p_target"].cast(pl.Float64).to_numpy()
    brier = float(np.mean((p_target - hits) ** 2))
    rate = float(np.mean(hits))
    base_rate_brier = rate * (1.0 - rate)
    for name, recomputed in (("brier", brier), ("base_rate_brier", base_rate_brier)):
        reported = _as_float_or_none(entry.get(name))
        if reported is None or not math.isclose(
            reported, recomputed, rel_tol=0.0, abs_tol=BRIER_TOLERANCE
        ):
            raise _mismatch(
                index,
                f"the digest reports {name} {reported} and the out-of-sample rows give "
                f"{recomputed!r}",
            )

    buys = fold_rows.filter(pl.col("is_buy"))
    reported_buys = entry.get("buy_count")
    if reported_buys is not None and int(reported_buys) != buys.height:
        raise _mismatch(
            index,
            f"the digest reports {reported_buys} BUY call(s) and the out-of-sample file "
            f"holds {buys.height}",
        )
    labels = [str(value) for value in buys["label"]]
    wins = sum(1 for label in labels if label == _TARGET)
    # `Decimal(repr(...))` and not `Decimal(float)`: the shortest decimal that round trips,
    # which is the number that was computed, rather than the double's full binary expansion.
    # The same crossing `research/labelling.py` makes.
    total = sum((Decimal(repr(float(value))) for value in buys["return_pct"]), Decimal(0))
    return _FoldScore(
        fold=str(index),
        version=str(version),
        trained_at=trained_at,
        n_trades=len(labels),
        win_rate=(wins / len(labels)) if labels else None,
        net_pnl=total,
        brier=brier,
        base_rate_brier=base_rate_brier,
    )


def _mismatch(index: int, detail: str) -> TournamentError:
    return TournamentError(
        REASON_DIGEST_MISMATCH,
        f"fold {index}: {detail}. The digest and the out-of-sample file are one run's output "
        "and they disagree, so one of them describes rows the other did not score. Nothing "
        "was written.",
    )


def _write_rows(
    store: Any,
    digest: Mapping[str, Any],
    scores: Sequence[_FoldScore],
    *,
    currency: str,
    written_at: int,
) -> tuple[int, int]:
    """Write one row per fold, skipping any `(model_id, model_version, fold)` already there.

    The existence read is `leaderboard_entries`, not `leaderboard()`. The second is the
    console's newest-fifty and deciding idempotence from a truncating window would start
    writing duplicates on the fifty-first fold — the rows-versus-ticks defect of spec 51
    again, and a duplicate row looks exactly like a second training run.
    """
    from acsoe.clients.store.contracts import LeaderboardRow

    run_id = str(digest[DIGEST_RUN_ID_FIELD])
    written = 0
    skipped = 0
    for score in scores:
        existing = store.leaderboard_entries(
            model_id=MODEL_ID, model_version=score.version, fold=score.fold
        )
        if existing:
            skipped += 1
            continue
        store.write_leaderboard_entry(
            LeaderboardRow(
                model_id=MODEL_ID,
                model_version=score.version,
                training_run_id=run_id,
                trained_at=score.trained_at,
                fold=score.fold,
                n_trades=score.n_trades,
                win_rate=score.win_rate,
                brier=score.brier,
                net_pnl=score.net_pnl,
                reporting_currency=currency,
                # Phase 7's, every one of them. A number here would be read as a measurement.
                sharpe=None,
                deflated_sharpe=None,
                alpha=None,
                beta=None,
                promoted=False,
                # When the row was written, from the injected clock: the console's poll
                # watermark moves only for this. See the module docstring.
                updated_at=written_at,
            )
        )
        written += 1
    return written, skipped


def _report(
    digest: Mapping[str, Any],
    scores: _Scores,
    written: int,
    skipped: int,
    currency: str,
) -> TournamentState:
    rows = scores.rows
    best = min(rows, key=lambda s: s.brier) if rows else None
    worst = max(rows, key=lambda s: s.brier) if rows else None
    return TournamentState(
        run_id=str(digest.get(DIGEST_RUN_ID_FIELD) or "") or None,
        rows_written=written,
        rows_skipped=skipped,
        folds=scores.folds,
        folds_empty=scores.empty,
        best_fold=None if best is None else best.fold,
        best_brier=None if best is None else best.brier,
        best_base_rate_brier=None if best is None else best.base_rate_brier,
        worst_fold=None if worst is None else worst.fold,
        worst_brier=None if worst is None else worst.brier,
        worst_base_rate_brier=None if worst is None else worst.base_rate_brier,
        reporting_currency=currency,
    )


def _micros(digest: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> int:
    """When this run was trained, in microseconds, the unit every store timestamp uses.

    **From the digest's own `created_at`, not from each fold's manifest.** Spec 74 says "from
    the manifest", and the digest carries the same instant written by the same trainer in the
    same run — so reading it here avoids opening one manifest per fold, which on the real
    archive is a file read per row to learn a number that is identical in all of them.

    A digest without it falls back to the **last fold's test window end**, which is the
    latest moment the run demonstrably knew about. Not `now`: the console orders the
    leaderboard by `trained_at`, and a clock read here would put an old run at the top of the
    table every time somebody re-ran the chain over it.
    """
    from datetime import UTC, datetime

    value = digest.get("created_at")
    if value is not None:
        moment = datetime.fromisoformat(str(value))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return int(moment.timestamp() * 1_000_000)
    ends = [int(entry["test_end_ts"]) for entry in entries if entry.get("test_end_ts")]
    if not ends:
        raise TournamentError(
            REASON_NO_DIGEST,
            "the digest records neither `created_at` nor any fold's `test_end_ts`, so its "
            "leaderboard rows would have no training time — and the console orders by "
            "exactly that.",
        )
    return max(ends) * 1_000_000


def _as_float_or_none(value: Any) -> float | None:
    """A reported metric, with a null kept null."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
