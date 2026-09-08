"""Fabricated trees for the verify tests.

Every criterion takes its repository root as a parameter rather than reading a
module-level constant, which is what makes these fixtures possible: a criterion
can be pointed at a directory built for the occasion and asked what it thinks.

Two shapes are used throughout.

`bare_tree` is a checkout with the *documents* and nothing built - which is the
honest meaning of "empty tree" here, since `context/`, `AGENTS.md` and `README.md`
are always present and it is `src/`, `db/migrations/` and `config/` that arrive
later. Every Phase 0 criterion must report PENDING against it and none may raise.

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


@pytest.fixture
def bare_tree(tmp_path: Path, repo_root: Path) -> Path:
    """A checkout carrying the documents and nothing that has been built yet."""
    shutil.copytree(repo_root / "context", tmp_path / "context")
    for name in ("AGENTS.md", "README.md"):
        shutil.copy(repo_root / name, tmp_path / name)
    return tmp_path


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
