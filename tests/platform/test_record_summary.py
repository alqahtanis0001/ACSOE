"""Tier 2 summary rows: price, order flow, realised variance, the health flag,
and the book checksum.

`scripts/record.py` is loaded by path, as `test_record_format.py` does, because
it is a standalone script and must not become a package.

The checksum test replays the committed `record_sample.jsonl` — nine real
ETH/USD book frames Kraken sent on 2026-09-08, each carrying the CRC32 Kraken
computed — through the recorder's own book state and demands that every one
matches. It is the one test here that cannot pass by construction.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PY = REPO_ROOT / "scripts" / "record.py"
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "record_sample.jsonl"

#: ETH/USD's `price_precision` and `qty_precision` from Kraken's `instrument`
#: snapshot on 2026-09-11. Fixture metadata for the replay below, not a value the
#: recorder carries — the recorder reads them off the socket at startup.
ETH_USD_PRECISION = (2, 8)


def _load_record_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_record_script_summary", RECORD_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


record = _load_record_module()

T0 = datetime(2026, 9, 11, 12, 0, 0, tzinfo=UTC)


class Rows:
    """A writer that validates every row the way the real one does, and keeps it."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def write(self, row: dict[str, Any]) -> None:
        record.validate_summary_line(row)
        self.rows.append(row)

    def by_pair(self) -> dict[str, dict[str, Any]]:
        return {row["pair"]: row for row in self.rows}


class Clock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def _summariser(
    rows: Rows,
    clock: Clock,
    *,
    precisions: dict[str, tuple[int, int]] | None = None,
    resubscribe: Any = None,
) -> Any:
    return record.Summariser(
        writer=rows,
        depth=10,
        depth_notional_usd=1_000.0,
        precisions=precisions,
        resubscribe=resubscribe,
        now=clock,
    )


def _book(
    symbol: str,
    *,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    snapshot: bool = False,
    checksum: int | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "symbol": symbol,
        "bids": [{"price": price, "qty": qty} for price, qty in bids],
        "asks": [{"price": price, "qty": qty} for price, qty in asks],
    }
    if checksum is not None:
        entry["checksum"] = checksum
    return {"channel": "book", "type": "snapshot" if snapshot else "update", "data": [entry]}


def _move_mid(symbol: str, old: tuple[float, float], new: tuple[float, float]) -> dict[str, Any]:
    """An update that replaces the single best bid and ask, moving mid."""
    return _book(
        symbol,
        bids=[(old[0], 0.0), (new[0], 1.0)],
        asks=[(old[1], 0.0), (new[1], 1.0)],
    )


def _trade(symbol: str, **fields: Any) -> dict[str, Any]:
    return {"channel": "trade", "type": "update", "data": [{"symbol": symbol, **fields}]}


# --------------------------------------------------------------------------- #
# Price
# --------------------------------------------------------------------------- #


def test_ohlc_of_mid_follows_arrival_order_and_rv_sums_squared_log_changes() -> None:
    rows, clock = Rows(), Clock(T0)
    summariser = _summariser(rows, clock)
    summariser.handle(_book("X/USD", bids=[(99.0, 1.0)], asks=[(101.0, 1.0)], snapshot=True), "")
    summariser.handle(_move_mid("X/USD", (99.0, 101.0), (101.0, 103.0)), "")  # mid 102
    summariser.handle(_move_mid("X/USD", (101.0, 103.0), (97.0, 99.0)), "")  # mid 98
    summariser.handle(_move_mid("X/USD", (97.0, 99.0), (100.0, 102.0)), "")  # mid 101
    summariser.flush_all(clock())

    (row,) = rows.rows
    assert row["v"] == record.SUMMARY_SCHEMA_VERSION
    assert (row["open"], row["high"], row["low"], row["close"]) == (100.0, 102.0, 98.0, 101.0)
    assert row["samples"] == 4
    expected_rv = math.log(102 / 100) ** 2 + math.log(98 / 102) ** 2 + math.log(101 / 98) ** 2
    assert row["rv_samples"] == 3
    assert row["rv"] == pytest.approx(expected_rv, rel=1e-5)
    # Nothing traded: the trade-derived prices are null, not zero.
    assert row["last_trade"] is None and row["vwap"] is None
    assert row["clean"] is True and row["flags"] == []


def test_a_row_with_book_updates_but_no_usable_sample_has_null_prices() -> None:
    rows, clock = Rows(), Clock(T0)
    summariser = _summariser(rows, clock)
    # One-sided book: an update, but no spread and no mid.
    summariser.handle(_book("X/USD", bids=[(99.0, 1.0)], asks=[], snapshot=True), "")
    summariser.flush_all(clock())
    (row,) = rows.rows
    assert row["updates"] == 1 and row["samples"] == 0
    assert row["open"] is row["high"] is row["low"] is row["close"] is None
    assert row["rv"] is None and row["rv_samples"] == 0


# --------------------------------------------------------------------------- #
# Order flow
# --------------------------------------------------------------------------- #


def test_order_flow_is_split_by_taker_side_and_by_order_type() -> None:
    rows, clock = Rows(), Clock(T0)
    summariser = _summariser(rows, clock)
    prints = [
        {"side": "buy", "ord_type": "market", "price": 10.0, "qty": 2.0},
        {"side": "sell", "ord_type": "limit", "price": 12.0, "qty": 1.0},
        {"side": "buy", "ord_type": "limit", "price": 11.0, "qty": 3.0},
        {"side": "sell", "price": 13.0, "qty": 1.0},  # no ord_type
        {"ord_type": "market", "price": 9.0, "qty": 1.0},  # no side
    ]
    for fields in prints:
        summariser.handle(_trade("X/USD", **fields), "")
    summariser.flush_all(clock())

    (row,) = rows.rows
    assert row["trades"] == 5
    assert row["volume"] == 8.0
    assert (row["buy_volume"], row["sell_volume"]) == (5.0, 2.0)
    assert (row["buy_trades"], row["sell_trades"]) == (2, 2)
    assert (row["market_trades"], row["limit_trades"]) == (2, 2)
    assert row["last_trade"] == 9.0
    assert row["vwap"] == pytest.approx((20 + 12 + 33 + 13 + 9) / 8)
    # A print that names no side or type is in `trades` and in neither split —
    # which is why the splits are allowed to fall short of the total.
    assert row["buy_trades"] + row["sell_trades"] < row["trades"]


# --------------------------------------------------------------------------- #
# Realised variance across boundaries
# --------------------------------------------------------------------------- #


def test_rv_carries_the_boundary_return_into_the_next_minute_but_never_across_a_snapshot() -> None:
    rows, clock = Rows(), Clock(T0)
    summariser = _summariser(rows, clock)
    summariser.handle(_book("X/USD", bids=[(99.0, 1.0)], asks=[(101.0, 1.0)], snapshot=True), "")
    summariser.handle(_move_mid("X/USD", (99.0, 101.0), (101.0, 103.0)), "")  # 100 -> 102
    clock.at = T0 + timedelta(minutes=1)
    assert summariser.flush_due(clock()) == 1

    summariser.handle(_move_mid("X/USD", (101.0, 103.0), (103.0, 105.0)), "")  # 102 -> 104
    # A fresh snapshot: the return from 104 to 50 is a seam, not a move.
    summariser.handle(_book("X/USD", bids=[(49.0, 1.0)], asks=[(51.0, 1.0)], snapshot=True), "")
    summariser.handle(_move_mid("X/USD", (49.0, 51.0), (50.0, 52.0)), "")  # 50 -> 51
    summariser.flush_all(clock())

    first, second = rows.rows
    assert first["rv_samples"] == 1
    assert first["rv"] == pytest.approx(math.log(102 / 100) ** 2, rel=1e-5)
    assert second["rv_samples"] == 2
    assert second["rv"] == pytest.approx(math.log(104 / 102) ** 2 + math.log(51 / 50) ** 2, rel=1e-5)
    assert second["flags"] == ["resnapshot"] and second["clean"] is False
    # The sums over minutes are the sum over the hour: nothing double counted,
    # nothing dropped at the boundary.
    assert first["rv_samples"] + second["rv_samples"] == 3


# --------------------------------------------------------------------------- #
# The health flag
# --------------------------------------------------------------------------- #


def test_a_disconnect_flags_every_pair_in_that_minute_and_only_that_minute() -> None:
    rows, clock = Rows(), Clock(T0)
    summariser = _summariser(rows, clock)
    for symbol in ("A/USD", "B/USD"):
        summariser.handle(_book(symbol, bids=[(9.0, 1.0)], asks=[(11.0, 1.0)], snapshot=True), "")
    clock.at = T0 + timedelta(seconds=30)
    summariser.mark("disconnect")
    clock.at = T0 + timedelta(minutes=1)
    summariser.flush_due(clock())
    for symbol in ("A/USD", "B/USD"):
        summariser.handle(_trade(symbol, side="buy", ord_type="limit", price=10.0, qty=1.0), "")
    clock.at = T0 + timedelta(minutes=1, seconds=5)
    summariser.mark("reconnect")
    clock.at = T0 + timedelta(minutes=2)
    summariser.flush_due(clock())

    first = [row for row in rows.rows if row["minute"] == "2026-09-11T12:00:00Z"]
    second = [row for row in rows.rows if row["minute"] == "2026-09-11T12:01:00Z"]
    assert [row["flags"] for row in first] == [["disconnect"], ["disconnect"]]
    assert [row["flags"] for row in second] == [["reconnect"], ["reconnect"]]
    assert all(row["clean"] is False for row in rows.rows)


def test_an_unknown_flag_is_refused() -> None:
    summariser = _summariser(Rows(), Clock(T0))
    with pytest.raises(ValueError):
        summariser.mark("sunspots")


# --------------------------------------------------------------------------- #
# The checksum
# --------------------------------------------------------------------------- #


def _crc_for(state: Any) -> int:
    """Kraken's checksum for the book as it stands, via the recorder's own
    formatter; the fixture replay below is what proves that formatter right."""
    value = state.checksum()
    assert isinstance(value, int)
    return value


def test_checksum_matches_kraken_on_every_book_frame_in_the_committed_sample() -> None:
    lines = [json.loads(raw) for raw in SAMPLE.read_text(encoding="utf-8").splitlines() if raw.strip()]
    frames = [line for line in lines if line["pair"] == "ETH/USD" and line["channel"] == "book"]
    assert len(frames) >= 5, "the fixture must carry real ETH/USD book frames"
    state = record.BookState(10, price_precision=ETH_USD_PRECISION[0], qty_precision=ETH_USD_PRECISION[1])
    verified = 0
    for line in frames:
        payload = line["payload"]
        for entry in payload["data"]:
            if payload["type"] == "snapshot":
                state.reset()
            state.apply(entry)
            expected = entry.get("checksum")
            if expected is None:
                continue
            assert state.checksum() == expected, f"mismatch on {line['ts_exchange']}"
            verified += 1
    assert verified == len(frames)


def test_checksum_is_unavailable_without_precisions() -> None:
    state = record.BookState(10)
    state.apply({"bids": [{"price": 1.0, "qty": 1.0}], "asks": [{"price": 2.0, "qty": 1.0}]})
    assert state.checksum() is None
    assert state.verify is False


def test_a_checksum_mismatch_flags_stops_sampling_and_asks_once_for_a_snapshot() -> None:
    rows, clock = Rows(), Clock(T0)
    asked: list[str] = []
    summariser = _summariser(rows, clock, precisions={"X/USD": (1, 8)}, resubscribe=asked.append)
    probe = record.BookState(10, price_precision=1, qty_precision=8)

    snapshot = {"symbol": "X/USD", "bids": [{"price": 99.0, "qty": 1.0}], "asks": [{"price": 101.0, "qty": 1.0}]}
    probe.apply(snapshot)
    summariser.handle(
        {"channel": "book", "type": "snapshot", "data": [{**snapshot, "checksum": _crc_for(probe)}]}, ""
    )
    good = {"symbol": "X/USD", "bids": [{"price": 99.5, "qty": 1.0}], "asks": []}
    probe.apply(good)
    summariser.handle({"channel": "book", "type": "update", "data": [{**good, "checksum": _crc_for(probe)}]}, "")
    # Now a frame whose checksum says Kraken's book is not ours.
    bad = {"symbol": "X/USD", "bids": [{"price": 99.6, "qty": 1.0}], "asks": [], "checksum": 12345}
    summariser.handle({"channel": "book", "type": "update", "data": [bad]}, "")
    summariser.handle({"channel": "book", "type": "update", "data": [bad]}, "")
    clock.at = T0 + timedelta(minutes=1)
    summariser.flush_due(clock())

    (row,) = rows.rows
    assert row["flags"] == ["checksum"] and row["clean"] is False
    assert row["updates"] == 4
    assert row["samples"] == 2, "a book known to be wrong yields no samples"
    assert asked == ["X/USD"], "one resubscribe per corruption episode, not one per frame"
    assert summariser.checksum_failures == 2

    # The snapshot the resubscribe produces restores sampling, and says so.
    probe.reset()
    fresh = {"symbol": "X/USD", "bids": [{"price": 98.0, "qty": 1.0}], "asks": [{"price": 100.0, "qty": 1.0}]}
    probe.apply(fresh)
    summariser.handle(
        {"channel": "book", "type": "snapshot", "data": [{**fresh, "checksum": _crc_for(probe)}]}, ""
    )
    summariser.flush_all(clock())
    _, row2 = rows.rows
    assert row2["samples"] == 1 and row2["flags"] == ["resnapshot"]
    assert asked == ["X/USD"]


def test_a_snapshot_that_fails_the_checksum_disables_verification_rather_than_flagging() -> None:
    rows, clock = Rows(), Clock(T0)
    asked: list[str] = []
    summariser = _summariser(rows, clock, precisions={"X/USD": (1, 8)}, resubscribe=asked.append)
    snapshot = {
        "symbol": "X/USD",
        "bids": [{"price": 99.0, "qty": 1.0}],
        "asks": [{"price": 101.0, "qty": 1.0}],
        "checksum": 1,  # wrong on the snapshot itself: our formatting, not drift
    }
    summariser.handle({"channel": "book", "type": "snapshot", "data": [snapshot]}, "")
    update = {"symbol": "X/USD", "bids": [{"price": 99.5, "qty": 1.0}], "asks": [], "checksum": 2}
    summariser.handle({"channel": "book", "type": "update", "data": [update]}, "")
    summariser.flush_all(clock())

    (row,) = rows.rows
    assert row["flags"] == [] and row["clean"] is True
    assert row["samples"] == 2, "an unverified book is still sampled"
    assert summariser.unverifiable == {"X/USD"}
    assert summariser.verified_pairs == 0
    assert asked == [] and summariser.checksum_failures == 0


# --------------------------------------------------------------------------- #
# The validator
# --------------------------------------------------------------------------- #


V1_ROW = {
    "v": 1,
    "kind": "summary",
    "pair": "ZRO/USD",
    "minute": "2026-09-11T21:46:00Z",
    "spread_bps": [10.0251, 10.0251, 10.0251],
    "depth_bid_bps": 30.0601,
    "depth_ask_bps": 55.0826,
    "mid": 0.9975,
    "updates": 337,
    "samples": 337,
    "depth_samples": 337,
    "trades": 0,
    "volume": 0.0,
    "quote_volume": 0.0,
}


def _v2_row() -> dict[str, Any]:
    rows, clock = Rows(), Clock(T0)
    summariser = _summariser(rows, clock)
    summariser.handle(_book("X/USD", bids=[(99.0, 1.0)], asks=[(101.0, 1.0)], snapshot=True), "")
    summariser.handle(_move_mid("X/USD", (99.0, 101.0), (100.0, 102.0)), "")
    summariser.handle(_trade("X/USD", side="buy", ord_type="market", price=100.5, qty=2.0), "")
    summariser.handle(_trade("X/USD", side="sell", ord_type="limit", price=100.4, qty=1.0), "")
    summariser.flush_all(clock())
    return dict(rows.rows[0])


def test_rows_written_before_the_bump_still_validate() -> None:
    record.validate_summary_line(dict(V1_ROW))


def test_a_v1_row_with_v2_keys_or_a_v2_row_with_v1_keys_is_refused() -> None:
    row = _v2_row()
    with pytest.raises(record.SchemaError):
        record.validate_summary_line({**row, "v": 1})
    with pytest.raises(record.SchemaError):
        record.validate_summary_line({**V1_ROW, "v": 2})
    with pytest.raises(record.SchemaError):
        record.validate_summary_line({**row, "v": 3})


@pytest.mark.parametrize(
    ("mutation", "why"),
    [
        ({"clean": True, "flags": ["checksum"]}, "clean must agree with flags"),
        ({"flags": ["sunspots"]}, "an unknown flag"),
        ({"flags": ["checksum", "checksum"], "clean": False}, "a repeated flag"),
        ({"buy_trades": 5}, "more sided prints than prints"),
        ({"market_trades": 5}, "more typed prints than prints"),
        ({"buy_volume": 100.0}, "more sided volume than volume"),
        ({"low": 200.0}, "low above open and close"),
        ({"high": 1.0}, "high below open and close"),
        ({"open": None}, "a partial OHLC"),
        ({"rv": -1e-9}, "a negative sum of squares"),
        ({"rv_samples": 0}, "rv present with no samples behind it"),
        ({"vwap": None}, "no vwap though something traded"),
        ({"last_trade": None}, "no last trade though something traded"),
    ],
)
def test_the_v2_relations_are_enforced(mutation: dict[str, Any], why: str) -> None:
    row = _v2_row()
    record.validate_summary_line(dict(row))
    with pytest.raises(record.SchemaError):
        record.validate_summary_line({**row, **mutation})


def test_the_cost_model_row_is_a_valid_v2_row_and_is_larger_than_before() -> None:
    # 266 B was the measured v1 row on 2026-09-11; the v2 row is roughly double.
    assert 500 <= record.summary_row_bytes() <= 700
