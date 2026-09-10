"""Engine 10 `cost` — specs 34 and 40.

The two tests that carry the spec are `test_a_candidate_below_the_hurdle_is_blocked` and
`test_a_candidate_above_the_hurdle_passes`: a gate with only a happy path is incomplete.
The one that carries the *invariant* is `test_changing_the_fee_tier_changes_the_net_edge`,
because a hardcoded fee would pass a single-value test and only that one catches it.

**No fixture here builds `state["exchange"]`.** Spec 34's version of this file built it by
hand in the shape this engine expected, and that is what hid three wrong field names for a
whole phase: engine 10 read `exchange.fees.maker_pct` and engine 1 published
`exchange.fee_tier.maker_fee_pct`, so both sides passed their own tests while disagreeing
with each other. A mock that agrees with its caller is not a test of the seam; the mock is
what gets tested.

So every `state["exchange"]` below is `ExchangeEngine().process(...).data` verbatim —
A's real engine 1, run against C's fake Kraken client. A test that needs a *specific* fee
varies the fake's fixture through `set_fee_tier` and lets engine 1 publish the result. It
does not shortcut the publisher, because shortcutting the publisher is the defect.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Protocol

import pytest
from tests.harness.fake_kraken import FakeKrakenClient

from acsoe.core.contracts import EngineStatus
from acsoe.engines.cost.contracts import (
    REASON_INPUTS_UNAVAILABLE,
    REASON_NET_EDGE_BELOW_HURDLE,
    REASON_SPREAD_WIDER_THAN_MOVE,
    format_signed_pct,
)
from acsoe.engines.cost.engine import CostEngine
from acsoe.engines.exchange.engine import ExchangeEngine

#: Kraken tier 1, from `trading-invariants.md`'s reference table. These are **the fake
#: exchange's fixture**, not a payload for this engine: they are handed to
#: `FakeKrakenClient.set_fee_tier` and engine 1 publishes whatever comes back. That is the
#: only place these numbers are allowed to appear — the engine itself may not contain them,
#: and `test_no_reference_fee_appears_in_the_engine_source` proves it does not.
TIER_1 = {"tier": 1, "maker_fee_pct": "0.0040", "taker_fee_pct": "0.0080"}

#: Kraken tier 3. The pass tests use this because at tier 1 the gate is unreachable by
#: construction — see the README.
TIER_3 = {"tier": 3, "maker_fee_pct": "0.0022", "taker_fee_pct": "0.0038"}

PAIR = "SOL/USD"


class ExchangePublisher(Protocol):
    """Run engine 1 and hand back exactly what it put in `state`."""

    def __call__(self, fee_tier: Mapping[str, Any] | None = None) -> dict[str, Any]: ...


@pytest.fixture
def publish_exchange(engine_context: Any, fake_kraken: FakeKrakenClient) -> ExchangePublisher:
    """`state["exchange"]`, produced by A's real engine 1 against C's fake client.

    `engine_context` carries that same `FakeKrakenClient`, so configuring the fake here
    configures the client engine 1 is about to call. Engine 1 reads nothing out of `state`
    — it is the first engine of the first chain — so an empty dict is a faithful argument
    and not a shortcut.

    Engine 1 returns `OK` even when every fetch failed: a failed fetch is an expected
    outcome for it, and `ERROR` means *unexpected*. So the status assertion below is a
    check that engine 1 ran, not a check that the exchange answered.
    """

    def publish(fee_tier: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if fee_tier is not None:
            fake_kraken.set_fee_tier(**fee_tier)
        result = ExchangeEngine().process(engine_context, {})
        assert result.status is EngineStatus.OK
        return dict(result.data)

    return publish


def build_state(
    exchange: dict[str, Any],
    *,
    spread_pct: str = "0.0005",
    slippage_pct: str = "0.0005",
    expected_move_pct: str = "0.03",
    pair: str = PAIR,
) -> dict[str, Any]:
    """A `state` as the opportunity chain would have built it by the time gate 10 runs.

    `exchange` is engine 1's published payload and is taken as an argument rather than
    built here, which is the point of spec 40. Everything else is a stand-in for an engine
    that does not exist yet: engine 8 `prediction` and engine 9 `order_book` are C's and
    are Phase 5, and engine 3 `market_sensor`'s quote map is a single field this engine
    reads by a path that was ratified and audited as correct.

    Money is a string in every field, because that is what survives `EngineResult.data`'s
    JSON check — a `Decimal` is refused by it outright, so a fixture that used one would be
    testing a state the orchestrator cannot produce.
    """
    return {
        "system": {"mode": "running", "close_intent": False},
        "cycle_id": 1,
        "guard_blockers": [],
        "scout": {"pair": pair},
        "prediction": {"expected_move_pct": expected_move_pct},
        "order_book": {"estimated_slippage_pct": slippage_pct},
        # Spread is published by engine 3, the market-data engine — not by engine 1,
        # which is the account engine. Ratified by the lead on 2026-09-09 after B
        # proposed it on `exchange`; the deciding argument was that `data_guard` blocks
        # on stale data, a negative spread and a missing candle, and all three are
        # market-data faults that should arrive from one publisher. Re-audited under
        # spec 40 and confirmed correct — the one path that went through ratification is
        # the one path that was right.
        "market_sensor": {"bar_closed": True, "quotes": {pair: {"spread_pct": spread_pct}}},
        "exchange": exchange,
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
# The seam: engine 1's own output, no double on either side
# --------------------------------------------------------------------------- #


def test_engine_ones_own_output_drives_this_gate_to_a_net_edge_comparison(
    cost: CostEngine,
    engine_context: Any,
    publish_exchange: ExchangePublisher,
) -> None:
    """The check spec 40 exists for.

    A's real `ExchangeEngine` runs against C's fake client, its `data` becomes
    `state["exchange"]` verbatim, and this gate prices a candidate from it. Before spec 40
    this path reached `cost_inputs_unavailable` on every tick — the gate refusing
    everything for the wrong reason, in prose naming a key nothing writes — and no test in
    the tree could see it, because every fixture built the payload in the shape the engine
    wanted.

    So the assertion that carries the spec is the *negative* one: not a missing-input
    block. The two positive ones pin that the fees which reached the arithmetic are the
    ones engine 1 published, rather than numbers that merely happen to agree.
    """
    exchange = publish_exchange(TIER_3)
    state = build_state(exchange, expected_move_pct="0.03")

    result = cost.process(engine_context, state)

    assert result.data["reason_code"] != REASON_INPUTS_UNAVAILABLE
    assert result.data["clears_hurdle"] is True

    published = exchange["fee_tier"]
    expected_friction = (
        Decimal(published["maker_fee_pct"])
        + Decimal(published["taker_fee_pct"])
        + Decimal("0.0005")
        + Decimal("0.0005")
    )
    assert Decimal(result.data["friction_pct"]) == expected_friction


def test_engine_one_publishes_the_field_names_this_gate_reads(
    publish_exchange: ExchangePublisher,
) -> None:
    """The three names the Phase 3 audit found wrong, asserted against the publisher.

    `exchange.fees` / `maker_pct` / `taker_pct` / `fallbacks_used` were B's assumptions,
    written against an engine 1 that did not exist yet and recorded in `contracts.py`
    under a heading claiming they were ratified. What was ratified was a set of positions
    in the cross-chain key table — which engine publishes what, under which state key —
    and that table never fixed engine 1's field names.
    """
    exchange = publish_exchange(TIER_3)

    assert "fees" not in exchange
    assert "fallbacks_used" not in exchange
    assert set(exchange["fee_tier"]) >= {"maker_fee_pct", "taker_fee_pct"}
    assert "failed_fetches" in exchange


#: Engine 1's own top-level payload keys. Named as bare strings and turned into search
#: patterns at runtime, never written out as quoted-key-and-colon anywhere in this file —
#: otherwise the check below trips on its own source, which it did on the first run.
EXCHANGE_PAYLOAD_KEYS = ("fee_tier", "failed_fetches", "pair_rules", "balances")


def test_no_fixture_in_this_file_hand_builds_the_exchange_payload() -> None:
    """Operator ruling 2026-09-10: the fixtures are rewritten, not repointed.

    Renaming one key inside a hand-built dict would make this file green again and would
    leave the seam exactly as untested as it was. So the ruling is checked mechanically:
    none of engine 1's payload keys may appear here as a dict-key literal — a quoted name
    followed by a colon — because building that payload by hand requires at least one.
    Reading one back out of the published dict is subscript syntax and is untouched.

    What it does not catch, stated so nobody reads it as more than it is: a payload
    assembled through a variable, or one loaded from a committed file. The ruling permits
    the second — "a fixture derived from that output" — and the first would be a
    deliberate evasion rather than the drift this guards against. `TIER_1` and `TIER_3`
    name the two fee fields and are untouched by it: they are the *fake exchange's*
    fixture, handed to `set_fee_tier`, which is the route the spec asks for.
    """
    from pathlib import Path

    source = Path(__file__).read_text(encoding="utf-8")
    for name in EXCHANGE_PAYLOAD_KEYS:
        literal = '"' + name + '":'
        assert literal not in source, f"{name} is engine 1's to publish, not this file's to write"


# --------------------------------------------------------------------------- #
# The gate: a block test and a pass test
# --------------------------------------------------------------------------- #


def test_a_candidate_below_the_hurdle_is_blocked(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """Tier 3 friction is 0.70% here; at `hurdle_multiple` 1.5 the candidate needs an
    expected move above 1.75%. A 1.0% move does not clear it."""
    state = build_state(publish_exchange(TIER_3), expected_move_pct="0.01")

    result = cost.process(engine_context, state)

    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["clears_hurdle"] is False
    assert result.data["reason_code"] == REASON_NET_EDGE_BELOW_HURDLE


def test_a_candidate_above_the_hurdle_passes(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """The same friction, a 3% expected move: net edge 2.30% against a 1.05% hurdle."""
    state = build_state(publish_exchange(TIER_3), expected_move_pct="0.03")

    result = cost.process(engine_context, state)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["clears_hurdle"] is True
    assert result.data["reason_code"] is None


def test_the_arithmetic_is_invariant_5(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """Every figure pinned, so a plausible-looking refactor cannot quietly change one.

    friction = 0.0022 + 0.0038 + 0.0005 + 0.0005 = 0.0070
    net_edge = 0.0300 - 0.0070                   = 0.0230
    hurdle   = 1.5 x 0.0070                      = 0.0105

    The first two terms now arrive through engine 1 rather than out of the fixture, so a
    figure that stopped matching would mean the publisher changed and not that the
    arithmetic did.
    """
    state = build_state(publish_exchange(TIER_3), expected_move_pct="0.03")

    data = cost.process(engine_context, state).data

    assert Decimal(data["friction_pct"]) == Decimal("0.0070")
    assert Decimal(data["net_edge_pct"]) == Decimal("0.0230")
    assert Decimal(data["hurdle_pct"]) == Decimal("0.01050")
    assert Decimal(data["expected_move_pct"]) == Decimal("0.03")


def test_a_candidate_exactly_on_the_hurdle_does_not_clear_it(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """Invariant 5 says `net_edge > hurdle`, strictly. "Buys only when the expected move
    beats every cost **with margin to spare**" is the project's stated posture, and an
    equality that passed would be a candidate with exactly no margin."""
    # friction 0.0100; hurdle 0.0150; a move of 0.0250 gives net edge exactly 0.0150.
    state = build_state(
        publish_exchange({"tier": 2, "maker_fee_pct": "0.0040", "taker_fee_pct": "0.0040"}),
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
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """The test spec 34 names, now driven the whole way through the publisher.

    A hardcoded fee passes a single-value test and fails this one, which is why it is
    written as a comparison of two runs rather than as an assertion on one number. Spec 40
    adds the second half: the tier changes on the *fake client's fixture*, and engine 1
    republishes, so the constant this rules out is a constant anywhere on the path — not
    only one inside engine 10.
    """
    tier_1 = cost.process(engine_context, build_state(publish_exchange(TIER_1))).data
    tier_3 = cost.process(engine_context, build_state(publish_exchange(TIER_3))).data

    assert Decimal(tier_1["friction_pct"]) > Decimal(tier_3["friction_pct"])
    assert Decimal(tier_1["net_edge_pct"]) < Decimal(tier_3["net_edge_pct"])
    assert Decimal(tier_1["hurdle_pct"]) > Decimal(tier_3["hurdle_pct"])


def test_at_tier_one_nothing_clears_the_gate_and_at_tier_three_it_does(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
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

    at_tier_1 = build_state(publish_exchange(TIER_1), expected_move_pct=at_the_target_barrier)
    assert cost.process(engine_context, at_tier_1).blocks_trading is True

    at_tier_3 = build_state(publish_exchange(TIER_3), expected_move_pct=at_the_target_barrier)
    assert cost.process(engine_context, at_tier_3).blocks_trading is False


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
    ["scout", "prediction", "order_book", "exchange", "market_sensor"],
)
def test_a_missing_publisher_blocks(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher, drop: str
) -> None:
    """Invariant 3: a gate that cannot reach its data blocks."""
    state = build_state(publish_exchange(TIER_3))
    del state[drop]

    result = cost.process(engine_context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert drop in (result.reason or "")


def test_a_failed_trade_volume_blocks_and_the_reason_names_the_call(
    cost: CostEngine,
    engine_context: Any,
    fake_kraken: FakeKrakenClient,
    publish_exchange: ExchangePublisher,
) -> None:
    """Spec 37 retired the fee-tier fallback, so this is now a block in **every** mode.

    The assertion that matters is the one about the sentence. "missing exchange.fee_tier"
    is true and useless: it sends the operator to look at `state`, where they find a
    `None` that tells them nothing about why. Engine 1 names the call that failed and what
    it said, in `failed_fetches`, and that is what the operator can act on — so the block
    reason quotes the call, not the state key.
    """
    fake_kraken.fail("trade_volume")
    exchange = publish_exchange()
    assert exchange["fee_tier"] is None, "engine 1 publishes null, never a substituted fee"

    result = cost.process(engine_context, build_state(exchange))
    reason = result.reason or ""

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "trade_volume" in reason
    assert "unavailable" in reason
    assert "exchange.fee_tier" not in reason


def test_an_envelope_error_on_trade_volume_reaches_the_operator_sentence(
    cost: CostEngine,
    engine_context: Any,
    fake_kraken: FakeKrakenClient,
    publish_exchange: ExchangePublisher,
) -> None:
    """Kraken answers 200 with a populated `error` array, which is a failure. Engine 1
    records it as `api_error` rather than `unavailable`, and the two are different facts
    for whoever reads the block: "we got an answer and it was no" against "we got no
    answer"."""
    fake_kraken.fail_with_envelope_error("trade_volume", ["EGeneral:Permission denied"])

    result = cost.process(engine_context, build_state(publish_exchange()))
    reason = result.reason or ""

    assert result.blocks_trading is True
    assert "trade_volume" in reason
    assert "api_error" in reason
    assert "Permission denied" in reason


def test_a_null_spread_is_not_read_as_a_zero_spread(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """The failure this engine is most likely to have had.

    Invariant 2: a failed spread fetch blocks the pair, with no fallback, because an
    assumed spread invalidates the cost gate. A published `null` therefore has to be
    distinguishable from a published `0` — and `0` is the single most optimistic value
    the field can take, so reading one as the other turns a fetch failure into the
    cheapest possible trade.
    """
    state = build_state(publish_exchange(TIER_3), expected_move_pct="0.03")
    state["market_sensor"]["quotes"][PAIR]["spread_pct"] = None

    blocked = cost.process(engine_context, state)

    state["market_sensor"]["quotes"][PAIR]["spread_pct"] = "0"
    zero_spread = cost.process(engine_context, state)

    assert blocked.blocks_trading is True
    assert blocked.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert zero_spread.blocks_trading is False


def test_a_float_fee_is_refused_rather_than_coerced(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """A float survives `EngineResult.data`'s JSON check, so the orchestrator would not
    have stopped it. Spec 34 makes a float in the edge path a defect, so this gate
    refuses it at its own boundary instead of pricing a hurdle with a number that has
    already drifted.

    The float is written **into engine 1's real payload** rather than into a fixture, and
    the corruption is deliberate: engine 1 cannot currently produce one, because every
    money value it publishes goes through `money_text`. This gate must not depend on that
    staying true, because the validator between them accepts a float silently and the
    place it would surface is the fourth decimal of a hurdle comparison.
    """
    exchange = publish_exchange(TIER_3)
    exchange["fee_tier"]["maker_fee_pct"] = 0.0022

    result = cost.process(engine_context, build_state(exchange))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


def test_an_unknown_pair_blocks_rather_than_pricing_another_pairs_spread(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    state = build_state(publish_exchange(TIER_3))
    state["scout"]["pair"] = "BTC/USD"

    result = cost.process(engine_context, state)

    assert result.blocks_trading is True
    assert "BTC/USD" in (result.reason or "")


# --------------------------------------------------------------------------- #
# What the operator reads
# --------------------------------------------------------------------------- #


def test_the_blocking_reason_is_prose_carrying_the_number(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """`ui-context.md`: "Net edge -0.21% after fees" (with U+2212) beats `cost_gate_fail`."""
    state = build_state(publish_exchange(TIER_3), expected_move_pct="0.0039")

    result = cost.process(engine_context, state)
    reason = result.reason or ""

    assert reason.startswith("Net edge ")
    assert format_signed_pct(Decimal(result.data["net_edge_pct"])) in reason
    assert "cost_gate_fail" not in reason
    assert "\N{MINUS SIGN}" in reason, "a hyphen, not U+2212 — rule 6 of the number rules"


def test_a_spread_wider_than_the_move_gets_its_own_reason(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """Strictly a subset of "below hurdle", distinguished because it tells the operator
    the market is the problem rather than the candidate."""
    state = build_state(publish_exchange(TIER_3), spread_pct="0.05", expected_move_pct="0.03")

    result = cost.process(engine_context, state)

    assert result.data["reason_code"] == REASON_SPREAD_WIDER_THAN_MOVE
    assert "Spread" in (result.reason or "")


def test_every_reason_code_this_engine_emits_is_renderable_by_the_console() -> None:
    """The seam nothing else would notice.

    `console/format.py` maps a stored `reason_code` to the sentence an operator reads,
    and a code absent from that table renders "No reason was recorded." with no error
    anywhere. Two agents own the two halves; `ownership.md` now carries it as a seam row,
    and this is the assertion that holds it.

    `cost_inputs_unavailable` was exempt when this engine landed because C had not added
    it yet. C has, so the exemption is gone rather than the test — all three codes are
    now required to be renderable.
    """
    from acsoe.console.format import NO_REASON_RECORDED, REASON_PROSE, operator_reason

    for code in (
        REASON_NET_EDGE_BELOW_HURDLE,
        REASON_SPREAD_WIDER_THAN_MOVE,
        REASON_INPUTS_UNAVAILABLE,
    ):
        assert code in REASON_PROSE
        assert operator_reason(code) != NO_REASON_RECORDED


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
#
# The test that stood here asserted `fallbacks_used == ["fee_tier_assumed_tier_1"]`. It is
# deleted rather than rewritten, per spec 40 and the operator's ruling of 2026-09-10: the
# tier 1 fallback is retired, so the assertion has no subject left. See the build log.


def test_this_engine_applies_no_fallback_and_says_so_by_recording_none(
    cost: CostEngine,
    engine_context: Any,
    fake_kraken: FakeKrakenClient,
    publish_exchange: ExchangePublisher,
) -> None:
    """`fallbacks_used` is a real `rejections` column and it is empty, in every mode.

    Invariant 2 requires every decision affected by a fallback to record which one fired,
    and after spec 37 this gate has no fallback to apply: `AssetPairs` carries no fee
    schedule, so "assume tier 1" was never implementable from a runtime source, and a
    confirmed pair with no fee data now blocks.

    Asserted on a blocked tick as well as a priced one, because the blocked one is where
    the tempting mistake lives: engine 1 publishes `failed_fetches` on exactly that tick,
    and copying a failed fetch into this column would look like diligence while
    misreporting the thing invariant 2 asks to be recorded. A failure to fetch is the
    opposite of a fallback — nothing was substituted, so nothing was traded on.
    """
    priced = cost.process(engine_context, build_state(publish_exchange(TIER_3)))
    assert priced.data["fallbacks_used"] == []

    fake_kraken.fail("trade_volume")
    exchange = publish_exchange()
    assert exchange["failed_fetches"], "the tick this is asserted against has a failed fetch"

    blocked = cost.process(engine_context, build_state(exchange))
    assert blocked.blocks_trading is True
    assert blocked.data.get("fallbacks_used", []) == []


def test_the_published_payload_is_json_serialisable(
    cost: CostEngine, engine_context: Any, publish_exchange: ExchangePublisher
) -> None:
    """`EngineResult` validates this, so a failure here is a construction error rather
    than an assertion failure — which is exactly why it is worth one test that says so
    out loud: money leaves this engine as a string, never as a `Decimal`."""
    import json

    result = cost.process(engine_context, build_state(publish_exchange(TIER_3)))

    assert json.loads(json.dumps(result.data))["net_edge_pct"] == result.data["net_edge_pct"]
    assert isinstance(result.data["net_edge_pct"], str)
