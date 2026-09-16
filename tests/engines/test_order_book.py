"""Engine 9 `order_book` — spec 96.

The tests that carry the spec are `test_the_thin_pairs_walk_matches_the_hand_computation`
and `test_the_deep_pairs_walk_matches_the_hand_computation`: two real books, one 26 times
deeper than the other, walked at the same notional, against expectations written out level
by level from the fixture's own numbers.

The one that carries the *contract* is
`test_engine_nine_never_blocks_on_any_fail_closed_shape`, because engine 9 is not a gate
and the whole design rests on the refusal being engine 10's.

**No fixture here builds `state["exchange"]` by hand.** Every one is
`ExchangeEngine().process(...).data` verbatim — A's real engine 1 against C's fake Kraken
client — for the reason spec 40 wrote down: a mock that agrees with its caller is not a
test of the seam, and engine 10 read three wrong field names for a whole phase because
every test built the payload in the shape the reader expected.

**The book is not built by hand either.** It is replayed out of
`tests/fixtures/book_sample.jsonl`, thirty seconds of real `ADA/USD` and `BTC/USD` cut
from the live archive by A's `scripts/cut_book_fixture.py`. The archive records book
**deltas**, so `_replay_book` reconstructs each state from the window's opening snapshot;
`test_the_reconstructed_books_hold_ten_levels_a_side_and_never_cross` is the evidence that
reconstruction is faithful, over all 977 states in the file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterator, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.harness.doubles import MappingConfig, load_default_config

from acsoe.core.contracts import EngineStatus
from acsoe.engines.cost.engine import CostEngine
from acsoe.engines.exchange.engine import ExchangeEngine
from acsoe.engines.order_book.contracts import (
    BASIS_NOTIONAL_FIELD,
    DEPTH_KEY,
    ESTIMATED_SLIPPAGE_FIELD,
    LEVELS_CONSUMED_FIELD,
    REASON_BOOK_FETCH_FAILED,
    REASON_BOOK_TOO_THIN,
    REASON_BOOK_UNUSABLE,
    REASON_INPUTS_UNAVAILABLE,
    REASON_NO_QUOTE_BALANCE,
    walk_the_bid_side,
)
from acsoe.engines.order_book.engine import OrderBookEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "book_sample.jsonl"

#: The depth every frame in the fixture was recorded at — `scripts/record.py`'s
#: `DEFAULT_DEPTH`. It is not this test's choice: it is a fact about the archive, and it
#: is the ceiling on any `order_book.depth` a committed fixture can validate.
RECORDED_DEPTH = 10

THIN = "ADA/USD"
DEEP = "BTC/USD"

#: Kraken tier 3, from `trading-invariants.md`'s reference table, handed to the *fake
#: exchange* and published by A's real engine 1. At tier 1 the cost gate is unreachable by
#: construction, so the two-engine test below needs a better tier.
TIER_3 = {"tier": 3, "maker_fee_pct": "0.0022", "taker_fee_pct": "0.0038"}


# --------------------------------------------------------------------------- #
# Reading the fixture
# --------------------------------------------------------------------------- #


def _fixture_lines() -> tuple[dict[str, Any], list[bytes]]:
    """The header object and the raw body lines, read as bytes.

    Line 1 is A's header and is **not** a recorded frame — it carries `_fixture` so a
    reader can tell in one key. Read as bytes because `tests/fixtures/` is marked `-text`
    in `.gitattributes` precisely so nothing rewrites the committed bytes, and a text-mode
    read on Windows would hide a CRLF that a byte-for-byte checksum is supposed to catch.
    """
    with FIXTURE.open("rb") as handle:
        header = json.loads(handle.readline())
        body = [line for line in handle if line.strip()]
    return header, body


def _replay_book(
    pair: str, *, depth: int = RECORDED_DEPTH
) -> Iterator[tuple[str, str, tuple[tuple[Decimal, Decimal], ...], tuple[tuple[Decimal, Decimal], ...]]]:
    """Every book state of `pair` in the fixture, oldest first.

    Kraken v2 sends one `snapshot` at subscribe and `update` deltas thereafter: a `qty` of
    zero deletes a level, anything else inserts or replaces one, and the side is truncated
    back to the subscribed depth. That truncation is not cosmetic — without it a level
    that fell off the bottom would be resurrected the next time a deeper level was
    deleted, and the book would slowly grow past the depth Kraken maintains.

    Yields `(ts_recv, frame type, bids, asks)` with prices and quantities as `Decimal`,
    built from the recorded strings through `str()` so no float ever exists.
    """
    _, body = _fixture_lines()
    bids: dict[Decimal, Decimal] = {}
    asks: dict[Decimal, Decimal] = {}
    for raw in body:
        frame = json.loads(raw)
        if frame.get("pair") != pair:
            continue
        payload = frame["payload"]
        data = payload["data"][0]
        if payload["type"] == "snapshot":
            bids, asks = {}, {}
        for side_name, side in (("bids", bids), ("asks", asks)):
            for level in data.get(side_name) or []:
                price = Decimal(str(level["price"]))
                quantity = Decimal(str(level["qty"]))
                if quantity == 0:
                    side.pop(price, None)
                else:
                    side[price] = quantity
        top_bids = tuple(sorted(bids.items(), key=lambda item: -item[0]))[:depth]
        top_asks = tuple(sorted(asks.items(), key=lambda item: item[0]))[:depth]
        bids, asks = dict(top_bids), dict(top_asks)
        yield frame["ts_recv"], payload["type"], top_bids, top_asks


def _first_book(pair: str) -> tuple[tuple[Decimal, Decimal], ...]:
    """The bid side of the fixture's opening snapshot for `pair`."""
    _, frame_type, bids, _ = next(iter(_replay_book(pair)))
    assert frame_type == "snapshot", (
        f"the first {pair} frame in the fixture is a {frame_type!r}, so there is no "
        "absolute book to start from — re-cut the window at a resubscribe"
    )
    return bids


def _as_strings(
    levels: tuple[tuple[Decimal, Decimal], ...],
) -> list[tuple[str, str]]:
    """Levels in the shape `FakeKrakenClient.set_order_book` takes."""
    return [(format(price, "f"), format(quantity, "f")) for price, quantity in levels]


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #


def _config_with_depth(depth: Any = RECORDED_DEPTH) -> MappingConfig:
    """`config/default.yaml` with `order_book.depth` **overridden**.

    Used only where a test needs a depth the shipped file does not carry — depth 2 to
    show the key bounds the walk, and the unusable values to show the engine declines
    rather than defaulting. **The success path does not come through here.** It uses the
    real `paper_config`, which declares `order_book.depth: 10` since the lead landed
    spec 80's debt, so the tests that matter most run against the real config object and
    not against a double of it.
    """
    raw = _raw_default_config()
    return MappingConfig({**raw, "order_book": {"depth": depth}})


def _config_without_order_book() -> MappingConfig:
    """`config/default.yaml` with no `order_book` section at all."""
    raw = {key: value for key, value in _raw_default_config().items() if key != "order_book"}
    return MappingConfig(raw)


def _raw_default_config() -> dict[str, Any]:
    import yaml

    path = REPO_ROOT / "config" / "default.yaml"
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _configured(context: Any, config: MappingConfig) -> Any:
    """`context` with a different config. `EngineContext` is frozen, so `replace`."""
    return dataclasses.replace(context, config=config)


@pytest.fixture
def book_context(engine_context: Any) -> Any:
    """`engine_context` unchanged — the real parsed `config/default.yaml`.

    No override. The lead landed `order_book.depth: 10` on 2026-09-16, so every success
    path below reads the shipped value through the same `Config` the daemon uses.
    `test_the_depth_the_tests_run_at_is_the_one_the_fixture_was_recorded_at` is what
    stops that silently becoming a depth the fixture cannot validate.
    """
    return engine_context


def _publish_exchange(
    context: Any,
    fake_kraken: Any,
    *,
    balances: Mapping[str, str] | None = None,
    fee_tier: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """`state["exchange"]`, produced by A's real engine 1 against C's fake client.

    Never built by hand. Engine 1 reads nothing out of `state`, so `{}` is a faithful
    argument rather than a shortcut.
    """
    fake_kraken.set_pair_rule(
        THIN,
        base="ADA",
        quote="USD",
        ordermin="5",
        costmin="1.00",
        tick_size="0.000001",
        lot_decimals=8,
        pair_decimals=6,
    )
    if balances is not None:
        fake_kraken.set_balances(balances)
    if fee_tier is not None:
        fake_kraken.set_fee_tier(**fee_tier)
    result = ExchangeEngine().process(context, {})
    assert result.status is EngineStatus.OK
    return dict(result.data)


def _state_for(
    context: Any,
    fake_kraken: Any,
    pair: str,
    *,
    balances: Mapping[str, str] | None = None,
    fee_tier: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "scout": {"pair": pair},
        "exchange": _publish_exchange(
            context, fake_kraken, balances=balances, fee_tier=fee_tier
        ),
    }


def _load_book_into(fake_kraken: Any, pair: str, index: int = 0) -> tuple[tuple[Decimal, Decimal], ...]:
    """Put the fixture's `index`-th book state for `pair` into the fake, and return the bids."""
    states = _replay_book(pair)
    for position, (_, _, bids, asks) in enumerate(states):
        if position == index:
            fake_kraken.set_order_book(pair, bids=_as_strings(bids), asks=_as_strings(asks))
            return bids
    raise AssertionError(f"the fixture holds fewer than {index + 1} states for {pair}")


# --------------------------------------------------------------------------- #
# The fixture itself
# --------------------------------------------------------------------------- #


def test_the_fixture_body_matches_the_checksum_its_own_header_claims() -> None:
    """Recompute the sha256, never read back the one the producer wrote.

    Ruling 7 on the DI, and the Phase 5 closing finding: a record of intent is not a
    record of what happened. A header that agreed with itself would prove nothing; this
    compares the header against the bytes on disk.
    """
    header, body = _fixture_lines()
    assert header["_fixture"] == "book_frames"
    digest = hashlib.sha256(b"".join(body)).hexdigest()
    assert digest == header["sha256_of_body"]


def test_the_fixture_holds_exactly_the_frames_its_header_counts() -> None:
    """Per pair, per frame type, counted from the body rather than trusted."""
    header, body = _fixture_lines()
    counted: dict[str, dict[str, int]] = {}
    for raw in body:
        frame = json.loads(raw)
        per_pair = counted.setdefault(str(frame["pair"]), {})
        kind = str(frame["payload"]["type"])
        per_pair[kind] = per_pair.get(kind, 0) + 1
    assert counted == header["lines"]["per_pair"]
    assert sorted(counted) == sorted(header["pairs"]) == [THIN, DEEP]


def test_the_fixture_is_stored_with_unix_line_endings() -> None:
    """`.gitattributes` marks `tests/fixtures/**` as `-text` for exactly this reason.

    A text-mode round trip on Windows rewrites every LF as CRLF, which changes the
    committed bytes and therefore the checksum above — silently, because git's clean
    filter normalises on the way into the index and `git status` reports nothing.
    """
    raw = FIXTURE.read_bytes()
    assert raw.count(b"\r\n") == 0


@pytest.mark.parametrize("pair", [THIN, DEEP])
def test_the_fixture_opens_with_a_snapshot_for_every_pair(pair: str) -> None:
    """Without one there is no absolute book in the file at all.

    Every frame after the first is a **delta**. A window cut anywhere but at a resubscribe
    would hold hundreds of real, byte-exact, entirely unusable frames, and would
    reconstruct into a plausible four-level book that a slippage walk prices as far
    thinner than the market was.
    """
    states = list(_replay_book(pair))
    assert states[0][1] == "snapshot"
    assert [kind for _, kind, _, _ in states[1:]] == ["update"] * (len(states) - 1)


@pytest.mark.parametrize("pair", [THIN, DEEP])
def test_the_reconstructed_books_hold_ten_levels_a_side_and_never_cross(pair: str) -> None:
    """The evidence that `_replay_book` rebuilds the real book and not an artefact of itself.

    Kraken maintains a depth-10 book, so after every single delta both sides must hold
    exactly ten levels, in strict price order, uncrossed. A reader that dropped a level, or
    resurrected one, or mis-ordered a side, breaks this within a handful of frames. It holds
    across every state in the file.
    """
    states = list(_replay_book(pair))
    assert len(states) >= 100
    for position, (timestamp, _, bids, asks) in enumerate(states):
        where = f"{pair} state {position} at {timestamp}"
        assert len(bids) == RECORDED_DEPTH, where
        assert len(asks) == RECORDED_DEPTH, where
        assert [price for price, _ in bids] == sorted(
            (price for price, _ in bids), reverse=True
        ), where
        assert [price for price, _ in asks] == sorted(price for price, _ in asks), where
        assert bids[0][0] < asks[0][0], where
        assert all(quantity > 0 for _, quantity in bids + asks), where


# --------------------------------------------------------------------------- #
# The walk, against hand computations
# --------------------------------------------------------------------------- #


def test_the_thin_pairs_walk_matches_the_hand_computation() -> None:
    """`ADA/USD`, the fixture's opening snapshot, $5,000 of quote balance.

    The ten bid levels, and their cumulative notional::

        L1   0.194674 x  3008.70000000 =  585.71566380   cum   585.71566380
        L2   0.194673 x   100.00000000 =   19.46730000   cum   605.18296380
        L3   0.194652 x  3079.12437480 =  599.35771780   cum  1204.54068160
        L4   0.194651 x  1030.33822061 =  200.55636498   cum  1405.09704658
        L5   0.194650  x 3451.71933202 =  671.87716798   cum  2076.97421456
        L6   0.194648 x  1226.99287505 =  238.83170914   cum  2315.80592370
        L7   0.194647 x  5608.14859176 = 1091.60929894   cum  3407.41522264
        L8   0.194645 x  2568.77854701 =  499.99990028   cum  3907.41512293
        L9   0.194630  x 1272.48972790 =  247.66467574   cum  4155.07979867
        L10  0.194629 x 16485.20893210 = 3208.49972925   cum  7363.57952791

    $5,000 is past L9's cumulative 4155.08 and inside L10, so the walk consumes **all ten
    levels** — the entire fetched depth, with $3,208 of L10 to spare. The base sold is the
    first nine levels' quantities in full plus `(5000 - 4155.07979867) / 0.194629`, the
    fill price is `5000 / base`, and the slippage is that against the 0.194674 top.
    """
    bids = _first_book(THIN)
    walk = walk_the_bid_side(bids, Decimal("5000"))
    assert walk is not None
    assert walk.levels_consumed == 10
    assert walk.best_bid == Decimal("0.194674")
    assert walk.fill_price == Decimal("0.1946473901839433686160148110")
    assert walk.slippage_pct == Decimal("0.0001366891113175430924786514892")


def test_the_deep_pairs_walk_matches_the_hand_computation() -> None:
    """`BTC/USD`, the fixture's opening snapshot, the same $5,000.

    The first four bid levels, and their cumulative notional::

        L1  75731.8 x 0.00069517 =     52.646475406   cum     52.646475406
        L2  75731.0 x 0.000051   =      3.862281      cum     56.508756406
        L3  75727.2 x 0.000051   =      3.8620872     cum     60.370843606
        L4  75726.8 x 1.06491467 =  80642.580232156   cum  80702.951075762

    $5,000 falls inside L4, so the walk stops there having touched **four** of ten
    levels — against the thin pair's ten, at the identical notional. That contrast is the
    point of committing two pairs: the same arithmetic, a book 26 times deeper, and
    slippage roughly half.
    """
    bids = _first_book(DEEP)
    walk = walk_the_bid_side(bids, Decimal("5000"))
    assert walk is not None
    assert walk.levels_consumed == 4
    assert walk.best_bid == Decimal("75731.8")
    assert walk.fill_price == Decimal("75726.85619614271459554707421")
    assert walk.slippage_pct == Decimal("0.00006528042192692375531712952815")


def test_the_thin_book_is_more_than_twice_as_expensive_as_the_deep_one() -> None:
    """The comparison the two fixtures exist to support, at one notional.

    Asserted as a relation rather than as two numbers, so it survives a re-cut of the
    fixture and still says the thing that matters: depth is what slippage measures.
    """
    thin = walk_the_bid_side(_first_book(THIN), Decimal("5000"))
    deep = walk_the_bid_side(_first_book(DEEP), Decimal("5000"))
    assert thin is not None and deep is not None
    assert thin.slippage_pct > deep.slippage_pct * 2
    assert thin.levels_consumed > deep.levels_consumed


def test_a_notional_that_fits_the_top_level_pays_no_slippage() -> None:
    """`ADA/USD` level 1 alone is $585.72, so $100 never leaves it.

    Exactly zero, not approximately: the fill price *is* the best bid. `Decimal`
    throughout is what makes that an equality rather than a tolerance.
    """
    walk = walk_the_bid_side(_first_book(THIN), Decimal("100"))
    assert walk is not None
    assert walk.levels_consumed == 1
    assert walk.fill_price == Decimal("0.194674")
    assert walk.slippage_pct == 0


def test_slippage_rises_with_size_on_the_same_book() -> None:
    """Monotone, which is the property the whole-balance upper bound rests on.

    The lead's ruling — estimate at the largest notional engine 11 could approve — is only
    an upper bound because slippage does not fall as size rises. If this were ever false
    the ruling would be unsound, so it is asserted rather than assumed.
    """
    bids = _first_book(THIN)
    previous = Decimal(-1)
    for notional in ("100", "600", "1500", "3000", "5000", "7000"):
        walk = walk_the_bid_side(bids, Decimal(notional))
        assert walk is not None, notional
        assert walk.slippage_pct >= previous, notional
        previous = walk.slippage_pct


def test_a_notional_past_the_fetched_depth_returns_nothing_rather_than_a_guess() -> None:
    """`ADA/USD`'s ten levels hold $7,363.58. $12,000 has nowhere to go.

    `None`, not a partial fill reported as a whole one. The levels the walk did not reach
    are by definition worse than the ones it did, so an extrapolation would be optimistic
    exactly where the risk is.
    """
    bids = _first_book(THIN)
    assert sum(price * quantity for price, quantity in bids) < Decimal("12000")
    assert walk_the_bid_side(bids, Decimal("12000")) is None


def test_the_whole_book_exactly_is_a_fill_and_one_cent_more_is_not() -> None:
    """The boundary, from both sides, because `>=` against `>` is a one-character mutation."""
    bids = _first_book(THIN)
    total = sum(price * quantity for price, quantity in bids)
    exact = walk_the_bid_side(bids, total)
    assert exact is not None
    assert exact.levels_consumed == RECORDED_DEPTH
    assert walk_the_bid_side(bids, total + Decimal("0.01")) is None


@pytest.mark.parametrize("through", [1, 2, 5, 9])
def test_a_notional_that_ends_exactly_on_a_level_consumes_that_level_and_no_more(
    through: int,
) -> None:
    """A basis equal to the cumulative notional through level N consumes exactly N.

    This is the case the `>=` at the level boundary decides, and it is the **only**
    observable difference between `>=` and `>` there. The fill price is identical either
    way, because the extra level a `>` takes contributes zero base at zero cost — so
    every value assertion in this file stayed green against that mutation and it survived
    the first sweep. What moves is `levels_consumed`, which is published provenance a
    criterion recomputes, and an overstated one says the book was thinner than it was.

    Found by the sweep, not by reading. Written against the exact defect, at four
    different depths so a fix that special-cases the first level does not pass.
    """
    bids = _first_book(THIN)
    exact = sum(price * quantity for price, quantity in bids[:through])

    walk = walk_the_bid_side(bids, exact)

    assert walk is not None
    assert walk.levels_consumed == through
    assert walk.base_filled == sum(quantity for _, quantity in bids[:through])


@pytest.mark.parametrize("basis", ["0", "-1", "-5000"])
def test_a_non_positive_basis_is_not_a_walk(basis: str) -> None:
    walk = walk_the_bid_side(_first_book(DEEP), Decimal(basis))
    assert walk is None


def test_a_hand_written_ladder_walks_to_an_exact_decimal() -> None:
    """Round numbers, so the arithmetic can be read without a calculator.

    100 x 1 = $100, then $50 of the 99 level buys 50/99 = 0.505050... units. Base sold is
    1.505050..., fill is 150 / 1.50505... = 99.664429..., slippage is 0.335570.../100.
    This is the same claim as the fixture tests and it is kept because a reader who
    disbelieves the 28-digit expectations above can check this one by hand in a minute.
    """
    ladder = ((Decimal("100"), Decimal("1")), (Decimal("99"), Decimal("2")))
    walk = walk_the_bid_side(ladder, Decimal("150"))
    assert walk is not None
    assert walk.levels_consumed == 2
    assert walk.base_filled == Decimal("1.505050505050505050505050505")
    assert walk.fill_price == Decimal("99.66442953020134228187919463")
    assert walk.slippage_pct == Decimal("0.0033557046979865771812080537")


def test_the_walk_never_returns_a_price_better_than_the_top_of_book() -> None:
    """Over every state of both pairs in the fixture, at three notionals.

    Non-negative slippage is a structural claim — levels are taken in descending price
    order — and it is the claim the `(best_bid - fill) / best_bid` direction depends on.
    A walk up the **ask** side, which is the mutation spec 96 names first, produces a
    negative number here on the first state it touches.
    """
    checked = 0
    for pair in (THIN, DEEP):
        for _, _, bids, _ in _replay_book(pair):
            for notional in (Decimal("100"), Decimal("1000"), Decimal("5000")):
                walk = walk_the_bid_side(bids, notional)
                if walk is None:
                    continue
                assert walk.fill_price <= walk.best_bid
                assert walk.slippage_pct >= 0
                checked += 1
    assert checked > 2000


def test_money_is_never_a_float_anywhere_in_the_walk() -> None:
    """`BookWalk`'s fields are `Money`, which raises on a float rather than coercing it."""
    from pydantic import ValidationError

    from acsoe.engines.order_book.contracts import BookWalk

    with pytest.raises(ValidationError):
        BookWalk(
            best_bid=100.0,  # type: ignore[arg-type]
            fill_price=Decimal("99"),
            base_filled=Decimal("1"),
            levels_consumed=1,
        )


# --------------------------------------------------------------------------- #
# The engine, success path
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("pair", "expected_slippage", "expected_levels"),
    [
        (THIN, "0.0001366891113175430924786514892", 10),
        (DEEP, "0.00006528042192692375531712952815", 4),
    ],
)
def test_the_engine_publishes_the_walk_it_made(
    book_context: Any,
    fake_kraken: Any,
    pair: str,
    expected_slippage: str,
    expected_levels: int,
) -> None:
    """End to end on the fixture's opening snapshot, at the real $5,000 paper balance.

    The same numbers as the two hand computations above, reached through the fake client,
    A's engine 1 and the engine's own config read rather than by calling the walk
    directly.
    """
    _load_book_into(fake_kraken, pair)
    state = _state_for(book_context, fake_kraken, pair, balances={"USD": "5000.00"})

    result = OrderBookEngine().process(book_context, state)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["pair"] == pair
    assert result.data["reason_code"] is None
    assert result.data[BASIS_NOTIONAL_FIELD] == "5000.00"
    assert result.data[LEVELS_CONSUMED_FIELD] == expected_levels
    assert result.data[ESTIMATED_SLIPPAGE_FIELD] == expected_slippage
    assert result.data["depth"] == RECORDED_DEPTH
    assert result.data["quote_currency"] == "USD"


def test_the_published_payload_can_be_recomputed_without_trusting_it(
    book_context: Any, fake_kraken: Any
) -> None:
    """`basis_notional`, `best_bid`, `fill_price` and `levels_consumed` are there so a
    criterion can rederive the ratio instead of reading back a number this engine wrote
    about itself.

    Three independent rederivations from the payload alone:

    1. the ratio is `(best_bid - fill_price) / best_bid` — which is what kills "measured
       from the mid", because the mid of this book is above the best bid and the ratio
       would come out larger;
    2. `fill_price x base_sold` returns the basis notional, where `base_sold` is recovered
       from the fixture's own levels;
    3. `levels_consumed` is the smallest level count whose cumulative notional reaches the
       basis.
    """
    bids = _load_book_into(fake_kraken, THIN)
    state = _state_for(book_context, fake_kraken, THIN, balances={"USD": "5000.00"})

    data = OrderBookEngine().process(book_context, state).data

    best_bid = Decimal(data["best_bid"])
    fill_price = Decimal(data["fill_price"])
    basis = Decimal(data[BASIS_NOTIONAL_FIELD])
    assert best_bid == bids[0][0]
    assert Decimal(data[ESTIMATED_SLIPPAGE_FIELD]) == (best_bid - fill_price) / best_bid

    cumulative = Decimal(0)
    needed = 0
    for index, (price, quantity) in enumerate(bids, start=1):
        cumulative += price * quantity
        if cumulative >= basis:
            needed = index
            break
    assert data[LEVELS_CONSUMED_FIELD] == needed


def test_the_basis_notional_is_the_whole_quote_balance_and_moves_with_it(
    book_context: Any, fake_kraken: Any
) -> None:
    """Two balances differing in one input, and the estimate moves.

    The lead's ruling in one assertion: the size is the account's whole quote balance, not
    a risk fraction and not a configured notional. A balance halved changes the published
    basis and, on a book this thin, the slippage with it.
    """
    _load_book_into(fake_kraken, THIN)
    engine = OrderBookEngine()

    small = engine.process(
        book_context, _state_for(book_context, fake_kraken, THIN, balances={"USD": "600.00"})
    ).data
    large = engine.process(
        book_context, _state_for(book_context, fake_kraken, THIN, balances={"USD": "5000.00"})
    ).data

    assert small[BASIS_NOTIONAL_FIELD] == "600.00"
    assert large[BASIS_NOTIONAL_FIELD] == "5000.00"
    assert Decimal(large[ESTIMATED_SLIPPAGE_FIELD]) > Decimal(small[ESTIMATED_SLIPPAGE_FIELD])
    assert large[LEVELS_CONSUMED_FIELD] > small[LEVELS_CONSUMED_FIELD]


def test_the_depth_the_tests_run_at_is_the_one_the_fixture_was_recorded_at() -> None:
    """A tripwire attached to the cause, not to a local reproduction of it.

    `order_book.depth` is requested of the lead under spec 80 and the tests overlay it
    until it lands. Whichever branch is live, the value must not exceed the depth every
    frame in the committed fixture was recorded at — a larger `depth` would configure the
    live engine to walk further than any committed evidence can validate, and the
    `book_too_thin` refusal would stop being provable.
    """
    try:
        declared = load_default_config().get(DEPTH_KEY)
    except KeyError:
        declared = None
    if declared is not None:
        assert isinstance(declared, int) and not isinstance(declared, bool)
        assert 0 < declared <= RECORDED_DEPTH, (
            f"config declares {DEPTH_KEY}={declared} but tests/fixtures/book_sample.jsonl "
            f"was recorded at depth {RECORDED_DEPTH}; re-cut the fixture or lower the key"
        )
    assert _config_with_depth().get(DEPTH_KEY) == RECORDED_DEPTH


def test_the_configured_depth_is_what_bounds_the_walk(
    engine_context: Any, fake_kraken: Any
) -> None:
    """The depth is read from config, not hardcoded, and it changes the answer.

    Driven at depth 2 and depth 10 against the same fixture book and the same balance:
    at 2 the bid side holds $605.18 and $5,000 does not fit; at 10 it holds $7,363.58 and
    it does. Same book, same basis, opposite outcome, one config key apart.
    """
    _load_book_into(fake_kraken, THIN)
    engine = OrderBookEngine()

    shallow_context = _configured(engine_context, _config_with_depth(2))
    shallow = engine.process(
        shallow_context,
        _state_for(shallow_context, fake_kraken, THIN, balances={"USD": "5000.00"}),
    ).data
    assert shallow["depth"] == 2
    assert shallow["reason_code"] == REASON_BOOK_TOO_THIN
    assert ESTIMATED_SLIPPAGE_FIELD not in shallow

    deep_context = _configured(engine_context, _config_with_depth(RECORDED_DEPTH))
    deep = engine.process(
        deep_context, _state_for(deep_context, fake_kraken, THIN, balances={"USD": "5000.00"})
    ).data
    assert deep["depth"] == RECORDED_DEPTH
    assert deep[ESTIMATED_SLIPPAGE_FIELD] == "0.0001366891113175430924786514892"


def test_every_money_field_leaves_as_a_string_and_none_is_a_float(
    book_context: Any, fake_kraken: Any
) -> None:
    """Contract rule 8. The validator accepts a float, which is the dangerous half."""
    _load_book_into(fake_kraken, DEEP)
    state = _state_for(book_context, fake_kraken, DEEP, balances={"USD": "5000.00"})

    data = OrderBookEngine().process(book_context, state).data

    for field in (BASIS_NOTIONAL_FIELD, "best_bid", "fill_price", ESTIMATED_SLIPPAGE_FIELD):
        assert isinstance(data[field], str), field
        assert "E" not in data[field] and "e" not in data[field], field
        Decimal(data[field])
    assert not any(isinstance(value, float) for value in data.values())


# --------------------------------------------------------------------------- #
# The fail-closed shapes
# --------------------------------------------------------------------------- #


def _shape_no_candidate(context: Any, fake_kraken: Any) -> dict[str, Any]:
    state = _state_for(context, fake_kraken, DEEP, balances={"USD": "5000.00"})
    state["scout"] = {}
    return state


def _shape_balance_fetch_failed(context: Any, fake_kraken: Any) -> dict[str, Any]:
    fake_kraken.fail("balance")
    return _state_for(context, fake_kraken, DEEP)


def _shape_pair_rules_fetch_failed(context: Any, fake_kraken: Any) -> dict[str, Any]:
    fake_kraken.fail("asset_pairs")
    return _state_for(context, fake_kraken, DEEP, balances={"USD": "5000.00"})


def _shape_pair_not_in_rules(context: Any, fake_kraken: Any) -> dict[str, Any]:
    state = _state_for(context, fake_kraken, DEEP, balances={"USD": "5000.00"})
    state["scout"] = {"pair": "NOSUCH/USD"}
    return state


def _shape_zero_quote_balance(context: Any, fake_kraken: Any) -> dict[str, Any]:
    _load_book_into(fake_kraken, DEEP)
    return _state_for(context, fake_kraken, DEEP, balances={"USD": "0.00", "BTC": "1.0"})


def _shape_quote_currency_absent_from_balances(context: Any, fake_kraken: Any) -> dict[str, Any]:
    _load_book_into(fake_kraken, DEEP)
    return _state_for(context, fake_kraken, DEEP, balances={"BTC": "1.0"})


def _shape_book_fetch_failed(context: Any, fake_kraken: Any) -> dict[str, Any]:
    fake_kraken.fail("order_book")
    return _state_for(context, fake_kraken, DEEP, balances={"USD": "5000.00"})


def _shape_unknown_pair_at_the_exchange(context: Any, fake_kraken: Any) -> dict[str, Any]:
    state = _state_for(context, fake_kraken, DEEP, balances={"USD": "5000.00"})
    fake_kraken.set_order_book(DEEP, bids=[], asks=[])
    return state


def _shape_crossed_book(context: Any, fake_kraken: Any) -> dict[str, Any]:
    fake_kraken.set_order_book(
        DEEP, bids=[("101.0", "10"), ("100.0", "10")], asks=[("99.0", "10"), ("102.0", "10")]
    )
    return _state_for(context, fake_kraken, DEEP, balances={"USD": "5000.00"})


def _shape_bids_out_of_order(context: Any, fake_kraken: Any) -> dict[str, Any]:
    fake_kraken.set_order_book(
        DEEP, bids=[("100.0", "10"), ("101.0", "10")], asks=[("102.0", "10")]
    )
    return _state_for(context, fake_kraken, DEEP, balances={"USD": "5000.00"})


def _shape_book_too_thin(context: Any, fake_kraken: Any) -> dict[str, Any]:
    _load_book_into(fake_kraken, THIN)
    return _state_for(context, fake_kraken, THIN, balances={"USD": "50000.00"})


#: Every fail-closed shape, with the code it must publish. The context builder is separate
#: from the state builder because two of the shapes are configuration faults and the rest
#: are not.
SHAPES: list[tuple[str, Any, str]] = [
    ("no candidate pair", _shape_no_candidate, REASON_INPUTS_UNAVAILABLE),
    ("balance fetch failed", _shape_balance_fetch_failed, REASON_INPUTS_UNAVAILABLE),
    ("pair rules fetch failed", _shape_pair_rules_fetch_failed, REASON_INPUTS_UNAVAILABLE),
    ("pair absent from rules", _shape_pair_not_in_rules, REASON_INPUTS_UNAVAILABLE),
    ("zero quote balance", _shape_zero_quote_balance, REASON_NO_QUOTE_BALANCE),
    (
        "quote currency not held",
        _shape_quote_currency_absent_from_balances,
        REASON_NO_QUOTE_BALANCE,
    ),
    ("book fetch failed", _shape_book_fetch_failed, REASON_BOOK_FETCH_FAILED),
    ("empty book", _shape_unknown_pair_at_the_exchange, REASON_BOOK_FETCH_FAILED),
    ("crossed book", _shape_crossed_book, REASON_BOOK_UNUSABLE),
    ("bids out of order", _shape_bids_out_of_order, REASON_BOOK_UNUSABLE),
    ("book too thin", _shape_book_too_thin, REASON_BOOK_TOO_THIN),
]


@pytest.mark.parametrize(("label", "build", "code"), SHAPES, ids=[row[0] for row in SHAPES])
def test_engine_nine_never_blocks_on_any_fail_closed_shape(
    book_context: Any, fake_kraken: Any, label: str, build: Any, code: str
) -> None:
    """The contract, on every shape: `OK`, no block, no estimate, a reason code.

    Engine 9 is not a gate. A non-gate that refused on its own criteria would make
    `is_gate` wrong — the principle the operator applied to engine 16 — so the refusal is
    engine 10's and this engine only declines to answer.

    `blocks_trading` is asserted beside the status rather than instead of it, because
    `ERROR` also carries `blocks_trading=True` and an empty payload, and asserting one
    without the other cannot tell a fail-closed shape from a crash.
    """
    state = build(book_context, fake_kraken)

    result = OrderBookEngine().process(book_context, state)

    assert result.status is EngineStatus.OK, label
    assert result.blocks_trading is False, label
    assert result.data["reason_code"] == code, label
    assert ESTIMATED_SLIPPAGE_FIELD not in result.data, label
    assert result.data != {}, label
    assert result.reason is not None and result.reason != "", label


@pytest.mark.parametrize(
    ("depth", "label"),
    [(None, "operator has not decided"), (0, "zero levels"), (-1, "negative"), ("ten", "not a number"), (True, "a bool")],
)
def test_an_unusable_configured_depth_declines_rather_than_defaulting(
    engine_context: Any, fake_kraken: Any, depth: Any, label: str
) -> None:
    """A depth silently chosen here decides how much book a slippage estimate may see,
    and therefore which candidates the cost gate lets through. None of these defaults."""
    context = _configured(engine_context, _config_with_depth(depth))
    state = _state_for(context, fake_kraken, DEEP, balances={"USD": "5000.00"})

    result = OrderBookEngine().process(context, state)

    assert result.status is EngineStatus.OK, label
    assert result.blocks_trading is False, label
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE, label
    assert ESTIMATED_SLIPPAGE_FIELD not in result.data, label


def test_an_undeclared_depth_key_declines_rather_than_erroring(
    engine_context: Any, fake_kraken: Any
) -> None:
    """`Config.get` raises on a key the model does not declare, and the raise would
    otherwise become `ERROR`, which blocks — which engine 9 must never do.

    This is the branch that is live today, because `config/default.yaml` carries no
    `order_book` section yet. It stays live as a test after the key lands.
    """
    context = _configured(engine_context, _config_without_order_book())
    state = _state_for(context, fake_kraken, DEEP, balances={"USD": "5000.00"})

    result = OrderBookEngine().process(context, state)

    assert result.status is EngineStatus.OK
    assert result.blocks_trading is False
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE


def test_a_float_balance_is_refused_rather_than_coerced(
    book_context: Any, fake_kraken: Any
) -> None:
    """A float arrives having already lost precision; coercing it launders the loss.

    Engine 1 publishes strings, so this shape can only arrive from a defect upstream —
    which is exactly why it is named here rather than absorbed.
    """
    _load_book_into(fake_kraken, DEEP)
    state = _state_for(book_context, fake_kraken, DEEP, balances={"USD": "5000.00"})
    state["exchange"]["balances"]["USD"] = 5000.0

    result = OrderBookEngine().process(book_context, state)

    assert result.status is EngineStatus.OK
    assert result.data["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert ESTIMATED_SLIPPAGE_FIELD not in result.data


def test_a_zero_balance_and_an_absent_balance_map_are_different_facts(
    book_context: Any, fake_kraken: Any
) -> None:
    """A handler that cannot distinguish two situations will silently pick the wrong one.

    A zero balance is a fact about the account; an unanswered `Balance` call is a fact
    about the call. The operator acts on them differently, so they carry different codes.
    """
    _load_book_into(fake_kraken, DEEP)
    engine = OrderBookEngine()

    zero = engine.process(
        book_context,
        _state_for(book_context, fake_kraken, DEEP, balances={"USD": "0.00"}),
    ).data
    fake_kraken.fail("balance")
    unfetched = engine.process(
        book_context, _state_for(book_context, fake_kraken, DEEP)
    ).data

    assert zero["reason_code"] == REASON_NO_QUOTE_BALANCE
    assert unfetched["reason_code"] == REASON_INPUTS_UNAVAILABLE
    assert zero["reason_code"] != unfetched["reason_code"]


def test_the_thin_pair_declines_past_its_depth_and_answers_within_it(
    book_context: Any, fake_kraken: Any
) -> None:
    """A block and a pass differing in one input: the balance.

    `ADA/USD`'s ten committed levels hold $7,363.58. At $50,000 there is no answer to give
    and `book_too_thin` says so; at $5,000 there is, on the same book in the same tick.
    """
    _load_book_into(fake_kraken, THIN)
    engine = OrderBookEngine()

    past = engine.process(
        book_context,
        _state_for(book_context, fake_kraken, THIN, balances={"USD": "50000.00"}),
    ).data
    within = engine.process(
        book_context,
        _state_for(book_context, fake_kraken, THIN, balances={"USD": "5000.00"}),
    ).data

    assert past["reason_code"] == REASON_BOOK_TOO_THIN
    assert ESTIMATED_SLIPPAGE_FIELD not in past
    assert past[BASIS_NOTIONAL_FIELD] == "50000.00"
    assert within["reason_code"] is None
    assert within[ESTIMATED_SLIPPAGE_FIELD] == "0.0001366891113175430924786514892"


def test_a_defect_on_our_side_of_the_client_boundary_is_not_swallowed(
    book_context: Any, fake_kraken: Any
) -> None:
    """Contract rule 7: an engine must not swallow its own exceptions to avoid `ERROR`.

    Only exchange-shaped failures become `book_fetch_failed`. A `TypeError` out of the
    client is a defect on this side and propagates, so the orchestrator turns it into
    `ERROR` and somebody finds out.
    """

    class Broken:
        async def order_book(self, pair: str, depth: int) -> Any:
            raise TypeError("the client is wired wrong")

    state = _state_for(book_context, fake_kraken, DEEP, balances={"USD": "5000.00"})
    clients = dataclasses.replace(book_context.clients, kraken=Broken())
    context = dataclasses.replace(book_context, clients=clients)

    with pytest.raises(TypeError, match="wired wrong"):
        OrderBookEngine().process(context, state)


# --------------------------------------------------------------------------- #
# Engine 9 and engine 10 together — spec 96 step 4
# --------------------------------------------------------------------------- #


def _cost_state(
    context: Any, fake_kraken: Any, pair: str, *, balances: Mapping[str, str]
) -> dict[str, Any]:
    """Everything engine 10 needs except engine 9's contribution.

    The spread comes from engine 3's key, the fees from A's engine 1 at tier 3, and the
    expected move from engine 8's key. Tier 3 because at tier 1 the cost gate is
    unreachable by construction and a pass test there would prove nothing.
    """
    state = _state_for(context, fake_kraken, pair, balances=balances, fee_tier=TIER_3)
    state["prediction"] = {"expected_move_pct": "0.0250"}
    state["market_sensor"] = {"quotes": {pair: {"spread_pct": "0.0002"}}}
    return state


def test_the_cost_gate_refuses_when_engine_nine_published_no_estimate(
    book_context: Any, fake_kraken: Any
) -> None:
    """The whole design in one test: engine 9 declines, engine 10 is the one that refuses.

    Engine 9 returns `OK` and does not block. Engine 10's `_require` then finds no
    `estimated_slippage_pct` and blocks — naming the absent key, not engine 9's reason,
    which is why the reason code has to be readable in engine 9's own payload.
    """
    state = _cost_state(book_context, fake_kraken, THIN, balances={"USD": "50000.00"})
    _load_book_into(fake_kraken, THIN)

    nine = OrderBookEngine().process(book_context, state)
    state["order_book"] = nine.data
    ten = CostEngine().process(book_context, state)

    assert nine.status is EngineStatus.OK
    assert nine.blocks_trading is False
    assert ten.status is EngineStatus.BLOCK
    assert ten.blocks_trading is True
    assert ten.reason is not None and ESTIMATED_SLIPPAGE_FIELD in ten.reason
    assert state["order_book"]["reason_code"] == REASON_BOOK_TOO_THIN


def test_the_cost_gate_prices_the_slippage_engine_nine_published(
    book_context: Any, fake_kraken: Any
) -> None:
    """Engine 10's friction is recomputed from its four terms, one of which is engine 9's.

    Recomputed rather than read back: `friction_pct` is checked against the sum of the two
    fees, the spread and **the exact string engine 9 wrote**, so a cost gate that dropped
    the slippage term entirely would still publish a plausible friction and this would
    still catch it.
    """
    state = _cost_state(book_context, fake_kraken, DEEP, balances={"USD": "5000.00"})
    _load_book_into(fake_kraken, DEEP)

    state["order_book"] = OrderBookEngine().process(book_context, state).data
    ten = CostEngine().process(book_context, state)

    slippage = Decimal(state["order_book"][ESTIMATED_SLIPPAGE_FIELD])
    assert slippage > 0
    expected_friction = (
        Decimal(TIER_3["maker_fee_pct"])
        + Decimal(TIER_3["taker_fee_pct"])
        + Decimal("0.0002")
        + slippage
    )
    assert Decimal(ten.data["friction_pct"]) == expected_friction
    assert Decimal(ten.data["net_edge_pct"]) == Decimal("0.0250") - expected_friction


def test_a_thinner_book_moves_the_cost_gates_friction(
    book_context: Any, fake_kraken: Any
) -> None:
    """Two pairs, one balance, and the only difference is depth.

    The thin pair's slippage is the larger, so its friction is the larger and its net edge
    the smaller. That is the sentence engine 9 exists to make true, and nothing else in
    the chain could make it true.
    """
    frictions: dict[str, Decimal] = {}
    for pair in (THIN, DEEP):
        state = _cost_state(book_context, fake_kraken, pair, balances={"USD": "5000.00"})
        _load_book_into(fake_kraken, pair)
        state["order_book"] = OrderBookEngine().process(book_context, state).data
        frictions[pair] = Decimal(CostEngine().process(book_context, state).data["friction_pct"])

    assert frictions[THIN] > frictions[DEEP]


def test_the_published_pair_follows_scout_across_ticks_rather_than_being_cached(
    book_context: Any, fake_kraken: Any
) -> None:
    """Engine 16's coherence walk checks any payload carrying a `pair` against
    `state["scout"]["pair"]`, and this is what gives that check something to catch.

    **One tick cannot tell an echo from a cache.** Every other test here builds `state`
    with one pair and asserts the published `pair` equals it — which is true of an engine
    that reads scout, and equally true of an engine that re-derived the pair from the book
    it just fetched, or that held the first pair it ever saw. The two sources agree by
    construction on a single tick, which is the witness problem: an assertion satisfiable
    by two different sources is an assertion about neither.

    So this drives **one engine instance over two ticks with different candidates**. A
    cached pair survives the first assertion and fails the second, and the failure it
    prevents is the expensive one: slippage walked on the right book, published against
    the wrong pair, and priced into engine 10's hurdle for a market nobody looked at.
    """
    engine = OrderBookEngine()

    _load_book_into(fake_kraken, THIN)
    first = engine.process(
        book_context, _state_for(book_context, fake_kraken, THIN, balances={"USD": "5000.00"})
    )
    _load_book_into(fake_kraken, DEEP)
    second = engine.process(
        book_context, _state_for(book_context, fake_kraken, DEEP, balances={"USD": "5000.00"})
    )

    assert first.data["pair"] == THIN
    assert second.data["pair"] == DEEP, (
        "the second tick published the first tick's pair, so engine 9 is holding a "
        "candidate across ticks and engine 16's coherence walk is the only thing that "
        "would ever notice"
    )
    # And the walk is measuring something: the two tick's estimates must differ, or the
    # pair could be wrong with no observable consequence on this fixture.
    assert first.data[ESTIMATED_SLIPPAGE_FIELD] != second.data[ESTIMATED_SLIPPAGE_FIELD], (
        "the thin and deep books priced the same slippage, so this fixture cannot show "
        "that the published pair and the walked book belong to each other"
    )
