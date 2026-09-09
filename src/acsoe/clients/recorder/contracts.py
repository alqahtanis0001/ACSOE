"""The raw recording line schema.

**This schema is not new and must not drift.** `scripts/record.py` has been writing
it since Phase 0, `tests/fixtures/record_sample.jsonl` is 25 committed lines of it,
and the Phase 0 criterion `record_sample_valid` validates that sample against it. The
engine supersedes the script; the format stays identical, so the archive is one
dataset rather than two.

One JSON object per line, exactly these seven keys:

===============  ========  ====================================================
``v``            int       always 1
``kind``         str       ``"tick"`` | ``"gap"`` | ``"session"``
``pair``         str|None  Kraken v2 symbol; null when the frame names no single one
``channel``      str       Kraken's channel name, or ``"_recorder"`` for a marker
``ts_exchange``  str|None  ISO-8601 UTC ending ``"Z"``, copied verbatim
``ts_recv``      str       ISO-8601 UTC ending ``"Z"``, when the frame was read
``payload``      dict      the Kraken frame verbatim, or the marker's own object
===============  ========  ====================================================

Recordings are immutable — invariant 11. Nothing here edits, backfills, interpolates
or reorders a line, and a break in the stream is written down as a ``gap`` marker
rather than silently healed. Validation happens **on write**, because a line that is
wrong when written is wrong forever: an append-only file cannot be cleaned up later,
and invariant 11 forbids the cleaning pass anyway.
"""

from __future__ import annotations

from typing import Any, Final

__all__ = [
    "ACK_CHANNEL",
    "LINE_KEYS",
    "LINE_KINDS",
    "RECORDER_CHANNEL",
    "SCHEMA_VERSION",
    "SchemaError",
    "build_line",
    "validate_line",
]

SCHEMA_VERSION: Final = 1

#: ``channel`` for lines the recorder wrote about itself rather than about the
#: market. Reserved: no Kraken channel may ever be called this.
RECORDER_CHANNEL: Final = "_recorder"

#: ``channel`` for a Kraken method response — those frames carry ``method``.
ACK_CHANNEL: Final = "_ack"

LINE_KEYS: Final = frozenset({"v", "kind", "pair", "channel", "ts_exchange", "ts_recv", "payload"})
LINE_KINDS: Final = frozenset({"tick", "gap", "session"})


class SchemaError(ValueError):
    """A line failed validation on write, and is therefore not written.

    Never suppressed. A malformed line in an append-only recording is unfixable
    later, so the recorder refuses to write it rather than writing it and hoping.
    """


def build_line(
    *,
    kind: str,
    pair: str | None,
    channel: str,
    ts_exchange: str | None,
    ts_recv: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Assemble one line. Key order matches ``scripts/record.py`` exactly."""
    return {
        "v": SCHEMA_VERSION,
        "kind": kind,
        "pair": pair,
        "channel": channel,
        "ts_exchange": ts_exchange,
        "ts_recv": ts_recv,
        "payload": payload,
    }


def validate_line(line: dict[str, Any]) -> None:
    """Raise :class:`SchemaError` on anything malformed.

    Kept deliberately identical to ``scripts/record.py``'s ``validate_line``, field
    for field and message for message. The two implementations are separate because
    that script imports nothing from ``src/acsoe/`` on purpose — it is the day-one
    recorder and must survive the framework being broken — and
    ``tests/clients/recorder/test_schema.py`` asserts they agree by running both over
    the same committed sample.
    """
    keys = set(line)
    if keys != LINE_KEYS:
        missing = sorted(LINE_KEYS - keys)
        extra = sorted(keys - LINE_KEYS)
        raise SchemaError(f"line keys wrong: missing={missing} extra={extra}")
    if line["v"] != SCHEMA_VERSION:
        raise SchemaError(f"unknown schema version {line['v']!r}")
    if line["kind"] not in LINE_KINDS:
        raise SchemaError(f"unknown kind {line['kind']!r}")
    if line["pair"] is not None and not isinstance(line["pair"], str):
        raise SchemaError(f"pair must be a string or null, got {type(line['pair']).__name__}")
    if not isinstance(line["channel"], str) or not line["channel"]:
        raise SchemaError("channel must be a non-empty string")
    if line["kind"] in ("gap", "session") and line["channel"] != RECORDER_CHANNEL:
        raise SchemaError(f"a {line['kind']} marker must use channel {RECORDER_CHANNEL!r}")
    for field in ("ts_exchange", "ts_recv"):
        value = line[field]
        if field == "ts_recv" and value is None:
            raise SchemaError("ts_recv may not be null")
        if value is None:
            continue
        if not isinstance(value, str) or not value.endswith("Z"):
            raise SchemaError(f"{field} must be an ISO-8601 UTC string ending 'Z', got {value!r}")
    if not isinstance(line["payload"], dict):
        raise SchemaError(f"payload must be an object, got {type(line['payload']).__name__}")
