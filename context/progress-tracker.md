# Progress Tracker

**Lead-only file.** Teammates write `context/progress/<agent>.md`. The lead merges here after a passing verify run.

## Current Phase

**Phase 0 — Structure.** Not started.

## Current Goal

Package skeleton, `core/` contracts, orchestrator, config, logging, injected clock, CLI, SQLite schema and migrations, store client, seed generator, fake Kraken client, test harness, `scripts/verify.py`, and `scripts/record.py`. No engines yet.

## Phase Status

A phase is green only when `python scripts/verify.py --phase N` passes every criterion.

| Phase | Status | Verified |
|---|---|---|
| 0 — Structure | Not started | — |
| 1 — Interface | Blocked on 0 | — |
| 2 — Data spine | Blocked on 1 | — |
| 3 — Economics | Blocked on 2 | — |
| 4 — Memory and replay | Blocked on 3 | — |
| 5 — Models | Blocked on 4 | — |
| 6 — Decision and execution | Blocked on 5 | — |
| 7 — Evaluation | Blocked on 6 | — |
| 8 — Live readiness | Blocked on 7 | — |

## Completed

- None yet.

## In Progress

- None yet.

## Next Up

- Phase 0. See the split in `context/ownership.md`.

## Locked Decisions

Settled with evidence. Do not relitigate. Changing one requires the operator, not an agent.

- Kraken Pro, spot only. No margin, futures, leverage, or shorting.
- Fees read live from `TradeVolume`. Minimums read live from `AssetPairs`. Never hardcoded.
- Reference friction: ~1.25% round trip at tier 1, ~0.65% at tier 3.
- Break-even win rate: ~61% at tier 1, ~54% at tier 3.
- Decision bar 15 minutes; hold 2–12 hours; loop tick 1 minute.
- Triple-barrier labels: +3% / −1.5% / 24-bar timeout.
- Post-only limit entry, cancel if unfilled, never chase.
- Tradable universe computed per tick from `ordermin`, `costmin`, tick size, live spread and balance. No account-size thresholds.
- All Kraken quote currencies scanned; crypto-quoted pairs disabled by default.
- DI fitted on the predictor's training set, MinMax-scaled, rolling percentile threshold, 30-day per-pair window.
- DI threshold crossings also feed the regime engine.
- Alpha attribution uses the full equity curve including cash periods, not trade windows.
- Execution offset bandit pooled by spread tier, not per pair.
- Promotion metric haircut for the number of models tried.
- Backtest training window capped at a rolling 90 days; retrains weekly during walk-forward.
- An LLM is not the predictor. Any alternative method must first clear the fee hurdle.
- Build order is structure, then interface, then backend.
- Console is built against the real schema with seeded fake data, so no rework when real data arrives.
- Paper mode until a validated model exists. A readiness gate, not an account-size gate.

## Open Questions

- None. Add here rather than guessing.

## Architecture Decisions

- Engines communicate only through `state`. No engine imports another.
- `context.now` is injected everywhere, so replay is faithful and look-ahead is structurally impossible.
- The memory engine runs after a block, outside the main loop, so rejections are never lost.
- Live loop code and `research/` never import from each other.
- Phase exit criteria are executable in `scripts/verify.py`, not a checklist anyone reads.

## Known Risks

- **Historical archives carry no order book or spread.** Engine 9 and the spread half of Engine 10 cannot be backtested before live recording began. `scripts/record.py` ships in Phase 0 for exactly this reason and must not be switched off.
- **A read-and-trade Kraken key exists on the dev machine.** Use a separate read-only key until Phase 8. The three live switches are the only thing between a bug and real money.
- **Every Kraken pair is a lot of pairs.** Develop against a config-limited subset; the universe filter handles the rest at runtime.
- **Building the interface before the backend risks guessing at data shapes.** Mitigated by fixing the schema in Phase 0 and seeding it. If a later phase needs a schema change, it goes through the lead and the console is updated in the same change.

## Session Notes

- Project starts from scratch. Any earlier ACSOE code was throwaway scaffolding and must not be carried over or referenced.
