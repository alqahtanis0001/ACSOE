# Build log — Phase 6 — c-interface

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is diagnosis-before-fix.** Write **What happened** and **Why** the moment you know why
something is broken, *before* you write the fix; come back and add **Fix** afterwards. The code
survives on disk whatever happens to the session; the reasoning that found it does not.

Minimum headings per entry: What happened, Why, Fix.

**Rule 2, carried from Phase 5 and not retired with it:** every assertion is proven capable of
failing, and the proof goes here. Name the mutation, quote the red message, and say the file was
restored from a byte copy with its hash compared in the same statement that applied it. A claim
that an assertion works is not evidence. A mutation that survives a *subset* of the suite has not
survived — it has not been asked. An equivalent mutant is a checked negative, not a survivor.

**What Phase 6 is, and what that changes about these entries.** Phase 5 built components that
can be wrong while looking right. Phase 6 connects them to money: engines 9, 14, 16, 18, 21 and
22, and the fill simulator. For the first time the whole chain runs end to end, which means two
things for this log. First, **every number Phase 5 produced was measured on one gate in
isolation** — the skeptic's lift, the DI's refusal rate, the anomaly block rate — and this is the
phase that finds out what they are worth in sequence, after friction. Second, the manage chain
holds real positions, so a defect here costs money rather than a metric. Record what you checked
and found *sound*, not only what you found broken: an audit that lists hits alone says nothing
about coverage.

Three things from Phase 5 that will be in someone's way here, so they are written down rather
than rediscovered:

- **Engine 8 publishes `is_buy: false` when it refuses**, so its payload cannot distinguish "no
  call" from "not a BUY". It is an open item for this phase, it is not a fail-open today because
  engine 8's own `BLOCK` stops the tick, and it moves together with engine 15's read of that
  field. `expected_move_pct` is the field that got this right: omitted from the payload on a
  refusal, so the consumer fails closed on an absent key rather than on a value it must interpret.
- **50.2% of out-of-sample rows carry an incomplete feature vector** and engines 8 and 13 refuse
  those at any threshold. A chain that produces few candidates is that number showing up, not
  necessarily a defect.
- **At tier 1 nothing clears the cost gate, by construction** — the hurdle needs an expected move
  above 3.125% and the target barrier is 3.0%. Zero trades at tier 1 is these numbers interacting
  exactly as specified, and is not a bug to chase.

## Entries

### Engine 8's `is_buy` said "not a BUY" when it meant "no call"

**Agent:** C (engines and models) · **Task:** spec 95 · **Date:** 2026-09-16

**What happened.** `PredictionState.is_buy` was declared `is_buy: bool = False` and
`to_state()` published it unconditionally, so all six of engine 8's refusal shapes —
`prediction_unavailable` in its six forms, `prediction_inputs_incomplete`, `di_refused`,
`di_percentile_mismatch` — put `is_buy: false` into `state["prediction"]`. That is the
identical payload a predictor publishes when it ran, scored, and called no BUY. Found by
C-4 during spec 73's mutation sweep on engine 15 and carried out of Phase 5 as an open
item.

**Why.** It is the same design question `expected_move_pct` had already answered the other
way in spec 71, and only one of the two fields got the answer. A pydantic field with a
non-`None` default is published on every path by construction: there is no code in engine
8 that *decides* to publish `is_buy: false` on a refusal, which is why nothing looked
wrong at any call site. The default did it.

Nothing failed open in between, and that is worth being precise about rather than
generous: engine 8's own `BLOCK` stops the opportunity chain under contract rule 6, so the
tick never reached engine 15 at all; and when engine 15 *is* handed such a payload
directly, its spec 73 hardening blocks, because that read is three-way (`bool` or block)
rather than two-way. The cost was to the record, not to the money — `block_records` and
the research dataset could not distinguish two different facts — and to the next reader.
Engine 14 `adaptive_router` (spec 97) is the first consumer of this field that is not a
gate, which is why the operator scheduled the fix before it rather than after.

**Fix.** `is_buy: bool | None = None` in `engines/prediction/contracts.py`, with
`to_state()` omitting the key when `None` in the same shape as `expected_move_pct`, and
`IS_BUY_FIELD` declared beside `EXPECTED_MOVE_FIELD`. Engine 8 needed no logic change:
every refusal already routes through `_blocked`, which takes no `is_buy` argument and so
cannot set one, and the single `OK` return sets it from `is_buy_call(move)` on a model
that has already scored. **The property is stated as a property of the signature** — the
way to break it is to add an `is_buy` parameter to `_blocked`, and there is no reason to.
That is the M4 mutation below.

Engine 15's read did **not** change and must not: the block it returns on a non-`bool`
`is_buy` landed in spec 73, a phase before the payload did, and it is the reason nothing
failed open in the meantime. What changed is its sentence. It used to say "engine 8
published no usable BUY verdict … and no way to know there was none", which was true when
the absence was uninformative; now the absence *is* engine 8's way of reporting a refusal,
so the sentence names which of the two happened and distinguishes the absent case from the
present-but-unusable one. The two READMEs and both contracts modules carry the same
distinction.

**Consequence.** One wording decision worth recording, because it nearly created a test
that could not fail. The first draft of engine 15's new sentence ended "This is not a
non-BUY call; a non-BUY is an explicit false" — and `NOT_A_BUY_CALL` is the literal string
`"not a BUY call"`. The obvious regression assertion is `NOT_A_BUY_CALL not in reason`, and
against that draft it passes for an accidental reason: `"not a BUY call"` is not a
substring of `"not a non-BUY call"`, by four characters. An assertion whose truth turns on
a near-miss of the literal it is checking is one edit away from silently inverting. The
sentence was reworded to avoid the phrase entirely, and the assertion is in both engine-15
tests.

**Why the tests are shaped the way they are.** Spec 95's check is *every refusal shape*,
which is a claim a list of examples cannot make on its own. `refusal_shapes` in
`tests/engines/test_prediction.py` drives ten shapes end to end through the real engines 3,
5 and 6 and the real artefact loader, and a second test asserts that the reason codes those
ten reach are **exactly** the set of `REASON_*` constants the contracts module declares —
the same enumeration `tests/console/test_reason_prose.py` already uses to require operator
prose. A fifth code added tomorrow turns that test red until a shape reaching it joins the
list, which is the part that makes "every" checkable rather than aspirational.

The two scored cases are asserted on their **sign**, not assumed. The fixture window that
`predicted` uses is the one the chain rehearsal calls `NOT_A_BUY_WINDOW_END`, where the
fixture model's expected move is negative; the BUY control runs on the window 200 bars
earlier. Both tests assert the sign before asserting `is_buy`, so a retrained fixture that
moved either answer turns the affected test red by name instead of leaving a branch green
and unreached — the same protection B built into the rehearsal for the same two windows.

And the seam gets one test with no double on either side:
`test_a_refusing_engine_8s_real_payload_blocks_naming_the_absence` induces a real
`di_refused` out of the real engine 8 and hands that payload to the real engine 15. Spec 95
is a change to what engine 8 *publishes*, and Phase 4 found twice in one day that mutating
a module's own logic does not test the fields it exports.

### Spec 95 — four mutations, four killed, and which test killed each

**Agent:** C (engines and models) · **Task:** spec 95 · **Date:** 2026-09-16

**Harness.** `scratchpad/mutate.py`. Every arm runs a **baseline first** and refuses to
report if the tree is already red. The target file is copied to the scratchpad *before*
the mutation and restored from those bytes with `sha256` compared **in the same statement
that writes it back** — never `git checkout --`, because teammates do not commit and that
restores the committed version over their uncommitted work. Every anchor is asserted to
occur **exactly once** in the file before it is replaced. Every file that is not the
variable is hashed on both sides of the arm and the hashes are printed with the result,
because three sessions share this checkout and without that an A/B here measures whichever
save was on disk. All four arms reported `witness files unchanged: True`.

**The arm** is `tests/engines/test_prediction.py`, `tests/engines/test_skeptic.py` and
`tests/engines/test_feature_chain_rehearsal.py` — the two files spec 95 changes plus B's
Phase 5 rehearsal, which is the only other place `state["prediction"]["is_buy"]` is read.
352 tests. **Directories deliberately excluded and why:** the rest of `tests/`, because
nothing else in the repository reads this key — checked by grep across `src/`, `tests/`,
`scripts/` and `console/` — and because the full suite was red in another lane throughout
(see the entry below). Every verdict here is a KILL, and a kill on a subset is a kill; no
survivor is being claimed on a subset, which is the direction the rule guards.

| | Mutation | Verdict | Killed by |
|---|---|---|---|
| M1 | `is_buy: bool \| None = None` back to `is_buy: bool = False` — spec 95's first named one | KILLED | `test_no_refusal_shape_publishes_is_buy`, `test_a_refusing_engine_8s_real_payload_blocks_naming_the_absence` |
| M2 | `to_state` emits the key as `null` instead of omitting it — spec 95's second | KILLED | the same two |
| M3 | engine 15 reads an absent verdict as a non-BUY — spec 95's third | KILLED | 8 tests, listed below |
| M4 | `_blocked` hands `is_buy=False` to `PredictionState` explicitly, leaving the contract alone | KILLED | the same two as M1 |

**M1's red message**, which is the defect in its own words:

```
AssertionError: the no run id configured refusal published is_buy=False, which is the
payload of a predictor that ran and called no BUY
```

**M2's**, showing that null is caught as well as false — the point of omitting rather than
nulling:

```
AssertionError: the no run id configured refusal published is_buy=None, which is the
payload of a predictor that ran and called no BUY
```

**M3 is the one worth reading.** It restores the pre-spec-73 fail-open exactly: the
three-way read collapsed to a truthiness test, so absent, `None` and `0` all take the
not-a-BUY `OK` path. Eight tests went red —
`test_an_is_buy_that_is_not_a_boolean_blocks_rather_than_reading_as_non_buy` in all six
of its parametrisations, `test_a_candidate_with_no_prediction_published_blocks_rather_than_passing`,
and the new seam test. The seam test's message is the whole finding in one line:

```
AssertionError: assert <EngineStatus.OK: 'OK'> is <EngineStatus.BLOCK: 'BLOCK'>
  ... data={'pair': 'AAAUS..., 'vetoed': False, 'reason': 'not a BUY call', ...}
```

A tick on which engine 8 refused, reported by the last gate as a call the predictor made
and did not like. That is what spec 95 and spec 73 between them prevent, and it is worth
noting which half does the preventing: **engine 15's block is what stops it, not engine
8's omission.** The omission makes the payload honest; the three-way read is the safety.
Removing either leaves the other holding — removing both is M3 plus M1 together, and
nothing would object.

**M4 is the mutation the contract change alone does not cover**, and it is the reason the
"no `is_buy` parameter on `_blocked`" property is worth stating out loud rather than
leaving as an accident of the current code. With `is_buy: bool | None = None` still in
place, a refusal path can publish a verdict simply by passing one, and the field's type
gives no warning. It is killed by the same two tests, which is the answer to "is the
contract change on its own enough" — no, and the behavioural tests are what cover the gap.

**Equivalent mutants, reported as checked negatives rather than survivors.** None was run.
The two obvious candidates are not equivalent and are covered above; there is no third
edit to this field that leaves behaviour unchanged.

### One red test at the spec 95 gate, and it is not spec 95's

**Agent:** C (engines and models) · **Task:** spec 95 · **Date:** 2026-09-16

**What happened.** `tests/console/test_real_rows.py::test_every_reason_code_engine_19_can_write_is_in_the_map`
fails: *"Left contains 2 more items, first extra item: `entry_resting_on_pair`"*.

**Why.** B's spec 89 added `REASON_ENTRY_RESTING_ON_PAIR` and `REASON_POSITION_OPEN_ON_PAIR`
to `engines/risk/contracts.py`, and spec 89 step 6 hands both codes to C's spec 99 for
operator prose in `console/format.py`. Spec 99 is the **verification-and-interface** half
of lane C, not this session — the task list splits lane C into disjoint files precisely so
two sessions never touch `console/format.py` at once. So this is a seam mid-flight between
two specs, doing exactly what the seam was designed to do: a code with no prose renders
"No reason was recorded." silently, and that test is the thing that stops it being silent.

I applied the three questions `code-standards.md` puts under "it is in another agent's path
is evidence, not a verdict", because a path heuristic that is right three times in four is
how the fourth case hides. Does it name my file? No — `engines/risk/contracts.py` and
`console/format.py`, neither mine. Does it reproduce every time? Yes. Is it caused by a
string I just wrote? No: `grep -rn entry_resting_on_pair src/ tests/` finds it in B's
contracts module and B's test only, and nothing in spec 95 touches a reason code at all.

**Fix.** Not mine to make. Reported to the lead for spec 99. Recorded here because it is
the reason `toolchain_green` cannot be green on this tree, and the next person to run the
gate should not spend the diagnosis twice.

### The DI paid for the whole reference set once per scored row

**Agent:** C (engines and models) · **Task:** spec 102 · **Date:** 2026-09-16

**What happened.** `di.score` costs about 1.13 ms a row at the test suite's sizes and about
136 ms a row at the full run's reference size, and the leave-one-out over a 200,000-row
reference takes roughly twenty minutes of one core. It is the test suite's largest single
cost at 3.1 s per trained fold, and every Phase 6 gate run pays it six times.

**Why — the time.** `_mean_nearest` computes `np.sum(reference**2, axis=1)` **inside its
chunk loop**, and `score()` calls it with a single query row. `research/training.py::_fit_di`
then scores the fold's test rows one at a time in a Python `for`. So each scored row squares
and sums the entire reference matrix: at the full run's size that is 200,000 x 117 float64,
about 187 MB allocated, written and read, **per row**. The k-nearest search the function
exists to do is O(N) on a vector of 200,000 distances and costs a fraction of that. The cost
is therefore linear in reference size for a reason that has nothing to do with the statistic
being computed, which is why it did not look wrong: every individual piece of that function
is the right arithmetic, and the only thing wrong is where the loop boundary sits.

**Why — the memory, which is the half that will not merely be slow on a smaller machine.**
The leave-one-out builds its exclusion mask as
`np.abs(decision_ts[None, :] - stamps[:, None]) <= exclusion_s`. At `_CHUNK = 512` against a
200,000-row reference that is an 819 MB int64 intermediate plus a 102 MB boolean, allocated
391 times, beside an 819 MB float64 distance block and an 819 MB squared block. The twenty
minutes is very unlikely to be the matrix multiply — 200,000² x 117 is about 4.7 TFLOP, which
a threaded BLAS does in a couple of minutes — and much more likely to be four gigabyte-scale
allocations per chunk starving it.

**Why it has not bitten yet.** The committed fixtures are small: the suite's reference sets
are in the low thousands of rows, where 187 MB becomes 2 MB and the whole defect reads as
"the DI is a bit slow". The full-archive numbers in the goal are the ones that make it a
prerequisite, and they came from a run nobody had a reason to profile until the gate started
paying for it six times.

**Fix.** Four changes, all arithmetic-preserving; the scope limit forbids touching k, the
percentile, the window, the exclusion, the scaler or what is refused, and none of these does.

1. The reference norms are computed **once per call** rather than once per chunk. Same
   values, same order, fewer times.
2. A batched `score_many(fitted, matrix)` chunking query rows against a **fixed element
   budget** rather than a fixed row count, so peak memory is a property of the reference
   size and not of how many rows are being scored. `research/training.py` calls it; engine 8
   keeps `score` for its single live vector and `score` delegates to the same code path, so
   the offline and live readings cannot drift — the same reason spec 72 narrowed one scaler
   rather than writing the arithmetic twice.
3. The pairwise-timestamp mask is replaced by the `searchsorted` bounds `fit` already
   computes for its own too-short-reference check: the excluded columns are a contiguous
   range in timestamp-sorted order, so they are set to infinity by index. **The set of
   excluded columns is identical by construction** — the same two bounds, in exact integer
   arithmetic — so this change is bit-for-bit rather than merely close, and the reference's
   own column order is untouched.
4. The partition runs on **squared** distances and the square root is taken of only the k
   selected. `sqrt` is monotone and correctly rounded, so the k smallest squared distances
   are the k smallest distances, their roots are the same floats, and sorting ascending
   before the mean puts them in the same summation order.

**The one place equivalence is not bitwise, stated rather than discovered.** Change 2 turns
a one-row GEMV into a many-row GEMM, and BLAS is entitled to associate differently. DI values
may move in the last few ulp. Spec 102 anticipates this and asks for a stated tolerance
justified in the docstring; the tolerance is measured rather than picked, and **refusals are
asserted identical with no tolerance at all**, because the refusal is the only thing anything
downstream can see. The residual risk — a row sitting within a few ulp of the threshold could
in principle flip — is inherent to any reassociation and is recorded here rather than left
for someone to find.

**Deliberately not written: a whole-run per-fold memory test.** Spec 102 says so and the
reason is worth repeating, because the absence otherwise looks like an omission. The
skeptic's training set grows every fold by design — it is the accumulation of every earlier
fold's out-of-sample BUY calls — until prerequisite 1 is ruled under spec 83. A test
asserting per-fold memory is flat cannot be green today, and one written against the capped
methodology would be a test of a methodology the operator has not chosen.

### Spec 99, first increment — the two spec 89 codes, and the red they trade for

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**Diagnosis, written before the fix.** `tests/console/test_real_rows.py::test_every_reason_code_engine_19_can_write_is_in_the_map`
fails with *"Left contains 2 more items, first extra item: `entry_resting_on_pair`"*. The
enumeration walks `acsoe.engines.risk.contracts` for `REASON_*` string constants and finds two
that `REASON_PROSE` does not carry: `position_open_on_pair` and `entry_resting_on_pair`, both
added by B's spec 89 (`contracts.py:182` and `:192`). Spec 89 step 6 hands the prose to spec 99,
which is this session. `C-models` diagnosed the same failure independently at the spec 95 gate
and correctly declined to fix it; the entry above this one is that diagnosis, and this is the
same fault seen from the owning side.

**It is the seam working, not a surprise.** A code with no entry in the map renders
"No reason was recorded." with no exception, no log line and no visibly degraded screen — the
one genuinely silent failure the console has, and the reason the enumeration exists. It went
red within a day of B landing the constants, which is the whole return on that test.

**The wording is B's, kept verbatim.** `position_open_on_pair` -> "This pair already holds an
open position"; `entry_resting_on_pair` -> "This pair already has an entry order resting on the
book". Same arrangement as engines 4, 7, 10 and 11: the producer writes the sentence and the
consumer does not paraphrase it, so the two cannot drift. Two sentences rather than one because
B's contract note is explicit that the two states are cleared by different actions — a position
is exited, an order is cancelled — and the operator reading the rejection row needs to know
which. `test_no_two_codes_share_a_sentence` would refuse one shared sentence anyway, which is
the same ruling enforced from the other end.

Neither sentence carries a number, a threshold or a cause, per spec 46: engine 11 writes prose
with the actual figure and `operator_reason` prefers the row's own text over this table.

**This deliberately turns a second test red, in B's lane.**
`tests/engines/test_risk.py::test_the_two_codes_spec_89_added_are_still_waiting_on_cs_prose`
asserts the codes are *absent* and is written to fail the moment C lands; its own failure
message says to move them into the renderable list and delete the tripwire. That file is B's
and I did not edit it. Reported to the lead and to B in the same breath as the fix, so the tree
is never red without somebody knowing which red is which.

### The gate list went red because a document changed, which is the arrangement working

**Agent:** C (verification and interface) · **Task:** spec 99 / housekeeping · **Date:** 2026-09-16

**What happened.** `tests/verify/test_phase0_criteria.py::test_is_gate_parses_the_registry_out_of_the_document`
fails on a clean tree:

```
AssertionError: assert {'anomaly', '...'safety', ...} == {'anomaly', '... 'scout', ...}
  Extra items in the left set:
  'decision'
```

**Why.** The operator ruled engine 16 `decision` a gate on 2026-09-16 (ruling 2), and the lead
put the **Y** into the Gate column of `context/engine-contracts.md` under spec 80. That test
does not read a list of gates from anywhere — it parses the registry table out of the document
and pins the parsed result against seven names written out by hand. The hand-written set is the
point. `verify.py`'s `is_gate_matches_registry` criterion checks that each *registered engine's*
`is_gate` attribute agrees with the document, so the document is the authority for everything
downstream of it; nothing else in the suite would notice if the document itself grew a gate. So
one test holds the document to a set a human has to retype, and widening the gate list is a
deliberate act with a red test in front of it — including when the lead is the one widening it.

**Fix.** `decision` added to the expected set, eight names now. The test keeps its shape: it
still parses, still asserts 23 rows, still spot-checks `data_guard` as a gate and `exchange` as
not one, and still compares against an enumerated literal rather than against anything derived
from the document. Making it derive the set from the same table it is checking would turn it
into a tautology that can never fail, which is the one change that must not be made here.

### The walk over every engine found four silent codes, and two are a phase old

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**What happened.** `tests/console/test_reason_prose.py` grew the walk spec 99 asks for — import
every `acsoe.engines.*.contracts`, collect every module-level `REASON_*` / `HOLD_*` string
constant, require each value to be a key of `REASON_PROSE`. It went red on its first run naming
four codes:

```
AssertionError: these engines publish a code with no operator prose, so it renders
'No reason was recorded.' on the console, silently:
engines/position_manager/contracts.py::HOLD_DATA_GUARD_BLOCKED = 'data_guard_blocked',
engines/position_manager/contracts.py::REASON_POSITION_UNRECORDABLE = 'position_unrecordable',
engines/regime/contracts.py::REASON_NO_FEATURE_ROW = 'no_feature_row',
engines/regime/contracts.py::REASON_NO_INPUTS = 'regime_inputs_incomplete'
```

**Why, and why the two halves are different findings.** The two from engine 21 are expected:
B landed them under spec 92 yesterday and B's own contracts module says *"Flagged to C for
`REASON_PROSE` (spec 99)"*. The seam worked as designed.

**Engine 12 `regime`'s two are the finding.** They have been on disk since Phase 5 and nothing
noticed, because until now this file enumerated one module per test and there had never been a
test named after engine 12. That is the exact failure spec 99 predicts in the abstract — "the
existing enumeration walks gates, and none of 9, 14, 18, 21, 22 is a gate" — turning up in a
place nobody listed: engine 12 is not a gate either, it is a phase old, and it was already
live. Six single-module tests written one per engine cannot catch the seventh engine; that is
not a property of the engines, it is a property of listing things by hand.

They render as silence rather than as a code, which is worth being exact about because the two
failures look different on screen. Engine 12 writes the bare code into `reason` and publishes no
`reason_code`, so `operator_reason("", "no_feature_row")` takes the `_CODE_LIKE` branch — the
stored text is recognised as a code and refused, the map lookup is on an empty string, and the
operator gets "No reason was recorded." on the one field whose job is to say why the market was
not classified. Engine 14 `adaptive_router` is about to read `state["regime"]["label"]` under
spec 97, so the tick where the label is `null` is about to matter more than it did.

**Fix.** Four sentences in `REASON_PROSE`. Engine 21's two are **my wording, not B's** — B is
not running and the precedent is already in this file for `no_fx_rate` and
`barriers_below_tick_size`, added the same way with B asked to replace them if wrong. Engine 12's
two are mine because engine 12 is lane C's and `C-models` is not running either. All four obey
spec 46: no number, no threshold, no cause the row did not carry.

`data_guard_blocked` is the first **hold** reason to get a sentence, and it is deliberately not
written as a refusal. Nothing was rejected; the manage chain declined to compute a barrier from
data the guard had already refused, and the position is still being watched. An operator told
"blocked" would go looking for a fault, so the sentence says what is paused and what is not.

**Two things the walk had to be built not to do**, both of which would have made it green and
useless:

- **Pass on an empty walk.** `unmapped == {}` is satisfied by reading nothing at all, and
  `pkgutil.iter_modules` returning nothing is a plausible accident. So the import-system answer
  is compared against an independent filesystem scan for `engines/*/contracts.py`, five engines
  that certainly exist must be in it, and four codes that certainly exist must have been
  collected out of it.
- **Exempt a real code by shape.** Three constants carry the `REASON_`/`HOLD_` prefix and are
  *not* codes: `memory.REASON_CODE_FIELD`, `memory.HOLD_REASON_FIELD` and
  `position_manager.HOLD_REASON_FIELD`, all naming a place in `state` rather than a value. The
  codebase convention is `*_FIELD`/`*_KEY`/`*_PATH` for a location, and skipping on that suffix
  alone is a rule a future real code could satisfy by accident — `REASON_TIMEOUT_FIELD` would
  vanish from the map with nothing to notice. So the inventory is pinned exactly and a fourth
  such constant turns the suite red and gets a decision. **Raised with the lead as a convention
  question**, per spec 99 step 5: both modules belong to other agents and the scope limit forbids
  renaming somebody else's constant to suit this test.

`BLOCK_REASON_KEY = "block_reason"` in `engines/memory/contracts.py` is the near miss that needed
no rule: it contains "REASON" but starts with neither prefix, and it names a location, so it is
out of scope rather than exempted.

**The inverse, as spec 99 step 4 asks, is a warning and not a failure.** Five prose keys no
engine publishes today — `insufficient_depth`, `meta_label_veto`, `no_candidate_cleared`,
`outlier_market_state`, `outside_universe`. Four are the seed generator's older spellings on
seeded rows that still have to render, and `insufficient_depth` is engine 9's, which does not
exist yet. Pinning that list would make it fail for cosmetic reasons on somebody else's change;
warning makes a retired code visible without that.

### Spec 99 — five mutations, five killed, and which test killed each

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**Harness.** `scratchpad/mutate_99.py`, `mutate_99b.py` and `mutate_99c.py`. Every arm runs a
**baseline first** and refuses to report if the tree is already red. The target is copied to the
scratchpad *before* the mutation and restored from those bytes with `sha256` compared **in the
same statement that writes it back** — never `git checkout --`, because teammates do not commit
and that would restore the committed file over their uncommitted work. Every anchor is asserted
to occur **exactly once** before it is replaced. Four files that are not the variable are hashed
on both sides of every arm and printed with the result. All five arms reported
`witness files unchanged: True` and `restored exactly: True`.

**The arm** is `tests/console/test_reason_prose.py` alone, 118 tests. Nothing else in the
repository reads `REASON_PROSE`'s completeness — `tests/console/test_real_rows.py` reads the map
but for engine 19's subset, and it was green throughout. Every verdict below is a KILL; no
survivor is claimed on a subset, which is the direction the rule guards.

| | Mutation | Verdict | Killed by |
|---|---|---|---|
| A | An unmapped `REASON_A_CODE_NOBODY_MAPPED = "tournament_fold_count_changed"` added to `engines/tournament/contracts.py` | KILLED | `test_every_code_every_engine_publishes_has_operator_prose` **and** `test_every_reason_code_tournament_declares_has_prose` |
| B | The same, in `engines/regime/contracts.py` — an engine with **no** per-module test | KILLED | `test_every_code_every_engine_publishes_has_operator_prose`, alone |
| C | `CODE_PREFIXES` mistyped to `("REASONS_", "HOLDS_")`, so the walk reads every module and collects nothing | KILLED | `test_the_walk_collects_codes_and_not_merely_modules`, `test_the_state_field_constants_are_pinned_rather_than_exempted_by_shape`, `test_the_inverse_is_reported_as_a_warning_and_never_as_a_failure` |
| D | The walk iterates an empty list instead of `pkgutil.iter_modules` | KILLED | `test_the_walk_reaches_every_engine_on_disk`, plus the three above |
| E | One entry dropped from the pinned `STATE_FIELD_CONSTANTS` inventory | KILLED | `test_every_code_every_engine_publishes_has_operator_prose`, `test_the_state_field_constants_are_pinned_rather_than_exempted_by_shape` |

**A and B are the same mutation in two places, and the difference between them is the finding.**
A is killed twice, because engine 20 already had a per-module test written when engine 20
landed. B is killed **once**, by the walk:

```
AssertionError: these engines publish a code with no operator prose, so it renders
'No reason was recorded.' on the console, silently:
engines/regime/contracts.py::REASON_A_CODE_NOBODY_MAPPED = 'regime_model_absent'.
Add a sentence to REASON_PROSE in src/acsoe/console/format.py.
```

Without the walk that mutation survives the entire suite, and survives it *silently* — which is
precisely how engine 12's two real codes sat unmapped for a phase. A mutation killed only by the
new test is the only kind of evidence that the new test was worth writing.

**C and D are the vacuous-pass arms**, and they are the ones a walk most needs. Both leave the
headline assertion green — nothing collected means nothing unmapped — and both are caught by the
guards instead:

```
AssertionError: the walk and the filesystem disagree about which engines exist;
only imported: []; only on disk: ['anomaly', 'cost', 'data_guard', 'exchange', ...]
```

**E proves the exemption inventory is load-bearing rather than decorative.** Drop
`("memory", "REASON_CODE_FIELD")` and the walk immediately demands prose for `reason_code` —
which is the *name of a column*, not a code. That is the shape of the mistake the pinning
prevents in the other direction too: a real code named `REASON_SOMETHING_FIELD` skipped by a
suffix rule nobody had to think about.

**Equivalent mutants, reported as a checked negative rather than a survivor.** One was
considered and not run: widening `CODE_PREFIXES` to include a prefix no engine uses
(`("REASON_", "HOLD_", "REFUSAL_")`) changes nothing today and would be equivalent by
construction rather than by test weakness. It is recorded here because "no survivors" is only
meaningful if the arms that could not have survived are named.

### `Path.write_text` rewrote every line of a file it was not asked to change

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**What happened.** After appending the walk to `tests/console/test_reason_prose.py` with a short
Python script, `git diff --stat` reported 250 changed lines in a file I had added 250 lines to —
which looked right — but `git diff` warned *"CRLF will be replaced by LF the next time Git
touches it"*, and a byte count showed **663 CRLF and zero LF**. The same had happened to
`docs/build-log/phase-6/c-interface.md`.

**Why.** `Path.write_text` opens in text mode, and on Windows text mode translates every `\n` to
`\r\n` on the way out. Reading a LF file and writing it back through `write_text` therefore
rewrites every line in the file, not only the ones that changed. `.gitattributes` in this repo
is `* text=auto eol=lf` precisely because line endings are evidence here — every committed
fixture is compared byte for byte by `verify.py` — so a working tree quietly converted to CRLF
is the class of thing that file exists to prevent.

It also corrupted two mutation arms before it was noticed: the harness's mutant step did
`write_text` on an already-CRLF string, producing `\r\r\n`, and pytest's line numbers in those
runs came out roughly doubled. The *verdicts* were unaffected and the restores were exact —
the restore path uses `write_bytes` and compares sha256 — but the evidence was not clean, so
arms C and D were re-run on the corrected file and the table above is from that run.

**Fix.** Both files converted back with `write_bytes(data.replace(b"\r\n", b"\n"))`; `git diff`
now shows insertions only. The mutation harness writes mutants with `write_bytes` as well, so a
mutant differs from its original in exactly the anchor and nothing else — which is what the
witness-hash check was already claiming and could not previously have caught, because the
witnesses are the files the arm does *not* touch.

**Consequence.** Any script in this repository that edits a tracked file must write bytes, not
text. `B`'s `engines/risk/engine.py`, `engines/risk/README.md` and `tests/engines/test_risk.py`
are CRLF in the working tree right now for what is very likely the same reason; that is B's lane
and is reported rather than fixed here.

### Spec 100 — the nine criteria registered while every one of them is PENDING

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What this entry is for.** Registering criteria is routine and would not belong here.
Three things about *these* are not routine, and two of them are defects the tests caught
in the criteria themselves.

**The first draft judged the wrong repository, and the test found it.** Every Phase 6
criterion looked up its engines with `try_import`, with no `root_import_path(ctx.root)`
around the body. That is not an import-hygiene nicety: `ctx.root` is the entire reason a
criterion takes its repository as a parameter, and without the context manager the nine
criteria imported the **installed** `acsoe` regardless of which tree they were pointed
at. On this machine that is the same repository, so all nine reported plausibly and the
defect was invisible — a criterion that always reports on the developer's own checkout
is exactly the fresh-clone failure the rule exists to prevent, wearing the costume of a
passing criterion.

It was found by the two tests in `tests/verify/test_phase6_criteria.py` that fabricate a
subject into a copied tree and ask what the criterion thinks: both reported "does not
exist yet" about a module sitting in the tree they had just written it into. Every check
now opens `with root_import_path(ctx.root):` before it looks anything up, which is what
every criterion from Phase 1 onward already did.

**An absent fixture and an empty one are different faults, and only one is PENDING.**
Absent means nobody has cut it yet: a schedule fact, and the owning spec is named.
**Empty is a FAIL**, because a deposited file carrying nothing reads downstream as "the
walk found no levels" or "the leaderboard has no models" — the vacuous pass this project
has been burned by three times. Both branches are driven to a verdict in the tests
rather than described, because `_phase6_fixture`'s FAIL branch is otherwise unreachable
until spec 96 deposits something, and a branch nobody has executed is a comment.

The same distinction one level up: an engine module that imports and declares no engine
class gets its own sentence rather than "does not exist yet". A PENDING that sends
somebody to write a file already sitting there is worse than no PENDING, and this phase
opened on exactly that state in another lane — `modelling/di.py` naming `score_many` in
`__all__` and not defining it.

**A test that could not tell its own rule from a violation of it, twice.**
`test_no_criterion_reads_data_models_or_logs` reads the Phase 6 section of `verify.py`
and checks that no criterion reaches into a gitignored directory. The first version
searched the text for `data/`, `models/` and `logs/` and went red on the section's own
prose explaining why it must not read them. The second stripped comments and strings
with `tokenize` and searched the code, which is worse in two ways at once: it drops the
string literals a path is actually built from, and `data_guard` matches "data" in an
identifier — so it reported a violation where there was none and would have missed a
real one. The third parses the section and searches **non-docstring string literals**,
which is what a path is, with a guard that at least one path literal was found so the
search cannot pass vacuously. Recorded because the wrong two versions both looked right.

**Why all nine are PENDING and why that is the deliverable.** Engines 18 and 22 are B's
and unbuilt, engines 9 and 14 are `C-models`'s and unbuilt, and neither committed fixture
is cut. A criterion exists so it can report PENDING, and PENDING is what stops a phase
with nothing in it looking finished — `--phase 6` carried `docs_vocabulary` and
`toolchain_green` alone until this landed and would have printed "Phase 6 is green" over
a phase in which nothing had ever placed an order. Each PENDING names the engine by
number, the spec that owes it, and the fee regime it will run in when it does.

### The fee tier is named once, in a fixture, because four files had already copied it

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** Ruling 8 requires every trade-driving criterion to run at fee tier 3
and to say so in its own message. Before writing them I looked at how tier 3 was already
being set, and found `set_fee_tier(tier=3, maker_fee_pct="0.0011", taker_fee_pct="0.0019")`
typed out by hand in four test files — B's paper broker tests, B's engine 21 tests, A's
engine 1 tests and the harness's own.

**Why that is a problem specifically here.** Nothing was wrong with any of the four. But
"tier 3" is about to become a claim that appears in a verdict the operator reads, and
four hand-typed copies of a pair of decimal strings is four opportunities for two
criteria to mean different things by the same sentence — silently, because both numbers
are plausible and neither is checked against anything.

**Fix.** `tests/fixtures/kraken/fee_tiers.json` names the tiers, `fee_tier_profile(tier)`
reads them, `FakeKrakenClient.use_fee_tier(tier)` applies one **and returns the profile
it applied**, so the tier a criterion reports and the tier it ran at are one object
rather than two statements that happen to agree. `tier_sentence(tier)` is the clause the
criteria embed, and it lives beside the profile for the same reason.

Five properties are asserted rather than assumed, and three of them are the ones a typo
breaks. The named tier 1 is pinned **equal to `trade_volume.json`'s default envelope**,
so the fake's default tier and its named tier 1 cannot disagree — "no trade at tier 1"
would otherwise mean two different things depending which route a test took. An unnamed
tier **raises** rather than falling back to tier 1, because a fake kinder than reality
hides fail-closed bugs and a silent fallback would give a criterion a no-trade regime
while its message said otherwise. And tier 3's fees are asserted lower than tier 1's on
both sides: a tier-3 profile carrying tier-1 numbers would leave every Phase 6 criterion
in the no-trade regime while reporting that it was not, and every one of them would
simply find no candidate — a whole phase of criteria passing for the wrong reason.

Not asserted, deliberately: the friction and the hurdle. Those are engine 10's
arithmetic, and a criterion that recomputed them here would be checking its own sum.
`fees_round_trip_pct` exists and its docstring says in as many words that it is **not**
the friction the gate hurdles against.

**One more, and it is the standing rule rather than a new one.**
`test_no_fee_number_in_the_fixture_reaches_src` searches `src/` for the literal strings,
not for the filename. `AGENTS.md` is explicit that a fee percentage in `src/` is stale by
definition, and the way one gets there is not by importing a fixture — it is by somebody
typing the number.

### The walk caught engine 16 within minutes of it landing, which is the second time today

**Agent:** C (verification and interface) · **Task:** spec 99 · **Date:** 2026-09-16

**What happened.** A full run of `tests/verify tests/console tests/harness` went red on
`test_every_code_every_engine_publishes_has_operator_prose` naming five codes that had
not existed when the previous run of the same file passed:

```
engines/decision/contracts.py::REASON_INPUTS_UNAVAILABLE = 'decision_inputs_unavailable',
engines/decision/contracts.py::REASON_INPUT_MISSING = 'input_missing',
engines/decision/contracts.py::REASON_NO_APPROVED_QUANTITY = 'no_approved_quantity',
engines/decision/contracts.py::REASON_PAIR_DISAGREEMENT = 'pair_disagreement',
engines/decision/contracts.py::REASON_STALE_BAR = 'stale_bar'
```

**Why.** B landed engine 16 `decision` (spec 90) while I was working, in the same
checkout. Nobody messaged anybody; the test simply noticed. Before the walk existed this
would have required somebody to write `test_every_reason_code_decision_declares_has_prose`
by hand, and the evidence that nobody reliably does is engine 12 `regime`, whose two
codes went unmapped for a whole phase for exactly that reason.

**Fix.** Five sentences, my wording with B asked to replace any that is wrong, on the
same terms as engine 21's earlier today. One wording constraint worth recording: engine
16 is a gate that **composes** the order intent and never decides — the operator's ruling
2 and the engine's own README say so in those words — so none of the five sentences says
"decided". A README that says composes and a console that says decided would put the
ruling back at issue in the one place nobody looks.

**Consequence, and it is the reason this is a separate entry rather than a line in the
one above.** The walk has now paid for itself twice on the day it was written, on two
engines nobody had a per-engine test for, one of them a phase old and one of them an hour
old. The interval between a code landing and the console being able to render it is now
bounded by a test run rather than by whether somebody remembered.

### The PENDING that moved, and why that is the mechanism rather than the friction

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** The same run turned three Phase 6 criterion tests red:
`test_pending_on_the_real_tree_names_the_subject_and_the_spec` for the three round trips
and for `console_shows_position_live`, each asserting the PENDING line named "engine 16
`decision`" and "spec 90".

**Why.** Because engine 16 now exists. The criteria correctly moved on to naming engine
18 `execution` and spec 91, and the mapping that pins what each PENDING must say had not
moved with them.

**Fix.** `AWAITED` updated to engine 18, with a note saying the mapping moves as the
phase is built and has now moved once. This is the intended behaviour and was written
down before it happened: without it, a criterion can go on reporting PENDING for a reason
that stopped being true, and a gate cannot tell that state apart from progress. The cost
is one deliberate edit per engine landed; the alternative is a PENDING line nobody has
read since it was written.

### A real BUY above the tier-3 bar can be produced honestly, and here is the measurement

**Agent:** C (verification and interface) · **Task:** spec 100 step 2 · **Date:** 2026-09-16

**What this settles.** Spec 100 step 2 asks for a candidate that is *a real BUY with an
expected move above the tier-3 bar of 1.625%*, produced by the real predictor, not
refused by the DI and not vetoed — and says that if it cannot be produced honestly, that
is a finding for the lead rather than something to route around with a hand-built
`state`. It can be produced. This entry is the measurement, because "a real BUY exists"
is exactly the kind of claim that gets repeated as fact later.

**What is fabricated, and it is one function.** The prices. The labeller, the feature
module, `research/training.py`, the calibrator, the DI and the anomaly detector are the
committed ones, reached through `verify.py`'s existing `_trained`, which gained an
optional `candles_builder` parameter so Phase 5's unremarkable market and Phase 6's
planted one come out of the same pipeline.

**The pattern had to be something a feature vector can see.** Planting "the price goes
up later" is not plantable: the model reads one row of `FEATURE_NAMES` and has no view
of the future. So the signature is four bars of a straight, positive, volume-breaking
climb — `log_return_4`, `efficiency_ratio_4`, `volume_z_4` — and the 4.5% rise that
follows over eight bars is what the real labeller turns into a `target` before the 1.5%
stop can be touched. A `-2.2%` bar later in each cycle supplies the `stop` label, because
a dataset of nothing but `target` and `timeout` teaches a predictor that the stop never
happens, and every expected move it produces is then too high by exactly the term that
is supposed to subtract.

**Measured, 140 days over two pairs, two folds, ~9 seconds to train:**

```
oos rows 2688 · BUY calls 794 · DI refusals 7
BUYs above the tier-3 bar of 0.01625: 656
p_target over those: min 0.702, p25 0.921, p50 0.982
expected move: min 0.0166, p50 0.0292, max 0.0300 (the target barrier, as the ceiling)
realised labels of those 656: target 597, stop 57, timeout 2
```

Fifty-seven of the rows the model calls a BUY on above the bar end at the **stop**. That
is the number that matters most here, and it is not a defect: it is the evidence that the
pattern was learned rather than memorised, and it means the chain will be driven by
candidates the model is wrong about as well as ones it is right about.

**The first version of the series was memorised and was reshaped.** Every signature was
followed by the rise, and the model returned `p_target` of 0.97 and above with `p_stop`
at nine decimal places of zero. Nothing about that is incorrect, and it is a poor
subject: a chain driven by a certainty never exercises the paths that exist *because* the
model is unsure, and a calibrator fitted on perfect separation is not a calibrator
anybody has tested. One signature in five now drifts down instead, which is where the
spread above came from.

### The assertion I wrote against that memorisation was asking the calibrator not to be isotonic

**Agent:** C (verification and interface) · **Task:** spec 100 step 2 · **Date:** 2026-09-16

**What happened.** Having reshaped the series, I asserted the property directly:
`max(p_target) < 0.99` over the BUY rows. It failed at `0.9999999979999998`, and kept
failing after I changed the planting period from 96 bars to 89 and replaced the cycle
arithmetic with a scramble.

**Why — and the first diagnosis was wrong, which is the part worth recording.** My first
explanation was that the clock features were leaking: `PLANTED_PERIOD` of 96 bars is
exactly 24 hours at a 15-minute bar, so every signature fell at the same time of day and
`hour_sin`, `hour_cos`, `weekday_sin` and `weekday_cos` could carry it. That is a real
hazard and the change to 89 bars — prime, and not a divisor of a day — is worth keeping.
It was not the cause. The maximum did not move.

The cause is that `modelling/calibration.py` fits an **isotonic** regression per class.
An isotonic fit is a step function, and when the top bin is pure its step is 1.0 — clipped
to `1 - 2e-9` by the storage form. Forty-eight per cent of the BUY rows sit in that top
step. Nothing is wrong with the model, the series or the calibrator: I had written an
assertion that can only pass if the calibrator stops being isotonic, and it would have
kept failing for as long as the top bin was pure, which is most of the time on any
separable problem.

**Fix.** The property is asserted where it actually lives — in outcomes. The subject must
produce BUY rows above the bar that the real labeller ends at something **other** than
`target` (57 of 656 do), and `min(p_target)` must be short of certain (0.702). Both are
statements about the model having learned a tendency rather than a rule, and neither
demands anything of the calibrator's shape. A probability *ceiling* was the wrong
instrument: what "not memorised" means is "wrong sometimes", and that is measurable
directly.

**Consequence.** The 89-bar period stays. A planting period that divides the day is a
real leak into the clock features even though it was not this one, and finding out that
it was not required changing it first — which is the cheaper order.

### The fresh-clone test took four versions, and the fourth is the first that states the rule

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** `test_no_criterion_reads_the_repositorys_data_models_or_logs` checks
that no Phase 6 criterion reaches into a gitignored directory. Versions one and two are
recorded in an earlier entry: a substring search that went red on the section's own
prose, and a `tokenize` strip that dropped the string literals a path is built from while
matching "data" inside `data_guard`. Version three searched non-docstring string literals
and passed — until the trade-producing subject landed and it went red on
`tmp / "subject" / "models"`.

**Why that was the test being wrong rather than the code.** That is a **temporary**
directory that happens to be called models, which is exactly where the subject's
artefacts are supposed to go, and `_trained` has constructed the same path since Phase 5.
The rule was never "do not write the word models"; it is "do not read *this repository's*
`data/`, `models/` or `logs/`", and versions one to three were all searching for the word.

**Fix.** Version four checks the rule. Every `/` chain in the section whose leftmost
operand is `ctx.root` or `REPO_ROOT` is walked and its string segments refused, with a
guard that at least one such chain was found so the check cannot pass vacuously; and
separately, no literal may carry one of the three names as a *path segment*
(`data/`, `models\\`), which catches a relative path built without `ctx.root`.
Docstrings stay excluded, for the reason version one exists.

**Consequence, and it is the reason this is a third entry rather than a footnote.** Three
of the four versions were green at the moment they were written. What moved was the code
under them, and each time the test failed for a reason that was about the test. A check
that has to be loosened every time the code grows is a check that was written against the
code's current shape rather than against the property — and the tempting repair each time
was a carve-out, which is how a rule becomes a list of exceptions nobody can read.

### The scripted market: what it refuses to do is the design

**Agent:** C (verification and interface) · **Task:** spec 100 step 1 · **Date:** 2026-09-16

**What happened.** `tests/harness/market_script.py` is the stream half of the fake
exchange: a rolling trade window and a top-of-book quote per pair, everything filtered by
an injected clock. `FakeKrakenClient` answers the four REST calls and nothing else, which
is enough for a gate and not for a round trip — engine 3 reads a stream, and the paper
broker's fills and the console's mark both move when that moves.

**Three things it deliberately does not do, and each was a real temptation.**

It does not **simulate**. A criterion says what traded and when; nothing in the harness
decides what the market does. A simulator would be a second opinion about price sitting
between the criterion and the engines, and when a round trip came out wrong there would
be two places to look instead of one.

It does not **fill orders**. B's paper broker owns fills, the ledger and the order state
by the operator's ruling of 2026-09-16, and the whole point of that ruling was that one
fill rule should exist once. A harness that decided fills would be its third copy.

It does not **hold its own clock**. It reads the same injected `Clock` the orchestrator
holds, so a criterion advances time in one place. A test that had to move the clock and
then tell the market about it is a test that will forget on the tick it matters.

**`drain()` returns nothing, and the docstring says why.** Engine 2 writes what `drain()`
returns into the archive. Fabricating raw frames would put invented JSONL in front of the
one engine whose entire job is to record what actually arrived, and no Phase 6 criterion
judges the archive — `recording_span_continuous` does that in Phase 2, against a committed
report. An empty return with a reason is honest; a plausible one would not be.

**The trade count per bar has to vary, and that is correctness rather than realism.**
`trades_z_*` is a z-score of the trade count over a lookback. A constant count is a
zero-variance window: it divides by zero, yields NaN, publishes as null, and engine 13
then correctly refuses the whole market-quality vector as incomplete — so a fixture with
a fixed count *cannot exhibit the property the criterion is about*. B hit this twice
building the Phase 5 rehearsal, the second time because the obvious fix, `min(trades, 24)`,
saturates: real bars carry hundreds of trades, every bar sat at the ceiling, and the count
was constant again one level down. Both failures have a test here, the second one against
bars carrying a thousand trades.

**The protocol is walked, not listed.** `test_every_method_the_real_stream_declares_is_here`
reads `MarketStreamProtocol.__protocol_attrs__` and checks each name, with an assertion
that the Protocol declares something so it cannot pass vacuously. That shape is A's, and
the reason is this phase's own finding: `PaperBroker` forwarded six of seven methods and
dropped `drain_gaps`, which would have had engine 2 record no `gap` line and a recording
claim to be continuous across reconnects. It was found by measurement rather than by a
test, because the test that would have caught it would have had to be written by the
person who forgot. Nobody writes a test for the method they forgot; a walk does not need
them to.

**Checked against its consumer, not against itself.** Two of the tests drive the real
engine 3 rather than reading the harness's fields back — one asserting the open bar is
never published (invariant 10; a partial high and close in front of the feature engine is
look-ahead by another name), and one planting a trade **between** two loop ticks and
asserting engine 3's per-tick range still carries it. The second is what
`context.previous_now` exists for, and a harness that could only plant trades on tick
boundaries could never show it.

### Spec 101 reads the position's hold reason out of a column that does not exist

**Agent:** C (verification and interface) · **Task:** spec 101 · **Date:** 2026-09-16

**What happened.** Spec 101 step 3: *"`hold_reason` rendered on the position when the
manage chain held, through `REASON_PROSE`."* Nothing in the database carries it, so the
console cannot render it and no amount of work in `console/` will change that.

**Why.** The chain is complete right up to the last step and then stops. Engine 21
publishes `state["position_manager"]["hold_reason"]`; engine 19 reads it
(`_hold_reason`), carries it into `MemoryState` and re-publishes it in
`state["memory"]["hold_reason"]` — and `state` is a fresh dict every tick with only
`state["system"]` surviving. **The console is a separate process reading SQLite.** It
never sees `state` at all.

`grep -rn hold_reason db/ src/acsoe/clients/store/` finds nothing: the `positions` table
has `position_id`, prices, barriers, `last_price`, `unrealised_pnl`, `opened_at`,
`timeout_at` and `updated_at`, and no hold. `ownership.md`'s seam row says
*"Manage-chain hold (`hold_reason`) | B writes | C (19 `memory`, console) reads"*, and
the reading half is true for engine 19 and impossible for the console.

This is the same shape as the persisted-mode seam of Phase 2, which is worth saying
because it is the reason the obvious workaround is refused. The console could *infer* a
hold from a `data_guard` row in `block_records` on the latest cycle. `engine-contracts.md`
already ruled that exact move out for the system mode — it is written by the command
reader that owns the value and **"never inferred from the `commands` trail"** — and the
reasoning transfers unchanged: an inference agrees with the truth until the day the rule
changes in one place, and a screen that guesses is worse than a screen that says nothing.

**Fix — not mine to make.** A schema change, so it is the lead's to approve and B's to
migrate (ownership rule 4). Escalated with a proposal rather than a question:
`hold_reason TEXT` on `positions`, written by engine 19 on the tick it updates the row
and `NULL` on any tick the chain did not hold. The column matches what `hold_reason`
already is — a fact about *now*, null whenever the manage chain did not hold — and the
console already reads `positions`, so no new read path appears. The alternative, a
`manage_ticks` table, is heavier and nothing else wants it.

**What I did instead**, so the spec is not blocked entirely: the age column, below.

### The open-positions table has never shown how old a position is

**Agent:** C (verification and interface) · **Task:** spec 101 · **Date:** 2026-09-16

**What happened.** Spec 101 wants the position rendered with *"its mark and unrealised
PnL changing tick by tick, **its age shown**, stale figures faded"*. Two of the three are
there from Phase 1: `last_price` and `unrealised_pnl` are on `PositionView` and
`staleness` fades past `console.stale_after_ms`. The age is not: `opened_at` and
`timeout_at` reach the view model and the payload, and the table renders eight columns —
pair, quantity, entry, last, target, stop, unrealised, change — none of which is age.

**Why it was not noticed in Phase 1.** Phase 1 rendered **seeded** rows, and spec 19's
acceptance was that the region renders and is absent when nothing is open. How long a
seeded position had been open is not a question anybody had a reason to ask of a fixture.
It becomes a real question the moment a position is a live one with a twelve-hour timeout
against it: "opened 4h 12m ago" and "times out in 7h 48m" are the two facts an operator
uses to decide whether to leave it alone.

**Fix.** `age_us` and `age_text` on `PositionView`, computed **in the reader from the
injected clock** — which is the rule `views.py` already states for `Staleness`: *"a view
model that worked out its own age"* would be reading a clock, and view models do not
read clocks. `format_age` already exists and is already the coarse form the band uses, so
the console says "4h 12m" in one voice rather than two.

### The declared protocol is not the whole surface, and a walk over it cannot say so

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** Driving the real chain against `ScriptedMarket` for the first time,
the guard chain blocked at engine 2:

```
blocked by market_data_recorder
unhandled AttributeError: 'ScriptedMarket' object has no attribute 'set_subscription'
```

`test_every_method_the_real_stream_declares_is_here` was green at the time, and it was
not wrong: `ScriptedMarket` **does** answer all seven names in
`MarketStreamProtocol.__protocol_attrs__`.

**Why.** The protocol is not the whole surface. Engine 2 reaches the stream's
*lifecycle* — `set_subscription` and the `subscription` property — and `PaperBroker`
forwards ten names to the client it wraps, of which four (`start`, `stop`,
`set_subscription`, `subscription`) are declared nowhere in `MarketStreamProtocol`.

The two layers then fail in opposite ways and only one of them fails loudly. Engine 2
takes `getattr(stream, "set_subscription", None)` and skips when it is absent, which is
what lets it run against C's plain `FakeKrakenClient`. `PaperBroker.set_subscription`
calls `self._real.set_subscription(pairs)` **unconditionally** — correctly: it is a
forwarder, and a forwarder that silently swallowed a missing method would be the
`drain_gaps` defect again. So in paper mode, where the broker is the stream every engine
sees, a client missing a lifecycle method raises rather than degrades, and it raises
inside the guard chain, which contract rule 7 turns into `ERROR` and `ERROR` blocks.

**This is the more interesting half of the finding.** A walk over `__protocol_attrs__` is
necessary and it is not sufficient, because a Protocol records what somebody wrote down
and an engine uses what it uses. Two things a double must satisfy are invisible to it:
the names reached by `getattr`, and the names a wrapper forwards.

**Fix.** Two parts.

`ScriptedMarket` gains the four lifecycle methods, with `subscription` holding what it
was last given — a stream that accepted a subscription and then reported a different one
would make engine 2's read-back meaningless, and the read-back is how engine 2 learns
what it is actually recording.

And a second test that derives its expectation rather than listing it: the AST of
`clients/paper/broker.py` is walked for every `self._real.<name>`, and `ScriptedMarket`
must answer each. **In paper mode the broker is the stream every engine sees**, so the
surface that matters is the one the broker forwards, not the one the Protocol declares.
It is derived from B's file, so a name B adds tomorrow is covered without anybody
remembering — which is the same property the reason-code walk has, arrived at from the
other direction.

### The whole Phase 6 trade chain is gated on engine 9, and engine 9 has no session

**Agent:** C (verification and interface) · **Task:** spec 100 · **Date:** 2026-09-16

**What happened.** Driving the real chain against the planted market at tier 3, with
engines 16, 18, 21 and 19 in place and the paper broker wrapping the scripted stream,
the tick gets six engines further than it ever has and stops:

```
tick 1  no block
tick 2  no block
tick 3  blocked by cost
        Cost gate could not price this candidate: missing order_book is NoneType,
        expected a mapping
```

Everything before it worked. Engine 3 published 200 candles and a closed bar; engine 5
produced the feature row; engine 7 scanned five pairs and **entered one**; engine 12
classified the market `choppy`; engine 13 loaded the anomaly artefact and did not block;
engine 8 scored. Then engine 10 `cost` read `state["order_book"]` and found nothing.

**Why.** Engine 9 `order_book` does not exist. Engine 10's `_require` treats an absent
key and a `None` identically and raises `MissingInputError`, which is correct and is the
fail-closed posture stated in its own docstring: *"engine 1 publishing `spread_pct: null`
because the order book fetch failed must not be read as a spread of zero, which would be
the most optimistic possible reading of a failure."* Slippage is one of the four terms of
friction, and a friction computed without it is a hurdle that is too low.

None of this is a surprise to the documents. `bootstrap.py` says the hole is load-bearing
this phase and that *"the tick stops at `cost` and `skeptic` never runs"*;
`ownership.md`'s seam table has "Slippage estimate | C (96) | B (10 `cost`, already reads
it)". The Phase 6 wave ordering puts spec 96 in wave 2 and specs 91, 92 and 93 in wave 3.
Everything is written down.

**What is new is who owns it.** Spec 96 is `C-models`'s, and `C-models` died at the usage
limit at 23:49Z and has not returned. So the critical path for **seven** of my nine
criteria and for B's specs 91, 92 and 93 rehearsals runs through a file belonging to a
session that is not running. Measured rather than inferred: this is the first time
anything has driven the chain far enough to find out, because until today engines 16 and
18 did not exist either.

**Not fixed here.** `engines/order_book/` is `C-models`'s lane and this session was told
not to touch `engines/`. Escalated to the lead with the measurement, which is the part
that makes it a scheduling decision rather than a guess.

**What this does not block.** The seven criteria still report PENDING and still name what
they wait for, which is the state they are supposed to be in. Everything up to engine 10
is now known to work end to end against the planted subject — six engines, a real
candidate, a real feature row and a real model score — and that is a stronger position
than the criteria could report before today.

---

# C-models, session 3 — spec 96, engine 9 `order_book`

Appended under my own heading. Nothing above this line is mine and nothing above it is edited.

### The archive records book **deltas**, so a mid-stream cut has no book in it at all

**Agent:** C (engines and models) · **Task:** spec 96, the fixture · **Date:** 2026-09-16

**What happened.** Spec 96 step 5 says "choose one deep pair and one thin pair from the tier-1
recording and a window of a few minutes with no gap". Taken literally that produces a fixture
from which no book can be reconstructed. Every `book` frame in `data/raw/` after the first is a
Kraken v2 **update**:

```
{"kind":"tick","pair":"ETH/USD","channel":"book", ...
 "payload":{"channel":"book","type":"update","data":[{"symbol":"ETH/USD",
   "bids":[{"price":2396.31,"qty":0.0},{"price":2396.17,"qty":20.8666329}],
   "asks":[], "checksum":839555268, ...}]}}
```

A `qty` of `0.0` deletes a level; everything else replaces one. There is no absolute book in any
of those lines. The only absolute book is a `type:"snapshot"` frame, and Kraken sends one **only
at subscribe** — which in a continuous recording means only after a reconnect.

**Why this is a trap and not merely an inconvenience.** A cutter window chosen anywhere in the
middle of the stream produces a file full of well-formed, real, byte-exact book frames that
cannot answer "what was the bid side" at any instant. It would have read as a good fixture. The
reconstruction would then have started from an empty book and filled in only the levels that
happened to change during the window — a *plausible* shallow book, four or five levels deep,
which a slippage walk would price as far thinner than the market was. That is the failure shape
`code-standards.md` names twice: a wrong answer that is in range survives, and the levels nobody
saw are the worst ones, so the error runs in the direction that makes the cost gate refuse for a
fabricated reason.

**Fix.** Cut from a **resubscribe**, not from a quiet moment. `data/raw/kraken_v2__msi__
2026-09-16.jsonl` carries four `gap` markers; the first is at `00:17:06.052717Z` with
`reconnected_at` equal to it, and the ten tier-1 snapshots land 250 to 290 ms later. A window
opening at `00:17:06.100000Z` therefore

- does **not** intersect the gap's interval `[disconnected_at, reconnected_at]`, which is what
  A's cutter refuses on, and
- **does** contain one `snapshot` frame per pair, ahead of every delta.

The dry run confirmed both, per pair: `ADA/USD: {'snapshot': 1, 'update': 451}`,
`BTC/USD: {'snapshot': 1, 'update': 524}`. The fixture reader can now start from a real ten-level
book and apply deltas in recorded order, with nothing assumed.

### `order_book.depth` does not exist in `config/default.yaml`, and its value is decided by the archive

**Agent:** C (engines and models) · **Task:** spec 96 step 2 · **Date:** 2026-09-16

**What happened.** Spec 96 step 2 reads `depth` from config key `order_book.depth`, marked
"requested of the lead, spec 80". There is **no `order_book:` section** in `config/default.yaml`
and no matching pydantic section in `src/acsoe/platform/config.py`. `Config` is `extra="forbid"`,
so the key needs both halves or the loader refuses to start, and both files are other agents'.

**Why it matters more than a missing key usually does.** `depth` is not tuning. It is the bound
on the walk, so it is the definition of `book_too_thin`: a notional the bid side cannot absorb
*within that many levels* is declined rather than extrapolated. Set it above what the archive
recorded and the live engine is configured to walk further than any committed evidence can
validate — the fixture could no longer exercise the refusal it exists to prove, and the README's
seconds-to-minutes bound would be quietly weaker than it claims.

`scripts/record.py`'s `DEFAULT_DEPTH` is `10`, and every snapshot in the archive confirms it:
ten bids and ten asks, for all ten tier-1 pairs, at every resubscribe measured. So **10** is the
value asked for, and it is asked for on the evidence rather than as a round number.

**Fix.** Requested of the lead by message, with the reasoning above, before any code. Until it
lands, `_depth` treats the absent key exactly as it treats a null one: `OK`,
`order_book_inputs_unavailable`, no estimate, and engine 10 refuses — which is the same posture
as every other fail-closed shape and does not special-case the phase's own incompleteness.
Three cases are told apart rather than conflated, per `code-standards.md` on handlers that cannot
distinguish two situations: `Config.get` **raises** `ConfigKeyError` (a `KeyError` subclass) for a
key the model does not declare, **returns `None`** for a declared key the operator left unset, and
returns the value for a key set to something that is not a count.

### Spec 96 — five mutations, five killed, and which test killed each

**Agent:** C (engines and models), session 4 · **Task:** spec 96 · **Date:** 2026-09-16

Session 3 built engine 9, its tests and the fixture and died before sweeping them. This is
the sweep, plus the fixtures README row it also owed. Nothing in the engine changed.

**Harness.** `scratchpad/mutate_ob.py`. Baseline first, and it refuses to report if the tree
is already red — sweeping a red tree marks every mutation KILLED. The target file is copied
to the scratchpad **before** the mutation and restored from those bytes with the sha256
compared **in the same statement that writes it back**; never `git checkout --`, because
`engines/order_book/` is untracked and there is nothing behind it. Every anchor is asserted
to occur exactly once. Every file that is not the variable is hashed on both sides of the arm
and reported: all five runs printed `witness files unchanged: True`.

**Arm, and the directory it excludes.** `tests/engines/test_order_book.py` — 51 tests, the
file that owns this engine. Running the sweep narrowly against the tests that own the code is
the protection `code-standards.md` asks for in a shared checkout, because a mutation live on
disk turns another agent's run red and a spurious failure reads as KILLED. **Excluded:**
`tests/engines/test_cost.py` and the chain rehearsals, which are B's and A's and would have
made attribution impossible; every verdict below is a kill, and a kill on a subset is a kill.
No survivor is being claimed on a subset, which is the direction the rule guards.

| | Mutation | Verdict | Newly red |
|---|---|---|---|
| O1 | the **ask** side walked instead of the bid side — spec 96's first named one | KILLED | 8 |
| O2 | the walk **stopping one level early** — spec 96's second | KILLED | 11 |
| O3 | slippage measured from the fill price rather than the **best bid** — spec 96's third | KILLED | 8 |
| O4 | a partial walk reported as complete instead of refusing past the fetched depth | KILLED | 7 |
| O5 | `levels_consumed` published one short of the levels the walk touched | KILLED | 8 |

**O1** was killed by, among others, `test_the_deep_pairs_walk_matches_the_hand_computation`
and `test_the_cost_gate_prices_the_slippage_engine_nine_published`. Worth naming because the
two failures say different things: the first is the arithmetic, the second is that engine 10
priced a different number. A file asserting only the arithmetic would have caught the defect
and not the consequence.

**O2** is the broadest kill at eleven tests, and the one that most needed the real fixture.
Stopping one level early is not a small error in one direction: a notional the book *can*
absorb is declined as `book_too_thin`, and one it can only just absorb is filled at a better
price than the book offers. `test_the_whole_book_exactly_is_a_fill_and_one_cent_more_is_not`
is the boundary that separates those two, and it is the test a hand-written ladder alone
would not have motivated.

**O3 is the interesting one and it is why spec 96 named it.** Measuring `(best_bid −
fill_price) / fill_price` rather than `/ best_bid` moves the answer by a fraction of a
percent, which is exactly the size of the thing being measured — a wrong answer in range. The
consequence downstream is a double charge: engine 10 already adds the measured spread as its
own term of `friction`, so slippage measured from anything between the bid and the ask
charges part of that spread twice, and the hurdle refuses trades for a cost the book does not
impose. Killed by both hand computations and by
`test_the_published_payload_can_be_recomputed_without_trusting_it`, which is the one that
recomputes the ratio from `best_bid` and `fill_price` rather than reading the published
`estimated_slippage_pct` — ruling 7's shape, and the reason that test exists.

**O5 is the checked negative that turned out not to be one.** `levels_consumed` changes no
decision: it is provenance beside the estimate, and the slippage is identical with it wrong.
I expected it to survive, which would have said that a published field nobody asserts on can
say anything. It was killed by eight tests, because the fixture's walks are asserted in full —
`test_the_engine_publishes_the_walk_it_made` is parametrised over both pairs and pins the
level count against a hand computation (ADA/USD consuming 10 levels for
0.0001366891113175430924786514892, BTC/USD consuming 4 for
0.00006528042192692375531712952815). That is the difference between publishing a number and
asserting it.

**No survivors, so nothing was re-run wide.** Had one survived, the rule is that a mutation
surviving a subset has not survived, and it would have gone to
`tests/engines/test_cost.py` and the chain rehearsal before being believed.

**Also landed, and it was outstanding rather than new:** the `book_sample.jsonl` row in
`tests/fixtures/README.md`, with the provenance session 3 worked out and did not get to
write down — the two pairs, the 30-second window, and above all *why the window opens 48 ms
after a reconnect*. Kraken v2 sends book **deltas**, and the only absolute book is the
`snapshot` frame at subscribe, so a cut from a quiet moment mid-stream would have produced a
file of real, byte-exact frames that cannot say what the bid side was at any instant. The
reconstruction would have started from an empty book and produced a plausible four- or
five-level ladder — thinner than the market was, in the direction that makes the cost gate
refuse for a fabricated reason. That reasoning belongs beside the file, not only in a build
log, because the next person to re-cut it will read the README.

### Decision: engine 14 weights by Brier skill against the fold's own base rate — and the base rate is not in the table

**Agent:** C (engines and models) · **Task:** spec 97 step 3 · **Date:** 2026-09-16

**Proposed here before any of engine 14 is written**, per spec 97 step 3, which makes this a
methodology choice the lead approves rather than something a lane decides.

**Options.** Three were on the table.

1. **Brier skill against the base rate, clipped at zero, normalised.** For each model version,
   `skill = 1 - brier / base_rate_brier`, clipped below at zero; `weight = skill / sum(skill)`,
   or all zero when nothing beats its base rate.
2. **Inverse Brier**, `weight ∝ 1 / brier`. Needs no base rate at all.
3. **Rank-based**, weight by position in a Brier ordering.

**Chose option 1**, which is the example spec 97 itself offers.

**Because** the other two both hand weight to a model that has no edge. Inverse Brier is the
sharper illustration: Brier is bounded and always positive, so `1 / brier` gives a model that
is *worse than always predicting the base rate* a perfectly respectable weight — and on the
numbers this project actually has, that is not a hypothetical. Spec 67's first real run came
in at or slightly worse than base rate on two folds of three. A rule that cannot express "this
model has no edge" would weight those folds as confidently as a good one, and spec 97's own
requirement that a model failing to beat its base rate gets weight zero would be unstatable.
Rank-based has the same defect wearing a different hat: the worst of three models still ranks
third, and third of three is a weight.

Option 1 also has the property that makes it honest about today: with one model version in the
table the weight is 1.0 whatever its skill, and with none it is the empty case. The rule does
not pretend to be doing work it is not.

**The blocker, and it is spec 97's own warning coming true.** `leaderboard` has a `brier`
column and **no base-rate Brier column** (`db/migrations/0001_initial.sql`). Engine 20 already
computes `base_rate_brier` per fold — `engines/tournament/engine.py` holds it on `_FoldScore`,
recomputes it from the out-of-sample rows, and checks the digest against it — and then
**discards it** on the way into the store, because there is no column to write it to.

**It cannot be recovered from the columns that exist, and the near-miss is worth recording
because I nearly took it.** `win_rate` is stored, and for a binary outcome the base-rate Brier
is `p(1-p)`, so `win_rate * (1 - win_rate)` looks like the number. It is not. `brier` and
`base_rate_brier` are computed over **every** fold row; `win_rate` is computed over the **BUY
subset** only. Two different populations, and on a fold where the BUY calls are the confident
ones they differ substantially. A skill score built from those two would be a ratio of
quantities measured on different sets — in range, plausible, and wrong in whichever direction
the BUY subset happens to lean. That is exactly the witness rule the lead added to
`code-standards.md` today, met from the other side: two numbers that look like the same
quantity, in one table, with nothing saying they are not.

**So this is a schema question, which spec 97 says in as many words is the lead's and not a
number encoded into `notes` and parsed back out.** What I am asking for: **`base_rate_brier
REAL` on `leaderboard`**, nullable, written by engine 20 from the value it already has. That
is a migration (B's `db/migrations/`), a `LeaderboardRow` field (B's `clients/store/`) and one
line in engine 20's `_write` (mine). Until it lands, engine 14 has no way to evaluate the
approved rule, and the fail-closed reading is the one I would build meanwhile: a row whose
`base_rate_brier` is absent gets **weight zero with a reason code**, not a default base rate
— inventing one would be this lane choosing the line at which a model counts as having edge.

**The regime and the DI margin are published as provenance and are not in the arithmetic**,
and that is deliberate rather than an omission. Spec 97 has engine 14 read
`state["regime"]["label"]`, and the mutation list says "the regime ignored **if** the approved
rule uses it". Conditioning a weight on regime requires per-regime metrics, and the leaderboard
holds one Brier per model version over the whole out-of-sample window with no regime breakdown
anywhere. A regime adjustment invented on top of that would be a methodology choice with no
measurement behind it, which is the thing spec 70 and spec 72 both stopped at rather than
walked past. The regime goes into `basis` so the operator can see which market the weights were
published in; it changes none of them. The same for `di_margin`.

**Cost.** One schema change and the seam it opens with B. And the honest statement that engine
14 is inert today — the walk-forward trains one predictor per fold, so there is one version to
weight — which the README says and which the fixture is built to work around rather than hide:
`leaderboard_sample.json` carries three fabricated versions precisely because the real table
cannot exercise the rule, and its provenance line says so.

### An unmarked position was worth nothing, and one such tick freezes the account

**Agent:** C (engines and models) · **Task:** spec 98 · **Date:** 2026-09-16

**What happened.** `_write_equity` read `positions_value` through
`decimal_field(manager or {}, ...)`, and `decimal_field` returns `Decimal(0)` for an
absent field. Only an absent `balances` skipped the row. So on a tick where engine 21
could not take a mark, `equity = cash + 0` and the position's entire value vanished from
that tick of the series. Found by the lead while confirming for B that engine 19 treats an
absent `positions_value` as nothing-to-record. It does not, and the lead checked the code
rather than the docstring — the docstring said the right thing.

**Why it matters more than a wrong number.** Engine 17 computes
`(peak_equity - equity) / peak_equity` against a peak read from the store, so on a fully
invested account one unmarked tick is a drawdown approaching 100% against a
`safety.max_drawdown_pct` of 0.10. The account freezes over a missing quote. Spec 92 has
engine 21 publish `positions_value` **absent, never zero**, precisely so this is
detectable — and `decimal_field`'s default threw that distinction away at the reader.

The lead's framing is the part worth keeping: this is the third instance this phase of
**a default that is correct in the only state the system has ever been in**.
`Orchestrator._flag`'s `bool()` was right for an absent payload, `decimal_field`'s zero is
right for a flat account, and engine 11's concurrency check was right while nothing could
open a position. All three become wrong on the first tick that holds a position, and none
of them looks wrong until then.

**Fix.** `store.count_open_positions()` is read **before** the equity arithmetic rather
than at the write, because this tick's positions have already landed and it is that count
which decides whether cash-only equity is the truth or a hole. Non-zero count with
`positions_value` or `unrealised_pnl` absent writes **no** equity row and names itself in
`equity_skipped_reason`; zero count with an absent mark writes the row on cash alone,
because there is nothing to mark. `unrealised_pnl` gets the same treatment: an absent one
reading as zero is a claim that the position sits exactly at its entry price, which Phase
7's attribution would read as fact.

**One existing test of mine was green because of the defect**, and it is worth naming
rather than quietly fixing. `test_the_position_count_comes_from_the_store_not_from_this_
tick_s_state` drove two ticks with an open position and no mark, and asserted
`open_position_count == 1` on **two equity rows that valued that position at nothing**.
The fix removes those rows, so the test had to change to supply a mark. Its subject is
sharper for it: tick 2 now publishes a mark and no positions list, so the store says one
open position while `state` says none — which is what the test was always about.

### The three new sources, and the write order that decides which row survives

**Agent:** C (engines and models) · **Task:** spec 98 · **Date:** 2026-09-16

`state["execution"]["orders"]`, `state["exit"]["orders"]` and `state["exit"]["positions"]`
are read now; engine 19 is the single writer of relational rows, so before this those rows
reached no table at all. Field shapes confirmed by B's audit rather than negotiated: the
row payloads are the store contract's minus `run_id`, `cycle_id` and `updated_at`, which
`_stamped` sets itself because a row carrying the publisher's `run_id` cannot be joined to
the block record for the tick.

**The write order is chain order and it is load-bearing twice**, per the lead's ruling.
`write_position` upserts on `position_id` and `write_order` on `userref`, so the row
engine 19 writes *last* is the stored state. Positions: 21 then 22, because engine 22 runs
after 21 and a position closed this tick must not be stored as open with a mark on it — a
row the console renders as live and `safety` counts towards its escalation precondition.
Orders: 18 then 21 then 22, because an entry placed on the opportunity chain and cancelled
on the manage chain must end cancelled; the other way it is stored as resting, which is a
live post-only buy to everything that reads the table, and invariant 8 exists for exactly
that order. Both are tested with an assertion on the **row count** as well as the status,
because an upsert that had silently become an insert would leave both rows present and the
status assertion would pass on whichever came back first.

### Spec 98 — eight mutations, eight killed, and the one that survived first

**Agent:** C (engines and models) · **Task:** spec 98 · **Date:** 2026-09-16

Harness `scratchpad/mutate_mem.py`, same guarantees as the other two sweeps: baseline
first with a refusal if it is red, byte copy before the mutation, sha256 compared in the
same statement that restores it, every anchor asserted to occur exactly once, witnesses
hashed on both sides. Arm `tests/engines/test_memory.py` and
`tests/engines/test_memory_rows.py`. **Excluded and named:** `tests/verify/`, which is the
other C session's and would make attribution impossible.

| | Mutation | Verdict | Killed by |
|---|---|---|---|
| P1 | engine 18's orders not read — spec 98's first named one | KILLED | `test_the_entry_order_engine_18_places_reaches_the_store` |
| P2 | engine 22's positions not read — spec 98's second | KILLED | the closed-position test and the 22-sources test |
| P3 | engine 22's orders not read | KILLED | the 22-sources test |
| P4 | 18's orders written after 21's — spec 98's third | KILLED | `test_a_placement_and_its_same_tick_cancel_end_as_cancelled` |
| P5 | 22's positions written before 21's | KILLED | `test_a_position_marked_and_closed_on_one_tick_ends_closed` |
| P6 | the equity row skipped whenever a mark is absent, open position or not | KILLED, 6 tests | `test_a_flat_account_still_writes_its_equity_row` and five older equity tests |
| P7 | the equity row never skipped — the defect as it stood | KILLED, 3 tests | the three invested-account tests |
| P8 | the hold reason carried forward instead of cleared | **survived, then killed** | `test_the_hold_reason_is_written_and_then_cleared` |

P6 and P7 are the lead's two required mutations and they fail in opposite directions,
which is the point: a version that always skips loses the flat account's row — a silent,
permanent hole in the one series the drawdown breaker reads — and a version that never
skips is the defect. The two tests they redden differ in **exactly one input**, whether a
position was published.

**P8 survived the first sweep and the test was at fault, not the engine.** The mutation
sets `hold_reason` only when there is one, so the previous tick's reason is carried
forward — an hour-old hold rendered forever, reporting a paused manage chain over one
running normally. My test drove a tick that held and then a tick that did not, and it
passed under the mutation: `a_position` dumps a real `PositionRow`, which carries
`hold_reason: None` as a **model default**, so the row payload itself already said null
and the column came out null whether or not engine 19 assigned anything. Two sources
supplying the same value — the lead's witness rule, met from the other side, on a test
written the same day the rule was added.

The fix is the one the rule prescribes: make the sources differ. Tick 2's row now carries
a **stale** `hold_reason`, which is not a contrivance — engine 21 builds its published
rows from the open positions it read out of the store, so last tick's value is exactly
what comes back — and only engine 19's tick-level assignment can clear it. Tick 1 already
distinguished the two, with the row saying null and the tick saying `data_guard`, and it
now asserts that precondition explicitly. P8 is red on re-run.

**One baseline refusal, and the harness was right to make it.** P8's first attempt aborted
with `REFUSED: baseline is red` on a `TypeError: object of type 'ScalarEvent' has no len()`
out of PyYAML, loading `config/default.yaml` — another agent mid-save. Nothing was
mutated, nothing was reported. That is the protection working: without the baseline the
mutation would have been applied to a tree that was already failing and reported KILLED on
somebody else's half-written config.

### `Path.write_text` again, this time inside the editing tool, and it broke a mutation sweep

**Agent:** C (engines and models) · **Task:** spec 98 · **Date:** 2026-09-16

**What happened.** Four mutation arms in a row aborted with
`anchor appears 0 times, expected exactly once`, against anchors I had copied character for
character out of the file. `src/acsoe/engines/memory/engine.py` was **566 CRLF and 0 bare
LF** in the working tree; its committed blob is 521 bare LF and no CRLF.
`tests/engines/test_memory_rows.py` was **mixed**: 614 CRLF and 390 LF.

**Why.** The text-mode round trip `code-standards.md` names, arriving through the editing
tool rather than through anyone's `Path.write_text`. It rewrites the **whole file's** line
endings, not the lines it was asked to change — and `.gitattributes` carries
`* text=auto eol=lf`, so git's clean filter normalises on the way into the index and
`git diff --numstat` reported only my real changes (53/8 and 416/3). `git status` said
nothing. The only visible symptom was four sweeps refusing to find an anchor.

**This is the same mechanism that cost the lead the spec 102 revert**, and connecting them
is the reason this entry exists rather than a one-line fix. Two Phase 5 criterion tests
patch `modelling/di.py` **by literal anchor** to prove the DI criterion can fail; the
refactor rewrote those lines and both proofs reported "anchor appears 0 times". A
whole-file line-ending rewrite does the same thing to every literal-anchor patcher in the
repository, silently, with no diff to show for it. Anywhere under `tests/fixtures/`, which
is marked `-text` so that no conversion happens near an evidence fixture, it would change
committed bytes instead.

**Fix.** Both files rewritten as bytes with `\r\n` replaced by `\n`: engine.py 25,109 →
24,543 bytes, test_memory_rows.py 39,810 → 39,196. Every file this session has touched was
then scanned; the only other CRLF file in the set is `tests/engines/test_memory.py`, which
is **not mine** — its blob is pure LF, `git status` reports it clean, and I have never
written it, so it is one of the ~120 pre-existing conversions `code-standards.md` already
records. Left alone rather than tidied, because a file I did not change is not mine to
rewrite in a shared checkout.

**Consequence.** The scan is worth making a habit rather than a reaction: `CRLF count` on
every file a session touched, before the mutation sweep rather than after four refusals.

### Engine 9 audited rather than only swept, and what was found sound

**Agent:** C (engines and models), session 4 · **Task:** spec 96 · **Date:** 2026-09-16

A mutation sweep proves the *tests* can fail. It says nothing about whether the engine is
right, and I inherited engine 9 from session 3 rather than writing it. This log asks for
what was checked and found sound as well as what was found broken, so: every one of spec
96's structural requirements was read against the code, and all of them hold.

- **`number = 9`, `is_gate = False`**, matching the registry's Gate column.
- **It cannot block, and that is structural rather than careful.** `EngineStatus.OK`
  appears exactly once in the module and `BLOCK`, `PASS` and `ERROR` appear zero times —
  one return point, one status. Spec 96 step 4 requires a non-gate that refuses on its own
  criteria to be impossible, and this is the strongest available form of it.
- **Nothing can escape as an `ERROR` either, which is the half a status count misses.**
  Contract rule 7 turns an uncaught exception into `ERROR` with `blocks_trading=True`, so
  a raise here would be engine 9 blocking the tick by the back door. Every `SetupError` —
  a missing config key, a null depth, a non-integer depth, a missing scout pair, an
  unreadable quote currency, an unparseable balance — is raised inside the one `try` that
  turns it into an `OK` with `order_book_inputs_unavailable`. The client call is wrapped
  separately and catches `KrakenError`, `ValidationError` and `ValueError` only, with the
  reasoning written beside it: anything that is not exchange-shaped propagates on purpose,
  because a defect on this side of the boundary is not a thin book.
- **No `float(` anywhere in the engine or its contracts**, and every money field is typed
  `Money`. The walk is `Decimal` throughout, and the two inexact operations — a remainder
  divided by a price, and quote divided by base — are named in the docstring with the
  reason nothing is quantized.
- **The README carries spec 96 step 6's bound in the required terms**: validated over
  seconds to minutes of recorded book rather than years of archive, because the historical
  archive carries no book at all, and every slippage number this system reports inherits
  that limit.

The one thing I would still like closed is not a defect in the engine: **engine 9 publishes
no `pair`**, so B2's engine 16 coherence walk — which checks any payload carrying a `pair`
against `state["scout"]["pair"]` — is silently exempt from the one engine whose whole job
is to price a specific pair's book. A cached or misread pair there produces a slippage
number that is in range, plausible, and about the wrong market. Raised with the lead as a
field-list question, since spec 96 fixes the payload and B2 is building against the spec.

### The Phase 4 equity replay drove an invested account as though it were all cash

**Agent:** C (verification and interface), session 3 · **Task:** the lead's job 1 ·
**Date:** 2026-09-16

**What happened.** Three tests in `tests/verify/test_phase4_criteria.py` fail, all with the
same message:

```
criterion raised - ValueError: live.drawdown_pct is not a decimal: None
```

`test_every_phase_4_criterion_passes_against_the_real_repository`,
`test_a_memory_engine_that_drops_the_closed_trades_is_a_fail` and
`test_a_memory_engine_that_drops_the_resting_orders_is_a_fail`. The criterion is
`memory_writes_safety_inputs_live` — the one that closes the project's single forward
dependency by reading the same six `safety` numbers out of B's Phase 0 seed and out of C's
engine 19.

**Why.** Nothing is wrong with engine 19. C-models changed it, correctly and by the lead's
ruling, so that an absent `positions_value` no longer means a position worth nothing:
`decimal_field` returns `Decimal(0)` for a missing field, and on a fully invested account
`equity = cash + 0` is a drawdown approaching 100% against the stored peak — an account
frozen by a missing quote. Engine 19 now reads `store.count_open_positions()` and, where
positions exist with no mark published, writes **no** equity row and names
`equity_skipped_reason`.

`_replay_seed_through_memory` in `scripts/verify.py` — mine — had already written the seed's
open positions into the live database at step 2, and then drove its two equity ticks at step 4
with `state["exchange"]["balances"]` **and nothing else**. Under the new rule both rows are
correctly skipped, `equity_snapshots` is empty, `safety` reads `drawdown_pct: None`, and the
criterion's own `as_decimal` raises on it.

So the replay was asserting a number it was producing by accident. Its two ticks said *this
account holds positions and is entirely in cash*, which is not a state the system can be in;
the old engine 19 answered the contradiction by silently discarding the positions' value, and
the criterion passed on the arithmetic that came out. The new engine 19 refuses the
contradiction instead, which is what made it visible. **The replay was wrong before this
change and produced the right answer anyway** — that is the shape worth recording, not the
red.

**A second defect, found while confirming the first, and worse than it.**
`test_a_peak_equity_recomputed_from_this_tick_is_a_fail` is **green right now and green for
the wrong reason**. It induces spec 50's named mutation (`peak = equity`), expects a FAIL, and
asserts `"drawdown_pct" in outcome.message`. The criterion never reaches its comparison — it
raises — and `verify.py` renders the raise as a FAIL whose message is
`criterion raised - ValueError: live.drawdown_pct is not a decimal: None`. That string
contains `drawdown_pct`, so both assertions hold, and **the one test standing behind the
reason the replay drives two equity ticks rather than one has not exercised the criterion
since the engine changed.** It is the substring rule in `code-standards.md` — `match=` can
only ever say *at least this* — wearing a different hat: `in outcome.message` on a bare
`FAIL` cannot tell a disagreement from a crash. It went unnoticed because it kept passing,
which is the only direction of this defect nobody looks in.

**A third thing, and a habit paying off.** `tests/verify/test_phase4_criteria.py` was **mixed**
in the working tree — 867 CRLF lines against 62 bare LF — measured before touching anything,
per the rule C-models added to `code-standards.md` today. A multi-line anchor written with
`\n` would have matched only inside the 62-line region, and the refusal would have surfaced a
long way from the cause. Note that `grep -c $'\r$'` in this shell reported the file as
*uniformly* CRLF and was wrong about every file I checked; the byte count
(`b.count(b'\r\n')` against `b.count(b'\n')`) is the one to trust.

**Fix.** In `scripts/verify.py` and `tests/verify/test_phase4_criteria.py`, both mine. The
lead approved "give the two equity ticks a `position_manager` payload with `positions_value`
and `unrealised_pnl` from the seed's latest `equity_snapshots` row and cash of
`equity - positions_value`". **I built that, measured it, and it was not enough — so what
landed is one step further, and the step is the reason this entry is long.**

1. `_seed_equity_bounds` became `_seed_equity_ticks`, returning **two whole rows** as
   `SeedEquityRow` — the row that set the peak and the latest row — each carrying `ts`,
   `equity`, `peak_equity`, `cash`, `positions_value` and `unrealised_pnl`. The peak row is
   found by walking the series as `Decimal`, never by `SELECT MAX` on a money column.
2. Each equity tick now replays **its own row**: the balance is that row's `cash`, the mark is
   that row's `positions_value` and `unrealised_pnl`. Engine 19 adds them and has to *arrive
   at* that row's equity.
3. A new comparison, `_equity_composition_disagreements`, checks engine 19's latest
   `equity_snapshots` row against the seed's on all five money columns —
   `realised_pnl_cum` deliberately excluded, being a running total over whichever trades each
   producer has seen and the one column the two sides are not expected to agree on.
4. A new refusal, `_no_equity_row_written`, reports "engine 19 wrote no equity_snapshots row"
   **before** the six readings are compared, so the original symptom can never again reach
   `as_decimal` and arrive as a raise. The composition comparison is reported **after** the six
   readings, because those are the criterion's thesis and this is the fidelity underneath them.
5. `tests/verify/test_phase4_criteria.py`: two parsers, `disagreeing_readings` and
   `disagreeing_columns`, which refuse a message containing `criterion raised` and then
   **extract and compare the whole set** of what disagreed. The three induced-failure tests
   now assert `== ["drawdown_pct"]`, `== ["consecutive_losses"]`, `== ["resting_entry_orders"]`
   rather than `in outcome.message`. One new test,
   `test_a_memory_engine_that_stores_the_total_without_its_composition_is_a_fail`.
6. The file was rewritten as bytes to pure LF, 41,284 → 40,417 bytes, 867 CRLF → 0.
   `git diff --quiet` rc 0 either side: the blob never changed, because `.gitattributes` had
   been normalising it into the index the whole time.

**Why the approved fix was not enough, measured rather than argued.** With
`cash = equity - positions_value`, the arm *"the mark is read out of the wrong column"*
**survived**: `cash + positions_value` returns the seed's total for **any** mark whatsoever,
because the cash was derived to cancel it. The replay would have reproduced the number while
the composition behind it was free. Reading the row's own `cash` turns the addition into an
assertion, and that arm now dies. Phase 5's closing finding, in a new place: recompute what a
number was supposed to be computed from — do not rearrange it.

The composition columns also had **no reader at all** before this. `cash`, `positions_value`
and `unrealised_pnl` are stored because the Phase 7 alpha attribution reads the curve
*including its cash periods* — `0001_initial.sql` says so in a comment — and every test in the
project compared the total. A writer keeping the total and losing the split left every
`safety` reading correct and handed Phase 7 a portfolio that was never invested.

**Mutation sweep — seven arms, six killed, one equivalent control survived as designed.**
Arm: `tests/verify/test_phase4_criteria.py` alone, 47 tests, named because a narrow arm is
what the shared-checkout rule asks for. Target `scripts/verify.py`, byte copy taken before any
arm at sha256 `e59a8f00661112986be8649f159b3c972c34d977f9a840cae3f5912d1a5953ab`, every anchor
asserted to occur exactly once, every restore written and its sha256 compared **in the same
statement** — `sha((path.write_bytes(original), path.read_bytes())[1]) == before`, a tuple and
not an `or`, because `write_bytes(...) or sha(...)` short-circuits on the byte count and
compares nothing. All hashes matched at the end of the sweep. Baseline green before it started.

| Arm | Mutation | Result | Killed by |
|---|---|---|---|
| V1 | the tick's cash is its whole equity, so the position is counted twice | KILLED | `passes_against_the_real_repository`, `drops_the_closed_trades`, `drops_the_resting_orders`, `stores_the_total_without_its_composition` |
| V2 | the mark published out of the wrong column of the seed's own row | KILLED | the same four |
| V3 | no mark published at all — **the exact defect this job fixed** | KILLED | those four plus `a_peak_equity_recomputed_from_this_tick` |
| V4 | **EQUIVALENT CONTROL** — the compared columns listed in a different order | SURVIVED, as designed | — |
| V5 | one equity tick instead of two, so no peak is ever established | KILLED | the same four as V1 |
| V6 | the composition comparison dropped, leaving the six readings alone | KILLED | `stores_the_total_without_its_composition` — and **only** that one, which is the evidence the new test was worth writing |
| V7 | the unrealised mark published as zero | KILLED | `stores_the_total_without_its_composition`, `passes_against_the_real_repository` |

V2 is the arm that changed the design: under the lead-approved arrangement it is the arm that
**survived**. V6 is the arm that says the new comparison is load-bearing rather than ornamental
— one test kills it, and that test did not exist this morning.

**One refusal and one thing left unexplained, both recorded rather than tidied away.**

* The sweep's **first** run reported a red baseline — `1 failed, 46 passed` — and printed only
  the summary line, which named nothing, so nothing was mutated and the run was thrown away.
  Three captured re-runs were green. The harness now writes each arm's **whole** output to
  `scratchpad/sweep-logs/<arm>.log` before anything is concluded from an exit code, which is
  rule 5 applied to a harness rather than to a test: the first version's diagnosis could only
  ever have been "something failed".
* A **segmentation fault**, once, running `tests/verify tests/console tests/harness` together:
  a Windows access violation inside `re` at `scripts/verify.py:509`,
  `check_docs_vocabulary`'s `pattern.search(line)`, reached from
  `test_a_planted_term_in_a_current_state_section_fails`. That is the shape of catastrophic
  regex backtracking overflowing the C stack. It has not recurred in two runs of
  `test_docs_vocabulary.py` (24 passed each) or a full 780-test lane run, and the lane log
  carries zero further access violations. **Unexplained**, and written down as unexplained —
  `check_docs_vocabulary` scans `context/*.md`, three agents share this checkout, and a
  mid-save file is a plausible cause I have not demonstrated. Flagged to the lead because it
  is in a criterion that runs in every phase gate.

### Spec 99's map caught up to four engines, and one sentence was describing a repaired defect

**Agent:** C (verification and interface), session 3 · **Task:** spec 99, the lead's job 2 ·
**Date:** 2026-09-16

**What happened.** `tests/console/test_reason_prose.py`'s walking test went red naming
**fourteen** codes with no operator prose, across four engines that landed after session 2
stopped: engine 9 `order_book` (4), engine 14 `adaptive_router` (4), engine 18 `execution`
(2 of its 6), engine 22 `exit` (4). Engines 16 and 21 were already fully mapped — checked
against their own `contracts.py` rather than against any list, as the lead asked.

Separately, `console/format.py`'s sentence for `entry_unrecorded_at_exchange` said the system
"cannot describe it because `OrderState` carries no quantity or limit price", and that had
stopped being true.

**Why.** Two different causes, and only the first is the walk working as designed.

The fourteen are the seam doing its job: a code with no prose renders `"No reason was
recorded."` on the console **silently, with no error anywhere**, and the walk is the only
thing in the project that can notice. Four engines landing in one afternoon is exactly the
rate the walk was written for.

The stale sentence is the other kind. A's spec 84 amendment added `qty`, `limit_price` and
`opened_at` to `OrderState`; B then built the row; the lead narrowed
`REASON_ENTRY_UNRECORDED` to the single remaining case — **the exchange answering with no
`opentm`**, so the order cannot be dated — and introduced `REASON_ENTRY_RECOVERED` for the
ordinary crash-recovery case. Every one of those changes was correct, and **the sentence
survived all of them.** Nothing could have caught it: a stale sentence is not a failing test,
it is a screen that quietly misinforms whoever reads it at 3am. A listed it in its progress
file under a heading naming B and C rather than editing another agent's file, which is how it
reached me at all.

**Fix.** Fourteen sentences in `REASON_PROSE`, one rewrite, and **six new property tests** in
`tests/console/test_reason_prose.py` — because presence is the weakest thing that can be
asserted about a sentence, and the editorial decisions are where the value is.

The rewrite names the specific gap instead of a general inability: *"An order is resting at
the exchange and this system cannot tell when it was placed, so it was left unrecorded; find
it by its reference."* "when it was placed" rather than "`opentm`", because the operator reads
this screen and not Kraken's field list, and the `userref` pointer survives because that is
still the only thing an operator can act on.

The editorial decisions the new tests pin, each of which could otherwise be undone by a
well-meaning edit with nothing objecting:

- **Engines 9 and 22 cannot refuse, so none of their sentences may read as a refusal.** This
  is structural rather than stylistic for engine 9: `EngineStatus.OK` appears exactly once in
  the module and `BLOCK`, `PASS` and `ERROR` zero times. When it cannot price the book it
  publishes *no estimate* and engine 10 `cost` is what refuses, on the absence. A sentence
  saying "rejected" here sends the operator past the gate that actually stopped the trade,
  looking for one that does not exist.
- **Two of engine 22's codes and one of engine 18's are things the engine *did*, not
  refusals.** `exits_placed` with no sentence is the console narrating a placed stop-loss as
  silence.
- **`exit_incomplete` must say the position is still open.** `positions_closed` is false
  beside it. A sentence saying only "incomplete" leaves the one question that matters — *am I
  still holding this?* — unanswered on the screen whose whole job is to answer it.
- **Engine 14's four codes all mean "no weights" and mean four different things to an
  operator**, two ordinary states and two refusals to guess. `leaderboard_empty` is where
  every fresh clone lives and `no_model_beats_its_base_rate` is a *finding* — the tournament
  reporting, correctly and usefully, that nothing on it has edge. Neither may borrow "could
  not" from the two beside them.
- **One fact keeps one spelling and one sentence.** Engine 9 reuses engine 7's
  `no_quote_balance`; engine 22 spells its hold exactly as engine 21's
  `HOLD_DATA_GUARD_BLOCKED`. Both are now asserted between the two producing modules, so a
  parallel code cannot be minted quietly. Two vocabularies for one fact is how a `trades`
  table ends up carrying both "stop" and "stopped".
- **The prose and the contract are read in one test.** `test_the_unrecorded_entry_sentence_matches_what_order_state_can_now_carry`
  asserts `{"qty", "limit_price", "opened_at"} <= OrderState.model_fields` **and** that the
  sentence no longer claims the order is indescribable, **and** that it names the timing gap.
  That is the answer to the class of defect this entry is about: the sentence went stale
  because nothing held it against the contract it described, and now something does.

**Mutation sweep — fifteen arms, fourteen killed, one equivalent control survived as
designed.** Arm: `tests/console/test_reason_prose.py` alone, 178 tests. Targets
`src/acsoe/console/format.py` and the test file, both hashed as bytes before any arm, both
verified CRLF-free before the sweep started (the harness refuses outright on a CRLF target,
because an LF anchor would match nothing and the refusal would read as "the code moved").
Every anchor asserted to occur exactly once; every restore written and its sha256 compared in
the same statement that wrote it. All hashes matched at the end.

| Arm | Mutation | Result | Killed by |
|---|---|---|---|
| P1 | an engine 9 sentence reads as a refusal | KILLED | `no_engine_nine_sentence_reads_as_a_refusal` |
| P2 | the thin-book sentence stops naming the depth fetched | KILLED | `the_thin_book_and_the_unreadable_setup_are_not_one_sentence` |
| P3 | the unrecorded-entry sentence reverted to the one A's amendment falsified | KILLED | `the_unrecorded_entry_sentence_matches_what_order_state_can_now_carry` |
| P4 | the recovered entry borrows the already-placed sentence | KILLED | `no_two_codes_share_a_sentence`, `the_three_provenance_codes_are_three_sentences` |
| P5 | the incomplete exit stops saying the position is still open | KILLED | `the_incomplete_exit_says_the_position_is_still_open` |
| P6 | the empty leaderboard reads as a fault | KILLED | `the_two_ordinary_router_states_do_not_read_as_faults` |
| P7 | engine 14's base-rate sentence deleted | KILLED | the walk, `every_reason_code_adaptive_router_declares_has_prose`, `the_four_router_codes_are_four_sentences`, `the_two_ordinary_router_states_do_not_read_as_faults` |
| P8 | **EQUIVALENT CONTROL** — two entries swapped in declaration order | SURVIVED, as designed | — |
| P9 | the `OrderState` field set fabricated rather than read | KILLED | `the_unrecorded_entry_sentence_matches_what_order_state_can_now_carry` |
| P10 | engine 9's fetch-failure sentence deleted | KILLED | the walk, `every_reason_code_order_book_declares_has_prose`, `no_engine_nine_sentence_reads_as_a_refusal` |
| P11 | engine 22's placed-exit sentence deleted | KILLED | the walk, `every_reason_code_exit_declares_has_prose`, `the_exit_outcome_codes_do_not_read_as_refusals` |
| P12 | the engine 9 / engine 7 shared-code comparison pointed elsewhere | KILLED | `engine_nine_reuses_the_scouts_empty_balance_code` |
| P13 | the engine 22 / engine 21 shared-hold comparison pointed elsewhere | KILLED | `engine_twenty_two_spells_the_hold_exactly_as_engine_twenty_one_does` |
| P14 | engine 22's quiet tick reads as a refusal | KILLED | `the_exit_outcome_codes_do_not_read_as_refusals` |
| P15 | engine 18's recovered-entry sentence deleted | KILLED | the walk, `every_reason_code_execution_declares_has_prose`, `the_three_provenance_codes_are_three_sentences` |

**Every one of the six new tests was observed red at least once**, which is the question a
kill count cannot answer. P4 and P7 each killed more than one test, and in both cases the
*deliberate* assertion is a single one of them — A's Phase 6 finding about `opened_at`'s
mutation C6 applies here too: a high kill count is not evidence that the property is tested.

**One mutation deliberately not run, and what that costs.** Proving the prose-to-contract
coupling from the *contract* side means deleting `opened_at` from A's `OrderState`. A owns
that file, three agents share this checkout, and a live mutation in someone else's run
surfaces as a spurious failure they may report as real — the direction that hides a survivor,
which `code-standards.md` already records from Phase 4. P9 mutates the test's own expected
field set instead. **That proves the set is read from the real model rather than fabricated;
it does not prove that the model losing a field turns this test red.** Stated rather than
implied, because the gap is small and the habit of not stating it is not.

**A finding the warning list gave up, and it is not mine to fix.**
`test_the_inverse_is_reported_as_a_warning_and_never_as_a_failure` warns that `REASON_PROSE`
carries five sentences no engine publishes. Session 2 wrote that four are the seed
generator's older spellings and that `insufficient_depth` "is engine 9's, which does not
exist yet". Engine 9 exists now, so I went and looked, and **that sentence was half wrong in
a way worth writing down**: `insufficient_depth` is not an engine spelling at all. It is at
`src/acsoe/clients/store/seed.py:188`, written as

```
("order_book", "insufficient_depth", "Order book too thin to fill without 0.8% slippage")
```

— a seeded **rejection row attributed to engine 9**. Two things follow, and both are other
agents' calls:

1. **Two spellings for one condition.** The seed says `insufficient_depth`, engine 9 says
   `book_too_thin`, and they render two different sentences. That is exactly the divergence
   the two sharing assertions added above exist to prevent, arriving from the one direction
   they cannot see — a *fixture* rather than an engine.
2. **Worse, and the reason this is a finding rather than tidying: engine 9 cannot reject.**
   It has one return point and one status, `OK`, and it publishes an absent estimate rather
   than a refusal; engine 10 `cost` is what refuses. The seed writes a rejection *attributed
   to* engine 9, so the console will render a refusal from an engine that has no refusal
   path. The seed predates the engine and nothing has compared the two since.

`clients/store/seed.py` is B's and `engines/order_book/` is C-models'. Raised with the lead
with both paths named, not touched. Both sentences stay in `REASON_PROSE` meanwhile, because
the seeded rows exist and must still render — the alternative is silence on the console,
which is the defect this whole file exists to prevent.

### I told B2 engine 9 publishes no `pair`. It always did, and I had read the spec

**Agent:** C (engines and models), session 4 · **Task:** spec 96 · **Date:** 2026-09-16

**What happened.** B2 asked whether engines 9 or 14 publish a `pair`, because engine 16's
coherence walk checks any payload that carries one against `state["scout"]["pair"]`. I
answered that engine 9 does not, argued that it should, and asked the lead to amend spec
96's field list. The lead approved the amendment. **Engine 9 has published `pair` since
session 3 built it** — `SlippageEstimate.pair`, set from
`_require(state.get(SCOUT_KEY), SCOUT_PAIR_FIELD, SCOUT_KEY)`, verbatim from scout, and
written by `to_state_data`.

**Why.** I answered from **spec 96's step 4 field list**, which names
`estimated_slippage_pct`, `basis_notional` and `levels_consumed` and does not mention
`pair`. I had swept the engine's tests and read its refusal paths; I had not read its
payload model. This is the exact mistake the lead has now made three times from the other
direction — naming a mechanism without checking its signature against the job — and the
correction in both directions is the same: **build against the code, not against the
description of it.** I had been told that an hour earlier and then did the opposite.

**Fix.** Nothing in the engine. B3-store told that the field is already there, and my
message to B2 corrected. The spec amendment is still worth having, because a field list
that omits a field the engine publishes is a document that will mislead the next reader
exactly as it misled me.

**What the episode did produce, and it is worth more than the correction.** My argument to
the lead was about a **cached or misread** pair — a slippage number in range, plausible
and about the wrong market, with engine 10 pricing a hurdle on it. Checking the tests, the
published pair was asserted, but only ever on a single tick against a `state` built with
that same pair. **One tick cannot tell an echo from a cache**: the assertion is satisfied
by an engine that reads scout, by one that re-derives the pair from the book it fetched,
and by one holding the first pair it ever saw. Two sources agreeing by construction is the
witness problem, and it means the hazard I had just described to the lead was uncovered.

`test_the_published_pair_follows_scout_across_ticks_rather_than_being_cached` drives **one
engine instance over two ticks with different candidates** and asserts the published pair
follows scout each time, plus that the two slippage estimates differ — otherwise the pair
could be wrong with no observable consequence on this fixture. Mutation O6 caches the
candidate on the instance: **KILLED, by that test and by nothing else in 56**, which is
the answer to "which test killed it" and confirms it was the only cover.

### Decision: the aggregation across a version's folds, which spec 97 never named

**Agent:** C (engines and models) · **Task:** spec 97 step 3 · **Date:** 2026-09-16

The lead raised this after approving the weighting rule, and it is not obvious: the
leaderboard holds **one row per model version per fold**, and the rule weights **versions**.
There is an aggregation step between the rows and the weight, and the three candidates give
three different numbers.

**Options.** The unweighted mean of the per-fold skills; the most recent fold's skill; a
fold-count-weighted mean.

**Chose the unweighted mean**, which is the lead's prior and I agree with it. The question
engine 14 asks is *how good is this model version*, and each fold is one out-of-sample
measurement of it. A most-recent-fold rule encodes a judgement about recency; a
fold-count-weighted mean quietly rewards a version for having been around longer. The
unweighted mean is the only one of the three that does not add a second, unstated judgement
to the one being asked.

**Two things the lead did not ask about, and one of them changes the answer.**

**Duplicates are not folds.** B's `leaderboard_entries` docstring records that there is no
unique index on `(model_id, model_version, fold)` and that it deliberately returns *every*
match, so a broken idempotency convention stays visible rather than being collapsed by the
reader. Those rows reaching a mean-over-folds would weight one fold twice — a weighting
decision made by a duplicate row rather than by a measurement. So engine 14 keeps the
latest row per `(version, fold)` by `updated_at` and reports how many it collapsed in
`basis`. Absorbed silently, the duplicate would move the weight and leave nothing to notice
it by; collapsed and counted, the broken convention is still visible where B wanted it.

**Only this engine's own model family is weighted.** The leaderboard is keyed on
`(model_id, model_version, fold)` and nothing stops a second family appearing in it.
Weighting across families would put a predictor's Brier in a distribution with a score
measured on a different question, and normalising would hand that family part of the
predictor's weight. There is exactly one family today, which is precisely why this would
have been unnoticeable — and it is what spec 97's "at least two distinct `model_id`s"
requirement for the fixture is *for*, which I only understood once I had to build the
fixture.

**Cost.** The aggregation is **inert on the real table**: engine 20 writes one row per
`(version, fold)` and the fold's artefact run id *is* the version, so every real version has
exactly one fold and all three aggregations agree. The fixture is the only thing that can
tell them apart, and `test_the_mean_across_a_versions_folds_is_unweighted` asserts the
fixture still carries a multi-fold version — otherwise the branch is green and unreached.

### Spec 97 — eight mutations, eight killed, and which test killed each

**Agent:** C (engines and models) · **Task:** spec 97 · **Date:** 2026-09-16

Harness `scratchpad/mutate_ar.py`, same guarantees as the other sweeps: baseline first with
a refusal if it is red, byte copy before the mutation, sha256 compared in the same statement
that restores it, every anchor asserted to occur exactly once, witnesses hashed both sides
and unchanged on all eight runs. Arm `tests/engines/test_adaptive_router.py`. **Excluded and
named:** everything else, because engine 14 is inert — nothing downstream reads its payload,
so no other file could observe a change in it, and a wider arm would add runtime and no
coverage. R6 is the exception and it mutates *engine 15's* source, for the reason below.

| | Mutation | Verdict | Killed by |
|---|---|---|---|
| R1 | the clip at zero removed — spec 97's first named one | KILLED | the below-base-rate test and the whole-rule test |
| R2 | the mean across folds replaced by the most recent fold | KILLED | the aggregation test and the whole-rule test |
| R3 | the model-family filter dropped | KILLED | `test_a_second_model_family_is_not_weighted` |
| R4 | duplicate `(version, fold)` rows kept as separate folds | KILLED | `test_a_duplicate_row_for_one_fold_is_collapsed_to_the_latest` |
| R5 | the truncation tripwire removed from the windowed read | KILLED | `test_a_full_window_publishes_no_weights_rather_than_a_partial_distribution` |
| R6 | engine 15 reading engine 14's weights — spec 97's third named one | KILLED | `test_engine_fifteen_does_not_read_this_payload` |
| R7 | a missing base rate defaulted to 0.25 | KILLED | `test_a_version_with_no_base_rate_gets_zero_rather_than_a_default` |
| R8 | the approved rule starts using the regime — spec 97's second, made concrete | KILLED | `test_the_regime_does_not_change_a_single_weight` |

**R1 is the one worth reading, because it leaves everything looking right.** Removing the
clip lets a version with *negative* skill shrink the denominator, so every other weight goes
**above** its true share — and the weights still sum to one, every value stays in [0, 1], and
the below-base-rate version still reads lowest. Nothing about the shape of the answer says it
is wrong. What catches it is the whole-rule test recomputing the expected weights from the
fixture's rows by a second implementation, plus an explicit control asserting the best
version does *not* equal `0.45 / 0.30`, which is what the unclipped denominator would give.

**R6 had to be applied to engine 15, not to engine 14**, and that is the point of it. Spec
97's claim is about the *consumer* — that the skeptic's verdict does not depend on a weight —
and no mutation of engine 14 could ever show it. The test scans engine 15's own source and
contracts for this engine's state key, which is the structural form of the claim under
contract rule 3: engine 15 names every key it is allowed to reach, so the absence of
`adaptive_router` from that list is the guarantee.

**R8 is spec 97's second named mutation made buildable.** The spec says "the regime ignored
*if* the approved rule uses it" — the approved rule does not, so the informative mutation is
the inverse: make the rule start using it. A uniform regime factor would have been an
*equivalent* mutant, because normalisation cancels a constant, so the mutation boosts only
multi-fold versions when the regime is `trending`. That is what a regime-conditional rule
would actually look like, and it is killed by the test asserting the weights are identical
across all three regime labels.

**No survivors, so nothing was re-run wide.**

### Amendment: the lead's fold-aggregation ruling, corrected by what the store does

**Agent:** C (engines and models) · **Task:** spec 97 step 3 · **Date:** 2026-09-16

Correcting the Decision entry above with a new entry rather than editing it, per script rule
6. The lead has accepted the duplicate-row handling **as an amendment to ruling 3 rather than
as a detail of the implementation**, and the distinction matters enough to record.

Ruling 3 was "the equal-weighted mean across a version's folds". Written literally, and
applied to what `leaderboard_entries` actually returns, that weights a fold **twice** when
the table holds two rows for it — because B's read deliberately returns *every* match on
`(model_id, model_version, fold)`, there being no unique index, precisely so that a broken
idempotency convention stays visible rather than being collapsed by the reader.

So under the ruling as written, **a weighting decision would have been made by a data
artefact rather than by a measurement.** The amendment: collapse to the latest row per
`(version, fold)` by `updated_at`, and **report how many were collapsed** in `basis`. The
arithmetic stops depending on the artefact, and B keeps the visibility the store was built
to give — the duplicate is still discoverable, it just no longer moves a number.

The general form, which is the part worth carrying: **a rule stated over "folds" is not
stated over "rows", and the gap between them belongs to whoever wrote the read.** Neither
the spec nor the ruling could have caught this, because both were written against the
concept and the hazard lives in the storage.

### Why the fixture requirement I did not understand was the one that found the defect

**Agent:** C (engines and models) · **Task:** spec 97 step 6 · **Date:** 2026-09-16

Spec 97 requires the leaderboard fixture to carry **at least two distinct `model_id`s**, and
it does not say why. I read that as "make the fixture varied" and nearly wrote one family
with three versions, which satisfies every other clause in the step.

Building the second family is what made me ask what engine 14 should do with it — and the
answer is that it must be excluded entirely, because normalising across families hands one
family part of another's weight. **There is one model family on the real table today, which
is exactly why this would have gone unnoticed**: with a single `model_id` the filter never
fires, the weights are correct by accident, and no test, metric or review could distinguish
an engine that filters from one that does not.

So the requirement was load-bearing and I could not see it from the requirement. The
transferable part: **write the fixture the spec asks for even when the reason is not
stated**, because a fixture clause that looks like arbitrary variety is often the only thing
standing between a correct-by-accident branch and a measurement. Mutation R3 drops the
filter and dies on `test_a_second_model_family_is_not_weighted`; without that fixture row,
R3 is an equivalent mutant and the sweep reports a clean kill rate over a hole.

### Correction: the scipy import crash is the known native fault, not unexplained

**Agent:** C (engines and models) · **Task:** spec 97 · **Date:** 2026-09-16

I filed the wide-arm crash as `unexplained`. **That attribution is wrong and the lead
corrected it.** A `Windows fatal exception: access violation` is the signature of the native
memory fault in the tracker's Known Risks, open since Phase 0 and seen inside pydantic-core,
inside `sqlite3`'s C extension, inside pure-Python PyYAML and inside CPython's own
`ast.walk`. Four unrelated libraries, one of them not compiled, which is what process-level
memory corruption looks like and is not what any library defect looks like.

**The new site is `scipy._lib._array_api._make_capabilities_note` → `textwrap.dedent` →
`re.sub`, during `import sklearn`, before any test ran.** The locus is new; the signature is
not. My evidence fits it exactly — nothing of mine on the stack, the identical command clean
immediately afterwards, and `tests/engines/` green through the same imports an hour earlier.

The standing rule I should have applied first: **suspect the known native fault before
treating a one-off in an untouched path as a defect.** `unexplained` stays an acceptable
thing to write, and writing it where a documented mechanism already fits is not caution, it
is a second unexplained entry diluting a real one. Distinct from the Phase 5 scipy entry,
which was a `TypeError` during collection and remains genuinely unexplained.

### Correction: spec 96's field list was wrong, and that is half of the `pair` mistake

**Agent:** C (engines and models) · **Task:** spec 96 · **Date:** 2026-09-16

Correcting my own earlier entry with a new one, per script rule 6. I wrote that telling B2
"engine 9 publishes no `pair`" was my mistake for reading spec 96's field list instead of
`engines/order_book/contracts.py`. That is true and it is not the whole account: **the
field list was wrong.** The lead has amended spec 96 to list `pair`, with a note that the
engine always published it.

The general form the lead put on it, kept here because it is the reusable part: **a spec's
field list is a description; `contracts.py` is the fact, and where they disagree the spec
is what is wrong.** That is the same shape as spec 97 step 2 naming `leaderboard_entries`,
a method whose signature cannot enumerate — a conclusion written correctly and the nearest
plausible mechanism reached for without checking it against the job.

So the reading rule stands unchanged — build against the code — but the failure is not
only a reader's. A description that disagrees with the code will mislead every reader in
turn until somebody checks, and the fix is to correct the description rather than to
remember that a particular one was unreliable.

**What being wrong produced, which cost less than it returned.** The published pair had
only ever been asserted on single ticks, against a `state` built with that same pair — two
sources agreeing by construction — so a **cached** pair was uncovered in the one engine
whose output is defined by which market it walked. Mutation O6 caches the candidate on the
instance and now dies on `test_the_published_pair_follows_scout_across_ticks_rather_than_
being_cached`, and on nothing else in the file.

### Migration 0004 landed, and the double was simpler than the read in the one dimension that changed

**Agent:** C (engines and models) · **Task:** spec 97 close-out · **Date:** 2026-09-16

**What happened.** B3 landed `all_leaderboard_rows(*, model_id)` and `base_rate_brier`.
Engine 14 called `enumerate_all()` with no argument, which raised `TypeError` and was red
in B3's lane before it was red in mine. One line. But re-pointing the tests at the real
row model turned 15 of 26 red with `_Store._all() got an unexpected keyword argument
'model_id'` — **the test double had the old signature**, and it had been green for as long
as the engine and the double agreed with each other rather than with the store.

**Why that is worth an entry rather than a fix.** It is `code-standards.md`'s double rule
arriving from the direction that rule does not describe. The usual form is a double too
simple to exhibit the property under test. This one was faithful enough on the day it was
written and then **stopped tracking the thing it stood for**, silently, because nothing
compares a double's signature against the real method. The engine and the double moved as
a pair and the store moved separately.

**Fix, and the part that is not just a signature.** `_Store` now mirrors
`all_leaderboard_rows` faithfully — **including that the store filters by family itself**
— and records the `model_id` it was asked for. Modelling the filter honestly immediately
exposed something I had not seen: **on the enumerating path engine 14's own family filter
is redundant**, because the store has already applied it. The filter is only load-bearing
on the **windowed fallback**, which returns every family.

So `test_a_second_model_family_is_not_weighted` now drives the *windowed* store. Left on
the enumerating path it would have been green against an engine with no filter at all —
the store would have filtered for it — and mutation R3 would have become an equivalent
mutant without anything saying so. It is the witness rule again: two sources capable of
producing the same correct answer, and the test must drive the one where only the subject
can.

A new test asserts the store was **asked** for `MODEL_ID`, rather than asserting the rows
that came back, because a filtered result is equally consistent with the engine filtering
afterwards. Mutation R9 asks for a different family: killed by eight tests.

**B3's `model_id` being required rather than defaulted is right** and the reasoning is
worth keeping: the read has no `LIMIT`, and "no limit" is only safe because one model's
rows are bounded by its walk-forward while the table is bounded by nothing. A default
would hide the scope at the call site, which is the same fault as the truncating window.

### The truncation tripwire was wrong on the real read, and B3 found it by reading

**Agent:** C (engines and models) · **Task:** spec 97 close-out · **Date:** 2026-09-16

**What happened.** The tripwire was `len(rows) == _WINDOWED_PROBE` on **both** read paths.
B3 pointed out that against the unlimited read it fires on a model that genuinely has
exactly `_WINDOWED_PROBE` rows — a false positive costing that tick **all** of its weights.

**Why it was wrong.** "Came back exactly full" is a fact about a *limited* read. The
enumerating read has no limit, so the comparison is not a weaker version of the check, it
is a different claim that happens to share its arithmetic — and one that cannot
distinguish a truncation from a coincidence. Over 405 folds the coincidence is not
negligible.

**Fix.** The length check stays on the windowed fallback, where it is exactly right, and
is gone from the enumerating path. The lead's requirement that the detection survive B's
read as "the assertion that the fallback is unreachable" is met **by a test** rather than
by a runtime heuristic, which is what an assertion is. `test_a_window_that_did_not_fill_is_
weighted_normally` and `test_a_full_window_publishes_no_weights_rather_than_a_partial_
distribution` keep the fallback's behaviour pinned; R5 still kills.

**Found by a colleague reading the code.** No fixture would have had exactly that many
rows, so no test would ever have shown it, and the sweep would have reported a clean kill
rate over it. Worth recording as evidence that review catches a class of defect mutation
testing structurally cannot: a wrong branch that no input in the suite reaches.

### One red in B's lane that I could not attribute, and did not

**Agent:** C (engines and models) · **Task:** spec 97 close-out · **Date:** 2026-09-16

`tests/clients/store/test_store.py::test_all_leaderboard_rows_is_scoped_to_one_model`
failed once in a batch of 180 and passed on an identical re-run of the same batch, same
order, minutes later. B3 had told me it was landing that exact method at that time.

**I did not hash the file on either side, so I cannot prove it was a save rather than a
flake** — `code-standards.md` says to hash what is not the variable on both sides of an
A/B in a shared checkout, and I did not. The honest statement is that the evidence is
consistent with B3 mid-save and I cannot rule out the native fault. Recorded as B's, not
chased, and flagged to B3 rather than filed as a defect. Re-running in isolation passed,
which tells me nothing and is noted only so nobody treats it as having told me something.

### Spec 104, diagnosis — engine 19 read an errored engine as a refusal with no code

**Agent:** C (interface and models) · **Task:** spec 104 · **Date:** 2026-09-16

The diagnosis is A's (`a-platform.md`, "an ERROR anywhere in the opportunity chain leaves the
tick unrecorded"). This is where in engine 19 it happens, re-derived from the code and
reproduced before any change.

**What happened.** On a tick where an opportunity-chain engine raises, engine 19 raises too, so
the tick has no `block_records` row, no `rejections` row and no `equity_snapshots` row.
Reproduced on unmodified engines with a lighter chain than A's: guard 1, 2, 3, 4, 17;
opportunity 5, 7, 18 (no engine 16, so a real engine 18 raises `ExecutionError: decision.intent
is absent`); manage 19; the scripted market at tier 3 behind B's paper broker. Tick 2 logged two
`engine_error`s, engine 18's and engine 19's `MissingInputError: engine 'execution' refused
'BTC/USD' without publishing a 'reason_code'`, and `state["memory"] == {}`.
Probe: `scratchpad/c104/probe_error.py`, output `probe_error.log`. No model is trained: engine 7
ranks alphabetically while `scout.rank_feature` is absent, so engines 5 and 7 produce a real
candidate on flat bars, which is all the defect needs.

**Why, in `src/acsoe/engines/memory/engine.py`.** Two functions, each right about the case it
was written for:

- `_write_block_records` writes rows from `state["guard_blockers"]` only. An opportunity-chain
  blocker never enters that list (the orchestrator appends only in the guard chain), so no row
  can exist for it whatever its status.
- `_write_rejection` decides "this is a rejection" from two facts: the primary blocker is not a
  guard, and scout published a pair. **Neither fact says whether the blocker decided anything.**
  It then reads `reason_code` from the blocker's payload, which rule 7 has emptied, and raises
  on purpose. The raise comes after positions and orders are written and before
  `_write_equity`, so the tick is half recorded.

Until the lead's `state["block_status"]` landed, the only way to tell an error from a refusal
here was the empty payload, and that is also exactly what a gate that blocked **without** its
code looks like — the case the raise exists for. Now the orchestrator publishes the status, so
engine 19 can read the fact instead of inferring it.

**What the fix must keep.** A `BLOCK` with no `reason_code` still raises (a gate breaking its
contract). A guard that errored is still recorded from `guard_blockers` alone, with no second
row. And `is_primary` on the new row is true because the opportunity chain runs only when no
guard blocked, so the unique primary index cannot be hit twice on one tick.

### Spec 104, fix — engine 19 reads `block_status`, and the errored engine gets one row

**Agent:** C (interface and models) · **Task:** spec 104 · **Date:** 2026-09-16

**Fix**, in `src/acsoe/engines/memory/` only:

1. `contracts.py`: `BLOCK_STATUS_KEY = "block_status"` and `REASON_ENGINE_ERRORED =
   "engine_errored"`, both exported. The comment on `TRADING_BLOCKED_BY_KEY` no longer says
   that every non-guard blocker is a rejection.
2. `engine.py`: one helper, `_errored_opportunity_engine(state)`, returns the blocker's name
   only when `state["block_status"] == "ERROR"` and the blocker is not in `guard_blockers`.
   `_write_block_records` writes the guard rows exactly as before, then, if the helper names
   an engine, one more row: that name, `status` `ERROR`, `block_reason` `engine_errored`,
   `is_primary` true. `_write_rejection` returns 0 for the same case **after** the guard check
   and **before** it reads the candidate or any `reason_code`. Nothing else moved, so
   positions, orders and the equity row are written in their usual order.
3. `console/format.py`: `engine_errored` → "A check failed with an error before it could
   decide, so nothing was traded; the log for this tick says why". It says *failed* and not
   *refused*, and it points at the log, because the engine's own error is not on the row. My
   first draft also said repeated errors would freeze trading. I cut it: that is a threshold
   the row does not carry, and the table's rule is that no sentence adds one.
4. `README.md`: a section for the errored engine and the two neighbouring cases, and
   `block_status` in the table of keys read.

**Decisions made on the way.**

- **An absent `block_status` reads as "not an error".** The orchestrator always publishes it
  beside `trading_blocked_by`, so absence comes only from a hand-built `state`. The alternative
  was refusing the tick, which would turn every older hand-built test red without protecting
  anything the orchestrator can produce. With the key absent, a blocker with no code still
  raises, which is the fail-loud direction. `a_rejection()` in the test file now carries
  `block_status: "BLOCK"`, so the fixture looks like what the orchestrator actually publishes.
- **`block_reason` is `engine_errored`, not the orchestrator's `unhandled X: ...` text.** The
  spec and invariant 12 both say so. The exception text is in the log line the orchestrator
  writes for the same `(run_id, cycle_id)`, and the prose sends the operator there.
- **`is_primary` is hard-coded true, not derived.** The opportunity chain runs only when no
  guard blocked, so there is nothing to be primary against. If a hand-built `state` ever had
  both, the unique index `ux_block_records_primary` would refuse the second primary, and that
  refusal is the visible symptom this engine already relies on.

**A wrong turn, mine.** The first run of the new tests failed one of them with
`tick() got multiple values for keyword argument 'exchange'`: the guard-error test passed
balances *and* an empty `exchange` payload. The empty payload is the right one (an errored
guard's payload is `{}`), so the balances went. That one is a test typo, not a finding.

**The lighter chain, and why it counts as "a real raising engine".** The orchestrator test
runs guard 1, 2, 3, 4, 17; opportunity 5, 7, 18; manage 19, all real, at fee tier 3 behind
B's paper broker, with no trained model. Engine 18 raises its own `ExecutionError` because
engine 16 is not in the chain. That is the same raise A's probe produced with the full chain,
reached for less. Nothing about the status is hand-built. The test asserts that the tick had a
real candidate (`state["scout"]["pair"]`), because without one the old code never reached
the raise and the test could not have gone red.

### Spec 104 — six mutations of engine 19, six killed, and a control that survived everywhere

**Agent:** C (interface and models) · **Task:** spec 104 · **Date:** 2026-09-16

Harness: `scratchpad/c104/sweep104.py`. It takes a byte copy first, checks every anchor
occurs exactly once, sets `PYTHONDONTWRITEBYTECODE=1`, passes `-p no:cacheprovider`, uses
`sys.executable`, and restores in a `finally` before the next arm with the sha256 compared in
the same statement. It gives no verdict without a pytest summary line. `engine.py` is 0 CRLF,
LF only, counted in Python before the sweep. Before the sweep I also checked the `tests/verify/`
patchers that anchor on this file's text (`test_phase4_criteria.py`, ten anchors): each still
occurs exactly once after the change, and the control's line (`return len(blockers) + 1`)
occurs nowhere in `tests/` or `scripts/`. File sha256 before and after every arm:
`5b10da0c08f0eaf72f237a388e8eb1f7f2122bb213745d4084ab9778aa782712`. Narrow target:
`tests/engines/test_memory_rows.py`, with a baseline of `39 passed`. Logs:
`logs/verify/c104-sweep-*`.

| Arm | Mutation | Mutant sha256 | Verdict | Killing test (written for it) | Red message |
|---|---|---|---|---|---|
| M1 | the ERROR skip in `_write_rejection` → `if False:` (**ERROR treated as a rejection**) | `feb9c7858147…` | killed, `4 failed, 35 passed` | `test_an_engine_that_raised_is_recorded_through_the_real_orchestrator` (spec 104's named check) | `engine 19 raised on the errored tick` — the orchestrator logged `MissingInputError: engine 'execution' refused … without publishing a 'reason_code'` |
| M2 | `status=BlockStatus.ERROR` → `BLOCK` | `821d40b207e0…` | killed, `3 failed` | `test_an_errored_engine_writes_a_block_record_no_rejection_and_the_equity_row` | `engine 17's error rate counts status = 'ERROR'` / `'BLOCK' == 'ERROR'` |
| M3 | a `RejectionRow` written as well (`reason_code=engine_errored`) | `adb4d27cc819…` | killed, `4 failed` | orchestrator test, and `…writes_a_block_record_no_rejection…` | `an engine that raised refused nothing` |
| M4 | `process` returns before `_write_equity` on the errored path | `2c6d545b2c98…` | killed, `2 failed` | orchestrator test, and `…writes_a_block_record_no_rejection_and_the_equity_row` | `the errored tick has no equity row, so the tick was lost` / `assert 0 == 1` |
| M5 | the error inferred from an empty payload (`state.get(str(blocked_by)) != {}`) instead of `block_status` | `a7eddcb9d892…` | killed, `3 failed` | `test_an_engine_that_raised_and_a_gate_that_blocked_without_a_code_are_different_facts` and `test_an_errored_engine_is_never_asked_for_a_reason_code` | `DID NOT RAISE MissingInputError` / `[] == ['engine_errored']` |
| M6 | `is_primary=True` → `False` | `0dfa8ea5d79e…` | killed, `3 failed` | orchestrator test, `…with_no_candidate…`, `…writes_a_block_record…` | `(…, 0)] == [(…, 1)]` |
| E1 | **equivalent control**: `return len(blockers) + 1` → `return 1 + len(blockers)` | `58a20dffce58…` | survived: `39 passed` narrow; `1259 passed` wide | — | — |

**Which test killed what.** Every kill landed on a test written for that property. Two notes
beside them. M5 also killed the older `test_a_refusal_without_a_reason_code_raises…`, which is
the same fact seen from spec 50's side, so it is not an incidental kill. M1 also killed
`…different_facts`, whose second half runs the errored tick. The orchestrator test is red
under M1, M2, M3, M4 and M6, which is what spec 104's "Check When Done" asks of it. It is
**not** red under M5, and it should not be: its payload is `{}`, so inferring the error from
the emptiness gives the right answer there. The two hand-built tests are the ones that tell
the two readings apart.

**The control against the wider suite.** Baseline over `tests/engines tests/console
tests/verify/test_phase4_criteria.py tests/core`: `1259 passed, 1 warning in 363.50s`
(`logs/verify/c104-wide-baseline.log`). E1 over the same set: `1259 passed, 1 warning in
357.71s`. No crash and no native fault in either run. After the sweep the file's hash is the
same as before it, and `git status` shows only my lane's files.

### Spec 105, first runs — the new position carries no mark on its fill tick, and one unexplained raise

**Agent:** C (interface and models) · **Task:** spec 105 · **Date:** 2026-09-16

**What happened (1).** The first complete run of `paper_equity_continuous_across_fill` on the
real tree reached the fill and returned FAIL: `entry 1690626088 filled and the store holds 1
position(s) for it with no mark`. The chain did approve, place and fill the entry at tier 3,
and engine 19 wrote both equity rows. What stopped the criterion was my own reading of "the
mark": I took it from `positions.last_price`, and on the fill tick that column is NULL.

**Why.** Engine 21's `_mark` (B's) does not re-mark a position opened by this tick's fill.
It adds `qty * entry_price` to `positions_value` and publishes the row without `last_price`
or `unrealised_pnl`. Its docstring says such a position "is worth what was just paid for it,
and `last_price` on a position that has existed for no time is the fill price". So on the
fill tick the mark **is** the fill price, but it is recorded only through the equity row's
`positions_value`, never on the position row. From the next tick on, `last_price` is the bid.

**How the bound handles it.** I did not widen it. The mark now comes from the store in one of
two ways, and each is checked rather than assumed:

- if the position row carries a `last_price`, that is the mark;
- if it does not, the equity row's `positions_value` must equal `qty x fill price` **exactly**,
  with exactly one open position, and the mark-to-bid gap is then zero.

A position valued at anything else with no mark is a FAIL. The tolerance on the fill tick is
therefore the maker fee alone, which is the tightest honest bound.

**For B, not changed by me.** The docstring's "`last_price` ... is the fill price" reads as a
statement about the stored row, and the stored row says NULL. The console would show that
position with no mark for one tick. This is reported to the lead as an observation, not a
defect; the engine is B's.

**What happened (2).** The very first invocation, through a throwaway script that called
`run_criterion`, returned after 0.7 s with `criterion raised - TypeError: 'float' object is
not callable`. That is before any training could have started. I did not keep a traceback.
Three later runs of the same code (one calling the check directly, two with a traceback
handler) did not reproduce it. The shape, a nonsensical `TypeError` once with no
reproduction, fits the registered native fault's corrupted-interpreter family (B's
`'MappingEndEvent' has no len()` today). I checked the other mechanisms: no stale `.pyc`
(`PYTHONDONTWRITEBYTECODE=1`), no concurrent writer (I am alone in the checkout), and no
tmp-dir sweeper symptom. Without the traceback this cannot be proven, so it is recorded as
**consistent with the native fault, not attributed**. The harness now keeps tracebacks.

### Spec 105 — my PENDING test ran the whole chain and reported PASS, because `bare_tree` is not an absent subject

**Agent:** C (interface and models) · **Task:** spec 105 · **Date:** 2026-09-16

**What happened.** My first PENDING test pointed the criterion at `bare_tree`, as spec 100's
`test_pending_on_a_tree_with_nothing_built` does. It came back **PASS**: the criterion
trained its subject, drove three ticks and judged the fill, all against a tree with no
`src/`.

**Why.** The editable install makes the real `acsoe` importable from any directory, and
pytest puts the repository root on `sys.path`, so `tests.harness` resolves as well.
`root_import_path` only shadows what the tree actually carries. `unbuilt_tree` in
`tests/verify/conftest.py` exists for exactly this and says so in its docstring. I had not
read it.

**Fix.** The test uses `unbuilt_tree`, an empty `acsoe` package that shadows the real one.
There the criterion is PENDING and names engine 9 and spec 96, the first engine it needs.

**For the lead, and it is spec 100's rather than mine.** Spec 100's nine criteria pass
`test_pending_on_a_tree_with_nothing_built` on `bare_tree` only because their bodies end
in a hard-coded PENDING ("not written yet"). The day a body is written, the same test will
run the real chain from the real repository and report PASS or FAIL on "a tree with nothing
built". That test should move to `unbuilt_tree` when the bodies land.

### Spec 105 — the criterion, observed PENDING, PASS and FAIL, and the broker broken in place

**Agent:** C (interface and models) · **Task:** spec 105 · **Date:** 2026-09-16

**What landed.**

- `scripts/verify.py`: `check_paper_equity_continuous_across_fill`, registered for phase 6 after
  spec 100's nine. `_trained` and `_constructed_dataset` gain an optional `macro_archive`,
  passed to `build_dataset` only when given, so the Phase 5 criteria train exactly as before.
- `tests/verify/test_phase6_criteria.py`: five tests. `EQUITY_ACROSS_FILL` is kept out of
  `PHASE6_CRITERIA`, so the parametrised real-tree PENDING test does not gain a ninth red.
- `tests/verify/test_runner.py`: the phase-6 set now includes the new name.

**The subject** is A's spec 87 rehearsal, rebuilt from verify.py's own pieces.
`_constructed_candles` is the same formula as `tests/research/test_training.py`, trained over
four folds with `btc` joined from `AAAUSD`, and the replay window ends 200 bars before the
series end. All 21 engines are real and run in registry order. The chains are hand-built
because spec 82 is held, and the docstring says to read `bootstrap.py` once it lands. The
market is the scripted market at fee tier 3 behind `PaperBroker`, and the store is a real
`StoreClient` in a temporary directory. The ticks are quiet, entry, then a planted trade at
`limit x 0.999`, then the fill tick. Training costs about 30 s and is cached per repository
root, like `_TRADE_SUBJECTS`; the store and the broker are never cached. A whole run takes
about 32 s.

**The tolerance.** It is read from the store alone:

- the fee, quantity and fill price come from the entry's `orders` row;
- the mark comes from the `positions` row's `last_price`, or, when that is empty, the fill
  price, but only if the equity row's `positions_value` is exactly `qty x fill price` with one
  open position;
- `tolerance = fee + qty x |mark - fill price|`, and the verdict is
  `|equity(fill tick) - equity(entry tick)| <= tolerance`.

It also checks that the row before the fill is the entry tick's (`cycle_id - 1`). On this
subject the mark gap is zero, so the bound is the maker fee alone, and equity moved by exactly
minus the fee.

**Observed messages, verbatim.**

PASS (real tree, `logs/verify/c105-probe-real-3.log`):

> equity 5000.00 on cycle 2 and 4996.3343443507499 on the fill tick, cycle 3: it moved -3.6656556492501. The fill's own cost is 3.6656556492501: fee 3.6656556492501 + 26.26015939 x |mark 126.9 - fill 126.9|, recorded for BTC/USD entry 1690626088 (notional 3332.414226591); at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers

FAIL (the real `broker.py` broken in place, arm B1, `logs/verify/c105-inplace-B1-unrecorded-fill-excluded.log`):

> equity 5000.00 on cycle 2 and 8332.414226591 on the fill tick, cycle 3: it moved 3332.414226591. The fill's own cost is 3.6656556492501: fee 3.6656556492501 + 26.26015939 x |mark 126.9 - fill 126.9|, recorded for BTC/USD entry 1690626088 (notional 3332.414226591). Equity moved by more than the fill cost, so the cash and the position disagree about when the fill happened. The paper ledger must count every fill the broker has executed, recorded or not (invariant 2, spec 103); otherwise the notional is counted twice and peak_equity carries it into engine 17's drawdown; at fee tier 3, reference friction about 0.65% round trip and a hurdle of 1.625%; tier 1 is a no-trade regime at the current barriers

`8332.414226591` is A's finding-1 figure to the digit.

PENDING (`unbuilt_tree`): the message names engine 9 `order_book` and spec 96, and then "will run
at fee tier 3 ...".

**The in-place cross-lane run**, approved by the lead and made once through
`scratchpad/c104/sweep105.py`. It takes a byte copy of `src/acsoe/clients/paper/broker.py`
(0 CRLF, anchor `for userref, executed in list(self._executed.items()):` exactly once, and no
test or script anchors on it), restores in a `finally`, and compares the sha256 in the same
statement. `PYTHONDONTWRITEBYTECODE=1`, `sys.executable`, `-X faulthandler`.

| Arm | Mutation | Mutant sha256 | Result |
|---|---|---|---|
| B1 attempt 1 | `... in []:` | `c15e1c2a…bfa0a4c1` (A's B1, identical) | **no result**: exit `0xC0000005`, empty output. The registered native fault, not counted. Log moved to `logs/verify/c105-crashed/B1-attempt1.log` |
| B1 attempt 2 | same | same | **FAIL**, quoted above |
| B0 control | `list(...)` → `tuple(...)` | `f5a55ae4…73cc8d7` | PASS, identical numbers to the real tree |

The broker's sha256 was `98c0df710256e4fb65c0e9dc6bf58acca6547eb2e38c7a088be01e28c70e6201`
before and after every arm, and `git status` never showed it modified. The committed FAIL test
makes the same break in the copied `phase6_tree`, never in the real file, and hashes the real
file on both sides.

### Spec 105 — eight mutations of the criterion: six killed, one equivalent, one control

**Agent:** C (interface and models) · **Task:** spec 105 · **Date:** 2026-09-16

Harness: `scratchpad/c104/sweep105v.py`, the spec 104 harness pointed at `scripts/verify.py`
(0 CRLF; every anchor exactly once in the file and absent from `tests/`), with a byte copy, a
`finally` restore and the sha256 in the same statement. File sha256 before and after every
arm: `f2299ae8fb19a000b633e4e29833e629a6348858fbdb539826c42ed03b5e0844`. Narrow target:
`test_phase6_criteria.py -k equity_across_fill`, baseline `4 passed` (then `5 passed` once
the V7 test existed).

| Arm | Mutation | Mutant | Verdict | Killing test |
|---|---|---|---|---|
| V1 | tolerance also admits the notional | `87a0e497…` | killed, 2 failed | `…fails_when_the_broker_leaves_out_an_unrecorded_fill` (the defect passes); `…passes_on_the_real_tree` (bound != fee) |
| V2 | the comparison is `if True:` | `73308f43…` | killed, 1 failed | `…fails_when_the_broker_leaves_out…` |
| V3 | tolerance is `Decimal("5")` | `0b23fa5d…` | killed, 1 failed | `…passes_on_the_real_tree` (bound != fee). The FAIL test stayed red because 5 is below the notional, so a constant is caught only by the test that pins the bound to the fee |
| V4 | the fee is left out of the bound | `87afe97b…` | killed, 2 failed | `…passes_on_the_real_tree` (moved -fee is outside a zero bound) |
| V5 | PASS message without the tier sentence | `b60f05b4…` | killed, 1 failed | `…passes_on_the_real_tree` |
| V6 | the no-mark branch accepts any value (`elif True:`) | `9e2af240…` | survived narrow and wide (checked negative) | — the very next check (`positions_value != qty x mark`) refuses the same values, so the branch only chooses the message. Recorded as a checked negative, not a survivor |
| V7 | the entry-tick check becomes `if False:` | `5c64c500…` | **survived the first sweep**; killed after a new test, 1 failed | `…fails_when_the_entry_tick_wrote_no_equity_row`, written for it. It makes engine 19 skip the entry tick's equity row in the copied tree, so the last earlier row is the quiet tick's, which compares clean |
| E2 | control: `moved = -(before - after)` | `b62a5c03…` | survived narrow and wide | — |

**Survivors against the wider set.** The wider set was the whole of
`tests/verify/test_phase6_criteria.py` and `tests/verify/test_runner.py`. The baseline was
`8 failed, 53 passed`, and the 8 are the known
`test_pending_on_the_real_tree_names_the_subject_and_the_spec` parametrisations
(`logs/verify/c105-verify-wide-baseline.log`). V6 and E2 each gave `8 failed, 53 passed` with
**the same eight**. My harness printed "KILLED" for both because it reads the exit code and
does not compare against the baseline set; the failing sets are identical, so both survived.
**A correction to my own tool, recorded rather than hidden:** a verdict over a red baseline
has to compare failing sets, which `code-standards.md` already says.

**No ninth red.** The new criterion runs to PASS on the real tree, so it is not in
`PHASE6_CRITERIA` and does not join that parametrised test's failures.

### Spec 105 — the gate at the spec 105 boundary

**Agent:** C (interface and models) · **Date:** 2026-09-16

The tree is `3e1ded8` plus `scripts/verify.py`, `tests/verify/test_phase6_criteria.py`,
`tests/verify/test_runner.py`, this log and my progress file. I was the only agent in the
checkout, and nothing was running beside the gate. The four commands ran one after another,
each redirected to its own file, and each file was read in full.

| Command | Result | Log |
|---|---|---|
| `pytest tests/ -q` | `8 failed, 3197 passed, 2 skipped, 3 warnings in 1383.05s`; all 8 are the known `test_pending_on_the_real_tree_names_the_subject_and_the_spec` parametrisations | `logs/verify/c105-gate-pytest.log` |
| `mypy --strict src/ scripts/` | `Success: no issues found in 153 source files` | `logs/verify/c105-gate-mypy.log` |
| `ruff check src/ tests/ scripts/` | `All checks passed!` | `logs/verify/c105-gate-ruff.log` |
| `verify.py --phase 6` | `12 criteria: 2 PASS, 1 FAIL, 9 PENDING`; `paper_equity_continuous_across_fill` PASS, and `toolchain_green` FAIL on the same 8 (its own run: `8 failed, 3197 passed, 2 skipped`, no other failure) | `logs/verify/c105-gate-verify.log`, `logs/verify/toolchain_green/20260916T201415_806009-pytest-attempt1.log` |

The suite grew by 5 tests over spec 104's boundary (A's gate had 3165 passed). No native fault
crashed any of the four runs.
