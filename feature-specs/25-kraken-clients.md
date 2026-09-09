# 25 — Kraken REST and WebSocket clients

**Owner:** A — Platform

## Goal

`src/acsoe/clients/kraken/` becomes the system's only route to the exchange: a REST client, a
WebSocket v2 client, a rate limiter, and the contracts every consumer reads. No engine in this
phase touches a socket; they all go through this.

## Implementation

1. Create `src/acsoe/clients/kraken/contracts.py` — the pydantic models named in `ownership.md`'s
   seam table: raw ticks, pair rules, fee tier, and the last-known-good values retained for
   emergency liquidation. This file is the contract B and C read; it lands **first** so they can
   mock against it.
2. Create `src/acsoe/clients/kraken/rest.py` — `httpx` + `tenacity`. **Every response parses
   through a `KrakenEnvelope` at the client boundary and raises `KrakenAPIError` on a non-empty
   `error` array**, per `AGENTS.md`: Kraken wraps everything in `{"error": [...], "result": {...}}`
   and does not use HTTP status for application errors, so a 200 with a populated `error` array is
   a failure, not a fill.
   **The envelope needs both halves of the test.** A parser that raised on every response would
   satisfy "a 200 with a populated `error` array raises" perfectly well and be useless. So assert
   the positive too: a 200 with an **empty** `error` array parses cleanly and yields its `result`.
   One test without the other proves nothing about the discrimination, which is the only thing the
   envelope is for.
3. Fee tier comes from `POST /0/private/TradeVolume`; order minimums, tick size and precision come
   from `GET /0/public/AssetPairs`. **Both at runtime, never a constant** — `AGENTS.md` is explicit
   that any remembered value is stale.
4. Create `src/acsoe/clients/kraken/ws.py` — Kraken WebSocket v2, `websockets`, with reconnect and
   a subscription model engine 2 drives.
5. Create `src/acsoe/clients/kraken/limiter.py` — the rate limiter, shared by both transports.
6. Credentials come from the environment only (`KRAKEN_API_KEY`, `KRAKEN_API_SECRET`), read
   through `platform/config.py`'s existing machinery. **Never logged, never printed, never written
   to an artefact.**
7. Write `src/acsoe/clients/kraken/README.md` covering the envelope rule, what is fetched at
   runtime, and the retained last-known-good values.

## Scope Limits

- Do **not** write any engine. Engines 1 to 4 are specs 26 to 29.
- Do **not** hardcode a fee, an order minimum, a tick size, or a precision — not even as a
  fallback, not even in a comment that later becomes code.
- Do **not** place, amend or cancel an order. This phase is read-only against the exchange;
  `AddOrder` belongs to Phase 6.
- Do **not** let a test reach the network. `tests/conftest.py`'s guard is autouse and stays that
  way; test against C's fake client and the committed fixtures under `tests/fixtures/kraken/`.
- Do **not** read the clock directly anywhere in this package; take the injected `Clock`.
- Do **not** widen `data/` or `logs/` handling here — spec 27 owns the recorder's writes.

## Check When Done

- **Both halves of the envelope check, as a pair:** a 200 carrying a non-empty `error` array
  raises `KrakenAPIError`, **and** a 200 carrying an empty `error` array parses cleanly and
  returns its `result`. Neither assertion is worth anything without the other.
- Fee tier and pair rules are fetched, not constant: a test asserts the values come from the
  fixture payload and changes when the fixture changes.
- The rate limiter serialises bursts without exceeding the configured budget.
- No secret appears in any log line, exception message, or repr — one test plants a key and scans
  the captured output, the same shape as A's Phase 0 redaction test.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 2`
