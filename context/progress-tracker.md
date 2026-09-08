# Progress Tracker

**Lead-only file.** Teammates write `context/progress/<agent>.md`. The lead merges here after a passing verify run.

## Current Phase

**Phase 0 — Structure.** Not started.

## Current Goal

`scripts/verify.py` first. Then the package skeleton, `core/` contracts and three-chain orchestrator, `platform/` config, clock, logging and live guard, CLI entrypoints, `config/default.yaml`, SQLite schema and migrations, store client, seed generator, fake Kraken client, test harness, and `scripts/record.py`. No engines yet.

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

## Decision history

Four onboarding audits, in order. Later sections override earlier ones where they conflict; superseded lines are struck through. The current design is always `engine-contracts.md` and `architecture-context.md` — this section is the record of how it got there.

### After the first audit

The lead's onboarding audit found 25 issues. These were resolved by the operator:

- `core/` holds contracts and the orchestrator only. Config, clock and logging moved to `platform/`, owned by A.
- ~~The orchestrator has three runtime chains: ingest (1–4), opportunity (5–18), manage (21, 22, 19).~~ **Superseded by the fifth audit** — the first chain is the *guard* chain and carries engine 17 as well: 1, 2, 3, 4, 17. The opportunity chain is 5–16 plus 18. Engines 20 and 23 still run in an offline chain via `acsoe research`. Without this split, positions were never watched, and freeze would have stopped the recorder.
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

### After the second audit

The lead's second audit found 22 issues, most of them decisions that had reached some files and not others. Resolved:

- `code-standards.md` corrected — config, clock and logging are in `platform/`, not `core/`.
- `core/` imports nothing. `Config`, `Clock` and `Clients` are Protocols declared in `core/contracts.py` and implemented in `platform/` and `clients/`.
- ~~Chain 2 is exactly three engines: 21, 22, 19.~~ **Superseded by the fourth audit** — there are now three runtime chains; see below. Engine 20 still runs offline.
- Paper-mode fallbacks are stated once, in a table, scoped to mode. Live mode always blocks. Fee falls back to tier 1; balance falls back to `paper.starting_balances`, a per-currency map; pair rules and spread have no fallback and block the pair.
- `clients/recorder/` exists and belongs to A.
- Per-task done is **no FAIL**. PENDING is expected mid-phase and only reaches zero at phase close.
- Every criterion must pass on a fresh clone. Evidence lives in committed fixtures under `tests/fixtures/`, never in gitignored `data/`. `--live` verifies the real run and is never required for green.
- `logs/` exists, belongs to A, and is gitignored.
- The command table has defined semantics and a reader: the orchestrator, in `core/`, at the top of every tick, marking each command consumed.
- The three-switch live check is `platform/live_guard.py`, A's. Three conditions, not three read paths.
- `feature-specs/` has a mandatory template, so Scope Limits is a defined section.
- C owns `tests/` root, `conftest.py` and `tests/fixtures/`. A creates `data/` and `logs/`.
- "Within one tick" means one `tick_size` from `AssetPairs`.
- `console.poll_interval_ms` must be under a quarter of `console.stale_after_ms`, enforced by config validation.
- ~~The eight non-ML engines are enumerated: 1, 2, 3, 4, 10, 11, 16, 17.~~ **Superseded by the third audit** — scout is deterministic, so there are nine and engine 7 is among them.
- `.claude/settings.local.json` and `logs/` restored to `.gitignore`.

### After the third audit

- `.gitignore` gained `!tests/fixtures/**`. Without it `*.jsonl` and `*.parquet` silently swallowed every committed fixture, and the entire fresh-clone verification strategy failed without an error message.
- The four phase criteria that depended on gitignored directories now name committed fixtures: `record_sample.jsonl`, `recording_report.json`, `labelled_sample.parquet`, `soak_digest.json`. The real runs moved behind `--live`.
- Engine 20 has a caller. A third `OFFLINE_CHAIN` is invoked by `acsoe research`, never by the daemon. Engine 23 runs there too.
- **Scout is deterministic.** Design question resolved: engine 7 contains no model — the universe filter is arithmetic and the ranking is a fixed score. It is therefore protected by invariant 4, and the non-ML count is nine, not eight. Engine 15 `skeptic` is the only model gate, and it can only veto.
- ~~`state["system_mode"]` is now an orchestrator key.~~ **Superseded by the fourth audit** — the persistent key is `state["system"]`, holding `mode` and `close_intent`.
- **The kill switch is `close_all`.** No fourth mechanism. Freeze stops new trades and keeps managing open ones; close_all ends exposure.
- The orchestrator mints `run_id` and `cycle_id`, and holds the `Clock`. Engines see only `context.now`.
- `paper.starting_balances` is a currency-to-amount map, not a scalar. One number cannot satisfy the per-quote-currency invariants.
- Creating a directory is not owning the runtime data written into it. Rule 1 governs source files.
- `console.poll_interval_ms` default dropped to 500 so the Phase 1 criterion is achievable; the criterion is now twice the poll interval.
- `is_gate` is asserted by `verify.py` against the registry table, so a mis-registered gate fails loudly.

### After the fourth audit

- **Freeze no longer stops the recorder.** ~~Engines 1–4 are now their own ingest chain.~~ **Renamed by the fifth audit** — it is the guard chain, 1, 2, 3, 4, 17. It runs in every mode; only the opportunity chain is switched off by freeze. Order-book history is never lost to a freeze.
- **The safety engine freezes via the commands table.** It cannot write `state["system"]`, so it writes a `freeze` or `close_all` row through the store, which the orchestrator consumes next tick. Same channel as the console, and every stop is an audit row.
- **State is fresh every tick.** The only persistent region is `state["system"]` — `mode` and `close_intent` — carried by the orchestrator. Manage-chain engines read prior decisions from the store, never from stale state keys.
- `close_intent` is the kill switch's data path. `frozen` alone means stop opening; `frozen` plus `close_intent` means liquidate now.
- `run_id` lives only on `context.run_id`. The duplicate state key is gone.
- Engine 23 is registered in `OFFLINE_CHAIN` only, which `cli/research.py` assembles. `bootstrap.py` never imports from `research/`, so invariant 5 holds.
- Each agent deposits its own evidence fixtures under `tests/fixtures/`; C owns the structure and shared fixtures.
- Anomaly is a data-quality gate (unsupervised, over market data) and stays protected. Skeptic is a learned opinion about the trade and stays excused. The distinction is now stated.
- `acsoe research` ships in Phase 0 as a stub.
- The stray empty code fence in `engine-contracts.md` is removed.

### After the fifth audit

The fifth audit found nine issues. Four of them were one question wearing four hats — what runs unconditionally, and who may write the persistent state — so they were resolved together rather than patched one at a time.

- **Engine 17 `safety` moved from the opportunity chain to the guard chain.** It was second to last in a chain that stops at the first block or PASS, so the circuit breaker only ever ran on ticks where every other gate had already passed. An account in drawdown whose candidates were all being rejected by the cost gate would never have tripped it. The guard chain is now 1, 2, 3, 4, 17, runs every tick in every mode, and never breaks early — a bad-data block must not stop safety from evaluating. Safety is stage 1 gatekeeping, not stage 3 judgement.
- **The guard chain records the first blocker, not the last.** Two guards can block on one tick; the reason `memory` logs is the first one.
- **Safety is idempotent about what it emits.** It runs every tick now, so it writes a command row only when that row would change the state: `freeze` only while running, `close_all` only when positions are open and no intent is already set. Otherwise a sustained drawdown would append a freeze row every sixty seconds forever.
- **`close_all` cancels resting entry orders as well as closing positions.** A post-only limit still on the book is not a position and survived the old definition, so the emergency stop could leave an order that filled minutes later and re-opened exposure. Engine 21 cancels, engine 22 closes.
- **The orchestrator clears `close_intent`, not engine 22.** The old wording had an engine writing `state["system"]`, which rule 2 and the state-keys section both forbid. Engines now report `entry_orders_cancelled` and `positions_closed` in their own `data`; the orchestrator clears the intent only when both are true, so a failed cancel or close retries next tick instead of being lost.
- **Command consumption is two-phase.** `claimed_at` when read, `consumed_at` when the effect completes. A daemon killed part-way through a liquidation used to restart with the command marked done, the in-memory intent gone and positions still open. Unconsumed rows are now re-applied at startup.
- **Mode always starts `idle` and is never restored from the store.** A crashed daemon comes back not trading, with the manage chain still watching what is open.
- **Engine 3 `market_sensor` owns the decision-bar clock.** It publishes `bar_closed`; engine 5 `feature` returns PASS when it is false. Nothing previously named which engine stopped the chain on a non-bar tick, which is the mechanism the entire cadence rests on.
- **`scripts/verify.py` may import both the live path and `research/`.** It is neither, which is what lets its `is_gate` assertion cover engines 20 and 23.
- **A `docs_vocabulary` criterion runs in every phase.** Every audit so far has found a decision that reached three files and not the fourth; each file stays self-consistent, so reading does not catch it and grep does. Retiring a term now includes adding it to the table in `ai-workflow-rules.md`.

### After the sixth audit

- **README said eight non-ML engines; it is nine.** `project-overview.md` had been corrected when scout was ruled deterministic, and the README had not. The `docs_vocabulary` check passed over it because a bare count is not a distinctive token, so `eight` used as a count of the engines without ML is now a retired term in its own right. A check that only catches renamed identifiers misses corrected facts.
- **Ownership's Phase 0 row for A listed two CLI entrypoints; the phase scope lists three.** A builds `acsoe engine`, `acsoe console`, and `acsoe research` as a stub reporting no offline engines until Phase 4.
- **The manage chain now holds when `data_guard` blocks.** Previously undecided: with the opportunity chain skipped but the manage chain still running, engine 22 could have exited a position on a target or stop computed from the same stale or negative-spread data the guard had just rejected — a fabricated trigger acting on real money. Engines 21 and 22 now place no exit on such a tick, still run so that engine 19 records it, and engine 21 reports `hold_reason`.
- **`close_intent` is the one exception, and the only deliberate override of a gate in the system.** An emergency stop proceeds regardless of the guard, because a bad fill is a smaller risk than unknown exposure. It overrides in the direction of less exposure, never more, which is why it does not violate invariant 4. Blocks from engines other than `data_guard` do not hold the manage chain: they concern whether a new trade is wise, not whether an open position's data is trustworthy.
- Phase 6 gained a criterion that proves both halves — a triggered stop does not exit on a `data_guard` tick, and the same position under `close_intent` does.

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
