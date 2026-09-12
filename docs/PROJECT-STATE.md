# ACSOE — Project State

**Adaptive Crypto Spot Opportunity Engine.** A single description of the system as it
exists today, for a reader who knows nothing about it.

This file states what is **built**, not how it was built. The narrative account of the
construction lives in `docs/build-log/`; the working record lives in
`context/progress-tracker.md`. Where a number here was measured rather than asserted, the
measurement is named.

Snapshot date: **2026-09-11.** Phases 0 to 4 of 9 are closed green. Phase 5 is next.

---

## 1. What ACSOE is and the question it asks

ACSOE is a fully automated spot trading system for Kraken, built as a Master's dissertation
project. It streams and records market data for every Kraken pair, builds 15-minute candles
from that stream, computes a tradable universe from live pair rules and the current account
balance, picks one candidate per decision bar, and puts that candidate through a chain of
independent gates. It buys only when the expected move beats every cost with a configured
margin to spare, holds with a profit target, a stop and a timeout, and records both the
trades it took and — equally — every candidate it refused, with a machine-readable reason.
It is long-only, spot-only, single-exchange, and runs in paper mode by default behind three
independent switches that must all be thrown before a real order can reach the exchange.

The question it asks is deliberately not the usual one. Most trading research asks whether
price can be predicted: it fits a model, reports an accuracy or a Sharpe ratio, and treats
transaction costs as a footnote applied at the end. ACSOE asks whether a prediction
**survives the cost of acting on it**. Kraken's fee schedule at the entry tier implies a
round-trip friction of roughly 1.25%, which against a 3% profit target means a break-even
win rate near 61% — so the interesting quantity is not whether a model beats a coin flip
but whether its edge is still positive once friction, slippage, spread and a hurdle
multiple have been subtracted from it first. The system is therefore built as rejection
machinery: most of its twenty-three engines exist to say no, nine of them contain no
machine learning at all, and no model output can override any gate. The single deliberate
override in the whole design is an emergency liquidation, which can only reduce exposure
and never open a position. That inverts the usual burden of proof, and it makes a negative
result a valid result: if the honest conclusion is that no net edge survives Kraken's fees
at this account size, the system is built to report that truthfully rather than bury it in
an optimistic backtest.

---

## 2. The twenty-three engines

Engines run in a fixed registry order within three runtime chains plus an offline chain.
The order is not alphabetical and not dependency-inferred; cheap deterministic checks run
before expensive model inference. The numbers are identifiers, not execution order — 12 and
13 execute before 8 and 9, and 17 executes before 5.

**Ten of the twenty-three are built.** Nine are registered in the runtime chains
(`src/acsoe/bootstrap.py`); engine 23 is registered only in the offline chain
(`src/acsoe/cli/research.py`).

| # | Name | What it does | Gate | Chain | Built |
|---|---|---|---|---|---|
| 1 | `exchange` | Fetches balances, fee tier and pair rules from Kraken each tick and publishes the account picture | | guard | **Yes** |
| 2 | `market_data_recorder` | Records raw WebSocket frames to append-only JSONL; derives the subscription scope from the quote currencies actually held | | guard | **Yes** |
| 3 | `market_sensor` | Builds 15-minute candles and quotes from the stream; owns the decision-bar clock (`bar_closed`) | | guard | **Yes** |
| 4 | `data_guard` | Blocks the tick when market data is stale, carries a negative spread, or is missing candles | **Y** | guard | **Yes** |
| 17 | `safety` | Account-level circuit breaker: drawdown, loss streak, error rate, sustained data outage. Freezes, or escalates to `close_all` | **Y** | guard | **Yes** |
| 5 | `feature` | Computes the per-pair feature vector on a closed bar; returns PASS when no bar closed, which stops the chain | | opportunity | No |
| 6 | `macro_context` | Reads BTC and ETH for market-wide context | | opportunity | No |
| 7 | `scout` | Builds the tradable universe from live pair rules, live prices and balance; publishes one candidate pair | **Y** | opportunity | **Yes** |
| 12 | `regime` | Classifies the market environment — trending, choppy, high volatility | | opportunity | No |
| 13 | `anomaly` | Refuses market conditions outside anything the system has seen | **Y** | opportunity | No |
| 8 | `prediction` | Predicts which of the three barriers is touched first; refuses to predict above the Dissimilarity Index threshold | | opportunity | No |
| 9 | `order_book` | Estimates slippage and depth from the live order book | | opportunity | No |
| 10 | `cost` | Computes friction from the live fee tier and spread; blocks when net edge does not clear the hurdle | **Y** | opportunity | **Yes** |
| 11 | `risk` | Sizes the position from equity and stop distance; refuses anything below `ordermin` or `costmin` | **Y** | opportunity | **Yes** |
| 14 | `adaptive_router` | Routes between models and execution strategies | | opportunity | No |
| 15 | `skeptic` | The meta-labelling model whose only job is to find reasons not to trade | **Y** | opportunity | No |
| 16 | `decision` | Assembles the final order intent from everything upstream | | opportunity | No |
| 18 | `execution` | Places the post-only limit entry, with the offset bandit | | opportunity | No |
| 21 | `position_manager` | Watches open positions and resting entry orders; cancels an entry that outruns its unfilled window | | manage | No |
| 22 | `exit` | Closes positions at target, stop or timeout, and liquidates on `close_all` | | manage | No |
| 19 | `memory` | The single writer of every relational row: blocks, rejections, positions, orders, trades, equity | | manage | **Yes** |
| 20 | `tournament` | Ranks and promotes trained model versions onto the leaderboard | | offline | No |
| 23 | `backtest` | Replay plus triple-barrier labelling — the dataset Phase 5 trains on | | offline | **Yes** |

Two things the table cannot show. The **Dissimilarity Index is not an engine**: it lives
inside `engines/prediction/` as an artefact fitted on the predictor's own training set,
because that is the only set it can honestly measure distance from. The **execution offset
bandit is likewise not an engine**: it lives inside `engines/execution/` with its state in
the store.

Every engine directory contains exactly three files — `engine.py`, `contracts.py` and a
non-optional `README.md`.

---

## 3. Locked decisions

Settled with evidence. Not to be relitigated; changing one requires the operator, not an
agent. Reproduced verbatim from `context/progress-tracker.md`.

- Kraken Pro, spot only. No margin, futures, leverage, or shorting.
- Fees read live from `TradeVolume`. Minimums read live from `AssetPairs`. Never hardcoded.
- Reference friction: ~1.25% round trip at tier 1, ~0.65% at tier 3.
- Break-even win rate: ~61% at tier 1, ~48% at tier 3.
- Decision bar 15 minutes; hold 2–12 hours; loop tick 1 minute.
- Triple-barrier labels: +3% / −1.5% / 48-bar timeout.
- Post-only limit entry, cancel if unfilled, never chase.
- Tradable universe computed per tick from `ordermin`, `costmin`, tick size, live spread and balance. No account-size thresholds.
- All Kraken quote currencies scanned; crypto-quoted pairs disabled by default.
- DI fitted on the predictor's training set, MinMax-scaled, rolling percentile threshold, 30-day per-pair window.
- DI threshold crossings also feed the regime engine.
- Alpha attribution uses the full equity curve including cash periods, not trade windows.
- Execution offset bandit pooled by spread tier, not per pair.
- Promotion metric haircut for the number of models tried.
- Backtest training window is the 90 days **before** each test window and nothing after it — past-only, never two-sided; retrains weekly during walk-forward. Operator ruling 2026-09-12; the earlier wording *capped at a rolling 90 days* was read as two-sided and is retired.
- Decision bars before `dataset.decision_start_date` (2017-01-01) are excluded from the labelled dataset. A tradability exclusion, not a data-quality one: the 2013–2016 bars are real but describe a market no position could have been taken in. Operator ruling 2026-09-12.
- Every pair that clears the archive's two-year rule is in the dataset, thin ones included. `dataset.min_labelled_rows` is the per-pair floor, 0 today (no floor); a cross-sectional model may want one, and the decision is deferred behind that named knob. Operator ruling 2026-09-12.
- An LLM is not the predictor. Any alternative method must first clear the fee hurdle.
- Build order is structure, then interface, then backend.
- Console is built against the real schema with seeded fake data, so no rework when real data arrives.
- Paper mode until a validated model exists. A readiness gate, not an account-size gate.

---

## 4. Runtime architecture

### The loop

One process — the daemon, `acsoe engine` — runs a tick every `timeframes.loop_tick_s`
(60 seconds). Each tick reads pending commands, then runs three chains in a fixed order.
Candidates are born only on a closed 15-minute decision bar, so on roughly fourteen ticks
in fifteen the opportunity chain stops immediately at engine 5.

### The three chains, and why each exists

**Guard chain — engines 1, 2, 3, 4, 17. Every tick, every mode. Never breaks early.**
Ingestion plus the account-level circuit breaker. It runs in `idle` and `frozen` as well as
`running`, because freeze must stop trading without stopping data collection: order-book
and spread history cannot be recovered retroactively, so an hour not recorded is an hour of
cost-model input that money cannot buy back later. The chain also never breaks on a block —
a bad-data block from `data_guard` must not stop `safety` from evaluating. The first
blocker is the **primary** one and is what gates the opportunity chain; **every** blocker is
recorded. Engine 17 `safety` is last, and last is load-bearing: it reads the current tick's
`trading_blocked_by`, which `data_guard` sets, so it cannot precede the engine whose verdict
it counts.

`safety` is a guard rather than a judgement because its question is about the *account* —
how far is equity down, how many losses in a row, how many errors this hour — and must be
answered on ticks where there is no candidate at all. Placed at the end of the opportunity
chain it would run only when every other gate had already passed, and an account bleeding
while every candidate is rejected by the cost gate would never trip the breaker.

**Opportunity chain — engines 5, 6, 7, 12, 13, 8, 9, 10, 11, 14, 15, 16, 18. Only when the
mode is `running` and nothing has blocked. May stop early.** This is the rejection
pipeline. It stops at the first block, and it stops on a PASS, which means no candidate
this cycle. Currently registered as `7 → 10 → 11`: the missing engines sit between them and
the orchestrator skips what is not registered, so it is registry order with holes rather
than a different order. `scout` must run first because 10 and 11 both read
`state["scout"]["pair"]` and neither invents one when it is absent; `cost` runs before
`risk` because the cheaper question comes first and there is no sense sizing a position the
edge cannot pay for.

**Manage chain — engines 21, 22, 19. Every tick, every mode. Never stops.** Watches
positions, exits them, records everything — including on the fourteen ticks in fifteen
where no bar closed. Currently registered as `19` alone; 21 and 22 are Phase 6. Engine 19
runs **last**, because it records what 21 and 22 did on this tick and an engine cannot
record a decision that has not been taken yet.

**When the guard rejects the data, the manage chain holds.** If
`state["trading_blocked_by"] == "data_guard"`, engines 21 and 22 place **no exit** — a
target or stop computed from exactly the data the guard just rejected would be a fabricated
trigger. They still run, because engine 19 must still record the tick, and because holding
is itself a fact worth recording. The hold suppresses *exits only*: engine 21 still cancels
an entry order that has outrun its unfilled window, because that is a decision about elapsed
time rather than price and it reduces exposure. The hold is bounded — `safety` counts
consecutive `data_guard` ticks from the store and escalates past
`safety.max_consecutive_data_blocks`, so a feed outage cannot hold a position indefinitely.

**Offline chain — engines 20 and 23.** Assembled in `cli/research.py` and invoked only by
`acsoe research`. It is **never** in `bootstrap.py`, and that is the entire mechanism
keeping architecture invariant 5 true: the live loop path never imports from `research/`.

### State lifetime

`state` is a **fresh dict every tick**. Exactly one region survives:

```python
state["system"] = {          # persistent — carried across ticks by the orchestrator
    "mode": "idle",          # idle | running | frozen
    "close_intent": False,   # set by the command reader; cleared by the orchestrator
}                            #   only after the manage chain reports the close finished
state["cycle_id"] = ...      # fresh each tick, minted by the orchestrator, restarts at 1
```

Everything else — every engine's output key, `trading_blocked_by`, `block_reason`,
`guard_blockers` — is gone at the end of the tick. A manage-chain engine that needs last
cycle's decision reads it from the store, never from `state`, because on fourteen ticks in
fifteen the opportunity chain did not run and those keys do not exist.

`state["system"]` is written **only by the orchestrator**, in exactly two places: the
command reader sets `mode` and `close_intent`, and the final step clears `close_intent`
once the manage chain reports the close finished. No engine writes it; any engine may read
it. Engine 17 `safety` therefore cannot freeze the system directly — it writes a command
row instead.

`run_id` lives only on `context.run_id`, never duplicated into `state`. **A tick is
identified by `(run_id, cycle_id)`, never by `cycle_id` alone**, because `cycle_id` restarts
at 1 with each process. Cross-restart sequences are ordered by `ts`, never by `cycle_id`.

**At startup `mode` is always `idle`** and is never restored from the store. A daemon that
crashed while trading comes back not trading: the manage chain still runs so open positions
stay watched, but nothing new opens until the operator activates again.

### The command table

The console writes rows; the daemon reads them at the top of every tick, before the guard
chain. Engine 17 `safety` is the second writer.

| Command | Effect |
|---|---|
| `activate` | Mode goes `idle` → `running`. The opportunity chain begins running. |
| `freeze` | Mode goes to `frozen`. The opportunity chain stops. The guard chain keeps recording and keeps running `safety`; the manage chain keeps managing open positions. Freeze never stops data collection. |
| `close_all` | Mode goes to `frozen` and `close_intent` is set. Engine 21 cancels every resting entry order and engine 22 exits every open position as a taker. The orchestrator clears the intent only when both report done, and retries next tick if not. This is the one operation that proceeds even when `data_guard` has blocked and even when the balance or book fetch is failing, on cached data past its TTL — unknown exposure is worse than a bad fill. |

**The kill switch is `close_all`. There is no fourth mechanism.**

**Consumption is two-phase, so a crash cannot swallow a kill switch.** Each row carries
`claimed_at` and `consumed_at`. The reader stamps `claimed_at` and applies the effect;
`consumed_at` is stamped only when the effect is complete — immediately for `activate` and
`freeze`, which are pure mode changes, and for `close_all` only when every resting order is
cancelled and every position closed. A row with `claimed_at` set and `consumed_at` null is
an interrupted command, and **every such row is re-applied at startup before the first
tick**. `claimed_at` also gives idempotency: a claimed row is never applied twice within a
run. An unrecognised command is ignored and logged as a warning; it never blocks the loop.

### What the daemon owns and what the console owns

They are **separate processes sharing one SQLite database**, and neither calls the other.

The **daemon** (`acsoe engine`) owns the loop, the injected clock, the Kraken clients and
every credential. It is the only writer of `state`, the only reader of the command table,
and — through engine 19 — the only writer of relational rows.

The **console** (`acsoe console`) is FastAPI serving one HTML page, vanilla JavaScript and a
WebSocket: no build step, no framework, no npm. It is **read-only over a read-only SQLite
connection**, proved read-only by attempting real writes, with one exception — the three
commands, which write rows to the `commands` table behind a SQLite authorizer that denies
every table but that one. **The console holds no credentials and can never place an order.**
It learns about change by polling a monotonically increasing `MAX(updated_at)` watermark at
`console.poll_interval_ms` and pushing over the WebSocket only when the watermark moves — no
triggers, no file watching, no polling from the browser. Live mode changes the entire frame
of the page: a 3px amber border around the viewport, in a colour reserved for that one
meaning and used nowhere else in the interface.

The console's honest default state is *nothing qualified today*, and the design treats that
as information rather than as failure.

---

## 5. Storage

SQLite holds everything relational. Large arrays never go into SQLite and relational
records never go into Parquet.

| Data | Store | Notes |
|---|---|---|
| Raw market recordings | JSONL in `data/raw/` | Append-only, daily rotation, compacted to Parquet |
| Built candles, feature snapshots | Parquet in `data/derived/` | Rebuildable from raw |
| Historical OHLCVT archive | CSV in `data/historical/` | Operator-supplied, with a `PROVENANCE.json` |
| Trades, rejections, runs, leaderboard | SQLite | Small, relational, queried constantly |
| Trained models | Files in `models/` | Versioned by training run id, never overwritten |
| SHAP explanations | Parquet, joined by decision id | One row per decision |

**Money is stored as an exact decimal string in a column declared `ANY` with
`CHECK (typeof(col) = 'text')`.** This looks wrong and is not: a column declared `TEXT` has
TEXT *affinity*, so an inserted float is silently converted to text **before** any CHECK
runs, and `typeof()` then reports `'text'`. Declaring `TEXT` enforces nothing, and STRICT
does not close it either. `ANY` is the one declaration that stores a value as given, so the
CHECK sees a real REAL and rejects it. Every table is STRICT. Timestamps are INTEGER
microseconds since the Unix epoch, UTC, taken from `context.now` — nothing in the package
reads a clock.

### `runs` — written by the orchestrator at startup

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `run_id` | TEXT NOT NULL UNIQUE | One per daemon process |
| `mode` | TEXT NOT NULL | `paper` \| `live` \| `replay` |
| `started_at` | INTEGER NOT NULL | |
| `ended_at` | INTEGER | |
| `acsoe_version` | TEXT | |
| `config_digest` | TEXT | |
| `system_mode` | TEXT | `idle` \| `running` \| `frozen`, or NULL. Written by the `core/` command reader **for the console to read**, never read back into `state` |
| `system_mode_at` | INTEGER | When that mode was written; separate from `updated_at`, which any write bumps |
| `updated_at` | INTEGER NOT NULL | |

NULL `system_mode` means *no daemon has written a mode for this run yet*, which the console
renders as an idle reading. That is a distinct fact from `'idle'`, which means a daemon
actively reported being idle, and the two are deliberately not collapsed.

### `commands` — written by the console and by engine 17 `safety`; read by the orchestrator

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `command` | TEXT NOT NULL | **No CHECK constraint** — an unrecognised command must stay reachable and testable |
| `source` | TEXT NOT NULL | `console` \| `safety` |
| `reason` | TEXT | |
| `payload` | TEXT | |
| `created_at` | INTEGER NOT NULL | |
| `created_by_run_id` | TEXT | |
| `claimed_at` | INTEGER | Stamped when the reader applies the effect |
| `claimed_by_run_id` | TEXT | |
| `consumed_at` | INTEGER | Stamped only when the effect is complete |
| `updated_at` | INTEGER NOT NULL | |

### `block_records` — written by engine 19 `memory`, one row per guard blocker per **tick**

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `cycle_id` | INTEGER NOT NULL | |
| `run_id` | TEXT NOT NULL | |
| `ts` | INTEGER NOT NULL | |
| `blocked_by` | TEXT NOT NULL | Engine name |
| `block_reason` | TEXT NOT NULL | |
| `is_primary` | INTEGER NOT NULL | 1 for the blocker that set `trading_blocked_by`; a partial unique index on `(run_id, cycle_id) WHERE is_primary = 1` makes a second primary fail at the database |
| `status` | TEXT NOT NULL | `BLOCK` \| `ERROR` |
| `updated_at` | INTEGER NOT NULL | |

This is its own table rather than a column on `rejections` because a rejection is one
*candidate* refused and a block record is one *tick* on which trading was blocked — and most
blocked ticks never had a candidate at all. Folding them together would inflate the
counterfactual dataset that is the point of the whole exercise: anyone counting refused
trades would be counting feed outages too. They join on `(run_id, cycle_id)`.

### `equity_snapshots` — written by engine 19 `memory`, one row per tick

`id`, `cycle_id`, `run_id`, `ts`, `currency`, `equity`*, `peak_equity`*, `cash`*,
`positions_value`*, `unrealised_pnl`*, `realised_pnl_cum`*, `open_position_count`,
`updated_at`. (`*` = exact decimal string.) Unique on `(run_id, cycle_id)`.

The cash and unrealised components are stored rather than derived from trades because the
Phase 7 alpha attribution reads the full curve **including cash periods**.

### `positions` — written by engine 19 `memory`

`position_id` (PK), `run_id`, `cycle_id`, `pair`, `base`, `quote`, `side` (`long` only),
`status` (`open` \| `closed`), `qty`*, `entry_price`*, `target_price`*, `stop_price`*,
`timeout_at`, `entry_userref`, `last_price`*, `unrealised_pnl`*, `opened_at`, `closed_at`,
`trade_id`, `updated_at`.

A partial unique index on `pair WHERE status = 'open'` enforces invariant 6 — one open
position per pair — at the database rather than by convention.

### `orders` — written by engine 19 `memory`

`userref` (PK), `order_id`, `run_id`, `cycle_id`, `position_id`, `pair`, `side`
(`buy` \| `sell`), `intent` (`entry` \| `exit`), `order_type` (`limit` \| `market`),
`oflags`, `status` (`pending` \| `resting` \| `filled` \| `cancelled` \| `rejected` \|
`expired`), `qty`*, `limit_price`*, `filled_qty`*, `avg_fill_price`*, `fee`*, `placed_at`,
`closed_at`, `updated_at`.

Keyed by `userref` so invariant 8's idempotency check — never place an order without
checking whether that userref already exists — is a primary-key lookup rather than a scan.

### `trades` — written by engine 19 `memory`, one row per closed round trip

`trade_id` (PK), `position_id`, `run_id`, `cycle_id`, `pair`, `base`, `quote`, `side`,
`qty`*, `entry_price`*, `exit_price`*, `entry_fee`*, `exit_fee`*, `entry_userref`,
`exit_userref`, `opened_at`, `closed_at`, `outcome` (`target` \| `stop` \| `timeout` \|
`liquidation`), `realised_pnl`*, `realised_pnl_pct`*, `realised_pnl_quote`*,
`reporting_currency`, `fx_rate_entry`*, `fx_rate_exit`*, `fallbacks_used` (JSON array),
`updated_at`.

Both the quote-currency and reporting-currency PnL and both FX rates are recorded because
invariant 7 requires FX exposure to be recorded per trade rather than silently absorbed into
PnL. `fallbacks_used` exists because invariants 2 and 14 require any tolerated fetch failure
or paper-mode fallback to be recorded on the resulting trade, so a fill is never mistaken
for one priced on good data.

### `rejections` — written by engine 19 `memory`, one row per refused candidate

`id`, `cycle_id`, `run_id`, `ts`, `pair`, `rejected_by`, `reason_code`, `reason`,
`expected_move_pct`*, `friction_pct`*, `net_edge_pct`*, `hurdle_pct`*, `candidate_score`
(REAL), `shap_ref`, `details`, `updated_at`.

`reason_code` is machine-readable for research; `reason` is written for the operator,
because the console renders it — *"Net edge −0.21% after fees"*, not `cost_gate_fail`. The
economics columns are exact decimal strings: they are derived from live fees and they gate a
trade, so they are money, not statistics.

### `leaderboard` — engine 20 `tournament` when built; currently written only by the seed generator

`id`, `model_id`, `model_version`, `training_run_id`, `trained_at`, `fold`, `n_trades`,
`win_rate`, `sharpe`, `deflated_sharpe`, `alpha`, `beta`, `brier` (all REAL — they are
statistics), `net_pnl`* , `reporting_currency`, `promoted`, `notes`, `updated_at`.

### Writers, at a glance

| Table | Written by |
|---|---|
| `runs` | The orchestrator (`core/`), at startup and on each mode change |
| `commands` | The console, and engine 17 `safety`. Read only by the orchestrator |
| `block_records`, `equity_snapshots`, `positions`, `orders`, `trades`, `rejections` | Engine 19 `memory`, and nothing else |
| `leaderboard` | Engine 20 `tournament` — not yet built |

**Engine 19 is the single writer of relational rows.** Engine 22 `exit` closes a position on
the exchange; `memory` records that it happened. One writer is what makes the manage chain's
"always runs" guarantee sufficient for invariant 12, and it is why `memory` sits underneath
`safety`'s entire input surface.

---

## 6. Config

`config/default.yaml`. Percentages are decimals; durations are seconds unless the key says
otherwise; money is a quoted string parsed as `Decimal`.

**Nothing the exchange can tell us appears in this file** — no fee, no order minimum, no
tick size, no precision. Those are fetched at runtime, every time.

A key whose value is `null` is **OPERATOR REQUIRED**: the context files name it but never
specify it, and it is trading behaviour, so no agent may invent one. The loader refuses to
start while any is null, naming the key. As of 2026-09-08 there are none left — the operator
supplied all nine — but the refusal machinery stays, because it is what protects the tenth
such key. All operator-chosen values below are explicitly **provisional**: starting values
that make the system runnable, to be revised once Phase 3's economics are measured rather
than assumed.

| Key | Value | Chosen by |
|---|---|---|
| `mode` | `paper` | Lead |
| `console.port` | `8765` | Lead |
| `console.poll_interval_ms` | `500` | Lead |
| `console.stale_after_ms` | `120000` | Lead |
| `logging.level` | `INFO` | Lead |
| `logging.retention_days` | `14` | Lead |
| `timeframes.decision_bar_s` | `900` | Locked decision |
| `timeframes.loop_tick_s` | `60` | Locked decision |
| `barriers.target_pct` | `0.03` | Locked decision |
| `barriers.stop_pct` | `0.015` | Locked decision |
| `barriers.timeout_bars` | `48` | Locked decision |
| `safety.max_consecutive_data_blocks` | `15` | Lead (invariant 14) |
| `safety.max_drawdown_pct` | `0.10` | **Operator** 2026-09-08 |
| `safety.max_consecutive_losses` | `5` | **Operator** 2026-09-08 |
| `safety.error_rate_window_s` | `3600` | Lead — specified as "the trailing hour" |
| `safety.max_errors_in_window` | `20` | **Operator** 2026-09-08 |
| `trading.hurdle_multiple` | `1.5` | **Operator** 2026-09-08 |
| `trading.risk_fraction_per_trade` | `0.01` | **Operator** 2026-09-08 |
| `trading.max_concurrent_positions` | `3` | **Operator** 2026-09-08 |
| `trading.entry_unfilled_window_s` | `300` | **Operator** 2026-09-08 |
| `trading.base_reporting_currency` | `USD` | **Operator** 2026-09-08 |
| `trading.allow_crypto_quoted` | `false` | Lead (invariant 7) |
| `trading.stable_quote_currencies` | `USD, EUR, GBP, CAD, AUD, CHF, JPY, USDC, USDT` | **Operator** 2026-09-10 |
| `paper.starting_balances` | `{USD: "5000.00"}` | **Operator** 2026-09-08 |
| `kraken.rest_capacity` | `15` | Lead |
| `kraken.rest_refill_per_s` | `0.5` | Lead |
| `kraken.rest_timeout_s` | `10` | Lead |
| `kraken.cache_ttl_s.asset_pairs` | `300` | Lead 2026-09-10 |
| `kraken.cache_ttl_s.trade_volume` | `60` | Lead 2026-09-10 |
| `data_guard.max_data_age_s` | `120` | **Operator** 2026-09-09 |
| `market_sensor.published_bars` | `200` | Lead — a plumbing bound, not a trading threshold |
| `backtest.training_window_days` | `90` | Locked decision |
| `backtest.retrain_interval_days` | `7` | Locked decision |
| `backtest.embargo_bars` | `48` | Lead 2026-09-11 — **provisional**, flagged to the operator |
| `dataset.decision_start_date` | `"2017-01-01"` | **Operator** 2026-09-12 — a tradability cutoff, not a data-quality one |
| `dataset.min_labelled_rows` | `0` | **Operator** 2026-09-12 — no floor today; 0 rather than null because a null key stops the process at load |
| `seeds.global` / `seeds.train` / `seeds.seed_generator` | `20260908` | Lead |

Three notes that matter more than their line count suggests.

**The `kraken.*` values are our own self-imposed request budget, not a claim about what
Kraken permits.** A remembered published rate limit is exactly the stale knowledge this
project refuses to encode. Deliberately conservative, and flagged for revision against the
documented limits before Phase 8.

**`cache_ttl_s` is not the last-known-good retention.** A cache stale beyond its TTL counts
as a *failed fetch* under invariant 2: it is not returned, and in live mode the trade blocks.
The last-known-good retention in `clients/kraken/` keeps the same values forever, past any
TTL, and may be read only by invariant 14's emergency liquidation. Two mechanisms, two
readers; they must not be merged.

**Two arithmetic consequences of the operator's values, recorded before they surprise
anyone.** First, at tier 1 nothing clears the cost gate *by construction*: invariant 5
requires `net_edge > hurdle_multiple × friction`, which at `hurdle_multiple: 1.5` needs an
expected move above `2.5 × 1.25% = 3.125%` — and the target barrier is 3.0%. Phase 6 must
not read zero trades at tier 1 as a bug. Second, `max_concurrent_positions: 3` is inert at
this balance: 1% of $5,000 is $50, a 1.5% stop implies ~$3,333 of notional, and three
positions would need ~$10,000 against a $5,000 balance — **the balance binds first and
concurrency is effectively 1**.

---

## 7. What is green, and what is not

A phase is green only when `python scripts/verify.py --phase N` passes every criterion.
`docs_vocabulary` and `toolchain_green` are registered for **every** phase; the rest are
phase-specific.

### Gate output, as last recorded

| Phase | Criteria | Result |
|---|---|---|
| 0 — Structure | 7 | **7 PASS, 0 FAIL, 0 PENDING** |
| 1 — Interface | 10 | **10 PASS, 0 FAIL, 0 PENDING** |
| 2 — Data spine | 9 | **9 PASS, 0 FAIL, 0 PENDING** |
| 3 — Economics | 9 | **9 PASS, 0 FAIL, 0 PENDING** |
| 4 — Memory and replay | 10 (+1 `--live`) | **9 PASS, 0 FAIL, 0 PENDING** as last run on 2026-09-11, before `walkforward_trains_on_the_past_only` was added; the full gate has not been re-run since. On 2026-09-12 every Phase 4 criterion was run directly against the repository and passed, and `tests/verify/test_phase4_criteria.py` (91 tests, including the new criterion's mutation proofs) passed |
| 5 — Models | — | Not started |
| 6 — Decision and execution | — | Blocked on 5 |
| 7 — Evaluation | — | Blocked on 6 |
| 8 — Live readiness | — | Blocked on 7 |

**Suite:** `pytest tests/` last reported **1674 passed, 1 skipped**, exit 0, across 66 test
files. `mypy --strict src/ scripts/` clean; `ruff check src/ tests/ scripts/` clean. These
gates were **not re-run for this document** — the figures are the previous session's, and
the caveat immediately below applies to all of them.

### The caveat, which is not a formality

**`toolchain_green` is intermittently red on a quiescent tree and nobody can explain it.**
On a tree with no agent running, `git status` clean and HEAD committed, running the five
phase gates back to back has produced three *different* single test failures — one per
phase, never the same test, functionally unrelated to each other (a config refusal, an
import-boundary scan, a store permission check, a labelling seam) — plus one
`0xC0000409 STACK_BUFFER_OVERRUN` process crash. In the same conditions, `pytest tests/`
run **directly** is green, and `verify.py --phase 1` run **alone** is green twice. The
failures appear only inside `toolchain_green`'s subprocess during a back-to-back sequence of
verify runs. All four agents hit this during Phase 4 and none could characterise it.

Three mechanisms have been deliberately kept apart rather than charged to one cause, because
this project has already paid for that mistake once: (1) a workspace sweeper that deleted
live databases, diagnosed and fixed; (2) a genuine native fault on this machine — a process
*death*, open and unexplained since Phase 2, seen inside pydantic-core, SQLite's C
extension, pure-Python pyyaml and CPython's own `ast.walk`; and (3) this, a different single
test failure on a quiescent tree with **no** process death, which is none of the above.

Why mechanism 3 stays unexplained is itself understood: inside `toolchain_green` the
criterion's one line **is** the only record, because the captured output is reduced to its
last three lines. That survives a `FAILED`, where pytest names the tests. It does not
survive an `ERROR`, where the traceback names the fixture that raised — exactly what an
intermittent fault needs. Every observation anyone has made of this has been a summary with
the diagnosis already discarded. The fix is small and is not yet authorised.

**The honest reading, stated plainly because it bears on every claim above: until mechanism
3 is understood, a phase gate carries a probability rather than a verdict.** A green run is
evidence that the suite passed *that time*. The obvious response — re-running until green —
is precisely the diagnostic that cannot fail, and is explicitly not what was done. Phase 4
is reported as *green on its criteria and intermittently red on the suite*.

What is unaffected is worth stating with equal precision: none of the fault sites is in a
code path that runs in production. They are the seed generator, the test harness and the
verifier. No engine, no store write on the live path and no orchestrator tick has ever
exhibited it. **The limitation is on the evidence-gathering apparatus, not on the system
under test.**

### Every criterion, by name

**Registered for every phase**

| Criterion | What it asserts |
|---|---|
| `docs_vocabulary` | No retired term appears in the documents, with the retired-term table parsed rather than hardcoded |
| `toolchain_green` | The three toolchain commands pass, with one retry reserved for a crash and never for a verdict |

**Phase 0 — Structure**

| Criterion | What it asserts |
|---|---|
| `orchestrator_empty_registry` | A tick over an **empty** registry completes cleanly and blocks nothing |
| `db_migrates_from_empty` | The migrations build the documented table set from an empty file |
| `seed_fixtures_present` | The seed produces all six `safety` fixtures, each overshooting its threshold rather than sitting on it |
| `record_sample_valid` | The committed recorder sample parses, carries a genuine `gap` marker, and contains no secret-shaped key |
| `is_gate_matches_registry` | Every registered engine's `is_gate` matches the Gate column of the registry table |

**Phase 1 — Interface**

| Criterion | What it asserts |
|---|---|
| `console_renders_seeded_screens` | Every screen answers over a seeded database |
| `console_websocket_pushes_on_change` | A push arrives **because** the database changed, and not otherwise |
| `console_commands_write_rows` | Activate, Freeze and Close-all each write exactly one correct row |
| `console_live_frame_amber` | The one bold move: a 3px `--live` frame in live, and no border in paper |
| `console_tokens_no_raw_hex` | Tokens only, declared once; `tokens.css`'s `:root` block is the one exception |
| `console_tabular_figures` | `font-variant-numeric: tabular-nums` on every numeric element, by one mechanism |
| `console_focus_and_reduced_motion` | The quality floor: a visible focus ring, and reduced motion honoured |
| `console_restart_banner` | `Idle — restarted, not trading` when the daemon's `run_id` has changed |

**Phase 2 — Data spine**

| Criterion | What it asserts |
|---|---|
| `commands_round_trip` | The real `StoreClient` — not a double — driven through `activate`, `freeze` and `close_all`, with the mode changed and the row consumed |
| `recording_span_continuous` | At least 24 continuous hours, with **every break accounted for** |
| `candles_match_kraken_ohlc` | Built 15-minute candles against Kraken's own OHLC, for three pairs |
| `data_guard_blocks_bad_data` | Injected stale, negative-spread and missing-candle data each block; clean data passes |
| `historical_loader_reports_gaps` | A fabricated archive with a known number of holes reports exactly that number |
| `console_shows_live_rows` | The console renders rows a daemon wrote, not only rows the seed wrote |
| `console_reads_persisted_mode` | `Running` and `Frozen` in the band, from a mode a **real daemon wrote** |

**Phase 3 — Economics**

| Criterion | What it asserts |
|---|---|
| `cost_gate_uses_live_fee_tier` | Net edge moves with the fee tier the client reports, and the gate blocks below the hurdle |
| `risk_rejects_sub_ordermin` | A size one increment below `ordermin` is refused, and no quantity comes back |
| `universe_varies_with_balance` | The tradable universe is smaller at $10 than at $5,000, over one fixture set |
| `safety_freezes_on_drawdown_without_opportunity_chain` | The breaker freezes on the seeded drawdown on a tick the opportunity chain never ran |
| `safety_escalates_on_sustained_outage` | `close_all` on the tick after the limit, and nothing on the tick at it |
| `safety_inputs_all_from_the_seed` | Every one of `safety`'s six inputs comes from the store, and none from `state` |
| `phase_3_gates_have_both_tests` | Each of engines 7, 10, 11 and 17 has a test proving it blocks and one proving it passes |

**Phase 4 — Memory and replay**

| Criterion | What it asserts |
|---|---|
| `memory_records_every_blocker` | Engine 19 writes one `block_records` row per entry in `state["guard_blockers"]` |
| `memory_writes_safety_inputs_live` | `safety` reading engine 19's **live** rows reaches the seed's six totals |
| `rejections_survive_restart` | A rejection written under one `run_id` is intact after a restart under another |
| `labelled_sample_replayed_from_archive` | `tests/fixtures/labelled_sample.parquet` is a real replay, not a hand-written file |
| `labeller_matches_hand_verified_labels` | The labeller reproduces every row of the hand-verified fixture, exactly |
| `walkforward_folds_purged_and_embargoed` | A straddling label window is purged, and an embargoed row is dropped — by identity |
| `walkforward_trains_on_the_past_only` | On every rolling fold, every training row's decision bar and label window end precede the test window, and the rows after it are counted and refused. Operator ruling 1, 2026-09-12 |
| `console_history_reads_real_rows` | The history screen renders rows a live engine 19 wrote, not the seed's |
| `replay_full_archive` | `--live` only: replay the operator's real archive and report what it held. Never required for green; reports PENDING when no archive is present |

---

## 8. Open items

Everything below is deferred, unratified, or a deliberate absence. Nothing here is hidden in
a commit message or a handoff box; this is the list.

### Deferred decisions

**The console's scan tally.** Engine 7 `scout` publishes `scanned`, `entered` and a
per-reason `excluded` tally into `state["scout"]`, where they live for exactly one tick —
and **no column in any table has room for any of the three**. Engine 19 can only write what
the schema holds, so the console's empty state still shows no count. Three options exist,
and the one that looks cheapest is the one that was refused: writing the tally into
`rejections.details` as JSON puts a tick-level fact in a candidate-level table, and anyone
counting refused trades then counts it — invariant 12's table meaning different things to
different readers. Deferred because that is invariant 12 territory rather than a console
nicety. Deferring is reversible; a table whose rows mean two things is not. Phase 7's
attribution is the natural forcing function.

**`mypy --strict` is not widened to `tests/`.** Roughly 1,680 test functions would each need
a return annotation. The hole is stated rather than implied, and a test asserts the
exclusion, so the next person to "fix" it meets a red and a decision rather than a silent
scope change.

**A per-pair floor on labelled rows.** Eleven of the 234 pairs carry fewer than 20,000
labelled rows, two of them under 5,000 (section 10). The operator ruled on 2026-09-12 to keep
them: `dataset.min_labelled_rows` exists, reads `0`, and engine 23 reports by name any pair it
leaves out. A cross-sectional model may want a floor, and if it does the decision is one edit
to a named knob rather than a question nobody wrote down.

**The `toolchain_green` evidence fix.** Writing the failing tool's full captured output to a
file, rather than keeping its last three lines, is what would make mechanism 3 diagnosable.
Small, identified, and awaiting authorisation because it needs its own mutation proof and
its own five gate runs.

### Recorded absences — things deliberately not built, which must not be read as choices

**Engine 7 `scout` has no ranking score.** Invariant 4 says candidate ranking is "a
deterministic score over features"; features are engine 5, which is Phase 5. The operator's
ruling, verbatim, because it belongs in the record: *a deterministic score over features is
meaningless before features exist, and a placeholder score would be a check whose output
resembles the claim while the claim is untrue.* So the universe is ordered **alphabetically**
— equal treatment of every pair when nothing yet distinguishes them — behind one named
function, `rank_universe` in `engines/scout/contracts.py`, which exists as a separate
function for that reason and no other. **An agent arriving in Phase 5 must not read
alphabetical ordering as a choice anyone defended.**

There is a trap attached to it. The engine builds its scan set as
`sorted(set(rules) | set(quotes))`, so `rank_universe` is always handed an already-ordered
sequence, and a ranking that merely preserved arrival order would still answer alphabetically
end to end. Whoever replaces the placeholder must test `rank_universe` **directly**, on input
where arrival order and intended order disagree on every element. An end-to-end fixture
cannot see the difference.

**The SHAP view renders an honest empty state.** `rejections.shap_ref` points at a Parquet
artefact the training pipeline does not write until Phase 5. A placeholder chart is banned.

**The console's stage count refuses to show a zero**, because a zero there reads as *no pair
qualified*, which is a result, when the truth is that nobody counted.

### Provisional values

`backtest.embargo_bars: 48`, `market_sensor.published_bars: 200` and both `kraken.cache_ttl_s`
keys are lead-chosen and flagged to the operator. All nine operator-chosen values are
explicitly starting values, subject to revision once the economics are measured. The embargo
is the one that decides whether a model is honestly validated: it is a leaf key, so
`Config.get` returns `None` rather than raising if it is ever removed, and **whatever reads
it must refuse a `None` explicitly and must never treat it as zero.** A zero or absent
embargo is exactly the Phase 4 defect that looks like success.

### Carried obligations

- **Replace the cycle feed's full scan of `block_records` with a most-recent-N read.**
  Harmless while the table held a seed; engine 19 now writes a row per guard per tick, which
  is when it stops being harmless.
- **The branch-coverage backlog**, which was recorded in a handoff box and nearly lost:
  `clients/kraken/contracts.py::_to_money` (4 branches), `limiter.py::acquire` (the
  `cost <= 0` guard), `engines/market_data_recorder/contracts.py::validate_line` (1),
  `platform/config.py` (5), and `clients/store/migrations.py::discover_migrations` (five
  refusal branches raising `MigrationError`, plus a sixth path for the non-`.sql` skip).
- **`scripts/record.py` should be left running, permanently.** Order-book and spread history
  cannot be recovered retroactively — Kraken's free archives carry OHLCV and no bid, ask,
  spread or depth — so every hour the recorder is not running is an hour of cost-model input
  that money cannot buy back. Engine 9 `order_book` and the spread half of engine 10 `cost`
  have nothing else to read. Note it has **no working graceful shutdown on Windows**:
  `loop.add_signal_handler` raises on the Proactor loop, so a kill has to be forced. The
  archive is append-only and every line is flushed, so a forced kill costs at most a partial
  final line.
- **`RUF001` on `tests/console/test_format.py` is suppressed deliberately.** `U2212 = "−"`
  must be the U+2212 glyph: it is the fixture for the minus-sign rule, and "correcting" it to
  an ASCII hyphen would make the test pass against the exact character it exists to reject.

### Known risks

- **Historical archives carry no order book or spread.** Engine 9 and the spread half of
  engine 10 cannot be backtested before live recording began. This is why `scripts/record.py`
  shipped in Phase 0 and must not be switched off.
- **A read-and-trade Kraken key exists on the dev machine.** Use a separate read-only key
  until Phase 8. The three live switches are the only thing between a bug and real money.
- **Every Kraken pair is a lot of pairs.** Develop against a config-limited subset; the
  universe filter handles the rest at runtime.
- **Building the interface before the backend risks guessing at data shapes.** Mitigated by
  fixing the schema in Phase 0 and seeding it. A later schema change goes through the lead
  and updates the console in the same change.
- **An intermittent native memory fault on this machine, not root-caused.** It has now been
  seen inside pydantic-core, inside SQLite's C extension, inside pure-Python pyyaml, inside
  CPython's own `ast.walk`, and as a lax validator returning a strict validator's error. That
  spread is what memory corruption looks like and is not what a library defect looks like.
  pyarrow, `pytest-asyncio`, test ordering, `root_import_path` and the pydantic-core version
  were each ruled out by test; 1,120 consecutive seeds outside pytest produced zero faults,
  which is suggestive at around p ≈ 0.1 and not conclusive. Hardware is suspected and is out
  of scope by operator ruling.

  Two consequences are load-bearing. **The crash-aware retry covers crashes and not wrong
  answers** — a crash is retried once and named, a verdict is never retried, and that policy
  is correct and must not be relaxed, because a rule that retries verdicts is a rule that
  retries real defects until they pass. And **a one-off failure in another agent's tests,
  which passes in isolation and which that agent did not touch, should be suspected as this
  fault before it is treated as their defect.** That is a procedural mitigation, which is
  exactly why it belongs in a limitations chapter: it depends on a person following it.

  The single most alarming instance: `test_sample_contains_no_secret_shaped_key` — the test
  that proves no credential was committed — once reported a spurious FAIL. It reads as a
  leaked secret in a public repository, and it was false. A fault that can fabricate *that*
  verdict can fabricate any of them, in either direction.

---

## 9. What remains to build, by engine

Thirteen engines remain, plus the model layer underneath four of them.

**Phase 5 — Models.** The feature and prediction stack, and the machinery that decides
whether a model is allowed to exist.

| Engine | What it needs |
|---|---|
| 5 `feature` | The per-pair feature vector, computed only on a closed bar. First in the opportunity chain, so it is also what stops the chain on the fourteen ticks in fifteen where no bar closed |
| 6 `macro_context` | BTC and ETH read for market-wide context |
| 8 `prediction` | The three-barrier classifier, plus the Dissimilarity Index fitted on its own training set, MinMax-scaled, with a rolling percentile threshold over a 30-day per-pair window |
| 12 `regime` | Trending / choppy / high-volatility classification, also fed by DI threshold crossings |
| 20 `tournament` | Leaderboard ranking and promotion, with the multiple-testing haircut |

Phase 5 also closes engine 7's ranking score — `rank_universe` is the single named seam.

**Phase 6 — Decision and execution.** The engines that turn a surviving candidate into a
position, and the manage chain that watches it.

| Engine | What it needs |
|---|---|
| 13 `anomaly` | The refusal on conditions outside anything seen. A gate |
| 9 `order_book` | Slippage and depth from the live book — and it cannot be backtested, only recorded forward |
| 14 `adaptive_router` | Routing between models and execution strategies |
| 15 `skeptic` | The meta-labelling model trained only on rows where the predictor said BUY. A gate |
| 16 `decision` | The order intent |
| 18 `execution` | Post-only limit entry, with the offset bandit pooled by spread tier |
| 21 `position_manager` | Watching open positions and resting entry orders; cancelling an entry past its window even during a data-guard hold |
| 22 `exit` | Target, stop, timeout, and the `close_all` liquidation |

Registering 21 and 22 completes the manage chain, and it is the point at which the
`close_intent` clearing path stops being theoretical: today an unregistered manage chain is
treated as "not finished", so a pending close can never be silently discarded.

**Phase 7 — Evaluation.** No new engines. Alpha attribution over the full equity curve
including cash periods, the deflated performance metric, and the SHAP artefacts that give
the research views something real to render.

**Phase 8 — Live readiness.** No new engines. `platform/live_guard.py` and the three
independent switches, plus the soak run. `close_all` is what Phase 8 verifies; there is no
separate kill mechanism to build.

---

## 10. The labelled dataset

This is what Phase 5 will train on. The figures below were **measured on 2026-09-12** by
running `research/labelling.py` over every built pair in `data/historical/` at the committed
config, after the full-archive rebuild of the same day — they are not copied from a build log.
The per-pair reports they were computed from are committed under `docs/dataset/`, because
`data/` is gitignored and a number that cannot be re-derived is a number that cannot be
checked.

### Totals, after the 2017-01-01 cutoff

| | Rows | Share |
|---|---|---|
| **Total labelled decision bars** | **20,331,237** | |
| `target` — +3% touched first | 4,857,764 | 23.89% |
| `stop` — −1.5% touched first | 10,424,046 | 51.27% |
| `timeout` — 48 bars elapsed | 5,049,427 | 24.84% |
| of which **decided by the both-barriers-touched rule** | **76,522** | **0.376%** |

**Distinct pairs: 234.** **Date range: 2017-01-01 to 2025-12-31** (decision bars,
UTC), nine years. Bars replayed: 20,443,861, from 413 USD-suffixed archive files of which
234 cleared the two-year rule.

Exclusions, each accounted for: **93,475 bars** before the cutoff (below),
**6,658 bars** whose label window ran past the end of the series, and
**12,491 bars** whose window contained no candle at all. Labelled plus the
three exclusions equals the bars replayed. Neither of the last two is labelled `timeout`; both
are excluded, because labelling a window that has not finished records an outcome that has not
happened, and a `timeout` label across a multi-day hole has no terminal price to compute a
return from.

### What the cutoff cost — stated so the exclusion is visible

Operator ruling 2 of 2026-09-12: decision bars before `dataset.decision_start_date`
(2017-01-01) are excluded. **The exclusion is about tradability, not data quality.** The
archive begins 2013-10-07 and its earliest bars are single trades of 0.1 BTC in fifteen
minutes; they are real, but they describe a market no position could have been taken in at
any size, and a model trained on them learns patterns that do not transfer.

| | Before the cutoff | After |
|---|---|---|
| Labelled rows | 20,424,028 | 20,331,237 |
| Removed | | **92,791 (0.45%)** |
| `target` share | 23.87% | 23.89% |
| `stop` share | 51.22% | 51.27% |
| `timeout` share | 24.91% | 24.84% |
| Ambiguous | 76,980 | 76,522 |

The cutoff touches **6 of 234 pairs** — the only ones whose history reaches back before
2017. Per pair, the bars it removed:

| Pair | Labelled before | Removed | Labelled after | Previous first decision bar |
|---|---|---|---|---|
| XBTUSD | 361,388 | 46,671 | 314,863 | 2013-10-07 |
| ETHUSD | 338,997 | 25,973 | 313,103 | 2015-08-07 |
| LTCUSD | 313,471 | 10,411 | 303,471 | 2013-11-07 |
| ETCUSD | 244,549 | 7,221 | 237,328 | 2016-07-27 |
| ZECUSD | 238,538 | 2,724 | 235,814 | 2016-10-29 |
| REPUSD | 107,735 | 475 | 107,308 | 2016-10-04 |

(93,475 bars were removed; 92,791 of them had been labelled and the remaining
684 had already been excluded for an empty window, which is why the two figures differ.)

### The largest pairs

| Pair | Bars | Labelled | `target` | `stop` | `timeout` | Ambiguous | Removed by cutoff | First decision bar |
|---|---|---|---|---|---|---|---|---|
| XBTUSD | 361,584 | 314,863 | 43,832 (13.9%) | 116,536 (37.0%) | 154,495 (49.1%) | 149 | 46,671 | 2017-01-01 |
| ETHUSD | 339,125 | 313,103 | 60,325 (19.3%) | 148,643 (47.5%) | 104,135 (33.3%) | 225 | 25,973 | 2017-01-01 |
| LTCUSD | 313,936 | 303,471 | 62,398 (20.6%) | 156,922 (51.7%) | 84,151 (27.7%) | 237 | 10,411 | 2017-01-01 |
| XRPUSD | 300,002 | 299,952 | 58,761 (19.6%) | 147,863 (49.3%) | 93,328 (31.1%) | 478 | 0 | 2017-05-18 |
| USDTUSD | 289,194 | 289,145 | 1,187 (0.4%) | 5,269 (1.8%) | 282,689 (97.8%) | 10 | 0 | 2017-03-29 |
| XMRUSD | 283,003 | 282,951 | 58,572 (20.7%) | 137,921 (48.7%) | 86,458 (30.6%) | 302 | 0 | 2017-01-02 |

The full per-pair table for all 234 pairs is `docs/dataset/labelled-dataset-2026-09-12.json`.

### The eleven thin pairs — kept, by ruling

Eleven pairs carry fewer than 20,000 labelled rows. Operator ruling 3 of 2026-09-12 keeps
them: `dataset.min_labelled_rows` is the per-pair floor, it reads `0` (no floor), and engine 23
names any pair it leaves out in `pairs_below_floor`. A cross-sectional model may want a floor;
that decision is **deferred behind a named knob, not overlooked.**

| Pair | Labelled | First decision bar |
|---|---|---|
| TUSDUSD | 4,659 | 2023-06-29 |
| ETHPYUSD | 4,812 | 2023-12-11 |
| ROOKUSD | 12,013 | 2022-05-06 |
| C98USD | 13,555 | 2022-09-29 |
| REQUSD | 14,609 | 2022-05-31 |
| CSMUSD | 14,958 | 2022-07-27 |
| AGLDUSD | 15,223 | 2022-05-05 |
| XBTPYUSD | 15,491 | 2023-12-11 |
| ALICEUSD | 17,787 | 2022-02-25 |
| PSTAKEUSD | 18,081 | 2022-02-24 |
| TBTCUSD | 18,439 | 2020-11-25 |

### Walk-forward folds — past-only, at the current embargo

Operator ruling 1 of 2026-09-12: **a fold trains on the 90 days before its test window and on
nothing after it.** The splitter built in Phase 4 trained on a window of equal length on both
sides of the test window, which is purged cross-validation — legitimate for hyperparameter
selection, but it lets a model see data from after the period it is scored on, so it reports a
number better than the same model would achieve live, and nothing said so. The validation
must answer *would this have worked if I had been trading it*. The splitter was corrected, and
`walkforward_trains_on_the_past_only` now proves on every rolling fold that no training row's
decision bar or label window end post-dates its test window.

Measured for the same three pairs the retired two-sided table used, at
`backtest.embargo_bars: 48`, `training_window_days: 90` and `retrain_interval_days: 7`,
splitting **per pair**, after the cutoff:

| Pair | Folds | Empty | Purged rows | Embargoed rows | Median train rows | Median test rows |
|---|---|---|---|---|---|---|
| XBTUSD | 457 | 0 | 14,922 | 6,944 | 8,586 | 672 |
| ETHUSD | 457 | 0 | 12,780 | 9,077 | 8,582 | 672 |
| SOLUSD | 224 | 0 | 3,856 | 6,890 | 8,582 | 672 |
| **Total** | **1,138** | **0** | **31,558** | **22,911** | | |

672 test rows is exactly seven days of 15-minute bars, so the test windows are full. The
median training set is now roughly ninety days of bars, half what the two-sided splitter
reported (~17,175), which is the ruling doing what it says rather than a defect. **No fold is
empty**, and none is silently dropped. The past-only property held on every fold of all three
pairs when checked directly against the labels (confirmed).

The embargo now sits on the training side of the boundary: the last 48 bars before each test
window are dropped from training even when their labels resolved in time. That is where an
embargo belongs in a past-only design, and it is why the embargoed count above is smaller than the purged one — with
a 48-bar horizon, most rows in that span are already purged.

### Where the archive is thin — stated plainly

**No order book, no spread, no depth. At all.** The archive is OHLCVT: open, high, low,
close, volume, trade count. Engine 9 `order_book` and the spread half of engine 10 `cost`
**cannot be backtested from this source**, and none of it can be recovered retroactively —
which is precisely why `scripts/record.py` has been running since Phase 0 and must not be
switched off. A backtest that silently assumes zero spread is invalid, and engine 23 carries
that statement in `state["backtest"]` rather than in a docstring nobody reads at the point of
use.

**The bars are ours, not Kraken's published OHLCVT.** They are reduced to 15-minute intervals
by `scripts/build_ohlcvt.py` from Kraken's published time-and-sales archive supplied by the
operator — three columns, one row per trade, 736,910,669 trades across the 234 pairs.
Every price and every quantity in them is a real trade Kraken published, and `trades` is a
real count, but the reduction is this project's. Confirming these bars against Kraken's own
published OHLCVT is a `--live` task and **has not been done**.

**Holes mean no trades, and the quiet fraction is large for many pairs.** An interval in which
nothing traded has no row, exactly as a Kraken archive contains only intervals in which trades
occurred — nothing is forward-filled, resampled or interpolated. Kraken never stops watching,
so that is a *stronger* statement than the recorder's own archive could make. But the quiet
fraction is real and for the smaller pairs it is most of the calendar: the provenance records
`missing_quiet` per pair, and for a pair like WBTCUSD it exceeds the bars that exist.

**The label distribution is heavily skewed, and by construction.** `stop` is 51% of all rows
against `target`'s 24% — which is what an asymmetric barrier does, since −1.5% is half the
distance of +3% and is reached roughly twice as often. Across 234 pairs the skew is stronger
than it was on three, because the smaller altcoins are more volatile and hit a barrier before
the 12-hour horizon more often, which is also why `timeout` fell from 38% to 25%. This is
correct behaviour and not a bug, but a classifier trained naively on it will learn to predict
`stop` and score well doing so. Phase 5 needs a metric that is not accuracy.

**What is reassuring.** The both-barriers-touched rule — the pessimistic ruling that resolves
an ambiguous bar to `stop` — decides **76,522 rows in 20,331,237, under four in a thousand**. It
was adopted because OHLC carries no intra-bar ordering and the favourable reading would
flatter the strategy exactly on the most violent bars; the measurement says the assumption
carries almost no weight in practice. Had that number been large, the labels would have been
mostly an assumption.

### The committed fixture is not the dataset

`tests/fixtures/labelled_sample.parquet` is **960 rows of SOLUSD over ten days**
(2022-11-09 to 2022-11-19), with 17 ambiguous rows. It is an evidence fixture proving the
labeller reproduces a real replay, committed because `data/` is gitignored and a criterion
reading the archive would pass only on the machine that downloaded it. It is paired with
`tests/fixtures/labels_hand_verified.json`, whose expectations were produced by a **second
implementation written from spec 52's prose** rather than from the labeller. Neither file is
training data, and neither should be confused with the 20,331,237-row dataset above.

---

## 11. The seams

Every cross-engine and cross-agent contract in `context/ownership.md`, with the field names
and types actually being passed. **This is what Phase 5's model layer is built against.**

Two conventions hold across all of them. `Money` is an annotated `Decimal` that **raises on a
float rather than coercing it**, and money crosses `state` as an exact decimal **string**,
never as a float — the `state` validator refuses a `Decimal` loudly, which is fine, and
*accepts* a float, which is the dangerous half. And a payload key that has no value is
**omitted**, not set to `None`, wherever a consumer tests for presence.

### Live-loop seams

| Seam | Producer | Consumer | Fields and types |
|---|---|---|---|
| Account picture | 1 `exchange` (A) | 10 `cost`, 11 `risk` (B), 2 `market_data_recorder` (A), 19 `memory` (C) | `state["exchange"]`: `fetched_at: int`, `balances: dict[str, str] \| None`, `fee_tier: dict[str, Any] \| None`, `pair_rules: dict[str, Any] \| None`, `failed_fetches: tuple[FetchFailure, ...]`, `retained: tuple[RetainedNote, ...]`. `FetchFailure(call: str, kind: str, reason: str)`; `RetainedNote(call: str, fetched_at: int, age_micros: int)` |
| Decision-bar tick | 3 `market_sensor` (A) | 5 `feature` (C) | `state["market_sensor"]["bar_closed"]: bool` — true only on the tick a 15-minute candle completed — with `closed_bar_ts: int \| None` |
| 15-minute candles and quotes | 3 `market_sensor` (A) | 4 `data_guard` (A), 11 `risk` (B), 5 `feature` (C) | `state["market_sensor"]`: `interval_s: int`, `candles: tuple[dict[str, Any], ...]`, `missing_bars: tuple[int, ...]`, `quotes: dict[str, dict[str, Any]]`, `stream_available: bool`, `trades_seen: int`. Each quote is a `QuoteView`: `pair: str`, `ts: str`, `bid/ask/spread/spread_pct: Money`, `age_s: float` |
| Data verdict | 4 `data_guard` (A) | orchestrator, 17 `safety` (B), 19 `memory` (C) | `state["data_guard"]`: `blocked: bool`, `reason_code: str \| None`, `findings: tuple[dict, ...]` of `Finding(reason_code: str, detail: str, pair: str \| None)`, `max_data_age_s: float \| None`, `oldest_quote_age_s: float \| None`, `pairs_seen: int`, `missing_bars: int` |
| Tradable universe and the candidate | 7 `scout` (B) | 10 `cost`, 11 `risk` (B) | `state["scout"]`: `pairs: tuple[str, ...]`, `scanned: int`, `excluded: Mapping[str, int]`, `equity: Money \| None`, `reason_code: str \| None`. **The candidate is published under the key `pair`, not `candidate`** — the model field is `candidate`, `CANDIDATE_FIELD = "pair"` is the wire name, and it is **omitted entirely when there is no candidate, never emitted as `None`** |
| Cost assessment | 10 `cost` (B) | 19 `memory` (C), console | `state["cost"]`: `pair: str`, `expected_move_pct/friction_pct/net_edge_pct/hurdle_pct: Money`, `clears_hurdle: bool`, `reason_code: str \| None`, `fallbacks_used: tuple[str, ...]` |
| Position sizing | 11 `risk` (B) | 19 `memory` (C), console | `state["risk"]`: `pair: str`, `approved: bool`, `qty/notional/value_at_bid/risk_amount: Money \| None`, `ordermin/costmin: Money`, `reason_code: str \| None`, `fallbacks_used: tuple[str, ...]` |
| Circuit-breaker verdict | 17 `safety` (B) | orchestrator, console | `state["safety"]`: `readings: SafetyReadings`, `tripped: tuple[SafetyCondition, ...]`, `action: SafetyAction`, `command_emitted: str \| None`, `suppressed_because: str \| None`. `SafetyReadings`: `drawdown_pct/equity/peak_equity: Money \| None`, `consecutive_losses: int`, `loss_streak_saturated: bool`, `errors_in_window: int`, `error_window_start_ts: int`, `open_positions: int`, `resting_entry_orders: int`, `consecutive_data_blocks: int`, `stored_data_blocks: int`, `current_tick_blocked_by_data_guard: bool` |
| What was recorded this tick | 19 `memory` (C) | console | `state["memory"]`: `cycle_id: int`, `run_id: str`, `written: dict[str, int]` (rows per table), `sources_present: tuple[str, ...]`, `equity/peak_equity: Money \| None`, `equity_skipped_reason: str \| None`, `hold_reason: str \| None` |

### Orchestrator-level keys

| Key | Written by | Read by | Type |
|---|---|---|---|
| `state["system"]["mode"]` | Orchestrator (Lead) only | Any engine | `"idle" \| "running" \| "frozen"` |
| `state["system"]["close_intent"]` | Orchestrator (Lead) only | 21, 22 | `bool` |
| `state["cycle_id"]` | Orchestrator | All | `int`, restarts at 1 per run |
| `state["trading_blocked_by"]`, `state["block_reason"]` | Orchestrator | Opportunity chain, 17, 19, 21, 22 | `str`. The **primary** blocker only. Fresh per tick |
| `state["guard_blockers"]` | Orchestrator | 19 `memory` | `list[{"engine": str, "reason": str, "status": str}]` in chain order. **Empty list on an unblocked tick, never absent** |
| `context.run_id` | Orchestrator | All | `str`. Lives on the context, never duplicated into `state` |

### Seams not yet live — Phase 6 fills these

| Seam | Producer | Consumer | Fields |
|---|---|---|---|
| Close-all completion | 21 `position_manager`, 22 `exit` (B) | Orchestrator (Lead) | `state["position_manager"]["entry_orders_cancelled"]: bool`, `state["exit"]["positions_closed"]: bool` — each true only when none remain. The orchestrator clears `close_intent` only when both are true, and treats a **missing** result as "not finished" |
| Manage-chain hold | 21 `position_manager` (B) | 19 `memory` (C), console | `state["position_manager"]["hold_reason"]: str \| None` — why no exit was placed; null on a tick where it did not hold |
| Expected move | 8 `prediction` (C) | 10 `cost` (B) | `state["prediction"]["expected_move_pct"]` — exact decimal **string**, before friction |
| Estimated slippage | 9 `order_book` (C) | 10 `cost` (B) | `state["order_book"]["estimated_slippage_pct"]` — exact decimal **string** |
| Feature vector | 5 `feature` (C) | 8 `prediction` (C), gates (B) | `engines/feature/contracts.py` — not yet written |
| Order intent | 16 `decision` (B) | 18 `execution` (B) | `engines/decision/contracts.py` — not yet written |

### Store seams

Engine 19 `memory` is the single writer; the tables and columns are in section 5. The
consumers are fixed because `safety` is the circuit breaker and an ambiguous input is a
breaker two agents implement two ways:

| Input | Table | Fields read | Read by |
|---|---|---|---|
| Equity drawdown | `equity_snapshots` | latest row's `equity`, `peak_equity`; drawdown is `(peak_equity − equity) / peak_equity` | 17 `safety` |
| Consecutive losses | `trades` | trailing run ordered by `closed_at`: `realised_pnl`, `outcome` | 17 `safety` |
| Error rate | `block_records` | rows in the trailing hour with `status = 'ERROR'` | 17 `safety` |
| Open positions | `positions` | count where `status = 'open'` | 17 `safety`, console |
| Resting entry orders | `orders` | count where `status = 'resting'` | 17 `safety`, 21 |
| Consecutive data blocks | `block_records` | trailing consecutive `cycle_id`s carrying a `data_guard` row, **ordered by `ts`** | 17 `safety` |
| Run record | `runs` | previous row's existence, for restart detection — **not** whether two `run_id`s differ, since `run_id` is UNIQUE and they always do | Console |
| Persisted system mode | `runs` | `system_mode`, `system_mode_at`, by `run_id` | Console |
| Commands | `commands` | `pending_commands()`, `claim_command()`, `claimed_unconsumed_commands()`, `mark_command_consumed()` | Orchestrator (Lead) |

### Research seams

| Seam | Producer | Consumer | Fields and types |
|---|---|---|---|
| The archive and the replayed decision-bar series | A (`research/replay.py`, `scripts/`) | C (`research/labelling.py`) | `DecisionBar` with `close_ts` and `state_dict()`; `PairCoverage`, `ReplayReport` with `span_seconds` |
| Labelled decision bars | C (`research/labelling.py`) | 23 `backtest` (A), C (`research/walkforward.py`) | `Label`: `pair: str`, `decision_ts: int`, `close/target_price/stop_price/touch_price: Decimal`, `label: str`, `touch_ts: int`, `bars_elapsed: int`, **`label_window_end_ts: int`**, `return_pct: float`, `ambiguous: bool`, `candles_in_window: int`. Money is a string in the frame |
| Fold indices | C (`research/walkforward.py`) | Phase 5 training | `Fold`: `fold_index`, `train_start_ts`, `train_end_ts`, `test_start_ts`, `test_end_ts`, `train_index: tuple[int, ...]`, `test_index: tuple[int, ...]`, `purged_count`, `embargoed_count`, `out_of_window_count`, `after_test_count`, `is_empty`. `train_end_ts == test_start_ts`: a fold trains on the past only |
| The labeller, called by name | 23 `backtest` (A) | C's module | Imported late and by name, and the engine **refuses rather than inventing a label** when it is absent. The barriers never cross this seam — `label_frame` takes the `Config` and reads them itself |

**`label_window_end_ts` is the seam that matters most.** It is the instant at which a row's
outcome became known — the touch for a touched barrier, the horizon for a timeout, which is
later than the last candle whenever the window ends inside a gap — and it is what the splitter
purges on. **Purging on `decision_ts` instead is the most plausible wrong implementation in
the project**, and it is invisible from the outside: the fold indices do not overlap either
way, so an end-to-end test cannot tell a correct embargo from none at all.

### The reason-code seam, which fails silently

Every gate emits a `reason_code`; `console/format.py`'s `REASON_PROSE` maps it to operator
prose. **A code absent from that map renders "No reason was recorded." — silently, with no
error anywhere.** Producers are engines 7, 10, 11, 13 and 15 and any future gate; the consumer
is the console. All nineteen Phase 3 codes are mapped. Any gate added in Phase 5 or 6 must add
its codes in the same change.
