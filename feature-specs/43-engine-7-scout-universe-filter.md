# 43 — Engine 7 `scout`, part 1: the tradable universe

**Owner:** B — Store and trading

**Phase:** 3 — Economics. Zero ML.

## Goal

`src/acsoe/engines/scout/` exists and computes, per tick, the set of Kraken pairs the
account could legitimately trade right now — from live pair rules, the live book and the
live balance, and from nothing that anyone typed into a config file.

## Implementation

1. Create `src/acsoe/engines/scout/` — `engine.py`, `contracts.py`, `README.md`.
   `name = "scout"`, `number = 7`, **`is_gate = True`**, **opportunity** chain, runtime
   stage 2, per the registry table.
2. **The universe is computed per tick over every pair `AssetPairs` reports.** A Locked
   Decision: *"Tradable universe computed per tick from `ordermin`, `costmin`, tick size,
   live spread and balance. No account-size thresholds."* There is no pair list, no config
   key holding one, and no threshold of the form "if balance < X". The filter is arithmetic
   and the balance is one of its inputs.
3. Inputs, all from `state` or the store, none from a constant:
   - `state["exchange"]["pair_rules"]["pairs"]` — `ordermin`, `costmin`, `tick_size`,
     `lot_decimals`, `pair_decimals`, `base`, `quote`
   - `state["exchange"]["balances"]` — per-currency spendable balance
   - `state["market_sensor"]["quotes"][pair]` — `bid`, `ask`, `spread_pct`
   - `context.clients.store.latest_equity_snapshot()` — total account equity
   - config: `trading.risk_fraction_per_trade`, `barriers.stop_pct`, `barriers.target_pct`,
     `trading.allow_crypto_quoted`, `trading.base_reporting_currency`
4. **A pair enters the universe only if every one of these is true.** Each exclusion is
   recorded with its own reason code, because the console's empty state is built from these
   counts — *"Scanned 412 pairs. 38 entered the tradable universe."*
   - Its rules are present. A pair absent from `pair_rules` is excluded. Invariant 2 gives
     pair rules no fallback in any mode.
   - It has a live quote. No quote is an exclusion, never an assumed spread — invariant 2 is
     explicit that an assumed spread invalidates the cost gate.
   - Its quote currency is held with a **positive** spendable balance. Invariant 7.
   - It is not crypto-quoted, unless `trading.allow_crypto_quoted`. Invariant 7.
   - The position this equity would size clears **`ordermin`** after rounding down to
     `lot_decimals`, and clears **`costmin`** at its value. Same arithmetic as engine 11 —
     see step 6.
   - **The barriers are expressible on the pair's tick grid.** `target_pct` and `stop_pct`
     of the entry price must each exceed one `tick_size`. This is what `tick_size` is doing
     in the Locked Decision's list: on a pair whose tick is coarse relative to its price,
     a −1.5% stop rounds onto the entry price itself and the position has no stop at all.
     Excluding such a pair is the only fail-closed answer, and it is arithmetic, not a
     threshold.
5. **Publish the counts, not just the survivors.** `state["scout"]` carries the number
   scanned, the number that entered, and a per-reason tally of the exclusions. The
   console's most-viewed screen state is the one where nothing qualified, and it renders
   from these numbers.
6. **The sizing arithmetic exists twice and must not drift.** Engine 11 `risk` sizes the
   position; this filter asks whether a position is possible at all. Contract rule 3 forbids
   one engine importing another, so the arithmetic is written twice on purpose — and a test
   asserts the two agree over a shared table of cases spanning both sides of `ordermin` and
   `costmin`. Name that test in both engines' `README.md` as the thing that holds them
   together.
7. Write `README.md`: what the universe is, that it is recomputed every tick, the exclusion
   reasons and their codes, and that engine 7 is deterministic and protected — invariant 4
   says no model output may override it, and it contains no model.

## Scope Limits

- Do **not** add a config key holding pairs, a default pair list, or a hardcoded symbol.
  Not in code, not in a fixture used by production, not in a comment.
- Do **not** hardcode `ordermin`, `costmin`, a tick size, a precision, or a fee.
- Do **not** apply a fallback for pair rules or for the spread. Both exclude the pair.
- Do **not** add an account-size threshold. If the filter contains a comparison of the
  balance against a literal, it is wrong.
- Do **not** rank, score, or choose a candidate here. That is spec 44.
- Do **not** import from `engines/risk/` or any other engine.
- Do **not** write in `engines/exchange/`, `engines/market_sensor/`, `clients/kraken/`,
  `core/`, or `bootstrap.py`.

## Check When Done

- **The Phase 3 criterion, literally:** the same fixture set yields **different pair counts
  at a $10 balance and at a $5,000 balance.** Assert both counts and assert they differ; a
  filter that ignores the balance passes an equality test and fails this one.
- Each of the six exclusion rules has its own test, and each is proved to be the *only*
  thing excluding that pair — flip the one input, and the pair enters.
- The tick-grid rule: a pair whose `tick_size` exceeds `stop_pct × price` is excluded, and
  the same pair at a finer tick enters. This one is easy to write so it never fires; make it
  fire.
- A pair with no live quote is excluded and is **not** treated as a zero spread.
- The sizing cross-check against engine 11 passes over the shared table, including the cases
  one increment either side of `ordermin`.
- The counts published add up: scanned equals entered plus the sum of the exclusion tally.
- Driven from A's real engine 1 and engine 3 output, not from hand-built dicts.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
