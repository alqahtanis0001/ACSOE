# 41 — Wire engine 11 `risk` to the real `state["exchange"]`, and give it a price

**Owner:** B — Store and trading

**Phase:** 3 — Economics.

## Goal

Engine 11 sizes against the payload engine 1 actually publishes, and takes its entry price
from a publisher that exists. Today it reads `state["exchange"]["pairs"][pair]["last_price"]`,
and **nothing in the system writes a price into `state["exchange"]` at all** — the only
`last_price` in the codebase is a column on an open position row.

## Implementation

1. **The pair-rules path is nested.** `EXCHANGE_PAIRS_KEY` is `"pairs"`; engine 1 publishes
   `pair_rules`, itself a mapping of `{fetched_at, pairs: {...}}`. The real path is
   `state["exchange"]["pair_rules"]["pairs"][pair]`. Fix the constants and keep both levels
   going through `_require`, so a null `pair_rules` — the failed-`AssetPairs` case — reports
   as the missing thing it is.
2. **`state["exchange"]["balances"]` is correct** as written: a flat `{currency: decimal
   string}` map. Change nothing.
3. **`fallbacks_used` does not exist on `state["exchange"]`.** Same finding as spec 40, and
   the same fix: delete the dead read. But risk has the one surviving obligation —
4. **Risk applies the balance fallback, because after spec 37 it is the only paper-mode
   fallback left.** In `paper` mode, when `balances` is absent because the `Balance` fetch
   failed, size against `paper.starting_balances` and record
   `balance_from_paper_starting_balances` in `fallbacks_used`. In `live` mode, block. The
   fallback is the configured map as written — "adjusted by simulated fills" is the fill
   simulator's contribution and that is Phase 6, so say in the `README.md` that the
   adjustment is not yet applied and name the phase that applies it.
   Invariant 2: a fallback may only make the system *less* willing to trade, and a
   configured starting balance is not larger than a real one in any case this gate cares
   about — if it were, the quote-balance check would be the thing that noticed.
5. **The entry price.** Take it from `state["market_sensor"]["quotes"][pair]`, the same
   publisher the cost gate reads its spread from. Absent quote, absent pair, or a
   non-positive price is a block — never a fallback, and never a price carried over from a
   previous tick.
   - Size the quantity from the **ask**. The entry is a buy, the ask is the worst price that
     buy could pay, and a higher assumed price yields fewer units for the same notional — so
     the position is never larger than the sizing chose.
   - Test `costmin` against the **bid**, the lowest the position could be worth. Rounding
     down and then valuing at the lower side is fail-closed on both edges: a marginal
     position is rejected rather than admitted.
   - **This is a lead ruling, made because nothing published a price and one had to be
     chosen.** Record it in `engines/risk/README.md` with the reasoning above, so the next
     agent can see it was decided rather than defaulted. It does not double-count the
     spread: engine 10 charges the spread as *friction on a round trip*, engine 11 uses the
     book to answer *how many units the money buys*. Two different questions on the same
     data.
6. Rewrite the "state paths are B's proposal" note in `engines/risk/contracts.py` to say
   which paths are now the publisher's and which were assumed and found wrong.

## Scope Limits

- Do **not** round a sub-minimum position up. Unchanged and untouchable.
- Do **not** size against the quote balance instead of equity. Invariant 6 says total
  account equity, equity comes from `equity_snapshots`, and no snapshot is a block.
- Do **not** invent a price from a candle, a mid, a previous tick, or a position row.
- Do **not** apply a paper-mode fallback for pair rules or for the spread. Both block.
- Do **not** apply the balance fallback in live mode, under any flag.
- Do **not** write in `engines/exchange/`, `engines/market_sensor/`, `clients/kraken/`,
  `core/`, or `bootstrap.py`.

## Check When Done

- **The seam is driven end to end with no double on either side**, as in spec 40: A's real
  `ExchangeEngine` and real `MarketSensorEngine` run against C's fake client and its
  fixtures, their `result.data` becomes `state`, and this gate sizes a real position from
  it. Every existing test builds those dicts by hand and two of the shapes are wrong.
- The block test and the pass test both still hold through that real payload: one increment
  below `ordermin` is **rejected**, not resized — the returned quantity is absent, not
  bumped — and at or above it passes.
- Changing `ordermin` in the fixture changes which sizes are rejected.
- Sizing uses the ask and `costmin` uses the bid: a fixture with a wide spread where the two
  differ, asserting the exact `Decimal` quantity and the exact `Decimal` value. A
  mid-price implementation gives a different number and fails.
- Paper mode with a failed `Balance` sizes against `paper.starting_balances` and reports
  `balance_from_paper_starting_balances`; **live mode with the same failure blocks.** Both,
  as a pair — the paper half alone would pass against an implementation that never checks
  the mode.
- A pair with no quote blocks, with a reason naming the pair.
- No `float` in any sizing path.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
