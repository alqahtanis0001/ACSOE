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
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Any, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

__all__ = [
    "TERMINAL_ORDER_STATUSES",
    "USERREF_MAX",
    "USERREF_MIN",
    "Balances",
    "BalancesSnapshot",
    "BookLevel",
    "FeeTierSnapshot",
    "KrakenClientProtocol",
    "MarketStreamProtocol",
    "Money",
    "OrderAck",
    "OrderAckStatus",
    "OrderBookSnapshot",
    "OrderClientProtocol",
    "OrderRequest",
    "OrderSide",
    "OrderState",
    "OrderStatus",
    "OrderType",
    "PairRule",
    "PairRulesSnapshot",
    "QuoteTick",
    "RawFrame",
    "RetainedValue",
    "StreamChannel",
    "TradeTick",
    "UserRef",
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

    ``ts_recv`` is stamped by the stream at the moment the frame was read, from the
    injected clock. It cannot be stamped by engine 2 instead: the engine sees the
    frame up to a minute later, and a receive time that was really a drain time turns
    a latency measurement into a measurement of the loop tick.
    """

    channel: str
    pair: str | None
    ts_exchange: str | None
    ts_recv: str
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
# Orders — spec 84, the one surface paper and live both wear
# --------------------------------------------------------------------------- #
#
# Engines 18, 21 and 22 place, cancel and query orders through `OrderClientProtocol`
# on `context.clients.kraken`, and they cannot tell paper from live. That is the
# whole design (`architecture-context.md`, Modes): the mode difference lives in the
# client layer, so the same engine code runs in both and a paper run exercises the
# live path rather than a parallel one.
#
# Nothing here is a fee, a minimum, a tick size or a precision. Sizes and prices
# arrive already rounded by the caller using the pair's own `lot_decimals` and
# `pair_decimals` from `AssetPairs` — this module refuses to know what those are.
#
# The three models are deliberately strict about *coupling* rather than about
# values: a limit order without a price, a fill with no average price, a resting
# order with a close time. Each of those is a self-contradiction that a consumer
# would otherwise have to re-check, and "absent is never zero" is only true if
# something enforces it at the boundary.


#: Kraken's ``userref`` is a **signed 32-bit** integer, and it is the whole of the
#: system's order idempotency (invariant 8: never place an order without checking
#: whether that ``userref`` already exists). A value outside the range is not
#: truncated by the exchange in any way this system could predict, so it is refused
#: here rather than discovered as a mismatched order later.
USERREF_MIN = -2_147_483_648
USERREF_MAX = 2_147_483_647

#: The bounded field itself, so the request, the ack and the state cannot drift
#: apart about what a ``userref`` is. The refusal message is pydantic's constraint
#: message — *"Input should be greater than or equal to …"* — and that is on
#: purpose: in a model with ``extra="forbid"`` a refusal always names the field, so
#: a test matching the field name passes whether the bound rejected the value or
#: the field was deleted. Only the constraint text tells those apart.
UserRef = Annotated[int, Field(ge=USERREF_MIN, le=USERREF_MAX)]


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """``limit`` or ``market``, and the system almost never wants the second.

    Invariant 8: an entry is always a post-only limit, and an unfilled entry is
    cancelled rather than chased with a market order. ``MARKET`` exists because
    invariant 14's emergency liquidation exits as a taker, having already decided
    that getting flat beats getting a good price. Engine 18 must never construct
    one; that is asserted in engine 18's own tests, not here, because a client
    contract that could not express a taker exit would make rule 14 unimplementable.
    """

    LIMIT = "limit"
    MARKET = "market"


class OrderAckStatus(StrEnum):
    """What the exchange said about a placement, immediately.

    Three values, and they are a subset of :class:`OrderStatus`'s five with the
    same spellings — ``StrEnum`` members compare equal to the matching string, so
    ``ack.status == OrderStatus.RESTING`` is True and a consumer holding either
    enum can compare against either. They are separate types because a placement
    cannot come back ``cancelled`` or ``expired``: nothing has had time to happen
    yet, and a status set that can express it invites a consumer to handle it.
    """

    RESTING = "resting"
    FILLED = "filled"
    REJECTED = "rejected"


class OrderStatus(StrEnum):
    """Where an order is now.

    ``RESTING`` is the only non-terminal one. The other four mean the order is
    finished and :attr:`OrderState.closed_at` says when.
    """

    RESTING = "resting"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


#: Every status that means the order is over. Named once so the coupling rule in
#: :class:`OrderState` and any consumer asking "is this done" cannot disagree.
TERMINAL_ORDER_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }
)


class OrderRequest(_Snapshot):
    """One order, as the system asks for it.

    ``post_only`` has **no default**. Invariant 8 makes every entry post-only and
    invariant 14 makes a liquidation a taker, so the right answer differs per call
    site and a default would be silently right in one of the two places and
    silently wrong in the other — producing, in the wrong direction, an entry that
    crosses the book and pays taker fees the cost gate never priced.
    """

    pair: str
    side: OrderSide
    order_type: OrderType
    qty: Money
    limit_price: Money | None = None
    post_only: bool
    userref: UserRef

    @field_validator("qty")
    @classmethod
    def _qty_is_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("an order quantity must be greater than zero")
        return value

    @field_validator("limit_price")
    @classmethod
    def _price_is_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("a limit price must be greater than zero")
        return value

    @model_validator(mode="after")
    def _price_matches_the_type(self) -> OrderRequest:
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError(
                "a limit order needs a limit_price; there is nothing for it to rest at"
            )
        if self.order_type is OrderType.MARKET and self.limit_price is not None:
            raise ValueError(
                "a market order has no limit_price; a price here is ignored by the "
                "exchange and believed by everything downstream, which is the worst "
                "of both"
            )
        return self

    @model_validator(mode="after")
    def _post_only_is_a_limit_flag(self) -> OrderRequest:
        if self.post_only and self.order_type is OrderType.MARKET:
            raise ValueError(
                "post_only is Kraken's oflags=post, a limit-order flag. A market order "
                "always takes liquidity, so post_only on one is a contradiction rather "
                "than a flag the exchange would quietly ignore"
            )
        return self

    def state_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "side": str(self.side),
            "order_type": str(self.order_type),
            "qty": money_text(self.qty),
            "limit_price": None if self.limit_price is None else money_text(self.limit_price),
            "post_only": self.post_only,
            "userref": self.userref,
        }


class OrderAck(_Snapshot):
    """What came back from the placement, before anything else happened.

    ``reason`` is present **exactly when** the status is ``rejected``, and it is
    non-empty. A rejection with no reason is the shape that makes a paper run and a
    live run indistinguishable in the logs for the wrong reasons; a reason attached
    to a resting order is a note nobody can interpret. A post-only order that would
    have crossed the book is the ordinary rejection here, and it names that cause.
    """

    userref: UserRef
    order_id: str
    status: OrderAckStatus
    reason: str | None = None

    @model_validator(mode="after")
    def _reason_iff_rejected(self) -> OrderAck:
        rejected = self.status is OrderAckStatus.REJECTED
        if rejected and not (self.reason or "").strip():
            raise ValueError(
                "a rejected order must name why it was rejected; a rejection with no "
                "cause cannot be told from a rejection nobody recorded"
            )
        if not rejected and self.reason is not None:
            raise ValueError(
                f"reason belongs to a rejection; status is {self.status} and a reason "
                "on an accepted order is a note no consumer can act on"
            )
        return self

    def state_dict(self) -> dict[str, Any]:
        return {
            "userref": self.userref,
            "order_id": self.order_id,
            "status": str(self.status),
            "reason": self.reason,
        }


class OrderState(_Snapshot):
    """Where one order stands now, from a query or a cancel.

    ``qty`` and ``limit_price`` describe **what the order is**; everything after
    them describes what has happened to it. The first two were added by the spec 84
    amendment of 2026-09-16 and the reason is worth keeping next to the fields.
    Without them, an order resting at the exchange that the store has never recorded
    — placed, then the process died before engine 19 ran — could be *detected* by
    engine 18 and not *described*, so no row could be written and nothing would ever
    cancel it. In the operator's words: an order that cannot be cancelled because
    nothing recorded enough to identify it is an unmanaged exposure, and that is the
    failure invariant 8 exists to prevent. Kraken returns both in ``descr`` on
    ``OpenOrders`` and ``QueryOrders``, so this is faithful to what a live client
    will actually hold rather than a field the paper side alone can fill.

    ``qty`` is **required**. Every order has one, at the exchange and in the store,
    and an optional field here would recreate exactly the ambiguity the amendment
    removes — a consumer could not tell "no quantity was recorded" from "no
    quantity exists".

    ``limit_price`` follows :class:`OrderRequest`'s coupling: present for a limit
    order, absent for a market one. There is no ``order_type`` beside it because
    presence **is** the statement and the two would be a second copy that can
    disagree; a consumer that needs the type reads ``limit_price is not None``.
    The lead's ruling of 2026-09-16 closes the one weakening that leaves **at the
    consumer that knows the answer**: engine 18 asked for a post-only buy limit, so
    an ``OrderState`` coming back with no ``limit_price`` is the exchange
    contradicting the placement rather than a market order, and engine 18 refuses
    to record it. The model cannot make that call; the placer can.

    ``opened_at`` completes the same amendment. It is optional, and **absent means
    the exchange did not say** — not "now" and not zero. Kraken's ``OpenOrders``
    returns ``opentm``, so a live client will normally have it; a consumer that
    needs a placement time and has none keeps whatever fail-closed behaviour it
    already had, which for engine 18 is to publish no row and name the ``userref``.
    That narrows the unrecorded-order gap to the single case the exchange itself
    cannot answer.

    Seven couplings are enforced, because each of them is a fact a consumer would
    otherwise have to re-derive and could re-derive differently:

    * ``qty`` is above zero. An order for nothing is not an order.
    * ``filled_qty`` never exceeds ``qty``. An order cannot fill more than it asked
      for, and a state that said so would put a position the exchange never opened
      into the ledger. Only checkable now that ``qty`` is here.
    * ``avg_fill_price`` is present **exactly when** ``filled_qty`` is above zero.
      An unfilled order has no average price, and ``0`` is not one — it would put a
      zero cost basis into the ledger.
    * an order that filled nothing paid no fee.
    * ``filled`` means something filled.
    * ``closed_at`` is present **exactly when** the status is terminal. A resting
      order has not closed; a cancelled one has, and engine 19 records when.
    """

    userref: UserRef
    order_id: str
    status: OrderStatus
    qty: Money
    limit_price: Money | None = None
    filled_qty: Money
    avg_fill_price: Money | None = None
    fee: Money
    opened_at: int | None = None
    closed_at: int | None = None

    @field_validator("filled_qty", "fee")
    @classmethod
    def _not_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("a filled quantity and a fee are never negative")
        return value

    @field_validator("qty")
    @classmethod
    def _qty_is_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("an order quantity must be greater than zero")
        return value

    @field_validator("limit_price")
    @classmethod
    def _limit_price_is_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("a limit price must be greater than zero")
        return value

    @field_validator("avg_fill_price")
    @classmethod
    def _price_is_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("an average fill price must be greater than zero")
        return value

    @model_validator(mode="after")
    def _fill_never_exceeds_the_order(self) -> OrderState:
        if self.filled_qty > self.qty:
            raise ValueError(
                f"filled_qty {money_text(self.filled_qty)} exceeds qty "
                f"{money_text(self.qty)}; an order cannot fill more than it asked for"
            )
        return self

    @model_validator(mode="after")
    def _fill_fields_agree(self) -> OrderState:
        filled = self.filled_qty > 0
        if filled and self.avg_fill_price is None:
            raise ValueError(
                f"{money_text(self.filled_qty)} filled with no avg_fill_price; a fill "
                "without a price cannot be valued and must not reach the ledger"
            )
        if not filled and self.avg_fill_price is not None:
            raise ValueError(
                "avg_fill_price is set on an order that filled nothing; absent is not "
                "zero and a price for no fill is neither"
            )
        if not filled and self.fee != 0:
            raise ValueError("an order that filled nothing paid no fee")
        if self.status is OrderStatus.FILLED and not filled:
            raise ValueError("status is filled and filled_qty is zero")
        return self

    @model_validator(mode="after")
    def _closed_at_matches_the_status(self) -> OrderState:
        terminal = self.status in TERMINAL_ORDER_STATUSES
        if terminal and self.closed_at is None:
            raise ValueError(f"status is {self.status}, which is over, so it closed at some point")
        if not terminal and self.closed_at is not None:
            raise ValueError(f"status is {self.status}, which is not over, so nothing closed")
        return self

    @model_validator(mode="after")
    def _it_did_not_close_before_it_opened(self) -> OrderState:
        """Only checkable when the exchange supplied both, which is the common case.

        Equality is allowed: a marketable order placed and finished inside one
        microsecond carries one stamp twice, and in paper the same injected clock
        reading produces exactly that. The refusal is for the strictly impossible
        ordering, which is a clock or a mapping defect and would put a negative
        lifetime into anything that measures how long an entry rested.
        """
        opened, closed = self.opened_at, self.closed_at
        if opened is not None and closed is not None and closed < opened:
            raise ValueError(
                f"closed_at {closed} is before opened_at {opened}; "
                "an order cannot close before it opened"
            )
        return self

    def state_dict(self) -> dict[str, Any]:
        return {
            "userref": self.userref,
            "order_id": self.order_id,
            "status": str(self.status),
            "qty": money_text(self.qty),
            "limit_price": None if self.limit_price is None else money_text(self.limit_price),
            "filled_qty": money_text(self.filled_qty),
            "avg_fill_price": (
                None if self.avg_fill_price is None else money_text(self.avg_fill_price)
            ),
            "fee": money_text(self.fee),
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
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

    Four calls, all read-only. Ordering is **not** here: it is
    :class:`OrderClientProtocol`, a separate protocol landed by spec 84, so that a
    consumer that only reads the market — engines 1, 2, 3, 4, 9 — cannot be handed
    an object that can place an order, and so that the paper broker can implement
    one protocol and forward the other.

    Matches ``tests/harness/fake_kraken.py``'s declaration exactly, so the fake and
    the real client are interchangeable everywhere and a fail-closed test keeps
    asserting on the same shape across the handover.
    """

    async def asset_pairs(self) -> PairRulesSnapshot: ...

    async def trade_volume(self) -> FeeTierSnapshot: ...

    async def balance(self) -> BalancesSnapshot: ...

    async def order_book(self, pair: str, depth: int) -> OrderBookSnapshot: ...


@runtime_checkable
class OrderClientProtocol(Protocol):
    """The order half of ``context.clients.kraken``. Spec 84.

    Four calls, async like every other call on the client, and **identical in
    paper and live**. In paper mode ``build_clients`` wraps :class:`KrakenClient`
    in B's paper broker (``clients/paper/``, operator ruling 2026-09-16), which
    implements this protocol and forwards the read-only calls; in live mode the
    real client implements it by **refusing**, until Phase 8 builds it. There is
    no third case and no flag that turns the refusal off.

    ``userref`` is the key everywhere, not ``order_id``. Invariant 8 makes it the
    system's idempotency token — the system chooses it before the order exists,
    so it is the only identifier that survives a placement whose answer never came
    back. ``order_id`` is the exchange's, arrives afterwards, and is carried for
    reconciliation rather than used for lookup.

    A call that cannot be completed **raises** rather than returning an empty
    result. Invariant 3: the absence of a "no" is never a "yes", and an
    ``open_orders`` that answered ``()`` during an outage would tell engine 21
    there was nothing resting to cancel.
    """

    async def add_order(self, request: OrderRequest) -> OrderAck: ...

    async def cancel_order(self, userref: int) -> OrderState: ...

    async def query_orders(self, userrefs: Sequence[int]) -> tuple[OrderState, ...]: ...

    async def open_orders(self) -> tuple[OrderState, ...]: ...


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

    def drain_gaps(self) -> tuple[Mapping[str, Any], ...]:
        """Every break recorded since the last call, oldest first.

        Drained rather than read, so engine 2 stays stateless across cycles
        (architecture invariant 1) and does not have to remember which breaks it has
        already written into the archive.
        """
        ...

    def drain_trades(self) -> tuple[TradeTick, ...]:
        """Every executed trade buffered since the last call, oldest first.

        Consuming. Nothing in the live loop uses it — engine 3 wants a window, not a
        queue — but a consumer that genuinely processes each trade once needs one.
        """
        ...

    def recent_trades(self) -> tuple[TradeTick, ...]:
        """The buffered trades **without** clearing them, oldest first.

        What engine 3 reads. It has to rebuild the same 15-minute bar on each of the
        fifteen ticks that bar spans, and an engine is stateless across cycles, so the
        window lives here rather than in the engine.
        """
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
