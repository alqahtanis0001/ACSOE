# 51 — The store surface engine 19 and the cycle feed need

**Owner:** B — Store and trading logic

**Phase:** 4. `clients/store/` is B under the permanent ownership map.

## Goal

Two things, both small, both blocking somebody else.

1. The cycle feed stops scanning the whole of `block_records`. It has been a full-table read
   since Phase 1, which was harmless while the table held a seed. Engine 19 starts writing a
   row per guard per tick in this phase, which is when it stops being harmless. This was
   recorded in the tracker as a **before Phase 4** item.
2. Whatever read or write surface engine 19 needs and does not have. Engine 19 is C, the
   store is B, and C may not add a method to `clients/store/client.py`.

## Implementation

1. Add a most-recent-N read for `block_records` to `StoreClient`, ordered by `ts`
   descending — `ts`, never `cycle_id`, which restarts with the process. Bound it by an
   explicit limit the caller passes. Tell C and the console owner the method name as soon as
   it exists; do not wait until the task is finished.
2. Read spec 49 and spec 50 and confirm every write engine 19 needs already exists on
   `StoreClient`. Where one does not, add it in B lane, in the same shape as the existing
   writers. Message C directly with the signature.
3. Confirm `peak_equity` can be obtained from the store without reading the whole series —
   spec 50 requires the running maximum to come from storage rather than from `state`.
4. Tests in `tests/clients/store/`, B own lane.

## Rules this spec is held to

- **Every assertion must be proven capable of failing**, with the mutation and the red
  message recorded in `docs/build-log/phase-4/b-store.md`. For the most-recent-N read the
  mutation is named for you: **order by `cycle_id` instead of `ts`** and confirm the test goes
  red against a fixture spanning two `run_id`s. If it stays green the test is not testing the
  ordering, and ordering is the entire reason this method exists.
- A limit-bounded read whose test uses fewer rows than the limit cannot fail. Use more.

## Scope Limits

- Do **not** change the schema or add a migration. Every table Phase 4 needs exists.
- Do **not** write engine 19. It is C.
- Do **not** edit `console/`. Hand the method name to C and stop there.
- Do **not** change any `safety` read path. It is green against the seed and must stay
  byte-identical in behaviour, because spec 50 proves the live rows reach the same totals
  through exactly those methods.

## Check When Done

- The cycle feed no longer performs an unbounded scan of `block_records`.
- C has the signature of every method engine 19 needs.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
