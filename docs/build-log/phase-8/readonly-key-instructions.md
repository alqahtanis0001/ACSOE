# The read-only Kraken key for `fees.py` — what to do in the morning

**Everything except the key itself is built, gated and pushed.** You create the key while logged
in to Kraken; the code already prefers it the moment it appears in `.env`.

**You do not need to restart anything.** `fees.py` re-reads `.env` on *every* poll
(`read_credentials` is called inside the poll, not at startup), so the running poller picks the
new key up on its **next hourly poll**. Nothing is stopped, nothing is restarted, and the
recorder and supervisor are not touched.

---

## 1. Create the key on Kraken

Kraken → **Settings → API → Add key**.

**Tick exactly one permission:**

| Permission | Set it? | Why |
|---|---|---|
| **Query Funds** | **YES** | This is the one `POST /0/private/TradeVolume` needs. It is the permission the existing key already holds, and the Phase 7 call that returned tier 1 used it |

**Leave every one of these OFF:**

| Permission | Why it must stay off |
|---|---|
| Create & Modify Orders | This key must never be able to trade. The poller only reads a fee tier |
| Cancel/Close Orders | Same reason |
| **Withdraw Funds** | Never, on any key this project uses |
| Deposit Funds | Not needed |
| Query Open/Closed Orders & Trades | Not needed: the poller reads the fee tier, not your order history |
| Query Ledger Entries | Not needed |
| Export Data / Access WebSockets API | Not needed. The poller uses REST only |
| Staking / Earn permissions | Not needed |

**Other settings:** leave the **nonce window** at its default; the poller's nonces are
microsecond-scale and strictly increasing on their own. No IP allowlist is required, though
adding this machine's address does no harm.

**Name it** something you will recognise later, e.g. `acsoe-fees-readonly`.

## 2. Put it in `.env`

Add these two lines to `C:\Users\saad2\Documents\GitHub\ACSOE\.env` (the same file the existing
key lives in; it is gitignored and must stay that way):

```
KRAKEN_READONLY_API_KEY=<the key>
KRAKEN_READONLY_API_SECRET=<the private key Kraken shows you once>
```

**Leave `KRAKEN_API_KEY` and `KRAKEN_API_SECRET` exactly as they are.** The daemon uses those,
and the poller falls back to them if the read-only pair is ever incomplete.

## 3. What happens then

- **Within the hour**, the next poll signs with the read-only key. Nothing else changes.
- The poller writes its result to `data/raw/fees/` as before.
- If you paste only one of the two lines, the poller **falls back to the shared pair and keeps
  working** — a half-written pair is deliberately not an error, because the alternative is
  losing the fee history over a typo.
- If you ever want to check which pair was used, the poller never logs either value (invariant
  13); what you can check is that the hourly line appears and carries no `gap` for
  `trade_volume`.

## Why this is worth doing at all

The poller and the engine daemon share one key today, and Kraken requires a key's nonce to
increase. Both sides count microseconds, and the daemon makes about two private calls a minute
against the poller's one an hour, so a rejection needs two calls inside the same microsecond:
**rare, and visible when it happens** — `fees.py` writes the failed poll down as a `gap` naming
the absence, and the next hour succeeds. So this is insurance on the recorded fee history, not a
fix for anything currently broken.

**What it does not do:** it changes nothing about the daemon, which keeps using the shared key,
and nothing about market-data recording, which uses the public websocket and no credentials at
all.
