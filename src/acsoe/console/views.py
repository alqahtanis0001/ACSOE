"""View models — one per screen region of ``context/ui-context.md``.

These are what the reader produces and what every screen above it renders. They
sit deliberately between B's row contracts and the markup: a `PositionRow` knows
about ``userref`` and ``timeout_at``, and the open-positions region does not.

**Money never becomes a float here.** Every monetary field is
:data:`acsoe.clients.store.contracts.Money`, which is a ``Decimal`` that *refuses*
a float rather than coercing one, so a value that has already lost precision is
rejected at this boundary instead of being rendered to two convincing decimal
places. Each money field is accompanied by a rendered string built by
``console/format.py``, because that is where the sign and the minus character are
decided and the screens must not each decide again.

**Staleness is carried, not recomputed.** ``age_ms`` and ``is_stale`` are set by
the reader from the injected clock. A view model that worked out its own age
would have to read a clock, and a console that reads wall time has a staleness
test that is a race rather than an assertion.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import Micros, Money

__all__ = [
    "IDLE",
    "IDLE_RESTARTED",
    "FeedRowView",
    "HistoryRowView",
    "LeaderboardEntryView",
    "PositionView",
    "Staleness",
    "StatusBand",
]

#: The State field of the status band when the daemon is idle and this is the
#: first run the database has ever seen.
IDLE: Final = "Idle"

#: And when a previous run exists. ``ui-context.md``: "The two states are not the
#: same event and must not look the same. One is a system waiting to be started;
#: the other is a system that stopped on its own." Text only — amber is reserved
#: for live mode, and the words have to carry the meaning anyway.
IDLE_RESTARTED: Final = "Idle \N{EM DASH} restarted, not trading"


class _View(BaseModel):
    """Base for every view model. Frozen, and a stray field is a defect."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Staleness(_View):
    """How old one figure is, against ``console.stale_after_ms``.

    Computed in **microseconds** and reported in milliseconds. That is not
    pedantry: the threshold is expressed in milliseconds, so a figure one
    microsecond past it floors to exactly the threshold in millisecond arithmetic
    and would read as fresh. The comparison therefore happens before the
    conversion, and ``age_ms`` is a display value only.
    """

    age_us: int
    stale_after_ms: int
    is_stale: bool
    age_text: str

    @property
    def age_ms(self) -> int:
        return self.age_us // 1000


class StatusBand(_View):
    """The hero. Balance, mode, state, data age — always visible, never scrolls."""

    mode: str
    state: str
    restarted: bool
    run_id: str | None
    previous_run_id: str | None
    balance: Money | None
    balance_text: str
    currency: str | None
    open_position_count: int
    resting_order_count: int
    equity_ts: Micros | None
    staleness: Staleness | None


class PositionView(_View):
    """One row of the open-positions region, rendered only when any exist."""

    position_id: str
    pair: str
    base: str
    quote: str
    qty: Money
    qty_text: str
    entry_price: Money
    entry_price_text: str
    last_price: Money | None
    last_price_text: str
    target_price: Money
    target_price_text: str
    stop_price: Money
    stop_price_text: str
    unrealised_pnl: Money | None
    unrealised_pnl_text: str
    unrealised_pnl_pct_text: str
    opened_at: Micros
    timeout_at: Micros
    staleness: Staleness


class FeedRowView(_View):
    """One row of the cycle feed: time, pair, outcome, reason.

    Two kinds share the row, because the feed is a record of what the system did
    on each tick and both are that. A ``rejection`` is one *candidate* refused; a
    ``block`` is one *tick* on which trading was blocked, and most blocked ticks
    never had a candidate at all. Keeping the kind on the row is what stops a
    reader counting feed outages as refused trades.
    """

    kind: str
    ts: Micros
    run_id: str
    cycle_id: int
    pair: str | None
    outcome: str
    reason: str


class HistoryRowView(_View):
    """One row of the history screen: a closed trade or a past rejection."""

    kind: str
    ts: Micros
    pair: str
    outcome: str
    reason: str
    qty_text: str
    entry_price_text: str
    exit_price_text: str
    realised_pnl: Money | None
    realised_pnl_text: str
    realised_pnl_pct_text: str
    reporting_currency: str | None


class LeaderboardEntryView(_View):
    """One ranked model version.

    The metrics are statistics, so ``float`` is correct for them and only for
    them; ``net_pnl`` is money and stays a ``Decimal``.
    """

    model_id: str
    model_version: str
    trained_at: Micros
    fold: str | None
    n_trades: int
    win_rate: float | None
    sharpe: float | None
    deflated_sharpe: float | None
    brier: float | None
    net_pnl: Money | None
    net_pnl_text: str
    reporting_currency: str | None
    promoted: bool
