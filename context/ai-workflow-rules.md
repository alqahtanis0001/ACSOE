# Development Workflow

## Approach

Spec-driven and phase-gated. `feature-specs/` defines what to build, context files define how, `progress-tracker.md` defines where we are. Implement against the specs — never infer trading behaviour from scratch.

**`feature-specs/` starts empty.** The first action of every phase is the lead writing that phase's specs from its row below, then getting operator approval. Nothing is built before specs exist.

## Build order

**Structure, then interface, then backend.**

The interface is built early, against the real database schema populated with seeded fake rows. When the backend later fills that same schema with real data, the console works without changes. This is why Phase 0 creates the schema and the seed generator before anything else.

## How scripts/verify.py works

Each criterion prints one of three results:

- **PASS** — checked and satisfied
- **FAIL** — checked and not satisfied
- **PENDING** — the thing it checks does not exist yet

A phase is green only when every criterion is PASS and none are PENDING. PENDING is what lets Agent C write the criteria before A and B have built the things they judge, which is why `verify.py` is sequenced first in Phase 0.

Every criterion must run offline with no network and no API key, and **must pass on a fresh clone**. `data/`, `models/` and `logs/` are gitignored, so a criterion may never depend on anything inside them.

Where a criterion concerns live or long-running behaviour, it checks a small **committed** artefact under `tests/fixtures/` — a redacted JSONL sample, a gap report, a run-log digest — produced by the real run and checked in. The real run is verified by `--live`, which is opt-in and never required for a phase to be green.

A criterion that only passes on the machine that produced it is a broken criterion.

Phase 0 has no preflight — there is no phase −1.

## The feature-spec format

Every spec in `feature-specs/` uses exactly this shape. The lead does not invent a variant.

```markdown
# NN — <title>

**Owner:** <agent>

## Goal
One or two sentences. What exists at the end that did not exist before.

## Implementation
Numbered steps naming real file paths. No code.

## Scope Limits
What this spec must NOT do. Never empty. This is the section that
stops an agent widening the work, so it is the most important one.

## Check When Done
Concrete checks, ending with:
pytest tests/ -q · mypy --strict src/ · ruff check src/ · python scripts/verify.py --phase N
```

## Phases are gates

Nine phases, in order. **A phase is done when `python scripts/verify.py --phase N` passes every criterion**, not when it looks finished. Never start later-phase work, even when blocked.

| Phase | Scope | Verified by |
|---|---|---|
| **0 — Structure** | `scripts/verify.py` first. Then package skeleton, `core/` contracts and two-chain orchestrator, `platform/` config, logging and injected clock, CLI entrypoints, `config/default.yaml`, SQLite schema and migrations, store client, seed data generator, fake Kraken client, test harness, `scripts/record.py` | Orchestrator runs an empty registry cleanly; a fresh database migrates from empty; seed generator produces a queryable database of realistic trades and rejections; `scripts/record.py` has produced a JSONL artefact on disk that parses and validates; `pytest`, `mypy --strict`, `ruff` all green |
| **1 — Interface** | The full console against seeded data: status band, positions, cycle feed, history, research views, WebSocket updates, three commands | Console starts and renders every screen from the seeded database; WebSocket pushes an update within one second of a database change; Activate, Freeze and Close-all each write a correct command row; live-mode frame renders amber and paper does not; no raw hex outside the token block; tabular figures on every numeric column; keyboard focus visible; `prefers-reduced-motion` respected |
| **2 — Data spine** | Engines 1, 2, 3, 4; historical OHLCVT loader; recorder engine supersedes `scripts/record.py` | `data/raw/` contains a continuous recording spanning at least 24 hours with a gap report accounting for every break; built 15m candles match a committed Kraken OHLC fixture for three pairs, every OHLC field within one `tick_size` for that pair as reported by `AssetPairs`, and volume within 0.1%; data guard blocks on injected stale, negative-spread and missing-candle data; historical loader ingests one pair's full archive and reports gap statistics; console shows live data replacing seeds |
| **3 — Economics** | Engines 7, 10, 11, 17. Zero ML | Cost engine computes net edge from the fee tier returned by the fake Kraken client rather than a constant, and blocks below hurdle; risk engine rejects a sub-`ordermin` position rather than rounding up; universe filter yields different pair counts at $10 and $5,000 balances; safety engine freezes on injected drawdown; each has a block test and a pass test |
| **4 — Memory and replay** | Engine 19 real implementation; Engine 23 replay and triple-barrier labelling | Six months of 15m CSVs replay into a labelled dataset; a committed fixture of 20 hand-verified labels is asserted against by the labeller; purged walk-forward splitter produces folds with no label-window overlap across boundaries; rejections persist and survive a restart; console history reads real rows |
| **5 — Models** | Engines 5, 6, 8, 12, 13, 15, plus the DI inside `engines/prediction/` | Predictor trains and produces calibrated probabilities; DI fitted on the predictor's training set with a rolling percentile threshold; skeptic trains only on predictor BUY rows; full walk-forward with weekly retraining completes and reports out-of-sample metrics |
| **6 — Decision and execution** | Engines 9, 14, 16, 18, 21, 22; fill simulator | One complete paper trade end to end through all four gates: post-only entry, simulated fill, minute-by-minute watch, exit on each of target, stop and timeout, all logged; an unfilled entry cancels and abandons without chasing; console shows the position live |
| **7 — Evaluation** | Engine 20, attribution, deflated metric, promotion gate | Three-month paper backtest emits an alpha-versus-benchmark report from the full equity curve including cash periods; promotion gate rejects a model whose edge does not survive the trial haircut; research screens render the leaderboard and SHAP view |
| **8 — Live readiness** | Live guard, kill switch, soak test | All three live switches proven individually required; kill switch halts a running loop within one tick and closes nothing it should not; a run log covers at least 7 continuous days in paper with zero unhandled exceptions; no secret appears in any log, artefact, or committed file |

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
4. `python scripts/verify.py --phase N` reports **no FAIL**. PENDING is expected mid-phase and only has to reach zero at phase close.
5. No invariant is violated.
6. The engine's `README.md` is written and accurate.
7. `context/progress/<agent>.md` reflects reality.
8. `docs/build-log/phase-N/<agent>.md` records every non-trivial problem and its fix.
9. Any context file the implementation contradicted has been corrected.

## Keeping docs in sync

Update the relevant context file in the same change whenever implementation alters architecture, storage, contracts, conventions, or scope. Progress files record actual state, never intended state.
