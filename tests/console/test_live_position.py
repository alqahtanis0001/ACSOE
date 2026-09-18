"""The open-positions region on a position the manage chain actually managed. Spec 101.

Phase 1 proved this region renders **seeded** rows, and that is a different claim: a
seeded row is written by the seed generator to the shape the console expects, and a
position the daemon holds is written by engine 19 out of what engine 21 published. Between
those two shapes sits every field the console reads, and until spec 101 one of them —
``hold_reason`` — was written by engine 21, stored by engine 19, read by the reader and
rendered nowhere.

**Real engine 21, then real engine 19, and no double between them.** `code-standards.md`:
for any seam driven by a double, keep one test with no double in it — and the whole seam
here *is* the shape of engine 21's payload. So every test below takes the seed's open
position, runs `PositionManagerEngine` over it with a quote, hands the resulting
`state["position_manager"]` to `MemoryEngine`, and then asks `ConsoleReader` what the
screen says. Nothing in this file writes a position row by hand.

**The moved mark is recomputed, never read back.** The second tick's expected unrealised
PnL is ``qty * (bid - entry)`` computed here from the quote this file planted, so a reader
that served the previous tick's figure cannot satisfy it by being self-consistent.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.paper.broker import PaperBroker
from acsoe.clients.store.client import StoreClient
from acsoe.console.format import MINUS_SIGN, REASON_PROSE, operator_reason
from acsoe.console.payloads import state_payload
from acsoe.console.reader import ConsoleReader
from acsoe.core.contracts import EngineStatus
from acsoe.engines.market_sensor.contracts import QuoteView
from acsoe.engines.memory.contracts import CYCLE_ID_KEY, GUARD_BLOCKERS_KEY
from acsoe.engines.memory.engine import MemoryEngine
from acsoe.engines.position_manager.contracts import (
    HOLD_DATA_GUARD_BLOCKED,
    HOLD_REASON_FIELD,
    POSITIONS_FIELD,
)
from acsoe.engines.position_manager.contracts import (
    STATE_KEY as POSITION_MANAGER_KEY,
)
from acsoe.engines.position_manager.engine import PositionManagerEngine

RUN = "run-live-position"
STALE_AFTER_MS = 120_000

#: The two marks the position is held at, in order, **as fractions of its own entry
#: price** rather than as prices.
#:
#: Derived rather than written out because they have a job: the first must sit below the
#: entry and the second above it, so that `direction` and the sign of the unrealised PnL
#: move between the ticks. Two marks on one side of the entry would leave both unchanged
#: and the test could not tell a figure that moved from a frozen one that happened to
#: agree. Written as literals they were `0.90` and `1.40`, which straddled nothing: the
#: seed's own entry price is not a number this file gets to choose.
BELOW_ENTRY = Decimal("0.95")
ABOVE_ENTRY = Decimal("1.05")

#: Enough places that neither mark collides with the entry after rounding, and few enough
#: that the rendered string is readable in a failure message.
MARK_QUANTUM = Decimal("0.000001")


SPREAD = Decimal("0.01")


def _quote(pair: str, bid: Decimal, now: Any) -> dict[str, Any]:
    """One top-of-book quote, through engine 3's **own** `QuoteView`.

    Fabricate the subject, never the contract. Engine 3's quotes come off a WebSocket
    stream, so the quote itself has to be planted — but its field names and its
    serialisation are engine 3's, so this file cannot invent a shape engine 21 would
    never meet. `verify.py`'s Phase 3 criteria build theirs the same way and for the same
    reason.
    """
    ask = bid + SPREAD
    return dict(
        QuoteView(
            pair=pair,
            ts=now.isoformat().replace("+00:00", "Z"),
            bid=bid,
            ask=ask,
            spread=SPREAD,
            spread_pct=SPREAD / bid,
            age_s=1.0,
        ).state_dict()
    )


def _tick_state(
    cycle_id: int, quotes: dict[str, Any], bids: dict[str, Decimal], *, blocked: str | None
) -> dict[str, Any]:
    """One tick's `state`, carrying only the keys engines 21 and 19 actually read.

    The trade range is pinned to the bid on purpose: this file is about what the console
    renders, and a range that reached a barrier would have engine 22 close the position
    out from under the assertion.
    """
    state: dict[str, Any] = {
        "system": {"mode": "running", "close_intent": False},
        CYCLE_ID_KEY: cycle_id,
        GUARD_BLOCKERS_KEY: [],
        "market_sensor": {
            "quotes": quotes,
            "trade_ranges": {
                pair: {"low": str(bid), "high": str(bid), "count": 1}
                for pair, bid in bids.items()
            },
        },
    }
    if blocked is not None:
        state["trading_blocked_by"] = blocked
        state["block_reason"] = "a crossed quote"
    return state


@pytest.fixture
def live_position(
    seed_fixtures: Any,
    seeded_db: Path,
    seed_clock: Any,
    paper_config: Any,
    fake_kraken: Any,
    fake_recorder: Any,
) -> Any:
    """A driver that runs one manage-chain tick and returns what the console then says.

    The seed's open position is the subject, so this is the row Phase 1 rendered — and it
    is re-marked and re-stored by the real engines before the console is asked about it,
    which is the difference spec 101 is about.
    """
    from tests.harness.doubles import FakeClients, FixedClock
    from tests.harness.market_script import ScriptedMarket

    from acsoe.core.contracts import EngineContext

    # `open_positions` on the seed's fixture object is a tuple of ids; the row itself is
    # read back through the store's own model, which is also what proves the seed really
    # left an open position here rather than only naming one.
    position_id = str(seed_fixtures.open_positions[0])

    class Driver:
        def __init__(self) -> None:
            self.position_id = position_id
            self.cycle = 100
            self._store = StoreClient(seeded_db)
            row = self._store.position(position_id)
            assert row is not None, f"the seed names {position_id} and did not write it"
            self.pair = str(row.pair)
            self.entry_price = Decimal(str(row.entry_price))
            self.qty = Decimal(str(row.qty))
            self.below = (self.entry_price * BELOW_ENTRY).quantize(MARK_QUANTUM)
            self.above = (self.entry_price * ABOVE_ENTRY).quantize(MARK_QUANTUM)
            assert self.below < self.entry_price < self.above, (
                "the two marks do not straddle the entry, so the sign cannot move"
            )
            self._open_pairs = [str(p.pair) for p in self._store.open_positions()]
            self._manager = PositionManagerEngine()
            self._memory = MemoryEngine()

            # The clock the market and the engines share. One object, advanced in one
            # place: a market told the time separately is a market that will be told it
            # wrong, and a stream that reports a trade from the future is look-ahead.
            self._clock = FixedClock(seed_clock.now())
            market = ScriptedMarket(
                clock=self._clock,
                interval_s=int(paper_config.get("timeframes.decision_bar_s")),
                published_bars=200,
                pairs=tuple(self._open_pairs),
            )
            # **The paper broker, not the bare fake client.** Engine 21 settles resting
            # entries before it marks anything, and the seed leaves a resting entry order
            # in the store on purpose — so a client with no order surface makes engine 21
            # ERROR on every tick and publish no positions at all. That is what this
            # driver did on its first run, and a console test asserting on an empty region
            # would have been asserting on an errored manage chain.
            self._broker = PaperBroker(
                market, store=self._store, config=paper_config, clock=self._clock
            )
            self._market = market

        def context(self) -> Any:
            return EngineContext(
                mode="paper",
                run_id=RUN,
                now=self._clock.now(),
                config=paper_config,
                clients=FakeClients(
                    kraken=self._broker, store=self._store, recorder=fake_recorder
                ),
            )

        def manage(self, bid: Decimal, *, blocked: str | None = None) -> dict[str, Any]:
            """One real engine-21 tick, then one real engine-19 tick over its payload."""
            self.cycle += 1
            self._clock.set(seed_clock.now() + timedelta(minutes=self.cycle - 100))
            context = self.context()
            bids = dict.fromkeys(self._open_pairs, bid)
            quotes = {
                pair: _quote(pair, value, context.now) for pair, value in bids.items()
            }
            for pair, value in bids.items():
                self._market.set_quote(pair, bid=str(value), ask=str(value + SPREAD))
            state = _tick_state(self.cycle, quotes, bids, blocked=blocked)
            managed = self._manager.process(context, state)
            assert managed.data is not None, "engine 21 published nothing to store"
            assert managed.status is EngineStatus.OK, (
                f"engine 21 errored rather than managing the tick: {managed.reason}"
            )
            state[POSITION_MANAGER_KEY] = managed.data
            self._memory.process(context, state)
            return dict(managed.data)

        def _reader(self, minutes: int) -> ConsoleReader:
            """A console reading `minutes` after the daemon's last tick.

            Offset from **the daemon's clock and not the seed's instant**. Anchored to the
            seed, a console asked for the row at `minutes=0` would be standing *before*
            the tick that wrote it: the age comes out negative, the reader clamps it to
            zero, and the row reports fresh — which is the answer the fresh case wants,
            arrived at by a console that is behind the daemon rather than by a row that is
            recent. Two hypotheses, one witness. Anchored here, `minutes=0` is a console
            reading at the instant the daemon wrote.
            """
            return ConsoleReader(
                seeded_db,
                clock=_ClockAt(self._clock.now() + timedelta(minutes=minutes)),
                stale_after_ms=STALE_AFTER_MS,
            )

        def view(self, *, minutes: int = 0) -> Any:
            reader = self._reader(minutes)
            try:
                return next(
                    view for view in reader.positions() if view.position_id == self.position_id
                )
            finally:
                reader.close()

        def payload(self, *, minutes: int = 0) -> dict[str, Any]:
            reader = self._reader(minutes)
            try:
                sent = state_payload(reader.status_band(mode="paper"), reader.positions())
            finally:
                reader.close()
            return next(
                row for row in sent["positions"] if row["position_id"] == self.position_id
            )

        def close(self) -> None:
            self._store.close()

    driver = Driver()
    try:
        yield driver
    finally:
        driver.close()


class _ClockAt:
    """A clock standing at one fixed instant. The console's own, and the only time it has."""

    def __init__(self, at: Any) -> None:
        self._at = at

    def now(self) -> Any:
        return self._at


# --------------------------------------------------------------------------- #
# The round trip
# --------------------------------------------------------------------------- #


def test_a_position_engine_21_marked_and_engine_19_stored_renders(live_position: Any) -> None:
    """Spec 101 step 5, first clause. No hand-written row anywhere on this path.

    The mark is the assertion that the round trip happened: the seed did not write this
    price, engine 21 computed it from the quote planted above, and the console is reading
    what engine 19 stored rather than what the seed left behind.
    """
    published = live_position.manage(live_position.below)
    assert published[POSITIONS_FIELD], "engine 21 marked no position, so nothing was stored"

    view = live_position.view()
    assert view.last_price == live_position.below
    assert view.last_price_text == str(live_position.below)
    assert view.entry_price == live_position.entry_price
    assert view.unrealised_pnl == live_position.qty * (live_position.below - live_position.entry_price)


def test_a_second_tick_moves_the_rendered_mark_and_the_unrealised_pnl(
    live_position: Any,
) -> None:
    """Spec 101 step 5, second clause: the region is live, not a snapshot.

    Both figures are recomputed here from the quote this file planted, so a reader that
    served the previous tick's mark cannot satisfy this by being consistent with itself —
    which is the FAIL arm the criterion names. The two marks straddle the entry, so the
    *sign* moves too and the direction class changes with it: a mutation that froze the
    figure would have to freeze a positive number where a negative one belongs.
    """
    live_position.manage(live_position.below)
    first = live_position.view()

    live_position.manage(live_position.above)
    second = live_position.view()

    assert first.last_price == live_position.below
    assert second.last_price == live_position.above
    assert second.last_price != first.last_price
    assert second.last_price_text != first.last_price_text

    qty = live_position.qty
    entry = live_position.entry_price
    assert first.unrealised_pnl == qty * (live_position.below - entry)
    assert second.unrealised_pnl == qty * (live_position.above - entry)
    assert second.unrealised_pnl - first.unrealised_pnl == qty * (live_position.above - live_position.below)

    # Rule 3: the sign carries the meaning and the colour only reinforces it, so both
    # move together and neither is asserted alone.
    assert first.direction == "neg"
    assert second.direction == "pos"
    assert first.unrealised_pnl_text.startswith(MINUS_SIGN)
    assert second.unrealised_pnl_pct_text.startswith("+")


def test_the_moved_mark_reaches_the_websocket_payload(live_position: Any) -> None:
    """The figure the browser is handed, not only the one the reader built.

    `payloads.py` is a second hand-written list of field names, and a field added to the
    view and forgotten here renders as `undefined` in the table with nothing raising.
    """
    live_position.manage(live_position.below)
    assert live_position.payload()["last_price"] == str(live_position.below)

    live_position.manage(live_position.above)
    moved = live_position.payload()
    assert moved["last_price"] == str(live_position.above)
    assert moved["last_price_text"] == str(live_position.above)
    assert moved["unrealised_pnl"] == format(
        live_position.qty * (live_position.above - live_position.entry_price), "f"
    )


# --------------------------------------------------------------------------- #
# The hold
# --------------------------------------------------------------------------- #


def test_a_held_position_shows_its_reason_as_operator_prose(live_position: Any) -> None:
    """Spec 101 step 3, and the finding the hand check opened with.

    Engine 21 has published `hold_reason` and engine 19 has stored it since Phase 6, and
    the console rendered nothing: a held position and an ordinary one were the same row.
    What that withheld is specific — a hold means **exits are paused** — so the prose is
    asserted to be the sentence `REASON_PROSE` holds for the code rather than merely to be
    non-empty, and the code itself is asserted **not** to be on screen.
    """
    published = live_position.manage(live_position.below, blocked="data_guard")
    assert published[HOLD_REASON_FIELD] == HOLD_DATA_GUARD_BLOCKED, (
        "engine 21 did not hold, so there is no hold for the console to show"
    )

    view = live_position.view()
    assert view.hold_reason == HOLD_DATA_GUARD_BLOCKED
    assert view.hold_reason_text == REASON_PROSE[HOLD_DATA_GUARD_BLOCKED]
    assert view.hold_reason_text == operator_reason(HOLD_DATA_GUARD_BLOCKED)
    assert "exits are paused" in view.hold_reason_text.lower()
    # Rule: a reason code never reaches the screen. `format.py` is the one place a code
    # becomes English, and a row that leaked the code would still pass a non-empty check.
    assert HOLD_DATA_GUARD_BLOCKED not in view.hold_reason_text

    sent = live_position.payload()
    assert sent["hold_reason"] == HOLD_DATA_GUARD_BLOCKED
    assert sent["hold_reason_text"] == REASON_PROSE[HOLD_DATA_GUARD_BLOCKED]


def test_an_unheld_position_shows_no_hold_and_the_cell_is_blank(live_position: Any) -> None:
    """The negative, driven **after** a real hold rather than from a fresh row.

    `code-standards.md`, from this lane and this phase: a test that asserts a field is
    clear against a row that never carried a value is satisfied by the model's own
    default, and C-models' `test_the_hold_reason_is_written_and_then_cleared` passed under
    its own mutation for exactly that reason. So the hold is planted first and then the
    block is lifted, and the clearing has something to clear.

    The blank is a blank and not the word for an absence: a cell reading "None" or
    "no hold" in a column that is empty on almost every row is furniture.
    """
    live_position.manage(live_position.below, blocked="data_guard")
    assert live_position.view().hold_reason == HOLD_DATA_GUARD_BLOCKED

    live_position.manage(live_position.above)
    cleared = live_position.view()
    assert cleared.hold_reason is None
    assert cleared.hold_reason_text == ""


def test_the_hold_is_the_only_thing_the_block_changes_about_the_row(
    live_position: Any,
) -> None:
    """A held position is still watched, and the screen has to keep saying so.

    `REASON_PROSE`'s sentence for this code promises the position is still watched. That
    promise is only true if the mark keeps moving through the hold, so it is asserted
    rather than trusted: engine 21 marks on a held tick and skips only the barriers.
    """
    live_position.manage(live_position.below)
    live_position.manage(live_position.above, blocked="data_guard")

    held = live_position.view()
    assert held.hold_reason == HOLD_DATA_GUARD_BLOCKED
    assert held.last_price == live_position.above, "the hold froze the mark; the position is not watched"
    assert held.unrealised_pnl == live_position.qty * (live_position.above - live_position.entry_price)


# --------------------------------------------------------------------------- #
# Rule 5 on the position row
# --------------------------------------------------------------------------- #


def test_a_position_the_daemon_has_stopped_touching_is_reported_stale(
    live_position: Any,
) -> None:
    """The reader's half of rule 5, on a row that is actually old.

    Driven by moving the **console's** clock past `console.stale_after_ms` rather than by
    ageing the row, because the console is a separate process and its clock is the only
    thing it has: a reader that judged staleness from anything the row itself carries
    would report a screen fresh while the daemon was dead.

    The fresh reading is taken as well. A staleness test that only ever observes `True`
    is satisfied by a reader that returns `True` unconditionally, which would fade every
    figure on the screen permanently — the failure `ui-context.md` names for a slow poll.
    """
    live_position.manage(live_position.below)

    fresh = live_position.view(minutes=0)
    assert fresh.staleness.is_stale is False
    assert fresh.staleness.age_us == 0, (
        "the console is reading at the instant the daemon wrote, so the row is not merely "
        "fresh - it is new, and a clamped negative age would be a different fact"
    )

    stale = live_position.view(minutes=5)
    assert stale.staleness.is_stale is True
    assert stale.staleness.age_us > STALE_AFTER_MS * 1000
    assert stale.staleness.age_text

    # The two ages still answer two different questions and must not be collapsed.
    assert stale.age_us != stale.staleness.age_us
