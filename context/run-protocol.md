# Run Protocol

This file defines exactly what happens when the operator types a command. The operator does no manual setup, no manual assignment, and no manual checking. Everything below is the team's job.

## The command

> **"Start phase N and update the progress tracker and script"**

`N` is a phase number from `ai-workflow-rules.md`. "Progress tracker" means `context/progress-tracker.md`. "Script" means the build log — see `context/script-rules.md`.

Variants the operator may use, all meaning the same thing: "start phase N", "begin phase N", "continue phase N".

## Team shape

One team lead plus three teammates, sharing one task list.

| Agent | Role |
|---|---|
| **Lead** | Owns `src/acsoe/core/` and `bootstrap.py`. Plans, assigns, reviews, merges, verifies, reports. |
| **A — Platform** | Packaging, config, logging, clock, CLI, scripts, data ingestion engines |
| **B — Store & trading logic** | Database, store client, and the deterministic trading engines |
| **C — Interface & models** | Console, test harness, models, evaluation |

Full path list in `context/ownership.md`.

## Sequence

### 1. Lead: preflight

- Read `context/progress-tracker.md`.
- If phase `N-1` is not marked green, **refuse and say why.** Do not start a phase on an unfinished foundation.
- If `N` is already green, report that and ask whether the operator wants a re-verify.
- Run `python scripts/verify.py --phase N-1` to confirm the tracker is telling the truth. Trust the command, not the note.
- **Phase 0 has no preflight.** There is no phase −1. Skip this whole step and go to planning.

### 2. Lead: plan

- Read every spec in `feature-specs/` belonging to phase `N`. **If none exist, write them first** from the phase `N` row of `ai-workflow-rules.md` and the ownership map, then get the operator's approval before assigning anything.
- Break them into tasks small enough that one teammate can finish and verify each independently.
- Write each task onto the shared task list with: spec number, owning agent (from the ownership map), the files it will touch, and its acceptance check.
- Post the plan in one message before any teammate starts, **grouped by owning agent with a task count each**. If an agent has no meaningful work this phase, say so — never invent filler tasks to keep three teammates busy. Running two teammates in a lopsided phase is correct.

### 3. Teammates: claim and build

- Claim a task from the shared list. Never start a task another agent has claimed.
- Write your claim into `context/progress/<agent>.md` before writing code.
- Build against the spec. Do not exceed its **Scope Limits**.
- If you need something another agent is still building, agree the contract in `contracts.py`, mock it, and continue against the mock. Do not idle and do not build it yourself.
- Communicate directly with the teammate who owns an interface you depend on. Do not route everything through the lead.

### 4. Teammates: self-test before handing back

A task is not done until you have personally run and passed:

```
pytest tests/ -q
mypy --strict src/
ruff check src/
python scripts/verify.py --phase N
```

For a single task, the bar is **no FAIL**. PENDING criteria are expected until the phase is finished. If anything FAILs, fix it. Do not hand back failing work and do not report a task complete on the task list until these are green.

For any gate engine, you must also have written one test proving it blocks and one proving it passes. A gate with only a happy-path test is incomplete.

### 5. Teammates: write your two files

Before marking a task complete:

- `context/progress/<agent>.md` — what you built, what is in progress, what blocked you, any open questions.
- `docs/build-log/phase-N/<agent>.md` — append your entries per `context/script-rules.md`. Every non-trivial bug and its fix goes here. This is dissertation material and it cannot be reconstructed later.

### 6. Lead: review

- Read each teammate's changes against `trading-invariants.md` and `engine-contracts.md`.
- Reject anything that weakens a gate, hardcodes an exchange value, reads the clock directly, or writes outside its owner's paths.
- Confirm every engine directory has its three files including a written `README.md`.
- Confirm no secret appears anywhere in the diff.

### 7. Lead: verify the whole phase

Run, and paste the real output:

```
python scripts/verify.py --phase N
```

At phase close the bar is every criterion PASS and zero PENDING. Mid-phase the bar is only no FAIL — PENDING is expected while work is outstanding, and is not a failure. Send FAILs back to their owning teammate; do not patch another agent's code yourself.

### 8. Lead: merge and report

- Merge teammate progress files into `context/progress-tracker.md`. Mark phase `N` green only after step 7 passed.
- Consolidate the build log entries into a readable phase section.
- Report to the operator with, in this order:
  1. What was built, in plain language
  2. The verbatim output of `scripts/verify.py --phase N`
  3. Every problem hit and how it was fixed
  4. Anything deliberately left out and why
  5. The exact commands the operator can run to check it independently
  6. What phase `N+1` will do

### 9. Operator verification

The operator will re-test. Expect to be asked to prove specific behaviour. If a defect is found, fix it inside phase `N` — do not defer it to a later phase and do not mark the phase green until it is fixed.

## Things that stop work immediately

Stop, write it in your progress file, and escalate:

- A change would touch `src/acsoe/core/` or `bootstrap.py` and you are not the lead
- A change would alter an invariant, the engine contract, or the engine registry
- A spec is ambiguous about trading behaviour
- A dependency is needed that is not listed in `architecture-context.md`
- Another agent's work is required and no contract exists to mock

## Rules that are never negotiable

- Never mark a phase green without a passing verify run.
- Never start phase `N+1` because phase `N` is "nearly done".
- Never patch another agent's files to unblock yourself.
- Never skip the build log because the session was short.
