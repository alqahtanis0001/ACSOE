# 120 — Retire the operator prose that no longer has a producer

**Owner:** C — Interface and models

**Phase:** 6. Second half of the operator's 2026-09-16 ruling. **Runs after spec 119 (B), which has
landed**: the seeded rows now carry only codes the live system can emit, so the keys they used to
keep alive are free to retire.

## What B's spec 119 changed about this spec's premise

Three findings from B, all recorded in `docs/build-log/phase-6/b-store.md`. **Read them before
starting; two of them make parts of the original finding stale:**

1. **The tracker's list of bad pairs was one short** — `scout`/`outside_universe` was a sixth, and
   nothing complained because spec 99's walk goes engines → map and that code *is* in the map.
2. **Engine 7 `scout` has the same shape as engine 9**: none of its twelve real codes can reach
   `rejections` at all. It publishes `empty_universe` exactly when there is no candidate, and engine
   19 writes no rejection without a candidate pair; its exclusion codes are a per-pair tally over
   the universe, not a refusal of a candidate.
3. **`REASON_PROSE` never needed the codes to be real.** `operator_reason` prefers the sentence
   stored beside the code, so the feed rendered correctly for five phases whatever the code said.
   That is the mechanism that hid all of this — and it means retiring a key changes what the console
   shows **only** for a row that has no stored sentence.

**The retirement list is already computed, not guessed.** C's own
`test_the_inverse_is_reported_as_a_warning_and_never_as_a_failure` currently names exactly five
orphaned keys: `insufficient_depth`, `meta_label_veto`, `no_candidate_cleared`,
`outlier_market_state`, `outside_universe`.

## Goal

`REASON_PROSE` carries an entry for every code the system can emit and none that no producer can
reach, and a test keeps it that way **from the map's side** — the direction spec 99's walk cannot
see.

## Implementation

1. Build-log entry first.
2. Retire the orphaned keys. Confirm the list yourself from the code rather than taking the five
   above on trust — B's finding 1 is exactly what happens when a list in a document is believed.
3. **Turn the existing warning into an assertion**: the inverse walk currently reports orphans as a
   warning and never as a failure, which is why five keys sat there unnoticed. Make it a failure,
   and say in the docstring why both directions are needed — one catches a silent "No reason was
   recorded.", the other catches prose describing a refusal the system cannot make.
4. **Producers now include the seed**, not only the engines: after spec 119 the seed emits real
   codes, so the set of producers is the engines' `contracts.py` codes plus any `hold_reason`
   values plus what `clients/store/seed.py` writes. Derive it; do not hardcode a list.
5. Observe the new assertion red before retiring the entries.
6. **If a key has no producer but reads like something that should exist, that is a finding, not a
   deletion** — report it. B's finding 2 is one of these: engine 7's refusal codes are unreachable
   by construction, so anything in the map for them describes a refusal the system cannot make.
7. Consider whether `operator_reason`'s preference for the stored sentence deserves a test of its
   own, given that it is what hid five phases of drift. If you conclude it does not belong in this
   spec, say so — that is a legitimate answer.

## Scope Limits

- `src/acsoe/console/format.py`, `tests/console/**`, C's records. Do not edit the seed, any engine,
  or B's tests.
- Do not retire a key whose producer you have not checked in the code.

## Check When Done

- Both directions of the walk asserted, the new one observed red before the retirement.
- `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
