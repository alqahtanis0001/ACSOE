"""Engine 10 `cost` — spec 34.

The two tests that carry the spec are `test_a_candidate_below_the_hurdle_is_blocked` and
`test_a_candidate_above_the_hurdle_passes`: a gate with only a happy path is incomplete.
The one that carries the *invariant* is `test_changing_the_fee_tier_changes_the_net_edge`,
because a hardcoded fee would pass a single-value test and only that one catches it.

Every fixture here builds `state["exchange"]` by hand rather than running A's engine 1.
That is the point of the seam: the contract is agreed, the mock is B's, and neither agent
waits. When A's client lands, the numbers change and the assertions do not.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from acsoe.core.contracts import EngineStatus
from acsoe.engines.cost.contracts import (
    REASON_INPUTS_UNAVAILABLE,
    REASON_NET_EDGE_BELOW_HURDLE,
    REASON_SPREAD_WIDER_THAN_MOVE,
    format_signed_pct,
)
from acsoe.engines.cost.engine import CostEngine

#: Kraken tier 1, from `trading-invariants.md`'s reference table. Used here as a *test
#: input*, which is the only place these numbers are allowed to appear — the engine
#: itself may not contain them, and `test_no_reference_fee_appears_in_the_source` proves
#: it does not.
TIER_1 = {"maker_pct": "0.0040", "taker_pct": "0.0080"}

#: Kraken tier 3. The pass tests use this because at tier 1 the gate is unreachable by
#: construction — see the README.
TIER_3 = {"maker_pct": "0.0022", "taker_pct": "0.0038"}

PAIR = "SOL/USD"


def build_state(
    *,
    fees: dict[str, str],
    spread_pct: str = "0.0005",
    slippage_pct: str = "0.0005",
    expected_move_pct: str = "0.03",
    pair: str = PAIR,
    fallbacks: list[str] | None = None,
) -> dict[str, Any]:
    """A `state` as the opportunity chain would have built it by the time gate 10 runs.

    Money is a string in every field, because that is what survives
    `EngineResult.data`'s JSON check — a `Decimal` is refused by it outright, so a
    fixture that used one would be testing a state the orchestrator cannot produce.
    """
    return {
        "system": {"mode": "running", "close_intent": False},
        "cycle_id": 1,
        "guard_blockers": [],
        "scout": {"pair": pair},
        "prediction": {"expected_move_pct": expected_move_pct},
        "order_book": {"estimated_slippage_pct": slippage_pct},
        "exchange": {
            "fees": dict(fees),
            "pairs": {pair: {"spread_pct": spread_pct}},
            "balances": {"USD": "5000.00"},
            "fallbacks_used": list(fallbacks or []),
        },
    }


@pytest.fixture
def cost() -> CostEngine:
    return CostEngine()


# --------------------------------------------------------------------------- #
# Registry shape
# --------------------------------------------------------------------------- #


def test_the_engine_declares_itself_as_the_registry_has_it(cost: CostEngine) -> None:
    """`scripts/verify.py` asserts `is_gate` against the registry table, which catches a
    gate registered as an ordinary engine — silent and expensive otherwise."""
    assert (cost.name, cost.number, cost.is_gate) == ("cost", 10, True)


# --------------------------------------------------------------------------- #
# The gate: a block test and a pass test
# --------------------------------------------------------------------------- #


def test_a_candidate_below_the_hurdle_is_blocked(cost: CostEngine, engine_context: Any) -> None:
    """Tier 3 friction is 0.70% here; at `hurdle_multiple` 1.5 the candidate needs an
    expected move above 1.75%. A 1.0% move does not clear it."""
    state = build_state(fees=TIER_3, expected_move_pct="0.01")

    result = cost.process(engine_context, state)

    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["clears_hurdle"] is False
    assert result.data["reason_code"] == REASON_NET_EDGE_BELOW_HURDLE


def test_a_candidate_above_the_hurdle_passes(cost: CostEngine, engine_context: Any) -> None:
    """The same friction, a 3% expected move: net edge 2.30% against a 1.05% hurdle."""
    state = build_state(fees=TIER_3, expected_move_pct="0.03")

    result = cost.process(engine_context, state)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["clears_hurdle"] is True
    assert result.data["reason_code"] is None


def test_the_arithmetic_is_invariant_5(cost: CostEngine, engine_context: Any) -> None:
    """Every figure pinned, so a plausible-looking refactor cannot quietly change one.

    friction = 0.0022 + 0.0038 + 0.0005 + 0.0005 = 0.0070
    net_edge = 0.0300 - 0.0070                   = 0.0230
    hurdle   = 1.5 x 0.0070                      = 0.0105
    """
    state = build_state(fees=TIER_3, expected_move_pct="0.03")

    data = cost.process(engine_context, state).data

    assert Decimal(data["friction_pct"]) == Decimal("0.0070")
    assert Decimal(data["net_edge_pct"]) == Decimal("0.0230")
    assert Decimal(data["hurdle_pct"]) == Decimal("0.01050")
    assert Decimal(data["expected_move_pct"]) == Decimal("0.03")


def test_a_candidate_exactly_on_the_hurdle_does_not_clear_it(
    cost: CostEngine, engine_context: Any
) -> None:
    """Invariant 5 says `net_edge > hurdle`, strictly. "Buys only when the expected move
    beats every cost **with margin to spare**" is the project's stated posture, and an
    equality that passed would be a candidate with exactly no margin."""
    # friction 0.0100; hurdle 0.0150; a move of 0.0250 gives net edge exactly 0.0150.
    state = build_state(
        fees={"maker_pct": "0.0040", "taker_pct": "0.0040"},
        spread_pct="0.0010",
        slippage_pct="0.0010",
        expected_move_pct="0.0250",
    )

    result = cost.process(engine_context, state)

    assert Decimal(result.data["net_edge_pct"]) == Decimal(result.data["hurdle_pct"])
    assert result.blocks_trading is True


# --------------------------------------------------------------------------- #
# The fee is fetched, never a constant
# --------------------------------------------------------------------------- #


def test_changing_the_fee_tier_changes_the_net_edge(
    cost: CostEngine, engine_context: Any
) -> None:
    """The test spec 34 names. A hardcoded fee passes a single-value test and fails this
    one, which is the whole reason it is written as a comparison of two runs rather than
    as an assertion on one number."""
    tier_1 = cost.process(engine_context, build_state(fees=TIER_1)).data
    tier_3 = cost.process(engine_context, build_state(fees=TIER_3)).data

    assert Decimal(tier_1["friction_pct"]) > Decimal(tier_3["friction_pct"])
    assert Decimal(tier_1["net_edge_pct"]) < Decimal(tier_3["net_edge_pct"])
    assert Decimal(tier_1["hurdle_pct"]) > Decimal(tier_3["hurdle_pct"])


def test_at_tier_one_nothing_clears_the_gate_and_at_tier_three_it_does(
    cost: CostEngine, engine_context: Any
) -> None:
    """The design consequence recorded in the tracker, asserted rather than assumed.

    At `hurdle_multiple: 1.5`, `net_edge > 1.5 x friction` rearranges to
    `expected_move > 2.5 x friction`. Tier 1 friction here is 1.30%, so the bar is 3.25%
    — above the 3% target barrier. The same candidate clears at tier 3.

    If this test ever starts failing, the finding is not that the test is stale: it is
    that `hurdle_multiple`, the barriers, or the reference fees have moved, and the
    tracker's "at tier 1 nothing clears the cost gate" note needs revisiting with them.
    """
    at_the_target_barrier = "0.03"

    assert cost.process(
        engine_context, build_state(fees=TIER_1, expected_move_pct=at_the_target_barrier)
    ).blocks_trading is True
    assert cost.process(
        engine_context, build_state(fees=TIER_3, expected_move_pct=at_the_target_barrier)
    ).blocks_trading is False


def test_no_reference_fee_appears_in_the_engine_source() -> None:
    """`trading-invariants.md` calls its reference fees "for sanity-checking only — never
    for use in code". A constant that happened to equal tier 1 would satisfy every
    behavioural test above on a tier-1 fixture, so the source is checked directly."""
    from pathlib import Path

    import acsoe.engines.cost as package

    source = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted(Path(package.__file__).parent.glob("*.py"))
    )
    for reference in ("0.0040", "0.0080", "0.0022", "0.0038", "0.40", "0.80"):
        assert reference not in source, f"a reference fee {reference} is written into the engine"


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "drop",
    ["scout", "prediction", "order_book", "exchange"],
)
def test_a_missing_publisher_blocks(cost: CostEngine, engine_context: Any, drop: str) -> None:
    """Invariant 3: a gate that cannot reach its data blocks."""
    state = build_state(fees=TIER_3)
    del state[drop]

    result = cost.process(engine_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert drop in (result.reason or "")


def test_a_null_spread_is_not_read_as_a_zero_spread(
    cost: CostEngine, engine_context: Any
) -> None:
    """The failure this engine is most likely to have had.

    Invariant 2: a failed spread fetch blocks the pair, with no fallback, because an
    assumed spread invalidates the cost gate. A published `null` therefore has to be
    distinguishable from a published `0` — and `0` is the single most optimistic value
    the field can take, so reading one as the other turns a fetch failure into the
    cheapest possible trade.
    """
    state = build_state(fees=TIER_3, expected_move_pct="0.03")
    state["exchange"]["pairs"][PAIR]["spread_pct"] = None

    blocked = cost.process(engine_context, state)

    state["exchange"]["pairs"][PAIR]["spread_pct"] = "0"
    zero_spread = cost.process(engine_context, state)

    assert blocked.blocks_trading is True
    assert blocked.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert zero_spread.blocks_trading is False


def test_a_float_fee_is_refused_rather_than_coerced(
    cost: CostEngine, engine_context: Any
) -> None:
    """A float survives `EngineResult.data`'s JSON check, so the orchestrator would not
    have stopped it. Spec 34 makes a float in the edge path a defect, so this gate
    refuses it at its own boundary instead of pricing a hurdle with a number that has
    already drifted."""
    state = build_state(fees=TIER_3)
    state["exchange"]["fees"]["maker_pct"] = 0.0022

    result = cost.process(engine_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


def test_an_unknown_pair_blocks_rather_than_pricing_another_pairs_spread(
    cost: CostEngine, engine_context: Any
) -> None:
    state = build_state(fees=TIER_3)
    state["scout"]["pair"] = "BTC/USD"

    result = cost.process(engine_context, state)

    assert result.blocks_trading is True
    assert "BTC/USD" in (result.reason or "")


# --------------------------------------------------------------------------- #
# What the operator reads
# --------------------------------------------------------------------------- #


def test_the_blocking_reason_is_prose_carrying_the_number(
    cost: CostEngine, engine_context: Any
) -> None:
    """`ui-context.md`: "Net edge -0.21% after fees" (with U+2212) beats `cost_gate_fail`."""
    state = build_state(fees=TIER_3, expected_move_pct="0.0039")

    result = cost.process(engine_context, state)
    reason = result.reason or ""

    assert reason.startswith("Net edge ")
    assert format_signed_pct(Decimal(result.data["net_edge_pct"])) in reason
    assert "cost_gate_fail" not in reason
    assert "\N{MINUS SIGN}" in reason, "a hyphen, not U+2212 — rule 6 of the number rules"


def test_a_spread_wider_than_the_move_gets_its_own_reason(
    cost: CostEngine, engine_context: Any
) -> None:
    """Strictly a subset of "below hurdle", distinguished because it tells the operator
    the market is the problem rather than the candidate."""
    state = build_state(fees=TIER_3, spread_pct="0.05", expected_move_pct="0.03")

    result = cost.process(engine_context, state)

    assert result.data["reason_code"] == REASON_SPREAD_WIDER_THAN_MOVE
    assert "Spread" in (result.reason or "")


def test_every_reason_code_this_engine_emits_is_renderable_by_the_console() -> None:
    """The seam nothing else would notice.

    `console/format.py` maps a stored `reason_code` to the sentence an operator reads,
    and a code absent from that table renders "No reason was recorded." Two agents own
    the two halves, so this asserts they agree — and it deliberately allows
    `cost_inputs_unavailable` to be missing for now, because that path always writes
    prose and `operator_reason` prefers prose over the mapping. When C adds it, delete
    the exemption rather than the test.
    """
    from acsoe.console.format import REASON_PROSE, operator_reason

    assert REASON_NET_EDGE_BELOW_HURDLE in REASON_PROSE
    assert REASON_SPREAD_WIDER_THAN_MOVE in REASON_PROSE
    assert operator_reason(REASON_INPUTS_UNAVAILABLE, "Cost gate could not price it") != ""


@pytest.mark.parametrize(
    "ratio",
    ["-0.0021", "0.0230", "0", "-0.00001", "1.5"],
)
def test_the_local_percentage_formatter_agrees_with_the_console(ratio: str) -> None:
    """`format_signed_pct` is duplicated in this engine rather than imported, because an
    engine on the live loop importing from `console/` would put the web layer on the
    trading path. The duplication is only safe while the two agree, so this pins it."""
    from acsoe.console.format import format_signed_pct as console_format

    assert format_signed_pct(Decimal(ratio)) == console_format(Decimal(ratio))


# --------------------------------------------------------------------------- #
# Fallbacks
# --------------------------------------------------------------------------- #


def test_a_fallback_that_fired_is_carried_into_the_decision(
    cost: CostEngine, engine_context: Any
) -> None:
    """Invariant 2: every decision affected by a fallback records which fallback fired.
    This gate is where the fee-tier fallback actually changes an answer, so it is the
    decision that has to carry it."""
    state = build_state(fees=TIER_1, fallbacks=["fee_tier_assumed_tier_1"])

    data = cost.process(engine_context, state).data

    assert data["fallbacks_used"] == ["fee_tier_assumed_tier_1"]


def test_the_published_payload_is_json_serialisable(
    cost: CostEngine, engine_context: Any
) -> None:
    """`EngineResult` validates this, so a failure here is a construction error rather
    than an assertion failure — which is exactly why it is worth one test that says so
    out loud: money leaves this engine as a string, never as a `Decimal`."""
    import json

    result = cost.process(engine_context, build_state(fees=TIER_3))

    assert json.loads(json.dumps(result.data))["net_edge_pct"] == result.data["net_edge_pct"]
    assert isinstance(result.data["net_edge_pct"], str)
