"""Tests for the three-chain orchestrator.

Each of these guards a property that would fail silently: a chain that stops when it
must not, a blocker that goes unrecorded, or a liquidation that is marked done before it
finished.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

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
    """An empty chain is valid and a tick over it completes cleanly.

    Constructs `Chains()` rather than calling `build_chains()`. It used to call
    `build_chains()`, which was the same defect the Phase 0 criterion
    `orchestrator_empty_registry` had: the assertion below says "empty registry" and
    reading the live registry says "whatever bootstrap currently holds". Those coincided
    until Phase 2 registered engines 1 to 4, at which point this test began asserting
    that four real engines produce no blockers against a fake client -- which they
    correctly do not satisfy, because `market_sensor` publishes no quotes over a
    REST-only fake and `data_guard` blocks.

    The property is worth keeping permanently: it is what stops a future orchestrator
    quietly requiring at least one engine. It just has to be held to a registry this
    test controls.
    """
    orchestrator = _orch(Chains())
    state = orchestrator.tick()
    assert state["cycle_id"] == 1
    assert state["guard_blockers"] == []
    assert state["system"]["mode"] == "idle"
    assert "trading_blocked_by" not in state


def test_cycle_id_increments_and_run_id_is_stable() -> None:
    orchestrator = _orch(Chains())
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


# -- the present-payload shapes, which the absent case cannot stand in for ----
#
# Spec 81. Until Phase 6 the manage chain was engine 19 alone, so `position_manager`
# and `exit` were always *absent* and the absent case was the only one these tests
# exercised. Once 21 and 22 are registered they are always present, and a present
# payload has shapes an absent key does not: an engine that raised publishes `{}`
# (contract rule 7), an engine that tried and failed publishes the flag as False, and
# an engine serialising through anything text-shaped can publish a string.


def test_close_intent_survives_when_the_position_manager_raised() -> None:
    """`ERROR` with an empty payload is present-and-unfinished, not finished.

    Contract rule 7 turns an uncaught exception into `ERROR` with `data={}`, so this
    is the one shape where the payload exists and says nothing at all. It reads as
    *not finished*, which is what stops a crashing engine 21 clearing the kill switch.
    """
    store = _close_all_store()
    pm = _Spy("position_manager", 21, raises=True)
    ex = _Spy("exit", 22, data={"positions_closed": True})
    orchestrator = _orch(Chains(manage=(pm, ex)), store)
    orchestrator.tick()
    assert orchestrator.system["close_intent"] is True, "a raised engine 21 must not finish a close"
    assert store.consumed == []


@pytest.mark.parametrize("cancelled", [False, None])
def test_close_intent_survives_a_flag_that_is_present_and_not_true(cancelled: object) -> None:
    store = _close_all_store()
    pm = _Spy("position_manager", 21, data={"entry_orders_cancelled": cancelled})
    ex = _Spy("exit", 22, data={"positions_closed": True})
    orchestrator = _orch(Chains(manage=(pm, ex)), store)
    orchestrator.tick()
    assert orchestrator.system["close_intent"] is True
    assert store.consumed == []


@pytest.mark.parametrize("flag", ["false", "0", [], {}, 0, 1, "true"])
def test_only_the_boolean_true_clears_the_intent(flag: object) -> None:
    """A non-boolean flag never finishes a liquidation, whatever it is truthy for.

    `bool("false")` is `True`, and so is `bool([1])` and `bool(1)`. A publisher that
    serialised `entry_orders_cancelled` through anything text-shaped would therefore
    have cleared `close_intent` with orders still resting on the book — a fail-open on
    the kill switch, reached without anybody writing a wrong value, only a wrong type.
    The contract calls these fields booleans; anything else is a publisher whose shape
    changed, and the fail-closed reading of a changed shape is "not finished".

    `1` and `"true"` are in the list deliberately: they are the two a reasonable person
    would argue *should* count, and they must not, because accepting them is what makes
    the rule unenforceable at the edge that matters.
    """
    store = _close_all_store()
    pm = _Spy("position_manager", 21, data={"entry_orders_cancelled": flag})
    ex = _Spy("exit", 22, data={"positions_closed": flag})
    orchestrator = _orch(Chains(manage=(pm, ex)), store)
    orchestrator.tick()
    assert orchestrator.system["close_intent"] is True, (
        f"{flag!r} is not the boolean True and must not clear a liquidation"
    )
    assert store.consumed == []


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


# ------------------------------------------------------- _record_run, against a real store


class _RealClients:
    """`Clients` holding a genuine `StoreClient`, not a double.

    Every other test in this file uses `_Store`, which is shaped like the real client
    method for method and is the right tool for the properties they assert. This one
    exists because a double cannot demonstrate the property below: `_record_run` returns
    early unless the store exposes `start_run`, so for a whole phase the only route into
    its body was a real client, and `cli/engine.py` was passing three `None`s. Two lines
    in it duplicated a keyword `_log` already supplies and raised `TypeError` the first
    time they ran. See `code-standards.md` under Testing.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    @property
    def kraken(self) -> Any:
        return object()

    @property
    def store(self) -> Any:
        return self._store

    @property
    def recorder(self) -> Any:
        return object()


def test_a_tick_records_its_run_through_a_real_store_client(tmp_path: Any) -> None:
    """A tick holding a real `StoreClient` completes and writes its `runs` row.

    The assertion is deliberately on the row rather than on "no exception": a `_log`
    call that raises would fail this test either way, but a `_record_run` that silently
    returned early would pass an exception-only assertion while recording nothing, and
    that is the state the daemon was actually in.
    """
    from acsoe.clients.store.client import StoreClient
    from acsoe.platform.logging import get_logger

    store = StoreClient(str(tmp_path / "acsoe.sqlite"))
    store.migrate()
    try:
        orch = Orchestrator(
            config=_Config(),
            clock=_Clock(),
            clients=_RealClients(store),
            chains=Chains(),
            # A REAL logger, and it is the whole point of this test. `_log` opens with
            # `if self._logger is None: return`, so an orchestrator built without one
            # never reaches the logging call and cannot exhibit the bug this test exists
            # for. The first version of this test passed against the unfixed code for
            # exactly that reason. Two absences were hiding it — no real store in the
            # CLI, no real logger in the tests — and a test needs both halves present.
            logger=get_logger("acsoe.test.orchestrator"),
        )
        orch.tick()
        orch.tick()

        runs = store.latest_runs(5)
        assert [r.run_id for r in runs].count(orch.run_id) == 1, (
            "_record_run must write exactly one runs row for this run_id, and write it "
            "once across two ticks rather than on every tick"
        )
        assert runs[0].mode == "paper"

        # The mode column stays NULL here and that is correct, not a half-delivery.
        # `_persist_mode` is called from the command reader after a transition has been
        # applied, and a daemon that starts idle and receives no command has entered no
        # mode to record. Asserted rather than left implicit, because the null is the
        # kind of thing a later reader "fixes".
        assert store.system_mode(orch.run_id).mode is None
    finally:
        store.close()


def test_the_run_record_failure_branch_logs_instead_of_killing_the_loop(
    tmp_path: Any,
) -> None:
    """The `except` around `start_run` exists so a bookkeeping row can never stop the
    loop. It contained the same duplicated keyword, so the branch that protects the loop
    would itself have raised — turning a logged warning into a dead daemon. Driven by a
    store whose `start_run` raises, which is the only way into it.
    """

    class _RaisingStore:
        def start_run(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("bookkeeping is unavailable")

        def set_system_mode(self, *args: Any, **kwargs: Any) -> bool:
            return False

    from acsoe.platform.logging import get_logger

    orch = Orchestrator(
        config=_Config(),
        clock=_Clock(),
        clients=_RealClients(_RaisingStore()),
        chains=Chains(),
        logger=get_logger("acsoe.test.orchestrator"),
    )

    state = orch.tick()

    assert state is not None
