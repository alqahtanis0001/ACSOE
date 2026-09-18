# Engine 1 — `exchange`

**Number:** 1 · **Chain:** guard · **Gate:** no · **Runtime stage:** 1

The account picture, fetched fresh every tick and published for everything
downstream: what the account holds, what it is charged, and what each pair's rules
are.

## What it reads from `state`

**Nothing.** It is the first engine of the first chain, so there is nothing in `state`
yet to read. `process` takes `state` because the interface is fixed; it never touches
it.

## What it writes into `state["exchange"]`

| Key | Type | Meaning |
|---|---|---|
| `fetched_at` | int | `context.now` in microseconds since the epoch, UTC |
| `balances` | `{currency: "amount"}` or `null` | `POST /0/private/Balance` |
| `fee_tier` | object or `null` | `POST /0/private/TradeVolume`: `tier`, `currency`, `volume_30d`, `maker_fee_pct`, `taker_fee_pct`, `fetched_at` |
| `pair_rules` | object or `null` | `GET /0/public/AssetPairs`: `fetched_at` plus `pairs`, keyed by symbol, each with `ordermin`, `costmin`, `tick_size`, `lot_decimals`, `pair_decimals`, `base`, `quote` |
| `failed_fetches` | list | One entry per call that did not answer: `call`, `kind` (`api_error` \| `unavailable`), `reason` |
| `retained` | list | One entry per last-known-good value the client still holds: `call`, `fetched_at`, `age_micros` |

**Every money value is an exact decimal string** — `"0.0025"`, not `0.0025`.
`EngineResult.data` refuses a `Decimal` and *accepts* a `float`, so the reflexive
`float()` cast on hitting that refusal is the dangerous mistake: a fee published as a
float arrives in engine 10's hurdle comparison wrong in the fourth decimal, which is
the magnitude that gate works at. Consumers read them back with `Decimal(str(value))`,
which round-trips exactly.

**Live spread is not here.** It belongs to engine 3 `market_sensor`, at
`state["market_sensor"]["quotes"][pair]["spread_pct"]` — ratified by the lead on
2026-09-09. Engine 1 is the *account* engine; engine 3 is the *market-data* engine,
and engine 4 blocks on three market-data faults that should all arrive from one place.

## It is not a gate, and that is deliberate

`is_gate = False`, matching the registry table in `context/engine-contracts.md`, which
`is_gate_matches_registry` asserts. **Engine 1 never sets `blocks_trading`, not even
when all three fetches fail.**

That is the design decision most likely to be "corrected" by a later reader, because
an empty account picture obviously should not produce a trade. Three reasons it stays:

- It would be a fifth gate nobody registered, in a system whose gate list is fixed by
  invariant 3.
- It runs first, so it would set `state["trading_blocked_by"] = "exchange"` and mask
  the real blocker on the same tick — and `block_records.is_primary` is exactly that
  first blocker, so the research record would be wrong too.
- `data_guard` blocking is what makes the manage chain hold exits. Giving engine 1 a
  block gives it a say in whether an open position gets managed, which is not a
  judgement about the account picture.

Reporting the absence honestly is enough. Every gate that needs a value it did not
get blocks on its own — that is invariant 3, and it fails closed without engine 1
having to.

## A failed fetch is recorded, never defaulted

The three calls run concurrently with `return_exceptions=True`, so one outage does not
become three blanks: a consumer has to know exactly which value it is missing. Engine
10 `cost` is the reader that makes the granularity load-bearing — when the fee tier is
absent and `trade_volume` is the call named in `failed_fetches`, its block sentence
quotes *that call and its reason*, because "missing exchange.fee_tier" is true and
sends the operator to look at a `None`.

**This engine substitutes nothing, and no consumer substitutes either.** `fee_tier` is
`null` when `TradeVolume` failed; it is never "assume tier 1". Invariant 2 is the place
to read why, and it is shorter than it used to be: no paper-mode fallback remains
anywhere in the system, and a failed fetch blocks in paper mode exactly as in live. So
the absence engine 1 publishes is the answer, not a placeholder somebody downstream is
expected to fill in. Supplying a tier here would be a hardcoded fee besides, which
invariant 2 forbids outright.

An exception that is not exchange-shaped is **re-raised**, not recorded. That is a
defect on our side of the boundary, and contract rule 7 says an engine must not
swallow its own exceptions to avoid `ERROR`.

## Retained last-known-good values

`retained` reports *that* the client is still holding a last-known-good `AssetPairs`
or `Balance` and how stale it has become. **It is not the value.** Invariant 2: for
trading, a stale value does not exist. Only rule 14's emergency liquidation may use
one, and engines 21 and 22 read it from the client directly in Phase 6 — publishing it
here would put it one attribute lookup away from a gate that must never see it.

## Async, from a synchronous engine

The exchange client is async and `process` is not. `platform/aio.run_blocking` runs
the tick's three calls under one `asyncio.run`. One loop creation per minute is not
worth a background thread and a client lifecycle to avoid.

## Testing

Against `tests/harness/fake_kraken.py`. Its snapshots are C's own dataclasses with the
same field names as `clients/kraken/contracts.py`'s models, so the engine coerces
whatever it is given into this system's validated models — which means fixture data
goes through the same validators as exchange data, and the engine behaves identically
either way.
