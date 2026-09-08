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

### A tick is `(run_id, cycle_id)`, and one index nearly proved it the hard way

**Agent:** Lead · **Task:** spec 11 · **Date:** 2026-09-08

**What happened.** Spec 11 as I wrote it required a partial unique index on `(cycle_id)` where
`is_primary` is true. Agent B escalated that this is unimplementable next to spec 13, which
mandates a seeded outage run spanning two `run_id`s. `cycle_id` restarts at 1 with each process,
so two runs necessarily reuse the same low values and the index would have rejected the very
fixture the phase requires.

**Why.** I wrote "one primary per tick" and then encoded "tick" as `cycle_id`, which is not what
a tick is. The context files said `cycle_id` "restarts with the process" and I read that as a
warning about ordering rather than as a statement about identity.

**Fix.** The index is `UNIQUE (run_id, cycle_id) WHERE is_primary = 1`. More usefully,
`architecture-context.md` now states outright that a tick is the pair, that every join to
`rejections`, logs and SHAP rows uses both columns, and that any once-per-tick constraint is
scoped to the pair; `engine-contracts.md`'s state-key entry says `cycle_id` is an integer,
restarts each run, and is ambiguous on its own.

**Consequence.** B's second point was the one worth having. The two seeded runs must *overlap*
in `cycle_id`, not merely differ in `run_id` — because if they did not overlap, ordering by
`cycle_id` would give the same answer as ordering by `ts`, and the Phase 3 criterion that exists
specifically to prove that difference would pass against a broken implementation. A fixture that
cannot fail is not a fixture. That overlap is now deliberate and documented in spec 13, which
also switched every seeded fixture from a fixed number to a multiple of the injected threshold,
so it keeps overshooting whatever the operator eventually sets.

### Three database constraints nobody specified, all approved

**Agent:** B · **Task:** spec 11 · **Date:** 2026-09-08 · *(recorded by the lead at approval)*

B proposed three constraints no spec asked for, each turning a documented convention into a
property of the database: `UNIQUE (pair) WHERE status = 'open'` for invariant 6's one-position-
per-pair; `UNIQUE (run_id, cycle_id)` on `equity_snapshots` for its one-row-per-tick; and
`CHECK (typeof(col) = 'text')` on every money column.

The third is the one that matters. SQLite is dynamically typed and will store a float in a TEXT
column without complaint, so "money is never `REAL`" was an assertion in a document rather than
anything the database would enforce. A drifting float equity series moves the drawdown threshold
that liquidates the account. Approved as written.

### Decision: retired terms may carry a same-line qualifier

**Agent:** Lead · **Task:** spec 02 · **Date:** 2026-09-08

**What happened.** The first real run of `scripts/verify.py` FAILed `docs_vocabulary` on
`progress-tracker.md:76` — "**Eight** config values are trading behaviour…" — matching the
retired term `eight`. C escalated rather than resolving it, correctly: spec 02 forbids editing a
context file to make the check pass.

**Options.** Reword the line and keep a bare-token match, making the word "eight" effectively
unusable in every document. Or change the row's term to a distinctive phrase such as
`eight engines`. Or special-case the row in the checker.

**Chose.** None of those. The table gained a third column — an optional same-line qualifier —
and the `eight` row now reads: hit only when the line also contains `machine learning`, `non-ML`
or `engines`.

**Because.** The phrase-token option is the one that looks cleanest and is actually wrong. The
defect this row exists to catch was "Twenty-three **engines** run in a fixed order… **Eight**
contain no **machine learning** at all" — a literal `eight engines` token matches none of that,
so the row would have been silently disarmed on its only real case. C had argued exactly this
point about over- versus under-matching and then proposed the under-matching fix; checking the
historical text rather than reasoning about it is what settled it. A qualifier keeps the strict
behaviour where it matters, keeps an ordinary English word usable, and stays **data in the table
rather than a rule in the checker**, which spec 02's Scope Limits require.

**Cost.** Same-line co-occurrence misses a sentence split across two lines. Accepted and written
into `ai-workflow-rules.md`: that gap is the manual procedure's, not the checker's.

**Consequence.** Line 76 was also wrong on the facts — nine nulls in `config/default.yaml`, not
eight, and I had miscounted it as seven in an earlier report. The check was pointing at a real
error even under the reading that would have made it a false positive.

### Decision: a missing dependency is FAIL, not PENDING

**Agent:** Lead · **Task:** spec 01 · **Date:** 2026-09-08

C reported that running verify under the system 3.14 interpreter instead of `.venv` made
`seed_fixtures_present` degrade to `PENDING("yaml is not installed")`, and asked whether
verify.py should re-exec itself into the venv.

**Chose.** No re-exec — that hides a broken environment, and C was right to avoid it. But the
PENDING is the same fault one level down. PENDING means *the subject does not exist yet*; a
missing interpreter dependency is a broken environment reporting as orderly progress, and would
let a phase sit at "no FAIL" while nothing was being checked. It reports FAIL with the fix.

**Because.** The value of three results instead of two is entirely in the distinction between
"not built yet" and "wrong". Anything that blurs it turns the gate back into a checklist.

### `EngineStatus` was `(str, Enum)`, and that is a silent bug under the circuit breaker

**Agent:** Lead · **Task:** spec 04 · **Date:** 2026-09-08 · *found by B, ruled by the lead*

**What happened.** Ruff's UP042 fired on B's ten store enums, wanting `StrEnum`. B switched them
and gave a reason better than the lint rule: with `(str, Enum)`, an accidental
`str(OrderStatus.RESTING)` writes `"OrderStatus.RESTING"` into a column queried for `'resting'`.
C then pointed out that `engine-contracts.md` specifies `class EngineStatus(str, Enum)` verbatim,
so my file would trip the same rule and could not be fixed the same way without changing a
contract declared fixed. Both suggested a per-file ignore.

**Why the ignore was wrong.** `EngineStatus` values do not stay in memory. `state["guard_blockers"]`
carries `result.status`, engine 19 writes it to `block_records.status`, and engine 17 `safety`
queries that column for `status = 'ERROR'` to compute the error rate that trips the breaker. An
f-string or `str()` anywhere on that path writes `"EngineStatus.ERROR"` — a plausible-looking
string that never matches. The error rate then reads zero forever and the breaker never fires on
it. Nothing fails; a safety mechanism just quietly stops working.

**Fix.** `engine-contracts.md` now specifies `class EngineStatus(StrEnum)`. `StrEnum` has been
stdlib since 3.11, already the project floor. No per-file ignore; UP042 stays on everywhere. Spec
04 requires a test asserting `str(EngineStatus.ERROR) == "ERROR"`.

**Consequence.** This is a change to a file whose header says the interface is fixed and that
changing it requires the lead. Taken deliberately: the contract's *intent* was a string enum whose
members equal their string values, and `StrEnum` implements that intent where `(str, Enum)` only
approximates it. The alternative was carrying a known silent defect in the safety path to keep a
linter quiet.

### No `.gitattributes`, and Windows was quietly rewriting the evidence

**Agent:** A · **Task:** spec 10 · **Date:** 2026-09-08 · *escalated by A, fixed by the lead*

**What happened.** Staging `tests/fixtures/record_sample.jsonl` warned that LF would be replaced
by CRLF. `core.autocrlf` is `true` in `C:/Program Files/Git/etc/gitconfig` — the Git for Windows
system default, set by nobody here — and the repository had no `.gitattributes` at all.

**Why.** Every committed-fixture criterion in this project compares bytes that git would rewrite
between commit and clone, against a rule that says a criterion passing only on the machine that
produced it is broken. The text fixtures survive parsing; the danger is Phase 4's
`labelled_sample.parquet`. Git's text/binary detection is a heuristic, and a wrong guess rewrites
`0x0A` bytes inside the payload. It does not fail loudly. It fails weeks later on another machine
as a fixture that will not parse, with nothing pointing back at a line-ending default nobody set.

**Fix.** `.gitattributes` at the root: `* text=auto eol=lf`, `tests/fixtures/** -text`, and
explicit `binary` for `*.parquet`, `*.sqlite`, `*.sqlite-journal`. `git add --renormalize .` run;
`git ls-files --eol` confirms `attr/-text` on the fixtures.

**Consequence.** Found in Phase 0 by an agent staging one file and reading the warning instead of
dismissing it. The cost of finding it in Phase 4 would have been a corrupted binary fixture and no
obvious cause.
