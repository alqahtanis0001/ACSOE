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
- Break-even win rate: ~61% at tier 1, ~48% at tier 3.
- Decision bar 15 minutes; hold 2–12 hours; loop tick 1 minute.
- Triple-barrier labels: +3% / −1.5% / 48-bar timeout.
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

## Decisions taken after the Phase 0 audit

The lead's onboarding audit found 25 issues. These were resolved by the operator:

- `core/` holds contracts and the orchestrator only. Config, clock and logging moved to `platform/`, owned by A.
- The orchestrator has two chains. The opportunity chain may stop early; the always chain (21, 22, 19, 20) runs every tick. Without this, positions were never watched.
- `scripts/verify.py` is sequenced first in Phase 0 and reports PASS, FAIL or PENDING, so criteria can exist before the code they judge.
- Every criterion runs offline against a recorded artefact. `--live` is opt-in and never required for a phase to be green.
- Each agent owns `tests/` mirroring its own source paths, and its own `docs/build-log/phase-N/<agent>.md`.
- One working tree, one branch, no per-teammate branches. The ownership map is the only concurrency control. The lead commits at task boundaries; teammates do not commit.
- Timeout is 48 bars, which is 12 hours and consistent with the 2–12 hour horizon. It was 24 bars, which is 6.
- Break-even at tier 3 is ~48%, not 54%. The tier 1 figure of ~61% was correct.
- Engine 6 renamed `macro_context` to stop colliding with the `context/` directory.
- Engine 13 `anomaly` moved from B to C — it is a model engine built in Phase 5.
- The Dissimilarity Index lives inside `engines/prediction/`. The execution offset bandit lives inside `engines/execution/`. Neither is an engine.
- A `recorder` client was added to `Clients` so engine 2 can append JSONL without violating contract rule 4.
- Friction assumes maker entry and taker exit — the worst realistic case.
- Paper mode falls back to tier 1 on a failed fee fetch and logs it. Live mode still blocks.
- `config/LIVE_CONFIRMED` is compared against `context.now` in UTC.
- The lead authors `config/default.yaml`.

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
