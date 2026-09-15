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
from pathlib import Path

import pytest

from acsoe.core.contracts import Clients, Clock, Config
from tests.harness.doubles import (
    FIXED_NOW,
    FakeClients,
    FixedClock,
    MappingConfig,
    build_verify_doubles,
    fresh_state,
    load_default_config,
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


def test_a_leaf_the_model_declares_optional_and_the_file_omits_reads_as_none() -> None:
    """The one dimension this double used to get wrong, and it is the dimension Phase 5
    lives in.

    Two keys are absent from `config/default.yaml` by operator ruling — the model run ids a
    fresh clone has no artefact for, and the ranking feature the Phase 7 question decides —
    and the engines that read them are written to read the `None` and block with **their
    own** reason code. This double wraps the raw dict, so it raised; the orchestrator turns
    a raise into `ERROR`, `ERROR` also blocks, and every test of those engines would have
    been written against the wrong branch with nothing red anywhere.

    The real `Config` declares each as `Ratio | None` or `str | None` and returns `None`.

    **It was five keys until 2026-09-15.** The three thresholds
    (`prediction.di_percentile`, `anomaly.threshold_percentile`, `skeptic.veto_threshold`)
    were ruled by the operator on 2026-09-14 and 2026-09-15 and are no longer absent; they
    move to the test below, which asserts the other half of the same property, because a
    double that answered `None` for a leaf the file *does* carry would be wrong in the
    direction that makes a configured gate look unconfigured.
    """
    config = load_default_config()
    for key in (
        "models.prediction_run_id",
        "scout.rank_feature",
    ):
        assert config.get(key) is None, key


def test_an_optional_leaf_the_file_supplies_reads_as_its_value() -> None:
    """The other half, and the half that arrived with the operator's rulings.

    `Ratio | None` has two legitimate readings and the double must give the right one for
    each. Absent reads as `None` above; supplied must read as the number, because a double
    answering `None` here would have engines 8, 13 and 15 block with `*_unavailable` in
    every test that used it — a configured gate reported as an unconfigured one, which is
    fail-closed and therefore silent.

    The values are not pinned: all three are provisional until the chain runs end to end,
    and this test is about the double, not about where the operator drew the lines.
    """
    config = load_default_config()
    for key in (
        "prediction.di_percentile",
        "anomaly.threshold_percentile",
        "skeptic.veto_threshold",
    ):
        value = config.get(key)
        assert isinstance(value, float) and 0.0 < value < 1.0, (key, value)


def test_a_typo_still_raises_rather_than_reading_as_an_unset_leaf() -> None:
    """The half that keeps the fix from being a blanket `None`.

    The answer comes from the real model's declared fields rather than from a list of key
    names here, so a misspelling is not declared, is not optional, and still raises — and
    the day the operator supplies `prediction.di_percentile` and the lead makes it
    required, this double starts raising for it again with nobody editing the harness.
    """
    config = load_default_config()
    for typo in ("prediction.di_percentil", "prediction.nosuch", "nosuch.key"):
        with pytest.raises(KeyError):
            config.get(typo)


def test_a_required_leaf_is_still_a_real_value() -> None:
    """The control. Without it, a double that returned `None` for everything would satisfy
    both tests above."""
    assert load_default_config().get("prediction.di_window_days") == 30


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
    directory = Path(doubles._tmp.name)
    try:
        assert isinstance(doubles.clock, Clock)
        assert isinstance(doubles.config, Config)
        assert isinstance(doubles.clients, Clients)
        assert doubles.config.mode == "paper"
    finally:
        doubles.close()
    assert doubles._tmp is None
    # The regression: `close()` used to remove the directory while the store still
    # held `acsoe.sqlite` open, which Windows refuses. The refusal surfaced from
    # `TemporaryDirectory`'s finalizer at garbage collection, where nothing could
    # catch it, and `verify.py --phase 0` printed a `PermissionError` above its
    # report on every run - green ones included.
    assert not directory.exists()
