# Script Rules — the build log

When the operator says "update the progress tracker and script", **the script is this build log.**

Each agent writes `docs/build-log/phase-N/<agent>.md`. The lead consolidates them into `docs/build-log/phase-N.md` at phase close. Three agents appending to one file loses work the same way three agents writing one tracker would. It is written by the agents, as work happens, and it becomes the raw material for the dissertation's implementation chapter.

It cannot be reconstructed afterwards. A bug you fixed and did not record is a bug that never happened, and the reasoning behind it is gone.

## What belongs in it

**Every non-trivial problem and its resolution.** This is the point of the file. Specifically:

- Anything that failed and needed diagnosis, not just a typo fix
- Anything where the obvious approach was wrong and you changed course
- Anything the exchange did that the documentation did not describe
- Anything that only appeared under load, over time, or on real data
- Any decision where two approaches were viable and you picked one

## What does not belong

- Narration of routine work ("created the file, added the function")
- Restating the spec
- Anything already captured in a commit message
- Praise for your own work

## Entry format

Append entries in chronological order. Keep them tight — a paragraph each, not an essay.

```markdown
### Kraken returns errors with HTTP 200

**Agent:** A · **Task:** spec 02 · **Date:** 2026-09-14

**What happened.** The client treated any 2xx response as success. `AddOrder` calls
that Kraken rejected came back as 200 with an `error` array populated, so failures
were being recorded as fills.

**Why.** Kraken wraps everything in `{"error": [...], "result": {...}}` and does not
use HTTP status to signal application errors.

**Fix.** Every response now parses through `KrakenEnvelope` at the client boundary and
raises `KrakenAPIError` on a non-empty error list, before any engine sees it.

**Consequence.** Added to `code-standards.md` as a standing rule. Two existing tests
had been passing for the wrong reason and were rewritten.
```

Not every entry needs all five headings. `What happened`, `Why`, and `Fix` are the minimum.

## Decision entries

When you choose between viable approaches, record it in the same file with this shape:

```markdown
### Decision: Decimal for money, float for features

**Agent:** Lead · **Date:** 2026-09-12

**Options.** Use float throughout for speed and simplicity, or Decimal for anything
that reaches an order.

**Chose.** Decimal for prices, quantities, fees and balances. Float for indicators,
model inputs and statistics.

**Because.** Float drift in an order quantity produces a rejection from Kraken that is
miserable to diagnose, and the performance cost is irrelevant at one decision per
fifteen minutes.

**Cost.** Conversion at the model boundary, and a lint rule to catch float leaking
into sizing code.
```

## Phase closing summary

When the lead closes a phase, add a summary at the top of that phase's file:

```markdown
## Phase N summary

**Built.** One paragraph, plain language.
**Verify output.** Paste the real `scripts/verify.py --phase N` result.
**Problems of note.** Two or three sentences pointing at the entries below.
**Deliberately deferred.** What was left out and to which phase.
```

## Rules

1. **Write the entry when you have diagnosed the problem, before you write the fix.** Not
   after the fix, not at the end of the task, not at the end of the session. This is a rule
   and not advice, and it is the one rule here with a mechanism behind it: the diagnosis is
   the only part of a fix that exists solely in your head. The code survives on disk whatever
   happens to the session. The reasoning that found it does not.

   The moment you know *why* something is broken, stop and write **What happened** and
   **Why**. Then fix it, then come back and write **Fix**. An entry that stops after **Why**
   is worth keeping; a perfect fix with no entry is a bug that never happened.

   This is not hypothetical and it is not about crashes alone. Phase 1 lost work to three IDE
   crashes. Phase 3 wave 1 was interrupted with three agents mid-task and every build log an
   empty stub, while every progress file survived — because progress files are written before
   the work and logs were being written after it. The habit, not the crash, is the defect: the
   natural moment to write an entry *feels* like the end, and the end is the one moment that
   is not guaranteed to arrive. A context limit, a machine fault, a reassignment or simply
   finishing late all take the same thing.
2. Use plain language. Someone reading this in six months has forgotten the code.
3. Be specific — name the file, the function, the endpoint, the exact wrong behaviour.
4. Record failures honestly, including your own wrong turns. A build log with no mistakes in it is a build log nobody will believe.
5. Never put a key, a secret, or an account balance in here. This file goes into a public repository and into a dissertation.
6. Do not rewrite history. Correct an earlier entry with a new one, not by editing the old one.
