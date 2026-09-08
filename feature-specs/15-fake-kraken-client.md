# 15 — Fake Kraken client with recorded fixtures

**Owner:** C — Interface and models

## Goal

A deterministic stand-in for the exchange that satisfies the `kraken` half of the `Clients`
Protocol, so every engine test runs offline against recorded responses.

## Implementation

1. Create the fake in `tests/harness/` implementing the same Protocol as the real client.
2. Back it with recorded fixture responses for `AssetPairs`, `TradeVolume`, `Balance` and an
   order book snapshot, stored under `tests/fixtures/` as committed JSON.
3. Make every value injectable per test: fee tier, `ordermin`, `costmin`, tick size,
   decimals, balances, spread. Phase 3 needs to vary the fee tier and balances and see the
   universe and the cost gate respond.
4. Model failure explicitly: each call can be configured to fail, so fail-closed behaviour and
   the paper-mode fallbacks are testable, and so is a stale cache past its TTL.
5. Reproduce Kraken's envelope faithfully — a non-empty `error` array with HTTP 200 is a
   failure, and the fake must be able to produce exactly that.
6. Add `tests/harness/test_fake_kraken.py` proving the fake matches the Protocol, that a
   configured failure raises the same error type the real client would, and that the 200-with-
   error case is treated as a failure.

## Scope Limits

- Do **not** hardcode a fee, minimum, tick size or precision as a system default. These are
  *test fixtures* for a fake exchange, never values the system falls back on.
- Do **not** let the fake touch the network.
- Do **not** implement the real client; `clients/kraken/` is A's and lands in Phase 2.
- Do **not** make the fake succeed where the real client would fail; a fake that is kinder
  than reality hides fail-closed bugs.

## Check When Done

- The fake satisfies the Protocol and is accepted where a real client is expected.
- A configured failure produces the same error type as the real client's contract.
- A 200 response carrying a non-empty `error` array is treated as a failure.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
