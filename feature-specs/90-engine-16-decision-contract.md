# 90 — Engine 16 `decision`: the tick-coherence gate, and the order intent

**Owner:** B — Store and trading

**Phase:** 6. `engines/decision/` is B's.

> **RULED BY THE OPERATOR 2026-09-16.** Engine 16 stays in the chain and **becomes a gate**.
> `is_gate = True`, the Gate column of the registry table gains a Y, invariant 3's gate list gains
> 16, and invariant 4's protected list gains it too — it is deterministic arithmetic with no model
> in it, so no model output may override it (the lead makes those edits, spec 80, before this is
> built). It is not a passthrough and it is not removed.

## Goal

Engine 16 performs the consistency check nothing in the system currently performs: **every
approving engine judged *this* tick's candidate.** If engine 7 picked pair X and engine 10
approved pair Y, or a `state` key survived from a previous bar, engine 16 blocks. It then
assembles the order intent, so engine 18 depends on one typed contract rather than reaching into
five engines' keys.

## The contract

- `name = "decision"`, `number = 16`, `is_gate = True`. Opportunity chain, after 15, before 18.
- **Reads** `state["cycle_id"]`, `state["market_sensor"]["closed_bar_ts"]`, `state["scout"]`,
  `state["prediction"]`, `state["order_book"]`, `state["cost"]`, `state["risk"]`,
  `state["adaptive_router"]`, `state["skeptic"]`.
- **Writes** `state["decision"]`: the order intent plus the check's own verdict.
- **The composition is composition, not decision, and the README says so plainly.** Engine 16
  decides exactly one thing — whether the inputs are coherent — and copies the rest. Nothing in
  it chooses a price, a size, a barrier or a model; each of those stays with the engine whose
  decision it is. The README must not call the assembly a decision.

## Implementation

1. `engines/decision/engine.py`, `contracts.py`, `README.md`.
2. **The check, each clause its own reason code**, and each blocking:
   - every payload that names a pair names the **same** pair as `state["scout"]["pair"]`
     (`pair_disagreement`, naming both engines and both pairs);
   - every payload that names a bar names this tick's `closed_bar_ts` (`stale_bar`, naming the
     engine, the bar it carried and this tick's);
   - an approving engine's payload is **absent** when the chain says it ran (`input_missing`);
   - `state["risk"]` approved but published no `qty` (`no_approved_quantity`) — engine 11 omits
     the field on a rejection, so this is the shape that says an approval and a refusal disagree.
   A clause that cannot be evaluated blocks: invariant 3, the absence of a "no" is never a "yes".
3. **The order intent**, published only when every clause passes: `pair`, `qty`, `closed_bar_ts`,
   `cycle_id`, and the provenance each source published — `net_edge_pct`, `hurdle_pct`,
   `expected_move_pct`, `estimated_slippage_pct`, `p_wrong`, `model_run_id`, the router's
   `active_model_run_id`. Money as exact decimal strings. **Absent in its entirety on a block**,
   the same shape engine 11 uses for `qty`, so there is no half-intent for engine 18 to read.
4. Reason codes to C by message (spec 99).
5. Tests in `tests/engines/test_decision.py`: a block test and a pass test per clause differing in
   one input; every `state` from the real upstream engines, never hand-built (Phase 3 ruling); the
   intent absent on every block; a pass whose intent is recomputed from the sources rather than
   read back from engine 16.

## Scope Limits

- Do **not** re-derive, recompute, adjust or re-check any number engine 16 copies. Disagreement is
  a block, never a correction.
- Do **not** size, price, weight or scale anything. A quantity lowered here would be a veto
  wearing a sizing costume.
- Do **not** block on a *model's* judgement — the skeptic has already vetoed or not. Engine 16's
  criteria are coherence only.
- Do **not** mint a `userref`; that is engine 18's, deterministic from the pair and the bar.
- Do **not** build before the lead's registry and invariant edits land (spec 80).

## Check When Done

- `is_gate_matches_registry` PASS with 16 counted as a gate; `anomaly_and_skeptic_have_both_tests`
  unaffected; engine 16 has a block test and a pass test per clause.
- Mutations observed red, killing test named: the pair comparison dropped; the bar comparison
  dropped; an absent input read as agreement; the intent published on a block.
- `pytest tests/ -q` · `mypy --strict src/ scripts/` · `ruff check src/ tests/ scripts/` · `python scripts/verify.py --phase 6`
