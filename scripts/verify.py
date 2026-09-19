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
import hashlib
import importlib
import importlib.util
import inspect
import json
import math
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
from decimal import ROUND_DOWN, Decimal, InvalidOperation
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

#: The bound on one toolchain subprocess. It is a guard against a tool that has **hung**,
#: not a budget for one that is merely slow, and the difference is the whole of the ruling
#: below: a hung tool reports nothing ever, while a working one reports late.
SUBPROCESS_TIMEOUT_S = 900

#: `pytest` gets its own, larger bound. **Lead ruling of 2026-09-15, flagged to the
#: operator as overturnable.**
#:
#: 900 s was chosen in Phase 0, when the suite was a handful of tests and a minute long.
#: It is now 2,506 tests, and the measurements are in this repository rather than in
#: anyone's memory - `logs/verify/toolchain_green/` keeps the evidence file of every
#: failure:
#:
#: * 2026-09-15 07:06Z, before the operator's three thresholds landed: **820.9 s**, a
#:   margin of 79 s under the limit;
#: * 2026-09-15 04:10Z, the same tree: **timed out**, having reached 74%;
#: * 2026-09-15 15:19Z, with the thresholds landed: **1502 s**.
#:
#: So the bound was already marginal and had already fired once on a tree that was fine,
#: and `prediction.di_percentile: 0.99` took it decisively over: the DI is fitted and
#: scored on every trained fold now that a percentile exists, measured at **3.1 s per
#: fold** (1.1 s in `di.fit`'s leave-one-out, 1.5 s in the per-row `di.score` loop at
#: 1.13 ms a row). That cost is Phase 7 prerequisite 5, deferred on the understanding that
#: it was only paid by the full walk-forward; it is paid by this gate too, which is
#: recorded in `context/progress-tracker.md` as the second reason to do that work.
#:
#: **Nothing here makes a criterion easier to satisfy.** pytest must still exit 0, with
#: every one of its tests passing, and mypy and ruff keep the 900 s bound because they run
#: in seconds and a hang in either is a real fault worth catching quickly. What changes is
#: only how long the gate waits before calling pytest hung - and a gate that reports FAIL
#: on a fully green tree is a false negative in the one check that decides whether a phase
#: is green, which is the failure mode this project has spent four phases cataloguing.
#:
#: Set at roughly 1.8x the measured 1502 s. The margin is deliberate: the 04:10Z timeout
#: above was the *same* suite as the 820.9 s one, so machine load alone moves this number
#: by more than 10%, and a bound sitting just above the measurement would keep firing on a
#: tree nobody had broken.
PYTEST_TIMEOUT_S = 2700

#: Per-tool overrides, by the name in `TOOLCHAIN`. Anything absent uses
#: `SUBPROCESS_TIMEOUT_S`. A mapping rather than a fourth element of each `TOOLCHAIN`
#: tuple, so the tuple's shape - which `TOOLCHAIN_ROOTS` and
#: `tests/verify/test_phase0_criteria.py` both unpack - does not change.
TOOL_TIMEOUT_S: dict[str, int] = {"pytest": PYTEST_TIMEOUT_S}


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

# The eleven tables of the storage model in context/architecture-context.md, which is
# the authority. B's runner exports the same set as EXPECTED_TABLES; the criterion
# cross-checks the two so a drift between the declaration and the SQL is caught.
# `approvals` joined with migration 0006 (spec 132, Phase 7): why an entry was approved,
# held between the placing tick and the trade row. `scout_tallies` joined with migration 0007
# (spec 146): engine 7's universe step on every tick it ran, candidate or not.
DOCUMENTED_TABLES = frozenset(
    {
        "approvals",
        "scout_tallies",
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

#: Where a toolchain command's **complete** captured output is written.
#:
#: Every failure deposits one, and so does a *green* pytest run - see
#: `_pytest_count_note`, and the operator ruling of 2026-09-17 behind it.
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
    """Write one command's whole captured output. Returns what to say about it.

    Called for every failure, and for a pytest run that *passed* - the operator's gate no
    longer runs its own `pytest tests/ -q` beside this one, so the run this wrapper drove
    is now the only place the suite's output exists.

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
        "# unedited. The criterion's own message quotes the last three lines of a\n"
        "# failure, or pytest's summary line when the run was green.\n"
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


def _pytest_count_note(
    root: Path, *, args: Sequence[str], output: str, attempt: int
) -> str:
    """What a **green** pytest run is on record as having actually run.

    The lead's gate used to run `pytest tests/ -q` itself, beside `verify.py`, and read the
    count off it. The operator retired that second run on 2026-09-17 because it is the
    identical command - which leaves this wrapper as the only thing that runs the suite at
    a boundary, and a PASS message reading only "all green" would have deleted the number
    rather than moved it. `0 passed` and `3271 passed` are both exit 0, and the difference
    between them is the difference between a gate and a formality: a collection error that
    pytest reports as exit 5 is loud, but a `pytest.ini` typo, a renamed directory or a
    `-p no:cacheprovider` accident that simply collects less is silent at the returncode.

    The evidence file goes down for the same reason it does on a failure - the output is
    gone otherwise - and a PASS that cannot state its count says so instead of implying one.
    """
    evidence = write_toolchain_evidence(
        root, name="pytest", args=args, returncode=0, output=output, attempt=attempt
    )
    summary = pytest_summary_line(output)
    if summary is None:
        return "pytest exited 0 but printed no summary line - " + evidence
    return "pytest `" + summary + "` - " + evidence


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
    interpreter: str, args: list[str], root: Path, env: dict[str, str], timeout_s: int
) -> tuple[int | None, str]:
    """One toolchain command. `None` as the returncode means it timed out.

    `timeout_s` is the caller's, from `TOOL_TIMEOUT_S`, because pytest and ruff are not
    the same kind of wait - see the constants at the top of this file.

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
            timeout=timeout_s,
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

    A PASS carries pytest's own summary line and the path to its complete output, on
    whichever attempt finished - see `_pytest_count_note`. This is the only place the
    suite's count is produced now that the gate has stopped running `pytest` a second
    time beside this one.
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
    counted: list[str] = []
    crashed = False
    for name, args, tool_max_exit in TOOLCHAIN:
        timeout_s = TOOL_TIMEOUT_S.get(name, SUBPROCESS_TIMEOUT_S)
        returncode, output = _run_tool(interpreter, args, ctx.root, env, timeout_s)
        if returncode is None:
            evidence = write_toolchain_evidence(
                ctx.root, name=name, args=args, returncode=None, output=output, attempt=1
            )
            failures.append(
                name + " timed out after " + str(timeout_s) + "s - " + evidence
            )
            continue
        if returncode == 0:
            if name == "pytest":
                counted.append(_pytest_count_note(ctx.root, args=args, output=output, attempt=1))
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
        returncode, output = _run_tool(interpreter, args, ctx.root, env, timeout_s)
        if returncode is None:
            crashed = True
            failures.append(
                first
                + "; the retry then timed out after "
                + str(timeout_s)
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
            # The count comes off the attempt that actually finished. Reading it off the
            # crashed first attempt instead would report however far the run had got
            # before the process died, as a total.
            if name == "pytest":
                counted.append(_pytest_count_note(ctx.root, args=args, output=output, attempt=2))
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
    message = "pytest, mypy --strict and ruff all green (" + label + ")"
    if counted:
        message += " - " + "; ".join(counted)
    if survived:
        message += " - RETRIED AFTER CRASH: " + "; ".join(survived)
    return passed(message)


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


# --- candles_match_independent_reduction_of_recorded_trades ------ #

OHLC_FIXTURE = Path("tests") / "fixtures" / "kraken" / "ohlc.json"

#: Three pairs, per the phase row in `ai-workflow-rules.md`.
OHLC_MIN_PAIRS = 3

#: Volume tolerance, as the phase row states it. Prices are compared within the pair's
#: `tick_size` as the **fake** exchange's `AssetPairs` serves it, which is invented Phase 0
#: test data (`tests/fixtures/kraken/asset_pairs.json`, whose `provenance` says so), not
#: Kraken's. There is deliberately no price tolerance named here, but the one read is a
#: chosen number all the same. Operator ruling S2, 2026-09-18.
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


#: Spec 127's recording of Kraken's public `AssetPairs`, and its recorded name join from REST
#: names (`XXBTZUSD`) to v2 symbols (`BTC/USD`). Newest date wins when there are several.
RECORDED_ASSET_PAIRS_GLOB: Final = "asset_pairs_recorded_*.json"
RECORDED_PAIR_NAMES_GLOB: Final = "pair_names_recorded_*.json"


def _pair_tick_sizes(root: Path) -> tuple[dict[str, Decimal] | None, str, Outcome | None]:
    """`(tick_size per v2 pair, where it came from, problem)`, from the **recorded** AssetPairs.

    Phase 7 prerequisite 9 and spec 141 step 5. Until 2026-09-19 this read the fake
    exchange's `asset_pairs.json`, invented Phase 0 test data (operator ruling S2). It now
    reads spec 127's recording of Kraken's public `AssetPairs`, the response body exactly as
    received, keyed by v2 symbol through spec 127's recorded name join. **No fallback to the
    invented file**: without a recording this is PENDING, never the old number. The rules
    are 2026's, which is what the recording is. A `tick_size` that is absent, unparseable or
    not positive is not a tolerance, and the pair is left out rather than given one; spec
    127's own test holds the recording to the live client's parser.
    """
    kraken = root / "tests" / "fixtures" / "kraken"
    recordings = sorted(kraken.glob(RECORDED_ASSET_PAIRS_GLOB))
    names = sorted(kraken.glob(RECORDED_PAIR_NAMES_GLOB))
    if not recordings or not names:
        return None, "", pending(
            "no recorded AssetPairs and name join under tests/fixtures/kraken/ yet (spec 127, "
            "prerequisite 9); the invented asset_pairs.json is no longer read"
        )
    recording = recordings[-1]
    try:
        captured = json.loads(recording.read_bytes().decode("utf-8"))
        envelope = json.loads(captured["payload"])
        if envelope.get("error"):
            return None, "", failed(f"{recording.name} recorded an error: {envelope['error']}")
        result = envelope["result"]
        joined = json.loads(names[-1].read_bytes().decode("utf-8"))["pairs"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return None, "", failed(f"{recording.name} could not be read as a recording: {exc}")
    tick_sizes: dict[str, Decimal] = {}
    for entry in joined.values():
        rule = result.get(str(entry.get("rest_key"))) if isinstance(entry, Mapping) else None
        tick = _decimal_or_none(rule.get("tick_size")) if isinstance(rule, Mapping) else None
        if tick is not None and tick > 0 and entry.get("v2_symbol"):
            tick_sizes[str(entry["v2_symbol"])] = tick
    captured_at = str((captured.get("provenance") or {}).get("captured_at", "an unstated time"))
    source = (
        f"Kraken's public AssetPairs as recorded at {captured_at} "
        f"(tests/fixtures/kraken/{recording.name}, 2026 rules)"
    )
    return tick_sizes, source, None


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


def check_candles_match_independent_reduction_of_recorded_trades(ctx: VerifyContext) -> Outcome:
    """Built 15-minute candles against an independent reduction of real Kraken trades.

    **What it checks.** `tests/fixtures/kraken/ohlc.json` holds real Kraken v2 `trade`
    frames taken verbatim from the recording, and expected bars computed from those same
    trades by the deliberately naive pure-Python reduction in `scripts/ohlc_fixture.py`,
    which shares no code with the `polars` builder under test. **The expected bars are not
    Kraken's published OHLC**: the archive has no OHLC channel (A's spec 28 decision,
    `docs/build-log/phase-2.md`). Every OHLC field must be within one `tick_size` and
    volume within 0.1%. Confirming the bars against Kraken's published OHLC is a
    `--live` task.

    **The tolerance is Kraken's recorded `tick_size`** since spec 141 step 5 (Phase 7
    prerequisite 9): spec 127's recording of the public `AssetPairs`, parsed by the live
    client's mapper. Until 2026-09-19 it was read out of the fake exchange's invented
    `asset_pairs.json`. It is never engaged on the committed fixture: open, high, low and
    close are each *selected* from the trades, not computed, so two correct reductions agree
    to the digit, and on 2026-09-18 all 9 bars did. The PASS reports the largest difference
    it saw so that stays visible rather than implied.

    Until 2026-09-18 this docstring said the tolerance was "fetched, never hardcoded" and
    the messages compared against "Kraken's own OHLC". Both were false from the day it was
    written, and the tests asserted that the word `tick_size` appeared rather than that
    the message was true. Operator ruling S2 and the tracker's FINDING of that date.

    **Named `candles_match_kraken_ohlc` until 2026-09-18** and renamed by the operator the
    same evening, because the name made the same false claim as the prose and is read more
    often: it appears in every gate output. Gate logs before that date carry the old name.
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
        tick_sizes, tolerance_source, early = _pair_tick_sizes(ctx.root)
        if tick_sizes is None:
            return early or pending("no pair rules to read a tolerance from")
        builder, early = _candle_builder()
        if builder is None:
            return early or pending("no candle builder yet - " + CANDLES_CONTRACT)

        checked = 0
        widest = Decimal(0)
        for pair, payload in pairs.items():
            if pair not in tick_sizes:
                return failed(
                    f"{pair} is in ohlc.json and not in {tolerance_source}, so there is no "
                    "recorded tick_size for it and this criterion will not have one invented"
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
                        f"the builder produced no {pair} candle at ts={ts}, which the "
                        "reference reduction of the recorded trades has. A dropped bar is "
                        "a missing decision bar."
                    )
                for name in OHLC_FIELDS:
                    want = _decimal_or_none(_field(expected, name))
                    got = _decimal_or_none(_field(candle, name))
                    if want is None or got is None:
                        return failed(f"{pair} at ts={ts}: `{name}` is missing or not a number")
                    widest = max(widest, abs(got - want))
                    if abs(got - want) > tick:
                        return failed(
                            f"{pair} at ts={ts}: {name} {got} vs the reference reduction's "
                            f"{want}, more than one tick_size ({tick}, from "
                            f"{tolerance_source})"
                        )
                want_vol = _decimal_or_none(_field(expected, "volume"))
                got_vol = _decimal_or_none(_field(candle, "volume"))
                if want_vol is None or got_vol is None:
                    return failed(f"{pair} at ts={ts}: `volume` is missing or not a number")
                allowed = abs(want_vol) * VOLUME_TOLERANCE
                if abs(got_vol - want_vol) > allowed:
                    return failed(
                        f"{pair} at ts={ts}: volume {got_vol} vs the reference reduction's "
                        f"{want_vol}, outside 0.1%"
                    )
                checked += 1

    return passed(
        f"{len(pairs)} pairs, {checked} bar(s): the builder matches an independent reduction "
        "of real recorded Kraken trades (scripts/ohlc_fixture.py - not Kraken's published "
        f"OHLC), largest OHLC difference {widest}, inside the one-tick_size tolerance taken "
        f"from {tolerance_source}; volume within 0.1%. Confirming against Kraken's published "
        "OHLC is a --live task"
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

    **Each of those two ticks is a whole seed row - its cash, its mark, its
    unrealised - and the latest equity row is then compared column by column.** Both
    halves were added on 2026-09-16 and neither is decoration:

    * Engine 19 adds a cash balance to a mark. Replaying the seed's *equity* as a bare
      balance says the account is entirely in cash while its positions sit in the same
      database - a contradiction the old engine 19 resolved by valuing the position at
      nothing, which is a drawdown approaching 100% and an account frozen by a missing
      quote. Since the lead's ruling it writes no row at all instead, and this replay
      was the thing publishing the contradiction.
    * Comparing only the six readings leaves the *composition* unasserted, and
      `equity_snapshots` stores it for the Phase 7 alpha attribution. Measured: a
      replay deriving the cash as `equity - positions_value` returns the seed's total
      for any mark whatsoever, so a mark read out of the wrong column survived. Both
      components now come from the row and are read back, which is Phase 5's closing
      finding applied here - recompute what a number was supposed to be computed from.
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

            # Both reads happen inside the workspace - the databases go with `tmp` -
            # but only the first is *reported* here. See each helper's docstring for
            # why one comes before the six readings and the other after.
            empty = _no_equity_row_written(live_path)
            if empty is not None:
                return empty
            composition = _equity_composition_disagreements(seed_path, live_path)

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

    if composition is not None:
        return composition

    return passed(
        "engine 19 wrote "
        + str(replayed)
        + " rows across five tables and `safety` reached the same six totals from them "
        "as from the Phase 0 seed (drawdown "
        + str(live["drawdown_pct"])
        + f", {live['consecutive_losses']} losing trade(s), "
        + f"{live['errors_in_window']} error block(s), {live['stored_data_blocks']} "
        + f"outage tick(s), {live['open_positions']} position(s), "
        + f"{live['resting_entry_orders']} resting order(s)), on an equity row matching "
        "the seed's on " + ", ".join(EQUITY_COMPOSITION)
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
        equity_ticks = _seed_equity_ticks(seed_path)
    blocks = _block_rows(seed_path)
    if equity_ticks is None:
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
        #
        #    **Each tick replays a whole seed row, not a balance.** Step 2 put the
        #    seed's open positions into this database, so by the time these ticks run
        #    the live account is invested. Engine 19 reads
        #    `store.count_open_positions()`, and a tick publishing a balance and no
        #    mark writes **no equity row at all** - correctly, because `cash + 0` on an
        #    invested account is a drawdown that did not happen, and one missing quote
        #    would otherwise freeze the account through engine 17.
        #
        #    So the cash and the mark are each read from the seed row being replayed,
        #    and engine 19's `equity = cash + positions_value` has to *arrive at* that
        #    row's equity. Deriving the cash as `equity - positions_value` instead
        #    would reproduce the total for any mark whatsoever - a number reproduced
        #    over an account invented to reach it, which is the shape Phase 5's closing
        #    finding names.
        for index, snapshot in enumerate(equity_ticks, start=3):
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
                            str(contracts.BALANCES_FIELD): {
                                currency: format(snapshot.cash, "f")
                            },
                            "fetched_at": int(now.timestamp() * MICROSECONDS),
                        },
                        str(contracts.POSITION_MANAGER_KEY): {
                            str(contracts.POSITIONS_VALUE_FIELD): format(
                                snapshot.positions_value, "f"
                            ),
                            str(contracts.UNREALISED_PNL_FIELD): format(
                                snapshot.unrealised_pnl, "f"
                            ),
                        },
                    },
                ),
            )
            written += 1
    return written, None


#: The `equity_snapshots` columns the replay hands over and reads back. Deliberately
#: not `realised_pnl_cum`, which is a running total over whichever trades each producer
#: has seen and is the one column the two sides are not expected to agree on.
EQUITY_COMPOSITION: Final = ("equity", "peak_equity", "cash", "positions_value", "unrealised_pnl")


@dataclass(frozen=True)
class SeedEquityRow:
    """One whole `equity_snapshots` row of the seed, composition included.

    **A whole row rather than a total, because engine 19 is never handed a total.** It
    is handed a cash balance and a mark and it *adds* them, and since the lead's ruling
    of 2026-09-16 it refuses the pair where the account holds positions and no mark
    arrived. Replaying the seed's equity as a cash balance alone hands it a
    contradiction - an invested account reporting a cash-only equity - and before that
    ruling the answer that came back was the position silently valued at nothing.

    Handing over the row's own `cash` and its own `positions_value` is also what turns
    `equity = cash + positions_value` into something this criterion *checks* rather
    than something it assumes: a replay that derived the cash as `equity -
    positions_value` would return the seed's total for any mark at all, including a
    mark read out of the wrong column. Measured - that arrangement survived the
    mutation, this one kills it.
    """

    ts: int
    equity: Decimal
    peak_equity: Decimal
    cash: Decimal
    positions_value: Decimal
    unrealised_pnl: Decimal


def _equity_rows(db_path: Path) -> list[SeedEquityRow]:
    """Every `equity_snapshots` row, oldest first.

    `ORDER BY ts` and never by a money column: money is stored as an exact decimal
    string, so SQL compares it lexicographically and decides '9.50' > '10000.00'. The
    peak below is found in Python as `Decimal` for the same reason.
    """
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT ts, " + ", ".join(EQUITY_COMPOSITION) + " FROM equity_snapshots "
            "ORDER BY ts ASC, rowid ASC"
        ).fetchall()
    finally:
        conn.close()
    return [
        SeedEquityRow(
            ts=int(row[0]),
            **{
                column: as_decimal(row[index], "equity_snapshots." + column)
                for index, column in enumerate(EQUITY_COMPOSITION, start=1)
            },
        )
        for row in rows
    ]


def _seed_equity_ticks(db_path: Path) -> tuple[SeedEquityRow, SeedEquityRow] | None:
    """(the row that set the peak, the latest row), or None where there are none.

    `safety`'s drawdown is `(peak_equity - equity) / peak_equity` on the **latest** row
    - `architecture-context.md`'s input table says so - so those two rows are the whole
    of what the replay has to reproduce, and they are replayed in that order because
    the peak has to exist in the store before the drawdown can be measured against it.

    The peak row is the one whose `equity` is the series maximum, which is the same row
    that first set `peak_equity` to the value the latest row still carries. It is
    found by walking the rows as `Decimal`, never by `SELECT MAX`.
    """
    rows = _equity_rows(db_path)
    if not rows:
        return None
    peak = max(rows, key=lambda row: row.equity)
    return peak, rows[-1]


def _no_equity_row_written(live_path: Path) -> Outcome | None:
    """FAIL, with a message, where engine 19 wrote no equity row at all.

    Reported **before** the six readings are compared, because a null drawdown is not
    a number `safety` disagrees about - it is no answer, and `as_decimal` raises on
    it. A criterion that raises is still a FAIL, and that is the trap: the raise text
    names the reading, so every induced-failure test asserting the reading is
    *mentioned* keeps passing while the criterion has stopped running.
    """
    if _seed_equity_ticks(live_path) is not None:
        return None
    return failed(
        "engine 19 wrote no equity_snapshots row, so `safety` has no drawdown to read. "
        "The usual cause is a tick publishing a balance and no mark while the account "
        "holds positions, which engine 19 refuses to value on cash alone."
    )


def _equity_composition_disagreements(seed_path: Path, live_path: Path) -> Outcome | None:
    """FAIL where engine 19's latest equity row is not the seed's latest equity row.

    Reported **after** the six readings, because those are the criterion's thesis and
    this is the fidelity underneath them. `safety` reads two of these five columns.
    The other three are stored because the Phase 7 alpha attribution reads the curve
    *including its cash periods* - `0001_initial.sql` says so - and nothing had ever
    compared them, so a writer that dropped or transposed the composition kept every
    `safety` reading intact and lost the attribution silently.

    It is also what makes the replay's own arithmetic falsifiable. Engine 19 is handed
    the seed row's `cash` and its `positions_value` and has to arrive at its `equity`.
    Comparing the total alone would let a wrong mark through, because a replay that
    derived the cash as `equity - positions_value` returns that total for any mark at
    all - measured, and it survived the mutation that read the mark out of the wrong
    column.
    """
    live = _seed_equity_ticks(live_path)
    seed = _seed_equity_ticks(seed_path)
    if live is None or seed is None:
        return None

    disagreements = [
        f"{column}: seed={getattr(seed[1], column)} live={getattr(live[1], column)}"
        for column in EQUITY_COMPOSITION
        if getattr(seed[1], column) != getattr(live[1], column)
    ]
    if disagreements:
        return failed(
            "engine 19's latest equity_snapshots row is not the seed's - "
            + "; ".join(disagreements)
            + ". Equity is `cash + positions_value` and both components are stored, so a "
            "row reaching the right total by the wrong split is still a wrong row: it is "
            "the one Phase 7 attributes alpha from."
        )
    return None


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
    * `embargoed` - decision bar two bars **before** the test window, inside the
      embargo span, with a label window that closed before the test window opened.
      Must be dropped. Nothing about its label window straddles anything, so a purge
      alone cannot remove it and an embargo of zero keeps it.
    * `before_embargo` - one bar older than the embargo span, label closed before the
      span opens. Must survive, or the criterion would pass against a splitter whose
      embargo is wider than the configured span, or that dropped everything near the
      boundary.

    The last two are what make the embargo assertion independent of the purge
    assertion: a test that would pass with the embargo set to zero is not testing the
    embargo.

    Operator ruling 1 of 2026-09-12 moved the embargo to the training side of the
    boundary: a fold trains on the past only, so there are no training rows after the
    test window for an embargo to hold back. Whether anything after the test window
    can train is `walkforward_trains_on_the_past_only`'s question, asked over rolling
    folds rather than one constructed row.
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
        embargo_start = test_start - embargo_bars * _CONSTRUCTED_INTERVAL_S

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
                # Inside the embargo span before the test window; label closed in time.
                "label_id": "embargoed",
                "decision_ts": test_start - 2 * _CONSTRUCTED_INTERVAL_S,
                "label_window_end_ts": test_start - _CONSTRUCTED_INTERVAL_S,
            },
            {
                # One bar older than the embargo span; label closed before it opens.
                "label_id": "before_embargo",
                "decision_ts": embargo_start - _CONSTRUCTED_INTERVAL_S,
                "label_window_end_ts": embargo_start - 1,
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
            + " bars or fewer before the test window, inside the configured embargo. No "
            "part of its label window straddles the boundary, so the purge cannot "
            "remove it - only the embargo can, and an embargo of zero keeps it."
        )
    if "before_embargo" not in train_ids:
        return failed(
            "`before_embargo` was dropped although it sits one bar older than the "
            "embargo span. The embargo is a bounded span of exactly "
            + str(embargo_bars)
            + " bars before the test window, not a truncation of everything near the "
            "boundary."
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
        "identity, and a row inside the "
        + str(embargo_bars)
        + "-bar embargo before the test window was embargoed, while a row a month "
        "earlier and a row one bar older than the embargo span both survived "
        "(purged=1, embargoed=1)"
    )


# --- walkforward_trains_on_the_past_only ------------------------------------ #


def check_walkforward_trains_on_the_past_only(ctx: VerifyContext) -> Outcome:
    """No training row post-dates its test window, on every fold. Operator ruling 1.

    The splitter this replaced trained on a window of equal length on both sides of the
    test window. That is purged cross-validation, legitimate for choosing
    hyperparameters, and it lets a model see data from after the period it is scored
    on - so the backtest reports a number better than the same model would achieve
    live, and nothing says so. The project's goal is a system that trades, so the
    validation must answer "would this have worked if I had been trading it", and only
    a past-only fold answers that.

    Constructed rather than read, like its sibling: a series of labelled rows every six
    hours spanning one training window and eight test windows, split into rolling
    folds. Then, for **every** fold and **every** training row, both the decision bar
    and the label window end must precede the fold's test window. Both, because a
    decision bar that precedes the window with an outcome known inside it is the
    purge's job, and a past-only rule that forgot the purge would still be a leak.

    Two things keep the assertion from being vacuous. The dataset must actually hold
    rows after each fold's test window - the first fold has eight weeks of them - and
    the fold must report how many it saw and refused, in `after_test_count`, agreeing
    with the data. A splitter that never produced a post-window row to refuse would
    pass the loop and prove nothing.
    """
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
        step = 6 * 3600
        # Two days, deliberately longer than the embargo span. With a horizon no longer
        # than the embargo every straddling row is also an embargoed row, and a
        # splitter that lost its purge would still pass here on the embargo's back:
        # the mutation proof for the purge half needs a straddler the embargo cannot
        # reach.
        horizon = 2 * day
        origin = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
        span = (train_days + 8 * test_days) * day
        rows = [
            {
                "decision_ts": origin + i * step,
                "label_window_end_ts": origin + i * step + horizon,
            }
            for i in range(span // step)
        ]
        try:
            folds = splitter(rows, config=engine_config, interval_s=_CONSTRUCTED_INTERVAL_S)
        except TypeError as exc:
            return pending(
                "acsoe.research.walkforward.purged_walk_forward does not accept the "
                "rolling call this criterion makes: " + str(exc)[:200]
            )

    if not folds:
        return failed(
            "the splitter returned no folds for a series spanning one training window "
            "and eight test windows"
        )

    checked = 0
    refused = 0
    for fold in folds:
        test_start = int(fold.test_start_ts)
        test_end = int(fold.test_end_ts)
        for i in fold.train_index:
            row = rows[int(i)]
            checked += 1
            if int(row["decision_ts"]) >= test_start:
                return failed(
                    "fold "
                    + str(fold.fold_index)
                    + " trained on a row whose decision bar is at or after its test "
                    "window opens. A fold trains on the past only (operator ruling 1, "
                    "2026-09-12): a model that has seen data from after the period it "
                    "is scored on reports a number the live system will never reach, "
                    "and nothing downstream says so."
                )
            if int(row["label_window_end_ts"]) >= test_start:
                return failed(
                    "fold "
                    + str(fold.fold_index)
                    + " trained on a row whose decision bar precedes its test window "
                    "but whose outcome became known inside it. That is the purge's "
                    "job, and a past-only rule does not replace it."
                )
        after = getattr(fold, "after_test_count", None)
        if after is None:
            return failed(
                "the fold does not expose `after_test_count`. The rows a fold refused "
                "for post-dating its test window are counted in their own column so "
                "the past-only rule is visible as a number rather than inferred from "
                "an absence."
            )
        in_data = sum(1 for row in rows if int(row["decision_ts"]) >= test_end)
        if int(after) != in_data:
            return failed(
                "fold "
                + str(fold.fold_index)
                + " reports after_test_count="
                + str(after)
                + " but the series holds "
                + str(in_data)
                + " rows after its test window. A count that disagrees with the data "
                "is one nothing can be read from."
            )
        refused += int(after)

    if checked == 0:
        return failed("no fold had any training rows; the assertion above ran over nothing")
    if refused == 0:
        return failed(
            "no fold saw a row after its test window, so nothing tested whether such "
            "a row can train. The constructed series is meant to hold eight weeks of "
            "them after the first fold."
        )
    return passed(
        str(len(folds))
        + " rolling folds, "
        + str(checked)
        + " training rows: every decision bar and every label window end precedes its "
        "fold's test window, and "
        + str(refused)
        + " rows after test windows were counted and none trained"
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
# Phase 5 - models (spec 60)
# --------------------------------------------------------------------------- #
#
# Every phase so far failed loudly. Phase 5 fails quietly: a subtly wrong walk-forward,
# a leaked feature, a metric that flatters, a DI fitted on the wrong rows. Each produces
# a model that looks excellent and is worthless, and nothing goes red. So every
# criterion below is written to be sensitive to a *named* wrong implementation rather
# than to the shape of the evidence, and each is observed PENDING, PASS and FAIL in
# `tests/verify/test_phase5_criteria.py`.
#
# Where a criterion needs a trained model it trains one **inside the criterion**, from
# the committed fixtures into a temporary models root. Nothing here reads `models/`,
# `data/` or `logs/`: all three are gitignored, and a criterion that depends on one
# passes only on the machine that produced it.

#: Engine number and owning spec, for the PENDING message. Same shape as
#: `PHASE3_ENGINES` and `PHASE4_ENGINES`, and for the same reason: a PENDING that does
#: not name the spec sends the reader to the task list to find out who is late.
PHASE5_ENGINES: Final[Mapping[str, tuple[int, str]]] = {
    "feature": (5, "spec 64, agent C"),
    "macro_context": (6, "spec 65, agent C"),
    "prediction": (8, "spec 71, agent C"),
    "regime": (12, "spec 66, agent C"),
    "anomaly": (13, "spec 72, agent C"),
    "skeptic": (15, "spec 73, agent C"),
    "tournament": (20, "spec 74, agent C"),
}

#: The leaf package spec 63 creates and the trainer spec 67 creates.
PHASE5_MODULES: Final[Mapping[str, str]] = {
    "acsoe.modelling.features": "spec 63, agent C",
    "acsoe.modelling.artefacts": "spec 63, agent C",
    "acsoe.modelling.weights": "spec 63, agent C",
    "acsoe.modelling.di": "spec 63, agent C",
    "acsoe.research.training": "spec 67, agent C",
}

#: Phase 5's two gates. `phase_3_gates_have_both_tests` asks the same question of
#: engines 7, 10, 11 and 17; criterion 8 asks it of the two this phase adds.
PHASE5_GATE_TEST_FILES: Final[Mapping[str, str]] = {
    "anomaly": "tests/engines/test_anomaly.py",
    "skeptic": "tests/engines/test_skeptic.py",
}

#: Committed evidence, both deposited by C under `tests/fixtures/`.
CANDLES_FIXTURE: Final = Path("tests") / "fixtures" / "candles_sample.parquet"
LABELS_FIXTURE: Final = Path("tests") / "fixtures" / "labelled_sample.parquet"
WALKFORWARD_DIGEST_FIXTURE: Final = Path("tests") / "fixtures" / "walkforward_digest.json"

#: Column names no feature may be computed from. The archive is OHLCVT: it carries no
#: bid, ask, depth or spread, so a feature reading one is computable live and not in
#: replay, and every metric a walk-forward reported would describe a model the live loop
#: cannot reproduce.
BOOK_COLUMNS: Final[tuple[str, ...]] = ("spread", "bid", "ask", "depth")

#: Config keys Phase 5 adds. Each PENDING names the key and the spec that lands it,
#: because a criterion reporting "config is incomplete" sends the reader to diff a file.
KEY_MIN_LOOKBACK_FILL: Final = "features.min_lookback_fill"
KEY_MAX_LOOKBACK_BARS: Final = "features.max_lookback_bars"
KEY_DI_PERCENTILE: Final = "prediction.di_percentile"
KEY_ANOMALY_PERCENTILE: Final = "anomaly.threshold_percentile"
KEY_SKEPTIC_VETO: Final = "skeptic.veto_threshold"
KEY_RANK_FEATURE: Final = "scout.rank_feature"

#: The three values the operator has withheld until the walk-forward reports. Absent is
#: not a defect and must never be a FAIL: spec 59 decision 7 says the engines fail
#: closed and the criteria report PENDING naming the key. A default here would be this
#: repository inventing a threshold that decides whether a model may refuse a trade.
OPERATOR_WITHHELD_KEYS: Final[tuple[str, ...]] = (
    KEY_DI_PERCENTILE,
    KEY_ANOMALY_PERCENTILE,
    KEY_SKEPTIC_VETO,
)

#: What the walk-forward digest carries per fold. Fixed here because spec 60 and spec 67
#: are two halves of one seam and both are C's: a criterion asserting a field the
#: trainer never writes can only ever be red, and a trainer writing a field nothing
#: reads is a number nobody checks. `accuracy` is deliberately absent - spec 59
#: decision 4, and `docs_vocabulary` carries the retired-term row for it.
#: The three barriers, in the order every artefact records them and engine 8 reads them.
#: Positional, so a permuted order swaps `target` for `stop` with nothing raising.
PHASE5_CLASS_ORDER: Final[tuple[str, ...]] = ("target", "stop", "timeout")

#: Retired by operator ruling of 2026-09-12 and computed nowhere. Present in a digest or a
#: manifest it is a FAIL rather than a warning: the base rate is 23.89%, so a model that
#: always predicts `stop` scores 51%, and the number itself is what misleads.
FORBIDDEN_METRIC: Final = "accuracy"

FOLD_DIGEST_FIELDS: Final[tuple[str, ...]] = (
    "fold_index",
    "train_end_ts",
    "test_start_ts",
    "test_end_ts",
    "rows",
    "effective_sample_size",
    "brier",
    "base_rate_brier",
    "log_loss",
    "buy_count",
    "buy_target_rate",
)


def _phase5_module(dotted: str) -> tuple[ModuleType | None, Outcome | None]:
    """Import a Phase 5 module, or say which spec still owes it."""
    module, problem = try_import(dotted)
    if module is not None:
        return module, None
    if problem is not None and problem.result is Result.FAIL:
        return None, problem
    return None, pending(f"{dotted} does not exist yet ({PHASE5_MODULES[dotted]})")


def _phase5_symbol(module: ModuleType, attr: str, dotted: str) -> tuple[Any, Outcome | None]:
    """An agreed symbol out of a Phase 5 module, or the PENDING naming its spec."""
    value, missing = module_attr(module, attr)
    if value is None:
        return None, pending(f"{missing} ({PHASE5_MODULES[dotted]})")
    return value, None


def _phase5_engine_class(engine: str) -> tuple[Any, Outcome | None]:
    """The engine class for `engine`, or a PENDING naming its number and spec."""
    number, spec = PHASE5_ENGINES[engine]
    module, problem = try_import(f"acsoe.engines.{engine}.engine")
    if module is None:
        if problem is not None and problem.result is Result.FAIL:
            return None, problem
        return None, pending(f"engine {number} `{engine}` does not exist yet ({spec})")
    for attr in dir(module):
        candidate = getattr(module, attr)
        if (
            isinstance(candidate, type)
            and getattr(candidate, "name", None) == engine
            and getattr(candidate, "number", None) == number
        ):
            return candidate, None
    return None, pending(
        f"acsoe.engines.{engine}.engine exists but declares no class with "
        f"`name = {engine!r}` and `number = {number}` ({spec})"
    )


def _withheld_key(config: Any, key: str) -> Outcome | None:
    """PENDING when the operator has not supplied `key`, and never a FAIL.

    Spec 59 decision 7. `prediction.di_percentile`, `anomaly.threshold_percentile` and
    `skeptic.veto_threshold` are the operator's to choose once the walk-forward has
    reported, and until then they are absent on purpose. An absent threshold is an
    unmade decision, not a broken one.

    It is a helper rather than three copies because the wrong move is available in three
    places, and it is the same wrong move each time: defaulting one of them would be an
    agent inventing a number that decides whether a model is allowed to refuse a trade.

    **Absent and present-but-`null` both count as withheld, and only the first can
    actually happen.** The ruling is that these keys are *absent* from
    `config/default.yaml`: the file's own header says a `null` is OPERATOR REQUIRED and
    stops every process at load, so a null here would be a different and much louder
    state. This tested `value is None` alone and therefore never fired, because
    `config_get` answers an absent key with the `_CONFIG_MISSING` sentinel — so
    `di_fitted_on_predictor_training_set` walked past its own PENDING branch and FAILed
    the trainer for not writing a DI it was right not to write. Two facts arriving through
    one channel, answered as one; both are accepted here and the message names the key
    either way.
    """
    value = config_get(config, key) if isinstance(config, Mapping) else _config_attr(config, key)
    if value is None or value is _CONFIG_MISSING:
        return pending(
            f"`{key}` is absent from config/default.yaml. It is the operator's to supply "
            "once the walk-forward has reported (spec 59 decision 7), and nothing in "
            "this repository may default it: the engine fails closed meanwhile, and this "
            "criterion waits rather than inventing a threshold."
        )
    return None


def _config_attr(config: Any, key: str) -> Any:
    """`config.get(key)` where absence is a `None` and not an exception.

    `Config.get` raises on an *unknown* key and returns `None` for a leaf the operator
    has not decided - two different facts it reports differently on purpose. A criterion
    waiting on a withheld value has to treat both as "not supplied yet", because until
    spec 61 lands the section itself does not exist either, and the difference between
    "no `prediction` section" and "no `di_percentile` inside it" is a matter of which
    hour it is rather than anything the operator did.
    """
    getter = getattr(config, "get", None)
    if getter is None:
        return None
    try:
        return getter(key)
    except Exception:
        # An unknown key is an absent key to a criterion that is waiting for one. The
        # broad catch is deliberate and narrow in effect: the only caller is
        # `_withheld_key`, which turns either fact into the same PENDING.
        return None


def _feature_fixture_frame(ctx: VerifyContext) -> tuple[Any, Outcome | None]:
    """`candles_sample.parquet` as a polars frame, or why not.

    Read rather than constructed because its **hole is real**. The slice spans 1,209
    fifteen-minute slots and holds 1,208 bars: the archive records no trades in one of
    them. A lookback that is a window of time and a lookback that is a count of rows
    return the same answer on every contiguous series ever written and differ only
    across a hole, so a constructed contiguous fixture could not tell the correct
    implementation from the defect.
    """
    polars, problem = _polars()
    if polars is None:
        return None, problem
    path = ctx.root / CANDLES_FIXTURE
    if not path.is_file():
        return None, pending(
            CANDLES_FIXTURE.as_posix() + " does not exist yet. It is the OHLCVT slice "
            "the labelled sample was produced from, deposited by C under spec 60: the "
            "labelled sample is the labeller's *output* and carries no open, high, low, "
            "volume or trades, so there is nothing else committed for the feature "
            "module to consume."
        )
    return polars.read_parquet(path), None


def _book_column_hits(source: str) -> list[str]:
    """Every mention of a book column in `source`, off the parsed syntax tree.

    Read from the AST rather than with a substring scan, for one reason that matters: a
    substring scan cannot tell `spread` inside a docstring explaining *why this module
    never reads a spread* from `row["spread"]`. The first is the documentation this rule
    wants and the second is the defect, and a check that cannot separate them makes the
    honest comment unwriteable.

    Names, attributes and string constants are all collected, because all three are how
    a column gets reached: `frame.spread`, `row["spread"]` and `pl.col("spread")`.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"could not be parsed: {exc}"]
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in BOOK_COLUMNS:
            hits.append(f"line {node.lineno}: name `{node.id}`")
        elif isinstance(node, ast.Attribute) and node.attr in BOOK_COLUMNS:
            hits.append(f"line {node.lineno}: attribute `.{node.attr}`")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in BOOK_COLUMNS
        ):
            hits.append(f"line {node.lineno}: string {node.value!r}")
    return hits


#: The decision-bar grid and the live publication bound, both needed to shape the two
#: feature paths identically. `KEY_DECISION_BAR_S` is Phase 4's and is reused rather than
#: respelled: one name for one key is what stops a criterion measuring a different grid
#: from the one the system trades on, which cost a criterion its meaning in Phase 4.
KEY_PUBLISHED_BARS: Final = "market_sensor.published_bars"

#: A fixed instant. Every Phase 5 criterion injects its clock; none reads the wall clock,
#: so two runs a week apart reach the same verdict.
PHASE5_NOW: Final = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)

#: How far the live and offline feature paths may differ, relative, once the frame length
#: is allowed to differ.
#:
#: **They cannot be bit-identical and the reason is not a defect.** The live loop is handed
#: `market_sensor.published_bars` candles because that is what engine 3 publishes; the
#: trainer is handed the whole archive. polars accumulates its rolling aggregates along
#: the column, and floating-point addition is not associative, so the same window lands on
#: slightly different bits depending on how many rows preceded it. Measured on the
#: committed slice at three window lengths: worst case **7.4e-15** relative, on
#: `volume_z_4`; with the frame length held still the two paths agree on every bit of
#: every feature.
#:
#: 1e-9 is six orders of magnitude above that noise and many orders below any genuine
#: difference in arithmetic — a different indicator formula differs by percent, not by
#: parts per billion. So this tolerance cannot hide a drifting second implementation,
#: which is the objection an exact comparison exists to answer.
FEATURE_REASSOCIATION_TOLERANCE: Final = 1e-9


def _phase5_engine_absent(engine: str, problem: Outcome | None = None) -> Outcome:
    if problem is not None and problem.result is Result.FAIL:
        return problem
    number, spec = PHASE5_ENGINES[engine]
    return pending(f"engine {number} `{engine}` does not exist yet ({spec})")


def _feature_surface(
    module: ModuleType,
) -> tuple[tuple[Any, tuple[str, ...], str, int] | None, Outcome | None]:
    """`(compute, FEATURE_NAMES, FEATURE_VERSION, MAX_LOOKBACK_BARS)`, or what is missing.

    All four, not just `compute`. A module with the arithmetic and no ordered feature
    list would satisfy a criterion that asked only for the function, and an artefact
    without its exact feature order is what `code-standards.md` calls unusable.
    """
    dotted = "acsoe.modelling.features"
    compute, problem = _phase5_symbol(module, "compute", dotted)
    if compute is None:
        return None, problem
    names, problem = _phase5_symbol(module, "FEATURE_NAMES", dotted)
    if names is None:
        return None, problem
    version, problem = _phase5_symbol(module, "FEATURE_VERSION", dotted)
    if version is None:
        return None, problem
    lookback, problem = _phase5_symbol(module, "MAX_LOOKBACK_BARS", dotted)
    if lookback is None:
        return None, problem
    return (compute, tuple(str(name) for name in names), str(version), int(lookback)), None


def _feature_values(row: Mapping[str, Any], names: Sequence[str]) -> dict[str, float | None]:
    """One feature row with NaN normalised to `None`, whichever side produced it.

    Engine 5 publishes `null` because `state` must be JSON-serialisable; the offline
    frame carries the NaN itself. Normalising here is what lets the two be compared at
    all, and it is done in the criterion rather than asked of either producer.
    """
    out: dict[str, float | None] = {}
    for name in names:
        value = row.get(name)
        if value is None:
            out[name] = None
            continue
        number = float(value)
        out[name] = None if number != number else number
    return out


def _sensor_payload_through_the_real_contract(
    frame: Any, *, pair: str, bar_ts: int, published_bars: int, interval_s: int
) -> tuple[dict[str, Any] | None, Outcome | None]:
    """`state["market_sensor"]` for these candles, built through engine 3's own model.

    **Fabricate the subject, never the contract.** The candles are this criterion's to
    choose; the *shape* they arrive in is engine 3's, so the payload is constructed by
    `MarketSensorState` itself rather than as a dict written here. A hand-written payload
    is how `check_data_guard_blocks_bad_data` came to have a body that never executed
    while both halves of its proof passed, and it is how engine 5's own first test came to
    assert against a non-bar tick that carried no candles when the real engine 3 publishes
    candles on every tick and only nulls the bar timestamp.

    `published_bars` is applied because engine 3 applies it. That is what makes the live
    path a genuinely different input from the offline one, which sees the whole archive —
    and a lookback longer than it is a window the live loop can never fill.
    """
    module, problem = try_import("acsoe.engines.market_sensor.contracts")
    if module is None:
        return None, problem or pending("engine 3 `market_sensor` does not exist yet")
    state_cls, missing = module_attr(module, "MarketSensorState")
    if state_cls is None:
        return None, pending(missing)

    tail = frame.tail(published_bars)
    candles = tuple(
        {
            "pair": pair,
            "ts": int(row["ts"]),
            "open": str(row["open"]),
            "high": str(row["high"]),
            "low": str(row["low"]),
            "close": str(row["close"]),
            "volume": str(row["volume"]),
            "trades": int(row["trades"]),
        }
        for row in tail.iter_rows(named=True)
    )
    payload = state_cls(
        bar_closed=True,
        closed_bar_ts=bar_ts,
        interval_s=interval_s,
        candles=candles,
        missing_bars=(),
        quotes={},
        stream_available=True,
        trades_seen=len(candles),
    )
    return payload.to_state(), None


# --- features_reproduce_in_replay ------------------------------------------ #


def check_features_reproduce_in_replay(ctx: VerifyContext) -> Outcome:
    """One arithmetic, two callers: engine 5's live path and the offline builder agree.

    This is the criterion `modelling/` exists for. Architecture invariant 5 keeps the live
    loop and `research/` from importing each other, and the obvious consequence of that
    rule — two implementations of one indicator, drifting — is the defect that makes a
    backtest meaningless while every test stays green, because each implementation is
    tested against itself and nothing ever compares them.

    The two inputs are deliberately **not** the same object. The live path is handed money
    as the decimal strings engine 3 publishes, truncated to `market_sensor.published_bars`
    and shaped by engine 3's own `MarketSensorState`; the offline path is handed the whole
    archive frame with `Decimal` money. If the shaping on either side loses or gains a bar
    the last row's lookbacks move and the two disagree — which is the failure worth
    catching and is invisible if the criterion hands both paths one pre-shaped frame.

    Comparison is **exact**. `float(Decimal("20.24"))` and `float("20.24")` are the same
    double, so two callers of one function have no licence to differ in the last bit, and
    a tolerance would hide a genuinely different computation whose answers happen to be
    close — which is what a drifting second implementation looks like early on.
    """
    polars, problem = _polars()
    if polars is None:
        return problem or pending("polars is unavailable")

    frame, problem = _feature_fixture_frame(ctx)
    if frame is None:
        return problem or pending(CANDLES_FIXTURE.as_posix() + " could not be read")

    config_map, problem = load_config(ctx.root)
    if config_map is None:
        return problem or pending("config/default.yaml could not be read")
    values, problem = required_thresholds(
        config_map, (KEY_DECISION_BAR_S, KEY_PUBLISHED_BARS, KEY_MIN_LOOKBACK_FILL)
    )
    if problem is not None:
        return _with_contract(
            problem,
            "the feature keys are not in config/default.yaml yet",
            "spec 61 (A-2) lands `features.min_lookback_fill`; this criterion needs it, "
            "`timeframes.decision_bar_s` and `market_sensor.published_bars` to shape the "
            "live and offline paths identically",
        )
    interval_s = int(values[KEY_DECISION_BAR_S])
    published_bars = int(values[KEY_PUBLISHED_BARS])
    min_fill = float(values[KEY_MIN_LOOKBACK_FILL])

    source_path = ctx.root / "src" / "acsoe" / "modelling" / "features.py"

    with root_import_path(ctx.root):
        module, problem = _phase5_module("acsoe.modelling.features")
        if module is None:
            return problem or pending("acsoe.modelling.features does not exist yet")
        if not source_path.is_file():
            return pending(
                "src/acsoe/modelling/features.py does not exist yet (spec 63, C-2); the "
                "import resolved to " + str(getattr(module, "__file__", "?"))
            )

        hits = _book_column_hits(source_path.read_text(encoding="utf-8"))
        if hits:
            return failed(
                "modelling/features.py reads a book-derived column: "
                + "; ".join(hits[:4])
                + ". The historical archive is OHLCVT — no bid, no ask, no depth, no "
                "spread — so a feature reading one is computable live and not computable "
                "in replay, and every backtest number it touched describes a model the "
                "live loop cannot reproduce. architecture-context.md states it as a "
                "Phase 5 rule."
            )

        surface, problem = _feature_surface(module)
        if surface is None:
            return problem or pending("acsoe.modelling.features is incomplete (spec 63)")
        compute, names, version, max_lookback = surface

        named_after_the_book = [
            name for name in names if any(word in name.lower() for word in BOOK_COLUMNS)
        ]
        if named_after_the_book:
            return failed(
                "FEATURE_NAMES carries "
                + ", ".join(named_after_the_book)
                + ", named after an input the archive does not have"
            )
        if max_lookback > published_bars:
            return failed(
                "MAX_LOOKBACK_BARS is "
                + str(max_lookback)
                + " and `"
                + KEY_PUBLISHED_BARS
                + "` is "
                + str(published_bars)
                + ". Engine 3 publishes the smaller number, so the live path can never "
                "fill the longest window while the offline builder fills it every time — "
                "the two paths then differ on every bar, silently, with the offline "
                "number being the one that looks right."
            )

        money = [c for c in ("open", "high", "low", "close", "volume") if c in frame.columns]
        floats = frame.with_columns([polars.col(c).cast(polars.Float64) for c in money])
        offline = compute(floats, interval_s=interval_s, min_lookback_fill=min_fill)
        if "ts" not in offline.columns:
            return failed(
                "modelling.features.compute returned a frame with no `ts` column; without "
                "it nothing downstream can join a feature row to a label"
            )

        pair = "SOLUSD"
        bar_ts = int(frame["ts"].max())
        sensor, problem = _sensor_payload_through_the_real_contract(
            frame,
            pair=pair,
            bar_ts=bar_ts,
            published_bars=published_bars,
            interval_s=interval_s,
        )
        if sensor is None:
            return problem or pending("engine 3 `market_sensor` does not exist yet")

        engine_cls, problem = _phase5_engine_class("feature")
        if engine_cls is None:
            return problem or _phase5_engine_absent("feature")

        engine_config, problem = _phase3_config()
        if engine_config is None:
            return problem or pending("the committed config could not be loaded")
        clients, problem = _fake_clients()
        if clients is None:
            return problem or pending("the shared test doubles are unavailable")
        context, problem = _engine_context(
            engine_config, clients, run_id="verify-phase-5", now=PHASE5_NOW
        )
        if context is None:
            return problem or pending("acsoe.core.contracts does not exist yet")

        result = engine_cls().process(context, {"market_sensor": sensor})
        data = dict(getattr(result, "data", {}) or {})
        offline_row = _feature_values(offline.tail(1).to_dicts()[0], names)
        # The same arithmetic over the same candles engine 5 was handed. This is what the
        # exact comparison below is against; `offline_row` is the whole-archive frame and
        # is compared within a tolerance, for the reason in the docstring.
        same_window = compute(
            floats.tail(published_bars),
            interval_s=interval_s,
            min_lookback_fill=min_fill,
        )
        window_row = _feature_values(same_window.tail(1).to_dicts()[0], names)

    pairs = data.get("pairs")
    if not isinstance(pairs, Mapping) or pair not in pairs:
        return failed(
            "engine 5 published no feature row for "
            + pair
            + " on a tick where `bar_closed` was true and "
            + str(published_bars)
            + " candles were available; it published "
            + repr(sorted(data))[:200]
        )
    live_row = _feature_values(pairs[pair], names)

    published_version = data.get("feature_version")
    if published_version != version:
        return failed(
            "engine 5 published feature_version "
            + repr(published_version)
            + " while modelling.features.FEATURE_VERSION is "
            + repr(version)
            + ". An artefact records the version it was trained at and engine 8 refuses "
            "one that disagrees, so two spellings mean an artefact can be loaded by an "
            "engine computing something else."
        )

    # (1) EXACT, with the frame length held still. Engine 5 may group, cast, truncate and
    # turn NaN into null; it may not change a number. Any difference here is a difference
    # in shaping and there is no licence for one.
    mismatches = [
        f"{name}: engine 5={live_row[name]!r} modelling={window_row[name]!r}"
        for name in names
        if live_row[name] != window_row[name]
    ]
    if mismatches:
        return failed(
            str(len(mismatches))
            + " of "
            + str(len(names))
            + " features differ between engine 5's live path and modelling.features over "
            "the very same candles: "
            + "; ".join(mismatches[:4])
            + ". One arithmetic in modelling/ is the point of the package, and with the "
            "same rows in, the engine's shaping must not move a single bit."
        )

    # (2) BOUNDED, across the frame lengths the two sides really see. The live loop is
    # given `market_sensor.published_bars` candles and the trainer the whole archive;
    # polars accumulates its rolling aggregates along the column, so the same window lands
    # on slightly different bits depending on how many rows preceded it. Measured here at
    # a relative 7.4e-15 worst case, which is reassociation and not arithmetic. The bound
    # is six orders of magnitude above that and many orders below any genuine difference
    # in formula, which shows up as percent rather than as parts per billion.
    worst = 0.0
    worst_name = ""
    drifted: list[str] = []
    for name in names:
        live = live_row[name]
        offline = offline_row[name]
        if live is None or offline is None:
            if live is not offline:
                drifted.append(f"{name}: live={live!r} archive={offline!r} (one is null)")
            continue
        scale = max(abs(live), abs(offline), 1e-12)
        relative = abs(live - offline) / scale
        if relative > worst:
            worst, worst_name = relative, name
        if relative > FEATURE_REASSOCIATION_TOLERANCE:
            drifted.append(f"{name}: live={live!r} archive={offline!r} rel={relative:.2e}")
    if drifted:
        return failed(
            str(len(drifted))
            + " features differ between the "
            + str(published_bars)
            + "-bar live window and the whole archive frame by more than "
            f"{FEATURE_REASSOCIATION_TOLERANCE:.0e}"
            + " relative: "
            + "; ".join(drifted[:4])
            + ". Floating-point reassociation inside a rolling kernel is parts per "
            "quadrillion; a difference this large is a different computation, or a "
            "lookback the live window is too short to fill."
        )

    filled = sum(1 for name in names if live_row[name] is not None)
    return passed(
        str(len(names))
        + " features (version "
        + version
        + ") reproduce on bar "
        + str(bar_ts)
        + " of "
        + CANDLES_FIXTURE.as_posix()
        + ": engine 5's live path and modelling.features agree EXACTLY over the same "
        + str(published_bars)
        + " candles ("
        + str(filled)
        + " filled), and agree with the whole-archive frame to "
        + (f"{worst:.1e} relative (worst: {worst_name})" if worst_name else "the last bit")
        + "; no feature reads a spread, bid, ask or depth"
    )


# --- feature_lookbacks_are_time_not_rows ----------------------------------- #


def check_feature_lookbacks_are_time_not_rows(ctx: VerifyContext) -> Outcome:
    """A lookback is a window of seconds, and a hole inside it is missing data.

    The archives contain only intervals in which trades occurred, so a missing candle
    means *no trades* and nothing may interpolate one into existence. That leaves two
    readings of "the last n bars", identical on every contiguous series and different on
    exactly the quiet periods this market has most of:

    * **Rows.** The previous n rows whatever their timestamps. Across a six-hour hole that
      is a window reaching back most of a day, and every z-score and range built on it is
      a statement about a different market.
    * **Time.** The rows inside ``n * interval_s`` seconds. Across the same hole the window
      holds a handful of bars, the counter says so, and every feature over it is NaN
      because the fill is below `features.min_lookback_fill`.

    It is the same rule the timeout barrier is held to in `architecture-context.md`,
    arriving one layer down.

    The series is **constructed**, like `walkforward_folds_purged_and_embargoed`'s rows:
    the hole has to sit immediately behind the bar under test, and no committed slice can
    be relied on to have one there. The hole is made **wider than the window minus the
    tail**, which is not fussiness — with a narrower hole the window legitimately still
    reaches past it and the expected count is a sum of two runs, which is how a first
    version of this check went red against a correct implementation.
    """
    polars, problem = _polars()
    if polars is None:
        return problem or pending("polars is unavailable")

    config_map, problem = load_config(ctx.root)
    if config_map is None:
        return problem or pending("config/default.yaml could not be read")
    values, problem = required_thresholds(
        config_map, (KEY_DECISION_BAR_S, KEY_MIN_LOOKBACK_FILL)
    )
    if problem is not None:
        return _with_contract(
            problem,
            "`" + KEY_MIN_LOOKBACK_FILL + "` is not in config/default.yaml yet",
            "spec 61 (A-2). A window whose fill is below it yields NaN for every feature "
            "over it, and without the key there is nothing to compare a fill against",
        )
    interval_s = int(values[KEY_DECISION_BAR_S])
    min_fill = float(values[KEY_MIN_LOOKBACK_FILL])

    with root_import_path(ctx.root):
        module, problem = _phase5_module("acsoe.modelling.features")
        if module is None:
            return problem or pending("acsoe.modelling.features does not exist yet")
        surface, problem = _feature_surface(module)
        if surface is None:
            return problem or pending("acsoe.modelling.features is incomplete (spec 63)")
        compute, names, _version, _max_lookback = surface

        counters = {
            name: int(match.group(1))
            for name in names
            if (match := re.fullmatch(r"bars_in_lookback_(\d+)", name)) is not None
        }
        if not counters:
            return pending(
                "FEATURE_NAMES carries no `bars_in_lookback_<n>` feature. Spec 63 makes "
                "the fill of each lookback a feature in its own right, because a window "
                "two thirds empty is a fact a model and an operator both need, and it is "
                "the only thing that distinguishes a short window from a quiet market. "
                "Names seen: " + ", ".join(names[:8]) + ("..." if len(names) > 8 else "")
            )
        counter_name = max(counters, key=lambda key: counters[key])
        window_bars = counters[counter_name]

        tail_bars = max(2, window_bars // 4)
        hole_bars = window_bars  # wider than window - tail, so the count is unambiguous
        origin = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
        stamps = [origin + i * interval_s for i in range(window_bars * 3)]
        resume = stamps[-1] + (hole_bars + 1) * interval_s
        stamps.extend(resume + i * interval_s for i in range(tail_bars))

        rows: list[dict[str, Any]] = []
        price = 100.0
        for index, ts in enumerate(stamps):
            # Deterministic and deliberately not flat: a constant series makes every
            # range and volume feature zero, and a check comparing zeros passes against
            # arithmetic that never ran.
            price = price * (1.0 + 0.0013 * ((index % 7) - 3))
            rows.append(
                {
                    "ts": ts,
                    "open": price * 0.999,
                    "high": price * 1.004,
                    "low": price * 0.996,
                    "close": price,
                    "volume": 1000.0 + 37.0 * (index % 11),
                    "trades": 20 + (index % 5),
                }
            )
        computed = compute(
            polars.DataFrame(rows), interval_s=interval_s, min_lookback_fill=min_fill
        )

    if "ts" not in computed.columns:
        return failed("modelling.features.compute returned a frame with no `ts` column")
    last = computed.filter(polars.col("ts") == stamps[-1])
    if last.height != 1:
        return failed(
            "compute produced "
            + str(last.height)
            + " rows for the last decision bar; one bar in, one feature row out"
        )
    row = _feature_values(last.to_dicts()[0], names)

    reported = row.get(counter_name)
    if reported is None:
        return failed(counter_name + " is null on a bar that has candles behind it")
    if int(reported) != tail_bars:
        return failed(
            counter_name
            + " reported "
            + str(int(reported))
            + " over a "
            + str(window_bars)
            + "-bar window containing a "
            + str(hole_bars)
            + "-bar hole. A lookback counted in ROWS reaches back past the hole and "
            "reports "
            + str(window_bars)
            + "; a lookback counted in TIME reports "
            + str(tail_bars)
            + ". The archive's holes are periods with no trades, so the rows on the far "
            "side of one describe a different market and nothing may stretch a window "
            "over them."
        )

    fill = int(reported) / window_bars
    if fill >= min_fill:
        return failed(
            "the constructed hole leaves a fill of "
             f"{fill:.3f}"
             ", not below `"
            + KEY_MIN_LOOKBACK_FILL
            + "` = "
            + f"{min_fill:.3f}"
            + ", so this criterion cannot ask the NaN question it exists to ask. That is "
            "a fault in the construction here, not in the feature module."
        )

    # Only the features of the deficient window. A bar's own range and the hour of the
    # day are known whatever the history behind them looks like, and the shorter windows
    # may legitimately be full; blanking those too would throw away the rows a
    # short-history pair can be judged on, which is the opposite of what engine 5 does
    # when it lists a pair rather than dropping it.
    suffix = f"_{window_bars}"
    of_this_window = [
        name for name in names if name.endswith(suffix) and name != counter_name
    ]
    if not of_this_window:
        return failed(
            "no feature other than the counter is named for the "
            + str(window_bars)
            + "-bar window, so this criterion has nothing to assert about NaN"
        )
    still_filled = [name for name in of_this_window if row[name] is not None]
    if still_filled:
        return failed(
            str(len(still_filled))
            + " features carry a value over a window only "
            + f"{fill:.1%}"
            + " filled, below `"
            + KEY_MIN_LOOKBACK_FILL
            + "` = "
            + f"{min_fill:.3f}"
            + ": "
            + ", ".join(still_filled[:5])
            + ". A number computed over a mostly-absent window is indistinguishable from "
            "one computed over a full window, and spec 63 says it is NaN. Nothing is "
            "interpolated and nothing is stretched."
        )

    return passed(
        counter_name
        + " reported "
        + str(int(reported))
        + " of "
        + str(window_bars)
        + " bars across a constructed "
        + str(hole_bars)
        + "-bar hole (a row-counted lookback would report "
        + str(window_bars)
        + "), and all "
        + str(len(of_this_window))
        + " features over that window are NaN at a fill of "
        + f"{fill:.3f}"
        + " against `"
        + KEY_MIN_LOOKBACK_FILL
        + "` = "
        + f"{min_fill:.3f}"
    )


# --------------------------------------------------------------------------- #
# The trainer's seam, driven by criteria 3 to 7
# --------------------------------------------------------------------------- #
#
# Spec 60 and spec 67 are two halves of one seam and both are C's. A criterion asserting
# a field the trainer never writes can only ever be red; a trainer writing a field
# nothing reads is a number nobody checks. So the names live in one place -
# `FOLD_DIGEST_FIELDS` above and the four symbols below - and both halves are built
# against them rather than against each other's prose.

#: What `acsoe.research.training` must expose for these criteria to drive it.
TRAINING_CONTRACT: Final = (
    "expected acsoe.research.training: "
    "build_dataset(labelled, candles, *, config, macro_archive=None) -> pl.DataFrame "
    "carrying pair, decision_ts, label, label_window_end_ts, return_pct, weight and one "
    "column per FEATURE_NAMES; "
    "train_walkforward(dataset, *, config, models_dir, derived_dir, now, max_folds=None) "
    "-> TrainingReport with .run_id, .fold_runs (one artefact run id per fold), .folds "
    "(one mapping per fold carrying " + ", ".join(FOLD_DIGEST_FIELDS) + "), .digest, "
    ".digest_path and .oos_path"
)

#: Columns the pooled dataset must carry beside the features. `pair` is an identifier and
#: is **never** a feature: a pooled model that can memorise a pair name has learned which
#: pairs went up in the training window and nothing that transfers.
DATASET_COLUMNS: Final[tuple[str, ...]] = (
    "pair",
    "decision_ts",
    "label",
    "label_window_end_ts",
    "return_pct",
    "weight",
)

#: Columns the out-of-sample file must carry. Specs 69, 74 and 75 read this file and
#: nothing else, so a missing column here is three specs with nothing to stand on.
OOS_COLUMNS: Final[tuple[str, ...]] = (
    "pair",
    "decision_ts",
    "label_window_end_ts",
    "fold_index",
    "p_target",
    "p_stop",
    "p_timeout",
    "expected_move_pct",
    "is_buy",
    "di",
    "di_refused",
    "label",
    "return_pct",
    "weight",
)

#: The constructed dataset the training criteria are driven over: two pairs, long enough
#: to hold several weekly folds behind a ninety-day training window, small enough that
#: five criteria can each train over it inside one gate run.
#:
#: **The committed sample cannot do this job and that is not a fixable oversight.**
#: `labelled_sample.parquet` is ten days of one pair, and `backtest.training_window_days`
#: is 90, so a rolling walk-forward over it produces **no folds at all** - and an
#: assertion over an empty fold list is the shape this project has been burned by three
#: times. Spec 60 was amended on 2026-09-13 to say so.
CONSTRUCTED_DAYS: Final = 140
CONSTRUCTED_PAIRS: Final[tuple[str, ...]] = ("AAAUSD", "BBBUSD")
CONSTRUCTED_MAX_FOLDS: Final = 2


def _training_module() -> tuple[ModuleType | None, Outcome | None]:
    module, problem = _phase5_module("acsoe.research.training")
    if module is None:
        return None, _with_contract(
            problem,
            "acsoe.research.training does not exist yet (spec 67, C-2)",
            TRAINING_CONTRACT,
        )
    return module, None


def _constructed_candles(polars: ModuleType, *, pair: str, interval_s: int) -> Any:
    """A deterministic price series per pair, long enough for several weekly folds.

    Seeded arithmetic rather than a random generator, so two runs of the gate a week
    apart produce the same bars and `training_is_reproducible_from_config_and_data` is
    measuring the trainer rather than the weather. Each pair gets a different phase and
    drift, because two identical series would make a pooled model's pair column and its
    feature columns carry the same information and the "no pair identity" property
    untestable.
    """
    bars = CONSTRUCTED_DAYS * 86_400 // interval_s
    origin = (int(datetime(2024, 1, 1, tzinfo=UTC).timestamp()) // interval_s) * interval_s
    offset = sum(ord(char) for char in pair)
    rows: list[dict[str, Any]] = []
    price = 100.0 + (offset % 17)
    for index in range(bars):
        # A wobble with a slow cycle on top, so the series has both quiet and volatile
        # stretches and the labels come out mixed rather than all `stop`.
        wobble = 0.0022 * (((index + offset) % 11) - 5) / 5.0
        swing = 0.004 * math.sin((index + offset) / 97.0)
        price = max(price * (1.0 + wobble + swing), 0.01)
        span = abs(wobble + swing) + 0.0008
        rows.append(
            {
                "ts": origin + index * interval_s,
                "open": price * (1.0 - span / 3),
                "high": price * (1.0 + span),
                "low": price * (1.0 - span),
                "close": price,
                "volume": 900.0 + 60.0 * ((index + offset) % 13),
                "trades": 15 + ((index + offset) % 9),
            }
        )
    return polars.DataFrame(rows)


#: The candle builder `_constructed_dataset` uses unless a caller names another. A
#: parameter rather than a hardcoded call because Phase 6 needs a *different* series
#: from the same pipeline: the Phase 5 criteria want a mixed, unremarkable market, and
#: spec 100 wants one with a pattern in it that precedes a target touch. Same labeller,
#: same features, same trainer - only the prices differ, which is the line "fabricate
#: the subject, never the contract" draws.
CandleBuilder = Callable[..., Any]


def _constructed_dataset(
    ctx: VerifyContext,
    polars: ModuleType,
    training: ModuleType,
    engine_config: Any,
    candles_builder: CandleBuilder | None = None,
    *,
    macro_archive: Mapping[str, str] | None = None,
) -> tuple[Any, Outcome | None]:
    """The pooled, labelled, featured, weighted frame the trainer takes.

    `macro_archive` is `build_dataset`'s own argument, passed only when a caller names one:
    the Phase 5 criteria train without macro columns, and spec 105's subject trains with
    them because engines 8 and 15 assemble their vectors from engine 6 as well.

    Built through the **real** labeller and the **real** feature module: only the prices
    are this criterion's. Fabricate the subject, never the contract.
    """
    labelling, problem = try_import("acsoe.research.labelling")
    if labelling is None:
        return None, _with_contract(
            problem,
            "acsoe.research.labelling does not exist yet",
            PHASE4_RESEARCH["acsoe.research.labelling"],
        )
    label_frame, missing = module_attr(labelling, "label_frame")
    if label_frame is None:
        return None, pending(missing)
    builder, problem = _phase5_symbol(training, "build_dataset", "acsoe.research.training")
    if builder is None:
        return None, _with_contract(problem, "build_dataset is absent", TRAINING_CONTRACT)

    interval_s = int(engine_config.get(KEY_DECISION_BAR_S))
    candles: dict[str, Any] = {}
    labelled: dict[str, Any] = {}
    for pair in CONSTRUCTED_PAIRS:
        build = candles_builder or _constructed_candles
        frame = build(polars, pair=pair, interval_s=interval_s)
        decimal_frame = frame.with_columns(
            [
                polars.col(column).cast(polars.Decimal(38, 12))
                for column in ("open", "high", "low", "close", "volume")
            ]
        )
        labels, _series = label_frame(
            decimal_frame, pair=pair, config=engine_config, interval_s=interval_s
        )
        candles[pair] = frame
        labelled[pair] = labels
    if macro_archive is None:
        dataset = builder(labelled, candles, config=engine_config)
    else:
        dataset = builder(labelled, candles, config=engine_config, macro_archive=macro_archive)
    del ctx
    return dataset, None


def _trained(
    ctx: VerifyContext,
    tmp: Path,
    *,
    name: str = "run",
    max_folds: int = CONSTRUCTED_MAX_FOLDS,
    now: datetime | None = None,
    overrides: Mapping[str, Any] | None = None,
    candles_builder: CandleBuilder | None = None,
    macro_archive: Mapping[str, str] | None = None,
) -> tuple[tuple[Any, Any, Any] | None, Outcome | None]:
    """`(report, dataset, config)` from one training run into a temporary models root.

    **Nothing here reads `models/`, `data/` or `logs/`.** All three are gitignored, so a
    criterion that depended on one would pass only on the machine that produced it. The
    artefacts are written into `tmp` and thrown away with it.

    `overrides` answers named keys for the **trainer only**, never the committed file: a
    criterion that needs a subject the operator's withheld key would otherwise prevent
    (a DI, while `prediction.di_percentile` is absent) supplies its own value here and says
    so, and the config it returns is the one the trainer saw.
    """
    polars, problem = _polars()
    if polars is None:
        return None, problem
    training, problem = _training_module()
    if training is None:
        return None, problem
    engine_config, problem = _phase3_config()
    if engine_config is None:
        return None, problem or pending("the committed config could not be loaded")
    trainer, problem = _phase5_symbol(
        training, "train_walkforward", "acsoe.research.training"
    )
    if trainer is None:
        return None, _with_contract(problem, "train_walkforward is absent", TRAINING_CONTRACT)

    dataset, problem = _constructed_dataset(
        ctx, polars, training, engine_config, candles_builder, macro_archive=macro_archive
    )
    if dataset is None:
        return None, problem
    if overrides:
        engine_config = _ConfigWith(engine_config, overrides)
    models_dir = tmp / name / "models"
    derived_dir = tmp / name / "derived"
    models_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = trainer(
            dataset,
            config=engine_config,
            models_dir=models_dir,
            derived_dir=derived_dir,
            now=PHASE5_NOW if now is None else now,
            max_folds=max_folds,
        )
    except TypeError as exc:
        return None, _with_contract(
            None,
            "acsoe.research.training.train_walkforward does not accept the call this "
            "criterion makes: " + str(exc)[:200],
            TRAINING_CONTRACT,
        )
    return (report, dataset, engine_config), None


class _ConfigWith:
    """The committed config with named keys answered, and nothing else changed."""

    def __init__(self, inner: Any, overrides: Mapping[str, Any]) -> None:
        self._inner = inner
        self._overrides = dict(overrides)

    def get(self, dotted_key: str, /) -> Any:
        if dotted_key in self._overrides:
            return self._overrides[dotted_key]
        return self._inner.get(dotted_key)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _fold_entries(report: Any) -> tuple[list[dict[str, Any]] | None, Outcome | None]:
    folds = getattr(report, "folds", None)
    if not folds:
        return None, failed(
            "the training run reported no folds. A rolling walk-forward over "
            + str(CONSTRUCTED_DAYS)
            + " days at `backtest.retrain_interval_days` must produce several, and an "
            "assertion over an empty fold list is an assertion over nothing."
        )
    entries = [dict(entry) for entry in folds]
    absent = [
        field for field in FOLD_DIGEST_FIELDS if any(field not in entry for entry in entries)
    ]
    if absent:
        return None, failed(
            "a fold entry is missing " + ", ".join(absent) + ". Every one of "
            + ", ".join(FOLD_DIGEST_FIELDS)
            + " is reported per fold; the effective sample size in particular sits beside "
            "that fold's row count by operator addition, because an aggregate hides the "
            "fold whose 8,000 rows are 300 observations."
        )
    return entries, None


def _identity_of(frame: Any, polars: ModuleType) -> set[str]:
    """`{pair|decision_ts}` for every row of a dataset or OOS frame."""
    del polars
    return {
        f"{row['pair']}|{int(row['decision_ts'])}"
        for row in frame.select(["pair", "decision_ts"]).iter_rows(named=True)
    }


def _fold_indices(
    dataset: Any, engine_config: Any, *, interval_s: int
) -> tuple[list[Any] | None, Outcome | None]:
    """The folds this criterion recomputes for itself, from the public splitter.

    **Recomputed, never read back from the artefact.** Ruling 7 of 2026-09-13: an identity
    proof that trusts the number the subject reported is not a proof. The splitter is
    deterministic and public, so the criterion can derive the truth and compare.
    """
    module, problem = try_import("acsoe.research.walkforward")
    if module is None:
        return None, problem or pending("acsoe.research.walkforward does not exist yet")
    splitter, missing = module_attr(module, "purged_walk_forward")
    if splitter is None:
        return None, pending(missing)
    rows = dataset.select(["decision_ts", "label_window_end_ts"]).to_dicts()
    return splitter(rows, config=engine_config, interval_s=interval_s), None


# --- predictor_trains_and_calibrates --------------------------------------- #


def check_predictor_trains_and_calibrates(ctx: VerifyContext) -> Outcome:
    """A predictor trains, its probabilities are a distribution, and the metric is Brier.

    Four claims, and the last is the one this phase turns on.

    **Three probabilities summing to one.** An unrenormalised calibrator scales every
    expected move by an unknown factor, and the ranking between candidates survives it, so
    the BUY boundary moves while everything still looks internally consistent.

    **A calibrator is present.** LightGBM's raw multiclass output is not calibrated, and
    an `expected_move_pct` computed from uncalibrated probabilities is a number in the
    right range and the wrong size.

    **The manifest carries the ordered feature list and the scaler.** A model without its
    exact feature order is unusable; `code-standards.md` says so and the artefact loader
    refuses one, but only if the manifest recorded it.

    **Brier against the fold's base-rate Brier, and accuracy nowhere.** The base rate is
    23.89%, so a model that always predicts `stop` is right 51% of the time: a digest
    reporting accuracy is reporting the model that never trades. `accuracy` present is a
    FAIL rather than a warning, because the number itself is what misleads.
    """
    with tempfile.TemporaryDirectory(prefix="acsoe-verify-train-") as raw_tmp:
        tmp = Path(raw_tmp)
        with root_import_path(ctx.root):
            trained, problem = _trained(ctx, tmp)
            if trained is None:
                return problem or pending("acsoe.research.training does not exist yet")
            report, _dataset, _engine_config = trained

            entries, problem = _fold_entries(report)
            if entries is None:
                return problem or failed("the training run reported no folds")

            artefacts, problem = _phase5_module("acsoe.modelling.artefacts")
            if artefacts is None:
                return problem or pending("acsoe.modelling.artefacts does not exist yet")
            features_mod, problem = _phase5_module("acsoe.modelling.features")
            if features_mod is None:
                return problem or pending("acsoe.modelling.features does not exist yet")
            feature_names = tuple(str(n) for n in features_mod.FEATURE_NAMES)

            fold_runs = list(getattr(report, "fold_runs", ()) or ())
            if len(fold_runs) != len(entries):
                return failed(
                    "the run reported "
                    + str(len(entries))
                    + " folds and "
                    + str(len(fold_runs))
                    + " artefact run ids. One artefact directory per fold, never "
                    "overwritten, is what makes a fold's metrics traceable to the model "
                    "that produced them."
                )

            run_dir = Path(str(getattr(report, "models_dir", tmp / "run" / "models")))
            directory = run_dir / fold_runs[0]
            try:
                loaded = artefacts.load_run(
                    directory,
                    expected_features=[
                        str(name) for name in entries[0].get("feature_names", feature_names)
                    ],
                )
            except Exception as exc:
                return failed(
                    "the first fold's artefact would not load from "
                    + str(directory)
                    + ": "
                    + f"{type(exc).__name__}: {exc}"[:300]
                )

            manifest = loaded.manifest
            if not manifest.feature_names:
                return failed(
                    "the manifest carries no feature list. A model without its exact "
                    "feature order is unusable: hand LightGBM the same columns in a "
                    "different order and it returns confident nonsense with nothing "
                    "raising."
                )
            if tuple(manifest.feature_names[: len(feature_names)]) != feature_names:
                return failed(
                    "the manifest's feature list does not begin with FEATURE_NAMES in "
                    "order; the macro columns follow them, they do not replace them"
                )
            if not loaded.scaler.feature_names:
                return failed("scaler.json carries no feature names")
            if tuple(manifest.class_order) != PHASE5_CLASS_ORDER:
                return failed(
                    "the manifest records class order "
                    + repr(tuple(manifest.class_order))
                    + "; it must be "
                    + repr(PHASE5_CLASS_ORDER)
                    + ", because the three probabilities are read positionally by engine "
                    "8 and a permuted order swaps `target` for `stop` silently"
                )
            if not manifest.extras.get("calibrator"):
                return failed(
                    "the manifest names no calibrator. LightGBM's raw multiclass output "
                    "is not calibrated, and an expected move computed from uncalibrated "
                    "probabilities is a number in the right range and the wrong size."
                )

    first = entries[0]
    for field in ("brier", "base_rate_brier"):
        if first.get(field) is None:
            return failed(
                "fold 0 reports no `"
                + field
                + "`. The evaluation number is the Brier of P(target) against the fold's "
                "own base-rate Brier; a Brier with nothing to compare it to says nothing."
            )
    offending = [
        entry.get("fold_index") for entry in entries if FORBIDDEN_METRIC in entry
    ]
    if offending:
        return failed(
            "`"
            + FORBIDDEN_METRIC
            + "` is reported on fold(s) "
            + repr(offending)
            + ". It is retired by operator ruling of 2026-09-12 and computed nowhere: at "
            "a 23.89% target rate a model that always predicts `stop` scores 51%, so a "
            "digest carrying it is reporting the model that never trades."
        )

    return passed(
        str(len(entries))
        + " fold(s) trained over a constructed "
        + str(CONSTRUCTED_DAYS)
        + "-day, "
        + str(len(CONSTRUCTED_PAIRS))
        + "-pair dataset into a temporary models root: probabilities over "
        + repr(PHASE5_CLASS_ORDER)
        + ", a calibrator named in the manifest, the ordered feature list and the scaler "
        "present, Brier "
        + f"{float(first['brier']):.4f}"
        + " against a base-rate Brier of "
        + f"{float(first['base_rate_brier']):.4f}"
        + " on fold 0, and no accuracy anywhere"
    )


# --- training_is_reproducible_from_config_and_data ------------------------- #


def check_training_is_reproducible_from_config_and_data(ctx: VerifyContext) -> Outcome:
    """Two runs over one config and one dataset agree, and a run id is never reused.

    "A run that cannot be reproduced from its config plus its data is not a result" is in
    `code-standards.md` and it is the only thing that makes a leaderboard comparable
    across weeks. The check is behavioural rather than a source scan: a seed taken from
    the clock, a thread count left to the machine, a dictionary iterated in insertion
    order — every one of them shows up here as two runs disagreeing, and none of them
    would show up in a grep.

    The second half is the refusal. `models/<run_id>/` is written once and never
    overwritten, so a second run into an existing run id must raise rather than replace:
    an overwritten artefact makes every leaderboard row that referenced it a claim about a
    model that no longer exists.
    """
    with tempfile.TemporaryDirectory(prefix="acsoe-verify-repro-") as raw_tmp:
        tmp = Path(raw_tmp)
        with root_import_path(ctx.root):
            first, problem = _trained(ctx, tmp, name="one", max_folds=1)
            if first is None:
                return problem or pending("acsoe.research.training does not exist yet")
            # One second later, which is what distinguishes two real runs. Injecting the
            # **same** instant into both made them one run by construction, and the
            # criterion then failed them for sharing a run id - asserting a property its
            # own fixture had made impossible, and one that could only have been satisfied
            # by putting a random suffix into an id whose whole job is to be reproducible.
            second, problem = _trained(
                ctx, tmp, name="two", max_folds=1, now=PHASE5_NOW + timedelta(seconds=1)
            )
            if second is None:
                return problem or pending("acsoe.research.training does not exist yet")

            report_one, _dataset, _config = first
            report_two, _dataset2, _config2 = second

            entries_one, problem = _fold_entries(report_one)
            if entries_one is None:
                return problem or failed("the first run reported no folds")
            entries_two, problem = _fold_entries(report_two)
            if entries_two is None:
                return problem or failed("the second run reported no folds")

            differing = [
                field
                for field in FOLD_DIGEST_FIELDS
                if entries_one[0].get(field) != entries_two[0].get(field)
            ]
            if differing:
                return failed(
                    "two runs over the same config and the same data disagree on "
                    + ", ".join(differing)
                    + " for fold 0: "
                    + repr({f: (entries_one[0].get(f), entries_two[0].get(f)) for f in differing})[
                        :260
                    ]
                    + ". Every seed comes from config; a seed from the clock, an unfixed "
                    "thread count or an insertion-ordered dictionary all look exactly "
                    "like this."
                )

            runs_one = list(getattr(report_one, "fold_runs", ()) or ())
            runs_two = list(getattr(report_two, "fold_runs", ()) or ())
            if not runs_one or not runs_two:
                return failed("a training run reported no artefact run ids")
            if set(runs_one) & set(runs_two):
                return failed(
                    "the two runs share the artefact run id(s) "
                    + repr(sorted(set(runs_one) & set(runs_two)))
                    + ". A run id identifies one training run; reusing it means the "
                    "second run either overwrote the first or was refused, and the "
                    "leaderboard cannot tell which model a row describes."
                )

            # The assertion the fold metrics cannot make. Identical metrics would also be
            # produced by two models that differ in a way the four reported numbers happen
            # not to separate; identical bytes would not.
            model_one = (
                Path(str(getattr(report_one, "models_dir", tmp))) / runs_one[0] / "model.txt"
            )
            model_two = (
                Path(str(getattr(report_two, "models_dir", tmp))) / runs_two[0] / "model.txt"
            )
            if not model_one.is_file() or not model_two.is_file():
                return failed(
                    "a fold wrote no `model.txt`; the model is written as LightGBM's own "
                    "text dump rather than a pickle, because a pickle in an artefact "
                    "directory is code that runs inside the process that places orders"
                )
            if model_one.read_bytes() != model_two.read_bytes():
                return failed(
                    "two runs over the same config and the same data produced different "
                    "model bytes while agreeing on every reported metric. The metrics are "
                    "four numbers and the model is the thing a leaderboard row points at; "
                    "a seed from the clock, an unfixed thread count or a non-deterministic "
                    "histogram strategy all look exactly like this."
                )

            store_cls, problem = _store_class()
            if store_cls is None:
                return problem or pending("clients.store.client.StoreClient does not exist yet")
            db_path, store_mod, problem = _migrated_db(tmp, "repro.sqlite")
            if db_path is None:
                return problem or pending("the store could not be migrated")
            del store_mod
            models_root = tmp / "artefact-root"
            store = store_cls(db_path, models_dir=models_root)
            try:
                created = store.new_model_run_dir("train-verify-0")
                if not created.is_dir():
                    return failed(
                        "new_model_run_dir returned "
                        + str(created)
                        + ", which is not a directory"
                    )
                try:
                    store.new_model_run_dir("train-verify-0")
                except Exception as exc:
                    refusal = f"{type(exc).__name__}: {exc}"
                else:
                    return failed(
                        "new_model_run_dir accepted an existing run id and returned a "
                        "path. A trained artefact is never overwritten: an overwritten "
                        "one makes every leaderboard row that referenced it a claim "
                        "about a model that no longer exists."
                    )
            finally:
                close = getattr(store, "close", None)
                if callable(close):
                    close()

    return passed(
        "two runs over one config and one dataset agree on every reported field of fold 0 "
        "("
        + ", ".join(FOLD_DIGEST_FIELDS)
        + ") and were written under different run ids; writing into an existing run id is "
        "refused - " + refusal[:140]
    )


# --- di_fitted_on_predictor_training_set ----------------------------------- #


def check_di_fitted_on_predictor_training_set(ctx: VerifyContext) -> Outcome:
    """The DI saw the predictor's training rows, by identity, and not the BUY subset.

    **This is the criterion spec 68 exists for, and a row count cannot make it.** Fitted
    on the BUY subset the DI learns that "normal" means a BUY-shaped setup and then vetoes
    every ordinary market state: the veto rate is high, the few trades that survive look
    clean, and the leaderboard flatters the model. Nothing crashes and nothing goes red. A
    count of reference rows passes whenever the two sets happen to be the same size, and
    on a fold where most calls are BUY they usually are.

    So the criterion **recomputes both candidate sets itself** - ruling 7 of 2026-09-13 -
    from the dataset it trained on and the public splitter, and asks three questions of
    the identities the DI artefact actually recorded:

    * is every reference row one of the fold's **training** rows;
    * is at least one of them **not** a BUY call, so the set cannot be the BUY subset;
    * is none of them one of the fold's **test** rows.

    The second is the one that separates "fitted on the training rows" from "fitted on the
    BUY subset of them", and it is why the DI artefact records identities rather than a
    hash: a digest can prove two sets are equal and can never prove one contains another.
    """
    config_map, problem = load_config(ctx.root)
    if config_map is None:
        return problem or pending("config/default.yaml could not be read")
    withheld = _withheld_key(config_map, KEY_DI_PERCENTILE)
    if withheld is not None:
        return withheld

    with tempfile.TemporaryDirectory(prefix="acsoe-verify-di-") as raw_tmp:
        tmp = Path(raw_tmp)
        with root_import_path(ctx.root):
            trained, problem = _trained(ctx, tmp, max_folds=1)
            if trained is None:
                return problem or pending("acsoe.research.training does not exist yet")
            report, dataset, engine_config = trained
            polars, problem = _polars()
            if polars is None:
                return problem or pending("polars is unavailable")

            interval_s = int(engine_config.get(KEY_DECISION_BAR_S))
            folds, problem = _fold_indices(dataset, engine_config, interval_s=interval_s)
            if folds is None:
                return problem or pending("the splitter could not be run")
            if not folds:
                return failed("the splitter produced no folds over the constructed dataset")
            fold = folds[0]

            rows = dataset.select(["pair", "decision_ts"]).to_dicts()
            train_ids = {
                f"{rows[i]['pair']}|{int(rows[i]['decision_ts'])}" for i in fold.train_index
            }
            test_ids = {
                f"{rows[i]['pair']}|{int(rows[i]['decision_ts'])}" for i in fold.test_index
            }

            di_mod, problem = _phase5_module("acsoe.modelling.di")
            if di_mod is None:
                return problem or pending("acsoe.modelling.di does not exist yet")
            fold_runs = list(getattr(report, "fold_runs", ()) or ())
            if not fold_runs:
                return failed("the training run reported no artefact run ids")
            models_dir = Path(str(getattr(report, "models_dir", tmp / "run" / "models")))
            di_path = models_dir / fold_runs[0] / "di.npz"
            if not di_path.is_file():
                return failed(
                    "no di.npz beside the fold's predictor at "
                    + str(di_path)
                    + ". The DI is fitted per fold on that fold's training rows and is "
                    "written under the same run id, because a DI from another fold is a "
                    "reference set from another market."
                )
            fitted = di_mod.load(di_path)
            reference = set(fitted.identity)
            if not reference:
                return failed("di.npz records no reference identities")

            oos_path = Path(str(getattr(report, "oos_path", "")))
            if not oos_path.is_file():
                return failed(
                    "the run wrote no out-of-sample file; specs 69, 74 and 75 read it and "
                    "nothing else"
                )
            oos = polars.read_parquet(oos_path)
            buy_ids = _identity_of(oos.filter(polars.col("is_buy")), polars)

    outside = sorted(reference - train_ids)
    if outside:
        leaked = [entry for entry in outside if entry in test_ids]
        return failed(
            str(len(outside))
            + " DI reference rows are not among the fold's training rows"
            + (
                f", and {len(leaked)} of them are TEST rows ({leaked[:3]})"
                if leaked
                else f" (first: {outside[:3]})"
            )
            + ". The reference set is the predictor's training rows for the fold and "
            "nothing else; fitted on the test rows the DI accepts exactly the conditions "
            "the model is about to be scored on."
        )
    non_buy = reference - buy_ids
    if not non_buy:
        return failed(
            "every one of the "
            + str(len(reference))
            + " DI reference rows is a BUY call. The DI is fitted on the predictor's "
            "training rows, never on the skeptic's BUY subset: fitted on BUY rows it "
            "learns that `normal` means a BUY-shaped setup and vetoes every ordinary "
            "market state, which raises the veto rate, leaves a handful of clean-looking "
            "trades and flatters the leaderboard, with nothing going red."
        )

    return passed(
        str(len(reference))
        + " DI reference rows, every one of them among the fold's "
        + str(len(train_ids))
        + " training rows by (pair, decision_ts) identity, "
        + str(len(non_buy))
        + " of them not BUY calls so the set is not the BUY subset, and none among the "
        + str(len(test_ids))
        + " test rows"
    )


# --- di_leave_one_out_excludes_48_bars ------------------------------------- #

#: The percentile this criterion trains its subject at. **Not a proposal and not the
#: operator's value**, which has since been ruled at 0.99 (2026-09-15, provisional) and is
#: deliberately still not read here: the property this criterion checks — which rows the
#: leave-one-out leaves out — does not depend on where the line is drawn, and a criterion
#: that read the config would start moving whenever the operator retuned a provisional
#: number. Supplied to the trainer only, through `_trained(overrides=...)`.
DI_EXCLUSION_SUBJECT_PERCENTILE: Final = 0.90

#: How far the recorded distribution may sit from this criterion's recomputation. The
#: arithmetic is the same Euclidean expansion over different chunking, so the two agree to
#: floating-point noise or not at all.
DI_EXCLUSION_TOLERANCE: Final = 1e-9

#: When leaving out the row alone counts as materially different on the subject: the
#: row-only threshold, drawn at the same percentile, must sit below at least this multiple
#: of the share it is meant to refuse of the excluded distribution. Below it, the subject
#: could not tell the exclusion from its absence and a PASS would prove nothing.
DI_EXCLUSION_MATERIAL_MULTIPLE: Final = 2.0


def _loo_distribution(
    np_mod: ModuleType,
    reference: Any,
    decision_ts: Any,
    *,
    neighbours: int,
    span_s: int | None,
) -> Any:
    """The mean distance to the `neighbours` nearest reference rows, leaving rows out.

    Written here rather than borrowed from `acsoe.modelling.di`, because it is the thing
    being checked. `span_s=None` leaves out the row alone — the reading before the ruling of
    2026-09-15 — and a span leaves out every row, of any pair, whose `decision_ts` is within
    it of the row being scored, inclusive.
    """
    rows = int(reference.shape[0])
    norms = np_mod.einsum("ij,ij->i", reference, reference)
    out = np_mod.empty(rows, dtype=np_mod.float64)
    step = 256
    for start in range(0, rows, step):
        stop = min(start + step, rows)
        block = reference[start:stop]
        squared = norms[start:stop, None] + norms[None, :] - 2.0 * (block @ reference.T)
        distances = np_mod.sqrt(np_mod.clip(squared, 0.0, None))
        distances[np_mod.arange(stop - start), np_mod.arange(start, stop)] = np_mod.inf
        if span_s is not None:
            gap = np_mod.abs(decision_ts[None, :] - decision_ts[start:stop, None])
            distances[gap <= span_s] = np_mod.inf
        nearest = np_mod.sort(distances, axis=1)[:, :neighbours]
        out[start:stop] = nearest.mean(axis=1)
    return out


def check_di_leave_one_out_excludes_48_bars(ctx: VerifyContext) -> Outcome:
    """The DI's leave-one-out leaves out every reference row within 48 bars, across pairs.

    **Ruling of 2026-09-15, amending ruling 6.** 78 of the 117 DI columns are BTC and ETH
    macro features identical for every pair on the same bar, and the calendar columns are
    too, so leaving out only the row being scored leaves its same-moment rows in the
    reference set as near-duplicates. The threshold then measures **time proximity**, not
    distributional distance, and a live candidate — at least the embargo after the reference
    window, with no such neighbours — lands above it: over 405 folds the row-only threshold
    at the 0.95 percentile refused 94.7% of out-of-sample rows. A DI fitted without the
    exclusion is the defect, not a variant.

    **The subject is fabricated, never the contract.** One fold is trained through
    `research/training.py` on the constructed two-pair dataset, with a percentile this
    criterion owns (`DI_EXCLUSION_SUBJECT_PERCENTILE`), because
    `prediction.di_percentile` stays absent by ruling and this property does not depend on
    it. The artefact's `di.npz` is then read and **both distributions recomputed here** from
    its reference matrix and the timestamps in its identity, with the span read from config
    as `backtest.embargo_bars x timeframes.decision_bar_s`:

    * PASS needs the recorded distribution to equal the excluded recomputation, and the
      threshold its percentile;
    * and the row-only recomputation to differ materially on the same subject. Without
      that, a subject with no same-moment rows would let an implementation without the
      exclusion pass, and the proof would be empty.
    """
    np_mod, problem = try_import("numpy")
    if np_mod is None:
        return problem or pending("numpy is not installed")

    with tempfile.TemporaryDirectory(prefix="acsoe-verify-di-exclusion-") as raw_tmp:
        tmp = Path(raw_tmp)
        with root_import_path(ctx.root):
            trained, problem = _trained(
                ctx,
                tmp,
                max_folds=1,
                overrides={KEY_DI_PERCENTILE: DI_EXCLUSION_SUBJECT_PERCENTILE},
            )
            if trained is None:
                return problem or pending("acsoe.research.training does not exist yet")
            report, _dataset, engine_config = trained

            di_mod, problem = _phase5_module("acsoe.modelling.di")
            if di_mod is None:
                return problem or pending("acsoe.modelling.di does not exist yet")

            interval_s = int(engine_config.get(KEY_DECISION_BAR_S))
            embargo_bars = int(engine_config.get(KEY_EMBARGO_BARS))
            span_s = embargo_bars * interval_s
            if span_s <= 0:
                return failed(
                    f"`{KEY_EMBARGO_BARS}` x `{KEY_DECISION_BAR_S}` is {span_s} s. The DI's "
                    "exclusion span is that product, and a span that excludes nothing is "
                    "leave-one-out on the row alone."
                )

            fold_runs = list(getattr(report, "fold_runs", ()) or ())
            if not fold_runs:
                return failed("the training run reported no artefact run ids")
            models_dir = Path(str(getattr(report, "models_dir", tmp / "run" / "models")))
            run_dir = models_dir / fold_runs[0]
            di_path = run_dir / "di.npz"
            if not di_path.is_file():
                return failed(
                    "the fold trained at `prediction.di_percentile` = "
                    + str(DI_EXCLUSION_SUBJECT_PERCENTILE)
                    + " wrote no di.npz at "
                    + str(di_path)
                )
            try:
                fitted = di_mod.load(di_path)
            except ValueError as exc:
                return failed(
                    "the trainer's own di.npz was refused on load: " + str(exc)[:300]
                )
            manifest = json.loads((run_dir / "manifest.json").read_bytes().decode("utf-8"))

    recorded_span = getattr(fitted, "exclusion_s", None)
    if recorded_span is None:
        return failed(
            "the DI records no exclusion span, so its leave-one-out left out only the row "
            "itself. Its same-moment rows on every pair stayed in the reference set and the "
            "threshold measures time proximity rather than distributional distance."
        )
    if int(recorded_span) != span_s:
        return failed(
            f"the DI was fitted with an exclusion span of {int(recorded_span)} s against "
            f"{span_s} s from config ({embargo_bars} bars x {interval_s} s). A live "
            "candidate is at least the embargo after the reference window, and the "
            "leave-one-out excludes the same span; any other span puts the threshold where "
            "live scores do not land."
        )
    manifest_span = ((manifest.get("extras") or {}).get("di") or {}).get("exclusion_s")
    if manifest_span != span_s:
        return failed(
            f"the manifest's extras.di.exclusion_s is {manifest_span!r} against {span_s} s; "
            "the artefact's own record of the span must say what it was fitted with"
        )

    reference = np_mod.asarray(fitted.reference, dtype=np_mod.float64)
    identity = list(fitted.identity)
    try:
        stamps = np_mod.array(
            [int(entry.rsplit("|", 1)[1]) for entry in identity], dtype=np_mod.int64
        )
    except (IndexError, ValueError):
        return failed("di.npz identity entries are not `pair|decision_ts`")
    neighbours = int(fitted.neighbours)
    percentile = float(fitted.percentile)
    shared_bars = int((np_mod.unique(stamps, return_counts=True)[1] >= 2).sum())
    if shared_bars == 0:
        return failed(
            "no two reference rows share a bar, so the subject has no same-moment rows and "
            "cannot tell an exclusion across pairs from one within a pair; the constructed "
            "dataset must carry at least two pairs on the same bars"
        )

    excluded = _loo_distribution(
        np_mod, reference, stamps, neighbours=neighbours, span_s=span_s
    )
    row_only = _loo_distribution(np_mod, reference, stamps, neighbours=neighbours, span_s=None)
    recorded = np_mod.asarray(fitted.distribution, dtype=np_mod.float64)
    excluded_threshold = float(np_mod.quantile(excluded, percentile))
    row_only_threshold = float(np_mod.quantile(row_only, percentile))
    refused_by_row_only = float((excluded > row_only_threshold).mean())
    meant = 1.0 - percentile

    if refused_by_row_only < DI_EXCLUSION_MATERIAL_MULTIPLE * meant:
        return failed(
            f"on this subject the row-only threshold ({row_only_threshold:.4f}) would refuse "
            f"{refused_by_row_only:.1%} of the excluded distribution against the {meant:.0%} "
            "it is drawn to refuse, which is not a material difference: the subject cannot "
            "tell the exclusion from its absence, and a PASS here would prove nothing"
        )
    if recorded.shape != excluded.shape:
        return failed(
            f"di.npz records {recorded.shape[0]} distribution values for "
            f"{excluded.shape[0]} reference rows"
        )
    if np_mod.allclose(recorded, row_only, rtol=DI_EXCLUSION_TOLERANCE, atol=DI_EXCLUSION_TOLERANCE):
        return failed(
            "the DI's leave-one-out distribution is leave-one-out on the row alone: every "
            "reference row kept its same-moment rows on every pair, and its own adjacent "
            f"bars, as neighbours. Its threshold ({float(fitted.threshold):.4f}) measures "
            "time proximity rather than distributional distance; excluding every row within "
            f"{span_s} s puts it at {excluded_threshold:.4f}."
        )
    deviation = float(np_mod.max(np_mod.abs(recorded - excluded)))
    if not np_mod.allclose(
        recorded, excluded, rtol=DI_EXCLUSION_TOLERANCE, atol=DI_EXCLUSION_TOLERANCE
    ):
        return failed(
            f"the DI's leave-one-out distribution differs from the one recomputed here "
            f"with every row of any pair within {span_s} s left out, by up to "
            f"{deviation:.3g}. The exclusion is inclusive at the span and reaches across "
            "pairs; a narrower, exclusive or same-pair-only exclusion keeps same-moment "
            "neighbours and measures time proximity."
        )
    if not math.isclose(
        float(fitted.threshold), excluded_threshold, rel_tol=DI_EXCLUSION_TOLERANCE
    ):
        return failed(
            f"the DI's threshold {float(fitted.threshold)!r} is not the {percentile:g} "
            f"quantile of its excluded distribution, {excluded_threshold!r}"
        )

    # The boundary, which the trained subject cannot show: its nearest neighbours are never
    # exactly 48 bars away, so an exclusive span and an inclusive one record the same
    # distribution on it. Five rows on one axis instead, handed to the module's own `fit`
    # (the subject's input is fabricated, its contract is not): row 1 is nearest to row 0 in
    # space and exactly the span away in time, row 2 one second further at 0.5.
    boundary_rows = np_mod.array([[0.0], [0.001], [0.5], [1.0], [2.0]])
    boundary_ts = [0, span_s, span_s + 1, 5 * span_s, 6 * span_s]
    boundary = di_mod.fit(
        boundary_rows,
        [f"BOUNDARY|{stamp}" for stamp in boundary_ts],
        neighbours=1,
        percentile=0.5,
        decision_ts=boundary_ts,
        exclusion_s=span_s,
    )
    if not math.isclose(float(boundary.distribution[0]), 0.5, rel_tol=1e-9):
        return failed(
            f"a reference row exactly {span_s} s from the scored row was kept as its "
            f"neighbour (distance {float(boundary.distribution[0]):.4g}, where excluding it "
            "gives 0.5). The span is inclusive: a live candidate can sit exactly the embargo "
            "after the reference window, so the leave-one-out excludes that row too."
        )

    return passed(
        f"{reference.shape[0]} DI reference rows, {shared_bars} bars carrying more than one "
        f"pair; the recorded leave-one-out equals the one recomputed here with every row of "
        f"any pair within {span_s} s ({embargo_bars} bars x {interval_s} s, from config) "
        f"left out (max deviation {deviation:.1e}), threshold {excluded_threshold:.4f} at "
        f"the subject's percentile {percentile:g}. Leaving out the row alone would put the "
        f"threshold at {row_only_threshold:.4f} and refuse {refused_by_row_only:.1%} of the "
        f"excluded distribution against {meant:.0%}; a row exactly {span_s} s away is "
        "excluded"
    )


# --- skeptic_trains_only_on_predictor_buy_rows ----------------------------- #


def check_skeptic_trains_only_on_predictor_buy_rows(ctx: VerifyContext) -> Outcome:
    """Every skeptic training row is an out-of-sample BUY call from an earlier fold.

    Three ways to get this wrong and each is silent:

    * **a non-BUY row.** The skeptic grades the predictor's BUY calls. Trained on rows the
      predictor never called, it is a second predictor wearing a veto.
    * **an in-sample BUY call.** The predictor is right about its own training set far more
      often than it is right live, so a skeptic trained on those calls learns the
      predictor's overfit rather than its mistakes, and vetoes almost nothing.
    * **a call from fold `k` or later.** That is the test window it will be judged on.
    * **a row the purge or the embargo would have removed.** A label window reaching into
      the test window is the same leak whichever model reads the row, and it is worse here
      than in the predictor: the skeptic's out-of-sample numbers are what an operator
      would use to decide whether the veto is worth keeping.

    The identity is recomputed here from the out-of-sample file rather than read back from
    the artefact, ruling 7: the whole point is to check which rows the skeptic saw, and a
    number the skeptic reported about itself is not evidence of that. The **test window**
    is recomputed too, from `purged_walk_forward` over the same rows, so a trainer that
    misreported its own fold bounds cannot purge against them and agree with itself.

    Both counts go into the PASS line — the eligible set and the naive "all earlier BUY
    calls" set — because if the purge and embargo remove nothing on this dataset the two
    are identical and this criterion cannot tell a trainer that applies them from one that
    does not. `test_the_purge_and_embargo_remove_rows_rather_than_nothing` asserts the gap
    is real; the PASS line lets a reader see it.
    """
    with tempfile.TemporaryDirectory(prefix="acsoe-verify-skeptic-") as raw_tmp:
        tmp = Path(raw_tmp)
        with root_import_path(ctx.root):
            trained, problem = _trained(ctx, tmp, max_folds=3)
            if trained is None:
                return problem or pending("acsoe.research.training does not exist yet")
            report, dataset, engine_config = trained
            polars, problem = _polars()
            if polars is None:
                return problem or pending("polars is unavailable")

            entries, problem = _fold_entries(report)
            if entries is None:
                return problem or failed("the training run reported no folds")
            with_skeptic = [
                entry for entry in entries if entry.get("skeptic_rows") not in (None, 0)
            ]
            if not with_skeptic:
                return pending(
                    "no fold produced a skeptic over the constructed dataset. The first "
                    "folds have no earlier out-of-sample BUY calls to train on and "
                    "correctly produce none (spec 69), so this needs a run with enough "
                    "folds; the digest says `skeptic_rows: 0` for each, and engine 15 "
                    "blocks with `skeptic_unavailable` for a model version without one."
                )
            fold = with_skeptic[0]
            fold_index = int(fold["fold_index"])

            oos_path = Path(str(getattr(report, "oos_path", "")))
            if not oos_path.is_file():
                return failed("the run wrote no out-of-sample file")
            oos = polars.read_parquet(oos_path)
            absent = [column for column in OOS_COLUMNS if column not in oos.columns]
            if absent:
                return failed(
                    "the out-of-sample file is missing " + ", ".join(absent) + ". Specs "
                    "69, 74 and 75 read this file and nothing else."
                )

            interval_s = int(engine_config.get(KEY_DECISION_BAR_S))
            embargo_s = int(engine_config.get(KEY_EMBARGO_BARS)) * interval_s
            folds, problem = _fold_indices(dataset, engine_config, interval_s=interval_s)
            if folds is None:
                return problem or pending("the splitter could not be run")
            recomputed = [f for f in folds if int(f.fold_index) == fold_index]
            if not recomputed:
                return failed(
                    "the digest reports a fold "
                    + str(fold_index)
                    + " that `purged_walk_forward` does not produce over the same rows. The "
                    "criterion recomputes the test window rather than reading it back, "
                    "because a trainer that misreported its own window would otherwise agree "
                    "with itself."
                )
            test_start_ts = int(recomputed[0].test_start_ts)

            earlier_buys = oos.filter(
                polars.col("is_buy") & (polars.col("fold_index") < fold_index)
            )
            eligible = earlier_buys.filter(
                (polars.col("label_window_end_ts") < test_start_ts)
                & (polars.col("decision_ts") < test_start_ts - embargo_s)
            )
            expected = _identity_of(eligible, polars)
            naive = _identity_of(earlier_buys, polars)
            every_buy = _identity_of(oos.filter(polars.col("is_buy")), polars)
            non_buy = _identity_of(oos.filter(~polars.col("is_buy")), polars)

            artefacts, problem = _phase5_module("acsoe.modelling.artefacts")
            if artefacts is None:
                return problem or pending("acsoe.modelling.artefacts does not exist yet")
            recorded = fold.get("skeptic_training_identity")
            if not recorded:
                return failed(
                    "fold "
                    + str(fold_index)
                    + " trained a skeptic and recorded no `skeptic_training_identity`. "
                    "The identity is the only thing that says which rows it saw; a row "
                    "count passes whenever two sets happen to be the same size."
                )
            expected_digest = artefacts.identity_digest(
                [entry.split("|")[0] for entry in sorted(expected)],
                [int(entry.split("|")[1]) for entry in sorted(expected)],
            )

    if not expected:
        return failed(
            "fold "
            + str(fold_index)
            + " reports a skeptic but there are no out-of-sample BUY calls from earlier "
            "folds for it to have trained on"
        )
    if recorded != expected_digest:
        contaminating = sorted((every_buy | non_buy) - expected)[:3]
        return failed(
            "the skeptic's training identity for fold "
            + str(fold_index)
            + " does not match the out-of-sample BUY calls from folds strictly before it "
            "that survive this fold's purge and embargo. Recomputed over "
            + str(len(expected))
            + " eligible rows, from "
            + str(len(naive))
            + " earlier BUY calls before the purge; the artefact records a different set. "
            "Rows that would contaminate it look like "
            + repr(contaminating)
            + ": an in-sample BUY call teaches the predictor's overfit rather than its "
            "mistakes, a non-BUY row makes the skeptic a second predictor, a call from "
            "this fold or later is the window it is about to be judged on, and a row "
            "whose label window reaches into that window already knows how it ended."
        )

    return passed(
        "fold "
        + str(fold_index)
        + "'s skeptic trained on exactly the "
        + str(len(expected))
        + " out-of-sample BUY calls from earlier folds that survive its purge and embargo, "
        "by (pair, decision_ts) identity recomputed from the out-of-sample file against a "
        "test window recomputed from the splitter; the purge and embargo removed "
        + str(len(naive) - len(expected))
        + " of "
        + str(len(naive))
        + " earlier BUY calls, and "
        + str(len(non_buy))
        + " non-BUY rows and every in-sample call are outside that set"
    )


# --- walkforward_weekly_retrain_reports_oos -------------------------------- #


def check_walkforward_weekly_retrain_reports_oos(ctx: VerifyContext) -> Outcome:
    """A rolling weekly walk-forward, reported per fold, with the effective sample size.

    Two halves, because neither alone is enough and spec 60 was amended on 2026-09-13 to
    say so.

    **The fold machinery**, over a constructed series long enough to hold several weekly
    folds. Every fold must satisfy ``train_end_ts == test_start_ts`` — the past-only
    ruling, visible in the digest rather than only in the splitter's source — and every
    fold's effective sample size must be **below** its row count, because at a 48-bar
    horizon consecutive decision bars share almost all of their label window and an
    effective size equal to the row count means the weights were never computed.

    **The committed digest**, `tests/fixtures/walkforward_digest.json`, which spec 67's
    `--write-fixture` produces from a real run. That is the evidence that the full dataset
    was actually walked; re-running it is `--live`, and a criterion that re-ran twenty
    million rows inside the gate would make the gate unrunnable.
    """
    with tempfile.TemporaryDirectory(prefix="acsoe-verify-wf-") as raw_tmp:
        tmp = Path(raw_tmp)
        with root_import_path(ctx.root):
            trained, problem = _trained(ctx, tmp, max_folds=3)
            if trained is None:
                return problem or pending("acsoe.research.training does not exist yet")
            report, _dataset, engine_config = trained
            entries, problem = _fold_entries(report)
            if entries is None:
                return problem or failed("the training run reported no folds")
            retrain_days = int(engine_config.get("backtest.retrain_interval_days"))

    constructed, problem = _check_digest_entries(entries, retrain_days, "the constructed run")
    if problem is not None:
        return problem

    path = ctx.root / WALKFORWARD_DIGEST_FIXTURE
    if not path.is_file():
        return pending(
            WALKFORWARD_DIGEST_FIXTURE.as_posix()
            + " has not been deposited yet. It is the committed evidence that the full "
            "dataset was walked, written by `python -m acsoe.research.training "
            "--write-fixture` (spec 67 step 7); the fold machinery above is already "
            "proven over a constructed series."
        )
    try:
        payload = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return failed(WALKFORWARD_DIGEST_FIXTURE.as_posix() + " is not readable JSON: " + str(exc))
    committed = payload.get("folds") if isinstance(payload, Mapping) else None
    if not isinstance(committed, list) or not committed:
        return failed(
            WALKFORWARD_DIGEST_FIXTURE.as_posix()
            + " carries no `folds` list. The digest is one entry per fold; an aggregate "
            "alone hides exactly the fold whose 8,000 rows are 300 observations."
        )
    _entries, problem = _check_digest_entries(
        [dict(entry) for entry in committed], retrain_days, "the committed digest"
    )
    if problem is not None:
        return problem

    return passed(
        str(len(constructed))
        + " fold(s) over a constructed "
        + str(CONSTRUCTED_DAYS)
        + "-day dataset and "
        + str(len(committed))
        + " in "
        + WALKFORWARD_DIGEST_FIXTURE.as_posix()
        + ": every fold reports "
        + ", ".join(FOLD_DIGEST_FIELDS)
        + ", trains only up to its own test window (train_end_ts == test_start_ts), and "
        "reports an effective sample size below its row count"
    )


def _check_digest_entries(
    entries: Sequence[Mapping[str, Any]], retrain_days: int, where: str
) -> tuple[list[Mapping[str, Any]], Outcome | None]:
    """The per-fold assertions, applied to a constructed run and to the committed digest.

    One function rather than two copies: the committed digest is the same shape as the run
    that produced it, and a check that only ran over one of them would let the other carry
    a fold the machinery would have refused.
    """
    rows = list(entries)
    absent = [f for f in FOLD_DIGEST_FIELDS if any(f not in entry for entry in rows)]
    if absent:
        return rows, failed(where + " is missing " + ", ".join(absent) + " on some fold")
    for entry in rows:
        index = entry.get("fold_index")
        if int(entry["train_end_ts"]) != int(entry["test_start_ts"]):
            return rows, failed(
                where
                + ", fold "
                + str(index)
                + ": train_end_ts "
                + str(entry["train_end_ts"])
                + " is not test_start_ts "
                + str(entry["test_start_ts"])
                + ". A past-only walk-forward trains up to the moment its test window "
                "opens and no further; training on both sides is purged cross-validation, "
                "legitimate for choosing hyperparameters and not for answering 'would "
                "this have worked if I had been trading it'. Operator ruling 1 of "
                "2026-09-12."
            )
        span_days = (int(entry["test_end_ts"]) - int(entry["test_start_ts"])) / 86_400
        if abs(span_days - retrain_days) > 0.5:
            return rows, failed(
                where
                + ", fold "
                + str(index)
                + ": the test window is "
                + f"{span_days:.2f}"
                + " days against `backtest.retrain_interval_days` of "
                + str(retrain_days)
                + ". The model retrains at the cadence the live system retrains at, or "
                "the backtest is measuring a system nobody would run."
            )
        count = int(entry["rows"])
        effective = float(entry["effective_sample_size"])
        if count <= 0:
            continue
        if effective >= count:
            return rows, failed(
                where
                + ", fold "
                + str(index)
                + ": effective sample size "
                + f"{effective:.1f}"
                + " is not below its row count of "
                + str(count)
                + ". At a 48-bar horizon consecutive decision bars share almost all of "
                "their label window, so an effective size equal to the row count means "
                "the uniqueness weights were never computed and every metric from this "
                "fold describes a dataset far larger than the one that exists."
            )
        if FORBIDDEN_METRIC in entry:
            return rows, failed(
                where + ", fold " + str(index) + ": `" + FORBIDDEN_METRIC + "` is retired "
                "and computed nowhere (operator ruling 2026-09-12)"
            )
    return rows, None


# --- anomaly_and_skeptic_have_both_tests ----------------------------------- #


def check_anomaly_and_skeptic_have_both_tests(ctx: VerifyContext) -> Outcome:
    """Phase 5's two gates each have a test proving they block and one proving they pass.

    The shape of `phase_3_gates_have_both_tests`, asked of engines 13 and 15. A gate with
    only a happy path is incomplete; a gate with only block cases is one that refuses
    everything and proves nothing. It reads the assertions rather than the test names, and
    it is a completeness check rather than a correctness one — whether those tests pass is
    `toolchain_green`'s question and that runs in every phase.
    """
    findings: list[str] = []
    absent: list[str] = []
    for engine in sorted(PHASE5_GATE_TEST_FILES):
        number, spec = PHASE5_ENGINES[engine]
        relative = PHASE5_GATE_TEST_FILES[engine]
        path = ctx.root / Path(relative)
        if not path.is_file():
            absent.append(f"engine {number} `{engine}` ({relative}, {spec})")
            continue
        blocking, passing, problem = _test_directions(path)
        if problem:
            return failed(problem)
        if not blocking or not passing:
            missing = "no test asserting it blocks" if not blocking else "no test asserting it passes"
            return failed(
                f"engine {number} `{engine}` has {missing} in {relative} "
                f"({blocking} block, {passing} pass). code-standards.md: every gate needs "
                "at least one test proving it blocks and one proving it passes."
            )
        findings.append(f"{engine} {blocking}/{passing}")

    if absent:
        return pending(
            "no test file yet for " + "; ".join(absent) + ". Each agent owns the tests "
            "mirroring its own source, so this criterion reads them and never writes one."
        )
    return passed(
        "both Phase 5 gates have a test asserting they block and one asserting they pass "
        "(block/pass per engine: " + ", ".join(findings) + ")"
    )


# --- scout_ranks_by_feature_not_arrival ------------------------------------ #


def check_scout_ranks_by_feature_not_arrival(ctx: VerifyContext) -> Outcome:
    """`rank_universe` is called **directly**, on input where arrival order is wrong.

    The seam the tracker named before Phase 5 opened. Engine 7 builds its scan set with
    `sorted`, so `rank_universe` is always handed an already-ordered sequence, and **a
    ranking that merely preserved arrival order would still answer alphabetically end to
    end**. Only a direct call on input where arrival order and intended order disagree on
    every element separates "orders by the feature" from "returns what it was given", and
    no end-to-end fixture can see the difference.

    The signature is read from `engines/scout/contracts.py` and not agreed by message. A
    criterion written against a keyword the module never grew raises `TypeError` — and the
    version that does *not* raise is worse, because it means the criterion reached a
    double instead of the real function. That is the Phase 4 labeller failure exactly: a
    signature agreed by message, a module that landed under another name, and nothing red.
    """
    with root_import_path(ctx.root):
        module, problem = try_import("acsoe.engines.scout.contracts")
        if module is None:
            return problem or pending("engine 7 `scout` does not exist yet")
        rank, missing = module_attr(module, "rank_universe")
        if rank is None:
            return pending(missing + " (spec 76, B-2)")

        # Arrival order and intended order disagree on EVERY element: the alphabetically
        # first pair has the highest value, the last has the lowest, and the sequence is
        # handed over already sorted - which is what engine 7 does.
        pairs = ("AAAUSD", "BBBUSD", "CCCUSD", "DDDUSD")
        values = {"AAAUSD": 9.0, "BBBUSD": 7.0, "CCCUSD": 3.0, "DDDUSD": 1.0}
        features = {pair: {"probe_feature": value} for pair, value in values.items()}
        try:
            descending = rank(
                pairs, features=features, feature="probe_feature", descending=True
            )
            ascending = rank(
                pairs, features=features, feature="probe_feature", descending=False
            )
            unconfigured = rank(pairs, features=features, feature=None)
            with_a_gap = rank(
                ("AAAUSD", "BBBUSD", "ZZZUSD"),
                features={"AAAUSD": {"probe_feature": 1.0}, "BBBUSD": {"probe_feature": 5.0}},
                feature="probe_feature",
                descending=True,
            )
        except TypeError as exc:
            return failed(
                "acsoe.engines.scout.contracts.rank_universe does not accept "
                "`rank_universe(pairs, *, features, feature, descending)`, which is spec "
                "76's own wording: "
                + str(exc)[:200]
                + ". The criterion calls the real function on purpose; catching this and "
                "reporting PENDING would be a criterion that never reaches what it judges."
            )

    if tuple(descending) != ("AAAUSD", "BBBUSD", "CCCUSD", "DDDUSD"):
        return failed(
            "ranking descending by the feature returned "
            + repr(tuple(descending))
            + "; the highest value is AAAUSD and the lowest DDDUSD"
        )
    if tuple(ascending) != ("DDDUSD", "CCCUSD", "BBBUSD", "AAAUSD"):
        return failed(
            "ranking ascending returned "
            + repr(tuple(ascending))
            + ", which is not the reverse of the descending order. **This is the case the "
            "criterion exists for**: the descending answer happens to equal alphabetical "
            "order, so a ranking that simply returned its input would satisfy it. The "
            "ascending call is where arrival order and intended order disagree on every "
            "element."
        )
    if tuple(unconfigured) != tuple(sorted(pairs)):
        return failed(
            "with no ranking feature configured the order was "
            + repr(tuple(unconfigured))
            + "; it must be alphabetical. `scout.rank_feature` is absent until the "
            "operator rules on spec 75's study, and equal treatment of every pair is how "
            "that absence is spelled."
        )
    if tuple(with_a_gap) != ("BBBUSD", "AAAUSD", "ZZZUSD"):
        return failed(
            "a pair with no value for the ranking feature came back as "
            + repr(tuple(with_a_gap))
            + "; it sorts after every pair that has one and is **never dropped**. A "
            "dropped pair is one engine 7 silently never considered, and engine 5 "
            "publishes a null feature rather than omitting the pair precisely so that "
            "cannot happen."
        )

    config_map, problem = load_config(ctx.root)
    if config_map is None:
        return problem or pending("config/default.yaml could not be read")
    configured = config_get(config_map, KEY_RANK_FEATURE)
    if configured is not _CONFIG_MISSING and configured is not None:
        return failed(
            "`"
            + KEY_RANK_FEATURE
            + "` is set to "
            + repr(configured)
            + " in config/default.yaml. It is the operator's, after spec 75's ranking "
            "study reports (ruling 7 of spec 59); until then the ordering is alphabetical "
            "and the engine publishes `rank_feature: null`."
        )

    return passed(
        "rank_universe called directly on four pairs whose feature order is the exact "
        "reverse of their arrival order: descending and ascending both follow the "
        "feature, a pair with no value sorts last and is not dropped, and with "
        "`scout.rank_feature` still absent the order is alphabetical"
    )


# --- tournament_writes_leaderboard_from_oos -------------------------------- #


def check_tournament_writes_leaderboard_from_oos(ctx: VerifyContext) -> Outcome:
    """Engine 20 writes one leaderboard row per model version, scored from the OOS rows.

    Phase 6's router weights by this table and Phase 7's promotion gate judges it, so a
    leaderboard whose numbers are wrong is two later phases reasoning from them. Five claims:

    * **every number on a row is the out-of-sample rows' number.** `n_trades`, `win_rate`,
      `net_pnl` and `brier` are checked against arithmetic this criterion does itself, over
      rows it selects by each fold's **half-open** test window `[test_start_ts,
      test_end_ts)`, never by the engine's route. The fixture puts fold 1's first row exactly
      on fold 0's `test_end_ts`, and that row is a BUY that hit its target, so a scorer that
      drew the window inclusive at the end, counted every row as a trade, or took its Brier
      from anywhere but these probabilities, writes a different number on the row;
    * **no row for an empty fold.** The fixture's third fold is the trainer's empty-fold entry;
      it trained no model, and a row for it would name a version with nothing behind it;
    * **a digest that disagrees with its rows writes nothing.** The same rows under a digest
      whose Brier for one fold is wrong must leave the table untouched: two numbers for one
      fold means one file describes rows the other did not score;
    * **`promoted` is never true**, and a second run over the same digest writes nothing;
    * **written through `StoreClient`.** An engine reaching past it with its own `sqlite3`
      connection is contract rule 4 and is checked on the source, because the row looks
      identical either way.

    The digest and out-of-sample file are constructed here rather than trained, and that is
    safe for one reason worth stating: their **shapes** are pinned by
    `walkforward_weekly_retrain_reports_oos` and
    `skeptic_trains_only_on_predictor_buy_rows`, which read the real producer's output
    against `FOLD_DIGEST_FIELDS` and `OOS_COLUMNS`. Without those two this would be a
    criterion agreeing with its own fabrication.
    """
    polars, problem = _polars()
    if polars is None:
        return problem or pending("polars is unavailable")

    week = 604_800
    base = 1_700_000_000
    versions = ("train-verify-f0", "train-verify-f1")
    # (label, is_buy, p_target) per row, per trained fold. The probabilities differ between
    # rows and between folds, so a Brier computed over the wrong rows is a different number.
    # **Each fold's third row is a target the predictor did not call BUY**: without one, a win
    # rate counted over every row equals the win rate over the BUY calls and the check below
    # cannot tell them apart. That survived a mutation sweep once, on a fixture without it.
    fold_rows = (
        (("target", True, 0.7), ("stop", True, 0.2), ("target", False, 0.4)),
        (("target", True, 0.9), ("stop", True, 0.3), ("target", False, 0.2)),
    )
    returns = {"target": 0.03, "stop": -0.015, "timeout": 0.004}

    def oos_rows(run_folds: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index in range(run_folds):
            for position, (label, is_buy, p_target) in enumerate(fold_rows[index]):
                rows.append(
                    {
                        "pair": "AAAUSD" if position % 2 == 0 else "BBBUSD",
                        # Fold 1's row 0 lands exactly on fold 0's `test_end_ts`.
                        "decision_ts": base + index * week + position * 900,
                        "label_window_end_ts": base + index * week + position * 900 + 43_200,
                        "fold_index": index,
                        "p_target": p_target,
                        "p_stop": round(1.0 - p_target - 0.05, 6),
                        "p_timeout": 0.05,
                        "expected_move_pct": 0.004 if is_buy else -0.004,
                        "is_buy": is_buy,
                        "di": None,
                        "di_refused": False,
                        "label": label,
                        "return_pct": returns[label],
                        "weight": 0.5,
                    }
                )
        return rows

    rows_in = oos_rows(len(versions))

    def windowed(start: int, end: int) -> list[dict[str, Any]]:
        return [row for row in rows_in if start <= int(row["decision_ts"]) < end]

    # What each row must say, from the half-open windows and this criterion's own arithmetic.
    expected: dict[str, dict[str, Any]] = {}
    folds: list[dict[str, Any]] = []
    for index, version in enumerate(versions):
        start, end = base + index * week, base + (index + 1) * week
        window = windowed(start, end)
        buys = [row for row in window if row["is_buy"]]
        hits = [1.0 if row["label"] == "target" else 0.0 for row in window]
        brier = math.fsum(
            (float(row["p_target"]) - hit) ** 2 for row, hit in zip(window, hits, strict=True)
        ) / len(window)
        rate = math.fsum(hits) / len(window)
        expected[version] = {
            "fold": str(index),
            "n_trades": len(buys),
            "win_rate": sum(1 for row in buys if row["label"] == "target") / len(buys),
            "net_pnl": sum((Decimal(repr(row["return_pct"])) for row in buys), Decimal(0)),
            "brier": brier,
        }
        folds.append(
            {
                "fold_index": index,
                "run_id": version,
                "train_start_ts": start - 90 * 86_400,
                "train_end_ts": start,
                "test_start_ts": start,
                "test_end_ts": end,
                "rows": len(window),
                "effective_sample_size": 1.5,
                "brier": brier,
                "base_rate_brier": rate * (1.0 - rate),
                "log_loss": 0.9,
                "buy_count": len(buys),
                "buy_target_rate": expected[version]["win_rate"],
                "is_empty": False,
            }
        )
    # The trainer's own empty-fold entry (`_empty_entry`): no model, no run id, no metrics.
    empty_index = len(versions)
    folds.append(
        {
            "fold_index": empty_index,
            "run_id": None,
            "train_start_ts": base + empty_index * week - 90 * 86_400,
            "train_end_ts": base + empty_index * week,
            "test_start_ts": base + empty_index * week,
            "test_end_ts": base + (empty_index + 1) * week,
            "rows": 0,
            "effective_sample_size": 0.0,
            "brier": None,
            "base_rate_brier": None,
            "buy_count": 0,
            "is_empty": True,
        }
    )

    with root_import_path(ctx.root):
        engine_cls, problem = _phase5_engine_class("tournament")
        if engine_cls is None:
            return problem or _phase5_engine_absent("tournament")

        with tempfile.TemporaryDirectory(prefix="acsoe-verify-tournament-") as raw_tmp:
            tmp = Path(raw_tmp)

            def deposit(directory: Path, run_id: str, run_folds: list[dict[str, Any]]) -> Path:
                # **Named the way the trainer names them**, the out-of-sample file beside
                # the digest and carrying its run id, because engine 20 derives one path
                # from the other. A fixture spelled differently would test a layout nothing
                # produces, and the engine would correctly refuse it.
                directory.mkdir(parents=True, exist_ok=True)
                digest_path = directory / "walkforward_digest.json"
                digest_path.write_bytes(
                    json.dumps(
                        {
                            "run_id": run_id,
                            "created_at": "2026-09-13T12:00:00+00:00",
                            "folds": run_folds,
                        },
                        sort_keys=True,
                        indent=2,
                    ).encode("utf-8")
                    + b"\n"
                )
                polars.DataFrame(rows_in).write_parquet(directory / f"oos_{run_id}.parquet")
                return digest_path

            digest_path = deposit(tmp / "run", "train-verify", folds)
            # The same rows under a digest whose Brier for the **last** trained fold is off
            # by a hundredth, so an engine that wrote fold by fold would already have
            # written fold 0 when it met the disagreement.
            tampered = [dict(entry) for entry in folds]
            tampered[1] = {
                **tampered[1],
                "run_id": "train-tampered-f1",
                "brier": float(tampered[1]["brier"]) + 0.01,
            }
            tampered[0] = {**tampered[0], "run_id": "train-tampered-f0"}
            tampered_path = deposit(tmp / "tampered", "train-tampered", tampered)

            store_cls, problem = _store_class()
            if store_cls is None:
                return problem or pending("clients.store.client.StoreClient does not exist yet")
            db_path, _store_mod, problem = _migrated_db(tmp, "tournament.sqlite")
            if db_path is None:
                return problem or pending("the store could not be migrated")

            store = store_cls(db_path, models_dir=tmp / "models")
            clients, problem = _fake_clients(store=store)
            if clients is None:
                return problem or pending("the shared test doubles are unavailable")
            engine_config, problem = _phase3_config()
            if engine_config is None:
                return problem or pending("the committed config could not be loaded")
            context, problem = _engine_context(
                engine_config, clients, run_id="verify-phase-5", now=PHASE5_NOW
            )
            if context is None:
                return problem or pending("acsoe.core.contracts does not exist yet")

            try:
                engine = engine_cls(digest_path=digest_path)
                tampered_engine = engine_cls(digest_path=tampered_path)
            except TypeError as exc:
                return failed(
                    "TournamentEngine does not accept `TournamentEngine(*, "
                    "digest_path=...)`, which is the seam `cli/research.py` constructs it "
                    "through: " + str(exc)[:200]
                )
            try:
                # **Read between the runs, not after all of them.** An earlier version took
                # both counts after the engine had run twice, so they were two reads of one
                # moment and the idempotence check could not fail — which is what a first
                # FAIL observation is for finding.
                first = engine.process(context, {})
                rows = _leaderboard_rows(db_path)
                again = engine.process(context, {})
                after_second = _leaderboard_rows(db_path)
                refused = tampered_engine.process(context, {})
                after_tampered = _leaderboard_rows(db_path)
            finally:
                # The store holds an open connection to a database inside the temporary
                # directory, and on Windows that stops the directory being removed.
                closer = getattr(store, "close", None)
                if callable(closer):
                    closer()
            source = (
                ctx.root / "src" / "acsoe" / "engines" / "tournament" / "engine.py"
            )
            direct = (
                [
                    line.strip()
                    for line in source.read_text(encoding="utf-8").splitlines()
                    if "sqlite3" in line or "INSERT INTO" in line.upper()
                ]
                if source.is_file()
                else []
            )

    if direct:
        return failed(
            "engines/tournament/engine.py reaches SQLite directly: "
            + "; ".join(direct[:3])
            + ". Contract rule 4 — an engine never touches the filesystem or the database "
            "except through `context.clients.store`, and the row it writes looks identical "
            "either way, so nothing but this would notice."
        )
    if str(getattr(first, "status", "")) != "OK":
        return failed(
            "engine 20 did not score a digest and out-of-sample file that agree: "
            + str(getattr(first, "status", None))
            + " - "
            + str(getattr(first, "reason", ""))[:300]
        )
    if len(rows) != len(versions):
        return failed(
            "engine 20 wrote "
            + str(len(rows))
            + " leaderboard rows for a digest carrying "
            + str(len(versions))
            + " trained model versions and one empty fold. One row per trained version is "
            "what Phase 6's router weights by; an empty fold trained no model and gets none."
        )
    by_version = {str(row.get("model_version")): row for row in rows}
    if set(by_version) != set(versions):
        return failed(
            "leaderboard versions are "
            + ", ".join(sorted(by_version))
            + ", expected "
            + ", ".join(versions)
            + ". The version is each fold's own artefact run id, never one invented for it."
        )
    wrong: list[str] = []
    for version, want in expected.items():
        row = by_version[version]
        if str(row.get("fold")) != want["fold"]:
            wrong.append(f"{version} fold {row.get('fold')} (expected {want['fold']})")
        if row.get("n_trades") != want["n_trades"]:
            wrong.append(f"{version} n_trades {row.get('n_trades')} (expected {want['n_trades']})")
        win_rate = row.get("win_rate")
        if win_rate is None or abs(float(win_rate) - want["win_rate"]) > 1e-12:
            wrong.append(f"{version} win_rate {win_rate} (expected {want['win_rate']})")
        try:
            net_pnl = Decimal(str(row.get("net_pnl")))
        except InvalidOperation:
            net_pnl = None
        if net_pnl != want["net_pnl"]:
            wrong.append(f"{version} net_pnl {row.get('net_pnl')} (expected {want['net_pnl']})")
        row_brier = row.get("brier")
        if row_brier is None or abs(float(row_brier) - want["brier"]) > 1e-9:
            wrong.append(f"{version} brier {row_brier} (expected {want['brier']!r})")
    if wrong:
        return failed(
            "leaderboard numbers are not the out-of-sample rows' numbers, counted over each "
            "fold's half-open test window: "
            + "; ".join(wrong)
            + ". A scorer that drew a fold boundary one bar wide, counted non-BUY rows, or "
            "took its Brier from anywhere but these probabilities writes exactly this."
        )
    promoted = [row for row in rows if row.get("promoted")]
    if promoted:
        return failed(
            str(len(promoted))
            + " leaderboard row(s) are marked promoted. Promotion is Phase 7's, behind a "
            "deflated metric and a multiple-testing haircut; a promoted row written now "
            "would be read by that gate as a decision somebody made."
        )
    if len(after_second) != len(rows):
        return failed(
            "a second run over the same digest wrote "
            + str(len(after_second) - len(rows))
            + " more rows. Engine 20 is idempotent on (model_id, model_version, fold): "
            "`acsoe research` replays the whole chain on every invocation, so a "
            "non-idempotent write doubles the leaderboard every time anybody runs it."
        )
    del again
    if len(after_tampered) != len(after_second) or str(getattr(refused, "status", "")) != (
        "BLOCK"
    ):
        return failed(
            "a digest whose Brier for one fold disagrees with that fold's out-of-sample rows "
            "was scored anyway: "
            + str(len(after_tampered) - len(after_second))
            + " row(s) written, status "
            + str(getattr(refused, "status", None))
            + ". The two files are one run's output, and when they disagree one of them "
            "describes rows the other did not score; nothing may be written from either."
        )

    return passed(
        str(len(rows))
        + " leaderboard rows written through the real StoreClient, one per trained model "
        "version and none for the empty fold, with n_trades, win_rate, net_pnl and brier "
        "equal to the out-of-sample rows counted over each fold's half-open window and "
        "promoted false on every one; a second run wrote none, and a digest that "
        "disagreed with its rows wrote nothing"
    )


def _leaderboard_rows(db_path: Path) -> list[dict[str, Any]]:
    """Every leaderboard row, read with sqlite3 rather than through the store.

    Deliberately not through `StoreClient.leaderboard()`, which the console uses and which
    returns the newest fifty: a criterion counting rows through a limited read cannot tell
    "engine 20 wrote two" from "engine 20 wrote two hundred and this read showed fifty".
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("SELECT * FROM leaderboard")
        except sqlite3.Error:
            return []
        return [dict(row) for row in cursor.fetchall()]
    finally:
        # **Closed, not left to `with`.** `sqlite3`'s context manager commits or rolls back
        # a transaction; it does not close the connection. On Windows an open handle stops
        # `TemporaryDirectory` deleting the file, and the criterion then reports "raised -
        # PermissionError" long after it had already answered its own question.
        conn.close()



# --------------------------------------------------------------------------- #
# Phase 6 - decision and execution. Spec 100.
# --------------------------------------------------------------------------- #
#
# Nine criteria, and on the tree they were written against **every one of them is
# PENDING**. Engines 16, 18 and 22 are unbuilt, engines 9 and 14 are unbuilt, and
# both committed fixtures are uncut. That is the point of writing them first: a
# criterion exists so it can report PENDING, and PENDING is what stops a phase with
# nothing in it looking finished. Spec 00 was first in Phase 0, spec 16 in Phase 1,
# spec 45 in Phase 3, spec 48 in Phase 4 and spec 60 in Phase 5 for the same reason.
#
# **Phase 6 fails expensively.** Every phase before this one could fail on paper.
# Here the manage chain holds real positions and the failure modes cost money rather
# than a metric: an entry that fills and is never recorded, a stop that is computed
# from data the guard already rejected, a liquidation that stalls because a balance
# fetch failed during the outage that triggered it. Each criterion below is therefore
# written against a **named wrong implementation** - the hold removed from engine 21,
# the liquidation reading fresh balances only, engine 9 walking the ask - rather than
# against the shape of the evidence.
#
# Three rules govern all nine, and the first is this phase's own.
#
# * **Everything that drives a trade runs at fee tier 3, and says so in its own
#   message.** Ruling 8 of the Phase 6 task list. At *Kraken's reference* tier 1
#   (invariant 5) the cost gate is unreachable: `hurdle_multiple` 1.5 makes the bar 2.5x
#   friction, reference tier-1 friction is about 1.25%, and 3.125% is above the 3.0%
#   target. **That is not true of the fake exchange's tier 1**, which these criteria
#   could run at: measured 2026-09-18, it clears (friction 0.708%, hurdle 1.062%). The
#   tier is named because the regime is part of what a verdict proves, and since operator
#   ruling S3 each message states the friction and hurdle engine 10 computed in its own
#   run (`_run_regime`), never a quoted figure. A verdict that does not name its fee
#   regime claims more than it proves. `hurdle_multiple` is not changed and the cost gate is not
#   weakened; the tier is what moves, and it moves through the **named** profile in
#   `tests/fixtures/kraken/fee_tiers.json` so two criteria cannot mean two different
#   things by "tier 3".
# * **No criterion reads `data/`, `models/` or `logs/`.** All three are gitignored,
#   so a criterion depending on one passes only on the machine that produced it.
#   Everything here reads a committed fixture under `tests/fixtures/` or fabricates
#   its subject into a temporary directory.
# * **Fabricate the subject, never the contract.** The prices, the book and the
#   scripted ticks are this file's. Every engine, every `contracts.py` and the config
#   model are the real ones. If a real BUY cannot be produced honestly at tier 3,
#   that is a finding for the lead and not something to route around with a
#   hand-built `state` - spec 100 says so in as many words, and Phase 4 found twice in
#   one day that a hand-built payload agrees with whoever built it.

#: Engine number and owning spec for every subject these criteria drive, so a PENDING
#: line names who owes it rather than making the reader come and find this file.
PHASE6_ENGINES: Final[dict[str, tuple[int, str]]] = {
    "order_book": (9, "C, spec 96"),
    "adaptive_router": (14, "C, spec 97"),
    "decision": (16, "B, spec 90"),
    "execution": (18, "B, spec 91"),
    "memory": (19, "C, spec 98"),
    "position_manager": (21, "B, spec 92"),
    "exit": (22, "B, spec 93"),
}

#: The two committed fixtures Phase 6 adds, and who cuts each. `data/db/` is
#: gitignored and `data/historical/` is not in the repository, so a criterion that
#: wanted a real book or a real leaderboard row has to read a committed sample or it
#: cannot run on a fresh clone at all.
PHASE6_FIXTURES: Final[dict[str, str]] = {
    "book_sample.jsonl": (
        "cut from the live archive by A's scripts/cut_book_fixture.py (spec 86) and "
        "deposited by C (spec 96); must carry a thin book and a deep one"
    ),
    "leaderboard_sample.json": (
        "written by C (spec 97); at least two models, because a router cannot be shown "
        "to move weight between one"
    ),
}

#: What the trade-driving criteria expect of the chain once B has built it. A
#: proposal to the owning agent, not a decree, and messaged to B when these were
#: registered - the same arrangement as `CONSOLE_CONTRACT` in Phase 1 and the Phase 2
#: data-spine contracts.
TRADE_CHAIN_CONTRACT: Final = (
    "expected, and fixed by context/engine-contracts.md rather than by this file: "
    "engine 16 `decision` a gate publishing one typed order intent, absent on every "
    "block; engine 18 `execution` placing one post-only entry per intent and never a "
    "market order; engine 21 `position_manager` publishing entry_orders_cancelled and "
    "hold_reason; engine 22 `exit` publishing positions_closed; engine 19 `memory` "
    "recording what 18 and 22 publish. Driven through the real Orchestrator at fee "
    "tier 3 against B's paper broker"
)

#: The paper broker is a client, not an engine, so it is looked up separately.
PAPER_BROKER_CONTRACT: Final = (
    "expected acsoe.clients.paper exposing the broker that implements A's "
    "OrderClientProtocol and wraps clients.kraken in paper mode (B, spec 88)"
)


def _tier_sentence(tier: int) -> tuple[str | None, Outcome | None]:
    """The fee-regime clause every trade-driving criterion puts in its own message.

    Read out of the harness rather than spelled here, so the sentence a criterion
    reports and the profile it applied come from one file. A criterion that named a
    tier it had not applied would be the exact wrong claim ruling 8 exists to stop.

    Called **inside** `root_import_path`, like every other import in this section.
    """
    module, problem = try_import("tests.harness.fake_kraken")
    if module is None:
        return None, problem or pending("tests.harness.fake_kraken is unavailable")
    sentence, missing = module_attr(module, "tier_sentence")
    if sentence is None:
        return None, pending("the harness has no named fee tiers yet: " + missing)
    return str(sentence(tier)), None


def _phase6_engine_class(engine: str) -> tuple[Any, Outcome | None]:
    """The engine class, or the PENDING naming its number and the spec that owes it.

    **A module that imports and declares no engine gets its own sentence.** "Does not
    exist yet" would send somebody to write a file that is already there, and a
    half-built engine is what an interrupted session leaves behind - Phase 6 opened on
    exactly that in another lane, with `modelling/di.py` naming `score_many` in
    `__all__` and not defining it.
    """
    number, spec = PHASE6_ENGINES[engine]
    module, problem = try_import(f"acsoe.engines.{engine}.engine")
    if module is None:
        if problem is not None and problem.result is Result.FAIL:
            return None, problem
        return None, pending(f"engine {number} `{engine}` does not exist yet ({spec})")
    for attr in dir(module):
        candidate = getattr(module, attr)
        if (
            isinstance(candidate, type)
            and getattr(candidate, "name", None) == engine
            and getattr(candidate, "number", None) == number
        ):
            return candidate, None
    return None, pending(
        f"acsoe.engines.{engine}.engine exists but declares no class with "
        f"`name = {engine!r}` and `number = {number}` ({spec})"
    )


def _phase6_engines(*engines: str) -> Outcome | None:
    """`None` when every named engine exists, else the first PENDING.

    Reported one at a time and in the order given, because "engines 16, 18 and 22 are
    missing" is a less useful line than the name of the one to build next.
    """
    for engine in engines:
        cls, problem = _phase6_engine_class(engine)
        if cls is None:
            return problem
    return None


def _phase6_fixture(ctx: VerifyContext, name: str) -> Outcome | None:
    """`None` when the committed fixture is there and carries something.

    **Absent is PENDING and empty is FAIL**, and the difference matters. Absent means
    nobody has cut it yet, which is a schedule fact. Empty means somebody deposited a
    file that carries nothing, and a walk over no levels or a leaderboard with no
    models is the vacuous pass this project has been burned by three times.
    """
    path = ctx.root / "tests" / "fixtures" / name
    if not path.is_file():
        return pending(
            f"tests/fixtures/{name} has not been deposited yet - " + PHASE6_FIXTURES[name]
        )
    if path.stat().st_size == 0:
        return failed(f"tests/fixtures/{name} is empty, so it proves nothing")
    return None


def _paper_broker_module() -> Outcome | None:
    """`None` when B's paper broker exists, else the PENDING naming spec 88.

    Looked up as a **client** and not as an engine, which is the operator's corrected
    ruling of 2026-09-16: a resting post-only entry fills on a later tick that only
    engine 21 sees and exits fill in engine 22, so under `engines/execution/` two
    engines forbidden by contract rule 3 from importing it would each need their own
    copy of one fill rule.
    """
    module, problem = try_import("acsoe.clients.paper")
    if module is None:
        return _with_contract(
            problem, "acsoe.clients.paper does not exist yet (B, spec 88)", PAPER_BROKER_CONTRACT
        )
    return None


def _trade_chain_subject() -> Outcome | None:
    """`None` when a round trip could be driven, else the PENDING naming what is missing.

    Spec 100 step 2. The subject is a fabricated market in a temporary directory -
    candles with a planted pattern that precedes target touches, trained through the
    real `research/training.py` into a real `models/<run_id>/` - driven through the
    real orchestrator, the real chains, a real `StoreClient`, the fake Kraken client at
    tier 3 and B's paper broker.

    **Everything in that sentence except the prices is the real thing.** The one
    licence spec 100 grants is over the *subject*: what the market did. It grants none
    over the *contract*: every engine, every `contracts.py` and the config model are
    the committed ones, and a candidate that will not clear the gates honestly is a
    finding for the lead rather than something to arrange around.

    It reports PENDING, never FAIL, while any part of the chain is unbuilt, and it
    names the next thing to build rather than the whole list.
    """
    problem = _phase6_engines("decision", "execution", "position_manager", "exit", "memory")
    if problem is not None:
        return problem
    problem = _paper_broker_module()
    if problem is not None:
        return problem
    return pending(
        "every engine and the paper broker exist; the trade-producing subject of spec "
        "100 step 2 is not written yet (C, spec 100) - " + TRADE_CHAIN_CONTRACT
    )


def _awaiting(problem: Outcome | None, tier: str, leg: str = "") -> Outcome:
    """One PENDING that names both the missing subject and the regime it will run in.

    A FAIL is passed through unchanged: a broken environment is a broken environment
    and the fee regime is beside the point. That is the same rule `_with_contract`
    follows, for the same reason.
    """
    assert problem is not None, "the caller must have something to report"
    if problem.result is Result.FAIL:
        return problem
    where = f"the {leg} leg will then run " if leg else "will run "
    return pending(problem.message + "; " + where + tier)


# --- what engine 10 computed in this criterion's run: operator ruling S3 --- #
#
# Every trade-driving criterion used to end its message with a fixed quotation of invariant
# 5's reference figures ("reference friction about 0.65% ... a hurdle of 1.625%; tier 1 is a
# no-trade regime"). Its run was at the fake exchange's invented tier-3 rates, where engine
# 10 computed friction 0.308% and a hurdle of 0.462% - so every PASS appended numbers its
# run did not use. Ruled 2026-09-18: a message states the figures its own run computed.
#
# Collected, not recomputed: every tick a criterion drives passes its finished `state`
# through `_note_engine10`, which keeps what engine 1 and engine 10 **published** - never
# a figure this file derives - and the message reports those. A criterion whose drives
# never reached engine 10 says so rather than inventing a regime.

#: The engine 10 verdicts the current criterion's drives saw, first-seen order, no
#: repeats: `(pair, maker, taker, friction, hurdle)`, each exactly as published. Reset
#: by `_regime_begin` at the start of every criterion that drives the chain.
_ENGINE10_SEEN: list[tuple[str, str, str, str, str]] = []

#: Kraken's own reference schedule, **quoted from invariant 5 and never computed here**:
#: that invariant gives its reference figures "for sanity-checking only - never for use
#: in code", so the sentence is prose. It is true only while `trading.hurdle_multiple` and
#: `barriers.target_pct` keep the quoted bar above the target;
#: `tests/verify/test_phase6_criteria.py` holds that relationship against the committed
#: config and fires if either moves, the same tripwire shape as spec 112.
KRAKEN_REFERENCE_TIER_1: Final = (
    "Kraken's own schedule is a separate question, quoted from invariant 5 rather than "
    "measured here: at its reference tier-1 fees (friction about 1.25% round trip) a "
    "candidate needs an expected move above 3.125% against the 3.0% target, so Kraken's "
    "tier 1 is a no-trade regime at the current barriers"
)


def _regime_begin() -> None:
    """Forget the previous criterion's engine 10 verdicts."""
    _ENGINE10_SEEN.clear()


def _note_engine10(state: Mapping[str, Any]) -> None:
    """Keep what engine 1 and engine 10 published on this tick, if engine 10 ran."""
    cost = state.get("cost")
    if not isinstance(cost, Mapping) or cost.get("friction_pct") is None:
        return
    fee_tier = (state.get("exchange") or {}).get("fee_tier") or {}
    row = (
        str(cost.get("pair")),
        str(fee_tier.get("maker_fee_pct")),
        str(fee_tier.get("taker_fee_pct")),
        str(cost.get("friction_pct")),
        str(cost.get("hurdle_pct")),
    )
    if row not in _ENGINE10_SEEN:
        _ENGINE10_SEEN.append(row)


def _pct(value: str) -> str:
    """An exact decimal fraction as a percentage, to three places, for reading."""
    try:
        return f"{Decimal(value) * 100:.3f}%"
    except (InvalidOperation, ValueError):
        return value


def _run_regime(tier: str) -> str:
    """The fee-regime clause for a run that happened: the tier, then engine 10's own
    figures from this run, then Kraken's reference schedule as a separate sentence.

    The exact published strings are given beside the rounded percentages, so a reader
    can check the message against the run's `state` digit for digit.
    """
    if not _ENGINE10_SEEN:
        measured = "engine 10 published no friction in this run"
    else:
        measured = "; ".join(
            f"engine 10 computed friction {friction} ({_pct(friction)}) and hurdle "
            f"{hurdle} ({_pct(hurdle)}) on {pair} in this run, at maker {maker} and taker "
            f"{taker} as engine 1 published them"
            for pair, maker, taker, friction, hurdle in _ENGINE10_SEEN
        )
    return f"{tier}; {measured}. {KRAKEN_REFERENCE_TIER_1}"


# --- the trade-producing subject, spec 100 step 2 -------------------------- #
#
# The hardest requirement in the spec, and the one that could have ended in a finding
# rather than in code: **a candidate has to be a real BUY with an expected move above
# the tier-3 bar, produced by the real predictor, not refused by the DI and not
# vetoed.** (Spec 100 wrote the bar as 1.625%, quoting invariant 5's reference tier 3;
# at the fake exchange's tier-3 rates engine 10's bar on this subject is 2.5 x 0.308% =
# 0.770%. Operator ruling S3, 2026-09-18.) Spec 100 is explicit that if that cannot be done honestly it is raised
# to the lead rather than routed around with a hand-built `state`.
#
# It can be done, and the measurement is in `docs/build-log/phase-6/c-interface.md`.
# What follows is the price series that does it, and only the price series is
# fabricated: the labeller, the feature module, the trainer, the calibrator, the DI and
# the anomaly detector are all the committed ones, reached through `_trained`.
#
# **The pattern is what a feature vector can actually see.** Planting "the price goes up
# later" is not plantable - the model reads one row of `FEATURE_NAMES`, not the future -
# so the signature is four bars of a straight, positive, volume-breaking climb, which
# lands in `log_return_4`, `efficiency_ratio_4` and `volume_z_4`, and the rise that
# follows is what the labeller turns into a `target`.
#
# **One signature in five is not honoured, deliberately.** The first version always was,
# and produced `p_target` of 0.97 and above with `p_stop` at nine decimal places of zero
# - a model that has memorised a deterministic rule. Nothing about that is *wrong*, and
# it is a poor subject: a chain driven by a certainty never exercises the paths that
# exist because the model is uncertain, and a calibrator fitted on perfect separation is
# not a calibrator anybody has tested. At four in five the measured `p_target` is 0.82 to
# 0.91 and the expected move is 2.2% to 2.7%, comfortably above the bar and visibly short
# of certain.

#: Bars between one planted signature and the next. Comfortably more than
#: `barriers.timeout_bars` (48), so one signature's label window never overlaps the next
#: signature's - overlapping windows would leak the second pattern into the first's
#: label and the criterion would be measuring the leak.
PLANTED_PERIOD: Final = 89

#: Bars the planted rise is spread over, and how far it rises. Well inside the timeout,
#: and above the 3.0% target with enough headroom that the 1.5% stop is never touched
#: first - which is what makes the label `target` rather than a coin toss.
PLANTED_RISE_BARS: Final = 8
PLANTED_RISE_TOTAL: Final = 0.045

#: One signature in this many is followed by a drift down instead of the rise.
PLANTED_HONOURED_IN: Final = 5

#: The tier-3 hurdle, `hurdle_multiple` x reference friction, as the number the subject
#: is measured against. **Not used to decide anything** - engine 10 computes the real
#: hurdle from the live fee tier, the measured spread and engine 9's slippage, and this
#: is only what the subject's own test compares an expected move to. A criterion that
#: hurdled against this constant would be checking its own arithmetic.
TIER_3_REFERENCE_HURDLE_PCT: Final = 0.01625


def _planted_candles(polars: ModuleType, *, pair: str, interval_s: int) -> Any:
    """A deterministic series carrying a signature that precedes a target touch.

    Seeded arithmetic and no random generator, so two runs of the gate a week apart
    produce the same bars and a criterion is measuring the engines rather than the
    weather. Each pair gets a different phase, because two identical series would let a
    pooled model read the pair column and the feature columns as the same information.
    """
    bars = CONSTRUCTED_DAYS * 86_400 // interval_s
    origin = (int(datetime(2024, 1, 1, tzinfo=UTC).timestamp()) // interval_s) * interval_s
    offset = sum(ord(char) for char in pair)
    price = 100.0 + (offset % 17)
    rows: list[dict[str, Any]] = []
    for index in range(bars):
        phase = (index + offset) % PLANTED_PERIOD
        cycle = (index + offset) // PLANTED_PERIOD
        honoured = (cycle * 2_654_435_761) % PLANTED_HONOURED_IN != 0
        volume = 900.0 + 60.0 * ((index + offset) % 13)
        trades = 15 + ((index + offset) % 9)
        if phase < 4:
            step = 0.0035
            volume *= 1.8
            trades = int(trades * 1.8)
        elif phase < 4 + PLANTED_RISE_BARS:
            step = (
                (1.0 + PLANTED_RISE_TOTAL) ** (1.0 / PLANTED_RISE_BARS) - 1.0
                if honoured
                else -0.0032
            )
        elif phase == 4 + PLANTED_RISE_BARS + 6:
            # The stop-out, so `stop` is an outcome the model has seen. A dataset of
            # nothing but `target` and `timeout` teaches a predictor that the stop never
            # happens, and every expected move it produces is then too high by the term
            # that is supposed to subtract.
            step = -0.022
        else:
            step = 0.0016 * math.sin((index + offset) / 5.0) - 0.00045
        price = max(price * (1.0 + step), 0.01)
        span = abs(step) + 0.0006
        rows.append(
            {
                "ts": origin + index * interval_s,
                "open": price * (1.0 - span / 3),
                "high": price * (1.0 + span),
                "low": price * (1.0 - span),
                "close": price,
                "volume": volume,
                "trades": trades,
            }
        )
    return polars.DataFrame(rows)


@dataclass(frozen=True)
class TradeSubjectModel:
    """One trained run over the planted market, and what it cost to produce.

    `config` is the committed config with `models.dir` and the three run ids answered,
    so engines 8, 13 and 15 load **these** artefacts. `oos` is the out-of-sample frame
    the training run wrote, which is what the subject's own test reads to show that a
    real BUY above the tier-3 bar exists.
    """

    models_dir: Path
    run_id: str
    config: Any
    oos: Any
    seconds: float


#: One trained subject per repository root, for the lifetime of the process.
#:
#: Spec 100 step 6: *"share one trained subject across criteria within a run where that
#: does not let one criterion's state leak into another's verdict, and say which."* This
#: is which. **The model is shared and nothing else is.** A fitted artefact is read-only
#: once written and every criterion reads the same numbers out of it, so sharing it
#: cannot carry one criterion's state into another's verdict - and training costs about
#: a minute, which six criteria paying separately would put on every gate run.
#:
#: The database, the paper broker's ledger and the store are **not** shared and must not
#: be: those are exactly the mutable state the rule is about, and each criterion builds
#: its own in its own temporary directory.
#:
#: Keyed by root, because a criterion pointed at a fabricated tree must not be handed
#: the real tree's model. The temporary directory is held on the entry so it outlives
#: the call that made it.
_TRADE_SUBJECTS: dict[str, TradeSubjectModel] = {}
_TRADE_SUBJECT_DIRS: list[Any] = []


def _trade_subject_model(ctx: VerifyContext) -> tuple[TradeSubjectModel | None, Outcome | None]:
    """The trained subject for `ctx.root`, training it once if nothing has yet.

    Reports PENDING rather than FAIL when the trainer or the modelling package is not
    reachable, for the reason `_phase5_module` does: a module of ours that has not been
    written is not a broken environment.
    """
    key = str(ctx.root)
    cached = _TRADE_SUBJECTS.get(key)
    if cached is not None:
        return cached, None

    polars, problem = _polars()
    if polars is None:
        return None, problem
    started = time.monotonic()
    holder = tempfile.TemporaryDirectory(prefix="acsoe-trade-subject-")
    _TRADE_SUBJECT_DIRS.append(holder)
    tmp = Path(holder.name)
    result, problem = _trained(
        ctx, tmp, name="subject", candles_builder=_planted_candles
    )
    if result is None:
        return None, problem
    report, _dataset, engine_config = result
    fold_runs = list(getattr(report, "fold_runs", ()) or ())
    if not fold_runs:
        return None, failed(
            "the training run over the planted market produced no fold artefacts, so "
            "engines 8, 13 and 15 have nothing to load. An assertion over an empty fold "
            "list is an assertion over nothing."
        )
    # The **last** fold, because it is the one trained on the most recent window and is
    # what a live daemon would have loaded. Taking the first would train the subject on
    # the oldest data available and is the kind of choice that looks arbitrary because
    # it is.
    run_id = str(fold_runs[-1])
    models_dir = tmp / "subject" / "models"
    subject = TradeSubjectModel(
        models_dir=models_dir,
        run_id=run_id,
        config=_ConfigWith(
            engine_config,
            {
                "models.dir": str(models_dir),
                "models.prediction_run_id": run_id,
                "models.anomaly_run_id": run_id,
                "models.skeptic_run_id": run_id,
            },
        ),
        oos=polars.read_parquet(report.oos_path),
        seconds=time.monotonic() - started,
    )
    _TRADE_SUBJECTS[key] = subject
    return subject, None


def _subject_buy_rows(subject: TradeSubjectModel, polars: ModuleType) -> Any:
    """The out-of-sample rows that are a BUY above the tier-3 bar and not DI-refused.

    The population a Phase 6 round trip is drawn from. Empty is the finding spec 100
    names: a subject that produces no honest BUY is raised to the lead, not arranged
    around.
    """
    return subject.oos.filter(
        polars.col("is_buy")
        & (~polars.col("di_refused"))
        & (polars.col("expected_move_pct") > TIER_3_REFERENCE_HURDLE_PCT)
    )


# --- paper_equity_continuous_across_fill, spec 105 ------------------------- #
#
# Operator ruling 2026-09-16: "a criterion, not just a fix". A's spec 87 rehearsal found
# that on the tick a resting entry filled, the paper ledger had not yet spent the cash
# while engine 21 already counted the position, so engine 19 wrote the notional twice,
# `peak_equity` kept it, and engine 17 froze the account on the next tick. Spec 103 fixed
# the broker. This is the assertion that would have caught it, and it is proved capable of
# failing by putting the defect back.
#
# **The bound is the fill's own cost, and it is computed from the rows the store holds.**
# Buying a position swaps cash for the position, so equity should be unchanged except for
# two things: the maker fee paid, and the difference between the price paid and the price
# the position is marked at. The fee, the quantity and the fill price come from the
# `orders` row engine 19 wrote for the entry; the mark comes from the `positions` row it
# wrote on the same tick. Nothing here is a constant, and a tolerance that were one would
# be a tolerance nobody could defend the day the fixture moved.
#
# **The chains are the registered ones, `acsoe.bootstrap.build_chains()`.** They were built
# by hand in registry order until spec 82 registered the Phase 6 engines, and spec 100's
# bodies switched this criterion over (lead decision D6): a criterion that builds its own
# chains can pass while the registry is wrong.
#
# **The subject is A's spec 87 rehearsal, reproduced.** It uses the constructed
# deterministic series (`_constructed_candles` is the same formula as
# `tests/research/test_training.py`), trained through the real trainer with the `btc`
# macro column joined from `AAAUSD` over four folds. It replays the window ending
# `FILL_SUBJECT_WINDOW_END` bars before the series end, on which A measured the real chain
# approving a BUY and engine 18 placing it at fee tier 3. Only the prices are this file's.

#: The universe the scripted market streams. BTC and ETH are the two macro assets the
#: committed config names, which is what lets engine 6 run for real.
FILL_SUBJECT_PAIRS: Final[tuple[str, ...]] = ("BTC/USD", "ETH/USD", "SOL/USD")

#: `{asset: archive pair}` joined as macro columns when the subject is trained.
FILL_SUBJECT_MACRO: Final[dict[str, str]] = {"btc": "AAAUSD"}

#: Folds trained. Fold 0 trains no skeptic (spec 69), so one fold would leave engine 15
#: unconfigured and the chain would stop there.
FILL_SUBJECT_FOLDS: Final = 4

#: Where the replayed window ends, in bars before the end of the constructed series, and
#: how long it is. The window A's probe found engine 8 calling a BUY on.
FILL_SUBJECT_WINDOW_END: Final = 200
FILL_SUBJECT_WINDOW_BARS: Final = 300

#: Flat bars planted after the window, so the ticks below have a continuous candle series
#: behind them and engine 4 never reports a missing candle.
FILL_SUBJECT_FLAT_BARS: Final = 4

#: The quoted spread above the best bid. The stream quote and the REST book are pinned to
#: the same prices, because engine 18 and the broker read different ones.
FILL_SUBJECT_SPREAD: Final = Decimal("0.010")

def _symbol(module_name: str, attr: str | None) -> tuple[Any, Outcome | None]:
    """One named symbol, or the module itself when `attr` is None, or the PENDING (or
    FAIL) that says why it is not there."""
    module, problem = try_import(module_name)
    if module is None:
        return None, problem or pending(f"{module_name} is unavailable")
    if attr is None:
        return module, None
    value, missing = module_attr(module, attr)
    if value is None:
        return None, pending(missing)
    return value, None


@dataclass(frozen=True)
class FillSubjectModel:
    """The trained run spec 105's subject loads, and what it cost to produce.

    Read-only once written, so it is shared across calls for one repository root, the
    same arrangement as `_TRADE_SUBJECTS`. The database, the broker and the store are
    built fresh for every run of the criterion and never cached.
    """

    models_dir: Path
    run_id: str
    seconds: float


_FILL_SUBJECTS: dict[str, FillSubjectModel] = {}
_FILL_SUBJECT_DIRS: list[Any] = []


#: What the trained subject is a function of, relative to a tree's root. The trainer, the
#: labeller, the walk-forward, the feature and DI arithmetic, the core types they import,
#: the config loader, the committed config and the harness that reads it. Nothing else in
#: a tree can change the artefacts.
FILL_SUBJECT_INPUTS: Final[tuple[str, ...]] = (
    "src/acsoe/research",
    "src/acsoe/modelling",
    "src/acsoe/core",
    "src/acsoe/platform",
    "config/default.yaml",
    "tests/harness/doubles.py",
)


def _fill_subject_key(ctx: VerifyContext) -> str:
    """The cache key for a tree's trained subject: a digest of what training reads.

    **Keyed by content, not by root** (spec 100 step 6). The mutation tests point these
    criteria at copied trees, one per test, and a root key retrains the same subject in
    every one of them, about half a minute each. A mutation of an engine does not change
    the artefacts, and a mutation of anything training reads changes this digest and
    retrains. A tree with none of these files falls back to its root, so nothing is shared
    with a tree the digest cannot describe.
    """
    digest = hashlib.sha256()
    found = False
    for relative in FILL_SUBJECT_INPUTS:
        path = ctx.root / relative
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path] if path.is_file() else []
        for file in files:
            if "__pycache__" in file.parts:
                continue
            found = True
            digest.update(file.relative_to(ctx.root).as_posix().encode("utf-8") + b"\0")
            digest.update(file.read_bytes() + b"\0")
    return digest.hexdigest() if found else "root:" + str(ctx.root)


def _fill_subject_model(ctx: VerifyContext) -> tuple[FillSubjectModel | None, Outcome | None]:
    """A's rehearsal subject, trained once per distinct training input per process.

    Shared read-only across criteria and across trees whose training inputs are
    byte-identical; the database, the broker and the store are built fresh for every
    drive and never cached.
    """
    key = _fill_subject_key(ctx)
    cached = _FILL_SUBJECTS.get(key)
    if cached is not None:
        return cached, None
    started = time.monotonic()
    holder = tempfile.TemporaryDirectory(prefix="acsoe-fill-subject-", ignore_cleanup_errors=True)
    _FILL_SUBJECT_DIRS.append(holder)
    tmp = Path(holder.name)
    result, problem = _trained(
        ctx,
        tmp,
        name="fill",
        max_folds=FILL_SUBJECT_FOLDS,
        macro_archive=FILL_SUBJECT_MACRO,
    )
    if result is None:
        return None, problem
    report, _dataset, _config = result
    fold_runs = list(getattr(report, "fold_runs", ()) or ())
    if not fold_runs:
        return None, failed(
            "the training run for spec 105's subject produced no fold artefacts, so "
            "engines 8, 13 and 15 have nothing to load"
        )
    run_id = str(fold_runs[-1])
    models_dir = Path(getattr(report, "models_dir", tmp / "fill" / "models"))
    for artefact in ("di.npz", "anomaly.joblib", "skeptic.txt"):
        if not (models_dir / run_id / artefact).is_file():
            return None, failed(
                f"the latest fold {run_id} fitted no {artefact}, so the chain would stop "
                "before engine 18 and the criterion could not reach its assertion"
            )
    subject = FillSubjectModel(
        models_dir=models_dir, run_id=run_id, seconds=time.monotonic() - started
    )
    _FILL_SUBJECTS[key] = subject
    return subject, None


def _equity_across_fill(subject: FillSubjectModel, tier: str) -> Outcome:
    """Drive a real entry to a real fill, then judge the two equity rows around it."""
    tools, problem = _drive_tools()
    if tools is None:
        return _awaiting(problem, tier)
    polars, problem = _polars()
    if polars is None:
        return _awaiting(problem, tier)
    doubles, fake_kraken, market_script = (
        tools["doubles"], tools["fake_kraken"], tools["market_script"]
    )
    contracts = tools["contracts"]

    base = doubles.load_default_config()
    data = base.as_dict()
    for field in ("prediction_run_id", "anomaly_run_id", "skeptic_run_id"):
        data["models"][field] = subject.run_id
    config = doubles.MappingConfig(data)
    interval_s = int(config.get(KEY_DECISION_BAR_S))
    tick_s = int(config.get("timeframes.loop_tick_s"))

    bar_cls = market_script.Bar
    rows = _constructed_candles(
        polars, pair=CONSTRUCTED_PAIRS[0], interval_s=interval_s
    ).to_dicts()
    end = len(rows) - FILL_SUBJECT_WINDOW_END
    window = [
        bar_cls(
            ts=int(row["ts"]),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
            trades=int(row["trades"]),
        )
        for row in rows[end - FILL_SUBJECT_WINDOW_BARS : end]
    ]
    last = window[-1].ts
    clock = doubles.FixedClock(datetime.fromtimestamp(last, tz=UTC))
    market = market_script.ScriptedMarket(
        clock=clock, interval_s=interval_s, published_bars=200, pairs=FILL_SUBJECT_PAIRS
    )
    profile = market.use_fee_tier(3)
    if profile.tier != 3:
        return failed(f"the harness applied fee tier {profile.tier} when asked for 3; " + tier)
    bid = window[-1].close.quantize(Decimal("0.001"))
    ask = bid + FILL_SUBJECT_SPREAD
    flat = [
        bar_cls.flat(last + interval_s * k, str(bid), trades=17 + (k * 7) % 23)
        for k in range(1, FILL_SUBJECT_FLAT_BARS + 1)
    ]
    for pair in FILL_SUBJECT_PAIRS:
        market.plant(pair, window)
        market.plant(pair, flat)
        market.set_quote(pair, bid=str(bid), ask=str(ask))
        market.set_order_book(pair, bids=[(str(bid), "1000")], asks=[(str(ask), "1000")])

    holder = tempfile.TemporaryDirectory(prefix="acsoe-fill-drive-", ignore_cleanup_errors=True)
    try:
        db = Path(holder.name) / "acsoe.sqlite"
        tools["migrate"](db)
        store = tools["store"](db, models_dir=subject.models_dir)
        try:
            return _judge_fill(
                tools, contracts, fake_kraken, store, market, clock, config,
                entry_at=last + interval_s + 1, tick_s=tick_s, tier=tier,
            )
        finally:
            store.close()
    finally:
        holder.cleanup()


def _judge_fill(
    tools: dict[str, Any],
    contracts: Any,
    fake_kraken: Any,
    store: Any,
    market: Any,
    clock: Any,
    config: Any,
    *,
    entry_at: int,
    tick_s: int,
    tier: str,
) -> Outcome:
    """Three ticks - quiet, entry, fill - and the verdict read from the store alone."""
    store.append_command(
        contracts.CommandRow(
            command=contracts.CommandName.ACTIVATE.value,
            source=contracts.CommandSource.CONSOLE,
            reason="verify.py spec 105",
            created_at=1,
            updated_at=1,
        )
    )
    broker = tools["broker"](market, store=store, config=config, clock=clock)
    orchestrator = tools["orchestrator"](
        config=config,
        clock=clock,
        clients=tools["doubles"].FakeClients(
            kraken=broker, store=store, recorder=fake_kraken.FakeRecorder()
        ),
        chains=tools["build_chains"](),
        run_id="verify-phase-6-fill",
    )

    def tick(at: int) -> dict[str, Any]:
        clock.set(datetime.fromtimestamp(at, tz=UTC))
        state = dict(orchestrator.tick())
        _note_engine10(state)
        return state

    quiet = tick(entry_at - tick_s)
    if "trading_blocked_by" in quiet:
        return failed(
            f"the quiet tick before the entry was blocked by {quiet['trading_blocked_by']}: "
            f"{quiet.get('block_reason')}; {_run_regime(tier)}"
        )
    entry = tick(entry_at)
    execution = entry.get("execution") or {}
    if "trading_blocked_by" in entry or execution.get("placed") is not True:
        return failed(
            "the subject placed no entry, so there was no fill to judge: blocked by "
            f"{entry.get('trading_blocked_by')!r} ({entry.get('block_reason')!r}), "
            f"engine 18 said {execution.get('reason_code')!r}. A's spec 87 probe placed one "
            f"on this window; {_run_regime(tier)}"
        )
    userref = int(execution["userref"])
    pair = str(execution.get("pair"))
    resting = store.order_by_userref(userref)
    if resting is None or resting.limit_price is None:
        return failed(
            f"engine 18 placed entry {userref} and engine 19 recorded no resting row with a "
            f"limit price for it; {_run_regime(tier)}"
        )
    # One trade strictly below the limit, between the entry tick and the next: a resting
    # post-only buy fills at its own price (spec 88).
    market.plant_trade(
        pair,
        at=datetime.fromtimestamp(entry_at + tick_s // 2, tz=UTC),
        price=str(resting.limit_price * Decimal("0.999")),
    )
    filled_tick = tick(entry_at + tick_s)

    order = store.order_by_userref(userref)
    if order is None or str(order.status.value) != "filled":
        return failed(
            f"a trade below the limit of entry {userref} did not fill it: the stored order is "
            f"{None if order is None else order.status.value!r}; {_run_regime(tier)}"
        )
    if order.avg_fill_price is None or order.fee is None:
        return failed(
            f"entry {userref} is recorded filled without a fill price or a fee, so its own "
            f"cost cannot be computed; {_run_regime(tier)}"
        )
    run_id = orchestrator.run_id
    series = [row for row in store.equity_series() if row.run_id == run_id]
    at_fill = [index for index, row in enumerate(series) if row.cycle_id == order.cycle_id]
    if len(at_fill) != 1 or at_fill[0] == 0:
        memory = filled_tick.get("memory") or {}
        return failed(
            f"the fill tick (cycle {order.cycle_id}) has {len(at_fill)} equity row(s) with "
            f"{at_fill[0] if at_fill else 0} before it; engine 19 said "
            f"{memory.get('equity_skipped_reason')!r}. A fill tick with no equity row is a "
            f"gap in the series engine 17 reads; {_run_regime(tier)}"
        )
    before, after = series[at_fill[0] - 1], series[at_fill[0]]
    if before.cycle_id != order.cycle_id - 1:
        return failed(
            f"the equity row before the fill tick is from cycle {before.cycle_id}, not "
            f"{order.cycle_id - 1}, so the entry tick wrote none; {_run_regime(tier)}"
        )
    position_ids = [
        str(found[0])
        for found in store.connection.execute(
            "SELECT position_id FROM positions WHERE entry_userref = ?", (userref,)
        ).fetchall()
    ]
    position = store.position(position_ids[0]) if len(position_ids) == 1 else None
    if position is None:
        return failed(
            f"entry {userref} filled and the store holds {len(position_ids)} position(s) "
            "for it, not one; " + _run_regime(tier)
        )
    qty, price, fee = order.filled_qty, order.avg_fill_price, order.fee
    if position.qty != qty or after.open_position_count != 1:
        return failed(
            f"the position holds {position.qty}, the fill recorded {qty}, and the fill "
            f"tick's equity row counts {after.open_position_count} open position(s); "
            "the fill's cost can only be read off one position that matches its fill; "
            + _run_regime(tier)
        )
    # The mark, from the stored row only. Since spec 106 engine 21 stores a position
    # opened by this tick's fill with `last_price` at the fill price. A NULL mark is
    # therefore that fix regressed, and it is a FAIL. It is never read off the equity
    # row instead: that would accept a position the console shows with no price.
    # Spec 107; before it this branch accepted NULL when the equity row valued the
    # position at cost, and B's mutant P1 (the NULL restored) passed.
    if position.last_price is None:
        return failed(
            f"entry {userref}'s position is stored with no mark (last_price NULL) on its "
            f"fill tick, cycle {order.cycle_id}. Engine 21 stores the fill price as the mark "
            "of a position this tick's fill opened (spec 106), so the mark-to-bid part of "
            "the fill's cost cannot be read from the store; " + _run_regime(tier)
        )
    mark = position.last_price
    if after.positions_value != qty * mark:
        return failed(
            f"the fill tick's equity row values the position at {after.positions_value}, "
            f"not {qty} x its mark {mark}; " + _run_regime(tier)
        )
    mark_gap = qty * abs(mark - price)
    tolerance = fee + mark_gap
    moved = after.equity - before.equity
    detail = (
        f"equity {before.equity} on cycle {before.cycle_id} and {after.equity} on the fill "
        f"tick, cycle {after.cycle_id}: it moved {moved}. The fill's own cost is {tolerance}: "
        f"fee {fee} + {qty} x |mark {mark} - fill {price}|, recorded for "
        f"{pair} entry {userref} (notional {qty * price})"
    )
    if abs(moved) <= tolerance:
        return passed(detail + "; " + _run_regime(tier))
    return failed(
        detail + ". Equity moved by more than the fill cost, so the cash and the position "
        "disagree about when the fill happened. The paper ledger must count every fill the "
        "broker has executed, recorded or not (invariant 2, spec 103); otherwise the notional "
        "is counted twice and peak_equity carries it into engine 17's drawdown; " + _run_regime(tier)
    )


def check_paper_equity_continuous_across_fill(ctx: VerifyContext) -> Outcome:
    """Equity on the tick an entry fills equals the tick before, within the fill's own cost.

    Spec 105, operator ruling 2026-09-16. The criterion drives real orchestrator ticks at
    fee tier 3 against B's paper broker, with engine 19 recording to a real `StoreClient`.
    A quiet tick, then the entry tick (the whole chain approves and engine 18 places a
    post-only buy), then the fill tick (a planted trade below the limit, which engine 21
    observes). The verdict is read from the store only: the two `equity_snapshots` rows,
    the entry's `orders` row (quantity, fill price, fee) and the new `positions` row (its
    mark, which must be stored: a NULL `last_price` is a FAIL, spec 107). The tolerance is
    the fee plus the quantity times the gap between mark and fill price, and never a
    constant.

    The chains are the registered ones, from `acsoe.bootstrap.build_chains()`.

    The named wrong implementation is the pre-spec-103 broker, whose balance leaves out a
    fill that engine 19 has not recorded yet. On the fill tick the cash is then unspent
    while the position is counted, and equity jumps by the whole notional.
    """
    with root_import_path(ctx.root):
        tier, problem = _tier_sentence(3)
        if tier is None:
            return _awaiting(problem, "at fee tier 3")
        _, problem = _drive_tools()
        if problem is not None:
            return _awaiting(problem, tier)
        subject, problem = _fill_subject_model(ctx)
        if subject is None:
            return _awaiting(problem, tier)
        _regime_begin()
        return _equity_across_fill(subject, tier)


# --- the registered chain, driven: spec 100 -------------------------------- #
#
# Every criterion below that needs the chain to run drives the **registered** chains,
# `acsoe.bootstrap.build_chains()`, through the real `Orchestrator`, against a real
# `StoreClient` in a temporary directory, B's `PaperBroker` wrapping the scripted market
# at fee tier 3, and the trained subject `_fill_subject_model` builds once. That subject
# is A's spec 87 rehearsal window, on which the real chain was measured approving a BUY;
# the planted-market subject above (`_trade_subject_model`) is kept for its own test and
# is not what the round trips run on, because the fill subject is the one whose
# entry tick has been measured end to end.
#
# **Nothing here builds an engine's payload.** The market, the book, the leaderboard rows
# and the commands the operator writes are the subject; every `state` key is published by
# the engine that owns it.

#: Flat bars planted after the subject window. More than `barriers.timeout_bars` (48), so
#: the timeout leg has candles behind every tick and engine 4 never sees a missing one.
DRIVE_FLAT_BARS: Final = 80

#: The universe the scripted market streams for a trade. BTC and ETH are the two macro
#: assets the committed config names; engine 7 ranks alphabetically, so BTC/USD is traded.
DRIVE_PAIRS: Final[tuple[str, ...]] = FILL_SUBJECT_PAIRS

#: The recorded book's two pairs: ADA/USD is the thin one, BTC/USD the deep one. The thin
#: run streams ADA first so engine 7 chooses it; the deep run streams the usual universe.
BOOK_THIN_PAIR: Final = "ADA/USD"
BOOK_DEEP_PAIR: Final = "BTC/USD"
BOOK_THIN_UNIVERSE: Final[tuple[str, ...]] = ("ADA/USD", "BTC/USD", "ETH/USD")

#: The fake exchange's rules for ADA/USD, which `tests/fixtures/kraken/asset_pairs.json`
#: does not carry. Invented exchange data for the fake, the same values
#: `tests/engines/test_order_book.py` gives it; engine 9 reads only `quote` from them.
BOOK_THIN_PAIR_RULE: Final[dict[str, Any]] = {
    "base": "ADA",
    "quote": "USD",
    "ordermin": "5",
    "costmin": "1.00",
    "tick_size": "0.000001",
    "lot_decimals": 8,
    "pair_decimals": 6,
}

#: How far past a barrier the planted touch prints, and where the book is then pinned.
#: Subject data: what the market did. The exit price is read back from the book the
#: criterion pinned and recomputed, never assumed.
TOUCH_PAST: Final = Decimal("0.05")

#: Quiet minutes watched between the fill and the barrier.
WATCH_MINUTES: Final = 3

#: The level size every pinned book carries. Larger than any position the subject opens,
#: so a taker sell is one level; the walk is still recomputed rather than assumed.
PINNED_LEVEL_QTY: Final = "1000"


class RecordingBroker:
    """B's paper broker, with every order request and cancel it was handed written down.

    Transparent: every attribute that is not one of the two recorded calls is the
    broker's own, so engines 18, 21 and 22 see exactly the object the daemon gives them.
    It exists because "no market order is ever placed" and "the entry was not
    re-placed" are claims about what reached the exchange, and in paper mode the broker
    **is** the exchange: a replacement placed and then resolved inside one tick leaves no
    row behind for engine 19 to write.

    What it cannot see is an order an engine built and never handed over. Nothing can,
    short of replacing the contract class, and that would be fabricating the contract.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.requests: list[Any] = []
        self.cancels: list[int] = []

    async def add_order(self, request: Any) -> Any:
        self.requests.append(request)
        return await self._inner.add_order(request)

    async def cancel_order(self, userref: int) -> Any:
        self.cancels.append(int(userref))
        return await self._inner.cancel_order(userref)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _drive_tools() -> tuple[dict[str, Any] | None, Outcome | None]:
    """Every symbol a drive needs, or the first thing that is missing.

    Phase 6's own engines first, through `_phase6_engines`, so a missing one is named by
    number and owning spec; then the broker; then the rest. Imported inside the caller's
    `root_import_path`, so a fabricated tree is judged on its own code. The chains come
    from `acsoe.bootstrap.build_chains`, which is the registry the daemon runs.
    """
    problem = _phase6_engines(
        "order_book", "adaptive_router", "decision", "execution", "position_manager",
        "exit", "memory",
    )
    if problem is None:
        problem = _paper_broker_module()
    if problem is not None:
        return None, problem
    tools: dict[str, Any] = {}
    wanted: list[tuple[str, str, str | None]] = [
        ("broker", "acsoe.clients.paper.broker", "PaperBroker"),
        ("store", "acsoe.clients.store.client", "StoreClient"),
        ("migrate", "acsoe.clients.store.migrations", "apply_migrations"),
        ("contracts", "acsoe.clients.store.contracts", None),
        ("orchestrator", "acsoe.core.orchestrator", "Orchestrator"),
        ("build_chains", "acsoe.bootstrap", "build_chains"),
        ("run_blocking", "acsoe.platform.aio", "run_blocking"),
        ("manager", "acsoe.engines.position_manager.contracts", None),
        ("exit", "acsoe.engines.exit.contracts", None),
        ("guard", "acsoe.engines.data_guard.contracts", None),
        ("doubles", "tests.harness.doubles", None),
        ("fake_kraken", "tests.harness.fake_kraken", None),
        ("market_script", "tests.harness.market_script", None),
    ]
    for label, module_name, attr in wanted:
        value, problem = _symbol(module_name, attr)
        if value is None:
            return None, problem
        tools[label] = value
    return tools, None


class DriveError(Exception):
    """A drive step found the chain not doing what the criterion requires.

    Raised by the step helpers and turned into a FAIL by the criterion, with the tier
    sentence appended. Not `AssertionError`, which `python -O` strips, and not a bare
    `Exception`, so a defect in this file still arrives as `criterion raised`.
    """


@dataclass
class Drive:
    """One scripted market, one store, one broker and one orchestrator, ticked by hand.

    Built by :func:`_driven`, which owns the temporary directory and closes the store.
    """

    tools: dict[str, Any]
    config: Any
    clock: Any
    market: Any
    store: Any
    broker: RecordingBroker
    orchestrator: Any
    chains: Any
    pairs: tuple[str, ...]
    last_bar_ts: int
    bid: Decimal
    interval_s: int
    tick_s: int
    commands: int = 0

    @property
    def entry_at(self) -> int:
        """One second into the first bar after the window: the tick on which it closed."""
        return self.last_bar_ts + self.interval_s + 1

    def tick(self, at: int) -> dict[str, Any]:
        """One real orchestrator tick at `at` (epoch seconds), and its finished `state`.

        `state["system"]` is the orchestrator's own dict and step 4 may already have
        cleared `close_intent` in it, so the copy returned here is what the tick ended
        with, not what the engines saw.
        """
        self.clock.set(datetime.fromtimestamp(at, tz=UTC))
        state = dict(self.orchestrator.tick())
        state["system"] = dict(state["system"])
        _note_engine10(state)
        return state

    def pin(self, bid: Decimal, *, pairs: Sequence[str] | None = None) -> None:
        """Pin the stream quote **and** the REST book of `pairs` to one market.

        Engines 3 and 18 read the stream; engine 9 and the broker read the book. Moving
        one without the other would be scripting two markets.
        """
        ask = bid + FILL_SUBJECT_SPREAD
        for pair in pairs or self.pairs:
            self.market.set_quote(pair, bid=str(bid), ask=str(ask))
            self.market.set_order_book(
                pair,
                bids=[(str(bid), PINNED_LEVEL_QTY)],
                asks=[(str(ask), PINNED_LEVEL_QTY)],
            )

    def cross(self, pair: str, *, quoted: Decimal, book_bid: Decimal) -> None:
        """A crossed stream quote on `pair`, which engine 4 blocks on as a negative
        spread, and a sound REST book at `book_bid` for anything that has to sell."""
        self.market.set_quote(pair, bid=str(quoted), ask=str(quoted - FILL_SUBJECT_SPREAD))
        self.market.set_order_book(
            pair,
            bids=[(str(book_bid), PINNED_LEVEL_QTY)],
            asks=[(str(book_bid + FILL_SUBJECT_SPREAD), PINNED_LEVEL_QTY)],
        )

    def command(self, name: str) -> None:
        """A command row, the way the console writes one."""
        contracts = self.tools["contracts"]
        self.commands += 1
        self.store.append_command(
            contracts.CommandRow(
                command=name,
                source=contracts.CommandSource.CONSOLE,
                reason="verify.py spec 100",
                created_at=self.commands,
                updated_at=self.commands,
            )
        )

    def open_orders(self) -> tuple[Any, ...]:
        return tuple(self.tools["run_blocking"](self.broker.open_orders()))

    def gates(self) -> list[str]:
        """Every registered gate in the guard and opportunity chains, in chain order."""
        return [
            str(engine.name)
            for chain in (self.chains.guard, self.chains.opportunity)
            for engine in chain
            if getattr(engine, "is_gate", False) is True
        ]

    def command_rows(self) -> list[dict[str, Any]]:
        """Every `commands` row. Identifier and timestamp columns only, no money."""
        cursor = self.store.connection.execute(
            "SELECT id, command, source, created_at, claimed_at, consumed_at "
            "FROM commands ORDER BY id"
        )
        names = ("id", "command", "source", "created_at", "claimed_at", "consumed_at")
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    def orders_with_intent(self, intent: str) -> list[Any]:
        """Every stored order with this intent, read through the store's own model."""
        userrefs = [
            int(row[0])
            for row in self.store.connection.execute(
                "SELECT userref FROM orders WHERE intent = ? ORDER BY userref", (intent,)
            ).fetchall()
        ]
        return [self.store.order_by_userref(userref) for userref in userrefs]

    def position_ids(self) -> list[str]:
        return [
            str(row[0])
            for row in self.store.connection.execute(
                "SELECT position_id FROM positions ORDER BY position_id"
            ).fetchall()
        ]

    def run_equity(self) -> list[Any]:
        run_id = self.orchestrator.run_id
        return [row for row in self.store.equity_series() if row.run_id == run_id]


def _micros(at: int) -> int:
    return at * 1_000_000


def _config_decimal(config: Any, key: str) -> Decimal:
    """A configured number as an exact `Decimal`; `repr` for a float, as the engines do."""
    value = config.get(key)
    return Decimal(repr(value) if isinstance(value, float) else str(value))


def _drive_config(tools: dict[str, Any], subject: FillSubjectModel) -> Any:
    """The committed config with the trained run named, and nothing else changed."""
    doubles = tools["doubles"]
    data = doubles.load_default_config().as_dict()
    for field in ("prediction_run_id", "anomaly_run_id", "skeptic_run_id"):
        data["models"][field] = subject.run_id
    return doubles.MappingConfig(data)


@contextlib.contextmanager
def _driven(
    tools: dict[str, Any],
    subject: FillSubjectModel,
    polars: Any,
    *,
    pairs: tuple[str, ...] = DRIVE_PAIRS,
    before_start: Callable[[Any, Any], None] | None = None,
) -> Iterator[Drive]:
    """The subject window planted, the account opened, the system activated.

    `before_start(market, store)` lets a criterion add subject data (a pair rule, a
    recorded book, leaderboard rows) before the first tick. No tick is run here.
    """
    doubles, fake_kraken, market_script = (
        tools["doubles"], tools["fake_kraken"], tools["market_script"]
    )
    config = _drive_config(tools, subject)
    interval_s = int(config.get(KEY_DECISION_BAR_S))
    tick_s = int(config.get("timeframes.loop_tick_s"))
    bar_cls = market_script.Bar
    rows = _constructed_candles(
        polars, pair=CONSTRUCTED_PAIRS[0], interval_s=interval_s
    ).to_dicts()
    end = len(rows) - FILL_SUBJECT_WINDOW_END
    window = [
        bar_cls(
            ts=int(row["ts"]),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
            trades=int(row["trades"]),
        )
        for row in rows[end - FILL_SUBJECT_WINDOW_BARS : end]
    ]
    last = window[-1].ts
    clock = doubles.FixedClock(datetime.fromtimestamp(last, tz=UTC))
    market = market_script.ScriptedMarket(
        clock=clock, interval_s=interval_s, published_bars=200, pairs=pairs
    )
    profile = market.use_fee_tier(3)
    if profile.tier != 3:
        raise DriveError(f"the harness applied fee tier {profile.tier} when asked for 3")
    bid = window[-1].close.quantize(Decimal("0.001"))
    flat = [
        bar_cls.flat(last + interval_s * k, str(bid), trades=17 + (k * 7) % 23)
        for k in range(1, DRIVE_FLAT_BARS + 1)
    ]
    for pair in pairs:
        market.plant(pair, window)
        market.plant(pair, flat)

    holder = tempfile.TemporaryDirectory(prefix="acsoe-drive-", ignore_cleanup_errors=True)
    try:
        db = Path(holder.name) / "acsoe.sqlite"
        tools["migrate"](db)
        store = tools["store"](db, models_dir=subject.models_dir)
        try:
            broker = RecordingBroker(
                tools["broker"](market, store=store, config=config, clock=clock)
            )
            chains = tools["build_chains"]()
            orchestrator = tools["orchestrator"](
                config=config,
                clock=clock,
                clients=doubles.FakeClients(
                    kraken=broker, store=store, recorder=fake_kraken.FakeRecorder()
                ),
                chains=chains,
                run_id="verify-phase-6-drive",
            )
            drive = Drive(
                tools=tools, config=config, clock=clock, market=market, store=store,
                broker=broker, orchestrator=orchestrator, chains=chains, pairs=pairs,
                last_bar_ts=last, bid=bid, interval_s=interval_s, tick_s=tick_s,
            )
            drive.pin(bid)
            if before_start is not None:
                before_start(market, store)
            drive.command(str(tools["contracts"].CommandName.ACTIVATE.value))
            yield drive
        finally:
            store.close()
    finally:
        holder.cleanup()


def _warm_up(drive: Drive) -> dict[str, Any]:
    """One quiet tick before the bar closes. It writes the first equity row, which engine
    11 sizes against; without it the entry tick is refused, correctly."""
    state = drive.tick(drive.entry_at - drive.tick_s)
    if "trading_blocked_by" in state:
        raise DriveError(
            f"the quiet tick before the entry was blocked by {state['trading_blocked_by']}: "
            f"{state.get('block_reason')}"
        )
    return state


@dataclass(frozen=True)
class Entry:
    """What the entry tick placed, with the limit recomputed from the published bid."""

    userref: int
    pair: str
    qty: Decimal
    limit: Decimal
    placed_at: int
    maker: Decimal
    taker: Decimal
    gates: tuple[str, ...]


def _entry(drive: Drive, *, pair: str | None = None) -> tuple[Entry, dict[str, Any]]:
    """Tick at the bar close: every registered gate runs and passes, and engine 18
    places one post-only buy at the best bid rounded down onto the pair's grid."""
    gates = drive.gates()
    table = list(drive.tools["table_gates"])
    if sorted(gates) != table:
        raise DriveError(
            f"the registered gates {sorted(gates)} are not the registry table's gates "
            f"{table} (context/engine-contracts.md), so a trade here would skip a gate"
        )
    state = drive.tick(drive.entry_at)
    if "trading_blocked_by" in state:
        raise DriveError(
            f"the entry tick was blocked by {state['trading_blocked_by']}: "
            f"{state.get('block_reason')}. A's spec 87 probe placed an entry on this window"
        )
    unrun = [gate for gate in gates if gate not in state]
    if not gates or unrun:
        raise DriveError(
            f"the entry tick did not run every registered gate: {unrun or 'none registered'}"
        )
    tier = (state.get("exchange") or {}).get("fee_tier") or {}
    if tier.get("tier") != 3:
        raise DriveError(f"engine 1 published fee tier {tier.get('tier')!r}, not 3")
    execution = state.get("execution") or {}
    if execution.get("placed") is not True:
        raise DriveError(
            "engine 18 placed nothing on a tick every gate passed: "
            f"{execution.get('reason_code')!r}"
        )
    orders = execution.get("orders") or []
    if len(orders) != 1:
        raise DriveError(f"engine 18 published {len(orders)} order rows, not one")
    row = orders[0]
    traded = str(execution.get("pair"))
    if pair is not None and traded != pair:
        raise DriveError(f"engine 7 chose {traded}, and this drive needs {pair}")
    shape = tuple(
        row.get(key) for key in ("side", "intent", "order_type", "oflags", "status")
    )
    if shape != ("buy", "entry", "limit", "post", "resting"):
        raise DriveError(f"the entry is not a resting post-only limit buy: {shape}")
    rules = state["exchange"]["pair_rules"]["pairs"][traded]
    grid = Decimal(1).scaleb(-int(rules["pair_decimals"]))
    quote = state["market_sensor"]["quotes"][traded]
    limit = Decimal(str(quote["bid"])).quantize(grid, rounding=ROUND_DOWN)
    if Decimal(str(row["limit_price"])) != limit:
        raise DriveError(
            f"the entry's limit is {row['limit_price']}, not the best bid {quote['bid']} "
            f"rounded down to {grid}: {limit}"
        )
    return (
        Entry(
            userref=int(execution["userref"]),
            pair=traded,
            qty=Decimal(str(row["qty"])),
            limit=limit,
            placed_at=int(row["placed_at"]),
            maker=Decimal(str(tier["maker_fee_pct"])),
            taker=Decimal(str(tier["taker_fee_pct"])),
            gates=tuple(gates),
        ),
        state,
    )


@dataclass(frozen=True)
class Filled:
    """The position a fill opened, its barriers recomputed from the config."""

    position_id: str
    filled_at: int
    stop: Decimal
    target: Decimal
    timeout_at: int


def _fill(drive: Drive, entry: Entry) -> tuple[Filled, dict[str, Any]]:
    """A trade strictly below the limit, then the next tick: the fill is recorded."""
    drive.market.plant_trade(
        entry.pair,
        at=datetime.fromtimestamp(drive.entry_at + drive.tick_s // 2, tz=UTC),
        price=str(entry.limit * Decimal("0.999")),
    )
    at = drive.entry_at + drive.tick_s
    state = drive.tick(at)
    if "trading_blocked_by" in state:
        raise DriveError(f"the fill tick was blocked by {state['trading_blocked_by']}")
    order = drive.store.order_by_userref(entry.userref)
    if order is None or str(order.status.value) != "filled":
        raise DriveError(
            f"a trade below the limit did not fill entry {entry.userref}: "
            f"{None if order is None else order.status.value!r}"
        )
    if order.avg_fill_price != entry.limit or order.filled_qty != entry.qty:
        raise DriveError(
            f"entry {entry.userref} filled {order.filled_qty} at {order.avg_fill_price}; a "
            f"resting post-only buy fills {entry.qty} at its own limit {entry.limit}"
        )
    positions = drive.store.open_positions()
    if len(positions) != 1 or positions[0].entry_userref != entry.userref:
        raise DriveError(
            f"the fill left {len(positions)} open position(s), not the entry's one"
        )
    position = positions[0]
    config = drive.config
    stop = entry.limit * (1 - _config_decimal(config, "barriers.stop_pct"))
    target = entry.limit * (1 + _config_decimal(config, "barriers.target_pct"))
    timeout_s = int(config.get("barriers.timeout_bars")) * drive.interval_s
    stored = (position.stop_price, position.target_price, position.timeout_at, position.opened_at)
    expected = (stop, target, _micros(at + timeout_s), _micros(at))
    if stored != expected:
        raise DriveError(
            f"the stored (stop, target, timeout_at, opened_at) are {stored}; measured from "
            f"the fill at {entry.limit} with the configured barriers they are {expected}"
        )
    return (
        Filled(
            position_id=str(position.position_id),
            filled_at=at,
            stop=stop,
            target=target,
            timeout_at=at + timeout_s,
        ),
        state,
    )


def _watch(drive: Drive, filled: Filled, *, start: int, until: int, every: int) -> int:
    """Tick every `every` seconds from `start` up to, not including, `until`.

    Every tick: no guard block, nothing triggered, and the stored position marked at the
    pinned bid, so the watch is a fact in the store rather than a loop that ran. A bar
    close runs the opportunity chain again and engine 11 refuses a second position on
    the pair; that refuses a *new* trade and is not a hold. Returns the ticks run.
    """
    ticks = 0
    at = start
    while at < until:
        state = drive.tick(at)
        if state.get("guard_blockers"):
            raise DriveError(
                f"the watch was blocked at {at} by {state['guard_blockers']}"
            )
        manager = state.get("position_manager") or {}
        if manager.get("triggered") or manager.get("hold_reason") is not None:
            raise DriveError(
                f"on flat trading at {at} engine 21 triggered {manager.get('triggered')} "
                f"and held for {manager.get('hold_reason')!r}"
            )
        position = drive.store.position(filled.position_id)
        if position is None or position.last_price != drive.bid:
            raise DriveError(
                f"the stored mark at {at} is "
                f"{None if position is None else position.last_price}, not the bid {drive.bid}"
            )
        ticks += 1
        at += every
    return ticks


def _sold_at(levels: Sequence[tuple[Decimal, Decimal]], qty: Decimal) -> Decimal:
    """The average price a taker sell of `qty` gets from `levels`, best bid first.

    Walked here from the book the criterion pinned, so the exit price the store holds
    is compared against the market that was scripted rather than read back.
    """
    remaining = qty
    proceeds = Decimal(0)
    for price, volume in levels:
        if remaining <= 0:
            break
        taken = volume if volume < remaining else remaining
        proceeds += taken * price
        remaining -= taken
    if remaining > 0:
        raise DriveError(f"the pinned book cannot absorb a sell of {qty}")
    return proceeds / qty


@dataclass(frozen=True)
class Closed:
    """A round trip recomputed from the scripted market and the published fee tier."""

    exit_price: Decimal
    exit_qty: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    realised: Decimal


def _reconcile(
    drive: Drive,
    entry: Entry,
    filled: Filled,
    *,
    exit_at: int,
    book_bid: Decimal,
    outcome: str,
    lot_decimals: int,
    fallbacks: tuple[str, ...],
    equity: bool,
) -> Closed:
    """Every row engine 19 wrote for the round trip, against a recomputation.

    **Exact, to the last digit, with no tolerance.** The quantity is rounded down onto
    the lot grid here, the exit price is walked here over the book the criterion pinned,
    the fees are the notional times the maker and taker rates engine 1 published, and
    the realised PnL is proceeds less cost less both fees. Each is then compared with
    the `orders`, `positions`, `trades` and (when the balance was known) the
    `equity_snapshots` row. A number read back from a row it is being checked against
    proves nothing.
    """
    store = drive.store
    exits = drive.tools["exit"]
    exit_userref = int(exits.exit_userref_for(filled.position_id))
    exit_qty = entry.qty.quantize(Decimal(1).scaleb(-lot_decimals), rounding=ROUND_DOWN)
    exit_price = _sold_at(((book_bid, Decimal(PINNED_LEVEL_QTY)),), exit_qty)
    entry_fee = entry.qty * entry.limit * entry.maker
    exit_fee = exit_qty * exit_price * entry.taker
    realised = exit_qty * exit_price - exit_qty * entry.limit - entry_fee - exit_fee

    entry_row = store.order_by_userref(entry.userref)
    if entry_row is None or entry_row.fee != entry_fee:
        raise DriveError(
            f"the entry's stored fee is {None if entry_row is None else entry_row.fee}, not "
            f"{entry.qty} x {entry.limit} x maker {entry.maker} = {entry_fee}"
        )
    exit_row = store.order_by_userref(exit_userref)
    if exit_row is None:
        raise DriveError(f"no exit order {exit_userref} was recorded for {filled.position_id}")
    got = (
        exit_row.side.value, exit_row.intent.value, exit_row.order_type.value,
        exit_row.status.value, exit_row.filled_qty, exit_row.avg_fill_price, exit_row.fee,
    )
    want = ("sell", "exit", "market", "filled", exit_qty, exit_price, exit_fee)
    if got != want:
        raise DriveError(
            "the exit order (side, intent, type, status, filled, price, fee) is "
            f"{got}; recomputed from the pinned book and taker {entry.taker} it is {want}"
        )
    position = store.position(filled.position_id)
    trade_id = str(exits.trade_id_for(filled.position_id))
    if (
        position is None
        or position.status.value != "closed"
        or position.closed_at != _micros(exit_at)
        or position.trade_id != trade_id
    ):
        raise DriveError(
            f"position {filled.position_id} is stored as "
            f"{None if position is None else (position.status.value, position.closed_at, position.trade_id)}, "
            f"not closed at {_micros(exit_at)} under {trade_id}"
        )
    trades = {row.trade_id: row for row in store.recent_closed_trades(limit=1000)}
    trade = trades.get(trade_id)
    if trade is None:
        raise DriveError(f"no trade {trade_id} was recorded")
    got_trade = (
        trade.outcome.value, trade.qty, trade.entry_price, trade.exit_price,
        trade.entry_fee, trade.exit_fee, trade.realised_pnl, trade.entry_userref,
        trade.exit_userref, tuple(trade.fallbacks_used),
    )
    want_trade = (
        outcome, exit_qty, entry.limit, exit_price, entry_fee, exit_fee, realised,
        entry.userref, exit_userref, fallbacks,
    )
    if got_trade != want_trade:
        raise DriveError(
            "the trade (outcome, qty, entry, exit, entry fee, exit fee, realised, entry "
            f"userref, exit userref, fallbacks) is {got_trade}; recomputed it is {want_trade}"
        )
    if equity:
        start = Decimal(str(drive.config.get("paper.starting_balances")["USD"]))
        cash = start - entry.qty * entry.limit - entry_fee + exit_qty * exit_price - exit_fee
        last = drive.run_equity()[-1]
        got_equity = (
            last.ts, last.cash, last.positions_value, last.equity,
            last.open_position_count, last.realised_pnl_cum,
        )
        want_equity = (_micros(exit_at), cash, Decimal(0), cash, 0, realised)
        if got_equity != want_equity:
            raise DriveError(
                "the exit tick's equity row (ts, cash, positions value, equity, open "
                f"positions, realised to date) is {got_equity}; recomputed from the opening "
                f"{start} it is {want_equity}"
            )
    requests = [
        (r.side.value, r.order_type.value, r.post_only, int(r.userref), r.qty)
        for r in drive.broker.requests
    ]
    wanted = [
        ("buy", "limit", True, entry.userref, entry.qty),
        ("sell", "market", False, exit_userref, exit_qty),
    ]
    if requests != wanted:
        raise DriveError(
            f"the broker was asked for {requests}; one post-only buy and one market sell "
            f"were expected: {wanted}"
        )
    return Closed(
        exit_price=exit_price,
        exit_qty=exit_qty,
        entry_fee=entry_fee,
        exit_fee=exit_fee,
        realised=realised,
    )


def _lot_decimals(state: dict[str, Any], pair: str) -> int:
    return int(state["exchange"]["pair_rules"]["pairs"][pair]["lot_decimals"])


def _drive_prelude(
    ctx: VerifyContext, leg: str = ""
) -> tuple[tuple[str, dict[str, Any], Any, FillSubjectModel] | None, Outcome | None]:
    """The tier sentence, the tools, polars and the trained subject, or the PENDING.

    Called inside `root_import_path`. The order is the order the PENDING lines name
    things in: the harness, then Phase 6's engines by number, then the broker, then the
    trained subject.
    """
    tier, problem = _tier_sentence(3)
    if tier is None:
        return None, _awaiting(problem, "at fee tier 3", leg)
    tools, problem = _drive_tools()
    if tools is None:
        return None, _awaiting(problem, tier, leg)
    polars, problem = _polars()
    if polars is None:
        return None, _awaiting(problem, tier, leg)
    subject, problem = _fill_subject_model(ctx)
    if subject is None:
        return None, _awaiting(problem, tier, leg)
    try:
        registry = parse_engine_registry(ctx.root)
    except (OSError, ValueError) as exc:
        return None, failed(f"the engine registry table cannot be read: {exc}; {tier}")
    # The gates the registry table declares, which `_entry` compares with the gates the
    # registered chains hold. Judging "every registered gate ran" against the chains alone
    # cannot see a gate that was never registered.
    tools = {**tools, "table_gates": sorted(row.name for row in registry.values() if row.is_gate)}
    return (tier, tools, polars, subject), None


def _driven_verdict(
    ctx: VerifyContext,
    body: Callable[[str, dict[str, Any], Any, FillSubjectModel], str],
    *,
    leg: str = "",
    what: str,
) -> Outcome:
    """Run `body` and turn its sentence into a PASS, or its `DriveError` into a FAIL.

    Both carry the tier sentence, because every one of these drives ran at fee tier 3.
    """
    with root_import_path(ctx.root):
        ready, problem = _drive_prelude(ctx, leg)
        if ready is None:
            assert problem is not None
            return problem
        tier, tools, polars, subject = ready
        _regime_begin()
        try:
            return passed(body(tier, tools, polars, subject) + "; " + _run_regime(tier))
        except DriveError as failure:
            return failed(f"{what}: {failure}; {_run_regime(tier)}")


# --- paper_trade_round_trip_target / _stop / _timeout ----------------------- #


@dataclass(frozen=True)
class Exited:
    """How a position was taken out on its barrier, and what the tick published."""

    exit_at: int
    book_bid: Decimal
    watched: int
    touch: str
    state: dict[str, Any]


def _trigger_exit(drive: Drive, entry: Entry, filled: Filled, leg: str) -> Exited:
    """Watch the position, reach the `leg` barrier, and check engines 21 and 22 took it.

    **The timeout leg is watched minute by minute for its first decision bar, then once a
    bar**, and its exit tick lands on `timeout_at` itself. Every tick of the horizon, 720 of
    them, cost 436 s on this machine, and this criterion runs three times in one gate (the
    report, the real-tree test and a mutation arm), which would push `toolchain_green`'s
    pytest toward its bound. A bar-close tick runs the whole chain, so the coarser cadence
    still watches the position on every tick where anything could decide to act on it.
    """
    tick_s, bar_s = drive.tick_s, drive.interval_s
    if leg == "timeout":
        exit_at = filled.timeout_at
        first_bar = filled.filled_at + bar_s
        watched = _watch(
            drive, filled, start=filled.filled_at + tick_s, until=first_bar, every=tick_s
        )
        watched += _watch(drive, filled, start=first_bar, until=exit_at, every=bar_s)
        book_bid = drive.bid
        touch = f"the clock reached its timeout at {exit_at} with neither barrier traded"
        printed = None
    else:
        exit_at = filled.filled_at + (WATCH_MINUTES + 1) * tick_s
        watched = _watch(
            drive, filled, start=filled.filled_at + tick_s, until=exit_at, every=tick_s
        )
        barrier = filled.target if leg == "target" else filled.stop
        printed = barrier + TOUCH_PAST if leg == "target" else barrier - TOUCH_PAST
        book_bid = printed.quantize(Decimal("0.001"), rounding=ROUND_DOWN)
        drive.market.plant_trade(
            entry.pair,
            at=datetime.fromtimestamp(exit_at - tick_s // 2, tz=UTC),
            price=str(printed),
        )
        drive.pin(book_bid, pairs=(entry.pair,))
        touch = f"a trade at {printed} crossed the {leg} {barrier} the minute before {exit_at}"
    state = drive.tick(exit_at)
    if state.get("guard_blockers"):
        raise DriveError(f"the exit tick was guard-blocked: {state['guard_blockers']}")
    manager = state.get("position_manager") or {}
    wanted = [{"position_id": filled.position_id, "barrier": leg}]
    if manager.get("triggered") != wanted:
        raise DriveError(
            f"engine 21 triggered {manager.get('triggered')} on the exit tick, not {wanted}"
        )
    if printed is not None:
        traded = state["market_sensor"]["trade_ranges"].get(entry.pair) or {}
        side = "high" if leg == "target" else "low"
        if Decimal(str(traded.get(side))) != printed:
            raise DriveError(
                f"engine 3's trade range {side} is {traded.get(side)}, not the planted {printed}"
            )
    exiting = state.get("exit") or {}
    if exiting.get("positions_closed") is not True:
        raise DriveError(f"engine 22 closed nothing: {exiting.get('reason_code')!r}")
    return Exited(exit_at=exit_at, book_bid=book_bid, watched=watched, touch=touch, state=state)


def _round_trip_body(leg: str) -> Callable[[str, dict[str, Any], Any, FillSubjectModel], str]:
    def body(tier: str, tools: dict[str, Any], polars: Any, subject: FillSubjectModel) -> str:
        del tier
        with _driven(tools, subject, polars) as drive:
            _warm_up(drive)
            entry, entry_state = _entry(drive)
            filled, _ = _fill(drive, entry)
            exited = _trigger_exit(drive, entry, filled, leg)
            closed = _reconcile(
                drive, entry, filled, exit_at=exited.exit_at, book_bid=exited.book_bid,
                outcome=leg, lot_decimals=_lot_decimals(entry_state, entry.pair),
                fallbacks=(), equity=True,
            )
        return (
            f"{entry.pair} entry {entry.userref}: a post-only buy of {entry.qty} at "
            f"{entry.limit}, placed on the bar close past all {len(entry.gates)} registered "
            f"gates ({', '.join(entry.gates)}), filled at its limit on the next tick, "
            f"watched for {exited.watched} ticks, then {exited.touch}; it exited at the "
            f"{leg} when engine 22 sold {closed.exit_qty} as a taker at "
            f"{closed.exit_price}. Entry fee {closed.entry_fee}, exit fee {closed.exit_fee} "
            f"and realised {closed.realised} were recomputed from the pinned book and "
            "engine 1's fee tier, and the orders, positions, trades and equity rows engine "
            "19 wrote match them exactly"
        )

    return body


def _round_trip(ctx: VerifyContext, leg: str) -> Outcome:
    """One paper round trip that ends at the named barrier, reconciled to the cent.

    The three criteria differ only in which barrier the scripted market reaches, and
    they are one function because the reconciliation is the assertion in all three:
    every row engine 19 wrote is read back and compared against the trade recomputed
    from the market the criterion scripted - entry, exit, fees and realised PnL,
    exactly, with no tolerance. A tolerance on money is a defect waiting for a rounding
    bug to hide in.

    Why all three rather than one. `target` and `stop` differ by which barrier the
    scripted trades touch; `timeout` never touches either and is the path where nothing
    triggers the exit except elapsed time, which is the only one of the three a broken
    clock comparison can break while the other two stay green.
    """
    return _driven_verdict(
        ctx, _round_trip_body(leg), leg=leg, what=f"the {leg} round trip"
    )


# --- unfilled_entry_cancels_without_chasing --------------------------------- #


def _unfilled_body(tier: str, tools: dict[str, Any], polars: Any, subject: FillSubjectModel) -> str:
    del tier
    with _driven(tools, subject, polars) as drive:
        _warm_up(drive)
        entry, _ = _entry(drive)
        window_s = int(drive.config.get("trading.entry_unfilled_window_s"))
        next_bar = drive.last_bar_ts + 2 * drive.interval_s
        cancelled_at: int | None = None
        ticks = 0
        at = drive.entry_at + drive.tick_s
        while at < next_bar:
            state = drive.tick(at)
            ticks += 1
            if state.get("guard_blockers") or "execution" in state:
                raise DriveError(
                    f"the tick at {at} was guard-blocked or ran the opportunity chain "
                    "before the next bar closed"
                )
            rows = (state.get("position_manager") or {}).get("orders") or []
            elapsed_us = _micros(at) - entry.placed_at
            due = elapsed_us >= _micros(window_s)
            if cancelled_at is None and rows and not due:
                raise DriveError(
                    f"engine 21 acted on the entry {elapsed_us // 1_000_000}s after placement, "
                    f"inside its {window_s}s window: {rows}"
                )
            if cancelled_at is None and due:
                shape = [(row.get("userref"), row.get("status")) for row in rows]
                if shape != [(entry.userref, "cancelled")]:
                    raise DriveError(
                        f"on the first tick at its {window_s}s window engine 21 published "
                        f"{shape}, not the entry cancelled"
                    )
                cancelled_at = at
            elif cancelled_at is not None and rows:
                raise DriveError(f"engine 21 acted again at {at}, after the cancel: {rows}")
            at += drive.tick_s
        if cancelled_at is None:
            raise DriveError(
                f"the entry was never cancelled across {ticks} ticks; its window is {window_s}s"
            )
        stored = drive.store.order_by_userref(entry.userref)
        if (
            stored is None
            or stored.status.value != "cancelled"
            or stored.closed_at != _micros(cancelled_at)
            or stored.filled_qty != 0
        ):
            raise DriveError(
                f"entry {entry.userref} is stored as "
                f"{None if stored is None else (stored.status.value, stored.closed_at, stored.filled_qty)}, "
                f"not cancelled unfilled at {_micros(cancelled_at)}"
            )
        requests = [
            (r.side.value, r.order_type.value, r.post_only, int(r.userref))
            for r in drive.broker.requests
        ]
        if requests != [("buy", "limit", True, entry.userref)]:
            raise DriveError(
                f"the broker was asked for {requests}; the entry alone was expected, and any "
                "second order is a chase (invariant 8)"
            )
        if drive.broker.cancels != [entry.userref]:
            raise DriveError(f"the broker was asked to cancel {drive.broker.cancels}")
        open_now = drive.open_orders()
        userrefs = [
            int(row[0])
            for row in drive.store.connection.execute("SELECT userref FROM orders").fetchall()
        ]
        if open_now or userrefs != [entry.userref] or drive.position_ids():
            raise DriveError(
                f"after the cancel the broker holds {len(open_now)} open order(s), the store "
                f"{userrefs} and positions {drive.position_ids()}"
            )
    return (
        f"{entry.pair} entry {entry.userref}, a post-only buy of {entry.qty} at "
        f"{entry.limit}, rested with nothing trading below it and was cancelled "
        f"{(_micros(cancelled_at) - entry.placed_at) // 1_000_000}s after placement, on the "
        f"first minute tick at trading.entry_unfilled_window_s ({window_s}s) and not "
        f"before. Across {ticks} ticks to the next bar close the broker was asked for that "
        "one order and that one cancel and nothing else - no market order and no second "
        "entry - and afterwards nothing is open at the broker or in the store"
    )


# --- triggered_stop_holds_on_data_guard_block ------------------------------- #


def _held_stop_body(tier: str, tools: dict[str, Any], polars: Any, subject: FillSubjectModel) -> str:
    del tier
    manager_contracts, guard = tools["manager"], tools["guard"]
    hold = str(manager_contracts.HOLD_DATA_GUARD_BLOCKED)
    with _driven(tools, subject, polars) as drive:
        _warm_up(drive)
        entry, entry_state = _entry(drive)
        filled, _ = _fill(drive, entry)
        pair = entry.pair
        held_at = filled.filled_at + drive.tick_s
        printed = filled.stop - TOUCH_PAST
        quoted = (filled.stop - Decimal("0.4")).quantize(Decimal("0.001"))
        book_bid = (filled.stop - Decimal("0.7")).quantize(Decimal("0.001"))
        drive.market.plant_trade(
            pair, at=datetime.fromtimestamp(held_at - drive.tick_s // 2, tz=UTC), price=str(printed)
        )
        drive.cross(pair, quoted=quoted, book_bid=book_bid)
        held = drive.tick(held_at)

        if held.get("trading_blocked_by") != "data_guard":
            raise DriveError(
                f"the crossed quote did not block the tick on data_guard: "
                f"{held.get('trading_blocked_by')!r}"
            )
        if (held.get("data_guard") or {}).get("reason_code") != guard.REASON_NEGATIVE_SPREAD:
            raise DriveError(f"engine 4 blocked for {held['data_guard'].get('reason_code')!r}")
        low = Decimal(str(held["market_sensor"]["trade_ranges"][pair]["low"]))
        if low > filled.stop:
            raise DriveError(f"no stop was touched (low {low}, stop {filled.stop}), so nothing was held")
        manager = held.get("position_manager") or {}
        if manager.get("triggered") != [] or manager.get("hold_reason") != hold:
            raise DriveError(
                f"engine 21 triggered {manager.get('triggered')} and published hold_reason "
                f"{manager.get('hold_reason')!r} on a tick data_guard blocked; the hold is no "
                f"trigger and {hold!r}"
            )
        exiting = held.get("exit") or {}
        stored = drive.store.position(filled.position_id)
        if (
            exiting.get("orders")
            or exiting.get("positions_closed") is not False
            or drive.orders_with_intent("exit")
            or any(r.side.value == "sell" for r in drive.broker.requests)
        ):
            raise DriveError(
                f"an exit was placed on the held tick: engine 22 said {exiting.get('reason_code')!r}, "
                f"the broker was asked for {[r.order_type.value for r in drive.broker.requests]}"
            )
        if stored is None or stored.status.value != "open" or stored.hold_reason != hold:
            raise DriveError(
                f"engine 19 stored the held position as "
                f"{None if stored is None else (stored.status.value, stored.hold_reason)}, not open "
                f"with hold_reason {hold!r}"
            )

        drive.command("close_all")
        closed_at = held_at + drive.tick_s
        liquidated = drive.tick(closed_at)
        if liquidated.get("trading_blocked_by") != "data_guard":
            raise DriveError("data_guard was no longer blocking when close_intent was applied")
        manager = liquidated.get("position_manager") or {}
        if manager.get("hold_reason") is not None:
            raise DriveError(
                f"engine 21 still held during the liquidation: {manager.get('hold_reason')!r}"
            )
        if (liquidated.get("exit") or {}).get("positions_closed") is not True:
            raise DriveError(
                f"with close_intent set the held position was not sold: "
                f"{(liquidated.get('exit') or {}).get('reason_code')!r}"
            )
        closed = _reconcile(
            drive, entry, filled, exit_at=closed_at, book_bid=book_bid, outcome="liquidation",
            lot_decimals=_lot_decimals(entry_state, pair), fallbacks=(), equity=True,
        )
        after = drive.store.position(filled.position_id)
        if after is None or after.hold_reason is not None:
            raise DriveError("the closed position still carries a hold_reason")
        _close_all_consumed(drive, source="console", at=closed_at)
    return (
        f"{pair} position {filled.position_id}: a trade at {printed} touched the stop "
        f"{filled.stop} on a tick engine 4 blocked for a crossed quote, and engines 21 and "
        f"22 placed no exit - no trigger, no order at the broker - with hold_reason "
        f"{hold!r} published and stored on the position. The operator's close_all on the "
        f"next tick, with data_guard still blocking, sold the same position as a taker at "
        f"{closed.exit_price} (outcome liquidation, realised {closed.realised}, every row "
        "reconciled), cleared the hold, and the orchestrator cleared close_intent and "
        "consumed the command"
    )


def _close_all_consumed(drive: Drive, *, source: str, at: int) -> dict[str, Any]:
    """The one `close_all` row from `source`, claimed or created earlier and consumed at
    `at`, with the orchestrator frozen and `close_intent` cleared."""
    rows = [
        row for row in drive.command_rows()
        if row["command"] == "close_all" and row["source"] == source
    ]
    system = drive.orchestrator.system
    if len(rows) != 1 or rows[0]["consumed_at"] != _micros(at):
        raise DriveError(
            f"the {source} close_all rows are {rows}; one, consumed at {_micros(at)}, was expected"
        )
    if system.get("close_intent") is not False or system.get("mode") != "frozen":
        raise DriveError(f"after the liquidation the orchestrator holds {system}")
    return rows[0]


# --- escalation_completes_during_outage ------------------------------------- #


def _outage_held(state: dict[str, Any], guard: Any, at: int) -> str:
    """Engine 4 is the primary blocker on a negative spread, and the balance and
    `AssetPairs` fetches both failed. Returns engine 1's reason for the balance."""
    if state.get("trading_blocked_by") != "data_guard" or (
        (state.get("data_guard") or {}).get("reason_code") != guard.REASON_NEGATIVE_SPREAD
    ):
        raise DriveError(
            f"at {at} the primary blocker is {state.get('trading_blocked_by')!r}, not data_guard "
            "on the crossed quote"
        )
    exchange = state.get("exchange") or {}
    failures = {row.get("call"): row.get("reason") for row in exchange.get("failed_fetches") or []}
    if exchange.get("balances") is not None or not {"balance", "asset_pairs"} <= set(failures):
        raise DriveError(
            f"at {at} engine 1 published balances {exchange.get('balances')!r} and failed "
            f"fetches {sorted(failures)}; the outage needs both balance and asset_pairs failing"
        )
    return str(failures["balance"])


def _fail_the_outage(drive: Drive) -> None:
    """The balance and `AssetPairs` calls fail at the transport, as in an outage.

    In paper mode the broker never makes the real `Balance` call, so failing it changes
    nothing on its own. The paper ledger is what fails: it cannot tell which currency a
    fill spent without `AssetPairs`, so `balance()` raises and engine 1 records the
    balance as a failed fetch. The fee tier keeps answering, because a liquidation that
    cannot price its fill is not completable by design (engine 22, spec 93).
    """
    drive.market.fail("balance")
    drive.market.fail("asset_pairs")


def _escalation_positions(drive: Drive) -> str:
    tools = drive.tools
    guard, exits = tools["guard"], tools["exit"]
    _warm_up(drive)
    entry, entry_state = _entry(drive)
    filled, _ = _fill(drive, entry)
    limit = int(drive.config.get("safety.max_consecutive_data_blocks"))
    book_bid = (drive.bid - Decimal("0.2")).quantize(Decimal("0.001"))
    drive.cross(entry.pair, quoted=drive.bid, book_bid=book_bid)
    _fail_the_outage(drive)
    equity_rows = len(drive.run_equity())

    at = filled.filled_at
    balance_reason = ""
    for blocked in range(1, limit + 2):
        at += drive.tick_s
        state = drive.tick(at)
        balance_reason = _outage_held(state, guard, at)
        escalations = [
            row for row in drive.command_rows()
            if row["command"] == "close_all" and row["source"] == "safety"
        ]
        if blocked <= limit and escalations:
            raise DriveError(
                f"engine 17 escalated after {blocked} blocked ticks; the limit is {limit} and "
                "it escalates on the tick after it, not before"
            )
        if [p.position_id for p in drive.store.open_positions()] != [filled.position_id]:
            raise DriveError(f"the position did not stay open and held at blocked tick {blocked}")
    if len(escalations) != 1 or escalations[0]["created_at"] != _micros(at):
        raise DriveError(
            f"on blocked tick {limit + 1} engine 17 wrote {escalations}; one close_all at "
            f"{_micros(at)} was expected"
        )
    escalated_at = at
    at += drive.tick_s
    state = drive.tick(at)
    _outage_held(state, guard, at)
    manager, exiting = state.get("position_manager") or {}, state.get("exit") or {}
    if manager.get("hold_reason") is not None or exiting.get("positions_closed") is not True:
        raise DriveError(
            f"the liquidation did not complete during the outage: engine 21 held "
            f"{manager.get('hold_reason')!r}, engine 22 said {exiting.get('reason_code')!r}"
        )
    if manager.get("entry_orders_cancelled") is not True:
        raise DriveError("engine 21 did not report every entry cancelled")
    fallback = str(exits.FALLBACK_ASSET_PAIRS_RETAINED)
    closed = _reconcile(
        drive, entry, filled, exit_at=at, book_bid=book_bid, outcome="liquidation",
        lot_decimals=_lot_decimals(entry_state, entry.pair), fallbacks=(fallback,),
        equity=False,
    )
    if len(drive.run_equity()) != equity_rows:
        raise DriveError(
            "engine 19 wrote an equity row while the balance was unknown; with no balance "
            "there is no equity to write, and invariant 2 has no fallback"
        )
    _close_all_consumed(drive, source="safety", at=at)
    if drive.open_orders():
        raise DriveError("an order is still open at the broker after the liquidation")
    return (
        f"engine 4 blocked {limit + 1} consecutive minute ticks on a crossed quote while "
        f"the balance and AssetPairs fetches failed (engine 1: {balance_reason}); engine 17 "
        f"wrote close_all on blocked tick {limit + 1} ({escalated_at}) and not before "
        f"(safety.max_consecutive_data_blocks {limit}); on the next tick, still blocked and "
        f"still failing, engine 22 sold {filled.position_id} as a taker at "
        f"{closed.exit_price} using the retained AssetPairs past its TTL "
        f"(fallbacks_used [{fallback}], realised {closed.realised}, every row reconciled), "
        "engine 19 wrote no equity row while the balance was unknown, and the orchestrator "
        "cleared close_intent and consumed engine 17's command"
    )


def _escalation_entry(drive: Drive, *, unreachable: str) -> str:
    guard = drive.tools["guard"]
    _warm_up(drive)
    entry, _ = _entry(drive)
    window_s = int(drive.config.get("trading.entry_unfilled_window_s"))
    at = drive.entry_at + drive.tick_s
    elapsed_s = (_micros(at) - entry.placed_at) // 1_000_000
    if elapsed_s >= window_s:
        raise DriveError(
            f"the close_all tick is {elapsed_s}s after placement, not inside the {window_s}s "
            "window, so a cancel there could not be told from the window's"
        )
    drive.cross(entry.pair, quoted=drive.bid, book_bid=drive.bid)
    _fail_the_outage(drive)
    drive.command("close_all")
    state = drive.tick(at)
    _outage_held(state, guard, at)
    manager, exiting = state.get("position_manager") or {}, state.get("exit") or {}
    rows = [
        (row.get("userref"), row.get("status"), row.get("closed_at"))
        for row in manager.get("orders") or []
    ]
    if rows != [(entry.userref, "cancelled", _micros(at))]:
        raise DriveError(
            f"with close_intent set {elapsed_s}s into a {window_s}s window engine 21 "
            f"published {rows}, not the entry cancelled at {_micros(at)}"
        )
    if manager.get("entry_orders_cancelled") is not True or exiting.get("positions_closed") is not True:
        raise DriveError(
            f"engine 21 reported entry_orders_cancelled {manager.get('entry_orders_cancelled')!r} "
            f"and engine 22 positions_closed {exiting.get('positions_closed')!r}"
        )
    if drive.broker.cancels != [entry.userref]:
        raise DriveError(f"the broker was asked to cancel {drive.broker.cancels}")
    stored = drive.store.order_by_userref(entry.userref)
    if stored is None or stored.status.value != "cancelled" or stored.closed_at != _micros(at):
        raise DriveError(f"entry {entry.userref} is not stored cancelled at {_micros(at)}")
    escalations = [row for row in drive.command_rows() if row["source"] == "safety"]
    if escalations:
        raise DriveError(f"engine 17 wrote {escalations}; this cancel must be the operator's")
    _close_all_consumed(drive, source="console", at=at)
    if drive.open_orders() or drive.position_ids():
        raise DriveError("something is still open after the operator's close_all")
    return (
        f"{unreachable} - so the cancel path is proven through an operator close_all: "
        f"entry {entry.userref}, placed {elapsed_s}s earlier and inside its {window_s}s "
        "window, was cancelled at the broker on the close_all tick while data_guard blocked "
        "and the same two fetches failed, engine 17 wrote nothing, and the command was "
        "consumed on that tick"
    )


def _escalation_body(
    tier: str, tools: dict[str, Any], polars: Any, subject: FillSubjectModel
) -> str:
    del tier
    config = _drive_config(tools, subject)
    window_s = int(config.get("trading.entry_unfilled_window_s"))
    limit = int(config.get("safety.max_consecutive_data_blocks"))
    tick_s = int(config.get("timeframes.loop_tick_s"))
    if window_s < (limit + 1) * tick_s:
        unreachable = (
            "a resting entry: at the committed config a safety escalation can never find "
            f"one, because trading.entry_unfilled_window_s ({window_s}s) is shorter than the "
            f"{limit + 1} blocked ticks of {tick_s}s it takes to escalate, and engine 21 "
            "cancels a stale entry during the hold"
        )
    else:
        unreachable = (
            f"a resting entry: at this config ({window_s}s window, {limit + 1} blocked ticks "
            f"of {tick_s}s) an escalation could find one, and this criterion still proves "
            "the cancel through the operator's close_all only"
        )
    with _driven(tools, subject, polars) as drive:
        positions = _escalation_positions(drive)
    with _driven(tools, subject, polars) as drive:
        entries = _escalation_entry(drive, unreachable=unreachable)
    return "Positions: " + positions + ". Resting entries: " + entries


# --- console_shows_position_live -------------------------------------------- #

#: What spec 101 adds that this criterion waits for. A proposal for C's own spec 101,
#: written here so the PENDING says what "the console part exists" means.
CONSOLE_LIVE_CONTRACT: Final = (
    "expected acsoe.console.views.PositionView to carry `hold_reason` (rendered through "
    "REASON_PROSE, spec 101 step 3), and the criterion then to drive a real position "
    "through engines 18, 21 and 19 and read it back through the console reader"
)

#: How far the mark is moved between the two reads, as a fraction of the fill price.
#:
#: A fraction and not a number of ticks, because the point is only that it **moves** and
#: the pair's own price scale is not this file's to know. Small enough that neither
#: barrier is reached - a triggered exit would close the position out from under the
#: second read - and large enough to survive rounding onto the pair's grid.
CONSOLE_MARK_STEP: Final = Decimal("0.004")


def _console_reader(drive: Drive) -> Any:
    """A `ConsoleReader` on the daemon's own database, with the daemon's own clock.

    The **same** clock object, not a copy. The console is a separate process and its
    clock is the only time it has, so a criterion that gave it a second clock would be
    measuring the gap between two fixtures rather than what the operator sees; and a
    staleness assertion against a clock that drifts from the daemon's is a race.
    """
    cls, problem = _symbol("acsoe.console.reader", "ConsoleReader")
    if cls is None:
        raise DriveError(f"the console reader is not importable: {problem}")
    stale_after_ms = int(drive.config.get("console.stale_after_ms"))
    return cls(Path(drive.store.db_path), clock=drive.clock, stale_after_ms=stale_after_ms)


def _console_position(drive: Drive, position_id: str) -> Any:
    """The one open-positions row the console would render for `position_id`."""
    reader = _console_reader(drive)
    try:
        views = reader.positions()
    finally:
        reader.close()
    found = [view for view in views if str(view.position_id) == position_id]
    if len(found) != 1:
        raise DriveError(
            f"the console's open-positions region holds {len(views)} row(s) and "
            f"{len(found)} of them is {position_id}; engine 19 stored one open position"
        )
    return found[0]


def _console_refuses_a_write(drive: Drive) -> str:
    """The console's connection refuses an `UPDATE` on the daemon's live database.

    Spec 101's scope limit is "the console places no order", and `ui-context.md` puts it
    more strongly: the console holds no credentials and can never place one. The narrow
    structural half of that is asserted here by **attempting** a write and requiring
    SQLite to refuse it - a guard that has never been shown to fire is not a guard - and
    the broader half, that nothing reached the broker, is asserted by the caller.
    """
    reader = _console_reader(drive)
    try:
        connection = reader.store.connection
        try:
            connection.execute("UPDATE positions SET last_price = '1'")
        except sqlite3.OperationalError as refused:
            return str(refused)
        raise DriveError(
            "the console's connection accepted an UPDATE on the daemon's positions table; "
            "it is opened read-only precisely so this cannot depend on anyone's discipline"
        )
    finally:
        reader.close()


#: U+2212, the minus sign `ui-context.md` rule 6 requires. Built with `chr` rather
#: than typed, so an editor that helpfully normalised the character into an ASCII
#: hyphen would turn this file's own assertions into hyphen assertions - which is the
#: exact defect rule 6 exists to catch, arriving through the check rather than the code.
CONSOLE_MINUS: Final = chr(0x2212)


def _decimal_places(text: str) -> int:
    """How many digits a rendered figure carries after the point."""
    head, _, tail = text.partition(".")
    del head
    return len(tail)


def _console_number_rules(view: Any, *, pair_decimals: int, negative: bool) -> list[str]:
    """`ui-context.md`'s number rules, on the row the operator is actually looking at.

    Returns the violations. **Only the rules a live position can demonstrate** are here:
    tabular figures are CSS and are held page-wide by `console_tabular_figures`, the
    palette by `console_tokens_no_raw_hex`, and the focus ring and reduced motion by
    `console_focus_and_reduced_motion` - all three Phase 1 criteria that run in this same
    gate. Re-implementing them here would be a second, weaker copy of a check that
    already exists.

    **Rule 4's other half is reported, not judged.** The operator amended the rule on
    2026-09-18: an order price renders at the precision it was stored at, and a derived
    threshold at the precision it was computed to, unrounded by design. The entry price is
    the order price and is asserted here; `_console_thresholds` reports the derived ones,
    and `_console_mark_precision` measures the mark, which is a third case and says why it
    cannot stand behind its own number.
    """
    problems: list[str] = []

    # Rule 2. Explicitly signed, always, including a flat position: a bare `0.00%` in a
    # column of signed figures reads as a missing value rather than a flat one.
    if not view.unrealised_pnl_pct_text.startswith(("+", CONSOLE_MINUS)):
        problems.append(
            f"the unrealised percentage renders {view.unrealised_pnl_pct_text!r}, which "
            "carries no explicit sign"
        )

    # Rule 6. A proper minus sign, never a hyphen - a hyphen is narrower than a digit and
    # breaks the tabular alignment the whole column depends on.
    for label, text in (
        ("unrealised PnL", view.unrealised_pnl_text),
        ("unrealised percentage", view.unrealised_pnl_pct_text),
    ):
        if "-" in text:
            problems.append(f"the {label} renders {text!r}, with an ASCII hyphen in it")
        if negative and not text.startswith(CONSOLE_MINUS):
            problems.append(
                f"the {label} renders {text!r} on a position that is down; rule 3 says the "
                "sign carries the meaning and the colour only reinforces it"
            )
    if negative and view.direction != "neg":
        problems.append(
            f"the row's direction is {view.direction!r} on a position that is down, so the "
            "colour and the sign disagree"
        )

    # Rule 4, on the one figure that is settled. Engine 18 quantizes the entry onto the
    # pair's own grid before it places the order - `_entry` above recomputes that and
    # refuses anything else - so the console rendering it at any other precision is the
    # console losing or inventing a digit, and that is a FAIL rather than a question.
    if _decimal_places(view.entry_price_text) != pair_decimals:
        problems.append(
            f"the entry price renders {view.entry_price_text!r}, which is "
            f"{_decimal_places(view.entry_price_text)} decimal places where engine 18 "
            f"placed it on this pair's {pair_decimals}-decimal grid"
        )
    return problems


def _console_thresholds(view: Any, *, pair_decimals: int) -> list[str]:
    """The derived figures and the precision they render at. **Not a breach.**

    `ui-context.md` rule 4, **as the operator amended it on 2026-09-18**: an *order price*
    renders at the precision it was stored at, because its writer rounded it to the
    exchange's grid before sending it; a *derived threshold* renders at the precision it
    was computed to, **and the console does not round it.** Rule 4 is a rule about
    writers, and the console has never been able to obey the older wording - it reads only
    the store, and the store holds no pair rules.

    So these three are reported as what they are rather than as a finding. The target and
    the stop are `entry * (1 +/- pct)` from engine 21; the unrealised PnL is
    `qty * (mark - entry)`. Rounding them at write time was available - engine 21 holds
    `pair_rules` at the line where it writes the row - and was **rejected**, because
    `research/labelling.py` computes its barriers the same unrounded way, so rounding the
    live ones would make the system trigger on barriers the training labels were never
    built from. And `stop_price` *is* the trigger engine 21 compares the traded low
    against, so a rounded rendering would show the operator a number that is not the
    threshold.

    The one figure rule 4 still governs here is the **entry price**, and
    `_console_number_rules` asserts it as a FAIL.
    """
    return [
        f"{label} {text!r} ({_decimal_places(text)}dp)"
        for label, text in (
            ("target", view.target_price_text),
            ("stop", view.stop_price_text),
            ("unrealised", view.unrealised_pnl_text),
        )
        if _decimal_places(text) > pair_decimals
    ]


def _console_mark_precision(view: Any, *, pair_decimals: int) -> str:
    """The mark's precision against the pair's grid. **A measurement this criterion cannot
    stand behind, and it says so.**

    The mark is not a derived threshold: it is an exchange-supplied bid passed through
    unchanged, so it should already sit on the grid, and a mark rendering more digits than
    `pair_decimals` would be engine 3 publishing a bid off it - A's lane, and a finding of
    its own rather than part of the 2026-09-18 amendment.

    **But this criterion pins the bid it then measures.** `drive.pin` sets the quote, so
    on this one figure the criterion is judging its own harness, and an assertion about a
    value the test itself supplied proves nothing about that value. That shape is on the
    record deliberately - it is the same defect as a double that agrees with its caller,
    arriving through a *fixture* rather than through a stub.

    The independent measurement belongs to the recorded archive and not here: every price
    in `tests/fixtures/book_sample.jsonl` is a Kraken v2 book frame copied byte-for-byte
    out of `data/raw/`, and BTC/USD's own `pair_decimals` sits in the recorded
    `AssetPairs` beside it. Measured by hand for spec 101 and reported to the lead - 783
    recorded BTC/USD prices, every one at exactly 1 decimal place, which is that pair's
    `pair_decimals`. The exchange is on its grid, so the digits below are this harness's.
    That check is **not** added here on purpose: a criterion named
    `console_shows_position_live` has no business asserting Kraken's price grid, and
    `order_book_slippage_on_recorded_book` already reads that fixture in A's own area.
    """
    places = _decimal_places(view.last_price_text)
    if places <= pair_decimals:
        return (
            f"The mark renders {view.last_price_text!r}, on this pair's "
            f"{pair_decimals}-decimal grid"
        )
    return (
        f"The mark renders {view.last_price_text!r} ({places}dp) where AssetPairs gives "
        f"this pair {pair_decimals} - NOT a verdict on engine 3: this criterion pinned "
        "that bid itself, so here it measures its own harness. The archive says the "
        "exchange is on the grid (783 recorded BTC/USD book prices, all 1dp)"
    )


def _console_position_body(
    tier: str, tools: dict[str, Any], polars: Any, subject: FillSubjectModel
) -> str:
    """Spec 101. A position a real daemon opened, read back through the console.

    Four reads of the same position, and each one is a different claim:

    1. **After the fill** - the region renders at all, on a row engine 19 wrote from
       engine 21's payload rather than on a seeded one.
    2. **After a second tick at a moved mark** - the region is *live*. The move is
       recomputed here from the price this criterion pinned, so a reader serving the
       previous tick's figure cannot satisfy it by being consistent with itself. That is
       the FAIL arm spec 101 names.
    3. **With the console's clock past `console.stale_after_ms`** - rule 5. Both readings
       are taken: a staleness check that only ever observes `True` is satisfied by a
       reader that fades everything permanently.
    4. **On a tick engine 4 blocked** - the hold, as operator prose and never as a code.

    Throughout: nothing the console did reached the broker, and its connection refuses a
    write to the daemon's own database.
    """
    del tier
    manager_contracts, guard = tools["manager"], tools["guard"]
    hold = str(manager_contracts.HOLD_DATA_GUARD_BLOCKED)
    prose_map, problem = _symbol("acsoe.console.format", "REASON_PROSE")
    if prose_map is None:
        raise DriveError(f"the console's reason map is not importable: {problem}")

    with _driven(tools, subject, polars) as drive:
        _warm_up(drive)
        entry, entry_state = _entry(drive)
        filled, _ = _fill(drive, entry)
        pair = entry.pair
        pair_decimals = int(entry_state["exchange"]["pair_rules"]["pairs"][pair]["pair_decimals"])
        placed = len(drive.broker.requests)

        # 1. The fill tick.
        first = _console_position(drive, filled.position_id)
        if first.last_price != entry.limit:
            raise DriveError(
                f"the console shows the mark as {first.last_price}, and the position was "
                f"filled at {entry.limit}; on the fill tick the mark is the fill price"
            )
        if first.hold_reason is not None:
            raise DriveError(
                f"the console shows a hold of {first.hold_reason!r} on a tick nothing blocked"
            )

        # 2. A second tick, at a mark this criterion moved.
        grid = Decimal(1).scaleb(-pair_decimals)
        moved = (entry.limit * (1 + CONSOLE_MARK_STEP)).quantize(grid, rounding=ROUND_DOWN)
        if moved == entry.limit:
            raise DriveError(
                f"the moved mark {moved} rounds onto the same grid point as the fill "
                f"{entry.limit}, so this drive could not tell a live figure from a frozen one"
            )
        drive.pin(moved)
        at = filled.filled_at + drive.tick_s
        state = drive.tick(at)
        if "trading_blocked_by" in state:
            raise DriveError(f"the second tick was blocked by {state['trading_blocked_by']}")
        second = _console_position(drive, filled.position_id)
        if second.last_price != moved:
            raise DriveError(
                f"the console still shows the mark as {second.last_price} after the market "
                f"moved to {moved}; the open-positions region is a snapshot, not live"
            )
        # Recomputed from the market this criterion pinned, never read back. `qty` is the
        # filled quantity and the two marks are both this file's, so a reader that served
        # either tick's figure twice fails this even though it would be self-consistent.
        expected_move = entry.qty * (moved - entry.limit)
        if second.unrealised_pnl - first.unrealised_pnl != expected_move:
            raise DriveError(
                f"the rendered unrealised PnL moved by "
                f"{second.unrealised_pnl - first.unrealised_pnl} when the mark moved from "
                f"{entry.limit} to {moved} on {entry.qty}, which is {expected_move}"
            )
        if second.unrealised_pnl_text == first.unrealised_pnl_text:
            raise DriveError(
                f"both ticks rendered the unrealised PnL as {second.unrealised_pnl_text!r}; "
                "the figure the operator reads did not move even though the value did"
            )

        # 3. Rule 5, from the console's own clock.
        fresh = second.staleness
        stale_after_ms = int(drive.config.get("console.stale_after_ms"))
        if fresh.is_stale:
            raise DriveError(
                f"the console calls a position it was just handed stale (age "
                f"{fresh.age_us}us against {stale_after_ms}ms); every figure on the screen "
                "would sit at half opacity permanently"
            )
        stale = _stale_reading(drive, filled.position_id, stale_after_ms)

        # 4. The hold, on a tick engine 4 blocks.
        held_at = at + drive.tick_s
        printed = filled.stop - TOUCH_PAST
        drive.market.plant_trade(
            pair, at=datetime.fromtimestamp(held_at - drive.tick_s // 2, tz=UTC), price=str(printed)
        )
        drive.cross(
            pair,
            quoted=(filled.stop - Decimal("0.4")).quantize(Decimal("0.001")),
            book_bid=(filled.stop - Decimal("0.7")).quantize(Decimal("0.001")),
        )
        blocked_state = drive.tick(held_at)
        if blocked_state.get("trading_blocked_by") != "data_guard":
            raise DriveError(
                "the crossed quote did not block the tick on data_guard: "
                f"{blocked_state.get('trading_blocked_by')!r}"
            )
        if (blocked_state.get("data_guard") or {}).get("reason_code") != guard.REASON_NEGATIVE_SPREAD:
            raise DriveError(
                f"engine 4 blocked for {(blocked_state.get('data_guard') or {}).get('reason_code')!r}"
            )
        if (blocked_state.get("position_manager") or {}).get("hold_reason") != hold:
            raise DriveError(
                "engine 21 did not hold on a tick data_guard blocked, so there is no hold "
                "for the console to show"
            )
        held = _console_position(drive, filled.position_id)
        if held.hold_reason != hold:
            raise DriveError(
                f"engine 21 published hold_reason {hold!r} and the console shows "
                f"{held.hold_reason!r}"
            )
        expected_prose = prose_map.get(hold)
        if not expected_prose:
            raise DriveError(f"console/format.py has no operator prose for {hold!r}")
        if held.hold_reason_text != expected_prose:
            raise DriveError(
                f"the console renders the hold as {held.hold_reason_text!r}; "
                f"REASON_PROSE[{hold!r}] is {expected_prose!r}"
            )
        if hold in held.hold_reason_text:
            raise DriveError(
                f"the reason code {hold!r} is on the screen inside "
                f"{held.hold_reason_text!r}; a code reaching the operator is a log line"
            )

        # The number rules, on the down tick where the sign has something to carry.
        if held.unrealised_pnl >= 0:
            raise DriveError(
                "the held tick left the position up, so the minus sign and the negative "
                "direction have nothing to demonstrate"
            )
        problems = _console_number_rules(held, pair_decimals=pair_decimals, negative=True)
        problems += _console_number_rules(second, pair_decimals=pair_decimals, negative=False)
        if problems:
            raise DriveError("ui-context.md's number rules: " + "; ".join(problems))
        thresholds = _console_thresholds(held, pair_decimals=pair_decimals)
        mark_precision = _console_mark_precision(held, pair_decimals=pair_decimals)

        # Read-only, throughout. Nothing the console did placed or cancelled anything.
        refusal = _console_refuses_a_write(drive)
        if len(drive.broker.requests) != placed:
            raise DriveError(
                f"the broker saw {len(drive.broker.requests) - placed} further request(s) "
                "while the console was reading; the console places no order"
            )

    return (
        f"{pair} position {filled.position_id}: the console read engine 19's row at the fill "
        f"mark {entry.limit}, and after one tick at {moved} it renders "
        f"{second.last_price_text} with the unrealised PnL moved by exactly "
        f"{expected_move} on {entry.qty} - live, not a snapshot. Past "
        f"console.stale_after_ms ({stale_after_ms}ms) the same row reports stale with its "
        f"age {stale.staleness.age_text!r} beside it, and fresh before it. On the tick "
        f"engine 4 blocked for a crossed quote the row shows the hold as "
        f"{held.hold_reason_text!r} and never the code {hold!r}. Signed percentages "
        f"({second.unrealised_pnl_pct_text} and {held.unrealised_pnl_pct_text}), a real "
        f"U+2212, and the entry price at exactly this pair's {pair_decimals} AssetPairs "
        f"decimal(s), which is where engine 18 put it. The console placed nothing - the "
        f"broker saw {placed} request(s) before and after - and its connection refused a "
        f"write: {refusal}. "
        + (
            "Every derived figure is inside the pair's precision too"
            if not thresholds
            else (
                "Derived thresholds render at the precision they were computed to and the "
                "console does not round them - ui-context.md rule 4 as amended 2026-09-18: "
                + ", ".join(thresholds)
                + ". Rounding them at write time was available and was rejected, because "
                "research/labelling.py computes its barriers the same unrounded way and "
                "stop_price is the trigger engine 21 compares against"
            )
        )
        + ". "
        + mark_precision
    )


def _stale_reading(drive: Drive, position_id: str, stale_after_ms: int) -> Any:
    """The same row, read by a console whose clock has moved past the threshold.

    The *console's* clock, and not the row's age, because the console is a separate
    process: a reader that judged staleness from anything the row itself carries would
    report a screen fresh while the daemon was dead. Restored afterwards, so the drive's
    own clock is where the next tick expects it.
    """
    was = drive.clock.now()
    try:
        drive.clock.set(was + timedelta(milliseconds=stale_after_ms * 2))
        view = _console_position(drive, position_id)
    finally:
        drive.clock.set(was)
    if not view.staleness.is_stale:
        raise DriveError(
            f"a console {stale_after_ms * 2}ms behind the row still calls it fresh; "
            "ui-context.md rule 5: stale data must look stale"
        )
    if not view.staleness.age_text:
        raise DriveError("the stale row carries no age to show beside the figure")
    return view


# --- order_book_slippage_on_recorded_book ----------------------------------- #


def _recorded_opening_books(
    ctx: VerifyContext,
) -> dict[str, tuple[tuple[tuple[Decimal, Decimal], ...], tuple[tuple[Decimal, Decimal], ...]]]:
    """Each pair's opening book in `tests/fixtures/book_sample.jsonl`, rebuilt here.

    Line 1 is the cutter's header. The first frame of each pair must be a `snapshot`,
    the only absolute book Kraken v2 sends; a pair that opens on a delta has no book in
    the file at all and is a FAIL. Read as bytes and parsed with `str()` on every number,
    so no float exists on the way to a `Decimal`.
    """
    path = ctx.root / "tests" / "fixtures" / "book_sample.jsonl"
    books: dict[str, Any] = {}
    with path.open("rb") as handle:
        handle.readline()
        for raw in handle:
            if not raw.strip():
                continue
            frame = json.loads(raw)
            pair = str(frame.get("pair"))
            if pair in books:
                continue
            payload = frame["payload"]
            if payload.get("type") != "snapshot":
                raise DriveError(
                    f"the first {pair} frame in book_sample.jsonl is a {payload.get('type')!r}, "
                    "so the fixture carries no absolute book for it"
                )
            data = payload["data"][0]
            sides = []
            for name, descending in (("bids", True), ("asks", False)):
                levels = sorted(
                    (
                        (Decimal(str(level["price"])), Decimal(str(level["qty"])))
                        for level in data.get(name) or []
                        if Decimal(str(level["qty"])) != 0
                    ),
                    key=lambda level: level[0],
                    reverse=descending,
                )
                sides.append(tuple(levels))
            books[pair] = (sides[0], sides[1])
    return books


def _walk_recorded(
    bids: Sequence[tuple[Decimal, Decimal]], basis: Decimal
) -> tuple[Decimal, int] | None:
    """`(fill price, levels touched)` selling `basis` of quote into `bids`, or `None`
    when the levels cannot absorb it. The same arithmetic, in the same order, as a
    walk of a book has to be: base bought from each level until the notional is met."""
    remaining = basis
    base = Decimal(0)
    touched = 0
    for price, quantity in bids:
        touched += 1
        notional = price * quantity
        if notional >= remaining:
            base += remaining / price
            remaining = Decimal(0)
            break
        base += quantity
        remaining -= notional
    if remaining > 0 or base <= 0:
        return None
    return basis / base, touched


def _book_levels(levels: Sequence[tuple[Decimal, Decimal]]) -> list[tuple[str, str]]:
    return [(format(price, "f"), format(quantity, "f")) for price, quantity in levels]


def _order_book_body(ctx: VerifyContext) -> Callable[..., str]:
    def body(tier: str, tools: dict[str, Any], polars: Any, subject: FillSubjectModel) -> str:
        del tier
        books = _recorded_opening_books(ctx)
        said: list[str] = []
        walked: dict[str, tuple[Decimal, int]] = {}
        for pair, universe, label in (
            (BOOK_THIN_PAIR, BOOK_THIN_UNIVERSE, "thin"),
            (BOOK_DEEP_PAIR, DRIVE_PAIRS, "deep"),
        ):
            if pair not in books:
                raise DriveError(f"book_sample.jsonl carries no {pair} book")
            bids, asks = books[pair]

            def setup(market: Any, store: Any, pair: str = pair, bids: Any = bids, asks: Any = asks) -> None:
                del store
                if pair == BOOK_THIN_PAIR:
                    market.set_pair_rule(pair, **BOOK_THIN_PAIR_RULE)
                market.set_order_book(pair, bids=_book_levels(bids), asks=_book_levels(asks))

            with _driven(tools, subject, polars, pairs=universe, before_start=setup) as drive:
                _warm_up(drive)
                state = drive.tick(drive.entry_at)
                depth = int(drive.config.get("order_book.depth"))
            scout = (state.get("scout") or {}).get("pair")
            if scout != pair:
                raise DriveError(f"engine 7 chose {scout!r} on the {label} run, not {pair}")
            published = state.get("order_book")
            if state.get("trading_blocked_by") == "order_book" or not isinstance(published, dict):
                raise DriveError(
                    f"engine 9 {'blocked' if isinstance(published, dict) else 'did not run'} "
                    f"on the {label} run (primary blocker {state.get('trading_blocked_by')!r}); "
                    "it is not a gate and must publish on every candidate tick"
                )
            if depth > len(bids):
                raise DriveError(
                    f"order_book.depth is {depth} and the recorded {pair} book holds "
                    f"{len(bids)} bid levels, so the fixture cannot validate the walk"
                )
            quote = state["exchange"]["pair_rules"]["pairs"][pair]["quote"]
            basis = Decimal(str(state["exchange"]["balances"][quote]))
            walk = _walk_recorded(bids[:depth], basis)
            if walk is None:
                raise DriveError(
                    f"the recorded {pair} book cannot absorb {basis} {quote} within {depth} "
                    "levels, so it cannot show a walk"
                )
            fill, levels = walk
            best = bids[0][0]
            expected = {
                "pair": pair,
                "depth": depth,
                "quote_currency": quote,
                "basis_notional": basis,
                "best_bid": best,
                "fill_price": fill,
                "levels_consumed": levels,
                "estimated_slippage_pct": (best - fill) / best,
                "reason_code": None,
            }
            got = {
                key: (
                    Decimal(str(published[key]))
                    if isinstance(expected[key], Decimal) and published.get(key) is not None
                    else published.get(key)
                )
                for key in expected
            }
            if got != expected:
                wrong = {key: (got[key], expected[key]) for key in expected if got[key] != expected[key]}
                raise DriveError(
                    f"engine 9's {label} walk of {pair} disagrees with the walk recomputed "
                    f"from the recorded book, as (published, recomputed): {wrong}"
                )
            walked[label] = ((best - fill) / best, levels)
            said.append(
                f"{pair} ({label}): {levels} of {depth} recorded bid levels walked to sell "
                f"the whole {basis} {quote} balance, fill {fill} against best bid {best}, "
                f"slippage {(best - fill) / best}"
            )
        if not (walked["thin"][0] > walked["deep"][0] and walked["thin"][1] > walked["deep"][1]):
            raise DriveError(
                f"the thin book walked {walked['thin']} and the deep one {walked['deep']}; the "
                "fixture no longer shows depth changing slippage"
            )
        return (
            "; ".join(said)
            + ". Each was recomputed from tests/fixtures/book_sample.jsonl and equals engine "
            "9's payload exactly, and engine 9 blocked neither candidate tick. The chain was "
            "driven through the registered engines so that it reaches engine 9; the walk "
            "itself reads no fee"
        )

    return body


# --- adaptive_router_weights_on_fixture ------------------------------------- #


def _leaderboard_fixture(ctx: VerifyContext) -> list[dict[str, Any]]:
    data = json.loads((ctx.root / "tests" / "fixtures" / "leaderboard_sample.json").read_bytes())
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise DriveError("leaderboard_sample.json carries no rows")
    return rows


def _router_weights(rows: Sequence[dict[str, Any]], model_id: str) -> tuple[dict[str, float], dict[str, int]]:
    """The weights recomputed from the file: `(weights, scored folds per version)`.

    One family only; the newest row per `(version, fold)` by `updated_at`; per fold
    `max(0, 1 - brier / base_rate_brier)`; the unweighted mean over a version's folds;
    normalised over versions in name order. The rule engine 14's README states.
    """
    latest: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in rows:
        if row.get("model_id") != model_id:
            continue
        key = (str(row["model_version"]), None if row.get("fold") is None else str(row["fold"]))
        held = latest.get(key)
        if held is None or int(row["updated_at"]) >= int(held["updated_at"]):
            latest[key] = row
    grouped: dict[str, list[dict[str, Any]]] = {}
    for (version, _fold), row in latest.items():
        grouped.setdefault(version, []).append(row)
    skills: dict[str, float] = {}
    scored: dict[str, int] = {}
    for version, members in sorted(grouped.items()):
        per_fold = [
            max(0.0, 1.0 - float(row["brier"]) / float(row["base_rate_brier"]))
            for row in members
            if row.get("brier") is not None
            and row.get("base_rate_brier") is not None
            and float(row["base_rate_brier"]) > 0.0
        ]
        skills[version] = sum(per_fold) / len(per_fold) if per_fold else 0.0
        scored[version] = len(per_fold)
    total = sum(skills.values())
    if total <= 0.0:
        return dict.fromkeys(skills, 0.0), scored
    return {version: skill / total for version, skill in skills.items()}, scored


def _router_body(ctx: VerifyContext) -> Callable[..., str]:
    def body(tier: str, tools: dict[str, Any], polars: Any, subject: FillSubjectModel) -> str:
        del tier
        router_contracts, problem = _symbol("acsoe.engines.adaptive_router.contracts", "MODEL_ID")
        if router_contracts is None:
            raise DriveError(f"engine 14 declares no model family: {problem}")
        model_id = str(router_contracts)
        rows = _leaderboard_fixture(ctx)
        families = {str(row.get("model_id")) for row in rows}
        keys = [(row.get("model_id"), row.get("model_version"), row.get("fold")) for row in rows]
        weights, scored = _router_weights(rows, model_id)
        witnesses = {
            "two versions of the family": len(weights) >= 2,
            "a second family": len(families) >= 2,
            "a duplicated (version, fold)": len(keys) != len(set(keys)),
            "a version with no edge": any(weight == 0.0 for weight in weights.values()),
            "a version with several folds": any(count >= 2 for count in scored.values()),
        }
        missing = [name for name, present in witnesses.items() if not present]
        if missing:
            raise DriveError(
                f"leaderboard_sample.json no longer carries {missing}, so the weights it "
                "produces cannot show the rule"
            )
        contracts = tools["contracts"]

        def setup(market: Any, store: Any) -> None:
            del market
            for row in rows:
                store.write_leaderboard_entry(
                    contracts.LeaderboardRow(
                        model_id=row["model_id"],
                        model_version=row["model_version"],
                        training_run_id=row.get("training_run_id"),
                        trained_at=row["trained_at"],
                        fold=row.get("fold"),
                        n_trades=row["n_trades"],
                        win_rate=row.get("win_rate"),
                        brier=row.get("brier"),
                        base_rate_brier=row.get("base_rate_brier"),
                        net_pnl=None if row.get("net_pnl") is None else Decimal(str(row["net_pnl"])),
                        reporting_currency=row.get("reporting_currency"),
                        promoted=bool(row.get("promoted", False)),
                        updated_at=row["updated_at"],
                    )
                )

        with _driven(tools, subject, polars, before_start=setup) as drive:
            _warm_up(drive)
            state = drive.tick(drive.entry_at)
        published = state.get("adaptive_router")
        if not isinstance(published, dict) or state.get("trading_blocked_by") == "adaptive_router":
            raise DriveError(
                f"engine 14 did not publish on the candidate tick (primary blocker "
                f"{state.get('trading_blocked_by')!r})"
            )
        folds = {
            version: (entry or {}).get("folds_scored")
            for version, entry in ((published.get("basis") or {}).get("versions") or {}).items()
        }
        got = (published.get("weights"), folds, published.get("reason_code"))
        want = (weights, scored, None)
        if got != want:
            raise DriveError(
                f"engine 14 published (weights, folds scored, reason) {got}; recomputed from "
                f"leaderboard_sample.json it is {want}"
            )
        return (
            f"on tests/fixtures/leaderboard_sample.json - fabricated rows, so this is a "
            f"property of the fixture and not of any trained model - engine 14 weighted "
            f"{weights}, equal to the weights recomputed from the file: the mean over each "
            "version's folds of max(0, 1 - brier / base_rate_brier), normalised, with the "
            f"older duplicate of a (version, fold) dropped, the other family "
            f"({sorted(families - {model_id})}) left out, and a version with no edge at "
            "zero. The chain was driven through the registered engines so that it reaches "
            "engine 14, which sits after the cost gate"
        )

    return body


def check_paper_trade_round_trip_target(ctx: VerifyContext) -> Outcome:
    """A candidate becomes a filled position that exits at the target, recorded exactly.

    The whole phase in one line: post-only entry past every registered gate, simulated
    fill, minute-by-minute watch, the exit, and every row engine 19 wrote reconciled
    against the trade. The named wrong implementation is engine 21 never deciding the
    target barrier.
    """
    return _round_trip(ctx, "target")


def check_paper_trade_round_trip_stop(ctx: VerifyContext) -> Outcome:
    """The same round trip ending at the stop.

    Separately registered because the stop is the leg that protects the account, and a
    chain that can only be shown to take profit has been shown the easy half. The named
    wrong implementation is engine 21 holding on a tick nothing blocked.
    """
    return _round_trip(ctx, "stop")


def check_paper_trade_round_trip_timeout(ctx: VerifyContext) -> Outcome:
    """The same round trip ending at the timeout, with neither barrier touched.

    The path no price movement triggers, so it is the one a broken clock comparison
    leaves open forever while the other two stay green.
    """
    return _round_trip(ctx, "timeout")


def check_unfilled_entry_cancels_without_chasing(ctx: VerifyContext) -> Outcome:
    """A post-only entry that never fills is cancelled, and nothing chases the price.

    Three claims. The order is cancelled on the first tick at
    `trading.entry_unfilled_window_s` and not before; **no market order reaches the
    broker** - in paper mode the broker is the exchange, and it is asked for exactly the
    entry and its cancel; and no second entry is placed before the next bar closes,
    which is the difference between giving up on a fill and chasing one.

    The named wrong implementation is engine 21 re-placing the cancelled entry at the
    new bid. It looks like diligence and it is the chase invariant 8 forbids.
    """
    return _driven_verdict(ctx, _unfilled_body, what="the unfilled entry")


def check_triggered_stop_holds_on_data_guard_block(ctx: VerifyContext) -> Outcome:
    """A stop that triggers on a tick the guard rejected places no exit, and says why.

    `engine-contracts.md`: when `state["trading_blocked_by"] == "data_guard"` the manage
    chain still runs and engines 21 and 22 place **no** exit, because a barrier computed
    from exactly the data the guard refused is a fabricated trigger. Engine 21 publishes
    `hold_reason` and engine 19 stores it on the position.

    And the other half in the same criterion, because the hold is only correct if it is
    also bounded: the **same** position with `close_intent` set does exit, while the guard
    is still blocking. A hold that survives a liquidation is invariant 14 broken.

    The named wrong implementations are the hold removed from engine 21, and engine 22
    reading a liquidation as an ordinary tick.
    """
    return _driven_verdict(ctx, _held_stop_body, what="the held stop")


def check_escalation_completes_during_outage(ctx: VerifyContext) -> Outcome:
    """The kill switch finishes while the outage that fired it is still happening.

    Two drives. **Positions:** engine 17 escalates on the tick after
    `safety.max_consecutive_data_blocks` blocked ticks and not before; on the next tick,
    with `data_guard` still blocking and the balance and `AssetPairs` fetches still
    failing, engine 22 closes the position using the retained `AssetPairs` and records
    that fallback on the trade, and the orchestrator clears `close_intent` and consumes
    the command. **Resting entries:** at the committed config a safety escalation can
    never find one (the unfilled window cancels it first), so the cancel half of the
    kill switch is proven through an operator `close_all` issued inside the entry's
    window, during the same outage.

    This is invariant 14, and it is the one place in the system where a fetch failure
    does **not** block. The named wrong implementations are engine 22 reading fresh pair
    rules only - correct everywhere else, which is why it is the mistake that gets made -
    and engine 21 cancelling on elapsed time only.

    `safety_escalates_on_sustained_outage` in Phase 3 proves engine 17 *emits* the row
    from the seed. This proves the manage chain *completes* on it.
    """
    return _driven_verdict(ctx, _escalation_body, what="the escalation")


def check_console_shows_position_live(ctx: VerifyContext) -> Outcome:
    """The console renders a position a real daemon opened, and the mark moves.

    Spec 101's subject. Phase 1 proved the region renders against **seeded** rows, which
    is a different claim: a seeded row is written by the seed generator to the shape the
    console expects, and a position written by engine 19 out of engine 21's payload is
    written to the shape engine 21 publishes.

    The PENDING guard below is kept although the drive now exists, and it is kept in
    the order it was written in: an absent `hold_reason` on `PositionView` is the console
    half of this criterion not being built, which is PENDING, and it must not arrive as a
    `DriveError` two hundred lines into a drive that spent a minute getting there.
    """
    with root_import_path(ctx.root):
        tier, problem = _tier_sentence(3)
        if tier is None:
            return _awaiting(problem, "at fee tier 3")
        problem = _phase6_engines("position_manager", "exit", "memory")
        if problem is None:
            problem = _paper_broker_module()
        if problem is None:
            view, missing = _symbol("acsoe.console.views", "PositionView")
            fields = getattr(view, "model_fields", None) if view is not None else None
            if view is None:
                problem = missing
            elif not isinstance(fields, dict) or "hold_reason" not in fields:
                problem = pending(
                    "the console's open-positions region shows no hold reason yet: "
                    "PositionView has no `hold_reason` (C, spec 101) - " + CONSOLE_LIVE_CONTRACT
                )
        if problem is not None:
            return _awaiting(problem, tier)
    return _driven_verdict(
        ctx, _console_position_body, what="the console's open-positions region"
    )


def check_order_book_slippage_on_recorded_book(ctx: VerifyContext) -> Outcome:
    """Engine 9's slippage estimate matches a walk this criterion recomputes.

    **Recomputed from the fixture, never a number this file stores.** The opening book
    of each pair is rebuilt here from `tests/fixtures/book_sample.jsonl`, loaded into the
    fake exchange, and the registered chain is driven to a candidate tick on that pair;
    engine 9's payload is then compared field by field with the walk recomputed from the
    same levels at the balance engine 1 published.

    Thin book and deep book, because a walk that consumes one level and a walk that
    consumes several are different code paths and the thin one is where the money is.
    Engine 9 **never blocks** and estimates at the whole quote balance, the lead's
    decision of 2026-09-16. The named wrong implementations are walking the ask side and
    a walk that is off by a level.

    Driven at fee tier 3 because that is the regime every drive in this section runs in;
    the walk reads no fee, and the message says both.
    """
    with root_import_path(ctx.root):
        _, problem = _phase6_engine_class("order_book")
        if problem is not None:
            return problem
        problem = _phase6_fixture(ctx, "book_sample.jsonl")
        if problem is not None:
            return problem
    return _driven_verdict(ctx, _order_book_body(ctx), what="engine 9 on the recorded book")


def check_adaptive_router_weights_on_fixture(ctx: VerifyContext) -> Outcome:
    """Engine 14's weights are recomputed from the leaderboard rows, not read back.

    The fixture's rows are written into a real store, the registered chain is driven to
    a candidate tick, and engine 14's weights are compared with weights this criterion
    derives from `leaderboard_sample.json` itself. The fixture carries **at least two
    models**, a second family, a duplicated `(version, fold)` and a version with no edge,
    and the criterion refuses a fixture that has lost any of those witnesses. Every
    sentence names the fixture as its subject: the weights are a property of these
    fabricated rows, not of any trained model.

    Engine 14 sits after engine 10 `cost`, so the chain can only reach it at fee tier 3.
    The named wrong implementations are an unclipped skill and a duplicate row averaged
    in or kept in place of the newer one.
    """
    with root_import_path(ctx.root):
        _, problem = _phase6_engine_class("adaptive_router")
        if problem is not None:
            return problem
        problem = _phase6_fixture(ctx, "leaderboard_sample.json")
        if problem is not None:
            return problem
    return _driven_verdict(ctx, _router_body(ctx), what="engine 14 on the leaderboard fixture")


# --- equity_row_never_values_positions_it_does_not_hold --------------------- #


def _equity_rows_body(
    tier: str, tools: dict[str, Any], polars: Any, subject: FillSubjectModel
) -> str:
    del tier
    with _driven(tools, subject, polars) as drive:
        _warm_up(drive)
        entry, _ = _entry(drive)
        filled, _ = _fill(drive, entry)
        exited = _trigger_exit(drive, entry, filled, "stop")
        drive.tick(exited.exit_at + drive.tick_s)
        rows = drive.run_equity()
    stamps = {row.ts for row in rows}
    invested = [row for row in rows if row.open_position_count > 0]
    needed = {
        "the fill tick": _micros(filled.filled_at),
        "the exit tick": _micros(exited.exit_at),
        "the tick after the exit": _micros(exited.exit_at + drive.tick_s),
    }
    missing = [name for name, ts in needed.items() if ts not in stamps]
    if missing or not invested:
        raise DriveError(
            f"the drive wrote no equity row for {missing or 'an invested tick'}, so there is "
            "nothing to judge"
        )
    wrong = [
        (row.cycle_id, row.ts, str(row.positions_value), row.open_position_count, str(row.equity))
        for row in rows
        if row.positions_value != 0 and row.open_position_count == 0
    ]
    if wrong:
        raise DriveError(
            f"{len(wrong)} of {len(rows)} equity rows value positions the account does not "
            "hold, as (cycle, ts, positions_value, open_position_count, equity): "
            f"{wrong}. A row that counts no open position and still carries a positions "
            "value is an equity figure for an account that no longer exists, and engine 17 "
            "reads its drawdown, and peak_equity keeps it, from exactly this series"
        )
    return (
        f"all {len(rows)} equity rows of a round trip ({len(invested)} with a position open, "
        "including the fill tick, the exit tick and the tick after it) carry a "
        "positions_value of zero whenever they count no open position"
    )


def check_equity_row_never_values_positions_it_does_not_hold(ctx: VerifyContext) -> Outcome:
    """No `equity_snapshots` row values positions it counts as not held.

    Operator ruling of 2026-09-17 on C's spec 100 finding: on the tick engine 22 sold a
    position, engine 19 wrote the pre-exit cash and engine 21's pre-exit positions value,
    and counted no open position. The row then valued a position the account no longer
    held, and on a target exit that figure was above the peak. This criterion is the
    observable form of that defect, and it was written, and seen to FAIL, before the fix
    (specs 113 and 114).

    The drive is a real round trip to the stop, plus one tick after the exit. It refuses
    to judge a drive that wrote no row on the fill tick, the exit tick or the tick after,
    because an empty series satisfies any rule about its rows.
    """
    return _driven_verdict(ctx, _equity_rows_body, what="the equity rows of a round trip")


# --------------------------------------------------------------------------- #
# Phase 7 - evaluation. Spec 141, registered PENDING-first ahead of its subjects.
# --------------------------------------------------------------------------- #

#: The committed trial ledger spec 139's gate reads its N from (ruling R9).
PHASE7_LEDGER: Final = Path("docs") / "dataset" / "phase-7-trial-ledger.json"

#: Spec 139's fabricated model: fifteen non-overlapping trades whose unwidened 95% lower
#: bound is above zero and whose Bonferroni-widened bound at the ledger's count is not. Net
#: returns on a 1,000 entry notional (10 units at 100).
PROMOTION_FIXTURE_RETURNS: Final[tuple[str, ...]] = (
    "0.004", "-0.002", "0.006", "0.001", "0.003", "-0.001", "0.005", "0.002", "0.000",
    "0.004", "0.003", "-0.002", "0.006", "0.001", "0.002",
)

PHASE7_NOW: Final = datetime(2026, 9, 20, 9, 30, tzinfo=UTC)


def _promotion_trades(contracts: Any, run_id: str) -> list[Any]:
    """The fixture's trades as real `TradeRow`s, an hour apart, ten minutes each."""
    start = 1_720_000_000_000_000
    minute = 60_000_000
    rows = []
    for index, net in enumerate(PROMOTION_FIXTURE_RETURNS):
        opened = start + index * 60 * minute
        realised = Decimal(net) * Decimal(1000)
        rows.append(
            contracts.TradeRow(
                trade_id=f"verify-promotion-{index:02d}",
                position_id=f"verify-position-{index:02d}",
                run_id=run_id,
                cycle_id=index + 1,
                pair=f"P{index:02d}/USD",
                base=f"P{index:02d}",
                quote="USD",
                qty=Decimal(10),
                entry_price=Decimal(100),
                exit_price=Decimal(100),
                entry_fee=Decimal(0),
                exit_fee=Decimal(0),
                opened_at=opened,
                closed_at=opened + 10 * minute,
                outcome="target" if Decimal(net) > 0 else "stop",
                realised_pnl=realised,
                realised_pnl_pct=Decimal(net),
                realised_pnl_quote=realised,
                reporting_currency="USD",
                fx_rate_entry=Decimal(1),
                fx_rate_exit=Decimal(1),
                updated_at=opened + 10 * minute,
            )
        )
    return rows


def _judge_fixture(
    tmp: Path, name: str, engine_cls: Any, ledger: Path, run_id: str
) -> tuple[Any, list[Any], Outcome | None]:
    """Engine 20's promotion gate over the fixture in a fresh store: `(result, rows, problem)`."""
    contracts, problem = try_import("acsoe.clients.store.contracts")
    if contracts is None:
        return None, [], problem or pending("clients.store.contracts does not exist yet")
    db_path, store_cls, problem = _migrated_db(tmp, name)
    if db_path is None:
        return None, [], problem or pending("the store could not be migrated")
    store = store_cls(db_path)
    try:
        for trade in _promotion_trades(contracts, run_id):
            store.write_trade(trade)
        clients, problem = _fake_clients(store=store)
        if clients is None:
            return None, [], problem or pending("the shared test doubles are unavailable")
        config, problem = _phase3_config()
        if config is None:
            return None, [], problem or pending("the committed config could not be loaded")
        context, problem = _engine_context(config, clients, run_id="verify-phase-7", now=PHASE7_NOW)
        if context is None:
            return None, [], problem or pending("acsoe.core.contracts does not exist yet")
        result = engine_cls(promote_run_id=run_id, ledger_path=ledger).process(context, {})
        rows = list(
            store.leaderboard_entries(model_id="chain_run", model_version=run_id, fold=None)
        )
    finally:
        store.close()
    return result, rows, None


def check_promotion_gate_rejects_haircut_edge(ctx: VerifyContext) -> Outcome:
    """Spec 139's fabricated model, judged through the real engine 20 and the real store.

    The Phase 7 row's second clause: "promotion gate rejects a model whose edge does not
    survive the trial haircut". Fifteen trades whose unwidened 95% lower bound on net
    return per trade is above zero are rejected at the committed ledger's trial count and
    promoted at a count of one, so the rejection is shown to be the haircut's doing and not
    a gate that refuses everything. The N used is the committed ledger's, read here.
    """
    ledger = ctx.root / PHASE7_LEDGER
    with root_import_path(ctx.root):
        promotion, problem = try_import("acsoe.modelling.promotion")
        if promotion is None:
            # Not `problem or pending(...)`: `try_import`'s PENDING is truthy and would win,
            # and the spec that owes the subject would never reach the operator.
            if problem is not None and problem.result is Result.FAIL:
                return problem
            return pending("acsoe.modelling.promotion does not exist yet (spec 139)")
        engine_cls, problem = _phase5_engine_class("tournament")
        if engine_cls is None:
            if problem is not None and problem.result is Result.FAIL:
                return problem
            return pending("engine 20 `tournament` does not exist yet (spec 74; gate spec 139)")
        if "promote_run_id" not in inspect.signature(engine_cls).parameters:
            return pending(
                "engine 20 `tournament` has no promotion gate yet: it takes no "
                "`promote_run_id` (spec 139)"
            )
        if not ledger.is_file():
            return pending(f"{PHASE7_LEDGER.as_posix()} does not exist yet (spec 139, R9)")
        payload = json.loads(ledger.read_bytes().decode("utf-8"))
        trials = payload.get("trial_count") if isinstance(payload, Mapping) else None
        if not isinstance(trials, int) or trials < 2:
            return failed(
                f"{PHASE7_LEDGER.as_posix()} states a trial_count of {trials!r}. The haircut "
                "can only be shown against a count above one."
            )
        with tempfile.TemporaryDirectory(prefix="acsoe-verify-promotion-") as raw_tmp:
            tmp = Path(raw_tmp)
            one = tmp / "ledger-one.json"
            one.write_bytes(
                json.dumps(
                    {"trial_count": 1, "trials": [{"family": "verify", "source": "verify"}]}
                ).encode("utf-8")
            )
            at_n, rows_n, problem = _judge_fixture(
                tmp, "at-n.sqlite", engine_cls, ledger, "verify-haircut"
            )
            if problem is not None:
                return problem
            at_one, rows_one, problem = _judge_fixture(
                tmp, "at-one.sqlite", engine_cls, one, "verify-haircut"
            )
            if problem is not None:
                return problem
        values = [float(Decimal(net)) for net in PROMOTION_FIXTURE_RETURNS]
        n = len(values)
        mean = sum(values) / n
        unwidened = mean - promotion.student_t_quantile(0.975, n - 1) * (
            promotion.hac_standard_error(values, 0)
        )

    for label, result in (("at the ledger's count", at_n), ("at one trial", at_one)):
        if str(getattr(result, "status", "")) != "OK":
            return failed(
                f"engine 20 did not judge the fixture {label}: "
                f"{getattr(result, 'status', None)} - {str(getattr(result, 'reason', ''))[:300]}"
            )
    if unwidened <= 0:
        return failed(
            f"the fixture's unwidened 95% lower bound is {unwidened:.6f}, not above zero, so "
            "a rejection could not be attributed to the haircut; the fixture is wrong"
        )
    data_n, data_one = at_n.data, at_one.data
    if len(rows_n) != 1 or len(rows_one) != 1:
        return failed(
            f"engine 20 wrote {len(rows_n)} and {len(rows_one)} verdict rows; one per judged "
            "run is the record the leaderboard screen and the report read"
        )
    if data_n.get("trial_count") != trials:
        return failed(
            f"engine 20 judged with N = {data_n.get('trial_count')!r}; the committed ledger "
            f"says {trials}"
        )
    if data_n.get("promoted") is not False or rows_n[0].promoted is not False:
        return failed(
            f"at the ledger's {trials} trials the fabricated model was promoted (lower bound "
            f"{data_n.get('lower_bound')!r}); its edge does not survive the haircut and the "
            "gate let it through"
        )
    if data_n.get("promotion_reason_code") != "promotion_lower_bound_not_above_zero":
        return failed(
            f"the rejection carries reason {data_n.get('promotion_reason_code')!r}, not "
            "promotion_lower_bound_not_above_zero"
        )
    if data_one.get("promoted") is not True or rows_one[0].promoted is not True:
        return failed(
            f"at one trial the same trades were not promoted (lower bound "
            f"{data_one.get('lower_bound')!r}), so the gate refuses what the haircut should "
            "decide and the rejection above proves nothing about the haircut"
        )
    return passed(
        f"spec 139's fabricated model, {n} non-overlapping trades, mean net return "
        f"{mean:.4%} per trade: unwidened 95% lower bound {unwidened:.4%}, above zero. At the "
        f"committed ledger's {trials} trials the interval is widened to confidence "
        f"{data_n['confidence']:.6f} (t quantile {data_n['t_quantile']:.3f}, HAC lag "
        f"{data_n['hac_lag']}) and its lower bound is {data_n['lower_bound']:.4%}: rejected, "
        f"promotion_lower_bound_not_above_zero, deflated Sharpe ratio "
        f"{data_n['deflated_sharpe']:.4f} reported beside it. The same trades at one trial: "
        f"lower bound {data_one['lower_bound']:.4%}, promoted. Real engine 20, real store"
    )


#: The two modules allowed to read the declared fee schedule (invariant 2's amendment).
FEE_SCENARIO_READERS: Final = (
    Path("src") / "acsoe" / "clients" / "kraken" / "replay.py",
    Path("src") / "acsoe" / "clients" / "kraken" / "replay_scenario.py",
)
#: What "reads the scenario fixtures" looks like in a module: a declared fixture's name, their
#: directory, or a loader. The set may widen and never narrow (lead ruling 2026-09-19, when the
#: directory marker first caught a module writing a trade slice beside the fixtures: the slice
#: moved, and the fixtures' and loaders' own names were added alongside the directory).
FEE_SCENARIO_MARKERS: Final = (
    "kraken_fee_schedule",
    "spread_book_table",
    "fixtures/replay",
    "load_fee_scenario",
    "load_spread_table",
)
FEE_SCENARIO_LOADERS: Final = frozenset({"load_fee_scenario", "load_spread_table"})
FEE_SCENARIO_MODULE: Final = "acsoe.clients.kraken.replay_scenario"
#: The one module that **writes** a declared fixture, pinned by exact path to the only markers
#: its job needs (lead ruling D22, 2026-09-19). `scripts/build_bucket_table.py` is spec 130's
#: builder of the declared spread and depth table: it writes
#: `tests/fixtures/replay/spread_book_table_<stamp>.json` and reads no fee and prices nothing.
#: Any other marker in it is still a hit, and no other module is covered. Rejected: moving the
#: builder into the replay client (an offline builder in a runtime client, another lane), a
#: "writes but never reads" rule (not provable from an AST), and scanning `src/` only (narrows
#: the check).
FEE_SCENARIO_PRODUCERS: Final[dict[Path, frozenset[str]]] = {
    Path("scripts") / "build_bucket_table.py": frozenset({"spread_book_table", "fixtures/replay"}),
}


def _joined_path_pieces(node: ast.AST) -> str | None:
    """The string pieces of a path built with `/` or passed to one call, joined with `/`.

    Catches `Path("tests") / "fixtures" / "replay"` and `Path("tests", "fixtures", "replay")`,
    which name the directory without ever spelling `fixtures/replay` in one constant.
    """
    pieces: list[str] = []

    def flatten(item: ast.AST) -> None:
        if isinstance(item, ast.BinOp) and isinstance(item.op, ast.Div):
            flatten(item.left)
            flatten(item.right)
        elif isinstance(item, ast.Call):
            for argument in item.args:
                flatten(argument)
        elif isinstance(item, ast.Constant) and isinstance(item.value, str):
            pieces.append(item.value)
        else:
            pieces.append("<not a string>")

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        flatten(node)
    elif isinstance(node, ast.Call) and len(node.args) > 1:
        for argument in node.args:
            flatten(argument)
    else:
        return None
    return "/".join(pieces) if len(pieces) > 1 else None


def _fee_scenario_readers(root: Path) -> list[str]:
    """Every module under `src/` and `scripts/` that names the declared fee, bar the two.

    Read off the syntax tree: a string constant carrying a marker, a name or attribute
    spelled like the loader, or an import of the scenario module. `scripts/verify.py` is
    skipped, because it names the markers in order to look for them.
    """
    allowed = {(root / path).resolve() for path in FEE_SCENARIO_READERS}
    producers = {(root / path).resolve(): marks for path, marks in FEE_SCENARIO_PRODUCERS.items()}
    found: list[str] = []
    for base in (root / "src", root / "scripts"):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.resolve() in allowed or path.name == "verify.py":
                continue
            try:
                tree = ast.parse(path.read_bytes().decode("utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            excused = producers.get(path.resolve(), frozenset())
            for node in ast.walk(tree):
                hit = None
                joined = _joined_path_pieces(node)
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value.replace("\\", "/")
                    hit = next((m for m in FEE_SCENARIO_MARKERS if m in text), None)
                elif joined is not None:
                    hit = next((m for m in FEE_SCENARIO_MARKERS if m in joined), None)
                elif isinstance(node, ast.Name | ast.Attribute):
                    name = node.id if isinstance(node, ast.Name) else node.attr
                    hit = name if name in FEE_SCENARIO_LOADERS else None
                elif isinstance(node, ast.ImportFrom) and (
                    node.module == FEE_SCENARIO_MODULE
                    or any(f"{node.module}.{a.name}" == FEE_SCENARIO_MODULE for a in node.names)
                ):
                    hit = FEE_SCENARIO_MODULE
                elif isinstance(node, ast.Import):
                    hit = next(
                        (a.name for a in node.names if a.name == FEE_SCENARIO_MODULE), None
                    )
                if hit is not None and hit not in excused:
                    found.append(f"{path.relative_to(root).as_posix()}: {hit}")
                    break
    return found


def check_fee_scenario_is_replay_only(ctx: VerifyContext) -> Outcome:
    """Invariant 2's amendment of 2026-09-19, enforced by test as ruled.

    A declared fee may price a replay and nothing else. Two halves: the replay client
    refuses construction in paper and in live (through its constructor and through
    `from_config`, the latter before it opens any fixture), and accepts it in replay; and
    no module outside the replay client names the declared fee schedule.
    """
    with root_import_path(ctx.root):
        replay, problem = try_import("acsoe.clients.kraken.replay")
        if replay is None:
            if problem is not None and problem.result is Result.FAIL:
                return problem
            return pending(
                "acsoe.clients.kraken.replay does not exist yet (spec 129, the replay client)"
            )
        client_cls, missing = module_attr(replay, "ReplayKrakenClient")
        if client_cls is None:
            return pending(missing)
        refusal, missing = module_attr(replay, "ReplayModeError")
        if refusal is None:
            return pending(missing)

        class _Rules:
            rules: Mapping[str, Any] = {}

        class _Scenario:
            rules = _Rules()

        class _Untouchable:
            """A config any read of which is a fixture opened before the mode check."""

            def __init__(self, mode: str) -> None:
                self.mode = mode
                self.reads: list[str] = []

            def get(self, key: str) -> Any:
                self.reads.append(key)
                raise AssertionError(f"read {key} before refusing mode {self.mode}")

        verdicts: list[str] = []
        for mode in ("paper", "live"):
            try:
                client_cls(
                    mode=mode, clock=None, scenario=_Scenario(), tape=None,
                    interval_s=900, published_bars=200,
                )
            except refusal:
                pass
            else:
                return failed(f"the replay client was constructed in mode {mode!r}")
            config = _Untouchable(mode)
            try:
                client_cls.from_config(config, clock=None, root=ctx.root)
            except refusal:
                pass
            except AssertionError:
                return failed(
                    f"from_config in mode {mode!r} read {config.reads} before refusing: a "
                    "paper or live process opened the declared scenario"
                )
            else:
                return failed(f"from_config built a replay client in mode {mode!r}")
            if config.reads:
                return failed(f"from_config in mode {mode!r} read {config.reads} first")
            verdicts.append(mode)
        try:
            client_cls(
                mode="replay", clock=None, scenario=_Scenario(), tape=None,
                interval_s=900, published_bars=200,
            )
        except refusal as exc:
            return failed(f"the replay client refused mode 'replay' too: {exc}")
    readers = _fee_scenario_readers(ctx.root)
    if readers:
        return failed(
            "outside the replay client, these modules name the declared fee schedule: "
            + "; ".join(readers[:5])
            + ". Invariant 2 permits a declared fee in replay mode only, and the replay "
            "client is the one reader that refuses every other mode."
        )
    return passed(
        "the replay client refused construction in "
        + " and ".join(verdicts)
        + " (constructor, and from_config before reading any key) and accepted replay; no "
        "module under src/ or scripts/ outside clients/kraken/replay.py and "
        "replay_scenario.py names the declared fee schedule "
        "(tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json)"
    )


#: Where spec 143 commits one attribution digest per run: the JSON of
#: `python -m acsoe.research.attribution --db <run> --json <file>`, i.e.
#: `AttributionReport.to_dict()`.
ALPHA_DIGESTS: Final = Path("tests") / "fixtures" / "phase7"
ALPHA_DIGEST_GLOB: Final = "run-digest-*.json"
ALPHA_DAY_US: Final = 86_400 * 1_000_000
#: How far a stated fit may sit from the one recomputed from the digest's own series. Both
#: are the same double arithmetic over the same numbers, so anything wider is a disagreement.
ALPHA_FIT_TOLERANCE: Final = 1e-9
ALPHA_DIGEST_KEYS: Final[tuple[str, ...]] = (
    "grid_us", "equity_levels", "btc_levels", "basket_levels", "btc", "basket", "flat_days",
    "window_start_us", "window_end_us", "tail_excluded_s", "coverage", "scenario_digest",
    "scenario_description", "run_ids",
)
ALPHA_FIT_FIELDS: Final[tuple[str, ...]] = (
    "n_days", "alpha_daily", "alpha_ci", "beta", "beta_ci", "alpha_se_hac", "hac_lag",
    "significant",
)


def _alpha_iso(micros: int) -> str:
    return datetime.fromtimestamp(micros / 1_000_000, UTC).strftime("%Y-%m-%dT%H:%MZ")


def _alpha_fit_disagreements(stated: Any, recomputed: Any, label: str) -> list[str]:
    """Every field of a stated fit that the recomputation from the series does not reproduce."""
    if recomputed is None or stated is None:
        if (recomputed is None) != (stated is None):
            return [
                (
                    f"the {label} fit is {'absent' if stated is None else 'stated'} in the "
                    f"digest and {'absent' if recomputed is None else 'present'} when recomputed"
                )
            ]
        return []
    out = []
    for name in ALPHA_FIT_FIELDS:
        want, got = stated.get(name), getattr(recomputed, name)
        if isinstance(got, bool) or isinstance(want, bool) or isinstance(got, int):
            same = want == got
        else:
            pairs = list(zip(want, got, strict=True)) if isinstance(got, tuple) else [(want, got)]
            same = all(
                isinstance(w, int | float)
                and math.isclose(float(w), g, rel_tol=ALPHA_FIT_TOLERANCE, abs_tol=1e-15)
                for w, g in pairs
            )
        if not same:
            out.append(f"the {label} fit states {name} {want!r}; its series give {got!r}")
    return out


def _alpha_digest_problems(attribution: ModuleType, digest: Any) -> list[str]:
    """Why a digest is not internally consistent, or nothing.

    Checked from the digest's own contents, never by trusting a figure it states about
    itself: the grid is whole days from the window's start; every day is regressed, flat ones
    included, so both fits count every grid day; every decision bar of the window carries an
    equity row; both regressions recompute from the series (spec 138's `regress_digest`); and
    the scenario digest is the sha256 of the description it travels with.
    """
    if not isinstance(digest, Mapping):
        return ["the digest is not a JSON object"]
    missing = [key for key in ALPHA_DIGEST_KEYS if key not in digest]
    if missing:
        return ["the digest carries no " + ", ".join(missing)]
    problems: list[str] = []
    grid = [int(v) for v in digest["grid_us"]]
    if len(grid) < 4:
        return [f"the grid holds {len(grid)} point(s); a regression needs at least four"]
    steps = {grid[i + 1] - grid[i] for i in range(len(grid) - 1)}
    if steps != {ALPHA_DAY_US}:
        problems.append("the grid is not whole days apart")
    start, end = int(digest["window_start_us"]), int(digest["window_end_us"])
    if grid[0] != start:
        problems.append(
            f"the grid starts {_alpha_iso(grid[0])} and the window {_alpha_iso(start)}: the "
            "benchmark was not marked over the run's own window"
        )
    tail = end - grid[-1]
    if not 0 <= tail < ALPHA_DAY_US or int(digest["tail_excluded_s"]) != tail // 1_000_000:
        problems.append(
            f"the grid ends {_alpha_iso(grid[-1])} against a window ending {_alpha_iso(end)}, "
            f"and the digest states a tail of {digest['tail_excluded_s']} s"
        )
    series = {name: digest[name] for name in ("equity_levels", "btc_levels", "basket_levels")}
    for name, values in series.items():
        if len(values) != len(grid):
            problems.append(f"{name} has {len(values)} points against a grid of {len(grid)}")
    if problems:
        return problems
    equity = [float(v) for v in series["equity_levels"]]
    returns = [equity[i + 1] / equity[i] - 1.0 for i in range(len(equity) - 1)]
    flat = sum(1 for r in returns if r == 0.0)
    if int(digest["flat_days"]) != flat:
        problems.append(
            f"the digest states {digest['flat_days']} flat day(s); its equity series has {flat}"
        )
    for label in ("btc", "basket"):
        fit = digest[label]
        if fit is not None and int(fit.get("n_days", -1)) != len(returns):
            problems.append(
                f"the {label} fit regressed {fit.get('n_days')} day(s) of {len(returns)}: days "
                "were dropped, and a regression that drops the flat days is not one over the "
                "full curve including cash periods"
            )
    coverage = digest["coverage"]
    bars = coverage.get("decision_bars") if isinstance(coverage, Mapping) else None
    expected = coverage.get("decision_bars_expected") if isinstance(coverage, Mapping) else None
    if not isinstance(bars, int) or bars != expected:
        problems.append(
            f"{bars!r} decision bars carry an equity row of {expected!r} in the window: a tick "
            "with no row is a day the curve does not cover"
        )
    floor = max(1, attribution.newey_west_rule(len(returns)))
    for label in ("btc", "basket"):
        fit = digest[label]
        if fit is not None and int(fit.get("hac_lag", -1)) < floor:
            problems.append(
                f"the {label} fit's HAC lag is {fit.get('hac_lag')}, below the Newey-West rule's "
                f"{floor} for {len(returns)} days: consecutive days that share positions were "
                "treated as independent"
            )
    recomputed = attribution.regress_digest(digest)
    problems += _alpha_fit_disagreements(digest["btc"], recomputed["btc"], "BTC/USD")
    problems += _alpha_fit_disagreements(digest["basket"], recomputed["basket"], "basket")
    description = digest["scenario_description"]
    stated = digest["scenario_digest"]
    if not isinstance(description, Mapping) or not isinstance(stated, str):
        problems.append("the digest names no replay scenario, so its window, tier and ranking are unknown")
    else:
        canonical = json.dumps(description, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        actual = hashlib.sha256(canonical.encode("ascii")).hexdigest()
        if actual != stated:
            problems.append(
                f"the scenario digest {stated[:12]} is not the sha256 of the description the "
                f"digest carries ({actual[:12]})"
            )
    return problems


def _alpha_digest_summary(digest: Mapping[str, Any]) -> str:
    """Window, tier, ranking, scenario and both benchmarks, as the spec asks the message to."""
    description = digest["scenario_description"]
    fee = description.get("fee") if isinstance(description, Mapping) else None
    tier = fee.get("tier") if isinstance(fee, Mapping) else None
    ranking = description.get("ranking") if isinstance(description, Mapping) else None

    def fit(label: str, value: Any) -> str:
        if value is None:
            return f"{label}: not regressed (the run held nothing)"
        verdict = "significant" if value["significant"] else "not significant"
        low, high = value["alpha_ci"]
        return (
            f"{label}: alpha {value['alpha_daily']:+.6f}/day (95% CI {low:+.6f} to "
            f"{high:+.6f}, {verdict}), beta {value['beta']:.3f}, {value['n_days']} days"
        )

    return (
        f"window {_alpha_iso(int(digest['window_start_us']))} to "
        f"{_alpha_iso(int(digest['window_end_us']))}, tier {tier}, ranking {ranking}, scenario "
        f"{str(digest['scenario_digest'])[:12]}; "
        + fit("BTC/USD buy-and-hold", digest["btc"])
        + "; "
        + fit("held-pairs basket", digest["basket"])
    )


def _alpha_pipeline(attribution: ModuleType, config: Any, tmp: Path) -> tuple[Any, Outcome | None]:
    """A fabricated six-day run through the real store, the real partition reader and the
    real report, returned as the JSON digest spec 143 would commit.

    The run is the subject and is fabricated; the store, its row models, the report and the
    partition reader are the real ones. A bar tick every fifteen minutes, one position held
    over days 1 to 4 with the equity moving only then, so days 0 and 5 are flat, and a BTC
    tape with a trade every bar. The report's window must be exactly the run's.
    """
    contracts, problem = try_import("acsoe.clients.store.contracts")
    if contracts is None:
        return None, problem or pending("clients.store.contracts does not exist yet")
    import polars as pl

    db_path, store_cls, problem = _migrated_db(tmp, "alpha-pipeline.sqlite")
    if db_path is None:
        return None, problem or pending("the store could not be migrated")
    bar_s = int(config.get("timeframes.decision_bar_s"))
    start_s = 1_720_224_000  # 2024-07-06 00:00 UTC, a Saturday and a partition week's start
    bars = 6 * 86_400 // bar_s
    partitions = tmp / "trades_weekly"
    weeks: dict[str, dict[str, int]] = {}
    for archive, base in (("XBTUSD", 57_000.0), ("AAAUSD", 2.0)):
        (partitions / archive).mkdir(parents=True)
        stamps = [start_s + k * bar_s for k in range(bars + 1)]
        prices = [f"{base * (1 + 0.004 * math.sin(k / 7.0) + 0.0001 * k):.4f}" for k in range(bars + 1)]
        pl.DataFrame({"ts": stamps, "price": prices, "volume": ["1"] * len(stamps)}).write_parquet(
            partitions / archive / "2024-07-06.parquet"
        )
        weeks[archive] = {"2024-07-06": len(stamps)}
    manifest = partitions / "manifest.json"
    manifest.write_bytes(json.dumps({"pairs": {a: {"weeks": w} for a, w in weeks.items()}}).encode())
    names = tmp / "pair_names.json"
    names.write_bytes(
        json.dumps(
            {"pairs": {"XBTUSD": {"v2_symbol": "BTC/USD"}, "AAAUSD": {"v2_symbol": "AAA/USD"}}}
        ).encode()
    )

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    description = {
        "kind": "acsoe-replay-scenario",
        "fee": {"tier": 3},
        "ranking": "expected_move",
        "partitions": {
            "manifest": manifest.relative_to(tmp).as_posix(),
            "sha256": sha(manifest),
            "archive_pairs_without_rules": ["ZZZUSD"],
        },
        "pair_rules": {"files": [{"file": names.relative_to(tmp).as_posix(), "sha256": sha(names)}]},
    }
    text = json.dumps(description, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    store = store_cls(db_path)
    try:
        store.start_run(
            "replay-verify-alpha", mode="replay", started_at=start_s * 1_000_000,
            scenario_digest=hashlib.sha256(text.encode("ascii")).hexdigest(),
            scenario_description=text,
        )
        level = Decimal("10000")
        for k in range(bars + 1):
            ts = (start_s + k * bar_s) * 1_000_000
            if 96 <= k < 480 and k % 5 == 0:
                level += Decimal("1.5") if k % 3 else Decimal("-0.9")
            store.write_equity_snapshot(
                contracts.EquitySnapshotRow(
                    cycle_id=k + 1, run_id="replay-verify-alpha", ts=ts, currency="USD",
                    equity=level, peak_equity=level, cash=level, positions_value=Decimal(0),
                    unrealised_pnl=Decimal(0), realised_pnl_cum=Decimal(0),
                    open_position_count=0, cash_source=contracts.CashSource.CYCLE_START,
                    updated_at=ts,
                )
            )
        opened, closed = (start_s + 96 * bar_s) * 1_000_000, (start_s + 480 * bar_s) * 1_000_000
        store.write_position(
            contracts.PositionRow(
                position_id="verify-alpha-1", run_id="replay-verify-alpha", cycle_id=97,
                pair="AAA/USD", base="AAA", quote="USD",
                status=contracts.PositionStatus.CLOSED, qty=Decimal("10"),
                entry_price=Decimal("2"), target_price=Decimal("2.06"),
                stop_price=Decimal("1.97"), timeout_at=closed, opened_at=opened,
                closed_at=closed, updated_at=closed,
            )
        )
    finally:
        store.close()
    report = attribution.attribute(
        db_path, marks=attribution.marks_from_description(description, tmp), decision_bar_s=bar_s
    )
    digest = json.loads(json.dumps(report.to_dict()))
    window = (start_s * 1_000_000, (start_s + bars * bar_s) * 1_000_000)
    stated = (digest.get("window_start_us"), digest.get("window_end_us"))
    if stated != window:
        return None, failed(
            f"the report's window is {_alpha_iso(int(stated[0]))} to {_alpha_iso(int(stated[1]))} "
            f"for a fabricated run spanning {_alpha_iso(window[0])} to {_alpha_iso(window[1])}: "
            "the benchmark is not following the run's own window"
        )
    return digest, None


def check_backtest_emits_alpha_report(ctx: VerifyContext) -> Outcome:
    """The Phase 7 row's first clause: an alpha-versus-benchmark report from the full equity
    curve including cash periods, judged on the committed digest of each real run.

    `data/` is gitignored, so each run is judged through the digest spec 143 commits under
    `tests/fixtures/phase7/` (`run-digest-*.json`, the JSON of spec 138's report), checked
    for internal consistency by `_alpha_digest_problems`. Before any digest is read, a
    fabricated six-day run is taken through the real store, partition reader and report, and
    its digest must pass the same check, so the check is shown to accept a genuine report on
    a fresh clone. PENDING until a digest is committed, which is after the run ends.

    **The one-day pipeline run spec 141 names is this criterion's `--live` half** (lead
    ruling 2026-09-19): the chain needs each fold's model artefacts, which live under the
    gitignored `models/`, so it cannot run on a fresh clone. The fresh-clone half is the
    fabricated run and the digest check above. The `--live` half is not built yet.
    """
    with root_import_path(ctx.root):
        attribution, problem = try_import("acsoe.research.attribution")
        if attribution is None:
            if problem is not None and problem.result is Result.FAIL:
                return problem
            return pending(
                "acsoe.research.attribution does not exist yet (spec 138, alpha against both "
                "benchmarks)"
            )
        for attr in ("attribute", "regress_digest", "marks_from_description", "newey_west_rule"):
            if not callable(getattr(attribution, attr, None)):
                return pending(f"acsoe.research.attribution has no {attr} yet (spec 138)")
        config, problem = _phase3_config()
        if config is None:
            return problem or pending("the committed config could not be loaded")
        with tempfile.TemporaryDirectory(prefix="acsoe-verify-alpha-") as raw_tmp:
            try:
                fabricated, problem = _alpha_pipeline(attribution, config, Path(raw_tmp))
            except attribution.AttributionError as exc:
                return failed(
                    "the report refused a fabricated run taken through the real store: "
                    + str(exc)[:300]
                )
            if fabricated is None:
                return problem or pending("the fabricated run could not be built")
            own = _alpha_digest_problems(attribution, fabricated)
        if own:
            return failed(
                "a fabricated run taken through the real store and report produced a digest "
                "the consistency check refuses: " + "; ".join(own[:3])
            )
        digests = sorted((ctx.root / ALPHA_DIGESTS).glob(ALPHA_DIGEST_GLOB))
        if not digests:
            return pending(
                "no committed digest of a Phase 7 run exists yet under tests/fixtures/phase7/ "
                "(spec 143 commits one per run when it ends); the report pipeline itself ran "
                "on a fabricated six-day run and its digest checked consistent"
            )
        verdicts = []
        for path in digests:
            try:
                digest = json.loads(path.read_bytes().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                return failed(f"{path.name} is not JSON: {exc}")
            found = _alpha_digest_problems(attribution, digest)
            if found:
                return failed(f"{path.name}: " + "; ".join(found[:4]))
            verdicts.append(f"{path.name}: {_alpha_digest_summary(digest)}")
    return passed(
        f"{len(digests)} run digest(s), each internally consistent (whole-day grid from the "
        "run's own window, every day regressed with flat days included, every decision bar "
        "carrying an equity row, both fits recomputed from the series, the scenario digest the "
        "sha256 of its description). " + " | ".join(verdicts)
    )


def check_research_screens_render(ctx: VerifyContext) -> Outcome:
    """The Phase 7 row's third clause: the leaderboard and SHAP view render from a seeded
    database, the SHAP rows written by engine 19. PENDING until spec 140 lands the writer:
    nothing writes a SHAP row today, so there is nothing for the view to render."""
    del ctx
    return pending(
        "nothing writes a SHAP row yet, so the SHAP view has nothing to render (spec 140, the "
        "SHAP writer and the research screens)"
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
register(
    2,
    Criterion(
        "candles_match_independent_reduction_of_recorded_trades",
        check_candles_match_independent_reduction_of_recorded_trades,
    ),
)
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
# Operator ruling 1, 2026-09-12. The splitter that passed the criterion above trained
# on both sides of the test window; nothing in the gate could see it, because the
# criterion above places every row by hand and never builds a fold with a future.
register(
    4,
    Criterion(
        "walkforward_trains_on_the_past_only",
        check_walkforward_trains_on_the_past_only,
    ),
)
register(4, Criterion("console_history_reads_real_rows", check_console_history_reads_real_rows))
# `--live` only, and never required for green. It reports PENDING rather than FAIL
# when no archive is present: the operator has not downloaded one, and an opt-in
# criterion that FAILs on its absence makes `--live` useless for every other check.
register(4, Criterion("replay_full_archive", check_replay_full_archive, live=True))

# Phase 5 - models. Spec 60, registered first in the phase and ahead of most of what it
# judges, for the reason spec 00 was first in Phase 0, spec 16 in Phase 1, spec 45 in
# Phase 3 and spec 48 in Phase 4. Until these existed `--phase 5` registered
# `docs_vocabulary` and `toolchain_green` alone and printed "Phase 5 is green: every
# criterion PASS, zero PENDING" over a phase that by then held a feature package, three
# engines and a ranking function. A phase with real code in it and nothing judging it
# must not be able to report as finished, and PENDING is how it says so.
#
# **Phase 5 fails quietly**, which is why these are shaped differently from earlier
# phases'. Every phase before this one failed loudly. Here a DI fitted on the wrong rows
# vetoes ordinary markets and flatters what survives; a leaked feature makes the Brier
# beautiful; a metric that flatters is simply believed. Nothing crashes and nothing goes
# red. So each criterion is written against a *named* wrong implementation rather than
# against the shape of the evidence, and the three that matter most assert row
# **identity** rather than row counts - a count passes whenever two sets happen to be the
# same size, which is exactly what a DI fitted on the BUY subset looks like on a fold
# where most calls are BUY.
#
# Accuracy is computed nowhere in this file. The base rate is 23.89% and a model that
# always predicts `stop` scores 51%, so a criterion reporting accuracy would be reporting
# the model that never trades. Operator ruling, 2026-09-12.
register(5, Criterion("features_reproduce_in_replay", check_features_reproduce_in_replay))
register(
    5,
    Criterion(
        "feature_lookbacks_are_time_not_rows", check_feature_lookbacks_are_time_not_rows
    ),
)
register(
    5,
    Criterion(
        "predictor_trains_and_calibrates", check_predictor_trains_and_calibrates
    ),
)
register(
    5,
    Criterion(
        "training_is_reproducible_from_config_and_data",
        check_training_is_reproducible_from_config_and_data,
    ),
)
register(
    5,
    Criterion(
        "di_fitted_on_predictor_training_set", check_di_fitted_on_predictor_training_set
    ),
)
register(
    5,
    Criterion(
        "di_leave_one_out_excludes_48_bars", check_di_leave_one_out_excludes_48_bars
    ),
)
register(
    5,
    Criterion(
        "skeptic_trains_only_on_predictor_buy_rows",
        check_skeptic_trains_only_on_predictor_buy_rows,
    ),
)
register(
    5,
    Criterion(
        "walkforward_weekly_retrain_reports_oos",
        check_walkforward_weekly_retrain_reports_oos,
    ),
)
register(
    5,
    Criterion("anomaly_and_skeptic_have_both_tests", check_anomaly_and_skeptic_have_both_tests),
)
register(
    5,
    Criterion("scout_ranks_by_feature_not_arrival", check_scout_ranks_by_feature_not_arrival),
)
register(
    5,
    Criterion(
        "tournament_writes_leaderboard_from_oos",
        check_tournament_writes_leaderboard_from_oos,
    ),
)
# Re-registered under phase 5 unchanged, so that the Phase 5 gate itself goes red if a
# Phase 5 change weakens the past-only walk-forward. `research/walkforward.py` is read by
# spec 67 and never edited; this is what makes that instruction enforceable rather than
# remembered. Operator ruling 1 of 2026-09-12.
register(
    5,
    Criterion(
        "walkforward_trains_on_the_past_only",
        check_walkforward_trains_on_the_past_only,
    ),
)

# Phase 6 - decision and execution. Spec 100, registered first in the phase and ahead of
# every subject it judges, for the reason spec 00 was first in Phase 0, spec 16 in Phase
# 1, spec 45 in Phase 3, spec 48 in Phase 4 and spec 60 in Phase 5. Until these existed
# `--phase 6` registered `docs_vocabulary` and `toolchain_green` alone and printed "Phase
# 6 is green: every criterion PASS, zero PENDING" over a phase in which engines 16, 18
# and 22 were unbuilt and nothing had ever placed an order. A phase with nothing in it
# must not be able to report as finished, and PENDING is how it says so.
#
# Registered while every one of them is PENDING, and deliberately: B builds engines 16,
# 18 and 22 against these rather than after them, which is the whole reason spec 100 sits
# in wave 2 of a phase whose engines land in wave 3.
register(6, Criterion("paper_trade_round_trip_target", check_paper_trade_round_trip_target))
register(6, Criterion("paper_trade_round_trip_stop", check_paper_trade_round_trip_stop))
register(6, Criterion("paper_trade_round_trip_timeout", check_paper_trade_round_trip_timeout))
register(
    6,
    Criterion(
        "unfilled_entry_cancels_without_chasing",
        check_unfilled_entry_cancels_without_chasing,
    ),
)
register(
    6,
    Criterion(
        "triggered_stop_holds_on_data_guard_block",
        check_triggered_stop_holds_on_data_guard_block,
    ),
)
register(
    6,
    Criterion("escalation_completes_during_outage", check_escalation_completes_during_outage),
)
register(6, Criterion("console_shows_position_live", check_console_shows_position_live))
register(
    6,
    Criterion(
        "order_book_slippage_on_recorded_book",
        check_order_book_slippage_on_recorded_book,
    ),
)
register(
    6,
    Criterion(
        "adaptive_router_weights_on_fixture", check_adaptive_router_weights_on_fixture
    ),
)
# Spec 105, operator ruling 2026-09-16 on A's spec 87 finding 1: the assertion that would
# have caught every paper fill freezing the account. Registered after spec 100's nine and
# runnable today, because the operator wanted PASS and FAIL observable before spec 82.
register(
    6,
    Criterion(
        "paper_equity_continuous_across_fill", check_paper_equity_continuous_across_fill
    ),
)
# Operator ruling 2026-09-17 on the exit-tick equity finding (spec 100 bodies): the
# observable form of the defect, registered and observed FAIL before specs 113 and 114.
register(
    6,
    Criterion(
        "equity_row_never_values_positions_it_does_not_hold",
        check_equity_row_never_values_positions_it_does_not_hold,
    ),
)

# Phase 7 - evaluation. Spec 141, registered PENDING-first ahead of the subjects it judges,
# for the reason every phase since Phase 0 has done so: a phase with nothing in it must
# not be able to report as finished. The row's three clauses first, in the row's order,
# then invariant 2's amendment of 2026-09-19.
register(7, Criterion("backtest_emits_alpha_report", check_backtest_emits_alpha_report))
register(
    7,
    Criterion("promotion_gate_rejects_haircut_edge", check_promotion_gate_rejects_haircut_edge),
)
register(7, Criterion("research_screens_render", check_research_screens_render))
register(7, Criterion("fee_scenario_is_replay_only", check_fee_scenario_is_replay_only))


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


def make_console_utf8() -> list[str]:
    """Make this process's own stdout and stderr able to carry a verdict.

    **The gate could not print its own house style, and the two had never met.** On
    2026-09-18 `verify.py --phase 6 > log 2>&1` died mid-run with
    `UnicodeEncodeError: 'charmap' codec can't encode character '\\u2212'`: a redirected
    stream on Windows is opened with `locale.getencoding()`, which is cp1252 here, and
    cp1252 has no minus sign. `ui-context.md` rule 6 *requires* U+2212 in numeric output
    and `console_shows_position_live` quotes the figures it checked, so its PASS message
    was the first criterion message ever to contain one. Seven criteria had printed; the
    other six never ran and the phase result was never reported.

    Note the shape of that failure: not a wrong verdict but a **lost** one, exiting 1 -
    the same code a real FAIL returns - so a reader with only the exit code would have
    concluded the phase was red on its merits.

    **`errors="backslashreplace"`, not `strict`, and that is not belt-and-braces.** UTF-8
    encodes every code point *except* a lone surrogate, and lone surrogates reach this
    program by an ordinary route: `os.fsdecode` maps undecodable filesystem bytes to the
    surrogate range, and criterion messages embed paths - `toolchain_green`'s "full
    output: ..." is one. Strict UTF-8 would therefore still be able to kill a run, on a
    rarer input, which is the worst version of this bug rather than a fixed one.
    `backslashreplace` also keeps the information: the escape names the code point, where
    `replace` would discard it, and a tool whose purpose is not losing a diagnosis should
    not lose one here either.

    Returns what it could not change, for the caller to report. Never raises: a stream
    that cannot be reconfigured - already wrapped, replaced by a test, a pipe someone
    handed us - is not a reason to refuse to run the gate, and on such a stream the old
    behaviour is exactly what happens today.

    Called from `main()` and **never at import**: `tests/verify/` imports this module, and
    mutating global streams at import time would fight pytest's capture.
    """
    unchanged: list[str] = []
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            unchanged.append(name)
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            unchanged.append(name)
    return unchanged


def main(argv: Sequence[str] | None = None) -> int:
    # Before the first `print`, and before anything that could raise into a traceback.
    unprintable = make_console_utf8()

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
    if unprintable:
        # Said rather than swallowed. On such a stream a verdict carrying a character the
        # locale encoding cannot represent will still kill the run, and the reader needs
        # to know that before it happens rather than from the traceback afterwards.
        print(
            "WARNING: "
            + " and ".join(unprintable)
            + " could not be set to UTF-8; a verdict containing a character this "
            + "locale cannot encode will end the run",
            flush=True,
        )
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
