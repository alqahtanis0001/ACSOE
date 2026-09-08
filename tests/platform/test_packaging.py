"""Spec 03 — the package installs and every subpackage imports.

Nothing else in Phase 0 can be reported complete until this passes: B's store
client and C's harness both import `acsoe`.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

SUBPACKAGES = [
    "acsoe.core",
    "acsoe.platform",
    "acsoe.engines",
    "acsoe.clients",
    "acsoe.clients.kraken",
    "acsoe.clients.store",
    "acsoe.clients.recorder",
    "acsoe.research",
    "acsoe.console",
    "acsoe.cli",
]

# The stack table of context/architecture-context.md, minus sqlite3 which is
# stdlib, plus pyyaml which the lead added to that table after C escalated that
# config/default.yaml had no parser. A dependency outside this set is an
# escalation to the lead, so the test asserts the set rather than trusting a
# reviewer to notice.
STACK_TABLE = {
    "websockets",
    "httpx",
    "tenacity",
    "pydantic",
    "polars",
    "numpy",
    "lightgbm",
    "scikit-learn",
    "hmmlearn",
    "shap",
    "statsmodels",
    "pyarrow",
    "duckdb",
    "orjson",
    "fastapi",
    "uvicorn",
    "structlog",
    "pytest",
    "pytest-asyncio",
    "hypothesis",
    "pyyaml",
    # Tooling required by context/code-standards.md's four verification commands.
    "mypy",
    "ruff",
    "types-pyyaml",
    # The extras self-reference that makes `dev` install `research`.
    "acsoe",
}


def _requirement_name(spec: str) -> str:
    """Strip version bounds, extras and markers from a requirement string."""
    head = spec.split(";", 1)[0].strip()
    for separator in (">=", "<=", "==", "!=", "~=", ">", "<", "["):
        head = head.split(separator, 1)[0]
    return head.strip().lower()


def test_acsoe_imports() -> None:
    acsoe = importlib.import_module("acsoe")
    assert acsoe.__version__


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name: str) -> None:
    assert importlib.import_module(name) is not None


def test_package_is_typed() -> None:
    """`py.typed` must ship, or mypy --strict cannot see the package's types."""
    acsoe = importlib.import_module("acsoe")
    package_dir = Path(next(iter(acsoe.__path__)))
    assert (package_dir / "py.typed").is_file()


def test_no_dependency_outside_the_stack_table() -> None:
    """A dependency not in `architecture-context.md` is an escalation, not a commit."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    declared = {_requirement_name(spec) for spec in project["dependencies"]}
    for extra in project["optional-dependencies"].values():
        declared |= {_requirement_name(spec) for spec in extra}

    assert declared <= STACK_TABLE, f"outside the stack table: {sorted(declared - STACK_TABLE)}"


def test_research_libraries_are_not_base_dependencies() -> None:
    """Architecture invariant 5: the live loop never imports from research/.

    The packaging says so too — the model libraries live in the `research`
    extra, and `dev` pulls that extra in so the README's setup line stays true.
    """
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    base = {_requirement_name(spec) for spec in project["dependencies"]}
    research = {_requirement_name(spec) for spec in project["optional-dependencies"]["research"]}
    dev = {_requirement_name(spec) for spec in project["optional-dependencies"]["dev"]}

    assert research == {"scikit-learn", "lightgbm", "hmmlearn", "shap", "statsmodels"}
    assert not (base & research)
    assert "acsoe" in dev, "dev must include the research extra so [dev] installs everything"


def test_expected_directories_exist() -> None:
    for relative in ("db/migrations", "config", "feature-specs", "scripts", "src/acsoe"):
        assert (REPO_ROOT / relative).is_dir(), relative
