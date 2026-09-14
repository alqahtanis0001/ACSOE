"""Rebuild the out-of-sample parquet and the walk-forward digest of an interrupted training run.

Operator ruling 2026-09-14. The full 234-pair run `train-20260913T205245-067b2b9d` died at fold
405 of 457, in the skeptic's uncapped matrix build, after writing folds 0 to 404. The trainer
writes its out-of-sample parquet and its digest only after the last fold, so neither exists.
This script rebuilds both from the 405 fold artefacts **without training anything**, and
refuses to write either unless every fold reproduces what the trainer itself recorded.

It must run on the code that produced the artefacts (`PYTHONPATH` pointing at a checkout of
the commit the run used), because it scores through the trainer's own arithmetic:
`research.training._matrix`, `Scaler.transform`, LightGBM's text model, `apply_calibration`,
`expected_move_pct`, `is_buy_call`, `_brier_of_target`, `_base_rate_brier`, `_log_loss`.

**For every fold**, before anything is written:

* `load_run` verifies every file's sha256 against the manifest and the exact feature order;
* the test rows are the dataset rows with `test_start_ts <= decision_ts < test_end_ts`,
  ordered `(decision_ts, pair)` as the trainer's sorted dataset ordered them — the splitter
  places every such row in the test set and purges none of them;
* the row count, Brier, base-rate Brier, log loss, BUY count, BUY target rate, target rate and
  effective sample size are recomputed and compared with the manifest's `metrics`, and the
  identity digest of the BUY rows with the manifest's `buy_identity`;
* the DI must be absent (`prediction.di_percentile` was absent for this run), so `di` is null
  and `di_refused` false, exactly as the trainer wrote them.

Any disagreement stops the script with nothing written. The digest says in its own `coverage`
block that it covers 405 of 457 folds, why, and how it was rebuilt.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

from acsoe.modelling import calibration
from acsoe.modelling.artefacts import identity_digest, load_run
from acsoe.modelling.expected_move import expected_move_pct, is_buy_call
from acsoe.modelling.features import FEATURE_VERSION
from acsoe.modelling.weights import effective_sample_size
from acsoe.platform.config import load_config
from acsoe.research import training
from acsoe.research.walkforward import read_settings

REPO = Path(sys.argv[1])
CONFIG = Path(sys.argv[2])
RUN_ID = "train-20260913T205245-067b2b9d"
DATASET = REPO / "data" / "derived" / "dataset_20260913T205245.parquet"
MODELS = REPO / "models"
DERIVED = REPO / "data" / "derived"
LOG = REPO / "logs" / "fullrun-20260913T214616.log"
TOLERANCE = 1e-12


def fail(message: str) -> None:
    sys.stdout.write("REFUSED: " + message + "\n")
    raise SystemExit(1)


def close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=TOLERANCE)


def main() -> int:
    for target in (DERIVED / f"oos_{RUN_ID}.parquet", DERIVED / f"walkforward_digest_{RUN_ID}.json"):
        if target.exists():
            fail(f"{target} already exists; this script never overwrites")

    config = load_config(CONFIG)
    config_digest = training._config_digest(config)
    interval_s = int(config.get("timeframes.decision_bar_s"))
    settings = read_settings(config)
    target_pct = float(config.get("barriers.target_pct"))
    stop_pct = float(config.get("barriers.stop_pct"))
    if config.get("prediction.di_percentile") is not None:
        fail("prediction.di_percentile is set in this config; the run trained without it")

    fold_dirs = sorted(
        (path for path in MODELS.glob(f"{RUN_ID}-f*") if path.is_dir()),
        key=lambda path: int(path.name.rsplit("-f", 1)[1]),
    )
    indices = [int(path.name.rsplit("-f", 1)[1]) for path in fold_dirs]
    if indices != list(range(len(indices))):
        fail(f"fold directories are not contiguous from 0: {indices[:5]}...{indices[-5:]}")

    dataset = pl.read_parquet(DATASET)
    sys.stdout.write(f"dataset {dataset.height} rows, {dataset.width} columns\n")
    stamps = dataset["decision_ts"]
    first, last = int(stamps.min()), int(stamps.max())
    # The splitter's own window arithmetic (`purged_walk_forward`): the first test window
    # opens one training window after the first decision bar and they roll weekly while the
    # window start is not past the last bar.
    expected_starts = []
    start = first + settings.training_window_s
    while start <= last:
        expected_starts.append(start)
        start += settings.test_window_s

    entries: list[dict] = []
    oos_parts: list[pl.DataFrame] = []
    worst: dict[str, float] = {}
    names_seen: tuple[str, ...] | None = None
    created_at: str | None = None
    for directory in fold_dirs:
        manifest_payload = json.loads((directory / "manifest.json").read_bytes().decode("utf-8"))
        names = tuple(manifest_payload["feature_names"])
        run = load_run(directory, expected_features=names, expected_version=FEATURE_VERSION)
        manifest = run.manifest
        fold = manifest.fold
        metrics = dict(manifest.metrics)
        index = int(fold.fold_index)
        if names_seen is None:
            names_seen = names
        elif names != names_seen:
            fail(f"fold {index} has a different feature list from fold 0")
        if manifest.config_digest != config_digest:
            fail(f"fold {index} was trained under config {manifest.config_digest}, this is {config_digest}")
        if fold.test_start_ts != expected_starts[index]:
            fail(f"fold {index} test_start_ts {fold.test_start_ts} is not the splitter's {expected_starts[index]}")
        if manifest.extras.get("di") is not None:
            fail(f"fold {index} carries a DI artefact; this script assumes none")
        created_at = manifest.created_at.isoformat()

        test = dataset.filter(
            (pl.col("decision_ts") >= fold.test_start_ts) & (pl.col("decision_ts") < fold.test_end_ts)
        ).sort(["decision_ts", "pair"])
        if test.height != fold.test_rows or test.height != int(metrics["rows"]):
            fail(f"fold {index}: {test.height} test rows, manifest says {fold.test_rows}/{metrics['rows']}")

        x_test = np.asarray(run.scaler.transform(training._matrix(test, names)), dtype=np.float64)
        booster = lgb.Booster(model_file=str(directory / "model.txt"))
        raw = np.asarray(booster.predict(x_test), dtype=np.float64)
        steps = calibration.from_json((directory / calibration.CALIBRATORS_NAME).read_bytes())
        probabilities = calibration.apply_calibration(raw, steps)
        mean_timeout = float(manifest.dataset["mean_timeout_return"])
        moves = [
            expected_move_pct(
                p_target=float(row[0]), p_stop=float(row[1]), p_timeout=float(row[2]),
                target_pct=target_pct, stop_pct=stop_pct, mean_timeout_return=mean_timeout,
            )
            for row in probabilities
        ]
        buys = [is_buy_call(value) for value in moves]

        labels = [str(value) for value in test["label"]]
        codes = training._codes(test)
        buy_labels = [label for label, buy in zip(labels, buys, strict=True) if buy]
        recomputed = {
            "brier": training._brier_of_target(probabilities, labels),
            "base_rate_brier": training._base_rate_brier(labels),
            "log_loss": training._log_loss(probabilities, codes),
            "buy_target_rate": (
                sum(1 for label in buy_labels if label == "target") / len(buy_labels) if buy_labels else None
            ),
            "target_rate": sum(1 for label in labels if label == "target") / max(len(labels), 1),
            "effective_sample_size": effective_sample_size([float(v) for v in test["weight"]]),
        }
        for key, value in recomputed.items():
            if not close(value, metrics.get(key)):
                fail(f"fold {index}: {key} recomputed {value!r}, manifest {metrics.get(key)!r}")
            if value is not None and metrics.get(key) is not None:
                worst[key] = max(worst.get(key, 0.0), abs(float(value) - float(metrics[key])))
        if sum(buys) != int(metrics["buy_count"]):
            fail(f"fold {index}: {sum(buys)} BUY calls recomputed, manifest {metrics['buy_count']}")
        buy_rows = test.filter(pl.Series(values=buys, dtype=pl.Boolean))
        identity = identity_digest(
            [str(v) for v in buy_rows["pair"]], [int(v) for v in buy_rows["decision_ts"]]
        )
        if identity != manifest.buy_identity:
            fail(f"fold {index}: BUY-row identity differs from the manifest")

        oos = test.select(
            ["pair", "decision_ts", "label_window_end_ts", "label", "return_pct", "weight"]
        ).with_columns(
            pl.lit(index).alias("fold_index"),
            pl.Series("p_target", probabilities[:, 0], dtype=pl.Float64),
            pl.Series("p_stop", probabilities[:, 1], dtype=pl.Float64),
            pl.Series("p_timeout", probabilities[:, 2], dtype=pl.Float64),
            pl.Series("expected_move_pct", moves, dtype=pl.Float64),
            pl.Series("is_buy", buys, dtype=pl.Boolean),
            pl.Series("di", [None] * test.height, dtype=pl.Float64),
            pl.Series("di_refused", [False] * test.height, dtype=pl.Boolean),
        ).select(training.OOS_COLUMNS)
        oos_parts.append(oos)
        entry = dict(metrics)
        entry["run_id"] = manifest.run_id
        entries.append(entry)
        if index % 25 == 0:
            sys.stdout.write(f"fold {index} verified: {test.height} rows, brier {recomputed['brier']:.6f}\n")
            sys.stdout.flush()

    assert names_seen is not None and created_at is not None
    written = len(entries)
    expected = len(expected_starts)
    missing_first = datetime.fromtimestamp(expected_starts[written], tz=UTC).date().isoformat()
    missing_last = datetime.fromtimestamp(expected_starts[-1], tz=UTC).date().isoformat()
    log_text = LOG.read_bytes().decode("utf-8", errors="replace")
    error_line = [line for line in log_text.splitlines() if "MemoryError" in line][-1:]
    script_bytes = Path(__file__).read_bytes()

    oos_frame = pl.concat(oos_parts, how="vertical")
    payload = {
        "run_id": RUN_ID,
        "created_at": created_at,
        "config_digest": config_digest,
        "feature_version": FEATURE_VERSION,
        "feature_names": list(names_seen),
        "class_order": list(training.CLASS_ORDER),
        "pairs": sorted({str(value) for value in dataset["pair"].unique()}),
        "rows": int(dataset.height),
        "effective_sample_size": effective_sample_size([float(v) for v in dataset["weight"]]),
        "folds": entries,
        "coverage": {
            "complete": False,
            "folds_written": written,
            "folds_expected": expected,
            "missing_fold_indices": [written, expected - 1],
            "missing_test_weeks": [missing_first, missing_last],
            "why": (
                "The training run died during fold "
                + str(written)
                + " of "
                + str(expected)
                + " (index "
                + str(written)
                + ") in _fit_skeptic -> _skeptic_matrix, when the scaler's transform of the "
                "skeptic's uncapped training matrix could not allocate. The skeptic for fold k "
                "trains on every eligible BUY call from folds before k, so its matrix grows "
                "every fold; by fold 404 it held 8,946,942 rows. Folds "
                + str(written)
                + " to "
                + str(expected - 1)
                + " (test weeks "
                + missing_first
                + " to "
                + missing_last
                + ") were never trained. By operator ruling of 2026-09-14 the run was not rerun "
                "or resumed, and this digest covers the folds that exist."
            ),
            "error": error_line[0].strip() if error_line else None,
            "log": str(LOG.relative_to(REPO)),
        },
        "rebuilt_from_artefacts": {
            "rebuilt_at": datetime.now(UTC).isoformat(),
            "script_sha256": hashlib.sha256(script_bytes).hexdigest(),
            "method": (
                "The trainer writes the out-of-sample parquet and this digest only after its "
                "last fold, so neither existed. Each fold's entry is that fold's own manifest "
                "`metrics`, written by the trainer; the out-of-sample rows were re-scored from "
                "each fold's verified artefacts (model.txt, calibrators.json, scaler.json, "
                "mean_timeout_return) over its test window, and accepted only because they "
                "reproduce the manifest's rows, brier, base_rate_brier, log_loss, buy_count, "
                "buy_target_rate, target_rate, effective_sample_size and buy_identity for every "
                "fold. Nothing was trained."
            ),
            "largest_absolute_differences": worst,
            "tolerance": TOLERANCE,
        },
        "notes": (
            "PARTIAL: covers "
            + str(written)
            + " of "
            + str(expected)
            + " folds; see `coverage`. The BUY-call target rate is reported per fold and is "
            "NOT compared against a break-even rate here. Break-even is a function of friction - "
            "live fees, the measured spread and slippage - none of which exists offline, and the "
            "reference figures in trading-invariants.md are marked for sanity-checking only and "
            "never for use in code. The comparison is the reader's."
        ),
    }
    oos_path = DERIVED / f"oos_{RUN_ID}.parquet"
    digest_path = DERIVED / f"walkforward_digest_{RUN_ID}.json"
    oos_frame.write_parquet(oos_path)
    digest_path.write_bytes(json.dumps(payload, sort_keys=True, indent=2, default=str).encode("utf-8") + b"\n")
    sys.stdout.write(
        f"verified and wrote {written} of {expected} folds: {oos_path} ({oos_frame.height} rows), "
        f"{digest_path}\nlargest differences {worst}\nscript sha256 {payload['rebuilt_from_artefacts']['script_sha256']}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
