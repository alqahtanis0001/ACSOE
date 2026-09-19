-- 0006_approval_economics.sql — spec 132, Phase 7 prerequisite 7 (F-new-1).
--
-- Forward-only and additive. No existing column is altered and nothing is dropped. Adds
-- one table (`approvals`), one index on it, seven columns on `trades` and two on `runs`.
-- `EXPECTED_TABLES` and `EXPECTED_INDEXES` gain the table and its index in the same
-- change.
--
-- WHY
--
--   Before this migration an approved trade left no record of why it was approved. Only
--   `rejections` carried expected move, friction, net edge and hurdle, so the
--   counterfactual dataset recorded the reasons for one side of the decision only.
--   This migration makes the other side recordable. Engine 19 (C, spec 133) writes it.
--
-- `approvals` — THE PLACING TICK'S ECONOMICS, HELD UNTIL THE TRADE IS WRITTEN
--
--   The economics exist in `state` only on the tick engine 18 places the entry. The
--   `trades` row is written ticks later, when engine 22 closes the position, and by then
--   `state` no longer holds them. So engine 19 writes one row here on the placing tick,
--   keyed by the entry order's `userref`. When it writes the trade it copies the row
--   onto `trades`.
--
--   Insert-only. The primary key refuses a second approval for one entry. That is why
--   `cycle_id` here is always the tick that placed the order. On `orders` the same column
--   is overwritten by every later tick (prerequisite 8, F-new-2).
--
--   Columns on `orders` were rejected. `StoreClient.write_order` upserts every column,
--   and engine 21 builds its fill and cancel rows from scratch, so the fill-tick write
--   would put NULL over the economics. `docs/build-log/phase-7/b-store.md` has the whole
--   decision.
--
-- THE ECONOMICS ARE MONEY-SHAPED, AND ABSENT IS NEVER ZERO
--
--   They are declared ANY with a text CHECK, as on `rejections`. They are the arithmetic
--   of invariant 5, computed from live fees, and they decide whether a trade happens, so
--   a float must never reach them. NULL means "not recorded". Every `trades` row written
--   before this migration reads NULL. Nothing backfills them from `rejections`, because
--   the two tables mean different things.
--
-- THE THREE MODEL RUN IDS
--
--   These are the runs engines 8, 13 and 15 loaded on the approving tick. NULL means "not
--   recorded". A blank string is refused, because that is how "unknown" gets past a
--   nullable column. The same rule as `positions.hold_reason` (0003).
--
-- `approvals.details` — EVERY GATE'S VERDICT ON THE APPROVING TICK (SPEC 145)
--
--   Operator ruling 2026-09-19. Canonical JSON written by engine 19: each engine that
--   judged the candidate, with the value it computed and the threshold it compared
--   against. This is the approval-side twin of `rejections.details`, which is
--   unchanged. NULL means not recorded. A blank string is refused, as for the run ids.
--   Added while 0006 is still uncommitted, so no 0007 is needed.
--
-- `runs.scenario_digest` AND `runs.scenario_description` — THE LEAD'S SPEC 134
--
--   These name the declared replay scenario that priced a run: the fee schedule and tier,
--   the synthetic book's bucket table, the rules file and the window. The orchestrator
--   writes them at startup through `StoreClient.start_run`. They are NULL for paper and
--   live runs. They are never a placeholder, so a blank string is refused here too.

CREATE TABLE approvals (
    userref           INTEGER PRIMARY KEY,
    run_id            TEXT    NOT NULL,
    cycle_id          INTEGER NOT NULL,
    ts                INTEGER NOT NULL,
    pair              TEXT    NOT NULL,
    expected_move_pct ANY     CHECK (expected_move_pct IS NULL OR typeof(expected_move_pct) = 'text'),
    friction_pct      ANY     CHECK (friction_pct IS NULL OR typeof(friction_pct) = 'text'),
    net_edge_pct      ANY     CHECK (net_edge_pct IS NULL OR typeof(net_edge_pct) = 'text'),
    hurdle_pct        ANY     CHECK (hurdle_pct IS NULL OR typeof(hurdle_pct) = 'text'),
    prediction_run_id TEXT    CHECK (prediction_run_id IS NULL OR trim(prediction_run_id) <> ''),
    anomaly_run_id    TEXT    CHECK (anomaly_run_id IS NULL OR trim(anomaly_run_id) <> ''),
    skeptic_run_id    TEXT    CHECK (skeptic_run_id IS NULL OR trim(skeptic_run_id) <> ''),
    details           TEXT    CHECK (details IS NULL OR trim(details) <> ''),
    updated_at        INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_approvals_run_cycle ON approvals (run_id, cycle_id);

ALTER TABLE trades ADD COLUMN expected_move_pct ANY
    CHECK (expected_move_pct IS NULL OR typeof(expected_move_pct) = 'text');
ALTER TABLE trades ADD COLUMN friction_pct ANY
    CHECK (friction_pct IS NULL OR typeof(friction_pct) = 'text');
ALTER TABLE trades ADD COLUMN net_edge_pct ANY
    CHECK (net_edge_pct IS NULL OR typeof(net_edge_pct) = 'text');
ALTER TABLE trades ADD COLUMN hurdle_pct ANY
    CHECK (hurdle_pct IS NULL OR typeof(hurdle_pct) = 'text');
ALTER TABLE trades ADD COLUMN prediction_run_id TEXT
    CHECK (prediction_run_id IS NULL OR trim(prediction_run_id) <> '');
ALTER TABLE trades ADD COLUMN anomaly_run_id TEXT
    CHECK (anomaly_run_id IS NULL OR trim(anomaly_run_id) <> '');
ALTER TABLE trades ADD COLUMN skeptic_run_id TEXT
    CHECK (skeptic_run_id IS NULL OR trim(skeptic_run_id) <> '');

ALTER TABLE runs ADD COLUMN scenario_digest TEXT
    CHECK (scenario_digest IS NULL OR trim(scenario_digest) <> '');
ALTER TABLE runs ADD COLUMN scenario_description TEXT
    CHECK (scenario_description IS NULL OR trim(scenario_description) <> '');
