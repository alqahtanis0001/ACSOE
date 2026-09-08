# Ownership Map

One team lead and three teammates share a single task list. Ownership is **permanent, not per phase** — the same agent owns the same directories for the whole project. That is what stops two teammates editing one file.

Confirm you own a file before editing it. If you do not, escalate.

## Roster

| Agent | Owns | Heaviest in phases |
|---|---|---|
| **Lead** | `src/acsoe/core/`, `bootstrap.py`, `config/`, `context/*` except `progress/`, `feature-specs/`, all merges, all schema approvals | All |
| **A — Platform** | `pyproject.toml`, `src/acsoe/platform/`, `src/acsoe/cli/`, `scripts/`, `clients/kraken/`, `engines/exchange`, `market_data_recorder`, `market_sensor`, `data_guard`, `research/replay.py`, `research/historical.py` | 0, 2, 4 |
| **B — Store and trading** | `clients/store/`, `db/migrations/`, `engines/scout`, `cost`, `risk`, `safety`, `decision`, `execution`, `position_manager`, `exit` | 0, 3, 5, 6, 8 |
| **C — Interface and models** | `console/`, `tests/harness/`, `engines/feature`, `macro_context`, `prediction`, `regime`, `anomaly`, `order_book`, `adaptive_router`, `skeptic`, `memory`, `tournament`, `research/labelling.py`, `research/training.py`, `research/walkforward.py` | 0, 1, 4, 5, 6, 7, 8 |

Not every phase needs all three. Phase 1 is almost entirely C; Phase 3 is almost entirely B. Run the agents who have real work and let the others sit out — the ownership map is permanent, only the headcount per phase flexes. Never invent filler tasks. Nobody idles mid-phase: if you are waiting on another agent's interface, agree the contract, mock it, and keep building.

## Phase 0 split

| Agent | Task |
|---|---|
| **Lead** | `core/`: `BaseEngine`, `EngineContext`, `EngineResult`, `EngineStatus`, `State`, the two-chain orchestrator, the empty `bootstrap.py` registry, and `config/default.yaml` with every threshold named |
| **A** | Package skeleton, `pyproject.toml`, and `src/acsoe/platform/`: config loader and validation, `structlog` setup, the injected clock. Plus `acsoe engine` and `acsoe console` CLI entrypoints and `scripts/record.py` |
| **B** | SQLite schema and migrations, the store client, and the seed generator producing realistic fake trades, rejections, positions and leaderboard rows |
| **C** | `scripts/verify.py` **first**, then the test harness, the fake Kraken client with recorded fixtures, and shared pytest fixtures. Verify must exist before A and B can report anything complete |

`scripts/record.py` is deliberately in Phase 0 and deliberately dumb: a standalone WebSocket-to-JSONL recorder with no dependency on the engine framework. Order-book and spread history cannot be recovered retroactively, so it starts collecting on day one and is superseded by Engines 1 and 2 in Phase 2.

## Paths nobody was assigned

**Tests.** Each agent owns `tests/` mirroring the source paths it owns. If you own `engines/cost/`, you own `tests/engines/test_cost.py`. C owns `tests/harness/` and the shared fixtures. Nobody may write a test for another agent's code.

**Build log.** Each agent writes `docs/build-log/phase-N/<agent>.md`. The lead consolidates them into `docs/build-log/phase-N.md` at phase close. Three agents appending to one file has the same concurrent-write hazard as the tracker, and is solved the same way.

**Config.** The lead authors `config/default.yaml`. A owns the loader in `platform/`. A may request a config key; only the lead adds one.

## Version control

There is one working tree and one branch. Teammates run in-process in the same checkout — there is nothing to merge between them, so branches and worktrees would add ceremony without benefit.

**The ownership map is the only concurrency control.** Nothing enforces it mechanically. That is why rule 1 is absolute.

The lead commits at task boundaries with a message naming the spec number and owning agent. Teammates do not commit. The lead does not commit anything that fails `scripts/verify.py`.

## Rules

**1. Write only inside your own paths.** No exceptions, including one-line fixes.

**2. `core/` and `bootstrap.py` are lead-only.** Every new engine needs registering, and every registration goes through the lead. Batch your requests.

**3. Never write `context/progress-tracker.md`.** Write `context/progress/<agent>.md` — `a-platform.md`, `b-store.md`, `c-interface.md`. The lead merges. Concurrent writes to one tracker lose work.

**4. Schema changes go through the lead.** Anyone may read the tables; only B writes them; only the lead approves a change, because a mid-phase migration breaks everyone's fixtures.

**5. Claim before you start.** Claim on the shared list, record the spec number in your progress file, then begin. Never start a claimed task.

**6. Cross-cutting work is a lead task.** Anything touching all three owners' directories is not a teammate task. Hand it back.

**7. Reading is always allowed.** The restriction is on writes only.

**8. Talk to each other.** If you depend on another teammate's interface, message them directly. Do not route every question through the lead.

## Interfaces between agents

Agree the contract first, mock it, build against the mock.

| Seam | Producer | Consumer | Contract lives in |
|---|---|---|---|
| Raw ticks, pair rules, fee tier | A | B, C | `clients/kraken/contracts.py` |
| 15-minute candles | A | C | `engines/market_sensor/contracts.py` |
| Store read and write | B | A, C | `clients/store/contracts.py` |
| Database schema | B | C | `db/migrations/` |
| Seeded fixture data | B | C | `clients/store/seed.py` |
| Tradable universe | B | C | `engines/scout/contracts.py` |
| Feature vector | C | B | `engines/feature/contracts.py` |
| Prediction and DI | C | B | `engines/prediction/contracts.py` |
| Order intent | B | C | `engines/decision/contracts.py` |

A seam not in this table probably means the split is wrong. Raise it rather than reaching across.

## Conflict procedure

1. Stop. Do not force, overwrite, or resolve another agent's file.
2. Record it in your progress file.
3. Escalate to the lead with the path and both intents.
4. The lead decides and makes the edit.
