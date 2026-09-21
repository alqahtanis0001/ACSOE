"""Pair rules and balances speak the engines' own asset names. Phase 8, F3.

REST keys a pair `XXBTZUSD`, with base `XXBT` and quote `ZUSD`; engine 3 publishes quotes under
the v2 symbol `BTC/USD`, and `Balance` answers in the same legacy codes. Engine 7 scans the union
of the pair-rule keys and the quote keys, and matches each pair's quote against the balances
**and** against `trading.stable_quote_currencies`. So with the REST spellings:

* every pair is excluded as having no rules, and every quoted symbol likewise from the other side;
* engine 2 derives the **websocket subscription** from those same keys, so the daemon subscribes
  with symbols the v2 feed rejects and receives no market data at all;
* normalising only the pairs would exclude every pair for want of a quote balance instead, and
  normalising neither would exclude every pair as not provably stable.

The ground truth is spec 127's pair of recordings: the real REST body, and the name join taken
from the v2 `instrument` snapshot captured beside it.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from acsoe.clients.kraken.rest import (
    WS_ASSET_ALIASES,
    asset_code_names,
    map_asset_pairs,
    map_balances,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "kraken"
RECORDED_BODY = FIXTURES / "asset_pairs_recorded_2026-09-19.json"
RECORDED_NAMES = FIXTURES / "pair_names_recorded_2026-09-19.json"
INVENTED_BODY = FIXTURES / "asset_pairs.json"


@pytest.fixture(scope="module")
def recorded() -> dict[str, Any]:
    """The real `AssetPairs` body. Spec 127 records the response verbatim, so `payload` is the
    raw JSON text rather than a parsed object."""
    recording = json.loads(RECORDED_BODY.read_text(encoding="utf-8"))
    payload = recording["payload"]
    body = json.loads(payload) if isinstance(payload, str) else payload
    result: dict[str, Any] = body["result"]
    return result


@pytest.fixture(scope="module")
def recorded_symbols() -> set[str]:
    names = json.loads(RECORDED_NAMES.read_text(encoding="utf-8"))["pairs"]
    return {entry["v2_symbol"] for entry in names.values() if entry.get("v2_symbol")}


def test_every_recorded_pair_is_keyed_by_the_engines_own_name(
    recorded: dict[str, Any], recorded_symbols: set[str]
) -> None:
    snapshot = map_asset_pairs(recorded, fetched_at=0)

    assert len(snapshot.pairs) == len(recorded), "a pair was dropped by the renaming"
    strays = sorted(set(snapshot.pairs) - recorded_symbols)
    assert not strays, f"{len(strays)} pairs are not keyed as the v2 feed keys them: {strays[:5]}"


def test_the_legacy_prefixes_are_gone_from_keys_and_from_assets(
    recorded: dict[str, Any],
) -> None:
    """The specific shape of the defect: `XXBTZUSD`, base `XXBT`, quote `ZUSD`."""
    snapshot = map_asset_pairs(recorded, fetched_at=0)

    assert "XXBTZUSD" not in snapshot.pairs
    rule = snapshot.pairs["BTC/USD"]
    assert (rule.pair, rule.base, rule.quote) == ("BTC/USD", "BTC", "USD")
    assert not [p for p in snapshot.pairs if p.startswith(("XX", "ZZ")) or "/" not in p]


def test_the_two_renamed_assets_are_renamed(recorded: dict[str, Any]) -> None:
    """`XBT` is `BTC` and `XDG` is `DOGE` on the v2 feed. Both appear in the recording."""
    snapshot = map_asset_pairs(recorded, fetched_at=0)

    assert "BTC/USD" in snapshot.pairs
    assert "DOGE/USD" in snapshot.pairs
    assert snapshot.pairs["DOGE/USD"].base == "DOGE"
    assert set(WS_ASSET_ALIASES) == {"XBT", "XDG"}, "a third alias needs its own evidence"


def test_the_rule_comes_from_kraken_rather_than_from_stripping_prefixes(
    recorded: dict[str, Any],
) -> None:
    """`XTZ/USD` is the test that separates the two approaches: stripping a leading `X` turns
    Tezos into `TZ`, and Kraken's own `wsname` does not."""
    snapshot = map_asset_pairs(recorded, fetched_at=0)

    assert "XTZ/USD" in snapshot.pairs, sorted(p for p in snapshot.pairs if "TZ" in p)[:5]
    assert "TZ/USD" not in snapshot.pairs


def test_the_asset_map_is_derived_from_the_body(recorded: dict[str, Any]) -> None:
    names = asset_code_names(recorded)

    assert names["XXBT"] == "BTC"
    assert names["ZUSD"] == "USD"
    assert names["XETH"] == "ETH"
    assert names["XXDG"] == "DOGE" or names.get("XDG") == "DOGE"
    assert len(names) > 100, "the map should cover every asset the recording trades"


def test_balances_are_renamed_with_that_map(recorded: dict[str, Any]) -> None:
    """The half that makes engine 7's quote-balance and stable-quote tests line up."""
    names = asset_code_names(recorded)

    snapshot = map_balances(
        {"ZUSD": "1500.00", "XXBT": "0.25"}, fetched_at=0, asset_names=names
    )

    assert snapshot.balances == {"USD": Decimal("1500.00"), "BTC": Decimal("0.25")}


def test_an_unknown_asset_code_passes_through_rather_than_vanishing() -> None:
    """An asset with a balance is a balance even when no pair trades it. Dropping it would
    hide money; guessing at its name would invent one."""
    snapshot = map_balances(
        {"ZUSD": "10.00", "NEWCOIN": "3.00"}, fetched_at=0, asset_names={"ZUSD": "USD"}
    )

    assert snapshot.balances == {"USD": Decimal("10.00"), "NEWCOIN": Decimal("3.00")}


def test_two_codes_renaming_onto_one_name_are_summed_not_overwritten() -> None:
    """If Kraken ever lists one asset under two codes, the last writer must not win: that
    would silently shrink the account."""
    snapshot = map_balances(
        {"ZUSD": "10.00", "USD": "2.50"}, fetched_at=0, asset_names={"ZUSD": "USD"}
    )

    assert snapshot.balances == {"USD": Decimal("12.50")}


def test_balances_are_untouched_without_a_map() -> None:
    snapshot = map_balances({"USD": "5.00"}, fetched_at=0)

    assert snapshot.balances == {"USD": Decimal("5.00")}


def test_a_body_with_no_wsname_is_left_exactly_as_it_is() -> None:
    """The invented Phase 0 fixture, which the fake client serves and which is already keyed
    the way the engines key pairs. The renaming must not touch it."""
    invented = json.loads(INVENTED_BODY.read_text(encoding="utf-8"))
    result = invented.get("result", invented)

    snapshot = map_asset_pairs(result, fetched_at=0)

    assert set(snapshot.pairs) == set(result), "the fake client's pairs were renamed"
    assert snapshot.pairs["BTC/USD"].quote == "USD"
    assert asset_code_names(result) == {"BTC": "BTC", "USD": "USD", "ETH": "ETH", "SOL": "SOL"}


def test_a_pair_with_neither_wsname_nor_assets_is_dropped_not_defaulted() -> None:
    """Rule 2: a pair whose rules cannot be read is blocked, never guessed at."""
    body = {
        "GOOD/USD": {
            "base": "GOOD",
            "quote": "USD",
            "ordermin": "1",
            "costmin": "5",
            "tick_size": "0.1",
            "lot_decimals": 8,
            "pair_decimals": 1,
        },
        "BROKEN": {"ordermin": "1", "costmin": "5", "tick_size": "0.1"},
    }

    snapshot = map_asset_pairs(body, fetched_at=0)

    assert set(snapshot.pairs) == {"GOOD/USD"}
