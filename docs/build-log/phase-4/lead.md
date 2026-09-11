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

### Finishing C's proof after its session died, and one mutation that asked the wrong question

**Agent:** Lead · **Task:** phase close · **Date:** 2026-09-11

**What happened.** C's session hit its usage limit mid-sentence, on the words *"Now proving the
new test can actually fail — both halves."* The test in question —
`test_the_engine_count_says_which_engines_it_counted` — was written and committed; the
falsifiability proof the phase requires of every assertion was not.

**What the tree looked like afterwards, which is the habit working.** One modified file:
`context/progress/c-interface.md`. No half-written test, no broken module. C wrote the progress
entry before doing the work, exactly as `script-rules.md` requires, so the design survived the
death of the session that held it. Phase 3 lost three build logs to an interruption for the
opposite reason.

**Proof of the wording half, obtained without writing in C's lane.** The assertion is
`"runtime engines" in empty.message`. Rather than mutate `verify.py`, I ran both criteria
read-only, took the real message, removed the word from a copy in memory, and showed the
assertion flips to False while `reported_engine_count` still parses 9 out of the tidied string.
That demonstrates both halves of C's claim at once: the wording assertion can fail, and it
fails *independently* of the count assertions, which is what C said was the reason for
splitting them in two.

**The mutation that asked the wrong question.** For the count half I unregistered engine 19
from `MANAGE_CHAIN` — my own file, committed, so `git checkout --` was a real safety net rather
than the absent backup of the earlier entry. Five tests passed. **That is not a survivor and it
must not be filed as one.** The assertion is relational — `empty + 1 == total` — and removing a
*runtime* engine moves both counts together, 9→8 and 10→9, so the gap it measures is untouched.
The mutation never asked the question the assertion answers. Killing that assertion needs the
gap itself to change, which means adding a second engine to `OFFLINE_CHAIN` in `cli/research.py`
— A's lane, and A is stood down.

So the honest state: the wording assertion is proven falsifiable, the two claims are proven
separable, and the relational premise is **unproven** and recorded as such.

**Consequence.** The rule this reinforces is already in `code-standards.md` in B's words — a
mutation that survives a subset has not survived, it has not been asked — but this is the first
time it has bitten on a *relational* assertion, where the obvious mutation moves both sides of
the relation at once and looks conclusive. Worth remembering: **to kill a relational assertion
you must change the relation, not either operand.**

### `toolchain_green` is intermittently red and nobody can explain it

**Agent:** Lead · **Task:** phase close · **Date:** 2026-09-11

**What happened.** On a provably quiescent tree — no agent running, `git status` clean, HEAD
committed — running the five phase gates back to back produced **three different single
failures**, one per phase, none of them the same test:

```
phase 1  FAIL toolchain_green  FAILED tests/platform/test_config.py::test_a_missing_required_key_is_refused
                               1 failed, 1673 passed
phase 2  FAIL toolchain_green  FAILED tests/research/test_historical.py::
                                 test_cli_research_is_the_only_module_outside_research_that_imports_it
                               1 failed, 1673 passed
                               (first attempt: pytest CRASHED, 3221226505 / 0xC0000409
                                STACK_BUFFER_OVERRUN)
phase 4  FAIL toolchain_green  ERROR tests/console/test_commands.py::
                                 test_the_command_connection_cannot_write_any_other_table
                               ERROR tests/research/test_backtest.py::
                                 test_the_config_itself_is_handed_to_the_labeller_not_three_pre_read_numbers
                               1672 passed, 2 errors
```

Phases 0 and 3 were green in the same sequence. An hour earlier the identical sequence was green
throughout.

**What is established, by observation rather than by reasoning.**

- `pytest tests/ -q` run **directly** is green: `1674 passed, 1 skipped`, exit 0.
- `verify.py --phase 1` run **alone, twice** is green both times, 10/10.
- The failures appear only when pytest runs inside `toolchain_green`'s subprocess during a
  back-to-back sequence of verify processes.
- The failing test differs every time and the ones seen so far have nothing in common
  functionally — a config refusal, an import-boundary scan, a store permission check, a
  labelling seam.
- One occurrence was not a test failure at all but a process crash with
  `0xC0000409 STACK_BUFFER_OVERRUN`, which is the native fault this machine has carried
  unexplained since Phase 2.

**What is NOT established, and is deliberately not guessed at.** Whether this is one mechanism
or several. Phase 3 paid for that lesson: a workspace sweeper deleting live databases, a
wall-clock assertion measuring the wrong thing, and a genuine native fault were charged to one
cause for two phases. Three of the four agents hit an unreproducible failure under
`toolchain_green` during Phase 4 and all three recorded it as unexplained rather than
attributing it. That is the right posture and this entry keeps it.

**Why it matters more than an ordinary flake.** `toolchain_green` is registered in **every**
phase, and it is the only criterion that can see a broken test suite. If it is intermittently
red for reasons nobody understands, then *"the phase is green"* is a statement with a
probability attached rather than a fact — and the failure mode is the one this whole phase was
arranged around: it is at its most convincing when it is wrong, because the obvious response is
to re-run until it is green and believe the green.

**Not fixed, not worked around, and explicitly not re-run until green.** It is an open item for
the operator, and it is the reason this phase is reported as *green on the criteria and
intermittently red on the suite* rather than simply green.
