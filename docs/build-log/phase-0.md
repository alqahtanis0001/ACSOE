# Build log — Phase 0: Structure

Written by the agents as work happens, per `context/script-rules.md`.
Record every non-trivial problem and its fix. This cannot be reconstructed later.

## Phase 0 summary

*Written by the lead when the phase closes.*

**Built.**
**Verify output.**
**Problems of note.**
**Deliberately deferred.**

---

## Entries

*Append chronologically. Minimum headings: What happened, Why, Fix.*

---

### Decision: `scripts/verify.py` belongs to C, not to A

**Agent:** Lead · **Date:** 2026-09-08

**Options.** `ownership.md`'s permanent roster gave Agent A the whole of `scripts/`. The Phase 0
split in the same file gave Agent C `scripts/verify.py`. Two agents owning one file, in a scheme
whose rule 1 is "write only inside your own paths, no exceptions" and whose only enforcement is
goodwill. Either A owns `verify.py` and the Phase 0 split is wrong, or C owns it and the roster is.

**Chose.** C owns `scripts/verify.py` permanently; A owns the rest of `scripts/`, including
`record.py`.

**Because.** Verification is C's surface already — C owns the test harness, `tests/conftest.py`
and the `tests/fixtures/` structure that the criteria read. Splitting the verifier from the
fixtures it asserts against would have put a seam through the middle of one job. Ownership is
permanent, not per phase, so this had to be fixed in the roster rather than papered over for
Phase 0.

**Consequence.** `ownership.md` roster and a new "`scripts/`" entry under *Paths nobody was
assigned* both corrected. Caught at assignment time, which is the last honest moment — one hour
later both agents would have been writing the same file.

### Decision: no task tooling, so the shared list is a file

**Agent:** Lead · **Date:** 2026-09-08

**Options.** `run-protocol.md` requires every task on a shared task list with spec number, owner,
files and acceptance check. This build exposes `SendMessage` but no `TaskCreate`/`TaskList`
tools, so there is no shared list to write to. Either invent a claim protocol over messages, or
put the list in a file.

**Chose.** `feature-specs/PHASE-0-TASKS.md`, lead-owned, with teammates claiming by recording the
spec number in their own `context/progress/<agent>.md` before writing code.

**Because.** Claiming in the shared file would reintroduce exactly the concurrent-write hazard
that `ownership.md` rule 3 cites as the reason no teammate may touch the tracker. Per-agent
progress files already carry the claim; ownership rule 5 already said so. The file is the list;
the claims stay distributed.

**Cost.** Nothing enforces the claim mechanically. Same as the ownership map itself, which is why
rule 1 is absolute.
