"""Spec 26 — engine 1 `exchange`.

Two properties carry this file.

**Fetched, never constant.** Changing the fixture changes what lands in
`state["exchange"]`. A test that only asserted the values were *present* would pass
identically against an engine that hardcoded them, which is the exact defect
invariant 2 exists to prevent.

**A failed fetch has a documented, tested outcome and never a silent default.** The
engine records which call failed and publishes `null` for its value. It does not
apply invariant 2's paper-mode fallbacks: those are the consumer's decision and the
consumer has to record which one fired.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from acsoe.core.contracts import EngineStatus
from acsoe.engines.exchange.contracts import STATE_KEY
from acsoe.engines.exchange.engine import ExchangeEngine
from tests.harness.fake_kraken import FakeKrakenClient, KrakenUnavailableError


@pytest.fixture
def engine() -> ExchangeEngine:
    return ExchangeEngine()


def run(engine: ExchangeEngine, engine_context: Any, state: dict[str, Any]) -> Any:
    return engine.process(engine_context, state)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def test_it_matches_the_registry_table(engine: ExchangeEngine) -> None:
    """`is_gate_matches_registry` asserts this; so does this file, so a mismatch
    fails locally before it fails a phase gate."""
    assert engine.name == "exchange"
    assert engine.number == 1
    assert engine.is_gate is False
    assert engine.name == STATE_KEY


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #


def test_it_publishes_balances_the_fee_tier_and_the_pair_rules(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    result = run(engine, engine_context, fresh_state)
    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False

    data = result.data
    assert data["failed_fetches"] == []
    assert data["balances"]["USD"] == "1000.00"
    assert data["fee_tier"]["tier"] == 1
    assert data["pair_rules"]["pairs"]["BTC/USD"]["ordermin"] == "0.00005"
    assert data["fetched_at"] == int(engine_context.now.timestamp() * 1_000_000)


def test_every_money_value_crosses_state_as_a_string(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    """`EngineResult.data` refuses a `Decimal` and *accepts* a `float`. The float is
    the silent half, so it is asserted against explicitly."""
    data = run(engine, engine_context, fresh_state).data
    money = [
        data["balances"]["USD"],
        data["fee_tier"]["maker_fee_pct"],
        data["fee_tier"]["taker_fee_pct"],
        data["pair_rules"]["pairs"]["BTC/USD"]["ordermin"],
        data["pair_rules"]["pairs"]["BTC/USD"]["tick_size"],
    ]
    for value in money:
        assert isinstance(value, str), value
        Decimal(value)  # round-trips exactly, which a float would not


def test_the_result_is_accepted_by_the_engine_result_validator(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    """Constructing the EngineResult is the validation; this asserts it happened
    rather than that it could."""
    result = run(engine, engine_context, fresh_state)
    assert result.engine == "exchange"
    assert result.duration_ms >= 0.0


# --------------------------------------------------------------------------- #
# Fetched, never constant
# --------------------------------------------------------------------------- #


def test_the_fee_tier_in_state_changes_when_the_fixture_changes(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    first = run(engine, engine_context, fresh_state).data["fee_tier"]
    fake_kraken.set_fee_tier(tier=3, maker_fee_pct="0.0011", taker_fee_pct="0.0019")
    second = run(engine, engine_context, fresh_state).data["fee_tier"]

    assert first["tier"] == 1
    assert second["tier"] == 3
    assert second["maker_fee_pct"] == "0.0011"
    assert second["maker_fee_pct"] != first["maker_fee_pct"]


def test_ordermin_in_state_changes_when_the_fixture_changes(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    first = run(engine, engine_context, fresh_state).data["pair_rules"]["pairs"]["BTC/USD"]
    fake_kraken.set_pair_rule("BTC/USD", ordermin="0.5", costmin="25000.00")
    second = run(engine, engine_context, fresh_state).data["pair_rules"]["pairs"]["BTC/USD"]

    assert second["ordermin"] == "0.5"
    assert second["costmin"] == "25000.00"
    assert second["ordermin"] != first["ordermin"]


def test_a_pair_removed_from_the_fixture_disappears_from_state(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    fake_kraken.remove_pair("SOL/USD")
    pairs = run(engine, engine_context, fresh_state).data["pair_rules"]["pairs"]
    assert "SOL/USD" not in pairs
    assert "BTC/USD" in pairs


# --------------------------------------------------------------------------- #
# Failed fetches
# --------------------------------------------------------------------------- #


def test_a_transport_failure_is_recorded_and_its_value_is_null(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    fake_kraken.fail("trade_volume")
    data = run(engine, engine_context, fresh_state).data

    assert data["fee_tier"] is None
    assert [f["call"] for f in data["failed_fetches"]] == ["trade_volume"]
    assert data["failed_fetches"][0]["kind"] == "unavailable"
    assert data["failed_fetches"][0]["reason"]


def test_an_envelope_error_is_recorded_as_an_api_error(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    """The two ways the exchange fails mean different things to a reader: "we got an
    answer and it was no" is not the same fact as "we got no answer"."""
    fake_kraken.fail_with_envelope_error("balance", ["EAPI:Invalid key"])
    data = run(engine, engine_context, fresh_state).data
    assert data["balances"] is None
    assert data["failed_fetches"][0] == {
        "call": "balance",
        "kind": "api_error",
        "reason": data["failed_fetches"][0]["reason"],
    }
    assert "EAPI:Invalid key" in data["failed_fetches"][0]["reason"]


def test_one_failure_does_not_blank_the_other_two(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    """Three concurrent calls, not three sequential ones. A consumer has to know
    exactly which value it is missing."""
    fake_kraken.fail("trade_volume")
    data = run(engine, engine_context, fresh_state).data
    assert data["fee_tier"] is None
    assert data["balances"] is not None
    assert data["pair_rules"] is not None


def test_a_total_outage_still_does_not_block_trading(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    """Engine 1 reports; engine 4 decides. A block here would be a fifth gate nobody
    registered, and it would mask the real blocker on the same tick."""
    for call in ("asset_pairs", "trade_volume", "balance"):
        fake_kraken.fail(call)
    result = run(engine, engine_context, fresh_state)

    assert result.blocks_trading is False
    assert result.status is EngineStatus.OK
    assert result.reason is None
    data = result.data
    assert (data["balances"], data["fee_tier"], data["pair_rules"]) == (None, None, None)
    assert {f["call"] for f in data["failed_fetches"]} == {
        "asset_pairs",
        "trade_volume",
        "balance",
    }


def test_no_fallback_is_ever_substituted_for_a_failed_fee_fetch(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    """Invariant 2's paper fallback is the *consumer's* decision and the consumer must
    record which fallback fired. A tier supplied here would erase that record, and
    would be a hardcoded fee besides."""
    fake_kraken.fail("trade_volume")
    data = run(engine, engine_context, fresh_state).data
    assert data["fee_tier"] is None
    assert "tier" not in str(data.get("fee_tier"))


def test_a_non_exchange_exception_is_re_raised_rather_than_recorded(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    """Contract rule 7: an engine must not swallow its own exceptions to avoid ERROR.
    A defect on our side of the boundary is not a failed fetch."""

    async def broken() -> None:
        raise ZeroDivisionError("a defect, not an outage")

    fake_kraken.balance = broken  # type: ignore[method-assign]
    with pytest.raises(ZeroDivisionError):
        run(engine, engine_context, fresh_state)


# --------------------------------------------------------------------------- #
# Retention
# --------------------------------------------------------------------------- #


def test_retained_values_are_reported_as_ages_and_never_as_values(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    """Invariant 2: for trading, a stale value does not exist. Only rule 14 may use
    one, and it reads it from the client, not from `state`."""
    fake_kraken.set_now(1_000)
    run(engine, engine_context, fresh_state)  # populate the retention

    fake_kraken.fail("asset_pairs")
    fake_kraken.fail("balance")
    data = run(engine, engine_context, fresh_state).data

    assert data["pair_rules"] is None
    assert data["balances"] is None
    retained = {note["call"]: note for note in data["retained"]}
    assert set(retained) == {"asset_pairs", "balance"}
    assert retained["balance"]["fetched_at"] == 1_000
    assert retained["balance"]["age_micros"] > 0
    # The values themselves are absent: no ordermin, no balance, anywhere in it.
    assert "ordermin" not in str(data["retained"])
    assert "1000.00" not in str(data["retained"])


def test_the_fee_tier_is_never_retained(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any], fake_kraken: Any
) -> None:
    """A retained stale fee is a loaded gun pointed at the cost gate."""
    run(engine, engine_context, fresh_state)
    fake_kraken.fail("trade_volume")
    data = run(engine, engine_context, fresh_state).data
    assert {note["call"] for note in data["retained"]} == {"asset_pairs", "balance"}


def test_a_client_with_no_retention_at_all_is_not_a_crash(
    engine: ExchangeEngine, engine_context: Any, fresh_state: dict[str, Any]
) -> None:
    """A minimal client double is a legitimate thing for another agent to write."""

    class Bare:
        async def asset_pairs(self) -> Any:
            raise KrakenUnavailableError("no")

        async def trade_volume(self) -> Any:
            raise KrakenUnavailableError("no")

        async def balance(self) -> Any:
            raise KrakenUnavailableError("no")

    context = engine_context
    object.__setattr__(context.clients, "kraken", Bare())
    data = engine.process(context, fresh_state).data
    assert data["retained"] == []
    assert len(data["failed_fetches"]) == 3


def test_the_fake_and_the_real_models_agree(fake_kraken: FakeKrakenClient) -> None:
    """The fake returns C's dataclasses; the engine coerces them into this system's
    validated models, so fixture data goes through the same validators as exchange
    data. A fixture with a zero `ordermin` is refused in a test exactly as it would
    be in production."""
    from acsoe.clients.kraken.contracts import coerce_pair_rules
    from acsoe.platform.aio import run_blocking

    snapshot = coerce_pair_rules(run_blocking(fake_kraken.asset_pairs()))
    assert snapshot.pairs["BTC/USD"].ordermin == Decimal("0.00005")

    fake_kraken.set_pair_rule("BTC/USD", ordermin="0")
    with pytest.raises(ValueError, match="must be positive"):
        coerce_pair_rules(run_blocking(fake_kraken.asset_pairs()))
