"""Engine 7 `scout` — the tradable universe, recomputed from scratch every tick.

Which Kraken pairs could this account legitimately trade *right now*? Not which pairs it
likes, which is spec 44's question; which ones are possible at all.

**A Locked Decision, quoted because this module is its only implementation:** *"Tradable
universe computed per tick from `ordermin`, `costmin`, tick size, live spread and balance.
No account-size thresholds."* There is no pair list here, no config key holding one, and no
comparison of a balance against a literal. The filter is arithmetic; the balance is one of
its inputs.

**Deterministic and protected.** Invariant 4: no confidence score, probability, ensemble
weight or router decision may skip, soften or override this gate. It contains no model, so
there is nothing here for one to override — and that is the property being protected rather
than a coincidence.

## Every exclusion is counted, and the counts must add up

The console's most-viewed screen state is the one where nothing qualified — *"Scanned 412
pairs. 38 entered the tradable universe."* — and it renders from this engine's tally. So a
pair is attributed to the **first** rule it fails and to exactly one, which makes
`scanned == entered + sum(excluded)` an identity rather than an aspiration. A test asserts
it, because a pair excluded without a code would silently leave that sentence untrue.

The order in :data:`EXCLUSION_REASONS` is therefore behaviour, not presentation: it decides
which code an excluded pair is counted under.

## The sizing arithmetic exists twice, on purpose

Engine 11 `risk` sizes the position; this filter asks whether a position is possible at all.
Contract rule 3 forbids one engine importing another, so the arithmetic is written twice —
and `test_the_sizing_agrees_with_engine_eleven` in `tests/engines/test_scout.py` holds the
two together over a shared table spanning both sides of `ordermin` and `costmin`. Both
READMEs name that test. If you change the sizing here, that is the test that should stop
you.

The shape is engine 11's exactly, including which side of the book each question is asked
of: the **ask** prices the entry, because it is the worst price a buy could pay and a higher
assumed price yields fewer units; the **bid** values the resulting position, because it is
the lowest it could be worth. The lead's ruling of 2026-09-10.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from pydantic import ValidationError

from acsoe.core.contracts import BaseEngine, EngineContext, EngineResult, EngineStatus, State
from acsoe.engines.scout.contracts import (
    EXCHANGE_BALANCES_KEY,
    EXCHANGE_KEY,
    EXCHANGE_PAIR_RULES_KEY,
    FEATURE_KEY,
    FEATURE_NAMES_KEY,
    FEATURE_PAIRS_KEY,
    MARKET_SENSOR_KEY,
    MARKET_SENSOR_QUOTES_KEY,
    PAIR_BASE_FIELD,
    PAIR_COSTMIN_FIELD,
    PAIR_LOT_DECIMALS_FIELD,
    PAIR_ORDERMIN_FIELD,
    PAIR_QUOTE_FIELD,
    PAIR_RULES_PAIRS_KEY,
    PAIR_TICK_SIZE_FIELD,
    QUOTE_ASK_FIELD,
    QUOTE_BID_FIELD,
    REASON_BELOW_COSTMIN,
    REASON_BELOW_ORDERMIN,
    REASON_CRYPTO_QUOTED,
    REASON_EMPTY_UNIVERSE,
    REASON_INPUTS_UNAVAILABLE,
    REASON_INSUFFICIENT_QUOTE_BALANCE,
    REASON_NO_FX_RATE,
    REASON_NO_LIVE_QUOTE,
    REASON_NO_QUOTE_BALANCE,
    REASON_PAIR_RULES_MISSING,
    REASON_QUOTE_NOT_PROVABLY_STABLE,
    REASON_TICK_GRID_TOO_COARSE,
    PairFacts,
    ScoutUniverse,
    round_down_to_lot,
    select_candidate,
)

RISK_FRACTION_KEY = "trading.risk_fraction_per_trade"
STOP_PCT_KEY = "barriers.stop_pct"
TARGET_PCT_KEY = "barriers.target_pct"
ALLOW_CRYPTO_QUOTED_KEY = "trading.allow_crypto_quoted"
REPORTING_CURRENCY_KEY = "trading.base_reporting_currency"

#: The operator's set of quote currencies that are not a second directional bet. **Absent
#: is not empty** — see :meth:`ScoutEngine._stable_quotes`.
STABLE_QUOTES_KEY = "trading.stable_quote_currencies"

#: The feature the universe is ranked by, and which end of it to take. **Absent until the
#: operator rules on the spec 75 ranking study**; alphabetical meanwhile. Spec 59
#: decision 7 — the ranking is a config-named feature, never a formula written here.
RANK_FEATURE_KEY = "scout.rank_feature"
RANK_DESCENDING_KEY = "scout.rank_descending"

__all__ = ["MissingInputError", "ScoutEngine"]


class MissingInputError(Exception):
    """An input this gate needs is absent, null or the wrong shape.

    Raised for a fault that makes the *whole tick* unanswerable — no pair rules at all, no
    equity, an unreadable threshold. A fault in one pair is an exclusion with a reason code,
    not this: excluding one pair and blocking the tick are very different answers and must
    not share a path.
    """


def _config_decimal(context: EngineContext, key: str) -> Decimal:
    """A configured ratio as a `Decimal`, blocking on absent or null.

    A YAML scalar like `0.015` parses to a Python `float`, and `Decimal(0.015)` is not
    `0.015`. The conversion goes through `repr`, the shortest string that round-trips — the
    only safe route from a YAML number to an exact decimal. A null key is the OPERATOR
    REQUIRED state and blocks rather than defaulting, because a default here is a number
    silently deciding which pairs the system will trade.
    """
    value = context.config.get(key)
    if value is None:
        raise MissingInputError(f"config {key} is null (OPERATOR REQUIRED)")
    try:
        return Decimal(repr(value) if isinstance(value, float) else str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MissingInputError(f"config {key} is not a number: {value!r}") from exc


class ScoutEngine(BaseEngine):
    """Gate 7. Opportunity chain, runtime stage 2."""

    name: ClassVar[str] = "scout"
    number: ClassVar[int] = 7
    #: Registry table in `context/engine-contracts.md` marks engine 7 as a Gate.
    #: `is_gate_matches_registry` asserts this exact value.
    is_gate: ClassVar[bool] = True

    def process(self, context: EngineContext, state: State) -> EngineResult:
        started = time.perf_counter()

        try:
            universe = self._compute(context, state)
        except MissingInputError as missing:
            return self._blocked_on_missing_input(str(missing), started)

        duration_ms = (time.perf_counter() - started) * 1000.0

        # **An empty universe is `PASS`, and the distinction is the whole reason
        # `EngineStatus` has both.** `PASS` means "nothing to do this cycle; not an error",
        # and the orchestrator stops the opportunity chain on it *without* setting
        # `trading_blocked_by`. Nothing qualifying is this system's honest default state on
        # a small account; recording it as a block would fill `block_records` with a normal
        # Tuesday and corrupt engine 17 `safety`'s error rate, which counts those rows.
        #
        # `BLOCK` is reserved for the gate failure above — this engine could not reach the
        # data to compute a universe at all. That is invariant 3 and it is a different fact.
        if universe.candidate is None:
            return EngineResult(
                engine=self.name,
                status=EngineStatus.PASS,
                blocks_trading=False,
                data=universe.to_state_data(),
                duration_ms=duration_ms,
            )

        return EngineResult(
            engine=self.name,
            status=EngineStatus.OK,
            blocks_trading=False,
            data=universe.to_state_data(),
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------ the filter

    def _compute(self, context: EngineContext, state: State) -> ScoutUniverse:
        """Every pair, filtered. One reason per excluded pair, and the counts add up."""
        rules = self._pair_rules(state)
        quotes = self._quotes(state)
        balances = self._balances(state)
        equity = self._equity(context)

        risk_fraction = _config_decimal(context, RISK_FRACTION_KEY)
        stop_pct = _config_decimal(context, STOP_PCT_KEY)
        target_pct = _config_decimal(context, TARGET_PCT_KEY)
        if stop_pct <= 0 or target_pct <= 0:
            raise MissingInputError("configured barriers must be positive ratios")

        reporting_currency = str(context.config.get(REPORTING_CURRENCY_KEY))
        allow_crypto = bool(context.config.get(ALLOW_CRYPTO_QUOTED_KEY))
        stable = self._stable_quotes(context)

        # Read before the filter runs, not after, because a configured feature with no
        # engine 5 output is a tick-level block and the whole tick is unanswerable. Doing
        # the work first and discovering it afterwards would publish nothing either way
        # and burn the scan.
        rank_feature = self._rank_feature(context)
        rank_descending = self._rank_descending(context)
        features = self._features(state, rank_feature)

        # The notional this account's equity would put behind any one position. Computed
        # once: it is a property of the account, not of a pair. Invariant 6 sizes against
        # total equity, so this is the same number engine 11 arrives at.
        target_notional = (equity * risk_fraction) / stop_pct

        pairs: list[str] = []
        excluded: dict[str, int] = {}
        scanned = sorted(set(rules) | set(quotes))

        for name in scanned:
            reason = self._exclusion(
                name,
                rules.get(name),
                quotes.get(name),
                balances=balances,
                allow_crypto=allow_crypto,
                stable=stable,
                target_notional=target_notional,
                stop_pct=stop_pct,
                target_pct=target_pct,
                reporting_currency=reporting_currency,
            )
            if reason is None:
                pairs.append(name)
            else:
                excluded[reason] = excluded.get(reason, 0) + 1

        # One candidate leaves this engine, never several: the judgement chain considers
        # one. The ordering lives in `rank_universe` — one named seam, so the ranking is
        # one edit and not a hunt through this engine — and it is alphabetical while no
        # feature is configured.
        candidate = select_candidate(
            pairs, features=features, feature=rank_feature, descending=rank_descending
        )

        return ScoutUniverse(
            pairs=tuple(pairs),
            scanned=len(scanned),
            excluded=excluded,
            equity=equity,
            candidate=candidate,
            reason_code=None if candidate is not None else REASON_EMPTY_UNIVERSE,
            rank_feature=rank_feature,
            rank_descending=rank_descending,
        )

    def _exclusion(
        self,
        name: str,
        rule: Any,
        quote: Any,
        *,
        balances: Mapping[str, Any],
        allow_crypto: bool,
        stable: frozenset[str] | None,
        target_notional: Decimal,
        stop_pct: Decimal,
        target_pct: Decimal,
        reporting_currency: str,
    ) -> str | None:
        """Why this pair is not tradable right now, or `None` if it is.

        The rules are applied in :data:`EXCLUSION_REASONS` order and the first failure wins,
        which is what makes the tally exhaustive. Every branch returns a code; none logs and
        continues, because a pair that fell out without a code would break the console's
        arithmetic silently.
        """
        if rule is None:
            return REASON_PAIR_RULES_MISSING
        if quote is None:
            return REASON_NO_LIVE_QUOTE

        try:
            facts = self._facts(name, rule, quote)
        except MissingInputError:
            # An unparseable rule or an unusable quote is not a tick-level fault; it is
            # this pair being untradable. A published `null` ordermin means the fetch
            # failed, and invariant 2 gives pair rules no fallback in any mode.
            return REASON_PAIR_RULES_MISSING
        if facts.ask <= 0 or facts.bid <= 0:
            # Absent is not zero and neither is a non-positive price: it is an unusable
            # quote, never a free entry.
            return REASON_NO_LIVE_QUOTE

        if not allow_crypto:
            if stable is None:
                return REASON_QUOTE_NOT_PROVABLY_STABLE
            if facts.quote not in stable:
                return REASON_CRYPTO_QUOTED

        held = balances.get(facts.quote)
        try:
            balance = Decimal(str(held)) if held is not None else Decimal(0)
        except (InvalidOperation, ValueError):
            balance = Decimal(0)
        if balance <= 0:
            return REASON_NO_QUOTE_BALANCE

        # The barriers must be expressible on this pair's tick grid. On a pair whose tick
        # is coarse relative to its price a stop rounds onto the entry price itself, and
        # the position has no stop at all.
        #
        # **Both barriers are checked, not just the nearer one.** The stop is nearer under
        # the committed config and would bind on its own, but "the stop is always the
        # nearer barrier" is a property of two numbers the operator may retune, and an
        # engine that assumed it would stop enforcing the target silently the day they
        # crossed.
        if min(stop_pct, target_pct) * facts.ask <= facts.tick_size:
            return REASON_TICK_GRID_TOO_COARSE

        # **Affordability cannot be computed across currencies, so the pair is excluded.**
        # `target_notional` derives from equity, which invariant 7 expresses in
        # `trading.base_reporting_currency`; the balance is in the pair's quote currency.
        # Comparing them needs an FX rate, and invariant 7 says one is converted "at the
        # trade timestamp" — but nothing in this system publishes one.
        #
        # Ruled by the operator on 2026-09-10, after I escalated rather than choosing.
        # Excluding *claims nothing about the world*, which is what separates it from
        # inventing a rate or assuming parity — the same shape as the not-provably-stable
        # exclusion above, and different in kind from a heuristic that would assert a fact
        # and be wrong on real data.
        if facts.quote != reporting_currency:
            return REASON_NO_FX_RATE

        # Invariant 6: never allocate cash the account does not hold in that pair's quote
        # currency. Both sides are computed and neither is a literal, so this is arithmetic
        # over the balance rather than the account-size threshold the Locked Decision
        # forbids.
        if target_notional > balance:
            return REASON_INSUFFICIENT_QUOTE_BALANCE

        qty = round_down_to_lot(target_notional / facts.ask, facts.lot_decimals)
        if qty < facts.ordermin:
            return REASON_BELOW_ORDERMIN
        if qty * facts.bid < facts.costmin:
            return REASON_BELOW_COSTMIN
        return None

    # ------------------------------------------------------------------ inputs

    def _facts(self, name: str, rule: Any, quote: Any) -> PairFacts:
        raw = {
            "pair": name,
            "base": _field(rule, PAIR_BASE_FIELD),
            "quote": _field(rule, PAIR_QUOTE_FIELD),
            "ordermin": _field(rule, PAIR_ORDERMIN_FIELD),
            "costmin": _field(rule, PAIR_COSTMIN_FIELD),
            "tick_size": _field(rule, PAIR_TICK_SIZE_FIELD),
            "lot_decimals": _field(rule, PAIR_LOT_DECIMALS_FIELD),
            "bid": _field(quote, QUOTE_BID_FIELD),
            "ask": _field(quote, QUOTE_ASK_FIELD),
        }
        try:
            return PairFacts.model_validate(raw)
        except ValidationError as exc:
            raise MissingInputError(f"{name}: {exc}") from exc

    def _pair_rules(self, state: State) -> Mapping[str, Any]:
        """`state["exchange"]["pair_rules"]["pairs"]`, or a tick-level block.

        A null `pair_rules` is the failed-`AssetPairs` case, and invariant 2 gives it no
        fallback in any mode. It is a block rather than an empty universe because those are
        different facts: "the exchange listed nothing you can trade" and "we could not ask"
        must not render the same on the console.
        """
        exchange = state.get(EXCHANGE_KEY)
        if not isinstance(exchange, dict):
            raise MissingInputError(f"{EXCHANGE_KEY} is absent")
        snapshot = exchange.get(EXCHANGE_PAIR_RULES_KEY)
        if not isinstance(snapshot, dict):
            raise MissingInputError(
                f"{EXCHANGE_KEY}.{EXCHANGE_PAIR_RULES_KEY} is absent; AssetPairs did not answer"
            )
        pairs = snapshot.get(PAIR_RULES_PAIRS_KEY)
        if not isinstance(pairs, dict):
            raise MissingInputError(
                f"{EXCHANGE_KEY}.{EXCHANGE_PAIR_RULES_KEY}.{PAIR_RULES_PAIRS_KEY} is absent"
            )
        return pairs

    def _quotes(self, state: State) -> Mapping[str, Any]:
        """`state["market_sensor"]["quotes"]`. An empty map is legal and excludes every
        pair one at a time; an absent `market_sensor` is a tick-level block."""
        sensor = state.get(MARKET_SENSOR_KEY)
        if not isinstance(sensor, dict):
            raise MissingInputError(f"{MARKET_SENSOR_KEY} is absent")
        quotes = sensor.get(MARKET_SENSOR_QUOTES_KEY)
        if not isinstance(quotes, dict):
            raise MissingInputError(f"{MARKET_SENSOR_KEY}.{MARKET_SENSOR_QUOTES_KEY} is absent")
        return quotes

    def _balances(self, state: State) -> Mapping[str, Any]:
        """`state["exchange"]["balances"]`, or an empty map when the fetch failed.

        **No fallback here, and none is needed.** Invariant 2's balance fallback belongs to
        engine 11, which is the engine that has to size a real position and record which
        fallback fired. This engine's answer to "the account holds nothing in that currency"
        is already an exclusion with a code, so an absent balances map degrades to every
        pair excluded for `no_quote_balance` — visible in the tally, and never mistaken for
        a universe that was computed against real balances.
        """
        exchange = state.get(EXCHANGE_KEY)
        if not isinstance(exchange, dict):
            raise MissingInputError(f"{EXCHANGE_KEY} is absent")
        balances = exchange.get(EXCHANGE_BALANCES_KEY)
        return balances if isinstance(balances, dict) else {}

    def _equity(self, context: EngineContext) -> Decimal:
        """Total account equity, from the latest `equity_snapshots` row.

        **Not the quote balance**, for the reason engine 11 gives: invariant 6 sizes against
        cash plus the value of open positions, and only engine 19 `memory` computes that.
        No snapshot is a block, never a fallback to a balance — a fallback there would let
        the system decide what it can trade against an equity figure nothing computed.
        """
        store = getattr(context.clients, "store", None)
        if store is None:
            raise MissingInputError("clients.store is not available")
        snapshot = store.latest_equity_snapshot()
        if snapshot is None:
            raise MissingInputError("no equity_snapshots row yet; cannot size against equity")
        currency = str(snapshot.currency)
        reporting = str(context.config.get(REPORTING_CURRENCY_KEY))
        if currency != reporting:
            raise MissingInputError(
                f"latest equity snapshot is in {currency}, not the reporting currency {reporting}"
            )
        equity: Decimal = snapshot.equity
        return equity

    def _rank_feature(self, context: EngineContext) -> str | None:
        """`scout.rank_feature`, or `None` while the operator has not ruled.

        **Absent and null are the same fact for this key**, and that is a statement about
        this key rather than a shortcut. `code-standards.md` warns that catching `KeyError`
        over a config read conflates "absent" with "present and null" — two facts
        `Config.get` reports differently on purpose, and for
        `trading.stable_quote_currencies` they genuinely differ. Here they do not: spec 59
        decision 7 keeps the key out of the YAML until the operator rules on the spec 75
        study, and spec 61 types the field `str | None = None`, so "no feature chosen yet"
        reaches this method as absence from a tree without the key and as null from one
        with it. Both mean alphabetical, and `rank_feature: null` is published either way.

        An empty or whitespace name is **not** the same fact and is refused. It is a key
        somebody set to nothing, and ranking by a feature named `""` would find no value
        for any pair, order them alphabetically under the null rule, and report a ranking
        it never performed — the placeholder score the operator refused, arriving through
        a typo instead of a design.
        """
        try:
            value = context.config.get(RANK_FEATURE_KEY)
        except KeyError:
            # `KeyError` and not `Exception`: `platform/config.py`'s `ConfigKeyError`
            # subclasses it, so this catches exactly "no such key" and lets a genuine
            # fault in the config layer reach the orchestrator as the ERROR it is.
            return None
        if value is None:
            return None
        name = str(value)
        if name.strip() == "":
            raise MissingInputError(f"config {RANK_FEATURE_KEY} is set to an empty feature name")
        return name

    def _rank_descending(self, context: EngineContext) -> bool:
        """`scout.rank_descending`, defaulting to `True`.

        **Not a trading threshold, so a default is legitimate here** where it would not be
        for a barrier or a risk fraction. It decides which end of a feature is interesting,
        it is only ever read once a feature has been named, and spec 61 gives the field the
        same default on the config model. A wrong direction produces a different candidate,
        never a trade the gates would otherwise have refused.
        """
        try:
            value = context.config.get(RANK_DESCENDING_KEY)
        except KeyError:
            return True
        return True if value is None else bool(value)

    def _features(self, state: State, feature: str | None) -> Mapping[str, Any] | None:
        """`state["feature"]["pairs"]`, or a tick-level block when a feature is configured
        and engine 5 published nothing.

        **A configured ranking that silently fell back to alphabetical would be the
        placeholder score the operator refused in Phase 3.** The engine would report a
        ranking it did not perform, and the candidate would be right only on the ticks
        where alphabetical happened to agree — which is the worst shape a defect can take
        here, because it is correct often enough to look fine. Invariant 3: a gate that
        cannot reach its data blocks.

        With no feature configured, engine 5's absence is not a fault at all and nothing is
        read. That is what lets this engine run unchanged on a tree where engine 5 does not
        exist yet, which is the tree it is being written on.
        """
        if feature is None:
            return None
        published = state.get(FEATURE_KEY)
        if not isinstance(published, dict):
            raise MissingInputError(
                f"{FEATURE_KEY} is absent while {RANK_FEATURE_KEY} names {feature!r}"
            )
        pairs = published.get(FEATURE_PAIRS_KEY)
        if not isinstance(pairs, dict):
            raise MissingInputError(
                f"{FEATURE_KEY}.{FEATURE_PAIRS_KEY} is absent while "
                f"{RANK_FEATURE_KEY} names {feature!r}"
            )

        # **A feature nobody computes is a third way of being unable to rank**, and it is
        # the one that hides. A misspelt name finds no value for any pair, the no-value
        # rule then orders every pair alphabetically among themselves, and the engine
        # publishes the misspelt name beside a ranking it never performed — no exception,
        # no null, and a candidate that is a real pair from the real universe. The
        # per-pair question and the whole-universe question are different, and answering
        # both with `_feature_value` returning `None` is what made this silent.
        #
        # `feature_names` is engine 5's republication of `modelling.features.FEATURE_NAMES`
        # and is a required field of its payload, so it is present whenever engine 5 ran at
        # all. Absent or the wrong shape blocks here for the same reason a missing `pairs`
        # does: the payload cannot answer the question this gate has to ask of it.
        names = published.get(FEATURE_NAMES_KEY)
        if not isinstance(names, (list, tuple)):
            raise MissingInputError(
                f"{FEATURE_KEY}.{FEATURE_NAMES_KEY} is absent while "
                f"{RANK_FEATURE_KEY} names {feature!r}"
            )
        if feature not in {str(name) for name in names}:
            raise MissingInputError(
                f"{RANK_FEATURE_KEY} names {feature!r}, which is not one of the "
                f"{len(names)} features engine 5 publishes"
            )
        return pairs

    def _stable_quotes(self, context: EngineContext) -> frozenset[str] | None:
        """`trading.stable_quote_currencies`, or `None` when the operator has not set it.

        **`None` and empty are different answers and must not be collapsed.** An absent key
        means nobody has said which currencies are stable, and the lead ruled on 2026-09-10
        that a quote which cannot be *shown* stable is excluded — under its own code, so a
        universe that shrank for want of a config key is distinguishable from one that
        shrank by policy. An empty set is an operator saying "none of them are", which is a
        decision and excludes everything under the ordinary code.

        The real `Config` returns a `frozenset` and the test double returns a list, so this
        coerces rather than assuming either.
        """
        try:
            value = context.config.get(STABLE_QUOTES_KEY)
        except KeyError:
            # `KeyError` and not `Exception`: `platform/config.py`'s `ConfigKeyError`
            # subclasses it, and so does the test double's raise, so this catches exactly
            # "no such key" from both and lets a genuine defect through to the orchestrator.
            # Catching broadly here would turn any fault in the config layer into a silent
            # universe-wide exclusion, which is the loudest possible symptom rendered as
            # the quietest possible one.
            return None
        if value is None:
            return None
        if isinstance(value, str) or not isinstance(value, Iterable):
            raise MissingInputError(
                f"config {STABLE_QUOTES_KEY} is not a list of currency codes: {value!r}"
            )
        return frozenset(str(code) for code in value)

    # ------------------------------------------------------------------ failure

    def _blocked_on_missing_input(self, detail: str, started: float) -> EngineResult:
        """Fail closed, naming what was missing. Invariant 3.

        `data` carries no universe rather than an empty one: publishing `scanned: 0` on a
        tick where nothing was scanned *because the fetch failed* would put a zero into the
        console's arithmetic that means something entirely different from a zero earned by
        filtering.
        """
        return EngineResult(
            engine=self.name,
            status=EngineStatus.BLOCK,
            blocks_trading=True,
            reason=f"Scout could not read the pairs it needs: missing {detail}",
            data={"reason_code": REASON_INPUTS_UNAVAILABLE},
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


def _field(container: Any, key: str) -> Any:
    """Fetch `key` out of a published mapping, treating `None` exactly like absent."""
    if not isinstance(container, dict):
        return None
    return container.get(key)
