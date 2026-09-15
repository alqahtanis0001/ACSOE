# 80 — Phase 6 rulings into the documents

**Owner:** Lead

**Phase:** 6. `context/*` except `progress/`, `feature-specs/`, `config/` are the lead's.

## Goal

Every operator ruling of 2026-09-16 that opened Phase 6, and every ruling taken during it, is
written into the file with authority over it before any teammate builds against it — so no
agent follows a stale copy in good faith.

## Implementation

1. `context/progress-tracker.md`, Known Risks or Findings, one entry stated plainly: **tier 1 is
   a no-trade regime at the current barriers** (`hurdle_multiple` 1.5 needs an expected move above
   3.125% against a 3.0% target). It is the project's central economic finding, not a defect,
   and the Phase 6 criteria therefore prove the machinery, not the economics — every criterion
   that drives a trade does so against the fake client at **tier 3** and says so in its message.
   `hurdle_multiple` and the cost gate are unchanged.
2. Same file: **engine 14 weights a single real model today.** The walk-forward trained one
   predictor per fold, not competing models, so the router is inert in practice, the same shape
   as `max_concurrent_positions: 3` being inert at a $5,000 balance. A criterion asserting that
   the weights move is asserting a property of the committed leaderboard fixture.
3. `context/ownership.md`, before anyone builds it: a roster entry for **the fill simulator** —
   B's, at `src/acsoe/clients/paper/`, per the operator's ruling of 2026-09-16 — in the same shape
   as the `research/backtest.py` paragraph under "Paths nobody was assigned". B also owns
   `tests/clients/paper/`.
3a. **The four rulings of 2026-09-16, recorded in the tracker with their reasoning:**
   - **The simulator's home, corrected by the operator.** The earlier ruling put it under
     `engines/execution/`; contract rule 3 forbids engines 21 and 22 importing it, and a resting
     entry fills on a tick only engine 21 sees. **Recorded as the operator's own correction**, made
     on a reconnaissance report that named the ownership gap and did not follow an order far enough
     to find the import one.
   - **The paper ledger**, as a defect found in planning: invariant 2 promised a balance "adjusted
     by simulated fills" that nothing implemented, so engine 11 sized against cash an earlier paper
     fill had already spent and engine 19's equity counted that cash twice. **`trading-invariants.md`
     rule 2's table is reworded**: in paper mode the balance is always `paper.starting_balances`
     adjusted by every recorded fill, whether or not the real fetch works.
   - **The offset bandit, deferred to Phase 7**, with the reason: it is a Locked Decision absent
     from the Phase 6 row, and it needs a table and a fill history that do not exist yet. Phase 6
     places every entry at the best bid.
   - **The skeptic cap**, spec 83, including Finding 1's caveat.
3b. **Engine 16 becomes a gate** (operator, 2026-09-16), and the edits land **before** B builds it:
   the Gate column of the registry table in `engine-contracts.md` gains a Y for 16; invariant 3's
   gate list and invariant 4's protected list in `trading-invariants.md` both gain 16, which is
   deterministic arithmetic and therefore protected from every model output; the glossary and
   `project-overview.md` are checked for any sentence that counts the gates. Its job is the
   tick-coherence check and it composes the order intent — the documents say *composes*, never
   *decides*, about the assembly.
4. `context/ownership.md` seam rows: the order surface (A → B), the per-tick trade range (A → B),
   the placed and closed rows 18 and 22 publish for engine 19 (B → C), the book fixture (C, cut
   by A's script), the leaderboard fixture (C → C), the adaptive router's weights (C → console).
   **The reason-code row is widened** from "gates 7, 10, 11, 13, 15, and any future gate" to every
   engine that publishes a `reason_code` or a `hold_reason`, because 9, 14, 18, 21 and 22 all do
   and none of them is a gate.
5. `context/engine-contracts.md`, cross-chain keys: the rows each Phase 6 engine's spec fixes
   (engine 14's outputs, `state["execution"]["orders"]`, `state["position_manager"]["triggered"]`,
   `state["exit"]["orders"]` / `["positions"]` / `["closed_trades"]`,
   `state["market_sensor"]["trade_ranges"]`). Added when the owning spec lands its `contracts.py`,
   not before, so the table never names a field that does not exist.
6. `config/default.yaml`: every key a Phase 6 spec requests (at minimum `order_book.depth`), field
   first on A's model and YAML second, in one change per the landing rule.
7. The rulings the operator makes on this phase's open questions (the simulator's home, engine
   16, the paper ledger, the offset bandit, the skeptic cap) go into their authority files the same
   day: `trading-invariants.md` for the paper ledger, `engine-contracts.md` and
   `architecture-context.md` for engine 16 and the simulator, the tracker for the skeptic cap.
   Run the four-step manual procedure in `ai-workflow-rules.md` for each, greping `AGENTS.md` and
   `README.md` as well as `context/`.

## Scope Limits

- Do **not** change `hurdle_multiple`, the barriers, or anything in engine 10.
- Do **not** add a cross-chain key row for a field that has not landed.
- Do **not** record an operator ruling that has not been made. An open question stays open.
- Do **not** consolidate build logs or close the phase.

## Check When Done

- `docs_vocabulary` PASS on every phase.
- Every seam in step 4 has a row, and every row names a producer whose phase is not later than
  its consumer's.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
