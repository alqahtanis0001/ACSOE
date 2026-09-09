"""Spec 27 — the line schema, and the writer.

The schema is not new: `scripts/record.py` has been writing it since Phase 0 and
`tests/fixtures/record_sample.jsonl` is 25 committed lines of it. The engine
supersedes the script and the format stays identical, so the archive is one dataset
rather than two.

`validate_line` exists twice — once in the script, once in `clients/recorder/` —
because the script imports nothing from `src/acsoe/` on purpose: it is the day-one
recorder and must survive the framework being broken. The duplication is only safe if
something asserts the two agree, so this file runs **both** over the same committed
sample. That is a stronger guarantee than sharing the code would give, because it also
proves the committed evidence still validates.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from acsoe.clients.recorder.contracts import (
    LINE_KEYS,
    RECORDER_CHANNEL,
    SCHEMA_VERSION,
    SchemaError,
    build_line,
    validate_line,
)
from acsoe.clients.recorder.writer import JsonlRecorder

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "record_sample.jsonl"


@pytest.fixture(scope="module")
def record_script() -> ModuleType:
    """`scripts/record.py`, imported by path. It is not a package."""
    spec = importlib.util.spec_from_file_location(
        "acsoe_record_script", REPO_ROOT / "scripts" / "record.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_lines() -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in SAMPLE.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# --------------------------------------------------------------------------- #
# The two validators agree
# --------------------------------------------------------------------------- #


def test_the_committed_sample_validates_against_both_implementations(
    record_script: ModuleType,
) -> None:
    lines = sample_lines()
    assert len(lines) == 25
    for line in lines:
        validate_line(line)
        record_script.validate_line(line)


def test_the_two_implementations_agree_on_the_key_set(record_script: ModuleType) -> None:
    assert LINE_KEYS == record_script.LINE_KEYS
    assert SCHEMA_VERSION == record_script.SCHEMA_VERSION
    assert RECORDER_CHANNEL == record_script.RECORDER_CHANNEL


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda line: line.pop("pair"), "missing"),
        (lambda line: line.update(extra=1), "extra"),
        (lambda line: line.update(v=2), "schema version"),
        (lambda line: line.update(kind="unknown"), "unknown kind"),
        (lambda line: line.update(channel=""), "non-empty"),
        (lambda line: line.update(ts_recv=None), "may not be null"),
        (lambda line: line.update(ts_recv="2026-01-01T00:00:00"), "ending 'Z'"),
        (lambda line: line.update(payload=[]), "payload must be an object"),
    ],
)
def test_both_implementations_reject_the_same_malformations(
    record_script: ModuleType, mutate: Any, match: str
) -> None:
    for validator in (validate_line, record_script.validate_line):
        line = sample_lines()[-1]
        mutate(line)
        with pytest.raises(ValueError, match=match):
            validator(line)


def test_a_gap_marker_must_use_the_reserved_channel() -> None:
    line = build_line(
        kind="gap",
        pair=None,
        channel="trade",
        ts_exchange=None,
        ts_recv="2026-01-01T00:00:00.000000Z",
        payload={},
    )
    with pytest.raises(SchemaError, match="_recorder"):
        validate_line(line)


# --------------------------------------------------------------------------- #
# The writer
# --------------------------------------------------------------------------- #


def test_it_appends_and_never_truncates(tmp_path: Path) -> None:
    line = build_line(
        kind="tick",
        pair="BTC/USD",
        channel="trade",
        ts_exchange=None,
        ts_recv="2026-01-01T00:00:00.000000Z",
        payload={"a": 1},
    )
    with JsonlRecorder(tmp_path) as recorder:
        recorder.append(line)
    with JsonlRecorder(tmp_path) as recorder:
        recorder.append(line)

    written = (tmp_path / "kraken_v2_2026-01-01.jsonl").read_text(encoding="utf-8")
    assert len(written.strip().splitlines()) == 2


def test_it_rotates_on_the_lines_own_date_not_the_wall_clock(tmp_path: Path) -> None:
    """A frame received at 23:59:59.9 belongs to that day's file even if the write
    lands a tenth of a second later. Nothing in this package reads a clock."""
    with JsonlRecorder(tmp_path) as recorder:
        for stamp in ("2026-01-01T23:59:59.900000Z", "2026-01-02T00:00:00.100000Z"):
            recorder.append(
                build_line(
                    kind="tick",
                    pair=None,
                    channel="ticker",
                    ts_exchange=None,
                    ts_recv=stamp,
                    payload={},
                )
            )
    assert (tmp_path / "kraken_v2_2026-01-01.jsonl").is_file()
    assert (tmp_path / "kraken_v2_2026-01-02.jsonl").is_file()


def test_a_malformed_line_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    """An append-only recording cannot be cleaned up later, and invariant 11 forbids
    the cleaning pass anyway. So the refusal happens before the bytes hit the file."""
    with JsonlRecorder(tmp_path) as recorder:
        with pytest.raises(SchemaError):
            recorder.append({"v": 1, "kind": "tick"})
        assert recorder.lines_written == 0
    assert list(tmp_path.glob("*.jsonl")) == []


def test_the_payload_is_written_verbatim(tmp_path: Path) -> None:
    payload = {"channel": "book", "data": [{"symbol": "BTC/USD", "bids": [["1.0", "2.0"]]}]}
    with JsonlRecorder(tmp_path) as recorder:
        recorder.append(
            build_line(
                kind="tick",
                pair="BTC/USD",
                channel="book",
                ts_exchange=None,
                ts_recv="2026-01-01T00:00:00.000000Z",
                payload=payload,
            )
        )
    written = json.loads((tmp_path / "kraken_v2_2026-01-01.jsonl").read_text(encoding="utf-8"))
    assert written["payload"] == payload


def test_close_is_idempotent_and_releases_the_handle(tmp_path: Path) -> None:
    """Windows makes an open handle inside a directory about to be removed a
    PermissionError rather than a warning."""
    recorder = JsonlRecorder(tmp_path)
    recorder.__enter__()
    recorder.append(
        build_line(
            kind="session",
            pair=None,
            channel=RECORDER_CHANNEL,
            ts_exchange=None,
            ts_recv="2026-01-01T00:00:00.000000Z",
            payload={"event": "start"},
        )
    )
    recorder.close()
    recorder.close()
    (tmp_path / "kraken_v2_2026-01-01.jsonl").unlink()
