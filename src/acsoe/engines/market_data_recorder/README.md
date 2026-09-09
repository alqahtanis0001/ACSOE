# Engine 2 — `market_data_recorder`

**Number:** 2 · **Chain:** guard · **Gate:** no · **Runtime stage:** 1

The framework recorder. Every tick it drains whatever the WebSocket stream buffered
since the last tick and appends it, verbatim, to the append-only archive in
`data/raw/`.

## What it reads from `state`

**Nothing.** It records the feed; it reads nothing another engine wrote.

## What it writes into `state["market_data_recorder"]`

| Key | Meaning |
|---|---|
| `stream_available` | False when the injected client exposes no market stream at all |
| `connected` | Whether the stream believes it has a live socket right now |
| `frames_recorded` | Raw frames appended this tick |
| `gaps_recorded` | Breaks written into the archive this tick, each with its own cause |
| `dropped_frames` | **Cumulative** frames the stream lost to a full buffer |
| `unparsed_frames` | **Cumulative** frames recorded verbatim that yielded neither a trade nor a quote |

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
