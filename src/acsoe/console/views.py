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

from collections.abc import Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import Micros, Money

__all__ = [
    "FROZEN",
    "IDLE",
    "IDLE_READINGS",
    "IDLE_RESTARTED",
    "MODE_READINGS",
    "RUNNING",
    "SHAP_PRODUCED_IN_PHASE",
    "STATE_READINGS",
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

#: The daemon is running: the opportunity chain is looking for candidates.
RUNNING: Final = "Running"

#: The daemon is frozen: the opportunity chain has stopped, and the guard and
#: manage chains have not. ``architecture-context.md``: freeze never stops data
#: collection, and open positions are still managed. Text only — amber is reserved
#: for live mode and appears nowhere else in the interface.
FROZEN: Final = "Frozen"

#: The two readings the band shows when no daemon has claimed a mode for this run.
IDLE_READINGS: Final = (IDLE, IDLE_RESTARTED)

#: **Every reading the State field may take, and there are four.**
#:
#: Two of them arrived in Phase 2 with spec 32. Through Phase 1 the field showed
#: the idle pair alone, because mode lived only in ``state["system"]["mode"]`` in
#: the daemon's memory and nothing the console could read distinguished a running
#: daemon from a frozen one — ``runs.mode`` is paper/live/replay, a different axis
#: entirely. That was honest rather than incomplete while no daemon ran at all,
#: and it stopped being honest the moment one did.
#:
#: The mode is now **read as a fact**: the command reader in ``core/`` that owns
#: ``state["system"]["mode"]`` persists it through ``StoreClient.set_system_mode``,
#: and ``ConsoleReader.status_band`` reads it back scoped to the current ``run_id``.
#: Deriving it instead from the trail of claimed ``commands`` rows was considered
#: and **rejected** at the Phase 1 close: that reconstructs a mode from a command
#: history, so it is only ever as correct as the assumption that every transition
#: leaves a claimed row, and a transition that leaves none makes the band
#: confidently wrong. For the one element whose job is to answer *is this safe*,
#: silent beats wrong. **A value the console cannot read renders an idle reading.
#: There is no third path.**
STATE_READINGS: Final = (IDLE, IDLE_RESTARTED, RUNNING, FROZEN)

#: The persisted ``system_mode`` values, to the words the operator reads. A mode
#: outside this map is not guessed at: it renders an idle reading, exactly as a
#: missing one does.
MODE_READINGS: Final[Mapping[str, str]] = {"running": RUNNING, "frozen": FROZEN}

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

    ``mode`` is paper/live/replay from the injected `Config`. ``system_mode`` is
    the *other* axis entirely — idle/running/frozen, persisted by the daemon's
    command reader — and ``state`` is the word the operator reads, which is the two
    of them plus the restart test rendered into one field.

    **``system_mode`` and ``run_record_missing`` are two different nulls and are
    kept apart deliberately.** `StoreClient.system_mode` returns ``None`` when
    there is no ``runs`` row for that ``run_id`` at all, which is a defect or a
    race; it returns a row whose ``mode`` is ``None`` when the run exists and no
    daemon has written a mode yet, which is the ordinary state before the first
    command is read. Both render an idle reading, per spec 32 — but only one of
    them is normal, and a band that collapsed them could not log the abnormal one.
    """

    mode: str
    state: str
    system_mode: str | None
    run_record_missing: bool
    restarted: bool
    run_id: str | None
    previous_run_id: str | None
    balance: Money | None
    balance_text: str
    currency: str | None
    #: What the figure beside ``balance`` actually *is*, and whether it is real money.
    #:
    #: **The band showed a balance with no statement of its source, and in paper mode that
    #: figure is the paper broker's ledger** — invariant 2's paper-ledger ruling makes the
    #: broker the authority on its own cash, so it reads `paper.starting_balances` and then
    #: whatever the simulation does to it. The Kraken account is fetched by engine 1 on
    #: every tick and is *not* what this number shows. A screen that says "Balance: 5,000.00
    #: USD" beside a real exchange's live prices is inviting exactly one misreading, and the
    #: operator only has to make it once.
    #:
    #: ``balance_is_simulated`` is the fact; ``balance_label`` is the sentence-case words for
    #: it (`ui-context.md`, no all-caps labels). Two fields rather than one because a later
    #: reader — a real-balance panel, a test, a digest — wants the boolean and not a display
    #: string parsed back into one. The live-mode amber border already distinguishes the two
    #: modes *as modes*; it says nothing about which account a figure came from.
    balance_is_simulated: bool
    balance_label: str
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
    age_us: int
    """How long the position has been open, in microseconds.

    Set by the reader from the injected clock, for the reason :class:`Staleness` gives:
    a view model that worked out its own age would be reading a clock, and the console
    has exactly one, held by the reader. Spec 101 — an operator deciding whether to
    leave a position alone reads its age against its timeout, and neither number means
    anything without the other."""

    age_text: str
    staleness: Staleness

    hold_reason: str | None
    """The manage chain's hold on this position, as engine 21 published it.

    **Deliberately required, with no default**, although ``None`` is the ordinary value.
    `code-standards.md` records the cost of the other choice in this exact place: a
    `PositionRow` whose `hold_reason` defaults to ``None`` satisfied the assertion a test
    was making about engine 19, so the test passed under its own mutation. A default here
    is a second source for the value under test, and every construction site is the
    reader, which always has the row in hand.

    ``None`` on a position nothing held, which is the ordinary case, and the field is
    **null rather than absent** for the reason `position_manager/contracts.py` gives one
    level up: on a tick that did not hold, the null *is* the answer.

    Spec 101. Engine 21 has published this since Phase 6 and engine 19 has stored it on
    the row, and until now the console read the row and rendered nothing — so a held
    position and an ordinary one were the same row on screen. What that withheld is
    specific: a hold means **exits are paused**, and an operator watching a position sit
    on its stop needs to know the exit is not coming this tick."""

    hold_reason_text: str
    """:attr:`hold_reason` as operator prose, through ``REASON_PROSE``.

    Empty string when nothing held, so the cell is blank rather than carrying a word for
    the absence of a hold. A code that reaches the screen is the defect
    :func:`~acsoe.console.format.operator_reason` exists to prevent — `ownership.md` makes
    `console/format.py` the one place a `hold_reason` becomes English, and this is the
    field that carries the result."""


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
    #: The Brier a constant prediction of the fold's own target rate would earn. A Brier
    #: means nothing without it (spec 140; migration 0004).
    base_rate_brier: float | None
    base_rate_brier_text: str
    #: How many independent observations the row's statistic rests on, where the row
    #: records one: the promotion gate's `n x (se_naive / se_hac)^2` for a judged run. A
    #: fold's row does not record one, and says so rather than borrow the trade count.
    effective_sample_size: float | None
    effective_sample_size_text: str
    net_pnl: Money | None
    net_pnl_text: str
    reporting_currency: str | None
    promoted: bool
    #: Why the promotion gate did not promote, in operator prose; empty when it did, or
    #: when the row was never judged (spec 139's reason code, mapped by `REASON_PROSE`).
    promotion_reason: str


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
