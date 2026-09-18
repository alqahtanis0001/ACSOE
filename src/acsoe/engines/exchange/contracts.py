"""What engine 1 `exchange` publishes into ``state["exchange"]``.

The account picture: balances, the live fee tier, and the live pair rules. Read by
engine 10 `cost` and engine 11 `risk` (B), by engine 7 `scout`, and by the console.

Two properties of this payload matter more than its field list.

**Every money value is an exact decimal string.** ``EngineResult.data`` refuses a
``Decimal`` and *accepts* a ``float``, so the dangerous mistake is the reflexive
``float()`` cast on hitting the refusal — a fee published as ``0.0022`` arrives in
engine 10's hurdle comparison wrong in the fourth decimal, which is the magnitude
that gate works at. Everything here goes through ``money_text()``.

**A failed fetch is recorded, never defaulted.** `ordermin`, `costmin`, `tick_size`,
the fee tier and the balances are all absent — ``None`` — when their fetch failed,
and the failure is named in ``failed_fetches``. Engine 1 reports the failed call and
substitutes nothing, and invariant 2 — the place to read this rule rather than a
restatement of it here — leaves no paper-mode fallback anywhere in the system, so no
consumer substitutes either. Downstream, a gate handed ``None`` blocks, which is
invariant 3 working as intended.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict

__all__ = [
    "CALLS",
    "STATE_KEY",
    "ExchangeState",
    "FetchFailure",
    "RetainedNote",
]

#: The one key this engine writes into ``state``. Contract rule 2.
STATE_KEY: Final = "exchange"

#: The calls engine 1 makes every tick, in the order it makes them.
CALLS: Final = ("asset_pairs", "trade_volume", "balance")


class _Payload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FetchFailure(_Payload):
    """One call that did not answer this tick.

    ``kind`` distinguishes the two ways the exchange fails, because they mean
    different things to a reader even though both block: ``api_error`` is "we got an
    answer and it was no" — a 200 carrying a populated ``error`` array — and
    ``unavailable`` is "we did not get an answer".

    ``reason`` is written for an operator and **never carries a credential**. The
    client's exceptions carry the method and the path only, which is what makes that
    true here without this module having to redact anything.
    """

    call: str
    kind: str
    reason: str


class RetainedNote(_Payload):
    """A last-known-good value the client is still holding, and how old it is.

    Published so the console and the log can *see* that a retained value exists and
    how stale it has become. **It is not the value**, and nothing downstream may trade
    on it: invariant 2 says a stale value does not exist for trading, and only rule
    14's emergency liquidation may read the real thing — which it does from the
    client directly, in Phase 6, not from here.
    """

    call: str
    fetched_at: int
    age_micros: int


class ExchangeState(_Payload):
    """The whole of ``state["exchange"]``.

    ``balances``, ``fee_tier`` and ``pair_rules`` are ``None`` when their fetch failed.
    ``None`` is the honest answer and is distinguishable from every real value; a zero
    balance or an empty pair map would not be.
    """

    fetched_at: int
    balances: dict[str, str] | None = None
    fee_tier: dict[str, Any] | None = None
    pair_rules: dict[str, Any] | None = None
    failed_fetches: tuple[FetchFailure, ...] = ()
    retained: tuple[RetainedNote, ...] = ()

    @property
    def complete(self) -> bool:
        """True when all three fetches answered. Not a gate — a fact."""
        return not self.failed_fetches

    def to_state(self) -> dict[str, Any]:
        """The JSON-safe mapping that becomes ``state["exchange"]``.

        ``mode="json"`` rather than a hand-written dict so a field added to this model
        cannot be forgotten here, and so tuples become lists.
        """
        payload: dict[str, Any] = self.model_dump(mode="json")
        return payload
