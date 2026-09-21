"""The band says whose money the balance is. Phase 8, D11 Part 1, operator ruling 2026-09-21.

The smoke run of 2026-09-21 put **`5,000.00 USD` under the word "Balance"** beside live Kraken
quotes. That figure was `paper.starting_balances` — invariant 2's paper-ledger ruling makes the
paper broker the authority on its own cash, so in paper mode the number on screen has nothing to
do with the Kraken account, which engine 1 fetches on every tick and nothing persists.

**Part 2 — actually showing the real wallet — is not built here.** It needs a store write and a
migration, and the operator rules on the schema after D10. This is the labelling half only, so
the screen stops implying something untrue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from acsoe.console.payloads import state_payload
from acsoe.console.reader import (
    BALANCE_LABELS,
    LIVE_MODE,
    UNKNOWN_BALANCE_LABEL,
    ConsoleReader,
    _balance_source,
)

#: `console.stale_after_ms`'s value in the other console tests. Nothing here depends on it;
#: `ConsoleReader` validates it, so it has to be a real number.
STALE_AFTER_MS = 120_000

TEMPLATE_REL = Path("src") / "acsoe" / "console" / "templates" / "index.html"
SCRIPT_REL = Path("src") / "acsoe" / "console" / "static" / "console.js"


@pytest.fixture
def seeded_reader(seeded_db: Path, seed_clock: Any) -> Any:
    """Same shape as `test_reader.py`'s. A local fixture rather than a shared one, because
    the reader owns a connection and each test wants it closed."""
    reader = ConsoleReader(seeded_db, clock=seed_clock, stale_after_ms=STALE_AFTER_MS)
    try:
        yield reader
    finally:
        reader.close()


@pytest.fixture
def template(repo_root: Path) -> str:
    return (repo_root / TEMPLATE_REL).read_text(encoding="utf-8")


@pytest.fixture
def script(repo_root: Path) -> str:
    return (repo_root / SCRIPT_REL).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# The rule, without a database
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("mode", "simulated", "label"),
    [
        ("paper", True, "Paper balance"),
        ("replay", True, "Replay balance"),
        ("live", False, "Balance"),
    ],
)
def test_each_mode_names_its_own_balance(mode: str, simulated: bool, label: str) -> None:
    assert _balance_source(mode) == (simulated, label)


def test_only_live_is_not_simulated() -> None:
    """The one mode in which the figure is money that exists. Asserted over the whole
    table rather than the three cases above, so a mode added later has to choose."""
    for mode in BALANCE_LABELS:
        simulated, _label = _balance_source(mode)
        assert simulated == (mode != LIVE_MODE)


@pytest.mark.parametrize("mode", ["", "paper-ish", "LIVE", "Live", "backtest"])
def test_an_unrecognised_mode_reads_as_simulated(mode: str) -> None:
    """Not a guess: the claim is "this is not `live`", which is what the string says.

    Note `LIVE` and `Live` — the comparison is exact, so a differently-cased value does not
    quietly become the one mode that means real money.
    """
    assert _balance_source(mode) == (True, UNKNOWN_BALANCE_LABEL)


def test_every_label_is_sentence_case() -> None:
    """`ui-context.md`: sentence case everywhere, no all-caps labels."""
    for label in (*BALANCE_LABELS.values(), UNKNOWN_BALANCE_LABEL):
        assert label == label[0].upper() + label[1:].lower()


def test_no_label_is_the_bare_word_balance_except_in_live() -> None:
    """The defect this closes: a figure labelled only "Balance" while it is simulated."""
    for mode, label in BALANCE_LABELS.items():
        if mode != LIVE_MODE:
            assert label != "Balance"


# --------------------------------------------------------------------------- #
# Through the reader and the payload
# --------------------------------------------------------------------------- #


def test_the_band_carries_the_label_and_the_fact(seeded_reader: ConsoleReader) -> None:
    band = seeded_reader.status_band(mode="paper")

    assert band.balance_is_simulated is True
    assert band.balance_label == "Paper balance"
    assert band.balance is not None, "the figure itself is unchanged by this"


def test_the_payload_carries_both(seeded_reader: ConsoleReader) -> None:
    """The boolean travels beside the words, so a later reader — the real-balance panel of
    Part 2, a digest, a test — does not have to parse a display string back into a fact."""
    payload = state_payload(seeded_reader.status_band(mode="paper"), seeded_reader.positions())

    assert payload["band"]["balance_is_simulated"] is True
    assert payload["band"]["balance_label"] == "Paper balance"


def test_a_live_band_says_balance(seeded_reader: ConsoleReader) -> None:
    """The other half. `mode: live` is refused by the config loader today, so this is the
    only place the live reading is exercised at all — and it must not say "Paper"."""
    band = seeded_reader.status_band(mode="live")

    assert band.balance_is_simulated is False
    assert band.balance_label == "Balance"


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


def test_the_markups_default_does_not_imply_real_money(template: str) -> None:
    """A page that has not yet received a payload renders whatever the template says. It
    must not be the word that means the Kraken account."""
    markup = template

    assert 'data-field="balance-label"' in markup, "the server has no hook to fill"
    assert ">Paper balance<" in markup
    assert ">Balance<" not in markup


def test_the_page_fills_the_label_from_the_payload(script: str) -> None:
    """Server-side wording, applied by the page — the same division as every other reading
    in the band. Without this the label would be frozen at the markup's default and would
    be wrong in live mode."""
    assert 'byField("balance-label")' in script


def test_the_reader_is_the_only_place_that_decides(script: str) -> None:
    """The page must not infer the wording from the mode word itself: two places deciding
    what a number means is how they come to disagree."""
    assert "balance_label" in script
    assert "Paper balance" not in script, "the page is restating a server decision"
