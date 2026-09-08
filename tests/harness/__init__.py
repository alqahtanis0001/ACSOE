"""Shared test harness for ACSOE.

Owner: C - Interface and models. Specs 14 and 15.

Everything in here is a *test double*. Nothing in this package is imported by
`src/acsoe/`, and no value defined here is a system default. In particular the
recorded Kraken fixtures under `tests/fixtures/kraken/` are invented numbers for a
fake exchange - never a fee, a minimum, a tick size or a precision the system may
fall back on. Invariant 2 and the rules at the top of `AGENTS.md` both say those
come from the exchange at runtime or the trade is blocked.

Submodules are imported lazily by the things that need them so that importing this
package stays cheap and dependency-free: `scripts/verify.py` reaches in for
`build_verify_doubles()` on a tree where most of `src/acsoe/` may not exist yet.
"""
