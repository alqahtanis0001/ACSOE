"""Spec 10 — the committed recorder sample validates offline.

The validator under test is imported from `scripts/record.py` itself rather than
reimplemented here. That is the point: the fixture and the writer cannot drift
apart, because a schema change that breaks the fixture breaks this test in the
same run.

`scripts/` is deliberately not a package — `record.py` imports nothing from
`src/acsoe/` so that it can run before the framework exists — so it is loaded by
path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PY = REPO_ROOT / "scripts" / "record.py"
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "record_sample.jsonl"

# Anything whose key name looks like a credential. Invariant 13: a secret never
# enters the repo, and a fixture is in the repo.
SECRETISH = ("key", "secret", "token", "sign", "nonce", "passphrase", "auth", "otp")


def _load_record_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_record_script", RECORD_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


record = _load_record_module()


def _sample_lines() -> list[dict[str, Any]]:
    # `.splitlines()` and the strip below make this CRLF-tolerant on purpose:
    # git for Windows ships core.autocrlf=true, so a fresh clone checks the
    # fixture out with CRLF endings even though the blob is LF.
    raw = SAMPLE.read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _walk_keys(obj: object, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            found.append(f"{path}/{key}")
            found.extend(_walk_keys(value, f"{path}/{key}"))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found.extend(_walk_keys(value, f"{path}[{index}]"))
    return found


# --------------------------------------------------------------------------
# The committed sample
# --------------------------------------------------------------------------


def test_sample_exists_and_is_not_empty() -> None:
    assert SAMPLE.is_file(), f"{SAMPLE} is missing — the Phase 0 gate reads it"
    assert SAMPLE.stat().st_size > 0


def test_every_sample_line_validates() -> None:
    for index, line in enumerate(_sample_lines()):
        record.validate_line(line)  # raises SchemaError on anything malformed
        assert isinstance(line["payload"], dict), index


def test_sample_has_no_blank_lines() -> None:
    raw = SAMPLE.read_text(encoding="utf-8")
    assert raw.endswith("\n"), "a JSONL file terminates its last record"
    assert not raw.rstrip("\n").endswith("\n"), "no trailing blank line"
    assert all(line.strip() for line in raw.splitlines())


def test_sample_exercises_all_three_kinds() -> None:
    """A sample without a gap marker is a defective sample.

    The reconnect path is the one most likely to be broken later and least
    likely to be exercised by an ordinary capture, so the fixture has to carry
    it.
    """
    kinds = {line["kind"] for line in _sample_lines()}
    assert kinds == {"tick", "gap", "session"}


def test_sample_ts_recv_is_monotonic() -> None:
    """Within one recorder run the lines are written in receive order."""
    stamps = [line["ts_recv"] for line in _sample_lines()]
    assert stamps == sorted(stamps)


def test_gap_markers_are_well_formed() -> None:
    gaps = [line for line in _sample_lines() if line["kind"] == "gap"]
    assert gaps, "no gap marker in the sample"
    for gap in gaps:
        assert gap["channel"] == record.RECORDER_CHANNEL
        assert gap["pair"] is None
        payload = gap["payload"]
        assert set(payload) == {
            "reason",
            "disconnected_at",
            "reconnected_at",
            "gap_ms",
            "attempt",
        }
        assert isinstance(payload["gap_ms"], int)
        assert payload["gap_ms"] >= 0
        assert isinstance(payload["attempt"], int)
        assert payload["reason"]
        # The marker is written on reconnect, so gap_ms is a measured interval,
        # never an estimate: it must agree with its own two timestamps.
        started = datetime.fromisoformat(payload["disconnected_at"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(payload["reconnected_at"].replace("Z", "+00:00"))
        assert ended >= started
        assert abs((ended - started).total_seconds() * 1000 - payload["gap_ms"]) < 1.0


def test_session_markers_are_well_formed() -> None:
    sessions = [line for line in _sample_lines() if line["kind"] == "session"]
    assert [s["payload"]["event"] for s in sessions] == ["start", "stop"]
    for marker in sessions:
        assert marker["channel"] == record.RECORDER_CHANNEL
        payload = marker["payload"]
        assert set(payload) == {"event", "url", "subscriptions"}
        assert isinstance(payload["subscriptions"], list)
        assert payload["subscriptions"]


def test_sample_carries_real_book_data() -> None:
    """The fixture must be a real capture, not a hand-written stub."""
    channels = {line["channel"] for line in _sample_lines() if line["kind"] == "tick"}
    assert "book" in channels
    snapshots = [
        line
        for line in _sample_lines()
        if line["channel"] == "book" and line["payload"].get("type") == "snapshot"
    ]
    assert snapshots
    data = snapshots[0]["payload"]["data"][0]
    assert data["bids"] and data["asks"]


def test_sample_contains_no_secret_shaped_key() -> None:
    """Invariant 13. The proof is a check, not a promise."""
    offenders = [
        path
        for line in _sample_lines()
        for path in _walk_keys(line)
        if any(token in path.rsplit("/", 1)[-1].lower() for token in SECRETISH)
    ]
    assert not offenders, offenders


def test_sample_connection_id_is_redacted() -> None:
    """The one field in a public capture that identifies this machine's session."""
    for line in _sample_lines():
        payload = line["payload"]
        if payload.get("channel") != "status":
            continue
        for item in payload.get("data", []):
            assert item.get("connection_id", 0) == 0


# --------------------------------------------------------------------------
# validate_line rejects, which is what "validate on write" means
# --------------------------------------------------------------------------


def _good_line() -> dict[str, Any]:
    return record.build_line(
        kind="tick",
        pair="BTC/USD",
        channel="book",
        ts_exchange="2026-09-08T16:05:32.019622Z",
        ts_recv="2026-09-08T16:05:32.119622Z",
        payload={"channel": "book", "data": []},
    )


def test_a_good_line_validates() -> None:
    record.validate_line(_good_line())


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda line: line.pop("pair"), "missing key"),
        (lambda line: line.update(extra=1), "unknown key"),
        (lambda line: line.update(v=2), "unknown schema version"),
        (lambda line: line.update(kind="snapshot"), "unknown kind"),
        (lambda line: line.update(pair=123), "pair not a string"),
        (lambda line: line.update(channel=""), "empty channel"),
        (lambda line: line.update(ts_recv=None), "null ts_recv"),
        (lambda line: line.update(ts_recv="2026-09-08T16:05:32+00:00"), "ts_recv not Z"),
        (lambda line: line.update(ts_exchange="2026-09-08 16:05:32"), "ts_exchange not Z"),
        (lambda line: line.update(payload=[]), "payload not an object"),
        (lambda line: line.update(payload=None), "payload null"),
    ],
)
def test_validate_line_rejects(mutate: Any, why: str) -> None:
    line = _good_line()
    mutate(line)
    with pytest.raises(record.SchemaError):
        record.validate_line(line)


def test_a_marker_must_use_the_reserved_channel() -> None:
    """Otherwise a gap could hide behind a plausible-looking channel name."""
    line = record.build_line(
        kind="gap",
        pair=None,
        channel="book",
        ts_exchange=None,
        ts_recv="2026-09-08T16:05:32.119622Z",
        payload={"reason": "x"},
    )
    with pytest.raises(record.SchemaError):
        record.validate_line(line)


# --------------------------------------------------------------------------
# Field extraction
# --------------------------------------------------------------------------


def test_extract_pair_single_symbol() -> None:
    assert record.extract_pair({"data": [{"symbol": "BTC/USD"}]}) == "BTC/USD"


def test_extract_pair_is_null_when_a_frame_covers_two_pairs() -> None:
    """Null rather than a guess: a two-symbol frame has no single pair."""
    payload = {"data": [{"symbol": "BTC/USD"}, {"symbol": "ETH/USD"}]}
    assert record.extract_pair(payload) is None


def test_extract_pair_reads_a_subscribe_ack() -> None:
    payload = {"method": "subscribe", "result": {"symbol": "ETH/USD"}, "success": True}
    assert record.extract_pair(payload) == "ETH/USD"


def test_extract_channel_falls_back_to_the_ack_marker() -> None:
    assert record.extract_channel({"channel": "book"}) == "book"
    assert record.extract_channel({"method": "subscribe"}) == record.ACK_CHANNEL
    assert record.extract_channel({}) == "_unknown"


def test_missing_exchange_timestamp_is_null_not_the_receive_time() -> None:
    """Filling it in would silently record zero exchange-to-recorder latency."""
    assert record.extract_ts_exchange({"channel": "heartbeat"}) is None
    assert record.extract_ts_exchange({"data": [{"timestamp": "2026-01-01T00:00:00.0Z"}]}) == (
        "2026-01-01T00:00:00.0Z"
    )


# --------------------------------------------------------------------------
# The writer: append-only, daily rotation
# --------------------------------------------------------------------------


def test_writer_rotates_on_the_utc_date(tmp_path: Path) -> None:
    with record.JsonlWriter(tmp_path) as writer:
        for stamp in (
            "2026-09-08T23:59:59.900000Z",
            "2026-09-09T00:00:00.100000Z",
            "2026-09-09T00:00:01.100000Z",
        ):
            writer.write(
                record.build_line(
                    kind="tick",
                    pair="BTC/USD",
                    channel="book",
                    ts_exchange=None,
                    ts_recv=stamp,
                    payload={"channel": "book"},
                )
            )
    assert writer.path_for("2026-09-08").read_text(encoding="utf-8").count("\n") == 1
    assert writer.path_for("2026-09-09").read_text(encoding="utf-8").count("\n") == 2


def test_writer_appends_and_never_truncates(tmp_path: Path) -> None:
    """Invariant 11: a recording is append-only. Reopening must not lose a line."""
    line = record.build_line(
        kind="tick",
        pair="BTC/USD",
        channel="book",
        ts_exchange=None,
        ts_recv="2026-09-08T00:00:00.000000Z",
        payload={"channel": "book"},
    )
    for _ in range(2):
        with record.JsonlWriter(tmp_path) as writer:
            writer.write(line)
    assert writer.path_for("2026-09-08").read_text(encoding="utf-8").count("\n") == 2


def test_writer_refuses_to_write_a_malformed_line(tmp_path: Path) -> None:
    """Validation happens before the bytes hit the file, because an append-only
    recording cannot be corrected afterwards."""
    with record.JsonlWriter(tmp_path) as writer:
        with pytest.raises(record.SchemaError):
            writer.write({"v": 1, "kind": "tick"})
    assert not list(tmp_path.glob("*.jsonl"))


def test_recorder_holds_no_credentials() -> None:
    """The recorder subscribes only to public channels and never authenticates."""
    source = RECORD_PY.read_text(encoding="utf-8")
    for forbidden in ("KRAKEN_API_KEY", "KRAKEN_API_SECRET", "GetWebSocketsToken", "api_sign"):
        assert forbidden not in source


def test_record_script_imports_nothing_from_the_package() -> None:
    """Spec 10: standalone on purpose, so it runs before the framework exists
    and keeps running after engines 1 and 2 supersede it."""
    source = RECORD_PY.read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "acsoe" not in stripped, stripped


def test_utc_now_iso_shape() -> None:
    stamp = record.utc_now_iso()
    assert stamp.endswith("Z")
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == datetime.now(UTC).utcoffset()
