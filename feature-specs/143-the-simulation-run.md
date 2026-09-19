# 143 — The chain simulation

**Owner:** Lead (runs it, commits the digest, substitutes the findings)

**Phase:** 7. After 142 is green. **Unattended**, in a session of its own.

## Goal

The ruled window, replayed through the full chain at each ruled fee tier, one process and one
database per tier. It produces:

- the funnel;
- the trades, with their approval economics;
- the equity curve including cash periods;
- spec 138's report.

The figures replace every SIMULATED VALUE PENDING in `docs/dataset/phase-7-findings.md`.

## Implementation

1. **The shape. RULING REQUIRED (R4)** for the window only; the tiers are ruled. The lead's
   proposal: six months (folds 379 to 404), at tiers 3 and 5, running in parallel.
   - Estimated at 7 to 15 hours per tier from measured parts. Spec 142 replaces the estimate with a
     measurement before the run is launched.
   - Twelve months at one tier is the alternative, at 15 to 29 hours.
2. **The tiers, RULED 2026-09-19 (R3): 3 and 5.** Tier 3 is 0.22%/0.38%, reachable by a small
   account; tier 5 is 0.15%/0.30%, at $100,000 held. Both are from the committed fixture. Tier 1
   needs no run: it is provably zero (`phase-7-findings.md` §2).
3. Before launch, record in the build log:
   - the scenario digest and the ranking in force;
   - the skeptic variant and the fold run ids;
   - the free memory and disk.

   The recorder keeps running throughout, and the run must not starve it.
4. After the run:
   - produce spec 138's report per tier;
   - commit a digest of each run (equity series, trades, funnel counts, scenario) under
     `tests/fixtures/` for spec 141's criterion;
   - substitute the findings' pending slots, each with its source.

## Scope Limits

- The run's figures are reported whatever they are. **A null or negative result is the result**
  (`project-overview.md`).
- No configuration is changed after launch to produce trades. A run stopped for a defect restarts
  from scratch with the defect recorded, never from a changed config mid-window.
- No figure from the run is written into the findings without its interval, or without the
  statement of why it has none.

## Check When Done

- Both runs complete, or the stop is recorded with its cause.
- The digests committed, and `backtest_emits_alpha_report` PASS against them.
- Every SIMULATED VALUE PENDING marker substituted or explained.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
