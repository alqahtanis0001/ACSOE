# 129 — The replay client: historical trades, recorded rules, a declared book and a declared fee

**Owner:** A — Platform

**Phase:** 7. Depends on 127 (rules), 128 (trades) and 130 (the declared table and fee fixture).

## Goal

A client in `clients/kraken/` that implements the surfaces engines 1, 2, 3 and 9 and the paper
broker read from the live client, and serves them from history. **No engine changes and no engine
branches on mode.** Engine 9 walks the book it is given with its own arithmetic. The mode
difference lives in the client layer, as `architecture-context.md` requires.

## Implementation

1. **Construction refuses outside replay mode.** A test proves construction fails in paper and live
   mode, which is the enforcement invariant 2's amendment (spec 126) requires.
2. **The stream.** Up to `context.now`, serve the trades of the weekly partitions for every pair
   the client lists, in timestamp order, never one second past `now`. Engine 3 drains them into
   candles and `trade_ranges` exactly as it drains the live stream. Recorder gap markers are never
   synthesised: history has no outages, and a fabricated gap would be a fabricated `data_guard`
   block.
3. **The synthetic top of book and the order book.**
   - For each pair at `now`, centre the book on the last traded price at or before `now`.
   - Take the half-spread and the depth from spec 130's bucket table, using the pair's trailing
     24-hour dollar volume computed from the served trades.
   - Build 10 bid and 10 ask levels whose cumulative notional reaches $10,000 at the bucket's
     recorded depth distance, evenly spread.
   - `order_book(pair, depth)` returns that book, and the stream's book and ticker messages carry
     its top.
   - A pair with no trade in the trailing window has **no quote**, so engine 7 excludes it as
     `no_live_quote`. That is never a zero spread.
4. **Pair rules:** spec 127's recorded file, served through the same parser as live. A pair absent
   from it is absent, and engine 7 excludes it as `pair_rules_missing`. That exclusion is the
   survivorship the findings name, and it is recorded, not patched.
5. **Fees:** the operator's fee scenario fixture, at the tier `replay.fee_tier` names, served
   through the `TradeVolume` surface. An absent fixture or tier is a failed fetch, and engine 10
   blocks as it would live.
6. **Balance:** none. The paper broker wraps this client and is the account (invariant 2's paper
   ledger), exactly as in paper mode.
7. **The scenario identity.** Expose one digest covering the rules file, the bucket table, the fee
   fixture and tier, and the partition manifest. Spec 134 writes it to the `runs` row.

## Scope Limits

- Nothing here estimates anything. Every number the client serves is a recorded trade, a recorded
  rule, or a value read from a declared fixture.
- Do not touch `clients/paper/`. If the broker needs a surface this client lacks, agree the
  contract with B and mock it.
- No engine file changes. If an engine cannot run against this client, the finding goes to the
  lead.

## Check When Done

- Construction refused in paper and live, each proven.
- Engine 9 run against the synthetic book reproduces a hand-computed walk for one thin bucket and
  one deep bucket.
- The stream never yields a trade stamped after `now`, proven by a clock that lags a planted
  trade.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
