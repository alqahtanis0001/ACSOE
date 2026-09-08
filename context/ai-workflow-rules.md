# Development Workflow

## Approach

Spec-driven and phase-gated. `feature-specs/` defines what to build, context files define how, `progress-tracker.md` defines where we are. Implement against the specs — never infer trading behaviour from scratch.

## Build order

**Structure, then interface, then backend.**

The interface is built early, against the real database schema populated with seeded fake rows. When the backend later fills that same schema with real data, the console works without changes. This is why Phase 0 creates the schema and the seed generator before anything else.

## Phases are gates

Nine phases, in order. **A phase is done when `python scripts/verify.py --phase N` passes every criterion**, not when it looks finished. Never start later-phase work, even when blocked.

| Phase | Scope | Verified by |
|---|---|---|
| **0 — Structure** | Package skeleton, `core/` contracts, orchestrator, config, logging, injected clock, CLI entrypoints, SQLite schema and migrations, store client, seed data generator, fake Kraken client, test harness, `scripts/verify.py`, `scripts/record.py` | Orchestrator runs an empty registry cleanly; a fresh database migrates from empty; seed generator produces a queryable database of realistic trades and rejections; `scripts/record.py` writes valid JSONL from live Kraken; `pytest`, `mypy --strict`, `ruff` all green |
| **1 — Interface** | The full console against seeded data: status band, positions, cycle feed, history, research views, WebSocket updates, three commands | Console starts and renders every screen from the seeded database; WebSocket pushes an update within one second of a database change; Activate, Freeze and Close-all each write a correct command row; live-mode frame renders amber and paper does not; no raw hex outside the token block; tabular figures on every numeric column; keyboard focus visible; `prefers-reduced-motion` respected |
| **2 — Data spine** | Engines 1, 2, 3, 4; historical OHLCVT loader; recorder engine supersedes `scripts/record.py` | Recorder runs 24h unattended with no crash and no unexplained gap; built 15m candles match Kraken's OHLC endpoint exactly for three sample pairs; data guard blocks on injected stale, negative-spread and missing-candle data; historical loader ingests one pair's full archive and reports gap statistics; console shows live data replacing seeds |
| **3 — Economics** | Engines 7, 10, 11, 17. Zero ML | Cost engine computes net edge from a live-fetched fee tier and blocks below hurdle; risk engine rejects a sub-`ordermin` position rather than rounding up; universe filter yields different pair counts at $10 and $5,000 balances; safety engine freezes on injected drawdown; each has a block test and a pass test |
| **4 — Memory and replay** | Engine 19 real implementation; Engine 23 replay and triple-barrier labelling | Six months of 15m CSVs replay into a labelled dataset; labels verified by hand on 20 sampled rows; purged walk-forward splitter produces folds with no label-window overlap across boundaries; rejections persist and survive a restart; console history reads real rows |
| **5 — Models** | Engines 5, 6, 8, the DI, 15, 12, 13 | Predictor trains and produces calibrated probabilities; DI fitted on the predictor's training set with a rolling percentile threshold; skeptic trains only on predictor BUY rows; full walk-forward with weekly retraining completes and reports out-of-sample metrics |
| **6 — Decision and execution** | Engines 9, 14, 16, 18, 21, 22; fill simulator | One complete paper trade end to end through all four gates: post-only entry, simulated fill, minute-by-minute watch, exit on each of target, stop and timeout, all logged; an unfilled entry cancels and abandons without chasing; console shows the position live |
| **7 — Evaluation** | Engine 20, attribution, deflated metric, promotion gate | Three-month paper backtest emits an alpha-versus-benchmark report from the full equity curve including cash periods; promotion gate rejects a model whose edge does not survive the trial haircut; research screens render the leaderboard and SHAP view |
| **8 — Live readiness** | Live guard, kill switch, soak test | All three live switches proven individually required; kill switch halts a running loop within one tick and closes nothing it should not; system runs 7 days unattended in paper without intervention; no secret appears in any log, artefact, or committed file |

## Scoping

One engine or one subsystem at a time. Small verifiable increments. If a change cannot be verified end to end quickly, split it.

Split a step if it combines:

- An engine and the client it depends on
- Live loop code and research code
- More than one owner's directories
- Anything not clearly specified in `feature-specs/`

## Escalate, do not edit

Stop and escalate if the work requires:

- Changing `src/acsoe/core/` or `bootstrap.py` and you are not the lead
- Adding, removing, or reordering an engine
- Changing `trading-invariants.md` or `engine-contracts.md`
- A dependency not listed in `architecture-context.md`
- Changing a schema another agent writes to

## Missing or ambiguous requirements

Never invent trading behaviour. Add an open question to `context/progress/<agent>.md` and stop that unit. Being blocked is better than guessing at financial logic.

## Definition of done for a task

1. Works end to end within its stated scope.
2. Tests exist, including a block test and a pass test for any gate.
3. `pytest`, `mypy --strict`, and `ruff check` are green.
4. `python scripts/verify.py --phase N` passes.
5. No invariant is violated.
6. The engine's `README.md` is written and accurate.
7. `context/progress/<agent>.md` reflects reality.
8. `docs/build-log/phase-N.md` records every non-trivial problem and its fix.
9. Any context file the implementation contradicted has been corrected.

## Keeping docs in sync

Update the relevant context file in the same change whenever implementation alters architecture, storage, contracts, conventions, or scope. Progress files record actual state, never intended state.
