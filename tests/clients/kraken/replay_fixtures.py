"""Fabricated replay scenarios for the replay client's and the driver's tests.

Everything here is **invented test data** in the shapes agreed with a-data by message
(specs 127, 128 and 130): a v2 `instrument` snapshot and a REST `AssetPairs` capture, a
bucket table, and weekly trade partitions with their manifest. The fee schedule is the
real committed fixture, because it exists. A test that needs the real rules, table or
partitions says so and uses them.

The contracts these fabricate are the *shapes*, and the code reading them is the real
code: `load_pair_rules`, `load_spread_table` and `TradeTape` are never doubled.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from acsoe.platform.config import Config, derive_config, load_config

REPO = Path(__file__).resolve().parents[3]
FEE_FIXTURE = REPO / "tests" / "fixtures" / "replay" / "kraken_fee_schedule_2026-09-19.json"

#: Saturday 2024-06-29 00:00 UTC: the week before fold 379's test week. The grid every
#: partition sits on.
WEEK_0 = int(datetime(2024, 6, 29, tzinfo=UTC).timestamp())
WEEK_S = 7 * 24 * 60 * 60

#: archive stem -> (REST key, wsname, v2 symbol, base, quote)
PAIRS: Mapping[str, tuple[str, str, str, str, str]] = {
    "XBTUSD": ("XXBTZUSD", "XBT/USD", "BTC/USD", "BTC", "USD"),
    "ETHUSD": ("XETHZUSD", "ETH/USD", "ETH/USD", "ETH", "USD"),
    "THINUSD": ("THINUSD", "THIN/USD", "THIN/USD", "THIN", "USD"),
}

#: The five buckets, in the table's own units. Depths are chosen so the ten levels sit
#: on an exact grid: `depth - spread/2` is nine times a whole number of basis points.
BUCKETS: Sequence[dict[str, Any]] = (
    {"name": "<$10k", "lower_usd": "0", "upper_usd": "10000", "spread_bps": "30.4", "depth_bps": "60.2"},
    {"name": "$10k-100k", "lower_usd": "10000", "upper_usd": "100000", "spread_bps": "25.8", "depth_bps": "39.9"},
    {"name": "$100k-1M", "lower_usd": "100000", "upper_usd": "1000000", "spread_bps": "12.3", "depth_bps": "24.15"},
    {"name": "$1M-10M", "lower_usd": "1000000", "upper_usd": "10000000", "spread_bps": "5.5", "depth_bps": "11.75"},
    {"name": ">$10M", "lower_usd": "10000000", "upper_usd": None, "spread_bps": "5.5", "depth_bps": "11.75",
     "values_from": "$1M-10M"},
)


@dataclass(frozen=True)
class Scenario:
    root: Path
    config: Config


def instrument_snapshot(extra: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    pairs = [
        {"symbol": "BTC/USD", "base": "BTC", "quote": "USD", "status": "online",
         "qty_precision": 8, "price_precision": 1, "qty_min": 0.0001, "cost_min": 0.5,
         "tick_size": 0.1},
        {"symbol": "ETH/USD", "base": "ETH", "quote": "USD", "status": "online",
         "qty_precision": 8, "price_precision": 2, "qty_min": 0.002, "cost_min": 0.5,
         "tick_size": 0.01},
        {"symbol": "THIN/USD", "base": "THIN", "quote": "USD", "status": "online",
         "qty_precision": 2, "price_precision": 4, "qty_min": 10, "cost_min": 0.5,
         "tick_size": 0.0001},
        # Listed in 2026 and absent from the archive: rules, and never a trade.
        {"symbol": "NEW/USD", "base": "NEW", "quote": "USD", "status": "online",
         "qty_precision": 2, "price_precision": 3, "qty_min": 1, "cost_min": 0.5,
         "tick_size": 0.001},
        *extra,
    ]
    return {"channel": "instrument", "type": "snapshot", "data": {"assets": [], "pairs": pairs}}


def asset_pairs() -> dict[str, Any]:
    result = {
        rest: {"altname": archive, "wsname": wsname, "base": base, "quote": "ZUSD"}
        for archive, (rest, wsname, _symbol, base, _quote) in PAIRS.items()
    }
    result["NEWUSD"] = {"altname": "NEWUSD", "wsname": "NEW/USD", "base": "NEW", "quote": "ZUSD"}
    return {"error": [], "result": result}


def spread_table(buckets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """`buckets` in spec 130's committed shape. Bounds and values are JSON numbers, as
    the committed fixture writes them, so the loader's exact-decimal read is exercised."""
    rows: list[dict[str, Any]] = []
    for bucket in buckets:
        row: dict[str, Any] = {
            "bucket": bucket["name"],
            "usd_day_from": float(bucket["lower_usd"]),
            "usd_day_below": None if bucket["upper_usd"] is None else float(bucket["upper_usd"]),
        }
        if "values_from" in bucket:
            row["mapped_to"] = bucket["values_from"]
        else:
            row["spread_bps"] = {"median": float(bucket["spread_bps"]), "q25": 1.0, "q75": 2.0}
            row["depth_bid_bps_to_10k_from_mid"] = {"median": float(bucket["depth_bps"])}
        rows.append(row)
    return {"_provenance": {"statement": "DECLARED, invented test data"}, "buckets": rows}


def captured(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Spec 127's capture shape: the body as text, and its sha256 in the provenance."""
    text = json.dumps(payload)
    return {
        "provenance": {"note": "invented test data", "payload_sha256": hashlib.sha256(text.encode()).hexdigest()},
        "payload": text,
    }


def pair_names() -> dict[str, Any]:
    """Spec 127's recorded name join: archive `altname` to REST key and v2 symbol."""
    joined = {
        archive: {"rest_key": rest, "v2_symbol": symbol}
        for archive, (rest, _wsname, symbol, _base, _quote) in PAIRS.items()
    }
    joined["NEWUSD"] = {"rest_key": "NEWUSD", "v2_symbol": "NEW/USD"}
    return {"provenance": {"note": "invented test data"}, "pairs": joined}


def write_partitions(
    directory: Path, trades: Mapping[str, Sequence[tuple[int, str, str]]], *, weeks: int = 3
) -> None:
    """`trades[archive]` as `(ts, price, volume)` rows, split into Saturday weeks.

    Every archive pair gets a manifest entry for every week, empty weeks listed with 0 and
    no file, exactly as spec 128 describes. Rows keep the order given.
    """
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "window": {
            "first_week": _label(WEEK_0),
            "last_week": _label(WEEK_0 + (weeks - 1) * WEEK_S),
        },
        "pairs": {},
    }
    for archive, rows in trades.items():
        counts: dict[str, int] = {}
        for week in range(weeks):
            start = WEEK_0 + week * WEEK_S
            inside = [row for row in rows if start <= row[0] < start + WEEK_S]
            counts[_label(start)] = len(inside)
            if inside:
                (directory / archive).mkdir(exist_ok=True)
                pl.DataFrame(
                    {
                        "ts": [row[0] for row in inside],
                        "price": [row[1] for row in inside],
                        "volume": [row[2] for row in inside],
                    },
                    schema={"ts": pl.Int64, "price": pl.Utf8, "volume": pl.Utf8},
                ).write_parquet(directory / archive / f"{_label(start)}.parquet")
        manifest["pairs"][archive] = {
            "source": f"{archive}.csv",
            "sha256": "0" * 64,
            "weeks": counts,
            "total_rows": sum(counts.values()),
        }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _label(start: int) -> str:
    return datetime.fromtimestamp(start, UTC).strftime("%Y-%m-%d")


def write_scenario(
    tmp_path: Path,
    trades: Mapping[str, Sequence[tuple[int, str, str]]],
    *,
    tier: int = 3,
    buckets: Sequence[dict[str, Any]] = BUCKETS,
    instrument_extra: Sequence[dict[str, Any]] = (),
    weeks: int = 3,
) -> Scenario:
    """Write every fixture under `tmp_path` and return a real replay-mode `Config`."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("asset_pairs.json", asset_pairs()),
        ("instrument.json", instrument_snapshot(instrument_extra)),
    ):
        (fixtures / name).write_text(json.dumps(captured(payload)), encoding="utf-8")
    (fixtures / "pair_names.json").write_text(json.dumps(pair_names()), encoding="utf-8")
    (fixtures / "table.json").write_text(json.dumps(spread_table(buckets)), encoding="utf-8")
    write_partitions(tmp_path / "partitions", trades, weeks=weeks)
    config = derive_config(
        load_config(REPO / "config" / "default.yaml", load_env=False),
        {
            "mode": "replay",
            "replay": {
                "asset_pairs_file": (fixtures / "asset_pairs.json").as_posix(),
                "instrument_file": (fixtures / "instrument.json").as_posix(),
                "pair_names_file": (fixtures / "pair_names.json").as_posix(),
                "spread_table_file": (fixtures / "table.json").as_posix(),
                "fee_schedule_file": FEE_FIXTURE.as_posix(),
                "fee_tier": tier,
                "partitions_dir": (tmp_path / "partitions").as_posix(),
                "first_fold": 379,
                "last_fold": 379,
                "run_id_format": "test-f{fold}-p7",
            },
        },
    )
    return Scenario(root=tmp_path, config=config)
