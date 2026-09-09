"""What engine 2 `market_data_recorder` publishes into ``state``.

Counters, not data. The recording itself goes to `data/raw/`; what reaches ``state``
is how much of it arrived this tick and what was lost, so the console and the log can
see the feed's health without anything having to re-read a gigabyte.

Every field here is a count of something that **would otherwise be invisible**. A
recorder that quietly wrote nothing looks exactly like a quiet market, and that is the
failure the whole recording exists to make impossible.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = ["STATE_KEY", "RecorderState"]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "market_data_recorder"


class RecorderState(BaseModel):
    """The whole of ``state["market_data_recorder"]``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stream_available: bool
    """False when the injected client exposes no market stream at all.

    Not an error and not a block. A client double without a stream is a legitimate
    thing for another agent to hand this engine — C's fake Kraken client is exactly
    that — and an engine that raised on it would make the orchestrator untestable.
    """

    connected: bool
    """Whether the stream believes it has a live socket right now."""

    frames_recorded: int
    """Raw frames appended to the archive this tick."""

    gaps_recorded: int
    """Breaks written into the archive this tick, each with its own cause."""

    dropped_frames: int
    """Cumulative frames the stream lost to a full buffer.

    Cumulative rather than per-tick on purpose: a buffer overflow is a fault about the
    process, not about the minute it happened in, and zeroing it every tick would make
    it almost impossible to notice.
    """

    unparsed_frames: int
    """Cumulative frames recorded verbatim that yielded neither a trade nor a quote.

    The cost of the lenient parse. A frame nobody understood is still in the archive —
    which is the half that cannot be recovered — but a rising number here means the
    field names in ``clients/kraken/ws.py`` no longer match what Kraken sends.
    """

    def to_state(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.model_dump(mode="json")
        return payload
