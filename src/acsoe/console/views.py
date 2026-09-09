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
    "IDLE_READINGS",
    "IDLE_RESTARTED",
    "SHAP_PRODUCED_IN_PHASE",
    "FeedRowView",
    "FeedStage",
    "FeedSummary",
    "HistoryView",
    "LeaderboardEntryView",
    "PositionView",
    "RejectionRowView",
    "ResearchView",
    "ShapPane",
    "Staleness",
    "StatusBand",
    "TradeRowView",
]

#: The State field of the status band when the daemon is idle and this is the
#: first run the database has ever seen.
IDLE: Final = "Idle"

#: And when a previous run exists. ``ui-context.md``: "The two states are not the
#: same event and must not look the same. One is a system waiting to be started;
#: the other is a system that stopped on its own." Text only — amber is reserved
#: for live mode, and the words have to carry the meaning anyway.
IDLE_RESTARTED: Final = "Idle \N{EM DASH} restarted, not trading"

#: **Every reading the State field may take in Phase 1, and there are two.**
#:
#: The daemon also has ``running`` and ``frozen``, and the Phase 1 console cannot
#: render either: mode lives only in ``state["system"]["mode"]`` in the daemon's
#: memory, and ``runs.mode`` is paper/live/replay, a different axis entirely. That
#: is honest here rather than incomplete — no daemon runs in Phase 1, the console
#: renders the Phase 0 seed, and neither state can occur.
#:
#: The operator ruled on 2026-09-09 that the fix lands in **Phase 2**, where the
#: command reader in ``core/`` that already owns the mode also persists it and the
#: console reads it as a fact. Deriving it from the claimed-``commands`` trail was
#: considered and rejected: a transition leaving no claimed row makes the band
#: confidently wrong, and for the one element answering *is this safe* silent
#: beats wrong. ``tests/console/test_reader.py`` asserts the State field never
#: leaves this tuple, so the deferral is enforced by the suite rather than
#: remembered by a person.
IDLE_READINGS: Final = (IDLE, IDLE_RESTARTED)

#: Which phase produces per-decision attribution. ``rejections.shap_ref`` is the
#: join key and the Parquet it points at is written by the training pipeline; there
#: is no attribution data in the Phase 0 seed and there will be none until then.
#: The SHAP pane names this rather than drawing a placeholder.
SHAP_PRODUCED_IN_PHASE: Final = 5


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
    """The hero. Balance, mode, state, data age — always visible, never scrolls.

    ``staleness`` is the age of the *balance figure*, which is what rule 5 fades to
    half opacity. ``data_staleness`` is the age of the **store watermark** — the
    highest ``updated_at`` across every table the console renders — which is the
    Data age field of the band. They are different questions: a daemon can be
    writing block records every tick while the equity series has not moved, and a
    band that conflated them would report the screen fresh because *something*
    changed.
    """

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
    watermark_ts: Micros | None
    data_staleness: Staleness | None


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
    direction: str
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

    ``run_id`` and ``cycle_id`` are both carried because **a tick is
    ``(run_id, cycle_id)``, never ``cycle_id`` alone** — the counter restarts at 1
    with each process. ``ts`` is the ordering key for the same reason.
    """

    kind: str
    ts: Micros
    time_text: str
    run_id: str
    cycle_id: int
    engine: str
    pair: str | None
    outcome: str
    reason: str


class FeedStage(_View):
    """One line of the cycle feed's empty state.

    ``count`` is ``None`` when nothing in the store records that stage. The line
    then *says so*, because a zero in a column of counts reads as a result — "no
    pair entered the universe" — when the truth is that nobody counted.
    """

    label: str
    count: int | None
    detail: str


class FeedSummary(_View):
    """What the system actually did, for the state it is in most of the time.

    ``ui-context.md``: "When nothing qualified, do not show 'No results.' Show what
    the system actually did." Every count here is read off rows that exist; none is
    computed from a rule, and none is invented for a stage the store does not
    record.
    """

    stages: tuple[FeedStage, ...]
    rejection_count: int
    blocked_tick_count: int
    headline: str


class TradeRowView(_View):
    """One closed trade on the history screen."""

    pair: str
    opened_at: Micros
    opened_text: str
    closed_at: Micros
    closed_text: str
    outcome: str
    qty: Money
    qty_text: str
    entry_price: Money
    entry_price_text: str
    exit_price: Money
    exit_price_text: str
    entry_fee: Money
    entry_fee_text: str
    exit_fee: Money
    exit_fee_text: str
    realised_pnl: Money
    realised_pnl_text: str
    realised_pnl_pct: Money
    realised_pnl_pct_text: str
    direction: str
    reporting_currency: str


class RejectionRowView(_View):
    """One refused candidate on the history screen.

    The four economics figures are ``None`` on a row that does not carry them — a
    ``scout`` rejection never reached the cost gate, so it has no net edge, and
    rendering a zero there would state a number the row does not hold.
    """

    ts: Micros
    time_text: str
    run_id: str
    cycle_id: int
    pair: str
    rejected_by: str
    rejected_by_text: str
    reason: str
    expected_move_pct_text: str
    friction_pct_text: str
    net_edge_pct_text: str
    hurdle_pct_text: str
    net_edge_direction: str


class HistoryView(_View):
    """The history screen: two tables, not one.

    A closed trade and a refused candidate are different records with different
    columns, and interleaving them into one table would have meant a row of blank
    cells for whichever kind each column did not belong to.
    """

    trades: tuple[TradeRowView, ...]
    rejections: tuple[RejectionRowView, ...]


class LeaderboardEntryView(_View):
    """One ranked model version.

    The metrics are statistics, so ``float`` is correct for them and only for
    them; ``net_pnl`` is money and stays a ``Decimal``.
    """

    model_id: str
    model_version: str
    trained_at: Micros
    trained_at_text: str
    fold: str | None
    n_trades: int
    win_rate: float | None
    win_rate_text: str
    sharpe: float | None
    sharpe_text: str
    deflated_sharpe: float | None
    deflated_sharpe_text: str
    brier: float | None
    brier_text: str
    net_pnl: Money | None
    net_pnl_text: str
    reporting_currency: str | None
    promoted: bool


class ShapPane(_View):
    """The SHAP pane, which in Phase 1 is an empty state and nothing else.

    Deliberately carries **no rows and no chart**. ``rejections.shap_ref`` is the
    join key and the Parquet it points at is written by the training pipeline in
    Phase 5; there is no attribution data yet. A chart of zeros, a placeholder
    figure or a sample explanation would look like attribution and would not be
    one, which is worse than nothing — so this model has nowhere to put one.
    """

    available: bool
    produced_in_phase: int
    message: str


class ResearchView(_View):
    """The research screen: the leaderboard, and the SHAP pane's honest absence."""

    leaderboard: tuple[LeaderboardEntryView, ...]
    shap: ShapPane
