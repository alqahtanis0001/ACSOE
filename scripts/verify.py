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
import asyncio
import contextlib
import gc
import importlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
        try:
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
        finally:
            # The doubles hold an open SQLite connection inside a temporary
            # directory. Unclosed, Windows refuses the removal and the finalizer
            # prints a `PermissionError` above the report on every run.
            doubles.close()

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
# Phase 1 - the console. Spec 16.
# --------------------------------------------------------------------------- #
#
# Eight criteria, all PENDING on the tree they were written against, exactly as
# the seven Phase 0 criteria were. The subjects are specs 17 to 24.
#
# Two rules cut across all eight and are the reason several of them look longer
# than the sentence in the spec:
#
# * **No criterion may read `data/`, `logs/` or `models/`.** They are gitignored,
#   so a criterion that depends on one cannot pass on a fresh clone. Every
#   criterion that needs rows seeds its own temporary database through B's
#   `seed_database` and hands the path to `create_app(config, db_path=...)`.
# * **No criterion may need a browser, a headless engine or a network fetch.**
#   The four static criteria read `static/` and `templates/` off disk; the four
#   dynamic ones drive the application through the ASGI interface the way uvicorn
#   does, with no HTTP client and no socket anywhere in the path.

CONSOLE_PACKAGE = Path("src") / "acsoe" / "console"
CONSOLE_STATIC = CONSOLE_PACKAGE / "static"
CONSOLE_TEMPLATES = CONSOLE_PACKAGE / "templates"
TOKENS_CSS = CONSOLE_STATIC / "tokens.css"

#: What the console has to expose for these criteria to check anything. Named in
#: one place so a PENDING message can say what is missing rather than only that
#: something is.
CONSOLE_CONTRACT = (
    "expected: acsoe.console.app.create_app(config, *, db_path=None, clock=None) "
    "serving GET / (spec 18), GET /api/state, /api/feed, /api/history, /api/research "
    "(specs 19-22), WS /ws (spec 23), POST /api/command/{activate|freeze|close_all} "
    "(spec 24)"
)

#: The page and the four screen payloads. `/api/state` carries both the status
#: band and the open-positions region - they are one screen in `ui-context.md`.
CONSOLE_SCREENS = (
    ("/", "the page shell"),
    ("/api/state", "status band and open positions"),
    ("/api/feed", "cycle feed"),
    ("/api/history", "history"),
    ("/api/research", "research views"),
)

CONSOLE_COMMANDS = ("activate", "freeze", "close_all")

#: `ui-context.md`: the State field when the daemon's `run_id` has changed and the
#: mode is idle. The em dash is part of the string the operator reads, so it is
#: matched literally - but it is never *printed* into a criterion message, because
#: this script's stdout is a Windows console and cp1252 cannot encode it.
RESTART_STATE_TEXT = "Idle — restarted, not trading"

#: The same string as a JSON payload might carry it. Starlette encodes with
#: `ensure_ascii=False`, so the literal form is what actually arrives; the escaped
#: form is accepted too so the criterion does not turn into an assertion about
#: which JSON encoder a later spec happened to pick.
RESTART_STATE_ESCAPED = RESTART_STATE_TEXT.replace("—", "\\u2014")

KEY_POLL_INTERVAL = "console.poll_interval_ms"

WS_ACCEPT_TIMEOUT_S = 10.0


@contextlib.contextmanager
def console_workspace() -> Iterator[Path]:
    """A temporary directory that is removed best-effort.

    Not `TemporaryDirectory`. SQLite on Windows keeps the file handle open until
    the connection is closed, and a console application that holds a reader open
    one moment longer than the criterion does turns cleanup into a
    `PermissionError` - which `run_criterion` would report as a FAIL of the
    console rather than of the temporary directory. The database is a throwaway;
    failing to delete it is not a verdict about anything.

    **It is not silent, though, and that is the correction.** This used to end in
    `shutil.rmtree(..., ignore_errors=True)`, which is the same reasoning taken one
    step too far: not failing the criterion became not saying anything at all. A
    connection the criteria never closed then leaked roughly 450MB per run, without
    a word, until the disk was full. The visible leak in `tests/harness/doubles.py`
    was two orders of magnitude smaller and was fixed first *because* it was
    visible. See `remove_workspace`.
    """
    tmp = Path(tempfile.mkdtemp(prefix="acsoe-verify-console-"))
    try:
        yield tmp
    finally:
        remove_workspace(tmp)


#: Every temporary directory this script makes. One prefix per helper, all under
#: `acsoe-verify-`, so `sweep_stale_workspaces` can recognise its own leftovers and
#: nothing else.
WORKSPACE_PREFIX = "acsoe-verify-"


def directory_bytes(path: Path) -> int:
    """Total size on disk, best effort. Never raises - it is only ever a number in a
    warning, and a warning that raises is worse than a missing figure."""
    total = 0
    with contextlib.suppress(OSError):
        for entry in path.rglob("*"):
            with contextlib.suppress(OSError):
                if entry.is_file():
                    total += entry.stat().st_size
    return total


def remove_workspace(tmp: Path) -> bool:
    """Delete a criterion's workspace, and **say so on stderr if it survives**.

    Two attempts with a `gc.collect()` between them: a connection dropped without
    being closed is released when its object is collected, and a criterion that
    returned early through one of two dozen `return pending(...)` paths may well
    have left one. Whatever survives that is a real leak, and it is reported rather
    than swallowed - with its size, because the one time this mattered the evidence
    for what had actually consumed the disk was deleted along with the leak.

    stderr, not the criterion's message. A workspace that will not delete is not a
    verdict about the console - it must not turn a PASS into a FAIL - but it is
    something a person has to be told, and printing above the report is exactly how
    the smaller, visible sibling of this bug was found in the first place.
    """
    shutil.rmtree(tmp, ignore_errors=True)
    if not tmp.exists():
        return True
    gc.collect()
    shutil.rmtree(tmp, ignore_errors=True)
    if not tmp.exists():
        return True
    size_mb = directory_bytes(tmp) / (1024 * 1024)
    print(
        f"warning: verify could not delete its workspace {tmp} ({size_mb:.1f} MB) - "
        "something is still holding a file open. This is a leak, not a verdict about "
        "any criterion.",
        file=sys.stderr,
    )
    return False


def sweep_stale_workspaces(*, report: bool = True) -> tuple[int, int]:
    """Remove `acsoe-verify-*` leftovers from earlier runs. Returns (removed, bytes).

    This process is the only one that knows those directories are safe to delete,
    and a run that finds fifty of its own leftovers should not leave them there.
    Best effort throughout: a directory another verify run is using right now simply
    will not delete, and that is fine - it is swept by whichever run goes last.

    Deliberately scoped to the exact prefix this script mints. It never touches
    `pytest-of-*`, which belongs to pytest, or anything else in the temp directory.
    """
    root = Path(tempfile.gettempdir())
    removed = 0
    freed = 0
    with contextlib.suppress(OSError):
        for entry in sorted(root.glob(WORKSPACE_PREFIX + "*")):
            if not entry.is_dir():
                continue
            size = directory_bytes(entry)
            shutil.rmtree(entry, ignore_errors=True)
            if not entry.exists():
                removed += 1
                freed += size
    if report and removed:
        print(
            f"swept {removed} stale verify workspace(s), {freed / (1024 * 1024):.1f} MB",
            file=sys.stderr,
        )
    return removed, freed


def seeded_console_db(directory: Path) -> tuple[Path | None, Outcome | None]:
    """Seed a throwaway database. Must be called inside `root_import_path`."""
    seed_mod, problem = try_import("acsoe.clients.store.seed")
    if seed_mod is None:
        return None, problem or pending("acsoe.clients.store.seed does not exist yet")
    seed_fn, missing = module_attr(seed_mod, "seed_database")
    if seed_fn is None:
        return None, pending(missing)
    db_path = directory / "acsoe.sqlite"
    seed_fn(db_path)
    if not db_path.is_file():
        return None, failed("seed_database created no database file")
    return db_path, None


def console_config(mode: str | None = None) -> tuple[Any, Outcome | None]:
    """A `Config` for the console, optionally with `mode` overridden.

    Built from the shared test double rather than from `platform/config.py` on
    purpose. `platform/config.py` refuses `mode: live` until Phase 8 and that
    refusal is not to be weakened to make a criterion convenient, so
    `console_live_frame_amber` fabricates its live config here instead of editing
    `config/default.yaml`.
    """
    module, problem = try_import("tests.harness.doubles")
    if module is None:
        return None, problem
    loader, missing = module_attr(module, "load_default_config")
    if loader is None:
        return None, pending("test doubles unavailable: " + missing)
    config = loader()
    if mode is None:
        return config, None
    cls, missing = module_attr(module, "MappingConfig")
    if cls is None:
        return None, pending("test doubles unavailable: " + missing)
    data = dict(config.as_dict())
    data["mode"] = mode
    return cls(data), None


def console_app(
    config: Any, db_path: Path
) -> tuple[Any, Outcome | None]:
    """Build the console over a seeded database. Inside `root_import_path`.

    The `db_path` keyword is what makes every criterion here able to run on a
    fresh clone: without it the console would open `data/db/acsoe.sqlite`, which
    is gitignored and may not exist.
    """
    module, problem = try_import("acsoe.console.app")
    if module is None:
        return None, problem or pending("acsoe.console.app does not exist yet")
    factory, missing = module_attr(module, "create_app")
    if factory is None:
        return None, pending(missing + " (" + CONSOLE_CONTRACT + ")")
    try:
        parameters = inspect.signature(factory).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "db_path" not in parameters:
        return None, pending(
            "acsoe.console.app.create_app does not accept `db_path` yet (" + CONSOLE_CONTRACT + ")"
        )
    return factory(config, db_path=db_path), None


#: Every attribute on `app.state` that owns a SQLite connection.
#:
#: **Both of them.** The console has two by design: spec 17's read-only reader and
#: spec 24's narrow read-write writer for the `commands` table alone. The
#: application closes both in its lifespan shutdown - and these criteria drive the
#: ASGI callable directly, the way they must to avoid an HTTP client, so no
#: lifespan ever runs. Closing only the reader left the writer holding
#: `acsoe.sqlite` open, `shutil.rmtree(ignore_errors=True)` then failed silently,
#: and roughly 450MB of seeded database survived every console criterion on every
#: run. Two hundred and fifty of those filled a 923GB disk.
CONSOLE_CONNECTION_ATTRS = ("reader", "command_writer")


def close_console(app: Any) -> None:
    """Release everything the application is holding the database open with."""
    state = getattr(app, "state", None)
    for attr in CONSOLE_CONNECTION_ATTRS:
        holder = getattr(state, attr, None)
        closer = getattr(holder, "close", None)
        if callable(closer):
            with contextlib.suppress(Exception):
                closer()


# --- driving an ASGI application without an HTTP client -------------------- #


@dataclass(frozen=True)
class AsgiResponse:
    status: int
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _http_scope(method: str, path: str) -> dict[str, Any]:
    headers = [(b"host", b"console.verify")]
    if method != "GET":
        headers.append((b"content-length", b"0"))
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("verify", 0),
        "server": ("console.verify", 80),
    }


async def _call_asgi(app: Any, method: str, path: str) -> AsgiResponse:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(_http_scope(method, path), receive, send)
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), 0)
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return AsgiResponse(int(status), body)


def asgi_request(app: Any, method: str, path: str) -> AsgiResponse:
    """One request, driven the way uvicorn drives it.

    Deliberately not `fastapi.testclient.TestClient`: it subclasses `httpx.Client`,
    and the repository's network guard patches `httpx.Client.send` for every test -
    so a criterion exercised under pytest would raise before reaching the
    in-process transport. Calling the application directly also exercises the real
    routing, endpoint and encoder with no socket anywhere in the path.
    """
    return asyncio.run(_call_asgi(app, method, path))


@dataclass(frozen=True)
class WsProbe:
    """What a WebSocket probe saw. `accepted` False means there is no endpoint."""

    accepted: bool
    pushed: bool
    elapsed_ms: float
    detail: str


async def _probe_websocket(
    app: Any, path: str, *, on_open: Callable[[], None], budget_s: float
) -> WsProbe:
    inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def receive() -> dict[str, Any]:
        return await inbound.get()

    async def send(message: dict[str, Any]) -> None:
        await outbound.put(message)

    scope: dict[str, Any] = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"console.verify")],
        "client": ("verify", 0),
        "server": ("console.verify", 80),
        "subprotocols": [],
    }

    await inbound.put({"type": "websocket.connect"})
    task = asyncio.ensure_future(app(scope, receive, send))
    try:
        try:
            first = await asyncio.wait_for(outbound.get(), timeout=WS_ACCEPT_TIMEOUT_S)
        except asyncio.TimeoutError:
            return WsProbe(False, False, 0.0, "the application never answered the handshake")
        if first.get("type") != "websocket.accept":
            return WsProbe(False, False, 0.0, "handshake answered with " + str(first.get("type")))

        on_open()
        started = time.monotonic()
        while True:
            remaining = budget_s - (time.monotonic() - started)
            if remaining <= 0:
                return WsProbe(True, False, budget_s * 1000, "no push inside the budget")
            try:
                message = await asyncio.wait_for(outbound.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return WsProbe(True, False, budget_s * 1000, "no push inside the budget")
            elapsed_ms = (time.monotonic() - started) * 1000
            if message.get("type") == "websocket.send":
                return WsProbe(True, True, elapsed_ms, "pushed")
            if message.get("type") == "websocket.close":
                return WsProbe(True, False, elapsed_ms, "the endpoint closed the socket")
    finally:
        await inbound.put({"type": "websocket.disconnect", "code": 1000})
        task.cancel()
        # `CancelledError` is a BaseException, so `suppress(Exception)` does not
        # catch it and the cancellation the probe itself asked for would surface
        # as a criterion that raised. An endpoint that never returns is the normal
        # case here - a push loop is supposed to run until the socket closes.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


def probe_websocket(app: Any, path: str, *, on_open: Callable[[], None], budget_s: float) -> WsProbe:
    return asyncio.run(_probe_websocket(app, path, on_open=on_open, budget_s=budget_s))


# --- reading the stylesheet without a browser ------------------------------ #

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


@dataclass(frozen=True)
class CssRule:
    at_context: str  # the enclosing at-rule preludes, joined; "" at top level
    selector: str
    block: str


def css_rules(text: str) -> list[CssRule]:
    """Every declaration block in a stylesheet, with its enclosing at-rules.

    A deliberately small brace scanner rather than a CSS parser. It has to do
    exactly two things these criteria depend on: keep a rule's selector attached
    to its declarations, and keep the `@media (prefers-reduced-motion: reduce)`
    prelude attached to the rules inside it. Anything more would be a dependency
    this project has not declared.
    """
    stripped = _CSS_COMMENT.sub(" ", text)
    rules: list[CssRule] = []

    def scan(chunk: str, context: str) -> None:
        position = 0
        while True:
            opened = chunk.find("{", position)
            if opened == -1:
                return
            prelude = chunk[position:opened].strip()
            depth = 1
            index = opened + 1
            while index < len(chunk) and depth:
                if chunk[index] == "{":
                    depth += 1
                elif chunk[index] == "}":
                    depth -= 1
                index += 1
            body = chunk[opened + 1 : index - 1]
            if prelude.startswith("@"):
                inner = (context + " " + prelude).strip()
                if "{" in body:
                    scan(body, inner)
                else:
                    rules.append(CssRule(context, prelude, body))
            else:
                rules.append(CssRule(context, prelude, body))
            position = index

    scan(stripped, "")
    return rules


def css_declarations(block: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for statement in block.split(";"):
        if ":" not in statement:
            continue
        name, _, value = statement.partition(":")
        pairs.append((name.strip().lower(), value.strip()))
    return pairs


def console_stylesheets(root: Path) -> dict[Path, str]:
    directory = root / CONSOLE_STATIC
    if not directory.is_dir():
        return {}
    return {
        path.relative_to(root): path.read_text(encoding="utf-8")
        for path in sorted(directory.rglob("*.css"))
    }


# --------------------------------------------------------------------------- #
# console_renders_seeded_screens
# --------------------------------------------------------------------------- #


def check_console_renders_seeded_screens(ctx: VerifyContext) -> Outcome:
    """Every screen answers over a seeded database.

    A screen that raises, 500s or returns an empty body is a FAIL. A screen that
    is not routed at all is PENDING - that is specs 19 to 22 not having landed,
    which is orderly progress rather than a defect.
    """
    with root_import_path(ctx.root), console_workspace() as tmp:
        db_path, early = seeded_console_db(tmp)
        if db_path is None:
            return early or pending("no seeded database")
        config, early = console_config()
        if config is None:
            return early or pending("no config to build the console with")
        app, early = console_app(config, db_path)
        if app is None:
            return early or pending("the console application does not exist yet")

        absent: list[str] = []
        problems: list[str] = []
        answered: list[str] = []
        try:
            for path, screen in CONSOLE_SCREENS:
                try:
                    response = asgi_request(app, "GET", path)
                except Exception as exc:  # a raising screen is a FAIL, never a crash
                    problems.append(screen + " (" + path + ") raised " + type(exc).__name__)
                    continue
                if response.status == 404:
                    absent.append(screen + " (" + path + ")")
                elif response.status != 200:
                    problems.append(screen + " (" + path + ") answered " + str(response.status))
                elif not response.body.strip():
                    problems.append(screen + " (" + path + ") returned an empty body")
                else:
                    answered.append(screen)
        finally:
            close_console(app)

    if problems:
        return failed("; ".join(problems))
    if absent:
        return pending("not routed yet: " + "; ".join(absent))
    return passed("all " + str(len(answered)) + " screens answered over a seeded database")


# --------------------------------------------------------------------------- #
# console_websocket_pushes_on_change
# --------------------------------------------------------------------------- #


def check_console_websocket_pushes_on_change(ctx: VerifyContext) -> Outcome:
    """A push arrives within twice `console.poll_interval_ms` of a database change.

    The budget is read from config, never hardcoded: `ui-context.md` makes the
    poll interval configuration and a criterion carrying its own copy of 500 would
    stop testing the console the moment the operator retuned it.
    """
    config_data, problem = load_config(ctx.root)
    if config_data is None:
        return problem or pending("config/default.yaml does not exist yet")
    poll_ms = config_get(config_data, KEY_POLL_INTERVAL)
    if poll_ms is _CONFIG_MISSING:
        return pending("config key `" + KEY_POLL_INTERVAL + "` is not defined yet")
    if poll_ms is None:
        return pending("the operator has not set `" + KEY_POLL_INTERVAL + "`")
    budget_ms = int(poll_ms) * 2

    with root_import_path(ctx.root), console_workspace() as tmp:
        db_path, early = seeded_console_db(tmp)
        if db_path is None:
            return early or pending("no seeded database")
        config, early = console_config()
        if config is None:
            return early or pending("no config to build the console with")
        app, early = console_app(config, db_path)
        if app is None:
            return early or pending("the console application does not exist yet")

        def move_the_watermark() -> None:
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute("SELECT MAX(updated_at) FROM runs").fetchone()
                conn.execute(
                    "UPDATE runs SET updated_at = ? WHERE run_id = "
                    "(SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1)",
                    (int(row[0] or 0) + 1_000_000,),
                )
                conn.commit()
            finally:
                conn.close()

        try:
            probe = probe_websocket(
                app, "/ws", on_open=move_the_watermark, budget_s=budget_ms / 1000
            )
        finally:
            close_console(app)

    if not probe.accepted:
        return pending(
            "no WebSocket endpoint at /ws yet - " + probe.detail + " (" + CONSOLE_CONTRACT + ")"
        )
    if not probe.pushed:
        return failed(
            "the watermark moved and nothing was pushed within "
            + str(budget_ms)
            + "ms (2 x "
            + KEY_POLL_INTERVAL
            + "="
            + str(poll_ms)
            + "): "
            + probe.detail
        )
    return passed(
        "pushed "
        + format(probe.elapsed_ms, ".0f")
        + "ms after the watermark moved, inside the "
        + str(budget_ms)
        + "ms budget"
    )


# --------------------------------------------------------------------------- #
# console_commands_write_rows
# --------------------------------------------------------------------------- #


def _command_rows(db_path: Path) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(db_path)
    try:
        return list(
            conn.execute(
                "SELECT id, command, source, claimed_at, consumed_at FROM commands ORDER BY id"
            ).fetchall()
        )
    finally:
        conn.close()


def check_console_commands_write_rows(ctx: VerifyContext) -> Outcome:
    """Activate, Freeze and Close-all each write exactly one correct row.

    `source = 'console'`, and both `claimed_at` and `consumed_at` null: the
    console announces an intention, and the daemon's reader is the only thing that
    may mark one claimed or consumed. A console that stamped either would let a
    command be swallowed without ever being applied.
    """
    with root_import_path(ctx.root), console_workspace() as tmp:
        db_path, early = seeded_console_db(tmp)
        if db_path is None:
            return early or pending("no seeded database")
        config, early = console_config()
        if config is None:
            return early or pending("no config to build the console with")
        app, early = console_app(config, db_path)
        if app is None:
            return early or pending("the console application does not exist yet")

        problems: list[str] = []
        written: list[str] = []
        try:
            for name in CONSOLE_COMMANDS:
                before = _command_rows(db_path)
                response = asgi_request(app, "POST", "/api/command/" + name)
                if response.status == 404:
                    return pending(
                        "no command endpoint yet: POST /api/command/"
                        + name
                        + " ("
                        + CONSOLE_CONTRACT
                        + ")"
                    )
                after = _command_rows(db_path)
                seen = {row[0] for row in before}
                added = [row for row in after if row[0] not in seen]
                if response.status not in (200, 201, 202):
                    problems.append(name + " answered " + str(response.status))
                if len(added) != 1:
                    problems.append(name + " wrote " + str(len(added)) + " rows, expected 1")
                    continue
                _, command, source, claimed_at, consumed_at = added[0]
                if command != name:
                    problems.append(name + " wrote command=" + repr(command))
                if source != "console":
                    problems.append(name + " wrote source=" + repr(source))
                if claimed_at is not None or consumed_at is not None:
                    problems.append(
                        name
                        + " wrote claimed_at="
                        + repr(claimed_at)
                        + " consumed_at="
                        + repr(consumed_at)
                        + ", both must be null"
                    )
                written.append(name)
        finally:
            close_console(app)

    if problems:
        return failed("; ".join(problems))
    return passed("one correct unclaimed row each for " + ", ".join(written))


# --------------------------------------------------------------------------- #
# console_live_frame_amber
# --------------------------------------------------------------------------- #

_FRAME_SELECTORS = ("html", "body", ":root", ".frame", ".viewport", "[data-mode")
_BORDER_PROPERTIES = ("border", "border-width", "border-style", "border-color")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_VAR_REFERENCE = re.compile(r"var\(\s*(--[\w-]+)\s*\)")


def css_root_tokens(text: str) -> dict[str, str]:
    """The custom properties declared on `:root`, so a `var()` can be resolved.

    Without this the criterion would be asserting that `console.css` contains the
    literal `3px` - which would force a raw measurement out of `tokens.css` and
    into a component, for exactly the reason `ui-context.md` says a raw hex must
    not go there. A token is the right way to write the frame width; the check
    has to be able to read one.
    """
    tokens: dict[str, str] = {}
    for rule in css_rules(text):
        if rule.selector.strip().split(",")[0].strip().lower() != ":root":
            continue
        for name, value in css_declarations(rule.block):
            if name.startswith("--"):
                tokens[name] = value
    return tokens


def resolve_css_vars(value: str, tokens: dict[str, str], *, depth: int = 4) -> str:
    """Substitute `var(--x)` from `tokens`, a few levels deep. Unknown names stay."""
    for _ in range(depth):
        replaced = _VAR_REFERENCE.sub(lambda m: tokens.get(m.group(1), m.group(0)), value)
        if replaced == value:
            break
        value = replaced
    return value


def _frame_border_rules(rules: Sequence[CssRule]) -> list[CssRule]:
    """Rules that put a border on the page frame itself."""
    found: list[CssRule] = []
    for rule in rules:
        selector = rule.selector.lower()
        if not any(token in selector for token in _FRAME_SELECTORS):
            continue
        for name, value in css_declarations(rule.block):
            if name in _BORDER_PROPERTIES and value.lower() not in ("none", "0", "0px"):
                found.append(rule)
                break
    return found


def check_console_live_frame_amber(ctx: VerifyContext) -> Outcome:
    """The one bold move: a 3px `--live` frame in live, and no border in paper.

    Checked from both ends. The served markup has to say which mode it is in, and
    the stylesheet has to be the *only* place a frame border is declared and has
    to declare it under the live selector alone - because a border applied
    unconditionally, or a second border rule somewhere else, would put amber on a
    paper screen and `ui-context.md` reserves amber for real money at risk.
    """
    stylesheets = console_stylesheets(ctx.root)
    if not stylesheets:
        return pending(CONSOLE_STATIC.as_posix() + " holds no stylesheet yet")

    with root_import_path(ctx.root), console_workspace() as tmp:
        db_path, early = seeded_console_db(tmp)
        if db_path is None:
            return early or pending("no seeded database")
        rendered: dict[str, str] = {}
        for mode in ("live", "paper"):
            config, early = console_config(mode)
            if config is None:
                return early or pending("no config to build the console with")
            app, early = console_app(config, db_path)
            if app is None:
                return early or pending("the console application does not exist yet")
            try:
                response = asgi_request(app, "GET", "/")
            finally:
                close_console(app)
            if response.status == 404:
                return pending("the page is not served yet (GET / is a 404)")
            if response.status != 200:
                return failed("GET / in " + mode + " mode answered " + str(response.status))
            rendered[mode] = response.text

    # An HTML comment naming the live selector is documentation, not a live page.
    # The assertion is about the attribute the browser sees.
    markup = {mode: _HTML_COMMENT.sub(" ", text) for mode, text in rendered.items()}

    problems: list[str] = []
    if 'data-mode="live"' not in markup["live"]:
        problems.append('the live page does not carry data-mode="live"')
    if 'data-mode="paper"' not in markup["paper"]:
        problems.append('the paper page does not carry data-mode="paper"')
    if 'data-mode="live"' in markup["paper"]:
        problems.append("the paper page claims live mode")

    all_rules = [rule for text in stylesheets.values() for rule in css_rules(text)]
    tokens: dict[str, str] = {}
    for text in stylesheets.values():
        tokens.update(css_root_tokens(text))
    live_colour = tokens.get("--live")

    border_rules = _frame_border_rules(all_rules)
    if not border_rules:
        return pending("no frame border is declared in the stylesheet yet")
    stray = [r for r in border_rules if 'data-mode="live"' not in r.selector.replace("'", '"')]
    if stray:
        problems.append(
            "a frame border is declared outside the live selector: "
            + "; ".join(r.selector for r in stray[:3])
        )
    live_rules = [r for r in border_rules if r not in stray]
    if not any(
        "3px" in resolve_css_vars(value, tokens)
        and (
            "--live" in value
            or (live_colour is not None and live_colour in resolve_css_vars(value, tokens))
        )
        for rule in live_rules
        for _, value in css_declarations(rule.block)
    ):
        problems.append("the live frame is not a 3px border in var(--live)")

    if problems:
        return failed("; ".join(problems))
    return passed(
        "live renders a 3px var(--live) frame and paper declares no border anywhere"
    )


# --------------------------------------------------------------------------- #
# console_tokens_no_raw_hex
# --------------------------------------------------------------------------- #

#: A CSS colour literal. The trailing guard stops `#E4E9ED` matching inside a
#: longer word, and the leading guard is what keeps `href="#feed"` out of the
#: results: `feed` is four hex digits, so a bare pattern flags every fragment
#: link whose id happens to be spelled in a-f. A colour in CSS is never preceded
#: by a quote; a fragment reference always is.
_HEX_LITERAL = re.compile(r"(?<![\"'])#([0-9A-Fa-f]{3,8})(?![0-9A-Za-z_-])")

_ROOT_BLOCK_SELECTORS = (":root", "html", ":root,html")

CONSOLE_SCANNED_SUFFIXES = (".css", ".html", ".js", ".py")


def _blank_css_comments(text: str) -> str:
    """Replace every CSS comment with spaces, keeping the string the same length.

    Length-preserving on purpose: the caller compares *character offsets* against
    the spans this produces, so deleting the comments would shift every offset
    after the first one and the token block would be found in the wrong place.
    Newlines are kept so line numbers in a failure message still point at the
    right line.
    """
    def blank(match: re.Match[str]) -> str:
        return "".join(c if c == "\n" else " " for c in match.group(0))

    return _CSS_COMMENT.sub(blank, text)


def _token_block_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of the `:root` declaration blocks in `tokens.css`.

    Comments are blanked first. The file opens with a long comment explaining why
    this block is the one exception, and without blanking, the selector that
    `finditer` sees for the first rule is that entire comment followed by
    `:root` - which matches nothing, and every token in the file is then reported
    as a raw hex outside the block.
    """
    text = _blank_css_comments(text)
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"([^{}]*)\{", text):
        selector = match.group(1).strip().replace(" ", "").lower()
        if selector.split(",")[0] not in _ROOT_BLOCK_SELECTORS:
            continue
        depth = 1
        index = match.end()
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        spans.append((match.end(), index))
    return spans


def check_console_tokens_no_raw_hex(ctx: VerifyContext) -> Outcome:
    """Tokens only, declared once. `tokens.css`'s `:root` block is the one exception.

    `ui-context.md`: "Never use a raw hex in a component. Tokens only, declared
    once on `:root`." A hex that reaches a component is a colour nobody can
    retune, and it is how a reserved colour leaks out of its reservation.
    """
    directory = ctx.root / CONSOLE_PACKAGE
    if not directory.is_dir():
        return pending(CONSOLE_PACKAGE.as_posix() + " does not exist yet")
    files = [
        path
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.suffix.lower() in CONSOLE_SCANNED_SUFFIXES
    ]
    if not files:
        return pending(CONSOLE_PACKAGE.as_posix() + " holds nothing to scan yet")

    tokens_path = ctx.root / TOKENS_CSS
    hits: list[str] = []
    tokens_declared = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        allowed = _token_block_spans(text) if path == tokens_path else []
        for match in _HEX_LITERAL.finditer(text):
            if any(start <= match.start() < end for start, end in allowed):
                tokens_declared += 1
                continue
            line = text.count("\n", 0, match.start()) + 1
            hits.append(path.relative_to(ctx.root).as_posix() + ":" + str(line) + ": " + match.group(0))

    if hits:
        shown = "; ".join(hits[:8])
        more = " (+" + str(len(hits) - 8) + " more)" if len(hits) > 8 else ""
        return failed(str(len(hits)) + " raw hex literal(s) outside the token block: " + shown + more)
    if not tokens_path.is_file():
        return pending(TOKENS_CSS.as_posix() + " does not exist yet")
    if tokens_declared == 0:
        return pending(TOKENS_CSS.as_posix() + " declares no token yet")
    return passed(
        str(tokens_declared)
        + " hex values, all inside the "
        + TOKENS_CSS.as_posix()
        + " token block; "
        + str(len(files))
        + " console files scanned"
    )


# --------------------------------------------------------------------------- #
# console_tabular_figures
# --------------------------------------------------------------------------- #

_CELL = re.compile(r"<(t[dh])\b([^>]*)>(.*?)</\1>", re.S | re.I)
_CLASS_ATTR = re.compile(r"class\s*=\s*[\"']([^\"']*)[\"']", re.I)
_TAGS = re.compile(r"<[^>]+>")
#: A cell whose text is a figure: digits, with an optional sign, separators, a
#: percent or a currency letter group. The proper minus sign is U+2212, which is
#: what `ui-context.md` requires in numeric output.
_NUMERIC_TEXT = re.compile("^[+−-]?[0-9][0-9\\s.,:]*%?$")


def check_console_tabular_figures(ctx: VerifyContext) -> Outcome:
    """`font-variant-numeric: tabular-nums` on every numeric element, one mechanism.

    Three assertions, none of which needs a browser:

    1. The stylesheet resolves a tabular-figure class - `.num` - to
       `font-variant-numeric: tabular-nums`.
    2. That class is the **only** place `tabular-nums` is declared. Two mechanisms
       is how one column quietly stops being tabular.
    3. Every table cell in the served markup whose text is a figure carries it.

    The residual limit is stated rather than hidden: cells built client-side are
    covered by the convention that a cell copies its column header's classes, and
    the header is server-rendered and checked here.
    """
    stylesheets = console_stylesheets(ctx.root)
    if not stylesheets:
        return pending(CONSOLE_STATIC.as_posix() + " holds no stylesheet yet")

    rules = [(rel, rule) for rel, text in stylesheets.items() for rule in css_rules(text)]
    tabular = [
        (rel, rule)
        for rel, rule in rules
        for name, value in css_declarations(rule.block)
        if name == "font-variant-numeric" and "tabular-nums" in value.lower()
    ]
    if not tabular:
        return pending("no `font-variant-numeric: tabular-nums` rule exists yet")
    selectors = {rule.selector.strip() for _, rule in tabular}
    if selectors != {".num"}:
        return failed(
            "tabular figures are declared on " + ", ".join(sorted(selectors)) + ", not on `.num` alone"
        )

    with root_import_path(ctx.root), console_workspace() as tmp:
        db_path, early = seeded_console_db(tmp)
        if db_path is None:
            return early or pending("no seeded database")
        config, early = console_config()
        if config is None:
            return early or pending("no config to build the console with")
        app, early = console_app(config, db_path)
        if app is None:
            return early or pending("the console application does not exist yet")
        try:
            response = asgi_request(app, "GET", "/")
        finally:
            close_console(app)

    if response.status == 404:
        return pending("the page is not served yet (GET / is a 404)")
    if response.status != 200:
        return failed("GET / answered " + str(response.status))

    markup = response.text
    marked = 0
    unmarked: list[str] = []
    for match in _CELL.finditer(markup):
        classes = set()
        attr = _CLASS_ATTR.search(match.group(2))
        if attr:
            classes = set(attr.group(1).split())
        if "num" in classes:
            marked += 1
            continue
        text = _TAGS.sub("", match.group(3)).strip()
        if text and _NUMERIC_TEXT.match(text):
            unmarked.append(text[:24])

    if unmarked:
        return failed(
            str(len(unmarked)) + " numeric cell(s) without the `num` class: " + ", ".join(unmarked[:6])
        )
    if marked == 0:
        return pending("no column carries the `num` class yet")
    return passed(
        str(marked)
        + " numeric cell(s) carry `.num`, and `.num` is the only tabular-figure rule"
    )


# --------------------------------------------------------------------------- #
# console_focus_and_reduced_motion
# --------------------------------------------------------------------------- #

_SUPPRESSED = ("none", "0", "0px", "hidden")


def check_console_focus_and_reduced_motion(ctx: VerifyContext) -> Outcome:
    """The quality floor: a visible focus ring, and reduced motion honoured.

    Both are asserted as *presence and non-suppression*. A `:focus-visible` rule
    that sets `outline: none` and nothing else is worse than no rule at all,
    because it looks like the requirement was met.
    """
    stylesheets = console_stylesheets(ctx.root)
    if not stylesheets:
        return pending(CONSOLE_STATIC.as_posix() + " holds no stylesheet yet")

    rules = [rule for text in stylesheets.values() for rule in css_rules(text)]

    focus_rules = [r for r in rules if ":focus-visible" in r.selector.lower()]
    if not focus_rules:
        return pending("no `:focus-visible` rule exists yet")

    visible = False
    suppressed: list[str] = []
    for rule in focus_rules:
        for name, value in css_declarations(rule.block):
            low = value.strip().lower()
            if name in ("outline", "outline-width", "outline-style", "box-shadow"):
                if low in _SUPPRESSED:
                    suppressed.append(rule.selector.strip() + " { " + name + ": " + value + " }")
                else:
                    visible = True
    if suppressed:
        return failed("the focus ring is suppressed: " + "; ".join(suppressed[:3]))
    if not visible:
        return failed(
            "`:focus-visible` exists but declares no visible outline or box-shadow"
        )

    reduced = [r for r in rules if "prefers-reduced-motion" in r.at_context.lower()]
    if not reduced:
        return pending("no `@media (prefers-reduced-motion: reduce)` block exists yet")
    drops_motion = any(
        name in ("animation", "animation-name", "animation-duration", "transition", "transition-duration")
        and (value.strip().lower() in ("none", "0s", "0ms") or "0.01ms" in value.lower())
        for rule in reduced
        for name, value in css_declarations(rule.block)
    )
    if not drops_motion:
        return failed(
            "the reduced-motion block does not drop the change flash - no animation or "
            "transition is set to none"
        )

    return passed(
        str(len(focus_rules))
        + " visible `:focus-visible` rule(s); the reduced-motion block drops the flash"
    )


# --------------------------------------------------------------------------- #
# console_restart_banner
# --------------------------------------------------------------------------- #


def _keep_only_latest_run(db_path: Path) -> int:
    """Leave one `runs` row, so the current run has no predecessor.

    `runs.run_id` is `NOT NULL UNIQUE` in `db/migrations/0001_initial.sql`, so two
    rows carrying the *same* `run_id` is a state the schema forbids and no
    criterion can fabricate. The equivalent branch - and the one an operator
    actually meets - is the first ever start, where there is no previous row to
    differ from. That is what this builds.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "DELETE FROM runs WHERE run_id <> "
            "(SELECT run_id FROM runs ORDER BY started_at DESC, id DESC LIMIT 1)"
        )
        conn.commit()
        return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
    finally:
        conn.close()


def _count_runs(db_path: Path) -> int:
    """How many `runs` rows the database holds, on a connection that gets closed.

    Written out rather than chained as `sqlite3.connect(...).execute(...)`, which is
    where this criterion was leaking a handle into its own workspace.
    """
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
    finally:
        conn.close()


def check_console_restart_banner(ctx: VerifyContext) -> Outcome:
    """`Idle - restarted, not trading` when the daemon's `run_id` has changed.

    The comparison is made server-side in SQLite, per `ui-context.md`: the console
    is a separate process with no memory across its own restarts, so it may never
    be derived from anything the browser or the app remembers.
    """
    with root_import_path(ctx.root), console_workspace() as tmp:
        config, early = console_config()
        if config is None:
            return early or pending("no config to build the console with")

        bodies: dict[str, str] = {}
        for label in ("restarted", "first-start"):
            directory = tmp / label
            directory.mkdir(parents=True, exist_ok=True)
            db_path, early = seeded_console_db(directory)
            if db_path is None:
                return early or pending("no seeded database")
            if label == "first-start":
                remaining = _keep_only_latest_run(db_path)
                if remaining != 1:
                    return failed("could not reduce the seed to a single run row")
            else:
                runs = _count_runs(db_path)
                if int(runs) < 2:
                    return failed("the seed carries " + str(runs) + " run rows, expected at least 2")

            app, early = console_app(config, db_path)
            if app is None:
                return early or pending("the console application does not exist yet")
            try:
                response = asgi_request(app, "GET", "/api/state")
            finally:
                close_console(app)
            if response.status == 404:
                return pending("the status band is not routed yet (GET /api/state is a 404)")
            if response.status != 200:
                return failed("GET /api/state answered " + str(response.status))
            bodies[label] = response.text

    def says_restarted(body: str) -> bool:
        return RESTART_STATE_TEXT in body or RESTART_STATE_ESCAPED in body

    problems: list[str] = []
    if not says_restarted(bodies["restarted"]):
        problems.append(
            "two runs with different run_ids and an idle mode did not read the restart banner"
        )
    if says_restarted(bodies["first-start"]):
        problems.append("a first start with no previous run still read the restart banner")
    if "Idle" not in bodies["first-start"]:
        problems.append("a first start does not read plain `Idle`")

    if problems:
        return failed("; ".join(problems))
    return passed(
        "a changed run_id reads the restart banner; a first start reads plain `Idle`"
    )


# --------------------------------------------------------------------------- #
# commands_round_trip - Phase 2, written by the lead
# --------------------------------------------------------------------------- #
#
# The criterion that would have caught the Phase 1 defect.
#
# `Orchestrator._consume_commands` looked up `store.claim_pending_commands`, which
# `StoreClient` has never had. The `getattr` returned None, the reader logged one debug
# line and returned, and a daemon wired to the real store ignored every Activate, Freeze
# and Close-all ever written - the kill switch was inert. Phase 0 reported green anyway,
# because the only implementations of that shape were a test double in
# `tests/core/test_orchestrator.py` and an adapter in `tests/console/test_commands.py`.
#
# **A seam exercised only through a double is not tested; the double is.** So this
# criterion refuses every double: it migrates a real database, writes real rows through
# the real `StoreClient`, and hands that same client to the real `Orchestrator`. The only
# fabricated objects are a config and a clock, neither of which is part of the seam.


class _RoundTripConfig:
    """The `Config` Protocol, and nothing more. Not part of the seam under test."""

    @property
    def mode(self) -> str:
        return "paper"

    def get(self, dotted_key: str, /) -> Any:
        raise KeyError(dotted_key)


class _RoundTripClock:
    """Monotonic, injected. `now()` advances so `claimed_at` and `consumed_at` differ.

    `start` is a parameter because a criterion that drives a daemon over a *seeded*
    database has to run it after the seed - see `_moment_after_newest_run`.
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._t = start if start is not None else datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    def now(self) -> datetime:
        self._t += timedelta(seconds=1)
        return self._t


class _RoundTripClients:
    def __init__(self, store: Any) -> None:
        self._store = store

    @property
    def kraken(self) -> Any:
        return object()

    @property
    def store(self) -> Any:
        return self._store

    @property
    def recorder(self) -> Any:
        return object()


class _DoneEngine:
    """A manage-chain stand-in reporting one completion flag.

    Engines 21 and 22 are Phase 6. `close_all` cannot reach phase two of its
    consumption without something reporting done, so this reports it - and it is
    deliberately the *only* stand-in here. It stands in for an engine that does not
    exist yet, never for the store or the reader, which both exist and are the seam.
    """

    is_gate = False

    def __init__(self, name: str, number: int, field: str) -> None:
        self.name = name
        self.number = number
        self._field = field

    def process(self, context: Any, state: Any) -> Any:
        from acsoe.core.contracts import EngineResult, EngineStatus

        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            reason=None,
            data={self._field: True},
            duration_ms=0.1,
        )


def _append_command(store: Any, contracts: ModuleType, name: str, stamp: int) -> int:
    row = contracts.CommandRow(
        command=name,
        source=contracts.CommandSource.CONSOLE,
        created_at=stamp,
        updated_at=stamp,
    )
    return int(store.append_command(row))


def _command_row(db_path: Path, command_id: int) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
    finally:
        conn.close()
    return row


def check_commands_round_trip(ctx: VerifyContext) -> Outcome:
    with (
        root_import_path(ctx.root),
        tempfile.TemporaryDirectory(prefix="acsoe-verify-cmds-") as tmp,
    ):
        db_path = Path(tmp) / "acsoe.sqlite"
        _, early = _apply_migrations(ctx, db_path)
        if early is not None:
            return early

        client_mod, problem = try_import("acsoe.clients.store.client")
        if client_mod is None:
            return problem or pending("acsoe.clients.store.client does not exist yet")
        contracts_mod, problem = try_import("acsoe.clients.store.contracts")
        if contracts_mod is None:
            return problem or pending("acsoe.clients.store.contracts does not exist yet")
        orch_mod, problem = try_import("acsoe.core.orchestrator")
        if orch_mod is None:
            return problem or pending("acsoe.core.orchestrator does not exist yet")
        core_mod, problem = try_import("acsoe.core.contracts")
        if core_mod is None:
            return problem or pending("acsoe.core.contracts does not exist yet")

        store_cls, missing = module_attr(client_mod, "StoreClient")
        if store_cls is None:
            return pending(missing)
        orch_cls, missing = module_attr(orch_mod, "Orchestrator")
        if orch_cls is None:
            return pending(missing)
        chains_cls, missing = module_attr(core_mod, "Chains")
        if chains_cls is None:
            return pending(missing)

        clock = _RoundTripClock()
        stamp = 1_788_000_000_000_000

        # -- activate and freeze: applied and consumed on the claiming tick ----
        for name, expected_mode in (("activate", "running"), ("freeze", "frozen")):
            with store_cls(db_path) as store:
                command_id = _append_command(store, contracts_mod, name, stamp)
                orchestrator = orch_cls(
                    config=_RoundTripConfig(),
                    clock=clock,
                    clients=_RoundTripClients(store),
                    chains=chains_cls(),
                )
                orchestrator.tick()
                mode = orchestrator.system["mode"]
            if mode != expected_mode:
                return failed(
                    f"the real store and the real reader disagree: `{name}` left mode "
                    f"{mode!r}, expected {expected_mode!r}. The reader is not reading "
                    "the store."
                )
            row = _command_row(db_path, command_id)
            if row["claimed_at"] is None:
                return failed(f"`{name}` was applied but its row was never claimed")
            if row["consumed_at"] is None:
                return failed(
                    f"`{name}` is a pure mode change and must be consumed on the same "
                    "tick; consumed_at is still null"
                )
            stamp += 1

        # -- close_all: claimed now, consumed only when both engines report done --
        with store_cls(db_path) as store:
            close_id = _append_command(store, contracts_mod, "close_all", stamp)
            orchestrator = orch_cls(
                config=_RoundTripConfig(),
                clock=clock,
                clients=_RoundTripClients(store),
                chains=chains_cls(),
            )
            orchestrator.tick()
            intent = orchestrator.system["close_intent"]
            mode = orchestrator.system["mode"]
        if not intent or mode != "frozen":
            return failed(
                f"`close_all` left mode={mode!r} close_intent={intent!r}; expected "
                "'frozen' and True"
            )
        row = _command_row(db_path, close_id)
        if row["claimed_at"] is None:
            return failed("`close_all` was applied but its row was never claimed")
        if row["consumed_at"] is not None:
            return failed(
                "`close_all` was consumed on the claiming tick. Two-phase consumption "
                "exists so a daemon killed mid-liquidation re-applies the command "
                "instead of coming back with it marked done and positions still open."
            )

        # -- the interrupted row is re-applied by a *new* orchestrator, then finished --
        with store_cls(db_path) as store:
            restarted = orch_cls(
                config=_RoundTripConfig(),
                clock=clock,
                clients=_RoundTripClients(store),
                chains=chains_cls(
                    manage=(
                        _DoneEngine("position_manager", 21, "entry_orders_cancelled"),
                        _DoneEngine("exit", 22, "positions_closed"),
                    )
                ),
            )
            restarted.tick()
            replayed_intent = restarted.system["close_intent"]
        row = _command_row(db_path, close_id)
        if row["consumed_at"] is None:
            return failed(
                "a restarted daemon did not finish the interrupted `close_all`: the row "
                "is still claimed and unconsumed after both engines reported done. This "
                "is the failure the kill switch exists to prevent."
            )
        if replayed_intent:
            return failed("`close_intent` was not cleared after both engines reported done")

        return passed(
            "real StoreClient through the real reader: activate and freeze applied and "
            "consumed on the claiming tick, close_all claimed but not consumed, and an "
            "interrupted close_all re-applied on restart and consumed only once done"
        )


# --------------------------------------------------------------------------- #
# Phase 2 - the data spine. Spec 33.
# --------------------------------------------------------------------------- #
#
# Six criteria alongside `commands_round_trip`, which the lead registered at the
# phase opening. All six are PENDING on the tree they were written against: engines
# 1 to 4, the recorder digest and the historical loader are A's, and none of them
# exists yet. That is the point. Criteria exist so they can report PENDING, and
# PENDING is what stops an empty phase looking finished.
#
# The same two rules that shaped the Phase 1 criteria shape these:
#
# * **No criterion may read `data/`, `logs/` or `models/`.** They are gitignored, so
#   a criterion depending on one cannot pass on a fresh clone. Everything here reads
#   a committed fixture under `tests/fixtures/` or fabricates its subject into a
#   temporary directory.
# * **No criterion may need the network, a key, or a browser.** The exchange values
#   come from the fake Kraken client over the committed `tests/fixtures/kraken/`
#   envelopes; the console is driven through the ASGI interface.
#
# A third rule is specific to this phase. Several of these criteria judge code that
# does not exist yet, so each one names the surface it expects in its PENDING line -
# the way `CONSOLE_CONTRACT` told specs 19 to 24 what to build. **The contract is a
# proposal to the owning agent, not a decree**; it was messaged to A when these
# criteria were registered, and moving it is a change to this file, not a change to
# the phase.


def _with_contract(problem: Outcome | None, absent: str, contract: str) -> Outcome:
    """A PENDING that always names the surface the criterion is waiting for.

    `try_import` reports "module does not exist yet" and stops there, which is the
    right message for a criterion whose subject is already agreed. It is the wrong
    one here: five of these six criteria judge code nobody has written, and a
    PENDING line that does not say what to build makes the owning agent come and
    read this file. A FAIL is never rewritten - a broken environment is a broken
    environment and the contract is beside the point.
    """
    if problem is not None and problem.result is Result.FAIL:
        return problem
    return pending(absent + " - " + contract)


# --- recording_span_continuous --------------------------------------------- #

RECORDING_REPORT = Path("tests") / "fixtures" / "recording_report.json"

#: Twenty-four hours, in microseconds. `architecture-context.md` fixes microseconds
#: since epoch as the project's timestamp unit, so that is the unit this report is
#: read in; an ISO-8601 string is accepted too, because a digest meant to be read by
#: a person is a reasonable place for one.
MIN_RECORDING_SPAN_US = 24 * 60 * 60 * 1_000_000

RECORDING_REPORT_CONTRACT = (
    "expected tests/fixtures/recording_report.json: "
    '{"span": {"start": .., "end": ..}, '
    '"segments": [{"start": .., "end": ..}, ..], '
    '"gaps": [{"start": .., "end": .., "cause": ".."}, ..]} '
    "- every moment as microseconds since epoch or ISO-8601, and the segments plus "
    "the gaps tiling the span exactly"
)


def _report_moment(value: Any, what: str) -> tuple[int | None, str]:
    """One instant out of the report, in microseconds. Returns (value, problem)."""
    if isinstance(value, bool):
        return None, what + " is a bool, not an instant"
    if isinstance(value, int):
        return value, ""
    if isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return None, what + " is neither microseconds nor ISO-8601: " + repr(value)
        if moment.tzinfo is None:
            return None, what + " is a naive datetime; UTC only"
        return int(moment.timestamp() * 1_000_000), ""
    return None, what + " is not an instant: " + repr(value)


def _report_interval(entry: Any, what: str) -> tuple[tuple[int, int] | None, str]:
    if not isinstance(entry, Mapping):
        return None, what + " is not an object"
    start, problem = _report_moment(entry.get("start"), what + ".start")
    if start is None:
        return None, problem
    end, problem = _report_moment(entry.get("end"), what + ".end")
    if end is None:
        return None, problem
    if end <= start:
        return None, what + " ends at or before it starts"
    return (start, end), ""


def check_recording_span_continuous(ctx: VerifyContext) -> Outcome:
    """At least 24 continuous hours, with **every break accounted for**.

    The accounting is the whole criterion. A report that simply shows no gaps is
    not the same as one that accounts for them: an outage the recorder never
    noticed leaves no gap entry and a naive check reads that as perfect uptime.
    So the segments and the gaps are required to *tile* the span - every moment in
    it is either recorded or is inside a break carrying a stated cause, and no
    moment is both. A hole in the tiling is a break nobody accounted for, and it
    is a FAIL however few gap entries the report happens to carry.
    """
    path = ctx.root / RECORDING_REPORT
    if not path.is_file():
        return pending(
            "tests/fixtures/recording_report.json does not exist yet (spec 27) - "
            + RECORDING_REPORT_CONTRACT
        )
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return failed("recording_report.json is not valid JSON: " + str(exc))
    if not isinstance(report, Mapping):
        return failed("recording_report.json is not a JSON object")

    for key in ("span", "segments", "gaps"):
        if key not in report:
            return pending(
                "recording_report.json carries no `" + key + "` yet - " + RECORDING_REPORT_CONTRACT
            )

    span, problem = _report_interval(report["span"], "span")
    if span is None:
        return failed(problem)
    span_start, span_end = span
    if span_end - span_start < MIN_RECORDING_SPAN_US:
        hours = (span_end - span_start) / 3_600_000_000
        return failed(f"the report spans {hours:.2f}h, and the criterion asks for 24h")

    segments_raw = report["segments"]
    gaps_raw = report["gaps"]
    if not isinstance(segments_raw, Sequence) or isinstance(segments_raw, str):
        return failed("`segments` is not a list")
    if not isinstance(gaps_raw, Sequence) or isinstance(gaps_raw, str):
        return failed("`gaps` is not a list")
    if not segments_raw:
        return failed("the report accounts for no recorded segment at all")

    intervals: list[tuple[int, int, str]] = []
    for index, entry in enumerate(segments_raw):
        interval, problem = _report_interval(entry, f"segments[{index}]")
        if interval is None:
            return failed(problem)
        intervals.append((interval[0], interval[1], "recorded"))
    for index, entry in enumerate(gaps_raw):
        interval, problem = _report_interval(entry, f"gaps[{index}]")
        if interval is None:
            return failed(problem)
        cause = entry.get("cause") if isinstance(entry, Mapping) else None
        if not isinstance(cause, str) or not cause.strip():
            return failed(
                f"gaps[{index}] carries no `cause`. A break with no cause is an outage "
                "mistaken for a quiet market, which is the one thing this report exists "
                "to tell apart."
            )
        intervals.append((interval[0], interval[1], "gap"))

    intervals.sort()
    cursor = span_start
    for start, end, kind in intervals:
        if start > cursor:
            unaccounted = (start - cursor) / 1_000_000
            return failed(
                f"{unaccounted:.0f}s of the span is neither a recorded segment nor an "
                "accounted break. A report that shows no gap there is not the same as "
                "one that accounts for it."
            )
        if start < cursor:
            return failed(f"a {kind} interval overlaps the one before it")
        cursor = end
    if cursor < span_end:
        trailing = (span_end - cursor) / 1_000_000
        return failed(f"the last {trailing:.0f}s of the span is unaccounted for")
    if cursor > span_end:
        return failed("the segments and gaps run past the end of the declared span")

    hours = (span_end - span_start) / 3_600_000_000
    return passed(
        f"{hours:.1f}h span tiled exactly by {len(segments_raw)} recorded segment(s) and "
        f"{len(gaps_raw)} accounted break(s); every break carries a cause"
    )


# --- candles_match_kraken_ohlc --------------------------------------------- #

OHLC_FIXTURE = Path("tests") / "fixtures" / "kraken" / "ohlc.json"

#: Three pairs, per the phase row in `ai-workflow-rules.md`.
OHLC_MIN_PAIRS = 3

#: Volume tolerance, as the phase row states it. Prices are compared against the
#: pair's own `tick_size` **as reported by `AssetPairs`** and never against a
#: constant; there is deliberately no price tolerance named here.
VOLUME_TOLERANCE = Decimal("0.001")

OHLC_FIELDS = ("open", "high", "low", "close")

#: Where a builder may live. A is free to put it in any of these; naming three
#: rather than one keeps this criterion from dictating a module layout it does not
#: own.
CANDLE_BUILDER_MODULES = (
    "acsoe.engines.market_sensor.candles",
    "acsoe.engines.market_sensor.contracts",
    "acsoe.engines.market_sensor.engine",
)

CANDLES_CONTRACT = (
    "expected: tests/fixtures/kraken/ohlc.json as "
    '{"interval_s": 900, "pairs": {"<PAIR>": {"trades": [..], "ohlc": '
    '[{"ts": .., "open": .., "high": .., "low": .., "close": .., "volume": ..}, ..]}}} '
    "for at least 3 pairs that also appear in tests/fixtures/kraken/asset_pairs.json; "
    "and `build_candles(trades, *, interval_s)` in one of "
    + ", ".join(CANDLE_BUILDER_MODULES)
    + ", returning one candle per closed bar carrying ts/open/high/low/close/volume"
)


def _field(obj: Any, name: str) -> Any:
    """A field off a mapping or off a model, without caring which A chose."""
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return as_decimal(value, "value")
    except (TypeError, ValueError):
        return None


def _pair_tick_sizes(root: Path) -> tuple[dict[str, Decimal] | None, Outcome | None]:
    """`tick_size` per pair, **as `AssetPairs` reports it**.

    Read through the fake Kraken client rather than out of the JSON directly. The
    phase row says "as reported by `AssetPairs`", and the point of that wording is
    that the tolerance is an exchange value the system fetches, not a number a test
    knows. Going through the client keeps the criterion reading it the same way the
    engines do, so a change in how a pair rule is parsed reaches this gate too.
    """
    fixture = root / "tests" / "fixtures" / "kraken" / "asset_pairs.json"
    if not fixture.is_file():
        return None, pending("tests/fixtures/kraken/asset_pairs.json does not exist yet")
    module, problem = try_import("tests.harness.fake_kraken")
    if module is None:
        return None, problem
    client_cls, missing = module_attr(module, "FakeKrakenClient")
    if client_cls is None:
        return None, pending("test doubles unavailable: " + missing)
    snapshot = asyncio.run(client_cls().asset_pairs())
    return {pair: rule.tick_size for pair, rule in snapshot.pairs.items()}, None


def _candle_builder() -> tuple[Any, Outcome | None]:
    for dotted in CANDLE_BUILDER_MODULES:
        module, problem = try_import(dotted)
        if module is None:
            if problem is not None and problem.result is Result.FAIL:
                return None, problem
            continue
        builder = getattr(module, "build_candles", None)
        if builder is not None:
            return builder, None
    return None, pending("no `build_candles` exists yet (spec 28) - " + CANDLES_CONTRACT)


def check_candles_match_kraken_ohlc(ctx: VerifyContext) -> Outcome:
    """Built 15-minute candles against Kraken's own OHLC, for three pairs.

    Every OHLC field within one `tick_size` **for that pair as `AssetPairs` reports
    it**, and volume within 0.1%. The tolerance is fetched, never hardcoded: rule 2
    of `trading-invariants.md` says any tick size an agent remembers is stale, and a
    criterion carrying its own copy of one would be asserting against a number the
    exchange has already moved.
    """
    fixture_path = ctx.root / OHLC_FIXTURE
    if not fixture_path.is_file():
        return pending(
            "tests/fixtures/kraken/ohlc.json does not exist yet (spec 28) - " + CANDLES_CONTRACT
        )
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return failed("ohlc.json is not valid JSON: " + str(exc))
    if not isinstance(fixture, Mapping) or not isinstance(fixture.get("pairs"), Mapping):
        return pending("ohlc.json carries no `pairs` yet - " + CANDLES_CONTRACT)

    pairs = fixture["pairs"]
    if len(pairs) < OHLC_MIN_PAIRS:
        return failed(
            f"ohlc.json covers {len(pairs)} pair(s); the phase row asks for "
            f"{OHLC_MIN_PAIRS}"
        )
    interval_s = fixture.get("interval_s", 900)
    if not isinstance(interval_s, int) or interval_s <= 0:
        return failed("ohlc.json `interval_s` is not a positive integer")

    with root_import_path(ctx.root):
        tick_sizes, early = _pair_tick_sizes(ctx.root)
        if tick_sizes is None:
            return early or pending("no pair rules to read a tolerance from")
        builder, early = _candle_builder()
        if builder is None:
            return early or pending("no candle builder yet - " + CANDLES_CONTRACT)

        checked = 0
        for pair, payload in pairs.items():
            if pair not in tick_sizes:
                return failed(
                    f"{pair} is in ohlc.json and not in asset_pairs.json, so its "
                    "tick_size cannot be read from AssetPairs and the tolerance would "
                    "have to be invented"
                )
            tick = tick_sizes[pair]
            if not isinstance(payload, Mapping):
                return failed(f"ohlc.json pairs[{pair}] is not an object")
            trades = payload.get("trades")
            expected_bars = payload.get("ohlc")
            if trades is None or expected_bars is None:
                return pending(
                    f"ohlc.json pairs[{pair}] carries no trades/ohlc yet - " + CANDLES_CONTRACT
                )
            built = builder(trades, interval_s=interval_s)
            by_ts: dict[int, Any] = {}
            for candle in built:
                ts = _field(candle, "ts")
                if not isinstance(ts, int):
                    return failed(f"a built candle for {pair} carries no integer `ts`")
                by_ts[ts] = candle

            for expected in expected_bars:
                ts = _field(expected, "ts")
                if not isinstance(ts, int):
                    return failed(f"ohlc.json has a {pair} bar with no integer `ts`")
                candle = by_ts.get(ts)
                if candle is None:
                    return failed(
                        f"the builder produced no {pair} candle at ts={ts}, which Kraken's "
                        "own OHLC has. A dropped bar is a missing decision bar."
                    )
                for name in OHLC_FIELDS:
                    want = _decimal_or_none(_field(expected, name))
                    got = _decimal_or_none(_field(candle, name))
                    if want is None or got is None:
                        return failed(f"{pair} at ts={ts}: `{name}` is missing or not a number")
                    if abs(got - want) > tick:
                        return failed(
                            f"{pair} at ts={ts}: {name} {got} vs Kraken {want}, which is "
                            f"more than one tick_size ({tick}) from AssetPairs"
                        )
                want_vol = _decimal_or_none(_field(expected, "volume"))
                got_vol = _decimal_or_none(_field(candle, "volume"))
                if want_vol is None or got_vol is None:
                    return failed(f"{pair} at ts={ts}: `volume` is missing or not a number")
                allowed = abs(want_vol) * VOLUME_TOLERANCE
                if abs(got_vol - want_vol) > allowed:
                    return failed(
                        f"{pair} at ts={ts}: volume {got_vol} vs Kraken {want_vol}, outside 0.1%"
                    )
                checked += 1

    return passed(
        f"{len(pairs)} pairs, {checked} bar(s): every OHLC field within one tick_size as "
        "AssetPairs reports it, volume within 0.1%"
    )


# --- data_guard_blocks_bad_data -------------------------------------------- #

#: The three conditions the phase row names, plus the pass case. A gate with only a
#: happy path is incomplete; a gate with only block cases is a gate that blocks
#: everything and proves nothing, so the clean case is not optional either.
GUARD_BLOCK_SCENARIOS = ("stale", "negative_spread", "missing_candle")
GUARD_CLEAN_SCENARIO = "clean"

DATA_GUARD_CONTRACT = (
    "expected: acsoe.engines.data_guard.contracts.BAD_DATA_SCENARIOS mapping "
    + repr([*GUARD_BLOCK_SCENARIOS, GUARD_CLEAN_SCENARIO])
    + " to a `state` mapping ready to hand to the engine, and "
    "acsoe.engines.data_guard.engine exposing the BaseEngine subclass with "
    "name == 'data_guard'. The fixtures live in A's own contracts module because the "
    "fields they set belong to engines 1 and 3, and this gate must not hardcode a "
    "field name it does not own"
)


def _engine_named(module: ModuleType, name: str) -> Any:
    """The `BaseEngine` subclass in `module` whose `name` is `name`."""
    for value in vars(module).values():
        if inspect.isclass(value) and getattr(value, "name", None) == name:
            return value
    return None


def check_data_guard_blocks_bad_data(ctx: VerifyContext) -> Outcome:
    """Injected stale, negative-spread and missing-candle data each block; clean passes.

    Four cases in one criterion, because three block cases without a pass case would
    be satisfied by a gate that refuses everything, and a pass case without the block
    cases would be satisfied by a gate that refuses nothing.
    """
    with root_import_path(ctx.root):
        contracts_mod, problem = try_import("acsoe.engines.data_guard.contracts")
        if contracts_mod is None:
            return _with_contract(
                problem,
                "engine 4 `data_guard` does not exist yet (spec 29)",
                DATA_GUARD_CONTRACT,
            )
        engine_mod, problem = try_import("acsoe.engines.data_guard.engine")
        if engine_mod is None:
            return problem or pending("acsoe.engines.data_guard.engine does not exist yet")
        scenarios = getattr(contracts_mod, "BAD_DATA_SCENARIOS", None)
        if not isinstance(scenarios, Mapping):
            return pending("no BAD_DATA_SCENARIOS yet - " + DATA_GUARD_CONTRACT)
        missing = [
            key
            for key in (*GUARD_BLOCK_SCENARIOS, GUARD_CLEAN_SCENARIO)
            if key not in scenarios
        ]
        if missing:
            return pending(
                "BAD_DATA_SCENARIOS is missing " + ", ".join(missing) + " - " + DATA_GUARD_CONTRACT
            )

        engine_cls = _engine_named(engine_mod, "data_guard")
        if engine_cls is None:
            return pending(
                "acsoe.engines.data_guard.engine exposes no class with name == 'data_guard'"
            )
        if not getattr(engine_cls, "is_gate", False):
            return failed(
                "data_guard declares is_gate = False. It is the first real gate in the "
                "system and engine-contracts.md marks it Y."
            )

        doubles, problem = _harness_doubles()
        if doubles is None:
            return problem or pending("test doubles unavailable")
        try:
            context, early = _guard_context(doubles)
            if context is None:
                return early or pending("acsoe.core.contracts.EngineContext does not exist yet")
            try:
                engine = engine_cls(doubles.config) if _takes_config(engine_cls) else engine_cls()
            except KeyError as exc:
                unset = _unset_config_key(ctx.root, exc)
                if unset is None:
                    raise
                return pending(_unset_key_message(unset))

            reasons: dict[str, str] = {}
            for key in GUARD_BLOCK_SCENARIOS:
                state = dict(scenarios[key])
                try:
                    result = engine.process(context, state)
                except KeyError as exc:
                    unset = _unset_config_key(ctx.root, exc)
                    if unset is None:
                        raise
                    return pending(_unset_key_message(unset))
                if not getattr(result, "blocks_trading", False):
                    return failed(
                        f"injected {key.replace('_', ' ')} data did not block. A gate that "
                        "passes data it does not trust is not a gate."
                    )
                reason = getattr(result, "reason", None)
                if not isinstance(reason, str) or not reason.strip():
                    return failed(f"the {key} block carries no reason for the operator")
                reasons[key] = reason.strip()

            clean = engine.process(context, dict(scenarios[GUARD_CLEAN_SCENARIO]))
            if getattr(clean, "blocks_trading", False):
                return failed(
                    "clean data blocked with reason "
                    + repr(getattr(clean, "reason", None))
                    + ". A gate that blocks everything proves nothing."
                )
        finally:
            doubles.close()

    if len(set(reasons.values())) != len(reasons):
        return failed(
            "two of the three conditions report the same reason, so the operator cannot "
            "tell a stale feed from a crossed book: " + repr(sorted(reasons.values()))
        )
    return passed(
        "stale, negative-spread and missing-candle each block with a distinct "
        "operator-readable reason, and clean data passes"
    )


def _unset_key_message(dotted: str) -> str:
    return (
        "engine 4 needs the config key `"
        + dotted
        + "`, which config/default.yaml does not carry. Only the lead adds a key, and "
        "refusing to run without a threshold is the correct fail-closed behaviour rather "
        "than a defect in the engine or in this gate."
    )


def _takes_config(engine_cls: Any) -> bool:
    try:
        parameters = inspect.signature(engine_cls).parameters
    except (TypeError, ValueError):
        return False
    return bool(parameters)


def _context_values(doubles: Any) -> dict[str, Any]:
    """What this script can supply for an `EngineContext` field, by name.

    The context is built by *asking the dataclass what it takes* rather than by
    passing a fixed argument list. `core/contracts.py` is the lead's and its shape
    is not mine to remember: an earlier version of this helper passed `cycle_id=1`,
    which is not a field - a tick is identified by `(run_id, cycle_id)` and the
    `cycle_id` half lives in `state`, not on the context - and omitted `mode`,
    which is required. That call raises `TypeError` and never returns a context. It
    was invisible only because `try_import` returned first while engine 4 did not
    exist, and A caught it by reading before landing the module that would have
    turned a PENDING into a red gate for everyone.

    Introspection rather than a corrected argument list, because a corrected list
    is the same defect one edit later. A field the lead adds that this cannot
    supply is reported by name instead of raising.
    """
    return {
        "mode": doubles.config.mode,
        "run_id": "verify-data-guard",
        "now": doubles.clock.now(),
        "config": doubles.config,
        "clients": doubles.clients,
    }


def _guard_context(doubles: Any) -> tuple[Any, Outcome | None]:
    """An `EngineContext` for one tick, built from the shared doubles."""
    core_mod, problem = try_import("acsoe.core.contracts")
    if core_mod is None:
        return None, problem or pending("acsoe.core.contracts does not exist yet")
    context_cls, missing = module_attr(core_mod, "EngineContext")
    if context_cls is None:
        return None, pending(missing)
    try:
        parameters = inspect.signature(context_cls).parameters
    except (TypeError, ValueError):
        return None, failed("acsoe.core.contracts.EngineContext has no readable signature")

    available = _context_values(doubles)
    unsupplied = [
        name
        for name, parameter in parameters.items()
        if name not in available and parameter.default is inspect.Parameter.empty
    ]
    if unsupplied:
        return None, pending(
            "acsoe.core.contracts.EngineContext requires "
            + ", ".join(unsupplied)
            + ", which this criterion has no value for. Add it to `_context_values`."
        )
    kwargs = {name: value for name, value in available.items() if name in parameters}
    return context_cls(**kwargs), None


_DOTTED_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")


def _unset_config_key(root: Path, exc: KeyError) -> str | None:
    """The dotted config key a `KeyError` names, if it really is absent from config.

    An engine reaching for a threshold nobody has set raises `KeyError` from the
    config layer, and that is the **correct** fail-closed behaviour - an engine
    silently receiving `None` for a threshold is the failure this project refuses.
    It is not a verdict about the engine, though, and reporting it as a FAIL makes
    an unconfigured gate look like a broken one.

    So the key is checked rather than assumed. Absent from `config/default.yaml`
    entirely: PENDING, naming the key, because only the lead adds one and spec 29
    says a key an engine needs and does not have is a request to the lead. Present
    in the file and still raising: not this, and the criterion FAILs as it should -
    the engine asked for something that exists, in a shape it did not expect.
    """
    text = str(exc.args[0]) if exc.args else ""
    match = _DOTTED_KEY.search(text)
    if match is None:
        return None
    dotted = match.group(0)
    config, _ = load_config(root)
    if config is None:
        return dotted
    return dotted if config_get(config, dotted) is _CONFIG_MISSING else None


# --- historical_loader_reports_gaps ---------------------------------------- #

#: A fabricated archive: 15-minute bars with three holes of 1, 2 and 4 missing bars.
#: Deliberately three holes of *different* sizes, so a loader that reported the
#: number of missing bars rather than the number of gaps reports 7 and is caught.
ARCHIVE_INTERVAL_S = 900
ARCHIVE_BARS = 48
ARCHIVE_HOLES = ((10, 1), (20, 2), (33, 4))

HISTORICAL_CONTRACT = (
    "expected: acsoe.research.historical.load_archive(path, *, interval_s) returning a "
    "report carrying `gap_count: int`, `row_count: int`, `timestamps` (the archive's "
    "own timestamps, in seconds), `duration_buckets` and a largest-gap figure"
)


def _fabricate_archive(path: Path) -> tuple[list[int], int]:
    """Write a Kraken OHLCVT CSV with known holes. Returns (timestamps, gap count)."""
    skipped: set[int] = set()
    for start, length in ARCHIVE_HOLES:
        skipped.update(range(start, start + length))
    base = 1_700_000_000
    lines: list[str] = []
    timestamps: list[int] = []
    for index in range(ARCHIVE_BARS):
        if index in skipped:
            continue
        ts = base + index * ARCHIVE_INTERVAL_S
        timestamps.append(ts)
        price = 100 + index
        lines.append(f"{ts},{price}.0,{price}.5,{price}.0,{price}.2,1.5,7")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return timestamps, len(ARCHIVE_HOLES)


def check_historical_loader_reports_gaps(ctx: VerifyContext) -> Outcome:
    """A fabricated archive with a known number of holes reports exactly that number.

    And a second assertion the first one cannot make: **no timestamp in the output
    was absent from the input.** Counting gaps correctly while also emitting filled
    rows passes the count check and still poisons Phase 4's triple-barrier labels,
    because a synthesised candle at a price that never traded invents a barrier
    touch that never happened. Spec 30 calls that its single most important
    sentence, so the gate asserts it separately rather than trusting the count.
    """
    with (
        root_import_path(ctx.root),
        tempfile.TemporaryDirectory(prefix="acsoe-verify-archive-") as tmp,
    ):
        module, problem = try_import("acsoe.research.historical")
        if module is None:
            return _with_contract(
                problem,
                "acsoe.research.historical does not exist yet (spec 30)",
                HISTORICAL_CONTRACT,
            )
        loader, missing = module_attr(module, "load_archive")
        if loader is None:
            return pending(missing + " - " + HISTORICAL_CONTRACT)

        archive = Path(tmp) / "XBTUSD_15.csv"
        timestamps, expected_gaps = _fabricate_archive(archive)
        report = loader(archive, interval_s=ARCHIVE_INTERVAL_S)

        gap_count = _field(report, "gap_count")
        if not isinstance(gap_count, int):
            return pending("the report carries no integer `gap_count` yet - " + HISTORICAL_CONTRACT)
        if gap_count != expected_gaps:
            return failed(
                f"the archive has {expected_gaps} hole(s) of "
                + ", ".join(str(n) for _, n in ARCHIVE_HOLES)
                + f" bars and the loader reported {gap_count}. A loader that silently "
                "filled the holes, or that counted missing bars rather than gaps, "
                "reports a different number - which is why the holes differ in size."
            )

        row_count = _field(report, "row_count")
        if isinstance(row_count, int) and row_count != len(timestamps):
            return failed(
                f"the archive carries {len(timestamps)} rows and the report says "
                f"{row_count}. A row the archive did not contain is an invented candle."
            )

        emitted = _field(report, "timestamps")
        if emitted is None:
            return pending(
                "the report exposes no `timestamps` to check against the input - "
                + HISTORICAL_CONTRACT
            )
        try:
            emitted_set = {int(value) for value in emitted}
        except (TypeError, ValueError):
            return failed("the report's `timestamps` are not integers")
        invented = sorted(emitted_set - set(timestamps))
        if invented:
            return failed(
                f"{len(invented)} timestamp(s) in the output were absent from the archive, "
                f"first at {invented[0]}. A missing candle means no trades occurred; "
                "interpolating one fabricates the outcome Phase 4 then labels."
            )

        for name in ("duration_buckets", "largest_gap_bars", "largest_gap"):
            if _field(report, name) is not None:
                break
        else:
            return pending(
                "the report neither buckets gap durations nor reports the largest - "
                + HISTORICAL_CONTRACT
            )

    return passed(
        f"{expected_gaps} gaps of "
        + "/".join(str(n) for _, n in ARCHIVE_HOLES)
        + f" bars reported exactly, over {len(timestamps)} rows, and no timestamp in the "
        "output was absent from the input"
    )


# --- console_shows_live_rows ----------------------------------------------- #


def _moment_after_newest_run(db_path: Path) -> datetime:
    """A clock reading later than every `runs` row already in the database.

    The seed's timestamps are fixed constants with no relationship to wall time -
    that is deliberate, so two seedings are byte-identical - and they happen to sit
    in the future. A daemon driven from an ordinary fixed clock would therefore
    write a `runs` row that sorts *before* every seeded one, and a console that
    reads the latest run would render seeded history and call it current. Starting
    the daemon after the seed is what a real daemon does; it weakens nothing,
    because the rows the criterion then asserts on are still written by a real
    orchestrator through a real store.
    """
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT MAX(started_at) FROM runs").fetchone()
    finally:
        conn.close()
    newest = int(row[0] or 0)
    return datetime.fromtimestamp(newest / 1_000_000, tz=UTC) + timedelta(minutes=1)


#: The four engines this phase builds. The criterion is PENDING until at least one
#: of them is registered, because until then no daemon can write a live row at all.
PHASE_2_ENGINE_NUMBERS = frozenset({1, 2, 3, 4})

LIVE_ROWS_CONTRACT = (
    "expected: engines 1 to 4 registered in bootstrap.py, and a tick of the real "
    "Orchestrator over the real StoreClient leaving at least one row carrying the "
    "daemon's own run_id that the console then renders"
)


def _run_ids_in_store(db_path: Path) -> set[str]:
    """Every `run_id` any console-rendered table currently carries."""
    conn = sqlite3.connect(db_path)
    found: set[str] = set()
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        for table in sorted(tables):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if "run_id" not in columns:
                continue
            # The table name comes from sqlite_master, never from input.
            for row in conn.execute(f"SELECT DISTINCT run_id FROM {table}"):
                if row[0] is not None:
                    found.add(str(row[0]))
    finally:
        conn.close()
    return found


class _LiveClients:
    """The three injected clients, with the *real* store and the fake exchange.

    `_RoundTripClients` next door exposes its three as read-only properties, which
    is right for the criterion it was written for and wrong here: this one needs a
    fake Kraken client, because a Phase 2 engine that fetched over the network
    inside a phase gate would be a criterion that cannot run on a fresh clone.
    """

    def __init__(self, store: Any, kraken: Any, recorder: Any) -> None:
        self.store = store
        self.kraken = kraken
        self.recorder = recorder


def _registered_phase_2_engines(bootstrap: ModuleType) -> list[str]:
    """The names of engines 1 to 4 that are actually wired into a chain."""
    built: list[str] = []
    for symbol in CHAIN_SYMBOLS:
        for engine in getattr(bootstrap, symbol, ()) or ():
            if getattr(engine, "number", None) in PHASE_2_ENGINE_NUMBERS:
                built.append(str(getattr(engine, "name", type(engine).__name__)))
    return built


def check_console_shows_live_rows(ctx: VerifyContext) -> Outcome:
    """The console renders rows a daemon wrote, not only rows the seed wrote.

    **Distinguished by run**, which is what makes the criterion unsatisfiable by
    seeded data: the daemon mints its own `run_id` and no seeded row carries it, so
    a console that renders the seed and nothing else cannot pass this by accident.
    """
    with root_import_path(ctx.root), console_workspace() as tmp:
        bootstrap, problem = try_import("acsoe.bootstrap")
        if bootstrap is None:
            return problem or pending("acsoe.bootstrap does not exist yet")
        built = _registered_phase_2_engines(bootstrap)
        if not built:
            return pending(
                "no Phase 2 engine is registered in bootstrap.py yet (specs 26-29) - "
                + LIVE_ROWS_CONTRACT
            )

        config, early = console_config()
        if config is None:
            return early or pending("no config to build the console with")
        db_path, early = seeded_console_db(tmp)
        if db_path is None:
            return early or pending("no seeded database")

        seeded_runs = _run_ids_in_store(db_path)

        client_mod, problem = try_import("acsoe.clients.store.client")
        if client_mod is None:
            return problem or pending("acsoe.clients.store.client does not exist yet")
        store_cls, missing = module_attr(client_mod, "StoreClient")
        if store_cls is None:
            return pending(missing)
        orch_cls, chains_cls, early = _orchestrator_and_chains()
        if orch_cls is None or chains_cls is None:
            return early or pending("the orchestrator does not exist yet")

        doubles, problem = _harness_doubles()
        if doubles is None:
            return problem or pending("test doubles unavailable")
        try:
            doubles.clock.set(_moment_after_newest_run(db_path))
            with store_cls(db_path) as store:
                clients = _LiveClients(store, doubles.clients.kraken, doubles.clients.recorder)
                orchestrator = orch_cls(
                    config=doubles.config,
                    clock=doubles.clock,
                    clients=clients,
                    chains=chains_cls(
                        guard=bootstrap.GUARD_CHAIN,
                        opportunity=bootstrap.OPPORTUNITY_CHAIN,
                        manage=bootstrap.MANAGE_CHAIN,
                    ),
                )
                try:
                    orchestrator.tick()
                    doubles.clock.advance(60)
                    orchestrator.tick()
                except Exception as exc:  # a registered engine must survive a tick
                    return failed(
                        "a tick over the registered Phase 2 engines raised "
                        f"{type(exc).__name__}: {exc}"
                    )
                daemon_run_id = orchestrator.run_id
        finally:
            doubles.close()

        live_runs = _run_ids_in_store(db_path) - seeded_runs
        if daemon_run_id not in live_runs:
            return pending(
                "the registered engines ("
                + ", ".join(built)
                + ") left no store row carrying the daemon's run_id, so there is nothing "
                "live for the console to render yet. Engine 19 `memory` is the single "
                "writer of relational rows and is Phase 4; the run record is the "
                "orchestrator's."
            )

        app, early = console_app(config, db_path)
        if app is None:
            return early or pending("the console application does not exist yet")
        try:
            rendered = {
                path: asgi_request(app, "GET", path)
                for path, _ in CONSOLE_SCREENS
                if path != "/"
            }
        finally:
            close_console(app)

    showing = [path for path, response in rendered.items() if daemon_run_id in response.text]
    if not showing:
        answered = {path: response.status for path, response in rendered.items()}
        return failed(
            "the daemon wrote rows under run_id "
            + daemon_run_id
            + " and no console screen renders any of them; screens answered "
            + repr(answered)
        )
    return passed(
        "a tick of "
        + ", ".join(built)
        + " wrote rows under the daemon's own run_id, and "
        + ", ".join(sorted(showing))
        + " render them alongside the seed"
    )


def _orchestrator_and_chains() -> tuple[Any, Any, Outcome | None]:
    orch_mod, problem = try_import("acsoe.core.orchestrator")
    if orch_mod is None:
        return None, None, problem or pending("acsoe.core.orchestrator does not exist yet")
    core_mod, problem = try_import("acsoe.core.contracts")
    if core_mod is None:
        return None, None, problem or pending("acsoe.core.contracts does not exist yet")
    orch_cls, missing = module_attr(orch_mod, "Orchestrator")
    if orch_cls is None:
        return None, None, pending(missing)
    chains_cls, missing = module_attr(core_mod, "Chains")
    if chains_cls is None:
        return None, None, pending(missing)
    return orch_cls, chains_cls, None


# --- console_reads_persisted_mode ------------------------------------------ #

RUNNING_STATE_TEXT = "Running"
FROZEN_STATE_TEXT = "Frozen"

PERSISTED_MODE_CONTRACT = (
    "expected: the command reader in core/ writing the run record at startup and "
    "calling store.set_system_mode(run_id, mode, at=now) after each transition it "
    "applies, so the console reads the mode as a fact"
)


def check_console_reads_persisted_mode(ctx: VerifyContext) -> Outcome:
    """`Running` and `Frozen` in the band, from a mode a **real daemon wrote**.

    Not a fabricated column value, per the operator's Phase 1 ruling. The criterion
    drives the real `Orchestrator` against the real `StoreClient`, appends a real
    `activate` and then a real `freeze` through the real command table, and asks the
    console what its State field says. Writing the column here directly would prove
    the console can read a column and nothing at all about the seam that fills it -
    which is precisely the class of defect `commands_round_trip` exists to catch.
    """
    with root_import_path(ctx.root), console_workspace() as tmp:
        config, early = console_config()
        if config is None:
            return early or pending("no config to build the console with")
        db_path, early = seeded_console_db(tmp)
        if db_path is None:
            return early or pending("no seeded database")

        client_mod, problem = try_import("acsoe.clients.store.client")
        if client_mod is None:
            return problem or pending("acsoe.clients.store.client does not exist yet")
        contracts_mod, problem = try_import("acsoe.clients.store.contracts")
        if contracts_mod is None:
            return problem or pending("acsoe.clients.store.contracts does not exist yet")
        store_cls, missing = module_attr(client_mod, "StoreClient")
        if store_cls is None:
            return pending(missing)
        if not hasattr(store_cls, "set_system_mode") or not hasattr(store_cls, "system_mode"):
            return pending(
                "StoreClient has no system-mode accessor yet (spec 31) - "
                + PERSISTED_MODE_CONTRACT
            )
        orch_cls, chains_cls, early = _orchestrator_and_chains()
        if orch_cls is None or chains_cls is None:
            return early or pending("the orchestrator does not exist yet")

        clock = _RoundTripClock(_moment_after_newest_run(db_path))
        stamp = 1_788_100_000_000_000
        readings: dict[str, str] = {}
        for name, expected in (("activate", RUNNING_STATE_TEXT), ("freeze", FROZEN_STATE_TEXT)):
            with store_cls(db_path) as store:
                _append_command(store, contracts_mod, name, stamp)
                orchestrator = orch_cls(
                    config=_RoundTripConfig(),
                    clock=clock,
                    clients=_RoundTripClients(store),
                    chains=chains_cls(),
                )
                orchestrator.tick()
                run_id = orchestrator.run_id
                persisted = store.system_mode(run_id)
            stamp += 1

            if persisted is None:
                return pending(
                    "the daemon left no `runs` row for its own run_id, so "
                    "set_system_mode had nothing to update. The run record is written "
                    "at startup by the orchestrator and that write does not exist yet - "
                    + PERSISTED_MODE_CONTRACT
                )
            if persisted.mode is None:
                return pending(
                    "the run exists and carries no persisted mode after `"
                    + name
                    + "`, so core/'s command reader is not calling set_system_mode yet - "
                    + PERSISTED_MODE_CONTRACT
                )

            app, early = console_app(config, db_path)
            if app is None:
                return early or pending("the console application does not exist yet")
            try:
                response = asgi_request(app, "GET", "/api/state")
            finally:
                close_console(app)
            if response.status == 404:
                return pending("the status band is not routed yet (GET /api/state is a 404)")
            if response.status != 200:
                return failed("GET /api/state answered " + str(response.status))
            readings[name] = response.text
            if expected not in response.text:
                return failed(
                    "the daemon persisted mode "
                    + repr(str(persisted.mode))
                    + " after `"
                    + name
                    + "` and the band does not read `"
                    + expected
                    + "`. The mode is a fact in the store; the band is reading "
                    "something else."
                )

    if RESTART_STATE_TEXT in readings["activate"] or RESTART_STATE_ESCAPED in readings["activate"]:
        return failed(
            "the band still reads the restart banner over a running daemon. An idle "
            "reading and a running one are different facts."
        )
    return passed(
        "a real daemon applied activate then freeze through the real store, and the "
        "band followed to `Running` then `Frozen`"
    )


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
# `toolchain_green` runs in EVERY phase, exactly as `docs_vocabulary` does.
#
# It was registered for phase 0 alone until the Phase 1 close, and that was a hole:
# `--phase 1` reported `7 PASS, 0 FAIL` on a tree where `pytest` was reporting
# `2 failed, 639 passed`. Nothing in the report was wrong - no Phase 1 criterion made
# any claim about the suite - but "a phase is done when `verify.py --phase N` passes
# every criterion" is the project's definition of done, so for every phase after 0 that
# definition could not see a broken test suite. It was caught only because run-protocol
# step 4 makes each agent run all four commands by hand, which is a person following a
# procedure rather than a gate.
#
# `TOOLCHAIN` stays scoped to `src/`. Widening it to `tests/` and `scripts/` is a
# separate decision the operator deliberately did not take here.
register_every_phase(Criterion("toolchain_green", check_toolchain_green))
register(0, Criterion("is_gate_matches_registry", check_is_gate_matches_registry))

# Phase 2. Registered by the lead at the phase opening, ahead of every engine spec,
# because it judges a defect that already exists rather than work still to come.
register(2, Criterion("commands_round_trip", check_commands_round_trip))

# Phase 2 - the data spine. Spec 33, registered before the engines it judges so that A
# has a gate to build against from the first commit, exactly as spec 16 was registered
# before the console. Every one of these reports PENDING until its subject lands.
register(2, Criterion("recording_span_continuous", check_recording_span_continuous))
register(2, Criterion("candles_match_kraken_ohlc", check_candles_match_kraken_ohlc))
register(2, Criterion("data_guard_blocks_bad_data", check_data_guard_blocks_bad_data))
register(2, Criterion("historical_loader_reports_gaps", check_historical_loader_reports_gaps))
register(2, Criterion("console_shows_live_rows", check_console_shows_live_rows))
register(2, Criterion("console_reads_persisted_mode", check_console_reads_persisted_mode))

# Phase 1 only - the console. Spec 16, registered before the console it judges so
# that specs 17 to 24 have a gate to build against from the first commit. Every
# one of these reports PENDING until its subject lands, which is what stops
# `--phase 1` claiming a green phase over an empty console.
register(1, Criterion("console_renders_seeded_screens", check_console_renders_seeded_screens))
register(
    1, Criterion("console_websocket_pushes_on_change", check_console_websocket_pushes_on_change)
)
register(1, Criterion("console_commands_write_rows", check_console_commands_write_rows))
register(1, Criterion("console_live_frame_amber", check_console_live_frame_amber))
register(1, Criterion("console_tokens_no_raw_hex", check_console_tokens_no_raw_hex))
register(1, Criterion("console_tabular_figures", check_console_tabular_figures))
register(1, Criterion("console_focus_and_reduced_motion", check_console_focus_and_reduced_motion))
register(1, Criterion("console_restart_banner", check_console_restart_banner))


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

    # Before anything else, and again at the end: this process is the only one that
    # knows an `acsoe-verify-*` directory is safe to delete, and a run that finds
    # fifty of its own leftovers should clear them rather than add a fifty-first.
    # Skipped inside a `toolchain_green` subprocess, where a concurrent outer run
    # may be using its own workspace right now.
    sweeping = not os.environ.get(RECURSION_GUARD_ENV)
    if sweeping:
        sweep_stale_workspaces()

    context = VerifyContext(root=REPO_ROOT, live=bool(args.live))
    to_run, skipped = criteria_for(args.phase, context.live)
    results = [(criterion, run_criterion(criterion, context)) for criterion in to_run]

    if sweeping:
        sweep_stale_workspaces(report=False)

    print(format_report(args.phase, context.root, results, skipped))
    return 1 if any(o.result is Result.FAIL for _, o in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
