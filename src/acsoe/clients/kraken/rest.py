"""The Kraken REST client: the envelope, the mapping, the retention.

Three things happen here and nowhere else.

**The envelope.** Kraken wraps every answer in ``{"error": [...], "result": {...}}``
and does **not** use HTTP status to signal application errors, so a 200 carrying a
populated ``error`` array is a failure. :func:`parse_envelope` is the only place a
response body is opened, and it has to get *both* halves right: a populated array
raises :class:`~acsoe.clients.kraken.errors.KrakenAPIError`, and an empty one
parses cleanly and yields its ``result``. A parser that raised on everything would
satisfy the first half perfectly and be useless.

**The mapping.** The exchange's field names are turned into the models in
``contracts.py`` by the four ``map_*`` functions below, and a missing field is a
failure rather than a default. This is the one part of this module that cannot be
proved offline: ``AGENTS.md`` says any Kraken endpoint shape an agent remembers is
stale, so the mapping is written against the committed fixtures in
``tests/fixtures/kraken/`` and is confirmed against the live endpoints by
``--live``, which is opt-in. It is deliberately isolated into named functions so
that confirming it is a small, obvious edit rather than an archaeology exercise.

**Caching, and retention, which are two different mechanisms.** They share a word
and collapsing them breaks the kill switch, so the client keeps them in two
separate places on purpose.

*The cache answers "may I use this now."* ``asset_pairs`` and ``trade_volume`` keep
their parsed snapshot for ``kraken.cache_ttl_s.asset_pairs`` and
``kraken.cache_ttl_s.trade_volume`` seconds respectively, so a one-minute loop tick
does not re-fetch pair rules that change on the timescale of a listing. Age is
measured against the **injected clock**. Past its TTL the entry is dropped and the
call re-fetches; **if that re-fetch fails the call raises and the expired entry is
never returned**, because invariant 2 says a cache stale beyond its TTL counts as a
failed fetch — for trading, a stale value does not exist.

*Retention answers "what is the last thing we knew."* ``asset_pairs`` and
``balance`` retain their last successful value with the time it was fetched and
**never discard it**, not on a failure and not on a TTL expiry, because rule 14's
emergency liquidation has to complete during the outage that triggered it.
``trade_volume`` and ``order_book`` retain nothing: their only reader is the cost
gate, and invariant 2 says an assumed spread or fee invalidates that gate. A TTL
cache for ``trade_volume`` is legitimate; a last-known-good for it is not.

``balance`` and ``order_book`` are not cached at all. Balances change on every fill
and a stale spread is the loaded gun invariant 2 names.

**No value in this module is a number.** No fee, no minimum, no tick size, no
precision — not as a constant, not as a fallback, not in a comment.

**No credential is ever rendered.** The signing inputs never enter an exception
message, a log line, or a repr; the transport is handed headers it does not print,
and every error carries the method and the path only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final, NoReturn, Protocol, TypeVar
from urllib.parse import urlencode

from acsoe.clients.kraken.contracts import (
    BalancesSnapshot,
    BookLevel,
    FeeTierSnapshot,
    OrderAck,
    OrderBookSnapshot,
    OrderRequest,
    OrderState,
    PairRule,
    PairRulesSnapshot,
    RetainedValue,
    to_micros,
)
from acsoe.clients.kraken.errors import KrakenAPIError, KrakenError, KrakenUnavailableError
from acsoe.clients.kraken.limiter import RateLimiter
from acsoe.platform.clock import Clock
from acsoe.platform.config import Config, Credentials

__all__ = [
    "HttpResponse",
    "HttpTransport",
    "HttpxTransport",
    "KrakenRestClient",
    "map_asset_pairs",
    "map_balances",
    "map_order_book",
    "map_trade_volume",
    "parse_envelope",
    "sign_request",
]

KRAKEN_REST_URL = "https://api.kraken.com"

ASSET_PAIRS_PATH = "/0/public/AssetPairs"
ORDER_BOOK_PATH = "/0/public/Depth"
TRADE_VOLUME_PATH = "/0/private/TradeVolume"
BALANCE_PATH = "/0/private/Balance"

#: Calls whose last successful value is kept for rule 14 and nothing else.
RETAINED_CALLS = frozenset({"asset_pairs", "balance"})

#: The four calls of ``OrderClientProtocol``. Written out so the refusal below and
#: the test that walks it read from one list rather than two that can drift.
ORDER_CALLS = ("add_order", "cancel_order", "query_orders", "open_orders")

#: Calls that may be served from a TTL-bounded cache. Deliberately not the same set
#: as :data:`RETAINED_CALLS`: ``balance`` is retained but never cached, and
#: ``trade_volume`` is cached but never retained. Written out so the difference is
#: visible rather than inferred from two scattered ``if`` statements.
CACHED_CALLS = frozenset({"asset_pairs", "trade_volume"})

_MICROSECONDS_PER_SECOND = 1_000_000

#: The two snapshot types that may be cached. A value-restricted ``TypeVar`` rather
#: than a union, so :meth:`KrakenRestClient._fresh` hands each caller back its own
#: type instead of a union both call sites would have to narrow again.
_Cached = TypeVar("_Cached", PairRulesSnapshot, FeeTierSnapshot)


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class HttpResponse:
    """Just enough of an HTTP response to parse an envelope from."""

    status_code: int
    body: bytes


class HttpTransport(Protocol):
    """How this client reaches HTTP.

    A seam rather than a direct ``httpx`` call, and it exists for a reason that is
    not testability in the abstract: ``tests/conftest.py``'s autouse network guard
    patches ``httpx.AsyncClient.send`` itself, so even a ``MockTransport`` cannot be
    exercised through ``httpx`` inside a test. Injecting at this level means the
    envelope, the mapping and the retention are all covered offline while the guard
    stays exactly as strict as it is.
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        content: bytes | None,
        timeout_s: float,
    ) -> HttpResponse: ...


class HttpxTransport:
    """The real transport. ``httpx`` plus nothing.

    A fresh ``AsyncClient`` per request, deliberately. The runtime loop is
    synchronous and ticks once a minute, so each tick's fetches run under one
    ``asyncio.run`` and a client held across ticks would be bound to an event loop
    that has since closed. Three handshakes a minute is not a cost worth a
    connection-pool lifecycle bug in the path that prices trades.
    """

    def __init__(self, *, verify: bool = True) -> None:
        self._verify = verify

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        content: bytes | None,
        timeout_s: float,
    ) -> HttpResponse:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=timeout_s, verify=self._verify) as client:
                response = await client.request(
                    method, url, headers=dict(headers), content=content
                )
        except httpx.HTTPError as exc:
            # The URL is safe to name; the headers are not, and are never rendered.
            raise KrakenUnavailableError(f"{method} {url} failed at the transport", exc) from exc
        return HttpResponse(status_code=response.status_code, body=response.content)


# --------------------------------------------------------------------------- #
# The envelope — both halves
# --------------------------------------------------------------------------- #


def parse_envelope(body: bytes | str, call: str) -> Any:
    """Open one Kraken response and return its ``result``.

    Raises :class:`KrakenAPIError` when ``error`` is non-empty, whatever the HTTP
    status was, and :class:`KrakenUnavailableError` when the body is not a Kraken
    envelope at all — a proxy error page, a truncated read, an HTML maintenance
    notice. The second case is "we did not get an answer" and both block.
    """
    try:
        payload = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise KrakenUnavailableError(f"{call}: response body was not JSON", exc) from exc
    if not isinstance(payload, dict) or "error" not in payload:
        raise KrakenUnavailableError(
            f"{call}: response body was not a Kraken envelope "
            "({'error': [...], 'result': {...}})"
        )
    errors = payload.get("error") or []
    if not isinstance(errors, list):
        raise KrakenUnavailableError(f"{call}: envelope 'error' was not a list")
    if errors:
        rendered = [str(item) for item in errors]
        raise KrakenAPIError(f"{call} failed: {'; '.join(rendered)}", rendered)
    if "result" not in payload:
        raise KrakenUnavailableError(
            f"{call}: envelope carried no 'result' and no error, which is neither a "
            "yes nor a no"
        )
    return payload["result"]


# --------------------------------------------------------------------------- #
# Mapping — the field-name assumption, isolated on purpose
# --------------------------------------------------------------------------- #


def _require(result: Mapping[str, Any], key: str, call: str) -> Any:
    if key not in result:
        raise KrakenUnavailableError(
            f"{call}: the response carried no {key!r}. The field names this client maps "
            "are confirmed against the live endpoint by --live; a rename shows up here "
            "as a failure rather than as a default."
        )
    return result[key]


def _decimal(value: Any, key: str, call: str) -> Decimal:
    if isinstance(value, float):
        raise KrakenUnavailableError(
            f"{call}: {key} arrived as a float, which has already lost precision"
        )
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise KrakenUnavailableError(f"{call}: {key} is not a decimal number") from exc


#: Where Kraken's websocket v2 names an asset differently from the REST ``wsname``.
#:
#: **Two entries, and they are not guesses.** They are the same two ``funding.py`` and
#: ``fees.py`` already carry, and they are confirmed against spec 127's two recordings: the
#: rule below reproduces the v2 symbol for **1,406 of the recording's 1,450 pairs and
#: disagrees on none**, the remainder being pairs the recorded name join keys by ``altname``
#: rather than by the REST key. Anything Kraken renames next shows up as a pair whose symbol
#: is absent from the v2 feed, which engine 7 then excludes as having no live quote — visible,
#: not silent.
WS_ASSET_ALIASES: Final = {"XBT": "BTC", "XDG": "DOGE"}


def _engine_names(name: str, entry: Mapping[str, Any]) -> tuple[str, str, str] | None:
    """``(symbol, base, quote)`` in the names the engines and the v2 feed use.

    Phase 8, F3. REST keys a pair ``XXBTZUSD`` with base ``XXBT`` and quote ``ZUSD``; engine 3
    publishes quotes under the v2 symbol ``BTC/USD``, and engine 7 scans the union of the two
    key spaces — so with REST keys **every pair is excluded as having no rules and every quote
    as having no rules either**, and engine 2 derives the websocket subscription from these
    same keys, so the daemon would subscribe with symbols the v2 feed rejects and receive
    nothing at all.

    Taken from Kraken's own ``wsname`` rather than by stripping the legacy ``X``/``Z``
    prefixes: stripping is a guess that breaks on every asset whose name legitimately starts
    with one (``XTZ`` would become ``TZ``), while ``wsname`` is the exchange telling us.

    **A body with no ``wsname`` is left exactly as it is** — that is the invented Phase 0
    fixture, which is already keyed the way the engines key pairs, and the fake client that
    serves it must keep working.
    """
    wsname = entry.get("wsname")
    if not isinstance(wsname, str) or "/" not in wsname:
        base, quote = entry.get("base"), entry.get("quote")
        if not isinstance(base, str) or not isinstance(quote, str):
            return None
        return name, base, quote
    raw_base, _, raw_quote = wsname.partition("/")
    base = WS_ASSET_ALIASES.get(raw_base, raw_base)
    quote = WS_ASSET_ALIASES.get(raw_quote, raw_quote)
    if not base or not quote:
        return None
    return f"{base}/{quote}", base, quote


def asset_code_names(result: Any) -> dict[str, str]:
    """Kraken's asset codes to the engines' names — ``{"XXBT": "BTC", "ZUSD": "USD"}``.

    Derived from the ``AssetPairs`` body itself, which carries both spellings for every asset
    in use: the prefixed ``base``/``quote`` and the plain ones inside ``wsname``. Nothing is
    hardcoded and nothing is stripped.

    Needed because ``Balance`` answers in the same legacy codes, and engine 7 matches a pair's
    quote against the balances **and** against ``trading.stable_quote_currencies``. Normalising
    the pairs alone would exclude every pair for want of a quote balance instead; normalising
    neither would exclude every pair as not provably stable.
    """
    names: dict[str, str] = {}
    if not isinstance(result, Mapping):
        return names
    for name, entry in result.items():
        if not isinstance(entry, Mapping):
            continue
        resolved = _engine_names(str(name), entry)
        if resolved is None:
            continue
        _symbol, base, quote = resolved
        for code, engine_name in (
            (entry.get("base"), base),
            (entry.get("quote"), quote),
        ):
            if isinstance(code, str) and code and engine_name:
                names[code] = engine_name
    return names


def engine_pair_names(result: Any) -> dict[str, str]:
    """Kraken's REST pair keys to the names a snapshot is keyed by — ``{"XXBTZUSD": "BTC/USD"}``.

    The join a caller needs once F3 has landed. Before it, a caller holding the REST body could
    ask which pairs :func:`map_asset_pairs` dropped with ``set(result) - set(snapshot.pairs)``;
    now that the snapshot is keyed by the v2 symbol, that subtraction names **every** pair
    instead of the unparsable ones. Going through the same :func:`_engine_names` as the snapshot
    itself is what stops the two drifting: a pair this function cannot name is a pair the
    snapshot does not contain either.
    """
    names: dict[str, str] = {}
    if not isinstance(result, Mapping):
        return names
    for name, entry in result.items():
        if not isinstance(entry, Mapping):
            continue
        resolved = _engine_names(str(name), entry)
        if resolved is not None:
            names[str(name)] = resolved[0]
    return names


def map_asset_pairs(result: Any, *, fetched_at: int) -> PairRulesSnapshot:
    """``AssetPairs`` result to :class:`PairRulesSnapshot`, keyed as the engines key pairs.

    A pair whose entry is missing a field is **dropped with the failure surfaced**
    rather than defaulted: a pair with no ``ordermin`` cannot be sized, and rule 2
    says a missing pair rule blocks that pair with no fallback. Dropping one pair
    does not fail the whole fetch, because one delisted or malformed symbol must not
    take the universe down with it.

    **Keys and asset names come from :func:`_engine_names`** (Phase 8, F3), so this snapshot
    speaks the same names as engine 3's quotes, engine 2's subscription and every gate.
    """
    if not isinstance(result, Mapping):
        raise KrakenUnavailableError("asset_pairs: result was not a mapping of pairs")
    rules: dict[str, PairRule] = {}
    for name, entry in result.items():
        if not isinstance(entry, Mapping):
            continue
        resolved = _engine_names(str(name), entry)
        if resolved is None:
            continue
        symbol, base, quote = resolved
        try:
            rules[symbol] = PairRule(
                pair=symbol,
                base=base,
                quote=quote,
                ordermin=_decimal(_require(entry, "ordermin", "asset_pairs"), "ordermin", "ap"),
                costmin=_decimal(_require(entry, "costmin", "asset_pairs"), "costmin", "ap"),
                tick_size=_decimal(
                    _require(entry, "tick_size", "asset_pairs"), "tick_size", "ap"
                ),
                lot_decimals=int(_require(entry, "lot_decimals", "asset_pairs")),
                pair_decimals=int(_require(entry, "pair_decimals", "asset_pairs")),
            )
        except (KrakenUnavailableError, ValueError, TypeError):
            # One unusable pair is not a failed fetch. It is simply a pair with no
            # rules, and a pair with no rules is blocked by rule 2 wherever it is
            # reached for. Keeping it out of the snapshot is what makes that true.
            continue
    if not rules:
        raise KrakenUnavailableError(
            "asset_pairs: no pair in the response carried a complete rule set"
        )
    return PairRulesSnapshot(pairs=rules, fetched_at=fetched_at)


def map_trade_volume(result: Any, *, fetched_at: int) -> FeeTierSnapshot:
    """``TradeVolume`` result to :class:`FeeTierSnapshot`.

    Every field is required. There is no "assume a tier" here and there must never
    be. Invariant 2 carries the reasoning: the paper-mode fee fallback was retired on
    2026-09-10 and the last paper-mode fallback of any kind on 2026-09-16, so a
    confirmed pair with no fee data blocks that pair in paper mode exactly as in live.
    Nothing downstream is waiting to supply what this function refuses to invent.
    """
    if not isinstance(result, Mapping):
        raise KrakenUnavailableError("trade_volume: result was not a mapping")
    call = "trade_volume"
    return FeeTierSnapshot(
        tier=int(_require(result, "tier", call)),
        currency=str(_require(result, "currency", call)),
        volume_30d=_decimal(_require(result, "volume_30d", call), "volume_30d", call),
        maker_fee_pct=_decimal(_require(result, "maker_fee_pct", call), "maker_fee_pct", call),
        taker_fee_pct=_decimal(_require(result, "taker_fee_pct", call), "taker_fee_pct", call),
        fetched_at=fetched_at,
    )


def map_balances(
    result: Any, *, fetched_at: int, asset_names: Mapping[str, str] | None = None
) -> BalancesSnapshot:
    """``Balance`` result to :class:`BalancesSnapshot`. A currency-to-amount map.

    ``asset_names`` renames Kraken's legacy codes to the engines' own (``ZUSD`` to ``USD``),
    from :func:`asset_code_names` (Phase 8, F3). **A code the map does not know is passed
    through unchanged** rather than dropped or guessed at: an unknown asset with a balance is
    still a balance, and engine 7 will simply find no pair quoted in it.

    Absent, nothing is renamed — which is the invented Phase 0 fixture, whose codes are already
    the engines' names.
    """
    if not isinstance(result, Mapping):
        raise KrakenUnavailableError("balance: result was not a mapping")
    names = asset_names or {}
    balances: dict[str, Decimal] = {}
    for code, amount in result.items():
        engine_name = names.get(str(code), str(code))
        value = _decimal(amount, str(code), "balance")
        # Two codes can rename onto one name only if Kraken lists the same asset twice; sum
        # rather than let the last one win, so a balance can never be silently dropped.
        balances[engine_name] = balances.get(engine_name, Decimal(0)) + value
    return BalancesSnapshot(balances=balances, fetched_at=fetched_at)


def _levels(raw: Any, side: str, depth: int, pair: str) -> tuple[BookLevel, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise KrakenUnavailableError(f"order_book: {pair} {side} was not a list of levels")
    levels: list[BookLevel] = []
    for entry in list(raw)[:depth]:
        if not isinstance(entry, Sequence) or isinstance(entry, (str, bytes)) or len(entry) < 2:
            raise KrakenUnavailableError(f"order_book: {pair} {side} level is malformed")
        levels.append(
            (
                _decimal(entry[0], f"{side}.price", "order_book"),
                _decimal(entry[1], f"{side}.volume", "order_book"),
            )
        )
    return tuple(levels)


def map_order_book(result: Any, *, pair: str, depth: int, fetched_at: int) -> OrderBookSnapshot:
    """``Depth`` result to :class:`OrderBookSnapshot`.

    An unknown pair, or one with an empty side, raises. It never returns a book with
    no levels: that would reach the cost gate as a zero spread, and invariant 2 says
    an assumed spread invalidates the gate outright.
    """
    if not isinstance(result, Mapping):
        raise KrakenUnavailableError("order_book: result was not a mapping")
    book = result.get(pair)
    if not isinstance(book, Mapping):
        raise KrakenAPIError(
            f"order_book failed: EQuery:Unknown asset pair ({pair})",
            ["EQuery:Unknown asset pair"],
        )
    try:
        return OrderBookSnapshot(
            pair=pair,
            bids=_levels(_require(book, "bids", "order_book"), "bids", depth, pair),
            asks=_levels(_require(book, "asks", "order_book"), "asks", depth, pair),
            fetched_at=fetched_at,
        )
    except ValueError as exc:
        # An empty side. `OrderBookSnapshot` refuses it, and it has to reach the
        # caller as a failure rather than as a snapshot.
        raise KrakenUnavailableError(f"order_book: {pair} came back unusable: {exc}") from exc


# --------------------------------------------------------------------------- #
# Signing
# --------------------------------------------------------------------------- #


def sign_request(*, path: str, nonce: int, form: Mapping[str, Any], secret: str) -> str:
    """Kraken's private-endpoint signature.

    HMAC-SHA512 over the path and the SHA-256 of the nonced form body, keyed by the
    base64-decoded secret, returned base64.

    **This is the one thing in this package that cannot be proved offline.** Its
    inputs and its output are deterministic and are tested as such, but whether the
    scheme is the one Kraken currently accepts can only be established by a call
    that succeeds — and ``AGENTS.md`` warns that remembered endpoint shapes are
    stale. It is confirmed by ``--live`` once the operator restores a key, and it is
    recorded as an open item in ``context/progress/a-platform.md`` until then.

    Raises rather than returning anything derived from a malformed secret. Nothing
    here is logged: not the secret, not the nonce, not the returned signature.
    """
    try:
        decoded = base64.b64decode(secret, validate=True)
    except (ValueError, TypeError) as exc:
        raise KrakenUnavailableError(
            "the API secret is not valid base64. The value itself is never rendered."
        ) from exc
    post = urlencode({"nonce": nonce, **form})
    digest = hashlib.sha256(f"{nonce}{post}".encode()).digest()
    signature = hmac.new(decoded, path.encode() + digest, hashlib.sha512)
    return base64.b64encode(signature.digest()).decode()


# --------------------------------------------------------------------------- #
# The client
# --------------------------------------------------------------------------- #


class KrakenRestClient:
    """Read-only REST access to Kraken.

    Four calls, all read-only. ``AddOrder`` is not here and must not be added in
    this phase: Phase 2 does not mutate the exchange.

    :param clock: the injected clock. Nothing in this package reads the wall clock.
    :param limiter: the shared rate limiter. Every call goes through it.
    :param transport: HTTP. Injected, so the envelope and the mapping are testable
        without the network and without relaxing the test guard.
    :param credentials: the key pair, or None. Absent credentials make the two
        private calls raise rather than silently return something.
    :param asset_pairs_ttl_s: ``kraken.cache_ttl_s.asset_pairs``, in seconds, or
        None when the operator has not supplied it. None makes ``asset_pairs()``
        raise rather than caching for an interval nobody chose.
    :param trade_volume_ttl_s: ``kraken.cache_ttl_s.trade_volume``, likewise. Read
        from its own key and kept in its own field: the two TTLs are independent
        and a single shared one is the shape spec 38 exists to prevent.
    """

    def __init__(
        self,
        *,
        clock: Clock,
        limiter: RateLimiter,
        transport: HttpTransport | None = None,
        credentials: Credentials | None = None,
        base_url: str = KRAKEN_REST_URL,
        timeout_s: float = 20.0,
        book_depth: int = 10,
        asset_pairs_ttl_s: int | None = None,
        trade_volume_ttl_s: int | None = None,
    ) -> None:
        self._clock = clock
        self._limiter = limiter
        self._transport: HttpTransport = transport if transport is not None else HttpxTransport()
        self._credentials = credentials
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._book_depth = book_depth
        self._retained: dict[str, RetainedValue] = {}
        self._nonce = 0
        #: Kraken's asset codes to the engines' names, from the last `asset_pairs` body
        #: (Phase 8, F3). Empty until the first successful fetch.
        self._asset_names: dict[str, str] = {}
        # Two TTLs, two fields, two caches. Nothing here is shared between the two
        # calls, so no future edit can accidentally make one TTL govern both.
        self._asset_pairs_ttl_s = asset_pairs_ttl_s
        self._trade_volume_ttl_s = trade_volume_ttl_s
        self._cached_asset_pairs: PairRulesSnapshot | None = None
        self._cached_trade_volume: FeeTierSnapshot | None = None

    @classmethod
    def from_config(
        cls,
        config: Config,
        *,
        clock: Clock,
        limiter: RateLimiter,
        transport: HttpTransport | None = None,
        credentials: Credentials | None = None,
        base_url: str = KRAKEN_REST_URL,
    ) -> KrakenRestClient:
        """Build a client whose tuning comes from ``config`` and from nowhere else.

        Spec 38 step 3: the TTLs come from ``kraken.cache_ttl_s.asset_pairs`` and
        ``kraken.cache_ttl_s.trade_volume``, **never a literal**. This exists so
        there is one construction site that cannot forget them — the constructor
        takes them as optional parameters because a test and a script build clients
        directly, and an optional parameter is exactly the kind of thing a caller
        omits by accident. It omitted them here once already, which is how the two
        keys came to be unreadable from the daemon.

        The two are read as **two separate attribute accesses on two separate
        fields**. There is no intermediate variable holding "the TTL", because a
        single shared TTL is the shape spec 38 exists to prevent and the easiest way
        to reintroduce it is to write it down once.

        The limiter is a parameter rather than something built here: it is the *one*
        limiter, shared with the WebSocket client, and a factory that made its own
        would give the account two independent budgets against one rate limit.
        """
        return cls(
            clock=clock,
            limiter=limiter,
            transport=transport,
            credentials=credentials,
            base_url=base_url,
            timeout_s=config.kraken.rest_timeout_s,
            asset_pairs_ttl_s=config.kraken.cache_ttl_s.asset_pairs,
            trade_volume_ttl_s=config.kraken.cache_ttl_s.trade_volume,
        )

    # -- the cache: "may I use this now" ---------------------------------- #

    def _require_ttl(self, ttl_s: int | None, key: str) -> int:
        """The configured TTL, or a failure naming the key that is missing.

        A missing TTL is not "cache forever" and is not "never cache". It is an
        unanswerable question about whether a value is still good, and invariant 3
        says the absence of a "no" is never a "yes" — so the call fails the way a
        failed fetch fails, which is what every gate downstream already handles.
        """
        if ttl_s is None:
            raise KrakenUnavailableError(
                f"{key} is not configured, so there is no interval after which a cached "
                "snapshot stops being usable. Invariant 2 makes a stale value a failed "
                "fetch, and a TTL nobody chose cannot decide when that happens. Supply "
                f"{key} in config/default.yaml."
            )
        return ttl_s

    def _fresh(self, cached: _Cached | None, ttl_s: int) -> _Cached | None:
        """``cached`` when it is still inside its TTL by the injected clock, else None.

        Returns the entry rather than a boolean on purpose. A predicate leaves the
        caller holding an optional it has already proved is present, and the only
        ways to spend that are a narrowing ``assert`` — which ``python -O`` deletes
        out of the function that decides whether a fee is fresh enough to price a
        trade — or a redundant second check. Returning the value narrows it by
        ordinary control flow instead.

        A negative age — the clock stood still or moved back — counts as expired.
        Fail-closed on a boundary is a re-fetch, never a reuse, and the same reason
        makes the upper comparison strict: at exactly its TTL an entry has reached
        the end of the interval it was permitted, so it is fetched again.
        """
        if cached is None:
            return None
        age = self._now_micros() - cached.fetched_at
        if 0 <= age < ttl_s * _MICROSECONDS_PER_SECOND:
            return cached
        return None

    # -- retention, read only by rule 14 ---------------------------------- #

    @property
    def last_known_good_asset_pairs(self) -> RetainedValue | None:
        """The last successful ``AssetPairs``, kept past its TTL. Rule 14 only."""
        return self._retained.get("asset_pairs")

    @property
    def last_known_good_balances(self) -> RetainedValue | None:
        """The last successful ``Balance``, kept past its TTL. Rule 14 only."""
        return self._retained.get("balance")

    # -- plumbing --------------------------------------------------------- #

    def _now_micros(self) -> int:
        return to_micros(self._clock.now())

    def _next_nonce(self) -> int:
        """Strictly increasing, seeded from the injected clock.

        Kraken rejects a nonce that does not increase, and an injected clock may
        legitimately stand still — a replay clock does. Taking the maximum of the
        clock and the last nonce plus one keeps both properties.
        """
        candidate = self._now_micros()
        self._nonce = max(candidate, self._nonce + 1)
        return self._nonce

    def _retain(self, call: str, snapshot: PairRulesSnapshot | BalancesSnapshot) -> None:
        if call in RETAINED_CALLS:
            self._retained[call] = RetainedValue(value=snapshot, fetched_at=snapshot.fetched_at)

    async def _public(self, call: str, path: str, params: Mapping[str, str]) -> Any:
        await self._limiter.acquire()
        url = f"{self._base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        response = await self._transport.request(
            "GET", url, headers={"Accept": "application/json"}, content=None,
            timeout_s=self._timeout_s,
        )
        return self._unwrap(call, path, response)

    async def _private(self, call: str, path: str, form: Mapping[str, Any]) -> Any:
        credentials = self._credentials
        if credentials is None:
            raise KrakenUnavailableError(
                f"{call} needs API credentials and none are set. KRAKEN_API_KEY and "
                "KRAKEN_API_SECRET come from the environment only, and a missing key "
                "blocks rather than falling back."
            )
        await self._limiter.acquire()
        nonce = self._next_nonce()
        body = urlencode({"nonce": nonce, **form}).encode()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "API-Key": credentials.key,
            "API-Sign": sign_request(
                path=path, nonce=nonce, form=form, secret=credentials.secret
            ),
        }
        response = await self._transport.request(
            "POST", f"{self._base_url}{path}", headers=headers, content=body,
            timeout_s=self._timeout_s,
        )
        return self._unwrap(call, path, response)

    def _unwrap(self, call: str, path: str, response: HttpResponse) -> Any:
        """Envelope first, status second.

        Deliberately in that order. A 5xx carrying a proper envelope is still an
        application answer, and a 200 carrying a populated ``error`` array is still a
        failure — which is the whole reason the status code is not the test. The
        status is only consulted when the body turned out not to be an envelope at
        all, where it is the more informative thing to report.
        """
        try:
            return parse_envelope(response.body, call)
        except KrakenUnavailableError:
            if response.status_code >= 400:
                raise KrakenUnavailableError(
                    f"{call}: HTTP {response.status_code} from {path} with no Kraken envelope"
                ) from None
            raise

    # -- the Protocol ----------------------------------------------------- #

    async def asset_pairs(self) -> PairRulesSnapshot:
        """Pair rules, from the cache while it is inside ``cache_ttl_s.asset_pairs``.

        Past the TTL this re-fetches, and a re-fetch that fails **raises**. The
        expired entry is dropped before the network is touched, so there is no code
        path on which it can be returned — invariant 2's "a cache stale beyond its
        TTL counts as a failed fetch", made unreachable rather than merely unwritten.

        The retained last-known-good is untouched by any of that. It survives this
        expiry and this failure, because rule 14 needs it during exactly this outage.
        """
        ttl_s = self._require_ttl(self._asset_pairs_ttl_s, "kraken.cache_ttl_s.asset_pairs")
        cached = self._fresh(self._cached_asset_pairs, ttl_s)
        if cached is not None:
            return cached
        self._cached_asset_pairs = None
        result = await self._public("asset_pairs", ASSET_PAIRS_PATH, {})
        snapshot = map_asset_pairs(result, fetched_at=self._now_micros())
        # The asset-code map comes from this same body (Phase 8, F3) and is what `balance`
        # renames with. Kept on the client rather than recomputed there, because `Balance`'s
        # own response carries no second spelling to derive it from.
        self._asset_names = asset_code_names(result)
        self._retain("asset_pairs", snapshot)
        self._cached_asset_pairs = snapshot
        return snapshot

    async def trade_volume(self) -> FeeTierSnapshot:
        """The fee tier, from the cache while it is inside ``cache_ttl_s.trade_volume``.

        Cached, and deliberately **never retained**. Invariant 2: its only reader is
        the cost gate, and a fee nobody fetched invalidates that gate exactly as a
        spread nobody measured does. A TTL cache says "this is still good"; a
        last-known-good would say "use it anyway", which is the thing that must not
        exist for this value.
        """
        ttl_s = self._require_ttl(self._trade_volume_ttl_s, "kraken.cache_ttl_s.trade_volume")
        cached = self._fresh(self._cached_trade_volume, ttl_s)
        if cached is not None:
            return cached
        self._cached_trade_volume = None
        result = await self._private("trade_volume", TRADE_VOLUME_PATH, {})
        snapshot = map_trade_volume(result, fetched_at=self._now_micros())
        self._cached_trade_volume = snapshot
        return snapshot

    async def balance(self) -> BalancesSnapshot:
        """Balances, in the engines' own asset names where they are known.

        The rename uses the map built by the last successful ``asset_pairs`` (Phase 8, F3).
        Before the first one it is empty and the codes pass through as Kraken sent them —
        which is correct rather than convenient: engine 1 fetches pair rules on the same tick,
        and a pair whose quote has no matching balance is excluded with a reason rather than
        sized against a guess.
        """
        result = await self._private("balance", BALANCE_PATH, {})
        snapshot = map_balances(
            result, fetched_at=self._now_micros(), asset_names=self._asset_names
        )
        self._retain("balance", snapshot)
        return snapshot

    async def order_book(self, pair: str, depth: int = 10) -> OrderBookSnapshot:
        result = await self._public(
            "order_book", ORDER_BOOK_PATH, {"pair": pair, "count": str(depth)}
        )
        return map_order_book(
            result, pair=pair, depth=depth, fetched_at=self._now_micros()
        )

    # -- OrderClientProtocol: refused until Phase 8 ----------------------- #
    #
    # Spec 84 step 2. These four exist so that the *surface* is complete — the
    # engines, the paper broker and the live client all wear the same shape from
    # today — while the live implementation does not exist yet.
    #
    # They refuse before anything else happens. No limiter token, no nonce, no
    # signature, no request. The refusal is the first statement in each body and
    # there is no flag, config key or environment variable that turns it off,
    # because a live client that half-places orders is worse than one that places
    # none: an order Kraken accepted and this process did not record is exposure
    # nothing in the system knows about.

    async def add_order(self, request: OrderRequest) -> OrderAck:
        _refuse_order_call("add_order", subject=f"userref {request.userref}")

    async def cancel_order(self, userref: int) -> OrderState:
        _refuse_order_call("cancel_order", subject=f"userref {userref}")

    async def query_orders(self, userrefs: Sequence[int]) -> tuple[OrderState, ...]:
        _refuse_order_call("query_orders", subject=f"{len(tuple(userrefs))} userrefs")

    async def open_orders(self) -> tuple[OrderState, ...]:
        _refuse_order_call("open_orders", subject="the open order list")


def _refuse_order_call(method: str, *, subject: str) -> NoReturn:
    """Fail closed, naming the method and the phase that will implement it.

    :class:`KrakenUnavailableError` rather than ``NotImplementedError`` on
    purpose. Every caller in the system already catches the exchange-shaped types
    and blocks — invariant 3 — so a refusal that arrives as one is handled by code
    that exists, while a ``NotImplementedError`` would escape to the orchestrator
    and become an ``ERROR`` status whose reason says nothing about Phase 8.

    The method name is in the message because every fail-closed path in this
    package raises this one type, which makes ``pytest.raises(KrakenUnavailableError)``
    on its own unable to say which branch ran (``code-standards.md``). ``subject``
    is what was being asked for, so a log line says which order was refused.
    """
    raise KrakenUnavailableError(
        f"KrakenRestClient.{method} refuses {subject} and makes no request: placing, "
        "cancelling and querying orders against Kraken is Phase 8 work and is not "
        "built. A live client that refuses is fail-closed; one that half-works is "
        "not. In paper mode this call is answered by the paper broker in "
        "clients/paper/, which never delegates it here."
    )


def is_exchange_error(exc: BaseException) -> bool:
    """True for anything a caller should treat as "the exchange said no or nothing".

    Exists so a fail-closed caller has one predicate rather than an import list that
    drifts.
    """
    return isinstance(exc, KrakenError)
