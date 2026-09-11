#!/usr/bin/env python
"""Build Kraken-archive-shaped 15-minute OHLCVT CSVs in `data/historical/` from the
**real** recorded trade frames in `data/raw/`.

    python scripts/build_archive.py --write

Spec 54. `data/historical/` is empty: Kraken's downloadable OHLCVT archives were never
obtained, the operator has rotated the API key, and no live call can be made. What the
repository does have is roughly three days of real Kraken WebSocket v2 `trade` frames
recorded by `scripts/record.py` since Phase 0. This script reduces those into the CSV
shape `acsoe.research.historical.load_archive` already reads, so Phase 4 has something
to replay.

## What this artefact is, and what it is not

**The trades are real.** Kraken v2 `trade` frames off the live socket, taken verbatim
out of `data/raw/`. Nothing is synthesised, nothing is smoothed, and there is no code
path here that invents a price.

**The reduction is ours.** These are not Kraken's own published OHLCVT candles. The
archive carries no OHLC channel — `record.py` subscribes to `book`, `ticker` and
`trade` — and no live call can be made, so the bars are computed here. That is weaker
than an independent source and it is written into `PROVENANCE.json` beside the CSVs
rather than left to a docstring nobody reads at the point of use. Confirming these bars
against Kraken's published archive is a `--live` task, and `replay_full_archive` is the
criterion that will do it when the operator supplies a real archive.

**The span is three days, not six months.** Every consumer that assumes a six-month
archive gets three days here, and the gap report says so honestly.

## A quiet interval produces no row. This is the point of the file.

Kraken's archives contain only intervals in which trades occurred, so a hole is a
**fact about the market** and not missing data. This script emits a row only for an
interval that actually had a trade in it. It never carries the previous close forward,
never resamples onto a regular grid, and there is deliberately no flag that does.

Emitting a zero-volume bar at the previous close is interpolation wearing a different
hat. It is load-bearing for Phase 4's triple-barrier labelling, which walks forward from
each decision bar to decide whether the target, the stop or the timeout came first: a
synthesised candle at a price that never traded invents a barrier touch that never
happened, and the label built from it is a fabricated outcome the model then learns
from. `research/historical.py` argues this at length and this script does not undo it.

## ...but a hole HERE does not mean what a hole in a real Kraken archive means

Kraken never stops watching, so a hole in Kraken's own archive can only mean no trades.
**This archive is built from a recording, and the recorder stopped.** `data/raw/` carries
session restarts with no matching stop, thirteen `kind: "gap"` records for dropped
connections, and a ten-hour stretch on 2026-09-08 with nothing in it at all. So a hole
here is *either* a quiet interval *or* an interval nobody was watching, and on a pair
that trades every fifteen minutes without fail it is always the second.

Worse than a whole hole: an interval the recorder covered for only part of produces a
row that **looks complete and is not** — real trades and real prices, but understated
volume and a high or a low that may never have been seen.

The CSV cannot say which is which. Kraken's OHLCVT format has seven columns and an
eighth would stop `read_archive_rows` reading the file, which is the whole point of the
shape. So the distinction is derived here and written to `PROVENANCE.json` beside the
CSVs: every **minute** in which the recorder logged any frame at all is marked, and each
interval is then `not_recorded`, `partial`, or genuinely quiet. It is derived from the
recording rather than assumed, and `replay.py` carries it alongside the gap report so
that it travels with the data.

## De-duplication is at the frame level, never the trade level

Two recorders produce the same frame twice; two genuinely identical trades arrive
**inside one frame**, not as two frames. De-duplicating at the trade level would
silently delete real volume. `scripts/ohlc_fixture.py` reached this conclusion first and
this script keeps it.

"By exact bytes" means the exact bytes of the frame **Kraken sent**, which is the
`payload` plus `ts_exchange` — not the exact bytes of the recorded line. The line also
carries `ts_recv`, which is the recorder's own arrival clock and differs between two
recorders by microseconds, so hashing the whole line finds no duplicates at all. See the
build log entry for 2026-09-11.

`data/raw/` is never written to. Invariant 11: recorded data is immutable and
corrections live in a derived layer. This script only ever opens it for reading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

DEFAULT_RAW_DIR: Final = Path("data") / "raw"
DEFAULT_OUT_DIR: Final = Path("data") / "historical"
DEFAULT_INTERVAL_S: Final = 900
PROVENANCE_FILENAME: Final = "PROVENANCE.json"

#: The byte the prefilter looks for before spending a `json.loads` on a line. The raw
#: files are gigabytes of `book` frames and trade frames are well under a percent of
#: them, so this cheap `in` on the undecoded bytes is what makes a full pass tolerable.
#:
#: **Deliberately broader than the check it stands in front of.** It was
#: `b'"channel":"trade"'`, which silently depended on the recorder using `orjson` and its
#: compact separators: one space after the colon and the prefilter matches nothing, the
#: pass finds zero trade frames, and the builder reports success over an empty archive. A
#: cheap prefilter is a second, weaker definition of the same predicate, and a narrower
#: one fails invisibly. The exact test lives in `decode_trade_frame` and nowhere else.
_TRADE_MARKER: Final = b'"trade"'

#: Every recorded line carries the recorder's own arrival clock. Found by a byte search
#: rather than by decoding, because coverage is measured over every line in the file and
#: there are millions of them. The **key** only: the separator between it and its value
#: is the serialiser's choice, and matching `b'"ts_recv":"'` made coverage silently
#: depend on `orjson` writing no space after the colon. Same defect as `_TRADE_MARKER`.
_TS_RECV_MARKER: Final = b'"ts_recv"'

PROVENANCE_NOTE: Final = (
    "Bars are reduced from real Kraken WebSocket v2 `trade` frames recorded by "
    "scripts/record.py into data/raw/, taken verbatim. They are NOT Kraken's own "
    "published OHLCVT archive: the recording carries no OHLC channel and no live call "
    "can be made, so the reduction is ours and is weaker than an independent source. "
    "Confirming these bars against Kraken's published archive is a --live task."
)

NO_INTERPOLATION_NOTE: Final = (
    "An interval in which nothing traded has NO row here, exactly as a real Kraken "
    "archive contains only intervals in which trades occurred. Nothing is forward-"
    "filled, resampled or interpolated, and no flag asks for it."
)


class Bar:
    """One interval's accumulating OHLCVT.

    Open and close are decided by the **trade's own exchange timestamp**, with
    `trade_id` breaking a tie, rather than by the order frames happen to sit in the
    file. Two recorders interleaving, or a reconnect replaying a frame, can put the
    file out of exchange order; an open taken from "the first row I saw" would then be
    a different number depending on how the recording was stitched together, which is
    not a property a price series may have.
    """

    __slots__ = ("close", "close_key", "high", "low", "open", "open_key", "trades", "ts", "volume")

    def __init__(self, ts: int, price: Decimal, qty: Decimal, key: tuple[float, int]) -> None:
        self.ts = ts
        self.open = price
        self.close = price
        self.high = price
        self.low = price
        self.volume = qty
        self.trades = 1
        self.open_key = key
        self.close_key = key

    def add(self, price: Decimal, qty: Decimal, key: tuple[float, int]) -> None:
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        if key < self.open_key:
            self.open_key = key
            self.open = price
        if key > self.close_key:
            self.close_key = key
            self.close = price
        self.volume += qty
        self.trades += 1

    def csv_row(self) -> str:
        return ",".join(
            (
                str(self.ts),
                _plain(self.open),
                _plain(self.high),
                _plain(self.low),
                _plain(self.close),
                _plain(self.volume),
                str(self.trades),
            )
        )


def _plain(value: Decimal) -> str:
    """A `Decimal` as plain decimal text, never scientific notation.

    `str(Decimal("1E-8"))` is `1E-8`, which `read_archive_rows` would parse back
    correctly but which no Kraken archive contains. `:f` keeps the round trip exact
    while keeping the file in the shape the loader was written against.
    """
    return f"{value:f}"


def parse_iso(text: str) -> float:
    """An ISO-8601 UTC instant as epoch seconds, sub-second precision kept.

    The fractional part never reaches a bar boundary decision — that floors to the
    interval — but it does decide which of two trades in the same second opened the
    bar, so throwing it away here would make the open depend on tie-breaking instead.
    """
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).timestamp()


def frame_digest(payload: Any, ts_exchange: Any) -> bytes:
    """The identity of a frame **as Kraken sent it**.

    Deliberately excludes the recorder's envelope. `ts_recv` is the arrival clock of
    whichever recorder wrote the line and two recorders never agree on it to the
    microsecond, so a digest over the whole line would call every duplicate distinct.
    `payload` is canonicalised with `sort_keys` because two `json` writers can order
    one object's keys differently while meaning the same frame.
    """
    material = json.dumps(payload, sort_keys=True, default=str).encode() + str(ts_exchange).encode()
    return hashlib.blake2b(material, digest_size=16).digest()


def recorded_minute(raw: bytes, cache: dict[bytes, int]) -> int | None:
    """The minute this recorded line arrived in, as epoch seconds, or `None`.

    Read straight out of the undecoded bytes. Every line in the recording carries
    `ts_recv`, and there are millions of them — `json.loads` on each one to find a
    timestamp would cost more than the whole rest of this script. The minute prefix is
    cached because thousands of consecutive lines share it.
    """
    index = raw.find(_TS_RECV_MARKER)
    if index < 0:
        return None
    # Step over the key, then over whatever the serialiser put between it and the
    # value, to the opening quote. Bounded so that a `null` value cannot walk into the
    # next key's quote and hand back sixteen characters of something else.
    after_key = index + len(_TS_RECV_MARKER)
    quote = raw.find(b'"', after_key, after_key + 8)
    if quote < 0:
        return None
    start = quote + 1
    minute = raw[start : start + 16]  # "2026-09-09T09:53"
    if len(minute) < 16:
        return None
    known = cache.get(minute)
    if known is not None:
        return known
    try:
        seconds = int(parse_iso(minute.decode("ascii") + ":00Z"))
    except (UnicodeDecodeError, ValueError):
        return None
    cache[minute] = seconds
    return seconds


def decode_trade_frame(raw: bytes) -> dict[str, Any] | None:
    """One recorded line as a `trade` frame, or `None` if it is anything else.

    Money is parsed with `parse_float=Decimal`, so a price never exists as a binary
    float even momentarily: `json.loads` builds the `Decimal` from the literal text in
    the file. `Decimal(str(some_float))` would also be exact for the values Kraken
    sends, but only because their shortest repr round-trips, which is a property of the
    data rather than of the code.
    """
    if _TRADE_MARKER not in raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        line = json.loads(stripped, parse_float=Decimal)
    except ValueError:
        return None
    # Narrowed rather than cast. `json.loads` is typed `Any`, and a recorded line that
    # parsed to a list or a scalar would reach `.get` below and raise AttributeError
    # out of a function whose whole contract is to return None for anything it does
    # not recognise. mypy pointed at the annotation; the hole was real.
    if not isinstance(line, dict):
        return None
    if line.get("kind") != "tick" or line.get("channel") != "trade":
        return None
    if not isinstance(line.get("payload"), dict):
        return None
    return line


def iter_recording(path: Path) -> Iterator[bytes]:
    """Yield one recorded line at a time.

    Streamed. The raw files are gigabytes each and `read()` on one of them is the
    difference between this script running and this machine swapping.
    """
    with path.open("rb") as handle:
        yield from handle


def classify_interval(
    ts: int, *, interval_s: int, recorded_minutes: frozenset[int]
) -> str:
    """Was this interval watched, half-watched, or not watched at all?

    `complete` — every minute of it is in the recording, so the absence of a trade is a
    fact about the market and the presence of one is a full bar.
    `partial` — some minutes only. A row built from this is real but understates volume
    and may miss the interval's true high or low; a hole in it proves nothing.
    `not_recorded` — nobody was watching. A hole here is an outage wearing a quiet
    market's clothes, and it is the one this project must never read as calm.
    """
    minutes = range(ts, ts + interval_s, 60)
    seen = sum(1 for minute in minutes if minute in recorded_minutes)
    if seen == 0:
        return "not_recorded"
    if seen == len(range(ts, ts + interval_s, 60)):
        return "complete"
    return "partial"


def build_bars(
    paths: list[Path],
    *,
    interval_s: int,
    pairs: tuple[str, ...] | None = None,
) -> tuple[dict[str, dict[int, Bar]], frozenset[int], dict[str, Any]]:
    """Reduce every recorded trade into per-pair, per-interval bars.

    Returns the bars, the set of minutes the recorder was actually logging in, and a
    statistics block for the provenance artefact. Nothing here creates a bar for an
    interval no trade fell in: the dict is keyed by the buckets that were actually hit,
    which is what makes "a quiet interval produces no row" true by construction rather
    than by a later filtering step somebody could remove.
    """
    bars: dict[str, dict[int, Bar]] = {}
    seen: set[bytes] = set()
    minutes: set[int] = set()
    minute_cache: dict[bytes, int] = {}
    wanted = set(pairs) if pairs else None

    stats: dict[str, Any] = {
        "files_read": [],
        "lines_read": 0,
        "trade_frames_read": 0,
        "frame_duplicates_dropped": 0,
        "trades_reduced": 0,
        "trades_skipped_unparsable": 0,
        "repeated_trade_ids": 0,
        "pairs_seen": set(),
    }
    trade_ids: dict[str, set[int]] = {}

    for path in sorted(paths):
        stats["files_read"].append(path.name)
        for raw in iter_recording(path):
            stats["lines_read"] += 1
            minute = recorded_minute(raw, minute_cache)
            if minute is not None:
                minutes.add(minute)
            line = decode_trade_frame(raw)
            if line is None:
                continue
            stats["trade_frames_read"] += 1
            digest = frame_digest(line["payload"], line.get("ts_exchange"))
            if digest in seen:
                stats["frame_duplicates_dropped"] += 1
                continue
            seen.add(digest)

            for item in line["payload"].get("data") or []:
                if not isinstance(item, dict):
                    continue
                symbol = item.get("symbol")
                stamp = item.get("timestamp")
                if not isinstance(symbol, str) or not isinstance(stamp, str):
                    stats["trades_skipped_unparsable"] += 1
                    continue
                if wanted is not None and symbol not in wanted:
                    continue
                try:
                    seconds = parse_iso(stamp)
                    price = Decimal(item["price"])
                    qty = Decimal(item["qty"])
                except (KeyError, ValueError, ArithmeticError):
                    stats["trades_skipped_unparsable"] += 1
                    continue

                stats["pairs_seen"].add(symbol)
                trade_id = int(item.get("trade_id") or 0)
                if trade_id:
                    known = trade_ids.setdefault(symbol, set())
                    if trade_id in known:
                        # Reported, never dropped. A repeated `trade_id` across two
                        # distinct frames would be a real double-count and is a fact
                        # the reader of this archive is entitled to know about; it is
                        # not a licence for this script to start de-duplicating trades.
                        stats["repeated_trade_ids"] += 1
                    known.add(trade_id)

                bucket = int(seconds // interval_s) * interval_s
                key = (seconds, trade_id)
                pair_bars = bars.setdefault(symbol, {})
                bar = pair_bars.get(bucket)
                if bar is None:
                    pair_bars[bucket] = Bar(bucket, price, qty, key)
                else:
                    bar.add(price, qty, key)
                stats["trades_reduced"] += 1

    stats["pairs_seen"] = sorted(stats["pairs_seen"])
    stats["recorded_minutes"] = len(minutes)
    return bars, frozenset(minutes), stats


def archive_filename(pair: str, interval_s: int) -> str:
    """`BTC/USD` at 900s becomes `BTCUSD_15.csv`.

    Named after the symbol **Kraken's WebSocket v2 actually used in the recording**,
    with the separator removed and the interval in minutes appended, which is the shape
    of Kraken's own downloadable files. No attempt is made to translate `BTC` to the
    `XBT` spelling some Kraken surfaces use: this file did not come from Kraken's
    archive service and naming it as though it had would be the one misleading thing in
    an artefact whose whole point is stating its own provenance. `AGENTS.md` is explicit
    that remembered Kraken naming is stale, and `load_archive` takes `pair=` anyway.
    """
    return f"{pair.replace('/', '').replace(':', '')}_{interval_s // 60}.csv"


def write_archive(bars: dict[int, Bar], path: Path) -> int:
    """Write one pair's bars as a headerless Kraken-shaped OHLCVT CSV, time-ascending.

    Returns the row count. Only buckets present in `bars` are written — the range
    between the first and last is never walked, which is the difference between this
    and a reducer that fills holes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [bars[ts].csv_row() for ts in sorted(bars)]
    path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8", newline="\n")
    return len(rows)


def _span(
    bars: dict[int, Bar], interval_s: int, recorded_minutes: frozenset[int]
) -> dict[str, Any]:
    """One pair's span, plus what its holes and its thin rows actually are.

    `missing_quiet` is the only figure here that means what a hole in Kraken's own
    archive means. `missing_not_recorded` and `partial_rows` are artefacts of this
    archive being built from a recording, and they are reported by timestamp rather
    than only counted so a consumer can exclude them instead of trusting a number.
    """
    if not bars:
        return {"first_ts": None, "last_ts": None, "rows": 0, "intervals_in_span": 0}
    first, last = min(bars), max(bars)

    missing_quiet: list[int] = []
    missing_not_recorded: list[int] = []
    missing_partial: list[int] = []
    partial_rows: list[int] = []
    for ts in range(first, last + interval_s, interval_s):
        coverage = classify_interval(
            ts, interval_s=interval_s, recorded_minutes=recorded_minutes
        )
        if ts in bars:
            if coverage != "complete":
                partial_rows.append(ts)
            continue
        if coverage == "not_recorded":
            missing_not_recorded.append(ts)
        elif coverage == "partial":
            missing_partial.append(ts)
        else:
            missing_quiet.append(ts)

    return {
        "first_ts": first,
        "last_ts": last,
        "first_iso": datetime.fromtimestamp(first, tz=UTC).isoformat().replace("+00:00", "Z"),
        "last_iso": datetime.fromtimestamp(last, tz=UTC).isoformat().replace("+00:00", "Z"),
        "rows": len(bars),
        "intervals_in_span": ((last - first) // interval_s) + 1,
        "missing_quiet": len(missing_quiet),
        "missing_not_recorded": len(missing_not_recorded),
        "missing_partially_recorded": len(missing_partial),
        "missing_quiet_ts": missing_quiet,
        "missing_not_recorded_ts": missing_not_recorded,
        "missing_partially_recorded_ts": missing_partial,
        "partial_rows": len(partial_rows),
        "partial_rows_ts": partial_rows,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="build_archive.py",
        description=(
            "Reduce real recorded Kraken trade frames in data/raw/ into "
            "Kraken-archive-shaped OHLCVT CSVs in data/historical/."
        ),
    )
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--interval-s", type=int, default=DEFAULT_INTERVAL_S)
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=None,
        help="restrict to these symbols; default is every pair found in the recording",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="without this the script reports what it would write and touches nothing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    interval = args.interval_s
    if interval <= 0:
        print("--interval-s must be positive", file=sys.stderr)
        return 2

    raw_dir = Path(args.raw_dir)
    paths = sorted(raw_dir.glob("*.jsonl"))
    if not paths:
        print(f"no recording found in {raw_dir}", file=sys.stderr)
        return 2

    bars, recorded_minutes, stats = build_bars(
        paths, interval_s=interval, pairs=tuple(args.pairs) if args.pairs else None
    )
    if not bars:
        print("no trades found in the recording", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    provenance: dict[str, Any] = {
        "schema_version": 1,
        "built_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "built_by": "scripts/build_archive.py",
        "interval_s": interval,
        "source": "data/raw/ - real Kraken WebSocket v2 trade frames",
        "provenance": PROVENANCE_NOTE,
        "interpolation": NO_INTERPOLATION_NOTE,
        "deduplication": (
            "Frame level, by the exact bytes of the frame Kraken sent (payload plus "
            "ts_exchange, canonicalised). NEVER at the trade level: two genuinely "
            "identical trades arrive inside one frame, so dropping them would delete "
            "real volume. `repeated_trade_ids` is reported and nothing is dropped for it."
        ),
        "coverage": (
            "A hole in a real Kraken archive can only mean no trades occurred, because "
            "Kraken never stops watching. This archive is built from a recording that "
            "did stop, so a hole is EITHER a quiet interval OR an interval nobody was "
            "watching. Each pair below therefore separates `missing_quiet` (every minute "
            "of the interval is in the recording and still no trade - the only holes "
            "that mean what Kraken's mean) from `missing_not_recorded` and "
            "`missing_partially_recorded`. `partial_rows` are rows that look complete "
            "and are not: real trades over an interval the recorder only partly covered, "
            "so the volume is understated and the high or low may never have been seen. "
            "Do not walk a triple barrier across a not-recorded stretch: it reads as a "
            "calm market and returns a timeout where the real market touched a barrier."
        ),
        # False, and this is the whole difference between this artefact and the one
        # `scripts/build_ohlcvt.py` builds from Kraken's published history. A hole here
        # is usually an outage, measured at `missing_quiet` 0 on all three pairs.
        "holes_mean_no_trades": False,
        "has_order_book": False,
        "has_spread": False,
        "statistics": {key: value for key, value in stats.items() if key != "pairs_seen"},
        "pairs": {},
    }

    for pair in sorted(bars):
        name = archive_filename(pair, interval)
        span = _span(bars[pair], interval, recorded_minutes)
        provenance["pairs"][pair] = {"file": name, **span}
        note = (
            f"{span['rows']} rows, {span['missing_quiet']} quiet holes, "
            f"{span['missing_not_recorded']} not-recorded holes, "
            f"{span['partial_rows']} partially recorded rows"
        )
        if args.write:
            write_archive(bars[pair], out_dir / name)
            print(f"{pair}: {note} -> {out_dir / name}", file=sys.stderr)
        else:
            print(f"{pair}: {note} (dry run, nothing written)", file=sys.stderr)

    print(
        f"trade frames read: {stats['trade_frames_read']}, "
        f"frame duplicates dropped: {stats['frame_duplicates_dropped']}, "
        f"trades reduced: {stats['trades_reduced']}, "
        f"repeated trade ids: {stats['repeated_trade_ids']}",
        file=sys.stderr,
    )

    if not args.write:
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    # `newline="\n"` is not decoration. `Path.write_text` opens in TEXT mode, and text
    # mode on Windows translates every `\n` to `\r\n` — so a bare call writes a CRLF
    # artefact into a file something else reads back. Lead's standing rule, 2026-09-11:
    # when writing a file, write bytes or pass `newline`, never a bare `write_text`.
    (out_dir / PROVENANCE_FILENAME).write_text(
        json.dumps(provenance, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {out_dir / PROVENANCE_FILENAME}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
