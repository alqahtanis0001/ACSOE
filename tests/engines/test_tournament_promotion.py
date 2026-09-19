"""Spec 139 — engine 20's promotion gate, against a real `StoreClient`.

The bar's arithmetic is held to its worked example and to outside references in
`tests/modelling/test_promotion.py`. These tests are about the engine: that it reads the run's
closed trades through the store rather than a double, computes each trade's net return from
the columns engine 19 wrote, takes N from the committed ledger's count, writes exactly one
verdict row whatever the verdict, and refuses — writing nothing — when a verdict would describe
something other than the run.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.store.client import StoreClient
from acsoe.clients.store.contracts import TradeOutcome, TradeRow
from acsoe.core.contracts import EngineStatus
from acsoe.engines.tournament.contracts import (
    CHAIN_RUN_MODEL_ID,
    REASON_PROMOTION_BAD_TRADE,
    REASON_PROMOTION_LOWER_BOUND,
    REASON_PROMOTION_NO_LEDGER,
    REASON_PROMOTION_TOO_FEW_TRADES,
)
from acsoe.engines.tournament.engine import TournamentEngine

ROOT = Path(__file__).resolve().parents[2]
COMMITTED_LEDGER = ROOT / "docs" / "dataset" / "phase-7-trial-ledger.json"
RUN_ID = "replay-promotion-test"
JUDGED_AT = datetime(2026, 9, 20, 9, 30, tzinfo=UTC)
MINUTE = 60_000_000
ENTRY = Decimal("100")
QTY = Decimal("10")

#: Fifteen non-overlapping trades whose unwidened 95% bound is above zero and whose
#: Bonferroni-widened bound at the ledger's count is not. The same series as
#: `tests/modelling/test_promotion.py`, as net returns on a 1,000 notional.
HAIRCUT_RETURNS = (
    "0.004", "-0.002", "0.006", "0.001", "0.003", "-0.001", "0.005", "0.002", "0.000", "0.004",
    "0.003", "-0.002", "0.006", "0.001", "0.002",
)


@pytest.fixture
def store(migrated_db: Path) -> Any:
    client = StoreClient(migrated_db)
    try:
        yield client
    finally:
        client.close()


def trade(index: int, net: str, *, opened: int, closed: int, quote: str = "USD") -> TradeRow:
    """A closed trade whose `realised_pnl` is `net` of a 1,000 entry notional."""
    realised = Decimal(net) * QTY * ENTRY
    return TradeRow(
        trade_id=f"t-{index:03d}",
        position_id=f"p-{index:03d}",
        run_id=RUN_ID,
        cycle_id=index + 1,
        pair=f"X{index}/{quote}",
        base=f"X{index}",
        quote=quote,
        qty=QTY,
        entry_price=ENTRY,
        exit_price=ENTRY,
        entry_fee=Decimal("0"),
        exit_fee=Decimal("0"),
        opened_at=opened,
        closed_at=closed,
        outcome=TradeOutcome.TARGET if Decimal(net) > 0 else TradeOutcome.STOP,
        realised_pnl=realised,
        realised_pnl_pct=Decimal(net),
        realised_pnl_quote=realised,
        reporting_currency="USD",
        fx_rate_entry=Decimal("1"),
        fx_rate_exit=Decimal("1"),
        updated_at=closed,
    )


def write_haircut_run(store: Any) -> None:
    start = 1_720_000_000_000_000
    for index, net in enumerate(HAIRCUT_RETURNS):
        opened = start + index * 100 * MINUTE
        store.write_trade(trade(index, net, opened=opened, closed=opened + 10 * MINUTE))


def ledger(tmp_path: Path, count: int) -> Path:
    """A ledger in the builder's shape with `count` rows. Fabricated subject, real reader."""
    path = tmp_path / f"ledger-{count}.json"
    rows = [{"family": "test", "source": "t", "locator": str(n), "configuration": "c",
             "statistic": "s"} for n in range(count)]
    path.write_bytes(json.dumps({"trial_count": count, "trials": rows}).encode("utf-8"))
    return path


def judge(engine_context: Any, store: Any, ledger_path: Path | None) -> Any:
    object.__setattr__(engine_context.clients, "store", store)
    context = dataclasses.replace(engine_context, now=JUDGED_AT)
    engine = TournamentEngine(promote_run_id=RUN_ID, ledger_path=ledger_path)
    return engine.process(context, {})


def verdict_rows(store: Any) -> Any:
    return store.leaderboard_entries(model_id=CHAIN_RUN_MODEL_ID, model_version=RUN_ID, fold=None)


def committed_count() -> int:
    return int(json.loads(COMMITTED_LEDGER.read_bytes().decode("utf-8"))["trial_count"])


# --------------------------------------------------------------------------- #
# Spec 139's Check When Done, through the real engine
# --------------------------------------------------------------------------- #


def test_the_haircut_failing_model_is_rejected_at_the_committed_ledgers_count(
    engine_context: Any, store: Any
) -> None:
    write_haircut_run(store)
    result = judge(engine_context, store, COMMITTED_LEDGER)
    assert result.status is EngineStatus.OK, result.reason
    data = result.data
    assert data["trial_count"] == committed_count()
    assert data["promoted"] is False
    assert data["promotion_reason_code"] == REASON_PROMOTION_LOWER_BOUND
    assert data["trades_judged"] == 15
    assert data["lower_bound"] <= 0
    rows = verdict_rows(store)
    assert len(rows) == 1
    assert rows[0].promoted is False
    notes = json.loads(rows[0].notes)
    assert notes["reason_code"] == REASON_PROMOTION_LOWER_BOUND
    assert notes["trial_count"] == committed_count()


def test_the_same_model_at_one_trial_is_promoted(
    engine_context: Any, store: Any, tmp_path: Path
) -> None:
    write_haircut_run(store)
    result = judge(engine_context, store, ledger(tmp_path, 1))
    assert result.status is EngineStatus.OK, result.reason
    assert result.data["promoted"] is True
    assert result.data["promotion_reason_code"] is None
    assert result.data["lower_bound"] > 0
    (row,) = verdict_rows(store)
    assert row.promoted is True
    assert json.loads(row.notes)["reason_code"] is None


def test_each_trades_net_return_is_realised_pnl_over_the_entry_notional(
    engine_context: Any, store: Any, tmp_path: Path
) -> None:
    """Recomputed here from the rows, not read back from `realised_pnl_pct`, which a mutated
    row could disagree with."""
    write_haircut_run(store)
    # Poison the percentage column: the gate must not read it.
    for index, net in enumerate(HAIRCUT_RETURNS):
        row = trade(index, net, opened=0, closed=0)
        stored = next(
            t for t in store.recent_closed_trades(limit=100) if t.trade_id == row.trade_id
        )
        store.write_trade(stored.model_copy(update={"realised_pnl_pct": Decimal("0.5")}))
    result = judge(engine_context, store, ledger(tmp_path, 1))
    expected = sum(Decimal(n) for n in HAIRCUT_RETURNS) / len(HAIRCUT_RETURNS)
    assert result.data["mean_net_return"] == pytest.approx(float(expected), abs=1e-15)


def test_a_run_with_fewer_than_ten_trades_is_not_promoted_and_says_why(
    engine_context: Any, store: Any, tmp_path: Path
) -> None:
    for index in range(9):
        opened = 1_720_000_000_000_000 + index * 100 * MINUTE
        store.write_trade(trade(index, "0.05", opened=opened, closed=opened + MINUTE))
    result = judge(engine_context, store, ledger(tmp_path, 1))
    assert result.status is EngineStatus.OK
    assert result.data["promoted"] is False
    assert result.data["promotion_reason_code"] == REASON_PROMOTION_TOO_FEW_TRADES
    assert result.data["lower_bound"] is None
    (row,) = verdict_rows(store)
    assert row.promoted is False
    assert row.n_trades == 9


def test_the_deflated_sharpe_is_reported_beside_the_verdict_whatever_it_is(
    engine_context: Any, store: Any
) -> None:
    write_haircut_run(store)
    result = judge(engine_context, store, COMMITTED_LEDGER)
    (row,) = verdict_rows(store)
    assert row.deflated_sharpe is not None
    assert row.deflated_sharpe == result.data["deflated_sharpe"]
    assert row.sharpe == result.data["sharpe"]


def test_judging_a_run_twice_writes_one_row(engine_context: Any, store: Any) -> None:
    write_haircut_run(store)
    first = judge(engine_context, store, COMMITTED_LEDGER)
    second = judge(engine_context, store, COMMITTED_LEDGER)
    assert (first.data["rows_written"], first.data["rows_skipped"]) == (1, 0)
    assert (second.data["rows_written"], second.data["rows_skipped"]) == (0, 1)
    assert len(verdict_rows(store)) == 1


def test_trades_of_another_run_are_not_judged(engine_context: Any, store: Any) -> None:
    write_haircut_run(store)
    stray = trade(99, "-0.5", opened=1, closed=2).model_copy(update={"run_id": "other-run"})
    store.write_trade(stray)
    result = judge(engine_context, store, COMMITTED_LEDGER)
    assert result.data["trades_judged"] == 15


# --------------------------------------------------------------------------- #
# Refusals: nothing written
# --------------------------------------------------------------------------- #


def test_no_ledger_blocks_and_writes_nothing(
    engine_context: Any, store: Any, tmp_path: Path
) -> None:
    write_haircut_run(store)
    result = judge(engine_context, store, tmp_path / "absent.json")
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_PROMOTION_NO_LEDGER
    assert verdict_rows(store) == ()


def test_a_ledger_whose_count_disagrees_with_its_rows_is_refused(
    engine_context: Any, store: Any, tmp_path: Path
) -> None:
    write_haircut_run(store)
    path = ledger(tmp_path, 3)
    payload = json.loads(path.read_bytes())
    payload["trial_count"] = 1
    path.write_bytes(json.dumps(payload).encode("utf-8"))
    result = judge(engine_context, store, path)
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_PROMOTION_NO_LEDGER
    assert "trial_count of 1 beside 3 trial rows" in result.reason
    assert verdict_rows(store) == ()


def test_a_trade_in_a_foreign_quote_blocks_rather_than_mixing_units(
    engine_context: Any, store: Any, tmp_path: Path
) -> None:
    write_haircut_run(store)
    store.write_trade(trade(50, "0.01", opened=5, closed=6, quote="EUR"))
    result = judge(engine_context, store, ledger(tmp_path, 1))
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_PROMOTION_BAD_TRADE
    assert "quoted in EUR" in result.reason
    assert verdict_rows(store) == ()


def test_a_store_holding_more_trades_than_the_gate_reads_is_refused(
    engine_context: Any, store: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store's read is a window; a window that could not hold every trade is refused,
    not judged, because a verdict over part of a run is a verdict about a different run."""
    from acsoe.engines.tournament import engine as tournament_engine

    monkeypatch.setattr(tournament_engine, "PROMOTION_TRADE_CAP", 14)
    write_haircut_run(store)
    result = judge(engine_context, store, ledger(tmp_path, 1))
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_PROMOTION_BAD_TRADE
    assert "more than 14 closed trades" in result.reason
    assert verdict_rows(store) == ()


def test_a_store_holding_exactly_the_cap_is_judged(
    engine_context: Any, store: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from acsoe.engines.tournament import engine as tournament_engine

    monkeypatch.setattr(tournament_engine, "PROMOTION_TRADE_CAP", 15)
    write_haircut_run(store)
    result = judge(engine_context, store, ledger(tmp_path, 1))
    assert result.status is EngineStatus.OK
    assert result.data["trades_judged"] == 15


def test_a_trade_with_no_entry_notional_blocks_rather_than_crashing(
    engine_context: Any, store: Any, tmp_path: Path
) -> None:
    """A zero notional has no net return. Refused by name: without the check the division
    raises and the run is judged by nobody, with no reason code to say why."""
    write_haircut_run(store)
    store.write_trade(trade(60, "0.01", opened=5, closed=6).model_copy(update={"qty": Decimal(0)}))
    result = judge(engine_context, store, ledger(tmp_path, 1))
    assert result.status is EngineStatus.BLOCK
    assert result.data["reason_code"] == REASON_PROMOTION_BAD_TRADE
    assert "entry notional of 0" in result.reason
    assert verdict_rows(store) == ()


# --------------------------------------------------------------------------- #
# The seam to the leaderboard screen (spec 140): no double between them
# --------------------------------------------------------------------------- #


def test_the_console_renders_the_verdict_engine_20_wrote(
    engine_context: Any, store: Any, migrated_db: Path, fixed_clock: Any
) -> None:
    """The real console reader over the database engine 20 just wrote: the reason in prose,
    the effective sample size recorded, the base-rate Brier absent rather than zero."""
    from acsoe.console.format import REASON_PROSE
    from acsoe.console.reader import ConsoleReader

    write_haircut_run(store)
    result = judge(engine_context, store, COMMITTED_LEDGER)
    assert result.data["promoted"] is False
    reader = ConsoleReader(migrated_db, clock=fixed_clock, stale_after_ms=120_000)
    try:
        (view,) = [row for row in reader.leaderboard() if row.model_id == CHAIN_RUN_MODEL_ID]
    finally:
        reader.close()
    assert view.model_version == RUN_ID
    assert view.promoted is False
    assert view.promotion_reason == REASON_PROSE[REASON_PROMOTION_LOWER_BOUND]
    # Fifteen non-overlapping trades: lag 0, so the HAC SE is the naive one and every
    # trade counts.
    assert view.effective_sample_size == pytest.approx(15.0)
    assert view.deflated_sharpe_text != "\N{EM DASH}"
    assert view.base_rate_brier is None
