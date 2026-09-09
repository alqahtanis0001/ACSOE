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
    """A double shaped like the **real** `StoreClient`, method for method.

    It used to expose `claim_pending_commands` and a `mark_close_all_consumed`, neither
    of which `StoreClient` has ever had. The orchestrator reached for both through
    `getattr`, found them here and nowhere else, and every test passed while a daemon
    wired to the real store ignored every command ever written. That is the whole
    lesson of the Phase 1 close: a seam exercised only through a double is not tested,
    the double is. The four methods below are the four the store really exposes, with
    the real signatures and the real `claimed_at IS NULL` semantics.

    The definitive guard against this recurring is `commands_round_trip` in
    `scripts/verify.py`, which drives the genuine `StoreClient` and never sees this
    class. This double now exists for the cases that criterion cannot reach cheaply —
    a store that is missing a method, a row with no id.
    """

    def __init__(self, commands: list[dict[str, Any]] | None = None) -> None:
        self._rows: list[dict[str, Any]] = []
        for index, command in enumerate(commands or [], start=1):
            row = dict(command)
            row.setdefault("id", index)
            row.setdefault("claimed_at", None)
            row.setdefault("consumed_at", None)
            self._rows.append(row)
        self.consumed: list[str] = []

    # -- reads ---------------------------------------------------------------

    def pending_commands(self) -> list[dict[str, Any]]:
        """Never-claimed rows, oldest first — `claimed_at IS NULL`."""
        return [r for r in self._rows if r["claimed_at"] is None]

    def claimed_unconsumed_commands(self) -> list[dict[str, Any]]:
        """Interrupted rows: claimed by some run, never completed."""
        return [
            r for r in self._rows if r["claimed_at"] is not None and r["consumed_at"] is None
        ]

    # -- writes --------------------------------------------------------------

    def claim_command(self, command_id: int, *, claimed_at: int, run_id: str) -> bool:
        """Returns False if the row was already claimed. That guard is the idempotency."""
        for row in self._rows:
            if row["id"] == command_id and row["claimed_at"] is None:
                row["claimed_at"] = claimed_at
                row["claimed_by_run_id"] = run_id
                return True
        return False

    def mark_command_consumed(self, command_id: int, *, consumed_at: int) -> bool:
        for row in self._rows:
            if row["id"] == command_id and row["consumed_at"] is None:
                row["consumed_at"] = consumed_at
                self.consumed.append(str(row["command"]))
                return True
        return False

    # -- helpers for assertions ----------------------------------------------

    def row(self, command_id: int) -> dict[str, Any]:
        return next(r for r in self._rows if r["id"] == command_id)


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
    assert store.consumed == [], "an unfinished close_all must stay unconsumed"


def test_close_intent_survives_when_only_one_engine_reports_done() -> None:
    store = _close_all_store()
    pm = _Spy("position_manager", 21, data={"entry_orders_cancelled": True})
    ex = _Spy("exit", 22, data={"positions_closed": False})
    orchestrator = _orch(Chains(manage=(pm, ex)), store)
    orchestrator.tick()
    assert orchestrator.system["close_intent"] is True, "a failed close must retry next tick"
    assert store.consumed == [], "an unfinished close_all must stay unconsumed"


def test_close_intent_clears_only_when_both_report_done() -> None:
    store = _close_all_store()
    pm = _Spy("position_manager", 21, data={"entry_orders_cancelled": True})
    ex = _Spy("exit", 22, data={"positions_closed": True})
    orchestrator = _orch(Chains(manage=(pm, ex)), store)
    orchestrator.tick()
    assert orchestrator.system["close_intent"] is False
    assert store.consumed == ["close_all"]
    assert store.row(1)["consumed_at"] is not None, (
        "phase two of the two-phase consumption stamps the real row, not a counter"
    )


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
    """Ignored, and *consumed* — because ignoring is a decision, and it is complete.

    `architecture-context.md` says an unrecognised command is ignored and logged and
    never blocks the loop. It says nothing about consumption, and leaving it unconsumed
    is the trap: `pending_commands` filters on `claimed_at IS NULL`, so the row would be
    claimed on this tick, never appear as pending again, and sit claimed-and-unconsumed
    forever — which is exactly the shape the startup replay looks for. Every restart for
    the life of the database would re-apply it. Consuming it is what stops a typo
    becoming a permanent fixture of every boot.
    """
    store = _Store([{"command": "self_destruct"}, {"command": "activate"}])
    orchestrator = _orch(Chains(), store)
    orchestrator.tick()
    assert orchestrator.system["mode"] == "running"
    assert store.consumed == ["self_destruct", "activate"]
    assert store.claimed_unconsumed_commands() == [], (
        "an ignored command must not be left for the startup replay to find"
    )


# ------------------------------------------------------- startup re-application


def _interrupted(command: str) -> _Store:
    """A row a previous process claimed and never finished."""
    return _Store([{"command": command, "claimed_at": 1, "claimed_by_run_id": "run-earlier"}])


def test_an_interrupted_close_all_is_re_applied_before_the_first_tick() -> None:
    """The failure the kill switch exists to prevent.

    A daemon killed between reading `close_all` and finishing the liquidation must not
    come back with the command marked done and positions still open. Mode is still never
    restored — it starts idle and this replays the *command*, which is what drags the
    intent back.
    """
    store = _interrupted("close_all")
    orchestrator = _orch(Chains(), store)
    orchestrator.tick()
    assert orchestrator.system["close_intent"] is True
    assert orchestrator.system["mode"] == "frozen"
    assert store.consumed == [], "it is not finished, so it is not consumed"


def test_the_startup_replay_runs_once_and_not_every_tick() -> None:
    """Re-applying on every tick would make a completed close_all immortal."""
    store = _interrupted("close_all")
    pm = _Spy("position_manager", 21, data={"entry_orders_cancelled": True})
    ex = _Spy("exit", 22, data={"positions_closed": True})
    orchestrator = _orch(Chains(manage=(pm, ex)), store)

    orchestrator.tick()
    assert orchestrator.system["close_intent"] is False
    assert store.consumed == ["close_all"]

    orchestrator.tick()
    assert orchestrator.system["close_intent"] is False, (
        "a finished close_all must not be resurrected by a second replay"
    )


def test_an_interrupted_mode_change_is_re_applied_and_then_consumed() -> None:
    store = _interrupted("freeze")
    orchestrator = _orch(Chains(), store)
    orchestrator.tick()
    assert orchestrator.system["mode"] == "frozen"
    assert store.consumed == ["freeze"]


def test_a_store_without_the_interrupted_reader_still_ticks() -> None:
    """Tolerance, not silence: the tick completes and the gap is logged."""

    class _Partial(_Store):
        claimed_unconsumed_commands = None  # type: ignore[assignment]

    store = _Partial([{"command": "activate"}])
    orchestrator = _orch(Chains(), store)
    orchestrator.tick()
    assert orchestrator.system["mode"] == "running", "the pending read still works"


def test_mode_always_starts_idle() -> None:
    """Never restored from the store: a crashed daemon comes back not trading."""
    assert _orch(Chains()).system["mode"] == "idle"
