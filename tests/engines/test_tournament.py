"""Spec 74 — engine 20 `tournament`.

Against a **real** `StoreClient` on a temporary migrated database and a digest a real training
run wrote. Nothing here fakes the store: a fake would be a second implementation of the one
table this engine exists to fill, and the idempotence rule is a property of what is already
in that table rather than of anything the engine remembers.

Four things are worth more than the rest and each has its own tests. **It never promotes** —
`promoted` is false on every row and the four Phase 7 metrics stay null, because a number
written into them now is one somebody reads later as a measurement. **Every score comes from
the out-of-sample rows**, recomputed here by a route the engine does not share — the digest's
own fold windows rather than `fold_index` — and a digest that disagrees with its rows writes
nothing. **It is idempotent on `(model_id, model_version, fold)`**, checked through the
store's own existence read rather than through the console's newest-fifty. And **the Brier
extremes carry their base rates**, because a Brier alone ranks which folds had the rarest
targets.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import require_module
from tests.engines.test_prediction import DI_PERCENTILE, Wrapped

pl = require_module("polars", reason="polars is not installed")
np = require_module("numpy", reason="numpy is not installed")
require_module("lightgbm", reason="lightgbm is not installed")

from acsoe.clients.store.client import StoreClient  # noqa: E402
from acsoe.clients.store.contracts import LeaderboardRow, to_micros  # noqa: E402
from acsoe.core.contracts import EngineStatus  # noqa: E402
from acsoe.engines.tournament.contracts import (  # noqa: E402
    MODEL_ID,
    REASON_DIGEST_MISMATCH,
    REASON_NO_DIGEST,
    REASON_NO_OOS,
    REASON_NO_STORE,
    TournamentState,
)
from acsoe.engines.tournament.engine import TournamentEngine  # noqa: E402

FOLDS = 3

#: Later than the training run's `created_at` (2026-09-13 12:00), which is what a real
#: `acsoe research` over a finished run looks like. The shared `engine_context` clock is
#: 2026-01-01, **earlier** than the run, so a test about which of the two instants
#: `updated_at` carries could not tell them apart on it.
SCORED_AT = datetime(2026, 9, 20, 9, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def trained(tmp_path_factory: Any) -> Any:
    """A real training run: a digest, an out-of-sample parquet, and artefacts beside them."""
    from tests.harness.doubles import load_default_config
    from tests.research.test_training import NOW, dataset_for

    from acsoe.research import training

    config = load_default_config()
    root = tmp_path_factory.mktemp("tournament-run")
    return training.train_walkforward(
        dataset_for(config, random_walk=False),
        config=Wrapped(config, **{"prediction.di_percentile": DI_PERCENTILE}),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=FOLDS,
    )


@pytest.fixture
def store(migrated_db: Path) -> Any:
    """B's real client on a migrated temporary database."""
    client = StoreClient(migrated_db)
    try:
        yield client
    finally:
        client.close()


def context_for(engine_context: Any, store: Any, *, now: datetime | None = None) -> Any:
    object.__setattr__(engine_context.clients, "store", store)
    if now is None:
        return dataclasses.replace(engine_context)
    return dataclasses.replace(engine_context, now=now)


def run(
    engine_context: Any, store: Any, digest_path: Path | None, *, now: datetime | None = None
) -> Any:
    return TournamentEngine(digest_path=digest_path).process(
        context_for(engine_context, store, now=now), {}
    )


@pytest.fixture
def scored(engine_context: Any, store: Any, trained: Any) -> Any:
    result = run(engine_context, store, trained.digest_path)
    assert result.status is EngineStatus.OK, (result.data, result.reason)
    return result


def copied_run(
    trained: Any,
    directory: Path,
    *,
    digest: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    oos: Callable[[Any], Any] | None = None,
) -> Path:
    """The run's digest and out-of-sample file copied side by side, each optionally altered.

    The copy keeps the trainer's naming (`oos_<run_id>.parquet` beside the digest), because
    the engine derives one path from the other and a fixture that spelled it differently
    would be testing a layout nothing produces.
    """
    payload = json.loads(trained.digest_path.read_bytes().decode("utf-8"))
    if digest is not None:
        payload = digest(payload)
    frame = pl.read_parquet(trained.oos_path)
    if oos is not None:
        frame = oos(frame)
    directory.mkdir(parents=True, exist_ok=True)
    digest_path = directory / trained.digest_path.name
    digest_path.write_bytes(json.dumps(payload, sort_keys=True, indent=2).encode("utf-8"))
    frame.write_parquet(directory / f"oos_{payload['run_id']}.parquet")
    return digest_path


# --------------------------------------------------------------------------- #
# Registry and the seam
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table() -> None:
    engine = TournamentEngine()
    assert engine.name == "tournament"
    assert engine.number == 20
    assert engine.is_gate is False


def test_the_constructor_takes_digest_path_as_a_keyword() -> None:
    """The seam `cli/research.py` calls by name, agreed with A-2 rather than discovered.

    That module raises loudly if this keyword does not exist rather than falling back to a
    no-argument call — which is how engine 23 spent a phase green against a labeller
    signature that never existed. This is the other half of that agreement.
    """
    import inspect

    signature = inspect.signature(TournamentEngine.__init__)
    parameter = signature.parameters["digest_path"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None


def test_the_research_cli_can_build_it(trained: Any) -> None:
    """End to end through A's own factory, not by importing the class here.

    `build_offline_chain` resolves this engine by name and by keyword. A test that
    constructed it directly would pass against a seam neither side could actually use.
    """
    from acsoe.cli.research import build_offline_chain

    chain = build_offline_chain(digest_path=trained.digest_path)
    tournament = [engine for engine in chain if engine.name == "tournament"]
    assert tournament, "the offline chain does not carry engine 20"
    assert tournament[0].number == 20


# --------------------------------------------------------------------------- #
# The refusals
# --------------------------------------------------------------------------- #


def test_with_no_digest_it_blocks(engine_context: Any, store: Any) -> None:
    result = run(engine_context, store, None)
    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_NO_DIGEST


def test_with_a_digest_that_is_not_one_it_blocks(
    engine_context: Any, store: Any, tmp_path: Path
) -> None:
    """A readable JSON file that is not a training digest. Not a crash: the message says
    which field is missing, because "engine 20 failed" sends a reader to the wrong file."""
    path = tmp_path / "not-a-digest.json"
    path.write_bytes(b'{"run_id": "x"}\n')
    result = run(engine_context, store, path)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_NO_DIGEST
    assert "folds" in (result.reason or "")


def test_with_the_out_of_sample_file_missing_it_blocks(
    engine_context: Any, store: Any, trained: Any, tmp_path: Path
) -> None:
    """A leaderboard written without the out-of-sample rows would report zero trades for
    every model, which reads as a model nobody traded rather than as a file nobody found."""
    copied = tmp_path / trained.digest_path.name
    copied.write_bytes(trained.digest_path.read_bytes())
    result = run(engine_context, store, copied)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_NO_OOS
    assert result.data["run_id"] == trained.run_id


def test_with_no_store_it_blocks_rather_than_reporting_success(
    engine_context: Any, trained: Any
) -> None:
    """A research run that reported success having written nothing is the failure this
    engine exists to make impossible; Phase 6's router would weight by an empty table."""
    object.__setattr__(engine_context.clients, "store", None)
    result = TournamentEngine(digest_path=trained.digest_path).process(engine_context, {})
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_NO_STORE


# --------------------------------------------------------------------------- #
# The rows
# --------------------------------------------------------------------------- #


def test_it_writes_one_row_per_fold(scored: Any, store: Any, trained: Any) -> None:
    rows = store.leaderboard(limit=200)
    assert len(rows) == len(trained.folds)
    assert scored.data["rows_written"] == len(trained.folds)
    assert scored.data["rows_skipped"] == 0
    assert scored.data["folds_empty"] == 0
    assert {row.fold for row in rows} == {
        str(entry["fold_index"]) for entry in trained.folds
    }


def test_every_row_identifies_the_model_version_and_the_run_that_made_it(
    scored: Any, store: Any, trained: Any
) -> None:
    """**The version is the fold's own artefact run id**, not the parent training run.

    Each fold writes a separate artefact directory and each is a model somebody could
    promote; `training_run_id` is what groups them back into one walk-forward. A leaderboard
    keyed on the parent would make every fold of a run look like one model with several
    scores, and Phase 6's router would weight it as one.
    """
    del scored
    versions = set(trained.fold_runs)
    rows = store.leaderboard(limit=200)
    assert {row.model_version for row in rows} == versions
    for row in rows:
        assert row.model_id == MODEL_ID
        assert row.training_run_id == trained.run_id
        assert row.model_version != trained.run_id
        assert (trained.models_dir / row.model_version / "manifest.json").is_file(), (
            f"{row.model_version} names no artefact; a leaderboard row must name a model "
            "somebody could load"
        )
        assert row.trained_at > 0


def test_no_row_is_promoted_and_the_phase_7_metrics_stay_null(
    scored: Any, store: Any
) -> None:
    """Spec 74's first scope limit and the named mutation's target.

    A Sharpe over label returns with no friction, no position sizing and no holding period is
    not a worse Sharpe — it is a different quantity wearing the name, and the person who reads
    it later will not be the person who wrote it.
    """
    del scored
    rows = store.leaderboard(limit=200)
    assert rows
    for row in rows:
        assert row.promoted is False
        assert row.sharpe is None
        assert row.deflated_sharpe is None
        assert row.alpha is None
        assert row.beta is None


def _half_open_window(oos: Any, entry: dict[str, Any]) -> Any:
    """A fold's out-of-sample rows chosen **by the digest's own test window**, `[start, end)`.

    Deliberately not the engine's route. The engine selects by `fold_index`; this selects by
    the timestamps the splitter drew the fold from. The two agree only while every row sits in
    exactly one half-open window, so an engine that drew its own boundary — inclusive at the
    end, or on `label_window_end_ts` — disagrees with this on the row that sits on the edge.
    """
    return oos.filter(
        (pl.col("decision_ts") >= int(entry["test_start_ts"]))
        & (pl.col("decision_ts") < int(entry["test_end_ts"]))
    )


def test_the_fixture_has_a_row_on_a_fold_boundary(trained: Any) -> None:
    """The premise every boundary assertion below rests on, asserted rather than assumed.

    If no out-of-sample row sat exactly on a fold's `test_end_ts`, an inclusive window and a
    half-open one would select the same rows and nothing in this file could tell them apart.
    """
    oos = pl.read_parquet(trained.oos_path)
    stamps = {int(value) for value in oos["decision_ts"]}
    edges = [int(entry["test_end_ts"]) for entry in trained.folds[:-1]]
    assert edges and all(edge in stamps for edge in edges), edges


def test_the_trade_numbers_are_recomputed_from_the_fold_windows(
    scored: Any, store: Any, trained: Any
) -> None:
    """Ruling 7: recomputed here, by a route the engine does not share.

    `n_trades`, `win_rate` and `net_pnl` are counts over rows this test can select for itself
    from each fold's `[test_start_ts, test_end_ts)`. A row that agreed with the digest and
    disagreed with the data would be caught, and so would a boundary drawn one bar wide.
    """
    del scored
    oos = pl.read_parquet(trained.oos_path)
    by_fold = {row.fold: row for row in store.leaderboard(limit=200)}
    for entry in trained.folds:
        buys = _half_open_window(oos, entry).filter(pl.col("is_buy"))
        labels = [str(value) for value in buys["label"]]
        row = by_fold[str(int(entry["fold_index"]))]
        assert row.n_trades == len(labels)
        assert labels, "a fold with no BUY call cannot prove the win rate"
        assert row.win_rate == pytest.approx(
            sum(1 for label in labels if label == "target") / len(labels)
        )
        expected = sum(
            (Decimal(repr(float(value))) for value in buys["return_pct"]), Decimal(0)
        )
        assert Decimal(str(row.net_pnl)) == expected


def test_the_win_rate_counts_only_the_targets_the_predictor_called(
    engine_context: Any, store: Any, trained: Any, tmp_path: Path
) -> None:
    """A target the predictor did not call BUY is a trade it never made, and not a win.

    **The trained fixture cannot show this on its own**: it is learnable by construction and
    every target row in it is a BUY call, so targets over all rows equal targets over BUY
    calls, and a win rate counting the first survived this file once. So the copy turns a
    handful of fold 0's non-BUY stops into missed targets, and restates that fold's Brier and
    base rate from the altered rows so the digest still agrees with them — the change is to
    the outcomes, not a disagreement between the files.
    """
    fold = int(trained.folds[0]["fold_index"])

    def miss_targets(frame: Any) -> Any:
        ordinal = pl.int_range(pl.len()).over(["fold_index", "is_buy", "label"])
        missed = (
            (pl.col("fold_index") == fold)
            & ~pl.col("is_buy")
            & (pl.col("label") == "stop")
            & (ordinal < 5)
        )
        return frame.with_columns(
            pl.when(missed).then(pl.lit("target")).otherwise(pl.col("label")).alias("label")
        )

    altered = miss_targets(pl.read_parquet(trained.oos_path))
    rows = altered.filter(pl.col("fold_index") == fold)
    hits = np.asarray([1.0 if str(v) == "target" else 0.0 for v in rows["label"]])
    probabilities = np.asarray([float(v) for v in rows["p_target"]])
    rate = float(np.mean(hits))

    def restate(payload: dict[str, Any]) -> dict[str, Any]:
        payload["folds"][0]["brier"] = float(np.mean((probabilities - hits) ** 2))
        payload["folds"][0]["base_rate_brier"] = rate * (1.0 - rate)
        return payload

    path = copied_run(trained, tmp_path / "run", digest=restate, oos=miss_targets)
    missed = rows.filter(~pl.col("is_buy") & (pl.col("label") == "target")).height
    assert missed == 5, "the premise: fold 0 now has targets the predictor did not call"

    result = run(engine_context, store, path)
    assert result.status is EngineStatus.OK, result.reason
    buys = rows.filter(pl.col("is_buy"))
    wins = buys.filter(pl.col("label") == "target").height
    row = {r.fold: r for r in store.leaderboard(limit=200)}[str(fold)]
    assert row.n_trades == buys.height
    assert row.win_rate == pytest.approx(wins / buys.height)
    assert row.win_rate != pytest.approx((wins + missed) / buys.height)


def test_the_brier_is_recomputed_from_the_out_of_sample_probabilities(
    scored: Any, store: Any, trained: Any
) -> None:
    """The headline number, from the rows, by the fold window rather than by `fold_index`.

    The out-of-sample file carries the **calibrated** `p_target`, so the Brier is a property
    of rows anybody can read. A leaderboard Brier taken from anywhere else — the training
    rows, the calibration tail, a digest describing a different selection — differs here.
    """
    del scored
    oos = pl.read_parquet(trained.oos_path)
    by_fold = {row.fold: row for row in store.leaderboard(limit=200)}
    for entry in trained.folds:
        rows = _half_open_window(oos, entry)
        hits = np.asarray([1.0 if str(v) == "target" else 0.0 for v in rows["label"]])
        probabilities = np.asarray([float(v) for v in rows["p_target"]])
        expected = float(np.mean((probabilities - hits) ** 2))
        row = by_fold[str(int(entry["fold_index"]))]
        assert row.brier == pytest.approx(expected, abs=1e-12)
        # And the digest said the same, which is what lets the engine refuse when it does not.
        assert float(entry["brier"]) == pytest.approx(expected, abs=1e-12)


def test_the_reporting_currency_travels_with_the_money(
    scored: Any, store: Any, engine_context: Any
) -> None:
    """A money column with no currency is a number nobody can add up."""
    expected = str(engine_context.config.get("trading.base_reporting_currency"))
    assert scored.data["reporting_currency"] == expected
    for row in store.leaderboard(limit=200):
        assert row.reporting_currency == expected


# --------------------------------------------------------------------------- #
# The two instants on a row
# --------------------------------------------------------------------------- #


def test_updated_at_is_when_the_row_was_written_and_moves_the_console_watermark(
    engine_context: Any, store: Any, trained: Any
) -> None:
    """`trained_at` is when the run was trained; `updated_at` is `context.now`.

    `leaderboard` is one of the tables the console's poll watermark reads, and the watermark
    only moves for rows stamped from the injected clock. The console's current watermark is
    stood in for by one earlier row written between training and scoring: a row stamped with
    its training time lands **under** that watermark, the console never pushes, and the
    screen goes on showing the old leaderboard.
    """
    trained_at = int(
        datetime.fromisoformat(str(trained.digest["created_at"])).timestamp() * 1_000_000
    )
    earlier = to_micros(datetime(2026, 9, 15, tzinfo=UTC))
    assert trained_at < earlier < to_micros(SCORED_AT)
    store.write_leaderboard_entry(
        LeaderboardRow(
            model_id="some-earlier-model",
            model_version="v0",
            trained_at=earlier,
            n_trades=0,
            updated_at=earlier,
        )
    )
    assert store.watermark() == earlier

    result = run(engine_context, store, trained.digest_path, now=SCORED_AT)
    assert result.status is EngineStatus.OK, result.reason

    ours = [row for row in store.leaderboard(limit=200) if row.model_id == MODEL_ID]
    assert len(ours) == len(trained.folds)
    for row in ours:
        assert row.updated_at == to_micros(SCORED_AT)
        assert row.trained_at == trained_at
    assert store.watermark() == to_micros(SCORED_AT)


# --------------------------------------------------------------------------- #
# Empty folds, and a digest that does not add up
# --------------------------------------------------------------------------- #


def _with_an_empty_fold(payload: dict[str, Any]) -> dict[str, Any]:
    """The trainer's own empty-fold entry shape (`_empty_entry`), appended after the rest."""
    last = payload["folds"][-1]
    week = int(last["test_end_ts"]) - int(last["test_start_ts"])
    payload["folds"].append(
        {
            "fold_index": int(last["fold_index"]) + 1,
            "run_id": None,
            "train_start_ts": int(last["train_start_ts"]) + week,
            "train_end_ts": int(last["train_end_ts"]) + week,
            "test_start_ts": int(last["test_end_ts"]),
            "test_end_ts": int(last["test_end_ts"]) + week,
            "rows": 0,
            "effective_sample_size": 0.0,
            "train_rows": 0,
            "brier": None,
            "base_rate_brier": None,
            "buy_count": 0,
            "is_empty": True,
        }
    )
    return payload


def test_an_empty_fold_gets_no_row_because_it_trained_no_model(
    engine_context: Any, store: Any, trained: Any, tmp_path: Path
) -> None:
    """A leaderboard row names a model version somebody could weight or promote.

    The trainer writes no artefact for an empty fold, so a row for one would name a directory
    that does not exist, with a `net_pnl` of exactly zero that reads as a model which broke
    even rather than one that was never trained.
    """
    path = copied_run(trained, tmp_path / "run", digest=_with_an_empty_fold)
    result = run(engine_context, store, path)
    assert result.status is EngineStatus.OK, result.reason
    assert result.data["folds"] == len(trained.folds) + 1
    assert result.data["folds_empty"] == 1
    assert result.data["rows_written"] == len(trained.folds)
    rows = store.leaderboard(limit=200)
    assert {row.model_version for row in rows} == set(trained.fold_runs)
    assert str(len(trained.folds)) not in {row.fold for row in rows}


def test_a_fold_the_digest_calls_empty_while_its_rows_exist_is_refused(
    engine_context: Any, store: Any, trained: Any, tmp_path: Path
) -> None:
    """Skipping empty folds must not become a way to drop a fold that was scored.

    Without this, a digest that marked a real fold empty would lose that fold's model from
    the leaderboard silently, and the report's `folds_empty` would call it routine.
    """

    def mark_empty(payload: dict[str, Any]) -> dict[str, Any]:
        payload["folds"][1]["is_empty"] = True
        return payload

    path = copied_run(trained, tmp_path / "run", digest=mark_empty)
    result = run(engine_context, store, path)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_DIGEST_MISMATCH
    assert "empty" in (result.reason or "")
    assert store.leaderboard(limit=200) == ()


def test_a_trained_fold_with_no_run_id_is_refused_rather_than_given_an_invented_name(
    engine_context: Any, store: Any, trained: Any, tmp_path: Path
) -> None:
    def drop_run_id(payload: dict[str, Any]) -> dict[str, Any]:
        payload["folds"][1]["run_id"] = None
        return payload

    path = copied_run(trained, tmp_path / "run", digest=drop_run_id)
    result = run(engine_context, store, path)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_NO_DIGEST
    assert "run_id" in (result.reason or "")
    assert store.leaderboard(limit=200) == ()


@pytest.mark.parametrize(
    ("field", "change"),
    [
        ("brier", lambda value: float(value) - 0.01),
        ("base_rate_brier", lambda value: float(value) + 0.01),
        ("rows", lambda value: int(value) + 1),
        ("buy_count", lambda value: int(value) - 1),
    ],
)
def test_a_digest_that_disagrees_with_its_rows_writes_nothing(
    engine_context: Any,
    store: Any,
    trained: Any,
    tmp_path: Path,
    field: str,
    change: Callable[[Any], Any],
) -> None:
    """Two numbers for one fold means one file describes rows the other did not score.

    The disagreement is placed on the **last** fold, so a leaderboard written fold by fold
    would already hold the earlier folds' rows when it was found. It must hold none.
    """

    def alter(payload: dict[str, Any]) -> dict[str, Any]:
        payload["folds"][-1][field] = change(payload["folds"][-1][field])
        return payload

    path = copied_run(trained, tmp_path / "run", digest=alter)
    result = run(engine_context, store, path)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_DIGEST_MISMATCH
    assert field in (result.reason or "") or "row" in (result.reason or "")
    assert f"fold {trained.folds[-1]['fold_index']}" in (result.reason or "")
    assert store.leaderboard(limit=200) == ()


def test_rows_for_a_fold_the_digest_does_not_list_are_refused(
    engine_context: Any, store: Any, trained: Any, tmp_path: Path
) -> None:
    """Out-of-sample rows the digest never reported were scored by a model nobody can name."""
    path = copied_run(
        trained,
        tmp_path / "run",
        digest=lambda payload: {**payload, "folds": payload["folds"][:-1]},
    )
    result = run(engine_context, store, path)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_DIGEST_MISMATCH
    assert store.leaderboard(limit=200) == ()


def test_rows_moved_across_a_fold_boundary_are_refused(
    engine_context: Any, store: Any, trained: Any, tmp_path: Path
) -> None:
    """The boundary defect from the producer's side: the edge row reassigned to the fold before.

    The row on fold 0's `test_end_ts` belongs to fold 1. Relabelled as fold 0, every count in
    both folds shifts by one row and nothing about the file's shape changes — which is exactly
    the leak a scorer trusting `fold_index` alone would carry into the leaderboard.
    """
    edge = int(trained.folds[0]["test_end_ts"])

    def move(frame: Any) -> Any:
        return frame.with_columns(
            pl.when(pl.col("decision_ts") == edge)
            .then(pl.lit(int(trained.folds[0]["fold_index"])))
            .otherwise(pl.col("fold_index"))
            .cast(frame.schema["fold_index"])
            .alias("fold_index")
        )

    path = copied_run(trained, tmp_path / "run", oos=move)
    result = run(engine_context, store, path)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_DIGEST_MISMATCH
    assert store.leaderboard(limit=200) == ()


# --------------------------------------------------------------------------- #
# Idempotence
# --------------------------------------------------------------------------- #


def test_running_twice_writes_nothing_the_second_time(
    engine_context: Any, store: Any, trained: Any
) -> None:
    """`acsoe research` over the same digest twice must not double the leaderboard.

    A duplicate row looks exactly like a second training run, and Phase 6's router would
    weight one model as if it were two.
    """
    first = run(engine_context, store, trained.digest_path)
    assert first.data["rows_written"] == len(trained.folds)

    second = run(engine_context, store, trained.digest_path)
    assert second.status is EngineStatus.OK
    assert second.data["rows_written"] == 0
    assert second.data["rows_skipped"] == len(trained.folds)
    assert len(store.leaderboard(limit=200)) == len(trained.folds)


def test_the_existence_check_is_not_the_consoles_truncating_read(
    engine_context: Any, store: Any, trained: Any
) -> None:
    """The defect this avoids is invisible until the fifty-first fold.

    `leaderboard()` returns the newest fifty by design — it is the console's read. Deciding
    idempotence from it would start writing duplicates the moment a walk-forward had more
    folds than that, which the real archive will. The engine is watched here through the
    store's own existence read, so a change back to the truncating one is caught with three
    folds rather than with fifty-one.
    """
    calls: list[dict[str, Any]] = []
    original = type(store).leaderboard_entries

    def watched(self: Any, **kwargs: Any) -> Any:
        calls.append(dict(kwargs))
        return original(self, **kwargs)

    truncating: list[int] = []
    original_leaderboard = type(store).leaderboard

    def watched_leaderboard(self: Any, limit: int = 50) -> Any:
        truncating.append(limit)
        return original_leaderboard(self, limit)

    type(store).leaderboard_entries = watched  # type: ignore[method-assign]
    type(store).leaderboard = watched_leaderboard  # type: ignore[method-assign]
    try:
        run(engine_context, store, trained.digest_path)
    finally:
        type(store).leaderboard_entries = original  # type: ignore[method-assign]
        type(store).leaderboard = original_leaderboard  # type: ignore[method-assign]

    assert len(calls) == len(trained.folds), calls
    assert all(call["model_id"] == MODEL_ID for call in calls)
    assert truncating == [], (
        "engine 20 decided idempotence from the console's newest-fifty read. On a "
        "walk-forward with more folds than that it would silently write duplicates."
    )


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #


def test_the_brier_extremes_are_reported_with_their_base_rates(
    scored: Any, trained: Any
) -> None:
    """A Brier alone says nothing: 0.18 is excellent against a base rate of 50% and poor
    against one of 5%. Without the comparison the report ranks which folds had the rarest
    targets."""
    data = scored.data
    assert data["folds"] == len(trained.folds)
    by_fold = {str(int(entry["fold_index"])): entry for entry in trained.folds}
    briers = {fold: float(entry["brier"]) for fold, entry in by_fold.items()}
    assert data["best_fold"] in briers
    assert data["worst_fold"] in briers
    assert data["best_brier"] == pytest.approx(min(briers.values()))
    assert data["worst_brier"] == pytest.approx(max(briers.values()))
    # Each extreme's base rate is **that fold's**, not another fold's and not the run's.
    assert data["best_base_rate_brier"] == pytest.approx(
        float(by_fold[data["best_fold"]]["base_rate_brier"])
    )
    assert data["worst_base_rate_brier"] == pytest.approx(
        float(by_fold[data["worst_fold"]]["base_rate_brier"])
    )


def test_the_published_payload_is_json_serialisable(scored: Any) -> None:
    json.dumps(scored.data)


def test_the_published_shape_carries_no_sharpe_or_promotion(scored: Any) -> None:
    """The report cannot report a Phase 7 metric either, because it has no field for one."""
    del scored
    fields = set(TournamentState.model_fields)
    for forbidden in ("sharpe", "deflated_sharpe", "alpha", "beta", "promoted"):
        assert forbidden not in fields, forbidden
