# 141 — The Phase 7 criteria in `verify.py`

**Owner:** C — Interface and models (`scripts/verify.py`, `tests/verify/`)

**Phase:** 7. Written first, as PENDING. Every criterion runs offline on a fresh clone.

## Goal

Criteria that judge the Phase 7 row as written, plus the rules this phase introduces. Each is
proven capable of FAIL.

## Implementation

1. **`backtest_emits_alpha_report`.** The row asks for a three-month paper backtest emitting an
   alpha-versus-benchmark report from the full equity curve including cash periods.
   - `data/` is gitignored, so this criterion judges a committed digest of the real run's report
     (spec 143), checked for internal consistency: equity rows cover every tick, including flat
     ones, and the report's figures recompute from the digest's series.
   - It also runs a committed one-day fixture through the whole pipeline.
   - `--live` checks the real run's database.
   - **The message states the window, tiers and scenario digest the digest came from.**
2. **`promotion_gate_rejects_haircut_edge`:** spec 139's fabricated pair, judged through the real
   engine 20.
3. **`research_screens_render`:** the leaderboard and SHAP view render from a seeded database.
4. **`fee_scenario_is_replay_only`:** the replay client refuses construction in paper and live, and
   no module outside `clients/kraken/`'s replay client imports the scenario fixtures (an AST walk).
   This is invariant 2's amendment, enforced by test as ruled. The fixture is
   `tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`.
5. **Prerequisite 9 closed:** `candles_match_independent_reduction_of_recorded_trades` reads its
   `tick_size` from spec 127's recorded `AssetPairs` instead of the invented file, and its message
   says so.

## Scope Limits

- Fabricate the subject, never the contract (`ai-workflow-rules.md`). The real engine 20, the real
  store and the real replay client, not doubles.
- No criterion depends on anything under `data/`, `models/` or `logs/`.

## Check When Done

- Each criterion observed PENDING before its subject exists, PASS on it, and FAIL on a planted
  defect, with the defect named in the build log.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
