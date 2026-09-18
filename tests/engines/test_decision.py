"""Engine 16 `decision` — spec 90.

**Nothing here hand-builds a publisher's payload where the publisher exists.**
`state["exchange"]`, `state["market_sensor"]`, `state["scout"]`, `state["cost"]` and
`state["risk"]` are A's and B's real engines 1, 3, 7, 10 and 11, run against C's fake
Kraken client — the Phase 3 ruling. Engines 8 `prediction` and 15 `skeptic` are C's and
need a trained artefact this file has no business loading, so their payloads are built
**through their own published contract models** and never as bare dicts, exactly as
engine 21's tests build engine 19's rows through `OrderRow`: a shape those engines could
not produce is refused before engine 16 ever sees it.

Engines 9 `order_book` and 14 `adaptive_router` do not exist at all, so theirs are the
only bare dicts in this file. `test_engines_nine_and_fourteen_still_do_not_exist` is the
tripwire that goes red the day they do, which is the day these two stop being allowed.

**Every block test differs from its pass test in one input**, and the inputs chosen are
deliberately the ones a real chain could move: an open position on the pair (which makes
engine 11 refuse for real), a `now` on which no bar closed, a real engine 10 payload
computed for a different candidate. Spec 90 step 5, and it is what stops "the gate
blocks" passing against an engine that blocks on everything.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from tests.harness.fake_kraken import FakeKrakenClient

from acsoe.clients.kraken.contracts import QuoteTick, TradeTick
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import (
    CashSource,
    EquitySnapshotRow,
    PositionRow,
    PositionStatus,
    to_micros,
)
from acsoe.core.contracts import EngineStatus
from acsoe.engines.adaptive_router.engine import AdaptiveRouterEngine
from acsoe.engines.cost.engine import CostEngine
from acsoe.engines.decision.contracts import (
    CHECKED_SOURCES,
    INTENT_FIELD,
    OPTIONAL_SOURCES,
    REASON_INPUT_MISSING,
    REASON_INPUTS_UNAVAILABLE,
    REASON_NO_APPROVED_QUANTITY,
    REASON_PAIR_DISAGREEMENT,
    REASON_STALE_BAR,
    REQUIRED_SOURCES,
    STATE_KEY,
)
from acsoe.engines.decision.engine import DecisionEngine
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.order_book.engine import OrderBookEngine
from acsoe.engines.prediction.contracts import PredictionState
from acsoe.engines.risk.contracts import RiskSizing
from acsoe.engines.risk.engine import RiskEngine
from acsoe.engines.scout.engine import ScoutEngine
from acsoe.engines.skeptic.contracts import SkepticState

PAIR = "SOL/USD"

#: The other pair in the universe. Used only to produce a **real** engine 10 payload for
#: a different candidate, which is what the pair-disagreement test splices in.
OTHER_PAIR = "ETH/USD"

#: The committed config: `timeframes.decision_bar_s` 900, `timeframes.tick_s` 60.
BAR_S = 900
TICK_S = 60

#: Tier 3, standing rule 8 of the Phase 6 task list: everything that drives a trade runs
#: at tier 3, because at tier 1 the cost gate is unreachable by construction and engine
#: 10 would refuse every candidate here for a reason unrelated to engine 16.
MAKER = "0.0022"
TAKER = "0.0038"

#: A two-cent spread on a $100 pair. Big enough that engine 11's ask-versus-bid rule is
#: visible and small enough that engine 10's friction stays under the hurdle.
BID = "99.98"
ASK = "100.00"

#: Engine 8's expected move. Comfortably past `2.5 x friction` at tier 3 — friction here
#: is 0.22% + 0.38% + 0.02% + 0.00% = 0.62%, so the hurdle needs a move above ~1.55%.
#:
#: The last term is engine 9's, and it is **exactly zero** on this book: the fake's top
#: bid level holds more than the 5,000 quote basis, so the walk consumes one level and
#: fills at the best bid. That is engine 9 working, and it is a weak witness — an engine
#: 10 that ignored the slippage term entirely would produce this same friction. Recorded
#: here rather than fixed here, because the fixture that fixes it is spec 94's: the
#: rehearsal's acceptance is "engine 10 reads engine 9's slippage, proven by
#: recomputation", and a zero cannot prove it.
EXPECTED_MOVE = "0.025"

#: The committed config's own worked example, quoted on `max_concurrent_positions`:
#: "the balance binds first at $5,000: one position is ~$3,333 notional".
EQUITY = "5000.00"


class FakeKrakenWithStream(FakeKrakenClient):
    """C's fake plus the two stream methods engine 3 reads, as in `test_risk.py`.

    Written out rather than imported so this file does not go red when another test of
    mine is refactored. The quotes are read out of the fake's own committed book through
    its own `order_book` call, so no price in this file is invented by the test.
    """

    def __init__(self) -> None:
        super().__init__()
        self._stream_quotes: dict[str, QuoteTick] = {}
        self._stream_trades: tuple[TradeTick, ...] = ()

    def stream_pairs(self, pairs: Sequence[str], *, at: datetime) -> None:
        from acsoe.platform.aio import run_blocking

        trades: list[TradeTick] = []
        quotes: dict[str, QuoteTick] = {}
        for pair in pairs:
            book = run_blocking(self.order_book(pair, 10))
            quotes[pair] = QuoteTick(pair=pair, ts=at, bid=book.best_bid, ask=book.best_ask)
            trades.append(TradeTick(pair=pair, ts=at, price=book.best_bid, qty=Decimal("1")))
        self._stream_quotes = quotes
        self._stream_trades = tuple(trades)

    def recent_trades(self) -> tuple[TradeTick, ...]:
        return self._stream_trades

    def latest_quote(self, pair: str) -> QuoteTick | None:
        return self._stream_quotes.get(pair)


def a_bar_closing_moment(after: datetime) -> datetime:
    """A `now` on which engine 3 reports a closed bar, derived rather than chosen.

    `bar_closed_on` asks whether `now // 900` changed since one tick ago, so any instant
    in the first 60 seconds of a bar qualifies. Thirty seconds in is the middle of that
    window, far from both edges, so the test does not turn on the boundary arithmetic
    `test_market_sensor.py` already owns.
    """
    return datetime.fromtimestamp(
        (int(after.timestamp()) // BAR_S + 1) * BAR_S + TICK_S // 2, tz=UTC
    )


def expected_closed_bar_ts(now: datetime) -> int:
    """The bar engine 3 will report as closed at `now`, computed independently.

    Deliberately not read back from engine 3's payload: the assertion that the intent
    carries *this tick's* bar has to be against a number derived from the clock, or it
    only proves engine 16 copied whatever it was given.
    """
    return (int(now.timestamp()) // BAR_S) * BAR_S - BAR_S


@pytest.fixture
def kraken(engine_context: Any) -> FakeKrakenWithStream:
    client = FakeKrakenWithStream()
    # Enough USD that engine 7 and engine 11 both find the position affordable: at 1%
    # risk and a 1.5% stop, $5,000 of equity sizes a ~$3,333 notional.
    client.set_balances({"USD": "5000.00"})
    client.set_fee_tier(tier=3, maker_fee_pct=MAKER, taker_fee_pct=TAKER)
    for pair in (PAIR, OTHER_PAIR):
        client.set_order_book(pair, bids=[(BID, "500")], asks=[(ASK, "500")])
    client.stream_pairs((PAIR, OTHER_PAIR), at=engine_context.now)
    return client


@pytest.fixture
def context(engine_context: Any, kraken: FakeKrakenWithStream, store: StoreClient) -> Any:
    """A tick on which a decision bar closed, wired to the fake exchange and the store.

    The equity snapshot is written here for the reason `test_risk.py` writes one:
    invariant 6 sizes against *total account equity*, only engine 19 computes it, and
    engine 19 is C's and does not run in this chain. Without it engine 11 refuses with
    `risk_inputs_unavailable` — correctly — and this file's whole premise evaporates,
    which is what `test_the_upstream_chain_actually_approves_before_engine_sixteen_sees_it`
    exists to catch. It caught it: that is how this row came to be here.
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
            cash_source=CashSource.CYCLE_START,
            updated_at=1_000,
        )
    )
    now = a_bar_closing_moment(engine_context.now)
    kraken.stream_pairs((PAIR, OTHER_PAIR), at=now)
    tick = dataclasses.replace(
        engine_context, now=now, previous_now=now - timedelta(seconds=TICK_S)
    )
    tick.clients.kraken = kraken
    tick.clients.store = store
    return tick


@pytest.fixture
def decision() -> DecisionEngine:
    return DecisionEngine()


def prediction_payload(
    *, pair: str, bar_ts: int, expected_move: str = EXPECTED_MOVE
) -> dict[str, Any]:
    """Engine 8's payload, through engine 8's own contract.

    C's engine 8 needs a trained artefact and this file has none, so the payload is built
    from `PredictionState` rather than run. It is not a bare dict: a field engine 8 could
    not publish, or money as a float, is refused here rather than reaching engine 16.
    """
    return PredictionState(
        pair=pair,
        bar_ts=bar_ts,
        model_run_id="run-2026-09-01",
        feature_version="v3",
        p_target=0.55,
        p_stop=0.25,
        p_timeout=0.20,
        expected_move_pct=expected_move,
        is_buy=True,
        di=0.4,
        di_threshold=0.9,
    ).to_state()


def skeptic_payload(*, pair: str) -> dict[str, Any]:
    """Engine 15's payload, through engine 15's own contract. It did not veto."""
    return SkepticState(
        pair=pair, model_run_id="skeptic-2026-09-01", p_wrong=0.31, threshold=0.6, vetoed=False
    ).to_state()


def approving_state(
    context: Any, *, candidate: str | None = PAIR, bar_ts: int | None = None
) -> dict[str, Any]:
    """`state` as the opportunity chain has it the instant before engine 16 runs.

    Engines 1, 3, 7, 10 and 11 are **run**, in registry order, each against the `state`
    the ones before it built. Only engines 8, 9, 14 and 15 are supplied, and only because
    they cannot be run here.

    `candidate` overrides engine 7's choice rather than replacing its payload: the rest of
    engine 7's output stays its own, and only the one field the downstream gates read is
    moved. That is what lets the pair-disagreement test differ in exactly one input.
    `candidate=None` leaves engine 7's own answer untouched, which is how the
    no-candidate test gets a scout payload nothing in this file wrote.
    """
    state: dict[str, Any] = {
        "system": {"mode": "running", "close_intent": False},
        "cycle_id": 7,
        "guard_blockers": [],
    }
    state["exchange"] = ExchangeEngine().process(context, state).data
    state["market_sensor"] = MarketSensorEngine().process(context, state).data
    state["scout"] = dict(ScoutEngine().process(context, state).data)
    if candidate is not None:
        state["scout"]["pair"] = candidate
    chosen = state["scout"].get("pair", PAIR)

    bar = state["market_sensor"]["closed_bar_ts"] if bar_ts is None else bar_ts
    state["prediction"] = prediction_payload(pair=chosen, bar_ts=bar)
    state["order_book"] = OrderBookEngine().process(context, state).data
    state["cost"] = CostEngine().process(context, state).data
    state["risk"] = RiskEngine().process(context, state).data
    state["adaptive_router"] = AdaptiveRouterEngine().process(context, state).data
    state["skeptic"] = skeptic_payload(pair=chosen)
    return state


def open_position(context: Any, pair: str) -> PositionRow:
    """A position engine 19 recorded earlier, so engine 11 refuses this pair for real."""
    opened_at = to_micros(context.now) - 60 * 1_000_000
    entry = Decimal("100.00")
    return PositionRow(
        position_id="pos-1",
        run_id="test-run",
        cycle_id=1,
        pair=pair,
        base=pair.split("/")[0],
        quote=pair.split("/")[1],
        status=PositionStatus.OPEN,
        qty=Decimal("10"),
        entry_price=entry,
        target_price=entry * Decimal("1.03"),
        stop_price=entry * Decimal("0.985"),
        timeout_at=to_micros(context.now) + 43_200 * 1_000_000,
        entry_userref=4_242,
        opened_at=opened_at,
        updated_at=opened_at,
    )


# --------------------------------------------------------------------------- #
# Registry shape
# --------------------------------------------------------------------------- #


def test_the_engine_declares_itself_as_the_registry_will_have_it(
    decision: DecisionEngine,
) -> None:
    """`engine-contracts.md:212` gives engine 16 a **Y** in the Gate column and
    `trading-invariants.md` lists it in invariant 4's protected set, both by the
    operator's ruling of 2026-09-16. `is_gate_matches_registry` compares this
    declaration against that table, so it is asserted here too rather than only there."""
    assert decision.name == "decision"
    assert decision.number == 16
    assert decision.is_gate is True


def test_the_upstream_chain_actually_approves_before_engine_sixteen_sees_it(
    context: Any,
) -> None:
    """The premise of every pass test in this file, asserted rather than assumed.

    If engine 10 or engine 11 were blocking — at tier 1 engine 10 refuses everything by
    construction, and with no quote balance engine 11 does — then `approving_state`
    would not be an approving state, and every "engine 16 passes" test below would be
    passing against a chain that never got there. This is the fixture checking itself.
    """
    state = approving_state(context)

    assert state["scout"]["pair"] == PAIR
    assert state["cost"]["clears_hurdle"] is True, "engine 10 approved at tier 3"
    assert state["risk"]["approved"] is True, "engine 11 sized a position"
    assert state["market_sensor"]["bar_closed"] is True, "a decision bar closed on this tick"


# --------------------------------------------------------------------------- #
# The pass, and the intent recomputed from the sources
# --------------------------------------------------------------------------- #


def test_a_coherent_tick_passes_and_publishes_an_intent_recomputed_from_the_sources(
    decision: DecisionEngine, context: Any
) -> None:
    """Spec 90 step 5: the intent is recomputed from the sources, not read back.

    Every expectation below names the payload it came from, so an engine 16 that invented
    a number, or copied the wrong one, fails here rather than agreeing with itself. The
    bar is computed from the clock rather than taken from engine 3, because "the intent
    carries *this tick's* bar" is only tested by a number the tick's own time produces.
    """
    state = approving_state(context)

    result = decision.process(context, state)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    data = result.data
    assert data["coherent"] is True
    assert data["reason_code"] is None

    intent = data[INTENT_FIELD]
    assert intent["pair"] == state["scout"]["pair"]
    assert intent["qty"] == state["risk"]["qty"]
    assert intent["closed_bar_ts"] == expected_closed_bar_ts(context.now)
    assert intent["cycle_id"] == state["cycle_id"]
    assert intent["net_edge_pct"] == state["cost"]["net_edge_pct"]
    assert intent["hurdle_pct"] == state["cost"]["hurdle_pct"]
    assert intent["expected_move_pct"] == state["cost"]["expected_move_pct"]
    assert intent["estimated_slippage_pct"] == state["order_book"]["estimated_slippage_pct"]
    assert intent["p_wrong"] == state["skeptic"]["p_wrong"]
    assert intent["model_run_id"] == state["prediction"]["model_run_id"]
    assert intent["active_model_run_id"] == state["adaptive_router"]["active_model_run_id"]


def test_the_intent_carries_no_number_engine_sixteen_could_have_invented(
    decision: DecisionEngine, context: Any
) -> None:
    """Composition, not decision: every value in the intent appears in a source payload.

    Weaker than the test above about *which* source, and stronger about there being no
    others: it walks the intent rather than a list, so a field added later that engine 16
    computes for itself is caught without this test being edited.
    """
    state = approving_state(context)
    published: set[Any] = set()
    for source in (*CHECKED_SOURCES, "market_sensor"):
        payload = state.get(source)
        if isinstance(payload, dict):
            published.update(
                value for value in payload.values() if isinstance(value, str | int | float)
            )
    published.add(state["cycle_id"])

    intent = decision.process(context, state).data[INTENT_FIELD]

    for field, value in intent.items():
        assert value in published, f"intent.{field} == {value!r} appears in no source payload"


def test_a_source_that_names_no_pair_is_not_a_disagreement(
    decision: DecisionEngine, context: Any
) -> None:
    """Engine 14 need not restate the candidate, and silence is not disagreement.

    The pass half of the pair clause, and it is the half that stops the gate being
    satisfied by an implementation that refuses any payload without a `pair`.
    """
    state = approving_state(context)
    assert "pair" not in state["adaptive_router"], "the router names no pair, by its own spec"

    result = decision.process(context, state)

    assert result.blocks_trading is False
    assert "adaptive_router" in result.data["checked"], "it was examined and it agreed"


# --------------------------------------------------------------------------- #
# Clause 1 — the pair
# --------------------------------------------------------------------------- #


def test_a_payload_judging_another_candidate_blocks_and_names_both(
    decision: DecisionEngine, context: Any
) -> None:
    """Engine 7 chose one pair and engine 10 approved another. Both are correct.

    The ETH/USD payload spliced in is a **real** engine 10 payload — the same engine run
    over the same chain with the other candidate — rather than the SOL/USD one with its
    `pair` field edited. That matters: an edited field tests string comparison, and a
    genuinely different payload tests what the failure actually looks like, which is two
    complete and internally consistent approvals about two different things.

    One input differs from the pass test: which payload sits under `state["cost"]`.
    """
    state = approving_state(context)
    state["cost"] = approving_state(context, candidate=OTHER_PAIR)["cost"]

    result = decision.process(context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_PAIR_DISAGREEMENT
    assert PAIR in (result.reason or ""), "the sentence names the candidate"
    assert OTHER_PAIR in (result.reason or ""), "and the pair that was judged instead"
    assert "cost" in (result.reason or ""), "and which engine judged it"


def test_a_scout_that_chose_nothing_blocks_rather_than_deciding_about_nothing(
    decision: DecisionEngine, context: Any, kraken: FakeKrakenWithStream
) -> None:
    """Engine 7 omits `pair` when it chose nothing, and returns `PASS`, which stops the
    chain — so reaching engine 16 without a candidate is the chain contradicting itself.

    The scout payload here is a **real** refusal: the account holds no USD, so every USD
    pair is excluded for `insufficient_quote_balance` and engine 7 names no candidate.
    One input differs from the pass test: the balance on the fake exchange.
    """
    kraken.set_balances({"USD": "0.00"})
    state = approving_state(context, candidate=None)
    assert "pair" not in state["scout"], "engine 7 really did choose nothing"

    result = decision.process(context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUT_MISSING


# --------------------------------------------------------------------------- #
# Clause 2 — the bar
# --------------------------------------------------------------------------- #


def test_a_payload_carrying_a_previous_bar_blocks_and_names_both_bars(
    decision: DecisionEngine, context: Any
) -> None:
    """A `state` key that survived a bar looks current to every engine that reads it.

    One input differs from the pass test: engine 8's `bar_ts` is one bar older. It is
    still a real `PredictionState`, so this is the payload engine 8 would have published
    on the previous bar and nothing else about it changed.
    """
    fresh = expected_closed_bar_ts(context.now)
    state = approving_state(context, bar_ts=fresh - BAR_S)

    result = decision.process(context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_STALE_BAR
    assert str(fresh) in (result.reason or ""), "the sentence names this tick's bar"
    assert str(fresh - BAR_S) in (result.reason or ""), "and the one that was carried"
    assert "prediction" in (result.reason or ""), "and which engine carried it"


def test_a_tick_on_which_no_bar_closed_blocks(decision: DecisionEngine, context: Any) -> None:
    """Engine 5 returns `PASS` when no bar closed, which stops the chain, so a null
    `closed_bar_ts` here is engine 16 running on a tick that had nothing to decide.

    One input differs from the pass test: `context.now`, moved half a bar in so no bar
    boundary was crossed since the previous tick. Engine 3 is re-run on it, so the null
    is engine 3's own answer rather than a key this test deleted.
    """
    mid_bar = context.now + timedelta(seconds=BAR_S // 2)
    quiet = dataclasses.replace(
        context, now=mid_bar, previous_now=mid_bar - timedelta(seconds=TICK_S)
    )
    state = approving_state(context)
    state["market_sensor"] = MarketSensorEngine().process(quiet, state).data
    assert state["market_sensor"]["closed_bar_ts"] is None, "engine 3 closed no bar here"

    result = decision.process(quiet, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUT_MISSING


# --------------------------------------------------------------------------- #
# Clause 3 — a payload that is not there
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("source", REQUIRED_SOURCES)
def test_a_required_payload_that_is_absent_blocks(
    decision: DecisionEngine, context: Any, source: str
) -> None:
    """Every one of the five, not a representative one.

    The opportunity chain stops at the first block or `PASS`, so engine 16 running at all
    means each of these ran and approved. An absent key is the chain contradicting
    itself, and invariant 3 says the absence of a "no" is never a "yes".
    """
    state = approving_state(context)
    del state[source]

    result = decision.process(context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUT_MISSING
    assert source in (result.reason or ""), "the sentence names what was missing"


@pytest.mark.parametrize("source", OPTIONAL_SOURCES)
def test_an_absent_provenance_payload_does_not_block(
    decision: DecisionEngine, context: Any, source: str
) -> None:
    """The pass half of the clause above, and the one asymmetry in this engine.

    Spec 97 says engine 14 publishes nothing engine 16 "reads to decide" while spec 90
    puts its `active_model_run_id` in the intent; both hold only if the field is a record
    rather than a criterion. Engine 9's slippage is treated the same way because engine
    10 — a gate — already refuses the tick when it is missing, and refusing again here
    would count one absence twice.

    The intent is still published and the field it would have carried is **omitted**,
    never null: the same shape as every other absent value in this system.
    """
    state = approving_state(context)
    del state[source]
    absent = {
        "order_book": "estimated_slippage_pct",
        "adaptive_router": "active_model_run_id",
    }[source]

    result = decision.process(context, state)

    assert result.blocks_trading is False
    assert source not in result.data["checked"], "it was not examined, and says so"
    assert absent not in result.data[INTENT_FIELD], "omitted, not null"


def test_checked_records_what_was_examined_and_not_what_was_expected(
    decision: DecisionEngine, context: Any
) -> None:
    """Without `checked`, "the pair matched everywhere" and "there was nowhere to match
    against" publish identically, and only one of those is a check."""
    state = approving_state(context)

    full = decision.process(context, state).data["checked"]
    del state["order_book"]
    thinner = decision.process(context, state).data["checked"]

    assert tuple(full) == CHECKED_SOURCES
    assert "order_book" in full
    assert "order_book" not in thinner


# --------------------------------------------------------------------------- #
# Clause 4 — the approved quantity
# --------------------------------------------------------------------------- #


def test_a_risk_refusal_reaching_engine_sixteen_blocks(
    decision: DecisionEngine, context: Any, store: StoreClient
) -> None:
    """Engine 11 refused, so the chain should have stopped at engine 11.

    A **real** refusal: a position is already open on the pair, which is invariant 6's
    per-pair clause and engine 11 declines to size a second one. So this payload has
    `approved: False` and no `qty` because engine 11 put it that way, not because the
    test did. One input differs from the pass test: a row in `positions`.
    """
    store.write_position(open_position(context, PAIR))
    state = approving_state(context)
    assert state["risk"]["approved"] is False, "engine 11 really did refuse"
    assert "qty" not in state["risk"], "and it published no quantity"

    result = decision.process(context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_NO_APPROVED_QUANTITY


@pytest.mark.parametrize(
    ("key", "value", "expected", "why"),
    [
        ("scout", {"pair": ""}, REASON_INPUT_MISSING, "a candidate that is the empty string"),
        (
            "risk",
            {"pair": PAIR, "approved": False, "qty": "10"},
            REASON_NO_APPROVED_QUANTITY,
            "a refusal that nevertheless carries a quantity",
        ),
    ],
    ids=["empty pair", "refused but sized"],
)
def test_a_shape_no_publisher_can_produce_is_still_refused(
    decision: DecisionEngine, context: Any, key: str, value: dict[str, Any], expected: str, why: str
) -> None:
    """Two guards that no *current* publisher can trip, kept and pinned anyway.

    Neither shape is reachable today and both are asserted deliberately rather than for
    coverage. Engine 7 omits `pair` entirely when it chose nothing rather than publishing
    an empty one, and `RiskSizing.to_state_data` emits `qty` only under `if self.approved`,
    so a refusal carrying a size cannot be constructed through engine 11's own contract.

    They are worth a test because **`state` is a plain dict**. Nothing in this system
    enforces that what sits under `state["risk"]` came out of `RiskSizing`; the contract
    governs the publisher, and engine 16 reads the mapping. Two mutations — `if False`
    over the approval check, and dropping the emptiness half of the candidate check —
    survived the whole file before these existed, which is the measurement that says the
    guards are currently load-bearing on nothing but this.

    If either publisher's contract changes so that the shape *is* producible, this test
    is what says the guard was already there.
    """
    state = approving_state(context)
    state[key] = {**state[key], **value}

    result = decision.process(context, state)

    assert result.blocks_trading is True, why
    assert result.data["reason_code"] == expected
    assert INTENT_FIELD not in result.data


def test_the_expected_move_in_the_intent_is_the_one_the_cost_gate_used(
    decision: DecisionEngine, context: Any
) -> None:
    """`expected_move_pct` exists in two payloads, and the intent must carry engine 10's.

    Engine 10 copies the figure from engine 8, so on every real tick the two are equal
    and reading either gives the same answer — which means the README's claim that all
    three of `net_edge_pct`, `hurdle_pct` and `expected_move_pct` come from one publisher
    had no witness at all. A mutation pointing the field at `state["prediction"]` survived
    the whole file.

    So the two are made to differ here: engine 10 runs against one prediction and a
    second, different one replaces it afterwards. The number that must survive is the one
    the gate decision was actually made on — a net edge in the record computed from a move
    the record does not carry is the record disagreeing with itself.

    This is the same finding as engine 21's `test_a_fill_sets_the_barriers_from_the_fill_
    price_and_not_the_bar_close`, the same day: an assertion whose two candidate sources
    happen to hold the same value proves nothing about which one was read.
    """
    state = approving_state(context)
    used_by_the_gate = state["cost"]["expected_move_pct"]
    superseded = "0.0333"
    assert superseded != used_by_the_gate
    state["prediction"] = prediction_payload(
        pair=PAIR, bar_ts=state["market_sensor"]["closed_bar_ts"], expected_move=superseded
    )

    intent = decision.process(context, state).data[INTENT_FIELD]

    assert intent["expected_move_pct"] == used_by_the_gate
    assert intent["expected_move_pct"] != superseded


def test_an_approval_that_names_no_quantity_blocks(
    decision: DecisionEngine, context: Any
) -> None:
    """One payload asserting an approval and a refusal at once.

    Engine 11 omits `qty` on every rejection, so this shape says the two halves of one
    payload disagree and neither can be trusted over the other. It is built through
    `RiskSizing` — engine 11's own contract, which permits it — rather than by deleting a
    key, so the shape asserted here is one the contract genuinely allows through.

    One input differs from the pass test: `qty`.
    """
    state = approving_state(context)
    sized = RiskSizing.model_validate(
        {**state["risk"], "pair": PAIR, "approved": True, "qty": None}
    )
    state["risk"] = sized.to_state_data()
    assert "qty" not in state["risk"]

    result = decision.process(context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_NO_APPROVED_QUANTITY


# --------------------------------------------------------------------------- #
# Clause 5 — the check itself cannot run
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda s: s.__setitem__("cycle_id", "7"), "a cycle id that is text"),
        (
            lambda s: s["market_sensor"].__setitem__("closed_bar_ts", "1757000000"),
            "a bar timestamp that is text",
        ),
        (
            lambda s: s["risk"].__setitem__("qty", 33.33),
            "a quantity that is a float and has already lost precision",
        ),
    ],
    ids=["cycle id is text", "bar ts is text", "quantity is a float"],
)
def test_a_clause_that_cannot_be_evaluated_blocks(
    decision: DecisionEngine, context: Any, mutate: Any, why: str
) -> None:
    """Invariant 3, at the edge where the data is present and unusable.

    The float case is the one worth having: it passes the orchestrator's
    JSON-serialisable check and would otherwise reach the order as a quantity that has
    already lost precision. `Money` refuses it, and engine 16 turns that refusal into a
    block rather than a best effort.
    """
    state = approving_state(context)
    mutate(state)

    result = decision.process(context, state)

    assert result.blocks_trading is True, why
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


# --------------------------------------------------------------------------- #
# The intent is absent on every block, without exception
# --------------------------------------------------------------------------- #


def every_blocking_scenario(context: Any, store: StoreClient) -> list[tuple[str, dict[str, Any]]]:
    """One `state` per way this gate can refuse, built the same way the tests above do."""
    fresh = expected_closed_bar_ts(context.now)
    scenarios: list[tuple[str, dict[str, Any]]] = []

    disagreeing = approving_state(context)
    disagreeing["cost"] = approving_state(context, candidate=OTHER_PAIR)["cost"]
    scenarios.append(("pair disagreement", disagreeing))

    scenarios.append(("stale bar", approving_state(context, bar_ts=fresh - BAR_S)))

    for source in REQUIRED_SOURCES:
        missing = approving_state(context)
        del missing[source]
        scenarios.append((f"{source} absent", missing))

    store.write_position(open_position(context, PAIR))
    scenarios.append(("risk refused", approving_state(context)))

    unusable = approving_state(context)
    unusable["cycle_id"] = "7"
    scenarios.append(("cycle id is text", unusable))
    return scenarios


def test_no_block_publishes_an_intent(
    decision: DecisionEngine, context: Any, store: StoreClient
) -> None:
    """Spec 90 step 3: absent **in its entirety** on a block.

    Not an empty mapping and not a null. A key called `intent` in the payload of a
    refused tick is a key some future engine 18 reads without checking the verdict, which
    is the same argument as engine 11 omitting `qty` — and the reason this walks every
    scenario rather than spot-checking one is that the exception would be in whichever
    one nobody checked.
    """
    for label, state in every_blocking_scenario(context, store):
        data = decision.process(context, state).data
        assert data["coherent"] is False, label
        assert INTENT_FIELD not in data, f"{label} published an intent"
        assert data["reason_code"] is not None, f"{label} blocked without saying why"


def test_the_published_payload_is_json_serialisable(
    decision: DecisionEngine, context: Any
) -> None:
    """Money leaves as a string; nothing here is a `Decimal` or a `datetime`."""
    import json

    data = decision.process(context, approving_state(context)).data

    assert json.loads(json.dumps(data))[INTENT_FIELD]["qty"] == data[INTENT_FIELD]["qty"]
    assert isinstance(data[INTENT_FIELD]["qty"], str)
    assert isinstance(data[INTENT_FIELD]["closed_bar_ts"], int)


# --------------------------------------------------------------------------- #
# The two seams that used to be stand-ins, and are not any more
# --------------------------------------------------------------------------- #


def test_no_publisher_payload_in_this_file_is_hand_built_any_more() -> None:
    """The tripwire that stood here has fired twice and is retired, not weakened.

    It asserted that engines 9 `order_book` and 14 `adaptive_router` did not exist,
    because `order_book_payload()` and `router_payload()` were the only hand-built
    publisher dicts in this file and were allowed only while their publishers did not
    exist. C landed spec 96 and then spec 97 within the day; both times the test went
    red, both times the stand-in was replaced with the real engine run in chain order,
    and both times the payload function was **deleted** rather than kept "for the unit
    tests" — a stand-in that outlives its publisher is a second description of an
    engine that nothing keeps true.

    What replaces the tripwire is the property it was protecting: no hand-built
    publisher payload is left. `prediction_payload` and `skeptic_payload` are the two
    exceptions and they are engines 8 and 15, which exist and are simply not runnable
    here — they need a fitted model artefact.
    """
    import importlib.util

    for name in ("acsoe.engines.order_book.engine", "acsoe.engines.adaptive_router.engine"):
        assert importlib.util.find_spec(name) is not None, (
            f"{name} has gone away; the stand-in it replaced was deleted, so "
            "`approving_state` will fail rather than quietly using an old dict"
        )
    assert "order_book_payload" not in globals()
    assert "router_payload" not in globals()


def test_engine_nines_own_payload_is_walked_by_the_coherence_check(
    decision: DecisionEngine, context: Any
) -> None:
    """The seam the tripwire warned about, now that engine 9 is real.

    Engine 9 publishes a `pair`, so engine 16's walk has something to check — and the
    walk is a walk over the payloads rather than a hand-written list of comparisons
    precisely so that landing engine 9 needed no edit to engine 16. This asserts that
    it really did not: engine 9 appears in `checked`, and a genuine engine 9 payload for
    the *other* candidate blocks.

    The spliced payload is a **real** engine 9 run over the other candidate, not the
    SOL/USD one with its `pair` edited — the same standard the engine 10 disagreement
    test holds itself to, and for the same reason: an edited field tests string
    comparison, a real payload tests what the failure looks like.
    """
    state = approving_state(context)
    assert state["order_book"]["pair"] == PAIR, "engine 9 names the candidate at all"
    assert "order_book" in decision.process(context, state).data["checked"]

    state["order_book"] = approving_state(context, candidate=OTHER_PAIR)["order_book"]

    result = decision.process(context, state)

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_PAIR_DISAGREEMENT
    assert "order_book" in (result.reason or ""), "the sentence names engine 9"


def test_every_reason_code_this_engine_emits_is_renderable_by_the_console() -> None:
    """A code absent from `REASON_PROSE` renders "No reason was recorded." — silently,
    with no error anywhere, which `ownership.md` carries as a seam row.

    This began as a tripwire asserting the *absence* of all five, because mapping them
    is C's under spec 99 and a "these are renderable" test would have been red in the
    tree until C landed. C landed them within the hour, the tripwire went red, and this
    is what it was written to become.

    The list is read from the contracts module rather than retyped, so a sixth code
    added to engine 16 later is checked here without anyone remembering to add it — the
    same argument as spec 99's own walking test, applied to one engine.
    """
    import acsoe.engines.decision.contracts as decision_contracts
    from acsoe.console.format import REASON_PROSE

    codes = sorted(
        value
        for name, value in vars(decision_contracts).items()
        if name.startswith("REASON_") and isinstance(value, str)
    )

    assert len(codes) == 5, f"engine 16's codes changed: {codes}"
    for code in codes:
        assert code in REASON_PROSE, f"{code} renders as 'No reason was recorded.'"


def test_the_state_key_is_the_one_engine_eighteen_will_read() -> None:
    """`state["decision"]`, spelled once. Engine 18 is spec 91 and reads this key; a
    rename that missed one side would be two engines agreeing about nothing."""
    assert STATE_KEY == "decision"
    assert DecisionEngine.name == STATE_KEY
