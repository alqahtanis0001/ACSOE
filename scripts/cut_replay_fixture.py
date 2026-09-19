"""Cut one replayed day out of the weekly trade partitions, as a committed fixture.

Spec 142 step 1. The rehearsal of one day, and spec 141's pipeline criterion after it,
need the day's trades to be on a fresh clone. `data/derived/` is gitignored, so the slice
is copied into `tests/fixtures/phase7/rehearsal_<day>/` (not the declared-scenario
fixture directory, D17), in the partition layout spec 128 defines. The replay client then reads it exactly as it reads the full partitions.

**What is cut.** Every pair's trades from `--from` up to the end of the day, taken byte
for byte from the partitions (the text of price and volume is never re-parsed). `--from`
is the lookback the replay client needs before the day's first tick: engine 3 publishes
`market_sensor.published_bars` closed bars, and the client serves a window of that many
bars ending at the tick. For the first tick of the day that reaches 50 hours back.

**What is written.**
- One parquet per pair per partition week that holds any of the slice.
- A `manifest.json` in spec 128's shape: per pair, the rows per week and the sha256 of each
  source partition it was cut from.
- The source manifest's sha256 and the cut's bounds, so a reader can check the slice
  against the partitions it came from.

Nothing is filled, resampled or interpolated. A pair with no trade in the slice has no
file and is listed with zero rows.

Read-only on `data/`. It refuses to overwrite an existing fixture directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

DEFAULT_SOURCE = Path("data") / "derived" / "trades_weekly"
DEFAULT_OUT = Path("tests") / "fixtures" / "phase7"
WEEK = timedelta(days=7)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc(text: str) -> datetime:
    moment = datetime.fromisoformat(text)
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def cut(source: Path, out: Path, *, start: datetime, end: datetime) -> dict[str, Any]:
    """Copy every row with `start <= ts < end` into `out`, in the partition layout."""
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    weeks = [datetime.fromisoformat(week).replace(tzinfo=UTC) for week in manifest["week_starts"]]
    touched = [week for week in weeks if week < end and week + WEEK > start]
    if not touched or touched[0] > start:
        raise SystemExit(f"the partitions do not reach back to {start.isoformat()}")
    if out.exists():
        raise SystemExit(f"{out} exists; a fixture is written once")
    out.mkdir(parents=True)
    lo, hi = int(start.timestamp()), int(end.timestamp())
    pairs: dict[str, Any] = {}
    total = 0
    for pair in sorted(manifest["pairs"]):
        counts: dict[str, int] = {}
        sources: dict[str, str] = {}
        for week in touched:
            label = week.strftime("%Y-%m-%d")
            path = source / pair / f"{label}.parquet"
            if not path.is_file():
                counts[label] = 0
                continue
            frame = pl.read_parquet(path).filter((pl.col("ts") >= lo) & (pl.col("ts") < hi))
            counts[label] = frame.height
            if frame.height:
                (out / pair).mkdir(exist_ok=True)
                frame.write_parquet(out / pair / f"{label}.parquet", compression="zstd")
                sources[label] = sha256_file(path)
        if sum(counts.values()):
            pairs[pair] = {"weeks": counts, "total_rows": sum(counts.values()), "source_sha256": sources}
            total += sum(counts.values())
    written = {
        "schema_version": 1,
        "cut_by": "scripts/cut_replay_fixture.py",
        "script_sha256": sha256_file(Path(__file__)),
        "cut_from": {"manifest": manifest_path.as_posix(), "sha256": sha256_file(manifest_path)},
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "week_starts": [week.strftime("%Y-%m-%d") for week in touched],
        "columns": manifest["columns"],
        "row_order": manifest["row_order"],
        "total_rows": total,
        "pairs": pairs,
    }
    # Bytes, not text mode: the fixture directory is `-text` in `.gitattributes`, so a
    # Windows text-mode write would commit CRLF line endings (code-standards.md).
    (out / "manifest.json").write_bytes(json.dumps(written, indent=1, sort_keys=True).encode("utf-8"))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cut_replay_fixture.py", description=__doc__.split("\n")[0])
    parser.add_argument("--day", required=True, help="the replayed UTC day, YYYY-MM-DD")
    parser.add_argument("--lookback-hours", type=float, default=51.0,
                        help="history before the day's first bar, at least published_bars bars")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    day = _utc(args.day)
    start = day - timedelta(hours=args.lookback_hours)
    end = day + timedelta(days=1, seconds=1)
    out = args.out or DEFAULT_OUT / f"rehearsal_{day:%Y-%m-%d}"
    written = cut(args.source, out, start=start, end=end)
    print(f"cut {written['total_rows']} rows over {len(written['pairs'])} pairs into {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
