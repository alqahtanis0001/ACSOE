"""The research views: the leaderboard, and the SHAP pane's honest absence. Spec 22.

The operator's first addition at approval: **spec 22 stands as written. The SHAP
pane is an empty state. Do not design a view for data that arrives in Phase 5.**

That ruling is enforced here rather than remembered. `ShapPane` carries three
fields — `available`, `produced_in_phase`, `message` — and has nowhere to put a
row, so serving one would take a change to the model, the payload and this file
together. A figure that looks like attribution and is not is worse than no
figure, because the operator cannot tell them apart.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from acsoe.console.app import TEMPLATE_PATH, create_app
from acsoe.console.reader import SHAP_EMPTY_STATE, ConsoleReader
from acsoe.console.views import SHAP_PRODUCED_IN_PHASE, LeaderboardEntryView, ResearchView

STALE_AFTER_MS = 120_000

#: Anything that would draw. Asserted against the research markup, because the
#: pane's emptiness has to hold on the page as well as in the payload.
_CHART_ELEMENTS = ("<canvas", "<svg", "<chart", "plotly", "chart.js", "d3.")


class _StubConfig:
    ALLOWED = {"console.stale_after_ms": STALE_AFTER_MS, "console.poll_interval_ms": 500}

    @property
    def mode(self) -> Any:
        return "paper"

    def get(self, dotted_key: str, /) -> Any:
        return self.ALLOWED[dotted_key]


async def _get(app: Any, path: str) -> tuple[int, dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"console.test")],
        "client": ("test", 0),
        "server": ("console.test", 80),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return int(status), json.loads(body)


@pytest.fixture
def console_app(seeded_db: Path, seed_clock: Any) -> Any:
    app = create_app(_StubConfig(), db_path=seeded_db, clock=seed_clock)
    try:
        yield app
    finally:
        app.state.reader.close()


@pytest.fixture
def seeded_reader(seeded_db: Path, seed_clock: Any) -> Any:
    reader = ConsoleReader(seeded_db, clock=seed_clock, stale_after_ms=STALE_AFTER_MS)
    try:
        yield reader
    finally:
        reader.close()


# --------------------------------------------------------------------------- #
# The leaderboard renders from the seed
# --------------------------------------------------------------------------- #


def test_the_leaderboard_renders_from_the_seed(seeded_reader: ConsoleReader) -> None:
    view = seeded_reader.research()
    assert isinstance(view, ResearchView)
    assert view.leaderboard
    assert all(isinstance(row, LeaderboardEntryView) for row in view.leaderboard)


def test_a_leaderboard_row_renders_every_metric_as_a_string_too(
    seeded_reader: ConsoleReader,
) -> None:
    """The screens must not each decide where a sign or a placeholder goes.

    A metric that is `None` on the row renders as a statement of absence, never as
    a zero: a zero Sharpe is a result and a missing Sharpe is not.
    """
    for row in seeded_reader.research().leaderboard:
        assert row.win_rate_text
        assert row.sharpe_text
        assert row.brier_text
        if row.sharpe is None:
            assert "0" not in row.sharpe_text


def test_the_leaderboard_metrics_are_floats_and_the_money_is_not(
    seeded_reader: ConsoleReader,
) -> None:
    """A win rate is a statistic and was never a `Decimal`. `net_pnl` is money and
    stays one — that split is the whole reason the payload sends the metrics as
    text and lets the no-float assertion in `test_payloads.py` stay total."""
    from decimal import Decimal

    for row in seeded_reader.research().leaderboard:
        if row.win_rate is not None:
            assert isinstance(row.win_rate, float)
        if row.net_pnl is not None:
            assert isinstance(row.net_pnl, Decimal)


@pytest.mark.asyncio
async def test_the_research_endpoint_answers_over_the_seed(console_app: Any) -> None:
    status, body = await _get(console_app, "/api/research")
    assert status == 200
    assert body["leaderboard"]


# --------------------------------------------------------------------------- #
# The SHAP pane: no fabricated row, no chart element
# --------------------------------------------------------------------------- #


def test_the_shap_pane_is_unavailable_and_names_the_phase_that_produces_it(
    seeded_reader: ConsoleReader,
) -> None:
    pane = seeded_reader.research().shap
    assert pane.available is False
    assert pane.produced_in_phase == SHAP_PRODUCED_IN_PHASE == 5
    assert str(SHAP_PRODUCED_IN_PHASE) in pane.message
    # **Two numbers now, and the second is the one an operator needs.** Engine 8 computes
    # attributions on every prediction from Phase 5, so a message saying only "arrives in
    # Phase 5" would be false the moment a model is loaded — the operator would go looking
    # for a broken predictor rather than for a table nobody has built. What is absent is the
    # storage, and that is Phase 7 with the SHAP view (spec 71, step 6).
    assert str(SHAP_PRODUCED_IN_PHASE + 2) in pane.message
    assert "not stored" in pane.message
    assert pane.message == SHAP_EMPTY_STATE


def test_the_shap_model_has_nowhere_to_put_a_row() -> None:
    """The ruling made structural. Serving a fabricated explanation would take a
    change to the model, the payload and this test together, which is a deliberate
    act rather than a drift."""
    from acsoe.console.views import ShapPane

    assert set(ShapPane.model_fields) == {"available", "produced_in_phase", "message"}


@pytest.mark.asyncio
async def test_the_shap_payload_carries_no_row_and_no_chart(console_app: Any) -> None:
    """The assertion `payloads._shap_payload` names. Three keys, none of them a
    value, and nothing that could be plotted."""
    _, body = await _get(console_app, "/api/research")
    shap = body["shap"]
    assert set(shap) == {"available", "produced_in_phase", "message"}
    assert shap["available"] is False
    for forbidden in ("rows", "chart", "features", "values", "explanation"):
        assert forbidden not in shap


@pytest.mark.asyncio
async def test_no_research_payload_smuggles_a_shap_row_in_beside_the_leaderboard(
    console_app: Any,
) -> None:
    """The pane being empty is worth nothing if the row arrives under another key."""
    _, body = await _get(console_app, "/api/research")
    assert set(body) == {"leaderboard", "shap"}


def test_the_research_markup_draws_nothing_and_says_which_phase_produces_it() -> None:
    """The pane's emptiness holds on the page too, not only in the payload.

    `ui-context.md` leaves the visualisation undesigned on purpose, so there is
    nothing on this page that would draw one: no canvas, no inline SVG, and no
    charting library — which the page could not have fetched anyway, since it
    fetches nothing from a third party.
    """
    markup = TEMPLATE_PATH.read_text(encoding="utf-8").lower()
    section = _shap_section(markup)
    assert section, "the research pane has no shap region"
    for element in _CHART_ELEMENTS:
        assert element not in markup, element
    assert "phase 5" in section


def _shap_section(markup: str) -> str:
    match = re.search(r'data-region="shap".*?</section>', markup, re.S)
    return match.group(0) if match else ""


# --------------------------------------------------------------------------- #
# Spec 140: the leaderboard's verdict columns
# --------------------------------------------------------------------------- #


def _leaderboard_with(migrated_db: Path, rows: list[dict[str, Any]], clock: Any) -> list[Any]:
    from decimal import Decimal

    from acsoe.clients.store.client import StoreClient
    from acsoe.clients.store.contracts import LeaderboardRow

    with StoreClient(migrated_db) as store:
        for index, extra in enumerate(rows):
            store.write_leaderboard_entry(
                LeaderboardRow(
                    model_id=extra.pop("model_id", "predictor"),
                    model_version=f"v{index}",
                    trained_at=1_000 + index,
                    n_trades=10,
                    net_pnl=Decimal("1.00"),
                    updated_at=1_000 + index,
                    **extra,
                )
            )
    reader = ConsoleReader(migrated_db, clock=clock, stale_after_ms=STALE_AFTER_MS)
    try:
        return sorted(reader.leaderboard(), key=lambda row: row.model_version)
    finally:
        reader.close()


def test_a_fold_row_says_its_effective_sample_is_not_recorded_rather_than_zero(
    migrated_db: Path, fixed_clock: Any
) -> None:
    (row,) = _leaderboard_with(
        migrated_db, [{"fold": "3", "brier": 0.2, "base_rate_brier": 0.21}], fixed_clock
    )
    assert row.effective_sample_size is None
    assert row.effective_sample_size_text == "not recorded"
    assert row.base_rate_brier == 0.21
    assert row.base_rate_brier_text == "0.21"
    assert row.promotion_reason == ""


def test_a_judged_runs_reason_and_effective_sample_come_from_its_notes(
    migrated_db: Path, fixed_clock: Any
) -> None:
    from acsoe.console.format import REASON_PROSE

    notes = json.dumps(
        {"reason_code": "promotion_too_few_trades", "effective_sample_size": 7.25}
    )
    promoted_notes = json.dumps({"reason_code": None, "effective_sample_size": 30.0})
    rejected, promoted, free_text = _leaderboard_with(
        migrated_db,
        [
            {"model_id": "chain_run", "notes": notes},
            {"model_id": "chain_run", "notes": promoted_notes, "promoted": True},
            {"notes": "a Phase 0 seed note, not JSON"},
        ],
        fixed_clock,
    )
    assert rejected.promotion_reason == REASON_PROSE["promotion_too_few_trades"]
    assert rejected.effective_sample_size_text == "7.2"
    assert promoted.promotion_reason == ""
    assert promoted.effective_sample_size == 30.0
    assert free_text.promotion_reason == ""
    assert free_text.effective_sample_size is None


@pytest.mark.asyncio
async def test_the_research_payload_carries_the_verdict_columns_as_text(console_app: Any) -> None:
    _, body = await _get(console_app, "/api/research")
    row = body["leaderboard"][0]
    for key in ("base_rate_brier_text", "effective_sample_size_text", "promotion_reason"):
        assert isinstance(row[key], str), key


def test_the_leaderboard_markup_has_a_column_for_each_verdict_figure() -> None:
    markup = TEMPLATE_PATH.read_text(encoding="utf-8")
    for heading in ("Base-rate Brier", "Effective sample", "Deflated", "Promoted", "Why not"):
        assert f">{heading}</th>" in markup, heading
