"""`modelling/` is a leaf: it imports nothing from `acsoe` except `core/contracts.py`.

Architecture invariant 5 keeps the live loop and `research/` from importing each other.
`modelling/` is the operator's exception of 2026-09-12 — the one package both sides may
import — and the exception only holds while the package stays a leaf. The moment
something here imports an engine, a client or `platform/`, importing it from the other
side drags that dependency across the boundary the invariant exists to keep, and it does
so silently: nothing fails, the import simply succeeds.

So the rule is asserted on the import graph rather than trusted to review, and the
detector is proved capable of failing against a mutated copy rather than only run against
a clean tree.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
PACKAGE = SRC / "acsoe" / "modelling"

#: The one `acsoe` module outside this package that `modelling/` may import. `core/` itself
#: imports nothing from the rest of the package (architecture invariant 0), so depending on
#: it drags nothing across with it — which is the whole reason it is the permitted one.
ALLOWED = "acsoe.core.contracts"

#: `modelling/` importing itself is not crossing anything, and it is how the package stays
#: one vocabulary rather than five modules that each redefine a feature name.
SELF = "acsoe.modelling"


def imported_acsoe_modules(root: Path) -> list[tuple[str, str]]:
    """Every `acsoe.*` module imported anywhere under `root`, as `(file, module)`.

    Read off the syntax tree rather than by grepping for the word `import`, so that a
    docstring explaining the rule — a sentence this package wants written — is not a hit.

    The module name is returned as data rather than baked into a formatted string, so
    that the allow-list below is a comparison against a module path and not a substring
    test. A substring test would accept `acsoe.core.contracts_evil` and, worse, would
    accept any line that merely *mentions* the allowed name.
    """
    found: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend(
                    (path.name, alias.name)
                    for alias in node.names
                    if alias.name.startswith("acsoe")
                )
            elif isinstance(node, ast.ImportFrom):
                # A relative import inside the package has no module prefix and is fine:
                # `modelling` importing `modelling` is not crossing anything.
                if node.level and not node.module:
                    continue
                module = node.module or ""
                if module.startswith("acsoe"):
                    found.append((path.name, module))
    return found


def offenders(root: Path) -> list[str]:
    return [
        f"{filename}: {module}"
        for filename, module in imported_acsoe_modules(root)
        if not _permitted(module)
    ]


def _permitted(module: str) -> bool:
    if module == ALLOWED or module.startswith(ALLOWED + "."):
        return True
    return module == SELF or module.startswith(SELF + ".")


def test_modelling_exists_where_this_test_thinks_it_does() -> None:
    """A detector pointed at nothing reports nothing wrong.

    `test_the_live_loop_does_not_import_research` learned this the expensive way in an
    earlier phase: the assertion has to fail when its subject moves, or it decays into a
    green line that checks a directory listing.
    """
    assert PACKAGE.is_dir(), PACKAGE
    assert sorted(p.name for p in PACKAGE.glob("*.py")) == [
        "__init__.py",
        "artefacts.py",
        "calibration.py",
        "di.py",
        "expected_move.py",
        "features.py",
        "macro.py",
        "weights.py",
    ]


def test_modelling_imports_nothing_from_acsoe_but_core_contracts() -> None:
    assert offenders(PACKAGE) == [], offenders(PACKAGE)


def test_the_detector_goes_red_when_a_forbidden_import_is_added(tmp_path: Path) -> None:
    """Proof the assertion above can fail, without writing into `src/`.

    Three agents share one checkout, so a transient mutation of a real source file is a
    hazard to whoever else is running the suite at that moment — a spurious failure in
    someone else's run reads as KILLED and hides a survivor. The real sources are copied,
    one forbidden import is added to the copy, and the same detector is run over both.
    """
    clean = tmp_path / "clean"
    clean.mkdir()
    for path in PACKAGE.glob("*.py"):
        (clean / path.name).write_bytes(path.read_bytes())

    mutated = tmp_path / "mutated"
    mutated.mkdir()
    for path in PACKAGE.glob("*.py"):
        (mutated / path.name).write_bytes(path.read_bytes())
    (mutated / "features.py").write_bytes(
        (mutated / "features.py").read_bytes()
        + b"\nfrom acsoe.clients.store.client import StoreClient\n"
    )

    assert offenders(clean) == []
    assert offenders(mutated) == ["features.py: acsoe.clients.store.client"]


def test_research_imports_no_engine() -> None:
    """The other half of invariant 5, and the rule both of this phase's near-misses broke.

    `research/` never imports the live loop path, and `engines/` is the live loop path. Two
    functions were written into an engine's `contracts.py` and then needed by
    `research/training.py` — the macro column names and the calibration application — and
    both had to move to `modelling/` before the trainer could use them. Neither would have
    raised: the offline builder would simply have grown its own copy, the two would have
    agreed for months, and the first divergence would have surfaced as a live probability
    differing from a backtested one with nothing pointing at the cause.

    `research/backtest.py` is engine 23 and legitimately imports `acsoe.core`; that is a
    different boundary and `tests/research/test_backtest.py` already pins it.
    """
    research = SRC / "acsoe" / "research"
    offenders = [
        f"{filename}: {module}"
        for filename, module in imported_acsoe_modules(research)
        if module == "acsoe.engines" or module.startswith("acsoe.engines.")
    ]
    assert offenders == [], offenders


def test_that_assertion_goes_red_when_an_engine_import_is_added(tmp_path: Path) -> None:
    """Proof the check above can fail, against a copy rather than the real tree.

    Three agents share this checkout, so a transient mutation of a real source file is a
    hazard to whoever else is running the suite — a spurious failure in their run reads as
    KILLED and hides a survivor.
    """
    copied = tmp_path / "research"
    copied.mkdir()
    (copied / "training.py").write_bytes(
        b"from acsoe.engines.macro_context.contracts import macro_column\n"
    )
    offenders = [
        module
        for _filename, module in imported_acsoe_modules(copied)
        if module.startswith("acsoe.engines")
    ]
    assert offenders == ["acsoe.engines.macro_context.contracts"]


def test_modelling_opens_no_client_reads_no_clock_and_holds_no_engine() -> None:
    """The other half of "leaf", and it is not implied by the import graph.

    A module could read the wall clock through `datetime.now()` or `time.time()` without
    importing anything from `acsoe` at all — invariant 9 is about the call, not the
    import — and a feature computed from wall time would reproduce differently in every
    replay while every import assertion stayed green.
    """
    forbidden_calls = {("datetime", "now"), ("datetime", "utcnow"), ("time", "time")}
    hits: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            owner = node.func.value
            name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
            if (name, node.func.attr) in forbidden_calls:
                hits.append(f"{path.name}:{node.lineno}: {name}.{node.func.attr}()")
    assert hits == [], hits
