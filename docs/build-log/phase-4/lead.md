# Build log — Phase 4 — lead

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

### The unexplained CRLF conversion from Phase 3, explained

**Agent:** Lead · **Task:** spec 58 / phase opening · **Date:** 2026-09-11

**What happened.** Editing `context/ownership.md` and one spec file with a
`read_text()` / `write_text()` round trip converted **both files entirely to CRLF**, against
a `.gitattributes` that says `* text=auto eol=lf`. `git add` printed *"CRLF will be replaced
by LF the next time Git touches it"*. A survey of the working tree found **120 tracked files
already in this state**, including every context file, every build log and most specs.

**Why.** `Path.write_text()` opens in text mode, and text mode on Windows translates every
`\n` to `\r\n`. `read_text()` translates the other way on the way in. So the round trip every
agent reaches for when editing a document — read it, replace a string, write it back — rewrites
the whole file's line endings, whether or not the edit touched those lines. Reproduced in three
lines: `b'one\ntwo\nthree\n'` goes in and `b'one\r\nTWO\r\nthree\r\n'` comes out. Passing
`newline=""` to `open()` leaves the bytes alone.

Phase 3 recorded this as *"an unexplained CRLF conversion, and it is the kind that hides"*,
noting the harness wrote with `write_bytes` and the file came back with 733 CRLF endings
anyway. The mechanism above is the one that produces exactly that symptom on any path where a
text-mode write happens anywhere in the chain, and it is almost certainly the same defect.

**Why nobody noticed for three phases.** `text=auto` means git applies a clean filter on the
way into the index, so a CRLF working file and an LF blob are *identical after cleaning* and
`git status` reports nothing. The repository's content has been correct the whole time. The
drift is confined to the working tree, which is why every audit that read the committed bytes
came back clean.

**Where it stops being benign, and it is exactly where Phase 4 lives.** `.gitattributes` marks
`tests/fixtures/**` as `-text` precisely so no conversion happens near an evidence fixture.
On those paths there is no clean filter to hide behind: a text-mode round trip changes the
committed bytes. On `labelled_sample.parquet` — spec 56, this phase — that is not a cosmetic
diff, it is a corrupted payload, and the criterion reading it would fail with a parse error
naming nothing useful.

**Fix.** The two files I converted are restored to LF. The general rule goes to the agents and
into `code-standards.md`: **when editing a file in place, write bytes or pass `newline=""`.**
Never a bare `write_text()`. The 120 pre-existing files are left alone — rewriting them all
would produce a several-hundred-file diff that changes nothing in the repository, which is the
same invisible-noise problem from the other direction.

**Consequence.** Phase 3's open item is closed with a mechanism rather than a guess. The
residual risk is narrowed from "somewhere in the tree" to "any text-mode write under a `-text`
path", which is checkable.

### The invariant 5 mutation, and a backup that was not one

**Agent:** Lead · **Task:** spec 58 / spec 55 handover · **Date:** 2026-09-11

**What happened.** Spec 55 names a mutation that only the lead may run: add
`from acsoe.research.backtest import BacktestEngine` to `bootstrap.py` and confirm the
architecture-invariant-5 guard goes red. A refused to run it and was right to — rule 2 is not
suspended for a transient write, and a mutation reverted a second later is still a write to
another agent's path in a shared checkout. A built a substitute and said in its own log
exactly where the substitute is weaker: no single test both proves the detector can fail and
proves it reads the real file.

**Result.** The guard fires and names the offending line:
`AssertionError: assert ['bootstrap.py: from acsoe.research.backtest import BacktestEngine'] == []`.
Two tests went red, the guard and the meta-test that pins it. Reverted; `git status` reports
`bootstrap.py` byte-identical to HEAD, and the guard is green again at 28 passed.

**The near-miss, which is the part worth recording.** I took a backup first —
`cp src/acsoe/bootstrap.py "$TMPDIR/bootstrap.py.bak"` — and `$TMPDIR` was empty in the
subshell, so the file went somewhere neither branch of the fallback could find. The restore
raised `FileNotFoundError` with the mutation still in place. It cost nothing because
`bootstrap.py` had no uncommitted changes and `git checkout --` restored it exactly. **Had it
carried uncommitted work, the restore would have destroyed it and the backup would not have
been there.** A backup written to an unresolved shell variable is not a backup, and the moment
you find that out is the moment you need it. Verify a backup exists before you rely on it, or
use the thing that already tracks the file.

**Consequence.** The mutation is proven and recorded here rather than in A's log, because the
write was mine. A's substitute stays: it covers the case where nobody is willing to touch
`bootstrap.py`, which is most of the time.
