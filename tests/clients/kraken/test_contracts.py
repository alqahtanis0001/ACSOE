"""Spec 25 — the contract every consumer reads.

Three properties, and each one exists because getting it wrong is silent.

**A float is refused, not coerced.** By the time a float reaches a validator the
precision is gone, so accepting one launders the defect.

**Absent is never zero.** An empty book side cannot be constructed, so "no book"
reaches a caller as a failure rather than as a zero spread.

**Money crosses `state` as a string.** `EngineResult.data` refuses a `Decimal` and
*accepts* a `float`, so the dangerous mistake is the reflexive `float()` cast. The
`state_dict` helpers are the one conversion and they emit strings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from acsoe.clients.kraken.contracts import (
    BalancesSnapshot,
    FeeTierSnapshot,
    OrderBookSnapshot,
    PairRule,
    PairRulesSnapshot,
    money_text,
    to_micros,
)


def rule(**overrides: object) -> PairRule:
    fields: dict[str, object] = {
        "pair": "BTC/USD",
        "base": "BTC",
        "quote": "USD",
        "ordermin": "0.00005",
        "costmin": "5.00",
        "tick_size": "0.1",
        "lot_decimals": 8,
        "pair_decimals": 1,
    }
    fields.update(overrides)
    return PairRule(**fields)  # type: ignore[arg-type]


def test_a_float_is_refused_rather_than_coerced() -> None:
    with pytest.raises(ValidationError, match="float"):
        rule(ordermin=0.00005)


def test_a_decimal_string_keeps_its_quantum() -> None:
    assert rule(costmin="5.00").costmin == Decimal("5.00")
    assert money_text(Decimal("5.00")) == "5.00"
    assert money_text(Decimal("0.0000005")) == "0.0000005"  # never scientific notation


def test_a_zero_minimum_is_refused() -> None:
    """A zero minimum would let a position of nothing satisfy the risk gate."""
    with pytest.raises(ValidationError):
        rule(ordermin="0")


def test_a_snapshot_refuses_a_key_that_disagrees_with_its_rule() -> None:
    with pytest.raises(ValidationError, match="keyed by symbol"):
        PairRulesSnapshot(pairs={"ETH/USD": rule()}, fetched_at=0)


def test_a_fee_expressed_as_a_percent_rather_than_a_ratio_is_refused() -> None:
    """0.40% is 0.004. A `0.40` here would be a 40% fee and would silently make
    every candidate uneconomic, which looks like a working gate."""
    with pytest.raises(ValidationError, match="ratio"):
        FeeTierSnapshot(
            tier=1,
            currency="USD",
            volume_30d="0",
            maker_fee_pct="40",
            taker_fee_pct="0.004",
            fetched_at=0,
        )


def test_an_empty_book_side_cannot_be_constructed() -> None:
    with pytest.raises(ValidationError, match="absent is not zero"):
        OrderBookSnapshot(pair="BTC/USD", bids=(), asks=((Decimal(1), Decimal(1)),), fetched_at=0)


def test_the_state_form_of_every_money_field_is_a_string() -> None:
    book = OrderBookSnapshot(
        pair="BTC/USD",
        bids=((Decimal("50000.0"), Decimal("1")),),
        asks=((Decimal("50000.2"), Decimal("1")),),
        fetched_at=7,
    )
    balances = BalancesSnapshot(balances={"USD": Decimal("1000.00")}, fetched_at=7)
    pairs = PairRulesSnapshot(pairs={"BTC/USD": rule()}, fetched_at=7)
    fees = FeeTierSnapshot(
        tier=1,
        currency="USD",
        volume_30d="0",
        maker_fee_pct="0.0025",
        taker_fee_pct="0.0045",
        fetched_at=7,
    )

    for payload in (
        book.state_dict(),
        balances.state_dict()["balances"],
        pairs.state_dict()["pairs"]["BTC/USD"],
        fees.state_dict(),
    ):
        for key, value in payload.items():
            assert not isinstance(value, float), f"{key} crossed state as a float"
            assert not isinstance(value, Decimal), f"{key} crossed state as a Decimal"

    assert book.state_dict()["spread"] == "0.2"
    assert balances.state_dict()["balances"]["USD"] == "1000.00"


def test_a_naive_timestamp_is_a_defect_rather_than_an_assumed_offset() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        to_micros(datetime(2026, 1, 1, 0, 0, 0))  # noqa: DTZ001 — the naive value is the fixture


def test_micros_are_utc() -> None:
    assert to_micros(datetime(1970, 1, 1, 0, 0, 1, tzinfo=UTC)) == 1_000_000
