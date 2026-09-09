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
    """
    tmp = Path(tempfile.mkdtemp(prefix="acsoe-verify-console-"))
    try:
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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


def close_console(app: Any) -> None:
    """Release whatever the application is holding the database open with."""
    reader = getattr(getattr(app, "state", None), "reader", None)
    closer = getattr(reader, "close", None)
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
                runs = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM runs").fetchone()[0]
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

    context = VerifyContext(root=REPO_ROOT, live=bool(args.live))
    to_run, skipped = criteria_for(args.phase, context.live)
    results = [(criterion, run_criterion(criterion, context)) for criterion in to_run]

    print(format_report(args.phase, context.root, results, skipped))
    return 1 if any(o.result is Result.FAIL for _, o in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
