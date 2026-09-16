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
