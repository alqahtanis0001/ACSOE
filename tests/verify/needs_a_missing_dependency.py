"""A module that cannot import because a *third-party* package is absent.

Not a test, and deliberately not named `test_*` so pytest never collects it. It
exists so `test_a_missing_project_dependency_is_fail_not_pending` can prove the
one distinction `try_import` is built around, against a real `ModuleNotFoundError`
raised by a real import rather than a fabricated exception:

* a module of *ours* that has not been written yet is **PENDING** - the subject
  does not exist;
* a declared dependency the interpreter does not have is **FAIL** - the
  environment is broken, and reporting that as orderly progress lets a phase sit
  at "no FAIL" while nothing is being checked.

`exc.name` is what separates them, and it is the import machinery that sets it.
Asserting on a hand-built exception would be asserting on my own assumption about
what CPython puts there.
"""

import no_such_third_party_package  # type: ignore[import-not-found]  # noqa: F401
