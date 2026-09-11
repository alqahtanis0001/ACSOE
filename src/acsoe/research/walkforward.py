"""The purged, embargoed walk-forward splitter. Spec 53.

Invariant 10: *walk-forward folds are purged and embargoed; overlapping label windows
must not straddle a train/test boundary.*

## Why this is the most dangerous module in the project

A splitter that forgets to purge produces a model that looks excellent and is worthless,
and **nothing fails to say so**. There is no crash, no red test and no operator-visible
symptom. A backtest run on leaked folds reports a Sharpe the live system will never see,
the Phase 7 promotion gate passes it, and the first honest number arrives from a real
account.

The defect is invisible to every end-to-end check, and the reason is worth stating
exactly: **the fold *indices* do not overlap whether or not the purge ran.** The leak is
in the **label windows**. A decision bar comfortably inside the training period can have
a label built entirely from bars inside the test period, and only a test that constructs
such a row on purpose can see it.

## Purge

Every label carries ``label_window_end_ts`` — the instant its outcome became known.
`research/labelling.py` emits it: the touch for a barrier that was hit, the horizon for
a timeout. **A training row whose window ends at or after the start of the test window is
dropped.**

Purging on ``decision_ts`` instead is the most plausible wrong implementation, and it
passes any test that does not deliberately place a decision bar early and its label
window late.

## Embargo

After the test window, training rows are dropped for a further ``backtest.embargo_bars``
bars before training rows are allowed back in. This exists because serial correlation
carries information across the boundary even where no label window literally straddles
it, so purging alone is not enough.

**There is no default for ``backtest.embargo_bars``.** It is read from config and a
missing key raises. An embargo that quietly defaulted to zero is precisely the defect
this module exists to prevent, and it would be indistinguishable from a working one in
every output.

## The training set is on both sides of the test window

Spec 53 states the embargo as "after the test window, drop training rows for a further
``embargo_bars`` bars **before allowing training rows back in**", which only means
anything if training rows can follow the test window. So a fold's training set is every
row outside the test window and within ``backtest.training_window_days`` of it on either
side, purged and embargoed. That is purged k-fold in the López de Prado sense, laid over
rolling test windows, and it is the lead's reading rather than the implementer's.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

__all__ = [
    "DECISION_TS_FIELD",
    "KEY_EMBARGO_BARS",
    "KEY_RETRAIN_INTERVAL_DAYS",
    "KEY_TRAINING_WINDOW_DAYS",
    "LABEL_WINDOW_END_FIELD",
    "Fold",
    "WalkForwardSettings",
    "purged_walk_forward",
    "read_settings",
]

KEY_TRAINING_WINDOW_DAYS: Final = "backtest.training_window_days"
KEY_RETRAIN_INTERVAL_DAYS: Final = "backtest.retrain_interval_days"
KEY_EMBARGO_BARS: Final = "backtest.embargo_bars"

#: The two fields a label must carry for a fold to be built from it. Both come from
#: `research/labelling.py`, and the second is the whole point of this module.
DECISION_TS_FIELD: Final = "decision_ts"
LABEL_WINDOW_END_FIELD: Final = "label_window_end_ts"

SECONDS_PER_DAY: Final = 86_400


class _Config(Protocol):
    """Structural, not imported. Invariant 10 keeps research out of the live path."""

    def get(self, dotted_key: str, /) -> Any: ...


class MissingSettingError(ValueError):
    """A walk-forward setting is absent or unusable.

    Raised rather than defaulted. `Config.get` already raises on a missing key, and this
    covers the null case the lead writes for a threshold the operator has not chosen.
    """


@dataclass(frozen=True, slots=True)
class WalkForwardSettings:
    training_window_days: int
    retrain_interval_days: int
    embargo_bars: int

    @property
    def training_window_s(self) -> int:
        return self.training_window_days * SECONDS_PER_DAY

    @property
    def test_window_s(self) -> int:
        return self.retrain_interval_days * SECONDS_PER_DAY

    def embargo_s(self, interval_s: int) -> int:
        """The embargo span in seconds. Stated in **bars**, like the timeout barrier."""
        return self.embargo_bars * interval_s


def _positive_int(value: Any, key: str) -> int:
    if value is None:
        raise MissingSettingError(
            f"config key `{key}` is null. This module has no default for it: an embargo "
            "or a window that silently defaults is indistinguishable from a working one "
            "in every output the backtest produces."
        )
    number = int(value)
    if number <= 0:
        raise MissingSettingError(f"config key `{key}` is {number}; it must be positive")
    return number


def read_settings(config: _Config) -> WalkForwardSettings:
    """The three settings from config. None of them has a default here."""
    return WalkForwardSettings(
        training_window_days=_positive_int(
            config.get(KEY_TRAINING_WINDOW_DAYS), KEY_TRAINING_WINDOW_DAYS
        ),
        retrain_interval_days=_positive_int(
            config.get(KEY_RETRAIN_INTERVAL_DAYS), KEY_RETRAIN_INTERVAL_DAYS
        ),
        embargo_bars=_positive_int(config.get(KEY_EMBARGO_BARS), KEY_EMBARGO_BARS),
    )


@dataclass(frozen=True, slots=True)
class Fold:
    """One train/test split, with the counts that say whether the purge did anything.

    ``purged_count`` and ``embargoed_count`` are **public, not internal**. A count of
    zero purged rows on a dataset with overlapping label windows is the symptom of the
    bug this module exists to prevent, and it is visible only if the number is reported.

    ``train_index`` and ``test_index`` are positional indices into the rows the caller
    passed, so a caller can recover the rows themselves without this module knowing
    anything about their type.
    """

    fold_index: int
    train_start_ts: int
    train_end_ts: int
    test_start_ts: int
    test_end_ts: int
    train_index: tuple[int, ...]
    test_index: tuple[int, ...]
    purged_count: int
    embargoed_count: int
    out_of_window_count: int
    """Rows outside the fold's training span entirely. Not a leak; reported so that
    `purged` and `embargoed` cannot absorb an unrelated exclusion and look larger."""

    @property
    def is_empty(self) -> bool:
        """A fold with no training rows or no test rows. **Reported, never dropped.**

        Spec 53 forbids silently discarding one: a run that quietly produced four folds
        where the caller expected twelve reports metrics over a third of the data with
        nothing anywhere saying so.
        """
        return not self.train_index or not self.test_index

    def summary(self) -> dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "test_start_ts": self.test_start_ts,
            "test_end_ts": self.test_end_ts,
            "train_rows": len(self.train_index),
            "test_rows": len(self.test_index),
            "purged": self.purged_count,
            "embargoed": self.embargoed_count,
            "out_of_window": self.out_of_window_count,
            "empty": self.is_empty,
        }


def _rows_of(labels: Any) -> list[Mapping[str, Any]]:
    """The labels as plain mappings, whether a frame or a sequence was passed."""
    to_dicts = getattr(labels, "to_dicts", None)
    if callable(to_dicts):
        rows: list[Mapping[str, Any]] = list(to_dicts())
        return rows
    if isinstance(labels, Sequence):
        for index, row in enumerate(labels):
            if not isinstance(row, Mapping):
                raise TypeError(f"labels[{index}] is a {type(row).__name__}, not a mapping")
        return list(labels)
    raise TypeError("labels must be a polars frame or a sequence of mappings")


def _required(row: Mapping[str, Any], field: str, index: int) -> int:
    if field not in row or row[field] is None:
        raise MissingSettingError(
            f"labels[{index}] carries no `{field}`. The splitter purges on the label "
            "window end; without it a fold cannot be purged at all, and a splitter that "
            "fell back to the decision bar would produce leaked folds that look correct."
        )
    return int(row[field])


def _one_fold(
    rows: Sequence[Mapping[str, Any]],
    *,
    fold_index: int,
    test_start_ts: int,
    test_end_ts: int,
    settings: WalkForwardSettings,
    interval_s: int,
) -> Fold:
    embargo_s = settings.embargo_s(interval_s)
    embargo_end = test_end_ts + embargo_s
    train_start = test_start_ts - settings.training_window_s
    train_end = test_end_ts + settings.training_window_s

    train: list[int] = []
    test: list[int] = []
    purged = 0
    embargoed = 0
    out_of_window = 0

    for index, row in enumerate(rows):
        decision_ts = _required(row, DECISION_TS_FIELD, index)
        window_end = _required(row, LABEL_WINDOW_END_FIELD, index)

        if test_start_ts <= decision_ts < test_end_ts:
            test.append(index)
            continue
        if not (train_start <= decision_ts <= train_end):
            out_of_window += 1
            continue
        if decision_ts < test_start_ts:
            # **Purged on the label window end, never on the decision bar.** A decision
            # bar two days inside the training period whose label was built from bars
            # inside the test period is the leak, and its `decision_ts` says nothing
            # about that.
            if window_end >= test_start_ts:
                purged += 1
                continue
            train.append(index)
            continue
        # After the test window. Serial correlation carries information across the
        # boundary even where no label window literally straddles it, so a bounded span
        # is dropped before training rows are allowed back in.
        if decision_ts < embargo_end:
            embargoed += 1
            continue
        train.append(index)

    return Fold(
        fold_index=fold_index,
        train_start_ts=train_start,
        train_end_ts=train_end,
        test_start_ts=test_start_ts,
        test_end_ts=test_end_ts,
        train_index=tuple(train),
        test_index=tuple(test),
        purged_count=purged,
        embargoed_count=embargoed,
        out_of_window_count=out_of_window,
    )


def purged_walk_forward(
    labels: Any,
    *,
    config: _Config,
    interval_s: int,
    test_start_ts: int | None = None,
    test_end_ts: int | None = None,
) -> list[Fold]:
    """Folds over ``labels``, purged and embargoed.

    ``labels`` is the frame `research/labelling.py` produces, or any sequence of
    mappings carrying ``decision_ts`` and ``label_window_end_ts``.

    Pass ``test_start_ts`` and ``test_end_ts`` to build **one** named fold — that is what
    a test constructing a straddling label window does, and it is the only way to place
    a row deliberately on either side of a boundary. Omit both and the test windows roll
    forward from the first decision bar by ``backtest.retrain_interval_days``.

    **No fold is dropped for coming out empty.** Spec 53 says to report it, and
    :attr:`Fold.is_empty` is how: a run that quietly produced four folds where the caller
    expected twelve reports metrics over a third of the data with nothing saying so.

    Reads no clock. Fold boundaries come from the data's own timestamps.
    """
    settings = read_settings(config)
    if interval_s <= 0:
        raise MissingSettingError("interval_s must be positive")
    # Argument validation **before** the empty-rows return, and the order is a fix
    # rather than a preference: with it the other way round, a malformed call raised
    # when there were rows and silently returned `[]` when there were not. "There were
    # no labels to split" and "this call is malformed" are different facts, and a
    # caller that had filtered a frame down to one pair would have read the second as
    # the first.
    if (test_start_ts is None) != (test_end_ts is None):
        raise MissingSettingError(
            "pass both test_start_ts and test_end_ts, or neither. Half a window is a "
            "boundary this module would have to invent the other side of."
        )
    rows = _rows_of(labels)
    if not rows:
        return []
    if test_start_ts is not None and test_end_ts is not None:
        return [
            _one_fold(
                rows,
                fold_index=0,
                test_start_ts=test_start_ts,
                test_end_ts=test_end_ts,
                settings=settings,
                interval_s=interval_s,
            )
        ]

    stamps = sorted(_required(row, DECISION_TS_FIELD, i) for i, row in enumerate(rows))
    first, last = stamps[0], stamps[-1]
    # The first test window opens once a full training window exists behind it. Starting
    # earlier would produce folds trained on a few days and tested on a week, and their
    # metrics would be pooled with the rest as though they were comparable.
    start = first + settings.training_window_s
    folds: list[Fold] = []
    index = 0
    while start <= last:
        folds.append(
            _one_fold(
                rows,
                fold_index=index,
                test_start_ts=start,
                test_end_ts=start + settings.test_window_s,
                settings=settings,
                interval_s=interval_s,
            )
        )
        start += settings.test_window_s
        index += 1
    return folds
