#!/usr/bin/env python
"""The spread the cost gate was calibrated on, against the spread it runs on.

Engine 10 `cost` blocks a trade when net edge does not clear
`hurdle_multiple x friction`, and `friction = maker + taker + spread + slippage`.
The spread term is the only one of the four that is a **live measurement** rather
than a number the exchange states: fees come from `TradeVolume`, minimums from
`AssetPairs`, and slippage from engine 9's book estimate — but the spread comes
from engine 3 `market_sensor`, computed from the stream at the moment of the
decision.

The model of that spread is calibrated on the **recorder's** archive. The gate
runs on the **daemon's** live quote. Nothing compares them, and a systematic
difference between the two would move every cost-gate verdict in the same
direction without changing a single line of output anywhere: the gate would keep
blocking and passing, its reasons would keep reading correctly, and the break-even
win rate the whole project is measured against would quietly be wrong.

At a ~1.25% round trip and a 3% target, a spread bias of a few basis points is not
decoration. It moves the break-even win rate, and the break-even win rate is the
number the dissertation's conclusion rests on.

So this reports the **distribution of the difference**, not a single number.
A mean difference near zero with a wide spread of differences is a different
finding from a small constant offset, and only the second one is a calibration
error: the first is sampling noise between two observers of the same book, and
"correcting" it would be fitting to noise.

## Two sources of difference, and only one of them is a defect

**Timing.** The recorder's tier 1 gives a spread at the instant of a book update;
tier 2 gives a *minute median*. The daemon quotes at the tick. Two observations
seconds apart in a moving market differ for an honest reason, and the difference
grows with volatility rather than with any error. This is why the report is
bucketed by source tier: a tier 2 comparison has a known approximation in it and a
tier 1 comparison does not.

**Construction.** `spread_pct` in engine 3 is `(ask - bid) / mid` as a decimal
ratio; the recorder's summaries store `spread_bps` as `(ask - bid) / mid * 10000`.
Those are the same quantity in different units, and this script converts rather
than assuming — a factor of 10,000 confused for a factor of 100 would look like a
catastrophic calibration error and be a units bug, which is the most likely thing
to be wrong here and the easiest to mistake for a finding.

This is a **script and not an engine**. See `context/architecture-context.md`,
"Two records, two writers": the archive has one writer and the store has one
writer, and anything reading across that boundary reads both and writes neither.

## What it reads, and the contract that is not yet met

The archive side works today, from `data/summaries/` (tier 2 rows carry
`spread_bps` directly) and from `data/raw/` (tier 1 book frames, from which the
spread is computed here the same way the summariser computes it).

The daemon side reads `logs/acsoe.jsonl` for the quote engine 3 published.
**Engine 3 does not currently log one.** It publishes
`state["market_sensor"]["quotes"][pair]["spread_pct"]` every tick and that value
never reaches the log, so there is nothing to compare against and this script says
so rather than reporting a distribution of nothing. The contract it wants is one
line per tick:

    {"event": "market_sensor_quotes",
     "quotes": {"BTC/USD": {"bid": "...", "ask": "...", "spread_pct": "0.00021"}},
     "run_id": "...", "cycle_id": 41, "ts": "2026-09-11T16:44:00.000000Z"}

One line a tick is 1,440 lines a day, which is nothing beside 17 GB of recording,
and it is the only way this comparison can ever be made after the fact — the live
quote is not written anywhere else, and like the order book it cannot be
reconstructed later.

Usage::

    python scripts/reconcile_spread.py --hours 24
    python scripts/reconcile_spread.py --from 2026-09-10T00:00:00Z --to 2026-09-11T00:00:00Z
    python scripts/reconcile_spread.py --pair BTC/USD --json
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

DEFAULT_ARCHIVE_DIR: Final = Path("data") / "raw"
DEFAULT_SUMMARY_DIR: Final = Path("data") / "summaries"
DEFAULT_LOG: Final = Path("logs") / "acsoe.jsonl"

CONFIG_CANDIDATES: Final = (
    Path("config") / "recorder.yaml",
    Path("config") / "default.yaml",
)
CONFIG_SECTION: Final = "recorder"

#: The log event this script wants.
QUOTES_EVENT: Final = "market_sensor_quotes"

#: How far from a daemon quote an archive observation may be and still be paired
#: with it. 60s because tier 2 is a one-minute bucket, so a tighter window would
#: throw away every tier 2 comparison; tier 1 pairs are reported with their own
#: measured offsets so the tighter matching there is visible rather than assumed.
DEFAULT_MATCH_WINDOW_S: Final = 60.0

DEFAULT_HOURS: Final = 24.0

BPS: Final = 10_000.0


class Observation:
    """One spread measurement, from either side, in basis points.

    Not a ``@dataclass`` — ``scripts/`` is loaded by path in the tests and the
    decorator raises at import there. See ``PairStat`` in ``scripts/record.py``.
    """

    __slots__ = ("pair", "source", "spread_bps", "ts")

    def __init__(self, *, pair: str, ts: float, spread_bps: float, source: str) -> None:
        self.pair = pair
        self.ts = ts
        self.spread_bps = spread_bps
        self.source = source


# --------------------------------------------------------------------------- #
# Times
# --------------------------------------------------------------------------- #


def parse_iso(value: str) -> float | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def window_from_args(args: argparse.Namespace) -> tuple[float, float]:
    """``(start, end)`` as epoch seconds.

    `--from`/`--to` win over `--hours`. An explicit window is what makes a report
    reproducible, and a report that silently means "the last 24 hours from
    whenever you happened to run it" cannot be quoted in a dissertation.
    """
    end = parse_iso(args.window_to) if args.window_to else datetime.now(UTC).timestamp()
    if end is None:
        raise ValueError(f"--to {args.window_to!r} is not an ISO-8601 UTC timestamp")
    if args.window_from:
        start = parse_iso(args.window_from)
        if start is None:
            raise ValueError(f"--from {args.window_from!r} is not an ISO-8601 UTC timestamp")
    else:
        start = end - args.hours * 3600.0
    if start >= end:
        raise ValueError("the window starts at or after it ends")
    return start, end


# --------------------------------------------------------------------------- #
# The recorder's side
# --------------------------------------------------------------------------- #


def read_summary_spreads(
    directory: Path, *, start: float, end: float, pairs: set[str] | None
) -> list[Observation]:
    """Tier 2: one median spread per pair per minute, already in basis points.

    The **p50** is taken and not the p25 or the p75, because the daemon's quote is
    a single observation and the median is the stored statistic closest in kind to
    one. The p25/p75 are still worth having and are not used here: they describe
    the width of the minute, which is a different question from where its centre
    sat.
    """
    found: list[Observation] = []
    for path in sorted(directory.glob("*.jsonl")):
        if not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                for raw in handle:
                    if b'"summary"' not in raw:
                        continue
                    try:
                        row = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(row, dict) or row.get("kind") != "summary":
                        continue
                    pair = row.get("pair")
                    if not isinstance(pair, str) or (pairs and pair not in pairs):
                        continue
                    ts = parse_iso(str(row.get("minute", "")))
                    if ts is None or not start <= ts <= end:
                        continue
                    spread = row.get("spread_bps")
                    if not isinstance(spread, list) or len(spread) != 3:
                        continue
                    median = spread[1]
                    if not isinstance(median, (int, float)):
                        continue
                    # A minute with no usable spread sample stores [0,0,0]. That is
                    # "no observation", not "a zero spread", and averaging it in
                    # would drag every statistic here toward zero.
                    if row.get("samples", 0) <= 0:
                        continue
                    found.append(
                        Observation(
                            pair=pair,
                            ts=ts,
                            spread_bps=float(median),
                            source="tier2_minute_median",
                        )
                    )
        except OSError:
            continue
    return found


def read_raw_spreads(
    directory: Path, *, start: float, end: float, pairs: set[str] | None
) -> list[Observation]:
    """Tier 1: the spread at the instant of a book frame, computed here.

    Only frames that carry both a top bid and a top ask are usable. A one-sided or
    crossed book is skipped rather than recorded as a spread of zero or a negative
    one — the same rule the summariser applies, for the same reason.

    This reads whole archive files, which are gigabytes. It is therefore bounded
    to the window by the filename's date before anything is parsed.
    """
    found: list[Observation] = []
    window_days = {
        datetime.fromtimestamp(moment, tz=UTC).strftime("%Y-%m-%d")
        for moment in (start, end, (start + end) / 2)
    }
    for path in sorted(directory.glob("*.jsonl")):
        if not path.is_file():
            continue
        if not any(day in path.name for day in window_days):
            continue
        try:
            with path.open("rb") as handle:
                for raw in handle:
                    if b'"book"' not in raw:
                        continue
                    try:
                        line = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(line, dict) or line.get("channel") != "book":
                        continue
                    pair = line.get("pair")
                    if not isinstance(pair, str) or (pairs and pair not in pairs):
                        continue
                    ts = parse_iso(str(line.get("ts_recv", "")))
                    if ts is None or not start <= ts <= end:
                        continue
                    spread = top_of_book_spread_bps(line.get("payload"))
                    if spread is None:
                        continue
                    found.append(
                        Observation(pair=pair, ts=ts, spread_bps=spread, source="tier1_instant")
                    )
        except OSError:
            continue
    return found


def top_of_book_spread_bps(payload: object) -> float | None:
    """`(ask - bid) / mid * 10000` from a Kraken v2 book frame, or None.

    Only a *snapshot* carries a full book; a delta carries changed levels, so the
    best bid in a delta is not necessarily the best bid in the book. Deltas are
    skipped rather than read optimistically — a spread computed from two changed
    levels is not a spread, and it would be indistinguishable from a real one in
    the output.
    """
    if not isinstance(payload, dict) or payload.get("type") != "snapshot":
        return None
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    entry = data[0]
    if not isinstance(entry, dict):
        return None
    bid = _best(entry.get("bids"), highest=True)
    ask = _best(entry.get("asks"), highest=False)
    if bid is None or ask is None or ask <= bid:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0.0:
        return None
    return (ask - bid) / mid * BPS


def _best(levels: object, *, highest: bool) -> float | None:
    if not isinstance(levels, list) or not levels:
        return None
    prices = [
        float(level["price"])
        for level in levels
        if isinstance(level, dict)
        and isinstance(level.get("price"), (int, float))
        and isinstance(level.get("qty"), (int, float))
        and level["qty"] > 0
    ]
    if not prices:
        return None
    return max(prices) if highest else min(prices)


# --------------------------------------------------------------------------- #
# The daemon's side
# --------------------------------------------------------------------------- #


def read_daemon_spreads(
    log_path: Path, *, start: float, end: float, pairs: set[str] | None
) -> tuple[list[Observation], int]:
    """``(observations, lines scanned)`` from the daemon's structured log."""
    found: list[Observation] = []
    scanned = 0
    if not log_path.is_file():
        return found, 0
    try:
        with log_path.open("rb") as handle:
            for raw in handle:
                scanned += 1
                try:
                    line = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(line, dict):
                    continue
                quotes = line.get("quotes")
                if not isinstance(quotes, dict):
                    continue
                ts = parse_iso(str(line.get("ts", "")))
                if ts is None or not start <= ts <= end:
                    continue
                for pair, quote in quotes.items():
                    if not isinstance(pair, str) or (pairs and pair not in pairs):
                        continue
                    spread = _spread_bps_of(quote)
                    if spread is None:
                        continue
                    found.append(
                        Observation(pair=pair, ts=ts, spread_bps=spread, source="daemon")
                    )
    except OSError:
        return found, scanned
    return found, scanned


def _spread_bps_of(quote: object) -> float | None:
    """A quote's spread in basis points, from whichever field it carries.

    `spread_pct` in `engines/market_sensor/contracts.py` is `(ask - bid) / mid` as
    a **decimal ratio**, not a percentage, despite the name — so it is multiplied
    by 10,000 and not by 100. Getting that wrong is the single most likely bug in
    this file, and it would present as a 100x calibration error rather than as an
    exception, so the conversion happens in one place with this note on it.

    `spread_pct` may legitimately be negative: a crossed book is a real thing a
    feed produces, and engine 3 publishes it rather than clamping it. It is kept
    here, because a systematically crossed feed is a finding.
    """
    if not isinstance(quote, dict):
        return None
    ratio = quote.get("spread_pct")
    if isinstance(ratio, str):
        try:
            ratio = float(ratio)
        except ValueError:
            ratio = None
    if isinstance(ratio, (int, float)):
        return float(ratio) * BPS
    bid, ask = quote.get("bid"), quote.get("ask")
    try:
        bid_f, ask_f = float(bid), float(ask)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    mid = (bid_f + ask_f) / 2.0
    if mid <= 0.0:
        return None
    return (ask_f - bid_f) / mid * BPS


# --------------------------------------------------------------------------- #
# The comparison
# --------------------------------------------------------------------------- #


def match(
    daemon: list[Observation], archive: list[Observation], *, window_s: float
) -> list[tuple[Observation, Observation, float]]:
    """Pair each daemon quote with the nearest archive observation of the same pair.

    Nearest in time rather than "the one before", because an archive observation a
    second after the quote is a better estimate of the same book than one fifty
    seconds before it, and preferring the earlier one would build a systematic lag
    into the very statistic being measured.
    """
    by_pair: dict[str, list[Observation]] = {}
    for item in archive:
        by_pair.setdefault(item.pair, []).append(item)
    for items in by_pair.values():
        items.sort(key=lambda item: item.ts)

    matched: list[tuple[Observation, Observation, float]] = []
    for quote in daemon:
        candidates = by_pair.get(quote.pair)
        if not candidates:
            continue
        stamps = [item.ts for item in candidates]
        index = bisect.bisect_left(stamps, quote.ts)
        best: Observation | None = None
        best_gap = window_s
        for offset in (index - 1, index):
            if 0 <= offset < len(candidates):
                gap = abs(candidates[offset].ts - quote.ts)
                if gap <= best_gap:
                    best, best_gap = candidates[offset], gap
        if best is not None:
            matched.append((quote, best, best_gap))
    return matched


def distribution(values: list[float]) -> dict[str, float]:
    """Count, mean, standard deviation and five quantiles.

    Quantiles as well as a mean because the shape is the finding. A mean of zero
    over a wide symmetric spread is two observers of one book disagreeing by
    timing, which is expected and harmless; a mean of three basis points over a
    narrow one is a calibration error that moves every cost-gate verdict the same
    way. A mean alone cannot tell those apart.
    """
    if not values:
        return {}
    ordered = sorted(values)
    count = len(ordered)
    mean = sum(ordered) / count
    variance = sum((value - mean) ** 2 for value in ordered) / count if count > 1 else 0.0
    return {
        "count": float(count),
        "mean": mean,
        "stdev": math.sqrt(variance),
        "min": ordered[0],
        "p05": _quantile(ordered, 0.05),
        "p25": _quantile(ordered, 0.25),
        "p50": _quantile(ordered, 0.50),
        "p75": _quantile(ordered, 0.75),
        "p95": _quantile(ordered, 0.95),
        "max": ordered[-1],
    }


def _quantile(ordered: list[float], q: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def analyse(
    matched: list[tuple[Observation, Observation, float]],
) -> dict[str, Any]:
    """Differences in basis points, split by archive tier and by pair.

    Split by tier because a tier 2 comparison carries a known approximation — the
    archive value is a minute median, not the value at the instant — and a tier 1
    comparison does not. Reporting them together would let the approximation in the
    one contaminate the conclusion about the other.
    """
    by_source: dict[str, list[float]] = {}
    by_pair: dict[str, list[float]] = {}
    gaps: list[float] = []
    for quote, observed, gap in matched:
        difference = quote.spread_bps - observed.spread_bps
        by_source.setdefault(observed.source, []).append(difference)
        by_pair.setdefault(quote.pair, []).append(difference)
        gaps.append(gap)
    return {
        "overall": distribution([d for values in by_source.values() for d in values]),
        "by_source": {source: distribution(values) for source, values in sorted(by_source.items())},
        "by_pair": {pair: distribution(values) for pair, values in sorted(by_pair.items())},
        "match_gap_s": distribution(gaps),
    }


def interpret(stats: dict[str, float]) -> str:
    """One sentence on what the shape means. Deliberately cautious.

    It says what the numbers are consistent with, never what they prove. A
    calibration conclusion drawn from one window of one market is not a finding,
    and this script is a instrument rather than a verdict.
    """
    if not stats:
        return "no matched observations, so nothing can be said."
    mean = stats["mean"]
    stdev = stats["stdev"]
    count = int(stats["count"])
    # Standard error of the mean: with enough samples a small bias is real, and
    # with few samples a large one is not.
    stderr = stdev / math.sqrt(count) if count > 1 else float("inf")
    if stdev > 0 and abs(mean) < 2 * stderr:
        return (
            f"mean {mean:+.3f} bps is within 2 standard errors ({stderr:.3f}) of zero over "
            f"{count} observations: consistent with timing noise between two observers of "
            f"one book, not with a calibration offset."
        )
    return (
        f"mean {mean:+.3f} bps against a standard error of {stderr:.3f} over {count} "
        f"observations: a systematic difference, not noise. The daemon quotes "
        f"{'wider' if mean > 0 else 'tighter'} than the archive by roughly "
        f"{abs(mean):.2f} bps, which shifts every cost-gate verdict the same way."
    )


# --------------------------------------------------------------------------- #
# Config and wiring
# --------------------------------------------------------------------------- #


def load_recorder_config(explicit: Path | None = None) -> dict[str, Any]:
    """The ``recorder:`` mapping, or ``{}``. Duplicated from `record.py`, which has
    to stay copyable to a bare server on its own."""
    if explicit is not None and not explicit.is_file():
        raise FileNotFoundError(f"--config {explicit} does not exist")
    try:
        import yaml  # optional
    except ImportError:
        if explicit is not None:
            raise
        return {}
    here = Path(__file__).resolve().parent.parent
    searched = (
        [explicit]
        if explicit is not None
        else [base / candidate for base in (Path.cwd(), here) for candidate in CONFIG_CANDIDATES]
    )
    for path in searched:
        if not path.is_file():
            continue
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get(CONFIG_SECTION), dict):
            return dict(loaded[CONFIG_SECTION])
    return {}


def _config_str(config: dict[str, Any], key: str) -> str | None:
    value = config.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _iso(moment: float) -> str:
    return datetime.fromtimestamp(moment, tz=UTC).isoformat().replace("+00:00", "Z")


def _fmt(stats: dict[str, float]) -> str:
    if not stats:
        return "    (no observations)"
    return (
        f"    n={int(stats['count'])}  mean {stats['mean']:+.3f}  sd {stats['stdev']:.3f}  "
        f"p05 {stats['p05']:+.3f}  p25 {stats['p25']:+.3f}  p50 {stats['p50']:+.3f}  "
        f"p75 {stats['p75']:+.3f}  p95 {stats['p95']:+.3f}"
    )


def run(args: argparse.Namespace) -> int:
    config = load_recorder_config(Path(args.config) if args.config else None)
    archive_dir = Path(args.archive or _config_str(config, "archive_dir") or DEFAULT_ARCHIVE_DIR)
    summary_dir = Path(args.summaries or _config_str(config, "summary_dir") or DEFAULT_SUMMARY_DIR)
    log_path = Path(args.log)
    start, end = window_from_args(args)
    pairs = set(args.pair) if args.pair else None

    daemon, scanned = read_daemon_spreads(log_path, start=start, end=end, pairs=pairs)

    print(f"window    {_iso(start)} -> {_iso(end)}  ({(end - start) / 3600:.1f}h)")
    print(f"archive   {archive_dir}")
    print(f"summaries {summary_dir}")
    print(f"log       {log_path}  ({scanned} lines scanned)")

    if not daemon:
        print(
            "\nNO LIVE SPREAD FOUND IN THE DAEMON'S LOG.\n"
            f"  Nothing in {log_path} carries a `quotes` mapping. Engine 3 computes\n"
            "  state['market_sensor']['quotes'][pair]['spread_pct'] every tick and never\n"
            "  logs it, so there is nothing to compare the archive against.\n"
            "\n"
            "  This is NOT a clean result. It is the absence of one, and it is the more\n"
            "  urgent finding of the two: the live quote is written nowhere else, so\n"
            "  every tick that passes without it is a comparison that can never be made\n"
            "  afterwards - the same property that makes the order book unbackfillable.\n"
            "\n"
            f"  The contract this script reads is one line per tick:\n"
            f'    {{"event": "{QUOTES_EVENT}", "quotes": {{"BTC/USD": {{"spread_pct": "0.00021"}}}},\n'
            f'     "run_id": "...", "cycle_id": 41, "ts": "..."}}\n'
            "  1,440 lines a day, against 17 GB of recording."
        )
        return 1

    archive = read_summary_spreads(summary_dir, start=start, end=end, pairs=pairs)
    if not args.no_tier1:
        archive += read_raw_spreads(archive_dir, start=start, end=end, pairs=pairs)

    if not archive:
        print("\nno archive observations in this window. Was the recorder running?")
        return 1

    matched = match(daemon, archive, window_s=args.match_window_s)
    result = analyse(matched)
    result["window"] = {"from": _iso(start), "to": _iso(end)}
    result["daemon_observations"] = len(daemon)
    result["archive_observations"] = len(archive)
    result["matched"] = len(matched)
    result["unmatched_daemon"] = len(daemon) - len(matched)
    result["interpretation"] = interpret(result["overall"])

    if args.json:
        print(json.dumps(result, indent=2, default=float))
        return 0

    print(
        f"\n{len(daemon)} daemon quotes, {len(archive)} archive observations, "
        f"{len(matched)} matched within {args.match_window_s:.0f}s "
        f"({len(daemon) - len(matched)} daemon quotes had no archive observation nearby)"
    )
    print("\ndifference = daemon spread - archive spread, in basis points\n")
    print("  overall")
    print(_fmt(result["overall"]))
    for source, stats in result["by_source"].items():
        print(f"\n  {source}")
        print(_fmt(stats))
    if len(result["by_pair"]) > 1 or args.pair:
        print("\n  by pair")
        for pair, stats in result["by_pair"].items():
            print(f"    {pair}")
            print(_fmt(stats))
    print(f"\n  time between matched observations (s)\n{_fmt(result['match_gap_s'])}")
    print(f"\n{result['interpretation']}")
    if "tier2_minute_median" in result["by_source"]:
        print(
            "\n  Note on tier 2: those archive values are minute MEDIANS, not the spread at\n"
            "  the instant of the quote. A difference there is part approximation by\n"
            "  construction and is not on its own evidence of a calibration error."
        )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="reconcile_spread.py",
        description=(
            "Compare the spread recorded in the archive against the spread the daemon "
            "published live, and report the distribution of the difference. Reads both; "
            "writes neither."
        ),
    )
    parser.add_argument("--archive", default=None, help="tier 1 archive directory")
    parser.add_argument("--summaries", default=None, help="tier 2 summary directory")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="the daemon's structured log")
    parser.add_argument("--pair", nargs="+", default=None, help="restrict to these pairs")
    parser.add_argument(
        "--hours",
        type=float,
        default=DEFAULT_HOURS,
        help="window length ending now, unless --from/--to are given",
    )
    parser.add_argument("--from", dest="window_from", default=None, help="ISO-8601 UTC")
    parser.add_argument("--to", dest="window_to", default=None, help="ISO-8601 UTC")
    parser.add_argument(
        "--match-window-s",
        type=float,
        default=DEFAULT_MATCH_WINDOW_S,
        help="how far apart a quote and an archive observation may be and still pair",
    )
    parser.add_argument(
        "--no-tier1",
        action="store_true",
        help="skip the raw archive, which is gigabytes, and compare against tier 2 only",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--config", default=None, help="config file carrying a `recorder:` mapping"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except ValueError as exc:
        print(f"\n{exc}\n")
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
