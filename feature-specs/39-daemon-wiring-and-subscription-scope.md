# 39 — `acsoe engine` gets real clients, and the stream learns what to subscribe to

**Owner:** A — Platform

**Phase:** 3 — Economics. Carried out of Phase 2 as a deliberate deferral, and unblocked by
the operator's ruling that `market_data.pairs` and `book_depth` stay undefaulted.

## Goal

`acsoe engine` stops constructing itself with three `None` client slots. The daemon runs a
real tick against a real Kraken client, a real store and a real recorder, and the WebSocket
subscribes to a set of pairs derived from what the account can actually spend rather than
from a list anyone typed.

## Implementation

1. In `src/acsoe/cli/engine.py`, construct and inject the three real clients: the Kraken
   client from `clients/kraken/`, the store client from `clients/store/`, and the recorder
   from `clients/recorder/`. The `Clients` dataclass keeps its three names; only the values
   change. Credentials come from the environment through `platform/config.py` as they
   already do, and the daemon starts in paper mode with no key present.
2. **A missing key is not a startup refusal.** Paper mode is the default and must run on a
   fresh clone. The private calls fail, engine 1 records the failure in `failed_fetches`,
   and every gate that needs a value it did not get blocks — which is invariant 3 working.
   Do not add a startup check that refuses to run without credentials; the live-mode guard
   is invariant 1's job and is Phase 8.
3. **The subscription set is derived, never configured.** Engine 2
   `market_data_recorder` decides what the stream is subscribed to, from
   `state["exchange"]` published by engine 1 on the same tick:
   - every pair in `pair_rules.pairs`
   - whose `quote` the account holds a **positive** balance in, per `balances`
   - excluding crypto-quoted pairs unless `trading.allow_crypto_quoted` is true.

   Nothing economic enters this filter — no `ordermin`, no `costmin`, no spread. That is
   engine 7's job and this is not it.
4. **Say plainly in the engine's `README.md` what this set is and is not.** It is the
   *subscription scope*: the pairs the system pays attention to, chosen so the socket is not
   asked for a thousand books the account could never trade in any currency. It is **not**
   the tradable universe. Engine 7 `scout` is the sole authority on that, it computes it per
   tick, and a pair inside the subscription scope is routinely outside the universe. Two
   different questions; do not let the second name leak into this code.
5. When `pair_rules` or `balances` is absent because the fetch failed, the subscription set
   is **unchanged** — the existing subscription stays live and nothing new is added. Do not
   fall back to a default list and do not unsubscribe from everything: dropping the stream
   on a transient private-call failure would destroy the order-book history that cannot be
   recovered, which is the one thing this system may never do.
6. Book depth is a parameter of the subscription call. Take the value engine 2 already uses
   for the recorder and keep it there, in A's code, as the recorder's own parameter. **Do
   not add a `book_depth` config key.**
7. Replace the Phase 2 test that pins "the daemon blocks on every tick with empty client
   slots" — it exists to turn red when this lands, and it has done its job. The
   replacement asserts the daemon completes a tick with real clients injected.

## Scope Limits

- Do **not** add `market_data.pairs`, `market_data.book_depth`, or any config key holding a
  list of pairs. Three hardcoded pairs contradict a Locked Decision.
- Do **not** compute, publish, or name a tradable universe here. No `ordermin`, no
  `costmin`, no tick size, no spread arithmetic in this spec's code.
- Do **not** import from `src/acsoe/engines/scout/`. Engine 2 reads `state["exchange"]`,
  which is the contract; reaching into another engine's module is contract rule 3.
- Do **not** let a test reach the network. The autouse guard in `tests/conftest.py` stays.
- Do **not** make the daemon refuse to start without credentials.
- Do **not** write in `core/` or `bootstrap.py`.

## Check When Done

- `acsoe engine` starts with real clients, completes at least two ticks against C's fake
  Kraken client and a temporary database, and exits cleanly on the stop event.
- The subscription set changes when the balances change: a test with `USD` held subscribes
  to USD-quoted pairs and not to EUR-quoted ones, and the reverse with `EUR` held. A
  hardcoded list passes neither direction.
- `allow_crypto_quoted: false` excludes a BTC-quoted pair that is otherwise eligible;
  flipping it to true includes it.
- A tick where the `AssetPairs` fetch fails leaves the subscription **unchanged** — asserted
  against the subscription the previous tick established, not against an empty set.
- `grep -rn "BTC/USD\|ETH/USD\|SOL/USD" src/acsoe/cli/ src/acsoe/engines/market_data_recorder/`
  returns nothing.
- `pytest tests/ -q` · `mypy --strict src/` · `ruff check src/` · `python scripts/verify.py --phase 3`
