"""Engines 18, 21 and 22 through real orchestrator ticks, before they are registered. Spec 87.

Written by A, and all three engines are B's. That is the deliberate exception A's
`test_guard_chain_rehearsal.py` and B's two rehearsals were written under: **this file
tests the orchestrator wiring, not the engines.** Whether engine 21 decides the right
barrier given a `state` is B's `tests/engines/test_position_manager.py`; whether the real
`Orchestrator` hands 18, 21, 22 and 19 a `state` they can act on, tick after tick, against
a real store and B's paper broker, is what spec 82's registration would otherwise
discover on the day.

**Everything runs at fee tier 3**, named from C's fixture through `use_fee_tier`. At fee
tier 1 no trade is possible by construction and every scenario below would be vacuous:
the cost gate's bar is 2.5x friction, and 2.5x tier-1 friction is above the 3.0% target
barrier. Assertion messages that concern money carry `tier_sentence(3)` for the same reason.

## Nothing here stages a `state` dict, and nothing upstream is supplied

Every engine runs, in the registry's relative order: guard 1, 2, 3, 4, 17; opportunity 5,
6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18; manage 21, 22, 19. The artefacts engines 8, 13
and 15 load are trained here, from C's constructed series, the way
`test_feature_chain_rehearsal.py` trains its skeptic fixture; the thresholds are the
committed ones (skeptic 0.50, DI and anomaly 0.99). There is **no compromise on "real
upstream"** in this file: a probe measured, before any test was written, that the real
chain approves a real BUY on this window and engine 18 places it. The build log has the
numbers.

The market is C's `ScriptedMarket` (spec 100's harness) wrapped by B's `PaperBroker`,
which is exactly how `cli/engine.py` wires paper mode. What the market *did* is the one
thing this file invents, and it is invented in the open: the stream quote and the REST
book are pinned to one price at every step, a fill is a planted trade strictly below the
limit, and a barrier touch is a planted trade at the barrier.

## What is asserted after every tick

`orders`, `positions`, `trades` and `equity_snapshots` are read back out of the store
after **every** tick and compared row for row, column for column, against the rows 18,
21 and 22 published on that tick — in engine 19's own publisher order, so the row that
must survive an upsert is the one expected. A row nobody published this tick must be
byte-for-byte what it was. See :func:`check_recorded`.

## The finding this rehearsal made, and how the scenarios are arranged around it

**Every paper fill inflated `peak_equity` by the position's notional**, and engine 17
froze the account two ticks later. Engine 1 read the paper ledger at the top of the tick,
before engine 19 had recorded that tick's fill, while engine 21 already counted the new
position in `positions_value`. Build log, 2026-09-16, "FINDING, not fixed". Spec 103 (B,
`178a0a8`) fixed it in the broker: the ledger now counts every fill the broker has
executed, recorded or not.

`test_a_filled_position_is_watched_across_quiet_ticks` is the scenario it broke. It was a
strict `xfail` naming the finding until spec 103 landed and it passed, and it is now a
plain test. Every other scenario still puts the tick it is *about* directly after the
fill. That arrangement was made so those scenarios would not depend on the defect, and
it costs nothing now that the defect is gone.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import pytest
from tests.harness.doubles import FakeClients, FixedClock, MappingConfig, load_default_config
from tests.harness.fake_kraken import TIER_3, FakeRecorder, fee_tier_profile, tier_sentence
from tests.harness.market_script import Bar, ScriptedMarket

from acsoe.clients.paper.broker import PaperBroker
from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import (
    CommandName,
    CommandRow,
    CommandSource,
    EquitySnapshotRow,
    OrderRow,
    PositionRow,
    TradeRow,
    to_micros,
)
from acsoe.clients.store.migrations import apply_migrations
from acsoe.core.contracts import Chains
from acsoe.core.orchestrator import Orchestrator
from acsoe.engines.adaptive_router.engine import AdaptiveRouterEngine
from acsoe.engines.anomaly.engine import AnomalyEngine
from acsoe.engines.cost.engine import CostEngine
from acsoe.engines.data_guard.contracts import REASON_NEGATIVE_SPREAD
from acsoe.engines.data_guard.engine import DataGuardEngine
from acsoe.engines.decision.engine import DecisionEngine
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.execution.contracts import (
    REASON_ENTRY_PLACED,
    REASON_ENTRY_RECOVERED,
    userref_for,
)
from acsoe.engines.execution.engine import ExecutionEngine
from acsoe.engines.exit.contracts import (
    REASON_DATA_GUARD_BLOCKED,
    REASON_EXITS_PLACED,
    REASON_NOTHING_TO_EXIT,
    exit_userref_for,
)
from acsoe.engines.exit.engine import ExitEngine
from acsoe.engines.feature.engine import FeatureEngine
from acsoe.engines.macro_context.engine import MacroContextEngine
from acsoe.engines.market_data_recorder.engine import MarketDataRecorderEngine
from acsoe.engines.market_sensor.engine import MarketSensorEngine
from acsoe.engines.memory.engine import MemoryEngine
from acsoe.engines.order_book.engine import OrderBookEngine
from acsoe.engines.position_manager.contracts import HOLD_DATA_GUARD_BLOCKED, position_id_for
from acsoe.engines.position_manager.engine import PositionManagerEngine
from acsoe.engines.prediction.engine import PredictionEngine
from acsoe.engines.regime.engine import RegimeEngine
from acsoe.engines.risk.engine import RiskEngine
from acsoe.engines.safety.engine import SafetyEngine
from acsoe.engines.scout.engine import ScoutEngine
from acsoe.engines.skeptic.engine import SkepticEngine
from acsoe.platform.aio import run_blocking

TIER = tier_sentence(TIER_3)

#: The committed config: `timeframes.decision_bar_s` 900 and `loop_tick_s` 60.
BAR = 900
TICK = 60

#: The universe the market streams. BTC and ETH are also the two macro assets
#: `config/default.yaml` names, which is what lets engine 6 run for real.
PAIRS = ("BTC/USD", "ETH/USD", "SOL/USD")

#: The pair engine 7 chooses. **Asserted on the entry tick, never assumed**: engine 7
#: ranks alphabetically until the operator rules on a ranking feature, and the day that
#: changes, `the_entry` says so by name instead of every test below failing obscurely.
TRADED = "BTC/USD"

#: Where the replayed window ends, in bars before the end of C's constructed series, and
#: how long it is. The same window `test_feature_chain_rehearsal.py` found engine 8
#: calling a BUY on; `the_entry` re-asserts the BUY on every run.
BUY_WINDOW_END = 200
WINDOW_BARS = 300

#: Flat bars planted after the window, so every tick below has a continuous candle
#: series behind it and engine 4 never sees a `missing_candle`. Comfortably longer than
#: `barriers.timeout_bars` (48), which the timeout scenario has to reach.
FLAT_BARS = 80

#: Folds the fixture trains. Fold 0 trains no skeptic (spec 69), so one fold would leave
#: engine 15 unconfigured and the chain would stop there.
FOLDS = 4

#: The committed spread the market is pinned to, above the best bid.
SPREAD = Decimal("0.010")

#: The paper account's opening cash, read from the committed config in `rehearsal_config`
#: and pinned here so a retune is a named failure rather than a silent new baseline.
STARTING_USD = Decimal("5000.00")


#: Every store `build` opened in the running test, closed when the test ends. An open
#: SQLite handle under `tmp_path` is a directory Windows will not delete.
_OPENED: list[StoreClient] = []


@pytest.fixture(autouse=True)
def _close_stores() -> Iterator[None]:
    yield
    while _OPENED:
        _OPENED.pop().close()


# --------------------------------------------------------------------------- #
# The trained subject
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """`(models root, the latest fold's run id)`, trained once for the module.

    The two percentiles are passed to the trainer because the fit records them; they are
    the same values `config/default.yaml` carries, so the engines load a run fitted at
    exactly the committed thresholds.
    """
    from tests.research.test_training import NOW, dataset_for

    from acsoe.research import training

    base = load_default_config()
    fitting = base.as_dict()
    fitting["prediction"]["di_percentile"] = base.get("prediction.di_percentile")
    fitting["anomaly"]["threshold_percentile"] = base.get("anomaly.threshold_percentile")
    root = tmp_path_factory.mktemp("trade-chain-models")
    report = training.train_walkforward(
        dataset_for(base, random_walk=False, macro_archive={"btc": "AAAUSD"}),
        config=MappingConfig(fitting),
        models_dir=root / "models",
        derived_dir=root / "derived",
        now=NOW,
        max_folds=FOLDS,
    )
    run_id = report.fold_runs[-1]
    directory = report.models_dir / run_id
    for artefact in ("di.npz", "anomaly.joblib", "skeptic.txt"):
        assert (directory / artefact).is_file(), f"{artefact} was not fitted; the chain would stop"
    return report.models_dir, run_id


@pytest.fixture(scope="module")
def window() -> list[Bar]:
    """The replayed window, as the bars `ScriptedMarket` plants."""
    from tests.research.test_training import candle_frame

    rows = candle_frame("AAAUSD", interval_s=BAR, random_walk=False, days=140).to_dicts()
    end = len(rows) - BUY_WINDOW_END
    return [
        Bar(
            ts=int(row["ts"]),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
            trades=int(row["trades"]),
        )
        for row in rows[end - WINDOW_BARS : end]
    ]


def rehearsal_config(run_id: str) -> MappingConfig:
    """The committed config with the trained run named, and nothing else changed."""
    data = load_default_config().as_dict()
    for key in ("prediction_run_id", "anomaly_run_id", "skeptic_run_id"):
        data["models"][key] = run_id
    config = MappingConfig(data)
    assert Decimal(str(config.get("paper.starting_balances")["USD"])) == STARTING_USD
    return config


# --------------------------------------------------------------------------- #
# Reading the store back
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Tables:
    """Every row of the four tables engine 19 writes for 18, 21 and 22."""

    orders: dict[int, OrderRow] = field(default_factory=dict)
    positions: dict[str, PositionRow] = field(default_factory=dict)
    trades: dict[str, TradeRow] = field(default_factory=dict)
    equity: tuple[EquitySnapshotRow, ...] = ()


def read_tables(store: StoreClient) -> Tables:
    """The whole of each table, through the store's own typed reads.

    Keys are listed with a plain `SELECT` on the identifier columns — never a money
    column — and every row is then read through the model the store itself returns.
    """
    userrefs = [int(row[0]) for row in store.connection.execute("SELECT userref FROM orders")]
    position_ids = [
        str(row[0]) for row in store.connection.execute("SELECT position_id FROM positions")
    ]
    (trade_count,) = store.connection.execute("SELECT COUNT(*) FROM trades").fetchone()
    trades = {row.trade_id: row for row in store.recent_closed_trades(limit=10_000)}
    assert len(trades) == trade_count
    orders: dict[int, OrderRow] = {}
    for userref in userrefs:
        order = store.order_by_userref(userref)
        assert order is not None
        orders[userref] = order
    positions: dict[str, PositionRow] = {}
    for position_id in position_ids:
        position = store.position(position_id)
        assert position is not None
        positions[position_id] = position
    return Tables(orders=orders, positions=positions, trades=trades, equity=store.equity_series())


def plain(model: Any) -> dict[str, Any]:
    """A row as comparable values, money in its **rendered** form.

    `Decimal` equality ignores the quantum (`code-standards.md`), and a quantity rounded
    to the pair's `lot_decimals` is a claim about form, so money is compared as text.
    """

    def value(item: Any) -> Any:
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, Enum):
            return str(item.value)
        if isinstance(item, tuple):
            return [value(part) for part in item]
        return item

    dumped = model.model_dump()
    dumped.pop("id", None)
    return {key: value(item) for key, item in dumped.items()}


def published(state: dict[str, Any], keys: tuple[str, ...], field_name: str) -> list[Any]:
    """`(publisher, row)` for every row the named engines published, in chain order."""
    rows: list[Any] = []
    for key in keys:
        payload = state.get(key)
        if isinstance(payload, dict):
            rows.extend((key, row) for row in payload.get(field_name, []))
    return rows


def check_recorded(
    state: dict[str, Any], before: Tables, after: Tables, *, run_id: str, ts: int
) -> None:
    """Engine 19 recorded exactly what 18, 21 and 22 published this tick, and nothing else.

    **The expectation is built from the published payload through the store's own row
    model**, stamped with this tick's identifiers — so a column engine 19 dropped, a
    column it set from somewhere else, and an absent field it wrote as something other
    than null all differ. Within a table the publisher order is engine 19's (18, 21, 22
    for orders; 21, 22 for positions): the last publisher's row is the one that survives
    the upsert, and it is the one expected.
    """
    stamp = {"run_id": run_id, "cycle_id": state["cycle_id"], "updated_at": ts}

    if "memory" not in state:
        # A process whose manage chain never ran recorded nothing at all.
        assert after == before, "rows changed on a tick engine 19 did not run"
        return
    assert state["memory"], "engine 19 raised on this tick, so nothing below can be checked"
    assert state["memory"]["cycle_id"] == state["cycle_id"], state["memory"]

    orders: dict[int, OrderRow] = {}
    for _, row in published(state, ("execution", "position_manager", "exit"), "orders"):
        orders[int(row["userref"])] = OrderRow.model_validate({**row, **stamp})
    positions: dict[str, PositionRow] = {}
    for publisher, row in published(state, ("position_manager", "exit"), "positions"):
        hold = state[publisher].get("hold_reason")
        positions[str(row["position_id"])] = PositionRow.model_validate(
            {**row, **stamp, "hold_reason": hold}
        )
    trades = {
        str(row["trade_id"]): TradeRow.model_validate({**row, **stamp})
        for _, row in published(state, ("exit",), "closed_trades")
    }

    for recorded, expected, prior, table in (
        (after.orders, orders, before.orders, "orders"),
        (after.positions, positions, before.positions, "positions"),
        (after.trades, trades, before.trades, "trades"),
    ):
        assert set(recorded) == set(prior) | set(expected), f"{table}: rows appeared or vanished"
        for key, row in expected.items():
            assert plain(recorded[key]) == plain(row), f"{table} {key} is not what was published"
        for key in set(recorded) - set(expected):
            assert plain(recorded[key]) == plain(prior[key]), f"{table} {key} changed unpublished"

    written = state["memory"]["written"]
    assert written["orders"] == len(
        published(state, ("execution", "position_manager", "exit"), "orders")
    )
    assert written["positions"] == len(published(state, ("position_manager", "exit"), "positions"))
    assert written["trades"] == len(trades)

    new = after.equity[len(before.equity) :]
    assert after.equity[: len(before.equity)] == before.equity, "an equity row was rewritten"
    if state["memory"]["equity_skipped_reason"] is not None:
        assert new == (), state["memory"]["equity_skipped_reason"]
        return
    (row,) = new
    manager = state["position_manager"]
    cash = Decimal(state["exchange"]["balances"]["USD"])
    value = Decimal(manager["positions_value"])
    previous = before.equity[-1] if before.equity else None
    realised = sum((trade.realised_pnl for trade in trades.values()), start=Decimal(0))
    assert (row.run_id, row.cycle_id, row.ts) == (run_id, state["cycle_id"], ts)
    assert row.cash == cash
    assert row.positions_value == value
    assert row.unrealised_pnl == Decimal(manager["unrealised_pnl"])
    assert row.equity == cash + value
    assert row.peak_equity == (
        row.equity if previous is None else max(previous.peak_equity, row.equity)
    )
    assert row.realised_pnl_cum == (previous.realised_pnl_cum if previous else 0) + realised
    assert row.open_position_count == sum(
        1 for position in after.positions.values() if position.status.value == "open"
    )


# --------------------------------------------------------------------------- #
# The rehearsal
# --------------------------------------------------------------------------- #


def full_chains() -> Chains:
    """The three runtime chains exactly as spec 82 will register them."""
    return Chains(
        guard=[
            ExchangeEngine(),
            MarketDataRecorderEngine(),
            MarketSensorEngine(),
            DataGuardEngine(),
            SafetyEngine(),
        ],
        opportunity=[
            FeatureEngine(),
            MacroContextEngine(),
            ScoutEngine(),
            RegimeEngine(),
            AnomalyEngine(),
            PredictionEngine(),
            OrderBookEngine(),
            CostEngine(),
            RiskEngine(),
            AdaptiveRouterEngine(),
            SkepticEngine(),
            DecisionEngine(),
            ExecutionEngine(),
        ],
        manage=[PositionManagerEngine(), ExitEngine(), MemoryEngine()],
    )


def killed_chains() -> Chains:
    """A process that died after engine 18 returned and before its manage chain ran."""
    chains = full_chains()
    return Chains(guard=chains.guard, opportunity=chains.opportunity, manage=[])


@dataclass
class Rehearsal:
    """One scripted market, one store, one broker, and the orchestrators ticking them."""

    clock: FixedClock
    market: ScriptedMarket
    store: StoreClient
    broker: PaperBroker
    config: MappingConfig
    bid: Decimal
    last_bar_ts: int
    orchestrator: Orchestrator | None = None
    tables: Tables = field(default_factory=Tables)
    commands: int = 0

    # -- moments ---------------------------------------------------------- #

    def at(self, seconds_after_window: int) -> datetime:
        """An instant counted from the close of the window's last bar."""
        return datetime.fromtimestamp(self.last_bar_ts + BAR + seconds_after_window, tz=UTC)

    @property
    def entry_moment(self) -> datetime:
        """One second into the first bar after the window: the tick on which it closed."""
        return self.at(1)

    # -- the market -------------------------------------------------------- #

    def quote(self, bid: Decimal, ask: Decimal, *, pairs: tuple[str, ...] = PAIRS) -> None:
        """Pin the stream's top of book **and** the REST book to one price.

        Two reads of one market in this design: engine 3 and engine 18 read the stream,
        engine 9 and the broker's post-only check and market-sell walk read the REST book.
        A test that moved one and not the other would be scripting two markets.
        """
        for pair in pairs:
            self.market.set_quote(pair, bid=str(bid), ask=str(ask))
            self.market.set_order_book(pair, bids=[(str(bid), "1000")], asks=[(str(ask), "1000")])

    def trade(self, at: datetime, price: Decimal, pair: str = TRADED) -> None:
        self.market.plant_trade(pair, at=at, price=str(price))

    # -- commands ---------------------------------------------------------- #

    def command(self, name: CommandName) -> None:
        """A command row, the way the console writes one."""
        self.commands += 1
        self.store.append_command(
            CommandRow(
                command=name.value,
                source=CommandSource.CONSOLE,
                reason="trade-chain rehearsal",
                created_at=self.commands,
                updated_at=self.commands,
            )
        )

    # -- ticking ----------------------------------------------------------- #

    def start(self, chains: Chains | None = None) -> Orchestrator:
        """A new process: a fresh orchestrator over the same store and the same broker.

        The broker is kept across a restart on purpose. It stands in for the exchange,
        and an exchange outlives the process that placed an order on it — which is the
        case engine 18's second idempotency probe exists for.
        """
        self.orchestrator = Orchestrator(
            config=self.config,
            clock=self.clock,
            clients=FakeClients(kraken=self.broker, store=self.store, recorder=FakeRecorder()),
            chains=chains or full_chains(),
        )
        return self.orchestrator

    def tick(self, at: datetime, *, check: bool = True) -> dict[str, Any]:
        """One real tick at `at`, then the store read back and checked against it.

        `check=False` defers the read-back to an explicit :meth:`check`, for the one test
        whose property must be asserted first: a read-back that fails because engine 19
        failed would otherwise kill a mutation under the right test's name for a reason
        that is not the property (build log, "M4 was killed by the right test for the
        wrong reason").
        """
        assert self.orchestrator is not None
        self.clock.set(at)
        before = self.tables
        state = self.orchestrator.tick()
        if check:
            self.check(state, before, at)
        return state

    def check(self, state: dict[str, Any], before: Tables, at: datetime) -> None:
        assert self.orchestrator is not None
        self.tables = read_tables(self.store)
        check_recorded(
            state, before, self.tables, run_id=self.orchestrator.run_id, ts=to_micros(at)
        )

    def open_orders(self) -> tuple[Any, ...]:
        return tuple(run_blocking(self.broker.open_orders()))


def build(
    tmp_path: Path,
    trained: tuple[Path, str],
    window: list[Bar],
    *,
    chains: Chains | None = None,
    warm_up: bool = True,
) -> Rehearsal:
    """The market planted, the account opened, the system activated, one quiet tick run.

    The warm-up tick is what writes the first equity row. Engine 11 sizes against total
    account equity, which only engine 19 computes and which it writes at the end of a
    tick — so without one quiet tick first, the entry tick would be refused by engine 11
    for want of an equity figure, correctly.
    """
    root, run_id = trained
    last_bar_ts = window[-1].ts
    clock = FixedClock(datetime.fromtimestamp(last_bar_ts, tz=UTC))
    market = ScriptedMarket(clock=clock, interval_s=BAR, published_bars=200, pairs=PAIRS)
    profile = market.use_fee_tier(TIER_3)
    assert profile.tier == TIER_3

    bid = window[-1].close.quantize(Decimal("0.001"))
    flat = [
        Bar.flat(last_bar_ts + BAR * k, str(bid), trades=17 + (k * 7) % 23)
        for k in range(1, FLAT_BARS + 1)
    ]
    for pair in PAIRS:
        market.plant(pair, window)
        market.plant(pair, flat)

    db = tmp_path / "acsoe.sqlite"
    apply_migrations(db)
    store = StoreClient(db, models_dir=root)
    _OPENED.append(store)
    config = rehearsal_config(run_id)
    rehearsal = Rehearsal(
        clock=clock,
        market=market,
        store=store,
        broker=PaperBroker(market, store=store, config=config, clock=clock),
        config=config,
        bid=bid,
        last_bar_ts=last_bar_ts,
    )
    rehearsal.quote(bid, bid + SPREAD)
    rehearsal.command(CommandName.ACTIVATE)
    rehearsal.start(chains)
    if warm_up:
        warm = rehearsal.tick(rehearsal.at(1 - TICK))
        assert warm["market_sensor"]["bar_closed"] is False
        assert warm["guard_blockers"] == [], warm["guard_blockers"]
        assert warm["memory"]["equity"] == str(STARTING_USD)
    return rehearsal


# --------------------------------------------------------------------------- #
# The shared steps: an entry, and its fill
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Entry:
    """What the entry tick produced, recomputed from its sources where it can be."""

    userref: int
    qty: Decimal
    limit: Decimal
    placed_at: int


def limit_for(bid: Decimal, pair_rules: dict[str, Any]) -> Decimal:
    """The best bid rounded **down** onto the pair's price grid, computed here."""
    grid = Decimal(1).scaleb(-int(pair_rules["pair_decimals"]))
    return bid.quantize(grid, rounding=ROUND_DOWN)


def the_entry(rehearsal: Rehearsal) -> tuple[Entry, dict[str, Any]]:
    """Tick at the bar close: the whole chain approves and engine 18 places one entry."""
    state = rehearsal.tick(rehearsal.entry_moment)
    assert "trading_blocked_by" not in state, (state.get("block_reason"), TIER)
    assert state["exchange"]["fee_tier"]["tier"] == TIER_3, TIER
    assert state["market_sensor"]["bar_closed"] is True
    assert state["scout"]["pair"] == TRADED, "engine 7 chose another pair; see TRADED"
    assert state["prediction"]["is_buy"] is True, "the BUY window no longer calls a BUY"
    assert state["cost"]["clears_hurdle"] is True, TIER
    assert state["decision"]["coherent"] is True

    execution = state["execution"]
    intent = state["decision"]["intent"]
    userref = userref_for(TRADED, int(state["market_sensor"]["closed_bar_ts"]))
    limit = limit_for(rehearsal.bid, state["exchange"]["pair_rules"]["pairs"][TRADED])
    assert execution["reason_code"] == REASON_ENTRY_PLACED, (execution, TIER)
    assert execution["placed"] is True
    assert execution["userref"] == userref
    (row,) = execution["orders"]
    assert row["qty"] == intent["qty"] == state["risk"]["qty"], "the quantity is engine 11's"
    assert row["limit_price"] == str(limit)
    assert (row["status"], row["intent"], row["order_type"], row["oflags"]) == (
        "resting",
        "entry",
        "limit",
        "post",
    )

    # Engine 21 saw the entry on the same tick, before engine 19 recorded it, and so did
    # not report every entry cancelled with one on the book.
    assert state["position_manager"]["entry_orders_cancelled"] is False
    assert state["position_manager"]["orders"] == []
    assert state["exit"]["reason_code"] == REASON_NOTHING_TO_EXIT
    assert rehearsal.tables.orders[userref].status.value == "resting"
    assert [order.userref for order in rehearsal.open_orders()] == [userref]
    return (
        Entry(
            userref=userref,
            qty=Decimal(row["qty"]),
            limit=limit,
            placed_at=to_micros(rehearsal.entry_moment),
        ),
        state,
    )


@dataclass(frozen=True)
class Filled:
    """The position a fill opened, with its barriers recomputed from the config."""

    position_id: str
    entry_fee: Decimal
    stop: Decimal
    target: Decimal
    timeout_at: int
    opened_at: int


def the_fill(rehearsal: Rehearsal, entry: Entry) -> tuple[Filled, dict[str, Any]]:
    """A trade strictly below the limit, then the next tick: engine 21 records the fill."""
    rehearsal.trade(rehearsal.entry_moment + timedelta(seconds=30), entry.limit - Decimal("0.1"))
    moment = rehearsal.entry_moment + timedelta(seconds=TICK)
    state = rehearsal.tick(moment)

    assert "trading_blocked_by" not in state, state.get("block_reason")
    assert "execution" not in state, "engine 18 ran on a tick where no bar closed"
    manager = state["position_manager"]
    maker = Decimal(fee_tier_profile(TIER_3).maker_fee_pct)
    config = rehearsal.config
    stop_pct = Decimal(str(config.get("barriers.stop_pct")))
    target_pct = Decimal(str(config.get("barriers.target_pct")))
    timeout_s = int(config.get("barriers.timeout_bars")) * int(
        config.get("timeframes.decision_bar_s")
    )
    filled = Filled(
        position_id=position_id_for(entry.userref),
        entry_fee=entry.qty * entry.limit * maker,
        # Barriers from the fill price, which in paper mode is the limit: a resting
        # maker buy fills at its own price (spec 88).
        stop=entry.limit * (Decimal(1) - stop_pct),
        target=entry.limit * (Decimal(1) + target_pct),
        timeout_at=to_micros(moment) + timeout_s * 1_000_000,
        opened_at=to_micros(moment),
    )

    (order,) = manager["orders"]
    assert (order["userref"], order["status"]) == (entry.userref, "filled")
    assert Decimal(order["avg_fill_price"]) == entry.limit
    assert Decimal(order["filled_qty"]) == entry.qty
    assert Decimal(order["fee"]) == filled.entry_fee, f"maker fee {TIER}"
    (position,) = manager["positions"]
    assert position["position_id"] == filled.position_id
    assert (position["status"], position["pair"]) == ("open", TRADED)
    assert Decimal(position["stop_price"]) == filled.stop
    assert Decimal(position["target_price"]) == filled.target
    assert position["timeout_at"] == filled.timeout_at
    assert manager["triggered"] == []
    assert manager["hold_reason"] is None
    assert manager["entry_orders_cancelled"] is True
    assert state["exit"]["reason_code"] == REASON_NOTHING_TO_EXIT
    assert rehearsal.tables.positions[filled.position_id].status.value == "open"
    assert rehearsal.open_orders() == ()
    return filled, state


def exit_trade(
    state: dict[str, Any], entry: Entry, filled: Filled, *, exit_price: Decimal, outcome: str
) -> None:
    """Engine 22 sold the whole position at `exit_price`, and the round trip is exact.

    Every money figure is recomputed from the tier-3 profile and the prices the market
    was scripted with — never read back from the payload it is checked against.
    """
    taker = Decimal(fee_tier_profile(TIER_3).taker_fee_pct)
    exit_fee = entry.qty * exit_price * taker
    realised = entry.qty * exit_price - entry.qty * entry.limit - filled.entry_fee - exit_fee
    userref = exit_userref_for(filled.position_id)

    exiting = state["exit"]
    assert exiting["reason_code"] == REASON_EXITS_PLACED, (exiting["reason_code"], TIER)
    assert exiting["positions_closed"] is True
    (order,) = exiting["orders"]
    assert (order["userref"], order["side"], order["order_type"], order["status"]) == (
        userref,
        "sell",
        "market",
        "filled",
    )
    assert Decimal(order["qty"]) == entry.qty
    assert Decimal(order["avg_fill_price"]) == exit_price
    (position,) = exiting["positions"]
    assert (position["position_id"], position["status"]) == (filled.position_id, "closed")
    (trade,) = exiting["closed_trades"]
    assert trade["outcome"] == outcome
    assert Decimal(trade["exit_price"]) == exit_price
    assert Decimal(trade["entry_fee"]) == filled.entry_fee
    assert Decimal(trade["exit_fee"]) == exit_fee, f"taker fee {TIER}"
    assert Decimal(trade["realised_pnl"]) == realised, TIER
    assert trade["fallbacks_used"] == []


# --------------------------------------------------------------------------- #
# 1. Entry placed, entry filled, stop touched and exited
# --------------------------------------------------------------------------- #


def test_an_entry_is_placed_filled_on_a_later_tick_and_stopped_out(
    tmp_path: Path, trained: tuple[Path, str], window: list[Bar]
) -> None:
    """Three ticks after the warm-up, each a separate `tick()` on one orchestrator.

    The stop is touched **between** the fill tick and the next, by a trade engine 3
    folds into that tick's range. The quote and the book move with it, so engine 22
    sells into the market the stop was touched in rather than the one before.
    """
    rehearsal = build(tmp_path, trained, window)
    entry, _ = the_entry(rehearsal)
    filled, _ = the_fill(rehearsal, entry)

    touched = filled.opened_at // 1_000_000 + 30
    exit_bid = (filled.stop - Decimal("0.6")).quantize(Decimal("0.001"))
    rehearsal.trade(datetime.fromtimestamp(touched, tz=UTC), filled.stop - Decimal("0.5"))
    rehearsal.quote(exit_bid, exit_bid + SPREAD)
    state = rehearsal.tick(datetime.fromtimestamp(filled.opened_at // 1_000_000 + TICK, tz=UTC))

    assert "trading_blocked_by" not in state, state.get("block_reason")
    manager = state["position_manager"]
    assert manager["hold_reason"] is None
    assert manager["triggered"] == [{"position_id": filled.position_id, "barrier": "stop"}]
    exit_trade(state, entry, filled, exit_price=exit_bid, outcome="stop")
    recorded = rehearsal.tables
    assert recorded.positions[filled.position_id].status.value == "closed"
    assert recorded.trades[f"trade-{filled.position_id}"].outcome.value == "stop"
    assert set(recorded.orders) == {entry.userref, exit_userref_for(filled.position_id)}
    assert rehearsal.orchestrator is not None
    assert rehearsal.orchestrator.system == {"mode": "running", "close_intent": False}


# --------------------------------------------------------------------------- #
# 2. Timeout reached and exited
# --------------------------------------------------------------------------- #


def test_a_position_that_reaches_its_timeout_is_exited_on_that_tick(
    tmp_path: Path, trained: tuple[Path, str], window: list[Bar]
) -> None:
    """No barrier is touched; the clock reaches `timeout_at` and engine 22 sells.

    The tick lands on `timeout_at` itself, 48 bars after the fill, in one step. That is
    a loop overshoot, which `context.previous_now` exists to make safe: the trade range
    engine 3 publishes spans the whole twelve hours of flat trading, and none of it is
    near either price barrier, so the timeout is the only thing that can fire.
    """
    rehearsal = build(tmp_path, trained, window)
    entry, _ = the_entry(rehearsal)
    filled, _ = the_fill(rehearsal, entry)

    moment = datetime.fromtimestamp(filled.timeout_at // 1_000_000, tz=UTC)
    state = rehearsal.tick(moment)

    assert state["market_sensor"]["bar_closed"] is False
    assert "trading_blocked_by" not in state, state.get("block_reason")
    traded = state["market_sensor"]["trade_ranges"][TRADED]
    assert filled.stop < Decimal(traded["low"]) <= Decimal(traded["high"]) < filled.target
    manager = state["position_manager"]
    assert manager["triggered"] == [{"position_id": filled.position_id, "barrier": "timeout"}]
    exit_trade(state, entry, filled, exit_price=rehearsal.bid, outcome="timeout")
    assert rehearsal.tables.positions[filled.position_id].closed_at == to_micros(moment)


# --------------------------------------------------------------------------- #
# 3. An unfilled entry, cancelled at its window and not replaced
# --------------------------------------------------------------------------- #


def test_an_unfilled_entry_is_cancelled_at_its_window_and_not_replaced(
    tmp_path: Path, trained: tuple[Path, str], window: list[Bar]
) -> None:
    """Nothing trades below the limit. One tick a minute, and the cancel lands at 300s.

    "Not replaced" is asserted where a replacement would have to exist: at the broker,
    which is the exchange in this design. A replacement placed by engine 21 would never
    reach `state` or the store — engine 21 publishes no placement — so a check of the
    tables alone could not see one.
    """
    rehearsal = build(tmp_path, trained, window)
    entry, _ = the_entry(rehearsal)
    window_s = int(rehearsal.config.get("trading.entry_unfilled_window_s"))
    assert window_s % TICK == 0, "the scenario ticks once a minute onto the window"

    for elapsed in range(TICK, window_s, TICK):
        state = rehearsal.tick(rehearsal.entry_moment + timedelta(seconds=elapsed))
        assert "trading_blocked_by" not in state, state.get("block_reason")
        assert "execution" not in state
        manager = state["position_manager"]
        assert manager["orders"] == [], f"cancelled {elapsed}s in, before its window"
        assert manager["entry_orders_cancelled"] is False
        assert rehearsal.tables.orders[entry.userref].status.value == "resting"
        assert [order.userref for order in rehearsal.open_orders()] == [entry.userref]

    moment = rehearsal.entry_moment + timedelta(seconds=window_s)
    state = rehearsal.tick(moment)
    assert "trading_blocked_by" not in state, state.get("block_reason")
    manager = state["position_manager"]
    (cancel,) = manager["orders"]
    assert (cancel["userref"], cancel["status"]) == (entry.userref, "cancelled")
    assert manager["entry_orders_cancelled"] is True
    assert manager["positions"] == []
    recorded = rehearsal.tables.orders[entry.userref]
    assert (recorded.status.value, recorded.closed_at) == ("cancelled", to_micros(moment))
    assert rehearsal.open_orders() == (), "the cancelled entry was replaced at the exchange"

    later = rehearsal.tick(moment + timedelta(seconds=TICK))
    assert "execution" not in later
    assert later["position_manager"]["orders"] == []
    assert later["position_manager"]["entry_orders_cancelled"] is True
    assert set(rehearsal.tables.orders) == {entry.userref}
    assert rehearsal.open_orders() == (), "an entry appeared after the cancel"


# --------------------------------------------------------------------------- #
# 4. A data_guard block holds a triggered stop; close_intent then exits it
# --------------------------------------------------------------------------- #


def test_a_data_guard_block_holds_a_touched_stop_and_close_intent_then_exits_it(
    tmp_path: Path, trained: tuple[Path, str], window: list[Bar]
) -> None:
    """The stop is touched on a tick whose book is crossed, so engine 4 blocks.

    Tick A: engines 21 and 22 place nothing, `hold_reason` is recorded on the position,
    and the touch is visible in engine 3's range — so this is a stop that *was* touched
    and was held, not a tick on which nothing happened. Tick B: the book is still crossed
    and the operator presses Close all; the same position is liquidated regardless of the
    guard, and the orchestrator clears `close_intent` because both flags came back true.

    Before spec 103, engine 17 also blocked on tick B, as a second guard blocker, because
    of finding 1 in the module docstring. Nothing here asserts on engine 17 either way.
    `data_guard` is the primary blocker, and the primary blocker is the only thing the hold
    reads.
    """
    rehearsal = build(tmp_path, trained, window)
    entry, _ = the_entry(rehearsal)
    filled, _ = the_fill(rehearsal, entry)
    opened_s = filled.opened_at // 1_000_000

    crossed = (filled.stop - Decimal("0.4")).quantize(Decimal("0.001"))
    liquidation_bid = (filled.stop - Decimal("0.7")).quantize(Decimal("0.001"))
    rehearsal.trade(datetime.fromtimestamp(opened_s + 30, tz=UTC), filled.stop - Decimal("0.5"))
    rehearsal.market.set_quote(TRADED, bid=str(crossed), ask=str(crossed - SPREAD))
    rehearsal.market.set_order_book(
        TRADED,
        bids=[(str(liquidation_bid), "1000")],
        asks=[(str(liquidation_bid + SPREAD), "1000")],
    )
    held = rehearsal.tick(datetime.fromtimestamp(opened_s + TICK, tz=UTC))

    assert held["trading_blocked_by"] == "data_guard", held.get("block_reason")
    assert held["data_guard"]["reason_code"] == REASON_NEGATIVE_SPREAD
    assert Decimal(held["market_sensor"]["trade_ranges"][TRADED]["low"]) <= filled.stop, (
        "no stop was touched, so there was nothing to hold"
    )
    manager = held["position_manager"]
    assert manager["hold_reason"] == HOLD_DATA_GUARD_BLOCKED
    assert manager["triggered"] == []
    assert manager["reason_code"] is None, "engine 21 failed rather than held"
    assert [row["position_id"] for row in manager["positions"]] == [filled.position_id]
    assert held["exit"]["reason_code"] == REASON_DATA_GUARD_BLOCKED
    assert held["exit"]["orders"] == []
    assert held["exit"]["positions_closed"] is False
    position = rehearsal.tables.positions[filled.position_id]
    assert (position.status.value, position.hold_reason) == ("open", HOLD_DATA_GUARD_BLOCKED)
    assert exit_userref_for(filled.position_id) not in rehearsal.tables.orders
    assert held["system"]["close_intent"] is False

    rehearsal.command(CommandName.CLOSE_ALL)
    liquidated = rehearsal.tick(datetime.fromtimestamp(opened_s + 2 * TICK, tz=UTC))

    assert liquidated["trading_blocked_by"] == "data_guard", "the guard must still be blocking"
    assert liquidated["guard_blockers"][0]["engine"] == "data_guard"
    manager = liquidated["position_manager"]
    assert manager["hold_reason"] is None, "a liquidation never holds"
    assert manager["entry_orders_cancelled"] is True
    exit_trade(liquidated, entry, filled, exit_price=liquidation_bid, outcome="liquidation")
    recorded = rehearsal.tables.positions[filled.position_id]
    assert (recorded.status.value, recorded.hold_reason) == ("closed", None)
    assert rehearsal.orchestrator is not None
    assert rehearsal.orchestrator.system == {"mode": "frozen", "close_intent": False}
    assert rehearsal.store.pending_commands() == ()
    assert rehearsal.store.claimed_unconsumed_commands() == ()


# --------------------------------------------------------------------------- #
# 5. A block by any other engine does not hold
# --------------------------------------------------------------------------- #


def test_a_block_by_any_other_engine_does_not_hold_a_touched_stop(
    tmp_path: Path, trained: tuple[Path, str], window: list[Bar]
) -> None:
    """Engine 17 blocks the tick the stop is touched on, and the stop is still taken.

    The block is engine 17's real drawdown breaker reading a real row. The row is a
    snapshot written into the store between the fill tick and this one, standing in for
    an account whose recorded history puts it 60% below its peak: engine 17 reads only
    the store, so this is the one input it has, and nothing in `state` is touched.
    Written this way rather than borrowed from finding 1 in the module docstring, so the
    scenario kept its witness once spec 103 fixed that defect.
    """
    rehearsal = build(tmp_path, trained, window)
    entry, _ = the_entry(rehearsal)
    filled, _ = the_fill(rehearsal, entry)
    opened_s = filled.opened_at // 1_000_000

    rehearsal.store.write_equity_snapshot(
        EquitySnapshotRow(
            cycle_id=1,
            run_id="an-account-history",
            ts=filled.opened_at + 1,
            currency="USD",
            equity=Decimal("4000.00"),
            peak_equity=Decimal("10000.00"),
            cash=Decimal("4000.00"),
            positions_value=Decimal("0"),
            unrealised_pnl=Decimal("0"),
            realised_pnl_cum=Decimal("0"),
            open_position_count=0,
            updated_at=filled.opened_at + 1,
        )
    )
    rehearsal.tables = read_tables(rehearsal.store)
    exit_bid = (filled.stop - Decimal("0.6")).quantize(Decimal("0.001"))
    rehearsal.trade(datetime.fromtimestamp(opened_s + 30, tz=UTC), filled.stop - Decimal("0.5"))
    rehearsal.quote(exit_bid, exit_bid + SPREAD)
    state = rehearsal.tick(datetime.fromtimestamp(opened_s + TICK, tz=UTC))

    assert state["trading_blocked_by"] == "safety", state.get("block_reason")
    assert [blocker["engine"] for blocker in state["guard_blockers"]] == ["safety"]
    assert "drawdown" in state["safety"]["tripped"], state["safety"]
    manager = state["position_manager"]
    assert manager["hold_reason"] is None, "engine 21 held on a block that was not data_guard"
    assert manager["triggered"] == [{"position_id": filled.position_id, "barrier": "stop"}]
    exit_trade(state, entry, filled, exit_price=exit_bid, outcome="stop")


# --------------------------------------------------------------------------- #
# 6. The same bar evaluated twice places one entry
# --------------------------------------------------------------------------- #


def test_a_restarted_process_does_not_place_the_same_entry_twice(
    tmp_path: Path, trained: tuple[Path, str], window: list[Bar]
) -> None:
    """Invariant 8, through engine 18's second probe: the order is at the exchange only.

    The first process places the entry and dies before its manage chain runs, so engine
    19 never records it — the case `open_orders()` is engine 18's probe for. The second
    process starts within the same bar's first minute, so the same bar closes again for
    it, engine 11 sees no resting entry in the store and approves, and engine 18 is asked
    for the same `userref` a second time.

    The equity row engine 11 sizes against is written here rather than by a warm-up
    tick, because the first process has no engine 19 to write one.
    """
    rehearsal = build(tmp_path, trained, window, chains=killed_chains(), warm_up=False)
    rehearsal.store.write_equity_snapshot(
        EquitySnapshotRow(
            cycle_id=1,
            run_id="an-account-history",
            ts=to_micros(rehearsal.at(-BAR)),
            currency="USD",
            equity=STARTING_USD,
            peak_equity=STARTING_USD,
            cash=STARTING_USD,
            positions_value=Decimal("0"),
            unrealised_pnl=Decimal("0"),
            realised_pnl_cum=Decimal("0"),
            open_position_count=0,
            updated_at=to_micros(rehearsal.at(-BAR)),
        )
    )
    rehearsal.tables = read_tables(rehearsal.store)
    first = rehearsal.tick(rehearsal.entry_moment)
    assert first["execution"]["reason_code"] == REASON_ENTRY_PLACED, (
        first.get("block_reason"),
        TIER,
    )
    userref = first["execution"]["userref"]
    assert rehearsal.tables.orders == {}, "the process died before engine 19 recorded it"

    rehearsal.command(CommandName.ACTIVATE)
    rehearsal.start()
    restart = rehearsal.at(TICK // 2)
    before = rehearsal.tables
    second = rehearsal.tick(restart, check=False)

    # The property, before anything is read back: a second placement under one
    # `userref` is refused by the broker, which makes engine 18 raise and block.
    assert "trading_blocked_by" not in second, (second.get("block_reason"), TIER)
    assert second["market_sensor"]["closed_bar_ts"] == first["market_sensor"]["closed_bar_ts"]
    execution = second["execution"]
    assert execution["userref"] == userref
    assert execution["placed"] is False
    assert execution["reason_code"] == REASON_ENTRY_RECOVERED
    assert [order.userref for order in rehearsal.open_orders()] == [userref]
    rehearsal.check(second, before, restart)
    recorded = rehearsal.tables.orders
    assert set(recorded) == {userref}
    assert recorded[userref].placed_at == to_micros(rehearsal.entry_moment)
    assert second["position_manager"]["entry_orders_cancelled"] is False


# --------------------------------------------------------------------------- #
# 7. A position watched across quiet ticks — the scenario finding 1 broke
# --------------------------------------------------------------------------- #


def test_a_filled_position_is_watched_across_quiet_ticks(
    tmp_path: Path, trained: tuple[Path, str], window: list[Bar]
) -> None:
    """The fill, then three quiet ticks: marked at the bid, nothing triggered, no block.

    The fill tick's equity is recomputed from the account rather than from engine 1's
    payload: the opening cash, less what the entry spent and its maker fee, plus the
    position at what was paid.

    History: this was a strict `xfail` for finding 1 (spec 87, build log 2026-09-16), and
    that equity assertion is the one it failed. Engine 19 wrote `8332.414226591`, which is
    the pre-fill cash of `5000.00` plus the position, and engine 17 then froze the account.
    Spec 103 fixed the broker's ledger, and the marker was removed once the test passed.
    """
    rehearsal = build(tmp_path, trained, window)
    entry, _ = the_entry(rehearsal)
    filled, fill_tick = the_fill(rehearsal, entry)

    cash_after_fill = STARTING_USD - entry.qty * entry.limit - filled.entry_fee
    assert Decimal(fill_tick["memory"]["equity"]) == cash_after_fill + entry.qty * entry.limit, (
        "the fill tick's equity counts the entry's notional twice"
    )

    for minute in (1, 2, 3):
        state = rehearsal.tick(
            datetime.fromtimestamp(filled.opened_at // 1_000_000 + minute * TICK, tz=UTC)
        )
        assert "trading_blocked_by" not in state, state.get("block_reason")
        manager = state["position_manager"]
        assert manager["triggered"] == []
        (position,) = manager["positions"]
        assert position["last_price"] == str(rehearsal.bid)
        assert Decimal(manager["positions_value"]) == entry.qty * rehearsal.bid
        assert Decimal(state["exchange"]["balances"]["USD"]) == cash_after_fill
        assert state["exit"]["reason_code"] == REASON_NOTHING_TO_EXIT
