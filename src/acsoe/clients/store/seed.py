"""The seeded database.

Phase 1's console renders this. **Phase 3 tests engine 17 `safety` against it**, because
every one of `safety`'s six inputs is written by engine 19 `memory`, which is Phase 4 —
a gate that needed a later phase's deliverable could never go green. This file is that
resolution, so it is a deliverable and not decoration.

The six things Phase 3 reads are produced as *named fixtures*, returned in
:class:`SeedFixtures`, not left to be rediscovered by query:

1. a run of consecutive `data_guard` ticks longer than the block limit, spanning two
   `run_id`s;
2. at least one open position;
3. at least one resting entry order;
4. an equity series whose **latest** row is in drawdown past the limit;
5. a trailing run of losing closed trades past the loss-streak limit;
6. `block_records` rows with `status = 'ERROR'` inside the error-rate window.

Every fixture in :class:`SeedFixtures` is **derived by reading the rows back**, never
from the loop counter that wrote them. Those two numbers are equal only when there is no
bug, which is the entire reason for reading them back.

**The two runs deliberately overlap in `cycle_id`, and that overlap is load-bearing.**
`cycle_id` restarts at 1 with each process, so `run_b`'s cycles land back down in
`run_a`'s opening minutes, and `block_records` carries rows on both sides of the
collision — `(run_a, 4)` and `(run_b, 4)` are different ticks hours apart. Two separate
bugs survive a database without that overlap: a counter that orders by `cycle_id`
instead of `ts` reads the outage backwards, and one that groups ticks by `cycle_id`
alone merges two runs into one. The seed exists to fail both, and
`SeedFixtures.cycle_ids_shared_across_runs` names the values that do it. Do not tidy the
run IDs apart, and do not renumber the opening ticks. It would silently disarm the test.

**Nothing here is real.** No live mode, no key, no real balance, no real fee. Every
number is fabricated for a fixture. In particular the fee fractions below are **not a fee
schedule and not a tier** — invariant 2 says fees come from `POST /0/private/TradeVolume`
at runtime and appear nowhere as a constant. No code may read these; they exist only so a
fabricated trade has a plausible PnL, and they are named to make that unmistakable.

**No unconsumed command row is ever seeded.** The orchestrator re-applies claimed but
unconsumed commands at startup and acts on pending ones at the top of the first tick, so
a seeded pending `activate` would start a daemon trading and a seeded unconsumed
`close_all` would liquidate on boot. Every seeded command is fully consumed.

**Nothing here reads a clock.** The database's "now" is :data:`SEED_ANCHOR_TS`, exposed
as `SeedFixtures.seed_now`; a Phase 3 test sets `context.now` from it.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Final

from acsoe.clients.store.client import DATA_GUARD_ENGINE, StoreClient
from acsoe.clients.store.contracts import (
    BlockRecordRow,
    BlockStatus,
    CashSource,
    CommandName,
    CommandRow,
    CommandSource,
    EquitySnapshotRow,
    LeaderboardRow,
    OrderIntent,
    OrderRow,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionRow,
    PositionStatus,
    RejectionRow,
    RunMode,
    RunRow,
    TradeOutcome,
    TradeRow,
    to_micros,
)

# ---------------------------------------------------------------------------
# Fixture-shape constants.
#
# These describe the SHAPE of the fixture, not a recommended limit and not a value
# anyone should copy into config. The three breaker limits the operator has not yet set
# are `null` in `config/default.yaml` on purpose; the numbers below exist only so that
# `seed_database()` can run with no config at all, and every fixture is generated as a
# multiple of whatever threshold is actually injected.
# ---------------------------------------------------------------------------

#: `seeds.seed_generator` in `config/default.yaml`.
DEFAULT_SEED: Final = 20260908

#: The database's "now". Fixed, because the seed reads no clock and two seedings of the
#: same seed must be identical.
SEED_ANCHOR: Final = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)
SEED_ANCHOR_TS: Final = to_micros(SEED_ANCHOR)

MICROS_PER_MINUTE: Final = 60 * 1_000_000

#: Loop ticks per decision bar — 15 one-minute ticks, from `architecture-context.md`.
#: Candidates are born only when a bar closes, so rejections land on these ticks and
#: block records stay off them.
DECISION_BAR_TICKS: Final = 15

#: How many opening ticks are held clear of trading activity so the `cycle_id`
#: collision between the two runs has somewhere to live. Fewer than one decision bar,
#: and well below the first trade close, so nothing else has to move to accommodate it.
RESERVED_TICKS: Final = DECISION_BAR_TICKS // 2

#: Specified in `config/default.yaml`, not invented here: one full decision bar.
FIXTURE_SHAPE_BLOCK_LIMIT: Final = 15
#: Specified in `config/default.yaml`: `architecture-context.md`'s "trailing hour".
FIXTURE_SHAPE_ERROR_WINDOW_S: Final = 3600
#: OPERATOR REQUIRED in config. Fixture shape only. Not a recommendation.
FIXTURE_SHAPE_DRAWDOWN_LIMIT: Final = Decimal("0.10")
#: OPERATOR REQUIRED in config. Fixture shape only. Not a recommendation.
FIXTURE_SHAPE_LOSS_STREAK_LIMIT: Final = 5
#: OPERATOR REQUIRED in config. Fixture shape only. Not a recommendation.
FIXTURE_SHAPE_ERROR_LIMIT: Final = 10
#: `trading.base_reporting_currency` is OPERATOR REQUIRED. Fixture shape only.
FIXTURE_SHAPE_REPORTING_CURRENCY: Final = "USD"
#: A fictional starting equity. Never a real balance.
FIXTURE_SHAPE_STARTING_EQUITY: Final = Decimal("1000.00")

#: **Not a fee schedule and not a Kraken tier.** A fabricated round-trip friction band,
#: used only so a fabricated trade has a plausible PnL. Real fees come from
#: `POST /0/private/TradeVolume` at runtime — invariant 2 — and no code reads this.
_FABRICATED_FEE_FRACTION: Final = (Decimal("0.0020"), Decimal("0.0055"))

CENT: Final = Decimal("0.01")
LOT: Final = Decimal("0.00000001")
PCT: Final = Decimal("0.000001")

#: Guard-chain execution order. `is_primary` goes to whichever blocker on a tick ran
#: first, which is what "the first one" means in invariant 12.
GUARD_CHAIN_ORDER: Final[tuple[str, ...]] = (
    "exchange",
    "market_data_recorder",
    "market_sensor",
    DATA_GUARD_ENGINE,
    "safety",
)

#: Engines that can plausibly raise an ERROR rather than a clean BLOCK.
_ERROR_ENGINES: Final[tuple[str, ...]] = (
    "exchange",
    "market_data_recorder",
    "market_sensor",
)

#: Fabricated pairs and reference prices. Pair names are not exchange metadata in the
#: sense of invariant 2 — no minimum, tick size or precision is asserted here.
_PAIRS: Final[tuple[tuple[str, str, str, Decimal], ...]] = (
    ("XBT/USD", "XBT", "USD", Decimal("61250.00")),
    ("ETH/USD", "ETH", "USD", Decimal("2480.00")),
    ("SOL/USD", "SOL", "USD", Decimal("148.20")),
    ("ADA/USD", "ADA", "USD", Decimal("0.4120")),
    ("DOT/USD", "DOT", "USD", Decimal("5.6400")),
    ("LINK/USD", "LINK", "USD", Decimal("11.8300")),
    ("AVAX/USD", "AVAX", "USD", Decimal("27.9500")),
    ("ATOM/USD", "ATOM", "USD", Decimal("4.7300")),
    ("XRP/USD", "XRP", "USD", Decimal("0.5840")),
    ("LTC/USD", "LTC", "USD", Decimal("68.4000")),
)

#: Rejection reasons written for the operator, not for the log — the console renders
#: them verbatim. `ui-context.md` requires a proper minus sign (U+2212) in numeric
#: output, so the stored text already carries one and the console needs no rewriting.
#:
#: **Every code here is one the named engine declares in its own `contracts.py`, and two
#: tests in `tests/clients/store/test_seed.py` walk from these rows back to the engines to
#: keep it that way.** Until spec 119 none of that was true: this list was written in
#: Phase 0, before any engine existed, so plausible codes were invented — correct at the
#: time — and nothing compared the two afterwards. The console hid it, because
#: `operator_reason` prefers the sentence stored beside the code and only consults
#: `REASON_PROSE` when there is none, so **the feed never needed the codes to be real**.
#: Adding a row means picking its code out of the engine's module, never composing one
#: that reads well: a rejection is research data about a refusal the system can make.
#:
#: **Engines 7 `scout` and 9 `order_book` are deliberately absent.** Neither can be a
#: `rejected_by` in the live chain, so a row naming one describes a refusal that cannot
#: happen. Engine 9 never returns `BLOCK` at all: a book too thin to walk leaves
#: `estimated_slippage_pct` unpublished and engine 10 `cost` refuses on the absence,
#: which is the `cost_inputs_unavailable` row below. Engine 7 does block, but only with
#: `empty_universe`, which it publishes exactly when there is **no** candidate — and
#: engine 19 writes no rejection without a candidate pair. Its exclusion codes are a
#: per-pair tally over the universe, not a refusal of a candidate.
_REJECTION_REASONS: Final[tuple[tuple[str, str, str], ...]] = (
    # ruff RUF001 flags U+2212 as an ambiguous character. It is the point: number
    # rule 6 of `ui-context.md` requires a proper minus sign in numeric output, not a
    # hyphen, because hyphens break tabular alignment. The console renders `reason`
    # verbatim, so the correct glyph is stored rather than substituted at render time.
    ("cost", "net_edge_below_hurdle", "Net edge −0.21% after fees"),  # noqa: RUF001
    ("cost", "net_edge_below_hurdle", "Net edge −0.08% after fees"),  # noqa: RUF001
    ("cost", "spread_wider_than_move", "Spread 0.42% is wider than the expected move"),
    # Engine 10 refusing on an input it never received — the shape engine 9 produces when
    # the bid side cannot absorb the basis notional within the fetched depth. Operator
    # ruling of 2026-09-16: the refusal belongs to the gate, not to the engine that
    # declined to guess.
    (
        "cost",
        "cost_inputs_unavailable",
        "No slippage estimate: the book was too thin to price the exit",
    ),
    ("risk", "below_ordermin", "Position would be below the pair's minimum order size"),
    ("risk", "below_costmin", "Position value below the pair's minimum order value"),
    ("risk", "insufficient_quote_balance", "Not enough USD held to open this position"),
    ("risk", "max_concurrent_positions", "Already holding the maximum number of positions"),
    ("risk", "position_open_on_pair", "This pair already holds an open position"),
    # One veto code, two sentences: engine 15 distinguishes nothing finer than a veto, and
    # the variety the feed needs lives in the prose, exactly as it does for the two
    # `net_edge_below_hurdle` rows above.
    ("skeptic", "skeptic_veto", "Skeptic vetoed: similar setups lost 4 of the last 5 times"),
    ("skeptic", "skeptic_veto", "Skeptic vetoed: entry timing looks like adverse selection"),
    ("anomaly", "market_anomalous", "Market state is an outlier on volume and spread"),
    ("prediction", "di_refused", "Conditions unlike anything in training (DI 0.97)"),
    ("decision", "stale_bar", "An approval on this candidate came from an earlier decision bar"),
)


@dataclass(frozen=True)
class SeedThresholds:
    """The breaker limits the seed generates fixtures **against**.

    Inject the real ones from `config/default.yaml` and every fixture scales with them.
    The defaults are fixture-shape constants, not recommended values: a fixture pinned
    to a literal silently stops overshooting the moment the operator sets a larger
    limit, and Phase 3 then fails for a reason unrelated to the code under test.
    """

    max_consecutive_data_blocks: int = FIXTURE_SHAPE_BLOCK_LIMIT
    max_drawdown_pct: Decimal = FIXTURE_SHAPE_DRAWDOWN_LIMIT
    max_consecutive_losses: int = FIXTURE_SHAPE_LOSS_STREAK_LIMIT
    error_rate_window_s: int = FIXTURE_SHAPE_ERROR_WINDOW_S
    max_errors_in_window: int = FIXTURE_SHAPE_ERROR_LIMIT

    # --- overshoot rules -------------------------------------------------
    # Counts overshoot by three; the ratio overshoots by a factor of two, capped short
    # of a total wipeout so that a large configured limit cannot ask for a negative
    # equity.

    @property
    def outage_run_length(self) -> int:
        return self.max_consecutive_data_blocks + 3

    @property
    def losing_streak_length(self) -> int:
        return self.max_consecutive_losses + 3

    @property
    def error_row_count(self) -> int:
        return self.max_errors_in_window + 3

    @property
    def target_drawdown_pct(self) -> Decimal:
        doubled = self.max_drawdown_pct * 2
        halfway_to_ruin = (self.max_drawdown_pct + Decimal(1)) / 2
        return min(doubled, halfway_to_ruin)


DEFAULT_THRESHOLDS: Final = SeedThresholds()


@dataclass(frozen=True)
class OutageRun:
    """The trailing run of ticks carrying a `data_guard` block record."""

    ticks: tuple[tuple[str, int], ...]
    run_ids: tuple[str, ...]
    first_ts: int
    last_ts: int
    double_blocker_ticks: tuple[tuple[str, int], ...]

    @property
    def length(self) -> int:
        return len(self.ticks)


@dataclass(frozen=True)
class DrawdownFixture:
    """The deepest point of the seeded equity curve, which is also its **latest** row.

    `safety` reads only the latest equity row, so a drawdown parked in the middle of the
    series would satisfy a literal reading of "a series containing a drawdown" and still
    leave the breaker with nothing to trip on.
    """

    trough_ts: int
    peak_equity: Decimal
    equity: Decimal
    drawdown_pct: Decimal


@dataclass(frozen=True)
class LossStreakFixture:
    """The trailing run of losing closed trades, oldest first."""

    trade_ids: tuple[str, ...]
    realised_pnl: tuple[Decimal, ...]

    @property
    def length(self) -> int:
        return len(self.trade_ids)


@dataclass(frozen=True)
class ErrorRateFixture:
    """`status = 'ERROR'` block records inside the trailing error window."""

    ids: tuple[int, ...]
    window_start_ts: int
    window_end_ts: int

    @property
    def count(self) -> int:
        return len(self.ids)


@dataclass(frozen=True)
class SeedFixtures:
    """Every fixture the seed guarantees, by name.

    Derived by reading the database back after writing it. A Phase 3 test asks for "the
    outage run" rather than rediscovering it by query.
    """

    db_path: Path
    seed: int
    thresholds: SeedThresholds
    seed_now: int
    reporting_currency: str
    run_ids: tuple[str, ...]
    consecutive_data_block_run: OutageRun
    open_positions: tuple[str, ...]
    resting_entry_orders: tuple[int, ...]
    drawdown: DrawdownFixture
    losing_streak: LossStreakFixture
    error_blocks: ErrorRateFixture
    trade_count: int
    rejection_count: int
    leaderboard_count: int
    position_count: int
    order_count: int
    equity_snapshot_count: int
    block_record_count: int
    #: `cycle_id` values that appear in `block_records` under more than one `run_id`.
    #: Spec 11 requires these: they are what make "a tick is `(run_id, cycle_id)`, never
    #: `cycle_id` alone" a claim this database can falsify rather than merely state.
    cycle_ids_shared_across_runs: tuple[int, ...] = field(default=())
    warnings: tuple[str, ...] = field(default=())


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_DOWN)


def _qty(value: Decimal) -> Decimal:
    """Quantities always round **down**. Rounding up produces an order Kraken rejects."""
    return value.quantize(LOT, rounding=ROUND_DOWN)


def _pct(value: Decimal) -> Decimal:
    return value.quantize(PCT, rounding=ROUND_DOWN)


def seed_database(
    db_path: Path,
    *,
    seed: int = DEFAULT_SEED,
    thresholds: SeedThresholds = DEFAULT_THRESHOLDS,
) -> SeedFixtures:
    """Migrate if needed, fill the database, and return the fixtures by name."""
    db_path = Path(db_path)
    builder = _SeedBuilder(db_path=db_path, seed=seed, thresholds=thresholds)
    return builder.build()


class _SeedBuilder:
    """Writes one seeded database. Split out so the timeline is computed once."""

    def __init__(self, *, db_path: Path, seed: int, thresholds: SeedThresholds) -> None:
        self.db_path = db_path
        self.seed = seed
        self.thresholds = thresholds
        self.rng = random.Random(seed)

        outage_len = thresholds.outage_run_length
        # Enough history for the console to look lived-in, and always enough room for
        # the outage plus a comfortable clean prefix in front of it.
        self.n_ticks = max(720, outage_len + 240)
        self.outage_start = self.n_ticks - outage_len
        # The daemon dies part-way through the outage and comes back. That is what puts
        # the run boundary *inside* the outage, and what makes the `ts` ordering
        # load-bearing: `run_b` restarts at `cycle_id` 1 while `run_a` is in the
        # seven-hundreds, so a `cycle_id`-ordered walk never reaches the newer ticks.
        self.run_boundary = self.outage_start + outage_len // 2
        self.error_window_ticks = max(1, thresholds.error_rate_window_s // 60)
        # `run_b` restarts at cycle 1, so the only ticks in `run_a` whose `cycle_id`s it
        # can collide with are the opening few. Those are kept clear of entries and
        # exits, because a block record on a tick that placed an order is a timeline
        # that could not have happened. Bounded well below the first close so a trade
        # can never be clamped to open after it closed.
        self.reserved_opening_ticks = min(self.n_ticks - self.run_boundary, RESERVED_TICKS)

        self.run_a = "seed-run-0001"
        self.run_b = "seed-run-0002"
        self.run_prior = "seed-run-0000"

    # -- timeline ---------------------------------------------------------

    def ts(self, tick: int) -> int:
        """Microseconds for a tick index. The last tick is exactly the seed's "now"."""
        return SEED_ANCHOR_TS - (self.n_ticks - 1 - tick) * MICROS_PER_MINUTE

    def tick_of(self, moment: int) -> int:
        """Inverse of :meth:`ts`, for placing a block record relative to a written row."""
        return (moment - self.ts(0)) // MICROS_PER_MINUTE

    def run_id_for(self, tick: int) -> str:
        return self.run_a if tick < self.run_boundary else self.run_b

    def cycle_id_for(self, tick: int) -> int:
        """`cycle_id` restarts at 1 with the process. The overlap this creates between
        the two runs is deliberate — see the module docstring."""
        if tick < self.run_boundary:
            return tick + 1
        return tick - self.run_boundary + 1

    # -- build ------------------------------------------------------------

    def build(self) -> SeedFixtures:
        with StoreClient(self.db_path) as store:
            store.migrate()
            with store.transaction():
                self._write_runs(store)
                trades, positions, orders = self._write_trading_history(store)
                self._write_equity(store, trades, positions)
                blocked = self._write_blocks(store, self._trading_ticks(positions, orders))
                self._write_rejections(store, blocked)
                self._write_leaderboard(store)
                self._write_commands(store)
            return self._derive_fixtures(store)

    # -- runs -------------------------------------------------------------

    def _write_runs(self, store: StoreClient) -> None:
        first_ts = self.ts(0)
        boundary_ts = self.ts(self.run_boundary)
        store.write_run(
            RunRow(
                run_id=self.run_prior,
                mode=RunMode.PAPER,
                started_at=first_ts - 6 * 60 * MICROS_PER_MINUTE,
                ended_at=first_ts - MICROS_PER_MINUTE,
                acsoe_version="0.1.0",
                updated_at=first_ts - MICROS_PER_MINUTE,
            )
        )
        store.write_run(
            RunRow(
                run_id=self.run_a,
                mode=RunMode.PAPER,
                started_at=first_ts,
                ended_at=boundary_ts - MICROS_PER_MINUTE,
                acsoe_version="0.1.0",
                updated_at=boundary_ts - MICROS_PER_MINUTE,
            )
        )
        store.write_run(
            RunRow(
                run_id=self.run_b,
                mode=RunMode.PAPER,
                started_at=boundary_ts,
                ended_at=None,
                acsoe_version="0.1.0",
                updated_at=SEED_ANCHOR_TS,
            )
        )

    # -- trades, positions, orders ---------------------------------------

    def _write_trading_history(
        self, store: StoreClient
    ) -> tuple[list[TradeRow], list[PositionRow], list[OrderRow]]:
        streak = self.thresholds.losing_streak_length
        n_trades = streak + 25

        # Every trade closes before the outage begins. Exits are held while `data_guard`
        # is blocking, so a trade closing mid-outage would contradict the manage-chain
        # hold the same seed is there to exercise.
        first_close = 20
        last_close = self.outage_start - 30
        step = max(1, (last_close - first_close) // max(1, n_trades - 1))

        trades: list[TradeRow] = []
        positions: list[PositionRow] = []
        orders: list[OrderRow] = []
        userref = 700_000_001

        for index in range(n_trades):
            close_tick = first_close + index * step
            # The last `streak` trades lose. The one immediately before them wins, so
            # the streak length is exact rather than "at least".
            in_streak = index >= n_trades - streak
            is_win = False if in_streak else (index != n_trades - streak - 1 and index % 3 != 1)
            if index == n_trades - streak - 1:
                is_win = True

            trade, position, entry_order, exit_order = self._make_closed_trade(
                index=index, close_tick=close_tick, is_win=is_win, entry_userref=userref
            )
            userref += 2
            trades.append(trade)
            positions.append(position)
            orders.extend((entry_order, exit_order))

        # Open positions. Distinct pairs — `ux_positions_open_pair` is invariant 6
        # enforced by the database, so two open rows on one pair would raise.
        open_pairs = (_PAIRS[2], _PAIRS[5])
        for offset, pair in enumerate(open_pairs):
            position, entry_order = self._make_open_position(
                index=offset, pair=pair, entry_userref=userref
            )
            userref += 1
            positions.append(position)
            orders.append(entry_order)

        # Resting entry orders on pairs with no open position. A resting post-only buy
        # is exposure that has not happened yet, which is why invariant 14 escalates on
        # it as well as on an open position.
        for offset, pair in enumerate((_PAIRS[0], _PAIRS[8])):
            orders.append(self._make_resting_entry(index=offset, pair=pair, userref=userref))
            userref += 1

        # One entry that outran its unfilled window and was cancelled rather than chased.
        orders.append(self._make_cancelled_entry(pair=_PAIRS[7], userref=userref))
        userref += 1

        for trade in trades:
            store.write_trade(trade)
        for position in positions:
            store.write_position(position)
        for order in orders:
            store.write_order(order)
        return trades, positions, orders

    def _make_closed_trade(
        self, *, index: int, close_tick: int, is_win: bool, entry_userref: int
    ) -> tuple[TradeRow, PositionRow, OrderRow, OrderRow]:
        pair, base, quote, reference = _PAIRS[index % len(_PAIRS)]
        hold_ticks = self.rng.randint(120, 700)
        # Clamped to the reserved opening ticks, not to zero: a long hold would otherwise
        # pile every early entry onto tick 0, and those are the only ticks whose
        # `cycle_id`s are low enough for `run_b` to collide with.
        open_tick = max(self.reserved_opening_ticks, close_tick - hold_ticks)
        opened_at = self.ts(open_tick)
        closed_at = self.ts(close_tick)

        drift = Decimal(self.rng.randint(-400, 400)) / Decimal(10_000)
        entry_price = _money(reference * (Decimal(1) + drift)) if quote == "USD" else reference
        entry_price = max(entry_price, CENT)

        notional = Decimal("80.00")
        quantity = _qty(notional / entry_price)
        if quantity <= 0:
            quantity = LOT
        cost_basis = _money(quantity * entry_price)

        if is_win:
            outcome = TradeOutcome.TARGET
            gross_move = Decimal("0.03")
        else:
            outcome = TradeOutcome.STOP if index % 4 else TradeOutcome.TIMEOUT
            gross_move = Decimal("-0.015") if outcome is TradeOutcome.STOP else Decimal("-0.004")

        exit_price = _money(entry_price * (Decimal(1) + gross_move))
        proceeds = _money(quantity * exit_price)

        fee_fraction = self._fabricated_fee_fraction()
        entry_fee = _money(cost_basis * fee_fraction)
        exit_fee = _money(proceeds * fee_fraction)

        realised_quote = _money(proceeds - cost_basis - entry_fee - exit_fee)
        # Fiat quote equals the reporting currency in this fixture, so FX is 1. Invariant
        # 7 still requires the rates to be recorded per trade rather than assumed.
        fx = Decimal("1.00000000")
        realised = realised_quote
        realised_pct = _pct(realised / cost_basis) if cost_basis else Decimal("0")

        trade_id = f"seed-trade-{index:04d}"
        position_id = f"seed-pos-{index:04d}"
        exit_userref = entry_userref + 1

        trade = TradeRow(
            trade_id=trade_id,
            position_id=position_id,
            run_id=self.run_id_for(close_tick),
            cycle_id=self.cycle_id_for(close_tick),
            pair=pair,
            base=base,
            quote=quote,
            qty=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            entry_userref=entry_userref,
            exit_userref=exit_userref,
            opened_at=opened_at,
            closed_at=closed_at,
            outcome=outcome,
            realised_pnl=realised,
            realised_pnl_pct=realised_pct,
            realised_pnl_quote=realised_quote,
            reporting_currency=FIXTURE_SHAPE_REPORTING_CURRENCY,
            fx_rate_entry=fx,
            fx_rate_exit=fx,
            fallbacks_used=("fee_tier_assumed_worst",) if index % 7 == 0 else (),
            updated_at=closed_at,
        )

        position = PositionRow(
            position_id=position_id,
            run_id=self.run_id_for(open_tick),
            cycle_id=self.cycle_id_for(open_tick),
            pair=pair,
            base=base,
            quote=quote,
            status=PositionStatus.CLOSED,
            qty=quantity,
            entry_price=entry_price,
            target_price=_money(entry_price * Decimal("1.03")),
            stop_price=_money(entry_price * Decimal("0.985")),
            timeout_at=opened_at + 48 * 15 * MICROS_PER_MINUTE,
            entry_userref=entry_userref,
            last_price=exit_price,
            unrealised_pnl=Decimal("0.00"),
            opened_at=opened_at,
            closed_at=closed_at,
            trade_id=trade_id,
            updated_at=closed_at,
        )

        entry_order = OrderRow(
            userref=entry_userref,
            order_id=f"OSEED-{entry_userref}",
            run_id=self.run_id_for(open_tick),
            cycle_id=self.cycle_id_for(open_tick),
            position_id=position_id,
            pair=pair,
            side=OrderSide.BUY,
            intent=OrderIntent.ENTRY,
            order_type=OrderType.LIMIT,
            oflags="post",
            status=OrderStatus.FILLED,
            qty=quantity,
            limit_price=entry_price,
            filled_qty=quantity,
            avg_fill_price=entry_price,
            fee=entry_fee,
            placed_at=opened_at,
            closed_at=opened_at,
            updated_at=opened_at,
        )

        # A stop must exit as a taker; a target exit may rest as a maker.
        exit_is_taker = outcome is not TradeOutcome.TARGET
        exit_order = OrderRow(
            userref=exit_userref,
            order_id=f"OSEED-{exit_userref}",
            run_id=self.run_id_for(close_tick),
            cycle_id=self.cycle_id_for(close_tick),
            position_id=position_id,
            pair=pair,
            side=OrderSide.SELL,
            intent=OrderIntent.EXIT,
            order_type=OrderType.MARKET if exit_is_taker else OrderType.LIMIT,
            oflags="" if exit_is_taker else "post",
            status=OrderStatus.FILLED,
            qty=quantity,
            limit_price=None if exit_is_taker else exit_price,
            filled_qty=quantity,
            avg_fill_price=exit_price,
            fee=exit_fee,
            placed_at=closed_at,
            closed_at=closed_at,
            updated_at=closed_at,
        )
        return trade, position, entry_order, exit_order

    def _make_open_position(
        self, *, index: int, pair: tuple[str, str, str, Decimal], entry_userref: int
    ) -> tuple[PositionRow, OrderRow]:
        name, base, quote, reference = pair
        open_tick = self.outage_start - 180 - index * 25
        opened_at = self.ts(max(0, open_tick))
        entry_price = _money(reference * (Decimal("0.995") + Decimal(index) / Decimal(500)))
        quantity = _qty(Decimal("80.00") / entry_price)
        last_price = _money(entry_price * Decimal("1.004"))
        position_id = f"seed-open-{index:04d}"

        position = PositionRow(
            position_id=position_id,
            run_id=self.run_id_for(max(0, open_tick)),
            cycle_id=self.cycle_id_for(max(0, open_tick)),
            pair=name,
            base=base,
            quote=quote,
            status=PositionStatus.OPEN,
            qty=quantity,
            entry_price=entry_price,
            target_price=_money(entry_price * Decimal("1.03")),
            stop_price=_money(entry_price * Decimal("0.985")),
            timeout_at=opened_at + 48 * 15 * MICROS_PER_MINUTE,
            entry_userref=entry_userref,
            last_price=last_price,
            unrealised_pnl=_money(quantity * (last_price - entry_price)),
            opened_at=opened_at,
            closed_at=None,
            trade_id=None,
            updated_at=SEED_ANCHOR_TS,
        )
        order = OrderRow(
            userref=entry_userref,
            order_id=f"OSEED-{entry_userref}",
            run_id=position.run_id,
            cycle_id=position.cycle_id,
            position_id=position_id,
            pair=name,
            side=OrderSide.BUY,
            intent=OrderIntent.ENTRY,
            order_type=OrderType.LIMIT,
            oflags="post",
            status=OrderStatus.FILLED,
            qty=quantity,
            limit_price=entry_price,
            filled_qty=quantity,
            avg_fill_price=entry_price,
            fee=_money(quantity * entry_price * self._fabricated_fee_fraction()),
            placed_at=opened_at,
            closed_at=opened_at,
            updated_at=opened_at,
        )
        return position, order

    def _make_resting_entry(
        self, *, index: int, pair: tuple[str, str, str, Decimal], userref: int
    ) -> OrderRow:
        name, _base, _quote, reference = pair
        placed_tick = self.outage_start - 6 - index * 3
        placed_at = self.ts(max(0, placed_tick))
        # Post-only, below the market, exactly as invariant 8 requires an entry to be.
        limit_price = _money(reference * Decimal("0.997"))
        quantity = _qty(Decimal("80.00") / limit_price)
        return OrderRow(
            userref=userref,
            order_id=f"OSEED-{userref}",
            run_id=self.run_id_for(max(0, placed_tick)),
            cycle_id=self.cycle_id_for(max(0, placed_tick)),
            position_id=None,
            pair=name,
            side=OrderSide.BUY,
            intent=OrderIntent.ENTRY,
            order_type=OrderType.LIMIT,
            oflags="post",
            status=OrderStatus.RESTING,
            qty=quantity,
            limit_price=limit_price,
            filled_qty=Decimal("0.00000000"),
            avg_fill_price=None,
            fee=None,
            placed_at=placed_at,
            closed_at=None,
            updated_at=placed_at,
        )

    def _make_cancelled_entry(self, *, pair: tuple[str, str, str, Decimal], userref: int) -> OrderRow:
        name, _base, _quote, reference = pair
        placed_tick = self.outage_start - 90
        placed_at = self.ts(max(0, placed_tick))
        limit_price = _money(reference * Decimal("0.994"))
        quantity = _qty(Decimal("80.00") / limit_price)
        return OrderRow(
            userref=userref,
            order_id=f"OSEED-{userref}",
            run_id=self.run_id_for(max(0, placed_tick)),
            cycle_id=self.cycle_id_for(max(0, placed_tick)),
            position_id=None,
            pair=name,
            side=OrderSide.BUY,
            intent=OrderIntent.ENTRY,
            order_type=OrderType.LIMIT,
            oflags="post",
            status=OrderStatus.CANCELLED,
            qty=quantity,
            limit_price=limit_price,
            filled_qty=Decimal("0.00000000"),
            avg_fill_price=None,
            fee=None,
            placed_at=placed_at,
            closed_at=placed_at + 20 * MICROS_PER_MINUTE,
            updated_at=placed_at + 20 * MICROS_PER_MINUTE,
        )

    def _fabricated_fee_fraction(self) -> Decimal:
        low, high = _FABRICATED_FEE_FRACTION
        span = int((high - low) * 10_000)
        return low + Decimal(self.rng.randint(0, span)) / Decimal(10_000)

    # -- equity -----------------------------------------------------------

    def _write_equity(
        self, store: StoreClient, trades: list[TradeRow], positions: list[PositionRow]
    ) -> None:
        """One row per tick, with the deepest drawdown on the **last** row.

        `safety` reads only the latest equity row. A drawdown parked mid-series would
        satisfy a literal reading of "a series containing a drawdown" and leave the
        breaker nothing to trip on, so the curve rises, peaks, and then declines
        monotonically into the outage.
        """
        peak_tick = int(self.n_ticks * 0.55)
        peak_target = _money(FIXTURE_SHAPE_STARTING_EQUITY * Decimal("1.12"))

        rise: list[Decimal] = []
        for tick in range(peak_tick + 1):
            fraction = Decimal(tick) / Decimal(peak_tick) if peak_tick else Decimal(1)
            wobble = Decimal(self.rng.randint(-150, 150)) / Decimal(100)
            rise.append(
                _money(
                    FIXTURE_SHAPE_STARTING_EQUITY
                    + (peak_target - FIXTURE_SHAPE_STARTING_EQUITY) * fraction
                    + wobble
                )
            )
        peak_actual = max(rise)
        trough = _money(peak_actual * (Decimal(1) - self.thresholds.target_drawdown_pct))

        equities: list[Decimal] = list(rise)
        fall_span = self.n_ticks - 1 - peak_tick
        start_of_fall = rise[-1]
        for step in range(1, fall_span + 1):
            fraction = Decimal(step) / Decimal(fall_span)
            equities.append(_money(start_of_fall - (start_of_fall - trough) * fraction))

        closes = sorted((trade.closed_at, trade.realised_pnl) for trade in trades)
        open_windows = [
            (position.qty * position.entry_price, position.opened_at, position.closed_at)
            for position in positions
        ]

        running_peak = Decimal("0.00")
        close_cursor = 0
        realised_cum = Decimal("0.00")
        for tick in range(self.n_ticks):
            moment = self.ts(tick)
            while close_cursor < len(closes) and closes[close_cursor][0] <= moment:
                realised_cum = _money(realised_cum + closes[close_cursor][1])
                close_cursor += 1

            cost_basis = Decimal("0.00")
            open_count = 0
            for basis, opened_at, closed_at in open_windows:
                if opened_at <= moment and (closed_at is None or moment < closed_at):
                    cost_basis = _money(cost_basis + basis)
                    open_count += 1
            positions_value = _money(cost_basis * Decimal("1.004"))
            unrealised = _money(positions_value - cost_basis)

            equity = equities[tick]
            running_peak = max(running_peak, equity)
            store.write_equity_snapshot(
                EquitySnapshotRow(
                    cycle_id=self.cycle_id_for(tick),
                    run_id=self.run_id_for(tick),
                    ts=moment,
                    currency=FIXTURE_SHAPE_REPORTING_CURRENCY,
                    equity=equity,
                    peak_equity=running_peak,
                    cash=_money(equity - positions_value),
                    positions_value=positions_value,
                    unrealised_pnl=unrealised,
                    realised_pnl_cum=realised_cum,
                    open_position_count=open_count,
                    # Every seeded row is written in the ordinary-tick shape (spec 113).
                    # Set explicitly rather than left to the model's default, so the
                    # fixture says so itself.
                    cash_source=CashSource.CYCLE_START,
                    updated_at=moment,
                )
            )

    # -- block records ----------------------------------------------------

    def _trading_ticks(
        self, positions: Sequence[PositionRow], orders: Sequence[OrderRow]
    ) -> frozenset[int]:
        """Ticks on which the seed placed, filled, cancelled, opened or closed something.

        A blocked tick skips the opportunity chain and holds the manage chain, so an
        order placed or a position opened on a tick that also carries a block record is
        a timeline that could not have happened. The block writer takes this set and
        stays off it. It is derived from the rows actually written rather than from the
        arithmetic that placed them, because the two agree only when there is no bug.
        """
        moments: list[int] = []
        for position in positions:
            moments.extend(m for m in (position.opened_at, position.closed_at) if m is not None)
        for order in orders:
            moments.extend(m for m in (order.placed_at, order.closed_at) if m is not None)
        return frozenset(self.tick_of(moment) for moment in moments)

    def _write_blocks(self, store: StoreClient, trading_ticks: frozenset[int]) -> frozenset[int]:
        """Build the tick-to-blockers map, then write it with `is_primary` on the first
        blocker of each tick in guard-chain order.

        Returns the ticks that ended up blocked, so the rejection writer can stay off
        them: a guard block skips the opportunity chain, so a blocked tick never had a
        candidate to refuse.
        """
        per_tick: dict[int, list[tuple[str, BlockStatus, str]]] = {}

        def add(tick: int, engine: str, status: BlockStatus, reason: str) -> None:
            per_tick.setdefault(tick, []).append((engine, status, reason))

        # The outage itself.
        for offset in range(self.thresholds.outage_run_length):
            tick = self.outage_start + offset
            add(
                tick,
                DATA_GUARD_ENGINE,
                BlockStatus.BLOCK,
                "Market data is stale: no book update in 4 minutes",
            )
            # A tick where two guards blocked contributes ONE to the outage count and
            # TWO rows. Seeding it deliberately means the tick-versus-row distinction is
            # exercised rather than assumed.
            if offset % 4 == 1:
                add(
                    tick,
                    "safety",
                    BlockStatus.BLOCK,
                    "Account drawdown past the configured limit",
                )

        # The tick immediately before the outage carries a block with NO `data_guard`
        # row. That is what makes the trailing run end exactly where it should under any
        # correct counting rule, rather than depending on which tick happens to be
        # adjacent in the table.
        add(
            self.outage_start - 1,
            "market_sensor",
            BlockStatus.BLOCK,
            "15-minute candle did not complete",
        )

        # ERROR rows inside the trailing error window. Placed on outage ticks first,
        # cycling through engines so more than one can share a tick if the configured
        # limit is large.
        window_first_tick = max(0, self.n_ticks - self.error_window_ticks)
        error_slots: list[tuple[int, str]] = []
        for tick in range(self.n_ticks - 1, window_first_tick - 1, -1):
            in_outage = tick >= self.outage_start
            for engine in _ERROR_ENGINES:
                # Outside the outage an ERROR row must not sit on a tick that would then
                # look like part of it; those ticks never receive a `data_guard` row, so
                # they are safe, but they must also stay behind the breaker tick above.
                if not in_outage and tick >= self.outage_start - 1:
                    continue
                error_slots.append((tick, engine))
        needed = self.thresholds.error_row_count
        if needed > len(error_slots):
            # Not a seed limitation to work around: `block_records` holds one row per
            # blocker per tick, so the number of ERROR rows that can exist inside the
            # window is bounded by ticks x engines whatever writes them. Say so, with
            # both ceilings — this seed's, and the one the guard chain itself imposes —
            # rather than advising the operator to lower a trading threshold to suit a
            # fixture.
            raise ValueError(
                f"cannot place {needed} ERROR rows inside the {self.error_window_ticks}-tick "
                f"error window: block_records carries at most one row per engine per tick, "
                f"and this seed errors {len(_ERROR_ENGINES)} engines, so its ceiling is "
                f"{len(error_slots)}. safety.max_errors_in_window="
                f"{self.thresholds.max_errors_in_window} needs {needed}. The whole guard "
                f"chain is {len(GUARD_CHAIN_ORDER)} engines, so a limit above "
                f"{self.error_window_ticks * len(GUARD_CHAIN_ORDER)} could not be reached "
                "by a real timeline either, and that breaker would never fire."
            )
        for tick, engine in error_slots[:needed]:
            add(tick, engine, BlockStatus.ERROR, f"{engine} raised during the tick")

        # Older history, well behind the breaker tick and therefore unreachable by any
        # trailing count: a short earlier outage, closed off by a non-`data_guard` block
        # so that a naive row-adjacency count and a tick-gap-aware count agree on it.
        early = max(1, self.outage_start // 3)
        for offset in range(3):
            add(
                early + offset,
                DATA_GUARD_ENGINE,
                BlockStatus.BLOCK,
                "Negative spread reported on the book",
            )
        add(early + 3, "market_sensor", BlockStatus.BLOCK, "Candle gap in the 15-minute stream")

        # `cycle_id` collisions between the two runs, mandated by spec 11 and placed
        # here rather than left to chance.
        #
        # `run_b` restarts at cycle 1 and only lives for the tail of the outage, so its
        # cycle numbers sit in `run_a`'s opening minutes. Blocking a few of those opening
        # ticks makes `(run_a, 4)` and `(run_b, 4)` both real rows in `block_records`,
        # which is what turns "a tick is `(run_id, cycle_id)`, never `cycle_id` alone"
        # into something a fixture can fail. Without the collision, a counter that
        # grouped by `cycle_id` alone and a partial unique index scoped to `cycle_id`
        # alone would both survive this database unnoticed. With it, the first counts
        # the wrong outage and the second refuses to insert.
        #
        # They sit at the very start of the history, hundreds of ticks behind the
        # terminator above, so no trailing count can reach them, and they avoid every
        # tick that placed or closed an order.
        run_b_cycles = self.n_ticks - self.run_boundary
        collidable = [
            tick
            for tick in range(run_b_cycles)
            if tick not in trading_ticks and tick % DECISION_BAR_TICKS != 0
        ]
        for tick in collidable[-4:]:
            add(
                tick,
                DATA_GUARD_ENGINE,
                BlockStatus.BLOCK,
                "Book subscription not yet confirmed after start-up",
            )

        for tick in sorted(per_tick):
            blockers = sorted(
                per_tick[tick],
                key=lambda item: GUARD_CHAIN_ORDER.index(item[0]),
            )
            moment = self.ts(tick)
            for position, (engine, status, reason) in enumerate(blockers):
                store.write_block_record(
                    BlockRecordRow(
                        cycle_id=self.cycle_id_for(tick),
                        run_id=self.run_id_for(tick),
                        ts=moment,
                        blocked_by=engine,
                        block_reason=reason,
                        is_primary=position == 0,
                        status=status,
                        updated_at=moment,
                    )
                )
        return frozenset(per_tick)

    # -- rejections -------------------------------------------------------

    def _write_rejections(self, store: StoreClient, blocked_ticks: frozenset[int]) -> None:
        """One per closed decision bar, on ticks the guard chain did not block.

        A guard block skips the opportunity chain entirely, so a blocked tick never has
        a candidate to reject. Candidates are born only on a closed 15-minute bar, so
        rejections land on every fifteenth tick — minus the ones `_write_blocks` took,
        which is why the blocked set is passed in rather than recomputed from the
        outage arithmetic. The earlier episodes move when the injected thresholds move,
        and one of them landing on a bar close is otherwise invisible.
        """
        blocked_from = self.outage_start - 1
        for tick in range(DECISION_BAR_TICKS, blocked_from, DECISION_BAR_TICKS):
            if tick in blocked_ticks:
                continue
            engine, code, reason = _REJECTION_REASONS[
                self.rng.randrange(len(_REJECTION_REASONS))
            ]
            pair = _PAIRS[self.rng.randrange(len(_PAIRS))][0]
            moment = self.ts(tick)
            friction = _pct(Decimal(self.rng.randint(60, 140)) / Decimal(10_000))
            expected = _pct(Decimal(self.rng.randint(20, 220)) / Decimal(10_000))
            store.write_rejection(
                RejectionRow(
                    cycle_id=self.cycle_id_for(tick),
                    run_id=self.run_id_for(tick),
                    ts=moment,
                    pair=pair,
                    rejected_by=engine,
                    reason_code=code,
                    reason=reason,
                    expected_move_pct=expected,
                    friction_pct=friction,
                    net_edge_pct=_pct(expected - friction),
                    hurdle_pct=_pct(friction),
                    candidate_score=round(self.rng.uniform(0.1, 0.9), 4),
                    shap_ref=f"shap/{self.run_id_for(tick)}/{self.cycle_id_for(tick)}",
                    details=None,
                    updated_at=moment,
                )
            )

    # -- leaderboard ------------------------------------------------------

    def _write_leaderboard(self, store: StoreClient) -> None:
        for index in range(6):
            trained_at = self.ts(0) - (6 - index) * 24 * 60 * MICROS_PER_MINUTE
            store.write_leaderboard_entry(
                LeaderboardRow(
                    model_id="predictor",
                    model_version=f"v0.{index + 1}",
                    training_run_id=f"seed-train-{index:04d}",
                    trained_at=trained_at,
                    fold=f"fold-{index % 3}",
                    n_trades=40 + index * 7,
                    win_rate=round(0.42 + index * 0.015, 4),
                    sharpe=round(0.2 + index * 0.11, 4),
                    deflated_sharpe=round(0.05 + index * 0.07, 4),
                    alpha=round(-0.02 + index * 0.012, 4),
                    beta=round(0.55 - index * 0.03, 4),
                    brier=round(0.26 - index * 0.008, 4),
                    net_pnl=_money(Decimal(-40 + index * 18)),
                    reporting_currency=FIXTURE_SHAPE_REPORTING_CURRENCY,
                    promoted=index == 5,
                    notes=None,
                    updated_at=trained_at,
                )
            )

    # -- commands ---------------------------------------------------------

    def _write_commands(self, store: StoreClient) -> None:
        """Audit history only, and every row fully consumed.

        A seeded pending `activate` would start a daemon trading on boot; a seeded
        claimed-but-unconsumed `close_all` would liquidate on boot, because the reader
        re-applies interrupted commands before the first tick. Neither is a thing a
        fixture may do.
        """
        for offset, (command, source, tick) in enumerate(
            (
                (CommandName.ACTIVATE, CommandSource.CONSOLE, 4),
                (CommandName.FREEZE, CommandSource.CONSOLE, self.outage_start // 2),
                (CommandName.ACTIVATE, CommandSource.CONSOLE, self.outage_start // 2 + 30),
            )
        ):
            moment = self.ts(tick)
            store.append_command(
                CommandRow(
                    command=command.value,
                    source=source,
                    reason=None,
                    created_at=moment,
                    created_by_run_id=None if source is CommandSource.CONSOLE else self.run_a,
                    claimed_at=moment + offset,
                    claimed_by_run_id=self.run_id_for(tick),
                    consumed_at=moment + offset,
                    updated_at=moment + offset,
                )
            )

    # -- fixtures ---------------------------------------------------------

    def _derive_fixtures(self, store: StoreClient) -> SeedFixtures:
        """Read the database back and describe what is actually in it.

        Deliberately not built from the loop counters above. Those say what the seed
        *intended* to write; these say what it wrote, and the two differ exactly when
        there is a bug — which is the case a fixture accessor exists to catch rather
        than to hide.
        """
        conn = store.connection
        warnings: list[str] = []

        # `current_tick=None` on purpose: a seeded database is a finished timeline with
        # no tick in flight, so "the trailing run of stored ticks" *is* the question.
        # `safety` never reads it this way — it anchors the walk to its own tick.
        outage = store.stored_data_guard_outage_excluding_current_tick(current_tick=None)
        double_blockers = tuple(
            (str(row["run_id"]), int(row["cycle_id"]))
            for row in conn.execute(
                """
                SELECT run_id, cycle_id
                FROM block_records
                WHERE blocked_by IN (?, 'safety')
                GROUP BY run_id, cycle_id
                HAVING COUNT(DISTINCT blocked_by) > 1
                ORDER BY MIN(ts) ASC
                """,
                (DATA_GUARD_ENGINE,),
            )
        )
        outage_tick_set = set(outage.ticks)
        outage_run = OutageRun(
            ticks=outage.ticks,
            run_ids=tuple(dict.fromkeys(run_id for run_id, _ in outage.ticks)),
            first_ts=outage.first_ts or 0,
            last_ts=outage.last_ts or 0,
            double_blocker_ticks=tuple(t for t in double_blockers if t in outage_tick_set),
        )

        latest = store.latest_equity_snapshot()
        if latest is None:  # pragma: no cover - the seed always writes a series
            raise RuntimeError("seed produced no equity snapshots")
        drawdown_pct = (latest.peak_equity - latest.equity) / latest.peak_equity
        drawdown = DrawdownFixture(
            trough_ts=latest.ts,
            peak_equity=latest.peak_equity,
            equity=latest.equity,
            drawdown_pct=drawdown_pct,
        )

        streak_ids: list[str] = []
        streak_pnl: list[Decimal] = []
        for trade in store.recent_closed_trades(limit=500):
            if trade.realised_pnl >= 0:
                break
            streak_ids.append(trade.trade_id)
            streak_pnl.append(trade.realised_pnl)
        streak_ids.reverse()
        streak_pnl.reverse()
        losing_streak = LossStreakFixture(
            trade_ids=tuple(streak_ids), realised_pnl=tuple(streak_pnl)
        )

        window_start = SEED_ANCHOR_TS - self.thresholds.error_rate_window_s * 1_000_000
        error_rows = store.block_records_in_window(
            start_ts=window_start, end_ts=SEED_ANCHOR_TS, status=BlockStatus.ERROR
        )
        error_blocks = ErrorRateFixture(
            ids=tuple(row.id for row in error_rows if row.id is not None),
            window_start_ts=window_start,
            window_end_ts=SEED_ANCHOR_TS,
        )

        open_positions = tuple(p.position_id for p in store.open_positions())
        resting = tuple(o.userref for o in store.resting_orders(intent=OrderIntent.ENTRY))

        shared_cycles = tuple(
            int(row["cycle_id"])
            for row in conn.execute(
                """
                SELECT cycle_id
                FROM block_records
                GROUP BY cycle_id
                HAVING COUNT(DISTINCT run_id) > 1
                ORDER BY cycle_id ASC
                """
            )
        )

        def count(table: str) -> int:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            return int(row["n"])

        if outage_run.length <= self.thresholds.max_consecutive_data_blocks:
            warnings.append(
                f"outage run is {outage_run.length} ticks, not past the configured "
                f"limit of {self.thresholds.max_consecutive_data_blocks}"
            )
        if drawdown.drawdown_pct <= self.thresholds.max_drawdown_pct:
            warnings.append(
                f"latest drawdown {drawdown.drawdown_pct} is not past the configured "
                f"limit of {self.thresholds.max_drawdown_pct}"
            )
        if losing_streak.length <= self.thresholds.max_consecutive_losses:
            warnings.append(
                f"losing streak is {losing_streak.length}, not past the configured "
                f"limit of {self.thresholds.max_consecutive_losses}"
            )
        if error_blocks.count <= self.thresholds.max_errors_in_window:
            warnings.append(
                f"{error_blocks.count} ERROR rows in the window, not past the configured "
                f"limit of {self.thresholds.max_errors_in_window}"
            )
        if len(outage_run.run_ids) < 2:
            warnings.append("outage run does not span two run_ids")
        if not outage_run.double_blocker_ticks:
            warnings.append("outage run contains no tick with two blockers")
        if not open_positions:
            warnings.append("no open position")
        if not resting:
            warnings.append("no resting entry order")
        if not shared_cycles:
            warnings.append(
                "no cycle_id appears under two run_ids in block_records, so nothing here "
                "distinguishes a tick keyed on (run_id, cycle_id) from one keyed on "
                "cycle_id alone"
            )

        return SeedFixtures(
            db_path=self.db_path,
            seed=self.seed,
            thresholds=self.thresholds,
            seed_now=SEED_ANCHOR_TS,
            reporting_currency=FIXTURE_SHAPE_REPORTING_CURRENCY,
            run_ids=(self.run_prior, self.run_a, self.run_b),
            consecutive_data_block_run=outage_run,
            open_positions=open_positions,
            resting_entry_orders=resting,
            drawdown=drawdown,
            losing_streak=losing_streak,
            error_blocks=error_blocks,
            trade_count=count("trades"),
            rejection_count=count("rejections"),
            leaderboard_count=count("leaderboard"),
            position_count=count("positions"),
            order_count=count("orders"),
            equity_snapshot_count=count("equity_snapshots"),
            block_record_count=count("block_records"),
            cycle_ids_shared_across_runs=shared_cycles,
            warnings=tuple(warnings),
        )
