# Build log — Phase 0 — c-interface

Your file. Append as you work, per context/script-rules.md.
The lead consolidates these into docs/build-log/phase-0.md at phase close.

Minimum headings per entry: What happened, Why, Fix.

## Entries

### Decision: `verify.py` takes the repository root as a parameter, not a constant

**Agent:** C · **Task:** spec 00 · **Date:** 2026-09-08

**Options.** Every criterion could read module-level `REPO_ROOT` derived from `__file__`, which
is the obvious shape for a script that only ever judges its own repository. Or every criterion
could take a `VerifyContext` carrying `root`.

**Chose.** The context object.

**Because.** Spec 01 requires each criterion to be proven twice — PENDING on an empty tree and
PASS against a fabricated minimal subject. With a module-level constant there is no way to
fabricate a subject except by monkeypatching a global, which leaks between tests and makes the
proof worth less than the code it takes to write. With `root` as a parameter the test builds a
throwaway directory, points the criterion at it, and asserts. The same reasoning drove
`root_import_path()`, a context manager that swaps `sys.path` and evicts every cached `acsoe.*`
and `tests.*` module on entry and restores them on exit — without it, a test that imports a
fabricated `acsoe` package poisons the interpreter for whichever criterion runs next.

**Cost.** Every criterion signature carries a parameter it usually only uses for `ctx.root`, and
two helpers had to lose the parameter entirely because they operate inside an already-entered
import context.

### Bash heredocs mangled an f-string containing nested quotes

**Agent:** C · **Task:** spec 00 · **Date:** 2026-09-08

**What happened.** Writing `scripts/verify.py` by appending to it through a quoted shell
heredoc failed with `unexpected EOF while looking for matching '` pointing at the line
`return None, f'{why} - run pip install -e ".[dev]"'`.

**Why.** Not fully diagnosed, and worth recording as unexplained rather than guessing: a
single-quoted heredoc delimiter should suppress all shell parsing of the body, and an earlier
heredoc in the same session containing apostrophes wrote correctly. The failing line is the
first one mixing a single-quoted f-string with embedded double quotes.

**Fix.** Stopped writing Python source through heredocs and used direct file writes instead.
The offending line was also rewritten to string concatenation, which removed the nested-quote
construct entirely.

**Consequence.** Worth knowing for the rest of the project: any agent generating Python through
a shell heredoc on this machine should assume the body is not fully literal and prefer a direct
write for anything containing quotes inside quotes.

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
rows is exactly the defect `seed_fixtures_present` is supposed to find, and asserting on the
field alone reports PASS. Deriving from documented columns is not re-encoding B's logic — it is
reading the schema the architecture file fixes, which is the same thing the console and engine
17 will do.

**Cost.** More code in the criterion, and it is now coupled to six documented column names. If
the lead approves a schema change, this criterion moves with it — which is correct, but it is a
maintenance edge that did not exist under the simpler design.

### A tick is `(run_id, cycle_id)`, and counting by `cycle_id` alone would have under-counted the seed

**Agent:** C · **Task:** spec 01 · **Date:** 2026-09-08

**What happened.** The first draft of the consecutive-`data_guard` counter in
`seed_fixtures_present` grouped block records by distinct `cycle_id`. B's schema message and
the lead's follow-up both landed before it ran, and both said the same thing: `cycle_id` is an
`INTEGER` minted per tick *within a run*, restarting at 1 with each process.

**Why it matters.** B's seed deliberately spans two `run_id`s and deliberately **reuses**
`cycle_id` values across them. Had the runs not overlapped, ordering by `cycle_id` would have
produced the same answer as ordering by `ts` and the entire point of the two-run fixture — that
the outage counter survives a restart — would have been unprovable. Grouping by `cycle_id`
alone would have collapsed the overlapping ticks together, under-counted an 18-tick outage run,
and reported a FAIL that was actually a bug in my query.

**Fix.** `_seeded_block_run()` keys every tick on the pair `(run_id, cycle_id)`, orders strictly
by `ts` with `rowid` as a tiebreak, and counts a tick once no matter how many guards blocked on
it. It also returns the number of distinct `run_id`s in the longest run and the number of ticks
inside it carrying more than one blocker, both of which the criterion now asserts — so the
two-run property and the one-tick-one-count property are proven rather than assumed.

### `docs_vocabulary` FAILs on a legitimate sentence, and the fix is not mine to make

**Agent:** C · **Task:** spec 02 · **Date:** 2026-09-08

**What happened.** The first real run of `docs_vocabulary` reported one hit:
`context/progress-tracker.md:76`, in `## Open Questions`, on the retired term `eight` — the
sentence "**Eight config values are trading behaviour that no context file specifies...**".

**Why.** The retired-term row reads `` `eight` used as a count of the engines without ML ``.
The backticks mark the token; the prose after them is a qualifier. My parser takes every
backticked span in the first column as a term and ignores the prose, so the check retires the
bare word `eight` everywhere in a scanned current-state file. Line 76 uses it to count config
values, not engines.

**Fix.** None by me, deliberately. Spec 02 forbids editing a context file to make the check
pass and says a hit goes to the lead, so it went to the lead with both readings written out and
a recommendation: change the table row's term to something distinctive such as
`` `eight engines` ``, which makes the qualifier part of the token and needs no code change at
all. Rewording line 76 fixes the instance; changing the row fixes the class.

**Consequence.** I built the over-broad reading on purpose. An over-broad check produces a
visible false FAIL that a human resolves in thirty seconds; an under-broad one produces a
silent PASS while the defect stands, which is the exact failure the sixth audit created this row
to stop. But the cost is real — the word "eight" is currently unusable in `AGENTS.md`,
`README.md` and `context/*.md` — and the lead should own that consequence rather than inherit it.
The check is FAILing in all nine phases at once, because `docs_vocabulary` is registered in every
one, so a single line is holding the gate for the whole project. That is the check working.

### The word-boundary rule in `docs_vocabulary` is load-bearing in three separate places

**Agent:** C · **Task:** spec 02 · **Date:** 2026-09-08

**What happened.** A naive substring scan for the retired terms FAILs the current tree three
times over, all of them false.

**Why.** `paper.starting_balance` is retired and `paper.starting_balances` is current, and the
retired string is a prefix of the live one — `trading-invariants.md:48` uses the plural in a
current-state section that is correctly scanned, so a prefix match fails the gate on the very
file that defines the rule. `eight` is a substring of "weight" (`trading-invariants.md:64`,
"ensemble weight") and of "Weight" (`ui-context.md:46`, a table header), and of "eighth"
(`ai-workflow-rules.md:64`, "the eighth audit"). All three are legitimate.

**Fix.** `term_pattern()` wraps each escaped term in `(?<![0-9A-Za-z_])` and `(?![0-9A-Za-z_])`,
applied only where the term actually begins or ends in a word character — so
`state["system_mode"]` gets a leading boundary and no trailing one, because it ends in `]`.
Matching is case-insensitive, which is what catches a stale `Chain 2` at the start of a sentence.

**Consequence.** Recorded because it is invisible from the code: three of the current tree's
files would fail this check under the obvious implementation, and a future maintainer who
"simplifies" the pattern to a plain `in` test will break the gate and not understand why.
