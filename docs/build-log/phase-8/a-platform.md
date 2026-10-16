# Phase 8 — Agent A build log

### D10 ended the rehearsal's data_guard scenario, so it was split rather than weakened

**Agent:** A · **Task:** spec 87, D10 follow-through · **Date:** 2026-10-16

**What happened.** `test_a_data_guard_block_holds_a_touched_stop_and_close_intent_then_exits_it`
failed with `KeyError: 'trading_blocked_by'`. It crossed the traded pair's stream quote alone and
expected engine 4 to block.

**Why.** That is the ruled behaviour change, not a defect. Under D10 option (b), engine 4 judges
only the feed: it blocks when even the freshest quote is past the bound, or when every quoted pair
is crossed. One crossed pair is excluded by engine 7 and, when a position is open on it, held by
engine 21 per position (`pair_quote_not_live`).

**Fix.** The test became two. The scripted market quotes three pairs, so **4a** crosses all three.
That is a corrupt feed, engine 4 blocks with `negative_spread`, and every original assertion still
holds: the `data_guard_blocked` hold on the tick and on the stored row, no trigger, no exit, then
Close all liquidating through the block. **4b** crosses only `BTC/USD` and leaves ETH and SOL
healthy. The tick is not blocked, engine 21 triggers nothing for the touched stop, the tick-level
hold is null, and the stored row says `pair_quote_not_live`. Close all then liquidates regardless,
and the hold clears. A stale variant was not possible: `ScriptedMarket.latest_quote` stamps a
pinned quote at `now`, and the harness is C's. Crossing is the only feed fault this rehearsal can
script without touching it.

**Consequence.** `check_recorded` built every expected position row with the **tick's** hold. It
now stores the row's own hold when the tick's is null, which is the rule
`context/engine-contracts.md` sets and engine 19 implements. Without that, 4b's read-back would
have failed on a correct store. Both tests pass against B's and C's WIP snapshot `fc5deb9`. The
engine 21 arms that would prove 4b catches a missing per-pair hold are written but not run, since
mutating B's file in a shared tree is the lead's call.

### The one-pair fixtures could not tell "oldest" from "freshest", so the fraction tests use four

**Agent:** A · **Task:** D10, engine 4 tests · **Date:** 2026-10-16

**What happened.** The operator asked for a half-dead feed (some pairs quiet, some quoting) to
pass, with the fresh-pair fraction recorded. The existing D10 tests used three pairs, and their
inputs differed in more than one respect from any passing baseline.

**Fix.** A four-pair, all-fresh baseline that passes. Each test then changes exactly one thing
from a passing state. Half-dead: two pairs aged past the bound gives no block,
`fresh_pairs == 2`, `pairs_seen == 4`, freshest 5 s and oldest 900 s. Dead: three pairs already
quiet, then the last fresh one aged one second past the bound, gives a block with staleness as
the only finding. Crossed: three of four crossed passes, all four blocks. The boundary test also
asserts `fresh_pairs` at the inclusive bound. Without that, a `<=`→`<` mutant on the count would
survive, because no other test puts an age exactly on the bound.

**Consequence.** The 12 arms on `data_guard/engine.py` are in scratch and **not run**. Each
anchor was checked to occur exactly once.

### Finding: the fresh-pair fraction is published but stored nowhere

**Agent:** A · **Date:** 2026-10-16

**What happened.** The ruling says to record the fresh-pair fraction, with no screen for it yet.
Engine 4 publishes `fresh_pairs` and `pairs_seen` in `state["data_guard"]` on every tick.
`state` is discarded when the tick ends.

**Why.** Engine 19 persists nothing from `state["data_guard"]`. `block_records` holds only the
blocker's name, its prose reason and the status, and only on a block. `scout_tallies` holds
engine 7's exclusion counts, and only on ticks that reach engine 7. The daemon's
`tick_market_snapshot` log line carries quote and subscription counts, but no ages.

**Not fixed: reported to the lead.** No schema change was asked for. The lane-A option with no
schema change is to add the four data_guard figures to `tick_market_snapshot` in `cli/engine.py`.
The paper-run report script reads them from the log if they are there.

### Decision: the fresh-pair fraction is kept on the per-tick log line, with `None` for "not published"

**Agent:** A · **Task:** lead follow-up to the finding above · **Date:** 2026-10-16

**Options.** Add a column or table, which is a schema change and B's and the lead's. Or carry
engine 4's figures on the `tick_market_snapshot` line, which is already written at INFO on every
tick precisely because `state` is otherwise lost. The lead ruled for the log line.

**Chose.** Five flat fields copied from that tick's `state["data_guard"]`: `pairs_seen`,
`fresh_pairs`, `freshest_quote_age_s`, `oldest_quote_age_s` and `max_data_age_s`. They are flat
rather than nested so a reader finds them beside `quote_count`, and no name contains a token the
log redactor matches; a test runs them through the real redactor anyway. **Every key is always
present, and a value is `None` unless engine 4 published one of the right type.** A guard that
errored publishes `{}`, and a 0 there would read as "no fresh pair", which is a statement about
the feed that nobody made. A string, or a boolean standing in for a count, is also `None`.

**Consequence.** The tests run the **real** engine 4 on the snapshot test's state, so the logged
figures are what the engine published. They flip one input, ETH aged past the bound, and assert
that exactly `fresh_pairs` and `oldest_quote_age_s` move, and nothing else on the line. They
also check the inclusive bound, unpublished and wrong-typed regions, the redactor, and the
written file through `run_loop`. Eight mutation arms are in scratch, not run. The paper-run
report now takes the fraction from `--log`, and it counts ticks with no figure rather than
treating them as zero. One fix was needed along the way: `mypy --strict` does not narrow through
a boolean held in a variable, so the age check became a direct `isinstance` branch.
