"""No money value reaches the browser through `float`. Specs 19 to 22.

`console/payloads.py` exists for one reason: FastAPI serialises a returned object
through `jsonable_encoder`, and `jsonable_encoder` renders a `Decimal` by calling
`float()` on it. Every money field on every view model is a `Decimal` that
deliberately *refuses* a float at the store boundary, and the response encoder
would have undone that on the way out, silently, for every price and every
balance the console serves.

The assertion here is deliberately **total**: the encoded body of every screen is
walked, and any JSON float anywhere in it fails. A list of exempted fields would
rot the first time a field was added; a total assertion cannot. What makes it
affordable is the decision recorded in `payloads.py` — the leaderboard's four
statistics are genuinely `float` and were never money, and they are sent as their
rendered text only.

Driven through the ASGI interface directly rather than `fastapi.testclient`, for
the reason `test_app.py` gives at length: the repository's network guard patches
`httpx.Client.send` for every test, and `TestClient` subclasses `httpx.Client`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.console.app import create_app
from acsoe.console.payloads import money, staleness_payload
from acsoe.console.reader import ConsoleReader
from acsoe.console.views import Staleness

STALE_AFTER_MS = 120_000

#: Every screen payload. `/health` is not one: it carries no figure.
SCREENS = ("/api/state", "/api/feed", "/api/history", "/api/research")


class _StubConfig:
    """The narrowest thing satisfying the `Config` Protocol."""

    ALLOWED = {"console.stale_after_ms": STALE_AFTER_MS, "console.poll_interval_ms": 500}

    def __init__(self, mode: str = "paper") -> None:
        self._mode = mode

    @property
    def mode(self) -> Any:
        return self._mode

    def get(self, dotted_key: str, /) -> Any:
        return self.ALLOWED[dotted_key]


async def _get(app: Any, path: str) -> tuple[int, bytes]:
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
    return int(status), body


@pytest.fixture
def console_app(seeded_db: Path, seed_clock: Any) -> Any:
    app = create_app(_StubConfig(), db_path=seeded_db, clock=seed_clock)
    try:
        yield app
    finally:
        app.state.reader.close()


def _floats(value: Any, path: str = "$") -> list[str]:
    """Every place a JSON float appears, named by its path.

    `bool` is checked before `int` because `bool` subclasses `int`; `int` is fine
    and `float` is not. Reported as paths rather than counted, so a failure says
    *which* field lost precision rather than that something did.
    """
    if isinstance(value, bool):
        return []
    if isinstance(value, float):
        return [f"{path} = {value!r}"]
    if isinstance(value, dict):
        found: list[str] = []
        for key, item in value.items():
            found.extend(_floats(item, f"{path}.{key}"))
        return found
    if isinstance(value, list):
        found = []
        for index, item in enumerate(value):
            found.extend(_floats(item, f"{path}[{index}]"))
        return found
    return []


# --------------------------------------------------------------------------- #
# The whole point of the module
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", SCREENS)
@pytest.mark.asyncio
async def test_no_screen_serves_a_json_float_anywhere(console_app: Any, path: str) -> None:
    """The assertion `payloads.py` claims, made against a populated database.

    An empty database would pass this trivially — there would be no money value to
    lose — so it runs against B's seed, where every screen carries figures.
    """
    status, body = await _get(console_app, path)
    assert status == 200
    assert _floats(json.loads(body)) == []


@pytest.mark.asyncio
async def test_the_seeded_screens_are_not_passing_this_vacuously(console_app: Any) -> None:
    """A guard on the guard: the bodies above must actually carry money.

    Without this, deleting every money field from the payloads would make the
    no-float assertion pass, which is the failure mode of every negative test.
    """
    _, body = await _get(console_app, "/api/state")
    payload = json.loads(body)
    assert payload["band"]["balance"] is not None
    assert Decimal(payload["band"]["balance"]) != 0
    assert payload["positions"]
    assert all(Decimal(row["entry_price"]) > 0 for row in payload["positions"])


@pytest.mark.asyncio
async def test_a_returned_view_model_would_have_failed_this(console_app: Any) -> None:
    """Proof the encoder really does what the module says it does.

    `jsonable_encoder` is the reason `payloads.py` exists. If a future FastAPI
    stopped floating a `Decimal`, this test fails and the module's justification
    has to be re-read rather than assumed — which is better than the module
    quietly becoming ceremony.
    """
    from fastapi.encoders import jsonable_encoder

    encoded = jsonable_encoder({"price": Decimal("0.123456789012345678")})
    assert isinstance(encoded["price"], float)
    assert str(encoded["price"]) != "0.123456789012345678"


# --------------------------------------------------------------------------- #
# The two helpers everything else is built from
# --------------------------------------------------------------------------- #


def test_money_emits_the_exact_decimal_string_and_never_scientific_notation() -> None:
    """`str(Decimal("1E+3"))` is `"1E+3"`. A consumer parsing the field should not
    have to know that, and it reads as noise in a payload."""
    assert money(Decimal("1E+3")) == "1000"
    assert money(Decimal("0.123456789012345678")) == "0.123456789012345678"
    assert money(None) is None


def test_money_keeps_the_trailing_zeros_the_writer_chose() -> None:
    """They are the quantum. `Decimal("1000.00")` means cents and `Decimal("1000")`
    means units, and normalising the difference away throws the precision that came
    from the exchange's own `pair_decimals`."""
    assert money(Decimal("1000.00")) == "1000.00"
    assert money(Decimal("1000")) == "1000"


def test_staleness_payload_is_none_when_there_is_no_figure_to_age() -> None:
    assert staleness_payload(None) is None


def test_staleness_payload_carries_the_threshold_it_was_judged_against() -> None:
    """The browser must not re-derive staleness from a number of its own. It is
    told what the threshold was and what the verdict is."""
    payload = staleness_payload(
        Staleness(age_us=1, stale_after_ms=STALE_AFTER_MS, is_stale=False, age_text="0ms")
    )
    assert payload is not None
    assert payload["stale_after_ms"] == STALE_AFTER_MS
    assert payload["is_stale"] is False
    assert payload["age_text"] == "0ms"


def test_an_age_in_milliseconds_is_a_display_value_derived_after_the_verdict() -> None:
    """One microsecond past the threshold is stale, and floors to exactly the
    threshold in millisecond arithmetic. The comparison happens before the
    conversion for exactly this case."""
    reader = ConsoleReader.__new__(ConsoleReader)
    reader._stale_after_ms = STALE_AFTER_MS
    stale = reader.staleness(0, now=STALE_AFTER_MS * 1_000 + 1)
    fresh = reader.staleness(0, now=STALE_AFTER_MS * 1_000)
    assert stale.is_stale is True
    assert fresh.is_stale is False
    assert stale.age_ms == fresh.age_ms == STALE_AFTER_MS


def test_every_position_payload_carries_the_age_the_page_renders(
    seeded_db: Path, seed_clock: Any
) -> None:
    """Spec 101. The page reads `age_text` and nothing derives it in the browser.

    `ui-context.md` scope limit for spec 101: the console computes no PnL and no age of
    its own beyond formatting what it was handed. A page that worked out an age from
    `opened_at` in JavaScript would be reading the *browser's* clock, which belongs to
    neither the daemon nor the console and is the one clock in the picture nobody
    controls.
    """
    from acsoe.console.payloads import _position_payload
    from acsoe.console.reader import ConsoleReader

    reader = ConsoleReader(seeded_db, clock=seed_clock, stale_after_ms=30_000)
    try:
        view = reader.positions()[0]
    finally:
        reader.close()
    payload = _position_payload(view)
    assert payload["age_text"] == view.age_text
    assert "age_us" not in payload, (
        "the raw microsecond age is a reader-side value; sending it invites the page to "
        "recompute the text from it"
    )
