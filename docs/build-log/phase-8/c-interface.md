# Phase 8 — C (Interface and models) build log

### Three Phase 6 criteria assumed one crossed pair blocks the tick, and D10 made that false

**Agent:** C · **Task:** D10 per-pair stop hold, verify half · **Date:** 2026-10-16

**What happened.** After D10 option (b) was merged, `triggered_stop_holds_on_data_guard_block`,
`escalation_completes_during_outage` and `console_shows_position_live` all FAILed on the current
tree. Each said the same thing: `the crossed quote did not block the tick on data_guard: None`
(the outage one: `the primary blocker is None`). Observed by running the three criteria from the
pre-change `verify.py` (`1dab722`) against the D10 tree.

**Why.** All three drives cross one pair, the position's own, with `Drive.cross`, and expect
engine 4 to block. The drive quotes three pairs. Since D10, engine 4 judges the feed: it blocks
on a negative spread only when **every** quoted pair is crossed. One crossed pair now belongs to
engine 7 (`no_live_quote`) and to engine 21's per-position hold.

**Fix.** A new `Drive.cross_feed` crosses every quoted pair: the named pair over the sound book it
is sold into, the rest at the pinned bid. The outage criterion and the console criterion use it
where they need engine 4 to block. Their assertions are unchanged. The held-stop criterion now
runs three ticks on one position. Tick 1 crosses only the position's own pair, the stop is
touched, and the tick is **not** blocked: engine 21 publishes no trigger, the row's
`hold_reason` is `pair_quote_not_live`, the tick-level hold is null, engine 19 stores the row's
reason, and no exit is placed. Tick 2 crosses the whole feed, and the original assertions hold
as before. Tick 3 is `close_all`, which liquidates through the block. After the change all three
PASS (49 s, 7 s and 2 s once the training subject is cached).

**Decision: one criterion rather than a new Phase 8 criterion.** Tick 1 is the scenario this
criterion has always run: one crossed pair and a touched stop. Only the mechanism that stops the
exit has changed. A separate criterion would repeat the same drive, at about 50 s a run, and
would lose the sequence: the same position held per pair and then feed-wide, with the stored
reason moving from one to the other. The case against: the criterion is registered for Phase 6
but now proves a Phase 8 ruling. Two named arms were added to `MUTATIONS` in
`tests/verify/test_phase6_criteria.py`. `per_pair_hold_removed_from_21` empties engine 21's
`not_live`. `memory_overwrites_the_rows_hold` restores engine 19's pre-D10 overwrite.

### Engine 19's clearing property moved half onto engine 21's contract

**Agent:** C · **Task:** D10, engine 19 · **Date:** 2026-10-16

**What happened.** `test_the_hold_reason_is_written_and_then_cleared` failed once engine 19
began storing the row's own `hold_reason`. Its second tick deliberately gave the row a stale
`data_guard` reason, and engine 19 now stores it.

**Why.** That test was hardened in Phase 6 against a real hole: the row model defaults
`hold_reason` to `None`, so a row that "said null" could not tell a cleared column from an
unassigned one. With the stale reason, only engine 19's tick-level overwrite could clear it.
Under D10 the row's reason is a real input. A stale one on a republished row would be stored and
carried forward, so clearing now depends on engine 21 setting the key on every row, every tick.
B confirmed this and tests it on their side
(`test_every_row_carries_this_ticks_answer_and_never_the_stores`). Engine 21 builds its rows
fresh in `_mark` and never copies them from the store.

**Fix.** Tick 2's row now carries `hold_reason: None`, as engine 21's contract says it will.
Four new tests each flip one input: the row's own reason stored, cleared on the next tick, beaten
by a feed-wide hold on every row, and an absent key read as null. **The consequence:** the old
"skip the assignment when the tick holds nothing" mutant is now *equivalent*. The stored row
already carries the row's own value, or the model default when the key is absent. That mutant
cannot be killed and is not listed.

### The training-backed runs did not finish under load: LightGBM's OpenMP threads spin

**Agent:** C · **Date:** 2026-10-16

**What happened.** A direct run of the three criteria was killed at its 90-minute limit, and a
memory and console pytest run at its 60-minute limit, with no result. Both were inside LightGBM's
`Booster.update`, under `research/training.py` (shown by a `faulthandler` stack dump). The
machine's load average was 12 to 16 on 4 cores, with three agents' suites running at once.

**Why.** `prediction.threads` sets LightGBM's `n_jobs`, and OpenMP worker threads busy-wait by
default. Several such processes on an oversubscribed machine spend their time spinning against
each other rather than training. Normally this training takes about 30 s.

**Fix (for the run, not the code).** With `OMP_WAIT_POLICY=PASSIVE` in the environment, the same
three criteria finished in 49 s, 7 s and 2 s. No code or config was changed. Worth knowing
before a full gate runs while other agents are testing.
