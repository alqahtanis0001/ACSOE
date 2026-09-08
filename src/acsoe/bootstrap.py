"""Engine registry and wiring. Lead-only.

The three runtime chains, in the fixed order of the registry table in
``context/engine-contracts.md``. Every new engine is registered here, and every
registration goes through the lead.

**Phase 0 registers nothing.** All three chains are empty, which is valid: the
orchestrator skips an unregistered engine and an empty chain runs cleanly. Engines
arrive from Phase 2 onward.

This module must never import from ``acsoe.research``. Engines 20 ``tournament`` and 23
``backtest`` run in an offline chain assembled in ``acsoe.cli.research``, which is what
keeps the live loop path free of research imports and architecture invariant 5 true.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from acsoe.core.contracts import Chains

if TYPE_CHECKING:
    from acsoe.core.contracts import BaseEngine

__all__ = [
    "GUARD_CHAIN",
    "MANAGE_CHAIN",
    "OPPORTUNITY_CHAIN",
    "build_chains",
]


#: Engines 1, 2, 3, 4, 17. Every tick, every mode, never breaks early.
#: Ingestion plus the account-level circuit breaker. Freeze must not stop data
#: collection, and a bad-data block must not stop ``safety`` evaluating.
GUARD_CHAIN: tuple[BaseEngine, ...] = ()

#: Engines 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18. Only when the mode is
#: ``running`` and nothing has blocked. Stops at the first block or PASS.
OPPORTUNITY_CHAIN: tuple[BaseEngine, ...] = ()

#: Engines 21, 22, 19. Every tick, every mode. Watches positions, exits them, records
#: everything — including on the fourteen ticks in fifteen where no bar closed.
MANAGE_CHAIN: tuple[BaseEngine, ...] = ()


def build_chains() -> Chains:
    """Assemble the three runtime chains for the orchestrator.

    A named structure rather than three positional sequences: transposing ``guard`` with
    ``manage`` would type-check, pass a smoke test, and silently stop watching open
    positions.
    """
    return Chains(
        guard=GUARD_CHAIN,
        opportunity=OPPORTUNITY_CHAIN,
        manage=MANAGE_CHAIN,
    )
