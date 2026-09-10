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
)

RISK_FRACTION_KEY = "trading.risk_fraction_per_trade"
STOP_PCT_KEY = "barriers.stop_pct"
TARGET_PCT_KEY = "barriers.target_pct"
ALLOW_CRYPTO_QUOTED_KEY = "trading.allow_crypto_quoted"
REPORTING_CURRENCY_KEY = "trading.base_reporting_currency"

#: The operator's set of quote currencies that are not a second directional bet. **Absent
#: is not empty** — see :meth:`ScoutEngine._stable_quotes`.
STABLE_QUOTES_KEY = "trading.stable_quote_currencies"

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
        # An empty universe is not an error and not a block: it is a tick with nothing to
        # consider, which happens routinely on a small account. Spec 44 owns the candidate
        # and the gate proper; this is the status that will not have to change under it.
        status = EngineStatus.OK if universe.pairs else EngineStatus.PASS
        return EngineResult(
            engine=self.name,
            status=status,
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

        return ScoutUniverse(
            pairs=tuple(pairs),
            scanned=len(scanned),
            excluded=excluded,
            equity=equity,
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
