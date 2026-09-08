"""Test package root.

`tests/` is a package on purpose. It gives `tests.harness.*` one module identity no
matter who imports it - pytest collecting a test file, `tests/conftest.py`, or
`scripts/verify.py` reaching in for `build_verify_doubles()`. Without it the same
module can be imported twice under two names, and two copies of `KrakenAPIError`
make an `isinstance` check fail for reasons nobody enjoys diagnosing.

Each agent owning a test area should add an `__init__.py` to it for the same
reason, and because two agents will eventually both write `test_config.py`.
"""
