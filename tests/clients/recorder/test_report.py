"""Spec 27 — the recording digest.

The property under test is **tiling**: the segments and the gaps together account for
every microsecond between the first frame and the last, with no hole and no overlap.
That is what makes a silent outage impossible to mistake for a quiet market, and it is
strictly stronger than a gap count — a count can be right while a break sits
unaccounted for between two segments nobody compared.

The second property is that an injected gap **appears as a gap** rather than being
closed silently. Both kinds are tested: an explicit `gap` marker written on reconnect,
and an implicit silence left by a recorder that was not running at all.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.recorder.contracts import RECORDER_CHANNEL, build_line
from acsoe.clients.recorder.report import build_report

START = datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def tick(moment: datetime) -> dict[str, Any]:
    return build_line(
        kind="tick",
        pair="BTC/USD",
        channel="trade",
        ts_exchange=None,
        ts_recv=iso(moment),
        payload={"channel": "trade", "data": [{"symbol": "BTC/USD"}]},
    )


def gap_marker(start: datetime, end: datetime, reason: str) -> dict[str, Any]:
    return build_line(
        kind="gap",
        pair=None,
        channel=RECORDER_CHANNEL,
        ts_exchange=None,
        ts_recv=iso(end),
        payload={
            "reason": reason,
            "disconnected_at": iso(start),
            "reconnected_at": iso(end),
            "gap_ms": int((end - start).total_seconds() * 1000),
        },
    )


def write(path: Path, lines: list[dict[str, Any]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n",
        encoding="utf-8",
    )
    return path


def steady(minutes: int, *, origin: datetime = START, step_s: int = 10) -> list[dict[str, Any]]:
    """A frame every `step_s` seconds for `minutes` minutes."""
    count = int(minutes * 60 / step_s)
    return [tick(origin + timedelta(seconds=index * step_s)) for index in range(count)]


def assert_tiles(report: dict[str, Any]) -> None:
    """Segments and gaps must cover the span exactly, with no hole and no overlap."""
    pieces = sorted(
        [(int(s["start"]), int(s["end"]), "segment") for s in report["segments"]]
        + [(int(g["start"]), int(g["end"]), "gap") for g in report["gaps"]]
    )
    assert pieces, "an empty tiling accounts for nothing"
    assert pieces[0][0] == int(report["span"]["start"])
    assert pieces[-1][1] == int(report["span"]["end"])
    for (_, end, _), (start, _, _) in zip(pieces, pieces[1:], strict=False):
        assert start == end, "a hole in the tiling is a break nobody accounted for"


# --------------------------------------------------------------------------- #
# The clean case
# --------------------------------------------------------------------------- #


def test_an_unbroken_recording_is_one_segment_and_no_gaps(tmp_path: Path) -> None:
    write(tmp_path / "kraken_v2_2026-03-01.jsonl", steady(30))
    report = build_report(sorted(tmp_path.glob("*.jsonl")))

    assert report["gaps"] == []
    assert len(report["segments"]) == 1
    assert_tiles(report)


def test_a_span_of_more_than_a_day_is_reported_in_hours(tmp_path: Path) -> None:
    lines = [tick(START), tick(START + timedelta(seconds=30)), tick(START + timedelta(hours=25))]
    write(tmp_path / "kraken_v2_2026-03-01.jsonl", lines)
    report = build_report(sorted(tmp_path.glob("*.jsonl")))
    assert report["span"]["hours"] == pytest.approx(25.0)


# --------------------------------------------------------------------------- #
# An injected gap appears as a gap
# --------------------------------------------------------------------------- #


def test_an_explicit_gap_marker_appears_as_a_gap_with_its_cause(tmp_path: Path) -> None:
    dropped = START + timedelta(minutes=10)
    back = dropped + timedelta(minutes=4)
    lines = [
        *steady(10),
        gap_marker(dropped, back, "ConnectionClosedError: 1006"),
        *steady(10, origin=back),
    ]
    write(tmp_path / "kraken_v2_2026-03-01.jsonl", lines)
    report = build_report(sorted(tmp_path.glob("*.jsonl")))

    assert len(report["gaps"]) == 1
    gap = report["gaps"][0]
    assert "ConnectionClosedError: 1006" in gap["cause"]
    assert gap["gap_ms"] == 4 * 60 * 1000
    assert len(report["segments"]) == 2
    assert_tiles(report)


def test_an_unrecorded_silence_appears_as_a_gap_even_with_no_marker(tmp_path: Path) -> None:
    """What a recorder that was *not running* leaves behind. It writes no marker
    precisely because it was not there to write one — which is exactly why the digest
    cannot rely on markers alone."""
    lines = [*steady(5), *steady(5, origin=START + timedelta(hours=3))]
    write(tmp_path / "kraken_v2_2026-03-01.jsonl", lines)
    report = build_report(sorted(tmp_path.glob("*.jsonl")))

    assert len(report["gaps"]) == 1
    assert "recorder was not running" in report["gaps"][0]["cause"]
    assert report["gaps"][0]["gap_ms"] > 2 * 3600 * 1000
    assert_tiles(report)


def test_a_gap_is_never_closed_silently(tmp_path: Path) -> None:
    """The negative of the two above: with the break present, the recorded time is
    strictly less than the span, and the difference is exactly the gap."""
    lines = [*steady(5), *steady(5, origin=START + timedelta(hours=2))]
    write(tmp_path / "kraken_v2_2026-03-01.jsonl", lines)
    report = build_report(sorted(tmp_path.glob("*.jsonl")))

    span_s = report["span"]["seconds"]
    recorded = report["totals"]["recorded_seconds"]
    missing = report["totals"]["missing_seconds"]
    assert recorded < span_s
    assert recorded + missing == pytest.approx(span_s)


def test_every_gap_carries_a_non_empty_cause(tmp_path: Path) -> None:
    dropped = START + timedelta(minutes=5)
    lines = [
        *steady(5),
        gap_marker(dropped, dropped + timedelta(minutes=2), "OSError: reset"),
        *steady(5, origin=dropped + timedelta(minutes=2)),
        *steady(5, origin=START + timedelta(hours=4)),
    ]
    write(tmp_path / "kraken_v2_2026-03-01.jsonl", lines)
    report = build_report(sorted(tmp_path.glob("*.jsonl")))

    assert len(report["gaps"]) == 2
    for gap in report["gaps"]:
        assert gap["cause"].strip()
    assert_tiles(report)


# --------------------------------------------------------------------------- #
# Robustness
# --------------------------------------------------------------------------- #


def test_it_spans_several_daily_files(tmp_path: Path) -> None:
    write(tmp_path / "kraken_v2_2026-03-01.jsonl", steady(30, origin=START + timedelta(hours=23)))
    write(tmp_path / "kraken_v2_2026-03-02.jsonl", steady(30, origin=START + timedelta(hours=24)))
    report = build_report(sorted(tmp_path.glob("*.jsonl")))
    assert len(report["source_files"]) == 2
    assert_tiles(report)


def test_a_truncated_final_line_is_skipped_rather_than_repaired(tmp_path: Path) -> None:
    """A process killed mid-write leaves a partial line. Invariant 11 forbids
    repairing a recording, so it is skipped and the rest is read."""
    path = tmp_path / "kraken_v2_2026-03-01.jsonl"
    write(path, steady(5))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"v":1,"kind":"tick","pair":null,"chan')
    report = build_report(sorted(tmp_path.glob("*.jsonl")))
    assert report["totals"]["lines"] == 30


def test_only_file_names_are_recorded_never_paths(tmp_path: Path) -> None:
    """A criterion that only passes on the machine that produced it is broken."""
    write(tmp_path / "kraken_v2_2026-03-01.jsonl", steady(5))
    report = build_report(sorted(tmp_path.glob("*.jsonl")))
    assert report["source_files"] == ["kraken_v2_2026-03-01.jsonl"]
    assert str(tmp_path) not in json.dumps(report)


def test_an_empty_recording_is_an_error_rather_than_an_empty_report(tmp_path: Path) -> None:
    write(tmp_path / "kraken_v2_2026-03-01.jsonl", [])
    with pytest.raises(ValueError, match="no usable line"):
        build_report(sorted(tmp_path.glob("*.jsonl")))
