# Phase 8 — team brief

Same shape as Phase 7's brief. **Read before doing anything:** `AGENTS.md`, then the context
files in the order it lists, then `feature-specs/PHASE-8-TASKS.md`, then
`docs/dataset/phase-8-findings.md` (the costing), then this file.

## The phase in one line

A live UI and a real activation button, on a system whose live path has four known defects, with
`live_guard`, `close_all` and a soak as the workflow row's criteria. **The account is tier 1 and
tier 1 approves nothing: the screen must show the system working and refusing, not a blank page.**

## Lanes (unchanged, permanent — `context/ownership.md`)

| Agent | Phase 8 work |
|---|---|
| **Lead** | `core/`, `config/`, `context/*`, the specs, every gate, every commit and push, `close_all`'s command reader half |
| **A — Platform** | `clients/kraken/` (the live client: `recent_trades`, `AssetPairs` naming, `TradeVolume`, the order surface), `platform/live_guard.py`, console access control, the soak |
| **B — Store and trading** | `engines/scout` (pair status), `engines/exit` and `position_manager` for `close_all`, any schema change |
| **C — Interface and models** | `console/` — the main window, the decision stream, the funnel, the activation control's screen half, `scripts/verify.py` criteria |

## Rules that bite in this phase

1. **Nothing enables live trading.** Invariant 1's three switches are proven, never relaxed. No
   code path may promote paper to live implicitly, and no default may change to make live easier.
2. **The recorder, the supervisor, `funding.py` and `fees.py` are never stopped or reconfigured.**
   A dead one is restarted; a live one is left alone.
3. **Never commit a secret.** The live path now handles real keys: they come from `.env`, and
   they are never logged, printed, echoed in an error, or written into a fixture. Phase 8's
   workflow row requires that no secret appears in any log, artefact or committed file.
4. **A gate whose refusal is invisible on screen is not finished.** The operator's acceptance is
   that tier 1 shows refusals with their numbers.
5. **Mutation proof writes its byte copy to disk before mutating** (Phase 7's harness kept it in
   memory; a hard kill would have lost the original).
6. **Scratch files go in your own folder**, never the scratchpad root and never another agent's.
7. **Anything over about an hour that the operator has not approved is a stop and a report.**

## What Phase 7 leaves you

- Both runs finished, 8,736 bar ticks each, no crashes, no resumes. Results and figures:
  `docs/dataset/phase-7-findings.md` Parts II and III. **Do not re-run or change any of it.**
- Five carried-forward defects, listed at the end of the task list. None is scheduled.
- A working detached-launch pattern (WMI), a boundary gate script, and a launch-precondition
  check, all committed under `docs/build-log/phase-7/`.
