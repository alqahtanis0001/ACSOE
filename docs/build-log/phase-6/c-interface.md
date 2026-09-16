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
