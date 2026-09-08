# Build log — Phase 0: Structure

Written by the agents as work happens, per `context/script-rules.md`.
Record every non-trivial problem and its fix. This cannot be reconstructed later.

## Phase 0 summary

*Written by the lead at phase close, 2026-09-08.*

Phase 0 built the structure the rest of the project is poured into: a verifier, a package, a
config layer, an orchestrator with no engines in it, a database with a seeded history, and a
test harness that cannot reach the network. No trading logic, no models, no exchange calls. The
phase is green — `python scripts/verify.py --phase 0` reports 7 criteria, 7 PASS, 0 FAIL, 0
PENDING — and green here means every criterion was *executed*, not that a checklist was read.

**Built.** Sixteen feature specs across four workers.

- **C — Interface.** `scripts/verify.py`, its criterion framework and the seven Phase 0
  criteria, each proved twice: PENDING against a tree where its subject does not exist, and PASS
  against a fabricated minimal subject. `docs_vocabulary` is registered in every phase and
  parses its retired-term table out of `ai-workflow-rules.md` rather than hardcoding it. Plus
  the test harness, `tests/conftest.py`, the `tests/fixtures/` structure, the network guard with
  its negative test, and the fake Kraken client.
- **A — Platform.** The src-layout package and `pyproject.toml`; `platform/config.py` and every
  refusal it owes — a null OPERATOR REQUIRED key named individually, `mode: live` refused, a
  poll interval above a quarter of the stale threshold refused; the clock, structlog JSON
  logging with two-layer redaction, and the runtime directories; the three CLI entry points; and
  `scripts/record.py` with a committed 25-line sample.
- **B — Store.** `db/migrations/` and a forward-only migration runner, the store client, and the
  seed generator — which produces all six fixtures Phase 3's circuit-breaker criteria count
  against, each overshooting its threshold rather than sitting on it.
- **Lead.** `core/` contracts and the three-chain orchestrator, `bootstrap.py` and the engine
  registry, and `config/default.yaml`.

**Verify output.**

```
$ .venv/Scripts/python.exe scripts/verify.py --phase 0
ACSOE verify - phase 0
repo: C:\Users\saad2\Documents\GitHub\ACSOE

PASS    docs_vocabulary              14 files scanned, 9 retired terms, no hit
PASS    orchestrator_empty_registry  one tick completed against 0 registered engines; empty chains are valid, state["system"]["mode"]='idle'
PASS    db_migrates_from_empty       fresh database migrated to all 9 documented tables
PASS    seed_fixtures_present        all six fixtures present: outage run 18 ticks over 2 run_ids (11 double-blocker), 2 open position(s), 2 resting order(s), drawdown 0.2000017843760037115020877199, losing streak 8, 23 ERROR blocks in the window, 33 trades / 46 rejections
PASS    record_sample_valid          25 lines valid against the recorder schema; kinds present: gap, session, tick
PASS    toolchain_green              pytest, mypy --strict and ruff all green (python.exe)
PASS    is_gate_matches_registry     0 engines registered; 0 mismatches

7 criteria: 7 PASS, 0 FAIL, 0 PENDING
Phase 0 is green: every criterion PASS, zero PENDING.
```

Underneath `toolchain_green`: 528 tests passing, `mypy --strict src/` clean across 29 source
files, `ruff check src/` clean.

**Problems of note.** Five are worth an examiner's attention, and they are not the five that
took the longest.

1. **A criterion that could not be satisfied in its own phase, three times over.**
   `is_gate_matches_registry` was specified to report PENDING while no engine was registered —
   but Phase 0 registers no engines by design, and a phase is green only at zero PENDING, so
   the gate was structurally uncompletable. The same shape had already appeared twice: Phase 3
   counting block records written by an engine that lands in Phase 4, and a missing interpreter
   dependency degrading to PENDING. The common error is reasoning about what exists rather than
   about what the check asserts. Zero engines matching zero rows is satisfied, not absent.
2. **A tick is `(run_id, cycle_id)`, and the fixture had to be able to fail.** A unique index
   scoped to `cycle_id` alone would have rejected the second seeded run. The sharper half was
   B's: if the two seeded runs did not *overlap* in `cycle_id`, then ordering by `cycle_id`
   would give the same answer as ordering by `ts`, and the Phase 3 criterion that exists
   specifically to prove that difference would pass against a broken implementation.
3. **Constraints that turn a document's assertion into a property of the database.** Money is
   `ANY` in a `STRICT` table with `CHECK (typeof(col) = 'text')` — counter-intuitively a
   stronger guarantee than declaring `TEXT`, which has TEXT *affinity* and silently converts an
   inserted float to a string before the CHECK ever sees it. A drifting float in the equity
   series moves the drawdown threshold that liquidates the account.
4. **`EngineStatus` was `(str, Enum)`.** `str(EngineStatus.ERROR)` yields
   `"EngineStatus.ERROR"`, which is written to `block_records.status` and never matches the
   `status = 'ERROR'` query the circuit breaker computes its error rate from. Nothing fails; a
   safety mechanism quietly stops working. The contract file was changed to `StrEnum` rather
   than a per-file lint ignore added.
5. **An intermittent native memory fault, closed as a risk rather than repaired.** Roughly 20%
   of full-suite runs die in the seed write path at pydantic `model_dump`. Investigated at
   length, not root-caused, hardware suspected and out of scope. `toolchain_green` now retries a
   *crash* once — never a verdict — and names the crash in the PASS. Full entry below.

**Deliberately deferred.**

- **Widening `TOOLCHAIN` beyond `src/`.** `mypy --strict scripts/` reports 2 errors in
  `verify.py` and `ruff check tests/` reports 2 violations, none of them reachable by the gate
  that implements them. Changing what every phase's gate asserts belongs at a phase boundary,
  not at a phase close.
- **The console's history, research, leaderboard and SHAP views.** Named in the Phase 1
  criteria, designed in no context file, and fed by engines that do not exist until Phase 4 and
  Phase 5. A scope question for the operator.
- **The hardware question behind the memory fault.** Answerable only on different hardware.
- **`Clients` in `cli/engine.py` carries three `None`s.** No engine is registered in Phase 0;
  wiring B's store client in is Phase 2 work, not a Phase 0 omission.

**Two arithmetic consequences of the operator's starting values**, checked before they surprise
anyone in a later phase and recorded in full in `context/progress-tracker.md`: at tier 1 nothing
clears the cost gate by construction (`hurdle_multiple: 1.5` needs a 3.125% expected move
against a 3.0% target barrier), and `max_concurrent_positions: 3` is inert at a $5,000 balance
where one position is ~$3,333 of notional. Neither is a defect. Both are tests a later phase
would otherwise fail for reasons unrelated to the code under test.

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

**Follow-up, and the part that actually made it work.** The first implementation declared the
money columns `TEXT` with that CHECK, and B found it enforced nothing. A column declared `TEXT`
has TEXT *affinity*: an inserted REAL `0.3` is silently converted to the string `'0.3'`, and
`typeof()` then reports `'text'`, so the CHECK passes and the float is already lost. `STRICT`
does not close it either — its TEXT columns convert numbers the same way.

The working form is `ANY` in a `STRICT` table with `CHECK (typeof(col) = 'text')`. `ANY` is the
one declaration that stores the value as given, so the CHECK sees a real REAL and rejects it.
Counter-intuitively, the *contents* are guaranteed TEXT far more strongly by declaring `ANY`
than by declaring `TEXT`.

Recording this loudly because it looks wrong on sight and invites "correction". Agent A saw
`equity_snapshots.equity is ANY` in a test failure and proposed adding `TEXT` back, which would
have reopened the hole. The reasoning is the defence; a lint-shaped fix here is a silent
regression in the money path.

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

### Spec 01 made Phase 0 impossible to finish

**Agent:** Lead · **Task:** spec 01 · **Date:** 2026-09-08

**What happened.** With the orchestrator and an empty `bootstrap.py` landed,
`is_gate_matches_registry` settled on PENDING: "no engine is registered yet". Spec 01 told
Agent C to report exactly that. But Phase 0 registers no engines by design, and a phase is
green only when every criterion is PASS with zero PENDING — so the criterion as written made
the phase structurally uncompletable.

**Why.** I wrote "PENDING while no engine exists" thinking about the *engines* rather than
about the *assertion*. PENDING means the subject does not exist yet. The subject here is
"every registered engine's `is_gate` matches the registry table", and with an empty registry
that assertion has been evaluated and holds. Zero engines matching zero rows is satisfied, not
absent.

**Fix.** Vacuous PASS on an empty registry, with the count in the message —
`0 engines registered; 0 mismatches`. The count is the guard: it tells a reader exactly how
much assurance the PASS represents, and if it ever reads 0 in a phase where engines were
supposed to be registered, that is itself the bug worth seeing.

**Consequence.** Worth noting the shape, because it is the third time a criterion has been
written that could not be satisfied in the phase that owns it — the Phase 3 forward dependency
on engine 19, the environment-degrades-to-PENDING case, and now this. The common error is
reasoning about what exists rather than about what the check actually asserts.

### Decision: `pyyaml` added to the architecture stack table

**Agent:** Lead · **Task:** spec 07 · **Date:** 2026-09-08

**What happened.** Agent C escalated that `config/default.yaml` is YAML and the stack table in
`architecture-context.md` listed no YAML parser, while `ai-workflow-rules.md` makes a dependency
outside that table an escalation. Spec 07 was therefore either impossible or a silent dependency
addition.

**Options.** Add `pyyaml` to the table, or move the config to TOML and use stdlib `tomllib` for
zero new dependencies.

**Chose.** `pyyaml`, with **`yaml.safe_load` only, never `yaml.load`** written into the table row
itself rather than left as a convention.

**Because.** Every context file already says `config/default.yaml`, and YAML's nested maps suit
`paper.starting_balances` — a currency-to-amount map — better than TOML would. The stdlib win was
real but smaller than the doc churn and the ergonomic loss.

**Consequence.** C had built a tiny stdlib fallback parser to keep working while blocked; I had it
deleted rather than kept as a safety net. Two config parsers are two behaviours that diverge on
something subtle at the worst possible moment.

### Decision: the `Config` Protocol is `mode` plus `get(dotted_key)`

**Agent:** Lead · **Task:** specs 04 and 07 · **Date:** 2026-09-08

**What happened.** `core/contracts.py` declared `Config` as a Protocol with a `mode` property and
`get("safety.max_consecutive_data_blocks")`. A's `platform/config.py` was a structured pydantic
model with nested sections and no `get`, so mypy refused it at the seam: "expected
acsoe.core.contracts.Config".

**Chose.** Keep the Protocol; A adds `get` to the model, walking the nested sections and **raising
on a miss** rather than returning a default.

**Because.** The alternative was pinning field names in the Protocol, which puts the same keys in
two files — the lead owns `config/default.yaml`, A owns the model — and lets them drift silently.
A dotted accessor means an engine reads a threshold without depending on the model's shape.

**Consequence.** A implemented it with no default parameter in the signature at all, and a test
asserting that, on the grounds that a `dict.get`-shaped signature invites `config.get(key,
fallback)` and a fallback for a trading threshold is a guessed answer to how much money is at
risk. That is a better guard than the one I asked for. A also added
`isinstance(config, contracts.Config)` against the runtime-checkable Protocol, so the next
divergence fails a test instead of waiting to cross the seam.

### Decision: Python 3.13, with the model libraries in a `research` extra

**Agent:** Lead · **Task:** spec 03 · **Date:** 2026-09-08

The machine's default interpreter is 3.14, and `lightgbm`, `shap`, `hmmlearn`, `statsmodels` and
`scikit-learn` have no reliable Windows wheels for it. Approved building on 3.13 with
`requires-python = ">=3.11"` unchanged.

Rather than take A's proposed fallback of moving those five to an extra only if the install broke,
I made the split the plan: base is the live-loop runtime, `research` holds the five model
libraries, and `dev` includes `research` so `pip install -e ".[dev]"` still installs everything and
`README.md` stays true. Every name stays inside the stack table.

The split also makes the packaging express architecture invariant 5 — the live loop never imports
from `research/` — which the flat list did not. A failing Phase 0 install was never an acceptable
outcome: it is a Phase 0 exit criterion.

### Decision: the CLI dispatcher imports command modules lazily

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08 · *(approved by the lead)*

A changed `cli/main.py` to import each command module inside its dispatch branch rather than at
module scope, and asked whether to revert it as an unconventional shape.

**Approved, and it should not be reverted.** Today `cli/research.py` imports nothing, so
architecture invariant 5 holds trivially. From Phase 4 it registers engines 20 and 23 and
therefore imports `acsoe.research` — at which point an eager dispatcher pulls `research/` into the
daemon's process on every `acsoe engine` invocation, **and nothing fails**. The invariant would be
violated in a way no test, no linter and no reviewer would notice, during the phase least able to
afford the distraction.

Fifteen lines now against an entry-point edit landed in the middle of the phase that is trying to
ship the offline chain. A's test asserts the property in a subprocess, because this process has
already imported all three modules and an in-process check would pass for the wrong reason — that
detail is what makes the test worth having.

### The verify criteria were reporting on this repository, not the tree under test

**Agent:** C · **Date:** 2026-09-08 · *flagged by A, verified by the lead*

**What happened.** Mid-phase, five of `tests/verify/test_phase0_criteria.py` began failing:
`orchestrator_empty_registry`, `is_gate_matches_registry` and `db_migrates_from_empty` stopped
reporting PENDING against a fabricated bare tree once the lead's and B's real modules landed.
Agent A spotted it and flagged that the criteria appeared to resolve `acsoe.*` from the installed
package rather than from the tree under test.

**Why it mattered more than the failing tests.** A criterion that silently reports on this
repository instead of its fabricated subject does not fail — it passes, for the wrong reason. The
symptom was five red tests; the disease would have been a phase gate that could no longer tell an
unbuilt tree from a built one.

**Fix, and it is the cause rather than the symptom.** `root_import_path` drops every managed
module from `sys.modules`, inserts the tree's `root` and `root/src` at `sys.path[0]`, invalidates
the import caches, and restores all of it on exit. `unbuilt_tree` adds an empty `src/acsoe/` for
criteria that reach the package by import, because without a package present the editable install
leaks straight through.

**Verified independently by the lead**, not taken on report: a fabricated tree does shadow the
installed package, `acsoe.bootstrap` is correctly absent inside it although it exists in the real
tree, and the real package is restored afterwards.

**The residual risk, and why it will not bite silently.** This works because the editable install
is a plain `.pth` file appending `src` to `sys.path` — there is no PEP 660 meta-path finder, so
`sys.path` ordering genuinely decides. Confirmed: `sys.meta_path` holds only the three stdlib
finders. If the build backend ever emits a meta-path finder instead, `sys.path[0]` would stop
winning and every fabricated-subject test would quietly start testing the real package.

C documented exactly that in `tests/verify/conftest.py` and wrote
`test_fabrication_actually_shadows_the_real_package` to fail loudly if it ever happens. That test
passes. This is the right shape for a risk you cannot remove: name it, and leave a tripwire rather
than a comment.

---

## Consolidated from the per-agent logs

Merged at phase close from `docs/build-log/phase-0/{lead,a-platform,b-store,c-interface}.md`,
which remain as the agents wrote them. Events the lead had already recorded above — the
`(run_id, cycle_id)` index, the money-column constraints, `pyyaml`, the `Config` Protocol, the
lazy dispatcher, Python 3.13, `.gitattributes`, the `docs_vocabulary` qualifier — are not
repeated here.

### The intermittent native memory fault in the seed write path, and why it was closed as a risk rather than a bug

**Agent:** Lead · **Task:** phase close · **Date:** 2026-09-08

**What happened.** `toolchain_green` fails intermittently — roughly one full-suite run in five —
because the pytest subprocess dies of a native memory fault rather than reporting a verdict.
Every observed instance surfaces in the same place: B's `seed.py:_write_trading_history` →
`client.write_trade` / `write_position` → pydantic `model_dump`, converging in pydantic-core's
`to_python`. Three distinct Windows statuses have been seen — `0xC0000005` ACCESS_VIOLATION,
`0xC0000374` HEAP_CORRUPTION and `0xC0000409` STACK_BUFFER_OVERRUN — plus one
`AttributeError: 'NoneType' object has no attribute '__dict__'` raised from inside `to_python`.
Every test passes whenever the process survives, and `seed_database` called 60 times outside
pytest is clean. C's earlier figure was 6 failures in 20 runs; across the fuller sample it
settles nearer 20%, and the rate is recorded as approximate on purpose — it is a probability,
and no run count observed here pins it more precisely.

**Why it was not root-caused.** It was investigated at length over a full session and the
investigation is closed as unsuccessful, not as pending. Ruled out, each by direct test rather
than by argument: **pyarrow**; **`pytest-asyncio`**; **test ordering** — the fault does not
track a sequence, and `test_seed.py` alone still fails roughly 1 in 15 in isolation; **C's
`root_import_path`**, the obvious suspect, whose swapper does create a second `PositionRow`
class while instances of the first are live, but 40 enter/exit cycles hammering `model_dump`
across both do not crash and the isolated failures never touch it; and **the pydantic-core
version**, where pinning a different build did not settle it. The turbo-clock test — the one
experiment that would have separated software from silicon — was **inconclusive, and known to be
inconclusive**: the active Windows power plan overrode the setting, so the run that was supposed
to be at reduced clocks was not.

**What is left.** The machine is an i9-14900HX, the same B0 die as the 14900K. The remaining
variable is hardware, and hardware is out of scope for this project. Three different fault
statuses converging on one hot native call path, with no reproduction outside the pytest process
and no software variable surviving elimination, is the *shape* of a hardware fault; it is not
proof of one, and this entry does not claim it is.

**Fix.** None available at this level, so the fault is **mitigated rather than repaired**, and
the mitigation is written to keep it visible. `describe_exit` already separates a crash from a
verdict: it classifies each tool's returncode against that tool's own documented range (pytest
0–5, mypy and ruff 0–2), names the Windows NTSTATUS or POSIX signal, and quotes the summary line
the run had already printed, so a process that prints `520 passed` and then dies no longer reads
as a failing suite. On top of that, the criterion now **retries a crash once, and only a crash.**
A clean retry reports PASS with the crash named in the message. A second crash FAILs, with the
`CRASH -` prefix. A verdict — any returncode inside the tool's own range — is never retried, at
any exit code, ever.

That last rule is the whole design. Retrying a verdict is the "re-run until it goes green" habit
that turns a memory fault into a flaky test, which is precisely what `describe_exit` was written
to prevent; an unqualified retry would have re-introduced it through the back door. The bound of
one attempt is for the same reason: two crashes in a row is no longer noise worth absorbing. Four
tests in `tests/verify/test_phase0_criteria.py` pin both boundaries.

**Consequence.** This is a **known risk, not an open question**, and it is recorded as one in
`context/progress-tracker.md`. Nobody should re-open it by re-running the suite to see whether
the result changes — that experiment has been run and its answer is the 20%. What would justify
re-opening it: the fault appearing on a second machine, appearing outside the seed write path, or
the retry starting to fail twice in a row with any regularity. The last of those is what the
bound exists to surface. And one thing to carry forward: the seed write path is exercised hard by
every full-suite run, and Phase 2 onward adds engines that write through the same client. If the
rate rises as that path gets busier, the mitigation stops being adequate and the hardware
question has to be answered on different hardware, not by an agent here.

### The reconnect backoff compounded across successful reconnects

**Agent:** A · **Task:** spec 10 · **Date:** 2026-09-08

**What happened.** `Recorder.run` held `backoff` as a local and reset it to 1s only after
`await self._session()` *returned*. `_session` never returns normally except when the recorder is
shutting down — it exits by raising `ConnectionClosedError`. The reset was therefore unreachable
in practice, and the delay doubled on every disconnect for the life of the process even when
every reconnect had succeeded on its first attempt.

**Why.** Exponential backoff is meant to be per-outage, and "the outage ended" is signalled by a
*successful connect*, not by the read loop returning. Writing it as a local in the retry loop
made the wrong event the reset point, and it is invisible in a short test because the first two
delays look fine.

**Fix.** `_backoff` is an instance attribute reset inside `_session` immediately after
`connect()` succeeds, next to `self._attempt = 0`. Re-running the induced-disconnect capture
gives 0.8, 1.1, 0.9, 0.7, 1.4, 1.1, 1.1 — flat, as it should be.

**How it was noticed.** Not by reading the code — it reads correctly. Producing the committed
sample required a `gap` marker, which required inducing real disconnects, which printed
`reconnecting in 0.6s (attempt 1)`, `1.3s (attempt 1)`, `2.0s (attempt 1)`, `4.2s (attempt 1)` in
one 20-second run. The delay doubling while `attempt` stayed at 1 is the whole tell: the two were
being reset at different points in the loop. Without a fixture that had to contain a gap marker
there would have been no reason to disconnect the recorder repeatedly in a short window.

**Consequence.** More than an ordinary retry bug. A recorder that drops once an hour would, after
twelve hours, sit out a full minute after each fault — and order-book and spread history cannot
be recovered retroactively, so every one of those minutes is data no later phase can obtain by
any means.

### Forcing a real gap marker into the committed sample

**Agent:** A · **Task:** spec 10 · **Date:** 2026-09-08

**What happened.** The sample has to contain a `gap` line — the reconnect path is the part of the
recorder most likely to break later and least likely to be exercised by an ordinary capture. A
clean Kraken v2 session ran 45 seconds and 7,337 lines without a single disconnect.

**Why not fabricate it.** A fixture that was typed rather than recorded proves the format, not
the behaviour, and the whole point of committing evidence is that it came out of the real code
path.

**Fix.** Added `--ping-interval` and `--ping-timeout` — legitimate operational knobs — and
captured with `--ping-timeout 0.001`, well below the round trip to Kraken. The `websockets`
keepalive declares the connection dead, the real reconnect path runs, and the markers carry real
measured `gap_ms` values (1986ms, 2292ms). Fault injection, not fabrication.

**Consequence.** The induced-fault capture was written to a scratch directory, **not** to
`data/raw/`. Polluting the real recording with artificial gaps would corrupt exactly the gap
statistics Phase 2's `recording_report.json` criterion has to report.

### `git check-ignore` reports a *negation* as a match, so it cannot prove a file is committable

**Agent:** A · **Task:** spec 10 · **Date:** 2026-09-08

`git check-ignore -v tests/fixtures/record_sample.jsonl` printed `.gitignore:21:!tests/fixtures/**`
and **exited 0**, which reads as "this file is ignored" and is how a naive check reports it.
`check-ignore` exits 0 when a path matches any ignore *rule*, including a negation; the leading
`!` is the only thing distinguishing "ignored" from "explicitly un-ignored", so a shell test of
the exit code alone gets the answer exactly backwards. The real proof is `git add` followed by
`git ls-files --stage <path>` returning a row. It does: mode 100644, blob 60a0439. Recorded
because the next agent to check a fixture will reach for `check-ignore` first.

### The console health check cannot use `TestClient`

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**What happened.** `fastapi.testclient.TestClient(app).get("/health")` raises
`NetworkAccessError` from C's network guard.

**Why.** `TestClient` is an `httpx.Client` subclass and does not override `send`, and the guard
patches `httpx.Client.send` for every test. The call never leaves the process — `TestClient` uses
an ASGI transport — but the guard sits above the transport and cannot tell an in-process ASGI
request from a real one. Reaching around it would have meant relaxing the guard for convenience,
which spec 14 forbids in as many words, and a slightly over-broad guard is the correct trade for
a system whose tests must never touch Kraken.

**Fix.** `asgi_get` in `tests/cli/test_entrypoints.py` drives the ASGI callable directly: builds
an HTTP scope, awaits `app(scope, receive, send)`, reassembles status and body from the messages
sent back. No socket, no httpx, nothing to relax — and it exercises the same routing and response
path uvicorn would, which is more than calling the endpoint function would have proved.

**Consequence.** The same constraint applies to every HTTP assertion in this repository. Phase 1
should copy the twenty-line driver rather than seek an exemption.

### A failing test bound a real socket

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

**What happened.** While `test_console_refuses_the_committed_config` was red it did not merely
fail. `main(["--config", DEFAULT_YAML, "console"])` no longer returned 2 at the config check, so
it fell through the entire entry point into `uvicorn.run` and tried to bind 127.0.0.1:8765 from
inside the test suite — `SystemExit: 3`, `[Errno 10048] only one usage of each socket address`.

**Why.** The test asserted a return code on a call with a side effect at the far end of it. As
long as the refusal happened, the side effect was unreachable, so the assertion and the guard
against the side effect were the same line — and when the assertion stopped holding, both went at
once.

**Fix.** `test_console_accepts_the_committed_config` stubs `uvicorn.run` before calling the entry
point, captures the app it was handed, and drives `/health` through `asgi_get`. Nothing in this
repository may bind a port to prove a config was accepted.

**Consequence, generalised before Phase 1:** a test that asserts a *refusal* from a function
whose success path starts a server needs the server stubbed regardless, because the refusal is
the only thing standing between the test and the server, and tests exist precisely for the days
that refusal stops happening.

### `--ticks 3` would have made the test suite take two minutes

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

`run_loop` sleeps `timeframes.loop_tick_s` — sixty seconds — *between* ticks, so the natural test
of the daemon is a two-minute test. Not a bug: the sleep is the loop tick, and a daemon that
ticked without waiting would hammer the exchange. The end-to-end test uses `--ticks 1`, which
breaks before the first sleep; multi-tick behaviour is exercised by calling `run_loop` directly
with `tick_seconds=0.0`, the seam that exists so cadence is set by the caller. A `--tick-seconds`
flag was deliberately **not** added: an operator-visible knob that makes the daemon spin faster
than the exchange expects is a worse thing to have in the CLI than a less convenient test.

The property that actually matters — that a stop request never lands inside a tick — is tested by
subclassing the real `Orchestrator`, setting the stop event from inside `tick()`, and asserting
exactly one tick completed. That is the manage chain's guarantee: it runs every tick in every
mode and records that an open position was watched, so a tick abandoned halfway is a decision
taken and never written down.

### `acsoe console` no longer carries a fallback application

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

While `src/acsoe/console/app.py` did not exist, `cli/console.py` carried its own
`build_placeholder_app` and fell back to it on `ImportError`. C's module landed during the
session and the fallback was **deleted rather than kept as a safety net**: two applications that
both answer `/health` mean a health endpoint that proves nothing, because `acsoe console` would
look identical whether it was serving the console or the thing standing in for it. `cli/console.py`
now imports `create_app` at module scope and fails loudly at import if the module is missing. The
import shape was agreed with C before either wrote to it: `create_app(config) -> FastAPI`, taking
the `Config` **Protocol** from `core/contracts.py` rather than A's concrete model, so `console/`
does not depend on `platform/`.

### The null count in `platform/config.py` said ten and the file has nine

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

Two docstrings said `config/default.yaml` carries ten OPERATOR REQUIRED nulls and that the loader
reports "all ten" at once. It carried nine: `safety.error_rate_window_s` was set to `3600` once B
pointed out that `architecture-context.md` specifies the trailing hour, so it was never
operator-required. The code was correct — it counts what it finds — but the prose was written
when the answer was ten and nobody re-read it. Recorded because it is exactly the class of drift
`docs_vocabulary` exists to catch and *cannot*: a bare count is not a distinctive token, so no
grep would ever have found it. `tests/cli/test_entrypoints.py` now asserts the refusal message
names all nine **and** that it does not name `safety.error_rate_window_s` — listing a key the
operator does not have to supply trains them to skim the list, and that list is the only thing
between a fresh clone and a daemon trading on numbers nobody chose.

### A test that encoded a transitional state as a permanent assertion

**Agent:** A · **Task:** specs 07, 09 · **Date:** 2026-09-08

**What happened.** The operator supplied all nine OPERATOR REQUIRED values and three of A's tests
went red. Each asserted that `config/default.yaml` **refuses to load**. With zero nulls, it loads.

**Why.** The assertion was true on the day it was written and was never going to stay true. It
conflated *the behaviour* — a null OPERATOR REQUIRED key must stop the process, which is
permanent — with *the state of one file on one day*. Writing the behaviour test against the
shipped file was convenient, and that convenience is what welded the two together. The failure
direction is worth naming: the tests broke because the config became **more** valid, which is not
a direction anyone writes a test expecting to be pushed in.

**Fix.** The assertion was moved, not deleted. Refusals now run against a config the test
fabricates — `unset_operator_config`, `with_nulled()` — built by taking the shipped file and
setting the nine back to `null`, with nine parametrised single-key cases proving one unset key is
enough on its own and that the message names *that* key and no other. The shipped file acquired
the opposite assertions: it loads cleanly, `mode` is `paper`, and each of the nine parses to its
expected type. `paper.starting_balances.USD` is asserted twice on purpose — once on the raw YAML,
where the value is a *string* and so never touches binary float, and once on the parsed Decimal —
because the parsed value alone cannot tell you which route it took
(`Decimal("5000.0") == Decimal("5000.00")`). Nothing in `platform/config.py` changed except two
stale docstrings; `_refuse_nulls` counts what it finds and never held a list of key names, which
is why zero nulls needed no code change at all.

**The general lesson, and the reason this is in the log: assert the behaviour against a fixture
you control, and assert the committed artefact's state separately.** A test that reads a real
file to prove a rule will pin that file's contents whether or not anyone meant it to.

### The duplicated key list fired, in the direction nobody expected

**Agent:** A · **Task:** spec 09 · **Date:** 2026-09-08

`tests/cli/test_entrypoints.py` and `tests/platform/test_config.py` each hold their own copy of
the nine operator keys, deliberately unshared, so that a tenth key makes both files fail loudly
rather than silently inherit a value chosen elsewhere. It worked — but it fired on the operator
*filling the nine in*, not on a tenth being added. A value arriving is a change to the set as
surely as a key arriving.

With zero nulls shipped, one direction of that signal was lost: the lead could now add a tenth
key **and supply a value for it** and nothing would notice.
`test_the_file_marks_exactly_these_nine_keys_as_the_operator_s` restores it by scanning the
shipped file for its `Operator-chosen` marker — a documented convention stated in the file's own
header, not an inference from formatting — and comparing the set to the tests' own list. The
other direction still needs no marker: a tenth key added as `null` survives the overlay in
`complete_config_dict()` / `startable_config` and takes every test using those fixtures down at
once.

### `executescript` discards the transaction you wrapped around it

**Agent:** B · **Task:** spec 11 · **Date:** 2026-09-08

**What happened.** The first migration runner did `conn.execute("BEGIN")`, then
`conn.executescript(migration.sql)`, then `COMMIT`, and would have applied the schema statement
by statement with no atomicity at all.

**Why.** `sqlite3.Connection.executescript` issues an implicit `COMMIT` of any pending transaction
*before* running its script. The `BEGIN` was committed away by the very call it was supposed to
protect.

**Fix.** `BEGIN` and `COMMIT` moved inside the script string, and the bookkeeping `INSERT` into
`schema_migrations` moved in with them. That second part matters independently: had the insert
stayed a separate statement, a crash between the two transactions would leave a database whose
schema was applied and whose version row was not, and the next startup would try to create tables
that already exist. `executescript` takes no bound parameters, so the three interpolated values
are a parsed integer, a name matched against `[a-z0-9_]+`, and a hex digest — nothing that can
carry an injection.

**Consequence.** `apply_migrations` returns the list of versions it applied, so "re-migrating is a
no-op" is a check on `== []` rather than on a schema diff.

### Decision: migration bookkeeping records no wall-clock time by default

**Agent:** B · **Date:** 2026-09-08

**Options.** Stamp `schema_migrations.applied_at` from the clock, which is what a migration runner
normally does, or leave it null unless a caller supplies it.

**Chose.** `apply_migrations(..., applied_at: int | None = None)`, defaulting to null.

**Because.** Spec 13 requires two seedings of the same seed to be byte-identical, and the seed
migrates the database it seeds. A wall-clock column would make every seeded database differ from
every other one in a way that has nothing to do with the seed. Nothing in this package reads a
clock; the operator gets the timestamp by passing one.

**Cost.** A migrated database carries no record of when it was migrated unless the caller asked
for one. The checksum, which is the field that actually protects anything, is always recorded.

### Decision: `verify.py` takes the repository root as a parameter, not a constant

**Agent:** C · **Task:** spec 00 · **Date:** 2026-09-08

**Options.** Every criterion reads a module-level `REPO_ROOT` derived from `__file__`, which is
the obvious shape for a script that only ever judges its own repository — or every criterion takes
a `VerifyContext` carrying `root`.

**Chose.** The context object.

**Because.** Spec 01 requires each criterion to be proven twice, PENDING on an empty tree and PASS
against a fabricated minimal subject. With a module-level constant there is no way to fabricate a
subject except by monkeypatching a global, which leaks between tests and makes the proof worth
less than the code it takes to write. The same reasoning drove `root_import_path()`.

**Cost.** Every criterion signature carries a parameter it usually only uses for `ctx.root`, and
two helpers had to lose the parameter entirely because they operate inside an already-entered
import context.

### Decision: criteria derive from SQL and then cross-check the fixture accessor

**Agent:** C · **Task:** spec 01 · **Date:** 2026-09-08

**Options.** B exposes `SeedFixtures`, a frozen dataclass naming all six Phase 3 fixtures, and
asked that `seed_fixtures_present` assert on those fields rather than re-deriving them by SQL —
sound reasoning, because two derivations of one rule drift. The alternative was to derive
everything independently from the database.

**Chose.** Both. The criterion derives all six from SQL using only columns fixed by
`architecture-context.md`, compares them against the configured thresholds, and *then* compares
its findings against `SeedFixtures`' declared values, failing on a disagreement and naming both
numbers.

**Because.** A gate that trusts the accessor cannot catch the case the gate exists for.
`SeedFixtures.consecutive_data_block_run.length` reporting 18 while `block_records` holds three
rows is exactly the defect `seed_fixtures_present` is supposed to find, and asserting on the field
alone reports PASS. Deriving from documented columns is not re-encoding B's logic — it is reading
the schema the architecture file fixes, which is the same thing the console and engine 17 will do.

**Cost.** More code, and coupling to six documented column names: an approved schema change moves
this criterion with it.

### Counting by `cycle_id` alone would have under-counted the seed

**Agent:** C · **Task:** spec 01 · **Date:** 2026-09-08

The first draft of the consecutive-`data_guard` counter grouped block records by distinct
`cycle_id`. B's seed deliberately spans two `run_id`s and deliberately **reuses** `cycle_id`
values across them, so grouping that way would have collapsed the overlapping ticks together,
under-counted an 18-tick outage run, and reported a FAIL that was actually a bug in the query.
`_seeded_block_run()` keys every tick on the pair `(run_id, cycle_id)`, orders strictly by `ts`
with `rowid` as a tiebreak, and counts a tick once no matter how many guards blocked on it. It
also returns the number of distinct `run_id`s in the longest run and the number of ticks inside it
carrying more than one blocker, both of which the criterion asserts — so the two-run property and
the one-tick-one-count property are proven rather than assumed.

### The word-boundary rule in `docs_vocabulary` is load-bearing in three separate places

**Agent:** C · **Task:** spec 02 · **Date:** 2026-09-08

**What happened.** A naive substring scan for the retired terms FAILs the current tree three times
over, all of them false.

**Why.** `paper.starting_balance` is retired and `paper.starting_balances` is current, and the
retired string is a prefix of the live one — `trading-invariants.md:48` uses the plural in a
current-state section that is correctly scanned, so a prefix match fails the gate on the very file
that defines the rule. `eight` is a substring of "weight", of "Weight" in a table header, and of
"eighth". All three are legitimate.

**Fix.** `term_pattern()` wraps each escaped term in `(?<![0-9A-Za-z_])` and `(?![0-9A-Za-z_])`,
applied only where the term actually begins or ends in a word character — so `state["system_mode"]`
gets a leading boundary and no trailing one, because it ends in `]`. Matching is case-insensitive,
which is what catches a stale `Chain 2` at the start of a sentence.

**Consequence.** Recorded because it is invisible from the code: three of the current tree's files
would fail this check under the obvious implementation, and a future maintainer who "simplifies"
the pattern to a plain `in` test will break the gate and not understand why.

### Bash heredocs mangled Python source, twice, in two different ways

**Agent:** C · **Task:** spec 00 · **Date:** 2026-09-08

**What happened.** Appending to `scripts/verify.py` through a *quoted* shell heredoc failed with
`unexpected EOF while looking for matching '`, pointing at
`return None, f'{why} - run pip install -e ".[dev]"'`. Separately, backslashes in a heredoc body
were not literal even with a quoted delimiter: a `\b` written into a regex arrived as a raw
backspace byte, and a `\n` inside a test string arrived as a real newline and broke the file.

**Why.** Not fully diagnosed, and recorded as unexplained rather than guessed at: a single-quoted
heredoc delimiter should suppress all shell parsing of the body, and an earlier heredoc in the
same session containing apostrophes wrote correctly. The failing line is the first one mixing a
single-quoted f-string with embedded double quotes.

**Fix.** Stopped writing Python source through heredocs and used direct file writes. The offending
line was also rewritten to string concatenation, removing the nested-quote construct entirely.

**Consequence.** A standing rule for this machine: any agent generating Python through a shell
heredoc should assume the body is not fully literal, and prefer a direct write for anything
containing escapes or quotes inside quotes.
