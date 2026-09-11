# 48 — The Phase 4 exit criteria in `scripts/verify.py`

**Owner:** C — Interface and models

**Phase:** 4 — Memory and replay. **This spec lands first**, before any subject it judges,
for the reason spec 00 was first in Phase 0, spec 16 in Phase 1 and spec 45 in Phase 3:
until these exist `--phase 4` registers `docs_vocabulary` and `toolchain_green` alone and
prints "Phase 4 is green" over an empty phase.

## Goal

`python scripts/verify.py --phase 4` becomes the executable form of the Phase 4 row of
`ai-workflow-rules.md`.

## Why this phase's criteria carry a heavier burden than any before it

Phase 4 is the phase where a mistake looks like success. A purging bug or a short embargo
produces a model that appears excellent and is worthless, and **nothing fails to say so**.
A missed block record makes the circuit breaker inert while every test stays green. There is
no crash, no red test and no operator-visible symptom for either. The criteria below are the
only thing standing between those defects and Phase 5, so each one is held to the stricter
proof in "Rules this spec is held to".

## Implementation

Register these for phase 4. Each is one named check printing PASS, FAIL or PENDING; each runs
offline with no network and no API key; each passes on a fresh clone.

1. `memory_records_every_blocker` — engine 19 writes one `block_records` row per entry in
   `state["guard_blockers"]`, on **every** blocked tick. Assert three cases in one criterion,
   because each hides a different bug:
   - a tick where `data_guard` blocked and **no candidate ever existed** still writes a row.
     An implementer reading invariant 12 as "rejections are logged" writes rows only where a
     candidate was rejected, and the outage counter is then built from a table that is empty
     on exactly the ticks it counts;
   - a tick where **two guards blocked at once** writes **two** rows, `is_primary` on the
     first only. One row per tick passes a naive count and destroys invariant 12;
   - an unblocked tick writes **no** row. A row on every tick makes every count meaningless.
2. `memory_writes_safety_inputs_live` — drive real ticks, then assert `safety` reading the
   **live** rows reaches the same six totals it reaches against the Phase 0 seed: drawdown,
   losing-trade streak, error blocks, outage ticks, open positions, resting orders. This is
   the criterion that closes the forward dependency Phase 3 was forced to seed around. Assert
   the six numbers, not that the tables are non-empty.
3. `rejections_survive_restart` — a rejection written under one `run_id` is still readable
   after the store is closed and reopened under a **different** `run_id`, with its
   `reason_code`, `reason` and economics intact. Assert the values, not the row count: a
   restart test that only counts rows passes against a writer that loses every column.
4. `labelled_sample_replayed_from_archive` — `tests/fixtures/labelled_sample.parquet` exists,
   parses, and is a **labelled slice produced by replaying an archive through the real
   loader**. Assert its schema, that every label is one of `target`, `stop`, `timeout`, that
   all three outcomes occur, that no labelled decision bar is within `barriers.timeout_bars`
   of the end of its pair's series, and that its provenance field names the archive it came
   from. **Ask of this one: would it still pass if the parquet had been written by hand?**
   That is why the provenance and the horizon assertions are here.
5. `labeller_matches_hand_verified_labels` — the labeller reproduces **every** row of the
   committed hand-verified fixture (spec 52), exactly, including the barrier that was touched
   and the bar index at which it was touched. One mismatch is a FAIL, not a tolerance.
6. `walkforward_folds_purged_and_embargoed` — **construct** a fold whose training set
   contains a decision bar whose label window straddles the train/test boundary and assert
   that row is **absent** from the returned training index; then assert the same for a row
   inside the embargo span after the test set. An end-to-end "the folds do not overlap" check
   cannot see the difference between a correct embargo and none at all, because the fold
   *indices* do not overlap in either case — the leak is in the **label windows**, which are
   invisible unless the criterion builds one that straddles on purpose. Assert the row's
   absence by identity, not by counting.
7. `console_history_reads_real_rows` — the history screen renders trades and rejections
   written by a live engine 19 rather than by the seed. Assert a value that came from the
   live rows appears in the rendered output.

And one live-only criterion, `live: True`, never required for green:

8. `replay_full_archive` — replays the full six-month archive from `data/historical/` and
   reports span, bar count and gap statistics. Reports PENDING, not FAIL, when no archive is
   present: the operator has not downloaded one, and an opt-in criterion that FAILs on its
   absence makes `--live` useless for every other check.

## Rules this spec is held to

- **Fabricate the subject a criterion judges. Never fabricate a contract it is held to.**
  Import the real `core/contracts.py`, `clients/store/contracts.py`, and the real engine and
  research `contracts.py` modules.
- **Prove each criterion three ways and record the proof in the build log.** PENDING against
  a tree where the subject does not exist; PASS against the real subject; and **FAIL against
  a deliberately broken subject** — break the thing it tests, watch it go red, record that it
  went red, then put it back. Phase 3 found three tests that could not fail, all by mutation,
  none by review, all written by careful agents who believed otherwise. **A claim that an
  assertion works is not evidence.** Name, in the build log, the exact mutation used for each
  criterion and the exact message it printed when red.
- For criterion 6 the mutation is named for you, because it is the one that matters:
  **set the embargo to zero and the purge to a no-op, separately, and confirm the criterion
  goes red for each.** If either mutation leaves it green, the criterion is judging fold
  indices rather than label windows and must be rewritten.
- **A gate satisfied by the shape of the evidence rather than by its content will accept
  fabricated evidence of the right shape.**

## Scope Limits

- Do **not** write, patch or "fix" any engine or research module. A FAIL goes back to its
  owning agent.
- Do **not** register a criterion needing the network, an API key, or anything under `data/`,
  `models/` or `logs/` — except criterion 8, which is `--live` only and reports PENDING when
  the archive is absent.
- Do **not** widen `TOOLCHAIN` beyond `src/`. Still deferred, still the operator's.
- Do **not** change any Phase 0, 1, 2 or 3 criterion.
- Do **not** consolidate build logs and do **not** mark the phase green. The lead closes a
  phase; this spec only makes closing possible.

## Check When Done

- `python scripts/verify.py --phase 4` reports all seven non-live criteria, PENDING where the
  subject is absent, and no FAIL that is not a real defect.
- Every criterion has been observed PENDING, observed PASS and **observed FAIL**, each
  induced failure and its message recorded in `docs/build-log/phase-4/c-interface.md`.
- Phases 0 to 3 still report exactly what they reported before this spec.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 4`
