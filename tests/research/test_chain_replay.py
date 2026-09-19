"""Spec 131: the driver's schedule, fold switching and restart, with nothing real behind it.

These are the driver's own decisions, tested where they are made: when the next tick
is, which fold scores it, when the config switches, and that a minute is never skipped
while exposure exists. `tests/cli/test_research_backtest.py` runs the same driver over
the registered chains, the replay client and the paper broker, with no double.
"""

from __future__ import annotations

from typing import Any

import pytest

from acsoe.research.backtest import (
    ChainReplay,
    FoldWindow,
    closed_bar_open,
    fold_for_tick,
    next_tick_s,
    replay_bounds,
)

BAR = 900
MINUTE = 60
WEEK = 7 * 24 * 3600
T0 = 1_720_224_000  # 2024-07-06 00:00 UTC, fold 379's test start

FOLDS = (
    FoldWindow(fold=379, run_id="r-f379", test_start_s=T0, test_end_s=T0 + WEEK),
    FoldWindow(fold=380, run_id="r-f380", test_start_s=T0 + WEEK, test_end_s=T0 + 2 * WEEK),
)


def test_the_first_tick_is_the_close_of_the_first_bar_and_the_last_the_close_of_the_last() -> None:
    assert replay_bounds(FOLDS, bar_s=BAR) == (T0 + BAR, T0 + 2 * WEEK)


def test_a_gap_between_two_folds_is_refused() -> None:
    gapped = (FOLDS[0], FoldWindow(fold=381, run_id="x", test_start_s=T0 + WEEK + BAR, test_end_s=T0 + 2 * WEEK))
    with pytest.raises(RuntimeError, match="contiguous"):
        replay_bounds(gapped, bar_s=BAR)


def test_the_fold_is_the_one_holding_the_closed_bar() -> None:
    """The tick at fold 380's start closes fold 379's last bar, so fold 379 scores it."""
    assert closed_bar_open(T0 + WEEK, bar_s=BAR) == T0 + WEEK - BAR
    assert fold_for_tick(FOLDS, T0 + WEEK, bar_s=BAR).fold == 379
    assert fold_for_tick(FOLDS, T0 + WEEK + BAR, bar_s=BAR).fold == 380
    # A minute tick inside fold 380's first bar still belongs to the bar that closed last.
    assert fold_for_tick(FOLDS, T0 + WEEK + 5 * MINUTE, bar_s=BAR).fold == 379
    with pytest.raises(RuntimeError, match="0 folds"):
        fold_for_tick(FOLDS, T0, bar_s=BAR)


@pytest.mark.parametrize(
    ("last", "exposed", "expected"),
    [
        (None, False, T0 + BAR),
        (T0 + BAR, False, T0 + 2 * BAR),
        (T0 + BAR, True, T0 + BAR + MINUTE),
        (T0 + BAR + 14 * MINUTE, True, T0 + 2 * BAR),
        (T0 + BAR + 7 * MINUTE, False, T0 + 2 * BAR),
        (T0 + 2 * WEEK, False, None),
        (T0 + 2 * WEEK - MINUTE, True, T0 + 2 * WEEK),
    ],
)
def test_the_next_tick(last: int | None, exposed: bool, expected: int | None) -> None:
    assert (
        next_tick_s(last, exposed=exposed, start_s=T0 + BAR, end_s=T0 + 2 * WEEK, bar_s=BAR, loop_s=MINUTE)
        == expected
    )


class Harness:
    """Stands in for the orchestrator, the clock, the store and the config view."""

    def __init__(self, exposure: dict[int, bool]) -> None:
        self.exposure = exposure  # tick -> exposure after that tick
        self.now: int | None = None
        self.ticks: list[int] = []
        self.configs: list[tuple[int | None, str]] = []
        self.activations: list[int] = []
        self.records: list[dict[str, Any]] = []

    def tick(self) -> None:
        assert self.now is not None
        self.ticks.append(self.now)

    def set_clock(self, tick_s: int) -> None:
        self.now = tick_s

    def use(self, config: str) -> None:
        self.configs.append((self.now, config))

    def exposed(self) -> bool:
        return self.exposure.get(self.ticks[-1], False) if self.ticks else False

    def driver(self) -> ChainReplay:
        return ChainReplay(
            folds=FOLDS,
            bar_s=BAR,
            loop_s=MINUTE,
            tick=self.tick,
            set_clock=self.set_clock,
            use_config=self.use,
            config_for=lambda fold: f"config-{fold.fold}",
            exposed=self.exposed,
            activate=self.activations.append,
            record=lambda entry: self.records.append(dict(entry)),
        )


def test_a_minute_ticks_on_every_minute_with_exposure_and_on_none_without() -> None:
    """A position planted by the second bar close and closed eight minutes later: minute
    ticks on exactly those minutes, bar closes everywhere else."""
    opened, closed = T0 + 2 * BAR, T0 + 2 * BAR + 8 * MINUTE
    exposure = dict.fromkeys(range(opened, closed, MINUTE), True)
    harness = Harness(exposure)
    summary = harness.driver().run(stop_after_s=T0 + 5 * BAR)
    expected = [T0 + BAR, *range(opened, closed + MINUTE, MINUTE), T0 + 3 * BAR, T0 + 4 * BAR, T0 + 5 * BAR]
    assert harness.ticks == expected
    assert summary.minute_ticks == 8
    assert summary.bar_ticks == 5


def test_the_config_switches_at_the_fold_boundary_and_is_recorded() -> None:
    harness = Harness({})
    harness.driver().run(begin_s=T0 + WEEK - BAR, stop_after_s=T0 + WEEK + 2 * BAR)
    assert harness.configs == [(None, "config-379"), (T0 + WEEK, "config-380")]
    switches = [entry for entry in harness.records if entry["event"] == "fold_switch"]
    assert [(entry["tick_s"], entry["fold"]) for entry in switches] == [
        (T0 + WEEK - BAR, 379),
        (T0 + WEEK + BAR, 380),
    ]


def test_activate_is_written_once_before_the_first_tick_of_each_process() -> None:
    harness = Harness({})
    driver = harness.driver()
    driver.run(stop_after_s=T0 + 2 * BAR)
    assert harness.activations == [T0 + BAR]
    driver.run(resume_after_s=T0 + 2 * BAR, stop_after_s=T0 + 4 * BAR)
    assert harness.activations == [T0 + BAR, T0 + 3 * BAR]
    starts = [entry["event"] for entry in harness.records if entry["event"] in ("start", "restart")]
    assert starts == ["start", "restart"]


def test_a_resume_continues_on_the_minute_grid_when_exposure_remains() -> None:
    """Killed at a minute tick with a position open: the next tick is the next minute,
    read from the store's exposure, never the next bar."""
    harness = Harness({})
    harness.exposure = {}
    driver = harness.driver()
    harness.ticks = [T0 + BAR + 3 * MINUTE]
    harness.exposure[T0 + BAR + 3 * MINUTE] = True
    driver.run(resume_after_s=T0 + BAR + 3 * MINUTE, max_ticks=1)
    assert harness.ticks[-1] == T0 + BAR + 4 * MINUTE


def test_begin_aligns_to_a_bar_close_inside_the_window() -> None:
    harness = Harness({})
    harness.driver().run(begin_s=T0 + WEEK + 1, stop_after_s=T0 + WEEK + 2 * BAR)
    assert harness.ticks == [T0 + WEEK + BAR, T0 + WEEK + 2 * BAR]
    with pytest.raises(ValueError, match="outside the window"):
        harness.driver().run(begin_s=T0 - WEEK)


def test_max_ticks_stops_the_run_unfinished() -> None:
    harness = Harness({})
    summary = harness.driver().run(max_ticks=3)
    assert summary.ticks == 3
    assert summary.finished is False
    assert harness.ticks == [T0 + BAR, T0 + 2 * BAR, T0 + 3 * BAR]


def test_a_tick_that_does_not_divide_the_bar_is_refused() -> None:
    with pytest.raises(ValueError, match="divide"):
        ChainReplay(
            folds=FOLDS, bar_s=BAR, loop_s=7 * MINUTE, tick=lambda: None, set_clock=lambda _s: None,
            use_config=lambda _c: None, config_for=lambda _f: None, exposed=lambda: False,
            activate=lambda _s: None, record=lambda _e: None,
        )
