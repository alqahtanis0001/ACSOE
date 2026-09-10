"""Tests for the fixed engine interface.

Three of these guard properties that would otherwise fail silently: the import
isolation of ``core/``, the string value of ``EngineStatus``, and the mandatory reason
on a block.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from typing import Any

import pytest
from pydantic import ValidationError

from acsoe.core.contracts import (
    BaseEngine,
    Chains,
    EngineContext,
    EngineResult,
    EngineStatus,
)


def _utc(**kw: int) -> dt.datetime:
    return dt.datetime(2026, 9, 8, tzinfo=dt.UTC, **kw)


class _Config:
    @property
    def mode(self) -> str:
        return "paper"

    def get(self, dotted_key: str, /) -> Any:
        raise KeyError(dotted_key)


class _Clients:
    kraken = object()
    store = object()
    recorder = object()


# --------------------------------------------------------------------------- status


def test_engine_status_str_is_the_value_not_the_repr() -> None:
    """The reason ``EngineStatus`` is a ``StrEnum``.

    Under ``(str, Enum)`` these produce ``"EngineStatus.ERROR"``. That value is written
    to ``block_records.status`` and queried by engine 17 as ``status = 'ERROR'``, so the
    mismatch would not raise — the circuit breaker's error count would read zero forever.
    """
    assert str(EngineStatus.ERROR) == "ERROR"
    assert f"{EngineStatus.ERROR}" == "ERROR"
    # UP031 is suppressed on the next line, and the reason is that obeying it would
    # delete the subject. This test asserts EngineStatus renders as its bare name through
    # every string-conversion route, and percent-formatting is one of the four routes
    # under test: rewriting it as a format specifier makes the line duplicate the f-string
    # case above and stop covering the route it exists for. Same shape as the RUF001
    # minus-sign fixture in tests/console/test_format.py, which `code-standards.md` names
    # as the standing example of a lint that is right in general and wrong on one line.
    assert "%s" % EngineStatus.BLOCK == "BLOCK"  # noqa: UP031
    assert format(EngineStatus.OK) == "OK"
    assert EngineStatus.PASS == "PASS"


def test_engine_status_members_are_exactly_the_contract() -> None:
    assert [s.value for s in EngineStatus] == ["OK", "PASS", "BLOCK", "ERROR"]


# ---------------------------------------------------------------------- import purity


def test_core_imports_nothing_else_from_the_package() -> None:
    """Architecture invariant 0: ``core/`` imports nothing from the rest of the package.

    Run in a subprocess because an earlier import elsewhere in the test session would
    otherwise populate ``sys.modules`` and hide a real violation.
    """
    code = (
        "import sys; import acsoe.core.contracts; "
        "bad=sorted(m for m in sys.modules "
        "if m.startswith('acsoe.') and not m.startswith('acsoe.core')); "
        "print(','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    leaked = [m for m in result.stdout.strip().split(",") if m]
    assert leaked == [], f"core/ leaked imports: {leaked}"


# ---------------------------------------------------------------------------- result


def test_block_without_a_reason_is_refused() -> None:
    with pytest.raises(ValidationError, match="requires a reason"):
        EngineResult(
            engine="cost", status=EngineStatus.BLOCK, blocks_trading=True, duration_ms=1.0
        )


def test_block_with_a_blank_reason_is_refused() -> None:
    with pytest.raises(ValidationError, match="requires a reason"):
        EngineResult(
            engine="cost",
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason="   ",
            duration_ms=1.0,
        )


def test_block_with_a_reason_is_accepted() -> None:
    result = EngineResult(
        engine="cost",
        status=EngineStatus.BLOCK,
        blocks_trading=True,
        reason="net edge -0.21% after fees",
        duration_ms=1.0,
    )
    assert result.blocks_trading is True


@pytest.mark.parametrize(
    "payload",
    [
        {"n": 1, "s": "x", "b": True, "none": None, "f": 0.5},
        {"nested": {"list": [1, 2, {"deep": "ok"}]}},
        {},
    ],
)
def test_json_serialisable_data_is_accepted(payload: dict[str, Any]) -> None:
    EngineResult(engine="e", status=EngineStatus.OK, data=payload, duration_ms=0.1)


def test_non_json_data_is_refused() -> None:
    class Model:
        pass

    with pytest.raises(ValidationError, match="JSON-serialisable"):
        EngineResult(
            engine="prediction",
            status=EngineStatus.OK,
            data={"model": Model()},
            duration_ms=0.1,
        )


def test_non_json_data_nested_is_refused() -> None:
    class Frame:
        pass

    with pytest.raises(ValidationError, match="JSON-serialisable"):
        EngineResult(
            engine="feature",
            status=EngineStatus.OK,
            data={"outer": {"inner": [Frame()]}},
            duration_ms=0.1,
        )


def test_result_is_frozen_and_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EngineResult(
            engine="e", status=EngineStatus.OK, duration_ms=0.1, side_channel="nope"
        )


# --------------------------------------------------------------------------- context


def test_naive_now_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EngineContext(
            mode="paper",
            run_id="r1",
            now=dt.datetime(2026, 9, 8),  # noqa: DTZ001 - deliberately naive
            config=_Config(),
            clients=_Clients(),
        )


def test_context_is_frozen() -> None:
    context = EngineContext(
        mode="paper", run_id="r1", now=_utc(), config=_Config(), clients=_Clients()
    )
    with pytest.raises(Exception):  # noqa: B017 - dataclass raises FrozenInstanceError
        context.mode = "live"  # type: ignore[misc]


# ---------------------------------------------------------------------------- chains


def test_chains_default_to_empty_and_are_named() -> None:
    """An empty chain is valid — Phase 0 registers no engine at all."""
    chains = Chains()
    assert chains.guard == () and chains.opportunity == () and chains.manage == ()


def test_base_engine_cannot_be_instantiated_without_process() -> None:
    class Incomplete(BaseEngine):
        name = "incomplete"
        number = 1

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]
