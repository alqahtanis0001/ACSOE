#!/usr/bin/env python
"""Build the declared spread-and-depth table by liquidity bucket, for replay. Spec 130.

    python scripts/build_bucket_table.py                      # print the table, write nothing
    python scripts/build_bucket_table.py --write              # also write the fixture

The archive the replay runs on is trades only, so it has no spread and no book. The
operator ruled on 2026-09-19 that both are **declared**, by bucket of the pair's trailing
24-hour dollar volume. The values are read off the recorder's 2026 summaries
(`phase-7-findings.md` §3). This script is how the table is made, and it is the only
source of the fixture the replay client reads.

**A declared value is not a measurement.** Each number here is a median over pairs
recorded in September 2026, applied to every pair in a 2023-24 window, recorded or not.
The fixture says so in its own words, and the interquartile ranges travel with the
medians as the declared uncertainty.

## What it computes, per recorded USD pair

Read-only over `data/summaries/summary*.jsonl`, the recorder's one row per pair per
minute. Only rows up to ``--until`` are used, so a rerun reproduces the same span while
the recorder keeps appending.

- **Spread:** the median of the minute's p50 spread (``spread_bps[1]``), over minutes
  that are schema version 2, ``clean`` and carry at least one sample.
- **Depth:** the median of ``depth_bid_bps`` over those same minutes where the book
  reached $10,000 (``depth_samples > 0``). The recorder defines it as the median
  distance **from the mid**, in bps, at which resting bids first add up to the
  notional.
- **Daily dollar volume:** the pair's summed ``quote_volume`` over every summary row in
  the span, divided by the span in days. The span runs from the first to the last
  minute over all USD rows.

## Per bucket

The buckets are ``<$10k``, ``$10k-100k``, ``$100k-1M``, ``$1M-10M`` and ``>$10M``. Each
reports the median of per-pair medians, its IQR and the pair count, for both spread and
depth.

It also reports a quarter of the median upper bound on slippage, ``depth - spread/2``.
That is the findings' "slippage at $5,000", and it is kept only so the reproduction can
be checked. The replay builds a book from the spread and the depth and lets engine 9
walk it; it never reads this figure.

**The ``>$10M`` bucket is empty in the recording.** BTC, ETH and SOL are recorded as
full books, not summaries. The fixture says so and maps that bucket to the ``$1M-10M``
row. Filling it from the full books instead is a ruling, not a choice made here.

Quantiles are polars' own (``median``; ``quantile`` with its default interpolation), as
in the reconnaissance scripts `q_depth.py` and `q_bucket.py`. That is what makes
reproducing the findings' table an equality, not an approximation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import orjson
import polars as pl

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
SUMMARIES_DIR: Final = Path("data") / "summaries"
FIXTURE_DIR: Final = Path("tests") / "fixtures" / "replay"

#: The span `phase-7-findings.md` §3 was measured over ([T] `q_spread_agg.py`):
#: 2026-09-11 16:13 to 2026-09-19 00:45 UTC. The default end, so a rerun reproduces it.
DEFAULT_UNTIL: Final = "2026-09-19T00:45:00Z"

QUOTE_SUFFIX: Final = "/USD"

#: Bucket edges on trailing 24-hour dollar volume. The lower edge is inclusive.
EDGES: Final = (0.0, 1e4, 1e5, 1e6, 1e7)
LABELS: Final = ("<$10k", "$10k-100k", "$100k-1M", "$1M-10M", ">$10M")

#: The index of the bucket an empty ``>$10M`` bucket borrows from.
EMPTY_TOP_BORROWS_FROM: Final = 3

#: The table `phase-7-findings.md` §3 publishes: pairs, spread, spread IQR, slippage
#: at $5,000, per bucket, to one decimal place. The reproduction check reads this.
FINDINGS_TABLE: Final = {
    "<$10k": (16, 30.4, 12.2, 36.0, 17.7),
    "$10k-100k": (49, 25.8, 11.2, 39.2, 20.8),
    "$100k-1M": (84, 12.3, 7.2, 19.4, 7.5),
    "$1M-10M": (36, 5.5, 2.7, 9.4, 1.7),
}

DECLARED_STATEMENT: Final = (
    "DECLARED, NOT MEASURED. Every value in this table is a median over USD pairs the "
    "recorder summarised over the recording span below, in September 2026. The replay "
    "applies it to every pair in a 2023-24 window, recorded or not, by the pair's own "
    "trailing 24-hour dollar volume. It is a declared scenario value applied to a "
    "different period, never a measurement of that period. The interquartile ranges "
    "are the declared uncertainty of each value. Operator ruling 2026-09-19; "
    "docs/dataset/phase-7-findings.md section 3."
)


class TableError(RuntimeError):
    """A table that cannot be built from the recording. The message names why."""


def parse_minute(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def iter_summary_rows(
    paths: Sequence[Path], *, until: datetime, sources: list[dict[str, Any]]
) -> Iterable[dict[str, Any]]:
    """Every USD ``summary`` row at or before ``until``, one line at a time.

    Appends one provenance entry per file to ``sources``: its name, the bytes read and
    their sha256. The last file is still being appended by the recorder, so the digest
    covers exactly the bytes this run read. A reader re-checks it over that prefix.
    """
    for path in paths:
        digest = hashlib.sha256()
        consumed = 0
        with path.open("rb") as handle:
            for line in handle:
                if not line.endswith(b"\n"):
                    break  # a line the recorder is still writing is not read, or hashed
                digest.update(line)
                consumed += len(line)
                try:
                    row = orjson.loads(line)
                except orjson.JSONDecodeError:
                    continue
                if not isinstance(row, dict) or row.get("kind") != "summary":
                    continue
                if not str(row.get("pair", "")).endswith(QUOTE_SUFFIX):
                    continue
                if parse_minute(str(row["minute"])) > until:
                    continue
                yield row
        sources.append({"file": path.name, "bytes_read": consumed, "sha256": digest.hexdigest()})


def per_pair_frame(rows: Iterable[dict[str, Any]]) -> tuple[pl.DataFrame, datetime, datetime]:
    """Per pair: median spread, median depth, daily dollar volume. And the span."""
    pairs: list[str] = []
    minutes: list[datetime] = []
    quote_volume: list[float] = []
    spread: list[float | None] = []
    depth: list[float | None] = []
    usable: list[bool] = []
    depth_reached: list[bool] = []
    for row in rows:
        pairs.append(str(row["pair"]))
        minutes.append(parse_minute(str(row["minute"])))
        quote_volume.append(float(row.get("quote_volume") or 0.0))
        spreads = row.get("spread_bps") or [None, None, None]
        spread.append(None if spreads[1] is None else float(spreads[1]))
        bid = row.get("depth_bid_bps")
        depth.append(None if bid is None else float(bid))
        usable.append(
            row.get("v") == 2 and bool(row.get("clean")) and int(row.get("samples", 0)) > 0
        )
        depth_reached.append(int(row.get("depth_samples", 0)) > 0)
    if not pairs:
        raise TableError("no USD summary rows in the span")
    first, last = min(minutes), max(minutes)
    days = (last - first).total_seconds() / 86_400
    frame = pl.DataFrame(
        {
            "pair": pairs,
            "quote_volume": quote_volume,
            "spread": spread,
            "depth": depth,
            "usable": usable,
            "depth_reached": depth_reached,
        },
        schema={
            "pair": pl.String,
            "quote_volume": pl.Float64,
            "spread": pl.Float64,
            "depth": pl.Float64,
            "usable": pl.Boolean,
            "depth_reached": pl.Boolean,
        },
    )
    volume = frame.group_by("pair").agg((pl.col("quote_volume").sum() / days).alias("usd_day"))
    usable_rows = frame.filter(pl.col("usable"))
    medians = usable_rows.group_by("pair").agg(
        pl.col("spread").median().alias("spread_med"),
        pl.col("depth").filter(pl.col("depth_reached")).median().alias("depth_med"),
    )
    per = medians.join(volume, on="pair", how="inner").with_columns(
        (pl.col("depth_med") - pl.col("spread_med") / 2).alias("slip_ub")
    )
    return per.sort("pair"), first, last


def bucket_of(usd_day: float) -> int:
    for index in range(len(EDGES) - 1, -1, -1):
        if usd_day >= EDGES[index]:
            return index
    return 0


def bucket_table(per: pl.DataFrame) -> list[dict[str, Any]]:
    per = per.with_columns(
        pl.col("usd_day").map_elements(bucket_of, return_dtype=pl.Int64).alias("bucket")
    )
    rows: list[dict[str, Any]] = []
    for index, label in enumerate(LABELS):
        members = per.filter(pl.col("bucket") == index).sort("pair")
        upper = EDGES[index + 1] if index + 1 < len(EDGES) else None
        row: dict[str, Any] = {
            "bucket": label,
            "usd_day_from": EDGES[index],
            "usd_day_below": upper,
            "pairs": members.height,
            "pair_list": members["pair"].to_list(),
        }
        if members.height:
            depths = members["depth_med"].drop_nulls()
            row["spread_bps"] = {
                "median": members["spread_med"].median(),
                "q25": members["spread_med"].quantile(0.25),
                "q75": members["spread_med"].quantile(0.75),
            }
            row["depth_bid_bps_to_10k_from_mid"] = {
                "median": depths.median(),
                "q25": depths.quantile(0.25),
                "q75": depths.quantile(0.75),
                "pairs_with_depth": depths.len(),
                "pairs_never_reaching_10k": sorted(
                    members.filter(pl.col("depth_med").is_null())["pair"].to_list()
                ),
            }
            row["slippage_5k_bps_check_only"] = (members["slip_ub"] * 0.25).median()
        rows.append(row)
    top = rows[-1]
    if top["pairs"] == 0:
        borrowed = rows[EMPTY_TOP_BORROWS_FROM]
        top["mapped_to"] = borrowed["bucket"]
        top["why"] = (
            "No recorded pair exceeds $10M a day in the summaries, because BTC, ETH and SOL "
            "are recorded as full books rather than as summaries. This bucket takes the "
            f"{borrowed['bucket']} row's values. Filling it from the full books instead "
            "is a ruling, not a choice made by this script."
        )
    return rows


def reproduction(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The table against `phase-7-findings.md` §3, each figure to one decimal place."""
    checks: dict[str, Any] = {}
    for row in rows:
        published = FINDINGS_TABLE.get(row["bucket"])
        if published is None:
            continue
        if not row["pairs"]:
            checks[row["bucket"]] = {"published": published, "computed": None, "equal": False}
            continue
        spread = row["spread_bps"]
        computed = (
            row["pairs"],
            round(spread["median"], 1),
            round(spread["q25"], 1),
            round(spread["q75"], 1),
            round(row["slippage_5k_bps_check_only"], 1),
        )
        checks[row["bucket"]] = {
            "published": list(published),
            "computed": list(computed),
            "equal": tuple(computed) == published,
        }
    return {
        "against": "docs/dataset/phase-7-findings.md section 3: pairs, spread, IQR, slippage at $5k",
        "buckets": checks,
        "all_equal": all(check["equal"] for check in checks.values()),
    }


def build(root: Path, *, until: datetime) -> dict[str, Any]:
    paths = sorted((root / SUMMARIES_DIR).glob("summary*.jsonl"))
    if not paths:
        raise TableError(f"no summary files under {root / SUMMARIES_DIR}")
    sources: list[dict[str, Any]] = []
    per, first, last = per_pair_frame(iter_summary_rows(paths, until=until, sources=sources))
    rows = bucket_table(per)
    script = Path(__file__)
    return {
        "_provenance": {
            "statement": DECLARED_STATEMENT,
            "built_by": "scripts/build_bucket_table.py",
            "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            "recording_span": {
                "first_minute": first.isoformat().replace("+00:00", "Z"),
                "last_minute": last.isoformat().replace("+00:00", "Z"),
                "days": round((last - first).total_seconds() / 86_400, 4),
                "until": until.isoformat().replace("+00:00", "Z"),
            },
            "sources": sources,
            "recorded_usd_pairs": per.height,
            "definitions": {
                "spread_bps": (
                    "per pair, the median over clean, schema-2 minutes with samples of the "
                    "minute's p50 spread; per bucket, the median of those per-pair medians"
                ),
                "depth_bid_bps_to_10k_from_mid": (
                    "per pair, the median over the same minutes where the book reached "
                    "$10,000 of depth_bid_bps: the distance from the mid, in bps, at which "
                    "resting bids first add up to $10,000; per bucket, the median of those"
                ),
                "usd_day": (
                    "the pair's summed quote_volume over every summary row in the span, "
                    "divided by the span in days"
                ),
                "quantiles": "polars median, and polars quantile at its default interpolation",
            },
            "used_by": (
                "the replay client only (spec 129). Never read by the live or paper path."
            ),
        },
        "buckets": rows,
        "reproduction": reproduction(rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_bucket_table.py")
    parser.add_argument("--until", default=DEFAULT_UNTIL)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    until = parse_minute(args.until)
    table = build(REPO_ROOT, until=until)
    for row in table["buckets"]:
        if "spread_bps" in row:
            spread, depth = row["spread_bps"], row["depth_bid_bps_to_10k_from_mid"]
            print(
                f"{row['bucket']:>10}: {row['pairs']:>3} pairs, spread {spread['median']:.1f} "
                f"(IQR {spread['q25']:.1f}-{spread['q75']:.1f}), depth to $10k "
                f"{depth['median']:.1f} (IQR {depth['q25']:.1f}-{depth['q75']:.1f}, "
                f"{depth['pairs_with_depth']} pairs), slippage@$5k "
                f"~{row['slippage_5k_bps_check_only']:.1f}",
                file=sys.stderr,
            )
        else:
            print(f"{row['bucket']:>10}: empty, mapped to {row.get('mapped_to')}", file=sys.stderr)
    print(f"reproduces the findings' table: {table['reproduction']['all_equal']}", file=sys.stderr)
    if not args.write:
        return 0
    stamp = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    target = REPO_ROOT / FIXTURE_DIR / f"spread_book_table_{stamp}.json"
    if target.exists():
        print(f"{target} already exists; a fixture is written once", file=sys.stderr)
        return 1
    target.write_bytes((json.dumps(table, indent=1) + "\n").encode("utf-8"))
    print(f"wrote {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
