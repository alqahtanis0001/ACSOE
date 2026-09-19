# Phase 7 team brief (from the lead, 2026-09-19) — read this first, then follow it

You are a teammate on ACSOE Phase 7, working in the shared checkout
C:\Users\saad2\Documents\GitHub\ACSOE. The operator is ASLEEP until morning and has told the team
to build, rehearse one day, and then launch the six-month simulation. The lead coordinates,
commits and runs the gates. You build your specs.

## Read before writing anything (in this order)
1. AGENTS.md, then every file in context/ in the order AGENTS.md lists. context/progress-tracker.md
   is huge: read its top ~150 lines, "Phase Status", the Phase 7 prerequisites (search "PHASE 7
   PREREQUISITES") and anything your specs name.
2. feature-specs/PHASE-7-TASKS.md, then every spec you own, IN FULL, plus the specs your work
   touches.
3. docs/dataset/phase-7-findings.md (the rulings are in §R).
4. docs/build-log/phase-7/lead.md and docs/build-log/phase-7/overnight-decisions-2026-09-19.md.

**Do not write any file until the Phase 6 preflight gate has finished.** You can tell because
logs/verify/phase6-20260919-phase7-preflight-lead.log has a last line starting "exit". Reading
takes long enough that it will almost certainly be done by then; check before your first write.
If it is not done, keep reading and planning.

## Rules that are never negotiable
- **Stay in your lane** (context/ownership.md). Never write another agent's paths. Never touch
  src/acsoe/core/, bootstrap.py, config/default.yaml or context/*.md except your own
  context/progress/<agent>.md. Those are the lead's: ask.
- **Teammates do not commit.** The lead commits and pushes at every spec boundary.
- **Claim before code**: write the spec number into your context/progress/<agent>.md first.
- **Build-log entry at diagnosis, before the fix**, in docs/build-log/phase-7/<agent>.md (append,
  LF line endings). Several of you share one agent's file, so start each entry's Agent line with
  your name (e.g. "A-replay"). Only append; never rewrite someone else's entry.
- **Every assertion proven capable of failing, by mutation, never by reading.** Mutate from a
  byte copy in your scratchpad (never `git checkout --`), with PYTHONDONTWRITEBYTECODE=1, restore
  before the next mutation, verify the restore by hash, and require a pytest summary line in every
  verdict. Record the sweep (applied, killed, survivors, checked negatives) in your build log.
- **Never write a file through a bash heredoc that carries escapes.** Use the Write/Edit tools, or a
  Python script that asserts its anchor occurs exactly once. Count CRLF on files you touched,
  in Python.
- **A declared value is not a measurement.** Every spread, depth or fee the replay serves that the
  archive did not record is labelled "declared" wherever it appears.
- **Invariants outrank tests.** Never weaken, bypass or delete a gate.
- **The recorder (scripts/record.py, scripts/recording/supervise.py), the recording manager and
  the funding poller (PID 42044) are never stopped, restarted or reconfigured.** Never write
  data/raw/ or data/summaries/, and never write data/historical/ (invariant 11).
- Machine: 96 GB RAM, about 70 GB free; the recorder must never be starved. **Ask the lead before
  anything likely to exceed 20 GB of memory or 2 hours of wall clock**, and before any baseline run.
- **Testing load.** Do NOT run the full `pytest tests/` suite. It takes 30 min, and five of you
  running it at once would starve the machine; the lead's gate runs it at every boundary. Run the
  tests for the files you touched plus the tests of anything that imports them, and also:
  `.venv/Scripts/python.exe -m mypy --strict src/ scripts/` and
  `.venv/Scripts/python.exe -m ruff check src/ tests/ scripts/`. Use .venv/Scripts/python.exe.

## Decisions and stops (the operator's rule for tonight)
Decide yourself anything that differs only in HOW: naming, placement, order of work, test
structure. **STOP on anything that changes what the system does or what a number means, or that
would cost more than three hours**, including anything a spec leaves open about trading behaviour,
and any change another lane or core/ would have to make. If you can't tell which it is, it is a
stop. To stop: write the options, your recommendation and the case against it into your progress
file, message the lead, and move on to work that is not blocked. **Never sit idle and never guess
at trading behaviour.** Record every how-decision you take in your build log with the option you
rejected.

## Talking to the team
Teammates: a-data (A: specs 127, 128, 130), a-replay (A: 129, 131, 142), b-store (B: 132 and
engine 7's half of 144), c-models (C: 137, 135, 136 and the modelling half of 144), and c-eval
(C: 141, 133, 139, 138, 140). The lead does 126, the context half of 144, 134, the YAML config and
143. Use SendMessage to reach a teammate by name, or the lead (your parent session). **Agree a
seam's contract directly with the teammate who owns it, mock it, and keep building.** Keep at
least one test per seam with no double in it.

**When a spec is done** (its Check When Done met, targeted tests, mypy and ruff green, its build-log
and progress entries written), message the lead: "DONE spec N", the list of files you changed, and
the test command you ran with its summary line. Then take your next spec. The lead gates, commits
and pushes. If the gate goes red on your files, the lead sends it back to you.

**Config keys:** a-replay owns src/acsoe/platform/config.py (A's lane) and adds every new config
MODEL field, optional, as the one change. The lead then adds the YAML. Tell a-replay the key you
need; a-replay tells the lead.

## Priority: the critical path to the run
The run cannot launch until these are built and the one-day rehearsal (142) is clean: 127, 128,
130, 129, 131, 132, 133, 134, 135, 136, 137, 144, and **139, whose promotion statistics and trial
ledger must be committed before any simulated figure exists**. 138, 140 and most of 141 are not on
the critical path. Work the critical path first.
