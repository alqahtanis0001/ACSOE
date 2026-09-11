#!/usr/bin/env python
"""Build `tests/fixtures/kraken/ohlc.json` from a real recording.

    python scripts/ohlc_fixture.py --from 2026-09-09T03:00:00Z --bars 3 --write

The fixture holds, per pair, the **real recorded trades** and the OHLCV those trades
imply. `candles_match_kraken_ohlc` feeds the trades to
`acsoe.engines.market_sensor.candles.build_candles` and compares the result against the
`ohlc` half, within one `tick_size` read from `AssetPairs` and 0.1% on volume.

Two things about the honesty of this artefact, stated here because the next reader will
otherwise assume more than it delivers.

**The trades are real.** They are Kraken v2 `trade` frames off the live socket, taken
verbatim out of `data/raw/`. Nothing is synthesised and nothing is smoothed.

**The `ohlc` half is a reference computation, not Kraken's own published OHLC.**
`scripts/record.py` subscribes to `book`, `ticker` and `trade`, so the archive contains
no OHLC channel to compare against, and no live call can be made — the operator has
rotated the key. So the expected values are computed **here**, by the deliberately
naive pure-Python reduction in :func:`reference_ohlc`, which shares no code with the
`polars` implementation under test. That is not the same as an independent source and
it is weaker than one: both are mine. It catches a bug in the `polars` bucketing,
grouping or Decimal handling — which is what the criterion is actually for — and it
cannot catch a shared misunderstanding of what a candle is. Confirming these bars
against Kraken's published OHLC is a `--live` task.

**Duplicate frames are dropped, duplicate trades are not.** Two `record.py` processes
ran concurrently from 2026-09-09T13:19:34Z, so part of the archive contains each frame
twice. De-duplication is at the **frame** level and by exact bytes: two recorders
produce byte-identical frames, whereas two genuinely identical trades arrive inside one
frame, not two. De-duplicating at the *trade* level would silently delete real volume.
The recording itself is never edited — invariant 11 — this happens on the way into the
derived artefact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DEFAULT_RAW_DIR = Path("data") / "raw"
DEFAULT_OUT = Path("tests") / "fixtures" / "kraken" / "ohlc.json"
DEFAULT_PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD")
DEFAULT_INTERVAL_S = 900


def parse_iso(text: str) -> int:
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.astimezone(UTC).timestamp())


def reference_ohlc(
    trades: list[dict[str, Any]], *, interval_s: int
) -> list[dict[str, Any]]:
    """The expected candles, computed the dumbest way that can be right.

    One pass, a plain dict, `Decimal` arithmetic, no dataframe. It shares no code with
    `engines/market_sensor/candles.py`, which is the only reason comparing them is
    worth anything.
    """
    bars: dict[int, dict[str, Any]] = {}
    for trade in trades:
        bucket = (int(trade["ts"]) // interval_s) * interval_s
        price = Decimal(str(trade["price"]))
        qty = Decimal(str(trade["qty"]))
        bar = bars.get(bucket)
        if bar is None:
            bars[bucket] = {
                "ts": bucket,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": qty,
                "trades": 1,
            }
            continue
        bar["high"] = max(bar["high"], price)
        bar["low"] = min(bar["low"], price)
        bar["close"] = price
        bar["volume"] = bar["volume"] + qty
        bar["trades"] = int(bar["trades"]) + 1
    return [
        {
            "ts": bar["ts"],
            "open": str(bar["open"]),
            "high": str(bar["high"]),
            "low": str(bar["low"]),
            "close": str(bar["close"]),
            "volume": str(bar["volume"]),
            "trades": bar["trades"],
        }
        for bar in sorted(bars.values(), key=lambda item: int(item["ts"]))
    ]


def collect(
    paths: list[Path],
    *,
    pairs: tuple[str, ...],
    start_s: int,
    end_s: int,
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Real trades for each pair inside ``[start_s, end_s)``, and the duplicate count."""
    collected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    duplicates = 0
    wanted = set(pairs)

    for path in sorted(paths):
        with path.open("rb") as handle:
            for raw in handle:
                stripped = raw.strip()
                if not stripped or b'"trade"' not in stripped:
                    continue
                try:
                    line = json.loads(stripped)
                except ValueError:
                    continue
                if line.get("kind") != "tick" or line.get("channel") != "trade":
                    continue
                payload = line.get("payload")
                if not isinstance(payload, dict):
                    continue

                digest = hashlib.sha256(
                    json.dumps(payload, sort_keys=True).encode()
                    + str(line.get("ts_exchange")).encode()
                ).hexdigest()
                if digest in seen:
                    duplicates += 1
                    continue
                seen.add(digest)

                for item in payload.get("data") or []:
                    if not isinstance(item, dict):
                        continue
                    symbol = item.get("symbol")
                    stamp = item.get("timestamp")
                    if symbol not in wanted or not isinstance(stamp, str):
                        continue
                    try:
                        seconds = parse_iso(stamp)
                    except ValueError:
                        continue
                    if not (start_s <= seconds < end_s):
                        continue
                    collected[str(symbol)].append(
                        {
                            "pair": str(symbol),
                            "ts": seconds,
                            "price": str(item["price"]),
                            "qty": str(item["qty"]),
                        }
                    )
    return dict(collected), duplicates


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ohlc_fixture.py",
        description="Build tests/fixtures/kraken/ohlc.json from a real recording.",
    )
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--pairs", nargs="+", default=list(DEFAULT_PAIRS))
    parser.add_argument("--interval-s", type=int, default=DEFAULT_INTERVAL_S)
    parser.add_argument("--from", dest="start", required=True, help="ISO-8601 UTC")
    parser.add_argument("--bars", type=int, default=3)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    interval = args.interval_s
    start = (parse_iso(args.start) // interval) * interval
    end = start + interval * args.bars

    paths = sorted(Path(args.raw_dir).glob("*.jsonl"))
    if not paths:
        print(f"no recording found in {args.raw_dir}", file=sys.stderr)
        return 2

    collected, duplicates = collect(
        paths, pairs=tuple(args.pairs), start_s=start, end_s=end
    )
    missing = [pair for pair in args.pairs if not collected.get(pair)]
    if missing:
        print(f"no trades recorded for {missing} in that window", file=sys.stderr)
        return 1

    fixture: dict[str, Any] = {
        "schema_version": 1,
        "interval_s": interval,
        "window": {
            "start": start,
            "end": end,
            "start_iso": datetime.fromtimestamp(start, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z"),
        },
        "provenance": (
            "Trades are real Kraken WebSocket v2 `trade` frames taken verbatim from "
            "data/raw/. The `ohlc` half is a reference computation by "
            "scripts/ohlc_fixture.py's naive pure-Python reduction, NOT Kraken's own "
            "published OHLC — the archive carries no OHLC channel and no live call can "
            "be made. It shares no code with the polars implementation under test. "
            "Confirming these bars against Kraken's published OHLC is a --live task."
        ),
        "frame_duplicates_dropped": duplicates,
        "pairs": {},
    }
    for pair in args.pairs:
        trades = collected[pair]
        fixture["pairs"][pair] = {
            "trades": trades,
            "ohlc": reference_ohlc(trades, interval_s=interval),
        }
        print(
            f"{pair}: {len(trades)} trades -> {len(fixture['pairs'][pair]['ohlc'])} bars",
            file=sys.stderr,
        )
    print(f"frame duplicates dropped: {duplicates}", file=sys.stderr)

    if not args.write:
        return 0
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # `newline="\n"` is load-bearing here and nowhere more than here. `write_text` opens
    # in TEXT mode and text mode on Windows turns every `\n` into `\r\n`, and
    # `json.dumps(..., indent=1)` is one newline per line — so a bare call rewrote all
    # 12,094 of them. `tests/fixtures/**` is `-text` in `.gitattributes`, deliberately,
    # so there is no clean filter to normalise it on the way into the index: unlike
    # everywhere else in this repository, a text-mode write here changes the **committed
    # bytes**. Found 2026-09-11 by C, after my own audit missed it by using `grep`.
    out.write_text(json.dumps(fixture, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KiB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
