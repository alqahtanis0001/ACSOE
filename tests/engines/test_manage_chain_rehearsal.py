"""Engine 19 `memory` through two real orchestrator ticks, before it is registered.

Written by B, and engine 19 is C's. That is deliberate and it is the same exception A's
`test_guard_chain_rehearsal.py` was written under: **this file tests the orchestrator
wiring, not the engine.** Whether `memory` writes the right row given a `state` is C's
`tests/engines/test_memory.py`; whether the *orchestrator* hands it a `state` it can use,
on a tick nobody staged by hand, is nobody's until someone writes it. Registration in
`bootstrap.py` is the lead's, and it should be a formality rather than a discovery.

**Two ticks rather than one, and this is the whole point of the file.** `state` is rebuilt
from scratch every tick except `state["system"]`, so an engine quietly depending on
something surviving passes a single-tick test and fails the second. A rehearsal that runs
one tick, or that runs two and only ever looks at the first, is judging one tick twice.

Nothing here stages a `state` dict. Every payload engine 19 reads arrives from a real
engine through the real `Orchestrator`, because a hand-built `state` that agrees with its
caller is the failure this project has now found four times.
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.harness.doubles import MappingConfig

from acsoe.clients.store.contracts import BlockStatus
from acsoe.core.contracts import Chains
from acsoe.core.orchestrator import Orchestrator
from acsoe.engines.data_guard.engine import DataGuardEngine
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_data_recorder.engine import MarketDataRecorderEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.memory.contracts import WRITTEN_TABLES
from acsoe.engines.memory.engine import MemoryEngine


class RecordingLogger:
    """Captures what the orchestrator logged, so an ERROR can be asserted by cause.

    A manage-chain engine that raises leaves `state[engine.name] == {}` and nothing else
    — the status and reason never reach `state`, unlike a guard blocker. Asserting the
    empty dict alone would be satisfied by an engine that raised for any reason at all,
    including one that happened before the one under test. The orchestrator logs the
    repr, so that is where the cause is.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def debug(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))

    def errors_for(self, engine: str) -> list[str]:
        return [
            str(fields.get("error", ""))
            for event, fields in self.events
            if event == "engine_error" and fields.get("engine") == engine
        ]


@pytest.fixture
def manage_config(paper_config: MappingConfig) -> MappingConfig:
    """The committed config plus the threshold engine 4 needs.

    Copied from A's guard-chain rehearsal for the same reason: without it engine 4 raises
    and the tick is blocked by an ERROR rather than by the data verdict this file is
    about, which would make every assertion below true for the wrong reason.
    """
    data = paper_config.as_dict()
    data["data_guard"] = {"max_data_age_s": 120.0}
    return MappingConfig(data)


def build(
    config: MappingConfig,
    clock: Any,
    clients: Any,
    *,
    guard: str = "full",
    run_id: str | None = None,
    logger: Any | None = None,
) -> Orchestrator:
    """The real orchestrator with engine 19 in the manage chain.

    `guard` selects what happens upstream, because engine 19's behaviour is defined by
    what the guard chain did and there is no other way to vary it honestly:

    - `"full"` — engines 1 to 4. The fake Kraken client is REST-only, so `data_guard`
      blocks and the tick is a blocked tick.
    - `"exchange"` — engine 1 alone. Nothing blocks, so the tick is a clean tick that
      still carries the balances engine 19 needs for an equity row.
    - `"none"` — no guard chain at all. A clean tick with no exchange payload either.
    """
    chains = {
        "full": [
            ExchangeEngine(),
            MarketDataRecorderEngine(),
            MarketSensorEngine(),
            DataGuardEngine(),
        ],
        "exchange": [ExchangeEngine()],
        "none": [],
    }[guard]
    return Orchestrator(
        config=config,
        clock=clock,
        clients=clients,
        chains=Chains(guard=chains, manage=[MemoryEngine()]),
        run_id=run_id,
        logger=logger,
    )


def block_rows(store: Any) -> list[tuple[str, int, str, bool, BlockStatus]]:
    rows = store.block_records_in_window(start_ts=0, end_ts=2**62)
    return [(r.run_id, r.cycle_id, r.blocked_by, r.is_primary, r.status) for r in rows]


# --------------------------------------------------------------------------- #
# 1. Two ticks, and the second is its own tick
# --------------------------------------------------------------------------- #


def test_two_real_ticks_complete_and_engine_19_reports_on_both(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    orchestrator = build(manage_config, fixed_clock, fake_clients_with_store)

    first = orchestrator.tick()
    second = orchestrator.tick()

    assert first["memory"]["cycle_id"] == first["cycle_id"] == 1
    assert second["memory"]["cycle_id"] == second["cycle_id"] == 2
    assert second["cycle_id"] == first["cycle_id"] + 1


def test_tick_two_writes_tick_twos_rows_and_does_not_repeat_or_overwrite_tick_ones(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    """The assertion the two-tick rule exists for.

    Three distinct failures all look identical after one tick and are separated here:
    tick 2 writing nothing, tick 2 re-writing tick 1's row, and tick 2 overwriting it.
    The first leaves one row, the second leaves two rows on one `cycle_id`, and the
    third leaves one row — so only the *set of cycle ids* tells them apart.
    """
    store = fake_clients_with_store.store
    orchestrator = build(manage_config, fixed_clock, fake_clients_with_store)

    orchestrator.tick()
    after_one = block_rows(store)
    orchestrator.tick()
    after_two = block_rows(store)

    assert [cycle for _, cycle, _, _, _ in after_one] == [1]
    assert [cycle for _, cycle, _, _, _ in after_two] == [1, 2]
    # One run, so a second `run_id` appearing here would mean the rehearsal built two
    # orchestrators without meaning to and the two ticks are not consecutive at all.
    assert len({run for run, _, _, _, _ in after_two}) == 1


def test_the_second_tick_is_recorded_even_though_state_did_not_survive(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    """`state` is rebuilt every tick, so tick 2's row is proof engine 19 re-read it.

    An engine that cached its inputs on `self` at construction would be indistinguishable
    from a correct one on tick 1 and would stamp tick 2 with tick 1's facts.
    """
    store = fake_clients_with_store.store
    orchestrator = build(manage_config, fixed_clock, fake_clients_with_store)

    first = orchestrator.tick()
    second = orchestrator.tick()

    assert first["memory"]["written"]["block_records"] == 1
    assert second["memory"]["written"]["block_records"] == 1
    assert {cycle for _, cycle, _, _, _ in block_rows(store)} == {1, 2}


# --------------------------------------------------------------------------- #
# 2. A clean tick records nothing and says so
# --------------------------------------------------------------------------- #


def test_an_unblocked_tick_writes_no_block_record(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    """No blocker, no row. Writing one here would inflate `safety`'s outage count with
    ticks that were fine, which is the breaker firing over nothing."""
    store = fake_clients_with_store.store
    state = build(manage_config, fixed_clock, fake_clients_with_store, guard="exchange").tick()

    assert state["guard_blockers"] == []
    assert block_rows(store) == []
    assert state["memory"]["written"]["block_records"] == 0


def test_a_clean_tick_still_reports_every_table_including_the_zeros(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    """"Ran and recorded nothing" against "did not run", and this is the only signal.

    An engine that reported only the tables it wrote would make the two indistinguishable
    from the console and the log, on exactly the ticks where the difference matters —
    a quiet system and a dead engine both show an empty feed.
    """
    state = build(manage_config, fixed_clock, fake_clients_with_store, guard="exchange").tick()
    written = state["memory"]["written"]

    assert set(written) == set(WRITTEN_TABLES)
    assert written["block_records"] == 0
    assert written["positions"] == 0
    assert written["orders"] == 0
    assert written["trades"] == 0
    assert written["rejections"] == 0


def test_absent_phase_6_engines_are_reported_absent_not_as_zeros(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    """Engines 18, 21 and 22 are Phase 6 and their keys are not in `state` yet.

    Absent must mean nothing-to-record. `sources_present` is how engine 19 says which
    publishers it actually saw, and it is the difference between a position count of
    zero and no position information at all.
    """
    state = build(manage_config, fixed_clock, fake_clients_with_store, guard="exchange").tick()

    assert "position_manager" not in state
    assert "exit" not in state
    assert "position_manager" not in state["memory"]["sources_present"]
    assert "exit" not in state["memory"]["sources_present"]
    assert "exchange" in state["memory"]["sources_present"]


# --------------------------------------------------------------------------- #
# 3. The manage chain runs when the guard rejected the data — the reason it exists
# --------------------------------------------------------------------------- #


def test_a_data_guard_block_is_recorded_by_the_manage_chain(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    """`engine-contracts.md`'s stated reason the manage chain runs on a blocked tick.

    `safety`'s outage count is derived from these rows and from nothing else, so a
    manage chain that stopped when the guard rejected the data would leave the breaker
    inert with every test still green. That is the failure this rehearsal is for.
    """
    store = fake_clients_with_store.store
    state = build(manage_config, fixed_clock, fake_clients_with_store).tick()

    assert state["trading_blocked_by"] == "data_guard"
    assert "memory" in state, "the manage chain did not run on a blocked tick"
    assert block_rows(store) == [
        (state["memory"]["run_id"], 1, "data_guard", True, BlockStatus.BLOCK)
    ]


def test_the_outage_counter_reads_the_rows_the_rehearsal_just_wrote(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    """End to end, through the method engine 17 `safety` actually calls.

    Two blocked ticks in one run is an outage of two. Asserting the rows exist proves
    engine 19 wrote something; asserting the counter reaches 2 proves it wrote something
    `safety` can use, which is a different claim and the one that matters.
    """
    store = fake_clients_with_store.store
    orchestrator = build(manage_config, fixed_clock, fake_clients_with_store)

    first = orchestrator.tick()
    orchestrator.tick()
    run_id = first["memory"]["run_id"]

    stored = store.stored_consecutive_data_block_ticks_excluding_current_tick(
        current_tick=(run_id, 3)
    )

    assert stored == 2


# --------------------------------------------------------------------------- #
# 4. `ux_equity_snapshots_tick`, and what its shape actually is
# --------------------------------------------------------------------------- #


def test_two_ticks_in_one_run_do_not_trip_the_equity_tick_constraint(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    """`write_equity_snapshot` is a plain INSERT under a UNIQUE `(run_id, cycle_id)`.

    Two ticks mint two cycle ids, so it must not fire — but "must not" is a prediction
    until a second tick has actually been driven through it against a real database.
    """
    store = fake_clients_with_store.store
    orchestrator = build(manage_config, fixed_clock, fake_clients_with_store, guard="exchange")

    first = orchestrator.tick()
    second = orchestrator.tick()

    assert first["memory"]["written"]["equity_snapshots"] == 1
    assert second["memory"]["written"]["equity_snapshots"] == 1
    series = store.equity_series()
    assert [row.cycle_id for row in series] == [1, 2]
    assert len({row.run_id for row in series}) == 1


def test_the_same_tick_twice_does_trip_the_equity_constraint(
    manage_config: MappingConfig, fixed_clock: Any, fake_clients_with_store: Any
) -> None:
    """The other half, because a constraint nobody has seen fire has an unknown shape.

    Two orchestrators sharing one `run_id` and one store: each mints `cycle_id` 1, so
    the second tick is the *same tick* as the first by the only identity the schema
    recognises. This is a real scenario, not a contrivance — it is what a process
    restarting under a reused `run_id` would do.

    What must happen is not a crash: contract rule 7 turns the `IntegrityError` into
    ERROR, the tick still completes, and the first tick's row is left intact. A second
    equity row for one tick would mean two different answers to "what was equity at
    tick 1", and `safety` reads the latest — so it would silently pick one.
    """
    store = fake_clients_with_store.store
    logger = RecordingLogger()
    build(
        manage_config, fixed_clock, fake_clients_with_store, guard="exchange", run_id="run-fixed"
    ).tick()
    second = build(
        manage_config,
        fixed_clock,
        fake_clients_with_store,
        guard="exchange",
        run_id="run-fixed",
        logger=logger,
    ).tick()

    # The tick completed rather than taking the loop down with it.
    assert second["cycle_id"] == 1
    assert second["memory"] == {}
    # On the cause, not merely on "something raised": engine 19 can raise
    # `MissingInputError` for half a dozen unrelated reasons and this test would pass
    # against every one of them.
    errors = logger.errors_for("memory")
    assert len(errors) == 1
    assert "IntegrityError" in errors[0]
    assert "equity_snapshots" in errors[0]
    # Exactly one row survives, and it is the first tick's.
    assert [row.cycle_id for row in store.equity_series()] == [1]
