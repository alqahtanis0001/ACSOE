"""Spec 27 — engine 2 `market_data_recorder`.

Three properties.

**It records while frozen.** A freeze stops trading; it never stops data collection.
Order-book and spread history cannot be recovered retroactively, so a minute not
recorded is a minute gone.

**An injected gap appears in the archive as a gap.** Marked, never healed. That is what
stops a silent outage being mistaken later for a quiet market.

**A client with no stream is reported, not raised.** C's fake Kraken client is exactly
that, and an engine that raised on it would take the whole guard chain to ERROR on a
tick where nothing is wrong.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.kraken.contracts import RawFrame
from acsoe.clients.recorder.contracts import RECORDER_CHANNEL, validate_line
from acsoe.clients.recorder.writer import JsonlRecorder
from acsoe.core.contracts import EngineStatus
from acsoe.engines.market_data_recorder.contracts import STATE_KEY
from acsoe.engines.market_data_recorder.engine import MarketDataRecorderEngine


@dataclass
class FakeStream:
    """A market stream double. C's fake Kraken client has none of this on purpose."""

    frames: list[RawFrame] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    connected: bool = True
    dropped_frames: int = 0
    unparsed_frames: int = 0

    def drain(self) -> tuple[RawFrame, ...]:
        drained = tuple(self.frames)
        self.frames.clear()
        return drained

    def drain_gaps(self) -> tuple[dict[str, Any], ...]:
        drained = tuple(self.gaps)
        self.gaps.clear()
        return drained


def frame(pair: str = "BTC/USD", *, ts: str = "2026-03-01T00:00:00.000000Z") -> RawFrame:
    return RawFrame(
        channel="trade",
        pair=pair,
        ts_exchange=ts,
        ts_recv=ts,
        payload={"channel": "trade", "data": [{"symbol": pair, "price": "1", "qty": "1"}]},
    )


@pytest.fixture
def engine() -> MarketDataRecorderEngine:
    return MarketDataRecorderEngine()


@pytest.fixture
def stream_context(engine_context: Any) -> tuple[Any, FakeStream]:
    stream = FakeStream()
    object.__setattr__(engine_context.clients, "kraken", stream)
    return engine_context, stream


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table(engine: MarketDataRecorderEngine) -> None:
    assert engine.name == "market_data_recorder"
    assert engine.number == 2
    assert engine.is_gate is False
    assert engine.name == STATE_KEY


# --------------------------------------------------------------------------- #
# Recording
# --------------------------------------------------------------------------- #


def test_every_drained_frame_reaches_the_recorder_verbatim(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    context, stream = stream_context
    stream.frames.extend([frame("BTC/USD"), frame("ETH/USD")])
    result = engine.process(context, fresh_state)

    lines = context.clients.recorder.lines
    assert len(lines) == 2
    assert [line["pair"] for line in lines] == ["BTC/USD", "ETH/USD"]
    assert lines[0]["payload"] == frame("BTC/USD").payload
    assert result.data["frames_recorded"] == 2


def test_every_written_line_validates_against_the_schema(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    context, stream = stream_context
    stream.frames.append(frame())
    stream.gaps.append(
        {
            "cause": "OSError: reset",
            "started_at": "2026-03-01T00:00:00.000000Z",
            "ended_at": "2026-03-01T00:01:00.000000Z",
            "gap_ms": 60_000,
        }
    )
    engine.process(context, fresh_state)
    for line in context.clients.recorder.lines:
        validate_line(dict(line))


def test_a_frame_is_never_recorded_twice(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    """The stream is drained, not read. A second tick over an unchanged stream must
    write nothing."""
    context, stream = stream_context
    stream.frames.append(frame())
    engine.process(context, fresh_state)
    second = engine.process(context, fresh_state)
    assert len(context.clients.recorder.lines) == 1
    assert second.data["frames_recorded"] == 0


def test_it_records_on_a_tick_where_the_mode_is_frozen(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    """A freeze stops trading and never stops data collection."""
    context, stream = stream_context
    fresh_state["system"]["mode"] = "frozen"
    stream.frames.append(frame())
    result = engine.process(context, fresh_state)
    assert result.data["frames_recorded"] == 1
    assert len(context.clients.recorder.lines) == 1


def test_it_records_on_a_tick_where_the_data_guard_blocked(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    """A block says the data cannot be traded on, not that it is not worth keeping.
    Data recorded during an outage is how the outage gets analysed."""
    context, stream = stream_context
    fresh_state["trading_blocked_by"] = "data_guard"
    fresh_state["block_reason"] = "stale"
    stream.frames.append(frame())
    assert engine.process(context, fresh_state).data["frames_recorded"] == 1


# --------------------------------------------------------------------------- #
# Gaps
# --------------------------------------------------------------------------- #


def test_an_injected_gap_is_written_into_the_archive_as_a_gap(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    context, stream = stream_context
    stream.gaps.append(
        {
            "cause": "ConnectionClosedError: 1006",
            "started_at": "2026-03-01T00:00:00.000000Z",
            "ended_at": "2026-03-01T00:04:00.000000Z",
            "gap_ms": 240_000,
        }
    )
    result = engine.process(context, fresh_state)

    written = context.clients.recorder.lines
    assert len(written) == 1
    assert written[0]["kind"] == "gap"
    assert written[0]["channel"] == RECORDER_CHANNEL
    assert written[0]["payload"]["cause"] == "ConnectionClosedError: 1006"
    assert result.data["gaps_recorded"] == 1


def test_a_gap_marker_sits_at_the_breaks_end_not_at_the_ticks(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    """The length of a break is not known until it ends, and nothing edits a
    recording afterwards. So the marker carries the moment the break closed, not the
    moment the loop noticed it up to a minute later."""
    context, stream = stream_context
    stream.gaps.append(
        {
            "cause": "OSError",
            "started_at": "2026-03-01T00:00:00.000000Z",
            "ended_at": "2026-03-01T00:04:00.000000Z",
            "gap_ms": 240_000,
        }
    )
    engine.process(context, fresh_state)
    assert context.clients.recorder.lines[0]["ts_recv"] == "2026-03-01T00:04:00.000000Z"


def test_a_gap_is_never_written_twice(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    """Drained rather than read, so the engine stays stateless across cycles and
    never has to remember what it already wrote."""
    context, stream = stream_context
    stream.gaps.append({"cause": "x", "ended_at": "2026-03-01T00:04:00.000000Z"})
    engine.process(context, fresh_state)
    engine.process(context, fresh_state)
    assert len(context.clients.recorder.lines) == 1


# --------------------------------------------------------------------------- #
# It never blocks
# --------------------------------------------------------------------------- #


def test_it_never_blocks_trading(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    """A dead feed is engine 4's judgement, on the market data itself."""
    context, stream = stream_context
    stream.connected = False
    result = engine.process(context, fresh_state)
    assert result.blocks_trading is False
    assert result.status is EngineStatus.OK
    assert result.data["connected"] is False


def test_a_client_with_no_stream_is_reported_not_raised(
    engine: MarketDataRecorderEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    """C's fake Kraken client is exactly this: REST only, no stream."""
    result = engine.process(engine_context, fresh_state)
    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["stream_available"] is False
    assert result.data["frames_recorded"] == 0
    assert engine_context.clients.recorder.lines == []


def test_the_loss_counters_are_cumulative_and_surfaced(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any]
) -> None:
    """A buffer overflow is a fault about the process, not about the minute it
    happened in. Zeroing it per tick would make it almost impossible to notice."""
    context, stream = stream_context
    stream.dropped_frames = 7
    stream.unparsed_frames = 3
    data = engine.process(context, fresh_state).data
    assert (data["dropped_frames"], data["unparsed_frames"]) == (7, 3)


# --------------------------------------------------------------------------- #
# End to end, through the real writer
# --------------------------------------------------------------------------- #


def test_a_tick_through_the_real_writer_lands_a_readable_archive(
    engine: MarketDataRecorderEngine, stream_context: Any, fresh_state: dict[str, Any],
    tmp_path: Path,
) -> None:
    context, stream = stream_context
    stream.frames.extend([frame(), frame("ETH/USD")])
    recorder = JsonlRecorder(tmp_path)
    with recorder:
        object.__setattr__(context.clients, "recorder", recorder)
        engine.process(context, fresh_state)

    written = (tmp_path / "kraken_v2_2026-03-01.jsonl").read_text(encoding="utf-8")
    lines = [json.loads(line) for line in written.splitlines() if line.strip()]
    assert [line["pair"] for line in lines] == ["BTC/USD", "ETH/USD"]
