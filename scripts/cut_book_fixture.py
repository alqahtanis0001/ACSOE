#!/usr/bin/env python
"""Cut a committed order-book fixture out of the live archive. Spec 86, for spec 96.

    python scripts/cut_book_fixture.py \\
        --pairs BTC/USD XRP/USD \\
        --from 2026-09-15T04:00:00Z --to 2026-09-15T04:10:00Z \\
        --out tests/fixtures/book_sample.jsonl --write

Engine 9 `order_book` walks a book to estimate slippage, and the criterion that checks
it needs a **real** book — one thin, one deep — rather than a hand-written ladder that
agrees with whatever the walk does. This script takes one out of `data/raw/`.

**It chooses nothing.** Not the pairs, not the window, not where the result goes. C
owns `tests/fixtures/` and picks all three; this is the mechanism, and keeping the
judgement out of it is what stops the fixture being A's opinion of a book.

## What it writes

Line 1 is a **header object** naming the source files, the window, the pairs, the
per-pair counts and a sha256 of the body. It is not a recorded line and does not
validate against `clients/recorder/contracts.py`; it carries `"_fixture"` so a reader
can tell in one key. Every line after it is a recorded `book` frame **byte-for-byte as
recorded** — the original bytes are copied, never re-serialised, because a
re-serialised line is this script's idea of the frame rather than the exchange's, and
the checksum inside a Kraken book frame is computed over what the exchange sent.

Written as **bytes**. The output lands in `tests/fixtures/`, which `.gitattributes`
marks `-text` precisely so no line-ending conversion happens near an evidence fixture:
a text-mode round trip on Windows would rewrite every LF as CRLF and change the
committed bytes.

## What it refuses, and why each refusal exists

A fixture that is quietly wrong is worse than no fixture, because the criterion that
reads it then passes for the wrong reason. So this refuses rather than cutting:

1. **An output path inside the source directory.** Invariant 11: the recording is
   append-only and nothing writes into it.
2. **A window with a recorded `gap` marker intersecting it.** The acceptance criterion
   of spec 86. A reconnect in the middle of a book stream means the fixture spans a
   resubscribe: the sequence of updates is not continuous, the checksums do not chain,
   and a slippage walk over it is a walk over two different books stitched together.
   The test is on the gap's **interval**, not on the marker's timestamp. A gap marker
   is written at *reconnect* — so a break that started inside the window and ended
   after it has its marker outside the window entirely, and a timestamp test would
   miss exactly the case that truncates the fixture's tail.
3. **A window the archive does not cover at both ends.** That is the open gap the
   marker cannot describe: if the recorder was not running, there is no marker saying
   so, and silence reads identically to a quiet market. Unrecorded silence is a gap
   too — the same point `scripts/recording_report.py` makes by reporting a tiling
   rather than a gap count.
4. **More than one source file contributing to the window.** Two recorders ran
   concurrently from 2026-09-09T13:19 and part of the archive is doubled. A fixture
   built from both holds each frame twice, which a book walk reads as twice the depth.
   Pass `--prefix` to name one.
5. **A named pair with no book frame in the window.** An empty pair in a two-pair
   fixture is a criterion that silently tests one.

## The prefilter, and why it is shaped the way it is

The archive is tens of gigabytes and the window is minutes, so most lines are skipped
without parsing. `code-standards.md`: *a cheap prefilter is a second, weaker parser,
and it must be strictly broader than the check it fronts* — A shipped two that were
narrower in Phase 4, one of which would have classified the whole recording as
unrecorded.

:func:`might_be_wanted` is broader by construction, and the argument is short enough to
check. A line this script wants is one whose `channel` is `"book"` or whose `kind` is
`"gap"`. Any JSON encoding of those strings either contains the literal bytes ``book``
or ``gap``, or escapes at least one character as ``\\u``. So a line containing none of
the three cannot be one we want. It deliberately does **not** match on separators,
quoting or key order, which is what the Phase 4 prefilters got wrong.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_DIR = Path("data") / "raw"

#: The one channel this cutter is interested in.
BOOK_CHANNEL = "book"

#: `kind` of a recorded break. `clients/recorder/contracts.py`.
GAP_KIND = "gap"

#: Bytes that a line we want must contain at least one of. See the module docstring
#: for why this is strictly broader than the parse it fronts.
_WANTED_MARKERS = (b"book", b"gap", b"\\u")

#: The key that tells a reader the first line is the header and not a recorded frame.
FIXTURE_MARKER = "_fixture"


class RefusalError(Exception):
    """The cut cannot be made honestly, so it is not made.

    Its own type rather than `SystemExit`, so a test can assert on the message. Every
    refusal names the thing it found — a gap's interval, the uncovered end of the
    window, the pair with nothing in it — because "refused" on its own sends the
    operator back to the archive with no idea what to change.
    """


# --------------------------------------------------------------------------- #
# Time
# --------------------------------------------------------------------------- #


def parse_iso(text: str) -> datetime:
    """An aware UTC datetime from an ISO-8601 string, ``Z`` or offset.

    A naive value is **refused** rather than assumed to be UTC. Every timestamp in the
    archive carries ``Z``, so a naive one on the command line is an operator mistake,
    and reading it as local time would shift the window by the machine's offset — by a
    different amount in summer, which is the kind of error that reproduces in one
    season and not the other.
    """
    moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise RefusalError(
            f"{text!r} has no timezone. Give the window in UTC, ending in Z — a naive "
            "timestamp would be read as local time and silently shift the window."
        )
    return moment.astimezone(UTC)


def line_moment(record: dict[str, Any]) -> datetime | None:
    """A line's ``ts_recv`` as an aware datetime, or None if it is unusable.

    None rather than a substituted time: a line whose receive time cannot be read is
    not a line at a guessed moment, and the caller treats it as not being in any
    window rather than as being in this one.
    """
    raw = record.get("ts_recv")
    if not isinstance(raw, str):
        return None
    try:
        return parse_iso(raw)
    except (ValueError, RefusalError):
        return None


# --------------------------------------------------------------------------- #
# The prefilter
# --------------------------------------------------------------------------- #


def might_be_wanted(raw: bytes) -> bool:
    """Could this line be a book frame or a gap marker? Deliberately over-inclusive.

    Strictly broader than the parse it fronts, which is the whole requirement. A line
    whose parsed ``channel`` is ``"book"`` contains the bytes ``book`` unless the
    encoder escaped a character, in which case it contains ``\\u``; the same holds for
    ``gap``. So a line matching none of the three markers cannot be one we want, and
    the skip is safe. It matches no separator, no quoting and no key order — the two
    prefilters A got wrong in Phase 4 both did.
    """
    return any(marker in raw for marker in _WANTED_MARKERS)


# --------------------------------------------------------------------------- #
# Gaps
# --------------------------------------------------------------------------- #


def gap_interval(record: dict[str, Any]) -> tuple[datetime, datetime] | None:
    """The span a gap marker covers, or None when the line does not say.

    **Two shapes of gap marker are in the archive and they are handled separately
    rather than being conflated.** `scripts/record.py` writes ``disconnected_at`` and
    ``reconnected_at``; engine 2 writes `ws.py`'s own dict, which uses ``started_at``
    and ``ended_at``. A marker carrying neither is not a marker with a zero-length
    span — it is a marker whose span this script does not know, and the caller falls
    back to the line's own ``ts_recv`` as a point rather than pretending to know more.
    """
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return None
    for start_key, end_key in (("disconnected_at", "reconnected_at"), ("started_at", "ended_at")):
        start, end = payload.get(start_key), payload.get(end_key)
        if isinstance(start, str) and isinstance(end, str):
            try:
                return parse_iso(start), parse_iso(end)
            except (ValueError, RefusalError):
                return None
    return None


def intersects(span: tuple[datetime, datetime], window: tuple[datetime, datetime]) -> bool:
    """Do two half-open intervals overlap at all?

    A gap that merely touches the window's edge — ends exactly at ``from``, or starts
    exactly at ``to`` — does not intersect it, because the window is ``[from, to)`` and
    the frames inside it are all on one side of the break.
    """
    (start, end), (window_from, window_to) = span, window
    return start < window_to and end > window_from


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def file_date(path: Path) -> str | None:
    """The UTC date in a recorder filename, or None when the name does not carry one.

    `clients/recorder/writer.py` rotates on the line's own ``ts_recv[:10]``, so the
    date in the name is exactly the dates of the lines inside. That makes skipping a
    file by name equivalent to skipping its lines by timestamp, not narrower than it —
    **and a name that does not parse is scanned rather than skipped**, which is what
    keeps the equivalence from becoming an assumption about every file in the
    directory.
    """
    stem = path.stem
    if len(stem) < 10:
        return None
    candidate = stem[-10:]
    try:
        datetime.strptime(candidate, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None
    return candidate


def dates_in(window: tuple[datetime, datetime]) -> set[str]:
    """Every UTC calendar date the window touches, inclusive at both ends."""
    window_from, window_to = window
    dates: set[str] = set()
    day = window_from.date()
    last = window_to.date()
    while day <= last:
        dates.add(day.isoformat())
        day += timedelta(days=1)
    return dates


def candidate_files(
    source_dir: Path, window: tuple[datetime, datetime], prefix: str | None
) -> list[Path]:
    """Every archive file that could hold a line inside the window, sorted by name."""
    if not source_dir.is_dir():
        raise RefusalError(f"{source_dir} is not a directory, so there is nothing to cut from")
    wanted_dates = dates_in(window)
    chosen: list[Path] = []
    for path in sorted(source_dir.glob("*.jsonl")):
        if prefix is not None and not path.name.startswith(prefix):
            continue
        date = file_date(path)
        if date is not None and date not in wanted_dates:
            continue
        chosen.append(path)
    if not chosen:
        raise RefusalError(
            f"no archive file in {source_dir} covers {wanted_dates}"
            + (f" with prefix {prefix!r}" if prefix else "")
        )
    return chosen


def iter_lines(path: Path) -> Iterator[bytes]:
    """Every line of one archive file, as raw bytes, read-only.

    Opened ``rb`` and never written to. The recorder may be appending to this very
    file while this runs — which is fine, and is why the script takes a closed window
    rather than "everything so far".
    """
    with path.open("rb") as handle:
        for raw in handle:
            stripped = raw.rstrip(b"\r\n")
            if stripped:
                yield stripped


def first_and_last_moments(path: Path) -> tuple[datetime | None, datetime | None]:
    """The receive times of the first and last usable lines in one file.

    Used for the coverage check only. Parsed rather than taken from the filename,
    because the filename says which *date* the file holds and coverage is a question
    about the ends of the window down to the second.
    """
    first: datetime | None = None
    last: datetime | None = None
    for raw in iter_lines(path):
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        moment = line_moment(record)
        if moment is None:
            continue
        if first is None:
            first = moment
        last = moment
    return first, last


# --------------------------------------------------------------------------- #
# The cut
# --------------------------------------------------------------------------- #


class Cut:
    """What one pass over the archive found. Nothing here writes."""

    def __init__(self) -> None:
        self.body: list[bytes] = []
        self.per_pair: dict[str, dict[str, int]] = {}
        self.contributing: list[str] = []
        self.gaps: list[dict[str, Any]] = []
        self.lines_scanned = 0
        self.lines_parsed = 0

    def note(self, pair: str, frame_type: str) -> None:
        counts = self.per_pair.setdefault(pair, {})
        counts[frame_type] = counts.get(frame_type, 0) + 1

    def total(self) -> int:
        return len(self.body)


def collect(
    paths: Sequence[Path], *, pairs: Sequence[str], window: tuple[datetime, datetime]
) -> Cut:
    """One read-only pass. Book frames for the named pairs, and every gap it meets."""
    wanted = set(pairs)
    cut = Cut()
    for path in paths:
        contributed = False
        for raw in iter_lines(path):
            cut.lines_scanned += 1
            if not might_be_wanted(raw):
                continue
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            cut.lines_parsed += 1
            moment = line_moment(record)
            if moment is None:
                continue

            if record.get("kind") == GAP_KIND:
                span = gap_interval(record) or (moment, moment)
                if intersects(span, window):
                    cut.gaps.append(
                        {
                            "file": path.name,
                            "started_at": span[0].isoformat().replace("+00:00", "Z"),
                            "ended_at": span[1].isoformat().replace("+00:00", "Z"),
                            "payload": record.get("payload"),
                            "span_known": gap_interval(record) is not None,
                        }
                    )
                continue

            if record.get("channel") != BOOK_CHANNEL:
                continue
            pair = record.get("pair")
            if not isinstance(pair, str) or pair not in wanted:
                continue
            if not (window[0] <= moment < window[1]):
                continue
            # The ORIGINAL bytes, not a re-serialisation. A Kraken book frame carries
            # a checksum over what the exchange sent, and a round trip through this
            # process's JSON encoder would change the bytes it is computed over.
            cut.body.append(raw)
            payload = record.get("payload")
            frame_type = payload.get("type") if isinstance(payload, dict) else None
            cut.note(pair, str(frame_type) if isinstance(frame_type, str) else "unknown")
            contributed = True
        if contributed:
            cut.contributing.append(path.name)
    return cut


def check(
    cut: Cut,
    paths: Sequence[Path],
    *,
    pairs: Sequence[str],
    window: tuple[datetime, datetime],
) -> None:
    """Every refusal, in the order that makes the message most useful."""
    if cut.gaps:
        found = cut.gaps[0]
        known = "" if found["span_known"] else " (span unknown; the marker's own time was used)"
        raise RefusalError(
            f"a recorded gap intersects the window: {found['started_at']} to "
            f"{found['ended_at']} in {found['file']}{known}. "
            f"{len(cut.gaps)} gap marker(s) intersect it in total. A fixture cut across "
            "a reconnect is two different books stitched together — the update sequence "
            "is not continuous and the Kraken checksums do not chain. Choose a window "
            "that does not span it."
        )

    covered_from: datetime | None = None
    covered_to: datetime | None = None
    for path in paths:
        first, last = first_and_last_moments(path)
        if first is not None and (covered_from is None or first < covered_from):
            covered_from = first
        if last is not None and (covered_to is None or last > covered_to):
            covered_to = last
    if covered_from is None or covered_to is None:
        raise RefusalError("the archive files hold no readable timestamps, so coverage is unknown")
    if covered_from > window[0] or covered_to < window[1]:
        raise RefusalError(
            f"the archive covers {covered_from.isoformat()} to {covered_to.isoformat()}, "
            f"which does not contain the whole window {window[0].isoformat()} to "
            f"{window[1].isoformat()}. An uncovered end is a gap with no marker — the "
            "recorder was not running, so nothing wrote one down, and silence there is "
            "indistinguishable from a quiet market."
        )

    if len(cut.contributing) > 1:
        raise RefusalError(
            "more than one archive file contributed to this window: "
            f"{', '.join(cut.contributing)}. Two recorders ran concurrently from "
            "2026-09-09T13:19 and part of the archive is doubled; a fixture built from "
            "both holds every frame twice, which a book walk reads as twice the depth. "
            "Pass --prefix to name one."
        )

    empty = [pair for pair in pairs if pair not in cut.per_pair]
    if empty:
        raise RefusalError(
            f"no book frame for {', '.join(empty)} in the window. A pair with nothing in "
            "it makes a two-pair fixture silently test one."
        )


def header(
    cut: Cut, *, pairs: Sequence[str], window: tuple[datetime, datetime], body_sha: str
) -> dict[str, Any]:
    return {
        FIXTURE_MARKER: "book_frames",
        "schema": 1,
        "cut_by": "scripts/cut_book_fixture.py",
        "window": {
            "from": window[0].isoformat().replace("+00:00", "Z"),
            "to": window[1].isoformat().replace("+00:00", "Z"),
            "bounds": "[from, to)",
        },
        "pairs": list(pairs),
        "source_files": list(cut.contributing),
        "lines": {
            "total": cut.total(),
            "scanned": cut.lines_scanned,
            "per_pair": {pair: dict(sorted(counts.items())) for pair, counts in
                         sorted(cut.per_pair.items())},
        },
        "sha256_of_body": body_sha,
        "note": (
            "Line 1 is this header and is not a recorded line. Every line after it is a "
            "Kraken v2 book frame copied byte-for-byte out of data/raw/, in recorded "
            "order. No gap marker intersects the window."
        ),
    }


def render(cut: Cut, *, pairs: Sequence[str], window: tuple[datetime, datetime]) -> bytes:
    """The whole fixture as bytes, header first.

    Assembled as bytes throughout. A `str` here would have to be encoded on the way to
    disk, and the one thing this artefact promises is that its body is the recorded
    bytes.
    """
    body = b"".join(line + b"\n" for line in cut.body)
    digest = hashlib.sha256(body).hexdigest()
    head = json.dumps(
        header(cut, pairs=pairs, window=window, body_sha=digest),
        separators=(",", ":"),
        sort_keys=False,
    ).encode("utf-8")
    return head + b"\n" + body


def guard_output(out: Path, source_dir: Path) -> None:
    """Invariant 11: nothing this project runs writes into the recording."""
    resolved_out = out.resolve()
    resolved_source = source_dir.resolve()
    if resolved_out == resolved_source or resolved_source in resolved_out.parents:
        raise RefusalError(
            f"refusing to write {resolved_out} inside the recording directory "
            f"{resolved_source}. Invariant 11: raw recordings are append-only and "
            "nothing writes into them."
        )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cut a book fixture out of data/raw/ for spec 96. Chooses nothing."
    )
    parser.add_argument("--pairs", nargs="+", required=True, help="Kraken v2 symbols")
    parser.add_argument("--from", dest="window_from", required=True, help="UTC ISO, inclusive")
    parser.add_argument("--to", dest="window_to", required=True, help="UTC ISO, exclusive")
    parser.add_argument("--out", type=Path, required=True, help="where the fixture goes")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument(
        "--prefix", default=None, help="only read archive files whose name starts with this"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="actually write. Without it the cut is made and reported but nothing lands.",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        window = (parse_iso(args.window_from), parse_iso(args.window_to))
        if window[1] <= window[0]:
            raise RefusalError(
                f"--to ({args.window_to}) is not after --from ({args.window_from}); "
                "an empty or backwards window has no frames in it"
            )
        pairs = tuple(dict.fromkeys(args.pairs))
        out: Path = args.out
        guard_output(out, args.source_dir)

        paths = candidate_files(args.source_dir, window, args.prefix)
        print(f"scanning {len(paths)} file(s): {', '.join(path.name for path in paths)}")
        cut = collect(paths, pairs=pairs, window=window)
        check(cut, paths, pairs=pairs, window=window)
        payload = render(cut, pairs=pairs, window=window)
    except RefusalError as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 2

    for pair, counts in sorted(cut.per_pair.items()):
        print(f"  {pair}: {counts}")
    print(f"  {cut.total()} frames, {len(payload)} bytes, {cut.lines_scanned} lines scanned")

    if not args.write:
        print(f"dry run: pass --write to create {out}")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    # Bytes, never text mode. `tests/fixtures/` is marked `-text` so that no
    # line-ending conversion happens near an evidence fixture, and a text-mode write
    # on Windows would turn every LF into CRLF and change the committed bytes.
    out.write_bytes(payload)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through `run`
    raise SystemExit(run())
