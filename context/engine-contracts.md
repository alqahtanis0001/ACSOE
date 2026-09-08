# Engine Contracts

This interface is fixed. Changing anything in this file requires the lead. Do not add parameters, return types, or side channels.

## The interface

```python
class EngineStatus(str, Enum):
    OK = "OK"        # ran, produced output, pipeline continues
    PASS = "PASS"    # nothing to do this cycle; not an error
    BLOCK = "BLOCK"  # halt the pipeline for this cycle
    ERROR = "ERROR"  # unexpected failure; treated as BLOCK


@dataclass(frozen=True)
class EngineContext:
    mode: Literal["paper", "live", "replay"]
    run_id: str
    now: datetime               # UTC, injected. Engines never read the clock.
    config: Config             # a Protocol declared in core/, implemented in platform/
    clients: Clients            # kraken, store, recorder — injected, never constructed


class EngineResult(BaseModel):
    engine: str
    status: EngineStatus
    blocks_trading: bool = False
    reason: str | None = None       # required when blocks_trading is True
    data: dict[str, Any] = {}
    duration_ms: float


class BaseEngine(ABC):
    name: ClassVar[str]             # snake_case, matches the directory
    number: ClassVar[int]           # 1..23
    is_gate: ClassVar[bool] = False

    @abstractmethod
    def process(self, context: EngineContext, state: State) -> EngineResult:
        ...
```

`is_gate` is not decorative. `scripts/verify.py` asserts that every engine's `is_gate` matches the Gate column of the registry table below, which catches a gate registered as an ordinary engine — a failure that would otherwise be silent and expensive.

`State = dict[str, Any]`, keyed by engine name, defined in `core/contracts.py`. An engine reads other engines' outputs through `state["<engine_name>"]` and writes only its own key.

## Rules

1. `process` is the only public entry point. No engine exposes another method to the orchestrator.
2. An engine writes exactly one key into `state`: its own name.
3. An engine never imports another engine. If you need something from engine N, read it from `state`.
4. An engine never constructs a client, opens a socket, or touches the filesystem directly — everything comes through `context.clients`. Three clients exist: `kraken` (exchange), `store` (SQLite and Parquet), and `recorder` (append-only raw JSONL, used only by engine 2).
5. An engine never calls `datetime.now()` or `time.time()`. Use `context.now`.
6. To block, return `EngineResult(status=BLOCK, blocks_trading=True, reason="...")`. A reason is mandatory and must be specific enough to analyse later.
7. Any uncaught exception is converted by the orchestrator into `ERROR` with `blocks_trading=True`. Engines should not swallow their own exceptions to avoid this.
8. `data` must be JSON-serialisable. No numpy arrays, no dataframes, no model objects.

## Orchestrator behaviour

### State lifetime

`state` is a **fresh dict every tick**. Nothing in it survives to the next tick except one region:

```python
state["system"] = {          # persistent — carried across ticks by the orchestrator
    "mode": "idle",          # idle | running | frozen
    "close_intent": False,   # set by close_all, cleared by engine 22 after acting
}
state["cycle_id"] = ...      # fresh each tick, minted by the orchestrator
```

Everything else — every engine's output key, `trading_blocked_by`, `block_reason` — is gone at the end of the tick. An engine in the manage chain that needs last cycle's decision reads it from the store, never from `state`, because on fourteen ticks out of fifteen the opportunity chain did not run and those keys do not exist.

`run_id` lives only on `context.run_id`. It is minted once per daemon process by the orchestrator and is not duplicated into `state`.

### The three runtime chains

Every tick runs the ingest and manage chains. The opportunity chain runs only when the system is `running`.

```
# 0. Read commands. Sets state["system"]["mode"] and close_intent.
consume_commands()

# 1. INGEST — every tick, every mode. Never stops.
for engine in INGEST_CHAIN:                    # exactly: 1, 2, 3, 4
    result = run(engine)
    state[engine.name] = result.data
    if result.blocks_trading:                  # data_guard says the data is bad
        state["trading_blocked_by"] = engine.name
        state["block_reason"] = result.reason
        # ingestion continues; only the opportunity chain is skipped

# 2. OPPORTUNITY — only if running and ingest did not block. May stop early.
if state["system"]["mode"] == "running" and "trading_blocked_by" not in state:
    for engine in OPPORTUNITY_CHAIN:           # 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 17, 18
        result = run(engine)
        state[engine.name] = result.data
        if result.blocks_trading:
            state["trading_blocked_by"] = engine.name
            state["block_reason"] = result.reason
            break
        if result.status is PASS:
            break                              # no candidate this cycle

# 3. MANAGE — every tick, every mode. Never stops.
for engine in MANAGE_CHAIN:                    # exactly: 21, 22, 19
    result = run(engine)
    state[engine.name] = result.data
```

**Why ingestion is its own chain.** Freeze must stop trading without stopping data collection, because order-book and spread history can never be recovered. Engines 1 to 4 therefore run in every mode including `frozen` and `idle`. Only the opportunity chain is switched off by freeze.

**Why manage is its own chain.** The loop ticks every minute but a candidate is only born when a 15-minute bar closes, so the opportunity chain stops early on roughly fourteen ticks out of fifteen. If position management sat in it, an open trade would go unwatched for fourteen minutes at a time and its stop would never fire. `position_manager`, `exit` and `memory` therefore run on every tick no matter what.

**How the safety engine freezes the system.** Engine 17 cannot write `state["system"]` — only the orchestrator may. Instead it writes a `freeze` or `close_all` row to the **commands table** through `context.clients.store`, the same channel the console uses. Its `BLOCK` stops the current cycle; the command row makes the freeze persist, because the orchestrator consumes it at the top of the next tick. Every such row is an audit record of exactly when and why the system stopped itself.

**How close_all works.** The command reader sets `state["system"]["close_intent"] = True`. Engine 22 `exit`, running in the manage chain the same tick, closes every open position as a taker and clears the flag. Mode is then `frozen`. `frozen` alone means "stop opening, keep managing"; `frozen` plus `close_intent` means "liquidate now". They are distinguishable.

**The offline chain.** Engine 20 `tournament` and engine 23 `backtest` run in `OFFLINE_CHAIN`, invoked only by `acsoe research`. That chain is **assembled in `cli/research.py`, never in `bootstrap.py`**, so the live loop path never imports from `research/` and architecture invariant 5 holds. `bootstrap.py` builds only the three runtime chains.

A blocked candidate that never reaches storage is lost research data, and an unwatched position is lost money. Do not "simplify" the orchestrator into a single loop.

If an engine in any chain is not yet registered — as in Phase 0, where none exist — the orchestrator skips it and logs at debug level. An empty chain is valid.

## Fixed engine order

The registry order is non-negotiable. The stage column refers to the runtime loop stages in `architecture-context.md`, not to build phases. Cheap deterministic checks run before expensive model inference.

| # | Name | Gate | Chain | Runtime stage |
|---|---|---|---|---|
| 1 | `exchange` | | **ingest** | 1 |
| 2 | `market_data_recorder` | | **ingest** | 1 |
| 3 | `market_sensor` | | **ingest** | 1 |
| 4 | `data_guard` | **Y** | **ingest** | 1 |
| 5 | `feature` | | opportunity | 2 |
| 6 | `macro_context` | | opportunity | 2 |
| 7 | `scout` | **Y** | opportunity | 2 |
| 12 | `regime` | | opportunity | 3 |
| 13 | `anomaly` | **Y** | opportunity | 3 |
| 8 | `prediction` | | opportunity | 3 |
| 9 | `order_book` | | opportunity | 3 |
| 10 | `cost` | **Y** | opportunity | 3 |
| 11 | `risk` | **Y** | opportunity | 3 |
| 14 | `adaptive_router` | | opportunity | 3 |
| 15 | `skeptic` | **Y** | opportunity | 3 |
| 16 | `decision` | | opportunity | 3 |
| 17 | `safety` | **Y** | opportunity | 3 |
| 18 | `execution` | | opportunity | 4 |
| 21 | `position_manager` | | **manage** | 4 |
| 22 | `exit` | | **manage** | 4 |
| 19 | `memory` | | **manage** | 4 |
| 20 | `tournament` | | **offline** | — |
| 23 | `backtest` | | **offline** | — |

Engine 23 `backtest` lives in `research/` and is registered only in `OFFLINE_CHAIN`, which `cli/research.py` assembles. It never appears in `bootstrap.py`.

Note that 12 and 13 execute before 8 and 9. The numbers are identifiers, not execution order.

Engine 6 is named `macro_context`, not `context`, so that it never reads ambiguously against the `context/` documentation directory.

The Dissimilarity Index is not an engine. It lives inside `engines/prediction/` as a fitted artefact alongside the predictor, because it must be fitted on the predictor's training set. The execution offset bandit is likewise not an engine; it lives inside `engines/execution/` with its state in the store.

## Per-engine directory

Every engine directory contains exactly three files:

- `engine.py` — the `BaseEngine` subclass
- `contracts.py` — pydantic models for what this engine puts in `state`
- `README.md` — purpose, inputs read from `state`, outputs written, gate conditions

The README is not optional. It is how the next agent understands the engine without reading the code.

## State keys

Each engine's `data` payload is typed in its own `contracts.py`. Orchestrator-level keys:

- `state["system"]` — the only persistent region. `mode` and `close_intent`. Written only by the orchestrator's command reader; readable by any engine.
- `state["cycle_id"]` — fresh per tick, minted by the orchestrator, joins logs, decisions and SHAP rows.
- `state["trading_blocked_by"]`, `state["block_reason"]` — set on block, fresh per tick.

`run_id` is `context.run_id`, nowhere else.

**The orchestrator holds the `Clock`.** It is constructed by the CLI, passed to the orchestrator, and used once per tick to stamp `context.now`. No engine ever sees it.
