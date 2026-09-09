# Engine 4 — `data_guard`

**Number:** 4 · **Chain:** guard · **Gate:** **YES** · **Runtime stage:** 1

The first real gate in the system: the engine that refuses to let the loop trade on data
it does not trust, and the block the outage counter is later derived from.

## What it reads from `state`

`state["market_sensor"]`, and nothing else:

| Field | Used for |
|---|---|
| `quotes[pair]["age_s"]` | staleness |
| `quotes[pair]["spread_pct"]` | crossed book |
| `missing_bars` | a decision bar with no candle |
| `stream_available` | wording of the no-data block |

It reads no other engine's output and it never touches a client. Every market-data fault
it judges arrives from one place — which is why the lead ratified the live spread as
engine 3's rather than engine 1's on 2026-09-09.

## What it writes into `state["data_guard"]`

| Key | Meaning |
|---|---|
| `blocked` | Whether this tick was refused |
| `reason_code` | The **primary** finding's code, or `null` |
| `findings` | **Every** finding, each with `reason_code`, `detail` and `pair` |
| `max_data_age_s` | The threshold applied, echoed so a block is readable without the config |
| `oldest_quote_age_s` | The freshest data's age, or `null` when nothing carried one |
| `pairs_seen`, `missing_bars` | What it had to work with |

Every finding is published, not only the one that became the `reason`. A tick can be
stale **and** carry a crossed book, and an operator looking at why trading stopped should
see both rather than whichever the engine happened to check first.

## What it blocks on

| Condition | `reason_code` |
|---|---|
| The freshest quote is older than `data_guard.max_data_age_s` | `market_data_stale` |
| Nothing has arrived at all | `no_market_data` |
| A crossed book: the bid is above the ask | `negative_spread` |
| A decision bar in the published window produced no candle | `missing_candle` |

The first three of those are named by the phase criteria. **`no_market_data` is the
fail-closed case invariant 3 requires** — a gate that cannot reach its data blocks — and
it is a separate code from `market_data_stale` on purpose: "Market data is older than the
guard allows" is a *false sentence* when there is none, and it would send an operator
looking for a lagging feed rather than an absent one.

Every code has a matching entry in `REASON_PROSE` in `console/format.py`. **A code that
is not in that map renders as "No reason was recorded." silently, with no error
anywhere** — so the codes are fixed, were agreed with Agent C, and
`tests/engines/test_data_guard.py` asserts the map contains every one the engine can
emit, deriving the list from this engine's own constants so it cannot decay.

## What it does not block on

- **A zero spread.** This gate blocks on a *crossed* book. A zero or absent spread is
  engine 10's refusal to make — invariant 2 says an assumed spread invalidates the cost
  gate — and that is a different refusal in a different place.
- **A failed exchange fetch.** Engine 1 reports those; engines 10 and 11 block on them.
  This gate judges *market data*, not the account picture.
- **The outage count.** Counting consecutive blocked ticks and escalating is engine 17
  `safety`, which is Phase 3. This engine does not write to `block_records` either —
  engine 19 `memory` is the single writer of relational rows, in Phase 4.

## The missing-candle rule is not a contradiction

`architecture-context.md` says a missing candle in the **historical archive** means no
trades occurred and is *not* a data error, and spec 30 forbids the loader from
interpolating one. Both of those hold, and so does this gate.

**The loader must never *invent* a bar. This gate must never *act* on a series with a
hole in it.** Fail-closed points in opposite directions for labelling and for trading: a
synthesised candle poisons a label, and acting on a gap risks money on a price nobody
observed. Someone "fixing" one of them by breaking the other is the hazard worth naming,
which is why it is stated here, next to the constant in `contracts.py`, and in a test.

## It has no escape hatch

`is_gate = True`, matching the registry table, which `is_gate_matches_registry` asserts.
There is no bypass parameter, no warn-only mode, and no model output that can override it
— invariant 4. `AGENTS.md`: invariants outrank tests, and a test that fails because a gate
blocked is the test that is wrong.

**A block here does not stop the guard chain.** `safety` still runs on the same tick and
every blocker is recorded; the orchestrator owns that, and this engine simply reports
honestly. `tests/engines/test_data_guard.py` proves it by driving the **real**
`Orchestrator` with a second guard behind this one — an engine cannot prove a property of
the chain it sits in.

**A block does not stop recording either.** Engine 2 has already run and the archive is
written regardless: a block says the data cannot be *traded on*, not that it is not worth
keeping. Data recorded during an outage is how the outage gets analysed.

## Thresholds

`data_guard.max_data_age_s`, from config, and nothing else.

**A missing key raises.** `config.get` refuses rather than returning `None`, the
orchestrator turns that into `ERROR`, and `ERROR` blocks. That is the correct fail-closed
answer for a threshold nobody has set, and a `KeyError` naming the key is better
documentation of the gap than a placeholder would be. As of 2026-09-09 the operator has
not yet supplied it, and `data_guard_blocks_bad_data` reports **PENDING naming the key**
rather than FAIL — because a *configured* data guard does not exist yet, which is what
PENDING means.

## The fixtures

`BAD_DATA_SCENARIOS` in `contracts.py` maps `clean`, `stale`, `negative_spread`,
`missing_candle` and `no_market_data` to a `state` ready to hand to this engine.

They live in this engine's contracts module rather than in `scripts/verify.py` because
the fields they set belong to engines 1 and 3 — a gate that hardcoded another engine's
field names in a fixture would be asserting on a shape it does not own.

**Each bad scenario differs from `clean` in exactly one respect**, asserted by a test. A
fixture that was stale *and* crossed would let a gate that only checked staleness pass the
negative-spread case.

**Use `bad_data_state(name)` if you intend to modify one.** It returns a deep copy;
`dict(BAD_DATA_SCENARIOS[name])` copies only the outer layer and shares
`state["market_sensor"]` with the module-level fixture, so a caller that writes into it
silently changes every consumer that runs afterwards. That happened once in this engine's
own tests, and the failure surfaced three tests away from the cause.
