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
from acsoe.clients.kraken.client import KrakenClient
from acsoe.clients.kraken.limiter import RateLimiter
from acsoe.clients.kraken.rest import KrakenRestClient
from acsoe.clients.kraken.ws import KrakenWebSocketClient
from acsoe.clients.recorder.writer import JsonlRecorder
from acsoe.clients.store.client import StoreClient
from acsoe.core.orchestrator import Orchestrator
from acsoe.engines.market_data_recorder.contracts import BOOK_DEPTH
from acsoe.platform.clock import Clock, SystemClock
from acsoe.platform.config import Config, ConfigError, load_config, load_credentials
from acsoe.platform.logging import bind_run, clear_cycle, configure_logging, get_logger
from acsoe.platform.paths import DB_FILENAME, RuntimePaths, ensure_runtime_directories

#: How often the loop wakes to check whether it has been asked to stop. Well
#: below the loop tick, so Ctrl-C is answered in under a second rather than after
#: a minute of sleeping.
_SHUTDOWN_POLL_S = 0.25


@dataclass(frozen=True)
class Clients:
    """The three clients an engine may use, per engine contract rule 4.

    Satisfies the ``Clients`` Protocol in ``core/contracts.py``: exactly three
    members, named ``kraken``, ``store`` and ``recorder``.

    All three still default to ``None``, and that is not left over from Phase 0.
    A test that drives one engine hands in the one client it needs, and the
    orchestrator's command reader ``getattr``s its way to the store and skips the
    read when it is absent — so an empty set of clients ticks rather than crashes.
    :func:`build_clients` is what the daemon uses, and it fills all three.
    """

    kraken: Any = None
    store: Any = None
    recorder: Any = None


def build_clients(config: Config, clock: Clock, paths: RuntimePaths) -> Clients:
    """The three real clients the daemon runs on.

    **A missing API key is not a startup refusal.** Paper mode is the default and has
    to run on a fresh clone with no ``.env``: ``load_credentials()`` returns ``None``,
    the two private calls raise, engine 1 records the failure in ``failed_fetches``,
    and every gate that needs a value it did not get blocks on its own. That is
    invariant 3 working. Refusing to start here would be a live-mode guard, which is
    invariant 1's job and is a Phase 8 deliverable.

    **The stream starts subscribed to nothing.** There is no pair list here, no
    default, and no config key holding one: the scope is derived per tick by engine 2
    from what engine 1 publishes, so the first tick is what tells the socket where to
    listen. An empty scope produces no subscribe frames at all rather than one asking
    for an empty symbol list.

    One rate limiter, shared by REST and the stream, because it is one account
    against one published rate limit.
    """
    limiter = RateLimiter(
        capacity=config.kraken.rest_capacity,
        refill_per_second=float(config.kraken.rest_refill_per_s),
    )
    rest = KrakenRestClient.from_config(
        config,
        clock=clock,
        limiter=limiter,
        credentials=load_credentials(),
    )
    stream = KrakenWebSocketClient(clock=clock, pairs=(), depth=BOOK_DEPTH)
    store = StoreClient(paths.db / DB_FILENAME)
    store.migrate()
    return Clients(
        kraken=KrakenClient(rest=rest, stream=stream),
        store=store,
        recorder=JsonlRecorder(paths.raw),
    )


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

    clock = SystemClock()
    clients = build_clients(config, clock, paths)
    orchestrator = build_orchestrator(config, clock, clients)

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
        # Named for the consequence rather than for the credential. Anything whose
        # field name contains "credential", "api_key" or "secret" is redacted by
        # `platform/logging.py`, correctly — and redacting a boolean about presence
        # destroys the only thing it was for, silently, leaving a line that still
        # looks fine and says nothing.
        private_calls_enabled=load_credentials() is not None,
    )
    # The stream opens before the first tick so that the socket is connecting while
    # engine 1 works out what to subscribe to. It starts subscribed to nothing.
    start_stream(clients)
    try:
        run_loop(
            orchestrator,
            tick_seconds=config.timeframes.loop_tick_s,
            max_ticks=args.ticks,
            stop=stop,
        )
    except KeyboardInterrupt:
        log.info("engine_interrupted")
    finally:
        # The recording is the half that cannot be recovered, so the socket and the
        # database are closed on every exit path including an interrupt.
        close_clients(clients)
    return 0


def start_stream(clients: Clients) -> None:
    """Open the market stream, if this set of clients has one.

    Duck-typed rather than isinstance-checked: a test hands in doubles that expose
    what they need to and nothing else, and a daemon that only started against the
    real class would be a daemon no test could start.
    """
    start = getattr(clients.kraken, "start", None)
    if callable(start):
        start()


def close_clients(clients: Clients) -> None:
    """Stop the stream and close the database, in that order.

    The stream first, so nothing is still arriving while the connection that records
    what arrived is being closed. Each is guarded on its own, because a client that
    fails to close must not stop the other one closing — this runs in a ``finally``
    and is the last chance either gets.
    """
    log = get_logger("acsoe.engine")
    for name, client, method in (
        ("kraken", clients.kraken, "stop"),
        ("store", clients.store, "close"),
    ):
        action = getattr(client, method, None)
        if not callable(action):
            continue
        try:
            action()
        except Exception:
            # Logged with its traceback rather than swallowed, and the loop
            # continues to the next client. Shutdown is not a place to raise: the
            # process is leaving either way and an exception here would hide
            # whatever the daemon was already exiting for.
            log.exception("client_close_failed", client=name)
