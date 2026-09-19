# 143 — The chain simulation

**Owner:** Lead (runs it, commits the digest, substitutes the findings)

**Phase:** 7. After 142 is green. **Unattended**, in a session of its own.

## Goal

The ruled window, replayed through the full chain at each ruled fee tier on the expected-move
ranking: two runs, one process and one database each. It produces, for each run:

- the funnel;
- the trades, with their approval economics;
- the equity curve including cash periods;
- spec 138's report.

The figures replace every SIMULATED VALUE PENDING in `docs/dataset/phase-7-findings.md`.

## Implementation

1. **The shape: THREE months**, folds 392 to 404, test weeks 2024-10-05 00:15Z to fold 404's test
   close, 2025-01-04 00:00 UTC. R4 first ruled six months (folds 379 to 404). The operator cut
   it to three on the evening of 2026-09-19, for the Sunday 13:00 report deadline (D23). **Only
   the window is shorter**: every engine and gate runs as live. The driver is passed
   `--begin 2024-10-05T00:15:00`. **Two runs: tier 3 and tier 5, both on engine 8's expected-move
   ranking** (`--ranking expected_move`). Each run has its own process and its own database.
   **No alphabetical run, now or later** (operator ruling 2026-09-19): alphabetical is the name
   of the limitation the ranking removed, not a rival ranking. Whether the model has skill is
   answered by the benchmark basket (R8) and the promotion gate (R10b). No Phase 7 criterion
   requires a baseline ranking. The lead's earlier four-run reading is withdrawn (`lead.md`).
   - The two tiers run in parallel on separate databases. **Folds never run in parallel within a
     run**, because account state crosses fold boundaries and a freeze in one week changes every
     week after it.
   - Sessions: build and rehearse first (spec 142), then launch unattended.
   - Estimated at 7 to 15 hours per run from measured parts. Spec 142 replaces the estimate with a
     measurement before launch. If the measured total means the two runs cannot finish in one
     unattended session, the lead brings the options to the operator before launch.
2. **The tiers, RULED 2026-09-19 (R3): 3 and 5.** Tier 3 is 0.22%/0.38%, reachable by a small
   account; tier 5 is 0.15%/0.30%, at $100,000 held. Both are from the committed fixture. Tier 1
   needs no run: it is provably zero (`phase-7-findings.md` §2).
3. Before launch, record in the build log, per run:
   - the scenario digest and the ranking in force;
   - the skeptic variant (capped, 13 folds) and the fold run ids;
   - the trial count from the committed ledger (spec 139), which is fixed before launch;
   - the free memory and disk.

   The recorder, the recording manager and the funding poller keep running throughout, and the runs
   must not starve them.
4. After the runs:
   - produce spec 138's report per run, against both benchmarks;
   - apply spec 139's promotion gate to the expected-move runs, and report the verdict against the
     bar fixed in advance;
   - commit a digest of each run (equity series, trades, funnel counts, scenario) under
     `tests/fixtures/` for spec 141's criterion;
   - substitute the findings' pending slots, each with its source.
5. **Report to the operator and stop.** The operator rules on the phase close after seeing the
   output, as in Phase 6. The lead does not close the phase and does not mark it green.

## Scope Limits

- The run's figures are reported whatever they are. **A null or negative result is the result**
  (`project-overview.md`).
- No configuration is changed after launch to produce trades. A run stopped for a defect restarts
  from scratch with the defect recorded, never from a changed config mid-window.
- No figure from the run is written into the findings without its interval, or without the
  statement of why it has none.

## Check When Done

- Both runs complete, or each stop is recorded with its cause.
- The digests committed, and `backtest_emits_alpha_report` PASS against them.
- Every SIMULATED VALUE PENDING marker substituted or explained.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
