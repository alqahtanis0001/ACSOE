"""`scripts/partition_trades.py` — the time-and-sales archive, weekly, for replay. Spec 128.

The fixtures are constructed, not cut from the archive. The properties that matter —
a miscount refused, a malformed row refused, a row arriving after its week refused —
cannot be shown on Kraken's export, which is clean. A test reading the real file would
pass against a partitioner with none of those refusals in it.

Every assertion here was run against a deliberately broken partitioner and seen red;
the sweep is in `docs/build-log/phase-7/a-platform.md`.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "partition_trades.py"

WEEK = 7 * 24 * 60 * 60
#: Saturday 2024-06-22 00:00 UTC, on the fold grid (two weeks before fold 379).
START = int(datetime(2024, 6, 22, tzinfo=UTC).timestamp())
END = START + 4 * WEEK


@pytest.fixture(scope="module")
def pt() -> ModuleType:
    """`scripts/partition_trades.py`, imported by path. It is not a package."""
    spec = importlib.util.spec_from_file_location("acsoe_partition_trades_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_source(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    """Kraken's shape: `timestamp,price,volume`, no header, CRLF as the archive has it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(f"{ts},{price},{vol}\r\n".encode() for ts, price, vol in rows))
    return path


def write_bars(path: Path, counts: dict[int, int]) -> Path:
    """A `_15.csv` whose only column this script reads is the trade count."""
    path.write_bytes(
        b"".join(f"{ts},1,1,1,1,1,{n}\n".encode() for ts, n in sorted(counts.items()))
    )
    return path


def run(pt: ModuleType, source: Path, out: Path, **kwargs: Any) -> dict[str, Any]:
    stats: dict[str, Any] = pt.partition_pair(
        "AAAUSD", source, out, start=START, end=END, **kwargs
    )
    return stats


def read_week(out: Path, day: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = pq.read_table(out / "AAAUSD" / f"{day}.parquet").to_pylist()
    return rows


MIXED: list[tuple[str, str, str]] = [
    (str(START - 10), "1.0", "5"),  # before the window
    (str(START), "63810.0", "0.10000000"),
    (str(START), "63809.9", "0.0031459"),  # same second, file order kept
    (str(START + 5), "1E-8", "2"),  # a decimal the bar builder reads, kept as written
    (str(START + 2 * WEEK + 1), "0.00001234", "1000.5"),
    (str(END - 1), "7", "0.5"),
    (str(END), "8", "0.5"),  # after the window
]


def test_rows_land_in_their_fold_week_as_published(pt: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "out"
    stats = run(pt, write_source(tmp_path / "src.csv", MIXED), out)
    assert sorted(p.name for p in (out / "AAAUSD").iterdir()) == [
        "2024-06-22.parquet",
        "2024-07-06.parquet",
        "2024-07-13.parquet",
    ]
    assert read_week(out, "2024-06-22") == [
        {"ts": START, "price": "63810.0", "volume": "0.10000000"},
        {"ts": START, "price": "63809.9", "volume": "0.0031459"},
        {"ts": START + 5, "price": "1E-8", "volume": "2"},
    ]
    assert read_week(out, "2024-07-06") == [
        {"ts": START + 2 * WEEK + 1, "price": "0.00001234", "volume": "1000.5"}
    ]
    assert read_week(out, "2024-07-13") == [{"ts": END - 1, "price": "7", "volume": "0.5"}]
    assert stats["rows_before_window"] == 1
    assert stats["rows_after_window"] == 1
    assert stats["rows_in_window"] == 5
    assert stats["rows_written"] == 5
    assert stats["source_rows"] == 7


def test_a_quiet_week_has_no_file_and_is_listed_empty(pt: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "out"
    stats = run(pt, write_source(tmp_path / "src.csv", MIXED), out)
    assert not (out / "AAAUSD" / "2024-06-29.parquet").exists()
    assert stats["empty_weeks"] == ["2024-06-29"]
    assert stats["weeks"] == {
        "2024-06-22": 3,
        "2024-06-29": 0,
        "2024-07-06": 1,
        "2024-07-13": 1,
    }


def test_the_source_digest_covers_the_whole_file(pt: ModuleType, tmp_path: Path) -> None:
    source = write_source(tmp_path / "src.csv", MIXED)
    stats = run(pt, source, tmp_path / "out", block_bytes=64)
    assert stats["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert stats["source_bytes"] == source.stat().st_size


def test_a_planted_miscount_is_refused(
    pt: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A writer that drops one row: the files no longer hold what the stream counted."""
    real = pt._write_slice

    def lossy(writer: Any, table: Any) -> None:
        real(writer, table.slice(1))

    monkeypatch.setattr(pt, "_write_slice", lossy)
    out = tmp_path / "out"
    with pytest.raises(pt.PartitionError, match="do not reconcile"):
        run(pt, write_source(tmp_path / "src.csv", MIXED), out)
    assert not (out / "AAAUSD").exists()


def test_the_models_bars_must_agree(pt: ModuleType, tmp_path: Path) -> None:
    source = write_source(tmp_path / "src.csv", MIXED)
    bars = {START - 900: 1, START: 3, START + 2 * WEEK: 1, END - 900: 1, END: 1}
    agreeing = write_bars(tmp_path / "good_15.csv", bars)
    assert run(pt, source, tmp_path / "a", bars_csv=agreeing)["trades_in_bars"] == 5

    short = write_bars(tmp_path / "bad_15.csv", {**bars, START: 2})
    with pytest.raises(pt.PartitionError, match="bars"):
        run(pt, source, tmp_path / "b", bars_csv=short)
    assert not (tmp_path / "b" / "AAAUSD").exists()


@pytest.mark.parametrize(
    ("row", "why"),
    [
        (("1719014400", "1.0"), "columns"),
        ((str(START + 1), "1.0", "1", "extra"), "columns"),
        ((str(START + 1) + ".5", "1.0", "1"), "AAAUSD"),
        ((str(START + 1), "one", "1"), "price"),
        ((str(START + 1), "1.0", "NaN"), "volume"),
    ],
)
def test_a_row_the_bar_builder_would_skip_refuses_the_pair(
    pt: ModuleType, tmp_path: Path, row: tuple[str, ...], why: str
) -> None:
    source = tmp_path / "src.csv"
    body = [f"{START},1.0,1", ",".join(row), f"{START + 2},1.0,1"]
    source.write_bytes(("\r\n".join(body) + "\r\n").encode())
    with pytest.raises(pt.PartitionError, match=why):
        run(pt, source, tmp_path / "out")
    assert not (tmp_path / "out" / "AAAUSD").exists()


def test_a_row_arriving_after_its_week_was_written_is_refused(
    pt: ModuleType, tmp_path: Path
) -> None:
    rows = [(str(START + 1), "1", "1"), (str(START + WEEK + 1), "1", "1"), (str(START + 2), "1", "1")]
    with pytest.raises(pt.PartitionError, match="after its week"):
        run(pt, write_source(tmp_path / "src.csv", rows), tmp_path / "out")


def test_out_of_order_rows_within_one_week_are_kept_in_file_order_and_counted(
    pt: ModuleType, tmp_path: Path
) -> None:
    rows = [(str(START + 9), "1", "1"), (str(START + 3), "2", "1"), (str(START + 7), "3", "1")]
    out = tmp_path / "out"
    stats = run(pt, write_source(tmp_path / "src.csv", rows), out)
    assert [r["price"] for r in read_week(out, "2024-06-22")] == ["1", "2", "3"]
    assert stats["out_of_order_rows"] == 1


def test_partitions_are_written_once(pt: ModuleType, tmp_path: Path) -> None:
    source = write_source(tmp_path / "src.csv", MIXED)
    run(pt, source, tmp_path / "out")
    with pytest.raises(pt.PartitionError, match="already exists"):
        run(pt, source, tmp_path / "out")


def test_sources_resolve_as_the_bar_builder_resolves_them(pt: ModuleType, tmp_path: Path) -> None:
    """The first directory wins, as in `build_ohlcvt.find_pair_file`, and a provenance
    that recorded the other file refuses."""
    first = write_source(tmp_path / "one" / "AAAUSD.csv", MIXED)
    write_source(tmp_path / "two" / "AAAUSD.csv", MIXED)
    builder = pt.load_build_ohlcvt()
    dirs = (tmp_path / "one", tmp_path / "two")
    ok = pt.resolve_sources({"pairs": {"AAAUSD": {"source_file": str(first)}}}, dirs, builder)
    assert ok == {"AAAUSD": first}
    other = {"pairs": {"AAAUSD": {"source_file": str(tmp_path / "two" / "AAAUSD.csv")}}}
    with pytest.raises(pt.PartitionError, match="PROVENANCE"):
        pt.resolve_sources(other, dirs, builder)


def test_the_run_writes_a_manifest_and_refuses_output_inside_the_archive(
    pt: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through `main`, from a working directory shaped like the repository."""
    monkeypatch.chdir(tmp_path)
    historical = tmp_path / "data" / "historical"
    source = write_source(historical / "KRAKEN_TimeAndSales_Combined" / "AAAUSD.csv", MIXED)
    write_bars(historical / "AAAUSD_15.csv", {START: 3, START + 2 * WEEK: 1, END - 900: 1})
    (historical / "PROVENANCE.json").write_bytes(
        json.dumps(
            {"pairs": {"AAAUSD": {"file": "AAAUSD_15.csv", "source_file": str(source.relative_to(tmp_path))}}}
        ).encode()
    )
    common = [
        "--provenance", str(historical / "PROVENANCE.json"),
        "--window-start", "2024-07-06T00:00:00+00:00",
        "--window-end", "2024-07-20T00:00:00+00:00",
        "--warmup-weeks", "2",
    ]
    out = tmp_path / "data" / "derived" / "trades_weekly"
    assert pt.main([*common, "--out-dir", str(out), "--write"]) == 0
    manifest = json.loads((out / "MANIFEST.json").read_bytes())
    assert manifest["partitions_start"] == "2024-06-22"
    assert manifest["pairs"]["AAAUSD"]["rows_in_window"] == 5
    assert manifest["pairs"]["AAAUSD"]["trades_in_bars"] == 5
    assert manifest["pairs"]["AAAUSD"]["source_file"].endswith("KRAKEN_TimeAndSales_Combined/AAAUSD.csv")
    assert manifest["script_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    # Written once.
    assert pt.main([*common, "--out-dir", str(out), "--write"]) == 1


# --------------------------------------------------------------------------- #
# Memory does not grow with file size
# --------------------------------------------------------------------------- #

_MEASURE = textwrap.dedent(
    """
    import importlib.util, sys
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("pt", sys.argv[1])
    pt = importlib.util.module_from_spec(spec); spec.loader.exec_module(pt)
    stats = pt.partition_pair(
        "AAAUSD", Path(sys.argv[2]), Path(sys.argv[3]),
        start=int(sys.argv[4]), end=int(sys.argv[5]), block_bytes=1 << 20,
    )
    print(stats["peak_working_set_bytes"], stats["rows_in_window"])
    """
)


def _synthetic(path: Path, rows: int) -> Path:
    """``rows`` trades, all inside the window's first week, about 28 bytes each."""
    step = max(1, (WEEK - 1) // rows) if rows < WEEK else 0
    with path.open("wb") as handle:
        chunk: list[bytes] = []
        for i in range(rows):
            ts = START + (i * step if step else i * WEEK // rows)
            chunk.append(b"%d,%d.%05d,0.%08d\r\n" % (ts, 60000 + i % 997, i % 100000, i % 99999999))
            if len(chunk) == 100_000:
                handle.write(b"".join(chunk))
                chunk.clear()
        handle.write(b"".join(chunk))
    return path


def _peak(tmp_path: Path, source: Path, name: str) -> tuple[int, int]:
    result = subprocess.run(
        [sys.executable, "-c", _MEASURE, str(SCRIPT), str(source), str(tmp_path / name), str(START), str(END)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    peak, rows = result.stdout.split()
    return int(peak), int(rows)


@pytest.mark.skipif(sys.platform != "win32", reason="the peak working set is the Win32 counter")
def test_peak_memory_does_not_grow_with_file_size(tmp_path: Path) -> None:
    """One file and one four times as large: the peak working set moves by far less than
    the difference between them. An eager read would add the whole larger file, parsed."""
    small = _synthetic(tmp_path / "small.csv", 1_500_000)
    large = _synthetic(tmp_path / "large.csv", 6_000_000)
    grown = large.stat().st_size - small.stat().st_size
    assert grown > 120 * 2**20
    small_peak, small_rows = _peak(tmp_path, small, "small")
    large_peak, large_rows = _peak(tmp_path, large, "large")
    assert (small_rows, large_rows) == (1_500_000, 6_000_000)
    assert large_peak - small_peak < grown // 4, (small_peak, large_peak, grown)
