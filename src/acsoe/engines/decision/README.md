# Engine 16 — `decision`

**Gate.** `is_gate = True`, by operator ruling of 2026-09-16. Opportunity chain, runtime
stage 3, after engine 15 `skeptic` and before engine 18 `execution`.

Engine 16 does two things, and it is important that they are described differently.

1. It **decides** one thing: whether every approving engine judged *this* tick's
   candidate.
2. It **composes** the order intent. That is assembly, not a decision, and nothing below
   calls it one.

## What it decides

By the time engine 16 runs, four gates have already said yes — 7 `scout`, 10 `cost`,
11 `risk`, 15 `skeptic`. So "combine their verdicts" was never a job worth an engine: the
verdicts are already unanimous or the chain stopped. What nothing in this system did
until spec 90 was ask whether they were all answering the **same question**.

If engine 7 chose SOL/USD and engine 10 approved BTC/USD, both are individually correct
and the order that results is one nobody approved. If a `state` key survived from a
previous bar, every engine that reads it sees a well-formed, current-looking number. Both
failures are silent everywhere else in the chain, because every engine reads the keys it
needs and none reads the keys it does not.

The check is deterministic, contains no model, and can only ever make the system less
willing to trade. That is why it is a gate and why invariant 4 protects it.

## Inputs read from `state`

| Key | Used for |
|---|---|
| `cycle_id` | the intent's `cycle_id` |
| `market_sensor.closed_bar_ts` | **the bar every other payload is measured against** |
| `scout.pair` | **the pair every other payload is measured against** |
| `prediction` | `model_run_id`; its `pair` and `bar_ts` are checked |
| `order_book` | `estimated_slippage_pct`; provenance only |
| `cost` | `net_edge_pct`, `hurdle_pct`, `expected_move_pct`; its `pair` is checked |
| `risk` | `approved`, `qty`; its `pair` is checked |
| `adaptive_router` | `active_model_run_id`; provenance only |
| `skeptic` | `p_wrong`; its `pair` is checked |

Nothing is read from `context`. No client, no clock, no configuration key — engine 16 is
arithmetic over what the engines before it published. A config threshold appearing here
would mean it had stopped being a coherence check.

## Output written to `state`

`state["decision"]`:

```
{"coherent": bool, "checked": [engine names], "reason_code": str | None,
 "intent": { ... }}       # "intent" absent entirely on a block
```

`checked` is the provenance of the check itself — which payloads the walk actually
examined. Without it, "the pair matched everywhere" and "there was nowhere to match
against" publish identically, and only one of those is a check.

The intent carries `pair`, `qty`, `closed_bar_ts`, `cycle_id`, and provenance:
`net_edge_pct`, `hurdle_pct`, `expected_move_pct`, `estimated_slippage_pct`, `p_wrong`,
`model_run_id`, `active_model_run_id`. Money is an exact decimal string; `p_wrong` is a
float, because it is a probability and not money.

## Gate conditions

In order, because the order is part of the behaviour. Every one of them blocks, and on
every one of them **the intent is absent from the payload in its entirety** — not an
empty mapping, not a null. There is no half-intent for engine 18 to read, which is the
same shape and the same argument as engine 11 omitting `qty` on a rejection.

1. **No candidate, or no payload from an engine that approved** — `input_missing`. The
   opportunity chain stops at the first block or `PASS` (`core/orchestrator.py`), so
   engine 16 running at all means every engine before it ran and approved. An absent
   payload is the chain contradicting itself, not a verdict anyone reached.
2. **No decision bar on this tick** — `input_missing`. Engine 5 `feature` returns `PASS`
   when no bar closed, which stops the chain on the fourteen ticks in fifteen where none
   did. A null `closed_bar_ts` here is not "no bar yet": it is engine 16 running on a
   tick that had nothing to decide about.
3. **Two payloads name different pairs** — `pair_disagreement`. The sentence names both
   engines and both pairs, because "they disagree" without saying which is a rejection
   row nobody can act on.
4. **A payload names a bar that is not this tick's** — `stale_bar`. The sentence names
   the engine, the bar it carried and this tick's.
5. **Engine 11 approved and published no `qty`, or did not approve at all** —
   `no_approved_quantity`. Engine 11 omits the field on a rejection, so an approval with
   no quantity is one payload asserting an approval and a refusal at once, and neither
   half can be trusted over the other.
6. **The check itself could not run** — `decision_inputs_unavailable`. A `closed_bar_ts`
   that is not a timestamp, a `cycle_id` that is not a number, a quantity that does not
   parse as money. Invariant 3: a clause that cannot be evaluated blocks.

## Two design choices worth stating, because both were decisions

### The clauses are a walk, not a list of comparisons

`_coherence` iterates `CHECKED_SOURCES` and asks each payload whether it happens to name
a pair or a bar. It does not name the four comparisons that exist today.

Engines 9 `order_book` and 14 `adaptive_router` did not exist when this was written. When
they land, whatever they publish is checked with no edit here. A hand-written list of
comparisons is written by the same person who forgot the one that matters — the argument
that produced the `MarketStreamProtocol` walk in `clients/paper/` on the same day, after
a per-method test suite failed to notice a missing method for the same reason.

A payload that names **no** pair is not checked and is not a failure. Engines 14 and 15
need not restate the candidate; only a disagreement is a disagreement.

### Provenance from engines 9 and 14 is copied, never judged

`estimated_slippage_pct` and `active_model_run_id` are omitted from the intent when
absent, and their absence never blocks.

This is forced by two specs that only hold together this way: spec 97 says engine 14 must
publish nothing engine 16 "reads to decide", and spec 90 puts the router's
`active_model_run_id` in the intent. Both are true exactly when the field is a record
rather than a criterion.

It costs nothing, which is the part worth checking rather than asserting. Engine 9
failing means engine 10 — a gate — refuses for want of the slippage, so the chain never
reaches engine 16. Engine 14 failing still leaves its key present, because the
orchestrator writes `result.data` on an `ERROR` result too. There is no reachable tick on
which requiring these two would refuse something that requiring the other five does not.

## What this engine must never do

- **Re-derive, recompute, adjust or re-check any number it copies.** Disagreement is a
  block, never a correction.
- **Size, price, weight or scale anything.** A quantity lowered here would be a veto
  wearing a sizing costume.
- **Block on a model's judgement.** Engine 15 has already vetoed or not. Engine 16's
  criteria are coherence only.
- **Mint a `userref`.** That is engine 18's, deterministic from the pair and the bar.

## The provenance fields come from one publisher on purpose

`net_edge_pct`, `hurdle_pct` and `expected_move_pct` are all taken from engine 10, even
though `expected_move_pct` originates in engine 8 and engine 10 copied it. The three
numbers appear in one comparison — invariant 5's `net_edge > hurdle_multiple x friction`
— and taking them from one payload means the record cannot show a net edge computed from
a move the record does not carry. Two publishers would make that possible for no gain.
