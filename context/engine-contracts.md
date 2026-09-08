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
    "close_intent": False,   # set by the command reader; cleared by the orchestrator
}                            #   only after the manage chain reports the close finished
state["cycle_id"] = ...      # fresh each tick, minted by the orchestrator
```

Everything else — every engine's output key, `trading_blocked_by`, `block_reason` — is gone at the end of the tick. An engine in the manage chain that needs last cycle's decision reads it from the store, never from `state`, because on fourteen ticks out of fifteen the opportunity chain did not run and those keys do not exist.

`run_id` lives only on `context.run_id`. It is minted once per daemon process by the orchestrator and is not duplicated into `state`.

**At startup `mode` is always `idle`.** It is never restored from the store. A daemon that crashed while trading comes back not trading — the manage chain still runs, so open positions stay watched, but nothing new is opened until the operator activates again. Any command row that was claimed but never consumed is re-applied first; see the command table in `architecture-context.md`.

### The three runtime chains

Every tick runs the guard and manage chains. The opportunity chain runs only when the system is `running` and nothing has already blocked.

```
# 0. Read commands. Sets state["system"]["mode"] and close_intent.
consume_commands()

# 1. GUARD — every tick, every mode. Never breaks early.
for engine in GUARD_CHAIN:                     # exactly: 1, 2, 3, 4, 17
    result = run(engine)
    state[engine.name] = result.data
    if result.blocks_trading and "trading_blocked_by" not in state:
        state["trading_blocked_by"] = engine.name    # first blocker wins
        state["block_reason"] = result.reason
        # the chain still finishes; only the opportunity chain is skipped

# 2. OPPORTUNITY — only if running and nothing blocked. May stop early.
if state["system"]["mode"] == "running" and "trading_blocked_by" not in state:
    for engine in OPPORTUNITY_CHAIN:           # 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18
        result = run(engine)
        state[engine.name] = result.data
        if result.blocks_trading:
            state["trading_blocked_by"] = engine.name
            state["block_reason"] = result.reason
            break
        if result.status is PASS:
            break                              # no candidate this cycle

# 3. MANAGE — every tick, every mode. Never stops.
#    Every engine still runs and still records. But 21 and 22 must not place
#    an exit when the guard rejected the data this tick, unless close_intent
#    is set. See "When the guard rejects the data, the manage chain holds".
for engine in MANAGE_CHAIN:                    # exactly: 21, 22, 19
    result = run(engine)
    state[engine.name] = result.data

# 4. Clear close_intent only once the close actually finished.
if close_intent_set and entry_orders_cancelled and positions_closed:
    state["system"]["close_intent"] = False
    mark_command_consumed()
```

**Why the guard chain never stops.** Freeze must stop trading without stopping data collection, because order-book and spread history can never be recovered. Engines 1 to 4 therefore run in every mode including `frozen` and `idle`. The chain also never breaks on a block: a bad-data block from `data_guard` must not stop `safety` from evaluating, so every guard engine runs every tick and only the first blocker is recorded.

**Why `safety` is a guard and not a judgement.** Engine 17 asks an account-level question — how far is equity down, how many losses in a row, how many errors this hour. That question has nothing to do with the candidate under consideration, and it must be answered on ticks where there is no candidate at all. Placed at the end of the opportunity chain it would run only when every other gate had already passed: on roughly fourteen ticks in fifteen that chain stops at `feature` because no bar closed, and on the remainder any earlier gate blocking stops it sooner. An account bleeding while every candidate is rejected by the cost gate would never trip the breaker. In the guard chain it runs on every tick in every mode, which is the only placement that makes it a circuit breaker rather than a formality.

**Why manage is its own chain.** The loop ticks every minute but a candidate is only born when a 15-minute bar closes, so the opportunity chain stops early on roughly fourteen ticks out of fifteen. If position management sat in it, an open trade would go unwatched for fourteen minutes at a time and its stop would never fire. `position_manager`, `exit` and `memory` therefore run on every tick no matter what.

**When the guard rejects the data, the manage chain holds.** `data_guard` blocking means the tick's market data is stale, has a negative spread, or is missing candles. The opportunity chain is skipped, but the manage chain still runs — and a target or stop computed from exactly that data would be a fabricated trigger. So when `state["trading_blocked_by"] == "data_guard"`, engines 21 and 22 **place no exit**: no target exit, no stop exit, no timeout exit. They still run, because engine 19 must still record the tick and because holding is itself a fact worth recording. Engine 21 reports `state["position_manager"]["hold_reason"]`, a short string naming why it held, and null on any tick where it did not.

The one exception is `close_intent`. An emergency stop proceeds regardless of the guard, because a bad fill is a smaller risk than unknown exposure: when the operator or `safety` has ordered a liquidation, the system stops reasoning about price quality and gets flat. This is the only place in the system where a gate's block is deliberately overridden, and it is overridden in the direction of less exposure, never more — which is why it does not violate invariant 4.

A block from any engine other than `data_guard` does not hold the manage chain. Those blocks concern whether a *new* trade is wise; they say nothing about whether the data underneath an *open* position is trustworthy.

**What stops the opportunity chain on a non-bar tick.** Engine 3 `market_sensor` owns the decision-bar clock. It publishes `state["market_sensor"]["bar_closed"]` — true only on the tick where a 15-minute candle completed — together with that bar's close timestamp. Engine 5 `feature`, first in the opportunity chain, returns `PASS` when `bar_closed` is false, and the chain stops there. No other engine may infer the bar boundary for itself, and the orchestrator does not know about bars at all: cadence is a property of the candle stream, not of `core/`.

**How the safety engine freezes the system.** Engine 17 cannot write `state["system"]` — only the orchestrator may. Instead it writes a `freeze` or `close_all` row to the **commands table** through `context.clients.store`, the same channel the console uses. Its `BLOCK` suppresses the opportunity chain for the current tick; the command row makes the freeze persist, because the orchestrator consumes it at the top of the next tick. Every such row is an audit record of exactly when and why the system stopped itself.

Because it now runs every tick, `safety` must be idempotent about what it emits. It writes a command row only when that row would change the system's state: `freeze` only while the mode is `running`, and `close_all` only when positions are open and `close_intent` is not already set. When the condition persists and the state already reflects it, `safety` still evaluates and still records its assessment in its own `data` for the console and the log, but emits nothing. Without this rule a sustained drawdown would append a freeze row every sixty seconds forever.

**How close_all works.** The command reader sets `state["system"]["close_intent"] = True` and the mode to `frozen`. Two engines act on it in the manage chain, in that order:

- Engine 21 `position_manager` cancels every resting entry order. A post-only limit still sitting on the book is not a position, and leaving one live after an emergency stop lets exposure re-open minutes later. It reports `state["position_manager"]["entry_orders_cancelled"]`, true only when none remain.
- Engine 22 `exit` closes every open position as a taker. It reports `state["exit"]["positions_closed"]`, true only when none remain.

The **orchestrator**, not either engine, clears `close_intent`, and only when both flags are true. If a cancel or a close failed this tick, the intent survives into the next tick and the manage chain retries. That is what makes the kill switch converge rather than fire once and hope.

`frozen` alone means "stop opening, keep managing". `frozen` plus `close_intent` means "liquidate now". They are distinguishable, and the second is not finished until both engines say it is.

**The offline chain.** Engine 20 `tournament` and engine 23 `backtest` run in `OFFLINE_CHAIN`, invoked only by `acsoe research`. That chain is **assembled in `cli/research.py`, never in `bootstrap.py`**, so the live loop path never imports from `research/` and architecture invariant 5 holds. `bootstrap.py` builds only the three runtime chains.

`scripts/verify.py` sits outside both sides of that boundary and may import either. That is what lets its `is_gate` assertion cover engines 20 and 23 as well as the registered ones.

A blocked candidate that never reaches storage is lost research data, and an unwatched position is lost money. Do not "simplify" the orchestrator into a single loop.

If an engine in any chain is not yet registered — as in Phase 0, where none exist — the orchestrator skips it and logs at debug level. An empty chain is valid. The `close_intent` step treats a missing `position_manager` or `exit` result as "not finished", so an unregistered manage chain can never silently discard a pending close.

## Fixed engine order

The registry order is non-negotiable. The stage column refers to the runtime loop stages in `architecture-context.md`, not to build phases. Cheap deterministic checks run before expensive model inference.

| # | Name | Gate | Chain | Runtime stage |
|---|---|---|---|---|
| 1 | `exchange` | | **guard** | 1 |
| 2 | `market_data_recorder` | | **guard** | 1 |
| 3 | `market_sensor` | | **guard** | 1 |
| 4 | `data_guard` | **Y** | **guard** | 1 |
| 17 | `safety` | **Y** | **guard** | 1 |
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
| 18 | `execution` | | opportunity | 4 |
| 21 | `position_manager` | | **manage** | 4 |
| 22 | `exit` | | **manage** | 4 |
| 19 | `memory` | | **manage** | 4 |
| 20 | `tournament` | | **offline** | — |
| 23 | `backtest` | | **offline** | — |

Engine 23 `backtest` lives in `research/` and is registered only in `OFFLINE_CHAIN`, which `cli/research.py` assembles. It never appears in `bootstrap.py`.

Note that 12 and 13 execute before 8 and 9, and that 17 executes before 5. The numbers are identifiers, not execution order.

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

### Cross-chain keys the contract fixes

Most of an engine's `data` is its own business, typed in its own `contracts.py`. Four fields are different: another chain depends on them, they cross an ownership boundary, or the orchestrator reads them. They are fixed here and may not be renamed without the lead.

| Key | Written by | Read by | Meaning |
|---|---|---|---|
| `state["market_sensor"]["bar_closed"]` | 3 `market_sensor` (A) | 5 `feature` (C) | A 15-minute decision bar closed on this tick |
| `state["position_manager"]["entry_orders_cancelled"]` | 21 `position_manager` (B) | orchestrator (Lead) | No resting entry order remains |
| `state["exit"]["positions_closed"]` | 22 `exit` (B) | orchestrator (Lead) | No open position remains |
| `state["position_manager"]["hold_reason"]` | 21 `position_manager` (B) | 19 `memory` (C), console | Why the manage chain placed no exit this tick; null when it did not hold |

The last two are only meaningful while `close_intent` is set. Absent or false always means "not finished", never "finished" — the same fail-closed default the gates use.

**The orchestrator holds the `Clock`.** It is constructed by the CLI, passed to the orchestrator, and used once per tick to stamp `context.now`. No engine ever sees it.
