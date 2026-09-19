-- 0007_tick_tallies.sql — spec 146, operator ruling 2026-09-19 (Q8).
--
-- Forward-only and additive: one table and one index. No existing table or column is
-- touched. `EXPECTED_TABLES` and `EXPECTED_INDEXES` gain them in the same change.
--
-- WHY
--
--   The funnel in `phase-7-findings.md` has to be fillable from stored rows. Until now
--   engine 7's universe step lived in `state["scout"]` for exactly one tick, and a tick
--   with no candidate left no row anywhere. Counting those ticks meant arithmetic on
--   absences. This table records one row per tick on which engine 7 ran and did not
--   error. Engine 19 writes it from engine 7's published payload, verbatim (spec 146,
--   C's half).
--
-- NOT A REJECTION
--
--   A tally is a fact about a tick, not a refused candidate, so it never goes into
--   `rejections` (invariant 12, and the Phase 3 deferral recorded in the tracker, which
--   rejected putting it there for this reason). It is its own table, joined on
--   `(run_id, cycle_id)`.
--
-- ONE ROW PER TICK, WRITTEN ONCE
--
--   `UNIQUE (run_id, cycle_id)`. `write_scout_tally` inserts and never upserts, so a
--   second write for one tick raises. A tick is `(run_id, cycle_id)` and never `cycle_id`
--   alone, which restarts with the process (`architecture-context.md`).
--
-- ABSENT IS NULL, NEVER ZERO
--
--   Every payload field is nullable. A field engine 7 did not publish is NULL, which is
--   what a BLOCK payload looks like: it carries only `reason_code`. A zero `scanned` on a
--   blocked tick would put a number in the funnel that means something else entirely.
--   Only the tick's identity and `updated_at` are required.
--
-- THE JSON COLUMNS ARE STORED AS GIVEN
--
--   `pairs`, `excluded`, `rank_skipped`, `ranked` and `rank_run_ids` are TEXT, JSON as
--   engine 19 serialised it, and they come back byte for byte. `StoreClient` checks their
--   shape on the way in (`ScoutTallyRow`). In particular, each expected move in `ranked`
--   must be an exact decimal string, never a JSON number. The CHECK here is only
--   `json_valid`, a backstop for hand-written SQL.
--
-- `equity` IS MONEY
--
--   It is declared ANY with a text CHECK like every money column, so a float is refused.
--
-- NO STATUS COLUMN, AND THE BAR IS ENGINE 3's (THE LEAD'S RULING, 2026-09-19)
--
--   Engine 7 publishes no status, and spec 146 stores its payload verbatim, so no status
--   is derived here. `reason_code` and `candidate` together carry the outcome: a
--   candidate, `empty_universe`, `no_rankable_pair`, or `scout_inputs_unavailable`. An
--   errored engine 7 writes no tally, and its `block_records` row records that tick.
--
--   `closed_bar_ts` is engine 3's published `closed_bar_ts`, stored verbatim: whole
--   seconds, the opening second of the bar that just closed. It is NULL when engine 3
--   published none. Named for its source, so nobody reads it as microseconds or as the
--   bar's close.

CREATE TABLE scout_tallies (
    id              INTEGER PRIMARY KEY,
    run_id          TEXT    NOT NULL,
    cycle_id        INTEGER NOT NULL,
    ts              INTEGER NOT NULL,
    closed_bar_ts   INTEGER CHECK (closed_bar_ts IS NULL OR closed_bar_ts >= 0),
    reason_code     TEXT    CHECK (reason_code IS NULL OR trim(reason_code) <> ''),
    candidate       TEXT    CHECK (candidate IS NULL OR trim(candidate) <> ''),
    scanned         INTEGER CHECK (scanned IS NULL OR scanned >= 0),
    entered         INTEGER CHECK (entered IS NULL OR entered >= 0),
    equity          ANY     CHECK (equity IS NULL OR typeof(equity) = 'text'),
    pairs           TEXT    CHECK (pairs IS NULL OR json_valid(pairs)),
    excluded        TEXT    CHECK (excluded IS NULL OR json_valid(excluded)),
    rank_feature    TEXT    CHECK (rank_feature IS NULL OR trim(rank_feature) <> ''),
    rank_descending INTEGER CHECK (rank_descending IS NULL OR rank_descending IN (0, 1)),
    rank_skipped    TEXT    CHECK (rank_skipped IS NULL OR json_valid(rank_skipped)),
    ranked          TEXT    CHECK (ranked IS NULL OR json_valid(ranked)),
    rank_run_ids    TEXT    CHECK (rank_run_ids IS NULL OR json_valid(rank_run_ids)),
    updated_at      INTEGER NOT NULL,
    UNIQUE (run_id, cycle_id)
) STRICT;

CREATE INDEX idx_scout_tallies_ts ON scout_tallies (ts);
