"""What the exchange client returns, and what every consumer reads.

This is the seam named in ``context/ownership.md``: *raw ticks, pair rules, fee
tier* flow from Agent A to Agents B and C, and *last-known-good exchange values*
flow to engines 21 and 22 in Phase 6. It lands before the transports so that B and
C can mock against it rather than wait.

Four things here are load-bearing and are easy to undo by accident.

**Nothing in this module is a value.** There is no fee, no order minimum, no tick
size, no precision, and no default for any of them — not even as a fallback and not
in a comment. Rule 2 of ``context/trading-invariants.md`` is absolute, and
``AGENTS.md`` says in as many words that any Kraken number an agent remembers is
stale. These are the *shapes* those values arrive in.

**Money is ``Decimal`` and a ``float`` is refused, not coerced.** By the time a
float reaches a validator the precision is already gone, so accepting one would
launder the defect rather than catch it. ``Decimal(str(0.1))`` is honest about what
happened to it; ``Decimal(0.1)`` is not.

**Absent is never zero.** A missing spread and a zero spread are different facts,
and invariant 3 says the absence of a "no" is never a "yes". So there is no
"empty book" value: :class:`OrderBookSnapshot` refuses to exist with an empty side,
and a fetch that failed raises rather than returning a snapshot full of zeroes. A
consumer that has no snapshot has no spread, which is a block.

**Money crosses ``state`` as a string, never as a ``Decimal`` or a ``float``.**
``EngineResult.data`` is validated JSON-serialisable in ``core/contracts.py`` and
``Decimal`` is refused outright, while ``float`` passes and silently loses the
precision the ``Decimal`` rule exists to protect. :func:`money_text` is the one
conversion, and it is plain decimal notation with the trailing zeros kept, because
the trailing zeros are the quantum.
"""

from __future__ import annotations

import datetime as _datetime
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Any, Protocol, runtime_checkable

from pydantic import BaseModel, BeforeValidator, ConfigDict, field_validator, model_validator

__all__ = [
    "Balances",
    "BalancesSnapshot",
    "BookLevel",
    "FeeTierSnapshot",
    "KrakenClientProtocol",
    "MarketStreamProtocol",
    "Money",
    "OrderBookSnapshot",
    "PairRule",
    "PairRulesSnapshot",
    "QuoteTick",
    "RawFrame",
    "RetainedValue",
    "StreamChannel",
    "TradeTick",
    "coerce_balances",
    "coerce_fee_tier",
    "coerce_order_book",
    "coerce_pair_rule",
    "coerce_pair_rules",
    "money_text",
    "to_micros",
]


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #


def _to_money(value: Any) -> Any:
    """Coerce to ``Decimal`` from anything exact, and refuse a ``float``.

    A bool is refused before the int branch, because ``bool`` is a subclass of
    ``int`` and ``Decimal(True)`` is a perfectly happy ``Decimal("1")``.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("a boolean is not a money value")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise ValueError(
            f"{value!r} is a float, and a float has already lost precision by the time "
            "it gets here. Money crosses this boundary as a decimal string or a Decimal."
        )
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError(f"{value!r} is not a decimal number") from exc
    raise ValueError(f"expected a decimal number, got {type(value).__name__}")


#: A quantity, price, fee or balance. ``Decimal`` in, ``Decimal`` out; a ``float``
#: raises rather than being coerced.
Money = Annotated[Decimal, BeforeValidator(_to_money)]

#: A currency code to amount map, exactly as ``paper.starting_balances`` is shaped.
Balances = Mapping[str, Money]

#: One order-book level: price, then volume at that price.
BookLevel = tuple[Money, Money]

_MICROSECONDS_PER_SECOND = 1_000_000


def to_micros(moment: _datetime.datetime) -> int:
    """Microseconds since the epoch, UTC. Refuses a naive datetime.

    ``astimezone`` on a naive value silently assumes local time, which would make
    every ``fetched_at`` in a recording wrong by the machine's UTC offset and
    wrong by a different amount in summer.
    """
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware UTC; a naive datetime is a defect")
    return int(moment.astimezone(_datetime.UTC).timestamp() * _MICROSECONDS_PER_SECOND)


def money_text(value: Decimal) -> str:
    """The canonical string a money value crosses ``state`` as.

    Plain decimal notation, never scientific, and the trailing zeros are kept
    because they carry the quantum: ``"5.00"`` says cents, ``"5"`` does not.
    Agreed with Agent B so both sides of the ``state`` hop agree byte for byte —
    ``clients/store/client.py`` writes the same form into the money TEXT columns.
    """
    return format(value, "f")


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #


class _Snapshot(BaseModel):
    """Frozen, and a stray key is refused rather than ignored.

    Kraken adds fields; silently absorbing one into a model that then travels into
    ``state`` would put unvalidated exchange data in front of an engine, which
    ``code-standards.md`` forbids at the client boundary. Refusing is noisy and
    that is the point — a new field is a decision, not an accident.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- #
# Pair rules — GET /0/public/AssetPairs
# --------------------------------------------------------------------------- #


class PairRule(_Snapshot):
    """One tradable pair's rules, exactly as the exchange reports them.

    Every field here is fetched. None of them has a default, and none of them may
    be read from ``config/default.yaml`` — invariant 2, and spec 28 repeats it for
    ``tick_size`` specifically because a constant tick size is the easiest one to
    slip in while writing a comparison tolerance.
    """

    pair: str
    base: str
    quote: str
    ordermin: Money
    costmin: Money
    tick_size: Money
    lot_decimals: int
    pair_decimals: int

    @field_validator("ordermin", "costmin", "tick_size")
    @classmethod
    def _strictly_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError(
                "ordermin, costmin and tick_size must be positive; a zero minimum would "
                "let a position of nothing satisfy the risk gate"
            )
        return value

    @field_validator("lot_decimals", "pair_decimals")
    @classmethod
    def _not_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("decimal places cannot be negative")
        return value

    def state_dict(self) -> dict[str, Any]:
        """The JSON-safe form this rule crosses ``state`` as. Money as strings."""
        return {
            "pair": self.pair,
            "base": self.base,
            "quote": self.quote,
            "ordermin": money_text(self.ordermin),
            "costmin": money_text(self.costmin),
            "tick_size": money_text(self.tick_size),
            "lot_decimals": self.lot_decimals,
            "pair_decimals": self.pair_decimals,
        }


class PairRulesSnapshot(_Snapshot):
    """Every pair's rules as of one successful ``AssetPairs`` call.

    ``fetched_at`` is microseconds since the epoch and is *injected*, never read
    from a clock inside the client. It is what makes a TTL check possible, and it
    is what rule 14 reads when it uses this snapshot past that TTL during an
    emergency liquidation.
    """

    pairs: Mapping[str, PairRule]
    fetched_at: int

    @model_validator(mode="after")
    def _keys_agree_with_rules(self) -> PairRulesSnapshot:
        for key, rule in self.pairs.items():
            if key != rule.pair:
                raise ValueError(
                    f"pair rules are keyed by symbol; {key!r} holds a rule for {rule.pair!r}"
                )
        return self

    def state_dict(self) -> dict[str, Any]:
        return {
            "fetched_at": self.fetched_at,
            "pairs": {name: rule.state_dict() for name, rule in self.pairs.items()},
        }


# --------------------------------------------------------------------------- #
# Fee tier — POST /0/private/TradeVolume
# --------------------------------------------------------------------------- #


class FeeTierSnapshot(_Snapshot):
    """The account's live maker and taker fees.

    Maker and taker are carried separately and are never blended. Invariant 5
    computes friction as maker on entry plus taker on exit — the worst realistic
    round trip, because a stop must always exit as a taker — so a single average
    rate cannot express it.

    Rates are decimals: ``Decimal("0.0040")`` is 0.40%. ``code-standards.md``
    names the convention and the field name carries the unit.

    Deliberately **not retained** past a failure. Its only reader is the cost gate,
    and invariant 2 says an assumed input invalidates that gate.
    """

    tier: int
    currency: str
    volume_30d: Money
    maker_fee_pct: Money
    taker_fee_pct: Money
    fetched_at: int

    @field_validator("maker_fee_pct", "taker_fee_pct")
    @classmethod
    def _is_a_ratio(cls, value: Decimal) -> Decimal:
        if value < 0 or value > 1:
            raise ValueError(
                f"a fee is a decimal ratio, so 0.40% is 0.004 and not 0.40; got {value}"
            )
        return value

    def state_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "currency": self.currency,
            "volume_30d": money_text(self.volume_30d),
            "maker_fee_pct": money_text(self.maker_fee_pct),
            "taker_fee_pct": money_text(self.taker_fee_pct),
            "fetched_at": self.fetched_at,
        }


# --------------------------------------------------------------------------- #
# Balances — POST /0/private/Balance
# --------------------------------------------------------------------------- #


class BalancesSnapshot(_Snapshot):
    """What the account holds, per currency.

    Retained past a failure, because rule 14's emergency liquidation has to be able
    to complete during the outage that triggered it and needs to know what it holds.
    """

    balances: Balances
    fetched_at: int

    def state_dict(self) -> dict[str, Any]:
        return {
            "balances": {code: money_text(amount) for code, amount in self.balances.items()},
            "fetched_at": self.fetched_at,
        }


# --------------------------------------------------------------------------- #
# Order book
# --------------------------------------------------------------------------- #


class OrderBookSnapshot(_Snapshot):
    """Top of book for one pair.

    **A side may not be empty.** An empty book has no best price, and a snapshot
    that answered ``0`` for one would hand the cost gate a zero spread, which is
    the single input invariant 2 says may never be assumed. Refusing at
    construction means "no book" arrives as an exception, which blocks, rather than
    as a plausible-looking snapshot, which does not.

    Deliberately **not retained** past a failure, for the same reason as the fee
    tier: a liquidation sells as a taker at whatever the book is, having already
    decided that getting flat beats getting a good price.
    """

    pair: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    fetched_at: int

    @field_validator("bids", "asks")
    @classmethod
    def _not_empty(cls, value: tuple[BookLevel, ...]) -> tuple[BookLevel, ...]:
        if not value:
            raise ValueError(
                "an order book side may not be empty; absent is not zero and an empty "
                "book must reach the caller as a failure, never as a zero spread"
            )
        return value

    @property
    def best_bid(self) -> Decimal:
        return self.bids[0][0]

    @property
    def best_ask(self) -> Decimal:
        return self.asks[0][0]

    @property
    def spread(self) -> Decimal:
        """Ask minus bid. **May be negative**, and that is not an error here.

        A crossed book is a real thing a feed produces during a fault, and engine 4
        ``data_guard`` is what blocks on it. Clamping it to zero in the client
        would delete the evidence the gate exists to see.
        """
        return self.best_ask - self.best_bid

    def state_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "best_bid": money_text(self.best_bid),
            "best_ask": money_text(self.best_ask),
            "spread": money_text(self.spread),
            "fetched_at": self.fetched_at,
        }


# --------------------------------------------------------------------------- #
# Retention — invariant 2, read only by invariant 14
# --------------------------------------------------------------------------- #


class RetainedValue(_Snapshot):
    """A last-known-good snapshot, with the moment it was fetched.

    Only two calls retain: ``asset_pairs`` and ``balance``. Rule 2 spells out why
    the other two do not, and the client must never become generous about it — a
    retained stale spread is a loaded gun pointed at the one input that must have
    no fallback.

    Read by rule 14's emergency liquidation and by nothing else. ``age_micros``
    exists so the caller records *how* stale the value it used was, because
    invariant 14 requires every tolerated fetch failure to be recorded on the
    resulting trade.
    """

    value: PairRulesSnapshot | BalancesSnapshot
    fetched_at: int

    def age_micros(self, now: int) -> int:
        return now - self.fetched_at


# --------------------------------------------------------------------------- #
# Raw market data — WebSocket v2
# --------------------------------------------------------------------------- #


class StreamChannel(StrEnum):
    """The channels this system subscribes to.

    Names match ``scripts/record.py``'s defaults, because engine 2 supersedes that
    script and a recording whose channel names disagreed with the day-one archive
    would split the dataset in two.
    """

    BOOK = "book"
    TICKER = "ticker"
    TRADE = "trade"


class RawFrame(_Snapshot):
    """One frame off the socket, kept verbatim.

    The recorder writes ``payload`` unchanged. Reading a symbol or a timestamp out
    of it is not a mutation — the payload still goes to disk as it arrived — and a
    frame that names more than one symbol gets ``pair=None`` rather than a guess,
    exactly as ``scripts/record.py`` does.
    """

    channel: str
    pair: str | None
    ts_exchange: str | None
    payload: dict[str, Any]


class TradeTick(_Snapshot):
    """One executed trade. The input candles are built from.

    Candles come from trades and not from the ticker, because a candle is a
    statement about what traded: an interval in which nothing traded has no candle,
    and that absence is a fact rather than a hole to be filled. Building from a
    ticker stream would manufacture a candle for every quiet minute.
    """

    pair: str
    ts: _datetime.datetime
    price: Money
    qty: Money

    @field_validator("ts")
    @classmethod
    def _aware(cls, value: _datetime.datetime) -> _datetime.datetime:
        if value.tzinfo is None:
            raise ValueError("a tick timestamp must be timezone-aware UTC")
        return value.astimezone(_datetime.UTC)

    @field_validator("price", "qty")
    @classmethod
    def _positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("a trade has a positive price and a positive quantity")
        return value


class QuoteTick(_Snapshot):
    """Top of book off the stream, for staleness and spread checks.

    ``spread`` may be negative for the same reason :class:`OrderBookSnapshot`'s may:
    a crossed book is what engine 4 blocks on, so the client reports it rather than
    tidying it away.
    """

    pair: str
    ts: _datetime.datetime
    bid: Money
    ask: Money

    @field_validator("ts")
    @classmethod
    def _aware(cls, value: _datetime.datetime) -> _datetime.datetime:
        if value.tzinfo is None:
            raise ValueError("a tick timestamp must be timezone-aware UTC")
        return value.astimezone(_datetime.UTC)

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    def state_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "ts": self.ts.isoformat().replace("+00:00", "Z"),
            "bid": money_text(self.bid),
            "ask": money_text(self.ask),
            "spread": money_text(self.spread),
        }


# --------------------------------------------------------------------------- #
# Coercion — the same models, whichever client produced them
# --------------------------------------------------------------------------- #
#
# `tests/harness/fake_kraken.py` returns frozen dataclasses of its own with the same
# field names as the models above; C owns them and they were written before this
# module existed. An engine must work identically against the fake and against the
# real client, so rather than duck-typing every attribute access at every call site,
# each `coerce_*` takes whatever it was given and returns *this module's* validated
# model. The harness's data then goes through the same validators as the exchange's,
# which is stricter than the alternative rather than looser: a fixture with a zero
# `ordermin` or a fee written as a percent is refused in a test exactly as it would
# be in production.
#
# Typed as `Any` deliberately. The parameter is genuinely structural — two
# independently-owned classes, neither of which may import the other — and a Protocol
# here would only restate the field list a third time.


def coerce_pair_rules(snapshot: Any) -> PairRulesSnapshot:
    """A :class:`PairRulesSnapshot`, from one or from anything shaped like one."""
    if isinstance(snapshot, PairRulesSnapshot):
        return snapshot
    return PairRulesSnapshot(
        pairs={
            str(name): coerce_pair_rule(rule) for name, rule in dict(snapshot.pairs).items()
        },
        fetched_at=int(snapshot.fetched_at),
    )


def coerce_pair_rule(rule: Any) -> PairRule:
    if isinstance(rule, PairRule):
        return rule
    return PairRule(
        pair=str(rule.pair),
        base=str(rule.base),
        quote=str(rule.quote),
        ordermin=rule.ordermin,
        costmin=rule.costmin,
        tick_size=rule.tick_size,
        lot_decimals=int(rule.lot_decimals),
        pair_decimals=int(rule.pair_decimals),
    )


def coerce_fee_tier(snapshot: Any) -> FeeTierSnapshot:
    if isinstance(snapshot, FeeTierSnapshot):
        return snapshot
    return FeeTierSnapshot(
        tier=int(snapshot.tier),
        currency=str(snapshot.currency),
        volume_30d=snapshot.volume_30d,
        maker_fee_pct=snapshot.maker_fee_pct,
        taker_fee_pct=snapshot.taker_fee_pct,
        fetched_at=int(snapshot.fetched_at),
    )


def coerce_balances(snapshot: Any) -> BalancesSnapshot:
    if isinstance(snapshot, BalancesSnapshot):
        return snapshot
    return BalancesSnapshot(
        balances={str(code): amount for code, amount in dict(snapshot.balances).items()},
        fetched_at=int(snapshot.fetched_at),
    )


def coerce_order_book(snapshot: Any) -> OrderBookSnapshot:
    """A book, refusing an empty side exactly as the real client does.

    The fake will happily serve a fixture with one side empty; this is where that
    becomes a failure rather than a zero spread, so a test cannot pass through a
    route production would refuse.
    """
    if isinstance(snapshot, OrderBookSnapshot):
        return snapshot
    return OrderBookSnapshot(
        pair=str(snapshot.pair),
        bids=tuple((price, volume) for price, volume in snapshot.bids),
        asks=tuple((price, volume) for price, volume in snapshot.asks),
        fetched_at=int(snapshot.fetched_at),
    )


# --------------------------------------------------------------------------- #
# Protocols
# --------------------------------------------------------------------------- #


@runtime_checkable
class KrakenClientProtocol(Protocol):
    """The REST half of ``context.clients.kraken``.

    Four calls, all read-only. ``AddOrder`` is deliberately absent: Phase 2 does not
    mutate the exchange, and placing an order belongs to Phase 6.

    Matches ``tests/harness/fake_kraken.py``'s declaration exactly, so the fake and
    the real client are interchangeable everywhere and a fail-closed test keeps
    asserting on the same shape across the handover.
    """

    async def asset_pairs(self) -> PairRulesSnapshot: ...

    async def trade_volume(self) -> FeeTierSnapshot: ...

    async def balance(self) -> BalancesSnapshot: ...

    async def order_book(self, pair: str, depth: int) -> OrderBookSnapshot: ...


@runtime_checkable
class MarketStreamProtocol(Protocol):
    """The streaming half, driven by engine 2 and read by engine 3.

    ``drain`` is the whole reason the seam is shaped this way. The loop is
    synchronous and ticks once a minute; the socket delivers continuously. So the
    stream buffers in the background and the engine takes everything buffered since
    the last tick, which is what lets a synchronous engine record an asynchronous
    feed without either side blocking the other.
    """

    def drain(self) -> tuple[RawFrame, ...]:
        """Every frame buffered since the last call, oldest first."""
        ...

    def drain_trades(self) -> tuple[TradeTick, ...]:
        """Every executed trade buffered since the last call, oldest first."""
        ...

    def latest_quote(self, pair: str) -> QuoteTick | None:
        """Top of book for one pair, or None when the stream has never seen it.

        None rather than a zeroed quote: absent is not zero, and engine 4 has to be
        able to tell a pair with no data from a pair with a zero spread.
        """
        ...

    @property
    def connected(self) -> bool: ...

    @property
    def gaps(self) -> tuple[Mapping[str, Any], ...]:
        """Every recorded break in the stream, each with its start, end and cause.

        A gap is marked, never healed. ``context/trading-invariants.md`` rule 11:
        a recording is append-only and a break is written down rather than closed.
        """
        ...
