"""The shared doubles, against the real Protocols now that `core/` declares them.

Spec 14 step 2. `FixedClock` and `MappingConfig` were written to the shape
`engine-contracts.md` implied, before `core/contracts.py` existed - the seam was
recorded in `context/progress/c-interface.md` as provisional. The contract has
since landed, so the provisional shapes are checked against the declaration
rather than against my reading of a document.

The `Config` case is the one that matters. `runtime_checkable` `isinstance` only
proves the attributes are *present*, never that they behave the way the Protocol's
docstring says - so the behaviour the contract is emphatic about is asserted
separately. A missing key must raise rather than return `None`, because an engine
silently receiving `None` for a threshold is the failure this project refuses to
allow, and a double that returns a default instead would let that bug pass every
test in the repository.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from acsoe.core.contracts import Clients, Clock, Config
from tests.harness.doubles import (
    FIXED_NOW,
    FakeClients,
    FixedClock,
    MappingConfig,
    build_verify_doubles,
    fresh_state,
)

# --------------------------------------------------------------------------- #
# The Protocols
# --------------------------------------------------------------------------- #


def test_the_fixed_clock_satisfies_the_clock_protocol() -> None:
    assert isinstance(FixedClock(), Clock)


def test_the_mapping_config_satisfies_the_config_protocol() -> None:
    assert isinstance(MappingConfig({"mode": "paper"}), Config)


def test_the_client_bundle_satisfies_the_clients_protocol() -> None:
    """Exactly three clients, per contract rule 4: kraken, store, recorder."""
    assert isinstance(FakeClients(), Clients)


def test_mode_is_declared_on_the_class_and_not_only_via_getattr() -> None:
    """A trap that costs nothing to avoid and is invisible once you fall into it.

    Since Python 3.12, `isinstance(x, SomeRuntimeCheckableProtocol)` resolves each
    protocol member with `inspect.getattr_static`, which walks the class dictionary
    and the MRO and never calls `__getattr__`. `MappingConfig` answers every key
    through `__getattr__`, so before `mode` was written out explicitly the double
    worked perfectly everywhere it was used and still failed
    `isinstance(config, Config)` - silently, with nothing to read.

    Asserted through `getattr_static` rather than through `isinstance` so that a
    future "simplification" that folds `mode` back into `__getattr__` fails *here*,
    naming the cause, instead of somewhere far away in a protocol check.
    """
    import inspect

    assert inspect.getattr_static(MappingConfig({"mode": "paper"}), "mode") is not None


# --------------------------------------------------------------------------- #
# The clock
# --------------------------------------------------------------------------- #


def test_the_clock_is_timezone_aware_utc() -> None:
    """A naive clock silently reintroduces look-ahead in replay, and
    `EngineContext` refuses one outright."""
    now = FixedClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_a_naive_start_is_refused() -> None:
    with pytest.raises(ValueError, match="naive"):
        FixedClock(datetime(2026, 1, 1))  # noqa: DTZ001 - the point of the test


def test_the_clock_does_not_move_unless_a_test_moves_it() -> None:
    """Determinism is what makes two runs of one test byte-identical, which is what
    makes a seeded database comparable and a replay faithful."""
    clock = FixedClock()
    assert clock.now() == clock.now() == FIXED_NOW
    assert clock.advance(60) == FIXED_NOW + timedelta(seconds=60)
    assert clock.now() == FIXED_NOW + timedelta(seconds=60)


def test_setting_a_moment_normalises_to_utc() -> None:
    clock = FixedClock()
    moment = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert clock.set(moment) == moment


# --------------------------------------------------------------------------- #
# The config double is not kinder than the real one
# --------------------------------------------------------------------------- #


def test_a_missing_key_raises_rather_than_returning_none() -> None:
    """The contract, in as many words: `get` "raises rather than returning a
    default".

    An earlier version of this double took a `default` and returned it. That made
    the fake kinder than `platform/config.py`, and a fake kinder than reality hides
    exactly the fail-closed bug it was built to expose - a threshold arriving as
    `None` and being treated as zero.
    """
    config = MappingConfig({"safety": {"max_consecutive_data_blocks": 15}})
    with pytest.raises(KeyError, match="max_drawdown_pct"):
        config.get("safety.max_drawdown_pct")


def test_the_error_names_the_segment_that_was_not_found() -> None:
    """A missing key that does not say *which* segment is missing sends the reader
    hunting through a nested YAML file for a typo."""
    config = MappingConfig({"safety": {}})
    with pytest.raises(KeyError, match="'nope' is not present under safety"):
        config.get("safety.nope.deeper")


def test_a_key_present_but_null_returns_none_and_does_not_raise() -> None:
    """Absent and `null` are different states.

    The lead writes OPERATOR REQUIRED thresholds as `null`; "the operator has not
    decided yet" is a decision waiting to be made, not a defect in anyone's code,
    and `seed_fixtures_present` reports it as PENDING rather than FAIL on exactly
    this distinction.
    """
    assert MappingConfig({"safety": {"max_drawdown_pct": None}}).get("safety.max_drawdown_pct") is None


def test_dotted_lookup_walks_nested_mappings() -> None:
    config = MappingConfig({"paper": {"starting_balances": {"USD": "1000.00"}}})
    assert config.get("paper.starting_balances.USD") == "1000.00"


def test_attribute_access_returns_a_config_for_a_nested_mapping() -> None:
    config = MappingConfig({"console": {"port": 8765}})
    assert config.console.port == 8765


# --------------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------------- #


def test_fresh_state_starts_idle_and_never_restores_a_mode() -> None:
    """A daemon always starts `idle` and only reaches `running` through an
    `activate` command, so a crash at 3am leaves a system that is up, watching its
    open positions, and not trading."""
    state = fresh_state()
    assert state["system"] == {"mode": "idle", "close_intent": False}


def test_fresh_state_carries_an_empty_guard_blockers_list_not_an_absent_one() -> None:
    """An empty list on an unblocked tick, never absent. Engine 19 writes one
    `block_records` row per entry, and absent would make the outage counter
    unbuildable rather than merely empty."""
    assert fresh_state()["guard_blockers"] == []


def test_fresh_state_carries_a_cycle_id() -> None:
    """`cycle_id` joins logs, decisions and SHAP rows - together with `run_id`, on
    its own it is ambiguous across runs."""
    assert isinstance(fresh_state()["cycle_id"], int)


# --------------------------------------------------------------------------- #
# The verify doubles
# --------------------------------------------------------------------------- #


def test_the_verify_doubles_build_and_clean_up_after_themselves() -> None:
    """`scripts/verify.py` runs `orchestrator_empty_registry` out of these, outside
    pytest, so they own their temporary directory rather than leaning on
    `tmp_path`. Nothing is written under `data/`: every criterion has to pass on a
    fresh clone, and `data/` is gitignored."""
    doubles = build_verify_doubles()
    try:
        assert isinstance(doubles.clock, Clock)
        assert isinstance(doubles.config, Config)
        assert isinstance(doubles.clients, Clients)
        assert doubles.config.mode == "paper"
    finally:
        doubles.close()
    assert doubles._tmp is None
