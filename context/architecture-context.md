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
| Console | `fastapi`, `uvicorn` | Local read-only dashboard |
| Logging | `structlog` | Structured JSON logs |
| Tests | `pytest`, `pytest-asyncio`, `hypothesis` | Unit and property tests |

Target OS is Windows. Any path handling must use `pathlib`, never string concatenation or hardcoded separators.

## Repository layout

```
src/acsoe/
  core/                 contracts, orchestrator, config, clock, logging   [LEAD ONLY]
  bootstrap.py          engine registry and wiring                       [LEAD ONLY]
  engines/
    <engine_name>/
      engine.py         the BaseEngine subclass
      contracts.py      pydantic models for this engine's output
      README.md         what it does, inputs, outputs, gate behaviour
  clients/
    kraken/             REST client, WebSocket client, rate limiter
    store/              SQLite and Parquet access
  research/             offline only: labelling, training, walk-forward
  console/              FastAPI app, static assets
  cli/                  acsoe engine, acsoe console entrypoints
scripts/
  verify.py             executable phase exit criteria
  record.py             standalone day-one recorder, no framework deps
db/
  migrations/           SQLite schema, forward-only
docs/
  build-log/            one file per phase, written by agents as they work
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
| 1. Ingestion and gatekeeping | 1, 2, 3, 4 | Every tick |
| 2. Screening | 5, 6, 7 | On each closed 15-minute bar |
| 3. Judgement | 8–17 | On the candidate only |
| 4. Execution, management, learning | 18, 21, 22, 19, 20 | On the position |

Engine 23 runs offline and is never invoked by the live loop.

## Timeframes

Three distinct concepts. Do not conflate them.

- **Decision bar: 15 minutes.** Features and labels are computed on closed 15-minute candles. New candidates are only born when a bar closes.
- **Holding horizon: 2 to 12 hours.** Target +3%, stop −1.5%, timeout after 24 bars.
- **Loop tick: 1 minute.** Manages open positions and entry orders. Never generates new signals.

## Data sources

### Historical (training)

Kraken's downloadable OHLCVT archives, loaded from `data/historical/`. They provide 15-minute CSVs covering full trading history.

Two properties that must be handled explicitly:

- **Gaps are real.** The archives only contain intervals where trades occurred. A missing candle means no trades, not a data error. Never interpolate a missing candle into existence — mark it and let the feature layer decide.
- **No book, no spread.** The archives are OHLCVT only. Bid, ask, depth, and spread do not exist in them.

### Live (recording)

Kraken WebSocket v2, recorded append-only to `data/raw/`.

**Order book and spread data can only be gathered going forward and can never be recovered retroactively.** The recorder must run continuously from Phase 1 onward, regardless of what else is being built.

### The consequence

Engine 9 (order book) and the spread component of Engine 10 cannot be backtested from the historical archives. Any backtest covering periods before live recording began must either exclude those engines or model their inputs from an explicitly documented proxy. A backtest that silently assumes zero spread is invalid.

## Storage model

| Data | Store | Notes |
|---|---|---|
| Raw market recordings | JSONL in `data/raw/` | Append-only, daily rotation, compacted to Parquet |
| Built candles, feature snapshots | Parquet in `data/derived/` | Rebuildable from raw |
| Trades, rejections, runs, leaderboard | SQLite | Small, relational, queried constantly |
| Trained models | Files in `models/` | Versioned by training run id, never overwritten |
| SHAP explanations | Parquet, joined by decision id | One row per decision |

Never put large arrays in SQLite. Never put relational records in Parquet.

## Build order

Structure, then interface, then backend.

The SQLite schema and a seed generator producing realistic fake rows are built in Phase 0, before the console. The console is then built in Phase 1 against the real schema with fake data. When the backend fills that same schema with real data from Phase 2 onward, the console needs no changes.

`scripts/record.py` is a standalone Phase 0 deliverable with no dependency on the engine framework. It exists because order-book and spread history cannot be recovered retroactively, so recording must start on day one rather than waiting for Phase 2. Engines 1 and 2 supersede it.

## Modes

- **paper** — default. Full pipeline runs, orders go to the fill simulator, no exchange mutation.
- **live** — requires all three switches from `trading-invariants.md`.
- **replay** — offline. Historical data through the same engines with an injected clock.

The same engine code runs in all three modes. Mode differences live only in the client layer.

## Invariants

1. Engines are stateless across cycles. All state lives in the `state` dict or the store.
2. Engines never call the network directly; they use injected clients.
3. Engines never read the clock; they use `context.now`.
4. Engines never import each other. Communication is through `state` only.
5. Research code never imports from the live loop path, and the live loop never imports from `research/`.
6. Anything slower than the loop tick belongs offline, not in an engine.
7. Credentials exist only in the environment.
