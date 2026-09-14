"""`python -m acsoe.research.training` end to end, with no double anywhere. Spec 67.

**Nothing in this file is a fake.** The archive is real CSVs in the layout
`data/historical/` uses, written from the committed `candles_sample.parquet`; the config is
the committed `config/default.yaml` with two paths redirected into `tmp_path`; the replay,
the labeller, the feature builder, the trainer and the artefact writer are all the real
ones. That is the point: `main()` is the only path in this module nothing exercised, and the
seam that went unnoticed there was a real one — `ArchiveReplay.frames()` became a generator
under spec 79 while `main()` still subscripted it as a dict, and the suite stayed green
because no test ran `main()` at all. With `--pairs` the failure even read as a plausible
"the archive has no XBTUSD", blaming the operator's argument.

The second thing this file asserts is the one spec 67's close-out is about: **the builder
never holds two pairs' archive frames at once.** The eager version held every pair's Decimal
frame, about 60 GB over 234 pairs at the measured 3 KB a bar, to produce a file of a few
hundred megabytes — the same wall engine 23 came off in spec 78. A memory measurement would
be flaky; counting live frames is not.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import require_module

pl = require_module("polars", reason="polars is not installed")
require_module("lightgbm", reason="lightgbm is not installed")
require_module("pyarrow", reason="pyarrow is not installed")
training = require_module(
    "acsoe.research.training", reason="acsoe.research.training does not exist yet"
)

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "tests" / "fixtures" / "candles_sample.parquet"
DEFAULT_CONFIG = REPO / "config" / "default.yaml"

#: The archive spellings `config/default.yaml` gives the two macro assets. Every run carries
#: them, smoke runs included: a run without them produces a different feature list and an
#: artefact engine 8 refuses.
MACRO = ("XBTUSD", "ETHUSD")
OTHER = "AAAUSD"
BAR = 900

#: 110 days of 15-minute bars. **Not a round number picked for comfort**: the walk-forward
#: needs more than `backtest.training_window_days` (90) plus one `retrain_interval_days` (7)
#: before its first test window opens, and a run that produced no folds would fail here with
#: a message about the splitter rather than about `main()`. The committed sample is 12.5
#: days, so it is tiled — see `archive_rows`.
BARS = 110 * 96


def archive_rows(shift: float, count: int = BARS) -> list[tuple[Any, ...]]:
    """OHLCVT rows in the archive's own CSV order, from the committed sample.

    **Every bar-to-bar return here is real market data.** The committed sample is 1,208 real
    SOLUSD bars and the walk-forward needs at least 97 days before its first fold, so the
    sample's *returns* are cycled to build a longer path, each lap continuing from the last
    close rather than jumping back to the start. Volume and trade counts cycle with them.

    Tiling is stated rather than hidden because it matters for what this file can claim: it
    is a test of `main()`, the streaming builder and the `--pairs` filter, not a measurement
    of anything about the market. A model's numbers over a tiled series mean nothing, which
    is why nothing here asserts one.

    `shift` scales the starting price so the three pairs are not the same series under three
    names, which would let a per-pair bug pass unnoticed.
    """
    frame = pl.read_parquet(SAMPLE).sort("ts")
    source = frame.to_dicts()
    origin = int(frame["ts"][0])
    price = float(source[0]["open"]) * shift
    rows: list[tuple[Any, ...]] = []
    for index in range(count):
        bar = source[index % len(source)]
        opening = float(bar["open"])
        step = float(bar["close"]) / opening if opening else 1.0
        closing = price * step
        rows.append(
            (
                origin + index * BAR,
                price,
                max(price, closing) * (float(bar["high"]) / max(opening, 1e-12)),
                min(price, closing) * (float(bar["low"]) / max(opening, 1e-12)),
                closing,
                float(bar["volume"]),
                int(bar["trades"]),
            )
        )
        price = closing
    return rows


@pytest.fixture(scope="module")
def archive(tmp_path_factory: Any) -> Path:
    """Three pairs of real bars on a contiguous grid, in the archive's CSV layout."""
    directory = tmp_path_factory.mktemp("archive")
    for index, pair in enumerate((*MACRO, OTHER)):
        lines = [
            ",".join(str(value) for value in row)
            for row in archive_rows(1.0 + 0.11 * index)
        ]
        (directory / f"{pair}_15.csv").write_bytes(
            ("\n".join(lines) + "\n").encode("utf-8")
        )
    return directory


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """The committed config with `models.dir` pointed into `tmp_path`.

    Two lines changed and nothing else, so every threshold, barrier and absent operator key
    is the real one. A fabricated config would let this test pass against settings nobody
    ships.
    """
    text = DEFAULT_CONFIG.read_bytes().decode("utf-8")
    assert "\n  dir: models" in text, "config/default.yaml no longer spells models.dir this way"
    redirected = text.replace(
        "\n  dir: models", "\n  dir: " + str(tmp_path / "models").replace("\\", "/"), 1
    )
    path = tmp_path / "config.yaml"
    path.write_bytes(redirected.encode("utf-8"))
    return path


def run_main(config_path: Path, archive: Path, tmp_path: Path, *extra: str) -> int:
    return training.main(
        [
            "--config",
            str(config_path),
            "--archive",
            str(archive),
            "--derived",
            str(tmp_path / "derived"),
            "--max-folds",
            "1",
            *extra,
        ]
    )


def dataset_written(tmp_path: Path) -> Path:
    written = sorted((tmp_path / "derived").glob("dataset_*.parquet"))
    assert written, "main() wrote no dataset parquet"
    return written[-1]


# --------------------------------------------------------------------------- #
# It runs at all
# --------------------------------------------------------------------------- #


def test_main_runs_over_the_whole_archive(
    config_path: Path, archive: Path, tmp_path: Path, capsys: Any
) -> None:
    """The seam nothing exercised. `frames()` became a generator under spec 79 and `main()`
    subscripted it as a dict; the suite was green with this path broken."""
    assert run_main(config_path, archive, tmp_path) == 0
    printed = capsys.readouterr().out
    assert "fold(s)" in printed
    assert "row(s) written" in printed


def test_main_with_pairs_reads_only_what_it_was_asked_for(
    config_path: Path, archive: Path, tmp_path: Path
) -> None:
    """`--pairs AAAUSD` plus the macro pairs it always carries, and nothing else.

    The failure this replaces read as "the archive has no XBTUSD" — a message blaming the
    operator's argument for a defect in the reader.
    """
    assert run_main(config_path, archive, tmp_path, "--pairs", OTHER) == 0
    frame = pl.read_parquet(dataset_written(tmp_path))
    assert sorted(set(frame["pair"])) == sorted([OTHER, *MACRO])


def test_a_pair_that_is_not_in_the_archive_names_the_spelling(
    config_path: Path, archive: Path, tmp_path: Path
) -> None:
    """`--pairs` takes archive spellings, and the refusal says so. `BTC/USD` is the live
    name and naming it here is the mistake most likely to be made."""
    with pytest.raises(training.TrainingError) as caught:
        run_main(config_path, archive, tmp_path, "--pairs", "BTC/USD")
    assert "archive spellings" in str(caught.value)


def test_the_macro_pairs_are_carried_even_when_not_asked_for(
    config_path: Path, archive: Path, tmp_path: Path
) -> None:
    """A run without them produces a different feature list and an artefact engine 8 will
    refuse. Asserted on the columns rather than on the pair list, because the feature list
    is the thing that has to match."""
    assert run_main(config_path, archive, tmp_path, "--pairs", OTHER) == 0
    columns = pl.read_parquet(dataset_written(tmp_path)).columns
    assert any(name.startswith("macro_btc_") for name in columns)
    assert any(name.startswith("macro_eth_") for name in columns)
    assert "macro_available" in columns


def test_the_dataset_carries_its_provenance_in_the_file(
    config_path: Path, archive: Path, tmp_path: Path
) -> None:
    """A parquet that cannot say where it came from is indistinguishable from one written by
    hand — the rule `labelled_sample.parquet` was deposited under, and the row groups are now
    written by a streaming writer that had to be taught to keep it."""
    import pyarrow.parquet as pq

    assert run_main(config_path, archive, tmp_path) == 0
    metadata = pq.ParquetFile(dataset_written(tmp_path)).schema_arrow.metadata
    recorded = json.loads((metadata or {})[b"acsoe_provenance"].decode("utf-8"))
    assert recorded["archive"] == str(archive)
    assert recorded["feature_version"] == "f1"
    assert recorded["interval_s"] == BAR
    assert recorded["macro_assets"] == ["btc", "eth"]
    assert recorded["rows"] == pl.read_parquet(dataset_written(tmp_path)).height


def test_the_dataset_is_written_as_one_row_group_per_pair(
    config_path: Path, archive: Path, tmp_path: Path
) -> None:
    """The mechanism, asserted rather than assumed.

    One row group per pair is what makes the build streamable; a file written as a single
    group is one that was assembled in memory first, which is the thing this fix removes.
    """
    import pyarrow.parquet as pq

    assert run_main(config_path, archive, tmp_path) == 0
    handle = pq.ParquetFile(dataset_written(tmp_path))
    assert handle.num_row_groups == 3, handle.num_row_groups


# --------------------------------------------------------------------------- #
# --ranking-study, spec 75
# --------------------------------------------------------------------------- #


def test_the_ranking_study_mode_writes_a_report_and_trains_nothing(
    config_path: Path, archive: Path, tmp_path: Path, capsys: Any
) -> None:
    """The second branch of `main()`, driven here for the reason the first one had to be.

    A branch nothing runs is a branch that is green while broken — which is how
    `ArchiveReplay.frames()` becoming a generator went unnoticed. This one is newer than that
    lesson, so it gets its test in the same change rather than in the next session.

    **Trains nothing** is asserted by the absence of a second dataset file: the study is a
    reading of a run that already happened, and re-training to produce it would make the
    table describe a different model from the one the operator is ruling on.
    """
    assert run_main(config_path, archive, tmp_path) == 0
    dataset = dataset_written(tmp_path)
    oos = sorted((tmp_path / "derived").glob("oos_*.parquet"))
    assert oos, "the training run wrote no out-of-sample file"
    before = sorted((tmp_path / "derived").glob("dataset_*.parquet"))
    capsys.readouterr()

    docs = tmp_path / "docs"
    assert (
        training.main(
            [
                "--config",
                str(config_path),
                "--ranking-study",
                str(oos[-1]),
                "--dataset",
                str(dataset),
                "--docs",
                str(docs),
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    assert "No feature is recommended" in printed

    written = sorted(docs.glob("ranking-study-*.json"))
    assert len(written) == 1
    report = json.loads(written[0].read_bytes().decode("utf-8"))
    assert report["meta"]["recommends"] is None
    assert report["break_even"]["friction"] is None
    assert report["rankings"][0]["feature"].startswith("(")
    assert sorted((tmp_path / "derived").glob("dataset_*.parquet")) == before


def test_the_ranking_study_refuses_without_a_dataset(
    config_path: Path, archive: Path, tmp_path: Path, capsys: Any
) -> None:
    """The feature values are in the dataset, not in the out-of-sample file, which carries
    what the predictor *said*. A study run without one would have nothing to rank by."""
    assert run_main(config_path, archive, tmp_path) == 0
    oos = sorted((tmp_path / "derived").glob("oos_*.parquet"))[-1]
    capsys.readouterr()
    assert (
        training.main(
            ["--config", str(config_path), "--ranking-study", str(oos)]
        )
        == 2
    )
    assert "--dataset" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# One frame resident
# --------------------------------------------------------------------------- #


def test_the_builder_never_holds_two_archive_frames_at_once(
    config_path: Path, archive: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 67's close-out, counted rather than measured.

    A resident-memory measurement would be flaky and would also pass a build that held two
    frames of a three-pair archive. Counting live frames is exact: `ArchiveReplay.frame` is
    wrapped so that every frame it returns registers its own death, and the high-water mark
    of live frames is asserted.

    **Two is allowed, one is not achievable.** The macro assets' *features* are computed
    before the loop and stay resident, and their archive frames are dropped as soon as they
    are reduced — but the caller holds one macro frame while computing its features, and
    Python's collector may not have run by the time the next is read. What must never happen
    is the shape this fix removes: every pair's frame alive at once, which on the real
    archive is 234 of them and about 60 GB.
    """
    import weakref

    from acsoe.research.replay import ArchiveReplay

    live = 0
    peak = 0
    original = ArchiveReplay.frame

    def counted(self: Any, pair: str) -> Any:
        nonlocal live, peak
        frame = original(self, pair)
        live += 1
        peak = max(peak, live)

        def died(_reference: Any) -> None:
            nonlocal live
            live -= 1

        counted.keep.append(weakref.ref(frame, died))  # type: ignore[attr-defined]
        return frame

    counted.keep = []  # type: ignore[attr-defined]
    monkeypatch.setattr(ArchiveReplay, "frame", counted)

    assert run_main(config_path, archive, tmp_path) == 0
    assert peak <= 2, (
        f"the dataset builder held {peak} archive frames at once. Over 234 pairs at the "
        "measured 3 KB a bar that is about 60 GB, which is the wall engine 23 came off in "
        "spec 78."
    )


def test_the_streaming_builder_and_the_in_memory_one_agree(
    config_path: Path, archive: Path, tmp_path: Path
) -> None:
    """Two paths into one dataset, so they are checked against each other.

    `build_dataset` is what the Phase 5 criteria and most tests call; `build_dataset_to_parquet`
    is what the full run uses. They share `dataset_rows_for_pair`, and this is the assertion
    that keeps that sharing honest rather than nominal.
    """
    from acsoe.platform.config import load_config
    from acsoe.research.labelling import label_frame

    config = load_config(config_path)
    interval_s = int(config.get("timeframes.decision_bar_s"))
    min_fill = float(config.get("features.min_lookback_fill"))

    frames = dict(training._archive_frames(archive, interval_s, ()))
    labelled = {
        pair: label_frame(frame, pair=pair, config=config, interval_s=interval_s)[0]
        for pair, frame in frames.items()
    }
    macro_features = {
        asset: training._features_of(frames[pair], interval_s, min_fill)
        for asset, pair in (("btc", "XBTUSD"), ("eth", "ETHUSD"))
    }
    eager = training.build_dataset(
        labelled,
        frames,
        config=config,
        macro_archive={"btc": "XBTUSD", "eth": "ETHUSD"},
    )

    streamed_path = tmp_path / "streamed.parquet"
    training.build_dataset_to_parquet(
        training._archive_frames(archive, interval_s, ()),
        streamed_path,
        config=config,
        macro_features=macro_features,
    )
    streamed = pl.read_parquet(streamed_path).sort(["decision_ts", "pair"])

    assert streamed.columns == eager.columns
    assert streamed.height == eager.height
    assert streamed.equals(eager)
