# 06 — `config/default.yaml` with every threshold named

**Owner:** Lead

## Goal

One configuration file holds every threshold the system uses, so no magic number reaches an
engine and every limit is auditable in one place.

## Implementation

1. Create `config/default.yaml`. `mode: paper`.
2. Name at minimum, grouped by area:
   - `console`: `port` 8765, `poll_interval_ms` 500, `stale_after_ms` 120000.
   - `safety`: `max_consecutive_data_blocks` 15, plus the drawdown limit, loss-streak limit
     and error-rate window the breaker reads.
   - `paper`: `starting_balances` as a currency-to-amount map.
   - `trading`: `hurdle_multiple`, `risk_fraction_per_trade`, `max_concurrent_positions`,
     `entry_unfilled_window_s`, `allow_crypto_quoted: false`, `base_reporting_currency`.
   - `barriers`: `target_pct` 0.03, `stop_pct` 0.015, `timeout_bars` 48.
   - `timeframes`: `decision_bar_s` 900, `loop_tick_s` 60.
   - `logging`: `level` `"INFO"`, `retention_days` 14 — requested by A for spec 08, approved.
   - `backtest`: `training_window_days` 90, `retrain_interval_days` 7.
   - `seeds`: every random seed, so a training run is reproducible from config plus data.
4. **A key the context files name but never value is written as `null` and marked OPERATOR
   REQUIRED.** Eight of them are trading behaviour — `trading.hurdle_multiple`,
   `risk_fraction_per_trade`, `max_concurrent_positions`, `entry_unfilled_window_s`,
   `base_reporting_currency`, `paper.starting_balances`, and `safety`'s drawdown, loss-streak
   and error-rate limits. AGENTS.md forbids inventing trading behaviour, and a plausible
   default here is a number that silently decides how much money is at risk. The loader
   refuses to start while any is null, naming the key.
3. Every value carries a short comment saying what it controls and its unit. Percentages are
   decimals — `0.03`, not `3`.
4. Add `tests/core/test_default_config.py` asserting the file parses, `mode` is `paper`, and
   the constraint `console.poll_interval_ms <= console.stale_after_ms / 4` holds.

## Scope Limits

- Do **not** write the loader or the pydantic model; spec 07 owns those.
- Do **not** put a fee, an order minimum, a tick size or a precision in this file. Those come
  from the exchange at runtime and appear nowhere as constants.
- Do **not** set `mode: live` in this or any other committed file, fixture or example.
- Do **not** add a key an agent has not requested; A requests, the lead adds.

## Check When Done

- The file parses and every threshold this phase needs is present and commented.
- No exchange-supplied value appears anywhere in it.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
