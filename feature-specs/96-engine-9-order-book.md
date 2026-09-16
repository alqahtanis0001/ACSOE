# 96 — Engine 9 `order_book`, and the book fixture it is validated on

**Owner:** C — Interface and models

**Phase:** 6. `engines/order_book/` and `tests/fixtures/` are C's.

## Goal

Engine 9 estimates the slippage the candidate's exit would pay and publishes it as
`state["order_book"]["estimated_slippage_pct"]`, the key engine 10 has read since Phase 3 — so the
cost gate stops blocking every candidate for want of it. It is validated against a committed book
fixture cut from the live archive, and its README says plainly how little that validates.

## Implementation

1. `engines/order_book/engine.py`, `contracts.py`, `README.md`. `name = "order_book"`,
   `number = 9`, `is_gate = False`. Opportunity chain, after 8, before 10.
2. **Reads** `state["scout"]["pair"]`; the book through `context.clients.kraken.order_book(pair,
   depth)` with `depth` from config key `order_book.depth` (requested of the lead, spec 80);
   `state["exchange"]["balances"]` and pair rules for the quote currency.
3. **What is estimated, and the size it is estimated at — lead ruling, flagged as overturnable.**
   Friction assumes maker entry and taker exit, so the slippage that matters is a **taker sell
   walking the bid side**. Engine 9 runs before engine 11 sizes the order, so the size is not yet
   known. It estimates at the **largest notional engine 11 could approve: the account's whole
   balance in the pair's quote currency**, because invariant 6 forbids allocating more than that
   and slippage does not fall as size rises — so the estimate is an upper bound and the cost gate
   errs toward refusing. `estimated_slippage_pct` = (best bid − volume-weighted fill price) / best
   bid over that walk, exact `Decimal`, published beside **`pair`**, `basis_notional` and
   `levels_consumed`.

   **`pair` corrected into this list 2026-09-16.** The engine always published it; *this spec's
   field list omitted it*, and C-models read the list rather than the contracts module and told B
   on that basis that engine 9 publishes no `pair` — which would have left engine 16's coherence
   walk silently exempting the one engine whose entire output is defined by a pair. Take it
   **verbatim from `state["scout"]["pair"]`**, so the walk compares a value against its own
   source. A spec's field list is a description; `contracts.py` is the fact, and where they
   disagree the spec is what is wrong.
4. **Fail-closed shapes, and engine 9 does not block on any of them.** It is not a gate, and a
   non-gate that refuses on its own criteria makes `is_gate` wrong — the principle the operator
   applied to engine 16. (Engine 8's `di_refused` block is the one operator-ruled exception,
   2026-09-12, and is not a precedent to extend.) So on each shape — book fetch failed; the bid
   side cannot absorb the basis notional within `depth` (`book_too_thin`: an estimate past the
   fetched depth would be a guess); a crossed or empty book; no quote balance — engine 9 returns
   `OK`, **omits** `estimated_slippage_pct`, and publishes the shape's `reason_code`. Engine 10, a
   gate, then refuses on the absent key. A test drives both engines together and asserts the
   refusal is engine 10's and engine 9's reason code is in its payload.
5. **The fixture.** Choose one deep pair and one thin pair from the tier-1 recording and a window
   of a few minutes with no gap; run A's `scripts/cut_book_fixture.py` (spec 86); deposit
   `tests/fixtures/book_sample.jsonl`; list it in `tests/fixtures/README.md` with its provenance.
6. **The README states the bound**, in these terms: engine 9 is validated over seconds to minutes
   of recorded book, not years of archive, because the historical archive carries no book at all;
   so nothing here says how slippage behaves across regimes, sizes or years, and every slippage
   number this system reports inherits that limit. The same sentence goes into the tracker via
   spec 80.
7. Tests in `tests/engines/test_order_book.py`: the fixture replayed into the fake client's book;
   the walk at several notionals against a hand-computed expected fill for **both** the deep and
   the thin pair; `book_too_thin` on the thin pair at a notional past its depth; every fail-closed
   shape by reason code; money never a float.

## Scope Limits

- Do **not** read `data/`. Tests and the criterion read the committed fixture only.
- Do **not** estimate the entry's slippage. A post-only maker entry takes none.
- Do **not** extrapolate past the fetched depth.
- Do **not** size the order or duplicate engine 11's sizing arithmetic.

## Check When Done

- Mutations observed red, killing test named: the ask side walked; the walk stopping one level
  early; slippage computed from mid rather than best bid.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
