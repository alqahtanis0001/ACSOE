"""Spec 86 step 1 — the paper broker is wired in by `build_clients`, in paper mode only.

**Every assertion here goes through `build_clients`.** That is the whole point of the
file and it is not a style preference. A-2's Phase 2 tripwire,
`test_a_tick_over_the_real_registry_records_errors_rather_than_raising`, was written to
turn red the day the daemon was wired to real clients and stayed green through exactly
that change — because it constructed the empty `Clients()` **itself** instead of going
through `cli/engine.py`. It pinned a fact the test supplied, so replacing the daemon's
wiring could not move it. `code-standards.md` states the rule it produced: *a test whose
purpose is "this goes red when X changes" must reach X through the code path X lives
on.* A hand-built `Clients(kraken=PaperBroker(...))` here would assert that the test can
call a constructor.

**The live and replay cases use a real `Config` with one field changed.** `load_config`
refuses `mode: live` outright — invariant 1, until `live_guard.py` lands in Phase 8 —
so there is no file that produces one, and `model_copy` is how the branch gets exercised
at all. A test asserts the loader still refuses, beside the wiring test, so the two facts
are separate: *live is unreachable today* and *if it were reached, it would get the bare
client*.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.cli.engine import build_clients, close_clients
from acsoe.clients.kraken import (
    KrakenClient,
    OrderClientProtocol,
    OrderRequest,
    OrderSide,
    OrderType,
)
from acsoe.clients.paper.broker import PaperBroker
from acsoe.platform.clock import FixedClock
from acsoe.platform.config import Config, ConfigError, load_config
from acsoe.platform.paths import ensure_runtime_directories

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = REPO_ROOT / "config" / "default.yaml"
FIXED_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def shipped_config() -> Config:
    """The committed `config/default.yaml`, loaded without touching `.env`.

    The shipped file rather than a fabricated one, because the question this file
    asks is what the *daemon* builds, and the daemon is started against this file.
    `load_env=False` so a developer's key cannot change the answer.
    """
    return load_config(DEFAULT_YAML, load_env=False)


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cleared explicitly rather than hoped about, so this passes on a keyed machine."""
    monkeypatch.delenv("KRAKEN_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_API_SECRET", raising=False)


def clients_for(config: Config, tmp_path: Path) -> Any:
    return build_clients(config, FixedClock(FIXED_NOW), ensure_runtime_directories(tmp_path))


def as_mode(config: Config, mode: str) -> Config:
    """The same config with one field changed, validators not re-run.

    `model_copy` deliberately: every other field is the shipped one, so the object
    under test differs from the daemon's in exactly the dimension the test is about.
    """
    return config.model_copy(update={"mode": mode})


# --------------------------------------------------------------------------- #
# Which object each mode receives
# --------------------------------------------------------------------------- #


def test_paper_mode_receives_the_paper_broker(shipped_config: Config, tmp_path: Path) -> None:
    clients = clients_for(shipped_config, tmp_path)
    try:
        assert shipped_config.mode == "paper", "the shipped config is paper; invariant 1"
        assert isinstance(clients.kraken, PaperBroker)
    finally:
        close_clients(clients)


@pytest.mark.parametrize("mode", ["live", "replay"], ids=["live", "replay"])
def test_no_other_mode_receives_the_paper_broker(
    shipped_config: Config, tmp_path: Path, mode: str
) -> None:
    """`live` for the obvious reason; `replay` because the wiring tests `== "paper"`.

    A simulator reached in live mode would place no real order while the system
    believed it had — a position it thinks it holds and does not, which is the worst
    failure this system has. `replay` is here because the wiring is written as
    `== "paper"` rather than `!= "live"`, and this is the test that would notice
    someone "simplifying" it to the negative form: the two read the same today and
    stop reading the same the moment a fourth mode exists.
    """
    clients = clients_for(as_mode(shipped_config, mode), tmp_path)
    try:
        assert isinstance(clients.kraken, KrakenClient)
        assert not isinstance(clients.kraken, PaperBroker)
    finally:
        close_clients(clients)


def test_the_loader_still_refuses_live_so_that_branch_is_unreachable_today(
    shipped_config: Config, tmp_path: Path
) -> None:
    """The other half of the pair above, kept separate on purpose.

    The wiring test says what live *would* get. This says live cannot be loaded at
    all, so nothing about the test above is a claim that live mode works. Both have to
    be true, and one moving without the other is a change somebody should see.
    """
    import yaml

    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    raw["mode"] = "live"
    path = tmp_path / "live.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8", newline="")

    with pytest.raises(ConfigError, match=re.escape("live_guard.py")):
        load_config(path, load_env=False)


def test_the_broker_wraps_the_real_client_rather_than_replacing_it(
    shipped_config: Config, tmp_path: Path
) -> None:
    """Paper mode still reaches the exchange for reads and for the stream.

    The broker answers the four order calls and forwards everything else, so a paper
    run still records the order book, still builds candles and still measures a real
    spread. If it replaced the client instead of wrapping it, the recording — the one
    thing that cannot be recovered later — would stop.
    """
    clients = clients_for(shipped_config, tmp_path)
    try:
        assert clients.kraken.subscription == ()
        assert callable(clients.kraken.drain)
        assert callable(clients.kraken.latest_quote)
    finally:
        close_clients(clients)


# --------------------------------------------------------------------------- #
# The seam: A's protocol against B's broker, with no double on either side
# --------------------------------------------------------------------------- #
#
# Spec 84 landed `OrderClientProtocol` with no consumer, so every test of it was a
# test of A's own models and A's own refusal. Phase 4 found what that costs twice in
# one day — A built engine 23 against `label_bars(...)`, a signature agreed by message
# that never existed, and nothing went red because everything drove a double. These
# two tests have no double on either side: B's real `PaperBroker`, built by the real
# `build_clients`, against A's real protocol and A's real `OrderRequest`.


def test_the_object_paper_mode_gets_satisfies_the_order_surface(
    shipped_config: Config, tmp_path: Path
) -> None:
    clients = clients_for(shipped_config, tmp_path)
    try:
        assert isinstance(clients.kraken, OrderClientProtocol)
    finally:
        close_clients(clients)


@pytest.mark.asyncio
async def test_an_order_in_paper_mode_never_reaches_the_live_client_s_refusal(
    shipped_config: Config, tmp_path: Path
) -> None:
    """The seam, asserted by where the failure comes from rather than by a type check.

    With no credentials the broker cannot price a fill — `TradeVolume` gives nothing
    and `AGENTS.md` forbids a remembered fee — so this call fails either way. **Which**
    failure arrives is the evidence: the live client's refusal names Phase 8, and if
    the wrap were missing or the broker delegated the call, that is the message that
    would come back. Anything else means the broker answered it itself.

    `isinstance` against the protocol cannot show this. A `runtime_checkable` Protocol
    checks that the four names exist, and the bare `KrakenClient` has all four — they
    are the ones that refuse.
    """
    clients = clients_for(shipped_config, tmp_path)
    request = OrderRequest(
        pair="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        qty=Decimal("0.001"),
        limit_price=Decimal("50000.00"),
        post_only=True,
        userref=860001,
    )
    try:
        outcome: object
        try:
            outcome = await clients.kraken.add_order(request)
        # Deliberately broad, and not re-raised: the exception IS the observation.
        # Narrowing it to a type would pre-judge which layer answered, which is the
        # one thing this test exists to find out.
        except Exception as exc:
            outcome = exc
        assert "Phase 8" not in str(outcome), (
            "the order reached the live client's Phase 8 refusal, so paper mode is "
            f"not wrapped: {outcome}"
        )
    finally:
        close_clients(clients)
