-- 0001_initial.sql — the full Phase 0 relational schema.
--
-- Forward-only. Never edit an applied migration; add a new numbered file instead.
--
-- Conventions, and why:
--
--   Money is an exact decimal string in TEXT, never REAL. `Decimal` in Python, exact
--   string in SQLite, conversion only at the store-client boundary. A float equity
--   series drifts, and a drifting equity series moves the drawdown threshold that
--   liquidates the account. SQLite is dynamically typed, so a declared TEXT column will
--   happily store a float — every money column therefore carries an explicit
--   `typeof(col) = 'text'` CHECK so the database refuses a float rather than silently
--   accepting one. See `context/architecture-context.md`, storage model.
--
--   Timestamps are INTEGER microseconds since the Unix epoch, UTC. They come from
--   `context.now`; nothing here reads a clock.
--
--   `cycle_id` is INTEGER and is minted per tick *within a run*. It restarts with the
--   process, so it is never unique on its own and never an ordering key: a tick is
--   identified by `(run_id, cycle_id)` and a cross-restart sequence is ordered by `ts`.
--
--   `updated_at` is on every table the console renders. `MAX(updated_at)` across those
--   tables is the monotonic watermark `ui-context.md` has the console poll.

-- ---------------------------------------------------------------------------
-- runs — one row per daemon process, written by the orchestrator at startup.
-- The console detects a silent restart by comparing the current `run_id` against
-- the `run_id` of the previous row (`ui-context.md`, "Restart is visible").
-- ---------------------------------------------------------------------------
CREATE TABLE runs (
    id             INTEGER PRIMARY KEY,
    run_id         TEXT    NOT NULL UNIQUE,
    mode           TEXT    NOT NULL CHECK (mode IN ('paper', 'live', 'replay')),
    started_at     INTEGER NOT NULL,
    ended_at       INTEGER,
    acsoe_version  TEXT,
    config_digest  TEXT,
    updated_at     INTEGER NOT NULL
);

CREATE INDEX idx_runs_started_at ON runs (started_at);

-- ---------------------------------------------------------------------------
-- commands — the console and engine 17 `safety` write; the orchestrator reads.
--
-- Consumption is two-phase so a crash cannot swallow a kill switch:
-- `claimed_at` is stamped when the reader applies the effect to state["system"],
-- `consumed_at` only when the effect is complete. A row with `claimed_at` set and
-- `consumed_at` null is an interrupted command and is re-applied at startup.
--
-- `command` deliberately carries NO CHECK constraint. An unrecognised command is
-- ignored and logged as a warning by the reader (`architecture-context.md`); a CHECK
-- here would make that case unreachable and untestable.
-- ---------------------------------------------------------------------------
CREATE TABLE commands (
    id                INTEGER PRIMARY KEY,
    command           TEXT    NOT NULL,
    source            TEXT    NOT NULL CHECK (source IN ('console', 'safety')),
    reason            TEXT,
    payload           TEXT,
    created_at        INTEGER NOT NULL,
    created_by_run_id TEXT,
    claimed_at        INTEGER,
    claimed_by_run_id TEXT,
    consumed_at       INTEGER,
    updated_at        INTEGER NOT NULL
);

CREATE INDEX idx_commands_pending ON commands (created_at)
    WHERE claimed_at IS NULL;

CREATE INDEX idx_commands_unconsumed ON commands (created_at)
    WHERE consumed_at IS NULL;

-- ---------------------------------------------------------------------------
-- block_records — one row per guard blocker per tick, written by engine 19 `memory`.
--
-- Columns are fixed by `context/architecture-context.md` because engine 17 `safety`
-- derives its outage count from this table.
--
-- The partial unique index enforces invariant 12's "is_primary on the first only":
-- two engines each claiming to have gated the opportunity chain would destroy the
-- audit trail, so a second primary for one tick fails at the database rather than
-- being resolved by whichever write landed last.
--
-- It is scoped `(run_id, cycle_id)`, not `(cycle_id)`. `cycle_id` restarts with the
-- process, so two runs necessarily reuse the same low values — and the Phase 3
-- criterion requires a seeded outage run spanning two `run_id`s precisely so that
-- ordering by `ts` rather than `cycle_id` is actually exercised. A tick is
-- `(run_id, cycle_id)`; the constraint is one primary per tick.
-- ---------------------------------------------------------------------------
CREATE TABLE block_records (
    id           INTEGER PRIMARY KEY,
    cycle_id     INTEGER NOT NULL,
    run_id       TEXT    NOT NULL,
    ts           INTEGER NOT NULL,
    blocked_by   TEXT    NOT NULL,
    block_reason TEXT    NOT NULL,
    is_primary   INTEGER NOT NULL CHECK (is_primary IN (0, 1)),
    status       TEXT    NOT NULL CHECK (status IN ('BLOCK', 'ERROR')),
    updated_at   INTEGER NOT NULL
);

CREATE INDEX idx_block_records_ts ON block_records (ts);

CREATE INDEX idx_block_records_run_cycle ON block_records (run_id, cycle_id);

-- `safety`'s error rate: rows in the trailing hour with status = 'ERROR'.
CREATE INDEX idx_block_records_status_ts ON block_records (status, ts);

-- `safety`'s outage count: the trailing run of ticks carrying a `data_guard` row.
CREATE INDEX idx_block_records_blocked_by_ts ON block_records (blocked_by, ts);

CREATE UNIQUE INDEX ux_block_records_primary ON block_records (run_id, cycle_id)
    WHERE is_primary = 1;

-- ---------------------------------------------------------------------------
-- equity_snapshots — one row per tick, written by engine 19 `memory`.
--
-- `safety` reads the latest row's `equity` and `peak_equity`; drawdown is
-- (peak_equity - equity) / peak_equity. The Phase 7 alpha attribution reads the full
-- curve *including cash periods*, which is why the cash and unrealised components are
-- stored rather than derived from trades.
-- ---------------------------------------------------------------------------
CREATE TABLE equity_snapshots (
    id                  INTEGER PRIMARY KEY,
    cycle_id            INTEGER NOT NULL,
    run_id              TEXT    NOT NULL,
    ts                  INTEGER NOT NULL,
    currency            TEXT    NOT NULL,
    equity              TEXT    NOT NULL CHECK (typeof(equity) = 'text'),
    peak_equity         TEXT    NOT NULL CHECK (typeof(peak_equity) = 'text'),
    cash                TEXT    NOT NULL CHECK (typeof(cash) = 'text'),
    positions_value     TEXT    NOT NULL CHECK (typeof(positions_value) = 'text'),
    unrealised_pnl      TEXT    NOT NULL CHECK (typeof(unrealised_pnl) = 'text'),
    realised_pnl_cum    TEXT    NOT NULL CHECK (typeof(realised_pnl_cum) = 'text'),
    open_position_count INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL
);

CREATE INDEX idx_equity_snapshots_ts ON equity_snapshots (ts);

CREATE UNIQUE INDEX ux_equity_snapshots_tick
    ON equity_snapshots (run_id, cycle_id);

-- ---------------------------------------------------------------------------
-- positions — what the console renders and what `safety` counts.
--
-- The partial unique index is invariant 6, "one open position per pair", enforced by
-- the database rather than by convention.
-- ---------------------------------------------------------------------------
CREATE TABLE positions (
    position_id    TEXT    PRIMARY KEY,
    run_id         TEXT    NOT NULL,
    cycle_id       INTEGER NOT NULL,
    pair           TEXT    NOT NULL,
    base           TEXT    NOT NULL,
    quote          TEXT    NOT NULL,
    side           TEXT    NOT NULL CHECK (side = 'long'),
    status         TEXT    NOT NULL CHECK (status IN ('open', 'closed')),
    qty            TEXT    NOT NULL CHECK (typeof(qty) = 'text'),
    entry_price    TEXT    NOT NULL CHECK (typeof(entry_price) = 'text'),
    target_price   TEXT    NOT NULL CHECK (typeof(target_price) = 'text'),
    stop_price     TEXT    NOT NULL CHECK (typeof(stop_price) = 'text'),
    timeout_at     INTEGER NOT NULL,
    entry_userref  INTEGER,
    last_price     TEXT    CHECK (last_price IS NULL OR typeof(last_price) = 'text'),
    unrealised_pnl TEXT    CHECK (unrealised_pnl IS NULL OR typeof(unrealised_pnl) = 'text'),
    opened_at      INTEGER NOT NULL,
    closed_at      INTEGER,
    trade_id       TEXT,
    updated_at     INTEGER NOT NULL
);

CREATE INDEX idx_positions_status ON positions (status);

CREATE INDEX idx_positions_pair_status ON positions (pair, status);

CREATE UNIQUE INDEX ux_positions_open_pair ON positions (pair)
    WHERE status = 'open';

-- ---------------------------------------------------------------------------
-- orders — every order, including a resting post-only entry.
--
-- Keyed by `userref` so the invariant 8 idempotency check ("never place an order
-- without checking whether that userref already exists") is a primary-key lookup
-- rather than a scan.
--
-- `safety` counts rows where status = 'resting'; engine 21 cancels them.
-- ---------------------------------------------------------------------------
CREATE TABLE orders (
    userref        INTEGER PRIMARY KEY,
    order_id       TEXT,
    run_id         TEXT    NOT NULL,
    cycle_id       INTEGER NOT NULL,
    position_id    TEXT,
    pair           TEXT    NOT NULL,
    side           TEXT    NOT NULL CHECK (side IN ('buy', 'sell')),
    intent         TEXT    NOT NULL CHECK (intent IN ('entry', 'exit')),
    order_type     TEXT    NOT NULL CHECK (order_type IN ('limit', 'market')),
    oflags         TEXT    NOT NULL DEFAULT '',
    status         TEXT    NOT NULL CHECK (
                       status IN ('pending', 'resting', 'filled',
                                  'cancelled', 'rejected', 'expired')),
    qty            TEXT    NOT NULL CHECK (typeof(qty) = 'text'),
    limit_price    TEXT    CHECK (limit_price IS NULL OR typeof(limit_price) = 'text'),
    filled_qty     TEXT    NOT NULL CHECK (typeof(filled_qty) = 'text'),
    avg_fill_price TEXT    CHECK (avg_fill_price IS NULL OR typeof(avg_fill_price) = 'text'),
    fee            TEXT    CHECK (fee IS NULL OR typeof(fee) = 'text'),
    placed_at      INTEGER NOT NULL,
    closed_at      INTEGER,
    updated_at     INTEGER NOT NULL
);

CREATE INDEX idx_orders_status ON orders (status);

CREATE INDEX idx_orders_order_id ON orders (order_id);

CREATE INDEX idx_orders_position_id ON orders (position_id);

-- ---------------------------------------------------------------------------
-- trades — one row per closed round trip.
--
-- `safety` reads the trailing run ordered by `closed_at`, using `realised_pnl` and
-- `outcome`, for the consecutive-loss limit.
--
-- Invariant 7 requires FX exposure against the reporting currency to be recorded per
-- trade rather than silently absorbed into PnL, hence both the quote-currency and
-- reporting-currency PnL and the two FX rates.
--
-- Invariant 2 and invariant 14 both require that any tolerated fetch failure or
-- paper-mode fallback is recorded on the resulting trade, so the fill is never
-- mistaken for one priced on good data. `fallbacks_used` is a JSON array of names.
-- ---------------------------------------------------------------------------
CREATE TABLE trades (
    trade_id           TEXT    PRIMARY KEY,
    position_id        TEXT,
    run_id             TEXT    NOT NULL,
    cycle_id           INTEGER NOT NULL,
    pair               TEXT    NOT NULL,
    base               TEXT    NOT NULL,
    quote              TEXT    NOT NULL,
    side               TEXT    NOT NULL CHECK (side = 'long'),
    qty                TEXT    NOT NULL CHECK (typeof(qty) = 'text'),
    entry_price        TEXT    NOT NULL CHECK (typeof(entry_price) = 'text'),
    exit_price         TEXT    NOT NULL CHECK (typeof(exit_price) = 'text'),
    entry_fee          TEXT    NOT NULL CHECK (typeof(entry_fee) = 'text'),
    exit_fee           TEXT    NOT NULL CHECK (typeof(exit_fee) = 'text'),
    entry_userref      INTEGER,
    exit_userref       INTEGER,
    opened_at          INTEGER NOT NULL,
    closed_at          INTEGER NOT NULL,
    outcome            TEXT    NOT NULL CHECK (
                           outcome IN ('target', 'stop', 'timeout', 'liquidation')),
    realised_pnl       TEXT    NOT NULL CHECK (typeof(realised_pnl) = 'text'),
    realised_pnl_pct   TEXT    NOT NULL CHECK (typeof(realised_pnl_pct) = 'text'),
    realised_pnl_quote TEXT    NOT NULL CHECK (typeof(realised_pnl_quote) = 'text'),
    reporting_currency TEXT    NOT NULL,
    fx_rate_entry      TEXT    NOT NULL CHECK (typeof(fx_rate_entry) = 'text'),
    fx_rate_exit       TEXT    NOT NULL CHECK (typeof(fx_rate_exit) = 'text'),
    fallbacks_used     TEXT    NOT NULL DEFAULT '[]',
    updated_at         INTEGER NOT NULL
);

CREATE INDEX idx_trades_closed_at ON trades (closed_at);

CREATE INDEX idx_trades_pair ON trades (pair);

-- ---------------------------------------------------------------------------
-- rejections — one candidate refused, with its reason and its SHAP row.
--
-- Distinct from `block_records`: a rejection is one *candidate*, a block record is one
-- *tick*, and most blocked ticks never had a candidate at all. They join on
-- (run_id, cycle_id).
--
-- `reason_code` is machine-readable for research; `reason` is written for the operator,
-- because the console renders it ("Net edge -0.21% after fees", not `cost_gate_fail`).
-- The economics columns are TEXT decimal strings: they are derived from live fees and
-- they gate a trade, so they are money, not statistics.
-- ---------------------------------------------------------------------------
CREATE TABLE rejections (
    id                INTEGER PRIMARY KEY,
    cycle_id          INTEGER NOT NULL,
    run_id            TEXT    NOT NULL,
    ts                INTEGER NOT NULL,
    pair              TEXT    NOT NULL,
    rejected_by       TEXT    NOT NULL,
    reason_code       TEXT    NOT NULL,
    reason            TEXT    NOT NULL,
    expected_move_pct TEXT    CHECK (expected_move_pct IS NULL OR typeof(expected_move_pct) = 'text'),
    friction_pct      TEXT    CHECK (friction_pct IS NULL OR typeof(friction_pct) = 'text'),
    net_edge_pct      TEXT    CHECK (net_edge_pct IS NULL OR typeof(net_edge_pct) = 'text'),
    hurdle_pct        TEXT    CHECK (hurdle_pct IS NULL OR typeof(hurdle_pct) = 'text'),
    candidate_score   REAL,
    shap_ref          TEXT,
    details           TEXT,
    updated_at        INTEGER NOT NULL
);

CREATE INDEX idx_rejections_ts ON rejections (ts);

CREATE INDEX idx_rejections_run_cycle ON rejections (run_id, cycle_id);

CREATE INDEX idx_rejections_rejected_by ON rejections (rejected_by);

-- ---------------------------------------------------------------------------
-- leaderboard — trained model versions ranked by out-of-sample performance.
--
-- Metrics are statistics, so REAL is correct for them (`code-standards.md`: float is
-- fine for features, indicators, model inputs and statistics). `net_pnl` is money and
-- is therefore TEXT like every other money column.
-- ---------------------------------------------------------------------------
CREATE TABLE leaderboard (
    id                 INTEGER PRIMARY KEY,
    model_id           TEXT    NOT NULL,
    model_version      TEXT    NOT NULL,
    training_run_id    TEXT,
    trained_at         INTEGER NOT NULL,
    fold               TEXT,
    n_trades           INTEGER NOT NULL,
    win_rate           REAL,
    sharpe             REAL,
    deflated_sharpe    REAL,
    alpha              REAL,
    beta               REAL,
    brier              REAL,
    net_pnl            TEXT    CHECK (net_pnl IS NULL OR typeof(net_pnl) = 'text'),
    reporting_currency TEXT,
    promoted           INTEGER NOT NULL CHECK (promoted IN (0, 1)),
    notes              TEXT,
    updated_at         INTEGER NOT NULL
);

CREATE INDEX idx_leaderboard_model ON leaderboard (model_id, model_version);

CREATE INDEX idx_leaderboard_trained_at ON leaderboard (trained_at);
