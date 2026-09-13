# Build log — Phase 5 — a-platform

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is diagnosis-before-fix.** Write **What happened** and **Why** the moment you know why
something is broken, *before* you write the fix; come back and add **Fix** afterwards. The code
survives on disk whatever happens to the session; the reasoning that found it does not.

Minimum headings per entry: What happened, Why, Fix.

Two habits this project holds every entry to:

- **Break the code and watch the test go red**, then put it back, and say in the entry that you
  did. A test nobody has seen fail is a claim, not a check. A mutation that survives a *subset*
  of the suite has not survived — it has not been asked, so re-run survivors against the whole
  suite.
- **Record what you checked and found sound**, not only what you found broken. An audit that
  lists hits alone says nothing about coverage.

**Phase 5 fails quietly**, which is what makes the first habit the phase's governing rule
rather than a preference: a subtly wrong threshold, a leaked feature or a metric that flatters
produces a model that looks excellent and is worthless, with nothing red anywhere.

The lead consolidates these into `docs/build-log/phase-5.md` at phase close.

## Entries

### Two agents built spec 61 step 1 at once, and the tree went red on a name, not a defect

**Agent:** A · **Task:** spec 61 · **Date:** 2026-09-13

**What happened.** I landed the eight Phase 5 sections in `src/acsoe/platform/config.py`,
appended about 74 tests to `tests/platform/test_config.py`, and ran them: 143 passed, one
failed on an expected message I had written wrongly. I fixed that one line and re-ran, and the
suite had grown from 144 tests to 218 with a *different* failure, in a test called
`test_all_eight_phase_5_sections_parse` that I had never written. Roughly 420 lines of Phase 5
config tests had arrived in the same file between the two runs, from the other agent the lead
addresses as `A`, covering the same eight sections against the same config model.

**Why.** Two agents are claimed on one spec. Both blocks define a module-level constant named
`PHASE_5_SECTIONS`; mine is later in the file, so at call time the other block's
`phase_5_config_dict()` resolved *my* dict, whose test values differ from the ones its
assertions name. Nothing was wrong with either block on its own. `config.py` itself was never
in conflict — there is exactly one copy of every section and the docstrings are mine — because
the collision is in the file two people appended to, not in the file one person wrote.

**Worth noticing, because the path heuristic gets this one wrong.** `context/ownership.md`
resolves conflicts by *path*, and by path this failure is unambiguously mine: it is in my lane,
it names my file, and it reproduces every time. The heuristic is silent about the case where
two instances of the *same* owner are both inside the lane, which is the case here, and the
answer is not to trust the path and start deleting — the ownership map is the only concurrency
control this project has, and it is not designed for this.

**Fix.** Stopped editing the shared file rather than resolving over the other agent's work,
per the conflict procedure in `ownership.md`: escalated to the lead with the path and both
intents, messaged the other agent directly with the same facts, and proposed a split that
destroys nothing — their test block stays, I delete my own duplicate block and port across the
one case theirs does not cover, and I take steps 2 to 4 of the spec, which neither of us has
started.

**Consequence.** The one case I want kept is aimed at the lead's YAML paste and is the reason
the block is not simply redundant: an operator key written as `di_percentile: null` is
**refused at startup** by `_refuse_nulls`, which treats every null in `config/default.yaml` as
OPERATOR REQUIRED, while the same key left *absent* loads cleanly and reads as `None`. Absent
and null are one character apart in a diff and point in opposite directions, and the three
operator keys are required to be absent by spec 59 decision 9.

**Resolved** the same hour by the lead, who had the answer before I did: six teammate sessions
were live, three revived originals and three `-2` replacements, and the originals were stood
down. The other block was withdrawn and mine stayed. Nothing was lost to the collision itself.

### `git checkout --` restored a mutation and deleted the uncommitted work underneath it

**Agent:** A · **Task:** spec 61 · **Date:** 2026-09-13

**What happened.** Running the first mutation of the sweep, I used the one-line form this
project has used since Phase 3: hash the file, apply the mutation with `sed`, run the tests,
`git checkout -- <file>`, hash again, print both hashes. The mutation did its job — the target
test went red with `Failed: DID NOT RAISE ConfigError` — and then the two hashes disagreed.
They disagreed because `git checkout --` had restored `src/acsoe/platform/config.py` to
**HEAD**, and HEAD did not contain step 1. All eight Phase 5 sections, the cross-section
validator and the amended `Config.get` docstring were gone, in a single command, with no
warning and an exit code of zero.

**Why.** `git checkout -- <path>` restores from the index, and the work was **uncommitted**:
teammates do not commit on this project, the lead commits at spec boundaries, and step 1 had
not reached one. The Phase 4 build log already carries the near-miss version of this — a
cross-lane mutation run against two files that were untracked, where the hash check was the
only safety net there was — and the rule written from it was "verify a cross-lane mutation
restored, by hash, in the same statement that applied it". That rule caught this one. What it
did not do, and what I had not thought through, is that **on this project `git checkout --` is
not a restore at all**: with the lead committing at spec boundaries, a teammate's working tree
is routinely the only copy of hours of work, so the *restore mechanism itself* is what destroys
it. The hash check told me afterwards; it could not prevent it.

It was worse than it looked for a second reason that had nothing to do with me. The lead had
pasted the Phase 5 YAML block minutes earlier, so `config/default.yaml` now carried eight
sections that the reverted model did not declare — and every section is `extra="forbid"`. For
the few minutes the revert stood, the committed config did not parse, which is every test in
every lane.

**Fix.** Re-applied the whole of step 1 from the edits in my own transcript, verified the
committed config loads, and then — since the YAML had landed in the meantime — closed the
second half of the landing by tightening all eight sections from `Section | None = None` to
required. The tightening was not opportunism: my own
`test_the_phase_5_sections_are_landing_in_two_halves` had gone red the moment the YAML
appeared, which is exactly what that test exists to do, and the fix for it is the tightening.
Collapsed that test and one other to the closed state afterwards, because a branch for a world
that can no longer happen is a claim nobody is checking.

**Consequence, and it is a standing rule rather than a note on this incident.** For the rest of
this phase a mutation is applied against a **byte copy** taken in the same statement and
restored from that copy, never from git:

    cp <file> <scratch>/<file>.orig && sed -i '<mutation>' <file> && pytest ... ; cp <scratch>/<file>.orig <file> && sha256sum both

`git checkout --` may be used only on a file whose current content is known to be committed,
and on this project that is a much narrower set than it looks. The three-question path
heuristic from Phase 4 has a fourth question in front of it now: *is the thing I am about to
restore from actually a copy of what is there?*

### A test for a default that the fixture supplied, found by the one mutation that survived

**Agent:** A · **Task:** spec 61 step 1 · **Date:** 2026-09-13

**What happened.** Nine mutations against `platform/config.py`, eight killed and one survivor:
changing `ScoutConfig.rank_descending`'s default from `True` to `False` broke nothing. The test
that exists to pin it, `test_an_absent_rank_feature_returns_none_and_the_direction_defaults_true`,
stayed green while the default was the opposite of what it asserts.

**Why.** The test loads a config built from `PHASE_5_SECTIONS`, and that overlay carries
`"scout": {"rank_descending": True}`. So the value the assertion read was the one the fixture
had just written, and the field default was never on the path at all. It is the same shape as
the Phase 3 finding about a hand-built `state["exchange"]` that agreed with its caller, and the
Phase 4 one about a tripwire that constructed its own empty client set: **the test pinned a
fact it supplied**, so nothing about the code could move it. The shipped `config/default.yaml`
sets the key explicitly too, which is why this would never have surfaced in ordinary use — and
is exactly what makes it worth having: the default is what applies the day the lead omits the
key, and until now nothing checked what it was.

**Fix.** Assert the default against a config whose `scout` section omits `rank_descending`
entirely, and keep a separate assertion that an explicit `false` is honoured, so the test can
tell "the default is True" from "the file said True".

**Consequence.** Worth stating because it is the second time in two phases the same question
has had to be asked of a green test: before asserting a default, check whether the fixture
supplies the value. The mutation is what asks it; reading the test is not.

### The same collision from the other side, and why "delete the duplicate" is not a safe instruction

**Agent:** A, the instance whose messages route as `A`; the entry above is `A-2`'s ·
**Task:** spec 61 · **Date:** 2026-09-13

**What happened.** I am the other half of the entry above. I read every context file, found
step 1 of spec 61 already implemented in `src/acsoe/platform/config.py` with no tests beside
it, and wrote a test block for it — the one whose `test_all_eight_phase_5_sections_parse` the
entry above reports arriving mid-run. Running it, `features.version` came back `test-v0`
against my `v1`. Two module-level constants named `PHASE_5_SECTIONS` in one file; the later
definition wins for every function in the module, so **the other block's tests were silently
being driven by my values and mine by nothing that was ever intended.**

**Why that is the interesting half.** Only one of the eighteen assertions was sensitive enough
to the substitution to notice. The rest of both blocks stayed green while reading a dict
neither author wrote. A duplicated module-level constant does not collide loudly in Python —
it shadows, and the tests carry on asserting against the wrong subject. That is the same shape
as a double that cannot exhibit the property under test: green, and evidence of nothing.

**Fix.** Deleted **my own** block, lines 839 to 1259, keeping the earlier one intact, then
re-ran: `144 passed in 2.19s`. Nothing was lost by choosing that direction — the surviving
block is the stronger of the two and covers three things mine did not: the null-versus-absent
refusal for each operator key, the `BAD_VALUES` table matching every refusal on its
**constraint** rather than on the key name, and the two-halves assertion that goes red if the
lead's YAML paste lands without the sections being tightened to required. The only case of
mine not already covered there is a boundary one, `min_lookback_fill` of exactly 1 accepted,
and it is not worth a second edit to a file two agents are inside.

**The part that is a standing hazard, not a fixed bug.** The entry above proposes the opposite
split — that the earlier author deletes *their* block and keeps mine. Both of us acting on our
own plan deletes both blocks and leaves step 1 with no tests at all, green, in the phase whose
governing rule is that it fails quietly. **A conflict resolved independently by both parties is
not resolved.** Messaged the lead and the other instance with the exact disk state rather than
with an intention, and stopped writing to shared files until the lane is assigned.

### numpy's stubs abort `mypy --strict` at the 3.11 floor, and the fix is `numpy<2.5`, not `<2.3`

**Agent:** A · **Task:** spec 61 step 2, from C's escalation · **Date:** 2026-09-13

**What happened.** C reported that a direct `import numpy` anywhere in `src/` makes
`mypy --strict src/ scripts/` report nothing at all, and asked me to verify two things it had
not: that numpy 2.2's stubs parse under 3.11, and that the installed model libraries tolerate
the downgrade. Reproduced exactly:

```
.venv\Lib\site-packages\numpy\__init__.pyi:737: error: Type statement is only supported in
Python 3.12 and greater  [syntax]
Found 1 error in 1 file (errors prevented further checking)
```

Exit code 2. **"errors prevented further checking" is the whole defect**: the gate returns no
answer rather than a wrong one, which is the failure mode the existing override comment in
`pyproject.toml` already describes and which has now arrived through a second route.

**Why the existing override does not cover it.** C's diagnosis is right and I could not fault
it. `module = ["numpy", "numpy.*", ...]` with `follow_imports = "skip"` governs what mypy does
*after* parsing a module it reached by following a chain. A module named outright in a checked
file is found and parsed regardless, and numpy 2.5.3's `__init__.pyi` carries **65** PEP 695
`type` statements, which are a syntax error at `python_version = "3.11"`. The override has held
since Phase 2 only because nothing in `src/` had yet needed numpy by name.

**What I measured, and the one place C's recommendation is wrong.** C recommended pinning
`numpy<2.3`. The bound is stricter than it needs to be. Unpacking the wheels for 2.2.6, 2.3.0
and 2.4.0 and searching all 127 stub files in each found **zero** PEP 695 `type` statements in
any of the three, and running the project's own config at `--python-version 3.11` against each
reported `Success: no issues found` — so the syntax arrived in 2.5, and **`numpy<2.5` is the
accurate bound**. Pinning two minor versions further back than the defect requires is not free:
it is two versions of bug fixes given up, in the library the DI's distance arithmetic runs on.

Every installed package's declared floor is satisfied by 2.4.x, read from `Requires-Dist`
rather than from `pip show`, which prints the names without the specifiers: lightgbm
`>=1.21.3`, scikit-learn `>=1.24.1`, shap `>=2`, scipy `>=2.0.0,<2.8`, statsmodels
`>=1.23.5,<3`, hmmlearn `>=1.10`, numba `>=1.22,<2.6`, pandas `>=1.26.0`. Nothing demands 2.5.

**The predicted benefit does not follow from the pin, and this is the part worth keeping.** C
expected that pinning would also stop numpy being `Any`, so the distance arithmetic would be
type-checked rather than exempt. It will not, on its own: `follow_imports = "skip"` keeps numpy
`Any` at *every* version, which is exactly what the control run shows — the same probe that
errors on a bare `np.ndarray` with the override lifted reports `Success` with it in place. The
benefit needs a **second** change, narrowing the override to polars only, and that one is not
free either: it surfaces the real numpy types across every module that uses them at once. Two
changes, two decisions, and only the first is needed to unblock C.

**A measurement artefact that nearly became a finding.** My first run against the 2.2.6 stubs
reported 5,182 errors, almost all `Unused "type: ignore"` inside numpy's own stubs, and it
looked like evidence that the downgrade traded one broken gate for another. It was an artefact
of how I had extracted the wheel: I unzipped `*.pyi` only, so `py.typed` was missing and mypy
stopped treating numpy as an installed typed package and stopped silencing errors inside it.
Re-extracting the full tree gave `Success`. Same shape as the reversed-order benchmark rule in
`code-standards.md` — plausible, in range, and pointing the wrong way — and the thing that
caught it was re-running the comparison a second way rather than believing the first number.

**Fix.** Not mine to land: the other instance in this lane has claimed step 2 and is going into
`pyproject.toml` for the dependency move anyway, and C's own note asks for both edits in one
pass rather than two. Handed over the verified bound and the reasoning instead of editing the
file underneath it. **The pin alone does not clear the gate** — `pyproject.toml` is a
declaration and mypy reads the *installed* numpy, so the venv needs the downgrade too, and that
is a shared-environment change that lands on B and C mid-run. Asked the lead to sequence it
behind a team stop rather than doing it unilaterally, for the same reason the phase's gate runs
are sequenced that way.

### Correction: the numpy pin was not needed, and all four of us had missed the option that was

**Agent:** A · **Task:** spec 61 step 2 · **Date:** 2026-09-13

Rule 6 of `script-rules.md` — a new entry, not an edit to the one above.

**What happened.** While I was verifying the pin and asking the lead to schedule a shared-venv
downgrade, `A-2` landed one line in `pyproject.toml` and the gate came back:

```
$ .venv/Scripts/python.exe -m mypy --strict src/ scripts/
Success: no issues found in 106 source files
```

numpy is **still 2.5.3** in the venv and `modelling/di.py` still imports it. The line is
`follow_imports_for_stubs = true`, added to the existing numpy-and-polars override.

**Why it works, and why nobody reached it.** `follow_imports = "skip"` silences a module's
*source* and not its *stub*, so the `.pyi` was still being parsed and the PEP 695 `type`
statement inside it still aborted the run. `follow_imports_for_stubs` extends the skip to the
stub. It changes no policy — numpy and polars were already deliberately `Any` here — and it
keeps the 3.11 floor, which is the thing every option on the table had been trading away.

**The part I got wrong, stated plainly.** My own entry above lists three ways out, quoting the
override comment that has named the same three since Phase 2, and I verified one of them
carefully instead of asking whether the list was complete. C did the same and so did the comment
I was reading. **Every one of us treated an enumeration written for a different purpose as
exhaustive.** The measurements I took are all sound — the bound really is `<2.5` rather than
`<2.3`, and the libraries really would tolerate it — and they answered a question that did not
need asking. Careful verification of an unnecessary option is still wasted, and it is a more
expensive mistake than a sloppy check of the right one, because it produces confidence.

**Withdrawn immediately:** the request to the lead to schedule a `pip install "numpy<2.5"`
behind a team stop. It would have downgraded a shared venv under B and C for nothing. That
withdrawal is the reason this entry exists rather than waiting for the end of the task.

**Checked before reporting it fixed**, because a gate that has just come back from reporting
nothing is exactly the one to distrust: `mypy --strict src/ scripts/` exits 0 and names **106**
source files, not a smaller number, so it is checking the tree rather than skipping it; the
override's scope is the numpy and polars block alone; and `modelling/di.py` is still importing
numpy by name, so the trigger has not simply been removed.

### `mypy --strict src/` checked nothing at all for several hours, and said `Found 1 error`

**Agent:** A · **Task:** spec 61 step 4 · **Date:** 2026-09-13

**What happened.** Running the gate after wiring `acsoe research`, `mypy --strict src/ scripts/`
reported a single error in `.venv/Lib/site-packages/numpy/__init__.pyi:737`: *Type statement is
only supported in Python 3.12 and greater*, followed by *errors prevented further checking*.
Not one file of `src/` was checked. Narrowing the run to my own lane
(`src/acsoe/cli/ src/acsoe/platform/ scripts/`) reported success on 33 files, which is what
made it clear the abort was not mine and not a broken environment.

**Why.** `[[tool.mypy.overrides]]` has carried `follow_imports = "skip"` for `numpy` and
`polars` since Phase 2, and the comment beside it says exactly why: numpy's bundled stubs use
PEP 695 `type` statements, which mypy treats as a **syntax error** under
`python_version = "3.11"`, this project's declared floor, and a syntax error inside a followed
import aborts the whole run. `skip` silences a module's *source* and **not its stub**. Every
module in `src/` reached numpy through polars until today, which the existing override
happened to cover; C's `modelling/di.py` (spec 63) is the first to write
`import numpy.typing as npt`, and a submodule import loads the parent package's stub directly.
So a correct, ordinary import in another agent's lane turned off a gate in mine.

It is the Phase 4 lesson in its purest form: **a wrong answer that is in range survives; this
one was worse, because the answer was "1 error" and the truth was "no answer".** The file named
is in `.venv/`, so it reads as an environment problem — something to shrug at and re-run —
rather than as the definition of done having quietly stopped meaning anything for three agents.

**Fix.** Added `follow_imports_for_stubs = true` to the same override block. It extends the
existing skip to the stub file, which is what the comment already claimed was happening, and it
changes no policy: numpy and polars were deliberately `Any` here already. `mypy --strict src/
scripts/` now checks **106 source files** and passes. Written up in `pyproject.toml` beside the
three ways out that were raised with the lead in Phase 2 — bump the floor to 3.12, pin
`numpy<2.3`, or keep the override — because this is a fourth that keeps the 3.11 floor, and the
floor is the promise `requires-python` makes.

**Consequence.** Worth one line in anyone's checklist: `mypy` printing a small number of errors
is not evidence that it checked what you think. Read the file count it reports. The gate that
says `Found 1 error in 1 file` and the gate that says `Success: no issues found in 106 source
files` differ by everything.

### Decision: `acsoe research` runs the engines itself rather than through the orchestrator

**Agent:** A · **Date:** 2026-09-13

**Options.** Spec 61 step 4 asks for a command that runs each offline engine's `process` against
a real replay-mode context. Two ways to get one: reuse `core/orchestrator.py`, which already
builds an `EngineContext`, converts a raised engine into `ERROR` and records results; or run the
chain directly in `cli/research.py`.

**Chose.** Run it directly, in a `run_offline_chain` function separate from the CLI entry point.

**Because.** The orchestrator's unit of work is a *tick* — it mints a `cycle_id`, carries
`state["system"]` across ticks, consumes commands, and runs three chains one of which must never
break early. None of that exists offline: the chain runs once, there is no persistent state, no
command table and no manage chain. Reusing it would mean inventing a tick for something that has
none, and `core/` is the lead's, so shaping it around a research runner is not a change A may
make anyway. The cost of running the engines here is one thing that has to be re-implemented
rather than inherited: contract rule 7, an uncaught exception becoming `ERROR` instead of a
traceback. That is eleven lines and it has its own test, because a research run whose engine
raised, whose traceback went to the terminal and whose exit code was zero is exactly the quiet
failure this phase is about — anything driving the command from a script would record it as a
success.

**Cost.** Two implementations of "turn an exception into ERROR" in the repository. Mitigated by
keeping the offline one small and by asserting it directly: `ExplodingEngine` in
`tests/cli/test_entrypoints.py` exists for no other reason.

### Decision: engine 20 resolves by name, so there is no registration line to forget

**Agent:** A · **Date:** 2026-09-13

**Options.** Engine 20 `tournament` is C's and does not exist yet. Either leave a commented slot
in `OFFLINE_CHAIN` and add the import the day C's class lands, or resolve the class by name at
chain-build time so it registers itself.

**Chose.** Resolve by name, with a test that pins the two legal states.

**Because.** The slot is a to-do item in someone else's head, and Phase 4 has the matching scar:
engine 23 was built against a labeller signature agreed by message, C's module landed under a
different name, and **nothing went red** because every test drove a double. A slot has the same
shape — the day the class lands, the chain silently stays one engine long, `acsoe research`
reports a clean run, and the leaderboard is simply never written. Resolving by name removes the
step that can be forgotten.

Two failure modes are made loud rather than silent, and both were deliberate:

- `except ModuleNotFoundError` cannot distinguish "C has not written it" from "C wrote it and
  one of its imports is missing". The handler reads `exc.name` and re-raises anything that is
  not C's own package, because answering the second as "not registered yet" is how engine 20
  would vanish from the chain the first time it had a bad import.
- The constructor keyword `digest_path` is the seam spec 74 states and I have agreed by message.
  If C's signature differs, chain building raises a `RuntimeError` naming the seam and saying to
  agree the keyword rather than change one side. A fallback to `factory()` would be the Phase 4
  defect again, in the one place I already know it can happen.

**Cost.** `build_offline_chain` now does an import-machinery lookup, so `scripts/verify.py`'s
`is_gate_matches_registry` will raise rather than skip if C's class is present and unconstructable.
That is the intended direction: loud, in a criterion C owns, rather than a quietly short chain.

### The tripwire for engine 20 cannot be built out of `importlib`

**Agent:** A · **Task:** spec 61 step 4 · **Date:** 2026-09-13

**What happened.** The test that pins the two legal states of the offline chain asked
`importlib.util.find_spec("acsoe.engines.tournament.engine") is not None` to decide which state
it was in. It raised `ModuleNotFoundError: No module named 'acsoe.engines.tournament'` instead of
returning `None` — and the same call inside `cli/research.py` raised for the same reason, so the
whole `acsoe research` test group was red.

**Why.** `find_spec` returns `None` for a missing *leaf* module, but it **imports the parent
package** in order to search it, so a missing parent raises. There is no
`src/acsoe/engines/tournament/` at all, which is the state this project is in until spec 74 lands
— the state the code exists to handle.

**Fix.** In `cli/research.py`, catch `ModuleNotFoundError` around `find_spec` and use `exc.name`
to tell C's absent package from a genuine broken import. In the test, stop asking `importlib` at
all and ask the filesystem whether `src/acsoe/engines/tournament/engine.py` exists.

**Consequence, and it is the more useful half.** The test now has an oracle that does not share
machinery with the code under test. Asking `importlib` both times would have been a test that
agrees with the implementation by construction — including when both are wrong, which is exactly
what had just happened: implementation and test raised the same exception for the same reason,
and the test could never have caught it. This is the "a seam exercised only through something the
author also wrote is not tested" rule arriving in a form that looks like an ordinary helper.

### `acsoe research` over the full archive holds 39 GB and takes six times as long as one pair predicts

**Agent:** A · **Task:** spec 61 step 4 · **Date:** 2026-09-13

**What happened.** Spec 61's acceptance check is `acsoe research --config config/default.yaml`,
so I ran it against the committed 859,248-bar archive. It is correct — it runs, it is CPU-bound
at 98%, nothing has failed — but at 33 minutes elapsed it had used 1,945 CPU-seconds and held
**39.6 GB** of resident memory, still climbing. The same command against a 400-bar scratch
archive finishes in seconds and exits 0, which is the bounded evidence the spec asks for; this
entry is about the other run.

**Why — as far as measurement goes, and no further.** I measured rather than guessed, because
the obvious suspect was C's labelling seam and blaming it would have been wrong:

| subject | bars | peak tracked memory | per bar | time |
|---|---|---|---|---|
| `label_frame` (C) | 5,000 / 10,000 / 20,000 | 9.4 / 18.6 / 37.1 MB | ~1.95 KB | — |
| engine 23 `process` (A) | 10,000 / 20,000 / 40,000 | 33 / 56 / 112 MB | ~2.9 KB | 2.6 / 8.2 / 16.9 s |
| engine 23 `process` (A) | 80,000 then 40,000 | 229 / 112 MB | ~3.0 KB | 35.6 / 16.9 s |

Both are **linear per pair**, in memory and in time: doubling 40,000 to 80,000 doubles both.
The third row is the same measurement **run in reverse order**, which is the control this project
requires of a benchmark after a Phase 4 result that reported a fourfold speed-up and was really
measuring a cold cache: 40,000 bars came back at 16.87 s against 16.94 s forward, so the numbers
are the change and not the machine.

That linearity is what makes the full run a finding. At 0.44 ms and 3 KB per bar, 859,248 bars
projects to **about six minutes and 2.5 GB**. The real run is at 33 minutes and 39.6 GB. So the
difference is not in labelling one pair and it is not in scale alone — something in the
multi-pair path diverges from the single-pair path, and the candidates are the merged replay
stream across three pairs and the accumulation of every labelled row before the single parquet
write. Also worth noting: `tracemalloc` accounts for ~2.5 GB of an order of magnitude more
resident, so most of what is held is allocated outside Python's own allocator — polars and
arrow buffers — which is where I would look first.

**Fix.** None here, deliberately. Engine 23 is mine, from Phase 4, and spec 61's scope is the
config fields, the dependencies, the models root and a research runner that runs; rewriting the
replay's memory behaviour inside a spec about wiring is exactly the widening the Scope Limits
section exists to stop. Reported to the lead with these numbers so it can be scheduled, and
recorded here so the next person does not start from "it feels slow".

**Consequence, and it is the part that matters for Phase 5 rather than for me.** The dataset
every model in this phase trains on comes out of this command. A run that holds 39 GB and grows
is one an operator can start on a smaller machine and lose an hour to, and the failure mode when
it runs out is a killed process rather than a message. Worth knowing before spec 67's
walk-forward is run for real, not after.

### Closing note on the full-archive run: 51.9 GB at session close, and I could not stop it

**Agent:** A · **Task:** spec 61 step 4 · **Date:** 2026-09-13

**What happened.** The full-archive `acsoe research` run described in the entry above kept
growing for the rest of the session. Three readings, all taken with `Get-Process`: 35.7 GB at
roughly 25 minutes, 39.6 GB at 33 minutes, **51.9 GB at 36 minutes** with 2,089 CPU-seconds
burned and **19.7 GB free on a 96 GB machine**. It never printed a line and never wrote a
parquet. Growth is close to half a gigabyte a minute and shows no sign of levelling.

**Why this is a different fact from the entry above.** That entry reported a performance
finding: the multi-pair path diverges by an order of magnitude from a per-pair measurement that
is linear in both time and memory. This one is about the machine. Three agents were working in
this checkout, and a process consuming memory at that rate is the environment-level version of
the hazard `code-standards.md` already records for mutation harnesses — one lane's work turning
another lane's run red, by a mechanism invisible from inside the second lane. A pytest run that
fails on a `MemoryError` names nothing useful and looks like a defect in whatever was being
tested.

**Fix.** None available to me. I tried to stop the process and the action was refused by the
permission layer as interference with a workload, which is a reasonable default and was the
wrong answer here — the process was mine, started by me, producing nothing anyone needed.
Recorded in the progress file with the PID and a plain instruction to kill it, because the
next person to read that file is the only one who can.

**Consequence, and it is the one I would want the next session to take.** The acceptance
evidence for spec 61 step 4 came from a **400-bar scratch archive** that exits 0 in seconds,
not from this run, and that was the right call for a reason worth stating: a check whose
runtime is unbounded is not a check anyone will run twice. The full-archive run was worth
starting once, as the honest end-to-end proof — and what it proved was not what I started it
for.

### CORRECTION: the full-archive run finished, exit 0, and my diagnosis of it was wrong

**Agent:** A · **Task:** spec 61 step 4 · **Date:** 2026-09-13

**What happened.** The run completed while I was writing the wind-down, after about 36 minutes:
`backtest OK`, **exit 0**, and a 429 MB parquet at
`data/derived/labelled_research-20260913T000430950753_20260913T004003Z.parquet`. So spec 61's
acceptance check — "`acsoe research --config config/default.yaml` runs engine 23 and exits 0" —
is proven against the committed config and the real archive, not only against the 400-bar
scratch run.

Then I read the output's metadata and the two entries above turned out to be wrong.

**Why.** I had been reasoning from a number I carried over from Phase 4: that
`data/historical/` held **three** pair files and **859,248** bars, which is what I built and
recorded there on 2026-09-11. It holds **234 CSVs and 20,443,861 bars** today — 47 GB — and the
labelled output is **20,331,237 rows over 13 columns**. Nobody told me the archive had grown by
a factor of twenty-four and I never checked; I measured the code carefully and then compared it
against a stale fact about the data.

With the real row count the arithmetic closes almost exactly. My per-pair measurement was
~3 KB of tracked memory per bar and it was *right*: 20.3M rows at that rate is about 60 GB, and
the process peaked at 51.9 GB. **There is no anomaly in the multi-pair path.** Engine 23
accumulates every labelled row of every pair in one Python list and writes a single parquet at
the end, so its memory is linear in total rows — and the total is now twenty million.

Runtime lands the same way: 2,089 CPU-seconds for 20.3M rows is ~0.10 ms per bar, *faster* per
bar than the 0.44 ms my small slices measured, because those slices paid fixed per-pair setup
over a few tens of thousands of rows. The earlier entry's "six minutes and 2.5 GB" projection
was arithmetic applied to the wrong N.

**Fix.** None to the code, and the correction narrows the real problem rather than dissolving
it. The accumulate-then-write shape is still the thing to change before spec 67 — at 20M rows
it needs ~50 GB of RAM to produce a 429 MB file, which is the whole of a large machine for an
output that would stream — but it is now a known, ordinary defect with an obvious fix (write
per pair, or append row groups) rather than a mysterious divergence somebody has to go hunting
for. That is a much cheaper piece of work to schedule, and it belongs in its own A spec over
`research/backtest.py`.

**Consequence, and it is the reason this entry exists rather than an edit to the one above.**
Two of this project's own rules caught me from opposite sides and I noticed neither in time.
*"A wrong answer that is in range survives"* — 39 GB was alarming but plausible, so I explained
it instead of checking the input. And the control I did apply, running the benchmark in reverse
order, was sound and proved the per-bar numbers honestly; it simply could not detect that I was
multiplying them by the wrong N. **A control on the measurement says nothing about the
assumption the measurement is being compared against.** The cheap check I skipped was `ls
data/historical/*.csv | wc -l`, against a directory I had written a table about in my own
progress file three days earlier.

The lead has already carried the wrong version into `feature-specs/PHASE-5-TASKS.md` under
"What the next session would otherwise rediscover". It needs replacing with this, and the lead
has been told.

### The `training` section shipped with two of its four bounds unchecked, and a mutation said so

**Agent:** A · **Task:** spec 61, the `training` section · **Date:** 2026-09-13

**What happened.** Landed `TrainingConfig` — `num_trees`, `learning_rate`, `num_leaves`,
`min_data_in_leaf` — with a parse test, a `num_leaves: 1` refusal test and the two-halves
landing test, all green. Then ran the mutations. Loosening `learning_rate` from `gt=0, lt=1` to
`ge=0, le=1` **broke nothing**: 158 passed with the constraint gone.

**Why.** The section had tests for the two things I had thought about — that the values parse
to the right types, and that a single leaf is refused — and no row in the `BAD_VALUES` table,
which is where every other section's bounds are actually checked. So three of the four fields
had constraints that nothing asked about. It is the ordinary version of the rule this file
keeps re-learning from a different direction: **a test written because the author found the
case interesting is not coverage of the cases that matter.** `num_leaves` got a test because
its failure mode is a good story; `learning_rate` did not, because "it is a ratio" felt
self-evidently handled.

**Fix.** Seven rows added to `BAD_VALUES`, covering all four fields at both ends where both
ends exist. Re-ran: `learning_rate` loosened now kills three parametrised cases, `num_trees`
loosened kills two, and making the section required kills 39 — which is the other half of the
landing proof, since the optional state is what keeps the committed config parsing until the
lead pastes the YAML.

**Consequence.** Worth stating as a habit rather than a fix: when a section lands, add its row
to the constraint table first and write the interesting test second. The table is mechanical
and complete; the interesting test is neither.

### Spec 78: the slice streams per pair, and a measurement that printed 0.0 four times

**Agent:** A · **Task:** spec 78 · **Date:** 2026-09-13

**What was changed.** `BacktestEngine.process` no longer builds a list of every labelled
row of every pair. It asks each pair's frame for its `height` — the counts were all it ever
needed — and hands the frame straight to a `_SliceWriter` that appends it to the parquet as
its own row group. One pair is alive at a time; `del labels, series` at the end of each
iteration is the whole of the fix, and the rest is making that safe.

Three things in it are not obvious and each has a reason:

- **The schema is established by the first pair and every later pair is cast to it.**
  `label_frame` builds `pl.DataFrame(payload)` per pair, so polars infers dtypes *per pair*,
  and a column that is entirely null for one thin pair infers as `Null` where another pair
  has `Int64`. Measured across five real archive pairs and all five agree — evidence about
  the common case, not a guarantee about the 234th. A parquet file needs one schema, so the
  choice is cast or crash, and a cast that cannot be done raises naming the pair rather than
  writing a row group whose types quietly disagree with the rest of the file.
- **The writer is closed in a `finally`**, so a run that raises part-way leaves a readable
  parquet of the pairs that finished instead of a file with no footer.
- **The report and the file are cross-checked.** `slice_writer.rows_written` must equal the
  sum of the per-pair counts, and a disagreement raises. It can only fire if a later edit
  lets a pair be counted and not written, or written and not counted — which is exactly the
  kind of drift that would otherwise be discovered by a trainer reading a dataset whose
  stated size is a lie.

**Also fixed, in the same function, because it was in the way.** `_write` stamped the slice
filename with `datetime.now(tz=UTC)` — a direct clock read inside an engine, which invariant 9
forbids without qualification. It cannot bias a label, it only names a file; but "it is only a
filename" is the argument that puts the second one somewhere that matters, and reading
`context.now` makes a replay's output name reproducible from its inputs. The path convention
is unchanged.

**A mypy override I added and then took back out.** pyarrow ships no `py.typed`, so importing
it under `--strict` is an `import-untyped` error. I added `"pyarrow.*"` to the ignore list in
`pyproject.toml`, which turned two lines in B's `clients/store/parquet.py` red — because the
project runs `warn_unused_ignores` and a global override makes an existing local ignore an
error rather than removing the need for it. B had written exactly that, in a comment above
those two lines, explaining why the ignore was deliberately local. **The reason was already on
disk, two lines above the thing I broke.** Reverted, and the same local ignore used here.

**The measurement, and the mistake in it.** Spec 78 asks for peak memory before and after,
compared in both orders. The first harness read the peak through
`ctypes.windll.kernel32.K32GetProcessMemoryInfo` with no `argtypes` and no `restype`, so the
call failed and returned nothing, and the function reported **0.0 MB** — which it printed,
four times, for two different implementations, and I read past it. `windll` defaults make a
failed call indistinguishable from a process that used no memory. Declaring the prototypes and
raising on a false return gave real numbers:

| run order | accumulate | stream |
|---|---|---|
| accumulate first | 792.9 MB | 430.3 MB |
| stream first | 800.1 MB | 404.1 MB |

24 pairs, 214,511 labelled rows, ~11.5 seconds either way. The order swap moves the numbers by
under 7% and does not move the conclusion, which is the control this project requires after a
Phase 4 benchmark that measured a cold cache and reported a fourfold speed-up.

**A zero is the one reading that should never be believed**, and this is the second time in
two days that the failure mode has been "the harness answered, and the answer was not a
measurement". The Phase 4 rule was about a wrong answer that is in range; this is the
complement — an answer so far out of range that it reads as a formatting problem rather than
as a broken instrument.

**Mutations, restored from byte copies and verified by sha256.** Iterating `report.pairs`
reversed kills only the new order test — which is the gap it was written for, since every
other test counts rather than orders. Adding one to each pair's reported height kills four,
including the report-versus-file cross-check. Writing each table twice kills three. All three
restored.

### Engine 3's `missing_bars` is not ambiguous across pairs — with more than one pair it is empty

**Agent:** A · **Task:** the engine 3 assessment the lead asked for · **Date:** 2026-09-13

**What happened.** C-2 reported that `state["market_sensor"]["missing_bars"]` pools every pair,
so no consumer can tell which pair has the hole. That is true, and measuring it against the
real functions rather than reading them turned up something sharper.

`MarketSensorEngine` calls `missing_bar_timestamps(closed_candles, interval_s=...)` over the
candles of **every** subscribed pair at once, with no `pair=` argument. That function takes the
set of timestamps present, spans first to last, and reports the bar openings absent from the
set. The set is a union, so a bar is only "missing" when **no pair traded in it at all**.

Measured with two pairs, one of them missing bars 2 and 3:

    pooled missing_bars : []
    per-pair AAAUSD     : []
    per-pair BBBUSD     : [2, 3]

And with the holes staggered — each pair silent in a bar the other traded in:

    pooled  : []
    per pair: AAAUSD [2], BBBUSD [1]

**Why that matters more than attribution.** The field does not merely lose *which* pair; past
a handful of pairs it loses the signal. The archive directory now holds 234 pairs. A live
system subscribed to anything like that number will have some pair trading in essentially
every fifteen-minute bar, so `missing_bars` is empty on essentially every tick — and
`data_guard`'s missing-candle block, one of its three conditions, can then never fire. What
protects the tick against absent candles in practice is the staleness threshold, alone.

**Why nothing went red.** The seam is tested by neither side, which is a pattern this build log
has now recorded three times in two phases. Engine 3's gap tests all use a **single pair**
(`BTC/USD`), where union and per-pair readings are identical, so they cannot see it.
`data_guard`'s tests construct `missing_bars` themselves as a tuple of timestamps, so they
prove the gate blocks on a value the test supplied and never ask whether the producer can
produce one. Each side is correct about itself and the pair of them agrees about nothing.

**Fix.** None written. The lead's instruction was to assess and propose without changing a
cross-chain key, and the proposal is in the message to `main`: engine 3 should **not** grow a
per-pair map, because spec 64's amendment already has engine 5 counting each pair's holes from
that pair's own candles — which engine 3 already publishes, each carrying its `pair` — and a
second producer of one fact is the thing this project keeps paying for. What is worth deciding
is separate and is not mine: whether `data_guard`'s missing-candle condition still means
anything at 234 pairs, and whether the field should say what it actually measures, which is
"bars in which no subscribed pair traded at all".

### Spec 78's result: 51.9 GB to 23.6 GB, and the remaining floor is the reader, not the writer

**Agent:** A · **Task:** spec 78 · **Date:** 2026-09-13

**What happened.** The full 234-pair archive through the streamed engine: **20,331,237 rows**,
peak **23.6 GB**, 31 minutes. Against the accumulating run recorded in the Phase 5 handoff —
the same 20,331,237 rows at a peak of 51.9 GB — that is the same dataset for 45% of the
memory. The labels are identical, not merely the count:

| | rows | target | stop | timeout |
|---|---|---|---|---|
| accumulated (before) | 20,331,237 | 4,857,764 | 10,424,046 | 5,049,427 |
| streamed (after) | 20,331,237 | 4,857,764 | 10,424,046 | 5,049,427 |

(The target rate falls out at 23.89%, which is the base rate spec 59 decision 4 quotes. Nice
to see the document and the data agree.)

**Spec 78's Check When Done asks for "well under a tenth of 51.9 GB" and this is not that.**
The target is about 5 GB and the run peaked at 23.6. The gap is measured rather than guessed,
and it is not in the part spec 78 changed: **`ArchiveReplay` holds the whole archive in memory,
twice, before labelling starts.** `__init__` keeps `self._rows` — every pair's parsed rows as
Python dicts — *and* `self._frames`, the same data again as polars frames, both eagerly, both
for the life of the run. Engine 23 reads only `frame(pair)`; `_rows` exists for `bars()`, which
the backtest never calls.

Measured on a 24-pair scratch archive, each run in its own process, both orders:

| | accumulate | stream | reader alone |
|---|---|---|---|
| accumulate first | 792.9 MB | 430.3 MB | 348.6 MB |
| stream first | 800.1 MB | 404.1 MB | 350.3 MB |

The reader alone is 81% of the streaming peak. That is the floor under anything the writer
does, and reaching spec 78's number means making the reader lazy — load one pair's frame when
it is asked for, release it after, and stop keeping a second copy nobody in this path reads.
That is `research/replay.py`, which is A's, and it is **not** in spec 78's Implementation
steps, so it is reported rather than done.

**One difference in the artefact, found by looking rather than by a test.** The first full
streamed run produced a 667 MB parquet where the accumulating one produced 429 MB, for
byte-identical rows: `polars.write_parquet` defaults to zstd and `pyarrow.ParquetWriter`
defaults to snappy. Nothing downstream reads the codec, and a slice that quietly grows by half
is still a change to the artefact made by an implementation detail rather than by a decision.
Pinned to zstd, and a test now asserts both the codec and one row group per pair — the latter
being what makes a selective read cheap, since parquet's per-group column statistics let a
reader skip every pair but the one it wants. Dropping the `compression="zstd"` argument turns
that test red; restored by byte copy, sha256 verified.

**Worth noticing about the spec.** Its Implementation steps and its Check When Done disagreed,
and only measuring showed it: the steps describe the writer and the acceptance number can only
be met by also changing the reader. Neither is wrong on its own. Writing the number the change
actually achieves, and why, is the honest answer; quietly widening the change to hit the number
would have been the other one.
