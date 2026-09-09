"""Append-only raw JSONL recording: the archive engine 2 writes.

The line schema here is the one `scripts/record.py` has been writing since Phase 0
and must not drift — `tests/fixtures/record_sample.jsonl` is validated against it by
a Phase 0 criterion, and the engine supersedes the script without changing the format
so the archive stays one dataset rather than two.
"""

from acsoe.clients.recorder.contracts import (
    ACK_CHANNEL,
    LINE_KEYS,
    LINE_KINDS,
    RECORDER_CHANNEL,
    SCHEMA_VERSION,
    SchemaError,
    build_line,
    validate_line,
)
from acsoe.clients.recorder.report import build_report, scan_events
from acsoe.clients.recorder.writer import JsonlRecorder

__all__ = [
    "ACK_CHANNEL",
    "LINE_KEYS",
    "LINE_KINDS",
    "RECORDER_CHANNEL",
    "SCHEMA_VERSION",
    "JsonlRecorder",
    "SchemaError",
    "build_line",
    "build_report",
    "scan_events",
    "validate_line",
]
