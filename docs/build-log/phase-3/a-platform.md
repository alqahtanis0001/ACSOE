# Build log — Phase 3 — a-platform

Append entries as you work, per `context/script-rules.md`. Every non-trivial problem
and its fix, and every decision where two approaches were viable. Not at the end of
the session — three IDE crashes in Phase 1 each took the code and the log at different
moments, and only the entries already written survived.

Minimum headings per entry: What happened, Why, Fix.

The lead consolidates these into `docs/build-log/phase-3.md` at phase close.

## Entries

### Decision: `cache_ttl_s` landed optional, and refuses at the point of use

**Agent:** A · **Task:** spec 38 step 1 · **Date:** 2026-09-10

**Options.** Spec 38 step 1 is a two-sided handoff: I add `cache_ttl_s` to the config
model, the lead pastes the matching YAML block, neither half is committed without the
other. The obvious implementation is a required field — `cache_ttl_s: CacheTtlConfig`
— because every other threshold in `platform/config.py` is required and that is what
"validated like every other threshold" reads as. The alternative is
`CacheTtlConfig | None = None`, with every reader raising on the `None`.

**Chose.** Optional at load, refused at read.

**Because.** A required field is the lead's 2026-09-10 failure with the halves
reversed. The lead pasted the YAML without the model field, `extra="forbid"` made
`load_config()` raise, and every test in the tree failed until it was reverted. A
required model field without the YAML fails in exactly the same place for exactly the
same reason: `tests/conftest.py`'s `paper_config` fixture, `scripts/verify.py` and
`test_engine_starts_against_the_committed_config` all load the committed
`config/default.yaml`, and a required field it does not carry takes all of them down.
Spec 38 also says in as many words *"you can test with a fabricated config until the
YAML lands"*, which is only possible if the shipped file still loads. So the field had
to tolerate the gap, and the gap is real: teammates do not commit, so the working tree
genuinely sits in the half-landed state until the lead acts.

**Nothing was defaulted, and that is the part worth checking.** `None` is not a value
and nothing is computed from it. `Config.get("kraken.cache_ttl_s.asset_pairs")` raises
`ConfigKeyError` when asked to descend through it, and `KrakenRestClient._require_ttl`
raises `KrakenUnavailableError` naming the missing key rather than caching for an
interval nobody chose. Absence fails closed at the point of use, which is the
`data_guard.max_data_age_s` precedent from Phase 2. A `null` in the YAML is still
refused by name at startup by `_refuse_nulls`, which is what spec 38 step 3 actually
asks for — that function scans the raw YAML and never needed the field to be required.

**Cost.** A window in which the shipped config could be missing the key and the daemon
would only discover it at the first fetch. The lead approved closing that window the
moment the YAML landed; the follow-up entry below records it.

### Two mechanisms sharing a word: the cache and the retention

**Agent:** A · **Task:** spec 38 · **Date:** 2026-09-10

**What happened.** The first shape I wrote for the cache used one dictionary keyed by
call name, alongside the existing `self._retained` dictionary keyed the same way. Two
dictionaries with the same keys, the same shape and opposite lifetimes.

**Why that is wrong.** Invariant 2 spends four paragraphs on the fact that "a cache
stale beyond its TTL counts as a failed fetch, and is retained anyway" is two rules
sharing a word. `asset_pairs` is both cached and retained; `trade_volume` is cached and
must never be retained; `balance` is retained and must never be cached. Written as two
parallel dictionaries, the difference between those three is a `frozenset` membership
test in each of two helpers, and the failure mode of getting it wrong is silent — a
retained fee tier would look exactly like a working cache and would price the cost gate
on a fee nobody fetched.

**Fix.** The cache is two named fields, `_cached_asset_pairs` and
`_cached_trade_volume`, each with its own TTL field, its own expiry check and its own
call site. Retention stays in `_retained`. `RETAINED_CALLS` and `CACHED_CALLS` are both
written out as module constants so the asymmetry is visible rather than inferred. Two
separate fields also make "the two TTLs are read separately" structural — there is no
shared object a later edit could make one TTL govern both through.

**One decision inside it.** An entry whose age is *exactly* its TTL is treated as
expired, not fresh (`0 <= age < ttl`). Both readings of "stale beyond its TTL" are
defensible on a boundary; the fail-closed direction is to fetch again, so that is the
one taken, and there is a test pinning the microsecond either side of it. A negative
age — a clock that stood still or moved back — is expired for the same reason.

**Consequence.** An expired entry is dropped from its field *before* the network is
touched, so there is no code path on which it can be returned. That is stronger than
merely not writing the return: a later "optimisation" that reordered the expiry check
would find nothing to return.
