"""What engine 7 `scout` reads out of `state` and what it writes back into it.

**The universe is computed, never configured.** A Locked Decision: *"Tradable universe
computed per tick from `ordermin`, `costmin`, tick size, live spread and balance. No
account-size thresholds."* There is no pair list in this module, no config key holding one,
and no comparison of a balance against a literal. Every number the filter uses arrives from
`AssetPairs`, the live book, the account, or a configured *ratio* — and a ratio is a policy,
not a pair.

**Every exclusion is counted and named.** The console's most-viewed screen state is the one
where nothing qualified — *"Scanned 412 pairs. 38 entered the tradable universe."* — and it
renders from :class:`ScoutUniverse`'s tally rather than from a log line. A pair excluded
without a code would vanish from that arithmetic, so the codes are exhaustive by
construction: `scanned` equals `entered` plus the sum of the tally, and a test asserts it.

## Money crosses `state` as an exact decimal string

The same rule engines 10 and 11 carry, restated here rather than imported because an engine
never imports another engine. `EngineResult.data` refuses a `Decimal` and *accepts* a
`float`, which is the dangerous half — so every money field below is :data:`Money`, the
`Decimal` that raises on a float rather than coercing it.

## The two crypto-quoted codes, and why there are two

Invariant 7 disables crypto-quoted pairs by default, and defines one as a pair whose quote
is "BTC, ETH, or **any non-stable asset**". That sentence needs a set of stable assets.
`AssetPairs` carries no asset class, so it is not derivable at runtime; the set is
`trading.stable_quote_currencies`, supplied by the operator.

**When that set is absent, a pair whose quote is not provably stable is excluded** — the
lead's ruling of 2026-09-10. `scout` is the sole authority on the tradable universe, so its
errors run in one direction: over-including risks a trade the operator explicitly disabled,
while under-including costs an opportunity that recurs on the next tick and every tick
after. (Engine 2 `market_data_recorder` gets the *opposite* answer for the same question,
because for a recorder the irreversible error is losing order-book history that cannot be
recovered. Fail-closed is not a direction; it is a question about which error is
irreversible.)

That is why :data:`REASON_QUOTE_NOT_PROVABLY_STABLE` exists beside
:data:`REASON_CRYPTO_QUOTED` rather than sharing it. A universe that shrank because the
operator disabled crypto-quoted pairs and a universe that shrank because nobody supplied
the stable set look identical from the outside, and the second is a configuration fault
somebody needs to fix.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_DOWN, Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import Money

__all__ = [
    "EXCHANGE_BALANCES_KEY",
    "EXCHANGE_KEY",
    "EXCHANGE_PAIR_RULES_KEY",
    "EXCLUSION_REASONS",
    "MARKET_SENSOR_KEY",
    "MARKET_SENSOR_QUOTES_KEY",
    "PAIRS_FIELD",
    "PAIR_BASE_FIELD",
    "PAIR_COSTMIN_FIELD",
    "PAIR_LOT_DECIMALS_FIELD",
    "PAIR_ORDERMIN_FIELD",
    "PAIR_QUOTE_FIELD",
    "PAIR_RULES_PAIRS_KEY",
    "PAIR_TICK_SIZE_FIELD",
    "QUOTE_ASK_FIELD",
    "QUOTE_BID_FIELD",
    "REASON_BELOW_COSTMIN",
    "REASON_BELOW_ORDERMIN",
    "REASON_CRYPTO_QUOTED",
    "REASON_INPUTS_UNAVAILABLE",
    "REASON_INSUFFICIENT_QUOTE_BALANCE",
    "REASON_NO_FX_RATE",
    "REASON_NO_LIVE_QUOTE",
    "REASON_NO_QUOTE_BALANCE",
    "REASON_PAIR_RULES_MISSING",
    "REASON_QUOTE_NOT_PROVABLY_STABLE",
    "REASON_TICK_GRID_TOO_COARSE",
    "SCOUT_KEY",
    "PairFacts",
    "ScoutUniverse",
    "round_down_to_lot",
]

# --------------------------------------------------------------------------- #
# State paths
# --------------------------------------------------------------------------- #

#: The one key this engine writes into `state`. Contract rule 2.
SCOUT_KEY: Final = "scout"

#: Where the universe itself lives inside that payload: `state["scout"]["pairs"]`.
#:
#: A named constant rather than a bare string, because it crosses an ownership boundary in
#: two directions — `scripts/verify.py`'s `universe_varies_with_balance` reads it to find
#: the universe it judges, and engines 10 and 11 will read the candidate spec 44 chooses
#: from it. A consumer that hardcoded `"pairs"` would go quiet rather than red the day it
#: moved, which is the failure the Phase 3 audit spent a whole phase on.
#:
#: **No `UNIVERSE_FIELD` alias, and that is settled rather than pending.** C's
#: `universe_varies_with_balance` proposed that name in its PENDING line before engine 7
#: existed; rather than have either side retype the other's string, C's criterion now
#: *asks* :class:`ScoutUniverse` — it serialises a probe pair through `to_state_data()` and
#: takes the key whose value contains it. So a rename here follows automatically on that
#: side, with no literal anywhere to drift, which is a better answer than the constant it
#: replaced and better than the alias. Settled 2026-09-10.
PAIRS_FIELD: Final = "pairs"

#: Engine 1 `exchange` (A). The account engine: balances, fee tier, pair rules.
EXCHANGE_KEY: Final = "exchange"

#: The whole `AssetPairs` snapshot, `{fetched_at, pairs: {...}}`, and the per-pair mapping
#: inside it. Two constants and not a dotted path, so a null `pair_rules` — the failed
#: fetch — reports as the missing snapshot it is rather than as an unknown pair. The same
#: shape engine 11 reads, and the same correction: the assumed path was one level shallower
#: and blocked every live tick.
EXCHANGE_PAIR_RULES_KEY: Final = "pair_rules"
PAIR_RULES_PAIRS_KEY: Final = "pairs"

#: A flat `{currency: decimal string}` map. Invariant 7 makes the *quote currency's*
#: balance part of tradability, so this is read per pair rather than in aggregate.
EXCHANGE_BALANCES_KEY: Final = "balances"

#: Engine 3 `market_sensor` (A). The market-data engine, and the publisher of the live book.
MARKET_SENSOR_KEY: Final = "market_sensor"
MARKET_SENSOR_QUOTES_KEY: Final = "quotes"

#: The two sides of the book. The ask prices the entry and the bid values the position, the
#: same way round as engine 11 — the lead's ruling of 2026-09-10, and the reason the two
#: engines can be cross-checked at all.
QUOTE_ASK_FIELD: Final = "ask"
QUOTE_BID_FIELD: Final = "bid"

#: `AssetPairs` fields, per pair. **Never a constant and never a config key.** `AGENTS.md`:
#: any remembered order minimum, tick size or precision is stale.
PAIR_ORDERMIN_FIELD: Final = "ordermin"
PAIR_COSTMIN_FIELD: Final = "costmin"
PAIR_TICK_SIZE_FIELD: Final = "tick_size"
PAIR_LOT_DECIMALS_FIELD: Final = "lot_decimals"
PAIR_QUOTE_FIELD: Final = "quote"
PAIR_BASE_FIELD: Final = "base"

# --------------------------------------------------------------------------- #
# Exclusion reason codes
# --------------------------------------------------------------------------- #
#
# Every one of these is a key in `console/format.py`'s `REASON_PROSE`, which is C's mapping
# from a stored code to the sentence an operator reads. A code absent from that table
# renders "No reason was recorded." — silently, with no error anywhere. C's spec 46 test
# **enumerates** these out of this module rather than hand-listing them, so adding a code
# here is what obliges the prose, and neither side can drift without the other noticing.

#: The pair has a quote but no rules — `AssetPairs` does not list it, or the fetch failed.
#: Invariant 2 gives pair rules no fallback in any mode: a wrong `ordermin` produces invalid
#: orders, so an unknown one excludes the pair.
REASON_PAIR_RULES_MISSING: Final = "pair_rules_missing"

#: No live top-of-book for this pair. **Never read as a zero spread** — invariant 2 says an
#: assumed spread invalidates the cost gate, and zero is the most optimistic value the field
#: can take.
REASON_NO_LIVE_QUOTE: Final = "no_live_quote"

#: The quote is a non-stable asset and `trading.allow_crypto_quoted` is false. Invariant 7:
#: profit denominated in a volatile asset is a second directional bet the system did not
#: choose to make.
REASON_CRYPTO_QUOTED: Final = "crypto_quoted"

#: `trading.stable_quote_currencies` is absent, so this quote cannot be *shown* to be
#: stable. Distinct from :data:`REASON_CRYPTO_QUOTED` on the lead's ruling — see the module
#: docstring. A universe that shrank for want of a config key is a fault somebody must fix,
#: and it must not be indistinguishable from one that shrank by policy.
REASON_QUOTE_NOT_PROVABLY_STABLE: Final = "quote_not_provably_stable"

#: The account holds nothing spendable in this pair's quote currency. Invariant 7: a pair is
#: only executable if the account holds spendable balance in that quote currency.
REASON_NO_QUOTE_BALANCE: Final = "no_quote_balance"

#: Affordability cannot be computed: the position's cost is in
#: `trading.base_reporting_currency` and the balance is in the pair's quote currency, and
#: **nothing in this system publishes an exchange rate between them.**
#:
#: Invariant 7 says PnL and equity are converted "at the trade timestamp", so the intent
#: exists and only the mechanism is missing. **Ruled by the operator on 2026-09-10:** a pair
#: whose affordability cannot be computed is excluded, under a code that says so.
#:
#: Excluding claims nothing about the world — it is the same shape as
#: :data:`REASON_QUOTE_NOT_PROVABLY_STABLE`, and different in kind from a heuristic that
#: would *assert* a rate and be wrong. Over-including is `scout`'s irreversible error;
#: under-including costs an opportunity that recurs on the next tick.
#:
#: Shared with engine 11, which carries the identical comparison and now the identical
#: refusal. Costs nothing today: no pair reaches it while `allow_crypto_quoted` is false and
#: every fixture quote is the reporting currency. It is here so the hole is closed before
#: that flag is ever turned on.
REASON_NO_FX_RATE: Final = "no_fx_rate"

#: The account holds *some* of the quote currency, but less than the position this equity
#: would size. Invariant 6: never allocate cash the account does not hold. **Not an
#: account-size threshold** — both sides of the comparison are computed, and neither is a
#: literal. Shared with engine 11, which rejects a live candidate on the same arithmetic.
REASON_INSUFFICIENT_QUOTE_BALANCE: Final = "insufficient_quote_balance"

#: The position this equity would size is below the pair's minimum order size, after
#: rounding down to `lot_decimals`. Shared with engine 11 deliberately: it is the same
#: arithmetic and it means the same thing, so it should read the same on the console.
REASON_BELOW_ORDERMIN: Final = "below_ordermin"

#: The same position is worth less than the pair's minimum order value, at the bid.
REASON_BELOW_COSTMIN: Final = "below_costmin"

#: The barriers are not expressible on this pair's tick grid: one `tick_size` is as large as
#: the stop distance, so a stop rounds onto the entry price itself and the position would
#: have no stop at all. **This is what `tick_size` is doing in the Locked Decision's list**,
#: and excluding is the only fail-closed answer. Arithmetic over the pair's own rules, not a
#: threshold.
REASON_TICK_GRID_TOO_COARSE: Final = "barriers_below_tick_size"

#: Fail-closed: an input this gate needs was absent or unusable, so no universe could be
#: computed at all. Invariant 3 — a gate that cannot reach its data blocks. Not an exclusion
#: reason and deliberately absent from :data:`EXCLUSION_REASONS`: it is a statement about
#: the tick rather than about a pair, and counting it in the tally would put it in an
#: arithmetic it does not belong to.
REASON_INPUTS_UNAVAILABLE: Final = "scout_inputs_unavailable"

#: Every reason a *pair* can be excluded, in the order the filter applies them.
#:
#: The order is part of the behaviour rather than an implementation detail: a pair is
#: attributed to the **first** rule it fails, so `scanned == entered + sum(tally)` holds
#: exactly. Changing the order changes which code an excluded pair is counted under, which
#: changes what the console's empty state says.
EXCLUSION_REASONS: Final[tuple[str, ...]] = (
    REASON_PAIR_RULES_MISSING,
    REASON_NO_LIVE_QUOTE,
    REASON_CRYPTO_QUOTED,
    REASON_QUOTE_NOT_PROVABLY_STABLE,
    REASON_NO_QUOTE_BALANCE,
    REASON_TICK_GRID_TOO_COARSE,
    REASON_NO_FX_RATE,
    REASON_INSUFFICIENT_QUOTE_BALANCE,
    REASON_BELOW_ORDERMIN,
    REASON_BELOW_COSTMIN,
)


# --------------------------------------------------------------------------- #
# Arithmetic
# --------------------------------------------------------------------------- #


def round_down_to_lot(quantity: Decimal, lot_decimals: int) -> Decimal:
    """Round a quantity **down** to the exchange's accepted precision.

    Duplicated from `engines/risk/contracts.py` rather than imported: contract rule 3 says
    an engine never imports another engine, and the duplication is the point of the
    cross-check test named in both READMEs. Down, never to-nearest — `ROUND_HALF_UP` on a
    quantity one ulp below `ordermin` would round it *to* `ordermin` and admit a pair the
    account cannot actually trade.
    """
    if lot_decimals < 0:
        raise ValueError(f"lot_decimals must not be negative, got {lot_decimals}")
    return quantity.quantize(Decimal(1).scaleb(-lot_decimals), rounding=ROUND_DOWN)


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #


class PairFacts(BaseModel):
    """One pair's rules and live book, parsed and validated.

    `extra="ignore"` because these are read out of much larger published payloads;
    `frozen=True` because an engine must not mutate what another engine published.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    pair: str
    base: str
    quote: str
    ordermin: Money
    costmin: Money
    tick_size: Money
    lot_decimals: int
    bid: Money
    ask: Money


class ScoutUniverse(BaseModel):
    """What this engine publishes into `state["scout"]`.

    `pairs` is the universe — every pair the account could legitimately trade *right now*,
    recomputed from scratch every tick. It is a sorted tuple rather than a set so the
    payload is deterministic and JSON-safe; the ordering here carries no ranking, which is
    spec 44's subject and is deliberately absent from this one.

    **The counts are not decoration.** `scanned`, `entered` and `excluded` are what the
    console's empty state renders, and they are required to add up.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pairs: tuple[str, ...] = ()
    scanned: int = 0
    excluded: Mapping[str, int] = {}
    equity: Money | None = None

    @property
    def entered(self) -> int:
        return len(self.pairs)

    @property
    def counts_add_up(self) -> bool:
        """`scanned == entered + sum(excluded)`. Asserted by a test, not merely hoped for.

        A pair excluded without a code would vanish from this arithmetic, and the console's
        "Scanned 412 pairs. 38 entered" would silently stop being true.
        """
        return self.scanned == self.entered + sum(self.excluded.values())

    def to_state_data(self) -> dict[str, Any]:
        """The JSON-serialisable form the orchestrator puts in `state["scout"]`."""
        return {
            PAIRS_FIELD: list(self.pairs),
            "scanned": self.scanned,
            "entered": self.entered,
            "excluded": dict(self.excluded),
            "equity": None if self.equity is None else format(self.equity, "f"),
        }
