# Build log — Phase 4 — c-interface

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem and its
fix, and every decision where two approaches were viable.

**Rule 1 is now diagnosis-before-fix.** Write **What happened** and **Why** the moment you know
why something is broken, *before* you write the fix; come back and add **Fix** afterwards. The
code survives on disk whatever happens to the session; the reasoning that found it does not.
Phase 3 opened with an interruption that took every build log and no progress file, because
progress files are written before the work and logs were being written after it.

Minimum headings per entry: What happened, Why, Fix.

Two habits Phase 3 turned into standards, both of which belong in entries here:

- **Break the code and watch the test go red**, then put it back, and say in the entry that you
  did. A test nobody has seen fail is a claim, not a check. A mutation that survives a *subset*
  of the suite has not survived — it has not been asked.
- **Record what you checked and found sound**, not only what you found broken. An audit that
  lists hits alone says nothing about coverage.

The lead consolidates these into `docs/build-log/phase-4.md` at phase close.

## Entries

### The "no criterion reads a gitignored path" test is a whole-file scan, and Phase 4 adds the first `--live` criterion

**Agent:** C · **Task:** spec 48 · **Date:** 2026-09-11

**What happened.** Registering the Phase 4 criteria turned
`tests/verify/test_phase0_criteria.py::test_no_phase_zero_criterion_reads_data_models_or_logs`
red on a single line of `check_replay_full_archive`:

```
AssertionError:     archive_dir = ctx.root / "data" / "historical"
assert '"data"' not in 'archive_dir..."historical"'
```

**Why.** The rule the test enforces is real and I am not weakening it: `data/`, `models/` and
`logs/` are gitignored, so a criterion that depends on anything inside one passes only on the
machine that produced it. But the test implements that rule as a **line scan over the whole of
`scripts/verify.py`**, and that implementation was only ever correct because no criterion in
Phases 0 to 3 was `--live`. `replay_full_archive` is the first one in the project, and reading
`data/historical/` is the entire point of it — spec 48 criterion 8 names the directory, and
`ai-workflow-rules.md` says a `--live` criterion is opt-in and never required for a phase to be
green. So the scan is now reporting a sanctioned exception as a defect.

The Phase 3 equivalent, `test_no_phase_3_criterion_touches_a_gitignored_directory`, does not
have this problem: it walks `inspect.getsource` **per criterion**. That is the shape the rule
wants, because the rule is about criteria rather than about the file they happen to live in.

**Fix.** The Phase 0 test now scans the source of each **registered non-live** criterion via
`inspect.getsource`, in every phase, instead of the file's raw lines — so it covers strictly
more than it did (it now reaches Phases 1 to 4's criteria, which the phase-0-named test never
claimed to but which the whole-file scan was incidentally providing) and it stops judging the
one criterion the project deliberately allows to read a gitignored path. A companion assertion
pins the exception: `replay_full_archive` must be registered `live=True`, so the day somebody
registers it as an ordinary criterion the test goes red rather than silently admitting a
gitignored read into the green path.

**Proved capable of failing.** Registering `replay_full_archive` with `live=False` turns the
new assertion red; putting `ctx.root / "data"` into a non-live criterion turns the scan red.
Both observed before this entry was closed.

### B's spec 51 read made a Phase 3 mutation anchor ambiguous

**Agent:** C · **Task:** spec 48 (found while running the suite) · **Date:** 2026-09-11

**What happened.** `tests/verify/test_phase3_criteria.py::test_an_outage_counted_by_cycle_id_is_a_fail`
went red with

```
AssertionError: acsoe.clients.store.client: anchor appears 2 times, expected exactly once.
The engine moved underneath this test and the induced failure would not be the one it claims
to induce.
```

**Why.** That test induces the Phase 3 outage defect by rewriting the one
`ORDER BY ts DESC, run_id DESC, cycle_id DESC` in `clients/store/client.py` to order by
`cycle_id` first. B is adding the bounded most-recent-N `block_records` read for spec 51 and
has — correctly — used the same ordering, so the anchor now matches two queries. Nothing is
broken in B's code and nothing is broken in the Phase 3 criterion. The guard inside
`patch_module` did exactly its job: it refused to apply an ambiguous patch rather than silently
mutating the wrong query and leaving a test that FAILs for a reason it does not name.

This is a defect in **my** test, in C's lane, not in B's store. It is recorded here rather than
raised to B.

**Fix.** Deferred until B's spec 51 read has landed and stopped moving, then the anchor is
re-cut against a string unique to the outage walk rather than against the bare `ORDER BY`.
Re-cutting it against a half-saved file is how an induced-failure test comes to induce a
different failure.

**Resolution, same day.** No fix was needed and none was made. B's spec 51 work landed a second
read — `recent_blocked_ticks` — whose ordering is `ORDER BY ts DESC, cycle_id DESC, run_id DESC`,
which is a different string from the outage walk's `ORDER BY ts DESC, run_id DESC, cycle_id DESC`.
The anchor is unique again and `test_an_outage_counted_by_cycle_id_is_a_fail` passes. The
transient duplicate was a half-saved file, exactly the case the task list says to judge by path
and leave alone. Recorded rather than deleted because the *next* store read with that ordering
will break the anchor again, and the entry is the note that says where to look.

### Decision: engine 19 derives a rejection from `state` rather than being handed a list of them

**Agent:** C · **Task:** spec 50 · **Date:** 2026-09-11

**Options.** Either an upstream engine publishes `state[...]["rejections"]` as a ready-made list
of rows and engine 19 writes them out, or engine 19 works out for itself that this tick was a
rejection and builds the row from what the chains already publish.

**Chose.** Derivation. A rejection exists when `state["trading_blocked_by"]` names an engine that
is **not** among this tick's `guard_blockers` *and* `state["scout"]["pair"]` carries a candidate.
The economics come from the blocking engine's own payload, where it published them.

**Because.** There is no engine that aggregates rejections. The gates each publish their own
`reason_code`, the orchestrator sets `trading_blocked_by`, and inventing a new publisher would
have meant asking the lead for a `state` key and B for an engine change — for information already
in `state`. More to the point, the two halves of the test are both necessary and neither is
obvious: "a candidate exists" alone records a rejection on every tick where `data_guard` blocked
*after* `scout` had run, and "the guard chain did not block" alone loses a rejection on a tick
where a guard blocked as well. A pre-made list would have skipped that derivation entirely, and
the criterion driving it would have tested a list-copier.

**Cost.** Engine 19 has to know the candidate's `state` path and the economics field names. They
are declared in `engines/memory/contracts.py` with the owning engine written beside each one —
the same thing `engines/cost/contracts.py` does — so no engine is imported, but a key renamed
upstream is silent here until someone greps. That is written into this engine's README.

### Spec 49: six mutations, six reds

**Agent:** C · **Task:** spec 49 · **Date:** 2026-09-11

Every assertion in `tests/engines/test_memory.py` was written, then broken, then watched go red,
then put back. The store is the real `StoreClient` over a temporary database throughout — a
double that accepts any row and remembers nothing cannot fail a test about what was written.

| # | Mutation in `engines/memory/engine.py` | Red message |
|---|---|---|
| 1 | `is_primary=index == 0` → `is_primary=True` | `sqlite3.IntegrityError: UNIQUE constraint failed: block_records.run_id, block_records.cycle_id` — the database refuses the second primary, which is the index doing its job |
| 2 | `is_primary=index == 0` → `is_primary=False` | `assert False is True` on `bool(rows[0]["is_primary"])` |
| 3 | `enumerate(blockers)` → `enumerate(blockers[:1])` (write only the primary) | `Right contains one more item: 'safety'` — the two-guard tick recorded one row |
| 4 | a `BlockRecordRow` written unconditionally when the blocker list is empty | `Left contains one more item: {'id': 1, 'cycle_id': 9, ...}` on the unblocked tick |
| 5 | an early `return 0` unless `state["scout"]["pair"]` is set (write only on ticks that had a candidate) | `assert 0 == 1 where 0 = len([])` — the candidate-less blocked tick wrote nothing, which is the defect that makes the breaker inert |
| 6 | `status=BlockStatus(str(entry["status"]))` → `status=BlockStatus.BLOCK` | `- ERROR / + BLOCK` — the error-rate input reads zero forever under this one and nothing raises |

Mutation 5 is the one that matters most and it is the one an ordinary review would not have
produced: the mutated engine is *coherent*. It writes a row for every rejection, it never
double-counts, and every test about rejections still passes. It only fails against a tick that
never had a candidate — which is most blocked ticks, because `data_guard` blocks in the guard
chain before the opportunity chain has run at all.

Mutation 1 is worth a second look for the opposite reason: it fails at the **database** rather
than at an assertion. That is `ux_block_records_primary` refusing to let two engines both claim
to have gated the opportunity chain, and it is why the engine does not catch `IntegrityError`
to keep a tick alive — contract rule 7 turns it into an `ERROR` result, which is the visible
symptom that catching it would suppress.

### A surviving mutation: no test covered "balances fetched, reporting currency not in them"

**Agent:** C · **Task:** spec 50 · **Date:** 2026-09-11

**What happened.** Spec 50 names "a zero equity row written when no equity is available" as a
mutation that must be observed red. I applied it in the narrowest honest form — when the
reporting currency is absent from the fetched balances, substitute `"0"` instead of skipping the
row — and **the whole of `tests/engines/test_memory_rows.py` stayed green: 18 passed.**

**Why.** `_write_equity` has three separate ways to decide there is nothing to record, and I had
written tests for two of them:

1. `state["exchange"]` absent entirely — engine 1 is not in the chain. Covered.
2. `state["exchange"]["balances"]` is `None` — engine 1 ran and the fetch failed, which is
   invariant 2's ordinary case. Covered.
3. `balances` is a real mapping that does not contain the reporting currency. **Not covered.**

The third is not a hypothetical: it is what a Kraken balance response looks like for an account
holding only crypto, or one whose USD balance is exactly zero and therefore omitted. The
mutation only reaches branch 3, so nothing objected. This is the case `code-standards.md`
describes as coverage disagreeing with mutation and the mutation being right — every line of
`_write_equity` was executed by the suite, and the branch nobody asserted on was the one
everybody ran past.

Worth recording in its own right: had I taken the mutation's survival as "the assertion is
strong enough, the mutation was unrealistic", the gap would have stayed. It was the mutation
that produced the finding, not the review.

**Fix.** A third test, `test_a_balance_response_without_the_reporting_currency_writes_no_row`,
asserting no `equity_snapshots` row and a skip reason naming the currency. The mutation was
re-run against it and went red.

### Spec 50: eight mutations, six red on the first pass and two gaps found

**Agent:** C · **Task:** spec 50 · **Date:** 2026-09-11

| # | Mutation in `engines/memory/engine.py` | Result |
|---|---|---|
| 7 | `peak = equity if previous is None else max(previous.peak_equity, equity)` → `peak = equity` | **red** — `At index 1 diff: '900.00' != '1000.00'`. This is the named one: it makes the drawdown permanently zero and the breaker permanently blind, and nothing raises |
| 8 | a `"0"` balance substituted when the reporting currency is missing | **survived**, and it found a real gap — see the entry above. Red after the third test was added |
| 9 | the `reason_code` guard removed (`if not reason_code:` → `if False:`) | red |
| 10 | `realised_cum` recomputed from this tick alone | red |
| 11 | `equity = cash + positions_value` → `equity = cash` | red |
| 12 | `open_position_count` counted from `state` instead of read back from the store | **survived** — second gap, see the entry below. Red after the new test |
| 13 | rows stamped with the publisher's `run_id` (`setdefault` instead of assignment) | red |
| 14 | a guard-chain block recorded as a rejection as well | red |

### A second surviving mutation: `open_position_count` from `state` and from the store were never made to disagree

**Agent:** C · **Task:** spec 50 · **Date:** 2026-09-11

**What happened.** Mutation 12 — count the open positions from `state["position_manager"]`
instead of reading `store.count_open_positions()` — left all 19 tests green.

**Why.** Every test I had written supplied the same answer on both sides. The absent-key test has
zero positions in `state` and zero in the store; the equity test publishes one position and
therefore has one in each. The two sources agree in both fixtures, so no assertion could
distinguish them. This is the *double must be capable of exhibiting the property* rule turned
around: the fixture, not the double, was simpler than the real thing in exactly the dimension the
test was about.

The two sources genuinely differ in the live system, and the difference matters. A position
opened on tick 40 is still open on tick 41; whether engine 21 republishes it in `state` on every
subsequent tick is engine 21's business and it is Phase 6, whereas the `positions` table is the
record. A count taken from `state` reports the account as flat on any tick where the publisher
said nothing — and `open_position_count` is what the Phase 7 attribution reads to separate cash
periods from invested ones.

**Fix.** `test_the_position_count_comes_from_the_store_not_from_this_tick_s_state` opens a
position on one tick and then runs a second tick whose `state` carries no `position_manager` key
at all, asserting the snapshot still counts one. The mutation is red against it.

### `purged_walk_forward` refused half a test window only when it had rows

**Agent:** C · **Task:** spec 53 · **Date:** 2026-09-11

**What happened.** `test_half_a_test_window_is_refused` went red on the first run:
`Failed: DID NOT RAISE MissingSettingError`.

**Why.** The function returned early on an empty label list *before* it validated the
`test_start_ts` / `test_end_ts` pair. So `purged_walk_forward(rows, test_start_ts=X)` with rows
raised — "pass both, or neither" — and the same call with no rows returned `[]`, silently. Two
different situations arriving through one channel and being answered as though they were one:
"there were no labels to split" and "the caller asked for a window whose other side this module
would have to invent". A caller filtering a label frame down to one pair, getting nothing back,
and reading `[]` as "no folds here" would never learn that its call was malformed.

That ordering was not a considered decision; the empty guard was written first and the argument
validation was appended below it, which is how this class of defect usually arrives.

**Fix.** The argument validation moved above the empty-rows return, so a malformed call raises
whatever the data looks like. The test was written before the fix and is what found it.

### Spec 53: all three named mutations red, on the unit tests **and** on the criterion

**Agent:** C · **Task:** spec 53 and spec 48 · **Date:** 2026-09-11

Each mutation was run twice — against `tests/research/test_walkforward.py` and against
`python scripts/verify.py --phase 4`. The second half is the one spec 48 requires: a mutation
that reddens a unit test says nothing about whether the *gate* would have noticed.

**W1 — the embargo set to zero.** `embargo_s()` returns `0`.
- Tests: `test_a_training_row_inside_the_embargo_span_is_dropped` and
  `test_the_purge_and_the_embargo_are_counted_separately` failed; 10 passed.
- Criterion: FAIL — *"`embargoed` survived into the training index. It sits 48 bars or fewer
  after the test window, inside the configured embargo. No part of its label window straddles
  the boundary, so the purge cannot remove it — only the embargo can, and an embargo of zero
  keeps it."*
- The purge tests stayed green, which is the point: the two mechanisms are independent and the
  criterion can tell them apart.

**W2 — the purge made a no-op.** `if window_end >= test_start_ts:` → `if False:`.
- Tests: 5 failed, 7 passed.
- Criterion: FAIL — *"`straddler` survived into the training index…"*.
- The embargo test stayed green. Again the point.

**W3 — purge on the decision bar timestamp instead of the label window end.**
`if window_end >= test_start_ts:` → `if decision_ts >= test_start_ts:`.
- Tests: the same 5 failed.
- Criterion: FAIL, with the same message.
- **This is the mutation that matters most**, and it is worth saying why it is not the same as
  W2. W2 is a splitter with no purge in it; W3 is a splitter that purges confidently, reports a
  non-zero `purged_count`, and drops the wrong rows. Every summary it prints looks healthy. It
  is caught only because `straddler` was constructed with its decision bar early and its label
  window late, on purpose — and nothing that reads a real labelled slice can do that.

W2 also produced an incidental observation worth keeping: under `if False:` mypy reported
`walkforward.py:252: error: Statement is unreachable`. The toolchain notices a dead purge even
when no test does, which is a second, weaker net under the same defect.

### The hand-verified fixture's trimmed window made the labeller exclude three entries

**Agent:** C · **Task:** spec 52 · **Date:** 2026-09-11

**What happened.** With `tests/fixtures/labels_hand_verified.json` deposited,
`labeller_matches_hand_verified_labels` went FAIL:

```
3 disagreement(s) with the hand-verified fixture, and one is a FAIL:
[3] SOLUSD@1624534200: expected 'target', the labeller excluded it;
[4] SOLUSD@1624812300: expected 'target', the labeller excluded it;
[7] SOLUSD@1624027500: expected 'stop', the labeller excluded it
```

**Why.** Not a labelling defect — a fixture defect, and an instructive one. The fixture carries
each entry's own candle window, because `data/` is gitignored and a criterion may not read the
archive. I trimmed each window **at the horizon**, reasoning that a fixture carrying more
candles than the window would let a labeller that scanned too far still agree with it.

But the labeller's end-of-series test is *"does the series extend to at least the horizon"* —
`last_ts >= window_end` — and that is the correct test, because a decision bar whose window runs
past the end of the data has an outcome that has not happened yet. On a trimmed window the last
candle is the last candle **at or before** the horizon, and in an archive with gaps that is
strictly *earlier* than the horizon whenever nothing traded in the closing minutes. All three
disagreements are exactly those: 1624534200 has 14 candles in a 16-bar span, 1624812300 has 12
in 22, 1624027500 has a quiet tail. The fixture was telling the labeller the series had ended.

The two implementations disagreed because the second one, which produced the expectations, was
given the **whole archive** and could see past the horizon; the labeller was given only the
trimmed slice. That is a difference in what each was shown, not in what each believes.

**Fix.** The window now runs to the horizon **plus the first candle strictly after it** — the
least context in which "the series covers this window" is answerable at all. Three of the twenty
entries change; the seventeen others are byte-identical, which is itself a check that the
trimming rule and not the labelling changed.

The original concern is not abandoned. One extra bar is enough for an over-scanning labeller to
find a touch it should not have seen, so the `timeout` entries now double as a scan-boundary
test rather than as a place the defect could hide.

### The two implementations disagreed on what `candles_in_window` counts

**Agent:** C · **Task:** spec 52 · **Date:** 2026-09-11

**What happened.** Thirteen of the twenty hand-verified comparisons failed on one field:

```
AssertionError: both barriers inside bar 30; ruling 1 makes it `stop`
assert 48 == 30
```

Every other field on every entry agreed — label, touch timestamp, bars elapsed, both barrier
prices, the ambiguity flag.

**Why.** `research/labelling.py` counts **every candle present in the timeout window**. The
second implementation — the one written from spec 52's prose to produce the fixture's
expectations — counted the candles it had *visited*, which for a touched label stops at the
touch. Two different quantities behind one name, and they coincide only for a `timeout`.

Spec 52 item 5 says "the count of candles actually present in the window", and the window is the
timeout window, so the labeller's reading is the correct one. The count exists to say how much
of the horizon had data underneath it — a window with four candles in it is a window whose label
rests on almost nothing — and a count that stopped at the touch would report a fast `target` as
data-poor when it was not.

**This is the finding the second implementation was for.** Had the fixture been produced by
running the labeller and saving its output, the two would have agreed trivially and neither
reading would ever have been stated. The disagreement is the only reason the field now has a
definition written down.

**Fix.** The fixture builder counts the whole window. `test_bars_elapsed_is_measured_in_time_not_in_rows`
carried the same wrong assumption in its assertion and was corrected with it. No change to
`labelling.py`.

### The surviving labelling mutation was the one that feeds the splitter

**Agent:** C · **Task:** spec 52 and spec 53 · **Date:** 2026-09-11

**What happened.** Eight mutations against `research/labelling.py`. Seven went red. The eighth —
**`label_window_end_ts=touch_ts` → `label_window_end_ts=decision_ts` on a touched barrier** —
left all 39 tests green.

**Why.** Every assertion in `tests/research/test_labelling.py` was about the *label*: which
barrier, when it was touched, how many bars had passed, whether the bar was ambiguous. The only
assertion on `label_window_end_ts` was in the timeout test, and the mutation changed the touched
branch. So the field with no test on it was the field the next module depends on.

And it is not a small field. `label_window_end_ts` is the entire seam with
`research/walkforward.py`: the splitter purges a training row whose window ends at or after the
test window starts. A labeller that reported the **decision bar** as the window end makes every
window end where it began, so nothing ever straddles a boundary, so the purge removes nothing —
which is precisely mutation W3, *"purge on the decision bar timestamp"*, reintroduced from the
producer side rather than the consumer side.

Three tests proved the splitter purges correctly. None of them could see that its input had
stopped telling it the truth. Two modules, each tested against its own behaviour, and the defect
lived in the sentence between them.

**Fix.** `test_a_touched_label_reports_the_touch_as_its_window_end` and
`test_the_seam_the_splitter_purges_on_is_the_later_of_the_touch_and_the_horizon`, the second of
which drives the real splitter over labels the real labeller produced and asserts the straddling
row is purged — an end-to-end check on the seam rather than on either side of it. L8 is red
against both.

The general lesson is worth keeping: **mutating a module's own logic does not test the fields it
exports.** Mutate the outputs another module reads, too.

### Hand verification: the working for three of the twenty labels

**Agent:** C · **Task:** spec 52 · **Date:** 2026-09-11

Spec 52 asks for the *working*, not the result, for at least three entries. All three are
SOLUSD, 15-minute bars, out of `data/historical/ohlcvt_15m/SOLUSD_15.csv`. Barriers are
`target_pct 0.03`, `stop_pct 0.015`, `timeout_bars 48` from `config/default.yaml`.

**A. decision_ts 1624327200, close 26.89 — expected `target` on bar 3.**

Barriers by hand. Target: 26.89 x 0.03 = 0.8067; 26.89 + 0.8067 = **27.6967**. Stop:
26.89 x 0.015 = 0.40335; 26.89 - 0.40335 = **26.48665**.

The window, printed from the archive:

```
1624327200  o 27.05  h 27.05  l 26.57  c 26.89   <- decision bar, never scanned
1624328100  o 27.01  h 27.01  l 26.95  c 26.95   bar 1
1624329000  o 27.14  h 27.26  l 27.05  c 27.05   bar 2
1624329900  o 27.26  h 27.90  l 27.26  c 27.90   bar 3
```

Bar 1: high 27.01 < 27.6967, low 26.95 > 26.48665 — neither. Bar 2: high 27.26 < 27.6967,
low 27.05 > 26.48665 — neither. Bar 3: high 27.90 >= 27.6967 — **target**. Its low is 27.26,
comfortably above the stop, so the bar is not ambiguous.

Bars elapsed: (1624329900 - 1624327200) / 900 = 2700 / 900 = **3**.

Note the decision bar's own low, 26.57. It is above the stop here, so scanning it would not
have changed this answer — which is why this entry is not the one that tests that rule.

**B. decision_ts 1623943800, close 40.26 — expected `stop` on bar 3.** This is the first row
in the whole archive.

Target: 40.26 x 0.03 = 1.2078; 40.26 + 1.2078 = **41.4678**. Stop: 40.26 x 0.015 = 0.6039;
40.26 - 0.6039 = **39.65610**.

```
1623943800  o 40.23  h 40.34  l 40.15  c 40.26   <- decision bar
1623944700  o 40.34  h 40.57  l 40.33  c 40.49   bar 1
1623945600  o 40.15  h 40.15  l 39.94  c 40.04   bar 2
1623946500  o 39.94  h 39.94  l 39.65  c 39.65   bar 3
```

Bar 1: low 40.33 > 39.6561. Bar 2: low 39.94 > 39.6561 — close, and it does not cross. Bar 3:
low 39.65 <= 39.65610 — **stop**, crossed by 0.0061. High 39.94 is far below the target, so
unambiguous. Bars elapsed 2700 / 900 = **3**.

The margin is worth noticing: 0.0061 on a 40-dollar price. A stop computed in `float` rather
than `Decimal` would be 39.656100000000002 or 39.65609999999999, and one of those two answers
turns this entry into a `timeout`. It is in the fixture for that.

**C. decision_ts 1652339700, close 42.55 — expected `stop` on bar 1, ambiguous.**

Target: 42.55 x 0.03 = 1.2765; 42.55 + 1.2765 = **43.8265**. Stop: 42.55 x 0.015 = 0.63825;
42.55 - 0.63825 = **41.91175**.

```
1652339700  o 37.56  h 43.15  l 33.00  c 42.55   <- decision bar
1652340600  o 42.60  h 45.24  l 41.29  c 44.59   bar 1
```

Bar 1: high 45.24 >= 43.8265 — target touched. Low 41.29 <= 41.91175 — stop touched. **Both
inside one candle**, so ruling 1 applies: the label is `stop` and `ambiguous` is true. Bars
elapsed 900 / 900 = **1**.

This is the entry that tests the decision-bar rule, and it does so by accident of the data
rather than by design. The decision bar's own low is 33.00, which is far below the stop of
41.91175, while its high of 43.15 is below the target. A labeller that scanned the decision
bar therefore answers `stop` at **bar 0**, unambiguous — a different label index and a
different ambiguity flag from the truth. Mutation L6 confirms it goes red.

### Spec 48: every Phase 4 criterion observed PENDING, PASS and FAIL

**Agent:** C · **Task:** spec 48 · **Date:** 2026-09-11

`tests/verify/test_phase4_criteria.py`, 34 tests. Two of them sweep all seven criteria for
PENDING on an unbuilt tree and PASS against the real repository; the rest induce one
failure each against `phase4_tree` — the **real** package with one line changed.

| Criterion | Induced failure | The criterion's message |
|---|---|---|
| `memory_records_every_blocker` | a block record written only on ticks with a candidate | "no candidate ever existed" |
| | one row per tick instead of one per blocker | "two guards blocked" |
| | a row written on every tick | "unblocked tick wrote" |
| | every status flattened to `BLOCK` | "reads zero forever" |
| `memory_writes_safety_inputs_live` | `peak_equity` recomputed from this tick | reports `drawdown_pct` disagreeing |
| | closed trades dropped | reports `consecutive_losses` disagreeing |
| | resting orders dropped | reports `resting_entry_orders` disagreeing |
| `rejections_survive_restart` | economics written as null | "only counts rows" |
| | rows stamped with the reading run | "run that wrote it" |
| `labelled_sample_replayed_from_archive` | the parquet rewritten by hand, losing its metadata | "acsoe_provenance" |
| | provenance claiming a 5% target | "different barriers" |
| | the stated series end moved back inside the horizon | "timeout horizon" |
| | the `timeout` rows filtered out | "no `timeout` label" |
| `labeller_matches_hand_verified_labels` | the end-of-series exclusion removed | "expected to be excluded" |
| | the decision bar included in the scan | names the disagreeing entries |
| | the timeout counted in rows | names the disagreeing entries |
| | ruling 1 reversed | names the disagreeing entries |
| | the fixture's excluded entries removed | "no entry that must be excluded" |
| `walkforward_folds_purged_and_embargoed` | embargo zero / purge no-op / purge on `decision_ts` / embargo as truncation / one count for both | see the spec 53 entry above |
| `console_history_reads_real_rows` | the history screen filtered back to the seed | "still showing the seed" |
| | the reason code renamed out of `REASON_PROSE` | "REASON_PROSE" |

Two of these are worth separating out, because they are the ones an ordinary review would
not have produced.

**The parquet written by hand.** `test_a_parquet_with_no_provenance_is_a_fail` takes the
real committed artefact, reads it, and writes it straight back out. Every column survives,
every label is correct, all three outcomes are present — and the key-value metadata is
gone. That is exactly the shape of a fixture somebody produced to make a gate pass, and
without the provenance assertion the criterion accepts it. Spec 56 asks "would this still
pass if the parquet had been written by hand?", and this is the test that answers no.

**The fixture with its exclusions removed.** `test_a_fixture_with_no_excluded_entry_is_a_fail`
drops the three entries that must be excluded and pads back to twenty. The labeller still
reproduces every remaining row exactly, so the comparison keeps passing — while the fixture
has quietly stopped being able to catch a labeller that labels a bar past the end of the
series. A criterion has to guard its own evidence, not only its subject.

### Spec 57 step 3 stops here: nothing persists engine 7's scan tally

**Agent:** C · **Task:** spec 57 · **Date:** 2026-09-11

**What happened.** Spec 57 step 3 says the console's empty state "can now show the scan tally
from engine 7 `scout`", the enabling change being that engine 19 exists. It cannot, and I have
stopped rather than invented a place to put it.

**Why.** Engine 7 publishes `scanned`, `pairs` (from which `entered` is derived) and a
per-reason `excluded` tally into `state["scout"]`, where they live for one tick.
`ScoutUniverse` guarantees `scanned == entered + sum(excluded)`, and the console's empty state
is written to render exactly that sentence. But the console is a separate process reading
SQLite and never sees `state`, and **no column in any table holds any of those three numbers**.
Engine 19 can only write what the schema has room for.

Three ways forward, and choosing between them is not mine:

1. A column on an existing table. `rejections.details` is free text and could carry the tally
   as JSON on one row per tick — but a rejection is one *candidate* and the tally is a fact
   about the *tick*, so this puts a tick-level fact in a candidate-level table and anyone
   counting refused trades would count it.
2. One `rejections` row per **excluded pair**. This is more defensible than it first looks:
   engine 7 is a gate, an excluded pair is a refused candidate, and I mapped all six of its
   per-exclusion codes into `REASON_PROSE` in Phase 3 at B's request — which only makes sense
   if those codes were expected to reach this table. It reconstructs `scanned` but **not**
   `entered`, and it writes tens of rows per tick.
3. A new column or a small table. A schema change, which is the lead's approval and B's edit.

**What I did instead.** Corrected the line that was wrong, which spec 57 does put in scope: it
said the universe filter was engine 4 and its counts arrived in Phase 2. It is engine 7 and it
shipped in Phase 3, so the console was telling an operator to wait for something already built.
The stage still shows no count and still does not show a zero — a zero there reads as "no pair
qualified", which is a result, when the truth is that nobody wrote the number down — and the
reason it gives is now the true one. `test_the_empty_state_names_engine_7_rather_than_the_engine_it_used_to_name`
pins it in both directions.

Raised with the lead and recorded as an open question in `context/progress/c-interface.md`.

### Spec 56: the parquet survives a git round trip, and why the Phase 3 CRLF item does not apply

**Agent:** C · **Task:** spec 56 · **Date:** 2026-09-11

Checked rather than assumed, because a CRLF conversion on a parquet payload corrupts it
silently and the unexplained conversion from Phase 3 is still an open item.

`git check-attr -a` on `tests/fixtures/labelled_sample.parquet` reports `binary: set`,
`text: unset`, `diff: unset`, `merge: unset` — the `-text` in `.gitattributes` is doing its
job. Hashing the file on disk against `git cat-file blob` of its own written object:

```
disk 25111 ed0a3752a7eb152b
blob 25111 ed0a3752a7eb152b
identical
```

Same length, same digest. Nothing converts anything, and `tests/harness/test_fixture_tracking.py`
still passes in both directions. `labels_hand_verified.json` carries the same attributes.

### The lead's CRLF mechanism, found in two of my own files under `tests/fixtures/`

**Agent:** C · **Task:** spec 56 · **Date:** 2026-09-11

**What happened.** The lead explained the Phase 3 "unexplained CRLF conversion": `Path.write_text()`
opens in **text mode**, and text mode on Windows translates every `\n` to `\r\n` — so the
idiom `p.write_text(p.read_text().replace(old, new))` rewrites the line endings of the *whole
file*, not the lines it edited. I checked my own deposits immediately, and two of them had it:

```
README.md                          bytes=    3952 CRLF=    73 bare_LF=     0
labels_hand_verified.json          bytes=  143276 CRLF=  7015 bare_LF=     0
labelled_sample.parquet            bytes=   25111 CRLF=     0 bare_LF=   102
```

The committed `tests/fixtures/README.md` is 2,825 bytes and **pure LF, 58 lines, zero CRLF**.
My edit — about six lines of real change — produced `73 insertions(+), 58 deletions(-)`: every
line in the file, because every line ending moved.

**Why it matters here and not elsewhere.** `.gitattributes` marks `tests/fixtures/**` as
`-text`, precisely so nothing converts anything near committed evidence. `git check-attr -a`
confirms `text: unset` on both files. **There is no clean filter to hide behind under this
directory**, so those CRLFs would have gone into the repository verbatim: a fixture 7,015 bytes
larger than it should be, and a whole-file diff on the README that buries the six lines that
actually changed. Everywhere else in the repo `* text=auto eol=lf` normalises on the way into
the index and the damage is invisible, which is exactly why this went unnoticed for two phases.

**The parquet was never at risk and that is luck rather than care.** `labelled_sample.parquet`
is written by `DataFrame.write_parquet`, which writes bytes, and it shows 0 CRLF and a
byte-identical git round trip. Had I taken the obvious route for the JSON sidecar — read it,
edit it, `write_text` it — on a parquet, the payload would have been corrupted and the
criterion would have failed with a parse error naming nothing useful. My fixture builder used
`write_text` for the JSON, so the near miss was one file type away.

**Fix.** Both files rewritten with LF, by writing **bytes**. The fixture builder now writes
`json.dumps(...).encode()` through `write_bytes`, so regenerating cannot reintroduce it, and
the JSON was regenerated rather than converted so the artefact is still the builder's own
output. Standing rule for my own scripts from here: **never a bare `write_text()` on a file in
this repository — `write_bytes`, or `open(..., newline="")`.**

**Reported, not fixed:** `tests/fixtures/recording_report.json` is A's evidence and shows the
same signature — 168 CRLF, 0 bare LF, under the same `-text` attribute. Flagged to A and the
lead rather than edited, because it is A's deposit.

### A one-line corrupt archive reports as "empty", because the loader tolerates a header

**Agent:** C · **Task:** spec 48, criterion 8 · **Date:** 2026-09-11

**What happened.** Writing the `replay_full_archive` observations, I fed it a file containing
`not,a,timestamp,at,all,here` and expected the loader to refuse it. The criterion FAILed —
correct verdict — but with the wrong reason:

```
assert 'did not load' in 'every archive under data/historical/ was empty'
```

**Why.** `read_archive_rows` tolerates a header row: `if line_number == 1 and not
head.lstrip("-").isdigit(): continue`. That is deliberate and right — some mirrors add one —
but it means a file whose **only** line is garbage is read as "a header and no bars" rather
than as a parse failure. Two situations arriving through one channel: "this archive is
corrupt" and "this archive is empty" get the same answer.

The verdict is FAIL either way, so nothing is hidden from the gate. What is lost is the
sentence an operator reads: "every archive was empty" sends them to look at the builder's
output when the file on disk is not OHLCVT at all. The distinction only disappears for a
one-line file; a valid first line followed by garbage raises properly.

**Fix.** Both paths are now pinned by tests rather than one of them being a surprise:
`test_an_archive_that_does_not_parse_is_a_fail` uses a valid first line and a garbage second
one and asserts the parse message, and `test_a_single_garbage_line_reports_as_an_empty_archive`
asserts the header-tolerance path with the message it actually produces and says why. No change
to A's loader — the tolerance is wanted, and this is a message, not a verdict.

### An unexplained IntegrityError in the criteria tests, recorded rather than waved away

**Agent:** C · **Task:** spec 48 · **Date:** 2026-09-11

**What happened.** One run of `tests/verify/test_phase4_criteria.py` produced 7 failures where
the run before and every run after produced none. Five of them were the
`memory_writes_safety_inputs_live` group, all with the same message:

```
criterion raised - IntegrityError: UNIQUE constraint failed:
  block_records.run_id, block_records.cycle_id
```

That is `ux_block_records_primary`, the partial unique index on `(run_id, cycle_id) WHERE
is_primary = 1`, refusing a second primary row for one tick.

**What I checked, before re-running anything.** The criterion replays the seed's block records
under the seed's own `(run_id, cycle_id)` identities, grouped so `process` is called once per
tick, and the engine sets `is_primary` on the first blocker only — so two primaries for one tick
require the same tick to be driven twice, and the grouping is deduplicated by construction. I
seeded a database directly at `seed.py`'s defaults and again at the config-derived thresholds
the criterion actually uses, and queried for the two shapes that could cause it: **0 ticks with
`SUM(is_primary) <> 1`, 0 ticks spanning more than one `ts`,** in both. The schema is unchanged
in git.

**It does not reproduce.** The named test passes in isolation, and the whole file passes twice
in a row, 40 tests. A and B were both editing the tree at the time and A's
`tests/research/test_backtest.py` went red and green the same way in the same window, so a
half-written module in the copied tree is the likeliest explanation — `phase4_tree` copies
`src/acsoe` wholesale, which is what makes these tests real and also what exposes them to
somebody else's save.

**I am recording it rather than closing it**, because `code-standards.md` says exactly what is
wrong with the alternative: *"re-run the named test in isolation, and if it passes it was the
machine's intermittent fault"* ran for two phases and confirmed itself every time, because in
isolation nothing else was doing the thing that caused it. Under what observation would I have
learnt something else? A reproduction. I do not have one, and the message is written down here
so that the next person who sees it starts from the two shapes I already ruled out rather than
from nothing.

### Spec 48 criterion 8: PENDING observed twice, PASS, and two FAILs

**Agent:** C · **Task:** spec 48 · **Date:** 2026-09-11

The lead's instruction was that `replay_full_archive` reporting PENDING when no archive is
present *must itself be a state I have observed*, and that the archive arriving made that
branch harder to reach rather than less necessary. It is unreachable on this machine —
`data/historical/` exists and holds 859,248 bars — so it is reached in a copied tree that does
not have one, which is also the honest picture of a fresh clone.

Five observations, in `tests/verify/test_phase4_criteria.py`:

- **PENDING, no `data/historical/` at all.** The fresh-clone state. Asserted with
  `assert not (phase4_tree / "data").exists()` first, so the test cannot pass because the
  fixture quietly changed underneath it.
- **PENDING, the directory exists and holds no `*.csv`.** A *different* absence: the operator
  has made the folder and not filled it, or has put the source time-and-sales files one level
  down and no derived bars at the top. Different message, so the operator can tell which one
  they are looking at.
- **PASS**, over two archive-shaped CSVs built in the test, one of them with a three-bar hole
  in it. Two rather than one deliberately: the criterion sums bars and gap runs across every
  archive it finds, and a single-file fixture cannot tell that from a criterion that reads only
  the first.
- **FAIL** on an archive that does not parse.
- **FAIL** on an empty archive file, which otherwise PASSes as `1 archive(s), 0 bars` —
  technically true, and exactly the shape of a build script that ran and produced nothing.

And with `--live` against the operator's real archive:
`PASS replay_full_archive  3 archive(s), 859248 bars spanning 4469 days, 18745 gap run(s)`.

### `holes_mean_no_trades` is now asserted, and it is the fact the gapped windows rest on

**Agent:** C · **Task:** spec 52 and spec 56 · **Date:** 2026-09-11

A's first archive was built from our own WebSocket recording, and A's warning with it was
precise: a hole there is **either** a quiet interval **or** an interval nobody was watching,
and a triple barrier walked across the second reads as a calm market and returns `timeout`
where the real market touched a barrier — a fabricated outcome with nothing to say so. The
operator then supplied Kraken's own published history, where a hole can only mean no trades
occurred, and A exposed the distinction as `ReplayReport.holes_mean_no_trades`.

It is `bool | None`, and `None` — a sidecar that never heard of the question — is the case that
matters. Read as truthiness, `None` and `False` are the same answer; read as `is not True` they
are not, and invariant 3 says the absence of a no is not a yes.

Two consequences, both landed:

- The fixture builder refuses to write `labelled_sample.parquet` unless the replay reports
  `holes_mean_no_trades is True`, and it records the value **in the parquet's provenance**.
- `labelled_sample_replayed_from_archive` asserts that field `is not True` → FAIL, with a
  message saying why: every gapped window in the fixture would otherwise be a label walked
  across an interval that may simply not have been recorded.

**This caught a real mistake on the first run.** The builder used
`ArchiveReplay.from_archives({pair: path})`, which never reads `PROVENANCE.json`, so the report
came back `holes_mean_no_trades=None` and the guard refused. `from_directory` — which is what
engine 23 uses — picks the sidecar up. The claim in the parquet is now the archive's own rather
than one the build script asserted about it.

**And a second mistake behind it.** `from_directory` loads all three pairs, so
`ReplayReport.first_ts` and `last_ts` are the min and max across *every* pair — the sample
claimed XBTUSD's 2013 start as SOLUSD's. That is not cosmetic: the criterion asserts no labelled
bar sits within the timeout horizon of `span_end_ts`, so a span borrowed from whichever pair ran
latest weakens that check and says nothing. The provenance now takes its span from
`report.archives[pair]`, the per-pair `ArchiveReport`, which is what A exposed it for.

### `replay_full_archive` loaded the real archive at a hardcoded 900 seconds

**Agent:** C · **Task:** spec 48, criterion 8 · **Date:** 2026-09-11

**What happened.** A answered my question about where engine 23 gets `interval_s` — from
`timeframes.decision_bar_s` in config, never from the `ArchiveReport`, because the report's
interval "is whatever the *caller* loaded the archive at, so taking it from there makes it agree
with itself by construction and proves nothing." Reading that, I looked at my own criterion and
found it doing neither: `check_replay_full_archive` passed `interval_s=_FOLD_INTERVAL_S`, a
module constant equal to 900, straight into `load_archive`.

**Why it matters, and it is the shape of defect this phase exists to catch.** The interval is
the grid every gap statistic is computed against. Load a 15-minute archive at 30 minutes and
`load_archive` reports **half** the expected bars, so most real gaps vanish and the criterion
prints a confident, plausible, wrong number: fewer gap runs and a shorter span than the archive
holds. Nothing raises and nothing looks odd. The operator reads it as a clean archive.

Today it is harmless because the constant happens to equal the config value. That is precisely
the condition under which a hardcoded threshold is invisible — `AGENTS.md` opens by saying a
remembered value is stale, and this one is remembered. The day the operator retunes
`decision_bar_s` the live criterion silently starts measuring a different archive from the one
the system trades.

**Fix.** The criterion reads `timeframes.decision_bar_s` from the committed config and reports
PENDING naming the key if it is unset, the same fail-closed shape every other threshold read
here uses. Proved by mutation: with the config key changed to 1800 the criterion reports a
different bar count and gap total over the same files, which is what makes it a read rather than
a coincidence.

**The constructed-fold interval stays a literal, and is now named for what it is.**
`walkforward_folds_purged_and_embargoed` builds its own four-row dataset, and the interval there
is a property of that fixture rather than of the system — the criterion would be no more correct
for tracking config, and coupling a constructed fixture to a threshold the operator may retune
is how a criterion starts failing for reasons that have nothing to do with its subject. Renamed
`_CONSTRUCTED_INTERVAL_S` with the distinction written at the definition, because a reader
meeting `_FOLD_INTERVAL_S` twice in one file would reasonably assume both uses meant the same
thing — which is how the archive read came to use it in the first place.

### I destroyed the evidence for a transient FAIL, by the exact mechanism the rule warns about

**Agent:** C · **Task:** spec 48 · **Date:** 2026-09-11

**What happened.** A sweep across every phase reported `phase 4 --live: 10 criteria: 9 PASS,
1 FAIL, 0 PENDING`. My command had piped the run through `grep "criteria:"`, so the summary line
was all I kept — **the criterion's name and its message went to the bin**. I then ran the gate
again to find out which one it was, and it came back 10/10.

**Why this is worth an entry rather than a shrug.** The lead's standing instruction, from the
Phase 3 rule, is to capture the output **before** re-running, because re-running to confirm
green is what destroyed the evidence for two phases. I did not break that rule by re-running
carelessly; I broke it earlier, by filtering the first run's output down to a summary. A
criterion that has reached a verdict has reached it, and `verify.py` streams and flushes each
line precisely so a killed run leaves its verdicts on disk — and I threw them away at the pipe.

There is a second, quieter cost. The earlier `phase 0: 6 PASS, 1 FAIL` in the same sweep is now
also unattributable. It resolved on the next run with `is_gate_matches_registry` reporting **10
engines registered** where it had said 9, so the lead was mid-edit on `bootstrap.py` registering
engine 19 — that one I can reconstruct from a changed message. The Phase 4 one I cannot, beyond
"B was writing the manage-chain rehearsal at the time and `toolchain_green` runs the whole
suite".

**Fix, and it is a habit rather than code.** When sweeping phases, keep the full output —
`tail -8` at minimum, and the whole run when anything is red. `grep "criteria:"` is for a run I
already expect to be green, and expecting a run to be green is not a reason to stop being able
to explain it.

### Two true numbers in one report that read as a contradiction

**Agent:** C · **Task:** spec 48 · **Date:** 2026-09-11

**What happened.** Reading a `--phase 0` report after the lead registered engine 19, two lines
of the same run disagreed:

```
PASS  orchestrator_empty_registry  ... (acsoe.bootstrap holds 9 registered engines ...)
PASS  is_gate_matches_registry     10 engines registered; 0 mismatches (5 gates ...)
```

**Why.** Both are right. `orchestrator_empty_registry` counts `acsoe.bootstrap`'s three runtime
chains; `is_gate_matches_registry` counts those **plus** the offline chain in
`cli/research.py`, where engine 23 `backtest` lives and is deliberately never registered in
`bootstrap.py`. Nine runtime plus one offline is ten.

So there is no defect in either count — the defect is in a sentence I wrote, and it is worth an
entry because of *when* it is read. This report is what somebody looks at to decide whether a
phase closes, and two adjacent PASS lines quoting different totals for "registered engines"
invites either a hunt for a bug that does not exist or, worse, a shrug that trains the reader to
stop noticing when the numbers genuinely disagree.

**Fix.** One word: `9 registered **runtime** engines`, with the reason at the call site. The two
tests that pinned the old phrasing, `test_orchestrator_passes_against_a_minimal_registry_and_tick`
and the blocking-gate one, were updated with a comment saying the word is part of the pinned
wording rather than decoration — otherwise the next person tidying the sentence removes it and
the ambiguity comes back silently.

Those two tests going red is the system working, incidentally. A message an operator reads is a
contract, and it should not be possible to change one by accident.

### Decoupling the count assertions from the prose, after the wording change broke two tests

**Agent:** C · **Task:** spec 48 · **Date:** 2026-09-11

**What happened.** Adding the word `runtime` to `orchestrator_empty_registry`'s message turned
two Phase 0 tests red. They asserted `"0 registered engines" in outcome.message` and
`"1 registered engines" in outcome.message` — substring matches on an English sentence.

My first instinct was that this was the system working: a message an operator reads is a
contract and should not be changeable by accident. The lead's push-back is better, and it is
worth writing down because it is not the obvious reading: **a substring match on prose taxes
exactly the improvements you most want someone to make**, and the tax is paid in red tests that
look like regressions. Nothing about the report got worse when the sentence got clearer.

**Both instincts are right about different things, and that is the resolution.** Those two tests
care about a **count**. Whether the sentence is unambiguous is a *different claim* with a
different failure mode, and it had been riding along inside a substring match that was never
written to carry it.

**Fix — two claims, two tests, each failing for its own reason.**

- `reported_engine_count(message)` reads the number out with a regex tolerant of the wording,
  and the two existing tests assert on the integer. They no longer care how the sentence reads.
- `test_the_engine_count_says_which_engines_it_counted` runs both criteria against the **real**
  repository, asserts the two totals genuinely differ by one — the premise, so the
  disambiguation is load-bearing rather than a precaution — and then asserts the smaller one
  says which engines it counted. Against a fabricated tree it would be asserting about a
  sentence nobody will ever read.

**Proved by mutation, and the two mutations separate cleanly**, which is the whole point:

| mutation | result |
|---|---|
| the word `runtime` tidied back out of the message | **only** the wording test red; 64 passed |
| the count itself off by one | both count tests red, and the wording test too — it asserts the +1 relationship as its premise |

The helper needed two patterns, and that turned out to be a small finding of its own:
`orchestrator_empty_registry` says *"N registered runtime engines"* while
`is_gate_matches_registry` says *"N engines registered"*. Neither is wrong in its own sentence,
but two lines of one report describing the same kind of thing in opposite shapes is part of why
their differing totals read as a contradiction rather than as two different questions.

**The lead's cause analysis was right and my fix had already landed before the message arrived.**
The gate was red in their tree because I was mid-save on `verify.py`; the suite before it had
failed on a different test entirely, which looked like flakiness and was the tree moving under
two runs. Recorded because both of us nearly filed it as the machine's intermittent fault.
