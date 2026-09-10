"""Spec 09 — the three entry points.

What is actually being asserted here, in order of how much it matters:

1. **Both entry points refuse to start on an unset OPERATOR REQUIRED key, and
   both accept the committed `config/default.yaml`.** The refusal is not a bug
   being tolerated, it is the deliverable: a daemon that started on a null
   threshold would be trading on numbers nobody chose. The acceptance is the
   other half — the shipped file is known-good and a fresh clone runs.
2. **A tick loop that never lands an interrupt mid-tick.** The manage chain is
   what records that an open position was watched; a half-run one is a position
   whose exit was decided and never written down.
3. `acsoe research` reports an empty offline chain and exits zero, and
   `build_offline_chain` is importable without running the CLI, because
   `scripts/verify.py` has to reach engines 20 and 23 through it.
4. `acsoe console` serves a health response.

**What changed on 2026-09-08.** Until then `config/default.yaml` carried nine null
OPERATOR REQUIRED keys, and points 1's refusals were asserted directly against it.
The operator has now supplied all nine, so the refusals are asserted against a
config this file fabricates — `unset_operator_config` — and the committed file has
acquired the opposite assertions. Nothing in the refusal machinery was relaxed to
get there: the nine values are provisional (`context/progress-tracker.md`) and a
null can come back, so what had to survive is that a null still stops the process.

`OPERATOR_FIXTURE` below is **fixture shape, not defaults.** Every value in it
exists so the loader has something to accept; none of them is a recommendation,
and none may be copied into `config/default.yaml`. The same warning is on
`OPERATOR_VALUES` in `tests/platform/test_config.py`, which holds the same values
for the same reason. They are duplicated rather than shared, and that duplication
has already earned itself once: when the operator filled the nine in, this file
failed loudly instead of silently inheriting the new values. It failed in the
direction nobody expected — the config becoming *more* valid — which is the useful
kind of loud.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import signal
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import structlog
import yaml
from tests.harness.fake_kraken import FakeKrakenClient

from acsoe.cli import main as cli_main
from acsoe.cli import research as research_cmd
from acsoe.cli.console import build_app
from acsoe.cli.engine import (
    Clients,
    build_clients,
    build_orchestrator,
    close_clients,
    run_loop,
)
from acsoe.clients.recorder.writer import JsonlRecorder
from acsoe.clients.store.client import StoreClient
from acsoe.core.contracts import Chains
from acsoe.core.orchestrator import Orchestrator
from acsoe.platform.clock import FixedClock, SystemClock
from acsoe.platform.config import Config, load_config
from acsoe.platform.paths import DB_FILENAME, ensure_runtime_directories

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = REPO_ROOT / "config" / "default.yaml"

#: A fixed instant, deliberately not "now", matching `tests/harness/doubles.py`.
#: Two runs of the same test then produce identical output, which is the whole
#: reason the clock is injected rather than read.
FIXED_NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

#: FIXTURE SHAPE, NOT DEFAULTS. See the module docstring.
OPERATOR_FIXTURE: dict[str, dict[str, Any]] = {
    "safety": {
        "max_drawdown_pct": "0.10",
        "max_consecutive_losses": 5,
        "max_errors_in_window": 20,
    },
    "trading": {
        "hurdle_multiple": "1.5",
        "risk_fraction_per_trade": "0.01",
        "max_concurrent_positions": 3,
        "entry_unfilled_window_s": 300,
        "base_reporting_currency": "USD",
    },
    "paper": {"starting_balances": {"USD": "1000.00"}},
}

#: The eleven keys no agent may choose a value for. Duplicated from
#: `tests/platform/test_config.py` for the reason in the module docstring.
OPERATOR_REQUIRED_KEYS: tuple[str, ...] = (
    "safety.max_drawdown_pct",
    "safety.max_consecutive_losses",
    "safety.max_errors_in_window",
    "trading.hurdle_multiple",
    "trading.risk_fraction_per_trade",
    "trading.max_concurrent_positions",
    "trading.entry_unfilled_window_s",
    "trading.base_reporting_currency",
    "paper.starting_balances",
    # Tenth, supplied 2026-09-09. Engine 4's staleness threshold: the whole
    # judgement of the first real gate, which is why the lead would not invent it
    # and the engine raised rather than defaulting until the operator set it.
    "data_guard.max_data_age_s",
    # Eleventh, supplied 2026-09-10. Invariant 7 defines a crypto-quoted pair as one
    # whose quote is "BTC, ETH, or any non-stable asset" and nothing in the repo held
    # the set of stable assets; Kraken does not supply it either. It decides which
    # pairs are tradable, which is the test the file's own header sets, so it is the
    # operator's and not the lead's. Contrast `kraken.cache_ttl_s`, which is marked in
    # the file but is NOT here: that one is lead-chosen client tuning, ruled 2026-09-10,
    # and the marker test caught the lead adding it. The alarm has now fired twice and
    # been answered both ways, deliberately, which is what it is for.
    "trading.stable_quote_currencies",
)

#: Specified by `architecture-context.md` as the trailing hour, so it was never
#: the operator's to supply. A refusal that named it would train them to skim.
NEVER_OPERATOR_REQUIRED = "safety.error_rate_window_s"


def write_config(tmp_path: Path, raw: dict[str, Any]) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def startable_config(tmp_path: Path) -> Path:
    """`config/default.yaml` with the operator's nine replaced by fixture values.

    Built from the shipped file rather than written from scratch, so a key the
    lead adds is picked up here automatically instead of being missed — and a key
    the lead adds as `null` survives the overlay and takes every test using this
    fixture down at once, which is how a tenth operator-required key announces
    itself.
    """
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    for section, values in OPERATOR_FIXTURE.items():
        raw[section].update(copy.deepcopy(values))
    return write_config(tmp_path, raw)


@pytest.fixture
def unset_operator_config(tmp_path: Path) -> Path:
    """The shipped config with all nine operator keys set back to `null`.

    What `config/default.yaml` itself looked like before 2026-09-08, and what it
    would look like again if the operator withdrew a provisional value. The
    refusal tests point here rather than at the committed file, so they assert the
    behaviour rather than the state of one file on one day.
    """
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    for dotted in OPERATOR_REQUIRED_KEYS:
        section, _, leaf = dotted.rpartition(".")
        assert leaf in raw[section], f"{dotted} is not in the shipped config"
        raw[section][leaf] = None
    return write_config(tmp_path, raw)


@pytest.fixture(autouse=True)
def _isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep a command's side effects inside `tmp_path`.

    Two of them: `ensure_runtime_directories()` creates `data/` and `logs/`
    relative to the working directory, and `configure_logging()` replaces the
    root logger's handlers process-wide. Both are correct behaviour for a daemon
    and both would otherwise leak out of the test — the second as an open file
    handle on a directory pytest is about to delete, which on Windows is a
    failure rather than a warning.
    """
    monkeypatch.chdir(tmp_path)
    _release_log_handlers()
    yield
    _release_log_handlers()
    structlog.reset_defaults()


def _release_log_handlers() -> None:
    """Close and detach every root handler. Called **before and after** each test.

    After, because `configure_logging()` replaces the root logger's handlers
    process-wide and a `TimedRotatingFileHandler` left open holds a file inside a
    directory pytest is about to remove — which on Windows is an error, not a warning.

    Before, because that is the half this fixture originally lacked and the half that
    explains the symptom. A handler leaked by a test in **another** module points at
    *that* module's `tmp_path`, survives into this one, and is still open whenever
    pytest gets round to collecting the older directory. The failure then lands as a
    teardown ERROR on whichever test happened to be running, which is why it was seen
    once here and did not reproduce: nothing in this module caused it and nothing in
    this module could reliably provoke it. Releasing on entry means this module cannot
    be the place a stranger's handle comes due.
    """
    logging.shutdown()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


def load(path: Path) -> Config:
    """Load without touching `.env`: a test must not inherit the developer's environment."""
    return load_config(path, load_env=False)


# --------------------------------------------------------------------------
# The dispatcher
# --------------------------------------------------------------------------


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as caught:
        cli_main.main(["--help"])
    assert caught.value.code == 0


def test_every_command_resolves_to_a_callable() -> None:
    for command in cli_main.COMMANDS:
        assert callable(cli_main.resolve_handler(command))


def test_an_unknown_command_is_refused_rather_than_returning_none() -> None:
    with pytest.raises(SystemExit):
        cli_main.resolve_handler("backtest")


def test_a_missing_subcommand_is_an_error() -> None:
    with pytest.raises(SystemExit) as caught:
        cli_main.main([])
    assert caught.value.code != 0


def test_running_the_engine_does_not_import_the_research_entry_point() -> None:
    """Architecture invariant 5, checked in the import graph rather than by eye.

    From Phase 4 `cli/research.py` registers engines 20 and 23 and therefore
    imports from `acsoe.research`. A dispatcher that imported all three command
    modules eagerly would pull that into the daemon process on every
    `acsoe engine`, and nothing would fail — which is exactly why the structure
    has to prevent it. Run in a subprocess because this process has already
    imported the module.
    """
    program = (
        "import sys\n"
        "from acsoe.cli import main\n"
        "main.resolve_handler('engine')\n"
        "assert 'acsoe.cli.research' not in sys.modules, sorted(\n"
        "    m for m in sys.modules if m.startswith('acsoe.'))\n"
        "assert 'acsoe.research' not in sys.modules\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert completed.returncode == 0, completed.stderr


# --------------------------------------------------------------------------
# acsoe engine
# --------------------------------------------------------------------------


def test_engine_refuses_an_unset_operator_key_and_names_every_one(
    unset_operator_config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail-closed, at the entry point rather than only in the loader.

    The daemon must refuse a config carrying an unset OPERATOR REQUIRED key, name
    all of them in one message, and exit with a code distinct from a crash so a
    supervisor can tell "the operator has not configured this" from "the daemon
    died". Asserted here as well as in `tests/platform/test_config.py` because the
    loader raising and the *process* refusing are two different things: an entry
    point that caught `ConfigError` and carried on with a warning would leave the
    loader's test green.
    """
    code = cli_main.main(["--config", str(unset_operator_config), "engine", "--ticks", "1"])
    assert code == 2
    stderr = capsys.readouterr().err
    assert "refusing to start" in stderr
    for key in OPERATOR_REQUIRED_KEYS:
        assert key in stderr
    # `safety.error_rate_window_s` is specified (the trailing hour) and set, so it
    # must not be listed. Naming a key the operator does not have to supply
    # trains them to skim the list.
    assert NEVER_OPERATOR_REQUIRED not in stderr


def test_engine_starts_against_the_committed_config(capsys: pytest.CaptureFixture[str]) -> None:
    """The other half: a fresh clone runs the daemon with no edits at all.

    `config/default.yaml` is passed exactly as committed — no overlay, no fixture,
    nothing filled in — and one tick completes. Until 2026-09-08 this test could
    not have existed, because the file was deliberately unstartable; the operator
    supplying the nine is what makes the shipped file a thing that can be asserted
    known-good rather than known-blocked.
    """
    assert cli_main.main(["--config", str(DEFAULT_YAML), "engine", "--ticks", "1"]) == 0
    assert "refusing to start" not in capsys.readouterr().err


def test_engine_ticks_against_an_empty_registry_and_exits_zero(startable_config: Path) -> None:
    """One tick end to end through the real dispatcher, config, logging and orchestrator.

    `--ticks 1` rather than more because the loop sleeps `timeframes.loop_tick_s`
    — sixty seconds — between ticks. Multiple ticks are exercised by
    `run_loop` directly, where the cadence can be set to zero.
    """
    assert cli_main.main(["--config", str(startable_config), "engine", "--ticks", "1"]) == 0
    assert (Path.cwd() / "logs").is_dir()
    assert (Path.cwd() / "data" / "raw").is_dir()


def test_the_loop_runs_the_requested_number_of_ticks(startable_config: Path) -> None:
    orchestrator = build_orchestrator(load(startable_config), FixedClock(FIXED_NOW), Clients())
    assert run_loop(orchestrator, tick_seconds=0.0, max_ticks=3) == 3
    assert orchestrator.cycle_id == 3


def test_an_empty_registry_produces_a_valid_tick(startable_config: Path) -> None:
    """An empty chain is a valid chain. The tick still mints a cycle and a state.

    The registry is constructed **empty, here**, rather than taken from `bootstrap`.
    Until engines 1 to 4 were registered those were the same thing, and this test
    asserted "no guard blocked" while its name claimed "an empty registry ticks" - two
    different claims that happened to coincide. The moment anything was registered the
    assertion decayed into a statement about whatever `bootstrap` currently holds, which
    is not a property of an empty registry at all. Same defect C found in
    `orchestrator_empty_registry`, in my file, found the same way: by it going red for a
    reason that had nothing to do with it.
    """
    orchestrator = Orchestrator(
        config=load(startable_config),
        clock=FixedClock(FIXED_NOW),
        clients=Clients(),
        chains=Chains(),
    )
    state = orchestrator.tick()
    assert state["cycle_id"] == 1
    assert state["guard_blockers"] == []
    assert state["system"]["mode"] == "idle"
    assert state["system"]["close_intent"] is False
    assert "trading_blocked_by" not in state


def test_the_guard_chain_ingests_before_it_judges_and_judges_before_it_breaks(
    startable_config: Path,
) -> None:
    """The guard chain's *order*, which is a property; not its membership, which is a date.

    **Rewritten for spec 47, and the reason is worth more than the fix.** This asserted a
    literal list of the four Phase 2 engines under a docstring saying "what `bootstrap`
    actually holds". That is a fact about what had been registered on the afternoon it was
    written, and registering engine 17 `safety` turned it red for no defect — the third
    expiring test this phase, after A's tripwire that pinned a value the test itself
    supplied and C's criterion test asserting PENDING because `test_scout.py` did not exist
    yet.

    What the chain's order actually guarantees, and what a later registration must not
    break:

    - **`exchange` first.** It publishes the account picture the rest of the chain reads.
    - **`market_sensor` after `market_data_recorder`.** Candles and quotes are built from
      frames that have been recorded, not the other way round.
    - **`data_guard` after both publishers.** It judges what 1 and 3 produced, so it cannot
      precede either.
    - **`safety` last.** It reads the current tick's `state["trading_blocked_by"]`, which
      `data_guard` sets, so it cannot precede the engine whose verdict it counts.

    Asserted as relative positions rather than as a list, so registering engines 5, 6, 12
    or 13 later changes nothing here — and reordering any of these four still fails.
    """
    from acsoe import bootstrap

    order = [engine.name for engine in bootstrap.build_chains().guard]

    for name in ("exchange", "market_data_recorder", "market_sensor", "data_guard", "safety"):
        assert name in order, f"{name} is not registered in the guard chain"

    assert order.index("exchange") < order.index("market_sensor")
    assert order.index("market_data_recorder") < order.index("market_sensor")
    assert order.index("market_sensor") < order.index("data_guard")
    assert order.index("exchange") < order.index("data_guard")
    assert order.index("data_guard") < order.index("safety"), (
        "safety reads state['trading_blocked_by'], which data_guard sets on the same tick"
    )
    assert order.index("safety") == len(order) - 1, (
        "safety is the account-level breaker and runs after every ingestion engine"
    )


def test_a_tick_with_no_clients_at_all_records_errors_rather_than_raising(
    startable_config: Path,
) -> None:
    """Contract rule 7: an engine that cannot reach a client fails the tick, not the loop.

    **Rewritten for spec 39, and worth saying why rather than quietly repointing it.**
    This was the Phase 2 pin on the daemon's broken state — three `None` client slots
    — written so that wiring the real clients would turn it red. It did not: it builds
    the empty `Clients()` itself rather than going through `cli/engine.py`, so it
    pinned a fact about a value the test supplies, not a fact about the daemon. A
    tripwire attached to a local reproduction of the symptom cannot detect the cause.

    What it actually tests is still true and still worth keeping, so it keeps that and
    loses the claim it could not support: a chain handed no clients records an `ERROR`
    per engine, never breaks early, and completes. The daemon's own wiring is asserted
    in the two tests below, against what `build_clients` builds.
    """
    orchestrator = build_orchestrator(load(startable_config), FixedClock(FIXED_NOW), Clients())
    state = orchestrator.tick()

    assert state["cycle_id"] == 1
    blockers = {blocker["engine"]: blocker["status"] for blocker in state["guard_blockers"]}
    assert blockers["exchange"] == "ERROR"
    assert state["trading_blocked_by"] == "exchange"
    # Every guard engine still ran: the chain never breaks early.
    for name in ("exchange", "market_data_recorder", "market_sensor", "data_guard"):
        assert name in state, name


def test_the_daemon_builds_three_real_clients_and_needs_no_credentials(
    startable_config: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 39 step 1 and step 2, asserted on the daemon's own construction path.

    **A missing API key is not a startup refusal.** Paper mode is the default and has
    to run on a fresh clone with no `.env`: the private calls then fail, engine 1
    records it, and the gates block on their own — which is invariant 3. Refusing here
    would be a live-mode guard, and that is invariant 1's job and a Phase 8
    deliverable. The environment is cleared explicitly rather than hoped about, so this
    proves the no-key path on a machine that happens to have a key.

    **The stream starts subscribed to nothing.** No pair list, no default, no config
    key holding one — the scope is derived per tick by engine 2 from what engine 1
    publishes. Asserted because an empty scope is the correct initial state and looks
    exactly like a bug if nobody has written down that it is not.
    """
    monkeypatch.delenv("KRAKEN_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_API_SECRET", raising=False)
    paths = ensure_runtime_directories(tmp_path)

    clients = build_clients(load(startable_config), FixedClock(FIXED_NOW), paths)

    assert clients.kraken is not None
    assert clients.store is not None
    assert clients.recorder is not None
    assert clients.kraken.subscription == ()
    # The database is the documented one, migrated, under the temporary root. The
    # name is written out as a literal rather than reused from `DB_FILENAME`:
    # `architecture-context.md` documents the layout as `db/  acsoe.sqlite`, and an
    # assertion built from the constant it is checking moves with it, so it could
    # never notice the code drifting away from the document.
    assert clients.store.db_path == paths.db / "acsoe.sqlite"
    assert DB_FILENAME == "acsoe.sqlite"
    assert clients.store.db_path.is_file()
    close_clients(clients)


def test_the_daemon_completes_two_ticks_with_real_clients(
    startable_config: Path, tmp_path: Path, fixed_clock: Any
) -> None:
    """Spec 39's first acceptance check, over the **real** `bootstrap` registry.

    C's fake Kraken client for the exchange, because no test may reach the network;
    B's real store against a temporary database; A's real JSONL recorder writing into
    a temporary `data/raw/`. Two ticks rather than one, because `state` is fresh every
    tick except `state["system"]` and an engine that quietly depended on something
    surviving passes a single-tick test and fails the second.

    The chains come from `build_chains()` rather than being assembled here: a CLI that
    built its own would be a second registry, and two registries drift.
    """
    store = StoreClient(tmp_path / DB_FILENAME)
    store.migrate()
    recorder = JsonlRecorder(tmp_path / "raw")
    clients = Clients(kraken=FakeKrakenClient(), store=store, recorder=recorder)
    orchestrator = build_orchestrator(load(startable_config), fixed_clock, clients)

    try:
        completed = run_loop(orchestrator, tick_seconds=0.0, max_ticks=2)
    finally:
        close_clients(clients)

    assert completed == 2
    assert orchestrator.cycle_id == 2


def test_the_daemon_stops_cleanly_on_the_stop_event_with_real_clients(
    startable_config: Path, tmp_path: Path, fixed_clock: Any
) -> None:
    """And closes both the stream and the database on the way out.

    `close_clients` runs in a `finally` in `run()`, so it has to survive an interrupt
    as well as a clean exit — the recording is the half that cannot be recovered, and
    a database left open on Windows is a file the next run cannot replace.
    """
    store = StoreClient(tmp_path / DB_FILENAME)
    store.migrate()
    clients = Clients(
        kraken=FakeKrakenClient(), store=store, recorder=JsonlRecorder(tmp_path / "raw")
    )
    orchestrator = build_orchestrator(load(startable_config), fixed_clock, clients)
    stop = threading.Event()

    assert run_loop(orchestrator, tick_seconds=0.0, max_ticks=1, stop=stop) == 1
    stop.set()
    close_clients(clients)

    assert run_loop(orchestrator, tick_seconds=0.0, stop=stop) == 0


def test_a_stop_request_is_answered_before_the_next_tick(startable_config: Path) -> None:
    stop = threading.Event()
    stop.set()
    orchestrator = build_orchestrator(load(startable_config), FixedClock(FIXED_NOW), Clients())
    assert run_loop(orchestrator, tick_seconds=0.0, stop=stop) == 0
    assert orchestrator.cycle_id == 0


def test_a_stop_raised_during_a_tick_still_completes_that_tick(startable_config: Path) -> None:
    """The one property of shutdown that costs money if it is wrong.

    A stop is checked between ticks, never inside one. The manage chain runs
    every tick in every mode and is what records that a position was watched, so
    a tick abandoned halfway is a decision taken and never written down.
    """
    stop = threading.Event()
    config = load(startable_config)

    class StopsItselfMidTick(Orchestrator):
        def tick(self) -> dict[str, Any]:
            state = super().tick()
            stop.set()  # as if SIGINT arrived while the chains were running
            state["reached_the_end_of_the_tick"] = True
            return state

    orchestrator = StopsItselfMidTick(
        config=config, clock=FixedClock(FIXED_NOW), clients=Clients()
    )
    assert run_loop(orchestrator, tick_seconds=0.0, stop=stop) == 1
    assert orchestrator.cycle_id == 1


def test_a_signal_sets_the_stop_flag_without_killing_the_process() -> None:
    """The installed handler flips a flag; it does not raise and it does not exit."""
    from acsoe.cli.engine import _install_signal_handlers

    previous = signal.getsignal(signal.SIGINT)
    stop = threading.Event()
    try:
        _install_signal_handlers(stop)
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler)
        handler(signal.SIGINT, None)
        assert stop.is_set()
    finally:
        signal.signal(signal.SIGINT, previous)


def test_the_clients_bundle_names_exactly_the_three_injected_clients() -> None:
    """Contract rule 4: kraken, store, recorder. No fourth, no direct filesystem."""
    clients = Clients()
    assert (clients.kraken, clients.store, clients.recorder) == (None, None, None)
    with pytest.raises(AttributeError):
        _ = clients.database  # type: ignore[attr-defined]


def test_the_daemon_builds_a_real_utc_clock() -> None:
    """Invariant 9 is only as good as what the orchestrator is handed."""
    clock = SystemClock()
    moment = clock.now()
    assert moment.tzinfo is not None
    assert moment.utcoffset() is not None and moment.utcoffset().total_seconds() == 0


# --------------------------------------------------------------------------
# acsoe research
# --------------------------------------------------------------------------


def test_research_reports_an_empty_offline_chain_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli_main.main(["research"]) == 0
    out = capsys.readouterr().out
    assert "no offline engines are registered" in out
    assert "20" in out and "23" in out


def test_build_offline_chain_is_importable_and_empty_in_phase_0() -> None:
    """`scripts/verify.py`'s `is_gate_matches_registry` reaches engines 20 and 23
    through this function, not through `bootstrap.py`, so it has to exist and be
    callable without running the CLI."""
    assert research_cmd.build_offline_chain() == ()
    assert research_cmd.OFFLINE_CHAIN == ()


def test_the_offline_chain_is_not_in_bootstrap() -> None:
    """Architecture invariant 5. `bootstrap.py` builds the three runtime chains only.

    The three `== ()` assertions this used to carry are gone. They were scaffolding that
    read as part of the claim and were not: "the chains are empty" is a fact about
    Phase 0, while "there is no offline chain here" is the invariant, and only the second
    survives an engine being registered. Keeping them would have made the test go red for
    the right reason at the wrong assertion.

    In their place, the invariant asserted on the source: `bootstrap` must not import
    from `research/`, which is where engines 20 and 23 live. `cli/research.py` assembles
    `OFFLINE_CHAIN`, and that separation is what keeps the live loop path clear of
    research code.
    """
    import ast

    from acsoe import bootstrap

    assert not hasattr(bootstrap, "OFFLINE_CHAIN")

    tree = ast.parse(Path(str(bootstrap.__file__)).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not [name for name in imported if name.startswith("acsoe.research")]


# --------------------------------------------------------------------------
# acsoe console
# --------------------------------------------------------------------------


def asgi_get(app: Any, path: str) -> tuple[int, dict[str, Any]]:
    """Drive one GET through the real ASGI application, in process.

    Deliberately not `fastapi.testclient.TestClient`: that is an `httpx.Client`
    subclass, and `tests/conftest.py`'s network guard patches `httpx.Client.send`
    for every test. Reaching around the guard to use it would be relaxing the
    guard for convenience, which spec 14 forbids. Calling the ASGI callable
    directly touches no socket at all, so there is nothing to relax.
    """

    async def drive() -> tuple[int, dict[str, Any]]:
        sent: list[dict[str, Any]] = []
        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        await app(scope, receive, send)
        status = next(m["status"] for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return status, json.loads(body)

    return asyncio.run(drive())


def test_console_serves_a_health_response(startable_config: Path) -> None:
    status, payload = asgi_get(build_app(load(startable_config)), "/health")
    assert status == 200
    assert payload["status"] == "ok"
    assert payload["mode"] == "paper"


def test_console_refuses_an_unset_operator_key(
    unset_operator_config: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The console loads the same config the daemon does and refuses the same file.

    If it started while the daemon could not, an operator would see a running
    console reporting a system that does not exist — and the console is the one
    surface that is *supposed* to be believable when everything else is down.
    """
    assert cli_main.main(["--config", str(unset_operator_config), "console"]) == 2
    assert "refusing to start" in capsys.readouterr().err


def test_console_accepts_the_committed_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """And accepts it on exactly the same file the daemon accepts.

    `uvicorn.run` is stubbed because the assertion is that the config was accepted
    and the app was built, not that a socket can be opened. A real `uvicorn.run`
    here binds `console.port` for real: while this test's ancestor was failing —
    it asserted a refusal that had stopped happening — it fell straight through
    into `uvicorn.run` and tried to bind 127.0.0.1:8765 from inside the suite,
    which is a test reaching the network by accident rather than by intent.
    """
    import uvicorn

    captured: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.update(kwargs, app=app))

    assert cli_main.main(["--config", str(DEFAULT_YAML), "console"]) == 0
    assert captured["port"] == 8765
    status, payload = asgi_get(captured["app"], "/health")
    assert (status, payload["status"], payload["mode"]) == (200, "ok", "paper")


def test_the_console_entry_point_never_imports_an_exchange_client() -> None:
    """`ui-context.md`: the console holds no credentials and can never place an order.

    The cheapest way to keep that true is for the process to never import the
    exchange client at all, so it is checked rather than asserted in prose.
    """
    program = (
        "import sys\n"
        "from acsoe.cli import console\n"
        "leaked = [m for m in sys.modules if m.startswith('acsoe.clients.kraken')]\n"
        "assert not leaked, leaked\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert completed.returncode == 0, completed.stderr


def test_the_console_port_comes_from_config_and_never_from_a_constant(
    startable_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ui-context.md`: the port is `console.port`. The README's 127.0.0.1:8765 is
    that key's default value, not a second source of truth."""
    import uvicorn

    captured: dict[str, Any] = {}

    def fake_run(app: Any, **kwargs: Any) -> None:
        captured.update(kwargs)
        captured["app"] = app

    monkeypatch.setattr(uvicorn, "run", fake_run)
    raw = yaml.safe_load(startable_config.read_text(encoding="utf-8"))
    raw["console"]["port"] = 9111
    startable_config.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    assert cli_main.main(["--config", str(startable_config), "console"]) == 0
    assert captured["port"] == 9111
    assert captured["host"] == "127.0.0.1"
    # structlog is configured by this point; uvicorn's default dictConfig would
    # reset the root logger and replace the JSON handler, and its redaction.
    assert captured["log_config"] is None


def test_the_port_flag_overrides_the_configured_port(
    startable_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import uvicorn

    captured: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.update(kwargs))
    assert cli_main.main(["--config", str(startable_config), "console", "--port", "9222"]) == 0
    assert captured["port"] == 9222
