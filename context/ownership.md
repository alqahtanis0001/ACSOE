# Ownership Map

One team lead and three teammates share a single task list. Ownership is **permanent, not per phase** — the same agent owns the same directories for the whole project. That is what stops two teammates editing one file.

Confirm you own a file before editing it. If you do not, escalate.

## Roster

| Agent | Owns | Heaviest in phases |
|---|---|---|
| **Lead** | `src/acsoe/core/`, `bootstrap.py`, `config/`, `context/*` except `progress/`, `feature-specs/`, all merges, all schema approvals | All |
| **A — Platform** | `pyproject.toml`, `src/acsoe/platform/`, `src/acsoe/cli/`, `scripts/` **except `scripts/verify.py`**, `clients/kraken/`, `clients/recorder/`, `logs/`, `data/`, `engines/exchange`, `market_data_recorder`, `market_sensor`, `data_guard`, `research/replay.py`, `research/historical.py`, `research/backtest.py` | 0, 2, 4 |
| **B — Store and trading** | `clients/store/`, `clients/paper/` (Phase 6, operator ruling 2026-09-16), `db/migrations/`, `engines/scout`, `cost`, `risk`, `safety`, `decision`, `execution`, `position_manager`, `exit` | 0, 3, 5, 6, 8 |
| **C — Interface and models** | `console/`, `scripts/verify.py`, `tests/harness/`, `engines/feature`, `macro_context`, `prediction`, `regime`, `anomaly`, `order_book`, `adaptive_router`, `skeptic`, `memory`, `tournament`, `research/labelling.py`, `research/training.py`, `research/walkforward.py`, `src/acsoe/modelling/` (Phase 5, operator ruling 2026-09-12: the leaf package both the engines and `research/` import) | 0, 1, 4, 5, 6, 7, 8 |

Not every phase needs all three. Phase 1 is almost entirely C; Phase 3 is almost entirely B. Run the agents who have real work and let the others sit out — the ownership map is permanent, only the headcount per phase flexes. Never invent filler tasks. Nobody idles mid-phase: if you are waiting on another agent's interface, agree the contract, mock it, and keep building.

## Phase 0 split

| Agent | Task |
|---|---|
| **Lead** | `core/`: `BaseEngine`, `EngineContext`, `EngineResult`, `EngineStatus`, `State`, the three-chain orchestrator (guard, opportunity, manage) including the two-phase command reader, the empty `bootstrap.py` registry, and `config/default.yaml` with every threshold named |
| **A** | Package skeleton, `pyproject.toml`, and `src/acsoe/platform/`: config loader and validation, `structlog` setup, the injected clock. Plus all three CLI entrypoints — `acsoe engine`, `acsoe console`, and `acsoe research` as a stub that reports no offline engines registered until Phase 4 — and `scripts/record.py` |
| **B** | SQLite schema and migrations — including `commands` with `claimed_at`/`consumed_at` and `block_records` — the store client, and the seed generator. **The seed is what Phase 3 tests `safety` against, because every one of `safety`'s inputs is written by engine 19, which is Phase 4.** It must therefore produce, as named fixtures and not incidentally: realistic trades, rejections and leaderboard rows; a run of consecutive `data_guard` block records longer than `safety.max_consecutive_data_blocks`; **at least one open position**; **at least one resting entry order**; an `equity_snapshots` series containing a drawdown past the configured limit; and a trailing run of losing `trades` past the loss-streak limit |
| **C** | `scripts/verify.py` **first**, then the test harness, the fake Kraken client with recorded fixtures, and shared pytest fixtures. Verify must exist before A and B can report anything complete |

`scripts/record.py` is deliberately in Phase 0 and deliberately dumb: a standalone WebSocket-to-JSONL recorder with no dependency on the engine framework. Order-book and spread history cannot be recovered retroactively, so it starts collecting on day one and is superseded by Engines 1 and 2 in Phase 2.

## Paths nobody was assigned

**`scripts/`.** A owns the directory and `scripts/record.py`; **C owns `scripts/verify.py`**. The permanent roster used to hand A all of `scripts/` while the Phase 0 split handed C `verify.py`, which is two agents owning one file. Verification is C's surface — C owns the test harness and the fixtures the criteria read — so `verify.py` sits with C, permanently, not just in Phase 0.

**`research/backtest.py`.** Engine 23 `backtest` lives in `research/` and appeared in no row
of the roster: A owns `replay.py` and `historical.py` there, C owns `labelling.py`,
`training.py` and `walkforward.py`, and the engine class itself was assigned to nobody.
**Assigned to A**, Phase 4, spec 55. A owns the replay it drives and `cli/research.py`, where
the offline chain is assembled and where engine 23 is registered — never in `bootstrap.py`.
The labelling and walk-forward modules it calls stay C's, and that is an ordinary agent seam,
recorded in the table below.

**The fill simulator.** Named in the Phase 6 scope row since the workflow file was written and in
no roster row — the same shape as `research/backtest.py`, and found the same way, by an audit
rather than by anything failing. **Assigned to B**, Phase 6, spec 88, and it lives in the **client
layer** at `src/acsoe/clients/paper/` with its tests at `tests/clients/paper/`.

The operator first ruled it under `engines/execution/` and **corrected that ruling on 2026-09-16**,
on finding what the correction rests on: a resting post-only entry fills on a *later* tick, which
only engine 21 sees, and exits fill in engine 22 — so under that home two engines forbidden by
contract rule 3 from importing it would each need their own copy of one fill rule. The client
layer is also where `architecture-context.md` says a mode difference belongs, which is what lets
engines 18, 21 and 22 run the same code in paper and live. A wraps it around `clients.kraken` in
`cli/engine.py` when the mode is paper, and never in live.

**Tests.** C owns the `tests/` root scaffolding, `tests/conftest.py`, the *structure* of `tests/fixtures/`, the shared fixtures, and `tests/harness/`. Beyond that, each agent owns `tests/` mirroring the source paths it owns.

**Evidence fixtures.** Each agent deposits the committed evidence for its own criteria under `tests/fixtures/`: A owns `record_sample.jsonl`, `recording_report.json` and `soak_digest.json`; C owns `labelled_sample.parquet`. Depositing an evidence file you produced is not writing in C's lane. If you own `engines/cost/`, you own `tests/engines/test_cost.py`. C owns `tests/harness/` and the shared fixtures. Nobody may write a test for another agent's code.

**Build log.** Each agent writes `docs/build-log/phase-N/<agent>.md`. The lead consolidates them into `docs/build-log/phase-N.md` at phase close. Three agents appending to one file has the same concurrent-write hazard as the tracker, and is solved the same way.

**Directories.** A creates `data/`, `logs/` and their subdirectories at startup, and owns that creation code. **Creating a directory is not owning the runtime data written into it.** B's store writes `data/db/` and `data/derived/`; C's snapshots write `data/derived/`; every engine writes `logs/`. Rule 1 governs source files, not runtime output.

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
| Raw JSONL recording | A | — | `clients/recorder/contracts.py` |
| Command table: Activate, Freeze, Close all | C writes, Lead reads | — | `clients/store/contracts.py` |
| Safety self-freeze rows on that same table | B writes, Lead reads | — | `clients/store/contracts.py` |
| Decision-bar tick (`bar_closed`) | A | C | `engines/market_sensor/contracts.py` |
| Close-all completion flags | B | Lead | `engines/position_manager/contracts.py`, `engines/exit/contracts.py` |
| Manage-chain hold (`hold_reason`) | B | C (19 `memory`, console) | `engines/position_manager/contracts.py` |
| Block records, and the outage count derived from them. **Consumed in Phase 3, produced in Phase 4 — Phase 3 reads the Phase 0 seed.** | C (19 `memory`) writes, B (17 `safety`) reads | — | `db/migrations/`, `clients/store/contracts.py` |
| Equity series, for `safety`'s drawdown. **Consumed in Phase 3, produced in Phase 4 — Phase 3 reads the Phase 0 seed.** | C (19 `memory`) writes | B (17 `safety`), C (20 `tournament`) | `db/migrations/`, `clients/store/contracts.py` |
| Closed trades, for `safety`'s loss streak. **Consumed in Phase 3, produced in Phase 4 — Phase 3 reads the Phase 0 seed.** | C (19 `memory`) writes | B (17 `safety`) | `db/migrations/`, `clients/store/contracts.py` |
| Open positions and resting orders, for `safety`'s escalation precondition. **Consumed in Phase 3, produced in Phase 4 — Phase 3 reads the Phase 0 seed.** | C (19 `memory`) writes | B (17 `safety`, 21, 22), C (console) | `db/migrations/`, `clients/store/contracts.py` |
| Last-known-good exchange values, retained for emergency liquidation only | A (`clients/kraken/`) | B (21 `position_manager`, 22 `exit`) | `clients/kraken/contracts.py` |
| Run record, written at startup, read for restart detection. **The console's test is whether a previous `runs` row exists, not whether two `run_id`s differ — `run_id` is UNIQUE, so they always differ.** | Lead (orchestrator) | C (console) | `clients/store/contracts.py` |
| Persisted system mode, so the console can render Running and Frozen rather than only the idle readings. **Consumed by the console, produced in Phase 2 — Phase 1 renders the idle readings only, because no daemon runs in Phase 1 and neither other state can occur.** Written by the command reader that already owns `state["system"]["mode"]`, never inferred from the `commands` trail. | Lead (`core/` command reader) writes the value, B migrates the column it lands in | C (console) | `db/migrations/`, `clients/store/contracts.py`, `context/ui-context.md` |
| Offline chain invocation | A owns `acsoe research` and engine 23 `backtest`; C owns engine 20 `tournament` | — | `cli/research.py` |
| Labelled decision bars, and the label window end the splitter purges on. **Produced and consumed in Phase 4.** | C (`research/labelling.py`) | A (23 `backtest`), C (`research/walkforward.py`) | `src/acsoe/research/labelling.py` |
| The archive under `data/historical/` and the replayed decision-bar series | A (`research/replay.py`, `scripts/`) | C (`research/labelling.py`) | `src/acsoe/research/historical.py` |
| 15-minute candles | A | C | `engines/market_sensor/contracts.py` |
| Store read and write | B | A, C | `clients/store/contracts.py` |
| Database schema | B | C | `db/migrations/` |
| Seeded fixture data | B | C | `clients/store/seed.py` |
| Tradable universe | B | C | `engines/scout/contracts.py` |
| Feature vector, `state["feature"]["pairs"][pair]`. **Produced and consumed in Phase 5.** | C (5 `feature`) | B (7 `scout`, the ranking), C (6, 8, 12, 13) | `engines/feature/contracts.py`, names in `modelling/features.py` |
| Prediction and DI, `state["prediction"]` | C | B (10 `cost` reads `expected_move_pct`), C (15 `skeptic`), Phase 6 (14) | `engines/prediction/contracts.py` |
| Model artefact directory, `models/<run_id>/`. B hands over a path; C's manifest says what is in it. **Consumed in Phase 5, produced in Phase 5 — spec 62 lands first.** | B (`StoreClient.model_run_dir`, `new_model_run_dir`) | C (`modelling/artefacts.py`, engines 8, 13, 15, `research/training.py`) | `clients/store/client.py`, `modelling/artefacts.py` |
| Leaderboard rows. **Produced in Phase 5, consumed in Phase 6 by engine 14 and in Phase 7 by the promotion gate.** | C (20 `tournament`) writes, through the store | C (14 `adaptive_router`, console), Phase 7 | `clients/store/contracts.py` |
| The ranking feature, `scout.rank_feature` and `scout.rank_descending`. Absent until the operator rules on spec 75's study; alphabetical meanwhile. | Lead (config) | B (7 `scout`, `rank_universe`) | `config/default.yaml`, `engines/scout/contracts.py` |
| The one shared arithmetic: features, DI, weights, artefact layout. | C (`modelling/`) | C (engines 5, 8, 13, 15), C (`research/training.py`) | `src/acsoe/modelling/` |
| Order intent | B | C | `engines/decision/contracts.py` |
| **Rejection reason codes.** Every gate emits a `reason_code`; the console maps it to operator prose. **A code absent from the map renders "No reason was recorded." — silently, with no error anywhere.** Widened 2026-09-16: **every engine that publishes a `reason_code` or a `hold_reason`**, not only the gates — 9, 14, 18, 21 and 22 all do and none of them is a gate, and a test walks every engine's contracts so the next missing code goes red instead of silent (spec 99). | C (`console/format.py`, `REASON_PROSE`) | B (gates 7, 10, 11, 13, 15, 16; engines 18, 21, 22), C (8, 9, 14; 19 `memory` writes `engine_errored` for an engine that raised, operator ruling 2026-09-16) | `src/acsoe/console/format.py` |
| The order surface: place, cancel and query an order, one shape in paper and live. **Produced and consumed in Phase 6; the live half refuses until Phase 8.** | A (84) | B (88 the paper broker, 91, 92, 93) | `clients/kraken/contracts.py` |
| Per-tick trade range per pair — the low, high and count since the previous tick, which is what a fill and a barrier touch between one-minute ticks are decided on. **Phase 6.** | A (3 `market_sensor`, 85) | B (88, 92, 93) | `engines/market_sensor/contracts.py` |
| The paper broker's constructor, so the CLI can wrap the Kraken client in paper mode. **Phase 6.** | B (88) | A (86, `cli/engine.py`) | `src/acsoe/clients/paper/` |
| The rows engines 18 and 22 publish for the single writer to record — placements, exit orders, closed positions. **Phase 6.** | B (91, 93) | C (19 `memory`, 98) | `engines/execution/contracts.py`, `engines/exit/contracts.py`, `engines/memory/contracts.py` |
| The order intent: one typed record engine 18 reads instead of five engines' keys. **Phase 6.** | B (16 `decision`, 90) | B (18 `execution`, 91), C (console) | `engines/decision/contracts.py` |
| The committed order-book fixture engine 9 is validated on, cut from the live archive. **Phase 6.** | A (`scripts/cut_book_fixture.py`, 86) cuts, C deposits and owns | C (9 `order_book`, 96) | `tests/fixtures/book_sample.jsonl` |
| The primary blocker's status, `state["block_status"]` (`BLOCK` or `ERROR`), so engine 19 records an errored opportunity-chain engine as a block record rather than losing the tick. **Phase 6, 2026-09-16.** | Lead (`core/` orchestrator) | C (19 `memory`) | `context/engine-contracts.md` |
| The committed leaderboard fixture carrying at least two models, because `data/db/` is gitignored and engine 20 has written no persisted row. **Phase 6.** | C (97) | C (14 `adaptive_router`, its criterion) | `tests/fixtures/leaderboard_sample.json` |

A seam not in this table probably means the split is wrong. Raise it rather than reaching across.

## Conflict procedure

1. Stop. Do not force, overwrite, or resolve another agent's file.
2. Record it in your progress file.
3. Escalate to the lead with the path and both intents.
4. The lead decides and makes the edit.
