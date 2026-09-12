"""Engine 23 `backtest` — replay plus labelling, and where it may be registered.

Spec 55. Every assertion here has been run against a deliberately broken engine and
observed red; the mutations and the exact red messages are in
`docs/build-log/phase-4/a-platform.md`.

**The labeller is C's.** Most tests here drive a double, because the half of the seam
this side owns is *what the engine hands over* — one frame per pair, the `Config` object
itself rather than three pre-read numbers, and the interval. What the labeller does with
those is proved in C's own tests, and re-proving it here would be a second labeller
nobody knew about.

**But the last section runs the real one.** A double can agree with a caller about a
signature that no longer exists — the first version of this file was built against a
`label_bars(bars, *, target_pct, stop_pct, timeout_bars)` agreed by message, and C's
module landed with `label_frame(frame, *, pair, config, interval_s)` instead. Every test
here was green against the mock the whole time. So there is an end-to-end test with no
injection at all, and it is the one that would have caught it.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from acsoe.core.contracts import EngineResult, EngineStatus
from acsoe.research.backtest import (
    LABELLER_ATTR,
    LABELLER_MODULE,
    STATE_KEY,
    BacktestEngine,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

INTERVAL_S = 900
BASE_TS = 1_700_000_000


def write_archive(directory: Path, name: str, indices: list[int]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        "\n".join(
            f"{BASE_TS + i * INTERVAL_S},{100 + i}.0,{100 + i}.5,{99 + i}.0,"
            f"{100 + i}.2,1.5,7"
            for i in indices
        )
        + "\n",
        encoding="utf-8",
    )
    return path


class RecordingLabeller:
    """Records exactly what the engine handed it, and returns one row per bar.

    Capable of exhibiting the properties under test: it keeps the frame it was given,
    so a test can assert the engine labelled one pair's series rather than the merged
    stream, and it keeps the `config` object, so a test can assert the engine handed
    the barriers' single reader over rather than pre-reading them itself.

    It returns a `polars` frame, because that is what C's `label_frame` returns and a
    double that returned a list would be simpler than the real thing in the dimension
    `_rows_of` is about.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        frame: Any,
        *,
        pair: str,
        config: Any,
        interval_s: int,
    ) -> tuple[Any, Any]:
        import polars as pl

        self.calls.append(
            {"frame": frame, "pair": pair, "config": config, "interval_s": interval_s}
        )
        rows = [
            {
                "pair": pair,
                "decision_ts": int(row["ts"]),
                "label": "timeout",
                "label_window_end_ts": int(row["ts"]) + 48 * interval_s,
            }
            for row in frame.to_dicts()
        ]
        return pl.DataFrame(rows), FakeSeries(len(rows))


#: How many more bars this double claims to have *considered* than it labelled.
#: Deliberately non-zero: in C's real `LabelledSeries` those two numbers differ by
#: `excluded_past_end + excluded_empty_window`, and a double that made them equal
#: cannot distinguish an engine counting rows from one counting bars offered. It could
#: not, and a mutation swapping the two survived all 28 tests. Build log, 2026-09-11.
CONSIDERED_SURPLUS = 3

#: Likewise non-zero, so "the ambiguous count is carried through" and "the ambiguous
#: count is hard-coded to zero" are different observable outcomes.
AMBIGUOUS_PER_PAIR = 2

#: And again, for the rows the decision-start cutoff removed (operator ruling 2).
BEFORE_START_PER_PAIR = 4


class FakeSeries:
    """Stands in for C's `LabelledSeries`. Carries the three things the engine reads,
    and carries them as three **different** numbers, because that is the only way an
    assertion about which one was used can fail."""

    def __init__(self, labelled: int) -> None:
        self.considered = labelled + CONSIDERED_SURPLUS
        self.ambiguous_count = AMBIGUOUS_PER_PAIR
        self.excluded_before_start = BEFORE_START_PER_PAIR
        self._labelled = labelled

    def counts(self) -> dict[str, int]:
        return {"target": 0, "stop": 0, "timeout": self._labelled}


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    directory = tmp_path / "ohlcvt_15m"
    write_archive(directory, "XBTUSD_15.csv", [0, 1, 2, 5, 6])
    write_archive(directory, "ETHUSD_15.csv", [0, 1])
    return directory


@pytest.fixture
def labeller() -> RecordingLabeller:
    return RecordingLabeller()


def build(archive: Path, tmp_path: Path, labeller: Any, **kwargs: Any) -> BacktestEngine:
    return BacktestEngine(
        archive_dir=archive,
        derived_dir=tmp_path / "derived",
        labeller=labeller,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Identity, and where this engine may be registered
# --------------------------------------------------------------------------- #


def test_the_engine_carries_the_registry_s_number_and_gate_flag() -> None:
    """`is_gate_matches_registry` reads these against the table in
    `context/engine-contracts.md`, which says `| 23 | backtest | | offline | - |` —
    number 23, no gate."""
    assert BacktestEngine.name == "backtest"
    assert BacktestEngine.number == 23
    assert BacktestEngine.is_gate is False


def test_the_engine_is_registered_in_the_offline_chain() -> None:
    from acsoe.cli.research import OFFLINE_CHAIN, build_offline_chain

    assert [engine.name for engine in build_offline_chain()] == ["backtest"]
    assert isinstance(OFFLINE_CHAIN[0], BacktestEngine)


def _modules_importing_research(root: Path) -> list[str]:
    """Every module under ``root`` that imports from ``acsoe.research``.

    The detector, factored out so that it can be pointed at a fabricated tree and
    *proved capable of failing* — see the two tests below.
    """
    offenders: list[str] = []
    for module in sorted(root.rglob("*.py")):
        for line in module.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("import acsoe.research", "from acsoe.research")):
                offenders.append(f"{module.name}: {stripped}")
    return offenders


def test_bootstrap_does_not_import_research() -> None:
    """The mutation spec 55 names: engine 23 registered in `bootstrap.py` instead of
    the offline chain. Asserted on the **real** `bootstrap.py`, reached through the
    imported module's own `__file__` rather than by a path built here, so that moving
    the file cannot silently point this at nothing."""
    from acsoe import bootstrap

    path = Path(str(bootstrap.__file__))
    assert path.is_file()
    assert path.parent == SRC / "acsoe"
    assert not hasattr(bootstrap, "OFFLINE_CHAIN")

    offenders = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(("import acsoe.research", "from acsoe.research"))
    ]
    assert offenders == [], offenders


def test_that_assertion_goes_red_when_the_import_is_added(tmp_path: Path) -> None:
    """Proof the check above can fail, without writing to `bootstrap.py`.

    `bootstrap.py` is the lead's file under `context/ownership.md` rule 2, and a
    transient mutation of it is still a write to another agent's path while three
    agents share one checkout. So the real file is copied, the forbidden import is
    added to the copy, and the same detector is run over it.

    **Where this is weaker, stated rather than glossed:** it proves the detector can
    fail, and `test_bootstrap_does_not_import_research` separately proves the detector
    is pointed at the real file — but no single test does both at once. The direct
    mutation is one line for the lead and is offered in the build log.
    """
    from acsoe import bootstrap

    real = Path(str(bootstrap.__file__))
    source = real.read_text(encoding="utf-8")

    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "bootstrap.py").write_text(source, encoding="utf-8")

    mutated = tmp_path / "mutated"
    mutated.mkdir()
    (mutated / "bootstrap.py").write_text(
        source + "\nfrom acsoe.research.backtest import BacktestEngine\n", encoding="utf-8"
    )

    # The same detector, over the real file's text and over the real file's text plus
    # one line. Green on one, red on the other, so the check is not vacuous.
    assert _modules_importing_research(clean) == []
    assert _modules_importing_research(mutated) == [
        "bootstrap.py: from acsoe.research.backtest import BacktestEngine"
    ]


def test_backtest_is_the_one_research_module_allowed_to_import_core() -> None:
    """An engine is a `BaseEngine`, so this module has to import `acsoe.core`. Every
    *other* module under `research/` must not — `historical.py` and `replay.py` have
    their own assertions, and this one catches a third module appearing."""
    offenders: list[str] = []
    for module in sorted((SRC / "acsoe" / "research").rglob("*.py")):
        if module.name == "backtest.py":
            continue
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith(
                    ("acsoe.core", "acsoe.engines", "acsoe.clients", "acsoe.cli", "acsoe.console")
                ):
                    offenders.append(f"{module.name}: {name}")
    assert offenders == [], offenders


# --------------------------------------------------------------------------- #
# What it does with the archive
# --------------------------------------------------------------------------- #


def test_it_replays_every_pair_and_labels_each_series(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    state: dict[str, Any] = {}
    result = build(archive, tmp_path, labeller).process(engine_context, state)

    assert isinstance(result, EngineResult)
    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.engine == "backtest"
    assert result.data["bars_replayed"] == 7
    assert result.data["labelled_rows"] == 7
    assert result.data["labelled_rows_by_pair"] == {"XBTUSD": 5, "ETHUSD": 2}
    assert sorted(result.data["pairs"]) == ["ETHUSD", "XBTUSD"]

    # Rows produced and bars offered are two different numbers and the double reports
    # them as two different numbers, so an engine reading the wrong one is visible.
    assert result.data["decision_bars_considered"] == 7 + 2 * CONSIDERED_SURPLUS
    assert result.data["label_counts"] == {"target": 0, "stop": 0, "timeout": 7}
    # Ruling 1 decided this many labels rather than the data. Asserted, because a
    # reported field nothing asserts is documentation and will silently become zero.
    assert result.data["ambiguous_labels"] == 2 * AMBIGUOUS_PER_PAIR


class _Override:
    """`paper_config` with one key overridden, so a test never depends on the committed
    value of the knob it is exercising."""

    def __init__(self, base: Any, key: str, value: Any) -> None:
        self._base = base
        self._key = key
        self._value = value

    def get(self, dotted: str, /) -> Any:
        return self._value if dotted == self._key else self._base.get(dotted)


def _with_config(engine_context: Any, config: Any) -> Any:
    return replace(engine_context, config=config)


# --------------------------------------------------------------------------- #
# Operator rulings 2 and 3, 2026-09-12: the cutoff's cost, and the per-pair floor
# --------------------------------------------------------------------------- #


def test_the_cutoff_cost_is_reported_per_pair_and_in_total(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """Ruling 2 asks for the number. The double reports a non-zero count so an engine
    that hard-coded zero, or read the wrong field, is visible."""
    result = build(archive, tmp_path, labeller).process(engine_context, {})

    assert result.data["excluded_before_start"] == 2 * BEFORE_START_PER_PAIR
    assert result.data["excluded_before_start_by_pair"] == {
        "XBTUSD": BEFORE_START_PER_PAIR,
        "ETHUSD": BEFORE_START_PER_PAIR,
    }
    assert result.data["decision_start_date"] == str(
        engine_context.config.get("dataset.decision_start_date")
    )


def test_no_floor_is_the_committed_value_and_keeps_every_pair(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """Ruling 3: the eleven thin pairs are kept today. The knob exists, reads 0, and
    the report says so in as many words rather than by omission."""
    result = build(archive, tmp_path, labeller).process(engine_context, {})

    assert result.data["min_labelled_rows"] == 0
    assert result.data["pairs_below_floor"] == {}
    assert sorted(result.data["pairs"]) == ["ETHUSD", "XBTUSD"]


def test_a_pair_below_the_floor_is_left_out_and_named_with_its_count(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """ETHUSD has two rows and XBTUSD five. A floor of three drops exactly one, and the
    dropped pair still reports the cutoff's cost: the number must not leave with it."""
    context = _with_config(
        engine_context, _Override(engine_context.config, "dataset.min_labelled_rows", 3)
    )

    result = build(archive, tmp_path, labeller).process(context, {})

    assert result.data["pairs_below_floor"] == {"ETHUSD": 2}
    assert result.data["labelled_rows_by_pair"] == {"XBTUSD": 5}
    assert result.data["labelled_rows"] == 5
    assert result.data["label_counts"] == {"target": 0, "stop": 0, "timeout": 5}
    assert result.data["decision_bars_considered"] == 5 + CONSIDERED_SURPLUS
    assert result.data["ambiguous_labels"] == AMBIGUOUS_PER_PAIR
    assert result.data["excluded_before_start_by_pair"]["ETHUSD"] == BEFORE_START_PER_PAIR
    assert result.data["min_labelled_rows"] == 3


def test_a_null_floor_is_refused_rather_than_read_as_zero(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """0 is a stated value; null is a hole. The knob exists so the decision is visible,
    and a hole read as "no floor" is the decision made silently."""
    context = _with_config(
        engine_context, _Override(engine_context.config, "dataset.min_labelled_rows", None)
    )

    with pytest.raises(RuntimeError, match=r"dataset\.min_labelled_rows"):
        build(archive, tmp_path, labeller).process(context, {})


def test_each_pair_is_labelled_as_its_own_series_not_as_one_merged_stream(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """The defect this catches is silent and ruinous. A triple barrier walked over a
    merged stream steps from an XBTUSD bar to an ETHUSD bar at a completely different
    price level, and every label after the first pair boundary is fabricated. The row
    count is identical either way, which is why this asserts on the frames handed over
    rather than on how many rows came back."""
    build(archive, tmp_path, labeller).process(engine_context, {})

    assert len(labeller.calls) == 2
    assert {call["pair"] for call in labeller.calls} == {"XBTUSD", "ETHUSD"}
    heights = {call["pair"]: call["frame"].height for call in labeller.calls}
    assert heights == {"XBTUSD": 5, "ETHUSD": 2}
    # Each frame is that pair's own series and no other's: 7 bars exist in total, and
    # neither call saw all 7.
    assert sum(heights.values()) == 7
    assert max(heights.values()) < 7


def test_the_config_itself_is_handed_to_the_labeller_not_three_pre_read_numbers(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """The barriers never cross this seam, and that is the design.

    `label_frame` reads `barriers.target_pct`, `barriers.stop_pct` and
    `barriers.timeout_bars` itself, so there is exactly **one** reader of those three
    keys in the project. An engine that pre-read them and passed three numbers would be
    a second reader — and C's converts a YAML float with `repr` while the obvious
    implementation here would use `str`, which moves the stop barrier in the sixteenth
    decimal for a reason nobody would ever chase down.

    This also deletes a hazard rather than guarding it: with no barrier arguments,
    `target_pct` and `stop_pct` cannot be swapped at the call site at all.
    """
    build(archive, tmp_path, labeller).process(engine_context, {})

    call = labeller.calls[0]
    assert call["config"] is engine_context.config
    assert call["interval_s"] == INTERVAL_S
    assert set(call) == {"frame", "pair", "config", "interval_s"}


def test_the_reported_barriers_come_from_the_labellers_own_reader(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """The report must not become that second reader either. It goes through
    `labelling.read_barriers`, so the numbers in `state` are the numbers the labels
    were built from, by construction rather than by both sides agreeing."""
    from acsoe.research.labelling import read_barriers

    result = build(archive, tmp_path, labeller).process(engine_context, {})
    expected = read_barriers(engine_context.config)
    assert result.data["barriers"] == {
        "target_pct": str(expected.target_pct),
        "stop_pct": str(expected.stop_pct),
        "timeout_bars": int(expected.timeout_bars),
    }
    assert result.data["barriers"]["target_pct"] == "0.03"
    assert result.data["barriers"]["stop_pct"] == "0.015"
    assert result.data["barriers"]["timeout_bars"] == 48


def test_an_empty_archive_directory_is_refused_rather_than_labelled_as_nothing(
    tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """An empty series that reports success is the quietest possible wrong answer: a
    Phase 5 training run over zero rows would report a perfect score."""
    from acsoe.research.historical import ArchiveError

    empty = tmp_path / "ohlcvt_15m"
    empty.mkdir()
    with pytest.raises(ArchiveError):
        build(empty, tmp_path, labeller).process(engine_context, {})


# --------------------------------------------------------------------------- #
# The labeller seam, and failing closed without it
# --------------------------------------------------------------------------- #


def test_without_a_labeller_module_the_engine_refuses_to_run(
    archive: Path, tmp_path: Path, engine_context: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It must not write an unlabelled slice and report success. That is the Phase 4
    failure mode exactly: nothing crashes, nothing goes red, and Phase 5 trains on a
    file with no labels in it."""
    monkeypatch.setitem(sys.modules, LABELLER_MODULE, None)
    engine = BacktestEngine(archive_dir=archive, derived_dir=tmp_path / "derived")
    with pytest.raises(RuntimeError, match="does not exist yet"):
        engine.process(engine_context, {})


def test_a_labelling_module_without_the_agreed_name_is_refused(
    archive: Path, tmp_path: Path, engine_context: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two situations that must not be conflated: the module is absent, and the module
    is present but does not carry the agreed function. `getattr(..., None)` followed by
    a callable check tells them apart, and the messages differ."""
    import types

    stand_in = types.ModuleType(LABELLER_MODULE)
    monkeypatch.setitem(sys.modules, LABELLER_MODULE, stand_in)
    engine = BacktestEngine(archive_dir=archive, derived_dir=tmp_path / "derived")
    with pytest.raises(RuntimeError, match=f"no callable {LABELLER_ATTR!r}"):
        engine.process(engine_context, {})


def test_an_injected_labeller_is_used_instead_of_the_module(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """The injection is what lets these tests run before C's module exists. It must
    take precedence, or every test above would be testing the import path."""
    build(archive, tmp_path, labeller).process(engine_context, {})
    assert labeller.calls


def test_a_label_result_that_cannot_be_read_raises_rather_than_becoming_nulls(
    archive: Path, tmp_path: Path, engine_context: Any
) -> None:
    """A slice of nulls is a slice Phase 5 would train on, and nothing about it would
    crash or go red. The seam is flexible about the container and not at all about
    whether it can be read."""

    def opaque(frame: Any, **kwargs: Any) -> tuple[Any, Any]:
        return object(), FakeSeries(0)

    with pytest.raises(TypeError, match="neither a polars frame"):
        build(archive, tmp_path, opaque).process(engine_context, {})


def test_a_sequence_of_non_mappings_is_refused_too(
    archive: Path, tmp_path: Path, engine_context: Any
) -> None:
    """A `list` passes the `Sequence` check and is still unreadable if its elements
    are not mappings. Two situations one `isinstance` would have conflated."""

    def wrong_elements(frame: Any, **kwargs: Any) -> tuple[Any, Any]:
        return [1, 2, 3], FakeSeries(3)

    with pytest.raises(TypeError, match="neither a polars frame"):
        build(archive, tmp_path, wrong_elements).process(engine_context, {})


def test_a_plain_sequence_of_mappings_is_accepted(
    archive: Path, tmp_path: Path, engine_context: Any
) -> None:
    """C returns a `polars` frame; a caller injecting a double should not have to build
    one. Accepted deliberately, and asserted so the leniency is a decision rather than
    an accident of duck typing."""

    def as_dicts(frame: Any, *, pair: str, **kwargs: Any) -> tuple[Any, Any]:
        rows = [{"pair": pair, "decision_ts": int(row["ts"])} for row in frame.to_dicts()]
        return rows, FakeSeries(len(rows))

    result = build(archive, tmp_path, as_dicts).process(engine_context, {})
    assert result.data["labelled_rows"] == 7


# --------------------------------------------------------------------------- #
# What it reports, and what it refuses to imply
# --------------------------------------------------------------------------- #


def test_the_output_says_there_is_no_spread_and_no_book(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """Carried in the output rather than in a docstring nobody reads at the point of
    use. A backtest that silently assumes zero spread is invalid, and engine 9 and the
    spread half of engine 10 cannot be backtested from an OHLCVT source at all."""
    result = build(archive, tmp_path, labeller).process(engine_context, {})
    assert result.data["has_spread"] is False
    assert result.data["has_order_book"] is False
    assert "zero spread is invalid" in result.data["spread_note"]
    assert "no spread" in result.data["book_note"]


def test_the_output_says_what_a_phase_4_backtest_is_not(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """Replay plus labelling, not a run through the twenty-three engines. A reader who
    took these rows for simulated trading results would be reading a dataset as a
    performance report."""
    result = build(archive, tmp_path, labeller).process(engine_context, {})
    assert "replay plus triple-barrier labelling" in result.data["phase_note"]
    assert "Engines 5 to 16 do not exist yet" in result.data["phase_note"]


def test_the_output_carries_whether_a_hole_means_no_trades(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """`None` here, because the fabricated archive has no sidecar — and `None` is
    unknown, which a consumer must treat as `False` would be treated. Invariant 3."""
    result = build(archive, tmp_path, labeller).process(engine_context, {})
    assert result.data["holes_mean_no_trades"] is None


def test_the_output_is_json_serialisable_with_money_as_strings(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """`EngineResult` refuses a `Decimal` in `data` and **accepts a float**, which is
    the dangerous half: an engine that hits the refusal and reflexively casts publishes
    a barrier that has already lost precision. The barriers cross as exact strings."""
    import json

    result = build(archive, tmp_path, labeller).process(engine_context, {})
    assert result.data["barriers"] == {
        "target_pct": "0.03",
        "stop_pct": "0.015",
        "timeout_bars": 48,
    }
    json.dumps(result.data)


def test_the_gap_report_and_the_span_reach_the_output(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """XBTUSD has one hole of two bars; ETHUSD has none."""
    result = build(archive, tmp_path, labeller).process(engine_context, {})
    assert result.data["gap_count"] == 1
    assert result.data["first_ts"] == BASE_TS
    assert result.data["last_ts"] == BASE_TS + 6 * INTERVAL_S
    assert result.data["span_seconds"] == 6 * INTERVAL_S


def test_the_state_key_is_the_engine_s_own_name(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """Contract rule 2: an engine writes exactly one key into `state`, its own."""
    assert BacktestEngine.name == STATE_KEY


# --------------------------------------------------------------------------- #
# The slice on disk
# --------------------------------------------------------------------------- #


def test_the_labelled_slice_is_written_to_the_derived_directory(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    import polars as pl

    result = build(archive, tmp_path, labeller).process(engine_context, {})
    written = Path(result.data["slice_path"])
    assert written.parent == tmp_path / "derived"
    assert written.suffix == ".parquet"
    assert pl.read_parquet(written).height == 7


def test_the_slice_is_named_by_the_run_so_a_second_run_cannot_replace_the_first(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """Two runs with different barriers produce different labels. One well-known
    filename would let the second silently replace the first while every count in
    `state` still looked right."""
    result = build(archive, tmp_path, labeller).process(engine_context, {})
    assert engine_context.run_id in Path(result.data["slice_path"]).name


def test_nothing_is_written_when_the_slice_is_switched_off(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """A criterion that only wants the counts must be able to run without leaving a
    file behind — `historical.load_archive` takes the same care for the same reason."""
    result = build(archive, tmp_path, labeller, write_slice=False).process(
        engine_context, {}
    )
    assert result.data["slice_path"] is None
    assert not (tmp_path / "derived").exists()


def test_the_archive_is_left_byte_identical(
    archive: Path, tmp_path: Path, labeller: RecordingLabeller, engine_context: Any
) -> None:
    """Invariant 11. The engine reads the archive and writes only to `data/derived/`."""
    before = {path: path.read_bytes() for path in archive.glob("*.csv")}
    build(archive, tmp_path, labeller).process(engine_context, {})
    assert {path: path.read_bytes() for path in archive.glob("*.csv")} == before


# --------------------------------------------------------------------------- #
# The real labeller, no injection
# --------------------------------------------------------------------------- #


def test_the_engine_drives_c_s_real_labeller_end_to_end(
    archive: Path, tmp_path: Path, engine_context: Any
) -> None:
    """No double anywhere. This is the test that catches the seam moving.

    Every other test in this file passed against a mock of a signature that had been
    agreed by message and never existed — `label_bars(bars, *, target_pct, stop_pct,
    timeout_bars)`. A mock agrees with whatever it was written to agree with, so a
    suite made only of mocks cannot notice that the real callee looks different. This
    one imports nothing of its own and injects nothing.
    """
    import polars as pl

    engine = BacktestEngine(archive_dir=archive, derived_dir=tmp_path / "derived")
    result = engine.process(engine_context, {})

    assert result.status in (EngineStatus.OK, EngineStatus.PASS)
    assert result.data["decision_bars_considered"] == 7
    assert result.data["ambiguous_labels"] == 0
    # Seven bars, a 48-bar horizon and a seven-bar series: every window runs past the
    # end, so the honest answer is zero labels rather than seven timeouts. An engine
    # reporting seven here would be reading `excluded_past_end` as a label.
    assert result.data["labelled_rows"] == 0
    assert result.data["label_counts"] == {"target": 0, "stop": 0, "timeout": 0}
    assert result.data["slice_path"] is None

    # ...and the columns the real labeller produces are the ones the splitter purges
    # on, reached through the engine rather than asserted from C's constants.
    from acsoe.research.labelling import LABEL_COLUMNS, label_frame

    labels, _series = label_frame(
        pl.read_csv(
            archive / "XBTUSD_15.csv",
            has_header=False,
            new_columns=["ts", "open", "high", "low", "close", "volume", "trades"],
        ),
        pair="XBTUSD",
        config=engine_context.config,
        interval_s=INTERVAL_S,
    )
    assert tuple(labels.columns) == LABEL_COLUMNS
    assert "label_window_end_ts" in labels.columns


def test_a_series_long_enough_to_label_produces_rows_and_a_slice(
    tmp_path: Path, engine_context: Any
) -> None:
    """The other half of the test above: with a series longer than the horizon, the
    real labeller returns rows, the engine writes them, and the parquet carries the
    column `research/walkforward.py` purges on.

    Without this one, `labelled_rows == 0` above would pass equally against an engine
    that never called the labeller at all.
    """
    import polars as pl

    directory = tmp_path / "long"
    write_archive(directory, "XBTUSD_15.csv", list(range(200)))
    engine = BacktestEngine(archive_dir=directory, derived_dir=tmp_path / "derived")
    result = engine.process(engine_context, {})

    assert result.status is EngineStatus.OK
    assert result.data["labelled_rows"] > 0
    assert sum(result.data["label_counts"].values()) == result.data["labelled_rows"]

    written = pl.read_parquet(Path(result.data["slice_path"]))
    assert written.height == result.data["labelled_rows"]
    assert "label_window_end_ts" in written.columns
    assert set(written["label"].to_list()) <= {"target", "stop", "timeout"}
