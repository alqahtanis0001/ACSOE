"""Fabricated trees for the verify tests.

Every criterion takes its repository root as a parameter rather than reading a
module-level constant, which is what makes these fixtures possible: a criterion
can be pointed at a directory built for the occasion and asked what it thinks.

Three shapes are used throughout.

`bare_tree` is a checkout with the *documents* and nothing built - which is the
honest meaning of "empty tree" here, since `context/`, `AGENTS.md` and `README.md`
are always present and it is `src/`, `db/migrations/` and `config/` that arrive
later. Every Phase 0 criterion must report PENDING against it and none may raise.

`unbuilt_tree` is the same plus an empty `src/acsoe/`, for the criteria that reach
the package by import. Without it the editable install leaks: `acsoe.bootstrap`
resolves to the real one and the criterion reports on this repository instead of
on the fabricated tree.

`tree_with_harness` adds `tests/` and `config/`, for the criteria that build a
tick out of the shared doubles.

`fabricate_package` writes a minimal `acsoe` into a tree's `src/`. That works
because the editable install is a plain `.pth` adding `src` to `sys.path` - no
meta-path finder - so `root_import_path` inserting the fabricated `src` at
`sys.path[0]` genuinely shadows the installed package. If that install mechanism
ever changes, these fabricated-subject tests will start silently testing the real
package instead, so the assertion in `test_fabrication_actually_shadows_the_real_package`
exists to catch it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

#: `toolchain_green` sets this in the environment of the pytest it shells out to,
#: so that the nested run does not shell out again and fork forever.
RECURSION_GUARD_ENV = "ACSOE_VERIFY_IN_TOOLCHAIN"


@pytest.fixture(autouse=True)
def _pristine_recursion_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the recursion guard so these tests see the criterion's real behaviour.

    This suite is run twice: directly, and again inside the pytest subprocess that
    `toolchain_green` launches. In the second run the guard variable is set, so
    `check_toolchain_green` short-circuits to "skipped: inside a toolchain_green
    subprocess" and every assertion about its actual behaviour fails - which is
    exactly what happened on the first `verify.py --phase 0` after these tests
    landed, and it went red only in the gate, never under a plain `pytest`.

    Clearing it is safe because no test here reaches the subprocess path: each one
    is stopped earlier by a tree with no `src/` or by a patched interpreter probe.
    The one test that wants the guard sets it back itself.
    """
    monkeypatch.delenv(RECURSION_GUARD_ENV, raising=False)


@pytest.fixture
def bare_tree(tmp_path: Path, repo_root: Path) -> Path:
    """A checkout carrying the documents and nothing that has been built yet."""
    shutil.copytree(repo_root / "context", tmp_path / "context")
    for name in ("AGENTS.md", "README.md"):
        shutil.copy(repo_root / name, tmp_path / name)
    return tmp_path


@pytest.fixture
def unbuilt_tree(bare_tree: Path) -> Path:
    """A bare tree carrying an **empty** `src/acsoe/` and nothing inside it.

    Needed because the editable install makes the real `acsoe` importable from any
    working directory, so `root_import_path` pointed at a tree with no `src/` at
    all quietly resolves `acsoe.bootstrap` to the *real* one and a criterion that
    should report PENDING reports on the developer's own repository instead.
    Writing an empty package into the tree restores the shadowing, and it is also
    the honest picture of the state being tested: after spec 03 the skeleton exists
    and nothing inside it has been built.
    """
    package = bare_tree / "src" / "acsoe"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    return bare_tree


@pytest.fixture
def tree_with_harness(bare_tree: Path, repo_root: Path) -> Path:
    """A bare tree that also carries `tests/` and `config/`.

    `orchestrator_empty_registry` builds its tick out of `tests.harness.doubles`,
    and those doubles read `config/default.yaml`. Copying both rather than stubbing
    them means the criterion is exercised against the real harness, which is the
    thing it will actually use.
    """
    shutil.copytree(repo_root / "tests", bare_tree / "tests")
    shutil.copytree(repo_root / "config", bare_tree / "config")
    return bare_tree


def fabricate_package(root: Path, modules: dict[str, str]) -> None:
    """Write a minimal `acsoe` package into `root/src`.

    `modules` maps a dotted module name to its source. Package `__init__.py` files
    are created for every intermediate package automatically.
    """
    src = root / "src"
    for dotted, source in modules.items():
        parts = dotted.split(".")
        directory = src.joinpath(*parts[:-1])
        directory.mkdir(parents=True, exist_ok=True)
        # Every package on the way down needs an __init__.py.
        for depth in range(1, len(parts)):
            init = src.joinpath(*parts[:depth], "__init__.py")
            if not init.exists():
                init.write_text("", encoding="utf-8")
        (directory / f"{parts[-1]}.py").write_text(source, encoding="utf-8")


EMPTY_BOOTSTRAP = """
GUARD_CHAIN: tuple[object, ...] = ()
OPPORTUNITY_CHAIN: tuple[object, ...] = ()
MANAGE_CHAIN: tuple[object, ...] = ()
"""

CHAINS_CONTRACT = """
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any


@dataclass(frozen=True)
class Chains:
    guard: Sequence[Any]
    opportunity: Sequence[Any]
    manage: Sequence[Any]
"""

ORCHESTRATOR = """
from typing import Any


class Orchestrator:
    def __init__(self, *, config: Any, clock: Any, clients: Any, chains: Any) -> None:
        self.config = config
        self.clock = clock
        self.clients = clients
        self.chains = chains

    def tick(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "system": {"mode": "idle", "close_intent": False},
            "cycle_id": 1,
            "guard_blockers": [],
        }
        for chain in (self.chains.guard, self.chains.opportunity, self.chains.manage):
            for engine in chain:
                state[engine.name] = {}
        return state
"""

ENGINE_STUB = """
class Engine:
    def __init__(self, name: str, number: int, is_gate: bool) -> None:
        self.name = name
        self.number = number
        self.is_gate = is_gate
"""

EMPTY_OFFLINE_CHAIN = """
OFFLINE_CHAIN: tuple[object, ...] = ()


def build_offline_chain() -> tuple[object, ...]:
    return OFFLINE_CHAIN
"""


def offline_chain_module(entries: str) -> str:
    """`cli/research.py` as the criterion reaches it - the offline chain is
    deliberately unreachable from `bootstrap.py`, so it is fabricated separately."""
    return (
        "from acsoe.engine_stub import Engine\n\n"
        f"OFFLINE_CHAIN = ({entries})\n\n\n"
        "def build_offline_chain():\n"
        "    return OFFLINE_CHAIN\n"
    )


def registry_bootstrap(guard: str = "", opportunity: str = "", manage: str = "") -> str:
    """`bootstrap.py` carrying fabricated engines in the three runtime chains."""
    return (
        "from acsoe.engine_stub import Engine\n\n"
        f"GUARD_CHAIN = ({guard})\n"
        f"OPPORTUNITY_CHAIN = ({opportunity})\n"
        f"MANAGE_CHAIN = ({manage})\n"
    )


# --------------------------------------------------------------------------- #
# db_migrates_from_empty
# --------------------------------------------------------------------------- #

#: The storage model of `architecture-context.md`. Repeated here rather than
#: imported from the criterion so the fabricated subject is an independent
#: statement of the same fact - a fabrication that imported the expectation it is
#: meant to satisfy would pass no matter what the criterion asserted.
DOCUMENTED_TABLES = (
    "trades",
    "rejections",
    "runs",
    "leaderboard",
    "positions",
    "orders",
    "equity_snapshots",
    "block_records",
    "commands",
)


def migrations_module(created: tuple[str, ...], declared: tuple[str, ...] | None) -> str:
    """A minimal `acsoe.clients.store.migrations`.

    `created` is what the runner actually builds; `declared` is what it advertises
    in `EXPECTED_TABLES`. Keeping them separate is what lets a test drive the two
    apart and prove the criterion notices.
    """
    declaration = (
        "EXPECTED_TABLES = None" if declared is None else f"EXPECTED_TABLES = frozenset({declared!r})"
    )
    return f"""
import sqlite3

BOOKKEEPING_TABLE = "schema_migrations"
{declaration}
_CREATED = {created!r}


def apply_migrations(db_path, migrations_dir=None):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS " + BOOKKEEPING_TABLE + " (name TEXT PRIMARY KEY)"
        )
        for name in _CREATED:
            conn.execute("CREATE TABLE IF NOT EXISTS " + name + " (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
"""


# --------------------------------------------------------------------------- #
# seed_fixtures_present
# --------------------------------------------------------------------------- #

#: Thresholds written into the fabricated `config/default.yaml`. Deliberately not
#: the real ones: `config/default.yaml` leaves several as `null` marked OPERATOR
#: REQUIRED, and inventing a drawdown limit into the real file would be inventing
#: trading behaviour. These are *test* numbers for a *fabricated* subject.
FABRICATED_THRESHOLDS = {
    "max_consecutive_data_blocks": 3,
    "max_drawdown_pct": 0.10,
    "max_consecutive_losses": 2,
    "max_errors_in_window": 1,
    "error_rate_window_s": 3600,
}


def fabricate_config(root: Path, **overrides: object) -> None:
    """Write a `config/default.yaml` carrying concrete `safety` thresholds."""
    values = {**FABRICATED_THRESHOLDS, **overrides}
    body = "\n".join(f"  {k}: {'null' if v is None else v}" for k, v in values.items())
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "default.yaml").write_text(
        f"mode: paper\nsafety:\n{body}\n", encoding="utf-8"
    )


#: A seed satisfying all six Phase 3 fixtures against `FABRICATED_THRESHOLDS`.
#:
#: The block records are the interesting part and are laid out to exercise the
#: three properties the criterion checks rather than only the headline count: the
#: five-tick outage spans **two** `run_id`s with `cycle_id` deliberately restarting
#: at 1 in the second, and two of its ticks carry a co-occurring `safety` blocker,
#: so "a tick contributes one, not two" is actually tested. Those same two rows
#: carry `status='ERROR'`, which is where the error-rate fixture comes from.
SEED_MODULE = '''
import sqlite3
from dataclasses import dataclass

BASE_TS = 1_800_000_000_000_000  # microseconds
STEP = 60_000_000  # one loop tick

# (run_id, cycle_id, extra blocker or None)
OUTAGE = [
    ("run-a", 1, None),
    ("run-a", 2, "safety"),
    ("run-b", 1, "safety"),
    ("run-b", 2, None),
    ("run-b", 3, None),
]
TRADES = ["5.00", "-1.00", "-2.00", "-3.00"]


@dataclass(frozen=True)
class _Run:
    length: int


@dataclass(frozen=True)
class SeedFixtures:
    consecutive_data_block_run: _Run
    losing_streak: _Run
    seed_now: int


def seed_database(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE block_records (
                run_id TEXT, cycle_id INTEGER, ts INTEGER,
                blocked_by TEXT, block_reason TEXT, is_primary INTEGER, status TEXT);
            CREATE TABLE equity_snapshots (ts INTEGER, equity TEXT, peak_equity TEXT);
            CREATE TABLE trades (closed_at INTEGER, realised_pnl TEXT, outcome TEXT);
            CREATE TABLE positions (pair TEXT, status TEXT);
            CREATE TABLE orders (userref INTEGER, status TEXT);
            CREATE TABLE rejections (cycle_id INTEGER, reason TEXT);
            """
        )
        ts = BASE_TS
        for run_id, cycle_id, extra in OUTAGE:
            conn.execute(
                "INSERT INTO block_records VALUES (?,?,?,?,?,?,?)",
                (run_id, cycle_id, ts, "data_guard", "stale candle", 1, "BLOCK"),
            )
            if extra is not None:
                conn.execute(
                    "INSERT INTO block_records VALUES (?,?,?,?,?,?,?)",
                    (run_id, cycle_id, ts, extra, "error rate", 0, "ERROR"),
                )
            ts += STEP
        last_ts = ts - STEP

        conn.execute("INSERT INTO equity_snapshots VALUES (?,?,?)", (BASE_TS, "1000", "1000"))
        conn.execute("INSERT INTO equity_snapshots VALUES (?,?,?)", (last_ts, "800", "1000"))
        for index, pnl in enumerate(TRADES):
            conn.execute(
                "INSERT INTO trades VALUES (?,?,?)",
                (BASE_TS + index * STEP, pnl, "loss" if pnl.startswith("-") else "win"),
            )
        conn.execute("INSERT INTO positions VALUES (?,?)", ("SOLUSD", "open"))
        conn.execute("INSERT INTO orders VALUES (?,?)", (1234, "resting"))
        conn.execute("INSERT INTO rejections VALUES (?,?)", (1, "net edge below hurdle"))
        conn.commit()
    finally:
        conn.close()
    return SeedFixtures(
        consecutive_data_block_run=_Run(len(OUTAGE)),
        losing_streak=_Run(sum(1 for p in TRADES if p.startswith("-"))),
        seed_now=last_ts,
    )
'''


#: A seed shaped like the real one: thresholds are **injected**, and every fixture
#: is generated as a multiple of the injected number rather than as a constant.
#:
#: Spec 13 makes this the seed's contract, which makes injecting the real config
#: values the *criterion's* job. `SCALING_SEED_DEFAULT_ERRORS` is deliberately far
#: below anything a test configures, so a criterion that forgets to inject falls
#: back to it and the fixture stops overshooting - which is exactly the defect
#: `test_seed_hands_the_configured_thresholds_to_the_generator` catches.
SCALING_SEED_DEFAULT_ERRORS = 1

SCALING_SEED_MODULE = '''
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal

BASE_TS = 1_800_000_000_000_000  # microseconds
STEP = 60_000_000  # one loop tick


@dataclass(frozen=True)
class SeedThresholds:
    max_consecutive_data_blocks: int = 1
    max_drawdown_pct: Decimal = Decimal("0.50")
    max_consecutive_losses: int = 1
    error_rate_window_s: int = 3600
    max_errors_in_window: int = 1


DEFAULT_THRESHOLDS = SeedThresholds()


@dataclass(frozen=True)
class _Counted:
    length: int

    @property
    def count(self):
        return self.length


@dataclass(frozen=True)
class SeedFixtures:
    thresholds: SeedThresholds
    consecutive_data_block_run: _Counted
    losing_streak: _Counted
    error_blocks: _Counted
    seed_now: int


def seed_database(db_path, *, seed=0, thresholds=DEFAULT_THRESHOLDS):
    outage_len = thresholds.max_consecutive_data_blocks + 3
    error_rows = thresholds.max_errors_in_window + 3
    losses = thresholds.max_consecutive_losses + 3
    drawdown = min(Decimal(thresholds.max_drawdown_pct) * 2, Decimal("0.9"))

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE block_records (
                run_id TEXT, cycle_id INTEGER, ts INTEGER,
                blocked_by TEXT, block_reason TEXT, is_primary INTEGER, status TEXT);
            CREATE TABLE equity_snapshots (ts INTEGER, equity TEXT, peak_equity TEXT);
            CREATE TABLE trades (closed_at INTEGER, realised_pnl TEXT, outcome TEXT);
            CREATE TABLE positions (pair TEXT, status TEXT);
            CREATE TABLE orders (userref INTEGER, status TEXT);
            CREATE TABLE rejections (cycle_id INTEGER, reason TEXT);
            """
        )
        # The daemon dies half way through the outage, so the run spans two run_ids
        # and `cycle_id` restarts at 1 - the property that makes `ts` ordering
        # load-bearing.
        boundary = outage_len // 2
        ticks = []
        for index in range(outage_len):
            run_id = "run-a" if index < boundary else "run-b"
            cycle_id = index + 1 if index < boundary else index - boundary + 1
            ts = BASE_TS + index * STEP
            ticks.append((run_id, cycle_id, ts))
            conn.execute(
                "INSERT INTO block_records VALUES (?,?,?,?,?,?,?)",
                (run_id, cycle_id, ts, "data_guard", "stale candle", 1, "BLOCK"),
            )
        # Error rows ride on the outage ticks, so every one of them is inside the
        # trailing window and every tick carries a second, co-occurring blocker.
        for index in range(error_rows):
            run_id, cycle_id, ts = ticks[index % len(ticks)]
            conn.execute(
                "INSERT INTO block_records VALUES (?,?,?,?,?,?,?)",
                (run_id, cycle_id, ts, "safety", "engine error", 0, "ERROR"),
            )
        last_ts = ticks[-1][2]

        peak = Decimal("1000")
        conn.execute("INSERT INTO equity_snapshots VALUES (?,?,?)", (BASE_TS, "1000", "1000"))
        conn.execute(
            "INSERT INTO equity_snapshots VALUES (?,?,?)",
            (last_ts, str(peak * (Decimal(1) - drawdown)), str(peak)),
        )

        conn.execute("INSERT INTO trades VALUES (?,?,?)", (BASE_TS, "5.00", "win"))
        for index in range(losses):
            conn.execute(
                "INSERT INTO trades VALUES (?,?,?)",
                (BASE_TS + (index + 1) * STEP, "-1.00", "loss"),
            )

        conn.execute("INSERT INTO positions VALUES (?,?)", ("SOLUSD", "open"))
        conn.execute("INSERT INTO orders VALUES (?,?)", (1234, "resting"))
        conn.execute("INSERT INTO rejections VALUES (?,?)", (1, "net edge below hurdle"))
        conn.commit()
    finally:
        conn.close()

    return SeedFixtures(
        thresholds=thresholds,
        consecutive_data_block_run=_Counted(outage_len),
        losing_streak=_Counted(losses),
        error_blocks=_Counted(error_rows),
        seed_now=last_ts,
    )
'''

#: `seed_database` advertises a `thresholds` argument and the module exposes no
#: class to build one from. That is a broken seed surface, not an absent subject.
SEED_MODULE_WITHOUT_THRESHOLD_CLASS = '''
def seed_database(db_path, *, thresholds=None):
    raise AssertionError("the criterion must refuse before calling this")
'''


# --------------------------------------------------------------------------- #
# record_sample_valid
# --------------------------------------------------------------------------- #

RECORD_TICK = (
    '{"v": 1, "kind": "tick", "pair": "SOL/USD", "channel": "book", '
    '"ts_exchange": "2026-01-01T00:00:00.000Z", "ts_recv": "2026-01-01T00:00:00.001Z", '
    '"payload": {"bids": [], "asks": []}}'
)
RECORD_GAP = (
    '{"v": 1, "kind": "gap", "pair": null, "channel": "_recorder", '
    '"ts_exchange": null, "ts_recv": "2026-01-01T00:01:00.000Z", '
    '"payload": {"reason": "disconnect", "disconnected_at": "2026-01-01T00:00:30.000Z", '
    '"reconnected_at": "2026-01-01T00:01:00.000Z", "gap_ms": 30000, "attempt": 1}}'
)
RECORD_SESSION = (
    '{"v": 1, "kind": "session", "pair": null, "channel": "_recorder", '
    '"ts_exchange": null, "ts_recv": "2026-01-01T00:00:00.000Z", '
    '"payload": {"event": "start", "url": "wss://ws.kraken.com/v2", '
    '"subscriptions": ["book"]}}'
)


def write_record_sample(root: Path, lines: tuple[str, ...]) -> Path:
    path = root / "tests" / "fixtures" / "record_sample.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
