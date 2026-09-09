"""Running one coroutine from synchronous code.

The exchange client is async — `code-standards.md` requires it, because a rate
limiter and a socket both want to await — and engines are synchronous, because
`BaseEngine.process` is. Something has to bridge that, and this is it, in one place
rather than in each engine that needs it.

``asyncio.run`` per call, deliberately, rather than a long-lived background loop.
The runtime loop ticks once a minute and an engine makes a handful of calls, so the
cost is a loop creation a minute; a persistent loop would be a thread and a
lifecycle to own, and a client bound to it would outlive the tick that created it.
``clients/kraken/rest.py`` opens its HTTP client per request for the same reason.

Calling this from *inside* a running loop raises rather than deadlocking. That
cannot happen from the runtime loop, which is synchronous throughout, but it can
happen from a test written with ``pytest.mark.asyncio``, and a silent deadlock there
is a hung suite with no traceback.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

__all__ = ["run_blocking"]

T = TypeVar("T")


def run_blocking(work: Coroutine[Any, Any, T]) -> T:
    """Run ``work`` to completion and return its result.

    Raises ``RuntimeError`` when an event loop is already running in this thread,
    after closing the coroutine so it does not also emit a "never awaited" warning
    that would bury the real message.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(work)
    work.close()
    raise RuntimeError(
        "run_blocking was called from inside a running event loop. Engines are "
        "synchronous and the runtime loop has no loop of its own; await the "
        "coroutine directly instead."
    )
