"""Engine registry and wiring. Lead-only.

The three runtime chains, in the fixed order of the registry table in
``context/engine-contracts.md``. Every new engine is registered here, and every
registration goes through the lead.

**Phase 2 registers the first four.** Engines 1 to 4 join the guard chain in registry
order; the opportunity and manage chains are still empty, which remains valid — the
orchestrator skips an unregistered engine and an empty chain runs cleanly.

Registration was deliberately held until every one of the four had been driven through
**two real orchestrator ticks** against the fake client, by A, in
``tests/engines/test_guard_chain_rehearsal.py``. Two ticks rather than one because
``state`` is fresh every tick except ``state["system"]``, so an engine quietly depending
on something surviving passes a single-tick test and fails the second. That rehearsal is
what turned this from a discovery into a formality, and it found the thing that would
have made it a discovery: against the REST-only fake client the guard chain **blocks
every tick** with ``no_market_data``, because ``market_sensor`` publishes no quotes. That
is the correct fail-closed outcome, and it would have taken the Phase 0 criterion
``orchestrator_empty_registry`` red — which read the live registry here and asserted no
blockers. C rebuilt that criterion to construct its own empty ``Chains`` first.

This module must never import from ``acsoe.research``. Engines 20 ``tournament`` and 23
``backtest`` run in an offline chain assembled in ``acsoe.cli.research``, which is what
keeps the live loop path free of research imports and architecture invariant 5 true.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from acsoe.core.contracts import Chains
from acsoe.engines.data_guard.engine import DataGuardEngine
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_data_recorder.engine import MarketDataRecorderEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine

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
#:
#: Order is the registry table's, not alphabetical and not dependency-inferred: 1
#: ``exchange`` publishes the account picture, 2 ``market_data_recorder`` records raw
#: frames, 3 ``market_sensor`` builds candles and quotes, and 4 ``data_guard`` judges
#: what 1 and 3 produced — so the gate has to come last of the four. Engine 17
#: ``safety`` joins at the end of this chain in Phase 3; it is built and tested but
#: deliberately unregistered, because it is Phase 3 work running concurrently.
#:
#: Constructors take no arguments and hold no resources. The WebSocket stream owns a
#: thread and needs ``start()``/``stop()``, but it lives on the client rather than on an
#: engine, which keeps that a ``cli/engine.py`` lifecycle concern.
GUARD_CHAIN: tuple[BaseEngine, ...] = (
    ExchangeEngine(),
    MarketDataRecorderEngine(),
    MarketSensorEngine(),
    DataGuardEngine(),
)

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
