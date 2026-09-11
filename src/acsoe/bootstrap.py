"""Engine registry and wiring. Lead-only.

The three runtime chains, in the fixed order of the registry table in
``context/engine-contracts.md``. Every new engine is registered here, and every
registration goes through the lead.

**Phase 2 registered the first four.** Engines 1 to 4 join the guard chain in registry
order; the opportunity and manage chains were still empty, which remained valid — the
orchestrator skips an unregistered engine and an empty chain runs cleanly.

**Phase 3 registers the remaining four, spec 47.** Engine 17 ``safety`` at the end of
the guard chain, and engines 7 ``scout``, 10 ``cost`` and 11 ``risk`` as the opportunity
chain. All four are gates; ``is_gate_matches_registry`` checks each against the Gate
column of the registry table in ``context/engine-contracts.md``.

**What is registered, what is not, and why the chain is not yet in full registry
order.** Nine of the twenty-three engines exist. The opportunity chain runs 7 -> 10 ->
11 with 5, 6, 12, 13, 8 and 9 absent from between them, and 14, 15, 16 and 18 absent
after — so it is the registry order with holes, not a different order. The manage chain
(21, 22, 19) is still empty and Phase 6 fills it. Engines 20 ``tournament`` and 23
``backtest`` never appear here at all: they are ``OFFLINE_CHAIN``, assembled in
``acsoe.cli.research``.

**Registration was held until 40 to 44 were green**, because a half-wired gate in the
live chain turns every other criterion's failure into a puzzle. The same deferral as
Phase 2's, for the same reason, and it paid the same way: the Phase 2 rehearsal turned
registration from a discovery into a formality, and B's spec 42 guard-chain tests did
that job here — ``safety`` was proved on an empty database to trip nothing, write
nothing, stay out of ``guard_blockers``, and read an absent equity snapshot as *no
drawdown measurable* rather than as zero. That was the open question this registration
would otherwise have discovered on the day.

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
from acsoe.engines.cost.engine import CostEngine
from acsoe.engines.data_guard.engine import DataGuardEngine
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_data_recorder.engine import MarketDataRecorderEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.memory.engine import MemoryEngine
from acsoe.engines.risk.engine import RiskEngine
from acsoe.engines.safety.engine import SafetyEngine
from acsoe.engines.scout.engine import ScoutEngine

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
#: **Engine 17 ``safety`` joins at the end in Phase 3, and last is load-bearing**: it
#: reads the current tick's ``state["trading_blocked_by"]``, which ``data_guard`` sets,
#: so it cannot precede the engine whose verdict it counts. It is a gatekeeper on the
#: *account* rather than a judgement about a candidate, which is why it belongs in the
#: guard chain at all — a freeze must not stop data collection, and a bad-data block
#: must not stop ``safety`` evaluating.
#:
#: Constructors take no arguments and hold no resources. The WebSocket stream owns a
#: thread and needs ``start()``/``stop()``, but it lives on the client rather than on an
#: engine, which keeps that a ``cli/engine.py`` lifecycle concern.
GUARD_CHAIN: tuple[BaseEngine, ...] = (
    ExchangeEngine(),
    MarketDataRecorderEngine(),
    MarketSensorEngine(),
    DataGuardEngine(),
    SafetyEngine(),
)

#: Engines 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18. Only when the mode is
#: ``running`` and nothing has blocked. Stops at the first block or PASS.
#:
#: **Phase 3 registers 7, 10 and 11**, in the registry table's order and not in a
#: contiguous run: 5, 6, 12, 13, 8 and 9 sit between them and do not exist yet. The
#: orchestrator skips an unregistered engine, so the chain is 7 -> 10 -> 11 until they
#: land, and the *relative* order is what the table fixes. Inserting the missing six
#: later is an edit to this tuple and to nothing else.
#:
#: The order is not arbitrary and is not dependency-inferred. 7 ``scout`` chooses the
#: candidate pair and must run first, because 10 and 11 both read
#: ``state["scout"]["pair"]`` and neither invents one when it is absent — a `PASS` tick
#: with an empty universe publishes no ``pair`` and the cost gate then fails closed,
#: which `tests/engines/test_scout.py` asserts rather than assumes. 10 ``cost`` before
#: 11 ``risk`` because the cheaper question comes first: cost needs a fee tier and a
#: spread, risk needs a price, an order book and the account's balances, and there is no
#: sense sizing a position the edge cannot pay for.
OPPORTUNITY_CHAIN: tuple[BaseEngine, ...] = (
    ScoutEngine(),
    CostEngine(),
    RiskEngine(),
)

#: Engines 21, 22, 19. Every tick, every mode. Watches positions, exits them, records
#: everything — including on the fourteen ticks in fifteen where no bar closed.
#:
#: **Phase 4 registers 19 `memory`, spec 58.** 21 `position_manager` and 22 `exit` are
#: Phase 6 and stay absent, so this is registry order with holes exactly as the
#: opportunity chain has been since Phase 3. The order matters when they land: 19 runs
#: **last**, because it records what 21 and 22 did on this tick, and an engine cannot
#: record a decision that has not been taken yet.
#:
#: Registration was held until engine 19 had been driven through **two real orchestrator
#: ticks** by an agent that did not build it — B, in
#: `tests/engines/test_manage_chain_rehearsal.py` — the same deferral Phase 2 and Phase 3
#: both took and the third time it paid. Two ticks rather than one because `state` is
#: fresh every tick except `state["system"]`, so an engine quietly depending on something
#: surviving passes a single-tick test and fails the second. The rehearsal's mutation N5
#: measured that rather than asserting it: with `cycle_id` cached on the engine across
#: ticks, the single-tick test still passes and five two-tick assertions fail.
#:
#: One thing the rehearsal established that is worth knowing before reading this chain.
#: `ux_equity_snapshots_tick` has now been **seen to fire**: two orchestrators sharing one
#: `run_id` — a process restarting under a reused id — each mint `cycle_id` 1, which is
#: the same tick by the only identity the schema recognises. Contract rule 7 turns the
#: `IntegrityError` into `ERROR`, the tick completes, engine 19 publishes nothing, and the
#: first tick's row survives untouched. That is the fail-closed outcome, not a defect.
MANAGE_CHAIN: tuple[BaseEngine, ...] = (MemoryEngine(),)


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
