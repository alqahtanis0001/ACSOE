# Engine Contracts

This interface is fixed. Changing anything in this file requires the lead. Do not add parameters, return types, or side channels.

## The interface

```python
class EngineStatus(StrEnum):
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
    previous_now: datetime | None = None   # the previous tick's stamp; None on the first


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

`EngineStatus` is a `StrEnum`, not `(str, Enum)`. The difference is not stylistic: with
`(str, Enum)`, `str(EngineStatus.ERROR)` and any f-string interpolation of it produce
`"EngineStatus.ERROR"` rather than `"ERROR"`. That value reaches `block_records.status`, which
engine 17 `safety` queries for `status = 'ERROR'` to compute its error rate — so the footgun sits
directly under the circuit breaker, and it fails silently, writing a plausible-looking string
that simply never matches. `StrEnum` has been in the standard library since 3.11, already this
project's floor.

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

   **An engine returning `ERROR` is not required to supply a `reason_code`, and engine 19 must record the tick regardless.** Operator ruling 2026-09-16. A `reason_code` is a decision an engine made; an `ERROR` is the absence of one — the orchestrator's conversion leaves `data == {}` — so no reader may demand a code from it. Engine 19 records an errored engine as a `block_records` row (`status = 'ERROR'`, `block_reason = 'engine_errored'`) and never as a rejection. Invariant 12 holds the rule and its reasoning. As first written this file was satisfiable by code that broke invariant 12 — engine 19 raising on the missing code lost the whole tick — which made the contract wrong rather than the code.
8. `data` must be JSON-serialisable. No numpy arrays, no dataframes, no model objects.

   **Money crosses `state` as an exact decimal string, never as a `float`.** The validator in `core/contracts.py` refuses a `Decimal` — loudly, which is fine — and **accepts a `float`**, which is the dangerous half. An engine that hits the refusal and reflexively casts to `float` publishes `0.0022` where it meant `Decimal("0.0022")`, loses precision on the way through, and arrives in a hurdle comparison wrong in the fourth decimal. That is the magnitude engine 10 `cost` operates at: reference friction is ~1.25% round trip at tier 1 and ~0.65% at tier 3, and a net edge is the small difference between two larger numbers.

   The validator cannot fix this, because it cannot know which field is money and float is legitimate for indicators, model inputs and statistics — that is the Phase 0 decision, `Decimal` for anything that reaches an order and float for everything else. So the rule lives here and is enforced per engine: type every money field in your `contracts.py` as `Money`, the annotated `Decimal` that raises on a float rather than coercing it, and serialise to string at the `state` boundary.

   Found by B while building engine 10, before any float had reached a gate.

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

`run_id` lives only on `context.run_id`. It is minted once per daemon process by the orchestrator and is not duplicated into `state`. The orchestrator also writes one `runs` row at startup carrying that `run_id` and the start timestamp; that row is what the console compares against to detect a restart, so it is written before the first tick, not lazily.

**At startup `mode` is always `idle`.** It is never restored from the store. A daemon that crashed while trading comes back not trading — the manage chain still runs, so open positions stay watched, but nothing new is opened until the operator activates again. Any command row that was claimed but never consumed is re-applied first; see the command table in `architecture-context.md`.

### The three runtime chains

Every tick runs the guard and manage chains. The opportunity chain runs only when the system is `running` and nothing has already blocked.

```
# 0. Read commands. Sets state["system"]["mode"] and close_intent.
consume_commands()

# 1. GUARD — every tick, every mode. Never breaks early.
state["guard_blockers"] = []
for engine in GUARD_CHAIN:                     # exactly: 1, 2, 3, 4, 17
    result = run(engine)
    state[engine.name] = result.data
    if result.blocks_trading:
        state["guard_blockers"].append(              # every blocker, for engine 19
            {"engine": engine.name, "reason": result.reason,
             "status": result.status})
        if "trading_blocked_by" not in state:        # the first one is primary
            state["trading_blocked_by"] = engine.name
            state["block_reason"] = result.reason
            state["block_status"] = result.status
        # the chain still finishes; only the opportunity chain is skipped

# 2. OPPORTUNITY — only if running and nothing blocked. May stop early.
if state["system"]["mode"] == "running" and "trading_blocked_by" not in state:
    for engine in OPPORTUNITY_CHAIN:           # 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18
        result = run(engine)
        state[engine.name] = result.data
        if result.blocks_trading:
            state["trading_blocked_by"] = engine.name
            state["block_reason"] = result.reason
            state["block_status"] = result.status    # BLOCK or ERROR; see rule 7
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
if state["system"]["close_intent"] \
        and state.get("position_manager", {}).get("entry_orders_cancelled") \
        and state.get("exit", {}).get("positions_closed"):
    state["system"]["close_intent"] = False
    mark_command_consumed()
```

**Why the guard chain never stops.** Freeze must stop trading without stopping data collection, because order-book and spread history can never be recovered. Engines 1 to 4 therefore run in every mode including `frozen` and `idle`. The chain also never breaks on a block: a bad-data block from `data_guard` must not stop `safety` from evaluating, so every guard engine runs every tick. The first blocker is the primary one that gates the opportunity chain, and **every** blocker is recorded — see invariant 12.

**Why `safety` is a guard and not a judgement.** Engine 17 asks an account-level question — how far is equity down, how many losses in a row, how many errors this hour. That question has nothing to do with the candidate under consideration, and it must be answered on ticks where there is no candidate at all. Placed at the end of the opportunity chain it would run only when every other gate had already passed: on roughly fourteen ticks in fifteen that chain stops at `feature` because no bar closed, and on the remainder any earlier gate blocking stops it sooner. An account bleeding while every candidate is rejected by the cost gate would never trip the breaker. In the guard chain it runs on every tick in every mode, which is the only placement that makes it a circuit breaker rather than a formality.

**Why manage is its own chain.** The loop ticks every minute but a candidate is only born when a 15-minute bar closes, so the opportunity chain stops early on roughly fourteen ticks out of fifteen. If position management sat in it, an open trade would go unwatched for fourteen minutes at a time and its stop would never fire. `position_manager`, `exit` and `memory` therefore run on every tick no matter what.

**When the guard rejects the data, the manage chain holds.** `data_guard` blocking means the tick's market data is stale, has a negative spread, or is missing candles. The opportunity chain is skipped, but the manage chain still runs — and a target or stop computed from exactly that data would be a fabricated trigger. So when `state["trading_blocked_by"] == "data_guard"`, engines 21 and 22 **place no exit**: no target exit, no stop exit, no timeout exit. They still run, because engine 19 must still record the tick and because holding is itself a fact worth recording. Engine 21 reports `state["position_manager"]["hold_reason"]`, a short string naming why it held, and null on any tick where it did not.

The hold suppresses **exits only**. Engine 21 still cancels an entry order that has outrun its unfilled window, because that is a decision about elapsed time rather than price — it needs no market data and it reduces exposure. Invariant 8 requires it and the hold does not suspend it. Reading "the manage chain holds" as "engine 21 does nothing" leaves a live post-only buy on the book through the outage, which is the hazard invariant 8 exists to prevent.

**The hold is bounded.** Engine 17 `safety` counts consecutive ticks blocked by `data_guard` and writes a `close_all` row once that count exceeds `safety.max_consecutive_data_blocks`. **Invariant 14** holds the threshold, its default, the conditions under which `safety` escalates at all, and the reasoning. Do not restate them here. What follows is only how the count is obtained.

**The counter comes from the store, not from `state`.** `state` is fresh every tick and `safety` may not write `state["system"]`, so there is nowhere in memory for a counter to live. Engine 19 `memory` writes one row per entry in `state["guard_blockers"]` into the `block_records` table — columns in `architecture-context.md` — and `safety` reads the trailing run of those rows, **ordered by `ts`**, counting how many consecutive most-recent `cycle_id`s carry a `data_guard` row. Consecutive *ticks*, not rows: a tick on which two guards blocked contributes one. Ordering by `cycle_id` would be wrong: it restarts with the process, and surviving a restart is the whole point of putting the counter in the store. Because the count lives in SQLite it survives a restart — a daemon that dies mid-outage and comes back does not reset the clock on an outage that is still happening.

The arithmetic is fixed here rather than left to the implementer, because it is off by one in the obvious reading. `data_guard` (4) runs *before* `safety` (17) in the guard chain, so the current tick's block is already visible in `state["trading_blocked_by"]`. `memory` (19) runs *later*, in the manage chain, so the store holds records only through the previous tick. The count is therefore **stored consecutive `data_guard` blocks through tick T−1, plus one if this tick is also blocked by `data_guard`**. Getting it wrong fires the breaker a minute early or a minute late; neither is acceptable.

Emitting the escalation obeys the same idempotency rule as any other `safety` emission: once `close_intent` is set, nothing is re-emitted while the outage continues.

**Engine 19 writes a block record on every blocked tick, candidate or not.** Invariant 12 already requires a rejection to reach storage. This states the weaker case explicitly, because the outage counter is built from those rows: a tick where `data_guard` blocked and no candidate ever existed still produces a record.

**A liquidation is never held.** When `close_intent` is set, engines 21 and 22 proceed regardless of the guard *and* regardless of a failed fetch, using last known good balances and cached pair metadata past its TTL. That is **invariant 14**, and the reasoning and its constraints live there. Do not restate them here, and do not weaken this file to disagree with them.

A block from any engine other than `data_guard` does not hold the manage chain. Those blocks concern whether a *new* trade is wise; they say nothing about whether the data underneath an *open* position is trustworthy.

**What stops the opportunity chain on a non-bar tick.** Engine 3 `market_sensor` owns the decision-bar clock. It publishes `state["market_sensor"]["bar_closed"]` — true only on the tick where a 15-minute candle completed — together with that bar's close timestamp. Engine 5 `feature`, first in the opportunity chain, returns `PASS` when `bar_closed` is false, and the chain stops there. No other engine may infer the bar boundary for itself, and the orchestrator does not know about bars at all: cadence is a property of the candle stream, not of `core/`.

**How the safety engine freezes the system.** Engine 17 cannot write `state["system"]` — only the orchestrator may. Instead it writes a `freeze` or `close_all` row to the **commands table** through `context.clients.store`, the same channel the console uses. Its `BLOCK` suppresses the opportunity chain for the current tick; the command row makes the freeze persist, because the orchestrator consumes it at the top of the next tick. Every such row is an audit record of exactly when and why the system stopped itself.

Because it now runs every tick, `safety` must be idempotent about what it emits. It writes a command row only when that row would change the system's state: `freeze` only while the mode is `running`, and `close_all` only when there are open positions **or resting entry orders** and `close_intent` is not already set. Entry orders count: an outage with no position but a live post-only buy is still exposure waiting to happen. When the condition persists and the state already reflects it, `safety` still evaluates and still records its assessment in its own `data` for the console and the log, but emits nothing. Without this rule a sustained drawdown would append a freeze row every sixty seconds forever.

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
| 16 | `decision` | **Y** | opportunity | 3 |
| 18 | `execution` | | opportunity | 4 |
| 21 | `position_manager` | | **manage** | 4 |
| 22 | `exit` | | **manage** | 4 |
| 19 | `memory` | | **manage** | 4 |
| 20 | `tournament` | | **offline** | — |
| 23 | `backtest` | | **offline** | — |

Engine 23 `backtest` lives in `research/` and is registered only in `OFFLINE_CHAIN`, which `cli/research.py` assembles. It never appears in `bootstrap.py`.

Note that 12 and 13 execute before 8 and 9, and that 17 executes before 5. The numbers are identifiers, not execution order.

Engine 6 is named `macro_context`, not `context`, so that it never reads ambiguously against the `context/` documentation directory.

**Engine 16 `decision` is a gate, by operator ruling 2026-09-16.** Three of its four inputs are
gates, so by the time it runs they have all already said yes — which is why "it combines their
outputs" was never a job. What it does is the check nothing else performs: **every approving
engine judged this tick's candidate**, the same pair and the same decision bar, with an approval
that carries a quantity. That is deterministic, it fails closed, and it can only make the system
less willing to trade, so it is a gate and is protected by invariant 4. It also *composes* the
order intent engine 18 reads, so execution depends on one typed contract rather than five engines'
keys — composition, not decision, and the engine's README says so in those words. Invariant 3
holds the condition; do not restate it here.

The Dissimilarity Index is not an engine. It lives inside `engines/prediction/` as a fitted artefact alongside the predictor, because it must be fitted on the predictor's training set. Its arithmetic is `modelling/di.py`, so the trainer fits and the engine scores with one implementation. **Engine 8 blocks on a DI refusal** under rule 6, reason code `di_refused`, and stays a non-gate in the table below: `is_gate` is the declaration `verify.py` checks against the Gate column, and rule 6 already lets any engine halt the tick. Operator ruling 2026-09-12; the reasoning is in `feature-specs/59-phase-5-rulings-into-the-documents.md`. The execution offset bandit is likewise not an engine; it lives inside `engines/execution/` with its state in the store.

## Per-engine directory

Every engine directory contains exactly three files:

- `engine.py` — the `BaseEngine` subclass
- `contracts.py` — pydantic models for what this engine puts in `state`
- `README.md` — purpose, inputs read from `state`, outputs written, gate conditions

The README is not optional. It is how the next agent understands the engine without reading the code.

## State keys

Each engine's `data` payload is typed in its own `contracts.py`. Orchestrator-level keys:

- `state["system"]` — the only persistent region. `mode` and `close_intent`. **Written only by the orchestrator**, in exactly two places: the command reader sets `mode` and `close_intent` at step 0, and step 4 clears `close_intent` once the manage chain reports the close finished. No engine writes it; any engine may read it.
- `state["cycle_id"]` — an integer, fresh per tick, minted by the orchestrator, restarting at 1 each run. It joins logs, decisions and SHAP rows **together with `context.run_id`**: on its own it is ambiguous across runs.
- `state["trading_blocked_by"]`, `state["block_reason"]`, `state["block_status"]` — the **primary** blocker: the first engine to block this tick, and what gates the opportunity chain. Fresh per tick, and all three absent on an unblocked tick. `block_status` is `BLOCK` or `ERROR`, added 2026-09-16 so engine 19 can tell an opportunity-chain engine that raised from one that refused without inferring it from an empty payload — which is also what a refusal missing its code looks like (rule 7, invariant 12).
- `state["guard_blockers"]` — every guard engine that blocked this tick, in chain order, each with its reason and status. The guard chain never breaks early, so there can be more than one. Engine 19 writes one `block_records` row per entry, `is_primary` on the first. An empty list on an unblocked tick, never absent.

`run_id` is `context.run_id`, nowhere else.

### Cross-chain keys the contract fixes

Most of an engine's `data` is its own business, typed in its own `contracts.py`. These fields are different: another chain depends on them, they cross an ownership boundary, or the orchestrator reads them. They are fixed here and may not be renamed without the lead.

| Key | Written by | Read by | Meaning |
|---|---|---|---|
| `state["market_sensor"]["bar_closed"]` | 3 `market_sensor` (A) | 5 `feature` (C) | A 15-minute decision bar closed on this tick |
| `state["position_manager"]["entry_orders_cancelled"]` | 21 `position_manager` (B) | orchestrator (Lead) | No resting entry order remains |
| `state["exit"]["positions_closed"]` | 22 `exit` (B) | orchestrator (Lead) | No open position remains |
| `state["position_manager"]["hold_reason"]` | 21 `position_manager` (B) | 19 `memory` (C), console | Why the manage chain placed no exit this tick; null when it did not hold |
| `state["scout"]["pair"]` | 7 `scout` (B) | 10 `cost` (B), 11 `risk` (B) | The candidate pair this tick, or absent when none qualified |
| `state["prediction"]["expected_move_pct"]` | 8 `prediction` (C) | 10 `cost` (B) | Expected move as an exact decimal string, before friction |
| `state["order_book"]["estimated_slippage_pct"]` | 9 `order_book` (C) | 10 `cost` (B) | Estimated slippage as an exact decimal string |
| `state["market_sensor"]["quotes"][pair]["spread_pct"]` | 3 `market_sensor` (A) | 4 `data_guard` (A), 10 `cost` (B) | Live top-of-book spread as an exact decimal string |
| `state["feature"]["pairs"][pair]` | 5 `feature` (C) | 7 `scout` (B), 6, 8, 12, 13 (C) | The feature row for every pair engine 3 published candles for, floats, `null` where a lookback was unfilled. Names and order from `modelling/features.py`. Present only on a tick where a decision bar closed |
| `state["prediction"]["is_buy"]` | 8 `prediction` (C) | 15 `skeptic` (C), 14 `adaptive_router` (C, Phase 6) | Whether the scored model called a BUY. **Absent when no model scored** — which is every refusal — so a consumer cannot read "engine 8 made no call" as "not a BUY". Phase 6, spec 95: it was `bool = False` published unconditionally, and engine 14 is its first reader outside a gate |
| `state["prediction"]["di"]`, `["di_threshold"]` | 8 `prediction` (C) | 14 `adaptive_router` (C, Phase 6), console | The Dissimilarity Index of this candidate against the active model's reference set. A refusal is a `BLOCK` with reason code `di_refused` and **no** `expected_move_pct`, so engine 10 fails closed on the absent key |
| `state["regime"]["label"]` | 12 `regime` (C) | 14 `adaptive_router` (C, Phase 6), console | `trending`, `choppy`, `high_volatility`, or `null` with a reason |
| `state["exit"]["closed_trades"][*]["net_proceeds"]` | 22 `exit` (B) | 19 `memory` (C) | Per closed trade, `qty × exit_price − exit_fee` as an exact decimal string: a fact about a sale engine 22 executed. Phase 6, spec 113, operator ruling 2026-09-17 |
| `state["position_manager"]["positions"][*]["value"]` | 21 `position_manager` (B) | 19 `memory` (C) | Per open position, `qty × last_price` as an exact decimal string, **present exactly when `last_price` is**. The per-row values sum to `positions_value` whenever that total is present. Phase 6, spec 113 |

**The exit-cycle equity row, ruled by the operator 2026-09-17.** On a tick where engine 22 closed
positions, engine 19's equity row must describe the account *after* those sales. Engine 1's balance
is from the start of the tick, engine 21's valuation is from before the sale, and the store's
position count is from after it — three moments that never coexisted, which is how the row came to
read 0 open positions beside a non-zero positions value. So on an exit tick engine 19 **filters and
sums**: engine 21's position rows minus every `position_id` engine 22 closed, and engine 1's cash
plus engine 22's `net_proceeds`; on every other tick it uses the totals as before. A remaining
position with no `value` means no equity row, exactly as an absent total does. The row records
`cash_source` (`cycle_start` or `after_exit`). No engine reads another engine's valuation method,
and no engine publishes a figure about positions it did not touch — an earlier design in which
engine 22 subtracted engine 21's marks was withdrawn for exactly that coupling.

**On the last four, added 2026-09-09.** B built engine 10 needing all four and could read only the fee tier's location from a spec, so it proposed paths as `Final` constants under a heading marking them unratified rather than inventing behaviour. Three are ratified as proposed. The fourth is **re-pointed**: B proposed `state["exchange"]["pairs"][pair]["spread_pct"]`, and it belongs on engine 3, not engine 1.

The line is that **engine 1 `exchange` is the account engine** — balances, fee tier, pair rules — **and engine 3 `market_sensor` is the market-data engine.** Spread is market data. The deciding argument is engine 4 `data_guard`: it blocks on stale data, a negative spread and a missing candle, and all three of those are market-data faults that should arrive from one place rather than two. `market_sensor` also already runs every tick in the guard chain ahead of `data_guard`, so nothing about the cadence needs to change — `quotes` is per-tick, alongside `bar_closed`, which is per-bar.

The three money fields are decimal **strings**, per rule 8. None of them may be a float.

`entry_orders_cancelled` and `positions_closed` are only meaningful while `close_intent` is set; absent or false always means "not finished", never "finished" — the same fail-closed default the gates use. `hold_reason` is the opposite: it is meaningful on ordinary ticks and is null during a liquidation, because a liquidation never holds. Name these fields when you refer to them; do not point at them by position, because this table gets appended to.

**The orchestrator holds the `Clock`.** It is constructed by the CLI, passed to the orchestrator, and used once per tick to stamp `context.now`. No engine ever sees it.

**`context.previous_now` is where the previous tick was, and it exists because an interval cannot be derived.** Added 2026-09-16, Phase 6, spec 85, by the lead; overturnable by the operator. An engine is stateless across cycles and `state` is fresh every tick, so "since the last tick" could only be written as `now − timeframes.loop_tick_s` — which is the previous tick's time *in a loop that ran on time*. `bar_closed_on` has used that device since Phase 2 and is sound, because it asks about an **index** and still fires exactly once when the loop runs late. An **interval** is not: if the loop overshoots, the trades inside the overshoot fall in no range any engine published, and a stop touched there is missed by engines 21 and 22. Found by A building engine 3's per-tick trade ranges and reported rather than worked around.

`None` means there is no previous tick — the first tick of a process, the first tick after a restart, or a context built by hand. **It is not zero and not "a moment ago."** An engine measuring an interval publishes nothing for that tick rather than guessing where the interval began; that is the fail-closed reading and it is also the honest description of a restart, which observed nothing while the process was down.

**A replay resuming a killed run may seed it; the daemon never does.** Lead decision D9 of 2026-09-19 (`docs/build-log/phase-7/overnight-decisions-2026-09-19.md`), for spec 131's kill-and-resume identity. The orchestrator's optional `previous_now` constructor argument sets the first tick's value to the last recorded tick's `now`. In replay the span between the two is history the replay client serves, so `None` would be a fabricated gap: the resumed run would miss a stop touched in its first minute, and the uninterrupted run would not. Live, nothing observed the span, so the daemon passes nothing and `None` stays the truth.

**`context.mode` is always the configured mode**, `paper`, `live` or `replay`, and never the run state (`idle`, `running`, `frozen`), which lives only in `state["system"]["mode"]`. Until 2026-09-19 the orchestrator put the run state into `context.mode` whenever it was not `idle`. No engine read it (finding F2 of the overnight log). A `previous_now` after `now`, or a naive one, is refused at construction: an interval running backwards is a clock fault, not a small number.
