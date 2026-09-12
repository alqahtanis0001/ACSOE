# 74 — Engine 20 `tournament`

**Owner:** C — Interface and models

**Phase:** 5. `engines/tournament/` is C's; it runs in `OFFLINE_CHAIN` via `cli/research.py` (A).

## Goal

The leaderboard has rows. Engine 20 scores every trained model version against realised
outcomes and writes one `leaderboard` row per version through the store, so that Phase 6's
adaptive router has something to weight by and Phase 7's promotion gate has something to judge.
In Phase 5 the realised outcomes are the labels; from Phase 6 they will also be trades.

## Implementation

1. `engines/tournament/engine.py`, `contracts.py`, `README.md`. `name = "tournament"`,
   `number = 20`, `is_gate = False`. Constructed with the path of a training digest; A's
   `acsoe research` passes it from `--digest`.
2. Reads spec 67's digest and OOS file for the run, and for each fold's model version writes
   a `LeaderboardRow`: `model_id = "predictor"`, `model_version = run_id`, `training_run_id`,
   `trained_at` from the manifest, `fold`, `n_trades` = BUY calls in the fold's test window,
   `win_rate` = target rate among them, `brier`, `net_pnl` = the sum of `return_pct` over BUY
   calls expressed as a decimal string in `trading.base_reporting_currency` units of one, and
   `promoted = False`. `sharpe`, `deflated_sharpe`, `alpha` and `beta` stay null: they are
   Phase 7's, and a number written here now would be read as one.
3. **Idempotent.** A `(model_id, model_version, fold)` already present is not written twice;
   the engine reports how many rows it wrote and how many it found.
4. Reports in `data`: rows written, rows skipped, the best and worst Brier across folds with
   their fold ids, and the base-rate Brier beside each.
5. `tests/engines/test_tournament.py`, C lane, against a real `StoreClient` on a temporary
   database and a digest built from the committed sample.

## Scope Limits

- Do **not** promote. `promoted` is always false here; the promotion gate is Phase 7.
- Do **not** read the archive. Engine 20 reads the store and the digest only,
  `architecture-context.md`.
- Do **not** compute alpha, beta, a deflated metric or a Sharpe.
- Do **not** write any relational row but `leaderboard`.

## Check When Done

- `tournament_writes_leaderboard_from_oos` PASS, observed FAIL with `promoted` forced true and
  with the write routed around the store client.
- The Phase 1 console's leaderboard screen renders the rows engine 20 wrote, checked by hand
  and recorded.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 5`
