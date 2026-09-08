#!/usr/bin/env python3
"""ACSOE executable phase gate.

`python scripts/verify.py --phase N` runs phase N's named criteria and prints
PASS, FAIL or PENDING for each.

    PASS     checked and satisfied
    FAIL     checked and not satisfied
    PENDING  the thing it checks does not exist yet

Exit code is non-zero only when something FAILed. PENDING is expected mid-phase
and only has to reach zero at phase close; that judgement is the lead's, from the
printed counts.

This script is neither the live loop nor research code, so architecture invariant 5
lets it import either side. It must not *require* either to exist: on a checkout
without `src/acsoe/` every criterion reports PENDING and nothing raises.

Owner: C - Interface and models. Specs 00, 01, 02.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import inspect
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

MIN_PHASE = 0
MAX_PHASE = 8

# Set in the environment of the subprocesses `toolchain_green` spawns. If anything
# ever shells out to this script from inside pytest, the nested run skips that
# criterion instead of recursing forever.
RECURSION_GUARD_ENV = "ACSOE_VERIFY_IN_TOOLCHAIN"

SUBPROCESS_TIMEOUT_S = 900


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


class Result(Enum):
    """The three results a criterion may report. Nothing else is permitted."""

    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"


@dataclass(frozen=True)
class Outcome:
    result: Result
    message: str


def passed(message: str) -> Outcome:
    return Outcome(Result.PASS, message)


def failed(message: str) -> Outcome:
    return Outcome(Result.FAIL, message)


def pending(message: str) -> Outcome:
    return Outcome(Result.PENDING, message)


@dataclass(frozen=True)
class VerifyContext:
    """What a criterion is allowed to know about the run.

    `root` is the repository being judged. It is a parameter rather than a
    constant so a unit test can point a criterion at a fabricated tree.
    """

    root: Path
    live: bool = False


CheckFn = Callable[["VerifyContext"], Outcome]


@dataclass(frozen=True)
class Criterion:
    name: str
    check: CheckFn
    live: bool = False


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

_REGISTRY: dict[int, list[Criterion]] = {p: [] for p in range(MIN_PHASE, MAX_PHASE + 1)}


def register(phase: int, criterion: Criterion) -> None:
    if phase not in _REGISTRY:
        raise ValueError(f"phase {phase} is outside {MIN_PHASE}..{MAX_PHASE}")
    if any(c.name == criterion.name for c in _REGISTRY[phase]):
        raise ValueError(f"criterion {criterion.name!r} already registered for phase {phase}")
    _REGISTRY[phase].append(criterion)


def register_every_phase(criterion: Criterion) -> None:
    for phase in range(MIN_PHASE, MAX_PHASE + 1):
        register(phase, criterion)


def criteria_for(phase: int, live: bool) -> tuple[list[Criterion], list[Criterion]]:
    """Return (criteria to run, live criteria skipped because --live was absent)."""
    registered = _REGISTRY.get(phase, [])
    if live:
        return list(registered), []
    return [c for c in registered if not c.live], [c for c in registered if c.live]


def run_criterion(criterion: Criterion, context: VerifyContext) -> Outcome:
    """Run one criterion. A criterion that raises is a FAIL, never a crash."""
    try:
        return criterion.check(context)
    except Exception as exc:  # deliberate: one bad check must not stop the run
        detail = f"{type(exc).__name__}: {exc}".replace("\n", " ")
        return failed(f"criterion raised - {detail[:400]}")


# --------------------------------------------------------------------------- #
# Import helpers
# --------------------------------------------------------------------------- #

_MANAGED_PREFIXES = ("acsoe", "tests")


def _is_managed(name: str) -> bool:
    return any(name == p or name.startswith(p + ".") for p in _MANAGED_PREFIXES)


@contextlib.contextmanager
def root_import_path(root: Path) -> Iterator[None]:
    """Import `acsoe` and `tests` from `root` for the duration of the block.

    Both are dropped from `sys.modules` on entry and restored on exit, so a unit
    test can point a criterion at a fabricated tree without poisoning the real
    interpreter for the criterion that runs next.
    """
    saved_path = list(sys.path)
    saved_modules = {k: v for k, v in sys.modules.items() if _is_managed(k)}
    for key in saved_modules:
        del sys.modules[key]
    src = root / "src"
    sys.path.insert(0, str(root))
    if src.is_dir():
        sys.path.insert(0, str(src))
    importlib.invalidate_caches()
    try:
        yield
    finally:
        sys.path[:] = saved_path
        for key in [k for k in sys.modules if _is_managed(k)]:
            del sys.modules[key]
        sys.modules.update(saved_modules)
        importlib.invalidate_caches()


VENV_HINT = "run under .venv\\Scripts\\python.exe, or pip install -e \".[dev]\""


def try_import(name: str) -> tuple[ModuleType | None, Outcome | None]:
    """Import `name`, or say precisely why not - and which of the three results
    that is.

    The distinction is the whole value of having three results rather than two:

    - A module of *ours* that has not been written yet is PENDING. That is what
      PENDING means: the subject does not exist.
    - A declared third-party dependency the interpreter does not have is **FAIL**.
      A broken environment is not orderly progress, and reporting it as PENDING
      would let a phase sit at "no FAIL" while nothing was actually being checked.
    - Any other exception propagates, so a module that exists but is broken
      becomes a FAIL rather than being disguised as unbuilt work.
    """
    try:
        return importlib.import_module(name), None
    except ModuleNotFoundError as exc:
        missing = exc.name or name
        if missing == name or name.startswith(missing + "."):
            return None, pending(f"{name} does not exist yet")
        return None, failed(
            f"{name} needs `{missing}`, which this interpreter does not have - " + VENV_HINT
        )


def module_attr(module: ModuleType, attr: str) -> tuple[Any, str]:
    """Fetch an agreed symbol, or name precisely which one is missing."""
    value = getattr(module, attr, None)
    if value is None:
        return None, f"{module.__name__}.{attr} does not exist yet"
    return value, ""


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

_CONFIG_MISSING = object()

# Confirmed with the lead. All five live under `safety` in config/default.yaml.
# Three of them - the drawdown limit, the losing-streak limit and the error count -
# were written as null and marked OPERATOR REQUIRED until the operator supplied
# values on 2026-09-08. The other two were always real values: invariant 14 fixes
# the data-block limit at one decision bar, and architecture-context.md fixes the
# error-rate window at the trailing hour. The OPERATOR REQUIRED path in
# `required_thresholds` stays: it is what a *future* unset key reports through,
# and it simply no longer fires on these five.
KEY_MAX_DATA_BLOCKS = "safety.max_consecutive_data_blocks"
KEY_MAX_DRAWDOWN = "safety.max_drawdown_pct"
KEY_MAX_LOSSES = "safety.max_consecutive_losses"
KEY_MAX_ERRORS = "safety.max_errors_in_window"
KEY_ERROR_WINDOW = "safety.error_rate_window_s"


def load_config(root: Path) -> tuple[Mapping[str, Any] | None, Outcome | None]:
    """Read `config/default.yaml`.

    `pyyaml` is the approved parser (architecture stack table), `safe_load` only.
    There is deliberately no second parser here: two parsers are two behaviours,
    and they diverge on something subtle at the worst possible moment.
    """
    path = root / "config" / "default.yaml"
    if not path.is_file():
        return None, pending("config/default.yaml does not exist yet")
    yaml_mod, problem = try_import("yaml")
    if yaml_mod is None:
        return None, problem
    data = yaml_mod.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config/default.yaml did not parse to a mapping")
    return data, None


def config_get(config: Mapping[str, Any], dotted: str) -> Any:
    """Look a dotted key up. Returns the sentinel `_CONFIG_MISSING` when absent.

    A key present but `null` returns None, which is not the same thing: the lead
    writes OPERATOR REQUIRED thresholds as null, and a criterion must report those
    as PENDING rather than accuse anyone of having built the wrong thing.
    """
    node: Any = config
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return _CONFIG_MISSING
        node = node[part]
    return node


def required_thresholds(
    config: Mapping[str, Any], keys: Sequence[str]
) -> tuple[dict[str, Any], Outcome | None]:
    values: dict[str, Any] = {}
    for key in keys:
        value = config_get(config, key)
        if value is _CONFIG_MISSING:
            return {}, pending("config key `" + key + "` is not defined yet")
        if value is None:
            return {}, pending(
                "the operator has not set `" + key + "` (null, OPERATOR REQUIRED)"
            )
        values[key] = value
    return values, None


def as_decimal(value: Any, what: str) -> Decimal:
    """Money and ratios cross into this script as Decimal, never float."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError(what + " is a bool, not a number")
    if isinstance(value, int):
        return Decimal(value)
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(what + " is not a decimal: " + repr(value)) from exc


# --------------------------------------------------------------------------- #
# docs_vocabulary - spec 02
# --------------------------------------------------------------------------- #

VOCAB_SOURCE = Path("context") / "ai-workflow-rules.md"
VOCAB_HEADING = "## Retired vocabulary"
TRACKER = Path("context") / "progress-tracker.md"
TRACKER_EXCLUDED_HEADING = "## Decision history"

_BACKTICKED = re.compile(r"`([^`]+)`")
_STRIKETHROUGH = re.compile(r"~~.+?~~")


@dataclass(frozen=True)
class RetiredTerm:
    term: str
    # Same-line co-occurrence cues. Empty means the bare term is a hit anywhere.
    # These come out of the table's middle column, never out of this file: a
    # term-specific rule in code would be a hardcode wearing a disguise.
    qualifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetiredTable:
    terms: tuple[RetiredTerm, ...]
    table_lines: frozenset[int]  # 1-based line numbers of the table itself


def parse_retired_terms(root: Path) -> RetiredTable:
    """Read the retired-term table out of ai-workflow-rules.md.

    Three columns: the term, an optional same-line qualifier, and what superseded
    it. A qualifier column of `-` (or an em dash) means the bare term matches; a
    row naming qualifiers is a hit only when the matched line also contains one of
    them.

    Parsed rather than hardcoded, so adding a row - with or without a qualifier -
    is all it takes to extend the check, which is the whole point of the criterion.
    """
    path = root / VOCAB_SOURCE
    if not path.is_file():
        raise FileNotFoundError(VOCAB_SOURCE.as_posix() + " is missing")
    lines = path.read_text(encoding="utf-8").splitlines()

    start = next((i for i, line in enumerate(lines) if line.strip() == VOCAB_HEADING), None)
    if start is None:
        raise ValueError(VOCAB_SOURCE.as_posix() + " has no `" + VOCAB_HEADING + "` section")

    header = next(
        (
            i
            for i in range(start, len(lines))
            if lines[i].lstrip().startswith("|") and "Retired term" in lines[i]
        ),
        None,
    )
    if header is None:
        raise ValueError(VOCAB_SOURCE.as_posix() + " has no retired-term table")

    terms: list[RetiredTerm] = []
    seen: set[str] = set()
    table_lines: set[int] = set()
    row = header
    while row < len(lines) and lines[row].lstrip().startswith("|"):
        table_lines.add(row + 1)
        cells = [c.strip() for c in lines[row].strip().strip("|").split("|")]
        if row > header + 1 and cells:
            # One cell may name several terms; they share the row's qualifiers.
            qualifiers = tuple(_BACKTICKED.findall(cells[1])) if len(cells) > 1 else ()
            for term in _BACKTICKED.findall(cells[0]):
                if term not in seen:
                    seen.add(term)
                    terms.append(RetiredTerm(term, qualifiers))
        row += 1

    if not terms:
        raise ValueError("the retired-term table parsed to zero terms")
    return RetiredTable(tuple(terms), frozenset(table_lines))


def term_pattern(term: str) -> re.Pattern[str]:
    """Word-boundary-aware, case-insensitive matcher for one retired term.

    The trailing boundary is load-bearing: `paper.starting_balance` is retired and
    `paper.starting_balances` is current, and the second contains the first. The
    leading one keeps the retired count `eight` out of "weight" and "Weight".
    """
    left = r"(?<![0-9A-Za-z_])" if (term[:1].isalnum() or term[:1] == "_") else ""
    right = r"(?![0-9A-Za-z_])" if (term[-1:].isalnum() or term[-1:] == "_") else ""
    return re.compile(left + re.escape(term) + right, re.IGNORECASE)


# A section whose job is to catalogue superseded things necessarily names them.
# The excluded region is always the smallest section doing that job, ending at the
# next `## ` heading - never a whole file. Exactly two qualify, and the lead's
# condition on the first is written into `ai-workflow-rules.md`: the exclusion
# holds only while that section stays short and wholly about the check.
EXCLUDED_SECTIONS: tuple[tuple[Path, str], ...] = (
    (VOCAB_SOURCE, VOCAB_HEADING),
    (TRACKER, TRACKER_EXCLUDED_HEADING),
)


def section_lines(path: Path, heading: str) -> frozenset[int]:
    """1-based line numbers of one `## ` section, heading included.

    A `###` subheading does not end the section; only the next `## ` does.
    """
    if not path.is_file():
        return frozenset()
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return frozenset()
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return frozenset(range(start + 1, end + 1))


def excluded_lines(root: Path, rel: Path, table: RetiredTable) -> frozenset[int]:
    """Every excluded line in one file."""
    excluded: set[int] = set()
    for source, heading in EXCLUDED_SECTIONS:
        if source == rel:
            excluded |= section_lines(root / rel, heading)
    if rel == VOCAB_SOURCE:
        # Belt and braces: the table is inside the excluded section today, and
        # stays excluded if it is ever moved out of it.
        excluded |= table.table_lines
    return frozenset(excluded)


def scanned_docs(root: Path) -> list[Path]:
    files = [Path("AGENTS.md"), Path("README.md")]
    files += sorted(p.relative_to(root) for p in (root / "context").glob("*.md"))
    return [f for f in files if (root / f).is_file()]


def check_docs_vocabulary(ctx: VerifyContext) -> Outcome:
    table = parse_retired_terms(ctx.root)
    patterns = [(entry, term_pattern(entry.term)) for entry in table.terms]
    files = scanned_docs(ctx.root)
    hits: list[str] = []

    for rel in files:
        skip = excluded_lines(ctx.root, rel, table)
        text = (ctx.root / rel).read_text(encoding="utf-8")
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if lineno in skip:
                continue
            line = _STRIKETHROUGH.sub(" ", raw)
            lowered = line.lower()
            for entry, pattern in patterns:
                if not pattern.search(line):
                    continue
                if entry.qualifiers and not any(q.lower() in lowered for q in entry.qualifiers):
                    continue
                hits.append(rel.as_posix() + ":" + str(lineno) + ": `" + entry.term + "`")

    if hits:
        shown = "; ".join(hits[:8])
        more = " (+" + str(len(hits) - 8) + " more)" if len(hits) > 8 else ""
        return failed(str(len(hits)) + " retired term(s): " + shown + more)
    return passed(
        str(len(files)) + " files scanned, " + str(len(table.terms)) + " retired terms, no hit"
    )


# --------------------------------------------------------------------------- #
# orchestrator_empty_registry - spec 01
# --------------------------------------------------------------------------- #

CHAIN_SYMBOLS = ("GUARD_CHAIN", "OPPORTUNITY_CHAIN", "MANAGE_CHAIN")

ORCHESTRATOR_CONTRACT = (
    "expected (agreed with the lead): acsoe.bootstrap exposing GUARD_CHAIN, "
    "OPPORTUNITY_CHAIN, MANAGE_CHAIN; acsoe.core.contracts.Chains(guard, opportunity, "
    "manage); acsoe.core.orchestrator.Orchestrator(config=, clock=, clients=, chains=)"
    " with .tick() -> State"
)


def _harness_doubles() -> tuple[Any, Outcome | None]:
    """The fakes the test harness already defines, reused so there is one set."""
    module, problem = try_import("tests.harness.doubles")
    if module is None:
        return None, problem
    factory, missing = module_attr(module, "build_verify_doubles")
    if factory is None:
        return None, pending("test doubles unavailable: " + missing)
    return factory(), None


def check_orchestrator_empty_registry(ctx: VerifyContext) -> Outcome:
    with root_import_path(ctx.root):
        bootstrap, problem = try_import("acsoe.bootstrap")
        if bootstrap is None:
            return problem or pending("acsoe.bootstrap does not exist yet")

        chains: dict[str, Any] = {}
        for symbol in CHAIN_SYMBOLS:
            value = getattr(bootstrap, symbol, None)
            if value is None:
                return pending("acsoe.bootstrap." + symbol + " does not exist yet")
            if not isinstance(value, Sequence):
                return failed("acsoe.bootstrap." + symbol + " is not an ordered sequence")
            chains[symbol] = value

        contracts, problem = try_import("acsoe.core.contracts")
        if contracts is None:
            return problem or pending("acsoe.core.contracts does not exist yet")
        chains_cls, missing = module_attr(contracts, "Chains")
        if chains_cls is None:
            return pending(missing + " (" + ORCHESTRATOR_CONTRACT + ")")

        orch_mod, problem = try_import("acsoe.core.orchestrator")
        if orch_mod is None:
            return problem or pending("acsoe.core.orchestrator does not exist yet")
        orchestrator_cls, missing = module_attr(orch_mod, "Orchestrator")
        if orchestrator_cls is None:
            return pending(missing + " (" + ORCHESTRATOR_CONTRACT + ")")

        doubles, problem = _harness_doubles()
        if doubles is None:
            return problem or pending("test doubles unavailable")

        registered = sum(len(chains[s]) for s in CHAIN_SYMBOLS)
        orchestrator = orchestrator_cls(
            config=doubles.config,
            clock=doubles.clock,
            clients=doubles.clients,
            chains=chains_cls(
                guard=chains["GUARD_CHAIN"],
                opportunity=chains["OPPORTUNITY_CHAIN"],
                manage=chains["MANAGE_CHAIN"],
            ),
        )
        state = orchestrator.tick()

        if not isinstance(state, Mapping):
            return failed("Orchestrator.tick() returned " + type(state).__name__ + ", not a State")
        if "system" not in state:
            return failed('tick() returned a state with no "system" region')
        system = state["system"]
        if not isinstance(system, Mapping) or "mode" not in system:
            return failed('state["system"] is not a mapping carrying "mode"')
        if "guard_blockers" not in state:
            return failed(
                'state["guard_blockers"] is absent; the contract says an empty list on an '
                "unblocked tick, never absent"
            )
        if state["guard_blockers"]:
            return failed("an empty registry produced guard blockers")
        if "trading_blocked_by" in state:
            return failed("an empty registry set trading_blocked_by")

        return passed(
            "one tick completed against "
            + str(registered)
            + " registered engines; empty chains are valid, "
            'state["system"]["mode"]='
            + repr(system["mode"])
        )


# --------------------------------------------------------------------------- #
# db_migrates_from_empty - spec 01
# --------------------------------------------------------------------------- #

# The nine tables of the storage model in context/architecture-context.md, which is
# the authority. B's runner exports the same set as EXPECTED_TABLES; the criterion
# cross-checks the two so a drift between the declaration and the SQL is caught.
DOCUMENTED_TABLES = frozenset(
    {
        "trades",
        "rejections",
        "runs",
        "leaderboard",
        "positions",
        "orders",
        "equity_snapshots",
        "block_records",
        "commands",
    }
)


def _apply_migrations(ctx: VerifyContext, db_path: Path) -> tuple[ModuleType | None, Outcome | None]:
    """Run B's migration runner against `db_path`. Must be called inside
    `root_import_path`. Returns (migrations module, early PENDING outcome)."""
    mig_dir = ctx.root / "db" / "migrations"
    if not mig_dir.is_dir():
        return None, pending("db/migrations/ does not exist yet")
    if not any(mig_dir.glob("*.sql")):
        return None, pending("db/migrations/ holds no .sql migration yet")

    module, problem = try_import("acsoe.clients.store.migrations")
    if module is None:
        return None, problem or pending("acsoe.clients.store.migrations does not exist yet")
    apply_fn, missing = module_attr(module, "apply_migrations")
    if apply_fn is None:
        return None, pending(missing)

    apply_fn(db_path, migrations_dir=mig_dir)
    return module, None


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows if not r[0].startswith("sqlite_")}


def check_db_migrates_from_empty(ctx: VerifyContext) -> Outcome:
    with (
        root_import_path(ctx.root),
        tempfile.TemporaryDirectory(prefix="acsoe-verify-db-") as tmp,
    ):
        db_path = Path(tmp) / "acsoe.sqlite"
        module, early = _apply_migrations(ctx, db_path)
        if early is not None:
            return early
        if not db_path.is_file():
            return failed("apply_migrations created no database file")

        tables = _table_names(db_path)
        bookkeeping = getattr(module, "BOOKKEEPING_TABLE", "schema_migrations")
        missing = sorted(DOCUMENTED_TABLES - tables)
        if missing:
            return failed("tables missing after migration: " + ", ".join(missing))

        declared = getattr(module, "EXPECTED_TABLES", None)
        if declared is not None and set(declared) != DOCUMENTED_TABLES:
            only_declared = sorted(set(declared) - DOCUMENTED_TABLES)
            only_documented = sorted(DOCUMENTED_TABLES - set(declared))
            return failed(
                "EXPECTED_TABLES disagrees with the storage model in "
                "architecture-context.md: declared-only="
                + str(only_declared)
                + " documented-only="
                + str(only_documented)
            )

        extras = sorted(tables - DOCUMENTED_TABLES - {bookkeeping})
        note = "; extra tables: " + ", ".join(extras) if extras else ""
        return passed(
            "fresh database migrated to all "
            + str(len(DOCUMENTED_TABLES))
            + " documented tables"
            + note
        )


# --------------------------------------------------------------------------- #
# seed_fixtures_present - spec 01
# --------------------------------------------------------------------------- #

MICROSECONDS = 1_000_000


def _seeded_block_run(conn: sqlite3.Connection) -> tuple[int, int, int]:
    """Longest run of consecutive blocked ticks carrying a `data_guard` row.

    A tick is `(run_id, cycle_id)`, never `cycle_id` alone - `cycle_id` restarts at
    1 with each process and the seed deliberately reuses values across two runs.
    Ordering is by `ts`, never by `cycle_id`, for exactly the same reason. A tick on
    which two guards blocked contributes one, not two.

    Returns (longest run length, distinct run_ids in that run, double-blocker ticks
    inside it).
    """
    rows = conn.execute(
        "SELECT run_id, cycle_id, ts, blocked_by FROM block_records ORDER BY ts, rowid"
    ).fetchall()

    order: list[tuple[str, int]] = []
    guarded: dict[tuple[str, int], bool] = {}
    blockers: dict[tuple[str, int], set[str]] = {}
    for run_id, cycle_id, _ts, blocked_by in rows:
        tick = (str(run_id), int(cycle_id))
        if tick not in guarded:
            order.append(tick)
            guarded[tick] = False
            blockers[tick] = set()
        blockers[tick].add(str(blocked_by))
        if str(blocked_by) == "data_guard":
            guarded[tick] = True

    best: list[tuple[str, int]] = []
    current: list[tuple[str, int]] = []
    for tick in order:
        if guarded[tick]:
            current.append(tick)
            if len(current) > len(best):
                best = list(current)
        else:
            current = []

    run_ids = {t[0] for t in best}
    doubles = sum(1 for t in best if len(blockers[t]) > 1)
    return len(best), len(run_ids), doubles


def _seeded_max_drawdown(conn: sqlite3.Connection) -> Decimal:
    rows = conn.execute("SELECT equity, peak_equity FROM equity_snapshots").fetchall()
    worst = Decimal(0)
    for equity, peak in rows:
        peak_d = as_decimal(peak, "equity_snapshots.peak_equity")
        if peak_d <= 0:
            continue
        drawdown = (peak_d - as_decimal(equity, "equity_snapshots.equity")) / peak_d
        worst = max(worst, drawdown)
    return worst


def _seeded_losing_streak(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT realised_pnl FROM trades WHERE closed_at IS NOT NULL ORDER BY closed_at, rowid"
    ).fetchall()
    streak = 0
    for (pnl,) in rows:
        if as_decimal(pnl, "trades.realised_pnl") < 0:
            streak += 1
        else:
            streak = 0
    return streak


def _seeded_error_blocks(conn: sqlite3.Connection, since_us: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM block_records WHERE status = 'ERROR' AND ts >= ?", (since_us,)
    ).fetchone()
    return int(row[0])


def _count(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def _seed_threshold_kwargs(
    seed_mod: ModuleType, seed_fn: Any, values: Mapping[str, Any]
) -> tuple[dict[str, Any], Outcome | None]:
    """Build the `thresholds=` argument `seed_database` scales its fixtures against.

    Spec 13 makes the seed's thresholds **injected, not read from config**, so the
    caller is the one that has to hand it the real numbers. Seeding with the module
    defaults and then asserting against `config/default.yaml` is the exact defect
    spec 13 warns about: a fixture pinned to a constant stops overshooting the moment
    the operator raises a limit, and the criterion accuses the seed of a bug the
    criterion caused. A fabricated minimal subject whose `seed_database` takes no
    `thresholds` parameter is seeded as-is.
    """
    try:
        parameters = inspect.signature(seed_fn).parameters
    except (TypeError, ValueError):
        return {}, None
    if "thresholds" not in parameters:
        return {}, None
    cls = getattr(seed_mod, "SeedThresholds", None)
    if cls is None:
        return {}, failed(
            "seed_database takes a `thresholds` argument but the module exposes no "
            "SeedThresholds to build it from"
        )
    try:
        return {"thresholds": cls(**values)}, None
    except TypeError as exc:
        return {}, failed(
            "SeedThresholds does not accept the configured safety keys ("
            + ", ".join(sorted(values))
            + "): "
            + str(exc)
        )


def check_seed_fixtures_present(ctx: VerifyContext) -> Outcome:
    config, problem = load_config(ctx.root)
    if config is None:
        return problem or pending("config/default.yaml does not exist yet")
    thresholds, early = required_thresholds(
        config,
        [KEY_MAX_DATA_BLOCKS, KEY_MAX_DRAWDOWN, KEY_MAX_LOSSES, KEY_MAX_ERRORS, KEY_ERROR_WINDOW],
    )
    if early is not None:
        return early

    max_blocks = int(thresholds[KEY_MAX_DATA_BLOCKS])
    max_drawdown = as_decimal(thresholds[KEY_MAX_DRAWDOWN], KEY_MAX_DRAWDOWN)
    max_losses = int(thresholds[KEY_MAX_LOSSES])
    max_errors = int(thresholds[KEY_MAX_ERRORS])
    window_s = int(thresholds[KEY_ERROR_WINDOW])

    with root_import_path(ctx.root):
        seed_mod, problem = try_import("acsoe.clients.store.seed")
        if seed_mod is None:
            return problem or pending("acsoe.clients.store.seed does not exist yet")
        seed_fn, missing = module_attr(seed_mod, "seed_database")
        if seed_fn is None:
            return pending(missing)

        seed_kwargs, mismatch = _seed_threshold_kwargs(
            seed_mod,
            seed_fn,
            {
                "max_consecutive_data_blocks": max_blocks,
                "max_drawdown_pct": max_drawdown,
                "max_consecutive_losses": max_losses,
                "max_errors_in_window": max_errors,
                "error_rate_window_s": window_s,
            },
        )
        if mismatch is not None:
            return mismatch

        with tempfile.TemporaryDirectory(prefix="acsoe-verify-seed-") as tmp:
            db_path = Path(tmp) / "acsoe.sqlite"
            fixtures = seed_fn(db_path, **seed_kwargs)
            if not db_path.is_file():
                return failed("seed_database created no database file")

            conn = sqlite3.connect(db_path)
            try:
                run_length, run_ids, doubles = _seeded_block_run(conn)
                drawdown = _seeded_max_drawdown(conn)
                losing_streak = _seeded_losing_streak(conn)
                open_positions = _count(
                    conn, "SELECT COUNT(*) FROM positions WHERE status = 'open'"
                )
                resting_orders = _count(
                    conn, "SELECT COUNT(*) FROM orders WHERE status = 'resting'"
                )
                trades = _count(conn, "SELECT COUNT(*) FROM trades")
                rejections = _count(conn, "SELECT COUNT(*) FROM rejections")
                seed_now = getattr(fixtures, "seed_now", None)
                if seed_now is None:
                    row = conn.execute("SELECT MAX(ts) FROM block_records").fetchone()
                    seed_now = int(row[0] or 0)
                errors = _seeded_error_blocks(conn, int(seed_now) - window_s * MICROSECONDS)
            finally:
                conn.close()

    problems: list[str] = []
    if run_length <= max_blocks:
        problems.append(
            "consecutive data_guard tick run is "
            + str(run_length)
            + ", not longer than "
            + KEY_MAX_DATA_BLOCKS
            + "="
            + str(max_blocks)
        )
    if run_ids < 2:
        problems.append("the outage run spans " + str(run_ids) + " run_id(s), not two")
    if doubles < 1:
        problems.append(
            "no tick inside the outage run has a second, co-occurring blocker, so the "
            "one-tick-one-count rule is never exercised"
        )
    if open_positions < 1:
        problems.append("no open position")
    if resting_orders < 1:
        problems.append("no resting entry order")
    if drawdown <= max_drawdown:
        problems.append(
            "max seeded drawdown "
            + str(drawdown)
            + " is not past "
            + KEY_MAX_DRAWDOWN
            + "="
            + str(max_drawdown)
        )
    if losing_streak <= max_losses:
        problems.append(
            "trailing losing streak "
            + str(losing_streak)
            + " is not past "
            + KEY_MAX_LOSSES
            + "="
            + str(max_losses)
        )
    if errors <= max_errors:
        problems.append(
            "ERROR block records in the trailing window: "
            + str(errors)
            + ", not past "
            + KEY_MAX_ERRORS
            + "="
            + str(max_errors)
        )
    if trades < 1:
        problems.append("no trades")
    if rejections < 1:
        problems.append("no rejections")

    # Cross-check the named-fixture surface against what is actually in the
    # database. A fixture accessor that disagrees with its own rows is the exact
    # failure this criterion exists to catch.
    declared_run = getattr(getattr(fixtures, "consecutive_data_block_run", None), "length", None)
    if declared_run is not None and int(declared_run) != run_length:
        problems.append(
            "SeedFixtures declares an outage run of "
            + str(declared_run)
            + " ticks; the database holds "
            + str(run_length)
        )
    declared_streak = getattr(getattr(fixtures, "losing_streak", None), "length", None)
    if declared_streak is not None and int(declared_streak) != losing_streak:
        problems.append(
            "SeedFixtures declares a losing streak of "
            + str(declared_streak)
            + "; the database holds "
            + str(losing_streak)
        )
    declared_errors = getattr(getattr(fixtures, "error_blocks", None), "count", None)
    if declared_errors is not None and int(declared_errors) != errors:
        problems.append(
            "SeedFixtures declares "
            + str(declared_errors)
            + " ERROR block records in the window; the database holds "
            + str(errors)
        )

    if problems:
        return failed("; ".join(problems))
    return passed(
        "all six fixtures present: outage run "
        + str(run_length)
        + " ticks over "
        + str(run_ids)
        + " run_ids ("
        + str(doubles)
        + " double-blocker), "
        + str(open_positions)
        + " open position(s), "
        + str(resting_orders)
        + " resting order(s), drawdown "
        + str(drawdown)
        + ", losing streak "
        + str(losing_streak)
        + ", "
        + str(errors)
        + " ERROR blocks in the window, "
        + str(trades)
        + " trades / "
        + str(rejections)
        + " rejections"
    )


# --------------------------------------------------------------------------- #
# record_sample_valid - spec 01
# --------------------------------------------------------------------------- #

RECORD_SAMPLE = Path("tests") / "fixtures" / "record_sample.jsonl"

RECORD_KEYS = frozenset({"v", "kind", "pair", "channel", "ts_exchange", "ts_recv", "payload"})
RECORD_KINDS = frozenset({"tick", "gap", "session"})
RECORDER_CHANNEL = "_recorder"
GAP_PAYLOAD_KEYS = ("reason", "disconnected_at", "reconnected_at", "gap_ms", "attempt")
SESSION_PAYLOAD_KEYS = ("event", "url", "subscriptions")

_ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def _validate_record_line(obj: Any) -> list[str]:
    """Validate one recorder line against A's schema (spec 10)."""
    problems: list[str] = []
    if not isinstance(obj, dict):
        return ["line is " + type(obj).__name__ + ", not a JSON object"]

    keys = set(obj)
    if keys != RECORD_KEYS:
        extra = sorted(keys - RECORD_KEYS)
        absent = sorted(RECORD_KEYS - keys)
        if extra:
            problems.append("unexpected key(s) " + ", ".join(extra))
        if absent:
            problems.append("missing key(s) " + ", ".join(absent))

    if obj.get("v") != 1:
        problems.append("v is " + repr(obj.get("v")) + ", expected 1")

    kind = obj.get("kind")
    if kind not in RECORD_KINDS:
        problems.append("kind is " + repr(kind) + ", expected one of " + str(sorted(RECORD_KINDS)))

    pair = obj.get("pair")
    if pair is not None and not (isinstance(pair, str) and pair):
        problems.append("pair is neither null nor a non-empty string")

    channel = obj.get("channel")
    if not (isinstance(channel, str) and channel):
        problems.append("channel is not a non-empty string")
    elif kind in {"gap", "session"} and channel != RECORDER_CHANNEL:
        problems.append("marker line has channel " + repr(channel) + ", expected _recorder")

    ts_exchange = obj.get("ts_exchange")
    if ts_exchange is not None and not (
        isinstance(ts_exchange, str) and _ISO_Z.match(ts_exchange)
    ):
        problems.append("ts_exchange is neither null nor ISO-8601 UTC ending Z")

    ts_recv = obj.get("ts_recv")
    if not (isinstance(ts_recv, str) and _ISO_Z.match(ts_recv)):
        problems.append("ts_recv is not an ISO-8601 UTC string ending Z")

    payload = obj.get("payload")
    if not isinstance(payload, dict):
        problems.append("payload is " + type(payload).__name__ + ", expected a JSON object")
    elif kind == "gap":
        absent = [k for k in GAP_PAYLOAD_KEYS if k not in payload]
        if absent:
            problems.append("gap payload missing " + ", ".join(absent))
        for numeric in ("gap_ms", "attempt"):
            value = payload.get(numeric)
            if numeric in payload and (isinstance(value, bool) or not isinstance(value, int)):
                problems.append("gap payload " + numeric + " is not an int")
    elif kind == "session":
        absent = [k for k in SESSION_PAYLOAD_KEYS if k not in payload]
        if absent:
            problems.append("session payload missing " + ", ".join(absent))
        if payload.get("event") not in {"start", "stop"}:
            problems.append("session payload event is " + repr(payload.get("event")))
        if "subscriptions" in payload and not isinstance(payload["subscriptions"], list):
            problems.append("session payload subscriptions is not a list")

    return problems


def check_record_sample_valid(ctx: VerifyContext) -> Outcome:
    path = ctx.root / RECORD_SAMPLE
    if not path.is_file():
        return pending(RECORD_SAMPLE.as_posix() + " does not exist yet")

    raw = path.read_text(encoding="utf-8")
    if not raw:
        return failed(RECORD_SAMPLE.as_posix() + " is empty")

    problems: list[str] = []
    kinds_seen: set[str] = set()
    # `read_text` already folds CRLF to LF through universal newlines, and
    # `.gitattributes` marks `tests/fixtures/**` as `-text` so a Windows clone
    # cannot rewrite the bytes. The strip below is defence in depth against a
    # sample that reaches us through some third path.
    lines = [line.rstrip("\r") for line in raw.split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    else:
        problems.append("file does not end with a newline")

    for number, line in enumerate(lines, start=1):
        if not line.strip():
            problems.append("line " + str(number) + ": blank line")
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append("line " + str(number) + ": not JSON - " + exc.msg)
            continue
        if isinstance(obj, dict):
            kind = obj.get("kind")
            if isinstance(kind, str):
                kinds_seen.add(kind)
        for problem in _validate_record_line(obj):
            problems.append("line " + str(number) + ": " + problem)

    # The sample is meant to exercise the marker path. A sample carrying only
    # ticks would let a validator that never handles a gap marker look correct.
    absent_kinds = sorted(RECORD_KINDS - kinds_seen)
    if absent_kinds:
        problems.append("sample carries no line of kind " + ", ".join(absent_kinds))

    if problems:
        shown = "; ".join(problems[:6])
        more = " (+" + str(len(problems) - 6) + " more)" if len(problems) > 6 else ""
        return failed(str(len(problems)) + " problem(s): " + shown + more)
    return passed(
        str(len(lines))
        + " lines valid against the recorder schema; kinds present: "
        + ", ".join(sorted(kinds_seen))
    )


# --------------------------------------------------------------------------- #
# toolchain_green - spec 01
# --------------------------------------------------------------------------- #

# Third element is the highest exit code the tool produces *itself*. pytest
# documents 0-5 (`pytest.ExitCode`); mypy and ruff use 0 for clean, 1 for findings
# and 2 for a usage or internal error. A returncode above that range was not chosen
# by the tool at all - the process died before it could return one.
TOOLCHAIN = (
    ("pytest", ["-m", "pytest", "tests/", "-q"], 5),
    ("mypy", ["-m", "mypy", "--strict", "src/"], 2),
    ("ruff", ["-m", "ruff", "check", "src/"], 2),
)

# Windows reports a fatal fault as an NTSTATUS in the returncode. Named here so the
# criterion's one line is readable without going to look 3221225477 up.
NTSTATUS_NAMES = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000374: "HEAP_CORRUPTION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000409: "STACK_BUFFER_OVERRUN",
}

_SUMMARY_DURATION = re.compile(r"\bin \d+(\.\d+)?s\b")
_SUMMARY_COUNT = re.compile(r"\b\d+ (passed|failed|error|errors|skipped|xfailed|xpassed)\b")
_SUMMARY_BAD = re.compile(r"\b\d+ (failed|error|errors)\b")


def pytest_summary_line(output: str) -> str | None:
    """pytest's final counts line, e.g. `519 passed, 1 error in 13.37s`.

    Read from the end, because the same words appear in the progress output above
    it. Returned so that a crash can be described against what the run had already
    managed to report before it died.
    """
    for raw in reversed(output.strip().splitlines()):
        line = raw.strip().strip("=").strip()
        if _SUMMARY_DURATION.search(line) and _SUMMARY_COUNT.search(line):
            return line
    return None


def exit_status(returncode: int) -> str:
    """A returncode in the form the operator can actually look up."""
    if returncode < 0:
        return "fatal signal " + str(-returncode)
    if returncode > 0xFFFF:
        name = NTSTATUS_NAMES.get(returncode)
        return (
            str(returncode)
            + " (0x"
            + format(returncode, "08X")
            + ("" if name is None else " " + name)
            + ")"
        )
    return "exit " + str(returncode)


def describe_exit(name: str, returncode: int, output: str, tool_max_exit: int) -> str:
    """One toolchain failure, in words that separate a verdict from a death.

    A tool exiting inside its own documented range has *reported* something, and the
    tail of its output says what. A returncode outside that range is the process
    dying: an NTSTATUS on Windows, `-N` for fatal signal N on POSIX.

    That distinction is the entire point of this function. A process that crashes
    *after* printing its summary is indistinguishable from a failing suite when all
    you have is a returncode - which is how a memory fault gets filed as a flaky
    test and re-run until it goes green instead of being fixed.
    """
    lines = output.strip().splitlines()
    tail = " | ".join(t.strip() for t in lines[-3:]) if lines else "(no output)"
    if 0 <= returncode <= tool_max_exit:
        return name + " exit " + str(returncode) + ": " + tail

    crashed = (
        name
        + " CRASHED: the process died with "
        + exit_status(returncode)
        + ", which is outside the 0-"
        + str(tool_max_exit)
        + " range "
        + name
        + " returns"
    )
    summary = pytest_summary_line(output) if name == "pytest" else None
    if summary is None:
        return crashed + ". Last output: " + tail
    if _SUMMARY_BAD.search(summary):
        return crashed + ", after reporting `" + summary + "`"
    return (
        crashed
        + ", after reporting `"
        + summary
        + "` - every test passed and the process then died, so this is NOT a test "
        + "failure and re-running until it goes green hides it"
    )


def _interpreter_with_toolchain(root: Path) -> tuple[str | None, list[str]]:
    """Pick an interpreter that can actually run the three commands.

    Prefers whatever is running this script; falls back to the project virtualenv
    so the gate behaves the same whether or not the operator remembered to
    activate it. The chosen interpreter is named in the criterion's message.
    """
    candidates = [sys.executable]
    for relative in ("Scripts/python.exe", "bin/python"):
        candidate = root / ".venv" / relative
        if candidate.is_file():
            candidates.append(str(candidate))

    probe = (
        "import importlib.util as u, sys;"
        "missing=[m for m in ('pytest','mypy','ruff') if u.find_spec(m) is None];"
        "print(','.join(missing))"
    )
    last_missing: list[str] = ["pytest", "mypy", "ruff"]
    for candidate in candidates:
        try:
            done = subprocess.run(  # fixed argv, never a shell
                [candidate, "-c", probe], capture_output=True, text=True, timeout=120
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode != 0:
            continue
        missing = [m for m in done.stdout.strip().split(",") if m]
        if not missing:
            return candidate, []
        last_missing = missing
    return None, last_missing


def _run_tool(
    interpreter: str, args: list[str], root: Path, env: dict[str, str]
) -> tuple[int | None, str]:
    """One toolchain command. `None` as the returncode means it timed out."""
    try:
        done = subprocess.run(  # fixed argv, never a shell
            [interpreter, *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None, ""
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def check_toolchain_green(ctx: VerifyContext) -> Outcome:
    """The three toolchain commands, with one retry reserved for a crash.

    A returncode inside a tool's documented range is a *verdict* - the tool looked at
    the code and reported on it - and a verdict is never retried, because re-running
    a failing suite until it goes green is the exact behaviour `describe_exit` exists
    to make impossible. A returncode outside that range is the process *dying*, which
    says nothing about the code at all, so that one command is run a second time.

    The retry is bounded at one and the crash is never swallowed: a clean retry still
    reports the crash in the PASS message, and a second crash FAILs. This is a known
    intermittent native memory fault in the seed write path, not root-caused and
    suspected to be hardware - see `docs/build-log/phase-0.md`. The retry is a
    mitigation that keeps the gate usable while leaving the fault visible in every
    run it occurs in.
    """
    if os.environ.get(RECURSION_GUARD_ENV):
        return pending("skipped: this run is inside a toolchain_green subprocess")
    if not (ctx.root / "src").is_dir():
        return pending("src/ does not exist yet")

    interpreter, missing = _interpreter_with_toolchain(ctx.root)
    if interpreter is None:
        # Not PENDING. The subject - `src/` - exists; it is the environment that is
        # broken, and a broken environment reporting as orderly progress is how a
        # phase sits at "no FAIL" while nothing is being checked.
        return failed(
            "no interpreter has the toolchain installed (missing: "
            + ", ".join(missing)
            + ") - "
            + VENV_HINT
        )

    env = dict(os.environ)
    env[RECURSION_GUARD_ENV] = "1"
    failures: list[str] = []
    survived: list[str] = []
    crashed = False
    for name, args, tool_max_exit in TOOLCHAIN:
        returncode, output = _run_tool(interpreter, args, ctx.root, env)
        if returncode is None:
            failures.append(name + " timed out after " + str(SUBPROCESS_TIMEOUT_S) + "s")
            continue
        if returncode == 0:
            continue
        if 0 <= returncode <= tool_max_exit:
            # A verdict. Not retried, at any exit code, ever.
            failures.append(describe_exit(name, returncode, output, tool_max_exit))
            continue

        # A crash. One retry, and only one - this branch is straight-line and there is
        # no path back into it for the same command.
        first = describe_exit(name, returncode, output, tool_max_exit)
        returncode, output = _run_tool(interpreter, args, ctx.root, env)
        if returncode is None:
            crashed = True
            failures.append(
                first
                + "; the retry then timed out after "
                + str(SUBPROCESS_TIMEOUT_S)
                + "s"
            )
            continue
        if returncode == 0:
            # Clean on the retry. PASS, but the crash is named in the message: a
            # mitigated fault that stops being reported stops being a known risk.
            survived.append(first + "; the retry was clean")
            continue
        if not (0 <= returncode <= tool_max_exit):
            crashed = True
            failures.append(first + "; the retry crashed too - " + describe_exit(
                name, returncode, output, tool_max_exit
            ))
            continue
        # The retry produced a verdict, so there is something to report about the
        # code itself. That verdict stands on its own and the crash is context.
        failures.append(
            describe_exit(name, returncode, output, tool_max_exit)
            + " (the first attempt crashed: "
            + first
            + ")"
        )

    label = Path(interpreter).name
    if failures:
        # The prefix is deliberate: the criterion prints one line, and a crash has to
        # be visible in it without opening anything.
        return failed(("CRASH - " if crashed else "") + "; ".join(failures))
    if survived:
        return passed(
            "pytest, mypy --strict and ruff all green ("
            + label
            + ") - RETRIED AFTER CRASH: "
            + "; ".join(survived)
        )
    return passed("pytest, mypy --strict and ruff all green (" + label + ")")


# --------------------------------------------------------------------------- #
# is_gate_matches_registry - spec 01
# --------------------------------------------------------------------------- #

REGISTRY_SOURCE = Path("context") / "engine-contracts.md"
REGISTRY_HEADING = "## Fixed engine order"


@dataclass(frozen=True)
class RegistryRow:
    number: int
    name: str
    is_gate: bool


def parse_engine_registry(root: Path) -> dict[str, RegistryRow]:
    """Read the fixed engine order out of engine-contracts.md, which is the
    authority. Parsed rather than hardcoded so a registry change moves the check."""
    path = root / REGISTRY_SOURCE
    if not path.is_file():
        raise FileNotFoundError(REGISTRY_SOURCE.as_posix() + " is missing")
    lines = path.read_text(encoding="utf-8").splitlines()

    start = next((i for i, line in enumerate(lines) if line.strip() == REGISTRY_HEADING), None)
    if start is None:
        raise ValueError(REGISTRY_SOURCE.as_posix() + " has no `" + REGISTRY_HEADING + "` section")
    header = next(
        (
            i
            for i in range(start, len(lines))
            if lines[i].lstrip().startswith("|") and "Gate" in lines[i] and "Name" in lines[i]
        ),
        None,
    )
    if header is None:
        raise ValueError(REGISTRY_SOURCE.as_posix() + " has no engine registry table")

    rows: dict[str, RegistryRow] = {}
    index = header + 2
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        cells = [c.strip() for c in lines[index].strip().strip("|").split("|")]
        index += 1
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        names = _BACKTICKED.findall(cells[1])
        if not names:
            continue
        rows[names[0]] = RegistryRow(int(cells[0]), names[0], "Y" in cells[2].upper())

    if not rows:
        raise ValueError("the engine registry table parsed to zero engines")
    return rows


def _registered_engines() -> tuple[list[Any], list[str], Outcome | None]:
    """Every engine reachable from the registries, runtime and offline.

    The offline chain is deliberately unreachable from `bootstrap.py` - that is
    what keeps architecture invariant 5 true - so it is collected separately from
    `cli/research.py`.
    """
    engines: list[Any] = []
    notes: list[str] = []
    blocking: Outcome | None = None

    bootstrap, problem = try_import("acsoe.bootstrap")
    if bootstrap is None:
        if problem is not None and problem.result is Result.FAIL:
            blocking = problem
        notes.append(problem.message if problem else "acsoe.bootstrap does not exist yet")
    else:
        for symbol in CHAIN_SYMBOLS:
            chain = getattr(bootstrap, symbol, None)
            if chain is None:
                notes.append("acsoe.bootstrap." + symbol + " does not exist yet")
            else:
                engines.extend(chain)

    research, problem = try_import("acsoe.cli.research")
    if research is None:
        if blocking is None and problem is not None and problem.result is Result.FAIL:
            blocking = problem
        notes.append(problem.message if problem else "acsoe.cli.research does not exist yet")
    else:
        builder = getattr(research, "build_offline_chain", None)
        if builder is None:
            notes.append("acsoe.cli.research.build_offline_chain does not exist yet")
        else:
            engines.extend(builder())
    return engines, notes, blocking


def check_is_gate_matches_registry(ctx: VerifyContext) -> Outcome:
    expected = parse_engine_registry(ctx.root)
    with root_import_path(ctx.root):
        engines, notes, blocking = _registered_engines()

        if blocking is not None:
            return blocking
        if notes:
            # A registry *source* is missing - the module, a chain symbol, or the
            # offline builder. That is a subject that does not exist yet, which is
            # what PENDING means.
            return pending("no engine registry to read yet (" + "; ".join(notes) + ")")

        problems: list[str] = []
        for engine in engines:
            name = getattr(engine, "name", None)
            if not isinstance(name, str):
                problems.append(type(engine).__name__ + " has no `name`")
                continue
            row = expected.get(name)
            if row is None:
                problems.append(name + " is registered but is not in the registry table")
                continue
            actual_gate = bool(getattr(engine, "is_gate", False))
            if actual_gate != row.is_gate:
                problems.append(
                    name
                    + " is_gate="
                    + str(actual_gate)
                    + " but the registry table says "
                    + str(row.is_gate)
                )
            actual_number = getattr(engine, "number", None)
            if actual_number != row.number:
                problems.append(
                    name
                    + " number="
                    + str(actual_number)
                    + " but the registry table says "
                    + str(row.number)
                )

    if problems:
        return failed(
            str(len(engines))
            + " engines registered; "
            + str(len(problems))
            + " mismatches: "
            + "; ".join(problems)
        )

    # Zero engines against zero rows is a **satisfied** assertion, not an absent
    # one: every registry source was read and nothing disagreed. Phase 0 registers
    # no engines by design, so reporting PENDING here would make Phase 0
    # structurally impossible to close - a phase is green only when nothing is
    # PENDING. The lead ruled this a vacuous PASS on 2026-09-08.
    #
    # The engine count in the message is not decoration; it is the guard against a
    # vacuous pass being read as a real one. A reader sees exactly how much
    # assurance this criterion is offering, and a `0` in a phase where engines were
    # supposed to be registered is itself the bug worth seeing.
    gates = sum(1 for e in engines if bool(getattr(e, "is_gate", False)))
    tail = "" if not engines else " (" + str(gates) + " gates, matched against the registry table)"
    return passed(str(len(engines)) + " engines registered; 0 mismatches" + tail)


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #

# Registered for every phase 0..8: every audit of these documents has found a
# decision that reached three files and not the fourth. See spec 02.
register_every_phase(Criterion("docs_vocabulary", check_docs_vocabulary))

# Phase 0 only. Later phases add their own criteria.
register(0, Criterion("orchestrator_empty_registry", check_orchestrator_empty_registry))
register(0, Criterion("db_migrates_from_empty", check_db_migrates_from_empty))
register(0, Criterion("seed_fixtures_present", check_seed_fixtures_present))
register(0, Criterion("record_sample_valid", check_record_sample_valid))
register(0, Criterion("toolchain_green", check_toolchain_green))
register(0, Criterion("is_gate_matches_registry", check_is_gate_matches_registry))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def format_report(
    phase: int,
    root: Path,
    results: Sequence[tuple[Criterion, Outcome]],
    skipped: Sequence[Criterion],
) -> str:
    lines = ["ACSOE verify - phase " + str(phase), "repo: " + str(root), ""]
    if results:
        width = max(len(c.name) for c, _ in results)
        for criterion, outcome in results:
            lines.append(
                outcome.result.value.ljust(8)
                + criterion.name.ljust(width)
                + "  "
                + outcome.message
            )
    else:
        lines.append("(no criteria registered for this phase)")

    counts = dict.fromkeys(Result, 0)
    for _, outcome in results:
        counts[outcome.result] += 1
    lines.append("")
    lines.append(
        str(len(results))
        + " criteria: "
        + str(counts[Result.PASS])
        + " PASS, "
        + str(counts[Result.FAIL])
        + " FAIL, "
        + str(counts[Result.PENDING])
        + " PENDING"
    )
    if skipped:
        lines.append(
            str(len(skipped))
            + " live criteria skipped (--live to include): "
            + ", ".join(c.name for c in skipped)
        )
    if counts[Result.FAIL]:
        lines.append("Phase " + str(phase) + " has FAILs. That is a stop, at any point in a phase.")
    elif counts[Result.PENDING]:
        lines.append(
            "Phase "
            + str(phase)
            + " is not green: "
            + str(counts[Result.PENDING])
            + " PENDING. Mid-phase the bar is no FAIL, so this is expected."
        )
    else:
        lines.append("Phase " + str(phase) + " is green: every criterion PASS, zero PENDING.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify.py", description="Run the executable exit criteria for one build phase."
    )
    parser.add_argument(
        "--phase",
        type=int,
        required=True,
        help="build phase " + str(MIN_PHASE) + " to " + str(MAX_PHASE),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run criteria that need the network or an API key; never required for green",
    )
    args = parser.parse_args(argv)

    if args.phase not in _REGISTRY:
        parser.error("--phase must be between " + str(MIN_PHASE) + " and " + str(MAX_PHASE))

    context = VerifyContext(root=REPO_ROOT, live=bool(args.live))
    to_run, skipped = criteria_for(args.phase, context.live)
    results = [(criterion, run_criterion(criterion, context)) for criterion in to_run]

    print(format_report(args.phase, context.root, results, skipped))
    return 1 if any(o.result is Result.FAIL for _, o in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
