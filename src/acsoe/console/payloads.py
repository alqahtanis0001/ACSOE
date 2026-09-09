"""View models to JSON, with no money value passing through ``float``.

This module exists for one reason, and it is not tidiness.

FastAPI serialises a returned object through ``jsonable_encoder``, and
``jsonable_encoder`` renders a ``Decimal`` by calling ``float()`` on it. Every
money field on every view model is a ``Decimal`` that deliberately *refuses* a
float at the store boundary — and the response encoder would have undone that on
the way out, silently, for every price and every balance the console serves. The
whole point of ``clients/store/contracts.Money`` is that a value which has lost
precision is rejected rather than rendered to two convincing decimal places.

So nothing here hands a ``Decimal`` to the encoder. Each payload emits **strings
and integers only**: the rendered text that ``console/format.py`` already
produced, and the raw exact decimal string beside it where a consumer might want
to compute. Timestamps stay integer microseconds, which is what the store holds
and what JSON represents exactly.

The routes return these dicts inside a `starlette.responses.JSONResponse`, which
FastAPI passes through untouched — a response object short-circuits
``jsonable_encoder`` entirely. ``tests/console/test_payloads.py`` asserts the
whole encoded body contains no JSON float anywhere, which is the assertion that
would fail the moment someone returned a view model directly.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from acsoe.console.views import (
    FeedRowView,
    FeedSummary,
    HistoryView,
    LeaderboardEntryView,
    PositionView,
    RejectionRowView,
    ResearchView,
    ShapPane,
    Staleness,
    StatusBand,
    TradeRowView,
)

__all__ = [
    "feed_payload",
    "history_payload",
    "money",
    "research_payload",
    "staleness_payload",
    "state_payload",
]


def money(value: Decimal | None) -> str | None:
    """A money value as its **exact decimal string**, never as a number.

    ``format(value, "f")`` rather than ``str``: ``str(Decimal("1E+3"))`` produces
    scientific notation, which a consumer parsing the field would have to handle
    and which reads as noise in a payload. Trailing zeros are kept, because they
    are the quantum the writer chose and normalising them away throws away the
    exchange's own ``pair_decimals``.
    """
    return None if value is None else format(value, "f")


def staleness_payload(value: Staleness | None) -> dict[str, Any] | None:
    """How old one figure is. ``None`` when there is no figure to age."""
    if value is None:
        return None
    return {
        "age_us": value.age_us,
        "age_ms": value.age_ms,
        "age_text": value.age_text,
        "stale_after_ms": value.stale_after_ms,
        "is_stale": value.is_stale,
    }


def _position_payload(view: PositionView) -> dict[str, Any]:
    return {
        "position_id": view.position_id,
        "pair": view.pair,
        "base": view.base,
        "quote": view.quote,
        "qty": money(view.qty),
        "qty_text": view.qty_text,
        "entry_price": money(view.entry_price),
        "entry_price_text": view.entry_price_text,
        "last_price": money(view.last_price),
        "last_price_text": view.last_price_text,
        "target_price": money(view.target_price),
        "target_price_text": view.target_price_text,
        "stop_price": money(view.stop_price),
        "stop_price_text": view.stop_price_text,
        "unrealised_pnl": money(view.unrealised_pnl),
        "unrealised_pnl_text": view.unrealised_pnl_text,
        "unrealised_pnl_pct_text": view.unrealised_pnl_pct_text,
        "direction": view.direction,
        "opened_at": view.opened_at,
        "timeout_at": view.timeout_at,
        "staleness": staleness_payload(view.staleness),
    }


def state_payload(band: StatusBand, positions: tuple[PositionView, ...]) -> dict[str, Any]:
    """The status band and the open-positions region: one screen, one payload.

    ``positions`` is an empty list when nothing is open, and the page renders **no
    region at all** in that case rather than an empty table. `ui-context.md` puts
    open positions behind "only rendered if any exist" for the same reason the
    cycle feed's empty state is prose: an empty table is furniture, not
    information.
    """
    return {
        "band": {
            "mode": band.mode,
            "state": band.state,
            "restarted": band.restarted,
            "run_id": band.run_id,
            "previous_run_id": band.previous_run_id,
            "balance": money(band.balance),
            "balance_text": band.balance_text,
            "currency": band.currency,
            "open_position_count": band.open_position_count,
            "resting_order_count": band.resting_order_count,
            "equity_ts": band.equity_ts,
            "staleness": staleness_payload(band.staleness),
            "watermark_ts": band.watermark_ts,
            "data_staleness": staleness_payload(band.data_staleness),
        },
        "positions": [_position_payload(view) for view in positions],
    }


def _feed_row_payload(view: FeedRowView) -> dict[str, Any]:
    return {
        "kind": view.kind,
        "ts": view.ts,
        "time_text": view.time_text,
        "run_id": view.run_id,
        "cycle_id": view.cycle_id,
        "engine": view.engine,
        "pair": view.pair,
        "outcome": view.outcome,
        "reason": view.reason,
    }


def feed_payload(rows: tuple[FeedRowView, ...], summary: FeedSummary) -> dict[str, Any]:
    """The cycle feed and the empty state that stands in for it.

    The summary is sent **whether or not there are rows**, because it is not an
    error state to be swapped in: it is what the system did, and it stays true
    when a handful of rows are showing.
    """
    return {
        "rows": [_feed_row_payload(view) for view in rows],
        "summary": {
            "headline": summary.headline,
            "rejection_count": summary.rejection_count,
            "blocked_tick_count": summary.blocked_tick_count,
            "stages": [
                {"label": stage.label, "count": stage.count, "detail": stage.detail}
                for stage in summary.stages
            ],
        },
    }


def _trade_payload(view: TradeRowView) -> dict[str, Any]:
    return {
        "pair": view.pair,
        "opened_at": view.opened_at,
        "opened_text": view.opened_text,
        "closed_at": view.closed_at,
        "closed_text": view.closed_text,
        "outcome": view.outcome,
        "qty": money(view.qty),
        "qty_text": view.qty_text,
        "entry_price": money(view.entry_price),
        "entry_price_text": view.entry_price_text,
        "exit_price": money(view.exit_price),
        "exit_price_text": view.exit_price_text,
        "entry_fee": money(view.entry_fee),
        "entry_fee_text": view.entry_fee_text,
        "exit_fee": money(view.exit_fee),
        "exit_fee_text": view.exit_fee_text,
        "realised_pnl": money(view.realised_pnl),
        "realised_pnl_text": view.realised_pnl_text,
        "realised_pnl_pct": money(view.realised_pnl_pct),
        "realised_pnl_pct_text": view.realised_pnl_pct_text,
        "direction": view.direction,
        "reporting_currency": view.reporting_currency,
    }


def _rejection_payload(view: RejectionRowView) -> dict[str, Any]:
    return {
        "ts": view.ts,
        "time_text": view.time_text,
        "run_id": view.run_id,
        "cycle_id": view.cycle_id,
        "pair": view.pair,
        "rejected_by": view.rejected_by,
        "rejected_by_text": view.rejected_by_text,
        "reason": view.reason,
        "expected_move_pct_text": view.expected_move_pct_text,
        "friction_pct_text": view.friction_pct_text,
        "net_edge_pct_text": view.net_edge_pct_text,
        "hurdle_pct_text": view.hurdle_pct_text,
        "net_edge_direction": view.net_edge_direction,
    }


def history_payload(view: HistoryView) -> dict[str, Any]:
    """Closed trades and past rejections, as two lists rather than one."""
    return {
        "trades": [_trade_payload(row) for row in view.trades],
        "rejections": [_rejection_payload(row) for row in view.rejections],
    }


def _leaderboard_payload(view: LeaderboardEntryView) -> dict[str, Any]:
    """One ranked model version.

    ``win_rate``, ``sharpe``, ``deflated_sharpe`` and ``brier`` are statistics and
    are genuinely ``float`` — they were never money and never a ``Decimal``. They
    are sent as their rendered text only, so that this payload carries no JSON
    number that could be mistaken for a monetary one and the test asserting no
    floats in the body stays a simple, total assertion rather than a list of
    exceptions.
    """
    return {
        "model_id": view.model_id,
        "model_version": view.model_version,
        "trained_at": view.trained_at,
        "trained_at_text": view.trained_at_text,
        "fold": view.fold,
        "n_trades": view.n_trades,
        "win_rate_text": view.win_rate_text,
        "sharpe_text": view.sharpe_text,
        "deflated_sharpe_text": view.deflated_sharpe_text,
        "brier_text": view.brier_text,
        "net_pnl": money(view.net_pnl),
        "net_pnl_text": view.net_pnl_text,
        "reporting_currency": view.reporting_currency,
        "promoted": view.promoted,
    }


def _shap_payload(view: ShapPane) -> dict[str, Any]:
    """The SHAP pane: three fields, none of which is a value.

    There is no ``rows`` key and no ``chart`` key, deliberately, and adding either
    is the change ``tests/console/test_research.py`` exists to fail. Phase 5 writes
    the attribution; until then the pane says so and shows nothing.
    """
    return {
        "available": view.available,
        "produced_in_phase": view.produced_in_phase,
        "message": view.message,
    }


def research_payload(view: ResearchView) -> dict[str, Any]:
    return {
        "leaderboard": [_leaderboard_payload(row) for row in view.leaderboard],
        "shap": _shap_payload(view.shap),
    }
