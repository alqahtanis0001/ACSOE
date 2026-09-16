"""Spec 86 step 2 — `scripts/cut_book_fixture.py`, the book-fixture cutter.

Every test builds its own scratch archive in `tmp_path`, shaped exactly like
`data/raw/`: one JSON object per line, the seven keys of
`clients/recorder/contracts.py`, files named `<prefix>_<YYYY-MM-DD>.jsonl`. Nothing
here reads the real recording, and nothing here writes near it — the recorder, the
recording manager and the funding poller are running, and invariant 11 makes the
archive append-only in any case.

The refusals are the substance of this file, and each one is tested as a **pair**: a
window that is refused and a window that is not, differing in one input. A cutter that
refused everything would satisfy every refusal test on its own and be useless.

The refusal worth reading twice is
`test_a_gap_that_starts_inside_the_window_and_ends_after_it_is_refused`. A gap marker
is written at *reconnect*, so that break's marker sits outside the window entirely and
a test on the marker's timestamp misses it — while the fixture's tail is exactly the
part that got truncated.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.cut_book_fixture import (
    FIXTURE_MARKER,
    RefusalError,
    collect,
    gap_interval,
    might_be_wanted,
    parse_iso,
    run,
)

DAY = "2026-09-15"
PREFIX = "kraken_v2"
WINDOW_FROM = f"{DAY}T04:00:00Z"
WINDOW_TO = f"{DAY}T04:10:00Z"


def at(second: str) -> str:
    """An ISO stamp on the fixture day. `second` is `HH:MM:SS`."""
    return f"{DAY}T{second}.000000Z"


def as_rendered(second: str) -> str:
    """The same moment as the refusal message renders it.

    `datetime.isoformat()` drops zero microseconds, so the message says
    `04:04:00Z` where the archive line says `04:04:00.000000Z`. Asserting the
    archive spelling would have made every gap-message assertion fail for a
    formatting reason rather than a behavioural one.
    """
    return f"{DAY}T{second}Z"


def book_line(pair: str, ts: str, *, frame_type: str = "update", price: float = 100.0) -> str:
    return json.dumps(
        {
            "v": 1,
            "kind": "tick",
            "pair": pair,
            "channel": "book",
            "ts_exchange": ts,
            "ts_recv": ts,
            "payload": {
                "channel": "book",
                "type": frame_type,
                "data": [
                    {
                        "symbol": pair,
                        "bids": [{"price": price, "qty": 1.0}],
                        "asks": [{"price": price + 1, "qty": 1.0}],
                        "checksum": 12345,
                        "timestamp": ts,
                    }
                ],
            },
        },
        separators=(",", ":"),
    )


def trade_line(pair: str, ts: str) -> str:
    return json.dumps(
        {
            "v": 1,
            "kind": "tick",
            "pair": pair,
            "channel": "trade",
            "ts_exchange": ts,
            "ts_recv": ts,
            "payload": {"channel": "trade", "data": [{"symbol": pair, "price": 100.0}]},
        },
        separators=(",", ":"),
    )


def gap_line(*, started: str, ended: str) -> str:
    """A `record.py`-shaped gap marker. Its `ts_recv` is the **reconnect**."""
    return json.dumps(
        {
            "v": 1,
            "kind": "gap",
            "pair": None,
            "channel": "_recorder",
            "ts_exchange": None,
            "ts_recv": ended,
            "payload": {
                "tier": "tier1",
                "reason": "ConnectionClosedError",
                "disconnected_at": started,
                "reconnected_at": ended,
                "gap_ms": 1000,
                "attempt": 1,
            },
        },
        separators=(",", ":"),
    )


def ws_gap_line(*, started: str, ended: str) -> str:
    """Engine 2's shape: `ws.py`'s own dict, with `started_at`/`ended_at`."""
    return json.dumps(
        {
            "v": 1,
            "kind": "gap",
            "pair": None,
            "channel": "_recorder",
            "ts_exchange": None,
            "ts_recv": ended,
            "payload": {
                "cause": "buffer overflow",
                "started_at": started,
                "ended_at": ended,
                "gap_ms": 1000,
            },
        },
        separators=(",", ":"),
    )


def archive(
    tmp_path: Path, lines: list[str], *, prefix: str = PREFIX, day: str = DAY
) -> Path:
    """A scratch `data/raw/`-shaped directory holding one file."""
    source = tmp_path / "raw"
    source.mkdir(parents=True, exist_ok=True)
    path = source / f"{prefix}_{day}.jsonl"
    with path.open("ab") as handle:
        for line in lines:
            handle.write(line.encode("utf-8") + b"\n")
    return source


def covered(inner: list[str]) -> list[str]:
    """`inner`, bracketed by two ticks so the window is covered at both ends.

    Coverage is its own refusal, so every test about something else has to satisfy it
    or it would be testing the coverage check by accident.
    """
    return [trade_line("BTC/USD", at("03:59:00")), *inner, trade_line("BTC/USD", at("04:11:00"))]


def cut(
    source: Path,
    out: Path,
    *,
    pairs: tuple[str, ...] = ("BTC/USD",),
    window_from: str = WINDOW_FROM,
    window_to: str = WINDOW_TO,
    write: bool = True,
    prefix: str | None = None,
) -> int:
    argv = [
        "--pairs",
        *pairs,
        "--from",
        window_from,
        "--to",
        window_to,
        "--out",
        str(out),
        "--source-dir",
        str(source),
    ]
    if prefix is not None:
        argv += ["--prefix", prefix]
    if write:
        argv.append("--write")
    return run(argv)


def read_fixture(path: Path) -> tuple[dict[str, Any], list[bytes]]:
    raw = path.read_bytes()
    head, _, body = raw.partition(b"\n")
    lines = [line for line in body.split(b"\n") if line]
    parsed: dict[str, Any] = json.loads(head)
    return parsed, lines


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #


def test_it_cuts_the_named_pairs_book_frames_byte_for_byte(tmp_path: Path) -> None:
    wanted_a = book_line("BTC/USD", at("04:00:00"), frame_type="snapshot")
    wanted_b = book_line("BTC/USD", at("04:05:00"))
    wanted_c = book_line("XRP/USD", at("04:06:00"))
    source = archive(
        tmp_path,
        covered(
            [
                book_line("BTC/USD", at("03:59:30")),  # before the window
                wanted_a,
                trade_line("BTC/USD", at("04:01:00")),  # wrong channel
                book_line("DOGE/USD", at("04:02:00")),  # wrong pair
                wanted_b,
                wanted_c,
                book_line("BTC/USD", at("04:10:00")),  # `to` is exclusive
            ]
        ),
    )
    out = tmp_path / "fixture.jsonl"

    assert cut(source, out, pairs=("BTC/USD", "XRP/USD")) == 0

    head, body = read_fixture(out)
    assert body == [wanted_a.encode(), wanted_b.encode(), wanted_c.encode()], (
        "the body is the recorded bytes, in recorded order, and nothing else"
    )
    assert head[FIXTURE_MARKER] == "book_frames"
    assert head["pairs"] == ["BTC/USD", "XRP/USD"]
    assert head["window"] == {"from": WINDOW_FROM, "to": WINDOW_TO, "bounds": "[from, to)"}
    assert head["lines"]["per_pair"] == {
        "BTC/USD": {"snapshot": 1, "update": 1},
        "XRP/USD": {"update": 1},
    }
    assert head["lines"]["total"] == 3
    assert head["source_files"] == [f"{PREFIX}_{DAY}.jsonl"]


def test_the_body_sha_in_the_header_is_the_sha_of_the_body(tmp_path: Path) -> None:
    """Recomputed here rather than trusted. A hash a producer wrote about itself is
    not a check on the producer — it is the producer agreeing with itself."""
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00"))]))
    out = tmp_path / "fixture.jsonl"
    assert cut(source, out) == 0

    raw = out.read_bytes()
    _, _, body = raw.partition(b"\n")
    head = json.loads(raw.partition(b"\n")[0])
    assert head["sha256_of_body"] == hashlib.sha256(body).hexdigest()


def test_the_output_carries_no_carriage_returns(tmp_path: Path) -> None:
    """`tests/fixtures/` is marked `-text`, so there is no clean filter to normalise
    a text-mode write. A CRLF here is a committed byte change, and on a parquet
    payload it is corruption; on this one it silently breaks a byte-for-byte
    comparison against the archive."""
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00"))]))
    out = tmp_path / "fixture.jsonl"
    assert cut(source, out) == 0
    assert b"\r" not in out.read_bytes()


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00"))]))
    out = tmp_path / "fixture.jsonl"
    assert cut(source, out, write=False) == 0
    assert not out.exists()


# --------------------------------------------------------------------------- #
# Gaps — the acceptance criterion
# --------------------------------------------------------------------------- #


def test_a_gap_inside_the_window_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = archive(
        tmp_path,
        covered(
            [
                book_line("BTC/USD", at("04:01:00")),
                gap_line(started=at("04:02:00"), ended=at("04:02:30")),
                book_line("BTC/USD", at("04:03:00")),
            ]
        ),
    )
    out = tmp_path / "fixture.jsonl"

    assert cut(source, out) == 2
    assert not out.exists()
    message = capsys.readouterr().err
    assert "a recorded gap intersects the window" in message
    assert as_rendered("04:02:00") in message, "the refusal names the gap it found"


def test_a_gap_that_starts_inside_the_window_and_ends_after_it_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The case a timestamp test misses, and the one that truncates the fixture.

    A gap marker is written at **reconnect** — `_close_gap` in `ws.py` says why: the
    length of a gap is not known until it ends, and a marker written at disconnect
    would have to be edited afterwards, which invariant 11 forbids. So a break that
    began at 04:09 and ended at 04:12 has its only marker at 04:12, outside the
    window. A cutter testing the marker's `ts_recv` cuts happily and produces a
    fixture whose last minute is missing, with nothing anywhere saying so.
    """
    source = archive(
        tmp_path,
        [
            trade_line("BTC/USD", at("03:59:00")),
            book_line("BTC/USD", at("04:01:00")),
            gap_line(started=at("04:09:00"), ended=at("04:12:00")),
            trade_line("BTC/USD", at("04:13:00")),
        ],
    )
    out = tmp_path / "fixture.jsonl"

    assert cut(source, out) == 2
    message = capsys.readouterr().err
    assert "a recorded gap intersects the window" in message
    assert as_rendered("04:09:00") in message


def test_a_gap_wholly_outside_the_window_is_not_refused(tmp_path: Path) -> None:
    """The other half. A cutter that refused on any gap anywhere would pass both
    tests above and never cut anything from a real archive, which reconnects
    several times an hour."""
    source = archive(
        tmp_path,
        covered(
            [
                gap_line(started=at("03:50:00"), ended=at("03:51:00")),
                book_line("BTC/USD", at("04:01:00")),
                gap_line(started=at("04:20:00"), ended=at("04:21:00")),
            ]
        ),
    )
    out = tmp_path / "fixture.jsonl"

    assert cut(source, out) == 0
    _, body = read_fixture(out)
    assert len(body) == 1


def test_a_gap_that_ends_exactly_at_the_window_start_is_not_refused(
    tmp_path: Path,
) -> None:
    """`[from, to)`. A break that closed at the instant the window opens left every
    frame in the window on one side of it."""
    source = archive(
        tmp_path,
        covered(
            [
                gap_line(started=at("03:58:00"), ended=WINDOW_FROM.replace("Z", ".000000Z")),
                book_line("BTC/USD", at("04:01:00")),
            ]
        ),
    )
    assert cut(source, tmp_path / "fixture.jsonl") == 0


def test_the_engine_2_shaped_gap_marker_is_read_as_well(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two writers, two payload shapes, both in the archive.

    `scripts/record.py` writes `disconnected_at`/`reconnected_at`; engine 2 writes
    `ws.py`'s own dict with `started_at`/`ended_at`. Reading only the first shape
    would make every break the daemon recorded invisible to this cutter.
    """
    source = archive(
        tmp_path,
        covered(
            [
                book_line("BTC/USD", at("04:01:00")),
                ws_gap_line(started=at("04:04:00"), ended=at("04:04:30")),
            ]
        ),
    )
    assert cut(source, tmp_path / "fixture.jsonl") == 2
    assert as_rendered("04:04:00") in capsys.readouterr().err


def test_a_gap_marker_with_no_interval_falls_back_to_its_own_timestamp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Absent is not zero, and it is not "no gap" either.

    A marker whose payload says neither shape is a break whose span is unknown, not a
    break of zero length. The cutter treats the marker's own `ts_recv` as a point
    inside the window and says in the message that the span was unknown, rather than
    deciding the break did not happen.
    """
    bare = json.dumps(
        {
            "v": 1,
            "kind": "gap",
            "pair": None,
            "channel": "_recorder",
            "ts_exchange": None,
            "ts_recv": at("04:05:00"),
            "payload": {"reason": "unknown"},
        },
        separators=(",", ":"),
    )
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00")), bare]))

    assert cut(source, tmp_path / "fixture.jsonl") == 2
    assert "span unknown" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# The other refusals
# --------------------------------------------------------------------------- #


def test_it_refuses_to_write_inside_the_recording(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Invariant 11, and the one refusal that protects data rather than the fixture."""
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00"))]))

    assert cut(source, source / "fixture.jsonl") == 2
    assert "Invariant 11" in capsys.readouterr().err
    assert not (source / "fixture.jsonl").exists()


def test_a_window_the_archive_does_not_cover_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An open gap has no marker: nothing was running to write one.

    The recording stops at 04:05 and the window runs to 04:10. There is no gap
    marker, because a marker is written on reconnect and there was no reconnect — so
    the five missing minutes look exactly like a quiet market.
    """
    source = archive(
        tmp_path,
        [trade_line("BTC/USD", at("03:59:00")), book_line("BTC/USD", at("04:01:00"))],
    )

    assert cut(source, tmp_path / "fixture.jsonl") == 2
    assert "does not contain the whole window" in capsys.readouterr().err


def test_two_recorders_contributing_to_one_window_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The doubled archive. Two `record.py` processes ran concurrently from
    2026-09-09T13:19, so part of `data/raw/` holds every frame twice — and a book
    walk over a doubled fixture reads twice the depth, which is a plausible,
    in-range, wrong answer rather than a crash."""
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00"))]))
    archive(
        tmp_path,
        covered([book_line("BTC/USD", at("04:01:00"))]),
        prefix="kraken_v2__msi__",
    )

    assert cut(source, tmp_path / "fixture.jsonl") == 2
    assert "more than one archive file contributed" in capsys.readouterr().err


def test_the_prefix_selects_one_recorder_and_the_cut_then_succeeds(
    tmp_path: Path,
) -> None:
    """The other half of the pair above — and the fix the refusal recommends."""
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00"))]))
    archive(
        tmp_path,
        covered([book_line("BTC/USD", at("04:02:00"))]),
        prefix="kraken_v2__msi__",
    )
    out = tmp_path / "fixture.jsonl"

    assert cut(source, out, prefix="kraken_v2__msi__") == 0
    _, body = read_fixture(out)
    assert len(body) == 1
    assert at("04:02:00").encode() in body[0]


def test_a_named_pair_with_no_book_frame_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00"))]))

    assert cut(source, tmp_path / "fixture.jsonl", pairs=("BTC/USD", "XRP/USD")) == 2
    message = capsys.readouterr().err
    assert "no book frame for XRP/USD" in message


def test_a_backwards_window_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00"))]))
    assert cut(source, tmp_path / "f.jsonl", window_from=WINDOW_TO, window_to=WINDOW_FROM) == 2
    assert "is not after" in capsys.readouterr().err


def test_a_naive_window_bound_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A naive timestamp read as local time shifts the window by the machine's UTC
    offset, by a different amount in summer — an error that reproduces in one season
    and not the other."""
    source = archive(tmp_path, covered([book_line("BTC/USD", at("04:01:00"))]))
    assert cut(source, tmp_path / "f.jsonl", window_from=f"{DAY}T04:00:00") == 2
    assert "has no timezone" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# The prefilter is strictly broader than the parse it fronts
# --------------------------------------------------------------------------- #


def test_the_prefilter_admits_a_unicode_escaped_book_line(tmp_path: Path) -> None:
    """The Phase 4 defect, written as a test rather than as a promise.

    A prefilter that is *narrower* than its parser does not make the check faster, it
    makes it wrong on the inputs it silently excludes — and A shipped two of those in
    one file, one of which would have classified the entire recording as unrecorded.
    A JSON encoder is allowed to write `"book"` as `"\\u0062ook"`. This line carries
    the bytes `book` nowhere, and the prefilter must still admit it.
    """
    escaped = (
        '{"v":1,"kind":"tick","pair":"BTC/USD","channel":"\\u0062ook",'
        f'"ts_exchange":null,"ts_recv":"{at("04:01:00")}",'
        '"payload":{"type":"update"}}'
    )
    assert b"book" not in escaped.encode("utf-8")
    assert might_be_wanted(escaped.encode("utf-8")), "the prefilter excluded a real book line"

    source = archive(tmp_path, covered([escaped]))
    out = tmp_path / "fixture.jsonl"
    assert cut(source, out) == 0
    _, body = read_fixture(out)
    assert body == [escaped.encode("utf-8")]


def test_the_prefilter_skips_a_line_that_cannot_be_wanted() -> None:
    """The other half. A prefilter returning True for everything is not a prefilter,
    and would make the test above pass while measuring nothing."""
    assert not might_be_wanted(trade_line("BTC/USD", at("04:01:00")).encode("utf-8"))


# --------------------------------------------------------------------------- #
# Units
# --------------------------------------------------------------------------- #


def test_gap_interval_reads_both_shapes_and_refuses_to_guess_a_third() -> None:
    record_shaped = json.loads(gap_line(started=at("04:00:00"), ended=at("04:01:00")))
    ws_shaped = json.loads(ws_gap_line(started=at("04:00:00"), ended=at("04:01:00")))
    expected = (parse_iso(at("04:00:00")), parse_iso(at("04:01:00")))

    assert gap_interval(record_shaped) == expected
    assert gap_interval(ws_shaped) == expected
    assert gap_interval({"payload": {"reason": "unknown"}}) is None
    assert gap_interval({"payload": "not a dict"}) is None


def test_collect_reads_the_archive_without_writing_to_it(tmp_path: Path) -> None:
    """Read-only, asserted on the directory rather than on the code.

    The recorder, the recording manager and the funding poller run continuously
    against the real `data/raw/`, and this script reads the same files while they are
    open. `collect` touching one of them would be invariant 11 and a live process's
    file at the same time.
    """
    lines = covered([book_line("BTC/USD", at("04:01:00"))])
    source = archive(tmp_path, lines)
    path = source / f"{PREFIX}_{DAY}.jsonl"
    before = (path.read_bytes(), sorted(p.name for p in source.iterdir()))

    cut_result = collect(
        [path], pairs=("BTC/USD",), window=(parse_iso(WINDOW_FROM), parse_iso(WINDOW_TO))
    )

    assert cut_result.total() == 1
    assert (path.read_bytes(), sorted(p.name for p in source.iterdir())) == before


def test_a_missing_source_directory_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2 and a named reason, not a traceback.

    `run` catches `RefusalError` and turns it into an exit code, which is what an
    operator sees. Asserting `pytest.raises(RefusalError)` here would assert on a
    layer the caller never reaches — the first version of this test did exactly that
    and failed with DID NOT RAISE while the refusal was working perfectly.
    """
    assert (
        run(
            [
                "--pairs",
                "BTC/USD",
                "--from",
                WINDOW_FROM,
                "--to",
                WINDOW_TO,
                "--out",
                str(tmp_path / "unused.jsonl"),
                "--source-dir",
                str(tmp_path / "no-such-directory-anywhere"),
            ]
        )
        == 2
    )
    assert "is not a directory" in capsys.readouterr().err


def test_the_refusal_type_is_its_own_so_a_caller_can_catch_it() -> None:
    """`RefusalError` exists so a test — or a future caller that is not the CLI —
    can tell a refusal from an unexpected crash. Asserted directly, because `run`
    swallows it and nothing else would notice it being widened to `Exception`."""
    with pytest.raises(RefusalError, match="has no timezone"):
        parse_iso("2026-09-15T04:00:00")
