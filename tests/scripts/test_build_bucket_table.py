"""`scripts/build_bucket_table.py` — the declared spread and depth table. Spec 130.

The arithmetic is driven by constructed summary files, because every filter this script
applies (schema version, `clean`, samples, depth reached, the span's end) is only visible
when a row that should be dropped is planted beside one that should be kept. The committed
fixture is then read with no double: it carries the declared statement, and its medians are
the ones `phase-7-findings.md` §3 publishes. Where the recording is on disk, it is rebuilt
and compared.

Every assertion here was run against a deliberately broken script and seen red; the sweep is
in `docs/build-log/phase-7/a-platform.md`.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_bucket_table.py"
REPLAY = REPO_ROOT / "tests" / "fixtures" / "replay"
TABLE = REPLAY / "spread_book_table_2026-09-19.json"
CLASSES = REPLAY / "kraken_fee_schedule_2026-09-19.pair_classes.json"
T0 = datetime(2026, 9, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def bbt() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_build_bucket_table_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(pair: str, minute: int, **fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "v": 2,
        "kind": "summary",
        "pair": pair,
        "minute": (T0 + timedelta(minutes=minute)).isoformat().replace("+00:00", "Z"),
        "spread_bps": [1.0, 10.0, 20.0],
        "depth_bid_bps": 30.0,
        "samples": 10,
        "depth_samples": 5,
        "quote_volume": 0.0,
        "clean": True,
    }
    base.update(fields)
    return base


def write_summaries(directory: Path, rows: list[dict[str, Any]], *, tail: bytes = b"") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "summary__msi__2026-09-12.jsonl"
    path.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in rows) + tail)
    return path


def build(bbt: ModuleType, root: Path, *, until_minute: int = 10_000) -> dict[str, Any]:
    table: dict[str, Any] = bbt.build(root, until=T0 + timedelta(minutes=until_minute))
    return table


def by_label(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["bucket"]: r for r in table["buckets"]}


def test_only_clean_v2_minutes_with_samples_set_a_pairs_spread(
    bbt: ModuleType, tmp_path: Path
) -> None:
    rows = [
        row("AAA/USD", 0, spread_bps=[1, 10.0, 20]),
        row("AAA/USD", 1, spread_bps=[1, 12.0, 20]),
        row("AAA/USD", 2, spread_bps=[1, 14.0, 20]),
        row("AAA/USD", 3, spread_bps=[1, 900.0, 20], clean=False),
        row("AAA/USD", 4, spread_bps=[1, 900.0, 20], v=1),
        row("AAA/USD", 5, spread_bps=[1, 900.0, 20], samples=0),
        row("AAA/EUR", 6, spread_bps=[1, 900.0, 20]),  # not USD
        # Not a summary row, but shaped enough like one to move the median if admitted.
        {**row("AAA/USD", 7, spread_bps=[1, 900.0, 20]), "kind": "gap"},
        {**row("AAA/USD", 8, spread_bps=[1, 900.0, 20]), "kind": "session"},
    ]
    write_summaries(tmp_path / "data" / "summaries", rows)
    bucket = by_label(build(bbt, tmp_path))["<$10k"]
    assert bucket["pair_list"] == ["AAA/USD"]
    assert bucket["spread_bps"]["median"] == 12.0


def test_depth_is_taken_only_from_minutes_that_reached_ten_thousand(
    bbt: ModuleType, tmp_path: Path
) -> None:
    rows = [
        row("AAA/USD", 0, depth_bid_bps=30.0),
        row("AAA/USD", 1, depth_bid_bps=40.0),
        row("AAA/USD", 2, depth_bid_bps=500.0, depth_samples=0),
        row("BBB/USD", 0, depth_bid_bps=None, depth_samples=0),
    ]
    write_summaries(tmp_path / "data" / "summaries", rows)
    depth = by_label(build(bbt, tmp_path))["<$10k"]["depth_bid_bps_to_10k_from_mid"]
    assert depth["median"] == 35.0
    assert depth["pairs_with_depth"] == 1
    assert depth["pairs_never_reaching_10k"] == ["BBB/USD"]


def test_daily_volume_uses_every_row_over_the_whole_span_and_edges_are_inclusive(
    bbt: ModuleType, tmp_path: Path
) -> None:
    """The span is two days, from the first to the last USD minute over all pairs. So a
    pair needs $20,000 in the span to sit on the $10k edge, and an unclean row's volume
    still counts."""
    rows = [
        row("AAA/USD", 0, quote_volume=10_000.0),
        row("AAA/USD", 1, quote_volume=10_000.0, clean=False),
        row("BBB/USD", 0, quote_volume=19_999.0),
        row("ZZZ/USD", 2 * 24 * 60, quote_volume=0.0),
    ]
    write_summaries(tmp_path / "data" / "summaries", rows)
    table = by_label(build(bbt, tmp_path))
    assert table["$10k-100k"]["pair_list"] == ["AAA/USD"]
    assert table["<$10k"]["pair_list"] == ["BBB/USD", "ZZZ/USD"]


def test_rows_after_the_span_end_and_a_half_written_line_are_not_read(
    bbt: ModuleType, tmp_path: Path
) -> None:
    rows = [row("AAA/USD", 0, spread_bps=[1, 10.0, 2]), row("AAA/USD", 100, spread_bps=[1, 90.0, 2])]
    partial = json.dumps(row("AAA/USD", 1, spread_bps=[1, 70.0, 2])).encode()
    path = write_summaries(tmp_path / "data" / "summaries", rows, tail=partial)
    table = build(bbt, tmp_path, until_minute=50)
    assert by_label(table)["<$10k"]["spread_bps"]["median"] == 10.0
    source = table["_provenance"]["sources"][0]
    complete = path.read_bytes()[: -len(partial)]
    assert source["bytes_read"] == len(complete)
    assert source["sha256"] == hashlib.sha256(complete).hexdigest()


def test_an_empty_top_bucket_borrows_the_row_below_and_says_so(
    bbt: ModuleType, tmp_path: Path
) -> None:
    rows = [row("AAA/USD", 0, quote_volume=5e6), row("ZZZ/USD", 24 * 60)]
    write_summaries(tmp_path / "data" / "summaries", rows)
    top = by_label(build(bbt, tmp_path))[">$10M"]
    assert top["pairs"] == 0
    assert top["mapped_to"] == "$1M-10M"

    rows.append(row("BIG/USD", 1, quote_volume=2e7))
    write_summaries(tmp_path / "data" / "summaries", rows)
    top = by_label(build(bbt, tmp_path))[">$10M"]
    assert top["pair_list"] == ["BIG/USD"]
    assert "mapped_to" not in top


def test_the_reproduction_check_can_say_no(bbt: ModuleType) -> None:
    published = [
        {
            "bucket": label,
            "pairs": pairs,
            "spread_bps": {"median": spread, "q25": low, "q75": high},
            "slippage_5k_bps_check_only": slip,
        }
        for label, (pairs, spread, low, high, slip) in bbt.FINDINGS_TABLE.items()
    ]
    assert bbt.reproduction(published)["all_equal"] is True
    published[2]["spread_bps"] = {**published[2]["spread_bps"], "q75": 19.6}
    check = bbt.reproduction(published)
    assert check["all_equal"] is False
    assert check["buckets"]["$100k-1M"]["equal"] is False


# --------------------------------------------------------------------------- #
# The committed fixtures, with no double
# --------------------------------------------------------------------------- #


def test_the_committed_table_is_declared_and_carries_the_published_medians(
    bbt: ModuleType,
) -> None:
    table = json.loads(TABLE.read_bytes())
    assert table["_provenance"]["statement"].startswith("DECLARED, NOT MEASURED.")
    assert table["_provenance"]["script_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    rows = by_label(table)
    for label, (pairs, spread, *_rest) in bbt.FINDINGS_TABLE.items():
        assert rows[label]["pairs"] == pairs
        assert round(rows[label]["spread_bps"]["median"], 1) == spread
    assert rows[">$10M"]["mapped_to"] == "$1M-10M"


@pytest.mark.skipif(
    not (REPO_ROOT / "data" / "summaries").is_dir(), reason="the recording is not in this clone"
)
def test_the_committed_table_rebuilds_from_the_recording(bbt: ModuleType) -> None:
    committed = json.loads(TABLE.read_bytes())
    until = bbt.parse_minute(committed["_provenance"]["recording_span"]["until"])
    rebuilt = bbt.build(REPO_ROOT, until=until)
    assert rebuilt["buckets"] == committed["buckets"]
    assert rebuilt["reproduction"] == committed["reproduction"]


def test_the_fee_class_companion_quotes_the_page_and_covers_every_archive_pair() -> None:
    classes = json.loads(CLASSES.read_bytes())
    page = gzip.decompress((REPLAY / "kraken_fee_schedule_2026-09-19.html.gz").read_bytes())
    rule = classes["_provenance"]["page_rule_verbatim"].replace('"', "&quot;")
    assert rule.encode() in page
    schedule = (REPLAY / "kraken_fee_schedule_2026-09-19.json").read_bytes()
    assert classes["_provenance"]["companion_of_sha256"] == hashlib.sha256(schedule).hexdigest()
    archive = {
        p.name[: -len("_15.csv")] for p in (REPO_ROOT / "data" / "historical").glob("*USD_15.csv")
    }
    if archive:
        assert set(classes["pairs"]) == archive
    tables = {entry["table"] for entry in classes["pairs"].values()}
    assert tables <= {"spot_crypto", "stablecoin_pegged_fx", None}
    # A stablecoin that is the quote only is Spot Crypto, by the page's own sentence.
    for pair, entry in classes["pairs"].items():
        symbol = entry["v2_symbol"]
        if entry["table"] == "stablecoin_pegged_fx":
            assert symbol is not None and symbol.endswith("/USD"), pair
        if symbol is not None and symbol.split("/")[1] not in ("USD",):
            assert entry["table"] == "spot_crypto", pair
