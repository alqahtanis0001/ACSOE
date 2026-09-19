# 145 — Every gate's verdict, recorded on both sides of every decision

**Owner:** C — Interface and models (engine 19). B adds the column (to migration 0006, before it is
committed).

**Phase:** 7. Operator ruling 2026-09-19 (F-new-1 changed from recorded-not-fixed to fixed):
*"the system stores the reasoning for approvals as well as refusals, so both sides of every
decision are answerable."* Approved over the two-hour mark, **before the run**. Sequenced after
spec 133 and before spec 140's writer, each through its own gate, one change at a time through
engine 19.

## Goal

Every approval and every refusal records **the verdict of every engine that judged the candidate on
that tick**: the value it computed and the threshold it compared against. That answers two
questions: *why was it approved*, and *how close did the other gates come*. The second cannot be
asked of the store today.

- **An approval** records it in `approvals.details` (a new column).
- **A refusal** records it in `rejections.details`, which has existed since 0001 and is filled by
  nothing. It covers every engine that ran before the refusing one, **plus the refusing engine's own
  values**, marked as the refuser.

## Implementation

1. **B:** `approvals.details TEXT` in `db/migrations/0006_approval_economics.sql`, nullable. Added
   while 0006 is uncommitted, so no new migration. The row model and the reader carry it.
   `rejections.details` is unchanged.
2. **C, `engines/memory/contracts.py`:** one declared table, `VERDICT_FIELDS`: engine name → the
   ordered field names recorded from its payload. The fields are those each engine already
   publishes (nothing new is published):
   - `anomaly`: score, threshold, anomalous, model_run_id
   - `prediction`: p_target, p_stop, p_timeout, expected_move_pct, is_buy, di, di_threshold,
     model_run_id (`shap` is excluded; it is spec 140's Parquet)
   - `order_book`: the estimated slippage and its basis, as its contract names them
   - `cost`: expected_move_pct, friction_pct, net_edge_pct, hurdle_pct, clears_hurdle, and the fee,
     spread and slippage components it publishes
   - `risk`: approved, qty, notional, risk_amount
   - `regime`: label
   - `adaptive_router`: active_model_run_id, di_margin, regime
   - `skeptic`: p_wrong, threshold, vetoed, model_run_id
   - `decision`: coherent, checked
   - `scout`: pair, and the ranking values it publishes (spec 144)

   **A test walks each named engine's `contracts.py` and fails if a listed field does not exist**,
   so a rename goes red instead of silently recording nothing.
3. **C, engine 19:** on the placing tick (spec 133's trigger), build the snapshot from `state` for
   every opportunity-chain engine present in `state` in chain order, and write it with the
   approval. On a refusal, build it the same way for every engine that ran, with
   `"refused_by": <engine>`. The snapshot is canonical JSON (sorted keys, no whitespace) with a
   `details_version: 1`.
   - Money fields stay exact decimal strings, and statistics stay floats, exactly as published.
   - A field an engine did not publish is **absent from the snapshot, never null-filled**, because
     absent and null are different facts.
   - An errored engine records `{"status": "ERROR"}` and nothing else.
4. The console is unchanged (spec 140's screens come after the run).

## Scope Limits

- **No engine publishes anything new, and no gate's verdict changes.** Engine 19 reads `state` and
  writes; nothing else moves.
- No backfill of rows written before this change.
- Not in `rejections`' existing columns: `details` only.
- A snapshot that cannot be built (a malformed payload) records what it can and never fails the
  tick, because engine 19 is the single writer and a lost tick is worse than a partial snapshot.
  That case is tested.

## Check When Done

- On the rehearsal harness's round trip, the approval's `details` equals each engine's published
  payload restricted to `VERDICT_FIELDS`, **recomputed from `state` and not read back**. A refusal at
  the skeptic records anomaly, prediction, order_book, cost, risk and router, with the skeptic as
  `refused_by`.
- Mutations: drop the refusing engine; null-fill absent fields; record a float for a money field;
  record engines after the refuser. Each is killed.
- The migration test shows a pre-0006 database migrating, with `approvals.details` NULL.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
