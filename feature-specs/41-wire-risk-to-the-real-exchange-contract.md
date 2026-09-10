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
4. **New behaviour, not a wiring detail: risk applies the paper-mode balance fallback, and
   nothing in the system currently applies it.** Read that twice before treating this step as
   a repoint. With "assume tier 1" retired by spec 37, invariant 2's paper-mode table has
   exactly one surviving fallback — balance — because pair rules block, the spread blocks,
   and the fee tier now blocks too. Engine 1 deliberately applies no fallback of its own, on
   the stated grounds that the consumer is the one that has to record which fired. **So the
   single remaining fallback in the whole system has no implementer, and this spec is where
   it gets one.** It is a behaviour being built: it needs its own tests, its own paragraph in
   the `README.md`, and its own build-log entry — not a line in a wiring diff.
   - In `paper` mode, when `balances` is absent because the `Balance` fetch failed, size
     against `paper.starting_balances` and record `balance_from_paper_starting_balances` in
     `fallbacks_used`.
   - In `live` mode, block. Invariant 2: in live mode a failed fetch always blocks, and the
     one exception in that document is rule 14's liquidation, which is not this.
   - The fallback is the configured map as written. "Adjusted by simulated fills" is the fill
     simulator's contribution and that is Phase 6; say so in the `README.md` and name the
     phase, so the gap is recorded rather than discovered later.
   - Invariant 2: a fallback may only ever make the system *less* willing to trade. A
     configured starting balance is not larger than a real one in any case this gate cares
     about — and if it ever were, the quote-balance check is what would notice.
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
- **Every test that hand-builds `state["exchange"]` is rewritten** to build it from engine
  1's actual output, or from a fixture derived from it. Operator ruling 2026-09-10, same
  reasoning as spec 40: a mock that agrees with its caller is what hid this for a whole
  phase, and it is the third appearance of that shape in this project.
- The block test and the pass test both still hold through that real payload: one increment
  below `ordermin` is **rejected**, not resized — the returned quantity is absent, not
  bumped — and at or above it passes.
- Changing `ordermin` in the fixture changes which sizes are rejected.
- Sizing uses the ask and `costmin` uses the bid: a fixture with a wide spread where the two
  differ, asserting the exact `Decimal` quantity and the exact `Decimal` value. A
  mid-price implementation gives a different number and fails.
- **The balance fallback carries its own tests, as the new behaviour it is.** Paper mode
  with a failed `Balance` sizes against `paper.starting_balances` and reports
  `balance_from_paper_starting_balances`; **live mode with the same failure blocks.** Both,
  as a pair — the paper half alone passes against an implementation that never checks the
  mode. A third asserts the fallback is recorded on the *decision*, per invariant 2: an
  approved sizing carries `fallbacks_used`, and so does a rejection produced on a tick where
  the fallback fired.
- A pair with no quote blocks, with a reason naming the pair.
- No `float` in any sizing path.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
