# Build log — Phase 4 — b-store

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is now diagnosis-before-fix.** Write **What happened** and **Why** the moment you know
why something is broken, *before* you write the fix; come back and add **Fix** afterwards. The
code survives on disk whatever happens to the session; the reasoning that found it does not.
Phase 3 opened with an interruption that took every build log and no progress file, because
progress files are written before the work and logs were being written after it.

Minimum headings per entry: What happened, Why, Fix.

Two habits Phase 3 turned into standards, both of which belong in entries here:

- **Break the code and watch the test go red**, then put it back, and say in the entry that you
  did. A test nobody has seen fail is a claim, not a check. A mutation that survives a *subset*
  of the suite has not survived — it has not been asked.
- **Record what you checked and found sound**, not only what you found broken. An audit that
  lists hits alone says nothing about coverage.

The lead consolidates these into `docs/build-log/phase-4.md` at phase close.

## Entries
