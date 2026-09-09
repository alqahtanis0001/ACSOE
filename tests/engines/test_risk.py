"""Engine 11 `risk` — spec 35.

The test that carries the spec is `test_a_sub_ordermin_position_is_rejected_not_resized`.
Spec 35 is explicit about why: "a test that only checked 'did not place' would pass
against a rounding implementation". So the assertion is on the **absence of a resized
quantity** — no field in the payload holds one, and no field equals `ordermin` — rather
than on the block alone.

`ordermin` has the same property the fee tier has in engine 10: a constant that happened
to match the fixture would satisfy every behavioural test in this file. So one test
changes it in the mock and asserts the outcome moves, and another reads the engine's own
source and asserts no minimum is written into it.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import EquitySnapshotRow, PositionRow, PositionStatus
from acsoe.core.contracts import EngineStatus
from acsoe.engines.risk.contracts import (
    REASON_BELOW_COSTMIN,
    REASON_BELOW_ORDERMIN,
    REASON_INPUTS_UNAVAILABLE,
    REASON_INSUFFICIENT_QUOTE_BALANCE,
    REASON_MAX_CONCURRENT_POSITIONS,
    round_down_to_lot,
)
from acsoe.engines.risk.engine import RiskEngine

PAIR = "SOL/USD"

#: The committed config's own worked example, quoted in `config/default.yaml` on
#: `max_concurrent_positions`: "the balance binds first at $5,000: one position is ~$3,333
#: notional". $5,000 x 1% / 1.5% = $3,333.33. Every sizing test here is anchored to it, so
#: a change to the sizing rule fails against the operator's stated intent rather than
#: against a number this file invented.
EQUITY = "5000.00"
EXPECTED_NOTIONAL = Decimal("3333.33")


def build_state(
    *,
    ordermin: str = "0.1",
    costmin: str = "5.00",
    lot_decimals: int = 8,
    last_price: str = "100.00",
    quote_balance: str = "5000.00",
    pair: str = PAIR,
    quote: str = "USD",
    fallbacks: list[str] | None = None,
) -> dict[str, Any]:
    """A `state` as the opportunity chain would have it by the time gate 11 runs.

    `ordermin`, `costmin` and `lot_decimals` are **fixture inputs**, which is the only
    place they are allowed to exist. `AGENTS.md`: any remembered order minimum is stale,
    so the engine may not contain one and
    `test_no_order_minimum_is_written_into_the_engine_source` proves it does not.
    """
    return {
        "system": {"mode": "running", "close_intent": False},
        "cycle_id": 1,
        "guard_blockers": [],
        "scout": {"pair": pair},
        "exchange": {
            "pairs": {
                pair: {
                    "quote": quote,
                    "last_price": last_price,
                    "ordermin": ordermin,
                    "costmin": costmin,
                    "lot_decimals": lot_decimals,
                }
            },
            "balances": {quote: quote_balance},
            "fallbacks_used": list(fallbacks or []),
        },
    }


def open_position(position_id: str, pair: str) -> PositionRow:
    """One open position, for the portfolio cap. Only `status` and `pair` matter here."""
    base, _, quote = pair.partition("/")
    return PositionRow(
        position_id=position_id,
        run_id="test-run",
        cycle_id=1,
        pair=pair,
        base=base,
        quote=quote,
        status=PositionStatus.OPEN,
        qty=Decimal("1.00000000"),
        entry_price=Decimal("100.00"),
        target_price=Decimal("103.00"),
        stop_price=Decimal("98.50"),
        timeout_at=9_999,
        opened_at=1_000,
        updated_at=1_000,
    )


@pytest.fixture
def risk() -> RiskEngine:
    return RiskEngine()


@pytest.fixture
def sized_context(engine_context: Any, store: StoreClient) -> Any:
    """An `EngineContext` whose store carries the equity snapshot sizing reads.

    Invariant 6 sizes against *total account equity*, which only engine 19 `memory`
    computes, and engine 19 is Phase 4. This is the same forward dependency engine 17
    has and it is resolved the same way: a real `StoreClient` against a migrated
    temporary database, with the row written here rather than by a live engine.
    """
    store.write_equity_snapshot(
        EquitySnapshotRow(
            cycle_id=1,
            run_id="test-run",
            ts=1_000,
            currency="USD",
            equity=Decimal(EQUITY),
            peak_equity=Decimal(EQUITY),
            cash=Decimal(EQUITY),
            positions_value=Decimal("0.00"),
            unrealised_pnl=Decimal("0.00"),
            realised_pnl_cum=Decimal("0.00"),
            open_position_count=0,
            updated_at=1_000,
        )
    )
    engine_context.clients.store = store
    return engine_context


# --------------------------------------------------------------------------- #
# Registry shape
# --------------------------------------------------------------------------- #


def test_the_engine_declares_itself_as_the_registry_has_it(risk: RiskEngine) -> None:
    assert (risk.name, risk.number, risk.is_gate) == ("risk", 11, True)


# --------------------------------------------------------------------------- #
# The gate: a pass test and the block test the spec names
# --------------------------------------------------------------------------- #


def test_a_position_at_or_above_ordermin_passes(risk: RiskEngine, sized_context: Any) -> None:
    """The pass half. $3,333.33 notional at $100 is 33.33333333 units at `lot_decimals`
    8, well above a 0.1 minimum."""
    result = risk.process(sized_context, build_state(ordermin="0.1"))

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["approved"] is True
    assert Decimal(result.data["qty"]) == Decimal("33.33333333")


def test_the_sizing_is_the_configured_fraction_of_equity_at_the_configured_stop(
    risk: RiskEngine, sized_context: Any
) -> None:
    """Anchored to the worked example in `config/default.yaml` itself.

    risk_amount = 5000.00 x 0.01        = 50.00
    notional    = 50.00 / 0.015         = 3333.33...
    qty         = 3333.33... / 100.00   = 33.3333...

    Reading `risk_fraction_per_trade` as a fraction of *notional* rather than of money at
    risk would size this at 0.5 units instead of 33.33 — 66 times smaller, an error that
    looks conservative and would quietly make the whole system untestable. The operator's
    own comment on `max_concurrent_positions` says $3,333, so this is asserted against
    stated intent rather than against a number invented here.
    """
    data = risk.process(sized_context, build_state()).data

    assert Decimal(data["risk_amount"]) == Decimal("50.0000")
    assert Decimal(data["notional"]).quantize(Decimal("0.01")) == EXPECTED_NOTIONAL


def test_a_sub_ordermin_position_is_rejected_not_resized(
    risk: RiskEngine, sized_context: Any
) -> None:
    """The test spec 35 names, asserted the way spec 35 requires.

    A test that only checked "did not place" would pass against a rounding
    implementation, because a rounding implementation also does not place *this* size —
    it places `ordermin` instead. So the assertion is on the **absence of a resized
    quantity**: no `qty` field at all, and no field anywhere in the payload carrying the
    minimum. Rounding up silently increases the money at risk beyond what the sizing
    decided, which is the opposite of what a risk gate is for.
    """
    # A minimum far above the 33.33 units the sizing produces.
    state = build_state(ordermin="500")

    result = risk.process(sized_context, state)

    assert result.blocks_trading is True
    assert result.data["approved"] is False
    assert result.data["reason_code"] == REASON_BELOW_ORDERMIN

    # The absence, asserted on the whole key set rather than on values.
    #
    # An earlier version of this checked that no *value* in the payload equalled
    # `ordermin`, which was wrong twice over: `ordermin` is legitimately published so the
    # console and the `rejections` row can say what the minimum was, so the check fired
    # on a correct payload — and value-sniffing would not have caught a bump to
    # `ordermin + 1` anyway. Pinning the key set is both stricter and honest: there is no
    # `qty`, no `notional` and no `risk_amount` field for anything to be bumped *into*.
    assert set(result.data) == {
        "pair",
        "approved",
        "ordermin",
        "costmin",
        "reason_code",
        "fallbacks_used",
    }, "a refused candidate must publish no quantity field at all, in any form"
    assert Decimal(result.data["ordermin"]) == Decimal("500")


def test_a_position_one_increment_below_the_minimum_is_still_rejected(
    risk: RiskEngine, sized_context: Any
) -> None:
    """The boundary, which is where a rounding implementation is most tempting.

    At `lot_decimals` 8 the sizing gives 33.33333333. A minimum one increment above that
    is 33.33333334, and the answer must still be no — one satoshi-equivalent short is
    short.
    """
    just_above = risk.process(sized_context, build_state(ordermin="33.33333334"))
    exactly_at = risk.process(sized_context, build_state(ordermin="33.33333333"))

    assert just_above.blocks_trading is True
    assert just_above.data["reason_code"] == REASON_BELOW_ORDERMIN
    assert exactly_at.blocks_trading is False, "at the minimum is allowed; below it is not"


# --------------------------------------------------------------------------- #
# The minimum is fetched, never remembered
# --------------------------------------------------------------------------- #


def test_changing_ordermin_changes_which_sizes_are_rejected(
    risk: RiskEngine, sized_context: Any
) -> None:
    """Proves the value is fetched. A constant would pass every single-value test above
    and fail this one."""
    generous = risk.process(sized_context, build_state(ordermin="0.1"))
    strict = risk.process(sized_context, build_state(ordermin="500"))

    assert generous.blocks_trading is False
    assert strict.blocks_trading is True


def test_no_order_minimum_is_written_into_the_engine_source() -> None:
    """`AGENTS.md`: any remembered order minimum is stale. A constant that happened to
    match the fixture would satisfy every behavioural test in this file, so the source is
    read directly — the same guard engine 10 carries for the reference fees."""
    import acsoe.engines.risk as package

    source = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted(Path(package.__file__).parent.glob("*.py"))
    )
    for remembered in ("0.1", "500", "5.00", "ordermin =", "costmin ="):
        assert remembered not in source, f"{remembered!r} looks like a remembered pair rule"


# --------------------------------------------------------------------------- #
# Rounding
# --------------------------------------------------------------------------- #


def test_quantities_round_down_never_to_nearest() -> None:
    """Rounding to nearest would round a quantity one ulp below `ordermin` *up to* it —
    the rounding-up defect arriving through a rounding mode rather than an explicit bump.
    Invariant 14 fixes the same rule for a liquidation: dust is cheaper than a rejected
    order."""
    assert round_down_to_lot(Decimal("1.999999999"), 8) == Decimal("1.99999999")
    assert round_down_to_lot(Decimal("0.99999999999"), 2) == Decimal("0.99")
    assert round_down_to_lot(Decimal("5"), 0) == Decimal("5")


def test_rounding_happens_before_the_minimum_is_tested(
    risk: RiskEngine, sized_context: Any
) -> None:
    """The ordering that is easy to get backwards.

    At `lot_decimals` 0 the 33.3333 units round down to 33. A minimum of 33.5 must
    therefore reject: the number compared against `ordermin` has to be the number that
    would actually be sent, not the unrounded one that passed.
    """
    result = risk.process(sized_context, build_state(lot_decimals=0, ordermin="33.5"))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_BELOW_ORDERMIN


# --------------------------------------------------------------------------- #
# The other three refusals
# --------------------------------------------------------------------------- #


def test_a_position_below_costmin_is_rejected(risk: RiskEngine, sized_context: Any) -> None:
    """`costmin` is tested on the rounded quantity's real value, not on the notional the
    sizing asked for: rounding down can drop the value below the minimum even when the
    request cleared it."""
    result = risk.process(sized_context, build_state(costmin="999999.00"))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_BELOW_COSTMIN
    assert "qty" not in result.data


def test_a_notional_larger_than_the_quote_balance_is_rejected(
    risk: RiskEngine, sized_context: Any
) -> None:
    """Invariant 6: never allocate cash the account does not hold in that pair's quote
    currency. Rejected rather than capped to fit — a position quietly resized is no
    longer the position the sizing rule chose, which is the same objection as rounding
    up to a minimum."""
    result = risk.process(sized_context, build_state(quote_balance="100.00"))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INSUFFICIENT_QUOTE_BALANCE
    assert "qty" not in result.data, "not capped to the balance — refused"


def test_the_balance_is_read_per_quote_currency(risk: RiskEngine, sized_context: Any) -> None:
    """Invariant 7: a pair is only executable if the account holds spendable balance in
    *that* quote currency. A EUR-quoted pair may not spend the USD pot."""
    state = build_state(quote="EUR", quote_balance="5000.00")
    state["exchange"]["balances"] = {"USD": "5000.00"}

    result = risk.process(sized_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


def test_the_portfolio_cap_is_counted_from_the_store_not_from_state(
    risk: RiskEngine, sized_context: Any, store: StoreClient
) -> None:
    """This gate runs in the opportunity chain and the manage chain runs after it, so
    `state["position_manager"]` does not exist yet — the same structural reason engine 17
    reads the store. `max_concurrent_positions` is 3 in the committed config."""
    for index, pair in enumerate(("BTC/USD", "ETH/USD", "XRP/USD")):
        store.write_position(open_position(f"p-{index}", pair))

    result = risk.process(sized_context, build_state())

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_MAX_CONCURRENT_POSITIONS
    assert "qty" not in result.data, "the cap is checked before sizing, so nothing is sized"


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #


def test_a_null_ordermin_blocks_and_is_never_read_as_zero(
    risk: RiskEngine, sized_context: Any
) -> None:
    """A null `ordermin` means the `AssetPairs` fetch failed. Invariant 2 gives pair
    rules no fallback at all — "block that pair, a wrong `ordermin` produces invalid
    orders" — and zero is the one value that would make every position trivially large
    enough."""
    state = build_state()
    state["exchange"]["pairs"][PAIR]["ordermin"] = None

    result = risk.process(sized_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "qty" not in result.data


def test_no_equity_snapshot_blocks_rather_than_sizing_against_the_balance(
    risk: RiskEngine, engine_context: Any, store: StoreClient
) -> None:
    """Invariant 6 sizes against *total account equity* — cash plus open positions —
    which only engine 19 computes. Falling back to the cash balance would let the system
    size a trade against an equity figure nothing had computed, and a fallback is never
    allowed to be the optimistic reading."""
    engine_context.clients.store = store

    result = risk.process(engine_context, build_state())

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "equity" in (result.reason or "")


def test_a_float_price_is_refused_rather_than_coerced(
    risk: RiskEngine, sized_context: Any
) -> None:
    """A float survives the orchestrator's JSON check. Spec 35: float drift in an order
    quantity produces a Kraken rejection that is miserable to diagnose."""
    state = build_state()
    state["exchange"]["pairs"][PAIR]["last_price"] = 100.0

    result = risk.process(sized_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


@pytest.mark.parametrize("drop", ["scout", "exchange"])
def test_a_missing_publisher_blocks(risk: RiskEngine, sized_context: Any, drop: str) -> None:
    state = build_state()
    del state[drop]

    result = risk.process(sized_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


# --------------------------------------------------------------------------- #
# The seam with C's console
# --------------------------------------------------------------------------- #


def test_every_reason_code_this_engine_emits_is_renderable_by_the_console() -> None:
    """A code absent from C's `REASON_PROSE` renders "No reason was recorded." with no
    error anywhere. `ownership.md` now carries this as a seam row."""
    from acsoe.console.format import REASON_PROSE

    for code in (
        REASON_BELOW_ORDERMIN,
        REASON_BELOW_COSTMIN,
        REASON_INSUFFICIENT_QUOTE_BALANCE,
        REASON_MAX_CONCURRENT_POSITIONS,
    ):
        assert code in REASON_PROSE


def test_the_published_payload_is_json_serialisable(
    risk: RiskEngine, sized_context: Any
) -> None:
    import json

    data = risk.process(sized_context, build_state()).data

    assert json.loads(json.dumps(data))["qty"] == data["qty"]
    assert isinstance(data["qty"], str)
