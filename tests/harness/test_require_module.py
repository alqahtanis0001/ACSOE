"""`require_module` skips for the right reason, and `pytest.importorskip` did not.

Found by A on 2026-09-10, sweeping the harness for tests that cannot fail.

`pytest.importorskip` is right about a module that has not been written yet and wrong
about one that is written and cannot import, and it cannot tell them apart: a
`ModuleNotFoundError` raised from *inside* a module — a dependency moved to an extra,
an optional import added — reaches the same handler as the module's own absence.

The scale is why it matters here rather than being a curiosity. **About 370 test
functions**, roughly a third of the suite, reach a fixture in `tests/conftest.py`
guarded that way: `store`, `seeded_db`, `seed_fixtures`, `migrated_db`, `seed_clock`,
`fake_clients_with_store`, `engine_context`. All of them would vanish, the run would
report **green**, and the skip reason would read "the store client does not exist yet"
— false, and pointing whoever read it away from the real cause. A green suite that has
quietly stopped testing is the worst shape this project keeps finding.

A raised the same thing about `pytest.importorskip` masking a *broken* module and was
glad to be wrong: an `ImportError` from inside a module is re-raised by pytest 9.1.1.
It is `ModuleNotFoundError` specifically that is swallowed, which is the one an absent
dependency produces. The last test here pins that, so if pytest ever changes its
behaviour the replacement stops being justified from a red test rather than from
somebody's memory.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.outcomes import Skipped

from tests.conftest import require_module

#: A module that imports a dependency nobody has. Written into a temporary package so
#: the fault is real rather than simulated - the import system does the raising.
NEEDS_A_MISSING_DEPENDENCY = "import a_dependency_nobody_installed\n"


def fabricate_broken_package(root: Path, name: str) -> None:
    package = root / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "needs_something.py").write_text(NEEDS_A_MISSING_DEPENDENCY, encoding="utf-8")


def test_an_absent_module_still_skips() -> None:
    """The behaviour that must not regress. Unwritten work skips, carrying its reason.

    This is the case `importorskip` was chosen for and it is still right: several
    suites run against trees where a package genuinely has not been written, and a
    skip is the honest answer there.
    """
    with pytest.raises(Skipped) as caught:
        require_module("acsoe.engines.nothing_here.contracts", reason="not written yet")
    assert "not written yet" in str(caught.value)


def test_a_module_that_exists_and_cannot_import_is_raised_not_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The discrimination `pytest.importorskip` cannot make.

    The module is on disk and its own import fails on a *different* missing name. That
    is a broken environment and must reach the operator as the error it is — skipping
    reports finished work as unfinished and hides the fault behind a sentence about
    Phase 0.
    """
    fabricate_broken_package(tmp_path, "brokenpkg")
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(ModuleNotFoundError) as caught:
        require_module("brokenpkg.needs_something", reason="brokenpkg does not exist yet")
    assert caught.value.name == "a_dependency_nobody_installed"


def test_the_helper_it_replaced_would_have_swallowed_that(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative half, so the replacement is not taken on trust.

    The same fabricated module through `pytest.importorskip`. It skips — silently,
    with a reason about a package that exists. If this ever stops skipping, pytest has
    changed and `require_module` no longer earns its place, which is worth learning
    from a red test.
    """
    fabricate_broken_package(tmp_path, "brokenpkg2")
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(Skipped):
        pytest.importorskip("brokenpkg2.needs_something", reason="does not exist yet")


def test_a_submodule_of_an_absent_package_still_skips() -> None:
    """The prefix case, which the naive `exc.name == name` test gets wrong.

    Importing `acsoe.engines.nothing_here.contracts` when the *package* is missing
    raises with `name` set to the package, not to the full dotted path. Treating that
    as "some other dependency is missing" would turn every genuinely-unwritten module
    into a hard error and make a criterion impossible to register ahead of its
    subject — which is the whole working method of this project.
    """
    with pytest.raises(Skipped):
        require_module("acsoe.engines.nothing_here.deeper.still", reason="not written yet")


def test_the_real_shared_fixtures_import_for_real() -> None:
    """The assertion that makes the session check meaningful rather than decorative.

    `pytest_sessionstart` aborts the run if one of these is on disk and unimportable.
    That guard is itself a branch nobody would notice going dead, so this asserts the
    modules the shared fixtures need are importable *here and now* — which is the
    thing the 370 tests are silently relying on.
    """
    for dotted in (
        "acsoe.core.contracts",
        "acsoe.clients.store.client",
        "acsoe.clients.store.migrations",
        "acsoe.clients.store.seed",
    ):
        assert require_module(dotted, reason=f"{dotted} does not exist yet") is not None
