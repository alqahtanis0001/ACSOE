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

The registry has **two chains**, and every tick runs both.

```
# CHAIN 1 — opportunity. May stop early.
for engine in OPPORTUNITY_CHAIN:
    result = run(engine)                       # exceptions -> ERROR
    state[engine.name] = result.data
    if result.blocks_trading:
        state["trading_blocked_by"] = engine.name
        state["block_reason"] = result.reason
        break
    if result.status is PASS:
        break                                  # no candidate this cycle

# CHAIN 2 — always. Runs every tick regardless of what chain 1 did.
for engine in ALWAYS_CHAIN:                    # exactly: 21, 22, 19
    result = run(engine)
    state[engine.name] = result.data
```

**Chain 2 is exactly three engines: 21, 22, 19. Nothing else.**

The loop ticks every minute but a new candidate is only born when a 15-minute bar closes, so chain 1 stops early on roughly fourteen ticks out of fifteen. If position management sat in chain 1, an open trade would go unwatched for fourteen minutes at a time and its stop would never fire. Chain 2 exists so `position_manager`, `exit` and `memory` run on every single tick no matter what.

**Engine 20 `tournament` is not in either chain.** It scores realised outcomes, which only change when a trade closes, so recomputing a leaderboard every sixty seconds would be waste. It runs offline, invoked after a trade closes and during the research loop.

A blocked candidate that never reaches storage is lost research data, and an unwatched position is lost money. Do not "simplify" the orchestrator into a single loop.

If an engine in chain 2 is not yet registered — as in Phase 0, where none exist — the orchestrator skips it and logs at debug level. An empty chain is valid.

## Fixed engine order

The registry order is non-negotiable. The stage column refers to the runtime loop stages in `architecture-context.md`, not to build phases. Cheap deterministic checks run before expensive model inference.

| # | Name | Gate | Chain | Runtime stage |
|---|---|---|---|---|
| 1 | `exchange` | | opportunity | 1 |
| 2 | `market_data_recorder` | | opportunity | 1 |
| 3 | `market_sensor` | | opportunity | 1 |
| 4 | `data_guard` | **Y** | opportunity | 1 |
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
| 21 | `position_manager` | | **chain 2** | 4 |
| 22 | `exit` | | **chain 2** | 4 |
| 19 | `memory` | | **chain 2** | 4 |
| 20 | `tournament` | | offline | — |

Engine 23 (`backtest`) lives in `research/` and is never registered.

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

- `state["trading_blocked_by"]` — engine name, set on block
- `state["block_reason"]` — the reason string
- `state["cycle_id"]` — unique per loop iteration, used to join logs, decisions, and SHAP rows
