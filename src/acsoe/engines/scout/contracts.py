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

import math
from collections.abc import Iterable, Mapping
from decimal import ROUND_DOWN, Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from acsoe.clients.store.contracts import Money

__all__ = [
    "CANDIDATE_FIELD",
    "EXCHANGE_BALANCES_KEY",
    "EXCHANGE_KEY",
    "EXCHANGE_PAIR_RULES_KEY",
    "EXCLUSION_REASONS",
    "FEATURE_KEY",
    "FEATURE_NAMES_KEY",
    "FEATURE_PAIRS_KEY",
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
    "RANKED_FIELD",
    "RANK_BY_EXPECTED_MOVE",
    "RANK_DESCENDING_FIELD",
    "RANK_FEATURE_FIELD",
    "RANK_RUN_IDS_FIELD",
    "RANK_SKIPPED_FIELD",
    "REASON_BELOW_COSTMIN",
    "REASON_BELOW_ORDERMIN",
    "REASON_CRYPTO_QUOTED",
    "REASON_EMPTY_UNIVERSE",
    "REASON_INPUTS_UNAVAILABLE",
    "REASON_INSUFFICIENT_QUOTE_BALANCE",
    "REASON_NO_FX_RATE",
    "REASON_NO_LIVE_QUOTE",
    "REASON_NO_QUOTE_BALANCE",
    "REASON_NO_RANKABLE_PAIR",
    "REASON_PAIR_RULES_MISSING",
    "REASON_QUOTE_NOT_PROVABLY_STABLE",
    "REASON_TICK_GRID_TOO_COARSE",
    "SCOUT_KEY",
    "PairFacts",
    "ScoutUniverse",
    "rank_universe",
    "round_down_to_lot",
    "select_candidate",
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

#: Where the single candidate lives: `state["scout"]["pair"]`.
#:
#: **Fixed by the cross-chain key table in `engine-contracts.md` and not renameable.**
#: Engines 10 `cost` and 11 `risk` read it directly — `cost/contracts.py` names the same
#: path in its own `CANDIDATE_PAIR_PATH` — so a rename here is a silent block on every live
#: tick in two other engines, which is precisely the failure the Phase 3 audit was about.
#:
#: **Absent, never null, when there is no candidate.** A `pair` key holding `None` is a key
#: a consumer can read and a `_require` can mistake for a value; an absent key cannot be.
#: The same shape `RiskSizing` uses for `qty` on a rejection, and for the same reason.
CANDIDATE_FIELD: Final = "pair"

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

#: Engine 5 `feature` (C). The feature vector for every pair engine 3 published candles
#: for, keyed by pair inside `pairs`, floats with `null` where a lookback was unfilled.
#:
#: **Read only by the ranking, and only when a feature is configured.** It is fixed by the
#: cross-chain key table in `engine-contracts.md` — `state["feature"]["pairs"][pair]`,
#: written by C, read here — and it is present only on a tick where a decision bar closed,
#: which is the only tick engine 7 runs on anyway: engine 5 is first in the opportunity
#: chain and returns `PASS` on every other tick, stopping the chain before this engine.
FEATURE_KEY: Final = "feature"
FEATURE_PAIRS_KEY: Final = "pairs"

#: `modelling.features.FEATURE_NAMES` in order, as engine 5 republishes it. A required
#: field of C's `FeatureState`, so it is present whenever engine 5 published at all.
#:
#: **Read to refuse a configured feature nobody computes.** Without it a misspelt
#: `scout.rank_feature` finds no value for any pair, the no-value rule orders them all
#: alphabetically among themselves, and the engine publishes the misspelt name beside a
#: ranking it never performed. The per-pair question ("does this pair have a value?") and
#: the whole-universe question ("does this feature exist?") are different, and one answer
#: cannot serve both.
FEATURE_NAMES_KEY: Final = "feature_names"

#: What this engine publishes about the ranking it performed, inside `state["scout"]`.
#: **Null is the answer rather than the absence of one** — it says the ordering was
#: alphabetical because no feature is configured, which the console and the spec 75
#: ranking study need to tell apart from a feature that rated every pair equally. That is
#: the opposite of :data:`CANDIDATE_FIELD`, which is absent rather than null, and the
#: difference is which fact the reader is entitled to draw from it.
RANK_FEATURE_FIELD: Final = "rank_feature"
RANK_DESCENDING_FIELD: Final = "rank_descending"

#: The `scout.rank_feature` value that orders the universe by engine 8's expected move.
#: Ruled by the operator on 2026-09-19 (R1, spec 144). **It is not a feature name.** It
#: names the predictor's own output, which engine 7 computes for every universe pair
#: through `modelling/ranking.py`, the arithmetic engines 8 and 13 use. So it is matched
#: before the engine checks the name against engine 5's `feature_names`, and it never
#: reaches that check.
RANK_BY_EXPECTED_MOVE: Final = "expected_move"

#: With the expected-move ranking, the pairs that were ranked, in order, each with its
#: expected move as an exact decimal string. This is the console's view of the ranking, so
#: it is published in full. A pair the ranking skipped is not in it. Empty under any other
#: ordering.
RANKED_FIELD: Final = "ranked"

#: With the expected-move ranking, how many universe pairs the ranking skipped, by the
#: shared function's skip code (R11: an incomplete vector, or an anomaly score or DI the
#: gates would refuse). **Not an exclusion.** A skipped pair stays in `pairs`, and
#: `scanned == entered + sum(excluded)` is untouched. A skipped pair is tradable. The
#: ranking only declined to examine it.
RANK_SKIPPED_FIELD: Final = "rank_skipped"

#: The model runs the ranking scored with, as `{"prediction": ..., "anomaly": ...}`. `None`
#: when no model ranked the universe.
RANK_RUN_IDS_FIELD: Final = "rank_run_ids"

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

#: The universe was computed and is empty: every pair was excluded, so there is no candidate
#: this tick. **This is a `PASS`, not a `BLOCK`, and not a failure of any kind.**
#:
#: Nothing qualifying is this system's honest default state on a small account — the console
#: renders it as *"Scanned 412 pairs. 38 entered the tradable universe. None qualified."* —
#: and recording it as a block would fill `block_records` with a normal Tuesday and corrupt
#: engine 17 `safety`'s error rate, which counts those rows.
#:
#: Like :data:`REASON_INPUTS_UNAVAILABLE` it is **not** in :data:`EXCLUSION_REASONS`: it is a
#: statement about the tick rather than about a pair. Every pair that produced it is already
#: counted under its own exclusion code, so counting this one too would double-count the
#: whole universe.
REASON_EMPTY_UNIVERSE: Final = "empty_universe"

#: The universe was computed and is **not** empty, but the expected-move ranking skipped
#: every pair in it. Each one had an incomplete vector, or an anomaly score or DI the gates
#: would refuse (R11, spec 144). So there is no candidate this tick.
#:
#: **A `PASS`, like :data:`REASON_EMPTY_UNIVERSE`, and for the same reason.** This matches
#: the measurement the ruling rests on. `q_emrank.py` takes no pair on a bar where none
#: passes anomaly and DI. It also matches what the gates would have said: every candidate
#: examined would have been refused. Not in :data:`EXCLUSION_REASONS`, because it is a
#: statement about the tick and not about a pair. It is its own code, not
#: `empty_universe`, because the universe was not empty. A console that said so would be
#: telling the operator the account can trade nothing when it can.
REASON_NO_RANKABLE_PAIR: Final = "no_rankable_pair"

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


def _feature_value(features: Mapping[str, Any] | None, pair: str, feature: str) -> float | None:
    """One pair's value for the named feature, or `None` when it has none.

    **Four situations arrive here and three of them are the same fact.** No feature map at
    all, a pair absent from the map, and a pair present with a null value all mean "this
    pair has no value for this feature", and spec 76 gives them one answer: sort after
    every pair that has one, and never drop the pair. The fourth is a usable number.

    **NaN counts as no value.** `modelling/features.py` yields NaN for a lookback whose
    fill is below `features.min_lookback_fill` and engine 5 publishes those as null, but a
    float NaN is one `orjson` setting away from crossing `state` intact — and NaN compares
    false against everything including itself, so a NaN left in a sort key orders
    unpredictably and can order differently between two runs over the same data. Treating
    it as absent is the only reading that keeps this ordering deterministic, which is the
    property invariant 4 protects.
    """
    if not isinstance(features, Mapping):
        return None
    row = features.get(pair)
    if not isinstance(row, Mapping):
        return None
    value = row.get(feature)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _rank_by_expected_move(
    names: list[str], expected_moves: Mapping[str, float] | None, *, descending: bool
) -> tuple[str, ...]:
    """The universe pairs the ranking scored, by expected move, then by name ascending.

    **A pair with no expected move is dropped, the opposite of the feature rule.** Under
    the feature ordering a pair with no value sorts last and stays examinable. Here, having
    no value means the shared function skipped the pair: an incomplete vector, or a score
    the anomaly or DI gate would refuse. R11, ruled 2026-09-19, says the ranking skips those
    pairs, because the 46-trade measurement did. A non-finite value is treated as no value,
    for the reason `_feature_value` gives.

    `expected_moves` being `None` here is a caller defect, not "nothing ranked". The engine
    always passes the function's answer, even an empty one. Reading `None` as empty would
    turn a lost ranking into a quiet tick with no candidate.
    """
    if expected_moves is None:
        raise ValueError(
            f"rank_universe was asked to order by {RANK_BY_EXPECTED_MOVE!r} and handed no "
            "expected moves"
        )
    scored: list[tuple[float, str]] = []
    for pair in names:
        value = expected_moves.get(pair)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            scored.append((float(value), pair))
    # Negated rather than `reverse=True`, so the tie-break stays ascending by name in both
    # directions. The same argument the feature ordering makes below.
    scored.sort(key=lambda item: (-item[0] if descending else item[0], item[1]))
    return tuple(pair for _value, pair in scored)


def rank_universe(
    pairs: Iterable[str],
    *,
    features: Mapping[str, Any] | None = None,
    feature: str | None = None,
    descending: bool = True,
    expected_moves: Mapping[str, float] | None = None,
) -> tuple[str, ...]:
    """The universe in the order the candidate is taken from.

    **One named feature, one direction, one tie-break.** `feature` is `scout.rank_feature`,
    `descending` is `scout.rank_descending`, and `features` is `state["feature"]["pairs"]`
    exactly as engine 5 publishes it.

    With `feature` `None` the ordering is alphabetical and nothing else. That is the
    baseline the operator ruled for the Phase 7 simulation, and it must not move.

    With `feature` equal to :data:`RANK_BY_EXPECTED_MOVE` (operator ruling R1,
    2026-09-19): by `expected_moves`, the predictor's expected move for each pair the shared
    ranking function scored, then by name ascending. **A pair with no expected move is
    dropped**, because R11 says the ranking skips it. See :func:`_rank_by_expected_move`.
    This ordering reads a model's output, which invariant 4 as amended by R12 permits:
    ordering changes which candidate is examined, never whether an examined candidate is
    approved. Every gate re-judges the chosen pair from scratch.

    With any other feature: by that value, then **by pair name ascending** as the
    tie-break, in both directions. A pair with no value for it sorts after every pair that
    has one, alphabetically among themselves, and is **never dropped**. A pair with no
    feature is still in the universe, and dropping it would silently shrink the universe
    the rest of this module spent the tick computing.

    ## History, because the next reader will come here looking for a score

    From Phase 3 to Phase 5 this function was alphabetical and carried a recorded absence
    in place of a ranking. The operator ruled on 2026-09-10 that a placeholder score would
    be a check whose output resembles the claim while the claim is untrue, and that
    ranking one candidate out of a filtered set was a Phase 5 decision to be made with real
    features in front of us. Spec 59 decision 7 then made it **a config-named feature
    rather than a formula**: the mechanism is here now, the feature itself arrives in
    `config/default.yaml` from the operator's ruling on the spec 75 ranking study, and
    while `scout.rank_feature` is absent the ordering stays alphabetical and the engine
    publishes `rank_feature: null`.

    ## Why the test for this is a direct one and an end-to-end test cannot replace it

    The engine builds its scan set with `sorted`, so this function is always handed an
    already-ordered sequence, and a ranking that merely preserved arrival order would
    still answer alphabetically end to end. Only a direct call on input where arrival
    order and intended order disagree on **every** element separates "orders by the
    feature" from "preserves what it was given". `feature-specs/PHASE-5-TASKS.md` names
    this seam directly and calls that test not optional.
    """
    names = list(pairs)
    if feature is None:
        # Deliberately not `sorted(..., key=...)`. With nothing configured there is
        # nothing to key on, and a key function is where a score arrives by accident.
        return tuple(sorted(names))
    if feature == RANK_BY_EXPECTED_MOVE:
        return _rank_by_expected_move(names, expected_moves, descending=descending)

    def ordering(pair: str) -> tuple[int, float, str]:
        value = _feature_value(features, pair, feature)
        if value is None:
            # 1 sorts after 0 in **both** directions, so "no value last" is a property of
            # the ordering rather than of the direction. The 0.0 is never compared against
            # anything: it exists only because every key must have the same shape.
            return (1, 0.0, pair)
        # Negating for descending keeps the tie-break ascending by name in both
        # directions. `reverse=True` would reverse the tie-break too, so two pairs with
        # equal values would swap places when the direction flipped and the candidate
        # would move on a config flag that is supposed to order by the feature alone.
        return (0, -value if descending else value, pair)

    return tuple(sorted(names, key=ordering))


def select_candidate(
    pairs: Iterable[str],
    *,
    features: Mapping[str, Any] | None = None,
    feature: str | None = None,
    descending: bool = True,
    expected_moves: Mapping[str, float] | None = None,
) -> str | None:
    """The one pair the judgement chain will consider, or `None` when the universe is empty.

    One candidate leaves this engine, never several: the judgement chain considers one, and
    engines 10 and 11 read a single `state["scout"]["pair"]`.

    `None` is a routine answer rather than a failure — nothing qualifying is this system's
    honest default state on a small account — and the engine turns it into `PASS`, not
    `BLOCK`. See the engine's module docstring for why that distinction is load-bearing.

    Every ranking argument is passed straight through to :func:`rank_universe`. This
    function holds no ordering of its own, so there is one seam and not two.
    """
    ordered = rank_universe(
        pairs,
        features=features,
        feature=feature,
        descending=descending,
        expected_moves=expected_moves,
    )
    return ordered[0] if ordered else None


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
    payload is deterministic and JSON-safe.

    **`pairs` is in scan order and carries no ranking, deliberately, and that is still
    true now that a ranking exists.** The ranking is expressed by :attr:`candidate` and by
    :attr:`rank_feature`, which say which pair was taken and on what basis. Sorting the
    published universe by the feature as well would put the same ordering in two places,
    and the day they disagreed — a consumer reading `pairs[0]` instead of `pair` — the
    disagreement would be silent. One expression of the ranking, not two.

    **The counts are not decoration.** `scanned`, `entered` and `excluded` are what the
    console's empty state renders, and they are required to add up.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pairs: tuple[str, ...] = ()
    scanned: int = 0
    excluded: Mapping[str, int] = {}
    equity: Money | None = None

    candidate: str | None = None
    """The one pair the judgement chain will consider, or `None` when nothing qualified.

    Chosen by :func:`select_candidate` over :func:`rank_universe`. It is published under
    :data:`CANDIDATE_FIELD` and is **absent from the payload** rather than null when there
    is none.
    """

    rank_feature: str | None = None
    """The feature the universe was ordered by, or `None` for alphabetical.

    Published as **null and not omitted**, unlike `candidate`. Null is the answer here
    rather than the absence of one: it says the ordering was alphabetical because nothing
    is configured, which is what separates "no ranking was asked for" from "the ranking
    rated every pair equally". The spec 75 study's alphabetical control is exactly that
    distinction, and a reader that could not draw it would be comparing a ranking against
    itself.
    """

    rank_descending: bool = True
    """Which end of :attr:`rank_feature` was taken. Published even when no feature is
    configured, because it is the configured direction and not a property of this tick —
    an operator reading the console should see what the ranking *would* do."""

    reason_code: str | None = None
    """Why there is no candidate, or `None` when there is one.

    :data:`REASON_EMPTY_UNIVERSE` on an empty universe, and :data:`REASON_NO_RANKABLE_PAIR`
    when the expected-move ranking skipped every pair of a non-empty one. Both are a
    `PASS` and not a failure, so this field is not evidence of one.
    """

    ranked: tuple[tuple[str, Money], ...] = ()
    """With the expected-move ranking, `(pair, expected move)` in ranked order. Empty
    otherwise. The expected move is a `Decimal`, published as an exact decimal string, as
    engine 8 publishes `expected_move_pct`."""

    rank_skipped: Mapping[str, int] = {}
    """With the expected-move ranking, universe pairs skipped per skip code. Not an
    exclusion tally: see :data:`RANK_SKIPPED_FIELD`."""

    rank_run_ids: Mapping[str, str] | None = None
    """The model runs the ranking scored with, or `None` when no model ranked."""

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
        """The JSON-serialisable form the orchestrator puts in `state["scout"]`.

        **`pair` is omitted entirely when there is no candidate**, rather than emitted as
        `null`. Engines 10 and 11 reach it through a `_require` that treats a published
        `None` exactly like an absent key — so a null would be handled correctly today, and
        the omission is about tomorrow: a key called `pair` sitting in the payload of a tick
        that chose nothing is a key some future consumer reads without the `_require`. The
        same shape, and the same argument, as `RiskSizing` omitting `qty` on a rejection.
        """
        payload: dict[str, Any] = {
            PAIRS_FIELD: list(self.pairs),
            "scanned": self.scanned,
            "entered": self.entered,
            "excluded": dict(self.excluded),
            "equity": None if self.equity is None else format(self.equity, "f"),
            "reason_code": self.reason_code,
            RANK_FEATURE_FIELD: self.rank_feature,
            RANK_DESCENDING_FIELD: self.rank_descending,
            RANKED_FIELD: [
                {CANDIDATE_FIELD: pair, "expected_move_pct": format(move, "f")}
                for pair, move in self.ranked
            ],
            RANK_SKIPPED_FIELD: dict(self.rank_skipped),
            RANK_RUN_IDS_FIELD: None if self.rank_run_ids is None else dict(self.rank_run_ids),
        }
        if self.candidate is not None:
            payload[CANDIDATE_FIELD] = self.candidate
        return payload
