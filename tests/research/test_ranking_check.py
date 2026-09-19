"""Spec 144's last check: the simulated ranking against the §4 grid's choice on the same bar.

The files are constructed in the shapes the Phase 5 study and the trainer wrote them, with the
numbers chosen so each rule of the grid's choice has a case of its own. The real study files are
gitignored runtime output; `grid_order` was held to `q_emrank.py`'s own selection code on 60
sampled bars of the real window (build log, 2026-09-19), which is the check a constructed file
cannot make.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import require_module

np = require_module("numpy", reason="numpy is not installed")
pl = require_module("polars", reason="polars is not installed")

from acsoe.modelling.ranking import RankedPair, Ranking  # noqa: E402
from acsoe.research.ranking_check import compare, grid_order  # noqa: E402

BAR = 1_730_000_700
FOLD = 390

#: pair -> (expected move, DI, anomaly score). Thresholds below: DI 1.0, anomaly 0.5 (each the
#: 0.99 quantile of a distribution built to put it there).
ROWS = {
    "AAAUSD": (0.010, 0.90, 0.40),  # passes
    "BBBUSD": (0.030, 1.20, 0.40),  # best move, DI above its threshold
    "CCCUSD": (0.025, 0.90, 0.60),  # second best, anomaly above its threshold
    "DDDUSD": (0.020, float("nan"), 0.40),  # an incomplete vector: the study left DI NaN
    "EEEUSD": (0.015, 1.00, 0.50),  # both exactly on their thresholds: passes
    "FFFUSD": (0.015, 0.50, 0.10),  # ties EEEUSD on move: the name decides
}


def distribution_with_quantile(value: float) -> object:
    """1,001 values whose 0.99 quantile is exactly ``value``."""
    return np.concatenate([np.full(990, value - 1.0), np.full(11, value)])


@pytest.fixture
def files(tmp_path: Path) -> tuple[Path, Path]:
    oos = pl.DataFrame(
        {
            "pair": [*ROWS, "AAAUSD"],
            "decision_ts": [BAR] * len(ROWS) + [BAR + 900],
            "fold_index": [FOLD] * (len(ROWS) + 1),
            "expected_move_pct": [*(move for move, _di, _an in ROWS.values()), 0.5],
        }
    )
    oos_path = tmp_path / "oos.parquet"
    oos.write_parquet(oos_path)
    study = tmp_path / "study"
    study.mkdir()
    pl.DataFrame(
        {
            "pair": list(ROWS),
            "decision_ts": [BAR] * len(ROWS),
            "fold_index": [FOLD] * len(ROWS),
            "di": [di for _move, di, _an in ROWS.values()],
            "anomaly_score": [an for _move, _di, an in ROWS.values()],
        }
    ).write_parquet(study / f"fold_{FOLD:03d}.parquet")
    np.savez(study / f"excl_fold_{FOLD:03d}.npz", di_distribution=distribution_with_quantile(1.0))
    np.savez(
        study / f"fold_{FOLD:03d}.npz",
        anomaly_train_scores=distribution_with_quantile(0.5),
        di_distribution=distribution_with_quantile(99.0),
    )
    return oos_path, study


def order(files: tuple[Path, Path]) -> tuple[int, list[object]]:
    oos_path, study = files
    return grid_order(
        BAR, oos_path=oos_path, study_dir=study, di_percentile=0.99, anomaly_percentile=0.99
    )


def test_the_grid_ranks_by_expected_move_among_the_pairs_both_gates_pass(
    files: tuple[Path, Path],
) -> None:
    """Every rule of `q_emrank.py`'s choice in one bar: DI above its line, anomaly above its
    line and a NaN are each left out; a value exactly on its line is kept; a tie on move goes
    to the name; the excluded DI is the **excluded** distribution's, not the row-only one's."""
    fold, ranked = order(files)
    assert fold == FOLD
    assert [entry.pair for entry in ranked] == ["EEEUSD", "FFFUSD", "AAAUSD"]


def test_a_bar_the_out_of_sample_file_does_not_hold_is_refused(
    files: tuple[Path, Path],
) -> None:
    oos_path, study = files
    with pytest.raises(ValueError, match=r"under folds \[\]"):
        grid_order(
            BAR + 1, oos_path=oos_path, study_dir=study, di_percentile=0.99,
            anomaly_percentile=0.99,
        )


def ranked(*pairs: str) -> Ranking:
    return Ranking(
        ranked=tuple(
            RankedPair(pair=pair, expected_move_pct=0.0, p_target=0.0, p_stop=0.0,
                       p_timeout=1.0, di=0.0, anomaly_score=0.0)
            for pair in pairs
        ),
        excluded=(),
    )


def test_agreement_is_judged_within_engine_7s_universe(files: tuple[Path, Path]) -> None:
    """The grid's first choice was EEEUSD. Engine 7's universe filter removed it, so the pair
    that must agree is the grid's first choice among the pairs engine 7 saw, and the pair it
    never saw is named as the explanation."""
    fold, grid = order(files)
    verdict = compare(BAR, fold, ranked("FFFUSD"), grid, universe={"AAAUSD", "FFFUSD"})
    assert verdict.grid_choice == "EEEUSD"
    assert verdict.grid_choice_in_universe == "FFFUSD"
    assert verdict.outside_universe == ("EEEUSD",)
    assert verdict.agrees is True


def test_a_different_choice_inside_the_universe_is_a_disagreement(
    files: tuple[Path, Path],
) -> None:
    fold, grid = order(files)
    verdict = compare(BAR, fold, ranked("AAAUSD"), grid, universe=set(ROWS))
    assert verdict.grid_choice_in_universe == "EEEUSD"
    assert verdict.outside_universe == ()
    assert verdict.agrees is False


def test_no_choice_on_either_side_agrees_and_one_side_alone_does_not(
    files: tuple[Path, Path],
) -> None:
    fold, grid = order(files)
    assert compare(BAR, fold, ranked(), [], universe=()).agrees is True
    assert compare(BAR, fold, ranked(), grid, universe=set(ROWS)).agrees is False
