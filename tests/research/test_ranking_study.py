"""Spec 75 — the candidate-ranking study.

The study exists so the operator can rule on `scout.rank_feature` from evidence. Its value is
entirely in being *unarguable*, so what is tested here is mostly what it refuses to do:
recommend, compose, order by outcome, write a break-even number nobody measured, take a pair
engine 7 would not take, or report a count without saying how much it is worth.

**Three levels.** The arithmetic is checked on small constructed frames where the right answer
can be worked out by hand — which feature takes which pair on which bar is a fact, and a study
that got it wrong would still produce a beautifully formatted table. The **choice** is then
held against engine 7's own `rank_universe`, bar by bar, over values that include NaN, ±inf,
null and ties, because the study is evidence only if it takes the pair the live engine would.
And the shape is checked against a real training run's output, because a constructed frame
proves nothing about the columns the real out-of-sample file actually has.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import require_module

pl = require_module("polars", reason="polars is not installed")
study = require_module(
    "acsoe.research.ranking_study", reason="the ranking study does not exist yet"
)

from acsoe.modelling.features import FEATURE_NAMES  # noqa: E402


class FixedConfig:
    """Only the two barrier sizes the report's break-even formula names."""

    def get(self, key: str) -> Any:
        return {"barriers.target_pct": 0.03, "barriers.stop_pct": 0.015}[key]


# --------------------------------------------------------------------------- #
# A frame small enough to check by hand
# --------------------------------------------------------------------------- #

#: Three bars, two pairs each, and the outcome is arranged so that **the two directions of
#: one feature disagree completely**: ranking by `alpha` descending always takes the pair
#: that hit its target, ascending always takes the pair that stopped out. A study that
#: ignored the direction, or applied it backwards, cannot produce both answers.
#:
#: The uniqueness weights differ by pair (0.5 for AAAUSD, 0.25 for BBBUSD) so the effective
#: size of a row depends on *which* pairs were taken, not only on how many.
HAND = [
    # (bar, pair, alpha, beta, label, return_pct, is_buy, di_refused, weight)
    (100, "AAAUSD", 9.0, 1.0, "target", 0.03, True, False, 0.5),
    (100, "BBBUSD", 1.0, 9.0, "stop", -0.015, False, False, 0.25),
    (200, "AAAUSD", 1.0, 9.0, "stop", -0.015, True, True, 0.5),
    (200, "BBBUSD", 9.0, 1.0, "target", 0.03, True, False, 0.25),
    (300, "AAAUSD", 9.0, 1.0, "target", 0.03, False, False, 0.5),
    (300, "BBBUSD", 1.0, 9.0, "timeout", 0.004, True, False, 0.25),
]


def frames_from(rows: list[dict[str, Any]], features: tuple[str, ...]) -> tuple[Any, Any]:
    """Split constructed rows into the out-of-sample file and the dataset, the way a run has."""
    frame = pl.DataFrame(rows)
    oos = frame.select(
        ["pair", "decision_ts", "label", "return_pct", "is_buy", "di", "di_refused", "weight"]
    )
    dataset = frame.select(["pair", "decision_ts", *features])
    return oos, dataset


def hand_frames(*, di: float | None = 0.1) -> tuple[Any, Any]:
    rows = [
        {
            "decision_ts": bar,
            "pair": pair,
            "alpha": alpha,
            "beta": beta,
            "label": label,
            "return_pct": ret,
            "is_buy": is_buy,
            "di": di,
            "di_refused": refused,
            "weight": weight,
        }
        for bar, pair, alpha, beta, label, ret, is_buy, refused, weight in HAND
    ]
    return frames_from(rows, ("alpha", "beta"))


@pytest.fixture
def hand_report() -> dict[str, Any]:
    oos, dataset = hand_frames()
    return study.build_report(oos, dataset, config=FixedConfig(), features=("alpha", "beta"))


def row_for(report: dict[str, Any], feature: str, direction: str) -> dict[str, Any]:
    for row in report["rankings"]:
        if row["feature"] == feature and row["direction"] == direction:
            return dict(row)
    raise AssertionError(f"no row for {feature} {direction}")


def one_bar(values: dict[str, Any], *, feature: str = "alpha") -> tuple[Any, Any]:
    """One decision bar, one row per pair, and every pair's outcome distinct by label.

    The label says which pair was taken: `target` for AAAUSD, `stop` for BBBUSD, `timeout`
    for anything else, so a row's target, stop and timeout rates name the choice directly.
    """
    labels = {"AAAUSD": "target", "BBBUSD": "stop"}
    rows = [
        {
            "decision_ts": 100,
            "pair": pair,
            feature: value,
            "label": labels.get(pair, "timeout"),
            "return_pct": 0.0,
            "is_buy": True,
            "di": 0.1,
            "di_refused": False,
            "weight": 1.0,
        }
        for pair, value in values.items()
    ]
    return frames_from(rows, (feature,))


def taken_label(values: dict[str, Any], direction: str) -> str:
    oos, dataset = one_bar(values)
    report = study.build_report(oos, dataset, config=FixedConfig(), features=("alpha",))
    row = row_for(report, "alpha", direction)
    for label in ("target", "stop", "timeout"):
        if row[f"{label}_rate"] == 1.0:
            return label
    raise AssertionError(row)


# --------------------------------------------------------------------------- #
# The arithmetic
# --------------------------------------------------------------------------- #


def test_ranking_descending_takes_the_highest_and_ascending_the_lowest(
    hand_report: dict[str, Any]
) -> None:
    """The two directions of one feature disagree completely on this frame, by construction.

    A study that ignored the direction would report the same numbers twice; one that applied
    it backwards would report them the wrong way round. Both are invisible in a table that
    only says "0.67".
    """
    descending = row_for(hand_report, "alpha", "descending")
    ascending = row_for(hand_report, "alpha", "ascending")
    assert descending["bars"] == ascending["bars"] == 3
    assert descending["target_rate"] == pytest.approx(1.0)
    assert ascending["target_rate"] == pytest.approx(0.0)
    assert ascending["stop_rate"] == pytest.approx(2 / 3)
    assert ascending["timeout_rate"] == pytest.approx(1 / 3)


def test_the_mean_return_follows_the_rows_that_were_taken(
    hand_report: dict[str, Any]
) -> None:
    assert row_for(hand_report, "alpha", "descending")["mean_return_pct"] == pytest.approx(
        0.03
    )
    assert row_for(hand_report, "alpha", "ascending")["mean_return_pct"] == pytest.approx(
        (-0.015 - 0.015 + 0.004) / 3
    )


def test_every_count_carries_the_effective_size_of_the_rows_it_counts(
    hand_report: dict[str, Any]
) -> None:
    """Spec 59 decision 5 as the operator amended it: the effective size beside every count.

    The weights differ by pair, so the effective size depends on which pairs a row took.
    `alpha` descending takes AAAUSD, BBBUSD, AAAUSD (0.5 + 0.25 + 0.5); ascending takes
    BBBUSD, AAAUSD, BBBUSD (0.25 + 0.5 + 0.25). Their BUY subsets are AAAUSD@100 and
    BBBUSD@200, and AAAUSD@200 and BBBUSD@300.
    """
    descending = row_for(hand_report, "alpha", "descending")
    ascending = row_for(hand_report, "alpha", "ascending")
    assert descending["effective_bars"] == pytest.approx(1.25)
    assert ascending["effective_bars"] == pytest.approx(1.0)
    assert descending["buy_effective_bars"] == pytest.approx(0.75)
    assert ascending["buy_effective_bars"] == pytest.approx(0.75)
    control = row_for(hand_report, study.ALPHABETICAL, "ascending")
    assert control["effective_bars"] == pytest.approx(1.5)


def test_the_di_refusal_rate_is_of_the_taken_pairs_not_of_every_row(
    hand_report: dict[str, Any]
) -> None:
    """One row in the frame has `di_refused` true and it is taken by `alpha` ascending on bar
    200 and by nothing else. A rate computed over every row would be 1/6 everywhere."""
    assert row_for(hand_report, "alpha", "ascending")["di_refused_rate"] == pytest.approx(
        1 / 3
    )
    assert row_for(hand_report, "alpha", "descending")["di_refused_rate"] == pytest.approx(
        0.0
    )
    assert hand_report["meta"]["di_fitted"] is True


def test_a_run_with_no_dissimilarity_index_reports_no_refusal_rate() -> None:
    """With `prediction.di_percentile` absent the trainer writes `di: null` and
    `di_refused: false` on every row. A rate of 0.0 would read as "the DI never refused a
    taken pair", a finding, when nothing was measured — and that is the committed state the
    full-archive run is trained in."""
    oos, dataset = hand_frames(di=None)
    report = study.build_report(oos, dataset, config=FixedConfig(), features=("alpha", "beta"))
    assert report["meta"]["di_fitted"] is False
    for row in report["rankings"]:
        assert row["di_refused_rate"] is None, row["feature"]


def test_the_buy_table_conditions_on_the_predictors_own_calls(
    hand_report: dict[str, Any]
) -> None:
    """Spec 75's second table. `alpha` ascending takes three pairs of which two were BUY
    calls, and neither hit its target."""
    ascending = row_for(hand_report, "alpha", "ascending")
    assert ascending["buy_bars"] == 2
    assert ascending["buy_target_rate"] == pytest.approx(0.0)
    descending = row_for(hand_report, "alpha", "descending")
    assert descending["buy_bars"] == 2
    assert descending["buy_target_rate"] == pytest.approx(1.0)


def test_the_alphabetical_control_is_present_and_is_not_a_feature(
    hand_report: dict[str, Any]
) -> None:
    """The control is the whole point: engine 7 ranks alphabetically today, so a feature
    that does not beat it changes nothing. On this frame it always takes AAAUSD."""
    control = row_for(hand_report, study.ALPHABETICAL, "ascending")
    assert control == hand_report["rankings"][0]
    assert control["bars"] == 3
    assert control["target_rate"] == pytest.approx(2 / 3)
    assert control["no_value_bars"] is None
    assert control["tied_bars"] is None
    assert study.ALPHABETICAL not in FEATURE_NAMES


def test_a_bar_with_one_pair_is_not_counted() -> None:
    """A bar with no choice would go into every feature's column and into the control's,
    flattening every difference towards zero in proportion to how many such bars the run
    had — which is most of them on a thin archive."""
    oos, dataset = hand_frames()
    extra = pl.DataFrame(
        [
            {
                "pair": "CCCUSD",
                "decision_ts": 400,
                "label": "target",
                "return_pct": 0.03,
                "is_buy": True,
                "di": 0.1,
                "di_refused": False,
                "weight": 0.5,
            }
        ]
    )
    features = pl.DataFrame(
        [{"pair": "CCCUSD", "decision_ts": 400, "alpha": 5.0, "beta": 5.0}]
    )
    report = study.build_report(
        pl.concat([oos, extra], how="vertical"),
        pl.concat([dataset, features], how="vertical"),
        config=FixedConfig(),
        features=("alpha", "beta"),
    )
    assert report["meta"]["bars"] == 3
    assert row_for(report, "alpha", "descending")["bars"] == 3


# --------------------------------------------------------------------------- #
# A pair with no value is never taken ahead of one with a value
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("direction", ["descending", "ascending"])
@pytest.mark.parametrize(
    "no_value", [None, math.nan, math.inf, -math.inf], ids=["null", "nan", "inf", "-inf"]
)
def test_a_pair_with_no_finite_value_is_never_taken_ahead_of_one_with_a_value(
    direction: str, no_value: float | None
) -> None:
    """`modelling/features.py` writes **NaN** for a lookback that has not filled, not null.

    polars orders NaN as the largest float, so a descending sort with `nulls_last` took the NaN
    pair first: on the real archive, the new listing or the thin pair with holes, measured
    under a feature's name. `rank_universe` treats every non-finite value as no value and sorts
    it last in both directions; so must this. BBBUSD holds the non-finite value and sorts
    before AAAUSD by nothing but its value, so taking it means the rule broke.
    """
    assert taken_label({"AAAUSD": 1.0, "BBBUSD": no_value}, direction) == "target"
    # And the bar was decided by the feature: the pair taken had a value. A count that read
    # the runner-up's value would call this bar undecided, on exactly the bars where a thin
    # pair lost — which survived a mutation sweep once.
    oos, dataset = one_bar({"AAAUSD": 1.0, "BBBUSD": no_value})
    report = study.build_report(oos, dataset, config=FixedConfig(), features=("alpha",))
    assert row_for(report, "alpha", direction)["no_value_bars"] == 0


@pytest.mark.parametrize("direction", ["descending", "ascending"])
def test_a_bar_where_no_pair_has_a_value_falls_to_name_order_and_is_counted(
    direction: str,
) -> None:
    oos, dataset = one_bar({"BBBUSD": math.nan, "AAAUSD": None, "CCCUSD": math.inf})
    report = study.build_report(oos, dataset, config=FixedConfig(), features=("alpha",))
    row = row_for(report, "alpha", direction)
    assert row["target_rate"] == pytest.approx(1.0), "AAAUSD by name, as rank_universe does"
    assert row["no_value_bars"] == 1
    assert row["tied_bars"] == 0


@pytest.mark.parametrize("direction", ["descending", "ascending"])
def test_a_tie_at_the_top_is_broken_by_name_in_both_directions_and_is_counted(
    direction: str,
) -> None:
    """Pair-name ascending in both directions, never reversed with the direction: that would
    move the candidate on a config flag that is supposed to order by the feature alone."""
    oos, dataset = one_bar({"BBBUSD": 5.0, "AAAUSD": 5.0, "CCCUSD": 5.0})
    report = study.build_report(oos, dataset, config=FixedConfig(), features=("alpha",))
    row = row_for(report, "alpha", direction)
    assert row["target_rate"] == pytest.approx(1.0)
    assert row["tied_bars"] == 1
    assert row["no_value_bars"] == 0


def test_a_tie_below_the_top_is_not_a_tie_that_decided_anything() -> None:
    oos, dataset = one_bar({"AAAUSD": 9.0, "BBBUSD": 2.0, "CCCUSD": 2.0})
    report = study.build_report(oos, dataset, config=FixedConfig(), features=("alpha",))
    assert row_for(report, "alpha", "descending")["tied_bars"] == 0


# --------------------------------------------------------------------------- #
# The choice is engine 7's choice
# --------------------------------------------------------------------------- #


def test_the_study_takes_the_pair_rank_universe_would_take_on_every_bar() -> None:
    """The seam, held with no double on either side.

    `research/` may not import the live path, so the rule is restated in the study; this
    test may import both, and asks them the same question over four hundred bars whose values
    are drawn to include every case the two could disagree on — NaN, +inf, -inf, null, exact
    ties at the top, negative values, and a pair set that differs from bar to bar. **The
    arrival order is shuffled per bar**, so neither side can pass by preserving what it was
    handed.
    """
    from acsoe.engines.scout.contracts import rank_universe

    generator = random.Random(20260913)
    pool = ["AAAUSD", "BBBUSD", "CCCUSD", "DDDUSD", "EEEUSD"]
    specials: list[float | None] = [math.nan, math.inf, -math.inf, None]
    rows: list[dict[str, Any]] = []
    for bar in range(400):
        pairs = generator.sample(pool, generator.randint(2, 5))
        tied = float(generator.randint(-3, 3))
        for pair in pairs:
            roll = generator.random()
            value: float | None
            if roll < 0.2:
                value = generator.choice(specials)
            elif roll < 0.45:
                value = tied
            else:
                value = float(generator.randint(-5, 5))
            rows.append({"decision_ts": 1000 + bar * 900, "pair": pair, "alpha": value})
    generator.shuffle(rows)
    frame = pl.DataFrame(rows, schema={"decision_ts": pl.Int64, "pair": pl.Utf8, "alpha": pl.Float64})
    oos = frame.select("pair", "decision_ts").with_columns(
        pl.lit("stop").alias("label"),
        pl.lit(0.0).alias("return_pct"),
        pl.lit(True).alias("is_buy"),
        pl.lit(0.1).alias("di"),
        pl.lit(False).alias("di_refused"),
        pl.lit(1.0).alias("weight"),
    )

    by_bar: dict[int, dict[str, float | None]] = {}
    for row in rows:
        by_bar.setdefault(int(row["decision_ts"]), {})[str(row["pair"])] = row["alpha"]

    for direction in ("descending", "ascending"):
        chosen = study.chosen_pairs(oos, frame, feature="alpha", direction=direction)
        assert set(chosen) == set(by_bar)
        for ts, values in by_bar.items():
            live = rank_universe(
                list(values),
                features={pair: {"alpha": value} for pair, value in values.items()},
                feature="alpha",
                descending=direction == "descending",
            )[0]
            assert chosen[ts] == live, (direction, ts, values)

    control = study.chosen_pairs(oos, frame, feature=None, direction="ascending")
    for ts, values in by_bar.items():
        assert control[ts] == rank_universe(list(values))[0]


# --------------------------------------------------------------------------- #
# What it refuses to do
# --------------------------------------------------------------------------- #


def test_the_report_recommends_nothing(hand_report: dict[str, Any]) -> None:
    """Spec 75, step 4. The operator rules; nobody guesses."""
    assert hand_report["meta"]["recommends"] is None
    text = json.dumps(hand_report).lower()
    for forbidden in ("recommend", "best_feature", "winner", "suggested", "preferred"):
        assert f'"{forbidden}"' not in text, forbidden


def test_the_rows_are_in_feature_order_and_not_in_outcome_order(
    hand_report: dict[str, Any]
) -> None:
    """An ordering by outcome is a recommendation with the word left off.

    On this frame `alpha` descending is the best row and `alpha` ascending the worst, and
    they come out adjacent and in declaration order regardless.
    """
    order = [(row["feature"], row["direction"]) for row in hand_report["rankings"]]
    assert order == [
        (study.ALPHABETICAL, "ascending"),
        ("alpha", "descending"),
        ("alpha", "ascending"),
        ("beta", "descending"),
        ("beta", "ascending"),
    ]


def test_no_break_even_number_is_written(hand_report: dict[str, Any]) -> None:
    """Invariant 2 and `AGENTS.md`'s first paragraph.

    Break-even is a function of friction — live fees, the measured spread, slippage — and
    `config/default.yaml` carries none of them, because nothing the exchange can tell us
    belongs in that file. A number here would be a hardcoded fee wearing a different name,
    so the report carries the formula and the barriers and leaves the friction null.
    """
    block = hand_report["break_even"]
    assert block["friction"] is None
    assert block["formula"] == "(stop_pct + friction) / (target_pct + stop_pct)"
    assert block["target_pct"] == pytest.approx(0.03)
    assert block["stop_pct"] == pytest.approx(0.015)


def test_no_composite_score_is_computed(hand_report: dict[str, Any]) -> None:
    """One feature at a time. A composite is a formula nobody asked for."""
    features = {row["feature"] for row in hand_report["rankings"]}
    assert features == {study.ALPHABETICAL, "alpha", "beta"}


def test_a_missing_feature_column_is_a_refusal_rather_than_a_silent_gap() -> None:
    oos, dataset = hand_frames()
    with pytest.raises(study.RankingStudyError, match="gamma"):
        study.build_report(
            oos, dataset, config=FixedConfig(), features=("alpha", "gamma")
        )


def test_a_dataset_that_does_not_cover_every_out_of_sample_row_is_a_refusal() -> None:
    """A `--dataset` from another build joins a subset, silently, and the table then
    describes a sample other than the run its provenance names."""
    oos, dataset = hand_frames()
    with pytest.raises(study.RankingStudyError, match="joins 5 row"):
        study.build_report(
            oos,
            dataset.filter(~((pl.col("pair") == "BBBUSD") & (pl.col("decision_ts") == 300))),
            config=FixedConfig(),
            features=("alpha", "beta"),
        )


def test_a_dataset_that_repeats_a_row_is_a_refusal() -> None:
    oos, dataset = hand_frames()
    with pytest.raises(study.RankingStudyError, match="joins 7 row"):
        study.build_report(
            oos,
            pl.concat([dataset, dataset.head(1)], how="vertical"),
            config=FixedConfig(),
            features=("alpha", "beta"),
        )


def test_a_single_pair_run_is_a_refusal(hand_report: dict[str, Any]) -> None:
    """A ranking study over one pair compares every choice against itself."""
    del hand_report
    oos, dataset = hand_frames()
    with pytest.raises(study.RankingStudyError, match="two or more pairs"):
        study.build_report(
            oos.filter(pl.col("pair") == "AAAUSD"),
            dataset.filter(pl.col("pair") == "AAAUSD"),
            config=FixedConfig(),
            features=("alpha", "beta"),
        )


# --------------------------------------------------------------------------- #
# Against a real run, and the file it writes
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def real_run(tmp_path_factory: Any) -> Any:
    require_module("lightgbm", reason="lightgbm is not installed")
    from acsoe.research import training
    from tests.engines.test_prediction import DI_PERCENTILE, Wrapped
    from tests.harness.doubles import load_default_config
    from tests.research.test_training import NOW, dataset_for

    config = load_default_config()
    root = tmp_path_factory.mktemp("ranking-study")
    dataset = dataset_for(config, random_walk=False)
    report = training.train_walkforward(
        dataset,
        config=Wrapped(config, **{"prediction.di_percentile": DI_PERCENTILE}),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=2,
    )
    return report, dataset, config


def test_every_feature_appears_twice_against_a_real_run(real_run: Any) -> None:
    """Spec 75's acceptance check, on the file the trainer actually writes.

    The constructed frames above prove the arithmetic and prove nothing about the columns
    a real out-of-sample file has.
    """
    report, dataset, config = real_run
    built = study.build_report(
        pl.read_parquet(report.oos_path), dataset, config=config
    )
    rankings = built["rankings"]
    assert rankings[0]["feature"] == study.ALPHABETICAL
    counted = dict.fromkeys(FEATURE_NAMES, 0)
    for row in rankings[1:]:
        counted[row["feature"]] += 1
        assert row["direction"] in study.DIRECTIONS
    assert set(counted.values()) == {2}, "every feature appears once per direction"
    assert len(rankings) == 1 + 2 * len(FEATURE_NAMES)


def test_every_row_carries_every_column(real_run: Any) -> None:
    report, dataset, config = real_run
    built = study.build_report(pl.read_parquet(report.oos_path), dataset, config=config)
    for row in built["rankings"]:
        assert set(row) == set(study.STUDY_COLUMNS), row["feature"]
        assert 0.0 < row["effective_bars"] < row["bars"], (
            "consecutive bars overlap, so the effective size is below the count",
            row["feature"],
        )


def test_the_report_is_written_with_its_provenance(real_run: Any, tmp_path: Path) -> None:
    """The rule `labelled_sample.parquet` was deposited under: a report that cannot say
    where it came from is indistinguishable from one written by hand."""
    report, dataset, config = real_run
    built = study.build_report(
        pl.read_parquet(report.oos_path),
        dataset,
        config=config,
        provenance={"oos_file": str(report.oos_path), "feature_version": "f1"},
    )
    path = study.write_report(built, tmp_path / "dataset")
    assert path.name.startswith("ranking-study-")
    written = json.loads(path.read_bytes().decode("utf-8"))
    assert written["meta"]["oos_file"] == str(report.oos_path)
    assert written["meta"]["feature_version"] == "f1"
    assert written["meta"]["bars"] > 0
    assert written["columns"] == list(study.STUDY_COLUMNS)
