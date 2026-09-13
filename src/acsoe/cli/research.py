"""``acsoe research`` — run the offline chain.

**This file, not ``bootstrap.py``, is where engines 20 ``tournament`` and 23
``backtest`` are registered.** That is what keeps architecture invariant 5 true:
the live loop never imports from ``research/``, because the only module that
assembles the offline chain is a CLI entry point the daemon never loads.

``build_offline_chain`` is importable without running the CLI, because
``scripts/verify.py``'s ``is_gate_matches_registry`` criterion has to inspect
engines 20 and 23 and cannot reach them through ``bootstrap.py``.

**This is the only module outside ``research/`` that may import from
``acsoe.research``, and it is why the import in it is at module scope rather than
inside a function.** The rule that matters is not "``cli/`` never imports
research" — that would leave the offline chain with nowhere to live — it is that
**``core/``, ``bootstrap.py``, ``engines/`` and ``clients/`` never do**, because
those are the live loop. ``acsoe engine`` dispatches through ``cli/main.py``,
which imports this module's sibling, not this module.

## What this command does, since spec 61 step 4

It **runs** the chain rather than listing it: a ``SystemClock``, a replay-mode
:class:`~acsoe.core.contracts.EngineContext` carrying the real ``Config`` and a
real store client, then every offline engine's ``process`` in registry order, one
printed line each with its status and reason, and a non-zero exit on any
``ERROR``.

Three decisions in that sentence are worth stating, because each has an obvious
alternative that is wrong here.

**Mode is ``replay``, not the config's mode.** ``config.mode`` is ``paper`` and
must stay so — invariant 1 — but an offline engine is not running the paper loop;
it is replaying history with an injected clock. The two are different axes and
``EngineContext.mode`` is the one that says which.

**There is no orchestrator.** The offline chain has no guard chain, no manage
chain, no ``state["system"]``, no cycle and nothing persistent to carry between
engines. Reusing :class:`~acsoe.core.orchestrator.Orchestrator` would mean
inventing a tick for something that runs once, so this module runs the engines
directly — and therefore has to do the one thing the orchestrator does that
matters here: convert an uncaught exception into ``ERROR`` rather than a
traceback, so a failing engine still produces a reported line and a non-zero
exit. Contract rule 7, locally.

**The clients are built here and there is no Kraken client in them.** Nothing
offline may reach the exchange; engine 23 reads the archive from disk and engine
20 reads the store and a digest. A ``None`` where the Kraken client would be is
the honest description of that, and it is why this module does not import
``cli/engine.py``'s client container — that one builds a websocket and a REST
client, and pulling it in would put a socket in a process that has no business
opening one.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from acsoe.clients.store.client import StoreClient
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.platform.clock import Clock, SystemClock
from acsoe.platform.config import Config, ConfigError, load_config
from acsoe.platform.logging import configure_logging, get_logger
from acsoe.platform.paths import DB_FILENAME, RuntimePaths, ensure_runtime_directories
from acsoe.research.backtest import BacktestEngine

__all__ = [
    "OFFLINE_CHAIN",
    "TOURNAMENT_ATTR",
    "TOURNAMENT_MODULE",
    "ResearchClients",
    "build_offline_chain",
    "run",
    "run_offline_chain",
]

#: Engine 20 ``tournament`` lands **here**, after engine 23, and never in
#: ``bootstrap.py``. C owns the class (spec 74); this names where it plugs in.
#:
#: Until it exists :func:`build_offline_chain` returns engine 23 alone, and
#: ``tests/cli/test_entrypoints.py`` carries the tripwire that goes red the moment
#: the module becomes importable and this file has not been updated. That is the
#: standing rule for a seam agreed by message: **a mock for a module that does not
#: exist yet needs a test that fails once it does.** A landed engine 20 that
#: nobody registered would leave `acsoe research` reporting a clean run of a chain
#: with a missing member, which is exactly the shape of failure this phase is
#: about — nothing red, and a leaderboard that is simply never written.
TOURNAMENT_MODULE: Final = "acsoe.engines.tournament.engine"
TOURNAMENT_ATTR: Final = "TournamentEngine"

#: The offline chain, in registry order: 23 ``backtest``, then 20 ``tournament``.
#:
#: Order is not alphabetical and not numeric. Engine 20 scores what engine 23's
#: run produced, so 23 runs first — `context/engine-contracts.md` fixes it.
OFFLINE_CHAIN: tuple[BaseEngine, ...] = (BacktestEngine(),)


@dataclass(frozen=True)
class ResearchClients:
    """The clients an offline engine may use. Satisfies the ``Clients`` Protocol.

    Exactly the three names contract rule 4 fixes, and two of them are ``None`` on
    purpose rather than by omission:

    * ``kraken`` is ``None`` because nothing offline may reach the exchange. An
      engine that asked for it here would get an ``AttributeError`` turned into
      ``ERROR``, which is the right answer.
    * ``recorder`` is ``None`` because the archive is immutable — invariant 11 —
      and the recorder is the one writer of it. A replay reads the archive and
      writes store rows; it never writes an archive line.
    * ``store`` is real, because engine 20 writes the leaderboard through it and
      because it is what hands an artefact directory to anything that asks.
    """

    store: Any
    kraken: Any = None
    recorder: Any = None


def build_offline_chain(*, digest_path: Path | None = None) -> tuple[BaseEngine, ...]:
    """Return the offline chain in registry order.

    Called by ``acsoe research`` and by ``scripts/verify.py``, which is why it
    takes no required argument: the criterion inspects ``is_gate`` on engines it
    never runs.

    ``digest_path`` is engine 20's training digest, passed from ``--digest``
    (spec 74). It is threaded through rather than read from config because a
    digest names one training run's output file, not a system-wide setting.
    """
    chain: tuple[BaseEngine, ...] = OFFLINE_CHAIN
    tournament = _tournament_engine(digest_path)
    if tournament is not None:
        chain = (*chain, tournament)
    return chain


def _tournament_engine(digest_path: Path | None) -> BaseEngine | None:
    """Engine 20, once C's module exists. ``None`` until then.

    Resolved by name rather than imported at module scope for the same reason
    engine 23 resolves C's labeller by name: this module has to stay importable —
    and therefore inspectable by ``is_gate_matches_registry`` — before the class
    it registers has been written.

    **It returns ``None`` for an absent module and raises for a broken one**, and
    telling those two apart is the whole of the code below. ``except
    ModuleNotFoundError`` on its own cannot: it catches a module that was never
    written *and* one whose own dependency is missing, and answering the second as
    "not registered yet" would drop engine 20 out of the chain silently, leaving
    `acsoe research` reporting a clean run over a chain of one. So the handler
    reads ``exc.name`` — which the exception carries precisely so that a caller
    need not guess — and re-raises anything that is not C's own package.

    The ``try`` is around ``find_spec`` and not only around the import because
    ``find_spec`` imports the *parent* package to search it: with no
    ``acsoe/engines/tournament/`` at all it raises rather than returning ``None``,
    which is the state this project is in until spec 74 lands.
    """
    try:
        found = importlib.util.find_spec(TOURNAMENT_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name is not None and TOURNAMENT_MODULE.startswith(exc.name):
            return None
        raise
    if found is None:
        return None

    module = importlib.import_module(TOURNAMENT_MODULE)
    factory = getattr(module, TOURNAMENT_ATTR, None)
    if factory is None:
        raise RuntimeError(
            f"{TOURNAMENT_MODULE} exists but has no {TOURNAMENT_ATTR!r}. That is the "
            "class `acsoe research` registers as engine 20; the seam is recorded in "
            "context/ownership.md."
        )
    try:
        engine: BaseEngine = factory(digest_path=digest_path)
    except TypeError as exc:
        # The seam was agreed by message (spec 74: "constructed with the path of a
        # training digest; A's `acsoe research` passes it from `--digest`"), and a
        # signature that does not match it must be loud. A silent fallback to
        # `factory()` here is how engine 23 spent a phase green against a labeller
        # signature that never existed.
        raise RuntimeError(
            f"{TOURNAMENT_MODULE}.{TOURNAMENT_ATTR} does not accept `digest_path`, "
            "which is what `acsoe research --digest` passes it. Agree the keyword "
            f"with C rather than changing either side alone. Underlying error: {exc}"
        ) from exc
    return engine


def _report_line(result: EngineResult) -> str:
    """One line per engine: number, name, status, and the reason when there is one.

    The reason is printed and not only logged because a blocked or errored offline
    run is something a person is looking at right now, and ``EngineResult.reason``
    is the field the contract requires to be "specific enough to analyse later".
    """
    reason = f" — {result.reason}" if result.reason else ""
    return f"  {result.engine:<10} {result.status.value:<5}{reason}"


def run_offline_chain(
    chain: tuple[BaseEngine, ...],
    *,
    config: Config,
    clients: Any,
    clock: Clock,
    run_id: str | None = None,
    on_result: Callable[[EngineResult], None] | None = None,
) -> tuple[list[EngineResult], State]:
    """Run every engine in ``chain`` once and return what each produced.

    Separated from :func:`run` so a test can drive the chain without a parsed
    command line, a config file on disk or a real database — and so the exception
    handling below is exercised by the tests rather than only by a broken run.

    Each engine's ``data`` is written into ``state`` under its own name, exactly
    as the orchestrator does it. Contract rule 2.

    ``on_result`` is called as each engine finishes, and exists because engine 23
    replays the whole archive: a run measured in minutes that prints nothing until
    the last engine returns is indistinguishable, from the outside, from a run that
    has hung. The caller decides what to do with the line; this function does not
    print.
    """
    now = clock.now()
    resolved_run_id = run_id or f"research-{now.strftime('%Y%m%dT%H%M%S%f')}"
    context = EngineContext(
        mode="replay",
        run_id=resolved_run_id,
        now=now,
        config=config,
        clients=clients,
    )
    log = get_logger("acsoe.research")
    state: State = {}
    results: list[EngineResult] = []

    for engine in chain:
        started = time.perf_counter()
        try:
            result = engine.process(context, state)
        except Exception as exc:
            # Contract rule 7, applied locally because there is no orchestrator
            # here to do it. Logged with its traceback — `code-standards.md`
            # forbids a bare `except Exception` that does neither — and converted
            # into ERROR so the chain still reports a line and the command still
            # exits non-zero. Swallowing it would turn a failed research run into
            # a silent one.
            log.exception("offline_engine_failed", engine=engine.name, run_id=resolved_run_id)
            result = EngineResult(
                engine=engine.name,
                status=EngineStatus.ERROR,
                blocks_trading=True,
                reason=f"{type(exc).__name__}: {exc}",
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        results.append(result)
        state[engine.name] = result.data
        if on_result is not None:
            on_result(result)

    return results, state


def _build_clients(paths: RuntimePaths) -> ResearchClients:
    store = StoreClient(paths.db / DB_FILENAME, models_dir=paths.models)
    # The schema has to exist before engine 20 writes a leaderboard row, and a
    # research run on a fresh clone is exactly the case where it does not.
    # Migrations are forward-only and idempotent, so this is safe on a database
    # the daemon already migrated.
    store.migrate()
    return ResearchClients(store=store)


def run(args: argparse.Namespace) -> int:
    config_path: Path = args.config
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        # Same exit code as `acsoe engine`: 2 means "the operator has not
        # configured this", distinct from a run that started and failed.
        print(f"acsoe research: refusing to start.\n{exc}", file=sys.stderr)
        return 2

    digest_path: Path | None = getattr(args, "digest", None)
    chain = build_offline_chain(digest_path=digest_path)
    if not chain:
        print(
            "acsoe research: no offline engines are registered. Engine 23 (backtest) "
            "and engine 20 (tournament) register in cli/research.py and nowhere else.",
            file=sys.stdout,
        )
        return 0

    paths = ensure_runtime_directories()
    configure_logging(
        log_dir=paths.logs,
        level=config.logging.level,
        retention_days=config.logging.retention_days,
        also_stderr=True,
    )

    clients = _build_clients(paths)
    clock = SystemClock()
    names = ", ".join(engine.name for engine in chain)
    # Flushed for the same reason the per-engine lines are: redirected to a file,
    # stdout is block-buffered, so an unflushed header is invisible for the whole
    # of a run that takes minutes — which makes a working run look like a hung one.
    print(
        f"acsoe research: running {len(chain)} offline engine(s) from {config_path}: {names}.",
        flush=True,
    )

    def report(result: EngineResult) -> None:
        # Flushed, because engine 23 replays the whole archive and the next line
        # may be minutes away; a buffered report arrives after the thing it was
        # meant to reassure anyone about.
        print(_report_line(result), flush=True)

    try:
        results, _ = run_offline_chain(
            chain, config=config, clients=clients, clock=clock, on_result=report
        )
    finally:
        close = getattr(clients.store, "close", None)
        if callable(close):
            close()

    errored = [result.engine for result in results if result.status is EngineStatus.ERROR]
    if errored:
        print(
            f"acsoe research: {len(errored)} engine(s) errored: {', '.join(errored)}. "
            "The traceback is in the run log.",
            file=sys.stderr,
        )
        return 1
    return 0


