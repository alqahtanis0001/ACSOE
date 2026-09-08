"""Tests for the three-chain orchestrator.

Each of these guards a property that would fail silently: a chain that stops when it
must not, a blocker that goes unrecorded, or a liquidation that is marked done before it
finished.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from acsoe.bootstrap import build_chains
from acsoe.core.contracts import (
    BaseEngine,
    Chains,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.core.orchestrator import Orchestrator


class _Clock:
    def __init__(self) -> None:
        self._t = dt.datetime(2026, 9, 8, 12, 0, tzinfo=dt.UTC)

    def now(self) -> dt.datetime:
        self._t += dt.timedelta(minutes=1)
        return self._t


class _Config:
    @property
    def mode(self) -> str:
        return "paper"

    def get(self, dotted_key: str, /) -> Any:
        raise KeyError(dotted_key)


class _Store:
    def __init__(self, commands: list[dict[str, Any]] | None = None) -> None:
        self._pending = list(commands or [])
        self.consumed: list[str] = []
        self.close_all_consumed = 0

    def claim_pending_commands(self, *, run_id: str, now: dt.datetime) -> list[dict[str, Any]]:
        claimed, self._pending = self._pending, []
        return claimed

    def mark_command_consumed(self, command: dict[str, Any], *, now: dt.datetime) -> None:
        self.consumed.append(command["command"])

    def mark_close_all_consumed(self, *, run_id: str, now: dt.datetime) -> None:
        self.close_all_consumed += 1


class _Clients:
    def __init__(self, store: _Store | None = None) -> None:
        self._store = store or _Store()

    @property
    def kraken(self) -> Any:
        return object()

    @property
    def store(self) -> _Store:
        return self._store

    @property
    def recorder(self) -> Any:
        return object()


class _Spy(BaseEngine):
    """Records that it ran, and returns whatever the test asked for."""

    def __init__(
        self,
        name: str,
        number: int,
        *,
        status: EngineStatus = EngineStatus.OK,
        blocks: bool = False,
        reason: str | None = None,
        data: dict[str, Any] | None = None,
        raises: bool = False,
    ) -> None:
        self.name = name  # type: ignore[misc]
        self.number = number  # type: ignore[misc]
        self.ran = 0
        self._status = status
        self._blocks = blocks
        self._reason = reason
        self._data = data or {}
        self._raises = raises

    def process(self, context: EngineContext, state: State) -> EngineResult:
        self.ran += 1
        if self._raises:
            raise RuntimeError("engine exploded")
        return EngineResult(
            engine=self.name,
            status=self._status,
            blocks_trading=self._blocks,
            reason=self._reason,
            data=self._data,
            duration_ms=0.1,
        )


def _orch(chains: Chains, store: _Store | None = None) -> Orchestrator:
    return Orchestrator(
        config=_Config(), clock=_Clock(), clients=_Clients(store), chains=chains
    )


# ------------------------------------------------------------------ empty registry


def test_empty_registry_ticks_cleanly() -> None:
    """Phase 0's exit criterion. An empty chain is valid."""
    orchestrator = _orch(build_chains())
    state = orchestrator.tick()
    assert state["cycle_id"] == 1
    assert state["guard_blockers"] == []
    assert state["system"]["mode"] == "idle"
    assert "trading_blocked_by" not in state


def test_cycle_id_increments_and_run_id_is_stable() -> None:
    orchestrator = _orch(build_chains())
    first, second = orchestrator.tick(), orchestrator.tick()
    assert (first["cycle_id"], second["cycle_id"]) == (1, 2)
    assert orchestrator.run_id  # minted once, lives only on the context


def test_state_is_fresh_each_tick_except_system() -> None:
    guard = _Spy("exchange", 1, data={"x": 1})
    orchestrator = _orch(Chains(guard=(guard,)))
    first = orchestrator.tick()
    first["scribble"] = "should not survive"
    second = orchestrator.tick()
    assert "scribble" not in second
    assert second["system"] is first["system"]  # the one carried region


# ------------------------------------------------------------------- guard chain


def test_guard_chain_never_breaks_early_and_records_every_blocker() -> None:
    """A bad-data block must not stop `safety` evaluating, and both must be recorded."""
    data_guard = _Spy("data_guard", 4, status=EngineStatus.BLOCK, blocks=True, reason="stale")
    safety = _Spy("safety", 17, status=EngineStatus.BLOCK, blocks=True, reason="drawdown")
    state = _orch(Chains(guard=(data_guard, safety))).tick()

    assert safety.ran == 1, "safety must run even though data_guard blocked first"
    assert state["trading_blocked_by"] == "data_guard"  # first is primary
    assert state["block_reason"] == "stale"
    assert [b["engine"] for b in state["guard_blockers"]] == ["data_guard", "safety"]
    assert [b["reason"] for b in state["guard_blockers"]] == ["stale", "drawdown"]


def test_guard_blocker_status_is_the_string_value() -> None:
    """Engine 19 writes this into block_records.status, which safety filters on."""
    boom = _Spy("data_guard", 4, status=EngineStatus.ERROR, blocks=True, reason="x")
    state = _orch(Chains(guard=(boom,))).tick()
    assert state["guard_blockers"][0]["status"] == "ERROR"


def test_guard_chain_runs_in_every_mode() -> None:
    """Freeze must never stop data collection."""
    recorder = _Spy("market_data_recorder", 2)
    orchestrator = _orch(Chains(guard=(recorder,)))
    orchestrator.system["mode"] = "frozen"
    orchestrator.tick()
    orchestrator.system["mode"] = "idle"
    orchestrator.tick()
    assert recorder.ran == 2


# ------------------------------------------------------------- opportunity chain


def test_opportunity_chain_is_skipped_unless_running() -> None:
    feature = _Spy("feature", 5)
    orchestrator = _orch(Chains(opportunity=(feature,)))
    orchestrator.tick()  # idle
    assert feature.ran == 0
    orchestrator.system["mode"] = "running"
    orchestrator.tick()
    assert feature.ran == 1


def test_opportunity_chain_is_skipped_when_a_guard_blocked() -> None:
    guard = _Spy("data_guard", 4, status=EngineStatus.BLOCK, blocks=True, reason="stale")
    feature = _Spy("feature", 5)
    orchestrator = _orch(Chains(guard=(guard,), opportunity=(feature,)))
    orchestrator.system["mode"] = "running"
    orchestrator.tick()
    assert feature.ran == 0


def test_opportunity_chain_stops_at_the_first_pass() -> None:
    """Fourteen ticks in fifteen: no bar closed, so `feature` PASSes and nothing follows."""
    feature = _Spy("feature", 5, status=EngineStatus.PASS)
    scout = _Spy("scout", 7)
    orchestrator = _orch(Chains(opportunity=(feature, scout)))
    orchestrator.system["mode"] = "running"
    orchestrator.tick()
    assert (feature.ran, scout.ran) == (1, 0)


def test_opportunity_chain_stops_at_the_first_block() -> None:
    cost = _Spy("cost", 10, status=EngineStatus.BLOCK, blocks=True, reason="net edge -0.21%")
    execution = _Spy("execution", 18)
    orchestrator = _orch(Chains(opportunity=(cost, execution)))
    orchestrator.system["mode"] = "running"
    state = orchestrator.tick()
    assert execution.ran == 0
    assert state["trading_blocked_by"] == "cost"


# ------------------------------------------------------------------ manage chain


def test_manage_chain_runs_even_when_everything_else_was_skipped() -> None:
    """An unwatched position is lost money. This is the whole reason it is its own chain."""
    guard = _Spy("data_guard", 4, status=EngineStatus.BLOCK, blocks=True, reason="stale")
    manage = [_Spy("position_manager", 21), _Spy("exit", 22), _Spy("memory", 19)]
    orchestrator = _orch(Chains(guard=(guard,), manage=tuple(manage)))
    orchestrator.tick()
    assert [m.ran for m in manage] == [1, 1, 1]


# ------------------------------------------------------------------------ errors


def test_a_raising_engine_becomes_error_and_blocks_without_killing_the_tick() -> None:
    """Contract rule 7. The manage chain must still run so engine 19 records it."""
    boom = _Spy("exchange", 1, raises=True)
    memory = _Spy("memory", 19)
    state = _orch(Chains(guard=(boom,), manage=(memory,))).tick()
    assert memory.ran == 1
    assert state["trading_blocked_by"] == "exchange"
    assert state["guard_blockers"][0]["status"] == "ERROR"
    assert "RuntimeError" in state["block_reason"]


# -------------------------------------------------------------------- close_all


def _close_all_store() -> _Store:
    return _Store([{"command": "close_all"}])


def test_close_all_sets_intent_and_freezes() -> None:
    store = _close_all_store()
    state = _orch(Chains(), store).tick()
    assert state["system"]["mode"] == "frozen"
    assert state["system"]["close_intent"] is True


def test_close_intent_survives_when_a_flag_is_missing() -> None:
    """Absent reads as 'not finished', never as 'finished'."""
    store = _close_all_store()
    orchestrator = _orch(Chains(), store)
    orchestrator.tick()
    assert orchestrator.system["close_intent"] is True
    assert store.close_all_consumed == 0


def test_close_intent_survives_when_only_one_engine_reports_done() -> None:
    store = _close_all_store()
    pm = _Spy("position_manager", 21, data={"entry_orders_cancelled": True})
    ex = _Spy("exit", 22, data={"positions_closed": False})
    orchestrator = _orch(Chains(manage=(pm, ex)), store)
    orchestrator.tick()
    assert orchestrator.system["close_intent"] is True, "a failed close must retry next tick"
    assert store.close_all_consumed == 0


def test_close_intent_clears_only_when_both_report_done() -> None:
    store = _close_all_store()
    pm = _Spy("position_manager", 21, data={"entry_orders_cancelled": True})
    ex = _Spy("exit", 22, data={"positions_closed": True})
    orchestrator = _orch(Chains(manage=(pm, ex)), store)
    orchestrator.tick()
    assert orchestrator.system["close_intent"] is False
    assert store.close_all_consumed == 1


def test_close_all_is_not_marked_consumed_on_the_claiming_tick() -> None:
    """A daemon killed mid-liquidation must re-apply the command, not skip it."""
    store = _close_all_store()
    _orch(Chains(), store).tick()
    assert store.consumed == [], "close_all must not be consumed before it finishes"


@pytest.mark.parametrize(("command", "mode"), [("activate", "running"), ("freeze", "frozen")])
def test_pure_mode_changes_are_consumed_immediately(command: str, mode: str) -> None:
    store = _Store([{"command": command}])
    orchestrator = _orch(Chains(), store)
    orchestrator.tick()
    assert orchestrator.system["mode"] == mode
    assert store.consumed == [command]


def test_an_unrecognised_command_is_ignored_and_never_blocks_the_loop() -> None:
    store = _Store([{"command": "self_destruct"}, {"command": "activate"}])
    orchestrator = _orch(Chains(), store)
    orchestrator.tick()
    assert orchestrator.system["mode"] == "running"
    assert store.consumed == ["activate"]


def test_mode_always_starts_idle() -> None:
    """Never restored from the store: a crashed daemon comes back not trading."""
    assert _orch(Chains()).system["mode"] == "idle"
