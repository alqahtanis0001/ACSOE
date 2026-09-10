# Engine 2 — `market_data_recorder`

**Number:** 2 · **Chain:** guard · **Gate:** no · **Runtime stage:** 1

The framework recorder. Every tick it drains whatever the WebSocket stream buffered
since the last tick and appends it, verbatim, to the append-only archive in
`data/raw/`.

## What it reads from `state`

`state["exchange"]`, published by engine 1 on the same tick, and nothing else. It uses
`pair_rules` and `balances` to work out what the socket should be subscribed to — see
the next section. Everything else about the recording is read from the stream.

The key `"exchange"` is **written out** in `contracts.py` rather than imported from
`engines/exchange/contracts.py`: contract rule 3 says an engine never imports another
engine. The duplicate is held honest by
`tests/engines/test_subscription_scope.py::test_the_duplicated_state_key_still_matches_engine_ones`,
which imports both and asserts they are equal — a test may reach across the boundary
that production code may not.

## The subscription scope, which is not the tradable universe

**This is the distinction to get right, and the second name must not leak into this
code.** The subscription scope is what the socket pays attention to: the pairs worth
asking for, so that a thousand books the account could never trade in any currency are
not carried across the network and into the archive. The *tradable universe* is what
may be traded, engine 7 `scout` is its sole authority, it is recomputed every tick, and
a pair inside this scope is routinely outside that universe.

It is **derived every tick, never configured.** There is no pair list, no default and
no config key holding one — `market_data.pairs` and `book_depth` do not exist and are
not going to, because the universe is computed per tick and a typed list of three
symbols would contradict that. The daemon starts subscribed to nothing and engine 1's
first tick is what tells the socket where to listen.

A pair is in scope when all three hold:

1. it has rules in `state["exchange"]["pair_rules"]["pairs"]`;
2. the account holds a **strictly positive** balance in its `quote` currency, per
   `state["exchange"]["balances"]` — invariant 7, and zero is not spendable;
3. it is not crypto-quoted, unless `trading.allow_crypto_quoted`. A quote counts as
   crypto when it is not in `trading.stable_quote_currencies`.

**Nothing economic enters this filter.** No `ordermin`, no `costmin`, no spread, no
equity, no price. That is engine 7's job and this is not it.

### When a fetch failed, the scope is left exactly as it was

If `pair_rules` or `balances` did not arrive, the scope is **not recomputed** and
nothing is unsubscribed. "I do not know" is a different answer from "nothing
qualifies", and the two are different values in the code: `subscription_scope` returns
`None` rather than `()`. Unsubscribing on a transient private-call failure would put a
hole in the order-book history of every pair, and that history cannot be recovered
afterwards.

This engine remembers nothing between ticks and does not need to. **The subscription
belongs to the stream, not to the engine**, so leaving it alone is the absence of an
action rather than the restoration of a remembered value.

Moving the scope is a **delta on the live socket** — a `subscribe` for what arrived, an
`unsubscribe` for what left, and silence for everything that stayed. Never a reconnect:
dropping the socket to change one symbol would break the history of every other pair.
A tick where the scope has not moved sends nothing at all, which is the common case.

### When the stable-quote set is absent, the exclusion is skipped and says so

`crypto_quoted_excluded` reports whether the crypto-quoted rule actually ran, which is
not the same as `trading.allow_crypto_quoted` being false: the rule also needs
`trading.stable_quote_currencies`, and while that key is absent the rule cannot be
applied. Engine 2 then proceeds with the balance rule alone and publishes the fact.

That is a **lead ruling**, and it is deliberately the opposite of engine 7's, which
excludes every pair not provably stable. The two engines answer different questions and
have opposite irreversible errors: over-subscribing here costs bandwidth while
under-subscribing destroys data that cannot be recovered, whereas over-including in the
universe risks a trade the operator explicitly disabled. No trade can occur in a
crypto-quoted pair on account of what this engine subscribes to; invariant 7's
enforcement lives in engine 7 and only there.

A published absence, not a silent default — the same shape as `failed_fetches`.

## What it writes into `state["market_data_recorder"]`

| Key | Meaning |
|---|---|
| `stream_available` | False when the injected client exposes no market stream at all |
| `connected` | Whether the stream believes it has a live socket right now |
| `frames_recorded` | Raw frames appended this tick |
| `gaps_recorded` | Breaks written into the archive this tick, each with its own cause |
| `dropped_frames` | **Cumulative** frames the stream lost to a full buffer |
| `unparsed_frames` | **Cumulative** frames recorded verbatim that yielded neither a trade nor a quote |
| `subscription` | The pairs the stream is subscribed to at the end of this tick, sorted |
| `subscription_derived` | True when this tick recomputed the scope; false when it left it alone |
| `crypto_quoted_excluded` | Whether the crypto-quoted rule actually ran this tick |

The last two are cumulative on purpose. A buffer overflow is a fault about the
*process*, not about the minute it happened in, and zeroing it every tick would make
it almost impossible to notice. A rising `unparsed_frames` is the signal that the
field names in `clients/kraken/ws.py` no longer match what Kraken sends — the cost of
the lenient parse, made visible.

Every field here is a count of something that would otherwise be invisible. **A
recorder that quietly wrote nothing looks exactly like a quiet market**, and that is
the failure the whole recording exists to make impossible.

## It runs while frozen, and that is the point

The guard chain runs every tick in every mode, and this engine is in it. A freeze
stops trading; it never stops data collection. Order-book and spread history cannot
be recovered retroactively, so a minute not recorded is a minute gone — which is why
`scripts/record.py` exists at all and why engine 2 lives in the guard chain rather
than anywhere else.

A `data_guard` block does not stop it either. Recording continues through a block:
the block is a statement about whether the data can be *traded on*, not about whether
it is worth keeping. Data recorded during an outage is how the outage gets analysed.

## It is not a gate and it never blocks

`is_gate = False`, matching the registry table. A dead feed is engine 4's judgement to
make, on the market data itself. Engine 2's job is to write down what arrived and what
did not, and to be honest in `state` about both.

A client with no stream — C's fake Kraken client is exactly that — is **reported, not
raised**: `stream_available` is false and the tick continues. Raising there would take
the whole guard chain to `ERROR` on a tick where nothing is actually wrong, and would
make the orchestrator untestable against the standard fake.

## A break is written into the archive, never healed

Gaps are **drained** from the stream and appended as `gap` marker lines carrying their
own cause. Drained rather than read, so this engine stays stateless across cycles
(architecture invariant 1) and never has to remember which breaks it already wrote —
the kind of bookkeeping that silently duplicates or silently drops one after a
restart.

A gap marker's `ts_recv` is the **gap's own end**, not the moment the loop noticed it.
The length of a break is not known until it ends, which is why the stream writes it on
reconnect and why nothing here edits it afterwards. Invariant 11.

## The line schema is not new

It is the seven-key schema `scripts/record.py` has been writing since Phase 0, defined
in `clients/recorder/contracts.py`:

```
v  kind  pair  channel  ts_exchange  ts_recv  payload
```

**It must not drift.** `tests/fixtures/record_sample.jsonl` is 25 committed lines of
it and the Phase 0 criterion `record_sample_valid` validates that sample against the
script's own validator. The engine supersedes the script; the format stays identical,
so the archive is one dataset rather than two.

`scripts/record.py` stays on disk and stays working. It is superseded, not deleted: it
imports nothing from `src/acsoe/`, so it is the fallback for when the engine framework
is down, and `architecture-context.md` describes it as the day-one recorder.

`validate_line` is deliberately duplicated between the script and
`clients/recorder/contracts.py` rather than shared, because the script must keep its
zero-dependency property. `tests/clients/recorder/test_schema.py` asserts the two
agree by running both over the same committed sample — which is a stronger guarantee
than sharing the code would give, since it also proves the *committed evidence* still
validates.

## Book depth is the recorder's own parameter, not a config key

`BOOK_DEPTH` in `contracts.py`, and it is 10 because that is `DEFAULT_DEPTH` in
`scripts/record.py`. Engine 2 supersedes that script, so a depth that disagreed with it
would split the archive into two datasets at the moment the daemon took over — and
invariant 11 makes that unrepairable afterwards. Changing it is a decision about the
recording, so it lives beside the recording rather than in an operator's YAML.

## `ts_recv` is stamped by the stream, not by this engine

The stream stamps it from the injected clock at the moment the frame is read. It
cannot be stamped here instead: the engine sees the frame up to a minute later, and a
receive time that was really a drain time turns a latency measurement into a
measurement of the loop tick.

## The committed digest

`tests/fixtures/recording_report.json`, built by `scripts/recording_report.py` from
`clients/recorder/report.py`. It reports a `span`, a list of `segments` and a list of
`gaps`, and **the segments and the gaps tile the span exactly** — every microsecond
between the first frame and the last is claimed either as recorded or as a named
break, so a hole in the tiling is a break nobody accounted for and there is nowhere
for one to hide.

Two kinds of break are both gaps there: an **explicit** one, from a `gap` marker
carrying its disconnect reason, and an **implicit** one — a stretch with no frame at
all, longer than the silence threshold. The second is what a recorder that was *not
running* leaves behind, and it writes no marker precisely because it was not there to
write one.

`scripts/recording_report.py` **refuses to write a digest whose span is under 24
hours**. A short digest would be truthful and would still fail the gate, which is
worse than the PENDING it reports while waiting. There is no flag that fabricates a
span.
