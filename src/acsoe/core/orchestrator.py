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
        """
        store = getattr(self._clients, "store", None)
        claim = getattr(store, "claim_pending_commands", None)
        if claim is None:
            self._log("commands_skipped", reason="store exposes no command reader")
            return

        for command in claim(run_id=self._run_id, now=self._clock.now()):
            name = getattr(command, "command", None) or command["command"]
            if name == "activate":
                self._system["mode"] = "running"
            elif name == "freeze":
                self._system["mode"] = "frozen"
            elif name == "close_all":
                self._system["mode"] = "frozen"
                self._system["close_intent"] = True
            else:
                # Never blocks the loop. A CHECK constraint on the column would have made
                # this path unreachable and untestable, which is why there isn't one.
                self._log("command_unrecognised", command=str(name))
                continue
            self._log("command_applied", command=str(name), mode=self._system["mode"])
            if name != "close_all":
                self._mark_consumed(command)

    def _mark_consumed(self, command: Any) -> None:
        store = getattr(self._clients, "store", None)
        mark = getattr(store, "mark_command_consumed", None)
        if mark is not None:
            mark(command, now=self._clock.now())

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
            store = getattr(self._clients, "store", None)
            mark = getattr(store, "mark_close_all_consumed", None)
            if mark is not None:
                mark(run_id=self._run_id, now=self._clock.now())
        else:
            self._log("close_all_pending", cancelled=cancelled, closed=closed)

    @staticmethod
    def _flag(state: State, engine_name: str, field: str) -> bool:
        payload = state.get(engine_name)
        if not isinstance(payload, dict):
            return False
        return bool(payload.get(field, False))
