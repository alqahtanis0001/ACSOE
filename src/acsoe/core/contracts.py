"""The fixed engine interface.

This module is the whole of the contract described in ``context/engine-contracts.md``.
It imports **nothing else from this package** — not ``platform``, not ``clients``, not
``engines``, not ``research``. ``Config``, ``Clock`` and ``Clients`` are Protocols
declared here and implemented elsewhere, which is what lets the lead own the shape and
Agent A own the implementation without either writing in the other's directory.

Changing anything in this module requires the lead. Do not add a parameter, a return
type, a status, or a side channel.
"""

from __future__ import annotations

import datetime as _datetime
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

__all__ = [
    "BaseEngine",
    "Chains",
    "Clients",
    "Clock",
    "Config",
    "EngineContext",
    "EngineResult",
    "EngineStatus",
    "Mode",
    "State",
]


Mode = Literal["paper", "live", "replay"]

#: Keyed by engine name. An engine reads other engines' outputs through
#: ``state["<engine_name>"]`` and writes only its own key. Fresh every tick, except for
#: the persistent ``state["system"]`` region the orchestrator carries across.
State = dict[str, Any]


class EngineStatus(StrEnum):
    """Outcome of one engine's run.

    ``StrEnum``, not ``(str, Enum)``, and the difference is load-bearing rather than
    stylistic. Under ``(str, Enum)``, ``str(EngineStatus.ERROR)`` and any f-string
    interpolation of it yield ``"EngineStatus.ERROR"`` instead of ``"ERROR"``. That value
    travels in ``state["guard_blockers"]``, is written by engine 19 to
    ``block_records.status``, and is queried by engine 17 ``safety`` as
    ``status = 'ERROR'`` to compute the error rate that trips the circuit breaker. The
    mismatch would never raise: the breaker's error count would simply read zero forever.
    """

    OK = "OK"
    """Ran, produced output, pipeline continues."""

    PASS = "PASS"
    """Nothing to do this cycle. Not an error."""

    BLOCK = "BLOCK"
    """Halt the pipeline for this cycle."""

    ERROR = "ERROR"
    """Unexpected failure. Treated as BLOCK."""


@runtime_checkable
class Clock(Protocol):
    """Source of time. Held by the orchestrator, never by an engine.

    Engines receive an already-stamped ``context.now`` and never see this object. That is
    what makes replay faithful and look-ahead structurally impossible.
    """

    def now(self) -> _datetime.datetime:
        """Timezone-aware UTC. Never naive."""
        ...


@runtime_checkable
class Config(Protocol):
    """Validated configuration, implemented in ``platform/``.

    Deliberately a read-only mapping-by-attribute rather than a fixed field list: the
    lead owns ``config/default.yaml`` and Agent A owns the model, so pinning field names
    here would put the same keys in two places and let them drift.
    """

    @property
    def mode(self) -> Mode: ...

    def get(self, dotted_key: str, /) -> Any:
        """Look up a value by dotted path, e.g. ``"safety.max_consecutive_data_blocks"``.

        Raises rather than returning a default. A missing configuration key is a defect,
        and an engine silently receiving ``None`` for a threshold is exactly the failure
        this project refuses to allow.
        """
        ...


@runtime_checkable
class Clients(Protocol):
    """The only way an engine reaches the outside world.

    Exactly three, per contract rule 4. An engine never constructs one, never opens a
    socket, and never touches the filesystem directly.
    """

    @property
    def kraken(self) -> Any:
        """Exchange access. Implemented in ``clients/kraken/``."""
        ...

    @property
    def store(self) -> Any:
        """SQLite and Parquet. Implemented in ``clients/store/``."""
        ...

    @property
    def recorder(self) -> Any:
        """Append-only raw JSONL. Used only by engine 2."""
        ...


@dataclass(frozen=True, slots=True)
class EngineContext:
    """What every engine is given. Immutable for the duration of a tick."""

    mode: Mode
    run_id: str
    now: _datetime.datetime
    config: Config
    clients: Clients
    previous_now: _datetime.datetime | None = None
    """When the previous tick of **this process** was stamped, or ``None``.

    Added in Phase 6, spec 85, because an engine that measures an *interval* cannot
    derive one. Engines are stateless across cycles and `state` is fresh every tick, so
    the only way to say "since the last tick" was `now - timeframes.loop_tick_s` — the
    previous tick's time *in a loop that ran on time*. `bar_closed_on` has used that
    device since Phase 2 and it is sound there, because it asks about an index and still
    fires exactly once when the loop runs late. An interval is different: if the loop
    overshoots, the trades in the overshoot fall inside **no** range, and a stop touched
    in that window is missed by engines 21 and 22. Found by A while building engine 3's
    per-tick trade ranges, and reported rather than worked around.

    ``None`` means there is no previous tick: the first tick of a process, a restart, or
    a caller that built a context by hand. **It is not zero and not "a moment ago".** A
    consumer measuring an interval publishes nothing for that tick rather than guessing
    at its start — the same fail-closed reading the gates use, and the honest description
    of the gap a restart leaves.
    """

    def __post_init__(self) -> None:
        if self.now.tzinfo is None:
            raise ValueError(
                "EngineContext.now must be timezone-aware UTC; got a naive datetime. "
                "A naive clock silently reintroduces look-ahead in replay."
            )
        if self.previous_now is not None:
            if self.previous_now.tzinfo is None:
                raise ValueError(
                    "EngineContext.previous_now must be timezone-aware UTC; got a naive "
                    "datetime. A naive clock silently reintroduces look-ahead in replay."
                )
            if self.previous_now > self.now:
                raise ValueError(
                    f"EngineContext.previous_now ({self.previous_now.isoformat()}) is after "
                    f"now ({self.now.isoformat()}). An interval that runs backwards is a "
                    "clock fault, and an engine measuring one would publish a negative span "
                    "rather than refuse."
                )


def _is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _assert_json_serialisable(value: Any, path: str) -> None:
    """Reject anything that is not plain JSON data.

    Contract rule 8. Numpy arrays, dataframes and model objects in ``data`` would make
    ``state`` unserialisable and a decision unauditable, so they are refused at the
    boundary rather than discovered at the point somebody tries to write a log line.

    Raises ``ValueError`` rather than ``TypeError`` even though the fault is a type:
    pydantic wraps only ``ValueError`` and ``AssertionError`` into ``ValidationError``,
    and a caller catching ``ValidationError`` around ``EngineResult(...)`` must not have
    one of the two validators escape as a bare ``TypeError``.

    **This check refuses a ``Decimal`` and accepts a ``float``, and the second half is
    the dangerous one.** It is not a defect here — the validator cannot know which field
    is money, and float is correct for indicators, model inputs and statistics. But an
    engine that hits the ``Decimal`` refusal and reflexively casts to ``float`` publishes
    a fee or an expected move that has already lost precision, and it arrives in engine
    10's hurdle comparison wrong in the fourth decimal, which is the magnitude that gate
    works at. **Money crosses ``state`` as an exact decimal string.** The rule lives in
    ``context/engine-contracts.md`` rule 8 and is enforced per engine by typing money
    fields as ``Money``, the annotated ``Decimal`` that raises on a float rather than
    coercing it. Do not "fix" this function by widening it to accept ``Decimal``: that
    would make ``state`` unserialisable, which is the thing rule 8 exists to prevent.
    """
    if _is_json_scalar(value):
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(
                    f"{path}: JSON object keys must be str, got {type(key).__name__}"
                )
            _assert_json_serialisable(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_json_serialisable(item, f"{path}[{index}]")
        return
    raise ValueError(
        f"{path}: EngineResult.data must be JSON-serialisable; got {type(value).__name__}. "
        "No numpy arrays, no dataframes, no model objects."
    )


class EngineResult(BaseModel):
    """What every engine returns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    engine: str
    status: EngineStatus
    blocks_trading: bool = False
    reason: str | None = None
    data: dict[str, Any] = {}
    duration_ms: float

    @field_validator("data")
    @classmethod
    def _data_is_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        _assert_json_serialisable(value, "data")
        return value

    @model_validator(mode="after")
    def _reason_required_when_blocking(self) -> EngineResult:
        if self.blocks_trading and not (self.reason and self.reason.strip()):
            raise ValueError(
                f"{self.engine}: blocks_trading=True requires a reason, and it must be "
                "specific enough to analyse later. A block whose cause is unrecorded is "
                "lost research data."
            )
        return self


class BaseEngine(ABC):
    """Every engine subclasses this and implements exactly ``process``."""

    name: ClassVar[str]
    number: ClassVar[int]
    is_gate: ClassVar[bool] = False

    @abstractmethod
    def process(self, context: EngineContext, state: State) -> EngineResult:
        """Run one tick's work for this engine.

        The only public entry point. An engine writes exactly one key into ``state`` —
        its own name — and never imports another engine.
        """
        ...


@dataclass(frozen=True, slots=True)
class Chains:
    """The three runtime chains, built by ``bootstrap.py``.

    A named structure rather than three positional sequences, deliberately: transposing
    ``guard`` with ``manage`` would type-check, pass a smoke test, and silently stop
    watching open positions.
    """

    guard: Sequence[BaseEngine] = ()
    opportunity: Sequence[BaseEngine] = ()
    manage: Sequence[BaseEngine] = ()
