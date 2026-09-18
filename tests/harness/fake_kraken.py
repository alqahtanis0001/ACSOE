"""A deterministic stand-in for the Kraken client. Spec 15.

Every engine test runs offline against recorded responses, and this is what makes
that possible before `clients/kraken/` exists (A, Phase 2).

Three things about it are deliberate and are easy to undo by accident.

**Nothing here is a system default.** The numbers in `tests/fixtures/kraken/*.json`
are invented test data for a fake exchange. They are not Kraken's fee schedule,
minimums, tick sizes or precisions, and no code outside `tests/` may read them.
Invariant 2 is absolute: those values come from `AssetPairs` and `TradeVolume` at
runtime, or the trade is blocked.

**The envelope is faithful; the result body is not claimed to be.** Kraken wraps
everything in `{"error": [...], "result": {...}}` and does not use HTTP status to
signal application errors - a 200 carrying a non-empty `error` array is a failure,
and `code-standards.md` makes checking it mandatory. That much is documented in
this repository, so the fake reproduces it exactly. The *shape of the result body*
is a simplified one owned by this harness, because `AGENTS.md` says in as many
words that any Kraken endpoint signature an agent remembers is stale and must not
be written into code. Fabricating a plausible-looking real payload would be
exactly that. A replaces these with genuine redacted recordings in Phase 2.

**The fake is never kinder than the real client.** Retention follows invariant 2
precisely: `balance()` and `asset_pairs()` retain their last successful result so
an emergency liquidation under invariant 14 can complete during the outage that
triggered it; `trade_volume()` and `order_book()` retain nothing, because their
only reader is the cost gate and an assumed spread invalidates that gate. A fake
that retained all four would let a test pass that must fail.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "kraken"

__all__ = [
    "TIER_1",
    "TIER_3",
    "BalancesSnapshot",
    "FakeKrakenClient",
    "FeeTierProfile",
    "FeeTierSnapshot",
    "KrakenAPIError",
    "KrakenClientProtocol",
    "KrakenError",
    "KrakenUnavailableError",
    "OrderBookSnapshot",
    "PairRule",
    "PairRulesSnapshot",
    "fee_tier_profile",
    "tier_sentence",
]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
#
# Names, shapes and module path agreed with A: `acsoe.clients.kraken.errors`,
# re-exported from `acsoe.clients.kraken`. Until Phase 2 lands them the harness
# defines them, and swaps to the real ones the moment they exist - so a test that
# asserts on the error type keeps asserting on the same type across the handover.
# A fake that raises a different exception than the real client is a fake that
# hides fail-closed bugs, which is precisely what spec 15 forbids.

try:  # pragma: no cover - exercised only once clients/kraken/ exists
    from acsoe.clients.kraken import (  # type: ignore[attr-defined]
        KrakenAPIError,
        KrakenError,
        KrakenUnavailableError,
    )
except ImportError:

    class KrakenError(Exception):  # type: ignore[no-redef]
        """Base class, so a caller failing closed catches one exchange-shaped type."""

    class KrakenAPIError(KrakenError):  # type: ignore[no-redef]
        """The envelope came back with a non-empty `error` list.

        Raised regardless of HTTP status: Kraken answers 200 with a populated
        `error` array, and treating that as success records failures as fills.
        """

        def __init__(self, message: str, errors: list[str]) -> None:
            super().__init__(message)
            self.errors = errors

    class KrakenUnavailableError(KrakenError):  # type: ignore[no-redef]
        """Transport, timeout, disconnect, or exhausted rate limit."""

        def __init__(self, message: str, cause: Exception | None = None) -> None:
            super().__init__(message)
            self.cause = cause


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
#
# Provisional, and owned by this harness. A's real models land in
# `clients/kraken/contracts.py` in Phase 2. Money is Decimal on every field that
# reaches an order; `float` never appears.


@dataclass(frozen=True)
class PairRule:
    pair: str
    base: str
    quote: str
    ordermin: Decimal
    costmin: Decimal
    tick_size: Decimal
    lot_decimals: int
    pair_decimals: int


@dataclass(frozen=True)
class PairRulesSnapshot:
    pairs: Mapping[str, PairRule]
    fetched_at: int  # microseconds since epoch, injected - never a clock read


@dataclass(frozen=True)
class FeeTierSnapshot:
    tier: int
    currency: str
    volume_30d: Decimal
    maker_fee_pct: Decimal  # a decimal, so 0.0025 is 0.25%
    taker_fee_pct: Decimal
    fetched_at: int


@dataclass(frozen=True)
class BalancesSnapshot:
    balances: Mapping[str, Decimal]
    fetched_at: int


@dataclass(frozen=True)
class OrderBookSnapshot:
    pair: str
    bids: tuple[tuple[Decimal, Decimal], ...]
    asks: tuple[tuple[Decimal, Decimal], ...]
    fetched_at: int

    @property
    def best_bid(self) -> Decimal:
        return self.bids[0][0]

    @property
    def best_ask(self) -> Decimal:
        return self.asks[0][0]

    @property
    def spread(self) -> Decimal:
        return self.best_ask - self.best_bid


@runtime_checkable
class KrakenClientProtocol(Protocol):
    """The `kraken` half of the `Clients` Protocol, as agreed with A.

    Method names come from A directly and are provisional until `clients/kraken/`
    lands in Phase 2. When `acsoe.core.contracts.Clients` exists,
    `test_fake_kraken.py` also checks the fake against the real declaration.
    """

    async def asset_pairs(self) -> PairRulesSnapshot: ...

    async def trade_volume(self) -> FeeTierSnapshot: ...

    async def balance(self) -> BalancesSnapshot: ...

    async def order_book(self, pair: str, depth: int) -> OrderBookSnapshot: ...


# --------------------------------------------------------------------------- #
# The envelope
# --------------------------------------------------------------------------- #

CALLS = ("asset_pairs", "trade_volume", "balance", "order_book")

# Which calls retain their last successful value. Invariant 2, and only these two:
# rule 14's emergency liquidation reads them past their TTL, and nothing else may.
RETAINED_CALLS = frozenset({"asset_pairs", "balance"})


def load_envelope(name: str) -> dict[str, Any]:
    """Read one committed fixture envelope."""
    path = FIXTURE_DIR / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "error" not in data or "result" not in data:
        raise ValueError(f"{path} is not a Kraken envelope")
    return data


def unwrap(envelope: Mapping[str, Any], call: str) -> Any:
    """Kraken's envelope rule, in one place.

    A non-empty `error` list is a failure even when the HTTP status was 200. This
    is the check `code-standards.md` requires on every response.
    """
    errors = envelope.get("error") or []
    if errors:
        raise KrakenAPIError(f"{call} failed: {'; '.join(errors)}", list(errors))
    return envelope["result"]


# --------------------------------------------------------------------------- #
# Named fee tiers
# --------------------------------------------------------------------------- #
#
# Spec 100 step 1. The Phase 6 criteria all have to say which fee tier they ran at,
# because the fee regime is part of what a verdict proves. **Neither profile here is
# Kraken's schedule, and neither is a no-trade regime**: measured 2026-09-18 on the
# committed subject, both clear the cost gate (the fixture's `_comment` gives the
# figures). The no-trade finding is about invariant 5's reference schedule for Kraken,
# which these criteria do not run at.
#
# Naming the tiers rather than spelling two decimal strings at each call
# site is what stops "tier 3" meaning two different things in two criteria - which
# it already nearly did, with `0.0011`/`0.0019` copied by hand into four test files.
#
# The numbers live in `tests/fixtures/kraken/fee_tiers.json` and nowhere else. They
# are invented data for a fake exchange; invariant 2 says the real ones come from
# `TradeVolume` at runtime or the trade is blocked.

TIER_1 = 1
TIER_3 = 3

#: Which of the fake exchange's fee profiles a criterion ran at, as one clause for its
#: message. **It carries no friction and no hurdle, and it must not.** `friction` is fees
#: plus the measured spread plus estimated slippage, engine 10 is the only thing entitled to
#: compute it, and only the criterion that drove a run knows what engine 10 computed in it.
#:
#: Until 2026-09-18 these sentences quoted invariant 5's *reference* figures for Kraken's
#: own schedule - "reference friction about 0.65% ... a hurdle of 1.625%; tier 1 is a
#: no-trade regime" - into every trade criterion's PASS, while those criteria ran at this
#: fixture's invented rates and engine 10 computed friction 0.308% and a hurdle of 0.462%.
#: At the fixture's own tier-1 rates the bar sits near 1.77%, under the 3.0% target, so
#: "no-trade regime" was not even true of the fake. Operator ruling S3: a message states
#: its own run's figures, and `scripts/verify.py` appends them from engine 10's payload.
_TIER_SENTENCES = {
    TIER_1: (
        "at the fake exchange's fee tier 1 (invented maker and taker rates from "
        "tests/fixtures/kraken/fee_tiers.json)"
    ),
    TIER_3: (
        "at the fake exchange's fee tier 3 (invented maker and taker rates from "
        "tests/fixtures/kraken/fee_tiers.json)"
    ),
}


@dataclass(frozen=True)
class FeeTierProfile:
    """One named fee tier, read from the committed fixture.

    Strings rather than `Decimal` on the fee fields, because that is what
    :meth:`FakeKrakenClient.set_fee_tier` takes and what the envelope carries; the
    conversion to `Decimal` happens once, in `trade_volume()`, the way it does in
    the real client.
    """

    tier: int
    currency: str
    volume_30d: str
    maker_fee_pct: str
    taker_fee_pct: str

    @property
    def fees_round_trip_pct(self) -> Decimal:
        """Maker in, taker out. **Not the friction** engine 10 hurdles against.

        Friction is this plus the measured spread plus estimated slippage, and this
        property exists to be compared against a fixture, never to stand in for the
        gate's arithmetic. A criterion that hurdled against this number would be
        checking its own sum rather than the engine's.
        """
        return Decimal(self.maker_fee_pct) + Decimal(self.taker_fee_pct)


def fee_tier_profile(tier: int) -> FeeTierProfile:
    """The named profile for `tier`, from `tests/fixtures/kraken/fee_tiers.json`."""
    data = json.loads((FIXTURE_DIR / "fee_tiers.json").read_text(encoding="utf-8"))
    tiers = data["tiers"]
    key = str(tier)
    if key not in tiers:
        raise ValueError(f"no named fee-tier profile for tier {tier}; have {sorted(tiers)}")
    entry = tiers[key]
    return FeeTierProfile(
        tier=int(entry["tier"]),
        currency=str(entry["currency"]),
        volume_30d=str(entry["volume_30d"]),
        maker_fee_pct=str(entry["maker_fee_pct"]),
        taker_fee_pct=str(entry["taker_fee_pct"]),
    )


def tier_sentence(tier: int) -> str:
    """The clause a criterion puts in its own PASS and FAIL message.

    Required by ruling 8 of the Phase 6 task list: *"Every criterion that drives a
    trade says tier 3 in its own message."* A verdict that does not name its fee
    regime claims more than it proves, because the same engines produce no trade at
    all one tier away.
    """
    try:
        return _TIER_SENTENCES[tier]
    except KeyError:
        raise ValueError(f"no sentence for tier {tier}; have {sorted(_TIER_SENTENCES)}") from None


# --------------------------------------------------------------------------- #
# The client
# --------------------------------------------------------------------------- #


@dataclass
class _Retained:
    value: Any
    fetched_at: int


class FakeKrakenClient:
    """A deterministic Kraken client backed by committed fixtures.

    Every value is injectable per test, because Phase 3 has to vary the fee tier
    and the balances and watch the universe filter and the cost gate respond.
    Every call can be made to fail, in either of the two ways the real exchange
    fails: a transport failure (`KrakenUnavailableError`) or a 200 carrying a
    populated `error` array (`KrakenAPIError`).

    It never touches the network. There is no code path here that could.
    """

    def __init__(self, *, now: int = 0) -> None:
        self._envelopes: dict[str, dict[str, Any]] = {name: load_envelope(name) for name in CALLS}
        self._transport_failures: dict[str, KrakenError] = {}
        self._retained: dict[str, _Retained] = {}
        self._calls: list[str] = []
        self.now = now

    # -- injection -------------------------------------------------------- #

    def set_now(self, now: int) -> None:
        """Set the fetch timestamp stamped on the next snapshot.

        Injected rather than read: invariant 9 forbids a clock read on this path,
        and a test that wants a stale cache needs to move time by hand.
        """
        self.now = now

    def set_fee_tier(
        self, *, tier: int, maker_fee_pct: str, taker_fee_pct: str, volume_30d: str = "0"
    ) -> None:
        self._envelopes["trade_volume"]["result"].update(
            {
                "tier": tier,
                "maker_fee_pct": maker_fee_pct,
                "taker_fee_pct": taker_fee_pct,
                "volume_30d": volume_30d,
            }
        )

    def use_fee_tier(self, tier: int) -> FeeTierProfile:
        """Apply a **named** tier from the fixture, and say which one was applied.

        The returned profile is what a criterion quotes in its message, so the tier
        it reports and the tier it ran at are the same object rather than two
        statements that happen to agree today.
        """
        profile = fee_tier_profile(tier)
        self.set_fee_tier(
            tier=profile.tier,
            maker_fee_pct=profile.maker_fee_pct,
            taker_fee_pct=profile.taker_fee_pct,
            volume_30d=profile.volume_30d,
        )
        self._envelopes["trade_volume"]["result"]["currency"] = profile.currency
        return profile

    def set_balances(self, balances: Mapping[str, str]) -> None:
        self._envelopes["balance"]["result"] = dict(balances)

    def set_pair_rule(self, pair: str, **fields: Any) -> None:
        result = self._envelopes["asset_pairs"]["result"]
        rule = dict(result.get(pair, {}))
        rule.update(fields)
        result[pair] = rule

    def remove_pair(self, pair: str) -> None:
        self._envelopes["asset_pairs"]["result"].pop(pair, None)

    def set_order_book(
        self, pair: str, *, bids: Sequence[tuple[str, str]], asks: Sequence[tuple[str, str]]
    ) -> None:
        self._envelopes["order_book"]["result"][pair] = {
            "bids": [list(level) for level in bids],
            "asks": [list(level) for level in asks],
        }

    # -- failure ---------------------------------------------------------- #

    def fail(self, call: str, error: KrakenError | None = None) -> None:
        """Make `call` fail at the transport, the way an outage does."""
        self._require_known(call)
        self._transport_failures[call] = error or KrakenUnavailableError(
            f"{call} is unavailable (injected by the fake)"
        )

    def fail_with_envelope_error(self, call: str, errors: Sequence[str]) -> None:
        """Make `call` answer HTTP 200 with a populated `error` array.

        The failure mode `code-standards.md` singles out, and the one a client that
        trusts the status code records as a success.
        """
        self._require_known(call)
        self._envelopes[call]["error"] = list(errors)

    def clear_failures(self, call: str | None = None) -> None:
        for name in CALLS if call is None else [call]:
            self._require_known(name)
            self._transport_failures.pop(name, None)
            self._envelopes[name]["error"] = []

    def _require_known(self, call: str) -> None:
        if call not in CALLS:
            raise ValueError(f"unknown call {call!r}; expected one of {CALLS}")

    # -- retention -------------------------------------------------------- #

    @property
    def last_known_good_asset_pairs(self) -> _Retained | None:
        """Retained past its TTL, and readable only by an emergency liquidation."""
        return self._retained.get("asset_pairs")

    @property
    def last_known_good_balances(self) -> _Retained | None:
        return self._retained.get("balance")

    @property
    def calls(self) -> tuple[str, ...]:
        return tuple(self._calls)

    def _result(self, call: str) -> Any:
        self._calls.append(call)
        failure = self._transport_failures.get(call)
        if failure is not None:
            raise failure
        return unwrap(self._envelopes[call], call)

    def _retain(self, call: str, value: Any) -> None:
        if call in RETAINED_CALLS:
            self._retained[call] = _Retained(value, self.now)

    # -- the Protocol ----------------------------------------------------- #

    async def asset_pairs(self) -> PairRulesSnapshot:
        result = self._result("asset_pairs")
        pairs = {
            name: PairRule(
                pair=name,
                base=str(rule["base"]),
                quote=str(rule["quote"]),
                ordermin=Decimal(str(rule["ordermin"])),
                costmin=Decimal(str(rule["costmin"])),
                tick_size=Decimal(str(rule["tick_size"])),
                lot_decimals=int(rule["lot_decimals"]),
                pair_decimals=int(rule["pair_decimals"]),
            )
            for name, rule in result.items()
        }
        snapshot = PairRulesSnapshot(pairs=pairs, fetched_at=self.now)
        self._retain("asset_pairs", snapshot)
        return snapshot

    async def trade_volume(self) -> FeeTierSnapshot:
        result = self._result("trade_volume")
        snapshot = FeeTierSnapshot(
            tier=int(result["tier"]),
            currency=str(result["currency"]),
            volume_30d=Decimal(str(result["volume_30d"])),
            maker_fee_pct=Decimal(str(result["maker_fee_pct"])),
            taker_fee_pct=Decimal(str(result["taker_fee_pct"])),
            fetched_at=self.now,
        )
        self._retain("trade_volume", snapshot)  # a no-op, deliberately
        return snapshot

    async def balance(self) -> BalancesSnapshot:
        result = self._result("balance")
        snapshot = BalancesSnapshot(
            balances={k: Decimal(str(v)) for k, v in result.items()}, fetched_at=self.now
        )
        self._retain("balance", snapshot)
        return snapshot

    async def order_book(self, pair: str, depth: int = 10) -> OrderBookSnapshot:
        result = self._result("order_book")
        book = result.get(pair)
        if book is None:
            raise KrakenAPIError(
                f"order_book failed: EQuery:Unknown asset pair ({pair})",
                ["EQuery:Unknown asset pair"],
            )

        def levels(side: str) -> tuple[tuple[Decimal, Decimal], ...]:
            return tuple(
                (Decimal(str(price)), Decimal(str(volume)))
                for price, volume in book[side][:depth]
            )

        snapshot = OrderBookSnapshot(
            pair=pair, bids=levels("bids"), asks=levels("asks"), fetched_at=self.now
        )
        self._retain("order_book", snapshot)  # a no-op, deliberately
        return snapshot


@dataclass
class FakeRecorder:
    """The `recorder` half of `Clients`: append-only, and in memory here.

    Engine 2 is the only engine permitted to touch it (engine contract rule 4).
    """

    lines: list[Mapping[str, Any]] = field(default_factory=list)

    def append(self, line: Mapping[str, Any]) -> None:
        self.lines.append(dict(line))
