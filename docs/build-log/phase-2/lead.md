# Build log — Phase 2 — lead

Entries the lead owns directly. Consolidated into `docs/build-log/phase-2.md` at phase close.

Minimum headings per entry: What happened, Why, Fix.

## Entries

### The command reader was broken in three places, not one

**Agent:** Lead · **Task:** first task of Phase 2, before any engine work · **Date:** 2026-09-09

**What happened.** `Orchestrator._consume_commands` looked up `store.claim_pending_commands`
through `getattr`. `StoreClient` has never had that method, so the lookup returned `None`, the
reader logged one debug line and returned, and a daemon wired to the real store ignored every
Activate, Freeze and Close-all ever written. Fixing it surfaced two more faults in the same forty
lines:

- `_mark_consumed` called `mark_command_consumed(command, now=...)`. The real signature is
  `(command_id, *, consumed_at)`. It would have raised if it had ever been reached — it never was,
  because the reader returned before getting there.
- `_clear_close_intent_if_finished` called `store.mark_close_all_consumed(run_id=..., now=...)`.
  Also absent. So even a **successful** liquidation left its row claimed-and-unconsumed, which is
  precisely the shape the startup replay looks for. The next restart would re-apply `close_all`
  against an already-flat account.
- The startup re-application of claimed-but-unconsumed rows did not exist at all. Nothing in
  `src/` called `claimed_unconsumed_commands()`, though `architecture-context.md` requires it and
  names the exact failure it prevents.

**Why.** Every one of these is a seam between two owners — the lead's `core/` and B's
`clients/store/` — and every test of that seam went through a double: `_Store` in
`tests/core/test_orchestrator.py`, and an adapter in `tests/console/test_commands.py`. Both doubles
implemented the shape the orchestrator *asked for* rather than the shape the store *has*, so both
sides passed their own tests while disagreeing with each other. **A seam exercised only through a
double is not tested; the double is.**

**Fix.** The reader is composed from the four methods `StoreClient` actually exposes —
`claimed_unconsumed_commands`, `pending_commands`, `claim_command`, `mark_command_consumed` —
entirely inside `core/`, renaming nothing in B's directory, per the operator's instruction. The
`close_all` row id is carried on the orchestrator until both manage engines report done, which is
what phase two of the two-phase consumption needs. `_to_micros` is duplicated in `core/` rather
than imported from `clients/store/contracts.py`, because invariant 0 says `core/` imports nothing
from the rest of the package and that boundary is worth more than six lines of reuse.

**Consequence.** `commands_round_trip` is registered for phase 2 and refuses every double: real
migration, real `StoreClient`, real `Orchestrator`. Only the config and clock are fabricated and
neither is part of the seam. C proves it can fail as part of spec 33 — a criterion nobody has seen
fail is a comment.

The question worth asking of every other row in `ownership.md`'s seam table before its phase
closes: *has anything ever driven this seam without a double on one side?*

### Decision: an unrecognised command is now consumed, not merely ignored

**Agent:** Lead · **Date:** 2026-09-09

**Options.** `architecture-context.md` says an unrecognised command is ignored and logged and never
blocks the loop. It says nothing about consumption, so either leaving it unconsumed or consuming it
was defensible.

**Chose.** Consume it, and log it.

**Because.** `pending_commands` filters on `claimed_at IS NULL`. A row claimed on the tick that
ignored it would never appear as pending again, and would sit claimed-and-unconsumed forever —
which is exactly what the startup replay hunts for. Every restart for the life of the database
would re-apply it. Ignoring a command is a *decision*, and a decision is complete the moment it is
taken, so `consumed_at` is the honest stamp.

**Cost.** A behaviour the context file does not describe, so it is recorded here and asserted in
`tests/core/test_orchestrator.py` rather than left to be rediscovered.

### Two edits outside the lead's lane, declared

**Agent:** Lead · **Date:** 2026-09-09

Fixing the reader broke two test files. `tests/core/test_orchestrator.py` mirrors `core/` and is
the lead's, so rewriting its `_Store` double to the real store's shape was in lane.
`tests/console/test_commands.py` is **C's**, and its `_StoreAdapter` existed only to work around
the defect I had just fixed — C had raised it as an open question rather than editing B's file,
which was the right call. I deleted the adapter and passed the real `StoreClient` straight in,
which makes that test strictly stronger: an adapter is a place a mismatch can hide.

That is still a write in C's directory, and rule 1 says no exceptions. Declared here rather than
left silent. The same judgement as the Phase 1 close: an operator-directed change, mechanical,
with the owning agent not running. If it becomes a habit rather than an exception, the rule has
stopped meaning anything.

### Decision: Phase 3's deterministic engines overlap Phase 2

**Agent:** Lead · **Date:** 2026-09-09 · **Decided by:** the operator

**Options.** Run Phase 2 with A carrying almost everything and B nearly idle, then start Phase 3
cold; or bring engines 10 `cost`, 11 `risk` and 17 `safety` forward and build them concurrently
against mocks.

**Chose.** The overlap, with a hard boundary.

**Because.** The phase rule exists to stop work standing on foundations that do not exist yet, and
these three do not. **They depend on the exchange only through a contract** — B agrees the
fee-tier and pair-rule shape with A against `clients/kraken/contracts.py` and builds against a
mock, which is the same "agree, mock, continue" rule that governs every other seam in the project.
And **`safety`'s six inputs have never depended on anything later than the Phase 0 seed**: all six
are written by engine 19 `memory`, which is Phase 4, and B built those fixtures in Phase 0 for
exactly this reason. Testing `safety` against the seed is the designed path, not a shortcut.

**Where the line is drawn.** Engine 7 `scout` stays in Phase 3 proper. It needs a real tradable
universe computed from live pair rules and balances — it depends on *data*, not on a contract, and
that is the whole distinction. The overlap covers engines that can be finished against an agreed
shape; it does not cover engines that need something real.

**Cost.** Three engines will exist having only ever seen a mock, which is not the same as being
finished. So they do not count toward Phase 2's gate, and **Phase 3 stays closed until Phase 2 is
green and all three are wired to A's real client.** The risk is that "built" gets mistaken for
"done" at the Phase 2 close; the tracker and the task list both say so explicitly, and the Phase 3
criteria will judge them against the real client regardless.
