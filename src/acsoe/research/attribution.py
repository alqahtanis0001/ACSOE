"""Alpha against two benchmarks, from a run's full equity curve including cash periods. Spec 138.

The Phase 7 row's first criterion: *"emits an alpha-versus-benchmark report from the full equity
curve including cash periods"*. This module reads one finished run's database and decides
nothing. It opens SQLite through a ``mode=ro`` URI, as the console's reader does, so it cannot
write a row even by mistake. It reads the columns it needs into its own small row types, money
columns as exact decimals from their stored text: `research/` may not import `acsoe.clients`, and
only `research/backtest.py` may reach the live side.

## The two benchmarks (ruling R8, 2026-09-19)

- **BTC/USD buy-and-hold.** Bought at the first tick of the run's window and held to the last,
  marked from the same time-and-sales partitions the run replayed, with no fees.
- **An equal-weighted basket of the pairs the run held, while it held them, and cash
  otherwise.** Between two consecutive ticks of the run the basket earns the mean of the price
  returns of the pairs with a position open at the first of the two ticks (``opened_at <= t <
  closed_at``), rebalanced to equal weights at every tick, and nothing when no position is open.
  Marked from the same partitions, with no fees. This is the lead's reading of R8 ("while held");
  the held pairs bought and held over the whole window would be a third series, not this one.

## The window is the run's own

Read from the run's first and last equity rows, never from a constant. The daily grid starts at
the first equity row and steps one day at a time up to the last. The part of the final day that
does not complete a whole day is left off the grid, and its length is reported. Every day of the
grid is regressed, **flat days included**: a day with no position is a day the run's capital was
in cash, which is the whole point of "including cash periods". A grid day with no equity row at or
before it is refused rather than carried forward, since nothing on disk says what the account was.

## The regression

Daily equity returns on daily benchmark returns, by ordinary least squares with a HAC
(Newey-West) covariance, because consecutive days share open positions. The lag is the larger of
two numbers, both stated: the most grid days any one hold spans, less one, so no two correlated
days are ever treated as independent; and the Newey-West rule of thumb ``floor(4 (n/100)^(2/9))``.
The intervals use the t distribution on the residual degrees of freedom. **Alpha is significant**
only when its 95% interval excludes zero. The effective sample size beside it is
``n x (se_ols / se_hac)^2``, capped at ``n``: the number of independent days that would give the
HAC standard error.

## What the rest of the report carries

Per-trade statistics beside the regression (count, pairs, outcome mix, net per trade with its
interval, and engine 10's expected move at entry beside the realised move), the coverage that
travels with the result (incomplete-vector refusals, the survivorship count, the scenario digest),
and the funnel in the chain's order. **Every interval states that overlapping holds are not
independent and that the true interval is wider.** Below ten trades no interval is reported.

**Joins carry prerequisite 8.** ``cycle_id`` on ``orders`` and ``positions`` is the last tick that
wrote the row, so a position is placed in time by ``opened_at`` and an order by ``placed_at``, and
this module never joins either on ``(run_id, cycle_id)``.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import itertools
import json
import math
import sqlite3
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Protocol

from acsoe.modelling.promotion import student_t_quantile

__all__ = [
    "BTC_PAIR",
    "CHAIN_ORDER",
    "AttributionError",
    "AttributionReport",
    "PartitionMarks",
    "PriceMarks",
    "Regression",
    "attribute",
    "daily_grid",
    "main",
    "marks_from_description",
    "regress",
    "regress_digest",
]

MICROS: Final = 1_000_000
DAY_US: Final = 86_400 * MICROS
_WEEK_S: Final = 7 * 86_400

#: The benchmark's own pair, in the engines' v2 spelling.
BTC_PAIR: Final = "BTC/USD"

CONFIDENCE: Final = 0.95

#: Below this many closed trades no per-trade interval is reported (spec 138 step 4, and
#: `phase-7-findings.md` §8: an interval over a handful of outcomes describes the handful).
MIN_TRADES_FOR_INTERVAL: Final = 10

#: The guard chain then the opportunity chain, in execution order (`engine-contracts.md`,
#: "Fixed engine order"). A test holds this equal to `bootstrap.py`'s chains, so the funnel's
#: order cannot drift from the registry's.
CHAIN_ORDER: Final[tuple[str, ...]] = (
    "exchange",
    "market_data_recorder",
    "market_sensor",
    "data_guard",
    "safety",
    "feature",
    "macro_context",
    "scout",
    "regime",
    "anomaly",
    "prediction",
    "order_book",
    "cost",
    "risk",
    "adaptive_router",
    "skeptic",
    "decision",
    "execution",
)

#: Engines 13 and 8 refusing a vector with an unfilled lookback (prerequisite 6).
INCOMPLETE_VECTOR_CODES: Final = ("anomaly_inputs_incomplete", "prediction_inputs_incomplete")

OVERLAP_STATEMENT: Final = (
    "Overlapping holds are not independent: consecutive days share open positions and "
    "concurrent trades move together, so the true interval is wider than any interval "
    "reported here."
)
JOIN_STATEMENT: Final = (
    "Positions are placed in time by opened_at and orders by placed_at. cycle_id on orders "
    "and positions is the last tick that wrote the row (prerequisite 8), so nothing here "
    "joins on (run_id, cycle_id)."
)
BASKET_STATEMENT: Final = (
    "The basket holds equal weights of the pairs the run held, over the ticks it held them, "
    "rebalanced at every tick, and cash otherwise; no fees. The held pairs bought and held "
    "over the whole window would be a different series."
)
FEW_TRADES_STATEMENT: Final = (
    "Fewer than ten closed trades: an interval would describe a handful of outcomes, not "
    "the system, so none is reported."
)


class AttributionError(RuntimeError):
    """The run cannot be attributed as it stands. Never papered over with a default."""


class PriceMarks(Protocol):
    """The last traded price at or before each moment, per pair."""

    def marks(self, pair: str, at_us: Sequence[int]) -> list[Decimal]:
        """One price per moment, in the order given. Raises when a moment has no trade."""
        ...


# --------------------------------------------------------------------------- #
# Reading the run
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunRow:
    """The columns of `runs` the report reads."""

    run_id: str
    scenario_digest: str | None
    scenario_description: str | None


@dataclass(frozen=True)
class EquityRow:
    """One tick of the equity curve: when, and the account's equity then."""

    ts: int
    equity: Decimal


@dataclass(frozen=True)
class PositionRow:
    """A position's pair and when it was held. `closed_at` is `None` while still open."""

    pair: str
    opened_at: int
    closed_at: int | None


@dataclass(frozen=True)
class TradeRow:
    """The columns of `trades` the per-trade statistics read."""

    trade_id: str
    pair: str
    opened_at: int
    closed_at: int
    outcome: str
    entry_price: Decimal
    exit_price: Decimal
    realised_pnl_pct: Decimal
    expected_move_pct: Decimal | None


@dataclass(frozen=True)
class RunData:
    """Everything the report reads from one run's database.

    Read into this module's own row types rather than the store's contracts, because
    `research/` may not import `acsoe.clients` (only `backtest.py` reaches the live side).
    Every money column the report reads is stored as exact decimal text and parsed with
    `_money`, which refuses anything that is not text.
    """

    runs: tuple[RunRow, ...]
    equity: tuple[EquityRow, ...]
    positions: tuple[PositionRow, ...]
    trades: tuple[TradeRow, ...]
    rejections: tuple[tuple[int, str, str], ...]
    """(ts, rejected_by, reason_code) of every rejection."""
    blocks: tuple[tuple[int, str], ...]
    """(ts, blocked_by) of every primary block record."""
    approvals: int


def _read_only(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise AttributionError(f"no run database at {db_path}")
    connection = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _money(value: Any, where: str) -> Decimal:
    """An exact decimal from a money column, which the schema stores as text."""
    if not isinstance(value, str):
        raise AttributionError(f"{where} is {value!r}, not the exact decimal text it must be")
    return Decimal(value)


def read_run(db_path: Path) -> RunData:
    """Every row the report needs, read once, into this module's row types."""
    connection = _read_only(db_path)
    try:
        def rows(sql: str) -> list[sqlite3.Row]:
            return list(connection.execute(sql).fetchall())

        runs = tuple(
            RunRow(
                run_id=str(r["run_id"]),
                scenario_digest=r["scenario_digest"],
                scenario_description=r["scenario_description"],
            )
            for r in rows(
                "SELECT run_id, scenario_digest, scenario_description FROM runs "
                "ORDER BY started_at, id"
            )
        )
        equity = tuple(
            EquityRow(ts=int(r["ts"]), equity=_money(r["equity"], "equity_snapshots.equity"))
            for r in rows("SELECT ts, equity FROM equity_snapshots ORDER BY ts, id")
        )
        positions = tuple(
            PositionRow(
                pair=str(r["pair"]),
                opened_at=int(r["opened_at"]),
                closed_at=None if r["closed_at"] is None else int(r["closed_at"]),
            )
            for r in rows("SELECT pair, opened_at, closed_at FROM positions ORDER BY opened_at")
        )
        trades = tuple(
            TradeRow(
                trade_id=str(r["trade_id"]),
                pair=str(r["pair"]),
                opened_at=int(r["opened_at"]),
                closed_at=int(r["closed_at"]),
                outcome=str(r["outcome"]),
                entry_price=_money(r["entry_price"], "trades.entry_price"),
                exit_price=_money(r["exit_price"], "trades.exit_price"),
                realised_pnl_pct=_money(r["realised_pnl_pct"], "trades.realised_pnl_pct"),
                expected_move_pct=(
                    None
                    if r["expected_move_pct"] is None
                    else _money(r["expected_move_pct"], "trades.expected_move_pct")
                ),
            )
            for r in rows(
                "SELECT trade_id, pair, opened_at, closed_at, outcome, entry_price, exit_price, "
                "realised_pnl_pct, expected_move_pct FROM trades ORDER BY closed_at"
            )
        )
        rejections = tuple(
            (int(r["ts"]), str(r["rejected_by"]), str(r["reason_code"]))
            for r in rows("SELECT ts, rejected_by, reason_code FROM rejections ORDER BY ts, id")
        )
        blocks = tuple(
            (int(r["ts"]), str(r["blocked_by"]))
            for r in rows(
                "SELECT ts, blocked_by FROM block_records WHERE is_primary = 1 ORDER BY ts, id"
            )
        )
        approvals = int(connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0])
    finally:
        connection.close()
    return RunData(
        runs=runs,
        equity=equity,
        positions=positions,
        trades=trades,
        rejections=rejections,
        blocks=blocks,
        approvals=approvals,
    )


# --------------------------------------------------------------------------- #
# The grid and the series on it
# --------------------------------------------------------------------------- #


def daily_grid(start_us: int, end_us: int) -> list[int]:
    """`start_us`, then every whole day after it up to `end_us`."""
    if end_us - start_us < DAY_US:
        raise AttributionError(
            "the run's window is shorter than one day, so there is no daily return to regress"
        )
    return [start_us + k * DAY_US for k in range((end_us - start_us) // DAY_US + 1)]


def _last_at_or_before(stamps: Sequence[int], values: Sequence[Any], grid: Sequence[int]) -> list[Any]:
    """The value of the last stamp at or before each grid point. Refuses a point with none."""
    out: list[Any] = []
    index = -1
    for point in grid:
        while index + 1 < len(stamps) and stamps[index + 1] <= point:
            index += 1
        if index < 0:
            raise AttributionError(
                f"no row at or before {_iso(point)}: the series does not reach back to the "
                "window's start"
            )
        out.append(values[index])
    return out


def _require_every_day_covered(stamps: Sequence[int], grid: Sequence[int]) -> None:
    """Every grid interval holds at least one equity row, so no day is carried forward."""
    index = 0
    for lower, upper in itertools.pairwise(grid):
        while index < len(stamps) and stamps[index] <= lower:
            index += 1
        if index >= len(stamps) or stamps[index] > upper:
            raise AttributionError(
                f"no equity row between {_iso(lower)} and {_iso(upper)}: the account on that "
                "day is not on disk, and a carried-forward figure would be an invented flat day"
            )


def _returns(levels: Sequence[float]) -> list[float]:
    out = []
    for before, after in itertools.pairwise(levels):
        if before <= 0:
            raise AttributionError(f"a level of {before} cannot carry a return")
        out.append(after / before - 1.0)
    return out


def basket_levels(
    ticks_us: Sequence[int], positions: Sequence[PositionRow], marks: PriceMarks
) -> list[float]:
    """The held-pairs basket's value at every tick of the run, starting at 1."""
    held_by_tick: list[list[str]] = [[] for _ in ticks_us]
    pairs: dict[str, list[int]] = {}
    for position in positions:
        closed = position.closed_at
        for i, tick in enumerate(ticks_us[:-1]):
            if position.opened_at <= tick and (closed is None or tick < closed):
                held_by_tick[i].append(position.pair)
                pairs.setdefault(position.pair, []).append(i)
    prices: dict[str, dict[int, Decimal]] = {}
    for pair, indices in pairs.items():
        wanted = sorted({ticks_us[i] for i in indices} | {ticks_us[i + 1] for i in indices})
        prices[pair] = dict(zip(wanted, marks.marks(pair, wanted), strict=True))
    levels = [1.0]
    for i in range(len(ticks_us) - 1):
        held = held_by_tick[i]
        if held:
            step = sum(
                float(prices[p][ticks_us[i + 1]] / prices[p][ticks_us[i]]) - 1.0 for p in held
            ) / len(held)
        else:
            step = 0.0
        levels.append(levels[-1] * (1.0 + step))
    return levels


# --------------------------------------------------------------------------- #
# The regression
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Regression:
    """Daily run returns on daily benchmark returns, OLS with a HAC covariance."""

    n_days: int
    alpha_daily: float
    alpha_ci: tuple[float, float]
    alpha_se_hac: float
    alpha_t: float
    alpha_p: float
    beta: float
    beta_ci: tuple[float, float]
    effective_n: float
    hac_lag: int
    lag_basis: str
    confidence: float
    significant: bool

    def describe(self) -> str:
        verdict = "significant" if self.significant else "not significant"
        return (
            f"alpha {self.alpha_daily:+.6f} a day (95% CI {self.alpha_ci[0]:+.6f} to "
            f"{self.alpha_ci[1]:+.6f}, t {self.alpha_t:.2f}, p {self.alpha_p:.3f}: {verdict}); "
            f"beta {self.beta:.4f} (95% CI {self.beta_ci[0]:.4f} to {self.beta_ci[1]:.4f}); "
            f"{self.n_days} days, effective {self.effective_n:.1f}; HAC lag {self.hac_lag} "
            f"({self.lag_basis})"
        )


def newey_west_rule(n: int) -> int:
    """`floor(4 (n/100)^(2/9))`, the Newey-West (1994) rule of thumb."""
    return math.floor(4.0 * float((n / 100.0) ** (2.0 / 9.0)))


def hold_lag(grid: Sequence[int], holds: Iterable[tuple[int, int | None]]) -> int:
    """The most grid intervals any one hold touches, less one: how far apart two daily
    returns can be and still share a position."""
    end = grid[-1]
    widest = 0
    for opened, closed in holds:
        last = end if closed is None else min(closed, end)
        if last <= grid[0] or opened >= end:
            continue
        first_day = max(0, (opened - grid[0]) // DAY_US)
        last_day = max(first_day, (last - 1 - grid[0]) // DAY_US)
        widest = max(widest, int(last_day - first_day))
    return widest


def regress(y: Sequence[float], x: Sequence[float], *, lag: int, lag_basis: str) -> Regression:
    """OLS of `y` on a constant and `x`, HAC standard errors at `lag`, t intervals."""
    import numpy as np
    import statsmodels.api as sm

    if len(y) != len(x):
        raise AttributionError(f"{len(y)} run returns against {len(x)} benchmark returns")
    n = len(y)
    if len(set(x)) < 2:
        raise AttributionError(
            "the benchmark's daily return never varies, so no beta can be told from an alpha"
        )
    if n < 3:
        raise AttributionError(f"{n} daily returns cannot carry a two-parameter regression")
    design = sm.add_constant(np.asarray(x, dtype=float), has_constant="add")
    target = np.asarray(y, dtype=float)
    hac = sm.OLS(target, design).fit(
        cov_type="HAC", cov_kwds={"maxlags": lag, "use_correction": True}, use_t=True
    )
    ols = sm.OLS(target, design).fit()
    alpha_ci, beta_ci = hac.conf_int(alpha=1.0 - CONFIDENCE)
    se_hac = float(hac.bse[0])
    se_ols = float(ols.bse[0])
    effective = float(n) if se_hac <= 0 else min(float(n), n * (se_ols / se_hac) ** 2)
    low, high = float(alpha_ci[0]), float(alpha_ci[1])
    return Regression(
        n_days=n,
        alpha_daily=float(hac.params[0]),
        alpha_ci=(low, high),
        alpha_se_hac=se_hac,
        alpha_t=float(hac.tvalues[0]),
        alpha_p=float(hac.pvalues[0]),
        beta=float(hac.params[1]),
        beta_ci=(float(beta_ci[0]), float(beta_ci[1])),
        effective_n=effective,
        hac_lag=lag,
        lag_basis=lag_basis,
        confidence=CONFIDENCE,
        significant=bool(low > 0.0 or high < 0.0),
    )


# --------------------------------------------------------------------------- #
# Per-trade statistics, coverage and the funnel
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TradeStatistics:
    count: int
    pairs: tuple[str, ...]
    outcomes: dict[str, int]
    net_mean: float | None
    net_ci: tuple[float, float] | None
    interval_note: str
    independent_clusters: int
    """Trades after merging every group of overlapping holds into one: a floor on how many
    independent outcomes the count holds."""
    expected_move_mean: float | None
    realised_move_mean: float | None
    with_expected_move: int
    per_trade: tuple[dict[str, Any], ...]


def _clusters(holds: Sequence[tuple[int, int]]) -> int:
    count = 0
    reach = None
    for opened, closed in sorted(holds):
        if reach is None or opened >= reach:
            count += 1
            reach = closed
        else:
            reach = max(reach, closed)
    return count


def trade_statistics(trades: Sequence[TradeRow]) -> TradeStatistics:
    """Net per trade is `realised_pnl_pct`: engine 22's PnL after both fees over the cost
    basis. The realised move is the gross `exit / entry - 1`, the figure engine 10's
    expected move at entry predicted."""
    nets = [float(t.realised_pnl_pct) for t in trades]
    per_trade = []
    expected: list[float] = []
    realised_with_expected: list[float] = []
    for t in trades:
        move = float(Decimal(t.exit_price) / Decimal(t.entry_price)) - 1.0
        em = None if t.expected_move_pct is None else float(t.expected_move_pct)
        if em is not None:
            expected.append(em)
            realised_with_expected.append(move)
        per_trade.append(
            {
                "trade_id": t.trade_id,
                "pair": t.pair,
                "opened_at": _iso(t.opened_at),
                "closed_at": _iso(t.closed_at),
                "outcome": str(t.outcome),
                "expected_move_pct": em,
                "realised_move_pct": move,
                "net_pct": float(t.realised_pnl_pct),
            }
        )
    net_mean = sum(nets) / len(nets) if nets else None
    net_ci: tuple[float, float] | None = None
    if len(nets) >= MIN_TRADES_FOR_INTERVAL and net_mean is not None:
        sd = math.sqrt(sum((v - net_mean) ** 2 for v in nets) / (len(nets) - 1))
        quantile = student_t_quantile(0.5 + CONFIDENCE / 2, len(nets) - 1)
        half = quantile * sd / math.sqrt(len(nets))
        net_ci = (net_mean - half, net_mean + half)
        note = (
            "95% t interval treating the trades as independent. " + OVERLAP_STATEMENT
        )
    else:
        note = FEW_TRADES_STATEMENT
    return TradeStatistics(
        count=len(trades),
        pairs=tuple(sorted({t.pair for t in trades})),
        outcomes=dict(sorted(Counter(str(t.outcome) for t in trades).items())),
        net_mean=net_mean,
        net_ci=net_ci,
        interval_note=note,
        independent_clusters=_clusters([(t.opened_at, t.closed_at) for t in trades]),
        expected_move_mean=sum(expected) / len(expected) if expected else None,
        realised_move_mean=(
            sum(realised_with_expected) / len(realised_with_expected)
            if realised_with_expected
            else None
        ),
        with_expected_move=len(expected),
        per_trade=tuple(per_trade),
    )


def _bar_ticks(equity: Sequence[EquityRow], decision_bar_s: int) -> set[int]:
    bar_us = decision_bar_s * MICROS
    return {row.ts for row in equity if row.ts % bar_us == 0}


def funnel(run: RunData, decision_bar_s: int) -> list[dict[str, Any]]:
    """Stage-by-stage counts on decision bars, in the chain's order.

    A bar is a tick whose time falls on the decision-bar grid; minute ticks while exposed run
    no opportunity chain. Each stage's `refused` is the primary block records and rejections
    that stage wrote on a bar. A blocker not in `CHAIN_ORDER` is listed after it, named.
    """
    bars = _bar_ticks(run.equity, decision_bar_s)
    refused: Counter[str] = Counter()
    codes: dict[str, Counter[str]] = {}
    for ts, engine in run.blocks:
        if ts in bars:
            refused[engine] += 1
            codes.setdefault(engine, Counter())["(guard block)"] += 1
    for ts, engine, code in run.rejections:
        if ts in bars:
            refused[engine] += 1
            codes.setdefault(engine, Counter())[code] += 1
    stages: list[dict[str, Any]] = [
        {"stage": "decision bars", "refused": 0, "survivors": len(bars), "reasons": {}}
    ]
    survivors = len(bars)
    order = list(CHAIN_ORDER) + sorted(set(refused) - set(CHAIN_ORDER))
    for engine in order:
        if engine not in refused:
            continue
        survivors -= refused[engine]
        stages.append(
            {
                "stage": engine if engine in CHAIN_ORDER else f"{engine} (not in the chain order)",
                "refused": refused[engine],
                "survivors": survivors,
                "reasons": dict(sorted(codes[engine].items())),
            }
        )
    stages.append({"stage": "approved (entry placed)", "count": run.approvals})
    stages.append({"stage": "filled (position opened)", "count": len(run.positions)})
    stages.append({"stage": "closed (trade)", "count": len(run.trades)})
    return stages


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AttributionReport:
    run_ids: tuple[str, ...]
    scenario_digest: str | None
    scenario_description: dict[str, Any] | None
    window_start_us: int
    window_end_us: int
    grid_us: tuple[int, ...]
    tail_excluded_s: int
    equity_levels: tuple[str, ...]
    btc_levels: tuple[str, ...]
    basket_levels: tuple[float, ...]
    flat_days: int
    btc: Regression
    basket: Regression | None
    """`None` when the basket's return never varies: a run that held nothing has no basket
    to regress on, and `basket_note` says so rather than a degenerate fit."""
    basket_note: str
    trades: TradeStatistics
    coverage: dict[str, Any]
    funnel: tuple[dict[str, Any], ...]
    statements: tuple[str, ...] = field(
        default=(OVERLAP_STATEMENT, JOIN_STATEMENT, BASKET_STATEMENT)
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["window"] = {
            "start": _iso(self.window_start_us),
            "end": _iso(self.window_end_us),
            "source": "the run's first and last equity rows",
            "days": len(self.grid_us) - 1,
            "tail_excluded_s": self.tail_excluded_s,
        }
        return data

    def render(self) -> str:
        t = self.trades
        net = (
            "none"
            if t.net_mean is None
            else f"{t.net_mean:+.4%}"
            + (
                ""
                if t.net_ci is None
                else f" (95% CI {t.net_ci[0]:+.4%} to {t.net_ci[1]:+.4%})"
            )
        )
        lines = [
            f"run {', '.join(self.run_ids)}; scenario {self.scenario_digest or 'none recorded'}",
            (
                f"window {_iso(self.window_start_us)} to {_iso(self.window_end_us)} "
                f"(the run's own), {len(self.grid_us) - 1} daily returns, {self.flat_days} of "
                f"them flat, all regressed; {self.tail_excluded_s} s after the last whole day "
                "left off"
            ),
            "against BTC/USD buy-and-hold: " + self.btc.describe(),
            "against the held-pairs basket: "
            + (self.basket_note if self.basket is None else self.basket.describe()),
            f"trades {t.count} on {len(t.pairs)} pair(s), {t.independent_clusters} "
            f"non-overlapping cluster(s); outcomes {t.outcomes}; net per trade {net}. "
            + t.interval_note,
            f"coverage {self.coverage}",
            *self.statements,
        ]
        return "\n".join(lines)


def _run_identity(runs: Sequence[RunRow]) -> tuple[tuple[str, ...], str | None, dict[str, Any] | None]:
    if not runs:
        raise AttributionError("the database holds no runs row")
    digests = {r.scenario_digest for r in runs}
    if len(digests) != 1:
        raise AttributionError(
            f"the database's runs rows carry {len(digests)} different scenario digests; one "
            "database is one run, and a report over two scenarios would describe neither"
        )
    first = runs[0]
    description = (
        None if first.scenario_description is None else json.loads(first.scenario_description)
    )
    return tuple(r.run_id for r in runs), first.scenario_digest, description


def _coverage(
    run: RunData, description: Mapping[str, Any] | None, decision_bar_s: int
) -> dict[str, Any]:
    bars = _bar_ticks(run.equity, decision_bar_s)
    incomplete = sum(
        1 for ts, _engine, code in run.rejections if ts in bars and code in INCOMPLETE_VECTOR_CODES
    )
    partitions = description.get("partitions") if isinstance(description, Mapping) else None
    missing = partitions.get("archive_pairs_without_rules") if isinstance(partitions, Mapping) else None
    bar_us = decision_bar_s * MICROS
    first, last = run.equity[0].ts, run.equity[-1].ts
    expected = last // bar_us - (first + bar_us - 1) // bar_us + 1
    return {
        "decision_bars": len(bars),
        "decision_bars_expected": expected,
        "decision_bar_s": decision_bar_s,
        "equity_rows": len(run.equity),
        "incomplete_vector_refusals": incomplete,
        "incomplete_vector_share": (incomplete / len(bars)) if bars else None,
        "incomplete_vector_note": (
            "refusals by engines 13 and 8 for an unfilled lookback (prerequisite 6). Pairs the "
            "ranking skipped for an incomplete vector were never examined and are not counted."
        ),
        "survivorship_pairs_without_rules": None if missing is None else len(missing),
        "survivorship_note": (
            "archive pairs in the replayed partitions that the 2026 AssetPairs recording does "
            "not list (spec 127), so the replay never examined them"
            if missing is not None
            else "no scenario description on the runs row, so the count is not recorded"
        ),
    }


def attribute(db_path: Path, *, marks: PriceMarks, decision_bar_s: int) -> AttributionReport:
    """The whole report for one run's database."""
    run = read_run(db_path)
    run_ids, digest, description = _run_identity(run.runs)
    if not run.equity:
        raise AttributionError("the run wrote no equity rows, so it has no curve to attribute")
    stamps = [row.ts for row in run.equity]
    start, end = stamps[0], stamps[-1]
    grid = daily_grid(start, end)
    _require_every_day_covered(stamps, grid)
    equity = _last_at_or_before(stamps, [row.equity for row in run.equity], grid)
    btc = marks.marks(BTC_PAIR, grid)
    ticks = sorted(set(stamps))
    basket_at_ticks = basket_levels(ticks, run.positions, marks)
    basket = _last_at_or_before(ticks, basket_at_ticks, grid)

    y = _returns([float(v) for v in equity])
    holds = [(p.opened_at, p.closed_at) for p in run.positions]
    by_holds = hold_lag(grid, holds)
    rule = newey_west_rule(len(y))
    lag = max(1, by_holds, rule)
    basis = f"the larger of {by_holds} (longest hold in grid days, less one) and {rule} (Newey-West rule)"
    basket_returns = _returns(basket)
    basket_fit: Regression | None = None
    if len(set(basket_returns)) < 2:
        basket_note = (
            f"not regressed: the run held no position over any day of the window "
            f"({len(run.positions)} position(s)), so the basket was cash throughout"
        )
    else:
        basket_fit = regress(y, basket_returns, lag=lag, lag_basis=basis)
        basket_note = BASKET_STATEMENT
    return AttributionReport(
        run_ids=run_ids,
        scenario_digest=digest,
        scenario_description=description,
        window_start_us=start,
        window_end_us=end,
        grid_us=tuple(grid),
        tail_excluded_s=(end - grid[-1]) // MICROS,
        equity_levels=tuple(str(v) for v in equity),
        btc_levels=tuple(str(v) for v in btc),
        basket_levels=tuple(basket),
        flat_days=sum(1 for r in y if r == 0.0),
        btc=regress(y, _returns([float(v) for v in btc]), lag=lag, lag_basis=basis),
        basket=basket_fit,
        basket_note=basket_note,
        trades=trade_statistics(run.trades),
        coverage=_coverage(run, description, decision_bar_s),
        funnel=tuple(funnel(run, decision_bar_s)),
    )


def regress_digest(digest: Mapping[str, Any]) -> dict[str, Regression | None]:
    """Recompute both regressions from a report's own series, for spec 141's consistency check."""
    equity = [float(v) for v in digest["equity_levels"]]
    y = _returns(equity)
    lag = int(digest["btc"]["hac_lag"])
    basis = str(digest["btc"]["lag_basis"])
    basket = _returns([float(v) for v in digest["basket_levels"]])
    return {
        "btc": regress(y, _returns([float(v) for v in digest["btc_levels"]]), lag=lag, lag_basis=basis),
        "basket": None
        if len(set(basket)) < 2
        else regress(y, basket, lag=lag, lag_basis=basis),
    }


# --------------------------------------------------------------------------- #
# Marks from the replayed partitions
# --------------------------------------------------------------------------- #


class PartitionMarks:
    """Last traded prices from spec 128's weekly partitions, the ones the run replayed.

    Reads one week at a time, carrying the last trade across week boundaries, so memory is
    bounded by the largest week of the largest pair rather than by the window.
    """

    def __init__(
        self, directory: Path, *, manifest: Mapping[str, Any], archive_for: Mapping[str, str]
    ) -> None:
        self._directory = directory
        self._manifest = manifest
        self._archive_for = archive_for

    def _weeks(self, archive: str) -> list[tuple[int, str]]:
        pairs = self._manifest.get("pairs")
        entry = pairs.get(archive) if isinstance(pairs, Mapping) else None
        weeks = entry.get("weeks") if isinstance(entry, Mapping) else None
        if not isinstance(weeks, Mapping):
            raise AttributionError(f"the partition manifest lists no weeks for {archive}")
        out = []
        for week, rows in weeks.items():
            if int(rows) > 0:
                start = datetime.fromisoformat(str(week)).replace(tzinfo=UTC)
                out.append((int(start.timestamp()), start.strftime("%Y-%m-%d")))
        return sorted(out)

    def marks(self, pair: str, at_us: Sequence[int]) -> list[Decimal]:
        import polars as pl

        archive = self._archive_for.get(pair)
        if archive is None:
            raise AttributionError(f"{pair} has no archive name in the recorded name map")
        order = sorted(range(len(at_us)), key=lambda i: at_us[i])
        wanted = [at_us[i] // MICROS for i in order]
        found: list[Decimal | None] = [None] * len(wanted)
        weeks = self._weeks(archive)
        # Start one listed week before the one holding the first moment, so the last trade
        # before a week's first trade is always in hand. Every listed week holds a trade.
        first = max(0, bisect.bisect_right([start for start, _ in weeks], wanted[0]) - 2)
        last: str | None = None
        cursor = 0
        for week_start, label in weeks[first:]:
            # Moments before this week, in weeks the manifest lists as empty, take the
            # last trade before them.
            while cursor < len(wanted) and wanted[cursor] < week_start:
                found[cursor] = None if last is None else Decimal(last)
                cursor += 1
            if cursor >= len(wanted):
                break
            frame = pl.read_parquet(self._directory / archive / f"{label}.parquet")
            stamps = [int(v) for v in frame["ts"].to_list()]
            prices = frame["price"].cast(pl.Utf8).to_list()
            while cursor < len(wanted) and wanted[cursor] < week_start + _WEEK_S:
                index = bisect.bisect_right(stamps, wanted[cursor]) - 1
                if index >= 0:
                    found[cursor] = Decimal(prices[index])
                elif last is not None:
                    found[cursor] = Decimal(last)
                cursor += 1
            if prices:
                last = prices[-1]
        while cursor < len(wanted):
            found[cursor] = None if last is None else Decimal(last)
            cursor += 1
        out: list[Decimal] = [Decimal(0)] * len(at_us)
        for position, value in zip(order, found, strict=True):
            if value is None:
                raise AttributionError(
                    f"{pair} has no trade at or before {_iso(at_us[position])} in the partitions"
                )
            out[position] = value
        return out


def _checked_json(root: Path, entry: Mapping[str, Any]) -> tuple[Path, Any]:
    path = root / str(entry["file"])
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != entry.get("sha256"):
        raise AttributionError(
            f"{path} has sha256 {actual}; the run replayed {entry.get('sha256')}. A benchmark "
            "marked from different data than the run is the quiet failure this refuses."
        )
    return path, json.loads(path.read_bytes().decode("utf-8"))


def marks_from_description(description: Mapping[str, Any], root: Path) -> PartitionMarks:
    """The partitions and the name map the run itself recorded, each checked by sha256."""
    partitions = description.get("partitions")
    if not isinstance(partitions, Mapping):
        raise AttributionError("the scenario description names no partitions")
    manifest_path, manifest = _checked_json(
        root, {"file": partitions["manifest"], "sha256": partitions.get("sha256")}
    )
    rules = description.get("pair_rules")
    files = rules.get("files") if isinstance(rules, Mapping) else None
    archive_for: dict[str, str] = {}
    for entry in files or ():
        _, document = _checked_json(root, entry)
        pairs = document.get("pairs") if isinstance(document, Mapping) else None
        if isinstance(pairs, Mapping) and all(
            isinstance(v, Mapping) and "v2_symbol" in v for v in pairs.values()
        ):
            archive_for = {str(v["v2_symbol"]): str(k) for k, v in pairs.items()}
    if not archive_for:
        raise AttributionError("no recorded name map among the scenario's pair-rule files")
    return PartitionMarks(manifest_path.parent, manifest=manifest, archive_for=archive_for)


def _iso(micros: int) -> str:
    return datetime.fromtimestamp(micros / MICROS, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m acsoe.research.attribution --db <run.sqlite>``: the report as JSON and text."""
    parser = argparse.ArgumentParser(prog="acsoe.research.attribution", description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="the run's database")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="the repository root")
    parser.add_argument("--json", type=Path, help="also write the report's JSON here")
    args = parser.parse_args(argv)
    from acsoe.platform.config import Config

    decision_bar_s = int(Config.load(args.root / "config" / "default.yaml").get(
        "timeframes.decision_bar_s"
    ))
    run = read_run(args.db)
    _, _, description = _run_identity(run.runs)
    if description is None:
        raise AttributionError("the run carries no scenario description, so its partitions are unknown")
    report = attribute(
        args.db, marks=marks_from_description(description, args.root), decision_bar_s=decision_bar_s
    )
    if args.json is not None:
        args.json.write_bytes(
            (json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")
        )
    sys.stdout.write(report.render() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
