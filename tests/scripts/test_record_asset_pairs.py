"""`scripts/record_asset_pairs.py` — a genuine `AssetPairs`, recorded once. Spec 127.

Two kinds of test. The capture, the join and the counts are driven by constructed doubles,
because the network is closed to tests and a planted disagreement is the only way to see a
check go red. **The committed recordings are then read with no double at all**: they parse
through the live client's own `map_asset_pairs`, their digests re-check, and the derived name
map agrees with them. That last group is spec 127's Check When Done.

Every assertion here was run against a deliberately broken script and seen red; the sweep is
in `docs/build-log/phase-7/a-platform.md`.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from acsoe.clients.kraken.errors import KrakenAPIError, KrakenUnavailableError
from acsoe.clients.kraken.rest import HttpResponse, map_asset_pairs
from acsoe.platform.clock import FixedClock
from acsoe.platform.config import load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "record_asset_pairs.py"
DAY = "2026-09-19"
AT = datetime(2026, 9, 19, 4, 20, tzinfo=UTC)


@pytest.fixture(scope="module")
def rap() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_record_asset_pairs_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rest_entry(altname: str, wsname: str, **rules: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "altname": altname,
        "wsname": wsname,
        "base": "B",
        "quote": "ZUSD",
        "ordermin": "5",
        "costmin": "0.5",
        "tick_size": "0.01",
        "pair_decimals": 2,
        "lot_decimals": 8,
        "status": "online",
    }
    entry.update(rules)
    return entry


def v2_item(symbol: str, **rules: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "symbol": symbol,
        "qty_min": 5.0,
        "cost_min": 0.5,
        "tick_size": 0.01,
        "price_precision": 2,
        "qty_precision": 8,
        "status": "online",
    }
    item.update(rules)
    return item


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #


class CannedTransport:
    """Answers every request with one body, and counts the requests."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.urls: list[str] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        content: bytes | None,
        timeout_s: float,
    ) -> HttpResponse:
        self.urls.append(url)
        return HttpResponse(status_code=200, body=self.body)


BODY = (
    b'{"error":[],"result":{"XXBTZUSD":{"altname":"XBTUSD","wsname":"XBT/USD","base":"XXBT",'
    b'"quote":"ZUSD","ordermin":"0.00005","costmin":"0.5","tick_size":"0.1",'
    b'"pair_decimals":1,"lot_decimals":8,"status":"online"}}}'
)


def test_the_body_is_kept_byte_for_byte_with_its_provenance(rap: ModuleType) -> None:
    transport = CannedTransport(BODY)
    captured = asyncio.run(
        rap.capture_asset_pairs(
            load_config(load_env=False), clock=FixedClock(AT), transport=transport
        )
    )
    assert transport.urls == ["https://api.kraken.com/0/public/AssetPairs"]
    document = rap.fixture_document(captured, request="GET /0/public/AssetPairs")
    assert document["payload"].encode("utf-8") == BODY
    provenance = document["provenance"]
    assert provenance["url"] == "https://api.kraken.com/0/public/AssetPairs"
    assert provenance["captured_at"] == "2026-09-19T04:20:00Z"
    assert provenance["payload_sha256"] == hashlib.sha256(BODY).hexdigest()
    assert provenance["client_version"]["acsoe"]


def test_a_body_the_live_parser_rejects_is_never_captured(rap: ModuleType) -> None:
    transport = CannedTransport(b'{"error":["EGeneral:Unavailable"],"result":{}}')
    with pytest.raises(KrakenAPIError):
        asyncio.run(
            rap.capture_asset_pairs(
                load_config(load_env=False), clock=FixedClock(AT), transport=transport
            )
        )


def test_an_envelope_with_no_usable_pair_is_never_captured(rap: ModuleType) -> None:
    """A clean envelope the live *mapping* rejects: the capture goes through the client's
    own `asset_pairs()`, not around it."""
    body = b'{"error":[],"result":{"XXBTZUSD":{"altname":"XBTUSD","wsname":"XBT/USD"}}}'
    with pytest.raises(KrakenUnavailableError, match="no pair"):
        asyncio.run(
            rap.capture_asset_pairs(
                load_config(load_env=False), clock=FixedClock(AT), transport=CannedTransport(body)
            )
        )


class ScriptedSocket:
    def __init__(self, frames: list[str]) -> None:
        self.frames = list(frames)
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    async def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def recv(self) -> str:
        return self.frames.pop(0)

    async def close(self) -> None:
        self.closed = True


def test_the_instrument_snapshot_frame_is_taken_verbatim(rap: ModuleType) -> None:
    snapshot = '{"channel":"instrument","type":"snapshot","data":{"assets":[],"pairs":[]}}'
    socket = ScriptedSocket(
        [
            '{"channel":"status","type":"update","data":[{"system":"online"}]}',
            '{"method":"subscribe","success":true,"result":{"channel":"instrument"}}',
            '{"channel":"heartbeat"}',
            '{"channel":"instrument","type":"update","data":{"assets":[],"pairs":[]}}',
            snapshot,
        ]
    )

    async def connector(url: str) -> ScriptedSocket:
        assert url == "wss://ws.kraken.com/v2"
        return socket

    captured = asyncio.run(rap.capture_instrument(clock=FixedClock(AT), connector=connector))
    assert captured.body == snapshot.encode()
    assert [message["method"] for message in socket.sent] == ["subscribe", "unsubscribe"]
    assert socket.closed


def test_a_recording_is_written_once_as_lf_bytes(rap: ModuleType, tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    document = {"provenance": {"payload_sha256": "x"}, "payload": "a\nb"}
    rap.write_fixture(target, document)
    assert b"\r\n" not in target.read_bytes()
    with pytest.raises(rap.RecordError, match="written once"):
        rap.write_fixture(target, document)


def test_a_payload_that_no_longer_matches_its_digest_is_refused(
    rap: ModuleType, tmp_path: Path
) -> None:
    good = tmp_path / "good.json"
    good.write_bytes(
        json.dumps(
            {"provenance": {"payload_sha256": hashlib.sha256(BODY).hexdigest()}, "payload": BODY.decode()}
        ).encode()
    )
    _, payload = rap.load_payload(good)
    assert "XXBTZUSD" in payload["result"]
    bad = tmp_path / "bad.json"
    bad.write_bytes(good.read_bytes().replace(b"0.00005", b"0.00006"))
    with pytest.raises(rap.RecordError, match="sha256"):
        rap.load_payload(bad)


# --------------------------------------------------------------------------- #
# REST against v2
# --------------------------------------------------------------------------- #


def test_the_asset_map_is_derived_only_where_the_evidence_agrees(rap: ModuleType) -> None:
    rest = {
        "XXBTZUSD": rest_entry("XBTUSD", "XBT/USD", ordermin="0.00005"),
        "XBTUSDT": rest_entry("XBTUSDT", "XBT/USDT", ordermin="0.00005"),
        "ETHUSD": rest_entry("ETHUSD", "ETH/USD", ordermin="0.002"),
        # Two unclaimed v2 symbols carry these rules, and they disagree about XDG.
        "XDGUSD": rest_entry("XDGUSD", "XDG/USD", ordermin="50"),
    }
    v2 = {
        "BTC/USD": v2_item("BTC/USD", qty_min=5e-05),
        "BTC/USDT": v2_item("BTC/USDT", qty_min=5e-05),
        "ETH/USD": v2_item("ETH/USD", qty_min=0.002),
        "DOGE/USD": v2_item("DOGE/USD", qty_min=50.0),
        "SHIB/USD": v2_item("SHIB/USD", qty_min=50.0),
    }
    assert rap.derive_asset_map(rest, v2) == {"XBT": "BTC"}


def test_values_are_compared_by_value_not_spelling(rap: ModuleType) -> None:
    rest = {"XDGUSD": rest_entry("XDGUSD", "XDG/USD", ordermin="50")}
    v2 = {"DOGE/USD": v2_item("DOGE/USD", qty_min=50.0)}
    assert rap.derive_asset_map(rest, v2) == {"XDG": "DOGE"}
    comparison = rap.compare_rest_v2(rest, v2, {"XDG": "DOGE"})
    assert comparison["matched"] == 1
    assert comparison["mismatches"] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("qty_min", 6.0),
        ("cost_min", 1.0),
        ("tick_size", 0.001),
        ("price_precision", 3),
        ("qty_precision", 7),
        ("status", "cancel_only"),
    ],
)
def test_every_compared_rule_can_disagree(rap: ModuleType, field: str, value: Any) -> None:
    rest = {"ETHUSD": rest_entry("ETHUSD", "ETH/USD")}
    v2 = {"ETH/USD": v2_item("ETH/USD", **{field: value})}
    comparison = rap.compare_rest_v2(rest, v2, {})
    assert len(comparison["mismatches"]) == 1
    assert field in comparison["mismatches"][0]


def test_an_unjoined_pair_is_reported_on_both_sides(rap: ModuleType) -> None:
    rest = {"XDGUSD": rest_entry("XDGUSD", "XDG/USD")}
    v2 = {"DOGE/USD": v2_item("DOGE/USD")}
    comparison = rap.compare_rest_v2(rest, v2, {})
    assert comparison["unmatched"] == ["XDGUSD"]
    assert comparison["v2_without_rest"] == ["DOGE/USD"]


def test_no_name_map_is_derived_from_recordings_that_disagree(
    rap: ModuleType, tmp_path: Path
) -> None:
    fixtures = tmp_path / "tests" / "fixtures" / "kraken"
    fixtures.mkdir(parents=True)

    def recorded(stem: str, payload: Any) -> None:
        text = json.dumps(payload)
        (fixtures / f"{stem}_{DAY}.json").write_bytes(
            json.dumps(
                {
                    "provenance": {
                        "payload_sha256": hashlib.sha256(text.encode()).hexdigest()
                    },
                    "payload": text,
                }
            ).encode()
        )

    recorded("asset_pairs_recorded", {"error": [], "result": {"ETHUSD": rest_entry("ETHUSD", "ETH/USD")}})
    recorded(
        "instrument_recorded",
        {"channel": "instrument", "type": "snapshot", "data": {"pairs": [v2_item("ETH/USD", qty_min=6.0)]}},
    )
    with pytest.raises(rap.RecordError, match="mismatches"):
        rap.names_document(tmp_path, DAY)


def test_a_pair_the_live_parser_drops_is_named(rap: ModuleType) -> None:
    rest = {"ETHUSD": rest_entry("ETHUSD", "ETH/USD"), "BADUSD": rest_entry("BADUSD", "BAD/USD")}
    del rest["BADUSD"]["ordermin"]
    assert rap.check_rules(rest) == {"pairs_in_payload": 2, "parsed": 1, "dropped": ["BADUSD"]}


# --------------------------------------------------------------------------- #
# Survivorship and the tick caveat
# --------------------------------------------------------------------------- #


def bars(path: Path, stamps: list[int]) -> None:
    path.write_bytes(b"".join(b"%d,1,1,1,1,1,1\n" % stamp for stamp in stamps))


def test_survivorship_counts_window_pairs_absent_by_altname(
    rap: ModuleType, tmp_path: Path
) -> None:
    inside_six = int(datetime(2024, 8, 1, tzinfo=UTC).timestamp())
    only_older = int(datetime(2023, 9, 1, tzinfo=UTC).timestamp())
    after = int(datetime(2025, 1, 4, tzinfo=UTC).timestamp())
    bars(tmp_path / "AAAUSD_15.csv", [only_older, inside_six])  # listed
    bars(tmp_path / "BBBUSD_15.csv", [inside_six])  # delisted
    bars(tmp_path / "CCCUSD_15.csv", [only_older])  # delisted, 1.5-year window only
    bars(tmp_path / "DDDUSD_15.csv", [after])  # outside both windows
    bars(tmp_path / "EEEUSD_15.csv", [inside_six])  # listed, cancel_only
    rest = {
        "AAAUSD": rest_entry("AAAUSD", "AAA/USD"),
        "EEEUSD": rest_entry("EEEUSD", "EEE/USD", status="cancel_only"),
    }
    report = rap.survivorship(rest, tmp_path)
    six = report["phase_7_six_months"]
    assert (six["archive_usd_pairs_trading"], six["absent"]) == (3, ["BBBUSD"])
    assert six["present_but_not_online"] == ["EEEUSD (cancel_only)"]
    longer = report["one_and_a_half_years"]
    assert (longer["archive_usd_pairs_trading"], longer["absent"]) == (4, ["BBBUSD", "CCCUSD"])


def test_the_tick_caveat_reads_q_ticks_and_compares(rap: ModuleType, tmp_path: Path) -> None:
    q_ticks = tmp_path / "q_ticks.out"
    q_ticks.write_text(
        "compared 2 pairs\n"
        "  differs: ('AAAUSD', 100, (4, 4), (5, 5), 0.1)\n"
        "  differs: ('BBBUSD', 100, (2, 2), (3, 3), 1.0)\n",
        encoding="utf-8",
    )
    rest = {
        "AAAUSD": rest_entry("AAAUSD", "AAA/USD", pair_decimals=5),
        "BBBUSD": rest_entry("BBBUSD", "BBB/USD", pair_decimals=2),
    }
    rows = {row["pair"]: row for row in rap.tick_check(rest, q_ticks)}
    assert rows["AAAUSD"]["agrees_with_2026_grid"] is True
    assert rows["BBBUSD"]["agrees_with_2026_grid"] is False
    assert rows["BBBUSD"]["window_grid_decimals"] == 2


# --------------------------------------------------------------------------- #
# The committed recordings, with no double
# --------------------------------------------------------------------------- #


def test_the_recorded_asset_pairs_parse_through_the_live_model(rap: ModuleType) -> None:
    path = REPO_ROOT / "tests" / "fixtures" / "kraken" / f"asset_pairs_recorded_{DAY}.json"
    provenance, payload = rap.load_payload(path)
    assert provenance["url"] == "https://api.kraken.com/0/public/AssetPairs"
    result = rap.asset_pairs_result(payload)
    snapshot = map_asset_pairs(result, fetched_at=0)
    assert set(snapshot.pairs) == set(result)
    for rule in snapshot.pairs.values():
        assert rule.ordermin > 0 and rule.costmin > 0 and rule.tick_size > 0


def test_the_committed_name_map_is_what_the_recordings_derive(rap: ModuleType) -> None:
    committed = json.loads(
        (REPO_ROOT / "tests" / "fixtures" / "kraken" / f"pair_names_recorded_{DAY}.json").read_bytes()
    )
    assert committed == rap.names_document(REPO_ROOT, DAY)
    assert committed["pairs"]["XBTUSD"] == {"rest_key": "XXBTZUSD", "v2_symbol": "BTC/USD"}
