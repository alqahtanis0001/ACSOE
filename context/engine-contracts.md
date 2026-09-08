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
    config: Config
    clients: Clients            # kraken, store — injected, never constructed


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

`State` is a `dict[str, Any]` keyed by engine name. An engine reads other engines' outputs through `state["<engine_name>"]` and writes only its own key.

## Rules

1. `process` is the only public entry point. No engine exposes another method to the orchestrator.
2. An engine writes exactly one key into `state`: its own name.
3. An engine never imports another engine. If you need something from engine N, read it from `state`.
4. An engine never constructs a client, opens a socket, or touches the filesystem directly — everything comes through `context.clients`.
5. An engine never calls `datetime.now()` or `time.time()`. Use `context.now`.
6. To block, return `EngineResult(status=BLOCK, blocks_trading=True, reason="...")`. A reason is mandatory and must be specific enough to analyse later.
7. Any uncaught exception is converted by the orchestrator into `ERROR` with `blocks_trading=True`. Engines should not swallow their own exceptions to avoid this.
8. `data` must be JSON-serialisable. No numpy arrays, no dataframes, no model objects.

## Orchestrator behaviour

```
for engine in REGISTRY (fixed order):
    result = run(engine)                       # exceptions -> ERROR
    state[engine.name] = result.data
    results.append(result)
    if result.blocks_trading:
        state["trading_blocked_by"] = engine.name
        state["block_reason"] = result.reason
        break
    if result.status is PASS:
        break                                  # nothing to trade this cycle

# ALWAYS runs, even after a block or a pass:
run(memory_engine)
```

The final memory step is not optional and is not part of the loop. A blocked candidate that never reaches storage is lost research data. This is the single most commonly broken rule — do not "simplify" the orchestrator by removing it.

## Fixed engine order

The registry order is non-negotiable. The stage column refers to the runtime loop stages in `architecture-context.md`, not to build phases. Cheap deterministic checks run before expensive model inference.

| # | Name | Gate | Runtime stage |
|---|---|---|---|
| 1 | `exchange` | | 1 |
| 2 | `market_data_recorder` | | 1 |
| 3 | `market_sensor` | | 1 |
| 4 | `data_guard` | **Y** | 1 |
| 5 | `feature` | | 2 |
| 6 | `context` | | 2 |
| 7 | `scout` | **Y** | 2 |
| 12 | `regime` | | 3 |
| 13 | `anomaly` | **Y** | 3 |
| 8 | `prediction` | | 3 |
| 9 | `order_book` | | 3 |
| 10 | `cost` | **Y** | 3 |
| 11 | `risk` | **Y** | 3 |
| 14 | `adaptive_router` | | 3 |
| 15 | `skeptic` | **Y** | 3 |
| 16 | `decision` | | 3 |
| 17 | `safety` | **Y** | 3 |
| 18 | `execution` | | 4 |
| 21 | `position_manager` | | 4 |
| 22 | `exit` | | 4 |
| 19 | `memory` | | 4 — always runs |
| 20 | `tournament` | | 4 |

Engine 23 (`backtest`) lives in `research/` and is never registered.

Note that 12 and 13 execute before 8 and 9. The numbers are identifiers, not execution order.

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
