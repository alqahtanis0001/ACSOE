# 87 — Rehearse engines 18, 21 and 22 through real orchestrator ticks

**Owner:** A — Platform

**Phase:** 6. A new file in A's lane, `tests/engines/test_trade_chain_rehearsal.py` — the
deliberate exception to "nobody writes a test for another agent's code", on the same terms as
Phase 3's guard-chain rehearsal and Phase 4's manage-chain rehearsal: it tests the **orchestrator
wiring**, not the engines.

## Goal

Before the lead registers 18, 21 and 22 (spec 82), an agent that did not build them drives them
through real `Orchestrator` ticks against a real `StoreClient`, the fake Kraken client at tier 3
and B's paper broker, with engine 19 recording. Registration becomes a formality rather than a
discovery.

## Implementation

1. Chains built by hand in the registry's relative order: opportunity ending 18, manage 21, 22,
   19. Every `state` an engine reads comes from the real upstream engines, never a hand-built
   payload (Phase 3 operator ruling).
2. Ticks, each a separate `tick()` call on one orchestrator: entry placed; entry filled on a later
   tick; position watched across quiet ticks; stop touched and exited; timeout reached and exited;
   an unfilled entry cancelled at `trading.entry_unfilled_window_s` and not replaced; a
   `data_guard`-blocked tick holding a triggered stop with `hold_reason` recorded; the same
   position exited once `close_intent` is set.
3. After every tick, read back what engine 19 wrote — `orders`, `positions`, `trades`,
   `equity_snapshots` — and assert it against what 18, 21 and 22 published, row for row.
4. At least one assertion per scenario that cannot be satisfied by an engine that raised: assert
   the status or the absence of `trading_blocked_by`, never `state[engine] == {}` alone.
5. Mutations, each from a byte copy with its hash compared in the same statement, and each verdict
   naming **which test** killed it: 21 holds on a non-`data_guard` block; 22 ignores
   `close_intent` during a hold; 21 replaces a cancelled entry; 18 skips the `userref` check.
   **If a scenario goes red for a real reason, do not fix engines 18, 21 or 22** — report to B and
   the lead.

## Scope Limits

- Do **not** edit any engine, the simulator, `bootstrap.py` or `core/`.
- Do **not** register anything.
- Do **not** assert three concurrent positions — the balance binds first at $5,000 (tracker).

## Check When Done

- Every scenario green on B's final code, every mutation red with its killing test named.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
