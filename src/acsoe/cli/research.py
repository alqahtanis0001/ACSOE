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
import json
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from acsoe.bootstrap import build_chains
from acsoe.clients.kraken.replay import ReplayKrakenClient
from acsoe.clients.paper.broker import PaperBroker
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import CommandRow, CommandSource
from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.core.orchestrator import Orchestrator
from acsoe.platform.clock import Clock, FixedClock, SystemClock
from acsoe.platform.config import Config, ConfigError, ConfigView, derive_config, load_config
from acsoe.platform.logging import configure_logging, get_logger
from acsoe.platform.paths import DB_FILENAME, RuntimePaths, ensure_runtime_directories
from acsoe.research.backtest import BacktestEngine, ChainReplay, FoldWindow

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
    store = StoreClient(
        paths.db / DB_FILENAME, models_dir=paths.models, derived_dir=paths.derived
    )
    # The schema has to exist before engine 20 writes a leaderboard row, and a
    # research run on a fresh clone is exactly the case where it does not.
    # Migrations are forward-only and idempotent, so this is safe on a database
    # the daemon already migrated.
    store.migrate()
    return ResearchClients(store=store)


def run(args: argparse.Namespace) -> int:
    if getattr(args, "action", None) == "backtest":
        return run_backtest(args)
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


# --------------------------------------------------------------------------- #
# `acsoe research backtest` — spec 131: the registered chains over history
# --------------------------------------------------------------------------- #
#
# This is the wiring, and it lives here rather than in `research/backtest.py` for one
# reason: it needs `bootstrap.py`, the orchestrator, the store, the paper broker and the
# replay client, and this module is the only one allowed to import both the live loop's
# modules and `acsoe.research` (architecture invariant 5). The driver it wires is
# `research.backtest.ChainReplay`, which makes no decision and imports none of them.

#: The ranking names `--ranking` accepts, and what each sets `scout.rank_feature` to.
#: `alphabetical` is the baseline (R4): the key absent, engine 7's stated default.
RANKINGS: Final[Mapping[str, str | None]] = {
    "expected_move": "expected_move",
    "alphabetical": None,
}


@dataclass(frozen=True)
class ReplayRunClients:
    """The clients a replay run's orchestrator sees. Satisfies the `Clients` Protocol.

    `kraken` is the paper broker wrapping the replay client, exactly as paper mode
    wraps the live one. `recorder` is `None`: a replay never writes the archive
    (invariant 11), and the replay client drains no frame for it to write.

    `scenario_digest` and `scenario_description` are what the orchestrator writes to
    the `runs` row (spec 134). They sit on the container because the broker wraps the
    replay client and forwards no attribute it does not know.
    """

    kraken: Any
    store: Any
    scenario_digest: str
    scenario_description: str
    recorder: Any = None


def replay_store(db_path: Path, paths: RuntimePaths) -> StoreClient:
    """A replay run's own store: its database, the artefact root, and the derived root.

    `derived_dir` is where engine 19 writes SHAP (spec 140). Without it every `write_shap`
    refuses and engine 19 carries on by design, so a run would record no explanations
    and nothing would say so; the replay's test writes one through this store.
    """
    store = StoreClient(db_path, models_dir=paths.models, derived_dir=paths.derived)
    store.migrate()
    return store


def fold_config(run_config: Config, fold: FoldWindow) -> Config:
    """The run's config with this fold's Phase 7 run directory in all three model keys.

    One directory per fold holds the predictor, the anomaly detector and the capped
    skeptic (spec 135), so engines 8, 13 and 15 are pointed at the same run id, and each
    reloads when it changes. Built fresh; `run_config` is never touched.
    """
    return derive_config(
        run_config,
        {
            "models.prediction_run_id": fold.run_id,
            "models.anomaly_run_id": fold.run_id,
            "models.skeptic_run_id": fold.run_id,
        },
    )


def _fold_windows(config: Any, store: Any) -> list[FoldWindow]:
    """Each fold's test window, read from its Phase 7 run directory's manifest."""
    fmt = str(config.get("replay.run_id_format"))
    folds: list[FoldWindow] = []
    for fold in range(int(config.get("replay.first_fold")), int(config.get("replay.last_fold")) + 1):
        run_id = fmt.format(fold=fold)
        manifest_path = Path(str(store.model_run_dir(run_id))) / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError(
                f"fold {fold}'s run directory {run_id!r} has no manifest; the replay "
                "refuses rather than score that week with another fold's models"
            )
        block = json.loads(manifest_path.read_text(encoding="utf-8")).get("fold") or {}
        if int(block.get("fold_index", -1)) != fold:
            raise RuntimeError(f"{run_id}'s manifest is for fold {block.get('fold_index')}")
        folds.append(
            FoldWindow(
                fold=fold,
                run_id=run_id,
                test_start_s=int(block["test_start_ts"]),
                test_end_s=int(block["test_end_ts"]),
            )
        )
    return folds


def _utc_seconds(moment: datetime | None) -> int | None:
    """A command-line instant as epoch seconds. A naive one is read as UTC, which is the
    only zone this system writes, and an aware one is converted rather than relabelled."""
    if moment is None:
        return None
    aware = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    return int(aware.timestamp())


def _last_recorded_tick_s(store: Any, record_path: Path) -> int | None:
    """Where a killed run stopped: the latest tick the run record or the store saw.

    Both, because each can be one tick ahead of the other when a process dies: the store
    commits inside engine 19 before the run record's line is written, and a tick that
    wrote no equity row (a position with no mark) is in the record only. The later of
    the two is never re-run, which is what keeps a resumed run from deciding a tick twice.
    """
    seen: list[int] = []
    if record_path.is_file():
        for line in record_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("event") == "tick":
                seen.append(int(entry["tick_s"]))
    latest = store.latest_equity_snapshot()
    if latest is not None:
        seen.append(int(latest.ts) // 1_000_000)
    blocks = store.recent_block_records(1)
    if blocks:
        seen.append(int(blocks[0].ts) // 1_000_000)
    return max(seen) if seen else None


def run_backtest(args: argparse.Namespace) -> int:
    """`acsoe research backtest`: one run, one process, one database (spec 131 step 4)."""
    config_path: Path = args.config
    try:
        committed = load_config(config_path)
    except ConfigError as exc:
        print(f"acsoe research backtest: refusing to start.\n{exc}", file=sys.stderr)
        return 2
    if committed.get("replay") is None:
        print("acsoe research backtest: the config has no `replay:` section.", file=sys.stderr)
        return 2

    root = Path.cwd().resolve()
    paths = ensure_runtime_directories(root)
    # One log directory per run when asked. Four concurrent runs sharing
    # `<cwd>/logs/acsoe.jsonl` would each try to rename it at the UTC midnight rollover
    # while the others hold it open, which fails on Windows and loses log lines from then
    # on (lead ruling (b), 2026-09-19). The default stays `<cwd>/logs`.
    log_dir: Path = args.log_dir if args.log_dir is not None else paths.logs
    configure_logging(
        log_dir=log_dir,
        level=committed.logging.level,
        retention_days=committed.logging.retention_days,
        also_stderr=False,
    )
    ranking = RANKINGS[args.ranking]
    tier = int(args.fee_tier) if args.fee_tier is not None else int(committed.get("replay.fee_tier"))
    run_config = derive_config(
        committed,
        {"mode": "replay", "replay.fee_tier": tier, "scout.rank_feature": ranking},
    )

    if args.db is None:
        print(
            "acsoe research backtest: --db is required. A run owns its own database "
            "(spec 131 step 4), and no default could keep two runs apart.",
            file=sys.stderr,
        )
        return 2
    db_path: Path = args.db
    db_path.parent.mkdir(parents=True, exist_ok=True)
    record_path = db_path.with_name(db_path.name + ".runrecord.jsonl")
    store = replay_store(db_path, paths)
    try:
        folds = _fold_windows(run_config, store)

        def config_for(fold: FoldWindow) -> Config:
            return fold_config(run_config, fold)

        view = ConfigView(config_for(folds[0]))
        start_s = min(fold.test_start_s for fold in folds)
        clock = FixedClock(datetime.fromtimestamp(start_s, UTC))
        begin_s = _utc_seconds(args.begin)
        stop_after_s = _utc_seconds(args.until)
        extras = {
            "window": {
                "first_fold": folds[0].fold,
                "last_fold": folds[-1].fold,
                "begin_s": begin_s,
                "stop_after_s": stop_after_s,
            },
            "ranking": ranking if ranking is not None else "alphabetical_baseline",
            "alphabetical_baseline": ranking is None,
            "run_id_format": str(run_config.get("replay.run_id_format")),
        }
        replay = ReplayKrakenClient.from_config(view, clock=clock, root=root, extras=extras)
        broker = PaperBroker(replay, store=store, config=view, clock=clock)
        clients = ReplayRunClients(
            kraken=broker,
            store=store,
            scenario_digest=replay.scenario_digest,
            scenario_description=replay.scenario_description,
        )
        resume_after_s = _last_recorded_tick_s(store, record_path) if args.resume else None
        if not args.resume and (store.latest_equity_snapshot() is not None or record_path.exists()):
            print(
                f"acsoe research backtest: {db_path} already holds a run. Pass --resume "
                "to continue it, or name a new database; a run never shares one.",
                file=sys.stderr,
            )
            return 2
        # One `run_id` per process, named for its database and the replay instant it
        # starts from. The orchestrator would otherwise mint it from the clock at
        # construction, which is the window's start for every process of every run: a
        # resumed process would reuse the killed one's id, its `cycle_id` would restart
        # at 1, and engine 19's once-per-tick constraints would refuse every row it
        # wrote. The database's name is in it because four runs over one window start at
        # the same instant, and engine 19's SHAP files are keyed by `run_id` under one
        # shared `data/derived/shap/`, where a second writer of a path is refused.
        anchor_s = resume_after_s if resume_after_s is not None else (begin_s or start_s)
        stem = "".join(c if c.isalnum() or c in "-_" else "-" for c in db_path.stem)
        run_id = (
            f"replay-{stem}-"
            + datetime.fromtimestamp(anchor_s, UTC).strftime("%Y%m%dT%H%M%SZ")
        )
        if resume_after_s is not None:
            run_id += "-resumed"
        orchestrator = _replay_orchestrator(
            view, clock, clients, run_id=run_id, previous_now_s=resume_after_s
        )

        def append(entry: Mapping[str, Any]) -> None:
            with record_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(dict(entry), sort_keys=True) + "\n")

        def activate(tick_s: int) -> None:
            store.append_command(
                CommandRow(
                    command="activate",
                    source=CommandSource.CONSOLE,
                    reason="replay driver: activate before the first tick of this process",
                    created_at=tick_s * 1_000_000,
                    updated_at=tick_s * 1_000_000,
                )
            )

        def exposed() -> bool:
            return store.count_open_positions() > 0 or store.count_resting_orders() > 0

        driver = ChainReplay(
            folds=folds,
            bar_s=int(run_config.get("timeframes.decision_bar_s")),
            loop_s=int(run_config.get("timeframes.loop_tick_s")),
            tick=orchestrator.tick,
            set_clock=lambda tick_s: clock.set(datetime.fromtimestamp(tick_s, UTC)),
            use_config=view.use,
            config_for=config_for,
            exposed=exposed,
            activate=activate,
            record=append,
        )
        append(
            {"event": "run", "run_id": orchestrator.run_id, "scenario_digest": replay.scenario_digest,
             "db": db_path.as_posix(), "resume_after_s": resume_after_s}
        )
        summary = driver.run(
            resume_after_s=resume_after_s,
            begin_s=begin_s,
            stop_after_s=stop_after_s,
            max_ticks=args.max_ticks,
        )
        append({"event": "end", "finished": summary.finished, "ticks": summary.ticks})
        print(
            f"acsoe research backtest: {summary.ticks} ticks ({summary.bar_ticks} bar, "
            f"{summary.minute_ticks} minute), finished={summary.finished}, "
            f"scenario {replay.scenario_digest[:12]}",
            flush=True,
        )
        return 0
    finally:
        store.close()


def _replay_orchestrator(
    config: Any, clock: Any, clients: Any, *, run_id: str, previous_now_s: int | None
) -> Orchestrator:
    """The registered chains, unchanged, under `core/`'s orchestrator, unchanged.

    **On a resume, the last recorded tick is passed as `previous_now`** so that the
    first resumed tick measures its trade range from where the killed process stopped.
    Live, a restart's first tick has `previous_now = None` because nothing watched the
    gap. In a replay the gap is history, fully on disk, and a resumed run that missed a
    stop touched in its first minute would not reproduce the uninterrupted one (spec 131
    step 6). The lead added the keyword to `core/` for this on 2026-09-19; the daemon
    never passes it.
    """
    return Orchestrator(
        config=config,
        clock=clock,
        clients=clients,
        chains=build_chains(),
        run_id=run_id,
        logger=get_logger("acsoe.orchestrator"),
        previous_now=(
            None if previous_now_s is None else datetime.fromtimestamp(previous_now_s, UTC)
        ),
    )
