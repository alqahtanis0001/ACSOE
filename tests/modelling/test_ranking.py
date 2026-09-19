"""Spec 144, the modelling half: engine 7's ranking by engine 8's expected move (R1, R11).

**The seam test here has no double in it.** The artefact is trained in a temporary root from the
constructed series, every feature row is the real engines 3, 5 and 6's output, and every number
the ranking produces is compared against what **the real engines 8 and 13** publish for the same
pair from the same artefact. The claim this module makes is "the chosen pair's expected move is
engine 8's by construction", and a test comparing the function against a restatement of engine 8
would be green against a ranking and an engine that had drifted apart together.

The universe is several *pairs* whose rows are engine 5's output on different tails of the same
series, renamed. Renaming is the one fabricated step and it is named: a pair's name is not a
feature, so the arithmetic under test cannot see it, and the alternative — training on several
real pairs — would put the fixture model's DI out of reach of any row it has not seen.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import require_module
from tests.engines.test_prediction import (
    MACRO_ARCHIVE,
    PAIR,
    Wrapped,
    complete_state,
    context_with,
)

require_module("polars", reason="polars is not installed")
require_module("lightgbm", reason="lightgbm is not installed")
require_module("sklearn", reason="scikit-learn is not installed")
np = require_module("numpy", reason="numpy is not installed")

from acsoe.core.contracts import EngineStatus  # noqa: E402
from acsoe.engines.anomaly.contracts import KEY_ANOMALY_RUN_ID  # noqa: E402
from acsoe.engines.anomaly.engine import AnomalyEngine  # noqa: E402
from acsoe.engines.prediction.contracts import KEY_PREDICTION_RUN_ID  # noqa: E402
from acsoe.engines.prediction.engine import PredictionEngine  # noqa: E402
from acsoe.modelling import ranking  # noqa: E402
from acsoe.modelling.features import MARKET_QUALITY_FEATURES  # noqa: E402

#: The same two percentiles the committed config carries. Supplied through the wrapper so the
#: fixture does not depend on a later edit to `config/default.yaml`.
DI_PERCENTILE = 0.99
ANOMALY_PERCENTILE = 0.99

#: How many renamed pairs the universe holds, and the bar offset between their tails.
UNIVERSE = 6
STEP = 7
#: The name each tail gets, and the order the rows arrive in. Chosen so that alphabetical order,
#: arrival order and expected-move order are three different orders on this fixture; the order
#: test asserts that they are, so a fixture change that made two of them coincide goes red there
#: rather than quietly turning an order assertion into a sort-by-name check.
NAMES = (1, 2, 3, 4, 5, 6)
ARRIVAL = (2, 5, 0, 3, 1, 4)

TARGET_PCT = 0.03
STOP_PCT = 0.015


@pytest.fixture(scope="module")
def trained(tmp_path_factory: Any) -> tuple[Path, str]:
    from acsoe.research import training
    from tests.harness.doubles import load_default_config
    from tests.research.test_training import NOW, dataset_for

    config = load_default_config()
    root = tmp_path_factory.mktemp("ranking-models")
    report = training.train_walkforward(
        dataset_for(config, random_walk=True, macro_archive=MACRO_ARCHIVE),
        config=Wrapped(
            config,
            **{
                "prediction.di_percentile": DI_PERCENTILE,
                "anomaly.threshold_percentile": ANOMALY_PERCENTILE,
            },
        ),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=1,
    )
    run_id = report.fold_runs[0]
    for name in ("di.npz", "anomaly.joblib"):
        assert (report.models_dir / run_id / name).is_file(), (
            f"the fixture trained no {name}, so the ranking could only ever refuse"
        )
    return report.models_dir, run_id


@pytest.fixture(scope="module")
def walk_bars() -> list[dict[str, Any]]:
    """The tail of the **random-walk** series the fixture model was trained on.

    Not engine 8's own `bars` fixture, which is the learnable series: a model trained on it
    calls every bar a stop with certainty, so every pair's expected move is the same number and
    an order test over them is a test of the tie-break alone. On the random walk the
    probabilities move from bar to bar, which is what a ranking needs to have something to rank.
    """
    from tests.engines.test_feature import BAR
    from tests.research.test_training import candle_frame

    frame = candle_frame(PAIR, interval_s=BAR, random_walk=True)
    return [
        {
            "ts": int(row["ts"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "trades": int(row["trades"]),
        }
        for row in frame.tail(300).to_dicts()
    ]


@pytest.fixture(scope="module")
def artefacts(trained: tuple[Path, str]) -> Any:
    root, run_id = trained
    return ranking.load_ranking_artefacts(root / run_id, root / run_id)


@pytest.fixture
def universe(
    engine_context: Any,
    walk_bars: list[dict[str, Any]],
    trained: tuple[Path, str],
) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """``(rows, macro, context)``: engine 5's rows on six tails of the series, renamed.

    Named so that **alphabetical order is the reverse of arrival order** and neither is the
    expected-move order the tests below compute, which is what makes an order assertion able to
    tell a ranking from a pass-through.
    """
    root, run_id = trained
    rows: dict[str, Any] = {}
    macro: dict[str, Any] = {}
    context: Any = None
    for index in ARRIVAL:
        tail = walk_bars[: len(walk_bars) - index * STEP]
        state, context = complete_state(engine_context, tail, root, run_id)
        name = f"P{NAMES[index]}USD"
        rows[name] = dict(state["feature"]["pairs"][PAIR])
        # Each tail's macro columns belong to its own bar; the ranking is handed one mapping
        # per tick live, so each pair's macro values are folded into its row instead.
        rows[name].update(state["macro_context"]["features"])
    return rows, macro, context


def engine_verdicts(
    context: Any, trained: tuple[Path, str], rows: dict[str, Any], pair: str
) -> tuple[Any, Any]:
    """What the real engines 13 and 8 publish when ``pair`` is the candidate."""
    root, run_id = trained
    state = {
        "feature": {"pairs": rows, "bar_ts": 0},
        "macro_context": {"features": {}},
        "scout": {"pair": pair},
    }
    context = context_with(
        context, root, **{KEY_PREDICTION_RUN_ID: run_id, KEY_ANOMALY_RUN_ID: run_id}
    )
    return AnomalyEngine().process(context, state), PredictionEngine().process(context, state)


def rank(rows: dict[str, Any], artefacts: Any, macro: dict[str, Any] | None = None) -> Any:
    return ranking.rank_by_expected_move(
        rows, macro or {}, artefacts, target_pct=TARGET_PCT, stop_pct=STOP_PCT
    )


# --------------------------------------------------------------------------- #
# The seam: every number is engine 8's and engine 13's, recomputed by them
# --------------------------------------------------------------------------- #


def test_every_ranked_expected_move_is_what_engine_8_publishes(
    universe: Any, artefacts: Any, trained: tuple[Path, str]
) -> None:
    """Spec 144's Check When Done, and the reason the function lives in `modelling/`.

    Compared as the **rendered decimal string**, the form engine 10 prices against the hurdle:
    ``Decimal`` equality would ignore a difference in the last digit of the float's shortest
    representation, and that digit is the number.
    """
    rows, macro, context = universe
    result = rank(rows, artefacts, macro)
    assert len(result.ranked) >= 3, (
        f"only {len(result.ranked)} of {UNIVERSE} pairs survived both gates, so there is no "
        f"order to compare; excluded {result.excluded}"
    )
    for entry in result.ranked:
        anomaly, prediction = engine_verdicts(context, trained, rows, entry.pair)
        assert anomaly.status is EngineStatus.OK, (entry.pair, anomaly.data)
        assert prediction.status is EngineStatus.OK, (entry.pair, prediction.data)
        assert format(Decimal(repr(entry.expected_move_pct)), "f") == (
            prediction.data["expected_move_pct"]
        ), entry.pair
        assert entry.p_target == prediction.data["p_target"]
        assert entry.p_stop == prediction.data["p_stop"]
        assert entry.p_timeout == prediction.data["p_timeout"]
        assert entry.anomaly_score == anomaly.data["score"], entry.pair
        # The one quantity equal within float rather than exactly: batching the DI turns a
        # one-row matrix product into a many-row one. Spec 137's tolerance.
        assert abs(entry.di - prediction.data["di"]) <= 1e-12, entry.pair


def test_an_excluded_pair_is_one_the_real_gates_refuse_for_the_same_reason(
    universe: Any, artefacts: Any, trained: tuple[Path, str]
) -> None:
    """R11 as a property: the ranking skips exactly what engines 13 and 8 would refuse.

    Three pairs are broken three ways — a market-quality hole (engine 13's inputs), a
    predictor-only hole (engine 8's inputs) and a vector moved far outside the training set
    (engine 8's DI) — and each gate is asked about each pair.
    """
    rows, macro, context = universe
    names = sorted(rows)
    non_quality = next(
        name for name in artefacts.feature_names if name not in MARKET_QUALITY_FEATURES
    )
    broken = dict(rows)
    broken[names[0]] = {**rows[names[0]], MARKET_QUALITY_FEATURES[0]: None}
    broken[names[1]] = {**rows[names[1]], non_quality: float("nan")}
    far = dict(rows[names[2]])
    for name in artefacts.feature_names:
        if name not in MARKET_QUALITY_FEATURES and not name.startswith("macro_"):
            far[name] = float(far[name]) * 50.0 + 50.0
    broken[names[2]] = far

    result = rank(broken, artefacts, macro)
    excluded = dict(result.excluded)
    assert excluded.get(names[0]) == ranking.EXCLUDED_ANOMALY_INPUTS_INCOMPLETE
    assert excluded.get(names[1]) == ranking.EXCLUDED_PREDICTION_INPUTS_INCOMPLETE
    assert excluded.get(names[2]) == ranking.EXCLUDED_DI_REFUSED
    ranked = {entry.pair for entry in result.ranked}
    assert ranked.isdisjoint(excluded), "a pair was both ranked and excluded"
    assert ranked | set(excluded) == set(broken), "a pair was neither ranked nor excluded"

    expected_codes = {
        names[0]: ("anomaly", "anomaly_inputs_incomplete"),
        names[1]: ("prediction", "prediction_inputs_incomplete"),
        names[2]: ("prediction", "di_refused"),
    }
    for pair, (which, code) in expected_codes.items():
        anomaly, prediction = engine_verdicts(context, trained, broken, pair)
        verdict = anomaly if which == "anomaly" else prediction
        assert verdict.status is EngineStatus.BLOCK, (pair, verdict.data)
        assert verdict.data["reason_code"] == code, (pair, verdict.data)


def test_a_score_above_the_anomaly_threshold_is_excluded_and_one_on_it_is_not(
    universe: Any, artefacts: Any
) -> None:
    """The threshold's direction and its boundary, as engine 13 draws them.

    The threshold is moved rather than the market, so the two cases differ in exactly one
    number: a score exactly on the line passes and one just past it is excluded.
    """
    rows, macro, _context = universe
    baseline = rank(rows, artefacts, macro)
    chosen = baseline.ranked[0]
    on_the_line = dataclasses.replace(artefacts, anomaly_threshold=chosen.anomaly_score)
    assert chosen.pair in {entry.pair for entry in rank(rows, on_the_line, macro).ranked}
    below = dataclasses.replace(
        artefacts, anomaly_threshold=float(np.nextafter(chosen.anomaly_score, -np.inf))
    )
    assert dict(rank(rows, below, macro).excluded).get(chosen.pair) == (
        ranking.EXCLUDED_MARKET_ANOMALOUS
    )


def test_a_di_on_the_threshold_is_ranked_and_one_past_it_is_excluded(
    universe: Any, artefacts: Any
) -> None:
    """The DI's boundary: strictly greater refuses, as `modelling.di.score` draws it."""
    rows, macro, _context = universe
    chosen = rank(rows, artefacts, macro).ranked[0]
    on_the_line = dataclasses.replace(
        artefacts, di=dataclasses.replace(artefacts.di, threshold=chosen.di)
    )
    assert chosen.pair in {entry.pair for entry in rank(rows, on_the_line, macro).ranked}
    below = dataclasses.replace(
        artefacts,
        di=dataclasses.replace(
            artefacts.di, threshold=float(np.nextafter(chosen.di, -np.inf))
        ),
    )
    assert dict(rank(rows, below, macro).excluded).get(chosen.pair) == (
        ranking.EXCLUDED_DI_REFUSED
    )


# --------------------------------------------------------------------------- #
# The order
# --------------------------------------------------------------------------- #


def test_the_order_is_expected_move_descending_whatever_order_the_rows_arrive_in(
    universe: Any, artefacts: Any
) -> None:
    """Arrival order, alphabetical order and expected-move order are three different orders
    here, so an implementation returning either of the first two goes red."""
    rows, macro, _context = universe
    result = rank(rows, artefacts, macro)
    moves = [entry.expected_move_pct for entry in result.ranked]
    assert moves == sorted(moves, reverse=True)
    pairs = [entry.pair for entry in result.ranked]
    assert pairs != sorted(pairs), (
        "the expected-move order happens to be alphabetical, so this fixture cannot tell a "
        "ranking from a sort by name"
    )
    arrival = [pair for pair in rows if pair in set(pairs)]
    assert pairs != arrival, "the expected-move order happens to be the arrival order"
    reversed_rows = dict(reversed(list(rows.items())))
    assert [entry.pair for entry in rank(reversed_rows, artefacts, macro).ranked] == pairs


def test_equal_expected_moves_are_ordered_by_pair_name(universe: Any, artefacts: Any) -> None:
    """Ties by name, ascending. Two identical rows under two names are an exact tie."""
    rows, macro, _context = universe
    source = next(iter(rows.values()))
    twins = {"ZZZUSD": dict(source), "AAAUSD": dict(source)}
    result = rank(twins, artefacts, macro)
    assert [entry.pair for entry in result.ranked] == ["AAAUSD", "ZZZUSD"], result


def test_macro_columns_are_read_from_the_macro_mapping_before_the_row(
    universe: Any, artefacts: Any
) -> None:
    """Engine 8 reads a name present in engine 6's mapping from that mapping, and the row
    otherwise. A macro hole is therefore a prediction-input hole."""
    rows, _macro, _context = universe
    pair = sorted(rows)[0]
    macro_name = next(name for name in artefacts.feature_names if name.startswith("macro_"))
    result = rank({pair: rows[pair]}, artefacts, {macro_name: None})
    assert dict(result.excluded) == {pair: ranking.EXCLUDED_PREDICTION_INPUTS_INCOMPLETE}


def test_an_empty_universe_ranks_nothing() -> None:
    """No pair is no candidate, not an error: engine 7's PASS rather than a block."""
    result = ranking.rank_by_expected_move(
        {}, {}, None, target_pct=TARGET_PCT, stop_pct=STOP_PCT  # type: ignore[arg-type]
    )
    assert result.ranked == ()
    assert result.excluded == ()


# --------------------------------------------------------------------------- #
# Loading: what engines 8 and 13 refuse, this refuses
# --------------------------------------------------------------------------- #


def copied(trained: tuple[Path, str], tmp_path: Path) -> Path:
    root, run_id = trained
    target = tmp_path / run_id
    shutil.copytree(root / run_id, target)
    return target


def rewrite_manifest(directory: Path, edit: Any) -> None:
    path = directory / "manifest.json"
    payload = json.loads(path.read_bytes().decode("utf-8"))
    edit(payload)
    path.write_bytes(json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n")


def test_an_artefact_with_no_anomaly_threshold_is_refused(
    trained: tuple[Path, str], tmp_path: Path
) -> None:
    directory = copied(trained, tmp_path)
    rewrite_manifest(directory, lambda payload: payload["extras"]["anomaly"].update(threshold=None))
    with pytest.raises(ranking.RankingError, match="records no anomaly threshold"):
        ranking.load_ranking_artefacts(directory, directory)


def test_an_artefact_with_no_di_is_refused(trained: tuple[Path, str], tmp_path: Path) -> None:
    """The file is removed **and** unhashed, so the refusal is the DI's own rather than
    `load_run`'s complaint about a hashed file gone missing."""
    directory = copied(trained, tmp_path)
    (directory / "di.npz").unlink()
    rewrite_manifest(directory, lambda payload: payload["files"].pop("di.npz"))
    with pytest.raises(ranking.RankingError, match=r"carries no di\.npz"):
        ranking.load_ranking_artefacts(directory, directory)


def test_a_tampered_artefact_is_refused(trained: tuple[Path, str], tmp_path: Path) -> None:
    directory = copied(trained, tmp_path)
    (directory / "calibrators.json").write_bytes(b"[]\n")
    with pytest.raises(ranking.RankingError, match="sha256"):
        ranking.load_ranking_artefacts(directory, directory)


def test_detector_inputs_other_than_the_market_quality_features_are_refused(
    trained: tuple[Path, str], tmp_path: Path
) -> None:
    directory = copied(trained, tmp_path)
    rewrite_manifest(
        directory,
        lambda payload: payload["extras"]["anomaly"].update(
            input_names=list(MARKET_QUALITY_FEATURES[:-1])
        ),
    )
    with pytest.raises(ranking.RankingError, match="inputs other than the market-quality"):
        ranking.load_ranking_artefacts(directory, directory)


def test_a_run_whose_feature_order_is_permuted_is_refused(
    trained: tuple[Path, str], tmp_path: Path
) -> None:
    """The order check engine 8 makes, and the one a loader reading the order from the artefact
    itself could never make: the manifest and the scaler are permuted together and every hash
    is made to agree, so the only thing left to object is the order rebuilt from
    `modelling/features.py` and `modelling/macro.py`."""
    from acsoe.modelling.artefacts import sha256_file

    directory = copied(trained, tmp_path)
    scaler_path = directory / "scaler.json"
    scaler = json.loads(scaler_path.read_bytes().decode("utf-8"))
    for key in ("feature_names", "minimum", "maximum"):
        scaler[key][0], scaler[key][1] = scaler[key][1], scaler[key][0]
    scaler_path.write_bytes(json.dumps(scaler, sort_keys=True, indent=2).encode("utf-8") + b"\n")

    def permute(payload: dict[str, Any]) -> None:
        names = payload["feature_names"]
        names[0], names[1] = names[1], names[0]
        payload["files"]["scaler.json"] = sha256_file(scaler_path)

    rewrite_manifest(directory, permute)
    with pytest.raises(ranking.RankingError, match="wrong ORDER"):
        ranking.load_ranking_artefacts(directory, directory)
