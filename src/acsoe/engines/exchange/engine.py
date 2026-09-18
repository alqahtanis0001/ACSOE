"""Engine 1 `exchange` — the account picture, fetched every tick.

First in the guard chain, and **not a gate**. It reports what the exchange said and
what it would not say; engine 4 `data_guard` decides, and engines 10 `cost` and 11
`risk` decide about a candidate. Engine 1 never blocks trading on its own.

That is the whole design, and the temptation it resists is worth naming: when all
three fetches fail there is no account picture at all, and blocking looks obviously
right. It is not this engine's call. A block here would be a fifth gate nobody
registered, it would set ``state["trading_blocked_by"] = "exchange"`` and mask the
real blocker on the same tick, and — because ``data_guard`` blocking is what makes
the manage chain hold exits — it would give engine 1 a say in whether an open
position gets managed. Reporting the absence honestly is enough: every gate that
needs a value it did not get blocks on its own, which is invariant 3.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

from acsoe.clients.kraken.contracts import (
    BalancesSnapshot,
    FeeTierSnapshot,
    PairRulesSnapshot,
    RetainedValue,
    coerce_balances,
    coerce_fee_tier,
    coerce_pair_rules,
    to_micros,
)
from acsoe.clients.kraken.errors import KrakenAPIError, KrakenError
from acsoe.core.contracts import (
    BaseEngine,
    EngineContext,
    EngineResult,
    EngineStatus,
    State,
)
from acsoe.engines.exchange.contracts import (
    CALLS,
    ExchangeState,
    FetchFailure,
    RetainedNote,
)
from acsoe.platform.aio import run_blocking

__all__ = ["ExchangeEngine"]


def _failure(call: str, exc: KrakenError) -> FetchFailure:
    """Describe a failure for an operator, without ever carrying a credential.

    The client's exceptions carry the method and the path only — never a header, a
    body or a signed nonce — which is what makes ``str(exc)`` safe to publish here.
    """
    kind = "api_error" if isinstance(exc, KrakenAPIError) else "unavailable"
    return FetchFailure(call=call, kind=kind, reason=str(exc))


class ExchangeEngine(BaseEngine):
    """Balances, the live fee tier and the live pair rules, published into ``state``."""

    name: ClassVar[str] = "exchange"
    number: ClassVar[int] = 1
    #: Registry table in `context/engine-contracts.md` marks engine 1 with no Gate.
    #: `is_gate_matches_registry` asserts this exact value.
    is_gate: ClassVar[bool] = False

    # ARG002: `state` is unused and must stay in the signature — it is the fixed
    # interface in `context/engine-contracts.md` and the orchestrator calls it
    # positionally. That engine 1 reads nothing from `state` is the point: it is the
    # first engine of the first chain, so there is nothing in `state` yet to read.
    def process(self, context: EngineContext, state: State) -> EngineResult:  # noqa: ARG002
        started = time.perf_counter()
        now_micros = to_micros(context.now)

        pairs, fees, balances, failures = self._fetch(context)

        retained = self._retained_notes(context, now_micros)
        payload = ExchangeState(
            fetched_at=now_micros,
            balances=balances.state_dict()["balances"] if balances is not None else None,
            fee_tier=fees.state_dict() if fees is not None else None,
            pair_rules=pairs.state_dict() if pairs is not None else None,
            failed_fetches=tuple(failures),
            retained=tuple(retained),
        )

        return EngineResult(
            engine=self.name,
            # OK even when every fetch failed. A failed fetch is an expected outcome
            # here, not an unexpected one, and ERROR is defined as "unexpected
            # failure" and is treated as a block — which engine 1 must not be.
            status=EngineStatus.OK,
            blocks_trading=False,
            data=payload.to_state(),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    # ------------------------------------------------------------------ fetching

    def _fetch(
        self, context: EngineContext
    ) -> tuple[
        PairRulesSnapshot | None,
        FeeTierSnapshot | None,
        BalancesSnapshot | None,
        list[FetchFailure],
    ]:
        """One event loop for the tick's three calls, run concurrently.

        ``gather(..., return_exceptions=True)`` rather than three awaits, so a failing
        ``TradeVolume`` does not stop the balances from being fetched. One outage must
        not become three blanks in ``state`` — a consumer needs to know exactly which
        value it is missing: engine 10 `cost` quotes the named call and its reason in
        its block sentence, rather than the state key that is merely ``None``.
        """
        client = context.clients.kraken

        async def all_three() -> tuple[Any, ...]:
            gathered = await asyncio.gather(
                client.asset_pairs(),
                client.trade_volume(),
                client.balance(),
                return_exceptions=True,
            )
            return tuple(gathered)

        results = run_blocking(all_three())

        failures: list[FetchFailure] = []
        pairs: PairRulesSnapshot | None = None
        fees: FeeTierSnapshot | None = None
        balances: BalancesSnapshot | None = None

        for call, outcome in zip(CALLS, results, strict=True):
            if isinstance(outcome, KrakenError):
                failures.append(_failure(call, outcome))
                continue
            if isinstance(outcome, BaseException):
                # Not an exchange-shaped failure: a defect on our side of the
                # boundary. Contract rule 7 says an engine must not swallow its own
                # exceptions to avoid ERROR, so this one is re-raised and the
                # orchestrator turns it into ERROR with blocks_trading=True.
                raise outcome
            # Coerced into this system's own validated models, so the engine behaves
            # identically against the real client and against C's fake — whose
            # snapshots are separate dataclasses with the same field names.
            if call == "asset_pairs":
                pairs = coerce_pair_rules(outcome)
            elif call == "trade_volume":
                fees = coerce_fee_tier(outcome)
            else:
                balances = coerce_balances(outcome)

        return pairs, fees, balances, failures

    # ------------------------------------------------------------------ retention

    def _retained_notes(self, context: EngineContext, now_micros: int) -> list[RetainedNote]:
        """Report *that* a last-known-good value exists and how old it is.

        Never the value itself. Invariant 2: for trading, a stale value does not
        exist. Only rule 14's emergency liquidation may use one, and engines 21 and 22
        read it from the client directly in Phase 6 — publishing it here would put it
        one attribute lookup away from a gate that must never see it.

        The client is duck-typed rather than isinstance-checked, because the fake in
        ``tests/harness/`` is a different class exposing the same two properties, and
        an engine that only worked against the real client would be untestable.
        """
        client = context.clients.kraken
        notes: list[RetainedNote] = []
        for call, attribute in (
            ("asset_pairs", "last_known_good_asset_pairs"),
            ("balance", "last_known_good_balances"),
        ):
            retained = getattr(client, attribute, None)
            if retained is None:
                continue
            fetched_at = getattr(retained, "fetched_at", None)
            if not isinstance(fetched_at, int):
                continue
            notes.append(
                RetainedNote(
                    call=call,
                    fetched_at=fetched_at,
                    age_micros=(
                        retained.age_micros(now_micros)
                        if isinstance(retained, RetainedValue)
                        else now_micros - fetched_at
                    ),
                )
            )
        return notes
