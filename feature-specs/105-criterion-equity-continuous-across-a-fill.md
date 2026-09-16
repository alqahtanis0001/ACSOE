# 105 — Criterion: equity is continuous across a paper fill

**Owner:** C — Interface and models

**Phase:** 6. Operator ruling 2026-09-16: "a criterion, not just a fix". The assertion that would
have caught spec 87's finding 1.

## Goal

A registered phase 6 criterion, `paper_equity_continuous_across_fill`, asserting that the
`equity_snapshots` row engine 19 writes on the tick an entry fills equals the row of the tick
before it, **within the fill's own cost** (the maker fee, plus the mark-to-bid difference on the
new position), driven through real orchestrator ticks at fee tier 3 against B's paper broker.

## Implementation

1. `scripts/verify.py`: the criterion, PENDING until its subject can run, and saying fee tier 3 in
   its PASS and FAIL messages. Compute the tolerance from the fill the store recorded — its
   quantity, price and fee — never a constant.
2. `tests/verify/`: PENDING, PASS and FAIL each observed. The FAIL is produced by **breaking the
   broker so the fill is excluded from the balance** — the pre-spec-103 behaviour — from a byte
   copy of `src/acsoe/clients/paper/broker.py`, hash compared in the same statement that restores
   it. That is a cross-lane mutation of B's file: run it only after spec 103 has landed, and never
   while B is working.
3. Build-log entry recording the FAIL message observed.

## Scope Limits

- Do not edit the broker, any engine, `core/` or `bootstrap.py` except transiently for the
  mutation, restored by hash.
- Do not widen the tolerance to make it pass; if the honest bound is unclear, stop and ask.

## Check When Done

- The criterion observed FAIL under the broken broker and PASS on the real one.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
