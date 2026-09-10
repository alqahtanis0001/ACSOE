"""Engine 7 `scout`, part 1 — the tradable universe. Spec 43.

The test that carries the Phase 3 criterion is
`test_the_universe_size_responds_to_the_quote_balance`: the same fixture set must yield
**different pair counts** at a $10 balance and at a $5,000 balance. A filter that ignores
the balance passes an equality test and fails that one.

**Every exclusion rule is proved to be the *only* thing excluding its pair.** Each test
flips one input and asserts the pair enters — a test that only asserted "excluded" would
pass against a filter excluding everything, which is the failure mode a fail-closed engine
is most likely to have. The tick-grid rule in particular is easy to write so that it never
fires; `test_a_coarse_tick_grid_excludes_and_a_fine_one_does_not` makes it fire.

**No fixture here hand-builds `state`.** Every payload is `ExchangeEngine().process(...)`
and `MarketSensorEngine().process(...)` verbatim — A's real engines 1 and 3 against C's
fake Kraken client — for the reason spec 40 and 41 established: a mock that agrees with its
caller cannot notice a publisher it disagrees with, and it cannot notice a missing one at
all.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.harness.doubles import MappingConfig
from tests.harness.fake_kraken import FakeKrakenClient

from acsoe.clients.kraken.contracts import QuoteTick, TradeTick
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import EquitySnapshotRow
from acsoe.core.contracts import EngineStatus
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.scout.contracts import (
    EXCLUSION_REASONS,
    REASON_BELOW_COSTMIN,
    REASON_BELOW_ORDERMIN,
    REASON_CRYPTO_QUOTED,
    REASON_INPUTS_UNAVAILABLE,
    REASON_INSUFFICIENT_QUOTE_BALANCE,
    REASON_NO_FX_RATE,
    REASON_NO_LIVE_QUOTE,
    REASON_NO_QUOTE_BALANCE,
    REASON_PAIR_RULES_MISSING,
    REASON_QUOTE_NOT_PROVABLY_STABLE,
    REASON_TICK_GRID_TOO_COARSE,
)
from acsoe.engines.scout.engine import ScoutEngine

#: The fixture's four pairs. Named here as *test data*, which is the only place a pair name
#: is allowed to appear — `test_no_pair_name_is_written_into_the_engine_source` proves the
#: engine contains none.
USD_PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD")
CRYPTO_QUOTED_PAIR = "ETH/BTC"
ALL_PAIRS = (*USD_PAIRS, CRYPTO_QUOTED_PAIR)

RUN = "run-scout"


# --------------------------------------------------------------------------- #
# The client: C's fake, plus the stream half engine 3 reads
# --------------------------------------------------------------------------- #


class FakeKrakenWithStream(FakeKrakenClient):
    """C's fake Kraken client with the two stream methods engine 3 `market_sensor` reads.

    One object serves engines 1 and 3, which is how the daemon runs. Quotes are read out of
    the same committed `order_book.json` the fake already serves, through its own
    `order_book` call, so every price this filter sees is the fake exchange's book and moves
    with it. A test that wants a particular spread calls `set_order_book`.
    """

    def __init__(self, *, now: int = 0) -> None:
        super().__init__(now=now)
        self._stream_quotes: dict[str, QuoteTick] = {}
        self._stream_trades: tuple[TradeTick, ...] = ()

    def stream_pairs(self, pairs: Sequence[str], *, at: datetime) -> None:
        """Make the stream report a trade and a top-of-book quote for each pair.

        Engine 3 derives its quote set from the pairs it saw trade in the window, so a pair
        left out of this call gets no quote — which is exactly the fixture the "no live
        quote" exclusion needs, and the reason this is a call rather than a constructor
        argument.
        """
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


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def scout() -> ScoutEngine:
    return ScoutEngine()


@pytest.fixture
def kraken(engine_context: Any) -> FakeKrakenWithStream:
    """The fake exchange both real engines run against, attached to the context.

    Every pair in the committed fixture is streamed by default, so a test that wants one
    absent removes it rather than remembering to add the other three.
    """
    client = FakeKrakenWithStream()
    engine_context.clients.kraken = client
    client.stream_pairs(ALL_PAIRS, at=engine_context.now - timedelta(seconds=60))
    return client


def write_equity(store: StoreClient, amount: str) -> None:
    store.write_equity_snapshot(
        EquitySnapshotRow(
            cycle_id=1,
            run_id=RUN,
            ts=1_000,
            currency="USD",
            equity=Decimal(amount),
            peak_equity=Decimal(amount),
            cash=Decimal(amount),
            positions_value=Decimal("0.00"),
            unrealised_pnl=Decimal("0.00"),
            realised_pnl_cum=Decimal("0.00"),
            open_position_count=0,
            updated_at=1_000,
        )
    )


@pytest.fixture
def account(engine_context: Any, store: StoreClient, kraken: Any) -> Any:
    """A context with a real `StoreClient` carrying a $5,000 equity snapshot.

    Invariant 6 sizes against *total account equity*, which only engine 19 `memory`
    computes, and engine 19 is Phase 4. Same forward dependency engines 11 and 17 have, and
    resolved the same way: the row is written here rather than by a live engine.
    """
    write_equity(store, "5000.00")
    engine_context.clients.store = store
    kraken.set_balances({"USD": "5000.00", "BTC": "0.01000000", "ETH": "0.50000000"})
    return engine_context


def build_state(context: Any) -> dict[str, Any]:
    """`state` as the opportunity chain would have it when gate 7 runs.

    `state["exchange"]` and `state["market_sensor"]` are A's real engines' `data`, verbatim.
    """
    return {
        "system": {"mode": "running", "close_intent": False},
        "cycle_id": 1,
        "guard_blockers": [],
        "exchange": ExchangeEngine().process(context, {}).data,
        "market_sensor": MarketSensorEngine().process(context, {}).data,
    }


def universe(scout: ScoutEngine, context: Any) -> dict[str, Any]:
    """Run the filter and hand back `state["scout"]`."""
    result = scout.process(context, build_state(context))
    payload: dict[str, Any] = result.data
    return payload


def with_config(context: Any, **overrides: Any) -> Any:
    """The same context with `trading.*` keys overridden.

    Used for the two config-driven exclusions — `allow_crypto_quoted` and the stable set —
    because both are operator policy rather than exchange data, so varying the fake's
    fixture cannot reach them.
    """
    import dataclasses

    data = context.config.as_dict()
    trading = dict(data["trading"])
    for key, value in overrides.items():
        if value is _ABSENT:
            trading.pop(key, None)
        else:
            trading[key] = value
    data["trading"] = trading
    return dataclasses.replace(context, config=MappingConfig(data))


class _Absent:
    """Sentinel: remove the key entirely, which is not the same as setting it empty."""


_ABSENT = _Absent()


# --------------------------------------------------------------------------- #
# Registry shape
# --------------------------------------------------------------------------- #


def test_the_engine_declares_itself_as_the_registry_has_it(scout: ScoutEngine) -> None:
    """`scripts/verify.py` asserts `is_gate` against the registry table, which catches a
    gate registered as an ordinary engine — silent and expensive otherwise."""
    assert (scout.name, scout.number, scout.is_gate) == ("scout", 7, True)


# --------------------------------------------------------------------------- #
# The Phase 3 criterion
# --------------------------------------------------------------------------- #


def test_the_universe_size_responds_to_the_quote_balance(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The criterion, literally: different counts at $10 and at $5,000, both asserted.

    A filter that ignored the balance would return the same universe twice and pass an
    equality test. The exclusion is named as well as counted, because "fewer pairs" and
    "fewer pairs *for this reason*" are different claims and only the second says the
    balance did the work.
    """
    kraken.set_balances({"USD": "5000.00"})
    rich = universe(scout, account)

    kraken.set_balances({"USD": "10.00"})
    poor = universe(scout, account)

    assert rich["entered"] == 3
    assert poor["entered"] == 0
    assert rich["entered"] != poor["entered"]
    assert poor["excluded"][REASON_INSUFFICIENT_QUOTE_BALANCE] == 3


def test_a_smaller_account_reaches_a_different_exclusion_than_a_poorer_one(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream, store: StoreClient
) -> None:
    """The sharper version of the criterion, and the one that shows the arithmetic.

    The test above moves the *balance* while equity stays large, so every pair fails
    affordability. This one moves the whole account — a $10 account sizing a $6.67 notional
    — and the universe shrinks by one pair rather than to nothing: BTC and ETH still clear
    their minimums at that size and SOL does not, because SOL's `ordermin` of 0.05 is above
    the 0.0444 units $6.67 buys at the fixture's ask.

    That is the balance being *arithmetic* rather than a gate, which is what the Locked
    Decision means by "computed from `ordermin`, `costmin`, tick size, live spread and
    balance. No account-size thresholds."
    """
    kraken.set_balances({"USD": "5000.00"})
    big = universe(scout, account)

    store.connection.execute("DELETE FROM equity_snapshots")
    store.connection.commit()
    write_equity(store, "10.00")
    kraken.set_balances({"USD": "10.00"})
    small = universe(scout, account)

    assert set(big["pairs"]) == set(USD_PAIRS)
    assert set(small["pairs"]) == {"BTC/USD", "ETH/USD"}
    assert small["excluded"][REASON_BELOW_ORDERMIN] == 1


# --------------------------------------------------------------------------- #
# The six exclusion rules, each proved to be the only thing excluding its pair
# --------------------------------------------------------------------------- #


def test_a_pair_with_no_rules_is_excluded_and_with_rules_enters(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 2 gives pair rules no fallback in any mode: a wrong `ordermin` produces
    invalid orders, so an unknown one excludes the pair. The pair is still quoted, so this
    is the rules and nothing else."""
    kraken.remove_pair("SOL/USD")

    without = universe(scout, account)

    assert "SOL/USD" not in without["pairs"]
    assert without["excluded"][REASON_PAIR_RULES_MISSING] == 1

    kraken.set_pair_rule(
        "SOL/USD",
        base="SOL",
        quote="USD",
        ordermin="0.05",
        costmin="5.00",
        tick_size="0.001",
        lot_decimals=8,
        pair_decimals=3,
    )
    assert "SOL/USD" in universe(scout, account)["pairs"], "the rules were the only thing"


def test_a_pair_with_no_quote_is_excluded_and_is_not_read_as_a_zero_spread(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 2: an assumed spread invalidates the cost gate, so a pair with no live
    book is excluded rather than priced at zero. Zero is the most optimistic value the
    field can take, which is exactly why it must not be the default."""
    kraken.stream_pairs(
        [p for p in ALL_PAIRS if p != "SOL/USD"], at=account.now - timedelta(seconds=60)
    )

    without = universe(scout, account)

    assert "SOL/USD" not in without["pairs"]
    assert without["excluded"][REASON_NO_LIVE_QUOTE] == 1

    kraken.stream_pairs(ALL_PAIRS, at=account.now - timedelta(seconds=60))
    assert "SOL/USD" in universe(scout, account)["pairs"], "the quote was the only thing"


def test_a_crypto_quoted_pair_is_excluded_unless_the_operator_allows_it(
    scout: ScoutEngine, account: Any
) -> None:
    """Invariant 7: profit in a crypto-quoted pair is denominated in a volatile asset,
    which is a second directional bet the system did not choose to make.

    `ETH/BTC` is the fixture's case and it is built for this: it is quoted in BTC, and the
    account holds a positive BTC balance, so it passes every rule before this one.

    **Flipping the flag no longer admits it, and that is the operator's FX ruling working.**
    Before 2026-09-10 this test asserted the pair entered once `allow_crypto_quoted` was
    true — and it was the test that walked straight through the gap I had escalated, because
    a BTC-quoted pair's affordability was never computed against a reporting-currency
    notional. It is now excluded a second time, under `no_fx_rate`.

    So the assertion is that the flag moves the pair from one exclusion to a *different*
    one. That is a stronger claim than "the flag was the only thing" and it is the true one:
    the flag is the only thing standing between this pair and the FX gap behind it.
    """
    excluded = universe(scout, account)

    assert CRYPTO_QUOTED_PAIR not in excluded["pairs"]
    assert excluded["excluded"][REASON_CRYPTO_QUOTED] == 1
    assert REASON_NO_FX_RATE not in excluded["excluded"], "the policy rule fires first"

    allowed = universe(scout, with_config(account, allow_crypto_quoted=True))

    assert CRYPTO_QUOTED_PAIR not in allowed["pairs"]
    assert REASON_CRYPTO_QUOTED not in allowed["excluded"], "the flag removed that one"
    assert allowed["excluded"][REASON_NO_FX_RATE] == 1


def test_a_pair_quoted_in_another_currency_cannot_be_shown_affordable(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The FX ruling on its own subject: a *stable* quote that is not the reporting one.

    `EUR` is in `trading.stable_quote_currencies`, so a EUR-quoted pair is not crypto-quoted
    and the flag is irrelevant to it. It still cannot be shown affordable, because the
    position's cost is in USD and the balance is in EUR, and nothing publishes a rate
    between them.

    This is the case the ruling is really about — the crypto-quoted test reaches it only by
    disabling a policy — and it is the one that would bite first if the operator ever added
    a European pair. Excluding claims nothing about the world; inventing a rate or assuming
    parity would.
    """
    eur_pair = "SOL/EUR"
    kraken.set_pair_rule(
        eur_pair,
        base="SOL",
        quote="EUR",
        ordermin="0.05",
        costmin="5.00",
        tick_size="0.001",
        lot_decimals=8,
        pair_decimals=3,
    )
    kraken.set_order_book(eur_pair, bids=[("149.99", "500")], asks=[("150.00", "500")])
    kraken.set_balances({"USD": "5000.00", "EUR": "5000.00"})
    kraken.stream_pairs([*ALL_PAIRS, eur_pair], at=account.now - timedelta(seconds=60))

    result = universe(scout, account)

    assert eur_pair not in result["pairs"]
    # One, not two: `ETH/BTC` is also unconvertible but never reaches this rule, because
    # `crypto_quoted` fires first. That ordering is the tally working — a pair is attributed
    # to the first rule it fails, and the policy refusal is the more useful thing to tell an
    # operator than the mechanism gap behind it.
    assert result["excluded"][REASON_NO_FX_RATE] == 1
    assert result["excluded"][REASON_CRYPTO_QUOTED] == 1
    assert set(result["pairs"]) == set(USD_PAIRS), "the reporting-currency pairs are unaffected"


def test_an_absent_stable_set_excludes_under_its_own_code(
    scout: ScoutEngine, account: Any
) -> None:
    """The lead's ruling of 2026-09-10, and the reason there are two codes rather than one.

    With `trading.stable_quote_currencies` absent, no quote can be *shown* stable, so every
    pair is excluded — `scout` is the sole authority on the tradable universe and its
    errors run one way: over-including risks a trade the operator disabled, under-including
    costs an opportunity that recurs next tick.

    The code has to differ from `crypto_quoted`. A universe that shrank by policy and one
    that shrank because nobody supplied a config key look identical from the outside, and
    only the second is a fault somebody must fix.
    """
    without_the_set = universe(scout, with_config(account, stable_quote_currencies=_ABSENT))

    assert without_the_set["pairs"] == []
    assert without_the_set["excluded"][REASON_QUOTE_NOT_PROVABLY_STABLE] == len(ALL_PAIRS)
    assert REASON_CRYPTO_QUOTED not in without_the_set["excluded"]

    assert set(universe(scout, account)["pairs"]) == set(USD_PAIRS), "the set was the only thing"


def test_an_empty_stable_set_is_a_decision_and_not_an_absent_one(
    scout: ScoutEngine, account: Any
) -> None:
    """`None` and empty are different answers and must not be collapsed.

    An absent key means nobody has said which currencies are stable. An **empty** set is an
    operator saying "none of them are", which is a decision — so it excludes under the
    ordinary `crypto_quoted` code rather than the configuration-fault one.
    """
    empty = universe(scout, with_config(account, stable_quote_currencies=[]))

    assert empty["pairs"] == []
    assert empty["excluded"][REASON_CRYPTO_QUOTED] == len(ALL_PAIRS)
    assert REASON_QUOTE_NOT_PROVABLY_STABLE not in empty["excluded"]


def test_a_pair_whose_quote_currency_is_not_held_is_excluded(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 7: a pair is only executable if the account holds spendable balance in
    that quote currency. Held with a *positive* balance — a zero holding is not a small
    one."""
    kraken.set_balances({"EUR": "5000.00"})

    without = universe(scout, account)

    assert without["pairs"] == []
    assert without["excluded"][REASON_NO_QUOTE_BALANCE] == len(USD_PAIRS)

    kraken.set_balances({"USD": "5000.00"})
    assert set(universe(scout, account)["pairs"]) == set(USD_PAIRS), "the balance was it"


def test_a_zero_balance_is_not_a_positive_one(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The boundary of the rule above, as its own test: `> 0`, not `>= 0`. A currency
    present in the map with nothing in it is the shape a drained account takes, and it must
    not read as held."""
    kraken.set_balances({"USD": "0"})

    result = universe(scout, account)

    assert result["pairs"] == []
    assert result["excluded"][REASON_NO_QUOTE_BALANCE] == len(USD_PAIRS)


def test_a_coarse_tick_grid_excludes_and_a_fine_one_does_not(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The rule that is easy to write so it never fires. This makes it fire.

    On a pair whose tick is coarse relative to its price, a stop rounds onto the entry price
    itself and the position has no stop at all. `SOL/USD`'s ask is 150.002, so the stop
    distance at `stop_pct` 0.015 is 2.250030 — a tick of 3 swallows it, and a tick of 0.001
    does not. Excluding is the only fail-closed answer, and it is arithmetic over the pair's
    own rules rather than a threshold anyone chose.
    """
    kraken.set_pair_rule("SOL/USD", tick_size="3")

    coarse = universe(scout, account)

    assert "SOL/USD" not in coarse["pairs"]
    assert coarse["excluded"][REASON_TICK_GRID_TOO_COARSE] == 1

    kraken.set_pair_rule("SOL/USD", tick_size="0.001")
    assert "SOL/USD" in universe(scout, account)["pairs"], "the tick size was the only thing"


def test_the_tick_grid_boundary_is_strict(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """A tick *equal* to the stop distance is excluded, not admitted.

    At that tick the stop lands exactly on the first step away from the entry, which is the
    smallest expressible stop rather than a usable one — and "expressible at all" is the
    property the rule is about. Asserted because an implementation using `>` instead of
    `>=` passes every other test in this file.
    """
    stop_distance = Decimal("0.015") * Decimal("150.002")

    kraken.set_pair_rule("SOL/USD", tick_size=format(stop_distance, "f"))
    assert "SOL/USD" not in universe(scout, account)["pairs"]

    kraken.set_pair_rule("SOL/USD", tick_size=format(stop_distance / 2, "f"))
    assert "SOL/USD" in universe(scout, account)["pairs"]


def test_a_position_below_ordermin_excludes_the_pair(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The sizing half, and it is engine 11's arithmetic. A minimum above what the equity
    would buy means no position is possible, which is a different statement from "this
    candidate is refused" and is why the universe filter exists at all."""
    kraken.set_pair_rule("SOL/USD", ordermin="500")

    strict = universe(scout, account)

    assert "SOL/USD" not in strict["pairs"]
    assert strict["excluded"][REASON_BELOW_ORDERMIN] == 1

    kraken.set_pair_rule("SOL/USD", ordermin="0.05")
    assert "SOL/USD" in universe(scout, account)["pairs"], "the minimum was the only thing"


def test_a_position_below_costmin_excludes_the_pair(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """`costmin` is tested on the rounded quantity's value **at the bid** — the lowest the
    position could be worth — for the same reason engine 11 does it that way."""
    kraken.set_pair_rule("SOL/USD", costmin="999999.00")

    strict = universe(scout, account)

    assert "SOL/USD" not in strict["pairs"]
    assert strict["excluded"][REASON_BELOW_COSTMIN] == 1

    kraken.set_pair_rule("SOL/USD", costmin="5.00")
    assert "SOL/USD" in universe(scout, account)["pairs"], "the minimum was the only thing"


# --------------------------------------------------------------------------- #
# The counts, which the console renders
# --------------------------------------------------------------------------- #


def test_the_counts_add_up(scout: ScoutEngine, account: Any) -> None:
    """`scanned == entered + sum(excluded)`, which is what makes "Scanned 412 pairs. 38
    entered the tradable universe." true rather than approximately true. A pair that fell
    out of the filter without a code would break this silently."""
    result = universe(scout, account)

    assert result["scanned"] == len(ALL_PAIRS)
    assert result["scanned"] == result["entered"] + sum(result["excluded"].values())


def test_the_counts_add_up_when_every_rule_fires(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The same identity on a tick where several different rules fire at once, because one
    exclusion reason is a much weaker test of an exhaustive tally than four."""
    kraken.remove_pair("BTC/USD")
    kraken.set_pair_rule("SOL/USD", ordermin="500")
    kraken.set_pair_rule("ETH/USD", tick_size="100")

    result = universe(scout, account)

    assert result["scanned"] == result["entered"] + sum(result["excluded"].values())
    assert set(result["excluded"]) == {
        REASON_PAIR_RULES_MISSING,
        REASON_BELOW_ORDERMIN,
        REASON_TICK_GRID_TOO_COARSE,
        REASON_CRYPTO_QUOTED,
    }


def test_every_published_exclusion_code_is_one_this_module_declares(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The tally's keys are enumerated from `EXCLUSION_REASONS`, never invented in place.

    C's spec 46 test reads that tuple to build the operator prose, so a code appearing in
    the tally but not in the tuple would render "No reason was recorded." on the console
    with no error anywhere.
    """
    kraken.remove_pair("BTC/USD")
    kraken.set_pair_rule("SOL/USD", ordermin="500")

    result = universe(scout, account)

    assert set(result["excluded"]) <= set(EXCLUSION_REASONS)


#: Codes this engine emits whose operator prose is with C and has not landed yet.
#:
#: **Self-deleting: `test_no_exemption_outlives_the_prose_it_was_waiting_for` fails once the
#: prose arrives.** A plain exemption would sit here forever and quietly cover the next code
#: too — and the failure mode of this seam is silence, not noise, so the exemption is built
#: to be impossible to forget rather than to be remembered.
#:
#: **Empty, and that is its normal state.** It held `no_fx_rate` for roughly twenty minutes
#: on 2026-09-10, between the operator's FX ruling and C landing the prose. The expiry test
#: went red the moment C landed it, which is the mechanism working: the entry was deleted
#: because a test failed, not because anyone remembered.
PROSE_PENDING_WITH_C: frozenset[str] = frozenset()


def test_every_exclusion_code_is_renderable_by_the_console() -> None:
    """The seam nothing else would notice. `console/format.py` maps a stored code to the
    sentence an operator reads, and a code absent from that table renders "No reason was
    recorded." silently. Enumerated out of `EXCLUSION_REASONS` rather than hand-listed, so
    a code added later cannot skip this."""
    from acsoe.console.format import NO_REASON_RECORDED, REASON_PROSE, operator_reason

    missing = [
        code
        for code in EXCLUSION_REASONS
        if code not in REASON_PROSE and code not in PROSE_PENDING_WITH_C
    ]
    assert missing == [], f"C's REASON_PROSE has no entry for {missing}"
    for code in EXCLUSION_REASONS:
        if code in PROSE_PENDING_WITH_C:
            continue
        assert operator_reason(code) != NO_REASON_RECORDED


def test_no_exemption_outlives_the_prose_it_was_waiting_for() -> None:
    """The half that makes the exemption above safe, and the reason it is two tests.

    An exemption for a code C has *not yet* mapped is a truthful note about a seam
    mid-landing. The same exemption left in place after C lands the prose is a hole: it
    would cover the next code added, silently, and silence is exactly how this seam fails —
    an unmapped code renders "No reason was recorded." with no error anywhere.

    So this fails the moment the prose exists, and the fix is to delete the entry rather
    than to remember to. This phase has spent a great deal of time finding tests that could
    not fail; an exemption that cannot expire is the same defect wearing a different hat.
    """
    from acsoe.console.format import REASON_PROSE

    landed = sorted(code for code in PROSE_PENDING_WITH_C if code in REASON_PROSE)
    assert landed == [], (
        f"prose has landed for {landed}; delete it from PROSE_PENDING_WITH_C so the "
        "enumeration covers it again"
    )


# --------------------------------------------------------------------------- #
# The cross-check against engine 11
# --------------------------------------------------------------------------- #


def test_the_sizing_agrees_with_engine_eleven(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream, store: StoreClient
) -> None:
    """The test both READMEs name, and the thing that holds the duplicated arithmetic
    together.

    Contract rule 3 forbids one engine importing another, so the sizing is written twice on
    purpose. Two copies only stay honest while something compares them, so this runs the
    **real** engine 11 over the same pair and the same published state and requires the two
    to agree on every case in the table — including the two that sit one lot increment
    either side of `ordermin`, which is where a rounding disagreement would hide.

    "Agree" means: `scout` includes the pair if and only if `risk` approves it. It does not
    mean the reason codes match, because the two engines answer different questions — a
    portfolio already full refuses in engine 11 and is not a property of the pair at all.
    """
    from acsoe.engines.risk.engine import RiskEngine

    # 33.33333333 units at an ask of 100.00 from a $5,000 account, so the table straddles
    # the minimum by one lot increment in each direction.
    kraken.set_order_book("SOL/USD", bids=[("99.99", "500")], asks=[("100.00", "500")])
    kraken.stream_pairs(ALL_PAIRS, at=account.now - timedelta(seconds=60))

    table = [
        ("0.05", "5.00"),
        ("33.33333332", "5.00"),
        ("33.33333333", "5.00"),
        ("33.33333334", "5.00"),
        ("500", "5.00"),
        ("0.05", "3332.99999966"),
        ("0.05", "3333.00000000"),
        ("0.05", "999999.00"),
    ]

    risk = RiskEngine()
    for ordermin, costmin in table:
        kraken.set_pair_rule("SOL/USD", ordermin=ordermin, costmin=costmin)
        state = build_state(account)

        in_universe = "SOL/USD" in scout.process(account, state).data["pairs"]

        state["scout"] = {"pair": "SOL/USD"}
        approved = risk.process(account, state).data["approved"]

        assert in_universe is approved, (
            f"ordermin={ordermin} costmin={costmin}: scout says {in_universe}, "
            f"risk says {approved} — the duplicated arithmetic has drifted"
        )


# --------------------------------------------------------------------------- #
# Fail-closed, and nothing remembered
# --------------------------------------------------------------------------- #


def test_a_failed_asset_pairs_fetch_blocks_rather_than_publishing_an_empty_universe(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """Invariant 3, and the distinction that matters on the console.

    "The exchange listed nothing you can trade" and "we could not ask" are different facts.
    Publishing `scanned: 0` for the second would put a zero into the empty-state arithmetic
    that means something entirely different from a zero earned by filtering.
    """
    kraken.fail("asset_pairs")

    result = scout.process(account, build_state(account))

    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "scanned" not in result.data
    assert "pair_rules" in (result.reason or "")


def test_no_equity_snapshot_blocks_rather_than_sizing_against_a_balance(
    scout: ScoutEngine, engine_context: Any, store: StoreClient, kraken: Any
) -> None:
    """Invariant 6 sizes against *total account equity*, which only engine 19 computes.
    Falling back to a cash balance would let the system decide what it can trade against an
    equity figure nothing had computed, and a fallback is never the optimistic reading."""
    engine_context.clients.store = store

    result = scout.process(engine_context, build_state(engine_context))

    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert "equity" in (result.reason or "")


@pytest.mark.parametrize(
    ("break_it", "names"),
    [
        (lambda s: s.pop("exchange"), "exchange"),
        (lambda s: s["exchange"].__setitem__("pair_rules", None), "pair_rules"),
        (lambda s: s["exchange"]["pair_rules"].pop("pairs"), "pairs"),
        (lambda s: s.pop("market_sensor"), "market_sensor"),
        (lambda s: s["market_sensor"].pop("quotes"), "quotes"),
    ],
)
def test_each_cause_of_a_block_is_distinguishable_from_the_others(
    scout: ScoutEngine, account: Any, break_it: Any, names: str
) -> None:
    """One reason **code** covers six causes, so the code alone is a weak assertion.

    `scout_inputs_unavailable` is emitted for an absent `exchange`, a failed `AssetPairs`, a
    missing pair map, an absent `market_sensor`, a missing quote map, and an unreachable or
    empty store. A test that accepted the code for any of them could not tell a missing
    publisher from an unreachable database — the same shape as
    `pytest.raises(SomeError)` where one type has several causes, which
    `code-standards.md` now names, arriving at engine level rather than in a test double.

    It is not hypothetical here. When engine 7 first landed, C's criterion reported *"engine
    7 published no 'pairs' at the $10.00 balance"* — true, and useless, because the engine
    was fail-closing on `market_sensor`, which that criterion had never supplied. The code
    was right and said nothing. So each cause is asserted to **name itself** in the operator
    sentence, and the store causes have their own tests above.
    """
    state = build_state(account)
    break_it(state)

    result = scout.process(account, state)

    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert names in (result.reason or ""), (
        f"the block reason must name {names!r}; one code covers six causes and the code "
        "alone cannot tell them apart"
    )


def test_the_block_reasons_are_not_all_the_same_sentence(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The companion to the parametrised test above, asserted as a set.

    Each case there checks its own sentence names its own cause, which every case would
    still satisfy if the engine emitted one sentence containing every key name. Collecting
    the sentences and requiring them to be distinct is what rules that out.
    """
    reasons = set()
    for break_it in (
        lambda s: s.pop("exchange"),
        lambda s: s["exchange"].__setitem__("pair_rules", None),
        lambda s: s.pop("market_sensor"),
        lambda s: s["market_sensor"].pop("quotes"),
    ):
        state = build_state(account)
        break_it(state)
        reasons.add(scout.process(account, state).reason)

    assert len(reasons) == 4, f"four causes produced {len(reasons)} distinct sentence(s)"


def test_a_non_empty_universe_reports_ok_and_an_empty_one_passes(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """An empty universe is a tick with nothing to consider, which happens routinely on a
    small account. It is not an error and not a block — neither is "no candidate"."""
    assert scout.process(account, build_state(account)).status is EngineStatus.OK

    kraken.set_balances({"EUR": "1.00"})
    empty = scout.process(account, build_state(account))

    assert empty.status is EngineStatus.PASS
    assert empty.blocks_trading is False
    assert empty.data["pairs"] == []


def test_no_pair_name_or_exchange_value_is_written_into_the_engine_source() -> None:
    """The Locked Decision, checked directly rather than trusted.

    "No pair list, no config key holding one, no hardcoded symbol." A pair name or a
    remembered minimum in the source would satisfy every behavioural test in this file on a
    fixture that happened to match, which is the same reason engines 10 and 11 carry this
    guard for fees and order minimums.
    """
    import ast

    import acsoe.engines.scout as package

    # **The AST, not the source text.** Engines 10 and 11 scan raw text for their
    # remembered fees and minimums and that is right for them, but it is wrong here: this
    # module's docstrings *quote invariant 7* — "BTC, ETH, or any non-stable asset" — and
    # that quotation is what explains why there are two crypto-quoted codes rather than
    # one. A text scan flags the explanation along with the defect, and the only ways to
    # satisfy it are to delete the reasoning or to paraphrase the invariant until it stops
    # matching. Same shape as `code-standards.md`'s standing `RUF001` example: a rule that
    # is right in general and wrong on the line that is the fixture for it.
    #
    # Parsing instead checks the thing the Locked Decision actually forbids — a symbol or a
    # pair rule used as a *value* — and comments do not survive into the AST at all, so it
    # is a stricter check rather than a looser one.
    literals: list[str] = []
    for path in sorted(Path(package.__file__).parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(
                node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
            )
        }
        literals.extend(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value not in docstrings
        )

    for symbol in ("BTC", "ETH", "SOL", "USDT", "USDC", "XBT"):
        offenders = [text for text in literals if symbol in text]
        assert offenders == [], f"{symbol} is a symbol and the universe is computed: {offenders}"
    for remembered in ("0.00005", "0.002", "0.05", "5.00"):
        offenders = [text for text in literals if remembered in text]
        assert offenders == [], f"{remembered!r} looks like a remembered pair rule: {offenders}"


def test_the_published_payload_is_json_serialisable(scout: ScoutEngine, account: Any) -> None:
    """`EngineResult` validates this, so a failure here is a construction error — which is
    why it is worth one test saying so out loud: money leaves as a string, never a
    `Decimal`."""
    import json

    data = universe(scout, account)

    assert json.loads(json.dumps(data))["pairs"] == data["pairs"]
    assert isinstance(data["equity"], str)
