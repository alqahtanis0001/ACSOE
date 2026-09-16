"""What engine 18 `execution` reads from `state`, and the row it publishes for engine 19.

The one piece of real arithmetic here is :func:`userref_for`, which is the whole of
invariant 8's idempotency: the system chooses the order's identifier **before** the order
exists, so it is the only identifier that survives a placement whose answer never came
back.
"""

from __future__ import annotations

import hashlib
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.kraken.contracts import USERREF_MAX

__all__ = [
    "ORDERS_FIELD",
    "PLACED_FIELD",
    "REASON_ENTRY_ALREADY_PLACED",
    "REASON_ENTRY_NOT_A_LIMIT",
    "REASON_ENTRY_PLACED",
    "REASON_ENTRY_RECOVERED",
    "REASON_ENTRY_UNRECORDED",
    "REASON_POST_ONLY_WOULD_CROSS",
    "STATE_KEY",
    "USERREF_FIELD",
    "ExecutionState",
    "to_userref",
    "userref_for",
]

#: `state["execution"]`. Engine 21 reads this key on the same tick, before engine 19 has
#: written anything, so that a `close_all` arriving on the tick of a placement does not
#: report every entry cancelled while one is resting.
STATE_KEY: Final = "execution"

ORDERS_FIELD: Final = "orders"
PLACED_FIELD: Final = "placed"
USERREF_FIELD: Final = "userref"
PAIR_FIELD: Final = "pair"

# --------------------------------------------------------------------------- #
# What it reads
# --------------------------------------------------------------------------- #

#: Engine 16. The order intent — one typed record rather than five engines' keys.
DECISION_KEY: Final = "decision"
INTENT_FIELD: Final = "intent"

#: Engine 3. The best bid, which is where every Phase 6 entry rests.
MARKET_SENSOR_KEY: Final = "market_sensor"
QUOTES_FIELD: Final = "quotes"
QUOTE_BID_FIELD: Final = "bid"

#: Engine 1. `pair_decimals`, the price grid the limit is rounded onto.
EXCHANGE_KEY: Final = "exchange"
PAIR_RULES_KEY: Final = "pair_rules"
PAIR_RULES_PAIRS_KEY: Final = "pairs"
PAIR_DECIMALS_FIELD: Final = "pair_decimals"

# --------------------------------------------------------------------------- #
# Reason codes
# --------------------------------------------------------------------------- #

#: A post-only limit buy is now resting on the book. Not a refusal — this engine is not
#: a gate — but the `reason_code` field is how every engine says what it did, and a
#: placement with no code would be the one outcome the console cannot narrate.
REASON_ENTRY_PLACED: Final = "entry_placed"

#: This `userref` already exists, so nothing was placed. Invariant 8, and the ordinary
#: case on a re-run of one tick rather than an error.
REASON_ENTRY_ALREADY_PLACED: Final = "entry_already_placed"

#: The exchange refused the placement because a post-only order would have crossed. The
#: candidate is abandoned for this tick; it is never re-placed at a worse price, which
#: would be chasing.
REASON_POST_ONLY_WOULD_CROSS: Final = "post_only_would_cross"


def to_userref(value: int) -> int:
    """Map any non-negative integer onto `[1, USERREF_MAX - 1]`.

    Split out from :func:`userref_for` **so that the range guarantee can be tested at
    its edges**, which is the only place it can fail. A test over the whole function
    can only sample the digest space, and dropping the `1 +` changes the answer for
    exactly one input in 2^31 — a mutation no sampling test will ever find. Here the
    boundary is reachable: `to_userref(0)` is 1 or it is not.

    The entropy is the digest's job; this function is only the range.
    """
    if value < 0:
        raise ValueError(f"{value} is negative; a digest is not")
    return 1 + value % (USERREF_MAX - 1)


def userref_for(pair: str, closed_bar_ts: int) -> int:
    """The order's identifier, derived from the pair and the bar and nothing else.

    **Deterministic across processes**, which rules out `hash()`: Python salts string
    hashing per process, so a restart between placing and checking would compute a
    different `userref` for the same candidate and place a second order on it. That is
    invariant 8's exact failure, arriving through a builtin that looks pure.

    Derived from `(pair, closed_bar_ts)` because those two are what make a candidate one
    candidate. One bar can yield at most one entry per pair — invariant 6's per-pair
    clause, which engine 11 enforces — so the pair and the bar identify the order before
    it exists, which is the property the whole idempotency check rests on.

    **Positive, in `[1, USERREF_MAX - 1]`**, although Kraken's range is signed 32-bit and
    a negative value is legal. Zero is excluded because it is the value a missing integer
    field decays to in too many places to be a safe identifier, and negatives are excluded
    because every `userref` in this system's fixtures, logs and rejection rows reads as a
    positive number and one stray minus sign in an operator's query is a silent miss.
    Narrowing the space from 2^32 to 2^31 does not change the collision argument below.

    **Collisions are a defect, not a retry**, and the caller treats them that way: a
    31-bit digest over a small daily candidate set collides with vanishing probability,
    and if one ever happens the order would be placed on the wrong pair. So engine 18
    compares the pair on the row it finds and raises rather than assuming.
    """
    digest = hashlib.blake2b(f"{pair}|{closed_bar_ts}".encode(), digest_size=8).digest()
    return to_userref(int.from_bytes(digest, "big"))


class ExecutionState(BaseModel):
    """What engine 18 publishes into `state["execution"]`.

    `orders` carries the row engine 19 writes — at most one, because one tick places at
    most one entry. It is a list rather than a single row so that engine 19 and engine 21
    read one shape here and in `state["position_manager"]`, which publishes several.

    `placed` is **this tick's** placement and nothing else. An order found already
    recorded publishes `placed: False` and still publishes its row, because engine 21
    needs to see it whether or not this tick is what put it there.

    `orders` is empty in exactly two cases, both of them an exchange answer this engine
    will not turn into a record: an entry the exchange reports with no `limit_price`,
    and an order it reports with no `opened_at`. See `REASON_ENTRY_NOT_A_LIMIT` and
    `REASON_ENTRY_UNRECORDED` below. Neither raises.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pair: str
    userref: int
    placed: bool
    orders: tuple[dict[str, Any], ...] = ()
    reason_code: str | None = None

    def to_state(self) -> dict[str, Any]:
        return {
            PAIR_FIELD: self.pair,
            USERREF_FIELD: self.userref,
            PLACED_FIELD: self.placed,
            ORDERS_FIELD: [dict(row) for row in self.orders],
            "reason_code": self.reason_code,
        }


#: The order is resting at the exchange under this `userref` and the store has never
#: heard of it: engine 18 placed it and the process died before engine 19 recorded it.
#:
#: Distinct from `entry_already_placed` because the *provenance* is different, not the
#: consequence: there the store is the source of everything, here the exchange is. Both
#: publish a row and neither places a duplicate.
#:
#: **Narrowed on 2026-09-16.** It used to cover every order found this way, because
#: `OrderState` carried no `qty`, no `limit_price` and no placement time and none of
#: the three could be had without fabricating it. A's spec 84 amendment added all
#: three, so the ordinary case now publishes a row under `REASON_ENTRY_RECOVERED` and
#: this code is left with the one thing the amendment does not fix: **the exchange
#: reported no `opentm`**, so the order cannot be dated.
#:
#: A clock reading substituted here is a time that never happened, written into the
#: column research and the console read as a placement time — and there is nowhere to
#: record the substitution either, because `fallbacks_used` is a `trades` column and
#: `orders` has none. So: no row, the `userref` published, the candidate abandoned for
#: the tick, and **no raise** (see `REASON_ENTRY_NOT_A_LIMIT` for why not).
REASON_ENTRY_UNRECORDED: Final = "entry_unrecorded_at_exchange"

#: The order is at the exchange, the store has never heard of it, and it **is** fully
#: describable: `qty`, `limit_price` and `opened_at` all came back. Engine 18 places no
#: duplicate and publishes the row, so engine 21 can see the order and cancel it in the
#: ordinary unfilled window.
#:
#: Distinct from `entry_already_placed` by *provenance* rather than by consequence —
#: there the store is the source, here the exchange is — and worth its own code because
#: the two say different things to an operator: one is a re-run of a tick, the other is
#: a process that died between placing and recording.
REASON_ENTRY_RECOVERED: Final = "entry_recovered_from_exchange"

#: The order at the exchange under this entry's `userref` carries **no limit price**,
#: and invariant 8 makes every entry a post-only buy limit. That is the exchange
#: contradicting the placement, so no row is written: a limit order with a null price
#: in `orders` is a row engine 21 cannot reason about.
#:
#: `OrderState` deliberately carries no `order_type` — the presence of a limit price is
#: a total discriminator and a second field holding the same bit is one more thing that
#: can disagree — so the model cannot refuse this and the consumer that knows what it
#: asked for must. Lead ruling, 2026-09-16.
#:
#: **It is a reason code and not a raise, and the reason is the circuit breaker.**
#: Contract rule 7 would turn a raise into `ERROR`, engine 19 writes
#: `block_records.status = 'ERROR'`, and engine 17 `safety` counts those in the trailing
#: hour against `safety.max_errors_in_window` and freezes the account. An exchange
#: contradicting itself about one order is not the system malfunctioning and must not
#: spend the breaker's budget. Lead ruling, 2026-09-16.
REASON_ENTRY_NOT_A_LIMIT: Final = "entry_at_exchange_is_not_a_limit"
