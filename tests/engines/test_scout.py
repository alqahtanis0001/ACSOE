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
from acsoe.clients.store.contracts import CashSource, EquitySnapshotRow
from acsoe.core.contracts import EngineStatus
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.scout.contracts import (
    CANDIDATE_FIELD,
    EXCLUSION_REASONS,
    REASON_BELOW_COSTMIN,
    REASON_BELOW_ORDERMIN,
    REASON_CRYPTO_QUOTED,
    REASON_EMPTY_UNIVERSE,
    REASON_INPUTS_UNAVAILABLE,
    REASON_INSUFFICIENT_QUOTE_BALANCE,
    REASON_NO_FX_RATE,
    REASON_NO_LIVE_QUOTE,
    REASON_NO_QUOTE_BALANCE,
    REASON_PAIR_RULES_MISSING,
    REASON_QUOTE_NOT_PROVABLY_STABLE,
    REASON_TICK_GRID_TOO_COARSE,
    rank_universe,
    select_candidate,
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
            cash_source=CashSource.CYCLE_START,
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
#: **Empty is its normal state.** It held `no_fx_rate` for roughly twenty minutes on
#: 2026-09-10, between the operator's FX ruling and C landing the prose; the expiry test
#: went red the moment C landed it, which is the mechanism working — the entry was deleted
#: because a test failed, not because anyone remembered.
#:
#: It held `empty_universe` for a few minutes under spec 44 — sent to C the minute the code
#: existed, ahead of the engine being finished, so it would not be the line holding up
#: spec 47. C landed the prose before the engine was done, and the expiry test emptied this
#: again. Twice now the mechanism has closed the gap rather than a person remembering.
#:
#: It held `no_rankable_pair` for minutes on 2026-09-19 (spec 144). C had landed the prose
#: before the engine was finished, and the expiry test emptied it on the first run.
PROSE_PENDING_WITH_C: frozenset[str] = frozenset()


def declared_reason_codes() -> dict[str, str]:
    """Every `REASON_*` string this engine's contract declares, read off the module.

    **Enumerated, never hand-listed**, and deliberately wider than `EXCLUSION_REASONS`: two
    of the codes this engine emits are statements about the *tick* rather than about a pair
    — `scout_inputs_unavailable` and `empty_universe` — and are kept out of that tuple on
    purpose, because counting them in the tally would break
    `scanned == entered + sum(excluded)`.

    A test that enumerated the tuple alone would therefore miss exactly the two codes an
    operator meets when something is wrong or when nothing qualified. C's own enumeration
    walks `vars()` for the same reason, and it was C noticing this that made the point.
    """
    import acsoe.engines.scout.contracts as module

    return {
        name: value
        for name, value in vars(module).items()
        if name.startswith("REASON_") and isinstance(value, str)
    }


def test_every_reason_code_this_engine_emits_is_renderable_by_the_console() -> None:
    """The seam nothing else would notice. `console/format.py` maps a stored code to the
    sentence an operator reads, and a code absent from that table renders "No reason was
    recorded." silently, with no error anywhere."""
    from acsoe.console.format import NO_REASON_RECORDED, REASON_PROSE, operator_reason

    declared = declared_reason_codes()
    assert set(EXCLUSION_REASONS) < set(declared.values()), (
        "the exclusion tuple must be a strict subset of the declared codes; the tick-level "
        "codes are what it is missing, and they are the ones an operator meets on a fault"
    )

    missing = sorted(
        code
        for code in declared.values()
        if code not in REASON_PROSE and code not in PROSE_PENDING_WITH_C
    )
    assert missing == [], f"C's REASON_PROSE has no entry for {missing}"
    for code in declared.values():
        if code in PROSE_PENDING_WITH_C:
            continue
        assert operator_reason(code) != NO_REASON_RECORDED


# --------------------------------------------------------------------------- #
# The handoff: engines 10 and 11 read the published pair with no translation
# --------------------------------------------------------------------------- #


def test_the_cost_gate_reads_the_published_candidate_with_no_translation(
    scout: ScoutEngine, account: Any
) -> None:
    """Spec 44's handoff check, run as one tick rather than asserted as a string equality.

    `scout` publishes `state["scout"]["pair"]` and engine 10 `cost` reads it through its own
    `CANDIDATE_PAIR_PATH`. Two constants, two modules, no import between them — contract
    rule 3 forbids one — so the only thing holding them together is that they name the same
    key. Comparing the two constants would prove they match *today*; running the two engines
    on one `state` proves the handoff works, which is the thing that was broken in three
    places when this phase opened.

    The gate is driven to a real net-edge comparison rather than a missing-input block,
    because a block would be satisfied by a `cost` that never found the pair at all.
    """
    from acsoe.engines.cost.contracts import REASON_INPUTS_UNAVAILABLE as COST_INPUTS
    from acsoe.engines.cost.engine import CostEngine

    state = build_state(account)
    scouted = scout.process(account, state)
    state["scout"] = scouted.data

    candidate = scouted.data[CANDIDATE_FIELD]
    # Engines 8 and 9 are C's and are Phase 5; they stay mocked, as spec 40 established.
    state["prediction"] = {"expected_move_pct": "0.03"}
    state["order_book"] = {"estimated_slippage_pct": "0.0005"}

    priced = CostEngine().process(account, state)

    assert priced.data["reason_code"] != COST_INPUTS, "cost found the candidate"
    assert priced.data["pair"] == candidate, "the same pair, with nothing in between"


def test_the_risk_gate_reads_the_published_candidate_with_no_translation(
    scout: ScoutEngine, account: Any
) -> None:
    """The same handoff for engine 11, which reads the pair through its own `SCOUT_KEY`.

    Both gates are checked because both read it, and because a candidate that reached one
    and not the other would be the audit's failure recurring at the next seam along.
    """
    from acsoe.engines.risk.contracts import REASON_INPUTS_UNAVAILABLE as RISK_INPUTS
    from acsoe.engines.risk.engine import RiskEngine

    state = build_state(account)
    scouted = scout.process(account, state)
    state["scout"] = scouted.data

    sized = RiskEngine().process(account, state)

    assert sized.data["reason_code"] != RISK_INPUTS, "risk found the candidate"
    assert sized.data["pair"] == scouted.data[CANDIDATE_FIELD]


def test_a_tick_with_no_candidate_leaves_the_downstream_gates_nothing_to_read(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The other side of the handoff, and the reason `pair` is absent rather than null.

    On a `PASS` tick the orchestrator stops the opportunity chain, so engines 10 and 11
    never run — but they must fail closed if they ever do, rather than reading a `None` as a
    pair. Asserted through the real cost gate: it blocks on the missing input rather than
    pricing something.
    """
    from acsoe.engines.cost.contracts import REASON_INPUTS_UNAVAILABLE as COST_INPUTS
    from acsoe.engines.cost.engine import CostEngine

    kraken.set_balances({"USD": "0"})
    state = build_state(account)
    scouted = scout.process(account, state)
    state["scout"] = scouted.data
    state["prediction"] = {"expected_move_pct": "0.03"}
    state["order_book"] = {"estimated_slippage_pct": "0.0005"}

    assert scouted.status is EngineStatus.PASS
    assert CANDIDATE_FIELD not in state["scout"]

    priced = CostEngine().process(account, state)

    assert priced.blocks_trading is True
    assert priced.data["reason_code"] == COST_INPUTS


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


# --------------------------------------------------------------------------- #
# Spec 44 — one candidate, or none
# --------------------------------------------------------------------------- #


def test_a_populated_universe_publishes_exactly_one_candidate(
    scout: ScoutEngine, account: Any
) -> None:
    """The pass half of the gate. One candidate leaves this engine, never several — the
    judgement chain considers one, and engines 10 and 11 read a single
    `state["scout"]["pair"]`."""
    result = scout.process(account, build_state(account))

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data[CANDIDATE_FIELD] in result.data["pairs"]
    assert isinstance(result.data[CANDIDATE_FIELD], str), "one pair, not a list of them"
    assert result.data["reason_code"] is None


def test_an_empty_universe_passes_and_does_not_block(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """**The middle case, and the assertion that would quietly be wrong forever.**

    `PASS` means "nothing to do this cycle; not an error", and the orchestrator stops the
    opportunity chain on it *without* setting `trading_blocked_by`. Nothing qualifying is
    this system's honest default state on a small account — the console renders it as
    *"Scanned 412 pairs. 38 entered the tradable universe. None qualified."*

    Recording it as a `BLOCK` would fill `block_records` with a normal Tuesday and corrupt
    engine 17 `safety`'s error rate, which counts those rows. A breaker tripped by ordinary
    quiet days is a breaker nobody can leave switched on.

    So the status is asserted **and** asserted not to be `BLOCK`: an engine returning
    `BLOCK` here would satisfy every other test in this file.
    """
    kraken.set_balances({"USD": "0"})

    result = scout.process(account, build_state(account))

    assert result.status is EngineStatus.PASS
    assert result.status is not EngineStatus.BLOCK
    assert result.blocks_trading is False
    assert result.data["pairs"] == []
    assert CANDIDATE_FIELD not in result.data, "absent, never null"
    assert result.data["reason_code"] == REASON_EMPTY_UNIVERSE


def test_a_gate_failure_blocks_and_is_not_the_same_as_nothing_qualifying(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The block half, asserted **beside** the pass half because the pair is the point.

    "We could not compute a universe" and "the universe is empty" are different facts and
    they take different statuses. Invariant 3 makes the first a block; spec 44 makes the
    second a pass. An engine that collapsed them would look correct from either test alone.
    """
    kraken.fail("asset_pairs")

    blocked = scout.process(account, build_state(account))

    assert blocked.status is EngineStatus.BLOCK
    assert blocked.blocks_trading is True
    assert blocked.reason
    assert CANDIDATE_FIELD not in blocked.data, "absent in both cases, never null"

    kraken.clear_failures("asset_pairs")
    kraken.set_balances({"USD": "0"})
    empty = scout.process(account, build_state(account))

    assert empty.status is EngineStatus.PASS
    assert empty.blocks_trading is False
    assert blocked.status is not empty.status, "the two facts do not share a status"


# --------------------------------------------------------------------------- #
# The ordering: alphabetical, and a recorded absence rather than a design
# --------------------------------------------------------------------------- #


def test_the_candidate_is_the_alphabetically_first_pair_in_the_universe(
    scout: ScoutEngine, account: Any
) -> None:
    """Ruled by the operator on 2026-09-10: there is no score in Phase 3.

    The universe here is BTC/USD, ETH/USD and SOL/USD, so the candidate is BTC/USD. Asserted
    **by name** rather than as `sorted(pairs)[0]`, which would be the implementation
    restated — a test that computes the expected answer the same way the engine does cannot
    disagree with it.
    """
    result = scout.process(account, build_state(account))

    assert set(result.data["pairs"]) == set(USD_PAIRS)
    assert result.data[CANDIDATE_FIELD] == "BTC/USD"


def test_the_ordering_does_not_move_when_spreads_or_volumes_change(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """**A hidden score would show up here as a different answer**, and this is the test
    carrying the whole ordering in Phase 3.

    A score over spread, volume, volatility or price is exactly what the ruling forbids — it
    would look like a ranking and be an arbitrary one. So the books are moved underneath the
    universe: BTC/USD is given a punishing spread and SOL/USD a tight one, which is the
    ordering any plausible invented score would reverse. The candidate does not move.
    """
    before = scout.process(account, build_state(account)).data[CANDIDATE_FIELD]

    # BTC/USD: a spread two hundred times wider than SOL/USD's, and a thinner book.
    kraken.set_order_book("BTC/USD", bids=[("49000.0", "0.01")], asks=[("51000.0", "0.01")])
    kraken.set_order_book("SOL/USD", bids=[("150.000", "900.0")], asks=[("150.001", "900.0")])
    kraken.stream_pairs(ALL_PAIRS, at=account.now - timedelta(seconds=60))

    after = scout.process(account, build_state(account)).data[CANDIDATE_FIELD]

    assert before == "BTC/USD"
    assert after == before, "the ordering is alphabetical; nothing about the book enters it"


def test_the_candidate_is_stable_under_a_shuffled_input_mapping(
    scout: ScoutEngine, account: Any
) -> None:
    """Determinism end to end: the published mappings are rebuilt in reverse, rotated and
    reverse-sorted, and the candidate does not move.

    Dict ordering is not part of engine 1's or engine 3's contract, which is exactly why an
    engine must not depend on it. Spec 44 asks for this directly — "shuffle the pair mapping
    and assert the answer is unchanged".

    **What this test does *not* prove, established by mutation rather than by reading.**
    Replacing `rank_universe`'s `sorted(pairs)` with `tuple(pairs)` leaves this test green.
    The engine builds its scan set as `sorted(set(rules) | set(quotes))`, so `rank_universe`
    is handed an already-ordered sequence and a ranking that merely preserved arrival order
    would still answer alphabetically. The two sorts are defence in depth in the engine and
    a blind spot in this test, and the blind spot is worth naming rather than leaving for
    someone to trip over.

    `test_rank_universe_orders_by_name_and_not_by_arrival` is what actually pins
    alphabetical-by-construction, and it is the one that caught that mutation.
    """
    baseline = scout.process(account, build_state(account)).data[CANDIDATE_FIELD]

    answers = {baseline}
    for reorder in (
        lambda items: list(reversed(items)),
        lambda items: items[1:] + items[:1],
        lambda items: sorted(items, key=lambda kv: kv[0], reverse=True),
    ):
        state = build_state(account)
        rules = state["exchange"]["pair_rules"]["pairs"]
        quotes = state["market_sensor"]["quotes"]
        state["exchange"]["pair_rules"]["pairs"] = dict(reorder(list(rules.items())))
        state["market_sensor"]["quotes"] = dict(reorder(list(quotes.items())))
        answers.add(scout.process(account, state).data[CANDIDATE_FIELD])

    assert answers == {"BTC/USD"}, f"the candidate moved with input order: {answers}"


def test_the_ordering_is_alphabetical_over_the_whole_universe_not_a_tie_break(
    scout: ScoutEngine, account: Any, kraken: FakeKrakenWithStream
) -> None:
    """The distinction spec 44 draws: alphabetical over the *whole* universe, not a
    tie-break applied to pairs some score already rated equal.

    Removing the alphabetically first pair must promote the next one by name. A hidden score
    with alphabetical tie-breaking would pass the fixed-universe test above and fail this,
    because it would promote whichever pair its score preferred rather than ETH/USD.
    """
    kraken.remove_pair("BTC/USD")
    without_btc = scout.process(account, build_state(account)).data

    assert "BTC/USD" not in without_btc["pairs"]
    assert without_btc[CANDIDATE_FIELD] == "ETH/USD"

    kraken.remove_pair("ETH/USD")
    without_eth = scout.process(account, build_state(account)).data

    assert without_eth[CANDIDATE_FIELD] == "SOL/USD"


def test_rank_universe_orders_by_name_and_not_by_arrival() -> None:
    """**The assertion that actually pins alphabetical-by-construction.**

    Found by mutation, and worth the explanation: replacing `sorted(pairs)` with
    `tuple(pairs)` inside `rank_universe` leaves every *behavioural* ordering test in this
    file green, because the engine hands it an already-sorted scan set. Only a direct call
    with deliberately unsorted input can tell "orders by name" from "preserves the order it
    was given".

    The input is reverse-alphabetical so that arrival order and name order disagree on every
    element rather than on one, and the assertion is on the whole tuple rather than on the
    first item — a ranking that returned the right head for the wrong reason would pass the
    weaker form.
    """
    assert rank_universe(["SOL/USD", "ETH/USD", "BTC/USD"]) == (
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
    )
    assert select_candidate(["SOL/USD", "ETH/USD", "BTC/USD"]) == "BTC/USD"
    assert rank_universe([]) == ()
    assert select_candidate([]) is None

    # Idempotent: ranking an already-ranked universe changes nothing. A ranking that
    # reversed on each call would satisfy the assertions above on one invocation.
    once = rank_universe(["c", "b", "a"])
    assert rank_universe(once) == once


def test_the_ordering_is_one_named_function_and_the_engine_holds_no_score(
    scout: ScoutEngine, account: Any
) -> None:
    """The seam Phase 5 will edit, asserted so it stays a seam.

    Spec 44 requires the ordering isolated in `contracts.py` as one named function — the way
    `CONDITION_ACTION` is a named table — so that fixing it in Phase 5 is one edit against a
    named thing rather than a hunt through the engine. This asserts the function exists,
    that it is what the engine's answer agrees with, and that the engine module itself
    contains no sorting of its own for a score to hide in.
    """
    import ast

    import acsoe.engines.scout.engine as engine_module

    assert rank_universe(["c", "a", "b"]) == ("a", "b", "c")
    assert select_candidate([]) is None
    assert select_candidate(["c", "a", "b"]) == "a"

    published = scout.process(account, build_state(account)).data
    assert published[CANDIDATE_FIELD] == select_candidate(published["pairs"])

    # The engine reaches the candidate **through the seam**, rather than computing an
    # ordering of its own that happens to agree today. `sorted` and `min` both appear in
    # this module legitimately — the scan set and the tick-grid barrier comparison — so a
    # blanket ban on them would be a rule about the wrong thing; what matters is that the
    # candidate comes from the named function Phase 5 will edit.
    tree = ast.parse(Path(engine_module.__file__).read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    # Spec 144 moved the call from `select_candidate` to `rank_universe`, because the
    # engine now publishes the whole expected-move order and not only its head. The seam
    # is the same one: `select_candidate` holds no ordering of its own.
    assert "rank_universe" in called, (
        "the candidate must come from contracts.rank_universe, so the ranking is one "
        "edit against a named seam rather than a hunt through the engine"
    )
    assert "max" not in called, "a max over a score is what the ruling forbids"


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


# --------------------------------------------------------------------------- #
# Spec 76 — the ranking, as a config-named feature
#
# `feature-specs/PHASE-5-TASKS.md` names this seam directly: `rank_universe` is always
# handed an already-sorted sequence, because the engine builds its scan set with `sorted`.
# So a ranking that merely preserved arrival order would still answer alphabetically end
# to end, and **an end-to-end fixture cannot see the difference**. Every ordering claim
# below is therefore made by a direct call on input whose arrival order and intended order
# disagree on every element, and the end-to-end tests exist to prove the wiring, not the
# ordering.
# --------------------------------------------------------------------------- #

#: A five-pair feature map. The values are deliberately not in pair-name order and not in
#: arrival order, so alphabetical, arrival and ranked are three different answers.
RANKED_FEATURE = "volatility_24h"
RANKED_VALUES = {
    "AAA/USD": 0.1,
    "BBB/USD": 0.5,
    "CCC/USD": 0.3,
    "DDD/USD": 0.9,
    "EEE/USD": 0.7,
}
RANKED_FEATURES = {pair: {RANKED_FEATURE: value} for pair, value in RANKED_VALUES.items()}

#: Reverse-alphabetical arrival, so arrival order disagrees with the intended order on
#: **every** element in both directions rather than on one.
ARRIVAL = tuple(sorted(RANKED_VALUES, reverse=True))

DESCENDING_ORDER = ("DDD/USD", "EEE/USD", "BBB/USD", "CCC/USD", "AAA/USD")
ASCENDING_ORDER = tuple(reversed(DESCENDING_ORDER))


def with_scout_config(context: Any, **overrides: Any) -> Any:
    """The same context with `scout.*` keys overridden, `_ABSENT` to remove one.

    Separate from `with_config`, which reaches `trading.*`. The ranking keys live under
    `scout`, and the committed `config/default.yaml` carries `scout.rank_descending` with
    **no `rank_feature`** — spec 59 decision 7 keeps it out until the operator rules on the
    spec 75 study — so removing the key is the committed state and not an edge case.
    """
    import dataclasses

    data = context.config.as_dict()
    section = dict(data.get("scout", {}))
    for key, value in overrides.items():
        if value is _ABSENT:
            section.pop(key, None)
        else:
            section[key] = value
    data["scout"] = section
    return dataclasses.replace(context, config=MappingConfig(data))


def test_rank_universe_orders_by_the_named_feature_and_not_by_arrival() -> None:
    """**The test the Phase 5 task list calls not optional**, in its feature form.

    Arrival order is the exact reverse of pair-name order, and the intended order agrees
    with neither: a ranking that returned `tuple(pairs)` gets reverse-alphabetical, one
    that ignored the feature and sorted gets alphabetical, and both differ from the answer
    on every element. The assertion is on the whole tuple rather than on the head, because
    a ranking that produced the right first pair for the wrong reason would satisfy the
    weaker form.
    """
    descending = rank_universe(
        ARRIVAL, features=RANKED_FEATURES, feature=RANKED_FEATURE, descending=True
    )
    ascending = rank_universe(
        ARRIVAL, features=RANKED_FEATURES, feature=RANKED_FEATURE, descending=False
    )

    assert descending == DESCENDING_ORDER
    assert ascending == ASCENDING_ORDER
    # The three answers are genuinely different, so none of the assertions above could be
    # satisfied by arrival order or by the alphabetical ordering this replaces.
    assert descending != ARRIVAL and descending != tuple(sorted(ARRIVAL))
    assert ascending != ARRIVAL and ascending != tuple(sorted(ARRIVAL))

    assert select_candidate(
        ARRIVAL, features=RANKED_FEATURES, feature=RANKED_FEATURE, descending=True
    ) == "DDD/USD"
    assert select_candidate(
        ARRIVAL, features=RANKED_FEATURES, feature=RANKED_FEATURE, descending=False
    ) == "AAA/USD"

    # Idempotent: ranking an already-ranked universe changes nothing. A ranking that
    # reversed on each call would satisfy every assertion above on one invocation.
    assert (
        rank_universe(descending, features=RANKED_FEATURES, feature=RANKED_FEATURE)
        == descending
    )


def test_rank_universe_is_still_alphabetical_when_no_feature_is_configured() -> None:
    """The committed state, and it must not become "whatever order the caller had".

    `feature=None` is what the engine passes while `scout.rank_feature` is absent, which is
    every tick until the operator rules on the spec 75 study. The input is again
    reverse-alphabetical so `tuple(pairs)` cannot pass.
    """
    assert rank_universe(ARRIVAL) == tuple(sorted(ARRIVAL))
    assert rank_universe(ARRIVAL, features=RANKED_FEATURES, feature=None) == tuple(sorted(ARRIVAL))
    assert select_candidate(ARRIVAL, features=RANKED_FEATURES, feature=None) == "AAA/USD"


@pytest.mark.parametrize("descending", [True, False])
def test_a_pair_with_no_value_sorts_last_and_is_never_dropped(descending: bool) -> None:
    """Four ways to have no value, one answer, and the pair stays in the universe.

    Spec 76: a pair whose value is null or absent sorts **after** every pair with a value,
    alphabetically among themselves, and is never dropped — a pair with no feature is still
    tradable, and dropping it would silently shrink the universe the filter just computed.

    The four are: an explicit null, a pair missing from the feature map, a row that is not
    a mapping at all, and NaN. NaN is here because `modelling/features.py` yields it for an
    unfilled lookback and it compares false against everything including itself, so a NaN
    left in a sort key orders unpredictably rather than loudly.
    """
    features: dict[str, Any] = {
        "AAA/USD": {RANKED_FEATURE: 0.1},
        "DDD/USD": {RANKED_FEATURE: 0.9},
        "BBB/USD": {RANKED_FEATURE: None},
        "CCC/USD": None,
        "EEE/USD": {RANKED_FEATURE: float("nan")},
        # "FFF/USD" is absent from the map entirely.
    }
    arrival = ("FFF/USD", "EEE/USD", "DDD/USD", "CCC/USD", "BBB/USD", "AAA/USD")

    ordered = rank_universe(
        arrival, features=features, feature=RANKED_FEATURE, descending=descending
    )

    valued = ("DDD/USD", "AAA/USD") if descending else ("AAA/USD", "DDD/USD")
    assert ordered[:2] == valued
    assert ordered[2:] == ("BBB/USD", "CCC/USD", "EEE/USD", "FFF/USD")
    assert set(ordered) == set(arrival), "a pair was dropped from the universe"
    assert len(ordered) == len(arrival)


@pytest.mark.parametrize("descending", [True, False])
def test_the_tie_break_is_the_pair_name_ascending_in_both_directions(descending: bool) -> None:
    """Equal values order by name ascending whichever way the feature is read.

    `sorted(..., reverse=True)` would reverse the tie-break along with the feature, so two
    equally-rated pairs would swap places when the direction flipped and the candidate
    would move on a flag that is supposed to order by the feature alone. Negating the value
    instead is what keeps the tie-break fixed, and this is the test that says so.
    """
    features = {pair: {RANKED_FEATURE: 0.5} for pair in ("AAA/USD", "BBB/USD", "CCC/USD")}

    ordered = rank_universe(
        ("CCC/USD", "BBB/USD", "AAA/USD"),
        features=features,
        feature=RANKED_FEATURE,
        descending=descending,
    )

    assert ordered == ("AAA/USD", "BBB/USD", "CCC/USD")


def test_rank_universe_handles_an_empty_universe_in_both_modes() -> None:
    assert rank_universe(()) == ()
    assert rank_universe((), features=RANKED_FEATURES, feature=RANKED_FEATURE) == ()
    assert select_candidate((), features=RANKED_FEATURES, feature=RANKED_FEATURE) is None


# --------------------------------------------------------------------------- #
# The engine's half: the config reads, the block, and what it publishes
# --------------------------------------------------------------------------- #


def test_the_engine_publishes_the_ranking_it_used(scout: ScoutEngine, account: Any) -> None:
    """Against the committed config, which has no `scout.rank_feature`.

    `rank_feature` is published as **null rather than omitted**, unlike `pair`: null is the
    answer here — the ordering was alphabetical because nothing is configured — and the
    spec 75 study's alphabetical control is exactly the distinction between that and a
    feature that rated every pair equally.
    """
    data = universe(scout, account)

    assert "rank_feature" in data, "null is the answer, so the key is published"
    assert data["rank_feature"] is None
    assert data["rank_descending"] is True
    assert data[CANDIDATE_FIELD] == min(data["pairs"]), "alphabetical while nothing is configured"


def test_the_engine_ranks_by_the_configured_feature(scout: ScoutEngine, account: Any) -> None:
    """The wiring, end to end through the real engine: the candidate follows the config key.

    The universe here is the fixture's three USD pairs, and the feature map is fabricated
    because engine 5 is C's and is not written yet. That is what the direct `rank_universe`
    tests above are for — this one proves the engine reads the two keys and `state["feature"]`
    and passes them to the seam, which no direct call can show.
    """
    features = {
        "feature": {
            "feature_names": [RANKED_FEATURE],
            "pairs": {"BTC/USD": {RANKED_FEATURE: 0.1}, "ETH/USD": {RANKED_FEATURE: 0.9}},
        }
    }

    descending = with_scout_config(account, rank_feature=RANKED_FEATURE, rank_descending=True)
    state = build_state(descending) | features
    published = scout.process(descending, state).data

    assert published["rank_feature"] == RANKED_FEATURE
    assert published["rank_descending"] is True
    assert published[CANDIDATE_FIELD] == "ETH/USD"
    # SOL/USD has no value at all and still enters the universe, behind both.
    assert "SOL/USD" in published["pairs"]

    ascending = with_scout_config(account, rank_feature=RANKED_FEATURE, rank_descending=False)
    flipped = scout.process(ascending, build_state(ascending) | features).data

    assert flipped[CANDIDATE_FIELD] == "BTC/USD"
    assert flipped["rank_descending"] is False


def test_the_candidate_moves_when_only_the_config_key_changes(
    scout: ScoutEngine, account: Any
) -> None:
    """One input changed, one answer changed. The same state, the same universe, the same
    feature map — only `scout.rank_feature` differs, and the candidate follows it.

    This is what separates "the engine ranks" from "the engine happens to agree with
    alphabetical on this fixture": the alphabetically first pair is BTC/USD and neither
    configured feature chooses it.
    """
    features = {
        "feature": {
            "feature_names": ["a", "b"],
            "pairs": {
                "BTC/USD": {"a": 0.1, "b": 0.9},
                "ETH/USD": {"a": 0.9, "b": 0.5},
                "SOL/USD": {"a": 0.5, "b": 0.1},
            },
        }
    }

    by_a = with_scout_config(account, rank_feature="a")
    by_b = with_scout_config(account, rank_feature="b")

    first = scout.process(by_a, build_state(by_a) | features).data
    second = scout.process(by_b, build_state(by_b) | features).data

    assert first[CANDIDATE_FIELD] == "ETH/USD"
    assert second[CANDIDATE_FIELD] == "BTC/USD"
    assert first[CANDIDATE_FIELD] != second[CANDIDATE_FIELD]


def test_a_configured_feature_with_no_engine_5_output_blocks(
    scout: ScoutEngine, account: Any
) -> None:
    """Fail closed, and this is the case the spec singles out.

    A configured ranking that silently fell back to alphabetical would be the placeholder
    score the operator refused in Phase 3: the engine would report a ranking it did not
    perform, and the candidate would be right only on the ticks where alphabetical happened
    to agree. Invariant 3 — a gate that cannot reach its data blocks.
    """
    context = with_scout_config(account, rank_feature=RANKED_FEATURE)

    result = scout.process(context, build_state(context))

    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert result.reason is not None
    # On the message, not the status: this engine blocks for many reasons and they share a
    # code. The reason names the key and the engine whose output was missing.
    assert "feature is absent" in result.reason
    assert RANKED_FEATURE in result.reason


def test_a_feature_payload_without_pairs_blocks_rather_than_ranking_nothing(
    scout: ScoutEngine, account: Any
) -> None:
    """Engine 5 present and `pairs` missing is a different fault from engine 5 absent, and
    both block. Reading it as an empty map would rank every pair as having no value and
    answer alphabetically — the silent fallback again, one level down."""
    context = with_scout_config(account, rank_feature=RANKED_FEATURE)

    result = scout.process(context, build_state(context) | {"feature": {"bar_ts": 1}})

    assert result.status is EngineStatus.BLOCK
    assert result.reason is not None
    assert "feature.pairs is absent" in result.reason


def test_a_feature_name_engine_5_does_not_publish_blocks(
    scout: ScoutEngine, account: Any
) -> None:
    """**The third way of being unable to rank, and the one that hides.**

    A misspelt `scout.rank_feature` finds no value for any pair, the no-value rule then
    orders every pair alphabetically among themselves, and the engine publishes the
    misspelt name beside a ranking it never performed. No exception, no null, and a
    candidate that is a real pair out of the real universe — so there is no signal
    anywhere that the ranking did not happen.

    The per-pair question ("does this pair have a value?") and the whole-universe question
    ("does this feature exist?") are different, and answering both with `_feature_value`
    returning `None` is what made this silent. Found by C reviewing the seam for spec 60's
    criterion, not by any of the thirteen mutations, which all mutate behaviour I had
    already thought of.
    """
    features = {
        "feature": {
            "feature_names": [RANKED_FEATURE, "bar_body_pct"],
            "pairs": {
                "BTC/USD": {RANKED_FEATURE: 0.1},
                "ETH/USD": {RANKED_FEATURE: 0.9},
            },
        }
    }
    typo = RANKED_FEATURE.replace("volatility", "volatilty")
    context = with_scout_config(account, rank_feature=typo)

    result = scout.process(context, build_state(context) | features)

    assert result.status is EngineStatus.BLOCK
    assert result.blocks_trading is True
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert result.reason is not None
    assert typo in result.reason
    assert "not one of the 2 features" in result.reason

    # And the near-miss is the whole point: the correctly spelled name still ranks, so
    # this is not an engine that blocks on every configured feature.
    spelled = with_scout_config(account, rank_feature=RANKED_FEATURE)
    ranked = scout.process(spelled, build_state(spelled) | features)
    assert ranked.status is EngineStatus.OK
    assert ranked.data[CANDIDATE_FIELD] == "ETH/USD"


def test_a_feature_payload_without_feature_names_blocks(
    scout: ScoutEngine, account: Any
) -> None:
    """`feature_names` is a required field of engine 5's payload, so its absence means the
    payload cannot answer the question this gate has to ask of it. Same refusal as a
    missing `pairs`, and for the same reason: reading it as "no names published" would put
    the silent fallback back exactly where it was."""
    context = with_scout_config(account, rank_feature=RANKED_FEATURE)
    payload = {"feature": {"pairs": {"BTC/USD": {RANKED_FEATURE: 0.1}}}}

    result = scout.process(context, build_state(context) | payload)

    assert result.status is EngineStatus.BLOCK
    assert result.reason is not None
    assert "feature.feature_names is absent" in result.reason


def test_every_name_engine_5_publishes_is_rankable(scout: ScoutEngine, account: Any) -> None:
    """The membership check must not refuse a name that is genuinely published.

    Against C's real engine 5 and its real `FEATURE_NAMES`, every published name is
    accepted and produces a candidate. Without this, the refusal above could be satisfied
    by an engine that refused everything, which is the fail-closed engine's likeliest bug
    and the one a block test alone cannot see.
    """
    from tests.conftest import require_module

    module = require_module(
        "acsoe.engines.feature.engine", reason="engine 5 `feature` (C, spec 64) does not exist yet"
    )
    state = build_state(account)
    state["feature"] = module.FeatureEngine().process(account, state).data
    names = list(state["feature"].get("feature_names") or [])
    assert len(names) > 1, "engine 5 published too few names for this to prove anything"

    for name in names:
        context = with_scout_config(account, rank_feature=str(name))
        result = scout.process(context, build_state(context) | {"feature": state["feature"]})
        assert result.status is not EngineStatus.BLOCK, f"{name} was refused but is published"


def test_engine_5_absent_is_not_a_fault_while_no_feature_is_configured(
    scout: ScoutEngine, account: Any
) -> None:
    """The committed state on every tick today: engine 5 is unwritten, nothing is
    configured, and engine 7 neither reads `state["feature"]` nor cares that it is missing.

    The pass half of the gate's pair. Without it, the block above could be satisfied by an
    engine that blocked whenever `state["feature"]` was absent, which would stop every tick
    in the tree as it stands.
    """
    result = scout.process(account, build_state(account))

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["rank_feature"] is None


def test_an_empty_rank_feature_name_is_refused(scout: ScoutEngine, account: Any) -> None:
    """A key set to nothing is not the same fact as a key nobody set.

    Ranking by a feature named `""` would find no value for any pair, order them
    alphabetically under the null rule, and publish `rank_feature: ""` — a ranking claimed
    and not performed. That is the placeholder score arriving through a typo, so it blocks.
    """
    for empty in ("", "   "):
        context = with_scout_config(account, rank_feature=empty)

        result = scout.process(context, build_state(context))

        assert result.status is EngineStatus.BLOCK
        assert result.reason is not None
        assert "empty feature name" in result.reason


def test_the_two_ranking_keys_are_read_through_config_and_not_defaulted_in_the_engine(
    scout: ScoutEngine, account: Any
) -> None:
    """Absent and null both mean alphabetical, and neither may mean "pick something".

    `scout.rank_feature` is absent from the committed YAML and spec 61 types the field
    `str | None`, so both states occur on real trees. `Config.get` reports them differently
    — a raise and a `None` — and this asserts the engine collapses them *to the same
    answer*, which is the one place in this engine where collapsing them is correct and is
    argued for at the call site.
    """
    absent = with_scout_config(account, rank_feature=_ABSENT)
    null = with_scout_config(account, rank_feature=None)

    for context in (absent, null):
        data = scout.process(context, build_state(context)).data
        assert data["rank_feature"] is None
        assert data[CANDIDATE_FIELD] == min(data["pairs"])

    # And the direction still reaches the payload from config rather than from a literal.
    flipped = with_scout_config(account, rank_descending=False)
    assert scout.process(flipped, build_state(flipped)).data["rank_descending"] is False


def test_the_ranking_runs_on_engine_5s_real_output_once_it_exists(
    scout: ScoutEngine, account: Any
) -> None:
    """The seam with no double in it, which is the half a fabricated map cannot cover.

    Every other ranking test above hands engine 7 a feature map this file wrote. Phase 4's
    standing finding is that a seam agreed between two agents and driven only by doubles is
    a test of the double: A's labeller tests were green against a `label_bars(...)` that
    never existed. So this one drives C's real engine 5 through the real orchestrator and
    ranks by a name out of its own `feature_names`, and it **skips only while
    `acsoe.engines.feature.engine` does not exist** — `require_module` re-raises if anything
    else is missing, so the day C lands engine 5 this test starts running rather than
    staying quietly skipped.
    """
    from tests.conftest import require_module

    module = require_module(
        "acsoe.engines.feature.engine", reason="engine 5 `feature` (C, spec 64) does not exist yet"
    )
    feature_engine = module.FeatureEngine()

    state = build_state(account)
    state["feature"] = feature_engine.process(account, state).data
    names = state["feature"].get("feature_names") or []
    assert names, "engine 5 published no feature names; the ranking has nothing to read"

    context = with_scout_config(account, rank_feature=str(names[0]))
    published = scout.process(context, build_state(context) | {"feature": state["feature"]}).data

    assert published["rank_feature"] == str(names[0])
    assert published[CANDIDATE_FIELD] in published["pairs"]


# --------------------------------------------------------------------------- #
# D10: a stale or crossed quote is not a live quote (operator ruling 2026-09-21)
# --------------------------------------------------------------------------- #
#
# Per-pair staleness and per-pair crossed books moved here from engine 4, which judged the
# whole tick on its oldest pair and so blocked every tick against the real exchange. Each
# test flips ONE input on one pair of a healthy tick and flips it back, so the exclusion
# is attributable to that input and nothing else.


def _bound(context: Any) -> float:
    """The shared staleness bound, read from the same key engine 4 reads. Read rather than
    retyped, so these tests follow the operator's value instead of pinning a copy of it."""
    return float(context.config.get("data_guard.max_data_age_s"))


def _scout_with(scout: ScoutEngine, context: Any, pair: str, **quote: Any) -> dict[str, Any]:
    """Engine 7 over a real tick in which one pair's quote differs in the named fields."""
    state = build_state(context)
    state["market_sensor"]["quotes"][pair].update(quote)
    payload: dict[str, Any] = scout.process(context, state).data
    return payload


def test_a_stale_quote_is_excluded_as_no_live_quote(scout: ScoutEngine, account: Any) -> None:
    """The operator's words: a stale quote IS no live quote. 438 s is `COOKIE/USD` at the
    smoke run's only decision bar."""
    stale = _scout_with(scout, account, "SOL/USD", age_s=438.0)
    fresh = _scout_with(scout, account, "SOL/USD", age_s=30.0)

    assert "SOL/USD" not in stale["pairs"]
    assert stale["excluded"][REASON_NO_LIVE_QUOTE] == 1
    assert "SOL/USD" in fresh["pairs"], "the age was the only thing"


def test_the_bound_itself_is_live_and_one_second_past_it_is_not(
    scout: ScoutEngine, account: Any
) -> None:
    """Same `<=` as engine 4's heartbeat, so the two gates agree on what "too old" means."""
    bound = _bound(account)

    at_bound = _scout_with(scout, account, "SOL/USD", age_s=bound)
    past = _scout_with(scout, account, "SOL/USD", age_s=bound + 1)

    assert "SOL/USD" in at_bound["pairs"]
    assert "SOL/USD" not in past["pairs"]


def test_a_crossed_book_is_excluded_as_no_live_quote(scout: ScoutEngine, account: Any) -> None:
    """Bid above ask is not a price anyone can trade at. It used to block every pair in
    engine 4; one thin book crossing is this pair's problem, not the feed's."""
    state = build_state(account)
    quote = state["market_sensor"]["quotes"]["SOL/USD"]
    bid, ask = quote["bid"], quote["ask"]

    crossed = _scout_with(scout, account, "SOL/USD", bid=ask, ask=bid)
    straight = _scout_with(scout, account, "SOL/USD", bid=bid, ask=ask)

    assert "SOL/USD" not in crossed["pairs"]
    assert crossed["excluded"][REASON_NO_LIVE_QUOTE] == 1
    assert "SOL/USD" in straight["pairs"], "the crossing was the only thing"


def test_a_quote_carrying_no_age_is_excluded_rather_than_assumed_fresh(
    scout: ScoutEngine, account: Any
) -> None:
    """Engine 3 stamps an age on every quote, so a missing one is a defect upstream — and
    a price that cannot be shown to be live is not treated as live."""
    state = build_state(account)
    del state["market_sensor"]["quotes"]["SOL/USD"]["age_s"]

    result = scout.process(account, state).data

    assert "SOL/USD" not in result["pairs"]
    assert result["excluded"][REASON_NO_LIVE_QUOTE] == 1


def test_the_tally_still_adds_up_with_stale_and_crossed_pairs(
    scout: ScoutEngine, account: Any
) -> None:
    """Reusing `no_live_quote` rather than minting a code is what keeps the arithmetic the
    console renders from untouched: `scanned == entered + sum(excluded)`."""
    state = build_state(account)
    quotes = state["market_sensor"]["quotes"]
    quotes["SOL/USD"]["age_s"] = 900.0
    quotes["ETH/USD"]["bid"], quotes["ETH/USD"]["ask"] = (
        quotes["ETH/USD"]["ask"],
        quotes["ETH/USD"]["bid"],
    )

    result = scout.process(account, state).data

    assert result["excluded"][REASON_NO_LIVE_QUOTE] == 2
    assert result["scanned"] == result["entered"] + sum(result["excluded"].values())


def test_a_null_staleness_bound_blocks_the_tick_rather_than_defaulting(
    scout: ScoutEngine, account: Any
) -> None:
    """A default would be a number silently deciding which prices count as live. The same
    OPERATOR REQUIRED reading every other threshold in this gate gets."""
    import dataclasses

    data = account.config.as_dict()
    data["data_guard"] = {**data["data_guard"], "max_data_age_s": None}
    unset = dataclasses.replace(account, config=MappingConfig(data))

    result = scout.process(unset, build_state(unset))

    assert result.status is EngineStatus.BLOCK
    assert "max_data_age_s" in (result.reason or "")
