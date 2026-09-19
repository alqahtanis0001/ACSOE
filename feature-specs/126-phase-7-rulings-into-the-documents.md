# 126 — Phase 7's rulings into the authority documents

**Owner:** Lead

**Phase:** 7. First, before any teammate builds against a replay input.

## Goal

Every Phase 7 ruling is written into the file that has authority over it, and every other mention
points there. That covers the replay inputs the archive cannot supply, the fee scenario, the
ranking and the skeptic cap. A teammate building the playback client or the artefact assembly
reads a rule, not a conversation.

## Implementation

1. **Invariant 2, `context/trading-invariants.md`.** Operator ruling 2026-09-19: **a declared fee
   scenario is permitted in replay mode only**. It is read from a committed scenario fixture that
   carries its source URL and capture date, and **a test, not convention**, proves that nothing
   outside replay mode can read it. Live and paper are unchanged: fees come from `TradeVolume`,
   and a failed fetch blocks. State that the scenario is a *declared input to an offline
   experiment*, never a fallback. Every trade and rejection it prices records the scenario's
   identity (spec 134).
2. **The same invariant, spread and book.** Invariant 2 says an assumed spread invalidates the cost
   gate. In replay mode the spread and depth are **declared, not assumed silently**. They come
   from the bucket table of spec 130, served as a synthetic book by the replay client (spec 129),
   with the same identity recorded. Ruled 2026-09-19: the operator delegated the form of the spread
   to the lead's recommendation, and the recommendation is the liquidity-bucket table. The evidence
   is `docs/dataset/phase-7-findings.md` §3. Add the rule beside the paper-mode table, not inside
   it.
3. **`context/architecture-context.md`, "The consequence"** (under Data sources). The paragraph
   already requires "an explicitly documented proxy". Name the two proxies: the declared book and
   the declared fee scenario. Name where each is documented, and state that they live **in the
   client layer only**, so no engine branches on mode.
4. **The ranking. RULED 2026-09-19 (R1): engine 8's expected move, batched.** Write invariant 4's
   amendment in the operator's words: *a model's output may order candidates for examination,
   provided every gate judges the chosen candidate independently and no gate's verdict is
   influenced by the ranking. The prohibition on a model overriding or softening a gate is
   untouched.* The rationale and its residual are in `docs/dataset/phase-7-findings.md` §R.2.
   Point there; do not restate them.
   - **R12, for the operator before this lands.** Invariant 4 also says *"A model may only ever
     make the system less willing to trade, never more."* The ranking measurably makes the system
     more willing: 3 trades become 46 at tier 3. The amendment must carve that sentence out in words
     the operator approves. Otherwise the invariant contradicts itself. **The lead does not write
     that wording.**
   - Invariant 4's paragraph on engine 7 ("its candidate ranking is a deterministic score over
     features. It contains no model") changes with it.
   - `project-overview.md` counts the engines with no machine learning, and `scout` is one of them.
     **Do not change the count to the next number down.** `docs_vocabulary` retires that word
     beside "engines". Say instead that engine 7's filter contains no model and its ordering reads
     the predictor's output.
   - Config: `scout.rank_feature: expected_move` (spec 144 defines the name), with the ruling's
     date.
5. **The skeptic cap. RULING REQUIRED (R2).** The cap itself was ruled 2026-09-16 (13 folds, spec
   83). What is open is whether the simulation runs the capped skeptic (the lead's recommendation;
   `phase-7-findings.md` §5a shows a fourfold difference in pass rate in this window) or the
   uncapped one as trained. Record the answer in the tracker's prerequisite 1.
6. **Config.** A `replay:` section naming:
   - the scenario fixtures: spec 130's table, and
     `tests/fixtures/replay/kraken_fee_schedule_2026-09-19.json`, fetched and committed by the lead
     on 2026-09-19;
   - the fee tier, **3 or 5, one per run** (R3, ruled 2026-09-19);
   - `training.skeptic_cap_folds: 13` if R2 is capped.

   A may request keys; only the lead adds them.
7. **Grep for the contradicted claim** (the retired-vocabulary procedure, steps 2 to 4). Search
   `AGENTS.md`, `README.md` and `context/` for "no fallback", "never a constant", "assumed spread"
   and "invalid". Each hit either stays true because the scenario is not a fallback, or points at
   the new rule.
8. **Seams in `context/ownership.md`:**
   - the scenario fixtures (A produces the table, the lead commits the fee schedule; A's replay
     client consumes them);
   - the approval economics on `trades` (B migrates, C writes);
   - the replay scenario on the `runs` row (lead writes, B migrates).

## Scope Limits

- **No code.** No engine, client or test changes here.
- Invariant 2's live and paper rules do not move by a word. The amendment adds a replay-only
  rule; it relaxes nothing that exists.
- Do not write any Kraken fee figure into a context file. The schedule is a fixture, and
  invariant 5's reference figures stay reference figures.
- Do not settle R2 or R12 by default. Each is written only once the operator has answered.

## Check When Done

- `docs_vocabulary` PASS, and the grep in step 7 is recorded in `docs/build-log/phase-7/lead.md`
  with each hit's disposition.
- Every seam in step 8 has a row naming a producer that exists no later than its consumer.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` ·
  `python scripts/verify.py --phase 7`
