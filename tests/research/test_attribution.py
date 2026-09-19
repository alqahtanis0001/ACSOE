"""Spec 138: alpha against both benchmarks, from the full equity curve including cash periods.

The run databases here are built through the real `StoreClient` and the real row models, so the
report reads exactly the shape engine 19 writes. The subject fabricated is the run: its equity
curve, positions and trades are planted with a known alpha and beta and then recovered.

Two planted defects the spec names are each held by a test that fails on them:

- **flat days dropped** — `test_every_day_is_regressed_flat_days_included` computes the all-days
  regression independently and requires the report to equal it;
- **a constant window** — `test_the_window_is_the_runs_own_and_the_benchmark_follows_it` plants
  a run in 2023 and requires the benchmark to be marked at exactly that run's grid.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import (
    ApprovalRow,
    BlockRecordRow,
    CashSource,
    EquitySnapshotRow,
    PositionRow,
    PositionStatus,
    RejectionRow,
    TradeOutcome,
    TradeRow,
)
from acsoe.research import attribution
from acsoe.research.attribution import (
    BTC_PAIR,
    DAY_US,
    MICROS,
    AttributionError,
    PartitionMarks,
    attribute,
)

HOUR_US = 3_600 * MICROS
TICK_US = 6 * HOUR_US
BAR_S = 900
START = datetime(2024, 7, 6, tzinfo=UTC)


def us(moment: datetime) -> int:
    return int(moment.timestamp()) * MICROS


@dataclass
class DictMarks:
    """Last-at-or-before prices from a planted tape, recording every moment asked for."""

    tapes: Mapping[str, Sequence[tuple[int, Decimal]]]
    requested: dict[str, list[int]] = field(default_factory=dict)

    def marks(self, pair: str, at_us: Sequence[int]) -> list[Decimal]:
        self.requested.setdefault(pair, []).extend(at_us)
        tape = self.tapes[pair]
        out = []
        for moment in at_us:
            before = [price for ts, price in tape if ts <= moment]
            if not before:
                raise AttributionError(f"{pair}: nothing at or before {moment}")
            out.append(before[-1])
        return out


@dataclass
class PlantedRun:
    db: Path
    grid: list[int]
    btc_returns: list[float]
    equity_returns: list[float]


def build_run(
    tmp_path: Path,
    *,
    start: datetime,
    daily_returns: Sequence[float],
    positions: Sequence[PositionRow] = (),
    trades: Sequence[TradeRow] = (),
    rejections: Sequence[RejectionRow] = (),
    blocks: Sequence[BlockRecordRow] = (),
    approvals: Sequence[ApprovalRow] = (),
    scenario: Mapping[str, object] | None = None,
    run_ids: Sequence[tuple[str, str | None]] = (("replay-planted", None),),
    extra_ticks_per_day: int = 3,
    name: str = "run.sqlite",
) -> Path:
    """A run whose equity at each day's start compounds `daily_returns`, ticking every six
    hours, with the day's level held across its intraday ticks."""
    db = tmp_path / name
    store = StoreClient(db)
    store.migrate()
    description = json.dumps(scenario, sort_keys=True) if scenario is not None else None
    for index, (run_id, digest) in enumerate(run_ids):
        store.start_run(
            run_id,
            mode="replay",
            started_at=us(start) + index,
            scenario_digest=digest if digest is not None else ("d" * 64 if scenario else None),
            scenario_description=description,
        )
    level = Decimal("10000")
    cycle = 0
    step = DAY_US // (extra_ticks_per_day + 1)
    for day in range(len(daily_returns) + 1):
        if day > 0:
            level = (level * (Decimal(1) + Decimal(repr(daily_returns[day - 1])))).quantize(
                Decimal("0.00000001")
            )
        for part in range(extra_ticks_per_day + 1 if day < len(daily_returns) else 1):
            cycle += 1
            ts = us(start) + day * DAY_US + part * step
            store.write_equity_snapshot(
                EquitySnapshotRow(
                    cycle_id=cycle,
                    run_id=run_ids[0][0],
                    ts=ts,
                    currency="USD",
                    equity=level,
                    peak_equity=level,
                    cash=level,
                    positions_value=Decimal(0),
                    unrealised_pnl=Decimal(0),
                    realised_pnl_cum=Decimal(0),
                    open_position_count=0,
                    cash_source=CashSource.CYCLE_START,
                    updated_at=ts,
                )
            )
    for row in positions:
        store.write_position(row)
    for trade in trades:
        store.write_trade(trade)
    for rejection in rejections:
        store.write_rejection(rejection)
    for block in blocks:
        store.write_block_record(block)
    for approval in approvals:
        store.write_approval(approval)
    store.close()
    return db


def btc_tape(start: datetime, returns: Sequence[float]) -> list[tuple[int, Decimal]]:
    """One BTC trade at each day's start, so the day's return is exactly `returns[day]`."""
    price = Decimal("60000")
    tape = [(us(start), price)]
    for day, r in enumerate(returns, start=1):
        price = price * (Decimal(1) + Decimal(repr(r)))
        tape.append((us(start) + day * DAY_US, price))
    return tape


def wiggle(days: int) -> list[float]:
    """Daily returns that vary, so a benchmark built from them can carry a beta."""
    return [0.001 * ((k % 4) - 1.5) for k in range(days)]


def position(pair: str, opened: int, closed: int | None, index: int = 0) -> PositionRow:
    return PositionRow(
        position_id=f"pos-{pair}-{index}",
        run_id="replay-planted",
        cycle_id=1,
        pair=pair,
        base=pair.split("/")[0],
        quote="USD",
        status=PositionStatus.OPEN if closed is None else PositionStatus.CLOSED,
        qty=Decimal("1"),
        entry_price=Decimal("100"),
        target_price=Decimal("103"),
        stop_price=Decimal("98.5"),
        timeout_at=opened + 12 * HOUR_US,
        opened_at=opened,
        closed_at=closed,
        updated_at=closed or opened,
    )


def trade(index: int, *, net: str, opened: int, closed: int, em: str | None = "0.02") -> TradeRow:
    return TradeRow(
        trade_id=f"t-{index:03d}",
        position_id=f"p-{index:03d}",
        run_id="replay-planted",
        cycle_id=index + 1,
        pair="AAA/USD" if index % 2 else "BBB/USD",
        base="AAA",
        quote="USD",
        qty=Decimal("1"),
        entry_price=Decimal("100"),
        exit_price=Decimal("100") * (Decimal(1) + Decimal(net)),
        entry_fee=Decimal(0),
        exit_fee=Decimal(0),
        opened_at=opened,
        closed_at=closed,
        outcome=TradeOutcome.TARGET if Decimal(net) > 0 else TradeOutcome.STOP,
        realised_pnl=Decimal(net) * 100,
        realised_pnl_pct=Decimal(net),
        realised_pnl_quote=Decimal(net) * 100,
        reporting_currency="USD",
        fx_rate_entry=Decimal(1),
        fx_rate_exit=Decimal(1),
        updated_at=closed,
        expected_move_pct=None if em is None else Decimal(em),
    )


def planted(
    tmp_path: Path, *, alpha: float, beta: float, days: int = 150, seed: int = 7,
    flat_every: int = 0,
) -> tuple[PlantedRun, DictMarks]:
    rng = random.Random(seed)
    x = [rng.gauss(0.0, 0.03) for _ in range(days)]
    y = []
    for k in range(days):
        if flat_every and k % flat_every == 0:
            y.append(0.0)
        else:
            y.append(alpha + beta * x[k] + rng.gauss(0.0, 0.004))
    db = build_run(tmp_path, start=START, daily_returns=y)
    grid = [us(START) + k * DAY_US for k in range(days + 1)]
    return PlantedRun(db, grid, x, y), DictMarks({BTC_PAIR: btc_tape(START, x)})


# --------------------------------------------------------------------------- #
# Recovering a planted alpha and beta, against each benchmark
# --------------------------------------------------------------------------- #


def test_a_planted_alpha_and_beta_are_recovered_against_btc(tmp_path: Path) -> None:
    run, marks = planted(tmp_path, alpha=0.002, beta=0.6)
    report = attribute(run.db, marks=marks, decision_bar_s=BAR_S)
    fit = report.btc
    assert fit.n_days == 150
    assert fit.alpha_ci[0] < 0.002 < fit.alpha_ci[1], fit.describe()
    assert fit.beta_ci[0] < 0.6 < fit.beta_ci[1], fit.describe()
    assert fit.significant is True
    assert abs(fit.alpha_daily - 0.002) < 0.001
    assert abs(fit.beta - 0.6) < 0.05


def test_the_same_series_with_the_alpha_removed_is_not_significant(tmp_path: Path) -> None:
    run, marks = planted(tmp_path, alpha=0.0, beta=0.6)
    report = attribute(run.db, marks=marks, decision_bar_s=BAR_S)
    assert report.btc.significant is False, report.btc.describe()
    assert report.btc.alpha_ci[0] < 0.0 < report.btc.alpha_ci[1]
    assert "not significant" in report.btc.describe()


def _basket_run(tmp_path: Path, *, alpha: float, beta: float) -> tuple[Path, DictMarks, list[float]]:
    """Two pairs held over planted spans of whole days. The basket's daily return is the mean
    of the held pairs' daily returns, computed here independently of the module."""
    days = 160
    rng = random.Random(11)
    pairs = ("AAA/USD", "BBB/USD")
    daily = {p: [rng.gauss(0.0, 0.04) for _ in range(days)] for p in pairs}
    spans = {"AAA/USD": [(5, 40), (70, 120)], "BBB/USD": [(20, 60), (100, 150)]}
    held = [[p for p in pairs if any(a <= k < b for a, b in spans[p])] for k in range(days)]
    basket = [sum(daily[p][k] for p in h) / len(h) if h else 0.0 for k, h in enumerate(held)]
    y = [alpha + beta * basket[k] + rng.gauss(0.0, 0.003) for k in range(days)]
    rows = [
        position(p, us(START) + a * DAY_US, us(START) + b * DAY_US, i)
        for p in pairs
        for i, (a, b) in enumerate(spans[p])
    ]
    btc = [rng.gauss(0.0, 0.03) for _ in range(days)]
    db = build_run(tmp_path, start=START, daily_returns=y, positions=rows)
    tapes = {BTC_PAIR: btc_tape(START, btc)}
    for p in pairs:
        tapes[p] = btc_tape(START, daily[p])
    return db, DictMarks(tapes), basket


def test_a_planted_alpha_and_beta_are_recovered_against_the_held_pairs_basket(
    tmp_path: Path,
) -> None:
    db, marks, _ = _basket_run(tmp_path, alpha=0.0015, beta=0.8)
    report = attribute(db, marks=marks, decision_bar_s=BAR_S)
    fit = report.basket
    assert fit.alpha_ci[0] < 0.0015 < fit.alpha_ci[1], fit.describe()
    assert fit.beta_ci[0] < 0.8 < fit.beta_ci[1], fit.describe()
    assert fit.significant is True


def test_the_basket_with_the_alpha_removed_is_not_significant(tmp_path: Path) -> None:
    db, marks, _ = _basket_run(tmp_path, alpha=0.0, beta=0.8)
    report = attribute(db, marks=marks, decision_bar_s=BAR_S)
    assert report.basket.significant is False, report.basket.describe()


def test_the_basket_holds_the_held_pairs_while_held_and_cash_otherwise(tmp_path: Path) -> None:
    """The basket's daily series equals the independent computation, cash days at zero."""
    db, marks, basket = _basket_run(tmp_path, alpha=0.0, beta=0.8)
    report = attribute(db, marks=marks, decision_bar_s=BAR_S)
    levels = report.basket_levels
    got = [after / before - 1.0 for before, after in itertools.pairwise(levels)]
    assert len(got) == len(basket)
    assert max(abs(g - b) for g, b in zip(got, basket, strict=True)) < 1e-12
    assert got[0] == 0.0 and got[160 - 1] == 0.0  # nothing held on day 0 or the last day


def test_a_position_still_open_at_the_end_is_held_to_the_end(tmp_path: Path) -> None:
    days = 4
    returns = [0.01, 0.02, -0.01, 0.03]
    db = build_run(
        tmp_path,
        start=START,
        daily_returns=[0.0] * days,
        positions=[position("AAA/USD", us(START) + 2 * DAY_US, None)],
    )
    marks = DictMarks({BTC_PAIR: btc_tape(START, returns), "AAA/USD": btc_tape(START, returns)})
    levels = attribute(db, marks=marks, decision_bar_s=BAR_S).basket_levels
    got = [after / before - 1.0 for before, after in itertools.pairwise(levels)]
    assert got == pytest.approx([0.0, 0.0, -0.01, 0.03], abs=1e-12)


# --------------------------------------------------------------------------- #
# Planted defect 1: flat days dropped
# --------------------------------------------------------------------------- #


def test_every_day_is_regressed_flat_days_included(tmp_path: Path) -> None:
    run, marks = planted(tmp_path, alpha=0.001, beta=0.5, flat_every=3)
    report = attribute(run.db, marks=marks, decision_bar_s=BAR_S)
    flat = sum(1 for r in run.equity_returns if r == 0.0)
    assert flat == 50
    assert report.flat_days == flat
    assert report.btc.n_days == len(run.equity_returns) == 150
    # The all-days regression, computed independently of the module.
    design = np.column_stack([np.ones(150), np.asarray(run.btc_returns)])
    levels = [float(v) for v in report.equity_levels]
    y = [after / before - 1.0 for before, after in itertools.pairwise(levels)]
    (alpha, beta), *_ = np.linalg.lstsq(design, np.asarray(y), rcond=None)
    assert report.btc.alpha_daily == pytest.approx(alpha, rel=1e-9, abs=1e-12)
    assert report.btc.beta == pytest.approx(beta, rel=1e-9)
    # And the regression over the active days alone is a different answer, so the check
    # above can tell the two apart.
    active = [k for k in range(150) if run.equity_returns[k] != 0.0]
    (alpha_active, _), *_ = np.linalg.lstsq(
        design[active], np.asarray(y)[active], rcond=None
    )
    assert abs(alpha_active - alpha) > 1e-4


def test_a_grid_day_with_no_equity_row_is_refused_not_carried_forward(tmp_path: Path) -> None:
    db = build_run(tmp_path, start=START, daily_returns=[0.0] * 5)
    import sqlite3

    connection = sqlite3.connect(db)
    lower, upper = us(START) + 2 * DAY_US, us(START) + 3 * DAY_US
    connection.execute("DELETE FROM equity_snapshots WHERE ts > ? AND ts <= ?", (lower, upper))
    connection.commit()
    connection.close()
    marks = DictMarks({BTC_PAIR: btc_tape(START, wiggle(5))})
    with pytest.raises(AttributionError, match="no equity row between"):
        attribute(db, marks=marks, decision_bar_s=BAR_S)


# --------------------------------------------------------------------------- #
# Planted defect 2: a constant window
# --------------------------------------------------------------------------- #


def test_the_window_is_the_runs_own_and_the_benchmark_follows_it(tmp_path: Path) -> None:
    """A run of 17 days starting 2023-03-10 06:00, far from the committed six months."""
    start = datetime(2023, 3, 10, 6, tzinfo=UTC)
    returns = [0.001 * ((k % 5) - 2) for k in range(17)]
    db = build_run(tmp_path, start=start, daily_returns=returns)
    marks = DictMarks({BTC_PAIR: btc_tape(start, [0.002 * ((k % 3) - 1) for k in range(17)])})
    report = attribute(db, marks=marks, decision_bar_s=BAR_S)
    grid = [us(start) + k * DAY_US for k in range(18)]
    assert marks.requested[BTC_PAIR] == grid
    assert list(report.grid_us) == grid
    assert report.window_start_us == us(start)
    assert report.window_end_us == us(start + timedelta(days=17))
    assert report.to_dict()["window"]["start"] == "2023-03-10T06:00:00Z"
    assert report.to_dict()["window"]["days"] == 17


def test_the_tail_that_does_not_complete_a_day_is_reported(tmp_path: Path) -> None:
    db = build_run(tmp_path, start=START, daily_returns=[0.0] * 3)
    import sqlite3

    connection = sqlite3.connect(db)
    last = us(START) + 3 * DAY_US + 5 * HOUR_US
    connection.execute(
        "INSERT INTO equity_snapshots (cycle_id, run_id, ts, currency, equity, peak_equity, "
        "cash, positions_value, unrealised_pnl, realised_pnl_cum, open_position_count, "
        "updated_at) VALUES (999, 'replay-planted', ?, 'USD', '10000', '10000', '10000', '0', "
        "'0', '0', 0, ?)",
        (last, last),
    )
    connection.commit()
    connection.close()
    marks = DictMarks({BTC_PAIR: btc_tape(START, wiggle(3))})
    report = attribute(db, marks=marks, decision_bar_s=BAR_S)
    assert report.window_end_us == last
    assert len(report.grid_us) == 4
    assert report.tail_excluded_s == 5 * 3600


# --------------------------------------------------------------------------- #
# The HAC lag, per-trade statistics, coverage and the funnel
# --------------------------------------------------------------------------- #


def test_the_hac_lag_is_the_longer_of_the_hold_span_and_the_rule_and_says_so(
    tmp_path: Path,
) -> None:
    run, marks = planted(tmp_path, alpha=0.0, beta=0.5)
    report = attribute(run.db, marks=marks, decision_bar_s=BAR_S)
    assert report.btc.hac_lag == attribution.newey_west_rule(150) == 4
    grid = [us(START) + k * DAY_US for k in range(11)]
    assert attribution.hold_lag(grid, [(grid[1] + HOUR_US, grid[1] + 7 * HOUR_US)]) == 0
    assert attribution.hold_lag(grid, [(grid[1] + 20 * HOUR_US, grid[2] + 2 * HOUR_US)]) == 1
    assert attribution.hold_lag(grid, [(grid[1], grid[8])]) == 6
    assert attribution.hold_lag(grid, [(grid[3], None)]) == 6
    assert "Newey-West rule" in report.btc.lag_basis


def test_a_long_hold_raises_the_lag_above_the_rule(tmp_path: Path) -> None:
    returns = [0.0] * 20
    db = build_run(
        tmp_path, start=START, daily_returns=returns,
        positions=[position("AAA/USD", us(START) + DAY_US, us(START) + 9 * DAY_US)],
    )
    tape = btc_tape(START, [0.001 * (k % 4) for k in range(20)])
    marks = DictMarks({BTC_PAIR: tape, "AAA/USD": tape})
    report = attribute(db, marks=marks, decision_bar_s=BAR_S)
    assert report.btc.hac_lag == 7
    assert report.btc.lag_basis.startswith("the larger of 7 ")


def _trades(n: int) -> list[TradeRow]:
    base = us(START)
    rows = []
    for i in range(n):
        opened = base + i * 12 * HOUR_US
        rows.append(
            trade(i, net="0.01" if i % 3 else "-0.005", opened=opened, closed=opened + 6 * HOUR_US)
        )
    return rows


def test_below_ten_trades_no_interval_is_reported_and_the_reason_is_given(tmp_path: Path) -> None:
    stats = attribution.trade_statistics(_trades(9))
    assert stats.count == 9
    assert stats.net_ci is None
    assert stats.interval_note == attribution.FEW_TRADES_STATEMENT


def test_at_ten_trades_the_interval_states_that_overlapping_holds_are_not_independent() -> None:
    stats = attribution.trade_statistics(_trades(10))
    assert stats.net_ci is not None
    assert stats.net_ci[0] < stats.net_mean < stats.net_ci[1]  # type: ignore[operator]
    assert attribution.OVERLAP_STATEMENT in stats.interval_note
    nets = [0.01 if i % 3 else -0.005 for i in range(10)]
    assert stats.net_mean == pytest.approx(sum(nets) / 10)
    assert stats.outcomes == {"stop": 4, "target": 6}
    assert stats.pairs == ("AAA/USD", "BBB/USD")


def test_overlapping_trades_count_as_one_cluster() -> None:
    base = us(START)
    rows = [
        trade(0, net="0.01", opened=base, closed=base + 6 * HOUR_US),
        trade(1, net="0.01", opened=base + HOUR_US, closed=base + 8 * HOUR_US),
        trade(2, net="0.01", opened=base + 7 * HOUR_US, closed=base + 9 * HOUR_US),
        trade(3, net="0.01", opened=base + 10 * HOUR_US, closed=base + 11 * HOUR_US),
    ]
    assert attribution.trade_statistics(rows).independent_clusters == 2


def test_the_expected_move_sits_beside_the_realised_move() -> None:
    base = us(START)
    rows = [
        trade(0, net="0.03", opened=base, closed=base + HOUR_US, em="0.02"),
        trade(1, net="-0.015", opened=base + 2 * HOUR_US, closed=base + 3 * HOUR_US, em="0.04"),
        trade(2, net="0.01", opened=base + 4 * HOUR_US, closed=base + 5 * HOUR_US, em=None),
    ]
    stats = attribution.trade_statistics(rows)
    assert stats.with_expected_move == 2
    assert stats.expected_move_mean == pytest.approx(0.03)
    assert stats.realised_move_mean == pytest.approx((0.03 - 0.015) / 2)
    assert [t["expected_move_pct"] for t in stats.per_trade] == [0.02, 0.04, None]


def test_the_funnel_is_in_the_chains_order_and_counts_bars_only(tmp_path: Path) -> None:
    base = us(START)
    bar = BAR_S * MICROS

    def rejection(ts: int, engine: str, code: str) -> RejectionRow:
        return RejectionRow(
            cycle_id=ts // bar, run_id="replay-planted", ts=ts, pair="AAA/USD",
            rejected_by=engine, reason_code=code, reason="planted", updated_at=ts,
        )

    rejections = [
        rejection(base + 0 * DAY_US, "cost", "net_edge_below_hurdle"),
        rejection(base + 1 * DAY_US, "anomaly", "anomaly_inputs_incomplete"),
        rejection(base + 2 * DAY_US, "prediction", "prediction_inputs_incomplete"),
        rejection(base + 3 * DAY_US, "cost", "net_edge_below_hurdle"),
        rejection(base + 6 * HOUR_US + 60 * MICROS, "cost", "off_the_bar"),  # a minute tick
    ]
    blocks = [
        BlockRecordRow(
            cycle_id=9, run_id="replay-planted", ts=base + 4 * DAY_US, blocked_by="data_guard",
            block_reason="stale", is_primary=True, status="BLOCK", updated_at=base,
        )
    ]
    db = build_run(
        tmp_path, start=START, daily_returns=[0.0] * 6, rejections=rejections, blocks=blocks,
        scenario={"partitions": {"archive_pairs_without_rules": ["AAAUSD", "CCCUSD"]}},
    )
    report = attribute(
        db, marks=DictMarks({BTC_PAIR: btc_tape(START, wiggle(6))}), decision_bar_s=BAR_S
    )
    stages = [s["stage"] for s in report.funnel]
    assert stages == [
        "decision bars", "data_guard", "anomaly", "prediction", "cost",
        "approved (entry placed)", "filled (position opened)", "closed (trade)",
    ]
    bars = report.funnel[0]["survivors"]
    assert bars == 25  # six days of four six-hour ticks, plus the last
    assert report.funnel[4]["refused"] == 2  # the minute tick's rejection is not a bar's
    assert report.funnel[4]["survivors"] == bars - 5
    assert report.coverage["incomplete_vector_refusals"] == 2
    assert report.coverage["incomplete_vector_share"] == pytest.approx(2 / 25)
    assert report.coverage["survivorship_pairs_without_rules"] == 2
    assert report.scenario_digest == "d" * 64


def test_the_chain_order_is_the_registrys() -> None:
    from acsoe import bootstrap

    names = [engine.name for engine in (*bootstrap.GUARD_CHAIN, *bootstrap.OPPORTUNITY_CHAIN)]
    assert tuple(names) == attribution.CHAIN_ORDER


# --------------------------------------------------------------------------- #
# The run's identity, read-only, and the digest recomputation
# --------------------------------------------------------------------------- #


def test_the_database_is_not_written(tmp_path: Path) -> None:
    run, marks = planted(tmp_path, alpha=0.0, beta=0.5, days=20)
    before = hashlib.sha256(run.db.read_bytes()).hexdigest()
    attribute(run.db, marks=marks, decision_bar_s=BAR_S)
    assert hashlib.sha256(run.db.read_bytes()).hexdigest() == before


def test_two_scenarios_in_one_database_are_refused(tmp_path: Path) -> None:
    db = build_run(
        tmp_path, start=START, daily_returns=[0.0] * 3, scenario={"k": 1},
        run_ids=(("replay-a", "a" * 64), ("replay-a-resumed", "b" * 64)),
    )
    with pytest.raises(AttributionError, match="2 different scenario digests"):
        attribute(db, marks=DictMarks({BTC_PAIR: btc_tape(START, wiggle(3))}), decision_bar_s=BAR_S)


def test_a_resumed_run_under_one_scenario_is_one_report(tmp_path: Path) -> None:
    db = build_run(
        tmp_path, start=START, daily_returns=[0.0] * 3, scenario={"k": 1},
        run_ids=(("replay-a", "a" * 64), ("replay-a-resumed", "a" * 64)),
    )
    report = attribute(
        db, marks=DictMarks({BTC_PAIR: btc_tape(START, wiggle(3))}), decision_bar_s=BAR_S
    )
    assert report.run_ids == ("replay-a", "replay-a-resumed")


def test_the_regressions_recompute_from_the_reports_own_series(tmp_path: Path) -> None:
    db, marks, _ = _basket_run(tmp_path, alpha=0.001, beta=0.8)
    report = attribute(db, marks=marks, decision_bar_s=BAR_S)
    digest = json.loads(json.dumps(report.to_dict()))
    again = attribution.regress_digest(digest)
    assert again["btc"] == report.btc
    assert again["basket"] == report.basket


# --------------------------------------------------------------------------- #
# Marks from real partitions: the seam with no double in it
# --------------------------------------------------------------------------- #


def _partitions(tmp_path: Path, weeks: Mapping[str, Sequence[tuple[int, str]]]) -> tuple[Path, dict[str, object]]:
    directory = tmp_path / "trades_weekly"
    (directory / "XBTUSD").mkdir(parents=True)
    manifest_weeks: dict[str, int] = {}
    for label, rows in weeks.items():
        manifest_weeks[label] = len(rows)
        if rows:
            pl.DataFrame(
                {
                    "ts": [ts for ts, _ in rows],
                    "price": [price for _, price in rows],
                    "volume": ["0.1"] * len(rows),
                }
            ).write_parquet(directory / "XBTUSD" / f"{label}.parquet")
    manifest = {"pairs": {"XBTUSD": {"weeks": manifest_weeks}}}
    (directory / "manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    return directory, manifest


def test_partition_marks_take_the_last_trade_at_or_before_and_carry_across_an_empty_week(
    tmp_path: Path,
) -> None:
    w0 = int(datetime(2024, 7, 6, tzinfo=UTC).timestamp())
    week = 7 * 86_400
    directory, manifest = _partitions(
        tmp_path,
        {
            "2024-07-06": [(w0 + 100, "60000.1"), (w0 + 5000, "60100.2")],
            "2024-07-13": [],
            "2024-07-20": [(w0 + 2 * week + 50, "59000.0")],
        },
    )
    marks = PartitionMarks(directory, manifest=manifest, archive_for={BTC_PAIR: "XBTUSD"})
    at = [w0 + 5000, w0 + 100, w0 + 4999, w0 + week + 10, w0 + 2 * week + 49, w0 + 2 * week + 50]
    got = marks.marks(BTC_PAIR, [s * MICROS for s in at])
    assert got == [
        Decimal("60100.2"), Decimal("60000.1"), Decimal("60000.1"), Decimal("60100.2"),
        Decimal("60100.2"), Decimal("59000.0"),
    ]
    with pytest.raises(AttributionError, match="no trade at or before"):
        marks.marks(BTC_PAIR, [(w0 + 99) * MICROS])
    with pytest.raises(AttributionError, match="no archive name"):
        marks.marks("ETH/USD", [w0 * MICROS])


def test_marks_come_only_from_the_files_the_run_replayed(tmp_path: Path) -> None:
    directory, _ = _partitions(tmp_path, {"2024-07-06": [(1_720_224_100, "1.0")]})
    names = tmp_path / "pair_names.json"
    names.write_bytes(
        json.dumps({"pairs": {"XBTUSD": {"rest_key": "XXBTZUSD", "v2_symbol": BTC_PAIR}}}).encode()
    )
    manifest = directory / "manifest.json"

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    description: dict[str, object] = {
        "partitions": {"manifest": manifest.relative_to(tmp_path).as_posix(), "sha256": sha(manifest)},
        "pair_rules": {"files": [{"file": "pair_names.json", "sha256": sha(names)}]},
    }
    marks = attribution.marks_from_description(description, tmp_path)
    assert marks.marks(BTC_PAIR, [1_720_224_200 * MICROS]) == [Decimal("1.0")]
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(AttributionError, match="the run replayed"):
        attribution.marks_from_description(description, tmp_path)


def test_the_report_renders_both_benchmarks_and_every_statement(tmp_path: Path) -> None:
    run, marks = planted(tmp_path, alpha=0.001, beta=0.5, days=30)
    text = attribute(run.db, marks=marks, decision_bar_s=BAR_S).render()
    assert "against BTC/USD buy-and-hold" in text
    assert "against the held-pairs basket" in text
    assert "(the run's own)" in text
    for statement in (
        attribution.OVERLAP_STATEMENT, attribution.JOIN_STATEMENT, attribution.BASKET_STATEMENT
    ):
        assert statement in text



def test_a_run_that_held_nothing_reports_no_basket_fit_and_says_why(tmp_path: Path) -> None:
    run, marks = planted(tmp_path, alpha=0.0, beta=0.5, days=20)
    report = attribute(run.db, marks=marks, decision_bar_s=BAR_S)
    assert report.basket is None
    assert report.basket_note.startswith("not regressed: the run held no position")
    assert report.basket_note in report.render()
    assert attribution.regress_digest(json.loads(json.dumps(report.to_dict())))["basket"] is None


def test_a_benchmark_that_never_moves_is_refused_rather_than_fitted() -> None:
    with pytest.raises(AttributionError, match="never varies"):
        attribution.regress([0.01, 0.02, 0.0, 0.01], [0.0] * 4, lag=1, lag_basis="test")


def test_the_realised_move_is_the_gross_price_move_not_the_net_after_fees() -> None:
    """Engine 10's expected move is a gross price move, so it is compared with one."""
    base = us(START)
    row = trade(0, net="0.02", opened=base, closed=base + HOUR_US).model_copy(
        update={"entry_fee": Decimal("0.4"), "exit_fee": Decimal("0.8"),
                "realised_pnl_pct": Decimal("0.008")}
    )
    stats = attribution.trade_statistics([row])
    assert stats.per_trade[0]["realised_move_pct"] == pytest.approx(0.02)
    assert stats.per_trade[0]["net_pct"] == pytest.approx(0.008)
    assert stats.net_mean == pytest.approx(0.008)


def test_the_effective_sample_size_is_the_hac_ratio_capped_at_n(tmp_path: Path) -> None:
    import statsmodels.api as sm

    run, marks = planted(tmp_path, alpha=0.001, beta=0.5)
    report = attribute(run.db, marks=marks, decision_bar_s=BAR_S)
    levels = [float(v) for v in report.equity_levels]
    y = np.asarray([after / before - 1.0 for before, after in itertools.pairwise(levels)])
    design = sm.add_constant(np.asarray(run.btc_returns))
    se_ols = sm.OLS(y, design).fit().bse[0]
    se_hac = report.btc.alpha_se_hac
    assert report.btc.effective_n == pytest.approx(min(150.0, 150 * (se_ols / se_hac) ** 2))
    assert 0 < report.btc.effective_n <= 150


def test_the_reader_cannot_write(tmp_path: Path) -> None:
    import sqlite3

    run, _ = planted(tmp_path, alpha=0.0, beta=0.5, days=3)
    connection = attribution._read_only(run.db)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM equity_snapshots")
    finally:
        connection.close()


def test_the_basket_earns_from_the_opening_tick_to_the_closing_tick_and_no_further(
    tmp_path: Path,
) -> None:
    """Held over (opened_at, closed_at]: the move in the first interval after the open counts,
    and the move in the interval after the close does not."""
    opened = us(START) + DAY_US + TICK_US  # a tick, six hours into day 1
    closed = opened + TICK_US
    db = build_run(
        tmp_path, start=START, daily_returns=[0.0] * 3,
        positions=[position("AAA/USD", opened, closed)],
    )
    tape = [
        (us(START), Decimal("100")),
        (opened + 1, Decimal("110")),  # inside the held interval: +10%
        (closed + 1, Decimal("121")),  # after the close: not the basket's
    ]
    marks = DictMarks({BTC_PAIR: btc_tape(START, wiggle(3)), "AAA/USD": tape})
    levels = attribute(db, marks=marks, decision_bar_s=BAR_S).basket_levels
    assert levels[2] / levels[1] - 1.0 == pytest.approx(0.10, abs=1e-12)
    assert levels[1] == 1.0 and levels[3] == pytest.approx(levels[2], abs=1e-12)


def test_the_coverage_says_how_many_decision_bars_the_window_holds_and_how_many_have_a_row(
    tmp_path: Path,
) -> None:
    """Every bar of the window should carry an equity row, flat ones included; the report
    states both counts so a digest can be checked for a missing tick."""
    db = build_run(tmp_path, start=START, daily_returns=wiggle(4), extra_ticks_per_day=95)
    marks = DictMarks({BTC_PAIR: btc_tape(START, wiggle(4))})
    coverage = attribute(db, marks=marks, decision_bar_s=BAR_S).coverage
    assert coverage["decision_bars_expected"] == 4 * 96 + 1
    assert coverage["decision_bars"] == 4 * 96 + 1
    assert coverage["equity_rows"] == 4 * 96 + 1
    # Six-hourly ticks leave three bars in four without a row, and the counts say so.
    sparse = build_run(tmp_path, start=START, daily_returns=wiggle(4), name="sparse.sqlite")
    coverage = attribute(sparse, marks=marks, decision_bar_s=BAR_S).coverage
    assert coverage["decision_bars_expected"] == 4 * 96 + 1
    assert coverage["decision_bars"] == 4 * 4 + 1


def test_a_money_column_that_is_not_text_is_refused() -> None:
    assert attribution._money("0.0125", "x") == Decimal("0.0125")
    with pytest.raises(AttributionError, match="not the exact decimal text"):
        attribution._money(0.0125, "equity_snapshots.equity")


def test_attribution_reaches_neither_core_nor_clients() -> None:
    """The research boundary, asserted here too so the reason travels with the module."""
    import ast

    tree = ast.parse(Path(attribution.__file__).read_text(encoding="utf-8"))
    imported = [
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in (node.names if isinstance(node, ast.Import) else [None])  # type: ignore[list-item]
        if not isinstance(node, ast.ImportFrom) or node.module
    ]
    assert not [m for m in imported if m and m.startswith(("acsoe.core", "acsoe.clients"))]


def test_trades_are_read_from_the_database_with_their_economics(tmp_path: Path) -> None:
    """The store-to-report path for trades, with no double: what engine 19 wrote is what the
    statistics use, including the expected move at entry and a trade with none recorded."""
    base = us(START)
    rows = [
        trade(0, net="0.03", opened=base, closed=base + HOUR_US, em="0.021"),
        trade(1, net="-0.015", opened=base + 2 * HOUR_US, closed=base + 3 * HOUR_US, em=None),
    ]
    _, marks = planted(tmp_path, alpha=0.0, beta=0.5, days=5)
    db = build_run(tmp_path, start=START, daily_returns=wiggle(5), trades=rows, name="t.sqlite")
    stats = attribute(db, marks=marks, decision_bar_s=BAR_S).trades
    assert stats.count == 2
    assert stats.with_expected_move == 1
    assert stats.expected_move_mean == pytest.approx(0.021)
    assert stats.outcomes == {"stop": 1, "target": 1}
    assert [t["net_pct"] for t in stats.per_trade] == pytest.approx([0.03, -0.015])
    assert [t["realised_move_pct"] for t in stats.per_trade] == pytest.approx([0.03, -0.015])
