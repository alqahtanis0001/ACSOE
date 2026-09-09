# `clients/kraken/` — the system's only route to the exchange

No engine opens a socket and no engine calls `httpx`. Everything the exchange knows
arrives through this package, and everything the exchange can tell us is fetched
here at runtime rather than remembered.

| File | What it is |
|---|---|
| `contracts.py` | The models every consumer reads. Lands first; B and C mock against it. |
| `errors.py` | `KrakenError`, `KrakenAPIError`, `KrakenUnavailableError`. |
| `limiter.py` | The token bucket both transports share. |
| `rest.py` | REST: the envelope, the field mapping, the retention. |
| `ws.py` | WebSocket v2: a background stream a synchronous loop can drain. |
| `client.py` | `KrakenClient` — REST plus stream, the one object `context.clients.kraken` holds. |

## The envelope rule

**Kraken returns errors with HTTP 200.** Every response is wrapped in
`{"error": [...], "result": {...}}` and the status code does not signal application
errors, so a 200 carrying a populated `error` array is a failure, not a success. A
client that trusts the status code records rejections as fills.

`parse_envelope` in `rest.py` is the only place a response body is opened, and it
has **two** obligations, not one:

- a non-empty `error` array raises `KrakenAPIError`, whatever the status was; **and**
- an empty `error` array parses cleanly and yields its `result`.

Both are asserted, as a pair, in `tests/clients/kraken/test_rest.py`. A parser that
raised on every response would satisfy the first perfectly and be useless — the
only property the envelope has is *discrimination*, and one assertion cannot
demonstrate it.

A body that is not an envelope at all — a proxy error page, a truncated read — is
`KrakenUnavailableError`: "we did not get an answer" rather than "we got an answer
and it was no". Both block. Only the second is worth retrying.

## What is fetched at runtime, and never written down

**There is no fee, order minimum, tick size or precision anywhere in this package.**
Not as a constant, not as a fallback, not in a comment that later becomes code.
Invariant 2 of `context/trading-invariants.md` is absolute, and `AGENTS.md` says any
Kraken number an agent remembers is stale.

| Value | Source | Model |
|---|---|---|
| Maker and taker fee, tier | `POST /0/private/TradeVolume` | `FeeTierSnapshot` |
| `ordermin`, `costmin`, tick size, decimals | `GET /0/public/AssetPairs` | `PairRulesSnapshot` |
| Balances | `POST /0/private/Balance` | `BalancesSnapshot` |
| Spread | `GET /0/public/Depth`, or the live ticker stream | `OrderBookSnapshot`, `QuoteTick` |

The client never supplies a fallback for any of them. `map_trade_volume` raises when
a fee field is missing rather than assuming a tier, and a pair whose `AssetPairs`
entry is incomplete is dropped from the snapshot rather than defaulted. That is
deliberate: invariant 2's paper-mode fallbacks are decisions made by the *consumer*,
which must record which fallback fired, and a client that quietly supplied one would
make that record impossible.

### The field-name assumption

The four `map_*` functions in `rest.py` are the one part of this package that cannot
be proved offline, and the same is true of `sign_request`. They are written against
the committed fixtures in `tests/fixtures/kraken/` and are confirmed against the live
endpoints by `--live`, which is opt-in and never required for a phase to be green.
They are isolated into named functions precisely so that confirming them is a small
obvious edit. A renamed field shows up as a `KrakenUnavailableError` naming the field
— a block — never as a default.

## Retained last-known-good values

Two calls retain their last successful result with the time it was fetched, and
**never discard it on a failure**:

- `last_known_good_asset_pairs`
- `last_known_good_balances`

They exist for one reason: rule 14's emergency liquidation is triggered by an outage
and has to complete *during* that outage, so it needs to know what the account holds
and how to round a quantity. Discarding on failure would make rule 14
unimplementable at exactly the moment it is needed. **Only rule 14 may read them.**

**The fee tier and the order book are deliberately not retained**, and being generous
about that would be a defect rather than a convenience. Their only reader is the cost
gate, and invariant 2 says an assumed spread invalidates that gate outright. A
liquidation does not need a spread: it sells as a taker at whatever the book is,
having already decided that getting flat beats getting a good price.

## Absent is never zero

`OrderBookSnapshot` **cannot be constructed with an empty side**. An empty book has
no best price, and a snapshot that answered `0` would reach the cost gate as a zero
spread — the single input that may never be assumed. So "no book" arrives as an
exception, which blocks, rather than as a plausible-looking snapshot, which does not.

A **crossed** book is the opposite case and is reported faithfully: `spread` may be
negative. Engine 4 `data_guard` blocks on exactly that, and clamping it to zero here
would delete the evidence the gate exists to see.

## Money

`Decimal` in, `Decimal` out. The `Money` annotation **raises on a `float` rather than
coercing it**, because by the time a float reaches a validator the precision is
already gone and accepting it would launder the defect.

**Money crosses `state` as an exact decimal string.** `EngineResult.data` refuses a
`Decimal` — loudly, which is fine — and *accepts* a `float`, which is the silent
half: an engine that hits the refusal and casts to `float` publishes a fee that
arrives in engine 10's hurdle comparison wrong in the fourth decimal. Every snapshot
therefore has a `state_dict()` that goes through `money_text()` = `format(d, "f")`,
which is plain decimal notation with the trailing zeros kept, because the trailing
zeros are the quantum. `format(d, "f")` matches `money_to_text` in `clients/store/`
byte for byte, agreed with Agent B.

## Credentials

`KRAKEN_API_KEY` and `KRAKEN_API_SECRET` come from the environment only, read through
`platform/config.py`'s `load_credentials()` — the one module in the system that reads
the environment. A missing key returns `None` rather than raising, because a fresh
clone with no `.env` must still run the paper pipeline; the two private calls then
raise rather than silently returning something.

**Nothing is ever rendered.** `Credentials.__repr__` and `__str__` both return a
constant, because the commonest way a key reaches a log is that nobody logged it —
an exception was formatted, or a dataclass was interpolated into a message.
`platform/logging.py`'s value scrubber is the second line of defence; this is the
first. Every error from this package carries the method and the path only: never a
header, never a body, never the signed nonce. `tests/clients/kraken/test_secrets.py`
plants a real key, drives a failing signed call, and scans the exception and the
written log file — after asserting the key really was sent, because otherwise the
scan would prove nothing.

## The rate limiter

A token bucket, shared by both transports. Time and sleeping are injected, so its
budget is asserted exactly rather than by waiting.

**The budget has no default.** `capacity` and `refill_per_second` are required
constructor arguments: picking a number here would be a literal in the one file whose
job is to stop the system exceeding it. Config keys have been requested from the
lead; until they exist the construction site supplies them.

The balance is allowed to go very slightly negative after a wait, and that is what
makes `acquire` terminate rather than a rounding shortcut — see the comment in
`limiter.py` and the build-log entry for 2026-09-09.

## The stream, and why it has a thread

The runtime loop is **synchronous** and ticks once a minute; the socket delivers
**continuously**. So `KrakenWebSocketClient` runs on its own thread with its own
event loop, buffers what arrives, and the engines take everything buffered since the
last tick — `drain()` for raw frames (engine 2), `drain_trades()` for executed trades
(engine 3), `latest_quote(pair)` for top of book.

**A break is recorded, never healed.** A disconnect becomes an entry in `gaps` with
its start, end and cause, written on *reconnect* rather than on disconnect, because
the length of a gap is not known until it ends and editing a recording afterwards is
what invariant 11 forbids.

**Frames are recorded verbatim and parsed leniently.** The recording never depends on
the parse succeeding: if Kraken renames a field, the archive — the half that cannot
be recovered later — stays correct and complete, candles simply stop building, and
engine 4 turns that into a block. A strict parser would throw away the irreplaceable
half to protect the recoverable one.

**The buffers are bounded** and an overflow drops the oldest entry and records the
loss as a gap. A silent overflow is impossible; so is a process that grows until it
dies because an engine stopped draining.

## What this package does not do

- **It places no orders.** `AddOrder` is not here and must not be added in this
  phase. Phase 2 is read-only against the exchange; placing an order is Phase 6.
- **It reads no clock.** Every timestamp comes from the injected `Clock`.
- **It applies no fallback.** See above.
- **It touches no network in a test.** `tests/conftest.py`'s autouse guard patches
  both the socket layer and `httpx.AsyncClient.send`, so the REST client injects its
  HTTP at a seam *above* `httpx` and the stream injects its `connect`. That is why
  the guard stays exactly as strict as it is while the envelope, the mapping, the
  retention, the reconnect and the gap marking are all covered offline.
