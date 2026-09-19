"""Does the simulated ranking choose what the §4 grid chose? Spec 144's last check.

`docs/dataset/phase-7-findings.md` §4 is the evidence the ranking amendment rests on. Its
expected-move column was computed offline by
`docs/dataset/phase-7-recon-2026-09-19/scripts/q_emrank.py`: on every bar, among the pairs whose
anomaly score and DI were finite and at or under the fold's thresholds, the pair with the
highest ``expected_move_pct``, ties by name. **If the simulated engine 7 chooses differently on
the same bar from the same fold's artefacts, the grid no longer describes the run**, and the
lead is told before spec 143 launches. The rehearsal (spec 142) runs this over its day.

This module restates the script's choice from the same files the script read, and compares it
with a :class:`~acsoe.modelling.ranking.Ranking`. It reads and never writes.

What the grid read, per bar:

* the source run's out-of-sample file: the pairs present on the bar, their fold and their
  ``expected_move_pct`` as the trainer computed it;
* the Phase 5 study's ``fold_NNN.parquet``: each test row's DI (``di``) and anomaly score;
* the thresholds, ``np.quantile`` at the configured percentile of the study's excluded DI
  distribution (``excl_fold_NNN.npz``) and of its anomaly training scores (``fold_NNN.npz``) —
  the same two quantiles spec 135 writes into the assembled run directories.

**Where the two may legitimately differ, and how this says so.** The grid ranked every pair the
archive held on the bar. Engine 7 ranks only the pairs its universe filter kept, on pair rules,
spread and balance, which the grid never modelled. So the comparison is made twice: against the
grid's first choice outright, and against its first choice **among the pairs engine 7 ranked
or excluded**, which is the one that must agree. A disagreement on the second is the stop.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from acsoe.modelling.ranking import Ranking

__all__ = ["Comparison", "GridChoice", "compare", "grid_order"]

#: The out-of-sample columns the grid read.
_OOS_COLUMNS: Final[tuple[str, ...]] = ("pair", "decision_ts", "fold_index", "expected_move_pct")


@dataclass(frozen=True, slots=True)
class GridChoice:
    """One pair the grid would have ranked on a bar, with the numbers it ranked on."""

    pair: str
    expected_move_pct: float
    di: float
    anomaly_score: float


@dataclass(frozen=True, slots=True)
class Comparison:
    """The verdict for one bar. ``agrees`` is the one that decides a stop."""

    decision_ts: int
    fold_index: int
    engine_choice: str | None
    grid_choice: str | None
    grid_choice_in_universe: str | None
    #: Pairs the grid would have preferred to engine 7's choice that engine 7 never saw,
    #: because its universe filter removed them. Explains a difference on ``grid_choice``.
    outside_universe: tuple[str, ...]

    @property
    def agrees(self) -> bool:
        return self.engine_choice == self.grid_choice_in_universe


def grid_order(
    decision_ts: int,
    *,
    oos_path: Path,
    study_dir: Path,
    di_percentile: float,
    anomaly_percentile: float,
) -> tuple[int, list[GridChoice]]:
    """``(fold_index, order)``: the grid's ranking on one bar, first choice first.

    Refuses a bar the out-of-sample file does not hold, or holds under more than one fold,
    rather than comparing against nothing.
    """
    bar = (
        pl.scan_parquet(oos_path)
        .filter(pl.col("decision_ts") == int(decision_ts))
        .select(list(_OOS_COLUMNS))
        .collect()
    )
    folds = sorted({int(value) for value in bar["fold_index"]})
    if len(folds) != 1:
        raise ValueError(
            f"bar {decision_ts} is under folds {folds} in {oos_path.name}; the grid ranked each "
            "bar within exactly one fold"
        )
    fold_index = folds[0]
    scores = pl.read_parquet(
        study_dir / f"fold_{fold_index:03d}.parquet",
        columns=["pair", "decision_ts", "di", "anomaly_score"],
    ).filter(pl.col("decision_ts") == int(decision_ts))
    with np.load(study_dir / f"excl_fold_{fold_index:03d}.npz") as payload:
        di_threshold = float(np.quantile(payload["di_distribution"], di_percentile))
    with np.load(study_dir / f"fold_{fold_index:03d}.npz") as payload:
        anomaly_threshold = float(np.quantile(payload["anomaly_train_scores"], anomaly_percentile))

    joined = bar.join(scores, on=["pair", "decision_ts"], how="left")
    kept: list[GridChoice] = []
    for row in joined.iter_rows(named=True):
        anomaly, di = row["anomaly_score"], row["di"]
        if anomaly is None or not math.isfinite(anomaly) or anomaly > anomaly_threshold:
            continue
        if di is None or not math.isfinite(di) or di > di_threshold:
            continue
        kept.append(
            GridChoice(
                pair=str(row["pair"]),
                expected_move_pct=float(row["expected_move_pct"]),
                di=float(di),
                anomaly_score=float(anomaly),
            )
        )
    kept.sort(key=lambda entry: (-entry.expected_move_pct, entry.pair))
    return fold_index, kept


def compare(
    decision_ts: int,
    fold_index: int,
    ranking: Ranking,
    order: Sequence[GridChoice],
    universe: Iterable[str],
) -> Comparison:
    """Engine 7's choice on a bar against the grid's, within engine 7's universe.

    :param ranking: what :func:`~acsoe.modelling.ranking.rank_by_expected_move` returned on
        the bar.
    :param universe: the pairs engine 7 handed the ranking, ranked or excluded.
    """
    seen = set(universe)
    engine_choice = ranking.ranked[0].pair if ranking.ranked else None
    grid_choice = order[0].pair if order else None
    inside = next((entry.pair for entry in order if entry.pair in seen), None)
    outside: list[str] = []
    for entry in order:
        if entry.pair == inside:
            break
        if entry.pair not in seen:
            outside.append(entry.pair)
    return Comparison(
        decision_ts=int(decision_ts),
        fold_index=int(fold_index),
        engine_choice=engine_choice,
        grid_choice=grid_choice,
        grid_choice_in_universe=inside,
        outside_universe=tuple(outside),
    )
