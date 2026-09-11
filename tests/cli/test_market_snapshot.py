"""The one line per tick that says what the daemon was looking at.

`state` is a fresh dict every tick and is discarded at the end of it, so engine
2's subscription and engine 3's quotes exist nowhere else. The recorder's archive
can be read a year later; the daemon's own view of the market cannot be
reconstructed from anything at all. **A tick that passes without this line is a
comparison that can never be made afterwards** — the same property that makes the
order book unbackfillable — which is why the assertions here are about the line
being written at all and about its shape surviving the log pipeline, rather than
about anything cosmetic.

Two of them carry real weight.

**`quotes` must be a list of objects, never a mapping keyed by pair.**
`platform/logging.py` redacts the value of any field whose *name* contains a token
like `key`, `sign`, `auth` or `nonce`, recursing through dicts. Keyed by pair, a
symbol containing one of those substrings loses its entire quote to `<redacted>` —
silently, every tick, for that pair alone — and `reconcile_spread.py` would simply
never see it. There would be no error and no gap in the file: just one pair
missing from a comparison nobody could redo.

**An empty subscription must still be logged.** "The daemon ran and subscribed to
nothing" and "the daemon was not running" are different facts, and a line that
appeared only when there was something to say would collapse them into one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from acsoe.cli.engine import MARKET_SNAPSHOT_EVENT, market_snapshot, run_loop
from acsoe.platform.logging import _redact_value, configure_logging

STAMP = "2026-09-11T19:30:00.000000Z"


def quote(pair: str, bid: str, ask: str, spread: str, pct: str) -> dict[str, Any]:
    """The shape engine 3 puts in `state`, from `Quote.state_dict()`."""
    return {
        "pair": pair,
        "ts": STAMP,
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "spread_pct": pct,
        "age_s": 0.5,
    }


def wired_state(cycle_id: int = 1) -> dict[str, Any]:
    return {
        "cycle_id": cycle_id,
        "system": {"mode": "paper", "close_intent": False},
        "market_data_recorder": {
            "subscription": ("ETH/USD", "BTC/USD"),
            "subscription_derived": True,
        },
        "market_sensor": {
            "quotes": {
                "BTC/USD": quote("BTC/USD", "99990", "100010", "20", "0.0002"),
                "ETH/USD": quote("ETH/USD", "3999.4", "4000.6", "1.2", "0.0003"),
            }
        },
    }


# --------------------------------------------------------------------------- #
# The shape
# --------------------------------------------------------------------------- #


def test_the_snapshot_carries_the_subscription_and_every_quote() -> None:
    snapshot = market_snapshot(wired_state())
    assert snapshot["subscription"] == ["BTC/USD", "ETH/USD"]
    assert snapshot["subscription_count"] == 2
    assert snapshot["subscription_derived"] is True
    assert [item["pair"] for item in snapshot["quotes"]] == ["BTC/USD", "ETH/USD"]
    first = snapshot["quotes"][0]
    assert first["bid"] == "99990"
    assert first["ask"] == "100010"
    assert first["spread_pct"] == "0.0002", "the derived spread is the point of the line"


def test_the_subscription_is_sorted_so_two_identical_ticks_are_identical() -> None:
    """A diff between two lines should mean the scope changed, not that a set
    iterated differently."""
    assert market_snapshot(wired_state())["subscription"] == ["BTC/USD", "ETH/USD"]


def test_quotes_is_a_list_of_objects_and_not_a_mapping() -> None:
    """**The shape is load-bearing.** See the module docstring."""
    quotes = market_snapshot(wired_state())["quotes"]
    assert isinstance(quotes, list)
    assert all(isinstance(item, dict) and "pair" in item for item in quotes)


def test_a_pair_whose_symbol_looks_like_a_credential_survives_redaction() -> None:
    """The assertion the list shape exists for.

    Run through the real redactor. Keyed by pair, `KEY/USD` and `SIGNA/USD` lose
    their whole quote to `<redacted>`; as a list, the symbol is a value and the
    redactor cannot reach it.
    """
    state = wired_state()
    state["market_sensor"]["quotes"]["KEY/USD"] = quote("KEY/USD", "9.99", "10.01", "0.02", "0.002")
    state["market_sensor"]["quotes"]["SIGNA/USD"] = quote("SIGNA/USD", "1", "1.01", "0.01", "0.01")

    redacted = _redact_value(market_snapshot(state))
    pairs = {item["pair"]: item for item in redacted["quotes"]}
    assert set(pairs) == {"BTC/USD", "ETH/USD", "KEY/USD", "SIGNA/USD"}
    assert pairs["KEY/USD"]["bid"] == "9.99"
    assert pairs["SIGNA/USD"]["spread_pct"] == "0.01"
    assert "<redacted>" not in json.dumps(redacted)


def test_the_same_quotes_keyed_by_pair_would_have_been_destroyed() -> None:
    """The control. Without it the test above passes against a redactor that does
    nothing, and proves nothing about the shape."""
    keyed = {"quotes": {"KEY/USD": {"bid": "9.99"}, "BTC/USD": {"bid": "1"}}}
    redacted = _redact_value(keyed)
    assert redacted["quotes"]["KEY/USD"] == "<redacted>"
    assert redacted["quotes"]["BTC/USD"] == {"bid": "1"}


# --------------------------------------------------------------------------- #
# The empty tick
# --------------------------------------------------------------------------- #


def test_a_tick_with_no_engines_wired_still_produces_a_line() -> None:
    """Engines 2 and 3 are registered but a bare `state` is what Phase 0 ticks
    produce, and what a test double produces. The line is still written, empty,
    because its absence has to mean "the daemon was not running"."""
    snapshot = market_snapshot({"cycle_id": 1, "system": {"mode": "idle"}})
    assert snapshot["subscription"] == []
    assert snapshot["subscription_count"] == 0
    assert snapshot["quotes"] == []
    assert snapshot["subscription_derived"] is False


@pytest.mark.parametrize("value", [None, "not a mapping", 42, []])
def test_a_malformed_state_region_is_survived(value: Any) -> None:
    """The loop must never die of the shape of something an engine published.

    A daemon that crashed on a tick because a key was the wrong type would stop
    recording market data, which costs more than the line is worth.
    """
    snapshot = market_snapshot(
        {"cycle_id": 1, "market_data_recorder": value, "market_sensor": value}
    )
    assert snapshot["subscription"] == []
    assert snapshot["quotes"] == []


def test_a_quote_missing_a_field_is_carried_with_what_it_has() -> None:
    """Dropping the whole quote because one field is absent would silently remove
    a pair from the comparison; carrying it lets the reconciler decide."""
    state = wired_state()
    state["market_sensor"]["quotes"]["XRP/USD"] = {"pair": "XRP/USD", "bid": "0.5"}
    quotes = {item["pair"]: item for item in market_snapshot(state)["quotes"]}
    assert quotes["XRP/USD"] == {"pair": "XRP/USD", "bid": "0.5"}


# --------------------------------------------------------------------------- #
# End to end, through the real loop and the real log pipeline
# --------------------------------------------------------------------------- #


class _StubOrchestrator:
    """A stub of the ORCHESTRATOR, not of the logging.

    The point of this test is that `run_loop`, `structlog` and the file handler
    all really run — a hand-built line proves nothing about whether the daemon
    writes one.
    """

    run_id = "test-run"

    def __init__(self) -> None:
        self.cycle_id = 0

    def tick(self) -> dict[str, Any]:
        self.cycle_id += 1
        return wired_state(self.cycle_id)


def test_the_loop_writes_one_line_per_tick_at_info(tmp_path: Path) -> None:
    """At INFO and not DEBUG: this is a record, not a diagnostic, and the shipped
    `logging.level` is INFO. Logged at DEBUG it would not be written at all and
    both reconcilers would report nothing, with no error anywhere."""
    configure_logging(level="INFO", log_dir=tmp_path, retention_days=1)
    ticks = run_loop(_StubOrchestrator(), tick_seconds=0.001, max_ticks=3)
    assert ticks == 3

    written = (tmp_path / "acsoe.jsonl").read_text(encoding="utf-8")
    lines = [json.loads(raw) for raw in written.splitlines() if raw.strip()]
    snapshots = [line for line in lines if line.get("event") == MARKET_SNAPSHOT_EVENT]
    assert len(snapshots) == 3, "one line per tick, always"

    first = snapshots[0]
    assert first["cycle_id"] == 1
    assert first["mode"] == "paper"
    assert first["subscription"] == ["BTC/USD", "ETH/USD"]
    assert [item["pair"] for item in first["quotes"]] == ["BTC/USD", "ETH/USD"]
    # A timestamp the reconcilers can window on.
    assert datetime.fromisoformat(first["ts"].replace("Z", "+00:00")).tzinfo is not None
    assert first["ts"] <= datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def test_the_line_never_carries_a_credential(tmp_path: Path) -> None:
    """Invariant 13. The line is the largest thing the daemon logs, so it is the
    one most worth asserting about rather than assuming."""
    configure_logging(level="INFO", log_dir=tmp_path, retention_days=1)
    run_loop(_StubOrchestrator(), tick_seconds=0.001, max_ticks=1)
    written = (tmp_path / "acsoe.jsonl").read_text(encoding="utf-8")
    for forbidden in ("KRAKEN_API_KEY", "KRAKEN_API_SECRET", "api_sign", "otp"):
        assert forbidden not in written
