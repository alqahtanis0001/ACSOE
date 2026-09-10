# 38 — TTL-bounded caching in the Kraken REST client

**Owner:** A — Platform

**Phase:** 3 — Economics.

## Goal

`AssetPairs` and `TradeVolume` stop being re-fetched on every one-minute tick, and invariant
2's sentence *"a cache stale beyond its TTL counts as a failed fetch"* becomes a property of
the client rather than a claim in a document. Today there is no cache and therefore no TTL,
so the rule has nothing to be true of.

## Implementation

1. **Before anything else in this spec, add the `cache_ttl_s` field to
   `KrakenSection` in `src/acsoe/platform/config.py`, then tell the lead.** That model sets
   `extra="forbid"`, so the YAML key and the model field must land in one change — the lead
   tried the YAML alone on 2026-09-10 and `load_config()` raised, failing every test in the
   tree until it was reverted. The lead authors `config/default.yaml` and pastes the block
   from spec 37's appendix the moment your field exists; you own the loader. Neither half is
   committed without the other.
2. In `src/acsoe/clients/kraken/rest.py`, cache the parsed `PairRulesSnapshot` and
   `FeeTierSnapshot` from a successful call, each with the `fetched_at` it already carries.
   A call inside its TTL returns the cached snapshot without touching the network.
3. TTLs come from config: `kraken.cache_ttl_s.asset_pairs` and
   `kraken.cache_ttl_s.trade_volume`. **Never a literal**, and the two are read separately —
   a single shared TTL is the shape this spec exists to prevent. Validate them as you
   validate every other threshold: a null is OPERATOR REQUIRED and the process refuses to
   start.
4. **A cache past its TTL is a failed fetch, not a stale value.** When the TTL has expired
   the client re-fetches; if that re-fetch fails, the call **raises** exactly as it does
   today. It does not return the expired entry. This is the half of invariant 2 that
   protects the kill switch, and the wording that makes it easy to get wrong is in the
   invariant itself: *for trading*, a stale value does not exist.
5. **Retention is untouched and is a separate mechanism.** `last_known_good_asset_pairs` and
   `last_known_good_balances` keep the last successful value forever, past any TTL, for rule
   14 only. The cache answers *"may I use this now"*; retention answers *"what is the last
   thing we knew"*. Do not merge them into one field, and do not let the TTL expiry discard
   the retained value.
6. **`TradeVolume` is not retained and must not become retained.** Invariant 2 is explicit:
   its only reader is the cost gate, and an assumed fee invalidates that gate. A TTL cache
   for it is legitimate; a last-known-good for it is not.
7. Age is computed against the **injected clock**, never `time.time()`. The client already
   takes a `Clock`; use it. `context.now` is not reachable from here, and a direct clock read
   inside the client would make a replay unfaithful in exactly the layer replay depends on.
8. Update `src/acsoe/clients/kraken/README.md`: what is cached, for how long, what expiry
   does, and the one-line statement that cache and retention are different mechanisms with
   different readers.

## Scope Limits

- Do **not** cache `Balance` or `order_book`. Balances change on every fill and a stale
  spread is the loaded gun invariant 2 names; both stay per-call.
- Do **not** return an expired entry under any flag, config key, or "degraded mode".
- Do **not** change, discard, or gate the last-known-good retention. Rule 14 depends on it
  surviving exactly the failure that expires a cache.
- Do **not** add a fee, an order minimum, a tick size, or a precision — not as a seed value
  for an empty cache, not as a fallback, not in a comment.
- Do **not** read the clock directly anywhere in this package.
- Do **not** touch the engines. Engine 1 calls the same three methods before and after.

## Check When Done

- **Both halves, as a pair.** A second call inside the TTL returns the cached snapshot and
  makes **no** HTTP request (assert on the transport, not on the return value — an
  identical snapshot proves nothing about whether the network was touched). A call after the
  TTL makes a request.
- A call after the TTL whose re-fetch fails **raises**, and does not return the expired
  entry. Assert the exception, and assert the expired value was not returned.
- After that same failure, `last_known_good_asset_pairs` still holds the pre-expiry
  snapshot. Retention survives the expiry that blocked trading — one test, both facts.
- The two TTLs are read from separate keys: a test that sets them to different values and
  proves `AssetPairs` and `TradeVolume` expire independently. A single-TTL implementation
  passes a same-value test and fails this one.
- Time is advanced through the injected clock in every one of the above. No `sleep`.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
