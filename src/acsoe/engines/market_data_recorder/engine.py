"""Engine 2 `market_data_recorder` — the framework recorder.

Drains everything the WebSocket stream buffered since the last tick and appends it,
verbatim, to the append-only archive in `data/raw/`. Supersedes `scripts/record.py`,
which stays on disk and stays working as the fallback for when the engine framework
is down.

**It runs in the guard chain, every tick, in every mode.** A freeze stops trading; it
never stops data collection. Order-book and spread history cannot be recovered
retroactively, so a minute not recorded is a minute gone — which is why the guard
chain runs in `idle` and `frozen` as well as `running`, and why this engine is in it.

**It is not a gate and it never blocks.** A dead feed is engine 4 `data_guard`'s
judgement to make, on the market data itself; engine 2's job is to write down what
arrived and what did not.

**A break is written into the archive, never healed.** Gaps are drained from the
stream and appended as `gap` marker lines carrying their own cause, so a silent
outage cannot be mistaken later for a quiet market.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, ClassVar

from acsoe.clients.recorder.contracts import RECORDER_CHANNEL, build_line
from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.market_data_recorder.contracts import RecorderState

__all__ = ["MarketDataRecorderEngine"]


def _iso(moment: Any) -> str:
    """ISO-8601 UTC ending in ``Z``, the form the recording schema requires."""
    text: str = moment.isoformat()
    return text.replace("+00:00", "Z") if text.endswith("+00:00") else text + "Z"


class MarketDataRecorderEngine(BaseEngine):
    """Raw market data to `data/raw/`, every tick, in every mode."""

    name: ClassVar[str] = "market_data_recorder"
    number: ClassVar[int] = 2
    #: Registry table in `context/engine-contracts.md` marks engine 2 with no Gate.
    is_gate: ClassVar[bool] = False

    # ARG002: `state` is unused and stays in the signature — the interface is fixed
    # and the orchestrator calls it positionally. This engine records the feed; it
    # reads nothing another engine wrote.
    def process(self, context: EngineContext, state: State) -> EngineResult:  # noqa: ARG002
        started = time.perf_counter()
        stream = context.clients.kraken
        recorder = context.clients.recorder

        drain = getattr(stream, "drain", None)
        if not callable(drain):
            # No stream on this client. Reported, not raised: a client double without
            # one is a legitimate thing to be handed, and raising here would take the
            # whole guard chain to ERROR on a tick where nothing is actually wrong.
            payload = RecorderState(
                stream_available=False,
                connected=False,
                frames_recorded=0,
                gaps_recorded=0,
                dropped_frames=0,
                unparsed_frames=0,
            )
            return EngineResult(
                engine=self.name,
                status=EngineStatus.OK,
                data=payload.to_state(),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        frames = tuple(drain())
        for frame in frames:
            recorder.append(
                build_line(
                    kind="tick",
                    pair=frame.pair,
                    channel=frame.channel,
                    ts_exchange=frame.ts_exchange,
                    ts_recv=frame.ts_recv,
                    # Verbatim. Invariant 11: a recording is never edited, cleaned or
                    # normalised on the way in.
                    payload=frame.payload,
                )
            )

        gaps = self._drain_gaps(stream)
        fallback_ts = _iso(context.now)
        for gap in gaps:
            recorder.append(
                build_line(
                    kind="gap",
                    pair=None,
                    channel=RECORDER_CHANNEL,
                    ts_exchange=None,
                    # The gap's own end, so the marker sits at the moment the break
                    # closed rather than at the moment the loop happened to notice.
                    ts_recv=str(gap.get("ended_at") or fallback_ts),
                    payload=dict(gap),
                )
            )

        payload = RecorderState(
            stream_available=True,
            connected=bool(getattr(stream, "connected", False)),
            frames_recorded=len(frames),
            gaps_recorded=len(gaps),
            dropped_frames=int(getattr(stream, "dropped_frames", 0)),
            unparsed_frames=int(getattr(stream, "unparsed_frames", 0)),
        )
        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            data=payload.to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    @staticmethod
    def _drain_gaps(stream: Any) -> tuple[Mapping[str, Any], ...]:
        """Take the breaks recorded since the last tick, and clear them.

        Drained rather than read so this engine stays stateless across cycles
        (architecture invariant 1): it never has to remember which breaks it has
        already written into the archive, which is the kind of bookkeeping that
        silently duplicates or silently drops one after a restart.
        """
        drain_gaps = getattr(stream, "drain_gaps", None)
        if not callable(drain_gaps):
            return ()
        return tuple(drain_gaps())
