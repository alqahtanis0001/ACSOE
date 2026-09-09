"""The three-chain orchestrator.

One tick of the runtime loop, exactly as specified in ``context/engine-contracts.md``.
Like ``core.contracts``, this module imports nothing else from the package: engines
arrive as a ``Chains`` value and the outside world arrives through the ``Clients``
Protocol.

Changing chain semantics requires the lead. The three properties most likely to be
"simplified" away, each of which costs money or research data:

* the guard chain runs in every mode and never breaks early, so a freeze cannot stop
  data collection and a bad-data block cannot stop the circuit breaker evaluating;
* the manage chain runs on every tick regardless of what the opportunity chain did, so
  an open position is never unwatched for the fourteen ticks in fifteen where no bar
  closed;
* ``close_intent`` is cleared by this module and only once both manage-chain engines
  report the close finished, so a failed cancel retries instead of being lost.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from acsoe.core.contracts import (
    Chains,
    Clients,
    Clock,
    Config,
    EngineContext,
    EngineResult,
    EngineStatus,
    Mode,
    State,
)

if TYPE_CHECKING:
    from acsoe.core.contracts import BaseEngine

__all__ = ["Orchestrator"]

_MICROSECONDS_PER_SECOND = 1_000_000


def _to_micros(moment: datetime) -> int:
    """Microseconds since the epoch, UTC.

    Duplicated deliberately rather than imported from ``clients/store/contracts.py``.
    Invariant 0 says ``core/`` imports nothing from the rest of the package, and that
    boundary is worth more than six lines of reuse: it is what lets the lead own the
    shape while Agent A and Agent B own the implementations. The store's ``to_micros``
    raises on a naive datetime; here the ``Clock`` Protocol already promises
    timezone-aware UTC, and ``astimezone`` on a naive value would silently assume local
    time, so a naive datetime is a defect worth failing on rather than converting.
    """
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware; naive datetimes are a defect")
    return int(moment.astimezone(UTC).timestamp() * _MICROSECONDS_PER_SECOND)


class Orchestrator:
    """Runs one tick. The loop that calls it repeatedly belongs to the CLI."""

    def __init__(
        self,
        *,
        config: Config,
        clock: Clock,
        clients: Clients,
        chains: Chains | None = None,
        run_id: str | None = None,
        logger: Any | None = None,
    ) -> None:
        self._config = config
        self._clock = clock
        self._clients = clients
        self._chains = chains if chains is not None else Chains()
        self._logger = logger
        self._cycle_id = 0

        # run_id is minted once per process and lives only on the context. It is never
        # duplicated into state.
        self._run_id = run_id if run_id is not None else self._mint_run_id()

        # The one region of state that survives a tick. Mode always starts idle and is
        # never restored from the store: a daemon that crashed while trading comes back
        # not trading, with the manage chain still watching whatever is open.
        self._system: dict[str, Any] = {"mode": "idle", "close_intent": False}

        # The `commands` row id of an accepted `close_all`, held until both manage-chain
        # engines report the liquidation finished. Two-phase consumption is what stops a
        # crash swallowing a kill switch, so the id has to outlive the tick that read it.
        self._pending_close_all_id: int | None = None

        # Interrupted commands are re-applied once, before the first tick's own read.
        self._startup_replayed = False

    # ------------------------------------------------------------------ properties

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def cycle_id(self) -> int:
        return self._cycle_id

    @property
    def system(self) -> dict[str, Any]:
        """The persistent region. Read-only to callers by convention."""
        return self._system

    # --------------------------------------------------------------------- helpers

    def _mint_run_id(self) -> str:
        stamp = self._clock.now().strftime("%Y%m%dT%H%M%S%f")
        return f"run-{stamp}"

    def _log(self, event: str, **fields: Any) -> None:
        if self._logger is None:
            return
        self._logger.debug(event, run_id=self._run_id, cycle_id=self._cycle_id, **fields)

    def _context(self) -> EngineContext:
        mode: Mode = self._system["mode"] if self._system["mode"] != "idle" else self._config.mode
        return EngineContext(
            mode=mode,
            run_id=self._run_id,
            now=self._clock.now(),
            config=self._config,
            clients=self._clients,
        )

    def _run(self, engine: BaseEngine, context: EngineContext, state: State) -> EngineResult:
        """Run one engine, converting any uncaught exception into ERROR.

        Contract rule 7. An engine that raises must not take the tick down with it: the
        manage chain still has to run so engine 19 records what happened, and a raised
        exception that stopped the loop would lose exactly the rejection the memory
        engine exists to keep.
        """
        started = time.perf_counter()
        try:
            result = engine.process(context, state)
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self._log(
                "engine_error", engine=engine.name, error=repr(exc), duration_ms=duration_ms
            )
            return EngineResult(
                engine=engine.name,
                status=EngineStatus.ERROR,
                blocks_trading=True,
                reason=f"unhandled {type(exc).__name__}: {exc}",
                data={},
                duration_ms=duration_ms,
            )
        return result

    # ------------------------------------------------------------------------ tick

    def tick(self) -> State:
        """Run one full tick and return the finished ``state``.

        ``state`` is a fresh dict every tick. Nothing survives to the next tick except
        ``state["system"]``, which this object carries across.
        """
        self._cycle_id += 1
        context = self._context()

        state: State = {
            "system": self._system,
            "cycle_id": self._cycle_id,
            "guard_blockers": [],
        }

        self._consume_commands()

        self._run_guard_chain(context, state)
        self._run_opportunity_chain(context, state)
        self._run_manage_chain(context, state)
        self._clear_close_intent_if_finished(state)

        return state

    # ----------------------------------------------------------------- step 0: cmds

    def _consume_commands(self) -> None:
        """Read pending commands at the top of the tick, before the guard chain.

        Two-phase: a row is stamped ``claimed_at`` when read and the effect applied
        immediately; ``consumed_at`` is stamped only when the effect is complete. For
        ``activate`` and ``freeze`` that is now, because they are pure mode changes. For
        ``close_all`` it is deferred to step 4, so a daemon killed mid-liquidation
        re-applies the command on restart instead of coming back with it marked done and
        positions still open.

        Composed from the four reads and writes ``StoreClient`` actually exposes —
        ``claimed_unconsumed_commands``, ``pending_commands``, ``claim_command`` and
        ``mark_command_consumed`` — rather than from a single compound method. Until the
        Phase 1 close this looked up ``store.claim_pending_commands``, which the store
        has never had: the ``getattr`` returned ``None``, this method logged one debug
        line and returned, and **a daemon wired to the real store ignored every command
        ever written.** It passed every gate because the only implementations of that
        shape were test doubles. A seam exercised solely through a double is not tested;
        the double is.
        """
        store = self._store()
        if store is None:
            self._log("commands_skipped", reason="no store client")
            return

        # Interrupted commands come first, before this run reads anything of its own.
        if not self._startup_replayed:
            self._replay_interrupted_commands(store)
            self._startup_replayed = True

        pending = getattr(store, "pending_commands", None)
        claim = getattr(store, "claim_command", None)
        if pending is None or claim is None:
            self._log(
                "commands_skipped",
                reason="store exposes no command reader",
                has_pending_commands=pending is not None,
                has_claim_command=claim is not None,
            )
            return

        stamp = _to_micros(self._clock.now())
        for row in pending():
            command_id = self._command_id(row)
            if command_id is None:
                self._log("command_without_id", command=str(self._command_name(row)))
                continue
            # `claim_command` guards on `claimed_at IS NULL`, so a row already claimed
            # returns False and is never applied twice within a run.
            if not claim(command_id, claimed_at=stamp, run_id=self._run_id):
                self._log("command_already_claimed", command_id=command_id)
                continue
            self._apply_command(store, row, command_id, stamp)

    def _replay_interrupted_commands(self, store: Any) -> None:
        """Re-apply every row claimed by an earlier process that never completed.

        ``architecture-context.md`` names the exact failure this prevents: a daemon
        killed between reading ``close_all`` and finishing the liquidation restarts with
        the command marked done, the in-memory intent gone, and positions still open —
        the one failure the kill switch exists to prevent. Mode is still never restored
        from the store; this replays *commands*, and an interrupted ``close_all``
        therefore completes even though the mode reverted to idle.

        The rows are already claimed, so they are not claimed again. That is what makes
        this idempotent across repeated restarts.
        """
        read = getattr(store, "claimed_unconsumed_commands", None)
        if read is None:
            self._log("startup_replay_skipped", reason="store exposes no interrupted-command reader")
            return

        stamp = _to_micros(self._clock.now())
        replayed = 0
        for row in read():
            command_id = self._command_id(row)
            if command_id is None:
                continue
            self._apply_command(store, row, command_id, stamp)
            replayed += 1
        if replayed:
            self._log("startup_replay", commands=replayed)

    def _apply_command(self, store: Any, row: Any, command_id: int, stamp: int) -> None:
        """Apply one already-claimed command and consume it if the effect is complete."""
        name = self._command_name(row)
        if name == "activate":
            self._system["mode"] = "running"
        elif name == "freeze":
            self._system["mode"] = "frozen"
        elif name == "close_all":
            self._system["mode"] = "frozen"
            self._system["close_intent"] = True
            self._pending_close_all_id = command_id
        else:
            # Never blocks the loop. A CHECK constraint on the column would have made
            # this path unreachable and untestable, which is why there isn't one.
            #
            # It *is* consumed, though. `pending_commands` filters on an unclaimed row,
            # so an unrecognised command that stayed unconsumed would sit claimed and
            # unconsumed forever and be re-applied by the startup replay on every
            # restart for the life of the database. "Ignored" is a decision, and a
            # decision is complete the moment it is taken.
            self._log("command_unrecognised", command=str(name))
            self._consume(store, command_id, stamp)
            return

        self._log("command_applied", command=str(name), mode=self._system["mode"])
        # `activate` and `freeze` are pure mode changes and are complete now.
        # `close_all` is consumed in step 4, and only once both engines report done.
        if name != "close_all":
            self._consume(store, command_id, stamp)

    def _store(self) -> Any:
        return getattr(self._clients, "store", None)

    @staticmethod
    def _command_name(row: Any) -> Any:
        """The command word, from a pydantic row or a plain mapping."""
        if isinstance(row, dict):
            return row.get("command")
        return getattr(row, "command", None)

    @staticmethod
    def _command_id(row: Any) -> int | None:
        value = row.get("id") if isinstance(row, dict) else getattr(row, "id", None)
        return None if value is None else int(value)

    def _consume(self, store: Any, command_id: int, stamp: int) -> None:
        mark = getattr(store, "mark_command_consumed", None)
        if mark is None:
            self._log(
                "command_not_consumed",
                command_id=command_id,
                reason="store exposes no mark_command_consumed",
            )
            return
        mark(command_id, consumed_at=stamp)

    # ---------------------------------------------------------------- step 1: guard

    def _run_guard_chain(self, context: EngineContext, state: State) -> None:
        """Every tick, every mode. Never breaks early.

        A block here does not stop the chain: `data_guard` rejecting the tick's data
        must not prevent `safety` from evaluating the account. Every blocker is recorded
        for engine 19; the first is the primary one that gates the opportunity chain.
        """
        for engine in self._chains.guard:
            result = self._run(engine, context, state)
            state[engine.name] = result.data
            if result.blocks_trading:
                state["guard_blockers"].append(
                    {
                        "engine": engine.name,
                        "reason": result.reason,
                        "status": str(result.status),
                    }
                )
                if "trading_blocked_by" not in state:
                    state["trading_blocked_by"] = engine.name
                    state["block_reason"] = result.reason

    # ---------------------------------------------------------- step 2: opportunity

    def _run_opportunity_chain(self, context: EngineContext, state: State) -> None:
        """Only when running and nothing has blocked. Stops at the first block or PASS."""
        if self._system["mode"] != "running":
            self._log("opportunity_skipped", reason=f"mode is {self._system['mode']}")
            return
        if "trading_blocked_by" in state:
            self._log("opportunity_skipped", reason=f"blocked by {state['trading_blocked_by']}")
            return

        for engine in self._chains.opportunity:
            result = self._run(engine, context, state)
            state[engine.name] = result.data
            if result.blocks_trading:
                state["trading_blocked_by"] = engine.name
                state["block_reason"] = result.reason
                break
            if result.status is EngineStatus.PASS:
                break

    # --------------------------------------------------------------- step 3: manage

    def _run_manage_chain(self, context: EngineContext, state: State) -> None:
        """Every tick, every mode. Never stops.

        Engines 21 and 22 decide for themselves whether to place an exit — they read
        ``state["trading_blocked_by"]`` and ``state["system"]["close_intent"]`` and hold
        when the guard rejected the data. The orchestrator does not make that decision
        for them; it only guarantees they are given the chance to.
        """
        for engine in self._chains.manage:
            result = self._run(engine, context, state)
            state[engine.name] = result.data

    # ---------------------------------------------------------- step 4: close_intent

    def _clear_close_intent_if_finished(self, state: State) -> None:
        """Clear ``close_intent`` only when both engines report the close finished.

        A missing key reads as "not finished", never as "finished" — the same fail-closed
        default the gates use. An unregistered manage chain therefore cannot silently
        discard a pending liquidation, and a failed cancel or close survives into the
        next tick and is retried.
        """
        if not self._system.get("close_intent"):
            return

        cancelled = self._flag(state, "position_manager", "entry_orders_cancelled")
        closed = self._flag(state, "exit", "positions_closed")
        if cancelled and closed:
            self._system["close_intent"] = False
            self._log("close_all_complete")
            # Phase two of the two-phase consumption, and the only place it happens for
            # `close_all`. This called `store.mark_close_all_consumed` until the Phase 1
            # close — another method the store has never had, so the row stayed claimed
            # and unconsumed after a *successful* liquidation and was re-applied by the
            # startup replay on the next restart, closing an account that was already
            # flat. The id is the one carried from the tick that accepted the command.
            store = self._store()
            if store is not None and self._pending_close_all_id is not None:
                self._consume(store, self._pending_close_all_id, _to_micros(self._clock.now()))
            self._pending_close_all_id = None
        else:
            self._log("close_all_pending", cancelled=cancelled, closed=closed)

    @staticmethod
    def _flag(state: State, engine_name: str, field: str) -> bool:
        payload = state.get(engine_name)
        if not isinstance(payload, dict):
            return False
        return bool(payload.get(field, False))
