# Architecture Context

## Stack

| Layer | Technology | Role |
|---|---|---|
| Language | Python 3.11+ | Whole system |
| Exchange transport | `websockets`, `httpx`, `tenacity` | Kraken WebSocket v2 and REST |
| Contracts | `pydantic` v2 | Engine results, config, external input validation |
| Dataframes | `polars` | Candle building, features, replay |
| Numerics | `numpy` | Indicators, distances, sizing |
| Models | `lightgbm`, `scikit-learn` | Predictor, skeptic, anomaly, calibration |
| Regimes | `hmmlearn` | Optional upgrade over rule-based regimes |
| Explanations | `shap` | Per-decision feature attribution |
| Statistics | `statsmodels` | Alpha versus benchmark attribution |
| Relational store | `sqlite3` (stdlib) | Trades, rejections, runs, leaderboard |
| Columnar store | `pyarrow`, `duckdb` | Feature snapshots, recordings, analysis |
| Serialization | `orjson` | Recording hot path |
| Model artefact serialisation | `joblib` | The one non-text artefact, the anomaly detector's isolation forest, which scikit-learn has no text dump for. Declared directly because engine 13 loads it on the live loop path; a transitive dependency that vanished would break a gate at load with nothing here to explain it. The manifest's sha256 over the file defends a swapped file, not a hostile original: unpickling executes, so never load an artefact from an untrusted source |
| Config parsing | `pyyaml` | `config/default.yaml`. **`yaml.safe_load` only, never `yaml.load`** |
| Console | `fastapi`, `uvicorn` | Local read-only dashboard |
| Logging | `structlog` | Structured JSON logs |
| Tests | `pytest`, `pytest-asyncio`, `hypothesis` | Unit and property tests |

Target OS is Windows. Any path handling must use `pathlib`, never string concatenation or hardcoded separators.

## Repository layout

```
src/acsoe/
  core/                 contracts, orchestrator only                     [LEAD ONLY]
  platform/             config, clock, logging, live_guard                [AGENT A]
  bootstrap.py          engine registry and wiring                       [LEAD ONLY]
  engines/
    <engine_name>/
      engine.py         the BaseEngine subclass
      contracts.py      pydantic models for this engine's output
      README.md         what it does, inputs, outputs, gate behaviour
  clients/
    kraken/             REST client, WebSocket client, rate limiter   [AGENT A]
    store/              SQLite and Parquet access                     [AGENT B]
    recorder/           append-only raw JSONL writer                  [AGENT A]
  research/             offline only: labelling, training, walk-forward
  modelling/            leaf package: feature arithmetic, artefact manifest,   [AGENT C]
                        DI arithmetic, sample weights. Imported by BOTH the
                        engines and research/; imports nothing but core types
  console/              FastAPI app, static assets
  cli/                  acsoe engine, acsoe console, acsoe research entrypoints
scripts/
  verify.py             executable phase exit criteria
  record.py             standalone day-one recorder, no framework deps
db/
  migrations/           SQLite schema, forward-only
logs/                   structlog JSON output, rotated daily          [AGENT A]
docs/
  build-log/
    phase-N/            one file per agent, written as they work
    phase-N.md          the lead's consolidation at phase close
config/
  default.yaml          paper mode, all thresholds
data/
  raw/                  append-only live recordings (JSONL, daily rotation)
  historical/           Kraken OHLCVT CSV archives
  derived/              built candles, feature snapshots (Parquet)
  db/                   acsoe.sqlite
models/                 trained artefacts, versioned by run id
tests/
context/
```

Every engine lives in its own directory. Never collapse engine logic into a shared module.

## The four stages of the runtime loop

**These are stages, not phases.** "Phase" always means a build phase from `ai-workflow-rules.md` (0 to 8). "Stage" always means a step in the runtime loop (1 to 4). Never use the two words interchangeably — build Phase 3 is the economics engines, runtime Stage 3 is judgement, and they are unrelated.

| Stage | Engines | Runs |
|---|---|---|
| 1. Ingestion and gatekeeping | 1, 2, 3, 4, 17 | Every tick, every mode |
| 2. Screening | 5, 6, 7 | On each closed 15-minute bar |
| 3. Judgement | 8–16 | On the candidate only |
| 4. Execution, management, learning | 18 on a new trade; 21, 22, 19 every tick | 18 with a candidate; manage chain always |

Engine 17 `safety` is stage 1, not stage 3. It is a gatekeeper on the account, not a judgement about a candidate, so it runs in the guard chain on every tick in every mode. See `engine-contracts.md`.

Engine 23 runs offline and is never invoked by the live loop.

## Timeframes

Three distinct concepts. Do not conflate them.

- **Decision bar: 15 minutes.** Features and labels are computed on closed 15-minute candles. New candidates are only born when a bar closes.
- **Holding horizon: 2 to 12 hours.** Target +3%, stop −1.5%, timeout after 48 bars.
  **The timeout barrier is a time, not a count of rows**, and the two are only the same thing
  on a series with no holes. 48 bars means `decision_bar_ts + 48 x decision_bar_s`; a walk
  visits whatever candles exist inside that window and stops at its end. Counting rows instead
  stretches a 12-hour horizon into a multi-day one across precisely the quiet periods the
  archives refuse to interpolate away, and the label built from it is a fabricated outcome.
  Ruled by the lead 2026-09-11, spec 52. This file is the authority for it; other files point
  here rather than restating it.
- **Loop tick: 1 minute.** Manages open positions and entry orders. Never generates new signals.

## Data sources

### Historical (training)

Kraken's downloadable OHLCVT archives, loaded from `data/historical/`. They provide 15-minute CSVs covering full trading history.

Two properties that must be handled explicitly:

- **Gaps are real.** The archives only contain intervals where trades occurred. A missing candle means no trades, not a data error. Never interpolate a missing candle into existence — mark it and let the feature layer decide.
- **No book, no spread.** The archives are OHLCVT only. Bid, ask, depth, and spread do not exist in them.
- **No intra-bar ordering.** A candle whose high reaches the target and whose low reaches the
  stop does not say which came first, and nothing in the archive can recover it. **The label
  is `stop`.** Ruled by the lead 2026-09-11, spec 52, and flagged to the operator as
  overturnable. The favourable reading would invent the ordering on exactly the bars where the
  market was most violent, and a model trained on that learns an edge that does not exist; the
  pessimistic reading is the only one that cannot flatter the strategy. The labeller reports
  how many labels were decided this way, because a slice where that count is large is a slice
  whose labels are mostly an assumption.

### Live (recording)

Kraken WebSocket v2, recorded append-only to `data/raw/`.

**Order book and spread data can only be gathered going forward and can never be recovered retroactively.** `scripts/record.py` ships in Phase 0 and must run continuously from the day Phase 0 closes, regardless of what else is being built.

### The consequence

Engine 9 (order book) and the spread component of Engine 10 cannot be backtested from the historical archives. Any backtest covering periods before live recording began must either exclude those engines or model their inputs from an explicitly documented proxy. A backtest that silently assumes zero spread is invalid.

**Phase 5 features are computed from the historical archive only.** The archive is OHLCVT and carries no spread, bid or ask — those exist only in the live recording, so a feature that reads them will not reproduce in replay.

## Storage model

| Data | Store | Notes |
|---|---|---|
| Raw market recordings | JSONL in `data/raw/` | Append-only, daily rotation, compacted to Parquet |
| Built candles, feature snapshots | Parquet in `data/derived/` | Rebuildable from raw |
| Trades, rejections, runs, leaderboard | SQLite | Small, relational, queried constantly |
| Open and closed positions | SQLite, table `positions` | What the console renders and what `safety` counts |
| Orders, including resting entries | SQLite, table `orders` | Keyed by `userref`; a resting post-only buy lives here |
| Equity series | SQLite, table `equity_snapshots` | One row per tick. Feeds `safety`'s drawdown and the Phase 7 alpha curve, which needs cash periods too |
| Block records | SQLite, table `block_records` | One row per guard blocker per **tick**. Not a column on `rejections` — see below |
| Trained models | Files in `models/` | Versioned by training run id, never overwritten |
| SHAP explanations | Parquet, joined by decision id | One row per decision |

Never put large arrays in SQLite. Never put relational records in Parquet.

### Trained artefacts: `models/<run_id>/`

One directory per training run, written once and **never overwritten**; the store client
refuses an existing directory. Each holds `manifest.json` (the run id, the config digest, every
seed, the feature version, **the ordered feature list**, the scaler as JSON, the fold bounds, the
dataset provenance, the metrics and a sha256 per file) beside the model files. The layout is
read and written by `modelling/artefacts.py` only, and an engine reaches it only through
`context.clients.store.model_run_dir(run_id)`, never by building a path. A model without its
exact feature order is unusable, and a run that cannot be reproduced from its config plus its
data is not a result. Engines 8, 13 and 15 load the run named in `models.*_run_id` and block
when it is absent, which is what a fresh clone with no `models/` does.

### Two records, two writers, and neither is derived from the other

**The archive and the store are separate.** Neither is built from the other and neither can be rebuilt from the other.

| | What it records | Its one writer |
|---|---|---|
| **The archive** — JSONL in `data/raw/` and `data/summaries/` | What the **market** did | `scripts/record.py` |
| **The store** — SQLite | What the **system decided** | Engine 19 `memory` |

The archive is an observation: it would contain exactly the same bytes if this system had never placed an order, and it keeps being written in `idle` and `frozen` because an hour not recorded is an hour of cost-model input that money cannot buy back. The store is a judgement: every row in it is something this system chose, including — especially — every candidate it refused.

**The offline chain is the one place they meet, and it meets them in one direction.** Engine 23 `backtest` *reads* the archive, replays it through the engines, and its decisions are written by engine 19 `memory` like any other run's, distinguished by `run_id`. That is the whole of the relationship: archive in, store rows out, through the ordinary writer. A replay never writes to the archive — invariant 11, a recording is immutable — and nothing in the store is ever the source of an archive line. Engine 20 `tournament` reads the store only and never touches the archive at all.

**Nothing else writes to either.** Any comparison *between* them is therefore an offline script that reads both and writes neither. That is why `scripts/reconcile_universe.py` and `scripts/reconcile_spread.py` are scripts and not engines: an engine that reconciled the two would need read access to both and would sit in a chain whose every other member has exactly one of them, and the first time it wrote a row to record what it found, the single-writer rule would be gone. A script cannot make that mistake, because it has no `state` to write into and no place in a registry.

*Where this stands today:* engine 23 is built and replays `data/historical/`, producing a labelled slice in `data/derived/`; engines 5 to 16 do not exist, so a replay does not yet run decisions through the chain and therefore does not yet produce store rows. The rule above is the design the Phase 6 and Phase 7 work is held to, and it is written here now because the two reconciliation scripts are the first things to read across the boundary.

### Why `block_records` is its own table

A rejection is one *candidate* refused, with its reason and its SHAP row. A block record is one *tick* on which trading was blocked, and most blocked ticks never had a candidate at all — `data_guard` blocks before the opportunity chain has run. Folding blocks into `rejections` would mean writing candidate-less rejection rows, inflating the counterfactual dataset that is the point of the whole exercise: anyone counting refused trades would be counting feed outages too.

They join on `cycle_id`. A blocked tick that *did* have a candidate produces one row in each.

Engine 17 `safety` derives its outage count from this table, so the columns are fixed:

| Column | Purpose |
|---|---|
| `cycle_id` | Integer, minted per tick and restarting at 1 each run |
| `run_id` | The daemon process |
| `ts` | `context.now`, UTC, microseconds since epoch |
| `blocked_by` | Engine name |
| `block_reason` | The reason string |
| `is_primary` | True for the blocker that set `state["trading_blocked_by"]` — the first one. False for a co-occurring blocker on the same tick |
| `status` | `BLOCK` or `ERROR`. `safety`'s error rate counts the `ERROR` rows in the trailing hour |

**A tick is identified by `(run_id, cycle_id)`, never by `cycle_id` alone.** `cycle_id` is an integer that restarts at 1 with each process, so it is unique only within a run. Every join to `rejections`, to logs and to SHAP rows uses both columns, and every uniqueness constraint that means "once per tick" is scoped to the pair. A constraint on `cycle_id` alone would reject a database holding two runs — which is the normal case, and is exactly what the Phase 0 seed contains.

**Order by `ts`, never by `cycle_id`.** `cycle_id` is minted per tick within a run and restarts with the process, so ordering a cross-restart sequence by it silently interleaves two runs. The outage counter has to survive a restart, which is precisely the case that would break.

Because the guard chain records every blocker, the outage count is **the number of consecutive most-recent `cycle_id`s that have any `data_guard` row**, not the number of rows. A tick where `data_guard` and `safety` both blocked contributes one to the count, not two.

### Engine 19 `memory` is the single writer of relational rows

`trades`, `positions`, `orders`, `equity_snapshots`, `block_records` and `rejections` are all written by engine 19 `memory`, from `state`, in the manage chain. No other engine writes a relational row. Engine 22 `exit` closes a position on the exchange; `memory` records that it happened. Keeping one writer is what makes the manage chain's "always runs" guarantee sufficient for invariant 12, and it is why `memory` is the dependency under `safety`'s entire input surface.

Money columns are stored as **exact decimal strings in TEXT**, never `REAL`. `Decimal` in, `Decimal` out. A float equity series drifts, and a drifting equity series moves the drawdown threshold that freezes the account — see invariant 14 for why that limit freezes rather than liquidates.

### What engine 17 `safety` reads

`safety` runs in the guard chain, *before* the manage chain, and `state` is fresh every tick — so `state["position_manager"]` and `state["exit"]` do not exist when it runs. Every input comes from the store. These are fixed, because `safety` is the circuit breaker and an ambiguous input is a breaker that two agents implement two ways:

| Input | Table | Fields | Written by | Built in |
|---|---|---|---|---|
| Equity drawdown | `equity_snapshots` | latest row: `equity`, `peak_equity`; drawdown is `(peak_equity − equity) / peak_equity` | 19 `memory` | Phase 4 |
| Consecutive losses | `trades` | trailing run ordered by `closed_at`: `realised_pnl`, `outcome` | 19 `memory` | Phase 4 |
| Error rate | `block_records` | rows in the trailing hour with `status = 'ERROR'` | 19 `memory` | Phase 4 |
| Open positions | `positions` | count where `status = 'open'` | 19 `memory` | Phase 4 |
| Resting entry orders | `orders` | count where `status = 'resting'` | 19 `memory` | Phase 4 |
| Consecutive data blocks | `block_records` | trailing consecutive `cycle_id`s with a `data_guard` row, ordered by `ts` | 19 `memory` | Phase 4 |

**Every one of those producers is Phase 4, and `safety` is built in Phase 3.** That is a forward dependency on all six inputs, not just the block count, and it is resolved the same way: B's Phase 0 seed generator produces all six, and Phase 3 tests `safety` against the seeded database. Phase 4 then proves the live `memory` engine writes rows `safety` reads to the same totals. Nothing in Phase 3 may touch a live engine 19.

## Build order

Structure, then interface, then backend.

The SQLite schema and a seed generator producing realistic fake rows are built in Phase 0, before the console. The console is then built in Phase 1 against the real schema with fake data. When the backend fills that same schema with real data from Phase 2 onward, the console needs no changes.

`scripts/record.py` is a standalone Phase 0 deliverable with no dependency on the engine framework. It exists because order-book and spread history cannot be recovered retroactively, so recording must start on day one rather than waiting for Phase 2. Engines 1 and 2 supersede it.

## The command table

The console writes rows to a `commands` table; the daemon reads them. Semantics:

| Command | Effect |
|---|---|
| `activate` | Mode goes `idle` to `running`. The opportunity chain begins running. |
| `freeze` | Mode goes to `frozen`. The opportunity chain stops. **The guard chain keeps recording and keeps running `safety`, and the manage chain keeps managing open positions.** Freeze never stops data collection. Managing remains subject to the data-guard hold: on a tick where `data_guard` blocked, no exit is placed. |
| `close_all` | Mode goes to `frozen` and `close_intent` is set. In the same tick engine 21 cancels every **resting entry order** and engine 22 exits every **open position** as a taker. The orchestrator clears the intent only when both report done, and retries next tick if not. This is the one operation that proceeds even when `data_guard` has blocked **and even when the balance or book fetch is failing**, on cached data past its TTL. See invariant 14 — unknown exposure is worse than a bad fill. |

**The kill switch is `close_all`. There is no fourth mechanism.** `freeze` stops new trades and keeps managing what is open; `close_all` is the emergency stop that ends exposure. Phase 8 verifies `close_all`, not something separate.

The command reader in `core/` is the only writer of `state["system"]`, the one persistent region of state. Engines act on what it sets but never write it back: engine 21 cancels resting entry orders and engine 22 closes positions, each reporting completion in its own `data`, and the orchestrator clears `close_intent` on their behalf. The reader belongs to the lead; the cancelling and closing belong to B.

**Engine 17 `safety` uses this same table.** It cannot write `state["system"]`, so when it must freeze the system it writes a `freeze` or `close_all` command row through the store client. The orchestrator consumes it at the top of the next tick. The console and the safety engine are the two writers; the orchestrator is the one reader. Because `safety` runs every tick it only emits a row that would actually change the state — the idempotency rule is in `engine-contracts.md`. It also emits `close_all` once `data_guard` has blocked for more than `safety.max_consecutive_data_blocks` consecutive ticks, so a feed outage cannot hold a position indefinitely.

The daemon reads pending commands **at the top of every tick**, before the guard chain, in the orchestrator. That reader lives in `core/` and is the lead's.

**Consumption is two-phase, so a crash cannot swallow a kill switch.** Each row carries `claimed_at` and `consumed_at`:

1. The reader stamps `claimed_at` and applies the effect to `state["system"]`.
2. `consumed_at` is stamped only when the effect is complete — immediately for `activate` and `freeze`, which are pure mode changes, and for `close_all` only when every resting order is cancelled and every position closed.

A row with `claimed_at` set and `consumed_at` null is an interrupted command. On startup the reader re-applies every such row before the first tick. Without this, a daemon killed between reading `close_all` and finishing the liquidation would restart with the command already marked done, the in-memory `close_intent` gone, and positions still open — the one failure the kill switch exists to prevent.

`claimed_at` also gives idempotency: a row that is already claimed is never applied twice within a run.

**Mode is never restored from the store.** A daemon always starts `idle` and only reaches `running` through an `activate` command. A crashed daemon therefore comes back not trading, with the manage chain still watching whatever is open. Re-applying unconsumed commands happens first, so an interrupted `close_all` still completes even though the mode reverted to `idle`.

Every claim and every consumption is logged as an audit row.

An unrecognised command is ignored and logged as a warning. It never blocks the loop.

## Modes

- **paper** — default. Full pipeline runs, orders go to the fill simulator, no exchange mutation.
- **live** — requires all three switches from `trading-invariants.md`.
- **replay** — offline. Historical data through the same engines with an injected clock.

The same engine code runs in all three modes. Mode differences live only in the client layer.

## Invariants

0. `core/` holds contracts and the orchestrator and nothing else, and **imports nothing from the rest of the package**. `core/contracts.py` declares `Config`, `Clock` and `Clients` as `typing.Protocol`s; `platform/` and `clients/` provide the concrete implementations. That is what makes the lead-versus-A boundary work: the lead owns the shape, A owns the implementation, and neither writes in the other's directory.
1. Engines are stateless across cycles. All state lives in the `state` dict or the store.
2. Engines never call the network directly; they use injected clients.
3. Engines never read the clock; they use `context.now`.
4. Engines never import each other. Communication is through `state` only.
5. Research code never imports from the live loop path, and the live loop never imports from `research/`. This constrains `src/acsoe/` only. `scripts/verify.py` is neither — it is allowed to import both, which is how it checks the offline chain. **`modelling/` is the one package both sides import** (operator ruling 2026-09-12): it holds the arithmetic that must agree between live and replay, imports nothing from `acsoe` but `core/contracts.py` types, reads no `state`, opens no client and holds no engine, and a test walks its import graph to keep it that way.
6. Anything slower than the loop tick belongs offline, not in an engine.
7. Credentials exist only in the environment.
