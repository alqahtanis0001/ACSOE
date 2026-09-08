# 12 — `clients/store/`: the store client and its contracts

**Owner:** B — Store and trading

## Goal

One typed way in and out of SQLite and Parquet, satisfying the `store` half of the `Clients`
Protocol, so no engine touches the filesystem or a raw row.

## Implementation

1. Create `src/acsoe/clients/store/` with the client and `contracts.py` holding the pydantic
   models for every row type in the schema.
2. Implement the reads `safety` needs, each as a named method: latest equity snapshot with
   its peak; the trailing run of closed trades; `block_records` in a trailing window; the
   trailing consecutive `data_guard` tick count **ordered by `ts`, counting distinct
   `cycle_id`s**; counts of open positions and resting orders.
3. **The consecutive-block count is off by one in the obvious reading, and the correction is
   specified here rather than rederived.** `data_guard` (4) runs *before* `safety` (17) in the
   guard chain, so the current tick's block is already visible in
   `state["trading_blocked_by"]` when `safety` runs. `memory` (19) runs *later*, in the manage
   chain, so the store holds records only through tick T−1. The count `safety` acts on is
   therefore **stored consecutive `data_guard` ticks through T−1, plus one if the current tick
   is also blocked by `data_guard`**. The client returns the stored part; the caller adds the
   current tick. Name the method so that boundary is unmissable — it returns the stored count,
   not the effective one. Getting this wrong fires the breaker a minute early or a minute
   late, and neither is acceptable.
4. Implement the command-table reads and writes: claim pending, mark consumed, append a row,
   and list rows claimed but not consumed for startup replay.
5. Implement the writes engine 19 will need: trades, positions, orders, equity snapshots,
   block records, rejections. Engine 19 is their single writer; the client is what it writes
   through.
6. Money crosses this boundary as `Decimal` in Python and exact decimal strings in SQLite.
   Conversion happens here and nowhere else.
7. Add Parquet read/write for `data/derived/` using `pyarrow`, timestamps UTC as microseconds.
8. Add `tests/clients/store/test_store.py` covering each read against a migrated temporary
   database, with exact `Decimal` assertions on every money value. Use `hypothesis` for the
   consecutive-tick counter — the off-by-one at a restart boundary is exactly where this
   breaks.

## Scope Limits

- Do **not** put business logic here. The client returns rows; `safety` decides what they mean.
- Do **not** use `float` or `pytest.approx` for money.
- Do **not** let the counter order by `cycle_id`; it restarts with the process.
- Do **not** touch the network. This client is SQLite and Parquet only.

## Check When Done

- Every `safety` read returns correct values against a migrated temporary database.
- A hypothesis test proves the consecutive-tick count is right across a simulated restart.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 0`
