# Engine 17 — `safety`

**Gate.** **Guard** chain, runtime stage 1 — not the opportunity chain. Owner: B.

The circuit breaker on the account: the engine that freezes the system, or liquidates it,
when the account is in a state no candidate-level judgement should be allowed to override.

## Why it is a guard and not the last link of the opportunity chain

It asks an account-level question — how far is equity down, how many losses in a row, how
many errors this hour, how long has the feed been bad. None of that has anything to do with
the candidate under consideration, and all of it must be answered on ticks where there is
no candidate at all.

Placed at the end of the opportunity chain it would run only when every other gate had
already passed. On roughly fourteen ticks in fifteen that chain stops at `feature` because
no bar closed, and on the rest any earlier gate stops it sooner. **An account bleeding
while every candidate is rejected by the cost gate would never trip the breaker.** The
guard chain is the only placement that makes this a circuit breaker rather than a
formality.

## The six inputs — all from the store, none from `state`

| Input | Store read | Table |
|---|---|---|
| Equity drawdown | `latest_equity_snapshot()` | `equity_snapshots` |
| Consecutive losses | `recent_closed_trades()` | `trades`, ordered by `closed_at` |
| Error rate | `count_block_records_in_window(status=ERROR)` | `block_records`, trailing hour |
| Open positions | `count_open_positions()` | `positions` |
| Resting entry orders | `count_resting_orders(intent=ENTRY)` | `orders` |
| Consecutive data blocks | `stored_consecutive_data_block_ticks_excluding_current_tick()` | `block_records` |

`state` is fresh every tick and this engine runs **before** the manage chain, so
`state["position_manager"]` and `state["exit"]` do not exist when it runs. That is
structural, not a convention. Their producer is engine 19 `memory`, which is Phase 4; the
Phase 0 seed resolves the forward dependency and nothing here may touch a live engine 19.

The single `state` read in the whole engine is `trading_blocked_by`, to learn whether *this*
tick is blocked by `data_guard`. That is not one of the six — the store cannot know it,
because engine 19 has not run yet this tick.

## The outage arithmetic, which is off by one in the obvious reading

Engine 4 `data_guard` runs **before** engine 17, so this tick's block is already in
`state`. Engine 19 `memory` runs **later**, in the manage chain, so the store holds records
only through tick T−1.

```
effective = stored_consecutive_blocks_through_T-1 + (1 if this tick blocked by data_guard)
```

Getting it wrong fires the breaker a minute early or a minute late. The store method is
named `stored_consecutive_data_block_ticks_excluding_current_tick` so the correction cannot
be forgotten at the call site, and it is passed this tick's `(run_id, cycle_id)` because
"consecutive through T−1" is unanswerable without knowing T — a clean tick writes no
`block_records` row at all, so an outage that ended two ticks ago is otherwise
indistinguishable from one still running.

The count is **consecutive most-recent `cycle_id`s carrying any `data_guard` row, ordered
by `ts`, never by `cycle_id`.** `cycle_id` restarts at 1 with each process, and surviving a
restart is the whole reason the counter lives in SQLite rather than in `state`. A tick where
two guards blocked contributes one, not two.

## How it acts

It **cannot** write `state["system"]` — only the orchestrator may. It writes a `freeze` or
`close_all` row to the `commands` table with `source = CommandSource.SAFETY`, the same
channel the console uses, and the orchestrator consumes it at the top of the next tick. Its
`BLOCK` suppresses the opportunity chain for the current tick; the command row is what makes
the decision persist. Every such row is an audit record of exactly when and why the system
stopped itself, and it carries **every** tripped condition, not just the strongest.

### Idempotency

It runs every tick, so it emits a row **only when that row would change the state**:

- `freeze` only while the mode is `running`.
- `close_all` only when there is exposure — an open position **or** a resting entry order.
- `close_all` only when `close_intent` is not already set.

Without this a sustained drawdown would append a freeze row every sixty seconds forever and
a sustained outage would re-trigger a liquidation already under way. On suppressed ticks it
still evaluates, still blocks, and still publishes its assessment: the assessment is the
record of the *evaluation*, the command row is the record of the *decision*, and research
needs both.

A resting post-only buy counts as exposure. Left on the book through a blackout it can open
a position into a market the system has already declared untrustworthy.

## Policy, isolated on purpose

`contracts.py` carries two tables rather than branches, because they are the part a person
rules on and the rest is mechanism:

- **`CONDITION_ACTION`** — which command each tripped condition emits. **Provisional**:
  `trading-invariants.md` §14 and `feature-specs/36` disagree about whether a drawdown
  breach freezes or escalates, and the Phase 0 seed satisfies every precondition §14 names,
  so no fixture can make both true. Escalated to the lead on 2026-09-09; the implemented
  reading treats spec 36's "freezes" as the loose one, since `close_all` also sets the mode
  to `frozen` and §14 is a trading invariant. The error rate maps to `FREEZE` because §14
  does not list it among the escalation conditions at all — it is an engine-health problem,
  not account exposure, and liquidating because the system is throwing exceptions would be
  the breaker causing the loss it exists to prevent.
- **`BOUNDARY_SOURCE`** — whether each threshold trips *at* its limit or *above* it, with
  the sentence in the documents that fixes it. Three trip at the limit; the outage is the
  only one that is strictly greater, because invariant 14 says "more than" and spec 36 says
  "on the tick after the limit and not one before". An off-by-one in a circuit breaker
  fires it a tick early or a tick late.

## Testing note: the seed can never sit on a boundary

The Phase 0 seed overshoots every threshold by three, deliberately, so that a fixture pinned
to a literal cannot stop overshooting when the operator raises a limit. That is right for
proving the breaker fires and it makes the seed **incapable of testing "and not one tick
before"**. The boundary is therefore tested on a controlled `block_records` fixture that
reproduces the seed's load-bearing property — two `run_id`s with reused `cycle_id` values —
and the seed is used for the realistic case and for the `ts`-versus-`cycle_id`
discrimination.

`seed_database` takes its thresholds by injection and its module defaults are fixture-shape
constants, not the committed config. One has since diverged: the default
`max_errors_in_window` is 10 while `config/default.yaml` says 20, so a caller using the
defaults gets 13 ERROR rows and this engine's error-rate condition does not trip. Build
`SeedThresholds` from the config, as `scripts/verify.py` does.
