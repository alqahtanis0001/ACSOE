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
