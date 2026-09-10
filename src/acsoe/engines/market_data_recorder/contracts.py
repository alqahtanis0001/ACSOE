"""What engine 2 `market_data_recorder` publishes into ``state``, and the scope it
subscribes to.

Counters, not data. The recording itself goes to `data/raw/`; what reaches ``state``
is how much of it arrived this tick and what was lost, so the console and the log can
see the feed's health without anything having to re-read a gigabyte.

Every field here is a count of something that **would otherwise be invisible**. A
recorder that quietly wrote nothing looks exactly like a quiet market, and that is the
failure the whole recording exists to make impossible.

**The subscription scope is not the tradable universe.** :func:`subscription_scope`
answers one question: which pairs is it worth asking the socket for, so that a book
the account could not trade in any currency is not carried across the network and
into the archive. It is deliberately cheap and deliberately non-economic — no
``ordermin``, no ``costmin``, no spread, no equity, no price. Engine 7 `scout` is the
sole authority on what may be traded, it recomputes that every tick, and a pair inside
this scope is routinely outside that universe. Two different questions. Do not let the
second name leak into this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "BOOK_DEPTH",
    "EXCHANGE_STATE_KEY",
    "STATE_KEY",
    "RecorderState",
    "subscription_scope",
]

#: How many book levels the stream is asked for, per pair.
#:
#: **A parameter of the recorder, not a config key**, and spec 39 says so in as many
#: words. It is 10 because that is ``DEFAULT_DEPTH`` in ``scripts/record.py``, and
#: engine 2 supersedes that script: a depth that disagreed with it would split the
#: archive into two datasets at the moment the daemon took over, which invariant 11
#: makes impossible to repair afterwards. Changing it is a decision about the
#: recording, so it belongs beside the recording and not in an operator's YAML.
BOOK_DEPTH: Final = 10

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "market_data_recorder"

#: The key engine 1 writes, which this engine reads to derive its subscription scope.
#:
#: **Written out rather than imported from ``engines/exchange/contracts.py``.**
#: Contract rule 3: an engine never imports another engine; if you need something
#: from engine N you read it from ``state``. That rule costs a duplicated string
#: here, and the cost is paid back by ``tests/engines/test_market_data_recorder.py``,
#: which imports both constants and asserts they are equal. A test may reach across
#: the boundary that production code may not, which is how a deliberate duplicate is
#: kept from drifting without weakening the rule.
EXCHANGE_STATE_KEY: Final = "exchange"


class RecorderState(BaseModel):
    """The whole of ``state["market_data_recorder"]``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stream_available: bool
    """False when the injected client exposes no market stream at all.

    Not an error and not a block. A client double without a stream is a legitimate
    thing for another agent to hand this engine — C's fake Kraken client is exactly
    that — and an engine that raised on it would make the orchestrator untestable.
    """

    connected: bool
    """Whether the stream believes it has a live socket right now."""

    frames_recorded: int
    """Raw frames appended to the archive this tick."""

    gaps_recorded: int
    """Breaks written into the archive this tick, each with its own cause."""

    dropped_frames: int
    """Cumulative frames the stream lost to a full buffer.

    Cumulative rather than per-tick on purpose: a buffer overflow is a fault about the
    process, not about the minute it happened in, and zeroing it every tick would make
    it almost impossible to notice.
    """

    unparsed_frames: int
    """Cumulative frames recorded verbatim that yielded neither a trade nor a quote.

    The cost of the lenient parse. A frame nobody understood is still in the archive —
    which is the half that cannot be recovered — but a rising number here means the
    field names in ``clients/kraken/ws.py`` no longer match what Kraken sends.
    """

    subscription: tuple[str, ...] = ()
    """The pairs the stream is subscribed to as of the end of this tick.

    Published so that "the subscription changed" and "the subscription was left
    alone" are both facts a test and an operator can read, rather than behaviour that
    has to be inferred from what turned up in the archive. Sorted, so two ticks with
    the same scope compare equal.
    """

    subscription_derived: bool = False
    """True when this tick recomputed the scope; False when it left it as it was.

    False is the honest answer on a tick where ``pair_rules`` or ``balances`` did not
    arrive. The scope is not recomputed then and nothing is unsubscribed — see
    :func:`subscription_scope`.
    """

    crypto_quoted_excluded: bool = False
    """Whether the crypto-quoted exclusion was actually applied this tick.

    Not the same thing as ``trading.allow_crypto_quoted`` being false. The exclusion
    also needs to know *which* quote currencies are crypto, which comes from
    ``trading.stable_quote_currencies``; while that key is absent the exclusion cannot
    be applied and this says so. Published rather than logged because a filter that
    silently did not run is indistinguishable from one that ran and excluded nothing.
    """

    def to_state(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.model_dump(mode="json")
        return payload


def _positive(amount: Any) -> bool:
    """True when ``amount`` parses as a strictly positive decimal.

    Balances cross ``state`` as exact decimal strings. Anything that will not parse
    is treated as *not held* rather than as an error: the scope is not a gate, and a
    malformed balance must not be able to take the guard chain down on a tick where
    the only consequence is which books get recorded.
    """
    try:
        return Decimal(str(amount)) > 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def subscription_scope(
    *,
    pair_rules: Mapping[str, Any] | None,
    balances: Mapping[str, Any] | None,
    allow_crypto_quoted: bool,
    stable_quotes: frozenset[str] | None,
) -> tuple[str, ...] | None:
    """The pairs worth subscribing to, or ``None`` for "no basis to decide".

    Derived, never configured. Reads ``state["exchange"]`` as engine 1 publishes it
    and nothing else — there is no pair list, no default, and no config key holding
    one, because the universe is computed per tick and a typed list of three symbols
    would contradict that.

    A pair is in scope when:

    * it has rules in ``pair_rules["pairs"]``;
    * the account holds a **strictly positive** balance in its ``quote`` currency;
    * and it is not crypto-quoted, unless ``allow_crypto_quoted``.

    ``None`` is returned — and is not the same as ``()`` — when ``pair_rules`` or
    ``balances`` is absent because the fetch failed. **The existing subscription then
    stays exactly as it is.** An empty tuple would mean "subscribe to nothing", and
    dropping the stream on a transient private-call failure would destroy order-book
    history that cannot be recovered afterwards, which is the one thing this system
    may never do. The two cases are different answers and are different values.

    ``stable_quotes`` is ``None`` while ``trading.stable_quote_currencies`` has not
    landed. The crypto-quoted exclusion is then **not applied**, and the caller
    publishes that it was not. That is a deliberate choice and it is recorded in the
    build log: the two fail-closed directions point opposite ways here, because
    excluding everything unprovable would subscribe to nothing and lose the
    irrecoverable half, while including too much costs bandwidth and cannot cause a
    trade — engine 7 enforces invariant 7 on the universe, which is where a trade is
    actually decided.
    """
    if pair_rules is None or balances is None:
        return None

    rules = pair_rules.get("pairs")
    if not isinstance(rules, Mapping):
        return None

    held = {code for code, amount in balances.items() if _positive(amount)}
    exclude_crypto = not allow_crypto_quoted and stable_quotes is not None

    scope: list[str] = []
    for name, rule in rules.items():
        if not isinstance(rule, Mapping):
            continue
        quote = rule.get("quote")
        if not isinstance(quote, str) or quote not in held:
            continue
        if exclude_crypto and stable_quotes is not None and quote not in stable_quotes:
            continue
        scope.append(str(name))
    # Sorted so the scope is a value rather than a traversal order: two ticks that
    # decided the same thing must compare equal, and a mapping's iteration order is
    # not something to hang "did the subscription change" on.
    return tuple(sorted(scope))
