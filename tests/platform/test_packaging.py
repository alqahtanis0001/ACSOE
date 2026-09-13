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
    # Declared directly on the lead's ruling of 2026-09-13 for spec 70, and a row in
    # `context/architecture-context.md`'s stack table since `be497ce`. Engine 13 loads
    # the anomaly detector with it on the live loop path, so the daemon imports by name
    # a library that today arrives only because scikit-learn asks for it.
    #
    # It was in this set for about an hour before the document had the row, with a
    # comment saying so, because the assertion below exists to make a dependency
    # outside the document an escalation and a silent addition here would have been a
    # test quietly granting one. Both halves are in now, which is why that note is gone
    # rather than left to read as though it were still true.
    "joblib",
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


#: Moved out of the `research` extra on 2026-09-13, spec 61 step 2, on the
#: operator's confirmation of spec 59 decision 8. Engines 8, 13 and 15 import
#: them on the live loop path, so an extra a daemon cannot start without is a
#: base dependency by another name.
#:
#: Distribution name to import name, because they differ for one of the three and
#: asserting only the distribution names would leave the thing that actually has
#: to work untested.
LIVE_MODEL_LIBRARIES = {
    "lightgbm": "lightgbm",
    "scikit-learn": "sklearn",
    "shap": "shap",
}

#: What is left offline. `hmmlearn` is the optional HMM upgrade spec 66 puts out
#: of scope; `statsmodels` is Phase 7's attribution, which runs in `research/`.
OFFLINE_ONLY_LIBRARIES = {"hmmlearn", "statsmodels"}


def _dependency_sets() -> tuple[set[str], set[str], set[str]]:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    base = {_requirement_name(spec) for spec in project["dependencies"]}
    research = {_requirement_name(spec) for spec in project["optional-dependencies"]["research"]}
    dev = {_requirement_name(spec) for spec in project["optional-dependencies"]["dev"]}
    return base, research, dev


def test_the_model_libraries_are_base_dependencies() -> None:
    """Spec 61 step 2. The split is live-loop versus offline, not ML versus not.

    Engines 8, 13 and 15 run in the opportunity chain and import these at load
    time: the predictor and the skeptic are LightGBM, the scaler and the anomaly
    detector are scikit-learn, and engine 8 publishes SHAP attributions on every
    decision. Left in an extra, a fresh clone that followed the README's base
    install would start, tick, and discover it at the moment a gate needed to run.
    """
    base, research, _ = _dependency_sets()
    for distribution in LIVE_MODEL_LIBRARIES:
        assert distribution in base, (
            f"{distribution} is imported on the live loop path and must be a base "
            "dependency, not an extra"
        )
        assert distribution not in research


@pytest.mark.parametrize(("distribution", "module"), sorted(LIVE_MODEL_LIBRARIES.items()))
def test_a_base_model_library_actually_imports(distribution: str, module: str) -> None:
    """Imported for real, and deliberately **not** through `pytest.importorskip`.

    `importorskip` re-raises an `ImportError` from inside a module but *skips* a
    `ModuleNotFoundError` — so a dependency moving back into an extra would turn
    every test behind it green-by-absence, under a reason string that is no longer
    true. That is the exact failure mode `code-standards.md` records. A missing
    base dependency has to be a failure here, because it is a failure in the
    daemon.
    """
    assert importlib.import_module(module) is not None, distribution


def test_the_research_extra_is_exactly_the_offline_libraries() -> None:
    """The extra still exists and still means something, which is the other half.

    Architecture invariant 5 is what it expresses: the live loop never imports
    from `research/`. A name belongs here when no engine in the guard, opportunity
    or manage chain can reach it. Asserted as an exact set so that moving a fourth
    library up into the base install is a decision somebody makes rather than a
    line somebody deletes.
    """
    base, research, dev = _dependency_sets()

    assert research == OFFLINE_ONLY_LIBRARIES
    assert not (base & research)
    assert "acsoe" in dev, "dev must include the research extra so [dev] installs everything"


def test_expected_directories_exist() -> None:
    for relative in ("db/migrations", "config", "feature-specs", "scripts", "src/acsoe"):
        assert (REPO_ROOT / relative).is_dir(), relative
