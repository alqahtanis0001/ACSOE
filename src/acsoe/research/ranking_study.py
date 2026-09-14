"""Spec 75 — the candidate-ranking study, for the operator's ruling on engine 7.

For every feature, in both directions: if the pair ranked first by that feature on each
decision bar were the one taken, what happened to it? Reported beside the **alphabetical**
choice that stands in today, which is the control.

## It recommends nothing

This module produces a table. Spec 75 is explicit that no feature is recommended in the
report; the recommendation, if any, is the lead's in the plan and the decision is the
operator's. So there is no ranking of the rankings here, no "best" key, and no ordering of
the rows by any metric — the rows come out in `FEATURE_NAMES` order with the control first,
because an ordering by outcome *is* a recommendation with the word left off.

## Why the control is the whole point

`scout.rank_feature` is absent and engine 7 ranks alphabetically meanwhile. That is not a
neutral baseline — alphabetical order is a fixed, arbitrary preference for the pairs whose
names sort early — but it is what the system does today, and a feature that does not beat it
is a feature that changes nothing. Every row is therefore reported next to it, over the same
bars.

## It takes the pair engine 7 would take

The study is only evidence if its choice on each bar is the choice `rank_universe` in
`engines/scout/contracts.py` would make from the same values, and it cannot import that
function (architecture invariant 5: `research/` never imports the live path). So the rule is
restated here and a test holds the two together bar by bar, on values including NaN, ±inf,
null and ties:

* by the feature's value, in the configured direction;
* **a non-finite value is no value** — null, NaN and ±inf alike — and a pair with no value
  sorts after every pair that has one, in both directions;
* ties, and the pairs with no value, in pair-name order ascending, in both directions.

The second rule is the one a dataframe sort gets wrong by default. `modelling/features.py`
writes **NaN**, not null, for a lookback that has not filled, and polars orders NaN as the
largest float: a descending sort with `nulls_last` takes the NaN pair first. On the real
archive that pair is the new listing or the thin pair with holes, so every descending row would
have measured "take the pair we know least about" under a feature's name.

## Every count carries its effective size, and says how much of it the feature decided

Consecutive decision bars share almost all of a 48-bar label window, so `bars` overstates the
independent outcomes by a large factor. Each row reports `effective_bars` beside `bars`: the
sum of the taken rows' own uniqueness weights (spec 59 decision 5, as the operator amended it:
the effective sample size beside **every** row count). It discounts overlap within a pair and
not the correlation between pairs, so it is an upper bound on the independent outcomes, not an
estimate of them.

And a feature only chooses on a bar where it separates the pairs. `no_value_bars` counts bars
where no pair had a value and `tied_bars` bars where the top two tied; on both, the pair was
taken in name order, which is the control's choice. A feature whose rate differs from the
control's over bars it mostly did not decide is the control under another name.

## One feature at a time, out of sample only

No composite score: a formula nobody asked for is a decision nobody made. And only the
out-of-sample file, joined to the dataset for the feature values — ranking by a feature the
model was fitted on, over rows it was fitted on, would measure the fit rather than the choice.
**The join must cover every out-of-sample row exactly once**, or the study refuses: a dataset
from another build joins a subset silently, and a table over an unknown subset of the run it
names is a table about some other sample.

## The break-even column is a formula, not a number

Spec 75 as amended 2026-09-13: **no break-even rate is computed here.** Break-even is a
function of friction — live fees, the measured spread, slippage — and `config/default.yaml`
carries none of them by design, because nothing the exchange can tell us is in that file. The
reference figures in `trading-invariants.md` are marked for sanity-checking only and never for
use in code. So the report carries the **formula** and the barrier sizes it is built from:

    break_even = (stop_pct + friction) / (target_pct + stop_pct)

and the reader supplies the friction from a live fee tier.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import polars as pl

from acsoe.modelling.features import FEATURE_NAMES

__all__ = [
    "ALPHABETICAL",
    "DIRECTIONS",
    "STUDY_COLUMNS",
    "RankingStudyError",
    "build_report",
    "chosen_pairs",
    "write_report",
]


class RankingStudyError(ValueError):
    """Inputs this study will not run on. Every message names which."""


#: The control's name in the `feature` column. Not a feature, and named so it cannot be
#: mistaken for one when the table is read or sorted.
ALPHABETICAL: Final = "(alphabetical control)"

#: Both, for every feature, because which end of a feature is the interesting one is exactly
#: what nobody knows yet. A study that guessed the direction would be the recommendation it
#: is forbidden from making, one layer down.
DIRECTIONS: Final[tuple[str, ...]] = ("descending", "ascending")

#: What each row reports. Fixed here so the JSON, the summary table and the tests cannot
#: disagree about the shape. Every count sits beside its effective size.
STUDY_COLUMNS: Final[tuple[str, ...]] = (
    "feature",
    "direction",
    "bars",
    "effective_bars",
    "no_value_bars",
    "tied_bars",
    "target_rate",
    "stop_rate",
    "timeout_rate",
    "mean_return_pct",
    "di_refused_rate",
    "buy_bars",
    "buy_effective_bars",
    "buy_target_rate",
)

_LABELS: Final[tuple[str, ...]] = ("target", "stop", "timeout")

#: Read from the out-of-sample file. `di` is there to tell a run with no DI fitted from a run
#: whose DI never refused, and `weight` for the effective sizes.
_OOS_COLUMNS: Final[tuple[str, ...]] = (
    "pair",
    "decision_ts",
    "label",
    "return_pct",
    "is_buy",
    "di",
    "di_refused",
    "weight",
)


def build_report(
    oos: pl.DataFrame,
    dataset: pl.DataFrame,
    *,
    config: Any,
    features: Sequence[str] = FEATURE_NAMES,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The whole study, as the structure that is written to `docs/dataset/`.

    :param oos: spec 67's out-of-sample file. Out of sample **only**: ranking by a feature
        the model was fitted on, over rows it was fitted on, measures the fit.
    :param dataset: the same run's dataset, for the feature values. The out-of-sample file
        carries what the predictor *said* and not what it *saw*.
    """
    eligible = _bars_with_a_choice(_joined(oos, dataset, features))
    if eligible.height == 0:
        raise RankingStudyError(
            "no decision bar carries two or more pairs, so there is nothing to rank. A "
            "ranking study over a single-pair run compares every choice against itself."
        )
    # A run trained without `prediction.di_percentile` writes `di: null` and
    # `di_refused: false` on every row. Averaging that gives 0.0, which reads as "the DI never
    # refused" when nothing was measured, so the rate is null for such a run.
    di_fitted = bool(eligible["di"].is_not_null().any())

    rows: list[dict[str, Any]] = [
        _row(eligible, ALPHABETICAL, "ascending", by_pair=True, di_fitted=di_fitted)
    ]
    for name in features:
        for direction in DIRECTIONS:
            rows.append(_row(eligible, name, direction, by_pair=False, di_fitted=di_fitted))

    target_pct = float(config.get("barriers.target_pct"))
    stop_pct = float(config.get("barriers.stop_pct"))
    return {
        "meta": {
            "measured_on": datetime.now(UTC).date().isoformat(),
            "method": (
                "acsoe.research.ranking_study.build_report over one training run's "
                "out-of-sample file joined to its dataset: on every decision bar carrying "
                "two or more pairs, the pair ranked first by each feature in each direction "
                "is taken, and its realised label is counted. The choice is engine 7's "
                "`rank_universe` rule: a non-finite value (null, NaN, inf) is no value and "
                "sorts after every valued pair in both directions, and ties and valueless "
                "pairs go in pair-name order"
            ),
            "bars": int(eligible["decision_ts"].n_unique()),
            "rows": int(eligible.height),
            "pairs": sorted({str(value) for value in eligible["pair"].unique()}),
            "features": len(features),
            "directions": list(DIRECTIONS),
            "control": ALPHABETICAL,
            "di_fitted": di_fitted,
            "recommends": None,
            "effective_bars_note": (
                "effective_bars is the sum of the taken rows' own uniqueness weights (spec 59 "
                "decision 5). It discounts label-window overlap within a pair and not the "
                "correlation between pairs, so it is an upper bound on independent outcomes."
            ),
            "decided_note": (
                "no_value_bars: bars where no pair had a finite value for the feature. "
                "tied_bars: bars where the top two pairs had the same value. On both, the "
                "pair was taken in name order, which is the control's choice."
            ),
            "note": (
                "No feature is recommended here and the rows are in feature order, not in "
                "outcome order: an ordering by outcome is a recommendation with the word "
                "left off. Spec 75 — the operator rules."
            ),
            **dict(provenance or {}),
        },
        "break_even": {
            "formula": "(stop_pct + friction) / (target_pct + stop_pct)",
            "target_pct": target_pct,
            "stop_pct": stop_pct,
            "friction": None,
            "note": (
                "The friction is deliberately null. Break-even is a function of live fees, "
                "the measured spread and slippage; config/default.yaml carries none of them "
                "because nothing the exchange can tell us belongs in that file, and the "
                "reference figures in trading-invariants.md are for sanity-checking only "
                "and never for use in code. The reader supplies the friction."
            ),
        },
        "columns": list(STUDY_COLUMNS),
        "rankings": rows,
    }


def chosen_pairs(
    oos: pl.DataFrame, dataset: pl.DataFrame, *, feature: str | None, direction: str
) -> dict[int, str]:
    """The pair this study takes on every bar with a choice, `{decision_ts: pair}`.

    `feature=None` is the alphabetical control. Public so the rule can be held against
    `rank_universe` bar by bar from outside `research/`, through exactly the preparation
    `build_report` uses.
    """
    features = () if feature is None else (feature,)
    eligible = _bars_with_a_choice(_joined(oos, dataset, features))
    taken = _grouped(
        eligible, feature or ALPHABETICAL, direction, by_pair=feature is None
    ).first()
    return {int(ts): str(pair) for ts, pair in zip(taken["decision_ts"], taken["pair"], strict=True)}


def write_report(report: Mapping[str, Any], directory: Path) -> Path:
    """Write the study to `docs/dataset/ranking-study-<date>.json` and return the path."""
    directory.mkdir(parents=True, exist_ok=True)
    measured = str((report.get("meta") or {}).get("measured_on") or "undated")
    path = directory / f"ranking-study-{measured}.json"
    path.write_bytes(
        json.dumps(report, sort_keys=True, indent=2, default=str).encode("utf-8") + b"\n"
    )
    return path


# --------------------------------------------------------------------------- #
# The arithmetic
# --------------------------------------------------------------------------- #


def _joined(
    oos: pl.DataFrame, dataset: pl.DataFrame, features: Sequence[str]
) -> pl.DataFrame:
    """Out-of-sample rows with their feature values, non-finite values nulled.

    Refuses when anything is absent, and when the join does not cover every out-of-sample row
    exactly once.
    """
    absent = [name for name in _OOS_COLUMNS if name not in oos.columns]
    if absent:
        raise RankingStudyError(
            "the out-of-sample file is missing " + ", ".join(absent) + ". This study reads "
            "what the predictor said and what actually happened, and both live there."
        )
    missing_features = [name for name in features if name not in dataset.columns]
    if missing_features:
        raise RankingStudyError(
            "the dataset is missing " + ", ".join(missing_features[:8])
            + ". The feature values come from the dataset because the out-of-sample file "
            "carries what the predictor said rather than what it saw."
        )
    values = [
        pl.when(pl.col(name).cast(pl.Float64).is_finite())
        .then(pl.col(name).cast(pl.Float64))
        .otherwise(None)
        .alias(name)
        for name in features
    ]
    joined = oos.select(_OOS_COLUMNS).join(
        dataset.select(["pair", "decision_ts", *features]).with_columns(values),
        on=["pair", "decision_ts"],
        how="inner",
    )
    if joined.height != oos.height:
        raise RankingStudyError(
            f"the dataset joins {joined.height} row(s) to an out-of-sample file of "
            f"{oos.height}. Every out-of-sample row must find its feature values exactly "
            "once; a dataset from another build, another pair set or another date range joins "
            "a subset (or repeats rows), and the table would describe a sample other than the "
            "run its provenance names. Pass the dataset parquet this run was trained from."
        )
    return joined


def _bars_with_a_choice(joined: pl.DataFrame) -> pl.DataFrame:
    """Only bars carrying two or more pairs.

    A bar with one pair has no choice to make, and counting it would put the same row into
    every feature's column and into the control's — flattening every difference this study
    exists to show towards zero in proportion to how many single-pair bars the run had.
    """
    return joined.filter(pl.len().over("decision_ts") >= 2)


def _grouped(
    eligible: pl.DataFrame, feature: str, direction: str, *, by_pair: bool
) -> Any:
    """Each bar's pairs in the order the candidate is taken from, grouped by bar.

    Values were already nulled when non-finite (`_joined`), so `nulls_last` is what puts a
    valueless pair after every valued one — in both directions, because it is applied
    independently of `descending`. The pair name ascending breaks ties in both directions, as
    `rank_universe` does: reversing it with the direction would move the candidate on a
    config flag that is supposed to order by the feature alone.
    """
    if by_pair:
        ordered = eligible.sort(["decision_ts", "pair"])
    else:
        ordered = eligible.sort(
            ["decision_ts", feature, "pair"],
            descending=[False, direction == "descending", False],
            nulls_last=True,
        )
    return ordered.group_by("decision_ts", maintain_order=True)


def _row(
    eligible: pl.DataFrame,
    feature: str,
    direction: str,
    *,
    by_pair: bool,
    di_fitted: bool,
) -> dict[str, Any]:
    """One line of the table: take the first pair per bar, and report what happened to it."""
    grouped = _grouped(eligible, feature, direction, by_pair=by_pair)
    taken = grouped.first()
    if by_pair:
        no_value: int | None = None
        tied: int | None = None
    else:
        heads = grouped.agg(
            pl.col(feature).get(0).alias("_first"), pl.col(feature).get(1).alias("_second")
        )
        no_value = int(heads.filter(pl.col("_first").is_null()).height)
        tied = int(
            heads.filter(
                pl.col("_first").is_not_null() & (pl.col("_first") == pl.col("_second"))
            ).height
        )
    return _summarise(taken, feature, direction, no_value, tied, di_fitted=di_fitted)


def _summarise(
    taken: pl.DataFrame,
    feature: str,
    direction: str,
    no_value: int | None,
    tied: int | None,
    *,
    di_fitted: bool,
) -> dict[str, Any]:
    bars = int(taken.height)
    labels = [str(value) for value in taken["label"]]
    counts = {name: sum(1 for value in labels if value == name) for name in _LABELS}
    buys = taken.filter(pl.col("is_buy"))
    buy_labels = [str(value) for value in buys["label"]]
    return {
        "feature": feature,
        "direction": direction,
        "bars": bars,
        "effective_bars": _effective(taken),
        "no_value_bars": no_value,
        "tied_bars": tied,
        "target_rate": counts["target"] / bars if bars else None,
        "stop_rate": counts["stop"] / bars if bars else None,
        "timeout_rate": counts["timeout"] / bars if bars else None,
        "mean_return_pct": (
            float(taken["return_pct"].mean() or 0.0) if bars else None
        ),
        "di_refused_rate": (
            float(taken["di_refused"].cast(pl.Float64).mean() or 0.0)
            if bars and di_fitted
            else None
        ),
        "buy_bars": int(buys.height),
        "buy_effective_bars": _effective(buys),
        "buy_target_rate": (
            sum(1 for value in buy_labels if value == "target") / len(buy_labels)
            if buy_labels
            else None
        ),
    }


def _effective(frame: pl.DataFrame) -> float:
    """The sum of the rows' uniqueness weights: the effective size beside a row count."""
    return float(frame["weight"].sum() or 0.0) if frame.height else 0.0
