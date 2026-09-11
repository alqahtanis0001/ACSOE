"""The funding-rate and open-interest poller, `scripts/recording/funding.py`.

Loaded by path: it is a standalone script and must not become a package. Every
test here drives the venue through a stub `fetch`; nothing touches the network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FUNDING_PY = REPO_ROOT / "scripts" / "recording" / "funding.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_funding_script", FUNDING_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


funding = _load()


def _ticker(symbol: str, pair: str, *, tag: str = "perpetual", volume_quote: float | None = 5e8) -> dict[str, Any]:
    ticker: dict[str, Any] = {
        "symbol": symbol,
        "pair": pair,
        "tag": tag,
        "markPrice": 77000.0,
        "fundingRate": 1.2e-8,
        "fundingRatePrediction": 1.1e-8,
        "openInterest": 12345.0,
        "lastTime": "2026-09-11T20:00:00.000Z",
    }
    if volume_quote is not None:
        ticker["volumeQuote"] = volume_quote
    return ticker


TICKERS = [
    _ticker("PF_XBTUSD", "XBT:USD"),
    _ticker("PI_XBTUSD", "XBT:USD", volume_quote=1e5),
    _ticker("FI_XBTUSD_260930", "XBT:USD", tag="month"),
    _ticker("PF_SOLUSD", "SOL:USD", volume_quote=2e7),
    _ticker("PF_ETHUSD", "ETH:USD"),
]


def _answer() -> dict[str, Any]:
    return {"result": "success", "serverTime": "2026-09-11T20:00:31.335Z", "tickers": list(TICKERS)}


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip()]


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #


def test_the_futures_alias_is_tried_alongside_the_spot_name() -> None:
    assert funding.perp_pairs_for("BTC/USD") == ("BTC:USD", "XBT:USD")
    assert funding.perp_pairs_for("DOGE/USD") == ("DOGE:USD", "XDG:USD")
    assert funding.perp_pairs_for("SOL/USD") == ("SOL:USD",)
    assert funding.perp_pairs_for("nonsense") == ()


def test_matching_keeps_every_liquid_perpetual_and_names_what_it_did_not_keep() -> None:
    result = funding.match_perpetuals(
        ["BTC/USD", "SOL/USD", "USDT/USD"], TICKERS, floor_usd=1_000_000.0
    )
    assert result.summary()["matched"] == {"BTC/USD": ["PF_XBTUSD"], "SOL/USD": ["PF_SOLUSD"]}
    assert result.unmatched == ["USDT/USD"]
    assert result.below_floor == [
        {"spot_symbol": "BTC/USD", "futures_symbol": "PI_XBTUSD", "volume_quote": 1e5}
    ]
    # The dated future on the same pair is never a match, however liquid.
    assert all(ticker["tag"] == "perpetual" for _, ticker in result.matched)


def test_an_explicit_symbol_is_recorded_regardless_of_floor_or_pair() -> None:
    result = funding.match_perpetuals(
        ["BTC/USD"], TICKERS, floor_usd=1e12, symbols=["PI_XBTUSD", "PF_ETHUSD"]
    )
    assert result.summary()["matched"] == {"BTC/USD": ["PI_XBTUSD"], "PF_ETHUSD": ["PF_ETHUSD"]}


def test_quote_volume_is_derived_when_the_venue_omits_it() -> None:
    assert funding.quote_volume_24h({"volumeQuote": 12.5}) == 12.5
    assert funding.quote_volume_24h({"vol24h": 2.0, "markPrice": 100.0}) == 200.0
    assert funding.quote_volume_24h({"vol24h": 2.0}) is None
    assert funding.quote_volume_24h({"volumeQuote": True}) is None


# --------------------------------------------------------------------------- #
# The archive
# --------------------------------------------------------------------------- #


def test_one_poll_writes_one_validated_line_per_match_with_the_ticker_verbatim(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(url: str) -> dict[str, Any]:
        calls.append(url)
        return _answer()

    with funding.JsonlWriter(tmp_path, prefix="funding", source_id="msi") as writer:
        result = funding.poll_once(
            writer,
            ["BTC/USD", "SOL/USD"],
            floor_usd=1e6,
            fetch=fetch,
            now_iso=lambda: "2026-09-11T20:00:02.000000Z",
        )
    assert calls == [funding.FUTURES_TICKERS_URL]
    assert len(result.matched) == 2
    path = tmp_path / "funding__msi__2026-09-11.jsonl"
    lines = _lines(path)
    assert [line["pair"] for line in lines] == ["BTC/USD", "SOL/USD"]
    for line in lines:
        funding.validate_line(line)
        assert line["kind"] == "tick" and line["channel"] == "funding"
        assert line["ts_exchange"] == "2026-09-11T20:00:31.335Z"
        assert line["payload"]["endpoint"] == funding.FUTURES_TICKERS_URL
    assert lines[0]["payload"]["futures_symbol"] == "PF_XBTUSD"
    assert lines[0]["payload"]["ticker"] == TICKERS[0], "the venue's entry, untouched"


def test_a_server_time_that_is_not_utc_iso_becomes_null_not_the_receive_time(tmp_path: Path) -> None:
    def fetch(url: str) -> dict[str, Any]:
        return {**_answer(), "serverTime": 1_700_000_000}

    with funding.JsonlWriter(tmp_path, prefix="funding", source_id="msi") as writer:
        funding.poll_once(writer, ["BTC/USD"], floor_usd=1e6, fetch=fetch)
    (line,) = _lines(next(tmp_path.glob("*.jsonl")))
    assert line["ts_exchange"] is None


def test_a_failed_slot_is_written_as_a_gap_marker(tmp_path: Path) -> None:
    def fetch(url: str) -> dict[str, Any]:
        raise funding.PollError("connection refused")

    slept: list[float] = []
    with funding.JsonlWriter(tmp_path, prefix="funding", source_id="msi") as writer:
        outcome = funding._poll_with_retries(
            writer,
            ["BTC/USD"],
            slot="2026-09-11T21:00:00.000000Z",
            floor_usd=1e6,
            symbols=None,
            fetch=fetch,
            sleep=slept.append,
        )
    assert outcome is None
    assert slept == list(funding.RETRY_DELAYS_S)
    (line,) = _lines(next(tmp_path.glob("*.jsonl")))
    funding.validate_line(line)
    assert line["kind"] == "gap" and line["channel"] == "_recorder"
    assert line["payload"]["slot"] == "2026-09-11T21:00:00.000000Z"
    assert line["payload"]["attempts"] == len(funding.RETRY_DELAYS_S) + 1
    assert "connection refused" in line["payload"]["reason"]


def test_a_venue_error_inside_http_200_is_a_poll_error() -> None:
    def fetch(url: str) -> dict[str, Any]:
        return {"result": "error", "error": "apiLimitExceeded"}

    class Sink:
        def write(self, line: dict[str, Any]) -> None:
            raise AssertionError("nothing may be written on a failed poll")

    with pytest.raises(funding.PollError):
        funding.poll_once(Sink(), ["BTC/USD"], floor_usd=1e6, fetch=lambda url: fetch(url))  # type: ignore[arg-type]


def test_backfill_writes_each_published_rate_verbatim_into_the_history_file(tmp_path: Path) -> None:
    rates = [
        {"timestamp": "2026-09-10T00:00:00.000Z", "fundingRate": -8e-10, "relativeFundingRate": -1.6e-5},
        {"timestamp": "2026-09-10T04:00:00.000Z", "fundingRate": 2e-11, "relativeFundingRate": 5e-7},
    ]
    urls: list[str] = []

    def fetch(url: str) -> dict[str, Any]:
        urls.append(url)
        return {"result": "success", "serverTime": "2026-09-11T20:00:31.335Z", "rates": rates}

    matching = funding.match_perpetuals(["BTC/USD"], TICKERS, floor_usd=1e6)
    with funding.JsonlWriter(tmp_path, prefix="funding_history", source_id="msi") as writer:
        written = funding.backfill(writer, matching, fetch=fetch, now_iso=lambda: "2026-09-11T20:00:02.000000Z")
    assert written == 2
    assert urls == [funding.FUTURES_HISTORY_URL + "?symbol=PF_XBTUSD"]
    lines = _lines(tmp_path / "funding_history__msi__2026-09-11.jsonl")
    assert [line["ts_exchange"] for line in lines] == [rate["timestamp"] for rate in rates]
    assert [line["payload"]["rate"] for line in lines] == rates
    assert all(line["channel"] == "funding_history" and line["pair"] == "BTC/USD" for line in lines)


# --------------------------------------------------------------------------- #
# Which pairs
# --------------------------------------------------------------------------- #


def _beat(tier: str, pairs: list[str]) -> str:
    return json.dumps({"v": 1, "source_id": "msi", "ts": "2026-09-11T20:00:00Z", "tier": tier, "pairs": pairs})


def test_tier1_is_read_from_the_newest_heartbeats_last_tier1_beat(tmp_path: Path) -> None:
    old = tmp_path / "heartbeat__msi__2026-09-10.ndjson"
    old.write_text(_beat("tier1", ["OLD/USD"]) + "\n", encoding="utf-8")
    new = tmp_path / "heartbeat__msi__2026-09-11.ndjson"
    new.write_text(
        "\n".join(
            [
                _beat("tier1", ["BTC/USD", "ETH/USD", "SOL/USD"]),
                _beat("tier2", ["ADA/USD"]),
                _beat("tier1", ["BTC/USD", "ETH/USD"]),  # after a disk-guard degrade
                '{"v":1,"tier":"tier1","pai',  # half-written final line after a kill
            ]
        ),
        encoding="utf-8",
    )
    import os

    os.utime(old, (1, 1))
    assert funding.tier1_pairs_from_heartbeat(tmp_path) == ("BTC/USD", "ETH/USD")


def test_no_heartbeat_is_a_refusal_not_an_empty_universe(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="--pairs"):
        funding.tier1_pairs_from_heartbeat(tmp_path)
    with pytest.raises(RuntimeError):
        funding.tier1_pairs_from_heartbeat(tmp_path / "missing")


# --------------------------------------------------------------------------- #
# Scheduling, storage, the lock
# --------------------------------------------------------------------------- #


def test_slots_align_to_midnight_utc() -> None:
    now = datetime(2026, 9, 11, 20, 17, 3, tzinfo=UTC)
    assert funding.next_slot(now, 3600) == datetime(2026, 9, 11, 21, 0, tzinfo=UTC)
    assert funding.next_slot(now, 900) == datetime(2026, 9, 11, 20, 30, tzinfo=UTC)
    on_the_hour = datetime(2026, 9, 11, 21, 0, 0, tzinfo=UTC)
    assert funding.next_slot(on_the_hour, 3600) == datetime(2026, 9, 11, 22, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        funding.next_slot(now, 0)


def test_storage_falls_from_flag_to_config_to_the_archive_subdirectory(tmp_path: Path) -> None:
    config = tmp_path / "recorder.yaml"
    config.write_text(
        "recorder:\n"
        "  archive_dir: from-config/raw\n"
        "  source_id: vps-1\n"
        "  funding_floor_usd: 250000\n"
        "  funding_interval_s: 1800\n",
        encoding="utf-8",
    )
    archive, out, source, floor, interval = funding.resolve_storage(
        funding.parse_args(["--config", str(config)])
    )
    assert archive == Path("from-config/raw")
    assert out == Path("from-config/raw") / "funding"
    assert (source, floor, interval) == ("vps-1", 250_000.0, 1800)

    archive, out, source, floor, interval = funding.resolve_storage(
        funding.parse_args(
            ["--config", str(config), "--out", "elsewhere", "--floor-usd", "5", "--interval-s", "60"]
        )
    )
    assert out == Path("elsewhere") and floor == 5.0 and interval == 60


def test_run_once_polls_writes_markers_and_exits(tmp_path: Path) -> None:
    archive = tmp_path / "raw"
    archive.mkdir()
    (archive / "heartbeat__msi__2026-09-11.ndjson").write_text(
        _beat("tier1", ["BTC/USD", "SOL/USD"]) + "\n", encoding="utf-8"
    )
    args = funding.parse_args(
        ["--archive", str(archive), "--source-id", "msi", "--once", "--config", str(_no_config(tmp_path))]
    )
    assert funding.run(args, fetch=lambda url: _answer()) == 0
    out = archive / "funding"
    lines = _lines(next(out.glob("funding__msi__*.jsonl")))
    kinds = [(line["kind"], line["channel"]) for line in lines]
    assert kinds == [
        ("tick", "funding"),
        ("tick", "funding"),
        ("session", "_recorder"),
        ("session", "_recorder"),
    ]
    start = lines[2]["payload"]
    assert start["event"] == "start" and start["spot_pairs"] == ["BTC/USD", "SOL/USD"]
    assert start["spot_pairs_from"] == "recorder heartbeat"
    assert start["matched"] == {"BTC/USD": ["PF_XBTUSD"], "SOL/USD": ["PF_SOLUSD"]}
    assert lines[3]["payload"]["event"] == "stop"
    assert (out / funding.LOCK_FILENAME).exists()


def _no_config(tmp_path: Path) -> Path:
    path = tmp_path / "empty.yaml"
    path.write_text("recorder: {}\n", encoding="utf-8")
    return path


def test_a_second_poller_on_the_same_directory_is_refused(tmp_path: Path) -> None:
    with funding.ArchiveLock(tmp_path), pytest.raises(funding.ArchiveLockedError):
        funding.ArchiveLock(tmp_path).acquire()
    # Released with the handle, so a later poller starts.
    funding.ArchiveLock(tmp_path).acquire().release()
