"""Engine 7 `scout`, spec 144: the universe examined in order of engine 8's expected move.

Operator ruling R1 (2026-09-19) orders the filtered universe by the predictor's expected
move. R11 skips every pair the anomaly or DI gate would refuse. The arithmetic is C's
`modelling/ranking.py`. This file covers engine 7's half, in three parts.

1. **`rank_universe` directly**, on input where arrival order and the intended order
   disagree on every element. An end-to-end fixture cannot catch a ranking that only
   preserves arrival order, because the engine builds its scan set with `sorted`
   (tracker, Next Up).
2. **The engine against a stand-in ranking module.** It covers the wiring, what is
   published, and every way of being unable to rank. The stand-in is installed in
   `sys.modules`, so the engine's import path is exercised unchanged.
3. **The seam with no double in it.** The real `modelling/ranking.py` runs on a real
   trained artefact, and the real engines 13 and 8 are asked about every pair. The chosen
   pair's expected move is engine 8's, recomputed rather than read back. Reversing the
   ranking changes the candidate and changes no gate's verdict on any pair.
"""

from __future__ import annotations

import dataclasses
import sys
import types
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.engines.test_scout import (
    USD_PAIRS,
    FakeKrakenWithStream,
    build_state,
    write_equity,
)

# C's fixtures for the real ranking: a trained artefact and engine 5's rows on tails of
# its training series. Imported rather than copied, so this file and C's seam test
# judge the same universe. Importing the module fails loudly if it moves.
from tests.modelling import test_ranking as _ranking_fixtures

from acsoe.clients.store.client import StoreClient
from acsoe.core.contracts import EngineStatus
from acsoe.engines.scout.contracts import (
    CANDIDATE_FIELD,
    RANK_BY_EXPECTED_MOVE,
    RANK_RUN_IDS_FIELD,
    RANK_SKIPPED_FIELD,
    RANKED_FIELD,
    REASON_EMPTY_UNIVERSE,
    REASON_INPUTS_UNAVAILABLE,
    REASON_NO_RANKABLE_PAIR,
    rank_universe,
    select_candidate,
)
from acsoe.engines.scout.engine import RANKING_MODULE, ScoutEngine

# Registered here under C's names, and requested by name in `real_universe`.
trained = _ranking_fixtures.trained
universe = _ranking_fixtures.universe
walk_bars = _ranking_fixtures.walk_bars

# --------------------------------------------------------------------------- #
# 1. rank_universe, directly
# --------------------------------------------------------------------------- #

#: Five pairs. Arrival is reverse-alphabetical, the intended order is neither, and every
#: element of all three orders differs, so a pass-through, a sort by name and a sort in the
#: wrong direction each fail on every position.
MOVES = {
    "AAA/USD": 0.010,
    "BBB/USD": 0.030,
    "CCC/USD": 0.021,
    "DDD/USD": 0.004,
    "EEE/USD": 0.017,
}
ARRIVAL = ("EEE/USD", "DDD/USD", "CCC/USD", "BBB/USD", "AAA/USD")
DESCENDING = ("BBB/USD", "CCC/USD", "EEE/USD", "AAA/USD", "DDD/USD")


def test_rank_universe_orders_by_expected_move_and_not_by_arrival() -> None:
    ordered = rank_universe(ARRIVAL, feature=RANK_BY_EXPECTED_MOVE, expected_moves=MOVES)

    assert ordered == DESCENDING
    for position, pair in enumerate(ordered):
        assert pair != ARRIVAL[position], f"position {position} agrees with arrival"
        assert pair != sorted(ARRIVAL)[position], f"position {position} agrees with names"
    assert select_candidate(ARRIVAL, feature=RANK_BY_EXPECTED_MOVE, expected_moves=MOVES) == (
        "BBB/USD"
    )
    # Idempotent: a ranking that reversed on each call would pass the first assertion.
    assert rank_universe(ordered, feature=RANK_BY_EXPECTED_MOVE, expected_moves=MOVES) == ordered


def test_the_direction_flag_reverses_the_order_and_keeps_the_name_tie_break() -> None:
    ascending = rank_universe(
        ARRIVAL, feature=RANK_BY_EXPECTED_MOVE, expected_moves=MOVES, descending=False
    )
    assert ascending == tuple(reversed(DESCENDING))
    for position, pair in enumerate(ascending):
        assert pair not in (ARRIVAL[position], sorted(ARRIVAL)[position]), position

    tied = {"CCC/USD": 0.01, "AAA/USD": 0.01, "BBB/USD": 0.01}
    for descending in (True, False):
        assert rank_universe(
            ("CCC/USD", "BBB/USD", "AAA/USD"),
            feature=RANK_BY_EXPECTED_MOVE,
            expected_moves=tied,
            descending=descending,
        ) == ("AAA/USD", "BBB/USD", "CCC/USD")


def test_a_pair_the_ranking_skipped_is_dropped_not_sorted_last() -> None:
    """R11. The opposite of the feature rule: a pair with no expected move is one a gate
    would refuse, so it is not examined at all. NaN and infinity count as absent."""
    moves = {"AAA/USD": 0.01, "CCC/USD": float("nan"), "DDD/USD": float("inf"), "EEE/USD": 0.02}
    ordered = rank_universe(ARRIVAL, feature=RANK_BY_EXPECTED_MOVE, expected_moves=moves)

    assert ordered == ("EEE/USD", "AAA/USD")
    assert rank_universe(ARRIVAL, feature=RANK_BY_EXPECTED_MOVE, expected_moves={}) == ()
    assert select_candidate(ARRIVAL, feature=RANK_BY_EXPECTED_MOVE, expected_moves={}) is None


def test_asking_for_the_expected_move_order_without_moves_is_a_defect_not_an_empty_answer() -> None:
    with pytest.raises(ValueError, match="handed no expected moves"):
        rank_universe(ARRIVAL, feature=RANK_BY_EXPECTED_MOVE)


def test_alphabetical_is_unchanged_when_no_ranking_is_configured() -> None:
    """The operator's baseline. Handing it expected moves changes nothing."""
    assert rank_universe(ARRIVAL, expected_moves=MOVES) == tuple(sorted(ARRIVAL))
    assert rank_universe(ARRIVAL, feature=None, expected_moves=MOVES) == tuple(sorted(ARRIVAL))


# --------------------------------------------------------------------------- #
# 2. The engine against a stand-in ranking module
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Ranked:
    pair: str
    expected_move_pct: float


@dataclass(frozen=True)
class _Ranking:
    ranked: tuple[_Ranked, ...]
    excluded: tuple[tuple[str, str], ...]


class _StandIn:
    """A stand-in for `modelling/ranking.py`, in the shape C landed.

    The expected moves and exclusions are scripted per pair. Every call is recorded so a
    test can assert what the engine handed in, not only what came back.
    """

    def __init__(self, moves: dict[str, float], excluded: dict[str, str] | None = None) -> None:
        self.moves = moves
        self.excluded = excluded or {}
        self.loads: list[tuple[Path, Path]] = []
        self.calls: list[dict[str, Any]] = []
        self.refuse_load: str | None = None
        self.refuse_rank: str | None = None
        module = types.ModuleType(RANKING_MODULE)

        class RankingError(ValueError):
            pass

        module.RankingError = RankingError  # type: ignore[attr-defined]
        module.load_ranking_artefacts = self._load  # type: ignore[attr-defined]
        module.rank_by_expected_move = self._rank  # type: ignore[attr-defined]
        self.module = module
        self.error = RankingError

    def _load(self, prediction_dir: Path, anomaly_dir: Path) -> object:
        if self.refuse_load:
            raise self.error(self.refuse_load)
        self.loads.append((prediction_dir, anomaly_dir))
        return object()

    def _rank(
        self,
        rows: dict[str, Any],
        macro: dict[str, Any],
        artefacts: object,
        *,
        target_pct: float,
        stop_pct: float,
    ) -> _Ranking:
        if self.refuse_rank:
            raise self.error(self.refuse_rank)
        self.calls.append(
            {"rows": dict(rows), "macro": dict(macro), "target": target_pct, "stop": stop_pct}
        )
        ranked = [_Ranked(p, self.moves[p]) for p in rows if p in self.moves]
        ranked.sort(key=lambda entry: (-entry.expected_move_pct, entry.pair))
        return _Ranking(
            ranked=tuple(ranked),
            excluded=tuple(sorted((p, c) for p, c in self.excluded.items() if p in rows)),
        )


class _Config:
    """The committed config with named keys answered, and nothing else changed."""

    def __init__(self, inner: Any, **overrides: Any) -> None:
        self._inner = inner
        self._overrides = overrides

    def get(self, key: str) -> Any:
        if key in self._overrides:
            return self._overrides[key]
        return self._inner.get(key)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


PREDICTION_RUN = "run-predict"
ANOMALY_RUN = "run-anomaly"

#: Rows for the three USD pairs the fake exchange lets into the universe. The stand-in
#: never reads a value. They only have to be present, as engine 5's payload is.
ROWS = {pair: {"x": 1.0} for pair in USD_PAIRS}


@pytest.fixture
def ranked_account(engine_context: Any, migrated_db: Path, tmp_path: Path) -> Any:
    """A $5,000 account whose store also knows an artefact root holding the two runs."""
    models = tmp_path / "models"
    (models / PREDICTION_RUN).mkdir(parents=True)
    (models / ANOMALY_RUN).mkdir(parents=True)
    store = StoreClient(migrated_db, models_dir=models)
    write_equity(store, "5000.00")
    engine_context.clients.store = store
    client = FakeKrakenWithStream()
    engine_context.clients.kraken = client
    from datetime import timedelta

    client.stream_pairs((*USD_PAIRS, "ETH/BTC"), at=engine_context.now - timedelta(seconds=60))
    client.set_balances({"USD": "5000.00", "BTC": "0.01000000", "ETH": "0.50000000"})
    return engine_context


def configured(context: Any, **overrides: Any) -> Any:
    keys = {
        "scout.rank_feature": RANK_BY_EXPECTED_MOVE,
        "models.prediction_run_id": PREDICTION_RUN,
        "models.anomaly_run_id": ANOMALY_RUN,
    }
    keys.update(overrides)
    return dataclasses.replace(context, config=_Config(context.config, **keys))


def ranked_state(context: Any, rows: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_state(context) | {
        "feature": {"pairs": ROWS if rows is None else rows, "feature_names": ["x"]},
        "macro_context": {"features": {"macro_btc_x": 0.5}},
    }


@pytest.fixture
def stand_in(monkeypatch: pytest.MonkeyPatch) -> _StandIn:
    # ETH/USD first, then SOL/USD, then BTC/USD, which is neither alphabetical nor arrival.
    fake = _StandIn({"BTC/USD": 0.004, "ETH/USD": 0.031, "SOL/USD": 0.012})
    monkeypatch.setitem(sys.modules, RANKING_MODULE, fake.module)
    return fake


def test_the_candidate_is_the_highest_expected_move_and_not_the_first_name(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    context = configured(ranked_account)
    result = ScoutEngine().process(context, ranked_state(context))

    assert result.status is EngineStatus.OK
    data = result.data
    assert data[CANDIDATE_FIELD] == "ETH/USD"
    assert data[CANDIDATE_FIELD] != min(data["pairs"]), "the fixture must not agree with names"
    assert [entry[CANDIDATE_FIELD] for entry in data[RANKED_FIELD]] == [
        "ETH/USD",
        "SOL/USD",
        "BTC/USD",
    ]
    # Published as engine 8 publishes it: the float's shortest repr, as an exact string.
    assert [entry["expected_move_pct"] for entry in data[RANKED_FIELD]] == [
        "0.031",
        "0.012",
        "0.004",
    ]
    assert data[RANK_RUN_IDS_FIELD] == {"prediction": PREDICTION_RUN, "anomaly": ANOMALY_RUN}
    assert data["rank_feature"] == RANK_BY_EXPECTED_MOVE


def test_only_the_filtered_universe_is_handed_to_the_ranking(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    """The universe filter is engine 7's. A crypto-quoted pair it excluded must never
    reach the model, even with a feature row published for it. The barriers and the
    macro mapping go through as the config and engine 6 give them."""
    context = configured(ranked_account)
    rows = {**ROWS, "ETH/BTC": {"x": 1.0}}
    data = ScoutEngine().process(context, ranked_state(context, rows)).data

    (call,) = stand_in.calls
    assert sorted(call["rows"]) == sorted(data["pairs"]) == sorted(USD_PAIRS)
    assert call["macro"] == {"macro_btc_x": 0.5}
    assert call["target"] == float(context.config.get("barriers.target_pct"))
    assert call["stop"] == float(context.config.get("barriers.stop_pct"))
    (load,) = stand_in.loads
    assert load == (
        context.clients.store.model_run_dir(PREDICTION_RUN),
        context.clients.store.model_run_dir(ANOMALY_RUN),
    )


def test_a_universe_pair_with_no_feature_row_is_handed_in_as_none(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    """A missing row goes in as `None`, which the function counts as an incomplete vector.
    Dropping it before the call would make the pair vanish from the skip tally too."""
    context = configured(ranked_account)
    rows = {pair: row for pair, row in ROWS.items() if pair != "SOL/USD"}
    ScoutEngine().process(context, ranked_state(context, rows))

    (call,) = stand_in.calls
    assert "SOL/USD" in call["rows"]
    assert call["rows"]["SOL/USD"] is None


def test_skipped_pairs_stay_in_the_universe_and_are_tallied_apart_from_exclusions(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    stand_in.moves = {"SOL/USD": 0.012}
    stand_in.excluded = {"ETH/USD": "di_refused", "BTC/USD": "market_anomalous"}
    context = configured(ranked_account)
    data = ScoutEngine().process(context, ranked_state(context)).data

    assert data[CANDIDATE_FIELD] == "SOL/USD"
    assert sorted(data["pairs"]) == sorted(USD_PAIRS), "a skipped pair left the universe"
    assert data[RANK_SKIPPED_FIELD] == {"di_refused": 1, "market_anomalous": 1}
    assert "di_refused" not in data["excluded"]
    assert data["scanned"] == data["entered"] + sum(data["excluded"].values())


def test_a_universe_the_ranking_skips_entirely_passes_with_its_own_code(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    """R11 with nothing left: no candidate, a `PASS` and not a block, and not
    `empty_universe`, because the account could trade these pairs."""
    stand_in.moves = {}
    stand_in.excluded = dict.fromkeys(USD_PAIRS, "prediction_inputs_incomplete")
    context = configured(ranked_account)
    result = ScoutEngine().process(context, ranked_state(context))

    assert result.status is EngineStatus.PASS
    assert result.blocks_trading is False
    assert CANDIDATE_FIELD not in result.data
    assert result.data["reason_code"] == REASON_NO_RANKABLE_PAIR
    assert result.data["entered"] == len(USD_PAIRS)
    assert result.data[RANK_SKIPPED_FIELD] == {"prediction_inputs_incomplete": 3}


def test_an_empty_universe_is_empty_universe_and_nothing_is_loaded(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    ranked_account.clients.kraken.set_balances({"USD": "0"})
    context = configured(ranked_account)
    result = ScoutEngine().process(context, ranked_state(context))

    assert result.status is EngineStatus.PASS
    assert result.data["reason_code"] == REASON_EMPTY_UNIVERSE
    assert stand_in.loads == [] and stand_in.calls == []


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"models.prediction_run_id": None}, "models.prediction_run_id is not set"),
        ({"models.anomaly_run_id": "  "}, "models.anomaly_run_id is not set"),
        ({"models.prediction_run_id": "never-trained"}, "could not be opened"),
    ],
)
def test_a_ranking_with_no_model_to_score_with_blocks(
    stand_in: _StandIn, ranked_account: Any, override: dict[str, Any], fragment: str
) -> None:
    context = configured(ranked_account, **override)
    result = ScoutEngine().process(context, ranked_state(context))

    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert result.reason is not None and fragment in result.reason
    assert stand_in.calls == []


def test_an_artefact_the_function_refuses_blocks_naming_the_cause(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    stand_in.refuse_load = "carries no di.npz"
    context = configured(ranked_account)
    result = ScoutEngine().process(context, ranked_state(context))

    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert result.reason is not None
    assert "artefacts are unusable: carries no di.npz" in result.reason


def test_a_ranking_the_function_cannot_compute_blocks_rather_than_falling_back(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    """A lost ranking must not become alphabetical. That would be the placeholder score
    the operator refused, reporting a ranking that never happened."""
    stand_in.refuse_rank = "ETH/USD: probabilities do not sum to one"
    context = configured(ranked_account)
    result = ScoutEngine().process(context, ranked_state(context))

    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert result.reason is not None and "could not be ranked" in result.reason


def test_the_ranking_module_missing_blocks_and_a_broken_dependency_raises(
    ranked_account: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the module's own absence reads as "not available". A dependency it imports
    being missing is a broken install, and it reaches the orchestrator as the ERROR it is.
    """
    context = configured(ranked_account)
    monkeypatch.setitem(sys.modules, RANKING_MODULE, None)  # import raises ModuleNotFoundError
    result = ScoutEngine().process(context, ranked_state(context))
    assert result.status is EngineStatus.BLOCK
    assert result.reason is not None and f"{RANKING_MODULE} does not exist" in result.reason

    import importlib

    def broken(name: str, *args: Any, **kwargs: Any) -> Any:
        raise ModuleNotFoundError("No module named 'lightgbm'", name="lightgbm")

    monkeypatch.delitem(sys.modules, RANKING_MODULE)
    monkeypatch.setattr(importlib, "import_module", broken)
    with pytest.raises(ModuleNotFoundError, match="lightgbm"):
        ScoutEngine().process(context, ranked_state(context))


def test_engine_5_absent_blocks_the_ranking_and_feature_names_are_not_consulted(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    """`expected_move` is not one of engine 5's names and must not be checked against them.
    That check would refuse the ruled ranking on every tick. Engine 5 publishing nothing
    still blocks."""
    context = configured(ranked_account)
    ranked = ScoutEngine().process(context, ranked_state(context))
    assert ranked.status is EngineStatus.OK, ranked.reason

    missing = ScoutEngine().process(context, build_state(context))
    assert missing.status is EngineStatus.BLOCK
    assert missing.reason is not None and "feature is absent" in missing.reason


def test_the_artefacts_are_loaded_once_and_reloaded_when_a_run_id_changes(
    stand_in: _StandIn, ranked_account: Any, tmp_path: Path
) -> None:
    engine = ScoutEngine()
    context = configured(ranked_account)
    engine.process(context, ranked_state(context))
    engine.process(context, ranked_state(context))
    assert len(stand_in.loads) == 1, "the same runs were loaded twice"

    (tmp_path / "models" / "run-other").mkdir()
    other = configured(ranked_account, **{"models.prediction_run_id": "run-other"})
    engine.process(other, ranked_state(other))
    assert len(stand_in.loads) == 2
    assert stand_in.loads[-1][0].name == "run-other"


def test_with_the_key_absent_the_ranking_is_never_consulted(
    stand_in: _StandIn, ranked_account: Any
) -> None:
    """The alphabetical baseline, exactly as before spec 144. The model is not loaded, and
    the payload carries an empty ranking and no run ids."""
    context = configured(ranked_account, **{"scout.rank_feature": None})
    data = ScoutEngine().process(context, ranked_state(context)).data

    assert data[CANDIDATE_FIELD] == min(data["pairs"]) == "BTC/USD"
    assert data["rank_feature"] is None
    assert data[RANKED_FIELD] == [] and data[RANK_SKIPPED_FIELD] == {}
    assert data[RANK_RUN_IDS_FIELD] is None
    assert stand_in.loads == [] and stand_in.calls == []


# --------------------------------------------------------------------------- #
# 3. The seam with no double: the real function, the real artefact, the real gates
# --------------------------------------------------------------------------- #


@pytest.fixture
def real_universe(
    engine_context: Any, migrated_db: Path, request: pytest.FixtureRequest
) -> Any:
    """C's fixture universe from `tests/modelling/test_ranking.py`, renamed onto the fake
    exchange's three USD pairs, so engine 7's real filter lets them in.

    The renaming is the one fabricated step. A pair's name is not a feature, so no number
    the ranking or the gates compute can see it. C's module states the same about its own
    renaming. Everything else is real: engines 1 and 3 against the fake exchange, engine
    5's rows and engine 6's macro columns on real tails of the training series, the trained
    artefact, and `StoreClient.model_run_dir`.
    """
    root, run_id = request.getfixturevalue("trained")
    rows, _macro, _context = request.getfixturevalue("universe")
    sources = sorted(rows)[: len(USD_PAIRS)]
    renamed = {target: rows[source] for target, source in zip(USD_PAIRS, sources, strict=True)}

    store = StoreClient(migrated_db, models_dir=root)
    write_equity(store, "5000.00")
    engine_context.clients.store = store
    client = FakeKrakenWithStream()
    engine_context.clients.kraken = client
    from datetime import timedelta

    client.stream_pairs(USD_PAIRS, at=engine_context.now - timedelta(seconds=60))
    client.set_balances({"USD": "5000.00"})
    return engine_context, renamed, run_id



def _gate_verdicts(context: Any, rows: dict[str, Any], scout: dict[str, Any], pair: str) -> Any:
    """What the real engines 13 and 8 publish when `pair` is the candidate.

    The state carries engine 7's own payload from the run under test, with only the
    candidate pointed at `pair`. So anything else engine 7 published (its order, its
    ranked list, its direction) is present, and a gate that read it would show up as a
    difference between the two directions.
    """
    from acsoe.engines.anomaly.engine import AnomalyEngine
    from acsoe.engines.prediction.engine import PredictionEngine

    state = {
        "feature": {"pairs": rows, "bar_ts": 0},
        "macro_context": {"features": {}},
        "scout": {**scout, CANDIDATE_FIELD: pair},
    }
    anomaly = AnomalyEngine().process(context, state)
    prediction = PredictionEngine().process(context, state)
    return (
        (anomaly.status, anomaly.blocks_trading, _without_timing(anomaly.data)),
        (prediction.status, prediction.blocks_trading, _without_timing(prediction.data)),
    )


def _without_timing(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if "duration" not in key}


def test_the_real_ranking_chooses_engine_8s_best_pair_and_reversing_it_moves_no_verdict(
    real_universe: Any,
) -> None:
    """Spec 144's Check When Done, with no double anywhere in the seam.

    1. The chosen pair's expected move equals the value engine 8 publishes for it,
       recomputed by engine 8 and compared as the rendered decimal string.
    2. Engine 7's order equals the shared function's own order.
    3. Reversing the ranking changes the candidate, and on every pair the verdicts of
       engines 13 and 8 are the same under both directions.
    """
    from acsoe.modelling import ranking as ranking_module

    context, rows, run_id = real_universe
    keys = {
        "scout.rank_feature": RANK_BY_EXPECTED_MOVE,
        "models.prediction_run_id": run_id,
        "models.anomaly_run_id": run_id,
    }
    descending = dataclasses.replace(
        context, config=_Config(context.config, **keys, **{"scout.rank_descending": True})
    )
    ascending = dataclasses.replace(
        context, config=_Config(context.config, **keys, **{"scout.rank_descending": False})
    )
    state = build_state(context) | {
        "feature": {"pairs": rows, "feature_names": []},
        "macro_context": {"features": {}},
    }

    down = ScoutEngine().process(descending, dict(state))
    up = ScoutEngine().process(ascending, dict(state))
    assert down.status is EngineStatus.OK, down.reason
    assert up.status is EngineStatus.OK, up.reason
    ranked_down = [entry[CANDIDATE_FIELD] for entry in down.data[RANKED_FIELD]]
    assert len(ranked_down) >= 2, (
        f"only {ranked_down} survived both gates, so there is no order to reverse; "
        f"skipped {down.data[RANK_SKIPPED_FIELD]}"
    )

    # 2. Engine 7's own sort agrees with the function's.
    root = context.clients.store.model_run_dir(run_id)
    direct = ranking_module.rank_by_expected_move(
        rows,
        {},
        ranking_module.load_ranking_artefacts(root, root),
        target_pct=float(context.config.get("barriers.target_pct")),
        stop_pct=float(context.config.get("barriers.stop_pct")),
    )
    assert ranked_down == [entry.pair for entry in direct.ranked]
    assert [entry[CANDIDATE_FIELD] for entry in up.data[RANKED_FIELD]] == ranked_down[::-1]

    # 3. The candidate moves ...
    assert down.data[CANDIDATE_FIELD] != up.data[CANDIDATE_FIELD]

    gate_context = dataclasses.replace(
        descending,
        config=_Config(
            context.config,
            **{"models.prediction_run_id": run_id, "models.anomaly_run_id": run_id},
        ),
    )
    for pair in sorted(rows):
        under_down = _gate_verdicts(gate_context, rows, down.data, pair)
        under_up = _gate_verdicts(gate_context, rows, up.data, pair)
        # ... and no gate's verdict on any pair does.
        assert under_down == under_up, pair

    # 1. The chosen pair's expected move is engine 8's, recomputed by engine 8.
    for result in (down, up):
        chosen = result.data[CANDIDATE_FIELD]
        (_anomaly, prediction) = _gate_verdicts(gate_context, rows, result.data, chosen)
        status, blocks, payload = prediction
        assert status is EngineStatus.OK and not blocks, (chosen, payload)
        published = {
            entry[CANDIDATE_FIELD]: entry["expected_move_pct"]
            for entry in result.data[RANKED_FIELD]
        }
        assert published[chosen] == payload["expected_move_pct"], chosen
        assert Decimal(published[chosen]) == Decimal(payload["expected_move_pct"])
