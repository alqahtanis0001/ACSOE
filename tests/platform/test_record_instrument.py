"""P1: the tier 1 socket keeps Kraken's `instrument` channel, so the pair rules are recorded.

`scripts/record.py` is loaded by path, as the other recorder tests do. The network
guard refuses every socket, loopback included, so the WebSocket is a scripted fake
put where `record.py` looks `connect` up. Each fake connection plays its frames and
then either drops — which drives the real reconnect path — or idles until stopped.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import orjson
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RECORD_PY = REPO_ROOT / "scripts" / "record.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_record_script_instrument", RECORD_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


record = _load()

INSTRUMENT_SUB = {"method": "subscribe", "params": {"channel": "instrument"}}

SNAPSHOT = {
    "channel": "instrument",
    "type": "snapshot",
    "data": {
        "assets": [{"id": "BTC", "status": "enabled", "precision": 10}],
        "pairs": [
            {
                "symbol": "BTC/USD",
                "base": "BTC",
                "quote": "USD",
                "status": "online",
                "qty_min": 5e-05,
                "cost_min": 0.5,
                "tick_size": 0.1,
                "price_precision": 1,
                "qty_precision": 8,
            }
        ],
    },
}
UPDATE = {
    "channel": "instrument",
    "type": "update",
    "data": {"assets": [], "pairs": [{"symbol": "BTC/USD", "status": "cancel_only"}]},
}
TRADE = {
    "channel": "trade",
    "type": "update",
    "data": [{"symbol": "BTC/USD", "price": 80000.1, "qty": 0.1, "side": "buy",
              "ord_type": "limit", "trade_id": 1, "timestamp": "2026-09-19T05:00:00.000000Z"}],
}


class FakeSocket:
    def __init__(self, frames: list[dict[str, Any]], *, drop: bool) -> None:
        self.frames = [orjson.dumps(frame) for frame in frames]
        self.drop = drop
        self.sent: list[dict[str, Any]] = []

    async def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def recv(self) -> bytes:
        await asyncio.sleep(0)
        if self.frames:
            return self.frames.pop(0)
        if self.drop:
            raise OSError("the fake connection dropped")
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class FakeConnect:
    """Stands in for `websockets.asyncio.client.connect`, one script per call."""

    def __init__(self, scripts: list[FakeSocket]) -> None:
        self.scripts = scripts
        self.opened: list[FakeSocket] = []

    def __call__(self, url: str, **kwargs: Any) -> Any:
        del url, kwargs
        socket = self.scripts.pop(0) if self.scripts else FakeSocket([], drop=False)
        self.opened.append(socket)
        return _Session(socket)


class _Session:
    def __init__(self, socket: FakeSocket) -> None:
        self.socket = socket

    async def __aenter__(self) -> FakeSocket:
        return self.socket

    async def __aexit__(self, *exc: object) -> None:
        return None


def _lines(directory: Path) -> list[dict[str, Any]]:
    return [
        json.loads(raw)
        for path in sorted(directory.glob("kraken_v2__*.jsonl"))
        for raw in path.read_bytes().splitlines()
        if raw.strip()
    ]


async def _until(predicate: Any, timeout_s: float = 10.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while not predicate():
        assert loop.time() < deadline, "timed out waiting for the stream"
        await asyncio.sleep(0.01)


def _stream(writer: Any, *, instrument: bool, channels: tuple[str, ...] = record.TIER1_CHANNELS) -> Any:
    return record.Stream(
        label="tier1",
        writer=writer,
        sink=record.make_raw_sink(writer),
        url="wss://fake",
        pairs=("BTC/USD", "ETH/USD", "SOL/USD"),
        channels=channels,
        depth=10,
        instrument=instrument,
    )


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(record, "BACKOFF_INITIAL_S", 0.01)


@pytest.mark.asyncio
async def test_every_connect_subscribes_instrument_first_and_records_it_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect = FakeConnect(
        [
            FakeSocket([SNAPSHOT, TRADE], drop=True),
            FakeSocket([SNAPSHOT, UPDATE], drop=False),
        ]
    )
    monkeypatch.setattr(record, "connect", connect)
    with record.JsonlWriter(tmp_path, source_id="test") as writer:
        stream = _stream(writer, instrument=True)
        task = asyncio.ensure_future(stream.run())
        await _until(lambda: writer.lines_written >= 6)
        stream.stop()
        await task

    assert len(connect.opened) == 2
    for socket in connect.opened:
        assert socket.sent[0] == INSTRUMENT_SUB, "instrument was not the first subscription"
        assert socket.sent.count(INSTRUMENT_SUB) == 1
        assert [sub["params"]["channel"] for sub in socket.sent[1:]] == list(record.TIER1_CHANNELS)

    lines = _lines(tmp_path)
    kinds = [(line["kind"], line["channel"]) for line in lines]
    assert kinds == [
        ("session", "_recorder"),
        ("tick", "instrument"),
        ("tick", "trade"),
        ("gap", "_recorder"),
        ("tick", "instrument"),
        ("tick", "instrument"),
        ("session", "_recorder"),
    ]
    snapshot_lines = [line for line in lines if line["channel"] == "instrument"]
    assert snapshot_lines[0]["payload"] == SNAPSHOT, "the snapshot was not recorded verbatim"
    assert snapshot_lines[1]["payload"] == SNAPSHOT, "a reconnect did not re-record the rules"
    assert snapshot_lines[2]["payload"] == UPDATE, "a status change was not recorded"
    for line in snapshot_lines:
        assert line["pair"] is None
        assert line["ts_exchange"] is None
    assert lines[0]["payload"]["subscriptions"][0] == {"channel": "instrument"}


@pytest.mark.asyncio
async def test_the_disk_guard_never_unsubscribes_instrument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect = FakeConnect([FakeSocket([SNAPSHOT], drop=False)])
    monkeypatch.setattr(record, "connect", connect)
    with record.JsonlWriter(tmp_path, source_id="test") as writer:
        stream = _stream(writer, instrument=True)
        task = asyncio.ensure_future(stream.run())
        await _until(lambda: writer.lines_written >= 2)
        await stream.drop_to(["BTC/USD"])
        stream.stop()
        await task

    sent = connect.opened[0].sent
    unsubscribes = [message for message in sent if message["method"] == "unsubscribe"]
    assert unsubscribes, "the degrade sent no unsubscribe at all"
    for message in unsubscribes:
        assert message["params"]["channel"] != "instrument"
        assert "BTC/USD" not in message["params"]["symbol"]
    assert stream.all_subscriptions()[0] == INSTRUMENT_SUB, "a reconnect after a degrade would drop the rules"
    assert stream.pairs == ("BTC/USD",)


@pytest.mark.asyncio
async def test_a_stream_without_the_flag_never_asks_for_instrument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect = FakeConnect([FakeSocket([TRADE], drop=False)])
    monkeypatch.setattr(record, "connect", connect)
    with record.JsonlWriter(tmp_path, source_id="test") as writer:
        stream = _stream(writer, instrument=False, channels=record.TIER2_CHANNELS)
        task = asyncio.ensure_future(stream.run())
        await _until(lambda: writer.lines_written >= 2)
        stream.stop()
        await task
    assert INSTRUMENT_SUB not in connect.opened[0].sent
    assert all(sub["params"]["channel"] != "instrument" for sub in stream.all_subscriptions())


@pytest.mark.asyncio
async def test_the_recorder_asks_for_instrument_on_tier_1_and_not_on_tier_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wiring in `_record`, not just the flag: tier 1 carries the rules once, and
    the summary tier — which keeps no raw frames — does not ask for them at all."""
    ranked = (
        record.PairStat(symbol="BTC/USD", quote_volume_24h=9e8, trades_24h=1,
                        price_precision=1, qty_precision=8),
        record.PairStat(symbol="SOL/USD", quote_volume_24h=5e6, trades_24h=1,
                        price_precision=2, qty_precision=8),
    )

    async def discover(url: str, *, quote: str, timeout_s: float = 0.0) -> Any:
        del url, quote, timeout_s
        return ranked, ()

    connect = FakeConnect([FakeSocket([SNAPSHOT], drop=False), FakeSocket([], drop=False)])
    monkeypatch.setattr(record, "connect", connect)
    monkeypatch.setattr(record, "discover_with_retry", discover)
    args = record.parse_args(
        [
            "--tier1-count", "1",
            "--tier2-floor-usd", "1",
            "--out", str(tmp_path / "raw"),
            "--summary-out", str(tmp_path / "summaries"),
            "--source-id", "test",
            "--duration-s", "1",
            "--disk-floor-gb", "0",
        ]
    )
    assert await record._record(args, tmp_path / "raw", tmp_path / "summaries", "test") == 0

    by_tier = {
        "tier1" if any(sub["params"]["channel"] == "ticker" for sub in socket.sent) else "tier2": socket
        for socket in connect.opened
    }
    assert set(by_tier) == {"tier1", "tier2"}
    assert by_tier["tier1"].sent[0] == INSTRUMENT_SUB
    assert INSTRUMENT_SUB not in by_tier["tier2"].sent
    raw = _lines(tmp_path / "raw")
    assert any(line["channel"] == "instrument" for line in raw), "no rules reached the archive"
