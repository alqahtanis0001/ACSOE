"""The dataset, the weights, and the weekly walk-forward predictor. Specs 67 and 68.

A predictor that trains at the same cadence the live system retrains, on a dataset
assembled from the historical archive and nothing else, reporting the metric that was
decided before it trained.

## The three rulings this module is held to

**The walk-forward is past-only.** `research/walkforward.py` is used as it is and is never
edited here; a fold trains on the days before its test window and nothing after it.
Operator ruling 1 of 2026-09-12, and `walkforward_trains_on_the_past_only` is registered
under phase 4 *and* phase 5 so that a change here turns the Phase 5 gate red.

**The metric is the Brier score of P(target) against the base-rate Brier**, per fold, with
multiclass log loss beside it and the target rate among BUY calls. **Accuracy is not
computed**: the base rate is 23.89% and a model that always predicts `stop` scores 51%, so
accuracy rewards the model that never trades.

**Rows are weighted by average uniqueness**, and the effective sample size is reported per
fold beside that fold's row count, and again in aggregate. A fold with 8,000 rows and an
effective size of 300 is a fold whose metrics mean almost nothing, and an aggregate hides
exactly that fold.

## What is deliberately absent

`prediction.di_percentile` is the operator's and is absent until the walk-forward reports.
The DI is fitted only when it is supplied; until then every fold reports `di_rows: null`
and `di_fitted_on_predictor_training_set` is PENDING naming the key. Nothing here defaults
it: that number decides when a model is allowed to refuse a trade.

**The break-even win rate is not computed here and the reason is invariant 2.** Spec 67
asks for the BUY-call target rate "beside the break-even rates", and break-even is a
function of *friction* — live fees plus the measured spread plus slippage. None of those
exists offline, and the reference figures in `trading-invariants.md` are marked for
sanity-checking only and never for use in code. So the digest reports `buy_target_rate`
and says in its own notes that the comparison is the reader's; writing 0.61 into this file
would be the hardcoded fee `AGENTS.md` forbids in its first paragraph, wearing a different
name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol

import numpy as np
import polars as pl

from acsoe.modelling.artefacts import (
    FoldBounds,
    Manifest,
    Scaler,
    identity_digest,
    write_run,
)
from acsoe.modelling.expected_move import expected_move_pct, is_buy_call
from acsoe.modelling.features import FEATURE_NAMES, FEATURE_VERSION, compute
from acsoe.modelling.macro import (
    MACRO_AVAILABLE_COLUMN,
    macro_column,
    macro_feature_names,
    macro_pair_names,
)
from acsoe.modelling.weights import average_uniqueness, effective_sample_size
from acsoe.research.labelling import LABEL_TARGET, label_frame
from acsoe.research.walkforward import Fold, purged_walk_forward

__all__ = [
    "CLASS_ORDER",
    "DATASET_COLUMNS",
    "OOS_COLUMNS",
    "TrainingError",
    "TrainingReport",
    "build_dataset",
    "main",
    "train_walkforward",
]


class TrainingError(ValueError):
    """A refusal to train. Every message names which of the several causes."""


#: The three barriers, in the order every artefact records them and engine 8 reads them.
#: Positional, so a permuted order swaps `target` for `stop` with nothing raising.
CLASS_ORDER: Final[tuple[str, ...]] = ("target", "stop", "timeout")

#: Carried beside the features. `pair` is an **identifier and never a feature**: a pooled
#: model that can memorise a pair name has learned which pairs went up in the training
#: window and nothing that transfers.
DATASET_COLUMNS: Final[tuple[str, ...]] = (
    "pair",
    "decision_ts",
    "label",
    "label_window_end_ts",
    "return_pct",
    "weight",
)

#: Specs 69, 74 and 75 read this file and nothing else.
OOS_COLUMNS: Final[tuple[str, ...]] = (
    "pair",
    "decision_ts",
    "fold_index",
    "p_target",
    "p_stop",
    "p_timeout",
    "expected_move_pct",
    "is_buy",
    "di",
    "di_refused",
    "label",
    "return_pct",
    "weight",
)

_MONEY = ("open", "high", "low", "close", "volume")


class _Config(Protocol):
    def get(self, dotted_key: str, /) -> Any: ...


def _required(config: _Config, key: str) -> Any:
    """A config value that must be present and not None.

    `Config.get` raises on an unknown key and returns `None` for a leaf the operator has
    not decided — two different facts reported differently on purpose. A `None` read as a
    zero is the Phase 4 embargo defect: no crash, no red test, just a model that flatters.
    """
    value = config.get(key)
    if value is None:
        raise TrainingError(
            f"`{key}` is absent. It is a leaf the operator has not supplied, and "
            "`Config.get` returns None rather than raising for one. Nothing here "
            "defaults it."
        )
    return value


def _config_digest(config: _Config) -> str:
    """A digest over every config value this module reads.

    Not over the whole file: a run must be reproducible from *its* config, and a change to
    `console.port` is not a change to the model. Keyed and sorted, so two runs over the
    same values agree byte for byte.
    """
    keys = (
        "timeframes.decision_bar_s",
        "barriers.target_pct",
        "barriers.stop_pct",
        "barriers.timeout_bars",
        "backtest.training_window_days",
        "backtest.retrain_interval_days",
        "backtest.embargo_bars",
        "training.num_trees",
        "training.learning_rate",
        "training.num_leaves",
        "training.min_data_in_leaf",
        "prediction.calibration_days",
        "prediction.threads",
        "prediction.di_window_days",
        "prediction.di_neighbours",
        "prediction.di_reference_rows",
        "prediction.di_percentile",
        "seeds.train",
        "seeds.global",
        "features.version",
        "features.min_lookback_fill",
        "features.max_lookback_bars",
    )
    payload = {key: _as_jsonable(config.get(key)) for key in keys}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _as_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)
# --------------------------------------------------------------------------- #
# The dataset
# --------------------------------------------------------------------------- #


def build_dataset(
    labelled: Mapping[str, pl.DataFrame],
    candles: Mapping[str, pl.DataFrame],
    *,
    config: _Config,
    macro_archive: Mapping[str, str] | None = None,
) -> pl.DataFrame:
    """One pooled frame: every pair's features joined to its labels, with sample weights.

    :param labelled: `research/labelling.py`'s output per pair — money as strings, one row
        per decision bar, carrying `label_window_end_ts` and `return_pct`.
    :param candles: the same pairs' OHLCVT, as `research/historical.py` parses it.
    :param macro_archive: `{asset: archive pair name}`. The macro pair's own feature row is
        joined onto every row of every pair by `decision_ts`, renamed through
        `modelling.macro.macro_column`. Omitted, the macro columns are absent entirely —
        which is a different dataset, so the manifest records the feature list either way
        and an engine loading it is held to exactly that list.

    **Weights are computed per pair, never pooled.** Two pairs' label windows overlap in
    wall-clock time and do not overlap in information: SOLUSD's next twelve hours and
    ADAUSD's next twelve hours are two observations, not one. Pooling before counting
    concurrency would divide every weight by roughly the number of pairs and make the
    effective sample size a statement about how many pairs are listed.

    **`pair` is carried and is never a feature.** The frame needs it to join, to weight per
    pair and to prove row identity; the trainer's feature list is `FEATURE_NAMES` plus the
    macro columns and nothing else.
    """
    interval_s = int(_required(config, "timeframes.decision_bar_s"))
    min_fill = float(_required(config, "features.min_lookback_fill"))
    floor = int(config.get("dataset.min_labelled_rows") or 0)

    macro_frames: dict[str, pl.DataFrame] = {}
    if macro_archive:
        for asset, pair in sorted(macro_archive.items()):
            frame = candles.get(pair)
            if frame is None:
                raise TrainingError(
                    f"macro asset {asset!r} names archive pair {pair!r}, which is not in "
                    "the candles given. The macro columns are joined from the same "
                    "archive as every other pair; a missing one is a dataset without a "
                    "market backdrop, and silently dropping the columns would train a "
                    "model an engine could never load."
                )
            macro_frames[asset] = _features_of(frame, interval_s, min_fill)

    parts: list[pl.DataFrame] = []
    for pair in sorted(labelled):
        labels = labelled[pair]
        if labels.height < floor:
            continue
        frame = candles.get(pair)
        if frame is None:
            raise TrainingError(f"{pair} has labels and no candles")
        features = _features_of(frame, interval_s, min_fill)
        joined = (
            labels.select(
                pl.col("pair"),
                pl.col("decision_ts").cast(pl.Int64),
                pl.col("label"),
                pl.col("label_window_end_ts").cast(pl.Int64),
                pl.col("return_pct").cast(pl.Float64),
            )
            .join(features, left_on="decision_ts", right_on="ts", how="inner")
            .sort("decision_ts")
        )
        if joined.height == 0:
            continue
        joined = joined.with_columns(
            pl.Series(
                "weight",
                average_uniqueness(
                    [int(v) for v in joined["decision_ts"]],
                    [int(v) for v in joined["label_window_end_ts"]],
                ),
                dtype=pl.Float64,
            )
        )
        parts.append(_with_macro(joined, macro_frames))

    if not parts:
        raise TrainingError(
            "no pair produced a labelled, featured row. Either the archive is shorter "
            "than the longest lookback or the labels and the candles do not share a "
            "decision-bar grid."
        )
    return pl.concat(parts, how="vertical").sort(["decision_ts", "pair"])


def pairs_below_floor(
    labelled: Mapping[str, pl.DataFrame], *, config: _Config
) -> tuple[str, ...]:
    """The pairs `build_dataset` leaves out, by name, the way engine 23 reports them.

    A separate function rather than a second return value, so `build_dataset`'s signature
    stays the one thing both the criterion and the CLI call. A pair left out is a pair the
    model has never seen and the leaderboard cannot say so later, so the CLI prints these
    and the manifest records the pairs that *were* used.
    """
    floor = int(config.get("dataset.min_labelled_rows") or 0)
    return tuple(sorted(pair for pair, frame in labelled.items() if frame.height < floor))


def _features_of(frame: pl.DataFrame, interval_s: int, min_fill: float) -> pl.DataFrame:
    """One pair's feature frame, from the archive's `Decimal` money.

    The cast to float happens here and once: engine 5 makes the same single cast from the
    decimal strings engine 3 publishes, which is what lets the two paths be compared for
    exact equality rather than for closeness.
    """
    money = [column for column in _MONEY if column in frame.columns]
    floats = frame.with_columns([pl.col(column).cast(pl.Float64) for column in money])
    return compute(floats, interval_s=interval_s, min_lookback_fill=min_fill)


def _with_macro(
    joined: pl.DataFrame, macro_frames: Mapping[str, pl.DataFrame]
) -> pl.DataFrame:
    """Join each macro asset's feature row onto every row by decision bar.

    A bar where a macro asset has no row keeps its own features and gets nulls for that
    asset, with `macro_available` false. **Not dropped**: a bar the pair traded in is a bar
    the model will meet live, and dropping it would remove exactly the periods when the
    macro feed was broken — which is training the model on the assumption that the feed is
    never broken.
    """
    if not macro_frames:
        return joined.with_columns(pl.lit(value=True).alias(MACRO_AVAILABLE_COLUMN))
    out = joined
    present: list[pl.Expr] = []
    for asset in sorted(macro_frames):
        renamed = macro_frames[asset].rename(
            {name: macro_column(asset, name) for name in FEATURE_NAMES}
        )
        out = out.join(renamed, left_on="decision_ts", right_on="ts", how="left")
        present.append(pl.col(macro_column(asset, FEATURE_NAMES[0])).is_not_null())
    available = present[0]
    for expression in present[1:]:
        available = available & expression
    return out.with_columns(available.alias(MACRO_AVAILABLE_COLUMN))


def feature_columns(dataset: pl.DataFrame, assets: Sequence[str] = ()) -> tuple[str, ...]:
    """The ordered feature list for this dataset: `FEATURE_NAMES` then the macro columns.

    Derived from the dataset rather than from config, so an artefact's feature list always
    describes the frame it was fitted on. The order is the contract: a model handed its
    columns permuted returns confident nonsense and nothing raises.
    """
    macro = [name for name in macro_feature_names(assets) if name in dataset.columns]
    return (*FEATURE_NAMES, *macro)
# --------------------------------------------------------------------------- #
# The walk-forward
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TrainingReport:
    """What one walk-forward run produced, and where it put it."""

    run_id: str
    models_dir: Path
    derived_dir: Path
    fold_runs: tuple[str, ...]
    folds: tuple[Mapping[str, Any], ...]
    digest: Mapping[str, Any]
    digest_path: Path
    oos_path: Path
    feature_names: tuple[str, ...]


def train_walkforward(
    dataset: pl.DataFrame,
    *,
    config: _Config,
    models_dir: Path,
    derived_dir: Path,
    now: datetime,
    max_folds: int | None = None,
    store: Any = None,
) -> TrainingReport:
    """Roll a weekly walk-forward over `dataset`, training one predictor per fold.

    :param now: injected. Nothing here reads a clock: the run id and every `created_at`
        come from this, so two runs over the same config and data at different moments
        differ only where they are supposed to.
    :param store: when given, `store.new_model_run_dir(run_id)` creates each artefact
        directory and refuses an existing one. Without it the same
        ``mkdir(exist_ok=False)`` is used directly — the identical atomic refusal, one
        primitive, so a caller without a database still cannot overwrite an artefact.
        `acsoe research` and the CLI below always pass the store.

    The folds come from `purged_walk_forward` unchanged. **This module never edits
    `research/walkforward.py`**, and `walkforward_trains_on_the_past_only` is registered
    under phase 5 so that an edit here that weakened it turns this phase's gate red rather
    than only Phase 4's.
    """
    _require_columns(dataset)
    interval_s = int(_required(config, "timeframes.decision_bar_s"))
    assets = _assets_in(dataset)
    names = feature_columns(dataset, assets)
    seed = int(_required(config, "seeds.train"))
    digest = _config_digest(config)

    rows = dataset.select(["decision_ts", "label_window_end_ts"]).to_dicts()
    folds = purged_walk_forward(rows, config=config, interval_s=interval_s)
    if not folds:
        raise TrainingError(
            f"the splitter produced no folds over {dataset.height} rows spanning "
            f"{_span_days(dataset):.1f} days. A rolling walk-forward needs more than "
            "`backtest.training_window_days` of history before its first test window "
            "opens; a run reporting zero folds is not a short run, it is no run."
        )
    if max_folds is not None:
        folds = folds[:max_folds]

    run_id = f"train-{now.strftime('%Y%m%dT%H%M%S')}-{digest[:8]}"
    models_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []
    fold_runs: list[str] = []
    oos_parts: list[pl.DataFrame] = []
    for fold in folds:
        entry, oos, fold_run = _train_one_fold(
            dataset,
            fold,
            config=config,
            names=names,
            seed=seed,
            config_digest=digest,
            run_id=run_id,
            models_dir=models_dir,
            now=now,
            store=store,
            assets=assets,
        )
        entries.append(entry)
        fold_runs.append(fold_run)
        if oos.height:
            oos_parts.append(oos)

    oos_frame = (
        pl.concat(oos_parts, how="vertical")
        if oos_parts
        else pl.DataFrame(schema=dict.fromkeys(OOS_COLUMNS, pl.Float64))
    )
    oos_path = derived_dir / f"oos_{run_id}.parquet"
    oos_frame.write_parquet(oos_path)

    payload = {
        "run_id": run_id,
        "created_at": now.isoformat(),
        "config_digest": digest,
        "feature_version": FEATURE_VERSION,
        "feature_names": list(names),
        "class_order": list(CLASS_ORDER),
        "pairs": sorted({str(value) for value in dataset["pair"].unique()}),
        "rows": int(dataset.height),
        "effective_sample_size": effective_sample_size(
            [float(value) for value in dataset["weight"]]
        ),
        "folds": entries,
        "notes": (
            "The BUY-call target rate is reported per fold and is NOT compared against a "
            "break-even rate here. Break-even is a function of friction - live fees, the "
            "measured spread and slippage - none of which exists offline, and the "
            "reference figures in trading-invariants.md are marked for sanity-checking "
            "only and never for use in code. The comparison is the reader's."
        ),
    }
    digest_path = derived_dir / f"walkforward_digest_{run_id}.json"
    digest_path.write_bytes(
        json.dumps(payload, sort_keys=True, indent=2, default=str).encode("utf-8") + b"\n"
    )

    return TrainingReport(
        run_id=run_id,
        models_dir=models_dir,
        derived_dir=derived_dir,
        fold_runs=tuple(fold_runs),
        folds=tuple(entries),
        digest=payload,
        digest_path=digest_path,
        oos_path=oos_path,
        feature_names=names,
    )


def _require_columns(dataset: pl.DataFrame) -> None:
    absent = [column for column in DATASET_COLUMNS if column not in dataset.columns]
    if absent:
        raise TrainingError(
            "the dataset is missing " + ", ".join(absent) + "; build it with build_dataset"
        )
    missing_features = [name for name in FEATURE_NAMES if name not in dataset.columns]
    if missing_features:
        raise TrainingError(
            f"the dataset is missing {len(missing_features)} feature column(s), the first "
            f"being {missing_features[0]}. The feature list is the contract an artefact is "
            "loaded against."
        )


def _assets_in(dataset: pl.DataFrame) -> tuple[str, ...]:
    """Which macro assets this dataset actually carries, read off its columns.

    Derived rather than configured, so the artefact's feature list always describes the
    frame it was fitted on: a dataset built without macro columns trains a model an engine
    will refuse rather than one it will silently feed the wrong inputs.
    """
    found: set[str] = set()
    for column in dataset.columns:
        for name in FEATURE_NAMES:
            suffix = "_" + name
            if column.startswith("macro_") and column.endswith(suffix):
                found.add(column[len("macro_") : -len(suffix)])
    return tuple(sorted(found))


def _span_days(dataset: pl.DataFrame) -> float:
    stamps = dataset["decision_ts"]
    if stamps.len() < 2:
        return 0.0
    return float((int(stamps.max()) - int(stamps.min())) / 86_400)
# --------------------------------------------------------------------------- #
# One fold
# --------------------------------------------------------------------------- #


def _train_one_fold(
    dataset: pl.DataFrame,
    fold: Fold,
    *,
    config: _Config,
    names: Sequence[str],
    seed: int,
    config_digest: str,
    run_id: str,
    models_dir: Path,
    now: datetime,
    store: Any,
    assets: Sequence[str],
) -> tuple[dict[str, Any], pl.DataFrame, str]:
    """Train, calibrate, score and write one fold. Returns its digest entry and its OOS rows."""
    import lightgbm as lgb
    from sklearn.isotonic import IsotonicRegression

    train = dataset[list(fold.train_index)]
    test = dataset[list(fold.test_index)]
    if train.height == 0 or test.height == 0:
        # Reported, never dropped. Spec 53 forbids a silently discarded empty fold: a run
        # that quietly produced four folds where the caller expected twelve reports
        # metrics over a third of the data with nothing saying so.
        return (
            _empty_entry(fold, train.height, test.height),
            pl.DataFrame(schema=dict.fromkeys(OOS_COLUMNS, pl.Float64)),
            "",
        )

    calibration_days = int(_required(config, "prediction.calibration_days"))
    cutoff = int(fold.train_end_ts) - calibration_days * 86_400
    fit_rows = train.filter(pl.col("decision_ts") < cutoff)
    calibration_rows = train.filter(pl.col("decision_ts") >= cutoff)
    if fit_rows.height == 0 or calibration_rows.height == 0:
        # The calibration tail is carved out of the **training** window and never out of
        # the test window: a calibrator fitted on the rows the model is scored on is a
        # leak that shows up only as a better number.
        fit_rows, calibration_rows = train, train

    # Fitted on the training rows and on nothing else. The rows it saw are recorded by
    # identity in the manifest, because **no metric can see this one**: MinMax is a
    # monotone per-feature transform and a gradient-boosted tree splits on order rather
    # than magnitude, so fitting it on train plus test changes the predictor's output not
    # at all. It changes the Dissimilarity Index, which is a Euclidean distance in this
    # same scaled space, and by the time that showed up it would be a refusal threshold
    # nobody could explain.
    scaler = Scaler.fit(_matrix(train, names), names)
    scaler_rows = train
    x_fit = np.asarray(scaler.transform(_matrix(fit_rows, names)), dtype=np.float64)
    x_cal = np.asarray(scaler.transform(_matrix(calibration_rows, names)), dtype=np.float64)
    x_test = np.asarray(scaler.transform(_matrix(test, names)), dtype=np.float64)

    y_fit = _codes(fit_rows)
    weights = np.asarray([float(value) for value in fit_rows["weight"]], dtype=np.float64)

    model = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=len(CLASS_ORDER),
        n_estimators=int(_required(config, "training.num_trees")),
        learning_rate=float(_required(config, "training.learning_rate")),
        num_leaves=int(_required(config, "training.num_leaves")),
        min_child_samples=int(_required(config, "training.min_data_in_leaf")),
        random_state=seed,
        # Determinism needs all three: a seed alone is not enough, a thread count alone is
        # not enough, and `force_row_wise` stops LightGBM choosing a histogram strategy
        # from the data's shape. `training_is_reproducible_from_config_and_data` is what
        # notices when one of them is dropped.
        deterministic=True,
        force_row_wise=True,
        n_jobs=int(_required(config, "prediction.threads")),
        verbose=-1,
    )
    model.fit(x_fit, y_fit, sample_weight=weights)

    calibrators, calibration_identity, calibration_end_ts = _fit_calibrators(
        model.predict_proba(x_cal), calibration_rows, IsotonicRegression
    )
    probabilities = _calibrate(model.predict_proba(x_test), calibrators)

    target_pct = float(_required(config, "barriers.target_pct"))
    stop_pct = float(_required(config, "barriers.stop_pct"))
    mean_timeout = _mean_timeout_return(train)
    moves = [
        expected_move_pct(
            p_target=float(row[0]),
            p_stop=float(row[1]),
            p_timeout=float(row[2]),
            target_pct=target_pct,
            stop_pct=stop_pct,
            mean_timeout_return=mean_timeout,
        )
        for row in probabilities
    ]
    buys = [is_buy_call(value) for value in moves]

    di_fit, di_values, di_refusals = _fit_and_score_di(
        config, train, test, scaler, names, seed, x_test
    )

    oos = test.select(["pair", "decision_ts", "label", "return_pct", "weight"]).with_columns(
        pl.lit(int(fold.fold_index)).alias("fold_index"),
        pl.Series("p_target", probabilities[:, 0], dtype=pl.Float64),
        pl.Series("p_stop", probabilities[:, 1], dtype=pl.Float64),
        pl.Series("p_timeout", probabilities[:, 2], dtype=pl.Float64),
        pl.Series("expected_move_pct", moves, dtype=pl.Float64),
        pl.Series("is_buy", buys, dtype=pl.Boolean),
        pl.Series("di", di_values, dtype=pl.Float64),
        pl.Series("di_refused", di_refusals, dtype=pl.Boolean),
    ).select(OOS_COLUMNS)

    entry = _fold_entry(
        fold,
        train=train,
        test=test,
        probabilities=probabilities,
        buys=buys,
        di_fit=di_fit,
        di_refusals=di_refusals,
    )

    fold_run_id = f"{run_id}-f{fold.fold_index}"
    directory = _new_run_dir(store, models_dir, fold_run_id)
    _write_fold_artefacts(
        directory,
        model=model,
        calibrators=calibrators,
        di_fit=di_fit,
        scaler=scaler,
        names=names,
        fold=fold,
        train=train,
        test=test,
        buys=buys,
        entry=entry,
        run_id=fold_run_id,
        config_digest=config_digest,
        seed=seed,
        now=now,
        assets=assets,
        mean_timeout=mean_timeout,
        scaler_rows=scaler_rows,
        calibration_identity=calibration_identity,
        calibration_rows=int(calibration_rows.height),
        calibration_end_ts=calibration_end_ts,
    )
    entry["run_id"] = fold_run_id
    return entry, oos, fold_run_id


def _matrix(frame: pl.DataFrame, names: Sequence[str]) -> np.ndarray[Any, Any]:
    """The feature columns as one `float64` array, in `names` order.

    **numpy rather than a list of lists, and the order is the whole point.** A row-by-row
    Python build is fine on a constructed fold and is quadratic-feeling on twenty million
    rows: the full dataset is 20,331,237 rows by roughly forty columns, so the list version
    would allocate 800 million Python floats to produce an array polars can hand over
    directly. `Scaler.transform` has a numpy path for the same reason, so there is still
    exactly one implementation of the scaling rather than a fast copy beside it.
    """
    null_to_nan = [pl.col(name).cast(pl.Float64).fill_null(math.nan) for name in names]
    return frame.select(null_to_nan).to_numpy().astype(np.float64, copy=False)


def _codes(frame: pl.DataFrame) -> np.ndarray[Any, Any]:
    """Labels as integer codes in `CLASS_ORDER`.

    Integer codes rather than strings so that LightGBM's `classes_` order is fixed by this
    module rather than by whichever label happened to appear first in the fold. A permuted
    class order swaps `target` for `stop` in every probability, silently.
    """
    index = {label: position for position, label in enumerate(CLASS_ORDER)}
    values = []
    for label in frame["label"]:
        if label not in index:
            raise TrainingError(
                f"label {label!r} is not one of {CLASS_ORDER}; the triple barrier has "
                "three outcomes and spec 52 forbids inventing a fourth"
            )
        values.append(index[label])
    return np.asarray(values, dtype=np.int64)


def _mean_timeout_return(train: pl.DataFrame) -> float:
    """The mean `return_pct` of the training window's timeout rows.

    **Measured, never assumed zero.** A timeout closes at whatever the price is twelve
    hours later, and across this dataset that has a sign; assuming zero biases every
    expected move in the same direction, which is small, consistent and exactly the kind
    of error that survives.
    """
    timeouts = train.filter(pl.col("label") == "timeout")["return_pct"]
    if timeouts.len() == 0:
        return 0.0
    return float(timeouts.mean() or 0.0)
# --------------------------------------------------------------------------- #
# Calibration, the metric, and the DI
# --------------------------------------------------------------------------- #


def _fit_calibrators(
    raw: np.ndarray[Any, Any], rows: pl.DataFrame, isotonic: Any
) -> tuple[list[Any], str, int]:
    """One isotonic regression per class, fitted on the held-out tail of the training window.

    **Returns the identity of the rows it was fitted on, and that is not decoration.** The
    first attempt at proving this recorded `calibration_rows` in the manifest from the
    caller's own variable, and a mutation that passed the *test* rows to this function
    survived the whole suite untouched: the manifest kept describing what the caller
    intended rather than what the calibrator saw. Taking the frame rather than pre-computed
    labels, and returning the digest from the same argument that feeds the fit, is what
    makes the record and the fit inseparable — substitute the test rows and the manifest
    says so.

    LightGBM's raw multiclass output is not calibrated, and an expected move computed from
    uncalibrated probabilities is a number in the right range and the wrong size. Isotonic
    is monotone, so it cannot reorder candidates; it moves the level, which is exactly what
    the expected move depends on and the ranking does not.
    """
    codes = _codes(rows)
    fitted: list[Any] = []
    for index in range(len(CLASS_ORDER)):
        target = (codes == index).astype(np.float64)
        model = isotonic(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        if target.sum() == 0 or target.sum() == target.size:
            # Every row of the calibration tail is or is not this class. Isotonic on a
            # constant target fits a constant, which would peg the class at 0 or 1 for
            # every live prediction. Identity instead, and the manifest records that this
            # class was not calibratable on this fold.
            fitted.append(None)
            continue
        model.fit(raw[:, index], target)
        fitted.append(model)
    identity = identity_digest(
        [str(value) for value in rows["pair"]],
        [int(value) for value in rows["decision_ts"]],
    )
    return fitted, identity, int(rows["decision_ts"].max() or 0)


def _calibrate(raw: np.ndarray[Any, Any], calibrators: Sequence[Any]) -> np.ndarray[Any, Any]:
    """Apply the per-class calibrators and **renormalise**.

    The renormalisation is not tidiness. Three independently calibrated probabilities do
    not sum to one, and an unrenormalised set scales every expected move by an unknown
    factor: the ranking between candidates survives it, so the BUY boundary moves while
    everything still looks internally consistent. `modelling.expected_move` refuses a set
    that does not sum to one, which is the assertion that keeps this line honest.
    """
    out = np.empty_like(raw, dtype=np.float64)
    for index, calibrator in enumerate(calibrators):
        column = raw[:, index]
        out[:, index] = column if calibrator is None else calibrator.predict(column)
    np.clip(out, 1e-9, 1.0, out=out)
    totals = out.sum(axis=1, keepdims=True)
    return out / totals


def _brier_of_target(probabilities: np.ndarray[Any, Any], labels: Sequence[str]) -> float:
    """The mean squared error of P(target) against whether the target was touched first."""
    actual = np.asarray([1.0 if label == LABEL_TARGET else 0.0 for label in labels])
    return float(np.mean((probabilities[:, 0] - actual) ** 2))


def _base_rate_brier(labels: Sequence[str]) -> float:
    """`p(1 - p)` for the fold's own target rate: what a constant prediction would earn.

    The number every fold's Brier is reported beside. A model that does not beat it has
    learned nothing, and it is the comparison that exists because **accuracy is useless
    here**: at a 23.89% target rate a model that always predicts `stop` is right 51% of the
    time, so a headline hit rate rewards the model that never trades.

    Computed on the **test** window's rate, because that is the window the Brier beside it
    is computed on, and `p(1-p)` is the smallest Brier any constant prediction could
    achieve there. It is therefore a *generous* baseline — a constant predictor that knew
    the answer's base rate — which is the right direction for a bar the model must clear.
    """
    rate = sum(1 for label in labels if label == LABEL_TARGET) / max(len(labels), 1)
    return float(rate * (1.0 - rate))


def _log_loss(probabilities: np.ndarray[Any, Any], codes: np.ndarray[Any, Any]) -> float:
    picked = probabilities[np.arange(codes.size), codes]
    return float(-np.mean(np.log(np.clip(picked, 1e-12, 1.0))))


def _fit_and_score_di(
    config: _Config,
    train: pl.DataFrame,
    test: pl.DataFrame,
    scaler: Scaler,
    names: Sequence[str],
    seed: int,
    x_test: np.ndarray[Any, Any],
) -> tuple[Any, list[float | None], list[bool]]:
    """Spec 68: fit the DI on **the fold's training rows** and score every test row.

    The reference set is the predictor's training rows, restricted per pair to the last
    `prediction.di_window_days` of the training window and subsampled to at most
    `prediction.di_reference_rows` with `seeds.train`. **Never the BUY subset**: fitted on
    BUY rows the DI learns that "normal" means a BUY-shaped setup and then vetoes every
    ordinary market state, which raises the veto rate, leaves a handful of clean-looking
    trades and flatters the leaderboard, with nothing going red.

    The caller never chooses the rows. This function reads the fold's training frame
    itself, which is the structural half of that guarantee — spec 68's scope limit says in
    as many words not to accept a caller who passes them.

    Returns `(fit, di per test row, refusal per test row)`, with the fit `None` and the
    scores null while `prediction.di_percentile` is absent: that value is the operator's
    after the walk-forward reports, and nothing here defaults the number that decides when
    a model may refuse a trade.
    """
    from acsoe.modelling import di as di_module

    percentile = config.get("prediction.di_percentile")
    if percentile is None:
        return None, [None] * test.height, [False] * test.height

    window_days = int(_required(config, "prediction.di_window_days"))
    neighbours = int(_required(config, "prediction.di_neighbours"))
    cap = int(_required(config, "prediction.di_reference_rows"))

    eligible = _di_reference_rows(train, window_days)
    matrix = np.asarray(scaler.transform(_matrix(eligible, names)), dtype=np.float64)
    identity = [
        f"{row['pair']}|{int(row['decision_ts'])}"
        for row in eligible.select(["pair", "decision_ts"]).iter_rows(named=True)
    ]
    complete = [index for index, row in enumerate(matrix) if np.isfinite(row).all()]
    if len(complete) > cap:
        # Seeded, so the reference set is reproducible from the config plus the data.
        generator = np.random.default_rng(seed)
        complete = sorted(generator.choice(complete, size=cap, replace=False).tolist())
    matrix = matrix[complete]
    identity = [identity[index] for index in complete]

    fit = di_module.fit(
        matrix, identity, neighbours=neighbours, percentile=float(percentile)
    )
    values: list[float | None] = []
    refusals: list[bool] = []
    for row in x_test:
        if not np.isfinite(row).all():
            # An incomplete live vector is blocked by engine 8 rather than scored, and the
            # offline record says the same: a NaN compared against the threshold is False,
            # so scoring one would silently mean "not dissimilar".
            values.append(None)
            refusals.append(False)
            continue
        scored = di_module.score(fit, row)
        values.append(scored.di)
        refusals.append(scored.refused)
    return fit, values, refusals


def _di_reference_rows(train: pl.DataFrame, window_days: int) -> pl.DataFrame:
    """The last `window_days` of the training window, **per pair**.

    Per pair rather than globally, because a pair that stopped trading a month before the
    boundary would otherwise contribute nothing and its live vectors would all read as
    dissimilar — a veto on the thin pairs, produced by the reference set's shape rather
    than by anything about the market.
    """
    span = window_days * 86_400
    parts = [
        group.filter(pl.col("decision_ts") >= int(group["decision_ts"].max()) - span)
        for (_pair,), group in train.group_by(["pair"], maintain_order=True)
    ]
    return pl.concat(parts, how="vertical") if parts else train
# --------------------------------------------------------------------------- #
# The digest entry, and the artefacts
# --------------------------------------------------------------------------- #


def _empty_entry(fold: Fold, train_rows: int, test_rows: int) -> dict[str, Any]:
    """A fold that came out empty, reported rather than dropped.

    Spec 53's rule: a run that quietly produced four folds where the caller expected twelve
    reports metrics over a third of the data with nothing saying so. Every metric is null
    rather than zero, because a Brier of 0.0 is a perfect model.
    """
    return {
        "fold_index": int(fold.fold_index),
        "run_id": None,
        "train_start_ts": int(fold.train_start_ts),
        "train_end_ts": int(fold.train_end_ts),
        "test_start_ts": int(fold.test_start_ts),
        "test_end_ts": int(fold.test_end_ts),
        "rows": int(test_rows),
        "effective_sample_size": 0.0,
        "train_rows": int(train_rows),
        "train_effective_sample_size": 0.0,
        "brier": None,
        "base_rate_brier": None,
        "log_loss": None,
        "buy_count": 0,
        "buy_target_rate": None,
        "purged_count": int(fold.purged_count),
        "embargoed_count": int(fold.embargoed_count),
        "after_test_count": int(fold.after_test_count),
        "di_rows": None,
        "di_threshold": None,
        "di_refusal_rate": None,
        "skeptic_rows": 0,
        "is_empty": True,
    }


def _fold_entry(
    fold: Fold,
    *,
    train: pl.DataFrame,
    test: pl.DataFrame,
    probabilities: np.ndarray[Any, Any],
    buys: Sequence[bool],
    di_fit: Any,
    di_refusals: Sequence[bool],
) -> dict[str, Any]:
    """One fold's line in the digest.

    **`rows` is the test row count and `effective_sample_size` is the sum of the test
    weights**, because those are the rows every metric on this line is computed over and
    the operator's addition is that the effective size sits beside *that fold's row count*.
    The training pair is reported too, under its own names, because the size of what the
    model was fitted on is the other number a reader needs and neither substitutes for the
    other.
    """
    labels = [str(value) for value in test["label"]]
    codes = _codes(test)
    buy_labels = [label for label, buy in zip(labels, buys, strict=True) if buy]
    return {
        "fold_index": int(fold.fold_index),
        "run_id": None,
        "train_start_ts": int(fold.train_start_ts),
        "train_end_ts": int(fold.train_end_ts),
        "test_start_ts": int(fold.test_start_ts),
        "test_end_ts": int(fold.test_end_ts),
        "rows": int(test.height),
        "effective_sample_size": effective_sample_size(
            [float(value) for value in test["weight"]]
        ),
        "train_rows": int(train.height),
        "train_effective_sample_size": effective_sample_size(
            [float(value) for value in train["weight"]]
        ),
        "brier": _brier_of_target(probabilities, labels),
        "base_rate_brier": _base_rate_brier(labels),
        "log_loss": _log_loss(probabilities, codes),
        "buy_count": int(sum(1 for buy in buys if buy)),
        "buy_target_rate": (
            sum(1 for label in buy_labels if label == LABEL_TARGET) / len(buy_labels)
            if buy_labels
            else None
        ),
        "target_rate": sum(1 for label in labels if label == LABEL_TARGET) / max(len(labels), 1),
        "purged_count": int(fold.purged_count),
        "embargoed_count": int(fold.embargoed_count),
        "after_test_count": int(fold.after_test_count),
        "di_rows": None if di_fit is None else int(di_fit.rows),
        "di_threshold": None if di_fit is None else float(di_fit.threshold),
        "di_refusal_rate": (
            None
            if di_fit is None
            else sum(1 for value in di_refusals if value) / max(len(di_refusals), 1)
        ),
        "skeptic_rows": 0,
        "is_empty": False,
    }


def _new_run_dir(store: Any, models_dir: Path, run_id: str) -> Path:
    """The artefact directory for one fold, created once and never reused.

    With a store, `new_model_run_dir` does it and refuses an existing run atomically.
    Without one, the same `mkdir(exist_ok=False)` — **one primitive, not a second
    implementation of the refusal**: a check-then-create would leave a window in which two
    runs both see an absent directory, and an overwritten artefact makes every leaderboard
    row that referenced it a claim about a model that no longer exists.
    """
    if store is not None:
        maker = getattr(store, "new_model_run_dir", None)
        if callable(maker):
            return Path(str(maker(run_id)))
    directory = models_dir / run_id
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def _write_fold_artefacts(
    directory: Path,
    *,
    model: Any,
    calibrators: Sequence[Any],
    di_fit: Any,
    scaler: Scaler,
    names: Sequence[str],
    fold: Fold,
    train: pl.DataFrame,
    test: pl.DataFrame,
    buys: Sequence[bool],
    entry: Mapping[str, Any],
    run_id: str,
    config_digest: str,
    seed: int,
    now: datetime,
    assets: Sequence[str],
    mean_timeout: float,
    scaler_rows: pl.DataFrame,
    calibration_identity: str,
    calibration_rows: int,
    calibration_end_ts: int,
) -> None:
    """Write the model, the calibrators, the DI and the manifest into one directory.

    The model is LightGBM's own text dump rather than a pickle: a pickle in an artefact
    directory is code that runs when a model is loaded, and the load happens inside the
    process that places orders. The calibrators are JSON for the same reason — isotonic
    regression is a step function and a step function is two arrays.
    """
    (directory / "model.txt").write_bytes(
        model.booster_.model_to_string().encode("utf-8")
    )
    (directory / "calibrators.json").write_bytes(
        json.dumps(
            [
                None
                if calibrator is None
                else {
                    "x": [float(value) for value in calibrator.X_thresholds_],
                    "y": [float(value) for value in calibrator.y_thresholds_],
                }
                for calibrator in calibrators
            ],
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    if di_fit is not None:
        from acsoe.modelling import di as di_module

        di_module.save(di_fit, directory / "di.npz")

    training_identity = identity_digest(
        [str(value) for value in train["pair"]],
        [int(value) for value in train["decision_ts"]],
    )
    buy_rows = test.filter(pl.Series(values=list(buys), dtype=pl.Boolean))
    buy_identity = identity_digest(
        [str(value) for value in buy_rows["pair"]],
        [int(value) for value in buy_rows["decision_ts"]],
    )

    manifest = Manifest(
        run_id=run_id,
        created_at=now,
        config_digest=config_digest,
        seeds={"train": seed},
        feature_version=FEATURE_VERSION,
        feature_names=tuple(names),
        class_order=CLASS_ORDER,
        fold=FoldBounds(
            fold_index=int(fold.fold_index),
            train_start_ts=int(fold.train_start_ts),
            train_end_ts=int(fold.train_end_ts),
            test_start_ts=int(fold.test_start_ts),
            test_end_ts=int(fold.test_end_ts),
            train_rows=int(train.height),
            test_rows=int(test.height),
            purged_count=int(fold.purged_count),
            embargoed_count=int(fold.embargoed_count),
            after_test_count=int(fold.after_test_count),
        ),
        dataset={
            "pairs": sorted({str(value) for value in train["pair"].unique()}),
            "macro_assets": list(assets),
            "mean_timeout_return": mean_timeout,
        },
        metrics=dict(entry),
        training_identity=training_identity,
        buy_identity=buy_identity,
        extras={
            "calibrator": "isotonic-per-class-renormalised",
            "model": "lightgbm-multiclass-text",
            # **Identity, because no metric can see either of these.** A calibrator fitted
            # on the test window is a textbook leak that moves the Brier by less than any
            # honest tolerance, because isotonic regression is monotone and cannot
            # manufacture skill; a scaler fitted on train plus test changes a tree model's
            # output not at all and changes the DI's distances completely. Both survived
            # the whole suite as mutations until these two digests existed. Ruling 7 of
            # 2026-09-13: prove which rows a thing saw, never take a number it reported
            # about itself.
            "calibration_identity": calibration_identity,
            "calibration_rows": calibration_rows,
            "calibration_end_ts": calibration_end_ts,
            "scaler_identity": identity_digest(
                [str(value) for value in scaler_rows["pair"]],
                [int(value) for value in scaler_rows["decision_ts"]],
            ),
            "scaler_rows": int(scaler_rows.height),
            "di": None
            if di_fit is None
            else {
                "file": "di.npz",
                "rows": int(di_fit.rows),
                "neighbours": int(di_fit.neighbours),
                "percentile": float(di_fit.percentile),
                "threshold": float(di_fit.threshold),
                "reference_identity": identity_digest(
                    [entry_id.split("|")[0] for entry_id in di_fit.identity],
                    [int(entry_id.split("|")[1]) for entry_id in di_fit.identity],
                ),
            },
        },
    )
    write_run(directory, manifest=manifest, scaler=scaler)
# --------------------------------------------------------------------------- #
# The command line
# --------------------------------------------------------------------------- #
#
# `python -m acsoe.research.training --config config/default.yaml`. Deliberately **not** a
# subcommand of `acsoe research`: that command assembles the offline chain and runs engines
# 23 and 20, and training is neither an engine nor a chain. Spec 61's scope limit says so.

FIXTURE_DIGEST: Final = Path("tests") / "fixtures" / "walkforward_digest.json"


def _load_config(path: Path) -> Any:
    from acsoe.platform.config import load_config

    return load_config(path)


def _archive_frames(
    directory: Path, interval_s: int, wanted: Sequence[str]
) -> dict[str, pl.DataFrame]:
    """The archive frames for `wanted`, or for every pair when it is empty.

    **One `frame(pair)` call each, never `dict(replay.frames())`.** Since spec 79 the
    replay reads a pair from disk on demand and keeps nothing, so materialising the whole
    archive is now something a caller has to ask for — and asking for it to then throw 233
    of 234 away is what an earlier version of this function did, at five and a half
    minutes a run.

    **The whole-archive case is still a known limit and is stated rather than hidden.**
    Every pair's frame is held at once here, which is roughly 60 GB over 234 pairs at the
    measured 3 KB per bar. That is the same shape as the engine 23 problem specs 78 and 79
    exist for, one module over, and the fix is the same: build the dataset per pair and
    append row groups rather than concatenating at the end. Until then the full run is
    `--pairs`-bounded and this docstring is the warning.
    """
    from acsoe.research.replay import ArchiveReplay

    replay = ArchiveReplay.from_directory(directory, interval_s=interval_s)
    available = list(replay.report.pairs)
    if wanted:
        missing = [pair for pair in wanted if pair not in available]
        if missing:
            raise TrainingError(
                "the archive has no " + ", ".join(missing) + "; --pairs names archive "
                "spellings (XBTUSD), not live ones (BTC/USD). It holds "
                + str(len(available))
                + " pairs."
            )
        available = list(wanted)
    return {pair: replay.frame(pair) for pair in available}


def main(argv: Sequence[str] | None = None) -> int:
    """Assemble the dataset from the archive, walk it forward, and write the artefacts."""
    parser = argparse.ArgumentParser(
        prog="python -m acsoe.research.training",
        description=(
            "Train the predictor at the live retraining cadence over the historical "
            "archive, writing one artefact directory per fold and one digest per run."
        ),
    )
    parser.add_argument("--config", type=Path, default=Path("config") / "default.yaml")
    parser.add_argument("--archive", type=Path, default=Path("data") / "historical")
    parser.add_argument("--derived", type=Path, default=Path("data") / "derived")
    parser.add_argument(
        "--pairs",
        type=str,
        default="",
        help="comma-separated archive pair names; empty means every pair in the archive",
    )
    parser.add_argument("--max-folds", type=int, default=None)
    parser.add_argument(
        "--start",
        type=int,
        default=None,
        help="earliest decision bar to keep, unix seconds; a smoke-run bound, not a label rule",
    )
    parser.add_argument("--end", type=int, default=None, help="latest decision bar to keep")
    parser.add_argument(
        "--write-fixture",
        action="store_true",
        help=(
            "copy the digest to tests/fixtures/walkforward_digest.json, which is the "
            "committed evidence walkforward_weekly_retrain_reports_oos reads offline"
        ),
    )
    args = parser.parse_args(argv)

    config = _load_config(args.config)
    interval_s = int(_required(config, "timeframes.decision_bar_s"))
    wanted = [p.strip() for p in args.pairs.split(",") if p.strip()]
    macro_wanted = sorted(
        set(macro_pair_names(config.get("macro") or {}, spelling="archive").values())
    )
    if wanted:
        # The macro pairs come too, or the run trains without a market backdrop and
        # produces a feature list engine 8 will refuse.
        wanted = sorted(set(wanted) | set(macro_wanted))
    frames = _archive_frames(args.archive, interval_s, wanted)

    labelled: dict[str, pl.DataFrame] = {}
    for pair, frame in frames.items():
        labels, _series = label_frame(
            frame, pair=pair, config=config, interval_s=interval_s
        )
        if labels.height:
            labelled[pair] = labels

    macro = macro_pair_names(config.get("macro") or {}, spelling="archive")
    available = {asset: pair for asset, pair in macro.items() if pair in frames}
    if len(available) != len(macro):
        # Silent macro loss would be the worst outcome: the model trains without a market
        # backdrop and the feature list still looks plausible right up to the moment
        # engine 8 refuses the artefact for a shape nobody chose.
        raise TrainingError(
            "the archive is missing the macro pair(s) "
            + ", ".join(sorted(set(macro.values()) - set(frames)))
            + ". Every run carries the macro columns, smoke runs included: training "
            "without them produces a different feature list and an artefact engine 8 "
            "will refuse."
        )

    dataset = build_dataset(labelled, frames, config=config, macro_archive=available or None)
    if args.start is not None:
        dataset = dataset.filter(pl.col("decision_ts") >= args.start)
    if args.end is not None:
        dataset = dataset.filter(pl.col("decision_ts") <= args.end)

    started = datetime.now(UTC)
    args.derived.mkdir(parents=True, exist_ok=True)
    dataset_path = args.derived / f"dataset_{started.strftime('%Y%m%dT%H%M%S')}.parquet"
    # Written once and reused by the loop, with its provenance **in the file**: a parquet
    # that cannot say where it came from is indistinguishable from one written by hand,
    # which is the rule `labelled_sample.parquet` was deposited under.
    dataset.write_parquet(
        dataset_path,
        metadata={
            "acsoe_provenance": json.dumps(
                {
                    "archive": str(args.archive),
                    "built_at": started.isoformat(),
                    "config_digest": _config_digest(config),
                    "feature_version": FEATURE_VERSION,
                    "interval_s": interval_s,
                    "macro_assets": sorted(available),
                    "pairs": sorted(labelled),
                    "pairs_below_floor": list(pairs_below_floor(labelled, config=config)),
                    "rows": int(dataset.height),
                    "start_ts": args.start,
                    "end_ts": args.end,
                },
                sort_keys=True,
            )
        },
    )

    report = train_walkforward(
        dataset,
        config=config,
        models_dir=Path(str(_required(config, "models.dir"))),
        derived_dir=args.derived,
        now=started,
        max_folds=args.max_folds,
    )

    if args.write_fixture:
        FIXTURE_DIGEST.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE_DIGEST.write_bytes(report.digest_path.read_bytes())

    excluded = pairs_below_floor(labelled, config=config)
    if excluded:
        sys.stdout.write(
            "excluded below `dataset.min_labelled_rows`: " + ", ".join(excluded) + "\n"
        )
    sys.stdout.write(
        f"{report.run_id}: {len(report.folds)} fold(s), dataset {dataset_path}, "
        f"digest {report.digest_path}, out-of-sample {report.oos_path}\n"
    )
    for entry in report.folds:
        brier = entry.get("brier")
        base = entry.get("base_rate_brier")
        sys.stdout.write(
            "  fold {index:>3}  rows {rows:>8}  effective {eff:>10.1f}  "
            "brier {brier}  base {base}\n".format(
                index=entry["fold_index"],
                rows=entry["rows"],
                eff=float(entry["effective_sample_size"]),
                brier="   n/a" if brier is None else f"{float(brier):.4f}",
                base="   n/a" if base is None else f"{float(base):.4f}",
            )
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through `python -m`
    raise SystemExit(main())
