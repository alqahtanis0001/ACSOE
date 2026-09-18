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
deliberate, and read invariant 2 for why rather than a restatement of it here: since
2026-09-16 **there is no paper-mode fallback left anywhere in the system**, so a
failed fetch blocks in paper mode exactly as it does in live. This client reports the
failed call and substitutes nothing, and no consumer substitutes either. A value
quietly supplied here would not be pre-empting somebody else's decision — there is no
such decision left to pre-empt — it would be the only thing in the system still able
to turn a block into a trade.

### The field-name assumption

The four `map_*` functions in `rest.py` are the one part of this package that cannot
be proved offline, and the same is true of `sign_request`. They are written against
the committed fixtures in `tests/fixtures/kraken/` and are confirmed against the live
endpoints by `--live`, which is opt-in and never required for a phase to be green.
They are isolated into named functions precisely so that confirming them is a small
obvious edit. A renamed field shows up as a `KrakenUnavailableError` naming the field
— a block — never as a default.

## The TTL cache, and the retention, which are two different mechanisms

They share the word "kept" and collapsing them breaks the kill switch, so they live
in two separate places in `rest.py` and are described here as two separate things.

**The cache answers "may I use this now."** It is bounded, and past its bound the
answer is no.

| Call | Cached for | Retained? |
|---|---|---|
| `AssetPairs` | `kraken.cache_ttl_s.asset_pairs` — 300s in the shipped config | yes |
| `TradeVolume` | `kraken.cache_ttl_s.trade_volume` — 60s | **no** |
| `Balance` | **not cached** | yes |
| `Depth` (order book) | **not cached** | no |

The two TTLs come from two separate config keys and are held in two separate fields.
There is no single "the TTL" anywhere in the client, because one shared value is the
shape spec 38 exists to prevent, and the easiest way to reintroduce it is to write it
down once. `KrakenRestClient.from_config` is the construction site that reads them;
the constructor still takes them as optional parameters, because tests and scripts
build clients directly and an omitted TTL must fail loudly rather than be guessed at.

**What expiry does.** Past its TTL the entry is dropped *before the network is
touched*, the call re-fetches, and **if that re-fetch fails the call raises**. It
does not return the expired entry, under any flag, config key or degraded mode.
Invariant 2: a cache stale beyond its TTL counts as a failed fetch — for trading, a
stale value does not exist. An entry whose age is *exactly* its TTL is expired, not
fresh, and a negative age (a clock that stood still or was stepped back) is expired
too: fail-closed on a boundary is a re-fetch, never a reuse.

**An absent TTL is not "cache forever" and not "never cache."** It is an unanswerable
question about whether a value is still good, so the call raises
`KrakenUnavailableError` naming the config key an operator would have to supply, and
spends no request finding out.

Age is measured against the **injected clock**, never `time.time()`. A direct clock
read here would make a replay unfaithful in exactly the layer replay depends on.

`Balance` and `Depth` are not cached at all. Balances change on every fill and a
cached one sizes an order that cannot fill; a stale spread is the loaded gun
invariant 2 names.

## Retained last-known-good values

**Retention answers "what is the last thing we knew."** It is unbounded, it survives
a TTL expiry and a failed fetch alike, and it has exactly one reader.

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

**The fee tier is the call where the two mechanisms are most easily confused**, and it
is the one where getting it wrong is silent: it *is* cached and it is *never*
retained. A TTL cache says "this is still good"; a last-known-good would say "use it
anyway". For a fee the second must not exist. So once `cache_ttl_s.trade_volume` has
expired and a re-fetch has failed, there is nowhere in this client holding a fee at
all — which is the correct state, and is asserted as such.

`last_known_good_asset_pairs` surviving the expiry that blocked trading is the pairing
the other way round, and it is one test rather than two: the same snapshot that the
cache has just refused to serve is still the one a liquidation would size against.

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
job is to stop the system exceeding it. They come from `kraken.rest_capacity` and
`kraken.rest_refill_per_s`, which the lead landed with spec 25's request.

**It is one limiter, shared with the stream.** `KrakenRestClient.from_config` takes it
as a parameter rather than building its own, because a factory that made one per
client would give a single account two independent budgets against one rate limit.

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

## The order surface — spec 84, Phase 6

`contracts.py` carries `OrderRequest`, `OrderAck`, `OrderState` and
`OrderClientProtocol`: `add_order`, `cancel_order(userref)`,
`query_orders(userrefs)` and `open_orders()`, all async. Engines 18, 21 and 22
place, cancel and query through that one surface and **cannot tell paper from
live** — the mode difference lives here, in the client layer, which is what makes
a paper run exercise the live code path rather than a parallel one.

**The models are strict about coupling, not about values.** A limit order with no
price, a market order carrying one, `post_only` on a market order, a fill with no
average price, a fill larger than the order, a fee on an order that filled nothing,
a resting order with a close time: each is refused at construction. Nothing here
knows a fee, a minimum, a tick size or a precision — sizes and prices arrive
already rounded by the caller using the pair's own `lot_decimals` and
`pair_decimals`.

**`OrderState` carries `qty` and `limit_price`** — the amendment to spec 84 of
2026-09-16. Without them an order resting at the exchange that the store had never
recorded, because the process died between the placement and engine 19, could be
*detected* by engine 18 and not *described*: no row could be written, so nothing
would ever cancel it, and an order that cannot be cancelled is an unmanaged
exposure — the failure invariant 8 exists to prevent. `qty` is required, because an
optional one could not tell "no quantity was recorded" from "no quantity exists".
`limit_price` follows `OrderRequest`'s coupling — present for a limit order, absent
for a market one — and there is deliberately **no `order_type` beside it**: its
presence *is* the statement, and a second copy of a fact is one more thing that can
disagree. Kraken returns both in `descr` on `OpenOrders` and `QueryOrders`. The one
weakening that leaves — nothing refuses a limit order whose price went missing — is
closed by the lead's ruling of 2026-09-16 **at the consumer that knows the answer**:
engine 18 asked for a post-only buy limit, so a state with no `limit_price` is the
exchange contradicting the placement, and engine 18 refuses to record it.

**`opened_at` completes it.** Optional microseconds since the epoch, from Kraken's
`opentm`, and **absent means the exchange did not say** — not now, and not zero. It
is coupled to nothing (a resting order has an open time and no close time), except
that an order may not close before it opened when both are known; equality is allowed
because in paper one injected clock reading stamps both. With `qty`, `limit_price` and
`opened_at` in, every value engine 18 could not fill from what it structurally knows
is now available, and the unrecorded-order gap narrows to the single case the exchange
itself cannot answer.

`userref` is the key everywhere, not `order_id`. Invariant 8 makes it the system's
idempotency token: the system chooses it *before* the order exists, so it is the
only identifier that survives a placement whose answer never came back. It is
bounded to Kraken's signed 32-bit range on all three models, from one shared
`UserRef` annotation, so the request cannot refuse a value the ack would accept.

**The live client refuses all four, and makes no request.** Live order placement
is Phase 8. The refusal is the first statement in each body — no limiter token, no
nonce, no signature — it names the method and the phase, and there is no flag that
turns it off. A live client that refuses is fail-closed; one that half-works is
not, because an order Kraken accepted and this process did not record is exposure
nothing in the system knows about. In paper mode `build_clients` wraps
`KrakenClient` in B's paper broker (`clients/paper/`, operator ruling 2026-09-16),
which implements the protocol and forwards the read-only calls.

## What this package does not do

- **It places no orders.** The four order methods exist and **refuse**: `AddOrder`,
  `CancelOrder` and `QueryOrders` are not implemented against Kraken and must not
  be until Phase 8. Fills are the paper broker's, never this package's.
- **It reads no clock.** Every timestamp comes from the injected `Clock`.
- **It applies no fallback.** See above.
- **It touches no network in a test.** `tests/conftest.py`'s autouse guard patches
  both the socket layer and `httpx.AsyncClient.send`, so the REST client injects its
  HTTP at a seam *above* `httpx` and the stream injects its `connect`. That is why
  the guard stays exactly as strict as it is while the envelope, the mapping, the
  retention, the reconnect and the gap marking are all covered offline.
