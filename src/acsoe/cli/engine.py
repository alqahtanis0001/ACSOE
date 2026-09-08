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
from typing import Any, Protocol

from acsoe.platform.clock import Clock, SystemClock
from acsoe.platform.config import Config, ConfigError, load_config
from acsoe.platform.logging import bind_run, clear_cycle, configure_logging, get_logger
from acsoe.platform.paths import RuntimePaths, ensure_runtime_directories

#: How often the loop wakes to check whether it has been asked to stop. Well
#: below the loop tick, so Ctrl-C is answered in under a second rather than after
#: a minute of sleeping.
_SHUTDOWN_POLL_S = 0.25


class Orchestrator(Protocol):
    """Structural match for ``core/orchestrator.py``'s orchestrator.

    Declared as a Protocol so this module can be tested against a stand-in and so
    the daemon does not import ``core`` at module import time. ``core/`` is the
    authority on the shape.
    """

    def tick(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Clients:
    """The three clients an engine may use, per engine contract rule 4.

    Phase 0 registers no engine, so nothing dereferences these. They are named
    rather than omitted because the orchestrator's constructor takes them and
    because an empty slot with a name is easier to fill than an argument that
    was never there.
    """

    kraken: object | None = None
    store: object | None = None
    recorder: object | None = None


class OrchestratorUnavailableError(RuntimeError):
    """`core/orchestrator.py` or `bootstrap.py` is not built yet."""


def build_orchestrator(config: Config, clock: Clock, clients: Clients) -> Orchestrator:
    """Import and construct the orchestrator.

    Imported here rather than at module scope so that ``acsoe --help`` and
    ``acsoe research`` work before ``core/`` exists, and so a missing orchestrator
    is a clear message rather than an ImportError traceback from a subcommand
    that never needed it.
    """
    try:
        from acsoe import bootstrap
        from acsoe.core import orchestrator as orchestrator_module
    except ImportError as exc:  # pragma: no cover - exercised once core/ lands
        raise OrchestratorUnavailableError(
            "the orchestrator is not built yet: src/acsoe/core/orchestrator.py and "
            "src/acsoe/bootstrap.py are lead-owned Phase 0 deliverables (specs 04 and 05). "
            "The daemon will not invent a tick loop of its own."
        ) from exc

    # `bootstrap.py` owns how the chains are assembled. Prefer its builder; fall
    # back to composing the three module-level registries if it exposes only
    # those. Either way the assembly stays in the lead's file, not in this one.
    builder = getattr(bootstrap, "build_chains", None)
    if callable(builder):
        chains: Any = builder()
    else:
        chains = bootstrap.Chains(
            guard=bootstrap.GUARD_CHAIN,
            opportunity=bootstrap.OPPORTUNITY_CHAIN,
            manage=bootstrap.MANAGE_CHAIN,
        )

    built: Any = orchestrator_module.Orchestrator(
        config=config,
        clock=clock,
        clients=clients,
        chains=chains,
    )
    return built


def _install_signal_handlers(stop: threading.Event) -> None:
    def handle(signum: int, _frame: FrameType | None) -> None:
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
            orchestrator.tick()
        except Exception:
            # The orchestrator converts an engine failure into ERROR itself. An
            # exception escaping it is a defect in the loop's own wiring, so it
            # is logged with its traceback and the daemon stops rather than
            # spinning on a broken tick every minute forever.
            log.exception("tick_failed")
            raise
        finally:
            clear_cycle()
        completed += 1
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

    clients = Clients()
    try:
        orchestrator = build_orchestrator(config, SystemClock(), clients)
    except OrchestratorUnavailableError as exc:
        log.error("orchestrator_unavailable", detail=str(exc))
        print(f"acsoe engine: {exc}", file=sys.stderr)
        return 3

    # `run_id` is minted by the orchestrator, which is also what writes the
    # `runs` row. Bind whatever it exposes so every line carries it.
    run_id = getattr(orchestrator, "run_id", None)
    if isinstance(run_id, str):
        bind_run(run_id)

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
