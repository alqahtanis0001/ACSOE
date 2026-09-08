"""``acsoe research`` — run the offline chain.

**This file, not ``bootstrap.py``, is where engines 20 ``tournament`` and 23
``backtest`` are registered**, from Phase 4 onward. That is what keeps
architecture invariant 5 true: the live loop never imports from ``research/``,
because the only module that assembles the offline chain is a CLI entry point the
daemon never loads.

In Phase 0 the chain is empty and this command says so and exits zero. An empty
chain is a valid chain, and reporting "no offline engines registered" is an
honest answer rather than an error.

``build_offline_chain`` is importable without running the CLI, because
``scripts/verify.py``'s ``is_gate_matches_registry`` criterion has to inspect
engines 20 and 23 and cannot reach them through ``bootstrap.py``.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

#: The offline chain, in registry order. Empty in Phase 0.
#:
#: From Phase 4 this holds engine 20 `tournament` and engine 23 `backtest`, in
#: that order. Nothing here may ever be added to `bootstrap.py`.
OFFLINE_CHAIN: tuple[Any, ...] = ()


def build_offline_chain() -> tuple[Any, ...]:
    """Return the offline chain in registry order.

    Called by ``acsoe research`` and by ``scripts/verify.py``. Empty in Phase 0.
    """
    return OFFLINE_CHAIN


def run(args: argparse.Namespace) -> int:
    chain = build_offline_chain()
    if not chain:
        print(
            "acsoe research: no offline engines are registered. "
            "Engine 20 (tournament) and engine 23 (backtest) are registered here "
            "from Phase 4 onward; the offline chain is empty until then.",
            file=sys.stdout,
        )
        return 0

    # Phase 4 onward. Kept minimal on purpose: the offline chain has no guard,
    # no manage chain and no persistent state, so there is nothing here for the
    # orchestrator to do.
    print(f"acsoe research: running {len(chain)} offline engine(s) from {args.config}.")
    for engine in chain:
        print(f"  - {getattr(engine, 'name', engine)}")
    return 0
