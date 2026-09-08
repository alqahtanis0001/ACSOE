"""``acsoe engine`` — the trading daemon.

This module owns the **loop**; ``core/orchestrator.py`` owns the **tick**. That
split is deliberate and is not a style choice: cadence is an operational concern
and the three-chain semantics are a contract, so putting a chain decision here
would put engine behaviour in a file the lead does not own.

In Phase 0 no engine is registered, so a tick runs three empty chains and does
nothing, cleanly. That is a valid tick, not a broken one.

Shutdown completes the tick in progress and then stops. An interrupt is never
allowed to land in the middle of one: the manage chain is what watches open
positions and writes their records, and a half-run manage chain is a position
whose exit was decided and never recorded.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any

from acsoe.bootstrap import build_chains
from acsoe.core.orchestrator import Orchestrator
from acsoe.platform.clock import Clock, SystemClock
from acsoe.platform.config import Config, ConfigError, load_config
from acsoe.platform.logging import bind_run, clear_cycle, configure_logging, get_logger
from acsoe.platform.paths import RuntimePaths, ensure_runtime_directories

#: How often the loop wakes to check whether it has been asked to stop. Well
#: below the loop tick, so Ctrl-C is answered in under a second rather than after
#: a minute of sleeping.
_SHUTDOWN_POLL_S = 0.25


@dataclass(frozen=True)
class Clients:
    """The three clients an engine may use, per engine contract rule 4.

    Satisfies the ``Clients`` Protocol in ``core/contracts.py``: exactly three
    members, named ``kraken``, ``store`` and ``recorder``.

    Phase 0 registers no engine, so nothing dereferences these and all three are
    ``None``. The orchestrator's command reader ``getattr``s its way to the store
    and skips the read when it is absent, which is why an empty set of clients
    ticks rather than crashes. They are named rather than omitted because an
    empty slot with a name is easier to fill than an argument that was never
    there — engines 1 and 2 arrive in Phase 2 and the store client is B's.
    """

    kraken: Any = None
    store: Any = None
    recorder: Any = None


def build_orchestrator(config: Config, clock: Clock, clients: Clients) -> Orchestrator:
    """Construct the orchestrator over the chains ``bootstrap.py`` assembles.

    The chains come from ``build_chains()`` rather than being composed here.
    ``bootstrap.py`` is lead-owned and is the single place a registration
    happens; a CLI that built its own ``Chains`` would be a second registry, and
    two registries drift.
    """
    return Orchestrator(
        config=config,
        clock=clock,
        clients=clients,
        chains=build_chains(),
        logger=get_logger("acsoe.orchestrator"),
    )


def _install_signal_handlers(stop: threading.Event) -> None:
    def handle(_signum: int, _frame: FrameType | None) -> None:
        # Neither argument is used: the handler's whole job is to flip the flag
        # the loop checks between ticks. Both carry a leading underscore because
        # `signal.signal` calls the handler positionally with exactly two
        # arguments, so the signature is fixed and cannot be narrowed.
        stop.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handle)
        except (ValueError, OSError):
            # Not the main thread, or the platform does not have it. The loop
            # still exits on KeyboardInterrupt.
            continue


def _sleep_until_next_tick(stop: threading.Event, seconds: float) -> None:
    """Sleep in slices so a stop request is answered promptly."""
    deadline = time.monotonic() + seconds
    while not stop.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(_SHUTDOWN_POLL_S, remaining))


def run_loop(
    orchestrator: Orchestrator,
    *,
    tick_seconds: float,
    max_ticks: int = 0,
    stop: threading.Event | None = None,
) -> int:
    """Run ticks until stopped. Returns the number of completed ticks.

    A stop request is checked **between** ticks only. Interrupting mid-tick would
    leave the manage chain half-run, and the manage chain is what records that a
    position was watched.
    """
    stop = stop or threading.Event()
    log = get_logger("acsoe.engine")
    completed = 0
    while not stop.is_set():
        try:
            state = orchestrator.tick()
        except Exception:
            # The orchestrator converts an engine failure into ERROR itself, so
            # an exception escaping it is a defect in the loop's own wiring
            # rather than in an engine. Logged with its traceback, and the daemon
            # stops rather than spinning on a broken tick every minute forever.
            log.exception("tick_failed", cycle_id=orchestrator.cycle_id)
            raise
        finally:
            # Belt and braces: anything inside the tick that bound a cycle_id
            # must not leave it bound across the sleep, where a line would claim
            # to belong to a tick that has already finished.
            clear_cycle()
        completed += 1
        log.debug("tick_completed", cycle_id=state["cycle_id"], mode=state["system"]["mode"])
        if max_ticks and completed >= max_ticks:
            break
        _sleep_until_next_tick(stop, tick_seconds)
    log.info("engine_stopped", ticks=completed)
    return completed


def run(args: argparse.Namespace) -> int:
    config_path: Path = args.config
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        # Refusing to start against a config carrying an unset OPERATOR REQUIRED
        # key is correct, not a bug. Printed to stderr and returned as a distinct
        # exit code so a supervisor can tell "operator has not configured this"
        # from "the daemon crashed".
        print(f"acsoe engine: refusing to start.\n{exc}", file=sys.stderr)
        return 2

    paths: RuntimePaths = ensure_runtime_directories()
    configure_logging(
        log_dir=paths.logs,
        level=config.logging.level,
        retention_days=config.logging.retention_days,
        also_stderr=True,
    )
    log = get_logger("acsoe.engine")

    orchestrator = build_orchestrator(config, SystemClock(), Clients())

    # `run_id` is minted by the orchestrator, which is also what writes the
    # `runs` row. Bind it so every line the loop emits carries it.
    bind_run(orchestrator.run_id)

    stop = threading.Event()
    _install_signal_handlers(stop)
    log.info(
        "engine_starting",
        mode=config.mode,
        loop_tick_s=config.timeframes.loop_tick_s,
        config=str(config_path),
    )
    try:
        run_loop(
            orchestrator,
            tick_seconds=config.timeframes.loop_tick_s,
            max_ticks=args.ticks,
            stop=stop,
        )
    except KeyboardInterrupt:
        log.info("engine_interrupted")
    return 0
