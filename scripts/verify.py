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
import ast
import asyncio
import contextlib
import copy
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
from typing import Any, Final

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
    """The fakes the test harness already defines, reused so there is one set.

    The store may legitimately be `None` here: several criteria are *supposed* to run
    on trees that have no store at all - `data_guard_blocks_bad_data` judges an engine
    that never touches one, against a fabricated tree carrying `tests/` and no `src/`.
    The guard against a *broken* store is in `migrated_store` itself, where the
    difference between "not written" and "written and will not import" can actually be
    told apart. See its docstring.
    """
    module, problem = try_import("tests.harness.doubles")
    if module is None:
        return None, problem
    factory, missing = module_attr(module, "build_verify_doubles")
    if factory is None:
        return None, pending("test doubles unavailable: " + missing)
    return factory(), None


def check_orchestrator_empty_registry(ctx: VerifyContext) -> Outcome:
    """A tick over an **empty** registry completes cleanly and blocks nothing.

    `bootstrap` is read only for the three chain symbols - their presence and their
    shape are the registry contract, and their absence is what makes this criterion
    report PENDING before spec 03 lands. The tick itself runs over chains this
    function constructs empty, so the criterion tests what its name says in every
    phase from 0 to 8 rather than only in the phase where nothing happens to be
    registered.
    """
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
                # **Explicitly empty, never `bootstrap`'s chains.** The criterion's
                # claim is that an empty registry is valid and a tick over one
                # completes cleanly - which is what stops a future orchestrator
                # quietly requiring at least one engine - and the two assertions
                # below are only true of an *empty* registry. Reading the live
                # chains made both statements coincide while nothing was registered
                # and diverge the moment something was: A rehearsed engines 1 to 4
                # against the fake client and the guard chain blocks every tick with
                # `no_market_data`, which is invariant 3 working correctly, and it
                # would have turned this closed Phase 0 criterion red for nobody's
                # defect. Same shape as the fabricated contract that agreed with a
                # mistake in `_guard_context`: the criterion was held to something
                # that happened to agree with it today.
                #
                # Nothing is lost. `is_gate_matches_registry` asserts the live
                # registry against the table in `engine-contracts.md`, and
                # `console_shows_live_rows` exercises the real chain end to end.
                # Reading the registry here was conflating two questions.
                #
                # Keyword arguments rather than `chains_cls()`: the real `Chains`
                # defaults every field to `()`, and a fabricated one in a test tree
                # need not.
                chains=chains_cls(guard=(), opportunity=(), manage=()),
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
            "one tick completed over an explicitly empty registry; empty chains are "
            'valid, state["system"]["mode"]='
            + repr(system["mode"])
            # "runtime" is load-bearing in this sentence rather than decorative. This
            # counts the three chains in `acsoe.bootstrap`; `is_gate_matches_registry`
            # counts those *plus* the offline chain in `cli/research.py`, where engine 23
            # `backtest` lives and is deliberately never registered in bootstrap. Both
            # numbers are right and they differ by one, so without the word they read as
            # a contradiction in a single report - at exactly the moment somebody is
            # reading that report to decide whether a phase closes.
            + " (acsoe.bootstrap holds "
            + str(registered)
            + " registered runtime engines, which this criterion deliberately does not "
            "tick over "
            "- is_gate_matches_registry and console_shows_live_rows judge those)"
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
#
# **What each command covers, and why.** All three were scoped to `src/` until this
# phase, and that was a hole rather than a simplification.
# `tests/scripts/test_fixture_bytes.py` was committed carrying a backslash escape
# inside an f-string expression - legal from Python 3.12 and a **SyntaxError on the
# 3.11** that `requires-python`, `python_version` and `target-version` all declare.
# The venv here is 3.13, so pytest imported the file happily and every test passed,
# and `ruff check src/` cannot see a file under `tests/`. Nothing in the gate could
# report it; it was found by an agent running ruff over its own test paths out of
# habit, which is a person having a good day rather than a check. `ruff` now reads
# every directory in the repository that holds Python, and reports that exact defect
# as `invalid-syntax` naming the file, the line and the version it is illegal on.
#
# **`mypy --strict` is deliberately NOT widened to `tests/`.** Strict mode demands a
# return annotation on every one of ~1700 test functions and on every fixture; that
# is a separate piece of work with its own blast radius, and it is not what this
# widening was ruled for. The hole it leaves has a shape the next reader needs: a
# type error inside a test file is caught by nothing here except the test failing.
TOOLCHAIN = (
    ("pytest", ["-m", "pytest", "tests/", "-q"], 5),
    ("mypy", ["-m", "mypy", "--strict", "src/", "scripts/"], 2),
    ("ruff", ["-m", "ruff", "check", "--output-format=concise", "src/", "tests/", "scripts/"], 2),
)

#: Where a failing toolchain command's **complete** captured output is written.
#:
#: The criterion prints one line, and one line is not a diagnosis. Until this existed
#: the message carried `describe_exit`'s last three lines and the rest was dropped on
#: the floor: that survives a `FAILED`, where pytest names the failing tests on the
#: summary line, and it does not survive an `ERROR`, where the traceback naming the
#: fixture that raised is a hundred lines above the tail. `toolchain_green` has been
#: intermittently red on a quiescent tree since Phase 2 and every investigation of it
#: has started from a summary with the diagnosis already discarded - see the mechanism
#: 3 section of `docs/PROJECT-STATE.md`. The file is the evidence; the message names it.
#:
#: Under `logs/`, which is gitignored, because this is a machine-local artefact of one
#: run rather than a committed fixture. No criterion reads it: it is written for the
#: person reading the failure, and the fresh-clone rule is unaffected.
TOOLCHAIN_EVIDENCE_DIR: Final = Path("logs") / "verify" / "toolchain_green"

#: Every directory the toolchain reads, in the order it first appears above.
#:
#: Derived from `TOOLCHAIN` rather than written out a second time. A path added to a
#: command but missing from a hand-maintained list would drop out of the existence
#: check in `check_toolchain_green`, and the tool would then meet an absent directory
#: and exit 2 with "file or directory not found" - a FAIL that reads as a broken
#: environment standing exactly where a PENDING belongs.
TOOLCHAIN_ROOTS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(arg for _name, args, _max_exit in TOOLCHAIN for arg in args if arg.endswith("/"))
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


def write_toolchain_evidence(
    root: Path,
    *,
    name: str,
    args: Sequence[str],
    returncode: int | None,
    output: str,
    attempt: int,
) -> str:
    """Write one failing command's whole captured output. Returns what to say about it.

    Never raises. A gate that cannot write its evidence still has to report the verdict
    it already has, so a failure here degrades to a note in the message rather than to
    an exception that replaces a real finding with an I/O error.

    The header is not decoration: months later the useful questions about one of these
    files are which command produced it, what it exited with, and whether it was the
    first attempt or the retry - and none of those are recoverable from the body.
    """
    directory = root / TOOLCHAIN_EVIDENCE_DIR
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S_%f")
    path = directory / (stamp + "-" + name + "-attempt" + str(attempt) + ".log")
    header = (
        "# toolchain_green evidence\n"
        "# command:    " + " ".join(args) + "\n"
        "# tool:       " + name + "\n"
        "# attempt:    " + str(attempt) + "\n"
        "# returncode: " + ("timed out" if returncode is None else exit_status(returncode)) + "\n"
        "# written:    " + datetime.now(UTC).isoformat().replace("+00:00", "Z") + "\n"
        "# root:       " + str(root) + "\n"
        "#\n"
        "# Everything below is the tool's captured stdout and stderr, complete and\n"
        "# unedited. The criterion's own message quotes only the last three lines.\n"
        "\n"
    )
    body = output if output else "(the command produced no output at all)\n"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # `newline="\n"`, never a bare `write_text`: text mode on Windows would turn
        # every newline into CRLF, and a traceback is read far more often than it is
        # diffed. Lead's standing rule, 2026-09-11.
        path.write_text(header + body, encoding="utf-8", newline="\n")
    except OSError as exc:
        return "full output could NOT be written (" + type(exc).__name__ + ": " + str(exc) + ")"
    return "full output: " + path.as_posix()


def _interpreter_with_toolchain(root: Path) -> tuple[str | None, list[str]]:
    """Pick an interpreter that can actually run the three commands.

    Prefers whatever is running this script; falls back to the project virtualenv
    so the gate behaves the same whether or not the operator remembered to
    activate it. The chosen interpreter is named in the criterion's message.
    """
    candidates = [sys.executable]
    for relative in ("Scripts/python.exe", "bin/python"):
        venv_python = root / ".venv" / relative
        if venv_python.is_file():
            candidates.append(str(venv_python))

    probe = (
        "import importlib.util as u, sys;"
        "missing=[m for m in ('pytest','mypy','ruff') if u.find_spec(m) is None];"
        "print(','.join(missing))"
    )
    last_missing: list[str] = ["pytest", "mypy", "ruff"]
    for candidate in candidates:
        try:
            done = subprocess.run(  # fixed argv, never a shell
                [candidate, "-c", probe],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
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
    """One toolchain command. `None` as the returncode means it timed out.

    The encoding is named rather than inherited, and `errors="replace"` is not
    decoration. `text=True` alone decodes the child's bytes with whatever
    `locale.getencoding()` returns for *this* process, which makes the gate's output
    depend on the operator's console codepage: under the default Windows locale a
    UTF-8 byte from a tool mojibakes silently, and under `PYTHONUTF8=1` or `-X utf8`
    a cp1252 byte raises `UnicodeDecodeError` **on the reader thread**, where
    `subprocess.run` cannot propagate it - so it returns empty stdout *and* empty
    stderr and the criterion reports a FAIL with `(no output)` where the list of
    failing tests should be. That was observed on 2026-09-10: pytest emitted an
    em-dash as byte 0x97 and every line of the diagnosis was lost. A gate that
    reports a verdict it cannot explain is the thing "never pipe this through
    `tail`" exists to prevent, so the decode is now deterministic and lossy in the
    one direction that keeps the text readable.
    """
    try:
        done = subprocess.run(  # fixed argv, never a shell
            [interpreter, *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SUBPROCESS_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired as timeout:
        # Whatever the command managed to print before the deadline is kept. A timeout
        # used to return empty output, so the one failure mode where you most want to
        # know how far the run got - which test was executing when it hung - reported
        # nothing at all.
        return None, _as_text(timeout.stdout) + _as_text(timeout.stderr)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def _as_text(stream: object) -> str:
    """A `TimeoutExpired`'s captured stream as text, whichever form it arrived in."""
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="replace")
    return str(stream)


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
    absent = [root for root in TOOLCHAIN_ROOTS if not (ctx.root / root).is_dir()]
    if absent:
        # PENDING, not FAIL. These are the *subjects*, and a subject that does not
        # exist yet is the ordinary state of an early phase. Handing an absent
        # directory to ruff or mypy is exit 2 and "file or directory not found",
        # which reads as a broken environment rather than as work not yet done.
        return pending("does not exist yet: " + ", ".join(absent))

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
            evidence = write_toolchain_evidence(
                ctx.root, name=name, args=args, returncode=None, output=output, attempt=1
            )
            failures.append(
                name + " timed out after " + str(SUBPROCESS_TIMEOUT_S) + "s - " + evidence
            )
            continue
        if returncode == 0:
            continue
        # Everything from here on is a failure of some kind, and every one of them
        # deposits the whole captured output before the message is reduced to a line.
        evidence = write_toolchain_evidence(
            ctx.root, name=name, args=args, returncode=returncode, output=output, attempt=1
        )
        if 0 <= returncode <= tool_max_exit:
            # A verdict. Not retried, at any exit code, ever.
            failures.append(
                describe_exit(name, returncode, output, tool_max_exit) + " - " + evidence
            )
            continue

        # A crash. One retry, and only one - this branch is straight-line and there is
        # no path back into it for the same command.
        first = describe_exit(name, returncode, output, tool_max_exit) + " - " + evidence
        returncode, output = _run_tool(interpreter, args, ctx.root, env)
        if returncode is None:
            crashed = True
            failures.append(
                first
                + "; the retry then timed out after "
                + str(SUBPROCESS_TIMEOUT_S)
                + "s - "
                + write_toolchain_evidence(
                    ctx.root,
                    name=name,
                    args=args,
                    returncode=None,
                    output=output,
                    attempt=2,
                )
            )
            continue
        if returncode == 0:
            # Clean on the retry. PASS, but the crash is named in the message: a
            # mitigated fault that stops being reported stops being a known risk.
            survived.append(first + "; the retry was clean")
            continue
        retry_evidence = write_toolchain_evidence(
            ctx.root, name=name, args=args, returncode=returncode, output=output, attempt=2
        )
        if not (0 <= returncode <= tool_max_exit):
            crashed = True
            failures.append(
                first
                + "; the retry crashed too - "
                + describe_exit(name, returncode, output, tool_max_exit)
                + " - "
                + retry_evidence
            )
            continue
        # The retry produced a verdict, so there is something to report about the
        # code itself. That verdict stands on its own and the crash is context.
        failures.append(
            describe_exit(name, returncode, output, tool_max_exit)
            + " - "
            + retry_evidence
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


#: When this process began, as a POSIX timestamp. A workspace created before this
#: instant cannot belong to this run; one created after it may belong to anybody.
#: Captured at import so it is fixed for the life of the process, and captured
#: *before* the first sweep so a workspace this run is about to mint cannot predate it.
PROCESS_STARTED_AT = time.time()

#: A minute of slack on either side of that instant. Temp-directory mtimes come from
#: the filesystem's clock and `time.time()` from the system's, and on Windows they are
#: not guaranteed to agree to better than a couple of seconds; FAT-derived filesystems
#: are coarser still. The cost of being too generous is a leftover directory surviving
#: one extra run. The cost of being too tight is deleting a live database, which is the
#: bug this whole mechanism just caused. The asymmetry decides the number.
SWEEP_SAFETY_MARGIN_S = 60.0


def sweep_stale_workspaces(*, report: bool = True) -> tuple[int, int]:
    """Remove `acsoe-verify-*` leftovers **from runs that finished before this one
    started**. Returns (removed, bytes).

    ## What this used to say, and why it was the defect

    > Best effort throughout: a directory another verify run is using right now simply
    > will not delete, and that is fine - it is swept by whichever run goes last.

    That is a POSIX assumption written as a fact about Windows, and it was wrong in
    both directions at once. Windows does refuse to unlink an *open* file - but **a
    SQLite database between connections is not open**, and every criterion here seeds,
    closes and reopens, so it is unlocked for that whole window. And `ignore_errors=True`
    does not stop at what it cannot remove: it deletes everything it can and skips the
    rest, so partial deletion was *guaranteed* rather than possible.

    Hence two signatures and one bug. Directory gone before the next connection opens
    gives `unable to open database file`. Directory surviving with its database deleted
    gives a **fresh empty database** from `sqlite3.connect` and then
    `no such table: equity_snapshots`. Both were misread for two phases as this
    machine's intermittent native fault, because the standing mitigation - re-run the
    named test in isolation - passes every time: in isolation nothing else is sweeping.

    The concurrency needed is this project's normal state. `tests/verify/test_runner.py`
    calls `main()` nine times, so one `pytest tests/` sweeps nine times, and three
    agents each running the suite is three of those at once.

    ## What it does now

    Only directories whose mtime predates :data:`PROCESS_STARTED_AT` by more than
    :data:`SWEEP_SAFETY_MARGIN_S` are removed. A run that has not finished has, by
    definition, written to its workspace since this process started - so its directory
    cannot be older than this process, and cannot be selected. No lock file, no
    inter-process protocol: the ordering is the whole argument.

    `ignore_errors=True` is kept, and now means what the old docstring wrongly claimed.
    Everything reaching `rmtree` has already been established as nobody's, so a failure
    to remove one is a genuine best-effort miss - a virus scanner holding a handle, say -
    and the next run gets it. What it is no longer doing is deciding *whether* a
    directory is safe to delete by trying and seeing what happens.

    Deliberately scoped to the exact prefix this script mints. It never touches
    `pytest-of-*`, which belongs to pytest, or anything else in the temp directory.

    ## What this guarantees, and what it does not

    **Guaranteed:** a workspace belonging to a run that started before this call and has
    not yet finished is never removed, whether or not any file in it is open. That is
    the property the old code got wrong, and it holds on Windows and POSIX alike because
    it rests on timestamps rather than on file locking.

    **Not guaranteed, deliberately:** that every stale leftover goes. A directory whose
    mtime cannot be read is kept; one another process holds open is kept; one written to
    within :data:`SWEEP_SAFETY_MARGIN_S` of this process's start is kept. Each is
    collected by a later run. The two errors are not symmetric and the function is tuned
    for the one that matters: keeping a leftover one run too long costs disk, deleting a
    live database costs a wrong verdict on a gate that decides whether real money trades.

    **Never relied upon:** that an open file cannot be deleted. It is true of an open
    file on Windows and it is not true of a *SQLite database between connections*, which
    is the state every criterion here spends most of its time in. Nothing in this
    function's correctness depends on the filesystem refusing anything.
    """
    root = Path(tempfile.gettempdir())
    cutoff = PROCESS_STARTED_AT - SWEEP_SAFETY_MARGIN_S
    removed = 0
    freed = 0
    try:
        entries = sorted(root.glob(WORKSPACE_PREFIX + "*"))
    except OSError:
        return 0, 0
    for entry in entries:
        # Per entry, not around the loop. An entry that will not stat used to abort the
        # whole sweep, so one unreadable leftover silently stopped every workspace after
        # it alphabetically from being cleaned up - the leak this function exists to
        # prevent, reintroduced by its own error handling.
        with contextlib.suppress(OSError):
            if not entry.is_dir():
                continue
            if not _predates_this_run(entry, cutoff):
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


def _predates_this_run(entry: Path, cutoff: float) -> bool:
    """Whether `entry` was last written to before this process could have touched it.

    The **newest** mtime anywhere inside it, not the directory's own. A directory's
    mtime changes when an entry is added or removed from it and not when a file inside
    is written, so a workspace whose database is being written to right now can carry a
    directory mtime from the moment it was created. Reading only that would have left
    the bug exactly where it was for any run longer than the margin.

    Unreadable means not ours: an entry that cannot be stat'ed is one we know nothing
    about, and the safe answer to "may I delete this" is no.
    """
    newest = 0.0
    try:
        newest = entry.stat().st_mtime
        for child in entry.rglob("*"):
            with contextlib.suppress(OSError):
                newest = max(newest, child.stat().st_mtime)
    except OSError:
        return False
    return newest < cutoff


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
    parameters: Mapping[str, inspect.Parameter]
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
    """What a WebSocket probe saw. `accepted` False means there is no endpoint.

    `pushed_unprompted` is the observation that makes `pushed` mean anything. A
    console that pushes on a timer regardless of the data satisfies "a push arrived"
    and is wrong - the operator would get a screen that refreshes constantly and
    tells them nothing about whether anything changed. So the probe watches a quiet
    window *before* touching the database, and a push there is a failure rather than
    an early success.
    """

    accepted: bool
    pushed: bool
    elapsed_ms: float
    detail: str
    pushed_unprompted: bool = False


async def _probe_websocket(
    app: Any, path: str, *, on_open: Callable[[], None], quiet_s: float, budget_s: float
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
        except TimeoutError:
            return WsProbe(False, False, 0.0, "the application never answered the handshake")
        if first.get("type") != "websocket.accept":
            return WsProbe(False, False, 0.0, "handshake answered with " + str(first.get("type")))

        # The quiet window: connected, nothing sent by this client, nothing changed
        # in the database. A polling console must poll through this and say nothing.
        # Waiting *longer* here only makes the check stricter, so a loaded machine
        # cannot turn this into a spurious failure - it can only fail to notice a
        # console that pushes on a timer, which is a missed detection rather than a
        # false accusation, and the fabricated console in `tests/verify/` catches
        # that case deterministically on an idle machine.
        quiet_started = time.monotonic()
        while True:
            remaining = quiet_s - (time.monotonic() - quiet_started)
            if remaining <= 0:
                break
            try:
                message = await asyncio.wait_for(outbound.get(), timeout=remaining)
            except TimeoutError:
                break
            if message.get("type") == "websocket.send":
                return WsProbe(
                    True,
                    False,
                    (time.monotonic() - quiet_started) * 1000,
                    "pushed before anything changed",
                    pushed_unprompted=True,
                )
            if message.get("type") == "websocket.close":
                return WsProbe(True, False, 0.0, "the endpoint closed the socket")

        on_open()
        started = time.monotonic()
        while True:
            remaining = budget_s - (time.monotonic() - started)
            if remaining <= 0:
                return WsProbe(True, False, budget_s * 1000, "nothing was pushed")
            try:
                message = await asyncio.wait_for(outbound.get(), timeout=remaining)
            except TimeoutError:
                return WsProbe(True, False, budget_s * 1000, "nothing was pushed")
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


def probe_websocket(
    app: Any, path: str, *, on_open: Callable[[], None], quiet_s: float, budget_s: float
) -> WsProbe:
    return asyncio.run(
        _probe_websocket(app, path, on_open=on_open, quiet_s=quiet_s, budget_s=budget_s)
    )


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
    """A push arrives **because** the database changed, and not otherwise.

    Three jobs, three mechanisms, and separating them is the point - they used to be
    one number doing all three badly.

    **The assertion is behavioural.** The socket stays quiet through a window in
    which nothing changed, and then pushes once something does. The client sends
    nothing at any point, so every push is unprompted. That pair is the property
    `ui-context.md` actually specifies: the console pushes *when the watermark
    moves*. A console that pushes on a timer regardless satisfies "a push arrived"
    and is wrong in a way an operator would feel - a screen that refreshes forever
    and never means anything.

    **The timeout is a safety net and nothing more.** Twenty poll intervals, so a
    broken console fails in finite time rather than hanging the gate. It is not a
    promptness assertion and must not read like one: it used to be *two* intervals,
    which is a factor of two of headroom measured on a machine also running the rest
    of the suite, and it went red once under a full run while passing three times in
    isolation. That budget was measuring the machine, not the console. The
    interesting property was never "within 1000ms" anyway - a console that polls on
    an interval is at most one interval late by construction, so the tight bound was
    standing in for "the poll loop is running", which the quiet window now
    demonstrates directly.

    **The evidence is the measured time in the message.** A promptness regression
    stays visible in gate output - "pushed 508ms after the watermark moved" - without
    being a spurious FAIL on a loaded machine.

    Both windows are read from config. `ui-context.md` makes the poll interval
    configuration, and a criterion carrying its own copy of 500 would stop testing
    the console the moment the operator retuned it.

    Changed 2026-09-10 on the lead's ruling. **This is a Phase 1 criterion and this
    is a Phase 3 change to it**, which is worth justifying rather than slipping in:
    the old form was a wall-clock assertion that had begun failing intermittently,
    and loosening its number inside an unrelated spec is how such an assertion ends
    up asserting nothing. Replacing it with the property it was standing in for is
    the alternative, and it is strictly stronger - the old form could not tell a
    console that pushes on change from one that pushes constantly.
    """
    config_data, problem = load_config(ctx.root)
    if config_data is None:
        return problem or pending("config/default.yaml does not exist yet")
    poll_ms = config_get(config_data, KEY_POLL_INTERVAL)
    if poll_ms is _CONFIG_MISSING:
        return pending("config key `" + KEY_POLL_INTERVAL + "` is not defined yet")
    if poll_ms is None:
        return pending("the operator has not set `" + KEY_POLL_INTERVAL + "`")
    #: Two poll intervals of silence, so a polling console has certainly polled at
    #: least once and chosen not to push. This is the assertion's half.
    quiet_ms = int(poll_ms) * 2
    #: Twenty, so a dead poller fails in finite time. This is the safety net's half
    #: and carries no claim about promptness.
    timeout_ms = int(poll_ms) * 20

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
                app,
                "/ws",
                on_open=move_the_watermark,
                quiet_s=quiet_ms / 1000,
                budget_s=timeout_ms / 1000,
            )
        finally:
            close_console(app)

    if not probe.accepted:
        return pending(
            "no WebSocket endpoint at /ws yet - " + probe.detail + " (" + CONSOLE_CONTRACT + ")"
        )
    if probe.pushed_unprompted:
        return failed(
            "the console pushed "
            + format(probe.elapsed_ms, ".0f")
            + "ms after connecting, with nothing changed in the database and nothing "
            "sent by the client. It is pushing on a timer rather than on the watermark, "
            "which satisfies `a push arrived` and still leaves the operator watching a "
            "screen that refreshes forever and means nothing."
        )
    if not probe.pushed:
        return failed(
            "the watermark moved and nothing was pushed. The socket was open, the "
            "client sent nothing to provoke it, and it stayed silent for "
            + str(timeout_ms)
            + "ms - twenty times `"
            + KEY_POLL_INTERVAL
            + "`="
            + str(poll_ms)
            + ", which is a dead poller rather than a slow one: "
            + probe.detail
        )
    return passed(
        "silent through "
        + str(quiet_ms)
        + "ms with nothing changed, then pushed "
        + format(probe.elapsed_ms, ".0f")
        + "ms after the watermark moved"
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
# RUF001 is correct that the character is ambiguous and would be destructive to obey.
# U+2212 is the glyph `ui-context.md` rule 6 *requires* in numeric output, and this
# pattern is what recognises it; replacing it with an ASCII hyphen would make the check
# accept the exact character it exists to reject. Same shape as the standing example in
# `code-standards.md`, where `tests/console/test_format.py` binds the same glyph.
_NUMERIC_TEXT = re.compile("^[+−-]?[0-9][0-9\\s.,:]*%?$")  # noqa: RUF001


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

    def process(self, context: Any, state: Any) -> Any:  # noqa: ARG002 - fixed engine interface
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
    """The `commands` row the store has just written, read back through raw SQLite.

    A missing row means the store handed back an id for something it did not write.
    That is a defect in the store rather than in the command under test, so it is
    named here: every caller indexes the result immediately, and without this the
    absence arrives three frames away as `'NoneType' object is not subscriptable`,
    naming neither the command nor the table.
    """
    conn = sqlite3.connect(db_path)
    row: sqlite3.Row | None
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise LookupError(
            "the store returned command id " + str(command_id) + " but `commands` has no "
            "such row"
        )
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

#: The floor on how much of the span was actually recorded, 0.0 to 1.0.
#:
#: **The span alone does not say the recorder survived the day, and until 2026-09-10
#: this criterion could not tell the difference.** A 24-hour span with eleven hours of
#: accounted holes and a 24-hour span with none tile identically, carry causes
#: identically, and passed identically - the check measured start-to-end elapsed time,
#: which made the word *continuous* in the phase row do no work at all. The first real
#: archive would have PASSed at 10.93h recorded of a 22.16h span: a recorder that was
#: down a quarter of the time, reporting success.
#:
#: 0.98 of 24h leaves roughly 29 minutes. That is generous for what it must tolerate -
#: the observed clean run lost 15 seconds across nine websocket reconnects, which is
#: 0.9998 - and still far too tight for an outage anybody would care about. The gap
#: between 0.9998 and 0.98 is the margin; the gap between 0.98 and 0.76 is the defect.
#:
#: Operator's decision, 2026-09-10. A threshold on this is trading-adjacent - it decides
#: what evidence the cost model is allowed to rest on - so it is not the lead's to pick.
MIN_RECORDED_FRACTION = 0.98

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

    **And the tiling is not enough on its own.** Accounting for a break is not the same
    as not having one: a report can tile perfectly, name a cause for every hole, and
    still describe a recorder that was down for a quarter of the day. So the span must
    also be at least `MIN_RECORDED_FRACTION` actually recorded. That floor was added on
    2026-09-10, after the first real archive would have passed at 49% recorded.
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

    totals = report.get("totals")
    fraction = totals.get("recorded_fraction") if isinstance(totals, Mapping) else None
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool):
        return pending(
            "the report carries no numeric `totals.recorded_fraction` - "
            + RECORDING_REPORT_CONTRACT
        )
    if fraction < MIN_RECORDED_FRACTION:
        return failed(
            f"only {fraction:.1%} of the span was actually recorded, and the floor is "
            f"{MIN_RECORDED_FRACTION:.0%}. The span tiles and every break carries a "
            "cause, so this report is honest - it is the recording that is not good "
            "enough. This fixture exists to prove the recorder survives a day, and a "
            "run that was down for the rest of it proves the opposite."
        )

    hours = (span_end - span_start) / 3_600_000_000
    return passed(
        f"{hours:.1f}h span tiled exactly by {len(segments_raw)} recorded segment(s) and "
        f"{len(gaps_raw)} accounted break(s); every break carries a cause; "
        f"{fraction:.2%} of the span actually recorded, floor {MIN_RECORDED_FRACTION:.0%}"
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


def _guard_state(contracts_mod: ModuleType, scenarios: Mapping[str, Any], key: str) -> Any:
    """One scenario's `state`, as a copy nothing else shares.

    `BAD_DATA_SCENARIOS` is a module-level mapping of mappings, so `dict(...)` copies
    the outer dict and leaves every nested region - `state["market_sensor"]`,
    `state["exchange"]` - pointing at the *same object* as the fixture. Nothing here
    mutates one today. A found it the hard way on his own side, where a test set a
    nested key and quietly changed the fixture for every test after it, and the
    failure surfaced somewhere unrelated.

    An engine is also entitled to publish into `state` under its own name, which is
    how engines communicate at all, so "nothing mutates it" is a property of today's
    engine 4 rather than of the contract.

    A's `bad_data_state(name)` returns a fresh deep copy and is preferred when it is
    there; `copy.deepcopy` is the fallback, so this criterion keeps working against
    a `contracts.py` that only exposes the mapping.
    """
    builder = getattr(contracts_mod, "bad_data_state", None)
    if callable(builder):
        return builder(key)
    return copy.deepcopy(scenarios[key])


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
                state = _guard_state(contracts_mod, scenarios, key)
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

            clean = engine.process(
                context, _guard_state(contracts_mod, scenarios, GUARD_CLEAN_SCENARIO)
            )
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
# Phase 3 - the economics gates. Spec 45.
# --------------------------------------------------------------------------- #
#
# Seven criteria for engines 7 `scout`, 10 `cost`, 11 `risk` and 17 `safety`.
# Registered first in the phase, before three of the four subjects are wired, for
# the reason spec 00 came first in Phase 0 and spec 16 first in Phase 1: until they
# exist, `--phase 3` registers `docs_vocabulary` and `toolchain_green` alone and
# prints "Phase 3 is green: every criterion PASS, zero PENDING" over a phase whose
# engines are unbuilt. It printed exactly that on 2026-09-10. PENDING is what stops
# an empty phase looking finished, and a criterion has to exist to report it.
#
# Three rules shape all seven, and the first is the one this phase exists to enforce.
#
# **Fabricate the subject a criterion judges. Never fabricate a contract it is held
# to.** The Phase 3 audit found engines 10 and 11 reading a `state["exchange"]` that
# engine 1 does not publish - `exchange.fees.maker_pct` against engine 1's
# `exchange.fee_tier.maker_fee_pct`, and three more - which survived a whole phase
# because every test built that payload by hand and therefore agreed with its caller.
# A criterion built the same way repeats that defect one level up, where it would be
# harder to see and would be believed. So: `state["exchange"]` here is always the
# real `ExchangeEngine`'s own output over the fake Kraken client, never a literal;
# every state key and field name is imported from the engine's real `contracts.py`
# rather than retyped; and where a subject genuinely does not exist yet - engines 8
# and 9 are Phase 5, engine 7 is unwritten - the *payload* is fabricated while the
# *key it lands under* still comes from the real contract.
#
# **No criterion may read `data/`, `logs/` or `models/`, need the network, or need a
# key.** All three directories are gitignored, so a criterion depending on one cannot
# pass on a fresh clone. Exchange values come from the fake client over the committed
# `tests/fixtures/kraken/` envelopes; store values come from the Phase 0 seed written
# into a temporary directory.
#
# **Nothing here may depend on a live engine 19 `memory`.** Every one of `safety`'s
# six inputs is written by engine 19, which is Phase 4. The Phase 0 seed exists to
# resolve that forward dependency and criteria 4, 5 and 6 read it.

#: The four engines this phase is about, with the spec that lands each one. Used in
#: PENDING messages so a waiting criterion names who is building its subject.
PHASE3_ENGINES: Final[Mapping[str, tuple[int, str]]] = {
    "scout": (7, "spec 43 and 44"),
    "cost": (10, "spec 40"),
    "risk": (11, "spec 41"),
    "safety": (17, "spec 42"),
}

#: `state["exchange"]` is only ever engine 1's own output. Named so the PENDING line
#: says which engine a criterion is waiting on rather than "a module is missing".
EXCHANGE_ENGINE_CONTRACT = (
    "expected: acsoe.engines.exchange.engine.ExchangeEngine, whose EngineResult.data "
    "is `state['exchange']`. No criterion here hand-builds that payload - the Phase 3 "
    "audit found three field names assumed wrong under it, and every test that could "
    "have caught it had built the payload itself"
)

SCOUT_CONTRACT = (
    "expected: acsoe.engines.scout.engine exposing the BaseEngine subclass with "
    "name == 'scout', publishing a per-tick universe into state['scout'] whose size "
    "responds to the quote-currency balance engine 1 reports, and "
    "acsoe.engines.scout.contracts declaring the universe key and the exclusion "
    "reason codes. The universe is read from the published payload, never counted by "
    "this criterion, because a count this criterion computes is a count engine 7 is "
    "not held to"
)


def _phase3_config() -> tuple[Any, Outcome | None]:
    """The committed config, through the shared test double.

    The same loader `console_config` uses, called directly rather than through it
    because nothing here is about the console and a reader should not have to check
    whether `console_config()` does something console-shaped on the way.
    """
    module, problem = try_import("tests.harness.doubles")
    if module is None:
        return None, problem
    loader, missing = module_attr(module, "load_default_config")
    if loader is None:
        return None, pending("test doubles unavailable: " + missing)
    return loader(), None


def _fake_kraken() -> tuple[Any, Outcome | None]:
    """C's fake Kraken client over the committed envelopes. Never the network."""
    module, problem = try_import("tests.harness.fake_kraken")
    if module is None:
        return None, problem
    cls, missing = module_attr(module, "FakeKrakenClient")
    if cls is None:
        return None, pending("test harness unavailable: " + missing)
    return cls(), None


def _fake_clients(kraken: Any = None, store: Any = None) -> tuple[Any, Outcome | None]:
    module, problem = try_import("tests.harness.doubles")
    if module is None:
        return None, problem
    cls, missing = module_attr(module, "FakeClients")
    if cls is None:
        return None, pending("test doubles unavailable: " + missing)
    clients = cls()
    if kraken is not None:
        clients.kraken = kraken
    if store is not None:
        clients.store = store
    return clients, None


#: A fixed instant. Every criterion here injects its clock; none reads the wall clock,
#: so two runs a week apart produce the same verdict.
PHASE3_NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def _engine_context(
    config: Any, clients: Any, *, run_id: str = "verify-phase-3", now: datetime | None = None
) -> tuple[Any, Outcome | None]:
    """The real `EngineContext`, or `None` if `core/` is not there yet.

    Deliberately the real one. `check_data_guard_blocks_bad_data` once fabricated an
    `EngineContext` with a `cycle_id` field that does not exist and no `mode`, its
    body never executed, and both halves of its two-sided proof passed anyway
    because the fabricated contract agreed with the mistake.
    """
    core_mod, problem = try_import("acsoe.core.contracts")
    if core_mod is None:
        return None, problem or pending("acsoe.core.contracts does not exist yet")
    cls, missing = module_attr(core_mod, "EngineContext")
    if cls is None:
        return None, pending(missing)
    return cls(
        mode="paper",
        run_id=run_id,
        now=PHASE3_NOW if now is None else now,
        config=config,
        clients=clients,
    ), None


def _engine_absent(problem: Outcome | None, engine: str) -> Outcome:
    """The PENDING an absent Phase 3 engine reports, naming the spec that lands it.

    `problem or pending(...)` is the wrong shape here and it cost two tests: `try_import`
    already returns a PENDING reading "acsoe.engines.safety.contracts does not exist
    yet", which is truthy, so it won and the spec number never reached the operator. A
    FAIL still wins, because a broken environment is a broken environment and whose spec
    it is beside the point.
    """
    if problem is not None and problem.result is Result.FAIL:
        return problem
    number, spec = PHASE3_ENGINES[engine]
    return pending(f"engine {number} `{engine}` does not exist yet ({spec})")


def _engine_class(module_name: str, engine: str) -> tuple[Any, Outcome | None]:
    """The `BaseEngine` subclass named `engine`, or the PENDING that says who owns it."""
    number, spec = PHASE3_ENGINES[engine]
    module, problem = try_import(module_name)
    if module is None:
        if problem is not None and problem.result is Result.FAIL:
            return None, problem
        return None, pending(f"engine {number} `{engine}` does not exist yet ({spec})")
    cls = _engine_named(module, engine)
    if cls is None:
        return None, pending(f"{module_name} exposes no class with name == {engine!r}")
    return cls, None


def _exchange_payload(
    config: Any, fake: Any
) -> tuple[Mapping[str, Any] | None, Any, Outcome | None]:
    """Run the real engine 1 over `fake` and return what it publishes.

    Returns (payload, context, early outcome). The context is returned with it
    because the gates under test are handed the same one - a criterion that built a
    second context could hand the gate a different clock or a different config from
    the one that produced the payload it is judging.
    """
    clients, problem = _fake_clients(kraken=fake)
    if clients is None:
        return None, None, problem
    context, problem = _engine_context(config, clients)
    if context is None:
        return None, None, problem
    module, problem = try_import("acsoe.engines.exchange.engine")
    if module is None:
        return None, None, _with_contract(
            problem, "engine 1 `exchange` does not exist yet", EXCHANGE_ENGINE_CONTRACT
        )
    engine_cls = _engine_named(module, "exchange")
    if engine_cls is None:
        return None, None, pending(
            "acsoe.engines.exchange.engine exposes no class with name == 'exchange' - "
            + EXCHANGE_ENGINE_CONTRACT
        )
    result = engine_cls().process(context, {})
    payload = result.data
    if not isinstance(payload, Mapping):
        return None, None, failed(
            "engine 1 published " + type(payload).__name__ + " rather than a mapping; "
            "`state['exchange']` is what every gate in this phase reads"
        )
    return payload, context, None


def _tradable_pair(
    exchange: Mapping[str, Any], contracts_mod: ModuleType
) -> tuple[str | None, Mapping[str, Any] | None, str]:
    """A pair engine 1 published, whose quote currency the account actually holds.

    Chosen from engine 1's output rather than written down here. A criterion naming
    `BTC/USD` would keep passing after that pair left the fixtures and would be
    testing the fixture rather than the gate; and `risk` needs a pair whose quote
    currency has a balance, which is a fact about the payload, not about the symbol.
    """
    rules_key = getattr(contracts_mod, "EXCHANGE_PAIR_RULES_KEY", "pair_rules")
    pairs_field = getattr(contracts_mod, "PAIR_RULES_PAIRS_FIELD", "pairs")
    quote_field = getattr(contracts_mod, "PAIR_QUOTE_FIELD", "quote")
    balances_key = getattr(contracts_mod, "EXCHANGE_BALANCES_KEY", "balances")

    rules = exchange.get(rules_key)
    if not isinstance(rules, Mapping):
        return None, None, f"engine 1 published no {rules_key!r}"
    pairs = rules.get(pairs_field)
    if not isinstance(pairs, Mapping) or not pairs:
        return None, None, f"engine 1 published no {rules_key}.{pairs_field}"
    balances = exchange.get(balances_key)
    held = set(balances) if isinstance(balances, Mapping) else set()

    for name in sorted(pairs):
        rule = pairs[name]
        if isinstance(rule, Mapping) and str(rule.get(quote_field, "")) in held:
            return str(name), rule, ""
    return None, None, (
        "engine 1 published no pair whose quote currency appears in "
        f"{balances_key}; `risk` cannot size a pair the account cannot pay for"
    )


def _quote_payload(pair: str, *, bid: str, ask: str, spread_pct: str) -> tuple[Any, Outcome | None]:
    """One top-of-book quote, built through engine 3's **real** `QuoteView`.

    Engine 3 exists, but its quotes come from a WebSocket stream the fake client
    deliberately does not have - `_quotes` returns `{}` for any client with no
    `recent_trades`, so there is no way to drive a real spread out of it offline.
    The subject is therefore fabricated and the contract is not: the model, its field
    names and its serialisation are engine 3's own, so a criterion cannot invent a
    quote shape engine 3 would never publish.
    """
    module, problem = try_import("acsoe.engines.market_sensor.contracts")
    if module is None:
        return None, problem or pending("acsoe.engines.market_sensor.contracts does not exist yet")
    cls, missing = module_attr(module, "QuoteView")
    if cls is None:
        return None, pending(missing)
    view = cls(
        pair=pair,
        ts=PHASE3_NOW.isoformat().replace("+00:00", "Z"),
        bid=Decimal(bid),
        ask=Decimal(ask),
        spread=Decimal(ask) - Decimal(bid),
        spread_pct=Decimal(spread_pct),
        age_s=1.0,
    )
    return view.state_dict(), None


# --- cost_gate_uses_live_fee_tier ------------------------------------------ #

#: Two fee tiers far enough apart that the same candidate clears the hurdle under one
#: and is refused under the other. Both are invented test data for a fake exchange and
#: neither is a claim about Kraken's schedule - `AGENTS.md` rule 1: any remembered fee
#: percentage is stale and must never be written into code. Nothing outside this
#: criterion reads them, and the *engine* still gets its rates from the client.
CHEAP_TIER = ("0.0005", "0.0010")
EXPENSIVE_TIER = ("0.0025", "0.0045")

#: The three numbers the cost gate needs that no Phase 3 engine publishes. Engine 8
#: `prediction` and engine 9 `order_book` are Phase 5 and are C's own; the spread is
#: engine 3's, which cannot be driven offline. Chosen so the *cheap* tier clears and
#: the *expensive* tier does not: with `trading.hurdle_multiple` at 1.5 a candidate
#: clears when `move > 2.5 x friction`, which 0.0100 does against the cheap tier's
#: 0.0025 friction and does not against the expensive tier's 0.0080.
CANDIDATE_MOVE_PCT = "0.0100"
CANDIDATE_SLIPPAGE_PCT = "0.0005"
CANDIDATE_SPREAD_PCT = "0.0005"


def _cost_state(
    exchange: Mapping[str, Any], contracts_mod: ModuleType, pair: str, quote: Any
) -> dict[str, Any]:
    """`state` as the opportunity chain would have it when engine 10 runs.

    Every key comes from `cost/contracts.py`. That is the whole point: the audit's
    four defects were all a *name* under `state["exchange"]`, and a criterion that
    retyped those names would agree with whichever version of the engine it was
    written against instead of catching the next disagreement.
    """
    scout_key, pair_field = contracts_mod.CANDIDATE_PAIR_PATH
    return {
        contracts_mod.EXCHANGE_KEY: dict(exchange),
        scout_key: {pair_field: pair},
        contracts_mod.MARKET_SENSOR_KEY: {
            contracts_mod.MARKET_SENSOR_QUOTES_KEY: {pair: quote}
        },
        contracts_mod.PREDICTION_KEY: {"expected_move_pct": CANDIDATE_MOVE_PCT},
        contracts_mod.ORDER_BOOK_KEY: {"estimated_slippage_pct": CANDIDATE_SLIPPAGE_PCT},
    }


def _cost_tick(
    config: Any, contracts_mod: ModuleType, engine_cls: Any, maker: str, taker: str
) -> tuple[Any, str, Outcome | None]:
    """One `cost` tick against a fee tier the fake client reports. Returns (result, pair)."""
    fake, problem = _fake_kraken()
    if fake is None:
        return None, "", problem
    fake.set_fee_tier(tier=2, maker_fee_pct=maker, taker_fee_pct=taker)

    exchange, context, problem = _exchange_payload(config, fake)
    if exchange is None:
        return None, "", problem
    pair, _rule, why = _tradable_pair(exchange, contracts_mod)
    if pair is None:
        return None, "", failed(why)
    quote, problem = _quote_payload(
        pair, bid="99.95", ask="100.05", spread_pct=CANDIDATE_SPREAD_PCT
    )
    if quote is None:
        return None, "", problem
    state = _cost_state(exchange, contracts_mod, pair, quote)
    return engine_cls().process(context, state), pair, None


def check_cost_gate_uses_live_fee_tier(ctx: VerifyContext) -> Outcome:
    """Net edge moves with the fee tier the client reports, and the gate blocks below
    the hurdle.

    **The comparison is the criterion.** A single tick would be satisfied by an engine
    with the fee rate compiled into it, which is precisely what invariant 2 forbids and
    what `AGENTS.md` opens by warning about. So the same candidate is run twice, and
    the two net edges must differ by *exactly* the difference between the two tiers -
    not merely differ, which a gate could achieve by reading anything at all that
    happened to change.
    """
    with root_import_path(ctx.root):
        contracts_mod, problem = try_import("acsoe.engines.cost.contracts")
        if contracts_mod is None:
            number, spec = PHASE3_ENGINES["cost"]
            return _with_contract(
                problem,
                f"engine {number} `cost` does not exist yet ({spec})",
                EXCHANGE_ENGINE_CONTRACT,
            )
        engine_cls, problem = _engine_class("acsoe.engines.cost.engine", "cost")
        if engine_cls is None:
            return problem or pending("engine 10 `cost` does not exist yet")

        config, problem = _phase3_config()
        if config is None:
            return problem or pending("the committed config could not be loaded")

        cheap, pair, problem = _cost_tick(config, contracts_mod, engine_cls, *CHEAP_TIER)
        if cheap is None:
            return problem or pending("engine 10 `cost` could not be driven")
        expensive, _pair, problem = _cost_tick(
            config, contracts_mod, engine_cls, *EXPENSIVE_TIER
        )
        if expensive is None:
            return problem or pending("engine 10 `cost` could not be driven")

        unavailable = getattr(contracts_mod, "REASON_INPUTS_UNAVAILABLE", None)
        for result in (cheap, expensive):
            data = result.data or {}
            if unavailable is not None and data.get("reason_code") == unavailable:
                number, spec = PHASE3_ENGINES["cost"]
                return pending(
                    f"engine {number} `cost` is not wired to engine 1 yet ({spec}): it "
                    "answered " + repr(unavailable) + " against engine 1's own published "
                    "payload rather than reaching a net-edge comparison. Its reason: "
                    + repr(getattr(result, "reason", None))
                )

        try:
            cheap_edge = as_decimal(cheap.data["net_edge_pct"], "cost.net_edge_pct")
            dear_edge = as_decimal(expensive.data["net_edge_pct"], "cost.net_edge_pct")
        except (KeyError, TypeError) as exc:
            return failed(f"engine 10 published no usable net_edge_pct: {exc}")

        expected_gap = (
            Decimal(EXPENSIVE_TIER[0])
            + Decimal(EXPENSIVE_TIER[1])
            - Decimal(CHEAP_TIER[0])
            - Decimal(CHEAP_TIER[1])
        )
        if cheap_edge == dear_edge:
            return failed(
                "the net edge did not move when the fee tier did: both tiers produced "
                f"{cheap_edge}. The gate is not reading the fee tier the client "
                "reported, and invariant 2 says a fee is never a constant."
            )
        if cheap_edge - dear_edge != expected_gap:
            return failed(
                "the net edge moved by "
                + str(cheap_edge - dear_edge)
                + " when the fee tier moved by "
                + str(expected_gap)
                + ". Something other than the reported fee is feeding the arithmetic."
            )
        if not bool(cheap.data.get("clears_hurdle")):
            return failed(
                "the candidate did not clear the hurdle on the cheap tier "
                f"(net edge {cheap_edge}, hurdle {cheap.data.get('hurdle_pct')}). A gate "
                "that refuses everything proves nothing about the fee tier."
            )
        if bool(expensive.data.get("clears_hurdle")):
            return failed(
                "the candidate still cleared the hurdle on the expensive tier "
                f"(net edge {dear_edge}, hurdle {expensive.data.get('hurdle_pct')}); the "
                "gate does not block below the hurdle."
            )
        if not getattr(expensive, "blocks_trading", False):
            return failed(
                "engine 10 reported the hurdle uncleared and still did not block the "
                "tick. Invariant 5: a candidate that does not clear the hurdle is refused."
            )

    return passed(
        f"{pair}: net edge {cheap_edge} at maker/taker {CHEAP_TIER[0]}/{CHEAP_TIER[1]} and "
        f"{dear_edge} at {EXPENSIVE_TIER[0]}/{EXPENSIVE_TIER[1]}, moving by exactly the "
        f"{expected_gap} fee difference; the cheap tier clears the hurdle and the "
        "expensive tier is blocked"
    )


# --- risk_rejects_sub_ordermin --------------------------------------------- #


def _risk_tick(
    config: Any,
    risk_contracts: ModuleType,
    cost_contracts: ModuleType,
    engine_cls: Any,
    store_cls: Any,
    db_path: Path,
    *,
    ordermin: str | None,
) -> tuple[Any, str, Mapping[str, Any], Outcome | None]:
    """One `risk` tick, optionally with the pair's `ordermin` overridden on the client.

    The override goes on the **fake exchange**, not into `state`. `ordermin` is an
    `AssetPairs` value and invariant 2 makes it a runtime fetch rather than a constant,
    so a criterion that injected it into the payload would be exercising a path no live
    tick takes - and would keep passing if `risk` stopped reading the pair rules at all.
    """
    fake, problem = _fake_kraken()
    if fake is None:
        return None, "", {}, problem
    if ordermin is not None:
        # Which pair gets chosen depends only on engine 1's fixtures and the balances,
        # and the override touches neither, so it is the same pair as the first tick.
        # It is still re-read below rather than assumed.
        probe, _context, problem = _exchange_payload(config, fake)
        if probe is None:
            return None, "", {}, problem
        probe_pair, _rule, why = _tradable_pair(probe, risk_contracts)
        if probe_pair is None:
            return None, "", {}, failed(why)
        ordermin_field = getattr(risk_contracts, "PAIR_ORDERMIN_FIELD", "ordermin")
        fake.set_pair_rule(probe_pair, **{ordermin_field: ordermin})

    with store_cls(db_path) as store:
        clients, problem = _fake_clients(kraken=fake, store=store)
        if clients is None:
            return None, "", {}, problem
        context, problem = _engine_context(config, clients)
        if context is None:
            return None, "", {}, problem
        module, problem = try_import("acsoe.engines.exchange.engine")
        if module is None:
            return None, "", {}, _with_contract(
                problem, "engine 1 `exchange` does not exist yet", EXCHANGE_ENGINE_CONTRACT
            )
        exchange_cls = _engine_named(module, "exchange")
        if exchange_cls is None:
            return None, "", {}, pending(
                "engine 1 `exchange` exposes no engine class - " + EXCHANGE_ENGINE_CONTRACT
            )
        exchange = exchange_cls().process(context, {}).data
        if not isinstance(exchange, Mapping):
            return None, "", {}, failed("engine 1 published no mapping into `state['exchange']`")
        pair, rule, why = _tradable_pair(exchange, risk_contracts)
        if pair is None or rule is None:
            return None, "", {}, failed(why)
        quote, problem = _quote_payload(
            pair, bid="99.95", ask="100.05", spread_pct=CANDIDATE_SPREAD_PCT
        )
        if quote is None:
            return None, "", {}, problem
        state = _cost_state(exchange, cost_contracts, pair, quote)
        return engine_cls().process(context, state), pair, rule, None


def check_risk_rejects_sub_ordermin(ctx: VerifyContext) -> Outcome:
    """A size one increment below `ordermin` is refused, and no quantity comes back.

    **The second half is the half that matters.** A criterion asserting only "no order
    was placed" passes against an implementation that quietly rounds the size *up* to
    `ordermin` and places it - which is a different trade from the one that was
    assessed, at a size nothing sized. So this asserts the returned quantity is absent,
    not merely that approval was withheld. It asserts the reason code too: this gate
    blocks for five different reasons, and "it refused" does not say the minimum
    refused it.

    `ordermin` is never written down here. The engine is asked to size the candidate
    once, and the pair's `ordermin` is then set one lot increment *above* whatever it
    sized - so the refused quantity is exactly one increment below the minimum whatever
    the sizing rules are, and the criterion cannot drift when those rules change.
    """
    with root_import_path(ctx.root):
        risk_contracts, problem = try_import("acsoe.engines.risk.contracts")
        if risk_contracts is None:
            number, spec = PHASE3_ENGINES["risk"]
            return _with_contract(
                problem,
                f"engine {number} `risk` does not exist yet ({spec})",
                EXCHANGE_ENGINE_CONTRACT,
            )
        engine_cls, problem = _engine_class("acsoe.engines.risk.engine", "risk")
        if engine_cls is None:
            return problem or pending("engine 11 `risk` does not exist yet")
        cost_contracts, problem = try_import("acsoe.engines.cost.contracts")
        if cost_contracts is None:
            return problem or pending("acsoe.engines.cost.contracts does not exist yet")
        store_cls, problem = _store_class()
        if store_cls is None:
            return problem or pending("acsoe.clients.store.client does not exist yet")
        config, problem = _phase3_config()
        if config is None:
            return problem or pending("the committed config could not be loaded")

        unavailable = getattr(risk_contracts, "REASON_INPUTS_UNAVAILABLE", None)
        lot_field = getattr(risk_contracts, "PAIR_LOT_DECIMALS_FIELD", "lot_decimals")
        below_ordermin = getattr(risk_contracts, "REASON_BELOW_ORDERMIN", "below_ordermin")

        with console_workspace() as tmp:
            db_path, early = _phase3_seeded_db(ctx, tmp)
            if db_path is None:
                return early or pending("the Phase 0 seed is not available")

            sized, pair, rule, problem = _risk_tick(
                config,
                risk_contracts,
                cost_contracts,
                engine_cls,
                store_cls,
                db_path,
                ordermin=None,
            )
            if sized is None:
                return problem or pending("engine 11 `risk` could not be driven")
            data = dict(sized.data or {})
            if unavailable is not None and data.get("reason_code") == unavailable:
                number, spec = PHASE3_ENGINES["risk"]
                return pending(
                    f"engine {number} `risk` is not wired to engine 1 yet ({spec}): against "
                    "engine 1's own published payload it answered "
                    + repr(unavailable)
                    + " rather than sizing. Its reason: "
                    + repr(getattr(sized, "reason", None))
                )
            raw_qty = data.get("qty")
            if raw_qty is None:
                return failed(
                    "engine 11 refused the candidate before `ordermin` had been tightened "
                    "at all, so there is nothing to push one increment below it. Reason: "
                    + repr(getattr(sized, "reason", None))
                )
            qty = as_decimal(raw_qty, "risk.qty")
            increment = Decimal(1).scaleb(-int(rule.get(lot_field, 8)))
            just_above = qty + increment

            refused, pair, rule, problem = _risk_tick(
                config,
                risk_contracts,
                cost_contracts,
                engine_cls,
                store_cls,
                db_path,
                ordermin=format(just_above, "f"),
            )
            if refused is None:
                return problem or pending("engine 11 `risk` could not be driven")
            rdata = dict(refused.data or {})

        if bool(rdata.get("approved")):
            return failed(
                f"engine 11 approved {rdata.get('qty')} against an `ordermin` of "
                f"{just_above}, one lot increment above it. Invariant 7: a size below the "
                "exchange minimum is not tradable."
            )
        if rdata.get("qty") is not None:
            return failed(
                "engine 11 refused the candidate and still returned a quantity of "
                + repr(rdata.get("qty"))
                + ". A rejected candidate has no size. A quantity that survives a "
                "rejection is one an executor can place, and a size rounded up to the "
                "minimum is a different trade from the one that was assessed."
            )
        if rdata.get("reason_code") != below_ordermin:
            return failed(
                "engine 11 refused for "
                + repr(rdata.get("reason_code"))
                + " rather than "
                + repr(below_ordermin)
                + ". This gate blocks for five different reasons and the criterion cannot "
                "tell it was the minimum that refused it."
            )

    return passed(
        f"{pair}: sized {qty}, then refused at an `ordermin` of {just_above} - one lot "
        f"increment ({increment}) above it - with reason {below_ordermin!r} and no "
        "quantity returned"
    )


# --- universe_varies_with_balance ------------------------------------------ #


#: A pair name no fixture carries, used to find which key `ScoutUniverse` publishes the
#: universe under. Shaped like a pair so a model that validates the field still accepts it.
UNIVERSE_PROBE_PAIR = "PROBE/USD"


def _published_pairs(
    exchange: Mapping[str, Any], contracts_mod: ModuleType
) -> Mapping[str, Any]:
    """The per-pair rules engine 1 published, addressed through the reader's own keys."""
    rules_key = getattr(contracts_mod, "EXCHANGE_PAIR_RULES_KEY", "pair_rules")
    pairs_key = getattr(contracts_mod, "PAIR_RULES_PAIRS_KEY", "pairs")
    rules = exchange.get(rules_key)
    if not isinstance(rules, Mapping):
        return {}
    pairs = rules.get(pairs_key)
    return pairs if isinstance(pairs, Mapping) else {}


def _scout_state(
    exchange: Mapping[str, Any], contracts_mod: ModuleType
) -> tuple[dict[str, Any] | None, Outcome | None]:
    """`state` as the opportunity chain has it when engine 7 runs.

    Engine 7 values a candidate position at the book, so it needs a bid and an ask for
    every pair as well as engine 1's account payload - the criterion originally supplied
    only the latter and the gate fail-closed on the missing quotes, correctly, which the
    criterion then misread as a filter that publishes no universe.

    The quotes are built through engine 3's real `QuoteView`, one per pair engine 1
    published, and every key comes from engine 7's own `contracts.py`. One price for all
    of them is deliberate: this criterion varies the *balance* and must hold everything
    else still, or a difference in pair counts could be a difference in prices.
    """
    quotes: dict[str, Any] = {}
    for pair in sorted(_published_pairs(exchange, contracts_mod)):
        quote, problem = _quote_payload(
            pair, bid="99.95", ask="100.05", spread_pct=CANDIDATE_SPREAD_PCT
        )
        if quote is None:
            return None, problem
        quotes[pair] = quote
    return {
        getattr(contracts_mod, "EXCHANGE_KEY", "exchange"): dict(exchange),
        getattr(contracts_mod, "MARKET_SENSOR_KEY", "market_sensor"): {
            getattr(contracts_mod, "MARKET_SENSOR_QUOTES_KEY", "quotes"): quotes
        },
    }, None


def _scout_universe_field(contracts_mod: ModuleType) -> tuple[str | None, Outcome | None]:
    """Which key under `state["scout"]` holds the universe, read from B's own contract.

    Two ways, and neither of them retypes the name.

    `UNIVERSE_FIELD` first, because that is what this criterion's PENDING line proposed
    when it was registered ahead of engine 7. **B built something different and better**:
    a `ScoutUniverse` pydantic model with a `to_state_data()` serialiser, which is the
    same shape engines 10 and 11 use and neither of those declares a field-name constant
    either. The contract in a PENDING message is a proposal to the owning agent, not a
    decree, so the criterion follows the engine rather than the other way round.

    So, failing the constant, the model is *asked*: a `ScoutUniverse` carrying one
    sentinel pair is serialised, and the key whose value contains that sentinel is the
    one. That derives the name from B's own serialiser, so a rename follows
    automatically and there is no literal here to drift - which is the same discipline
    the rest of this section applies to `state["exchange"]`, where four retyped field
    names survived a whole phase because every test agreed with whoever wrote it.
    """
    declared = getattr(contracts_mod, "UNIVERSE_FIELD", None)
    if isinstance(declared, str):
        return declared, None

    model = getattr(contracts_mod, "ScoutUniverse", None)
    if model is None:
        return None, None
    try:
        payload = model(pairs=(UNIVERSE_PROBE_PAIR,)).to_state_data()
    except (TypeError, ValueError, AttributeError) as exc:
        return None, pending(
            "acsoe.engines.scout.contracts.ScoutUniverse could not be asked which key "
            f"carries the universe ({type(exc).__name__}: {exc}) - " + SCOUT_CONTRACT
        )
    if not isinstance(payload, Mapping):
        return None, failed(
            "ScoutUniverse.to_state_data() returned "
            + type(payload).__name__
            + " rather than a mapping; `state['scout']` is what every later gate reads"
        )
    for key, value in payload.items():
        if isinstance(value, (list, tuple)) and UNIVERSE_PROBE_PAIR in value:
            return str(key), None
    return None, failed(
        "ScoutUniverse published a universe of one pair and no key in its payload "
        f"carries it: {sorted(payload)}. The universe is what every later gate iterates "
        "over, and nothing downstream can find it either."
    )


def check_universe_varies_with_balance(ctx: VerifyContext) -> Outcome:
    """The tradable universe is smaller at $10 than at $5,000, over one fixture set.

    Both counts are asserted **and** asserted to differ. A criterion checking only
    that the filter runs would pass against a filter that ignores the balance
    entirely, and invariant 7's whole claim is that what the account can afford is
    part of what is tradable.
    """
    with root_import_path(ctx.root):
        contracts_mod, problem = try_import("acsoe.engines.scout.contracts")
        if contracts_mod is None:
            number, spec = PHASE3_ENGINES["scout"]
            return _with_contract(
                problem, f"engine {number} `scout` does not exist yet ({spec})", SCOUT_CONTRACT
            )
        # Read before the engine is imported. The criterion may not guess where the
        # universe is published - guessing a key under another engine's payload is the
        # audit's own defect - so an agreed `contracts.py` is the precondition for
        # anything else here, engine included.
        universe_key, problem = _scout_universe_field(contracts_mod)
        if universe_key is None:
            return problem or pending(
                "acsoe.engines.scout.contracts does not say where the universe is "
                "published - " + SCOUT_CONTRACT
            )
        engine_cls, problem = _engine_class("acsoe.engines.scout.engine", "scout")
        if engine_cls is None:
            return problem or pending("engine 7 `scout` does not exist yet - " + SCOUT_CONTRACT)
        config, problem = _phase3_config()
        if config is None:
            return problem or pending("the committed config could not be loaded")
        store_cls, problem = _store_class()
        if store_cls is None:
            return problem or pending("acsoe.clients.store.client does not exist yet")
        unavailable = getattr(contracts_mod, "REASON_INPUTS_UNAVAILABLE", None)

        counts: dict[str, int] = {}
        with console_workspace() as tmp:
            db_path, early = _phase3_seeded_db(ctx, tmp)
            if db_path is None:
                return early or pending("the Phase 0 seed is not available")

            for label, balance in (("small", "10.00"), ("large", "5000.00")):
                fake, problem = _fake_kraken()
                if fake is None:
                    return problem or pending("the fake Kraken client is unavailable")
                # Engine 1 is run once to learn which quote currencies exist, the
                # balances are set on the *client*, and it is run again. The balance is
                # never written into the payload: invariant 2 makes it a runtime fetch,
                # and a criterion injecting one would be exercising a path no live tick
                # takes.
                probe, _context, problem = _exchange_payload(config, fake)
                if probe is None:
                    return problem or pending("engine 1 `exchange` could not be driven")
                pairs = _published_pairs(probe, contracts_mod)
                quote_field = getattr(contracts_mod, "PAIR_QUOTE_FIELD", "quote")
                fake.set_balances(
                    dict.fromkeys(
                        sorted(
                            str(rule.get(quote_field))
                            for rule in pairs.values()
                            if isinstance(rule, Mapping)
                        ),
                        balance,
                    )
                )

                with store_cls(db_path) as store:
                    clients, problem = _fake_clients(kraken=fake, store=store)
                    if clients is None:
                        return problem or pending("test doubles unavailable")
                    context, problem = _engine_context(config, clients, now=_seed_now(db_path))
                    if context is None:
                        return problem or pending("acsoe.core.contracts does not exist yet")
                    exchange, _ctx, problem = _exchange_payload(config, fake)
                    if exchange is None:
                        return problem or pending("engine 1 `exchange` could not be driven")
                    state, problem = _scout_state(exchange, contracts_mod)
                    if state is None:
                        return problem or pending("engine 3's quote contract is unavailable")
                    result = engine_cls().process(context, state)

                data = result.data or {}
                if unavailable is not None and data.get("reason_code") == unavailable:
                    number, spec = PHASE3_ENGINES["scout"]
                    # The engine's own sentence, verbatim. `scout_inputs_unavailable`
                    # covers six different missing inputs - an absent `market_sensor`,
                    # an absent `exchange`, an unreachable store, no equity snapshot, a
                    # null config key, a currency mismatch - and reporting only the code
                    # would throw away the one thing that says which.
                    return pending(
                        f"engine {number} `scout` could not be driven yet ({spec}): "
                        + repr(getattr(result, "reason", None))
                    )
                published = data.get(universe_key)
                if published is None:
                    return failed(
                        f"engine 7 published no {universe_key!r} at the ${balance} balance, "
                        "and did not report its inputs unavailable either. The universe is "
                        "what every later gate iterates over. It said: "
                        + repr(getattr(result, "reason", None))
                    )
                counts[label] = len(published)

        if counts["small"] == counts["large"]:
            return failed(
                f"the universe held {counts['small']} pair(s) at $10 and the same "
                f"{counts['large']} at $5,000. Invariant 7 makes affordability part of "
                "tradability, so a filter that ignores the balance is not filtering on it."
            )
        if counts["small"] > counts["large"]:
            return failed(
                f"the universe was larger at $10 ({counts['small']}) than at $5,000 "
                f"({counts['large']}). More money cannot make fewer pairs tradable."
            )

    return passed(
        f"{counts['small']} pair(s) tradable at a $10 balance and {counts['large']} at "
        "$5,000, over the same fixture set"
    )


# --- the three `safety` criteria ------------------------------------------- #
#
# All three drive B's real `SafetyEngine` over the Phase 0 seed through B's real
# `StoreClient`. None of them touches a live engine 19 `memory`, which is Phase 4 and
# writes every one of `safety`'s six inputs - the seed exists to resolve exactly that
# forward dependency.
#
# The tick is anchored at `(run_id, cycle_id)` deliberately in each case, because that
# anchor is what the outage walk means by "consecutive through T-1". Anchoring at a
# `cycle_id` above 1 under a `run_id` the seed does not carry says "the previous tick
# was clean and wrote no block record", which ends the seeded outage; anchoring at
# cycle 1 says "this is the first tick of a new process", which the walk is required
# to treat as continuing an outage across a restart. Criterion 4 needs the first and
# criterion 5 needs the second, and they are not interchangeable.


def _phase3_seeded_db(ctx: VerifyContext, tmp: Path) -> tuple[Path | None, Outcome | None]:
    """The Phase 0 seed, scaled against **the committed config's** thresholds.

    Not `seeded_console_db`, which passes no `thresholds` and therefore gets `seed.py`'s
    module defaults - documented as "fixture-shape constants, not recommended values",
    and already diverged: the default `max_errors_in_window` is 10 where the config says
    20, so the default-scaled seed carries 13 ERROR rows, overshooting 10 and sitting
    under 20. The console criteria do not care what the thresholds are; these three care
    a great deal, and seeding to a constant while asserting against the config is the
    defect spec 13 names - a fixture pinned to a literal stops overshooting the moment
    the operator raises a limit, and the criterion then accuses the seed of a bug the
    criterion caused. `check_seed_fixtures_present` takes this same path.
    """
    config, problem = load_config(ctx.root)
    if config is None:
        return None, problem or pending("config/default.yaml does not exist yet")
    thresholds, early = required_thresholds(
        config,
        [KEY_MAX_DATA_BLOCKS, KEY_MAX_DRAWDOWN, KEY_MAX_LOSSES, KEY_MAX_ERRORS, KEY_ERROR_WINDOW],
    )
    if early is not None:
        return None, early

    seed_mod, problem = try_import("acsoe.clients.store.seed")
    if seed_mod is None:
        return None, problem or pending("acsoe.clients.store.seed does not exist yet")
    seed_fn, missing = module_attr(seed_mod, "seed_database")
    if seed_fn is None:
        return None, pending(missing)
    seed_kwargs, mismatch = _seed_threshold_kwargs(
        seed_mod,
        seed_fn,
        {
            "max_consecutive_data_blocks": int(thresholds[KEY_MAX_DATA_BLOCKS]),
            "max_drawdown_pct": as_decimal(thresholds[KEY_MAX_DRAWDOWN], KEY_MAX_DRAWDOWN),
            "max_consecutive_losses": int(thresholds[KEY_MAX_LOSSES]),
            "max_errors_in_window": int(thresholds[KEY_MAX_ERRORS]),
            "error_rate_window_s": int(thresholds[KEY_ERROR_WINDOW]),
        },
    )
    if mismatch is not None:
        return None, mismatch

    db_path = tmp / "acsoe.sqlite"
    seed_fn(db_path, **seed_kwargs)
    if not db_path.is_file():
        return None, failed("seed_database created no database file")
    return db_path, None


def _seed_workspace(ctx: VerifyContext, tmp: Path) -> tuple[Path | None, Any, Outcome | None]:
    """The config-scaled Phase 0 seed, plus the `Config` the engines are handed."""
    config, problem = _phase3_config()
    if config is None:
        return None, None, problem or pending("the committed config could not be loaded")
    db_path, early = _phase3_seeded_db(ctx, tmp)
    if db_path is None:
        return None, None, early or pending("the Phase 0 seed is not available")
    return db_path, config, None


def _store_class() -> tuple[Any, Outcome | None]:
    module, problem = try_import("acsoe.clients.store.client")
    if module is None:
        return None, problem or pending("acsoe.clients.store.client does not exist yet")
    cls, missing = module_attr(module, "StoreClient")
    if cls is None:
        return None, pending(missing)
    return cls, None


def _safety_state(
    *, cycle_id: int, blocked_by: str | None = None, close_intent: bool = False
) -> dict[str, Any]:
    """`state` as the guard chain has it when engine 17 runs.

    `position_manager` and `exit` are never set, and their absence is the point: the
    manage chain runs *after* the guard chain, so a fixture that supplied them would
    be handing the engine a state the orchestrator cannot produce - and would let an
    engine that read them pass a criterion asserting it does not.
    """
    state: dict[str, Any] = {
        "system": {"mode": "running", "close_intent": close_intent},
        "cycle_id": cycle_id,
        "guard_blockers": [],
    }
    if blocked_by is not None:
        state["trading_blocked_by"] = blocked_by
        state["block_reason"] = "seeded outage"
    return state


def _safety_command_rows(db_path: Path, contracts_mod: ModuleType) -> list[str]:
    """Every command `safety` has ever written, oldest first, claimed or not.

    Read from the table rather than through `store.pending_commands()`, which returns
    the *queue*. The orchestrator's command reader claims and consumes at the top of
    every tick, so a criterion that ticks a daemon and then asks the queue what was
    written sees an empty list the moment the daemon obeys - "every row was consumed"
    and "no row was written" are the same answer there, and they are opposite verdicts.
    `check_commands_round_trip` reads the table directly for the same reason.

    The console's rows are a different source and are excluded, using B's enum value
    rather than the literal `'safety'`.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT command FROM commands WHERE source = ? ORDER BY id",
            (str(contracts_mod.CommandSource.SAFETY),),
        ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def _drawdown_action_is_freeze(safety_contracts: ModuleType) -> bool:
    """Whether spec 37's ruling has reached `CONDITION_ACTION` yet."""
    table = getattr(safety_contracts, "CONDITION_ACTION", None)
    condition = getattr(safety_contracts, "SafetyCondition", None)
    action = getattr(safety_contracts, "SafetyAction", None)
    if table is None or condition is None or action is None:
        return False
    return table.get(condition.DRAWDOWN) is action.FREEZE


SPEC_42_PENDING = (
    "engine 17 `safety` has not been ratified against the spec 37 ruling yet (spec 42): "
    "CONDITION_ACTION still maps DRAWDOWN to an escalation. Invariant 14 as rewritten "
    "escalates on one condition only, a sustained data outage; drawdown, loss streak and "
    "error rate all write `freeze`. This criterion starts judging behaviour the moment "
    "that table says FREEZE, and will fail a `close_all` emitted on the seeded drawdown"
)


def check_safety_freezes_on_drawdown_without_opportunity_chain(ctx: VerifyContext) -> Outcome:
    """The breaker freezes on the seeded drawdown on a tick the opportunity chain never
    reached, and writes nothing on the ticks after it.

    **It runs in a real orchestrator with an empty opportunity chain**, rather than by
    calling `process` directly. "Not gated behind the other gates" is a claim about
    placement, and placement is the orchestrator's, so a criterion that called the
    engine itself would be asserting the thing it wanted to prove.

    The absence of the `close_all` is asserted as well as the presence of the `freeze`,
    and it is not vacuous: the seed carries open positions and resting entry orders, so
    invariant 14's escalation precondition is satisfied and an engine that still read
    drawdown as an escalation would emit one here.
    """
    with root_import_path(ctx.root):
        safety_contracts, problem = try_import("acsoe.engines.safety.contracts")
        if safety_contracts is None:
            return _engine_absent(problem, "safety")
        engine_cls, problem = _engine_class("acsoe.engines.safety.engine", "safety")
        if engine_cls is None:
            return problem or pending("engine 17 `safety` does not exist yet")
        store_contracts, problem = try_import("acsoe.clients.store.contracts")
        if store_contracts is None:
            return problem or pending("acsoe.clients.store.contracts does not exist yet")
        if not _drawdown_action_is_freeze(safety_contracts):
            return pending(SPEC_42_PENDING)

        store_cls, problem = _store_class()
        if store_cls is None:
            return problem or pending("acsoe.clients.store.client does not exist yet")
        orch_mod, problem = try_import("acsoe.core.orchestrator")
        if orch_mod is None:
            return problem or pending("acsoe.core.orchestrator does not exist yet")
        core_mod, problem = try_import("acsoe.core.contracts")
        if core_mod is None:
            return problem or pending("acsoe.core.contracts does not exist yet")
        orch_cls, missing = module_attr(orch_mod, "Orchestrator")
        if orch_cls is None:
            return pending(missing)
        chains_cls, missing = module_attr(core_mod, "Chains")
        if chains_cls is None:
            return pending(missing)

        with console_workspace() as tmp:
            db_path, config, early = _seed_workspace(ctx, tmp)
            if db_path is None:
                return early or pending("the Phase 0 seed is not available")

            # The seed's `data_guard` run is the newest thing in `block_records` and is
            # three ticks past the outage limit, so on any tick it also trips the
            # outage - which *is* an escalation, correctly, and would emit the very
            # `close_all` this criterion asserts the absence of. Deleting that run from
            # this copy of the seed is what isolates the drawdown, and it is the only
            # way to ask the question at all: with two escalating conditions live, an
            # engine that had never been corrected would be indistinguishable from one
            # that had. Everything the criterion actually reads - the drawdown series,
            # the losing streak, the open positions, the resting orders - is untouched,
            # and the outage is criterion 5's subject, tested there against the seed's
            # own rows.
            # Read before the deletion: `_seed_now` takes the newest `block_records`
            # timestamp, and the rows about to go are the newest ones.
            seed_now = _seed_now(db_path)
            outage = _seeded_outage_ticks(db_path)
            _truncate_outage_to(db_path, outage, 0)

            with store_cls(db_path) as store:
                exposure = _seed_exposure(db_path, store_contracts)
                if exposure == (0, 0):
                    return failed(
                        "the Phase 0 seed carries neither an open position nor a resting "
                        "entry order, so the absence of a `close_all` here would prove "
                        "nothing: invariant 14 gates escalation on exposure"
                    )
                # A list, sliced by length below, never a set difference: the seed
                # may already carry a `safety` row, and a set difference would report
                # a second identical command as nothing having happened.
                before = _safety_command_rows(db_path, store_contracts)
                clients, problem = _fake_clients(store=store)
                if clients is None:
                    return problem or pending("test doubles unavailable")
                # The operator presses Activate first, through the real `commands`
                # table. A daemon starts `idle` and never restores its mode, and
                # freezing a system that is not running is correctly a no-op - so
                # without this the criterion would be asking whether the breaker stops
                # a system that was already stopped, which nothing can answer. The row
                # is written the way the console writes it and applied by the real
                # command reader at the top of the first tick.
                _append_command(
                    store, store_contracts, "activate", int(seed_now.timestamp() * 1_000_000)
                )
                orchestrator = orch_cls(
                    config=config,
                    clock=_RoundTripClock(seed_now),
                    clients=clients,
                    chains=chains_cls(guard=(engine_cls(),)),
                )
                # Three ticks, all with an empty opportunity chain. The first must
                # emit; the rest must not, or a sustained drawdown appends a row every
                # sixty seconds forever.
                first = orchestrator.tick()
                orchestrator.tick()
                orchestrator.tick()
                mode = orchestrator.system.get("mode")
                emitted = _safety_command_rows(db_path, store_contracts)[len(before) :]
                published = first.get("safety") or {}

        tripped = list(published.get("tripped") or [])
        drawdown = str(safety_contracts.SafetyCondition.DRAWDOWN)
        freeze = str(store_contracts.CommandName.FREEZE)
        close_all = str(store_contracts.CommandName.CLOSE_ALL)

        if drawdown not in tripped:
            return failed(
                "the seeded drawdown did not trip the breaker on a tick where the "
                f"opportunity chain never ran; it reported {tripped}"
            )
        if close_all in emitted:
            return failed(
                "the seeded drawdown emitted `close_all`. Spec 37's ruling makes the "
                "sustained data outage the only escalation; drawdown writes `freeze`. "
                f"Commands written: {emitted}"
            )
        if freeze not in emitted:
            return failed(
                "the breaker tripped on the seeded drawdown and wrote no `freeze` row. "
                "Its BLOCK stops one tick; the row is what makes the decision persist "
                f"across the restart. Commands written: {emitted}"
            )
        if len(emitted) != 1:
            return failed(
                f"three ticks with the condition unchanged wrote {len(emitted)} rows "
                f"({emitted}). A breaker that re-emits while the condition persists "
                "appends a row every tick forever."
            )

        if mode != "frozen":
            return failed(
                "three ticks after the breaker wrote its `freeze` the daemon still reads "
                f"mode={mode!r}. The row is only a record until the command reader "
                "applies it; a breaker whose decision never reaches `state['system']` "
                "has not stopped anything."
            )

    return passed(
        "the seeded drawdown froze the system on a tick with an empty opportunity chain "
        f"(tripped: {', '.join(tripped)}); one `freeze` row over three ticks, no "
        f"`close_all`, and the daemon reached `{mode}` - against a seed carrying "
        f"{exposure[0]} open position(s) and {exposure[1]} resting entry order(s)"
    )


def _seed_exposure(db_path: Path, store_contracts: ModuleType) -> tuple[int, int]:
    """(open positions, resting entry orders) in the seed - invariant 14's precondition.

    The three status values are taken from B's real enums rather than written into the
    SQL. They are lowercase in the schema and the first draft of this helper spelled
    them `'OPEN'` and `'RESTING'`, which matched nothing and reported an unexposed seed
    - and an unexposed seed is a state both `safety` criteria are written to refuse, so
    the mistake surfaced as two confident FAILs accusing the seed. A criterion that
    retypes a contract can be wrong about it in exactly the way this phase exists to
    correct.
    """
    conn = sqlite3.connect(db_path)
    try:
        positions = _count(
            conn,
            "SELECT COUNT(*) FROM positions WHERE status = ?",
            (str(store_contracts.PositionStatus.OPEN),),
        )
        orders = _count(
            conn,
            "SELECT COUNT(*) FROM orders WHERE status = ? AND intent = ?",
            (
                str(store_contracts.OrderStatus.RESTING),
                str(store_contracts.OrderIntent.ENTRY),
            ),
        )
    finally:
        conn.close()
    return positions, orders


def _seed_now(db_path: Path) -> datetime:
    """The seed's own most recent instant, as the clock a criterion should run at.

    `safety`'s error-rate input is "ERROR rows inside the configured window counted
    back from `context.now`", so a criterion that picks its own instant and then
    compares against the seed counts zero rows on both sides and calls that agreement.
    The seed is generated from a fixed seed value, so this is as deterministic as a
    literal - it is simply the fixture's instant rather than one chosen beside it.

    Falls back to :data:`PHASE3_NOW` on an empty table: a criterion whose subject has
    no rows has other problems, and they are its own to report.
    """
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT MAX(ts) FROM block_records").fetchone()
    finally:
        conn.close()
    if row is None or row[0] is None:
        return PHASE3_NOW
    return datetime.fromtimestamp(int(row[0]) / 1_000_000, tz=UTC)


def _seeded_outage_ticks(db_path: Path) -> list[tuple[str, int]]:
    """The seed's longest run of consecutive `data_guard` ticks, oldest first.

    Ordered by `ts` and grouped by `(run_id, cycle_id)`, for the reasons
    `_seeded_block_run` spells out: `cycle_id` restarts at 1 with each process and the
    seed reuses values across two runs on purpose, and a tick two guards blocked
    contributes one.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT run_id,
                   cycle_id,
                   MIN(ts) AS ts,
                   MAX(CASE WHEN blocked_by = 'data_guard' THEN 1 ELSE 0 END) AS has_guard
            FROM block_records
            GROUP BY run_id, cycle_id
            ORDER BY ts, run_id, cycle_id
            """
        ).fetchall()
    finally:
        conn.close()

    best: list[tuple[str, int]] = []
    current: list[tuple[str, int]] = []
    for row in rows:
        if int(row["has_guard"]):
            current.append((str(row["run_id"]), int(row["cycle_id"])))
            if len(current) > len(best):
                best = list(current)
        else:
            current = []
    return best


def _truncate_outage_to(db_path: Path, ticks: Sequence[tuple[str, int]], keep: int) -> None:
    """Delete the seeded outage's trailing ticks so the run is exactly `keep` long.

    The rows that remain are the seed's own rows - this shortens the fixture, it does
    not write a new one. The seed overshoots every threshold by three deliberately, so
    that a fixture pinned to a literal cannot stop overshooting when the operator
    raises a limit; that is right for proving the breaker fires and it makes the seed
    incapable of ever sitting **at** the boundary, which is exactly what "and not one
    tick before" has to test.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "DELETE FROM block_records WHERE run_id = ? AND cycle_id = ?",
            [(run_id, cycle_id) for run_id, cycle_id in ticks[keep:]],
        )
        conn.commit()
    finally:
        conn.close()


def check_safety_escalates_on_sustained_outage(ctx: VerifyContext) -> Outcome:
    """`close_all` on the tick after the limit, and nothing on the tick at it.

    Both halves, because a criterion asserting only the escalation passes against an
    implementation that fires a tick early - and firing early liquidates an account
    over an outage that has not reached the threshold the operator chose.

    Counted from the seeded `block_records` and from nothing else. Engine 19 `memory`
    writes those rows in Phase 4 and Phase 3 may not depend on it. The seed's outage
    run is longer than the limit by design, so it cannot sit at the boundary; the
    fixture is shortened to `limit - 1` and then to `limit` trailing ticks, using the
    seed's own rows, and the boundary is read off the engine.
    """
    with root_import_path(ctx.root):
        safety_contracts, problem = try_import("acsoe.engines.safety.contracts")
        if safety_contracts is None:
            return _engine_absent(problem, "safety")
        engine_cls, problem = _engine_class("acsoe.engines.safety.engine", "safety")
        if engine_cls is None:
            return problem or pending("engine 17 `safety` does not exist yet")
        store_contracts, problem = try_import("acsoe.clients.store.contracts")
        if store_contracts is None:
            return problem or pending("acsoe.clients.store.contracts does not exist yet")
        store_cls, problem = _store_class()
        if store_cls is None:
            return problem or pending("acsoe.clients.store.client does not exist yet")

        config, problem = _phase3_config()
        if config is None:
            return problem or pending("the committed config could not be loaded")
        limit = config.get(KEY_MAX_DATA_BLOCKS)
        if limit is None:
            return pending(_unset_key_message(KEY_MAX_DATA_BLOCKS))
        limit = int(limit)

        outage = str(safety_contracts.SafetyCondition.DATA_OUTAGE)
        close_all = str(store_contracts.CommandName.CLOSE_ALL)
        readings: dict[str, Any] = {}

        for label, keep in (("at the limit", limit - 1), ("past the limit", limit)):
            with console_workspace() as tmp:
                db_path, _config, early = _seed_workspace(ctx, tmp)
                if db_path is None:
                    return early or pending("the Phase 0 seed is not available")
                ticks = _seeded_outage_ticks(db_path)
                if len(ticks) < limit:
                    return failed(
                        f"the Phase 0 seed's longest `data_guard` run is {len(ticks)} tick(s) "
                        f"and `safety.max_consecutive_data_blocks` is {limit}. The seed is "
                        "supposed to overshoot every threshold; this criterion cannot reach "
                        "the boundary from it."
                    )
                seed_now = _seed_now(db_path)
                exposure = _seed_exposure(db_path, store_contracts)
                if exposure == (0, 0):
                    return failed(
                        "the Phase 0 seed carries no open position and no resting entry "
                        "order, so invariant 14's escalation precondition is absent and no "
                        "`close_all` could be emitted whatever the outage did"
                    )
                _truncate_outage_to(db_path, ticks, keep)
                anchor_run, anchor_cycle = ticks[keep - 1]

                with store_cls(db_path) as store:
                    before = _safety_command_rows(db_path, store_contracts)
                    clients, problem = _fake_clients(store=store)
                    if clients is None:
                        return problem or pending("test doubles unavailable")
                    context, problem = _engine_context(
                        config, clients, run_id=anchor_run, now=seed_now
                    )
                    if context is None:
                        return problem or pending("acsoe.core.contracts does not exist yet")
                    result = engine_cls().process(
                        context,
                        _safety_state(cycle_id=anchor_cycle + 1, blocked_by="data_guard"),
                    )
                    emitted = _safety_command_rows(db_path, store_contracts)[len(before) :]
                    data = result.data or {}
                    readings[label] = {
                        "tripped": list(data.get("tripped") or []),
                        "effective": data.get("consecutive_data_blocks"),
                        "emitted": emitted,
                    }

        at_limit = readings["at the limit"]
        past_limit = readings["past the limit"]

        if at_limit["effective"] != limit:
            return failed(
                f"the tick at the limit counted {at_limit['effective']} consecutive blocked "
                f"tick(s), not {limit}. The count is `stored through T-1` plus this tick, "
                "and the criterion cannot judge the boundary if it is not standing on it."
            )
        if outage in at_limit["tripped"]:
            return failed(
                f"the outage tripped at exactly {limit} consecutive blocked ticks. "
                "Invariant 14 says 'more than', so the limit itself must not fire - firing "
                "a tick early liquidates an account over an outage that has not reached "
                "the operator's threshold."
            )
        if close_all in at_limit["emitted"]:
            return failed(
                "a `close_all` was written on the tick at the limit: "
                f"{at_limit['emitted']}"
            )
        if past_limit["effective"] != limit + 1:
            return failed(
                f"the tick past the limit counted {past_limit['effective']}, not {limit + 1}"
            )
        if outage not in past_limit["tripped"]:
            return failed(
                f"{limit + 1} consecutive blocked ticks did not trip the outage; it "
                f"reported {past_limit['tripped']}. The breaker never fires."
            )
        if close_all not in past_limit["emitted"]:
            return failed(
                "the outage tripped past the limit and no `close_all` was written. Per "
                "the spec 37 ruling the sustained outage is the one condition that "
                f"escalates. Commands written: {past_limit['emitted']}"
            )

    return passed(
        f"counted from the seeded block_records: {limit} consecutive blocked tick(s) "
        f"does not trip the outage and writes no `close_all`; {limit + 1} trips it and "
        f"writes one, against a seed carrying {exposure[0]} open position(s) and "
        f"{exposure[1]} resting entry order(s)"
    )


#: What `safety` must read from the store, and the seeded value each one has to match.
#: The criterion computes every right-hand side straight from the seeded tables by SQL,
#: so a reading that agrees is a reading that came from those rows.
SAFETY_INPUT_FIELDS: Final[tuple[str, ...]] = (
    "drawdown_pct",
    "consecutive_losses",
    "errors_in_window",
    "stored_data_blocks",
    "open_positions",
    "resting_entry_orders",
)

#: Values a `state` payload would carry if `safety` read one. Deliberately plausible
#: and deliberately wrong: an engine reading engine 19 out of `state` would report
#: these instead of the seed's, and every one of them is far enough from the seeded
#: value that agreement cannot be a coincidence.
POISONED_STATE: Final[Mapping[str, Any]] = {
    "position_manager": {
        "open_positions": 99,
        "positions": [],
        "resting_entry_orders": 99,
        "hold_reason": None,
    },
    "exit": {"positions_closed": True},
    "memory": {
        "drawdown_pct": "0.99",
        "consecutive_losses": 99,
        "errors_in_window": 99,
        "stored_data_blocks": 99,
    },
}


def check_safety_inputs_all_from_the_seed(ctx: VerifyContext) -> Outcome:
    """Every one of `safety`'s six inputs comes from the store, and none from `state`.

    Two independent proofs, because either alone is satisfiable by the wrong engine.

    **The readings match the seeded tables.** Each of the six is recomputed here
    straight from the seeded SQL and compared with what the engine reported. A reading
    that agrees with a number this criterion derived from the rows is a reading that
    came from those rows.

    **The readings do not move when `state` is poisoned.** The same tick is run again
    with `state["position_manager"]`, `state["exit"]` and `state["memory"]` carrying
    plausible, wrong values of the same six quantities. An engine reading any of them
    from `state` reports a different number the second time. This is the half that
    catches a *live engine 19* being read: engine 19 is Phase 4 and the seed exists to
    resolve that forward dependency, so a Phase 3 gate that reached for it would still
    pass every test written against a database.
    """
    with root_import_path(ctx.root):
        engine_cls, problem = _engine_class("acsoe.engines.safety.engine", "safety")
        if engine_cls is None:
            return problem or pending("engine 17 `safety` does not exist yet")
        store_contracts, problem = try_import("acsoe.clients.store.contracts")
        if store_contracts is None:
            return problem or pending("acsoe.clients.store.contracts does not exist yet")
        store_cls, problem = _store_class()
        if store_cls is None:
            return problem or pending("acsoe.clients.store.client does not exist yet")
        config, problem = _phase3_config()
        if config is None:
            return problem or pending("the committed config could not be loaded")
        window_s = config.get(KEY_ERROR_WINDOW)
        if window_s is None:
            return pending(_unset_key_message(KEY_ERROR_WINDOW))

        with console_workspace() as tmp:
            db_path, _config, early = _seed_workspace(ctx, tmp)
            if db_path is None:
                return early or pending("the Phase 0 seed is not available")

            seed_now = _seed_now(db_path)
            seed_now_us = int(seed_now.timestamp() * 1_000_000)
            conn = sqlite3.connect(db_path)
            try:
                seeded: dict[str, Decimal | int] = {
                    "drawdown_pct": _seeded_max_drawdown(conn),
                    "consecutive_losses": _seeded_losing_streak(conn),
                    "errors_in_window": _seeded_error_blocks(
                        conn, seed_now_us - int(window_s) * MICROSECONDS
                    ),
                }
            finally:
                conn.close()
            positions, orders = _seed_exposure(db_path, store_contracts)
            seeded["open_positions"] = positions
            seeded["resting_entry_orders"] = orders
            seeded["stored_data_blocks"] = len(_seeded_outage_ticks(db_path))

            readings: dict[str, dict[str, Any]] = {}
            for label, extra in (("clean", {}), ("poisoned", POISONED_STATE)):
                with store_cls(db_path) as store:
                    clients, problem = _fake_clients(store=store)
                    if clients is None:
                        return problem or pending("test doubles unavailable")
                    # Cycle 1 under a `run_id` the seed does not carry: the first tick
                    # of a new process, which the outage walk is required to treat as
                    # continuing an outage across a restart rather than resetting it.
                    # That is what makes the whole seeded run visible to the reading
                    # this criterion checks. Anchoring under one of the seed's own
                    # `run_id`s instead makes the walk refuse to cross into itself and
                    # reports zero, which is correct behaviour and the wrong question.
                    context, problem = _engine_context(config, clients, now=seed_now)
                    if context is None:
                        return problem or pending("acsoe.core.contracts does not exist yet")
                    state = _safety_state(cycle_id=1)
                    state.update(copy.deepcopy(dict(extra)))
                    result = engine_cls().process(context, state)
                    readings[label] = dict(result.data or {})

        missing = [f for f in SAFETY_INPUT_FIELDS if f not in readings["clean"]]
        if missing:
            return failed(
                "engine 17 published no reading for " + ", ".join(missing) + ". Every one "
                "of the six is a `commands`-table decision's evidence and the console "
                "renders them; a breaker that does not report what it read cannot be audited."
            )

        for field in SAFETY_INPUT_FIELDS:
            reported = readings["clean"][field]
            expected = seeded[field]
            same = (
                as_decimal(reported, f"safety.{field}") == expected
                if isinstance(expected, Decimal)
                else int(reported) == int(expected)
            )
            if not same:
                return failed(
                    f"engine 17 reported {field} = {reported!r}; the seeded tables say "
                    f"{expected!r}. That reading did not come from the Phase 0 seed."
                )

        moved = [
            field
            for field in SAFETY_INPUT_FIELDS
            if readings["poisoned"].get(field) != readings["clean"].get(field)
        ]
        if moved:
            return failed(
                "poisoning `state` with a plausible engine 19 payload changed "
                + ", ".join(moved)
                + ". Every one of `safety`'s six inputs is a store read: engine 19 is "
                "Phase 4, it runs in the manage chain *after* the guard chain even once "
                "it exists, and `state` cannot carry those values when engine 17 runs."
            )

    return passed(
        "all six inputs match the seeded tables (drawdown "
        + str(seeded["drawdown_pct"])
        + f", {seeded['consecutive_losses']} losing trade(s), "
        + f"{seeded['errors_in_window']} error block(s), {seeded['stored_data_blocks']} "
        + f"outage tick(s), {seeded['open_positions']} position(s), "
        + f"{seeded['resting_entry_orders']} resting order(s)) and none of them moved "
        "when state was poisoned with an engine 19 payload"
    )


# --- phase_3_gates_have_both_tests ----------------------------------------- #

#: Where each Phase 3 gate's tests live. Each agent owns `tests/` mirroring the source
#: it owns, so these are B's files; this criterion reads them and never writes one.
PHASE3_TEST_FILES: Final[Mapping[str, str]] = {
    "scout": "tests/engines/test_scout.py",
    "cost": "tests/engines/test_cost.py",
    "risk": "tests/engines/test_risk.py",
    "safety": "tests/engines/test_safety.py",
}

#: Read as "this test asserts the gate refused" and "this test asserts it allowed".
#: Matched against the parsed syntax tree rather than the test's name: a name is a
#: label the author chose and `test_it_blocks_on_a_wide_spread` can assert nothing at
#: all, whereas an `EngineStatus.BLOCK` in a comparison is the assertion itself.
BLOCK_MARKERS: Final[tuple[str, ...]] = ("BLOCK",)
PASS_MARKERS: Final[tuple[str, ...]] = ("OK",)


def _test_directions(path: Path) -> tuple[int, int, str]:
    """How many tests in `path` assert a block, and how many assert a pass.

    Counted from the AST. Every `EngineStatus.<NAME>` attribute access inside a
    `def test_*` body is collected, along with `blocks_trading` compared against a
    boolean, and a test is counted in a direction when it carries a marker for it. A
    test carrying both - a parametrised one covering the gate in both directions -
    counts for both, which is correct: the criterion asks whether the behaviour is
    exercised, not how many functions it took.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return 0, 0, f"{path.name} could not be parsed: {exc}"

    blocking = 0
    passing = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        statuses = {
            child.attr
            for child in ast.walk(node)
            if isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "EngineStatus"
        }
        blocks_flags = {
            bool(sibling.value)
            for child in ast.walk(node)
            if isinstance(child, ast.Compare)
            for operand in [child.left, *child.comparators]
            for sibling in ast.walk(child)
            if isinstance(sibling, ast.Constant)
            and isinstance(sibling.value, bool)
            and isinstance(operand, ast.Attribute)
            and operand.attr == "blocks_trading"
        }
        if statuses & set(BLOCK_MARKERS) or True in blocks_flags:
            blocking += 1
        if statuses & set(PASS_MARKERS) or False in blocks_flags:
            passing += 1
    return blocking, passing, ""


def check_phase_3_gates_have_both_tests(ctx: VerifyContext) -> Outcome:
    """Each of engines 7, 10, 11 and 17 has a test proving it blocks and one proving it
    passes.

    A gate with only a happy path is incomplete and a gate with only block cases is a
    gate that refuses everything and proves nothing. `code-standards.md` requires both
    halves of every gate; this is the criterion that notices when one is missing, and
    it is a completeness check rather than a correctness one - whether those tests
    *pass* is `toolchain_green`'s question and it runs in every phase.

    It reads the assertions, not the test names.
    """
    findings: list[str] = []
    absent: list[str] = []
    for engine in sorted(PHASE3_TEST_FILES):
        number, spec = PHASE3_ENGINES[engine]
        path = ctx.root / Path(PHASE3_TEST_FILES[engine])
        if not path.is_file():
            absent.append(f"engine {number} `{engine}` ({PHASE3_TEST_FILES[engine]}, {spec})")
            continue
        blocking, passing, problem = _test_directions(path)
        if problem:
            return failed(problem)
        if not blocking or not passing:
            missing = "no test asserting it blocks" if not blocking else "no test asserting it passes"
            return failed(
                f"engine {number} `{engine}` has {missing} in "
                f"{PHASE3_TEST_FILES[engine]} ({blocking} block, {passing} pass). "
                "code-standards.md: every gate needs at least one test proving it blocks "
                "and one proving it passes."
            )
        findings.append(f"{engine} {blocking}/{passing}")

    if absent:
        return pending(
            "no test file yet for " + "; ".join(absent) + ". Each agent owns the tests "
            "mirroring its own source, so this criterion reads them and never writes one."
        )
    return passed(
        "every Phase 3 gate has a test asserting it blocks and one asserting it passes "
        "(block/pass per engine: " + ", ".join(findings) + ")"
    )


# --------------------------------------------------------------------------- #
# Phase 4 - memory and replay (spec 48)
# --------------------------------------------------------------------------- #
#
# Phase 4 is the phase where a mistake looks like success. A purging bug or a short
# embargo produces a model that appears excellent and is worthless; a missed block
# record makes the circuit breaker inert. Neither crashes, neither turns a test red,
# neither is visible to an operator. Every criterion below is therefore written to be
# sensitive to a *named* wrong implementation rather than to the shape of the evidence,
# and every one has been observed PENDING, PASS and FAIL - the last against a
# deliberately broken subject, recorded in `docs/build-log/phase-4/c-interface.md`.

#: Engine number and owning spec, for the PENDING message. Same shape as
#: `PHASE3_ENGINES`, and for the same reason: a PENDING that does not name the spec
#: sends the reader to the task list to find out who is late.
PHASE4_ENGINES: Final[Mapping[str, tuple[int, str]]] = {
    "memory": (19, "spec 49 and spec 50, agent C"),
}

#: The research modules Phase 4 adds, and who owes them.
PHASE4_RESEARCH: Final[Mapping[str, str]] = {
    "acsoe.research.labelling": "spec 52, agent C",
    "acsoe.research.walkforward": "spec 53, agent C",
    "acsoe.research.replay": "spec 54, agent A",
}

KEY_TARGET_PCT: Final = "barriers.target_pct"
KEY_STOP_PCT: Final = "barriers.stop_pct"
KEY_TIMEOUT_BARS: Final = "barriers.timeout_bars"
KEY_EMBARGO_BARS: Final = "backtest.embargo_bars"
#: The decision-bar grid. The same key engine 3 `market_sensor` reads for the live
#: bar and engine 23 `backtest` reads for the replay, so an archive can never be
#: measured on a different grid from the one the system trades.
KEY_DECISION_BAR_S: Final = "timeframes.decision_bar_s"
KEY_REPORTING_CURRENCY: Final = "trading.base_reporting_currency"

#: The three outcomes of the triple barrier. There is no fourth, and spec 52 forbids
#: inventing one.
BARRIER_LABELS: Final[tuple[str, ...]] = ("target", "stop", "timeout")

#: C's committed evidence. Both are deposited under `tests/fixtures/`, which is the
#: only place a criterion may read committed artefacts from - `data/`, `models/` and
#: `logs/` are gitignored and a criterion that reads one passes only on the machine
#: that produced it.
LABELLED_SAMPLE_REL: Final = "tests/fixtures/labelled_sample.parquet"
HAND_VERIFIED_REL: Final = "tests/fixtures/labels_hand_verified.json"

#: Columns `labelled_sample.parquet` must carry. Asserted as a superset test rather
#: than an equality one: a producer adding a column is not a defect, a producer
#: dropping the window end is, because the splitter purges on it.
LABELLED_SAMPLE_COLUMNS: Final[tuple[str, ...]] = (
    "pair",
    "decision_ts",
    "close",
    "target_price",
    "stop_price",
    "label",
    "touch_ts",
    "bars_elapsed",
    "touch_price",
    "label_window_end_ts",
    "ambiguous",
    "candles_in_window",
)

#: Provenance keys the parquet must carry *in the file*. A parquet that cannot say
#: where it came from is indistinguishable from one written by hand, and spec 56 is
#: explicit that this criterion is written to notice.
LABELLED_SAMPLE_PROVENANCE: Final[tuple[str, ...]] = (
    "archive",
    "pair",
    "interval_s",
    "span_start_ts",
    "span_end_ts",
    "target_pct",
    "stop_pct",
    "timeout_bars",
    "ambiguous_count",
    "holes_mean_no_trades",
    "source_note",
)


def _phase4_engine_class(module_name: str, engine: str) -> tuple[Any, Outcome | None]:
    """The Phase 4 `BaseEngine` subclass, or the PENDING that names its spec."""
    number, spec = PHASE4_ENGINES[engine]
    module, problem = try_import(module_name)
    if module is None:
        if problem is not None and problem.result is Result.FAIL:
            return None, problem
        return None, pending(f"engine {number} `{engine}` does not exist yet ({spec})")
    cls = _engine_named(module, engine)
    if cls is None:
        return None, pending(f"{module_name} exposes no class with name == {engine!r}")
    return cls, None


def _memory_engine() -> tuple[Any, Any, Outcome | None]:
    """(engine class, its contracts module, early outcome).

    The contracts module comes back with the class because every criterion here
    builds a `state` payload and **the key names are not this script's to remember**.
    They are imported from `acsoe.engines.memory.contracts`, which is the real
    contract engine 19 is held to. `check_data_guard_blocks_bad_data` is the standing
    example of what happens otherwise: it fabricated the contract it was judging
    against, the fabrication agreed with the mistake, and the criterion's body never
    executed while both halves of its proof passed.
    """
    engine_cls, problem = _phase4_engine_class("acsoe.engines.memory.engine", "memory")
    if engine_cls is None:
        return None, None, problem
    contracts, problem = try_import("acsoe.engines.memory.contracts")
    if contracts is None:
        return None, None, problem or pending(
            "acsoe.engines.memory.contracts does not exist yet (spec 49, agent C)"
        )
    return engine_cls, contracts, None


def _migrated_db(tmp: Path, name: str = "live.sqlite") -> tuple[Path | None, Any, Outcome | None]:
    """An empty database with every migration applied, plus the `StoreClient` class.

    Empty on purpose. The whole point of `memory_writes_safety_inputs_live` is that
    the numbers arrive from engine 19 rather than from B's seed generator, so the
    database engine 19 writes into must start with nothing in it - a criterion that
    seeded it first would be comparing the seed with itself.
    """
    store_cls, problem = _store_class()
    if store_cls is None:
        return None, None, problem
    db_path = tmp / name
    with store_cls(db_path) as store:
        store.migrate()
    return db_path, store_cls, None


def _memory_tick_state(
    contracts: Any,
    *,
    cycle_id: int,
    blockers: Sequence[Mapping[str, Any]] = (),
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """`state` as the manage chain has it when engine 19 runs.

    `guard_blockers` is always present - the contract says an empty list on an
    unblocked tick, never absent - and `trading_blocked_by` is set from the first
    blocker exactly as the orchestrator sets it, so a tick handed to engine 19 here
    is one the orchestrator could actually produce.
    """
    state: dict[str, Any] = {
        "system": {"mode": "running", "close_intent": False},
        str(contracts.CYCLE_ID_KEY): cycle_id,
        str(contracts.GUARD_BLOCKERS_KEY): [dict(entry) for entry in blockers],
    }
    if blockers:
        state["trading_blocked_by"] = blockers[0]["engine"]
        state["block_reason"] = blockers[0]["reason"]
    if extra:
        state.update(copy.deepcopy(dict(extra)))
    return state


def _rejection_extra(
    contracts: Any,
    *,
    pair: str,
    rejected_by: str,
    reason: str,
    reason_code: str,
    economics: Mapping[str, str] = {},
) -> dict[str, Any]:
    """`state` as it stands when the **opportunity** chain refused a candidate.

    Built the way the orchestrator builds it rather than as a list of rejection rows,
    because engine 19 derives the rejection: a guard-chain block is one *tick*, an
    opportunity-chain block on a tick that had a candidate is one *rejection*, and the
    engine tells them apart by whether the blocking engine is among this tick's
    `guard_blockers`. Handing it a pre-made list of rows would skip exactly that
    derivation and test nothing about it.
    """
    scout_key, pair_field = contracts.CANDIDATE_PAIR_PATH
    blocker: dict[str, Any] = {str(contracts.REASON_CODE_FIELD): reason_code}
    blocker.update(dict(economics))
    return {
        str(scout_key): {str(pair_field): pair},
        str(contracts.TRADING_BLOCKED_BY_KEY): rejected_by,
        str(contracts.BLOCK_REASON_KEY): reason,
        rejected_by: blocker,
    }


def _block_rows(db_path: Path) -> list[dict[str, Any]]:
    """Every `block_records` row, oldest first by `ts`."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT run_id, cycle_id, ts, blocked_by, block_reason, is_primary, status "
            "FROM block_records ORDER BY ts, rowid"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


# --- memory_records_every_blocker ------------------------------------------ #


def check_memory_records_every_blocker(ctx: VerifyContext) -> Outcome:
    """Engine 19 writes one `block_records` row per entry in `state["guard_blockers"]`.

    Three cases in one criterion, because each hides a different bug and each of the
    three is a defect that leaves every test green:

    * **A blocked tick with no candidate still writes a row.** An implementer reading
      invariant 12 as "rejections are logged" writes a row only where a candidate was
      rejected - and `safety`'s outage counter is then built from a table that is
      empty on exactly the ticks it counts. The breaker never fires.
    * **Two guards blocking at once writes two rows, `is_primary` on the first only.**
      The guard chain never breaks early, so `data_guard` and `safety` can both block.
      One row per tick passes a naive count and destroys invariant 12.
    * **An unblocked tick writes no row.** A row on every tick makes every count that
      reads this table meaningless, the outage run included.

    The store is the **real** `StoreClient` over a temporary database. A double that
    accepts any row and remembers nothing cannot fail a test about what was written.
    """
    with root_import_path(ctx.root):
        engine_cls, contracts, problem = _memory_engine()
        if engine_cls is None:
            return problem or pending("engine 19 `memory` does not exist yet")
        config, problem = _phase3_config()
        if config is None:
            return problem or pending("the committed config could not be loaded")

        with console_workspace() as tmp:
            db_path, store_cls, problem = _migrated_db(tmp)
            if db_path is None:
                return problem or pending("acsoe.clients.store.client does not exist yet")

            run_id = "verify-phase-4-blocks"
            base = PHASE3_NOW
            with store_cls(db_path) as store:
                clients, problem = _fake_clients(store=store)
                if clients is None:
                    return problem or pending("test doubles unavailable")
                engine = engine_cls()

                # Tick 1: `data_guard` blocked and no candidate ever existed. Nothing
                # anywhere in this state names a pair, a score or a rejection reason.
                context, problem = _engine_context(config, clients, run_id=run_id, now=base)
                if context is None:
                    return problem or pending("acsoe.core.contracts does not exist yet")
                engine.process(
                    context,
                    _memory_tick_state(
                        contracts,
                        cycle_id=1,
                        blockers=[
                            {
                                "engine": "data_guard",
                                "reason": "stale candles",
                                "status": "BLOCK",
                            }
                        ],
                    ),
                )

                # Tick 2: two guards at once, in chain order.
                context, _ = _engine_context(
                    config, clients, run_id=run_id, now=base + timedelta(minutes=1)
                )
                engine.process(
                    context,
                    _memory_tick_state(
                        contracts,
                        cycle_id=2,
                        blockers=[
                            {
                                "engine": "data_guard",
                                "reason": "stale candles",
                                "status": "BLOCK",
                            },
                            {
                                "engine": "safety",
                                "reason": "drawdown past the limit",
                                "status": "BLOCK",
                            },
                        ],
                    ),
                )

                # Tick 3: nothing blocked.
                context, _ = _engine_context(
                    config, clients, run_id=run_id, now=base + timedelta(minutes=2)
                )
                engine.process(context, _memory_tick_state(contracts, cycle_id=3))

                # Tick 4: an ERROR rather than a BLOCK. `EngineStatus` is a `StrEnum`
                # precisely so this reaches the column as `ERROR` and not as
                # `EngineStatus.ERROR`; `safety` counts the error rate with
                # `status = 'ERROR'` and the mismatch would never raise - the count
                # would simply read zero forever.
                context, _ = _engine_context(
                    config, clients, run_id=run_id, now=base + timedelta(minutes=3)
                )
                engine.process(
                    context,
                    _memory_tick_state(
                        contracts,
                        cycle_id=4,
                        blockers=[
                            {
                                "engine": "market_sensor",
                                "reason": "engine raised",
                                "status": "ERROR",
                            }
                        ],
                    ),
                )

            rows = _block_rows(db_path)

    by_cycle: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_cycle.setdefault(int(row["cycle_id"]), []).append(row)

    candidateless = by_cycle.get(1, [])
    if len(candidateless) != 1:
        return failed(
            "a tick where `data_guard` blocked and no candidate ever existed wrote "
            + str(len(candidateless))
            + " block_records rows, expected exactly 1. Invariant 12 is not `rejections "
            "are logged`: `safety`'s outage counter is built from this table and most "
            "blocked ticks never had a candidate, so a writer that needs one leaves the "
            "breaker reading zero through the entire outage."
        )
    if str(candidateless[0]["blocked_by"]) != "data_guard":
        return failed(
            "the candidate-less blocked tick recorded blocked_by = "
            + repr(candidateless[0]["blocked_by"])
            + ", not the engine that blocked it"
        )

    doubled = by_cycle.get(2, [])
    if len(doubled) != 2:
        return failed(
            "a tick on which two guards blocked wrote "
            + str(len(doubled))
            + " block_records rows, expected 2. The guard chain never breaks early, so "
            "`data_guard` and `safety` can both block on one tick; one row per tick "
            "passes a naive count and loses half of invariant 12's record."
        )
    order = [str(row["blocked_by"]) for row in doubled]
    if order != ["data_guard", "safety"]:
        return failed("the two blockers were not recorded in chain order; got " + repr(order))
    primaries = [bool(row["is_primary"]) for row in doubled]
    if primaries != [True, False]:
        return failed(
            "is_primary on the two-blocker tick was "
            + repr(primaries)
            + ", expected [True, False]. The primary blocker is the one that gated the "
            "opportunity chain, and it is the first; marking every row primary makes "
            "`ux_block_records_primary` meaningless and marking none loses which gate "
            "actually stopped the tick."
        )

    unblocked = by_cycle.get(3, [])
    if unblocked:
        return failed(
            "an unblocked tick wrote "
            + str(len(unblocked))
            + " block_records row(s). A row on every tick makes every count that reads "
            "this table meaningless - the outage run becomes the uptime."
        )

    errored = by_cycle.get(4, [])
    if len(errored) != 1:
        return failed(
            "a tick whose blocker reported ERROR wrote "
            + str(len(errored))
            + " block_records rows, expected 1"
        )
    status = errored[0]["status"]
    if status != "ERROR":
        return failed(
            "block_records.status for an ERROR blocker reached the column as "
            + repr(status)
            + " rather than 'ERROR'. `safety` counts the error rate with "
            "`status = 'ERROR'`; this mismatch never raises and the count simply "
            "reads zero forever."
        )

    return passed(
        "4 ticks, "
        + str(len(rows))
        + " rows: candidate-less block wrote 1, two-guard tick wrote 2 with is_primary "
        "on the first only, unblocked tick wrote 0, and an ERROR blocker reached the "
        "column as the string 'ERROR'"
    )


# --- memory_writes_safety_inputs_live -------------------------------------- #


def _safety_readings(
    engine_cls: Any, config: Any, store_cls: Any, db_path: Path, now: datetime
) -> tuple[Mapping[str, Any] | None, Outcome | None]:
    """Engine 17's six readings against whatever is in `db_path`.

    Cycle 1 under a `run_id` neither database carries: the first tick of a new
    process, which the outage walk must treat as continuing an outage across a
    restart rather than resetting it. Anchoring under one of the stored `run_id`s
    makes the walk refuse to cross into itself and reports zero - correct behaviour,
    wrong question.
    """
    with store_cls(db_path) as store:
        clients, problem = _fake_clients(store=store)
        if clients is None:
            return None, problem
        context, problem = _engine_context(
            config, clients, run_id="verify-phase-4-safety", now=now
        )
        if context is None:
            return None, problem
        result = engine_cls().process(context, _safety_state(cycle_id=1))
    return dict(result.data or {}), None


def check_memory_writes_safety_inputs_live(ctx: VerifyContext) -> Outcome:
    """`safety` reading engine 19's **live** rows reaches the seed's six totals.

    This is the criterion that closes the one forward dependency in the project. Every
    one of `safety`'s six inputs is produced by engine 19, which is Phase 4; `safety`
    was built in Phase 3 and was proved against B's Phase 0 seed because its producer
    did not exist. The proof that the seam is real is **the same six numbers from two
    independent producers** - B's seed generator, and C's engine 19 - so the assertion
    is on the numbers and never on the tables being non-empty.

    The facts engine 19 is driven with are the seed's own facts, replayed as `state`
    payloads through the real `EngineContext` and the real store contracts. That is
    fabricating the *subject* - engines 18, 21 and 22 are Phase 6 and there is nothing
    else to publish those payloads - and never the contract.

    **The equity replay is two ticks on purpose.** The first establishes the peak, the
    second drops to the seed's closing equity. An engine 19 that recomputed
    `peak_equity` from the current tick rather than reading the running maximum out of
    the store reports a peak equal to that tick's equity, a drawdown of zero, and this
    criterion FAILs on `drawdown_pct`. A one-tick replay could not tell the two apart.
    """
    with root_import_path(ctx.root):
        memory_cls, contracts, problem = _memory_engine()
        if memory_cls is None:
            return problem or pending("engine 19 `memory` does not exist yet")
        safety_cls, problem = _engine_class("acsoe.engines.safety.engine", "safety")
        if safety_cls is None:
            return problem or pending("engine 17 `safety` does not exist yet")
        store_contracts, problem = try_import("acsoe.clients.store.contracts")
        if store_contracts is None:
            return problem or pending("acsoe.clients.store.contracts does not exist yet")
        config, problem = _phase3_config()
        if config is None:
            return problem or pending("the committed config could not be loaded")
        currency = str(config.get(KEY_REPORTING_CURRENCY))

        with console_workspace() as tmp:
            seed_path, _config, early = _seed_workspace(ctx, tmp)
            if seed_path is None:
                return early or pending("the Phase 0 seed is not available")
            store_cls, problem = _store_class()
            if store_cls is None:
                return problem or pending("acsoe.clients.store.client does not exist yet")

            seed_now = _seed_now(seed_path)
            seeded, problem = _safety_readings(
                safety_cls, config, store_cls, seed_path, seed_now
            )
            if seeded is None:
                return problem or pending("engine 17 could not be driven over the seed")

            live_path, _cls, problem = _migrated_db(tmp)
            if live_path is None:
                return problem or pending("acsoe.clients.store.client does not exist yet")

            replayed, problem = _replay_seed_through_memory(
                memory_cls,
                contracts,
                config,
                store_cls,
                store_contracts,
                seed_path,
                live_path,
                currency=currency,
                now=seed_now,
            )
            if problem is not None:
                return problem

            live, problem = _safety_readings(
                safety_cls, config, store_cls, live_path, seed_now
            )
            if live is None:
                return problem or pending("engine 17 could not be driven over the live rows")

    missing = [f for f in SAFETY_INPUT_FIELDS if f not in live or f not in seeded]
    if missing:
        return failed(
            "engine 17 published no reading for " + ", ".join(missing) + " on one side"
        )

    disagreements: list[str] = []
    for field in SAFETY_INPUT_FIELDS:
        left, right = seeded[field], live[field]
        same = (
            as_decimal(left, "seed." + field) == as_decimal(right, "live." + field)
            if isinstance(left, str) and "." in str(left)
            else str(left) == str(right)
        )
        if not same:
            disagreements.append(f"{field}: seed={left!r} live={right!r}")
    if disagreements:
        return failed(
            "`safety` read different numbers from engine 19's live rows than from the "
            "Phase 0 seed - " + "; ".join(disagreements) + ". The seam Phase 3 was "
            "forced to seed around is not closed: one of the two producers is wrong and "
            "the live one is the new arrival."
        )

    return passed(
        "engine 19 wrote "
        + str(replayed)
        + " rows across five tables and `safety` reached the same six totals from them "
        "as from the Phase 0 seed (drawdown "
        + str(live["drawdown_pct"])
        + f", {live['consecutive_losses']} losing trade(s), "
        + f"{live['errors_in_window']} error block(s), {live['stored_data_blocks']} "
        + f"outage tick(s), {live['open_positions']} position(s), "
        + f"{live['resting_entry_orders']} resting order(s))"
    )


def _rows_as_state(rows: Sequence[Any]) -> list[dict[str, Any]]:
    """Row models as JSON payloads an engine could legally publish in `state`.

    `mode="json"` because `state` carries no `Decimal` - contract rule 8 - and money
    crosses it as an exact decimal string. Dumping with `mode="python"` here would
    hand engine 19 `Decimal` objects it will never see from a real engine, and a
    writer that only works on those is a writer that fails on its first live tick.
    """
    return [row.model_dump(mode="json") for row in rows]


def _replay_seed_through_memory(
    memory_cls: Any,
    contracts: Any,
    config: Any,
    store_cls: Any,
    store_contracts: ModuleType,
    seed_path: Path,
    live_path: Path,
    *,
    currency: str,
    now: datetime,
) -> tuple[int, Outcome | None]:
    """Drive engine 19 with the seed's own facts and return the row count it wrote.

    Read out of the seed through B's real `StoreClient` rather than by SQL wherever a
    method exists, so the payloads engine 19 is handed are the real row models.
    """
    written = 0
    with store_cls(seed_path) as seed_store:
        positions = _rows_as_state(seed_store.open_positions())
        orders = _rows_as_state(
            seed_store.resting_orders(intent=store_contracts.OrderIntent.ENTRY)
        )
        trades = _rows_as_state(seed_store.recent_closed_trades(100_000))
        peak, closing = _seed_equity_bounds(seed_path)
    blocks = _block_rows(seed_path)
    if peak is None or closing is None:
        return 0, pending("the Phase 0 seed carries no equity_snapshots row")

    # Trades come back newest first; `safety` walks the trailing run ordered by
    # `closed_at`, so they are replayed oldest first and the run is rebuilt in order.
    trades = sorted(trades, key=lambda row: int(row["closed_at"]))

    engine = memory_cls()
    with store_cls(live_path) as store:
        clients, problem = _fake_clients(store=store)
        if clients is None:
            return 0, problem

        # 1. The block records, tick by tick, under the seed's own run_ids, cycle_ids
        #    and timestamps. The outage run and the error-rate window are both
        #    properties of *which ticks* carry a `data_guard` row and *when*, so
        #    replaying them under fresh identifiers would answer a different question.
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
        order: list[tuple[str, int]] = []
        for row in blocks:
            tick = (str(row["run_id"]), int(row["cycle_id"]))
            if tick not in grouped:
                grouped[tick] = []
                order.append(tick)
            grouped[tick].append(row)
        for run_id, cycle_id in order:
            rows = sorted(grouped[(run_id, cycle_id)], key=lambda r: not bool(r["is_primary"]))
            context, problem = _engine_context(
                config,
                clients,
                run_id=run_id,
                now=datetime.fromtimestamp(int(rows[0]["ts"]) / MICROSECONDS, tz=UTC),
            )
            if context is None:
                return 0, problem
            engine.process(
                context,
                _memory_tick_state(
                    contracts,
                    cycle_id=cycle_id,
                    blockers=[
                        {
                            "engine": str(r["blocked_by"]),
                            "reason": str(r["block_reason"]),
                            "status": str(r["status"]),
                        }
                        for r in rows
                    ],
                ),
            )
            written += len(rows)

        # 2. Positions and resting orders, as engines 18, 21 and 22 will publish them.
        context, problem = _engine_context(
            config, clients, run_id="verify-phase-4-replay", now=now
        )
        if context is None:
            return 0, problem
        engine.process(
            context,
            _memory_tick_state(
                contracts,
                cycle_id=1,
                extra={
                    str(contracts.POSITION_MANAGER_KEY): {
                        str(contracts.POSITIONS_FIELD): positions,
                        str(contracts.ORDERS_FIELD): orders,
                        str(contracts.HOLD_REASON_FIELD): None,
                    }
                },
            ),
        )
        written += len(positions) + len(orders)

        # 3. The closed trades, oldest first.
        context, _ = _engine_context(
            config, clients, run_id="verify-phase-4-replay", now=now
        )
        engine.process(
            context,
            _memory_tick_state(
                contracts,
                cycle_id=2,
                extra={
                    str(contracts.EXIT_KEY): {
                        str(contracts.CLOSED_TRADES_FIELD): trades,
                        "positions_closed": True,
                    }
                },
            ),
        )
        written += len(trades)

        # 4. Equity: the peak first, then the close. Two ticks, because one cannot
        #    tell a `peak_equity` read from the store from one recomputed here.
        for index, equity in enumerate((peak, closing), start=3):
            context, _ = _engine_context(
                config, clients, run_id="verify-phase-4-replay", now=now
            )
            engine.process(
                context,
                _memory_tick_state(
                    contracts,
                    cycle_id=index,
                    extra={
                        str(contracts.EXCHANGE_KEY): {
                            str(contracts.BALANCES_FIELD): {currency: format(equity, "f")},
                            "fetched_at": int(now.timestamp() * MICROSECONDS),
                        }
                    },
                ),
            )
            written += 1
    return written, None


def _seed_equity_bounds(db_path: Path) -> tuple[Decimal | None, Decimal | None]:
    """(peak_equity, equity) of the seed's most recent `equity_snapshots` row.

    `safety`'s drawdown is `(peak_equity - equity) / peak_equity` on the **latest**
    row - `architecture-context.md`'s input table says so - so these two numbers are
    the whole of what the live rows have to reproduce.
    """
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT equity, peak_equity FROM equity_snapshots ORDER BY ts DESC, rowid DESC "
            "LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None, None
    return (
        as_decimal(row[1], "equity_snapshots.peak_equity"),
        as_decimal(row[0], "equity_snapshots.equity"),
    )


# --- rejections_survive_restart -------------------------------------------- #

#: Deliberately specific, and deliberately not a value any seed generator would
#: produce. A restart test that only counts rows passes against a writer that loses
#: every column, so the assertion is on the values.
REJECTION_PROBE: Final[Mapping[str, str]] = {
    "reason_code": "net_edge_below_hurdle",
    "reason": "Net edge -0.2137% after fees",
    "expected_move_pct": "0.0191",
    "friction_pct": "0.0093",
    "net_edge_pct": "-0.002137",
    "hurdle_pct": "0.01395",
}


def check_rejections_survive_restart(ctx: VerifyContext) -> Outcome:
    """A rejection written under one `run_id` is intact after a restart under another.

    Invariant 12: a rejection that does not reach storage counts as a defect equal to
    a lost trade. "Reaches storage" means the row and **its columns** - the reason
    code the console maps to prose, the operator-facing reason, and the economics that
    make it analysable later. A criterion that counted rows would pass against a
    writer that lost every one of them.

    The store is closed and reopened between the write and the read, and the reader
    runs under a different `run_id`, because "still in this process's memory" and
    "on disk" are the two things this criterion exists to tell apart.
    """
    with root_import_path(ctx.root):
        engine_cls, contracts, problem = _memory_engine()
        if engine_cls is None:
            return problem or pending("engine 19 `memory` does not exist yet")
        config, problem = _phase3_config()
        if config is None:
            return problem or pending("the committed config could not be loaded")

        with console_workspace() as tmp:
            db_path, store_cls, problem = _migrated_db(tmp)
            if db_path is None:
                return problem or pending("acsoe.clients.store.client does not exist yet")

            pair = "VERIFY/PROBE"
            economics = {
                key: value for key, value in REJECTION_PROBE.items() if key.endswith("_pct")
            }
            with store_cls(db_path) as store:
                clients, problem = _fake_clients(store=store)
                if clients is None:
                    return problem or pending("test doubles unavailable")
                context, problem = _engine_context(
                    config, clients, run_id="verify-phase-4-before", now=PHASE3_NOW
                )
                if context is None:
                    return problem or pending("acsoe.core.contracts does not exist yet")
                engine_cls().process(
                    context,
                    _memory_tick_state(
                        contracts,
                        cycle_id=7,
                        extra=_rejection_extra(
                            contracts,
                            pair=pair,
                            rejected_by="cost",
                            reason=REJECTION_PROBE["reason"],
                            reason_code=REJECTION_PROBE["reason_code"],
                            economics=economics,
                        ),
                    ),
                )

            # The process boundary this criterion exists to cross.
            with store_cls(db_path) as reopened:
                rows = reopened.recent_rejections(50)

    found = [row for row in rows if row.pair == pair]
    if not found:
        return failed(
            "no rejection survived the restart. Invariant 12 puts a lost rejection on "
            "the same footing as a lost trade, and the console's history screen reads "
            "this table."
        )
    row = found[0]
    for field, expected in REJECTION_PROBE.items():
        actual = getattr(row, field, None)
        if actual is None:
            return failed(
                "the rejection survived the restart with `" + field + "` null. A "
                "restart test that only counts rows passes against a writer that loses "
                "every column, which is why this one asserts the values."
            )
        same = (
            as_decimal(actual, "rejection." + field) == Decimal(expected)
            if field.endswith("_pct")
            else str(actual) == expected
        )
        if not same:
            return failed(
                f"the rejection's `{field}` came back as {actual!r}, not {expected!r}"
            )
    if row.run_id != "verify-phase-4-before":
        return failed(
            "the rejection came back stamped with run_id "
            + repr(row.run_id)
            + "; it must carry the run that wrote it, not the one that read it"
        )
    return passed(
        "a rejection written under one run_id survived a close and reopen under "
        "another with its reason_code, its operator-facing reason and all four "
        "economics columns intact"
    )


# --- labelled_sample_replayed_from_archive --------------------------------- #


def _polars() -> tuple[Any, Outcome | None]:
    module, problem = try_import("polars")
    if module is None:
        return None, problem or pending("polars is not installed")
    return module, None


def check_labelled_sample_replayed_from_archive(ctx: VerifyContext) -> Outcome:
    """`tests/fixtures/labelled_sample.parquet` is a real replay, not a hand-written file.

    The question to ask of this criterion is the one spec 56 asks: **would it still
    pass if the parquet had been written by hand?** Three assertions exist because the
    answer has to be no.

    * **Provenance in the file.** The archive it came from, the span, the barrier
      settings it was labelled under, the ambiguous count, and the statement that the
      source carries no spread and no book. A parquet that cannot say where it came
      from is indistinguishable from one somebody typed.
    * **The barrier settings in the provenance match the committed config.** A fixture
      labelled under different barriers is evidence about a system nobody is building.
    * **The horizon.** No labelled decision bar may sit within `barriers.timeout_bars`
      of the end of its pair's series. Labelling such a bar `timeout` records an
      outcome that has not happened yet, and it is the single easiest mistake to make
      in the labeller - invariant 10 with a different face.
    """
    fixture = ctx.root / LABELLED_SAMPLE_REL
    if not fixture.is_file():
        return pending(
            LABELLED_SAMPLE_REL + " has not been deposited yet (spec 56, agent C); it "
            "needs A's archive from spec 54 and the labeller from spec 52"
        )
    config, problem = load_config(ctx.root)
    if config is None:
        return problem or pending("config/default.yaml could not be read")
    thresholds, problem = required_thresholds(
        config, (KEY_TARGET_PCT, KEY_STOP_PCT, KEY_TIMEOUT_BARS)
    )
    if problem is not None:
        return problem

    with root_import_path(ctx.root):
        pl, problem = _polars()
        if pl is None:
            return problem or pending("polars is not installed")
        try:
            frame = pl.read_parquet(fixture)
            metadata = pl.read_parquet_metadata(fixture)
        except Exception as exc:  # a corrupt payload is a FAIL, not a crash
            return failed(
                LABELLED_SAMPLE_REL
                + " did not parse as parquet: "
                + f"{type(exc).__name__}: {exc}"[:300]
                + ". `.gitattributes` marks tests/fixtures/** as -text precisely "
                "because a CRLF conversion on a parquet payload corrupts it."
            )

    missing = [c for c in LABELLED_SAMPLE_COLUMNS if c not in frame.columns]
    if missing:
        return failed(
            LABELLED_SAMPLE_REL + " is missing column(s) " + ", ".join(missing) + ". "
            "`label_window_end_ts` in particular is what the walk-forward splitter "
            "purges on; without it a fold cannot be purged at all."
        )
    if frame.height == 0:
        return failed(LABELLED_SAMPLE_REL + " holds no rows")

    provenance_raw = metadata.get("acsoe_provenance") if metadata else None
    if provenance_raw is None:
        return failed(
            LABELLED_SAMPLE_REL + " carries no `acsoe_provenance` key-value metadata. "
            "Spec 56 requires the provenance to live *in the file*: which archive, "
            "which span, which barrier settings, how many labels were ambiguous, and "
            "the statement that the source carries no spread and no book."
        )
    try:
        provenance = json.loads(provenance_raw)
    except json.JSONDecodeError as exc:
        return failed("acsoe_provenance is not JSON: " + str(exc)[:200])
    absent = [k for k in LABELLED_SAMPLE_PROVENANCE if k not in provenance]
    if absent:
        return failed("acsoe_provenance is missing " + ", ".join(absent))

    labels = [str(value) for value in frame["label"].to_list()]
    unknown = sorted({label for label in labels if label not in BARRIER_LABELS})
    if unknown:
        return failed(
            "labels outside the triple barrier: "
            + ", ".join(unknown)
            + ". There is no fourth outcome."
        )
    for label in BARRIER_LABELS:
        if label not in labels:
            return failed(
                "no `" + label + "` label in the sample. All three outcomes must occur "
                "or the criterion cannot tell a labeller that emits one from one that "
                "emits three."
            )

    for key, dotted in (
        ("target_pct", KEY_TARGET_PCT),
        ("stop_pct", KEY_STOP_PCT),
        ("timeout_bars", KEY_TIMEOUT_BARS),
    ):
        stated = str(provenance[key])
        configured = str(thresholds[dotted])
        if Decimal(stated) != Decimal(configured):
            return failed(
                "the sample was labelled with "
                + key
                + " = "
                + stated
                + " but config/default.yaml says "
                + configured
                + ". A fixture labelled under different barriers is evidence about a "
                "system nobody is building."
            )

    # Read as `is not True`, never as falsiness. The field is `bool | None`: `True` is
    # Kraken's own published history, where a hole can only mean no trades occurred;
    # `False` is an archive built from our own recording, where a hole is *either* a
    # quiet interval *or* an interval nobody was watching; and `None` is a sidecar that
    # never heard of the question. A triple barrier walked across a not-recorded stretch
    # reads as a calm market and returns `timeout` where the real market touched a
    # barrier - a fabricated outcome with nothing to say so. Invariant 3: the absence of
    # a no is not a yes.
    if provenance["holes_mean_no_trades"] is not True:
        return failed(
            "the sample's archive does not state that its holes mean no trades occurred "
            "(holes_mean_no_trades="
            + repr(provenance["holes_mean_no_trades"])
            + "). Every gapped window in this fixture is then a label walked across an "
            "interval that may simply not have been recorded, which fabricates the "
            "outcome the model learns from."
        )

    interval_s = int(provenance["interval_s"])
    timeout_bars = int(thresholds[KEY_TIMEOUT_BARS])
    span_end = int(provenance["span_end_ts"])
    horizon = timeout_bars * interval_s
    latest = max(int(value) for value in frame["decision_ts"].to_list())
    if latest + horizon > span_end:
        return failed(
            "a labelled decision bar at "
            + str(latest)
            + " sits inside the timeout horizon of the series end at "
            + str(span_end)
            + " (horizon "
            + str(horizon)
            + "s). A bar whose window runs past the end of the data is excluded, never "
            "labelled `timeout` - labelling it records an outcome that has not happened "
            "yet, which is invariant 10 with a different face."
        )

    ambiguous = int(provenance["ambiguous_count"])
    stated_ambiguous = sum(1 for value in frame["ambiguous"].to_list() if bool(value))
    if ambiguous != stated_ambiguous:
        return failed(
            "acsoe_provenance says "
            + str(ambiguous)
            + " ambiguous label(s) but the frame carries "
            + str(stated_ambiguous)
        )

    return passed(
        str(frame.height)
        + " labelled bars from "
        + str(provenance["archive"])
        + " ("
        + str(provenance["pair"])
        + "), all three outcomes present, "
        + str(ambiguous)
        + " ambiguous, latest decision bar "
        + str(span_end - latest)
        + "s before the series end against a "
        + str(horizon)
        + "s horizon"
    )


# --- labeller_matches_hand_verified_labels --------------------------------- #


def check_labeller_matches_hand_verified_labels(ctx: VerifyContext) -> Outcome:
    """The labeller reproduces every row of the hand-verified fixture, exactly.

    One mismatch is a FAIL, not a tolerance. The fixture's value is that it was
    checked against the printed candle window by hand rather than produced by running
    the labeller and saving the output - a fixture built that way proves only that the
    labeller equals itself.

    The candles travel **in the fixture**. The archive lives under `data/`, which is
    gitignored, and a criterion that read one would pass only on the machine that
    downloaded it.
    """
    fixture = ctx.root / HAND_VERIFIED_REL
    if not fixture.is_file():
        return pending(
            HAND_VERIFIED_REL + " has not been deposited yet (spec 52, agent C)"
        )
    try:
        document = json.loads(fixture.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return failed(HAND_VERIFIED_REL + " did not parse: " + str(exc)[:200])
    entries = document.get("entries") if isinstance(document, Mapping) else None
    if not isinstance(entries, list) or not entries:
        return failed(HAND_VERIFIED_REL + " carries no `entries` list")
    if len(entries) != 20:
        return failed(
            HAND_VERIFIED_REL
            + " carries "
            + str(len(entries))
            + " entries; spec 52 requires 20 hand-verified labels"
        )

    config, problem = load_config(ctx.root)
    if config is None:
        return problem or pending("config/default.yaml could not be read")
    _thresholds, problem = required_thresholds(
        config, (KEY_TARGET_PCT, KEY_STOP_PCT, KEY_TIMEOUT_BARS)
    )
    if problem is not None:
        return problem

    with root_import_path(ctx.root):
        module, problem = try_import("acsoe.research.labelling")
        if module is None:
            if problem is not None and problem.result is Result.FAIL:
                return problem
            return pending(
                "acsoe.research.labelling does not exist yet ("
                + PHASE4_RESEARCH["acsoe.research.labelling"]
                + ")"
            )
        labeller, missing = module_attr(module, "label_candles")
        if labeller is None:
            return pending(missing)
        engine_config, problem = _phase3_config()
        if engine_config is None:
            return problem or pending("the committed config could not be loaded")

        mismatches: list[str] = []
        excluded_seen = 0
        ambiguous_seen = 0
        for index, entry in enumerate(entries):
            candles = [
                {
                    "ts": int(row["ts"]),
                    "open": Decimal(str(row["open"])),
                    "high": Decimal(str(row["high"])),
                    "low": Decimal(str(row["low"])),
                    "close": Decimal(str(row["close"])),
                    "volume": Decimal(str(row.get("volume", "0"))),
                    "trades": int(row.get("trades", 0)),
                }
                for row in entry["candles"]
            ]
            produced = labeller(
                candles,
                pair=str(entry["pair"]),
                decision_ts=int(entry["decision_ts"]),
                config=engine_config,
                interval_s=int(entry["interval_s"]),
            )
            expected_label = entry["expected_label"]
            if expected_label is None:
                excluded_seen += 1
                if produced is not None:
                    mismatches.append(
                        f"[{index}] {entry['pair']}@{entry['decision_ts']}: expected to "
                        f"be excluded (its window runs past the end of the series) but "
                        f"the labeller returned {produced.label!r}"
                    )
                continue
            if produced is None:
                mismatches.append(
                    f"[{index}] {entry['pair']}@{entry['decision_ts']}: expected "
                    f"{expected_label!r}, the labeller excluded it"
                )
                continue
            if bool(entry.get("ambiguous")):
                ambiguous_seen += 1
            checks: list[tuple[str, Any, Any]] = [
                ("label", expected_label, produced.label),
                ("touch_ts", entry["expected_touch_ts"], produced.touch_ts),
                ("bars_elapsed", entry["expected_bars_elapsed"], produced.bars_elapsed),
                ("target_price", entry["target_price"], format(produced.target_price, "f")),
                ("stop_price", entry["stop_price"], format(produced.stop_price, "f")),
                ("ambiguous", bool(entry.get("ambiguous")), bool(produced.ambiguous)),
            ]
            for field, expected, actual in checks:
                if field in ("target_price", "stop_price"):
                    same = Decimal(str(expected)) == Decimal(str(actual))
                else:
                    same = expected == actual
                if not same:
                    mismatches.append(
                        f"[{index}] {entry['pair']}@{entry['decision_ts']} {field}: "
                        f"hand-verified {expected!r}, labeller {actual!r}"
                    )

    if mismatches:
        return failed(
            str(len(mismatches))
            + " disagreement(s) with the hand-verified fixture, and one is a FAIL: "
            + "; ".join(mismatches[:4])
        )
    if excluded_seen == 0:
        return failed(
            "the hand-verified fixture carries no entry that must be excluded for "
            "running past the end of its series. That is the case spec 52 names, and "
            "a fixture without it cannot fail against a labeller that labels those "
            "bars `timeout`."
        )
    if ambiguous_seen == 0:
        return failed(
            "the hand-verified fixture carries no bar that touched both barriers. "
            "Ruling 1 - both barriers touched is `stop` - is untested without one, and "
            "it is the ruling that stops the labels flattering the strategy."
        )
    return passed(
        "all 20 hand-verified labels reproduced exactly, including "
        + str(excluded_seen)
        + " end-of-series exclusion(s) and "
        + str(ambiguous_seen)
        + " bar(s) that touched both barriers"
    )


# --- walkforward_folds_purged_and_embargoed -------------------------------- #

#: One bar, in seconds, **of the four-row dataset this criterion constructs** - not of
#: the system. The constructed fold is expressed in bars so the embargo, which config
#: states in bars, lands on a boundary this criterion can reason about without restating
#: a duration anywhere.
#:
#: Deliberately a literal and deliberately **not** `timeframes.decision_bar_s`. The rows
#: here are built by this criterion, so the interval is a property of the fixture; making
#: it track a threshold the operator may retune would let a criterion start failing for
#: reasons that have nothing to do with its subject.
#:
#: Named `_CONSTRUCTED_` rather than `_FOLD_` because the earlier name read as "the
#: interval", and `check_replay_full_archive` reached for it to load a **real** archive -
#: where the interval is the grid every gap statistic is measured against and config is
#: the only honest source. That criterion now reads the config key.
_CONSTRUCTED_INTERVAL_S: Final = 900


def check_walkforward_folds_purged_and_embargoed(ctx: VerifyContext) -> Outcome:
    """A straddling label window is purged, and an embargoed row is dropped - by identity.

    **An end-to-end "the folds do not overlap" check cannot see the difference between
    a correct embargo and none at all**, because the fold *indices* do not overlap in
    either case. The leak is in the **label windows**, and it is invisible unless the
    criterion builds one that straddles the boundary on purpose. So this criterion
    constructs the dataset rather than reading one.

    Four rows, and each exists to be distinguishable from the others:

    * `safe` - decision bar and label window both comfortably inside training. Must
      survive, or the criterion is passing a splitter that returns nothing.
    * `straddler` - decision bar comfortably inside training, label window ending
      **inside the test window**. Must be purged. A splitter that purged on the
      decision bar timestamp instead of the window end keeps this row, which is the
      single most plausible wrong implementation.
    * `embargoed` - decision bar and label window both **after** the test window,
      inside the embargo span. Must be dropped. Nothing about its label window
      straddles anything, so a purge alone cannot remove it and an embargo of zero
      keeps it.
    * `after_embargo` - past the embargo span. Must survive, or the criterion would
      pass against a splitter that dropped everything after the test window.

    The last two are what make the embargo assertion independent of the purge
    assertion: a test that would pass with the embargo set to zero is not testing the
    embargo.
    """
    config_map, problem = load_config(ctx.root)
    if config_map is None:
        return problem or pending("config/default.yaml could not be read")
    values, problem = required_thresholds(config_map, (KEY_EMBARGO_BARS,))
    if problem is not None:
        return pending(
            "config/default.yaml carries no `"
            + KEY_EMBARGO_BARS
            + "`. Only the lead adds a config key (spec 58), and the splitter must "
            "refuse to run without an embargo rather than default one to zero - a "
            "silent zero is exactly the defect this criterion exists to catch."
        )
    embargo_bars = int(values[KEY_EMBARGO_BARS])
    if embargo_bars <= 0:
        return failed(
            KEY_EMBARGO_BARS
            + " is "
            + str(embargo_bars)
            + ". An embargo of zero is no embargo: serial correlation carries "
            "information across the boundary even where no label window literally "
            "straddles it."
        )

    with root_import_path(ctx.root):
        module, problem = try_import("acsoe.research.walkforward")
        if module is None:
            if problem is not None and problem.result is Result.FAIL:
                return problem
            return pending(
                "acsoe.research.walkforward does not exist yet ("
                + PHASE4_RESEARCH["acsoe.research.walkforward"]
                + ")"
            )
        splitter, missing = module_attr(module, "purged_walk_forward")
        if splitter is None:
            return pending(missing)
        engine_config, problem = _phase3_config()
        if engine_config is None:
            return problem or pending("the committed config could not be loaded")

        train_days = int(engine_config.get("backtest.training_window_days"))
        test_days = int(engine_config.get("backtest.retrain_interval_days"))
        day = 86_400
        origin = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
        test_start = origin + train_days * day
        test_end = test_start + test_days * day
        embargo_end = test_end + embargo_bars * _CONSTRUCTED_INTERVAL_S

        rows = [
            {
                "label_id": "safe",
                "decision_ts": test_start - 30 * day,
                "label_window_end_ts": test_start - 29 * day,
            },
            {
                # Comfortably inside training by its decision bar, and its label window
                # ends a day *inside* the test window. This is the leak.
                "label_id": "straddler",
                "decision_ts": test_start - 2 * day,
                "label_window_end_ts": test_start + day,
            },
            {
                "label_id": "embargoed",
                "decision_ts": test_end + _CONSTRUCTED_INTERVAL_S,
                "label_window_end_ts": test_end + 2 * _CONSTRUCTED_INTERVAL_S,
            },
            {
                "label_id": "after_embargo",
                "decision_ts": embargo_end + day,
                "label_window_end_ts": embargo_end + day + _CONSTRUCTED_INTERVAL_S,
            },
        ]
        try:
            folds = splitter(
                rows,
                config=engine_config,
                interval_s=_CONSTRUCTED_INTERVAL_S,
                test_start_ts=test_start,
                test_end_ts=test_end,
            )
        except TypeError as exc:
            return pending(
                "acsoe.research.walkforward.purged_walk_forward does not accept the "
                "constructed-fold call this criterion makes: " + str(exc)[:200]
            )

    if not folds:
        return failed(
            "the splitter returned no folds for a dataset spanning the training "
            "window, the test window and the embargo. Spec 53 forbids silently "
            "dropping a fold that comes out empty - report it."
        )
    fold = folds[0]
    train_ids = [str(rows[i]["label_id"]) for i in fold.train_index]

    if "safe" not in train_ids:
        return failed(
            "the splitter dropped `safe`, whose decision bar and label window are both "
            "a month inside the training window. A splitter that returns an empty "
            "training set satisfies every purge assertion and trains nothing."
        )
    if "straddler" in train_ids:
        return failed(
            "`straddler` survived into the training index. Its decision bar is two days "
            "inside the training window but its label window ends a day inside the test "
            "window, so the row's outcome is built from test-period bars. A splitter "
            "purging on `decision_ts` rather than on `label_window_end_ts` keeps exactly "
            "this row, and nothing downstream will ever say so: the backtest simply "
            "reports a Sharpe the live system will never see."
        )
    if "embargoed" in train_ids:
        return failed(
            "`embargoed` survived into the training index. It sits "
            + str(embargo_bars)
            + " bars or fewer after the test window, inside the configured embargo. No "
            "part of its label window straddles the boundary, so the purge cannot "
            "remove it - only the embargo can, and an embargo of zero keeps it."
        )
    if "after_embargo" not in train_ids:
        return failed(
            "`after_embargo` was dropped although it sits past the embargo span. The "
            "embargo is a bounded span, not a truncation of everything after the test "
            "window."
        )

    purged = getattr(fold, "purged_count", None)
    embargoed = getattr(fold, "embargoed_count", None)
    if purged is None or embargoed is None:
        return failed(
            "the fold does not expose `purged_count` and `embargoed_count`. Spec 53 "
            "makes them public because a count of zero purged rows on a dataset with "
            "overlapping windows is the symptom of the bug, and it is visible only if "
            "the number is reported."
        )
    if int(purged) != 1 or int(embargoed) != 1:
        return failed(
            "the fold reported purged="
            + str(purged)
            + ", embargoed="
            + str(embargoed)
            + "; the constructed dataset has exactly one of each, and a splitter that "
            "reports them in the wrong column is one whose two mechanisms are the same "
            "mechanism."
        )

    return passed(
        "a training row whose label window ends inside the test window was purged by "
        "identity, and a row "
        + str(embargo_bars)
        + " bars past the test window was embargoed, while a row a month earlier and a "
        "row past the embargo span both survived (purged=1, embargoed=1)"
    )


# --- console_history_reads_real_rows --------------------------------------- #

#: Values no seed generator produces. Spec 57 requires the seed and the live rows to
#: be distinguishable *by value* - a history test that passes against a seeded
#: database is not testing what this spec is for.
LIVE_ROW_PROBE: Final[Mapping[str, str]] = {
    "pair": "ZZZ/QQQ",
    "reason": "Net edge -0.4471% after fees",
    "reason_code": "net_edge_below_hurdle",
}


def check_console_history_reads_real_rows(ctx: VerifyContext) -> Outcome:
    """The history screen renders rows a live engine 19 wrote, not the seed's.

    The database is seeded first and then written to by engine 19, which is the
    honest picture: the console reads one table and cannot know which producer filled
    it. What makes the criterion mean something is that the live row carries a pair
    and a reason **no seed generator produces**, so the assertion cannot be satisfied
    by the seed. A rendering check that asserted only that the page came back cannot
    fail for the reason it exists.
    """
    with root_import_path(ctx.root):
        engine_cls, contracts, problem = _memory_engine()
        if engine_cls is None:
            return problem or pending("engine 19 `memory` does not exist yet")
        config, problem = console_config()
        if config is None:
            return problem or pending("the console config could not be built")
        store_cls, problem = _store_class()
        if store_cls is None:
            return problem or pending("acsoe.clients.store.client does not exist yet")
        # Read out of `console/format.py` rather than retyped here. The string is the
        # console's, and a criterion that retyped it could be wrong about it in exactly
        # the way it exists to catch - the sentence changes, this script keeps comparing
        # against the old one, and the silent-render check stops checking anything.
        format_mod, problem = try_import("acsoe.console.format")
        if format_mod is None:
            return problem or pending("acsoe.console.format does not exist yet")
        no_reason, missing = module_attr(format_mod, "NO_REASON_RECORDED")
        if no_reason is None:
            return pending(missing)

        with console_workspace() as tmp:
            db_path, early = seeded_console_db(tmp)
            if db_path is None:
                return early or pending("the Phase 0 seed is not available")

            with store_cls(db_path) as store:
                clients, problem = _fake_clients(store=store)
                if clients is None:
                    return problem or pending("test doubles unavailable")
                # Five minutes past the seed's own most recent instant, so the live
                # row is the newest thing in the table and cannot fall off the end of
                # a limit-bounded read. A criterion that depended on the seed being
                # small would pass here and fail on somebody's larger fixture.
                context, problem = _engine_context(
                    config,
                    clients,
                    run_id="verify-phase-4-console",
                    now=_seed_now(db_path) + timedelta(minutes=5),
                )
                if context is None:
                    return problem or pending("acsoe.core.contracts does not exist yet")
                engine_cls().process(
                    context,
                    _memory_tick_state(
                        contracts,
                        cycle_id=11,
                        extra=_rejection_extra(
                            contracts,
                            pair=LIVE_ROW_PROBE["pair"],
                            rejected_by="cost",
                            reason=LIVE_ROW_PROBE["reason"],
                            reason_code=LIVE_ROW_PROBE["reason_code"],
                        ),
                    ),
                )

            app, problem = console_app(config, db_path)
            if app is None:
                return problem or pending("the console could not be built")
            try:
                # The history *screen* is `/` plus `/api/history`; the rows themselves
                # reach the page through this endpoint, and it is the one that runs
                # `console/format.py` over them. Asserting on the shell alone would be
                # asserting that a page came back, which cannot fail for the reason
                # this criterion exists.
                shell = asgi_request(app, "GET", "/")
                response = asgi_request(app, "GET", "/api/history")
            finally:
                close_console(app)

    if shell.status != 200:
        return failed("the console shell returned " + str(shell.status))
    if response.status != 200:
        return failed("/api/history returned " + str(response.status))
    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as exc:
        return failed("/api/history did not return JSON: " + str(exc)[:200])

    rejections = payload.get("rejections") or []
    live = [row for row in rejections if row.get("pair") == LIVE_ROW_PROBE["pair"]]
    if not live:
        return failed(
            "the history screen rendered "
            + str(len(rejections))
            + " rejection(s) and none of them is the pair "
            + LIVE_ROW_PROBE["pair"]
            + ", which only a live engine 19 wrote into this database. The screen is "
            "still showing the seed, and the seed alone would satisfy any assertion "
            "that only counted rows."
        )
    rendered = str(live[0].get("reason") or "")
    if rendered == str(no_reason):
        return failed(
            "the live rejection rendered as "
            + repr(str(no_reason))
            + ". A `reason_code` engine 19 can write is missing from `REASON_PROSE` in "
            "console/format.py, and the console fails silently on exactly that - no "
            "error, no log line, just a row with nothing in its reason column."
        )
    if rendered != LIVE_ROW_PROBE["reason"]:
        return failed(
            "the live rejection rendered as "
            + repr(rendered)
            + " rather than the operator-facing reason engine 19 stored, "
            + repr(LIVE_ROW_PROBE["reason"])
        )
    if str(live[0].get("run_id")) != "verify-phase-4-console":
        return failed(
            "the rendered rejection is stamped with run_id "
            + repr(live[0].get("run_id"))
            + "; the live row carries the run that wrote it"
        )
    return passed(
        "the history screen rendered a rejection written by a live engine 19 - pair "
        + LIVE_ROW_PROBE["pair"]
        + ", run_id verify-phase-4-console, reason "
        + repr(rendered)
        + " - over a database that also carries the Phase 0 seed's "
        + str(len(rejections) - len(live))
        + " seeded rejection(s)"
    )


# --- replay_full_archive (--live only) ------------------------------------- #


def check_replay_full_archive(ctx: VerifyContext) -> Outcome:
    """`--live` only: replay the operator's real archive and report what it held.

    **PENDING rather than FAIL when no archive is present.** The operator has not
    downloaded one, and an opt-in criterion that FAILs on its absence makes `--live`
    useless for every other check in every other phase.

    **The interval comes from `timeframes.decision_bar_s`, never from a constant here
    and never from the archive's own report.** It is the grid every gap statistic is
    measured against: load a 15-minute archive at 30 minutes and `load_archive` reports
    half the expected bars, so most real gaps vanish and this criterion prints a
    confident, plausible, wrong number. Taking it from the report instead would be
    worse - the report's interval is whatever the caller loaded at, so it would agree
    with itself by construction. Config is the same authority engine 3 `market_sensor`
    and engine 23 `backtest` both read.
    """
    archive_dir = ctx.root / "data" / "historical"
    if not archive_dir.is_dir():
        return pending(
            "no archive under data/historical/ - download one and re-run with --live"
        )
    archives = sorted(archive_dir.glob("*.csv"))
    if not archives:
        return pending(
            "data/historical/ carries no .csv archive - this criterion is opt-in and "
            "reports PENDING rather than FAIL when the operator has not downloaded one"
        )
    config, problem = load_config(ctx.root)
    if config is None:
        return problem or pending("config/default.yaml could not be read")
    values, problem = required_thresholds(config, (KEY_DECISION_BAR_S,))
    if problem is not None:
        return problem
    interval_s = int(values[KEY_DECISION_BAR_S])
    with root_import_path(ctx.root):
        module, problem = try_import("acsoe.research.historical")
        if module is None:
            return problem or pending("acsoe.research.historical does not exist yet")
        loader, missing = module_attr(module, "load_archive")
        if loader is None:
            return pending(missing)
        reports = []
        for archive in archives:
            try:
                reports.append(loader(archive, interval_s=interval_s))
            except Exception as exc:
                return failed(
                    archive.name + " did not load: " + f"{type(exc).__name__}: {exc}"[:300]
                )
    spans = [
        (report.first_ts, report.last_ts)
        for report in reports
        if report.first_ts is not None and report.last_ts is not None
    ]
    if not spans:
        return failed("every archive under data/historical/ was empty")
    earliest = min(start for start, _ in spans)
    latest = max(end for _, end in spans)
    bars = sum(report.row_count for report in reports)
    gaps = sum(report.gap_count for report in reports)
    return passed(
        str(len(reports))
        + " archive(s), "
        + str(bars)
        + " bars spanning "
        + str((latest - earliest) // 86_400)
        + " days, "
        + str(gaps)
        + " gap run(s)"
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
# `TOOLCHAIN` was scoped to `src/` until Phase 4, when the operator ruled the widening
# that had been deferred since Phase 0 and declined once at the Phase 1 boundary. `ruff`
# now reads `src/`, `tests/` and `scripts/`, and `mypy --strict` reads `src/` and
# `scripts/`. What that catches, what it still does not, and why `mypy` stops short of
# `tests/` are all at `TOOLCHAIN` itself.
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

# Phase 3 - the economics gates. Spec 45, registered first in the phase and ahead of
# three of the four engines it judges, for the reason spec 00 was first in Phase 0 and
# spec 16 first in Phase 1. Until these existed `--phase 3` registered `docs_vocabulary`
# and `toolchain_green` alone and printed "Phase 3 is green: every criterion PASS, zero
# PENDING" over a phase in which engines 7, 10, 11 and 17 were unbuilt or unwired. A
# phase with nothing in it must not be able to report as finished, and PENDING is how it
# says so.
register(3, Criterion("cost_gate_uses_live_fee_tier", check_cost_gate_uses_live_fee_tier))
register(3, Criterion("risk_rejects_sub_ordermin", check_risk_rejects_sub_ordermin))
register(3, Criterion("universe_varies_with_balance", check_universe_varies_with_balance))
register(
    3,
    Criterion(
        "safety_freezes_on_drawdown_without_opportunity_chain",
        check_safety_freezes_on_drawdown_without_opportunity_chain,
    ),
)
register(
    3, Criterion("safety_escalates_on_sustained_outage", check_safety_escalates_on_sustained_outage)
)
register(3, Criterion("safety_inputs_all_from_the_seed", check_safety_inputs_all_from_the_seed))
register(3, Criterion("phase_3_gates_have_both_tests", check_phase_3_gates_have_both_tests))

# Phase 4 - memory and replay. Spec 48, registered first in the phase and ahead of
# every subject it judges, for the reason spec 00 was first in Phase 0, spec 16 first
# in Phase 1 and spec 45 first in Phase 3. Until these existed `--phase 4` registered
# `docs_vocabulary` and `toolchain_green` alone and printed "Phase 4 is green: every
# criterion PASS, zero PENDING" over a phase in which engine 19, the labeller, the
# splitter and both committed fixtures did not exist. A phase with nothing in it must
# not be able to report as finished, and PENDING is how it says so.
#
# Phase 4 is also the phase where a mistake looks like success: a purging bug or a
# short embargo produces a model that appears excellent and is worthless, and a missed
# block record makes the circuit breaker inert. Neither crashes and neither turns a
# test red, so each of these is written to be sensitive to a named wrong
# implementation rather than to the shape of the evidence.
register(4, Criterion("memory_records_every_blocker", check_memory_records_every_blocker))
register(
    4,
    Criterion("memory_writes_safety_inputs_live", check_memory_writes_safety_inputs_live),
)
register(4, Criterion("rejections_survive_restart", check_rejections_survive_restart))
register(
    4,
    Criterion(
        "labelled_sample_replayed_from_archive",
        check_labelled_sample_replayed_from_archive,
    ),
)
register(
    4,
    Criterion(
        "labeller_matches_hand_verified_labels",
        check_labeller_matches_hand_verified_labels,
    ),
)
register(
    4,
    Criterion(
        "walkforward_folds_purged_and_embargoed",
        check_walkforward_folds_purged_and_embargoed,
    ),
)
register(4, Criterion("console_history_reads_real_rows", check_console_history_reads_real_rows))
# `--live` only, and never required for green. It reports PENDING rather than FAIL
# when no archive is present: the operator has not downloaded one, and an opt-in
# criterion that FAILs on its absence makes `--live` useless for every other check.
register(4, Criterion("replay_full_archive", check_replay_full_archive, live=True))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def name_column_width(criteria: Sequence[Criterion]) -> int:
    """The width the criterion-name column is padded to.

    Taken from the criterion *names* rather than from finished results, because
    `main` prints each line as its criterion returns and the column has to be
    settled before the first one runs. The names are known from the registry, so
    this is the same number `format_report` used to compute at the end.
    """
    return max((len(c.name) for c in criteria), default=0)


def report_header(phase: int, root: Path) -> list[str]:
    return ["ACSOE verify - phase " + str(phase), "repo: " + str(root), ""]


def criterion_line(criterion: Criterion, outcome: Outcome, width: int) -> str:
    return (
        outcome.result.value.ljust(8) + criterion.name.ljust(width) + "  " + outcome.message
    )


def report_summary(
    phase: int,
    results: Sequence[tuple[Criterion, Outcome]],
    skipped: Sequence[Criterion],
) -> list[str]:
    counts = dict.fromkeys(Result, 0)
    for _, outcome in results:
        counts[outcome.result] += 1
    lines = [""]
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
    return lines


def format_report(
    phase: int,
    root: Path,
    results: Sequence[tuple[Criterion, Outcome]],
    skipped: Sequence[Criterion],
) -> str:
    """The whole report as one string.

    `main` no longer builds the report this way - it streams the same pieces as each
    criterion returns, so a run killed mid-flight still leaves the verdicts it had
    reached on disk. This composes those pieces in the same order and produces the
    identical text, and it is what the unit tests hold the format to.
    """
    lines = report_header(phase, root)
    if results:
        width = name_column_width([criterion for criterion, _ in results])
        lines.extend(
            criterion_line(criterion, outcome, width) for criterion, outcome in results
        )
    else:
        lines.append("(no criteria registered for this phase)")
    lines.extend(report_summary(phase, results, skipped))
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

    # Streamed, not batched, and flushed line by line. A criterion that has reached a
    # verdict has reached it, and this machine's known intermittent native fault kills
    # the process often enough that "the run that crashed" must not also be "the run
    # that printed nothing". The text is byte-identical to the batched report.
    for line in report_header(args.phase, context.root):
        print(line, flush=True)
    width = name_column_width(to_run)
    results: list[tuple[Criterion, Outcome]] = []
    for criterion in to_run:
        outcome = run_criterion(criterion, context)
        results.append((criterion, outcome))
        print(criterion_line(criterion, outcome, width), flush=True)
    if not results:
        print("(no criteria registered for this phase)", flush=True)

    if sweeping:
        sweep_stale_workspaces(report=False)

    for line in report_summary(args.phase, results, skipped):
        print(line, flush=True)
    return 1 if any(o.result is Result.FAIL for _, o in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
