"""The recording digest: what was captured, and every break in it.

`data/` is gitignored and a phase criterion may never depend on anything inside it,
so the committed evidence for "the recorder ran continuously" is a small digest —
`tests/fixtures/recording_report.json` — produced from a real recording and checked
in. The real recording itself is verified by `--live`, which is opt-in.

**The digest's job is to make a silent outage impossible to mistake for a quiet
market.** So it does not report an uptime percentage or a gap count. It reports a
`span`, a list of `segments` and a list of `gaps`, and the segments and the gaps
**tile the span exactly**: every microsecond between the first frame and the last is
claimed either as recorded or as a named break. A hole in the tiling is a break
nobody accounted for, and there is nowhere for one to hide.

Two kinds of break exist and both are gaps here:

* an **explicit** one — a ``gap`` marker the recorder wrote on reconnect, carrying the
  disconnect reason; and
* an **implicit** one — a stretch with no frame at all, longer than the silence
  threshold. That is what a recorder that was not running leaves behind, and it
  writes no marker precisely because it was not there to write one.

A gap is marked, never interpolated away, and this module never invents a frame.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_SILENCE_THRESHOLD_S",
    "Break",
    "ScanResult",
    "build_report",
    "iter_events",
    "scan_events",
]

#: A stretch with no frame longer than this is an unrecorded silence.
#:
#: Chosen against the feed rather than as a round number: Kraken v2 sends a heartbeat
#: on an idle connection, and `scripts/record.py` runs a 20-second keepalive ping with
#: a 20-second pong deadline, so a live connection that has gone 60 seconds without
#: delivering anything at all has already failed its own keepalive. Anything longer is
#: not a quiet market, it is an absent recorder.
DEFAULT_SILENCE_THRESHOLD_S: float = 60.0

_TS_KEY = b'"ts_recv"'
_KIND_KEY = b'"kind"'
_MICROS = 1_000_000


def _parse_iso(text: str) -> int:
    """ISO-8601 UTC to microseconds since the epoch."""
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.astimezone(UTC).timestamp() * _MICROS)


def _iso(micros: int) -> str:
    return (
        datetime.fromtimestamp(micros / _MICROS, tz=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class Break:
    """One accounted-for break: when it started, when it ended, and why."""

    start: int
    end: int
    cause: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "start_iso": _iso(self.start),
            "end_iso": _iso(self.end),
            "gap_ms": (self.end - self.start) // 1000,
            "cause": self.cause,
        }


@dataclass
class ScanResult:
    """Everything one pass over the recording found."""

    first: int | None = None
    last: int | None = None
    lines: int = 0
    ticks: int = 0
    gap_markers: int = 0
    session_markers: int = 0
    malformed: int = 0
    breaks: list[Break] | None = None
    segments: list[tuple[int, int]] | None = None


def _string_field(raw: bytes, key: bytes) -> bytes | None:
    """The value of a top-level string field, read without parsing the object.

    A recording is measured in gigabytes and every line carries a full Kraken frame,
    most of it order-book levels this module never looks at. Parsing all of it to read
    two fields costs minutes per pass.

    It steps past the key, the colon, any whitespace and the opening quote rather than
    matching a fixed ``"key":"``. ``orjson`` writes the compact form and the recorder
    uses ``orjson``, but a recording that has been through any other writer is still a
    valid recording, and a scanner that silently found *nothing* in one would report
    "no usable line" rather than anything a reader could act on.

    Matching the **key** rather than the value is what keeps this honest: a scan for
    the bare token ``"gap"`` would classify any frame that merely contained that word
    as a break. The first occurrence is the right one, because the recorder writes the
    seven schema keys before ``payload``, so a same-named key nested inside a Kraken
    frame can never be reached first.
    """
    index = raw.find(key)
    if index < 0:
        return None
    start = index + len(key)
    while start < len(raw) and raw[start : start + 1] in (b":", b" ", b"\t"):
        start += 1
    if raw[start : start + 1] != b'"':
        return None
    start += 1
    end = raw.find(b'"', start)
    if end < 0:
        return None
    return raw[start:end]


def _extract_ts(raw: bytes) -> int | None:
    """``ts_recv`` as microseconds since the epoch, or None when it is unreadable."""
    value = _string_field(raw, _TS_KEY)
    if value is None:
        return None
    try:
        return _parse_iso(value.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return None


def iter_events(paths: Sequence[Path]) -> Iterator[tuple[int, bytes]]:
    """Yield ``(ts_recv_micros, raw_line)`` in file order, skipping unreadable lines.

    Files are read in sorted order, which is date order given the writer's naming. A
    partial final line — the process was killed mid-write — is skipped rather than
    repaired, per invariant 11.
    """
    for path in sorted(paths):
        with path.open("rb") as handle:
            for raw in handle:
                stripped = raw.strip()
                if not stripped:
                    continue
                ts = _extract_ts(stripped)
                if ts is None:
                    continue
                yield ts, stripped


def scan_events(
    events: Iterable[tuple[int, bytes]],
    *,
    silence_threshold_s: float = DEFAULT_SILENCE_THRESHOLD_S,
) -> ScanResult:
    """One streaming pass, producing the segments and the breaks.

    Memory is bounded by the number of *breaks*, not by the number of lines: a
    recording is far too large to hold, and holding it would buy nothing.
    """
    threshold = int(silence_threshold_s * _MICROS)
    result = ScanResult(breaks=[], segments=[])
    breaks: list[Break] = result.breaks or []
    segments: list[tuple[int, int]] = result.segments or []

    cursor: int | None = None
    previous: int | None = None

    for ts, raw in events:
        result.lines += 1
        if result.first is None:
            result.first = ts
            cursor = ts
        kind = _string_field(raw, _KIND_KEY)
        if kind == b"gap":
            result.gap_markers += 1
            explicit = _explicit_break(raw, ts)
            if explicit is not None and cursor is not None:
                start = max(explicit.start, cursor)
                end = max(explicit.end, start)
                if end > start:
                    segments.append((cursor, start))
                    breaks.append(Break(start=start, end=end, cause=explicit.cause))
                    cursor = end
        elif kind == b"session":
            result.session_markers += 1
        else:
            result.ticks += 1

        if (
            previous is not None
            and cursor is not None
            and ts - previous > threshold
            and previous >= cursor
        ):
            # Nothing arrived for longer than a live connection can stay silent. No
            # marker exists because the process that would have written one was not
            # running.
            seconds = (ts - previous) / _MICROS
            segments.append((cursor, previous))
            breaks.append(
                Break(
                    start=previous,
                    end=ts,
                    cause=(
                        f"unrecorded silence: {seconds:.0f}s with no frame, longer than the "
                        f"{silence_threshold_s:.0f}s a live connection can stay quiet — the "
                        "recorder was not running"
                    ),
                )
            )
            cursor = ts

        previous = max(ts, previous) if previous is not None else ts
        result.last = previous

    if cursor is not None and result.last is not None and result.last > cursor:
        segments.append((cursor, result.last))
    result.segments = [s for s in segments if s[1] > s[0]]
    result.breaks = breaks
    return result


def _explicit_break(raw: bytes, ts: int) -> Break | None:
    """Read a ``gap`` marker's own account of the break it is recording."""
    try:
        line = json.loads(raw)
    except ValueError:
        return None
    payload = line.get("payload")
    if not isinstance(payload, dict):
        return None
    started = payload.get("disconnected_at")
    ended = payload.get("reconnected_at")
    reason = str(payload.get("reason") or "unknown disconnect")
    try:
        start = _parse_iso(str(started)) if started else ts
        end = _parse_iso(str(ended)) if ended else ts
    except ValueError:
        return None
    return Break(start=start, end=end, cause=f"disconnect: {reason}")


def build_report(
    paths: Sequence[Path],
    *,
    silence_threshold_s: float = DEFAULT_SILENCE_THRESHOLD_S,
) -> dict[str, Any]:
    """The committed digest, as `scripts/verify.py` reads it.

    Every moment is microseconds since the epoch, with an ISO-8601 twin beside it for
    a human. Only file **names** are recorded, never paths: a criterion that only
    passes on the machine that produced it is a broken criterion.
    """
    result = scan_events(iter_events(paths), silence_threshold_s=silence_threshold_s)
    if result.first is None or result.last is None:
        raise ValueError("no usable line found in the recording")

    segments = [
        {"start": start, "end": end, "start_iso": _iso(start), "end_iso": _iso(end)}
        for start, end in (result.segments or [])
    ]
    gaps = [item.as_dict() for item in (result.breaks or [])]
    recorded = sum(end - start for start, end in (result.segments or []))
    missing = sum(item.end - item.start for item in (result.breaks or []))

    return {
        "schema_version": 1,
        "source_files": sorted(path.name for path in paths),
        "silence_threshold_s": silence_threshold_s,
        "span": {
            "start": result.first,
            "end": result.last,
            "start_iso": _iso(result.first),
            "end_iso": _iso(result.last),
            "seconds": (result.last - result.first) / _MICROS,
            "hours": (result.last - result.first) / _MICROS / 3600.0,
        },
        "segments": segments,
        "gaps": gaps,
        "totals": {
            "lines": result.lines,
            "ticks": result.ticks,
            "gap_markers": result.gap_markers,
            "session_markers": result.session_markers,
            "recorded_seconds": recorded / _MICROS,
            "missing_seconds": missing / _MICROS,
        },
    }
